// Earshot wire format — must match core/Sources/EarshotCore/Wire/Packet.swift
// and docs/WIRE_FORMAT.md. Little-endian. 7-byte header + payload.
#pragma once
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif

enum { ES_PKT_AUDIO = 0x01, ES_PKT_TAP = 0x02, ES_PKT_STATE = 0x03, ES_PKT_CLOCK = 0x04, ES_PKT_ACK = 0x05 };
enum { ES_GESTURE_MARK = 0, ES_GESTURE_START = 1, ES_GESTURE_STOP = 2, ES_GESTURE_YES = 3, ES_GESTURE_NO = 4 };
enum { ES_SRC_BUTTON = 0, ES_SRC_KNOCK = 1, ES_SRC_SNAP = 2 };
enum { ES_STATE_OFF = 0, ES_STATE_ASKING = 1, ES_STATE_LISTENING = 2, ES_STATE_REFUSED = 3 };
enum { ES_FLAG_USB = 0x01, ES_FLAG_BATT_LOW = 0x02, ES_FLAG_TONE = 0x04 };

#define ES_HDR_SIZE 7
#define ES_SAMPLE_RATE 16000
#define ES_FRAME_SAMPLES 320          /* 20 ms */
#define ES_AUDIO_PAYLOAD 164          /* 4-byte ADPCM block header + 160 bytes */
#define ES_TAP_PAYLOAD 6
#define ES_MAX_PACKET (ES_HDR_SIZE + ES_AUDIO_PAYLOAD)

// GATT (matches app/Earshot/Transport/GATT.swift)
#define ES_GATT_SERVICE "E5A1D000-0B5E-4C6B-9C5E-EA5407000000"
#define ES_GATT_AUDIO   "E5A1D001-0B5E-4C6B-9C5E-EA5407000000"
#define ES_GATT_TAP     "E5A1D002-0B5E-4C6B-9C5E-EA5407000000"
#define ES_GATT_STATE   "E5A1D003-0B5E-4C6B-9C5E-EA5407000000"
#define ES_GATT_CLOCK   "E5A1D004-0B5E-4C6B-9C5E-EA5407000000"
#define ES_GATT_ACK     "E5A1D005-0B5E-4C6B-9C5E-EA5407000000"
#define ES_WIFI_PORT 7070

static inline void es_put16(uint8_t *p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }
static inline void es_put32(uint8_t *p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = (v >> (8 * i)) & 0xFF; }
static inline uint16_t es_get16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static inline uint32_t es_get32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static inline uint64_t es_get64(const uint8_t *p) { return (uint64_t)es_get32(p) | ((uint64_t)es_get32(p + 4) << 32); }

static inline size_t es_header(uint8_t *out, uint8_t type, uint16_t seq, uint32_t clip_ms) {
    out[0] = type; es_put16(out + 1, seq); es_put32(out + 3, clip_ms); return ES_HDR_SIZE;
}
static inline size_t es_tap_packet(uint8_t *out, uint16_t seq, uint32_t clip_ms, uint8_t gesture, uint8_t source, uint32_t press_ms) {
    es_header(out, ES_PKT_TAP, seq, clip_ms);
    out[7] = gesture; out[8] = source; es_put32(out + 9, press_ms); return ES_HDR_SIZE + ES_TAP_PAYLOAD;
}
static inline size_t es_state_packet(uint8_t *out, uint16_t seq, uint32_t clip_ms, uint8_t state, uint8_t flags) {
    es_header(out, ES_PKT_STATE, seq, clip_ms); out[7] = state; out[8] = flags; return ES_HDR_SIZE + 2;
}

#ifdef __cplusplus
}
#endif
