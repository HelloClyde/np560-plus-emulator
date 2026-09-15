/* SPDX-License-Identifier: GPL-2.0-or-later
 * OFFLINE mathematical reference. Independently builds long-double
 * coefficients, checks integer dots against unfused IMDCT -> window ->
 * three-short-window overlap, then applies persistent overlap/inversion.
 * No QEMU linkage; not pristine libmad rounding or synthesis PCM.
 */
#include <stdint.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <assert.h>
#include <string.h>

typedef long double mad_fixed_t;
typedef long double mad_fixed64hi_t;
typedef uint32_t mad_fixed64lo_t;
#define MAD_F(x) ((long double)(x)/268435456.L)
#define mad_f_mul(a,b) ((a)*(b))
#define MAD_F_ML0(hi,lo,a,b) ((hi)=(a)*(b),(lo)=0)
#define MAD_F_MLA(hi,lo,a,b) ((hi)+=(a)*(b))
#define MAD_F_MLZ(hi,lo) ((void)(lo),(hi))
#include "libmad_hybrid_float.inc"

static int32_t matrix[4][36][18];
static long double pi;
static long double maximum_error;
static long double maximum_libmad_error;

static long double win(int b,int n)
{
    if (b==1 && n>=18) return n<24 ? 1 : n<30 ? sinl(pi*(n-17.5L)/12) : 0;
    if (b==3 && n<18) return n<6 ? 0 : n<12 ? sinl(pi*(n-5.5L)/12) : 1;
    return sinl(pi*(n+.5L)/36);
}

static void initialize(void)
{
    pi=acosl(-1);
    for (int b=0;b<4;++b) for (int n=0;n<36;++n) {
        int64_t norm=0;
        for (int k=0;k<18;++k) {
            long double v;
            if (b==2) {
                int w=k%3,t=n-6*(w+1),freq=k/3;
                v=t<0 || t>=12 ? 0 : sinl(pi*(t+.5L)/12)*cosl(pi*(t+3.5L)*(freq+.5L)/6);
            } else v=win(b,n)*cosl(pi*(n+9.5L)*(k+.5L)/18);
            matrix[b][n][k]=(int32_t)llroundl(v*268435456.L);
            norm+=llabs(matrix[b][n][k]);
        }
        assert(norm < INT64_C(16)*268435456);
    }
}

static void transform(int block,const int32_t x[18],int32_t z[36])
{
    long double ideal[36]={0};
    mad_fixed_t mad_x[18],mad_z[36];
    for (int i=0;i<18;++i) mad_x[block==2 ? 6*(i%3)+i/3 : i]=x[i];
    if (block==2) III_imdct_s(mad_x,mad_z);
    else III_imdct_l(mad_x,mad_z,(unsigned)block);
    if (block!=2) {
        for (int n=0;n<36;++n) {
            long double total=0;
            for (int k=0;k<18;++k) total+=x[k]*cosl(pi*(n+9.5L)*(k+.5L)/18);
            ideal[n]=total*win(block,n)/32;
        }
    } else {
        for (int w=0;w<3;++w) for (int n=0;n<12;++n) {
            long double total=0;
            for (int k=0;k<6;++k) total+=x[3*k+w]*cosl(pi*(n+3.5L)*(k+.5L)/6);
            ideal[n+6+6*w]+=total*sinl(pi*(n+.5L)/12)/32;
        }
    }
    for (int n=0;n<36;++n) {
        int64_t acc=0;
        for (int k=0;k<18;++k) acc+=(int64_t)x[k]*matrix[block][n][k];
        z[n]=(int32_t)(acc>>33);
        long double e=fabsl(z[n]-ideal[n]);
        if (e>maximum_error) maximum_error=e;
        assert(e<4);
        long double mad_error=fabsl(z[n]-mad_z[n]/32);
        if (mad_error>maximum_libmad_error) maximum_libmad_error=mad_error;
        assert(mad_error<32); /* fast factorization uses quantized constants */
        assert(z[n] > -INT64_C(1073741824) && z[n] < INT64_C(1073741824));
    }
}

int main(void)
{
    initialize();
    char mode;
    int32_t previous[576]={0};
    setvbuf(stdout,NULL,_IOLBF,0);
    while (scanf(" %c",&mode)==1) {
        int block,rate=0,mixed=0,action=0,status=0;
        int32_t x[576]={0},z[36],out[576],overlap[576]={0};
        for (int i=0;i<576;++i) out[i]=(int32_t)UINT32_C(0xa55aa55a);
        if (mode=='T') {
            assert(scanf("%d",&block)==1);
            for (int i=0;i<18;++i) assert(scanf("%"SCNd32,x+i)==1);
            if (block<0 || block>3) status=2;
            else transform(block,x,out);
            printf("%d",status);
            for (int i=0;i<36;++i) printf(" %"PRId32,out[i]);
        } else {
            assert(mode=='H');
            assert(scanf("%d%d%d%d",&rate,&block,&mixed,&action)==4);
            for (int i=0;i<576;++i) assert(scanf("%"SCNd32,x+i)==1);
            for (int i=0;i<576;++i) assert(scanf("%"SCNd32,overlap+i)==1);
            if (action==1) memcpy(overlap,previous,sizeof(overlap));
            if (action==2) memset(overlap,0,sizeof(overlap));
            if (rate<0 || rate>8 || block<0 || block>3 || mixed<0 || mixed>1) status=2;
            else for (int sb=0;sb<32 && !status;++sb) {
                int b=block;
                if (block==2 && mixed && sb<(rate==8 ? 4 : 2)) b=0;
                transform(b,x+18*sb,z);
                for (int t=0;t<18;++t) {
                    int64_t v=(int64_t)z[t]+overlap[sb*18+t];
                    if ((sb&t&1)!=0) v=-v;
                    if (v<INT32_MIN || v>INT32_MAX) { status=3;break; }
                    out[t*32+sb]=(int32_t)v;
                    overlap[sb*18+t]=z[t+18];
                }
            }
            memcpy(previous,overlap,sizeof(overlap));
            printf("%d",status);
            for (int i=0;i<576;++i) printf(" %"PRId32,out[i]);
            for (int i=0;i<576;++i) printf(" %"PRId32,overlap[i]);
        }
        puts("");
    }
    fprintf(stderr,"maximum_q23_formula_error=%.12Lf\n",maximum_error);
    fprintf(stderr,"maximum_q23_libmad_float_error=%.12Lf\n",maximum_libmad_error);
    return 0;
}
