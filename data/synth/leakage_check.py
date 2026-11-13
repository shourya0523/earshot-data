#!/usr/bin/env python3
"""Prove test scripts (and paraphrases) are not in training material.
Checks every training/dev text source against the 10 test scripts:
  1. exact line matches (normalised)            -> must be 0
  2. shared word 6-grams (normalised)           -> listed; must be 0 for synthetic scripts
  3. per-line max token Jaccard vs any test line -> lines >= 0.6 flagged as possible paraphrases
Writes data/manifests/leakage_report.json and exits 1 on failure."""
import json, pathlib, sys, re
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval")); sys.path.insert(0, str(ROOT / "data/synth"))
import textnorm as tn, calldsl


def lines_of_call(p):
    c = calldsl.parse(p.read_text())
    return [it["text"] for it in c["items"] if it["kind"] == "speech"]


def ngrams(t, n=6):
    w = t.split(); return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


test_lines = [tn.normalize(l) for p in sorted((ROOT / "data/scripts/test").glob("*.call")) for l in lines_of_call(p)]
test_set = set(test_lines); test_ng = set().union(*[ngrams(l) for l in test_lines])
test_tok = [set(l.split()) for l in test_lines]
sources = {}
for d in ["train_synth", "dev_synth"]:
    sources[d] = [l for p in sorted((ROOT / "data/scripts" / d).glob("*.call")) for l in lines_of_call(p)]
tag = ROOT / "train/tagger/data/train.jsonl"
if tag.exists():
    sources["tagger_train"] = [json.loads(l)["text"] for l in tag.read_text().splitlines()]
rep = {}; fail = False
for name, L in sources.items():
    exact = [l for l in L if tn.normalize(l) in test_set]
    shared = sorted({g for l in L for g in ngrams(tn.normalize(l)) & test_ng})
    para = []
    for l in L:
        s = set(tn.normalize(l).split())
        if len(s) < 5: continue
        j = max((len(s & t) / len(s | t) for t in test_tok), default=0)
        if j >= 0.6: para.append((round(j, 2), l))
    rep[name] = dict(lines=len(L), exact_matches=len(exact), shared_6grams=len(shared), shared_examples=shared[:20], possible_paraphrases=len(para), paraphrase_examples=para[:10])
    if exact or (name.endswith("synth") and (shared or para)):
        fail = True
rep["verdict"] = "FAIL" if fail else "PASS"
(ROOT / "data/manifests").mkdir(exist_ok=True)
(ROOT / "data/manifests/leakage_report.json").write_text(json.dumps(rep, indent=1))
print(json.dumps({k: (v if k == "verdict" else {kk: vv for kk, vv in v.items() if not kk.endswith("examples")}) for k, v in rep.items()}, indent=1))
sys.exit(1 if fail else 0)
