#!/usr/bin/env python3
"""Build the Whisper fine-tuning set (train/dev manifests) and render extra drug-dense synthetic utterances.
  python3 train/whisper/prepare_data.py
Train mix (by item count, majority real):
  real  : EMSContExt train, Eka train, PriMock57 train, MedIntent train   (real_items.jsonl split == train)
  synth : chunks (<= 28 s) of the 80 generated train calls + N short drug/vitals utterances (TTS + train-bank noise)
Never uses test items or test scripts; synthetic text is checked against the test scripts (same rule as gen_calls).
Output: train/whisper/data/{train,dev}.jsonl  rows: {id, wav, start_s, end_s, text, type, subset}"""
import json, pathlib, random, sys
import numpy as np, soundfile as sf
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data/synth")); sys.path.insert(0, str(ROOT / "eval"))
import calldsl, render, gen_calls, textnorm as tn

OUT = ROOT / "train/whisper/data"; OUT.mkdir(parents=True, exist_ok=True)
N_DRUG_UTT = 250
# per-subset caps (items) for the training mix; real subsets are drug/EMS-focused first
# CPU run: ~3k items, >= 75% real (owner: more human speech). The Kaggle GPU notebook uses no caps on real subsets.
CAPS = dict(emsctx=999, emsassist=600, eka=550, primock=350, medintent=120, afrispeech=500, multimed=250, radio=250,
            train_synth_call=150, drug_utt=250, united_syn_med=150, ems_synth_ext=60, dispatch_synth_ext=20)
import os
if os.environ.get("EARSHOT_NO_CAPS"):
    CAPS = {k: (10**9 if k in ("emsctx", "emsassist", "eka", "primock", "medintent", "afrispeech", "multimed", "radio") else v) for k, v in CAPS.items()}
rng = random.Random(42)


def call_chunks(split):
    rows = []
    gtd = ROOT / f"data/scripts/{split}_synth/gt"
    for segp in sorted(gtd.glob("*.segments.json")):
        cid = segp.name.split(".")[0]
        wav = next((ROOT / f"data/audio/{split}_synth").glob(f"{cid}.snr*.wav"), None)
        if wav is None: continue
        segs = json.loads(segp.read_text()); cur = []
        def flush():
            if cur:
                rows.append(dict(id=f"{cid}_{len(rows)}", wav=str(wav.relative_to(ROOT)), start_s=max(0, cur[0]["start_ms"] / 1000 - 0.3),
                                 end_s=cur[-1]["end_ms"] / 1000 + 0.3, text=" ".join(s["text"] for s in cur), type="synthetic", subset=f"{split}_synth_call"))
        for s in segs:
            if cur and (s["end_ms"] - cur[0]["start_ms"]) / 1000 > 27:
                flush(); cur = []
            cur.append(s)
        flush()
    return rows


def drug_utterances(n):
    """Short medic call-outs dense in drug names/doses/routes/vitals. Text from gen_calls phrasings."""
    test_lines = [tn.normalize(it["text"]) for p in sorted((ROOT / "data/scripts/test").glob("*.call"))
                  for it in calldsl.parse(p.read_text())["items"] if it["kind"] == "speech"]
    test_tok = [set(l.split()) for l in test_lines]; test_set = set(test_lines)
    tb = render.TapBank("train"); voices = render.available_voices() + [(render.LIBRITTS, i) for i in range(0, 900, 37)]
    meds = [m for sc in gen_calls.SCEN.values() for m in sc["meds"] if m[0] in gen_calls.DRUG]
    allnames = [d["name"] for d in gen_calls.F["drugs"]]
    out = []; d = ROOT / "data/audio/train_synth_utt"; d.mkdir(parents=True, exist_ok=True)
    nrng = np.random.default_rng(7)
    k = 0
    while len(out) < n:
        k += 1
        if rng.random() < 0.6:
            drug, dose, unit, route = rng.choice(meds)
        else:   # any formulary drug with a typical dose
            x = gen_calls.DRUG[rng.choice(allnames)]
            drug, dose = x["name"], rng.choice(x["typical_doses"] or ["1"]); unit = x["units"][0]; route = rng.choice(x["routes"] or [""])
        s, _ = gen_calls.say_med(drug, dose, unit, route, rng)
        if rng.random() < 0.5:
            nm = rng.choice(["bp", "hr", "rr", "spo2", "bgl", "gcs", "etco2"])
            ph, _ = gen_calls.say_vital(nm, gen_calls.vit(nm, rng, rng.random() < .5), rng)
            s = f"{s}. {ph[0].upper() + ph[1:]}" if rng.random() < .5 else f"{ph[0].upper() + ph[1:]}. {s}"
        s = s[0].upper() + s[1:] + "."
        nn = tn.normalize(s); st = set(nn.split())
        if nn in test_set or (len(st) >= 5 and max(len(st & t) / len(st | t) for t in test_tok) >= 0.6):
            continue
        v, sid = voices[rng.randrange(len(voices))]
        y = render.tts(s, v, sid, rng.uniform(0.85, 1.1))
        y = render.mic_sim(y, rng.choice(["M1", "M1", "M2"]), nrng)
        pad = np.zeros(int(render.SR * rng.uniform(0.2, 0.8)), np.float32)
        y = np.concatenate([pad, y, pad])
        bed = render.noise_bed(len(y), "train", nrng, kinds=tuple(rng.sample(["cab", "road", "siren", "monitor"], 2)))
        y = y + render.mix_snr(y, bed, rng.choice([0, 5, 10, 15, 20, 30]))
        y = y / max(1.0, np.max(np.abs(y)) / 0.98)
        p = d / f"u{len(out):04d}.wav"; sf.write(p, y, render.SR, subtype="PCM_16")
        out.append(dict(id=f"u{len(out):04d}", wav=str(p.relative_to(ROOT)), start_s=0, end_s=len(y) / render.SR, text=s, type="synthetic", subset="drug_utt"))
    return out


def united_syn_med(n):
    """United-Syn-Med TTS sentences that mention a drug from the pipeline formulary or our home-med list."""
    import pyarrow.parquet as pq, re
    F = json.loads(pathlib.Path("/home/user/pipeline/shared/formulary.json").read_text())
    names = set()
    for d in F["drugs"]:
        for x in [d["generic"], *d.get("brands", []), *d.get("slang", [])]:
            if len(x) > 3: names.add(x.lower())
    for o in json.loads((ROOT / "data/dictionary/home_meds.json").read_text())["items"]:
        names.add(o["name"].lower())
    rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")\b", re.I)
    out = []; d = ROOT / "data/audio/united_syn_med"; d.mkdir(parents=True, exist_ok=True)
    for f in sorted((ROOT / "data/raw/united_syn_med").glob("*.parquet")):
        pf = pq.ParquetFile(f)
        for g in range(pf.metadata.num_row_groups):
            for r in pf.read_row_group(g).to_pylist():
                if not rx.search(r["transcription"]): continue
                uid = f"usm_{f.stem[6:11]}_{len(out):05d}"
                wav = d / f"{uid}.wav"
                if not wav.exists():
                    import subprocess
                    subprocess.run(["ffmpeg", "-v", "quiet", "-i", "pipe:0", "-ac", "1", "-ar", "16000", str(wav)], input=r["audio"]["bytes"])
                dur = sf.info(wav).duration
                if 0.5 < dur <= 30:
                    out.append(dict(id=uid, wav=str(wav.relative_to(ROOT)), start_s=0, end_s=dur, text=r["transcription"], type="synthetic", subset="united_syn_med"))
                if len(out) >= n: return out
    return out


def cap(rows):
    by = {}
    for r in rows: by.setdefault(r["subset"], []).append(r)
    out = []
    for k, v in by.items():
        rng.shuffle(v)
        if k == "eka":   # prefer drug-bearing Eka clips
            v.sort(key=lambda r: 0 if (ROOT / f"data/scripts/real/gt/eka/{r['id']}.drug_terms.json").exists() and json.loads((ROOT / f"data/scripts/real/gt/eka/{r['id']}.drug_terms.json").read_text()) else 1)
        out += v[: CAPS.get(k, len(v))]
    return out


def real_rows(split):
    rows = []
    for l in open(ROOT / "data/manifests/real_items.jsonl"):
        it = json.loads(l)
        if it["split"] != split or it["duration"] <= 0.5 or it["duration"] > 30: continue
        if it["type"] not in ("real", "synthetic_external"): continue
        gt = ROOT / f"data/scripts/real/gt/{it['subset']}/{it['id']}.transcript.txt"
        txt = gt.read_text().strip()
        if "[NAME]" in txt or "[ADDRESS]" in txt or "[DOB]" in txt:   # audio still contains the PII -> excluded from training
            continue
        rows.append(dict(id=it["id"], wav=f"data/audio/real/{it['subset']}/{it['id']}.wav", start_s=0, end_s=it["duration"], text=txt,
                         type="real" if it["type"] == "real" else "synthetic", subset=it["subset"]))
    return rows


if __name__ == "__main__":
    dev_real = real_rows("dev"); rng.shuffle(dev_real)
    dev_keep = [r for r in dev_real if r["type"] == "real"][:90]
    keep_ids = {r["id"] for r in dev_keep}
    # dev-split sessions never overlap test sessions, so dev items not used for dev loss can train
    real_tr = real_rows("train") + [r for r in dev_real if r["id"] not in keep_ids]; syn_calls = call_chunks("train")
    utt = drug_utterances(N_DRUG_UTT); usm = united_syn_med(CAPS["united_syn_med"])
    train = cap(real_tr + syn_calls + utt + usm)
    rng.shuffle(train)
    dev = call_chunks("dev")[:60] + dev_keep
    for name, rows in [("train", train), ("dev", dev)]:
        (OUT / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    def stats(rows):
        r = [x for x in rows if x["type"] == "real"]; s = [x for x in rows if x["type"] != "real"]
        dr = sum(x["end_s"] - x["start_s"] for x in r) / 3600; ds = sum(x["end_s"] - x["start_s"] for x in s) / 3600
        return dict(items=len(rows), real_items=len(r), synthetic_items=len(s), real_hours=round(dr, 2), synthetic_hours=round(ds, 2),
                    real_share_items=round(len(r) / len(rows), 3), real_share_hours=round(dr / (dr + ds), 3))
    st = dict(train=stats(train), dev=stats(dev))
    (OUT / "mix.json").write_text(json.dumps(st, indent=1)); print(json.dumps(st, indent=1))
