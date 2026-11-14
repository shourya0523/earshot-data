#!/usr/bin/env python3
"""Generates train/whisper/colab_finetune.ipynb (Google Colab version of kaggle_finetune.py).
Differences from Kaggle: HF token from Colab Secrets; training data + checkpoints on Google Drive so a disconnect only
costs the steps since the last checkpoint (re-run all cells -> resumes); single GPU (batch 4 x accum 8 = 32 clips/step)."""
import json, pathlib

CELLS = [
"""# Earshot: fine-tune whisper small.en on Google Colab (free T4 works; L4/A100 are faster)
# 1) Runtime -> Change runtime type -> T4 GPU (or better).  2) Secrets (key icon, left bar): add HF_TOKEN (HF *write* token), toggle 'Notebook access' on.
# 3) Put earshot_train_data.tar (from the Kaggle output) in Google Drive at MyDrive/earshot/earshot_train_data.tar  (optional: without it, cell 3 rebuilds the data, ~1.5 h)
# 4) Runtime -> Run all. If Colab disconnects: reconnect and Run all again; training resumes from the last checkpoint on Drive.
# Version: 2026-11-14 colab v1.1 (fix: stale train lists in git were mistaken for prepared data)
TAG = "fmt"             # model is pushed to <hf-user>/whisper-ems-small.en-ft-<TAG>
LR = 1e-5
EPOCHS = 2
FREEZE_ENCODER = False  # True = decoder only (faster, cheap second option)
DRIVE_DIR = "/content/drive/MyDrive/earshot"   # tar + checkpoints live here
SAVE_EVERY = 150        # steps between checkpoints (each ~1 GB on Drive; only the last 2 are kept)""",

"""import os, subprocess, json, glob
def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)
from google.colab import drive, userdata
drive.mount("/content/drive")
os.makedirs(DRIVE_DIR, exist_ok=True)
HF_TOKEN = userdata.get("HF_TOKEN"); os.environ["HF_TOKEN"] = HF_TOKEN
repo = "https://github.com/shourya0523/earshot-data.git"
if not os.path.exists("/content/earshot"): sh(f"git clone --depth 1 -b claude/eager-volta-za1pmi {repo} /content/earshot")
if not os.path.exists("/content/pipeline"): sh(f"git clone --depth 1 -b overnight {repo} /content/pipeline")
os.chdir("/content/earshot")
sh("pip -q install piper-tts==1.8.0 jiwer soundfile librosa peft 'transformers>=4.45' accelerate huggingface_hub")
sh("sed -i 's#/home/user/pipeline/shared/formulary.json#/content/pipeline/shared/formulary.json#' train/whisper/prepare_data.py")
sh("nvidia-smi --query-gpu=name,memory.total --format=csv")""",

"""# data: re-use the prepared tar from Drive (fast) or rebuild (~1.5 h, then saved to Drive for next time)
tar = f"{DRIVE_DIR}/earshot_train_data.tar"
MARK = "/content/earshot/train/whisper/data/.prepared"
if os.path.exists(MARK):
    print("data already extracted")
elif os.path.exists(tar):
    sh(f"tar -xf '{tar}' -C /content/earshot")          # ~5-10 min for 6 GB from Drive
    open(MARK, "w").write("from tar\n")
else:
    os.environ["EARSHOT_SKIP_MEDWAV"] = "1"; os.environ["PYTHONUNBUFFERED"] = "1"
    for step in ["piper", "real", "more", "round2", "round3", "fsd", "zenodo", "ev"]:
        sh(f"python3 -u data/collect/download_all.py --only {step} --skip-big")
    sh("python3 data/collect/prepare_real.py")
    sh("python3 data/collect/prepare_extra_human.py --delete-parquet")
    os.environ["EARSHOT_NO_CAPS"] = "1"
    sh("python3 data/synth/gen_calls.py --n 80 --split train --seed 1 && python3 data/synth/gen_calls.py --n 10 --split dev --seed 2")
    sh("python3 data/synth/build_synth_set.py train && python3 data/synth/build_synth_set.py dev")
    sh("python3 train/whisper/prepare_data.py")
    files = {"train/whisper/data/train.jsonl", "train/whisper/data/dev.jsonl", "train/whisper/data/mix.json"}
    for n in ("train", "dev"):
        for l in open(f"train/whisper/data/{n}.jsonl"): files.add(json.loads(l)["wav"])
    open("/content/tarlist.txt", "w").write("\\n".join(sorted(files)) + "\\n")
    sh(f"tar -cf '{tar}' -T /content/tarlist.txt")
    open(MARK, "w").write("rebuilt\n")
mix = json.load(open("train/whisper/data/mix.json"))
assert mix["train"]["real_hours"] > 20, f"training mix looks wrong (only {mix['train']['real_hours']} h real); expected ~45 h"
print(open("train/whisper/data/mix.json").read())""",

"""# model + data loaders (same recipe as the Kaggle notebook)
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import torch, numpy as np, soundfile as sf, random
from transformers import WhisperForConditionalGeneration, WhisperProcessor, Seq2SeqTrainer, Seq2SeqTrainingArguments
BASE = "openai/whisper-small.en"
proc = WhisperProcessor.from_pretrained(BASE)
model = WhisperForConditionalGeneration.from_pretrained(BASE)
model.config.forced_decoder_ids = None; model.generation_config.forced_decoder_ids = None
if FREEZE_ENCODER:
    for p_ in model.model.encoder.parameters(): p_.requires_grad = False
_t = json.load(open("/content/pipeline/shared/ems_terms.json"))
prompt = (_t.get("initial_prompt") or ", ".join(_t.get("initial_prompt_core", []))).strip()
print("training prompt:", prompt[:120], "...")
tok = proc.tokenizer
prompt_ids = [tok.convert_tokens_to_ids("<|startofprev|>")] + tok(" " + prompt, add_special_tokens=False).input_ids[-223:]
sot, nots, eot = tok.convert_tokens_to_ids("<|startoftranscript|>"), tok.convert_tokens_to_ids("<|notimestamps|>"), tok.eos_token_id
def rows(n): return [json.loads(l) for l in open(f"train/whisper/data/{n}.jsonl")]
class DS(torch.utils.data.Dataset):
    def __init__(self, R, p_prompt, seed): self.R, self.p, self.rng = R, p_prompt, random.Random(seed)
    def __len__(self): return len(self.R)
    def __getitem__(self, i):
        r = self.R[i]
        y, sr = sf.read(r["wav"], dtype="float32", start=int(r["start_s"] * 16000), stop=int(r["end_s"] * 16000))
        if y.ndim > 1: y = y.mean(1)
        if self.rng.random() < 0.5: y = y * self.rng.uniform(0.5, 1.5)
        feats = proc.feature_extractor(y[:480000], sampling_rate=16000, return_tensors="np").input_features[0]
        pre = prompt_ids if self.rng.random() < self.p else []
        seq = (pre + [sot, nots] + tok(" " + r["text"].strip(), add_special_tokens=False).input_ids + [eot])[-448:]
        lab = [-100] * len(pre) + seq[len(pre):]
        return dict(input_features=feats, decoder_input_ids=seq[:-1], labels=lab[1:])
def collate(b):
    L = max(len(x["decoder_input_ids"]) for x in b)
    di = torch.full((len(b), L), eot); lab = torch.full((len(b), L), -100)
    for k, x in enumerate(b):
        di[k, :len(x["decoder_input_ids"])] = torch.tensor(x["decoder_input_ids"]); lab[k, :len(x["labels"])] = torch.tensor(x["labels"])
    return dict(input_features=torch.tensor(np.stack([x["input_features"] for x in b])), decoder_input_ids=di, labels=lab)
big = torch.cuda.get_device_properties(0).total_memory > 30e9      # A100/L4-class: bigger batches
bs, acc = (16, 2) if big else (4, 8)
print(f"run {TAG}: GPU {torch.cuda.get_device_name(0)}, batch {bs} x accum {acc}, lr {LR}, epochs {EPOCHS}, freeze_encoder {FREEZE_ENCODER}")""",

"""# train (checkpoints on Drive; re-running this cell after a disconnect resumes)
ckdir = f"{DRIVE_DIR}/ckpt_{TAG}"
args = Seq2SeqTrainingArguments(output_dir=ckdir, per_device_train_batch_size=bs, gradient_accumulation_steps=acc, learning_rate=LR,
                                warmup_steps=50, num_train_epochs=EPOCHS, fp16=True, eval_strategy="steps", eval_steps=SAVE_EVERY,
                                save_strategy="steps", save_steps=SAVE_EVERY, save_total_limit=2, load_best_model_at_end=True,
                                metric_for_best_model="eval_loss", logging_steps=25, report_to=[], dataloader_num_workers=2,
                                remove_unused_columns=False, gradient_checkpointing=not big)
tr = Seq2SeqTrainer(model=model, args=args, train_dataset=DS(rows("train"), 0.7, 1), eval_dataset=DS(rows("dev"), 1.0, 2), data_collator=collate)
resume = bool(glob.glob(f"{ckdir}/checkpoint-*"))
if not resume:
    print("dev loss before:", tr.evaluate())
tr.train(resume_from_checkpoint=resume or None)
print("dev loss after:", tr.evaluate())""",

"""# push the best model (private HF repo) for the data agent to benchmark
from huggingface_hub import HfApi
api = HfApi(token=HF_TOKEN); user = api.whoami()["name"]; rid = f"{user}/whisper-ems-small.en-ft-{TAG}"
api.create_repo(rid, private=True, exist_ok=True)
out = "/content/out"; model.save_pretrained(out, safe_serialization=True); proc.save_pretrained(out)
open(f"{out}/train_mix.json", "w").write(open("train/whisper/data/mix.json").read())
json.dump(dict(tag=TAG, lr=LR, epochs=EPOCHS, freeze_encoder=FREEZE_ENCODER, platform="colab", log=tr.state.log_history), open(f"{out}/train_log.json", "w"), indent=1)
api.upload_folder(folder_path=out, repo_id=rid)
print("PUSHED", rid)""",
]

nb = {"cells": [{"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": c.splitlines(True)} for c in CELLS],
      "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "provenance": []}, "kernelspec": {"name": "python3", "display_name": "Python 3"},
                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
p = pathlib.Path(__file__).with_name("colab_finetune.ipynb")
p.write_text(json.dumps(nb, indent=1))
for c in CELLS:
    compile(c, "cell", "exec")
print("wrote", p)
