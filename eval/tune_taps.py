#!/usr/bin/env python3
"""Grid-search tap_detector parameters on TRAIN synthetic calls + train-bank noise; report on test separately.
Objective: maximise recall subject to false taps <= 1 per 10 min of audio (product threshold)."""
import itertools, json, pathlib, random, sys
import numpy as np, soundfile as sf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import tap_detector as td
ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_set(wavs, gtdir):
    out = []
    for w in wavs:
        y, _ = sf.read(w, dtype="float32")
        gid = pathlib.Path(w).name.split(".")[0]
        g = json.loads((gtdir / f"{gid}.taps.json").read_text())
        gt = [t for t in g["taps"] if t["source"] in ("knock", "snap")]
        out.append((td.features(y), gt, len(y) / 16000))
    return out


def evaluate(S, p, tol=300):
    tp = fp = n = 0; secs = 0
    for F, gt, d in S:
        det = [t for t in td.detect(None, p, F) if t["kind"] == "double"]
        used = set()
        for g in gt:
            for j, t in enumerate(det):
                if j not in used and abs(t["clip_ms"] - g["clip_ms"]) <= tol:
                    used.add(j); tp += 1; break
        fp += len(det) - len(used); n += len(gt); secs += d
    return dict(recall=tp / max(1, n), fp_per_10min=fp / (secs / 600), tp=tp, n=n, fp=fp)


if __name__ == "__main__":
    tr = sorted((ROOT / "data/audio/train_synth").glob("*.wav")); random.Random(0).shuffle(tr)
    S = load_set(tr[:24], ROOT / "data/scripts/train_synth/gt")
    grid = dict(rise_db=[12, 16, 20, 24], decay_db=[8, 12, 16], decay_ms=[40, 60, 80], tail_db=[4, 8, 12], tail_ms=[120, 200])
    best = None; rows = []
    for vals in itertools.product(*grid.values()):
        p = dict(zip(grid.keys(), vals)); r = evaluate(S, p); rows.append((p, r))
        ok = r["fp_per_10min"] <= 1.0
        key = (ok, r["recall"] if ok else -r["fp_per_10min"])
        if best is None or key > best[0]:
            best = (key, p, r)
    print("best", best[1], best[2])
    (ROOT / "eval/results").mkdir(exist_ok=True)
    (ROOT / "eval/results/tap_params.json").write_text(json.dumps({**td.DEFAULT, **best[1]}, indent=1))
    rows.sort(key=lambda x: (-x[1]["recall"], x[1]["fp_per_10min"]))
    (ROOT / "eval/results/tap_grid.json").write_text(json.dumps(rows[:60], indent=0))
