#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { int predictor; int index; } es_adpcm_state;
// Encode n samples (n even) into 4 + n/2 bytes. Block header = state before the first sample.
int es_adpcm_encode_block(const int16_t *pcm, int n, es_adpcm_state *st, uint8_t *out);
// Decode a block of len bytes into 2*(len-4) samples.
int es_adpcm_decode_block(const uint8_t *in, int len, int16_t *out);
#ifdef __cplusplus
}
#endif
