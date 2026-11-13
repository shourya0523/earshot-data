#!/usr/bin/env python3
"""Render the 10 scripted test calls (TTS + noise + tap sounds) and their ground truth.
Audio -> data/audio/test/tts/<id>.{clean,snr15,snr10,snr5}.wav ; GT -> data/scripts/test/gt/tts/
Uses only the 'test' half of the tap/noise banks (render.bank_of)."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calldsl, render

ROOT = pathlib.Path(__file__).resolve().parents[2]
AUD = ROOT / "data/audio/test/tts"; GT = ROOT / "data/scripts/test/gt/tts"
tb = render.TapBank("test")
print("tap bank", len(tb.knock), "knock hits", len(tb.snap), "snap hits")
info = []
for i, f in enumerate(sorted((ROOT / "data/scripts/test").glob("c*.call"))):
    call = calldsl.parse(f.read_text())
    assert not calldsl.validate_test_call(call), f
    r = render.render(call, AUD, "test", seed=100 + i, snrs=(15, 10, 5), tapbank=tb)
    for ext in ("transcript.txt", "transcript_speakers.txt", "segments.json", "events.jsonl", "taps.json", "expected.json"):
        (AUD / f"{r['call_id']}.{ext}").replace(GT / f"{r['call_id']}.{ext}") if GT.mkdir(parents=True, exist_ok=True) is None else None
    info.append(r); print(r, flush=True)
(GT / "render_info.json").write_text(json.dumps(info, indent=1))
