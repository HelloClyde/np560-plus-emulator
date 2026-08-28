/* King Billion DMCU CPU model. */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/qemu-print.h"
#include "exec/exec-all.h"
#include "disas/dis-asm.h"
#include "tcg/debug-assert.h"
#include "cpu.h"

static void dmcu_cpu_set_pc(CPUState *cs, vaddr value)
{
    DMCUCPU *cpu = DMCU_CPU(cs);
    cpu->env.pc = value & 0x00ffffffu;
}

static vaddr dmcu_cpu_get_pc(CPUState *cs)
{
    return DMCU_CPU(cs)->env.pc & 0x00ffffffu;
}

static bool dmcu_cpu_has_work(CPUState *cs)
{
    return !cs->halted ||
           (cs->interrupt_request & (CPU_INTERRUPT_HARD |
                                     CPU_INTERRUPT_RESET));
}

static void dmcu_interrupt_push(DMCUCPU *cpu, uint32_t value)
{
    CPUDMCUState *env = &cpu->env;
    uint16_t address;
    uint16_t old_value;

    env->gpr[DMCU_SP] = (env->gpr[DMCU_SP] - 2) & 0xffff;
    address = env->gpr[DMCU_SP] & 0xffff;
    old_value = lduw_le_p(cpu->internal_data + address);
    dmcu_file_component_record_stack_write(
        env, address, address, old_value, value, 16, 1);
    dmcu_application_file_attach_record_frame_write(
        env, address, old_value, value, 16, 1);
    stw_le_p(cpu->internal_data + address, value);
}

static bool dmcu_cpu_exec_interrupt(CPUState *cs, int interrupt_request)
{
    DMCUCPU *cpu = DMCU_CPU(cs);
    CPUDMCUState *env = &cpu->env;
    uint16_t old_sp = env->gpr[DMCU_SP] & 0xffff;
    uint16_t old_fp = env->gpr[DMCU_FP] & 0xffff;
    uint32_t interrupted_pc = env->pc & 0x00ffffffu;
    uint32_t interrupted_psw = env->psw & 0xf;
    uint16_t interrupted_fp_word =
        lduw_le_p(cpu->internal_data + old_fp);
    unsigned int i;

    if (!(interrupt_request & CPU_INTERRUPT_HARD) || env->in_interrupt ||
        env->critical_count || !cpu->internal_data) {
        return false;
    }

    /*
     * LINK stores the caller FP at [FP].  A compiler epilogue may briefly
     * leave SP above that anchor while popping saved registers, immediately
     * before UNLINK resets SP to FP.  Accepting an interrupt at that single
     * boundary would make the architectural six-byte PSW/CS/PC frame overlap
     * [FP], destroying the caller frame (observed at the shipped 00:A4B8
     * UNLINK).  The DMCU advertises hardware stack under/overflow detection;
     * retain the pending request until the next instruction makes the frame
     * non-overlapping.  This is an address-independent CPU stack interlock.
     */
    if (old_sp >= 6 && old_fp &&
        old_fp < old_sp && old_fp + 2u > old_sp - 6u) {
        env->interrupt_frame_overlap_deferrals++;
        return false;
    }

    /* 32:C360 is the extension word of the reconstructed AC01 C36C branch
     * at 32:C35E.  Preserve the first occurrence so later timer traffic does
     * not erase the instruction boundary which produced an invalid resume. */
    if ((env->pc & 0x00ffffffu) == dmcu_code_address(0x32, 0xc360)) {
        if (!env->interrupt_midword_entries) {
            env->interrupt_first_midword_pc = env->pc & 0x00ffffffu;
            env->interrupt_first_midword_completed_pc =
                env->completed_instruction_pc & 0x00ffffffu;
            env->interrupt_first_midword_completed_next_pc =
                env->completed_instruction_next_pc & 0x00ffffffu;
            env->interrupt_first_midword_completed_word =
                env->completed_instruction_word;
            env->interrupt_first_midword_completed_ext =
                env->completed_instruction_ext;
        }
        env->interrupt_midword_entries++;
    }

    /* RETI restores PSW, CS, then PC.  Push the interrupted PC first so the
     * architectural frame has PSW on top, matching the shipped 08:40D0
     * timer vector and its synthetic callback return frame. */
    dmcu_interrupt_push(cpu, dmcu_code_pc(env->pc));
    dmcu_interrupt_push(cpu, dmcu_code_segment(env->pc));
    dmcu_interrupt_push(cpu, env->psw & 0xf);
    env->interrupt_frame_base = env->gpr[DMCU_SP] & 0xffff;
    env->interrupt_frame_expected_psw = interrupted_psw;
    env->interrupt_frame_expected_cs = dmcu_code_segment(interrupted_pc);
    env->interrupt_frame_expected_pc = dmcu_code_pc(interrupted_pc);
    env->interrupt_frame_watch_active = true;
    env->interrupt_foreground_fp_address = old_fp;
    env->interrupt_foreground_fp_expected = interrupted_fp_word;
    if (lduw_le_p(cpu->internal_data + old_fp) != interrupted_fp_word) {
        env->interrupt_foreground_fp_writes++;
        if (!env->interrupt_foreground_fp_first_entry) {
            env->interrupt_foreground_fp_first_entry =
                env->interrupt_entries + 1;
            env->interrupt_foreground_fp_first_entry_pc = interrupted_pc;
            env->interrupt_foreground_fp_first_write_pc = interrupted_pc;
            env->interrupt_foreground_fp_first_old = interrupted_fp_word;
            env->interrupt_foreground_fp_first_new =
                lduw_le_p(cpu->internal_data + old_fp);
            env->interrupt_foreground_fp_first_bits = 16;
            env->interrupt_foreground_fp_first_sp =
                env->gpr[DMCU_SP] & 0xffff;
            env->interrupt_foreground_fp_first_fp = old_fp;
        }
    }
    if (env->direct_menu_stack_watch_active &&
        !env->direct_menu_stack_escape_valid &&
        old_sp <= (env->direct_menu_stack_arm_sp & 0xffff) &&
        (env->gpr[DMCU_SP] & 0xffff) >
            (env->direct_menu_stack_arm_sp & 0xffff)) {
        dmcu_record_direct_menu_stack_escape(
            cpu, DMCU_DIRECT_MENU_STACK_ESCAPE_SP |
                 DMCU_DIRECT_MENU_STACK_ESCAPE_IRQ,
            env->pc, dmcu_code_address(0x08, 0x40d0), 0xffff, 0,
            old_sp, old_fp);
    }
    env->interrupt_last_entry_pc = env->pc & 0x00ffffffu;
    env->interrupt_last_entry_sp =
        (env->gpr[DMCU_SP] + 6) & 0xffff;
    env->irq_save_fp_watch_active = false;

    /*
     * CN1916884A specifies that an interrupt suspends the active repeat
     * source/counter context and resumes it after the service routine.  The
     * ISR must therefore execute with an inactive repeat engine.  Keeping a
     * single live context here allowed the foreground REPB state to steer
     * vector instructions and, eventually, to skip the far-fill boundary
     * fixup which protects the F100 SFR window.
     *
     * DMCU currently rejects nested hardware interrupts, so one architectural
     * shadow is sufficient.  This is CPU state, not firmware HLE.
     */
    env->interrupt_repeat_saved = env->repeat_count != 0;
    if (env->interrupt_repeat_saved) {
        env->interrupt_repeat_pc = env->repeat_pc;
        env->interrupt_repeat_end = env->repeat_end;
        env->interrupt_repeat_count = env->repeat_count;
        env->interrupt_repeat_block = env->repeat_block;
        env->interrupt_repeat_saves++;
        if (env->repeat_pc == dmcu_code_address(0x2e, 0x46bc) &&
            env->repeat_end == dmcu_code_address(0x2e, 0x46c0)) {
            env->far_copy_repeat_saves++;
            env->far_copy_repeat_entry_pc = env->pc & 0x00ffffffu;
            env->far_copy_repeat_saved_count = env->repeat_count;
            env->far_copy_repeat_saved_ds0 =
                env->sfr[DMCU_SFR_DS0] & 0x1ff;
            env->far_copy_repeat_saved_ds1 =
                env->sfr[DMCU_SFR_DS1] & 0x1ff;
            for (i = 0; i < 16; i++) {
                env->far_copy_repeat_saved_gpr[i] =
                    env->gpr[i] & 0xffff;
            }
        }
    }
    env->repeat_pc = 0;
    env->repeat_end = 0;
    env->repeat_count = 0;
    env->repeat_block = false;
    env->pc = dmcu_code_address(0x08, 0x40d0);
    env->in_interrupt = true;
    env->interrupt_entries++;
    cs->interrupt_request &= ~CPU_INTERRUPT_HARD;
    return true;
}

static void dmcu_cpu_synchronize_from_tb(CPUState *cs,
                                         const TranslationBlock *tb)
{
    tcg_debug_assert(!(cs->tcg_cflags & CF_PCREL));
    DMCU_CPU(cs)->env.pc = tb->pc & 0x00ffffffu;
}

static void dmcu_restore_state_to_opc(CPUState *cs,
                                      const TranslationBlock *tb,
                                      const uint64_t *data)
{
    DMCU_CPU(cs)->env.pc = data[0] & 0x00ffffffu;
}

static void dmcu_cpu_reset_hold(Object *obj)
{
    DMCUCPU *cpu = DMCU_CPU(obj);
    DMCUCPUClass *dcc = DMCU_CPU_GET_CLASS(cpu);
    CPUDMCUState *env = &cpu->env;

    if (dcc->parent_phases.hold) {
        dcc->parent_phases.hold(obj);
    }
    memset(env, 0, sizeof(*env));
    env->pc = cpu->reset_pc ? cpu->reset_pc : DMCU_PROGRAM_BASE;
    env->mask_rom03_present = cpu->mask_rom03_present;
    env->rom_hle_enabled = cpu->rom_hle_enabled;
    env->soc_rom_skeleton = cpu->soc_rom_skeleton;
    env->hle_ui_enabled = cpu->hle_ui_enabled;
    env->auxiliary_code_base = cpu->auxiliary_code_base;
    env->auxiliary_code_limit = cpu->auxiliary_code_limit;
    env->resident_rom_base = cpu->resident_rom_base;
    env->resident_rom_limit = cpu->resident_rom_limit;
    env->startup_context = cpu->startup_context;
    env->gpr[DMCU_SP] = 0xfffe;
    env->file_wrapper_active_slot = 0xffffu;
    env->lcd_foreground = 1;
    /* Bit 15 selects DS1.  Segment 1 keeps the reset stack in the upper
     * half of the 64 KiB internal X RAM. */
    env->sfr[DMCU_SFR_DS1] = 1;
}

static void dmcu_cpu_realizefn(DeviceState *dev, Error **errp)
{
    CPUState *cs = CPU(dev);
    DMCUCPU *cpu = DMCU_CPU(dev);
    DMCUCPUClass *dcc = DMCU_CPU_GET_CLASS(dev);
    Error *local_err = NULL;

    cpu_exec_realizefn(cs, &local_err);
    if (local_err) {
        error_propagate(errp, local_err);
        return;
    }
    cs->num_ases = 2;
    cpu_address_space_init(cs, DMCU_AS_DATA, "dmcu-data", cs->memory);
    cpu_address_space_init(cs, DMCU_AS_CODE, "dmcu-code",
                           cpu->code_memory ? cpu->code_memory : cs->memory);
    qemu_init_vcpu(cs);
    cpu_reset(cs);
    dcc->parent_realize(dev, errp);
}

static void dmcu_cpu_dump_state(CPUState *cs, FILE *f, int flags)
{
    CPUDMCUState *env = &DMCU_CPU(cs)->env;
    int i;

    qemu_fprintf(f, "PC=%02x:%04x PSW=%c%c%c%c SB=%04x SE=%02x\n",
                 dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                 env->psw & DMCU_PSW_Z ? 'Z' : '-',
                 env->psw & DMCU_PSW_C ? 'C' : '-',
                 env->psw & DMCU_PSW_N ? 'N' : '-',
                 env->psw & DMCU_PSW_V ? 'V' : '-',
                 env->shift_buffer & 0xffff, env->se & 0xff);
    for (i = 0; i < 16; i++) {
        qemu_fprintf(f, "R%-2d=%04x%s", i, env->gpr[i] & 0xffff,
                     (i & 3) == 3 ? "\n" : "  ");
    }
}

static void dmcu_cpu_disas_set_info(CPUState *cpu, disassemble_info *info)
{
    info->mach = 0;
    info->print_insn = dmcu_print_insn;
}

static ObjectClass *dmcu_cpu_class_by_name(const char *cpu_model)
{
    ObjectClass *oc;
    g_autofree char *typename = NULL;

    oc = object_class_by_name(cpu_model);
    if (oc && object_class_dynamic_cast(oc, TYPE_DMCU_CPU)) {
        return oc;
    }
    typename = g_strdup_printf(DMCU_CPU_TYPE_NAME("%s"), cpu_model);
    return object_class_by_name(typename);
}

void dmcu_cpu_list(void)
{
    GSList *list = object_class_get_list_sorted(TYPE_DMCU_CPU, false);
    GSList *item;

    qemu_printf("Available DMCU CPUs:\n");
    for (item = list; item; item = item->next) {
        qemu_printf("  %s\n", object_class_get_name(item->data));
    }
    g_slist_free(list);
}

#include "hw/core/sysemu-cpu-ops.h"

static int dmcu_asidx_from_attrs(CPUState *cs, MemTxAttrs attrs)
{
    return attrs.secure ? DMCU_AS_CODE : DMCU_AS_DATA;
}

static hwaddr dmcu_cpu_get_phys_page_attrs_debug(CPUState *cs, vaddr addr,
                                                  MemTxAttrs *attrs)
{
    *attrs = (MemTxAttrs) { .secure = 1 };
    return addr;
}

static const struct SysemuCPUOps dmcu_sysemu_ops = {
    .get_phys_page_attrs_debug = dmcu_cpu_get_phys_page_attrs_debug,
    .asidx_from_attrs = dmcu_asidx_from_attrs,
};

#include "hw/core/tcg-cpu-ops.h"

static const struct TCGCPUOps dmcu_tcg_ops = {
    .initialize = dmcu_translate_init,
    .synchronize_from_tb = dmcu_cpu_synchronize_from_tb,
    .restore_state_to_opc = dmcu_restore_state_to_opc,
    .cpu_exec_interrupt = dmcu_cpu_exec_interrupt,
    .tlb_fill = dmcu_cpu_tlb_fill,
};

static void dmcu_cpu_class_init(ObjectClass *oc, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    CPUClass *cc = CPU_CLASS(oc);
    DMCUCPUClass *dcc = DMCU_CPU_CLASS(oc);
    ResettableClass *rc = RESETTABLE_CLASS(oc);

    device_class_set_parent_realize(dc, dmcu_cpu_realizefn,
                                    &dcc->parent_realize);
    resettable_class_set_parent_phases(rc, NULL, dmcu_cpu_reset_hold, NULL,
                                       &dcc->parent_phases);
    cc->class_by_name = dmcu_cpu_class_by_name;
    cc->has_work = dmcu_cpu_has_work;
    cc->dump_state = dmcu_cpu_dump_state;
    cc->set_pc = dmcu_cpu_set_pc;
    cc->get_pc = dmcu_cpu_get_pc;
    cc->sysemu_ops = &dmcu_sysemu_ops;
    cc->disas_set_info = dmcu_cpu_disas_set_info;
    cc->tcg_ops = &dmcu_tcg_ops;
}

static const TypeInfo dmcu_cpu_types[] = {
    {
        .name = TYPE_DMCU_CPU,
        .parent = TYPE_CPU,
        .instance_size = sizeof(DMCUCPU),
        .instance_align = __alignof(DMCUCPU),
        .class_size = sizeof(DMCUCPUClass),
        .class_init = dmcu_cpu_class_init,
        .abstract = true,
    }, {
        .name = TYPE_DMCU_V1_CPU,
        .parent = TYPE_DMCU_CPU,
    },
};

DEFINE_TYPES(dmcu_cpu_types)
