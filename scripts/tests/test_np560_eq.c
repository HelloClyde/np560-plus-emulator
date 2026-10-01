/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Standalone numerical checks; does not claim original DSP equivalence. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "np560_eq.h"

static void check_factory_tables(const char *path)
{
    static const unsigned rates[] = {8000, 11025, 12000, 16000, 22050,
                                      24000, 32000, 44100, 48000};
    unsigned char raw[260];
    FILE *file = fopen(path, "rb");
    assert(file);
    assert(fseek(file, 0x2d5966, SEEK_SET) == 0);
    assert(fread(raw, 1, sizeof(raw), file) == sizeof(raw));
    assert(fclose(file) == 0);
    NP560EQ eq = {0};
    unsigned cases = 0;
    for (unsigned mode = 0; mode < 13; mode++) {
        uint16_t gains[10];
        for (unsigned b = 0; b < 10; b++) {
            unsigned offset = mode * 20 + b * 2;
            gains[b] = raw[offset] | raw[offset + 1] << 8;
        }
        for (unsigned rate = 0; rate < sizeof(rates)/sizeof(rates[0]); rate++) {
            NP560EQ fresh = {0};
            /* Configure on a dirty instance and compare to a new one: both
             * sample-rate and preset transitions must discard old history. */
            assert(np560_eq_configure(&eq, rates[rate], gains, true));
            assert(np560_eq_configure(&fresh, rates[rate], gains, true));
            double history[2][10][4] = {{{0}}};
            unsigned random = 42;
            for (unsigned n = 0; n < 20000; n++) {
                for (unsigned ch = 0; ch < 2; ch++) {
                    random = random * 1664525u + 1013904223u;
                    double x = (int)(random >> 16) - 32768;
                    double reference = x;
                    /* Different recurrence (direct form I) compared with
                     * actual transposed form II. This tests arithmetic and
                     * history only, not the assumed coefficient design. */
                    for (unsigned b = 0; b < fresh.bands; b++) {
                        double *h = history[ch][b];
                        double y = fresh.b[b][0] * reference + fresh.b[b][1] * h[0]
                            + fresh.b[b][2] * h[1] - fresh.a[b][0] * h[2]
                            - fresh.a[b][1] * h[3];
                        h[1] = h[0]; h[0] = reference;
                        h[3] = h[2]; h[2] = y;
                        reference = y;
                    }
                    double actual = np560_eq_sample(&eq, ch, x);
                    assert(isfinite(actual));
                    assert(fabs(actual - reference) < 1e-5);
                    assert(actual == np560_eq_sample(&fresh, ch, x));
                }
            }
            cases++;
        }
    }
    printf("Factory parameter numerical cases: %u (not original DSP equivalence)\n", cases);
}

int main(int argc, char **argv)
{
    NP560EQ eq = {0}, saved, fresh = {0};
    uint16_t gains[10];
    unsigned i, hz, band;
    for (i = 0; i < 10; i++) {
        gains[i] = 32768;
    }
    assert(np560_eq_configure(&eq, 44100, gains, true));
    for (int value = -32768; value <= 32767; value++) {
        assert(np560_eq_sample(&eq, 0, value) == value);
        assert(np560_eq_quantize(value, 32768) == value);
    }
    /* At an isolated band's center the analytic amplitude is its gain.
     * Measure steady-state sine power, independently of stored coefficients. */
    for (hz = 8000; hz <= 48000; hz += 8000) {
        for (band = 0; band < 10; band++) {
            double f = 31.25 * (1u << band), in2 = 0, out2 = 0;
            gains[band] = band & 1 ? 16384 : 49152;
            assert(np560_eq_configure(&eq, hz, gains, true));
            for (i = 0; i < 4 * hz; i++) {
                double x = sin(2 * 3.14159265358979323846 * f * i / hz);
                double y = np560_eq_sample(&eq, 0, x);
                assert(isfinite(y));
                assert(np560_eq_sample(&eq, 1, 0) == 0);
                if (i >= 2 * hz) {
                    in2 += x * x;
                    out2 += y * y;
                }
            }
            if (in2 > 1) {
                double expected = f < 0.45 * hz ? gains[band] / 32768.0 : 1;
                assert(fabs(sqrt(out2 / in2) - expected) < 0.002);
            }
            gains[band] = 32768;
        }
    }
    gains[5] = 49152;
    assert(np560_eq_configure(&eq, 44100, gains, true));
    np560_eq_sample(&eq, 0, 1000);
    saved = eq;
    assert(np560_eq_configure(&eq, 44100, gains, true));
    assert(memcmp(&eq, &saved, sizeof(eq)) == 0);
    gains[0] = 0;
    assert(!np560_eq_configure(&eq, 44100, gains, true));
    assert(memcmp(&eq, &saved, sizeof(eq)) == 0);
    gains[0] = 32768;
    assert(!np560_eq_configure(&eq, 0, gains, true));
    assert(memcmp(&eq, &saved, sizeof(eq)) == 0);
    np560_eq_reset_history(&eq);
    assert(np560_eq_configure(&fresh, 44100, gains, true));
    for (i = 0; i < 10000; i++) {
        double x = i % 177 - 88.0;
        assert(np560_eq_sample(&eq, 0, x) == np560_eq_sample(&fresh, 0, x));
    }
    assert(np560_eq_configure(&eq, 22050, gains, false));
    assert(np560_eq_sample(&eq, 0, 12345) == 12345);
    assert(np560_eq_quantize(60000, 8192) == 15000); /* no pre-volume clip */
    assert(np560_eq_quantize(60000, 32768) == 32767);
    assert(np560_eq_quantize(-60000, 32768) == -32768);
    assert(np560_eq_quantize(-1.5, 32768) == -1);
    /* Extreme accepted gain words, ten simultaneous filters, then silence.
     * These bounds exercise numerical stability, not an acoustic gold file. */
    for (unsigned extreme = 0; extreme < 2; extreme++) {
        for (i = 0; i < 10; i++) {
            gains[i] = extreme ? 65535 : 1;
        }
        assert(np560_eq_configure(&eq, 48000, gains, true));
        double tail = 0;
        for (i = 0; i < 480000; i++) {
            double y = np560_eq_sample(&eq, 0, i == 0 ? 32767 : 0);
            assert(isfinite(y) && fabs(y) < 1e8);
            if (i > 479000) {
                tail += fabs(y);
            }
        }
        assert(tail < 1);
    }
    /* Rate changes reset history just like a freshly configured session. */
    assert(np560_eq_configure(&eq, 8000, gains, true));
    memset(&fresh, 0, sizeof(fresh));
    assert(np560_eq_configure(&fresh, 8000, gains, true));
    for (i = 0; i < 1000; i++) {
        assert(np560_eq_sample(&eq, 0, i == 0 ? 1 : 0) ==
               np560_eq_sample(&fresh, 0, i == 0 ? 1 : 0));
    }
    puts("EQ numerical checks passed (experimental HLE, not factory equivalence)");
    if (argc == 2) {
        check_factory_tables(argv[1]);
    }
    return 0;
}
