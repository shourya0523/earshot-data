#!/usr/bin/env bash
# One command: data -> encoder cache -> LoRA train -> export q5 -> benchmark. Usage: train/whisper/run_all.sh [tag rank lr epochs]
cd "$(dirname "$0")/../.."
TAG=${1:-r16}; RANK=${2:-16}; LR=${3:-3e-4}; EP=${4:-2}
[ -f train/whisper/data/train.jsonl ] || python3 train/whisper/prepare_data.py
[ "$(cat train/out/enc_train.done 2>/dev/null)" = "$(wc -l < train/whisper/data/train.jsonl)" ] || python3 train/whisper/train_lora.py --stage cache
python3 train/whisper/train_lora.py --stage train --tag $TAG --rank $RANK --lr $LR --epochs $EP
python3 train/whisper/train_lora.py --stage export --tag $TAG
M=models/whisper-ems-small.en-$TAG-q5.bin
python3 eval/run_asr.py --model $M --prompt pipeline --threads 4 --out eval/runs/ft_$TAG/test_tts_snr10 --wav data/audio/test/tts/c*.snr10.wav
for sub in emsctx eka primock medintent; do python3 eval/run_asr.py --model $M --prompt pipeline --threads 4 --out eval/runs/ft_$TAG/real_test_$sub --list eval/lists/real_test_$sub.tsv; done
echo "FT DONE $TAG $(date -u +%H:%M)"
