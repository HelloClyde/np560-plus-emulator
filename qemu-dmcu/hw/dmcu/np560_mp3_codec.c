/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef NP560_MP3_CODEC_STANDALONE
#include "qemu/osdep.h"
#endif
#include "np560_mp3_codec.h"
#include <stdlib.h>
#include <string.h>

/* Pinned upstream CC0 implementation; scalar mode makes the initial HLE
 * reference independent of host SIMD dispatch. Not a host file player. */
#define MINIMP3_ONLY_MP3
#define MINIMP3_NO_SIMD
#define MINIMP3_IMPLEMENTATION
#include "minimp3/minimp3.h"

struct NP560MP3Codec {
    mp3dec_t decoder;
    NP560MP3NoPCMInfo no_pcm;
};

NP560MP3NoPCMInfo np560_mp3_codec_no_pcm_info(const NP560MP3Codec *codec)
{
    return codec ? codec->no_pcm : (NP560MP3NoPCMInfo){0};
}

static void classify_no_pcm(NP560MP3Codec *codec, const uint8_t *input,
                            unsigned bytes, unsigned header)
{
    mp3dec_scratch_t scratch = {0};
    bs_t bits;
    int required;
    /* The validated caller supplies exactly one complete frame. Upstream
     * resets history when the preceding header is absent/incompatible. */
    unsigned available = codec->decoder.header[0] == 0xff &&
                         hdr_compare(codec->decoder.header, input) ?
                         codec->decoder.reserv : 0;
    bs_init(&bits, input + 4, bytes - 4);
    if (header == 6) {
        get_bits(&bits, 16);
    }
    required = L3_read_side_info(&bits, scratch.gr_info, input);
    codec->no_pcm.available_history = available;
    if (required < 0 || bits.pos > bits.limit) {
        codec->no_pcm.reason = 1;
    } else {
        codec->no_pcm.required_history = required;
        codec->no_pcm.reason = available < required ? 2 : 3;
    }
}

NP560MP3Codec *np560_mp3_codec_new(void)
{
    return calloc(1, sizeof(NP560MP3Codec));
}

void np560_mp3_codec_free(NP560MP3Codec *codec)
{
    free(codec);
}

void np560_mp3_codec_reset(NP560MP3Codec *codec)
{
    if (codec) {
        memset(codec, 0, sizeof(*codec));
        mp3dec_init(&codec->decoder);
    }
}

static uint16_t crc_byte(uint16_t crc, uint8_t byte)
{
    unsigned i;
    for (i = 0; i < 8; i++) {
        unsigned carry = ((crc >> 15) ^ (byte >> 7)) & 1;
        crc = (uint16_t)(crc << 1) ^ (carry ? 0x8005 : 0);
        byte <<= 1;
    }
    return crc;
}

/* The upstream framing API intentionally refuses truncated packets. For an
 * explicitly terminal packet, use the very same Layer III kernel with its
 * bit limit set to bytes actually received. This is not zero-padding a frame
 * to its header length: unavailable ancillary bytes never enter maindata or
 * the reservoir. Guard storage is initialized for bounded Huffman lookahead;
 * only the validated part2_3 bit ranges are decoded. */
static NP560MP3Status decode_final_packet(mp3dec_t *candidate,
                                          const uint8_t *input, unsigned bytes,
                                          unsigned header, unsigned side,
                                          unsigned channels, unsigned version,
                                          int16_t *pcm)
{
    mp3dec_scratch_t scratch = {0};
    bs_t lengths, bits;
    unsigned part_bits = 0, granules = version == 3 ? 2 : 1;
    unsigned fields = granules * channels, i;
    int main_data_begin;

    /* A changed version/rate/layer cannot borrow the previous stream's
     * reservoir. Match the upstream complete-frame reset decision. */
    if (candidate->header[0] != 0xff ||
        !hdr_compare(candidate->header, input)) {
        memset(candidate, 0, sizeof(*candidate));
    }
    bs_init(&lengths, input + header, side);
    main_data_begin = get_bits(&lengths, version == 3 ? 9 : 8);
    lengths.pos = version == 3 ? 9 + (channels == 1 ? 5 : 3) + 4 * channels :
                                8 + channels;
    for (i = 0; i < fields; i++) {
        part_bits += get_bits(&lengths, 12);
        lengths.pos += (version == 3 ? 59 : 63) - 12;
    }
    if (part_bits > (bytes - header - side + main_data_begin) * 8) {
        return NP560_MP3_SHORT;
    }
    bs_init(&bits, input + 4, bytes - 4);
    if (header == 6) {
        get_bits(&bits, 16);
    }
    if (L3_read_side_info(&bits, scratch.gr_info, input) != main_data_begin ||
        bits.pos > bits.limit) {
        return NP560_MP3_DECODE_ERROR;
    }
    if (candidate->reserv < main_data_begin) {
        return NP560_MP3_MISSING_HISTORY;
    }
    memcpy(candidate->header, input, 4);
    if (!L3_restore_reservoir(candidate, &bits, &scratch, main_data_begin)) {
        return NP560_MP3_MISSING_HISTORY;
    }
    for (i = 0; i < granules; i++) {
        memset(scratch.grbuf, 0, sizeof(scratch.grbuf));
        L3_decode(candidate, &scratch, scratch.gr_info + i * channels, channels);
        if (scratch.bs.pos > scratch.bs.limit) {
            return NP560_MP3_DECODE_ERROR;
        }
        mp3d_synth_granule(candidate->qmf_state, scratch.grbuf[0], 18,
                          channels, pcm + i * 576 * channels, scratch.syn[0]);
    }
    L3_save_reservoir(candidate, &scratch);
    return NP560_MP3_OK;
}

static NP560MP3Status codec_decode(NP560MP3Codec *codec,
                                   const uint8_t *input, size_t length,
                                   NP560MP3Frame *frame, int final)
{
    static const unsigned rates[] = {44100, 48000, 32000};
    static const unsigned bitrates[2][15] = {
        {0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320},
        {0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160},
    };
    unsigned version, layer, br, rate, hz, bytes, channels, side, header;
    int samples;
    mp3dec_frame_info_t info = {0};
    mp3dec_t candidate;
    int16_t pcm[MINIMP3_MAX_SAMPLES_PER_FRAME] = {0};

    if (!frame) {
        return NP560_MP3_BAD_HEADER;
    }
    memset(frame, 0, sizeof(*frame));
    if (!codec || (!input && length)) {
        return NP560_MP3_BAD_HEADER;
    }
    codec->no_pcm = (NP560MP3NoPCMInfo){0};
    if (length < 4) {
        return NP560_MP3_SHORT;
    }
    version = (input[1] >> 3) & 3;
    layer = (input[1] >> 1) & 3;
    br = input[2] >> 4;
    rate = (input[2] >> 2) & 3;
    if (input[0] != 0xff || (input[1] & 0xe0) != 0xe0 ||
        version == 1 || !layer || br == 15 || rate == 3 ||
        (input[3] & 3) == 2) {
        return NP560_MP3_BAD_HEADER;
    }
    /* Free-format framing needs a separately evidenced original contract;
     * don't let the library skip bytes or scan the caller's entire file. */
    if (layer != 1 || br == 0) {
        return NP560_MP3_UNSUPPORTED;
    }
    hz = rates[rate] >> (version == 3 ? 0 : version == 2 ? 1 : 2);
    bytes = (version == 3 ? 144000 : 72000) * bitrates[version != 3][br] /
            hz + ((input[2] >> 1) & 1);
    channels = (input[3] >> 6) == 3 ? 1 : 2;
    side = version == 3 ? (channels == 1 ? 17 : 32) :
                         (channels == 1 ? 9 : 17);
    header = (input[1] & 1) ? 4 : 6;
    if (bytes < header + side) {
        return NP560_MP3_BAD_HEADER;
    }
    if (length < header + side || (!final && length < bytes)) {
        return NP560_MP3_SHORT;
    }
    if (length > bytes) {
        /* This API owns one already-framed packet, not a byte stream.
         * Reject surplus bytes before committing synthesis/reservoir state.
         * Ordinary HLE previously rejected the partial consumption later
         * as DECODE_ERROR; preserve that status without the state mutation.
         */
        return final ? NP560_MP3_BAD_HEADER : NP560_MP3_DECODE_ERROR;
    }
    if (header == 6) {
        uint16_t crc = crc_byte(crc_byte(0xffff, input[2]), input[3]);
        unsigned i;
        for (i = 0; i < side; i++) {
            crc = crc_byte(crc, input[header + i]);
        }
        if (crc != ((unsigned)input[4] << 8 | input[5])) {
            return NP560_MP3_BAD_CRC;
        }
    }
    /* One complete, already-framed packet only. Check the library's actual
     * consumption before committing history. Short/error prechecks leave
     * state unchanged and cannot manufacture PCM or a ready indication. */
    candidate = codec->decoder;
    if (final) {
        NP560MP3Status status;

        bytes = length;
        status = decode_final_packet(&candidate, input, bytes, header, side,
                                     channels, version, pcm);
        if (status != NP560_MP3_OK) {
            return status;
        }
        samples = version == 3 ? 1152 : 576;
    } else {
        samples = mp3dec_decode_frame(&candidate, input, bytes, pcm, &info);
        if (info.frame_offset != 0 || info.frame_bytes != (int)bytes ||
            info.hz != (int)hz || info.channels != (int)channels ||
            info.layer != 3 ||
            (samples != 0 && samples != (version == 3 ? 1152 : 576))) {
            return NP560_MP3_DECODE_ERROR;
        }
    }
    if (!final && samples == 0) {
        classify_no_pcm(codec, input, bytes, header);
    }
    codec->decoder = candidate;
    frame->consumed = bytes;
    frame->hz = hz;
    frame->channels = channels;
    if (samples == 0) {
        /* Preserve the existing return/consumption contract. The separate
         * read-only explanation must not synthesize silence or turn an
         * invalid sideinfo result into successful decoder priming. */
        return NP560_MP3_NO_PCM;
    }
    frame->samples_per_channel = samples;
    memcpy(frame->pcm, pcm, samples * channels * sizeof(pcm[0]));
    return NP560_MP3_OK;
}

NP560MP3Status np560_mp3_codec_decode(NP560MP3Codec *codec,
                                     const uint8_t *input, size_t length,
                                     NP560MP3Frame *frame)
{
    return codec_decode(codec, input, length, frame, 0);
}

NP560MP3Status np560_mp3_codec_decode_final(NP560MP3Codec *codec,
                                           const uint8_t *input, size_t length,
                                           NP560MP3Frame *frame)
{
    return codec_decode(codec, input, length, frame, 1);
}
