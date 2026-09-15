/* SPDX-License-Identifier: GPL-2.0-or-later
 * Compile and execute the pinned original C function independently of the
 * native expression emitter, widening values and products instead of
 * narrowing valid inputs. Separately check the mathematical cosine matrix.
 * Offline only; not linked into QEMU or used during playback.
 */
#include <assert.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>

typedef int64_t mad_fixed_t;
#define MAD_F(x) ((int64_t)(x))
#define MUL(x,y) ((int64_t)(((__int128)(x)*(y))>>28))
#define SHIFT(x) (x)
#include "libmad_dct32_wide.inc"

int main(void)
{
    int64_t input[32],lo[16][8],hi[16][8],v[64];
    long double max_error=0;
    while (scanf("%"SCNd64,input)==1) {
        for (int i=1;i<32;++i) assert(scanf("%"SCNd64,input+i)==1);
        dct32(input,0,lo,hi);
        for (int i=0;i<16;++i) { v[i]=lo[i][0]>>6;v[33+i]=(-hi[i][0])>>6; }
        for (int i=0;i<16;++i) v[32-i]=-v[i];
        v[16]=0;
        for (int i=33;i<48;++i) v[96-i]=v[i];
        for (int i=0;i<64;++i) {
            long double exact=0;
            for (int k=0;k<32;++k) exact+=input[k]*cosl(acosl(-1)*(i+16)*(2*k+1)/64)/64;
            long double error=fabsl(v[i]-exact);
            if (error>max_error) max_error=error;
            assert(v[i]>=INT32_MIN && v[i]<=INT32_MAX);
            /* Wide Q28 factorization versus exact real cosines, including
             * extreme int32 inputs. Not an equality claim about old Q26. */
            assert(error<128);
            printf("%s%"PRId64,i ? " " : "",v[i]);
        }
        puts("");
    }
    fprintf(stderr,"max_v_q17_math_difference=%.9Lf\n",max_error);
    return 0;
}
