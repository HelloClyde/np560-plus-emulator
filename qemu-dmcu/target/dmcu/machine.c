/* DMCU execution state. Device state and guest RAM belong to the board. */
#include "qemu/osdep.h"
#include "cpu.h"
#include "migration/cpu.h"

/* Resource limit on a migration stream, not an emulated IRQ depth limit. */
#define DMCU_MIGRATION_MAX_PARENTS (1u << 20)

static const VMStateDescription vmstate_dmcu_irq_context = {
    .name = "dmcu/irq-context",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
#define IRQ_U32(f) VMSTATE_UINT32(f, DMCUInterruptContext)
        IRQ_U32(interrupt_frame_size),
        IRQ_U32(interrupt_frame_base),
        IRQ_U32(interrupt_frame_expected_psw),
        IRQ_U32(interrupt_frame_expected_cs),
        IRQ_U32(interrupt_frame_expected_pc),
        IRQ_U32(interrupt_last_entry_pc),
        IRQ_U32(interrupt_last_entry_sp),
        IRQ_U32(interrupt_foreground_fp_address),
        IRQ_U32(interrupt_foreground_fp_expected),
        IRQ_U32(interrupt_repeat_pc),
        IRQ_U32(interrupt_repeat_end),
        IRQ_U32(interrupt_repeat_count),
        IRQ_U32(interrupt_repeat_block),
        IRQ_U32(interrupt_single_repeat_pc),
        IRQ_U32(interrupt_single_repeat_count),
        IRQ_U32(irq_save_fp_save_expected),
#undef IRQ_U32
        VMSTATE_BOOL(interrupt_repeat_saved, DMCUInterruptContext),
        VMSTATE_BOOL(interrupt_frame_watch_active, DMCUInterruptContext),
        VMSTATE_BOOL(interrupt_from_icr, DMCUInterruptContext),
        VMSTATE_BOOL(irq_save_fp_watch_active, DMCUInterruptContext),
        VMSTATE_END_OF_LIST()
    },
};

static int dmcu_get_irq_contexts(QEMUFile *f, void *opaque, size_t size,
                                 const VMStateField *field)
{
    GArray **slot = opaque;
    uint32_t count = qemu_get_be32(f);
    GArray *parents;
    unsigned i;
    int ret = qemu_file_get_error(f);

    if (ret) {
        return ret;
    }
    if (count > DMCU_MIGRATION_MAX_PARENTS) {
        return -E2BIG;
    }
    /* Do not allocate based on an untrusted count before reading its data. */
    parents = g_array_new(false, false, sizeof(DMCUInterruptContext));
    for (i = 0; i < count; i++) {
        DMCUInterruptContext context = { 0 };

        ret = vmstate_load_state(f, &vmstate_dmcu_irq_context, &context, 1);
        if (ret) {
            g_array_free(parents, true);
            return ret;
        }
        if ((context.interrupt_frame_size != 4 &&
             context.interrupt_frame_size != 6) ||
            context.interrupt_frame_base > 0xffff) {
            g_array_free(parents, true);
            return -EINVAL;
        }
        g_array_append_val(parents, context);
    }
    g_array_free(*slot, true);
    *slot = parents;
    return 0;
}

static int dmcu_put_irq_contexts(QEMUFile *f, void *opaque, size_t size,
                                 const VMStateField *field, JSONWriter *vmdesc)
{
    GArray *parents = *(GArray **)opaque;
    unsigned i;

    if (parents->len > DMCU_MIGRATION_MAX_PARENTS) {
        return -E2BIG;
    }
    qemu_put_be32(f, parents->len);
    for (i = 0; i < parents->len; i++) {
        int ret = vmstate_save_state(f, &vmstate_dmcu_irq_context,
                                    &g_array_index(parents,
                                                   DMCUInterruptContext, i),
                                    NULL);
        if (ret) {
            return ret;
        }
    }
    return qemu_file_get_error(f);
}

static const VMStateInfo vmstate_dmcu_irq_contexts = {
    .name = "dmcu/irq-contexts",
    .get = dmcu_get_irq_contexts,
    .put = dmcu_put_irq_contexts,
};

static int dmcu_cpu_pre_save(void *opaque)
{
    DMCUCPU *cpu = opaque;

    /* Old host ROM/UI diagnostics have extra host-managed state. They are
     * not a supported virtual device and must not silently lose that state. */
    if (cpu->rom_hle_enabled || cpu->hle_ui_enabled || cpu->rom_service ||
        cpu->instruction_clock_enabled) {
        return -ENOTSUP;
    }
    cpu->migration_features = cpu->mask_rom03_present |
                              (cpu->soc_rom_skeleton << 1);
    return 0;
}

static int dmcu_cpu_pre_load(void *opaque)
{
    DMCUCPU *cpu = opaque;
    CPUDMCUState *env = &cpu->env;
    int ret = dmcu_cpu_pre_save(cpu);

    if (ret) {
        return ret;
    }
    /* Discard observer rings from the destination's abandoned timeline.
     * Host pointers/callbacks and RAM ownership remain untouched. Never
     * call cpu_reset here: that would also reset common CPU/machine state. */
    memset(env, 0, sizeof(*env));
    env->file_wrapper_active_slot = 0xffff;
    env->mask_rom03_present = cpu->mask_rom03_present;
    env->soc_rom_skeleton = cpu->soc_rom_skeleton;
    env->control_observers_minimal = cpu->control_observers_minimal;
    env->auxiliary_code_base = cpu->auxiliary_code_base;
    env->auxiliary_code_limit = cpu->auxiliary_code_limit;
    env->resident_rom_base = cpu->resident_rom_base;
    env->resident_rom_limit = cpu->resident_rom_limit;
    env->startup_context = cpu->startup_context;
    return 0;
}

static int dmcu_cpu_post_load(void *opaque, int version_id)
{
    DMCUCPU *cpu = opaque;
    CPUDMCUState *env = &cpu->env;

    if (env->pc > 0xffffff || env->ignore_ds_count > 4 ||
        env->critical_count > 4 ||
        (!env->in_interrupt && cpu->interrupt_contexts->len) ||
        (env->in_interrupt &&
         ((env->interrupt_frame_size != 4 && env->interrupt_frame_size != 6) ||
          env->interrupt_frame_base > 0xffff))) {
        return -EINVAL;
    }
    /* vmstate_cpu_common restores halted/IRQ requests and flushes TLB/TBs.
     * In particular, do not acknowledge an ICR or run a DTU transfer here. */
    return 0;
}

const VMStateDescription vmstate_dmcu_cpu = {
    .name = "cpu/dmcu",
    .version_id = 1,
    .minimum_version_id = 1,
    .pre_save = dmcu_cpu_pre_save,
    .pre_load = dmcu_cpu_pre_load,
    .post_load = dmcu_cpu_post_load,
    .fields = (const VMStateField[]) {
        /* Verify configuration; do not overwrite destination address-space
         * wiring with values from another boot mode or ROM arrangement. */
#define DMCU_CPU_EQUAL(f) \
    VMSTATE_UINT32_EQUAL(f, DMCUCPU, "DMCU configuration differs")
        DMCU_CPU_EQUAL(reset_pc),
        DMCU_CPU_EQUAL(auxiliary_code_base),
        DMCU_CPU_EQUAL(auxiliary_code_limit),
        DMCU_CPU_EQUAL(resident_rom_base),
        DMCU_CPU_EQUAL(resident_rom_limit),
        DMCU_CPU_EQUAL(startup_context),
        DMCU_CPU_EQUAL(migration_features),
#undef DMCU_CPU_EQUAL
#define ENV_U32(f) VMSTATE_UINT32(env.f, DMCUCPU)
#define ENV_BOOL(f) VMSTATE_BOOL(env.f, DMCUCPU)
        ENV_U32(pc),
        VMSTATE_UINT32_ARRAY(env.gpr, DMCUCPU, 16),
        VMSTATE_UINT32_ARRAY(env.sfr, DMCUCPU, 256),
        ENV_U32(psw),
        ENV_U32(shift_buffer),
        ENV_U32(se),
        ENV_U32(ignore_ds_count),
        ENV_U32(critical_count),
        ENV_U32(single_repeat_pc),
        ENV_U32(single_repeat_count),
        ENV_U32(repeat_pc),
        ENV_U32(repeat_end),
        ENV_U32(repeat_count),
        ENV_U32(repeat_block),
        ENV_BOOL(irq_state_changed),
        ENV_U32(dtu_fault_sources),
        ENV_BOOL(in_interrupt),
        ENV_BOOL(interrupt_from_icr),
        ENV_U32(interrupt_frame_size),
        ENV_U32(interrupt_frame_base),
        ENV_U32(interrupt_frame_expected_psw),
        ENV_U32(interrupt_frame_expected_cs),
        ENV_U32(interrupt_frame_expected_pc),
        ENV_U32(interrupt_last_entry_pc),
        ENV_U32(interrupt_last_entry_sp),
        ENV_U32(interrupt_foreground_fp_address),
        ENV_U32(interrupt_foreground_fp_expected),
        ENV_U32(interrupt_repeat_pc),
        ENV_U32(interrupt_repeat_end),
        ENV_U32(interrupt_repeat_count),
        ENV_U32(interrupt_repeat_block),
        ENV_U32(interrupt_single_repeat_pc),
        ENV_U32(interrupt_single_repeat_count),
        ENV_U32(irq_save_fp_save_expected),
        ENV_BOOL(interrupt_repeat_saved),
        ENV_BOOL(interrupt_frame_watch_active),
        ENV_BOOL(irq_save_fp_watch_active),
        /* These physical input levels currently live in env, not on the
         * board. Include them until ownership is moved, rather than dropping
         * held switches. Frontend input leases are a separate lifecycle. */
        ENV_U32(web_key_state),
        ENV_U32(web_key_code),
        ENV_U32(web_matrix_state_low),
        ENV_U32(web_matrix_state_high),
#undef ENV_U32
#undef ENV_BOOL
        VMSTATE_SINGLE(interrupt_contexts, DMCUCPU, 0,
                       vmstate_dmcu_irq_contexts, GArray *),
        VMSTATE_END_OF_LIST()
    },
};
