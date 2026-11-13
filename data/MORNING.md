# Morning hand-off (data agent)

**Repo:** `shourya0523/earshot-data`, branch `claude/eager-volta-za1pmi`, [PR #1](https://github.com/shourya0523/earshot-data/pull/1). Pushing to `sbalsara05/EarShot` was blocked, so copy over later.

**Done**
- Collected about 45 h of real speech, a synthetic pipeline (TTS + noise + taps) and the 10 test calls with full ground truth.
- Wrote the dictionary additions (merged by the pipeline agent) and the provenance and risk docs.

**ASR**
- Stock small.en drug-name WER is 35–38% on the test calls and 41% on real clinician speech (threshold 15%); WER is 12–23%.
- No existing open model beats it (`eval/BENCHMARK.md`).

**Pipeline**
- Reviewed in 3 rounds, with most findings fixed.
- Still open:
  - 5 unsupported drug values (R3-1).
  - Early segment times, which mislabel taps (R3-2).
  - RR recall 0.29 (R3-3).
- Greedy decoding costs about 8 WER points.
- NEMSIS valid 10/10 and 0 diagnosis leaks (`eval/REPORT.md`).

**Taps:** the reference detector gets knock recall 0.94, snap 0.82, and 0 false taps in 10 min of noise. Thresholds are in `docs/REVIEW.md`.

**Running:** the owner is running the Kaggle GPU full fine-tune (`train/whisper/kaggle_finetune.ipynb`). The CPU LoRA run was stopped. No model has shipped yet; stock stays the default.

**Next**
1. When the Kaggle model is on HF, I pull it, convert to ggml q5, and benchmark it plus `earshot-eval` with `--asr-model`. It ships as `models/whisper-ems-small.en-q5.bin` only if it beats stock.
2. Record the 10 calls through the VoiceS3R (`data/RECORDING.md`).
3. Pipeline agent: fix R3-1/2/3 and A/B the prompt.
