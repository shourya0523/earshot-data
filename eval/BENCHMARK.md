# ASR model benchmark (existing open models, no fine-tuning)

All runs use whisper.cpp (beam 5) with the **pipeline's exact initial prompt** (`eval/pipeline_prompt.txt`) and the same EMS-aware text normalisation (`eval/textnorm.py`).
Drug-name WER counts errors on reference tokens that are drug names (dictionary + Eka's labelled drug spans).
False drugs = drug-name tokens in the output that aren't in the reference, per 1,000 reference words (lower is better).
RTF = processing time / audio duration on 4 x86 CPU threads in this container. Ratios are comparable between models; the absolute speed is not the iPad's.

## Test calls, TTS + noise 10 dB (synthetic)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | (not run) | | | | | | |
| EMSAssist small.en v2 | 244M | (not run) | | | | | | |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## EMSContExt (EMS narratives, read) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 30 | 4.4% | 11.1% (9) | 97.8% | 90.5% | 0.0 | 1.08 |
| EMSAssist small.en v2 | 244M | (not run) | | | | | | |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## Eka (clinician, Indian English) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | 90 | 27.1% | 40.3% (149) | 82.5% | 100.0% | 0.0 | 3.04 |
| EMSAssist small.en v2 | 244M | (not run) | | | | | | |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## PriMock57 (GP consults, UK) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | (not run) | | | | | | |
| EMSAssist small.en v2 | 244M | (not run) | | | | | | |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## MedIntent (symptom phrases) (real)

| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |
|---|---|---|---|---|---|---|---|---|
| whisper small.en (stock) | 244M | (not run) | | | | | | |
| EMSAssist small.en v2 | 244M | (not run) | | | | | | |
| EMSAssist base.en v3 | 74M | (not run) | | | | | | |
| whisper base.en (stock) | 74M | (not run) | | | | | | |
| Whisper-Medicalv1 (distil-large-v3) | 756M | (not run) | | | | | | |

## Pooled: all real test sets

| Model | WER (mean of sets) | Drug-name WER (mean of sets with ≥10 drug tokens) |
|---|---|---|
| whisper small.en (stock) | 15.8% | 40.3% |
