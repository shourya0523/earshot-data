# firmware/common

Portable C shared by the clip firmware (not in this repo yet) and mirrored by `EarshotCore` in Swift:

- `earshot_proto.h` — wire format (7-byte header, packet types, tap/state payloads) and GATT UUIDs. Matches `core/Sources/EarshotCore/Wire/Packet.swift` and `docs/WIRE_FORMAT.md`.
- `adpcm.c/.h` — IMA ADPCM, 320 samples → 164-byte block. Bit-exact with the Swift decoder (`WireTests.testADPCMMatchesFirmwareVector` reads `test/adpcm_vector.bin`).
- `state_machine.c/.h` — consent gate: OFF → ASKING → LISTENING / REFUSED; button single/long, acoustic double/triple; audio allowed only while LISTENING.
- `tap_detect.c/.h` — knock/snap detection from raw mic samples; singles ignored, double = mark, triple = stop; muted during tones + 200 ms; thresholds tunable via the `state` characteristic.

Host tests (no hardware): `make -C firmware/common/test` — 32 checks incl. false-tap cases (bump, door slam, siren chirps, speech).
