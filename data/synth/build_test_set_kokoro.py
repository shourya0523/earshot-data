#!/usr/bin/env python3
"""Render held-out test calls with Kokoro-82M voices (a different TTS engine from the Piper voices used in training).

Same pipeline as build_test_set.py (mic simulation, TEST half of the noise/tap banks, same ground-truth files);
only the speech generator changes, so the fine-tuned model can't benefit from having learned the training voices.

  python3 data/synth/build_test_set_kokoro.py                 # data/scripts/test_radio/*.call (30 radio-style calls)
  python3 data/synth/build_test_set_kokoro.py --scripts test  # the original 10 test calls, re-voiced
Audio -> data/audio/test/kokoro/<id>.snr{15,10,5}.wav ; GT -> data/scripts/test/gt/kokoro/
Needs: pip install "kokoro>=0.9.4" (Python <3.13) and espeak-ng (apt). Runs on CPU or GPU.
"""
import argparse, json, pathlib, re, sys
import numpy as np
from scipy import signal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calldsl, render

ROOT = pathlib.Path(__file__).resolve().parents[2]
SR = render.SR

# American (a*) and British (b*) Kokoro voices. None of these exist in the Piper training pool.
VOICES = ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_kore", "af_aoede", "am_adam", "am_michael", "am_fenrir",
          "am_puck", "am_echo", "am_eric", "am_liam", "am_onyx", "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
          "bm_daniel", "bm_fable"]

# Extra spoken forms for terms the radio scripts use that the Piper lexicon doesn't cover.
EXTRA_LEXICON = [(r"\bRUQ\b", "R.U.Q."), (r"\bQRS\b", "Q.R.S."), (r"\bROSC\b", "rosk"), (r"\bI-gel\b", "eye gel"),
                 (r"\bA-fib\b", "A fib"), (r"\bOPA\b", "O.P.A."), (r"\bPD\b", "P.D."), (r"\bETA\b", "E.T.A."),
                 (r"\bmics\b", "mikes"), (r"\bmLs\b", "M.L.s"), (r"\bT's\b", "tees")]

_PIPES = {}


def _pipe(lang):
    if lang not in _PIPES:
        from kokoro import KPipeline
        _PIPES[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    return _PIPES[lang]


def kokoro_tts(text, voice, speaker_id=None, rate=1.0):
    """Drop-in for render.tts: returns mono float32 at 16 kHz, peak-normalised, silence-trimmed."""
    for pat, rep in EXTRA_LEXICON:
        text = re.sub(pat, rep, text)
    text = render.speakable(text)
    parts = [np.asarray(a, dtype=np.float32) for _, _, a in _pipe(voice[0])(text, voice=voice, speed=1.0 / rate)]
    y = np.concatenate(parts) if parts else np.zeros(SR // 10, np.float32)
    y = signal.resample_poly(y, 2, 3).astype(np.float32)        # 24 kHz -> 16 kHz
    idx = np.where(np.abs(y) > 0.01)[0]
    if len(idx):
        y = y[max(0, idx[0] - 800): idx[-1] + 1600]
    return y / (np.max(np.abs(y)) + 1e-9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scripts", default="test_radio", help="folder under data/scripts with the .call files")
    ap.add_argument("--snrs", default="15,10,5")
    ap.add_argument("--only", default="", help="comma-separated call ids to render (default: all)")
    a = ap.parse_args()
    render.tts = kokoro_tts                                       # swap the speech generator, keep everything else
    aud = ROOT / "data/audio/test/kokoro"; gt = ROOT / "data/scripts/test/gt/kokoro"
    aud.mkdir(parents=True, exist_ok=True); gt.mkdir(parents=True, exist_ok=True)
    snrs = tuple(int(s) for s in a.snrs.split(","))
    only = set(filter(None, a.only.split(",")))
    tb = render.TapBank("test")
    info = []
    for i, f in enumerate(sorted((ROOT / "data/scripts" / a.scripts).glob("*.call"))):
        call = calldsl.parse(f.read_text())
        cid = call["meta"]["call_id"]
        if only and cid not in only:
            continue
        probs = calldsl.validate_test_call(call)
        assert not probs, (f, probs)
        r = render.render(call, aud, "test", seed=300 + i, snrs=snrs, voices=[(v, None) for v in VOICES], tapbank=tb)
        for ext in ("transcript.txt", "transcript_speakers.txt", "segments.json", "events.jsonl", "taps.json", "expected.json"):
            (aud / f"{cid}.{ext}").replace(gt / f"{cid}.{ext}")
        r["tts"] = "kokoro-82m"; info.append(r); print(r, flush=True)
    (gt / "render_info.json").write_text(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
