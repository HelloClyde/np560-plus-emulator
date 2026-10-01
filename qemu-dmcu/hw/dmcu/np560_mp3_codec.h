/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_DMCU_NP560_MP3_CODEC_H
#define HW_DMCU_NP560_MP3_CODEC_H

#include <stddef.h>
#include <stdint.h>

/* Codec kernel for the explicitly enabled ROM 01/02 HLE service.
 * This layer has no guest memory, file, clock, DAC or UI access. The service
 * adapter owns those contracts; it must NOT publish ready for an error.
 * Used by the explicitly enabled ROM service adapter and standalone tests.
 */
typedef struct NP560MP3Codec NP560MP3Codec;

/* Read-only explanation of the last complete-frame NO_PCM result. This
 * does not change its return status, consumed input or reservoir commit. */
typedef struct NP560MP3NoPCMInfo {
    uint32_t reason; /* 0 none, 1 invalid sideinfo, 2 missing history, 3 unknown */
    uint32_t available_history, required_history;
} NP560MP3NoPCMInfo;

NP560MP3NoPCMInfo np560_mp3_codec_no_pcm_info(const NP560MP3Codec *codec);

typedef enum NP560MP3Status {
    NP560_MP3_OK,
    NP560_MP3_SHORT,
    NP560_MP3_BAD_HEADER,
    NP560_MP3_UNSUPPORTED,
    NP560_MP3_BAD_CRC,
    NP560_MP3_NO_PCM,       /* Consumed frame, no valid PCM: history/error. */
    NP560_MP3_DECODE_ERROR,
    NP560_MP3_MISSING_HISTORY, /* Final packet: required reservoir is absent. */
} NP560MP3Status;

typedef struct NP560MP3Frame {
    uint32_t consumed;
    uint32_t hz;
    uint32_t channels;
    uint32_t samples_per_channel;
    int16_t pcm[1152 * 2]; /* Interleaved, no trimming/gain/resampling. */
} NP560MP3Frame;

NP560MP3Codec *np560_mp3_codec_new(void);
void np560_mp3_codec_free(NP560MP3Codec *codec);
void np560_mp3_codec_reset(NP560MP3Codec *codec);
/* Exactly one framed packet. Surplus bytes are a DECODE_ERROR, not a
 * request to consume only the first frame; history stays unchanged and the
 * output frame is empty on rejection. Stream splitting belongs to the caller. */
NP560MP3Status np560_mp3_codec_decode(NP560MP3Codec *codec,
                                     const uint8_t *input, size_t length,
                                     NP560MP3Frame *frame);
/* Explicit end-of-input only: one final packet, at most its declared size.
 * Missing ancillary bytes are permitted only when the complete sideinfo and
 * all declared audio bits exist in input plus the real decoder reservoir.
 * No compressed bytes are invented. Success consumes the actual input size;
 * every failure leaves both decoder state and output frame unchanged/empty.
 * A caller must not use this to decode an ordinary temporarily short packet. */
NP560MP3Status np560_mp3_codec_decode_final(NP560MP3Codec *codec,
                                           const uint8_t *input, size_t length,
                                           NP560MP3Frame *frame);
#endif
