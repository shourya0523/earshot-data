# Earshot: full fine-tune of whisper small.en on a Kaggle GPU (T4 x2 or P100).
# Paste into a Kaggle notebook cell (or upload train/whisper/kaggle_finetune.ipynb) with: Accelerator = GPU, Internet = On.
# Kaggle Secrets needed: HF_TOKEN (write access, to push the model), GITHUB_TOKEN (read access to shourya0523/earshot-data, if private).
# Output: a private HF model repo <HF_USER>/whisper-ems-small.en-ft (HF format). The data agent converts it to ggml + q5 and evaluates it.
# Runtime: ~60 min data rebuild (downloads + TTS) + ~60-90 min training (all real clips, 3 epochs).
# Version: 2026-11-13 v3 (round3 human speech, no caps, /tmp data, pipeline's current prompt).
import os, subprocess, sys, json, pathlib

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
sh("python3 -I data/collect/download_all.py --only piper,real,more,round2,round3,fsd,zenodo,ev --skip-big")
sh("python3 data/collect/prepare_real.py")
sh("python3 data/collect/prepare_extra_human.py --delete-parquet")
os.environ["EARSHOT_NO_CAPS"] = "1"   # GPU: use every real training clip
sh("python3 data/synth/gen_calls.py --n 80 --split train --seed 1 && python3 data/synth/gen_calls.py --n 10 --split dev --seed 2")
sh("python3 data/synth/build_synth_set.py train && python3 data/synth/build_synth_set.py dev")
sh("python3 train/whisper/prepare_data.py")

# 3) full fine-tune (encoder + decoder), low LR, few epochs to keep general English
import torch, numpy as np, soundfile as sf, random
from transformers import WhisperForConditionalGeneration, WhisperProcessor, Seq2SeqTrainer, Seq2SeqTrainingArguments
BASE = "openai/whisper-small.en"
proc = WhisperProcessor.from_pretrained(BASE)
model = WhisperForConditionalGeneration.from_pretrained(BASE)
model.config.forced_decoder_ids = None; model.generation_config.forced_decoder_ids = None
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

args = Seq2SeqTrainingArguments(output_dir="/tmp/ft", per_device_train_batch_size=8, gradient_accumulation_steps=2, learning_rate=1e-5,
                                warmup_steps=50, num_train_epochs=3, fp16=True, eval_strategy="epoch", save_strategy="epoch", save_total_limit=1,
                                load_best_model_at_end=True, metric_for_best_model="eval_loss", logging_steps=25, report_to=[], dataloader_num_workers=2,
                                remove_unused_columns=False, gradient_checkpointing=True)
tr = Seq2SeqTrainer(model=model, args=args, train_dataset=DS(rows("train"), 0.7, 1), eval_dataset=DS(rows("dev"), 1.0, 2), data_collator=collate)
print("dev loss before:", tr.evaluate())
tr.train()
print("dev loss after:", tr.evaluate())

# 4) push (private) - the data agent pulls this, converts to ggml q5, and benchmarks it against stock
from huggingface_hub import HfApi
api = HfApi(token=HF_TOKEN); user = api.whoami()["name"]; rid = f"{user}/whisper-ems-small.en-ft"
api.create_repo(rid, private=True, exist_ok=True)
model.save_pretrained("/kaggle/working/out", safe_serialization=True); proc.save_pretrained("/kaggle/working/out")
open("/kaggle/working/out/train_mix.json", "w").write(open("train/whisper/data/mix.json").read())
api.upload_folder(folder_path="/kaggle/working/out", repo_id=rid)
print("PUSHED", rid)
print(open("train/whisper/data/mix.json").read())
