# Shortlist: what we actually use, and the real:synthetic ratio

## Fine-tuning set (`train/whisper/data/`, built by `train/whisper/prepare_data.py`)
| Run | Items | Real items | Synthetic items | Real hours | Synthetic hours | Real share (items / hours) |
|---|---|---|---|---|---|---|
| CPU LoRA (capped; stopped) | 3,328 | 2,698 | 630 | 5.74 | 1.52 | **81% / 79%** |
| Kaggle GPU (`EARSHOT_NO_CAPS=1`) | ≈ 21k | ≈ 20k | 630 | ≈ 45 | 1.5 | **≈ 97% / 97%** (estimate from the prepared pool) |

**Real speech pool (train + reusable dev; test sessions are never used):**
| Source | Train | Dev | Notes |
|---|---|---|---|
| PriMock57 | 1,573 clips, 2.6 h | 1,389, 2.2 h | UK GP mock consultations |
| Eka | 1,467, 3.4 h | 709, 1.7 h | Indian-English clinicians, drug spans |
| AfriSpeech-200, clinical | 5,128, 12.0 h | 971, 2.3 h | African accents, drug-dense, **NC** |
| MultiMed EN | 3,645, 10.9 h | 197, 0.6 h | Medical talks |
| Police/EMS radio | 1,756, 4.3 h | 95, 0.3 h | Real radio channel |
| EMSAssist-2 | 1,196, 2.0 h | 53, 0.1 h | Human-read EMS phrases |
| MedIntent | 328, 0.4 h | 318, 0.4 h | Crowd-read symptom phrases |
| EMSContExt | 43, 0.1 h | 36 | Human-read EMS narratives |

**Synthetic:**
- 80 generated EMS calls (chunked), 250 drug/vitals call-outs, 150 United-Syn-Med drug sentences: all Piper TTS + train-bank noise.
- 60 + 20 external TTS EMS / dispatch utterances.

## Evaluation sets
| Set | Type | Size | Ground truth |
|---|---|---|---|
| 10 scripted test calls | synthetic (TTS + noise + taps) | 23.6 min × 4 SNRs | transcript, events, taps, expected SOAP/IMIST/NEMSIS fields |
| Team recordings via VoiceS3R | real device | **to record** (`data/RECORDING.md`) | aligned by `align_team_recording.py` |
| Real held-out test subsets | real | EMSContExt 30, Eka 120, PriMock57 120, MedIntent 100 clips (33 min) | reference transcripts (+ Eka drug spans) |
| Noise-only | synthetic mix of real noise | 10 × 1 min | no taps (false-tap rate) |
| dev_synth | synthetic | 10 calls | full GT |

Leakage proof: `data/manifests/leakage_report.json` (PASS):
- 0 exact line matches with the test scripts,
- 0 shared 6-grams,
- 0 lines with token Jaccard ≥ 0.6, in train/dev synthetic scripts and drug utterances.

Splits are by session, consultation or speaker; see `data/manifests/real_items.jsonl`.
