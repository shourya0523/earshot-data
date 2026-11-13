#!/usr/bin/env python3
"""Reference double-knock / double-snap detector (Python), used to (a) measure tap detection on the test audio and
(b) recommend thresholds for the firmware/app implementation. Not the product detector.

Algorithm (16 kHz mono):
 1. 2 ms hop energy envelope in two bands: low-mid (150-2000 Hz, knock body) and high (2.5-7 kHz, snap crack).
 2. Transient = frame whose broadband energy exceeds the running background (median of previous 1.5 s) by
    `rise_db`, rises within `attack_ms`, and decays by `decay_db` within `decay_ms` (speech doesn't decay that fast).
 3. Group transients: gap between hits in [min_gap_ms, max_gap_ms]. 2 hits = tap (double), 3 = stop (triple),
    1 = ignored. A group must be followed by `quiet_ms` with no further hit.
 4. Class: high-band / low-band energy ratio at the hit > snap_ratio_db -> snap else knock.
  python3 eval/tap_detector.py --wav a.wav [--params p.json] -> {"taps":[{clip_ms,source,kind}],"duration_s"}"""
import argparse, json, pathlib
import numpy as np, soundfile as sf
from scipy import signal

DEFAULT = dict(rise_db=14.0, attack_ms=12, decay_db=10.0, decay_ms=70, min_gap_ms=110, max_gap_ms=550, quiet_ms=500, snap_ratio_db=0.0, refractory_ms=90)
SR = 16000


def band_env(y, lo, hi, hop):
    b, a = signal.butter(4, [lo / (SR / 2), min(hi, SR / 2 - 100) / (SR / 2)], "band")
    z = signal.lfilter(b, a, y)
    n = len(z) // hop
    return np.sqrt(np.mean(z[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)


def features(y):
    hop = int(0.002 * SR)
    lo = band_env(y, 150, 2000, hop); hi = band_env(y, 2500, 7000, hop)
    e = 20 * np.log10(lo + hi + 1e-9)
    win = int(1.5 / 0.002)
    bg = np.empty_like(e); step = 25
    for i in range(0, len(e), step):
        seg = e[max(0, i - win): i] if i > 10 else e[: win]
        bg[i: i + step] = np.median(seg) if len(seg) else e[i]
    # local context: max energy in the 60-200 ms after the hit (speech keeps going, a knock doesn't)
    return dict(lo=lo, hi=hi, e=e, bg=bg)


def detect(y, p=None, feats=None):
    p = {**DEFAULT, **(p or {})}
    F = feats or features(y)
    lo, hi, e, bg = F["lo"], F["hi"], F["e"], F["bg"]
    hits = []
    a_fr = max(1, int(p["attack_ms"] / 2)); d_fr = max(1, int(p["decay_ms"] / 2)); ref = int(p["refractory_ms"] / 2)
    i = a_fr
    while i < len(e) - d_fr:
        if e[i] - bg[i] >= p["rise_db"] and e[i] >= e[i - a_fr] + p["rise_db"] * 0.6:
            j = i + int(np.argmax(e[i: i + 5])); peak = e[j]
            tail = e[j + d_fr: j + d_fr + int(p.get("tail_ms", 120) / 2)]
            if peak - np.min(e[j: j + d_fr]) >= p["decay_db"] and (len(tail) == 0 or peak - np.max(tail) >= p.get("tail_db", 6.0)):
                ratio = 20 * np.log10(hi[j] + 1e-9) - 20 * np.log10(lo[j] + 1e-9)
                hits.append((j * 2, ratio)); i = j + ref; continue
        i += 1
    taps = []; k = 0
    while k < len(hits):
        g = [hits[k]]
        while k + 1 < len(hits) and p["min_gap_ms"] <= hits[k + 1][0] - g[-1][0] <= p["max_gap_ms"] and len(g) < 4:
            k += 1; g.append(hits[k])
        nxt = hits[k + 1][0] if k + 1 < len(hits) else 1e12
        prev = hits[k - len(g)][0] if k - len(g) >= 0 else -1e12
        if (nxt - g[-1][0] >= p["quiet_ms"] and g[0][0] - prev >= p["quiet_ms"]) and len(g) <= 3:
            src = "snap" if np.mean([r for _, r in g]) > p["snap_ratio_db"] else "knock"
            if len(g) == 2:
                taps.append(dict(clip_ms=int(g[0][0]), source=src, kind="double"))
            elif len(g) >= 3:
                taps.append(dict(clip_ms=int(g[0][0]), source=src, kind="triple_stop"))
        k += 1
    return taps


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--wav", nargs="+"); ap.add_argument("--out"); ap.add_argument("--params")
    a = ap.parse_args()
    p = json.loads(pathlib.Path(a.params).read_text()) if a.params else None
    for w in a.wav:
        y, sr = sf.read(w, dtype="float32")
        if y.ndim > 1: y = y.mean(1)
        if sr != SR: y = signal.resample_poly(y, SR, sr)
        t = detect(y, p)
        res = dict(taps=[x for x in t if x["kind"] == "double"], stops=[x for x in t if x["kind"] != "double"], duration_s=len(y) / SR)
        if a.out:
            uid = pathlib.Path(w).name.split(".")[0]
            pathlib.Path(a.out).mkdir(parents=True, exist_ok=True)
            (pathlib.Path(a.out) / f"{uid}.taps_detected.json").write_text(json.dumps(res))
        else:
            print(w, res)


if __name__ == "__main__":
    main()
