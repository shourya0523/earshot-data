#!/usr/bin/env python3
"""Turn downloaded real-speech sources into 16 kHz mono wavs + reference transcripts + split assignment.
  python3 -I data/collect/prepare_real.py
Outputs: data/audio/real/<src>/<id>.wav, data/scripts/real/gt/<src>/<id>.transcript.txt (+ .drug_terms.json for Eka),
data/manifests/real_items.jsonl (id, source, split, duration, pii, license).
Splits are assigned by a stable hash of the *speaker/session/consultation* so no session spans two splits."""
import hashlib, io, json, pathlib, re, subprocess, sys, csv
import numpy as np, soundfile as sf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scrub_pii import scrub

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"; AUD = ROOT / "data/audio/real"; GT = ROOT / "data/scripts/real/gt"
SR = 16000
items = []


def h(s, mod=100):
    return int(hashlib.sha1(s.encode()).hexdigest(), 16) % mod


def to_wav(raw_bytes, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return sf.info(dest).duration
    p = subprocess.run(["ffmpeg", "-v", "quiet", "-i", "pipe:0", "-ac", "1", "-ar", str(SR), "-f", "wav", str(dest)], input=raw_bytes)
    return sf.info(dest).duration if dest.exists() else 0


def write_gt(src, uid, text, extra=None):
    d = GT / src; d.mkdir(parents=True, exist_ok=True)
    clean, found = scrub(text)
    (d / f"{uid}.transcript.txt").write_text(clean.strip() + "\n")
    if extra:
        (d / f"{uid}.drug_terms.json").write_text(json.dumps(extra))
    return found


def split_of(key, test, dev):
    x = h(key)
    return "test" if x < test else ("dev" if x < test + dev else "train")


import pyarrow.parquet as pq
# EMSContExt: EMS narratives read aloud by humans
for r in pq.read_table(RAW / "emscontext/test.parquet").to_pylist():
    uid = "ems_" + pathlib.Path(r["audio"]["path"]).stem
    d = to_wav(r["audio"]["bytes"], AUD / "emsctx" / f"{uid}.wav")
    pii = write_gt("emsctx", uid, r["transcript"])
    items.append(dict(id=uid, source="EMSContExt_audio", type="real", subset="emsctx", split=split_of(uid, 35, 30), duration=d, pii=pii,
                      license="unknown (no dataset card)"))
# Eka: Indian-English clinician speech with drug/dose spans
for f in sorted((RAW / "eka").glob("test-*.parquet")):
    for r in pq.read_table(f).to_pylist():
        uid = "eka_" + r["md5_audio"][:12]
        ents = json.loads(r["medical_entities"] or "[]")
        drugs = [e[0] for e in ents if e[1] == "drugs"]
        sp = split_of(r["session_id"] or uid, 30, 30)
        if sp != "train" and not drugs and h(uid) % 3:   # keep dev/test focused on drug-bearing clips
            continue
        d = to_wav(r["audio"], AUD / "eka" / f"{uid}.wav")
        pii = write_gt("eka", uid, r["text"], extra=drugs)
        items.append(dict(id=uid, source="ekacare/eka-medical-asr-evaluation-dataset", type="real", subset="eka", split=sp, duration=d, pii=pii or "de-identified",
                          license="MIT", has_drugs=bool(drugs)))
# PriMock57: mock GP consultations, split by consultation
for r in (x for f in sorted((RAW / "primock57").glob("*.parquet")) for x in pq.read_table(f).to_pylist()):
    if len(r["transcription"].split()) < 4:
        continue
    uid = "pm_" + r["id"]
    cons = re.sub(r"_(doctor|patient)_u\d+$", "", r["id"])
    sp = split_of(cons, 35, 30)
    d = to_wav(r["audio"]["bytes"], AUD / "primock" / f"{uid}.wav")
    pii = write_gt("primock", uid, r["transcription"])
    items.append(dict(id=uid, source="PriMock57 (macabdul9/Primock57)", type="real", subset="primock", split=sp, duration=d, pii=pii or "no (actors)", license="CC-BY-4.0"))
# Medical Speech, Transcription and Intent (crowd-read symptom phrases)
mi = RAW / "medspeech_intent"
if (mi / "overview.csv").exists():
    rows = {r["file_name"]: r for r in csv.DictReader(open(mi / "overview.csv", encoding="utf-8"))}
    for w in sorted((mi / "wav").glob("*.wav")):
        r = rows.get(w.name)
        if not r: continue
        uid = "mi_" + w.stem[:24]
        d = to_wav(w.read_bytes(), AUD / "medintent" / f"{uid}.wav")
        pii = write_gt("medintent", uid, r["phrase"])
        items.append(dict(id=uid, source="Medical Speech, Transcription and Intent", type="real", subset="medintent", split=split_of(r.get("speaker_id", uid), 30, 30),
                          duration=d, pii=pii or "no", license="unknown", intent=r.get("prompt")))

# EMSAssist-2: human-read EMS condition/protocol phrases (speaker name in file name -> hashed speaker id; train/dev only)
for f in sorted((RAW / "emsassist2").glob("*.parquet")):
    for r in pq.read_table(f).to_pylist():
        m = re.match(r"separate_([a-z]+)_(\d+)", pathlib.Path(r["audio"]["path"]).stem)
        spk = hashlib.sha1((m.group(1) if m else "x").encode()).hexdigest()[:6]
        uid = f"ea_{spk}_{m.group(2) if m else h(r['audio']['path'], 10**6)}"
        sp = "dev" if h(spk + uid) < 10 else "train"
        d = to_wav(r["audio"]["bytes"], AUD / "emsassist" / f"{uid}.wav")
        pii = write_gt("emsassist", uid, r["transcript"])
        items.append(dict(id=uid, source="saahith/EMSAssist-2", type="real", subset="emsassist", split=sp, duration=d, pii=pii or "no (speaker name removed)", license="unknown"))
# External synthetic EMS speech (TTS voices made by others): training only
for f in sorted((RAW / "ems_synth_saahith").glob("*.parquet")):
    for r in pq.read_table(f).to_pylist():
        uid = "es_" + pathlib.Path(r["audio"]["path"]).stem.replace("_synth", "") + ("v" if "validation" in f.name else "")
        d = to_wav(r["audio"]["bytes"], AUD / "ems_synth_ext" / f"{uid}.wav")
        write_gt("ems_synth_ext", uid, r["transcript"])
        items.append(dict(id=uid, source="saahith/synthetic_with_val", type="synthetic_external", subset="ems_synth_ext", split="train", duration=d, pii="no", license="unknown"))
import ast
for r in pq.read_table(RAW / "dispatcher_ambulance/train.parquet").to_pylist():
    turns = ast.literal_eval(r["dialog_dict"]); chunks = ast.literal_eval(r["chunks"])
    # chunk files are named <Role>-<k>.wav, k = k-th turn of that role
    cnt = {}
    for t in turns:
        role = t["role"]; cnt[role] = cnt.get(role, 0) + 1
        col = f"{role.lower().replace(' ', '-')}-{cnt[role]}"
        if col not in r or not r[col]: continue
        uid = f"da_{r['id']}_{col}"
        d = to_wav(r[col]["bytes"], AUD / "dispatch_synth_ext" / f"{uid}.wav")
        pii = write_gt("dispatch_synth_ext", uid, t["content"])
        items.append(dict(id=uid, source="ahmedelsayed/dispatcher-ambulance", type="synthetic_external", subset="dispatch_synth_ext", split="train", duration=d,
                          pii=pii or "synthetic addresses", license="unknown"))
(ROOT / "data/manifests").mkdir(parents=True, exist_ok=True)
(ROOT / "data/manifests/real_items.jsonl").write_text("".join(json.dumps(i) + "\n" for i in items))
import collections
c = collections.Counter((i["subset"], i["split"]) for i in items)
dur = collections.defaultdict(float)
for i in items: dur[(i["subset"], i["split"])] += i["duration"]
for k in sorted(c): print(k, c[k], f"{dur[k]/60:.1f} min")
