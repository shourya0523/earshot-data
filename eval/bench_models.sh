#!/usr/bin/env bash
# Benchmark whisper.cpp models with the pipeline's prompt on: TTS test calls (10 dB) + real test subsets. Idempotent (skips done files).
cd "$(dirname "$0")/.."
declare -A M=( [stock_small]=data/raw/models/ggml-small.en.bin [emsassist_small]=models/ggml/ggml-whisper-small.en-EMSAssist-v2.bin [emsassist_base]=models/ggml/ggml-whisper-base.en-EMSAssist-v3.bin
               [stock_base]=data/raw/models/ggml-base.en.bin [medical_v1]=data/raw/models/ggml-whisper-medical-v1.bin )
for name in ${@:-stock_small emsassist_small emsassist_base stock_base medical_v1}; do
  m=${M[$name]}; tdir=eval/runs/$name/test_tts_snr10; [ $name = stock_small ] && tdir=eval/runs/stock_small_pp/test_tts_snr10
  python3 eval/run_asr.py --model $m --prompt pipeline --threads 4 --out $tdir --wav data/audio/test/tts/c*.snr10.wav
  for sub in emsctx eka primock medintent; do
    python3 eval/run_asr.py --model $m --prompt pipeline --threads 4 --out eval/runs/$name/real_test_$sub --list eval/lists/real_test_$sub.tsv
  done
  echo "DONE $name $(date -u +%H:%M)"
done
