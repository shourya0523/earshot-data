#!/usr/bin/env python3
"""Add more HUMAN speech to the training pool (appends to data/manifests/real_items.jsonl; train/dev only, never test).
  python3 data/collect/prepare_extra_human.py [--delete-parquet]
Sources:
  afrispeech : AfriSpeech-200 clinical-domain clips only (human, African-accented English; drug names, doses) - split by speaker
  multimed   : MultiMed English train shard 0 (human, medical talks/YouTube) - clips <= 30 s
  radio      : police/EMS radio transmissions (human, real radio channel; MIT) - clips with >= 4 words
  emsassist  : EMSAssist-2 train shard 1 + test shard 0 (human read EMS phrases; their 'test' is not our test)
PII: transcripts are scrubbed; clips whose transcript needed scrubbing are dropped from training (audio still has the PII)."""
import argparse, csv, hashlib, io, json, pathlib, re, subprocess, sys, tarfile
import soundfile as sf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scrub_pii import scrub
ROOT = pathlib.Path(__file__).resolve().parents[2]; RAW = ROOT / "data/raw"; AUD = ROOT / "data/audio/real"; GT = ROOT / "data/scripts/real/gt"
MAN = ROOT / "data/manifests/real_items.jsonl"


def h(s, m=100): return int(hashlib.sha1(s.encode()).hexdigest(), 16) % m


def to_wav(b, dest, src_fmt=None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        subprocess.run(["ffmpeg", "-v", "quiet", "-i", "pipe:0", "-ac", "1", "-ar", "16000", str(dest)], input=b)
    return sf.info(dest).duration if dest.exists() else 0


def add(items, sub, uid, b, text, source, lic, split, pii_note):
    clean, found = scrub(text)
    if found: return   # drop PII-bearing clips
    if len(clean.split()) < 2: return
    d = to_wav(b, AUD / sub / f"{uid}.wav")
    if not 0.5 < d <= 30: return
    (GT / sub).mkdir(parents=True, exist_ok=True); (GT / sub / f"{uid}.transcript.txt").write_text(clean.strip() + "\n")
    items.append(dict(id=uid, source=source, type="real", subset=sub, split=split, duration=d, pii=pii_note, license=lic))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--delete-parquet", action="store_true"); a = ap.parse_args()
    import pyarrow.parquet as pq
    old = [json.loads(l) for l in open(MAN)] if MAN.exists() else []
    have = {i["id"] for i in old}; items = []
    # AfriSpeech clinical
    for f in sorted((RAW / "afrispeech").glob("*.parquet")):
        pf = pq.ParquetFile(f)
        for g in range(pf.metadata.num_row_groups):
            for r in pf.read_row_group(g).to_pylist():
                if r.get("domain") != "clinical": continue
                uid = "af_" + hashlib.sha1(r["audio_id"].encode()).hexdigest()[:12]
                if uid in have: continue
                add(items, "afrispeech", uid, r["audio"]["bytes"], r["transcript"], "AfriSpeech-200 (clinical domain)", "CC-BY-NC-SA-4.0",
                    "dev" if h(r["speaker_id"]) < 8 else "train", "no (read text)")
        if a.delete_parquet: f.unlink()
    # MultiMed English
    for f in sorted((RAW / "multimed").glob("*.parquet")):
        pf = pq.ParquetFile(f)
        for g in range(pf.metadata.num_row_groups):
            for k, r in enumerate(pf.read_row_group(g).to_pylist()):
                b = r["audio"]["bytes"] if isinstance(r.get("audio"), dict) else None
                if not b: continue
                uid = f"mm_{f.stem}_{g}_{k}"
                if uid in have: continue
                add(items, "multimed", uid, b, r["text"], "MultiMed English (leduckhai)", "MIT", "dev" if h(uid) < 5 else "train", "possible (public talks), scrubbed")
        if a.delete_parquet: f.unlink()
    # police / EMS radio
    tz = RAW / "police_radio/data.tar.gz"
    if tz.exists():
        meta = {r["file_name"]: r["transcription"] for r in csv.DictReader(open(RAW / "police_radio/metadata.csv", encoding="utf-8"))}
        with tarfile.open(tz) as t:
            for m in t:
                name = pathlib.Path(m.name).name
                if not m.isfile() or name not in meta: continue
                txt = meta[name]
                if len(txt.split()) < 4: continue
                uid = "pr_" + hashlib.sha1(name.encode()).hexdigest()[:12]
                if uid in have: continue
                add(items, "radio", uid, t.extractfile(m).read(), txt, "police-radio-punctuated-dataset", "MIT", "dev" if h(name) < 5 else "train", "radio traffic; scrubbed, PII clips dropped")
    # EMSAssist-2 extra shards (human read)
    for f in [RAW / "emsassist2/train-1.parquet", RAW / "emsassist2/test-0.parquet"]:
        if not f.exists(): continue
        for r in pq.read_table(f).to_pylist():
            m = re.match(r"separate_([a-z]+)_(\d+)", pathlib.Path(r["audio"]["path"]).stem)
            spk = hashlib.sha1((m.group(1) if m else "x").encode()).hexdigest()[:6]
            uid = f"ea_{spk}_{f.stem}_{m.group(2) if m else h(r['audio']['path'], 10**6)}"
            if uid in have: continue
            add(items, "emsassist", uid, r["audio"]["bytes"], r["transcript"], "saahith/EMSAssist-2", "unknown", "train", "no (speaker name removed)")
        if a.delete_parquet: f.unlink()
    with open(MAN, "a") as fo:
        for i in items: fo.write(json.dumps(i) + "\n")
    import collections
    c = collections.Counter((i["subset"], i["split"]) for i in items); d = collections.defaultdict(float)
    for i in items: d[(i["subset"], i["split"])] += i["duration"]
    for k in sorted(c): print(k, c[k], f"{d[k]/3600:.2f} h")


if __name__ == "__main__":
    main()
