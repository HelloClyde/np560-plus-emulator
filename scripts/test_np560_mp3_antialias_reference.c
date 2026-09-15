/* SPDX-License-Identifier: GPL-2.0-or-later
 * OFFLINE oracle, never linked with QEMU. Executes pinned libmad
 * III_aliasreduce with unchanged function text and cs/ca arrays, but
 * widened sample/accumulator types. Exact signed products are added
 * before floor(/2^28); wrapper enforces the guest's pair-atomic overflow
 * contract. Not pristine libmad fixed.h rounding or full PCM conformance.
 */
#include <stdint.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>

typedef int64_t mad_fixed_t;
typedef int64_t mad_fixed64hi_t;
typedef uint32_t mad_fixed64lo_t;
#define MAD_F(x) INT64_C(x)
#define MAD_F_ML0(hi,lo,a,b) ((hi)=(int64_t)(a)*(b),(lo)=0)
#define MAD_F_MLA(hi,lo,a,b) ((hi)+=(int64_t)(a)*(b))
#define MAD_F_MLZ(hi,lo) ((void)(lo),(hi)>>28)
#include "libmad_antialias.inc"

static int fits(int64_t n) { return n >= INT32_MIN && n <= INT32_MAX; }

int main(void)
{
    char mode;
    setvbuf(stdout, NULL, _IOLBF, 0);
    while (scanf(" %c", &mode) == 1) {
        int index, rate, block, mixed, status=0;
        int64_t xr[576]={0}, original[576];
        if (mode == 'P') {
            int32_t a, b;
            assert(scanf("%d%"SCNd32"%"SCNd32, &index, &a, &b) == 3);
            int64_t u=0, v=0;
            if (index < 0 || index > 7) status=2;
            else {
                xr[17-index]=a; xr[18+index]=b;
                III_aliasreduce(xr,36);
                u=xr[17-index]; v=xr[18+index];
                if (!fits(u) || !fits(v)) { status=3; u=v=0; }
            }
            printf("%d %"PRId64" %"PRId64"\n", status,u,v);
        } else {
            assert(mode == 'V');
            assert(scanf("%d%d%d", &rate,&block,&mixed) == 3);
            for (int i=0;i<576;++i) assert(scanf("%"SCNd64,xr+i) == 1);
            memcpy(original,xr,sizeof(xr));
            if (rate<0 || rate>8 || block<0 || block>3 || mixed<0 || mixed>1) status=2;
            else {
                int lines=block!=2 ? 576 : !mixed ? 0 : rate==8 ? 72 : 36;
                if (lines) III_aliasreduce(xr,lines);
                for (int edge=18;edge<lines && !status;edge+=18) {
                    for (int i=0;i<8;++i) {
                        int l=edge-1-i,r=edge+i;
                        if (!fits(xr[l]) || !fits(xr[r])) { status=3; break; }
                        original[l]=xr[l]; original[r]=xr[r];
                    }
                }
            }
            printf("%d",status);
            for (int i=0;i<576;++i) printf(" %"PRId64,original[i]);
            puts("");
        }
    }
    return 0;
}
