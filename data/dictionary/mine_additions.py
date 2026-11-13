#!/usr/bin/env python3
"""Propose additions to the pipeline's shared/formulary.json (its schema), from data the data agent collected:
  1. ASR variants: drug tokens that stock whisper small.en got wrong in our runs (ref -> hyp substitutions).
  2. Drugs / aliases in the data-agent seed (data/dictionary/ems_seed.json) that the pipeline formulary lacks.
  3. Drug mentions in real transcripts (Eka spans, EMSContExt, YouTube EMS captions) missing from the formulary.
  python3 data/dictionary/mine_additions.py --formulary /home/user/pipeline/shared/formulary.json \
      --runs eval/runs/stock_small/test_tts_snr10 ... --gt data/scripts/test/gt/tts ...
Output: data/dictionary/formulary_additions.json  (merge = append to the listed arrays; no edits to existing values)"""
import argparse, collections, glob, json, pathlib, re, sys
import jiwer
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval")); import textnorm as tn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--formulary", default="/home/user/pipeline/shared/formulary.json")
    ap.add_argument("--pairs", nargs="*", default=[], help="run_dir=gt_dir pairs")
    a = ap.parse_args()
    F = json.loads(pathlib.Path(a.formulary).read_text())
    known = {}
    for d in F["drugs"]:
        for n in [d["generic"], *d.get("brands", []), *d.get("aliases", []), *d.get("slang", []), *d.get("asr_variants", [])]:
            known[tn.normalize(n)] = d["generic"]
    seed = tn.dictionary()
    seed_canon = {}
    for x in seed["drugs"]:
        for n in [x["name"], x["generic"], *x["brands"], *x["aliases"]]:
            seed_canon[tn.normalize(n)] = x
    def generic_of(tok):
        if tok in known: return known[tok]
        x = seed_canon.get(tok)
        if x:
            for n in [x["generic"], x["name"], *x["brands"]]:
                if tn.normalize(n) in known: return known[tn.normalize(n)]
            return x["generic"]
        return None
    # 1. ASR variants from runs
    variants = collections.defaultdict(collections.Counter)
    for pair in a.pairs:
        run, gt = pair.split("=")
        for hp in glob.glob(f"{run}/*.hyp.txt"):
            uid = pathlib.Path(hp).name.split(".hyp.txt")[0]
            gid = uid if pathlib.Path(gt, f"{uid}.transcript.txt").exists() else uid.split(".")[0]
            rp = pathlib.Path(gt, f"{gid}.transcript.txt")
            if not rp.exists(): continue
            ref = tn.normalize(rp.read_text()); hyp = tn.normalize(open(hp).read())
            r = ref.split(); h = hyp.split()
            for ch in jiwer.process_words(ref, hyp).alignments[0]:
                if ch.type != "substitute": continue
                for k in range(ch.ref_end_idx - ch.ref_start_idx):
                    rt = r[ch.ref_start_idx + k]; ht = h[ch.hyp_start_idx + k] if ch.hyp_start_idx + k < ch.hyp_end_idx else None
                    g = generic_of(rt)
                    if g and ht and ht != rt and len(ht) > 2 and ht not in known:
                        variants[g][ht] += 1
    # 2. seed drugs / aliases missing from pipeline formulary
    missing_drugs, missing_alias = [], collections.defaultdict(set)
    for x in seed["drugs"]:
        names = [x["name"], x["generic"], *x["brands"], *x["aliases"], *x.get("asr_variants", [])]
        g = next((known[tn.normalize(n)] for n in names if tn.normalize(n) in known), None)
        if g is None:
            missing_drugs.append(dict(generic=x["generic"], brands=x["brands"], aliases=x["aliases"], asr_variants=x.get("asr_variants", []),
                                      **{"class": x["drug_class"]}, routes=x["routes"], typical_doses=[dict(amount=d, unit=x["units"][0]) for d in x["typical_doses"]],
                                      source="data-agent seed (NASEMSO model guidelines drug list)"))
        else:
            for n in names:
                if tn.normalize(n) not in known and len(n) > 2:
                    missing_alias[g].add(n.lower())
    # 3. real-transcript drug mentions (Eka spans) not in formulary
    unknown_real = collections.Counter()
    for p in glob.glob(str(ROOT / "data/scripts/real/gt/eka/*.drug_terms.json")):
        for t in json.load(open(p)):
            n = tn.normalize(t)
            n = re.sub(r"\b\d+(\.\d+)? ?(mg|mcg|g|ml|units)?\b", "", n).strip()
            if n and len(n) > 3 and n not in known and not any(w in known for w in n.split()):
                unknown_real[n] += 1
    home = [m for m in seed.get("home_meds", []) if tn.normalize(m) not in known]
    out = dict(
        note="Proposed additions for shared/formulary.json (pipeline schema). Append-only: add asr_variants/aliases to existing drugs; new_drugs are absent entirely. Evidence counts = times stock whisper small.en produced the variant on our test/dev audio.",
        asr_variants_observed={g: [dict(variant=v, count=c) for v, c in cnt.most_common()] for g, cnt in sorted(variants.items())},
        aliases_missing={g: sorted(v) for g, v in sorted(missing_alias.items())},
        new_drugs=missing_drugs,
        home_meds_missing=home,
        real_transcript_drug_terms_unknown=[dict(term=t, count=c) for t, c in unknown_real.most_common(60)],
    )
    p = ROOT / "data/dictionary/formulary_additions.json"
    p.write_text(json.dumps(out, indent=1))
    print("variants for", len(variants), "drugs;", sum(len(v) for v in missing_alias.values()), "aliases;", len(missing_drugs), "new drugs;", len(home), "home meds;",
          len(unknown_real), "unknown real terms ->", p)


if __name__ == "__main__":
    main()
