# firmware/common

Portable C for the clip side of the contract (`docs/FIRMWARE_CONTRACT.md`, bytes in `docs/WIRE_FORMAT.md`). No RTOS/Arduino dependencies: compile these files into any board build unchanged. Mirrored by `EarshotCore` in Swift.

| File | What it gives the board |
|---|---|
| `earshot_proto.h` | packet types, sizes, header/tap/state builders, GATT UUIDs, `ES_PROTO_VERSION` |
| `adpcm.c/.h` | IMA ADPCM, 320 samples → 164-byte block; bit-exact with the Swift decoder |
| `es_wire.c/.h` | parse iPad writes (ack, clock, force-OFF); tap queue that resends until acked; 3 s audio resend ring (RAM only); audio packet builder |
| `state_machine.c/.h` | consent gate and button gestures (single / long press); `es_sm_audio_allowed()` |

Board glue left to the firmware owner: I2S/codec capture at 16 kHz, button GPIO (the only tap input), tones/vibration, BLE GATT server, Wi-Fi soft AP + TCP. A board loop is roughly:

```c
read 320 samples (silence while a tone plays + 200 ms)
es_sm_button()/es_sm_tick() -> apply es_action (tone, es_ring_clear, es_tapq_push, state packet)
if (es_sm_audio_allowed(&sm)) es_audio_packet(&enc, es_ring_push(&ring, now), now, pcm) -> notify
es_tapq_service(); on writes: es_parse_incoming() -> es_tapq_ack / clock offset / force OFF
```

Host tests: `make -C firmware/common/test` (state machine, ADPCM vector for the Swift test, wire helpers).
