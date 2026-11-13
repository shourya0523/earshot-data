# Phase 4 report: Earshot pipeline on our test data

## Verdicts (one line per area)

**Pipeline under test:** `earshot-eval` (branch `overnight`), stock whisper.cpp small.en, the ground-truth tap file, and the 10 scripted test calls (TTS + noise + taps).
- **Latest: @ 5f434ae** (round-3 fixes: beam 5 + fallback, seed prompt, token timestamps).
- Earlier rows: @ da52ea6 (greedy).

| Area | Verdict |
|---|---|
| **Transcription** | **FAIL.** Drug-name WER is still 31–38% (threshold 15%), and 41% on real clinician speech (Eka). Overall WER @ 5f434ae is **12.5% / 14.7% / 20.8%** at 15 / 10 / 5 dB (was 17.6 / 23.3 / 32.2 with greedy). **Whisper fine-tune triggered** (Kaggle GPU run in progress). |
| **Extraction** | **PASS on correct transcripts; ASR-limited on audio.** On GT transcripts (pipeline agent, round 2): drug 0.93, dose 0.93, unit 0.95, route 0.92. On audio @10 dB: drug P 0.95 / R 0.86; dose, unit and route recall 0.79–0.82; RR recall 0.29 (rule bug R3-3). No tagger needed: extraction isn't at fault when the transcript is right. |
| **Receipts** | **PASS @ 5f434ae.** Unsupported-field rate is **0** at all three SNRs. It was 3.7% @ da52ea6: 5 invented drug values, fixed by the pipeline agent (R3-1). |
| **Taps** | **Tune thresholds.** Reference detector: knock recall 0.94, snap 0.82 (< 0.9), **0 false taps in 10 min of noise**. Snap needs a lower onset in the high band (recommended values in REVIEW). Pipeline tap labelling is **0.70–0.72** @ 5f434ae (0.64 before); the remaining misses follow ASR misses. |
| **Time** | **Improving.** Timestamp error median 0 s, p90 **4.2–4.9 s** @ 5f434ae (was 5.0–6.7 s). |
| **Outputs** | **PASS with gaps.** NEMSIS XML **valid against the v3.5.1 XSD, 10/10**. **0 diagnosis leaks.** Key-field match SOAP/CHART/IMIST 82%, NEMSIS 75% @10 dB; misses track the ASR misses. |
| **Speed** | **OK on x86; check on iPad.** RTF ~0.4 greedy and ~0.7 beam 5 (4 x86 threads; the beam runs shared the CPU). ASR is > 99% of the time; cleanup, extraction, merge and render are < 0.2 s per call. |

## Thresholds and actions
| Fails if | Measured | Action |
|---|---|---|
| Drug-name WER > 15% or WER > 20% (real + team) | real: drug WER 41.2% (Eka, 182 tokens), mean WER 11.8%; team set not recorded yet | **Fine-tune Whisper small.en.** First checked the existing open models (`eval/BENCHMARK.md`): none beats stock. Then a CPU LoRA run, stopped by the owner in favour of a **Kaggle GPU full fine-tune** (`train/whisper/kaggle_finetune.ipynb`). |
| Drug F1 < 0.90 or dose/unit/route recall < 0.85 *with a correct transcript* | GT transcripts: 0.93 / 0.93 / 0.95 / 0.92 | No tagger. |
| Unsupported-field rate > 0 | 3.7% | Pipeline bug: REVIEW R3-1. |
| Tap FP > 1 per 10 min of noise, or recall < 0.9 | FP 0/10 min; knock 0.94, snap 0.82 | Threshold recommendation in REVIEW. |

## Detail @ 5f434ae (beam 5, seed prompt, token timestamps)
| SNR | WER | drug WER | drug P/R | dose R | unit R | route R | BP R | HR R | RR R | SpO2 R | BGL R | unsupported | tap labelling | ts err p90 | key-field SOAP/NEMSIS | NEMSIS valid | leaks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15 dB | 12.5% | 30.8% | .90/.86 | .82 | .82 | .74 | .56 | .75 | .43 | .50 | .57 | 0 | .72 | 4.2 s | 73% / 69% | 10/10 | 0 |
| 10 dB | 14.7% | 30.8% | .94/.77 | .73 | .64 | .68 | .75 | .75 | .43 | .50 | .57 | 0 | .70 | 4.9 s | 76% / 71% | 10/10 | 0 |
| 5 dB | 20.8% | 38.5% | .95/.82 | .77 | .73 | .63 | .69 | .56 | .29 | .57 | .71 | 0 | .72 | 4.9 s | 74% / 70% | 10/10 | 0 |

The recall regressions on SpO2 and some meds versus da52ea6 come from ASR output changes ("sat" → "set", `♪♪♪` hallucinations, "Now we're breather"). They are reported as R4-1…R4-3 with fixes.

## Detail @ da52ea6 (greedy): pipeline on the TTS test calls (10 calls, 23.6 min audio)
| SNR | WER | drug WER | drug P/R | dose R | unit R | route R | BP R | HR R | RR R | SpO2 R | BGL R | unsupported | tap labelling | ts err p90 | key-field SOAP/NEMSIS | NEMSIS valid | leaks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15 dB | 17.6% | 34.6% | .95/.82 | .77 | .64 | .68 | .62 | .69 | .57 | .64 | .71 | 3.9% | .62 | 5.0 s | 74% / 70% | 10/10 | 0 |
| 10 dB | 23.3% | 34.6% | .95/.86 | .82 | .82 | .79 | .69 | .81 | .29 | .93 | .71 | 3.7% | .64 | 5.0 s | 82% / 75% | 10/10 | 0 |
| 5 dB | 32.2% | 38.5% | .95/.82 | .77 | .73 | .68 | .62 | .62 | .43 | .64 | .71 | 4.1% | .60 | 6.7 s | 75% / 68% | 10/10 | 0 |
| 10 dB, VAD off | 23.7% | 38.5% | .95/.82 | | | | | | | | | 2.0% | | 8.2 s | | | |

Precision for every vital is 0.91–1.00. Misses are recall: what ASR didn't hear correctly isn't extracted, and nothing is invented except the 5 drug values in R3-1.

## Breakdown by data type
| Type | Status |
|---|---|
| Synthetic (TTS + noise + taps) | Full pipeline results above. |
| Real (held-out subsets of EMSContExt / Eka / PriMock57 / MedIntent) | ASR scored (`eval/BENCHMARK.md`). No event ground truth exists for these sources, so extraction is only scored on synthetic and team data. |
| Team-recorded (VoiceS3R) | **Not recorded yet.** Kit in `data/RECORDING.md`; run `eval/run_pipeline.py` on `data/audio/test/team` after recording. |
| Stock vs fine-tuned | Stock above. Fine-tuned: pending the Kaggle run, which is evaluated with the same commands and `--asr-model`. |

## Reproduce
```bash
python3 eval/run_pipeline.py --wavs 'data/audio/test/tts/c*.snr10.wav' --gt data/scripts/test/gt/tts --out eval/runs/pipe_stock/test_tts_snr10
python3 eval/score.py --gt data/scripts/test/gt/tts --run eval/runs/pipe_stock/test_tts_snr10
python3 eval/tap_detector.py --params eval/results/tap_params.json --wav data/audio/test/noise_only/*.wav --out eval/runs/taps_ref/noise_only
```
