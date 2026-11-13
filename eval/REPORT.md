# Phase 4 report: Earshot pipeline on our test data

## Verdicts (one line per area)

**Pipeline under test:** `earshot-eval` (branch `overnight` @ da52ea6), stock whisper.cpp small.en (greedy), the ground-truth tap file, and the 10 scripted test calls (TTS + noise + taps).

| Area | Verdict |
|---|---|
| **Transcription** | **FAIL.** Drug-name WER is 35–38% at every SNR (threshold 15%); on real clinician speech (Eka) it is 41%. Overall WER is 17.6% / 23.3% / 32.2% at 15 / 10 / 5 dB; greedy decoding costs ~8 points versus beam 5. **Whisper fine-tune triggered** (Kaggle GPU run in progress). |
| **Extraction** | **PASS on correct transcripts; ASR-limited on audio.** On GT transcripts (pipeline agent, round 2): drug 0.93, dose 0.93, unit 0.95, route 0.92. On audio @10 dB: drug P 0.95 / R 0.86; dose, unit and route recall 0.79–0.82; RR recall 0.29 (rule bug R3-3). No tagger needed: extraction isn't at fault when the transcript is right. |
| **Receipts** | **FAIL (pipeline bug).** The unsupported-field rate is 3.7% @10 dB (must be 0): 5 drug values with no drug in the quote (`docs/REVIEW.md` R3-1). Reported; not a fine-tune problem. |
| **Taps** | **Tune thresholds.** Reference detector: knock recall 0.94, snap 0.82 (< 0.9), **0 false taps in 10 min of noise**. Snap needs a lower onset in the high band (recommended values in REVIEW). Tap labelling in the pipeline is 0.64, caused by early segment start times (R3-2). |
| **Time** | **Needs fix.** Timestamp error median 0 s, but p90 5.0 s @10 dB. The cause is the same as R3-2 (segment starts include preceding noise). |
| **Outputs** | **PASS with gaps.** NEMSIS XML **valid against the v3.5.1 XSD, 10/10**. **0 diagnosis leaks.** Key-field match SOAP/CHART/IMIST 82%, NEMSIS 75% @10 dB; misses track the ASR misses. |
| **Speed** | **OK on x86; check on iPad.** RTF 0.40–0.43 uncontended (4 threads, small.en greedy). ASR is >99% of the time; cleanup, extraction, merge and render are < 0.2 s per call. |

## Thresholds and actions
| Fails if | Measured | Action |
|---|---|---|
| Drug-name WER > 15% or WER > 20% (real + team) | real: drug WER 41.2% (Eka, 182 tokens), mean WER 11.8%; team set not recorded yet | **Fine-tune Whisper small.en.** First checked the existing open models (`eval/BENCHMARK.md`): none beats stock. Then a CPU LoRA run, stopped by the owner in favour of a **Kaggle GPU full fine-tune** (`train/whisper/kaggle_finetune.ipynb`). |
| Drug F1 < 0.90 or dose/unit/route recall < 0.85 *with a correct transcript* | GT transcripts: 0.93 / 0.93 / 0.95 / 0.92 | No tagger. |
| Unsupported-field rate > 0 | 3.7% | Pipeline bug: REVIEW R3-1. |
| Tap FP > 1 per 10 min of noise, or recall < 0.9 | FP 0/10 min; knock 0.94, snap 0.82 | Threshold recommendation in REVIEW. |

## Detail: pipeline on the TTS test calls (10 calls, 23.6 min audio)
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
