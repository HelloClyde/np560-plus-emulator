/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_DMCU_NP560_NPE_CODEC_H
#define HW_DMCU_NP560_NPE_CODEC_H

#include "qapi/error.h"

typedef struct NP560NPECodec NP560NPECodec;

NP560NPECodec *np560_npe_codec_new(const char *socket_path, Error **errp);
void np560_npe_codec_free(NP560NPECodec *codec);
bool np560_npe_codec_init(NP560NPECodec *codec, unsigned mode,
                          uint16_t *frame_bits, Error **errp);
bool np560_npe_codec_decode(NP560NPECodec *codec, const uint8_t *frame,
                            unsigned frame_bytes, uint8_t pcm[320],
                            Error **errp);
bool np560_npe_codec_reset(NP560NPECodec *codec, Error **errp);

#endif
