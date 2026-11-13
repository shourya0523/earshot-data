# Pipeline ready — earshot-eval

Status: **stock pipeline works end to end on Linux** (whisper.cpp `small.en` + rules-v1). Tested on Ubuntu 24.04, Swift 6.2.1.

## Build

```bash
core/scripts/setup_linux.sh          # Swift 6.2.1, whisper.cpp (pkg-config "whisper"), models/ggml-small.en.bin
cd core && swift build -c release    # binary: core/.build/release/earshot-eval
```
- whisper.cpp installed elsewhere: `export PKG_CONFIG_PATH=<prefix>/lib/pkgconfig LD_LIBRARY_PATH=<prefix>/lib`.
- macOS: `brew install whisper-cpp`, then `swift build -c release`.
- No whisper at all: `EARSHOT_NO_WHISPER=1 swift build` (transcript `.json` input only).
- Tests: `swift test`.

## Run

```bash
B=core/.build/release/earshot-eval
$B run call.wav --taps taps.json --asr-model models/ggml-small.en.bin --out out/call1          # stock
$B run call.wav --taps taps.json --asr-model models/whisper-ems-small.en-q5.bin --out out/ft     # fine-tuned slot
$B run transcript.json --taps taps.json --out out/text_only    # skip ASR: test extraction alone
$B make-replay call.wav call.replay --taps taps.json           # wav -> replay packet file
$B run call.replay --asr-model models/ggml-small.en.bin        # replay input (packets, taps inside)
```
Demo: `$B run mocks/demo_call/transcript.truth.json --taps mocks/demo_call/taps.json --out out/demo`.

## Inputs
| Input | Format |
|---|---|
| audio | `.wav` — 16 kHz mono 16-bit preferred; other rates/channels/float32 are converted in memory |
| replay | `.replay`/`.bin` — length-prefixed packets (`docs/WIRE_FORMAT.md`) |
| transcript | `.json` — `[{"start_ms":0,"end_ms":2000,"text":"..."}]` or a previous `transcript.raw.json` |
| taps | `[{"clip_ms":52500,"source":"button","gesture":"mark"}]`; source `button|knock|snap|tablet`; gesture `mark` (default) `yes|no|arrival|handoff`. `clip_ms` = ms from audio start (wav/json) or clip-boot ms (replay) |
| config (`--config`) | `{"call_id":"c1","start_time":"2026-11-15T14:00:00-05:00","asr":{"model":"...","threads":4,"use_initial_prompt":true},"tagger":null,"vad":{...},"merge":{"windowMs":3000,"extendedMs":10000},"pii_scrub":true}` — all optional |

Flags: `--asr-model <path>`, `--tagger <path|none>` (Core ML, macOS only; on Linux it's ignored with a note in timing.json), `--threads`, `--call-id`, `--start`, `--dict <dir>` (default: finds `shared/`), `--no-prompt`, `--no-pii`.

## Outputs (in `--out`)
| File | Contents |
|---|---|
| `transcript.raw.json` | `{call_id, asr_model, initial_prompt, segments:[{id:"s1",start_ms,end_ms,text,avg_logprob}]}` — never edited |
| `transcript.clean.json` | `{segments:[{raw_span,text}], corrections:[{id,raw_span,raw_range:[a,b],original,replacement,rule}]}` |
| `events.json` | event list (format below) |
| `soap.md`, `chart.md`, `imist_ambo.md` | rendered by code; every line cites `[eN]`; missing = "not heard" |
| `nemsis.xml` | NEMSIS v3.5.1 EMSDataSet, **UNVALIDATED**; eTimes.11/12, eVitals, eMedications (RxNorm + route/unit codes), eProcedures (no SNOMED yet) |
| `timing.json` | seconds per stage (vad, asr_total, cleanup, extract_rules, merge, pii, render), stats, model names |

Event: `{"id","call_id","time"(ISO),"t_ms","type","fields","source","quote","raw_span","confidence","models":{"asr","extract"},"receipts":{field:{"raw_span","quote","raw_range","inferred"?}},"flags":["confirm"|"inferred"|"unlabeled"],"tap_source","tap_clip_ms"}`.
Types: vitals, medication, procedure, status, dispatch, transport, tap, consent, arrival, handoff, audio_gap. `status.fields.kind` ∈ patient, symptom, history, allergy, home_med, prior_to_arrival_med, med_not_given, drug_mention, condition, not_done.
Vitals field names: `bp_systolic bp_diastolic bp_method heart_rate resp_rate spo2 etco2 glucose gcs temp pain mental_status pupils ecg o2_on`. Medication: `drug`(generic) `dose unit route drug_as_heard`.

Determinism: same input + config + threads ⇒ same files, except `timing.json`.

## Known gaps
- Word times inside a segment are proportional estimates (no token timestamps yet).
- Free-text fields (dispatch, chief complaint, destination, allergy, history) are raw quotes ≤5 words.
- Units not spoken are filled from the protocol dose only when unique, flagged `inferred` + `*`.
- Procedures have no SNOMED codes; NEMSIS XML not schema-validated.
- `mocks/demo_call/demo_call.replay` is not in git (binary); regenerate: `python3 core/tools/make_demo_call.py /tmp/demo.wav mocks/demo_call && $B make-replay /tmp/demo.wav mocks/demo_call/demo_call.replay --taps mocks/demo_call/taps.json` (needs espeak-ng, ffmpeg).
- Performance: 166 s demo audio → 51 s ASR on 4 x86 threads (small.en, CPU).

Report bugs in `docs/REVIEW.md`.
