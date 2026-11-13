"""Parser for the .call script format used by data/scripts/test/*.call and generated training calls.

Format (one item per line):
  @call <id> <slug> start=HH:MM:SS
  @patient key=value ...           (values may be "quoted")
  @traps a; b                      (diagnosis words that may be SPOKEN but must never appear in outputs)
  SPK: text  >> ev; ev; ...        SPK in M1 M2 PT BY RD
      ev := vital:<name>=<value> "quote" | med:<drug>,<dose>,<unit>[,<route>] "quote" | proc:<name> "quote"
          | status:<term> "quote" | time:<eTimes.NN> "quote" | dispatch:<text> "quote" | found:<text> "quote"
  TAP <knock|snap|button> +label   tap that is labelled by the NEXT speech line carrying events
  TAP <knock|snap|button> -        unlabelled tap (no speech within -3 s..+10 s)
  GAP <seconds>                    silence (noise only)
  KNOCK3                           triple knock = stop recording
"""
import re, shlex

SPEAKERS = {"M1", "M2", "PT", "BY", "RD"}
VITAL_UNITS = {"bp": "mmHg", "hr": "bpm", "rr": "/min", "spo2": "%", "bgl": "mg/dL", "etco2": "mmHg", "gcs": "", "pain": "/10", "temp": "F"}


def parse_event(s):
    m = re.match(r'\s*(\w+):(.*?)\s+"(.*)"\s*$', s)
    if not m:
        raise ValueError(f"bad event: {s!r}")
    kind, body, quote = m.group(1), m.group(2).strip(), m.group(3)
    if kind == "vital":
        name, val = body.split("=", 1)
        return dict(type="vital", fields=dict(name=name, value=val, unit=VITAL_UNITS.get(name, "")), quote=quote)
    if kind == "med":
        parts = [p.strip() for p in body.split(",")]
        f = {k: v for k, v in zip(["drug", "dose", "unit", "route"], parts) if v}  # unspoken fields are omitted
        return dict(type="medication", fields=f, quote=quote)
    if kind == "proc":
        return dict(type="procedure", fields=dict(name=body), quote=quote)
    if kind == "status":
        return dict(type="status", fields=dict(term=body), quote=quote)
    if kind == "time":
        return dict(type="time", fields=dict(etime=body), quote=quote)
    if kind in ("dispatch", "found"):
        return dict(type=kind, fields=dict(text=body), quote=quote)
    raise ValueError(kind)


def parse(text):
    call = dict(meta={}, patient={}, traps=[], items=[])
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("@call"):
            _, cid, slug, *kv = line.split()
            call["meta"] = dict(call_id=cid, slug=slug, **dict(x.split("=", 1) for x in kv))
        elif line.startswith("@patient"):
            for tok in shlex.split(line[len("@patient"):]):
                k, v = tok.split("=", 1)
                call["patient"][k] = v
        elif line.startswith("@traps"):
            call["traps"] = [t.strip() for t in line[len("@traps"):].split(";") if t.strip()]
        elif line.startswith("TAP"):
            _, src, lab = line.split()
            call["items"].append(dict(kind="tap", source=src, labelled=(lab == "+label")))
        elif line.startswith("GAP"):
            call["items"].append(dict(kind="gap", seconds=float(line.split()[1])))
        elif line.strip() == "KNOCK3":
            call["items"].append(dict(kind="triple", source="knock"))
        else:
            spk, rest = line.split(":", 1)
            spk = spk.strip()
            assert spk in SPEAKERS, line
            text_, evs = (rest.split(">>", 1) + [""])[:2]
            text_ = text_.strip()
            events = [parse_event(e) for e in evs.split(";") if e.strip()]
            for e in events:
                if e["quote"] not in text_:
                    raise ValueError(f"quote not in text: {e['quote']!r} / {text_!r}")
            call["items"].append(dict(kind="speech", speaker=spk, text=text_, events=events))
    return call


def validate_test_call(call):
    """Test-set rules: >=3 meds/vitals, >=4 taps, some labelled and some not."""
    evs = [e for it in call["items"] if it["kind"] == "speech" for e in it["events"]]
    mv = sum(e["type"] in ("vital", "medication") for e in evs)
    taps = [it for it in call["items"] if it["kind"] == "tap"]
    lab = sum(t["labelled"] for t in taps)
    problems = []
    if mv < 3: problems.append(f"only {mv} meds/vitals")
    if len(taps) < 4: problems.append(f"only {len(taps)} taps")
    if lab == 0 or lab == len(taps): problems.append("need both labelled and unlabelled taps")
    return problems
