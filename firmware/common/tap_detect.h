// Knock / snap detection from the raw mic signal (before ADPCM).
// Single spikes are ignored; 2 spikes within window = double, 3 = triple.
#pragma once
#include <stdint.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint16_t knock_threshold;   // peak / full scale * 1000 (default 350)
    uint16_t snap_threshold;    // high-band peak / full scale * 1000 (default 300)
    uint16_t min_gap_ms;        // min spacing between spikes (default 120)
    uint16_t window_ms;         // max spacing between spikes in a group (default 600)
    uint16_t max_spike_ms;      // a spike must decay within this (default 40)
    uint16_t background_ratio;  // spike peak must exceed background envelope * ratio/10 (default 40 = 4x)
} es_tap_cfg;

typedef enum { ES_TAPEV_NONE = 0, ES_TAPEV_DOUBLE = 2, ES_TAPEV_TRIPLE = 3 } es_tap_event_kind;
typedef struct { es_tap_event_kind kind; uint8_t source; uint32_t first_ms; } es_tap_event;

typedef struct {
    es_tap_cfg cfg;
    int sample_rate;
    uint32_t t_ms;          // time of the next sample block
    float env;              // slow background envelope (abs)
    float prev;             // previous sample (for high-pass)
    // spike tracking
    bool in_spike;
    uint32_t spike_start;
    float spike_peak, spike_hf_peak;
    uint32_t spike_quiet_since;
    // grouping
    int count;
    uint32_t first_spike_ms, last_spike_ms;
    int knock_votes, snap_votes;
    uint32_t mute_until;
    // stats
    uint32_t spikes_seen, singles_ignored, groups_rejected;
} es_tap_detector;

void es_tap_default_cfg(es_tap_cfg *c);
void es_tap_init(es_tap_detector *d, const es_tap_cfg *c, int sample_rate);
// Mute while a tone plays: ignore until mute_until_ms (+200 ms is added).
void es_tap_mute(es_tap_detector *d, uint32_t until_ms);
// Feed samples starting at time t_ms. Returns at most one event.
es_tap_event es_tap_process(es_tap_detector *d, const int16_t *pcm, int n, uint32_t t_ms);

#ifdef __cplusplus
}
#endif
