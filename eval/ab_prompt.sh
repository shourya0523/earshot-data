#!/usr/bin/env bash
# Stock vs fine-tuned, each with NO prompt and with the pipeline's format-only prompt, then the ship gate.
#   eval/ab_prompt.sh models/whisper-ems-small.en-q5.bin [snr10]
set -e
cd "$(dirname "$0")/.."
FT=${1:?fine-tuned ggml model}; SNR=${2:-snr10}
STOCK=${STOCK:-data/raw/models/ggml-small.en.bin}
GT=data/scripts/test/gt/tts
for m in stock ft; do
  model=$([ $m = stock ] && echo "$STOCK" || echo "$FT")
  for p in noprompt format; do
    extra=$([ $p = noprompt ] && echo "--no-prompt" || echo "")
    out=eval/runs/ab_${m}_${p}/test_tts_$SNR
    python3 eval/run_pipeline.py --wavs "data/audio/test/tts/c*.$SNR.wav" --gt $GT --out $out --asr-model "$model" --extra-args "$extra"
    python3 eval/score.py --gt $GT --run $out --json eval/results/ab_${m}_${p}_test_tts_$SNR.json > eval/results/ab_${m}_${p}_test_tts_$SNR.txt 2>&1
  done
done
python3 eval/decide_ship.py --model "$FT" \
  --stock-noprompt eval/results/ab_stock_noprompt_test_tts_$SNR.json --ft-noprompt eval/results/ab_ft_noprompt_test_tts_$SNR.json \
  --stock-format eval/results/ab_stock_format_test_tts_$SNR.json --ft-format eval/results/ab_ft_format_test_tts_$SNR.json
