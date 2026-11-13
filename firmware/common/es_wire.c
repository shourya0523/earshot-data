#include "es_wire.h"
#include "adpcm.h"
#include <string.h>

es_incoming es_parse_incoming(const uint8_t *p, size_t len) {
    es_incoming m; memset(&m, 0, sizeof m);
    if (len < ES_HDR_SIZE) { m.kind = ES_IN_BAD; return m; }
    switch (p[0]) {
    case ES_PKT_ACK:
        if (len < ES_HDR_SIZE + 2) { m.kind = ES_IN_BAD; break; }
        m.kind = ES_IN_ACK; m.acked_seq = es_get16(p + 7); break;
    case ES_PKT_CLOCK:
        if (len < ES_HDR_SIZE + 8) { m.kind = ES_IN_BAD; break; }
        m.kind = ES_IN_CLOCK; m.epoch_ms = es_get64(p + 7); break;
    case ES_PKT_STATE:
        if (len < ES_HDR_SIZE + 2) { m.kind = ES_IN_BAD; break; }
        if (len >= ES_HDR_SIZE + 10) {
            m.kind = ES_IN_TUNING;
            m.knock_threshold = es_get16(p + 9); m.min_gap_ms = es_get16(p + 11);
            m.window_ms = es_get16(p + 13); m.snap_threshold = es_get16(p + 15);
        }
        if (p[7] == ES_STATE_OFF) m.kind = ES_IN_FORCE_OFF_MSG;   /* force-off wins over tuning */
        else if (m.kind != ES_IN_TUNING) m.kind = ES_IN_NONE;     /* iPad may only force OFF */
        break;
    default: m.kind = ES_IN_BAD;
    }
    return m;
}

void es_tapq_init(es_tap_queue *q) { memset(q, 0, sizeof *q); }

uint16_t es_tapq_push(es_tap_queue *q, uint32_t now, uint8_t gesture, uint8_t source, uint32_t press_ms) {
    es_tap_slot *s = NULL, *oldest = NULL;
    for (int i = 0; i < ES_TAPQ_LEN; i++) {
        if (!q->slot[i].used) { s = &q->slot[i]; break; }
        if (!oldest || (uint16_t)(q->slot[i].seq - oldest->seq) > 0x8000) oldest = &q->slot[i];
    }
    if (!s) { s = oldest; q->dropped++; }
    memset(s, 0, sizeof *s);
    s->used = true; s->seq = q->next_seq++;
    es_tap_packet(s->pkt, s->seq, now, gesture, source, press_ms);
    return s->seq;
}

void es_tapq_ack(es_tap_queue *q, uint16_t seq) {
    for (int i = 0; i < ES_TAPQ_LEN; i++) if (q->slot[i].used && q->slot[i].seq == seq) q->slot[i].used = false;
}

int es_tapq_service(es_tap_queue *q, uint32_t now, bool link_up, void (*send)(const uint8_t *, size_t, void *), void *ctx) {
    if (!link_up) return 0;
    int n = 0;
    for (int i = 0; i < ES_TAPQ_LEN; i++) {
        es_tap_slot *s = &q->slot[i];
        if (s->used && (s->sends == 0 || now - s->last_sent >= ES_TAP_RESEND_MS)) {
            send(s->pkt, sizeof s->pkt, ctx); s->last_sent = now; if (s->sends < 255) s->sends++; n++;
        }
    }
    return n;
}

int es_tapq_pending(const es_tap_queue *q) { int n = 0; for (int i = 0; i < ES_TAPQ_LEN; i++) n += q->slot[i].used; return n; }

void es_ring_clear(es_audio_ring *r) { memset(r, 0, sizeof *r); }

uint8_t *es_ring_push(es_audio_ring *r, uint32_t clip_ms) {
    uint8_t *p = r->pkt[r->head];
    r->clip[r->head] = clip_ms;
    r->head = (r->head + 1) % ES_RING_FRAMES;
    if (r->count < ES_RING_FRAMES) r->count++;
    return p;
}

int es_ring_resend_since(const es_audio_ring *r, uint32_t lost_at, void (*send)(const uint8_t *, size_t, void *), void *ctx) {
    int n = 0;
    for (int i = r->count - 1; i >= 1; i--) {   /* oldest first, newest excluded (sent normally) */
        int k = (r->head - 1 - i + ES_RING_FRAMES) % ES_RING_FRAMES;
        if (r->clip[k] + 500 >= lost_at) { send(r->pkt[k], ES_HDR_SIZE + ES_AUDIO_PAYLOAD, ctx); n++; }
    }
    return n;
}

size_t es_audio_packet(es_audio_enc *e, uint8_t *out, uint32_t clip_ms, const int16_t *pcm) {
    es_header(out, ES_PKT_AUDIO, e->seq++, clip_ms);
    es_adpcm_state st = {e->predictor, e->index};
    es_adpcm_encode_block(pcm, ES_FRAME_SAMPLES, &st, out + ES_HDR_SIZE);
    e->predictor = st.predictor; e->index = st.index;
    return ES_HDR_SIZE + ES_AUDIO_PAYLOAD;
}
