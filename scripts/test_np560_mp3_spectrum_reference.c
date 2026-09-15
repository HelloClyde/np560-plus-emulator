/* SPDX-License-Identifier: GPL-2.0-or-later
 * OFFLINE entropy oracle only. libmad bit/Huffman algorithm with identity
 * requantization exposes the signed integers, not PCM. FFmpeg's unchanged
 * region functions supply boundaries independently of the native generator.
 */
#include <stdio.h>
#include <string.h>
#include <assert.h>
enum mad_error { MAD_ERROR_NONE=0, MAD_ERROR_BADSCFSI=3,
                 MAD_ERROR_BADHUFFTABLE=4, MAD_ERROR_BADHUFFDATA=5 };
typedef int mad_fixed_t;
struct mad_bitptr { unsigned char data[1024]; unsigned pos; };
static unsigned long mad_bit_read(struct mad_bitptr *p, unsigned n)
{
    unsigned long v=0;
    assert(p->pos+n <= sizeof(p->data)*8);
    while (n--) { v=(v<<1)|((p->data[p->pos/8]>>(7-p->pos%8))&1); ++p->pos; }
    return v;
}
static unsigned mad_bit_length(const struct mad_bitptr *a, const struct mad_bitptr *b) { return b->pos-a->pos; }
static void mad_bit_skip(struct mad_bitptr *p, unsigned n) { p->pos+=n; }
static unsigned mad_bit_bitsleft(const struct mad_bitptr *p) { return 8-p->pos%8; }
#include "libmad_scalefactors.inc"
#include "huffman.h"
static unsigned observed_coded, observed_stuffing;
static mad_fixed_t III_requantize(unsigned value, int exp) { (void)exp; return value; }
static void III_exponents(const struct channel *c, const unsigned char *w, int exponents[39])
{ (void)c; (void)w; memset(exponents,0,39*sizeof(*exponents)); }
#include "libmad_entropy.inc"
typedef struct { int sample_rate_index; } MPADecodeContext;
typedef struct { int block_type, region_size[3]; } GranuleDef;
#define FFMIN(a,b) ((a)<(b)?(a):(b))
static int ff_band_index_long[9][23];
#include "ffmpeg_regions.inc"
int main(void)
{
    setvbuf(stdout, NULL, _IOLBF, 0);
    unsigned lsf,freq,scfsi,intensity,prefix,values[16],previous_values[39],i,row;
    char hex[2049];
    for(row=0;row<9;++row) for(i=0;i<22;++i)
        ff_band_index_long[row][i+1]=ff_band_index_long[row][i]+ff_band_size_long[row][i]/2;
    while(scanf("%u %u %u %u %u",&lsf,&freq,&scfsi,&intensity,&prefix)==5) {
        struct channel ch, previous;
        struct mad_bitptr p={{0},prefix};
        unsigned part2=0,status=0,region,band=0;
        unsigned char bands[39]={0};
        int quant[576]={0},end=0;
        MPADecodeContext s={(int)freq};
        GranuleDef g={0,{0,0,288}};
        for(i=0;i<16;++i) assert(scanf("%u",&values[i])==1);
        for(i=0;i<39;++i) assert(scanf("%u",&previous_values[i])==1);
        assert(scanf("%2048s",hex)==1);
        memset(&ch,0,sizeof(ch)); memset(&previous,0,sizeof(previous));
        for(i=0;i<strlen(hex)/2;++i) { unsigned b; assert(sscanf(hex+2*i,"%2x",&b)==1);p.data[i]=b; }
        ch.part2_3_length=values[0];ch.big_values=values[1];ch.global_gain=values[2];
        ch.scalefac_compress=values[3];ch.flags=values[4];ch.block_type=values[5];
        for(i=0;i<3;++i) { ch.table_select[i]=values[6+i];ch.subblock_gain[i]=values[9+i]; }
        ch.region0_count=values[12];ch.region1_count=values[13];
        for(i=0;i<39;++i)previous.scalefac[i]=previous_values[i];
        g.block_type=ch.block_type;
        if(values[14])init_short_region(&s,&g);else init_long_region(&s,&g,ch.region0_count,ch.region1_count);
        /* All exponents are zero for this entropy-only observation, so
         * split the independently calculated regions into <=192-wide bands.
         * This avoids relying on libmad's explicitly uncertain 8k mixed SFB
         * layout. Huffman bit decoding itself is unchanged.
         */
        for(region=0;region<3;++region) {
            unsigned count=0;
            int width=g.region_size[region]*2-end;
            end=g.region_size[region]*2;
            while(width>0) { int n=FFMIN(width,192);bands[band++]=n;width-=n;++count; }
            if(region==0)ch.region0_count=count-1;
            if(region==1)ch.region1_count=count-1;
        }
        assert(band<39);
        status=lsf?III_scalefactors_lsf(&p,&ch,intensity?&previous:0,intensity?I_STEREO:0,
                                       ch.part2_3_length,&part2)
                  :III_scalefactors(&p,&ch,&previous,scfsi,ch.part2_3_length,&part2);
        observed_coded=observed_stuffing=0;
        if(!status && part2<=ch.part2_3_length)
            status=III_huffdecode(&p,quant,&ch,bands,ch.part2_3_length-part2);
        if(!status && part2==ch.part2_3_length) observed_coded=ch.big_values*2;
        printf("%u %u %u %u %u",status,part2,observed_coded,observed_stuffing,ch.flags);
        for(i=0;i<39;++i)printf(" %u",ch.scalefac[i]);
        for(i=0;i<39;++i)printf(" %u",lsf&&intensity?previous.scalefac[i]:0);
        for(i=0;i<576;++i)printf(" %d",quant[i]);
        putchar('\n');
    }
    return 0;
}
