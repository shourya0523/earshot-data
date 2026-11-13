#!/usr/bin/env python3
"""Home-medication dictionary, data-driven: RxNorm display names (RxNav) matched against real clinical conversation
text (MTS-Dialog, ACI-Bench dialogues + notes, PriMock57/Eka/EMSContExt transcripts, YouTube EMS captions, ADE drugs).
Ranks by mention count, resolves each to its RxNorm ingredient + rxcui via RxNav, and writes
data/dictionary/home_meds.json  ([{name, generic, rxcui, tty, mentions, sources}]).
  python3 -I data/dictionary/build_home_meds.py"""
import collections, glob, json, pathlib, re, time, urllib.parse, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
STOP = set("""water oxygen sodium potassium calcium magnesium iron zinc sugar glucose salt alcohol caffeine nicotine air light lead iodine
sulfur carbon gold silver copper tin protein vitamin today time pain blood stone milk coffee tea honey nitrogen amber balance rest care plan
test cold heat fever chill cough flu""".split())


def corpus():
    T = collections.defaultdict(list)
    import pyarrow.parquet as pq, csv
    for r in csv.DictReader(open(RAW / "text/mts_dialog_train.csv", encoding="utf-8")):
        T["MTS-Dialog"].append(r["dialogue"] + " " + r["section_text"])
    for f in glob.glob(str(RAW / "text/aci/*.parquet")):
        for r in pq.read_table(f).to_pylist():
            T["ACI-Bench"].append((r.get("dialogue") or "") + " " + (r.get("note") or ""))
    for r in pq.read_table(RAW / "text/ade_drug_dosage.parquet").to_pylist():
        T["ADE"].append(r["text"])
    for src in ["primock", "eka", "emsctx", "medintent"]:
        for p in glob.glob(str(ROOT / f"data/scripts/real/gt/{src}/*.transcript.txt")):
            T[src].append(open(p).read())
    for p in glob.glob(str(RAW / "youtube_captions/*.en.vtt")):
        txt = re.sub(r"<[^>]+>|\d\d:\d\d:\d\d\.\d+ --> .*|WEBVTT.*|Kind:.*|Language:.*", " ", open(p, errors="ignore").read())
        T["YouTube EMS captions"].append(txt)
    return T


def rxnav(path):
    url = "https://rxnav.nlm.nih.gov/REST/" + path
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "earshot-data/0.1"}), timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(1 + i)
    return {}


def main():
    names = json.load(open(RAW / "rxnorm/displaynames.json"))["displayTermsList"]["term"]
    names = {n.lower() for n in names if 4 <= len(n) <= 30 and re.fullmatch(r"[a-z][a-z \-]+", n.lower()) and n.lower() not in STOP and len(n.split()) <= 2}
    T = corpus()
    cnt = collections.Counter(); srcs = collections.defaultdict(set)
    for src, docs in T.items():
        for d in docs:
            toks = re.findall(r"[a-z][a-z\-]+", d.lower())
            grams = set(toks) | {" ".join(toks[i:i + 2]) for i in range(len(toks) - 1)}
            for g in grams & names:
                cnt[g] += 1; srcs[g].add(src)
    # drop generic English words that happen to be RxNorm names (must look drug-like or be rare in plain English)
    eng = set()
    try:
        eng = {w.strip().lower() for w in open("/usr/share/dict/words")}
    except Exception:
        pass
    cand = [(g, c) for g, c in cnt.most_common() if c >= 2 and (g not in eng)][:500]
    out = []
    for g, c in cand:
        j = rxnav(f"rxcui.json?name={urllib.parse.quote(g)}&search=1")
        ids = (j.get("idGroup") or {}).get("rxnormId") or []
        if not ids:
            continue
        rx = ids[0]
        p = rxnav(f"rxcui/{rx}/properties.json").get("properties") or {}
        tty = p.get("tty")
        if tty not in ("IN", "BN", "PIN", "MIN"):
            continue
        generic = p.get("name", g).lower()
        if tty == "BN":
            rel = rxnav(f"rxcui/{rx}/related.json?tty=IN")
            grp = [x for x in (rel.get("relatedGroup") or {}).get("conceptGroup", []) if x.get("conceptProperties")]
            if grp:
                generic = grp[0]["conceptProperties"][0]["name"].lower()
        out.append(dict(name=g, generic=generic, rxcui=rx, tty=tty, mentions=c, sources=sorted(srcs[g])))
        time.sleep(0.06)
    p = ROOT / "data/dictionary/home_meds.json"
    p.write_text(json.dumps(dict(note="Medications mentioned in real clinical conversation/EMS text, resolved via RxNav (RxNorm). For history/home-med recognition and ASR prompt candidates; NOT EMS-administered drugs.",
                                 source="RxNav displaynames + rxcui lookup, 2026-11-13", items=out), indent=1))
    print(len(out), "meds ->", p); print([o["name"] for o in out[:60]])


if __name__ == "__main__":
    main()
