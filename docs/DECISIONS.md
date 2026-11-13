# Decisions

| # | Decision | Alternatives | Why |
|---|---|---|---|
| 1 | Branch `overnight` lives in **`shourya0523/earshot-data`** (user's call): pushes to `sbalsara05/EarShot` are refused (GitHub App not connected). Commits authored `shourya0523 <shourya0523@users.noreply.github.com>`. The data agent works on `claude/eager-volta-za1pmi` in the same repo and polls every branch for `docs/PIPELINE_READY.md`. | API/MCP writes (also refused) | only working write path |
| 2 | Phonetic key = own Metaphone port (`core/tools/phonetic.py` ≡ `Phonetic.swift`), not Double Metaphone | pip `metaphone` package | running downloaded package code was blocked; one tiny shared algorithm keeps Python and Swift identical |
| 3 | ADPCM frame = 4-byte block header + 160 bytes (164 B payload, 171 B packet) | 160 B with no state | each frame decodes alone, so a lost frame never desyncs; 68.4 kbps |
| 4 | `seq` is a per-packet-type counter | one shared counter | audio gaps must be detectable from audio seq alone; tap seq is the ack id |
| 5 | Little-endian wire format | network order | ESP32 and Apple are LE; zero-cost |
| 6 | Unspoken unit is **never filled**. If the amount matches exactly one protocol dose, `fields.unit_suggested` carries it and outputs say "unit not heard; protocol dose is in mg" | fill + flag | "anything not heard stays blank"; matches the data agent's ground truth |
| 7 | Patient info, symptoms, history, allergies, home meds are `status` events with `fields.kind` | new event types | spec fixes the type list |
| 8 | Condition events keep the medic's own word ("compensating"), never a definition | expansion text | expansion read like a diagnosis |
| 9 | Common-word drug aliases (epi, mag, sugar…) need dose/route/verb nearby (`context_required_aliases`) | always match | avoids false meds |
| 10 | **PII is kept by default** (user's call: the ePCR needs name/DOB/address). Scrubber stays available: `--pii-scrub` / `"pii_scrub": true` tokenizes quotes and fields; raw transcript always stays raw | scrub by default | user instruction |
| 11 | Sentence/clause punctuation from Whisper used as boundaries for free-text capture | none | stops "allergic to penicillin she takes…" run-ons |
| 12 | whisper.cpp linked as a system library (pkg-config), `EARSHOT_NO_WHISPER=1` to build without | vendor sources in SwiftPM | ggml build flags are complex; system lib works on Linux/macOS, xcframework on iOS |
| 13 | Greedy, temperature 0, no fallback, fixed threads | default sampling | repeatable eval |
| 14 | Demo audio from espeak-ng; WAV never committed, only the transcript/taps (+ replay regenerable) | commit WAV | "no audio on disk"; repo size |
| 15 | Whisper non-speech tags inside a segment (`[beep]`, `(siren)`) are dropped in cleanup as a logged correction; whole-segment tags are dropped before segment ids are assigned | keep | data agent finding (stock small.en emits them in siren noise) |
| 16 | Sound-alike (phonetic) drug matches need a unit, route or give-verb within 3 tokens and are always "please confirm" | number nearby | "lights", "General" falsely matched in golden test |
| 17 | The 1.4 MB demo replay file is not in git; regenerate with `earshot-eval make-replay` | commit binary | repo size; history rewritten before first push |
