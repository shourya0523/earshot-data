#!/usr/bin/env python3
"""Model benchmark table -> eval/BENCHMARK.md (+ eval/results/benchmark.json).
Per model x set: WER, drug-name WER, number acc, jargon recall, false drug insertions per 1k ref words, RTF.
  python3 eval/bench_report.py"""
import json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score, textnorm as tn, jiwer

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODELS = [("stock_small", "whisper small.en (stock)", "244M"), ("emsassist_small", "EMSAssist small.en v2", "244M"),
          ("emsassist_base", "EMSAssist base.en v3", "74M"), ("stock_base", "whisper base.en (stock)", "74M"), ("medical_v1", "Whisper-Medicalv1 (distil-large-v3)", "756M")]
SETS = [("test_tts_snr10", "Test calls, TTS + noise 10 dB", "synthetic", ROOT / "data/scripts/test/gt/tts"),
        ("real_test_emsctx", "EMSContExt (EMS narratives, read)", "real", ROOT / "data/scripts/real/gt/emsctx"),
        ("real_test_eka", "Eka (clinician, Indian English)", "real", ROOT / "data/scripts/real/gt/eka"),
        ("real_test_primock", "PriMock57 (GP consults, UK)", "real", ROOT / "data/scripts/real/gt/primock"),
        ("real_test_medintent", "MedIntent (symptom phrases)", "real", ROOT / "data/scripts/real/gt/medintent")]


def run_dir(model, set_):
    if model == "stock_small" and set_ == "test_tts_snr10":
        return ROOT / "eval/runs/stock_small_pp/test_tts_snr10"
    return ROOT / "eval/runs" / model / set_


def false_drugs(run, gt, ids):
    ins = 0; words = 0
    for uid in ids:
        ref = tn.normalize((gt / f"{score.gt_id(uid)}.transcript.txt").read_text()); hyp = tn.normalize((run / f"{uid}.hyp.txt").read_text())
        rset = set(ref.split()); words += len(ref.split())
        ins += sum(1 for t in hyp.split() if t in score.DRUGS and t not in rset)
    return 1000 * ins / max(1, words)


def main():
    res = {}
    for m, _, _ in MODELS:
        for s, _, _, gt in SETS:
            run = run_dir(m, s)
            if not run.exists(): continue
            score.GT_DIR = gt
            ids = [p.name.split(".hyp.txt")[0] for p in run.glob("*.hyp.txt") if (gt / f"{score.gt_id(p.name.split('.hyp.txt')[0])}.transcript.txt").exists()]
            if not ids: continue
            t = score.transcription(gt, run, ids); sp = score.speed(run) or {}
            res[f"{m}/{s}"] = dict(n=len(ids), wer=t["wer"], drug_wer=t["drug_wer"], drug_tokens=t["drug_tokens"], number_acc=t["number_acc"],
                                   jargon_recall=t["jargon_recall"], false_drug_per_1k=false_drugs(run, gt, ids), rtf=sp.get("rtf"), audio_min=(sp.get("audio_s") or 0) / 60)
    (ROOT / "eval/results").mkdir(exist_ok=True)
    (ROOT / "eval/results/benchmark.json").write_text(json.dumps(res, indent=1))
    pct = lambda x: "–" if x is None else f"{100*x:.1f}%"
    L = ["# ASR model benchmark (existing open models, no fine-tuning)", "",
         "All runs use whisper.cpp (beam 5) with the **pipeline's exact initial prompt** (`eval/pipeline_prompt.txt`) and the same EMS-aware text normalisation (`eval/textnorm.py`).",
         "Drug-name WER counts errors on reference tokens that are drug names (dictionary + Eka's labelled drug spans).",
         "False drugs = drug-name tokens in the output that aren't in the reference, per 1,000 reference words (lower is better).",
         "RTF = processing time / audio duration on 4 x86 CPU threads in this container. Ratios are comparable between models; the absolute speed is not the iPad's.", ""]
    for s, title, typ, _ in SETS:
        L += [f"## {title} ({typ})", "", "| Model | Size | Files | WER | Drug-name WER (tokens) | Number acc | Jargon recall | False drugs /1k words | RTF |", "|---|---|---|---|---|---|---|---|---|"]
        for m, name, size in MODELS:
            r = res.get(f"{m}/{s}")
            if not r: L.append(f"| {name} | {size} | (not run) | | | | | | |"); continue
            L.append(f"| {name} | {size} | {r['n']} | {pct(r['wer'])} | {pct(r['drug_wer'])} ({r['drug_tokens']}) | {pct(r['number_acc'])} | {pct(r['jargon_recall'])} | {r['false_drug_per_1k']:.1f} | {r['rtf']:.2f} |" if r['rtf'] else
                     f"| {name} | {size} | {r['n']} | {pct(r['wer'])} | {pct(r['drug_wer'])} ({r['drug_tokens']}) | {pct(r['number_acc'])} | {pct(r['jargon_recall'])} | {r['false_drug_per_1k']:.1f} | – |")
        L.append("")
    # pooled real
    L += ["## Pooled: all real test sets", "", "| Model | WER (mean of sets) | Drug-name WER (mean of sets with ≥10 drug tokens) |", "|---|---|---|"]
    for m, name, _ in MODELS:
        rs = [res[f"{m}/{s}"] for s, _, t, _ in SETS if t == "real" and f"{m}/{s}" in res]
        if not rs: continue
        d = [r["drug_wer"] for r in rs if r["drug_tokens"] >= 10]
        L.append(f"| {name} | {pct(sum(r['wer'] for r in rs)/len(rs))} | {pct(sum(d)/len(d)) if d else '–'} |")
    (ROOT / "eval/BENCHMARK.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
