#!/usr/bin/env bash
cd "$(dirname "$0")/../.."
until grep -q "^done" data/raw/download_round3.log; do sleep 30; done
python3 data/collect/prepare_extra_human.py --delete-parquet > data/raw/prepare_extra_human.log 2>&1 && touch data/manifests/.extra_human_done
