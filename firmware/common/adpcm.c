// IMA ADPCM, bit-exact with core/Sources/EarshotCore/Wire/ADPCM.swift
#include "adpcm.h"
static const int8_t kIndex[16] = {-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8};
static const int16_t kStep[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230,
    253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327,
    3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487,
    12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767};

static int step(int code, es_adpcm_state *s) {
    int st = kStep[s->index], diff = st >> 3;
    if (code & 4) diff += st;
    if (code & 2) diff += st >> 1;
    if (code & 1) diff += st >> 2;
    s->predictor += (code & 8) ? -diff : diff;
    if (s->predictor > 32767) s->predictor = 32767;
    if (s->predictor < -32768) s->predictor = -32768;
    s->index += kIndex[code];
    if (s->index < 0) s->index = 0;
    if (s->index > 88) s->index = 88;
    return s->predictor;
}

int es_adpcm_encode_block(const int16_t *pcm, int n, es_adpcm_state *s, uint8_t *out) {
    uint16_t p = (uint16_t)(int16_t)s->predictor;
    out[0] = p & 0xFF; out[1] = p >> 8; out[2] = (uint8_t)s->index; out[3] = 0;
    uint8_t *o = out + 4;
    for (int i = 0; i < n; i++) {
        int st = kStep[s->index], diff = pcm[i] - s->predictor, code = 0;
        if (diff < 0) { code = 8; diff = -diff; }
        int tmp = st;
        if (diff >= tmp) { code |= 4; diff -= tmp; }
        tmp >>= 1;
        if (diff >= tmp) { code |= 2; diff -= tmp; }
        tmp >>= 1;
        if (diff >= tmp) code |= 1;
        step(code, s);
        if ((i & 1) == 0) *o = (uint8_t)code; else { *o |= (uint8_t)(code << 4); o++; }
    }
    return 4 + n / 2;
}

int es_adpcm_decode_block(const uint8_t *in, int len, int16_t *out) {
    if (len <= 4) return 0;
    es_adpcm_state s = {(int16_t)(in[0] | (in[1] << 8)), in[2] > 88 ? 88 : in[2]};
    int k = 0;
    for (int i = 4; i < len; i++) {
        out[k++] = (int16_t)step(in[i] & 0x0F, &s);
        out[k++] = (int16_t)step(in[i] >> 4, &s);
    }
    return k;
}
