/* NP560 Timer0/1/2: the periodic configuration used by the original driver.
 *
 * CN1916884A fig. 23 supplies the counter/comparator/reload architecture.
 * Original 08:3930/47A4 supplies clock division and period-minus-one.
 * Original 24:97AC/9A1E selects and starts T0, T1 or T2 for DAC transfers.
 * Other input/capture modes and the full clock tree remain unmodelled.
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "np560_timer.h"

#define TX_TON 0x8000u
#define TX_PERIODIC_CONFIG 0x0080u
#define TB_TBON 0x8000u

/* CN1916884A figures 24/25: TBON and 32768 >> B[3:0] Hz; selector 15
 * is unused. Original 32:DC20 writes TBC=8009, TBICR=0031. The three
 * words at 0494/0496/0498 are guest RAM, decremented by original 08:40D0,
 * not independent timer devices. */
static void np560_timebase_write(NP560TimersState *timers,
                                 uint16_t old_value, uint16_t value)
{
    NP560PeriodicTimerState *s = &timers->timebase;
    unsigned select = value & 15;
    bool enabled = (value & TB_TBON) && select != 15;

    if (!((old_value ^ value) & (TB_TBON | 15))) {
        return;
    }
    ptimer_transaction_begin(s->timer);
    ptimer_stop(s->timer);
    s->frequency = select != 15 ? 32768u >> select : 0;
    if (s->frequency) {
        ptimer_set_freq(s->timer, s->frequency);
    }
    ptimer_set_limit(s->timer, 1, 1);
    if (enabled) {
        /* Restart a complete period on enable/selector change. Phase on
         * reprogramming is not specified by the available document. */
        ptimer_run(s->timer, 0);
    } else if (value & TB_TBON) {
        s->unsupported_configs++;
        qemu_log_mask(LOG_UNIMP, "NP560 TBC unused selector %04x\n", value);
    }
    s->running = enabled;
    ptimer_transaction_commit(s->timer);
}

static uint32_t np560_timer_frequency(DMCUCPU *cpu)
{
    return dmcu_system_clock_hz(&cpu->env);
}

static uint16_t np560_periodic_timer_counter(NP560PeriodicTimerState *s)
{
    return (ptimer_get_limit(s->timer) - ptimer_get_count(s->timer)) & 0xffff;
}

uint16_t np560_timers_read(void *opaque, unsigned reg, uint16_t value)
{
    NP560TimersState *s = opaque;

    /* The counter address follows the three-register Tx/TxP/TxC layout;
     * unlike TxP/C, a shipped direct counter access is not yet identified. */
    if (reg >= DMCU_SFR_T0 && reg <= DMCU_SFR_T2 &&
        (reg - DMCU_SFR_T0) % 3 == 0) {
        return np560_periodic_timer_counter(
            &s->channel[(reg - DMCU_SFR_T0) / 3]);
    }
    return value;
}

static void np560_periodic_timer_write(NP560PeriodicTimerState *s, unsigned reg,
                                       uint16_t old_value, uint16_t value)
{
    unsigned counter_reg = DMCU_SFR_T0 + 3 * s->index;
    unsigned control = s->cpu->env.sfr[counter_reg + 2];
    uint64_t counter = np560_periodic_timer_counter(s);
    uint64_t limit = s->cpu->env.sfr[counter_reg + 1] + 1u;
    bool supported = (control & ~TX_TON) == TX_PERIODIC_CONFIG;
    bool enabled = (control & TX_TON) && supported;

    ptimer_transaction_begin(s->timer);
    if (reg == DMCU_SFR_PLL || reg == DMCU_SFR_CLKCON) {
        s->frequency = np560_timer_frequency(s->cpu);
        ptimer_set_freq(s->timer, s->frequency);
    }
    if (reg == counter_reg + 1) {
        ptimer_set_limit(s->timer, limit, 0);
        /* Preserve the up-counter. If the new compare is already behind
         * it, the 16-bit counter wraps before reaching that comparison. */
        ptimer_set_count(s->timer, limit > counter ? limit - counter :
                                                0x10000 + limit - counter);
    }
    if (reg == counter_reg) {
        ptimer_set_count(s->timer, limit > value ? limit - value :
                                              0x10000 + limit - value);
    }
    if (reg == counter_reg + 2) {
        if (enabled && !s->running) {
            /* The original periodic setup writes P then 8080 and expects
             * a complete first period. No caller-specific countdown edits. */
            ptimer_set_limit(s->timer, limit, 1);
            ptimer_run(s->timer, 0);
        } else if (!enabled && s->running) {
            ptimer_stop(s->timer);
        }
        if ((control & TX_TON) && !supported && old_value != value) {
            s->unsupported_configs++;
            qemu_log_mask(LOG_UNIMP, "NP560 T%uC mode %04x not modelled\n",
                          s->index, control);
        }
        s->running = enabled;
    }
    ptimer_transaction_commit(s->timer);
}

void np560_timers_write(void *opaque, unsigned reg,
                       uint16_t old_value, uint16_t value)
{
    NP560TimersState *s = opaque;
    unsigned i;

    if (reg == DMCU_SFR_PLL || reg == DMCU_SFR_CLKCON) {
        for (i = 0; i < NP560_PERIODIC_TIMERS; i++) {
            np560_periodic_timer_write(&s->channel[i], reg, old_value, value);
        }
    } else if (reg == DMCU_SFR_TBC) {
        np560_timebase_write(s, old_value, value);
    } else if (reg >= DMCU_SFR_T0 && reg <= DMCU_SFR_T2C) {
        np560_periodic_timer_write(&s->channel[(reg - DMCU_SFR_T0) / 3],
                                  reg, old_value, value);
    }
}

static void np560_periodic_timer_tick(void *opaque)
{
    NP560PeriodicTimerState *s = opaque;

    s->expirations++;
    /* RQ is a latch even while EN/IE masks delivery. It is cleared by the
     * CPU accepting the source, not by this timer or by host polling. */
    dmcu_irq_raise(s->cpu, 1 + s->index);
}

static void np560_timebase_tick(void *opaque)
{
    NP560PeriodicTimerState *s = opaque;

    s->expirations++;
    /* The oscillator produces RQ even with TBICR.EN or SOCR.IE clear.
     * CPU/DTU acceptance owns RQ clearing and priority/vector selection. */
    dmcu_irq_raise(s->cpu, 0);
}

void np560_timers_reset(void *opaque)
{
    NP560TimersState *timers = opaque;
    unsigned i;

    for (i = 0; i < NP560_PERIODIC_TIMERS; i++) {
        NP560PeriodicTimerState *s = &timers->channel[i];

        s->running = false;
        s->expirations = 0;
        s->unsupported_configs = 0;
        s->frequency = np560_timer_frequency(s->cpu);
        ptimer_transaction_begin(s->timer);
        ptimer_stop(s->timer);
        ptimer_set_freq(s->timer, s->frequency);
        ptimer_set_limit(s->timer, 1, 1);
        ptimer_transaction_commit(s->timer);
    }
    timers->timebase.running = false;
    timers->timebase.expirations = 0;
    timers->timebase.unsupported_configs = 0;
    timers->timebase.frequency = 32768;
    ptimer_transaction_begin(timers->timebase.timer);
    ptimer_stop(timers->timebase.timer);
    ptimer_set_freq(timers->timebase.timer, 32768);
    ptimer_set_limit(timers->timebase.timer, 1, 1);
    ptimer_transaction_commit(timers->timebase.timer);
}

void np560_timers_init(NP560TimersState *s, DMCUCPU *cpu)
{
    unsigned i;

    s->cpu = cpu;
    for (i = 0; i < NP560_PERIODIC_TIMERS; i++) {
        NP560PeriodicTimerState *channel = &s->channel[i];

        channel->cpu = cpu;
        channel->index = i;
        channel->timer = ptimer_init(np560_periodic_timer_tick, channel,
                                    PTIMER_POLICY_NO_COUNTER_ROUND_DOWN |
                                    PTIMER_POLICY_TRIGGER_ONLY_ON_DECREMENT);
    }
    s->timebase.cpu = cpu;
    s->timebase.timer = ptimer_init(np560_timebase_tick, &s->timebase,
                                  PTIMER_POLICY_NO_COUNTER_ROUND_DOWN |
                                  PTIMER_POLICY_TRIGGER_ONLY_ON_DECREMENT);
    np560_timers_reset(s);
}

void np560_timers_destroy(NP560TimersState *s)
{
    unsigned i;

    for (i = 0; i < NP560_PERIODIC_TIMERS; i++) {
        ptimer_free(s->channel[i].timer);
    }
    ptimer_free(s->timebase.timer);
}

char *np560_periodic_timer_state(NP560TimersState *timers, unsigned index)
{
    NP560PeriodicTimerState *s = &timers->channel[index];
    unsigned counter_reg = DMCU_SFR_T0 + 3 * index;

    return g_strdup_printf("RUNNING:%u HZ:%u COUNT:%04x PRELOAD:%04x "
                           "CONTROL:%04x ICR:%04x EXPIRED:%" PRIu64
                           " UNSUPPORTED_CONFIGS:%" PRIu64,
                           s->running, s->frequency,
                           np560_periodic_timer_counter(s),
                           s->cpu->env.sfr[counter_reg + 1],
                           s->cpu->env.sfr[counter_reg + 2],
                           s->cpu->env.sfr[DMCU_ICR_FIRST + 1 + index],
                           s->expirations, s->unsupported_configs);
}

char *np560_timebase_state(NP560TimersState *timers)
{
    NP560PeriodicTimerState *s = &timers->timebase;

    return g_strdup_printf("RUNNING:%u HZ:%u CONTROL:%04x ICR:%04x "
                           "EXPIRED:%" PRIu64 " UNSUPPORTED_CONFIGS:%" PRIu64,
                           s->running, s->frequency,
                           s->cpu->env.sfr[DMCU_SFR_TBC],
                           s->cpu->env.sfr[DMCU_ICR_FIRST],
                           s->expirations, s->unsupported_configs);
}
