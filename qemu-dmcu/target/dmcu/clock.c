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
#include "decode.h"
#include "clock-internal.h"
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
    /* EMCR boundaries are multiples of 64 KiB. Compare their high bytes
     * directly rather than rebuilding three 24-bit addresses for every
     * external data-bus transaction. The low address bits cannot change
     * which side of an aligned boundary the access falls on. */
    uint32_t high = address >> 16;
    uint32_t b1 = env->sfr[4] >> 8;
    uint32_t b2 = env->sfr[5] >> 8;
    uint32_t b3 = env->sfr[6] >> 8;

    if (b1 < 0x21u || b1 > b2 || b2 > b3) {
        return -1;
    }
    if (high >= b3) {
        return env->sfr[6] & 3;
    }
    if (high >= b2) {
        return env->sfr[5] & 3;
    }
    if (high >= b1) {
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
    /* AND/ANDB, pp.24-25: short encodings 1, long encodings A=1/B=2. */
    if ((op & 15) == 4 && (op >> 4) <= 11) {
        return op >= 0x60 ? ab : 1;
    }
    /* OR/ORB, pp.49-50: short encodings 1, long encodings A=1/B=2. */
    if ((op & 15) == 5 && (op >> 4) <= 11) {
        return op >= 0x60 ? ab : 1;
    }
    /* SUB/SUBB/SUBC/SUBCB and XOR/XORB, pp.51-56. */
    if (((op & 15) == 2 || (op & 15) == 3 || (op & 15) == 7) &&
        (op >> 4) <= 11) {
        return op >= 0x60 ? ab : 1;
    }
    /* CMP/CMPB, pp.95-96. No A6/B6 memory-destination encodings. */
    if ((op & 15) == 6 && (op >> 4) <= 9) {
        return op >= 0x60 ? ab : 1;
    }
    switch (op) {
    /* AJMP/ACALL cc=0, pp.18,79,88: no condition test, three/four
     * cycles respectively. Other conditions (and reserved high nibbles)
     * remain unknown until branch pipeline timing is reconciled. */
    case 0xac:
        return arg == 0 ? 3 : 0;
    case 0xbc:
        return arg == 0 ? 4 : 0;
    /* SJMP, p.91: unconditional far segmented jump, three cycles.
     * No A/B split is printed. Conditional branches remain unclassified.
     */
    case 0xad:
        return 3;
    /* RJMP cc=0, pp.18,90: no condition test, four cycles. Limit this
     * classification to the always-taken encoding; do not guess a cost
     * for the fall-through path of D1..DE from the single printed row.
     */
    case 0xd0:
        return 4;
    /* RET p.92 is exactly two cycles. RETI/RETS pp.93-94 say 2~3;
     * leave those and reserved subencodings unknown, not a guessed value. */
    case 0xc6:
        return arg == 0 ? 2 : 0;
    /* SL register, immediate and postincrement-memory forms, pp.63-64.
     * Count comes from a signed byte or imm4; cost is independent of it.
     * External operand wait states are charged separately on the data bus.
     */
    case 0x0c: case 0x2c: case 0x4c:
        return 1;
    /* SLOSB, SR and SROSB, pp.65-70: register-byte, immediate and
     * postincrement-memory encodings all take one documented cycle.
     * Signed counts reverse direction, not the timing classification.
     */
    case 0x1c: case 0x5c: case 0x3c:
    case 0x0d: case 0x4d: case 0x2d:
    case 0x1d: case 0x5d: case 0x3d:
        return 1;
    /* CMPD1/CMPI1/CMPI2 short forms and all long compare/update forms,
     * pp.97-100. Long forms are TWO cycles even for internal execution.
     * Short CMPD2 is printed as 2E (conflicting with LINK), not runtime 5E;
     * leave 5E unknown rather than silently correcting the source table.
     */
    case 0x4e: case 0x4f: case 0x5f:
        return 1;
    case 0x6e: case 0x6f: case 0x7e: case 0x7f:
    case 0x8e: case 0x8f: case 0x9e: case 0x9f:
        return 2;
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
    /* MUL/UMUL, pp.32-33. MUL's printed C0 0n row is narrower than
     * its two-operand syntax; do not infer timing for other C0 encodings.
     */
    case 0xc0:
        return arg < 16 ? 1 : 0;
    case 0xc1:
        return 1;
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

unsigned dmcu_decode_cycles(uint16_t word, uint32_t pc)
{
    return pc >= 0x010000u ?
        dmcu_documented_cycles(word, pc >= 0x210000u) : 0;
}

void dmcu_instruction_clock_step(CPUDMCUState *env, uint16_t word)
{
    dmcu_instruction_clock_step_decoded(env, word,
                                       dmcu_decode_cycles(word, env->pc));
}

void dmcu_instruction_clock_refresh(CPUDMCUState *env)
{
    uint32_t hz = dmcu_system_clock_hz(env);

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
    /* Publish only validated configurations. Resuming a rejected clock
     * must re-enter this check rather than treating it as cached. */
    env->instruction_clock_cached_pll = env->sfr[DMCU_SFR_PLL];
    env->instruction_clock_cached_clkcon = env->sfr[DMCU_SFR_CLKCON];
    if (env->instruction_clock_hz != hz) {
        env->instruction_clock_hz = hz;
        env->instruction_clock_period_fp = (1000000000ULL << 32) / hz;
    }
    /* Carry fractional ns across clock changes. Prior time is never
     * multiplied by a new frequency. The changing-CLKCON instruction was
     * charged at its incoming clock; the next uses the committed new one.
     * Period truncation is <2^-32 ns/instruction, not 1 ns/instruction.
     */
}
