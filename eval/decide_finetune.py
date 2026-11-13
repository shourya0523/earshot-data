#!/usr/bin/env python3
"""Phase 5 gate for Whisper: fine-tune if drug-name WER > 15% or overall WER > 20% on the real (+team, when present) test sets.
Uses eval/results/benchmark.json (stock small.en, pipeline prompt). Prints FAIL/PASS and appends the decision to data/DECISIONS.md."""
import json, pathlib, datetime
ROOT = pathlib.Path(__file__).resolve().parents[1]
b = json.loads((ROOT / "eval/results/benchmark.json").read_text())
real = {k: v for k, v in b.items() if k.startswith("stock_small/real_test_")}
team = {k: v for k, v in b.items() if k.startswith("stock_small/test_team")}
sets = {**real, **team}
words = sum(v["n"] for v in sets.values())
wer = sum(v["wer"] for v in sets.values()) / max(1, len(sets))
dsets = {k: v for k, v in sets.items() if v["drug_tokens"] >= 10}
dwer = sum(v["drug_wer"] * v["drug_tokens"] for v in dsets.values()) / max(1, sum(v["drug_tokens"] for v in dsets.values()))
tts = b.get("stock_small/test_tts_snr10", {})
fail = dwer > 0.15 or wer > 0.20
msg = (f"stock small.en on real{'+team' if team else ''} test sets: mean WER {wer:.1%}, drug-name WER {dwer:.1%} "
       f"(token-weighted over {', '.join(k.split('/')[1] for k in dsets)}); TTS test calls: WER {tts.get('wer', 0):.1%}, drug WER {tts.get('drug_wer', 0):.1%}. "
       f"Threshold drug WER > 15% or WER > 20% -> {'FAIL: fine-tune Whisper small.en' if fail else 'PASS: keep stock'}")
ts = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")
with open(ROOT / "data/DECISIONS.md", "a") as f:
    f.write(f"| {ts} | Phase 5 gate (Whisper): {msg} | `eval/decide_finetune.py`, `eval/BENCHMARK.md` |\n")
print("FAIL" if fail else "PASS"); print(msg)
