// Knock / snap detection from the raw mic signal (before ADPCM).
// Parameters follow the data agent's tuned reference detector
// (eval/tap_detector.py, docs/REVIEW.md "Tap thresholds"):
//   2 ms energy envelope in two bands (150-2000 Hz, 2.5-7 kHz);
//   onset >= 20 dB above the 1.5 s median floor (snaps: >= 16 dB in the high band);
//   decay >= 16 dB within 40 ms of the peak, then the next 120 ms stays >= 8 dB below it;
//   hits 110-550 ms apart: 2 = double (mark/yes), 3 = triple (stop/no);
//   >= 500 ms without other transients before the first and after the last hit;
//   snap vs knock: high/low band ratio at the peak > 0 dB.
// Single spikes, slams, sirens and speech are ignored.
#pragma once
#include <stdint.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint16_t onset_db10;        // knock onset above floor, dB x10 (default 200 = 20 dB)
    uint16_t snap_onset_db10;   // snap onset above high-band floor, dB x10 (default 160)
    uint16_t min_gap_ms;        // min spacing between hits (default 110)
    uint16_t window_ms;         // max spacing between hits (default 550)
    uint16_t decay_db10;        // required drop within decay_ms (default 160)
    uint16_t decay_ms;          // (default 40)
    uint16_t tail_db10;         // tail must stay this far below peak (default 80)
    uint16_t tail_ms;           // (default 120)
    uint16_t quiet_ms;          // quiet before first / after last hit (default 500)
} es_tap_cfg;

typedef enum { ES_TAPEV_NONE = 0, ES_TAPEV_DOUBLE = 2, ES_TAPEV_TRIPLE = 3 } es_tap_event_kind;
typedef struct { es_tap_event_kind kind; uint8_t source; uint32_t first_ms; } es_tap_event;

#define ES_TAP_BLOCK 32                 // 2 ms at 16 kHz
#define ES_TAP_FLOOR_BLOCKS 750         // 1.5 s

typedef struct {
    es_tap_cfg cfg;
    // band filters (1st-order sections)
    float lp1_lo, hp1_lo_x, hp1_lo_y;   // low band: HP 150 Hz then LP 2 kHz
    float hp2_x, hp2_y, lp2_hi;         // high band: HP 2.5 kHz then LP 7 kHz
    float acc_lo, acc_hi; int acc_n;
    uint32_t t_ms;
    // median floors: histograms of quantized dB over a sliding window
    uint8_t ring_lo[ES_TAP_FLOOR_BLOCKS], ring_hi[ES_TAP_FLOOR_BLOCKS];
    uint16_t hist_lo[256], hist_hi[256];
    int ring_pos, ring_n;
    // candidate hit being evaluated
    int phase;                          // 0 idle, 1 rising, 2 decay check, 3 tail check
    uint32_t peak_ms, decay_ok_ms;
    float peak_db, peak_lo, peak_hi;
    // grouping
    int count;
    uint32_t hits[3];
    int snap_votes, knock_votes;
    uint32_t last_noise_ms;             // last rejected transient (quiet rule)
    uint32_t mute_until;
    // stats for false-tap logging
    uint32_t hits_seen, rejected, singles_ignored, groups_rejected;
} es_tap_detector;

void es_tap_default_cfg(es_tap_cfg *c);
void es_tap_init(es_tap_detector *d, const es_tap_cfg *c, int sample_rate);
// Mute while a tone plays: ignored until until_ms + 200 ms.
void es_tap_mute(es_tap_detector *d, uint32_t until_ms);
// Feed 16 kHz samples starting at time t_ms. Returns at most one event per call.
es_tap_event es_tap_process(es_tap_detector *d, const int16_t *pcm, int n, uint32_t t_ms);

#ifdef __cplusplus
}
#endif
