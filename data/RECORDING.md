# Recording the 10 test calls through the VoiceS3R (team version)

**Goal:** a real-mic version of each scripted test call, recorded through the clip, to compare with the TTS version.
Time needed: about 1 hour for all 10 calls with 3 people.

## Setup (10 min)
1. **Device:** M5Stack Atom VoiceS3R with **factory firmware** (it enumerates as a USB microphone). Plug it into the laptop with a USB-C data cable.
2. **Wear it** on the chest or radio strap of the person reading **M1** (lead medic), mic facing up. Don't hold it.
3. **Roles:** M1 = wears the clip, presses the button, knocks and snaps. M2 = partner, stands 1–2 m away. PT/BY = patient/bystander, 1–2 m away. Whoever is free reads **RD** (dispatch radio) from across the room, or from a phone speaker.
4. **Noise:** do half the calls in a quiet room. Do the other half with noise: a phone playing a siren or road-noise video at moderate volume 2–3 m away, or a running car or idling vehicle if available. Note which in the log below.
5. **Install:** `pip install sounddevice soundfile numpy`, then run `python3 data/collect/record_session.py --list-devices` and find the VoiceS3R device name or index.

## Per call (about 4 min each)
```bash
python3 data/collect/record_session.py --call c01 --device <index-or-name> --take t1
```
- Open `data/scripts/test/c01_chest_pain.call` on a second screen. Read the lines after `M1:`, `M2:`, `PT:`, `BY:` and `RD:`. **Skip everything after `>>`.** Those are annotations, not speech.
- `GAP n` means stay silent for about n seconds. Keep the gaps: they matter for tap labelling.
- **Taps:** when the script says
  - `TAP button ...` → M1 **presses the clip button once**. The laptop operator types `b` + Enter right after.
  - `TAP knock ...` → M1 does a **double knock** on the clip housing (two knocks, about 0.25 s apart). The operator types `k` + Enter.
  - `TAP snap ...` → M1 does a **double finger snap** about 10–20 cm from the clip. The operator types `s` + Enter.
  - `+label` = do it **just before** the next line with `>>` (within 1–2 s), so speech labels the tap.
  - `-` (unlabelled) = do it **in silence**: nobody talks for about 10 s before and after.
  - `KNOCK3` → **triple knock** (stop). The operator types `3` + Enter.
- **Distractors:** in every second call, during a long gap, M1 does **one single knock**. The operator types `1` + Enter. The app should ignore it.
- Type `q` + Enter at the end of the call.
- Don't restart for a stumble; just continue. Restart (`--take t2`) only if a tap was missed or the order went wrong.

## After recording
```bash
python3 data/collect/align_team_recording.py --call c01 --take t1     # builds GT for that take
python3 eval/run_pipeline.py --wavs 'data/audio/test/team/*.wav' --gt data/scripts/test/gt/team --out eval/runs/pipe_stock/test_team
python3 eval/score.py --gt data/scripts/test/gt/team --run eval/runs/pipe_stock/test_team
```
**Privacy:** the scripts use no real patient details. Don't add any. Audio files stay out of git (`data/audio/` is ignored); upload them to the team drive with their sha256 in `data/manifests/team_takes.csv`.

## Log (fill in)
| call | take | readers (M1/M2/PT) | room / noise | notes |
|---|---|---|---|---|
| c01 | t1 | | | |
| c02 | t1 | | | |
| c03 | t1 | | | |
| c04 | t1 | | | |
| c05 | t1 | | | |
| c06 | t1 | | | |
| c07 | t1 | | | |
| c08 | t1 | | | |
| c09 | t1 | | | |
| c10 | t1 | | | |
