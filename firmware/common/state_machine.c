#include "state_machine.h"
#include "earshot_proto.h"
#include <string.h>

void es_sm_init(es_sm *sm, bool acoustic_consent) {
    memset(sm, 0, sizeof(*sm));
    sm->state = ES_STATE_OFF;
    sm->acoustic_consent = acoustic_consent;
    sm->long_press_ms = 1500;
}

static es_action go(es_sm *sm, uint8_t st) {
    es_action a; memset(&a, 0, sizeof(a));
    if (sm->state != st) { a.state_changed = true; }
    sm->state = st; a.new_state = st;
    return a;
}

static void tap(es_action *a, uint8_t gesture, uint8_t source, uint32_t t) {
    a->emit_tap = true; a->tap_gesture = gesture; a->tap_source = source; a->tap_press_ms = t;
}

es_action es_sm_input(es_sm *sm, es_input_kind kind, uint8_t source, uint32_t now) {
    es_action a; memset(&a, 0, sizeof(a)); a.new_state = sm->state;
    bool acoustic = (kind == ES_IN_DOUBLE || kind == ES_IN_TRIPLE);
    // map acoustic gestures onto button meaning
    es_input_kind k = kind;
    if (acoustic) {
        if (sm->state == ES_STATE_LISTENING) k = (kind == ES_IN_DOUBLE) ? ES_IN_SINGLE : ES_IN_LONG;
        else if (sm->acoustic_consent) {
            // Feather: triple = start (OFF) / no (ASKING); double = yes (ASKING)
            if (sm->state == ES_STATE_OFF) { if (kind != ES_IN_TRIPLE) return a; k = ES_IN_SINGLE; }
            else if (sm->state == ES_STATE_ASKING) k = (kind == ES_IN_DOUBLE) ? ES_IN_SINGLE : ES_IN_LONG;
        } else {
            return a;  // VoiceS3R: knocks/snaps only count while LISTENING
        }
    }
    if (kind == ES_IN_FORCE_OFF) {
        if (sm->state == ES_STATE_OFF) return a;
        a = go(sm, ES_STATE_OFF); a.clear_buffers = true; a.tone = ES_TONE_FALLING; return a;
    }
    switch (sm->state) {
    case ES_STATE_OFF:
        if (k == ES_IN_SINGLE) { a = go(sm, ES_STATE_ASKING); a.tone = ES_TONE_RISING; tap(&a, ES_GESTURE_START, source, now); }
        break;
    case ES_STATE_ASKING:
        if (k == ES_IN_SINGLE) { a = go(sm, ES_STATE_LISTENING); a.tone = ES_TONE_HIGH; tap(&a, ES_GESTURE_YES, source, now); }
        else if (k == ES_IN_LONG) {
            // refusal: logged, then OFF. Nothing was captured.
            sm->refusals++;
            a = go(sm, ES_STATE_OFF); a.tone = ES_TONE_LOW; a.clear_buffers = true; a.log_refusal = true;
            tap(&a, ES_GESTURE_NO, source, now);
        }
        break;
    case ES_STATE_LISTENING:
        if (k == ES_IN_SINGLE) { tap(&a, ES_GESTURE_MARK, source, now); a.tone = ES_TONE_CLICK; }
        else if (k == ES_IN_LONG) { a = go(sm, ES_STATE_OFF); a.tone = ES_TONE_FALLING; a.clear_buffers = true; tap(&a, ES_GESTURE_STOP, source, now); }
        break;
    default:
        a = go(sm, ES_STATE_OFF);
    }
    return a;
}

bool es_sm_button(es_sm *sm, bool pressed, uint32_t now, es_action *out) {
    if (pressed && !sm->btn_down) { sm->btn_down = true; sm->btn_down_ms = now; sm->long_fired = false; return false; }
    if (!pressed && sm->btn_down) {
        sm->btn_down = false;
        if (sm->long_fired) return false;            // long already handled while held
        if (now - sm->btn_down_ms < 30) return false; // debounce
        *out = es_sm_input(sm, ES_IN_SINGLE, ES_SRC_BUTTON, sm->btn_down_ms);
        return true;
    }
    return false;
}

bool es_sm_tick(es_sm *sm, uint32_t now, es_action *out) {
    if (sm->btn_down && !sm->long_fired && now - sm->btn_down_ms >= sm->long_press_ms) {
        sm->long_fired = true;
        *out = es_sm_input(sm, ES_IN_LONG, ES_SRC_BUTTON, sm->btn_down_ms);
        return true;
    }
    return false;
}
