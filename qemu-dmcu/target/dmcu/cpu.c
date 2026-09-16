/* King Billion DMCU CPU model. */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/qemu-print.h"
#include "exec/exec-all.h"
#include "exec/memory.h"
#include "disas/dis-asm.h"
#include "tcg/debug-assert.h"
#include "cpu.h"

static void dmcu_cpu_set_pc(CPUState *cs, vaddr value)
{
    cpu_env(cs)->pc = value & 0x00ffffffu;
}

static vaddr dmcu_cpu_get_pc(CPUState *cs)
{
    return cpu_env(cs)->pc & 0x00ffffffu;
}

static bool dmcu_cpu_has_work(CPUState *cs)
{
    return !cs->halted ||
           (cs->interrupt_request & (CPU_INTERRUPT_HARD |
                                     CPU_INTERRUPT_RESET));
}

/* CN1916884A, figures 7B, 12, 13 and 16. An ED source with a nonzero
 * channel count belongs to the DTU. A zero count requests CPU service at
 * priority 3, regardless of the PRI bits used as channel number.
 * Equal-priority source order is provisionally ascending vector; the
 * available specification only defines selection of the highest priority. */
static unsigned dmcu_irq_priority(unsigned icr)
{
    return icr & DMCU_ICR_ED ? 3 : (icr & DMCU_ICR_PRI) >> 4;
}

static int dmcu_irq_select(CPUDMCUState *env)
{
    unsigned psr = dmcu_sfr_read_word(env, DMCU_SFR_PSW);
    unsigned threshold = (psr & DMCU_PSR_CPRI) >> 12;
    int selected = -1;
    unsigned selected_priority = 0;
    unsigned source;

    if (!(env->sfr[DMCU_SFR_SOCR] & DMCU_SOCR_IE)) {
        return -1;
    }
    for (source = 0; source < DMCU_ICR_COUNT; source++) {
        unsigned icr = env->sfr[DMCU_ICR_FIRST + source];
        unsigned channel = (icr & DMCU_ICR_PRI) >> 4;
        unsigned priority = dmcu_irq_priority(icr);

        if ((icr & (DMCU_ICR_EN | DMCU_ICR_RQ)) !=
                (DMCU_ICR_EN | DMCU_ICR_RQ) ||
            ((icr & DMCU_ICR_ED) &&
             (env->sfr[DMCU_DTUC_FIRST + channel] & DMCU_DTUC_COUNT)) ||
            priority < threshold ||
            ((psr & DMCU_PSR_CIRQ) && priority == threshold)) {
            continue;
        }
        if (selected < 0 || priority > selected_priority) {
            selected = source;
            selected_priority = priority;
        }
    }
    return selected;
}

/* Boolean work check does not need to select the highest-priority vector.
 * Inspect each latched source once, rather than scanning the whole ICR bank
 * again for DTU work after a negative CPU-only selection. Actual CPU entry
 * continues to use dmcu_irq_select, including its original tie order. */
static bool dmcu_irq_or_dtu_pending(CPUDMCUState *env)
{
    unsigned psr = dmcu_sfr_read_word(env, DMCU_SFR_PSW);
    unsigned threshold = (psr & DMCU_PSR_CPRI) >> 12;
    bool enabled = env->sfr[DMCU_SFR_SOCR] & DMCU_SOCR_IE;

    for (unsigned source = 0; source < DMCU_ICR_COUNT; source++) {
        unsigned icr = env->sfr[DMCU_ICR_FIRST + source];
        unsigned priority;

        if ((icr & (DMCU_ICR_EN | DMCU_ICR_RQ)) !=
                (DMCU_ICR_EN | DMCU_ICR_RQ)) {
            continue;
        }
        if ((icr & DMCU_ICR_ED) &&
            (env->sfr[DMCU_DTUC_FIRST + ((icr & DMCU_ICR_PRI) >> 4)] &
             DMCU_DTUC_COUNT)) {
            if (!(env->dtu_fault_sources & (1u << source))) {
                return true;
            }
            continue;
        }
        priority = dmcu_irq_priority(icr);
        if (enabled && priority >= threshold &&
            !((psr & DMCU_PSR_CIRQ) && priority == threshold)) {
            return true;
        }
    }
    return false;
}

/* CPU-internal software requests are synchronous register state changes,
 * not asynchronous I/O. The instruction helper exits its TB afterwards so
 * arbitration observes the completed PC (also under -icount). External
 * devices use cpu_interrupt() below to wake a sleeping vCPU. */
void dmcu_irq_update(CPUDMCUState *env)
{
    CPUState *cs = env_cpu(env);

    env->irq_state_changed = true;
    if (dmcu_irq_or_dtu_pending(env)) {
        cs->interrupt_request |= CPU_INTERRUPT_HARD;
    } else {
        cpu_reset_interrupt(cs, CPU_INTERRUPT_HARD);
    }
}

void dmcu_irq_raise(DMCUCPU *cpu, unsigned source)
{
    g_assert(source < DMCU_ICR_COUNT);
    cpu->env.sfr[DMCU_ICR_FIRST + source] |= DMCU_ICR_RQ;
    /* Peripheral callbacks hold BQL. Service an enabled transfer at the
     * peripheral event, independently of host vCPU scheduling. Waiting for
     * cpu_exec_interrupt coalesces successive DAC requests in the one-bit
     * RQ latch even when a fully populated DTU buffer can accept them.
     * Empty channels and completed blocks still request CPU service below;
     * software-written RQ retains its completed-instruction boundary. This
     * models autonomous DMA, not bus-cycle stealing or a guest ISR call. */
    dmcu_dtu_run(cpu);
    if (dmcu_irq_or_dtu_pending(&cpu->env)) {
        cpu_interrupt(&cpu->parent_obj, CPU_INTERRUPT_HARD);
    }
}

void dmcu_internal_memory_write(DMCUCPU *cpu, uint32_t addr,
                                uint32_t value, int bits)
{
    AddressSpace *as = cpu_get_address_space(&cpu->parent_obj, DMCU_AS_INTERNAL);
    uint32_t logical = addr & 0xffff;

    /* This address space is rooted at the raw SRAM backing, not the board
     * bus: neither DS/IGNDS nor overlapping SFR/MMIO windows apply. QEMU's
     * RAM stores notify all executable aliases and migration dirty tracking.
     * Byte operands retain the existing high-byte-first lane numbering.
     * Instructions which can write SRAM must also end their TB, because a
     * physical write invalidates future lookups, not already executing code.
     */
    if (bits == 8) {
        address_space_stb(as, logical ^ 1u, value,
                          MEMTXATTRS_UNSPECIFIED, NULL);
    } else {
        address_space_stw_le(as, logical, value,
                             MEMTXATTRS_UNSPECIFIED, NULL);
    }
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
    dmcu_start_page_return_record_write(
        env, address, old_value, value, 16, 2, env->pc);
    dmcu_npe_resource_return_record_write(
        env, address, old_value, value, 16, 2, env->pc);
    dmcu_internal_memory_write(cpu, address, value, 16);
}

/* Use the same field set for push/pop. Guest registers (including PSR, PC,
 * SP, FP and DS) are deliberately absent: the CPU frame and ISR own them. */
#define DMCU_IRQ_CONTEXT_FIELDS(F) \
    F(interrupt_frame_size) \
    F(interrupt_frame_base) \
    F(interrupt_frame_expected_psw) \
    F(interrupt_frame_expected_cs) \
    F(interrupt_frame_expected_pc) \
    F(interrupt_last_entry_pc) \
    F(interrupt_last_entry_sp) \
    F(interrupt_foreground_fp_address) \
    F(interrupt_foreground_fp_expected) \
    F(interrupt_repeat_pc) \
    F(interrupt_repeat_end) \
    F(interrupt_repeat_count) \
    F(interrupt_repeat_block) \
    F(interrupt_single_repeat_pc) \
    F(interrupt_single_repeat_count) \
    F(irq_save_fp_save_expected) \
    F(interrupt_repeat_saved) \
    F(interrupt_frame_watch_active) \
    F(interrupt_from_icr) \
    F(irq_save_fp_watch_active)

static void dmcu_interrupt_suspend(DMCUCPU *cpu)
{
    CPUDMCUState *env = &cpu->env;
    DMCUInterruptContext context;

#define SAVE_IRQ_FIELD(name) context.name = env->name;
    DMCU_IRQ_CONTEXT_FIELDS(SAVE_IRQ_FIELD)
#undef SAVE_IRQ_FIELD
    g_array_append_val(cpu->interrupt_contexts, context);
}

void dmcu_interrupt_complete(CPUDMCUState *env)
{
    DMCUCPU *cpu = env_archcpu(env);
    GArray *parents = cpu->interrupt_contexts;

    if (parents->len) {
        DMCUInterruptContext *context = &g_array_index(
            parents, DMCUInterruptContext, parents->len - 1);

#define RESTORE_IRQ_FIELD(name) env->name = context->name;
        DMCU_IRQ_CONTEXT_FIELDS(RESTORE_IRQ_FIELD)
#undef RESTORE_IRQ_FIELD
        g_array_set_size(parents, parents->len - 1);
    } else {
        env->in_interrupt = false;
        env->interrupt_from_icr = false;
        env->interrupt_frame_watch_active = false;
        env->irq_save_fp_watch_active = false;
    }
    dmcu_irq_update(env);
}

#undef DMCU_IRQ_CONTEXT_FIELDS

/* Shared architectural frame/repeat context. source < 0 is a synchronous
 * TRAP, which does not acknowledge an ICR or change the priority structure. */
static void dmcu_interrupt_enter(DMCUCPU *cpu, uint32_t return_pc,
                                  uint32_t target, int source)
{
    CPUDMCUState *env = &cpu->env;
    uint16_t old_sp = env->gpr[DMCU_SP] & 0xffff;
    uint16_t old_fp = env->gpr[DMCU_FP] & 0xffff;
    uint32_t interrupted_pc = return_pc & 0x00ffffffu;
    uint16_t interrupted_psw = dmcu_sfr_read_word(env, DMCU_SFR_PSW);
    uint16_t interrupted_fp_word;
    uint16_t socr = dmcu_sfr_read_word(env, DMCU_SFR_SOCR);
    unsigned frame_size = (socr & DMCU_SOCR_NSEG) ? 4 : 6;
    unsigned int i;

    interrupted_fp_word = lduw_le_p(cpu->internal_data + old_fp);

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

    /* RETI restores architectural PSR, CS, then PC.  The internal TCG flag
     * layout (Z,C,N,V) is not the guest PSR layout (Z,V,C,N), and the upper
     * PSR bits are part of the frame too.  Use the same conversion as
     * REG[01]/F102, including for guest-created callback frames. */
    if (env->in_interrupt) {
        dmcu_interrupt_suspend(cpu);
    }
    dmcu_interrupt_push(cpu, dmcu_code_pc(return_pc));
    if (!(socr & DMCU_SOCR_NSEG)) {
        dmcu_interrupt_push(cpu, dmcu_code_segment(return_pc));
    }
    dmcu_interrupt_push(cpu, interrupted_psw);
    env->interrupt_frame_size = frame_size;
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
            env->pc, target, 0xffff, 0,
            old_sp, old_fp);
    }
    env->interrupt_last_entry_pc = interrupted_pc;
    env->interrupt_last_entry_sp =
        old_sp;
    env->irq_save_fp_watch_active = false;
    env->irq_save_fp_save_expected = old_fp;

    /*
     * CN1916884A specifies that an interrupt suspends the active repeat
     * source/counter context and resumes it after the service routine.  The
     * ISR must therefore execute with an inactive repeat engine.  Keeping a
     * single live context here allowed the foreground REPB state to steer
     * vector instructions and, eventually, to skip the far-fill boundary
     * fixup which protects the F100 SFR window.
     *
     * Nested ICR entries preserve their parent's shadow independently. REP
     * inside an ISR is not architecturally supported; its IREP exception is
     * a separate, still unimplemented boundary, not a new supported mode.
     */
    env->interrupt_repeat_saved = env->repeat_count != 0 ||
                                  env->single_repeat_count != 0;
    if (env->interrupt_repeat_saved) {
        env->interrupt_repeat_pc = env->repeat_pc;
        env->interrupt_repeat_end = env->repeat_end;
        env->interrupt_repeat_count = env->repeat_count;
        env->interrupt_repeat_block = env->repeat_block;
        env->interrupt_single_repeat_pc = env->single_repeat_pc;
        env->interrupt_single_repeat_count = env->single_repeat_count;
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
    env->single_repeat_pc = 0;
    env->single_repeat_count = 0;
    env->interrupt_from_icr = source >= 0;
    if (source >= 0) {
        unsigned icr = env->sfr[DMCU_ICR_FIRST + source];
        unsigned psr = (interrupted_psw & ~DMCU_PSR_CPRI) |
                       DMCU_PSR_CIRQ | (dmcu_irq_priority(icr) << 12);

        env->sfr[DMCU_ICR_FIRST + source] &= ~DMCU_ICR_RQ;
        dmcu_sfr_write_word(env, DMCU_SFR_PSW, psr);
    }
    env->pc = target;
    env->in_interrupt = true;
    env->interrupt_max_depth = MAX(env->interrupt_max_depth,
                                  cpu->interrupt_contexts->len + 1);
    env->interrupt_entries++;
    dmcu_irq_update(env);
}

void dmcu_software_trap(CPUDMCUState *env, uint32_t return_pc, unsigned trap)
{
    DMCUCPU *cpu = env_archcpu(env);
    unsigned segment = env->sfr[DMCU_SFR_SOCR] & DMCU_SOCR_NSEG ?
                       dmcu_code_segment(return_pc) : 1;

    /* CN1916884A, TRAP operation (PDF p124): PC=zero_extend(trap*4),
     * CS=1 in segmented mode, otherwise retain CS. Unlike asynchronous
     * ICR entry, it specifies no RAM-vector selection, mask or PRI update.
     * Follow the operation table; the prose's NSEG sentence is ambiguous.
     * Explicit reconstructed-ROM hole detection runs before this helper. */
    dmcu_interrupt_enter(cpu, return_pc,
                         dmcu_code_address(segment, (trap & 0xff) * 4), -1);
    env->software_traps++;
}

static bool dmcu_cpu_exec_interrupt(CPUState *cs, int interrupt_request)
{
    DMCUCPU *cpu = env_archcpu(cpu_env(cs));
    CPUDMCUState *env = &cpu->env;
    bool transferred = false;
    uint16_t old_sp, old_fp, socr;
    unsigned frame_size, vector, segment;
    int source;

    if (interrupt_request & CPU_INTERRUPT_HARD) {
        transferred = dmcu_dtu_run(cpu);
        if (transferred) {
            dmcu_irq_update(env);
        }
    }
    socr = dmcu_sfr_read_word(env, DMCU_SFR_SOCR);
    /* CN1916884A, IGNDS operation (PDF p114): its no-DS instruction
     * sequence also masks hardware interrupts. Entering a vector here would
     * consume the foreground IGNDS count in the ISR, then resume a memory
     * access with the wrong bank. Leave RQ/HARD pending until the sequence
     * finishes; do not clear or re-enable the guest's SOCR.IE bit. */
    if (!(interrupt_request & CPU_INTERRUPT_HARD) ||
        !(socr & DMCU_SOCR_IE) || env->critical_count ||
        env->ignore_ds_count || !cpu->internal_data) {
        return transferred;
    }
    source = dmcu_irq_select(env);
    if (source < 0) {
        cpu_reset_interrupt(cs, CPU_INTERRUPT_HARD);
        return transferred;
    }
    old_sp = env->gpr[DMCU_SP] & 0xffff;
    old_fp = env->gpr[DMCU_FP] & 0xffff;
    frame_size = socr & DMCU_SOCR_NSEG ? 4 : 6;
    /* Retain the historical asynchronous SP/FP overlap deferral. Its full
     * hardware basis is unresolved; do not apply it to synchronous TRAPs
     * or pretend that it implements STOVUN stack exceptions. */
    if (old_sp >= frame_size && old_fp &&
        old_fp < old_sp && old_fp + 2u > old_sp - frame_size) {
        env->interrupt_frame_overlap_deferrals++;
        return transferred;
    }
    vector = source < 16 ? 0x40 + source * 8 : 0xc0 + (source - 16) * 4;
    dmcu_dtu_trace_irq(cpu, source);
    segment = socr & DMCU_SOCR_NSEG ? dmcu_code_segment(env->pc) :
                                    (socr & DMCU_SOCR_RAM ? 0 : 1);
    dmcu_interrupt_enter(cpu, env->pc,
                         dmcu_code_address(segment, vector), source);
    return true;
}

static void dmcu_cpu_synchronize_from_tb(CPUState *cs,
                                         const TranslationBlock *tb)
{
    tcg_debug_assert(!(cs->tcg_cflags & CF_PCREL));
    cpu_env(cs)->pc = tb->pc & 0x00ffffffu;
}

static void dmcu_restore_state_to_opc(CPUState *cs,
                                      const TranslationBlock *tb,
                                      const uint64_t *data)
{
    cpu_env(cs)->pc = data[0] & 0x00ffffffu;
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
    g_array_set_size(cpu->interrupt_contexts, 0);
    if (cpu->rom_service_reset) {
        cpu->rom_service_reset(cpu->rom_service_opaque);
    }
    env->pc = cpu->reset_pc ? cpu->reset_pc : DMCU_PROGRAM_BASE;
    env->mask_rom03_present = cpu->mask_rom03_present;
    env->rom_hle_enabled = cpu->rom_hle_enabled;
    env->soc_rom_skeleton = cpu->soc_rom_skeleton;
    env->hle_ui_enabled = cpu->hle_ui_enabled;
    env->control_observers_minimal = cpu->control_observers_minimal;
    env->instruction_clock_enabled = cpu->instruction_clock_enabled;
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
    cs->num_ases = 3;
    cpu_address_space_init(cs, DMCU_AS_DATA, "dmcu-data", cs->memory);
    cpu_address_space_init(cs, DMCU_AS_CODE, "dmcu-code",
                           cpu->code_memory ? cpu->code_memory : cs->memory);
    /* Do not fall back to the board bus: stack writes must bypass MMIO. */
    assert(cpu->internal_memory);
    cpu_address_space_init(cs, DMCU_AS_INTERNAL, "dmcu-internal",
                           cpu->internal_memory);
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
    if (attrs.space == DMCU_AS_INTERNAL) {
        return DMCU_AS_INTERNAL;
    }
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

static void dmcu_cpu_init(Object *obj)
{
    DMCU_CPU(obj)->interrupt_contexts = g_array_new(
        false, false, sizeof(DMCUInterruptContext));
}

static void dmcu_cpu_finalize(Object *obj)
{
    g_array_free(DMCU_CPU(obj)->interrupt_contexts, true);
}

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
    dc->vmsd = &vmstate_dmcu_cpu;
}

static const TypeInfo dmcu_cpu_types[] = {
    {
        .name = TYPE_DMCU_CPU,
        .parent = TYPE_CPU,
        .instance_size = sizeof(DMCUCPU),
        .instance_align = __alignof(DMCUCPU),
        .instance_init = dmcu_cpu_init,
        .instance_finalize = dmcu_cpu_finalize,
        .class_size = sizeof(DMCUCPUClass),
        .class_init = dmcu_cpu_class_init,
        .abstract = true,
    }, {
        .name = TYPE_DMCU_V1_CPU,
        .parent = TYPE_DMCU_CPU,
    },
};

DEFINE_TYPES(dmcu_cpu_types)
