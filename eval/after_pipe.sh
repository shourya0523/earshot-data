#!/usr/bin/env bash
# Wait for the pipeline re-eval, stop the (low-priority) variant miner, run the Phase 5 gate, fine-tune if it fails.
cd "$(dirname "$0")/.."
until grep -q "PIPE DONE vadfixed" eval/runs/after_bench.log 2>/dev/null; do sleep 30; done
sleep 5; pkill -f mine_asr_variants_tts.py
python3 eval/bench_report.py > /dev/null 2>&1
if python3 eval/decide_finetune.py | head -1 | grep -q FAIL; then
  ./train/whisper/run_all.sh r16 16 3e-4 2
  python3 eval/run_pipeline.py --wavs "data/audio/test/tts/c*.snr10.wav" --gt data/scripts/test/gt/tts --out eval/runs/pipe_ft_r16/test_tts_snr10 --asr-model models/whisper-ems-small.en-r16-q5.bin
  python3 eval/score.py --gt data/scripts/test/gt/tts --run eval/runs/pipe_ft_r16/test_tts_snr10 --json eval/results/pipe_ft_r16_test_tts_snr10.json > eval/results/pipe_ft_r16_test_tts_snr10.txt 2>&1
  echo "PIPE FT DONE r16"
  ./train/whisper/run_all.sh r32 32 2e-4 2
fi
python3 data/dictionary/mine_asr_variants_tts.py > eval/runs/asr_variants.log 2>&1
echo "ALL DONE $(date -u +%H:%M)"
