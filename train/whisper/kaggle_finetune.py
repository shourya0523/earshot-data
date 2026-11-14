# Earshot: full fine-tune of whisper small.en on a Kaggle GPU (T4 x2 or P100).
# Paste into a Kaggle notebook cell (or upload train/whisper/kaggle_finetune.ipynb) with: Accelerator = GPU, Internet = On.
# Kaggle Secrets needed: HF_TOKEN (write access, to push the model), GITHUB_TOKEN (read access to shourya0523/earshot-data, if private).
# Output: a private HF model repo <HF_USER>/whisper-ems-small.en-ft-<TAG> (HF format). The data agent converts it to ggml + q5 and evaluates it.
# Runtime: ~85 min data prep (skipped when a prepared earshot_train_data.tar is attached) + ~45-90 min training.
# Version: 2026-11-14 v5 (settings block, faster training, reusable prepared data).
import os, subprocess, sys, json, pathlib, glob

# ---------------- SETTINGS (edit these) ----------------
TAG = "dec"             # run name; model is pushed to <hf-user>/whisper-ems-small.en-ft-<TAG>  (first run, v4, pushed to ...-ft)
LR = 2e-5               # learning rate (v4 run: 1e-5, full model)
EPOCHS = 2              # passes over the training data (v4 run: 3)
FREEZE_ENCODER = True   # True = train only the decoder (vocabulary / drug names; faster). False = full model (v4 run)
SAVE_DATA = True        # write the prepared training audio to /kaggle/working/earshot_train_data.tar (~6 GB) so later runs can
                        # attach this notebook's output as input and skip the ~1.4 h data prep
# -------------------------------------------------------

def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)

from kaggle_secrets import UserSecretsClient
sec = UserSecretsClient()
HF_TOKEN = sec.get_secret("HF_TOKEN")
try:
    GH = sec.get_secret("GITHUB_TOKEN")
except Exception:
    GH = None

# 1) code
repo = f"https://{GH + '@' if GH else ''}github.com/shourya0523/earshot-data.git"
sh(f"git clone --depth 1 -b claude/eager-volta-za1pmi {repo} /tmp/earshot")   # /tmp: big local disk; /kaggle/working is ~20 GB
sh("git clone --depth 1 -b overnight " + repo + " /tmp/pipeline")   # shared/formulary.json lives on the pipeline branch
os.chdir("/tmp/earshot")
sh("pip -q install piper-tts==1.8.0 jiwer soundfile librosa peft 'transformers>=4.45' accelerate huggingface_hub")
sh("apt-get -qq install -y ffmpeg > /dev/null || true")
# point the scripts at the pipeline checkout's formulary
sh("sed -i 's#/home/user/pipeline/shared/formulary.json#/tmp/pipeline/shared/formulary.json#' train/whisper/prepare_data.py")

# 2) data (same scripts and splits as the overnight run; test sets are never used for training)
cached = sorted(glob.glob("/kaggle/input/**/earshot_train_data.tar", recursive=True))
if cached:
    print("re-using prepared data from", cached[0], flush=True)
    sh(f"tar -xf '{cached[0]}' -C /tmp/earshot")
    SAVE_DATA = False
else:
  if True:  # (indent block for the full prep)
    os.environ["HF_TOKEN"] = HF_TOKEN            # authenticated HF downloads (higher rate limits)
    os.environ["EARSHOT_SKIP_MEDWAV"] = "1"      # skip 1,800 one-by-one MedIntent clips (low value, very slow)
    os.environ["PYTHONUNBUFFERED"] = "1"
    for step in ["piper", "real", "more", "round2", "round3", "fsd", "zenodo", "ev"]:   # one step per call so progress shows
        sh(f"python3 -u data/collect/download_all.py --only {step} --skip-big")
    sh("python3 data/collect/prepare_real.py")
    sh("python3 data/collect/prepare_extra_human.py --delete-parquet")
    os.environ["EARSHOT_NO_CAPS"] = "1"   # GPU: use every real training clip
    sh("python3 data/synth/gen_calls.py --n 80 --split train --seed 1 && python3 data/synth/gen_calls.py --n 10 --split dev --seed 2")
    sh("python3 data/synth/build_synth_set.py train && python3 data/synth/build_synth_set.py dev")
    sh("python3 train/whisper/prepare_data.py")

if SAVE_DATA:
    files = {"train/whisper/data/train.jsonl", "train/whisper/data/dev.jsonl", "train/whisper/data/mix.json"}
    for n in ("train", "dev"):
        for l in open(f"train/whisper/data/{n}.jsonl"):
            files.add(json.loads(l)["wav"])
    open("/tmp/tarlist.txt", "w").write("\n".join(sorted(files)) + "\n")
    sh("tar -cf /kaggle/working/earshot_train_data.tar -T /tmp/tarlist.txt && ls -la /kaggle/working/earshot_train_data.tar")

# 3) fine-tune, low LR, few epochs to keep general English
import torch, numpy as np, soundfile as sf, random
from transformers import WhisperForConditionalGeneration, WhisperProcessor, Seq2SeqTrainer, Seq2SeqTrainingArguments
BASE = "openai/whisper-small.en"
proc = WhisperProcessor.from_pretrained(BASE)
model = WhisperForConditionalGeneration.from_pretrained(BASE)
model.config.forced_decoder_ids = None; model.generation_config.forced_decoder_ids = None
if FREEZE_ENCODER:
    for p_ in model.model.encoder.parameters(): p_.requires_grad = False
print(f"run {TAG}: lr {LR}, epochs {EPOCHS}, freeze_encoder {FREEZE_ENCODER}, trainable params {sum(p_.numel() for p_ in model.parameters() if p_.requires_grad)/1e6:.0f}M", flush=True)
# train with the prompt the pipeline actually uses at inference (shared/ems_terms.json -> initial_prompt on the pipeline branch)
_t = json.load(open("/tmp/pipeline/shared/ems_terms.json"))
prompt = (_t.get("initial_prompt") or ", ".join(_t.get("initial_prompt_core", [])) or open("eval/pipeline_prompt.txt").read()).strip()
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
        if self.rng.random() < 0.5:   # light gain / speed jitter
            y = y * self.rng.uniform(0.5, 1.5)
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

args = Seq2SeqTrainingArguments(output_dir="/tmp/ft", per_device_train_batch_size=8, gradient_accumulation_steps=2, learning_rate=LR,
                                warmup_steps=50, num_train_epochs=EPOCHS, fp16=True, eval_strategy="epoch", save_strategy="epoch", save_total_limit=1,
                                load_best_model_at_end=True, metric_for_best_model="eval_loss", logging_steps=25, report_to=[], dataloader_num_workers=4,
                                remove_unused_columns=False, gradient_checkpointing=False, dataloader_persistent_workers=True)
tr = Seq2SeqTrainer(model=model, args=args, train_dataset=DS(rows("train"), 0.7, 1), eval_dataset=DS(rows("dev"), 1.0, 2), data_collator=collate)
print("dev loss before:", tr.evaluate())
tr.train()
print("dev loss after:", tr.evaluate())

# 4) push (private) - the data agent pulls this, converts to ggml q5, and benchmarks it against stock
from huggingface_hub import HfApi
api = HfApi(token=HF_TOKEN); user = api.whoami()["name"]; rid = f"{user}/whisper-ems-small.en-ft-{TAG}"
api.create_repo(rid, private=True, exist_ok=True)
model.save_pretrained("/kaggle/working/out", safe_serialization=True); proc.save_pretrained("/kaggle/working/out")
open("/kaggle/working/out/train_mix.json", "w").write(open("train/whisper/data/mix.json").read())
json.dump(dict(tag=TAG, lr=LR, epochs=EPOCHS, freeze_encoder=FREEZE_ENCODER, log=tr.state.log_history), open("/kaggle/working/out/train_log.json", "w"), indent=1)
api.upload_folder(folder_path="/kaggle/working/out", repo_id=rid)
print("PUSHED", rid)
print(open("train/whisper/data/mix.json").read())
