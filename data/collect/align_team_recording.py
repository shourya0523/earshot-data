#!/usr/bin/env python3
"""Build ground truth for a team-recorded take of a scripted test call.
  python3 data/collect/align_team_recording.py --call c01 --take t1
Inputs: data/audio/test/team/<call>.<take>.wav, data/scripts/test/gt/team/<call>.<take>.taps_log.json, data/scripts/test/<call>_*.call
Method: word-level whisper.cpp timestamps (-ml 1) are aligned to the script words; each script line gets the time of its
first aligned word. Logged knock/snap times are snapped to the nearest audio transient within ±1.5 s. Logged taps are
matched to the script's TAP lines in order. Output: same GT files as the TTS version under data/scripts/test/gt/team/
named <call>.<take>.* (score with --gt data/scripts/test/gt/team and run ids <call>.<take>)."""
import argparse, json, pathlib, subprocess, sys
import numpy as np, soundfile as sf, jiwer
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data/synth")); sys.path.insert(0, str(ROOT / "eval"))
import calldsl, render, textnorm as tn, tap_detector as td


def words_with_times(wav):
    out = ROOT / "eval/runs/_align" / pathlib.Path(wav).stem; out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(ROOT / ".tools/whisper-cli"), "-m", str(ROOT / "data/raw/models/ggml-small.en.bin"), "-f", str(wav), "-ml", "1", "-oj", "-of", str(out), "-np", "-t", "4"],
                   check=True, capture_output=True)
    j = json.load(open(f"{out}.json"))
    W = []
    for s in j["transcription"]:
        for w in tn.normalize(s["text"]).split():
            W.append((w, s["offsets"]["from"]))
    return W


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--call", required=True); ap.add_argument("--take", default="t1")
    a = ap.parse_args()
    uid = f"{a.call}.{a.take}"
    wav = ROOT / f"data/audio/test/team/{uid}.wav"; gtd = ROOT / "data/scripts/test/gt/team"
    call = calldsl.parse(next((ROOT / "data/scripts/test").glob(f"{a.call}_*.call")).read_text())
    log = json.loads((gtd / f"{uid}.taps_log.json").read_text())["taps"]
    W = words_with_times(wav)
    lines = [it for it in call["items"] if it["kind"] == "speech"]
    ref_words, owner = [], []
    for li, it in enumerate(lines):
        ws = tn.normalize(it["text"]).split(); ref_words += ws; owner += [li] * len(ws)
    hyp = " ".join(w for w, _ in W)
    al = jiwer.process_words(" ".join(ref_words), hyp).alignments[0]
    t_of_ref = [None] * len(ref_words)
    for ch in al:
        if ch.type in ("equal", "substitute"):
            for k in range(ch.ref_end_idx - ch.ref_start_idx):
                hi = ch.hyp_start_idx + k
                if hi < len(W): t_of_ref[ch.ref_start_idx + k] = W[hi][1]
    line_t = []
    for li in range(len(lines)):
        ts = [t_of_ref[i] for i in range(len(ref_words)) if owner[i] == li and t_of_ref[i] is not None]
        line_t.append(min(ts) if ts else None)
    # interpolate missing line times
    for li in range(len(line_t)):
        if line_t[li] is None:
            prev = next((line_t[k] for k in range(li - 1, -1, -1) if line_t[k] is not None), 0)
            line_t[li] = prev + 2000
    y, _ = sf.read(wav, dtype="float32")
    F = td.features(y)
    raw = []  # loose transient list (singles allowed) to snap logged knock/snap times onto
    e, bg = F["e"], F["bg"]
    for i in range(3, len(e) - 30):
        if e[i] - bg[i] > 12 and e[i] > e[i - 3] + 8:
            raw.append(i * 2)
    doubles = [t for t in log if t["kind"] == "double"]
    script_taps = [it for it in call["items"] if it["kind"] == "tap"]
    taps = []
    for k, (st, lg) in enumerate(zip(script_taps, doubles)):
        t = lg["clip_ms"]
        if lg["source"] in ("knock", "snap") and raw:
            near = [r for r in raw if abs(r - lg["key_ms"]) <= 1500 and r <= lg["key_ms"]]
            if near: t = min(near, key=lambda r: abs(r - (lg["key_ms"] - 400)))
        taps.append(dict(id=f"t{k+1}", clip_ms=int(t), source=st["source"], labelled=st["labelled"], logged_source=lg["source"]))
    if len(doubles) != len(script_taps):
        print(f"WARNING: {len(doubles)} logged taps vs {len(script_taps)} in script; extra/missing ones ignored")
    # events
    start = call["meta"].get("start", "12:00:00")
    events = []; ti = 0; pending = []
    seq = [it for it in call["items"] if it["kind"] in ("speech", "tap")]
    li = 0; tap_iter = iter(taps)
    for it in seq:
        if it["kind"] == "tap":
            tp = next(tap_iter, None)
            if tp and tp["labelled"]: pending.append(tp)
            continue
        t_line = line_t[li]; li += 1
        tap = pending.pop(0) if (it["events"] and pending) else None
        for e_ in it["events"]:
            ms = tap["clip_ms"] if tap else t_line
            ev = dict(id=f"e{len(events)+1}", call_id=uid, time=render.hms_add(start, ms), clip_ms=ms, type=e_["type"], fields=e_["fields"],
                      source="tap+heard" if tap else "heard", quote=e_["quote"], segment_start_ms=t_line)
            if tap: ev["tap_id"] = tap["id"]
            events.append(ev)
    for tp in taps:
        if not tp["labelled"]:
            events.append(dict(id=f"m{tp['id']}", call_id=uid, time=render.hms_add(start, tp["clip_ms"]), clip_ms=tp["clip_ms"], type="marker", fields={},
                               source="tap", quote=None, label="marked, no label", tap_id=tp["id"]))
    events.sort(key=lambda e: e["clip_ms"])
    (gtd / f"{uid}.transcript.txt").write_text(" ".join(it["text"] for it in lines) + "\n")
    (gtd / f"{uid}.events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (gtd / f"{uid}.taps.json").write_text(json.dumps(dict(taps=taps, ignored=[t for t in log if t["kind"] != "double"], start=start), indent=1))
    (gtd / f"{uid}.expected.json").write_text(json.dumps(render.expected_fields(call, events, start), indent=1))
    print("wrote GT for", uid, len(events), "events", len(taps), "taps")


if __name__ == "__main__":
    main()
