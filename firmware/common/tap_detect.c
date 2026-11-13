#include "tap_detect.h"
#include "earshot_proto.h"
#include <string.h>
#include <math.h>

void es_tap_default_cfg(es_tap_cfg *c) {
    c->onset_db10 = 200; c->snap_onset_db10 = 160; c->min_gap_ms = 110; c->window_ms = 550;
    c->decay_db10 = 160; c->decay_ms = 40; c->tail_db10 = 80; c->tail_ms = 120; c->quiet_ms = 500;
}

void es_tap_init(es_tap_detector *d, const es_tap_cfg *c, int sr) {
    (void)sr;   // filters below assume 16 kHz
    memset(d, 0, sizeof(*d)); d->cfg = *c; d->last_noise_ms = 0;
}

void es_tap_mute(es_tap_detector *d, uint32_t until) { d->mute_until = until + 200; d->phase = 0; d->count = 0; }

// quantize dB (0..127.5) to 0..255
static uint8_t q(float db) { if (db < 0) db = 0; if (db > 127.5f) db = 127.5f; return (uint8_t)(db * 2); }
static float median(const uint16_t *h, int n) {
    int half = n / 2, acc = 0;
    for (int i = 0; i < 256; i++) { acc += h[i]; if (acc > half) return i / 2.0f; }
    return 0;
}

static void reset_group(es_tap_detector *d) { d->count = 0; d->snap_votes = d->knock_votes = 0; }

static es_tap_event finish(es_tap_detector *d) {
    es_tap_event e = {ES_TAPEV_NONE, ES_SRC_KNOCK, d->hits[0]};
    if (d->count == 2 || d->count == 3) {
        e.kind = (es_tap_event_kind)d->count;
        e.source = d->snap_votes > d->knock_votes ? ES_SRC_SNAP : ES_SRC_KNOCK;
    } else if (d->count == 1) d->singles_ignored++;
    reset_group(d);
    return e;
}

static void noise(es_tap_detector *d, uint32_t t) {
    // a transient that is not a clean tap: breaks any group (quiet rule)
    d->rejected++; d->last_noise_ms = t;
    if (d->count) { d->groups_rejected++; reset_group(d); }
}

static void accept_hit(es_tap_detector *d) {
    uint32_t t = d->peak_ms;
    d->hits_seen++;
    if (d->count == 0) {
        if (d->last_noise_ms && t - d->last_noise_ms < d->cfg.quiet_ms) { d->rejected++; return; }   // not quiet before
    } else {
        uint32_t gap = t - d->hits[d->count - 1];
        if (gap < d->cfg.min_gap_ms) return;                                   // ringing of the same hit
        if (gap > d->cfg.window_ms) { if (d->count == 1) d->singles_ignored++; reset_group(d); }
    }
    if (d->count >= 3) { d->groups_rejected++; reset_group(d); d->last_noise_ms = t; return; }   // 4+ hits: rattle
    d->hits[d->count++] = t;
    if (d->peak_hi - d->peak_lo > 0) d->snap_votes++; else d->knock_votes++;
}

// one 2 ms block
static es_tap_event block(es_tap_detector *d, float e_lo, float e_hi, uint32_t t) {
    es_tap_event ev = {ES_TAPEV_NONE, 0, 0};
    float db_lo = 10 * log10f(e_lo + 1.0f), db_hi = 10 * log10f(e_hi + 1.0f);
    float db = 10 * log10f(e_lo + e_hi + 1.0f);
    float f_lo = median(d->hist_lo, d->ring_n), f_hi = median(d->hist_hi, d->ring_n);
    float floor_db = 10 * log10f(powf(10, f_lo / 10) + powf(10, f_hi / 10));
    bool muted = t < d->mute_until;
    const float onset = d->cfg.onset_db10 / 10.f, snap_onset = d->cfg.snap_onset_db10 / 10.f;

    if (!muted) switch (d->phase) {
    case 0:
        if (d->ring_n >= 50 && (db >= floor_db + onset || db_hi >= f_hi + snap_onset)) {
            d->phase = 1; d->peak_db = db; d->peak_lo = db_lo; d->peak_hi = db_hi; d->peak_ms = t;
        }
        break;
    case 1:   // rising: follow the peak
        if (db > d->peak_db) { d->peak_db = db; d->peak_lo = db_lo; d->peak_hi = db_hi; d->peak_ms = t; }
        else d->phase = 2;
        /* fallthrough */
    case 2:
        if (d->phase == 2) {
            if (db <= d->peak_db - d->cfg.decay_db10 / 10.f) { d->phase = 3; d->decay_ok_ms = t; }
            else if (t - d->peak_ms > d->cfg.decay_ms) { noise(d, t); d->phase = 0; }
        }
        break;
    case 3:   // tail must stay well below the peak
        if (db > d->peak_db - d->cfg.tail_db10 / 10.f) { noise(d, t); d->phase = 0; }
        else if (t - d->peak_ms >= d->cfg.tail_ms) { accept_hit(d); d->phase = 0; }
        break;
    }
    // floors follow only quiet blocks (not the candidate hit itself)
    if (d->phase == 0) {
        if (d->ring_n == ES_TAP_FLOOR_BLOCKS) { d->hist_lo[d->ring_lo[d->ring_pos]]--; d->hist_hi[d->ring_hi[d->ring_pos]]--; } else d->ring_n++;
        d->ring_lo[d->ring_pos] = q(db_lo); d->ring_hi[d->ring_pos] = q(db_hi);
        d->hist_lo[q(db_lo)]++; d->hist_hi[q(db_hi)]++;
        d->ring_pos = (d->ring_pos + 1) % ES_TAP_FLOOR_BLOCKS;
    }
    // close a group once the window and the quiet period after the last hit have passed
    if (d->count > 0 && d->phase == 0) {
        uint32_t wait = d->cfg.window_ms > d->cfg.quiet_ms ? d->cfg.window_ms : d->cfg.quiet_ms;
        uint32_t last = d->hits[d->count - 1];
        if (t - last > wait) {
            if (d->last_noise_ms > last) { d->groups_rejected++; reset_group(d); }   // noise right after: not quiet
            else ev = finish(d);
        }
    }
    return ev;
}

es_tap_event es_tap_process(es_tap_detector *d, const int16_t *pcm, int n, uint32_t t0) {
    es_tap_event ev = {ES_TAPEV_NONE, 0, 0};
    // 1st-order coefficients at 16 kHz
    const float a_hp150 = 0.9428f, a_lp2k = 0.5602f, a_hp2k5 = 0.6158f, a_lp7k = 0.9330f;
    for (int i = 0; i < n; i++) {
        float x = pcm[i];
        // low band: HP 150 Hz, LP 2 kHz
        float hp = a_hp150 * (d->hp1_lo_y + x - d->hp1_lo_x); d->hp1_lo_x = x; d->hp1_lo_y = hp;
        d->lp1_lo += a_lp2k * (hp - d->lp1_lo);
        // high band: HP 2.5 kHz, LP 7 kHz
        float hh = a_hp2k5 * (d->hp2_y + x - d->hp2_x); d->hp2_x = x; d->hp2_y = hh;
        d->lp2_hi += a_lp7k * (hh - d->lp2_hi);
        d->acc_lo += d->lp1_lo * d->lp1_lo; d->acc_hi += d->lp2_hi * d->lp2_hi;
        if (++d->acc_n == ES_TAP_BLOCK) {
            uint32_t t = t0 + (uint32_t)(i * 1000 / 16000);
            es_tap_event e = block(d, d->acc_lo / ES_TAP_BLOCK, d->acc_hi / ES_TAP_BLOCK, t);
            if (e.kind != ES_TAPEV_NONE) ev = e;
            d->acc_lo = d->acc_hi = 0; d->acc_n = 0;
        }
    }
    return ev;
}
