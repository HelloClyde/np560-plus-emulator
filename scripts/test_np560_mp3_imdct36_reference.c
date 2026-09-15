/* SPDX-License-Identifier: GPL-2.0-or-later
 * OFFLINE pinned libmad functions with wide integer intermediates.
 * No QEMU linkage; not libmad's original 32-bit overflow behaviour.
 */
#include <stdint.h>
#include <inttypes.h>
#include <assert.h>
#include <stdio.h>
typedef int64_t mad_fixed_t;
#define MAD_F(x) ((int64_t)(x))
static int64_t mad_f_mul(int64_t a, int64_t b)
{
    return (int64_t)(((__int128)a * b) >> 28);
}
#include "libmad_imdct36_wide.inc"

int main(void)
{
    int block;
    while (scanf("%d", &block) == 1) {
        mad_fixed_t input[18], output[36];
        assert(block == 0 || block == 1 || block == 3);
        for (int i=0; i<18; ++i) assert(scanf("%" SCNd64, input+i)==1);
        III_imdct_l(input, output, block);
        for (int i=0; i<36; ++i) printf("%s%" PRId64, i ? " " : "", output[i] >> 5);
        putchar('\n');
    }
    return 0;
}
