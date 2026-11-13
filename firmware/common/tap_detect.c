#include "tap_detect.h"
#include "earshot_proto.h"
#include <string.h>
#include <math.h>

void es_tap_default_cfg(es_tap_cfg *c) {
    c->knock_threshold = 350; c->snap_threshold = 300; c->min_gap_ms = 120; c->window_ms = 600;
    c->max_spike_ms = 40; c->background_ratio = 40;
}

void es_tap_init(es_tap_detector *d, const es_tap_cfg *c, int sr) {
    memset(d, 0, sizeof(*d)); d->cfg = *c; d->sample_rate = sr; d->env = 100;
}

void es_tap_mute(es_tap_detector *d, uint32_t until) { d->mute_until = until + 200; d->in_spike = false; d->count = 0; }

static es_tap_event finish_group(es_tap_detector *d) {
    es_tap_event e = {ES_TAPEV_NONE, ES_SRC_KNOCK, d->first_spike_ms};
    if (d->count == 2 || d->count == 3) {
        e.kind = (es_tap_event_kind)d->count;
        e.source = d->snap_votes > d->knock_votes ? ES_SRC_SNAP : ES_SRC_KNOCK;
    } else if (d->count == 1) d->singles_ignored++;
    else if (d->count > 3) d->groups_rejected++;
    d->count = 0; d->knock_votes = d->snap_votes = 0;
    return e;
}

static void end_spike(es_tap_detector *d, uint32_t now) {
    d->in_spike = false;
    uint32_t dur = d->spike_quiet_since - d->spike_start;
    if (dur > d->cfg.max_spike_ms) { d->groups_rejected += d->count ? 1 : 0; d->count = 0; d->knock_votes = d->snap_votes = 0; return; } // too long: slam, siren, speech
    d->spikes_seen++;
    if (d->count > 0 && d->spike_start - d->last_spike_ms < d->cfg.min_gap_ms) return; // ringing of the same knock
    if (d->count == 0) d->first_spike_ms = d->spike_start;
    d->count++;
    d->last_spike_ms = d->spike_start;
    // classify: snaps are mostly high-frequency energy
    if (d->spike_hf_peak > 0.6f * d->spike_peak) d->snap_votes++; else d->knock_votes++;
    (void)now;
}

es_tap_event es_tap_process(es_tap_detector *d, const int16_t *pcm, int n, uint32_t t0) {
    es_tap_event ev = {ES_TAPEV_NONE, 0, 0};
    const float fs = 32768.f;
    const float thr = d->cfg.knock_threshold / 1000.f * fs;
    const float hthr = d->cfg.snap_threshold / 1000.f * fs;
    const float ratio = d->cfg.background_ratio / 10.f;
    for (int i = 0; i < n; i++) {
        uint32_t now = t0 + (uint32_t)((uint64_t)i * 1000 / d->sample_rate);
        float x = pcm[i];
        float hf = x - d->prev; d->prev = x;              // first difference = crude high-pass
        float ax = fabsf(x), ahf = fabsf(hf) * 0.5f;
        if (now < d->mute_until) { d->env = d->env * 0.999f + ax * 0.001f; continue; }
        bool loud = (ax > thr || ahf > hthr) && (ax > d->env * ratio || ahf > d->env * ratio);
        if (!d->in_spike) {
            if (loud) {
                d->in_spike = true; d->spike_start = now; d->spike_peak = ax; d->spike_hf_peak = ahf; d->spike_quiet_since = now;
            } else {
                d->env = d->env * 0.999f + ax * 0.001f;   // background follows only outside spikes
            }
        } else {
            if (ax > d->spike_peak) d->spike_peak = ax;
            if (ahf > d->spike_hf_peak) d->spike_hf_peak = ahf;
            if (ax > 0.25f * d->spike_peak) d->spike_quiet_since = now;
            if (now - d->spike_quiet_since > 15 || now - d->spike_start > (uint32_t)d->cfg.max_spike_ms * 3) {
                if (now - d->spike_start > (uint32_t)d->cfg.max_spike_ms * 3) d->spike_quiet_since = now; // force "too long"
                end_spike(d, now);
            }
        }
        if (d->count > 0 && !d->in_spike && now - d->last_spike_ms > d->cfg.window_ms) {
            es_tap_event e = finish_group(d);
            if (e.kind != ES_TAPEV_NONE) ev = e;
        }
    }
    return ev;
}
