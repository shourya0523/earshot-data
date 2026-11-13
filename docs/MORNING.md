# Morning hand-off (pipeline agent)

**Repo/branch:** `shourya0523/earshot-data` @ `overnight`. Pushes to `sbalsara05/EarShot` were refused all night (GitHub App not connected for that org). Once that is fixed, push this branch there: `git push https://github.com/sbalsara05/EarShot overnight`. The data agent works on `claude/eager-volta-za1pmi` in the same repo.

## What works (verified on Linux, Swift 6.2.1)
- **`EarshotCore` pipeline, end to end with stock models:** wire decode → ADPCM → adaptive VAD → whisper.cpp `small.en` → cleanup → rules extraction → tap merge → SOAP / CHART / IMIST-AMBO / NEMSIS XML, all rendered by code with `[eN]` receipts and "not heard".
  - Demo: 166 s of audio transcribes in about 51 s on 4 CPU threads.
  - At 10 dB SNR (cab rumble + monitor beeps), all 14 utterances are still segmented.
- **`earshot-eval`:** `run`, `make-replay`, `check-stream`, `fake-clip`. Hand-off doc: `docs/PIPELINE_READY.md`.
- **Tests:** `swift test` runs 64 tests.
  - Unit tests: extraction, cleanup, merge, PII, phonetic.
  - One regression test per data-agent review finding.
  - Golden files per renderer.
  - `LiveSession` (the live app path).
  - Conformance checker.
  - NEMSIS validated with `xmllint` against the vendored v3.5.1 XSDs.
- **Review:** every critical and high item in `docs/REVIEW.md` is fixed except H8, which is partial; responses are recorded in that file. M8 (PII scrub gaps) is won't-fix because PII is kept by default, as you asked.
- **Dictionary:**
  - `shared/formulary.json`: 72 drugs and 57 home meds, built from MA protocols, RxNorm, openFDA and NEMSIS, plus the data agent's filtered additions.
  - `shared/ems_terms.json`: 360 terms.
  - Both rebuild offline with `core/tools/build_dictionary.py --offline`.
- **Firmware contract:**
  - Specs: `docs/WIRE_FORMAT.md` and `docs/FIRMWARE_CONTRACT.md` (MUST/SHOULD ids, bring-up checklist).
  - Portable reference C in `firmware/common`: wire helpers, tap resend queue, 3 s RAM resend ring, consent state machine, and a knock/snap detector using the data agent's tuned parameters. `make -C firmware/common/test` passes 248 checks with 0 false taps.
  - Swift ↔ C ADPCM match bit for bit.
- **Contract tooling:**
  - `earshot-eval check-stream` validates a clip capture against the contract.
  - `earshot-eval fake-clip` is a reference clip over TCP.
  - `core/tools/capture_clip.py` stands in for the iPad during bring-up.
  - The demo replay passes every conformance check.

## Stubbed / not verified
- **iPad app (`app/`):** a barebones pipeline test screen on purpose; real screens come from you. It has never been compiled: there is no Xcode here. The code and XcodeGen project are written against iOS 26 APIs. Expect a few compile fixes on first build.
- **BLE / Wi-Fi sources and the throughput test:** written but untested. They need a real iPad and clip.
- **Tagger (Core ML) and Foundation Models:** wired behind flags and untested. No tagger model exists yet, and Foundation Models doesn't run on Linux.
- **Procedures:** no SNOMED codes, so NEMSIS eProcedures.03 = Not Recorded.
- **NEMSIS placeholders:** these required elements can't be nil, so they hold placeholders listed in a `REQUIRES CREW ENTRY` comment: eTimes.03, eTimes.13, eResponse.23 when no mode was heard, and eDispatch.01 when unmapped. Agency ids come from config, with placeholder defaults.
- **Board firmware:** removed by request. Only the contract and `firmware/common` remain.

## Needs a real device
1. **Clip bring-up:** follow the checklist at the end of `docs/FIRMWARE_CONTRACT.md`. Capture over Wi-Fi, then `check-stream` and `run`.
2. **iPad:** `app/scripts/fetch_deps.sh` → open `app/Earshot.xcodeproj` → set Signing team → run.
   - Simulator: Replay transport plays `mocks/demo_call/demo_call.replay`; tiny.en is faster there.
   - iPad: BLE throughput test for 2 min (pass: ≥ 80 kbps, < 1 % loss).
3. **Knock/snap thresholds:** re-tune on real case recordings (`data/RECORDING.md` on the data branch).

## Next steps per person
- **Firmware owner:** compile `firmware/common/*.c` into the board build, implement the GATT/Wi-Fi glue per WIRE_FORMAT, and pass `check-stream`.
- **iOS owner:** build the app, fix compile errors, swap in the real screens. `AppModel` + `LiveSession` + `PacketSource` are the API.
- **Data agent:** re-run eval on `overnight` (VAD, diagnosis guard, units and NEMSIS all changed). Use `--start` for time scoring, and `vad.mode: "fixed"` to A/B against no VAD.
- **Demo/pitch:**
  - Ledger shows "audio sent: 0 bytes".
  - Receipts on every line.
  - NEMSIS passes the XSD.
  - Wall time comes from arrival → nurse accept.
  - The dispatch-vs-found flag catches "called for a fall, turned out to be chest pain".
