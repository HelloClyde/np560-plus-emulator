/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Experimental, opt-in reconstruction of the first NPE resident-audio
 * boundary. Only addresses with verified strict-ROM holes are intercepted.
 * The later AD92 output service is limited to the observed NPE PCM transfer;
 * reaching it alone does not prove audible game sound. */
#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "exec/address-spaces.h"
#include "cpu.h"
#include "np560_npe_codec.h"
#include "np560_npe_hle.h"

enum {
    NPE_ACD8 = 0x02acd8,
    NPE_B6DE = 0x01b6de,
    NPE_B7AA = 0x01b7aa,
    NPE_B816 = 0x01b816,
    NPE_B84E = 0x01b84e,
    NPE_AD92 = 0x02ad92,
    NPE_STREAM_BASE = 0x8800,
    NPE_PCM_BYTES = 320,
    NPE_TRANSFER_MAX = 0x800,
    NPE_INIT_TRACE_SLOTS = 16,
};

typedef struct NP560NPEInitTrace {
    uint32_t caller;
    uint16_t sp, fp;
    uint16_t regs[4];
    /* Include the caller's frame header and first arguments above R11. */
    uint16_t stack[28];
    struct {
        uint16_t fp, parent_fp, return_cs, return_pc;
    } frames[20];
    uint8_t frame_count;
    uint8_t service;
} NP560NPEInitTrace;

struct NP560NPEHLE {
    DMCUCPU *cpu;
    NP560NPECodec *codec;
    bool active, prepared;
    uint16_t cursor, frame_bits;
    unsigned format, frame_bytes, bit_offset;
    uint64_t playback_frames;
    uint8_t previous_raw_tail;
    bool trace_raw_frames;
    uint64_t calls[6], decoded_frames, decoded_nonzero_frames;
    uint64_t copy_nonzero_transfers, failed_calls;
    unsigned last_decode_nonzero, last_copy_nonzero;
    uint32_t last_pc;
    char last_error[192];
    uint32_t init_trace_count;
    NP560NPEInitTrace init_trace[NPE_INIT_TRACE_SLOTS];
};

static uint16_t internal_word(NP560NPEHLE *hle, uint16_t offset)
{
    return hle->cpu->internal_data[offset] |
           (hle->cpu->internal_data[(offset + 1) & 0xffff] << 8);
}

static uint16_t stack_arg(NP560NPEHLE *hle, CPUDMCUState *env,
                          unsigned index)
{
    uint16_t offset = (env->gpr[DMCU_SP] + 4 + index * 2) & 0xffff;

    return internal_word(hle, offset);
}

static void trace_init_call(NP560NPEHLE *hle, CPUDMCUState *env,
                            unsigned service)
{
    NP560NPEInitTrace *trace = &hle->init_trace[
        hle->init_trace_count++ % NPE_INIT_TRACE_SLOTS];
    unsigned i;

    trace->service = service;
    trace->sp = env->gpr[DMCU_SP] & 0xffff;
    trace->fp = env->gpr[DMCU_FP] & 0xffff;
    for (i = 0; i < ARRAY_SIZE(trace->regs); i++) {
        trace->regs[i] = env->gpr[i] & 0xffff;
    }
    for (i = 0; i < ARRAY_SIZE(trace->stack); i++) {
        trace->stack[i] = internal_word(hle, (trace->sp + 2 * i) & 0xffff);
    }
    /* SCALL leaves the return CS word above the return PC word. */
    trace->caller = ((trace->stack[0] & 0xff) << 16) | trace->stack[1];
    trace->frame_count = 0;
    for (i = 0; i < ARRAY_SIZE(trace->frames); i++) {
        uint16_t fp = i ? trace->frames[i - 1].parent_fp : trace->fp;
        uint16_t return_cs, return_pc;

        if ((fp & 1) || fp > 0xfff9 ||
            (i && fp <= trace->frames[i - 1].fp)) {
            break;
        }
        return_cs = internal_word(hle, fp + 2);
        return_pc = internal_word(hle, fp + 4);
        if (return_cs > 0xff || (return_pc & 1)) {
            break;
        }
        trace->frames[i].fp = fp;
        trace->frames[i].parent_fp = internal_word(hle, fp);
        trace->frames[i].return_cs = return_cs;
        trace->frames[i].return_pc = return_pc;
        trace->frame_count++;
    }
}

static bool read_guest(NP560NPEHLE *hle, uint32_t address,
                       uint8_t *buffer, size_t size)
{
    AddressSpace *as = cpu_get_address_space(CPU(hle->cpu), DMCU_AS_DATA);

    return address_space_read(as, address, MEMTXATTRS_UNSPECIFIED,
                              buffer, size) == MEMTX_OK;
}

static bool write_guest(NP560NPEHLE *hle, uint32_t address,
                        const uint8_t *buffer, size_t size)
{
    AddressSpace *as = cpu_get_address_space(CPU(hle->cpu), DMCU_AS_DATA);

    return address_space_write(as, address, MEMTXATTRS_UNSPECIFIED,
                               buffer, size) == MEMTX_OK;
}

static void service_error(NP560NPEHLE *hle, uint32_t pc, const char *message)
{
    hle->failed_calls++;
    hle->last_pc = pc;
    g_strlcpy(hle->last_error, message, sizeof(hle->last_error));
}

static bool codec_ok(NP560NPEHLE *hle, uint32_t pc, bool success,
                     Error *error)
{
    if (!success) {
        service_error(hle, pc,
                      error ? error_get_pretty(error) : "codec transport failed");
    }
    error_free(error);
    return success;
}

static bool hole_is_strict(NP560NPEHLE *hle, uint32_t pc)
{
    AddressSpace *code = cpu_get_address_space(CPU(hle->cpu), DMCU_AS_CODE);
    uint8_t word[2];

    return address_space_read(code, pc, MEMTXATTRS_UNSPECIFIED,
                              word, sizeof(word)) == MEMTX_OK &&
           lduw_le_p(word) == 0x0f00;
}

NP560NPEHLE *np560_npe_hle_new(DMCUCPU *cpu, const char *codec_socket,
                                Error **errp)
{
    static const uint32_t holes[] = {NPE_ACD8, NPE_B6DE, NPE_B7AA,
                                     NPE_B816, NPE_B84E, NPE_AD92};
    NP560NPEHLE *hle = g_new0(NP560NPEHLE, 1);
    unsigned i;

    hle->cpu = cpu;
    hle->trace_raw_frames = g_getenv("NP560_NPE_TRACE_RAW") != NULL;
    for (i = 0; i < ARRAY_SIZE(holes); i++) {
        if (!hole_is_strict(hle, holes[i])) {
            error_setg(errp, "NPE HLE requires strict ROM hole %02x:%04x",
                       holes[i] >> 16, holes[i] & 0xffff);
            g_free(hle);
            return NULL;
        }
    }
    hle->codec = np560_npe_codec_new(codec_socket, errp);
    if (!hle->codec) {
        g_free(hle);
        return NULL;
    }
    return hle;
}

void np560_npe_hle_free(NP560NPEHLE *hle)
{
    if (hle) {
        np560_npe_codec_free(hle->codec);
        g_free(hle);
    }
}

void np560_npe_hle_reset(void *opaque)
{
    NP560NPEHLE *hle = opaque;
    Error *error = NULL;

    if (!hle) {
        return;
    }
    hle->active = hle->prepared = false;
    hle->cursor = hle->frame_bits = 0;
    hle->format = hle->frame_bytes = hle->bit_offset = 0;
    hle->playback_frames = 0;
    hle->previous_raw_tail = 0;
    hle->last_decode_nonzero = hle->last_copy_nonzero = 0;
    hle->init_trace_count = 0;
    if (!np560_npe_codec_reset(hle->codec, &error)) {
        service_error(hle, 0, error_get_pretty(error));
    }
    error_free(error);
}

static bool stream_init(NP560NPEHLE *hle, CPUDMCUState *env)
{
    uint8_t format_word[2], header[4];
    unsigned format, mode;
    Error *error = NULL;

    if (stack_arg(hle, env, 0) ||
        stack_arg(hle, env, 1) != NPE_STREAM_BASE ||
        stack_arg(hle, env, 2) != 0 ||
        !read_guest(hle, 0x51282a, format_word, 2) ||
        !read_guest(hle, NPE_STREAM_BASE, header, sizeof(header))) {
        service_error(hle, NPE_B6DE, "invalid stream-initialization arguments");
        return false;
    }
    format = lduw_le_p(format_word);
    if (format < 9 || format > 18 || header[0] != 0x20 ||
        header[1] != format) {
        service_error(hle, NPE_B6DE, "unsupported or inconsistent NPE format");
        return false;
    }
    mode = format - 8;
    bool success = np560_npe_codec_init(hle->codec, mode,
                                        &hle->frame_bits, &error);

    if (!codec_ok(hle, NPE_B6DE, success, error)) {
        return false;
    }
    hle->active = true;
    hle->prepared = false;
    hle->format = format;
    hle->frame_bytes = hle->frame_bits / 8;
    hle->cursor = 4; /* documented four-byte NPE section header */
    hle->bit_offset = 0;
    hle->playback_frames = 0;
    hle->previous_raw_tail = 0;
    env->gpr[0] = 0;
    return true;
}

static bool stream_position(NP560NPEHLE *hle, CPUDMCUState *env)
{
    uint16_t high = stack_arg(hle, env, 0), low = stack_arg(hle, env, 1);
    uint8_t remainder[2];

    if (!hle->active ||
        (high && (high != 0x51 || low != 0x2afc)) ||
        low > 0xfffe || (low & 1) || hle->cursor >= 0x7800) {
        service_error(hle, NPE_B816, "invalid stream-position request");
        return false;
    }
    /* The PRG's refill copies whole words. Report an odd byte position as
     * an aligned pointer plus eight residual bits so its word move retains
     * the byte at the 1 KiB refill boundary. The total bit position is
     * unchanged: (cursor & ~1) * 8 + (cursor & 1) * 8. */
    stw_le_p(remainder, hle->bit_offset + ((hle->cursor & 1) * 8));
    if (!write_guest(hle, ((uint32_t)high << 16) | low,
                     remainder, sizeof(remainder))) {
        service_error(hle, NPE_B816, "cannot write bit remainder");
        return false;
    }
    env->gpr[0] = 0;
    env->gpr[1] = NPE_STREAM_BASE + (hle->cursor & ~1u);
    return true;
}

static bool stream_decode(NP560NPEHLE *hle, CPUDMCUState *env)
{
    uint16_t output_high = stack_arg(hle, env, 0);
    uint16_t output_low = stack_arg(hle, env, 1);
    uint16_t meta_high = stack_arg(hle, env, 2);
    uint16_t meta_low = stack_arg(hle, env, 3);
    uint8_t frame[36], raw_frame[36], pcm[NPE_PCM_BYTES];
    Error *error = NULL;
    unsigned i;

    if (!hle->active || output_high || output_low != 0x2984 ||
        meta_high > 0x1ff || meta_low & 1 ||
        hle->bit_offset || hle->cursor + hle->frame_bytes > 0x400) {
        service_error(hle, NPE_B7AA, "unsupported frame cursor or output pointer");
        return false;
    }
    /* The PRG's initial decodes (including the first real playback frame)
     * read a raw window. Its refill/rebase path then presents raw NPE bytes
     * at 8800, while the missing bit reader must preserve the original
     * 16-bit word-lane view across odd-sized frames. */
    for (i = 0; i < hle->frame_bytes; i++) {
        uint32_t offset = hle->cursor + i;
        uint32_t source = !hle->prepared ? ((offset - 4) ^ 1u) + 4 : offset;

        if (!read_guest(hle, NPE_STREAM_BASE + source, raw_frame + i, 1)) {
            service_error(hle, NPE_B7AA, "cannot read compressed frame");
            return false;
        }
    }
    if (!hle->prepared) {
        memcpy(frame, raw_frame, hle->frame_bytes);
        if (hle->cursor == 4 && (hle->frame_bytes & 1)) {
            /* Byte n-1 of the first raw frame becomes the first byte of
             * the next globally word-swapped 21-byte frame. */
            if (!read_guest(hle, NPE_STREAM_BASE + hle->cursor +
                            hle->frame_bytes - 1, &hle->previous_raw_tail, 1)) {
                service_error(hle, NPE_B7AA, "cannot read initial raw tail");
                return false;
            }
        }
    } else if ((hle->playback_frames * hle->frame_bytes) & 1) {
        frame[0] = hle->previous_raw_tail;
        for (i = 1; i < hle->frame_bytes; i += 2) {
            frame[i] = raw_frame[i + 1];
            frame[i + 1] = raw_frame[i];
        }
    } else {
        for (i = 0; i + 1 < hle->frame_bytes; i += 2) {
            frame[i] = raw_frame[i + 1];
            frame[i + 1] = raw_frame[i];
        }
        if (hle->frame_bytes & 1) {
            if (!read_guest(hle, NPE_STREAM_BASE + hle->cursor + hle->frame_bytes,
                            frame + hle->frame_bytes - 1, 1)) {
                service_error(hle, NPE_B7AA, "cannot read next compressed byte");
                return false;
            }
            hle->previous_raw_tail = raw_frame[hle->frame_bytes - 1];
        }
    }
    if (hle->trace_raw_frames && hle->prepared && hle->playback_frames < 8) {
        g_autofree char *raw_hex = g_malloc(hle->frame_bytes * 2 + 1);
        g_autofree char *normalized_hex = g_malloc(hle->frame_bytes * 2 + 1);

        for (i = 0; i < hle->frame_bytes; i++) {
            sprintf(raw_hex + i * 2, "%02x", raw_frame[i]);
            sprintf(normalized_hex + i * 2, "%02x", frame[i]);
        }
        fprintf(stderr, "NP560_NPE_FRAME index=%" PRIu64 " cursor=%04x carry=%02x "
                "raw=%s normalized=%s\n", hle->playback_frames,
                hle->cursor, hle->previous_raw_tail, raw_hex, normalized_hex);
    }
    bool success = np560_npe_codec_decode(hle->codec, frame,
                                          hle->frame_bytes, pcm, &error);

    if (!codec_ok(hle, NPE_B7AA, success, error) ||
        !write_guest(hle, output_low, pcm, sizeof(pcm))) {
        if (!hle->last_error[0]) {
            service_error(hle, NPE_B7AA, "cannot write decoded PCM");
        }
        return false;
    }
    hle->cursor += hle->frame_bytes;
    hle->playback_frames++;
    hle->decoded_frames++;
    hle->last_decode_nonzero = 0;
    for (i = 0; i < NPE_PCM_BYTES; i += 2) {
        hle->last_decode_nonzero += lduw_le_p(pcm + i) != 0;
    }
    hle->decoded_nonzero_frames += hle->last_decode_nonzero != 0;
    env->gpr[0] = 160;
    return true;
}

static bool stream_rebase(NP560NPEHLE *hle, CPUDMCUState *env)
{
    uint16_t bit_offset = stack_arg(hle, env, 2);
    if (!hle->active || stack_arg(hle, env, 0) ||
        stack_arg(hle, env, 1) != NPE_STREAM_BASE || bit_offset > 15 ||
        (bit_offset & 7)) {
        service_error(hle, NPE_B84E, "unsupported stream rebase");
        return false;
    }
    /* Rebase changes the bit reader's address, not the predictor state.
     * B6DE already supplies the separately observed decoder reset. */
    hle->prepared = true;
    hle->cursor = bit_offset / 8;
    hle->bit_offset = 0;
    return true;
}

static bool output_copy(NP560NPEHLE *hle, CPUDMCUState *env)
{
    uint16_t source_high = stack_arg(hle, env, 0);
    uint16_t source_low = stack_arg(hle, env, 1);
    uint16_t destination_high = stack_arg(hle, env, 2);
    uint16_t destination_low = stack_arg(hle, env, 3);
    uint16_t samples = stack_arg(hle, env, 4);
    uint8_t pcm[NPE_TRANSFER_MAX];
    size_t bytes = (size_t)samples * 2;

    /* The stopped Hero run at 2E:813E supplied 00:1000 -> 00:1784,
     * 0x140 words. Keep this experimental service inside that observed
     * guest-owned NPE output area, not a generic unknown-ROM memcpy. */
    if (!hle->active || source_high ||
        source_low != 0x1000 || destination_high ||
        (destination_low & 1) || destination_low < 0x1000 ||
        destination_low >= 0x3000 || samples != 0x140 ||
        destination_low + bytes > 0x8000 || bytes > sizeof(pcm)) {
        service_error(hle, NPE_AD92, "unsupported NPE PCM transfer");
        return false;
    }
    if (!read_guest(hle, source_low, pcm, bytes) ||
        !write_guest(hle, destination_low, pcm, bytes)) {
        service_error(hle, NPE_AD92, "cannot transfer NPE PCM");
        return false;
    }
    hle->last_copy_nonzero = 0;
    for (size_t i = 0; i < bytes; i += 2) {
        hle->last_copy_nonzero += lduw_le_p(pcm + i) != 0;
    }
    hle->copy_nonzero_transfers += hle->last_copy_nonzero != 0;
    return true;
}

bool np560_npe_hle_service(NP560NPEHLE *hle, CPUDMCUState *env, uint32_t pc)
{
    bool handled;
    unsigned slot;

    if (!hle) {
        return false;
    }
    switch (pc) {
    case NPE_ACD8: slot = 0; break;
    case NPE_B6DE: slot = 1; break;
    case NPE_B816: slot = 2; break;
    case NPE_B7AA: slot = 3; break;
    case NPE_B84E: slot = 4; break;
    case NPE_AD92: slot = 5; break;
    default:
        return false;
    }
    if (!hole_is_strict(hle, pc)) {
        service_error(hle, pc, "resident ROM service marker changed");
        return false;
    }
    hle->calls[slot]++;
    hle->last_pc = pc;
    hle->last_error[0] = 0;
    if (slot <= 1) {
        trace_init_call(hle, env, slot);
    }
    switch (pc) {
    case NPE_ACD8:
        /* The original caller sets hardware and callback configuration in
         * 08:2F22 before this point. Record the requested mode here, but do
         * not invent unseen register or memory writes. */
        handled = stack_arg(hle, env, 0) <= 0x100;
        if (!handled) {
            service_error(hle, pc, "unexpected audio-init argument");
        }
        break;
    case NPE_B6DE: handled = stream_init(hle, env); break;
    case NPE_B816: handled = stream_position(hle, env); break;
    case NPE_B7AA: handled = stream_decode(hle, env); break;
    case NPE_B84E: handled = stream_rebase(hle, env); break;
    case NPE_AD92: handled = output_copy(hle, env); break;
    default: g_assert_not_reached();
    }
    return handled;
}

char *np560_npe_hle_state(NP560NPEHLE *hle)
{
    char *state;
    GString *text;
    uint32_t first, sequence;

    if (!hle) {
        return g_strdup("disabled");
    }
    state = g_strdup_printf(
        "experimental active=%u prepared=%u format=%u cursor=%04x bit=%u "
        "frame-bits=%u stream-frames=%" PRIu64
        " calls=%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
        ",%" PRIu64 ",%" PRIu64 " decoded=%" PRIu64
        " decoded-nonzero=%" PRIu64 " last-decode-nonzero=%u"
        " copies-nonzero=%" PRIu64 " last-copy-nonzero=%u"
        " failures=%" PRIu64
        " last=%02x:%04x error=%s",
        hle->active, hle->prepared, hle->format, hle->cursor,
        hle->bit_offset, hle->frame_bits, hle->playback_frames,
        hle->calls[0], hle->calls[1], hle->calls[2], hle->calls[3],
        hle->calls[4], hle->calls[5], hle->decoded_frames,
        hle->decoded_nonzero_frames, hle->last_decode_nonzero,
        hle->copy_nonzero_transfers, hle->last_copy_nonzero,
        hle->failed_calls,
        hle->last_pc >> 16, hle->last_pc & 0xffff,
        hle->last_error[0] ? hle->last_error : "none");
    text = g_string_new(state);
    g_free(state);
    first = hle->init_trace_count > NPE_INIT_TRACE_SLOTS ?
        hle->init_trace_count - NPE_INIT_TRACE_SLOTS : 0;
    g_string_append_printf(text, " init-trace=%u:", hle->init_trace_count);
    for (sequence = first; sequence < hle->init_trace_count; sequence++) {
        const NP560NPEInitTrace *trace = &hle->init_trace[
            sequence % NPE_INIT_TRACE_SLOTS];
        unsigned i;

        g_string_append_printf(text,
            "%s%u@%02x:%04x/sp%04x/fp%04x/r%04x,%04x,%04x,%04x/s",
            sequence == first ? "" : ";", trace->service,
            trace->caller >> 16, trace->caller & 0xffff,
            trace->sp, trace->fp, trace->regs[0], trace->regs[1],
            trace->regs[2], trace->regs[3]);
        for (i = 0; i < ARRAY_SIZE(trace->stack); i++) {
            g_string_append_printf(text, "%s%04x", i ? "," : "",
                                   trace->stack[i]);
        }
        g_string_append(text, "/frames");
        for (i = 0; i < trace->frame_count; i++) {
            g_string_append_printf(text, "%s%04x>%04x:%04x(%04x)",
                                   i ? "," : "", trace->frames[i].fp,
                                   trace->frames[i].return_cs,
                                   trace->frames[i].return_pc,
                                   trace->frames[i].parent_fp);
        }
    }
    return g_string_free(text, false);
}
