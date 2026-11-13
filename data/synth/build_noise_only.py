#!/usr/bin/env python3
"""10 x 60 s noise-only clips (test bank: cab, road, siren, monitor + real dispatch radio chatter), no taps.
Used for false taps per minute. -> data/audio/test/noise_only/n01..n10.wav"""
import pathlib, sys, numpy as np, soundfile as sf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import render
ROOT = pathlib.Path(__file__).resolve().parents[2]; out = ROOT / "data/audio/test/noise_only"; out.mkdir(parents=True, exist_ok=True)
radio = render.load(ROOT / "data/raw/dispatch/stockton_water_rescue.mp3")
for i in range(10):
    rng = np.random.default_rng(500 + i); n = 60 * render.SR
    kinds = [("cab", "road", "siren", "monitor"), ("cab", "monitor"), ("road", "siren"), ("cab", "siren", "monitor"), ("engine", "monitor")][i % 5]
    y = render.noise_bed(n, "test", rng, kinds=kinds)
    y = 0.1 * y / (np.sqrt(np.mean(y ** 2)) + 1e-9)
    if i % 2 == 0 and len(radio) > n:   # radio chatter in half of them
        s = rng.integers(0, len(radio) - n); r = radio[s:s + n]; y += 0.08 * r / (np.sqrt(np.mean(r ** 2)) + 1e-9)
    y = y / max(1.0, np.max(np.abs(y)) / 0.95)
    sf.write(out / f"n{i+1:02d}.wav", y, render.SR, subtype="PCM_16")
print("ok")
