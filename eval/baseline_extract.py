#!/usr/bin/env python3
"""Stand-in extractor (dictionary + regex) used until the Swift pipeline's earshot-eval is ready.
Input: ASR segments (<id>.segments.json from run_asr.py) + tap file ({"taps":[{clip_ms,source}]}).
Output: <id>.events.jsonl in the ground-truth event format, every value carrying a quote from the transcript.
Rules mirrored from the product spec: tap time becomes event time; speech within ±3 s labels a tap, extending to
+10 s; unlabelled taps -> "marked, no label"; speech with no tap -> source "heard"; nothing invented."""
import argparse, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import textnorm as tn

D = tn.dictionary()


def build_lexicon():
    drug = {}
    for x in D["drugs"]:
        for n in [x["name"], x["generic"], *x["brands"], *x["aliases"], *x.get("asr_variants", [])]:
            k = tn.normalize(n)
            if k and len(k) > 2 and k not in ("neb", "breathing treatment", "bolus", "fluid bolus", "ms", "dex", "mag", "ket", "roc", "special k", "calcium"):
                drug.setdefault(k, x["name"])
    drug["mag"] = "magnesium sulfate"
    route = {}
    for c, al in D["routes"].items():
        route[tn.normalize(c)] = c
        for a in al:
            route.setdefault(tn.normalize(a), c)
    route.update({"under the tongue": "SL", "chewed": "PO", "nebulizer": "neb", "by nebulizer": "neb", "neb": "neb", "nrb": "NRB",
                  "non rebreather": "NRB", "nasal cannula": "NC", "intranasal": "IN", "in the nose": "IN", "iv": "IV", "im": "IM", "io": "IO", "sl": "SL", "po": "PO"})
    route.pop("in", None)  # too ambiguous as a bare word
    unit = {"mg": "mg", "mcg": "mcg", "g": "g", "ml": "mL", "l": "L", "units": "units", "meq": "mEq", "puffs": "puffs", "j": "J", "percent": "%"}
    return drug, route, unit


DRUG, ROUTE, UNIT = build_lexicon()
NUM = r"(\d+(?:\.\d+)?)"
VITAL_RX = [
    ("bp", re.compile(r"(?:\b(?:bp|blood pressure|pressure)\b[a-z ]{0,12}?)?\b(\d{2,3}) over (\d{2,3})\b")),
    ("hr", re.compile(r"\b(?:heart rate|pulse|hr|heart s|rate)\b(?: is| s| of| at|s)?\s+(\d{2,3})\b")),
    ("rr", re.compile(r"\b(?:resps|respirations|resp|rr|respiratory rate|breathing)\b(?: are| is| of| at| s)?\s+(\d{1,2})\b")),
    ("spo2", re.compile(r"\b(?:sat|sats|spo2|pulse ox|o2 sat|satting|saturation)\b(?: s| is| of| at| are| coming up)?\s+(\d{2,3})\b")),
    ("bgl", re.compile(r"\b(?:bgl|sugar|blood sugar|glucose|cbg|bg)\b(?: s| is| of| at| was)?(?: now)?\s+(\d{2,3})\b")),
    ("gcs", re.compile(r"\b(?:gcs|glasgow)\b(?: s| is| of| at)?\s+(\d{1,2})\b")),
    ("pain", re.compile(r"\b(\d{1,2}) out of 10\b")),
    ("etco2", re.compile(r"\b(?:etco2|capno|co2)\b(?: s| is| of| at)?\s+(\d{1,3})\b")),
]
PROC_RX = [
    ("12-lead ECG", re.compile(r"\b12 lead\b|\becg\b")), ("IV access", re.compile(r"\b(?:14|16|18|20|22|24)\b(?: gauge)?(?: in the| in|,)? (?:left|right)\b|\b(?:14|16|18|20|22|24) gauge\b|\bgot a line\b|\biv access\b")),
    ("IO access", re.compile(r"\bio access\b|\bez io\b|\bdrilled\b")), ("BVM ventilation", re.compile(r"\bbagging\b|\bbvm\b|\bbag valve\b")),
    ("tourniquet", re.compile(r"\btourniquet\b(?! time)")), ("splinting", re.compile(r"\bsplint\b")), ("NPA", re.compile(r"\bnpa\b|\bnasal airway\b|\bnasal trumpet\b")),
    ("OPA", re.compile(r"\bopa\b|\boral airway\b")), ("CPAP", re.compile(r"\bcpap\b|\bsee pap\b")), ("CPR", re.compile(r"\bcompressions\b|\bcpr\b")),
    ("stroke scale", re.compile(r"\bbefast\b|\bcincinnati\b|\bstroke scale\b")), ("refusal", re.compile(r"\brefusal\b|\bagainst medical advice\b|\bama\b")),
    ("spinal motion restriction", re.compile(r"\bc collar\b|\bbackboard\b")), ("suction", re.compile(r"\bsuction")), ("defibrillation", re.compile(r"\bshock(?:ing)?\b|\bdefib")),
]
STATUS = {}
for t in D["status_terms"]:
    STATUS.setdefault(tn.normalize(t), t)
STATUS.update({"a and o times 4": "A&O×4", "a and o times 3": "A&O×3", "a and o times 2": "A&O×2", "a and o 4": "A&O×4", "a and o 3": "A&O×3", "aox4": "A&O×4",
               "pale cool and diaphoretic": "pale, cool and diaphoretic", "pale cool diaphoretic": "pale, cool and diaphoretic",
               "wheezes": "wheezes", "tripoding": "tripoding", "postictal": "postictal", "pinpoint pupils": "pinpoint pupils", "facial droop": "facial droop",
               "arm drift": "arm drift", "slurred speech": "slurred speech", "compensating": "compensating", "still seizing": "actively seizing"})
STATUS_NORM = {"a&o×4": "A&O×4", "a&o×3": "A&O×3"}
TIME_CUES = []
for code, v in D["time_events"].items():
    for c in v["cues"]:
        TIME_CUES.append((tn.normalize(c), code))
TIME_CUES += [(tn.normalize(c), k) for c, k in [("on scene", "eTimes.06"), ("transporting", "eTimes.09"), ("arrived at", "eTimes.11"), ("arriving at", "eTimes.11"),
                                                  ("at the trauma center", "eTimes.11"), ("we re here", "eTimes.11"), ("at general", "eTimes.11"),
                                                  ("transfer of care", "eTimes.12"), ("handing off", "eTimes.12"), ("back in service", "eTimes.13")]]
TIME_CUES.sort(key=lambda x: -len(x[0]))


def find_all(norm, key):
    return [m.start() for m in re.finditer(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", norm)]


def extract_segment(text):
    """Return list of (type, fields, quote_norm) from one ASR segment."""
    n = tn.normalize(text)
    out = []
    # medications
    used = set()
    for k in sorted(DRUG, key=len, reverse=True):
        for pos in find_all(n, k):
            if any(p <= pos < q for p, q in used):
                continue
            used.add((pos, pos + len(k)))
            name = DRUG[k]
            # doses: nearest number after the drug (within 4 tokens) else before ("324 of aspirin")
            after = n[pos + len(k):].split()[:5]
            before = n[:pos].split()[-3:]
            f = dict(drug=name); qt = [k]
            dose_tokens = []
            for i, t in enumerate(after):
                if re.fullmatch(NUM, t):
                    f["dose"] = t; dose_tokens = after[: i + 1]
                    if i + 1 < len(after) and after[i + 1] in UNIT:
                        f["unit"] = UNIT[after[i + 1]]; dose_tokens = after[: i + 2]
                    break
                if t in DRUG or t in ("and",):
                    break
            if "dose" not in f and before and re.fullmatch(NUM, before[-1] if before[-1] != "of" else (before[-2] if len(before) > 1 else "")):
                num = before[-1] if before[-1] != "of" else before[-2]
                f["dose"] = num
                if before[-1] == "of" and len(before) > 2 and before[-3] == num:
                    pass
            if "dose" not in f and len(before) >= 2 and before[-1] in UNIT and re.fullmatch(NUM, before[-2]):
                f["dose"], f["unit"] = before[-2], UNIT[before[-1]]
            if name == "oxygen" and "unit" not in f and "l" in after[:3]:
                f["unit"] = "L/min"
            if f.get("unit") == "L" and name == "oxygen":
                f["unit"] = "L/min"
            # route anywhere in the segment after the drug, or immediately before
            tail = " ".join(n[pos:].split()[:9])
            for rk in sorted(ROUTE, key=len, reverse=True):
                if find_all(tail, rk):
                    f["route"] = ROUTE[rk]; break
            if "route" not in f and name == "oxygen":
                for rk in ("nrb", "non rebreather", "nasal cannula"):
                    if rk in n: f["route"] = ROUTE.get(rk, "NRB")
            out.append(("medication", f, " ".join(([before[-1]] if "dose" in f and before and before[-1] == f.get("dose") else []) + [k] + dose_tokens)))
    names = {e[1]["drug"] for e in out}
    if {"albuterol", "ipratropium"} <= names:
        out = [e for e in out if e[1]["drug"] != "albuterol/ipratropium"]
    # vitals
    for name, rx in VITAL_RX:
        for m in rx.finditer(n):
            if name == "bp":
                out.append(("vital", dict(name="bp", value=f"{m.group(1)}/{m.group(2)}", unit="mmHg"), m.group(0)))
            else:
                v = m.group(1)
                if name == "hr" and "over" in n[m.end():m.end() + 6]:
                    continue
                if name == "hr" and n[max(0, m.start() - 6):m.start()].strip().endswith("resp"):
                    continue
                out.append(("vital", dict(name=name, value=v, unit={"hr": "bpm", "rr": "/min", "spo2": "%", "bgl": "mg/dL", "gcs": "", "pain": "/10", "etco2": "mmHg"}[name]), m.group(0)))
    # de-duplicate hr matched through 'heart rate' and 'rate'
    seen = set(); ded = []
    for e in out:
        key = (e[0], json.dumps(e[1], sort_keys=True))
        if key in seen: continue
        seen.add(key); ded.append(e)
    out = ded
    for name, rx in PROC_RX:
        m = rx.search(n)
        if m:
            out.append(("procedure", dict(name=name), m.group(0)))
    for k in sorted(STATUS, key=len, reverse=True):
        if k and len(k) > 3 and find_all(n, k):
            out.append(("status", dict(term=STATUS[k]), k))
    for cue, code in TIME_CUES:
        if find_all(n, cue):
            out.append(("time", dict(etime=code), cue)); break
    if re.search(r"\b(respond|dispatched|toned out)\b", n):
        out.append(("dispatch", dict(text=text.strip()), n))
    if re.search(r"\bfound\b", n):
        out.append(("found", dict(text=text.strip()), n))
    return out


def hms_add(start, ms):
    import datetime as dt
    return (dt.datetime.strptime(start, "%H:%M:%S") + dt.timedelta(milliseconds=ms)).strftime("%H:%M:%S")


def run(segments, taps, start, cid):
    evs = []
    for si, s in enumerate(segments):
        for typ, f, q in extract_segment(s["text"]):
            evs.append(dict(type=typ, fields=f, quote=q, seg=si, clip_ms=s["start_ms"], source="heard"))
    # tap merge
    seg_has = {e["seg"] for e in evs}
    used_segs = set(); out_taps = []
    for t in sorted(taps, key=lambda t: t["clip_ms"]):
        tm = t["clip_ms"]; best = None
        for lo, hi in ((-3000, 3000), (-3000, 10000)):
            cands = [i for i in seg_has if i not in used_segs and lo <= segments[i]["start_ms"] - tm <= hi]
            if cands:
                best = min(cands, key=lambda i: abs(segments[i]["start_ms"] - tm)); break
        if best is None:
            evs.append(dict(type="marker", fields={}, quote=None, seg=None, clip_ms=tm, source="tap", label="marked, no label", tap_source=t["source"]))
        else:
            used_segs.add(best)
            for e in evs:
                if e["seg"] == best:
                    e["source"] = "tap+heard"; e["clip_ms"] = tm; e["tap_source"] = t["source"]
    evs.sort(key=lambda e: e["clip_ms"])
    for i, e in enumerate(evs):
        e["id"] = f"p{i+1}"; e["call_id"] = cid; e["time"] = hms_add(start, e["clip_ms"])
        e["segment_text"] = segments[e["seg"]]["text"] if e["seg"] is not None else None
    return evs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="dir with <id>.segments.json from run_asr.py")
    ap.add_argument("--gt-dir", required=True, help="dir with <id>.taps.json (tap file input: button taps + knock/snap times)")
    ap.add_argument("--tap-input", default="gt", choices=["gt", "detected", "none"],
                    help="gt: use ground-truth tap file (as the app would receive button/knock events); detected: <run>/<id>.taps_detected.json")
    a = ap.parse_args()
    rd = pathlib.Path(a.run_dir); gd = pathlib.Path(a.gt_dir)
    for sp in sorted(rd.glob("*.segments.json")):
        uid = sp.name.split(".")[0]
        segs = json.loads(sp.read_text())
        tf = gd / f"{uid.split('_')[0]}.taps.json"
        start = "12:00:00"; taps = []
        if tf.exists():
            tj = json.loads(tf.read_text()); start = tj.get("start", start)
            if a.tap_input == "gt":
                taps = tj["taps"]
        if a.tap_input == "detected" and (rd / f"{uid}.taps_detected.json").exists():
            taps = json.loads((rd / f"{uid}.taps_detected.json").read_text())["taps"]
        evs = run(segs, taps, start, uid)
        (rd / f"{uid}.events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs))
    print("extracted", rd)


if __name__ == "__main__":
    main()
