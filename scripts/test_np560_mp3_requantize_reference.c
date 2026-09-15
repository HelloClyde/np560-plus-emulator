/* SPDX-License-Identifier: GPL-2.0-or-later
 * Offline oracle: pinned libmad expressions with widened intermediates,
 * plus unchanged FFmpeg band exponent functions.
 * Not linked to QEMU and never used as a live decoder.
 */
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <assert.h>

typedef int32_t mad_fixed_t;
#define MAD_F(x) ((int32_t)(x))
#define MAD_F_MAX INT32_MAX
static int overflow;
static int64_t mad_f_mul(int64_t x, int32_t y)
{
    return (x*y) >> 28;
}
#include "libmad_requantize.inc"

typedef struct { int sample_rate_index; void *avctx; } MPADecodeContext;
typedef struct {
    int block_type, switch_point, long_end, short_start;
    int global_gain, scalefac_scale, preflag, subblock_gain[3], scale_factors[39];
} GranuleDef;
/* The original function requests a sample for 8k mixed; preserve its
 * layout calculation but suppress repetitive offline diagnostic messages. */
#define avpriv_request_sample(...) ((void)0)
#include "ffmpeg_exponents.inc"

static int scalar(int value, int exp, int32_t *result)
{
    *result = 0;
    if (value < -8206 || value > 8206) return 2;
    if (!value) return 0;
    overflow = 0;
    int64_t r = III_requantize(abs(value), exp);
    if (overflow || r > (value < 0 ? INT64_C(2147483648) : INT32_MAX)) return 3;
    *result = (int32_t)(value < 0 ? -r : r);
    return 0;
}

int main(void)
{
    char mode;
    setvbuf(stdout, NULL, _IOLBF, 0);
    while (scanf(" %c", &mode) == 1) {
        if (mode == 'S') {
            int value, exp;
            int32_t result;
            assert(scanf("%d%d", &value, &exp) == 2);
            int status = scalar(value, exp, &result);
            printf("%d %d\n", status, result);
        } else {
            int rate, channel[16], sf[39], quant[576], status = 0;
            int16_t exponents[576];
            int32_t result[576];
            int band_exponents[39];
            assert(mode == 'V' && scanf("%d", &rate) == 1);
            for (int i = 0; i < 16; ++i) assert(scanf("%d", channel+i) == 1);
            for (int i = 0; i < 39; ++i) assert(scanf("%d", sf+i) == 1);
            for (int i = 0; i < 576; ++i) assert(scanf("%d", quant+i) == 1);
            for (int i = 0; i < 576; ++i) result[i] = (int32_t)UINT32_C(0xa55aa55a);
            for (int i = 0; i < 39; ++i) band_exponents[i] = 0xa55a;
            if (rate < 0 || rate > 8 || channel[2] < 0 || channel[2] > 255 ||
                channel[4] < 0 || channel[4] > 15 || channel[5] < 0 || channel[5] > 3) status = 2;
            for (int i = 9; i < 12; ++i) if (channel[i] < 0 || channel[i] > 7) status = 2;
            for (int i = 0; i < 39; ++i) if (sf[i] < 0 || sf[i] > 31) status = 2;
            for (int i = 0; i < 576; ++i) if (quant[i] < -8206 || quant[i] > 8206) status = 2;
            if (!status) {
                MPADecodeContext s = {.sample_rate_index = rate};
                GranuleDef g = {.block_type = channel[5], .switch_point = !!(channel[4]&8),
                    .global_gain = channel[2], .scalefac_scale = !!(channel[4]&2), .preflag = !!(channel[4]&4)};
                memcpy(g.scale_factors, sf, sizeof(sf));
                for (int i = 0; i < 3; ++i) g.subblock_gain[i] = channel[i+9];
                compute_band_indexes(&s, &g);
                exponents_from_scale_factors(&s, &g, exponents);
                memset(band_exponents, 0, sizeof(band_exponents));
                int pos = 0, band = 0;
                for (int i = 0; i < g.long_end; ++i) {
                    band_exponents[band++] = exponents[pos]-400;
                    pos += ff_band_size_long[rate][i];
                }
                for (int i = g.short_start; i < 13; ++i) for (int win = 0; win < 3; ++win) {
                    band_exponents[band++] = exponents[pos]-400;
                    pos += ff_band_size_short[rate][i];
                }
                assert(pos == 576 && band <= 39);
                for (int i = 0; i < 576; ++i) {
                    int32_t value;
                    status = scalar(quant[i], exponents[i]-400, &value);
                    /* This reference batch is non-overflowing; scalar and
                     * explicit vector policy fixtures exercise overflow. */
                    assert(status == 0);
                    result[i] = value;
                }
            }
            printf("%d", status);
            for (int i = 0; i < 39; ++i) printf(" %d", band_exponents[i]);
            for (int i = 0; i < 576; ++i) printf(" %d", result[i]);
            putchar('\n');
        }
    }
    return 0;
}
