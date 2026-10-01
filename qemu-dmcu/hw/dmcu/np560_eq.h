/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_DMCU_NP560_EQ_H
#define HW_DMCU_NP560_EQ_H

#include <stdbool.h>
#include <stdint.h>

/* Experimental HLE, NOT recovered factory DSP. Gains are interpreted as
 * unsigned Q15, centers are 31.25 * 2^band Hz, Q=sqrt(2). Zero gains and
 * unsupported sample rates are rejected atomically, not silently clamped.
 * Caller owns one zero-initialized instance per decoder session. */
typedef struct NP560EQ {
    uint32_t hz;
    uint16_t gains[10];
    bool enabled;
    unsigned bands;
    double b[10][3], a[10][2];
    double delay[2][10][2];
} NP560EQ;

bool np560_eq_configure(NP560EQ *eq, uint32_t hz,
                        const uint16_t gains[10], bool enabled);
void np560_eq_reset_history(NP560EQ *eq);
/* Floating output preserves boost headroom until the caller applies volume
 * and performs final saturation. Channel must be 0 or 1. */
double np560_eq_sample(NP560EQ *eq, unsigned channel, double input);
int16_t np560_eq_quantize(double sample, uint16_t volume_q15);

#endif
