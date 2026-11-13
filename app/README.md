# Earshot iPad app

Thin SwiftUI layer over `EarshotCore` (../core). All pipeline logic lives in the package and is tested on Linux.

```bash
app/scripts/fetch_deps.sh      # whisper.xcframework + models + xcodegen
open app/Earshot.xcodeproj
```
- Simulator: Settings → Transport is "Replay (demo)" by default; Connect → Start call plays `mocks/demo_call/demo_call.replay` through the real pipeline (whisper.cpp on CPU; tiny.en is faster there).
- iPad: Transport "Bluetooth LE"; pair with the clip on first connect. Use Connect → Bluetooth throughput test first.

Screens: Connect/status · Live timeline (dispatch-vs-found flag, vitals-due reminder) · Recall (unlabeled taps, please-confirm, not heard) · Draft (SOAP / CHART / IMIST-AMBO / NEMSIS tabs, tap a line for its receipt, share-sheet export, sign & wipe) · Handoff (nurse accept = eTimes.12, wall-time clock, arrival geofence + button) · Ledger (audio sent: 0 bytes) · Settings (stock vs fine-tuned A/B, tagger, Apple Intelligence).
