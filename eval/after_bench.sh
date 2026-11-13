#!/usr/bin/env bash
# Chain: wait for model benchmark -> rebuild pipeline -> pipeline eval on test calls -> score -> resume ASR-variant mining.
cd "$(dirname "$0")/.."
while pgrep -f bench_models.sh >/dev/null; do sleep 30; done
python3 eval/bench_report.py > /dev/null 2>&1
export PATH=/opt/swift/usr/bin:$PATH
(cd /home/user/pipeline/core && swift build -c release 2>&1 | tail -3 && swift test 2>&1 | grep -E "Executed .* tests" | tail -1) > eval/runs/pipe_build.log 2>&1
echo "pipeline @ $(git -C /home/user/pipeline rev-parse --short HEAD)" >> eval/runs/pipe_build.log
for v in snr10 snr5 snr15; do
  python3 eval/run_pipeline.py --wavs "data/audio/test/tts/c*.$v.wav" --gt data/scripts/test/gt/tts --out eval/runs/pipe_stock/test_tts_$v
  python3 eval/score.py --gt data/scripts/test/gt/tts --run eval/runs/pipe_stock/test_tts_$v --json eval/results/pipe_stock_test_tts_$v.json > eval/results/pipe_stock_test_tts_$v.txt 2>&1
  echo "PIPE DONE $v $(date -u +%H:%M)"
done
echo '{"vad":{"mode":"fixed"}}' > eval/runs/vad_fixed.json
python3 eval/run_pipeline.py --wavs "data/audio/test/tts/c*.snr10.wav" --gt data/scripts/test/gt/tts --out eval/runs/pipe_stock_vadfixed/test_tts_snr10 --extra-args "--config eval/runs/vad_fixed.json"
python3 eval/score.py --gt data/scripts/test/gt/tts --run eval/runs/pipe_stock_vadfixed/test_tts_snr10 --json eval/results/pipe_stock_vadfixed_test_tts_snr10.json > eval/results/pipe_stock_vadfixed_test_tts_snr10.txt 2>&1
echo "PIPE DONE vadfixed $(date -u +%H:%M)"
python3 data/dictionary/mine_asr_variants_tts.py > eval/runs/asr_variants.log 2>&1
echo "VARIANTS DONE $(date -u +%H:%M)"
