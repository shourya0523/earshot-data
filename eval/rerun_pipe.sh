#!/usr/bin/env bash
cd "$(dirname "$0")/.."
export PATH=/opt/swift/usr/bin:$PATH
TAG=${1:-r4}
(cd /home/user/pipeline/core && swift build -c release 2>&1 | tail -1 && swift test 2>&1 | grep -E "Executed .* tests" | tail -1) > eval/runs/pipe_build_$TAG.log 2>&1
echo "pipeline @ $(git -C /home/user/pipeline rev-parse --short HEAD)" >> eval/runs/pipe_build_$TAG.log
for v in snr10 snr5 snr15; do
  python3 eval/run_pipeline.py --wavs "data/audio/test/tts/c*.$v.wav" --gt data/scripts/test/gt/tts --out eval/runs/pipe_stock_$TAG/test_tts_$v
  python3 eval/score.py --gt data/scripts/test/gt/tts --run eval/runs/pipe_stock_$TAG/test_tts_$v --json eval/results/pipe_stock_${TAG}_test_tts_$v.json > eval/results/pipe_stock_${TAG}_test_tts_$v.txt 2>&1
  echo "PIPE DONE $TAG $v $(date -u +%H:%M)"
done
