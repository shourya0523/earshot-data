#include "state_machine.h"
#include "earshot_proto.h"
#include <string.h>

void es_sm_init(es_sm *sm) {
    memset(sm, 0, sizeof(*sm));
    sm->state = ES_STATE_OFF;
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
    if (kind == ES_IN_FORCE_OFF) {
        if (sm->state == ES_STATE_OFF) return a;
        a = go(sm, ES_STATE_OFF); a.clear_buffers = true; a.tone = ES_TONE_FALLING; return a;
    }
    switch (sm->state) {
    case ES_STATE_OFF:
        if (kind == ES_IN_SINGLE) { a = go(sm, ES_STATE_ASKING); a.tone = ES_TONE_RISING; tap(&a, ES_GESTURE_START, source, now); }
        break;
    case ES_STATE_ASKING:
        if (kind == ES_IN_SINGLE) { a = go(sm, ES_STATE_LISTENING); a.tone = ES_TONE_HIGH; tap(&a, ES_GESTURE_YES, source, now); }
        else if (kind == ES_IN_LONG) {
            // refusal: logged, then OFF. Nothing was captured.
            sm->refusals++;
            a = go(sm, ES_STATE_OFF); a.tone = ES_TONE_LOW; a.clear_buffers = true; a.log_refusal = true;
            tap(&a, ES_GESTURE_NO, source, now);
        }
        break;
    case ES_STATE_LISTENING:
        if (kind == ES_IN_SINGLE) { tap(&a, ES_GESTURE_MARK, source, now); a.tone = ES_TONE_CLICK; }
        else if (kind == ES_IN_LONG) { a = go(sm, ES_STATE_OFF); a.tone = ES_TONE_FALLING; a.clear_buffers = true; tap(&a, ES_GESTURE_STOP, source, now); }
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
