#!/usr/bin/env python3
"""Data-driven ASR variants: speak every drug name (pipeline formulary generics/brands/slang + home meds) in a medic
carrier phrase with 2 Piper voices at 10 dB SNR (train noise bank), transcribe with stock whisper.cpp small.en using the
pipeline's initial prompt, align, and record what whisper wrote for each name.
  python3 data/dictionary/mine_asr_variants_tts.py --formulary /home/user/pipeline/shared/formulary.json
Output: data/dictionary/asr_variants_tts.json  {generic: {name_said: {hyp_variant: count}}} + per-name accuracy."""
import argparse, collections, json, pathlib, random, subprocess, sys
import numpy as np, soundfile as sf, jiwer
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data/synth")); sys.path.insert(0, str(ROOT / "eval"))
import render, textnorm as tn

CARRIERS = ["Giving {n}, four milligrams.", "She takes {n} at home.", "Okay, {n} is in.", "He's on {n} and that's it.", "Pushing {n} now."]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--formulary", default="/home/user/pipeline/shared/formulary.json")
    a = ap.parse_args()
    F = json.loads(pathlib.Path(a.formulary).read_text())
    names = []
    for d in F["drugs"]:
        for n in [d["generic"], *d.get("brands", [])[:3], *d.get("slang", [])[:3]]:
            if n and len(n) > 2: names.append((d["generic"], n))
    hm = json.loads((ROOT / "data/dictionary/home_meds.json").read_text())
    for o in hm["items"]:
        names.append((o["generic"], o["name"]))
    for m in hm.get("seed_added", []):
        names.append((m.lower(), m))
    seen = set(); names = [x for x in names if not (x[1].lower() in seen or seen.add(x[1].lower()))]
    rng = random.Random(3); nrng = np.random.default_rng(3)
    voices = [("en_US-ryan-medium", None), ("en_US-amy-medium", None), ("en_US-joe-medium", None), ("en_US-kristin-medium", None)]
    work = ROOT / "eval/runs/asr_variants"; work.mkdir(parents=True, exist_ok=True)
    utts = []
    for i, (g, n) in enumerate(names):
        for vi in range(2):
            v = voices[(i * 2 + vi) % len(voices)]
            utts.append((g, n, rng.choice(CARRIERS).format(n=n), v))
    # pack into ~25 s files
    files = []; cur = []; cur_len = 0; k = 0
    def flush():
        nonlocal cur, cur_len, k
        if not cur: return
        y = np.concatenate([np.concatenate([u[4], np.zeros(int(0.8 * render.SR), np.float32)]) for u in cur])
        bed = render.noise_bed(len(y), "train", nrng, kinds=("cab", "monitor"))
        y = y + render.mix_snr(y, bed, 10); y = y / max(1.0, np.max(np.abs(y)) / 0.98)
        p = work / f"v{k:04d}.wav"; sf.write(p, y, render.SR, subtype="PCM_16")
        files.append((p, [u[:3] for u in cur])); cur = []; cur_len = 0; k += 1
    for g, n, s, v in utts:
        y = render.tts(s, v[0], v[1]); y = render.mic_sim(y, "M1", nrng)
        cur.append((g, n, s, v, y)); cur_len += len(y) / render.SR + 0.8
        if cur_len > 24: flush()
    flush()
    prompt = (ROOT / "eval/pipeline_prompt.txt").read_text().strip()
    res = collections.defaultdict(lambda: collections.defaultdict(collections.Counter)); ok = collections.Counter(); tot = collections.Counter()
    for p, items in files:
        subprocess.run([str(ROOT / ".tools/whisper-cli"), "-m", str(ROOT / "data/raw/models/ggml-small.en.bin"), "-f", str(p), "-t", "4", "-nt", "-np",
                        "--prompt", prompt, "-otxt", "-of", str(p.with_suffix(""))], capture_output=True)
        hyp = tn.normalize(p.with_suffix(".txt").read_text())
        ref_words, owner = [], []
        for j, (g, n, s) in enumerate(items):
            pre, _, post = s.partition("{n}") if False else (None, None, None)
            ws = tn.normalize(s).split(); nw = tn.normalize(n).split()
            # locate the name inside the carrier
            for q in range(len(ws) - len(nw) + 1):
                if ws[q:q + len(nw)] == nw: break
            for q2, w in enumerate(ws):
                ref_words.append(w); owner.append((j, q <= q2 < q + len(nw)))
        h = hyp.split()
        al = jiwer.process_words(" ".join(ref_words), hyp).alignments[0]
        hyp_of = collections.defaultdict(list); wrong = collections.defaultdict(bool)
        for ch in al:
            for t in range(ch.ref_start_idx, ch.ref_end_idx):
                j, is_name = owner[t]
                if not is_name: continue
                if ch.type == "equal":
                    hyp_of[j].append(h[ch.hyp_start_idx + (t - ch.ref_start_idx)])
                elif ch.type == "substitute":
                    hyp_of[j].append(h[ch.hyp_start_idx + (t - ch.ref_start_idx)]); wrong[j] = True
                elif ch.type == "delete":
                    wrong[j] = True
            if ch.type == "insert" and ch.hyp_start_idx > 0:
                pass
        for j, (g, n, s) in enumerate(items):
            heard = " ".join(hyp_of.get(j, [])) or "∅"
            tot[n] += 1
            if not wrong[j] and heard == tn.normalize(n): ok[n] += 1
            else: res[g][n][heard] += 1
    out = dict(note="What stock whisper.cpp small.en (pipeline prompt, 10 dB cab+monitor noise, 2 Piper voices) wrote for each drug name. Use as asr_variants (review junk like '∅').",
               per_name_accuracy={n: round(ok[n] / tot[n], 2) for n in sorted(tot)},
               overall_name_accuracy=round(sum(ok.values()) / max(1, sum(tot.values())), 3),
               variants={g: {n: dict(c) for n, c in d.items()} for g, d in sorted(res.items())})
    (ROOT / "data/dictionary/asr_variants_tts.json").write_text(json.dumps(out, indent=1))
    print("names", len(tot), "utterances", sum(tot.values()), "accuracy", out["overall_name_accuracy"])


if __name__ == "__main__":
    main()
