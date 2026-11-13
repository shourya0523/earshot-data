// Host tests: gcc -I.. ../*.c test_main.c -lm && ./a.out
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "../earshot_proto.h"
#include "../adpcm.h"
#include "../state_machine.h"
#include "../tap_detect.h"

static int fails = 0, checks = 0;
#define CHECK(c, msg) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d %s\n", __FILE__, __LINE__, msg); } } while (0)

static void test_state_machine(void) {
    es_sm sm; es_sm_init(&sm, false); es_action a;
    CHECK(!es_sm_audio_allowed(&sm), "no audio when OFF");
    // single press -> ASKING
    es_sm_button(&sm, true, 1000, &a); CHECK(es_sm_button(&sm, false, 1100, &a), "release fires");
    CHECK(sm.state == ES_STATE_ASKING && a.tone == ES_TONE_RISING && a.tap_gesture == ES_GESTURE_START, "OFF->ASKING");
    CHECK(!es_sm_audio_allowed(&sm), "no audio when ASKING");
    // knocks don't count before consent on VoiceS3R
    a = es_sm_input(&sm, ES_IN_DOUBLE, ES_SRC_KNOCK, 1200); CHECK(sm.state == ES_STATE_ASKING && !a.emit_tap, "knock ignored in ASKING");
    // single press -> LISTENING (yes)
    es_sm_button(&sm, true, 2000, &a); es_sm_button(&sm, false, 2100, &a);
    CHECK(sm.state == ES_STATE_LISTENING && a.tap_gesture == ES_GESTURE_YES && a.tone == ES_TONE_HIGH, "yes");
    CHECK(es_sm_audio_allowed(&sm), "audio when LISTENING");
    // mark by button, then by knock and snap
    es_sm_button(&sm, true, 3000, &a); es_sm_button(&sm, false, 3080, &a);
    CHECK(a.emit_tap && a.tap_gesture == ES_GESTURE_MARK && a.tap_source == ES_SRC_BUTTON && a.tap_press_ms == 3000, "button mark uses press time");
    a = es_sm_input(&sm, ES_IN_DOUBLE, ES_SRC_SNAP, 4000); CHECK(a.tap_gesture == ES_GESTURE_MARK && a.tap_source == ES_SRC_SNAP, "snap mark");
    // long press -> OFF + clear
    es_sm_button(&sm, true, 5000, &a);
    CHECK(!es_sm_tick(&sm, 6000, &a), "not long yet");
    CHECK(es_sm_tick(&sm, 6500, &a) && sm.state == ES_STATE_OFF && a.clear_buffers && a.tone == ES_TONE_FALLING, "long -> OFF");
    CHECK(!es_sm_button(&sm, false, 6600, &a), "release after long does nothing");
    // refusal path
    es_sm_button(&sm, true, 7000, &a); es_sm_button(&sm, false, 7100, &a);
    es_sm_button(&sm, true, 8000, &a); es_sm_tick(&sm, 9600, &a);
    CHECK(sm.state == ES_STATE_OFF && a.log_refusal && a.tap_gesture == ES_GESTURE_NO && sm.refusals == 1, "refusal logged, OFF");
    // triple knock while listening = stop
    es_sm_input(&sm, ES_IN_SINGLE, ES_SRC_BUTTON, 10000); es_sm_input(&sm, ES_IN_SINGLE, ES_SRC_BUTTON, 10100);
    a = es_sm_input(&sm, ES_IN_TRIPLE, ES_SRC_KNOCK, 11000); CHECK(sm.state == ES_STATE_OFF && a.tap_gesture == ES_GESTURE_STOP, "triple stop");
    // iPad force off
    es_sm_input(&sm, ES_IN_SINGLE, ES_SRC_BUTTON, 12000); es_sm_input(&sm, ES_IN_SINGLE, ES_SRC_BUTTON, 12100);
    a = es_sm_input(&sm, ES_IN_FORCE_OFF, 0, 13000); CHECK(sm.state == ES_STATE_OFF && a.clear_buffers, "force off");
    // Feather acoustic consent: triple start, double yes, double mark, triple stop
    es_sm f; es_sm_init(&f, true);
    a = es_sm_input(&f, ES_IN_DOUBLE, ES_SRC_KNOCK, 0); CHECK(f.state == ES_STATE_OFF, "feather: double does not start");
    es_sm_input(&f, ES_IN_TRIPLE, ES_SRC_KNOCK, 0); CHECK(f.state == ES_STATE_ASKING, "feather: triple starts");
    es_sm_input(&f, ES_IN_DOUBLE, ES_SRC_KNOCK, 0); CHECK(f.state == ES_STATE_LISTENING, "feather: double = yes");
    a = es_sm_input(&f, ES_IN_DOUBLE, ES_SRC_KNOCK, 0); CHECK(a.tap_gesture == ES_GESTURE_MARK, "feather: double = mark");
    es_sm_input(&f, ES_IN_TRIPLE, ES_SRC_KNOCK, 0); CHECK(f.state == ES_STATE_OFF, "feather: triple = stop");
}

// ---- synthetic signals ----
#define SR 16000
static void add_knock(int16_t *b, int n, double t, double amp) {     // low thump, sharp attack, fast decay
    int s = (int)(t * SR);
    for (int i = 0; i < SR / 50 && s + i < n; i++) {
        double v = amp * exp(-i / (0.004 * SR)) * sin(2 * M_PI * 180 * i / SR);
        int x = b[s + i] + (int)v; b[s + i] = x > 32767 ? 32767 : x < -32768 ? -32768 : x;
    }
}
static unsigned rng = 1;
static double nz(void) { rng = rng * 1103515245 + 12345; return ((rng >> 16) & 0x7FFF) / 16384.0 - 1; }
static void add_snap(int16_t *b, int n, double t, double amp) {      // short broadband click
    int s = (int)(t * SR); double prev = 0;
    for (int i = 0; i < SR / 200 && s + i < n; i++) {
        double w = nz(); double hp = w - prev; prev = w;
        double v = amp * exp(-i / (0.0012 * SR)) * hp;
        int x = b[s + i] + (int)v; b[s + i] = x > 32767 ? 32767 : x < -32768 ? -32768 : x;
    }
}
static void add_slam(int16_t *b, int n, double t, double amp) {      // long low rumble ~250 ms
    int s = (int)(t * SR);
    for (int i = 0; i < SR / 4 && s + i < n; i++) {
        double v = amp * exp(-i / (0.08 * SR)) * (sin(2 * M_PI * 60 * i / SR) + 0.5 * nz());
        int x = b[s + i] + (int)v; b[s + i] = x > 32767 ? 32767 : x < -32768 ? -32768 : x;
    }
}
static void add_chirp(int16_t *b, int n, double t, double amp) {     // siren chirp 600->1400 Hz, 300 ms
    int s = (int)(t * SR); double ph = 0;
    for (int i = 0; i < SR * 3 / 10 && s + i < n; i++) {
        double f = 600 + 800.0 * i / (SR * 0.3); ph += 2 * M_PI * f / SR;
        int x = b[s + i] + (int)(amp * sin(ph)); b[s + i] = x > 32767 ? 32767 : x < -32768 ? -32768 : x;
    }
}
static void add_speech(int16_t *b, int n, double t, double dur, double amp) {
    int s = (int)(t * SR);
    for (int i = 0; i < (int)(dur * SR) && s + i < n; i++) {
        double env = 0.5 + 0.5 * sin(2 * M_PI * 4 * i / SR);
        int x = b[s + i] + (int)(amp * env * (0.6 * sin(2 * M_PI * 140 * i / SR) + 0.4 * nz())); b[s + i] = x > 32767 ? 32767 : x < -32768 ? -32768 : x;
    }
}

typedef struct { int doubles, triples; int knocks, snaps; } result;
static result run(int16_t *b, int n) {
    es_tap_cfg c; es_tap_default_cfg(&c); es_tap_detector d; es_tap_init(&d, &c, SR);
    result r = {0};
    for (int i = 0; i + 320 <= n; i += 320) {
        es_tap_event e = es_tap_process(&d, b + i, 320, (uint32_t)(i / 16));
        if (e.kind == ES_TAPEV_DOUBLE) r.doubles++;
        if (e.kind == ES_TAPEV_TRIPLE) r.triples++;
        if (e.kind) { if (e.source == ES_SRC_SNAP) r.snaps++; else r.knocks++; }
    }
    return r;
}
static int16_t *noise_floor(int n) {
    int16_t *b = calloc(n, 2);
    for (int i = 0; i < n; i++) b[i] = (int16_t)(nz() * 150);
    return b;
}

static void test_tap_detector(void) {
    int n = SR * 6; result r; int16_t *b;
    b = noise_floor(n); add_knock(b, n, 1.0, 20000); add_knock(b, n, 1.3, 20000);
    r = run(b, n); CHECK(r.doubles == 1 && r.triples == 0 && r.knocks == 1, "double knock -> 1 double"); free(b);
    b = noise_floor(n); add_knock(b, n, 1.0, 20000); add_knock(b, n, 1.25, 18000); add_knock(b, n, 1.5, 20000);
    r = run(b, n); CHECK(r.triples == 1 && r.doubles == 0, "triple knock -> 1 triple"); free(b);
    b = noise_floor(n); add_snap(b, n, 2.0, 26000); add_snap(b, n, 2.35, 26000);
    r = run(b, n); CHECK(r.doubles == 1 && r.snaps == 1, "double snap classified as snap"); free(b);
    // false-tap cases
    int false_taps = 0, cases = 0;
    b = noise_floor(n); add_knock(b, n, 1.0, 22000); r = run(b, n); cases++; false_taps += r.doubles + r.triples;
    CHECK(r.doubles + r.triples == 0, "single bump ignored"); free(b);
    b = noise_floor(n); add_slam(b, n, 1.0, 25000); r = run(b, n); cases++; false_taps += r.doubles + r.triples;
    CHECK(r.doubles + r.triples == 0, "door slam ignored"); free(b);
    b = noise_floor(n); add_chirp(b, n, 1.0, 20000); add_chirp(b, n, 1.5, 20000); r = run(b, n); cases++; false_taps += r.doubles + r.triples;
    CHECK(r.doubles + r.triples == 0, "siren chirps ignored"); free(b);
    b = noise_floor(n); add_speech(b, n, 0.5, 4.0, 9000); r = run(b, n); cases++; false_taps += r.doubles + r.triples;
    CHECK(r.doubles + r.triples == 0, "speech ignored"); free(b);
    b = noise_floor(n); add_knock(b, n, 1.0, 20000); add_knock(b, n, 2.0, 20000); r = run(b, n); cases++; false_taps += r.doubles + r.triples;
    CHECK(r.doubles + r.triples == 0, "two knocks 1 s apart are two singles"); free(b);
    printf("false-tap rate: %d/%d synthetic distractor clips\n", false_taps, cases);
    // mute while tone plays
    es_tap_cfg c; es_tap_default_cfg(&c); es_tap_detector d; es_tap_init(&d, &c, SR);
    b = noise_floor(n); add_knock(b, n, 1.0, 20000); add_knock(b, n, 1.3, 20000);
    es_tap_mute(&d, 1400);
    int got = 0;
    for (int i = 0; i + 320 <= n; i += 320) got += es_tap_process(&d, b + i, 320, (uint32_t)(i / 16)).kind != 0;
    CHECK(got == 0, "muted during tone + 200 ms"); free(b);
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
    CHECK(es_tap_packet(p, 2, 99, ES_GESTURE_MARK, ES_SRC_KNOCK, 95) == 13 && p[0] == 2 && p[1] == 2 && p[3] == 99 && p[8] == 1 && p[9] == 95, "tap packet layout matches Swift");
}

int main(void) {
    test_state_machine(); test_tap_detector(); test_adpcm();
    printf("%d/%d checks passed\n", checks - fails, checks);
    return fails ? 1 : 0;
}
