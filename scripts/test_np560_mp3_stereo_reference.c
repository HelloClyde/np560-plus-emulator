/* SPDX-License-Identifier: GPL-2.0-or-later
 * OFFLINE oracle, never linked to QEMU. MS uses the public libmad Q28
 * constant/formula, widening BEFORE sum/difference. Reorder executes
 * the pinned FFmpeg function unchanged. No synthesis/PCM here.
 */
#include <stdint.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>

typedef int32_t INTFLOAT;
typedef struct { int sample_rate_index; void *avctx; } MPADecodeContext;
typedef struct {
    int block_type, switch_point, long_end, short_start;
    INTFLOAT sb_hybrid[576];
} GranuleDef;
#define avpriv_request_sample(...) ((void)0)
#include "ffmpeg_reorder.inc"

static int ms(int32_t m, int32_t s, int32_t *left, int32_t *right)
{
    int64_t l = (((int64_t)m+s)*INT64_C(0x0b504f33)) >> 28;
    int64_t r = (((int64_t)m-s)*INT64_C(0x0b504f33)) >> 28;
    *left = *right = 0;
    if (l < INT32_MIN || l > INT32_MAX || r < INT32_MIN || r > INT32_MAX) return 3;
    *left = (int32_t)l;
    *right = (int32_t)r;
    return 0;
}

int main(void)
{
    char mode;
    setvbuf(stdout, NULL, _IOLBF, 0);
    while (scanf(" %c", &mode) == 1) {
        if (mode == 'P') {
            int32_t m, s, l, r;
            assert(scanf("%"SCNd32"%"SCNd32, &m, &s) == 2);
            int status = ms(m, s, &l, &r);
            printf("%d %"PRId32" %"PRId32"\n", status, l, r);
        } else if (mode == 'R') {
            MPADecodeContext ctx = {0};
            GranuleDef g = {0};
            assert(scanf("%d%d%d", &ctx.sample_rate_index, &g.block_type, &g.switch_point) == 3);
            for (int i = 0; i < 576; ++i) assert(scanf("%"SCNd32, g.sb_hybrid+i) == 1);
            int status = ctx.sample_rate_index < 0 || ctx.sample_rate_index > 8 ||
                g.block_type < 0 || g.block_type > 3 || g.switch_point < 0 || g.switch_point > 1 ? 2 : 0;
            if (!status) {
                compute_band_indexes(&ctx, &g);
                reorder_block(&ctx, &g);
            }
            printf("%d", status);
            for (int i = 0; i < 576; ++i)
                printf(" %"PRId32, status ? (int32_t)UINT32_C(0xa55aa55a) : g.sb_hybrid[i]);
            puts("");
        } else {
            assert(mode == 'M');
            int32_t l[576], r[576];
            for (int i = 0; i < 576; ++i) assert(scanf("%"SCNd32, l+i) == 1);
            for (int i = 0; i < 576; ++i) assert(scanf("%"SCNd32, r+i) == 1);
            int status = 0;
            for (int i = 0; i < 576; ++i) {
                int32_t a, b;
                status = ms(l[i], r[i], &a, &b);
                if (status) break; /* failing coefficient remains unchanged */
                l[i] = a;
                r[i] = b;
            }
            printf("%d", status);
            for (int i = 0; i < 576; ++i) printf(" %"PRId32, l[i]);
            for (int i = 0; i < 576; ++i) printf(" %"PRId32, r[i]);
            puts("");
        }
    }
    return 0;
}
