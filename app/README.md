# Earshot iPad app (pipeline test harness)

Barebones UI to exercise `EarshotCore` end to end; the real screens come later. All pipeline logic lives in ../core (tested on Linux).

```bash
app/scripts/fetch_deps.sh      # whisper.xcframework + models + xcodegen
open app/Earshot.xcodeproj
```
- One screen: transport picker (Replay / BLE / Wi-Fi), ASR slot (stock / fine-tuned), Start/Stop/Mark/Arrived/Nurse accept, link status, event list (tap → receipt), the four outputs, export via share sheet, sign & wipe, BLE throughput test.
- Simulator: Replay plays `mocks/demo_call/demo_call.replay` through the real pipeline (CPU whisper; tiny.en is faster there).
- Kept for the real UI: `AppModel` (call lifecycle, model slots, export, ledger), `Transport/` (BLE, Wi-Fi, throughput meter), `Services/` (encrypted CallStore, arrival Geofence, Foundation Models tap suggestions with span-citation check).
