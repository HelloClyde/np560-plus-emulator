/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Optional local transport to an interpreted, user-supplied codec image.
 * This file contains no proprietary decoder and never runs the DLL natively.
 * The resident ROM service contract is implemented separately. */
#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "np560_npe_codec.h"

#include <sys/un.h>

#define CODEC_PCM_SAMPLES 160
#define CODEC_PCM_BYTES (CODEC_PCM_SAMPLES * 2)
#define CODEC_MAX_FRAME_BYTES 36
#define CODEC_MAX_ERROR_BYTES 240

struct NP560NPECodec {
    int fd;
    uint16_t frame_bits;
};

static bool codec_transfer(NP560NPECodec *codec, void *bytes, size_t length,
                           bool write_side, Error **errp)
{
    uint8_t *cursor = bytes;

    while (length) {
        ssize_t done = write_side ? send(codec->fd, cursor, length, MSG_NOSIGNAL) :
                                    recv(codec->fd, cursor, length, 0);

        if (done > 0) {
            cursor += done;
            length -= done;
            continue;
        }
        if (done < 0 && errno == EINTR) {
            continue;
        }
        error_setg_errno(errp, done < 0 ? errno : EPIPE,
                         "NPE codec transport %s failed",
                         write_side ? "write" : "read");
        return false;
    }
    return true;
}

static bool codec_reply(NP560NPECodec *codec, uint8_t expected,
                        Error **errp)
{
    uint8_t tag, count_bytes[2];
    uint16_t count;
    char message[CODEC_MAX_ERROR_BYTES + 1];

    if (!codec_transfer(codec, &tag, 1, false, errp)) {
        return false;
    }
    if (tag == expected) {
        return true;
    }
    if (tag != 'E') {
        error_setg(errp, "NPE codec returned unexpected tag 0x%02x", tag);
        return false;
    }
    if (!codec_transfer(codec, count_bytes, 2, false, errp)) {
        return false;
    }
    count = lduw_le_p(count_bytes);
    if (count > CODEC_MAX_ERROR_BYTES) {
        error_setg(errp, "NPE codec error reply is oversized");
        return false;
    }
    if (!codec_transfer(codec, message, count, false, errp)) {
        return false;
    }
    message[count] = 0;
    error_setg(errp, "NPE codec rejected request: %s", message);
    return false;
}

NP560NPECodec *np560_npe_codec_new(const char *socket_path, Error **errp)
{
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    struct timeval timeout = {.tv_sec = 3};
    NP560NPECodec *codec;
    int fd;

    if (!socket_path || !*socket_path ||
        strlen(socket_path) >= sizeof(address.sun_path)) {
        error_setg(errp, "NPE codec Unix-socket path is empty or too long");
        return NULL;
    }
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        error_setg_errno(errp, errno, "cannot create NPE codec socket");
        return NULL;
    }
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0 ||
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) < 0) {
        error_setg_errno(errp, errno, "cannot set NPE codec socket timeout");
        close(fd);
        return NULL;
    }
    g_strlcpy(address.sun_path, socket_path, sizeof(address.sun_path));
    if (connect(fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
        error_setg_errno(errp, errno, "cannot connect to NPE codec socket %s",
                         socket_path);
        close(fd);
        return NULL;
    }
    codec = g_new0(NP560NPECodec, 1);
    codec->fd = fd;
    return codec;
}

void np560_npe_codec_free(NP560NPECodec *codec)
{
    if (codec) {
        close(codec->fd);
        g_free(codec);
    }
}

bool np560_npe_codec_init(NP560NPECodec *codec, unsigned mode,
                          uint16_t *frame_bits, Error **errp)
{
    uint8_t request[2] = {'I', mode};
    uint8_t reply[2];
    uint16_t expected;

    if (!codec || !frame_bits || mode < 1 || mode > 10) {
        error_setg(errp, "NPE codec mode must be 1..10");
        return false;
    }
    codec->frame_bits = 0;
    if (!codec_transfer(codec, request, sizeof(request), true, errp) ||
        !codec_reply(codec, 'K', errp) ||
        !codec_transfer(codec, reply, sizeof(reply), false, errp)) {
        return false;
    }
    expected = (mode * 3 + 6) * 8;
    if (lduw_le_p(reply) != expected) {
        error_setg(errp, "NPE codec frame bits mismatch: got %u, expected %u",
                   lduw_le_p(reply), expected);
        return false;
    }
    codec->frame_bits = expected;
    *frame_bits = expected;
    return true;
}

bool np560_npe_codec_decode(NP560NPECodec *codec, const uint8_t *frame,
                            unsigned frame_bytes, uint8_t pcm[CODEC_PCM_BYTES],
                            Error **errp)
{
    uint8_t request[3] = {'D'};
    uint8_t sample_bytes[2];

    if (!codec || !frame || !pcm || !codec->frame_bits ||
        frame_bytes < 1 || frame_bytes > CODEC_MAX_FRAME_BYTES ||
        frame_bytes * 8 != codec->frame_bits) {
        error_setg(errp, "NPE codec frame does not match initialized mode");
        return false;
    }
    stw_le_p(request + 1, frame_bytes);
    if (!codec_transfer(codec, request, sizeof(request), true, errp) ||
        !codec_transfer(codec, (void *)frame, frame_bytes, true, errp) ||
        !codec_reply(codec, 'P', errp) ||
        !codec_transfer(codec, sample_bytes, sizeof(sample_bytes), false, errp)) {
        return false;
    }
    if (lduw_le_p(sample_bytes) != CODEC_PCM_SAMPLES) {
        error_setg(errp, "NPE codec returned %u samples, expected %u",
                   lduw_le_p(sample_bytes), CODEC_PCM_SAMPLES);
        return false;
    }
    return codec_transfer(codec, pcm, CODEC_PCM_BYTES, false, errp);
}

bool np560_npe_codec_reset(NP560NPECodec *codec, Error **errp)
{
    uint8_t request = 'R';

    if (!codec) {
        error_setg(errp, "NPE codec socket is not connected");
        return false;
    }
    codec->frame_bits = 0;
    return codec_transfer(codec, &request, 1, true, errp) &&
           codec_reply(codec, 'K', errp);
}
