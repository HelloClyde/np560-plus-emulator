/* SPDX-License-Identifier: GPL-2.0-only
 * Minimal ClamAV compatibility layer: emit an RVA image, not a runnable PE.
 */
#ifndef NP560_ASPACK_COMPAT_H
#define NP560_ASPACK_COMPAT_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NP560_ASPACK_LIMIT (32u * 1024u * 1024u)
struct cli_exe_section { uint32_t rva, vsz, raw, rsz; };
typedef enum { ASPACK_VER_NONE, ASPACK_VER_212, ASPACK_VER_OTHER,
               ASPACK_VER_242 } aspack_version_t;
static int np560_decoded;
static uint32_t np560_oep;
static int np560_contains(const void *base, size_t size, const void *p, size_t n)
{
    uintptr_t a = (uintptr_t)base, b = (uintptr_t)p;
    return b >= a && b - a <= size && n <= size - (b - a);
}
#define CLI_ISCONTAINED(b,s,p,n) np560_contains(b,s,p,n)
#define cli_dbgmsg(...) fprintf(stderr, __VA_ARGS__)
#define CLI_ROL(v,n) ((v) = ((uint32_t)(v) << (n)) | ((uint32_t)(v) >> (32-(n))))
static uint32_t cli_readint32(const void *p)
{
    const uint8_t *b = p;
    return b[0] | (uint32_t)b[1]<<8 | (uint32_t)b[2]<<16 | (uint32_t)b[3]<<24;
}
static void cli_writeint32(void *p, uint32_t v)
{
    uint8_t *b = p;
    for (int i = 0; i < 4; ++i) b[i] = v >> (8*i);
}
static void *cli_max_malloc(size_t n)
{ return n <= NP560_ASPACK_LIMIT ? malloc(n) : NULL; }
static void *cli_max_calloc(size_t n, size_t s)
{ return s && n <= NP560_ASPACK_LIMIT/s ? calloc(n,s) : NULL; }
/* Never emit ClamAV's partial/raw fallback as a successful result. */
static int cli_writen(int fd, const void *p, size_t n)
{ (void)fd; (void)p; (void)n; return -1; }
static int cli_rebuildpe(char *image, struct cli_exe_section *s, unsigned count,
                        uint32_t base, uint32_t ep, unsigned a, unsigned b, int fd)
{
    (void)image; (void)s; (void)count; (void)base; (void)a; (void)b; (void)fd;
    np560_oep = ep;
    np560_decoded = 1;
    return 1; /* All blocks decoded. Caller saves a clearly named RVA dump. */
}
#endif
