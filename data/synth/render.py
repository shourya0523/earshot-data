"""Render a parsed .call into audio + ground truth.

TTS (Piper) per speaker -> timeline with gaps -> tap sounds (double knock / double snap; button = silent,
logged only) -> mic simulation (wearer loud, others quieter/duller, radio band-limited) -> noise bed at SNR.

Ground truth written next to the audio:
  <id>.wav (noisy), <id>.clean.wav, <id>.transcript.txt, <id>.segments.json, <id>.events.jsonl,
  <id>.taps.json, <id>.expected.json
Bank split: every sound/noise file is assigned to 'test' or 'train' by a stable hash so test audio
never reuses a tap or noise recording seen in training (see data/manifests/bank_split.json).
"""
import datetime as dt, hashlib, json, pathlib, random, wave, io
import numpy as np
import soundfile as sf
from scipy import signal

SR = 16000
ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"


def bank_of(path):
    h = int(hashlib.sha1(pathlib.Path(path).name.encode()).hexdigest(), 16)
    return "test" if h % 5 == 0 else "train"


def load(path, sr=SR):
    import librosa
    y, _ = librosa.load(str(path), sr=sr, mono=True)
    return y.astype(np.float32)


# ------------------------------------------------------------------ TTS
_VOICES = {}


def piper_voice(name):
    from piper import PiperVoice
    if name not in _VOICES:
        _VOICES[name] = PiperVoice.load(str(RAW / "piper" / f"{name}.onnx"))
    return _VOICES[name]


TTS_LEXICON = [  # spoken forms for Piper only; reference transcripts keep the written form
    (r"\bIV\b", "I.V."), (r"\bIM\b", "I.M."), (r"\bIO\b", "I.O."), (r"\bmLs\b", "M.L.s"), (r"\bmL\b", "M.L."), (r"\bBGL\b", "B.G.L."),
    (r"\bNPA\b", "N.P.A."), (r"\bTXA\b", "T.X.A."), (r"\bAC\b", "A.C."), (r"\baVF\b", "A.V.F."), (r"\bMVC\b", "M.V.C."), (r"\bCT\b", "C.T."),
    (r"\bBE-FAST\b", "be fast"), (r"\bDuoNeb\b", "duo neb"), (r"\bSolu-Medrol\b", "solu medrol"), (r"\bVersed\b", "ver-sed"),
    (r"\bD10\b", "D ten"), (r"\bD50\b", "D fifty"), (r"\bBP\b", "B.P."), (r"\bGCS\b", "G.C.S."), (r"\bNRB\b", "N.R.B."),
    (r"\bEpi\b", "eppy"), (r"\bepi\b", "eppy"), (r"\bAMA\b", "A.M.A."), (r"\bSpO2\b", "S.P.O. two"), (r"\bA&O\b", "A and O"),
    (r"\bmcg\b", "micrograms"), (r"\bmg\b", "milligrams"), (r"\bnare\b", "nair"), (r"\bEMS\b", "E.M.S."), (r"\bCPAP\b", "see pap"),
    (r"\bALS\b", "A.L.S."), (r"\bBLS\b", "B.L.S."), (r"\bET\b", "E.T."), (r"\bSL\b", "S.L."), (r"\bPO\b", "P.O."), (r"\bIN\b", "I.N."),
    (r"\bLR\b", "L.R."), (r"\bNS\b", "N.S."), (r"\bO2\b", "O two"), (r"\bEtCO2\b", "end tidal"), (r"\bETCO2\b", "end tidal"),
]


def speakable(text):
    import re
    for pat, rep in TTS_LEXICON:
        text = re.sub(pat, rep, text)
    return text


def tts(text, voice, speaker_id=None, rate=1.0):
    from piper import SynthesisConfig
    text = speakable(text)
    v = piper_voice(voice)
    cfg = SynthesisConfig(speaker_id=speaker_id, length_scale=rate, noise_scale=0.667, noise_w_scale=0.8)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        v.synthesize_wav(text, w, syn_config=cfg)
    buf.seek(0)
    y, sr = sf.read(buf, dtype="float32")
    if sr != SR:
        y = signal.resample_poly(y, SR, sr)
    # trim leading/trailing silence
    idx = np.where(np.abs(y) > 0.01)[0]
    if len(idx):
        y = y[max(0, idx[0] - 800): idx[-1] + 1600]
    return y / (np.max(np.abs(y)) + 1e-9)


VOICE_POOL = [("en_US-lessac-medium", None), ("en_US-ryan-medium", None), ("en_US-amy-medium", None),
              ("en_US-joe-medium", None), ("en_US-kristin-medium", None), ("en_US-hfc_male-medium", None),
              ("en_US-hfc_female-medium", None), ("en_US-john-medium", None), ("en_US-norman-medium", None),
              ("en_GB-alan-medium", None), ("en_GB-northern_english_male-medium", None)]
LIBRITTS = "en_US-libritts_r-medium"  # 904 speakers


def available_voices():
    return [v for v in VOICE_POOL if (RAW / "piper" / f"{v[0]}.onnx").exists()]


# ------------------------------------------------------------------ mic + channel simulation
def mic_sim(y, speaker, rng):
    if speaker == "M1":           # wearer: close, loud
        g = 0.5
    elif speaker == "RD":         # portable radio on the other medic's belt
        b, a = signal.butter(4, [300 / (SR / 2), 3000 / (SR / 2)], "band")
        y = signal.lfilter(b, a, y)
        y = np.tanh(3 * y) / np.tanh(3)
        g = 0.22
    else:                         # partner / patient / bystander: 1-2 m away
        b, a = signal.butter(2, 5000 / (SR / 2), "low")
        y = signal.lfilter(b, a, y)
        ir = np.zeros(int(0.25 * SR)); ir[0] = 1
        taps = rng.integers(200, len(ir), 12); ir[taps] = rng.uniform(0.05, 0.25, 12) * np.exp(-taps / (0.08 * SR))
        y = signal.fftconvolve(y, ir)[: len(y) + int(0.1 * SR)]
        g = {"M2": 0.3, "PT": 0.28, "BY": 0.2}[speaker] * rng.uniform(0.8, 1.2)
    return (g * y / (np.max(np.abs(y)) + 1e-9)).astype(np.float32)


# ------------------------------------------------------------------ tap sounds
def _hits_from(path, max_hits=6):
    """Cut individual percussive hits (~150 ms) from a recording."""
    y = load(path)
    if len(y) < SR * 0.2:
        return []
    env = np.convolve(np.abs(y), np.ones(80) / 80, "same")
    peaks, _ = signal.find_peaks(env, height=0.3 * env.max(), distance=int(0.15 * SR))
    out = []
    for p in peaks[:max_hits]:
        s = max(0, p - int(0.01 * SR)); h = y[s: s + int(0.15 * SR)].copy()
        h *= np.exp(-np.arange(len(h)) / (0.05 * SR))
        if np.max(np.abs(h)) > 0:
            out.append(h / np.max(np.abs(h)))
    return out


class TapBank:
    def __init__(self, which):
        self.which = which
        self.knock = []; self.snap = []
        kfiles = sorted((RAW / "fsd50k" / "clips" / "Knock").glob("*.wav")) + sorted((RAW / "knocking_zenodo" / "x").rglob("*.wav"))
        sfiles = sorted((RAW / "fsd50k" / "clips" / "Finger_snapping").glob("*.wav"))
        for f in kfiles:
            if bank_of(f) == which:
                self.knock += _hits_from(f)
            if len(self.knock) > 300: break
        for f in sfiles:
            if bank_of(f) == which:
                self.snap += _hits_from(f, 4)
        assert self.knock and self.snap, f"empty tap bank {which}: {len(self.knock)} knocks {len(self.snap)} snaps"

    def multi(self, source, n, rng, gap=None):
        hits = self.knock if source == "knock" else self.snap
        parts = []
        for i in range(n):
            h = hits[rng.integers(len(hits))] * rng.uniform(0.6, 0.95)
            parts.append(h)
            if i < n - 1:
                g = gap if gap else rng.uniform(0.18, 0.35)
                parts.append(np.zeros(int(g * SR) - len(h) if int(g * SR) > len(h) else 0, np.float32))
        return np.concatenate(parts).astype(np.float32)


# ------------------------------------------------------------------ noise
NOISE_KINDS = {
    "cab": lambda: sorted((RAW / "demand" / "TCAR").glob("*.wav")) + sorted((RAW / "demand" / "TBUS").glob("*.wav")),
    "road": lambda: sorted((RAW / "demand" / "STRAFFIC").glob("*.wav")) + sorted((RAW / "fsd50k" / "clips" / "Traffic_noise_and_roadway_noise").glob("*.wav")),
    "siren": lambda: sorted((RAW / "emergencyvehicle" / "ambulance").glob("*.wav")) + sorted((RAW / "fsd50k" / "clips" / "Siren").glob("*.wav")),
    "monitor": lambda: sorted((RAW / "fsd50k" / "clips" / "Beep_and_bleep").glob("*.wav")) + sorted((RAW / "fsd50k" / "clips" / "Alarm").glob("*.wav")),
    "engine": lambda: sorted((RAW / "fsd50k" / "clips" / "Idling").glob("*.wav")) + sorted((RAW / "fsd50k" / "clips" / "Engine").glob("*.wav")),
}


def monitor_beeps(n, rng):
    """Synthetic patient-monitor sounds: QRS beep (~1/s) + occasional IEC 60601-1-8 style alarm bursts."""
    t = np.arange(n) / SR
    y = np.zeros(n, np.float32)
    hr = rng.uniform(0.7, 1.6)
    f = rng.choice([880, 960, 1000])
    for s in np.arange(rng.uniform(0, 1), n / SR, 1 / hr):
        i = int(s * SR); L = int(0.06 * SR)
        if i + L < n:
            y[i:i + L] += 0.15 * np.sin(2 * np.pi * f * t[:L]) * np.hanning(L)
    for s in rng.uniform(0, n / SR, max(1, int(n / SR / 40))):
        for k in range(3):
            i = int((s + k * 0.25) * SR); L = int(0.15 * SR)
            if i + L < n:
                y[i:i + L] += 0.25 * np.sin(2 * np.pi * 523 * t[:L]) * np.hanning(L)
    return y


def noise_bed(n, which, rng, kinds=("cab", "road", "siren", "monitor")):
    bed = np.zeros(n, np.float32)
    for kind in kinds:
        files = [f for f in NOISE_KINDS[kind]() if bank_of(f) == which]
        if kind == "monitor" and (rng.random() < 0.5 or not files):
            bed += monitor_beeps(n, rng); continue
        if not files:
            continue
        seg = np.zeros(n, np.float32); pos = 0
        while pos < n:
            y = load(files[rng.integers(len(files))])
            if len(y) == 0: break
            y = y / (np.sqrt(np.mean(y ** 2)) + 1e-9)
            take = min(len(y), n - pos)
            seg[pos:pos + take] = y[:take]; pos += take
        level = {"cab": 1.0, "road": 0.6, "siren": rng.choice([0.0, 0.3, 0.8]), "monitor": 0.3, "engine": 0.7}[kind]
        if kind == "siren":   # sirens come and go
            env = np.clip(np.sin(np.linspace(0, rng.uniform(1, 4) * np.pi, n)) + rng.uniform(-0.5, 0.3), 0, 1)
            seg *= env
        bed += level * seg
    return bed


def mix_snr(clean_speech_only, bed, snr_db):
    sp = clean_speech_only[np.abs(clean_speech_only) > 1e-4]
    ps = np.mean(sp ** 2) if len(sp) else 1e-6
    pn = np.mean(bed ** 2) + 1e-12
    return bed * np.sqrt(ps / (pn * 10 ** (snr_db / 10)))


# ------------------------------------------------------------------ timeline
def hms_add(start, ms):
    t0 = dt.datetime.strptime(start, "%H:%M:%S")
    return (t0 + dt.timedelta(milliseconds=ms)).strftime("%H:%M:%S")


def render(call, out_dir, which_bank="test", seed=0, snrs=(10,), voices=None, tapbank=None, write_clean=True):
    rng = np.random.default_rng(seed)
    meta = call["meta"]; cid = meta["call_id"]
    out_dir = pathlib.Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    pool = voices or available_voices()
    order = list(rng.permutation(len(pool)))
    spk_voice = {}
    for i, s in enumerate(["M1", "M2", "PT", "BY", "RD"]):
        spk_voice[s] = pool[order[i % len(pool)]]
    rates = {s: rng.uniform(0.85, 1.05) for s in spk_voice}
    tb = tapbank or TapBank(which_bank)

    speech = []; taps = []; distractors = []; segments = []; pending = []
    cursor = 0.5
    chunks = []  # (start_sample, array, is_speech)
    unl_taps = 0
    for it in call["items"]:
        if it["kind"] == "gap":
            cursor += it["seconds"]
        elif it["kind"] == "tap":
            cursor += 0.4
            t_ms = int(cursor * 1000)
            tap = dict(id=f"t{len(taps)+1}", clip_ms=t_ms, source=it["source"], labelled=it["labelled"])
            if it["source"] != "button":
                a = tb.multi(it["source"], 2, rng); chunks.append((int(cursor * SR), a * (0.9 if it["source"] == "knock" else 0.6), False))
                cursor += len(a) / SR
            taps.append(tap)
            if it["labelled"]:
                pending.append(tap)
            else:
                unl_taps += 1
                if unl_taps % 2 == 1 and it["source"] != "button":   # single distractor 6 s later (must be ignored)
                    pass
                d_t = cursor + 6.0
                src = "snap" if it["source"] == "knock" else "knock"
                a = tb.multi(src, 1, rng)
                chunks.append((int(d_t * SR), a * 0.7, False))
                distractors.append(dict(clip_ms=int(d_t * 1000), source=src, kind="single_ignored"))
            cursor += 1.0
        elif it["kind"] == "triple":
            cursor += 1.0
            a = tb.multi("knock", 3, rng)
            chunks.append((int(cursor * SR), a * 0.9, False))
            distractors.append(dict(clip_ms=int(cursor * 1000), source="knock", kind="triple_stop"))
            cursor += len(a) / SR + 1.0
        else:
            v, sid = spk_voice[it["speaker"]]
            y = tts(it["text"], v, sid, rates[it["speaker"]])
            y = mic_sim(y, it["speaker"], rng)
            st = cursor
            chunks.append((int(st * SR), y, True))
            seg = dict(start_ms=int(st * 1000), end_ms=int((st + len(y) / SR) * 1000), speaker=it["speaker"], text=it["text"])
            segments.append(seg)
            ev_tap = None
            if it["events"] and pending:
                ev_tap = pending.pop(0)
            for e in it["events"]:
                speech.append((seg, e, ev_tap))
            cursor = st + len(y) / SR + rng.uniform(0.3, 0.9)
    assert not pending, f"{cid}: labelled tap without a following event line"
    n = int((cursor + 1.0) * SR)
    sp = np.zeros(n, np.float32); fx = np.zeros(n, np.float32)
    for s, a, is_sp in chunks:
        a = a[: n - s]
        (sp if is_sp else fx)[s:s + len(a)] += a
    start = meta.get("start", "12:00:00")
    # events
    events = []
    for k, (seg, e, tap) in enumerate(speech):
        if tap:
            src, t_ms = "tap+heard", tap["clip_ms"]
        else:
            src, t_ms = "heard", seg["start_ms"]
        ev = dict(id=f"e{k+1}", call_id=cid, time=hms_add(start, t_ms), clip_ms=t_ms, type=e["type"], fields=e["fields"],
                  source=src, quote=e["quote"], segment_start_ms=seg["start_ms"])
        if tap:
            ev["tap_id"] = tap["id"]
        events.append(ev)
    for tap in taps:
        if not tap["labelled"]:
            events.append(dict(id=f"m{tap['id']}", call_id=cid, time=hms_add(start, tap["clip_ms"]), clip_ms=tap["clip_ms"], type="marker",
                               fields={}, source="tap", quote=None, label="marked, no label", tap_id=tap["id"]))
    events.sort(key=lambda e: e["clip_ms"])
    expected = expected_fields(call, events, start)
    # write
    transcript = "\n".join(f"{s['speaker']}: {s['text']}" for s in segments)
    (out_dir / f"{cid}.transcript.txt").write_text(" ".join(s["text"] for s in segments) + "\n")
    (out_dir / f"{cid}.transcript_speakers.txt").write_text(transcript + "\n")
    (out_dir / f"{cid}.segments.json").write_text(json.dumps(segments, indent=1))
    (out_dir / f"{cid}.events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (out_dir / f"{cid}.taps.json").write_text(json.dumps(dict(taps=[dict(clip_ms=t["clip_ms"], source=t["source"], id=t["id"], labelled=t["labelled"]) for t in taps],
                                                           ignored=distractors, start=start), indent=1))
    (out_dir / f"{cid}.expected.json").write_text(json.dumps(expected, indent=1))
    clean = sp + fx
    if write_clean:
        sf.write(out_dir / f"{cid}.clean.wav", np.clip(clean, -1, 1), SR, subtype="PCM_16")
    bed = noise_bed(n, which_bank, rng)
    outs = {}
    for snr in snrs:
        y = clean + mix_snr(sp, bed, snr)
        y = y / max(1.0, np.max(np.abs(y)) / 0.98)
        p = out_dir / (f"{cid}.snr{snr}.wav")
        sf.write(p, y, SR, subtype="PCM_16"); outs[snr] = p
    return dict(call_id=cid, seconds=n / SR, voices={k: v[0] for k, v in spk_voice.items()}, snrs=list(snrs), n_taps=len(taps), n_events=len(events))


# ------------------------------------------------------------------ expected output key fields
def expected_fields(call, events, start):
    p = call["patient"]
    meds = [e["fields"] for e in events if e["type"] == "medication"]
    vit = [e for e in events if e["type"] == "vital"]
    procs = sorted({e["fields"]["name"] for e in events if e["type"] == "procedure"})
    status = [e["fields"]["term"] for e in events if e["type"] == "status"]
    etimes = {}
    for e in events:
        if e["type"] == "time" and e["fields"]["etime"] not in etimes:
            etimes[e["fields"]["etime"]] = e["time"]
    disp = next((e["fields"]["text"] for e in events if e["type"] == "dispatch"), None)
    found = next((e["fields"]["text"] for e in events if e["type"] == "found"), None)
    first = {}
    for e in vit:
        first.setdefault(e["fields"]["name"], e["fields"]["value"])
    last = {}
    for e in vit:
        last[e["fields"]["name"]] = e["fields"]["value"]
    def med_str(m):
        return " ".join(x for x in [m["drug"], m.get("dose", ""), m.get("unit", ""), m.get("route", "")] if x).strip()
    heard_pt = {k: p.get(k) for k in ["age", "sex", "weight_kg", "complaint", "allergies", "home_meds", "history"]}
    wall = None
    if "eTimes.11" in etimes and "eTimes.12" in etimes:
        a = dt.datetime.strptime(etimes["eTimes.11"], "%H:%M:%S"); b = dt.datetime.strptime(etimes["eTimes.12"], "%H:%M:%S")
        wall = int((b - a).total_seconds())
    return dict(
        note=("Patient-block values are scenario metadata. Only fields actually spoken in the transcript are scoreable; "
              "'spoken_patient_fields' lists those. Unspoken ones must render as 'not heard'."),
        spoken_patient_fields=[k for k, v in heard_pt.items() if v and v.lower() not in ("unknown", "none") and _spoken(call, k, v)],
        patient=heard_pt,
        soap=dict(S=dict(chief_complaint_symptom=p.get("complaint"), allergies=p.get("allergies"), medications=p.get("home_meds"), history=p.get("history")),
                  O=dict(first_vitals=first, last_vitals=last, status=status, found=found),
                  A=dict(must_not_contain=call["traps"]),
                  P=dict(medications=[med_str(m) for m in meds], procedures=procs)),
        imist_ambo=dict(I_identification=dict(age=p.get("age"), sex=p.get("sex")), M_mechanism_or_complaint=disp,
                        I_injuries_or_information=found or p.get("complaint"), S_signs=first,
                        T_treatment=[med_str(m) for m in meds] + procs, A_allergies=p.get("allergies"),
                        M_medications=p.get("home_meds"), B_background=p.get("history"), O_other=None),
        nemsis_etimes=etimes, wall_time_seconds=wall, dispatch_reason=disp,
        medications=meds, vitals=[dict(name=e["fields"]["name"], value=e["fields"]["value"], time=e["time"]) for e in vit],
        diagnosis_traps=call["traps"],
    )


def _spoken(call, key, val):
    txt = " ".join(it["text"].lower() for it in call["items"] if it["kind"] == "speech")
    words = {"age": None, "sex": None}
    if key == "age":
        return any(w in txt for w in [f"{val}", _num_words(int(val))]) if val.isdigit() else False
    toks = [t.strip(" .,").lower() for t in val.replace(",", " ").split()]
    return any(t in txt for t in toks if len(t) > 3)


def _num_words(n):
    ones = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    tens = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
    if n < 20: return ones[n]
    return tens[n // 10] + ("-" + ones[n % 10] if n % 10 else "")
