// Host tests: gcc -I.. ../*.c test_main.c -lm && ./a.out
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "../earshot_proto.h"
#include "../adpcm.h"
#include "../state_machine.h"
#include "../es_wire.h"

static int fails = 0, checks = 0;
#define CHECK(c, msg) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d %s\n", __FILE__, __LINE__, msg); } } while (0)

static void test_state_machine(void) {
    es_sm sm; es_sm_init(&sm); es_action a;
    CHECK(!es_sm_audio_allowed(&sm), "no audio when OFF");
    // single press -> ASKING
    es_sm_button(&sm, true, 1000, &a); CHECK(es_sm_button(&sm, false, 1100, &a), "release fires");
    CHECK(sm.state == ES_STATE_ASKING && a.tone == ES_TONE_RISING && a.tap_gesture == ES_GESTURE_START, "OFF->ASKING");
    CHECK(!es_sm_audio_allowed(&sm), "no audio when ASKING");
    // single press -> LISTENING (yes)
    es_sm_button(&sm, true, 2000, &a); es_sm_button(&sm, false, 2100, &a);
    CHECK(sm.state == ES_STATE_LISTENING && a.tap_gesture == ES_GESTURE_YES && a.tone == ES_TONE_HIGH, "yes");
    CHECK(es_sm_audio_allowed(&sm), "audio when LISTENING");
    // mark by button
    es_sm_button(&sm, true, 3000, &a); es_sm_button(&sm, false, 3080, &a);
    CHECK(a.emit_tap && a.tap_gesture == ES_GESTURE_MARK && a.tap_source == ES_SRC_BUTTON && a.tap_press_ms == 3000, "button mark uses press time");
    es_sm_button(&sm, true, 4000, &a); es_sm_button(&sm, false, 4010, &a);
    CHECK(!a.emit_tap || a.tap_press_ms != 4000, "presses under 30 ms are debounced");
    // long press -> OFF + clear
    es_sm_button(&sm, true, 5000, &a);
    CHECK(!es_sm_tick(&sm, 6000, &a), "not long yet");
    CHECK(es_sm_tick(&sm, 6500, &a) && sm.state == ES_STATE_OFF && a.clear_buffers && a.tone == ES_TONE_FALLING, "long -> OFF");
    CHECK(!es_sm_button(&sm, false, 6600, &a), "release after long does nothing");
    // refusal path
    es_sm_button(&sm, true, 7000, &a); es_sm_button(&sm, false, 7100, &a);
    es_sm_button(&sm, true, 8000, &a); es_sm_tick(&sm, 9600, &a);
    CHECK(sm.state == ES_STATE_OFF && a.log_refusal && a.tap_gesture == ES_GESTURE_NO && sm.refusals == 1, "refusal logged, OFF");
    // iPad force off
    es_sm_input(&sm, ES_IN_SINGLE, ES_SRC_BUTTON, 12000); es_sm_input(&sm, ES_IN_SINGLE, ES_SRC_BUTTON, 12100);
    a = es_sm_input(&sm, ES_IN_FORCE_OFF, 0, 13000); CHECK(sm.state == ES_STATE_OFF && a.clear_buffers, "force off");
}

static void test_adpcm(void) {
    int16_t pcm[ES_FRAME_SAMPLES], dec[ES_FRAME_SAMPLES];
    for (int i = 0; i < ES_FRAME_SAMPLES; i++)   // same vector as WireTests.testADPCMMatchesFirmwareVector
        pcm[i] = (int16_t)(12000 * sin(i * 2 * M_PI * 300 / 16000) + 3000 * sin(i * 2 * M_PI * 1700 / 16000));
    es_adpcm_state st = {0, 0}; uint8_t blk[ES_AUDIO_PAYLOAD];
    CHECK(es_adpcm_encode_block(pcm, ES_FRAME_SAMPLES, &st, blk) == ES_AUDIO_PAYLOAD, "block size 164");
    CHECK(es_adpcm_decode_block(blk, ES_AUDIO_PAYLOAD, dec) == ES_FRAME_SAMPLES, "decode count");
    FILE *f = fopen("adpcm_vector.bin", "wb"); fwrite(blk, 1, sizeof blk, f); fclose(f);
    uint8_t p[ES_MAX_PACKET];
    CHECK(es_tap_packet(p, 2, 99, ES_GESTURE_MARK, ES_SRC_BUTTON, 95) == 13 && p[0] == 2 && p[1] == 2 && p[3] == 99 && p[8] == 0 && p[9] == 95, "tap packet layout matches Swift");
}

static int sent_count; static uint8_t last_sent[256]; static size_t last_len;
static void cap(const uint8_t *p, size_t n, void *ctx) { (void)ctx; sent_count++; memcpy(last_sent, p, n); last_len = n; }

static void test_wire(void) {
    // incoming parse
    uint8_t ack[9] = {ES_PKT_ACK, 0, 0, 0, 0, 0, 0, 7, 1};
    es_incoming m = es_parse_incoming(ack, sizeof ack); CHECK(m.kind == ES_IN_ACK && m.acked_seq == 263, "parse ack");
    uint8_t clk[15] = {ES_PKT_CLOCK, 0, 0, 0, 0, 0, 0, 0x80, 0x1b, 0x5c, 0x6a, 0x9a, 0x01, 0, 0};
    m = es_parse_incoming(clk, sizeof clk); CHECK(m.kind == ES_IN_CLOCK && m.epoch_ms == 0x019a6a5c1b80ULL, "parse clock");
    uint8_t off[9] = {ES_PKT_STATE, 0, 0, 0, 0, 0, 0, ES_STATE_OFF, 0};
    CHECK(es_parse_incoming(off, sizeof off).kind == ES_IN_FORCE_OFF_MSG, "parse force off");
    uint8_t on[9] = {ES_PKT_STATE, 0, 0, 0, 0, 0, 0, ES_STATE_LISTENING, 0};
    CHECK(es_parse_incoming(on, sizeof on).kind == ES_IN_NONE, "iPad cannot force LISTENING");
    CHECK(es_parse_incoming(ack, 3).kind == ES_IN_BAD, "short packet rejected");
    // tap queue: resend until acked
    es_tap_queue q; es_tapq_init(&q); sent_count = 0;
    uint16_t s0 = es_tapq_push(&q, 1000, ES_GESTURE_MARK, ES_SRC_BUTTON, 990);
    CHECK(es_tapq_service(&q, 1000, false, cap, NULL) == 0, "no send while link down");
    CHECK(es_tapq_service(&q, 1001, true, cap, NULL) == 1 && last_len == 13 && last_sent[0] == ES_PKT_TAP, "first send");
    CHECK(es_tapq_service(&q, 1200, true, cap, NULL) == 0, "not resent before 500 ms");
    CHECK(es_tapq_service(&q, 1501, true, cap, NULL) == 1, "resent after 500 ms");
    es_tapq_ack(&q, s0); CHECK(es_tapq_pending(&q) == 0 && es_tapq_service(&q, 3000, true, cap, NULL) == 0, "acked tap stops");
    for (int i = 0; i < ES_TAPQ_LEN + 2; i++) es_tapq_push(&q, 4000, ES_GESTURE_MARK, ES_SRC_BUTTON, 4000);
    CHECK(q.dropped == 2 && es_tapq_pending(&q) == ES_TAPQ_LEN, "full queue drops oldest");
    // audio ring + packet
    static es_audio_ring r; es_ring_clear(&r);
    es_audio_enc enc = {0, 0, 0}; int16_t pcm[ES_FRAME_SAMPLES] = {0};
    for (int f = 0; f < 200; f++) { uint8_t *slot = es_ring_push(&r, 1000 + f * 20); CHECK(es_audio_packet(&enc, slot, 1000 + f * 20, pcm) == 171, "audio packet 171 B"); }
    CHECK(r.count == ES_RING_FRAMES && enc.seq == 200, "ring keeps 3 s");
    sent_count = 0; int n = es_ring_resend_since(&r, 1000 + 190 * 20, cap, NULL);
    CHECK(n == 34 && sent_count == 34, "resend frames since drop - 500 ms");   // frames 165..198 (199 is the newest)
    es_ring_clear(&r); CHECK(r.count == 0 && r.pkt[5][0] == 0, "clear zeroes audio");
    uint8_t st[16]; CHECK(es_state_packet(st, 0, 0, ES_STATE_LISTENING, ES_FLAG_USB) == 10 && st[9] == ES_PROTO_VERSION, "state carries proto version");
}

int main(void) {
    test_state_machine(); test_adpcm(); test_wire();
    printf("%d/%d checks passed\n", checks - fails, checks);
    return fails ? 1 : 0;
}
