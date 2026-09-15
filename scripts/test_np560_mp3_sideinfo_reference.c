/* SPDX-License-Identifier: GPL-2.0-or-later
 * Offline oracle only. The included function and structs are mechanically
 * extracted from the pinned libmad source; never linked to QEMU/guest.
 */
#include <stdio.h>
#include <string.h>
#include <assert.h>

enum mad_error {
    MAD_ERROR_NONE = 0, MAD_ERROR_BADBIGVALUES = 3,
    MAD_ERROR_BADBLOCKTYPE = 4, MAD_ERROR_BADSCFSI = 5
};
struct mad_bitptr { unsigned char data[32]; unsigned pos; };
static unsigned long mad_bit_read(struct mad_bitptr *p, unsigned n)
{
    unsigned long value = 0;
    assert(p->pos + n <= 256);
    while (n--) {
        value = (value << 1) | ((p->data[p->pos / 8] >> (7-p->pos % 8)) & 1);
        ++p->pos;
    }
    return value;
}

#include "libmad_sideinfo.inc"

int main(void)
{
    unsigned lsf, nch;
    char hex[65];
    while (scanf("%u %u %64s", &lsf, &nch, hex) == 3) {
        struct mad_bitptr p = {{0}, 0};
        struct sideinfo si;
        unsigned words[72] = {0}, data_bits, private_bits, i, gr, ch;
        unsigned ngr = lsf ? 1 : 2;
        memset(&si, 0, sizeof(si));
        assert(lsf <= 1 && nch >= 1 && nch <= 2 && strlen(hex) % 2 == 0);
        for (i = 0; i < strlen(hex)/2; ++i) {
            unsigned byte;
            assert(sscanf(hex+2*i, "%2x", &byte) == 1);
            p.data[i] = byte;
        }
        enum mad_error status = III_sideinfo(&p, nch, lsf, &si, &data_bits, &private_bits);
        words[0] = si.main_data_begin;
        words[1] = si.private_bits;
        words[2] = si.scfsi[0]; words[3] = si.scfsi[1];
        words[4] = data_bits; words[5] = nch; words[6] = ngr; words[7] = p.pos;
        for (gr = 0; gr < ngr; ++gr) for (ch = 0; ch < nch; ++ch) {
            const struct channel *c = &si.gr[gr].ch[ch];
            unsigned *w = words+8+(gr*nch+ch)*16;
            w[0] = c->part2_3_length; w[1] = c->big_values;
            w[2] = c->global_gain; w[3] = c->scalefac_compress;
            w[4] = c->flags; w[5] = c->block_type;
            for (i = 0; i < 3; ++i) { w[6+i] = c->table_select[i]; w[9+i] = c->subblock_gain[i]; }
            w[12] = c->region0_count; w[13] = c->region1_count;
        }
        printf("%u %u", status, p.pos);
        for (i = 0; i < 72; ++i) printf(" %u", words[i]);
        putchar('\n');
    }
    return 0;
}
