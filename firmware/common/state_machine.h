// Clip state machine (consent gate). Pure C, time is injected, so it runs in
// host tests (test/test_state_machine.c) and on both boards.
#pragma once
#include <stdint.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef enum { ES_TONE_NONE = 0, ES_TONE_RISING, ES_TONE_HIGH, ES_TONE_LOW, ES_TONE_CLICK, ES_TONE_FALLING } es_tone;
typedef enum { ES_IN_SINGLE = 0, ES_IN_LONG, ES_IN_FORCE_OFF } es_input_kind;

typedef struct {
    bool state_changed;      // send a state packet
    uint8_t new_state;
    bool emit_tap;           // send a tap packet (resent until acked)
    uint8_t tap_gesture;
    uint8_t tap_source;
    uint32_t tap_press_ms;
    es_tone tone;            // play this (mic is muted while playing + 200 ms)
    bool clear_buffers;      // drop all buffered audio (stop / refusal)
    bool log_refusal;
} es_action;

typedef struct {
    uint8_t state;
    uint32_t refusals;       // count of logged refusals
    // button gesture tracking
    bool btn_down;
    uint32_t btn_down_ms;
    bool long_fired;
    uint32_t long_press_ms;  // default 1500
} es_sm;

void es_sm_init(es_sm *sm);
// Feed a high-level input (button single/long press, iPad force-off).
es_action es_sm_input(es_sm *sm, es_input_kind kind, uint8_t source, uint32_t now_ms);
// Raw button edges + periodic tick -> single/long detection. Returns an action if one fired.
bool es_sm_button(es_sm *sm, bool pressed, uint32_t now_ms, es_action *out);
bool es_sm_tick(es_sm *sm, uint32_t now_ms, es_action *out);
// Consent gate: audio may be sent only while LISTENING.
static inline bool es_sm_audio_allowed(const es_sm *sm) { return sm->state == 2; }

#ifdef __cplusplus
}
#endif
