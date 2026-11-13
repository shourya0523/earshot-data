# ASR model benchmark (existing open models, no fine-tuning)

All runs use whisper.cpp (beam 5) with the **pipeline's exact initial prompt** (`eval/pipeline_prompt.txt`) and the same EMS-aware text normalisation (`eval/textnorm.py`).
Drug-name WER counts errors on reference tokens that are drug names (dictionary + Eka's labelled drug spans).
False drugs = drug-name tokens in the output that aren't in the reference, per 1,000 reference words (lower is better).
RTF = processing time / audio duration on 4 x86 CPU threads in this container. Ratios are comparable between models; the absolute speed is not the iPad's.

## Test calls, TTS + noise 10 dB (synthetic)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 10 | 15.0% | 38.5% (26) | 85.5% | 78.3% | 0.0 | 0.33 |
| EMSAssist small.en v2 | 244M | 10 | 14.8% | 50.0% (26) | 87.3% | 78.3% | 0.0 | 0.27 |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## EMSContExt (EMS narratives, read) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 30 | 4.4% | 11.1% (9) | 97.8% | 90.5% | 0.0 | 1.08 |
| EMSAssist small.en v2 | 244M | 30 | 3.9% | 11.1% (9) | 97.8% | 95.2% | 0.0 | 0.55 |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## Eka (clinician, Indian English) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 120 | 27.2% | 41.2% (182) | 83.3% | 100.0% | 3.1 | 2.57 |
| EMSAssist small.en v2 | 244M | 120 | 24.6% | 43.4% (182) | 88.3% | 100.0% | 0.0 | 0.88 |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## PriMock57 (GP consults, UK) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 120 | 12.0% | 40.0% (5) | 88.9% | 85.7% | 0.0 | 0.96 |
| EMSAssist small.en v2 | 244M | 120 | 13.8% | 40.0% (5) | 83.3% | 85.7% | 0.0 | 0.81 |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## MedIntent (symptom phrases) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 100 | 3.7% | 0.0% (0) | 100.0% | 100.0% | 0.0 | 1.36 |
| EMSAssist small.en v2 | 244M | (not run) | | | | | | |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## Pooled: all real test sets

| Model | WER (mean of sets) | Drug-name WER (mean of sets with ≥10 drug tokens) |
|---|---|---|
| whisper small.en (stock) | 11.8% | 41.2% |
| EMSAssist small.en v2 | 14.1% | 43.4% |
