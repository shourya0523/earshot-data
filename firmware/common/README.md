# firmware/common

Portable C for the clip side of the contract (`docs/FIRMWARE_CONTRACT.md`, bytes in `docs/WIRE_FORMAT.md`). No RTOS/Arduino dependencies: compile these files into any board build unchanged. Mirrored by `EarshotCore` in Swift.

| File | What it gives the board |
|---|---|
| `earshot_proto.h` | packet types, sizes, header/tap/state builders, GATT UUIDs, `ES_PROTO_VERSION` |
| `adpcm.c/.h` | IMA ADPCM, 320 samples → 164-byte block; bit-exact with the Swift decoder |
| `es_wire.c/.h` | parse iPad writes (ack, clock, force-OFF, tuning); tap queue that resends until acked; 3 s audio resend ring (RAM only); audio packet builder |
| `state_machine.c/.h` | consent gate and gestures (button and knock-only builds); `es_sm_audio_allowed()` |
| `tap_detect.c/.h` | knock/snap detector (data agent's tuned parameters); mute during tones |

Board glue left to the firmware owner: I2S/codec capture at 16 kHz, button GPIO, tones/vibration, BLE GATT server, Wi-Fi soft AP + TCP. A board loop is roughly:

```c
read 320 samples -> es_tap_process() -> es_sm_input() on double/triple
es_sm_button()/es_sm_tick() -> apply es_action (tone + es_tap_mute, es_ring_clear, es_tapq_push, state packet)
if (es_sm_audio_allowed(&sm)) es_audio_packet(&enc, es_ring_push(&ring, now), now, pcm) -> notify
es_tapq_service(); on writes: es_parse_incoming() -> es_tapq_ack / clock offset / force OFF / tuning
```

Host tests: `make -C firmware/common/test` (state machine, detector incl. false-tap clips, ADPCM vector for the Swift test, wire helpers).
