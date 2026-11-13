# Data sources (provenance)

Every file fetched is listed with its URL, sha256, size, license and PII flag in `data/manifests/raw_manifest.jsonl`.
Re-fetch it all with `python3 -I data/collect/download_all.py` (about 4 GB). Audio and weights are not in git.
Access was checked on 2026-11-13 from the cloud container. github.com, kaggle.com and freesound.org were blocked, so HF and Zenodo mirrors were used. YouTube audio download is not permitted, so YouTube was used for captions (text) only.

## Real human speech (audio + transcript)
| Source | What | Used | Size | License | PII | How |
|---|---|---|---|---|---|---|
| `saahith/EMSContExt_audio` (HF) | 109 human-read EMS narrative sentences (vitals, meds, assessment) | train 43 / dev 36 / **test 30** | 90 MB, 15.6 min | unknown (no card) | none seen | HF parquet |
| `ekacare/eka-medical-asr-evaluation-dataset`, `en` (HF) | Indian-English clinician speech with drug/dose spans | train 811 / dev 372 / **test 410** | 66 MB, 2 h | MIT | de-identified at source | HF parquet, 4 shards |
| `macabdul9/Primock57` (HF mirror of babylonhealth/primock57) | UK GP mock consultations, doctor/patient utterances ≥ 4 words | train 291 / dev 295 / **test 387** (split by consultation) | 179 MB, 1.6 h | CC-BY-4.0 | none (actors) | HF parquet (test split only) |
| `Shamus/Medical_Speech_Transcription_and_Intent` (HF mirror of Figure Eight) | crowd-read symptom phrases | 300 wavs sampled: 96 / 102 / **102** | 284 MB, 21 min | unknown (Kaggle copy says CC BY-NC-SA 4.0, unverified) | none | per-file HF download |

Splits are made by a hash of the session, consultation or speaker, so no session appears in two splits. The manifest is `data/manifests/real_items.jsonl`.

## Text-only (dictionary, tagger training, phrasing)
| Source | Use | License | PII |
|---|---|---|---|
| `mkieffer/ACI-Bench` (HF) | conversation-to-note phrasing | CC-BY-4.0 | role-play |
| `har1/MTS_Dialogue-Clinical_Note` (MTS-Dialog) | medication / history phrasing | CC-BY-4.0 (upstream) | none |
| `ade-benchmark-corpus/ade_corpus_v2` drug-dosage relation | DRUG + DOSE span labels | unknown | none |
| `tner/bc5cdr` | chemical NER (drug names in context) | BioCreative research use | none |
| YouTube auto-captions (6 of 24 EMS videos; the rest hit the bot check: radio reports, NREMT skills stations, scenarios) | real EMS wording; ASR-error patterns for the dictionary | YouTube ToS; text not redistributed | possible names in ride-along/bodycam: scrubbed before use |

## Noise and tap sounds
| Source | Use | Files | License |
|---|---|---|---|
| FSD50K per-file mirror `Fhrozen/FSD50k` | **Knock** (213), **Finger_snapping** (160), Tap, Siren, Alarm, Traffic, Engine, Idling, Beep | 951 | CC0 / CC-BY (non-commercial clips excluded) |
| Zenodo 3668503 "Knocking Sound Effects With Emotional Intentions" | knock positives | 1 zip | CC-BY-4.0 |
| ESC-50 mirror `TigreGotico/ESC-50` | door knock, siren, clock alarm, engine (eval/augmentation only) | 240 | CC BY-NC 3.0 |
| DEMAND (Zenodo 1227121) TCAR / TBUS / STRAFFIC | ambulance-cab and road noise beds | 3 zips | CC-BY-4.0 |
| `gelang/emergencyvehicle` | ambulance siren clips | 80 | unknown |
| archive.org `202208072004-266724-9809` (Frederick Co. MD fire/EMS) | real dispatch radio, noise and jargon only | 2 mp3 | Public Domain Mark |
| archive.org `scanstockton51` | scanner radio, eval noise only | 1 mp3 | CC BY-NC-ND 3.0 |
| synthetic | patient-monitor QRS beeps and IEC 60601-1-8-style alarm bursts (`render.monitor_beeps`) | generated | n/a |

Every noise and tap file is assigned to a **train** or **test** bank by a stable hash of its filename (`render.bank_of`). Test audio never reuses a tap or noise recording that appears in training audio.

## Synthetic speech
| Item | Detail |
|---|---|
| TTS | Piper 1.8 voices from `rhasspy/piper-voices`: 9 en_US single-speaker voices, 2 en_GB voices, and `libritts_r` (904 speakers; train only). Voice licenses are per MODEL_CARD (mostly CC-BY / CC0 / MIT). |
| Mic simulation | Wearer close and loud. Partner and patient −6 to −9 dB, low-passed, with short room reverb. Radio band-passed 300–3000 Hz and soft-clipped. |
| Scripts | 10 hand-written test calls (`data/scripts/test`), 80 generated train calls and 10 generated dev calls (`data/synth/gen_calls.py`). |

## Not used (and why)
- n2c2 2009/2018 medication corpora and MIMIC need a data use agreement or credentialing.
- PriMock57 full audio on GitHub is blocked here; the HF utterance mirror was used instead.
- `WhissleAI/speech-simulated-medical-exams` and `OUTCOMESAI/*` are gated.
- The Figshare emergency-siren dataset's storage host is blocked (403).
- YouTube audio download is not allowed in this environment.
