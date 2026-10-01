/* Per-instruction clock hot path. No elapsed time or IRQ boundaries batched. */
#ifndef DMCU_CLOCK_INTERNAL_H
#define DMCU_CLOCK_INTERNAL_H

#include "cpu.h"
#include "sysemu/cpu-timers.h"

void dmcu_instruction_clock_refresh(CPUDMCUState *env);

/* Preserve the incoming clock even when the instruction writes PLL/CLKCON. */
static inline QEMU_ALWAYS_INLINE void dmcu_clock_charge(
    CPUDMCUState *env, unsigned cycles, bool first)
{
    uint64_t total = env->instruction_clock_period_fp * cycles +
                     env->instruction_clock_fraction;
    uint64_t ns = total >> 32;
    uint64_t extra_ns = ns - (first ? 1 : 0);
    CPUState *cpu = env_cpu(env);

    env->instruction_clock_fraction = total;
    env->instruction_clock_ns += ns;
    env->instruction_clock_cycles += cycles;
    /* The machine permits this clock only with a single vCPU, fixed
     * icount shift=0 and no replay. Usually the current decrementer slice
     * covers the charge. Keep the exact vCPU-local update inline in that
     * case; the generic path retains budget rollover and overflow checks. */
    if (likely(cpu->icount_pending_extra_ns <= INT64_MAX &&
               extra_ns < cpu->neg.icount_decr.u16.low &&
               extra_ns <= INT64_MAX - cpu->icount_pending_extra_ns)) {
        cpu->icount_pending_extra_ns += extra_ns;
        cpu->neg.icount_decr.u16.low -= extra_ns;
        cpu->icount_budget -= extra_ns;
    } else {
        icount_account_extra_ns(cpu, extra_ns);
    }
}

static inline QEMU_ALWAYS_INLINE void dmcu_instruction_clock_step_decoded(
    CPUDMCUState *env, uint16_t word, unsigned cycles)
{
    env->instruction_clock_data_active = false;
    /* Registers, not write notifications: covers reset and restore too.
     * Unsupported configurations never return from refresh, so there is
     * no cached unsupported configuration that can bypass its checks. */
    if (!env->instruction_clock_hz ||
        env->instruction_clock_cached_pll != env->sfr[DMCU_SFR_PLL] ||
        env->instruction_clock_cached_clkcon != env->sfr[DMCU_SFR_CLKCON]) {
        dmcu_instruction_clock_refresh(env);
    }
    if (!cycles) {
        env->instruction_clock_unknown++;
        env->instruction_clock_unknown_sram += env->pc < 0x010000u;
        if (env->instruction_clock_profile_enabled && env->pc >= 0x010000u) {
            env->instruction_clock_unknown_opcodes[word >> 8]++;
        }
        env->instruction_clock_last_unknown = word;
        cycles = 1;
    }
    if (unlikely(env->instruction_clock_profile_enabled)) {
        env->instruction_clock_executed_opcodes[word >> 8]++;
        env->instruction_clock_executed_words[word]++;
    }
    env->instruction_clock_count++;
    /* The single-instruction TCG prologue already charged one ns. */
    dmcu_clock_charge(env, cycles, true);
}

#endif
