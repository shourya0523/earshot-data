// Board abstraction. VoiceS3R and Feather each implement this.
#pragma once
#include <stdint.h>
#include "state_machine.h"

class EsHal {
public:
    virtual ~EsHal() {}
    virtual bool begin() = 0;
    // Blocking read of exactly n samples (16 kHz mono). Returns samples read.
    virtual int readMic(int16_t *buf, int n) = 0;
    // Feedback for a state change: a tone (VoiceS3R) or vibration (Feather).
    // Returns how long it lasts in ms; the mic is ignored until then + 200 ms.
    virtual uint32_t feedback(es_tone t) = 0;
    virtual bool hasButton() = 0;
    virtual bool buttonPressed() = 0;
    virtual void showState(uint8_t state) = 0;   // consent light / OLED
    virtual uint8_t powerFlags() = 0;            // ES_FLAG_USB | ES_FLAG_BATT_LOW
    virtual const char *name() = 0;
};
