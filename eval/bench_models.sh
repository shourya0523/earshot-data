#!/usr/bin/env bash
# Benchmark alternative whisper.cpp models with the pipeline's prompt on: TTS test calls (10 dB) + real test subsets.
cd "$(dirname "$0")/.."
declare -A M=( [emsassist_small]=models/ggml/ggml-whisper-small.en-EMSAssist-v2.bin [emsassist_base]=models/ggml/ggml-whisper-base.en-EMSAssist-v3.bin
               [stock_base]=data/raw/models/ggml-base.en.bin [medical_v1]=data/raw/models/ggml-whisper-medical-v1.bin )
for name in ${@:-emsassist_small emsassist_base stock_base medical_v1}; do
  m=${M[$name]}
  python3 eval/run_asr.py --model $m --prompt pipeline --threads 4 --out eval/runs/$name/test_tts_snr10 --wav data/audio/test/tts/c*.snr10.wav
  for sub in emsctx eka primock medintent; do
    python3 eval/run_asr.py --model $m --prompt pipeline --threads 4 --out eval/runs/$name/real_test_$sub --list eval/lists/real_test_$sub.tsv
  done
  echo "DONE $name"
done
