#!/usr/bin/env python3
"""Ship gate for a fine-tuned Whisper (owner's rules, docs/PROMPT_PRIMING.md on the pipeline branch).

Inputs: score.py JSONs for stock and fine-tuned, each with NO prompt and with the format-only prompt
(eval/ab_prompt.sh produces them). Ship only if ALL hold:
  1. no prompt: fine-tuned beats stock (drug-name WER lower, overall WER not higher)
  2. format-only prompt: fine-tuned is not worse than stock (WER and drug-name WER not higher)
  3. fine-tuned has 0 prompt copies in both runs
Prints SHIP / DON'T SHIP with the reasons, appends the decision to data/DECISIONS.md, exits 0 only on SHIP.

  python3 eval/decide_ship.py --stock-noprompt A.json --ft-noprompt B.json --stock-format C.json --ft-format D.json
"""
import argparse, datetime, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOL = 0.005   # half a WER point counts as "not worse"


def load(p):
    j = json.loads(pathlib.Path(p).read_text())
    t = j["transcription"]
    return dict(wer=t["wer"], dwer=t["drug_wer"], copies=(j.get("prompt_copy") or {}).get("prompt_copies"))


def main():
    ap = argparse.ArgumentParser()
    for k in ("stock-noprompt", "ft-noprompt", "stock-format", "ft-format"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--model", default="models/whisper-ems-small.en-q5.bin")
    a = ap.parse_args()
    sn, fn, sf, ff = (load(getattr(a, k)) for k in ("stock_noprompt", "ft_noprompt", "stock_format", "ft_format"))
    checks = []
    checks.append(("beats stock with no prompt",
                   fn["dwer"] < sn["dwer"] and fn["wer"] <= sn["wer"] + TOL,
                   f"drug WER {fn['dwer']:.1%} vs {sn['dwer']:.1%}, WER {fn['wer']:.1%} vs {sn['wer']:.1%}"))
    checks.append(("not worse with format-only prompt",
                   ff["dwer"] <= sf["dwer"] + TOL and ff["wer"] <= sf["wer"] + TOL,
                   f"drug WER {ff['dwer']:.1%} vs {sf['dwer']:.1%}, WER {ff['wer']:.1%} vs {sf['wer']:.1%}"))
    copies = [c for c in (fn["copies"], ff["copies"])]
    checks.append(("0 prompt copies (fine-tuned, both runs)",
                   all(c == 0 for c in copies), f"copies no-prompt={copies[0]}, format={copies[1]} (scorer must include prompt_copy)"))
    ship = all(ok for _, ok, _ in checks)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    verdict = "SHIP" if ship else "DON'T SHIP"
    print(verdict)
    ts = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")
    summary = "; ".join(f"{n}: {'pass' if ok else 'FAIL'} ({d})" for n, ok, d in checks)
    with open(ROOT / "data/DECISIONS.md", "a") as f:
        f.write(f"| {ts} | Ship gate (fine-tuned Whisper `{a.model}`): **{verdict}**. {summary} | `eval/decide_ship.py`, `eval/ab_prompt.sh` |\n")
    sys.exit(0 if ship else 1)


if __name__ == "__main__":
    main()
