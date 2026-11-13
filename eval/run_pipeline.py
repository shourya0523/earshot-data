#!/usr/bin/env python3
"""Run the pipeline agent's `earshot-eval` on every call and convert its outputs for eval/score.py.
  python3 eval/run_pipeline.py --wavs 'data/audio/test/tts/c*.snr10.wav' --gt data/scripts/test/gt/tts \
      --out eval/runs/pipe_stock/test_tts_snr10 [--asr-model ...] [--tagger ...] [--extra-args "--no-prompt"]
  python3 eval/run_pipeline.py --convert-only --out ...     (re-convert existing raw outputs)
Per call: <out>/raw/<id>/ (earshot-eval output as-is), <out>/<id>.hyp.txt, <id>.events.jsonl (GT format),
<id>.outputs/ (soap/chart/imist/nemsis), timing.jsonl (stages from timing.json).
Tap file given to earshot-eval = ground-truth taps (button + knock + snap), i.e. what the clip would send."""
import argparse, glob, json, pathlib, shutil, subprocess, sys, datetime as dt
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = pathlib.Path("/home/user/pipeline/core/.build/release/earshot-eval")
DICT = pathlib.Path("/home/user/pipeline/shared")
VMAP = {"heart_rate": "hr", "resp_rate": "rr", "spo2": "spo2", "etco2": "etco2", "glucose": "bgl", "gcs": "gcs", "temp": "temp", "pain": "pain"}
VUNIT = {"hr": "bpm", "rr": "/min", "spo2": "%", "bgl": "mg/dL", "gcs": "", "pain": "/10", "etco2": "mmHg", "temp": "F"}
TIME_TYPES = {"arrival": "eTimes.11", "handoff": "eTimes.12", "transport": "eTimes.09"}


def convert(uid, raw_dir, out, gt_dir):
    r = json.loads((raw_dir / "transcript.raw.json").read_text())
    (out / f"{uid}.hyp.txt").write_text(" ".join(s["text"].strip() for s in r["segments"]) + "\n")
    (out / f"{uid}.segments.json").write_text(json.dumps([dict(start_ms=s["start_ms"], end_ms=s["end_ms"], text=s["text"]) for s in r["segments"]]))
    ev = json.loads((raw_dir / "events.json").read_text())
    ev = ev if isinstance(ev, list) else ev.get("events", [])
    conv = []
    for e in ev:
        f = e.get("fields") or {}; rc = e.get("receipts") or {}
        base = dict(id=e["id"], call_id=uid, clip_ms=e.get("t_ms", 0), source=e.get("source"), quote=e.get("quote"), flags=e.get("flags") or [],
                    raw_type=e["type"], tap_source=e.get("tap_source"))
        def q_of(k):
            return (rc.get(k) or {}).get("quote") or e.get("quote")
        def inferred(k):
            return bool((rc.get(k) or {}).get("inferred")) or ("inferred" in (e.get("flags") or []) and k == "unit")
        t = e["type"]
        if t == "vitals":
            if f.get("bp_systolic") and f.get("bp_diastolic"):
                conv.append({**base, "type": "vital", "fields": dict(name="bp", value=f"{f['bp_systolic']}/{f['bp_diastolic']}", unit="mmHg"), "quote": q_of("bp_systolic")})
            for k, n in VMAP.items():
                if f.get(k) not in (None, ""):
                    conv.append({**base, "type": "vital", "fields": dict(name=n, value=str(f[k]), unit=VUNIT[n]), "quote": q_of(k)})
            if f.get("mental_status"):
                conv.append({**base, "type": "status", "fields": dict(term=str(f["mental_status"])), "quote": q_of("mental_status")})
        elif t == "medication":
            mf = {k: str(f[k]) for k in ("drug", "dose", "unit", "route") if f.get(k) not in (None, "")}
            inf = [k for k in mf if inferred(k)]
            conv.append({**base, "type": "medication", "fields": mf, "inferred_fields": inf, "quote": e.get("quote")})
        elif t == "procedure":
            conv.append({**base, "type": "procedure", "fields": dict(name=str(f.get("name") or f.get("procedure") or "")), "raw_fields": f})
        elif t == "status":
            kind = f.get("kind")
            if kind == "finding" and f.get("term"):
                conv.append({**base, "type": "status", "fields": dict(term=str(f["term"])), "raw_fields": f})
            elif kind == "condition" and f.get("condition"):
                conv.append({**base, "type": "status", "fields": dict(term=str(f["condition"])), "raw_fields": f})
            else:   # patient / allergy / home_med / drug_mention / symptom / history: not scored as status
                conv.append({**base, "type": f"status_{kind}", "fields": {k: str(v) for k, v in f.items() if k != "kind"}, "raw_fields": f})
        elif t in ("arrival", "handoff"):
            conv.append({**base, "type": "time", "fields": dict(etime=TIME_TYPES[t]), "raw_fields": f})
        elif t == "transport":
            if f.get("etime"):
                conv.append({**base, "type": "time", "fields": dict(etime=str(f["etime"])), "raw_fields": f})
            else:   # destination / mode: not an eTime
                conv.append({**base, "type": "transport_info", "fields": {k: str(v) for k, v in f.items()}, "raw_fields": f})
        elif t == "dispatch":
            if f.get("dispatch_reason"):
                conv.append({**base, "type": "dispatch", "fields": dict(text=str(f["dispatch_reason"])), "raw_fields": f})
            if f.get("found") or f.get("chief_complaint"):
                conv.append({**base, "type": "found", "fields": dict(text=str(f.get("found") or f.get("chief_complaint"))), "raw_fields": f})
        elif t == "tap":
            conv.append({**base, "type": "marker", "fields": {}, "label": (f.get("label"))})
        else:
            conv.append({**base, "type": t, "fields": {k: str(v) for k, v in f.items()}})
    (out / f"{uid}.events.jsonl").write_text("".join(json.dumps(c) + "\n" for c in conv))
    od = out / f"{uid}.outputs"; od.mkdir(exist_ok=True)
    for name, dst in [("soap.md", "soap.md"), ("chart.md", "chart.md"), ("imist_ambo.md", "imist.md"), ("nemsis.xml", "nemsis.xml")]:
        if (raw_dir / name).exists():
            shutil.copy(raw_dir / name, od / dst)
    tj = json.loads((raw_dir / "timing.json").read_text())
    return tj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wavs"); ap.add_argument("--gt", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--asr-model", default=str(ROOT / "data/raw/models/ggml-small.en.bin")); ap.add_argument("--tagger")
    ap.add_argument("--extra-args", default=""); ap.add_argument("--convert-only", action="store_true"); ap.add_argument("--no-taps", action="store_true")
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True); gt = pathlib.Path(a.gt)
    wavs = sorted(glob.glob(a.wavs)) if a.wavs else []
    if a.convert_only:
        wavs = [str(p) for p in sorted((out / "raw").iterdir())]
    tim = open(out / "timing.jsonl", "w")
    for w in wavs:
        uid = pathlib.Path(w).name.split(".")[0]
        raw = out / "raw" / uid
        gid = uid.split("_")[0]
        tf = gt / f"{gid}.taps.json"
        tj = json.loads(tf.read_text()) if tf.exists() else {"taps": [], "start": "12:00:00"}
        if not a.convert_only and not (raw / "events.json").exists():
            raw.mkdir(parents=True, exist_ok=True)
            taps_path = raw.parent / f"{uid}.taps.input.json"
            taps_path.write_text(json.dumps([] if a.no_taps else [dict(clip_ms=t["clip_ms"], source=t["source"], gesture="mark") for t in tj["taps"]]))
            start = f"2026-11-15T{tj.get('start', '12:00:00')}-05:00"
            cmd = [str(BIN), "run", w, "--taps", str(taps_path), "--asr-model", a.asr_model, "--dict", str(DICT), "--call-id", uid, "--start", start, "--out", str(raw)]
            if a.tagger: cmd += ["--tagger", a.tagger]
            cmd += a.extra_args.split()
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode != 0:
                print("FAIL", uid, p.stderr[-800:], file=sys.stderr); continue
        t = convert(uid, raw, out, gt)
        dur = sf.info(w).duration if w.endswith(".wav") else None
        tim.write(json.dumps(dict(id=uid, audio_s=dur or 0, wall_s=t["seconds"]["total"], stages=t["seconds"], model=t.get("asr_model"))) + "\n"); tim.flush()
        print(uid, t["seconds"]["total"], flush=True)


if __name__ == "__main__":
    main()
