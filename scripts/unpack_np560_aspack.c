/* SPDX-License-Identifier: GPL-2.0-only
 * Static ASPack 2.12 analysis adapter. Does not execute the input or repair IAT.
 * gcc -O1 -g -fsanitize=address,undefined scripts/unpack_np560_aspack.c -o tmp/np560-unaspack
 * tmp/np560-unaspack input.dll.bin output.rva.bin
 */
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include "np560_aspack_compat.h"
#include "vendor/clamav-aspack/aspack.c"

static uint8_t *input_buffer, *image_buffer;
static void fail(const char *message)
{
    fprintf(stderr, "error: %s\n", message);
    free(input_buffer); free(image_buffer);
    exit(1);
}
static uint16_t u16(const uint8_t *p)
{ return p[0] | (uint16_t)p[1]<<8; }
static int contained(size_t size, size_t at, size_t n)
{ return at <= size && n <= size-at; }

int main(int argc, char **argv)
{
    if (argc != 3) fail("usage: unpack_np560_aspack input.dll.bin output.rva.bin");
    FILE *f = fopen(argv[1], "rb");
    if (!f) fail("cannot open input");
    if (fseek(f,0,SEEK_END)) fail("input seek failed");
    long length = ftell(f);
    if (length < 0x100 || length > NP560_ASPACK_LIMIT) fail("input size outside limit");
    rewind(f);
    uint8_t *raw = input_buffer = malloc(length);
    if (!raw || fread(raw,1,length,f) != (size_t)length) fail("input read failed");
    fclose(f);
    if (memcmp(raw,"MZ",2)) fail("not MZ");
    uint32_t pe = cli_readint32(raw+0x3c);
    if (!contained(length,pe,24+96) || memcmp(raw+pe,"PE\0\0",4)) fail("bad PE header");
    uint8_t *coff = raw+pe+4, *opt = coff+20;
    uint16_t nsec = u16(coff+2), opts = u16(coff+16);
    if (u16(coff) != 0x14c || u16(opt) != 0x10b || opts < 96 || nsec < 3 || nsec > 32)
        fail("expected x86 PE32 with bounded section count");
    if (!contained(length,pe+24,opts+(size_t)nsec*40)) fail("section table out of bounds");
    uint32_t size = cli_readint32(opt+56), headers = cli_readint32(opt+60);
    uint32_t vep = cli_readint32(opt+16), base = cli_readint32(opt+28);
    if (size < headers || size > NP560_ASPACK_LIMIT || headers > (uint32_t)length || !vep)
        fail("bad image layout");
    uint8_t *image = image_buffer = calloc(1,size);
    if (!image) fail("image allocation failed");
    memcpy(image,raw,headers);
    struct cli_exe_section sections[32];
    for (unsigned i=0; i<nsec; ++i) {
        uint8_t *p = opt+opts+i*40;
        sections[i] = (struct cli_exe_section){cli_readint32(p+12),cli_readint32(p+8),
                                              cli_readint32(p+20),cli_readint32(p+16)};
        struct cli_exe_section s=sections[i];
        if (!contained(size,s.rva,s.vsz) || !contained(size,s.rva,s.rsz) ||
            !contained(length,s.raw,s.rsz)) fail("section out of bounds");
        memcpy(image+s.rva,raw+s.raw,s.rsz);
    }
    uint32_t ep = vep-1; /* ClamAV pe.c uses vep-1 for the 2.12 stub. */
    if (!contained(size,ep,0x748) || memcmp(image+vep,"\x60\xe8\x03\0\0\0\xe9\xeb",8) ||
        memcmp(image+vep+0x3b9,"\x68\0\0\0\0\xc3",6)) fail("not recognized ASPack 2.12");
    for (unsigned i=0;i<58;++i)
        if (image[ep + 0x70e + i] > 24) fail("invalid distance shift");
    unsigned blocks=0;
    for (size_t pos=ep+0x57c;;pos+=8) {
        if (!contained(size,pos,8)) fail("unterminated block list");
        uint32_t rva=cli_readint32(image+pos), n=cli_readint32(image+pos+4);
        if (!rva) break;
        if (++blocks > 32 || !n || !contained(size,rva,n) ||
            (rva < ep+0x748 && rva+n > ep)) fail("invalid/overlapping packed block");
    }
    if (!blocks) fail("empty packed block list");
    if (!unaspack(image,size,sections,nsec,ep,base,-1,ASPACK_VER_212) || !np560_decoded)
        fail("incomplete decompression; no output created");
    int out = open(argv[2],O_WRONLY|O_CREAT|O_EXCL,0600);
    if (out < 0) fail("output exists or cannot be created");
    size_t done=0;
    while (done<size) {
        ssize_t n=write(out,image+done,size-done);
        if (n <= 0) fail("output write failed");
        done += n;
    }
    if (close(out)) fail("output close failed");
    printf("RVA dump only: bytes=%u base=%08x oep_rva=%08x blocks=%u; IAT not rebuilt\n",
           size,base,np560_oep,blocks);
    free(image); free(raw);
    return 0;
}
