/* SPDX-License-Identifier: GPL-2.0-or-later
 * OFFLINE adapted libmad oracle. Explicit adaptations are in its Python
 * extractor: raw-quant boundaries, 8k mixed prefix, widened MS arithmetic.
 * Top-band SF/mask inheritance is applied to private channel copies below.
 */
#include <stdint.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>

typedef int32_t mad_fixed_t;
#define MAD_F(x) ((mad_fixed_t)(x))
enum mad_error { MAD_ERROR_NONE = 0, MAD_ERROR_BADSTEREO = 2 };
enum { MAD_FLAG_I_STEREO = 1, MAD_FLAG_MS_STEREO = 2, MAD_FLAG_LSF_EXT = 4 };
struct mad_header { unsigned mode_extension, flags; };
static mad_fixed_t quant_right[576];
static unsigned mixed_lines;
static short observed_modes[39];
static int32_t mad_f_mul(int64_t x, int32_t y)
{
    int64_t result = (x*y) >> 28;
    assert(result >= INT32_MIN && result <= INT32_MAX);
    return (int32_t)result;
}
#include "libmad_joint.inc"
#include "ffmpeg_joint_bands.inc"

static void pair(int32_t value, int index, int32_t *l, int32_t *r)
{
    if (index < 7) {
        *l = mad_f_mul(value, is_table[index]);
        *r = mad_f_mul(value, is_table[6-index]);
    } else {
        int scale = (index-7)/31, pos = (index-7)%31;
        int32_t opposite = pos ? mad_f_mul(value, is_lsf_table[scale][(pos-1)/2]) : value;
        *l = pos&1 ? opposite : value;
        *r = pos&1 ? value : opposite;
    }
}

int main(void)
{
    char mode;
    setvbuf(stdout, NULL, _IOLBF, 0);
    while (scanf(" %c", &mode) == 1) {
        if (mode == 'P') {
            int32_t value, l=0, r=0;
            int index;
            assert(scanf("%"SCNd32"%d", &value, &index) == 2);
            int status = index < 0 || index > 68 ? 2 : 0;
            if (!status) pair(value, index, &l, &r);
            printf("%d %"PRId32" %"PRId32"\n", status, l, r);
        } else {
            int rate, ext, fields[2][16], sf[39], mask[39], tags[39];
            int32_t xr[2][576];
            struct granule gr[2] = {0};
            unsigned char widths[39];
            assert(mode == 'J' && scanf("%d%d", &rate, &ext) == 2);
            for (int c=0;c<2;++c) for (int i=0;i<16;++i) assert(scanf("%d", fields[c]+i) == 1);
            for (int i=0;i<39;++i) assert(scanf("%d", sf+i) == 1);
            for (int i=0;i<39;++i) assert(scanf("%d", mask+i) == 1);
            for (int i=0;i<576;++i) assert(scanf("%"SCNd32, quant_right+i) == 1);
            for (int c=0;c<2;++c) for (int i=0;i<576;++i) assert(scanf("%"SCNd32, &xr[c][i]) == 1);
            int status = rate < 0 || rate > 8 || ext < 0 || ext > 3 ? 2 : 0;
            for (int c=0;c<2;++c) {
                if (fields[c][4]<0 || fields[c][4]>15 || fields[c][5]<0 || fields[c][5]>3) status=2;
                gr[0].ch[c].flags=fields[c][4]; gr[0].ch[c].block_type=fields[c][5];
                gr[0].ch[c].scalefac_compress=fields[c][3];
            }
            if (ext && (fields[0][5]!=fields[1][5] || ((fields[0][4]^fields[1][4])&8))) status=2;
            if (ext&1) {
                if (fields[1][3]<0 || fields[1][3]>(rate<3?15:511)) status=2;
                for (int i=0;i<39;++i)
                    if (sf[i]<0 || sf[i]>31 || mask[i]<0 || mask[i]>1 || (rate>=3 && sf[i]==31 && !mask[i])) status=2;
            }
            for (int i=0;i<39;++i) tags[i]=0xa55a;
            if (!status && ext) {
                int short_block=fields[1][5]==2, mixed=short_block && (fields[1][4]&8);
                int long_end=short_block?(mixed?(rate<3?8:6):0):22;
                int short_start=short_block?(mixed?3:0):13, nb=0;
                mixed_lines=0;
                for (int i=0;i<long_end;++i) {
                    widths[nb++]=ff_band_size_long[rate][i];
                    mixed_lines+=ff_band_size_long[rate][i];
                }
                for (int i=short_start;i<13;++i) for (int w=0;w<3;++w) widths[nb++]=ff_band_size_short[rate][i];
                for (int i=0;i<39;++i) {
                    gr[0].ch[1].scalefac[i]=sf[i];
                    gr[1].ch[1].scalefac[i]=mask[i];
                }
                int tail=short_block?3:1;
                for (int i=nb-tail;i<nb;++i) {
                    gr[0].ch[1].scalefac[i]=sf[i-tail];
                    gr[1].ch[1].scalefac[i]=mask[i-tail];
                }
                struct mad_header header={ext,rate<3?0:MAD_FLAG_LSF_EXT};
                status=III_stereo(xr, gr, &header, widths);
                int base=rate<3?0:7+31*(fields[1][3]&1);
                for (int i=0;i<39;++i)
                    tags[i]=i>=nb?0:((observed_modes[i]&I_STEREO)?2+base+gr[0].ch[1].scalefac[i]:
                        ((observed_modes[i]&MS_STEREO)?1:0));
            }
            printf("%d",status);
            for (int i=0;i<39;++i) printf(" %d",tags[i]);
            for (int c=0;c<2;++c) for (int i=0;i<576;++i) printf(" %"PRId32,xr[c][i]);
            puts("");
        }
    }
    return 0;
}
