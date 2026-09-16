/* NP560 two-channel DAC register output for Web presentation.
 *
 * Original 24:97AC/9A1E routes DTU to F1E0/F1E2. Original 08:33FA/3462
 * performs signed ramps around zero; 08:4702/475E uses REG72 bit0/bit15
 * for start/stop. We preserve the 16-bit sample words, expose signed PCM,
 * and hold the DAC value between guest writes using QEMU virtual time.
 * Dedicated request clock reconstruction is constrained by the five rate
 * entries at original 32:BD96, 08:38D0 and 24:9A1E. See
 * doc/np560_audio_requests.md for the inferred clock ratio and its limits.
 * Analog resolution/filtering, remaining control bits and amplifier GPIO
 * are not yet known. This does not implement any missing ROM decoder.
 */
#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "qemu/host-utils.h"
#include "np560_audio.h"

#define NP560_AUDIO_TICK_NS 10000000

static void np560_audio_sync(NP560AudioState *s);

static bool np560_audio_enabled(NP560AudioState *s)
{
    return (s->control & 0x8001) == 1;
}

static void np560_audio_request_tick(void *opaque)
{
    NP560AudioState *s = opaque;
    uint64_t before[2] = {s->sample_writes[0], s->sample_writes[1]};
    unsigned channel;

    /* Both request lines belong to this one sample-clock event. Render
     * once before either DAC latches; host time spent handling channel 0
     * must not advance the presentation ring before channel 1. */
    np560_audio_sync(s);
    s->request_in_progress = true;
    s->request_ticks++;
    /* Original 24:9A1E routes REG61 to DTU0/F1E0 and REG60 to DTU1/F1E2.
     * Raise one latched request per channel, never copy a buffer or invoke
     * a guest callback here. EN/IE and completion are owned by ICR/DTU. */
    dmcu_irq_raise(s->cpu, 17);
    dmcu_irq_raise(s->cpu, 16);
    s->request_in_progress = false;
    for (channel = 0; channel < 2; channel++) {
        uint64_t writes = s->sample_writes[channel] - before[channel];

        /* Count actual register writes, not inferred ready/completion.
         * These read-only diagnostics distinguish missing samples from
         * delayed presentation without changing requests or guest state. */
        s->request_writes[channel] += writes;
        s->request_without_write[channel] += writes == 0;
        s->request_multiple_writes[channel] += writes > 1;
    }
}

static void np560_audio_request_config(NP560AudioState *s)
{
    unsigned mode = s->control & 0xe;
    unsigned multiplier = ((s->pll & 0x1fff) >> 5) + 1;
    unsigned divisor = (s->pll & 0x1f) + 1;
    unsigned decimation = mode & 2 ? 1536 : 1024;
    bool supported = (mode == 8 || mode == 10) &&
                     (s->pll & 0xc000) == 0x8000;
    uint32_t hz = supported ?
        4000000u * multiplier / (divisor * decimation) : 0;
    bool running = supported && np560_audio_enabled(s);

    /* This ratio reproduces all five original dedicated configurations to
     * within 0.04% of their nominal rates. Do not substitute the nominal
     * firmware rate or tie this clock to the host 48 kHz presentation rate.
     * PLL lock, other modes and phase on reconfiguration remain unknown. */
    if (running == s->request_running && hz == s->request_hz) {
        return;
    }
    ptimer_transaction_begin(s->request_timer);
    ptimer_stop(s->request_timer);
    if (hz) {
        ptimer_set_freq(s->request_timer, hz);
    }
    ptimer_set_limit(s->request_timer, 1, 1);
    if (running) {
        ptimer_run(s->request_timer, 0);
    }
    s->request_hz = hz;
    s->request_running = running;
    ptimer_transaction_commit(s->request_timer);
}

static void np560_audio_sync(NP560AudioState *s)
{
    /* The request callback rendered both channels before either latch.
     * Avoid even a redundant virtual-clock read for its two DAC writes. */
    if (s->request_in_progress) {
        return;
    }
    int64_t elapsed = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) - s->epoch_ns;
    uint64_t target, first, frame;
    uint16_t a = np560_audio_enabled(s) ? s->sample[0] : 0;
    uint16_t b = np560_audio_enabled(s) ? s->sample[1] : 0;

    if (elapsed <= 0) {
        return;
    }
    target = muldiv64(elapsed, NP560_AUDIO_RATE, NANOSECONDS_PER_SECOND);
    if (target <= s->next_frame) {
        return;
    }
    /* Bound catch-up work after a delayed callback. Old frames are no longer
     * in the presentation ring; sequence numbers expose that loss to clients. */
    first = MAX(s->next_frame, target > NP560_AUDIO_FRAMES ?
                target - NP560_AUDIO_FRAMES : 0);
    for (frame = first; frame < target; frame++) {
        unsigned offset = (frame % NP560_AUDIO_FRAMES) * 4;

        stw_le_p(s->pcm + offset, a);
        stw_le_p(s->pcm + offset + 2, b);
    }
    s->next_frame = target;
}

static void np560_audio_tick(void *opaque)
{
    NP560AudioState *s = opaque;

    np560_audio_sync(s);
    timer_mod(s->timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
              NP560_AUDIO_TICK_NS);
}

static void np560_audio_control_event(NP560AudioState *s, unsigned reg,
                                      uint16_t old_value, uint16_t value)
{
    NP560AudioControlEvent *event =
        &s->control_events[s->control_event_next++ % NP560_AUDIO_CONTROL_EVENTS];

    event->virtual_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    event->frame = s->next_frame;
    event->pc = s->cpu->env.current_instruction_pc;
    event->reg = reg;
    event->old_value = old_value;
    event->value = value;
    event->enabled = np560_audio_enabled(s);
    event->running = s->request_running;
    event->ticks = s->request_ticks;
    memcpy(event->writes, s->request_writes, sizeof(event->writes));
    memcpy(event->empty, s->request_without_write, sizeof(event->empty));
    memcpy(event->outside, s->writes_outside_request, sizeof(event->outside));
}

void np560_audio_write(NP560AudioState *s, unsigned reg, uint16_t value)
{
    /* Render the old held value up to the guest write, then latch the new
     * value. CPU, banked/IGNDS MMIO, and DTU use this one device boundary. */
    np560_audio_sync(s);
    if (reg == DMCU_SFR_DAC0 || reg == DMCU_SFR_DAC1) {
        s->sample[reg - DMCU_SFR_DAC0] = value;
        s->sample_writes[reg - DMCU_SFR_DAC0]++;
        if (!s->request_in_progress) {
            s->writes_outside_request[reg - DMCU_SFR_DAC0]++;
        }
    } else if (reg == DMCU_SFR_DACC) {
        uint16_t old_value = s->control;

        s->control = value;
        s->control_writes++;
        np560_audio_request_config(s);
        np560_audio_control_event(s, reg, old_value, value);
    } else if (reg == DMCU_SFR_AUDIO_PLL) {
        uint16_t old_value = s->pll;

        s->pll = value;
        np560_audio_request_config(s);
        np560_audio_control_event(s, reg, old_value, value);
    }
}

void np560_audio_reset(void *opaque)
{
    NP560AudioState *s = opaque;

    s->epoch_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    s->generation++;
    s->next_frame = 0;
    memset(s->pcm, 0, sizeof(s->pcm));
    memset(s->sample_writes, 0, sizeof(s->sample_writes));
    s->control_writes = 0;
    s->control_event_next = 0;
    memset(s->control_events, 0, sizeof(s->control_events));
    s->sample[0] = s->cpu->env.sfr[DMCU_SFR_DAC0];
    s->sample[1] = s->cpu->env.sfr[DMCU_SFR_DAC1];
    s->control = s->cpu->env.sfr[DMCU_SFR_DACC];
    s->pll = s->cpu->env.sfr[DMCU_SFR_AUDIO_PLL];
    ptimer_transaction_begin(s->request_timer);
    ptimer_stop(s->request_timer);
    ptimer_set_limit(s->request_timer, 1, 1);
    ptimer_transaction_commit(s->request_timer);
    s->request_running = false;
    s->request_in_progress = false;
    s->request_hz = 0;
    s->request_ticks = 0;
    memset(s->request_writes, 0, sizeof(s->request_writes));
    memset(s->request_without_write, 0, sizeof(s->request_without_write));
    memset(s->request_multiple_writes, 0, sizeof(s->request_multiple_writes));
    memset(s->writes_outside_request, 0, sizeof(s->writes_outside_request));
    np560_audio_request_config(s);
    timer_mod(s->timer, s->epoch_ns + NP560_AUDIO_TICK_NS);
}

void np560_audio_init(NP560AudioState *s, DMCUCPU *cpu)
{
    s->cpu = cpu;
    s->request_timer = ptimer_init(np560_audio_request_tick, s,
                                  PTIMER_POLICY_NO_COUNTER_ROUND_DOWN |
                                  PTIMER_POLICY_TRIGGER_ONLY_ON_DECREMENT);
    s->timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, np560_audio_tick, s);
    np560_audio_reset(s);
}

void np560_audio_destroy(NP560AudioState *s)
{
    timer_free(s->timer);
    ptimer_free(s->request_timer);
}

char *np560_audio_snapshot(NP560AudioState *s)
{
    uint64_t frames = MIN(s->next_frame, NP560_AUDIO_FRAMES);
    uint64_t first = s->next_frame - frames;
    unsigned offset = (first % NP560_AUDIO_FRAMES) * 4;
    unsigned first_bytes = MIN(frames * 4, sizeof(s->pcm) - offset);
    g_autofree uint8_t *linear = g_malloc(MAX(frames * 4, 1));
    g_autofree char *encoded = NULL;
    g_autoptr(GString) events = g_string_new(NULL);
    uint64_t event_first = s->control_event_next -
        MIN(s->control_event_next, NP560_AUDIO_CONTROL_EVENTS);
    uint64_t sequence;

    /* Read-only snapshot, not a dequeue or an emulation clock. Two clients
     * can read independently; slow clients can detect a gap from first_frame. */
    memcpy(linear, s->pcm + offset, first_bytes);
    memcpy(linear + first_bytes, s->pcm, frames * 4 - first_bytes);
    encoded = g_base64_encode(linear, frames * 4);
    for (sequence = event_first; sequence < s->control_event_next; sequence++) {
        NP560AudioControlEvent *event =
            &s->control_events[sequence % NP560_AUDIO_CONTROL_EVENTS];

        g_string_append_printf(events,
            "%s{\"sequence\":%" PRIu64 ",\"virtual_ns\":%" PRId64
            ",\"frame\":%" PRIu64 ",\"pc\":%u,\"reg\":%u,"
            "\"old_value\":%u,\"value\":%u,\"enabled\":%s,\"running\":%s,"
            "\"ticks\":%" PRIu64 ",\"writes\":[%" PRIu64 ",%" PRIu64 "],"
            "\"without_write\":[%" PRIu64 ",%" PRIu64 "],"
            "\"outside\":[%" PRIu64 ",%" PRIu64 "]}",
            sequence == event_first ? "" : ",", sequence, event->virtual_ns,
            event->frame, event->pc, event->reg, event->old_value, event->value,
            event->enabled ? "true" : "false", event->running ? "true" : "false",
            event->ticks, event->writes[0], event->writes[1],
            event->empty[0], event->empty[1], event->outside[0], event->outside[1]);
    }
    return g_strdup_printf(
        "{\"format\":\"s16le\",\"sample_rate\":%u,\"channels\":2,"
        "\"generation\":%" PRIu64 ",\"first_frame\":%" PRIu64 ","
        "\"next_frame\":%" PRIu64 ",\"enabled\":%s,"
        "\"registers\":[%u,%u,%u],\"writes\":[%" PRIu64 ",%" PRIu64
        ",%" PRIu64 "],\"request_clock\":{\"running\":%s,\"hz\":%u,"
        "\"pll\":%u,\"ticks\":%" PRIu64 "},"
        "\"request_delivery\":{\"writes\":[%" PRIu64 ",%" PRIu64 "],"
        "\"without_write\":[%" PRIu64 ",%" PRIu64 "],"
        "\"multiple_writes\":[%" PRIu64 ",%" PRIu64 "],"
        "\"writes_outside_request\":[%" PRIu64 ",%" PRIu64 "]},"
        "\"control_event_next\":%" PRIu64 ",\"control_events\":[%s],"
        "\"pcm\":\"%s\"}", NP560_AUDIO_RATE,
        s->generation, first, s->next_frame,
        np560_audio_enabled(s) ? "true" : "false",
        s->sample[0], s->sample[1], s->control,
        s->sample_writes[0], s->sample_writes[1], s->control_writes,
        s->request_running ? "true" : "false", s->request_hz, s->pll,
        s->request_ticks, s->request_writes[0], s->request_writes[1],
        s->request_without_write[0], s->request_without_write[1],
        s->request_multiple_writes[0], s->request_multiple_writes[1],
        s->writes_outside_request[0], s->writes_outside_request[1],
        s->control_event_next, events->str, encoded);
}
