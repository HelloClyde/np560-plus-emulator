/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef NP560_EQ_STANDALONE
#include "qemu/osdep.h"
#endif
#include <assert.h>
#include <math.h>
#include <string.h>
#include "np560_eq.h"

void np560_eq_reset_history(NP560EQ *eq)
{
    memset(eq->delay, 0, sizeof(eq->delay));
}

bool np560_eq_configure(NP560EQ *eq, uint32_t hz,
                        const uint16_t gains[10], bool enabled)
{
    NP560EQ next = {0};
    unsigned i;

    if (hz < 8000 || hz > 48000) {
        return false;
    }
    for (i = 0; i < 10; i++) {
        if (!gains[i]) {
            return false;
        }
    }
    if (eq->hz == hz && eq->enabled == enabled &&
        memcmp(eq->gains, gains, sizeof(eq->gains)) == 0) {
        return true; /* repeated menu confirmation must not reset history */
    }
    next.hz = hz;
    next.enabled = enabled;
    memcpy(next.gains, gains, sizeof(next.gains));
    for (i = 0; enabled && i < 10; i++) {
        double center = 31.25 * (1u << i);
        double w, alpha, amplitude, a0;
        unsigned n;

        /* Explicit compatibility rule: omit centers at/above 0.45 Fs. */
        if (center >= 0.45 * hz || gains[i] == 32768) {
            continue;
        }
        w = 2.0 * 3.14159265358979323846 * center / hz;
        alpha = sin(w) / (2.0 * sqrt(2.0));
        amplitude = sqrt(gains[i] / 32768.0);
        a0 = 1.0 + alpha / amplitude;
        n = next.bands++;
        /* RBJ peaking EQ: https://www.w3.org/TR/audio-eq-cookbook/
         * This source specifies the filter, not NP560's original choices. */
        next.b[n][0] = (1.0 + alpha * amplitude) / a0;
        next.b[n][1] = -2.0 * cos(w) / a0;
        next.b[n][2] = (1.0 - alpha * amplitude) / a0;
        next.a[n][0] = next.b[n][1];
        next.a[n][1] = (1.0 - alpha / amplitude) / a0;
    }
    *eq = next;
    return true;
}

double np560_eq_sample(NP560EQ *eq, unsigned channel, double input)
{
    unsigned i;
    assert(channel < 2);
    for (i = 0; i < eq->bands; i++) {
        double *state = eq->delay[channel][i];
        double output = eq->b[i][0] * input + state[0];
        state[0] = eq->b[i][1] * input - eq->a[i][0] * output + state[1];
        state[1] = eq->b[i][2] * input - eq->a[i][1] * output;
        input = output;
    }
    return input;
}

int16_t np560_eq_quantize(double sample, uint16_t volume_q15)
{
    double value = floor(sample * volume_q15 / 32768.0 + 0.5);
    /* Defensive conversion guard, not a substitute for filter stability. */
    if (isnan(value)) {
        return 0;
    }
    if (value >= 32767.0) {
        return 32767;
    }
    if (value <= -32768.0) {
        return -32768;
    }
    return (int16_t)value;
}
