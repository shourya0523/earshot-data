#!/usr/bin/env python3
"""Render generated train/dev synthetic calls with the TRAIN half of the tap/noise banks.
Voices: the 11 single-speaker Piper voices + random LibriTTS-R speakers (train only).
Audio -> data/audio/<split>_synth/<id>.snrXX.wav ; GT -> data/scripts/<split>_synth/gt/"""
import json, pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calldsl, render
ROOT = pathlib.Path(__file__).resolve().parents[2]
split = sys.argv[1]
AUD = ROOT / f"data/audio/{split}_synth"; GT = ROOT / f"data/scripts/{split}_synth/gt"; GT.mkdir(parents=True, exist_ok=True)
tb = render.TapBank("train")
rng = random.Random(11 if split == "train" else 12)
base = render.available_voices()
info = []
for i, f in enumerate(sorted((ROOT / f"data/scripts/{split}_synth").glob("*.call"))):
    cid = f.stem
    if (GT / f"{cid}.expected.json").exists() and list(AUD.glob(f"{cid}.snr*.wav")):
        continue   # GT is in git, audio is not: render whenever the audio is missing
    call = calldsl.parse(f.read_text())
    pool = base + [(render.LIBRITTS, rng.randrange(904)) for _ in range(8)]
    snr = rng.choice([0, 5, 10, 15, 20])
    r = render.render(call, AUD, "train", seed=1000 + i, snrs=(snr,), voices=pool, tapbank=tb, write_clean=False)
    for ext in ("transcript.txt", "transcript_speakers.txt", "segments.json", "events.jsonl", "taps.json", "expected.json"):
        (AUD / f"{cid}.{ext}").replace(GT / f"{cid}.{ext}")
    r["voices"] = {k: str(v) for k, v in r["voices"].items()}
    info.append(r); print(cid, round(r["seconds"]), snr, flush=True)
with open(GT / "render_info.jsonl", "a") as fo:
    for r in info: fo.write(json.dumps(r) + "\n")
