#!/usr/bin/env python3
"""Record one scripted test call through the M5Stack Atom VoiceS3R (factory firmware = USB microphone) and log taps.

  pip install sounddevice soundfile numpy
  python3 data/collect/record_session.py --list-devices
  python3 data/collect/record_session.py --call c01 --device "VoiceS3R"      # or the device index

While recording, press keys in this terminal (then Enter):
  b + Enter  = you just PRESSED THE BUTTON on the clip  (button taps make no sound, so this log is their only record)
  k + Enter  = you just did a DOUBLE KNOCK on the clip
  s + Enter  = you just did a DOUBLE SNAP near the clip
  1 + Enter  = single knock/snap distractor (should be ignored by the app)
  3 + Enter  = triple knock (stop)
  q + Enter  = stop recording
Writes data/audio/test/team/<call>.<take>.wav (16 kHz mono 16-bit) and data/scripts/test/gt/team/<call>.<take>.taps_log.json.
Then run data/collect/align_team_recording.py to produce the ground truth for that take."""
import argparse, json, pathlib, queue, sys, threading, time

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--call"); ap.add_argument("--device"); ap.add_argument("--take", default="t1"); ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--sr", type=int, default=16000)
    a = ap.parse_args()
    import sounddevice as sd, soundfile as sf, numpy as np
    if a.list_devices:
        print(sd.query_devices()); return
    dev = int(a.device) if a.device and a.device.isdigit() else a.device
    out = ROOT / "data/audio/test/team"; out.mkdir(parents=True, exist_ok=True)
    gtd = ROOT / "data/scripts/test/gt/team"; gtd.mkdir(parents=True, exist_ok=True)
    wav = out / f"{a.call}.{a.take}.wav"
    q = queue.Queue(); log = []
    t0 = [None]

    def cb(indata, frames, ti, status):
        if t0[0] is None: t0[0] = time.monotonic()
        q.put(indata.copy())
    f = sf.SoundFile(str(wav), "w", samplerate=a.sr, channels=1, subtype="PCM_16")
    stop = threading.Event()

    def writer():
        while not stop.is_set() or not q.empty():
            try: f.write(q.get(timeout=0.2))
            except queue.Empty: pass
    th = threading.Thread(target=writer); th.start()
    print(f"Recording {wav.name}. Read the script in data/scripts/test/{a.call}_*.call. Keys: b k s 1 3 q (+Enter)")
    with sd.InputStream(device=dev, channels=1, samplerate=a.sr, dtype="float32", callback=cb):
        for line in sys.stdin:
            c = line.strip().lower()[:1]
            now = time.monotonic()
            if t0[0] is None: continue
            ms = int((now - t0[0]) * 1000)
            if c == "q": break
            kind = {"b": ("button", "double"), "k": ("knock", "double"), "s": ("snap", "double"), "1": ("knock", "single_ignored"), "3": ("knock", "triple_stop")}.get(c)
            if kind:
                # keypress lags the physical gesture by ~300-700 ms; align_team_recording.py snaps knock/snap times to the audio transient
                log.append(dict(clip_ms=max(0, ms - 400), source=kind[0], kind=kind[1], key_ms=ms)); print(" logged", log[-1])
    stop.set(); th.join(); f.close()
    (gtd / f"{a.call}.{a.take}.taps_log.json").write_text(json.dumps(dict(call=a.call, take=a.take, device=str(a.device), taps=log), indent=1))
    print("saved", wav, "and", len(log), "tap marks")


if __name__ == "__main__":
    main()
