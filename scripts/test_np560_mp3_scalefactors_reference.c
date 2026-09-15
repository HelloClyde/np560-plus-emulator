/* SPDX-License-Identifier: GPL-2.0-or-later
 * Offline execution of the pinned libmad functions; not part of QEMU.
 */
#include <stdio.h>
#include <string.h>
#include <assert.h>
enum mad_error { MAD_ERROR_NONE = 0, MAD_ERROR_BADSCFSI = 5 };
struct mad_bitptr { unsigned char data[64]; unsigned pos; };
static unsigned long mad_bit_read(struct mad_bitptr *p, unsigned n)
{
    unsigned long v = 0;
    assert(p->pos+n <= 512);
    while (n--) {
        v = (v << 1) | ((p->data[p->pos/8] >> (7-p->pos % 8)) & 1);
        ++p->pos;
    }
    return v;
}
static unsigned mad_bit_length(const struct mad_bitptr *start, const struct mad_bitptr *end)
{ return end->pos-start->pos; }
#include "libmad_scalefactors.inc"
int main(void)
{
    unsigned lsf, comp, block, flags, scfsi, intensity, prefix;
    char hex[129];
    while (scanf("%u %u %u %u %u %u %u %128s", &lsf, &comp, &block, &flags,
                 &scfsi, &intensity, &prefix, hex) == 8) {
        struct mad_bitptr p = {{0}, prefix};
        struct channel channel, previous;
        unsigned i, length = 0, status;
        memset(&channel, 0, sizeof(channel));
        memset(&previous, 0, sizeof(previous));
        for (i = 0; i < strlen(hex)/2; ++i) {
            unsigned byte;
            assert(sscanf(hex+2*i, "%2x", &byte) == 1);
            p.data[i] = byte;
        }
        channel.scalefac_compress = comp;
        channel.block_type = block; channel.flags = flags;
        for (i = 0; i < 39; ++i) previous.scalefac[i] = (i*7+5) & 31;
        status = lsf ? III_scalefactors_lsf(&p, &channel, intensity ? &previous : 0,
                                           intensity ? I_STEREO : 0, 512-prefix, &length)
                     : III_scalefactors(&p, &channel, &previous, scfsi, 512-prefix, &length);
        assert(status == 0);
        printf("%u %u", length, channel.flags);
        for (i = 0; i < 39; ++i) printf(" %u", channel.scalefac[i]);
        for (i = 0; i < 39; ++i) printf(" %u", lsf && intensity ? previous.scalefac[i] : 0);
        putchar('\n');
    }
    return 0;
}
