# Decisions

| # | Decision | Alternatives | Why |
|---|---|---|---|
| 1 | Push to `overnight` as instructed. Git push was 403 (GitHub App not connected); user OK'd pushing via the GitHub API, so those commits are authored by the app, not `shourya0523`. Local commits keep `shourya0523 <shourya0523@users.noreply.github.com>`. | wait for access | data agent needs the code |
| 2 | Phonetic key = own Metaphone port (`core/tools/phonetic.py` ≡ `Phonetic.swift`), not Double Metaphone | pip `metaphone` package | running downloaded package code was blocked; one tiny shared algorithm keeps Python and Swift identical |
| 3 | ADPCM frame = 4-byte block header + 160 bytes (164 B payload, 171 B packet) | 160 B with no state | each frame decodes alone, so a lost frame never desyncs; 68.4 kbps |
| 4 | `seq` is a per-packet-type counter | one shared counter | audio gaps must be detectable from audio seq alone; tap seq is the ack id |
| 5 | Little-endian wire format | network order | ESP32 and Apple are LE; zero-cost |
| 6 | Unspoken unit filled only when the amount matches exactly one protocol dose; flagged `inferred`, `*`, receipt says why | leave blank | spec example ("324 of aspirin") shows mg; still visible and confirmable |
| 7 | Patient info, symptoms, history, allergies, home meds are `status` events with `fields.kind` | new event types | spec fixes the type list |
| 8 | Condition events keep the medic's own word ("compensating"), never a definition | expansion text | expansion read like a diagnosis |
| 9 | Common-word drug aliases (epi, mag, sugar…) need dose/route/verb nearby (`context_required_aliases`) | always match | avoids false meds |
| 10 | PII scrub applies to events/outputs; `transcript.raw.json` stays raw | scrub raw | raw is the source of truth; eval data is synthetic |
| 11 | Sentence/clause punctuation from Whisper used as boundaries for free-text capture | none | stops "allergic to penicillin she takes…" run-ons |
| 12 | whisper.cpp linked as a system library (pkg-config), `EARSHOT_NO_WHISPER=1` to build without | vendor sources in SwiftPM | ggml build flags are complex; system lib works on Linux/macOS, xcframework on iOS |
| 13 | Greedy, temperature 0, no fallback, fixed threads | default sampling | repeatable eval |
| 14 | Demo audio from espeak-ng; WAV never committed, only the transcript/taps (+ replay regenerable) | commit WAV | "no audio on disk"; repo size |
