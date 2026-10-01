/* Diagnostic only: pinned minimp3 without the NP560 wrapper. */
#include <stdio.h>
#include <stdlib.h>
#define MINIMP3_ONLY_MP3
#define MINIMP3_IMPLEMENTATION
#include "minimp3/minimp3.h"

int main(int argc, char **argv)
{
    mp3dec_t decoder = {0};
    unsigned char *input;
    mp3d_sample_t pcm[MINIMP3_MAX_SAMPLES_PER_FRAME];
    long size;
    int offset = 0, frames = 0;
    FILE *in, *out;
    if (argc != 3 || !(in = fopen(argv[1], "rb"))) return 2;
    if (fseek(in, 0, SEEK_END) || (size = ftell(in)) <= 0 || size > 1048576 ||
        fseek(in, 0, SEEK_SET)) { fclose(in); return 2; }
    input = malloc(size);
    if (!input || fread(input, 1, size, in) != (size_t)size) { fclose(in); free(input); return 2; }
    fclose(in);
    /* Exclusive output prevents a comparison run from replacing evidence. */
    out = fopen(argv[2], "wbx");
    if (!out) { free(input); return 2; }
    mp3dec_init(&decoder);
    while (offset < size) {
        mp3dec_frame_info_t info = {0};
        int samples = mp3dec_decode_frame(&decoder, input+offset, size-offset, pcm, &info);
        if (info.frame_bytes <= 0) break;
        offset += info.frame_bytes;
        if (samples) {
            size_t count = samples * info.channels;
            if (fwrite(pcm, sizeof(*pcm), count, out) != count) {
                fclose(out); free(input); return 2;
            }
            frames++;
        }
    }
    if (fclose(out)) { free(input); return 2; }
    free(input);
    printf("frames=%d consumed=%d bytes=%ld\n", frames, offset, size);
    return offset == size ? 0 : 1;
}
