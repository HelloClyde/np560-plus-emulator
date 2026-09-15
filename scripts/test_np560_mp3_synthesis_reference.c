/* SPDX-License-Identifier: GPL-2.0-or-later
 * OFFLINE integer ring + independently arranged FFmpeg window and full
 * floating 64x32 synthesis. Also runs pinned libmad's different fast DCT
 * / alternating-filter topology with long-double arithmetic from reset.
 * No host playback or QEMU linkage. PCM rounding ties toward +infinity.
 */
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include <assert.h>

typedef long double mad_fixed_t;
typedef long double mad_fixed64hi_t;
typedef uint32_t mad_fixed64lo_t;
struct mad_frame { mad_fixed_t sbsample[2][36][32]; };
struct mad_synth { mad_fixed_t filter[2][2][2][16][8]; unsigned phase;
                  struct { mad_fixed_t samples[2][1152]; } pcm; };
#define MAD_F(x) ((long double)(x)/268435456.L)
#define MUL(a,b) ((a)*(b))
#define SHIFT(x) (x)
#define PRESHIFT(x) MAD_F(x)
#define ML0(hi,lo,a,b) ((hi)=(a)*(b),(lo)=0)
#define MLA(hi,lo,a,b) ((hi)+=(a)*(b))
#define MLN(hi,lo) ((hi)=-(hi))
#define MLZ(hi,lo) ((void)(lo),(hi))
#include "libmad_synthesis_float.inc"
#include "ffmpeg_synthesis_window.inc"

#ifdef NP560_FAST_DCT
#undef MAD_F
#undef MUL
#undef SHIFT
#define MAD_F(x) ((int64_t)(x))
#define MUL(x,y) ((int64_t)(((__int128)(x)*(y))>>28))
#define SHIFT(x) (x)
#include "libmad_dct32_wide.inc"
#endif

static int32_t cosine[32][32],window[512];
static long double exact_cosine[64][32],max_math_error,max_mad_error;
static int32_t previous[1024];
static int previous_head;
static long double floating_v[1024];
static struct mad_synth mad;
static int comparable;

static int16_t clip(int64_t v) { return v<-32768 ? -32768 : v>32767 ? 32767 : (int16_t)v; }

static void initialize(void)
{
    long double pi=acosl(-1);
    for (int i=0;i<64;++i) for (int k=0;k<32;++k) exact_cosine[i][k]=cosl(pi*(i+16)*(2*k+1)/64);
    for (int i=0;i<32;++i) for (int k=0;k<32;++k) cosine[i][k]=(int32_t)llroundl(exact_cosine[i<16 ? i : i+17][k]*67108864.L);
    for (int i=0;i<257;++i) {
        window[i]=ff_mpa_enwindow[i];
        if (i) window[512-i]=(i&63) ? -window[i] : window[i];
    }
}

static void slot(int32_t v[1024],int *head,const int32_t input[32],int16_t pcm[32])
{
    *head=(*head-64)&1023;
    int32_t *row=v+*head;
#ifdef NP560_FAST_DCT
    int64_t wide[32],lo[16][8],hi[16][8];
    for (int k=0;k<32;++k) wide[k]=input[k];
    dct32_wide(wide,0,lo,hi);
    for (int i=0;i<16;++i) { row[i]=(int32_t)(lo[i][0]>>6);row[33+i]=(int32_t)((-hi[i][0])>>6); }
#else
    for (int i=0;i<32;++i) {
        int64_t sum=0;
        for (int k=0;k<32;++k) sum+=(int64_t)input[k]*cosine[i][k];
        row[i<16 ? i : i+17]=(int32_t)(sum>>32);
    }
#endif
    for (int i=0;i<16;++i) row[32-i]=-row[i];
    row[16]=0;
    for (int i=33;i<48;++i) row[96-i]=row[i];
    long double float_pcm[32]={0};
    if (comparable) {
        memmove(floating_v+64,floating_v,960*sizeof(*floating_v));
        for (int i=0;i<64;++i) {
            floating_v[i]=0;
            for (int k=0;k<32;++k) floating_v[i]+=input[k]/8388608.L*exact_cosine[i][k];
        }
        struct mad_frame f={0};
        for (int k=0;k<32;++k) f.sbsample[0][0][k]=input[k]/8388608.L;
        synth_full(&mad,&f,1,1);
        mad.phase=(mad.phase+1)&15;
    }
    for (int j=0;j<32;++j) {
        int64_t sum=0;
        for (int i=0;i<16;++i) {
            int off=128*(i/2)+(i%2 ? 96 : 0)+j;
            sum+=(int64_t)v[(*head+off)&1023]*window[j+32*i];
            if (comparable) float_pcm[j]+=floating_v[off]*window[j+32*i]/65536.L;
        }
        pcm[j]=clip((sum+INT64_C(131072))>>18);
        if (comparable) {
            long double e=fabsl((long double)pcm[j]-clip((int64_t)floorl(float_pcm[j]*32768+.5L)));
            if (e>max_math_error) max_math_error=e;
            assert(e<=8); /* Q26 row quantization plus Q17 history/PCM rounding */
            e=fabsl((long double)pcm[j]-clip((int64_t)floorl(mad.pcm.samples[0][j]*32768+.5L)));
            if (e>max_mad_error) max_mad_error=e;
            assert(e<=32); /* independent fast DCT uses pinned Q28 constants */
        }
    }
}

int main(void)
{
    initialize();
    char mode;
    setvbuf(stdout,NULL,_IOLBF,0);
    while (scanf(" %c",&mode)==1) {
        int bank,ptr,head,action,status=0,ns=mode=='G' ? 18 : 1;
        int32_t input[576]={0},v[1024];
        int16_t pcm[576];
        for (int i=0;i<576;++i) pcm[i]=(int16_t)0xa55a;
        assert(scanf("%d%d%d%d",&bank,&ptr,&head,&action)==4);
        for (int i=0;i<ns*32;++i) assert(scanf("%"SCNd32,input+i)==1);
        for (int i=0;i<1024;++i) assert(scanf("%"SCNd32,v+i)==1);
        if (action==1) { memcpy(v,previous,sizeof(v));head=previous_head; }
        else {
            comparable=1;
            memset(floating_v,0,sizeof(floating_v));memset(&mad,0,sizeof(mad));
            for (int i=0;i<1024;++i) if (v[i]) comparable=0;
        }
        if (action==2) { memset(v,0,sizeof(v));head=0;comparable=1;memset(floating_v,0,sizeof(floating_v));memset(&mad,0,sizeof(mad)); }
        if (bank<0 || bank>511 || ptr<0x8000 || ptr>0xeffe || (ptr&1) || head<0 || head>3840 || (head&255)) status=2;
        else {
            head/=4;
            for (int t=0;t<ns;++t) slot(v,&head,input+t*32,pcm+t*32);
            head*=4;
        }
        memcpy(previous,v,sizeof(v));previous_head=head;
        if (status) comparable=0;
        printf("%d %d",status,head);
        for (int i=0;i<ns*32;++i) printf(" %d",pcm[i]);
        for (int i=0;i<1024;++i) printf(" %"PRId32,v[i]);
        puts("");
    }
    fprintf(stderr,"max_pcm_math_difference=%.0Lf\nmax_pcm_libmad_float_difference=%.0Lf\n",max_math_error,max_mad_error);
    return 0;
}
