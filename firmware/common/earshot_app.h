// Shared clip application: state machine + tap detection + ADPCM + transport.
#pragma once
#include "hal.h"

void earshot_setup(EsHal *hal, bool acoustic_consent);
void earshot_loop();   // call forever; each call handles one 20 ms audio frame
