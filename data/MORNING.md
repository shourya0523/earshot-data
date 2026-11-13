# Morning hand-off (data agent)
- **Repo:** `shourya0523/earshot-data`, branch `claude/eager-volta-za1pmi` ([PR #1](https://github.com/shourya0523/earshot-data/pull/1)). Pushing to `sbalsara05/EarShot` was blocked, so copy over later.
- **Data:** ~45 h real speech plus synthetic EMS calls (TTS + noise + knock/snap taps). The 10 test calls have full GT. Leakage check passes. See `data/SOURCES.md`, `SHORTLIST.md`, `RISKS.md`.
- **Dictionary:** RxNorm home meds and observed ASR misspellings, merged into `shared/` by the pipeline agent.
- **ASR (stock small.en):** drug-name WER 35–38% on the test calls and 41% on real clinician speech (threshold 15%). No open model beats it (`eval/BENCHMARK.md`).
- **Pipeline:** reviewed in 3 rounds (`docs/REVIEW.md`); all critical findings are marked fixed. Before the round-3 fixes: NEMSIS valid 10/10, 0 diagnosis leaks, drug precision 0.95. A re-run on the latest pipeline is in `eval/REPORT.md`.
- **Taps:** reference detector gets knock recall 0.94, snap 0.82, and 0 false taps in 10 min of noise. Thresholds went into the firmware contract.
- **Fine-tune:** the owner is running the Kaggle GPU notebook (`train/whisper/kaggle_finetune.ipynb`; mix ≈97% real speech). The CPU LoRA run was stopped. **No model shipped yet; stock stays the default.**
- **Next:**
  1. Pull the Kaggle model from HF, then convert to ggml q5.
  2. Re-run `eval/bench_models.sh` and `eval/run_pipeline.py --asr-model`.
  3. Ship as `models/whisper-ems-small.en-q5.bin` only if it beats stock.
- **Then:** record the 10 calls through the VoiceS3R (`data/RECORDING.md`) and score the team set.
