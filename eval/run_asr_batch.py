#!/usr/bin/env python3
"""Batch ASR for many short real clips (model stays loaded; same whisper.cpp core via pywhispercpp).
  python3 eval/run_asr_batch.py --model data/raw/models/ggml-small.en.bin --out eval/runs/stock_small/real_dev \
     --items data/manifests/real_items.jsonl --split dev --cap 150
Writes <out>/<subset>/<id>.hyp.txt, <id>.segments.json, timing.jsonl."""
import argparse, json, pathlib, sys, time, random
import soundfile as sf
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from run_asr import prompt_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "data/raw/models/ggml-small.en.bin"))
    ap.add_argument("--out", required=True); ap.add_argument("--items", default=str(ROOT / "data/manifests/real_items.jsonl"))
    ap.add_argument("--split", default="dev"); ap.add_argument("--cap", type=int, default=150); ap.add_argument("--subsets", default="emsctx,eka,primock,medintent")
    ap.add_argument("--prompt", default="ems", choices=["ems", "none"]); ap.add_argument("--beam", type=int, default=5); ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    from pywhispercpp.model import Model
    kw = dict(n_threads=a.threads, print_progress=False, print_realtime=False, no_context=True, suppress_non_speech_tokens=False)
    pr = prompt_text(a.prompt)
    if pr: kw["initial_prompt"] = pr
    m = Model(a.model, params_sampling_strategy=1 if a.beam > 1 else 0, redirect_whispercpp_logs_to=None, **kw)
    if a.beam > 1:
        m._params.beam_search = {"beam_size": a.beam, "patience": -1.0}
    items = [json.loads(l) for l in open(a.items)]
    for sub in a.subsets.split(","):
        sel = sorted([i for i in items if i["subset"] == sub and i["split"] == a.split], key=lambda i: i["id"])
        random.Random(0).shuffle(sel); sel = sel[: a.cap]
        out = pathlib.Path(a.out) / sub; out.mkdir(parents=True, exist_ok=True)
        tim = open(out / "timing.jsonl", "a")
        for it in sel:
            uid = it["id"]
            if (out / f"{uid}.hyp.txt").exists():
                continue
            wav = ROOT / "data/audio/real" / sub / f"{uid}.wav"
            dur = sf.info(wav).duration
            t = time.time()
            segs = m.transcribe(str(wav))
            el = time.time() - t
            S = [dict(start_ms=s.t0 * 10, end_ms=s.t1 * 10, text=s.text.strip()) for s in segs]
            (out / f"{uid}.segments.json").write_text(json.dumps(S))
            (out / f"{uid}.hyp.txt").write_text(" ".join(s["text"] for s in S).strip() + "\n")
            tim.write(json.dumps(dict(id=uid, audio_s=dur, wall_s=round(el, 3), model=pathlib.Path(a.model).name, prompt=a.prompt)) + "\n"); tim.flush()
        print(sub, a.split, len(sel), flush=True)


if __name__ == "__main__":
    main()
