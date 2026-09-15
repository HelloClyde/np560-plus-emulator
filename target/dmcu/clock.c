/* DMCU system clock and experimental instruction-time integration.
 *
 * Partial documented instruction costs and external data wait states.
 * NOT a complete machine-cycle model: instruction prefetch, pipeline/bus
 * overlap, interrupt entry and HLE service costs remain unmodelled. Unknown
 * opcode costs retain the old one-cycle estimate with explicit counters.
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "cpu.h"
#include "exec/exec-all.h"
#include "sysemu/cpu-timers.h"

uint32_t dmcu_system_clock_hz(const CPUDMCUState *env)
{
    unsigned pll = env->sfr[DMCU_SFR_PLL];
    unsigned select = env->sfr[DMCU_SFR_CLKCON] & 0x1f;

    if (select & 0x10) {
        return 32768;
    }
    if (pll & 0x8000) {
        /* Original frequency-to-preload calculation already used by
         * Timer0/1/2. Lock/transients and alternate modes remain unknown. */
        unsigned multiplier = ((pll & 0x1fff) >> 5) + 1;
        unsigned divisor = (pll & 0x1f) + 1;

        return (4000000u * multiplier / divisor) >> (select & 7);
    }
    /* CN1916884A fig.22, the published non-PLL CLKSEL table. */
    return (select & 8 ? 16384000u : 24576000u) >> (select & 7);
}

/* CN1916884A pp.15,132,138-139: boundaries are lower-inclusive; the WS in
 * an EMCR applies ABOVE that EMCR's boundary, not to the preceding region.
 * Do not sort malformed boundaries or invent a reset configuration.
 */
static int dmcu_external_waits(const CPUDMCUState *env, uint32_t address)
{
    uint32_t b1 = (env->sfr[4] & 0xff00u) << 8;
    uint32_t b2 = (env->sfr[5] & 0xff00u) << 8;
    uint32_t b3 = (env->sfr[6] & 0xff00u) << 8;

    if (b1 < 0x210000u || b1 > b2 || b2 > b3) {
        return -1;
    }
    if (address >= b3) {
        return env->sfr[6] & 3;
    }
    if (address >= b2) {
        return env->sfr[5] & 3;
    }
    if (address >= b1) {
        return env->sfr[4] & 3;
    }
    return (env->sfr[DMCU_SFR_SOCR] >> 6) & 3;
}

/* Visually checked rows, not an automatically trusted OCR table. A/B in
 * p.18 means internal ROM/Flash vs external instruction storage, BOTH with
 * internal RAM/register operands. External operand overlap is not covered.
 * Return zero for a cost not yet established. In particular the published
 * UDIVL row itself says '?'; conditional branch pipeline text and latency
 * tables must be reconciled before selecting taken/not-taken costs.
 */
static unsigned dmcu_documented_cycles(uint16_t word, bool external)
{
    unsigned op = word >> 8;
    unsigned arg = word & 0xff;
    unsigned ab = external ? 2 : 1;

    /* ADD/ADDB/ADDC/ADDCB, pp.20-23. */
    if ((op & 15) <= 1 && (op >> 4) <= 11) {
        return op >= 0x60 ? ab : 1;
    }
    switch (op) {
    /* MOV/MOVB, pp.102-103. */
    case 0x08: case 0x09: case 0x0a: case 0x0b:
    case 0x1a: case 0x1b: case 0x28: case 0x29:
    case 0x2a: case 0x2b: case 0x38: case 0x39:
    case 0x3a: case 0x3b: case 0x48: case 0x49:
    case 0x58: case 0x59: case 0x5a: case 0x5b:
        return 1;
    case 0x68: case 0x69: case 0x6a: case 0x6b:
    case 0x78: case 0x79: case 0x88: case 0x89:
    case 0xa8: case 0xa9:
        return ab;
    case 0x8a: case 0x8b:
        return arg < 16 ? ab : 0;
    /* EXCH, MOVSE/MOVZE, pp.101,104-105. */
    case 0x0e: case 0x18: case 0x19:
        return 1;
    case 0x98: case 0x99: case 0xb8: case 0xb9:
        return 2;
    /* DIV/DIVL are 4, UDIV is 1; UDIVL is UNKNOWN, pp.28-31. */
    case 0xc2: case 0xc4:
        return arg < 16 ? 4 : 0;
    case 0xc3:
        return arg < 16 ? 1 : 0;
    /* PUSH/POP, LINK, NOP, CRIT/IGNDS, pp.113-119. */
    case 0x1f: case 0x2e:
        return 1;
    case 0xc7:
        return arg == 0 ? 1 : 0;
    case 0x3f:
        return (arg <= 3 || (arg >= 0x10 && arg <= 0x13)) ? 1 : 0;
    /* Repeat SETUP costs only, pp.120-123. No guessed prefetch cache. */
    case 0xbf:
        return arg == 0 ? ab : 0;
    case 0xcf:
        return arg < 16 ? 1 : 0;
    case 0xae:
        return ab;
    case 0xaf:
        return arg < 16 ? ab : 0;
    default:
        return 0;
    }
}

/* Preserve the incoming instruction clock, including accesses which write
 * PLL/CLKCON part-way through an instruction. Waits do not add instructions.
 */
static void dmcu_clock_charge(CPUDMCUState *env, unsigned cycles, bool first)
{
    uint64_t total = env->instruction_clock_period_fp * cycles +
                     env->instruction_clock_fraction;
    uint64_t ns = total >> 32;

    env->instruction_clock_fraction = total;
    env->instruction_clock_ns += ns;
    env->instruction_clock_cycles += cycles;
    icount_account_extra_ns(env_cpu(env), ns - (first ? 1 : 0));
}

void dmcu_instruction_clock_data(CPUDMCUState *env, uint32_t physical)
{
    int waits;

    /* Only actual instruction data-bus transactions call this, not debug
     * reads, DTU transactions, or the stack/Y internal address space.
     */
    if (!env->instruction_clock_data_active || physical < 0x210000u) {
        return;
    }
    env->instruction_clock_external_data++;
    waits = dmcu_external_waits(env, physical);
    if (waits < 0) {
        env->instruction_clock_unknown_map++;
    } else if (waits) {
        env->instruction_clock_data_waits += waits;
        dmcu_clock_charge(env, waits, false);
    }
}

void dmcu_instruction_clock_step(CPUDMCUState *env, uint16_t word)
{
    uint32_t hz = dmcu_system_clock_hz(env);
    unsigned cycles;

    env->instruction_clock_data_active = false;

    /* No pretend running clock in idle/sleep, and no sub-ns rate rounding
     * disguised as cycle accuracy. These require separate implementations.
     * Halt this explicit experimental mode with a retained diagnostic.
     */
    if ((env->sfr[DMCU_SFR_CLKCON] & 0xc0) || hz > 1000000000u) {
        CPUState *cs = env_cpu(env);

        env->instruction_clock_fault = (env->sfr[DMCU_SFR_CLKCON] & 0xc0)
                                      ? 1 : 2;
        qemu_log_mask(LOG_UNIMP,
            "DMCU instruction clock unsupported CLKCON=%04x Hz=%u at %06x\n",
            env->sfr[DMCU_SFR_CLKCON], hz, env->pc);
        cs->halted = 1;
        cs->exception_index = EXCP_HLT;
        cpu_loop_exit(cs);
    }
    if (env->instruction_clock_hz != hz) {
        env->instruction_clock_hz = hz;
        env->instruction_clock_period_fp = (1000000000ULL << 32) / hz;
    }
    /* Carry fractional ns across clock changes. Prior time is never
     * multiplied by a new frequency. The changing-CLKCON instruction was
     * charged at its incoming clock; the next uses the committed new one.
     * Period truncation is <2^-32 ns/instruction, not 1 ns/instruction.
     */
    /* Fig.2: 01:0000..20:FFFF is internal ROM/Flash. SRAM execution is
     * supported by the emulator, but not assigned the ROM's A timing.
     */
    cycles = env->pc >= 0x010000u ?
             dmcu_documented_cycles(word, env->pc >= 0x210000u) : 0;
    if (!cycles) {
        env->instruction_clock_unknown++;
        env->instruction_clock_last_unknown = word;
        cycles = 1;
    }
    env->instruction_clock_count++;
    /* QEMU's single-instruction prologue has already charged one ns. */
    dmcu_clock_charge(env, cycles, true);
}
