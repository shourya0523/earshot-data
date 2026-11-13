#!/usr/bin/env python3
"""Run whisper.cpp (whisper-cli) over a list of wavs with the EMS initial prompt from shared/formulary.json.
Writes <out>/<id>.hyp.txt, <id>.whisper.json and <out>/timing.jsonl (audio seconds, wall seconds, RTF).
  python3 eval/run_asr.py --model data/raw/models/ggml-small.en.bin --out eval/runs/stock_small/test_tts \
      --wav data/audio/test/tts/c01.snr10.wav ...    (or --list file.txt with "id<TAB>path" lines)"""
import argparse, json, os, pathlib, subprocess, sys, time
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parents[1]


def prompt_text(kind):
    if kind == "none":
        return None
    d = json.loads((ROOT / "data" / "dictionary" / "ems_seed.json").read_text())
    return d.get("initial_prompt") or d.get("prompt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "data/raw/models/ggml-small.en.bin"))
    ap.add_argument("--cli", default=str(ROOT / ".tools/whisper-cli"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--wav", nargs="*", default=[])
    ap.add_argument("--list")
    ap.add_argument("--prompt", default="ems", choices=["ems", "none"])
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--beam", type=int, default=5)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    items = [(pathlib.Path(w).name.split(".")[0], w) for w in a.wav]
    if a.list:
        items += [tuple(l.split("\t")[:2]) for l in open(a.list).read().splitlines() if l.strip()]
    pr = prompt_text(a.prompt)
    tim = open(out / "timing.jsonl", "a")
    for uid, wav in items:
        if (out / f"{uid}.hyp.txt").exists():
            continue
        info = sf.info(wav)
        cmd = [a.cli, "-m", a.model, "-f", wav, "-t", str(a.threads), "-bs", str(a.beam), "-oj", "-of", str(out / f"{uid}.whisper"), "-np"]
        if pr:
            cmd += ["--prompt", pr]
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        el = time.time() - t
        if r.returncode != 0:
            print("FAIL", uid, r.stderr[-500:], file=sys.stderr); continue
        j = json.load(open(out / f"{uid}.whisper.json"))
        segs = [dict(start_ms=s["offsets"]["from"], end_ms=s["offsets"]["to"], text=s["text"].strip()) for s in j["transcription"]]
        (out / f"{uid}.segments.json").write_text(json.dumps(segs, indent=0))
        (out / f"{uid}.hyp.txt").write_text(" ".join(s["text"] for s in segs).strip() + "\n")
        tim.write(json.dumps(dict(id=uid, audio_s=info.duration, wall_s=round(el, 2), rtf=round(el / max(info.duration, 1e-3), 3),
                                  model=pathlib.Path(a.model).name, prompt=a.prompt)) + "\n"); tim.flush()
        print(uid, f"{info.duration:.1f}s audio in {el:.1f}s", flush=True)


if __name__ == "__main__":
    main()
