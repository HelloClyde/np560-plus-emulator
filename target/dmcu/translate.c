/* DMCU TCG translator.
 *
 * Instructions remain in the auditable C helper, while short straight-line
 * sequences share one TCG block.  The helper reports whether the resulting
 * PC is the sequential successor, a safe dynamic successor, or requires
 * CPU arbitration. Taken branches and repeat back-edges leave the current
 * block. Instructions which can touch the translated data bus
 * are always the final instruction in a block; this is required for QEMU
 * MMIO restart semantics and keeps device accesses precise. Internal SRAM
 * writes also end the block so self-modified following code is retranslated.
 */

#include "qemu/osdep.h"
#include "cpu.h"
#include "tcg/tcg.h"
#include "tcg/tcg-op.h"
#include "exec/exec-all.h"
#include "exec/cpu_ldst.h"
#include "exec/helper-proto.h"
#include "exec/helper-gen.h"
#include "exec/log.h"
#include "exec/translator.h"

#define HELPER_H "helper.h"
#include "exec/helper-info.c.inc"
#undef HELPER_H

static TCGv cpu_pc;

typedef struct DisasContext {
    DisasContextBase base;
    CPUDMCUState *env;
    uint32_t pc;
    bool last_insn_wraps;
} DisasContext;

static bool dmcu_is_32bit(uint16_t word)
{
    uint8_t op = word >> 8;
    uint8_t arg = word;
    uint8_t hi = op >> 4;
    uint8_t lo = op & 0x0f;

    if (lo <= 7 && hi >= 6 && hi <= 11) {
        return true;
    }
    switch (op) {
    case 0x68: case 0x69: case 0x6a: case 0x6b:
    case 0x6c: case 0x6d: case 0x6e: case 0x6f:
    case 0x78: case 0x79: case 0x7c: case 0x7d:
    case 0x7e: case 0x7f:
    case 0x88: case 0x89: case 0x8a: case 0x8b:
    case 0x8c: case 0x8d: case 0x8e: case 0x8f:
    case 0x98: case 0x99: case 0x9a: case 0x9b:
    case 0x9c: case 0x9d: case 0x9e: case 0x9f:
    case 0xa8: case 0xa9: case 0xac: case 0xad:
    case 0xae: case 0xaf:
    case 0xb8: case 0xb9: case 0xbc: case 0xbd:
    case 0xbe:
        return true;
    case 0xbf:
        return arg == 0;
    default:
        return false;
    }
}

static bool dmcu_is_stack_pointer(unsigned reg)
{
    return reg == DMCU_FP || reg == DMCU_SP;
}

/* Return true when the helper can write executable RAM, reach board MMIO or
 * a ROM/HLE service. Only read-only R11/R15 accesses may share a block;
 * invalidating a TB during a store does not abort that TB's execution.
 * This deliberately errs on the side of shorter blocks. */
static bool dmcu_may_do_io(uint16_t word, uint16_t ext)
{
    uint8_t op = word >> 8;
    uint8_t arg = word;
    unsigned hi = op >> 4;
    unsigned operation = op & 15;

    /* Direct SFR/bit instructions can now operate clocked devices without
     * going through data_read/write. Account their instruction before any
     * virtual-clock read or timer transaction (required by -icount). */
    if (((hi == 6 || hi == 7) &&
         (operation <= 9 || operation >= 14) &&
         dmcu_sfr_has_timing(arg)) ||
        (op >= 0xe0 && dmcu_sfr_has_timing(arg)) ||
        (op == 0x1f && dmcu_sfr_has_timing(arg & 0x7f)) ||
        ((op == 0x6c || op == 0x6d || op == 0x7c || op == 0x7d ||
          op == 0x8c || op == 0x8d) &&
         (dmcu_sfr_has_timing(arg) || dmcu_sfr_has_timing(ext >> 8)))) {
        return true;
    }
    if (operation <= 7) {
        if (hi <= 1 || (hi >= 4 && hi <= 7)) {
            return false;
        }
        if (hi == 2 || hi == 3) {
            return !dmcu_is_stack_pointer(8 + (arg & 7));
        }
        return true;
    }

    switch (op) {
    case 0x3f:
        return arg == 0xff; /* RESET exits to the system/device boundary. */
    case 0x08: case 0x09:
    case 0x18: case 0x19:
    case 0x48: case 0x49:
    case 0x68: case 0x69:
        return false;
    case 0x0a: case 0x0b:
    case 0x1a: case 0x1b:
    case 0x58: case 0x59:
        return true;
    case 0x28: case 0x29:
    case 0x38: case 0x39:
        return !dmcu_is_stack_pointer(arg & 15);
    case 0x2a: case 0x2b:
    case 0x3a: case 0x3b:
    case 0x5a: case 0x5b:
        return true;
    case 0x6a: case 0x6b:
        return true;
    case 0x78: case 0x79:
        return !dmcu_is_stack_pointer(arg & 15);
    case 0x88: case 0x89:
    case 0x8a: case 0x8b:
    case 0x98: case 0x99:
    case 0xa8: case 0xa9:
    case 0xb8: case 0xb9:
        return true;
    case 0x2c: case 0x2d:
    case 0x3c: case 0x3d:
    case 0x2e: /* LINK pushes FP. */
    case 0x0f: /* TRAP writes an internal interrupt frame. */
        return true;
    case 0x1f:
        return !(arg & 0x80); /* PUSH SFR; POP only reads SRAM. */
    case 0x0c: case 0x0d: case 0x1c: case 0x1d:
    case 0x4a: case 0x4b: case 0x4c: case 0x4d:
    case 0x5c: case 0x5d:
    case 0xc8: case 0xc9: case 0xca: case 0xcb:
        return false;
    case 0x8e: case 0x8f: case 0x9e: case 0x9f:
        return true;
    case 0x1e:
        return ((arg >> 4) & 1) &&
               !dmcu_is_stack_pointer(arg & 15);
    case 0xbe:
        /* Memory MAC reads the X data bus and may also write it via .m.
         * It must finish the TB even when the current operands are RAM. */
        return (arg & 0x30) == 0;
    case 0x9a: case 0x9b: case 0x9c: case 0x9d:
    case 0xac: case 0xad: case 0xbc: case 0xbd:
    case 0xcc: case 0xcd: case 0xce:
    case 0xd0: case 0xd1: case 0xd2: case 0xd3:
    case 0xd4: case 0xd5: case 0xd6: case 0xd7:
    case 0xd8: case 0xd9: case 0xda: case 0xdb:
    case 0xdc: case 0xdd: case 0xde:
    case 0xc6:
        return true;
    default:
        return false;
    }
}

void dmcu_translate_init(void)
{
    cpu_pc = tcg_global_mem_new_i32(tcg_env,
                                    offsetof(CPUDMCUState, pc), "pc");
}

static void dmcu_tr_init_disas_context(DisasContextBase *db,
                                       CPUState *cs)
{
    DisasContext *ctx = container_of(db, DisasContext, base);
    ctx->env = cpu_env(cs);
    ctx->pc = db->pc_first;
    ctx->last_insn_wraps = false;
    /* The generic prologue charges the WHOLE TB's instruction count. Our
     * C executor can leave after any instruction (REP/REPB back-edges,
     * CRIT/IGNDS expiry, SFR changes, strict-ROM/unsupported halts), not
     * only after statically decoded branches. Such an exit used to charge
     * the unexecuted tail again on the successor TB. A 38-instruction
     * repeat fixture was charged 74, before adding a longer dead tail.
     *
     * Keep icount precise at the architectural instruction boundary,
     * including helper longjmps and virtual-clock device accesses. Ordinary
     * execution retains the existing 16-instruction linked blocks. This
     * counts instructions, NOT DMCU hardware cycles; numeric shift and
     * QEMU's adaptive shift are not a model of PLL/CLKCON or bus waits.
     */
    db->max_insns = MIN(db->max_insns,
                        (tb_cflags(db->tb) & CF_USE_ICOUNT) ? 1 : 16);
}

static void dmcu_tr_tb_start(DisasContextBase *db, CPUState *cs)
{
}

static void dmcu_tr_insn_start(DisasContextBase *db, CPUState *cs)
{
    DisasContext *ctx = container_of(db, DisasContext, base);
    tcg_gen_insn_start(ctx->pc);
}

static void dmcu_tr_translate_insn(DisasContextBase *db, CPUState *cs)
{
    DisasContext *ctx = container_of(db, DisasContext, base);
    TCGLabel *sequential = gen_new_label();
    TCGLabel *lookup = gen_new_label();
    TCGv_i32 exec_result = tcg_temp_new_i32();
    /* Register every fetched page with the TB, including an extension word
     * on the next page. A raw cpu_lduw_code() can read that word without
     * linking its RAM page to this TB, so a guest write leaves stale code. */
    uint16_t word0 = translator_lduw(ctx->env, db, ctx->pc);
    uint16_t word1 = 0;
    unsigned size = 2;
    bool wrapped_extension = false;
    TCGv_i32 extension;

    if (dmcu_is_32bit(word0)) {
        if (dmcu_code_pc(ctx->pc) == 0xfffe) {
            /* Only the opcode belongs to this contiguous TB extent.
             * Its extension is fetched at run time from the original CS's
             * first page, not from the adjacent segment or an untracked
             * translation-time read. End the TB at this page boundary. */
            wrapped_extension = true;
        } else {
            word1 = translator_lduw(ctx->env, db, ctx->pc + 2);
            size = 4;
        }
    }
    if (wrapped_extension || dmcu_may_do_io(word0, word1)) {
        translator_io_start(db);
    }
    ctx->last_insn_wraps = wrapped_extension;

    tcg_gen_movi_i32(cpu_pc, ctx->pc);
    if (wrapped_extension) {
        extension = tcg_temp_new_i32();
        gen_helper_fetch_extension(extension, tcg_env,
                                   tcg_constant_i32(ctx->pc));
    } else {
        extension = tcg_constant_i32(word1);
    }
    gen_helper_exec(exec_result, tcg_env, tcg_constant_i32(word0),
                    extension);
    tcg_gen_brcondi_i32(TCG_COND_EQ, exec_result, DMCU_EXEC_NEXT, sequential);
    tcg_gen_brcondi_i32(TCG_COND_EQ, exec_result, DMCU_EXEC_LOOKUP, lookup);
    tcg_gen_exit_tb(NULL, 0);
    gen_set_label(lookup);
    tcg_gen_lookup_and_goto_ptr();
    gen_set_label(sequential);
    /* This is the linear TB byte extent, not the architectural PC. The
     * helper advances PC within CS. Even FF:FFFE must keep a positive TB
     * size; no following page is translated after the boundary below. */
    ctx->pc += size;
    db->pc_next = ctx->pc;
    /* Only one instruction may straddle a page boundary. Do not translate
     * another instruction on page 2 speculatively; page tracking and MMIO
     * fallback remain the generic translator's responsibility. */
    if ((ctx->pc ^ db->pc_first) & TARGET_PAGE_MASK) {
        db->is_jmp = DISAS_TOO_MANY;
    }
}

static void dmcu_tr_tb_stop(DisasContextBase *db, CPUState *cs)
{
    DisasContext *ctx = container_of(db, DisasContext, base);

    if (db->is_jmp != DISAS_NORETURN) {
        /* Only the helper's sequential/safe result reaches this point.
         * Its zero result still exits directly to cpu_exec above, including
         * CRIT/IGNDS expiry, IRQ state changes and bank switches. Do not
         * chain those arbitration edges. Safe dynamic successors use the
         * separate lookup path above, not this sequential destination.
         *
         * Keep MMIO and executable-memory stores as the last instruction
         * of their TB. Chaining a separate successor uses QEMU's standard
         * code invalidation and next-TB interrupt/icount entry checks; it
         * does not run the next instruction inside an invalidated block.
         * The helper has already committed the architectural successor PC.
         */
        uint32_t next = dmcu_code_advance(db->pc_first,
                                          db->pc_next - db->pc_first);

        if (!ctx->last_insn_wraps && translator_use_goto_tb(db, next)) {
            tcg_gen_goto_tb(0);
            tcg_gen_exit_tb(db->tb, 0);
        } else {
            /* A wrapped wide instruction fetched its extension at run
             * time; its linear TB extent does not include that word.
             * Lookup uses the actual env->pc, never a guessed linear PC.
             * CF_NO_GOTO_PTR (debug single-step/replay) is handled here.
             */
            tcg_gen_lookup_and_goto_ptr();
        }
    }
}

static void dmcu_tr_disas_log(const DisasContextBase *db,
                              CPUState *cs, FILE *logfile)
{
    const DisasContext *ctx = container_of(db, DisasContext, base);

    fprintf(logfile, "IN: %s\n", lookup_symbol(db->pc_first));
    /* The logger prints the complete final instruction; its extension may
     * wrap into CS:0000 although it is not part of the tracked TB extent. */
    target_disas(logfile, cs, db->pc_first,
                 db->tb->size + (ctx->last_insn_wraps ? 2 : 0));
}

static const TranslatorOps dmcu_tr_ops = {
    .init_disas_context = dmcu_tr_init_disas_context,
    .tb_start = dmcu_tr_tb_start,
    .insn_start = dmcu_tr_insn_start,
    .translate_insn = dmcu_tr_translate_insn,
    .tb_stop = dmcu_tr_tb_stop,
    .disas_log = dmcu_tr_disas_log,
};

void gen_intermediate_code(CPUState *cs, TranslationBlock *tb, int *max_insns,
                           target_ulong pc, void *host_pc)
{
    DisasContext dc = { };
    translator_loop(cs, tb, max_insns, pc, host_pc, &dmcu_tr_ops, &dc.base);
}
