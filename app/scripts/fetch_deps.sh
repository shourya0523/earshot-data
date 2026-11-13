#!/usr/bin/env bash
# macOS + Xcode 26: builds whisper.xcframework and downloads the stock model.
set -euo pipefail
cd "$(dirname "$0")/.."
WCPP_REV=${WCPP_REV:-5922450fbce1ed9d1648babd0d5ac4520055b436}   # commit tested on Linux
if [ ! -d Frameworks/whisper.xcframework ]; then
  rm -rf /tmp/whisper.cpp && git clone https://github.com/ggml-org/whisper.cpp /tmp/whisper.cpp
  (cd /tmp/whisper.cpp && git checkout "$WCPP_REV" && ./build-xcframework.sh)
  mkdir -p Frameworks && cp -R /tmp/whisper.cpp/build-apple/whisper.xcframework Frameworks/
fi
mkdir -p Models
[ -f Models/ggml-small.en.bin ] || curl -L -o Models/ggml-small.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin
# Simulator is CPU-only and slow with small.en; tiny.en is a fallback the app uses if small is missing.
[ -f Models/ggml-tiny.en.bin ] || curl -L -o Models/ggml-tiny.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin
# Fine-tuned models from the data agent, if present
for f in ../models/whisper-ems-small.en-q5.bin; do [ -f "$f" ] && cp "$f" Models/; done
[ -d ../models/EMSTagger.mlpackage ] && cp -R ../models/EMSTagger.mlpackage ../models/tagger-vocab.txt Models/ || true
command -v xcodegen >/dev/null || brew install xcodegen
xcodegen
echo "Open app/Earshot.xcodeproj, set Signing team, run on the iPad or the Simulator (Replay transport)."
