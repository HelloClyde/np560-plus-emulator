/* DMCU AMPB data transfer unit, as used by the NP560.
 * CN1916884A figs. 16-18 and the original 24:97AC/98FC/9A1E drivers.
 * Requests perform one transfer, not a whole buffer; completion remains
 * an ICR request for the CPU at priority 3. Cycle stealing is not modelled.
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/timer.h"
#include "exec/address-spaces.h"
#include "cpu.h"

void dmcu_dtu_trace_irq(DMCUCPU *cpu, unsigned source)
{
    CPUDMCUState *env = &cpu->env;
    unsigned channel;

    if (!cpu->dtu_refill_trace_enabled) {
        return;
    }
    env->dtu_irq_entries[source]++;
    for (channel = 0; channel < DMCU_DTU_CHANNELS; channel++) {
        DMCUDTURefillEvent *e = &env->dtu_refill_pending[channel];
        if (e->pending && !e->accepted && e->source == source) {
            e->accepted = true;
            e->accepted_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
            e->accepted_pc = env->pc;
        }
    }
}

void dmcu_dtu_trace_reload(CPUDMCUState *env, unsigned channel, unsigned count)
{
    DMCUCPU *cpu = DMCU_CPU(env_cpu(env));
    DMCUDTURefillEvent *e = &env->dtu_refill_pending[channel];

    if (!cpu->dtu_refill_trace_enabled || !count || !e->pending) {
        return;
    }
    e->reloaded_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    e->reload_pc = env->current_instruction_pc;
    e->count = count;
    e->cpu_entries = env->interrupt_entries - e->entries_at_completion;
    e->pending = false;
    env->dtu_refill_trace[env->dtu_refill_count++ % DMCU_DTU_REFILL_TRACE_SLOTS] = *e;
}

char *dmcu_dtu_refill_state(DMCUCPU *cpu)
{
    CPUDMCUState *env = &cpu->env;
    uint64_t first = env->dtu_refill_count - MIN(env->dtu_refill_count, DMCU_DTU_REFILL_TRACE_SLOTS);
    uint64_t seq;
    unsigned source;
    GString *text = g_string_new(NULL);

    g_string_append_printf(text, "{\"enabled\":%s,\"count\":%" PRIu64 ",\"irq_entries\":[",
                           cpu->dtu_refill_trace_enabled ? "true" : "false", env->dtu_refill_count);
    for (source = 0; source < DMCU_ICR_COUNT; source++) {
        g_string_append_printf(text, "%s%" PRIu64, source ? "," : "", env->dtu_irq_entries[source]);
    }
    g_string_append(text, "],\"events\":[");
    for (seq = first; seq < env->dtu_refill_count; seq++) {
        DMCUDTURefillEvent *e = &env->dtu_refill_trace[seq % DMCU_DTU_REFILL_TRACE_SLOTS];
        g_string_append_printf(text,
            "%s{\"seq\":%" PRIu64 ",\"channel\":%u,\"source\":%u,"
            "\"completed_ns\":%" PRIu64 ",\"accepted_ns\":%" PRIu64 ",\"reloaded_ns\":%" PRIu64 ","
            "\"accepted\":%s,\"completion_pc\":%u,\"accepted_pc\":%u,\"reload_pc\":%u,"
            "\"count\":%u,\"socr\":%u,\"psr\":%u,\"critical\":%u,\"ignore_ds\":%u,\"cpu_entries\":%u}",
            seq == first ? "" : ",", seq, e->channel, e->source,
            e->completed_ns, e->accepted_ns, e->reloaded_ns,
            e->accepted ? "true" : "false", e->completion_pc, e->accepted_pc, e->reload_pc,
            e->count, e->socr, e->psr, e->critical, e->ignore_ds, e->cpu_entries);
    }
    g_string_append(text, "]}");
    return g_string_free(text, false);
}

static bool dmcu_dtu_request(CPUDMCUState *env, unsigned source)
{
    unsigned icr = env->sfr[DMCU_ICR_FIRST + source];
    unsigned channel = (icr & DMCU_ICR_PRI) >> 4;

    return (icr & (DMCU_ICR_EN | DMCU_ICR_RQ | DMCU_ICR_ED)) ==
           (DMCU_ICR_EN | DMCU_ICR_RQ | DMCU_ICR_ED) &&
           (env->sfr[DMCU_DTUC_FIRST + channel] & DMCU_DTUC_COUNT) &&
           !(env->dtu_fault_sources & (1u << source));
}

bool dmcu_dtu_has_work(CPUDMCUState *env)
{
    unsigned source;

    for (source = 0; source < DMCU_ICR_COUNT; source++) {
        if (dmcu_dtu_request(env, source)) {
            return true;
        }
    }
    return false;
}

static hwaddr dmcu_dtu_address(CPUDMCUState *env, uint16_t pointer,
                               bool banked, bool byte)
{
    hwaddr address = pointer;

    if (banked) {
        unsigned ds = env->sfr[pointer & 0x8000 ? DMCU_SFR_DS1 :
                                                   DMCU_SFR_DS0] & 0x1ff;
        address = (ds << 15) | (pointer & 0x7fff);
    } else if (pointer < DMCU_UNBANKED_PAGE_SIZE) {
        address += DMCU_UNBANKED_LOW_PAGE_BASE;
    } else if (pointer >= 0xf000 && pointer < 0xf800) {
        address = DMCU_UNBANKED_SFR_PAGE_BASE + pointer - 0xf000;
    }
    /* The data bus numbers the high byte first, even for internal RAM. */
    return address ^ (byte ? 1 : 0);
}

bool dmcu_dtu_run(DMCUCPU *cpu)
{
    CPUDMCUState *env = &cpu->env;
    AddressSpace *as = cpu_get_address_space(CPU(cpu), DMCU_AS_DATA);
    unsigned source;
    bool handled = false;

    /* Called with the iothread lock held: at a hardware request, or at a
     * completed CPU instruction for software RQ/configuration changes.
     * IE/CPRI and the CPU's ISR state gate CPU entry, not data transfers.
     * One pass handles each currently latched source once. Simultaneous
     * source ordering remains ascending vector, as in CPU arbitration. */
    for (source = 0; source < DMCU_ICR_COUNT; source++) {
        unsigned icr, channel, control, count, increment;
        uint16_t src, dst;
        hwaddr pointers, src_address, dst_address;
        MemTxResult result;
        uint8_t data[2];
        unsigned size;

        if (!dmcu_dtu_request(env, source)) {
            continue;
        }
        handled = true;
        icr = env->sfr[DMCU_ICR_FIRST + source];
        channel = (icr & DMCU_ICR_PRI) >> 4;
        control = env->sfr[DMCU_DTUC_FIRST + channel];
        count = control & DMCU_DTUC_COUNT;
        increment = (control & DMCU_DTUC_INC) >> 14;
        size = control & DMCU_DTUC_WBT ? 1 : 2;
        /* The pointer table is unbanked internal memory, not selected by
         * the foreground DS registers or its current IGNDS prefix. */
        pointers = DMCU_UNBANKED_SFR_PAGE_BASE + 0xf0 + channel * 4;
        src = address_space_lduw_le(as, pointers, MEMTXATTRS_UNSPECIFIED, NULL);
        dst = address_space_lduw_le(as, pointers + 2,
                                    MEMTXATTRS_UNSPECIFIED, NULL);
        if (increment == 3 || (size == 2 && ((src | dst) & 1))) {
            qemu_log_mask(LOG_UNIMP, "DMCU DTU unsupported request: "
                          "source=%u channel=%u control=%04x src=%04x dst=%04x\n",
                          source, channel, control, src, dst);
            env->dtu_fault_sources |= 1u << source;
            continue;
        }
        src_address = dmcu_dtu_address(env, src, control & DMCU_DTUC_SDS,
                                       size == 1);
        dst_address = dmcu_dtu_address(env, dst, control & DMCU_DTUC_DDS,
                                       size == 1);
        env->sfr[DMCU_ICR_FIRST + source] &= ~DMCU_ICR_RQ;
        result = address_space_read(as, src_address, MEMTXATTRS_UNSPECIFIED,
                                    data, size);
        if (result == MEMTX_OK) {
            result = address_space_write(as, dst_address,
                                         MEMTXATTRS_UNSPECIFIED, data, size);
        }
        if (result != MEMTX_OK) {
            qemu_log_mask(LOG_GUEST_ERROR, "DMCU DTU bus failure: "
                          "source=%u channel=%u result=%u\n",
                          source, channel, result);
            env->dtu_fault_sources |= 1u << source;
            env->sfr[DMCU_ICR_FIRST + source] |= DMCU_ICR_RQ;
            continue;
        }
        if (increment == 1) {
            address_space_stw_le(as, pointers + 2, (dst + size) & 0xffff,
                                 MEMTXATTRS_UNSPECIFIED, NULL);
        } else if (increment == 2) {
            address_space_stw_le(as, pointers, (src + size) & 0xffff,
                                 MEMTXATTRS_UNSPECIFIED, NULL);
        }
        env->sfr[DMCU_DTUC_FIRST + channel] =
            (control & ~DMCU_DTUC_COUNT) | (count - 1);
        env->dtu_transfers[channel]++;
        if (count == 1) {
            env->dtu_completions[channel]++;
            if (cpu->dtu_refill_trace_enabled) {
                DMCUDTURefillEvent *e = &env->dtu_refill_pending[channel];
                *e = (DMCUDTURefillEvent) {
                    .pending = true, .channel = channel, .source = source,
                    .completed_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
                    .entries_at_completion = env->interrupt_entries,
                    .completion_pc = env->pc,
                    .socr = env->sfr[DMCU_SFR_SOCR], .psr = dmcu_sfr_read_word(env, DMCU_SFR_PSW),
                    .critical = env->critical_count, .ignore_ds = env->ignore_ds_count,
                };
            }
            /* Latch completion until the CPU accepts it. A separate
             * request raised by the destination's side effects survives. */
            env->sfr[DMCU_ICR_FIRST + source] |= DMCU_ICR_RQ;
        }
    }
    return handled;
}
