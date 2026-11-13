#!/usr/bin/env python3
"""Score Earshot runs against ground truth.

  python3 eval/score.py --gt data/scripts/test/gt/tts --run eval/runs/<name>/<set> [--json out.json] [--md out.md]

Run dir per call id <id> (id may carry a suffix: c01.snr10 -> gt c01):
  <id>.hyp.txt                 raw transcript (required for transcription metrics)
  <id>.clean.txt               cleaned transcript (optional; scored separately)
  <id>.events.jsonl            predicted events, GT event format (+ quote) (optional)
  <id>.taps_detected.json      {"taps":[{clip_ms, source}]} knock/snap detector output (optional)
  <id>.outputs/{soap.*,chart.*,imist.*,nemsis.xml}  rendered outputs (optional)
  timing.jsonl                 {"id","audio_s","wall_s",...,"stages":{...}} (optional)
GT dir: <id>.transcript.txt, <id>.events.jsonl, <id>.taps.json, <id>.expected.json
Noise-only dir (--noise-run): <id>.taps_detected.json + <id>.duration_s for false-taps/minute.
"""
import argparse, collections, json, pathlib, re, statistics, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import textnorm as tn
import jiwer

DRUGS = tn.drug_terms()
JARGON = tn.jargon_terms()
UNITS = {"mg", "mcg", "g", "ml", "l", "units", "meq", "puffs", "percent", "j"}
DICT = tn.dictionary()
CANON = {}
for x in DICT["drugs"]:
    for n in [x["name"], x["generic"], *x["brands"], *x["aliases"], *x.get("asr_variants", [])]:
        CANON[tn.normalize(n)] = x["name"]


def canon_drug(s):
    k = tn.normalize(s or "")
    return CANON.get(k, k)


GT_DIR = None


def gt_id(uid):
    if GT_DIR is not None and (GT_DIR / f"{uid}.transcript.txt").exists():
        return uid                      # team takes: c01.t1
    if GT_DIR is not None and "." in uid and (GT_DIR / f"{uid.rsplit('.', 1)[0]}.transcript.txt").exists():
        return uid.rsplit(".", 1)[0]
    return uid.split(".")[0].split("_")[0]


# ------------------------------------------------------------------ transcription
def align_counts(ref, hyp, pred):
    """per-token error counting restricted to ref tokens satisfying pred: returns (n_ref_sel, errors_on_sel)"""
    out = jiwer.process_words(ref, hyp)
    r = ref.split(); h = hyp.split()
    n = sum(pred(t) for t in r); err = 0
    for ch in out.alignments[0]:
        if ch.type in ("substitute", "delete"):
            err += sum(pred(t) for t in r[ch.ref_start_idx:ch.ref_end_idx])
        elif ch.type == "insert":
            # an inserted drug token next to a drug ref token is a split (e.g. 'nar can'); count once
            pass
    return n, err


def transcription(gt, run, ids):
    rows = []
    for uid in ids:
        hp = run / f"{uid}.hyp.txt"
        if not hp.exists():
            continue
        ref = tn.normalize((gt / f"{gt_id(uid)}.transcript.txt").read_text())
        hyp = tn.normalize(hp.read_text())
        w = jiwer.process_words(ref, hyp)
        extra = set()
        dt = gt / f"{gt_id(uid)}.drug_terms.json"
        if dt.exists():   # per-clip drug spans from the source dataset (e.g. Eka)
            for term in json.loads(dt.read_text()):
                extra |= {w for w in tn.normalize(term).split() if len(w) > 2 and not re.fullmatch(r"[\d.]+", w) and w not in UNITS}
        isdrug = lambda t, extra=extra: t in DRUGS or t in extra
        dn, de = align_counts(ref, hyp, isdrug)
        nn, ne = align_counts(ref, hyp, lambda t: bool(re.fullmatch(r"\d+(\.\d+)?", t)))
        un, ue = align_counts(ref, hyp, lambda t: t in UNITS)
        jr = [j for j in JARGON if re.search(rf"(?<![a-z0-9]){re.escape(j)}(?![a-z0-9])", ref)]
        jh = [j for j in jr if re.search(rf"(?<![a-z0-9]){re.escape(j)}(?![a-z0-9])", hyp)]
        rows.append(dict(id=uid, ref_words=len(ref.split()), errors=w.substitutions + w.deletions + w.insertions, wer=w.wer,
                         drug_n=dn, drug_err=de, num_n=nn, num_err=ne, unit_n=un, unit_err=ue, jargon_n=len(jr), jargon_hit=len(jh),
                         drug_misses=_misses(ref, hyp, isdrug)))
    if not rows:
        return None
    S = lambda k: sum(r[k] for r in rows)
    return dict(n_files=len(rows), wer=S("errors") / max(1, S("ref_words")), drug_wer=S("drug_err") / max(1, S("drug_n")), drug_tokens=S("drug_n"),
                number_acc=1 - S("num_err") / max(1, S("num_n")), number_tokens=S("num_n"), unit_acc=1 - S("unit_err") / max(1, S("unit_n")),
                jargon_recall=S("jargon_hit") / max(1, S("jargon_n")), jargon_terms=S("jargon_n"), per_file=rows)


def _misses(ref, hyp, pred):
    out = jiwer.process_words(ref, hyp); r = ref.split(); h = hyp.split(); m = []
    for ch in out.alignments[0]:
        if ch.type in ("substitute", "delete"):
            rs = r[ch.ref_start_idx:ch.ref_end_idx]
            if any(pred(t) for t in rs):
                m.append(f"{' '.join(rs)} -> {' '.join(h[ch.hyp_start_idx:ch.hyp_end_idx]) or '∅'}")
    return m


# ------------------------------------------------------------------ extraction
def load_events(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def num_eq(a, b):
    try:
        return abs(float(a) - float(b)) < 1e-6
    except Exception:
        return tn.normalize(str(a)) == tn.normalize(str(b))


def norm_route(r):
    r = (r or "").strip().lower()
    return {"nebulized": "neb", "nebulizer": "neb", "sublingual": "sl", "intranasal": "in", "intramuscular": "im", "intravenous": "iv", "oral": "po", "non-rebreather": "nrb"}.get(r, r)


def norm_unit(u):
    u = (u or "").strip().lower()
    return {"lpm": "l/min", "liters": "l/min", "milligrams": "mg", "micrograms": "mcg", "ml": "ml", "mls": "ml", "cc": "ml"}.get(u, u)


def extraction(gt, run, ids, time_tol_ms=15000):
    C = collections.defaultdict(lambda: [0, 0, 0])  # field -> [tp, n_pred, n_gt]
    ts_err = []; unsupported = 0; pred_fields = 0; unsup_examples = []
    tap_lab = [0, 0]; tap_unl = [0, 0]; inferred_n = [0]
    for uid in ids:
        pe = load_events(run / f"{uid}.events.jsonl")
        if not (run / f"{uid}.events.jsonl").exists():
            continue
        ge = load_events(gt / f"{gt_id(uid)}.events.jsonl")
        hyp = tn.normalize((run / f"{uid}.hyp.txt").read_text()) if (run / f"{uid}.hyp.txt").exists() else ""
        # receipts: every predicted field value must be supported by its quote (present in the raw transcript) or a tap
        for e in pe:
            if e.get("type") == "marker":
                if e.get("fields"):
                    unsupported += len(e["fields"]); pred_fields += len(e["fields"]); unsup_examples.append((uid, e.get("id"), "marker with fields"))
                continue
            q = tn.normalize(e.get("quote") or "")
            for k, v in (e.get("fields") or {}).items():
                if k in ("unit",) and k == "unit" and e.get("type") == "vital":
                    continue  # vital units are implied by the vital name
                if k in ("name",) and e.get("type") == "vital":
                    continue
                if e.get("type") in ("dispatch", "found", "time"):
                    continue
                pred_fields += 1
                if k in (e.get("inferred_fields") or []):
                    unsupported += 1; inferred_n[0] += 1; unsup_examples.append((uid, e.get("id"), f"{k}={v} INFERRED (not heard)")); continue
                ok = bool(q) and q in hyp and _value_in_quote(k, v, _window(hyp, q) if k == "route" else q, e)
                if not ok:
                    unsupported += 1; unsup_examples.append((uid, e.get("id"), f"{k}={v} quote={e.get('quote')!r}"))
        # medications: greedy match by drug then time
        gm = [e for e in ge if e["type"] == "medication"]; pm = [e for e in pe if e.get("type") == "medication"]
        pairs = _match(gm, pm, lambda g, p: canon_drug(g["fields"].get("drug")) == canon_drug(p["fields"].get("drug")), time_tol_ms)
        C["drug"][0] += len(pairs); C["drug"][1] += len(pm); C["drug"][2] += len(gm)
        for f in ("dose", "unit", "route"):
            C[f][1] += sum(1 for p in pm if p["fields"].get(f)); C[f][2] += sum(1 for g in gm if g["fields"].get(f))
            for g, p in pairs:
                gv, pv = g["fields"].get(f), p["fields"].get(f)
                if gv and pv and ((f == "dose" and num_eq(gv, pv)) or (f == "unit" and norm_unit(gv) == norm_unit(pv)) or (f == "route" and norm_route(gv) == norm_route(pv))):
                    C[f][0] += 1
        # vitals per name
        gv = [e for e in ge if e["type"] == "vital"]; pv = [e for e in pe if e.get("type") == "vital"]
        names = {e["fields"]["name"] for e in gv} | {e["fields"].get("name") for e in pv}
        for n in names:
            g_ = [e for e in gv if e["fields"]["name"] == n]; p_ = [e for e in pv if e["fields"].get("name") == n]
            pr = _match(g_, p_, lambda a, b: str(a["fields"]["value"]).replace(" ", "") == str(b["fields"].get("value")).replace(" ", ""), time_tol_ms)
            k = f"vital.{n}"; C[k][0] += len(pr); C[k][1] += len(p_); C[k][2] += len(g_)
            for a, b in pr:
                ts_err.append(abs(a["clip_ms"] - b["clip_ms"]))
        for typ, key in (("procedure", "name"), ("status", "term")):
            g_ = [e for e in ge if e["type"] == typ]; p_ = [e for e in pe if e.get("type") == typ]
            pr = _match(g_, p_, lambda a, b: tn.normalize(a["fields"][key]) == tn.normalize(b["fields"].get(key, "")), time_tol_ms)
            C[typ][0] += len(pr); C[typ][1] += len(p_); C[typ][2] += len(g_)
        for g, p in pairs:
            ts_err.append(abs(g["clip_ms"] - p["clip_ms"]))
        # tap labelling: labelled GT taps should yield an event at the tap time with matching type; unlabelled -> marker
        gtaps = json.loads((gt / f"{gt_id(uid)}.taps.json").read_text())["taps"] if (gt / f"{gt_id(uid)}.taps.json").exists() else []
        for t in gtaps:
            near = [e for e in pe if abs(e.get("clip_ms", -1e9) - t["clip_ms"]) <= 400]
            if t["labelled"]:
                tap_lab[1] += 1
                want = {e["type"] for e in ge if e.get("tap_id") == t["id"]}
                if any(e.get("type") in want and e.get("source") == "tap+heard" for e in near):
                    tap_lab[0] += 1
            else:
                tap_unl[1] += 1
                if any(e.get("type") == "marker" for e in near) and not any(e.get("type") != "marker" for e in near):
                    tap_unl[0] += 1
    if not C:
        return None
    pr = {}
    for k, (tp, np_, ng) in sorted(C.items()):
        p = tp / np_ if np_ else None; r = tp / ng if ng else None
        f1 = (2 * p * r / (p + r)) if p and r else (0.0 if (p is not None and r is not None) else None)
        pr[k] = dict(tp=tp, pred=np_, gt=ng, precision=p, recall=r, f1=f1)
    q = lambda xs, f: (sorted(xs)[min(len(xs) - 1, int(f * len(xs)))] if xs else None)
    return dict(fields=pr, unsupported_field_rate=(unsupported / pred_fields) if pred_fields else 0.0, unsupported=unsupported, pred_fields=pred_fields,
                unsupported_examples=unsup_examples[:25], unsupported_inferred=inferred_n[0],
                unsupported_field_rate_excl_flagged_inferred=((unsupported - inferred_n[0]) / pred_fields) if pred_fields else 0.0, timestamp_error_ms=dict(median=statistics.median(ts_err) if ts_err else None, p90=q(ts_err, 0.9), n=len(ts_err)),
                tap_labelling=dict(labelled_correct=tap_lab[0], labelled_total=tap_lab[1], unlabelled_correct=tap_unl[0], unlabelled_total=tap_unl[1],
                                   accuracy=(tap_lab[0] + tap_unl[0]) / max(1, tap_lab[1] + tap_unl[1])))


def _value_in_quote(k, v, q, e):
    v = str(v)
    if k == "drug":
        return any(canon_drug(term) == canon_drug(v) for term in _ngrams(q)) or tn.normalize(v) in q
    if k == "dose" or (k == "value"):
        if e.get("type") == "vital" and "/" in v:
            a, b = v.split("/"); return a in q.split() and b in q.split()
        return tn.normalize(v) in q.split()
    if k == "unit":
        u = norm_unit(v)
        return any(x in q.split() for x in {"mg": ["mg"], "mcg": ["mcg"], "g": ["g"], "ml": ["ml"], "l": ["l"], "l/min": ["l", "lpm"], "units": ["units"], "meq": ["meq"]}.get(u, [u]))
    if k == "route":
        al = {tn.normalize(v)} | {tn.normalize(a) for a in DICT["routes"].get(v, [])} | {tn.normalize(x) for x in ROUTE_EXTRA.get(v.upper(), [])}
        return any(a and re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", q) for a in al)
    return True


ROUTE_EXTRA = {"PO": ["chewed", "by mouth"], "SL": ["under the tongue", "sublingual"], "NEB": ["neb", "nebulizer", "nebulized"], "IN": ["intranasal", "nasal"],
               "NRB": ["non rebreather", "nrb"], "IV": ["iv"], "IM": ["im"], "IO": ["io"]}


def _window(hyp, q, w=60):
    i = hyp.find(q)
    return hyp[max(0, i - w): i + len(q) + w] if i >= 0 else q


def _ngrams(q, n=3):
    t = q.split()
    return [" ".join(t[i:j]) for i in range(len(t)) for j in range(i + 1, min(len(t), i + n) + 1)]


def _match(G, P, eq, tol):
    used = set(); pairs = []
    for g in sorted(G, key=lambda e: e.get("clip_ms", 0)):
        best = None
        for j, p in enumerate(P):
            if j in used or not eq(g, p):
                continue
            d = abs(g.get("clip_ms", 0) - p.get("clip_ms", 0))
            if d <= tol and (best is None or d < best[0]):
                best = (d, j)
        if best:
            used.add(best[1]); pairs.append((g, P[best[1]]))
    return pairs


# ------------------------------------------------------------------ taps
def taps(gt, run, ids, tol_ms=300):
    S = collections.defaultdict(lambda: [0, 0, 0])
    any_ = False
    for uid in ids:
        p = run / f"{uid}.taps_detected.json"
        if not p.exists():
            continue
        any_ = True
        det = json.loads(p.read_text())["taps"]
        g = [t for t in json.loads((gt / f"{gt_id(uid)}.taps.json").read_text())["taps"] if t["source"] in ("knock", "snap")]
        for src in ("knock", "snap"):
            G = [t for t in g if t["source"] == src]; D_ = [t for t in det if t["source"] == src]
            used = set(); tp = 0
            for t in G:
                for j, d in enumerate(D_):
                    if j not in used and abs(d["clip_ms"] - t["clip_ms"]) <= tol_ms:
                        used.add(j); tp += 1; break
            S[src][0] += tp; S[src][1] += len(D_); S[src][2] += len(G)
    if not any_:
        return None
    return {k: dict(tp=v[0], detected=v[1], gt=v[2], precision=v[0] / v[1] if v[1] else None, recall=v[0] / v[2] if v[2] else None) for k, v in S.items()}


def noise_false_taps(noise_run):
    n = 0; secs = 0
    for p in pathlib.Path(noise_run).glob("*.taps_detected.json"):
        j = json.loads(p.read_text()); n += len(j["taps"]); secs += j.get("duration_s", 0)
    return dict(false_taps=n, minutes=secs / 60, per_10_min=(n / (secs / 600)) if secs else None) if secs else None


# ------------------------------------------------------------------ outputs
def outputs(gt, run, ids):
    res = collections.defaultdict(lambda: [0, 0]); xml_ok = [0, 0]; diag_leaks = []
    any_ = False
    for uid in ids:
        od = run / f"{uid}.outputs"
        if not od.exists():
            continue
        any_ = True
        ex = json.loads((gt / f"{gt_id(uid)}.expected.json").read_text())
        texts = {p.stem.split(".")[0].lower(): p.read_text(errors="ignore") for p in od.iterdir() if p.is_file()}
        for fmt in ("soap", "chart", "imist", "nemsis"):
            t = next((v for k, v in texts.items() if k.startswith(fmt)), None)
            if t is None:
                continue
            nt = tn.normalize(t)
            keys = []
            for m in ex["medications"]:
                keys.append(tn.normalize(m["drug"]).split()[0]); keys.append(tn.normalize(m.get("dose", "")))
            for v in ex["vitals"]:
                keys += [tn.normalize(x) for x in str(v["value"]).split("/")]
            if fmt == "nemsis":
                keys += [hms for hms in ex["nemsis_etimes"].values()]
                nt = t
            hit = sum(1 for k in keys if k and (k in nt))
            res[fmt][0] += hit; res[fmt][1] += len(keys)
            for trap in ex.get("diagnosis_traps", []):
                if tn.normalize(trap) and re.search(rf"\b{re.escape(tn.normalize(trap))}\b", tn.normalize(t)):
                    diag_leaks.append((uid, fmt, trap))
        if (od / "nemsis.xml").exists():
            xml_ok[1] += 1
            ok = validate_nemsis(od / "nemsis.xml")
            xml_ok[0] += bool(ok)
    if not any_:
        return None
    return dict(key_field_match={k: v[0] / v[1] if v[1] else None for k, v in res.items()}, nemsis_schema_valid=f"{xml_ok[0]}/{xml_ok[1]}", diagnosis_leaks=diag_leaks)


def validate_nemsis(p):
    xsd = pathlib.Path(__file__).resolve().parent / "nemsis_xsd" / "EMSDataSet_v3.xsd"
    if not xsd.exists():
        return None
    try:
        import xmlschema
        return xmlschema.XMLSchema(str(xsd)).is_valid(str(p))
    except Exception:
        return False


def speed(run):
    p = run / "timing.jsonl"
    if not p.exists():
        return None
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    a = sum(r["audio_s"] for r in rows); w = sum(r["wall_s"] for r in rows)
    st = collections.defaultdict(float)
    for r in rows:
        for k, v in (r.get("stages") or {}).items():
            st[k] += v
    return dict(audio_s=a, wall_s=w, rtf=w / a if a else None, stages_s=dict(st) or None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True); ap.add_argument("--run", required=True)
    ap.add_argument("--noise-run"); ap.add_argument("--json"); ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    global GT_DIR
    gt, run = pathlib.Path(a.gt), pathlib.Path(a.run); GT_DIR = gt
    ids = sorted({p.name.split(".hyp.txt")[0] for p in run.glob("*.hyp.txt")} | {p.name.split(".events.jsonl")[0] for p in run.glob("*.events.jsonl")})
    ids = [i for i in ids if (gt / f"{gt_id(i)}.transcript.txt").exists()]
    res = dict(run=str(run), gt=str(gt), n=len(ids), transcription=transcription(gt, run, ids), extraction=extraction(gt, run, ids),
               taps=taps(gt, run, ids), outputs=outputs(gt, run, ids), speed=speed(run))
    if a.noise_run:
        res["noise_false_taps"] = noise_false_taps(a.noise_run)
    if a.json:
        pathlib.Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.json).write_text(json.dumps(res, indent=1, default=str))
    if not a.quiet:
        t = res["transcription"]
        if t:
            print(f"WER {t['wer']:.3f}  drugWER {t['drug_wer']:.3f} ({t['drug_tokens']} tok)  num acc {t['number_acc']:.3f}  unit acc {t['unit_acc']:.3f}  jargon recall {t['jargon_recall']:.3f}")
        e = res["extraction"]
        if e:
            for k, v in e["fields"].items():
                print(f"  {k:14s} P={_f(v['precision'])} R={_f(v['recall'])} F1={_f(v['f1'])}  (tp {v['tp']} / pred {v['pred']} / gt {v['gt']})")
            print("  unsupported-field rate", round(e["unsupported_field_rate"], 4), " ts err", e["timestamp_error_ms"], " tap labelling", e["tap_labelling"])
        if res["taps"]: print("  taps", res["taps"])
        if res["speed"]: print("  speed", res["speed"])
    return res


def _f(x):
    return "  - " if x is None else f"{x:.2f}"


if __name__ == "__main__":
    main()
