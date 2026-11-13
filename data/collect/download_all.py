#!/usr/bin/env python3
"""Fetch every external source used by Earshot data/eval into data/raw/<source>/.
Writes data/manifests/raw_manifest.jsonl (url, path, bytes, sha256, license, pii).
Usage: python3 -I data/collect/download_all.py [--only name,name] [--skip-big]
Idempotent: skips files that already exist with the recorded size."""
import urllib.parse
import argparse, csv, hashlib, io, json, os, pathlib, random, sys, time, urllib.request, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
MAN = ROOT / "data" / "manifests" / "raw_manifest.jsonl"
HF = "https://huggingface.co"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(url, dest, tries=4):
    dest = pathlib.Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for i in range(tries):
        try:
            url = urllib.parse.quote(url, safe=":/?=&%")
            req = urllib.request.Request(url, headers={"User-Agent": "earshot-data/0.1"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            tmp.rename(dest)
            return dest
        except Exception as e:  # noqa
            print(f"  retry {i+1} {url}: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed {url}")


RECORDS = []


def rec(source, url, path, license, pii, how="https download"):
    p = pathlib.Path(path)
    RECORDS.append(dict(source=source, url=url, path=str(p.relative_to(ROOT)), bytes=p.stat().st_size,
                        sha256=sha256(p), license=license, pii=pii, how=how))


def hf_file(repo, fpath, dest, source, license, pii, kind="datasets"):
    pre = f"{HF}/datasets/{repo}" if kind == "datasets" else f"{HF}/{repo}"
    url = f"{pre}/resolve/main/{fpath}"
    fetch(url, dest)
    rec(source, url, dest, license, pii)


# ---------------------------------------------------------------- real speech
def real_speech(skip_big):
    d = RAW / "emscontext"
    hf_file("saahith/EMSContExt_audio", "data/test-00000-of-00001-10ebbca1092c9df0.parquet", d / "test.parquet",
            "EMSContExt_audio (UVA EMS narratives, human-read)", "unknown (no dataset card)", "no")
    d = RAW / "eka"
    for i in range(2 if skip_big else 4):
        hf_file("ekacare/eka-medical-asr-evaluation-dataset", f"en/test-0000{i}.parquet", d / f"test-{i}.parquet",
                "Eka Care medical ASR eval (en)", "MIT", "de-identified")
    d = RAW / "primock57"
    hf_file("macabdul9/Primock57", "data/test-00000-of-00001.parquet", d / "test.parquet",
            "PriMock57 mock GP consultations (utterances)", "CC-BY-4.0", "no (actors)")
    d = RAW / "medspeech_intent"
    hf_file("Shamus/Medical_Speech_Transcription_and_Intent", "overview-of-recordings.csv", d / "overview.csv",
            "Medical Speech, Transcription and Intent (Figure Eight)", "unknown (Figure Eight; Kaggle lists CC BY-NC-SA 4.0? unverified)", "no")


def medspeech_wavs(n=300):
    d = RAW / "medspeech_intent"
    rows = list(csv.DictReader(open(d / "overview.csv", encoding="utf-8")))
    random.Random(7).shuffle(rows)
    api = json.load(urllib.request.urlopen(f"{HF}/api/datasets/Shamus/Medical_Speech_Transcription_and_Intent/tree/main?recursive=1", timeout=120))
    paths = {pathlib.Path(x["path"]).name: x["path"] for x in api if x["path"].endswith(".wav")}
    got = 0
    for r in rows:
        fn = r.get("file_name")
        if fn in paths:
            hf_file("Shamus/Medical_Speech_Transcription_and_Intent", paths[fn], d / "wav" / fn,
                    "Medical Speech, Transcription and Intent (Figure Eight)", "unknown", "no")
            got += 1
            if got >= n:
                break
    print("medspeech wavs", got)


# ---------------------------------------------------------------- noise + taps
FSD_CLASSES = {"Knock": 300, "Finger_snapping": 199, "Tap": 120, "Siren": 132, "Alarm": 80, "Traffic_noise_and_roadway_noise": 80,
               "Engine": 60, "Idling": 60, "Clapping": 60, "Beep_and_bleep": 60, "Speech": 0}


def fsd50k():
    d = RAW / "fsd50k"
    for f in ["labels/dev.csv", "labels/eval.csv"]:
        hf_file("Fhrozen/FSD50k", f, d / f, "FSD50K labels", "CC-BY-4.0", "no")
    lic = {}
    for split in ["dev", "eval"]:
        try:
            mp = d / f"metadata/{split}_clips_info_FSD50K.json"
            hf_file("Fhrozen/FSD50k", f"metadata/{split}_clips_info_FSD50K.json", mp, "FSD50K clip metadata", "CC-BY-4.0", "no")
            for k, v in json.load(open(mp)).items():
                lic[k] = v.get("license", "")
        except Exception as e:
            print("fsd metadata", e)
    picks = {c: [] for c in FSD_CLASSES}
    for split in ["dev", "eval"]:
        for r in csv.DictReader(open(d / f"labels/{split}.csv")):
            labs = r["labels"].split(",")
            L = lic.get(r["fname"], "")
            if "NonCommercial" in L or "/by-nc" in L:
                continue  # keep only CC0 / CC-BY for training use
            for c in FSD_CLASSES:
                if c in labs and len(picks[c]) < FSD_CLASSES[c]:
                    # Knock / snap must be the *only* foreground class to be clean positives
                    if c in ("Knock", "Finger_snapping") and len(labs) > 3:
                        continue
                    picks[c].append((split, r["fname"], L))
    out = []
    for c, lst in picks.items():
        for split, fn, L in lst:
            dest = d / "clips" / c / f"{fn}.wav"
            url = f"{HF}/datasets/Fhrozen/FSD50k/resolve/main/clips/{split}/{fn}.wav"
            try:
                fetch(url, dest)
                rec(f"FSD50K/{c}", url, dest, L or "CC-BY-4.0 (dataset)", "no")
                out.append(c)
            except Exception as e:
                print("fsd", fn, e)
    print("fsd clips", {c: out.count(c) for c in set(out)})


def esc50():
    d = RAW / "esc50"
    hf_file("TigreGotico/ESC-50", "meta/esc50.csv", d / "esc50.csv", "ESC-50 meta", "CC BY-NC 3.0", "no")
    want = {"door_wood_knock", "siren", "clock_alarm", "engine", "mouse_click", "car_horn"}
    for r in csv.DictReader(open(d / "esc50.csv")):
        if r["category"] in want:
            hf_file("TigreGotico/ESC-50", r["filename"], d / r["category"] / r["filename"], f"ESC-50/{r['category']}",
                    "CC BY-NC 3.0 (eval/augmentation only)", "no")


def zenodo():
    d = RAW / "knocking_zenodo"
    url = "https://zenodo.org/api/records/3668503/files/Knocking%20Sound%20Effects%20With%20Emotional%20Intentions.zip/content"
    z = fetch(url, d / "knocking.zip"); rec("Knocking Sound Effects With Emotional Intentions (zenodo 3668503)", url, z, "CC-BY-4.0", "no")
    if not (d / "x").exists():
        zipfile.ZipFile(z).extractall(d / "x")
    d = RAW / "demand"
    for name in ["TCAR_16k", "STRAFFIC_16k", "TBUS_16k"]:
        url = f"https://zenodo.org/api/records/1227121/files/{name}.zip/content"
        z = fetch(url, d / f"{name}.zip"); rec(f"DEMAND {name} (zenodo 1227121)", url, z, "CC-BY-4.0", "no")
        if not (d / name).exists():
            zipfile.ZipFile(z).extractall(d)


def emergency_vehicle(n=80):
    d = RAW / "emergencyvehicle"
    api = json.load(urllib.request.urlopen(f"{HF}/api/datasets/gelang/emergencyvehicle/tree/main?recursive=1", timeout=120))
    for sub in ["ambulance", "traffic"]:
        fs = sorted(x["path"] for x in api if x["path"].endswith(".wav") and f"{sub}/" in x["path"])[:n]
        for f in fs:
            hf_file("gelang/emergencyvehicle", f, d / sub / pathlib.Path(f).name, f"gelang/emergencyvehicle/{sub}", "unknown", "no")


def dispatch_radio():
    d = RAW / "dispatch"
    item = "202208072004-266724-9809"
    meta = json.load(urllib.request.urlopen(f"https://archive.org/metadata/{item}", timeout=120))
    for f in meta["files"]:
        if f["name"].endswith(".mp3"):
            url = f"https://archive.org/download/{item}/{f['name']}"
            p = fetch(url, d / f["name"]); rec("archive.org Frederick Co. MD Fire/EMS dispatch", url, p, "Public Domain Mark 1.0", "yes (addresses, unit IDs on air)")
    url = "https://archive.org/download/scanstockton51/04-30-2011-Clifton-Court-Water-Rescue.mp3"
    p = fetch(url, d / "stockton_water_rescue.mp3"); rec("archive.org Stockton PD/FD scanner", url, p, "CC BY-NC-ND 3.0 (eval/noise only)", "yes (on-air)")


# ---------------------------------------------------------------- text corpora
def text():
    d = RAW / "text"
    for f in ["aci/train.parquet", "aci/valid.parquet", "aci/test1.parquet"]:
        hf_file("mkieffer/ACI-Bench", f, d / "aci" / pathlib.Path(f).name, "ACI-Bench", "CC-BY-4.0", "no (role-play)")
    for f in ["MTS-Dialog-TrainingSet (SDHP).csv"]:
        hf_file("har1/MTS_Dialogue-Clinical_Note", f, d / "mts_dialog_train.csv", "MTS-Dialog", "CC-BY-4.0 (upstream)", "no")
    hf_file("ade-benchmark-corpus/ade_corpus_v2", "Ade_corpus_v2_drug_dosage_relation/train-00000-of-00001.parquet", d / "ade_drug_dosage.parquet",
            "ADE corpus v2 drug-dosage relation", "unknown", "no")
    for sp in ["train", "validation", "test"]:
        url = f"{HF}/api/datasets/tner/bc5cdr/parquet/bc5cdr/{sp}/0.parquet"
        p = fetch(url, d / "bc5cdr" / f"{sp}.parquet"); rec("BC5CDR (tner BIO)", url, p, "BioCreative (research use)", "no")


YT = ["wNxP0VV7MA0", "AjMZE9S9vkQ", "_T92XEGPbWg", "ojruICUvoV4", "ZRlSt_sA15g", "Ga1ySY8cHYM", "ZemE0bWmdDc", "j_vOcMMH6x4", "Fb6UIBquI5U",
      "cwyJHy8zaE4", "mAg7cXxL7b8", "vl4tci1OUog", "bGHa2CC3IEE", "bgAIGbzHZiE", "Fvti32AVkMo", "rBXKtLnWp0I", "_RjJq4IkZtA", "pfBU0BqPE9c",
      "m_L7rwfJ0aE", "Thgzuwen5_s", "mxUqHwHbNtk", "UkTOQ_P_8z0", "87DvYA3nX_M", "oW9nNJxJ3O4"]


def youtube_captions():
    import subprocess
    d = RAW / "youtube_captions"
    d.mkdir(parents=True, exist_ok=True)
    for vid in YT:
        if list(d.glob(f"{vid}*.vtt")):
            continue
        subprocess.run(["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "en.*,en", "--sub-format", "vtt",
                        "--write-info-json", "-o", str(d / "%(id)s.%(ext)s"), f"https://www.youtube.com/watch?v={vid}"],
                       capture_output=True, timeout=180)
        time.sleep(25)
    for p in d.glob("*.vtt"):
        rec("YouTube captions (text only)", f"https://www.youtube.com/watch?v={p.name.split('.')[0]}", p,
            "YouTube standard license (captions used for vocabulary/tagger text only; not redistributed)", "possible (names in bodycam/ride-along)", "yt-dlp --skip-download")


# ---------------------------------------------------------------- TTS voices
PIPER = [("en/en_US/lessac/medium", "en_US-lessac-medium"), ("en/en_US/ryan/medium", "en_US-ryan-medium"),
         ("en/en_US/amy/medium", "en_US-amy-medium"), ("en/en_US/joe/medium", "en_US-joe-medium"),
         ("en/en_US/kristin/medium", "en_US-kristin-medium"), ("en/en_US/hfc_male/medium", "en_US-hfc_male-medium"),
         ("en/en_US/hfc_female/medium", "en_US-hfc_female-medium"), ("en/en_US/libritts_r/medium", "en_US-libritts_r-medium"),
         ("en/en_US/john/medium", "en_US-john-medium"), ("en/en_US/norman/medium", "en_US-norman-medium"),
         ("en/en_GB/alan/medium", "en_GB-alan-medium"), ("en/en_GB/northern_english_male/medium", "en_GB-northern_english_male-medium")]


def piper_voices():
    d = RAW / "piper"
    for sub, name in PIPER:
        for ext in [".onnx", ".onnx.json"]:
            try:
                hf_file("rhasspy/piper-voices", f"{sub}/{name}{ext}", d / f"{name}{ext}", f"Piper voice {name}", "see voice MODEL_CARD (mostly CC-BY/CC0/MIT)", "no", kind="models")
            except Exception as e:
                print("piper", name, e)


def whisper_models():
    d = RAW / "models"
    for m in ["ggml-small.en.bin", "ggml-base.en.bin"]:
        hf_file("ggerganov/whisper.cpp", m, d / m, f"whisper.cpp {m}", "MIT", "no", kind="models")


def more_speech():
    """Expansion round (owner asked for more training data before fine-tuning)."""
    d = RAW / "eka"
    for i in range(4, 8):
        hf_file("ekacare/eka-medical-asr-evaluation-dataset", f"en/test-0000{i}.parquet", d / f"test-{i}.parquet", "Eka Care medical ASR eval (en)", "MIT", "de-identified")
    d = RAW / "primock57"
    for f in ["data/train-00000-of-00002.parquet", "data/train-00001-of-00002.parquet"]:
        hf_file("macabdul9/Primock57", f, d / pathlib.Path(f).name, "PriMock57 mock GP consultations (utterances)", "CC-BY-4.0", "no (actors)")
    d = RAW / "ems_synth_saahith"
    for f in ["data/train-00000-of-00001-8cc622404e34766d.parquet", "data/validation-00000-of-00001-abf7d4ec65e51b60.parquet"]:
        hf_file("saahith/synthetic_with_val", f, d / pathlib.Path(f).name.split("-")[0].__add__(".parquet"), "saahith/synthetic_with_val (EMS utterances, synthetic voices)", "unknown (no card)", "no")
    d = RAW / "dispatcher_ambulance"
    hf_file("ahmedelsayed/dispatcher-ambulance", "data/train-00000-of-00001.parquet", d / "train.parquet", "ahmedelsayed/dispatcher-ambulance (dispatch-crew dialogs, synthetic voices)", "unknown (no card)", "synthetic addresses")
    d = RAW / "modulate_dictation"
    hf_file("modulate/synthetic-medical-dictation", "data/dev-00000-of-00003.parquet", d / "dev-0.parquet", "modulate/synthetic-medical-dictation", "CC-BY-4.0", "no (TTS)")
    d = RAW / "emsassist2"
    hf_file("saahith/EMSAssist-2", "data/train-00000-of-00002-b50edc4e2587ffd7.parquet", d / "train-0.parquet", "saahith/EMSAssist-2 (EMS condition phrases)", "unknown (no card)", "no")
    medspeech_wavs(1800)


def round2():
    """Second expansion round, from the model/dataset search (data/MODEL_SEARCH.md)."""
    import urllib.request as U
    for i in (0, 1):
        f = f"data/train-0000{i}-of-00033.parquet"
        hf_file("Shamus/United-Syn-Med", f, RAW / "united_syn_med" / pathlib.Path(f).name, "United-Syn-Med (mirror of united-we-care/United-Syn-Med; drug-name TTS)", "CC-BY-SA-4.0 (original)", "no")
    hf_file("Trelis/medical-terms-2025", "data/test-00000-of-00001.parquet", RAW / "trelis_terms/test.parquet", "Trelis/medical-terms-2025", "MIT", "no")
    hf_file("Xueren/EMS-Knowledge", "data/train-00000-of-00001-7c3bec9885223866.parquet", RAW / "ems_knowledge/train.parquet", "Xueren/EMS-Knowledge", "MIT", "no")
    api = json.load(U.urlopen(f"{HF}/api/datasets/Xueren/EMSDialogue-Datasets/tree/main?recursive=1", timeout=120))
    for x in api:
        if x["type"] == "file" and x["path"].endswith(".json"):
            dest = RAW / "emsdialog" / x["path"]
            try:
                fetch(f"{HF}/datasets/Xueren/EMSDialogue-Datasets/resolve/main/{x['path']}", dest)
            except Exception as e:
                print("emsdialog", x["path"], e)
    rec("Xueren/EMSDialogue-Datasets (4.4k synthetic + 149 real de-identified EMS dialogues)", f"{HF}/datasets/Xueren/EMSDialogue-Datasets", next((RAW / "emsdialog").rglob("*.json")),
        "CC-BY-NC-4.0", "de-identified")
    hf_file("xxbubziexx/police-radio-punctuated-dataset", "metadata.csv", RAW / "police_radio/metadata.csv", "police-radio-punctuated-dataset", "MIT", "yes (real radio)")
    hf_file("xxbubziexx/police-radio-punctuated-dataset", "data.tar.gz", RAW / "police_radio/data.tar.gz", "police-radio-punctuated-dataset", "MIT", "yes (real radio)")
    for repo in ("saahith/whisper-small.en-EMSAssist-v2", "saahith/whisper-base.en-EMSAssist-v3"):
        for f in ("config.json", "pytorch_model.bin", "vocab.json", "merges.txt", "added_tokens.json", "tokenizer_config.json", "special_tokens_map.json", "preprocessor_config.json", "normalizer.json"):
            hf_file(repo, f, RAW / "models" / repo.split("/")[1] / f, f"{repo} (EMS-trained Whisper)", "none stated", "no", kind="models")
    hf_file("droytel/whisper-medical-v1-ggml", "ggml-whisper-medical-v1.bin", RAW / "models/ggml-whisper-medical-v1.bin", "droytel/whisper-medical-v1-ggml (Crystalcareai/Whisper-Medicalv1, distil-large-v3)", "MIT", "no", kind="models")


STEPS = dict(round2=round2, more=more_speech, real=real_speech, medwav=medspeech_wavs, fsd=fsd50k, esc=esc50, zenodo=zenodo, ev=emergency_vehicle,
             dispatch=dispatch_radio, text=text, yt=youtube_captions, piper=piper_voices, whisper=whisper_models)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-big", action="store_true")
    a = ap.parse_args()
    names = a.only.split(",") if a.only else list(STEPS)
    for n in names:
        print("==", n, flush=True)
        try:
            STEPS[n](a.skip_big) if n == "real" else STEPS[n]()
        except Exception as e:
            print("STEP FAILED", n, e, flush=True)
        MAN.parent.mkdir(parents=True, exist_ok=True)
        old = {}
        if MAN.exists():
            for l in MAN.read_text().splitlines():
                r = json.loads(l); old[r["path"]] = r
        for r in RECORDS:
            old[r["path"]] = r
        MAN.write_text("".join(json.dumps(r) + "\n" for r in sorted(old.values(), key=lambda r: r["path"])))
        RECORDS.clear()
    print("done")
