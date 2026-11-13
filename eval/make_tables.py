#!/usr/bin/env python3
"""Score every run directory listed below and print markdown tables (used for eval/BASELINE.md and eval/REPORT.md).
  python3 eval/make_tables.py --runs eval/runs/stock_small --gt-test data/scripts/test/gt/tts --gt-real data/scripts/real/gt > /tmp/t.md"""
import argparse, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score

ROOT = pathlib.Path(__file__).resolve().parents[1]


def score_dir(run, gt):
    score.GT_DIR = pathlib.Path(gt)
    ids = sorted({p.name.split(".hyp.txt")[0] for p in run.glob("*.hyp.txt")} | {p.name.split(".events.jsonl")[0] for p in run.glob("*.events.jsonl")})
    ids = [i for i in ids if (score.GT_DIR / f"{score.gt_id(i)}.transcript.txt").exists()]
    if not ids: return None
    return dict(n=len(ids), transcription=score.transcription(score.GT_DIR, run, ids), extraction=score.extraction(score.GT_DIR, run, ids),
                taps=score.taps(score.GT_DIR, run, ids), outputs=score.outputs(score.GT_DIR, run, ids), speed=score.speed(run))


def f(x, pct=True):
    return "–" if x is None else (f"{100*x:.1f}%" if pct else f"{x:.2f}")


def asr_table(rows):
    out = ["| Set | Type | Files | Audio (min) | WER | Drug-name WER (drug tokens) | Number acc | Unit acc | Jargon recall | RTF |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, typ, r in rows:
        t = r["transcription"]; s = r.get("speed") or {}
        out.append(f"| {name} | {typ} | {t['n_files']} | {s.get('audio_s', 0)/60:.1f} | {f(t['wer'])} | {f(t['drug_wer'])} ({t['drug_tokens']}) | {f(t['number_acc'])} ({t['number_tokens']}) | {f(t['unit_acc'])} | {f(t['jargon_recall'])} ({t['jargon_terms']}) | {f(s.get('rtf'), False)} |")
    return "\n".join(out)


def ext_table(rows, fields=("drug", "dose", "unit", "route", "vital.bp", "vital.hr", "vital.rr", "vital.spo2", "vital.bgl", "vital.gcs", "vital.pain", "procedure", "status")):
    out = ["| Run | " + " | ".join(fields) + " | Unsupported-field rate | Tap labelling acc | Timestamp err median / p90 (s) |", "|---" * (len(fields) + 4) + "|"]
    for name, r in rows:
        e = r["extraction"]
        if not e: continue
        cells = []
        for k in fields:
            v = e["fields"].get(k)
            cells.append("–" if not v else f"P {f(v['precision'], False)} / R {f(v['recall'], False)}")
        ts = e["timestamp_error_ms"]
        out.append(f"| {name} | " + " | ".join(cells) + f" | {f(e['unsupported_field_rate'])} ({e['unsupported']}/{e['pred_fields']}) | {f(e['tap_labelling']['accuracy'])} | "
                   + (f"{ts['median']/1000:.1f} / {ts['p90']/1000:.1f}" if ts["median"] is not None else "–") + " |")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--json-out"); a = ap.parse_args()
    res = {}
    for run in sorted((ROOT / "eval/runs").glob("*/*")):
        if not run.is_dir() or run.name == "raw": continue
        if run.name.startswith("test_tts"): gt = ROOT / "data/scripts/test/gt/tts"
        elif run.name.startswith("real_"): gt = ROOT / "data/scripts/real/gt" / run.name.split("_", 2)[2]
        elif run.name.startswith("dev_synth"): gt = ROOT / "data/scripts/dev_synth/gt"
        elif run.name.startswith("test_team"): gt = ROOT / "data/scripts/test/gt/team"
        else: continue
        r = score_dir(run, gt)
        if r: res[f"{run.parent.name}/{run.name}"] = r
    if a.json_out:
        pathlib.Path(a.json_out).write_text(json.dumps(res, indent=1, default=str))
    print("\n".join(sorted(res)))
