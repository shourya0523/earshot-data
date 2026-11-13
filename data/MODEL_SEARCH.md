# Existing open models and datasets (checked 2026-11-13, before any fine-tuning)

The owner asked to look for ready-made models of the right size and for existing datasets before training our own.
I searched the HF API and Zenodo, and read each model card.

## Speech recognition (ASR)
**Finding:** no credible tiny/base/small Whisper fine-tune targets drug names. Most small "medical" Whisper models are trained on the Kaggle symptom-phrase set ("knee pain"), which has almost no drug vocabulary. The Trelis/medical-terms-2025 benchmark puts stock whisper-small at 26.4% medical-term error (large-v3-turbo 22.7%), which matches our 27% drug-name WER. A bigger *stock* model barely helps.

| Candidate | Size | License | Why | Plan |
|---|---|---|---|---|
| `saahith/whisper-small.en-EMSAssist-v2` | small.en 242M | **none stated** | The only EMS-trained Whisper; drop-in for whisper.cpp | **Benchmark** (convert to ggml) |
| `saahith/whisper-base.en-EMSAssist-v3` | base.en 74M | none stated | Low-latency EMS option | **Benchmark** |
| `droytel/whisper-medical-v1-ggml` (Crystalcareai/Whisper-Medicalv1, distil-large-v3) | 756M | MIT | Most-used English medical Whisper; ggml already published | **Benchmark as a ceiling** (slow on iPad) |
| `google/medasr` | 105M Conformer-CTC | HAI-DEF terms, **click-through gate** | Only small medical-native model; Core ML/ONNX ports exist | **Not run:** needs the owner to accept Google's terms. Mirrors exist, but using them would bypass the gate. |
| `yuriyvnv/parakeet-tdt-0.6b-EN-Medical` | 600M | CC-BY-4.0 | MultiMed WER 14.3 | Skip: NeMo, not whisper.cpp |
| Kaggle-symptom fine-tunes (oegbo, Roy9829, Bakhshial, KerNeLGaming…) | small | Apache / none | No drug vocabulary | Skip |

## Tagger (token classification)
**Finding:** no open model covers vitals. Keep rules for VITAL_NAME/VALUE.

| Candidate | Size | Labels | License | Use |
|---|---|---|---|---|
| `genzeonplatform/healthcare-brain-medication-ner` | 108M Bio_ClinicalBERT | DRUG_NAME, STRENGTH, DOSAGE, ROUTE, FREQUENCY, FORM… (F1 0.927, synthetic test) | Apache-2.0 | **Start point** if a tagger is needed. Test zero-shot on lowercase ASR text first. |
| `OpenMed/OpenMed-NER-PharmaDetect-ElectraMed-33M` | 33M | CHEM (BC5CDR F1 0.94) | Apache-2.0 | Tiny alternative; extend the head |
| `d4data/biomedical-ner-all` | 66M DistilBERT | 41 MACCROBAT labels incl. Medication, Dosage, Lab_value | Apache-2.0 | Baseline; ONNX exists |
| `kormilitzin/en_core_med7_trf` | spaCy | DRUG, STRENGTH, DOSAGE, ROUTE, FORM… (F1 0.90) | MIT | Teacher / pseudo-labeller only (no Core ML path) |

## New datasets taken
| Dataset | License | Taken | Use |
|---|---|---|---|
| `Shamus/United-Syn-Med` (mirror of united-we-care) | CC-BY-SA-4.0 | 2 of 33 shards (~1 GB) | Drug-name TTS sentences for ASR training (synthetic) |
| `Xueren/EMSDialogue-Datasets` | **CC-BY-NC-4.0** | all JSON (84 MB): 4.4k synthetic plus **149 real de-identified first-responder dialogues** | Real EMS phrasing for the tagger, scripts and dictionary. NC: research use only. |
| `Xueren/EMS-Knowledge` | MIT | 9 MB | EMS pharmacology vocabulary |
| `xxbubziexx/police-radio-punctuated-dataset` | MIT | 579 MB, 2,900 real radio transmissions | Radio-channel robustness (contains real on-air content; train-only, never redistributed) |
| `Trelis/medical-terms-2025` | MIT | 50 rows | Quick drug-term benchmark |
| `saahith/EMSAssist-2`, `saahith/synthetic_with_val`, `ahmedelsayed/dispatcher-ambulance` | none stated | yes (earlier round) | EMS speech (real read speech, and synthetic) |

**Not taken:**
- Hani89 synthetic speech (53 GB) and afrispeech-200 (11 GB, NC): too big for the disk allowance.
- Zenodo 10864063 CADEC-audio (1.7 GB): maybe later.
- Gated: WhissleAI, OUTCOMESAI, google/medasr.
