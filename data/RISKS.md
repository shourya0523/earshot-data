# Risks: licensing, privacy, bias (data agent)

## Licensing
| Risk | Affected data | What we did / what the team must do |
|---|---|---|
| **No license stated** | EMSContExt_audio, EMSAssist-2, saahith/synthetic_with_val, dispatcher-ambulance, gelang/emergencyvehicle, ADE corpus, MedIntent (Figure Eight; a Kaggle copy says CC BY-NC-SA 4.0, unverified) | Used for internal evaluation and research fine-tuning only. **Before any model trained on these ships commercially**, get permission or retrain without them. Each one is tagged in `data/manifests/raw_manifest.jsonl`, so a "commercial-clean" retrain is a manifest filter. |
| **Non-commercial** | ESC-50 (CC BY-NC), UrbanSound8K (not used), Stockton scanner (CC BY-NC-ND), some FSD50K clips (excluded by license filter) | ESC-50 and Stockton are used **only as eval noise** and never in training audio. FSD50K clips with NC licenses were dropped at download. |
| **Research-use only** | BC5CDR (BioCreative) | Text for tagger experiments only. |
| **YouTube** | 6–24 EMS videos' captions | Text only, never redistributed, used for vocabulary and phrasing. No audio was downloaded. |
| **Attribution required** | CC-BY: PriMock57, ACI-Bench, MTS-Dialog, DEMAND, Knocking (Zenodo), FSD50K CC-BY clips, Piper voices | Keep `data/SOURCES.md` with any model card. Model cards list training sources. |
| **Model licenses** | whisper small.en (MIT), Piper voices (per voice card), any base tagger (see model card) | Recorded in `models/*.md`. |

## Privacy
- **Real patient audio:** none was collected. All "real" audio is read speech, mock consultations (actors) or de-identified clinician speech (Eka). Dispatch radio (archive.org) can contain addresses and unit IDs on air, so it is used only as low-level background noise in eval clips and never transcribed or trained on.
- **PII scrub:** transcripts of real sources pass through `data/collect/scrub_pii.py`, which replaces names, street addresses and DOBs with `[NAME]`, `[ADDRESS]` and `[DOB]`. The scrub is conservative regex plus a first-name list, so it **will miss** lowercase or unusual names. Any clip whose transcript was scrubbed is **excluded from ASR training**, because its audio still contains the spoken PII.
- **Speaker identity:** EMSAssist-2 filenames contain a reader's first name. It is replaced by a hash in our ids.
- **Team recordings** (`data/RECORDING.md`): scripts contain no real patient data. Keep the audio out of git, store it on the team drive, and get each reader's consent to keep their voice recordings.
- **Product:** the app must not store audio. The reviewer checked this: the pipeline path writes none, but `make-replay` does (eval-only; see `docs/REVIEW.md` M11).

## Bias and coverage
- **Accents:** most "real" audio is UK English (PriMock57) and Indian English (Eka). US EMS crews are under-represented. The TTS voices are mostly US/UK neutral. Expect worse WER on strong regional accents, non-native speakers and stressed or shouted speech. **The team recordings are the only real US-EMS test material.** Record a diverse set of readers.
- **Synthetic vs real:** synthetic calls are templated. Real medics clip words, talk over each other and use local slang. Scores on TTS audio are **optimistic for vocabulary coverage** and **pessimistic for prosody**. Report real, synthetic and team sets separately (we do).
- **Noise realism:** noise beds are DEMAND car/bus/street recordings, plus siren clips and synthetic monitor beeps. No real ambulance-cab recordings with the VoiceS3R mic exist yet.
- **Tap sounds:** knocks and snaps come from foley and Freesound recordings mixed digitally. Real knocks on the clip housing couple mechanically into the MEMS mic and will sound different. Re-tune on device recordings.
- **Patient demographics:** scripts vary age and sex but not language. There are no non-English patients and no pediatric-specific vocabulary beyond a few doses.
- **Drug list:** focused on US ALS protocols (Massachusetts protocols plus the NASEMSO list). Regional drugs (e.g. UK paramedic JRCALC drugs) are missing.
- **Fine-tuning risk:** a model tuned on our vocabulary can become over-eager and "hear" drug names in unrelated words. The pipeline already shows this with phonetic matching ("Medic" → morphine). Any fine-tuned model must be checked for **false drug insertions** on non-drug speech (PriMock57 dev) as well as drug WER. That check is part of the ship rule in `eval/REPORT.md`.
