/* Test the production DMCU VMState descriptor, not a second serializer.
 * CPU-common state, guest RAM and peripheral migration are outside this test.
 */
#include "qemu/osdep.h"
#include "cpu.h"
#include "migration/vmstate.h"
#include "migration/qemu-file.h"
#include "migration/savevm.h"
#include "io/channel-buffer.h"
#include "qemu/module.h"

static DMCUCPU *new_cpu(void)
{
    DMCUCPU *cpu = g_new0(DMCUCPU, 1);

    /* Serialization does not require a running vCPU or board. No CPU/QOM
     * stub, device callback or alternative state implementation is linked. */
    cpu->interrupt_contexts = g_array_new(false, false,
                                         sizeof(DMCUInterruptContext));
    cpu->reset_pc = 0x30000;
    cpu->resident_rom_limit = 0x200000;
    cpu->soc_rom_skeleton = true;
    return cpu;
}

static void free_cpu(DMCUCPU *cpu)
{
    g_array_free(cpu->interrupt_contexts, true);
    g_free(cpu);
}

static QIOChannelBuffer *copy_buffer(QIOChannelBuffer *source)
{
    QIOChannelBuffer *copy = qio_channel_buffer_new(MAX(source->usage, 1));

    memcpy(copy->data, source->data, source->usage);
    copy->usage = source->usage;
    return copy;
}

static QIOChannelBuffer *save_cpu(DMCUCPU *cpu, int *ret)
{
    QIOChannelBuffer *buffer = qio_channel_buffer_new(4096);
    QIOChannelBuffer *copy;
    QEMUFile *f = qemu_file_new_output(QIO_CHANNEL(buffer));

    *ret = vmstate_save_state(f, &vmstate_dmcu_cpu, cpu, NULL);
    /* VMState looks ahead for optional subsections after every structure. */
    qemu_put_byte(f, QEMU_VM_EOF);
    qemu_fflush(f);
    if (!*ret) {
        *ret = qemu_file_get_error(f);
    }
    /* Closing a QIOChannelBuffer releases its bytes, even with another
     * object reference. Keep an independent wire image before fclose. */
    copy = copy_buffer(buffer);
    qemu_fclose(f);
    object_unref(OBJECT(buffer));
    return copy;
}

static int load_cpu(DMCUCPU *cpu, QIOChannelBuffer *buffer, int version)
{
    QEMUFile *f;
    QIOChannelBuffer *input = copy_buffer(buffer);
    int ret;

    f = qemu_file_new_input(QIO_CHANNEL(input));
    ret = vmstate_load_state(f, &vmstate_dmcu_cpu, cpu, version);
    qemu_fclose(f);
    object_unref(OBJECT(input));
    return ret;
}

static void fill_cpu(DMCUCPU *cpu, unsigned depth, bool nseg)
{
    CPUDMCUState *env = &cpu->env;
    unsigned i;

    env->pc = 0x201234;
    for (i = 0; i < 16; i++) {
        env->gpr[i] = 0x123 + i * 0x111;
    }
    for (i = 0; i < 256; i++) {
        env->sfr[i] = 0x41 + i * 0x73;
    }
    env->psw = 0xb;
    env->shift_buffer = 0xcafe;
    env->se = 17;
    env->ignore_ds_count = 3;
    env->critical_count = 2;
    env->single_repeat_pc = 0x20fffe;
    env->single_repeat_count = 65536;
    env->repeat_pc = 0x200000;
    env->repeat_end = 0x20fffc;
    env->repeat_count = 41;
    env->repeat_block = 1;
    env->irq_state_changed = true;
    env->dtu_fault_sources = 0x80000002;
    env->web_key_state = 0x5;
    env->web_key_code = 0x100;
    env->web_matrix_state_low = 0xdeadbeef;
    env->web_matrix_state_high = 0x12345678;
    env->in_interrupt = depth != 0;
    env->interrupt_from_icr = depth != 0;
    env->interrupt_frame_size = nseg ? 4 : 6;
    env->interrupt_frame_base = 0x7ffc;
    env->interrupt_frame_expected_psw = 0x4021;
    env->interrupt_frame_expected_cs = 0x31;
    env->interrupt_frame_expected_pc = 0x1357;
    env->interrupt_last_entry_pc = 0x311357;
    env->interrupt_last_entry_sp = 0x8000;
    env->interrupt_foreground_fp_address = 0x9000;
    env->interrupt_foreground_fp_expected = 0x2468;
    env->interrupt_repeat_pc = 0x32fffa;
    env->interrupt_repeat_end = 0x320004;
    env->interrupt_repeat_count = 65536;
    env->interrupt_repeat_block = 1;
    env->interrupt_single_repeat_pc = 0x32fffc;
    env->interrupt_single_repeat_count = 123;
    env->irq_save_fp_save_expected = 0x4000;
    env->interrupt_repeat_saved = depth != 0;
    env->interrupt_frame_watch_active = depth != 0;
    env->irq_save_fp_watch_active = depth != 0;
    for (i = 1; i < depth; i++) {
        DMCUInterruptContext context = {
            .interrupt_frame_size = nseg ? 4 : 6,
            .interrupt_frame_base = 0x8000 - 6 * i,
            .interrupt_frame_expected_psw = 0x2000 + i,
            .interrupt_frame_expected_cs = i,
            .interrupt_frame_expected_pc = 0x1000 + i,
            .interrupt_last_entry_pc = 0x201000 + i,
            .interrupt_last_entry_sp = 0x8000 - 6 * (i - 1),
            .interrupt_foreground_fp_address = 0x9000 + i * 2,
            .interrupt_foreground_fp_expected = 0x7000 + i,
            .interrupt_repeat_pc = 0x220000 + i * 2,
            .interrupt_repeat_end = 0x228000 + i * 2,
            .interrupt_repeat_count = 65536 - i,
            .interrupt_repeat_block = 1,
            .interrupt_single_repeat_pc = 0x220000 + i * 2,
            .interrupt_single_repeat_count = 33 + i,
            .irq_save_fp_save_expected = 0x4000 + i,
            .interrupt_repeat_saved = true,
            .interrupt_frame_watch_active = true,
            .interrupt_from_icr = (i % 2) != 0,
            .irq_save_fp_watch_active = true,
        };
        g_array_append_val(cpu->interrupt_contexts, context);
    }
}

static void roundtrip(unsigned depth, bool nseg)
{
    DMCUCPU *src = new_cpu();
    DMCUCPU *dst = new_cpu();
    QIOChannelBuffer *wire, *again;
    uint8_t host_memory;
    int ret;

    fill_cpu(src, depth, nseg);
    /* Both sides have obsolete observer data; neither is execution state. */
    src->env.control_trace_count = 12345;
    dst->env.control_trace_count = 67890;
    dst->internal_data = &host_memory;
    wire = save_cpu(src, &ret);
    g_assert_cmpint(ret, ==, 0);
    /* Independently check version-1 fixed-width big-endian register bytes. */
    g_assert_cmphex(ldl_be_p(wire->data), ==, 0x30000);
    g_assert_cmphex(ldl_be_p(wire->data + 28), ==, 0x201234);
    g_assert_cmphex(ldl_be_p(wire->data + 32), ==, 0x123);
    g_assert_cmpint(load_cpu(dst, wire, 1), ==, 0);
    g_assert_cmpmem(src->env.gpr, sizeof(src->env.gpr),
                    dst->env.gpr, sizeof(dst->env.gpr));
    g_assert_cmpmem(src->env.sfr, sizeof(src->env.sfr),
                    dst->env.sfr, sizeof(dst->env.sfr));
    g_assert_cmpuint(dst->env.single_repeat_count, ==, 65536);
    g_assert_cmpuint(dst->env.repeat_count, ==, 41);
    g_assert_cmpuint(dst->env.interrupt_repeat_count, ==, 65536);
    g_assert_cmpuint(dst->env.interrupt_single_repeat_count, ==, 123);
    g_assert_cmpuint(dst->env.ignore_ds_count, ==, 3);
    g_assert_cmpuint(dst->env.critical_count, ==, 2);
    g_assert_cmpuint(dst->env.dtu_fault_sources, ==, 0x80000002);
    g_assert_cmpuint(dst->env.shift_buffer, ==, 0xcafe);
    g_assert_cmpuint(dst->env.se, ==, 17);
    g_assert_cmpuint(dst->env.web_matrix_state_low, ==, 0xdeadbeef);
    g_assert_cmpuint(dst->env.web_matrix_state_high, ==, 0x12345678);
    g_assert_cmpuint(dst->env.control_trace_count, ==, 0);
    g_assert(dst->internal_data == &host_memory);
    g_assert_cmpuint(src->interrupt_contexts->len, ==,
                     dst->interrupt_contexts->len);
    g_assert_cmpmem(src->interrupt_contexts->data,
                    src->interrupt_contexts->len * sizeof(DMCUInterruptContext),
                    dst->interrupt_contexts->data,
                    dst->interrupt_contexts->len * sizeof(DMCUInterruptContext));
    again = save_cpu(dst, &ret);
    g_assert_cmpint(ret, ==, 0);
    g_assert_cmpmem(wire->data, wire->usage, again->data, again->usage);
    /* Reload also replaces, rather than appends to, an existing IRQ stack. */
    g_assert_cmpint(load_cpu(dst, wire, 1), ==, 0);
    g_assert_cmpuint(src->interrupt_contexts->len, ==,
                     dst->interrupt_contexts->len);
    object_unref(OBJECT(again));
    object_unref(OBJECT(wire));
    free_cpu(src);
    free_cpu(dst);
}

static void test_roundtrip(void)
{
    roundtrip(0, false);
    roundtrip(1, false);
    roundtrip(4, false);
    roundtrip(4, true);
}

static void test_reject(void)
{
    DMCUCPU *src = new_cpu();
    DMCUCPU *dst = new_cpu();
    QIOChannelBuffer *wire;
    size_t length;
    int ret;

    fill_cpu(src, 0, false);
    wire = save_cpu(src, &ret);
    g_assert_cmpint(ret, ==, 0);
    length = wire->usage;
    wire->usage = 0;
    g_assert_cmpint(load_cpu(dst, wire, 1), <, 0);
    wire->usage = length / 2;
    g_assert_cmpint(load_cpu(dst, wire, 1), <, 0);
    wire->usage = length - 2;
    g_assert_cmpint(load_cpu(dst, wire, 1), <, 0);
    wire->usage = length;
    g_assert_cmpint(load_cpu(dst, wire, 0), <, 0);
    g_assert_cmpint(load_cpu(dst, wire, 2), <, 0);
    dst->reset_pc = 0x200000;
    g_assert_cmpint(load_cpu(dst, wire, 1), <, 0);
    dst->reset_pc = src->reset_pc;
    dst->soc_rom_skeleton = false;
    g_assert_cmpint(load_cpu(dst, wire, 1), <, 0);
    dst->soc_rom_skeleton = true;
    /* Final field is the parent count, followed by the stream EOF marker. */
    stl_be_p(wire->data + length - 5, UINT32_MAX);
    g_assert_cmpint(load_cpu(dst, wire, 1), ==, -E2BIG);
    stl_be_p(wire->data + length - 5, 1);
    g_assert_cmpint(load_cpu(dst, wire, 1), <, 0); /* absent parent body */
    stl_be_p(wire->data + length - 5, 0);
    dst->rom_hle_enabled = true;
    g_assert_cmpint(load_cpu(dst, wire, 1), ==, -ENOTSUP);
    object_unref(OBJECT(wire));
    wire = save_cpu(dst, &ret);
    g_assert_cmpint(ret, ==, -ENOTSUP);
    object_unref(OBJECT(wire));
    free_cpu(src);
    free_cpu(dst);
}

int main(int argc, char **argv)
{
    module_call_init(MODULE_INIT_QOM);
    g_setenv("QTEST_SILENT_ERRORS", "1", 1);
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/dmcu/vmstate/execution-and-irq-stack", test_roundtrip);
    g_test_add_func("/dmcu/vmstate/invalid-or-incompatible", test_reject);
    return g_test_run();
}
