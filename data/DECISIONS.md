# Decisions log (data agent)

Unattended overnight run. Every judgment call is logged here with a timestamp (ET).

| When (ET) | Decision | Why |
|---|---|---|
| 2026-11-13 03:40 | Work on branch `claude/eager-volta-za1pmi` (the session's assigned branch); poll *all* remote branches for `docs/PIPELINE_READY.md`. | Prompt says "make a new branch"; the environment only allows this branch for pushes. The pipeline agent may be on a different branch. |
| 2026-11-13 03:40 | Commits authored as `shourya0523`; no Claude co-author trailer. | Explicit instruction in the prompt overrides the default attribution. |
| 2026-11-13 03:40 | No GPU budget was set → CPU only (4 vCPU, 15 GB RAM, no GPU in this container). Kaggle/Colab not used unless fine-tuning is required. | "Ask if needed" can't be asked overnight; free tier default. Kaggle web login needs a browser/2FA, so it is not automatable from here. |
| 2026-11-13 03:40 | YouTube: captions only (text), no audio. | Audio download from YouTube is blocked in this environment. Captions give real EMS wording for the dictionary and tagger text. |
| 2026-11-13 03:40 | github.com / kaggle / freesound are blocked; use HF mirrors (PriMock57, FSD50K, ESC-50, Medical Speech & Intent) and zenodo/archive.org. | Network policy. |
| 2026-11-13 03:40 | whisper.cpp built from the source vendored in the `pywhispercpp` 1.5.1 sdist (PyPI). | github.com blocked; PyPI allowed. Same ggml model file `ggml-small.en.bin` from HF `ggerganov/whisper.cpp`. |
| 2026-11-13 03:40 | Large files (audio, weights) are not committed. Manifests carry URL + sha256; `data/collect/download_all.sh` re-fetches; synthetic audio is regenerated deterministically by script. | Keeps the shared branch small; GitHub LFS quota is 1 GB on free plans. |
| 2026-11-13 03:50 | **Push is refused** (`repo_not_connected`: Claude GitHub App not linked for this account). Reads/fetch work. Commit locally, retry push every poll; MORNING.md says how to fix. | Can't be fixed from inside the session. |
| 2026-11-13 03:50 | Remote has no branches yet, so `/shared` doesn't exist. Seed dictionary written to `shared/formulary.json` with schema notes; if the pipeline agent's version appears, merge mine into theirs (their schema wins). | Phase 1 needs the dictionary now. |
| 2026-11-13 04:10 | User granted GitHub access, but push is still refused (`repo_not_connected`). A helper session was created to try `gh`; it hit the same gate (gh token invalid). Work stays committed locally; `eval/poll_pipeline.sh` retries the push every 25 min. | The Claude GitHub App must be installed on `sbalsara05/EarShot`. |
| 2026-11-13 04:10 | Labelled tap → **every** event in the labelling utterance gets source `tap+heard` and the tap's time (e.g. one tap + "BP 158/94, pulse 104, sat 95" = 3 events at the tap time). Scoring is per field, so grouping doesn't change scores. | The spec's event format has one value set per event. |
| 2026-11-13 04:10 | Units/routes that are **not spoken** are omitted from ground truth (e.g. "324 of aspirin, chewed" → dose 324, route PO, no unit). | "Anything not heard stays blank." |
| 2026-11-13 04:10 | Test clips map 1:1 clip time → wall clock (`start` + clip_ms), so 2–3 min calls compress a whole call; eTimes are close together. | Test clips must be 1–3 min. |
| 2026-11-13 04:10 | Whisper's non-speech tags (`[beep]`, `(siren)`) are stripped before WER. Flag for the pipeline: cleanup should drop them, or use `--suppress-nst`. | Stock small.en emits them in monitor/siren noise. |
| 2026-11-13 04:20 | **Repo moved:** the owner asked to use `shourya0523/earshot-data` (branch `claude/eager-volta-za1pmi`, rebased onto its `main`) until access to `sbalsara05/EarShot` works; everything gets copied over later. The poller watches both remotes for `docs/PIPELINE_READY.md`. | Pushes to EarShot are blocked. |
