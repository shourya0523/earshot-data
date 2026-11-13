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
| EMSAssist base.en v3 | 74M | 10 | 19.9% | 61.5% (26) | 84.9% | 66.7% | 0.0 | 0.14 |
| whisper base.en (stock) | 74M | 10 | 19.7% | 38.5% (26) | 84.3% | 69.6% | 0.0 | 0.11 |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## EMSContExt (EMS narratives, read) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 30 | 4.4% | 11.1% (9) | 97.8% | 90.5% | 0.0 | 1.08 |
| EMSAssist small.en v2 | 244M | 30 | 3.9% | 11.1% (9) | 97.8% | 95.2% | 0.0 | 0.55 |
| EMSAssist base.en v3 | 74M | 30 | 5.9% | 11.1% (9) | 97.8% | 81.0% | 0.0 | 0.24 |
| whisper base.en (stock) | 74M | 30 | 5.2% | 0.0% (9) | 95.6% | 100.0% | 0.0 | 0.19 |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## Eka (clinician, Indian English) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 120 | 27.2% | 41.2% (182) | 83.3% | 100.0% | 3.1 | 2.57 |
| EMSAssist small.en v2 | 244M | 120 | 24.6% | 43.4% (182) | 88.3% | 100.0% | 0.0 | 0.88 |
| EMSAssist base.en v3 | 74M | 120 | 37.6% | 53.8% (182) | 75.0% | 100.0% | 3.1 | 0.36 |
| whisper base.en (stock) | 74M | 120 | 36.7% | 50.0% (182) | 80.0% | 100.0% | 0.0 | 0.30 |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## PriMock57 (GP consults, UK) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 120 | 12.0% | 40.0% (5) | 88.9% | 85.7% | 0.0 | 0.96 |
| EMSAssist small.en v2 | 244M | 120 | 13.8% | 40.0% (5) | 83.3% | 85.7% | 0.0 | 0.81 |
| EMSAssist base.en v3 | 74M | 120 | 18.0% | 40.0% (5) | 94.4% | 85.7% | 0.0 | 0.30 |
| whisper base.en (stock) | 74M | 120 | 14.6% | 40.0% (5) | 88.9% | 85.7% | 0.0 | 0.28 |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## MedIntent (symptom phrases) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 100 | 3.7% | 0.0% (0) | 100.0% | 100.0% | 0.0 | 1.36 |
| EMSAssist small.en v2 | 244M | 100 | 4.7% | 0.0% (0) | 100.0% | 100.0% | 0.0 | 1.10 |
| EMSAssist base.en v3 | 74M | 100 | 6.2% | 0.0% (0) | 100.0% | 57.1% | 0.0 | 0.40 |
| whisper base.en (stock) | 74M | 100 | 5.0% | 0.0% (0) | 100.0% | 85.7% | 0.0 | 0.35 |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## Pooled: all real test sets

| Model | WER (mean of sets) | Drug-name WER (mean of sets with ≥10 drug tokens) |
|---|---|---|
| whisper small.en (stock) | 11.8% | 41.2% |
| EMSAssist small.en v2 | 11.8% | 43.4% |
| EMSAssist base.en v3 | 16.9% | 53.8% |
| whisper base.en (stock) | 15.4% | 50.0% |
