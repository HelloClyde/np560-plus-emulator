/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/timer.h"
#include "exec/address-spaces.h"
#include "cpu.h"
#include "np560_mp3_codec.h"
#include "np560_mp3_hle.h"
#include "np560_eq.h"

/* Version 1 mirrors the NEW software workspace of the reconstructed
 * MP3 decoder, not recovered factory-private fields. Original ring,
 * session, heap, callbacks and all DAC transfers remain guest code.
 * Version 2 additionally HLEs the reconstructed public free-word query.
 * Version 3 retains compressed input through PCM handoff, then reclaims
 * the completed window AFTER calculating the query's safe write credit.
 * Version 4 also copies decoded PCM into the owned session's output pair;
 * native publication and per-request DTU/DAC transport remain unchanged.
 * Version 5 permits a bounded short final frame only at original producer
 * EOF, with all audio bits present in real input/history; no byte padding.
 * Version 6 holds first-frame delivery for original configured priming;
 * it is a software lifecycle contract, not recovered DSP cycle latency. */
enum {
    WORK_BYTES = 0x6300, PENDING = 8, PCM_VALID = 14, STATUS = 16,
    DETAIL = 18, MAGIC = 20, HDR0 = 0x48, HDR1 = 0x4a, LENGTH = 0x4c,
    BODY_BYTES = 0x50, CRC = 0x54, FRAME = 0x100, SCRATCH = 0x3300,
    PCM_LEFT = 0x5700, PCM_RIGHT = 0x5b80,
    RECLAIM_END = 0x60, RECLAIM_PENDING = 0x62, STAGED = 0x64,
    FINAL_INPUT = 0x66, RING_FORMAT_CHANGE = 0x58,
};

typedef struct MP3Session {
    NP560EQ eq;
    NP560MP3Codec *codec;
    NP560MP3Frame frame;
    bool pending;
    unsigned next_pcm_offset, priming_remaining;
    uint64_t frames, granules;
    unsigned startup_history_frames, startup_history_available;
} MP3Session;

#define MP3_LIFECYCLE_EVENTS 64

typedef struct MP3LifecycleEvent {
    int64_t virtual_ns;
    uint32_t workspace;
    unsigned service;
    uint64_t frames, granules, session_frames, session_granules;
    bool present, pending;
} MP3LifecycleEvent;

struct NP560MP3HLE {
    DMCUCPU *cpu;
    uint32_t base;
    unsigned version, gate_count;
    GHashTable *sessions;
    uint64_t calls[4], frames, granules, failures, reset_count;
    uint64_t input_space_calls, input_space_failures;
    uint64_t pcm_copy_calls, pcm_copy_failures;
    uint64_t final_frame_calls, final_frame_failures;
    uint64_t priming_calls;
    /* Read-only classification of actual codec returns. NO_PCM deliberately
     * does not claim missing reservoir: the kernel leaves that ambiguous. */
    uint64_t codec_results[NP560_MP3_MISSING_HISTORY + 1];
    uint64_t no_pcm_reasons[4];
    NP560MP3NoPCMInfo last_no_pcm;
    uint64_t startup_history_frames, history_after_output, history_no_progress;
    unsigned max_startup_history_frames;
    /* v7 parameters only; v8 adds explicitly assumed EQ, not factory DSP. */
    uint16_t mode_coefficients[10];
    bool mode_loaded, mode_enabled;
    uint64_t mode_calls[3], mode_failures;
    uint64_t lifecycle_next;
    MP3LifecycleEvent lifecycle[MP3_LIFECYCLE_EVENTS];
};

/* Entry to validated reset/release, or successful first-frame decode. These
 * bounded observations have no guest writes, clock charge or callback. */
static void lifecycle_event(NP560MP3HLE *s, MP3Session *session,
                            uint32_t workspace, unsigned service)
{
    MP3LifecycleEvent *event =
        &s->lifecycle[s->lifecycle_next++ % MP3_LIFECYCLE_EVENTS];

    event->virtual_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    event->workspace = workspace;
    event->service = service;
    event->frames = s->frames;
    event->granules = s->granules;
    event->present = session != NULL;
    event->pending = session && session->pending;
    event->session_frames = session ? session->frames : 0;
    event->session_granules = session ? session->granules : 0;
}

static void session_free(void *opaque)
{
    MP3Session *session = opaque;
    np560_mp3_codec_free(session->codec);
    g_free(session);
}

void np560_mp3_hle_reset(void *opaque)
{
    NP560MP3HLE *s = opaque;
    g_hash_table_remove_all(s->sessions);
    s->reset_count++;
    s->lifecycle_next = 0;
    memset(s->lifecycle, 0, sizeof(s->lifecycle));
    memset(s->mode_coefficients, 0, sizeof(s->mode_coefficients));
    s->mode_loaded = s->mode_enabled = false;
}

void np560_mp3_hle_free(NP560MP3HLE *s)
{
    if (s) {
        g_hash_table_destroy(s->sessions);
        g_free(s);
    }
}

static bool gate_matches(NP560MP3HLE *s, uint32_t pc, unsigned service)
{
    uint8_t raw[16];
    uint16_t words[] = {0x0f00, 0xc620, 0x504d, 0x484c,
                        s->version, service, 0, 0};
    unsigned i;
    if (address_space_read(cpu_get_address_space(CPU(s->cpu), DMCU_AS_CODE),
                           pc, MEMTXATTRS_UNSPECIFIED, raw, sizeof(raw)) != MEMTX_OK) {
        return false;
    }
    for (i = 0; i < ARRAY_SIZE(words); i++) {
        if (lduw_le_p(raw + 2 * i) != words[i]) {
            return false;
        }
    }
    return true;
}

NP560MP3HLE *np560_mp3_hle_new(DMCUCPU *cpu, uint32_t base, Error **errp)
{
    NP560MP3HLE *s;
    uint8_t marker[16];
    unsigned i;
    if ((base & 1) || base < 0x10000 || base > 0x30000 - 64 ||
        (base >> 16) != ((base + 63) >> 16)) {
        error_setg(errp, "MP3 HLE gate must fit ROM 01/02");
        return NULL;
    }
    s = g_new0(NP560MP3HLE, 1);
    s->cpu = cpu;
    s->base = base;
    s->sessions = g_hash_table_new_full(g_direct_hash, g_direct_equal, NULL, session_free);
    if (address_space_read(cpu_get_address_space(CPU(cpu), DMCU_AS_CODE),
                           base, MEMTXATTRS_UNSPECIFIED, marker, sizeof(marker)) != MEMTX_OK ||
        (lduw_le_p(marker + 8) < 1 || lduw_le_p(marker + 8) > 8)) {
        error_setg(errp, "MP3 HLE gate %06x has no versioned service marker", base);
        np560_mp3_hle_free(s);
        return NULL;
    }
    s->version = lduw_le_p(marker + 8);
    s->gate_count = s->version >= 7 ? 9 : s->version >= 4 ? 6 : s->version >= 2 ? 5 : 4;
    if ((base >> 16) != ((base + s->gate_count * 16 - 1) >> 16)) {
        error_setg(errp, "MP3 HLE gate must fit ROM 01/02");
        np560_mp3_hle_free(s);
        return NULL;
    }
    for (i = 0; i < s->gate_count; i++) {
        if (!gate_matches(s, base + 16 * i, i)) {
            error_setg(errp, "MP3 HLE gate %06x has no versioned service marker", base + 16 * i);
            np560_mp3_hle_free(s);
            return NULL;
        }
    }
    return s;
}

/* Refuse MMIO, ROM, wraparound and cross-bank workspaces before any write.
 * Check every mapped RAM subsection: aliases may split an owned heap. */
static bool writable_span(AddressSpace *as, uint32_t address, uint32_t size)
{
    uint32_t done = 0;
    while (done < size) {
        MemoryRegionSection section = memory_region_find(as->root, address + done, size - done);
        uint64_t bytes = int128_get64(section.size);
        bool valid = section.mr && bytes && !section.readonly &&
            section.offset_within_address_space == address + done &&
            memory_region_is_ram(section.mr) && !memory_region_is_rom(section.mr) &&
            !memory_region_is_ram_device(section.mr);
        if (section.mr) {
            memory_region_unref(section.mr);
        }
        if (!valid) {
            return false;
        }
        done += bytes;
    }
    return true;
}

static uint16_t read_word(AddressSpace *as, uint32_t address)
{
    uint8_t data[2];
    MemTxResult result = address_space_read(as, address, MEMTXATTRS_UNSPECIFIED, data, 2);
    g_assert(result == MEMTX_OK); /* fully validated ordinary RAM */
    return lduw_le_p(data);
}

static void write_word(AddressSpace *as, uint32_t address, uint16_t word)
{
    uint8_t data[2];
    MemTxResult result;
    stw_le_p(data, word);
    result = address_space_write(as, address, MEMTXATTRS_UNSPECIFIED, data, 2);
    g_assert(result == MEMTX_OK);
}

/* Version 2 also implements the missing public 01:49BE query. This uses
 * the explicit NEW factory/session/ring layouts, not guessed ROM fields.
 * It performs the same validation, status and free-word calculation as
 * the reconstructed three-layer guest query. No input is consumed, no
 * ready bit is forced, and neither a callback nor a file read is made.
 * Version 3 additionally reclaims a completed retained input window as
 * documented below; unlike v2 its query is not a read-only ring operation.
 * A service runs atomically on the vCPU; transient native claim/release
 * stores are unnecessary, but an already held guest lock is respected. */
static void input_space(NP560MP3HLE *s, CPUDMCUState *env, AddressSpace *as)
{
    uint32_t owner, workspace;
    uint16_t segment, offset, read, writer, bank;
    unsigned status = 2, result = 0, available;
    bool publish_status = false, root_busy = false;

    s->input_space_calls++;
    if (!writable_span(as, 0x3342, 6)) {
        goto done;
    }
    segment = read_word(as, 0x3342);
    offset = read_word(as, 0x3344);
    if (segment == 0xffff) {
        status = 7;
        root_busy = true;
        goto done;
    }
    if (!(segment | offset)) {
        status = 8;
        goto failed;
    }
    if ((segment != 0x51 && segment != 0x52) || (offset & 1) ||
        (segment == 0x51 && offset < 0x4a46) ||
        (segment == 0x52 && offset > 0x3a40 - 96) ||
        (offset & 0x7fff) > 0x8000 - 96) {
        goto failed;
    }
    owner = ((uint32_t)segment << 16) | offset;
    if (!writable_span(as, owner, 96) ||
        read_word(as, owner + 82) != 0x504d ||
        !read_word(as, owner + 80) || read_word(as, owner + 80) > 255) {
        goto failed;
    }
    if (read_word(as, owner + 46)) {
        status = 7;
        goto failed;
    }
    publish_status = true;
    if (read_word(as, owner + 44) != 0x534d) {
        status = 8;
        goto failed;
    }
    bank = read_word(as, owner + 8) & 0x1ff;
    offset = read_word(as, owner + 16);
    workspace = ((uint32_t)bank << 15) | offset;
    if ((offset & 1) || offset > 0x8000 - WORK_BYTES ||
        !writable_span(as, workspace, WORK_BYTES) ||
        read_word(as, workspace + 0x46) != 0x5247 ||
        !writable_span(as, 0x3340, 2)) {
        goto failed;
    }
    read = read_word(as, workspace + 0x40);
    writer = read_word(as, 0x3340);
    if (read < 0x1000 || read >= 0x1600 ||
        writer < 0x1000 || writer >= 0x1600 || (writer & 1)) {
        goto failed;
    }
    available = (writer + 0x600 - read) % 0x600;
    if (available > 1532) {
        goto failed;
    }
    if (s->version >= 3) {
        unsigned reclaim = read_word(as, workspace + RECLAIM_PENDING);
        unsigned staged = read_word(as, workspace + STAGED);
        unsigned end = read_word(as, workspace + RECLAIM_END);
        unsigned length = read_word(as, workspace + LENGTH);
        unsigned pending = read_word(as, workspace + PENDING);

        /* v3 is an explicit compatibility contract, not a factory-ROM
         * claim. Return capacity of the still-owned window, then make
         * its completed frame reusable. The original producer receives
         * conservative (never excessive) credit; E906 compares its last
         * consumption delta against a window including that very frame.
         * No caller-PC check, EOF-bit edit, input invention or host I/O. */
        if (reclaim > 1 || staged > 1 || (reclaim && staged) ||
            ((reclaim || staged) &&
             (!length || length > available ||
              end != 0x1000 + (read - 0x1000 + length) % 0x600)) ||
            (reclaim && pending)) {
            goto failed;
        }
        if (reclaim) {
            write_word(as, workspace + 0x40, end);
            write_word(as, workspace + RECLAIM_PENDING, 0);
        }
    }
    result = 766 - (available + 1) / 2;
    status = 0;
failed:
    if (publish_status) {
        write_word(as, owner + 52, status);
    }
    if (status) {
        write_word(as, 0x3346, 1);
    }
done:
    env->gpr[0] = result;
    env->gpr[2] = status;
    if (status > 1 && !root_busy) {
        s->input_space_failures++;
    }
}

static void publish_pcm(NP560MP3HLE *s, MP3Session *session, AddressSpace *as,
                        uint32_t address, unsigned offset)
{
    unsigned i, channel;
    for (channel = 0; channel < 2; channel++) {
        for (i = 0; i < 576; i++) {
            int16_t sample = channel < session->frame.channels ?
                session->frame.pcm[(offset + i) * session->frame.channels + channel] : 0;
            write_word(as, address + (channel ? PCM_RIGHT : PCM_LEFT) + i * 2, sample);
        }
    }
    write_word(as, address + PENDING, session->pending ? 1 : 0);
    write_word(as, address + PCM_VALID, 576);
    s->granules++;
}

/* Compatibility gain from original 08:34C4 and PRG 0x3057E6, not a recovered
 * implementation of the missing MP3-specific 333E processing. Q15 rounded
 * multiplication matches the original MULS.ss.r.s fractional operation.
 * Avoid implementation-defined right shifts of negative signed integers. */
static const uint16_t mp3_volume_gain[8] = {
        0, 0x2027, 0x287a, 0x32f5, 0x4027, 0x50c3, 0x65ad, 0x7fff
};

static int16_t mp3_output_gain(int16_t sample, unsigned level)
{
    int32_t rounded = (int32_t)sample * mp3_volume_gain[level] + 16384;

    return rounded >= 0 ? rounded / 32768 : -((32767 - rounded) / 32768);
}

/* Version 4 implements the reconstructed session's software PCM delivery.
 * DS0:R3 identifies its already-claimed owner, R0 the next output phase.
 * This is NOT hardware DMA: the original PHASE/READY publication, callbacks,
 * DTU buffer programming and individual DAC requests still execute normally.
 * Validate both sources and ALL destinations before the first output write. */
static void copy_pcm(NP560MP3HLE *s, CPUDMCUState *env, AddressSpace *as)
{
    uint32_t offset = env->gpr[3], phase = env->gpr[0];
    uint32_t owner, workspace, bank, work_offset;
    uint16_t buffers[4];
    uint8_t pcm[2304];
    MP3Session *session;
    MemTxResult transaction;
    unsigned status = 2, i, j;

    s->pcm_copy_calls++;
    if (env->ignore_ds_count || (offset & 1) || offset > 0x8000 - 96 || phase > 1) {
        goto done;
    }
    owner = ((env->sfr[DMCU_SFR_DS0] & 0x1ff) << 15) | offset;
    if (owner < 0x514a46 || owner > 0x523a40 - 96 ||
        !writable_span(as, owner, 96) ||
        read_word(as, owner + 82) != 0x504d ||
        !read_word(as, owner + 80) || read_word(as, owner + 80) > 255 ||
        read_word(as, owner + 44) != 0x534d ||
        read_word(as, owner + 46) != 1 ||
        read_word(as, owner + 48) != (phase ^ 1)) {
        goto done;
    }
    bank = read_word(as, owner + 8);
    work_offset = read_word(as, owner + 16);
    workspace = (bank << 15) | work_offset;
    if (bank > 0x1ff || (work_offset & 1) || work_offset > 0x8000 - WORK_BYTES ||
        !writable_span(as, workspace, WORK_BYTES) ||
        !g_hash_table_lookup(s->sessions, GUINT_TO_POINTER(workspace + 1)) ||
        read_word(as, workspace + MAGIC) != 0x4d33 ||
        read_word(as, workspace + PCM_VALID) != 576) {
        goto done;
    }
    for (i = 0; i < 4; i++) {
        buffers[i] = read_word(as, owner + 20 + 4 * i);
        if (read_word(as, owner + 18 + 4 * i) ||
            (buffers[i] & 1) || buffers[i] < 0x1600 || buffers[i] > 0x8000 - 1152 ||
            !writable_span(as, buffers[i], 1152)) {
            goto done;
        }
        for (j = 0; j < i; j++) {
            if (buffers[i] < buffers[j] + 1152 && buffers[j] < buffers[i] + 1152) {
                goto done;
            }
        }
    }
    transaction = address_space_read(as, workspace + PCM_LEFT,
                                     MEMTXATTRS_UNSPECIFIED, pcm, sizeof(pcm));
    g_assert(transaction == MEMTX_OK); /* fully validated ordinary RAM */
    /* Reconstructed MP3 output contract: original 16:EDB4 (and the
     * original software-gain path 08:34C4) sets BIT8A.7 after the current
     * and target volume have both reached zero. Keep that guest-owned
     * ramp/flag; suppress only this published buffer, not decoder history,
     * decoded source PCM, device timing or the other output phase.
     * The original callback advances the current level; never ramp it here. */
    session = g_hash_table_lookup(s->sessions, GUINT_TO_POINTER(workspace + 1));
    if (s->version >= 8 && s->mode_enabled) {
        unsigned level = read_word(as, 0x4a64) >> 8;
        uint16_t gain = level < 8 ? mp3_volume_gain[level] : 32768;
        bool mute = read_word(as, 0xf014) & 0x0080;

        if (!np560_eq_configure(&session->eq, session->frame.hz,
                                s->mode_coefficients, true)) {
            s->mode_failures++;
            goto done;
        }
        for (i = 0; i < sizeof(pcm); i += 2) {
            double filtered = np560_eq_sample(&session->eq, i / 1152,
                                              (int16_t)lduw_le_p(pcm + i));
            /* Advance history even while muted, and clip only after gain. */
            stw_le_p(pcm + i, mute ? 0 : np560_eq_quantize(filtered, gain));
        }
    } else if (read_word(as, 0xf014) & 0x0080) {
        memset(pcm, 0, sizeof(pcm));
    } else {
        uint16_t volume = read_word(as, 0x4a64);
        /* DMCU logical byte 4A64 (current) is the high lane; 4A65 is
         * target. Respect the native ramp instead of jumping to target. */
        unsigned level = volume >> 8;

        /* A zero current level is silent even before the native mute flag
         * catches up. Never turn the all-zero ramp endpoint into full gain.
         * Do not turn unrelated/corrupt bytes into a table index. */
        if (level < 8) {
            for (i = 0; i < sizeof(pcm); i += 2) {
                int16_t value = (int16_t)(pcm[i] | (pcm[i + 1] << 8));
                uint16_t scaled = mp3_output_gain(value, level);

                pcm[i] = scaled;
                pcm[i + 1] = scaled >> 8;
            }
        }
    }
    for (i = 0; i < 2; i++) {
        transaction = address_space_write(as, buffers[i * 2 + phase],
                                          MEMTXATTRS_UNSPECIFIED,
                                          pcm + i * 1152, 1152);
        g_assert(transaction == MEMTX_OK);
    }
    status = 0;
done:
    env->gpr[0] = status ? 0 : 576;
    env->gpr[2] = status;
    s->pcm_copy_failures += status != 0;
}

static void audio_mode_service(NP560MP3HLE *s, CPUDMCUState *env,
                               AddressSpace *as, unsigned service)
{
    unsigned i, sp = env->gpr[15] & 0xffff;
    uint32_t address;
    uint16_t coefficients[10], hi, lo, count;
    uint8_t *stack = s->cpu->internal_data;

    s->mode_calls[service - 6]++;
    if (service == 8) {
        s->mode_enabled = false;
        if (s->version >= 8) {
            GHashTableIter iter;
            gpointer value;
            g_hash_table_iter_init(&iter, s->sessions);
            while (g_hash_table_iter_next(&iter, NULL, &value)) {
                np560_eq_reset_history(&((MP3Session *)value)->eq);
            }
        }
        return;
    }
    if (service == 7) {
        if (s->mode_loaded) {
            s->mode_enabled = true;
        } else {
            s->mode_failures++;
        }
        return;
    }
    /* Ordinary SCALL return frame is four bytes; AJMP veneer adds none.
     * Read the unbanked stack, preserving all guest registers and flags. */
    if (sp > 0x10000 - 10) {
        s->mode_failures++;
        return;
    }
    hi = lduw_le_p(stack + sp + 4);
    lo = lduw_le_p(stack + sp + 6);
    count = lduw_le_p(stack + sp + 8);
    address = ((uint32_t)hi << 16) | lo;
    if (count != 10 || hi > 0xff || (address & 1) || address > 0x1000000 - 20) {
        s->mode_failures++;
        return;
    }
    /* Validate every subsection before reading; never cause MMIO side
     * effects through an untrusted pointer. ROM coefficients are valid. */
    for (i = 0; i < 20;) {
        MemoryRegionSection section = memory_region_find(as->root, address + i, 20 - i);
        uint64_t bytes = int128_get64(section.size);
        bool valid = section.mr && bytes &&
            section.offset_within_address_space == address + i &&
            (memory_region_is_ram(section.mr) || memory_region_is_rom(section.mr)) &&
            !memory_region_is_ram_device(section.mr);
        if (section.mr) {
            memory_region_unref(section.mr);
        }
        if (!valid) {
            s->mode_failures++;
            return;
        }
        i += bytes;
    }
    for (i = 0; i < 10; i++) {
        coefficients[i] = read_word(as, address + 2 * i);
    }
    memcpy(s->mode_coefficients, coefficients, sizeof(coefficients));
    s->mode_loaded = true;
}

bool np560_mp3_hle_service(void *opaque, CPUDMCUState *env, uint32_t pc)
{
    NP560MP3HLE *s = opaque;
    AddressSpace *as = cpu_get_address_space(CPU(s->cpu), DMCU_AS_DATA);
    uint32_t offset = env->gpr[3], address;
    unsigned service, status = 0, detail = 0, result = 0, i;
    MP3Session *session;
    void *key;
    if (pc < s->base || pc >= s->base + 16 * s->gate_count || (pc - s->base) % 16) {
        return false;
    }
    service = (pc - s->base) / 16;
    if (!gate_matches(s, pc, service)) {
        return false;
    }
    if (service >= 6) {
        audio_mode_service(s, env, as, service);
        return true;
    }
    if (service == 4) {
        input_space(s, env, as);
        return true;
    }
    if (service == 5) {
        copy_pcm(s, env, as);
        return true;
    }
    s->calls[service]++;
    if (env->ignore_ds_count || (offset & 1) || offset > 0x8000 - WORK_BYTES) {
        env->gpr[0] = 0;
        env->gpr[2] = 2;
        s->failures++;
        return true;
    }
    address = ((env->sfr[DMCU_SFR_DS0] & 0x1ff) << 15) | offset;
    if (!writable_span(as, address, WORK_BYTES)) {
        env->gpr[0] = 0;
        env->gpr[2] = 2;
        s->failures++;
        return true;
    }
    key = GUINT_TO_POINTER(address + 1);
    session = g_hash_table_lookup(s->sessions, key);
    if (service == 0 || service == 3) {
        lifecycle_event(s, session, address, service);
    }
    if (service == 0) {
        if (!session) {
            session = g_new0(MP3Session, 1);
            session->codec = np560_mp3_codec_new();
            if (!session->codec) {
                g_free(session);
                status = 2;
                goto complete;
            }
            g_hash_table_insert(s->sessions, key, session);
        }
        np560_mp3_codec_reset(session->codec);
        memset(&session->eq, 0, sizeof(session->eq));
        memset(&session->frame, 0, sizeof(session->frame));
        session->pending = false;
        session->next_pcm_offset = session->priming_remaining = 0;
        session->frames = session->granules = 0;
        session->startup_history_frames = session->startup_history_available = 0;
        for (i = 0; i < 1152; i++) {
            write_word(as, address + PCM_LEFT + i * 2, 0);
        }
        write_word(as, address + PENDING, 0);
        write_word(as, address + PCM_VALID, 0);
        write_word(as, address + MAGIC, 0x4d33);
    } else if (service == 3) {
        g_hash_table_remove(s->sessions, key);
        write_word(as, address + MAGIC, 0);
        write_word(as, address + PENDING, 0);
        write_word(as, address + PCM_VALID, 0);
    } else if (!session || read_word(as, address + MAGIC) != 0x4d33) {
        status = 2;
    } else if (service == 2) {
        if (!session->pending) {
            status = 1;
        } else if (session->priming_remaining) {
            session->priming_remaining--;
            s->priming_calls++;
        } else {
            unsigned pcm_offset = session->next_pcm_offset;
            session->next_pcm_offset += 576;
            session->pending = session->next_pcm_offset <
                               session->frame.samples_per_channel;
            if (pcm_offset == 0) {
                /* The ring cleared its per-step change flag while waiting.
                 * Carry the first frame's notification to its first real
                 * publication, so factory FIRST_FORMAT_SEEN is not lost. */
                write_word(as, address + RING_FORMAT_CHANGE, 1);
            }
            publish_pcm(s, session, as, address, pcm_offset);
            session->granules++;
            result = 576;
        }
    } else if (session->pending) {
        status = 6;
    } else {
        uint8_t input[1532];
        uint16_t h0 = read_word(as, address + HDR0);
        uint16_t h1 = read_word(as, address + HDR1);
        unsigned header = (h0 & 1) ? 4 : 6;
        unsigned body = read_word(as, address + BODY_BYTES);
        unsigned length = read_word(as, address + LENGTH);
        unsigned final = s->version >= 5 ? read_word(as, address + FINAL_INPUT) : 0;
        NP560MP3Status decoded;
        /* A new input attempt supersedes the preceding publication. Even
         * staging/EOF validation failures must not leave old PCM marked
         * ready. Pending-granule/busy paths above retain their own output. */
        write_word(as, address + PCM_VALID, 0);
        if (body > sizeof(input) - header || length != header + body || final > 1) {
            status = 2;
            goto complete;
        }
        stw_be_p(input, h0);
        stw_be_p(input + 2, h1);
        if (header == 6) {
            stw_be_p(input + 4, read_word(as, address + CRC));
        }
        /* Guest staging stores network-order words on a little-endian
         * word bus. The last odd byte lives in the word's high lane. */
        for (i = 0; i < body; i++) {
            uint16_t word = read_word(as, address + SCRATCH + (i & ~1u));
            input[header + i] = (i & 1) ? word : word >> 8;
        }
        /* Descriptor rejection must happen before the codec commits its
         * reservoir and synthesis history. Otherwise retrying a corrected
         * descriptor decodes this packet twice and changes subsequent PCM.
         * Channel mode is wholly in header byte 3 (high two bits).
         */
        if (read_word(as, address + FRAME + 2) !=
            ((input[3] >> 6) == 3 ? 1 : 2)) {
            status = 7;
            detail = 0x800 + NP560_MP3_DECODE_ERROR;
            goto complete;
        }
        if (final) {
            s->final_frame_calls++;
            /* FINAL_INPUT is a request from the reconstructed ring. The
             * independently checked original producer EOF bit is required;
             * neither this gate nor the codec may turn a live short read
             * into end-of-stream or fetch unprovided staging bytes. */
            if (!writable_span(as, 0xf012, 2) ||
                !(read_word(as, 0xf012) & 0x80)) {
                s->final_frame_failures++;
                status = 2;
                goto complete;
            }
            decoded = np560_mp3_codec_decode_final(session->codec, input, length,
                                                   &session->frame);
            s->final_frame_failures += decoded != NP560_MP3_OK;
        } else {
            decoded = np560_mp3_codec_decode(session->codec, input, length, &session->frame);
        }
        if ((unsigned)decoded < G_N_ELEMENTS(s->codec_results)) {
            s->codec_results[decoded]++;
        }
        if (decoded == NP560_MP3_NO_PCM) {
            s->last_no_pcm = np560_mp3_codec_no_pcm_info(session->codec);
            if (s->last_no_pcm.reason < G_N_ELEMENTS(s->no_pcm_reasons)) {
                s->no_pcm_reasons[s->last_no_pcm.reason]++;
            }
            if (s->last_no_pcm.reason == 2) {
                if (session->frames != 0) {
                    s->history_after_output++;
                } else {
                    if (session->startup_history_frames &&
                        s->last_no_pcm.available_history <= session->startup_history_available) {
                        s->history_no_progress++;
                    }
                    session->startup_history_available = s->last_no_pcm.available_history;
                    session->startup_history_frames++;
                    s->startup_history_frames++;
                    s->max_startup_history_frames = MAX(s->max_startup_history_frames,
                                                       session->startup_history_frames);
                }
            }
        }
        if (decoded != NP560_MP3_OK || session->frame.consumed != length ||
            session->frame.channels != read_word(as, address + FRAME + 2)) {
            status = 7;
            detail = 0x800 + (decoded ? decoded : NP560_MP3_DECODE_ERROR);
            write_word(as, address + PCM_VALID, 0);
        } else {
            unsigned prime = 1;
            /* Original configured minimum nonfatal startup calls, not a
             * fabricated DSP cycle delay. Never prime an active stream or
             * an unconfigured/different-rate caller. 100 is the original
             * unconfigured sentinel, not a valid queue depth. */
            if (s->version >= 6 && session->frames == 0 &&
                writable_span(as, 0xf006, 2) &&
                writable_span(as, 0xf014, 2) &&
                writable_span(as, 0x4a60, 2) &&
                writable_span(as, 0x512b10, 2) &&
                !(read_word(as, 0xf006) & 0x8000) &&
                (read_word(as, 0xf014) & 0x400) &&
                read_word(as, 0x4a60) == session->frame.hz) {
                unsigned configured = read_word(as, 0x512b10);
                if (configured >= 1 && configured <= 3) {
                    prime = configured;
                }
            }
            session->pending = session->frame.samples_per_channel == 1152;
            session->next_pcm_offset = 576;
            if (prime > 1) {
                /* Keep the actual decoded frame and compressed ownership.
                 * No output buffer, ready bit, or consumption is published.
                 * Subsequent steps release granules in source order. */
                session->next_pcm_offset = 0;
                session->priming_remaining = prime - 2;
                session->pending = true;
                write_word(as, address + PENDING, 1);
                write_word(as, address + PCM_VALID, 0);
                s->priming_calls++;
            } else {
                publish_pcm(s, session, as, address, 0);
                result = 576;
                session->granules++;
            }
            s->frames++;
            session->frames++;
            if (session->frames == 1) {
                lifecycle_event(s, session, address, service);
            }
        }
    }
complete:
    write_word(as, address + STATUS, status);
    write_word(as, address + DETAIL, detail);
    env->gpr[0] = result;
    env->gpr[2] = status;
    if (status > 1) {
        s->failures++;
    }
    return true;
}

char *np560_mp3_hle_state(NP560MP3HLE *s)
{
    g_autoptr(GString) events = g_string_new(NULL);
    uint64_t first, sequence;

    if (!s) {
        return g_strdup("{\"enabled\":false}");
    }
    first = s->lifecycle_next - MIN(s->lifecycle_next, MP3_LIFECYCLE_EVENTS);
    for (sequence = first; sequence < s->lifecycle_next; sequence++) {
        MP3LifecycleEvent *event = &s->lifecycle[sequence % MP3_LIFECYCLE_EVENTS];

        g_string_append_printf(events,
            "%s{\"sequence\":%" PRIu64 ",\"virtual_ns\":%" PRId64
            ",\"workspace\":%u,\"service\":%u,\"present\":%s,\"pending\":%s,"
            "\"frames\":%" PRIu64 ",\"granules\":%" PRIu64 ","
            "\"session_frames\":%" PRIu64 ",\"session_granules\":%" PRIu64 "}",
            sequence == first ? "" : ",", sequence, event->virtual_ns,
            event->workspace, event->service, event->present ? "true" : "false",
            event->pending ? "true" : "false", event->frames, event->granules,
            event->session_frames, event->session_granules);
    }
    g_autoptr(GString) modes = g_string_new(NULL);
    g_autoptr(GString) codec_results = g_string_new(NULL);
    static const char *const codec_names[] = {
        "ok", "short", "bad_header", "unsupported", "bad_crc",
        "no_pcm", "decode_error", "missing_history"
    };
    G_STATIC_ASSERT(G_N_ELEMENTS(codec_names) == G_N_ELEMENTS(s->codec_results));
    for (unsigned i = 0; i < G_N_ELEMENTS(codec_names); i++) {
        g_string_append_printf(codec_results, "%s\"%s\":%" PRIu64,
                               i ? "," : "", codec_names[i], s->codec_results[i]);
    }
    for (unsigned i = 0; i < 10; i++) {
        g_string_append_printf(modes, "%s%u", i ? "," : "", s->mode_coefficients[i]);
    }
    return g_strdup_printf("{\"audio_mode\":{\"loaded\":%s,\"enabled\":%s,"
        "\"dsp_implemented\":%s,\"coefficients\":[%s],"
        "\"calls\":[%" PRIu64 ",%" PRIu64 ",%" PRIu64 "],\"failures\":%" PRIu64 "},"
        "\"enabled\":true,\"base\":%u,\"sessions\":%u,"
        "\"version\":%u,\"input_space_calls\":%" PRIu64 ","
        "\"input_space_failures\":%" PRIu64 ","
        "\"pcm_copy_calls\":%" PRIu64 ",\"pcm_copy_failures\":%" PRIu64 ","
        "\"final_frame_calls\":%" PRIu64 ",\"final_frame_failures\":%" PRIu64 ","
        "\"priming_calls\":%" PRIu64 ","
        "\"calls\":[%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "],"
        "\"frames\":%" PRIu64 ",\"granules\":%" PRIu64 ",\"failures\":%" PRIu64 ","
        "\"device_resets\":%" PRIu64 ",\"lifecycle_next\":%" PRIu64
        ",\"lifecycle_events\":[%s],\"codec_results\":{%s},"
        "\"no_pcm_reasons\":{\"invalid_sideinfo\":%" PRIu64
        ",\"missing_history\":%" PRIu64 ",\"unknown\":%" PRIu64 "},"
        "\"last_no_pcm\":{\"reason\":%u,\"available_history\":%u,\"required_history\":%u},"
        "\"history_recovery\":{\"startup_frames\":%" PRIu64
        ",\"after_output\":%" PRIu64 ",\"no_progress\":%" PRIu64
        ",\"max_startup_frames\":%u}}",
        s->mode_loaded ? "true" : "false", s->mode_enabled ? "true" : "false",
        s->version >= 8 ? "true" : "false",
        modes->str, s->mode_calls[0], s->mode_calls[1], s->mode_calls[2], s->mode_failures,
        s->base, g_hash_table_size(s->sessions),
        s->version, s->input_space_calls, s->input_space_failures,
        s->pcm_copy_calls, s->pcm_copy_failures,
        s->final_frame_calls, s->final_frame_failures,
        s->priming_calls,
        s->calls[0], s->calls[1], s->calls[2], s->calls[3], s->frames,
        s->granules, s->failures, s->reset_count, s->lifecycle_next, events->str,
        codec_results->str, s->no_pcm_reasons[1], s->no_pcm_reasons[2],
        s->no_pcm_reasons[0] + s->no_pcm_reasons[3], s->last_no_pcm.reason,
        s->last_no_pcm.available_history, s->last_no_pcm.required_history,
        s->startup_history_frames, s->history_after_output, s->history_no_progress,
        s->max_startup_history_frames);
}
