// Reference implementation of the clip side of the wire contract
// (docs/FIRMWARE_CONTRACT.md). Portable C, no RTOS/Arduino; host-tested.
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "earshot_proto.h"
#ifdef __cplusplus
extern "C" {
#endif

/* ---------- iPad -> clip messages ---------- */
typedef enum { ES_IN_NONE = 0, ES_IN_ACK, ES_IN_CLOCK, ES_IN_FORCE_OFF_MSG, ES_IN_TUNING, ES_IN_BAD } es_in_kind;
typedef struct {
    es_in_kind kind;
    uint16_t acked_seq;        /* ES_IN_ACK */
    uint64_t epoch_ms;         /* ES_IN_CLOCK: iPad epoch ms at the moment of writing */
    uint16_t knock_threshold, min_gap_ms, window_ms, snap_threshold;   /* ES_IN_TUNING */
} es_incoming;
/* Parse one packet written by the iPad (BLE write, or one TCP frame body). */
es_incoming es_parse_incoming(const uint8_t *p, size_t len);

/* ---------- tap queue: resend until acked ---------- */
#define ES_TAPQ_LEN 16
#define ES_TAP_RESEND_MS 500
typedef struct { bool used; uint16_t seq; uint8_t pkt[ES_HDR_SIZE + ES_TAP_PAYLOAD]; uint32_t last_sent; uint8_t sends; } es_tap_slot;
typedef struct { es_tap_slot slot[ES_TAPQ_LEN]; uint16_t next_seq; uint32_t dropped; } es_tap_queue;
void es_tapq_init(es_tap_queue *q);
/* Queue a tap; returns its seq. If full, the oldest unacked tap is dropped (counted). */
uint16_t es_tapq_push(es_tap_queue *q, uint32_t now_ms, uint8_t gesture, uint8_t source, uint32_t press_ms);
void es_tapq_ack(es_tap_queue *q, uint16_t seq);
/* Calls send() for every tap due (new, or unacked for >= ES_TAP_RESEND_MS). Returns number sent. */
int es_tapq_service(es_tap_queue *q, uint32_t now_ms, bool link_up, void (*send)(const uint8_t *, size_t, void *), void *ctx);
int es_tapq_pending(const es_tap_queue *q);

/* ---------- audio resend ring (RAM only, never flash) ---------- */
#define ES_RING_FRAMES 150     /* 3 s */
typedef struct { uint8_t pkt[ES_RING_FRAMES][ES_HDR_SIZE + ES_AUDIO_PAYLOAD]; uint32_t clip[ES_RING_FRAMES]; int head, count; } es_audio_ring;
void es_ring_clear(es_audio_ring *r);      /* zeroes memory: called on stop/refusal */
uint8_t *es_ring_push(es_audio_ring *r, uint32_t clip_ms);   /* slot to fill with the new packet */
/* After a link drop: resend frames captured since (lost_at - 500 ms), oldest first, excluding the newest. */
int es_ring_resend_since(const es_audio_ring *r, uint32_t lost_at_ms, void (*send)(const uint8_t *, size_t, void *), void *ctx);

/* ---------- audio frame builder ---------- */
typedef struct { uint16_t seq; int predictor; int index; } es_audio_enc;
/* Build one audio packet (7 + 164 bytes) from 320 samples. Returns size. */
size_t es_audio_packet(es_audio_enc *e, uint8_t *out, uint32_t clip_ms, const int16_t *pcm);

#ifdef __cplusplus
}
#endif
