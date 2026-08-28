/* DMCU TCG translator.
 *
 * Instructions remain in the auditable C helper, while short straight-line
 * sequences share one TCG block.  The helper reports whether the resulting
 * PC is the sequential successor, so taken branches and repeat back-edges
 * leave immediately.  Instructions which can touch the translated data bus
 * are always the final instruction in a block; this is required for QEMU
 * MMIO restart semantics and keeps device accesses precise.
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

/* Return true when the helper can reach address_space memory or a ROM/HLE
 * service.  Pure register and R11/R15 internal-SRAM instructions may safely
 * share a block.  This deliberately errs on the side of shorter blocks. */
static bool dmcu_may_do_io(uint16_t word)
{
    uint8_t op = word >> 8;
    uint8_t arg = word;
    unsigned hi = op >> 4;
    unsigned operation = op & 15;
    unsigned dr;
    unsigned sr;

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
    case 0x08: case 0x09:
    case 0x18: case 0x19:
    case 0x48: case 0x49:
    case 0x68: case 0x69:
        return false;
    case 0x0a: case 0x0b:
    case 0x1a: case 0x1b:
    case 0x58: case 0x59:
        return !dmcu_is_stack_pointer(arg >> 4);
    case 0x28: case 0x29:
    case 0x38: case 0x39:
        return !dmcu_is_stack_pointer(arg & 15);
    case 0x2a: case 0x2b:
    case 0x3a: case 0x3b:
    case 0x5a: case 0x5b:
        dr = arg >> 4;
        sr = arg & 15;
        return !dmcu_is_stack_pointer(dr) ||
               !dmcu_is_stack_pointer(sr);
    case 0x6a: case 0x6b:
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
        return !dmcu_is_stack_pointer(arg >> 4);
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
    db->max_insns = MIN(db->max_insns, 16);
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
    TCGv_i32 continue_block = tcg_temp_new_i32();
    uint16_t word0 = cpu_lduw_code(ctx->env, ctx->pc);
    uint16_t word1 = 0;
    unsigned size = 2;

    if (dmcu_is_32bit(word0)) {
        word1 = cpu_lduw_code(ctx->env, ctx->pc + 2);
        size = 4;
    }
    if (dmcu_may_do_io(word0)) {
        translator_io_start(db);
    }

    tcg_gen_movi_i32(cpu_pc, ctx->pc);
    gen_helper_exec(continue_block, tcg_env, tcg_constant_i32(word0),
                    tcg_constant_i32(word1));
    tcg_gen_brcondi_i32(TCG_COND_NE, continue_block, 0, sequential);
    tcg_gen_exit_tb(NULL, 0);
    gen_set_label(sequential);
    ctx->pc = (ctx->pc + size) & 0x00ffffffu;
    db->pc_next = ctx->pc;
}

static void dmcu_tr_tb_stop(DisasContextBase *db, CPUState *cs)
{
    if (db->is_jmp != DISAS_NORETURN) {
        tcg_gen_exit_tb(NULL, 0);
    }
}

static void dmcu_tr_disas_log(const DisasContextBase *db,
                              CPUState *cs, FILE *logfile)
{
    fprintf(logfile, "IN: %s\n", lookup_symbol(db->pc_first));
    target_disas(logfile, cs, db->pc_first, db->tb->size);
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
