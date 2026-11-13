# Phase 2: stock model baseline (before the pipeline was ready)

Model: whisper.cpp `small.en` (ggml f16, `ggerganov/whisper.cpp`), whisper-cli beam 5, 4 CPU threads, initial prompt as noted.
Scoring: `eval/score.py` with EMS-aware normalisation (`eval/textnorm.py`):
- Numbers are mapped to digits and "158/94" to "158 over 94".
- Units are canonical.
- Whisper's `[beep]` / `(siren)` tags are dropped.

Drug-name WER = errors on reference tokens that are drug names (dictionary, plus Eka's labelled drug spans).

## TTS test calls (10 scripted calls, 2–3 min each, Piper voices + noise + knock/snap taps); data-agent seed prompt
| Condition | WER | Drug-name WER (26 tokens) | Number acc | Unit acc | Jargon recall | RTF (4 thr) |
|---|---|---|---|---|---|---|
| clean (digital silence between lines) | 20.1% | 38.5% | 84.3% | 81.8% | 78.3% | 0.73 |
| SNR 15 dB | 11.7% | 30.8% | 86.7% | 100% | 82.6% | 0.27 |
| SNR 10 dB | 12.4% | 26.9% | 89.2% | 100% | 82.6% | 0.53* |
| SNR 5 dB | 13.0% | 26.9% | 88.0% | 100% | 82.6% | 0.30 |

- **"Clean" scores worse than noisy.** On long digital silence, whisper skips or loops chunks; c08 alone has WER 58% there. That's why the pipeline needs VAD or chunking, and why the noisy versions are the real test.
- `*` The RTF was measured while other jobs shared the CPU; 0.27–0.33 is the uncontended figure.

## Same audio, the **pipeline's** initial prompt (`eval/pipeline_prompt.txt`)
| Set | WER | Drug-name WER |
|---|---|---|
| TTS test calls @10 dB | 15.0% | **38.5%** |

The pipeline's prompt is **worse** for drug names than the seed prompt (38.5% vs 26.9%). Reported in `docs/REVIEW.md` (R3-5).

## Real speech, held-out test subsets (pipeline prompt)
| Set (type) | Files | WER | Drug-name WER (tokens) |
|---|---|---|---|
| EMSContExt: human-read EMS narratives | 30 | 4.4% | 11.1% (9) |
| Eka: clinician speech, Indian English | 120 | 27.2% | **41.2% (182)** |
| PriMock57: UK GP mock consultations | 120 | 12.0% | 40.0% (5) |
| MedIntent: crowd-read symptom phrases | 100 | 3.7% | – (0) |

There is **no team-recorded (VoiceS3R) set yet**. It needs the morning recording session (`data/RECORDING.md`).

## Error examples (stock small.en)
- ipratropium → "epitropium" (4/4)
- Keppra → "capra"
- famotidine → "famitating" / "famitidine"
- metoprolol → "metaprolol"
- TXA → "exa"
- Versed → "vs"
- "bagging" → "begging"
- sats → "Satz"
- "under the tongue" → "under the top"
- "Narcan" → "Narcon"

These are collected as ASR variants in `data/dictionary/formulary_additions.json`. The pipeline agent merged them.

## Drug-extraction stand-in (Python, dictionary + regex: `eval/baseline_extract.py`) on stock transcripts, @10 dB, GT tap file
| Field | Precision | Recall |
|---|---|---|
| drug | 0.89 | 0.77 |
| dose | 1.00 | 0.73 |
| unit | 1.00 | 0.73 |
| route | 0.93 | 0.74 |

Unsupported-field rate is 2.8%. Those were stand-in quote bugs, since fixed.

This was the estimate of extraction quality before the Swift pipeline existed; the real pipeline numbers are in `eval/REPORT.md`.
