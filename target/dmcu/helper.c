/* DMCU instruction semantics and Harvard address-space mapping. */

#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/error-report.h"
#include "cpu.h"
#include "exec/exec-all.h"
#include "exec/tb-flush.h"
#include "exec/address-spaces.h"
#include "exec/cpu_ldst.h"
#include "exec/helper-proto.h"
#include "hw/core/tcg-cpu-ops.h"

#define MASK16 0xffffu
#define MASK24 0xffffffu

static inline uint32_t internal_data_read(uint32_t addr, int bits);

/* Observe the saved caller-FP word in the original 2E:BE2E file-attach
 * frame.  This is diagnostic-only: callers still perform the guest store
 * after this function returns.  Source 0 is an ordinary internal-data
 * store, source 1 is a hardware-IRQ frame push, and source 2 is a translated
 * data-bus store. */
void dmcu_application_file_attach_record_frame_write(CPUDMCUState *env,
                                                     uint32_t address,
                                                     uint32_t old_value,
                                                     uint32_t value,
                                                     int bits,
                                                     uint8_t source)
{
    uint32_t width = bits / 8u;
    uint32_t anchor = env->application_file_attach_frame_address & MASK16;
    uint32_t mask = bits == 8 ? 0xffu : MASK16;

    if (!env->application_file_attach_frame_watch_active ||
        address >= anchor + 2u || address + width <= anchor ||
        (old_value & mask) == (value & mask)) {
        return;
    }

    env->application_file_attach_frame_writes++;
    if (env->application_file_attach_frame_writes != 1) {
        return;
    }
    env->application_file_attach_frame_first_pc =
        (source == 1 ? env->pc : env->current_instruction_pc) & MASK24;
    env->application_file_attach_frame_first_address = address & MASK24;
    env->application_file_attach_frame_first_old = old_value & mask;
    env->application_file_attach_frame_first_new = value & mask;
    env->application_file_attach_frame_first_bits = bits;
    env->application_file_attach_frame_first_source = source;
    env->application_file_attach_frame_first_sp = env->gpr[DMCU_SP] & MASK16;
    env->application_file_attach_frame_first_fp = env->gpr[DMCU_FP] & MASK16;
}

void dmcu_record_direct_menu_stack_escape(DMCUCPU *cpu, uint32_t kind,
                                          uint32_t pc, uint32_t next_pc,
                                          uint16_t word, uint16_t ext,
                                          uint16_t old_sp, uint16_t old_fp)
{
    CPUDMCUState *env = &cpu->env;
    unsigned int n;

    if (env->direct_menu_stack_escape_valid) {
        return;
    }
    env->direct_menu_stack_escape_valid = true;
    env->direct_menu_stack_escape_kind = kind;
    env->direct_menu_stack_escape_pc = pc & MASK24;
    env->direct_menu_stack_escape_next_pc = next_pc & MASK24;
    env->direct_menu_stack_escape_word = word & MASK16;
    env->direct_menu_stack_escape_ext = ext & MASK16;
    env->direct_menu_stack_escape_old_sp = old_sp;
    env->direct_menu_stack_escape_new_sp = env->gpr[DMCU_SP] & MASK16;
    env->direct_menu_stack_escape_old_fp = old_fp;
    env->direct_menu_stack_escape_new_fp = env->gpr[DMCU_FP] & MASK16;
    for (n = 0; n < ARRAY_SIZE(env->direct_menu_stack_escape_gpr); n++) {
        env->direct_menu_stack_escape_gpr[n] = env->gpr[n] & MASK16;
    }
    for (n = 0; n < ARRAY_SIZE(env->direct_menu_stack_escape_stack); n++) {
        env->direct_menu_stack_escape_stack[n] =
            internal_data_read((old_sp + n * 2u) & MASK16, 16);
    }

    /* Preserve the bounded history immediately before the first escape.
     * The faulting transfer itself is carried in the dedicated fields. */
    env->control_trace_frozen = true;
    qemu_log_mask(
        LOG_UNIMP,
        "DMCU direct-menu stack escape kind=%x at %02x:%04x>%02x:%04x "
        "word=%04x ext=%04x sp=%04x>%04x fp=%04x>%04x\n",
        kind, dmcu_code_segment(pc), dmcu_code_pc(pc),
        dmcu_code_segment(next_pc), dmcu_code_pc(next_pc), word, ext,
        old_sp, env->gpr[DMCU_SP] & MASK16, old_fp,
        env->gpr[DMCU_FP] & MASK16);
}

/*
 * Bounded, read-only application-context diagnostics.  The update package
 * does not contain the factory 03:0080 scheduler, so the only authoritative
 * description of its selector objects is the argument flow through the
 * recovered 1B:CE3C -> 23:A38C -> 18:21F4 chain.  Keep the object dump here
 * rather than fabricating a guest descriptor: every value below is observed
 * from an unmodified guest call frame and no register or memory is changed.
 */
static void log_application_far_words(const char *name, uint16_t high,
                                      uint16_t low, unsigned words)
{
    uint32_t physical = ((uint32_t)high << 16) | low;
    unsigned index;

    qemu_log_mask(LOG_UNIMP, " %s=%04x:%04x[", name, high, low);
    if ((high & 0xff00u) == 0) {
        for (index = 0; index < words; index++) {
            qemu_log_mask(
                LOG_UNIMP, "%s%04x", index ? "," : "",
                address_space_lduw_le(
                    &address_space_memory,
                    (physical + index * 2u) & MASK24,
                    MEMTXATTRS_UNSPECIFIED, NULL));
        }
    } else {
        qemu_log_mask(LOG_UNIMP, "outside-24-bit-data-space");
    }
    qemu_log_mask(LOG_UNIMP, "]");
}

/* Diagnostic watch for the far return frame of the complete 30:0000 menu
 * builder.  This records guest writes only; it never changes memory. */
static bool menu_builder_return_watch_active;
static uint16_t menu_builder_return_watch_base;
static unsigned menu_builder_return_watch_writes;
static unsigned menu_builder_return_watch_entries;
static bool menu_position_return_watch_active;
static uint16_t menu_position_return_watch_base;
static unsigned menu_position_return_watch_writes;
static unsigned menu_position_return_watch_entries;
/* Diagnostic-only watch for the factory hardware initializer called by
 * 01:3902.  The call frame is valid when SCALL creates it, but the current
 * cold boot later returns through FF:4B48.  Track both data paths so the
 * first writer identifies the missing SoC lane/alias rule.
 */
static bool hardware_init_return_watch_active;
static uint16_t hardware_init_return_watch_base;
static unsigned hardware_init_return_watch_writes;
static unsigned hardware_init_return_watch_entries;
/* Diagnostic-only provenance for the 0x28-byte local object passed from
 * 1B:25FE to 18:CFA8 and later consumed by 11:1752. */
static bool operation_object_watch_active;
static uint16_t operation_object_watch_base;
static unsigned operation_object_watch_writes;

static inline uint32_t width_mask(int bits)
{
    return bits == 32 ? UINT32_MAX : (1u << bits) - 1;
}

/* Observer-only provenance for the root desktop clock's caller-owned output
 * buffer.  The exact formatter receives this as a far pointer, while the
 * caller later consumes it as an internal-SRAM near pointer.  Observe both
 * buses so a missing bank-zero alias is distinguishable from a formatter
 * which simply returns without producing bytes. */
static inline bool clock_format_output_matches(CPUDMCUState *env,
                                               uint32_t address, int bits,
                                               uint8_t bus)
{
    uint32_t output = ((uint32_t)env->clock_format_root_args[0] << 16) |
                      env->clock_format_root_args[1];
    uint32_t core_output = ((uint32_t)env->clock_format_core_args[2] << 16) |
                           env->clock_format_core_args[3];
    uint32_t width = bits / 8u;

    if (!env->clock_format_root_active) {
        return false;
    }
    if (bus == 0) {
        if (!env->clock_format_root_args[0] &&
            address < output + DMCU_CLOCK_FORMAT_BUFFER_BYTES &&
            address + width > output) {
            return true;
        }
        return !env->clock_format_core_args[2] &&
               address < core_output + DMCU_CLOCK_FORMAT_BUFFER_BYTES &&
               address + width > core_output;
    }
    return (address < output + DMCU_CLOCK_FORMAT_BUFFER_BYTES &&
            address + width > output) ||
           (address < core_output + DMCU_CLOCK_FORMAT_BUFFER_BYTES &&
            address + width > core_output);
}

static inline void trace_clock_format_output_write(CPUDMCUState *env,
                                                   uint32_t address,
                                                   uint32_t old_value,
                                                   uint32_t value, int bits,
                                                   uint8_t bus)
{
    uint32_t sequence;
    uint32_t slot;

    if (!clock_format_output_matches(env, address, bits, bus)) {
        return;
    }
    sequence = env->clock_format_output_trace_count++;
    slot = sequence % DMCU_CLOCK_FORMAT_OUTPUT_TRACE_SLOTS;
    env->clock_format_output_trace_pc[slot] =
        env->current_instruction_pc & MASK24;
    env->clock_format_output_trace_address[slot] = address & MASK24;
    env->clock_format_output_trace_old[slot] = old_value & width_mask(bits);
    env->clock_format_output_trace_new[slot] = value & width_mask(bits);
    env->clock_format_output_trace_bits[slot] = bits;
    env->clock_format_output_trace_bus[slot] = bus;
}

/* Observer-only watch for the low word of the root controller's saved object
 * pointer.  The watch is armed after 1D:F30A has initialized the local, so the
 * first later change names the writer which turns a valid menu object into a
 * zero-length one.  Bus 0 is internal SRAM and bus 1 is translated data. */
static inline void trace_root_object_slot_write(CPUDMCUState *env,
                                                uint32_t address,
                                                uint32_t old_value,
                                                uint32_t new_value,
                                                int bits, uint8_t bus,
                                                uint32_t pc)
{
    uint32_t width = bits / 8u;
    uint32_t slot = env->root_object_slot_watch_address & MASK16;

    if (!env->root_object_slot_watch_active ||
        address >= slot + 2u || address + width <= slot ||
        (old_value & width_mask(bits)) == (new_value & width_mask(bits))) {
        return;
    }

    env->root_object_slot_writes++;
    if (env->root_object_slot_first_bad_valid) {
        return;
    }
    env->root_object_slot_first_bad_valid = true;
    env->root_object_slot_first_bad_pc = pc & MASK24;
    env->root_object_slot_first_bad_old = old_value & width_mask(bits);
    env->root_object_slot_first_bad_new = new_value & width_mask(bits);
    env->root_object_slot_first_bad_sp = env->gpr[DMCU_SP] & MASK16;
    env->root_object_slot_first_bad_fp = env->gpr[DMCU_FP] & MASK16;
    env->root_object_slot_first_bad_bits = bits;
    env->root_object_slot_first_bad_bus = bus;
    env->root_object_slot_first_bad_in_irq = env->in_interrupt;
}

/* Observer-only provenance for the root menu object's leading descriptor.
 * The exact controller later receives 51:4A46 and reads the child count at
 * +8.  Retain every value-changing external write through +0x0F so the
 * constructor and its source registers can be identified without changing
 * guest memory or supplying a synthetic descriptor. */
static inline void trace_root_object_data_write(CPUDMCUState *env,
                                                uint32_t physical,
                                                uint32_t logical,
                                                uint32_t old_value,
                                                uint32_t new_value,
                                                int bits,
                                                uint32_t pc)
{
    const uint32_t base = 0x514a46u;
    const uint32_t end = base + 0x10u;
    uint32_t width = bits / 8u;
    uint32_t sequence;
    uint32_t slot;
    static const unsigned gpr_index[7] = { 0, 1, 2, 3, 8, 9, 10 };
    unsigned index;

    if (physical >= end || physical + width <= base ||
        (old_value & width_mask(bits)) ==
        (new_value & width_mask(bits))) {
        return;
    }

    sequence = env->root_object_data_write_count++;
    slot = sequence % DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS;
    env->root_object_data_trace_pc[slot] = pc & MASK24;
    env->root_object_data_trace_physical[slot] = physical & MASK24;
    env->root_object_data_trace_logical[slot] = logical & MASK16;
    env->root_object_data_trace_old[slot] = old_value & width_mask(bits);
    env->root_object_data_trace_new[slot] = new_value & width_mask(bits);
    env->root_object_data_trace_sp[slot] = env->gpr[DMCU_SP] & MASK16;
    env->root_object_data_trace_fp[slot] = env->gpr[DMCU_FP] & MASK16;
    env->root_object_data_trace_ds0[slot] =
        env->sfr[DMCU_SFR_DS0] & 0x1ffu;
    env->root_object_data_trace_ds1[slot] =
        env->sfr[DMCU_SFR_DS1] & 0x1ffu;
    for (index = 0; index < ARRAY_SIZE(gpr_index); index++) {
        env->root_object_data_trace_gpr[slot][index] =
            env->gpr[gpr_index[index]] & MASK16;
    }
    env->root_object_data_trace_bits[slot] = bits;
    env->root_object_data_trace_in_irq[slot] = env->in_interrupt;
}

/* Observer-only provenance for the resident menu path word A2:2AA0.  This
 * word maps to physical 51:2AA0 through DS0 and is consumed by 24:162C to
 * construct the root-menu ancestry.  Retain all overlapping guest stores,
 * including same-value stores, so cold-start ownership can be reconstructed
 * without changing the path or supplying host menu state. */
static inline void trace_menu_path_write(CPUDMCUState *env,
                                         uint32_t physical,
                                         uint32_t logical,
                                         uint32_t old_value,
                                         uint32_t new_value,
                                         int bits,
                                         uint32_t pc)
{
    const uint32_t base = 0x512aa0u;
    const uint32_t end = base + 2u;
    uint32_t width = bits / 8u;
    uint32_t sequence;
    uint32_t slot;
    unsigned index;

    if (physical >= end || physical + width <= base) {
        return;
    }

    sequence = env->menu_path_write_count++;
    slot = sequence % DMCU_MENU_PATH_WRITE_TRACE_SLOTS;
    env->menu_path_write_pc[slot] = pc & MASK24;
    env->menu_path_write_physical[slot] = physical & MASK24;
    env->menu_path_write_logical[slot] = logical & MASK16;
    env->menu_path_write_old[slot] = old_value & width_mask(bits);
    env->menu_path_write_new[slot] = new_value & width_mask(bits);
    env->menu_path_write_sp[slot] = env->gpr[DMCU_SP] & MASK16;
    env->menu_path_write_fp[slot] = env->gpr[DMCU_FP] & MASK16;
    env->menu_path_write_ds0[slot] = env->sfr[DMCU_SFR_DS0] & 0x1ffu;
    env->menu_path_write_ds1[slot] = env->sfr[DMCU_SFR_DS1] & 0x1ffu;
    for (index = 0; index < 4; index++) {
        env->menu_path_write_gpr[slot][index] =
            env->gpr[index] & MASK16;
    }
    env->menu_path_write_bits[slot] = bits;
    env->menu_path_write_in_irq[slot] = env->in_interrupt;
}

static void trace_operation_object_write(CPUDMCUState *env,
                                         uint32_t address,
                                         uint32_t value, int bits,
                                         const char *bus)
{
    uint32_t pc = env->current_instruction_pc & MASK24;
    uint32_t width = bits / 8u;
    uint32_t old_value;

    /* Once LINK #0xB3 has established the 18:CFA8 frame, +6/+8 are the
     * caller-provided far pointer to the operation object.  Learn the base
     * from the guest frame instead of assuming the observed 0F7E address. */
    if (!operation_object_watch_active &&
        pc >= 0x18cfb8u && pc <= 0x18da2cu) {
        uint16_t fp = env->gpr[DMCU_FP] & MASK16;
        uint16_t object_hi = internal_data_read((fp + 6u) & MASK16, 16);
        uint16_t object_lo = internal_data_read((fp + 8u) & MASK16, 16);

        if (object_hi == 0) {
            operation_object_watch_active = true;
            operation_object_watch_base = object_lo;
            qemu_log_mask(LOG_UNIMP,
                          "DMCU operation object watch base=%04x "
                          "from=%02x:%04x fp=%04x\n",
                          object_lo, dmcu_code_segment(pc),
                          dmcu_code_pc(pc), fp);
        }
    }
    if (!operation_object_watch_active ||
        operation_object_watch_writes >= 256u ||
        address >= 0x10000u ||
        address + width <= operation_object_watch_base ||
        address >= (uint32_t)operation_object_watch_base + 0x28u) {
        return;
    }

    if (!strcmp(bus, "internal")) {
        old_value = internal_data_read(address & MASK16, bits);
    } else if (bits == 8) {
        old_value = address_space_ldub(&address_space_memory, address,
                                       MEMTXATTRS_UNSPECIFIED, NULL);
    } else {
        old_value = address_space_lduw_le(&address_space_memory, address,
                                          MEMTXATTRS_UNSPECIFIED, NULL);
    }
    qemu_log_mask(
        LOG_UNIMP,
        "DMCU operation object write #%u bus=%s pc=%02x:%04x "
        "address=%04x offset=%02x old=%04x new=%04x bits=%d "
        "sp=%04x fp=%04x\n",
        operation_object_watch_writes + 1, bus,
        dmcu_code_segment(pc), dmcu_code_pc(pc), address & MASK16,
        (address - operation_object_watch_base) & 0xff,
        old_value & width_mask(bits), value & width_mask(bits), bits,
        env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16);
    operation_object_watch_writes++;
}

/* Observer-only provenance for the startup condition which selects the
 * firmware's 0x7e -> 0x50 USB/My-Disk path.  SFR B0 is represented by the
 * synthetic trace address ff00b0; all other addresses are physical data-bus
 * locations. */
static inline void trace_usb_boot_write(CPUDMCUState *env, uint32_t address,
                                        uint32_t old_value,
                                        uint32_t new_value, int bits)
{
    uint32_t mask = width_mask(bits);
    unsigned slot;

    if ((old_value & mask) == (new_value & mask)) {
        return;
    }
    slot = env->usb_boot_trace_count % DMCU_USB_BOOT_TRACE_SLOTS;
    env->usb_boot_trace_pc[slot] = env->current_instruction_pc & MASK24;
    env->usb_boot_trace_address[slot] = address & MASK24;
    env->usb_boot_trace_old[slot] = old_value & mask;
    env->usb_boot_trace_new[slot] = new_value & mask;
    env->usb_boot_trace_bits[slot] = bits;
    env->usb_boot_trace_count++;
}

static inline uint32_t width_sign(int bits)
{
    return 1u << (bits - 1);
}

static inline int32_t sext8(uint32_t value)
{
    return (int8_t)value;
}

static inline int32_t sext16(uint32_t value)
{
    return (int16_t)value;
}

static inline uint32_t dmcu_insn_size(uint16_t word)
{
    uint8_t op = word >> 8;
    uint8_t arg = word;
    uint8_t hi = op >> 4;
    uint8_t lo = op & 15;

    if (lo <= 7 && hi >= 6 && hi <= 11) {
        return 4;
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
        return 4;
    case 0xbf:
        return arg == 0 ? 4 : 2;
    default:
        return 2;
    }
}

static inline uint32_t reg_read(CPUDMCUState *env, unsigned reg, int bits)
{
    reg &= 15;
    if (bits == 8) {
        uint32_t word = env->gpr[reg >> 1] & MASK16;

        /* RB0/RB2/... are the high bytes; RB1/RB3/... are the low bytes. */
        return reg & 1 ? word & 0xff : word >> 8;
    }
    return env->gpr[reg] & MASK16;
}

static inline void reg_write(CPUDMCUState *env, unsigned reg,
                             uint32_t value, int bits)
{
    reg &= 15;
    if (bits == 8) {
        unsigned word_reg = reg >> 1;

        if (reg & 1) {
            env->gpr[word_reg] = (env->gpr[word_reg] & 0xff00) |
                                 (value & 0xff);
        } else {
            env->gpr[word_reg] = (env->gpr[word_reg] & 0x00ff) |
                                 ((value & 0xff) << 8);
        }
        /* The barrel-shifter exponent register SE is architecturally
         * exposed as RB10 (the high byte of R5/ARX). */
        if (reg == 10) {
            env->se = value & 0xff;
        }
    } else {
        env->gpr[reg] = value & 0xffff;
        if (reg == 5) {
            env->se = (value >> 8) & 0xff;
        }
    }
}

static inline uint32_t sfr_read(CPUDMCUState *env, unsigned reg, int bits)
{
    uint32_t value;

    reg &= 0xff;
    if (reg >= 0xf0) {
        return reg_read(env, reg - 0xf0, bits);
    }
    if (reg == DMCU_SFR_SB) {
        /*
         * SB is the architectural shift buffer.  Plain shifts place their
         * discarded bits here; the resident memmove reads it to recover the
         * byte remainder after dividing a length by four.
         */
        return env->shift_buffer & (bits == 8 ? 0xff : MASK16);
    }
    if (reg == DMCU_SFR_PSW) {
        /* Hardware PSR bit order is Z,V,C,N in bits 0..3. */
        value = env->sfr[reg] & ~0xfu;
        value |= env->psw & DMCU_PSW_Z ? 0x1 : 0;
        value |= env->psw & DMCU_PSW_V ? 0x2 : 0;
        value |= env->psw & DMCU_PSW_C ? 0x4 : 0;
        value |= env->psw & DMCU_PSW_N ? 0x8 : 0;
        return value & (bits == 8 ? 0xff : 0xffff);
    }
    return env->sfr[reg] & (bits == 8 ? 0xff : 0xffff);
}

static inline void sfr_write(CPUDMCUState *env, unsigned reg,
                             uint32_t value, int bits)
{
    uint32_t old_value;

    reg &= 0xff;
    if (reg >= 0xf0) {
        reg_write(env, reg - 0xf0, value, bits);
        return;
    }
    if (reg == DMCU_SFR_SB) {
        if (bits == 8) {
            env->shift_buffer =
                (env->shift_buffer & 0xff00u) | (value & 0xffu);
        } else {
            env->shift_buffer = value & MASK16;
        }
        env->sfr[reg] = env->shift_buffer;
        return;
    }
    if (reg == DMCU_SFR_PSW) {
        uint32_t written = bits == 8 ?
                           (env->sfr[reg] & 0xff00) | (value & 0xff) :
                           value & MASK16;

        env->sfr[reg] = written;
        env->psw = (written & 0x1 ? DMCU_PSW_Z : 0) |
                   (written & 0x2 ? DMCU_PSW_V : 0) |
                   (written & 0x4 ? DMCU_PSW_C : 0) |
                   (written & 0x8 ? DMCU_PSW_N : 0);
        return;
    }
    old_value = env->sfr[reg];
    if (bits == 8) {
        env->sfr[reg] = (env->sfr[reg] & 0xff00) | (value & 0xff);
    } else {
        env->sfr[reg] = value & 0xffff;
    }

    if (reg == 0xb0) {
        trace_usb_boot_write(env, 0xff00b0u, old_value,
                             env->sfr[reg], bits);
    }

    if ((reg == DMCU_SFR_DS0 || reg == DMCU_SFR_DS1) &&
        old_value != env->sfr[reg]) {
        tlb_flush(env_cpu(env));
    } else if (reg != DMCU_SFR_DS0 && reg != DMCU_SFR_DS1) {
        qemu_log_mask(LOG_UNIMP, "DMCU SFR[%02x] <- %04x at %02x:%04x\n",
                      reg, env->sfr[reg] & MASK16,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc));
    }
}

static inline uint32_t data_physical_address(CPUDMCUState *env, uint32_t addr)
{
    uint32_t logical = addr & MASK16;
    uint32_t segment;

    if (env->ignore_ds_count) {
        /* IGNDS exposes the unbanked 64 KiB internal data/SFR window. */
        return logical;
    } else {
        segment = env->sfr[(logical & 0x8000) ? DMCU_SFR_DS1
                                              : DMCU_SFR_DS0] & 0x1ff;
    }
    return ((segment << 15) | (logical & 0x7fff)) & MASK24;
}

/*
 * DMCU program images serialize each 16-bit instruction/data word least
 * significant byte first, which is also the representation used by the
 * writable code-overlay backing store.  Byte operands on an external DS bank
 * follow the processor's word-oriented bus lanes: an even byte address
 * selects the high byte and the following odd address selects the low byte.
 *
 * The byte-lane rule also applies when DS0/DS1 select physical banks 0 and 1:
 * those banks are the data-bus view of internal X RAM, not a byte-natural
 * exception.  This matters for the resident font copy, which moves a sequence
 * of bytes from an external font word into bank-0 X RAM and subsequently
 * consumes it as a 16-bit row word.  Exempting bank 0 swaps the two eight-pixel
 * halves of every glyph.
 *
 * IGNDS changes only the bank-selection path for the following instruction;
 * it does not change the 16-bit bus's byte-lane numbering.  In particular,
 * the resident 28:FE80 small-font renderer copies glyph bytes into 0x4844 and
 * then reads them back under IGNDS.  Treating that read as byte-natural swaps
 * every adjacent pair of glyph rows (for example digit zero starts 66,3c
 * instead of 3c,66).
 */
static inline uint32_t data_backing_address(CPUDMCUState *env,
                                            uint32_t addr, int bits)
{
    uint32_t logical = addr & MASK16;

    if (bits == 8) {
        logical ^= 1u;
    }
    return logical;
}

static inline uint32_t data_actual_physical_address(CPUDMCUState *env,
                                                    uint32_t addr, int bits)
{
    uint32_t physical = data_physical_address(env, addr);

    if (bits == 8) {
        physical ^= 1u;
    }
    return physical;
}

static void native_buffer_stats(uint32_t base, uint32_t *nonzero,
                                uint32_t *hash)
{
    uint32_t count = 0;
    uint32_t digest = 2166136261u;
    unsigned i;

    for (i = 0; i < 14400; i++) {
        uint8_t value = address_space_ldub(&address_space_memory, base + i,
                                           MEMTXATTRS_UNSPECIFIED, NULL);

        count += value != 0;
        digest = (digest ^ value) * 16777619u;
    }
    *nonzero = count;
    *hash = digest;
}

static inline void trace_outer_context_data(CPUDMCUState *env, uint32_t addr,
                                            uint32_t value, int bits,
                                            bool write)
{
    uint32_t pc = env->pc & MASK24;
    uint32_t physical = data_physical_address(env, addr);
    unsigned slot;

    /*
     * 33:4510 is the recovered outer event dispatcher.  With the currently
     * reconstructed reset context at address zero, its direct structure
     * accesses land below +0x1cc4.  Retain a bounded trace of that window so
     * the missing 03:0030 constructor can be inferred from guest behaviour.
     */
    if (pc < 0x334510 || pc >= 0x3352a0 || physical > 0x001d00) {
        return;
    }
    slot = env->context_data_trace_count;
    if (slot >= DMCU_CONTEXT_DATA_TRACE_ENTRIES) {
        return;
    }
    env->context_data_trace_pc[slot] = pc;
    env->context_data_trace_logical[slot] = addr & MASK16;
    env->context_data_trace_physical[slot] = physical;
    env->context_data_trace_value[slot] = value & width_mask(bits);
    env->context_data_trace_bits[slot] = bits;
    env->context_data_trace_write[slot] = write;
    env->context_data_trace_count++;
}

static inline uint32_t translated_data_read(CPUDMCUState *env, uint32_t addr,
                                            int bits)
{
    uint32_t backing_addr = data_backing_address(env, addr, bits);
    uint32_t value = bits == 8 ? cpu_ldub_data(env, backing_addr)
                               : cpu_lduw_data(env, backing_addr);
    uint32_t pc = env->pc & MASK24;
    static unsigned font_lookup_data_reads;
    static unsigned resident_file_table_reads;
    static unsigned foreground_dispatch_table_reads;
    static unsigned foreground_parent_table_reads;
    static unsigned modal_dispatch_index_reads;
    static unsigned modal_dispatch_table_reads;
    static unsigned modal_record_field_reads;
    /* Preserve the four byte fetches which form the width and height words
     * consumed by the exact 26:CF40 root-resource clipper.  Recording the
     * translated physical address as well as the returned byte separates a
     * bad resource pointer from a wrong external-bus lane convention. */
    if (bits == 8 && env->root_bitmap_resource_calls != 0 &&
        (pc == 0x26d092u || pc == 0x26d0c4u ||
         pc == 0x26d0f6u || pc == 0x26d128u)) {
        unsigned trace = (env->root_bitmap_resource_calls - 1u) %
                         DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS;
        unsigned byte = pc == 0x26d092u ? 0u :
                        pc == 0x26d0c4u ? 1u :
                        pc == 0x26d0f6u ? 2u : 3u;

        env->root_bitmap_resource_byte_physical[trace][byte] =
            data_actual_physical_address(env, addr, bits) & MASK24;
        env->root_bitmap_resource_byte_logical[trace][byte] =
            addr & MASK16;
        env->root_bitmap_resource_byte_ds[trace][byte] =
            env->sfr[(addr & 0x8000u) ? DMCU_SFR_DS1 : DMCU_SFR_DS0] &
            0x01ffu;
        env->root_bitmap_resource_byte_value[trace][byte] = value & 0xffu;
    }

    /*
     * 27:7FAE loads the modal-page state at [FP+0x0a].  The compiler then
     * converts 27:7FDC + state * 2 into a DS:offset data pointer and reads the
     * code-embedded jump table at 27:7FD6.  A bad return was observed only
     * after that read produced the odd word 4D31.  Log both ends of this
     * calculation, without substituting either value, so a single natural
     * boot distinguishes state corruption from DS/bus translation damage.
     * HELPER(exec) has already advanced env->pc to the next instruction.
     */
    if (pc == 0x277fb0u && modal_dispatch_index_reads < 256) {
        uint32_t actual_physical =
            data_actual_physical_address(env, addr, bits);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU modal dispatch index read #%u pc=%02x:%04x "
            "logical=%04x physical=%06x value=%04x bits=%d "
            "DS0=%03x DS1=%03x SP=%04x FP=%04x\n",
            modal_dispatch_index_reads + 1,
            dmcu_code_segment(pc), dmcu_code_pc(pc), addr & MASK16,
            actual_physical & MASK24, value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[15] & MASK16, env->gpr[11] & MASK16);
        modal_dispatch_index_reads++;
    }

    /*
     * 2B:6EA6 reads one word from record+0x24+2*row and passes it as the
     * secondary state to 27:7E84.  The first natural failure eventually used
     * 0x88F2 as that state.  Preserve the computed far pointer, original
     * record base, bus translation, and returned word so one boot identifies
     * the bad producer without changing the vendor record or dispatch logic.
     * The single-word MOV has advanced env->pc to 2B:6EA8 here.
     */
    if (pc == 0x2b6ea8u && modal_record_field_reads < 1024) {
        uint32_t actual_physical =
            data_actual_physical_address(env, addr, bits);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU modal record field read #%u pc=%02x:%04x "
            "logical=%04x backing=%04x physical=%06x value=%04x bits=%d "
            "DS0=%03x DS1=%03x SP=%04x FP=%04x "
            "R0=%04x R1=%04x R2=%04x R3=%04x R4=%04x R5=%04x\n",
            modal_record_field_reads + 1,
            dmcu_code_segment(pc), dmcu_code_pc(pc), addr & MASK16,
            backing_addr & MASK16, actual_physical & MASK24,
            value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[15] & MASK16, env->gpr[11] & MASK16,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            env->gpr[4] & MASK16, env->gpr[5] & MASK16);
        modal_record_field_reads++;
    }

    if (pc == 0x277fd8u && modal_dispatch_table_reads < 256) {
        uint32_t actual_physical =
            data_actual_physical_address(env, addr, bits);
        uint32_t direct = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        int32_t table_index =
            ((int32_t)actual_physical - (int32_t)0x277fdcu) / 2;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU modal dispatch table read #%u pc=%02x:%04x "
            "logical=%04x backing=%04x physical=%06x index=%d "
            "tlb=%04x direct=%04x bits=%d DS0=%03x DS1=%03x "
            "SP=%04x FP=%04x\n",
            modal_dispatch_table_reads + 1,
            dmcu_code_segment(pc), dmcu_code_pc(pc), addr & MASK16,
            backing_addr & MASK16, actual_physical & MASK24, table_index,
            value & width_mask(bits), direct & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[15] & MASK16, env->gpr[11] & MASK16);
        modal_dispatch_table_reads++;
    }

    /*
     * The resident file opener derives a per-volume table entry at 1F:1FE6
     * and then loads the far object pointer stored in that entry at 1F:1FF8.
     * Keep a small diagnostic trace of those exact reads: the reconstructed
     * initializer visibly populates 51:27C2, while an empty return here makes
     * every native resource open fail with FFFE before touching NAND data.
     */
    /* HELPER(exec) advances env->pc before performing the operand access, so
     * match the next-PC values for both words of each far-pointer load. */
    if ((pc == 0x1f1fe8u || pc == 0x1f1fecu ||
         pc == 0x1f1ffau || pc == 0x1f1ffcu) &&
        resident_file_table_reads < 32) {
        uint32_t actual_physical =
            data_actual_physical_address(env, addr, bits);
        uint32_t direct = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU resident file table read #%u pc=%02x:%04x "
            "logical=%04x backing=%04x physical=%06x "
            "tlb=%04x direct=%04x bits=%d DS0=%03x DS1=%03x\n",
            resident_file_table_reads + 1,
            dmcu_code_segment(pc), dmcu_code_pc(pc), addr & MASK16,
            backing_addr & MASK16, actual_physical & MASK24,
            value & width_mask(bits), direct & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff);
        resident_file_table_reads++;
    }

    /*
     * The application foreground selects its state handler through the
     * immutable 21:AA46/AA48 dispatch tables.  A zero result skips the
     * 31:345E/22:381E setup branches and leaves the boot-status screen in
     * place.  Compare the translated load with a direct board-memory read at
     * each exact table-load instruction; this is bounded, read-only
     * diagnostics and does not change the guest value or control flow.
     */
    if ((pc == 0x2fc62eu || pc == 0x2253ecu ||
         pc == 0x2254bcu || pc == 0x22550eu ||
         pc == 0x22554eu || pc == 0x22564au) &&
        foreground_dispatch_table_reads < 32) {
        uint32_t actual_physical =
            data_actual_physical_address(env, addr, bits);
        uint32_t direct = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU foreground dispatch table read #%u pc=%02x:%04x "
            "logical=%04x backing=%04x physical=%06x "
            "tlb=%04x direct=%04x bits=%d DS0=%03x DS1=%03x "
            "r0=%04x r1=%04x\n",
            foreground_dispatch_table_reads + 1,
            dmcu_code_segment(pc), dmcu_code_pc(pc), addr & MASK16,
            backing_addr & MASK16, actual_physical & MASK24,
            value & width_mask(bits), direct & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16);
        foreground_dispatch_table_reads++;
    }
    if (pc == 0x2fc62eu && foreground_parent_table_reads < 16) {
        uint32_t actual_physical =
            data_actual_physical_address(env, addr, bits);
        uint32_t direct = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU foreground parent table read #%u "
            "logical=%04x physical=%06x tlb=%04x direct=%04x "
            "DS0=%03x DS1=%03x r0=%04x r1=%04x\n",
            foreground_parent_table_reads + 1, addr & MASK16,
            actual_physical & MASK24, value & width_mask(bits),
            direct & width_mask(bits),
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16);
        foreground_parent_table_reads++;
    }

    if ((pc >= 0x061d40u && pc < 0x0622a8u) ||
        (pc >= 0x062900u && pc < 0x063a00u)) {
        if (!env->menu_overlay_copy_reads) {
            env->menu_overlay_first_read_pc = pc;
            env->menu_overlay_first_read_address =
                data_actual_physical_address(env, addr, bits);
            env->menu_overlay_first_read_value = value & width_mask(bits);
        }
        env->menu_overlay_copy_reads++;
    }

    /*
     * 2A:D46E/D470 load the two words of a recovered far callback before
     * 2A:D482 transfers through it.  The physical board view currently
     * contains 0033:091C while the guest observed zero, so compare the TLB
     * data-bus result with a direct physical read at the exact failure site.
     * This is diagnostic only and does not alter either value.
     */
    if (pc == 0x2ad46e || pc == 0x2ad470) {
        uint32_t physical = data_physical_address(env, addr);
        uint32_t direct = bits == 8 ?
            address_space_ldub(&address_space_memory,
                               data_actual_physical_address(env, addr, bits),
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(LOG_UNIMP,
                      "DMCU callback read logical=%04x backing=%04x "
                      "physical=%06x tlb=%04x direct=%04x bits=%d "
                      "at %02x:%04x DS0=%03x DS1=%03x\n",
                      addr & MASK16, backing_addr & MASK16, physical,
                      value & width_mask(bits), direct & width_mask(bits),
                      bits, dmcu_code_segment(pc), dmcu_code_pc(pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
    }
    if (pc == dmcu_code_address(0x25, 0xe346)) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU storage attach F01A read logical=%04x "
                      "reported-physical=%06x value=%04x bits=%d "
                      "IGNDS=%u DS0=%03x DS1=%03x\n",
                      addr & MASK16, data_physical_address(env, addr),
                      value & width_mask(bits), bits, env->ignore_ds_count,
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
    }

    /* The reconstructed 17:9244 resident font lookup is code-bus complete,
     * but its embedded tables may also be visible through the SoC data bus.
     * Keep a bounded opt-in trace so strict runs can prove the actual
     * selector/address ranges before the board maps any additional ROM data.
     */
    if (pc >= 0x179244 && pc < 0x179e22 &&
        font_lookup_data_reads < 128) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU font lookup read logical=%04x physical=%06x "
                      "value=%04x bits=%d at %02x:%04x DS0=%03x DS1=%03x\n",
                      addr & MASK16, data_physical_address(env, addr),
                      value & width_mask(bits), bits,
                      dmcu_code_segment(pc), dmcu_code_pc(pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
        font_lookup_data_reads++;
    }

    if (pc == 0x519a24 || pc == 0x519a32 || pc == 0x519a34 ||
        pc == 0x519a46 || pc == 0x519a48) {
        if (env->stream_copy_reads == 0) {
            env->stream_copy_pc = pc;
            env->stream_copy_logical = addr & 0xffff;
            env->stream_copy_physical = data_physical_address(env, addr);
            env->stream_copy_value = value;
            env->stream_copy_ds0 = env->sfr[DMCU_SFR_DS0] & 0x1ff;
            env->stream_copy_ds1 = env->sfr[DMCU_SFR_DS1] & 0x1ff;
        }
        env->stream_copy_reads++;
    }
    trace_outer_context_data(env, addr, value, bits, false);
    return value;
}

enum {
    IRQ_SAVE_FP_BUS_TRANSLATED = 1,
    IRQ_SAVE_FP_BUS_INTERNAL = 2,
};

/*
 * The recovered application initializer at 29:C126 owns a conventional
 * three-word far-call frame: saved FP, return CS, return PC.  A failed boot
 * has changed all three words to FFFF before its final UNLINK/RETS.  Preserve
 * the first and last overlapping write from either data path so the next run
 * identifies the writer without a multi-million-instruction trace.  This is
 * observation only; the write is never suppressed or changed.
 */
static inline void trace_application_init_frame_write(
    CPUDMCUState *env, uint32_t physical, uint32_t old_value,
    uint32_t new_value, int bits, unsigned bus)
{
    uint32_t base = env->application_init_frame_base & MASK16;
    uint32_t width = bits / 8;

    if (!env->application_init_frame_watch_active ||
        physical >= base + 6u || physical + width <= base) {
        return;
    }

    env->application_init_frame_writes++;
    if (env->application_init_frame_writes == 1) {
        env->application_init_frame_first_write_pc =
            env->current_instruction_pc & MASK24;
        env->application_init_frame_first_write_address = physical & MASK24;
        env->application_init_frame_first_write_old =
            old_value & width_mask(bits);
        env->application_init_frame_first_write_new =
            new_value & width_mask(bits);
        env->application_init_frame_first_write_bits = bits;
        env->application_init_frame_first_write_bus = bus;
        env->application_init_frame_first_write_sp =
            env->gpr[DMCU_SP] & MASK16;
        env->application_init_frame_first_write_fp =
            env->gpr[DMCU_FP] & MASK16;
        env->application_init_frame_first_write_in_interrupt =
            env->in_interrupt != 0;
    }
    env->application_init_frame_last_write_pc =
        env->current_instruction_pc & MASK24;
    env->application_init_frame_last_write_address = physical & MASK24;
    env->application_init_frame_last_write_old = old_value & width_mask(bits);
    env->application_init_frame_last_write_new = new_value & width_mask(bits);
    env->application_init_frame_last_write_bits = bits;
    env->application_init_frame_last_write_bus = bus;
    env->application_init_frame_last_write_sp =
        env->gpr[DMCU_SP] & MASK16;
    env->application_init_frame_last_write_fp =
        env->gpr[DMCU_FP] & MASK16;
    env->application_init_frame_last_write_in_interrupt =
        env->in_interrupt != 0;
}

/*
 * The shipped 08:40D0 timer vector saves FP at unbanked 00:04D6 before its
 * synthetic RETI enters the application callback, then restores FP from the
 * same word at 08:4264.  Observe the first later write while that one-slot
 * save area is live.  This is deliberately diagnostic-only: the write is
 * neither suppressed nor changed.
 */
static inline void trace_irq_save_fp_write(CPUDMCUState *env,
                                           uint32_t logical,
                                           uint32_t physical,
                                           uint32_t old_value,
                                           uint32_t new_value,
                                           int bits, unsigned bus)
{
    uint32_t width = bits / 8;

    if (!env->in_interrupt || physical >= 0x000004d8u ||
        physical + width <= 0x000004d6u) {
        return;
    }

    if (!env->irq_save_fp_watch_active) {
        env->irq_save_fp_watch_active = true;
        env->irq_save_fp_saves++;
        env->irq_save_fp_save_entry = env->interrupt_entries;
        env->irq_save_fp_save_pc = env->current_instruction_pc & MASK24;
        env->irq_save_fp_save_next_pc = env->pc & MASK24;
        env->irq_save_fp_save_old = old_value & width_mask(bits);
        env->irq_save_fp_saved_value = new_value & width_mask(bits);
        env->irq_save_fp_save_logical = logical & MASK16;
        env->irq_save_fp_save_physical = physical & MASK24;
        env->irq_save_fp_save_bits = bits;
        env->irq_save_fp_save_bus = bus;
        env->irq_save_fp_save_ds0 = env->sfr[DMCU_SFR_DS0] & 0x1ff;
        env->irq_save_fp_save_ds1 = env->sfr[DMCU_SFR_DS1] & 0x1ff;
        return;
    }

    if ((old_value & width_mask(bits)) ==
        (new_value & width_mask(bits))) {
        return;
    }

    env->irq_save_fp_overwrites++;
    if (env->irq_save_fp_first_overwrite_entry) {
        return;
    }

    env->irq_save_fp_first_overwrite_entry = env->interrupt_entries;
    env->irq_save_fp_first_overwrite_pc =
        env->current_instruction_pc & MASK24;
    env->irq_save_fp_first_overwrite_next_pc = env->pc & MASK24;
    env->irq_save_fp_first_overwrite_old = old_value & width_mask(bits);
    env->irq_save_fp_first_overwrite_new = new_value & width_mask(bits);
    env->irq_save_fp_first_overwrite_logical = logical & MASK16;
    env->irq_save_fp_first_overwrite_physical = physical & MASK24;
    env->irq_save_fp_first_overwrite_bits = bits;
    env->irq_save_fp_first_overwrite_bus = bus;
    env->irq_save_fp_first_overwrite_ds0 = env->sfr[DMCU_SFR_DS0] & 0x1ff;
    env->irq_save_fp_first_overwrite_ds1 = env->sfr[DMCU_SFR_DS1] & 0x1ff;
    env->irq_save_fp_first_overwrite_sp = env->gpr[DMCU_SP] & MASK16;
    env->irq_save_fp_first_overwrite_fp = env->gpr[DMCU_FP] & MASK16;
}

/* Watch the three words pushed by the CPU at hardware-IRQ entry.  The timer
 * vector builds a separate synthetic RETI frame below them, so writes to the
 * original PSW/CS/PC words are never required for the callback transition.
 * Record provenance only; do not suppress or rewrite the guest store. */
static inline void trace_interrupt_frame_write(CPUDMCUState *env,
                                               uint32_t physical,
                                               uint32_t old_value,
                                               uint32_t new_value,
                                               int bits)
{
    uint32_t width = bits / 8;
    uint32_t base = env->interrupt_frame_base & MASK16;

    if (!env->in_interrupt || !env->interrupt_frame_watch_active ||
        physical >= base + 6u || physical + width <= base ||
        (old_value & width_mask(bits)) ==
            (new_value & width_mask(bits))) {
        return;
    }

    env->interrupt_frame_writes++;
    if (env->interrupt_frame_first_write_entry) {
        return;
    }
    env->interrupt_frame_first_write_entry = env->interrupt_entries;
    env->interrupt_frame_first_write_entry_pc =
        env->interrupt_last_entry_pc & MASK24;
    env->interrupt_frame_first_write_base = base;
    env->interrupt_frame_first_write_pc =
        env->current_instruction_pc & MASK24;
    env->interrupt_frame_first_write_address = physical & MASK24;
    env->interrupt_frame_first_write_old = old_value & width_mask(bits);
    env->interrupt_frame_first_write_new = new_value & width_mask(bits);
    env->interrupt_frame_first_write_bits = bits;
    env->interrupt_frame_first_write_sp = env->gpr[DMCU_SP] & MASK16;
    env->interrupt_frame_first_write_fp = env->gpr[DMCU_FP] & MASK16;
}

static inline void trace_interrupt_foreground_fp_write(CPUDMCUState *env,
                                                       uint32_t physical,
                                                       uint32_t old_value,
                                                       uint32_t new_value,
                                                       int bits)
{
    uint32_t width = bits / 8;
    uint32_t address = env->interrupt_foreground_fp_address & MASK16;

    if (!env->in_interrupt || !env->interrupt_frame_watch_active ||
        physical >= address + 2u || physical + width <= address ||
        (old_value & width_mask(bits)) ==
            (new_value & width_mask(bits))) {
        return;
    }
    env->interrupt_foreground_fp_writes++;
    if (env->interrupt_foreground_fp_first_entry) {
        return;
    }
    env->interrupt_foreground_fp_first_entry = env->interrupt_entries;
    env->interrupt_foreground_fp_first_entry_pc =
        env->interrupt_last_entry_pc & MASK24;
    env->interrupt_foreground_fp_first_write_pc =
        env->current_instruction_pc & MASK24;
    env->interrupt_foreground_fp_first_old = old_value & width_mask(bits);
    env->interrupt_foreground_fp_first_new = new_value & width_mask(bits);
    env->interrupt_foreground_fp_first_bits = bits;
    env->interrupt_foreground_fp_first_sp = env->gpr[DMCU_SP] & MASK16;
    env->interrupt_foreground_fp_first_fp = env->gpr[DMCU_FP] & MASK16;
}

enum {
    RESOURCE_RANGE_BUS_TRANSLATED = 1,
    RESOURCE_RANGE_BUS_INTERNAL = 2,
};

static inline void trace_resource_range_write(CPUDMCUState *env,
                                              uint32_t logical,
                                              uint32_t address,
                                              uint32_t old_value,
                                              uint32_t new_value,
                                              int bits, unsigned bus)
{
    unsigned index;

    if (bits == 8 && address >= 0x4a36u && address < 0x4a3au) {
        index = address - 0x4a36u;
        env->resource_range_byte_writes[index]++;
        env->resource_range_byte_last_pc[index] =
            env->current_instruction_pc & MASK24;
        env->resource_range_byte_last_old[index] = old_value & 0xff;
        env->resource_range_byte_last_new[index] = new_value & 0xff;
        if (env->resource_range_byte_writes[index] == 1) {
            env->resource_range_byte_first_pc[index] =
                env->current_instruction_pc & MASK24;
            env->resource_range_byte_first_logical[index] = logical & MASK16;
            env->resource_range_byte_first_old[index] = old_value & 0xff;
            env->resource_range_byte_first_new[index] = new_value & 0xff;
            env->resource_range_byte_first_bus[index] = bus;
        }
        return;
    }
    if (bits != 16 || (address != 0x4a36u && address != 0x4a38u)) {
        return;
    }

    /* A write to the first word is one complete candidate selection.  Keep
     * the far-copy caller and the source record while the NAND scratch page
     * still contains it; the buffer is reused immediately afterwards.  This
     * observer never alters guest registers, memory, or control flow. */
    if (address == 0x4a36u) {
        uint32_t slot = env->resource_candidate_trace_count %
                        DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS;
        uint16_t fp = env->gpr[DMCU_FP] & MASK16;
        uint16_t parent_fp = internal_data_read(fp, 16);
        uint32_t source_physical =
            data_physical_address(env, env->gpr[9]) & MASK24;
        unsigned word;

        env->resource_candidate_trace_pc[slot] =
            env->current_instruction_pc & MASK24;
        env->resource_candidate_trace_caller[slot] =
            ((internal_data_read((fp + 2u) & MASK16, 16) & 0xffu) << 16) |
            internal_data_read((fp + 4u) & MASK16, 16);
        env->resource_candidate_trace_outer_caller[slot] =
            ((internal_data_read((parent_fp + 2u) & MASK16, 16) & 0xffu)
             << 16) |
            internal_data_read((parent_fp + 4u) & MASK16, 16);
        env->resource_candidate_trace_source_physical[slot] = source_physical;
        env->resource_candidate_trace_source_logical[slot] =
            env->gpr[9] & MASK16;
        env->resource_candidate_trace_old[slot] = old_value & MASK16;
        env->resource_candidate_trace_base[slot] = new_value & MASK16;
        env->resource_candidate_trace_range[slot] = 0;
        env->resource_candidate_trace_sp[slot] =
            env->gpr[DMCU_SP] & MASK16;
        env->resource_candidate_trace_fp[slot] = fp;
        env->resource_candidate_trace_r8[slot] = env->gpr[8] & MASK16;
        env->resource_candidate_trace_r10[slot] = env->gpr[10] & MASK16;
        env->resource_candidate_trace_ds0[slot] =
            env->sfr[DMCU_SFR_DS0] & 0x1ff;
        env->resource_candidate_trace_ds1[slot] =
            env->sfr[DMCU_SFR_DS1] & 0x1ff;
        env->resource_candidate_trace_parent_fp[slot] = parent_fp;
        for (word = 0; word < DMCU_RESOURCE_CANDIDATE_ARGUMENT_WORDS;
             word++) {
            env->resource_candidate_trace_copy_args[slot][word] =
                internal_data_read((fp + 6u + word * 2u) & MASK16, 16);
            env->resource_candidate_trace_outer_args[slot][word] =
                internal_data_read(
                    (parent_fp + 6u + word * 2u) & MASK16, 16);
        }
        env->resource_candidate_trace_record_valid[slot] =
            source_physical >= 0x510002u && source_physical <= 0x51ffe0u;
        if (old_value == 0x0e93u && new_value != 0x0e93u &&
            new_value != 0) {
            env->resource_io_trace_frozen = true;
            env->resource_io_trace_frozen_pc =
                env->current_instruction_pc & MASK24;
            env->control_trace_frozen = true;
        }
        memset(env->resource_candidate_trace_record[slot], 0,
               sizeof(env->resource_candidate_trace_record[slot]));
        if (env->resource_candidate_trace_record_valid[slot]) {
            uint32_t record = source_physical - 2u;

            env->resource_candidate_trace_range[slot] =
                address_space_lduw_le(
                    &address_space_memory, source_physical + 2u,
                    MEMTXATTRS_UNSPECIFIED, NULL);
            for (word = 0; word < DMCU_RESOURCE_CANDIDATE_RECORD_WORDS;
                 word++) {
                env->resource_candidate_trace_record[slot][word] =
                    address_space_lduw_le(
                        &address_space_memory, record + word * 2u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
        env->resource_candidate_trace_count++;
    }
    index = (address - 0x4a36u) / 2u;
    env->resource_range_writes[index]++;
    env->resource_range_last_pc[index] =
        env->current_instruction_pc & MASK24;
    env->resource_range_last_logical[index] = logical & MASK16;
    env->resource_range_last_source_logical[index] = env->gpr[9] & MASK16;
    env->resource_range_last_source_physical[index] =
        data_physical_address(env, env->gpr[9]) & MASK24;
    env->resource_range_last_r8[index] = env->gpr[8] & MASK16;
    env->resource_range_last_r10[index] = env->gpr[10] & MASK16;
    env->resource_range_last_sp[index] = env->gpr[DMCU_SP] & MASK16;
    env->resource_range_last_fp[index] = env->gpr[DMCU_FP] & MASK16;
    env->resource_range_last_ds0[index] =
        env->sfr[DMCU_SFR_DS0] & 0x1ff;
    env->resource_range_last_ds1[index] =
        env->sfr[DMCU_SFR_DS1] & 0x1ff;
    env->resource_range_last_old[index] = old_value & MASK16;
    env->resource_range_last_new[index] = new_value & MASK16;
    if (env->resource_range_writes[index] == 1) {
        env->resource_range_first_pc[index] =
            env->current_instruction_pc & MASK24;
        env->resource_range_first_old[index] = old_value & MASK16;
        env->resource_range_first_new[index] = new_value & MASK16;
        env->resource_range_first_ds0[index] =
            env->sfr[DMCU_SFR_DS0] & 0x1ff;
        env->resource_range_first_ds1[index] =
            env->sfr[DMCU_SFR_DS1] & 0x1ff;
        env->resource_range_first_bus[index] = bus;
    }
}

static inline void translated_data_write(CPUDMCUState *env, uint32_t addr,
                                          uint32_t value, int bits)
{
    uint32_t physical = data_physical_address(env, addr);
    uint32_t backing_addr = data_backing_address(env, addr, bits);
    uint32_t actual_physical =
        data_actual_physical_address(env, addr, bits);
    uint32_t instruction_pc = env->current_instruction_pc & MASK24;
    static unsigned framebuffer_writes;
    static unsigned storage_root_writes;
    static unsigned storage_geometry_writes;
    static unsigned storage_record_writes;
    static unsigned storage_descriptor_writes;
    static unsigned storage_cursor_writes;
    static unsigned storage_ftl_state_writes;
    static unsigned storage_ftl_entry_zero_writes;
    static unsigned menu_state_overlay_writes;
    static unsigned menu_fill_overlay_writes;
    static unsigned menu_code_overlap_writes;
    static unsigned arithmetic_wrapper_boundary_writes;
    static unsigned menu_bit_wrapper_writes;
    static unsigned framebuffer_pointer_writes;
    static unsigned render_record_writes;
    static unsigned foreground_state_handler_writes;
    static unsigned modal_record_pointer_writes;
    static unsigned modal_record_body_writes;

    if (clock_format_output_matches(env, actual_physical, bits, 1)) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        trace_clock_format_output_write(env, actual_physical, old_value,
                                        value, bits, 1);
    }

    /*
     * The desktop's lower-left button occupies x<80 in the first 20 raw rows
     * of either native 4-bpp framebuffer page.  The ST7529 scan direction
     * presents those rows at the bottom of the final LCD.  Retain unique
     * value-changing writer contexts
     * after the natural root-controller entry.  A generic copy loop is keyed
     * together with its first two return frames so callers remain distinct.
     * This observer never changes or suppresses the pending guest store.
     */
    if (env->root_entry_frame_valid &&
        actual_physical >= 0x500000u && actual_physical < 0x507080u) {
        uint32_t base = actual_physical < 0x503840u ?
                        0x500000u : 0x503840u;
        uint32_t offset = actual_physical - base;
        uint32_t row = offset / 120u;
        uint32_t byte_column = offset % 120u;

        if (row < 20u && byte_column < 40u) {
            uint32_t old_value = bits == 8 ?
                address_space_ldub(&address_space_memory, actual_physical,
                                   MEMTXATTRS_UNSPECIFIED, NULL) :
                address_space_lduw_le(&address_space_memory, actual_physical,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            uint32_t masked_new = value & width_mask(bits);

            if ((old_value & width_mask(bits)) != masked_new) {
                uint16_t frame = env->gpr[DMCU_FP] & MASK16;
                uint32_t chain[DMCU_START_GLYPH_TRACE_FRAMES] = { 0 };
                unsigned depth;
                uint32_t slot;

                for (depth = 0;
                     depth < DMCU_START_GLYPH_TRACE_FRAMES && frame;
                     depth++) {
                    uint16_t parent = internal_data_read(frame, 16);
                    uint16_t cs = internal_data_read(
                        (frame + 2u) & MASK16, 16);
                    uint16_t pc = internal_data_read(
                        (frame + 4u) & MASK16, 16);

                    chain[depth] = ((cs & 0xffu) << 16) | pc;
                    if (!parent || parent == frame) {
                        break;
                    }
                    frame = parent;
                }
                env->desktop_fb_trace_writes++;
                for (slot = 0; slot < env->desktop_fb_trace_count; slot++) {
                    if (env->desktop_fb_trace_pc[slot] == instruction_pc &&
                        env->desktop_fb_trace_chain[slot][0] == chain[0] &&
                        env->desktop_fb_trace_chain[slot][1] == chain[1]) {
                        env->desktop_fb_trace_hits[slot]++;
                        break;
                    }
                }
                if (slot == env->desktop_fb_trace_count &&
                    slot < DMCU_DESKTOP_FB_TRACE_SLOTS) {
                    env->desktop_fb_trace_pc[slot] = instruction_pc;
                    env->desktop_fb_trace_address[slot] = actual_physical;
                    env->desktop_fb_trace_old[slot] =
                        old_value & width_mask(bits);
                    env->desktop_fb_trace_new[slot] = masked_new;
                    env->desktop_fb_trace_bits[slot] = bits;
                    env->desktop_fb_trace_hits[slot] = 1;
                    env->desktop_fb_trace_sp[slot] =
                        env->gpr[DMCU_SP] & MASK16;
                    env->desktop_fb_trace_fp[slot] =
                        env->gpr[DMCU_FP] & MASK16;
                    memcpy(env->desktop_fb_trace_chain[slot], chain,
                           sizeof(chain));
                    env->desktop_fb_trace_count++;
                }
            }
        }
    }

    /* 33:5EE0 is the root desktop clock's exact format-string overlay.
     * Preserve the bounded write history so a late flat-bank copy which
     * replaces the ROM-installed data can be attributed without altering the
     * guest store, its byte lanes, or any control flow. */
    if (actual_physical < 0x335eecu &&
        actual_physical + bits / 8u > 0x335ee0u) {
        uint32_t trace = env->clock_format_write_trace_count %
                         DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS;
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        env->clock_format_write_trace_pc[trace] = instruction_pc;
        env->clock_format_write_trace_address[trace] = actual_physical;
        env->clock_format_write_trace_old[trace] = old_value & MASK16;
        env->clock_format_write_trace_new[trace] =
            value & width_mask(bits);
        env->clock_format_write_trace_bits[trace] = bits;
        env->clock_format_write_trace_sp[trace] =
            env->gpr[DMCU_SP] & MASK16;
        env->clock_format_write_trace_fp[trace] =
            env->gpr[DMCU_FP] & MASK16;
        env->clock_format_write_trace_ds0[trace] =
            env->sfr[DMCU_SFR_DS0] & 0x01ffu;
        env->clock_format_write_trace_ds1[trace] =
            env->sfr[DMCU_SFR_DS1] & 0x01ffu;
        env->clock_format_write_trace_count++;
    }

    /* The first root bitmap header is consumed at 51:4A98.  Track the guest
     * instruction which physically populates its surrounding 16-byte window;
     * this observer identifies whether byte-stream lane order is introduced
     * by a CPU copy or by the NAND controller without modifying either. */
    if (actual_physical >= 0x514a90u && actual_physical < 0x514aa0u) {
        uint16_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        if (env->root_bitmap_source_writes == 0) {
            env->root_bitmap_source_first_pc = instruction_pc;
            env->root_bitmap_source_first_physical = actual_physical;
            env->root_bitmap_source_first_logical = addr & MASK16;
            env->root_bitmap_source_first_old = old_value;
            env->root_bitmap_source_first_new = value & width_mask(bits);
            env->root_bitmap_source_first_ds0 =
                env->sfr[DMCU_SFR_DS0] & 0x01ffu;
            env->root_bitmap_source_first_ds1 =
                env->sfr[DMCU_SFR_DS1] & 0x01ffu;
            env->root_bitmap_source_first_bits = bits;
        }
        env->root_bitmap_source_writes++;
        env->root_bitmap_source_last_pc = instruction_pc;
        env->root_bitmap_source_last_physical = actual_physical;
        env->root_bitmap_source_last_logical = addr & MASK16;
        env->root_bitmap_source_last_old = old_value;
        env->root_bitmap_source_last_new = value & width_mask(bits);
        env->root_bitmap_source_last_ds0 =
            env->sfr[DMCU_SFR_DS0] & 0x01ffu;
        env->root_bitmap_source_last_ds1 =
            env->sfr[DMCU_SFR_DS1] & 0x01ffu;
        env->root_bitmap_source_last_bits = bits;
    }
    {
        unsigned target_index;
        uint32_t width = bits / 8u;

        for (target_index = 0; target_index < 6; target_index++) {
            uint32_t target = 0x514a96u + target_index;

            if (actual_physical <= target &&
                actual_physical + width > target) {
                uint8_t byte = (value >>
                                ((target - actual_physical) * 8u)) & 0xffu;

                env->root_bitmap_header_write_count[target_index]++;
                if (byte != 0 &&
                    env->root_bitmap_header_first_nonzero_pc[target_index] ==
                    0) {
                    env->root_bitmap_header_first_nonzero_pc[target_index] =
                        instruction_pc;
                    env->root_bitmap_header_first_nonzero_value[target_index] =
                        byte;
                }
                env->root_bitmap_header_last_pc[target_index] = instruction_pc;
                env->root_bitmap_header_last_logical[target_index] =
                    addr & MASK16;
                env->root_bitmap_header_last_value[target_index] =
                    value & width_mask(bits);
                env->root_bitmap_header_last_bits[target_index] = bits;
            }
        }
    }

    /*
     * SYSTEM_MODE reads A1:386C through a byte access.  External byte lanes
     * are swapped, so the guest-visible mode byte lives at physical
     * 50:B86D.  Retain every value-changing write to that byte: this makes a
     * later blank mode-1 refresh attributable to the guest routine which
     * selected it, without modifying the write or synthesizing display
     * state.
     */
    if (actual_physical <= 0x50b86du &&
        actual_physical + bits / 8u > 0x50b86du) {
        uint8_t old_mode = address_space_ldub(
            &address_space_memory, 0x50b86du,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint8_t new_mode = (value >> ((0x50b86du - actual_physical) * 8u)) &
                           0xffu;

        if (old_mode != new_mode) {
            uint32_t slot = env->native_refresh_mode_write_count %
                            DMCU_NATIVE_REFRESH_TRACE_SLOTS;

            env->native_refresh_mode_write_pc[slot] = instruction_pc;
            env->native_refresh_mode_write_old[slot] = old_mode;
            env->native_refresh_mode_write_new[slot] = new_mode;
            env->native_refresh_mode_write_count++;
        }
    }

    dmcu_file_wrapper_record_stack_write(
        env, addr & MASK16, actual_physical & MASK16,
        bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
        value, bits, 1);
    dmcu_application_file_attach_record_frame_write(
        env, actual_physical,
        bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
        value, bits, 2);

    trace_root_object_slot_write(
        env, actual_physical,
        bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
        value, bits, 1, instruction_pc);

    trace_root_object_data_write(
        env, actual_physical, addr,
        bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
        value, bits, instruction_pc);

    trace_menu_path_write(
        env, actual_physical, addr,
        bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
        value, bits, instruction_pc);

    /* Keep the first and last guest writes to the filesystem error word for
     * the selected provision fopen.  This is a read-only diagnostic: the
     * actual translated store below remains the only state mutation. */
    if (env->file_open_watch_active && actual_physical < 0x00512ae2u &&
        actual_physical + bits / 8u > 0x00512ae0u) {
        uint16_t old_value = address_space_lduw_le(
            &address_space_memory, 0x00512ae0u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint32_t slot = env->file_open_error_writes %
                        DMCU_FILE_OPEN_ERROR_TRACE_SLOTS;

        if (env->file_open_error_writes == 0) {
            env->file_open_error_first_pc = instruction_pc;
            env->file_open_error_first_old = old_value;
            env->file_open_error_first_value = value & MASK16;
        }
        env->file_open_error_trace_pc[slot] = instruction_pc;
        env->file_open_error_trace_physical[slot] = actual_physical & MASK24;
        env->file_open_error_trace_logical[slot] = addr & MASK16;
        env->file_open_error_trace_old[slot] = old_value;
        env->file_open_error_trace_new[slot] = value & MASK16;
        env->file_open_error_trace_sp[slot] = env->gpr[DMCU_SP] & MASK16;
        env->file_open_error_trace_fp[slot] = env->gpr[DMCU_FP] & MASK16;
        env->file_open_error_trace_stage[slot] = env->file_open_stage;
        env->file_open_error_trace_ds0[slot] =
            env->sfr[DMCU_SFR_DS0] & 0x1ff;
        env->file_open_error_trace_ds1[slot] =
            env->sfr[DMCU_SFR_DS1] & 0x1ff;
        env->file_open_error_trace_r0[slot] = env->gpr[0] & MASK16;
        env->file_open_error_trace_r1[slot] = env->gpr[1] & MASK16;
        env->file_open_error_trace_bits[slot] = bits;
        env->file_open_error_writes++;
        env->file_open_error_last_pc = instruction_pc;
        env->file_open_error_last_physical = actual_physical & MASK24;
        env->file_open_error_last_old = old_value;
        env->file_open_error_last_value = value & MASK16;
        env->file_open_error_last_logical = addr & MASK16;
        env->file_open_error_last_bits = bits;
    }
    if (env->file_commit_watch_active && actual_physical < 0x00512ae2u &&
        actual_physical + bits / 8u > 0x00512ae0u) {
        uint16_t old_value = address_space_lduw_le(
            &address_space_memory, 0x00512ae0u,
            MEMTXATTRS_UNSPECIFIED, NULL);

        if (env->file_commit_error_writes == 0) {
            env->file_commit_error_first_pc = instruction_pc;
            env->file_commit_error_first_old = old_value;
            env->file_commit_error_first_value = value & MASK16;
        }
        env->file_commit_error_writes++;
        env->file_commit_error_last_pc = instruction_pc;
        env->file_commit_error_last_old = old_value;
        env->file_commit_error_last_value = value & MASK16;
        env->file_commit_error_last_stage = env->file_commit_stage;
    }

    /* Follow the exact USERINFO.SYS word through late overlay installation.
     * This narrow, read-only history reveals both the restoring writer and a
     * later broad copy that may replace the literal with flat code. */
    if (actual_physical < 0x319410u &&
        actual_physical + bits / 8u > 0x31940eu) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        uint32_t trace_slot = env->userinfo_path_writes %
                              DMCU_USERINFO_PATH_TRACE_SLOTS;

        env->userinfo_path_trace_pc[trace_slot] = instruction_pc;
        env->userinfo_path_trace_address[trace_slot] = actual_physical & MASK24;
        env->userinfo_path_trace_old[trace_slot] =
            old_value & width_mask(bits);
        env->userinfo_path_trace_new[trace_slot] = value & width_mask(bits);
        env->userinfo_path_trace_sp[trace_slot] =
            env->gpr[DMCU_SP] & MASK16;
        env->userinfo_path_trace_fp[trace_slot] =
            env->gpr[DMCU_FP] & MASK16;
        env->userinfo_path_trace_ds0[trace_slot] =
            env->sfr[DMCU_SFR_DS0] & 0x1ff;
        env->userinfo_path_trace_ds1[trace_slot] =
            env->sfr[DMCU_SFR_DS1] & 0x1ff;
        env->userinfo_path_trace_bits[trace_slot] = bits;
        env->userinfo_path_writes++;
    }

    /* The exact 42:5858 registry initializer builds a short linked pool at
     * 50:FE74 with 0x48-byte records.  Retain the last writer of each link /
     * activity header so a single provision run can distinguish pool
     * exhaustion from a guest routine which destroys the chain.  This is
     * observation only; the translated store below remains authoritative. */
    {
        static const uint32_t pool_node[DMCU_FILE_ROOT_POOL_NODES] = {
            0x0050fe74u, 0x0050febcu, 0x0050ff04u,
            0x0050ff4cu, 0x0050ff94u, 0x0050ffdcu,
        };
        unsigned index;

        for (index = 0; index < ARRAY_SIZE(pool_node); index++) {
            uint32_t base = pool_node[index];

            if (actual_physical < base + 6u &&
                actual_physical + bits / 8u > base) {
                uint32_t old_value = bits == 8 ?
                    address_space_ldub(&address_space_memory,
                                       actual_physical,
                                       MEMTXATTRS_UNSPECIFIED, NULL) :
                    address_space_lduw_le(&address_space_memory,
                                          actual_physical,
                                          MEMTXATTRS_UNSPECIFIED, NULL);

                if (actual_physical < base + 4u &&
                    actual_physical + bits / 8u > base) {
                    env->file_root_pool_link_writes[index]++;
                    env->file_root_pool_link_last_pc[index] = instruction_pc;
                    env->file_root_pool_link_last_offset[index] =
                        actual_physical - base;
                    env->file_root_pool_link_last_old[index] =
                        old_value & width_mask(bits);
                    env->file_root_pool_link_last_value[index] =
                        value & width_mask(bits);
                    env->file_root_pool_link_last_bits[index] = bits;
                } else {
                    env->file_root_pool_field_writes[index]++;
                    env->file_root_pool_field_last_pc[index] = instruction_pc;
                    env->file_root_pool_field_last_offset[index] =
                        actual_physical - base;
                    env->file_root_pool_field_last_old[index] =
                        old_value & width_mask(bits);
                    env->file_root_pool_field_last_value[index] =
                        value & width_mask(bits);
                    env->file_root_pool_field_last_bits[index] = bits;
                }
                break;
            }
        }
    }

    if (env->application_init_frame_watch_active &&
        actual_physical <
            (env->application_init_frame_base & MASK16) + 6u &&
        actual_physical + bits / 8u >
            (env->application_init_frame_base & MASK16)) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        trace_application_init_frame_write(
            env, actual_physical, old_value, value, bits,
            IRQ_SAVE_FP_BUS_TRANSLATED);
    }

    trace_operation_object_write(env, actual_physical, value, bits,
                                 "data");

    /*
     * A2:28FA/28FC supplies the far record pointer consumed by the indirect
     * 2E:DB80 callback path.  Trace only its exact two words.  The currently
     * failing run contains 1449:DC7C here, which resolves into the read-only
     * program window; the writer PC decides whether the pointer producer or
     * the external-memory mapping is wrong.
     */
    if (actual_physical < 0x005128feu &&
        actual_physical + bits / 8u > 0x005128fau &&
        modal_record_pointer_writes < 64) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU modal record pointer write #%u pc=%02x:%04x "
            "logical=%04x physical=%06x backing=%06x old=%04x new=%04x "
            "bits=%d DS0=%03x DS1=%03x SP=%04x FP=%04x\n",
            modal_record_pointer_writes + 1,
            dmcu_code_segment(instruction_pc),
            dmcu_code_pc(instruction_pc), addr & MASK16,
            actual_physical & MASK24, backing_addr & MASK24,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16);
        modal_record_pointer_writes++;
    }

    /* The callback at 2D:9CD0 mutates the object later consumed by 2B:6CE6.
     * Log its first bounded stores when they resolve into segment 49.  This is
     * observation only; writes still follow the normal QEMU memory path. */
    if (instruction_pc >= 0x2d9cd0u && instruction_pc < 0x2db526u &&
        actual_physical >= 0x0049dc00u &&
        actual_physical < 0x0049dd00u &&
        modal_record_body_writes < 128) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU modal record body write #%u pc=%02x:%04x "
            "logical=%04x physical=%06x backing=%06x old=%04x new=%04x "
            "bits=%d DS0=%03x DS1=%03x SP=%04x FP=%04x\n",
            modal_record_body_writes + 1,
            dmcu_code_segment(instruction_pc),
            dmcu_code_pc(instruction_pc), addr & MASK16,
            actual_physical & MASK24, backing_addr & MASK24,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16);
        modal_record_body_writes++;
    }

    /* The recovered 18:CFA8 constructor finishes by storing two far
     * callbacks at object+0x1E and object+0x22.  If either store is routed
     * through a non-zero data page, the low-address object watcher above
     * deliberately ignores it.  Preserve the complete address translation
     * for these four exact store instructions so the missing SoC alias can
     * be distinguished from an untaken constructor tail. */
    if (instruction_pc == 0x18d9fau || instruction_pc == 0x18d9fcu ||
        instruction_pc == 0x18da1eu || instruction_pc == 0x18da20u) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU operation callback store pc=%02x:%04x logical=%04x "
            "physical=%06x backing=%06x actual=%06x value=%04x bits=%d "
            "ds0=%03x ds1=%03x sp=%04x fp=%04x\n",
            dmcu_code_segment(instruction_pc), dmcu_code_pc(instruction_pc),
            addr & MASK16, physical & MASK24, backing_addr & MASK24,
            actual_physical & MASK24, value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16);
    }

    /* The first application storage record points at a 0x60-byte root
     * metadata object currently allocated at 51:2878.  Its +0x10/+0x12
     * bounds are both zero on the failing natural boot, so the exact
     * 20:76CA file resolver has no records to scan.  Retain every
     * value-changing write to that object, including its writer PC and
     * stack/frame, without changing the guest-visible store.  A bounded ring
     * makes the provenance available through the Web state endpoint and
     * avoids multi-gigabyte instruction logs. */
    if (actual_physical < 0x005128d8u &&
        actual_physical + bits / 8u > 0x00512878u) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        if ((old_value & width_mask(bits)) !=
            (value & width_mask(bits))) {
            uint32_t slot = env->root_metadata_trace_count %
                            DMCU_ROOT_METADATA_TRACE_SLOTS;

            env->root_metadata_trace_pc[slot] =
                env->current_instruction_pc & MASK24;
            env->root_metadata_trace_address[slot] =
                actual_physical & MASK24;
            env->root_metadata_trace_old[slot] =
                old_value & width_mask(bits);
            env->root_metadata_trace_new[slot] =
                value & width_mask(bits);
            env->root_metadata_trace_sp[slot] =
                env->gpr[DMCU_SP] & MASK16;
            env->root_metadata_trace_fp[slot] =
                env->gpr[DMCU_FP] & MASK16;
            env->root_metadata_trace_bits[slot] = bits;
            env->root_metadata_trace_count++;
        }
    }

    /* Compact, persistent watch for the resident NAND scanner's geometry
     * inputs.  A corrupted 4B66 turns its ordinary 0x0836 OOB probe into a
     * huge column such as 0xCC87; retaining the first/last 32 writes makes
     * that causal transition visible through cpu-state without enabling an
     * instruction log or changing guest execution. */
    {
        static const uint32_t geometry_words[] = {
            0x000004dcu, 0x000004deu,
            0x00004b04u, 0x00004b06u,
            0x00004b64u, 0x00004b66u,
        };
        uint32_t access_end = actual_physical + bits / 8u;
        unsigned geometry_index;

        for (geometry_index = 0;
             geometry_index < G_N_ELEMENTS(geometry_words);
             geometry_index++) {
            uint32_t watched = geometry_words[geometry_index];
            uint32_t old_value;
            uint32_t slot;

            if (actual_physical >= watched + 2u || access_end <= watched) {
                continue;
            }
            old_value = bits == 8 ?
                address_space_ldub(&address_space_memory, actual_physical,
                                   MEMTXATTRS_UNSPECIFIED, NULL) :
                address_space_lduw_le(&address_space_memory, actual_physical,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            if ((old_value & width_mask(bits)) ==
                (value & width_mask(bits))) {
                break;
            }
            slot = env->storage_geometry_trace_count++ %
                   DMCU_STORAGE_GEOMETRY_TRACE_SLOTS;
            env->storage_geometry_trace_pc[slot] =
                env->current_instruction_pc & MASK24;
            env->storage_geometry_trace_address[slot] = actual_physical;
            env->storage_geometry_trace_old[slot] =
                old_value & width_mask(bits);
            env->storage_geometry_trace_new[slot] = value & width_mask(bits);
            env->storage_geometry_trace_bits[slot] = bits;
            break;
        }
    }

    /* Track the small set of guest variables used by the exact USB/My-Disk
     * boot-state decision.  This records the pre-store value and writer PC,
     * without altering the write or supplying a synthetic ROM service. */
    {
        static const uint32_t usb_boot_words[] = {
            0x004b28u,
            0x512a48u, 0x512a4au, 0x512a56u,
        };
        uint32_t access_end = actual_physical + bits / 8u;
        unsigned state_index;

        for (state_index = 0;
             state_index < G_N_ELEMENTS(usb_boot_words);
             state_index++) {
            uint32_t state_address = usb_boot_words[state_index];

            if (actual_physical < state_address + 2u &&
                access_end > state_address) {
                uint32_t old_value = bits == 8 ?
                    address_space_ldub(&address_space_memory,
                                       actual_physical,
                                       MEMTXATTRS_UNSPECIFIED, NULL) :
                    address_space_lduw_le(&address_space_memory,
                                          actual_physical,
                                          MEMTXATTRS_UNSPECIFIED, NULL);

                trace_usb_boot_write(env, actual_physical, old_value,
                                     value, bits);
                break;
            }
        }
    }

    /* Retain value-changing writes to the state consumed by the exact
     * 29:3DD2 low-level event helper.  This is a read-only provenance probe:
     * it neither fabricates an event nor changes the guest-visible store.
     * The continuously advancing unbanked 0:4B40 clock is shown in cpu-state but is
     * deliberately excluded from this ring so it cannot evict the flag and
     * timestamp writers that determine why the modal poll completes. */
    {
        static const uint32_t event_state_words[] = {
            0x000494u, 0x000496u, 0x000498u,
            0x512a4eu,
            0x512a64u, 0x512a66u, 0x512a68u, 0x512a6au,
            0x512a7eu, 0x512a82u, 0x512a9au, 0x512aacu,
        };
        uint32_t access_end = actual_physical + bits / 8u;
        unsigned state_index;

        for (state_index = 0;
             state_index < G_N_ELEMENTS(event_state_words);
             state_index++) {
            uint32_t state_address = event_state_words[state_index];

            if (actual_physical < state_address + 2u &&
                access_end > state_address) {
                uint32_t old_value = bits == 8 ?
                    address_space_ldub(&address_space_memory,
                                       actual_physical,
                                       MEMTXATTRS_UNSPECIFIED, NULL) :
                    address_space_lduw_le(&address_space_memory,
                                          actual_physical,
                                          MEMTXATTRS_UNSPECIFIED, NULL);

                bool countdown = state_address == 0x000494u ||
                                 state_address == 0x000496u ||
                                 state_address == 0x000498u;
                bool boundary =
                    (old_value & width_mask(bits)) == 0 ||
                    (value & width_mask(bits)) == 0 ||
                    ((env->current_instruction_pc & MASK24) != 0x0840fau &&
                     (env->current_instruction_pc & MASK24) != 0x084104u &&
                     (env->current_instruction_pc & MASK24) != 0x08410eu);

                if ((old_value & width_mask(bits)) !=
                    (value & width_mask(bits)) &&
                    (!countdown || boundary)) {
                    unsigned slot = env->event_state_trace_count %
                                    DMCU_EVENT_STATE_TRACE_SLOTS;

                    env->event_state_trace_pc[slot] =
                        env->current_instruction_pc & MASK24;
                    env->event_state_trace_address[slot] =
                        actual_physical & MASK24;
                    env->event_state_trace_old[slot] =
                        old_value & width_mask(bits);
                    env->event_state_trace_new[slot] =
                        value & width_mask(bits);
                    env->event_state_trace_bits[slot] = bits;
                    env->event_state_trace_count++;
                }
                break;
            }
        }
    }

    /* The exact 18:6454 blitter commits its four 16-bit framebuffer words at
     * 18:6558.  Keep the translated and actual targets visible: this catches
     * DS/far-pointer mistakes even when the store lands outside both known
     * 14,400-byte framebuffer windows. */
    if ((env->current_instruction_pc & MASK24) ==
        dmcu_code_address(0x18, 0x6558)) {
        env->native_font_store_calls++;
        env->native_font_store_pc = env->current_instruction_pc & MASK24;
        env->native_font_store_logical = addr & MASK16;
        env->native_font_store_physical = physical & MASK24;
        env->native_font_store_actual_physical = actual_physical & MASK24;
        env->native_font_store_value = value & width_mask(bits);
        env->native_font_store_bits = bits;
        env->native_font_store_ds0 = env->sfr[DMCU_SFR_DS0] & 0x1ff;
        env->native_font_store_ds1 = env->sfr[DMCU_SFR_DS1] & 0x1ff;
        if (env->native_font_store_calls <= 32) {
            qemu_log_mask(
                LOG_UNIMP,
                "DMCU resident font store call=%u logical=%04x "
                "physical=%06x actual=%06x value=%04x bits=%d "
                "DS0=%03x DS1=%03x\n",
                env->native_font_store_calls, addr & MASK16,
                physical & MASK24, actual_physical & MASK24,
                value & width_mask(bits), bits,
                env->native_font_store_ds0, env->native_font_store_ds1);
        }
    }

    /* Diagnostic-only provenance monitor for the source-50 foreground state
     * wrapper destination.  The range is first restored by resident guest
     * code and is currently overwritten again before state 0x01 dispatches.
     * Log both phases without changing the store or guest control flow. */
    if (actual_physical >= 0x00333c86u &&
        actual_physical < 0x00333ee6u &&
        foreground_state_handler_writes < 1024) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU foreground state handler write #%u pc=%02x:%04x "
            "logical=%04x physical=%06x old=%04x new=%04x bits=%d "
            "DS0=%03x DS1=%03x sp=%04x fp=%04x\n",
            foreground_state_handler_writes + 1,
            dmcu_code_segment(env->current_instruction_pc),
            dmcu_code_pc(env->current_instruction_pc), addr & MASK16,
            actual_physical & MASK24, old_value & width_mask(bits),
            value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16);
        foreground_state_handler_writes++;
    }

    /* 33:615E consumes seven 18-byte records from 52:4D50..4DCD.  The
     * backing RAM is currently empty when that renderer runs.  Record the
     * first actual producers without changing or synthesizing any data. */
    if (actual_physical >= 0x00524d50u &&
        actual_physical < 0x00524dceu &&
        render_record_writes < 256) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU render record write #%u pc=%02x:%04x logical=%04x "
            "physical=%06x old=%04x new=%04x bits=%d DS0=%03x DS1=%03x\n",
            render_record_writes + 1,
            dmcu_code_segment(env->current_instruction_pc),
            dmcu_code_pc(env->current_instruction_pc), addr & MASK16,
            actual_physical & MASK24, old_value & width_mask(bits),
            value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff);
        render_record_writes++;
    }

    /* 00:04FC/04FE is the native font blitter's active framebuffer far
     * pointer.  A recurring blank-screen failure changes it from 50:3840 to
     * 50:0000, after which 31:4BFC copies an empty back buffer over the LCD
     * buffer.  Retain the writer and bus view; do not change the guest value. */
    if (actual_physical < 0x00000500u &&
        actual_physical + bits / 8 > 0x000004fcu &&
        framebuffer_pointer_writes < 64) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU framebuffer pointer write #%u bus=translated "
            "pc=%02x:%04x logical=%04x physical=%06x "
            "old=%04x new=%04x bits=%d DS0=%03x DS1=%03x\n",
            framebuffer_pointer_writes + 1,
            dmcu_code_segment(env->current_instruction_pc),
            dmcu_code_pc(env->current_instruction_pc), addr & MASK16,
            actual_physical & MASK24, old_value & width_mask(bits),
            value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff);
        framebuffer_pointer_writes++;
    }

    /* A2:28E0 is the byte-to-sector resource window used by exact
     * 29:AC4E.  Preserve the first and last guest writes so a monitor that
     * attaches after the 32-entry resource-I/O ring has wrapped can still
     * diagnose a resource read which ran before this value was initialized.
     * This is observation only; the ordinary memory write below is unchanged.
     */
    if ((bits == 16 && actual_physical == 0x005128e0u) ||
        (bits == 8 && actual_physical >= 0x005128e0u &&
         actual_physical < 0x005128e2u)) {
        uint16_t old_word = address_space_lduw_le(
            &address_space_memory, 0x005128e0u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t new_word;

        if (bits == 16) {
            new_word = value & MASK16;
        } else if (actual_physical == 0x005128e0u) {
            new_word = (old_word & 0xff00u) | (value & 0xffu);
        } else {
            new_word = (old_word & 0x00ffu) | ((value & 0xffu) << 8);
        }
        if (!env->resource_window_writes) {
            env->resource_window_first_write_pc =
                env->current_instruction_pc & MASK24;
            env->resource_window_first_write_old = old_word;
            env->resource_window_first_write_new = new_word;
            env->resource_window_first_write_bits = bits;
        }
        env->resource_window_writes++;
        env->resource_window_last_write_pc =
            env->current_instruction_pc & MASK24;
        env->resource_window_last_write_old = old_word;
        env->resource_window_last_write_new = new_word;
        env->resource_window_last_write_bits = bits;
    }

    /* Preserve the provenance of the seven storage-capacity counters used by
     * the exact 2D:78AA resource-volume initializer.  The values are sampled
     * again when 2D:7996 publishes the derived base, so later FTL activity
     * cannot make a post-mortem RAM dump look like the initialization input.
     * This is diagnostic-only and does not alter the write. */
    if (bits == 16 && actual_physical >= 0x000004eeu &&
        actual_physical <= 0x000004fau &&
        !(actual_physical & 1u)) {
        unsigned index = (actual_physical - 0x000004eeu) / 2u;

        env->resource_base_count_writes[index]++;
        env->resource_base_count_last_pc[index] =
            env->current_instruction_pc & MASK24;
        env->resource_base_count_last_value[index] = value & MASK16;
    }
    if (actual_physical >= 0x00511000u &&
        actual_physical < 0x00511020u) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        if ((old_value & width_mask(bits)) !=
            (value & width_mask(bits))) {
            unsigned slot = env->factory_record_writes %
                            DMCU_FACTORY_RECORD_TRACE_SLOTS;

            env->factory_record_write_pc[slot] =
                env->current_instruction_pc & MASK24;
            env->factory_record_write_address[slot] = actual_physical;
            env->factory_record_write_old[slot] =
                old_value & width_mask(bits);
            env->factory_record_write_new[slot] = value & width_mask(bits);
            env->factory_record_write_sp[slot] =
                env->gpr[DMCU_SP] & MASK16;
            env->factory_record_write_fp[slot] =
                env->gpr[DMCU_FP] & MASK16;
            env->factory_record_write_ds0[slot] =
                env->sfr[DMCU_SFR_DS0] & 0x1ff;
            env->factory_record_write_ds1[slot] =
                env->sfr[DMCU_SFR_DS1] & 0x1ff;
            env->factory_record_write_bits[slot] = bits;
            env->factory_record_writes++;
        }
    }

    if (env->in_interrupt && env->interrupt_frame_watch_active &&
        actual_physical <
            (env->interrupt_frame_base & MASK16) + 6u &&
        actual_physical + bits / 8 >
            (env->interrupt_frame_base & MASK16)) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        trace_interrupt_frame_write(env, actual_physical, old_value, value,
                                    bits);
    }
    if (env->in_interrupt && env->interrupt_frame_watch_active &&
        actual_physical <
            (env->interrupt_foreground_fp_address & MASK16) + 2u &&
        actual_physical + bits / 8 >
            (env->interrupt_foreground_fp_address & MASK16)) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        trace_interrupt_foreground_fp_write(
            env, actual_physical, old_value, value, bits);
    }
    if (env->in_interrupt && actual_physical < 0x000004d8u &&
        actual_physical + bits / 8 > 0x000004d6u) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        trace_irq_save_fp_write(env, addr, actual_physical, old_value, value,
                                bits, IRQ_SAVE_FP_BUS_TRANSLATED);
    }
    if (bits == 16 &&
        (actual_physical == 0x00004a36u ||
         actual_physical == 0x00004a38u)) {
        uint32_t old_value = address_space_lduw_le(
            &address_space_memory, actual_physical,
            MEMTXATTRS_UNSPECIFIED, NULL);

        trace_resource_range_write(env, addr, actual_physical, old_value,
                                   value, bits,
                                   RESOURCE_RANGE_BUS_TRANSLATED);
    } else if (bits == 8 && actual_physical >= 0x00004a36u &&
               actual_physical < 0x00004a3au) {
        uint32_t old_value = address_space_ldub(
            &address_space_memory, actual_physical,
            MEMTXATTRS_UNSPECIFIED, NULL);

        trace_resource_range_write(env, addr, actual_physical, old_value,
                                   value, bits,
                                   RESOURCE_RANGE_BUS_TRANSLATED);
    }

    if (((actual_physical >= 0x336bb2u &&
          actual_physical < 0x336bc2u) ||
         (actual_physical >= 0x336c2au &&
          actual_physical < 0x336c3au)) &&
        menu_bit_wrapper_writes < 64) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu bit wrapper write #%u pc=%02x:%04x "
            "logical=%04x physical=%06x old=%04x new=%04x bits=%d "
            "DS0=%03x DS1=%03x\n",
            menu_bit_wrapper_writes + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            addr & MASK16, actual_physical & MASK24,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff);
        menu_bit_wrapper_writes++;
    }

    if (((actual_physical >= 0x3286b4u &&
          actual_physical < 0x3286bau) ||
         (actual_physical >= 0x328706u &&
          actual_physical < 0x328716u) ||
         (actual_physical >= 0x3324c2u &&
          actual_physical < 0x3324c6u) ||
         (actual_physical >= 0x3324e6u &&
          actual_physical < 0x3324eeu)) &&
        arithmetic_wrapper_boundary_writes < 128) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU arithmetic wrapper boundary write #%u pc=%02x:%04x "
            "logical=%04x physical=%06x old=%04x new=%04x bits=%d "
            "DS0=%03x DS1=%03x sp=%04x fp=%04x\n",
            arithmetic_wrapper_boundary_writes + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            addr & MASK16, actual_physical & MASK24,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16);
        arithmetic_wrapper_boundary_writes++;
    }

    if (menu_builder_return_watch_active &&
        actual_physical < (uint32_t)menu_builder_return_watch_base + 4u &&
        actual_physical + bits / 8u > menu_builder_return_watch_base &&
        menu_builder_return_watch_writes < 64) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu builder return overwrite #%u pc=%02x:%04x "
            "logical=%04x physical=%06x old=%04x new=%04x bits=%d "
            "watch=%04x stack=%04x,%04x sp=%04x fp=%04x "
            "DS0=%03x DS1=%03x r0=%04x r1=%04x r2=%04x r3=%04x\n",
            menu_builder_return_watch_writes + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            addr & MASK16, actual_physical & MASK24,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            menu_builder_return_watch_base,
            internal_data_read(menu_builder_return_watch_base, 16),
            internal_data_read(
                (menu_builder_return_watch_base + 2u) & MASK16, 16),
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16);
        menu_builder_return_watch_writes++;
    }

    if (menu_position_return_watch_active &&
        actual_physical < (uint32_t)menu_position_return_watch_base + 4u &&
        actual_physical + bits / 8u > menu_position_return_watch_base &&
        menu_position_return_watch_writes < 64) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu position return overwrite #%u pc=%02x:%04x "
            "logical=%04x physical=%06x old=%04x new=%04x bits=%d "
            "watch=%04x stack=%04x,%04x sp=%04x fp=%04x "
            "DS0=%03x DS1=%03x r0=%04x r1=%04x r2=%04x r3=%04x\n",
            menu_position_return_watch_writes + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            addr & MASK16, actual_physical & MASK24,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            menu_position_return_watch_base,
            internal_data_read(menu_position_return_watch_base, 16),
            internal_data_read(
                (menu_position_return_watch_base + 2u) & MASK16, 16),
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16);
        menu_position_return_watch_writes++;
    }

    if (hardware_init_return_watch_active &&
        actual_physical < (uint32_t)hardware_init_return_watch_base + 4u &&
        actual_physical + bits / 8u > hardware_init_return_watch_base &&
        hardware_init_return_watch_writes < 64) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        env->hardware_init_return_writes =
            hardware_init_return_watch_writes + 1;
        if (!env->hardware_init_return_first_valid) {
            env->hardware_init_return_first_valid = true;
            env->hardware_init_return_first_pc =
                env->current_instruction_pc & MASK24;
            env->hardware_init_return_first_bus = 1;
            env->hardware_init_return_first_logical = addr & MASK16;
            env->hardware_init_return_first_physical =
                actual_physical & MASK24;
            env->hardware_init_return_first_old =
                old_value & width_mask(bits);
            env->hardware_init_return_first_new =
                value & width_mask(bits);
            env->hardware_init_return_first_bits = bits;
            env->hardware_init_return_first_sp =
                env->gpr[DMCU_SP] & MASK16;
            env->hardware_init_return_first_fp =
                env->gpr[DMCU_FP] & MASK16;
        }

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU hardware-init return overwrite #%u bus=translated "
            "pc=%02x:%04x logical=%04x physical=%06x "
            "old=%04x new=%04x bits=%d watch=%04x "
            "stack=%04x,%04x sp=%04x fp=%04x DS0=%03x DS1=%03x\n",
            hardware_init_return_watch_writes + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            addr & MASK16, actual_physical & MASK24,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            hardware_init_return_watch_base,
            internal_data_read(hardware_init_return_watch_base, 16),
            internal_data_read(
                (hardware_init_return_watch_base + 2u) & MASK16, 16),
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff);
        hardware_init_return_watch_writes++;
    }

    if ((actual_physical >= 0x27e528u) &&
        (actual_physical < 0x27e84cu) &&
        !(((env->pc & MASK24) >= 0x010000u &&
           (env->pc & MASK24) < 0x020000u) ||
          ((env->pc & MASK24) >= 0x050000u &&
           (env->pc & MASK24) < 0x070000u) ||
          ((env->pc & MASK24) >= 0x090000u &&
           (env->pc & MASK24) < 0x0a0000u)) &&
        menu_code_overlap_writes < 128) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu code overlap write #%u pc=%02x:%04x "
            "logical=%04x physical=%06x old=%04x new=%04x bits=%d "
            "DS0=%03x DS1=%03x r0=%04x r1=%04x r2=%04x r3=%04x "
            "sp=%04x fp=%04x\n",
            menu_code_overlap_writes + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            addr & MASK16, actual_physical & MASK24,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16);
        menu_code_overlap_writes++;
    }

    /*
     * Observe installation and later replacement of the exact 3D:76CA
     * directory-record resolver at its live 20:76CA destination.  This is a
     * read-only diagnostic: the guest store below is neither suppressed nor
     * changed.  Keeping first and last writers distinguishes a skipped copy
     * from a successful copy that a later overlay phase replaces.
     */
    if (actual_physical >= 0x2076cau && actual_physical < 0x207c56u) {
        if (!env->file_record_overlay_writes) {
            env->file_record_overlay_first_pc = env->pc & MASK24;
            env->file_record_overlay_first_address = actual_physical & MASK24;
            env->file_record_overlay_first_value = value & width_mask(bits);
            env->file_record_overlay_first_bits = bits;
        }
        env->file_record_overlay_writes++;
        env->file_record_overlay_last_pc = env->pc & MASK24;
        env->file_record_overlay_last_address = actual_physical & MASK24;
        env->file_record_overlay_last_value = value & width_mask(bits);
        env->file_record_overlay_last_bits = bits;
    }

    /* The 27:81C8 resource-storage recovery overlay is correct at entry but
     * its AJMP at 27:81E4 can later turn into resource bytes.  Preserve the
     * first installer and most recent writer of that exact word so a data-bus
     * alias error can be distinguished from an unsupported CPU opcode. */
    if (actual_physical < 0x2781e6u &&
        actual_physical + bits / 8u > 0x2781e4u) {
        uint16_t old_word = address_space_lduw_le(
            &address_space_memory, 0x2781e4u,
            MEMTXATTRS_UNSPECIFIED, NULL);

        if (!env->resource_recovery_word_writes) {
            env->resource_recovery_word_first_pc = env->pc & MASK24;
            env->resource_recovery_word_first_address =
                actual_physical & MASK24;
            env->resource_recovery_word_first_old = old_word;
            env->resource_recovery_word_first_value =
                value & width_mask(bits);
            env->resource_recovery_word_first_bits = bits;
        }
        env->resource_recovery_word_writes++;
        env->resource_recovery_word_last_pc = env->pc & MASK24;
        env->resource_recovery_word_last_address = actual_physical & MASK24;
        env->resource_recovery_word_last_old = old_word;
        env->resource_recovery_word_last_value = value & width_mask(bits);
        env->resource_recovery_word_last_bits = bits;
    }

    if ((env->pc & MASK24) >= 0x065b00u &&
        (env->pc & MASK24) < 0x065c2au &&
        menu_state_overlay_writes < 64) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU menu state overlay write #%u pc=%02x:%04x "
                      "physical=%06x value=%04x bits=%d DS0=%03x\n",
                      menu_state_overlay_writes + 1,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      actual_physical & MASK24,
                      value & width_mask(bits), bits,
                      env->sfr[DMCU_SFR_DS0] & 0x1ff);
        menu_state_overlay_writes++;
    }
    if (actual_physical >= 0x30fe0eu && actual_physical < 0x30fee0u &&
        menu_fill_overlay_writes < 8) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU menu fill overlay write #%u pc=%02x:%04x "
                      "physical=%06x value=%04x bits=%d DS0=%03x DS1=%03x\n",
                      menu_fill_overlay_writes + 1,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      actual_physical & MASK24,
                      value & width_mask(bits), bits,
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
        menu_fill_overlay_writes++;
    }

    if (((env->pc & MASK24) >= 0x061d40u &&
         (env->pc & MASK24) < 0x0622a8u) ||
        ((env->pc & MASK24) >= 0x062900u &&
         (env->pc & MASK24) < 0x063a00u)) {
        if (!env->menu_overlay_copy_writes) {
            env->menu_overlay_first_write_pc = env->pc & MASK24;
            env->menu_overlay_first_write_address = actual_physical & MASK24;
            env->menu_overlay_first_write_value = value & width_mask(bits);
        }
        env->menu_overlay_copy_writes++;
        env->menu_overlay_last_write_pc = env->pc & MASK24;
        env->menu_overlay_last_write_address = actual_physical & MASK24;
        env->menu_overlay_last_write_value = value & width_mask(bits);
        if (actual_physical >= 0x2cc9e8u &&
            actual_physical < 0x2ccbcau) {
            env->menu_overlay_entry_writes++;
        }
    }
    if (actual_physical >= 0x2cc9e8u && actual_physical < 0x2ccbcau) {
        env->generic_menu_all_writes++;
        env->generic_menu_last_write_pc = env->pc & MASK24;
        env->generic_menu_last_write_address = actual_physical & MASK24;
        env->generic_menu_last_write_value = value & width_mask(bits);
    }
    if (actual_physical >= 0x200b82u && actual_physical < 0x20161au) {
        if (!env->menu_catalog_all_writes) {
            env->menu_catalog_first_write_pc = env->pc & MASK24;
            env->menu_catalog_first_write_address = actual_physical & MASK24;
            env->menu_catalog_first_write_value = value & width_mask(bits);
        }
        env->menu_catalog_all_writes++;
        env->menu_catalog_last_write_pc = env->pc & MASK24;
        env->menu_catalog_last_write_address = actual_physical & MASK24;
        env->menu_catalog_last_write_value = value & width_mask(bits);
    }

    /*
     * 3B:5084 derives the runtime NAND geometry at 00:04DC..04E2.  The
     * resource updater rejects the device while 04E0:04E2 is zero, so keep a
     * bounded trace of every guest write to this four-word result.  This is
     * diagnostic-only and deliberately runs before the write below.
     */
    if (actual_physical < 0x000004e4u &&
        actual_physical + bits / 8 > 0x000004dcu &&
        storage_geometry_writes < 128) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(LOG_UNIMP,
                      "DMCU storage geometry write #%u %06x "
                      "old=%04x new=%04x bits=%d at %02x:%04x "
                      "logical=%04x DS0=%03x DS1=%03x\n",
                      storage_geometry_writes + 1, actual_physical,
                      old_value & width_mask(bits),
                      value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      addr & MASK16,
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
        storage_geometry_writes++;
    }

    /*
     * The recovered FTL bootstrap publishes its active metadata block and
     * per-quarter allocator state at 00:04E4..04FA.  Logical block zero is
     * represented by the first dword at 00:0286.  Keep these two watches
     * deliberately narrow: they distinguish a failed OOB classification
     * from a later map-page program/read failure without supplying any guest
     * state or replacing the original scanner.
     */
    if (actual_physical < 0x000004fcu &&
        actual_physical + bits / 8 > 0x000004e4u &&
        storage_ftl_state_writes < 192) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(LOG_UNIMP,
                      "DMCU FTL state write #%u %06x old=%04x new=%04x "
                      "bits=%d at %02x:%04x logical=%04x\n",
                      storage_ftl_state_writes + 1, actual_physical,
                      old_value & width_mask(bits),
                      value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      addr & MASK16);
        storage_ftl_state_writes++;
    }
    if (actual_physical < 0x0000028au &&
        actual_physical + bits / 8 > 0x00000286u &&
        storage_ftl_entry_zero_writes < 96) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(LOG_UNIMP,
                      "DMCU FTL entry0 write #%u %06x old=%04x new=%04x "
                      "bits=%d at %02x:%04x logical=%04x\n",
                      storage_ftl_entry_zero_writes + 1, actual_physical,
                      old_value & width_mask(bits),
                      value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      addr & MASK16);
        storage_ftl_entry_zero_writes++;
    }

    /*
     * 42:5858 installs the application storage-list root with DS0=A2 at
     * logical 29C0/29C2.  DMCU data selectors address 32 KiB windows, so
     * that pair is physically 51:29C0/29C2 rather than A2:29C0/29C2.
     * File opens currently observe that far pointer as zero, so retain every
     * bounded value-changing attempt here to distinguish a skipped registry
     * initializer from a later guest-side clear.  This is diagnostic-only;
     * the write below remains the sole source of guest-visible state.
     */
    if (actual_physical < 0x005129c4u &&
        actual_physical + bits / 8 > 0x005129c0u &&
        storage_root_writes < 128) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(LOG_UNIMP,
                      "DMCU storage root write #%u %06x old=%04x new=%04x "
                      "bits=%d at %02x:%04x logical=%04x "
                      "DS0=%03x DS1=%03x\n",
                      storage_root_writes + 1, actual_physical,
                      old_value & width_mask(bits),
                      value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      addr & MASK16,
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
        storage_root_writes++;
    }

    /*
     * The storage registry publishes a 0x26-byte-stride record array rooted
     * at 51:27A0.  The current failing path reaches record 0 with a valid
     * driver-object pointer at +0x22, but that object's +0x06 callback stays
     * zero when unit initialization fails.  Trace every value-changing write across the
     * first four records, not only their headers, so an initializer which
     * selects a field through an indirect pointer cannot escape the watch.
     * This remains diagnostic-only; the actual write below is unchanged.
     */
    if (actual_physical >= 0x005127a0u &&
        actual_physical < 0x00512838u &&
        storage_record_writes < 256) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        if ((old_value & width_mask(bits)) !=
            (value & width_mask(bits))) {
            qemu_log_mask(LOG_UNIMP,
                          "DMCU storage record write #%u %06x "
                          "old=%04x new=%04x bits=%d at %02x:%04x "
                          "logical=%04x DS0=%03x DS1=%03x\n",
                          storage_record_writes + 1, actual_physical,
                          old_value & width_mask(bits),
                          value & width_mask(bits), bits,
                          dmcu_code_segment(env->pc),
                          dmcu_code_pc(env->pc), addr & MASK16,
                          env->sfr[DMCU_SFR_DS0] & 0x1ff,
                          env->sfr[DMCU_SFR_DS1] & 0x1ff);
            storage_record_writes++;
        }
    }

    /* Record 0 streams its on-media device descriptor into 51:1A40 and
     * keeps the current media cursor at A2:29C8/29CA (physical 51:29C8).
     * Trace both ranges without changing guest state so the exact primary
     * reader can be correlated with the NAND page/sector address it chose. */
    if (actual_physical >= 0x00511a40u &&
        actual_physical < 0x00511c40u &&
        storage_descriptor_writes < 1024) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(LOG_UNIMP,
                      "DMCU storage descriptor write #%u %06x "
                      "old=%04x new=%04x bits=%d at %02x:%04x "
                      "logical=%04x DS0=%03x DS1=%03x\n",
                      storage_descriptor_writes + 1, actual_physical,
                      old_value & width_mask(bits),
                      value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      addr & MASK16,
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
        storage_descriptor_writes++;
    }
    if (actual_physical >= 0x005129c8u &&
        actual_physical < 0x005129ccu &&
        storage_cursor_writes < 128) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(LOG_UNIMP,
                      "DMCU storage cursor write #%u %06x "
                      "old=%04x new=%04x bits=%d at %02x:%04x "
                      "logical=%04x DS0=%03x DS1=%03x\n",
                      storage_cursor_writes + 1, actual_physical,
                      old_value & width_mask(bits),
                      value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      addr & MASK16,
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
        storage_cursor_writes++;
    }

    /* Diagnostic-only watch for the native result-selector/launch overlays.
     * Log only their first two instruction words so the reconstructed guest
     * loader and the writable code-alias mapping can be verified without
     * changing guest state or flooding ordinary execution. */
    if ((actual_physical >= 0x2ed34a && actual_physical < 0x2ed34e) ||
        (actual_physical >= 0x319e18 && actual_physical < 0x319e1c)) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU overlay watch %06x=%04x bits=%d at %02x:%04x "
                      "DS0=%03x DS1=%03x\n",
                      actual_physical, value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
    }

    /* Retain only value-changing writes to the application-exit state found
     * by the exact 03:0084 RAM differential.  Byte accesses use swapped A0
     * on this external bus, so report the actual RAM byte address rather than
     * the pre-lane-swap logical address.  This is diagnostic-only and does
     * not alter the guest-visible write. */
    if ((actual_physical >= 0x5128d6 && actual_physical < 0x5128dc) ||
        (actual_physical >= 0x512a80 && actual_physical < 0x512a90) ||
        (actual_physical >= 0x512aaa && actual_physical < 0x512aac) ||
        (actual_physical >= 0x512ab6 && actual_physical < 0x512ab8) ||
        (actual_physical >= 0x512aba && actual_physical < 0x512abc) ||
        (actual_physical >= 0x512ac0 && actual_physical < 0x512ac2) ||
        (actual_physical >= 0x52455c && actual_physical < 0x524572)) {
        uint32_t old_value = bits == 8 ?
            address_space_ldub(&address_space_memory, actual_physical,
                               MEMTXATTRS_UNSPECIFIED, NULL) :
            address_space_lduw_le(&address_space_memory, actual_physical,
                                  MEMTXATTRS_UNSPECIFIED, NULL);

        if ((env->pc & MASK24) == 0x28f6deu &&
            actual_physical == 0x5128dau && bits == 16) {
            env->matrix_event_maps++;
            env->matrix_event_map_pc = env->pc & MASK24;
            env->matrix_event_last = value & MASK16;
        }
        if ((old_value & width_mask(bits)) !=
            (value & width_mask(bits))) {
            if (actual_physical >= 0x52455cu &&
                actual_physical < 0x524572u) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU menu context write %06x old=%04x new=%04x "
                    "bits=%d at %02x:%04x logical=%04x DS0=%03x\n",
                    actual_physical,
                    old_value & width_mask(bits),
                    value & width_mask(bits), bits,
                    dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                    addr & MASK16,
                    env->sfr[DMCU_SFR_DS0] & 0x1ff);
            }
            if (actual_physical == 0x512aaau ||
                actual_physical == 0x512ab6u ||
                actual_physical == 0x512abau ||
                actual_physical == 0x512ac0u) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU application state write %06x old=%04x new=%04x "
                    "bits=%d at %02x:%04x logical=%04x\n",
                    actual_physical,
                    old_value & width_mask(bits),
                    value & width_mask(bits), bits,
                    dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                    addr & MASK16);
            }
            if (actual_physical == 0x512aaau) {
                uint16_t frame = env->gpr[DMCU_FP] & MASK16;
                unsigned int index;

                env->application_state_write_count++;
                env->application_state_write_pc = env->pc & MASK24;
                env->application_state_write_address =
                    actual_physical & MASK24;
                env->application_state_write_old =
                    old_value & width_mask(bits);
                env->application_state_write_new =
                    value & width_mask(bits);
                env->application_state_write_bits = bits;
                env->application_state_write_sp =
                    env->gpr[DMCU_SP] & MASK16;
                env->application_state_write_fp = frame;
                for (index = 0; index < 10; index++) {
                    env->application_state_write_gpr[index] =
                        env->gpr[index] & MASK16;
                }
                for (index = 0; index < 9; index++) {
                    env->application_state_write_frame[index] =
                        internal_data_read((frame + index * 2u) & MASK16, 16);
                }
                memset(env->application_state_write_chain, 0,
                       sizeof(env->application_state_write_chain));
                for (index = 0;
                     index < DMCU_APPLICATION_STATE_WRITE_FRAMES;
                     index++) {
                    unsigned int word_index;

                    env->application_state_write_chain[index][0] = frame;
                    for (word_index = 0; word_index < 9; word_index++) {
                        env->application_state_write_chain[index]
                            [word_index + 1] = internal_data_read(
                                (frame + word_index * 2u) & MASK16, 16);
                    }
                    frame = env->application_state_write_chain[index][1];
                    if (!frame) {
                        break;
                    }
                }
            }
            unsigned selector_slot = env->selector_state_trace_count %
                                     DMCU_SELECTOR_STATE_TRACE_SLOTS;

            env->selector_state_trace_pc[selector_slot] = env->pc & MASK24;
            env->selector_state_trace_address[selector_slot] =
                actual_physical & MASK24;
            env->selector_state_trace_old[selector_slot] =
                old_value & width_mask(bits);
            env->selector_state_trace_new[selector_slot] =
                value & width_mask(bits);
            env->selector_state_trace_bits[selector_slot] = bits;
            env->selector_state_trace_count++;
        }
    }

    /* Source 50:17AE passes 51:2770 as the event-dispatch object.  This bank
     * is writable application RAM, so retain its materialisation history;
     * otherwise a later indirect call only exposes the final malformed far
     * pointer and hides which exact routine installed it. */
    if (physical < 0x512788 && physical + bits / 8 > 0x512770) {
        unsigned object_slot = env->indirect_object_writes %
                               DMCU_INDIRECT_OBJECT_WRITE_SLOTS;
        uint32_t old_value;
        unsigned frame_word;

        if (bits == 8) {
            old_value = address_space_ldub(
                &address_space_memory,
                data_actual_physical_address(env, addr, bits),
                MEMTXATTRS_UNSPECIFIED, NULL);
        } else {
            old_value = address_space_lduw_le(
                &address_space_memory, physical,
                MEMTXATTRS_UNSPECIFIED, NULL);
        }
        env->indirect_object_write_pc[object_slot] = env->pc & MASK24;
        env->indirect_object_write_address[object_slot] = physical & MASK24;
        env->indirect_object_write_old[object_slot] = old_value;
        env->indirect_object_write_new[object_slot] =
            value & width_mask(bits);
        env->indirect_object_write_bits[object_slot] = bits;
        env->indirect_object_write_sp[object_slot] =
            env->gpr[DMCU_SP] & MASK16;
        env->indirect_object_write_fp[object_slot] =
            env->gpr[DMCU_FP] & MASK16;
        for (frame_word = 0;
             frame_word < DMCU_INDIRECT_OBJECT_WRITE_FRAME_WORDS;
             frame_word++) {
            env->indirect_object_write_frame[object_slot][frame_word] =
                internal_data_read(
                    (env->gpr[DMCU_FP] + 6 + frame_word * 2) & MASK16, 16);
        }
        env->indirect_object_writes++;
    }

    /* 51:1E2C is the transient foreground UI-record queue.  The foreground
     * parent clears its header on every pass and 22:FD9E appends records, so
     * polling RAM from the Web API can repeatedly miss a valid short-lived
     * population.  Retain every guest write in a bounded ring instead.  This
     * is read-only diagnostics and does not change the value being stored. */
    if (physical < 0x511f90u && physical + bits / 8 > 0x511e2cu) {
        unsigned record_slot = env->ui_record_writes %
                               DMCU_UI_RECORD_WRITE_SLOTS;
        uint32_t record_old;

        if (bits == 8) {
            record_old = address_space_ldub(
                &address_space_memory,
                data_actual_physical_address(env, addr, bits),
                MEMTXATTRS_UNSPECIFIED, NULL);
        } else {
            record_old = address_space_lduw_le(
                &address_space_memory, physical,
                MEMTXATTRS_UNSPECIFIED, NULL);
        }
        env->ui_record_write_pc[record_slot] = env->pc & MASK24;
        env->ui_record_write_address[record_slot] = physical & MASK24;
        env->ui_record_write_old[record_slot] =
            record_old & width_mask(bits);
        env->ui_record_write_new[record_slot] = value & width_mask(bits);
        env->ui_record_write_bits[record_slot] = bits;
        env->ui_record_write_sp[record_slot] =
            env->gpr[DMCU_SP] & MASK16;
        env->ui_record_write_fp[record_slot] =
            env->gpr[DMCU_FP] & MASK16;
        env->ui_record_writes++;
    }

    /* Preserve value-changing guest writes to the resident state/event
     * manager's count and first four ten-byte registration records.  Ignore
     * the byte-wise zero fill so it cannot evict the actual registrations. */
    if ((physical < 0x512252u && physical + bits / 8 > 0x512250u) ||
        (physical < 0x512292u && physical + bits / 8 > 0x51226au)) {
        unsigned manager_slot = env->manager_state_writes %
                                DMCU_MANAGER_STATE_WRITE_SLOTS;
        uint32_t manager_old;

        if (bits == 8) {
            manager_old = address_space_ldub(
                &address_space_memory,
                data_actual_physical_address(env, addr, bits),
                MEMTXATTRS_UNSPECIFIED, NULL);
        } else {
            manager_old = address_space_lduw_le(
                &address_space_memory, physical,
                MEMTXATTRS_UNSPECIFIED, NULL);
        }
        if ((manager_old & width_mask(bits)) !=
            (value & width_mask(bits))) {
            env->manager_state_write_pc[manager_slot] = env->pc & MASK24;
            env->manager_state_write_address[manager_slot] =
                physical & MASK24;
            env->manager_state_write_old[manager_slot] =
                manager_old & width_mask(bits);
            env->manager_state_write_new[manager_slot] =
                value & width_mask(bits);
            env->manager_state_write_bits[manager_slot] = bits;
            env->manager_state_write_sp[manager_slot] =
                env->gpr[DMCU_SP] & MASK16;
            env->manager_state_write_fp[manager_slot] =
                env->gpr[DMCU_FP] & MASK16;
            env->manager_state_writes++;
        }
    }

    if (env->event_frame_watch_active && !env->event_frame_write_valid &&
        physical < 0x10000 &&
        backing_addr < env->event_frame_base + 4 &&
        backing_addr + bits / 8 > env->event_frame_base) {
        env->event_frame_write_valid = true;
        env->event_frame_write_pc = env->pc & MASK24;
        env->event_frame_write_address = backing_addr & MASK16;
        env->event_frame_write_old =
            internal_data_read(backing_addr, bits);
        env->event_frame_write_new = value & width_mask(bits);
        env->event_frame_write_bits = bits;
        env->event_frame_write_sp = env->gpr[DMCU_SP] & MASK16;
        env->event_frame_write_fp = env->gpr[DMCU_FP] & MASK16;
    }

    if (physical < 0x32e8b0 && physical + bits / 8 > 0x32e86e) {
        if (!env->event_text_write_count) {
            env->event_text_first_pc = env->pc & MASK24;
            env->event_text_first_address = physical & MASK24;
            env->event_text_first_value = value & width_mask(bits);
            env->event_text_first_bits = bits;
        }
        env->event_text_write_count++;
        env->event_text_last_pc = env->pc & MASK24;
        env->event_text_last_address = physical & MASK24;
        env->event_text_last_value = value & width_mask(bits);
        env->event_text_last_bits = bits;
        if (!env->event_text_overwrite_valid &&
            (env->pc & MASK24) >= 0x2e4572 &&
            (env->pc & MASK24) < 0x2e46f6) {
            env->event_text_overwrite_valid = true;
            env->event_text_overwrite_pc = env->pc & MASK24;
            env->event_text_overwrite_destination = physical & MASK24;
            env->event_text_overwrite_source =
                data_physical_address(env, env->gpr[9]) & MASK24;
            env->event_text_overwrite_r1 = env->gpr[1] & MASK16;
            env->event_text_overwrite_r8 = env->gpr[8] & MASK16;
            env->event_text_overwrite_r9 = env->gpr[9] & MASK16;
            env->event_text_overwrite_sp = env->gpr[DMCU_SP] & MASK16;
            env->event_text_overwrite_fp = env->gpr[DMCU_FP] & MASK16;
        }
    }

    if (physical < 0x51291a && physical + bits / 8 > 0x512914) {
        unsigned slot = env->font_config_trace_count %
                        DMCU_FONT_CONFIG_TRACE_SLOTS;

        env->font_config_trace_pc[slot] = env->pc & MASK24;
        env->font_config_trace_address[slot] = physical & MASK24;
        env->font_config_trace_value[slot] = value & width_mask(bits);
        env->font_config_trace_bits[slot] = bits;
        env->font_config_trace_count++;
    }

    if (actual_physical < 0x503840 &&
        actual_physical + bits / 8 > 0x500000) {
        uint32_t old_count = env->native_back_nonzero_bytes;
        unsigned byte_index;

        for (byte_index = 0; byte_index < bits / 8; byte_index++) {
            uint32_t byte_address = actual_physical + byte_index;
            uint8_t old_value;
            uint8_t new_value;

            if (byte_address < 0x500000 || byte_address >= 0x503840) {
                continue;
            }
            old_value = address_space_ldub(
                &address_space_memory, byte_address,
                MEMTXATTRS_UNSPECIFIED, NULL);
            new_value = value >> (byte_index * 8);
            if (!old_value && new_value) {
                env->native_back_nonzero_bytes++;
            } else if (old_value && !new_value &&
                       env->native_back_nonzero_bytes) {
                env->native_back_nonzero_bytes--;
            }
        }
        env->native_back_peak_nonzero_bytes =
            MAX(env->native_back_peak_nonzero_bytes,
                env->native_back_nonzero_bytes);
        env->native_back_last_write_pc = env->current_instruction_pc & MASK24;
        if (!old_count && env->native_back_nonzero_bytes) {
            env->native_back_rises++;
            env->native_back_last_rise_pc =
                env->current_instruction_pc & MASK24;
        } else if (old_count && !env->native_back_nonzero_bytes) {
            uint32_t fp = env->gpr[DMCU_FP] & MASK16;

            env->native_back_clears++;
            env->native_back_last_clear_pc =
                env->current_instruction_pc & MASK24;
            env->native_back_clear_from =
                ((internal_data_read((fp + 2) & MASK16, 16) & 0xff) << 16) |
                internal_data_read((fp + 4) & MASK16, 16);
            env->native_back_clear_destination =
                (internal_data_read((fp + 6) & MASK16, 16) << 16) |
                internal_data_read((fp + 8) & MASK16, 16);
            env->native_back_clear_source =
                (internal_data_read((fp + 10) & MASK16, 16) << 16) |
                internal_data_read((fp + 12) & MASK16, 16);
            env->native_back_clear_length =
                internal_data_read((fp + 14) & MASK16, 16);
        }
    }

    if (actual_physical < 0x507080 &&
        actual_physical + bits / 8 > 0x503840) {
        uint32_t old_count = env->native_fb_nonzero_bytes;
        unsigned byte_index;

        for (byte_index = 0; byte_index < bits / 8; byte_index++) {
            uint32_t byte_address = actual_physical + byte_index;
            uint8_t old_value;
            uint8_t new_value;

            if (byte_address < 0x503840 || byte_address >= 0x507080) {
                continue;
            }
            old_value = address_space_ldub(
                &address_space_memory, byte_address,
                MEMTXATTRS_UNSPECIFIED, NULL);
            new_value = value >> (byte_index * 8);
            if (!old_value && new_value) {
                env->native_fb_nonzero_bytes++;
            } else if (old_value && !new_value &&
                       env->native_fb_nonzero_bytes) {
                env->native_fb_nonzero_bytes--;
            }
        }
        env->native_fb_peak_nonzero_bytes =
            MAX(env->native_fb_peak_nonzero_bytes,
                env->native_fb_nonzero_bytes);
        env->native_fb_last_write_pc = env->current_instruction_pc & MASK24;
        if (!old_count && env->native_fb_nonzero_bytes) {
            env->native_fb_rises++;
            env->native_fb_last_rise_pc =
                env->current_instruction_pc & MASK24;
        } else if (old_count && !env->native_fb_nonzero_bytes) {
            uint32_t fp = env->gpr[DMCU_FP] & MASK16;

            env->native_fb_clears++;
            env->native_fb_last_clear_pc =
                env->current_instruction_pc & MASK24;
            env->native_fb_clear_from =
                ((internal_data_read((fp + 2) & MASK16, 16) & 0xff) << 16) |
                internal_data_read((fp + 4) & MASK16, 16);
            env->native_fb_clear_destination =
                (internal_data_read((fp + 6) & MASK16, 16) << 16) |
                internal_data_read((fp + 8) & MASK16, 16);
            env->native_fb_clear_source =
                (internal_data_read((fp + 10) & MASK16, 16) << 16) |
                internal_data_read((fp + 12) & MASK16, 16);
            env->native_fb_clear_length =
                internal_data_read((fp + 14) & MASK16, 16);
        }
    }

    if (actual_physical >= 0x503840 && actual_physical < 0x507080 &&
        (value & width_mask(bits)) != 0 &&
        framebuffer_writes < 128) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU framebuffer write %06x=%04x bits=%d "
                      "at %02x:%04x DS0=%03x DS1=%03x\n",
                      actual_physical, value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
        framebuffer_writes++;
    }

    /* The vendor updater derives its writable NFTL interval in 07ea/07ec.
     * Keep this as an opt-in execution log instead of changing guest state:
     * an indirect memset can otherwise hide which command discarded the
     * interval established by 51:8d8a. */
    if (bits == 16 && (physical == 0x5007ea || physical == 0x5007ec)) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU partition bound write %06x=%04x at %02x:%04x "
                      "DS0=%03x DS1=%03x\n",
                      physical, value & MASK16,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
    }

    /*
     * Object zero is the first storage object rejected by 50:B0B2.  Its
     * descriptor points at 50:02A6 (backing/template state) and 50:0806
     * (the 0x18-byte materialised record).  Watch only those two short
     * ranges so an opt-in trace can distinguish never-initialised data from
     * data cleared by a later command without flooding normal execution.
     */
    if ((physical >= 0x5002a6 && physical < 0x5002be) ||
        (physical >= 0x500806 && physical < 0x50081e)) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU object0 write %06x=%04x bits=%d "
                      "at %02x:%04x DS0=%03x DS1=%03x\n",
                      physical, value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
    }

    /* Keep the most recent vendor NFTL status write.  The command wrapper
     * later translates this value into the public result at 50:001a, so
     * tracing only 0xfff6 there loses the original failure site. */
    if (bits == 16 && physical == 0x500860) {
        env->burn_error_writes++;
        env->burn_error_pc = env->pc & MASK24;
        env->burn_error_value = value & MASK16;
    }

    if (physical == 0x512924 || physical == 0x512925 ||
        physical == 0x512926 || physical == 0x512927) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU display metric write %06x=%04x bits=%d "
                      "at %02x:%04x DS0=%03x DS1=%03x\n",
                      physical, value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
    }

    if (bits == 16 && (physical == 0x512aa4 || physical == 0x512aa6)) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU app tick state write %06x=%04x at %02x:%04x "
                      "DS0=%03x DS1=%03x\n",
                      physical, value & MASK16,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
    }
    /* Keep the recovered resource-lifecycle wrapper auditable while the
     * missing ROM loader ordering is being reconstructed.  This is log-only:
     * the write and executable RAM alias remain entirely guest controlled. */
    if (physical >= 0x33524c && physical < 0x33525e) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU resource storage overlay write %06x=%04x/%d "
                      "at %02x:%04x DS0=%03x DS1=%03x\n",
                      physical, value & width_mask(bits), bits,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
    }
    /* Observe the application/file-system globals which distinguish a
     * resource-open failure from a later application-state reset.  This is
     * deliberately log-only: strict guest execution and memory contents are
     * unchanged. */
    if (bits == 16 &&
        (physical == 0x507090 || physical == 0x507092 ||
         physical == 0x5070be || physical == 0x5070c0 ||
         physical == 0x507dee || physical == 0x507df0 ||
         physical == 0x512984 || physical == 0x512986 ||
         physical == 0x512ab6)) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU resource global write %06x=%04x at %02x:%04x "
                      "DS0=%03x DS1=%03x\n",
                      physical, value & MASK16,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
    }
    if (bits == 8) {
        cpu_stb_data(env, backing_addr, value);
    } else {
        cpu_stw_data(env, backing_addr, value);
    }
    trace_outer_context_data(env, addr, value, bits, true);
}

static inline uint32_t data_read(CPUDMCUState *env, uint32_t addr, int bits)
{
    uint32_t logical = addr & MASK16;
    uint32_t physical = data_physical_address(env, addr);

    /*
     * Direct mem operands expose R0..R15 through F2E0..F2FE.  Register-
     * indirect [Rn] operands use the translated data bus even when they
     * happen to resolve to the same 24-bit number; pointer_read/write below
     * deliberately bypass this direct-register alias.
     */
    if (bits == 16 && logical >= 0xf2e0 && logical <= 0xf2fe &&
        !(logical & 1) && physical == logical) {
        return env->gpr[(physical - 0xf2e0) >> 1] & MASK16;
    }
    return translated_data_read(env, addr, bits);
}

static inline void data_write(CPUDMCUState *env, uint32_t addr,
                              uint32_t value, int bits)
{
    uint32_t logical = addr & MASK16;
    uint32_t physical = data_physical_address(env, addr);

    if (bits == 16 && logical >= 0xf2e0 && logical <= 0xf2fe &&
        !(logical & 1) && physical == logical) {
        env->gpr[(physical - 0xf2e0) >> 1] = value & MASK16;
        return;
    }
    translated_data_write(env, addr, value, bits);
}

static inline uint32_t internal_data_read(uint32_t addr, int bits)
{
    DMCUCPU *cpu = DMCU_CPU(current_cpu);
    uint32_t logical = addr & MASK16;
    uint32_t backing = bits == 8 ? logical ^ 1u : logical;
    uint8_t *physical = cpu->internal_data + backing;

    /*
     * R11/R15 frame and stack operands use the DMCU's unbanked internal
     * SRAM path.  They must not be dispatched through the board data bus:
     * doing so lets an MMIO window at the same numeric address consume a
     * saved FP or return PC.  Byte operands nevertheless retain the DMCU's
     * high-byte-first lane numbering.  This is required for a bank-zero far
     * pointer to alias a byte local addressed through R11/R15: the shipped
     * 18:6D56 memcpy writes selector 00, offset FP-1 through the translated
     * bus and the caller immediately consumes the same byte as [R11-1].
     * Ordinary direct/indirect data operands use translated_data_read() and
     * therefore continue to see peripherals and the same word lanes.
     */
    return bits == 8 ? ldub_p(physical) : lduw_le_p(physical);
}

void dmcu_file_component_record_stack_write(CPUDMCUState *env,
                                            uint32_t logical,
                                            uint32_t backing,
                                            uint32_t old_value,
                                            uint32_t value,
                                            int bits,
                                            uint8_t source)
{
    uint32_t base;
    uint32_t limit;
    uint32_t width = bits / 8;
    uint32_t sequence;
    uint32_t slot;

    if (!env->file_component_watch_active) {
        return;
    }

    base = ((env->file_component_entry_fp & MASK16) - 0x10u) & MASK16;
    limit = base + DMCU_FILE_COMPONENT_FRAME_WORDS * 2u;
    if (base + DMCU_FILE_COMPONENT_FRAME_WORDS * 2u > 0x10000u ||
        backing >= limit || backing + width <= base) {
        return;
    }

    sequence = env->file_component_write_count++;
    slot = sequence % DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS;
    env->file_component_write_pc[slot] =
        source ? env->pc & MASK24 : env->current_instruction_pc & MASK24;
    env->file_component_write_logical[slot] = logical & MASK16;
    env->file_component_write_backing[slot] = backing & MASK16;
    env->file_component_write_old[slot] = old_value & width_mask(bits);
    env->file_component_write_new[slot] = value & width_mask(bits);
    env->file_component_write_sp[slot] = env->gpr[DMCU_SP] & MASK16;
    env->file_component_write_fp[slot] = env->gpr[DMCU_FP] & MASK16;
    env->file_component_write_bits[slot] = bits;
    env->file_component_write_source[slot] = source;
    env->file_component_write_in_irq[slot] = env->in_interrupt;
}

void dmcu_file_wrapper_record_stack_write(CPUDMCUState *env,
                                          uint32_t logical,
                                          uint32_t backing,
                                          uint32_t old_value,
                                          uint32_t value,
                                          int bits,
                                          uint8_t source)
{
    uint32_t base = env->file_wrapper_frame_base & MASK16;
    uint32_t width = bits / 8u;
    uint32_t sequence;
    uint32_t slot;

    if (!env->file_wrapper_frame_watch_active ||
        backing >= base + 0x0cu || backing + width <= base) {
        return;
    }
    sequence = env->file_wrapper_frame_writes++;
    slot = sequence % DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS;
    env->file_wrapper_frame_write_pc[slot] =
        source ? env->pc & MASK24 : env->current_instruction_pc & MASK24;
    env->file_wrapper_frame_write_logical[slot] = logical & MASK16;
    env->file_wrapper_frame_write_backing[slot] = backing & MASK16;
    env->file_wrapper_frame_write_old[slot] = old_value & width_mask(bits);
    env->file_wrapper_frame_write_new[slot] = value & width_mask(bits);
    env->file_wrapper_frame_write_sp[slot] = env->gpr[DMCU_SP] & MASK16;
    env->file_wrapper_frame_write_fp[slot] = env->gpr[DMCU_FP] & MASK16;
    env->file_wrapper_frame_write_bits[slot] = bits;
    env->file_wrapper_frame_write_source[slot] = source;
    env->file_wrapper_frame_write_in_irq[slot] = env->in_interrupt;
}

static inline void internal_data_write(uint32_t addr, uint32_t value,
                                       int bits)
{
    static bool input_object_watch_active;
    static unsigned input_object_internal_writes;
    static bool menu_layout_watch_active;
    static unsigned menu_layout_internal_writes;
    static unsigned framebuffer_pointer_internal_writes;
    DMCUCPU *cpu = DMCU_CPU(current_cpu);
    CPUDMCUState *env = &cpu->env;
    uint32_t logical = addr & MASK16;
    uint32_t backing = bits == 8 ? logical ^ 1u : logical;
    uint8_t *physical = cpu->internal_data + backing;
    uint32_t width = bits / 8;

    trace_clock_format_output_write(
        env, logical,
        bits == 8 ? ldub_p(physical) : lduw_le_p(physical),
        value, bits, 0);

    trace_root_object_slot_write(
        env, backing, bits == 8 ? ldub_p(physical) : lduw_le_p(physical),
        value, bits, 0, env->current_instruction_pc);

    dmcu_file_component_record_stack_write(
        env, logical, backing,
        bits == 8 ? ldub_p(physical) : lduw_le_p(physical),
        value, bits, 0);
    dmcu_file_wrapper_record_stack_write(
        env, logical, backing,
        bits == 8 ? ldub_p(physical) : lduw_le_p(physical),
        value, bits, 0);
    dmcu_application_file_attach_record_frame_write(
        env, backing,
        bits == 8 ? ldub_p(physical) : lduw_le_p(physical),
        value, bits, 0);

    trace_operation_object_write(env, logical, value, bits, "internal");

    if (env->application_init_frame_watch_active &&
        backing < (env->application_init_frame_base & MASK16) + 6u &&
        backing + width > (env->application_init_frame_base & MASK16)) {
        uint32_t old_value = bits == 8 ?
            ldub_p(physical) : lduw_le_p(physical);

        trace_application_init_frame_write(
            env, backing, old_value, value, bits, IRQ_SAVE_FP_BUS_INTERNAL);
    }

    if (env->graphics_frame_watch_active) {
        uint32_t limit = (env->graphics_frame_base - 0x20u) & MASK16;

        if (backing < limit + 2u && backing + width > limit) {
            env->graphics_frame_limit_writes++;
            env->graphics_frame_limit_last_pc =
                env->current_instruction_pc & MASK24;
            env->graphics_frame_limit_last_old = bits == 8 ?
                ldub_p(physical) : lduw_le_p(physical);
            env->graphics_frame_limit_last_new = value & width_mask(bits);
            env->graphics_frame_limit_last_bits = bits;
        }
    }

    if (hardware_init_return_watch_active &&
        backing < (uint32_t)hardware_init_return_watch_base + 4u &&
        backing + width > hardware_init_return_watch_base &&
        hardware_init_return_watch_writes < 64) {
        uint32_t old_value = bits == 8 ?
            ldub_p(physical) : lduw_le_p(physical);

        env->hardware_init_return_writes =
            hardware_init_return_watch_writes + 1;
        if (!env->hardware_init_return_first_valid) {
            env->hardware_init_return_first_valid = true;
            env->hardware_init_return_first_pc =
                env->current_instruction_pc & MASK24;
            env->hardware_init_return_first_bus = 0;
            env->hardware_init_return_first_logical = logical;
            env->hardware_init_return_first_physical = backing;
            env->hardware_init_return_first_old =
                old_value & width_mask(bits);
            env->hardware_init_return_first_new =
                value & width_mask(bits);
            env->hardware_init_return_first_bits = bits;
            env->hardware_init_return_first_sp =
                env->gpr[DMCU_SP] & MASK16;
            env->hardware_init_return_first_fp =
                env->gpr[DMCU_FP] & MASK16;
        }

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU hardware-init return overwrite #%u bus=internal "
            "pc=%02x:%04x logical=%04x backing=%04x "
            "old=%04x new=%04x bits=%d watch=%04x "
            "stack=%04x,%04x sp=%04x fp=%04x\n",
            hardware_init_return_watch_writes + 1,
            dmcu_code_segment(env->current_instruction_pc),
            dmcu_code_pc(env->current_instruction_pc), logical, backing,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            hardware_init_return_watch_base,
            internal_data_read(hardware_init_return_watch_base, 16),
            internal_data_read(
                (hardware_init_return_watch_base + 2u) & MASK16, 16),
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16);
        hardware_init_return_watch_writes++;
    }

    if (logical < 0x0500u && logical + width > 0x04fcu &&
        framebuffer_pointer_internal_writes < 64) {
        uint32_t old_value = bits == 8 ?
            ldub_p(physical) : lduw_le_p(physical);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU framebuffer pointer write #%u bus=internal "
            "pc=%02x:%04x logical=%04x physical=%06x "
            "old=%04x new=%04x bits=%d DS0=%03x DS1=%03x\n",
            framebuffer_pointer_internal_writes + 1,
            dmcu_code_segment(env->current_instruction_pc),
            dmcu_code_pc(env->current_instruction_pc), logical, backing,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff);
        framebuffer_pointer_internal_writes++;
    }

    if (env->in_interrupt && env->interrupt_frame_watch_active &&
        backing < (env->interrupt_frame_base & MASK16) + 6u &&
        backing + width > (env->interrupt_frame_base & MASK16)) {
        uint32_t old_value = bits == 8 ?
            ldub_p(physical) : lduw_le_p(physical);

        trace_interrupt_frame_write(env, backing, old_value, value, bits);
    }
    if (env->in_interrupt && env->interrupt_frame_watch_active &&
        backing <
            (env->interrupt_foreground_fp_address & MASK16) + 2u &&
        backing + width >
            (env->interrupt_foreground_fp_address & MASK16)) {
        uint32_t old_value = bits == 8 ?
            ldub_p(physical) : lduw_le_p(physical);

        trace_interrupt_foreground_fp_write(
            env, backing, old_value, value, bits);
    }
    if (env->in_interrupt && logical < 0x04d8u &&
        logical + width > 0x04d6u) {
        uint32_t old_value = bits == 8 ?
            ldub_p(physical) : lduw_le_p(physical);

        trace_irq_save_fp_write(env, logical, backing, old_value, value, bits,
                                IRQ_SAVE_FP_BUS_INTERNAL);
    }
    if (bits == 16 && (logical == 0x4a36u || logical == 0x4a38u)) {
        trace_resource_range_write(
            env, logical, backing, lduw_le_p(physical), value, bits,
            RESOURCE_RANGE_BUS_INTERNAL);
    } else if (bits == 8 && logical >= 0x4a36u && logical < 0x4a3au) {
        trace_resource_range_write(
            env, logical, backing, ldub_p(physical), value, bits,
            RESOURCE_RANGE_BUS_INTERNAL);
    }

    /* The generic-menu renderer reaches 30:09C8 with a malformed rectangle.
     * Watch the four coordinate locals in its 30:05C2..06A0 layout pass so
     * we can distinguish a bad calculation from a later stack overwrite. */
    if ((env->pc & MASK24) >= dmcu_code_address(0x30, 0x0500) &&
        (env->pc & MASK24) <= dmcu_code_address(0x30, 0x06a4) &&
        (env->gpr[DMCU_FP] & MASK16) == 0xff52) {
        menu_layout_watch_active = true;
    }
    if (menu_layout_watch_active && logical >= 0xff42u &&
        logical < 0xff4au && menu_layout_internal_writes < 128) {
        uint32_t old_value = bits == 8 ?
            ldub_p(physical) : lduw_le_p(physical);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu layout local write #%u address=%04x old=%04x "
            "new=%04x bits=%d at %02x:%04x sp=%04x fp=%04x\n",
            menu_layout_internal_writes + 1, logical,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            env->gpr[DMCU_SP] & MASK16,
            env->gpr[DMCU_FP] & MASK16);
        menu_layout_internal_writes++;
    }

    if ((env->pc & MASK24) >= dmcu_code_address(0x32, 0xf0ee) &&
        (env->pc & MASK24) <= dmcu_code_address(0x32, 0xff00) &&
        (env->gpr[DMCU_FP] & MASK16) == 0xfe80) {
        input_object_watch_active = true;
    }
    if (input_object_watch_active && logical < 0xfe5au &&
        logical + width > 0xfe32u && input_object_internal_writes < 512) {
        uint32_t old_value = bits == 8 ?
            ldub_p(physical) : lduw_le_p(physical);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU input object write #%u address=%04x old=%04x new=%04x "
            "bits=%d at %02x:%04x sp=%04x fp=%04x\n",
            input_object_internal_writes + 1, logical,
            old_value & width_mask(bits), value & width_mask(bits), bits,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            env->gpr[DMCU_SP] & MASK16,
            env->gpr[DMCU_FP] & MASK16);
        input_object_internal_writes++;
    }

    if (env->event_frame_watch_active && !env->event_frame_write_valid &&
        logical < env->event_frame_base + 4 &&
        logical + width > env->event_frame_base) {
        env->event_frame_write_valid = true;
        env->event_frame_write_pc = env->pc & MASK24;
        env->event_frame_write_address = logical;
        env->event_frame_write_old = bits == 8 ?
            ldub_p(physical) : lduw_le_p(physical);
        env->event_frame_write_new = value & width_mask(bits);
        env->event_frame_write_bits = bits;
        env->event_frame_write_sp = env->gpr[DMCU_SP] & MASK16;
        env->event_frame_write_fp = env->gpr[DMCU_FP] & MASK16;
    }

    if (bits == 8) {
        stb_p(physical, value);
    } else {
        stw_le_p(physical, value);
    }
}

static inline bool is_stack_pointer(unsigned reg)
{
    return reg == DMCU_FP || reg == DMCU_SP;
}

static inline uint32_t pointer_read(CPUDMCUState *env, unsigned reg,
                                    uint32_t addr, int bits)
{
    return is_stack_pointer(reg) ? internal_data_read(addr, bits) :
                                   translated_data_read(env, addr, bits);
}

static inline void pointer_write(CPUDMCUState *env, unsigned reg,
                                 uint32_t addr, uint32_t value, int bits)
{
    if (is_stack_pointer(reg)) {
        internal_data_write(addr, value, bits);
    } else {
        translated_data_write(env, addr, value, bits);
    }
}

static inline void push(CPUDMCUState *env, uint32_t value)
{
    env->gpr[DMCU_SP] = (env->gpr[DMCU_SP] - 2) & 0xffff;
    internal_data_write(env->gpr[DMCU_SP], value, 16);
}

static inline uint32_t pop(CPUDMCUState *env)
{
    uint32_t value = internal_data_read(env->gpr[DMCU_SP], 16);
    env->gpr[DMCU_SP] = (env->gpr[DMCU_SP] + 2) & 0xffff;
    return value;
}

static inline void near_return_push(CPUDMCUState *env, uint32_t pc)
{
    push(env, dmcu_code_pc(pc));
}

static inline void far_return_push(CPUDMCUState *env, uint32_t pc)
{
    /* SCALL pushes PC first and CS second, leaving CS at the top. */
    push(env, dmcu_code_pc(pc));
    push(env, dmcu_code_segment(pc));
}

static inline uint32_t near_return_pop(CPUDMCUState *env)
{
    return dmcu_code_address(dmcu_code_segment(env->pc), pop(env));
}

static inline uint32_t far_return_pop(CPUDMCUState *env)
{
    uint32_t cs = pop(env) & 0xff;
    uint32_t pc = pop(env);

    return dmcu_code_address(cs, pc);
}

static inline bool flag(CPUDMCUState *env, uint32_t mask)
{
    return (env->psw & mask) != 0;
}

static inline void set_flag(CPUDMCUState *env, uint32_t mask, bool value)
{
    env->psw = value ? env->psw | mask : env->psw & ~mask;
}

static inline void logic_flags(CPUDMCUState *env, uint32_t result, int bits)
{
    uint32_t mask = width_mask(bits);
    uint32_t sign = width_sign(bits);
    result &= mask;
    set_flag(env, DMCU_PSW_Z, result == 0);
    set_flag(env, DMCU_PSW_N, result & sign);
    set_flag(env, DMCU_PSW_C, false);
    set_flag(env, DMCU_PSW_V, false);
}

static uint32_t alu_add(CPUDMCUState *env, uint32_t left, uint32_t right,
                        uint32_t carry, int bits, bool chained_z)
{
    uint32_t mask = width_mask(bits);
    uint32_t sign = width_sign(bits);
    uint32_t total = left + right + carry;
    uint32_t result = total & mask;
    bool old_z = flag(env, DMCU_PSW_Z);

    set_flag(env, DMCU_PSW_C, total > mask);
    set_flag(env, DMCU_PSW_V,
             (~(left ^ right) & (left ^ result) & sign) != 0);
    set_flag(env, DMCU_PSW_N, result & sign);
    set_flag(env, DMCU_PSW_Z, chained_z ? old_z && result == 0 : result == 0);
    return result;
}

static uint32_t alu_sub(CPUDMCUState *env, uint32_t left, uint32_t right,
                        uint32_t borrow, int bits, bool chained_z)
{
    uint32_t mask = width_mask(bits);
    uint32_t sign = width_sign(bits);
    uint32_t subtrahend = right + borrow;
    uint32_t result = (left - subtrahend) & mask;
    bool old_z = flag(env, DMCU_PSW_Z);

    set_flag(env, DMCU_PSW_C, left < subtrahend); /* C is borrow. */
    set_flag(env, DMCU_PSW_V,
             ((left ^ right) & (left ^ result) & sign) != 0);
    set_flag(env, DMCU_PSW_N, result & sign);
    set_flag(env, DMCU_PSW_Z, chained_z ? old_z && result == 0 : result == 0);
    return result;
}

static uint32_t alu(CPUDMCUState *env, unsigned operation,
                    uint32_t left, uint32_t right, int bits)
{
    uint32_t mask = width_mask(bits);
    uint32_t result;

    left &= mask;
    right &= mask;
    switch (operation) {
    case 0: return alu_add(env, left, right, 0, bits, false);
    case 1: return alu_add(env, left, right, flag(env, DMCU_PSW_C),
                           bits, true);
    case 2: return alu_sub(env, left, right, 0, bits, false);
    case 3: return alu_sub(env, left, right, flag(env, DMCU_PSW_C),
                           bits, true);
    case 4: result = left & right; break;
    case 5: result = left | right; break;
    case 6: return alu_sub(env, left, right, 0, bits, false);
    case 7: result = left ^ right; break;
    default: g_assert_not_reached();
    }
    logic_flags(env, result, bits);
    return result & mask;
}

static bool condition(CPUDMCUState *env, unsigned code)
{
    bool z = flag(env, DMCU_PSW_Z);
    bool c = flag(env, DMCU_PSW_C);
    bool n = flag(env, DMCU_PSW_N);
    bool v = flag(env, DMCU_PSW_V);

    switch (code) {
    case 0x0: return true;
    case 0x1: return z;
    case 0x2: return !z;
    case 0x3: return v;
    case 0x4: return !v;
    case 0x5: return c;
    case 0x6: return !c;
    case 0x7: return n;
    case 0x8: return !n;
    case 0x9: return n != v;
    case 0xa: return !(z || c);
    case 0xb: return !((n != v) || z);
    case 0xc: return z || c;
    case 0xd: return (n != v) || z;
    case 0xe: return n == v;
    default: return false;
    }
}

static inline uint32_t near_pc(uint32_t pc, uint32_t low)
{
    return dmcu_code_address(dmcu_code_segment(pc), low);
}

static inline uint32_t bit_read(CPUDMCUState *env, uint32_t addr,
                                unsigned bitno)
{
    /* bitoff 00..7F names SFR 80..FF; 70..7F therefore maps R0..R15. */
    return (sfr_read(env, (addr | 0x80) & 0xff, 16) >>
            (bitno & 15)) & 1;
}

static inline void bit_write(CPUDMCUState *env, uint32_t addr,
                             unsigned bitno, bool value)
{
    unsigned reg = (addr | 0x80) & 0xff;
    uint32_t current = sfr_read(env, reg, 16);
    uint32_t mask = 1u << (bitno & 15);

    sfr_write(env, reg, value ? current | mask : current & ~mask, 16);
}

static void unsupported(CPUDMCUState *env, uint32_t pc, uint16_t word)
{
    CPUState *cs = env_cpu(env);
    bool first = !env->unsupported_valid;

    if (!env->unsupported_valid) {
        env->unsupported_predecessor_pc = env->completed_instruction_pc;
        env->unsupported_predecessor_next_pc =
            env->completed_instruction_next_pc;
        env->unsupported_predecessor_word = env->completed_instruction_word;
        env->unsupported_predecessor_ext = env->completed_instruction_ext;
        env->unsupported_predecessor_sp = env->gpr[DMCU_SP];
        env->unsupported_predecessor_fp = env->gpr[DMCU_FP];
    }
    env->unsupported_valid = true;
    env->unsupported_pc = pc & MASK24;
    env->unsupported_word = word;
    env->unsupported_count++;
    env->pc = pc & MASK24;
    if (first) {
        env->control_trace_frozen = true;
        qemu_log_mask(LOG_UNIMP,
                      "DMCU unsupported instruction %04x at %02x:%04x\n",
                      word, dmcu_code_segment(pc), dmcu_code_pc(pc));
    }
    cs->halted = 1;
    cs->exception_index = EXCP_HLT;
    cpu_loop_exit(cs);
}

static bool exec_alu(CPUDMCUState *env, uint8_t op, uint8_t arg,
                     uint16_t ext)
{
    unsigned operation = op & 15;
    unsigned hi = op >> 4;
    bool byte_mode;
    int bits;
    uint32_t left, right, result, dst;
    enum { DST_GPR, DST_SFR, DST_MEM } dst_kind;

    if (operation > 7) {
        return false;
    }
    byte_mode = hi == 0 || hi == 2 || hi == 4 ||
                hi == 6 || hi == 8 || hi == 10;
    bits = byte_mode ? 8 : 16;

    if (hi == 0 || hi == 1) {
        dst_kind = DST_GPR;
        dst = arg >> 4;
        left = reg_read(env, dst, bits);
        right = reg_read(env, arg, bits);
    } else if (hi == 2 || hi == 3) {
        unsigned ptrreg = 8 + (arg & 7);
        uint32_t ptr = env->gpr[ptrreg];
        dst_kind = DST_GPR;
        dst = arg >> 4;
        left = reg_read(env, dst, bits);
        right = pointer_read(env, ptrreg, ptr, bits);
        if (arg & 8) {
            env->gpr[ptrreg] = (ptr + bits / 8) & MASK16;
        }
    } else if (hi == 4 || hi == 5) {
        dst_kind = DST_GPR;
        dst = arg >> 4;
        left = reg_read(env, dst, bits);
        right = arg & 15;
    } else if (hi == 6 || hi == 7) {
        dst_kind = DST_SFR;
        dst = arg;
        left = sfr_read(env, dst, bits);
        right = ext & (byte_mode ? 0xff : 0xffff);
    } else if (hi == 8 || hi == 9) {
        dst_kind = DST_SFR;
        dst = arg;
        left = sfr_read(env, dst, bits);
        right = data_read(env, ext, bits);
    } else if ((hi == 10 || hi == 11) && operation != 6) {
        dst_kind = DST_MEM;
        dst = ext;
        left = data_read(env, dst, bits);
        right = sfr_read(env, arg, bits);
    } else {
        return false;
    }

    result = alu(env, operation, left, right, bits);
    if (operation != 6) {
        if (dst_kind == DST_GPR) {
            reg_write(env, dst, result, bits);
        } else if (dst_kind == DST_SFR) {
            sfr_write(env, dst, result, bits);
        } else {
            data_write(env, dst, result, bits);
        }
    }
    return true;
}

static bool exec_move(CPUDMCUState *env, uint8_t op, uint8_t arg,
                      uint16_t ext)
{
    int bits;
    unsigned dr, sr;
    uint32_t ptr, value;

    switch (op) {
    case 0x08: case 0x09:
        bits = op == 0x09 ? 8 : 16;
        reg_write(env, arg >> 4, reg_read(env, arg, bits), bits);
        return true;
    case 0x0a: case 0x0b:
        bits = op == 0x0b ? 8 : 16;
        dr = arg >> 4;
        pointer_write(env, dr, env->gpr[dr], reg_read(env, arg, bits), bits);
        return true;
    case 0x18: case 0x19:
        value = reg_read(env, arg, 8);
        reg_write(env, arg >> 4, op == 0x18 ? sext8(value) : value, 16);
        return true;
    case 0x1a: case 0x1b:
        bits = op == 0x1b ? 8 : 16;
        dr = arg >> 4;
        ptr = env->gpr[dr];
        pointer_write(env, dr, ptr, reg_read(env, arg, bits), bits);
        env->gpr[dr] = (ptr + bits / 8) & MASK16;
        return true;
    case 0x28: case 0x29:
        bits = op == 0x29 ? 8 : 16;
        sr = arg & 15;
        reg_write(env, arg >> 4,
                  pointer_read(env, sr, env->gpr[sr], bits), bits);
        return true;
    case 0x2a: case 0x2b:
        bits = op == 0x2b ? 8 : 16;
        dr = arg >> 4;
        sr = arg & 15;
        pointer_write(env, dr, env->gpr[dr],
                      pointer_read(env, sr, env->gpr[sr], bits), bits);
        return true;
    case 0x38: case 0x39:
        bits = op == 0x39 ? 8 : 16;
        sr = arg & 15;
        ptr = env->gpr[sr];
        reg_write(env, arg >> 4, pointer_read(env, sr, ptr, bits), bits);
        env->gpr[sr] = (ptr + bits / 8) & MASK16;
        return true;
    case 0x3a: case 0x3b:
        bits = op == 0x3b ? 8 : 16;
        sr = arg & 15;
        ptr = env->gpr[sr];
        dr = arg >> 4;
        pointer_write(env, dr, env->gpr[dr],
                      pointer_read(env, sr, ptr, bits), bits);
        env->gpr[sr] = (ptr + bits / 8) & MASK16;
        return true;
    case 0x48: case 0x49:
        reg_write(env, arg >> 4, arg & 15, op == 0x49 ? 8 : 16);
        return true;
    case 0x58: case 0x59:
        bits = op == 0x59 ? 8 : 16;
        dr = arg >> 4;
        env->gpr[dr] = (env->gpr[dr] - bits / 8) & MASK16;
        pointer_write(env, dr, env->gpr[dr], reg_read(env, arg, bits), bits);
        return true;
    case 0x5a: case 0x5b:
        bits = op == 0x5b ? 8 : 16;
        dr = arg >> 4;
        sr = arg & 15;
        pointer_write(env, dr, env->gpr[dr],
                      pointer_read(env, sr, env->gpr[sr], bits), bits);
        env->gpr[dr] = (env->gpr[dr] + bits / 8) & MASK16;
        env->gpr[sr] = (env->gpr[sr] + bits / 8) & MASK16;
        return true;
    case 0x68: case 0x69:
        sfr_write(env, arg, ext, op == 0x69 ? 8 : 16);
        return true;
    case 0x6a: case 0x6b:
        bits = op == 0x6b ? 8 : 16;
        sr = arg & 15;
        pointer_write(env, sr, env->gpr[sr] + ext,
                      reg_read(env, arg >> 4, bits), bits);
        return true;
    case 0x78: case 0x79:
        bits = op == 0x79 ? 8 : 16;
        sr = arg & 15;
        reg_write(env, arg >> 4,
                  pointer_read(env, sr, env->gpr[sr] + ext, bits), bits);
        return true;
    case 0x88: case 0x89:
        bits = op == 0x89 ? 8 : 16;
        sfr_write(env, arg, data_read(env, ext, bits), bits);
        return true;
    case 0x8a: case 0x8b:
        if (arg >= 16) {
            return false;
        }
        bits = op == 0x8b ? 8 : 16;
        pointer_write(env, arg, env->gpr[arg], data_read(env, ext, bits), bits);
        return true;
    case 0x98: case 0x99:
        value = data_read(env, ext, 8);
        sfr_write(env, arg, op == 0x98 ? sext8(value) : value, 16);
        return true;
    case 0xa8: case 0xa9:
        bits = op == 0xa9 ? 8 : 16;
        data_write(env, ext, sfr_read(env, arg, bits), bits);
        return true;
    case 0xb8: case 0xb9:
        value = sfr_read(env, arg, 8);
        data_write(env, ext, op == 0xb8 ? sext8(value) : value, 16);
        return true;
    default:
        return false;
    }
}

static bool exec_shift(CPUDMCUState *env, uint8_t op, uint8_t arg)
{
    enum { SH_NONE, SH_SL, SH_SR, SH_ASR, SH_ASL, SH_ROL, SH_ROR,
           SH_SLOSB, SH_SROSB } kind = SH_NONE;
    int count;
    unsigned steps;
    unsigned dr = arg >> 4;
    uint32_t value = env->gpr[dr] & MASK16;
    uint32_t incoming_shift_buffer;
    uint32_t outgoing_shift_buffer = 0;
    uint32_t carry = 0;
    bool overflow = false;
    bool mem = false;
    uint32_t addr = 0;

    switch (op) {
    case 0x0c: kind = SH_SL; count = sext8(reg_read(env, arg, 8)); break;
    case 0x1c: kind = SH_SLOSB; count = sext8(reg_read(env, arg, 8)); break;
    case 0x0d: kind = SH_SR; count = sext8(reg_read(env, arg, 8)); break;
    case 0x1d: kind = SH_SROSB; count = sext8(reg_read(env, arg, 8)); break;
    case 0x4a: kind = SH_ASR; count = sext8(reg_read(env, arg, 8)); break;
    case 0xc8: kind = SH_ROL; count = reg_read(env, arg, 8) & 15; break;
    case 0xc9: kind = SH_ROR; count = reg_read(env, arg, 8) & 15; break;
    case 0x4b: kind = SH_ASR; count = arg & 15; break;
    case 0x4c: kind = SH_SL; count = arg & 15; break;
    case 0x5c: kind = SH_SLOSB; count = arg & 15; break;
    case 0x4d: kind = SH_SR; count = arg & 15; break;
    case 0x5d: kind = SH_SROSB; count = arg & 15; break;
    case 0xca: kind = SH_ROL; count = arg & 15; break;
    case 0xcb: kind = SH_ROR; count = arg & 15; break;
    case 0x2c: kind = SH_SL; count = sext8(reg_read(env, arg, 8)); mem = true; break;
    case 0x2d: kind = SH_SR; count = sext8(reg_read(env, arg, 8)); mem = true; break;
    case 0x3c: kind = SH_SLOSB; count = sext8(reg_read(env, arg, 8)); mem = true; break;
    case 0x3d: kind = SH_SROSB; count = sext8(reg_read(env, arg, 8)); mem = true; break;
    default: return false;
    }
    if (mem) {
        addr = env->gpr[dr];
        value = pointer_read(env, dr, addr, 16);
    }
    if (count < 0) {
        count = -count;
        if (kind == SH_SL) { kind = SH_SR; }
        else if (kind == SH_SR) { kind = SH_SL; }
        else if (kind == SH_SLOSB) { kind = SH_SROSB; }
        else if (kind == SH_SROSB) { kind = SH_SLOSB; }
        else if (kind == SH_ASR) { kind = SH_ASL; }
    }
    steps = count;
    incoming_shift_buffer = env->shift_buffer & MASK16;
    while (steps--) {
        uint32_t out;

        if (kind == SH_SL || kind == SH_SLOSB) {
            out = value >> 15;
            if (kind == SH_SL) {
                outgoing_shift_buffer =
                    ((outgoing_shift_buffer << 1) | out) & MASK16;
            }
            value = (value << 1) & MASK16;
            overflow |= out;
        } else if (kind == SH_SR || kind == SH_SROSB || kind == SH_ASR) {
            out = value & 1;
            if (kind == SH_SR || kind == SH_ASR) {
                outgoing_shift_buffer =
                    (outgoing_shift_buffer >> 1) | (out << 15);
            }
            /* For right shifts V is the OR of discarded bits before C. */
            overflow |= carry;
            if (kind == SH_ASR) {
                value = (value >> 1) | (value & 0x8000);
            } else {
                value >>= 1;
            }
        } else if (kind == SH_ASL) {
            uint32_t sign = value & 0x8000;

            out = (value >> 14) & 1;
            if (!!out != !!sign) {
                overflow = true;
            }
            value = sign | ((value << 1) & 0x7fff);
        } else if (kind == SH_ROL) {
            out = value >> 15;
            value = ((value << 1) | out) & MASK16;
        } else {
            out = value & 1;
            value = (value >> 1) | (out << 15);
        }
        carry = out;
    }
    if (kind == SH_SLOSB || kind == SH_SROSB) {
        /* OSB instructions consume the prior SB even when count is zero. */
        value |= incoming_shift_buffer;
    } else if (kind == SH_SL || kind == SH_SR || kind == SH_ASR) {
        env->shift_buffer = outgoing_shift_buffer;
    }
    if (kind == SH_ASL && overflow) {
        value = value & 0x8000 ? 0x8000 : 0x7fff;
    }
    set_flag(env, DMCU_PSW_C, count ? carry : false);
    set_flag(env, DMCU_PSW_Z, value == 0);
    set_flag(env, DMCU_PSW_N, value & 0x8000);
    set_flag(env, DMCU_PSW_V,
             kind == SH_ROL || kind == SH_ROR ? false : overflow);
    if (mem) {
        pointer_write(env, dr, addr, value, 16);
        env->gpr[dr] = (addr + 2) & MASK16;
    } else {
        env->gpr[dr] = value;
    }
    return true;
}

static bool exec_bit(CPUDMCUState *env, uint8_t op, uint8_t arg,
                     uint16_t ext)
{
    uint32_t za, zb, qa, qb, left, right, result;
    if (op >= 0xe0) {
        result = bit_read(env, arg, op & 15);
        logic_flags(env, result, 1);
        bit_write(env, arg, op & 15, op < 0xf0);
        return true;
    }
    switch (op) {
    case 0x6c: case 0x6d: case 0x7c: case 0x7d: case 0x8c: case 0x8d:
        za = ext >> 8;
        zb = ext & 15;
        qa = arg;
        qb = (ext >> 4) & 15;
        left = bit_read(env, za, zb);
        right = bit_read(env, qa, qb);
        if (op == 0x8d) {
            alu_sub(env, left, right, 0, 1, false);
            return true;
        }
        if (op == 0x6c) { result = left | right; }
        else if (op == 0x6d) { result = left ^ right; }
        else if (op == 0x7c) { result = right; }
        else if (op == 0x7d) { result = !right; }
        else { result = left & right; }
        logic_flags(env, result, 1);
        /* A bit write to PSR (for example BMOV C,R1.15) wins over the
         * instruction's ordinary flag side effects, matching compiler use. */
        bit_write(env, za, zb, result);
        return true;
    default:
        return false;
    }
}

static uint16_t rom_argument(CPUDMCUState *env, unsigned index)
{
    return internal_data_read(env->gpr[DMCU_SP] + index * 2, 16);
}

static void trace_resource_io_call(CPUDMCUState *env, uint32_t from,
                                   uint32_t target)
{
    if (env->resource_io_trace_frozen) {
        return;
    }
    uint64_t index = env->resource_io_calls++;
    uint32_t slot = index % DMCU_RESOURCE_IO_TRACE_SLOTS;
    uint32_t page;
    uint16_t shift;
    uint16_t logical_block = 0xffff;
    uint16_t map_slot = 0xffff;
    unsigned argument;

    env->resource_io_from[slot] = from & MASK24;
    env->resource_io_target[slot] = target & MASK24;
    env->resource_io_sp[slot] = env->gpr[DMCU_SP] & MASK16;
    env->resource_io_fp[slot] = env->gpr[DMCU_FP] & MASK16;
    for (argument = 0; argument < 6; argument++) {
        env->resource_io_args[slot][argument] = rom_argument(env, argument);
    }
    env->resource_io_base[slot] = internal_data_read(0x4a36u, 16);
    shift = internal_data_read(0x04dcu, 16);
    env->resource_io_shift[slot] = shift;
    env->resource_io_window[slot] = address_space_lduw_le(
        &address_space_memory, 0x005128e0u, MEMTXATTRS_UNSPECIFIED, NULL);
    /* Only 25:206E consumes A2:28E0.  The lower 2D:261C and 2C:2EBA
     * storage layers are also included in the general trace, but their calls
     * remain valid while the application-level byte window is zero. */
    if (target == 0x25206eu && !env->resource_io_window[slot]) {
        if (!env->resource_window_zero_io_calls) {
            env->resource_window_first_zero_from = from & MASK24;
            env->resource_window_first_zero_target = target & MASK24;
            for (argument = 0; argument < 6; argument++) {
                env->resource_window_first_zero_args[argument] =
                    env->resource_io_args[slot][argument];
            }
            env->resource_window_first_zero_base =
                env->resource_io_base[slot];
            env->resource_window_first_zero_shift = shift;
        }
        env->resource_window_zero_io_calls++;
    }

    if (target == 0x2c2ebau && shift < 32) {
        page = ((uint32_t)env->resource_io_args[slot][0] << 16) |
               env->resource_io_args[slot][1];
        logical_block = page >> shift;
        map_slot = internal_data_read(
            (0x0286u + ((logical_block & 0xffu) << 1)) & MASK16, 16);
    }
    env->resource_io_logical_block[slot] = logical_block;
    env->resource_io_map_slot[slot] = map_slot;
}

enum {
    USERINFO_FLOW_FALLBACK_ENTRY = 1,
    USERINFO_FLOW_OPEN_RETURN,
    USERINFO_FLOW_READ_RETURN,
    USERINFO_FLOW_VERSION_RETURN,
    USERINFO_FLOW_CRC_RETURN,
    USERINFO_FLOW_VALID_BRANCH,
    USERINFO_FLOW_APPLY_RETURN,
    USERINFO_FLOW_CLOSE_CALL,
    USERINFO_FLOW_CLOSE_RETURN,
    USERINFO_FLOW_INVALID_REOPEN,
    USERINFO_FLOW_FALLBACK_RETURN,
    USERINFO_FLOW_RESIDENT_CLOSE_ENTRY,
    USERINFO_FLOW_RESIDENT_CLOSE_GUARD,
    USERINFO_FLOW_CLOSE_STATE_RETURN,
    USERINFO_FLOW_CLOSE_SYNC_RETURN,
    USERINFO_FLOW_CLOSE_VOLUME_RETURN,
    USERINFO_FLOW_CLOSE_RELEASE_RETURN,
    USERINFO_FLOW_CLOSE_DESTROY_RETURN,
    USERINFO_FLOW_RESIDENT_CLOSE_RETURN,
    USERINFO_FLOW_STATE_CALL,
    USERINFO_FLOW_STATE_RETURN,
};

static uint8_t trace_userinfo_descriptor_byte(uint16_t hi, uint16_t lo,
                                              uint16_t offset)
{
    uint32_t address = (((uint32_t)hi << 16) | lo) & MASK24;

    if (hi == 0) {
        return internal_data_read((lo + offset) & MASK16, 8);
    }
    return address_space_ldub(&address_space_memory,
                              ((address + offset) & MASK24) ^ 1u,
                              MEMTXATTRS_UNSPECIFIED, NULL);
}

static void trace_userinfo_flow(CPUDMCUState *env, uint8_t event,
                                uint32_t from, uint32_t target,
                                uint16_t sp, uint16_t fp,
                                uint16_t handle_hi, uint16_t handle_lo)
{
    uint64_t sequence = env->userinfo_flow_events++;
    uint32_t slot = sequence % DMCU_USERINFO_FLOW_TRACE_SLOTS;
    uint16_t frame = 0;

    if (env->userinfo_flow_depth &&
        env->userinfo_flow_depth <= DMCU_USERINFO_CLOSE_STACK) {
        frame = env->userinfo_flow_frame_fp[env->userinfo_flow_depth - 1u];
    }
    if (!handle_hi && !handle_lo && frame) {
        handle_hi = internal_data_read((frame - 4u) & MASK16, 16);
        handle_lo = internal_data_read((frame - 2u) & MASK16, 16);
    }

    env->userinfo_flow_trace_event[slot] = event;
    env->userinfo_flow_trace_depth[slot] = env->userinfo_flow_depth;
    env->userinfo_flow_trace_close_depth[slot] = env->userinfo_close_depth;
    env->userinfo_flow_trace_from[slot] = from & MASK24;
    env->userinfo_flow_trace_target[slot] = target & MASK24;
    env->userinfo_flow_trace_sp[slot] = sp;
    env->userinfo_flow_trace_fp[slot] = fp;
    env->userinfo_flow_trace_r0[slot] = env->gpr[0] & MASK16;
    env->userinfo_flow_trace_r1[slot] = env->gpr[1] & MASK16;
    env->userinfo_flow_trace_r2[slot] = env->gpr[2] & MASK16;
    env->userinfo_flow_trace_r3[slot] = env->gpr[3] & MASK16;
    env->userinfo_flow_trace_valid[slot] = frame ?
        internal_data_read((frame - 8u) & MASK16, 16) : 0xffffu;
    env->userinfo_flow_trace_result[slot] = frame ?
        internal_data_read((frame - 10u) & MASK16, 16) : 0xffffu;
    env->userinfo_flow_trace_handle_hi[slot] = handle_hi;
    env->userinfo_flow_trace_handle_lo[slot] = handle_lo;
    env->userinfo_flow_trace_error[slot] = address_space_lduw_le(
        &address_space_memory, 0x00512ae0u,
        MEMTXATTRS_UNSPECIFIED, NULL);
    env->userinfo_flow_trace_descriptor_14[slot] =
        (handle_hi || handle_lo) ?
        trace_userinfo_descriptor_byte(handle_hi, handle_lo, 0x14u) : 0xffu;
    env->userinfo_flow_trace_descriptor_15[slot] =
        (handle_hi || handle_lo) ?
        trace_userinfo_descriptor_byte(handle_hi, handle_lo, 0x15u) : 0xffu;
}

static void trace_control_transfer(CPUDMCUState *env, uint32_t from,
                                   uint32_t sequential, uint16_t word,
                                   uint16_t sp, uint16_t fp)
{
    static unsigned timer_idle_bad_leaf_entry_logs;
    static unsigned object_callback_entries;
    static unsigned object_callback_returns;
    static unsigned flat_32_8778_entries;
    static unsigned result_scanner_steps;
    static unsigned result_list_steps;
    static unsigned resident_file_open_steps;
    static unsigned file_path_resolve_steps;
    static unsigned file_pointer_classify_steps;
    static unsigned file_path_component_steps;
    static unsigned menu_event_exit_logs;
    static unsigned menu_event_path_logs;
    static unsigned menu_body_call_logs;
    static unsigned menu_poll_decode_logs;
    static unsigned resident_probe_logs;
    static unsigned menu_tick_path_logs;
    static unsigned menu_state_event_logs;
    static unsigned menu_layout_call_logs;
    static unsigned menu_position_call_logs;
    static unsigned menu_record_decode_entry_logs;
    static unsigned menu_record_decode_return_logs;
    static unsigned menu_text_stream_entry_logs;
    static unsigned direct_resource_read_stage_logs;
    static unsigned direct_resource_read_path_logs;
    static unsigned direct_resource_geometry_steps;
    static unsigned direct_resource_lookup_steps;
    static bool direct_resource_menu_read_active;
    static unsigned far_memory_copy_call_logs;
    static unsigned wide_from_int16_path_logs;
    static unsigned segment33_low_path_logs;
    static unsigned post_wide_control_logs;
    static unsigned post_wide_instruction_steps;
    static bool post_wide_control_trace_active;
    static bool post_wide_control_trace_done;
    static unsigned uint32_modulo_wrapper_path_logs;
    static unsigned uint32_divide_wrapper_path_logs;
    static bool menu_tick_probe_active;
    static unsigned storage_registry_steps;
    static unsigned resource_storage_update_steps;
    static unsigned storage_ftl_classify_returns;
    static unsigned storage_ftl_fast_classify_returns;
    static unsigned storage_factory_ecc_returns;
    static bool application_state_control_trace_active;
    static unsigned application_state_control_logs;
    static unsigned application_resource_context_logs;
    static unsigned application_selector_context_logs;
    static unsigned application_selector_return_logs;
    static unsigned application_launch_context_logs;
    static unsigned application_resource_read_logs;
    static unsigned application_resource_read_return_logs;
    static unsigned application_resource_transfer_logs;
    static unsigned application_resource_file_logs;
    static unsigned modal_event_return_logs;
    static unsigned modal_event_nonzero_logs;
    static unsigned flat_menu_entry_logs;
    static unsigned flat_menu_exit_logs;
    static unsigned foreground_status_return_logs;
    static unsigned operation_context_failure_logs;
    static unsigned operation_context_return_logs;
    static unsigned operation_context_path_logs;
    static unsigned operation_modal_path_logs;
    uint32_t target = env->pc & MASK24;

    /* These are the first instructions after each nested formatter call.
     * ADD SP leaves R0/R1 untouched, so the values observed here are the
     * exact callee results while also avoiding any modification of the guest
     * return path. */
    if ((from & MASK24) == dmcu_code_address(0x15, 0xffec)) {
        unsigned index;

        env->clock_format_core_returns++;
        env->clock_format_core_result[0] = env->gpr[0] & MASK16;
        env->clock_format_core_result[1] = env->gpr[1] & MASK16;
        env->clock_format_core_return_sp = env->gpr[DMCU_SP] & MASK16;
        for (index = 0; index < DMCU_CLOCK_FORMAT_BUFFER_BYTES; index++) {
            env->clock_format_core_buffer_after[index] =
                trace_userinfo_descriptor_byte(
                    env->clock_format_core_args[2],
                    env->clock_format_core_args[3], index);
        }
        env->clock_root_core_trace_active = false;
    }
    if ((from & MASK24) == dmcu_code_address(0x31, 0x77ec)) {
        unsigned index;

        env->clock_format_service_returns++;
        env->clock_format_service_result[0] = env->gpr[0] & MASK16;
        env->clock_format_service_result[1] = env->gpr[1] & MASK16;
        env->clock_format_service_return_sp = env->gpr[DMCU_SP] & MASK16;
        for (index = 0; index < DMCU_CLOCK_FORMAT_BUFFER_BYTES; index++) {
            env->clock_format_service_buffer_after[index] =
                trace_userinfo_descriptor_byte(
                    env->clock_format_service_args[0],
                    env->clock_format_service_args[1], index);
        }
    }
    if ((from & MASK24) == dmcu_code_address(0x31, 0x5948)) {
        unsigned index;

        env->clock_format_root_returns++;
        env->clock_format_root_result[0] = env->gpr[0] & MASK16;
        env->clock_format_root_result[1] = env->gpr[1] & MASK16;
        env->clock_format_root_return_sp = env->gpr[DMCU_SP] & MASK16;
        for (index = 0; index < DMCU_CLOCK_FORMAT_BUFFER_BYTES; index++) {
            env->clock_format_buffer_after[index] =
                trace_userinfo_descriptor_byte(
                    env->clock_format_root_args[0],
                    env->clock_format_root_args[1], index);
        }
        env->clock_format_root_active = false;
    }
    if ((from & MASK24) == dmcu_code_address(0x0c, 0x88ea)) {
        unsigned index;

        env->clock_stream_write_returns++;
        env->clock_stream_write_result[0] = env->gpr[0] & MASK16;
        env->clock_stream_write_result[1] = env->gpr[1] & MASK16;
        for (index = 0; index < DMCU_CLOCK_FORMAT_BUFFER_BYTES; index++) {
            env->clock_stream_buffer_after[index] =
                trace_userinfo_descriptor_byte(
                    env->clock_format_root_args[0],
                    env->clock_format_root_args[1], index);
        }
    }
    if ((from & MASK24) == dmcu_code_address(0x31, 0x5598)) {
        env->clock_stream_dispatch_returns++;
        env->clock_stream_dispatch_result[0] = env->gpr[0] & MASK16;
        env->clock_stream_dispatch_result[1] = env->gpr[1] & MASK16;
    }
    if ((from & MASK24) == dmcu_code_address(0x0c, 0x87fc)) {
        unsigned index;
        uint16_t scan_fp = env->gpr[DMCU_FP] & MASK16;

        env->clock_scan_returns++;
        env->clock_scan_result[0] = env->gpr[0] & MASK16;
        env->clock_scan_result[1] = env->gpr[1] & MASK16;
        env->clock_scan_return_sp = env->gpr[DMCU_SP] & MASK16;
        env->clock_scan_return_fp = scan_fp;
        for (index = 0; index < DMCU_CLOCK_SCAN_LOCAL_WORDS; index++) {
            env->clock_scan_locals[index] = internal_data_read(
                (scan_fp - 0x28u + index * 2u) & MASK16, 16);
        }
    }
    if ((from & MASK24) == dmcu_code_address(0x0c, 0x883e)) {
        env->clock_scan_length_branches++;
        env->clock_scan_length_result[0] = env->gpr[0] & MASK16;
        env->clock_scan_length_result[1] = env->gpr[1] & MASK16;
        env->clock_scan_length_fp = env->gpr[DMCU_FP] & MASK16;
        env->clock_scan_length_target = target & MASK24;
        if (target == dmcu_code_address(0x0c, 0x8842)) {
            env->clock_scan_literal_branches++;
        }
    }

    /* 2D:D93C delegates each path component to 28:D7E2.  Keep a compact
     * trace at the call boundary, after its memory-fill dependency returns,
     * immediately before the first source byte is consumed, and at the
     * shared result epilogue.  Near pointers are read through
     * internal_data_read(), so the diagnostic observes the same A0 byte lane
     * as the guest rather than the raw physical byte order. */
    if ((target == 0x28d7e2u || target == 0x28d810u ||
         target == 0x28d930u || target == 0x28dab8u) &&
        file_path_component_steps < 64) {
        uint16_t component_fp = env->gpr[DMCU_FP] & MASK16;
        uint16_t output_hi = 0xffffu;
        uint16_t output_lo = 0xffffu;
        uint16_t input_hi = 0xffffu;
        uint16_t input_lo = 0xffffu;
        uint16_t length = 0xffffu;
        uint16_t input_byte = 0xffffu;
        uint16_t output_byte = 0xffffu;

        if (target == 0x28d7e2u) {
            /* Pre-SCALL stack: last pushed far pointer is first argument. */
            output_hi = internal_data_read(sp & MASK16, 16);
            output_lo = internal_data_read((sp + 2u) & MASK16, 16);
            input_hi = internal_data_read((sp + 4u) & MASK16, 16);
            input_lo = internal_data_read((sp + 6u) & MASK16, 16);
        } else {
            output_hi = internal_data_read(
                (component_fp + 6u) & MASK16, 16);
            output_lo = internal_data_read(
                (component_fp + 8u) & MASK16, 16);
            input_hi = internal_data_read(
                (component_fp + 10u) & MASK16, 16);
            input_lo = internal_data_read(
                (component_fp + 12u) & MASK16, 16);
            length = internal_data_read(
                (component_fp - 4u) & MASK16, 16);
        }
        if (input_hi == 0 && input_lo != 0xffffu) {
            input_byte = internal_data_read(input_lo & MASK16, 8);
        }
        if (output_hi == 0 && output_lo != 0xffffu) {
            output_byte = internal_data_read(output_lo & MASK16, 8);
        }
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU file path component #%u pc=%02x:%04x "
            "from=%02x:%04x sp=%04x fp=%04x "
            "out=%04x:%04x/%02x in=%04x:%04x/%02x "
            "length=%04x r0=%04x r1=%04x\n",
            file_path_component_steps + 1,
            dmcu_code_segment(target), dmcu_code_pc(target),
            dmcu_code_segment(from), dmcu_code_pc(from), sp, component_fp,
            output_hi, output_lo, output_byte & 0xffu,
            input_hi, input_lo, input_byte & 0xffu, length,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16);
        file_path_component_steps++;
    }

    /* Bounded branch/call milestones for the recovered operation
     * constructor.  Logging only transfers whose source or destination lies
     * in the 0xA86-byte body captures the selected path without retaining a
     * full instruction trace. */
    if ((((from & MASK24) >= 0x18cfa8u &&
          (from & MASK24) < 0x18da2eu) ||
         (target >= 0x18cfa8u && target < 0x18da2eu)) &&
        operation_context_path_logs < 512) {
        uint16_t object_base = operation_object_watch_active ?
            operation_object_watch_base : 0xffffu;
        uint16_t field_1e_hi = 0xffffu;
        uint16_t field_1e_lo = 0xffffu;
        uint16_t field_22_hi = 0xffffu;
        uint16_t field_22_lo = 0xffffu;

        if (object_base != 0xffffu) {
            field_1e_hi = internal_data_read(
                (object_base + 0x1eu) & MASK16, 16);
            field_1e_lo = internal_data_read(
                (object_base + 0x20u) & MASK16, 16);
            field_22_hi = internal_data_read(
                (object_base + 0x22u) & MASK16, 16);
            field_22_lo = internal_data_read(
                (object_base + 0x24u) & MASK16, 16);
        }
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU operation context path #%u %02x:%04x/%04x>"
            "%02x:%04x seq=%02x:%04x r=%04x,%04x,%04x,%04x "
            "sp=%04x fp=%04x object=%04x callbacks=%04x:%04x,"
            "%04x:%04x\n",
            operation_context_path_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            dmcu_code_segment(target), dmcu_code_pc(target),
            dmcu_code_segment(sequential), dmcu_code_pc(sequential),
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            sp & MASK16, fp & MASK16, object_base,
            field_1e_hi, field_1e_lo, field_22_hi, field_22_lo);
        operation_context_path_logs++;
    }

    /* The first selected operation path enters the exact linked modal
     * layout at 31:7772, which delegates to the resident text closure at
     * 15:FF04.  Keep their relatively small control-transfer surfaces in a
     * separate bounded trace.  This reveals the precise return target if a
     * nested closure consumes too much (or too little) of its caller frame. */
    if ((((from & MASK24) >= 0x317772u &&
          (from & MASK24) <= 0x317822u) ||
         (target >= 0x317772u && target <= 0x317822u) ||
         ((from & MASK24) >= 0x15ff04u &&
          (from & MASK24) <= 0x15ffffu) ||
         (target >= 0x15ff04u && target <= 0x15ffffu)) &&
        operation_modal_path_logs < 256) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU operation modal path #%u %02x:%04x/%04x>"
            "%02x:%04x seq=%02x:%04x r=%04x,%04x,%04x,%04x "
            "sp=%04x fp=%04x stack=%04x,%04x,%04x,%04x\n",
            operation_modal_path_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            dmcu_code_segment(target), dmcu_code_pc(target),
            dmcu_code_segment(sequential), dmcu_code_pc(sequential),
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            sp & MASK16, fp & MASK16,
            internal_data_read(sp & MASK16, 16),
            internal_data_read((sp + 2u) & MASK16, 16),
            internal_data_read((sp + 4u) & MASK16, 16),
            internal_data_read((sp + 6u) & MASK16, 16));
        operation_modal_path_logs++;
    }

    /* Resident 18:CFA8 has exactly three source-proven zero-result exits.
     * Keep their origin and shared resource globals together in one bounded
     * record so an operation-0x0A retry can be diagnosed without retaining a
     * multi-million-line control-flow trace.  This is observation only: all
     * reads use the physical application-RAM bank and guest state is left
     * untouched. */
    if (target == 0x18da24u &&
        ((from & MASK24) == 0x18cff0u ||
         (from & MASK24) == 0x18d098u ||
         (from & MASK24) == 0x18d7f4u) &&
        operation_context_failure_logs < 32) {
        uint16_t operation = address_space_ldub(
            &address_space_memory, 0x52517eu,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t object_size = address_space_lduw_le(
            &address_space_memory, 0x525758u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t selector = address_space_lduw_le(
            &address_space_memory, 0x525180u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t base = address_space_lduw_le(
            &address_space_memory, 0x525182u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t extent = address_space_lduw_le(
            &address_space_memory, 0x525184u,
            MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU operation context failure #%u class=%s "
            "from=%02x:%04x op=%02x result=%04x object=%04x "
            "selector=%04x base=%04x extent=%04x sp=%04x fp=%04x\n",
            operation_context_failure_logs + 1,
            (from & MASK24) == 0x18cff0u ? "allocation" :
            (from & MASK24) == 0x18d098u ? "resource-test" :
                                           "validation",
            dmcu_code_segment(from), dmcu_code_pc(from), operation & 0xffu,
            env->gpr[0] & MASK16, object_size, selector, base, extent,
            sp & MASK16, fp & MASK16);
        operation_context_failure_logs++;
    }
    if ((from & MASK24) == 0x18da2cu && target == 0x1b2602u &&
        (word == 0xc620u || word == 0xc600u) &&
        operation_context_return_logs < 32) {
        uint16_t operation = address_space_ldub(
            &address_space_memory, 0x52517eu,
            MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU operation context return #%u op=%02x result=%04x "
            "to=%02x:%04x sp=%04x fp=%04x\n",
            operation_context_return_logs + 1, operation & 0xffu,
            env->gpr[0] & MASK16, dmcu_code_segment(target),
            dmcu_code_pc(target), sp & MASK16, fp & MASK16);
        operation_context_return_logs++;
    }

    /*
     * The recovered resident operation at 1B:23B8 deliberately enters the
     * middle of the 31:4476 graphics routine at 31:4974.  That continuation
     * consumes locals in the resident caller's large frame, so sampling the
     * standalone 31:4476 prologue gives a false provenance for its geometry.
     * Retain the frame's initial value, every write to its loop limit, and a
     * ring of continuation entries.  This is read-only diagnostics and is
     * intentionally independent of LOG_UNIMP so Web runs stay fast.
     */
    if ((from & MASK24) == 0x1b23b8u && word == 0x2ea9u) {
        uint16_t frame = env->gpr[DMCU_FP] & MASK16;

        env->graphics_frame_watch_active = true;
        env->graphics_frame_entries++;
        env->graphics_frame_base = frame;
        env->graphics_frame_initial_limit =
            internal_data_read((frame - 0x20u) & MASK16, 16);
        env->graphics_frame_initial_step =
            internal_data_read((frame - 4u) & MASK16, 16);
        env->graphics_frame_initial_index =
            internal_data_read((frame - 2u) & MASK16, 16);
        env->graphics_frame_limit_writes = 0;
        env->graphics_frame_limit_last_pc = 0;
        env->graphics_frame_limit_last_old = 0;
        env->graphics_frame_limit_last_new = 0;
        env->graphics_frame_limit_last_bits = 0;
    }
    if ((word >> 8) == 0xbdu && target == 0x314974u) {
        unsigned slot = env->graphics_continuation_calls %
                        DMCU_GRAPHICS_CONTINUATION_TRACE_SLOTS;
        unsigned argument;
        uint16_t frame = fp & MASK16;

        env->graphics_continuation_from[slot] = from & MASK24;
        env->graphics_continuation_sp[slot] = sp & MASK16;
        env->graphics_continuation_fp[slot] = frame;
        env->graphics_continuation_limit[slot] =
            internal_data_read((frame - 0x20u) & MASK16, 16);
        env->graphics_continuation_step[slot] =
            internal_data_read((frame - 4u) & MASK16, 16);
        env->graphics_continuation_index[slot] =
            internal_data_read((frame - 2u) & MASK16, 16);
        for (argument = 0; argument < 6; argument++) {
            env->graphics_continuation_args[slot][argument] =
                internal_data_read((sp + argument * 2u) & MASK16, 16);
        }
        env->graphics_continuation_calls++;
    }
    if (target == 0x1b23f4u && (word == 0xc620u || word == 0xc600u)) {
        uint16_t frame = fp & MASK16;

        env->graphics_continuation_returns++;
        env->graphics_continuation_return_from = from & MASK24;
        env->graphics_continuation_return_limit =
            internal_data_read((frame - 0x20u) & MASK16, 16);
        env->graphics_continuation_return_step =
            internal_data_read((frame - 4u) & MASK16, 16);
        env->graphics_continuation_return_index =
            internal_data_read((frame - 2u) & MASK16, 16);
    }

    if ((from & MASK24) == 0x5f1722u && target == 0x2fc5deu &&
        foreground_status_return_logs < 32) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU foreground status return #%u result=%04x "
            "sp=%04x fp=%04x target=%02x:%04x\n",
            foreground_status_return_logs + 1,
            env->gpr[0] & MASK16, env->gpr[DMCU_SP] & MASK16,
            env->gpr[DMCU_FP] & MASK16,
            dmcu_code_segment(target), dmcu_code_pc(target));
        foreground_status_return_logs++;
    }
    static const uint32_t application_targets[
        DMCU_APPLICATION_TRACE_ENTRIES] = {
        0x2d7dd2u, /* recovered top-level application dispatcher */
        0x2d7e52u, /* return from the one-shot application initializer */
        0x2b2f44u, /* system/storage registry initializer */
        0x2d7f06u, /* return from the system/storage registry initializer */
        0x2d7f44u, /* return from 31:706a */
        0x2d7f48u, /* return from 33:4ee2 */
        0x2d7f4cu, /* return from 33:0fd6 */
        0x2d7f62u, /* return from 29:13dc */
        0x2d7f66u, /* return from 32:cfcc */
        0x2d7f6au, /* return from 33:6f30 */
        0x2d7f7cu, /* return from 32:f47a */
        0x2902d8u, /* storage-capacity scan */
        0x229738u, /* one-shot application initializer */
        0x22515eu, /* application main loop */
        0x225170u, /* return from 32:9a9a */
        0x225174u, /* return from 33:65c0 */
        0x225188u, /* return from 29:13dc */
        0x22518eu, /* return from 33:6f3c */
        0x225192u, /* return from 32:c86e */
        0x22519eu, /* return from 2d:b54c */
        0x2251aau, /* return from 32:50ba */
        0x2251b4u, /* return from 33:4a84 */
        0x2251bau, /* return from 32:f65a */
        0x2251beu, /* return from 08:4360 */
        0x32512cu, /* resource FILE driver */
        0x2ebe2eu, /* resource FILE attach */
        0x2ebe42u, /* resource attach: return from file-size query */
        0x2ebe6eu, /* resource attach: return from resident file open */
        0x2ebf4eu, /* resource attach: return from first path check */
        0x2ebf72u, /* resource attach: return from second path check */
        0x2ebf94u, /* resource attach: common return */
        0x30c99eu, /* file-size trampoline */
        0x31339au, /* file-size record scanner entry */
        0x3133c8u, /* file-size scanner: return from path resolver */
        0x3133d0u, /* file-size scanner: path resolver failed */
        0x3133f6u, /* file-size scanner: return from directory record scan */
        0x313424u, /* file-size scanner: record/attribute failure */
        0x31343cu, /* file-size scanner: valid regular-file record */
        0x31345au, /* file-size scanner: common return */
        0x30c9a2u, /* resident-file-open wrapper */
        0x1bce3cu, /* resident resource initializer */
        0x23a38cu, /* exact application-context selector */
        0x1bd492u, /* return from application-context selector */
        0x1f1f1au, /* resident filesystem open routine */
        0x333376u, /* hardware-state predicate before application loop */
        0x0e75bau, /* non-returning resident application loop */
        0x22522au, /* loop: return from 32:f65a */
        0x22522eu, /* loop: return from 30:8c1c */
        0x225232u, /* loop: return from 33:5090 */
        0x225236u, /* loop: return from 33:4ef8 */
        0x22523au, /* loop: return from 33:5d76 */
        0x22542au, /* loop: return from 32:2930 */
        0x22542eu, /* loop: return from 32:342e */
        0x225432u, /* loop: return from 33:4ee2 */
        0x225436u, /* loop: return from 33:43ce */
        0x336f30u, /* top-level post-registry hook entry */
        0x32f47au, /* top-level timer/config entry */
        0x030084u, /* inferred scheduler: return from top-level dispatcher */
        0x2d7f80u, /* unexpected return from non-returning application loop */
        0x334f50u, /* factory linked reset preamble */
        0x33603cu, /* factory linked SP/FP/compiler-start preamble */
        0x114560u, /* linked 261-descriptor compiler initializer */
        0x077fe4u, /* linked nine-descriptor constant initializer */
        0x03026au, /* linked exact system main */
        0x2e2e82u, /* shared compiler epilogue: identify the unwinding caller */
        0x31d3bau, /* foreground copy helper: capture caller and arguments */
        0x2fc59au, /* foreground parent reached from the main status loop */
        0x5f16f6u, /* relocated foreground context/status predicate */
        0x31345eu, /* foreground asynchronous-state branch */
        0x22381eu, /* alternate foreground asynchronous-state branch */
        0x202de0u, /* foreground UI/event loop */
        0x20be12u, /* modal loading task entry */
        0x20bee0u, /* modal loading task event-loop head */
        0x20bf00u, /* return from the resident event dispatcher */
        0x20c336u, /* modal loading task exit path */
        0x08441au, /* resident byte-fill primitive */
        0x301a54u, /* rectangle/region compositor entry */
        0x332562u, /* foreground event-gate entry */
        0x202e30u, /* return from the foreground event gate */
        0x324c34u, /* foreground event-ready predicate */
        0x202e34u, /* return from the event-ready predicate */
        0x295126u, /* installed cursor/redraw refresh routine */
        0x294c86u, /* unrelated flat JPEG-parser exit; should be unreachable */
        0x294df4u, /* unrelated flat JPEG-parser entry; should be unreachable */
        0x334eccu, /* exact matrix-index to application-event mapper */
        0x202e9eu, /* foreground return from the event mapper */
        0x277d8au, /* resource/text stream worker reached through callback */
        0x334510u, /* outer resident event-handler dispatch */
        0x0300a6u, /* return to the caller-constrained outer event loop */
        0x2b9178u, /* application root-object constructor */
        0x279892u, /* parent which invokes the root-object constructor */
        0x503870u, /* one-valued wrapper around the constructor parent */
        0x503892u, /* zero-valued wrapper around the constructor parent */
        0x325accu, /* validation checksum which guards resource decoding */
        0x335906u, /* mode-mask helper: diagnose its far return frame */
        0x33529eu, /* flat shared epilogue entered by outer paths */
        0x3352aau, /* flat large copy/convert body: diagnose its caller */
        0x3357e2u, /* flat copy/convert shared entry A */
        0x335b9au, /* flat copy/convert shared entry B */
        0x3358dau, /* flat copy/convert shared callback path */
        0x1fb496u, /* resident application-event dispatcher */
        0x1b23f4u, /* return from first operation-0x0b table allocation */
        0x1b2400u, /* first operation-0x0b allocation succeeded */
        0x1b2c46u, /* operation-0x0b cleanup path */
        0x2578eau, /* heap walker requests a descriptor bit */
        0x2578eeu, /* return from descriptor-bit allocator */
        0x2579aau, /* heap descriptor allocation failed */
        0x30251eu, /* descriptor-bit allocator entry */
        0x302624u, /* descriptor-bit allocator exhausted */
        0x302626u, /* descriptor-bit allocator epilogue */
        0x31f2d8u, /* modal loop return from low-level event helper */
        0x31f2feu, /* modal loop accepted an event and is exiting */
        0x32c476u, /* modal-object cleanup wrapper */
        0x2b758eu, /* shared cleanup tail entered with the caller's frame */
        0x2b54e6u, /* continuation selected by the shared cleanup tail */
        0x2885eeu, /* first helper called by the shared cleanup tail */
        0x203390u, /* second helper called by the shared cleanup tail */
        0x2894c2u, /* result/resource scanner entry */
        0x3351e0u, /* result scanner resource-handle lookup wrapper */
        0x3351f2u, /* result scanner handle-to-pointer wrapper */
        0x3366e2u, /* display/state refresh thunk */
        0x318f74u, /* result-record preparation/sort wrapper */
        0x241f02u, /* shared byte-sort tail */
        0x2ed34au, /* exact post-foreground launch sequence */
        0x2ed38au, /* return from first launch FILE open */
        0x2ed3c0u, /* return from second launch FILE open */
        0x2ed3e0u, /* return from launch FILE-size wrapper */
        0x2ed404u, /* null primary FILE branch */
        0x2ed420u, /* primary FILE opened; enter launch-manager path */
        0x1821f4u, /* exact resident application launch manager */
        0x18232au, /* return from launch-manager resource opener */
        0x2fe4c8u, /* application-code registry lookup */
        0x1824aau, /* return from application-code registry lookup */
        0x2ed456u, /* return from resident launch manager */
        0x2ed4a6u, /* launch sequence common epilogue */
        0x2cc9e8u, /* exact generic-menu application entry */
        0x2cca00u, /* generic menu: descriptor page decoded */
        0x2ccb32u, /* generic menu: return from page-table builder */
        0x2ccb48u, /* generic menu: null page-table failure path */
        0x2ccb5au, /* generic menu: valid page-table success path */
        0x2ccbb2u, /* generic menu: return from layout/string copy */
        0x2ccbb6u, /* generic menu: return from menu event handler */
        0x2ccbc2u, /* generic menu: cleanup complete */
        0x2a322au, /* exact menu page-table builder entry */
        0x2a327cu, /* page builder: static maximum-page decoded */
        0x2a32f2u, /* page builder: dynamic maximum-page decoded */
        0x2a330au, /* page builder: requested page is valid */
        0x2a335au, /* page builder: resident static pointer path */
        0x2a3376u, /* page builder: first packed pointer decoded */
        0x2a33aau, /* page builder: successor packed pointer decoded */
        0x2a33b8u, /* page builder: resource-backed pointer path */
        0x2a3492u, /* page builder: successful result */
        0x2aa75au, /* return from resident FILE open in validation */
        0x25ce1eu, /* return from the validation/file-open wrapper */
        0x2d78b6u, /* allocator: return from first readiness predicate */
        0x2d78d6u, /* allocator: return from second readiness predicate */
        0x2d79b0u, /* allocator: return from capacity preparation */
        0x2d79e2u, /* allocator: return from heap allocation */
        0x2d7a12u, /* allocator: return from storage status query */
        0x25ce2eu, /* return from the resource allocator */
        0x31f6aeu, /* storage update: return from unit initialization */
        0x31f6c4u, /* storage update: return from maintenance pass */
        0x31f6dau, /* storage update: return from final commit */
        0x2aa952u, /* exact factory-default/catalogue routine entry */
        0x2d8134u, /* caller return from factory-default/catalogue routine */
        0x330070u, /* text dispatcher: capture bad modal text-pointer caller */
        0x32082eu, /* record/text adapter: capture the bad source record */
        0x2d7facu, /* return from persistent startup-selector byte read */
        0x3343deu, /* return from persistent startup-selector routine */
        /* Read-only foreground-cycle boundaries.  These retain the value in
         * R0 at each producer/consumer boundary without changing the event
         * queue, application selector, or guest timing. */
        0x202e12u, /* return from the raw foreground event source */
        0x202e9eu, /* return from the foreground timer/event mapper */
        0x1df2ecu, /* exact resident root-menu controller entry */
        0x1df6d8u, /* root controller item-loop decision point */
        0x1df900u, /* item loop skipped after the ULE comparison */
        0x10e4aau, /* exact resident hierarchy root-menu renderer entry */
        0x202f16u, /* event word copied into the decoder local */
        0x203190u, /* state-transition flag loaded from frame -0x16 */
        0x203388u, /* foreground loop exit selected by global 51:2250 */
        0x31f2b2u, /* return from the modal event-ready predicate */
        0x31f282u, /* exact modal event-loop entry and its calling frame */
        0x31f2aeu, /* first direct transfer into the modal loop body */
    };

    /* These four linked segment-33 PCs are live fall-through locations in
     * the flat renderer, while their independently-called timer-idle leaves
     * live at the source-50 PCs.  Keep a bounded trace until every active
     * caller is relocated.  This is diagnostic only. */
    if ((word >> 8) == 0xbdu &&
        (target == 0x336bb2u || target == 0x336bbau ||
         target == 0x336c2au || target == 0x336c32u) &&
        timer_idle_bad_leaf_entry_logs < 32) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU timer-idle bad leaf entry #%u target=%02x:%04x "
            "from=%02x:%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "DS0=%03x DS1=%03x\n",
            timer_idle_bad_leaf_entry_logs + 1,
            dmcu_code_segment(target), dmcu_code_pc(target),
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff);
        timer_idle_bad_leaf_entry_logs++;
    }

    /* 30:D6D0 converts two 0..15 UI colour indices through the byte table
     * rooted at physical 50:B857 and stores the resulting pixel nibbles in
     * 4BA8/4BAE.  Keep both the raw RAM byte and the byte selected by the
     * currently-modelled external-bus A0 lane.  This makes a bad caller
     * distinguishable from a bad byte-lane rule without changing either the
     * table or the guest result.  `sp` is the pre-SCALL stack pointer, so its
     * first two words are the callee's +6 and +8 arguments after SCALL/LINK. */
    if ((word >> 8) == 0xbdu && target == 0x30d6d0u) {
        static unsigned bad_mode_pair_logs;
        unsigned slot = env->color_trace_count % DMCU_COLOR_TRACE_SLOTS;
        uint16_t index_a = internal_data_read(sp, 16) & 0xff;
        uint16_t index_b = internal_data_read((sp + 2u) & MASK16, 16) & 0xff;
        uint32_t address_a = (0x50b857u + index_a) & MASK24;
        uint32_t address_b = (0x50b857u + index_b) & MASK24;

        env->color_trace_caller[slot] = from & MASK24;
        env->color_trace_index_a[slot] = index_a;
        env->color_trace_index_b[slot] = index_b;
        env->color_trace_address_a[slot] = address_a;
        env->color_trace_address_b[slot] = address_b;
        env->color_trace_raw_a[slot] = address_space_ldub(
            &address_space_memory, address_a, MEMTXATTRS_UNSPECIFIED, NULL);
        env->color_trace_raw_b[slot] = address_space_ldub(
            &address_space_memory, address_b, MEMTXATTRS_UNSPECIFIED, NULL);
        env->color_trace_lane_a[slot] = address_space_ldub(
            &address_space_memory, address_a ^ 1u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        env->color_trace_lane_b[slot] = address_space_ldub(
            &address_space_memory, address_b ^ 1u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        env->color_trace_result_a[slot] = 0xffff;
        env->color_trace_result_b[slot] = 0xffff;
        env->color_trace_count++;
        if (from == 0x5f1bdcu && (index_a > 15u || index_b > 15u) &&
            bad_mode_pair_logs < 8) {
            qemu_log_mask(
                LOG_UNIMP,
                "DMCU bad relocated mode-pair #%u indices=%u,%u "
                "sp=%04x fp=%04x frame=%04x,%04x,%04x,%04x,%04x,%04x "
                "r0=%04x r1=%04x r2=%04x r3=%04x DS0=%03x DS1=%03x\n",
                bad_mode_pair_logs + 1, index_a, index_b, sp, fp,
                internal_data_read(fp, 16),
                internal_data_read((fp + 2u) & MASK16, 16),
                internal_data_read((fp + 4u) & MASK16, 16),
                internal_data_read((fp + 6u) & MASK16, 16),
                internal_data_read((fp + 8u) & MASK16, 16),
                internal_data_read((fp + 10u) & MASK16, 16),
                env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                env->gpr[2] & MASK16, env->gpr[3] & MASK16,
                env->sfr[DMCU_SFR_DS0] & 0x1ff,
                env->sfr[DMCU_SFR_DS1] & 0x1ff);
            bad_mode_pair_logs++;
        }
    }
    if (env->color_trace_count && (from & MASK24) == 0x30d75eu) {
        unsigned slot = (env->color_trace_count - 1u) %
                        DMCU_COLOR_TRACE_SLOTS;

        env->color_trace_result_a[slot] = internal_data_read(0x4ba8, 16);
    }
    if (env->color_trace_count && (from & MASK24) == 0x30d798u) {
        unsigned slot = (env->color_trace_count - 1u) %
                        DMCU_COLOR_TRACE_SLOTS;

        env->color_trace_result_b[slot] = internal_data_read(0x4bae, 16);
    }

    if ((env->pc & MASK24) == 0x1bce3cu &&
        application_resource_context_logs < 4) {
        uint16_t resource_high = internal_data_read(sp, 16);
        uint16_t resource_low = internal_data_read((sp + 2u) & MASK16, 16);
        uint16_t state_high = internal_data_read((sp + 4u) & MASK16, 16);
        uint16_t state_low = internal_data_read((sp + 6u) & MASK16, 16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application resource context #%u from=%02x:%04x "
            "sp=%04x fp=%04x DS0=%03x DS1=%03x",
            application_resource_context_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff);
        log_application_far_words("resource", resource_high, resource_low,
                                  32);
        log_application_far_words("state", state_high, state_low, 32);
        qemu_log_mask(LOG_UNIMP, "\n");
        application_resource_context_logs++;
    }

    if ((env->pc & MASK24) == 0x23a38cu &&
        application_selector_context_logs < 16) {
        uint16_t cursor_high = internal_data_read(sp, 16);
        uint16_t cursor_low = internal_data_read((sp + 2u) & MASK16, 16);
        uint16_t mode_high = internal_data_read((sp + 4u) & MASK16, 16);
        uint16_t mode_low = internal_data_read((sp + 6u) & MASK16, 16);
        uint16_t record_out_high = internal_data_read((sp + 8u) & MASK16,
                                                       16);
        uint16_t record_out_low = internal_data_read((sp + 10u) & MASK16,
                                                      16);
        uint16_t candidate_high = internal_data_read((sp + 12u) & MASK16,
                                                      16);
        uint16_t candidate_low = internal_data_read((sp + 14u) & MASK16,
                                                     16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application selector context #%u from=%02x:%04x "
            "sp=%04x fp=%04x",
            application_selector_context_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp);
        log_application_far_words("cursor", cursor_high, cursor_low, 4);
        log_application_far_words("mode", mode_high, mode_low, 4);
        log_application_far_words("record-out", record_out_high,
                                  record_out_low, 4);
        log_application_far_words("candidate", candidate_high,
                                  candidate_low, 32);
        qemu_log_mask(LOG_UNIMP, "\n");
        application_selector_context_logs++;
    }

    if ((env->pc & MASK24) == 0x1bd492u &&
        application_selector_return_logs < 16) {
        uint16_t cursor = internal_data_read((fp - 0x000bu) & MASK16, 8);
        uint16_t mode = internal_data_read((fp - 0x000cu) & MASK16, 8);
        uint16_t record_high = internal_data_read((fp - 0x000au) & MASK16,
                                                   16);
        uint16_t record_low = internal_data_read((fp - 0x0008u) & MASK16,
                                                  16);
        uint16_t candidate_high = internal_data_read((fp - 0x0006u) & MASK16,
                                                      16);
        uint16_t candidate_low = internal_data_read((fp - 0x0004u) & MASK16,
                                                     16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application selector return #%u from=%02x:%04x "
            "sp=%04x fp=%04x result=%04x cursor=%02x mode=%02x",
            application_selector_return_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, cursor & 0xff, mode & 0xff);
        log_application_far_words("record", record_high, record_low, 32);
        log_application_far_words("candidate", candidate_high,
                                  candidate_low, 16);
        qemu_log_mask(LOG_UNIMP, "\n");
        application_selector_return_logs++;
    }

    if ((env->pc & MASK24) == 0x1821f4u &&
        application_launch_context_logs < 16) {
        uint16_t record_high = internal_data_read(sp, 16);
        uint16_t record_low = internal_data_read((sp + 2u) & MASK16, 16);
        uint16_t parent_high = internal_data_read((sp + 4u) & MASK16, 16);
        uint16_t parent_low = internal_data_read((sp + 6u) & MASK16, 16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application launch context #%u from=%02x:%04x "
            "sp=%04x fp=%04x",
            application_launch_context_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp);
        log_application_far_words("record", record_high, record_low, 48);
        log_application_far_words("parent", parent_high, parent_low, 32);
        qemu_log_mask(LOG_UNIMP, "\n");
        application_launch_context_logs++;
    }

    if ((env->pc & MASK24) == 0x25206eu &&
        application_resource_read_logs < 16) {
        uint16_t output_high = internal_data_read(sp, 16);
        uint16_t output_low = internal_data_read((sp + 2u) & MASK16, 16);
        uint16_t source_high = internal_data_read((sp + 4u) & MASK16, 16);
        uint16_t source_low = internal_data_read((sp + 6u) & MASK16, 16);
        uint16_t length = internal_data_read((sp + 8u) & MASK16, 16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application resource read #%u from=%02x:%04x "
            "sp=%04x fp=%04x length=%04x window=%04x",
            application_resource_read_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp, length,
            address_space_lduw_le(&address_space_memory, 0x5128e0u,
                                  MEMTXATTRS_UNSPECIFIED, NULL));
        log_application_far_words("output-before", output_high, output_low,
                                  8);
        log_application_far_words("source", source_high, source_low, 8);
        log_application_far_words("transfer-window", 0x0051, 0x1840, 16);
        qemu_log_mask(LOG_UNIMP, "\n");
        application_resource_read_logs++;
    }

    if ((env->pc & MASK24) == 0x2520a8u &&
        application_resource_read_return_logs < 16) {
        uint16_t output_high = internal_data_read((fp + 6u) & MASK16, 16);
        uint16_t output_low = internal_data_read((fp + 8u) & MASK16, 16);
        uint16_t source_high = internal_data_read((fp + 10u) & MASK16, 16);
        uint16_t source_low = internal_data_read((fp + 12u) & MASK16, 16);
        uint16_t length = internal_data_read((fp + 14u) & MASK16, 16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application resource read return #%u from=%02x:%04x "
            "sp=%04x fp=%04x result=%04x:%04x length=%04x window=%04x",
            application_resource_read_return_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16, length,
            address_space_lduw_le(&address_space_memory, 0x5128e0u,
                                  MEMTXATTRS_UNSPECIFIED, NULL));
        log_application_far_words("output-after", output_high, output_low,
                                  8);
        log_application_far_words("source", source_high, source_low, 8);
        log_application_far_words("transfer-window", 0x0051, 0x1840, 16);
        qemu_log_mask(LOG_UNIMP, "\n");
        application_resource_read_return_logs++;
    }

    if ((env->pc & MASK24) == 0x29ac4eu &&
        application_resource_transfer_logs < 16) {
        /* 28:12A8 is a two-word tail jump.  Its SCALL return frame occupies
         * the first two words at SP; the five caller argument words follow. */
        uint16_t output_high = internal_data_read((sp + 4u) & MASK16, 16);
        uint16_t output_low = internal_data_read((sp + 6u) & MASK16, 16);
        uint16_t source_high = internal_data_read((sp + 8u) & MASK16, 16);
        uint16_t source_low = internal_data_read((sp + 10u) & MASK16, 16);
        uint16_t length = internal_data_read((sp + 12u) & MASK16, 16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application resource transfer #%u from=%02x:%04x "
            "sp=%04x fp=%04x return=%04x,%04x length=%04x window=%04x",
            application_resource_transfer_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            internal_data_read(sp, 16),
            internal_data_read((sp + 2u) & MASK16, 16), length,
            address_space_lduw_le(&address_space_memory, 0x5128e0u,
                                  MEMTXATTRS_UNSPECIFIED, NULL));
        log_application_far_words("output", output_high, output_low, 8);
        log_application_far_words("source", source_high, source_low, 8);
        qemu_log_mask(LOG_UNIMP, "\n");
        application_resource_transfer_logs++;
    }

    if ((env->pc & MASK24) == 0x2ebe2eu &&
        application_resource_file_logs < 16) {
        uint16_t path_high = internal_data_read(sp, 16);
        uint16_t path_low = internal_data_read((sp + 2u) & MASK16, 16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application resource file #%u from=%02x:%04x "
            "sp=%04x fp=%04x",
            application_resource_file_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp);
        log_application_far_words("path", path_high, path_low, 25);
        qemu_log_mask(LOG_UNIMP, "\n");
        application_resource_file_logs++;
    }

    if ((env->pc & MASK24) == 0x2ebe42u &&
        application_resource_file_logs < 16) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application resource stat return #%u from=%02x:%04x "
            "sp=%04x fp=%04x size=%04x:%04x\n",
            application_resource_file_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16);
        application_resource_file_logs++;
    }

    if ((env->pc & MASK24) == 0x2ebe6eu &&
        application_resource_file_logs < 16) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application resource open return #%u from=%02x:%04x "
            "sp=%04x fp=%04x file=%04x:%04x\n",
            application_resource_file_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16);
        application_resource_file_logs++;
    }

    /* The exact 31:F282 modal loop accepts only type 4 / code F0.  Observe
     * the outputs written by the recovered 29:3DD2 helper at its balanced
     * return without changing the guest's event state or control flow. */
    if ((env->pc & MASK24) == 0x31f2d8u &&
        (from & MASK24) == 0x293dd2u + 0x02c2u) {
        uint16_t caller_fp = env->gpr[DMCU_FP] & MASK16;
        uint16_t event_type = internal_data_read(
            (caller_fp - 2u) & MASK16, 16);
        uint16_t event_code = internal_data_read(
            (caller_fp - 4u) & MASK16, 16);
        bool nonzero = (env->gpr[0] & MASK16) != 0;

        modal_event_return_logs++;
        if (modal_event_return_logs <= 4 ||
            (nonzero && modal_event_nonzero_logs < 16)) {
            qemu_log_mask(
                LOG_UNIMP,
                "DMCU modal event return #%u sp=%04x old-fp=%04x "
                "caller-fp=%04x result=%04x type=%04x code=%04x "
                "flags=%04x timers=%04x,%04x,%04x\n",
                modal_event_return_logs, sp, fp, caller_fp,
                env->gpr[0] & MASK16, event_type, event_code,
                address_space_lduw_le(&address_space_memory, 0x512a4eu,
                                      MEMTXATTRS_UNSPECIFIED, NULL),
                address_space_lduw_le(&address_space_memory,
                                      DMCU_UNBANKED_LOW_PAGE_BASE + 0x0494u,
                                      MEMTXATTRS_UNSPECIFIED, NULL),
                address_space_lduw_le(&address_space_memory,
                                      DMCU_UNBANKED_LOW_PAGE_BASE + 0x0496u,
                                      MEMTXATTRS_UNSPECIFIED, NULL),
                address_space_lduw_le(&address_space_memory,
                                      DMCU_UNBANKED_LOW_PAGE_BASE + 0x0498u,
                                      MEMTXATTRS_UNSPECIFIED, NULL));
            if (nonzero) {
                modal_event_nonzero_logs++;
            }
        }
    }

    if ((env->pc & MASK24) == 0x115c12u &&
        menu_record_decode_entry_logs < 16) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu record decode entry #%u from=%02x:%04x "
            "sp=%04x fp=%04x r0=%04x r1=%04x "
            "index=%02x types=%02x,%02x,%02x,%02x "
            "stack=%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x\n",
            menu_record_decode_entry_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            address_space_ldub(&address_space_memory, 0x5253a3u,
                               MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_ldub(&address_space_memory, 0x3370fdu,
                               MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_ldub(&address_space_memory, 0x3370fcu,
                               MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_ldub(&address_space_memory, 0x3370ffu,
                               MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_ldub(&address_space_memory, 0x3370feu,
                               MEMTXATTRS_UNSPECIFIED, NULL),
            internal_data_read(sp, 16),
            internal_data_read((sp + 2) & MASK16, 16),
            internal_data_read((sp + 4) & MASK16, 16),
            internal_data_read((sp + 6) & MASK16, 16),
            internal_data_read((sp + 8) & MASK16, 16),
            internal_data_read((sp + 10) & MASK16, 16),
            internal_data_read((sp + 12) & MASK16, 16),
            internal_data_read((sp + 14) & MASK16, 16),
            internal_data_read((sp + 16) & MASK16, 16));
        menu_record_decode_entry_logs++;
    }
    if ((env->pc & MASK24) == 0x18a296u &&
        (from & MASK24) >= 0x115c12u &&
        (from & MASK24) < 0x1172b6u &&
        menu_record_decode_return_logs < 16) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu record decode return #%u from=%02x:%04x "
            "sp=%04x fp=%04x r0=%04x r1=%04x\n",
            menu_record_decode_return_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16);
        menu_record_decode_return_logs++;
    }

    if ((env->pc & MASK24) == 0x26459cu &&
        menu_text_stream_entry_logs < 16) {
        uint16_t stream_hi = internal_data_read((sp + 4) & MASK16, 16);
        uint16_t stream_lo = internal_data_read((sp + 6) & MASK16, 16);
        uint32_t stream = ((uint32_t)stream_hi << 16) | stream_lo;
        unsigned index;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu text stream entry #%u from=%02x:%04x "
            "sp=%04x fp=%04x args=%04x,%04x,%04x,%04x bytes=",
            menu_text_stream_entry_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            internal_data_read(sp, 16),
            internal_data_read((sp + 2) & MASK16, 16), stream_hi, stream_lo);
        for (index = 0; index < 32; index++) {
            qemu_log_mask(
                LOG_UNIMP, "%02x",
                address_space_ldub(&address_space_memory,
                                   (stream + index) & MASK24,
                                   MEMTXATTRS_UNSPECIFIED, NULL));
        }
        qemu_log_mask(LOG_UNIMP, "\n");
        menu_text_stream_entry_logs++;
    }

    /*
     * Diagnostic-only trace for the exact FILE read used by the isolated
     * native-menu probe.  The trace observes guest state at existing branch
     * targets and never changes a register, flag, memory byte, or return
     * value.  Keep the bounded counter because the same routine is also used
     * by background resource clients after the first menu attempt.
     */
    if ((env->pc & MASK24) == 0x1cccd4u &&
        internal_data_read(sp, 16) == 0x0053u &&
        internal_data_read((sp + 2) & MASK16, 16) == 0x0200u) {
        direct_resource_menu_read_active = true;
    }
    if (direct_resource_menu_read_active &&
        (((env->pc & MASK24) >= 0x1cccd4u &&
          (env->pc & MASK24) <= 0x1cd462u) ||
         ((from & MASK24) >= 0x1cccd4u &&
          (from & MASK24) <= 0x1cd462u)) &&
        direct_resource_read_path_logs < 256) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU direct resource read path #%u pc=%02x:%04x "
            "from=%02x:%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "r2=%04x r3=%04x remaining=%04x:%04x chunk=%04x "
            "current=%04x:%04x\n",
            direct_resource_read_path_logs + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            internal_data_read((fp + 0xfff6u) & MASK16, 16),
            internal_data_read((fp + 0xfff8u) & MASK16, 16),
            internal_data_read((fp + 0xfffau) & MASK16, 16),
            internal_data_read((fp + 0xfffcu) & MASK16, 16),
            internal_data_read((fp + 0xfffeu) & MASK16, 16));
        direct_resource_read_path_logs++;
    }
    if (direct_resource_menu_read_active &&
        (env->pc & MASK24) >= 0x074700u &&
        (env->pc & MASK24) <= 0x0747a2u &&
        direct_resource_geometry_steps < 128) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU direct resource geometry #%u pc=%02x:%04x "
            "from=%02x:%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "r2=%04x r3=%04x r4=%04x r5=%04x "
            "args=%04x,%04x local=%04x\n",
            direct_resource_geometry_steps + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            env->gpr[4] & MASK16, env->gpr[5] & MASK16,
            internal_data_read((fp + 6) & MASK16, 16),
            internal_data_read((fp + 8) & MASK16, 16),
            internal_data_read((fp + 0xfffeu) & MASK16, 16));
        direct_resource_geometry_steps++;
    }
    if (direct_resource_menu_read_active &&
        (((env->pc & MASK24) >= 0x2ad374u &&
          (env->pc & MASK24) <= 0x2ad5c4u) ||
         ((env->pc & MASK24) >= 0x2d3460u &&
          (env->pc & MASK24) <= 0x2d3626u) ||
         (env->pc & MASK24) == 0x2e787eu ||
         (env->pc & MASK24) == 0x066840u) &&
        direct_resource_lookup_steps < 320) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU direct resource lookup #%u pc=%02x:%04x "
            "from=%02x:%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "r2=%04x r3=%04x table="
            "%04x:%04x,%04x:%04x,%04x:%04x,type=%04x\n",
            direct_resource_lookup_steps + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            address_space_lduw_le(&address_space_memory, 0x5127a4u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory, 0x5127a6u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory, 0x5127a8u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory, 0x5127aau,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory, 0x5127bcu,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory, 0x5127beu,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory, 0x5127c0u,
                                  MEMTXATTRS_UNSPECIFIED, NULL));
        direct_resource_lookup_steps++;
    }
    if (direct_resource_menu_read_active &&
        ((env->pc & MASK24) == 0x1cccd4u ||
         (env->pc & MASK24) == 0x1ccd7cu ||
         (env->pc & MASK24) == 0x1ccdc8u ||
         (env->pc & MASK24) == 0x1cce08u ||
         (env->pc & MASK24) == 0x1ccea0u ||
         (env->pc & MASK24) == 0x1ccef4u ||
         (env->pc & MASK24) == 0x1ccf40u ||
         (env->pc & MASK24) == 0x1cd05cu ||
         (env->pc & MASK24) == 0x1cd19au ||
         (env->pc & MASK24) == 0x1cd1c4u ||
         (env->pc & MASK24) == 0x1cd1e2u ||
         (env->pc & MASK24) == 0x1cd286u ||
         (env->pc & MASK24) == 0x1cd318u ||
         (env->pc & MASK24) == 0x1cd322u ||
         (env->pc & MASK24) == 0x1cd374u ||
         (env->pc & MASK24) == 0x1cd39au ||
         (env->pc & MASK24) == 0x1cd40cu ||
         (env->pc & MASK24) == 0x1cd41au ||
         (env->pc & MASK24) == 0x1cd41eu ||
         (env->pc & MASK24) == 0x1cd444u ||
         (env->pc & MASK24) == 0x1cd450u ||
         (env->pc & MASK24) == 0x1cd460u ||
         (env->pc & MASK24) == 0x074500u ||
         (env->pc & MASK24) == 0x074532u ||
         (env->pc & MASK24) == 0x074536u ||
         (env->pc & MASK24) == 0x074572u ||
         (env->pc & MASK24) == 0x074576u ||
         (env->pc & MASK24) == 0x0745f4u ||
         (env->pc & MASK24) == 0x0745feu ||
         (env->pc & MASK24) == 0x074700u ||
         (env->pc & MASK24) == 0x074744u ||
         (env->pc & MASK24) == 0x074748u ||
         (env->pc & MASK24) == 0x07478au ||
         (env->pc & MASK24) == 0x074794u ||
         (env->pc & MASK24) == 0x0747a0u ||
         ((env->pc & MASK24) == 0x3304b6u &&
          (from & MASK24) >= 0x1cccd4u &&
          (from & MASK24) <= 0x1cd462u)) &&
        direct_resource_read_stage_logs < 64) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU direct resource read stage #%u pc=%02x:%04x "
            "from=%02x:%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "r2=%04x r3=%04x error=%04x "
            "locals=e2:%04x,e4:%04x,e6:%04x,e8:%04x,ea:%04x,"
            "ec:%04x,ee:%04x,f0:%04x,f2:%04x,f4:%04x,"
            "f6:%04x,f8:%04x,fa:%04x,fc:%04x,fe:%04x "
            "stack=%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x\n",
            direct_resource_read_stage_logs + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            address_space_lduw_le(&address_space_memory, 0x512ae0u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            internal_data_read((fp + 0xffe2u) & MASK16, 16),
            internal_data_read((fp + 0xffe4u) & MASK16, 16),
            internal_data_read((fp + 0xffe6u) & MASK16, 16),
            internal_data_read((fp + 0xffe8u) & MASK16, 16),
            internal_data_read((fp + 0xffeau) & MASK16, 16),
            internal_data_read((fp + 0xffecu) & MASK16, 16),
            internal_data_read((fp + 0xffeeu) & MASK16, 16),
            internal_data_read((fp + 0xfff0u) & MASK16, 16),
            internal_data_read((fp + 0xfff2u) & MASK16, 16),
            internal_data_read((fp + 0xfff4u) & MASK16, 16),
            internal_data_read((fp + 0xfff6u) & MASK16, 16),
            internal_data_read((fp + 0xfff8u) & MASK16, 16),
            internal_data_read((fp + 0xfffau) & MASK16, 16),
            internal_data_read((fp + 0xfffcu) & MASK16, 16),
            internal_data_read((fp + 0xfffeu) & MASK16, 16),
            internal_data_read(sp, 16),
            internal_data_read((sp + 2) & MASK16, 16),
            internal_data_read((sp + 4) & MASK16, 16),
            internal_data_read((sp + 6) & MASK16, 16),
            internal_data_read((sp + 8) & MASK16, 16),
            internal_data_read((sp + 10) & MASK16, 16),
            internal_data_read((sp + 12) & MASK16, 16),
            internal_data_read((sp + 14) & MASK16, 16));
        direct_resource_read_stage_logs++;
    }
    if ((((env->pc & MASK24) >= 0x030080u &&
          (env->pc & MASK24) < 0x0300f2u) ||
         ((from & MASK24) >= 0x030080u &&
          (from & MASK24) < 0x0300f2u)) &&
        resident_probe_logs < 96) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU resident probe #%u pc=%02x:%04x from=%02x:%04x "
            "sequential=%02x:%04x word=%04x sp=%04x fp=%04x "
            "r0=%04x r1=%04x stack=%04x,%04x,%04x,%04x\n",
            resident_probe_logs + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from),
            dmcu_code_segment(sequential), dmcu_code_pc(sequential),
            word, sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            internal_data_read(sp, 16),
            internal_data_read((sp + 2) & MASK16, 16),
            internal_data_read((sp + 4) & MASK16, 16),
            internal_data_read((sp + 6) & MASK16, 16));
        resident_probe_logs++;
    }

    if (((env->pc & MASK24) == 0x25cc94u ||
         (env->pc & MASK24) == 0x25ce72u ||
         (env->pc & MASK24) == 0x25cedEu ||
         (env->pc & MASK24) == 0x255858u ||
         (env->pc & MASK24) == 0x255874u ||
         (env->pc & MASK24) == 0x255882u ||
         (env->pc & MASK24) == 0x255886u ||
         (env->pc & MASK24) == 0x255c4cu) &&
        storage_registry_steps < 128) {
        uint16_t root_hi = address_space_lduw_le(
            &address_space_memory, 0x005129c0u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t root_lo = address_space_lduw_le(
            &address_space_memory, 0x005129c2u,
            MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(LOG_UNIMP,
                      "DMCU storage registry #%u pc=%02x:%04x "
                      "from=%02x:%04x sequential=%02x:%04x word=%04x "
                      "r0=%04x r1=%04x r2=%04x r3=%04x "
                      "sp=%04x fp=%04x root=%04x:%04x "
                      "stack=%04x,%04x,%04x,%04x "
                      "DS0=%03x DS1=%03x\n",
                      storage_registry_steps + 1,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      dmcu_code_segment(from), dmcu_code_pc(from),
                      dmcu_code_segment(sequential),
                      dmcu_code_pc(sequential), word,
                      env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                      env->gpr[2] & MASK16, env->gpr[3] & MASK16,
                      sp, fp, root_hi, root_lo,
                      internal_data_read(sp, 16),
                      internal_data_read((sp + 2) & MASK16, 16),
                      internal_data_read((sp + 4) & MASK16, 16),
                      internal_data_read((sp + 6) & MASK16, 16),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff);
        storage_registry_steps++;
    }

    if (((env->pc & MASK24) == 0x2d78aau ||
         (env->pc & MASK24) == 0x2d78b6u ||
         (env->pc & MASK24) == 0x2d78ccu ||
         (env->pc & MASK24) == 0x2d78d6u ||
         (env->pc & MASK24) == 0x2d78ecu ||
         (env->pc & MASK24) == 0x2d79a8u ||
         (env->pc & MASK24) == 0x2d79acu ||
         (env->pc & MASK24) == 0x2d79b0u ||
         (env->pc & MASK24) == 0x2d79c6u ||
         (env->pc & MASK24) == 0x2d79ecu ||
         (env->pc & MASK24) == 0x2d7a0eu ||
         (env->pc & MASK24) == 0x2d7a52u ||
         (env->pc & MASK24) == 0x2d7a5au) &&
        resource_storage_update_steps < 128) {
        uint16_t update_fp = env->gpr[DMCU_FP] & MASK16;

        qemu_log_mask(LOG_UNIMP,
                      "DMCU resource storage update #%u pc=%02x:%04x "
                      "from=%02x:%04x r0=%04x r1=%04x r2=%04x r3=%04x "
                      "sp=%04x fp=%04x arg=%04x:%04x "
                      "local=%04x,%04x,%04x,%04x "
                      "geometry=%04x:%04x range=%04x,%04x\n",
                      resource_storage_update_steps + 1,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      dmcu_code_segment(from), dmcu_code_pc(from),
                      env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                      env->gpr[2] & MASK16, env->gpr[3] & MASK16,
                      sp, update_fp,
                      internal_data_read((update_fp + 6) & MASK16, 16),
                      internal_data_read((update_fp + 8) & MASK16, 16),
                      internal_data_read((update_fp - 2) & MASK16, 16),
                      internal_data_read((update_fp - 4) & MASK16, 16),
                      internal_data_read((update_fp - 6) & MASK16, 16),
                      internal_data_read((update_fp - 8) & MASK16, 16),
                      address_space_lduw_le(
                          &address_space_memory, 0x00004b04u,
                          MEMTXATTRS_UNSPECIFIED, NULL),
                      address_space_lduw_le(
                          &address_space_memory, 0x00004b06u,
                          MEMTXATTRS_UNSPECIFIED, NULL),
                      address_space_lduw_le(
                          &address_space_memory, 0x00004a36u,
                          MEMTXATTRS_UNSPECIFIED, NULL),
                      address_space_lduw_le(
                          &address_space_memory, 0x00004a38u,
                          MEMTXATTRS_UNSPECIFIED, NULL));
        resource_storage_update_steps++;
    }

    if ((env->pc & MASK24) == 0x323e8au) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU flat 32:3E8A epilogue entered from %02x:%04x "
                      "word=%04x sp=%04x fp=%04x stack=%04x,%04x,%04x,%04x\n",
                      dmcu_code_segment(from), dmcu_code_pc(from), word,
                      sp, fp,
                      internal_data_read(sp, 16),
                      internal_data_read((sp + 2) & MASK16, 16),
                      internal_data_read((sp + 4) & MASK16, 16),
                      internal_data_read((sp + 6) & MASK16, 16));
    }
    if ((env->pc & MASK24) == 0x2d83c4u) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU flat 2D:83C4 epilogue entered from %02x:%04x "
                      "word=%04x sp=%04x fp=%04x stack=%04x,%04x,%04x,%04x\n",
                      dmcu_code_segment(from), dmcu_code_pc(from), word,
                      sp, fp,
                      internal_data_read(sp, 16),
                      internal_data_read((sp + 2) & MASK16, 16),
                      internal_data_read((sp + 4) & MASK16, 16),
                      internal_data_read((sp + 6) & MASK16, 16));
    }
    if ((env->pc & MASK24) == 0x328a68u) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU flat 32:8A68 epilogue entered from %02x:%04x "
                      "word=%04x sp=%04x fp=%04x stack=%04x,%04x,%04x,%04x\n",
                      dmcu_code_segment(from), dmcu_code_pc(from), word,
                      sp, fp,
                      internal_data_read(sp, 16),
                      internal_data_read((sp + 2) & MASK16, 16),
                      internal_data_read((sp + 4) & MASK16, 16),
                      internal_data_read((sp + 6) & MASK16, 16));
    }
    if ((env->pc & MASK24) >= 0x328778u &&
        (env->pc & MASK24) < 0x328a68u &&
        (env->pc & MASK24) != (sequential & MASK24) &&
        flat_32_8778_entries < 32) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU flat 32:8778-8A67 entry #%u %02x:%04x "
                      "from %02x:%04x word=%04x sp=%04x fp=%04x "
                      "stack=%04x,%04x,%04x,%04x\n",
                      flat_32_8778_entries + 1,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      dmcu_code_segment(from), dmcu_code_pc(from), word,
                      sp, fp,
                      internal_data_read(sp, 16),
                      internal_data_read((sp + 2) & MASK16, 16),
                      internal_data_read((sp + 4) & MASK16, 16),
                      internal_data_read((sp + 6) & MASK16, 16));
        flat_32_8778_entries++;
    }
    if (((env->pc & MASK24) == 0x2894d6u ||
         (env->pc & MASK24) == 0x2894e4u ||
         (env->pc & MASK24) == 0x2894fcu ||
         (env->pc & MASK24) == 0x28950au ||
         (env->pc & MASK24) == 0x289530u ||
         (env->pc & MASK24) == 0x28953eu ||
         (env->pc & MASK24) == 0x28955cu ||
         (env->pc & MASK24) == 0x2895a8u ||
         (env->pc & MASK24) == 0x2895f8u ||
         (env->pc & MASK24) == 0x289656u ||
         (env->pc & MASK24) == 0x289684u ||
         (env->pc & MASK24) == 0x2896a2u ||
         (env->pc & MASK24) == 0x2896bau ||
         (env->pc & MASK24) == 0x289758u ||
         (env->pc & MASK24) == 0x2897acu ||
         (env->pc & MASK24) == 0x2897b0u) &&
        result_scanner_steps < 128) {
        uint16_t scanner_fp = env->gpr[DMCU_FP] & MASK16;

        qemu_log_mask(LOG_UNIMP,
                      "DMCU result scanner #%u pc=%02x:%04x "
                      "from=%02x:%04x r0=%04x r1=%04x "
                      "index=%04x count=%04x alloc=%04x,%04x "
                      "found=%04x flags=%02x "
                      "record0=%02x ptr=%04x:%04x\n",
                      result_scanner_steps + 1,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      dmcu_code_segment(from), dmcu_code_pc(from),
                      env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                      internal_data_read((scanner_fp - 4) & MASK16, 16),
                      internal_data_read((scanner_fp - 0x5a) & MASK16, 16),
                      internal_data_read((scanner_fp - 0x5c) & MASK16, 16),
                      internal_data_read((scanner_fp - 0x5e) & MASK16, 16),
                      internal_data_read((scanner_fp - 0x56) & MASK16, 16),
                      internal_data_read((scanner_fp - 1) & MASK16, 8),
                      internal_data_read((scanner_fp - 0x54) & MASK16, 8),
                      internal_data_read((scanner_fp - 8) & MASK16, 16),
                      internal_data_read((scanner_fp - 6) & MASK16, 16));
        result_scanner_steps++;
    }
    if (((env->pc & MASK24) == 0x319e4au ||
         (env->pc & MASK24) == 0x319e82u ||
         (env->pc & MASK24) == 0x319ea4u ||
         (env->pc & MASK24) == 0x319eb6u) &&
        result_list_steps < 64) {
        uint16_t list_fp = env->gpr[DMCU_FP] & MASK16;

        qemu_log_mask(LOG_UNIMP,
                      "DMCU result list #%u pc=%02x:%04x "
                      "from=%02x:%04x r0=%04x r1=%04x arg=%02x "
                      "object=%04x:%04x count=%04x\n",
                      result_list_steps + 1,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      dmcu_code_segment(from), dmcu_code_pc(from),
                      env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                      internal_data_read((list_fp + 6) & MASK16, 8),
                      internal_data_read((list_fp - 6) & MASK16, 16),
                      internal_data_read((list_fp - 4) & MASK16, 16),
                      internal_data_read((list_fp - 2) & MASK16, 16));
        result_list_steps++;
    }
    if (((env->pc & MASK24) == 0x2f37b0u ||
         (env->pc & MASK24) == 0x31b83cu ||
         (env->pc & MASK24) == 0x31b8ceu ||
         (env->pc & MASK24) == 0x2f37bcu ||
         (env->pc & MASK24) == 0x2f37f4u ||
         (env->pc & MASK24) == 0x2f38f2u) &&
        file_path_resolve_steps < 96) {
        uint16_t path_fp = env->gpr[DMCU_FP] & MASK16;
        uint16_t root_hi = address_space_lduw_le(
            &address_space_memory, 0x005129c0u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t root_lo = address_space_lduw_le(
            &address_space_memory, 0x005129c2u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint32_t root = ((root_hi & 0xffu) << 16) | root_lo;
        uint16_t root_flag = root ? address_space_lduw_le(
            &address_space_memory, (root + 4u) & MASK24,
            MEMTXATTRS_UNSPECIFIED, NULL) : 0;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU file path resolve #%u pc=%02x:%04x "
            "from=%02x:%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "args=%04x:%04x,%04x:%04x root=%04x:%04x flag=%04x "
            "error=%04x\n",
            file_path_resolve_steps + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), sp, path_fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            internal_data_read((path_fp + 6) & MASK16, 16),
            internal_data_read((path_fp + 8) & MASK16, 16),
            internal_data_read((path_fp + 10) & MASK16, 16),
            internal_data_read((path_fp + 12) & MASK16, 16),
            root_hi, root_lo, root_flag,
            address_space_lduw_le(
                &address_space_memory, 0x00512ae0u,
                MEMTXATTRS_UNSPECIFIED, NULL));
        file_path_resolve_steps++;
    }
    if (((env->pc & MASK24) == 0x2f2fe0u ||
         (env->pc & MASK24) == 0x2f3018u ||
         (env->pc & MASK24) == 0x2f3048u ||
         (env->pc & MASK24) == 0x2f30b4u ||
         (env->pc & MASK24) == 0x2f30f4u ||
         (env->pc & MASK24) == 0x2f3120u ||
         (env->pc & MASK24) == 0x2f3124u) &&
        file_pointer_classify_steps < 96) {
        uint16_t classify_fp = env->gpr[DMCU_FP] & MASK16;
        uint16_t arg_hi = internal_data_read(
            (classify_fp + 6) & MASK16, 16);
        uint16_t arg_lo = internal_data_read(
            (classify_fp + 8) & MASK16, 16);
        uint32_t pointer_physical = data_physical_address(
            env, env->gpr[3] & MASK16);
        uint16_t pointer_raw_byte = address_space_ldub(
            &address_space_memory, pointer_physical & MASK24,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t pointer_lane_byte = address_space_ldub(
            &address_space_memory, (pointer_physical ^ 1u) & MASK24,
            MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU file pointer classify #%u pc=%02x:%04x "
            "from=%02x:%04x sp=%04x fp=%04x "
            "r0=%04x r1=%04x r2=%04x r3=%04x "
            "arg=%04x:%04x ds0=%03x ds1=%03x "
            "ptr=%06x raw=%02x lane=%02x\n",
            file_pointer_classify_steps + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), sp, classify_fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            arg_hi, arg_lo,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff,
            pointer_physical & MASK24,
            pointer_raw_byte & 0xff, pointer_lane_byte & 0xff);
        file_pointer_classify_steps++;
    }
    if (((env->pc & MASK24) == 0x1f1f1cu ||
         (env->pc & MASK24) == 0x1f1f80u ||
         (env->pc & MASK24) == 0x1f2000u ||
         (env->pc & MASK24) == 0x1f20e2u ||
         (env->pc & MASK24) == 0x1f2114u ||
         (env->pc & MASK24) == 0x1f2168u ||
         (env->pc & MASK24) == 0x1f2480u ||
         (env->pc & MASK24) == 0x1f253au ||
         (env->pc & MASK24) == 0x1f2540u) &&
        resident_file_open_steps < 128) {
        uint16_t open_fp = env->gpr[DMCU_FP] & MASK16;
        uint16_t path_hi = internal_data_read((open_fp + 6) & MASK16, 16);
        uint16_t path_lo = internal_data_read((open_fp + 8) & MASK16, 16);
        uint16_t path_word[12] = {
            0xffff, 0xffff, 0xffff, 0xffff,
            0xffff, 0xffff, 0xffff, 0xffff,
            0xffff, 0xffff, 0xffff, 0xffff,
        };
        uint16_t filesystem_error = address_space_lduw_le(
            &address_space_memory, 0x00512ae0u,
            MEMTXATTRS_UNSPECIFIED, NULL);
        unsigned path_index;

        if (path_hi == 0) {
            for (path_index = 0; path_index < ARRAY_SIZE(path_word);
                 path_index++) {
                path_word[path_index] = internal_data_read(
                    (path_lo + path_index * 2) & MASK16, 16);
            }
        }
        qemu_log_mask(LOG_UNIMP,
                      "DMCU resident file open #%u pc=%02x:%04x "
                      "from=%02x:%04x r0=%04x r1=%04x mode=%04x "
                      "path=%04x:%04x/"
                      "%04x,%04x,%04x,%04x,%04x,%04x,"
                      "%04x,%04x,%04x,%04x,%04x,%04x "
                      "object=%04x:%04x result=%04x error=%04x\n",
                      resident_file_open_steps + 1,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      dmcu_code_segment(from), dmcu_code_pc(from),
                      env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                      internal_data_read((open_fp + 10) & MASK16, 16),
                      path_hi, path_lo,
                      path_word[0], path_word[1],
                      path_word[2], path_word[3],
                      path_word[4], path_word[5],
                      path_word[6], path_word[7],
                      path_word[8], path_word[9],
                      path_word[10], path_word[11],
                      internal_data_read((open_fp - 4) & MASK16, 16),
                      internal_data_read((open_fp - 2) & MASK16, 16),
                      internal_data_read((open_fp - 6) & MASK16, 16),
                      filesystem_error);
        resident_file_open_steps++;
    }
    if ((env->pc & MASK24) == 0x18a4fcu &&
        menu_event_exit_logs < 8) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu event loop exit #%u from=%02x:%04x "
            "r0=%04x event=%04x mode=%04x flags=%02x,%02x\n",
            menu_event_exit_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from),
            env->gpr[0] & MASK16,
            address_space_lduw_le(
                &address_space_memory, 0x00507e38u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512abau,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_ldub(
                &address_space_memory, 0x0050708bu,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_ldub(
                &address_space_memory, 0x0050708cu,
                MEMTXATTRS_UNSPECIFIED, NULL));
        menu_event_exit_logs++;
    }
    if (((env->pc & MASK24) == 0x189a58u ||
         (env->pc & MASK24) == 0x189ab2u ||
         (env->pc & MASK24) == 0x189b58u ||
         (env->pc & MASK24) == 0x18a4fcu ||
         (env->pc & MASK24) == 0x3365fcu ||
         (env->pc & MASK24) == 0x32cc9cu ||
         (env->pc & MASK24) == 0x3365d4u ||
         (env->pc & MASK24) == 0x2fd266u ||
         (env->pc & MASK24) == 0x334ddau ||
         (env->pc & MASK24) == 0x330edcu ||
         (env->pc & MASK24) == 0x30fe0eu ||
         (env->pc & MASK24) == 0x18a0cau ||
         (env->pc & MASK24) == 0x31142eu ||
         (env->pc & MASK24) == 0x311432u ||
         (env->pc & MASK24) == 0x334e5eu ||
         (env->pc & MASK24) == 0x334e72u ||
         (env->pc & MASK24) == 0x065b00u ||
         (env->pc & MASK24) == 0x065c28u ||
         (env->pc & MASK24) == 0x061c40u ||
         (env->pc & MASK24) == 0x061cbeu ||
         (env->pc & MASK24) == 0x061fc0u ||
         (env->pc & MASK24) == 0x061fc4u) &&
        menu_event_path_logs < 32) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu event path #%u pc=%02x:%04x from=%02x:%04x "
            "word=%04x target=%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "7090=%04x 7dee=%04x mode=%04x\n",
            menu_event_path_logs + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            address_space_lduw_le(
                &address_space_memory, env->pc & MASK24,
                MEMTXATTRS_UNSPECIFIED, NULL),
            sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            address_space_lduw_le(
                &address_space_memory, 0x00507090u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00507deeu,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512abau,
                MEMTXATTRS_UNSPECIFIED, NULL));
        menu_event_path_logs++;
    }
    if ((from & MASK24) >= 0x189a58u &&
        (from & MASK24) <= 0x18a4fcu &&
        (word & 0xff00u) == 0xbd00u &&
        menu_body_call_logs < 64) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu body call #%u from=%02x:%04x target=%02x:%04x "
            "word=%04x targetword=%04x sp=%04x fp=%04x r0=%04x r1=%04x\n",
            menu_body_call_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from),
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc), word,
            address_space_lduw_le(
                &address_space_memory, env->pc & MASK24,
                MEMTXATTRS_UNSPECIFIED, NULL),
            sp, fp, env->gpr[0] & MASK16, env->gpr[1] & MASK16);
        menu_body_call_logs++;
    }
    if (((env->pc & MASK24) == 0x2fc216u ||
         (env->pc & MASK24) == 0x1ef734u ||
         (env->pc & MASK24) == 0x2fc23au ||
         (env->pc & MASK24) == 0x2fc242u ||
         (env->pc & MASK24) == 0x2fc2eau ||
         (env->pc & MASK24) == 0x2fc310u ||
         (env->pc & MASK24) == 0x2fc336u ||
         (env->pc & MASK24) == 0x2fc338u ||
         (env->pc & MASK24) == 0x2fc340u ||
         (env->pc & MASK24) == 0x327050u) &&
        menu_poll_decode_logs < 96) {
        uint32_t frame = env->gpr[11] & MASK16;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu poll decode #%u pc=%02x:%04x from=%02x:%04x "
            "word=%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "local2=%04x local4=%04x 708a=%04x 7098=%04x 7e38=%04x\n",
            menu_poll_decode_logs + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            sp, fp, env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            address_space_lduw_le(
                &address_space_memory, (frame - 2) & MASK16,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, (frame - 4) & MASK16,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x0050708au,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00507098u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00507e38u,
                MEMTXATTRS_UNSPECIFIED, NULL));
        menu_poll_decode_logs++;
    }
    if ((env->pc & MASK24) == 0x2fc216u &&
        (from & MASK24) == 0x32773au && fp == 0xffe0u) {
        menu_tick_probe_active = true;
        menu_tick_path_logs = 0;
        menu_state_event_logs = 0;
    }
    if (menu_tick_probe_active &&
        ((env->pc & MASK24) == 0x2ffa32u ||
         (env->pc & MASK24) == 0x321ef2u ||
         (env->pc & MASK24) == 0x2ffaf4u ||
         (env->pc & MASK24) == 0x30c61au ||
         (env->pc & MASK24) == 0x2ffafau ||
         (env->pc & MASK24) == 0x2ffb18u ||
         (env->pc & MASK24) == 0x2ffb1eu ||
         (env->pc & MASK24) == 0x2ffb48u ||
         (env->pc & MASK24) == 0x2ffb4eu ||
         (env->pc & MASK24) == 0x3bf74eu) &&
        menu_tick_path_logs < 32) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu tick path #%u pc=%02x:%04x from=%02x:%04x "
            "word=%04x targetword=%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "2a76=%04x 2aa4=%04x 2aa6=%04x 2ada=%04x 708b=%04x\n",
            menu_tick_path_logs + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            address_space_lduw_le(
                &address_space_memory, env->pc & MASK24,
                MEMTXATTRS_UNSPECIFIED, NULL),
            sp, fp, env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            address_space_lduw_le(
                &address_space_memory, 0x00512a76u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512aa4u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512aa6u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512adau,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x0050708bu,
                MEMTXATTRS_UNSPECIFIED, NULL));
        menu_tick_path_logs++;
    }
    if (menu_tick_probe_active &&
        ((env->pc & MASK24) == 0x3bf89eu ||
         (env->pc & MASK24) == 0x3bf8a0u ||
         (env->pc & MASK24) == 0x3bf8a4u ||
         (env->pc & MASK24) == 0x3bf8a6u ||
         (env->pc & MASK24) == 0x3bf8aau ||
         (env->pc & MASK24) == 0x3bf8b2u ||
         (env->pc & MASK24) == 0x3bf8b6u ||
         (env->pc & MASK24) == 0x3bf8c2u ||
         (env->pc & MASK24) == 0x3bf8cau ||
         (env->pc & MASK24) == 0x3bf8ccu ||
         (env->pc & MASK24) == 0x3bf8dcu ||
         (env->pc & MASK24) == 0x3bf8e4u) &&
        menu_state_event_logs < 32) {
        uint32_t frame = env->gpr[11] & MASK16;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu state event #%u pc=%02x:%04x from=%02x:%04x "
            "word=%04x sp=%04x fp=%04x r0=%04x r1=%04x "
            "local6=%04x local2=%04x 2a6c=%04x 2a90=%04x 2a92=%04x "
            "2aaa=%04x 2aba=%04x 2ac2=%04x\n",
            menu_state_event_logs + 1,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            sp, fp, env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            address_space_lduw_le(
                &address_space_memory, (frame - 6) & MASK16,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, (frame - 2) & MASK16,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512a6cu,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512a90u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512a92u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512aaau,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512abau,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00512ac2u,
                MEMTXATTRS_UNSPECIFIED, NULL));
        menu_state_event_logs++;
    }
    if (menu_tick_probe_active && (env->pc & MASK24) == 0x2fc340u) {
        menu_tick_probe_active = false;
    }
    unsigned slot;
    unsigned application;
    uint8_t op = word >> 8;
    bool freeze_after = false;
    bool call_or_return = op == 0xbd || op == 0xad || op == 0xbc ||
                          op == 0xcc || op == 0xcd || op == 0xce ||
                          op == 0xc6;

    /* Observer-only ABI monitor for the packed root-resource compositor.
     * The caller has already placed its six words at the pre-call SP; retain
     * those words and the active Harvard data segments without changing the
     * guest stack, registers, memory, or control flow. */
    if (target == dmcu_code_address(0x17, 0x18e6) &&
        target != (sequential & MASK24)) {
        unsigned index;

        env->root_bitmap_blit_calls++;
        env->root_bitmap_blit_from = from & MASK24;
        env->root_bitmap_blit_sp = sp & MASK16;
        env->root_bitmap_blit_fp = fp & MASK16;
        env->root_bitmap_blit_ds0 = env->sfr[DMCU_SFR_DS0] & 0x01ffu;
        env->root_bitmap_blit_ds1 = env->sfr[DMCU_SFR_DS1] & 0x01ffu;
        for (index = 0; index < ARRAY_SIZE(env->root_bitmap_blit_args);
             index++) {
            env->root_bitmap_blit_args[index] =
                internal_data_read((sp + index * 2u) & MASK16, 16);
        }
    }
    if ((from & MASK24) == dmcu_code_address(0x17, 0x253e) &&
        op == 0xc6u) {
        env->root_bitmap_blit_returns++;
        env->root_bitmap_blit_return_to = target;
        env->root_bitmap_blit_result[0] = env->gpr[0] & MASK16;
        env->root_bitmap_blit_result[1] = env->gpr[1] & MASK16;
    }
    if (target == dmcu_code_address(0x26, 0xcf40) &&
        target != (sequential & MASK24)) {
        unsigned trace = env->root_bitmap_resource_calls %
                         DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS;
        unsigned index;

        env->root_bitmap_resource_from[trace] = from & MASK24;
        env->root_bitmap_resource_sp[trace] = sp & MASK16;
        env->root_bitmap_resource_fp[trace] = fp & MASK16;
        env->root_bitmap_resource_next[trace] = target;
        env->root_bitmap_resource_gate[trace] = 0;
        for (index = 0;
             index < ARRAY_SIZE(env->root_bitmap_resource_args[trace]);
             index++) {
            env->root_bitmap_resource_args[trace][index] =
                internal_data_read((sp + index * 2u) & MASK16, 16);
        }
        env->root_bitmap_resource_calls++;
    }
    if ((from & MASK24) == dmcu_code_address(0x26, 0xd2b0) &&
        op == 0xc6u) {
        env->root_bitmap_resource_returns++;
    }
    if (target == dmcu_code_address(0x18, 0x6d56) &&
        target != (sequential & MASK24)) {
        uint16_t args[5];
        uint32_t destination;
        uint32_t source;
        uint32_t length;
        unsigned index;

        for (index = 0; index < ARRAY_SIZE(args); index++) {
            args[index] = internal_data_read((sp + index * 2u) & MASK16, 16);
        }
        destination = (((uint32_t)args[0] & 0xffu) << 16) | args[1];
        source = (((uint32_t)args[2] & 0xffu) << 16) | args[3];
        length = args[4];
        if (destination <= 0x514a9bu &&
            destination + length > 0x514a96u) {
            env->root_bitmap_header_copy_calls++;
            env->root_bitmap_header_copy_from = from & MASK24;
            for (index = 0; index < ARRAY_SIZE(args); index++) {
                env->root_bitmap_header_copy_args[index] = args[index];
            }
        }

        /* The first natural root resource is the complete 240x22 toolbar.
         * Preserve the raw staging bytes supplied to its exact resident
         * memcpy, indexed by their destination offset.  The companion
         * snapshot at 2E:0C46 below records the completed object.  Comparing
         * the two read-only buffers distinguishes NAND/DMA byte ordering from
         * CPU MOVB/REP corruption without changing any guest-visible state. */
        if (env->root_resource_trace_active == 1u &&
            env->root_resource_trace_object_hi[0] == 0x0051u) {
            uint32_t object =
                (((uint32_t)env->root_resource_trace_object_hi[0] & 0xffu)
                 << 16) | env->root_resource_trace_object_lo[0];

            if (destination >= object &&
                destination < object + DMCU_ROOT_TOP_BITMAP_BYTES) {
                uint32_t offset = destination - object;
                uint32_t captured = MIN(
                    length, (uint32_t)DMCU_ROOT_TOP_BITMAP_BYTES - offset);
                uint32_t trace = env->root_top_source_calls++;

                if (trace < DMCU_ROOT_TOP_COPY_TRACE_SLOTS) {
                    env->root_top_source_from[trace] = from & MASK24;
                    for (index = 0; index < ARRAY_SIZE(args); index++) {
                        env->root_top_source_args[trace][index] = args[index];
                    }
                }
                for (index = 0; index < captured; index++) {
                    env->root_top_source[offset + index] =
                        address_space_ldub(
                            &address_space_memory,
                            ((source + index) & MASK24) ^ 1u,
                            MEMTXATTRS_UNSPECIFIED, NULL);
                    if (!env->root_top_source_coverage[offset + index]) {
                        env->root_top_source_coverage[offset + index] = 1u;
                        env->root_top_source_covered++;
                    }
                }
            }
        }
    }
    if (target == dmcu_code_address(0x2e, 0x4572) &&
        target != (sequential & MASK24) &&
        env->root_resource_trace_active == 1u &&
        env->root_top_far_copy_steps < DMCU_ROOT_TOP_FAR_COPY_TRACE_SLOTS) {
        uint32_t trace = env->root_top_far_copy_steps++;
        unsigned index;

        env->root_top_far_copy_pc[trace] = target;
        env->root_top_far_copy_from[trace] = from & MASK24;
        env->root_top_far_copy_psw[trace] = env->psw & MASK16;
        for (index = 0; index < 11; index++) {
            env->root_top_far_copy_gpr[trace][index] =
                env->gpr[index] & MASK16;
        }
        for (index = 0; index < 6; index++) {
            env->root_top_far_copy_args[trace][index] =
                internal_data_read((sp + index * 2u) & MASK16, 16);
        }
        {
            uint32_t destination =
                (((uint32_t)env->root_top_far_copy_args[trace][0] & 0xffu)
                 << 16) | env->root_top_far_copy_args[trace][1];
            uint32_t source =
                (((uint32_t)env->root_top_far_copy_args[trace][2] & 0xffu)
                 << 16) | env->root_top_far_copy_args[trace][3];
            uint32_t length =
                ((uint32_t)env->root_top_far_copy_args[trace][4] << 16) |
                env->root_top_far_copy_args[trace][5];
            uint32_t object =
                (((uint32_t)env->root_resource_trace_object_hi[0] & 0xffu)
                 << 16) | env->root_resource_trace_object_lo[0];

            if (destination >= object &&
                destination < object + DMCU_ROOT_TOP_BITMAP_BYTES) {
                uint32_t offset = destination - object;
                uint32_t captured = MIN(
                    length, (uint32_t)DMCU_ROOT_TOP_BITMAP_BYTES - offset);

                for (index = 0; index < captured; index++) {
                    env->root_top_source[offset + index] =
                        address_space_ldub(
                            &address_space_memory,
                            ((source + index) & MASK24) ^ 1u,
                            MEMTXATTRS_UNSPECIFIED, NULL);
                    if (!env->root_top_source_coverage[offset + index]) {
                        env->root_top_source_coverage[offset + index] = 1u;
                        env->root_top_source_covered++;
                    }
                }
            }
        }
    }
    /* Capture at the 28:12A4 call thunk rather than its 29:AC4E tail target:
     * the SCALL's pre-transfer SP points directly at the five arguments,
     * while the following SJMP already has a return frame below SP. */
    if (target == dmcu_code_address(0x28, 0x12a4) &&
        target != (sequential & MASK24)) {
        uint16_t args[5];
        uint32_t destination;
        unsigned index;

        for (index = 0; index < ARRAY_SIZE(args); index++) {
            args[index] = internal_data_read((sp + index * 2u) & MASK16, 16);
        }
        destination = (((uint32_t)args[0] & 0xffu) << 16) | args[1];
        if (destination <= 0x514a9bu &&
            destination + args[4] > 0x514a96u) {
            env->root_bitmap_transfer_calls++;
            env->root_bitmap_transfer_from = from & MASK24;
            for (index = 0; index < ARRAY_SIZE(args); index++) {
                env->root_bitmap_transfer_args[index] = args[index];
            }
        }
    }

    /* Focused USERINFO.SYS validator/close monitor.  The complete seeded
     * file now reaches validation, but its read-only close recursively
     * re-enters the registry fallback.  Preserve every decisive branch and
     * the +0x14/+0x15 descriptor flags without modifying guest execution. */
    {
        uint32_t control_from = from & MASK24;
        uint32_t control_target = env->pc & MASK24;
        uint16_t handle_hi = 0;
        uint16_t handle_lo = 0;
        uint8_t event = 0;

        /* The registry result loader reaches this framed body both through a
         * normal SCALL and through a compiler-generated RETS tail transfer. */
        if (control_target == 0x5ef732u) {
            if (env->userinfo_flow_depth < DMCU_USERINFO_CLOSE_STACK) {
                env->userinfo_flow_frame_fp[env->userinfo_flow_depth] = 0;
                env->userinfo_flow_depth++;
            }
            trace_userinfo_flow(env, USERINFO_FLOW_FALLBACK_ENTRY,
                                control_from, control_target, sp, fp, 0, 0);
        } else if (env->userinfo_flow_depth &&
                   ((control_from >= 0x5ef732u &&
                     control_from <= 0x5ef9bcu) ||
                    (control_target >= 0x5ef732u &&
                     control_target <= 0x5ef9bcu))) {
            unsigned frame_slot = env->userinfo_flow_depth - 1u;

            if (frame_slot < DMCU_USERINFO_CLOSE_STACK &&
                control_from != 0x5ef9bcu) {
                env->userinfo_flow_frame_fp[frame_slot] = fp;
            }
            if (control_target == 0x5ef760u && op == 0xc6u) {
                event = USERINFO_FLOW_OPEN_RETURN;
            } else if (control_target == 0x5ef7e6u && op == 0xc6u) {
                event = USERINFO_FLOW_READ_RETURN;
            } else if (control_target == 0x5ef812u && op == 0xc6u) {
                event = USERINFO_FLOW_VERSION_RETURN;
            } else if (control_target == 0x5ef81eu && op == 0xc6u) {
                event = USERINFO_FLOW_CRC_RETURN;
            } else if (control_from == 0x5ef820u && op == 0xacu) {
                event = USERINFO_FLOW_VALID_BRANCH;
            } else if (control_target == 0x5ef894u && op == 0xc6u) {
                event = USERINFO_FLOW_APPLY_RETURN;
            } else if (control_from == 0x5ef8acu && op == 0xbdu) {
                event = USERINFO_FLOW_CLOSE_CALL;
            } else if (control_target == 0x5ef8b0u && op == 0xc6u) {
                event = USERINFO_FLOW_CLOSE_RETURN;
            } else if (control_from == 0x5ef8d0u && op == 0xbdu) {
                event = USERINFO_FLOW_INVALID_REOPEN;
            }
            if (event) {
                trace_userinfo_flow(env, event, control_from, control_target,
                                    sp, fp, 0, 0);
            }
        }

        event = 0;
        if (control_target == 0x24eaecu && op == 0xbdu &&
            (env->userinfo_flow_depth || control_from == 0x58b1e8u)) {
            unsigned close_slot = env->userinfo_close_depth;

            handle_hi = internal_data_read(sp, 16);
            handle_lo = internal_data_read((sp + 2u) & MASK16, 16);
            if (close_slot < DMCU_USERINFO_CLOSE_STACK) {
                env->userinfo_close_handle_hi[close_slot] = handle_hi;
                env->userinfo_close_handle_lo[close_slot] = handle_lo;
                env->userinfo_close_depth++;
            }
            trace_userinfo_flow(env, USERINFO_FLOW_RESIDENT_CLOSE_ENTRY,
                                control_from, control_target, sp, fp,
                                handle_hi, handle_lo);
        } else if (env->userinfo_close_depth) {
            unsigned close_slot = env->userinfo_close_depth - 1u;

            if (close_slot < DMCU_USERINFO_CLOSE_STACK) {
                handle_hi = env->userinfo_close_handle_hi[close_slot];
                handle_lo = env->userinfo_close_handle_lo[close_slot];
            }
            if (control_from == 0x24ec1eu && op == 0xacu) {
                event = USERINFO_FLOW_RESIDENT_CLOSE_GUARD;
            } else if (control_target == 0x24ec7eu && op == 0xc6u) {
                event = USERINFO_FLOW_CLOSE_STATE_RETURN;
            } else if (control_target == 0x24ed26u && op == 0xc6u) {
                event = USERINFO_FLOW_CLOSE_SYNC_RETURN;
            } else if (control_target == 0x24ed4au && op == 0xc6u) {
                event = USERINFO_FLOW_CLOSE_VOLUME_RETURN;
            } else if (control_target == 0x24ede2u && op == 0xc6u) {
                event = USERINFO_FLOW_CLOSE_RELEASE_RETURN;
            } else if (control_target == 0x24eef0u && op == 0xc6u) {
                event = USERINFO_FLOW_CLOSE_DESTROY_RETURN;
            } else if (control_from == 0x24ef04u && op == 0xc6u) {
                event = USERINFO_FLOW_RESIDENT_CLOSE_RETURN;
            }
            if (event) {
                trace_userinfo_flow(env, event, control_from, control_target,
                                    sp, fp, handle_hi, handle_lo);
            }
            if (event == USERINFO_FLOW_RESIDENT_CLOSE_RETURN) {
                if (close_slot < DMCU_USERINFO_CLOSE_STACK) {
                    env->userinfo_close_handle_hi[close_slot] = 0;
                    env->userinfo_close_handle_lo[close_slot] = 0;
                }
                env->userinfo_close_depth--;
            }
        }

        if (control_from == 0x5ef9bcu && op == 0xc6u &&
            env->userinfo_flow_depth) {
            unsigned frame_slot = env->userinfo_flow_depth - 1u;

            trace_userinfo_flow(env, USERINFO_FLOW_FALLBACK_RETURN,
                                control_from, control_target, sp, fp, 0, 0);
            if (frame_slot < DMCU_USERINFO_CLOSE_STACK) {
                env->userinfo_flow_frame_fp[frame_slot] = 0;
            }
            env->userinfo_flow_depth--;
        }

        if (control_target == 0x5d6d9eu && op == 0xbdu) {
            unsigned index;

            env->userinfo_state_calls++;
            env->userinfo_state_last_from = control_from;
            env->userinfo_state_last_target = control_target;
            for (index = 0; index < DMCU_USERINFO_STATE_CODE_WORDS; index++) {
                env->userinfo_state_code[index] = cpu_lduw_code(
                    env, 0x5d6d9eu + index * 2u);
            }
            trace_userinfo_flow(env, USERINFO_FLOW_STATE_CALL,
                                control_from, control_target, sp, fp, 0, 0);
        } else if (control_from == 0x5d6e9cu && op == 0xc6u) {
            env->userinfo_state_returns++;
            env->userinfo_state_last_from = control_from;
            env->userinfo_state_last_target = control_target;
            trace_userinfo_flow(env, USERINFO_FLOW_STATE_RETURN,
                                control_from, control_target, sp, fp, 0, 0);
        }
    }

    /* Read-only ABI proof for the resident file writer at 17:E3EE.  The
     * vendor callers push FILE *, source buffer, then a 32-bit byte count.
     * Retain a bounded logical-byte sample and checksum so a valid call can
     * be distinguished from an all-FF source without changing guest state. */
    if ((env->pc & MASK24) == 0x17e3eeu && op == 0xbdu) {
        uint32_t file = ((uint32_t)internal_data_read(sp, 16) << 16) |
                        internal_data_read((sp + 2u) & MASK16, 16);
        uint32_t buffer =
            ((uint32_t)internal_data_read((sp + 4u) & MASK16, 16) << 16) |
            internal_data_read((sp + 6u) & MASK16, 16);
        uint32_t length =
            ((uint32_t)internal_data_read((sp + 8u) & MASK16, 16) << 16) |
            internal_data_read((sp + 10u) & MASK16, 16);
        uint32_t sample_bytes = MIN(length, (uint32_t)0x10000u);
        uint32_t hash = 0x811c9dc5u;
        uint32_t non_ff = 0;
        unsigned index;

        env->file_write_calls++;
        env->file_write_caller = from & MASK24;
        env->file_write_sp = sp;
        env->file_write_file = file & MASK24;
        env->file_write_buffer = buffer & MASK24;
        env->file_write_length = length;
        env->file_write_sample_bytes = sample_bytes;
        env->file_write_watch_active = true;
        env->file_write_stage = 1;
        env->file_write_last_child = 0;
        env->file_write_child_calls = 0;
        env->file_write_child_returns = 0;
        for (index = 0; index < sample_bytes; index++) {
            uint8_t value = address_space_ldub(
                &address_space_memory, ((buffer + index) & MASK24) ^ 1u,
                MEMTXATTRS_UNSPECIFIED, NULL);

            hash = (hash ^ value) * 0x01000193u;
            if (value != 0xffu) {
                non_ff++;
            }
            if (index < sizeof(env->file_write_sample)) {
                env->file_write_sample[index] = value;
            }
        }
        env->file_write_sample_non_ff = non_ff;
        env->file_write_sample_fnv1a = hash;
    }
    {
        static const uint32_t child_calls[] = {
            0x17e42eu, 0x17e5c8u, 0x17e6f4u, 0x17e73eu,
            0x17e8b8u, 0x17e902u, 0x17e9bcu, 0x17ea0eu,
            0x17eb0au, 0x17eb8cu, 0x17ebc6u, 0x17ec02u,
            0x17ecdeu, 0x17ed22u, 0x17edeau,
            /* Direct children of relocated storage selector 07:4200. */
            0x074230u, 0x0742ccu, 0x0742fcu, 0x0743feu,
            0x0744b6u, 0x0744dau,
            /* Direct children of relocated storage scan 07:4800. */
            0x074836u, 0x074876u, 0x0748c0u, 0x074918u,
            0x074984u, 0x0749b4u, 0x074a0cu, 0x074a32u,
            0x074ac8u, 0x074ba4u, 0x074caeu, 0x074cf6u,
            0x074daau, 0x074e04u, 0x074e4eu, 0x074f06u,
            /* Direct children of exact record lookup 2A:D374. */
            0x2ad3a4u, 0x2ad402u, 0x2ad44au,
        };
        uint32_t control_from = from & MASK24;
        uint32_t control_target = env->pc & MASK24;
        unsigned child;

        if (env->file_write_watch_active &&
            ((control_from >= 0x17e3eeu && control_from <= 0x17ef6eu) ||
             (control_from >= 0x074200u && control_from <= 0x0744eeu) ||
             (control_from >= 0x074000u && control_from <= 0x0741c8u) ||
             (control_from >= 0x074800u && control_from <= 0x074f86u) ||
             (control_from >= 0x2ad374u && control_from <= 0x2ad5c4u))) {
            env->file_write_last_from = control_from;
            env->file_write_last_target = control_target;
            env->file_write_last_sp = sp;
            env->file_write_last_fp = fp;
            env->file_write_last_r0 = env->gpr[0] & MASK16;
            env->file_write_last_r1 = env->gpr[1] & MASK16;
            env->file_write_last_r2 = env->gpr[2] & MASK16;
            env->file_write_last_r3 = env->gpr[3] & MASK16;
        }
        for (child = 0; child < ARRAY_SIZE(child_calls); child++) {
            if (env->file_write_watch_active &&
                control_from == child_calls[child] && op == 0xbdu) {
                env->file_write_child_calls++;
                env->file_write_last_child = child + 1;
                env->file_write_stage = 2 + child * 2;
                break;
            }
            if (env->file_write_watch_active &&
                control_target == child_calls[child] + 4u && op == 0xc6u) {
                env->file_write_child_returns++;
                env->file_write_last_child = child + 1;
                env->file_write_stage = 3 + child * 2;
                break;
            }
        }
        /* Exact 2A:D374 performs its device callback by constructing a far
         * return frame and executing RETS at D482.  Treat that dynamic edge
         * as a child milestone even though it is not encoded as SCALL. */
        if (env->file_write_watch_active &&
            control_from == 0x2ad482u && op == 0xc6u) {
            env->file_write_child_calls++;
            env->file_write_last_child = ARRAY_SIZE(child_calls) + 1u;
            env->file_write_stage = 90;
        } else if (env->file_write_watch_active &&
                   control_target == 0x2ad484u && op == 0xc6u) {
            env->file_write_child_returns++;
            env->file_write_last_child = ARRAY_SIZE(child_calls) + 1u;
            env->file_write_stage = 91;
        }
    }
    if (((from & MASK24) == 0x17ea46u ||
         (from & MASK24) == 0x17ef6cu) && op == 0xc6u) {
        uint32_t sequence = env->file_write_returns + 1u;
        uint32_t trace_slot = env->file_write_returns %
                              DMCU_FILE_WRITE_RETURN_TRACE_SLOTS;

        env->file_write_returns++;
        env->file_write_result_hi = env->gpr[0] & MASK16;
        env->file_write_result_lo = env->gpr[1] & MASK16;
        env->file_write_return_trace_sequence[trace_slot] = sequence;
        env->file_write_return_trace_hi[trace_slot] = env->file_write_result_hi;
        env->file_write_return_trace_lo[trace_slot] = env->file_write_result_lo;
        if (env->file_write_result_hi != 0 ||
            env->file_write_result_lo != 0x0100u) {
            env->file_write_nonfull_returns++;
            if (env->file_write_first_nonfull_sequence == 0) {
                env->file_write_first_nonfull_sequence = sequence;
                env->file_write_first_nonfull_hi = env->file_write_result_hi;
                env->file_write_first_nonfull_lo = env->file_write_result_lo;
            }
        }
        env->file_write_stage = 100;
        env->file_write_watch_active = false;
    }

    /* Persistent stage markers for the guest-native v289 provisioner.  The
     * ordinary control trace is a bounded ring and the resource hook runs
     * early enough to be overwritten before a web snapshot is taken. */
    if ((env->pc & MASK24) == 0x58b140u && op == 0xbdu) {
        env->provision_calls++;
        env->provision_caller = from & MASK24;
        env->provision_sp = sp;
        env->provision_stage = 1;
    }
    if ((env->pc & MASK24) == 0x1f1f1au &&
        (from & MASK24) == 0x58b1b4u && op == 0xbdu) {
        env->provision_stage = 2;
    }
    if ((env->pc & MASK24) == 0x58b1b8u && op == 0xc6u) {
        env->provision_stage = 3;
        env->provision_open_hi = env->gpr[0] & MASK16;
        env->provision_open_lo = env->gpr[1] & MASK16;
    }
    if ((env->pc & MASK24) == 0x590000u &&
        (from & MASK24) == 0x58b1d6u && op == 0xbdu) {
        env->provision_stage = 4;
    }
    if ((env->pc & MASK24) == 0x24eaecu &&
        (from & MASK24) == 0x58b1e8u && op == 0xbdu) {
        env->provision_stage = 5;
    }
    if ((env->pc & MASK24) == 0x58b1ecu && op == 0xc6u) {
        env->provision_stage = 6;
    }
    if ((env->pc & MASK24) == 0x30c99eu &&
        (from & MASK24) == 0x58b1fau && op == 0xbdu) {
        env->provision_stage = 7;
    }
    if ((from & MASK24) == 0x58b206u && op == 0xc6u) {
        env->provision_stage = 8;
        env->provision_result_hi = env->gpr[0] & MASK16;
        env->provision_result_lo = env->gpr[1] & MASK16;
    }

    /* Persistent file-open diagnosis.  Static preprocessing splits the exact
     * resident 1F:1F1A implementation into its 17 direct child calls plus
     * three early-failure exits.  Keep the guest path and write-protect word
     * with that compact state so a failed creation can be classified in one
     * boot instead of relying on the short generic control ring. */
    {
        static const uint32_t child_calls[] = {
            0x1f1f7au, 0x1f1fc0u, 0x1f2010u, 0x1f20dcu,
            0x1f20fcu, 0x1f2150u, 0x1f218eu, 0x1f21deu,
            0x1f2208u, 0x1f221eu, 0x1f225au, 0x1f22d6u,
            0x1f2334u, 0x1f2358u, 0x1f23b6u, 0x1f241eu,
            0x1f249au,
        };
        uint32_t control_from = from & MASK24;
        uint32_t control_target = env->pc & MASK24;
        unsigned child;

        /* Retain the outer resident-fopen context independently of the
         * provision-only detailed watcher.  The root allocator is reached
         * through the fixed internal call at 2F:37B8, so without this parent
         * context every allocation appears to have the same caller. */
        if (control_target == 0x1f1f1au && op == 0xbdu) {
            env->file_root_current_open_caller = control_from;
            env->file_root_current_open_sp = sp;
            env->file_root_current_open_fp = 0;
            env->file_root_current_open_mode = 0xffffu;
            env->file_root_current_open_path_hi = 0xffffu;
            env->file_root_current_open_path_lo = 0xffffu;
        }
        if (control_from == 0x1f1f2cu) {
            env->file_root_current_open_fp = fp;
            env->file_root_current_open_mode =
                internal_data_read((fp + 0x0au) & MASK16, 16);
            env->file_root_current_open_path_hi =
                internal_data_read((fp + 0x06u) & MASK16, 16);
            env->file_root_current_open_path_lo =
                internal_data_read((fp + 0x08u) & MASK16, 16);
        }

        /* 31:B83C is the exact call-free file-root allocator.  Snapshot the
         * whole bounded chain on every entry and pair it with the returned
         * pointer.  This compact persistent trace replaces repeated manual
         * RAM polling and survives long after the generic control ring wraps. */
        if (control_target == 0x31b83cu && op == 0xbdu) {
            uint64_t sequence = env->file_root_pool_calls;
            uint32_t pool_slot = sequence % DMCU_FILE_ROOT_POOL_TRACE_SLOTS;
            uint16_t head_hi = address_space_lduw_le(
                &address_space_memory, 0x005129c0u,
                MEMTXATTRS_UNSPECIFIED, NULL);
            uint16_t head_lo = address_space_lduw_le(
                &address_space_memory, 0x005129c2u,
                MEMTXATTRS_UNSPECIFIED, NULL);
            uint32_t node = (((uint32_t)head_hi << 16) | head_lo) & MASK24;
            unsigned index;

            env->file_root_lifecycle_events++;
            env->file_root_pool_trace_event[pool_slot] =
                env->file_root_lifecycle_events;
            env->file_root_pool_trace_from[pool_slot] = control_from;
            env->file_root_pool_trace_open_caller[pool_slot] =
                env->file_root_current_open_caller;
            env->file_root_pool_trace_open_sp[pool_slot] =
                env->file_root_current_open_sp;
            env->file_root_pool_trace_open_fp[pool_slot] =
                env->file_root_current_open_fp;
            env->file_root_pool_trace_open_mode[pool_slot] =
                env->file_root_current_open_mode;
            env->file_root_pool_trace_open_path_hi[pool_slot] =
                env->file_root_current_open_path_hi;
            env->file_root_pool_trace_open_path_lo[pool_slot] =
                env->file_root_current_open_path_lo;
            env->file_root_pool_trace_head_hi[pool_slot] = head_hi;
            env->file_root_pool_trace_head_lo[pool_slot] = head_lo;
            env->file_root_pool_trace_length[pool_slot] = 0;
            env->file_root_pool_trace_available[pool_slot] = 0;
            env->file_root_pool_trace_result_hi[pool_slot] = 0;
            env->file_root_pool_trace_result_lo[pool_slot] = 0;
            env->file_root_pool_trace_error[pool_slot] = 0;
            memset(env->file_root_pool_trace_node[pool_slot], 0,
                   sizeof(env->file_root_pool_trace_node[pool_slot]));
            memset(env->file_root_pool_trace_next[pool_slot], 0,
                   sizeof(env->file_root_pool_trace_next[pool_slot]));
            memset(env->file_root_pool_trace_flag[pool_slot], 0,
                   sizeof(env->file_root_pool_trace_flag[pool_slot]));
            memset(env->file_root_pool_trace_sentinel[pool_slot], 0,
                   sizeof(env->file_root_pool_trace_sentinel[pool_slot]));
            memset(env->file_root_pool_trace_open_path[pool_slot], 0,
                   sizeof(env->file_root_pool_trace_open_path[pool_slot]));
            {
                uint16_t path_hi = env->file_root_current_open_path_hi;
                uint16_t path_lo = env->file_root_current_open_path_lo;
                uint32_t path = (((uint32_t)path_hi << 16) | path_lo) &
                                MASK24;

                for (index = 0; index < DMCU_FILE_ROOT_PATH_BYTES; index++) {
                    env->file_root_pool_trace_open_path[pool_slot][index] =
                        path_hi == 0 ?
                        internal_data_read((path_lo + index) & MASK16, 8) :
                        address_space_ldub(
                            &address_space_memory,
                            ((path + index) & MASK24) ^ 1u,
                            MEMTXATTRS_UNSPECIFIED, NULL);
                }
            }
            for (index = 0;
                 node && index < DMCU_FILE_ROOT_POOL_NODES; index++) {
                uint16_t next_hi = address_space_lduw_le(
                    &address_space_memory, node,
                    MEMTXATTRS_UNSPECIFIED, NULL);
                uint16_t next_lo = address_space_lduw_le(
                    &address_space_memory, (node + 2u) & MASK24,
                    MEMTXATTRS_UNSPECIFIED, NULL);
                uint32_t next = (((uint32_t)next_hi << 16) | next_lo) &
                                MASK24;
                uint8_t flag = address_space_ldub(
                    &address_space_memory, ((node + 4u) & MASK24) ^ 1u,
                    MEMTXATTRS_UNSPECIFIED, NULL);
                uint8_t sentinel = address_space_ldub(
                    &address_space_memory, ((node + 5u) & MASK24) ^ 1u,
                    MEMTXATTRS_UNSPECIFIED, NULL);

                env->file_root_pool_trace_node[pool_slot][index] = node;
                env->file_root_pool_trace_next[pool_slot][index] = next;
                env->file_root_pool_trace_flag[pool_slot][index] = flag;
                env->file_root_pool_trace_sentinel[pool_slot][index] = sentinel;
                env->file_root_pool_trace_length[pool_slot]++;
                if (flag == 0) {
                    env->file_root_pool_trace_available[pool_slot] |=
                        1u << index;
                }
                node = next;
            }
            env->file_root_pool_calls++;
        }
        if (control_from == 0x31b8dau && op == 0xc6u) {
            uint64_t sequence = env->file_root_pool_returns;
            uint32_t pool_slot = sequence % DMCU_FILE_ROOT_POOL_TRACE_SLOTS;

            env->file_root_pool_trace_result_hi[pool_slot] =
                env->gpr[0] & MASK16;
            env->file_root_pool_trace_result_lo[pool_slot] =
                env->gpr[1] & MASK16;
            env->file_root_pool_trace_error[pool_slot] =
                address_space_lduw_le(&address_space_memory, 0x00512ae0u,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->file_root_pool_returns++;
        }

        /* Pair allocations with exact guest release calls.  The far object
         * argument is already on the internal stack at the SCALL boundary;
         * observing it here avoids changing the restored 32:5592 routine. */
        if (control_target == 0x325592u && op == 0xbdu) {
            uint64_t sequence = env->file_root_release_calls;
            uint32_t release_slot = sequence %
                                    DMCU_FILE_ROOT_RELEASE_TRACE_SLOTS;
            uint16_t object_hi = internal_data_read(sp, 16);
            uint16_t object_lo = internal_data_read((sp + 2u) & MASK16, 16);
            uint32_t object = (((uint32_t)object_hi << 16) | object_lo) &
                              MASK24;

            env->file_root_lifecycle_events++;
            env->file_root_release_trace_event[release_slot] =
                env->file_root_lifecycle_events;
            env->file_root_release_trace_caller[release_slot] = control_from;
            env->file_root_release_trace_object[release_slot] = object;
            env->file_root_release_trace_sp[release_slot] = sp;
            env->file_root_release_trace_fp[release_slot] = fp;
            env->file_root_release_trace_flag[release_slot] =
                object ? address_space_ldub(
                    &address_space_memory, ((object + 4u) & MASK24) ^ 1u,
                    MEMTXATTRS_UNSPECIFIED, NULL) : 0xffu;
            env->file_root_release_calls++;
        }

        if (control_target == 0x1f1f1au && op == 0xbdu) {
            env->file_open_calls++;
            if (control_from == 0x58b1b4u) {
                env->file_open_watch_active = true;
                env->file_open_provision_seen = true;
                env->file_open_args_captured = false;
                env->file_open_caller = control_from;
                env->file_open_sp = sp;
                env->file_open_fp = fp;
                env->file_open_stage = 1;
                env->file_open_child_calls = 0;
                env->file_open_child_returns = 0;
                env->file_open_child_call_mask = 0;
                env->file_open_child_return_mask = 0;
                memset(env->file_open_child_result_hi, 0,
                       sizeof(env->file_open_child_result_hi));
                memset(env->file_open_child_result_lo, 0,
                       sizeof(env->file_open_child_result_lo));
                memset(env->file_open_child_error, 0,
                       sizeof(env->file_open_child_error));
                env->file_open_dynamic_calls = 0;
                env->file_open_dynamic_record = 0;
                env->file_open_dynamic_target = 0;
                env->file_open_dynamic_returns = 0;
                env->file_open_dynamic_result_hi = 0;
                env->file_open_dynamic_result_lo = 0;
                env->file_open_dynamic_error = 0;
                env->file_open_driver_wrapper_hits = 0;
                env->file_open_driver_wrapper_word = 0;
                env->file_open_driver_child_calls = 0;
                env->file_open_driver_child_returns = 0;
                env->file_open_driver_child_result_hi = 0;
                env->file_open_driver_child_result_lo = 0;
                env->file_open_driver_mirror_calls = 0;
                env->file_open_driver_mirror_returns = 0;
                env->file_open_driver_mirror_result = 0;
                env->file_open_driver_status_calls = 0;
                env->file_open_driver_status_returns = 0;
                env->file_open_driver_status_result = 0;
                env->file_open_returns = 0;
                env->file_open_error_writes = 0;
                env->file_open_error_first_pc = 0;
                env->file_open_error_last_pc = 0;
                env->file_open_error_last_physical = 0;
                env->file_open_error_first_old = 0;
                env->file_open_error_first_value = 0;
                env->file_open_error_last_old = 0;
                env->file_open_error_last_value = 0;
                env->file_open_error_last_logical = 0;
                env->file_open_error_last_bits = 0;
                memset(env->file_open_error_trace_pc, 0,
                       sizeof(env->file_open_error_trace_pc));
                memset(env->file_open_error_trace_physical, 0,
                       sizeof(env->file_open_error_trace_physical));
                memset(env->file_open_error_trace_logical, 0,
                       sizeof(env->file_open_error_trace_logical));
                memset(env->file_open_error_trace_old, 0,
                       sizeof(env->file_open_error_trace_old));
                memset(env->file_open_error_trace_new, 0,
                       sizeof(env->file_open_error_trace_new));
                memset(env->file_open_error_trace_sp, 0,
                       sizeof(env->file_open_error_trace_sp));
                memset(env->file_open_error_trace_fp, 0,
                       sizeof(env->file_open_error_trace_fp));
                memset(env->file_open_error_trace_stage, 0,
                       sizeof(env->file_open_error_trace_stage));
                memset(env->file_open_error_trace_ds0, 0,
                       sizeof(env->file_open_error_trace_ds0));
                memset(env->file_open_error_trace_ds1, 0,
                       sizeof(env->file_open_error_trace_ds1));
                memset(env->file_open_error_trace_r0, 0,
                       sizeof(env->file_open_error_trace_r0));
                memset(env->file_open_error_trace_r1, 0,
                       sizeof(env->file_open_error_trace_r1));
                memset(env->file_open_error_trace_bits, 0,
                       sizeof(env->file_open_error_trace_bits));
                env->file_path_resolve_calls = 0;
                env->file_open_nested_calls = 0;
                env->file_open_nested_active_slot = 0xffffu;
                memset(env->file_open_nested_caller, 0,
                       sizeof(env->file_open_nested_caller));
                memset(env->file_open_nested_entry_sp, 0,
                       sizeof(env->file_open_nested_entry_sp));
                memset(env->file_open_nested_fp, 0,
                       sizeof(env->file_open_nested_fp));
                memset(env->file_open_nested_mode, 0,
                       sizeof(env->file_open_nested_mode));
                memset(env->file_open_nested_path_hi, 0,
                       sizeof(env->file_open_nested_path_hi));
                memset(env->file_open_nested_path_lo, 0,
                       sizeof(env->file_open_nested_path_lo));
                memset(env->file_open_nested_result_hi, 0,
                       sizeof(env->file_open_nested_result_hi));
                memset(env->file_open_nested_result_lo, 0,
                       sizeof(env->file_open_nested_result_lo));
                memset(env->file_open_nested_error, 0,
                       sizeof(env->file_open_nested_error));
                env->file_path_trace_active_slot = 0xffffu;
                memset(env->file_path_trace_caller, 0,
                       sizeof(env->file_path_trace_caller));
                memset(env->file_path_trace_fp, 0,
                       sizeof(env->file_path_trace_fp));
                memset(env->file_path_trace_stage, 0,
                       sizeof(env->file_path_trace_stage));
                memset(env->file_path_trace_object_hi, 0,
                       sizeof(env->file_path_trace_object_hi));
                memset(env->file_path_trace_object_lo, 0,
                       sizeof(env->file_path_trace_object_lo));
                memset(env->file_path_trace_input_hi, 0,
                       sizeof(env->file_path_trace_input_hi));
                memset(env->file_path_trace_input_lo, 0,
                       sizeof(env->file_path_trace_input_lo));
                memset(env->file_path_trace_result, 0,
                       sizeof(env->file_path_trace_result));
                memset(env->file_path_trace_error, 0,
                       sizeof(env->file_path_trace_error));
                memset(env->file_path_trace_data, 0,
                       sizeof(env->file_path_trace_data));
                env->file_open_patch_words[0] =
                    cpu_lduw_code(env, 0x1f225au);
                env->file_open_patch_words[1] =
                    cpu_lduw_code(env, 0x1f225cu);
                env->file_open_patch_words[2] =
                    cpu_lduw_code(env, 0x24eddeu);
                env->file_open_patch_words[3] =
                    cpu_lduw_code(env, 0x24ede0u);
                env->file_open_patch_words[4] =
                    cpu_lduw_code(env, 0x24ed46u);
                env->file_open_patch_words[5] =
                    cpu_lduw_code(env, 0x24ed48u);
                env->file_open_patch_words[6] =
                    cpu_lduw_code(env, 0x24ec7au);
                env->file_open_patch_words[7] =
                    cpu_lduw_code(env, 0x24ec7cu);
                env->file_open_patch_words[8] =
                    cpu_lduw_code(env, 0x24ed22u);
                env->file_open_patch_words[9] =
                    cpu_lduw_code(env, 0x24ed24u);
                env->file_open_patch_words[10] =
                    cpu_lduw_code(env, 0x1f22d6u);
                env->file_open_patch_words[11] =
                    cpu_lduw_code(env, 0x1f22d8u);
                env->file_open_patch_words[12] =
                    cpu_lduw_code(env, 0x1f2334u);
                env->file_open_patch_words[13] =
                    cpu_lduw_code(env, 0x1f2336u);
                env->file_open_patch_words[14] =
                    cpu_lduw_code(env, 0x1f2358u);
                env->file_open_patch_words[15] =
                    cpu_lduw_code(env, 0x1f235au);
                memset(env->file_open_path, 0, sizeof(env->file_open_path));
            }
        }
        if (env->file_open_watch_active &&
            control_target == 0x1f1f1au && op == 0xbdu) {
            uint16_t trace_slot = env->file_open_nested_calls %
                                  DMCU_FILE_PATH_TRACE_SLOTS;

            env->file_open_nested_active_slot = trace_slot;
            env->file_open_nested_caller[trace_slot] = control_from;
            env->file_open_nested_entry_sp[trace_slot] = sp;
            env->file_open_nested_calls++;
        }
        /* Attribute bad far-path pointers to the producer calling the
         * relocated wrapper, rather than only to resident fopen. */
        if (control_target == 0x30c9a2u && op == 0xbdu) {
            uint16_t trace_slot = env->file_wrapper_calls %
                                  DMCU_FILE_PATH_TRACE_SLOTS;

            env->file_wrapper_active_slot = trace_slot;
            env->file_wrapper_caller[trace_slot] = control_from;
            env->file_wrapper_entry_sp[trace_slot] = sp;
            memset(env->file_wrapper_entry_stack[trace_slot], 0,
                   sizeof(env->file_wrapper_entry_stack[trace_slot]));
            memset(env->file_wrapper_exit_stack[trace_slot], 0,
                   sizeof(env->file_wrapper_exit_stack[trace_slot]));
            env->file_wrapper_exit_sp[trace_slot] = 0;
            env->file_wrapper_exit_fp[trace_slot] = 0;
            env->file_wrapper_exit_target[trace_slot] = 0;
            env->file_wrapper_calls++;
        }
        if (control_from == 0x30c9a4u &&
            env->file_wrapper_active_slot < DMCU_FILE_PATH_TRACE_SLOTS) {
            uint16_t trace_slot = env->file_wrapper_active_slot;
            unsigned index;

            env->file_wrapper_fp[trace_slot] = fp;
            env->file_wrapper_path_hi[trace_slot] =
                internal_data_read((fp + 0x06u) & MASK16, 16);
            env->file_wrapper_path_lo[trace_slot] =
                internal_data_read((fp + 0x08u) & MASK16, 16);
            env->file_wrapper_flags[trace_slot] =
                internal_data_read((fp + 0x0au) & MASK16, 16);
            for (index = 0; index < DMCU_FILE_WRAPPER_STACK_WORDS; index++) {
                env->file_wrapper_entry_stack[trace_slot][index] =
                    internal_data_read((fp + index * 2u) & MASK16, 16);
            }
            if (env->file_wrapper_path_hi[trace_slot] == 0x0031u &&
                env->file_wrapper_path_lo[trace_slot] == 0x940eu) {
                env->file_wrapper_frame_watch_active = true;
                env->file_wrapper_frame_base = fp;
                env->file_wrapper_frame_writes = 0;
            }
        }
        if (env->file_open_watch_active &&
            control_from >= 0x1f1f1au && control_from <= 0x1f2548u) {
            env->file_open_last_from = control_from;
            env->file_open_last_target = control_target;
            env->file_open_last_sp = sp;
            env->file_open_last_fp = fp;
            env->file_open_last_r0 = env->gpr[0] & MASK16;
            env->file_open_last_r1 = env->gpr[1] & MASK16;
            env->file_open_last_r2 = env->gpr[2] & MASK16;
            env->file_open_last_r3 = env->gpr[3] & MASK16;
        }
        if (env->file_open_watch_active && !env->file_open_args_captured &&
            control_from == 0x1f1f2cu) {
            uint32_t path;
            unsigned index;

            env->file_open_mode =
                internal_data_read((fp + 0x0au) & MASK16, 16);
            env->file_open_path_hi =
                internal_data_read((fp + 0x06u) & MASK16, 16);
            env->file_open_path_lo =
                internal_data_read((fp + 0x08u) & MASK16, 16);
            env->file_open_f01a = internal_data_read(0xf01au, 16);
            path = (((uint32_t)env->file_open_path_hi << 16) |
                    env->file_open_path_lo) & MASK24;
            for (index = 0; index < sizeof(env->file_open_path); index++) {
                if (env->file_open_path_hi == 0) {
                    env->file_open_path[index] = internal_data_read(
                        (env->file_open_path_lo + index) & MASK16, 8);
                } else {
                    env->file_open_path[index] = address_space_ldub(
                        &address_space_memory, ((path + index) & MASK24) ^ 1u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
                }
            }
            env->file_open_args_captured = true;
        }
        if (env->file_open_watch_active &&
            control_from == 0x1f1f2cu &&
            env->file_open_nested_active_slot <
                DMCU_FILE_PATH_TRACE_SLOTS) {
            uint16_t trace_slot = env->file_open_nested_active_slot;

            env->file_open_nested_fp[trace_slot] = fp;
            env->file_open_nested_mode[trace_slot] =
                internal_data_read((fp + 0x0au) & MASK16, 16);
            env->file_open_nested_path_hi[trace_slot] =
                internal_data_read((fp + 0x06u) & MASK16, 16);
            env->file_open_nested_path_lo[trace_slot] =
                internal_data_read((fp + 0x08u) & MASK16, 16);
        }
        /* Selected 2D:D93C path walk.  The generic fopen trace retains only
         * the child's final FFFC status; this narrow observer records the
         * component string before and after 28:D7E2, plus the directory
         * object's attribute and continuation pointer.  It never changes
         * guest registers, memory, or control flow. */
        if (env->file_open_watch_active &&
            control_from == 0x2dd93cu && word == 0x2e08u) {
            uint16_t path_fp = env->gpr[DMCU_FP] & MASK16;
            uint16_t trace_slot = env->file_path_resolve_calls %
                                  DMCU_FILE_PATH_TRACE_SLOTS;
            uint32_t input;
            unsigned index;

            env->file_path_trace_active_slot = trace_slot;
            env->file_path_trace_caller[trace_slot] =
                ((uint32_t)internal_data_read(
                    (path_fp + 2u) & MASK16, 16) << 16) |
                internal_data_read((path_fp + 4u) & MASK16, 16);
            env->file_path_trace_fp[trace_slot] = path_fp;
            env->file_path_trace_stage[trace_slot] = env->file_open_stage;
            env->file_path_trace_object_hi[trace_slot] =
                internal_data_read((path_fp + 6u) & MASK16, 16);
            env->file_path_trace_object_lo[trace_slot] =
                internal_data_read((path_fp + 8u) & MASK16, 16);
            env->file_path_trace_input_hi[trace_slot] =
                internal_data_read((path_fp + 10u) & MASK16, 16);
            env->file_path_trace_input_lo[trace_slot] =
                internal_data_read((path_fp + 12u) & MASK16, 16);
            input = (((uint32_t)env->file_path_trace_input_hi[trace_slot]
                      << 16) |
                     env->file_path_trace_input_lo[trace_slot]) & MASK24;
            for (index = 0; index < DMCU_FILE_PATH_TRACE_BYTES; index++) {
                env->file_path_trace_data[trace_slot][index] =
                    env->file_path_trace_input_hi[trace_slot] == 0 ?
                    internal_data_read(
                        (env->file_path_trace_input_lo[trace_slot] + index) &
                        MASK16, 8) :
                    address_space_ldub(
                        &address_space_memory,
                        ((input + index) & MASK24) ^ 1u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
            }
            if (env->file_path_resolve_calls) {
                env->file_path_resolve_calls++;
                goto file_path_primary_entry_done;
            }
            env->file_path_resolve_calls++;
            env->file_path_primary_watch_active = true;
            env->file_path_resolve_caller =
                ((uint32_t)internal_data_read(
                    (path_fp + 2u) & MASK16, 16) << 16) |
                internal_data_read((path_fp + 4u) & MASK16, 16);
            env->file_path_resolve_sp = sp;
            env->file_path_resolve_fp = path_fp;
            env->file_path_resolve_object_hi =
                internal_data_read((path_fp + 6u) & MASK16, 16);
            env->file_path_resolve_object_lo =
                internal_data_read((path_fp + 8u) & MASK16, 16);
            env->file_path_resolve_input_hi =
                internal_data_read((path_fp + 10u) & MASK16, 16);
            env->file_path_resolve_input_lo =
                internal_data_read((path_fp + 12u) & MASK16, 16);
            env->file_path_component_result_hi = 0xffffu;
            env->file_path_component_result_lo = 0xffffu;
            env->file_path_component_fp = 0xffffu;
            env->file_component_watch_active = false;
            env->file_component_entry_sp = 0xffffu;
            env->file_component_entry_fp = 0xffffu;
            env->file_component_exit_sp = 0xffffu;
            env->file_component_exit_fp = 0xffffu;
            env->file_component_entry_irq = env->interrupt_entries;
            env->file_component_daac_irq = 0;
            env->file_component_rets_irq = 0;
            env->file_component_exit_irq = 0;
            env->file_component_arg_entry_hi = 0xffffu;
            env->file_component_arg_entry_lo = 0xffffu;
            env->file_component_arg_daac_hi = 0xffffu;
            env->file_component_arg_daac_lo = 0xffffu;
            env->file_component_arg_rets_hi = 0xffffu;
            env->file_component_arg_rets_lo = 0xffffu;
            env->file_component_result_rets_hi = 0xffffu;
            env->file_component_result_rets_lo = 0xffffu;
            env->file_component_write_count = 0;
            memset(env->file_component_frame_entry, 0,
                   sizeof(env->file_component_frame_entry));
            memset(env->file_component_frame_exit, 0,
                   sizeof(env->file_component_frame_exit));
            memset(env->file_component_write_pc, 0,
                   sizeof(env->file_component_write_pc));
            env->file_path_resolver_call_fp = 0xffffu;
            env->file_path_resolver_return_fp = 0xffffu;
            env->file_path_resolve_remaining_hi = 0;
            env->file_path_resolve_remaining_lo = 0;
            env->file_path_resolve_selector = 0;
            env->file_path_resolve_result = 0xffffu;
            env->file_path_resolve_failure_pc = 0;
            env->file_path_resolve_final_result = 0xffffu;
            env->file_path_resolve_child_hi = 0;
            env->file_path_resolve_child_lo = 0;
            env->file_path_resolve_attribute = 0;
            env->file_path_resolve_remaining_char = 0;
            memset(env->file_path_resolve_input, 0,
                   sizeof(env->file_path_resolve_input));
            memset(env->file_path_resolve_remaining, 0,
                   sizeof(env->file_path_resolve_remaining));
            memset(env->file_path_resolve_object, 0,
                   sizeof(env->file_path_resolve_object));
            input = (((uint32_t)env->file_path_resolve_input_hi << 16) |
                     env->file_path_resolve_input_lo) & MASK24;
            for (index = 0; index < sizeof(env->file_path_resolve_input);
                 index++) {
                env->file_path_resolve_input[index] =
                    env->file_path_resolve_input_hi == 0 ?
                    internal_data_read(
                        (env->file_path_resolve_input_lo + index) & MASK16,
                        8) :
                    address_space_ldub(
                        &address_space_memory, ((input + index) & MASK24) ^ 1u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
            }
file_path_primary_entry_done:
            ;
        }
        if (env->file_open_watch_active &&
            control_target == 0x28d7e2u && op == 0xbdu &&
            env->file_path_primary_watch_active) {
            uint16_t component_fp =
                ((env->gpr[DMCU_SP] & MASK16) - 2u) & MASK16;
            unsigned index;

            env->file_component_watch_active = true;
            env->file_component_entry_sp = env->gpr[DMCU_SP] & MASK16;
            env->file_component_entry_fp = component_fp;
            env->file_component_entry_irq = env->interrupt_entries;
            env->file_component_arg_entry_hi =
                internal_data_read((component_fp + 0x0au) & MASK16, 16);
            env->file_component_arg_entry_lo =
                internal_data_read((component_fp + 0x0cu) & MASK16, 16);
            for (index = 0; index < DMCU_FILE_COMPONENT_FRAME_WORDS;
                 index++) {
                env->file_component_frame_entry[index] =
                    internal_data_read(
                        (component_fp - 0x10u + index * 2u) & MASK16, 16);
            }
        }
        if (env->file_open_watch_active &&
            control_target == 0x2dd96eu && op == 0xc6u &&
            env->file_path_primary_watch_active) {
            uint16_t component_fp = env->file_component_entry_fp;
            unsigned index;

            env->file_path_component_result_hi = env->gpr[0] & MASK16;
            env->file_path_component_result_lo = env->gpr[1] & MASK16;
            env->file_path_component_fp = env->gpr[DMCU_FP] & MASK16;
            env->file_component_exit_sp = env->gpr[DMCU_SP] & MASK16;
            env->file_component_exit_fp = env->gpr[DMCU_FP] & MASK16;
            env->file_component_exit_irq = env->interrupt_entries;
            for (index = 0; index < DMCU_FILE_COMPONENT_FRAME_WORDS;
                 index++) {
                env->file_component_frame_exit[index] =
                    internal_data_read(
                        (component_fp - 0x10u + index * 2u) & MASK16, 16);
            }
            env->file_component_watch_active = false;
        }
        if (env->file_open_watch_active &&
            control_from == 0x2dd9e2u && op == 0xbdu &&
            env->file_path_primary_watch_active) {
            uint16_t path_fp = env->gpr[DMCU_FP] & MASK16;
            uint32_t object;
            uint32_t remaining;
            unsigned index;

            env->file_path_resolver_call_fp = path_fp;
            env->file_path_resolve_remaining_hi =
                internal_data_read((path_fp + 10u) & MASK16, 16);
            env->file_path_resolve_remaining_lo =
                internal_data_read((path_fp + 12u) & MASK16, 16);
            object = (((uint32_t)env->file_path_resolve_object_hi << 16) |
                      env->file_path_resolve_object_lo) & MASK24;
            remaining =
                (((uint32_t)env->file_path_resolve_remaining_hi << 16) |
                 env->file_path_resolve_remaining_lo) & MASK24;
            env->file_path_resolve_selector = address_space_lduw_le(
                &address_space_memory, (object + 0x30u) & MASK24,
                MEMTXATTRS_UNSPECIFIED, NULL);
            env->file_path_resolve_remaining_char =
                env->file_path_resolve_remaining_hi == 0 ?
                internal_data_read(env->file_path_resolve_remaining_lo, 8) :
                address_space_ldub(
                    &address_space_memory, remaining ^ 1u,
                    MEMTXATTRS_UNSPECIFIED, NULL);
            for (index = 0; index < sizeof(env->file_path_resolve_remaining);
                 index++) {
                env->file_path_resolve_remaining[index] =
                    env->file_path_resolve_remaining_hi == 0 ?
                    internal_data_read(
                        (env->file_path_resolve_remaining_lo + index) &
                        MASK16, 8) :
                    address_space_ldub(
                        &address_space_memory,
                        ((remaining + index) & MASK24) ^ 1u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
        if (env->file_open_watch_active &&
            control_target == 0x2dd9e6u && op == 0xc6u &&
            env->file_path_primary_watch_active) {
            uint32_t object;
            unsigned index;

            env->file_path_resolver_return_fp =
                env->gpr[DMCU_FP] & MASK16;
            env->file_path_resolve_result = env->gpr[0] & MASK16;
            object = (((uint32_t)env->file_path_resolve_object_hi << 16) |
                      env->file_path_resolve_object_lo) & MASK24;
            env->file_path_resolve_attribute = address_space_ldub(
                &address_space_memory, ((object + 0x14u) & MASK24) ^ 1u,
                MEMTXATTRS_UNSPECIFIED, NULL);
            env->file_path_resolve_child_hi = address_space_lduw_le(
                &address_space_memory, (object + 0x22u) & MASK24,
                MEMTXATTRS_UNSPECIFIED, NULL);
            env->file_path_resolve_child_lo = address_space_lduw_le(
                &address_space_memory, (object + 0x24u) & MASK24,
                MEMTXATTRS_UNSPECIFIED, NULL);
            for (index = 0; index < sizeof(env->file_path_resolve_object);
                 index++) {
                env->file_path_resolve_object[index] = address_space_ldub(
                    &address_space_memory, ((object + index) & MASK24) ^ 1u,
                    MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
        if (env->file_open_watch_active &&
            env->file_path_primary_watch_active &&
            control_target == 0x2dda72u &&
            ((control_from == 0x2dda48u) ||
             (control_from == 0x2dda6eu))) {
            env->file_path_resolve_failure_pc = control_from & MASK16;
        }
        if (env->file_open_watch_active &&
            control_from == 0x2ddad8u && op == 0xc6u &&
            env->file_path_trace_active_slot <
                DMCU_FILE_PATH_TRACE_SLOTS) {
            uint16_t trace_slot = env->file_path_trace_active_slot;

            env->file_path_trace_result[trace_slot] = env->gpr[0] & MASK16;
            env->file_path_trace_error[trace_slot] =
                address_space_lduw_le(
                    &address_space_memory, 0x512ae0u,
                    MEMTXATTRS_UNSPECIFIED, NULL);
            env->file_path_trace_active_slot = 0xffffu;
        }
        if (env->file_open_watch_active &&
            env->file_path_primary_watch_active &&
            control_from == 0x2ddad8u && op == 0xc6u) {
            env->file_path_resolve_final_result = env->gpr[0] & MASK16;
            env->file_path_primary_watch_active = false;
        }
        for (child = 0; child < ARRAY_SIZE(child_calls); child++) {
            if (env->file_open_watch_active &&
                control_from == child_calls[child] && op == 0xbdu) {
                env->file_open_child_calls++;
                env->file_open_child_call_mask |= 1u << child;
                env->file_open_stage = 2 + child;
                break;
            }
            if (env->file_open_watch_active &&
                control_target == child_calls[child] + 4u && op == 0xc6u) {
                env->file_open_child_returns++;
                env->file_open_child_return_mask |= 1u << child;
                env->file_open_child_result_hi[child] =
                    env->gpr[0] & MASK16;
                env->file_open_child_result_lo[child] =
                    env->gpr[1] & MASK16;
                env->file_open_child_error[child] =
                    address_space_lduw_le(
                        &address_space_memory, 0x512ae0u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
                break;
            }
        }
        if (env->file_open_watch_active &&
            control_from == 0x1f2458u && op == 0xc6u) {
            uint16_t record_hi = address_space_lduw_le(
                &address_space_memory, 0x005129c4u,
                MEMTXATTRS_UNSPECIFIED, NULL);
            uint16_t record_lo = address_space_lduw_le(
                &address_space_memory, 0x005129c6u,
                MEMTXATTRS_UNSPECIFIED, NULL);

            env->file_open_dynamic_calls++;
            env->file_open_dynamic_record =
                (((uint32_t)record_hi << 16) | record_lo) & MASK24;
            env->file_open_dynamic_target = control_target;
        } else if (env->file_open_watch_active &&
                   control_target == 0x1f245au && op == 0xc6u) {
            env->file_open_dynamic_returns++;
            env->file_open_dynamic_result_hi = env->gpr[0] & MASK16;
            env->file_open_dynamic_result_lo = env->gpr[1] & MASK16;
            env->file_open_dynamic_error = address_space_lduw_le(
                &address_space_memory, 0x00512ae0u,
                MEMTXATTRS_UNSPECIFIED, NULL);
        }
        if (env->file_open_watch_active && control_from == 0x1af040u) {
            env->file_open_driver_wrapper_hits++;
            env->file_open_driver_wrapper_word = word;
        }
        if (env->file_open_watch_active && control_from == 0x1af042u &&
            control_target == 0x1af000u && op == 0xbdu) {
            env->file_open_driver_child_calls++;
        } else if (env->file_open_watch_active &&
                   control_target == 0x1af046u && op == 0xc6u) {
            env->file_open_driver_child_returns++;
            env->file_open_driver_child_result_hi = env->gpr[0] & MASK16;
            env->file_open_driver_child_result_lo = env->gpr[1] & MASK16;
        }
        if (env->file_open_watch_active && control_from == 0x1af006u &&
            control_target == 0x29d878u && op == 0xbdu) {
            env->file_open_driver_mirror_calls++;
        } else if (env->file_open_watch_active &&
                   control_target == 0x1af00au && op == 0xc6u) {
            env->file_open_driver_mirror_returns++;
            env->file_open_driver_mirror_result = env->gpr[0] & MASK16;
        }
        if (env->file_open_watch_active && control_from == 0x1af00eu &&
            control_target == 0x31b33cu && op == 0xbdu) {
            env->file_open_driver_status_calls++;
        } else if (env->file_open_watch_active &&
                   control_target == 0x1af012u && op == 0xc6u) {
            env->file_open_driver_status_returns++;
            env->file_open_driver_status_result = env->gpr[0] & MASK16;
        }
        if (env->file_open_watch_active &&
            control_from == 0x1f1f52u && control_target == 0x1f2540u) {
            env->file_open_stage = 64; /* write-protect fast rejection */
        } else if (env->file_open_watch_active &&
                   control_from == 0x1f1f86u &&
                   control_target == 0x1f253au) {
            env->file_open_stage = 65; /* path resolver rejected input */
        } else if (env->file_open_watch_active &&
                   control_target == 0x1f253au && op == 0xacu &&
                   env->file_open_stage < 64) {
            env->file_open_stage = 66; /* later construction error */
        }
        if (env->file_open_watch_active &&
            control_from == 0x1f2546u && op == 0xc6u &&
            env->file_open_nested_active_slot <
                DMCU_FILE_PATH_TRACE_SLOTS) {
            uint16_t trace_slot = env->file_open_nested_active_slot;

            env->file_open_nested_result_hi[trace_slot] =
                env->gpr[0] & MASK16;
            env->file_open_nested_result_lo[trace_slot] =
                env->gpr[1] & MASK16;
            env->file_open_nested_error[trace_slot] = address_space_lduw_le(
                &address_space_memory, 0x512ae0u,
                MEMTXATTRS_UNSPECIFIED, NULL);
            env->file_open_nested_active_slot = 0xffffu;
        }
        if (control_from == 0x30ca82u && op == 0xc6u &&
            env->file_wrapper_active_slot < DMCU_FILE_PATH_TRACE_SLOTS) {
            uint16_t trace_slot = env->file_wrapper_active_slot;
            unsigned index;

            env->file_wrapper_result_hi[trace_slot] = env->gpr[0] & MASK16;
            env->file_wrapper_result_lo[trace_slot] = env->gpr[1] & MASK16;
            env->file_wrapper_exit_sp[trace_slot] = sp;
            env->file_wrapper_exit_fp[trace_slot] = fp;
            env->file_wrapper_exit_target[trace_slot] = control_target;
            for (index = 0; index < DMCU_FILE_WRAPPER_STACK_WORDS; index++) {
                env->file_wrapper_exit_stack[trace_slot][index] =
                    internal_data_read((sp + index * 2u) & MASK16, 16);
            }
            env->file_wrapper_frame_watch_active = false;
            env->file_wrapper_active_slot = 0xffffu;
        }
        if (env->file_open_watch_active &&
            control_target == 0x58b1b8u && op == 0xc6u) {
            env->file_open_returns++;
            env->file_open_result_hi = env->gpr[0] & MASK16;
            env->file_open_result_lo = env->gpr[1] & MASK16;
            env->file_open_error = address_space_lduw_le(
                &address_space_memory, 0x512ae0u,
                MEMTXATTRS_UNSPECIFIED, NULL);
            if (env->file_open_stage < 64) {
                env->file_open_stage = 18;
            }
            env->file_open_watch_active = false;
        }
    }

    /* Persistent, read-only trace for the exact 07:4000 copy of source
     * 4A:3460.  Resident fopen reaches this resolver while creating a file.
     * The resolver selects two callbacks through storage records; preserving
     * their dynamic targets and results makes allocation failures observable
     * without intercepting either callback. */
    {
        uint32_t control_from = from & MASK24;
        uint32_t control_target = env->pc & MASK24;
        uint32_t record = (
            ((uint32_t)address_space_lduw_le(
                &address_space_memory, 0x005129c4u,
                MEMTXATTRS_UNSPECIFIED, NULL) << 16) |
            address_space_lduw_le(
                &address_space_memory, 0x005129c6u,
                MEMTXATTRS_UNSPECIFIED, NULL)) & MASK24;

        if (control_target == 0x074000u && op == 0xbdu) {
            env->storage_driver_calls++;
            env->storage_driver_caller = control_from;
            env->storage_driver_argument = internal_data_read(sp, 16);
            env->storage_driver_first_record = 0;
            env->storage_driver_first_status = 0xffffu;
            env->storage_driver_callback1_calls = 0;
            env->storage_driver_callback1_target = 0;
            env->storage_driver_callback1_result_hi = 0;
            env->storage_driver_callback1_result_lo = 0;
            env->storage_driver_second_record = 0;
            env->storage_driver_callback2_calls = 0;
            env->storage_driver_callback2_target = 0;
            env->storage_driver_callback2_result_hi = 0;
            env->storage_driver_callback2_result_lo = 0;
            env->storage_driver_return_target = 0;
            env->storage_driver_result_hi = 0;
            env->storage_driver_result_lo = 0;
        } else if (control_from == 0x07405au) {
            env->storage_driver_first_record = record;
            env->storage_driver_first_status = env->gpr[0] & MASK16;
        } else if (control_from == 0x0740d6u && op == 0xc6u) {
            env->storage_driver_callback1_calls++;
            env->storage_driver_callback1_target = control_target;
            env->storage_driver_second_record = record;
        } else if (control_target == 0x0740d8u && op == 0xc6u) {
            env->storage_driver_callback1_result_hi = env->gpr[0] & MASK16;
            env->storage_driver_callback1_result_lo = env->gpr[1] & MASK16;
        } else if (control_from == 0x07414eu && op == 0xc6u) {
            env->storage_driver_callback2_calls++;
            env->storage_driver_callback2_target = control_target;
            env->storage_driver_second_record = record;
        } else if (control_target == 0x074150u && op == 0xc6u) {
            env->storage_driver_callback2_result_hi = env->gpr[0] & MASK16;
            env->storage_driver_callback2_result_lo = env->gpr[1] & MASK16;
        } else if (control_from == 0x0741c6u && op == 0xc6u) {
            env->storage_driver_returns++;
            env->storage_driver_return_target = control_target;
            env->storage_driver_result_hi = env->gpr[0] & MASK16;
            env->storage_driver_result_lo = env->gpr[1] & MASK16;
        }
    }

    /* One-shot catalogue-commit diagnosis for the native provisioner.  It
     * spans resident fopen's record-status/apply closure and the later
     * 24:EAEC close routine, retaining the last exact milestone after the
     * generic control ring has wrapped.  This observes guest state only. */
    {
        static const uint32_t close_child_calls[] = {
            0x24eb54u, 0x24ebdeu, 0x24ec7au, 0x24ed0au,
            0x24ed22u, 0x24ed46u, 0x24ed96u, 0x24eddeu,
            0x24ee28u, 0x24ee90u, 0x24eeecu,
        };
        uint32_t control_from = from & MASK24;
        uint32_t control_target = env->pc & MASK24;
        bool milestone = false;
        unsigned child;

        if (control_from == 0x58b1b4u &&
            control_target == 0x1f1f1au && op == 0xbdu) {
            env->file_commit_watch_active = true;
            env->file_commit_stage = 1;
            env->file_commit_last_child = 0;
            env->file_commit_caller = control_from;
            env->file_commit_file = 0;
            env->file_commit_record = 0;
            env->file_commit_child_calls = 0;
            env->file_commit_child_returns = 0;
            env->file_commit_child_call_mask = 0;
            env->file_commit_child_return_mask = 0;
            memset(env->file_commit_child_result_hi, 0,
                   sizeof(env->file_commit_child_result_hi));
            memset(env->file_commit_child_result_lo, 0,
                   sizeof(env->file_commit_child_result_lo));
            memset(env->file_commit_child_error, 0,
                   sizeof(env->file_commit_child_error));
            env->file_commit_error_writes = 0;
            env->file_commit_error_first_pc = 0;
            env->file_commit_error_last_pc = 0;
            env->file_commit_error_first_old = 0;
            env->file_commit_error_first_value = 0;
            env->file_commit_error_last_old = 0;
            env->file_commit_error_last_value = 0;
            env->file_commit_error_last_stage = 0;
            env->file_commit_status_calls = 0;
            env->file_commit_status_returns = 0;
            env->file_commit_select_calls = 0;
            env->file_commit_select_returns = 0;
            env->file_commit_apply_calls = 0;
            env->file_commit_apply_returns = 0;
            env->file_commit_pair_calls = 0;
            env->file_commit_pair_returns = 0;
            env->file_commit_driver_calls = 0;
            env->file_commit_driver_returns = 0;
            env->file_commit_callback_calls = 0;
            env->file_commit_callback_returns = 0;
            env->file_commit_returns = 0;
            memset(env->file_commit_record_data, 0,
                   sizeof(env->file_commit_record_data));
            memset(env->file_commit_file_data, 0,
                   sizeof(env->file_commit_file_data));
            milestone = true;
        }
        if (env->file_commit_watch_active && control_target == 0x5d5cdcu &&
            op == 0xbdu) {
            uint16_t record_hi = internal_data_read(sp, 16);
            uint16_t record_lo = internal_data_read((sp + 2u) & MASK16, 16);
            uint32_t record = (((uint32_t)record_hi << 16) | record_lo) & MASK24;
            unsigned index;

            env->file_commit_status_calls++;
            env->file_commit_stage = 10;
            env->file_commit_record = record;
            for (index = 0; index < sizeof(env->file_commit_record_data); index++) {
                if (record_hi == 0) {
                    env->file_commit_record_data[index] = internal_data_read(
                        (record_lo + index) & MASK16, 8);
                } else {
                    env->file_commit_record_data[index] = address_space_ldub(
                        &address_space_memory, ((record + index) & MASK24) ^ 1u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
                }
            }
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_from == 0x5d5d78u &&
                   control_target == 0x074200u && op == 0xbdu) {
            env->file_commit_select_calls++;
            env->file_commit_stage = 11;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_target == 0x5d5d7cu && op == 0xc6u) {
            env->file_commit_select_returns++;
            env->file_commit_stage = 12;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_from == 0x5d5e0cu &&
                   control_target == 0x5de3a6u && op == 0xbdu) {
            env->file_commit_apply_calls++;
            env->file_commit_stage = 13;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_from == 0x5de426u &&
                   control_target == 0x074500u && op == 0xbdu) {
            env->file_commit_pair_calls++;
            env->file_commit_stage = 14;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_target == 0x5de42au && op == 0xc6u) {
            env->file_commit_pair_returns++;
            env->file_commit_stage = 15;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_from == 0x5de43cu &&
                   control_target == 0x074000u && op == 0xbdu) {
            env->file_commit_driver_calls++;
            env->file_commit_stage = 16;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_target == 0x5de440u && op == 0xc6u) {
            env->file_commit_driver_returns++;
            env->file_commit_stage = 17;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   (control_from == 0x5de558u ||
                    control_from == 0x5de5d4u) && op == 0xc6u) {
            env->file_commit_callback_calls++;
            env->file_commit_stage = control_from == 0x5de558u ? 18 : 20;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   (control_target == 0x5de55au ||
                    control_target == 0x5de5d6u) && op == 0xc6u) {
            env->file_commit_callback_returns++;
            env->file_commit_stage = control_target == 0x5de55au ? 19 : 21;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_from == 0x5de5f4u &&
                   control_target == 0x5d5e10u && op == 0xc6u) {
            env->file_commit_apply_returns++;
            env->file_commit_stage = 22;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_target == 0x1f2222u && op == 0xc6u) {
            env->file_commit_status_returns++;
            env->file_commit_stage = 23;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_target == 0x58b1b8u && op == 0xc6u) {
            env->file_commit_file =
                (((uint32_t)(env->gpr[0] & MASK16) << 16) |
                 (env->gpr[1] & MASK16)) & MASK24;
            env->file_commit_stage = 30;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_from == 0x58b1e8u &&
                   control_target == 0x24eaecu && op == 0xbdu) {
            uint16_t file_hi = internal_data_read(sp, 16);
            uint16_t file_lo = internal_data_read((sp + 2u) & MASK16, 16);
            uint32_t file = (((uint32_t)file_hi << 16) | file_lo) & MASK24;
            unsigned index;

            env->file_commit_calls++;
            env->file_commit_file = file;
            /* Restrict error provenance to close/commit itself.  Fopen and
             * the 256 preceding writes already have separate diagnostics. */
            env->file_commit_error_writes = 0;
            env->file_commit_error_first_pc = 0;
            env->file_commit_error_last_pc = 0;
            env->file_commit_error_first_old = 0;
            env->file_commit_error_first_value = 0;
            env->file_commit_error_last_old = 0;
            env->file_commit_error_last_value = 0;
            env->file_commit_error_last_stage = 0;
            for (index = 0; index < sizeof(env->file_commit_file_data); index++) {
                if (file_hi == 0) {
                    env->file_commit_file_data[index] = internal_data_read(
                        (file_lo + index) & MASK16, 8);
                } else {
                    env->file_commit_file_data[index] = address_space_ldub(
                        &address_space_memory, ((file + index) & MASK24) ^ 1u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
                }
            }
            env->file_commit_stage = 40;
            milestone = true;
        }
        for (child = 0; child < ARRAY_SIZE(close_child_calls); child++) {
            if (!env->file_commit_watch_active) {
                break;
            }
            if (control_from == close_child_calls[child] && op == 0xbdu) {
                env->file_commit_child_calls++;
                env->file_commit_child_call_mask |= 1u << child;
                env->file_commit_last_child = child + 1u;
                env->file_commit_stage = 41 + child * 2u;
                milestone = true;
                break;
            }
            if (control_target == close_child_calls[child] + 4u &&
                op == 0xc6u) {
                env->file_commit_child_returns++;
                env->file_commit_child_return_mask |= 1u << child;
                env->file_commit_last_child = child + 1u;
                env->file_commit_child_result_hi[child] =
                    env->gpr[0] & MASK16;
                env->file_commit_child_result_lo[child] =
                    env->gpr[1] & MASK16;
                env->file_commit_child_error[child] =
                    address_space_lduw_le(
                        &address_space_memory, 0x00512ae0u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
                env->file_commit_stage = 42 + child * 2u;
                milestone = true;
                break;
            }
        }
        if (env->file_commit_watch_active && control_from == 0x24eecau &&
            op == 0xc6u) {
            env->file_commit_child_calls++;
            env->file_commit_child_call_mask |=
                1u << ARRAY_SIZE(close_child_calls);
            env->file_commit_last_child = ARRAY_SIZE(close_child_calls) + 1u;
            env->file_commit_stage = 90;
            milestone = true;
        } else if (env->file_commit_watch_active &&
                   control_target == 0x24eeccu && op == 0xc6u) {
            env->file_commit_child_returns++;
            env->file_commit_child_return_mask |=
                1u << ARRAY_SIZE(close_child_calls);
            env->file_commit_last_child = ARRAY_SIZE(close_child_calls) + 1u;
            env->file_commit_child_result_hi[ARRAY_SIZE(close_child_calls)] =
                env->gpr[0] & MASK16;
            env->file_commit_child_result_lo[ARRAY_SIZE(close_child_calls)] =
                env->gpr[1] & MASK16;
            env->file_commit_child_error[ARRAY_SIZE(close_child_calls)] =
                address_space_lduw_le(
                    &address_space_memory, 0x00512ae0u,
                    MEMTXATTRS_UNSPECIFIED, NULL);
            env->file_commit_stage = 91;
            milestone = true;
        }
        if (env->file_commit_watch_active &&
            control_target == 0x58b1ecu && op == 0xc6u) {
            env->file_commit_returns++;
            env->file_commit_result_hi = env->gpr[0] & MASK16;
            env->file_commit_result_lo = env->gpr[1] & MASK16;
            env->file_commit_stage = 100;
            milestone = true;
            env->file_commit_watch_active = false;
        }
        if (milestone) {
            env->file_commit_last_from = control_from;
            env->file_commit_last_target = control_target;
            env->file_commit_last_sp = sp;
            env->file_commit_last_fp = fp;
            env->file_commit_last_r0 = env->gpr[0] & MASK16;
            env->file_commit_last_r1 = env->gpr[1] & MASK16;
            env->file_commit_last_r2 = env->gpr[2] & MASK16;
            env->file_commit_last_r3 = env->gpr[3] & MASK16;
        }
    }

    /* Persistent milestones for the finite 29:02D8 storage-capacity scan.
     * The ordinary control ring is quickly overwritten by timer activity,
     * while this one-shot call is the first non-returning boundary currently
     * observed beneath 2B:2F44.  Record only its six calls and their returns;
     * this is read-only diagnosis and does not alter guest control flow. */
    {
        uint16_t capacity_stage = 0;
        uint32_t control_from = from & MASK24;
        uint32_t control_target = env->pc & MASK24;

        if (control_target == 0x2902d8u && op == 0xbdu) {
            env->capacity_scan_calls++;
            capacity_stage = 1;
        } else if (control_from == 0x290306u &&
                   control_target == 0x3307b0u && op == 0xbdu) {
            capacity_stage = 2;
        } else if (control_target == 0x29030au && op == 0xc6u) {
            capacity_stage = 3;
        } else if (control_from == 0x2903aau &&
                   control_target == 0x330b24u && op == 0xbdu) {
            capacity_stage = 4;
        } else if (control_target == 0x2903aeu && op == 0xc6u) {
            capacity_stage = 5;
        } else if (control_from == 0x290416u &&
                   control_target == 0x2ad374u && op == 0xbdu) {
            capacity_stage = 6;
        } else if (control_target == 0x29041au && op == 0xc6u) {
            capacity_stage = 7;
        } else if (control_from == 0x290446u &&
                   control_target == 0x3307b0u && op == 0xbdu) {
            capacity_stage = 8;
        } else if (control_target == 0x29044au && op == 0xc6u) {
            capacity_stage = 9;
        } else if (control_from == 0x290536u &&
                   control_target == 0x20f928u && op == 0xbdu) {
            capacity_stage = 10;
        } else if (control_target == 0x29053au && op == 0xc6u) {
            capacity_stage = 11;
        } else if (control_from == 0x29059eu &&
                   control_target == 0x3307b0u && op == 0xbdu) {
            capacity_stage = 12;
        } else if (control_target == 0x2905a2u && op == 0xc6u) {
            capacity_stage = 13;
        } else if (control_from == 0x2905aeu && op == 0xc6u) {
            capacity_stage = 14;
            env->capacity_scan_returns++;
        }
        if (capacity_stage) {
            env->capacity_scan_stage = capacity_stage;
            env->capacity_scan_last_from = control_from;
            env->capacity_scan_last_target = control_target;
            env->capacity_scan_last_sp = sp;
            env->capacity_scan_last_fp = fp;
            env->capacity_scan_last_r0 = env->gpr[0] & MASK16;
            env->capacity_scan_last_r1 = env->gpr[1] & MASK16;
            env->capacity_scan_last_r2 = env->gpr[2] & MASK16;
            env->capacity_scan_last_r3 = env->gpr[3] & MASK16;
        }
    }

    /* One-shot registry initializer milestones.  Its capacity child is now
     * known to return, so count the result-loader and all 25 fixed entry
     * creations separately to expose the exact next non-returning edge. */
    {
        uint16_t registry_stage = 0;
        uint32_t control_from = from & MASK24;
        uint32_t control_target = env->pc & MASK24;
        bool entry_call =
            control_from >= 0x2b2f92u && control_from <= 0x2b3142u &&
            ((control_from - 0x2b2f92u) % 0x12u) == 0 && op == 0xbdu;
        bool entry_return =
            control_target >= 0x2b2f96u && control_target <= 0x2b3146u &&
            ((control_target - 0x2b2f96u) % 0x12u) == 0 && op == 0xc6u;

        if (control_target == 0x2b2f44u && op == 0xbdu) {
            env->registry_init_calls++;
            registry_stage = 1;
        } else if (control_from == 0x2b2f52u && op == 0xbdu) {
            registry_stage = 2;
        } else if (control_target == 0x2b2f56u && op == 0xc6u) {
            registry_stage = 3;
        } else if (control_from == 0x2b2f82u && op == 0xbdu) {
            env->registry_init_result_calls++;
            registry_stage = 4;
        } else if (control_target == 0x2b2f86u && op == 0xc6u) {
            env->registry_init_result_returns++;
            registry_stage = 5;
        } else if (entry_call) {
            env->registry_init_entry_calls++;
            registry_stage = 6;
        } else if (entry_return) {
            env->registry_init_entry_returns++;
            registry_stage = 7;
        } else if (control_from == 0x2b3148u && op == 0xbdu) {
            registry_stage = 8;
        } else if (control_target == 0x2b314cu && op == 0xc6u) {
            registry_stage = 9;
        } else if (control_from == 0x2b314cu && op == 0xbdu) {
            registry_stage = 10;
        } else if (control_target == 0x2b3150u && op == 0xc6u) {
            registry_stage = 11;
        } else if (control_from == 0x2b317cu && op == 0xc6u) {
            env->registry_init_returns++;
            registry_stage = 12;
        }
        if (registry_stage) {
            env->registry_init_stage = registry_stage;
            env->registry_init_last_from = control_from;
            env->registry_init_last_target = control_target;
            env->registry_init_last_sp = sp;
            env->registry_init_last_fp = fp;
            env->registry_init_last_r0 = env->gpr[0] & MASK16;
            env->registry_init_last_r1 = env->gpr[1] & MASK16;
        }
    }

    /* The third fixed registry record currently enters the relocated
     * 5C:BF4E builder but does not return.  Its twelve direct call sites are
     * source-proven and fixed, so a compact call/return milestone replaces
     * megabytes of transient control logging. */
    {
        static const uint32_t child_calls[] = {
            0x5cbfc4u, 0x5cc00au, 0x5cc078u, 0x5cc0a2u,
            0x5cc11au, 0x5cc18au, 0x5cc1c2u, 0x5cc330u,
            0x5cc342u, 0x5cc366u, 0x5cc3bau, 0x5cc422u,
        };
        uint16_t build_stage = 0;
        uint32_t control_from = from & MASK24;
        uint32_t control_target = env->pc & MASK24;
        unsigned child;

        if (control_target == 0x5cbf4eu && op == 0xbdu) {
            env->file_entry_build_calls++;
            env->file_entry_build_record_hi = env->gpr[0] & MASK16;
            env->file_entry_build_record_lo = env->gpr[1] & MASK16;
            build_stage = 1;
        }
        for (child = 0; child < ARRAY_SIZE(child_calls); child++) {
            if (control_from == child_calls[child] && op == 0xbdu) {
                env->file_entry_build_child_calls++;
                env->file_entry_build_last_child = child + 1;
                build_stage = 2 + child * 2;
                break;
            }
            if (control_target == child_calls[child] + 4u && op == 0xc6u) {
                env->file_entry_build_child_returns++;
                env->file_entry_build_last_child = child + 1;
                build_stage = 3 + child * 2;
                break;
            }
        }
        if (control_from == 0x5cc484u && op == 0xc6u) {
            env->file_entry_build_returns++;
            build_stage = 26;
        }
        if (build_stage) {
            env->file_entry_build_stage = build_stage;
            env->file_entry_build_last_from = control_from;
            env->file_entry_build_last_target = control_target;
            env->file_entry_build_last_sp = sp;
            env->file_entry_build_last_fp = fp;
        }
    }

    /* Persistent, narrow frame probe for the recovered 29:C126 initializer.
     * trace_control_transfer() observes a SCALL after its return frame is
     * pushed and LINK/UNLINK after their architectural effects, allowing the
     * three words to be checked at every relevant boundary. */
    if ((env->pc & MASK24) == 0x29c126u && op == 0xbdu) {
        env->application_init_frame_calls++;
        env->application_init_frame_caller = from & MASK24;
        env->application_init_frame_entry_sp = env->gpr[DMCU_SP] & MASK16;
        env->application_init_frame_entry_fp = env->gpr[DMCU_FP] & MASK16;
        env->application_init_frame_watch_active = false;
    }
    if ((from & MASK24) == 0x29c126u && word == 0x2e05u) {
        uint16_t base = env->gpr[DMCU_FP] & MASK16;

        env->application_init_frame_watch_active = true;
        env->application_init_frame_base = base;
        env->application_init_frame_initial[0] = internal_data_read(base, 16);
        env->application_init_frame_initial[1] =
            internal_data_read((base + 2u) & MASK16, 16);
        env->application_init_frame_initial[2] =
            internal_data_read((base + 4u) & MASK16, 16);
    }
    if ((env->pc & MASK24) == 0x25206eu && op == 0xbdu &&
        (from & MASK24) >= 0x29c126u &&
        (from & MASK24) < 0x29c3c0u) {
        env->application_init_frame_child_calls++;
        env->application_init_frame_child_last_from = from & MASK24;
        env->application_init_frame_child_call_sp =
            env->gpr[DMCU_SP] & MASK16;
        env->application_init_frame_child_call_fp =
            env->gpr[DMCU_FP] & MASK16;
    }
    if ((env->pc & MASK24) >= 0x29c126u &&
        (env->pc & MASK24) < 0x29c3c0u &&
        (from & MASK24) == 0x252476u && op == 0xc6u) {
        uint16_t base = env->application_init_frame_base & MASK16;

        env->application_init_frame_child_returns++;
        env->application_init_frame_child_return_sp =
            env->gpr[DMCU_SP] & MASK16;
        env->application_init_frame_child_return_fp =
            env->gpr[DMCU_FP] & MASK16;
        env->application_init_frame_child_return_words[0] =
            internal_data_read(base, 16);
        env->application_init_frame_child_return_words[1] =
            internal_data_read((base + 2u) & MASK16, 16);
        env->application_init_frame_child_return_words[2] =
            internal_data_read((base + 4u) & MASK16, 16);
    }
    if ((from & MASK24) == 0x29c3bcu && word == 0x2f00u) {
        uint16_t base = env->application_init_frame_base & MASK16;

        env->application_init_frame_unlinks++;
        env->application_init_frame_unlink_words[0] =
            internal_data_read(base, 16);
        env->application_init_frame_unlink_words[1] =
            internal_data_read((base + 2u) & MASK16, 16);
        env->application_init_frame_unlink_words[2] =
            internal_data_read((base + 4u) & MASK16, 16);
        env->application_init_frame_restored_fp =
            env->gpr[DMCU_FP] & MASK16;
        env->application_init_frame_unlink_sp =
            env->gpr[DMCU_SP] & MASK16;
    }
    if ((from & MASK24) == 0x29c3beu && op == 0xc6u) {
        env->application_init_frame_exits++;
        env->application_init_frame_exit_to = env->pc & MASK24;
        env->application_init_frame_exit_sp = env->gpr[DMCU_SP] & MASK16;
        env->application_init_frame_exit_fp = env->gpr[DMCU_FP] & MASK16;
        env->application_init_frame_watch_active = false;
    }

    /* Read-only provenance for the exact 20:76CA directory-record resolver.
     * Capture the far output/selector arguments, the candidate returned by
     * 2B:8056, the loop back edge, and the final output state.  These narrow
     * checkpoints identify a missing root record versus a later name/attribute
     * rejection without altering the guest's memory or control flow. */
    if ((env->pc & MASK24) == 0x2076cau && op == 0xbdu) {
        env->file_record_resolve_calls++;
        env->file_record_resolve_current_output =
            ((uint32_t)internal_data_read(sp, 16) << 16) |
            internal_data_read((sp + 2u) & MASK16, 16);
        env->file_record_resolve_current_selector =
            ((uint32_t)internal_data_read((sp + 4u) & MASK16, 16) << 16) |
            internal_data_read((sp + 6u) & MASK16, 16);
        if (env->file_record_resolve_calls == 1) {
            env->file_record_resolve_caller = from & MASK24;
            env->file_record_resolve_call_sp = sp;
            env->file_record_resolve_output =
                env->file_record_resolve_current_output;
            env->file_record_resolve_selector =
                env->file_record_resolve_current_selector;
        }
    }
    if ((env->pc & MASK24) == 0x207848u &&
        (from & MASK24) == 0x2b827au) {
        uint32_t candidate = ((uint32_t)(env->gpr[0] & MASK16) << 16) |
                             (env->gpr[1] & MASK16);
        uint32_t output = env->file_record_resolve_current_output & MASK24;
        unsigned trace = env->file_record_candidate_returns %
                         DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS;
        unsigned index;

        env->file_record_candidate_returns++;
        env->file_record_candidate_pointer_trace[trace] = candidate & MASK24;
        env->file_record_candidate_call_trace[trace] =
            env->file_record_resolve_calls;
        env->file_record_candidate_output_trace[trace] = output;
        env->file_record_candidate_selector_trace[trace] =
            env->file_record_resolve_current_selector & MASK24;
        env->file_record_candidate_cursor_trace[trace] =
            address_space_lduw_le(&address_space_memory, output + 0x30u,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        env->file_record_candidate_limit_trace[trace] =
            address_space_lduw_le(&address_space_memory, output + 0x32u,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        env->file_record_candidate_span_trace[trace] =
            address_space_lduw_le(&address_space_memory, output + 0x34u,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        env->file_record_candidate_active_trace[trace] =
            address_space_lduw_le(&address_space_memory, output + 0x3cu,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        env->file_record_candidate_compare_valid[trace] = 0;
        for (index = 0; index < 0x40; index++) {
            env->file_record_candidate_data_trace[trace][index] =
                address_space_ldub(&address_space_memory,
                                   ((candidate + index) & MASK24) ^ 1u,
                                   MEMTXATTRS_UNSPECIFIED, NULL);
        }
        if (env->file_record_candidate_returns == 1) {
            env->file_record_candidate_pointer = candidate & MASK24;
            for (index = 0; index < 0x40; index++) {
                env->file_record_candidate_data[index] =
                    address_space_ldub(&address_space_memory,
                                       ((candidate + index) & MASK24) ^ 1u,
                                       MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
    }
    if ((env->pc & MASK24) == 0x2079f6u && op == 0xc6u &&
        env->file_record_candidate_returns != 0) {
        unsigned trace = (env->file_record_candidate_returns - 1u) %
                         DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS;

        env->file_record_candidate_compare_trace[trace] =
            env->gpr[0] & MASK16;
        env->file_record_candidate_compare_valid[trace] = 1;
    }
    if ((env->pc & MASK24) == 0x207836u &&
        (from & MASK24) == 0x207ac6u) {
        env->file_record_resolve_loops++;
    }
    if ((from & MASK24) == 0x207c54u && op == 0xc6u) {
        uint32_t output = env->file_record_resolve_output & MASK24;

        env->file_record_resolve_returns++;
        env->file_record_resolve_result = env->gpr[0] & MASK16;
        env->file_record_resolve_mode =
            address_space_ldub(&address_space_memory, (output + 5u) ^ 1u,
                               MEMTXATTRS_UNSPECIFIED, NULL);
        env->file_record_resolve_cursor =
            address_space_lduw_le(&address_space_memory, output + 0x30u,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        env->file_record_resolve_limit =
            address_space_lduw_le(&address_space_memory, output + 0x32u,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        env->file_record_resolve_span =
            address_space_lduw_le(&address_space_memory, output + 0x34u,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        env->file_record_resolve_active =
            address_space_lduw_le(&address_space_memory, output + 0x3cu,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
    }

    /* 18:F97C constructs the filesystem/root object whose +0x10/+0x12
     * directory bounds remain zero on the failing path.  Keep the bounded
     * entry ABI and return values so the real caller and missing input can be
     * identified without altering the function or injecting filesystem
     * state. */
    if ((env->pc & MASK24) == 0x18f97cu &&
        (env->pc & MASK24) != (sequential & MASK24)) {
        uint32_t trace = env->root_object_init_calls %
                         DMCU_ROOT_OBJECT_INIT_TRACE_SLOTS;
        unsigned index;

        env->root_object_init_from[trace] = from & MASK24;
        env->root_object_init_sp[trace] = sp;
        env->root_object_init_fp[trace] = fp;
        for (index = 0; index < 4; index++) {
            env->root_object_init_gpr[trace][index] =
                env->gpr[index] & MASK16;
        }
        for (index = 0; index < DMCU_ROOT_OBJECT_INIT_STACK_WORDS; index++) {
            env->root_object_init_stack[trace][index] =
                internal_data_read((sp + index * 2u) & MASK16, 16);
        }
        env->root_object_init_calls++;
    }
    if ((from & MASK24) == 0x18fff8u && op == 0xc6u) {
        uint32_t trace = env->root_object_init_returns %
                         DMCU_ROOT_OBJECT_INIT_TRACE_SLOTS;

        env->root_object_init_result[trace][0] = env->gpr[0] & MASK16;
        env->root_object_init_result[trace][1] = env->gpr[1] & MASK16;
        env->root_object_init_returns++;
    }
    if ((env->pc & MASK24) == 0x18ff40u &&
        ((from & MASK24) == 0x18fe9cu ||
         (from & MASK24) == 0x18feb6u ||
         (from & MASK24) == 0x18fed0u ||
         (from & MASK24) == 0x18feecu ||
         (from & MASK24) == 0x18ff08u ||
         (from & MASK24) == 0x18ff22u ||
         (from & MASK24) == 0x18ff28u)) {
        unsigned index;

        env->root_object_failures++;
        if (env->root_object_failures == 1) {
            env->root_object_fail_from = from & MASK24;
            env->root_object_fail_sp = sp;
            env->root_object_fail_fp = fp;
            for (index = 0; index < DMCU_ROOT_OBJECT_FAIL_GPRS; index++) {
                env->root_object_fail_gpr[index] =
                    env->gpr[index] & MASK16;
            }
            for (index = 0; index < DMCU_ROOT_OBJECT_FAIL_LOCALS; index++) {
                env->root_object_fail_locals[index] =
                    internal_data_read(
                        (fp - 18u + index * 2u) & MASK16, 16);
            }
            for (index = 0; index < DMCU_ROOT_OBJECT_FAIL_WORDS; index++) {
                env->root_object_fail_words[index] =
                    address_space_lduw_le(
                        &address_space_memory, 0x00512878u + index * 2u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
    }

    /* The application calls the exact 4A:78AA overlay at runtime 2D:78AA to
     * derive the logical base of its NAND resource volume.  Retain the first
     * call arguments and the first published result together with every
     * operand as it existed at that instant.  In particular, do not infer
     * these inputs from a later RAM snapshot: the FTL keeps updating several
     * of the counters after initialization. */
    if ((env->pc & MASK24) == 0x2d78aau &&
        (env->pc & MASK24) != (sequential & MASK24)) {
        env->resource_base_init_calls++;
        if (env->resource_base_init_calls == 1) {
            env->resource_base_init_caller = from & MASK24;
            env->resource_base_init_call_sp = sp;
            env->resource_base_init_arg_hi = internal_data_read(sp, 16);
            env->resource_base_init_arg_lo =
                internal_data_read((sp + 2u) & MASK16, 16);
        }
    }
    if ((from & MASK24) == 0x2d7996u) {
        env->resource_base_init_writes++;
        if (env->resource_base_init_writes == 1) {
            static const uint16_t input_address[
                DMCU_RESOURCE_BASE_COUNT_INPUTS] = {
                0x04ee, 0x04f0, 0x04f2, 0x04f4,
                0x04f6, 0x04f8, 0x04fa,
            };
            unsigned index;

            env->resource_base_init_write_pc = from & MASK24;
            env->resource_base_init_write_sp = sp;
            env->resource_base_init_write_fp = fp;
            env->resource_base_init_capacity =
                internal_data_read((fp - 10u) & MASK16, 16);
            env->resource_base_init_units_per_block =
                internal_data_read((fp - 8u) & MASK16, 16);
            env->resource_base_init_reserved_blocks =
                internal_data_read((fp - 6u) & MASK16, 16);
            env->resource_base_init_result =
                address_space_lduw_le(&address_space_memory, 0x00004a36u,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->resource_base_init_block_bytes_hi =
                address_space_lduw_le(&address_space_memory, 0x00004b08u,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->resource_base_init_block_bytes_lo =
                address_space_lduw_le(&address_space_memory, 0x00004b0au,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            for (index = 0; index < DMCU_RESOURCE_BASE_COUNT_INPUTS;
                 index++) {
                env->resource_base_init_count_values[index] =
                    address_space_lduw_le(&address_space_memory,
                                          input_address[index],
                                          MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
    }

    /*
     * The direct generic-menu probe eventually enters the complete flat
     * 33:6030 routine even though the PRG contains no direct SCALL xref to
     * that address.  Record the transferring instruction and both sides of
     * its stack before changing any reconstruction code.  This is bounded,
     * read-only diagnostics: it neither supplies a return frame nor changes
     * the callback target.
     */
    if ((env->pc & MASK24) == 0x336030u &&
        (env->pc & MASK24) != (sequential & MASK24) &&
        flat_menu_entry_logs < 8) {
        unsigned index;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU flat menu entry #%u %02x:%04x>%02x:%04x "
            "word=%04x sequential=%02x:%04x "
            "sp-before=%04x sp-after=%04x fp-before=%04x fp-after=%04x "
            "r=%04x,%04x,%04x,%04x stack-before=",
            flat_menu_entry_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from),
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc), word,
            dmcu_code_segment(sequential), dmcu_code_pc(sequential),
            sp, env->gpr[DMCU_SP] & MASK16, fp,
            env->gpr[DMCU_FP] & MASK16,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16);
        for (index = 0; index < 12; index++) {
            qemu_log_mask(LOG_UNIMP, "%s%04x", index ? "," : "",
                          internal_data_read((sp + index * 2) & MASK16, 16));
        }
        qemu_log_mask(LOG_UNIMP, " stack-after=");
        for (index = 0; index < 12; index++) {
            qemu_log_mask(
                LOG_UNIMP, "%s%04x", index ? "," : "",
                internal_data_read(
                    ((env->gpr[DMCU_SP] & MASK16) + index * 2) & MASK16,
                    16));
        }
        qemu_log_mask(LOG_UNIMP, "\n");
        flat_menu_entry_logs++;
    }
    if ((from & MASK24) == 0x336daeu &&
        (env->pc & MASK24) != (sequential & MASK24) &&
        flat_menu_exit_logs < 8) {
        unsigned index;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU flat menu exit #%u %02x:%04x>%02x:%04x "
            "word=%04x sp-before=%04x sp-after=%04x "
            "fp-before=%04x fp-after=%04x stack-before=",
            flat_menu_exit_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from),
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc), word,
            sp, env->gpr[DMCU_SP] & MASK16, fp,
            env->gpr[DMCU_FP] & MASK16);
        for (index = 0; index < 12; index++) {
            qemu_log_mask(LOG_UNIMP, "%s%04x", index ? "," : "",
                          internal_data_read((sp + index * 2) & MASK16, 16));
        }
        qemu_log_mask(LOG_UNIMP, "\n");
        flat_menu_exit_logs++;
    }

    /* Once the application main loop observes a pending foreground state,
     * follow only its compact 22:5240..53F4 decision path.  The foreground
     * has already stored 0x00FE in 51:2AAA at this point; this trace tells us
     * whether the installed words, comparison flags, or conditional branch
     * diverge from the exact PRG implementation without changing guest state.
     */
    if ((from & MASK24) == 0x22523cu &&
        (env->pc & MASK24) == 0x225240u) {
        application_state_control_trace_active = true;
        application_state_control_logs = 0;
    }
    if (application_state_control_trace_active &&
        ((((from & MASK24) >= 0x22523cu &&
           (from & MASK24) <= 0x2253f4u) ||
          ((env->pc & MASK24) >= 0x225240u &&
           (env->pc & MASK24) <= 0x2253f4u)) ||
         call_or_return) &&
        application_state_control_logs < 256) {
        uint16_t application_state = address_space_lduw_le(
            &address_space_memory, 0x00512aaau,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t application_pending = address_space_lduw_le(
            &address_space_memory, 0x00512abau,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t application_stage = address_space_lduw_le(
            &address_space_memory, 0x00512ac0u,
            MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application state control #%u from=%02x:%04x "
            "word=%04x to=%02x:%04x sequential=%02x:%04x "
            "r0=%04x r1=%04x psw=%04x sp=%04x fp=%04x "
            "2aaa=%04x 2aba=%04x 2ac0=%04x\n",
            application_state_control_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(sequential), dmcu_code_pc(sequential),
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->psw & MASK16, sp, fp,
            application_state, application_pending, application_stage);
        application_state_control_logs++;
    }
    if (application_state_control_trace_active &&
        ((env->pc & MASK24) == 0x225226u ||
         (env->pc & MASK24) == 0x2253f4u ||
         (env->pc & MASK24) == 0x225654u ||
         application_state_control_logs >= 256)) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application state control end logs=%u at=%02x:%04x\n",
            application_state_control_logs,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc));
        application_state_control_trace_active = false;
    }

    if ((from & MASK24) == 0x3286b4u &&
        wide_from_int16_path_logs < 64) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU wide-from-int16 first word #%u word=%04x "
            "next=%02x:%04x sp=%04x fp=%04x r0=%04x r1=%04x\n",
            wide_from_int16_path_logs + 1, word,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc), sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16);
        wide_from_int16_path_logs++;
    }

    if (((from & MASK24) == 0x328708u ||
         (from & MASK24) == 0x328714u) &&
        wide_from_int16_path_logs < 64) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU wide-from-int16 exit #%u from=%02x:%04x word=%04x "
            "to=%02x:%04x sp=%04x fp=%04x\n",
            wide_from_int16_path_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc), sp, fp);
        wide_from_int16_path_logs++;
    }

    if (!post_wide_control_trace_done &&
        ((from & MASK24) == 0x328708u ||
         (from & MASK24) == 0x328714u)) {
        post_wide_control_trace_active = true;
        post_wide_instruction_steps = 0;
        post_wide_control_logs = 0;
    }

    if (post_wide_control_trace_active) {
        post_wide_instruction_steps++;
        if ((call_or_return || env->pc != sequential) &&
            post_wide_control_logs < 256) {
            qemu_log_mask(
                LOG_UNIMP,
                "DMCU post-wide control #%u step=%u from=%02x:%04x "
                "word=%04x to=%02x:%04x sequential=%02x:%04x "
                "sp=%04x fp=%04x\n",
                post_wide_control_logs + 1, post_wide_instruction_steps,
                dmcu_code_segment(from), dmcu_code_pc(from), word,
                dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                dmcu_code_segment(sequential), dmcu_code_pc(sequential),
                sp, fp);
            post_wide_control_logs++;
        }
        if (post_wide_instruction_steps >= 20000 ||
            post_wide_control_logs >= 256) {
            qemu_log_mask(
                LOG_UNIMP,
                "DMCU post-wide control end steps=%u controls=%u "
                "at=%02x:%04x\n",
                post_wide_instruction_steps, post_wide_control_logs,
                dmcu_code_segment(env->pc), dmcu_code_pc(env->pc));
            post_wide_control_trace_active = false;
            post_wide_control_trace_done = true;
        }
    }

    if ((env->pc & MASK24) >= 0x331000u &&
        (env->pc & MASK24) < 0x33249au &&
        (from & 0xff0000u) != 0x330000u &&
        segment33_low_path_logs < 128) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU segment-33 low entry #%u from=%02x:%04x word=%04x "
            "to=%02x:%04x sequential=%02x:%04x sp=%04x fp=%04x\n",
            segment33_low_path_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            dmcu_code_segment(sequential), dmcu_code_pc(sequential), sp, fp);
        segment33_low_path_logs++;
    }

    if ((env->pc & MASK24) == 0x33249au &&
        uint32_modulo_wrapper_path_logs < 64) {
        unsigned index;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU uint32 modulo wrapper entry #%u from=%02x:%04x "
            "word=%04x sequential=%02x:%04x sp=%04x fp=%04x stack=",
            uint32_modulo_wrapper_path_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            dmcu_code_segment(sequential), dmcu_code_pc(sequential), sp, fp);
        for (index = 0; index < 12; index++) {
            qemu_log_mask(
                LOG_UNIMP, "%s%04x", index ? "," : "",
                internal_data_read((sp + index * 2u) & MASK16, 16));
        }
        qemu_log_mask(LOG_UNIMP, "\n");
        uint32_modulo_wrapper_path_logs++;
    }

    if ((env->pc & MASK24) == 0x3324eau &&
        uint32_divide_wrapper_path_logs < 64) {
        unsigned index;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU uint32 divide wrapper entry #%u from=%02x:%04x "
            "word=%04x sequential=%02x:%04x sp=%04x fp=%04x stack=",
            uint32_divide_wrapper_path_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from), word,
            dmcu_code_segment(sequential), dmcu_code_pc(sequential), sp, fp);
        for (index = 0; index < 12; index++) {
            qemu_log_mask(
                LOG_UNIMP, "%s%04x", index ? "," : "",
                internal_data_read((sp + index * 2u) & MASK16, 16));
        }
        qemu_log_mask(LOG_UNIMP, "\n");
        uint32_divide_wrapper_path_logs++;
    }

    if ((env->pc & MASK24) == 0x300000u) {
        /* The observed entry is a synthetic far call: 33:2510 RETS pops
         * 30:0000 from [sp..sp+3], leaving the callback's return frame at
         * sp+4. */
        menu_builder_return_watch_base = (sp + 4u) & MASK16;
        menu_builder_return_watch_active = true;
        menu_builder_return_watch_writes = 0;
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu builder return watch entry #%u from=%02x:%04x "
            "word=%04x sp-before=%04x watch=%04x values=%04x,%04x "
            "fp=%04x\n",
            ++menu_builder_return_watch_entries,
            dmcu_code_segment(from), dmcu_code_pc(from), word, sp,
            menu_builder_return_watch_base,
            internal_data_read(menu_builder_return_watch_base, 16),
            internal_data_read(
                (menu_builder_return_watch_base + 2u) & MASK16, 16),
            fp);
    }
    if ((from & MASK24) == 0x30130cu &&
        menu_builder_return_watch_active) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu builder return watch exit to=%02x:%04x "
            "sp-before=%04x watch=%04x values=%04x,%04x fp=%04x "
            "writes=%u\n",
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc), sp,
            menu_builder_return_watch_base,
            internal_data_read(menu_builder_return_watch_base, 16),
            internal_data_read(
                (menu_builder_return_watch_base + 2u) & MASK16, 16),
            fp, menu_builder_return_watch_writes);
        menu_builder_return_watch_active = false;
    }

    if ((env->pc & MASK24) == 0x3007beu) {
        menu_position_return_watch_base = (sp - 4u) & MASK16;
        menu_position_return_watch_active = true;
        menu_position_return_watch_writes = 0;
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu position return watch entry #%u from=%02x:%04x "
            "word=%04x sp-before=%04x watch=%04x values=%04x,%04x "
            "fp=%04x\n",
            ++menu_position_return_watch_entries,
            dmcu_code_segment(from), dmcu_code_pc(from), word, sp,
            menu_position_return_watch_base,
            internal_data_read(menu_position_return_watch_base, 16),
            internal_data_read(
                (menu_position_return_watch_base + 2u) & MASK16, 16),
            fp);
    }
    if ((from & MASK24) == 0x3008d6u &&
        menu_position_return_watch_active) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu position return watch exit to=%02x:%04x "
            "sp-before=%04x watch=%04x values=%04x,%04x fp=%04x "
            "writes=%u\n",
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc), sp,
            menu_position_return_watch_base,
            internal_data_read(menu_position_return_watch_base, 16),
            internal_data_read(
                (menu_position_return_watch_base + 2u) & MASK16, 16),
            fp, menu_position_return_watch_writes);
        menu_position_return_watch_active = false;
    }

    /* 11:1886 is the compiler's synthetic far-call through the callback
     * stored at object+0x22.  A corrupt target here is only the final symptom
     * of the current foreground stack descent, so retain a bounded sequence
     * of successful entries and returns as well as the eventual bad target.
     * The active object is an internal-RAM far pointer in the observed path;
     * keep its original two words in the log instead of assuming that fact
     * while deciding whether it is still valid. */
    if (((from & MASK24) == 0x111886u ||
         (from & MASK24) == 0x2e1886u) &&
        object_callback_entries < 64) {
        uint16_t object_hi = internal_data_read((fp + 6) & MASK16, 16);
        uint16_t object_lo = internal_data_read((fp + 8) & MASK16, 16);
        uint16_t callback_hi = 0xffff;
        uint16_t callback_lo = 0xffff;

        if (object_hi == 0) {
            callback_hi = internal_data_read((object_lo + 0x22) & MASK16, 16);
            callback_lo = internal_data_read((object_lo + 0x24) & MASK16, 16);
        }
        qemu_log_mask(LOG_UNIMP,
                      "DMCU object callback entry #%u %02x:%04x "
                      "sp=%04x fp=%04x object=%04x:%04x "
                      "field=%04x:%04x args=%04x,%04x,%04x\n",
                      object_callback_entries + 1,
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      sp, fp, object_hi, object_lo,
                      callback_hi, callback_lo,
                      internal_data_read(sp, 16),
                      internal_data_read((sp + 2) & MASK16, 16),
                      internal_data_read((sp + 4) & MASK16, 16));
        object_callback_entries++;
    }
    if ((env->pc & MASK24) == 0x111888u &&
        object_callback_returns < 64) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU object callback return #%u from %02x:%04x "
                      "sp-before=%04x sp-after=%04x fp=%04x\n",
                      object_callback_returns + 1,
                      dmcu_code_segment(from), dmcu_code_pc(from),
                      sp, env->gpr[DMCU_SP] & MASK16, fp);
        object_callback_returns++;
    }

    if ((env->pc & MASK24) == 0x32f786u &&
        (env->gpr[0] & MASK16) == 0x0051u &&
        (env->gpr[1] & MASK16) == 0x2770u) {
        unsigned index;

        env->indirect_object_copy_calls++;
        env->indirect_object_copy_from = from & MASK24;
        env->indirect_object_copy_sp = sp;
        env->indirect_object_copy_fp = fp;
        for (index = 0; index < ARRAY_SIZE(env->indirect_object_copy_gpr);
             index++) {
            env->indirect_object_copy_gpr[index] = env->gpr[index] & MASK16;
        }
    }

    /* 32:945C is the recovered far-string wrapper and 2E:4572 is the exact
     * general far-memory copy implementation it delegates to.  The first
     * observed menu failure is a copy into 27:E528, so retain the complete
     * argument frame at the wrapper, its pointer-normalisation helper, the
     * copy entry/recursive entry, and the final return.  This is diagnostic
     * only; it deliberately does not alter a pointer or suppress the write. */
    if (((env->pc & MASK24) == 0x32945cu ||
         (env->pc & MASK24) == 0x31aed0u ||
         (env->pc & MASK24) == 0x2e4572u ||
         (from & MASK24) == 0x2e468cu ||
         (from & MASK24) == 0x2e46f4u) &&
        far_memory_copy_call_logs < 96) {
        unsigned index;

        qemu_log_mask(LOG_UNIMP,
                      "DMCU far memory path #%u %02x:%04x>%02x:%04x "
                      "sp=%04x fp=%04x DS0=%03x DS1=%03x "
                      "r=%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x "
                      "stack=",
                      far_memory_copy_call_logs + 1,
                      dmcu_code_segment(from), dmcu_code_pc(from),
                      dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                      sp, fp,
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff,
                      env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                      env->gpr[2] & MASK16, env->gpr[3] & MASK16,
                      env->gpr[4] & MASK16, env->gpr[5] & MASK16,
                      env->gpr[6] & MASK16, env->gpr[7] & MASK16,
                      env->gpr[8] & MASK16, env->gpr[9] & MASK16);
        for (index = 0; index < 12; index++) {
            qemu_log_mask(LOG_UNIMP, "%s%04x", index ? "," : "",
                          internal_data_read((sp + index * 2) & MASK16, 16));
        }
        qemu_log_mask(LOG_UNIMP, "\n");
        far_memory_copy_call_logs++;
    }

    /* 2E:DB9C is the exact resident event dispatcher recovered from
     * NP560.PRG 4B:DB9C.  Its two RETS instructions perform a synthetic far
     * call through the callback stored at object+4.  Preserve the complete
     * pre-RETS frame and the source object so a stop in unavailable SoC ROM
     * can be traced back to data, rather than inferred from the final PC. */
    if (((from & MASK24) == 0x2edc9cu ||
         (from & MASK24) == 0x2edcecu) &&
        (env->pc & MASK24) != (sequential & MASK24)) {
        unsigned callback_slot = env->indirect_callback_calls %
                                 DMCU_INDIRECT_CALLBACK_TRACE_SLOTS;
        uint16_t object_hi = internal_data_read((fp + 6) & MASK16, 16);
        uint16_t object_lo = internal_data_read((fp + 8) & MASK16, 16);
        unsigned index;

        env->indirect_callback_from[callback_slot] = from & MASK24;
        env->indirect_callback_target[callback_slot] = env->pc & MASK24;
        env->indirect_callback_sp[callback_slot] = sp;
        env->indirect_callback_fp[callback_slot] = fp;
        env->indirect_callback_object_hi[callback_slot] = object_hi;
        env->indirect_callback_object_lo[callback_slot] = object_lo;
        for (index = 0; index < DMCU_INDIRECT_CALLBACK_STACK_WORDS;
             index++) {
            env->indirect_callback_stack[callback_slot][index] =
                internal_data_read((sp + index * 2) & MASK16, 16);
        }
        if ((object_hi & 0xff00) == 0) {
            uint32_t object_physical = ((uint32_t)object_hi << 16) |
                                       object_lo;

            for (index = 0; index < DMCU_INDIRECT_CALLBACK_OBJECT_WORDS;
                 index++) {
                env->indirect_callback_object[callback_slot][index] =
                    address_space_lduw_le(
                        &address_space_memory, object_physical + index * 2,
                        MEMTXATTRS_UNSPECIFIED, NULL);
            }
            env->indirect_callback_field_hi[callback_slot] =
                address_space_lduw_le(
                    &address_space_memory, object_physical + 4,
                    MEMTXATTRS_UNSPECIFIED, NULL);
            env->indirect_callback_field_lo[callback_slot] =
                address_space_lduw_le(
                    &address_space_memory, object_physical + 6,
                    MEMTXATTRS_UNSPECIFIED, NULL);
        } else {
            env->indirect_callback_field_hi[callback_slot] = 0xffff;
            env->indirect_callback_field_lo[callback_slot] = 0xffff;
        }
        env->indirect_callback_calls++;
    }

    /* Every DMCU instruction word is two-byte aligned.  A computed RET/RETS
     * can still land at an odd address inside the nominal program window
     * when a callback/table entry is byte-swapped or otherwise corrupted.
     * Treat that as invalid control at the transfer itself; waiting for the
     * eventual unsupported word loses the source RET beneath timer traffic. */
    if (call_or_return &&
        (env->pc & MASK24) != (sequential & MASK24) &&
        (from & MASK24) < DMCU_PROGRAM_BASE + DMCU_PROGRAM_SIZE &&
        (((env->pc & MASK24) >=
          DMCU_PROGRAM_BASE + DMCU_PROGRAM_SIZE) ||
         ((env->pc & 1u) != 0)) &&
        !env->invalid_control_valid) {
        env->invalid_control_valid = true;
        env->invalid_control_from = from & MASK24;
        env->invalid_control_to = env->pc & MASK24;
        env->invalid_control_word = word;
        env->invalid_control_sp = sp;
        env->invalid_control_fp = fp;
        env->invalid_control_in_interrupt = env->in_interrupt;
        /* Keep the immediately preceding call/return chain intact.  Once an
         * invalid target executes, timer interrupts otherwise replace the
         * circular trace with secondary fallout at 00:0000. */
        freeze_after = true;
    }

    if ((env->pc & MASK24) == 0x1cf28au &&
        !env->event_frame_watch_active) {
        env->event_frame_watch_active = true;
        env->event_frame_base = env->gpr[DMCU_SP] & MASK16;
    }
    if ((from & MASK24) == 0x2427ccu &&
        (env->pc & MASK24) == 0x1c2a14u &&
        storage_ftl_classify_returns < 64) {
        uint16_t caller_fp = env->gpr[DMCU_FP] & MASK16;
        uint16_t block = internal_data_read((caller_fp - 0x000a) & MASK16,
                                            16);
        uint16_t identifier = internal_data_read(
            (caller_fp - 0x0010) & MASK16, 16);

        if (block == 0x0801u || block == 0x0c01u || block < 4u) {
            qemu_log_mask(LOG_UNIMP,
                          "DMCU FTL classify block=%04x id=%04x "
                          "status=%04x fp=%04x map-block=%04x\n",
                          block, identifier, env->gpr[0] & MASK16,
                          caller_fp, internal_data_read(0x04e4, 16));
            storage_ftl_classify_returns++;
        }
    }
    if ((from & MASK24) == 0x2b4e3cu &&
        (env->pc & MASK24) == 0x24be78u &&
        storage_factory_ecc_returns < 12) {
        uint16_t caller_fp = env->gpr[DMCU_FP] & MASK16;

        qemu_log_mask(LOG_UNIMP,
                      "DMCU factory ECC candidate=%04x result=%04x "
                      "engine=%04x:%04x descriptor="
                      "%04x,%04x,%04x,%04x\n",
                      internal_data_read((caller_fp - 0x0002) & MASK16, 16),
                      env->gpr[0] & MASK16,
                      address_space_lduw_le(&address_space_memory, 0x00f20c,
                                             MEMTXATTRS_UNSPECIFIED, NULL),
                      address_space_lduw_le(&address_space_memory, 0x00f20a,
                                             MEMTXATTRS_UNSPECIFIED, NULL),
                      address_space_lduw_le(&address_space_memory,
                                             0x511200, MEMTXATTRS_UNSPECIFIED,
                                             NULL),
                      address_space_lduw_le(&address_space_memory,
                                             0x511202, MEMTXATTRS_UNSPECIFIED,
                                             NULL),
                      address_space_lduw_le(&address_space_memory,
                                             0x511204, MEMTXATTRS_UNSPECIFIED,
                                             NULL),
                      address_space_lduw_le(&address_space_memory,
                                             0x511206, MEMTXATTRS_UNSPECIFIED,
                                             NULL));
        storage_factory_ecc_returns++;
    }
    if ((from & MASK24) == 0x24c19eu &&
        (env->pc & MASK24) == 0x31f6c4u) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU factory metadata return result=%04x "
                      "record=%04x,%04x,%04x,%04x fields=%04x,%04x\n",
                      env->gpr[0] & MASK16,
                      address_space_lduw_le(&address_space_memory,
                                             0x511000, MEMTXATTRS_UNSPECIFIED,
                                             NULL),
                      address_space_lduw_le(&address_space_memory,
                                             0x511002, MEMTXATTRS_UNSPECIFIED,
                                             NULL),
                      address_space_lduw_le(&address_space_memory,
                                             0x511006, MEMTXATTRS_UNSPECIFIED,
                                             NULL),
                      address_space_lduw_le(&address_space_memory,
                                             0x511016, MEMTXATTRS_UNSPECIFIED,
                                             NULL),
                      address_space_lduw_le(&address_space_memory,
                                             0x511018, MEMTXATTRS_UNSPECIFIED,
                                             NULL),
                      internal_data_read(0x04e4, 16));
    }
    if ((from & MASK24) == 0x31f6fcu &&
        (env->pc & MASK24) == 0x30a412u) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU low-level storage bootstrap result=%04x "
                      "map-block=%04x entry0=%04x:%04x\n",
                      env->gpr[0] & MASK16,
                      internal_data_read(0x04e4, 16),
                      internal_data_read(0x0286, 16),
                      internal_data_read(0x0288, 16));
    }
    if ((from & MASK24) == 0x28cf3au &&
        (env->pc & MASK24) == 0x2d2a2cu &&
        storage_ftl_fast_classify_returns < 32) {
        uint16_t caller_fp = env->gpr[DMCU_FP] & MASK16;
        uint16_t block = internal_data_read((caller_fp - 0x0002) & MASK16,
                                            16);

        if (block == 0x0801u || block == 0x0c01u || block < 4u) {
            qemu_log_mask(LOG_UNIMP,
                          "DMCU FTL fast-classify block=%04x status=%04x "
                          "fp=%04x map-block=%04x\n",
                          block, env->gpr[0] & MASK16, caller_fp,
                          internal_data_read(0x04e4, 16));
            storage_ftl_fast_classify_returns++;
        }
    }
    if ((from & MASK24) == 0x1c30aeu &&
        (env->pc & MASK24) == 0x2781fau) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU FTL bootstrap return result=%04x map-block=%04x "
                      "range=%04x..%04x entry0=%04x:%04x free=%04x\n",
                      env->gpr[0] & MASK16,
                      internal_data_read(0x04e4, 16),
                      internal_data_read(0x027e, 16),
                      internal_data_read(0x0280, 16),
                      internal_data_read(0x0286, 16),
                      internal_data_read(0x0288, 16),
                      internal_data_read(0x04ee, 16));
    }
    /* Only sample a real direct call into 2E:4572.  A RETI may legitimately
     * resume at that address while executing the caller's next instruction;
     * treating every transition to the entry PC as a fresh call reads the
     * interrupted frame as arguments and creates a false FAR_COPY_BAD. */
    if ((env->pc & MASK24) == 0x2e4572u &&
        (word & 0xff00u) == 0xbd00u &&
        !env->far_copy_bad_valid) {
        uint32_t length_hi = internal_data_read((sp + 8) & MASK16, 16);
        uint32_t length_lo = internal_data_read((sp + 10) & MASK16, 16);

        if (length_hi || length_lo > 0x1000u) {
            unsigned argument;

            env->far_copy_bad_valid = true;
            env->far_copy_bad_from = from & MASK24;
            env->far_copy_bad_sp = sp;
            env->far_copy_bad_fp = fp;
            for (argument = 0; argument < 6; argument++) {
                env->far_copy_bad_args[argument] =
                    internal_data_read((sp + argument * 2) & MASK16, 16);
            }
        }
    }

    if ((env->pc & MASK24) == 0x31f282u) {
        const unsigned modal_entry = DMCU_APPLICATION_TRACE_ENTRIES - 2;
        unsigned argument;

        env->application_trace_calls[modal_entry]++;
        if (env->application_trace_calls[modal_entry] == 1) {
            env->application_trace_from[modal_entry] = from & MASK24;
            env->application_trace_sp[modal_entry] = sp;
            env->application_trace_r0[modal_entry] = env->gpr[0] & MASK16;
            env->application_trace_r1[modal_entry] = env->gpr[1] & MASK16;
            env->application_trace_r2[modal_entry] = env->gpr[2] & MASK16;
            for (argument = 0; argument < 4; argument++) {
                env->application_trace_args[modal_entry][argument] =
                    internal_data_read((sp + argument * 2) & MASK16, 16);
            }
        }
    }
    if ((env->pc & MASK24) == 0x31f2aeu &&
        (env->pc & MASK24) != (sequential & MASK24)) {
        const unsigned modal_head = DMCU_APPLICATION_TRACE_ENTRIES - 1;
        unsigned argument;

        env->application_trace_calls[modal_head]++;
        if (env->application_trace_calls[modal_head] == 1) {
            env->application_trace_from[modal_head] = from & MASK24;
            env->application_trace_sp[modal_head] = sp;
            env->application_trace_r0[modal_head] = env->gpr[0] & MASK16;
            env->application_trace_r1[modal_head] = env->gpr[1] & MASK16;
            env->application_trace_r2[modal_head] = env->gpr[2] & MASK16;
            for (argument = 0; argument < 4; argument++) {
                env->application_trace_args[modal_head][argument] =
                    internal_data_read((sp + argument * 2) & MASK16, 16);
            }
        }
    }
    /* The exact 32:DB08 overlay can also be reached by sequentially falling
     * out of an older flat body.  Capture the stack before its LINK executes,
     * and retain the control history which led to that bad boundary. */
    if ((from & MASK24) == 0x32db08u) {
        unsigned resource_slot = env->resource_open_calls %
                                 DMCU_RESOURCE_OPEN_TRACE_SLOTS;
        unsigned stack_word;

        env->resource_open_trace_from[resource_slot] = from & MASK24;
        env->resource_open_trace_sp[resource_slot] = sp;
        env->resource_open_trace_fp[resource_slot] = fp;
        for (stack_word = 0; stack_word < 8; stack_word++) {
            env->resource_open_trace_args[resource_slot][stack_word] =
                internal_data_read((sp + stack_word * 2) & MASK16, 16);
        }
        env->resource_open_calls++;
        /* The standalone resource diagnostic freezes here so later timer
         * traffic cannot erase its caller.  During the direct-menu stack
         * watch, keep the larger call ring live until the first unwind above
         * the probe's entry frame identifies the actual bad predecessor. */
        if (!env->direct_menu_stack_watch_active) {
            env->control_trace_frozen = true;
        }
    }
    if (!call_or_return ||
        (env->pc & MASK24) == (sequential & MASK24)) {
        return;
    }
    if ((env->pc & MASK24) == 0x18a510u &&
        !env->first_low_sp_valid) {
        unsigned region_slot = env->region_mask_calls %
                               DMCU_REGION_MASK_TRACE_SLOTS;
        unsigned argument;

        env->region_mask_trace_from[region_slot] = from & MASK24;
        env->region_mask_trace_sp[region_slot] = sp;
        env->region_mask_trace_fp[region_slot] = fp;
        for (argument = 0; argument < 6; argument++) {
            env->region_mask_trace_args[region_slot][argument] =
                internal_data_read((sp + argument * 2) & MASK16, 16);
        }
        env->region_mask_calls++;
    }
    if ((from & MASK24) == 0x3009c8u && menu_layout_call_logs < 4) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu layout rectangle #%u sp=%04x fp=%04x "
            "args=%04x,%04x,%04x,%04x,%04x "
            "locals=d8:%04x da:%04x dc:%04x de:%04x e8:%04x "
            "ec:%04x ee:%04x f0:%04x f2:%04x f4:%04x f6:%04x "
            "f8:%04x fa:%04x fc:%04x fe:%04x\n",
            menu_layout_call_logs + 1, sp, fp,
            internal_data_read(sp, 16),
            internal_data_read((sp + 2) & MASK16, 16),
            internal_data_read((sp + 4) & MASK16, 16),
            internal_data_read((sp + 6) & MASK16, 16),
            internal_data_read((sp + 8) & MASK16, 16),
            internal_data_read((fp + 0xffd8u) & MASK16, 16),
            internal_data_read((fp + 0xffdau) & MASK16, 16),
            internal_data_read((fp + 0xffdcu) & MASK16, 16),
            internal_data_read((fp + 0xffdeu) & MASK16, 16),
            internal_data_read((fp + 0xffe8u) & MASK16, 16),
            internal_data_read((fp + 0xffecu) & MASK16, 16),
            internal_data_read((fp + 0xffeeu) & MASK16, 16),
            internal_data_read((fp + 0xfff0u) & MASK16, 16),
            internal_data_read((fp + 0xfff2u) & MASK16, 16),
            internal_data_read((fp + 0xfff4u) & MASK16, 16),
            internal_data_read((fp + 0xfff6u) & MASK16, 16),
            internal_data_read((fp + 0xfff8u) & MASK16, 16),
            internal_data_read((fp + 0xfffau) & MASK16, 16),
            internal_data_read((fp + 0xfffcu) & MASK16, 16),
            internal_data_read((fp + 0xfffeu) & MASK16, 16));
        menu_layout_call_logs++;
    }
    if (((from & MASK24) == 0x2f9070u ||
         (from & MASK24) == 0x30085au ||
         (from & MASK24) == 0x30087cu ||
         (from & MASK24) == 0x2f908au ||
         (from & MASK24) == 0x2f90a8u ||
         (from & MASK24) == 0x3008d6u ||
         (from & MASK24) == 0x2fb9d2u ||
         (from & MASK24) == 0x2f90e8u ||
         (from & MASK24) == 0x29670cu) &&
        menu_position_call_logs < 16) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu position path #%u %02x:%04x>%02x:%04x "
            "sp=%04x fp=%04x r=%04x:%04x:%04x:%04x "
            "stack=%04x,%04x,%04x,%04x,%04x,%04x\n",
            menu_position_call_logs + 1,
            dmcu_code_segment(from), dmcu_code_pc(from),
            dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
            sp, fp,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            internal_data_read(sp, 16),
            internal_data_read((sp + 2) & MASK16, 16),
            internal_data_read((sp + 4) & MASK16, 16),
            internal_data_read((sp + 6) & MASK16, 16),
            internal_data_read((sp + 8) & MASK16, 16),
            internal_data_read((sp + 10) & MASK16, 16));
        menu_position_call_logs++;
    }
    if ((env->pc & MASK24) == 0x507dd8u) {
        env->nand_manager_caller = from & MASK24;
    }
    if (op == 0xbd && (from & MASK24) >= 0x229738u &&
        (from & MASK24) < 0x229c28u) {
        env->application_init_calls++;
        env->application_init_last_from = from & MASK24;
        env->application_init_last_target = env->pc & MASK24;
        env->application_init_last_r0 = env->gpr[0] & MASK16;
        env->application_init_last_r1 = env->gpr[1] & MASK16;
    }
    if (op == 0xbd &&
        (((from & MASK24) >= 0x25cc94u &&
          (from & MASK24) < 0x25d05au) ||
         ((from & MASK24) >= 0x255858u &&
          (from & MASK24) < 0x255c4eu) ||
         ((from & MASK24) >= 0x30a3c2u &&
          (from & MASK24) < 0x30a4aeu) ||
         ((from & MASK24) >= 0x25e324u &&
          (from & MASK24) < 0x25e6e4u) ||
         ((from & MASK24) >= 0x31f670u &&
          (from & MASK24) < 0x31f6feu))) {
        env->resource_init_calls++;
        env->resource_init_last_from = from & MASK24;
        env->resource_init_last_target = env->pc & MASK24;
        env->resource_init_last_r0 = env->gpr[0] & MASK16;
        env->resource_init_last_r1 = env->gpr[1] & MASK16;
    }
    /* Keep the Web diagnostics scoped to the menu stage.  Bootstrap UI
     * glyphs otherwise occupy the same bounded rings and can make a fixed
     * menu path look as though it is still issuing the earlier bad calls. */
    if ((env->pc & MASK24) == 0x2cc9e8u) {
        env->text_trace_count = 0;
        env->glyph_draw_trace_count = 0;
        env->font_blit_trace_count = 0;
        env->font_copy_trace_count = 0;
        env->glyph_draw_active_character = 0;
    }
    for (application = 0;
         application < DMCU_APPLICATION_TRACE_ENTRIES; application++) {
        unsigned argument;

        if ((env->pc & MASK24) != application_targets[application]) {
            continue;
        }
        if ((env->pc & MASK24) == 0x31f2aeu ||
            (env->pc & MASK24) == 0x31f282u) {
            break;
        }
        env->application_trace_calls[application]++;
        env->application_trace_from[application] = from & MASK24;
        env->application_trace_sp[application] = sp;
        env->application_trace_r0[application] = env->gpr[0] & MASK16;
        env->application_trace_r1[application] = env->gpr[1] & MASK16;
        env->application_trace_r2[application] = env->gpr[2] & MASK16;
        if ((env->pc & MASK24) == 0x2d7facu) {
            /* 2D:7FAC is the far-call return from the exact one-byte
             * resource read at logical 10:D072.  Preserve the destination
             * byte in the ordinary R2 trace field before stack cleanup and
             * the following MOVB consume it.  This is read-only diagnostics;
             * no architectural register or guest memory is changed. */
            env->application_trace_r2[application] =
                internal_data_read((fp - 1) & MASK16, 8);
        }
        for (argument = 0; argument < 4; argument++) {
            env->application_trace_args[application][argument] =
                internal_data_read((sp + argument * 2) & MASK16, 16);
        }
        if ((env->pc & MASK24) == 0x1df2ecu) {
            /* 28:8480 enters the resident root controller with RETS as an
             * indirect far call.  At this interception point the target and
             * synthetic return pairs still occupy stack words 0..3, so the
             * ordinary four-word snapshot above records those mechanics
             * instead of the controller's arguments.  Preserve the first
             * two real far pointers in args[] and the third in r0:r1.  This
             * is diagnostic-only state and does not consume or modify the
             * guest stack. */
            for (argument = 0; argument < 4; argument++) {
                env->application_trace_args[application][argument] =
                    internal_data_read((sp + 8u + argument * 2u) & MASK16,
                                       16);
            }
            {
                uint32_t object =
                    ((uint32_t)(env->application_trace_args[application][0] &
                                0xffu) << 16) |
                    env->application_trace_args[application][1];

                /* The remaining trace registers are more useful as a
                 * point-in-time object snapshot than as the two trailing
                 * zero arguments used by this cold-start path. */
                env->application_trace_r0[application] =
                    address_space_lduw_le(&address_space_memory,
                                          (object + 0x08u) & MASK24,
                                          MEMTXATTRS_UNSPECIFIED, NULL);
                env->application_trace_r1[application] =
                    address_space_lduw_le(&address_space_memory,
                                          (object + 0x22u) & MASK24,
                                          MEMTXATTRS_UNSPECIFIED, NULL);
                env->application_trace_r2[application] =
                    address_space_lduw_le(&address_space_memory,
                                          (object + 0x42u) & MASK24,
                                          MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
        if ((env->pc & MASK24) == 0x1df6d8u) {
            uint32_t object =
                ((uint32_t)(internal_data_read((fp - 4u) & MASK16, 16) &
                            0xffu) << 16) |
                internal_data_read((fp - 2u) & MASK16, 16);

            /* Snapshot the loop fields before the event-class branches can
             * change R0/R1.  The controller locals at FP-4:FP-2 hold the
             * object pointer and FP-6 is the one-based item index.  This is
             * read-only diagnostics; execution and guest memory are not
             * modified. */
            env->application_trace_r0[application] =
                address_space_lduw_le(&address_space_memory,
                                      (object + 0x08u) & MASK24,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->application_trace_r1[application] =
                address_space_lduw_le(&address_space_memory,
                                      (object + 0x42u) & MASK24,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->application_trace_r2[application] =
                internal_data_read((fp - 6u) & MASK16, 16);
        }
        if ((env->pc & MASK24) == 0x1df900u) {
            /* Reaching F900 directly from the F8FC ULE means the item loop
             * was not selected.  R0 and R2 still contain index and count;
             * retain PSW in R1 to distinguish bad operands from bad flags or
             * condition evaluation.  Diagnostic only. */
            env->application_trace_r0[application] = env->gpr[0] & MASK16;
            env->application_trace_r1[application] = env->psw & 0x000fu;
            env->application_trace_r2[application] = env->gpr[2] & MASK16;
        }
        if ((env->pc & MASK24) == 0x3133f6u &&
            !env->file_size_record_snapshot_valid) {
            uint32_t record =
                ((uint32_t)internal_data_read((sp + 4) & MASK16, 16) << 16) |
                internal_data_read((sp + 6) & MASK16, 16);
            unsigned index;

            /* 31:33F6 is the return from the directory-record scan.  The
             * caller releases/reuses the temporary record immediately, so a
             * later Web query sees zeroes.  Freeze the first successful
             * record while it is still live.  This is read-only diagnostics:
             * no guest register, memory, or control flow is changed. */
            env->file_size_record_snapshot_valid = true;
            env->file_size_record_snapshot_base = record & MASK24;
            env->file_size_record_snapshot_attr =
                address_space_ldub(&address_space_memory,
                                   ((record + 0x14u) & MASK24) ^ 1u,
                                   MEMTXATTRS_UNSPECIFIED, NULL);
            env->file_size_record_snapshot_length_hi =
                address_space_lduw_le(&address_space_memory,
                                      (record + 0x2cu) & MASK24,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->file_size_record_snapshot_length_lo =
                address_space_lduw_le(&address_space_memory,
                                      (record + 0x2eu) & MASK24,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            for (index = 0; index < 0x40; index++) {
                env->file_size_record_snapshot_data[index] =
                    address_space_ldub(&address_space_memory,
                                       ((record + index) & MASK24) ^ 1u,
                                       MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
        if ((env->pc & MASK24) == 0x03026au &&
            env->application_trace_calls[application] == 2) {
            /* Preserve the complete control-transfer tail which re-enters
             * SYSMAIN.  A second entry from the post-initializer loader tail
             * proves that execution bypassed both its expected return and the
             * 03:0080 scheduler.
             * This is bounded, read-only diagnostics; guest execution keeps
             * running while only the circular control trace is frozen. */
            freeze_after = true;
            qemu_log_mask(
                LOG_UNIMP,
                "DMCU lifecycle trace frozen at SYSMAIN #2 "
                "from=%02x:%04x sp=%04x fp=%04x\n",
                dmcu_code_segment(from), dmcu_code_pc(from), sp, fp);
        }
        if ((env->pc & MASK24) == 0x2d7f80u &&
            env->application_trace_calls[application] == 1) {
            /* 22:515E is a non-returning foreground loop whose only tail is
             * AJMP 22:5226.  Reaching the instruction after its 06:4600
             * wrapper therefore means a nested RETS escaped at least one
             * frame.  Freeze the bounded call/return ring at the first such
             * boundary so later manager I/O cannot overwrite the transfer
             * which entered 06:4608.  This is diagnostic-only state. */
            freeze_after = true;
        }
        if ((env->pc & MASK24) == 0x08441au &&
            rom_argument(env, 5) > 0x0100u) {
            /* Preserve the call chain before an invalid rectangle width can
             * make the exact byte-fill primitive overwrite the guest stack.
             * SCALL has already pushed a two-word far-return frame here, so
             * the caller's fourth argument is callee stack word five. */
            freeze_after = true;
        }
        break;
    }
    if ((env->pc & MASK24) == 0x288482u) {
        /* Preserve the bounded call/return history at the exact continuation
         * of the 28:8480 indirect root-controller call.  The foreground idle
         * loop otherwise overwrites the controller's initial branch path
         * before Web diagnostics can inspect why 10:E4AA was skipped. */
        freeze_after = true;
    }
    if (env->control_trace_frozen) {
        return;
    }
    if (env->control_trace_count) {
        unsigned previous = (env->control_trace_count - 1) %
                            DMCU_CONTROL_TRACE_WORDS;

        if (env->control_trace_from[previous] == (from & MASK24) &&
            env->control_trace_to[previous] == (env->pc & MASK24) &&
            env->control_trace_word[previous] == word) {
            return;
        }
    }
    slot = env->control_trace_count % DMCU_CONTROL_TRACE_WORDS;
    env->control_trace_from[slot] = from & MASK24;
    env->control_trace_to[slot] = env->pc & MASK24;
    env->control_trace_word[slot] = word;
    env->control_trace_sp[slot] = sp;
    env->control_trace_fp[slot] = fp;
    env->control_trace_count++;
    if (freeze_after) {
        env->control_trace_frozen = true;
    }
}

/*
 * Observe SoC ROM calls before SCALL changes R15.  Reconstructed resident
 * functions execute normally, while unavailable functions additionally keep
 * the missing-ROM snapshot below.  Keeping the font counters on this common
 * entry path avoids the false "zero calls" result that occurred once those
 * functions were restored as real guest code.
 */
static void trace_rom_call(CPUDMCUState *env, uint32_t target,
                           uint32_t caller, uint32_t return_pc, bool missing)
{
    static uint32_t font_blit_calls;
    static uint32_t lcd_flush_calls;
    unsigned i;

    if (missing) {
        env->missing_rom_call_valid = true;
        env->missing_rom_calls++;
        env->missing_rom_call_target = target & MASK24;
        env->missing_rom_call_caller = caller & MASK24;
        env->missing_rom_call_return = return_pc & MASK24;
        env->missing_rom_call_sp = env->gpr[DMCU_SP] & MASK16;
        env->missing_rom_call_psw = env->psw & 15;
        env->missing_rom_call_ds0 = env->sfr[DMCU_SFR_DS0] & 0x1ff;
        env->missing_rom_call_ds1 = env->sfr[DMCU_SFR_DS1] & 0x1ff;
        for (i = 0; i < ARRAY_SIZE(env->missing_rom_call_gpr); i++) {
            env->missing_rom_call_gpr[i] = env->gpr[i] & MASK16;
        }
        for (i = 0; i < DMCU_ROM_TRACE_STACK_WORDS; i++) {
            env->missing_rom_call_stack[i] = rom_argument(env, i);
        }
    }

    if (target == dmcu_code_address(0x17, 0x9244)) {
        env->native_font_lookup_calls++;
        env->native_font_lookup_caller = caller & MASK24;
        env->native_font_lookup_x = rom_argument(env, 0) & MASK16;
        env->native_font_lookup_y = rom_argument(env, 1) & MASK16;
        env->native_font_lookup_character = rom_argument(env, 2) & MASK16;
        if (env->native_font_lookup_calls <= 16) {
            qemu_log_mask(LOG_UNIMP,
                          "DMCU resident font lookup call=%u "
                          "character=%04x x=%u y=%u from=%02x:%04x\n",
                          env->native_font_lookup_calls,
                          env->native_font_lookup_character,
                          env->native_font_lookup_x,
                          env->native_font_lookup_y,
                          dmcu_code_segment(caller), dmcu_code_pc(caller));
        }
    }

    if (target == dmcu_code_address(0x28, 0x12a4)) {
        env->native_font_alt_copy_calls++;
        env->native_font_alt_copy_caller = caller & MASK24;
        for (i = 0; i < ARRAY_SIZE(env->native_font_alt_copy_args); i++) {
            env->native_font_alt_copy_args[i] = rom_argument(env, i);
        }
        if (env->native_font_alt_copy_calls <= 16) {
            qemu_log_mask(LOG_UNIMP,
                          "DMCU resident font alternate-copy call=%u "
                          "args=%04x,%04x,%04x,%04x,%04x "
                          "from=%02x:%04x\n",
                          env->native_font_alt_copy_calls,
                          env->native_font_alt_copy_args[0],
                          env->native_font_alt_copy_args[1],
                          env->native_font_alt_copy_args[2],
                          env->native_font_alt_copy_args[3],
                          env->native_font_alt_copy_args[4],
                          dmcu_code_segment(caller), dmcu_code_pc(caller));
        }
    }

    if ((target & MASK24) == dmcu_code_address(0x02, 0xbbf6)) {
        uint32_t page = ((rom_argument(env, 0) & MASK16) << 16) |
                        (rom_argument(env, 1) & MASK16);

        if ((caller & MASK24) == dmcu_code_address(0x50, 0xb834)) {
            env->bbf6_status_calls++;
            env->bbf6_status_page = page;
            env->bbf6_status_column = rom_argument(env, 2) & MASK16;
            env->bbf6_status_length = rom_argument(env, 5) & MASK16;
        } else if ((caller & MASK24) ==
                   dmcu_code_address(0x50, 0xb940)) {
            env->bbf6_full_calls++;
            env->bbf6_full_page = page;
            env->bbf6_full_column = rom_argument(env, 2) & MASK16;
            env->bbf6_full_length = rom_argument(env, 5) & MASK16;
        }
    }

    if (target == dmcu_code_address(0x18, 0x6454)) {
        uint16_t display_rows = address_space_lduw_le(
            &address_space_memory, 0x512a2c,
            MEMTXATTRS_UNSPECIFIED, NULL);
        unsigned trace_slot;

        font_blit_calls++;
        env->native_font_blit_calls++;
        env->native_font_blit_pointer =
            (internal_data_read(0x04fc, 16) << 16) |
            internal_data_read(0x04fe, 16);
        env->native_font_blit_row = internal_data_read(0x4b9c, 16);
        env->native_font_blit_count = internal_data_read(0x4b9e, 16);
        env->native_font_blit_position_y = internal_data_read(0x4b98, 16);
        env->native_font_blit_position_x = internal_data_read(0x4b9a, 16);
        env->native_font_blit_x = internal_data_read(0x4ba2, 16);
        env->native_font_blit_column = internal_data_read(0x4ba4, 16);
        env->native_font_blit_glyph = internal_data_read(0x4ba6, 16);
        env->native_font_blit_mask_a = internal_data_read(0x4ba8, 16);
        env->native_font_blit_mask_b = internal_data_read(0x4bae, 16);
        env->native_font_blit_mode = internal_data_read(0x4bb0, 16);
        env->native_font_blit_nonzero_glyph_calls +=
            env->native_font_blit_glyph != 0;
        env->native_font_blit_glyph_or |= env->native_font_blit_glyph;
        if (env->native_font_blit_pointer == 0x00503840) {
            env->native_font_blit_pointer_calls[0]++;
        } else if (env->native_font_blit_pointer == 0x00500000) {
            env->native_font_blit_pointer_calls[1]++;
        } else if (env->native_font_blit_pointer == 0x00508000) {
            env->native_font_blit_pointer_calls[2]++;
        } else {
            env->native_font_blit_pointer_calls[3]++;
        }
        /* A2:2A2C is reset before each character and incremented per row. */
        if (display_rows == 0) {
            trace_slot = env->font_blit_trace_count %
                         DMCU_FONT_BLIT_TRACE_SLOTS;
            env->font_blit_trace_caller[trace_slot] = caller & MASK24;
            env->font_blit_trace_pointer[trace_slot] =
                env->native_font_blit_pointer;
            env->font_blit_trace_position_x[trace_slot] =
                env->native_font_blit_position_x;
            env->font_blit_trace_position_y[trace_slot] =
                env->native_font_blit_position_y;
            env->font_blit_trace_character[trace_slot] = internal_data_read(
                (env->gpr[DMCU_FP] + 0x000a) & MASK16, 8);
            env->font_blit_trace_rows[trace_slot] = env->native_font_blit_row;
            env->font_blit_trace_count_words[trace_slot] =
                env->native_font_blit_count;
            env->font_blit_trace_offset[trace_slot] = env->native_font_blit_x;
            env->font_blit_trace_column[trace_slot] =
                env->native_font_blit_column;
            env->font_blit_trace_glyph[trace_slot] =
                env->native_font_blit_glyph;
            env->font_blit_trace_mode[trace_slot] = env->native_font_blit_mode;
            env->font_blit_trace_count++;
        }
        if (font_blit_calls <= 4 || !(font_blit_calls & 0x3f)) {
            qemu_log_mask(LOG_UNIMP,
                          "DMCU font blit call=%u row=%04x limit=%04x "
                          "x=%04x stride=%04x source=%04x:%04x\n",
                          font_blit_calls, display_rows,
                          internal_data_read(0x4b9c, 16),
                          internal_data_read(0x4ba2, 16),
                          internal_data_read(0x4ba4, 16),
                          internal_data_read(0x04fc, 16),
                          internal_data_read(0x04fe, 16));
        }
    }

    if (target == dmcu_code_address(0x18, 0x657a)) {
        uint32_t destination = (rom_argument(env, 0) << 16) |
                               rom_argument(env, 1);
        uint32_t source = (rom_argument(env, 2) << 16) |
                          rom_argument(env, 3);
        uint16_t length = rom_argument(env, 4);
        unsigned nonzero = 0;
        uint32_t hash = 2166136261u;

        for (i = 0; i < length; i++) {
            uint8_t value = address_space_ldub(
                &address_space_memory, (source + i) & MASK24,
                MEMTXATTRS_UNSPECIFIED, NULL);

            nonzero += value != 0;
            hash = (hash ^ value) * 16777619u;
        }
        env->native_font_copy_calls++;
        env->native_font_copy_destination = destination;
        env->native_font_copy_source = source;
        env->native_font_copy_length = length;
        env->native_font_copy_nonzero = nonzero;
        env->native_font_copy_nonzero_calls += nonzero != 0;
        env->native_font_copy_max_nonzero =
            MAX(env->native_font_copy_max_nonzero, nonzero);
        if (env->glyph_draw_active_character) {
            unsigned trace_slot = env->font_copy_trace_count %
                                  DMCU_FONT_COPY_TRACE_SLOTS;

            env->font_copy_trace_character[trace_slot] =
                env->glyph_draw_active_character & MASK16;
            env->font_copy_trace_source[trace_slot] = source & MASK24;
            env->font_copy_trace_length[trace_slot] = length;
            env->font_copy_trace_nonzero[trace_slot] = nonzero;
            env->font_copy_trace_hash[trace_slot] = hash;
            env->font_copy_trace_count++;
        }
        qemu_log_mask(LOG_UNIMP,
                      "DMCU font copy source=%02x:%04x length=%u "
                      "destination=%02x:%04x from=%02x:%04x\n",
                      dmcu_code_segment(source), dmcu_code_pc(source),
                      length, dmcu_code_segment(destination),
                      dmcu_code_pc(destination), dmcu_code_segment(caller),
                      dmcu_code_pc(caller));
    }

    if (target == dmcu_code_address(0x14, 0x6aec)) {
        uint16_t mode = rom_argument(env, 0);
        uint32_t source = mode == 0 ? 0x503840 :
                          mode == 1 ? 0x500000 :
                          mode == 2 ? 0x508000 : 0;
        unsigned nonzero = 0;

        lcd_flush_calls++;
        if (source) {
            for (i = 0; i < 14400; i++) {
                nonzero += address_space_ldub(
                    &address_space_memory, source + i,
                    MEMTXATTRS_UNSPECIFIED, NULL) != 0;
            }
        }
        env->native_lcd_flush_calls++;
        env->native_lcd_flush_mode = mode;
        env->native_lcd_flush_source = source;
        env->native_lcd_flush_nonzero = nonzero;
        env->native_lcd_flush_nonzero_calls += nonzero != 0;
        env->native_lcd_flush_max_nonzero =
            MAX(env->native_lcd_flush_max_nonzero, nonzero);
        env->native_lcd_flush_mode_calls[MIN(mode, 3)]++;
        qemu_log_mask(LOG_UNIMP,
                      "DMCU native LCD flush call=%u mode=%u source=%06x "
                      "nonzero=%u from=%02x:%04x\n",
                      lcd_flush_calls, mode, source, nonzero,
                      dmcu_code_segment(caller), dmcu_code_pc(caller));
    }

    if (missing) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU missing SoC ROM call %02x:%04x from %02x:%04x "
                      "return=%02x:%04x sp=%04x "
                      "stack=%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x\n",
                      dmcu_code_segment(target), dmcu_code_pc(target),
                      dmcu_code_segment(caller), dmcu_code_pc(caller),
                      dmcu_code_segment(return_pc), dmcu_code_pc(return_pc),
                      env->missing_rom_call_sp,
                      env->missing_rom_call_stack[0],
                      env->missing_rom_call_stack[1],
                      env->missing_rom_call_stack[2],
                      env->missing_rom_call_stack[3],
                      env->missing_rom_call_stack[4],
                      env->missing_rom_call_stack[5],
                      env->missing_rom_call_stack[6],
                      env->missing_rom_call_stack[7]);
    }
}

static void lcd_set_pixel(uint8_t *frame, unsigned x, unsigned y,
                          bool value)
{
    uint8_t *pixel = &frame[y * DMCU_LCD_STRIDE + (x >> 3)];
    uint8_t mask = 0x80 >> (x & 7);

    *pixel = value ? *pixel | mask : *pixel & ~mask;
}

/*
 * The updater does not contain the SoC's resident UI/mask ROM.  Keep the
 * ROM-less machine useful by rendering a small menu into the same 1-bpp
 * framebuffer used by the emulated LCD services.  This is deliberately in
 * the QEMU backend: the Web frontend remains a dumb framebuffer/input client.
 */
static const uint8_t np560_font5x7[128][5] = {
    [' '] = { 0x00, 0x00, 0x00, 0x00, 0x00 },
    ['#'] = { 0x14, 0x7f, 0x14, 0x7f, 0x14 },
    ['%'] = { 0x23, 0x13, 0x08, 0x64, 0x62 },
    ['('] = { 0x00, 0x1c, 0x22, 0x41, 0x00 },
    [')'] = { 0x00, 0x41, 0x22, 0x1c, 0x00 },
    ['+'] = { 0x08, 0x08, 0x3e, 0x08, 0x08 },
    ['-'] = { 0x08, 0x08, 0x08, 0x08, 0x08 },
    ['.'] = { 0x00, 0x60, 0x60, 0x00, 0x00 },
    ['/'] = { 0x20, 0x10, 0x08, 0x04, 0x02 },
    [':'] = { 0x00, 0x36, 0x36, 0x00, 0x00 },
    ['='] = { 0x14, 0x14, 0x14, 0x14, 0x14 },
    ['>'] = { 0x00, 0x41, 0x22, 0x14, 0x08 },
    ['?'] = { 0x02, 0x01, 0x51, 0x09, 0x06 },
    ['0'] = { 0x3e, 0x51, 0x49, 0x45, 0x3e },
    ['1'] = { 0x00, 0x42, 0x7f, 0x40, 0x00 },
    ['2'] = { 0x42, 0x61, 0x51, 0x49, 0x46 },
    ['3'] = { 0x21, 0x41, 0x45, 0x4b, 0x31 },
    ['4'] = { 0x18, 0x14, 0x12, 0x7f, 0x10 },
    ['5'] = { 0x27, 0x45, 0x45, 0x45, 0x39 },
    ['6'] = { 0x3c, 0x4a, 0x49, 0x49, 0x30 },
    ['7'] = { 0x01, 0x71, 0x09, 0x05, 0x03 },
    ['8'] = { 0x36, 0x49, 0x49, 0x49, 0x36 },
    ['9'] = { 0x06, 0x49, 0x49, 0x29, 0x1e },
    ['A'] = { 0x7e, 0x11, 0x11, 0x11, 0x7e },
    ['B'] = { 0x7f, 0x49, 0x49, 0x49, 0x36 },
    ['C'] = { 0x3e, 0x41, 0x41, 0x41, 0x22 },
    ['D'] = { 0x7f, 0x41, 0x41, 0x22, 0x1c },
    ['E'] = { 0x7f, 0x49, 0x49, 0x49, 0x41 },
    ['F'] = { 0x7f, 0x09, 0x09, 0x09, 0x01 },
    ['G'] = { 0x3e, 0x41, 0x49, 0x49, 0x7a },
    ['H'] = { 0x7f, 0x08, 0x08, 0x08, 0x7f },
    ['I'] = { 0x00, 0x41, 0x7f, 0x41, 0x00 },
    ['J'] = { 0x20, 0x40, 0x41, 0x3f, 0x01 },
    ['K'] = { 0x7f, 0x08, 0x14, 0x22, 0x41 },
    ['L'] = { 0x7f, 0x40, 0x40, 0x40, 0x40 },
    ['M'] = { 0x7f, 0x02, 0x0c, 0x02, 0x7f },
    ['N'] = { 0x7f, 0x04, 0x08, 0x10, 0x7f },
    ['O'] = { 0x3e, 0x41, 0x41, 0x41, 0x3e },
    ['P'] = { 0x7f, 0x09, 0x09, 0x09, 0x06 },
    ['Q'] = { 0x3e, 0x41, 0x51, 0x21, 0x5e },
    ['R'] = { 0x7f, 0x09, 0x19, 0x29, 0x46 },
    ['S'] = { 0x46, 0x49, 0x49, 0x49, 0x31 },
    ['T'] = { 0x01, 0x01, 0x7f, 0x01, 0x01 },
    ['U'] = { 0x3f, 0x40, 0x40, 0x40, 0x3f },
    ['V'] = { 0x1f, 0x20, 0x40, 0x20, 0x1f },
    ['W'] = { 0x3f, 0x40, 0x38, 0x40, 0x3f },
    ['X'] = { 0x63, 0x14, 0x08, 0x14, 0x63 },
    ['Y'] = { 0x07, 0x08, 0x70, 0x08, 0x07 },
    ['Z'] = { 0x61, 0x51, 0x49, 0x45, 0x43 },
    ['_'] = { 0x40, 0x40, 0x40, 0x40, 0x40 },
};

static void np560_hle_fill(uint8_t *frame, unsigned x1, unsigned y1,
                           unsigned x2, unsigned y2, bool value)
{
    unsigned x, y;

    x2 = MIN(x2, DMCU_LCD_WIDTH - 1);
    y2 = MIN(y2, DMCU_LCD_HEIGHT - 1);
    for (y = y1; y <= y2; y++) {
        for (x = x1; x <= x2; x++) {
            lcd_set_pixel(frame, x, y, value);
        }
    }
}

static void np560_hle_box(uint8_t *frame, unsigned x1, unsigned y1,
                          unsigned x2, unsigned y2, bool value)
{
    unsigned x, y;

    for (x = x1; x <= x2; x++) {
        lcd_set_pixel(frame, x, y1, value);
        lcd_set_pixel(frame, x, y2, value);
    }
    for (y = y1; y <= y2; y++) {
        lcd_set_pixel(frame, x1, y, value);
        lcd_set_pixel(frame, x2, y, value);
    }
}

static void np560_hle_text(uint8_t *frame, unsigned x, unsigned y,
                           const char *text, unsigned scale, bool value)
{
    unsigned column, row, dx, dy;

    for (; *text; text++, x += 6 * scale) {
        unsigned ch = (uint8_t)*text;

        if (ch >= 'a' && ch <= 'z') {
            ch -= 'a' - 'A';
        }
        if (ch >= G_N_ELEMENTS(np560_font5x7)) {
            ch = '#';
        }
        for (column = 0; column < 5; column++) {
            for (row = 0; row < 7; row++) {
                if (!(np560_font5x7[ch][column] & (1u << row))) {
                    continue;
                }
                for (dy = 0; dy < scale; dy++) {
                    for (dx = 0; dx < scale; dx++) {
                        unsigned px = x + column * scale + dx;
                        unsigned py = y + row * scale + dy;

                        if (px < DMCU_LCD_WIDTH && py < DMCU_LCD_HEIGHT) {
                            lcd_set_pixel(frame, px, py, value);
                        }
                    }
                }
            }
        }
    }
}

static void np560_hle_centered_text(uint8_t *frame, unsigned y,
                                    const char *text, unsigned scale,
                                    bool value)
{
    unsigned width = strlen(text) * 6 * scale - scale;
    unsigned x = width < DMCU_LCD_WIDTH ? (DMCU_LCD_WIDTH - width) / 2 : 0;

    np560_hle_text(frame, x, y, text, scale, value);
}

static const char *const np560_hle_items[] = {
    "DICTIONARY", "LEARNING", "TOOLS", "SYSTEM",
};

static void np560_hle_render(CPUDMCUState *env)
{
    uint8_t frame[DMCU_LCD_FB_SIZE] = { 0 };
    unsigned index;

    np560_hle_box(frame, 0, 0, DMCU_LCD_WIDTH - 1,
                  DMCU_LCD_HEIGHT - 1, true);
    if (env->hle_ui_page == 0) {
        np560_hle_centered_text(frame, 5, "NOAH NP560+", 2, true);
        np560_hle_centered_text(frame, 21, "QEMU ROM-LAYER", 1, true);
        for (index = 0; index < G_N_ELEMENTS(np560_hle_items); index++) {
            unsigned y = 34 + index * 17;
            bool selected = index == env->hle_ui_selection;

            if (selected) {
                np560_hle_fill(frame, 25, y - 3, 214, y + 10, true);
            }
            np560_hle_text(frame, 35, y, selected ? ">" : " ", 1,
                           !selected);
            np560_hle_text(frame, 51, y, np560_hle_items[index], 1,
                           !selected);
        }
        np560_hle_centered_text(frame, 108, "UP DOWN ENTER", 1, true);
    } else {
        const char *title = np560_hle_items[env->hle_ui_selection];

        np560_hle_centered_text(frame, 9, title, 2, true);
        np560_hle_fill(frame, 18, 31, 221, 32, true);
        np560_hle_centered_text(frame, 50, "ROM API PENDING", 1, true);
        np560_hle_centered_text(frame, 67, "FIRMWARE IS LOADED", 1, true);
        np560_hle_centered_text(frame, 97, "ESC: BACK", 1, true);
    }
    cpu_physical_memory_write(DMCU_LCD_FB_BASE, frame, sizeof(frame));
    env->lcd_service_calls++;
    env->lcd_frames++;
}

static void np560_hle_start(CPUDMCUState *env)
{
    env->hle_ui_active = true;
    env->hle_ui_page = 0;
    env->hle_ui_selection = 0;
    env->hle_ui_key_latch = env->web_key_state;
    np560_hle_render(env);
}

static void np560_hle_tick(CPUDMCUState *env)
{
    uint32_t keys, pressed;
    bool redraw = false;
    unsigned index;

    if (!env->hle_ui_enabled || !env->hle_ui_active) {
        return;
    }
    keys = env->web_key_state;
    pressed = keys & ~env->hle_ui_key_latch;
    env->hle_ui_key_latch = keys;
    if (!pressed) {
        return;
    }

    for (index = 0; index < G_N_ELEMENTS(np560_hle_items); index++) {
        if (pressed & (1u << (8 + index))) {
            env->hle_ui_selection = index;
            env->hle_ui_page = index + 1;
            redraw = true;
            break;
        }
    }
    if (!redraw && env->hle_ui_page == 0) {
        if (pressed & ((1u << 0) | (1u << 12))) {
            env->hle_ui_selection =
                (env->hle_ui_selection + G_N_ELEMENTS(np560_hle_items) - 1) %
                G_N_ELEMENTS(np560_hle_items);
            redraw = true;
        } else if (pressed & ((1u << 1) | (1u << 7) | (1u << 13))) {
            env->hle_ui_selection =
                (env->hle_ui_selection + 1) % G_N_ELEMENTS(np560_hle_items);
            redraw = true;
        } else if (pressed & ((1u << 3) | (1u << 4))) {
            env->hle_ui_page = env->hle_ui_selection + 1;
            redraw = true;
        }
    } else if (!redraw &&
               (pressed & ((1u << 2) | (1u << 5) | (1u << 6)))) {
        env->hle_ui_page = 0;
        redraw = true;
    }
    if (redraw) {
        np560_hle_render(env);
    }
}

/*
 * The resident segment-03 ROM owns the application's event loop.  The reset
 * vector enters the event handler at 33:4F50 (its initialization-event
 * continuation), then RETS to 03:0032.  The complete handler is present at
 * 33:4510 and has the ordinary compiler ABI:
 *
 *     handler(uint16_t event, far_pointer context)
 *
 * Recreate the missing ROM's call frame only while the CPU is parked at its
 * return address.  Drawing and state changes remain native NP560.PRG code;
 * the Web bridge only supplies key edges and reads the LCD framebuffer.
 */
static void np560_native_dispatch(CPUDMCUState *env, uint16_t event)
{
    uint32_t context = env->startup_context & MASK24;
    uint32_t return_pc = dmcu_code_address(0x03, 0x0032);

    /* The caller removes the six argument bytes after every far return. */
    env->gpr[DMCU_SP] = 0xfffe;
    env->gpr[DMCU_FP] = 0;
    push(env, context & MASK16);
    push(env, context >> 16);
    push(env, event);
    far_return_push(env, return_pc);
    env->pc = dmcu_code_address(0x33, 0x4510);
    env->native_ui_events++;
    env->native_ui_last_event = event;
    qemu_log_mask(LOG_UNIMP,
                  "DMCU native UI event %04x context=%06x -> 33:4510\n",
                  event, context);
}

static bool np560_native_tick(CPUDMCUState *env, uint32_t start)
{
    uint32_t keys;
    uint32_t pressed;
    uint16_t event = 0;

    if (!env->rom_hle_enabled ||
        (dmcu_code_address(0x03, 0x0032) >= env->resident_rom_base &&
         dmcu_code_address(0x03, 0x0032) < env->resident_rom_limit) ||
        env->hle_ui_enabled ||
        start != dmcu_code_address(0x03, 0x0032)) {
        return false;
    }

    keys = env->web_key_state;
    if (!env->native_ui_active) {
        /* 0x8e is the handler's resident-ROM/UI activation event. */
        env->native_ui_active = true;
        env->native_ui_key_latch = keys;
        event = 0x008e;
    } else {
        pressed = keys & ~env->native_ui_key_latch;
        env->native_ui_key_latch = keys;
        if (pressed & ((1u << 0) | (1u << 12))) {
            event = 0x0082; /* up */
        } else if (pressed & ((1u << 1) | (1u << 7) | (1u << 13))) {
            event = 0x0083; /* down */
        } else if (pressed & ((1u << 2) | (1u << 5) | (1u << 6))) {
            event = 0x0084; /* left/back */
        } else if (pressed & ((1u << 3) | (1u << 4))) {
            event = 0x0085; /* right/enter */
        }
    }

    if (!event) {
        return false;
    }
    np560_native_dispatch(env, event);
    return true;
}

static void lcd_rectangle(CPUDMCUState *env, bool filled)
{
    uint8_t frame[DMCU_LCD_FB_SIZE];
    unsigned x1 = rom_argument(env, 0);
    unsigned y1 = rom_argument(env, 1);
    unsigned x2 = rom_argument(env, 2);
    unsigned y2 = rom_argument(env, 3);
    unsigned x, y, swap;
    bool color = env->lcd_foreground & 1;

    if (x1 > x2) {
        swap = x1;
        x1 = x2;
        x2 = swap;
    }
    if (y1 > y2) {
        swap = y1;
        y1 = y2;
        y2 = swap;
    }
    if (x1 >= DMCU_LCD_WIDTH || y1 >= DMCU_LCD_HEIGHT) {
        return;
    }
    x2 = MIN(x2, DMCU_LCD_WIDTH - 1);
    y2 = MIN(y2, DMCU_LCD_HEIGHT - 1);
    cpu_physical_memory_read(DMCU_LCD_FB_BASE, frame, sizeof(frame));
    for (y = y1; y <= y2; y++) {
        for (x = x1; x <= x2; x++) {
            if (filled || y == y1 || y == y2 || x == x1 || x == x2) {
                lcd_set_pixel(frame, x, y, color);
            }
        }
    }
    cpu_physical_memory_write(DMCU_LCD_FB_BASE, frame, sizeof(frame));
    env->lcd_service_calls++;
    qemu_log_mask(LOG_UNIMP,
                  "DMCU LCD %s rectangle (%u,%u)-(%u,%u), color=%u\n",
                  filled ? "filled" : "outline", x1, y1, x2, y2, color);
}

#define NP560_ROM_STRING_LIMIT 512

static uint32_t rom_pointer(CPUDMCUState *env, unsigned index)
{
    return (((uint32_t)rom_argument(env, index) & 0xff) << 16) |
           rom_argument(env, index + 1);
}

static size_t rom_read_string(uint32_t address, char *buffer, size_t capacity)
{
    size_t length;

    if (!capacity) {
        return 0;
    }
    for (length = 0; length + 1 < capacity; length++) {
        uint8_t value;

        cpu_physical_memory_read((address + length) & MASK24, &value, 1);
        if (!value) {
            break;
        }
        buffer[length] = value;
    }
    buffer[length] = '\0';
    return length;
}

static void rom_write_string(uint32_t address, const char *buffer,
                             size_t capacity)
{
    size_t length = MIN(strlen(buffer), capacity ? capacity - 1 : 0);
    uint8_t zero = 0;

    if (!capacity) {
        return;
    }
    cpu_physical_memory_write(address & MASK24, buffer, length);
    cpu_physical_memory_write((address + length) & MASK24, &zero, 1);
}

static bool rom_string_is_text(const char *buffer)
{
    const uint8_t *cursor = (const uint8_t *)buffer;

    if (!*cursor) {
        return true;
    }
    for (; *cursor; cursor++) {
        if (*cursor < 0x20 || *cursor > 0x7e) {
            return false;
        }
    }
    return true;
}

static void rom_format_one(char *output, size_t capacity, const char *format,
                           uint16_t value)
{
    size_t used = 0;
    bool converted = false;

    for (; *format && used + 1 < capacity; format++) {
        char temporary[24];
        const char *insert = temporary;
        size_t length;

        if (*format != '%' || converted) {
            output[used++] = *format;
            continue;
        }
        format++;
        if (!*format) {
            break;
        }
        if (*format == '%') {
            output[used++] = '%';
            continue;
        }
        switch (*format) {
        case 'c':
            temporary[0] = value & 0xff;
            temporary[1] = '\0';
            break;
        case 'd':
        case 'i':
            snprintf(temporary, sizeof(temporary), "%d", (int16_t)value);
            break;
        case 'x':
            snprintf(temporary, sizeof(temporary), "%x", value);
            break;
        case 'X':
            snprintf(temporary, sizeof(temporary), "%X", value);
            break;
        case 'u':
        default:
            snprintf(temporary, sizeof(temporary), "%u", value);
            break;
        }
        converted = true;
        length = MIN(strlen(insert), capacity - used - 1);
        memcpy(output + used, insert, length);
        used += length;
    }
    output[used] = '\0';
}

static void lcd_text(CPUDMCUState *env, bool fixed_length)
{
    uint8_t frame[DMCU_LCD_FB_SIZE];
    char text[NP560_ROM_STRING_LIMIT];
    uint32_t address = rom_pointer(env, 2);
    unsigned x = rom_argument(env, 0);
    unsigned y = rom_argument(env, 1);
    size_t length = rom_read_string(address, text, sizeof(text));
    size_t index;

    if (fixed_length) {
        length = MIN(length, (size_t)rom_argument(env, 4));
        text[length] = '\0';
    }
    /* The external font ROM is not in NP560.PRG.  Preserve ASCII and render
     * each byte of an unavailable double-byte glyph as a visible cell. */
    for (index = 0; index < length; index++) {
        uint8_t ch = text[index];

        if (ch < 0x20 || ch > 0x7e) {
            text[index] = '#';
        }
    }
    cpu_physical_memory_read(DMCU_LCD_FB_BASE, frame, sizeof(frame));
    np560_hle_text(frame, x, y, text, 1, env->lcd_foreground & 1);
    cpu_physical_memory_write(DMCU_LCD_FB_BASE, frame, sizeof(frame));
    env->lcd_service_calls++;
    qemu_log_mask(LOG_UNIMP, "DMCU LCD text (%u,%u) ptr=%06x len=%zu\n",
                  x, y, address, length);
}

static bool np560_rom_service(CPUDMCUState *env, uint32_t target,
                              uint32_t return_pc)
{
    uint32_t logical = target;

    switch (logical) {
    case 0x03407c: {
        /* strcpy(destination, source). */
        char source[NP560_ROM_STRING_LIMIT];
        uint32_t destination = rom_pointer(env, 0);

        rom_read_string(rom_pointer(env, 2), source, sizeof(source));
        rom_write_string(destination, source, sizeof(source));
        env->gpr[0] = destination >> 16;
        env->gpr[1] = destination & MASK16;
        return true;
    }
    case 0x034080: {
        /* strcat(destination, source). */
        char destination_text[NP560_ROM_STRING_LIMIT];
        char source[NP560_ROM_STRING_LIMIT];
        uint32_t destination = rom_pointer(env, 0);
        size_t used = rom_read_string(destination, destination_text,
                                      sizeof(destination_text));

        rom_read_string(rom_pointer(env, 2), source, sizeof(source));
        g_strlcpy(destination_text + used, source,
                  sizeof(destination_text) - used);
        rom_write_string(destination, destination_text,
                         sizeof(destination_text));
        env->gpr[0] = destination >> 16;
        env->gpr[1] = destination & MASK16;
        return true;
    }
    case 0x0340b4: {
        /* sprintf(destination, format, one uint16_t argument). */
        char format[96];
        char output[NP560_ROM_STRING_LIMIT];
        uint32_t destination = rom_pointer(env, 0);
        uint16_t value = rom_argument(env, 4);

        rom_read_string(rom_pointer(env, 2), format, sizeof(format));
        if (!rom_string_is_text(format) || !strchr(format, '%')) {
            snprintf(output, sizeof(output), "%u", value);
        } else {
            rom_format_one(output, sizeof(output), format, value);
        }
        rom_write_string(destination, output, sizeof(output));
        env->gpr[0] = destination >> 16;
        env->gpr[1] = destination & MASK16;
        return true;
    }
    case 0x1feea6: {
        /*
         * The compiler uses this resident-ROM entry as a far indirect-call
         * trampoline.  Its three-word ABI is:
         *
         *     callback physical byte address (high, low), uint16_t argument
         *
         * All observed callers remove six bytes after the call.  Replace the
         * two callback words with the forwarded argument, then create the
         * ordinary SCALL return frame.  The callback's RETS consequently
         * returns to the original caller with SP restored to the position
         * expected by that caller's six-byte cleanup.
         */
        uint32_t callback = ((uint32_t)rom_argument(env, 0) << 16) |
                            rom_argument(env, 1);
        uint16_t argument = rom_argument(env, 2);

        if ((callback & 1) || callback < DMCU_PROGRAM_BASE ||
            callback >= DMCU_PROGRAM_BASE + DMCU_PROGRAM_SIZE) {
            qemu_log_mask(LOG_UNIMP,
                          "DMCU ROM far callback rejected %06x arg=%04x\n",
                          callback, argument);
            return true;
        }
        internal_data_write(env->gpr[DMCU_SP], argument, 16);
        far_return_push(env, return_pc);
        env->pc = callback;
        qemu_log_mask(LOG_UNIMP,
                      "DMCU ROM far callback %02x:%04x arg=%04x\n",
                      dmcu_code_segment(callback),
                      dmcu_code_pc(callback), argument);
        return true;
    }
    case 0x034120:
        /* Millisecond delay.  The QEMU main loop already supplies pacing. */
        return true;
    case 0x0341a8:
        lcd_text(env, false);
        return true;
    case 0x0341ac:
        lcd_text(env, true);
        return true;
    case 0x0341c8:
        env->lcd_foreground = rom_argument(env, 0) & 1;
        env->lcd_background = rom_argument(env, 1) & 1;
        env->lcd_service_calls++;
        return true;
    case 0x034214:
        lcd_rectangle(env, false);
        return true;
    case 0x034218:
        lcd_rectangle(env, true);
        return true;
    case 0x034224:
        if (rom_argument(env, 0)) {
            env->lcd_frames++;
        }
        env->lcd_service_calls++;
        return true;
    case 0x03422c:
        env->lcd_frames++;
        env->lcd_service_calls++;
        return true;
    default:
        return false;
    }
}

/*
 * NP560.PRG is an overlay image: a few compiler run-time entry points are
 * called at their final CS:PC even though the bytes stored at that position
 * still belong to the pre-overlay image.  The resident loader normally
 * installs these helpers before application code runs.  Model the helpers
 * whose ABI can be established independently from all of their call sites.
 */
static bool np560_overlay_service(CPUDMCUState *env, uint32_t target)
{
    switch (target) {
    case 0x31c0e8:
    case 0x31c224:
        /*
         * Acquire/release an overlay bank by its one-word module id.  The
         * update image already supplies the currently executing main banks;
         * keep the reference-management calls side-effect free until the
         * external overlay directory has been recovered.
         */
        env->overlay_service_calls++;
        qemu_log_mask(LOG_UNIMP, "DMCU overlay %s module=%04x\n",
                      target == 0x31c0e8 ? "acquire" : "release",
                      rom_argument(env, 0));
        return true;
    case 0x256042: {
        /* Resident overlay utility: clear byte buffer (length, far pointer). */
        uint16_t length = rom_argument(env, 0);
        uint32_t destination = ((uint32_t)rom_argument(env, 1) << 16) |
                               rom_argument(env, 2);
        uint8_t zeroes[256] = { 0 };

        while (length) {
            uint16_t chunk = MIN(length, (uint16_t)sizeof(zeroes));

            cpu_physical_memory_write(destination & MASK24, zeroes, chunk);
            destination = (destination + chunk) & MASK24;
            length -= chunk;
        }
        env->gpr[0] = 0;
        env->overlay_service_calls++;
        return true;
    }
    case 0x3307b0: {
        /* 32-bit multiply: (arg0:arg1) * (arg2:arg3) -> R0:R1. */
        uint32_t left = ((uint32_t)rom_argument(env, 0) << 16) |
                        rom_argument(env, 1);
        uint32_t right = ((uint32_t)rom_argument(env, 2) << 16) |
                         rom_argument(env, 3);
        uint32_t product = left * right;

        env->gpr[0] = product >> 16;
        env->gpr[1] = product & MASK16;
        env->overlay_service_calls++;
        return true;
    }
    default:
        return false;
    }
}

static bool exec_control(CPUDMCUState *env, uint8_t op, uint8_t arg,
                         uint16_t ext, uint32_t start, uint32_t next)
{
    uint32_t target;
    if ((op == 0xac || op == 0xbc) && (arg >> 4) == 0) {
        bool take = condition(env, arg & 15);

        if (start == 0x5188a8) {
            env->stream_source_branch_seen++;
            env->stream_source_branch_taken = take;
        } else if (start == 0x5188b8) {
            env->stream_count_branch_seen++;
            env->stream_count_branch_taken = take;
        }
        if (take) {
            if (op == 0xbc) {
                near_return_push(env, next);
            }
            env->pc = near_pc(start, ext);
        }
        return true;
    }
    if (op == 0xad || op == 0xbd) {
        target = dmcu_code_address(arg, ext);
        if (op == 0xbd) {
            bool execute_resident_rom =
                target >= env->resident_rom_base &&
                target < env->resident_rom_limit;
            bool execute_auxiliary =
                target >= env->auxiliary_code_base &&
                target < env->auxiliary_code_limit;

            if (execute_resident_rom &&
                (target == dmcu_code_address(0x02, 0xbbf6) ||
                 target == dmcu_code_address(0x14, 0x6aec) ||
                 target == dmcu_code_address(0x17, 0x9244) ||
                 target == dmcu_code_address(0x18, 0x6454) ||
                 target == dmcu_code_address(0x18, 0x657a) ||
                 target == dmcu_code_address(0x28, 0x12a4))) {
                trace_rom_call(env, target, start, next, false);
            }

            if (target == 0x25206eu || target == 0x2d261cu ||
                target == 0x2c2ebau) {
                trace_resource_io_call(env, start, target);
            }
            if (target == dmcu_code_address(0x2e, 0x4572) &&
                !env->resource_io_trace_frozen) {
                uint32_t slot = env->far_copy_call_trace_count %
                                DMCU_FAR_COPY_CALL_TRACE_SLOTS;
                unsigned int argument;

                env->far_copy_call_trace_from[slot] = start & MASK24;
                env->far_copy_call_trace_interrupts[slot] =
                    env->interrupt_entries;
                env->far_copy_call_trace_sp[slot] =
                    env->gpr[DMCU_SP] & MASK16;
                env->far_copy_call_trace_fp[slot] =
                    env->gpr[DMCU_FP] & MASK16;
                for (argument = 0;
                     argument < DMCU_RESOURCE_CANDIDATE_ARGUMENT_WORDS;
                     argument++) {
                    env->far_copy_call_trace_args[slot][argument] =
                        rom_argument(env, argument);
                }
                env->far_copy_call_trace_count++;
            }

            if (target == dmcu_code_address(0x0b, 0xccd2)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU ROM 0B:CCD2 call from %02x:%04x "
                              "sp=%04x fp=%04x args=%04x,%04x,%04x,%04x,%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0), rom_argument(env, 1),
                              rom_argument(env, 2), rom_argument(env, 3),
                              rom_argument(env, 4));
            }
            if (target == dmcu_code_address(0x5f, 0xf928)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU relocated storage sector probe call "
                              "from %02x:%04x "
                              "sp=%04x fp=%04x args=%04x,%04x,%04x,%04x,"
                              "%04x,%04x,%04x,%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0), rom_argument(env, 1),
                              rom_argument(env, 2), rom_argument(env, 3),
                              rom_argument(env, 4), rom_argument(env, 5),
                              rom_argument(env, 6), rom_argument(env, 7));
            }
            if (target == dmcu_code_address(0x29, 0x02d8)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU storage capacity scan call from %02x:%04x "
                              "sp=%04x fp=%04x args=%04x,%04x,%04x,%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0), rom_argument(env, 1),
                              rom_argument(env, 2), rom_argument(env, 3));
            }
            if (target == dmcu_code_address(0x30, 0xa3c2)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU storage unit open call from %02x:%04x "
                              "sp=%04x fp=%04x unit=%04x next=%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0), rom_argument(env, 1));
            }
            if (target == dmcu_code_address(0x18, 0xf97c)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU resident storage unit init call from "
                              "%02x:%04x sp=%04x fp=%04x unit=%04x "
                              "root=%04x:%04x rec0=%04x:%04x "
                              "rec2=%04x:%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0),
                              address_space_lduw_le(
                                  &address_space_memory, 0x005129c4u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
                              address_space_lduw_le(
                                  &address_space_memory, 0x005129c6u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
                              address_space_lduw_le(
                                  &address_space_memory, 0x005127a4u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
                              address_space_lduw_le(
                                  &address_space_memory, 0x005127a6u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
                              address_space_lduw_le(
                                  &address_space_memory, 0x005127f0u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
                              address_space_lduw_le(
                                  &address_space_memory, 0x005127f2u,
                                  MEMTXATTRS_UNSPECIFIED, NULL));
            }
            if (target == dmcu_code_address(0x2c, 0xfe08) ||
                target == dmcu_code_address(0x31, 0xcbe8) ||
                target == dmcu_code_address(0x5f, 0xf928) ||
                target == dmcu_code_address(0x27, 0x81c8) ||
                target == dmcu_code_address(0x32, 0x6ea8) ||
                target == dmcu_code_address(0x32, 0x6f12) ||
                target == dmcu_code_address(0x2e, 0xc104) ||
                target == dmcu_code_address(0x2c, 0x2eba) ||
                target == dmcu_code_address(0x2a, 0x1440) ||
                target == dmcu_code_address(0x2e, 0xbf9a) ||
                target == dmcu_code_address(0x29, 0x05b0) ||
                target == dmcu_code_address(0x30, 0xfe0e) ||
                target == dmcu_code_address(0x2e, 0x4572)) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU storage worker call %02x:%04x from %02x:%04x "
                    "sp=%04x fp=%04x args=%04x,%04x,%04x,%04x,"
                    "%04x,%04x,%04x,%04x\n",
                    dmcu_code_segment(target), dmcu_code_pc(target),
                    dmcu_code_segment(start), dmcu_code_pc(start),
                    env->gpr[DMCU_SP] & MASK16,
                    env->gpr[DMCU_FP] & MASK16,
                    rom_argument(env, 0), rom_argument(env, 1),
                    rom_argument(env, 2), rom_argument(env, 3),
                    rom_argument(env, 4), rom_argument(env, 5),
                    rom_argument(env, 6), rom_argument(env, 7));
            }
            if (target == dmcu_code_address(0x27, 0x81c8)) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU FTL logical lookup entry page=%04x "
                    "map-block=%04x range=%04x..%04x ready=%04x "
                    "entry0=%04x:%04x max=%04x\n",
                    rom_argument(env, 0),
                    internal_data_read(0x04e4, 16),
                    internal_data_read(0x027e, 16),
                    internal_data_read(0x0280, 16),
                    internal_data_read(0x0284, 16),
                    internal_data_read(0x0286, 16),
                    internal_data_read(0x0288, 16),
                    internal_data_read(0x4b6c, 16));
            }
            if (target == dmcu_code_address(0x2d, 0x3460)) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU storage driver resolve call from %02x:%04x "
                    "sp=%04x fp=%04x r0-r3=%04x,%04x,%04x,%04x "
                    "args=%04x,%04x root=%04x:%04x\n",
                    dmcu_code_segment(start), dmcu_code_pc(start),
                    env->gpr[DMCU_SP] & MASK16,
                    env->gpr[DMCU_FP] & MASK16,
                    env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                    env->gpr[2] & MASK16, env->gpr[3] & MASK16,
                    rom_argument(env, 0), rom_argument(env, 1),
                    address_space_lduw_le(
                        &address_space_memory, 0x005129c4u,
                        MEMTXATTRS_UNSPECIFIED, NULL),
                    address_space_lduw_le(
                        &address_space_memory, 0x005129c6u,
                        MEMTXATTRS_UNSPECIFIED, NULL));
            }
            if (target == dmcu_code_address(0x33, 0x091c) ||
                target == dmcu_code_address(0x33, 0x6e5e) ||
                target == dmcu_code_address(0x33, 0x0070)) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU storage callback call %02x:%04x from %02x:%04x "
                    "sp=%04x fp=%04x args=%04x,%04x,%04x,%04x\n",
                    dmcu_code_segment(target), dmcu_code_pc(target),
                    dmcu_code_segment(start), dmcu_code_pc(start),
                    env->gpr[DMCU_SP] & MASK16,
                    env->gpr[DMCU_FP] & MASK16,
                    rom_argument(env, 0), rom_argument(env, 1),
                    rom_argument(env, 2), rom_argument(env, 3));
            }
            if (target == dmcu_code_address(0x25, 0xe324)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU storage attach call from %02x:%04x "
                              "sp=%04x fp=%04x args=%04x,%04x,%04x,%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0), rom_argument(env, 1),
                              rom_argument(env, 2), rom_argument(env, 3));
            }
            if (target == dmcu_code_address(0x2a, 0xd374)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU storage record lookup call from %02x:%04x "
                              "sp=%04x fp=%04x flag=%04x record=%04x:%04x "
                              "caller-args=%04x,%04x stack=%04x,%04x,%04x,"
                              "%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0), rom_argument(env, 1),
                              rom_argument(env, 2),
                              internal_data_read(
                                  (env->gpr[DMCU_FP] + 6) & MASK16, 16),
                              internal_data_read(
                                  (env->gpr[DMCU_FP] + 8) & MASK16, 16),
                              internal_data_read(
                                  env->gpr[DMCU_SP] & MASK16, 16),
                              internal_data_read(
                                  (env->gpr[DMCU_SP] + 2) & MASK16, 16),
                              internal_data_read(
                                  (env->gpr[DMCU_SP] + 4) & MASK16, 16),
                              internal_data_read(
                                  (env->gpr[DMCU_SP] + 6) & MASK16, 16));
            }

            if (start == dmcu_code_address(0x50, 0x8476)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU map-call index=%04x "
                              "r0-r7=%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x "
                              "sp=%04x fp=%04x\n",
                              internal_data_read(
                                  (env->gpr[DMCU_FP] + 0xffe2) & MASK16, 16),
                              env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                              env->gpr[2] & MASK16, env->gpr[3] & MASK16,
                              env->gpr[4] & MASK16, env->gpr[5] & MASK16,
                              env->gpr[6] & MASK16, env->gpr[7] & MASK16,
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16);
            }

            if (target == dmcu_code_address(0x28, 0xfd38)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU glyph call 28:fd38 from %02x:%04x "
                              "sp=%04x fp=%04x args=%04x,%04x,%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0), rom_argument(env, 1),
                              rom_argument(env, 2));
            }
            if (start == dmcu_code_address(0x31, 0x5944) &&
                target == dmcu_code_address(0x31, 0x7772)) {
                unsigned argument;

                env->clock_format_root_calls++;
                env->clock_format_root_active = true;
                env->clock_format_output_trace_count = 0;
                env->clock_stream_move_trace_count = 0;
                env->clock_stream_copy_trace_count = 0;
                env->clock_format_root_sp = env->gpr[DMCU_SP] & MASK16;
                for (argument = 0; argument < 8; argument++) {
                    env->clock_format_root_args[argument] =
                        rom_argument(env, argument) & MASK16;
                }
            }
            if (start == dmcu_code_address(0x31, 0x77e8) &&
                target == dmcu_code_address(0x15, 0xff04)) {
                unsigned argument;

                env->clock_format_service_calls++;
                env->clock_format_service_sp = env->gpr[DMCU_SP] & MASK16;
                for (argument = 0; argument < 8; argument++) {
                    env->clock_format_service_args[argument] =
                        rom_argument(env, argument) & MASK16;
                }
            }
            if (start == dmcu_code_address(0x15, 0xffe8) &&
                target == dmcu_code_address(0x0c, 0x8622)) {
                unsigned argument;

                env->clock_format_core_calls++;
                env->clock_format_core_sp = env->gpr[DMCU_SP] & MASK16;
                for (argument = 0; argument < 8; argument++) {
                    env->clock_format_core_args[argument] =
                        rom_argument(env, argument) & MASK16;
                }
                for (argument = 0;
                     argument < DMCU_CLOCK_FORMAT_STRING_BYTES; argument++) {
                    env->clock_format_string[argument] =
                        trace_userinfo_descriptor_byte(
                            env->clock_format_core_args[4],
                            env->clock_format_core_args[5], argument);
                }
                for (argument = 0;
                     argument < DMCU_CLOCK_FORMAT_VARARG_WORDS; argument++) {
                    env->clock_format_varargs[argument] = internal_data_read(
                        (env->clock_format_core_args[6] + argument * 2u) &
                        MASK16, 16);
                }
                if (env->clock_format_core_args[4] == 0x0033u &&
                    env->clock_format_core_args[5] == 0x5ee0u) {
                    env->clock_root_core_trace_active = true;
                    env->clock_root_core_call_trace_count = 0;
                }
            }
            if (env->clock_root_core_trace_active) {
                uint32_t sequence = env->clock_root_core_call_trace_count++;
                uint32_t slot = sequence % DMCU_CLOCK_CORE_CALL_TRACE_SLOTS;

                env->clock_root_core_call_trace_from[slot] = start & MASK24;
                env->clock_root_core_call_trace_target[slot] = target & MASK24;
                env->clock_root_core_call_trace_sp[slot] =
                    env->gpr[DMCU_SP] & MASK16;
            }
            if ((start == dmcu_code_address(0x0c, 0x88e6) ||
                 start == dmcu_code_address(0x0c, 0xbbda) ||
                 start == dmcu_code_address(0x0c, 0xbc32)) &&
                target == dmcu_code_address(0x31, 0x552e)) {
                unsigned argument;

                env->clock_stream_write_calls++;
                for (argument = 0; argument < 6; argument++) {
                    env->clock_stream_write_args[argument] =
                        rom_argument(env, argument) & MASK16;
                }
            }
            if (start == dmcu_code_address(0x0c, 0x87f8) &&
                target == dmcu_code_address(0x31, 0x1122)) {
                unsigned argument;

                env->clock_scan_calls++;
                env->clock_scan_sp = env->gpr[DMCU_SP] & MASK16;
                env->clock_scan_fp = env->gpr[DMCU_FP] & MASK16;
                for (argument = 0;
                     argument < DMCU_CLOCK_SCAN_ARGUMENT_WORDS; argument++) {
                    env->clock_scan_args[argument] =
                        rom_argument(env, argument) & MASK16;
                }
            }
            if (start == dmcu_code_address(0x31, 0x5594) &&
                target == dmcu_code_address(0x22, 0xbe8a)) {
                unsigned argument;

                env->clock_stream_dispatch_calls++;
                for (argument = 0; argument < 6; argument++) {
                    env->clock_stream_dispatch_args[argument] =
                        rom_argument(env, argument) & MASK16;
                }
                for (argument = 0;
                     argument < DMCU_CLOCK_STREAM_OBJECT_BYTES; argument++) {
                    env->clock_stream_object_a[argument] =
                        trace_userinfo_descriptor_byte(
                            env->clock_stream_dispatch_args[0],
                            env->clock_stream_dispatch_args[1], argument);
                    env->clock_stream_object_b[argument] =
                        trace_userinfo_descriptor_byte(
                            env->clock_stream_dispatch_args[2],
                            env->clock_stream_dispatch_args[3], argument);
                }
            }
            if (env->clock_format_root_active &&
                start == dmcu_code_address(0x22, 0xc062) &&
                target == dmcu_code_address(0x30, 0x6490)) {
                uint32_t sequence = env->clock_stream_move_trace_count++;
                uint32_t slot = sequence %
                                DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS;
                unsigned argument;
                unsigned pointer;
                unsigned offset;

                env->clock_stream_move_trace_caller[slot] = start & MASK24;
                env->clock_stream_move_trace_sp[slot] =
                    env->gpr[DMCU_SP] & MASK16;
                env->clock_stream_move_trace_fp[slot] =
                    env->gpr[DMCU_FP] & MASK16;
                for (argument = 0;
                     argument < DMCU_CLOCK_STREAM_MOVE_ARGUMENT_WORDS;
                     argument++) {
                    env->clock_stream_move_trace_args[slot][argument] =
                        rom_argument(env, argument) & MASK16;
                }
                for (pointer = 0; pointer < 3; pointer++) {
                    for (offset = 0;
                         offset < DMCU_CLOCK_STREAM_MOVE_SAMPLE_BYTES;
                         offset++) {
                        env->clock_stream_move_trace_samples[slot]
                            [pointer][offset] =
                            trace_userinfo_descriptor_byte(
                                env->clock_stream_move_trace_args[slot]
                                    [pointer * 2u],
                                env->clock_stream_move_trace_args[slot]
                                    [pointer * 2u + 1u],
                                offset);
                    }
                }
            }
            if (env->clock_format_root_active &&
                (start == dmcu_code_address(0x30, 0x6528) ||
                 start == dmcu_code_address(0x30, 0x6572)) &&
                target == dmcu_code_address(0x2e, 0x4572)) {
                uint32_t sequence = env->clock_stream_copy_trace_count++;
                uint32_t slot = sequence %
                                DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS;
                unsigned argument;
                unsigned pointer;
                unsigned offset;

                env->clock_stream_copy_trace_caller[slot] = start & MASK24;
                env->clock_stream_copy_trace_sp[slot] =
                    env->gpr[DMCU_SP] & MASK16;
                env->clock_stream_copy_trace_fp[slot] =
                    env->gpr[DMCU_FP] & MASK16;
                for (argument = 0;
                     argument < DMCU_CLOCK_STREAM_MOVE_ARGUMENT_WORDS;
                     argument++) {
                    env->clock_stream_copy_trace_args[slot][argument] =
                        rom_argument(env, argument) & MASK16;
                }
                for (pointer = 0; pointer < 3; pointer++) {
                    for (offset = 0;
                         offset < DMCU_CLOCK_STREAM_MOVE_SAMPLE_BYTES;
                         offset++) {
                        env->clock_stream_copy_trace_samples[slot]
                            [pointer][offset] =
                            trace_userinfo_descriptor_byte(
                                env->clock_stream_copy_trace_args[slot]
                                    [pointer * 2u],
                                env->clock_stream_copy_trace_args[slot]
                                    [pointer * 2u + 1u],
                                offset);
                    }
                }
            }
            if (env->root_header_io_trace_pending &&
                start == dmcu_code_address(0x2e, 0x0b7c) &&
                target == dmcu_code_address(0x28, 0x12a4)) {
                unsigned argument;

                for (argument = 0; argument < 6; argument++) {
                    env->root_header_io_trace_service_args[argument] =
                        rom_argument(env, argument) & MASK16;
                }
            }
            if (target == dmcu_code_address(0x33, 0x0070)) {
                static unsigned text_dispatch_logs;

                if (text_dispatch_logs < 64) {
                    qemu_log_mask(
                        LOG_UNIMP,
                        "DMCU text-dispatch 33:0070 from %02x:%04x "
                        "sp=%04x fp=%04x args=%04x,%04x,%04x,%04x\n",
                        dmcu_code_segment(start), dmcu_code_pc(start),
                        env->gpr[DMCU_SP] & MASK16,
                        env->gpr[DMCU_FP] & MASK16,
                        rom_argument(env, 0), rom_argument(env, 1),
                        rom_argument(env, 2), rom_argument(env, 3));
                    text_dispatch_logs++;
                }
            }
            if (env->root_entry_frame_valid &&
                target == dmcu_code_address(0x2e, 0x0af6)) {
                uint32_t index = env->root_resource_trace_count++;

                if (index < DMCU_ROOT_RESOURCE_TRACE_SLOTS) {
                    unsigned argument;

                    env->root_resource_trace_active = index + 1u;
                    env->root_resource_trace_caller[index] = start & MASK24;
                    env->root_resource_trace_stage[index] = 1u;
                    if (!env->root_header_io_trace_captured &&
                        start == dmcu_code_address(0x1d, 0xf522)) {
                        env->root_header_io_trace_pending = true;
                        env->root_header_io_trace_start =
                            env->resource_io_calls;
                    }
                    for (argument = 0; argument < 4; argument++) {
                        env->root_resource_trace_args[index][argument] =
                            rom_argument(env, argument) & MASK16;
                    }
                } else {
                    env->root_resource_trace_active = 0;
                }
            }
            if (env->root_entry_frame_valid &&
                target == dmcu_code_address(0x18, 0x66ee)) {
                uint32_t index = env->desktop_blit_trace_count++;

                if (index < DMCU_DESKTOP_BLIT_TRACE_SLOTS) {
                    uint16_t frame = env->gpr[DMCU_FP] & MASK16;
                    unsigned argument;
                    unsigned depth;

                    env->desktop_blit_trace_caller[index] = start & MASK24;
                    env->desktop_blit_trace_sp[index] =
                        env->gpr[DMCU_SP] & MASK16;
                    env->desktop_blit_trace_fp[index] = frame;
                    for (argument = 0; argument < 6; argument++) {
                        env->desktop_blit_trace_args[index][argument] =
                            rom_argument(env, argument) & MASK16;
                    }
                    for (depth = 0;
                         depth < DMCU_START_GLYPH_TRACE_FRAMES && frame;
                         depth++) {
                        uint16_t parent = internal_data_read(frame, 16);
                        uint16_t cs = internal_data_read(
                            (frame + 2u) & MASK16, 16);
                        uint16_t pc = internal_data_read(
                            (frame + 4u) & MASK16, 16);

                        env->desktop_blit_trace_chain[index][depth] =
                            ((cs & 0xffu) << 16) | pc;
                        if (!parent || parent == frame) {
                            break;
                        }
                        frame = parent;
                    }
                }
            }
            if (target == dmcu_code_address(0x28, 0x1f08) ||
                target == dmcu_code_address(0x33, 0x0070) ||
                target == dmcu_code_address(0x2e, 0x5316)) {
                uint32_t pointer = ((rom_argument(env, 2) & 0xff) << 16) |
                                   rom_argument(env, 3);
                uint32_t text_pointer =
                    (pointer +
                     (target == dmcu_code_address(0x2e, 0x5316) ? 10 : 0)) &
                    MASK24;
                unsigned slot = env->text_trace_count % DMCU_TEXT_TRACE_SLOTS;
                unsigned byte;

                env->text_trace_pc[slot] = start & MASK24;
                env->text_trace_x[slot] = rom_argument(env, 0) & MASK16;
                env->text_trace_y[slot] = rom_argument(env, 1) & MASK16;
                env->text_trace_pointer[slot] = pointer & MASK24;
                env->text_trace_data0[slot] = 0;
                env->text_trace_data1[slot] = 0;
                for (byte = 0; byte < 8; byte++) {
                    uint32_t value = address_space_ldub(
                        &address_space_memory, (text_pointer + byte) ^ 1u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
                    uint32_t *packed = byte < 4 ?
                        &env->text_trace_data0[slot] :
                        &env->text_trace_data1[slot];

                    *packed |= value << ((byte & 3) * 8);
                }
                if ((env->text_trace_x[slot] < 60u &&
                     env->text_trace_y[slot] >= 96u) ||
                    (env->text_trace_data0[slot] & 0xffffu) == 0xaabfu) {
                    uint32_t index = env->desktop_text_trace_count++;

                    if (index < DMCU_DESKTOP_TEXT_TRACE_SLOTS) {
                        uint16_t frame = env->gpr[DMCU_FP] & MASK16;
                        unsigned depth;

                        env->desktop_text_trace_target[index] =
                            target & MASK24;
                        env->desktop_text_trace_caller[index] =
                            start & MASK24;
                        env->desktop_text_trace_x[index] =
                            env->text_trace_x[slot];
                        env->desktop_text_trace_y[index] =
                            env->text_trace_y[slot];
                        env->desktop_text_trace_pointer[index] =
                            pointer & MASK24;
                        env->desktop_text_trace_data0[index] =
                            env->text_trace_data0[slot];
                        env->desktop_text_trace_data1[index] =
                            env->text_trace_data1[slot];
                        env->desktop_text_trace_sp[index] =
                            env->gpr[DMCU_SP] & MASK16;
                        env->desktop_text_trace_fp[index] = frame;
                        for (depth = 0;
                             depth < DMCU_START_GLYPH_TRACE_FRAMES && frame;
                             depth++) {
                            uint16_t parent = internal_data_read(frame, 16);
                            uint16_t cs = internal_data_read(
                                (frame + 2u) & MASK16, 16);
                            uint16_t pc = internal_data_read(
                                (frame + 4u) & MASK16, 16);

                            env->desktop_text_trace_chain[index][depth] =
                                ((cs & 0xffu) << 16) | pc;
                            if (!parent || parent == frame) {
                                break;
                            }
                            frame = parent;
                        }
                    }
                }
                env->text_trace_count++;
                qemu_log_mask(LOG_UNIMP,
                              "DMCU text call target=%02x:%04x from %02x:%04x "
                              "x=%u y=%u pointer=%02x:%04x\n",
                              dmcu_code_segment(target), dmcu_code_pc(target),
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->text_trace_x[slot],
                              env->text_trace_y[slot],
                              dmcu_code_segment(pointer),
                              dmcu_code_pc(pointer));
            }
            if (target == dmcu_code_address(0x25, 0x6042)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU clear call 25:6042 from %02x:%04x "
                              "sp=%04x fp=%04x args=%04x,%04x,%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0), rom_argument(env, 1),
                              rom_argument(env, 2));
            }
            if (target >= dmcu_code_address(0x30, 0x8a00) &&
                target < dmcu_code_address(0x30, 0x9444)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU shared-epilogue call %02x:%04x "
                              "from %02x:%04x sp=%04x fp=%04x\n",
                              dmcu_code_segment(target),
                              dmcu_code_pc(target),
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16);
            }
            if (target >= dmcu_code_address(0x32, 0x7c00) &&
                target < dmcu_code_address(0x32, 0x8a90)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU segment-32 suspect call %02x:%04x "
                              "from %02x:%04x sp=%04x fp=%04x\n",
                              dmcu_code_segment(target),
                              dmcu_code_pc(target),
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16);
            }

            /*
             * 28:FD38 is the ordinary byte-glyph renderer used by the
             * bootstrap UI.  The hierarchy renderer also calls the resident
             * lookup/compositor at 17:9244 directly.  The recovered stream
             * menu paths call 32:7B42 with the
             * complete one- or two-byte character, or 32:7C0E for the
             * alternate character path, in argument 2 (for example GBK
             * 0xD3E9 for "娱").  Keep all three in
             * the same bounded, diagnostic-only trace so a menu run can be
             * checked for its actual guest character codes instead of merely
             * checking that the framebuffer became non-zero.
             */
            if (target == dmcu_code_address(0x17, 0x9244) ||
                target == dmcu_code_address(0x28, 0xfd38) ||
                target == dmcu_code_address(0x32, 0x7b42) ||
                target == dmcu_code_address(0x32, 0x7c0e)) {
                unsigned trace_slot = env->glyph_draw_trace_count %
                                      DMCU_GLYPH_DRAW_TRACE_SLOTS;

                env->glyph_draw_trace_caller[trace_slot] = start & MASK24;
                env->glyph_draw_trace_x[trace_slot] =
                    rom_argument(env, 0) & MASK16;
                env->glyph_draw_trace_y[trace_slot] =
                    rom_argument(env, 1) & MASK16;
                env->glyph_draw_trace_character[trace_slot] =
                    rom_argument(env, 2) & MASK16;
                env->glyph_draw_active_character =
                    env->glyph_draw_trace_character[trace_slot];
                env->glyph_draw_trace_count++;

                /*
                 * "开始" is part of the outer desktop chrome and is drawn
                 * before 2C:C9E8 resets the general menu trace rings.  Keep
                 * a separate, never-reset, bounded record for the first GBK
                 * 0xBFAA ("开") glyphs.  This is observation only: capturing
                 * the frame chain does not alter the guest call or memory.
                 */
                if ((rom_argument(env, 2) & MASK16) == 0xbfaau) {
                    uint32_t index = env->start_glyph_trace_count++;

                    if (index < DMCU_START_GLYPH_TRACE_SLOTS) {
                        uint16_t frame = env->gpr[DMCU_FP] & MASK16;
                        unsigned depth;

                        env->start_glyph_trace_caller[index] = start & MASK24;
                        env->start_glyph_trace_x[index] =
                            rom_argument(env, 0) & MASK16;
                        env->start_glyph_trace_y[index] =
                            rom_argument(env, 1) & MASK16;
                        env->start_glyph_trace_character[index] =
                            rom_argument(env, 2) & MASK16;
                        env->start_glyph_trace_sp[index] =
                            env->gpr[DMCU_SP] & MASK16;
                        env->start_glyph_trace_fp[index] = frame;
                        for (depth = 0;
                             depth < DMCU_START_GLYPH_TRACE_FRAMES && frame;
                             depth++) {
                            uint16_t parent = internal_data_read(frame, 16);
                            uint16_t cs = internal_data_read(
                                (frame + 2u) & MASK16, 16);
                            uint16_t pc = internal_data_read(
                                (frame + 4u) & MASK16, 16);

                            env->start_glyph_trace_chain[index][depth] =
                                ((cs & 0xffu) << 16) | pc;
                            if (!parent || parent == frame) {
                                break;
                            }
                            frame = parent;
                        }
                    }
                }
            }

            if (env->rom_hle_enabled &&
                np560_overlay_service(env, target)) {
                return true;
            }

            if (env->hle_ui_enabled && !execute_resident_rom &&
                target == dmcu_code_address(0x03, 0x0030) &&
                start == DMCU_PROGRAM_BASE) {
                np560_hle_start(env);
                env->pc = dmcu_code_address(0x03, 0x0032);
                return true;
            }

            if (env->rom_hle_enabled &&
                target < DMCU_PROGRAM_BASE && !execute_resident_rom &&
                !execute_auxiliary) {
                /*
                 * The NP560 mask ROM entry 03:0030 creates the outer C
                 * frame before handing control to the update image.  Its
                 * bytes are not present in NP560.PRG, so model that ABI
                 * contract and leave 03:0032 as the return-to-ROM address.
                 */
                if (target == dmcu_code_address(0x03, 0x0030) &&
                    start == DMCU_PROGRAM_BASE) {
                    uint32_t context = env->startup_context & MASK24;
                    uint32_t source = (context + 0x38) & MASK24;
                    uint32_t destination = (context + 0x30) & MASK24;

                    env->gpr[DMCU_FP] = 0xfff8;
                    env->gpr[DMCU_SP] = 0xfff8;
                    internal_data_write(0xfff4, context >> 16, 16);
                    internal_data_write(0xfff6, context & MASK16, 16);
                    internal_data_write(0xfff8, 0x0000, 16);
                    internal_data_write(0xfffa, 0x0003, 16);
                    internal_data_write(0xfffc, 0x0032, 16);
                    /* 33:4F50 is a compiler-created mid-function entry. */
                    env->gpr[0] = source >> 16;
                    env->gpr[1] = (source << 1) & MASK16;
                    env->shift_buffer = (source >> 15) & 1;
                    env->gpr[2] = destination >> 16;
                    env->gpr[3] = destination & MASK16;
                }
                if (target == dmcu_code_address(0x17, 0x9244)) {
                    env->rom_probe_calls++;
                    env->rom_probe_target = target;
                    env->rom_probe_args[0] = rom_argument(env, 0);
                    env->rom_probe_args[1] = rom_argument(env, 1);
                    env->rom_probe_args[2] = rom_argument(env, 2);
                    qemu_log_mask(LOG_UNIMP,
                                  "DMCU ROM 17:9244 args=%04x,%04x,%04x "
                                  "caller=%02x:%04x\n",
                                  env->rom_probe_args[0],
                                  env->rom_probe_args[1],
                                  env->rom_probe_args[2], start >> 16,
                                  start & MASK16);
                }
                if (!np560_rom_service(env, target, next)) {
                    qemu_log_mask(LOG_UNIMP,
                                  "DMCU ROM service stub %02x:%04x\n",
                                  arg, ext);
                }
                return true;
            }
            if (!env->rom_hle_enabled && target < DMCU_PROGRAM_BASE &&
                !execute_auxiliary &&
                (!execute_resident_rom || env->soc_rom_skeleton)) {
                trace_rom_call(env, target, start, next, true);
            }
            /* The reconstructed post-initializer loader in free resident
             * segment 09 installs the recovered program overlays immediately before
             * entering either the source-position 20:026A dispatcher or its
             * factory-linked 03:026A resident copy.  Those
             * writes use the DMCU data AddressSpace, while instruction fetches
             * use the separate code AddressSpace.  Hardware observes them
             * coherently; discard any flat-image TBs translated before the
             * loader completed so the first instruction at each destination
             * also comes from the installed overlay. */
            if ((target == dmcu_code_address(0x20, 0x026a) ||
                 target == dmcu_code_address(0x03, 0x026a)) &&
                dmcu_code_segment(start) == 0x09) {
                env->overlay_code_syncs++;
                tb_flush(env_cpu(env));
                tlb_flush(env_cpu(env));
                qemu_log_mask(LOG_UNIMP,
                              "DMCU post-initializer overlay code sync "
                              "caller=%02x:%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start));
            }
            far_return_push(env, next);
        }
        env->pc = target & MASK24;
        return true;
    }
    if (op == 0xcc || op == 0xce) {
        if (condition(env, arg >> 4)) {
            if (op == 0xcc) {
                near_return_push(env, next);
            }
            env->pc = near_pc(start, data_read(env, env->gpr[arg & 15], 16));
        }
        return true;
    }
    if (op == 0xcd) {
        near_return_push(env, next);
        env->pc = near_pc(start,
                          (dmcu_code_pc(next) + sext8(arg) * 2) & MASK16);
        return true;
    }
    if (op >= 0xd0 && op <= 0xde) {
        if (condition(env, op & 15)) {
            env->pc = near_pc(start,
                              (dmcu_code_pc(next) + sext8(arg) * 2) & MASK16);
        }
        return true;
    }
    if (op >= 0x9a && op <= 0x9d) {
        unsigned bitno = (ext >> 8) & 15;
        bool value = bit_read(env, arg, bitno);
        bool take = (op == 0x9a || op == 0x9c) ? value : !value;
        if (take) {
            if (op == 0x9c) { bit_write(env, arg, bitno, false); }
            if (op == 0x9d) { bit_write(env, arg, bitno, true); }
            env->pc = near_pc(start,
                              (dmcu_code_pc(next) + sext8(ext) * 2) & MASK16);
        }
        return true;
    }
    if (op == 0xc6) {
        if (arg == 0x00) {
            env->pc = near_return_pop(env);
        } else if (arg == 0x20) {
            uint32_t return_sp = env->gpr[DMCU_SP] & MASK16;

            if (start == dmcu_code_address(0x14, 0x65e8) &&
                hardware_init_return_watch_active) {
                env->hardware_init_return_exits++;
                env->hardware_init_return_exit[0] =
                    internal_data_read(hardware_init_return_watch_base, 16);
                env->hardware_init_return_exit[1] =
                    internal_data_read(
                        (hardware_init_return_watch_base + 2u) & MASK16, 16);
                env->hardware_init_return_exit_sp = return_sp;
                env->hardware_init_return_exit_fp =
                    env->gpr[DMCU_FP] & MASK16;
                env->hardware_init_return_exit_valid = true;
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU hardware-init return watch exit "
                    "watch=%04x values=%04x,%04x sp=%04x fp=%04x "
                    "writes=%u\n",
                    hardware_init_return_watch_base,
                    internal_data_read(hardware_init_return_watch_base, 16),
                    internal_data_read(
                        (hardware_init_return_watch_base + 2u) & MASK16, 16),
                    return_sp, env->gpr[DMCU_FP] & MASK16,
                    hardware_init_return_watch_writes);
                hardware_init_return_watch_active = false;
            }

            if (start == dmcu_code_address(0x33, 0x094e) ||
                start == dmcu_code_address(0x33, 0x6e62) ||
                start == dmcu_code_address(0x33, 0x00a6)) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU storage callback return %02x:%04x r0=%04x "
                    "sp=%04x fp=%04x to=%02x:%04x\n",
                    dmcu_code_segment(start), dmcu_code_pc(start),
                    env->gpr[0] & MASK16, return_sp,
                    env->gpr[DMCU_FP] & MASK16,
                    internal_data_read(return_sp, 16) & 0xff,
                    internal_data_read((return_sp + 2) & MASK16, 16));
            }
            if (start == dmcu_code_address(0x2c, 0xffde) ||
                start == dmcu_code_address(0x31, 0xcc82) ||
                start == dmcu_code_address(0x27, 0x850a) ||
                start == dmcu_code_address(0x32, 0x6f10) ||
                start == dmcu_code_address(0x32, 0x6f7a) ||
                start == dmcu_code_address(0x2e, 0xc26c) ||
                start == dmcu_code_address(0x2c, 0x30ba) ||
                start == dmcu_code_address(0x2a, 0x16c0) ||
                start == dmcu_code_address(0x2e, 0xc102) ||
                start == dmcu_code_address(0x29, 0x0884)) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU storage worker return %02x:%04x r0=%04x "
                    "r1=%04x sp=%04x fp=%04x to=%02x:%04x\n",
                    dmcu_code_segment(start), dmcu_code_pc(start),
                    env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                    return_sp, env->gpr[DMCU_FP] & MASK16,
                    internal_data_read(return_sp, 16) & 0xff,
                    internal_data_read((return_sp + 2) & MASK16, 16));
            }
            if (start == dmcu_code_address(0x27, 0x850a)) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU FTL logical lookup return result=%04x "
                    "map-block=%04x range=%04x..%04x ready=%04x "
                    "entry0=%04x:%04x\n",
                    env->gpr[0] & MASK16,
                    internal_data_read(0x04e4, 16),
                    internal_data_read(0x027e, 16),
                    internal_data_read(0x0280, 16),
                    internal_data_read(0x0284, 16),
                    internal_data_read(0x0286, 16),
                    internal_data_read(0x0288, 16));
            }
            if (start == dmcu_code_address(0x2c, 0x30ba)) {
                unsigned index;

                qemu_log_mask(LOG_UNIMP,
                              "DMCU storage descriptor after sector read=");
                for (index = 0; index < 16; index++) {
                    qemu_log_mask(
                        LOG_UNIMP, "%s%04x", index ? "," : "",
                        address_space_lduw_le(
                            &address_space_memory,
                            0x00511a40u + index * 2,
                            MEMTXATTRS_UNSPECIFIED, NULL));
                }
                qemu_log_mask(LOG_UNIMP, "\n");
            }
            if (start == dmcu_code_address(0x18, 0xfff8)) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU resident storage unit init return "
                    "r0=%04x status=%04x sp=%04x fp=%04x "
                    "to=%02x:%04x rec0=%04x:%04x rec2=%04x:%04x\n",
                    env->gpr[0] & MASK16,
                    address_space_lduw_le(
                        &address_space_memory, 0x00512ae0u,
                        MEMTXATTRS_UNSPECIFIED, NULL),
                    return_sp, env->gpr[DMCU_FP] & MASK16,
                    internal_data_read(return_sp, 16) & 0xff,
                    internal_data_read((return_sp + 2) & MASK16, 16),
                    address_space_lduw_le(
                        &address_space_memory, 0x005127a4u,
                        MEMTXATTRS_UNSPECIFIED, NULL),
                    address_space_lduw_le(
                        &address_space_memory, 0x005127a6u,
                        MEMTXATTRS_UNSPECIFIED, NULL),
                    address_space_lduw_le(
                        &address_space_memory, 0x005127f0u,
                        MEMTXATTRS_UNSPECIFIED, NULL),
                    address_space_lduw_le(
                        &address_space_memory, 0x005127f2u,
                        MEMTXATTRS_UNSPECIFIED, NULL));
            }
            if (start == dmcu_code_address(0x2d, 0x3536) ||
                start == dmcu_code_address(0x2d, 0x35ae)) {
                qemu_log_mask(
                    LOG_UNIMP,
                    "DMCU storage driver indirect call at %02x:%04x "
                    "target=%04x:%04x sp=%04x fp=%04x "
                    "index=%02x ds0=%03x ds1=%03x root=%04x:%04x "
                    "record0=%04x:%04x\n",
                    dmcu_code_segment(start), dmcu_code_pc(start),
                    internal_data_read(return_sp, 16) & 0xff,
                    internal_data_read((return_sp + 2) & MASK16, 16),
                    return_sp, env->gpr[DMCU_FP] & MASK16,
                    internal_data_read(
                        (env->gpr[DMCU_FP] + 6) & MASK16, 8) & 0xff,
                    env->sfr[DMCU_SFR_DS0] & 0x1ff,
                    env->sfr[DMCU_SFR_DS1] & 0x1ff,
                    address_space_lduw_le(
                        &address_space_memory, 0x005129c4u,
                        MEMTXATTRS_UNSPECIFIED, NULL),
                    address_space_lduw_le(
                        &address_space_memory, 0x005129c6u,
                        MEMTXATTRS_UNSPECIFIED, NULL),
                    address_space_lduw_le(
                        &address_space_memory, 0x005127a4u,
                        MEMTXATTRS_UNSPECIFIED, NULL),
                    address_space_lduw_le(
                        &address_space_memory, 0x005127a6u,
                        MEMTXATTRS_UNSPECIFIED, NULL));
            }

            if (start == dmcu_code_address(0x33, 0x6f34)) {
                env->post_registry_hook_returns++;
                env->post_registry_hook_return_sp = return_sp;
                env->post_registry_hook_return_word0 =
                    internal_data_read(return_sp, 16);
                env->post_registry_hook_return_word1 =
                    internal_data_read((return_sp + 2) & MASK16, 16);
            }

            if (start >= dmcu_code_address(0x03, 0x1f00) &&
                start < dmcu_code_address(0x03, 0x1f80)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU clear RETS at %02x:%04x sp=%04x "
                              "fp=%04x stack=%04x,%04x\n",
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              env->gpr[DMCU_SP] & MASK16,
                              env->gpr[DMCU_FP] & MASK16,
                              rom_argument(env, 0), rom_argument(env, 1));
            }
            env->pc = far_return_pop(env);
            /*
             * The resident 06:5800 cleanup has just copied the original
             * application body back over the temporary 2D:3460 bootstrap
             * storage resolver.  Data and code are coherent on the DMCU;
             * synchronize QEMU's separate code AddressSpace before the
             * application can branch into that retired overlay range.
             */
            if (start == dmcu_code_address(0x06, 0x5832)) {
                env->overlay_code_syncs++;
                tb_flush(env_cpu(env));
                tlb_flush(env_cpu(env));
                qemu_log_mask(LOG_UNIMP,
                              "DMCU storage overlay retired; code sync "
                              "return=%02x:%04x\n",
                              dmcu_code_segment(env->pc),
                              dmcu_code_pc(env->pc));
            }
            /* The clean-room resident manager installs the exact source-50
             * 33:3CA6/33:3CC6 launch sequence and the complete source-4E
             * 31:4974 work-table creator.  Their data/code aliases share RAM,
             * but a stale TCG translation may still name the previous flat
             * bodies.  The physical DMCU instruction view is coherent, so
             * synchronize at the guest installer's evidenced RETS boundary. */
            if (start == dmcu_code_address(0x06, 0x1c36)) {
                env->overlay_code_syncs++;
                tb_flush(env_cpu(env));
                tlb_flush(env_cpu(env));
            }
            /* The recovered 1F:F000 resident installer writes the four tiny
             * source-50 hardware-bit wrappers and then calls the 1F:A000
             * sub-installer for the exact 30:3A56 list-item setter.  Those
             * stores arrive through the DMCU data view, while TCG may already
             * hold translations from the separate code view.  Real code RAM
             * is coherent, so make all guest writes visible at the expanded
             * installer's final RETS, before the menu calls these routines. */
            if (start == dmcu_code_address(0x1f, 0xf094)) {
                env->overlay_code_syncs++;
                tb_flush(env_cpu(env));
                tlb_flush(env_cpu(env));
                qemu_log_mask(LOG_UNIMP,
                              "DMCU menu late-wrapper code sync\n");
            }
            /* The resident 1A:5500 installer writes the exact source-50
             * foreground state wrappers into 33:3C86..3EE4.  Data and code
             * alias the same physical RAM on the DMCU, but TCG can retain a
             * translation made from the flat image before those guest stores.
             * Synchronize at the installer's balanced RETS so state 0x01 sees
             * the newly installed wrapper rather than the stale long body. */
            if (start == dmcu_code_address(0x1a, 0x5e84)) {
                env->overlay_code_syncs++;
                tb_flush(env_cpu(env));
                tlb_flush(env_cpu(env));
                qemu_log_mask(LOG_UNIMP,
                              "DMCU foreground state wrapper code sync\n");
            }
            /* The late 1A:0000 application-region installer writes a large
             * set of recovered routines through the DMCU data alias.  The
             * real SoC exposes coherent program RAM, but QEMU can retain a
             * translation made from the previous code view.  This matters
             * for the relocated 5F:1A5A numeric leaf: the data diagnostic
             * already reads its installed RETS while a stale TB continues
             * into the old 5F:1BBA body.  Synchronize at the installer's
             * balanced RETS, before any caller can enter the new overlays. */
            if (start == dmcu_code_address(0x1a, 0x41f4)) {
                env->overlay_code_syncs++;
                tb_flush(env_cpu(env));
                tlb_flush(env_cpu(env));
                qemu_log_mask(LOG_UNIMP,
                              "DMCU late application overlay code sync\n");
            }
            /* The recovered generic-menu manager performs another coherent
             * RAM-to-RAM overlay exchange after the bootstrap foreground has
             * retired.  In particular it replaces 2C:C9E8 and 32:AF98 at
             * 06:1D40..20:9A.  Flush at that guest RETS boundary so QEMU does
             * not execute a TCG block translated from the previous overlay. */
            if (start == dmcu_code_address(0x06, 0x209a)) {
                env->overlay_code_syncs++;
                /* The physical DMCU has a coherent instruction view.  A
                 * complete synchronization here also prevents a target whose
                 * old TB began outside one of the narrow written ranges from
                 * retaining foreground code after the manager exchange. */
                tb_flush(env_cpu(env));
                /* Invalidate only the ranges written by 06:1D40.  Other
                 * foreground overlays are intentionally still live here;
                 * flushing every TB would expose those unrelated mutable
                 * RAM slots before the resident manager restores them. */
                tb_invalidate_phys_range(0x200b82u, 0x201619u);
                tb_invalidate_phys_range(0x31138cu, 0x311459u);
                tb_invalidate_phys_range(0x2a0514u, 0x2a079bu);
                tb_invalidate_phys_range(0x2fe4c8u, 0x2fe5ebu);
                tb_invalidate_phys_range(0x32af98u, 0x32afedu);
                tb_invalidate_phys_range(0x2f8e8eu, 0x2f8fc5u);
                tb_invalidate_phys_range(0x2f8fc6u, 0x2f90fdu);
                tb_invalidate_phys_range(0x2fc216u, 0x2fc341u);
                tb_invalidate_phys_range(0x2cd350u, 0x2cd52fu);
                tb_invalidate_phys_range(0x156c56u, 0x157b73u);
                tb_invalidate_phys_range(0x2ffa32u, 0x2ffb4fu);
                tb_invalidate_phys_range(0x2cc9e8u, 0x2ccbc9u);
                tb_invalidate_phys_range(0x2be3e6u, 0x2be5fdu);
                tb_invalidate_phys_range(0x31aa5cu, 0x31aaffu);
                tb_invalidate_phys_range(0x2a322au, 0x2a34a5u);
                tb_invalidate_phys_range(0x326f7cu, 0x326fe5u);
                tb_invalidate_phys_range(0x32125cu, 0x3212e3u);
                tb_invalidate_phys_range(0x30d270u, 0x30d34fu);
                tb_invalidate_phys_range(0x2fc342u, 0x2fc46du);
                tb_invalidate_phys_range(0x295126u, 0x2953e7u);
                tb_invalidate_phys_range(0x3366d8u, 0x3366e1u);
                tb_invalidate_phys_range(0x3351e0u, 0x335204u);
                tb_invalidate_phys_range(0x2577dau, 0x257bc2u);
                tb_invalidate_phys_range(0x27e07eu, 0x27e201u);
                tb_invalidate_phys_range(0x28dda6u, 0x28e087u);
                tb_invalidate_phys_range(0x300b0cu, 0x300c23u);
                tb_invalidate_phys_range(0x30251eu, 0x302630u);
                tb_invalidate_phys_range(0x33197au, 0x3319a8u);
                tb_invalidate_phys_range(0x315300u, 0x3153bau);
                tb_invalidate_phys_range(0x334e5eu, 0x334e74u);
                tb_invalidate_phys_range(0x33468cu, 0x3346a2u);
                tb_invalidate_phys_range(0x334d2au, 0x334d40u);
                tb_invalidate_phys_range(0x3365fcu, 0x336606u);
                tb_invalidate_phys_range(0x32cc9cu, 0x32cce8u);
                tb_invalidate_phys_range(0x3365d4u, 0x3365deu);
                tb_invalidate_phys_range(0x2fd266u, 0x2fd38eu);
                tb_invalidate_phys_range(0x334ddau, 0x334df0u);
                tb_invalidate_phys_range(0x330edcu, 0x330f0eu);
            }
            /*
             * The reconstructed 01:0200 resident loader installs writable
             * program overlays through the DMCU data address space, then
             * returns to the shipped startup code at 20:031C.  Both address
             * spaces alias the same RAMBlock, but TCG translations created
             * through the separate code AddressSpace are not invalidated by
             * every data-side alias write.  The hardware has a coherent
             * instruction view, so synchronize once at this evidenced loader
             * boundary before the application executes the new entries.
             */
            if (dmcu_code_segment(start) == 0x01 &&
                env->pc == dmcu_code_address(0x20, 0x031c)) {
                env->overlay_code_syncs++;
                tb_flush(env_cpu(env));
                tlb_flush(env_cpu(env));
            }
            if (start == dmcu_code_address(0x33, 0x6f34)) {
                env->post_registry_hook_return_pc = env->pc & MASK24;
            }
            if (start == dmcu_code_address(0x28, 0x8396) ||
                start == dmcu_code_address(0x28, 0x8480) ||
                start == dmcu_code_address(0x28, 0x856a)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU application callback %02x:%04x "
                              "selected at %02x:%04x sp=%04x fp=%04x\n",
                              dmcu_code_segment(env->pc),
                              dmcu_code_pc(env->pc),
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              return_sp, env->gpr[DMCU_FP] & MASK16);
            }
            if (dmcu_code_segment(env->pc) == 0x10) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU RETS entered segment 10 at %02x:%04x "
                              "from %02x:%04x sp-before=%04x "
                              "return-frame=%04x,%04x "
                              "below=%04x,%04x,%04x,%04x fp=%04x\n",
                              dmcu_code_segment(env->pc),
                              dmcu_code_pc(env->pc),
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              return_sp,
                              internal_data_read(return_sp, 16),
                              internal_data_read((return_sp + 2) & MASK16, 16),
                              internal_data_read((return_sp + 4) & MASK16, 16),
                              internal_data_read((return_sp + 6) & MASK16, 16),
                              internal_data_read((return_sp + 8) & MASK16, 16),
                              internal_data_read((return_sp + 10) & MASK16, 16),
                              env->gpr[DMCU_FP] & MASK16);
            }
            if (env->pc >= dmcu_code_address(0x05, 0x0000) &&
                env->pc < dmcu_code_address(0x05, 0x5000)) {
                qemu_log_mask(LOG_UNIMP,
                              "DMCU RETS entered resident loader %02x:%04x "
                              "from %02x:%04x "
                              "sp=%04x frame=%04x,%04x fp=%04x\n",
                              dmcu_code_segment(env->pc),
                              dmcu_code_pc(env->pc),
                              dmcu_code_segment(start), dmcu_code_pc(start),
                              return_sp,
                              internal_data_read(return_sp, 16),
                              internal_data_read((return_sp + 2) & MASK16, 16),
                              env->gpr[DMCU_FP] & MASK16);
            }
        } else if (arg == 0x10) {
            uint32_t cs;
            uint32_t pc;
            uint32_t frame_sp = env->gpr[DMCU_SP] & MASK16;

            env->psw = pop(env) & 15;
            cs = pop(env);
            pc = pop(env);
            env->pc = dmcu_code_address(cs, pc);
            /*
             * The NP560 timer vector at 08:41E0 deliberately uses RETI to
             * enter its application callback from a synthetic interrupt
             * frame.  The original hardware interrupt remains active until
             * the callback returns to the vector epilogue and that epilogue
             * executes its second RETI.  Clearing in_interrupt here allowed
             * the 64 Hz source to nest while the vector's single save area
             * (08:049A..04D8) was still live, eventually corrupting the
             * interrupted PC to 00:0000.
             */
            if (env->in_interrupt &&
                start != dmcu_code_address(0x08, 0x41e0)) {
                if (env->interrupt_repeat_saved) {
                    if (env->interrupt_repeat_pc ==
                            dmcu_code_address(0x2e, 0x46bc) &&
                        env->interrupt_repeat_end ==
                            dmcu_code_address(0x2e, 0x46c0)) {
                        unsigned int i;
                        uint32_t mismatch = 0;

                        env->far_copy_repeat_restores++;
                        env->far_copy_repeat_return_pc = env->pc & MASK24;
                        env->far_copy_repeat_restore_ds0 =
                            env->sfr[DMCU_SFR_DS0] & 0x1ff;
                        env->far_copy_repeat_restore_ds1 =
                            env->sfr[DMCU_SFR_DS1] & 0x1ff;
                        for (i = 0; i < 16; i++) {
                            env->far_copy_repeat_restore_gpr[i] =
                                env->gpr[i] & MASK16;
                            if (env->far_copy_repeat_restore_gpr[i] !=
                                env->far_copy_repeat_saved_gpr[i]) {
                                mismatch |= 1u << i;
                            }
                        }
                        env->far_copy_repeat_gpr_mismatch_mask = mismatch;
                    }
                    if (env->repeat_count) {
                        env->interrupt_repeat_conflicts++;
                    }
                    env->repeat_pc = env->interrupt_repeat_pc;
                    env->repeat_end = env->interrupt_repeat_end;
                    env->repeat_count = env->interrupt_repeat_count;
                    env->repeat_block = env->interrupt_repeat_block;
                    env->interrupt_repeat_saved = false;
                    env->interrupt_repeat_restores++;
                }
                env->in_interrupt = false;
                env->interrupt_returns++;
                env->interrupt_last_return_from = start & MASK24;
                env->interrupt_last_return_pc = env->pc & MASK24;
                env->interrupt_last_return_sp =
                    env->gpr[DMCU_SP] & MASK16;
                if ((env->pc & MASK24) !=
                        (env->interrupt_last_entry_pc & MASK24) ||
                    frame_sp != (env->interrupt_frame_base & MASK16)) {
                    if (!env->interrupt_bad_returns) {
                        env->interrupt_first_bad_from = start & MASK24;
                        env->interrupt_first_bad_sp =
                            env->gpr[DMCU_SP] & MASK16;
                        env->interrupt_first_bad_entry_pc =
                            env->interrupt_last_entry_pc & MASK24;
                        env->interrupt_first_bad_entry_sp =
                            env->interrupt_last_entry_sp & MASK16;
                        env->interrupt_first_bad_return_pc =
                            env->pc & MASK24;
                        env->interrupt_first_bad_frame_sp =
                            frame_sp & MASK16;
                        env->interrupt_first_bad_frame_base =
                            env->interrupt_frame_base & MASK16;
                    }
                    env->interrupt_bad_returns++;
                }
                env->interrupt_frame_watch_active = false;
            }
        } else {
            return false;
        }
        return true;
    }
    return false;
}

static bool exec_compare_update(CPUDMCUState *env, uint8_t op,
                                uint8_t arg, uint16_t ext)
{
    int delta;
    uint32_t left, right;

    switch (op) {
    case 0x4e: delta = -1; break;
    case 0x5e: delta = -2; break;
    case 0x4f: delta = 1; break;
    case 0x5f: delta = 2; break;
    case 0x6e: case 0x8e: delta = -1; break;
    case 0x7e: case 0x9e: delta = -2; break;
    case 0x6f: case 0x8f: delta = 1; break;
    case 0x7f: case 0x9f: delta = 2; break;
    default: return false;
    }

    if (op < 0x60) {
        left = reg_read(env, arg >> 4, 16);
        right = arg & 15;
        alu_sub(env, left, right, 0, 16, false);
        reg_write(env, arg >> 4, left + delta, 16);
    } else {
        left = sfr_read(env, arg, 16);
        right = op < 0x80 ? ext : data_read(env, ext, 16);
        alu_sub(env, left, right, 0, 16, false);
        sfr_write(env, arg, left + delta, 16);
    }
    return true;
}

static bool exec_divide(CPUDMCUState *env, uint8_t op, uint8_t arg)
{
    uint32_t divisor = reg_read(env, arg, 16);
    int64_t squot = 0, srem = 0;
    uint64_t uquot = 0, urem = 0;
    bool overflow = false;
    bool is_signed;

    if (op < 0xc2 || op > 0xc5 || (arg >> 4) != 0) {
        return false;
    }
    is_signed = op == 0xc2 || op == 0xc4;
    if (divisor == 0) {
        overflow = true;
    } else if (is_signed) {
        int64_t dividend = op == 0xc2 ? sext16(env->gpr[7])
            : (int32_t)((env->gpr[6] << 16) | env->gpr[7]);
        int64_t signed_divisor = sext16(divisor);
        squot = dividend / signed_divisor;
        srem = dividend % signed_divisor;
        overflow = squot < INT16_MIN || squot > INT16_MAX;
    } else {
        uint64_t dividend = op == 0xc3 ? env->gpr[7] & MASK16
            : ((env->gpr[6] & MASK16) << 16) | (env->gpr[7] & MASK16);
        uquot = dividend / divisor;
        urem = dividend % divisor;
        overflow = uquot > UINT16_MAX;
    }

    set_flag(env, DMCU_PSW_C, false);
    set_flag(env, DMCU_PSW_V, overflow);
    if (!overflow) {
        uint32_t quotient = is_signed ? squot : uquot;
        env->gpr[7] = quotient & MASK16;
        env->gpr[6] = (is_signed ? srem : urem) & MASK16;
        set_flag(env, DMCU_PSW_Z, (quotient & MASK16) == 0);
        set_flag(env, DMCU_PSW_N, quotient & 0x8000);
    }
    return true;
}

static bool exec_exponent(CPUDMCUState *env, uint8_t op, uint8_t arg)
{
    unsigned kind, count = 0;
    uint32_t value, temp;
    bool indirect, block, signed_value;

    if (op != 0x1e || (arg >> 4) > 7) {
        return false;
    }
    kind = arg >> 4;
    indirect = kind & 1;
    block = kind >= 4;
    signed_value = kind < 2 || (kind >= 4 && kind < 6);
    if (indirect) {
        uint32_t addr = env->gpr[arg & 15];
        value = pointer_read(env, arg & 15, addr, 16);
        env->gpr[arg & 15] = (addr + 2) & MASK16;
    } else {
        value = reg_read(env, arg, 16);
    }

    temp = value;
    if (signed_value) {
        unsigned sign = temp >> 15;
        while (count < 16 && (temp >> 15) == sign) {
            temp = (temp << 1) & MASK16;
            count++;
        }
        count--;
    } else {
        while (count < 16 && !(temp & 0x8000)) {
            temp = (temp << 1) & MASK16;
            count++;
        }
    }
    if (!block || reg_read(env, 10, 8) > count) {
        reg_write(env, 10, count, 8);
    }
    set_flag(env, DMCU_PSW_Z, value == 0);
    set_flag(env, DMCU_PSW_C, false);
    set_flag(env, DMCU_PSW_N, false);
    set_flag(env, DMCU_PSW_V, false);
    return true;
}

uint32_t HELPER(exec)(CPUDMCUState *env, uint32_t word0, uint32_t word1)
{
    static unsigned resident_allocator_trace_steps;
    static unsigned result_heap_failure_logs;
    static unsigned result_heap_return_logs;
    static unsigned storage_sector_probe_trace_steps;
    static unsigned application_input_callback_trace_steps;
    static unsigned resource_data_control_entries;
    static unsigned menu_result_data_control_entries;
    static unsigned application_resource_paging_trace_steps;
    static unsigned resource_geometry_trace_steps;
    static unsigned application_scanner_gate_steps;
    static unsigned state50_outer_entries;
    static bool state50_branch_trace_active;
    static unsigned state50_branch_trace_steps;
    static unsigned resident_event_path_trace_steps;
    uint8_t op = word0 >> 8;
    uint8_t arg = word0;
    uint16_t ext = word1;
    uint32_t start = env->pc & MASK24;
    uint32_t next = (start + dmcu_insn_size(word0)) & MASK24;
    uint32_t value, left, right;
    uint32_t old_sp = env->gpr[DMCU_SP] & MASK16;
    uint32_t old_fp = env->gpr[DMCU_FP] & MASK16;
    uint32_t old_ds0 = env->sfr[DMCU_SFR_DS0] & 0x1ff;
    uint32_t old_ds1 = env->sfr[DMCU_SFR_DS1] & 0x1ff;
    bool was_ignoring_ds = env->ignore_ds_count != 0;
    bool was_critical = env->critical_count != 0;
    bool address_space_changed;
    bool execute_resident_rom =
        start >= env->resident_rom_base && start < env->resident_rom_limit;
    bool execute_auxiliary =
        start >= env->auxiliary_code_base && start < env->auxiliary_code_limit;
    bool skeleton_hole = env->soc_rom_skeleton && execute_resident_rom &&
                         word0 == 0x0f00;
    unsigned trace_slot = env->exec_trace_count % DMCU_EXEC_TRACE_WORDS;

    /* Data helpers run after env->pc has advanced to the fall-through PC.
     * Keep the actual instruction start separately so watchpoints can report
     * both the writer and its next PC without a two-byte ambiguity. */
    env->current_instruction_pc = start;

    if (env->file_component_watch_active && start == 0x28daacu) {
        uint16_t component_fp = env->file_component_entry_fp;

        env->file_component_arg_daac_hi =
            internal_data_read((component_fp + 0x0au) & MASK16, 16);
        env->file_component_arg_daac_lo =
            internal_data_read((component_fp + 0x0cu) & MASK16, 16);
        env->file_component_daac_irq = env->interrupt_entries;
    }
    if (env->file_component_watch_active && start == 0x28dac2u) {
        uint16_t component_fp = env->file_component_entry_fp;

        env->file_component_arg_rets_hi =
            internal_data_read((component_fp + 0x0au) & MASK16, 16);
        env->file_component_arg_rets_lo =
            internal_data_read((component_fp + 0x0cu) & MASK16, 16);
        env->file_component_result_rets_hi = env->gpr[0] & MASK16;
        env->file_component_result_rets_lo = env->gpr[1] & MASK16;
        env->file_component_rets_irq = env->interrupt_entries;
    }

    /* Bounded path trace for the exact 29:3DD2 resident event selector.
     * Post-return snapshots can be misleading when the 64 Hz interrupt
     * changes a flag or countdown between the deciding load and RETS.  Log
     * only the first few passes through the two modal-exit predicates, before
     * each instruction executes.  This is diagnostic-only: no register,
     * condition flag, data selector, memory value, or control flow changes. */
    if (start >= 0x293ddcu && start <= 0x29408cu &&
        resident_event_path_trace_steps < 96u &&
        (start == 0x293ddcu || start == 0x293de0u ||
         start == 0x293de2u || start == 0x293de4u ||
         start == 0x293deau || start == 0x293deeu ||
         start == 0x293df0u || start == 0x293e2eu ||
         start == 0x29408cu)) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU resident-event path #%u pc=%02x:%04x "
            "r0=%04x psw=%04x ds0=%03x ign=%u "
            "flags=%04x timers=%04x,%04x,%04x\n",
            resident_event_path_trace_steps + 1,
            dmcu_code_segment(start), dmcu_code_pc(start),
            env->gpr[0] & MASK16, env->psw & MASK16,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->ignore_ds_count,
            address_space_lduw_le(&address_space_memory, 0x512a4eu,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory,
                                  DMCU_UNBANKED_LOW_PAGE_BASE + 0x0494u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory,
                                  DMCU_UNBANKED_LOW_PAGE_BASE + 0x0496u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory,
                                  DMCU_UNBANKED_LOW_PAGE_BASE + 0x0498u,
                                  MEMTXATTRS_UNSPECIFIED, NULL));
        resident_event_path_trace_steps++;
    }

    if (start == dmcu_code_address(0x14, 0x65ce)) {
        hardware_init_return_watch_base = old_sp;
        hardware_init_return_watch_active = true;
        hardware_init_return_watch_writes = 0;
        env->hardware_init_return_entries++;
        env->hardware_init_return_base = old_sp;
        env->hardware_init_return_initial[0] =
            internal_data_read(old_sp, 16);
        env->hardware_init_return_initial[1] =
            internal_data_read((old_sp + 2u) & MASK16, 16);
        env->hardware_init_return_entry_previous_pc =
            env->completed_instruction_pc & MASK24;
        env->hardware_init_return_entry_previous_next_pc =
            env->completed_instruction_next_pc & MASK24;
        env->hardware_init_return_entry_previous_word =
            env->completed_instruction_word & MASK16;
        env->hardware_init_return_entry_previous_ext =
            env->completed_instruction_ext & MASK16;
        env->hardware_init_return_entry_sp = old_sp;
        env->hardware_init_return_entry_fp = old_fp;
        env->hardware_init_return_writes = 0;
        env->hardware_init_return_first_valid = false;
        env->hardware_init_return_exit_valid = false;
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU hardware-init return watch entry #%u "
            "previous=%02x:%04x>%02x:%04x/%04x,%04x "
            "watch=%04x values=%04x,%04x sp=%04x fp=%04x\n",
            ++hardware_init_return_watch_entries,
            dmcu_code_segment(env->hardware_init_return_entry_previous_pc),
            dmcu_code_pc(env->hardware_init_return_entry_previous_pc),
            dmcu_code_segment(
                env->hardware_init_return_entry_previous_next_pc),
            dmcu_code_pc(env->hardware_init_return_entry_previous_next_pc),
            env->hardware_init_return_entry_previous_word & MASK16,
            env->hardware_init_return_entry_previous_ext & MASK16,
            hardware_init_return_watch_base,
            env->hardware_init_return_initial[0] & MASK16,
            env->hardware_init_return_initial[1] & MASK16,
            old_sp, old_fp);
    }

    /* Exact recovered-code milestones around the 2A48 startup latch. */
    switch (start) {
    case 0x084360u: env->usb_boot_milestone_calls[0]++; break;
    case 0x229b1cu: env->usb_boot_milestone_calls[1]++; break;
    case 0x2f3adeu: env->usb_boot_milestone_calls[2]++; break;
    case 0x2f3b04u: env->usb_boot_milestone_calls[3]++; break;
    case 0x2f3b2au: env->usb_boot_milestone_calls[4]++; break;
    default: break;
    }

    /*
     * 47:D374 is the application storage-record lookup used by 18:F97C to
     * read LBA 0, extract the MBR partition start, and then read that VBR.
     * Keep a dedicated trace while the root-object constructor is active so
     * unrelated later file I/O cannot evict the evidence from a generic
     * callback ring.  Every field below is observational: no guest register,
     * stack word, buffer byte, or return value is changed.
     */
    if (env->root_object_init_calls > env->root_object_init_returns) {
        if (start == dmcu_code_address(0x2a, 0xd374)) {
            uint32_t sequence = env->storage_lookup_trace_count++;
            uint32_t slot = sequence % DMCU_STORAGE_LOOKUP_TRACE_SLOTS;
            uint16_t unit = internal_data_read((old_sp + 4u) & MASK16, 16);
            uint32_t record_base =
                ((uint32_t)address_space_lduw_le(
                    &address_space_memory, 0x005129c4u,
                    MEMTXATTRS_UNSPECIFIED, NULL) << 16) |
                address_space_lduw_le(
                    &address_space_memory, 0x005129c6u,
                    MEMTXATTRS_UNSPECIFIED, NULL);
            uint32_t record = (record_base + (unit & 0xffu) * 0x26u) &
                              MASK24;
            uint32_t buffer =
                ((uint32_t)address_space_lduw_le(
                    &address_space_memory, (record + 0x18u) & MASK24,
                    MEMTXATTRS_UNSPECIFIED, NULL) << 16) |
                address_space_lduw_le(
                    &address_space_memory, (record + 0x1au) & MASK24,
                    MEMTXATTRS_UNSPECIFIED, NULL);

            env->storage_lookup_stage[slot] = 1;
            env->storage_lookup_unit[slot] = unit;
            env->storage_lookup_lba_hi[slot] =
                internal_data_read((old_sp + 6u) & MASK16, 16);
            env->storage_lookup_lba_lo[slot] =
                internal_data_read((old_sp + 8u) & MASK16, 16);
            memset(env->storage_lookup_position_result[slot], 0xff,
                   sizeof(env->storage_lookup_position_result[slot]));
            env->storage_lookup_read_result[slot] = 0xffff;
            env->storage_lookup_result[slot] = 0xffff;
            memset(env->storage_lookup_partition_extracted[slot], 0xff,
                   sizeof(env->storage_lookup_partition_extracted[slot]));
            memset(env->storage_lookup_capacity[slot], 0xff,
                   sizeof(env->storage_lookup_capacity[slot]));
            env->storage_lookup_partition_result[slot] = 0xffff;
            env->storage_lookup_record[slot] = record;
            env->storage_lookup_buffer[slot] = buffer & MASK24;
            env->storage_lookup_cursor_hi[slot] = 0xffff;
            env->storage_lookup_cursor_lo[slot] = 0xffff;
            env->storage_lookup_sector_calls[slot] = 0;
            env->storage_lookup_ftl_calls[slot] = 0;
            env->storage_lookup_ftl_lba_hi[slot] = 0xffff;
            env->storage_lookup_ftl_lba_lo[slot] = 0xffff;
            for (unsigned index = 0;
                 index < DMCU_STORAGE_LOOKUP_RECORD_WORDS; index++) {
                env->storage_lookup_record_words[slot][index] =
                    address_space_lduw_le(
                        &address_space_memory,
                        (record + index * 2u) & MASK24,
                        MEMTXATTRS_UNSPECIFIED, NULL);
            }
            memset(env->storage_lookup_head[slot], 0,
                   sizeof(env->storage_lookup_head[slot]));
            memset(env->storage_lookup_partition[slot], 0,
                   sizeof(env->storage_lookup_partition[slot]));
            memset(env->storage_lookup_signature[slot], 0,
                   sizeof(env->storage_lookup_signature[slot]));
        } else if (env->storage_lookup_trace_count) {
            uint32_t slot = (env->storage_lookup_trace_count - 1u) %
                            DMCU_STORAGE_LOOKUP_TRACE_SLOTS;

            if (start == dmcu_code_address(0x2a, 0xd484)) {
                env->storage_lookup_stage[slot] |= 2;
                env->storage_lookup_position_result[slot][0] =
                    env->gpr[0] & MASK16;
                env->storage_lookup_position_result[slot][1] =
                    env->gpr[1] & MASK16;
            } else if (start == dmcu_code_address(0x32, 0x6f12)) {
                env->storage_lookup_stage[slot] |= 4;
                env->storage_lookup_sector_calls[slot]++;
                env->storage_lookup_cursor_hi[slot] =
                    address_space_lduw_le(
                        &address_space_memory, 0x005129c8u,
                        MEMTXATTRS_UNSPECIFIED, NULL);
                env->storage_lookup_cursor_lo[slot] =
                    address_space_lduw_le(
                        &address_space_memory, 0x005129cau,
                        MEMTXATTRS_UNSPECIFIED, NULL);
            } else if (start == dmcu_code_address(0x2c, 0x2eba)) {
                env->storage_lookup_stage[slot] |= 8;
                env->storage_lookup_ftl_calls[slot]++;
                env->storage_lookup_ftl_lba_hi[slot] =
                    internal_data_read((old_sp + 4u) & MASK16, 16);
                env->storage_lookup_ftl_lba_lo[slot] =
                    internal_data_read((old_sp + 6u) & MASK16, 16);
            } else if (start == dmcu_code_address(0x2a, 0xd4fc)) {
                uint32_t buffer = env->storage_lookup_buffer[slot] & MASK24;

                env->storage_lookup_stage[slot] |= 0x10;
                env->storage_lookup_read_result[slot] =
                    env->gpr[0] & MASK16;
                cpu_physical_memory_read(
                    buffer, env->storage_lookup_head[slot],
                    DMCU_STORAGE_LOOKUP_HEAD_BYTES);
                cpu_physical_memory_read(
                    (buffer + 0x1beu) & MASK24,
                    env->storage_lookup_partition[slot],
                    DMCU_STORAGE_LOOKUP_PARTITION_BYTES);
                cpu_physical_memory_read(
                    (buffer + 0x1feu) & MASK24,
                    env->storage_lookup_signature[slot], 2);
            } else if (start == dmcu_code_address(0x2a, 0xd5c4)) {
                env->storage_lookup_stage[slot] |= 0x20;
                env->storage_lookup_result[slot] = env->gpr[0] & MASK16;
            } else if (start == dmcu_code_address(0x2c, 0xfeec)) {
                env->storage_lookup_stage[slot] |= 0x40;
                env->storage_lookup_partition_extracted[slot][0] =
                    env->gpr[0] & MASK16;
                env->storage_lookup_partition_extracted[slot][1] =
                    env->gpr[1] & MASK16;
            } else if (start == dmcu_code_address(0x2c, 0xffaa)) {
                env->storage_lookup_stage[slot] |= 0x80;
                env->storage_lookup_partition_extracted[slot][0] =
                    internal_data_read((old_fp - 4u) & MASK16, 16);
                env->storage_lookup_partition_extracted[slot][1] =
                    internal_data_read((old_fp - 2u) & MASK16, 16);
                env->storage_lookup_capacity[slot][0] =
                    internal_data_read((old_fp - 8u) & MASK16, 16);
                env->storage_lookup_capacity[slot][1] =
                    internal_data_read((old_fp - 6u) & MASK16, 16);
            } else if (start == dmcu_code_address(0x2c, 0xffd6)) {
                env->storage_lookup_stage[slot] |= 0x100;
                env->storage_lookup_partition_result[slot] =
                    env->gpr[0] & MASK16;
            }
        }
    }

    if (!env->direct_menu_stack_watch_active && start == 0x064900u) {
        env->direct_menu_stack_watch_active = true;
        env->direct_menu_stack_arm_pc = start;
        env->direct_menu_stack_arm_sp = old_sp;
        env->direct_menu_stack_arm_fp = old_fp;
        qemu_log_mask(LOG_UNIMP,
                      "DMCU direct-menu stack watch armed at %02x:%04x "
                      "sp=%04x fp=%04x\n",
                      dmcu_code_segment(start), dmcu_code_pc(start),
                      old_sp, old_fp);
    }

    /* Preserve the two native framebuffer pages immediately before the first
     * natural root-controller invocation.  This observer-only snapshot makes
     * it possible to distinguish a desktop layer that was drawn and then
     * covered from one that the recovered foreground never constructed. */
    if (!env->root_entry_frame_valid &&
        start == dmcu_code_address(0x1d, 0xf2ec)) {
        cpu_physical_memory_read(0x500000u, env->root_entry_back_frame,
                                 DMCU_NATIVE_FRAMEBUFFER_BYTES);
        cpu_physical_memory_read(0x503840u, env->root_entry_front_frame,
                                 DMCU_NATIVE_FRAMEBUFFER_BYTES);
        env->root_entry_frame_valid = true;
    }

    /* Track the exact resident resource decoder used by the root controller.
     * State zero requests both the top toolbar and its own lower footer, but
     * only the toolbar currently reaches the native blitter.  These bounded,
     * read-only checkpoints identify whether the missing footer is rejected
     * as invalid geometry, fails object allocation, or reaches the final
     * composition call.  No guest register, memory, flag, or branch changes. */
    if (env->root_resource_trace_active) {
        uint32_t slot = env->root_resource_trace_active - 1u;

        if (slot < DMCU_ROOT_RESOURCE_TRACE_SLOTS) {
            uint16_t frame = env->root_resource_trace_fp[slot];

            if (start == dmcu_code_address(0x2e, 0x0af8)) {
                frame = old_fp & MASK16;
                env->root_resource_trace_fp[slot] = frame;
            } else if (frame && env->root_header_io_trace_pending &&
                       start == dmcu_code_address(0x2e, 0x0b80)) {
                uint64_t end = env->resource_io_calls;
                uint64_t available = end - env->root_header_io_trace_start;
                uint32_t count = MIN(
                    available, (uint64_t)DMCU_ROOT_HEADER_IO_TRACE_SLOTS);
                uint64_t first = end - count;
                uint32_t trace;
                unsigned argument;

                env->root_header_io_trace_count = count;
                for (trace = 0; trace < count; trace++) {
                    uint32_t source = (first + trace) %
                                      DMCU_RESOURCE_IO_TRACE_SLOTS;

                    env->root_header_io_trace_from[trace] =
                        env->resource_io_from[source];
                    env->root_header_io_trace_target[trace] =
                        env->resource_io_target[source];
                    for (argument = 0; argument < 6; argument++) {
                        env->root_header_io_trace_args[trace][argument] =
                            env->resource_io_args[source][argument];
                    }
                    env->root_header_io_trace_base[trace] =
                        env->resource_io_base[source];
                    env->root_header_io_trace_shift[trace] =
                        env->resource_io_shift[source];
                    env->root_header_io_trace_window[trace] =
                        env->resource_io_window[source];
                    env->root_header_io_trace_logical_block[trace] =
                        env->resource_io_logical_block[source];
                    env->root_header_io_trace_map_slot[trace] =
                        env->resource_io_map_slot[source];
                }
                for (argument = 0; argument < 4; argument++) {
                    env->root_header_io_trace_result[argument] =
                        internal_data_read(
                            (frame + 0xfff6u + argument) & MASK16, 8);
                }
                env->root_header_io_trace_pending = false;
                env->root_header_io_trace_captured = true;
            } else if (frame && start == dmcu_code_address(0x2e, 0x0bbe)) {
                env->root_resource_trace_source_hi[slot] =
                    internal_data_read((frame + 0xfffcu) & MASK16, 16);
                env->root_resource_trace_source_lo[slot] =
                    internal_data_read((frame + 0xfffeu) & MASK16, 16);
                env->root_resource_trace_width[slot] =
                    internal_data_read((frame + 0xfff4u) & MASK16, 16);
                env->root_resource_trace_height[slot] =
                    internal_data_read((frame + 0xfff2u) & MASK16, 16);
                env->root_resource_trace_stage[slot] |= 2u;
            } else if (start == dmcu_code_address(0x2e, 0x0bd6)) {
                env->root_resource_trace_stage[slot] |= 0x100u;
            } else if (start == dmcu_code_address(0x2e, 0x0bda)) {
                env->root_resource_trace_stage[slot] |= 4u;
            } else if (frame && start == dmcu_code_address(0x2e, 0x0c00)) {
                env->root_resource_trace_handle[slot] =
                    internal_data_read((frame + 0xfffau) & MASK16, 16);
                env->root_resource_trace_stage[slot] |= 8u;
            } else if (start == dmcu_code_address(0x2e, 0x0c0a)) {
                env->root_resource_trace_stage[slot] |= 0x200u;
            } else if (start == dmcu_code_address(0x2e, 0x0c0e)) {
                env->root_resource_trace_stage[slot] |= 0x10u;
            } else if (frame && start == dmcu_code_address(0x2e, 0x0c22)) {
                env->root_resource_trace_object_hi[slot] =
                    internal_data_read((frame + 0xffecu) & MASK16, 16);
                env->root_resource_trace_object_lo[slot] =
                    internal_data_read((frame + 0xffeeu) & MASK16, 16);
                env->root_resource_trace_stage[slot] |= 0x20u;
            } else if (start == dmcu_code_address(0x2e, 0x0c46)) {
                env->root_resource_trace_stage[slot] |= 0x40u;
                if (slot == 0u &&
                    env->root_resource_trace_width[slot] == 0x00f0u &&
                    env->root_resource_trace_height[slot] == 0x0016u &&
                    env->root_resource_trace_object_hi[slot] == 0x0051u) {
                    uint32_t object =
                        (((uint32_t)env->root_resource_trace_object_hi[slot]
                          & 0xffu) << 16) |
                        env->root_resource_trace_object_lo[slot];

                    cpu_physical_memory_read(
                        object & MASK24, env->root_top_bitmap,
                        DMCU_ROOT_TOP_BITMAP_BYTES);
                    env->root_top_bitmap_base = object & MASK24;
                    env->root_top_bitmap_length = DMCU_ROOT_TOP_BITMAP_BYTES;
                    env->root_top_bitmap_valid = true;
                    /* Keep the general I/O ring at the exact end of the
                     * first toolbar load.  Later clock/footer refreshes are
                     * repetitive and otherwise overwrite the decisive FTL
                     * block and sector sequence. */
                    env->resource_io_trace_frozen = true;
                    env->resource_io_trace_frozen_pc = start & MASK24;
                }
            } else if (start == dmcu_code_address(0x2e, 0x0c62)) {
                env->root_resource_trace_stage[slot] |= 0x80u;
            } else if (start == dmcu_code_address(0x2e, 0x0c7c)) {
                env->root_resource_trace_stage[slot] |= 0x400u;
                env->root_resource_trace_active = 0;
            }
        } else {
            env->root_resource_trace_active = 0;
        }
    }

    /* The toolbar's four aligned 512-byte sectors enter the exact general
     * far-copy worker with an odd destination.  Preserve the parity decision
     * and selected byte/word loop while the first root resource is active.
     * This is observer-only and is intentionally bounded to one cold boot. */
    if (env->root_resource_trace_active == 1u &&
        (start == dmcu_code_address(0x2e, 0x45b6) ||
         start == dmcu_code_address(0x2e, 0x45ba) ||
         start == dmcu_code_address(0x2e, 0x45bc) ||
         start == dmcu_code_address(0x2e, 0x45c4) ||
         start == dmcu_code_address(0x2e, 0x45c8) ||
         start == dmcu_code_address(0x2e, 0x45da) ||
         start == dmcu_code_address(0x2e, 0x4694) ||
         start == dmcu_code_address(0x2e, 0x46b0) ||
         start == dmcu_code_address(0x2e, 0x46d0)) &&
        env->root_top_far_copy_steps < DMCU_ROOT_TOP_FAR_COPY_TRACE_SLOTS) {
        uint32_t trace = env->root_top_far_copy_steps++;
        unsigned index;

        env->root_top_far_copy_pc[trace] = start;
        env->root_top_far_copy_from[trace] = 0;
        env->root_top_far_copy_psw[trace] = env->psw & MASK16;
        for (index = 0; index < 11; index++) {
            env->root_top_far_copy_gpr[trace][index] =
                env->gpr[index] & MASK16;
        }
        memset(env->root_top_far_copy_args[trace], 0,
               sizeof(env->root_top_far_copy_args[trace]));
    }

    /*
     * State 0x50 is the last zero-input boot state before the root menu.  Its
     * exact resident body is 0C:0000..4A6A and is large enough that an
     * ordinary circular control trace loses the decisive branch long before
     * the body returns.  Capture one bounded, late outer invocation.  An
     * outer call is distinguished from the module's nineteen recursive calls
     * by its far return frame (32:C006, the exact state-50 wrapper).  This is
     * diagnostic-only: no register, flag, memory byte, or control target is
     * changed.
     */
    if (start == dmcu_code_address(0x0c, 0x0000) &&
        internal_data_read(old_sp, 16) == 0x0032 &&
        internal_data_read((old_sp + 2) & MASK16, 16) == 0xc006) {
        uint16_t state = address_space_lduw_le(
            &address_space_memory, 0x512aaa,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t phase = address_space_lduw_le(
            &address_space_memory, 0x512aa0,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t handle = address_space_lduw_le(
            &address_space_memory, 0x52573c,
            MEMTXATTRS_UNSPECIFIED, NULL);

        state50_outer_entries++;
        if (state50_outer_entries <= 32) {
            qemu_log_mask(
                LOG_UNIMP,
                "DMCU state50 outer entry #%u sp=%04x fp=%04x "
                "args=%04x,%04x,%04x,%04x,%04x,%04x "
                "state=%04x phase=%04x handle=%04x\n",
                state50_outer_entries, old_sp, old_fp,
                internal_data_read((old_sp + 4) & MASK16, 16),
                internal_data_read((old_sp + 6) & MASK16, 16),
                internal_data_read((old_sp + 8) & MASK16, 16),
                internal_data_read((old_sp + 10) & MASK16, 16),
                internal_data_read((old_sp + 12) & MASK16, 16),
                internal_data_read((old_sp + 14) & MASK16, 16),
                state, phase, handle);
        }
        if (state50_outer_entries == 16) {
            state50_branch_trace_active = true;
            state50_branch_trace_steps = 0;
            qemu_log_mask(LOG_UNIMP,
                          "DMCU state50 branch trace begin at outer #16\n");
        }
    }

    /*
     * 31:4BAC is the recovered firmware's framebuffer swap/refresh routine.
     * Mode 1 copies 50:0000 to the LCD buffer at 50:3840 through resident
     * 08:43A6.  Capture both buffers immediately before and after that call,
     * plus the final pre-flush state, so a persistent blank screen can be
     * assigned to rendering, the resident copy, or LCD transport without
     * changing any guest byte.  A1:386C is byte-lane-swapped on the external
     * data bus and therefore resides at physical 50:B86D.
     */
    if (start == dmcu_code_address(0x31, 0x4bac)) {
        uint32_t refresh_slot = env->native_refresh_trace_count %
                                DMCU_NATIVE_REFRESH_TRACE_SLOTS;
        uint32_t caller =
            ((internal_data_read(old_sp, 16) & 0xffu) << 16) |
            internal_data_read((old_sp + 2u) & MASK16, 16);
        uint32_t parent =
            ((internal_data_read((old_fp + 2u) & MASK16, 16) & 0xffu) <<
             16) |
            internal_data_read((old_fp + 4u) & MASK16, 16);

        env->native_refresh_calls++;
        env->native_refresh_mode = address_space_ldub(
            &address_space_memory, 0x50b86d,
            MEMTXATTRS_UNSPECIFIED, NULL);
        env->native_refresh_pointer =
            (internal_data_read(0x04fc, 16) << 16) |
            internal_data_read(0x04fe, 16);
        native_buffer_stats(0x500000,
                            &env->native_refresh_back_entry_nonzero,
                            &env->native_refresh_back_entry_hash);
        native_buffer_stats(0x503840,
                            &env->native_refresh_front_entry_nonzero,
                            &env->native_refresh_front_entry_hash);
        env->native_refresh_trace_caller[refresh_slot] = caller;
        env->native_refresh_trace_parent[refresh_slot] = parent;
        env->native_refresh_trace_mode[refresh_slot] =
            env->native_refresh_mode;
        env->native_refresh_trace_pointer[refresh_slot] =
            env->native_refresh_pointer;
        env->native_refresh_trace_back_nonzero[refresh_slot] =
            env->native_refresh_back_entry_nonzero;
        env->native_refresh_trace_front_nonzero[refresh_slot] =
            env->native_refresh_front_entry_nonzero;
        env->native_refresh_trace_state[refresh_slot] =
            address_space_lduw_le(
            &address_space_memory, 0x512aaau,
            MEMTXATTRS_UNSPECIFIED, NULL);
        env->native_refresh_trace_resource[refresh_slot] =
            address_space_lduw_le(&address_space_memory, 0x512abau,
                                  MEMTXATTRS_UNSPECIFIED, NULL);
        env->native_refresh_trace_count++;
        env->native_refresh_back_nonzero_calls +=
            env->native_refresh_back_entry_nonzero != 0;
    } else if (start == dmcu_code_address(0x31, 0x4bfc)) {
        env->native_refresh_copy_calls++;
        native_buffer_stats(0x500000,
                            &env->native_refresh_back_copy_nonzero,
                            &env->native_refresh_back_copy_hash);
    } else if (start == dmcu_code_address(0x31, 0x4c00)) {
        native_buffer_stats(0x503840,
                            &env->native_refresh_front_after_nonzero,
                            &env->native_refresh_front_after_hash);
        env->native_refresh_front_nonzero_calls +=
            env->native_refresh_front_after_nonzero != 0;
        if (env->native_refresh_back_copy_nonzero !=
                env->native_refresh_front_after_nonzero ||
            env->native_refresh_back_copy_hash !=
                env->native_refresh_front_after_hash) {
            env->native_refresh_copy_mismatches++;
        }
    } else if (start == dmcu_code_address(0x31, 0x4c58)) {
        native_buffer_stats(0x500000,
                            &env->native_refresh_preflush_back_nonzero,
                            &env->native_refresh_preflush_back_hash);
        native_buffer_stats(0x503840,
                            &env->native_refresh_preflush_front_nonzero,
                            &env->native_refresh_preflush_front_hash);
    }

    if (start == dmcu_code_address(0x08, 0x4264) && env->in_interrupt) {
        env->irq_save_fp_restores++;
        env->irq_save_fp_restore_entry = env->interrupt_entries;
        env->irq_save_fp_restore_pc = start;
        env->irq_save_fp_restore_expected = env->irq_save_fp_saved_value;
        env->irq_save_fp_restore_value = internal_data_read(0x04d6, 16);
        env->irq_save_fp_restore_fp = old_fp;
    }

    if ((start == 0x2895b2u || start == 0x2895fau ||
         start == 0x289658u || start == 0x28968cu ||
         start == 0x2896c6u || start == 0x2896ccu ||
         start == 0x2896d2u || start == 0x2896d8u) &&
        application_scanner_gate_steps < 64) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU application scanner gate #%u pc=%02x:%04x "
            "fp=%04x index=%04x flag=%02x r0=%04x r1=%04x "
            "object=%04x:%04x record=%04x:%04x psw=%04x\n",
            application_scanner_gate_steps + 1,
            dmcu_code_segment(start), dmcu_code_pc(start), old_fp,
            internal_data_read((old_fp - 4u) & MASK16, 16),
            internal_data_read((old_fp - 1u) & MASK16, 8) & 0xff,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            internal_data_read((old_fp - 12u) & MASK16, 16),
            internal_data_read((old_fp - 10u) & MASK16, 16),
            internal_data_read((old_fp - 8u) & MASK16, 16),
            internal_data_read((old_fp - 6u) & MASK16, 16),
            env->psw & MASK16);
        application_scanner_gate_steps++;
    }

    /*
     * 25:206E does not dereference 10:Dxxx as a flat ROM far pointer.  Its
     * 28:12A8 child divides the address by the 0x200-byte transfer window,
     * asks 2D:261C/2C:2EBA for the corresponding FTL page, and copies from
     * 51:1840.  Trace the bounded intermediate results while reconstructing
     * that NAND-backed resource path; this is diagnostic only and never
     * changes guest registers or memory.
     */
    if (start == 0x1bce3cu) {
        /* Earlier boot-time resource reads can consume this bounded trace
         * before the application selector opens 10:D03F.  Start a fresh
         * diagnostic window for the authoritative application path. */
        application_resource_paging_trace_steps = 0;
    }
    if ((start == 0x29ac7au || start == 0x29aca2u ||
         start == 0x29acd2u || start == 0x29ad04u ||
         start == 0x29ad30u || start == 0x29ad82u ||
         start == 0x29aee8u || start == 0x2d262cu ||
         start == 0x2d276au || start == 0x2d27e4u ||
         start == 0x2c2f5cu || start == 0x2c2f60u ||
         start == 0x2c2f7eu || start == 0x2c2faau ||
         start == 0x2c3008u) &&
        application_resource_paging_trace_steps < 64) {
        uint16_t logical_block = internal_data_read(
            (old_fp - 4u) & MASK16, 16);
        uint16_t map_slot = internal_data_read(
            (0x0286u + ((logical_block & 0xffu) << 1)) & MASK16, 16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU resource paging step #%u pc=%02x:%04x "
            "r0-r3=%04x,%04x,%04x,%04x sp=%04x fp=%04x",
            application_resource_paging_trace_steps + 1,
            dmcu_code_segment(start), dmcu_code_pc(start),
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            env->gpr[DMCU_SP] & MASK16, env->gpr[DMCU_FP] & MASK16);
        log_application_far_words("stage", 0x0051, 0x1840, 8);
        if ((start >> 16) == 0x2cu) {
            qemu_log_mask(
                LOG_UNIMP,
                " ftl=block:%04x/rem:%04x/page:%04x/column:%04x/"
                "saved:%04x/r0:%04x slot:%04x window:%04x-%04x "
                "special:%04x,%04x cache:%04x:%04x",
                logical_block,
                internal_data_read((old_fp - 6u) & MASK16, 16),
                internal_data_read((old_fp - 8u) & MASK16, 16),
                internal_data_read((old_fp - 12u) & MASK16, 16),
                internal_data_read((old_fp - 2u) & MASK16, 16),
                env->gpr[0] & MASK16, map_slot,
                internal_data_read(0x027e, 16),
                internal_data_read(0x0280, 16),
                internal_data_read(0x4acc, 16),
                internal_data_read(0x4ace, 16),
                internal_data_read(0x4b04, 16),
                internal_data_read(0x4b06, 16));
        }
        qemu_log_mask(LOG_UNIMP, "\n");
        application_resource_paging_trace_steps++;
    }

    if (((start == 0x1a3a18u &&
          ((env->gpr[4] & MASK16) == 0x0098u ||
           (env->gpr[4] & MASK16) == 0x0001u)) ||
         start == 0x1a3a26u || start == 0x31d582u) &&
        resource_geometry_trace_steps < 12) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU resource geometry step #%u pc=%02x:%04x word=%04x "
            "r1=%04x r3=%04x r4=%04x DS0=%03x DS1=%03x",
            resource_geometry_trace_steps + 1,
            dmcu_code_segment(start), dmcu_code_pc(start), word0 & MASK16,
            env->gpr[1] & MASK16, env->gpr[3] & MASK16,
            env->gpr[4] & MASK16,
            env->sfr[DMCU_SFR_DS0] & 0x1ff,
            env->sfr[DMCU_SFR_DS1] & 0x1ff);
        log_application_far_words("destination", 0x0031, 0xd582, 8);
        log_application_far_words("source", 0x004e, 0xd582, 8);
        qemu_log_mask(LOG_UNIMP, "\n");
        resource_geometry_trace_steps++;
    }

    /* Once the foreground task has stopped on an unsupported word, periodic
     * timer IRQs can still wake the CPU and overwrite the circular trace with
     * interrupt prologue/epilogue traffic.  Keep the first-failure window
     * intact; the unsupported instruction itself is recorded before the flag
     * is set below. */
    if (!env->unsupported_valid) {
        env->exec_trace_pc[trace_slot] = start & MASK24;
        env->exec_trace_word[trace_slot] = word0 & MASK16;
        env->exec_trace_count++;
    }

    /* Flat 25:B000..B5D5 is resource/payload data, while the complete linked
     * same-PC function survives in source segment 42.  Preserve the first
     * control chain which enters this window; periodic timer IRQ returns can
     * otherwise replace the circular trace before the first unsupported data
     * word halts the foreground task.  This is diagnostic only. */
    if (start == 0x25b202u && word0 != 0x2e01u &&
        menu_result_data_control_entries < 1) {
        unsigned control_slot = env->control_trace_count ?
            (env->control_trace_count - 1) % DMCU_CONTROL_TRACE_WORDS : 0;

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU menu-result data entry %02x:%04x "
            "from=%02x:%04x next=%02x:%04x word=%04x ext=%04x "
            "last-control=%02x:%04x>%02x:%04x/%04x "
            "sp=%04x fp=%04x stack=%04x,%04x,%04x,%04x,%04x,%04x\n",
            dmcu_code_segment(start), dmcu_code_pc(start),
            dmcu_code_segment(env->completed_instruction_pc),
            dmcu_code_pc(env->completed_instruction_pc),
            dmcu_code_segment(env->completed_instruction_next_pc),
            dmcu_code_pc(env->completed_instruction_next_pc),
            env->completed_instruction_word & MASK16,
            env->completed_instruction_ext & MASK16,
            env->control_trace_count ?
                dmcu_code_segment(env->control_trace_from[control_slot]) : 0,
            env->control_trace_count ?
                dmcu_code_pc(env->control_trace_from[control_slot]) : 0,
            env->control_trace_count ?
                dmcu_code_segment(env->control_trace_to[control_slot]) : 0,
            env->control_trace_count ?
                dmcu_code_pc(env->control_trace_to[control_slot]) : 0,
            env->control_trace_count ?
                env->control_trace_word[control_slot] & MASK16 : 0,
            old_sp, old_fp,
            internal_data_read(old_sp, 16),
            internal_data_read((old_sp + 2) & MASK16, 16),
            internal_data_read((old_sp + 4) & MASK16, 16),
            internal_data_read((old_sp + 6) & MASK16, 16),
            internal_data_read((old_sp + 8) & MASK16, 16),
            internal_data_read((old_sp + 10) & MASK16, 16));
        menu_result_data_control_entries++;
        env->control_trace_frozen = true;
    }

    /* 26:FB00..FCFF is shipped resource payload, not an executable module.
     * Record the control transfer which first enters it so an accidental
     * supported-looking payload word cannot hide the actual bad return or
     * callback behind a later unsupported opcode.  Ignore the periodic IRQ
     * epilogue returning to an already-corrupt foreground PC. */
    if (start >= 0x26fb00u && start < 0x26fd00u &&
        dmcu_code_segment(env->completed_instruction_pc) != 0x08u &&
        start != ((env->completed_instruction_pc +
                  dmcu_insn_size(env->completed_instruction_word)) & MASK24) &&
        resource_data_control_entries < 16) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU resource-data control entry #%u %02x:%04x "
            "from=%02x:%04x next=%02x:%04x word=%04x ext=%04x "
            "sp=%04x fp=%04x stack=%04x,%04x,%04x,%04x,%04x,%04x\n",
            resource_data_control_entries + 1,
            dmcu_code_segment(start), dmcu_code_pc(start),
            dmcu_code_segment(env->completed_instruction_pc),
            dmcu_code_pc(env->completed_instruction_pc),
            dmcu_code_segment(env->completed_instruction_next_pc),
            dmcu_code_pc(env->completed_instruction_next_pc),
            env->completed_instruction_word & MASK16,
            env->completed_instruction_ext & MASK16,
            old_sp, old_fp,
            internal_data_read(old_sp, 16),
            internal_data_read((old_sp + 2) & MASK16, 16),
            internal_data_read((old_sp + 4) & MASK16, 16),
            internal_data_read((old_sp + 6) & MASK16, 16),
            internal_data_read((old_sp + 8) & MASK16, 16),
            internal_data_read((old_sp + 10) & MASK16, 16));
        resource_data_control_entries++;
    }

    /*
     * The exact sector probe is relocated to 5F:F928 because 20:F928 is a
     * live fall-through point in the unrelated 20:E914 function.  Trace both
     * sides of that split: 20:* proves the original body remains intact,
     * while 5F:* records genuine calls into the relocated probe.
     */
    if ((start == dmcu_code_address(0x20, 0xf928) ||
         start == dmcu_code_address(0x20, 0xfc82) ||
         start == dmcu_code_address(0x20, 0xfc8a) ||
         start == dmcu_code_address(0x5f, 0xf928) ||
         start == dmcu_code_address(0x5f, 0xf92a) ||
         start == dmcu_code_address(0x5f, 0xfc82) ||
         start == dmcu_code_address(0x5f, 0xfc8a)) &&
        storage_sector_probe_trace_steps < 32) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU sector probe trace #%u pc=%02x:%04x word=%04x "
            "r0-r3=%04x,%04x,%04x,%04x sp=%04x fp=%04x "
            "stack=%04x,%04x,%04x,%04x,%04x,%04x "
            "fpargs=%04x,%04x ds=%03x,%03x\n",
            storage_sector_probe_trace_steps + 1,
            dmcu_code_segment(start), dmcu_code_pc(start), word0 & MASK16,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            old_sp, old_fp,
            internal_data_read(old_sp, 16),
            internal_data_read((old_sp + 2) & MASK16, 16),
            internal_data_read((old_sp + 4) & MASK16, 16),
            internal_data_read((old_sp + 6) & MASK16, 16),
            internal_data_read((old_sp + 8) & MASK16, 16),
            internal_data_read((old_sp + 10) & MASK16, 16),
            internal_data_read((old_fp + 6) & MASK16, 16),
            internal_data_read((old_fp + 8) & MASK16, 16),
            old_ds0, old_ds1);
        storage_sector_probe_trace_steps++;
    }

    if ((start == dmcu_code_address(0x11, 0x1886) ||
         start == dmcu_code_address(0x2e, 0x1886)) &&
        application_input_callback_trace_steps < 16) {
        uint16_t object_hi = internal_data_read((old_fp + 6) & MASK16, 16);
        uint16_t object_lo = internal_data_read((old_fp + 8) & MASK16, 16);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU input callback trace #%u pc=%02x:%04x target=%04x:%04x "
            "sp=%04x fp=%04x object=%04x:%04x "
            "stack=%04x,%04x,%04x,%04x,%04x,%04x "
            "object-words=%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,"
            "%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x\n",
            application_input_callback_trace_steps + 1,
            dmcu_code_segment(start), dmcu_code_pc(start),
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            old_sp, old_fp, object_hi, object_lo,
            internal_data_read(old_sp, 16),
            internal_data_read((old_sp + 2) & MASK16, 16),
            internal_data_read((old_sp + 4) & MASK16, 16),
            internal_data_read((old_sp + 6) & MASK16, 16),
            internal_data_read((old_sp + 8) & MASK16, 16),
            internal_data_read((old_sp + 10) & MASK16, 16),
            internal_data_read(object_lo, 16),
            internal_data_read((object_lo + 2) & MASK16, 16),
            internal_data_read((object_lo + 4) & MASK16, 16),
            internal_data_read((object_lo + 6) & MASK16, 16),
            internal_data_read((object_lo + 8) & MASK16, 16),
            internal_data_read((object_lo + 10) & MASK16, 16),
            internal_data_read((object_lo + 12) & MASK16, 16),
            internal_data_read((object_lo + 14) & MASK16, 16),
            internal_data_read((object_lo + 16) & MASK16, 16),
            internal_data_read((object_lo + 18) & MASK16, 16),
            internal_data_read((object_lo + 20) & MASK16, 16),
            internal_data_read((object_lo + 22) & MASK16, 16),
            internal_data_read((object_lo + 24) & MASK16, 16),
            internal_data_read((object_lo + 26) & MASK16, 16),
            internal_data_read((object_lo + 28) & MASK16, 16),
            internal_data_read((object_lo + 30) & MASK16, 16),
            internal_data_read((object_lo + 32) & MASK16, 16),
            internal_data_read((object_lo + 34) & MASK16, 16));
        application_input_callback_trace_steps++;
    }

    /*
     * The operation-0x0b resident setup reaches several decision points by
     * sequential execution, so the control-transfer trace cannot observe
     * them.  Keep a deliberately small diagnostic trace at the instruction
     * boundary.  Besides the call frame, capture the descriptor bitmap,
     * heap/list anchors, and the four operation result slots whose missing
     * initialization currently prevents the fixed application launcher from
     * reaching storage I/O.
     */
    if ((start == dmcu_code_address(0x1b, 0x23b8) ||
         start == dmcu_code_address(0x1b, 0x23f4) ||
         start == dmcu_code_address(0x1b, 0x2400) ||
         start == dmcu_code_address(0x1b, 0x2c46) ||
         start == dmcu_code_address(0x31, 0x4974) ||
         start == dmcu_code_address(0x31, 0x49b0) ||
         start == dmcu_code_address(0x33, 0x51e0) ||
         start == dmcu_code_address(0x25, 0x77da) ||
         start == dmcu_code_address(0x25, 0x78ea) ||
         start == dmcu_code_address(0x25, 0x78ee) ||
         start == dmcu_code_address(0x25, 0x79aa) ||
         start == dmcu_code_address(0x30, 0x251e) ||
         start == dmcu_code_address(0x30, 0x2624) ||
         start == dmcu_code_address(0x30, 0x2626)) &&
        resident_allocator_trace_steps < 64) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU resident allocator #%u pc=%02x:%04x word=%04x "
            "r0-r3=%04x,%04x,%04x,%04x sp=%04x fp=%04x "
            "stack=%04x,%04x,%04x,%04x,%04x,%04x "
            "bitmap=%04x bounds=%04x,%04x "
            "list=%04x,%04x,%04x,%04x "
            "results=%04x,%04x,%04x,%04x ds=%03x,%03x\n",
            resident_allocator_trace_steps + 1,
            dmcu_code_segment(start), dmcu_code_pc(start), word0 & MASK16,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            old_sp, old_fp,
            internal_data_read(old_sp, 16),
            internal_data_read((old_sp + 2) & MASK16, 16),
            internal_data_read((old_sp + 4) & MASK16, 16),
            internal_data_read((old_sp + 6) & MASK16, 16),
            internal_data_read((old_sp + 8) & MASK16, 16),
            internal_data_read((old_sp + 10) & MASK16, 16),
            address_space_lduw_le(
                &address_space_memory, 0x005127eau,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x005129a0u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x005129a2u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00514a40u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00514a42u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00514a44u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00514a46u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00525626u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x0052574cu,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x0052574eu,
                MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(
                &address_space_memory, 0x00525760u,
                MEMTXATTRS_UNSPECIFIED, NULL),
            old_ds0, old_ds1);
        resident_allocator_trace_steps++;
    }

    /*
     * The fifth allocation in the resident operation requests 0x0164 bytes.
     * The broad allocator trace above is useful during bootstrap, but its
     * fixed budget is consumed by the four preceding 0x0100 allocations.
     * Classify every source-proven zero-result arm for the 0x0164 request and
     * retain the current list node.  This is deliberately read-only: the
     * guest heap, bitmap, registers, and control flow are not modified.
     */
    if ((start == dmcu_code_address(0x25, 0x786a) ||
         start == dmcu_code_address(0x25, 0x78c8) ||
         start == dmcu_code_address(0x25, 0x79aa) ||
         start == dmcu_code_address(0x25, 0x79c0) ||
         start == dmcu_code_address(0x25, 0x7af6) ||
         start == dmcu_code_address(0x25, 0x7b78)) &&
        internal_data_read((old_fp + 6u) & MASK16, 16) == 0x0164u &&
        result_heap_failure_logs < 16) {
        uint16_t node_hi = internal_data_read((old_fp - 4u) & MASK16, 16);
        uint16_t node_lo = internal_data_read((old_fp - 2u) & MASK16, 16);
        uint32_t node = ((uint32_t)node_hi << 16) | node_lo;
        uint16_t node_words[4] = { 0xffffu, 0xffffu, 0xffffu, 0xffffu };
        const char *failure_class;
        unsigned index;

        if (start == dmcu_code_address(0x25, 0x786a)) {
            failure_class = "next-above-bound";
        } else if (start == dmcu_code_address(0x25, 0x78c8)) {
            failure_class = "span-underflow";
        } else if (start == dmcu_code_address(0x25, 0x79aa)) {
            failure_class = "descriptor-bit";
        } else if (start == dmcu_code_address(0x25, 0x79c0)) {
            failure_class = "span-too-small";
        } else if (start == dmcu_code_address(0x25, 0x7af6)) {
            failure_class = "gap-descriptor-bit";
        } else {
            failure_class = "next-null-or-above-bound";
        }
        if ((node_hi & 0xff00u) == 0) {
            for (index = 0; index < ARRAY_SIZE(node_words); index++) {
                node_words[index] = address_space_lduw_le(
                    &address_space_memory, (node + index * 2u) & MASK24,
                    MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU result heap failure #%u class=%s pc=%02x:%04x "
            "request=%04x node=%04x:%04x words=%04x,%04x,%04x,%04x "
            "span=%04x bit=%04x bound=%04x:%04x r0-r3=%04x,%04x,%04x,%04x "
            "sp=%04x fp=%04x ds=%03x,%03x\n",
            result_heap_failure_logs + 1, failure_class,
            dmcu_code_segment(start), dmcu_code_pc(start),
            internal_data_read((old_fp + 6u) & MASK16, 16), node_hi, node_lo,
            node_words[0], node_words[1], node_words[2], node_words[3],
            internal_data_read((old_fp - 6u) & MASK16, 16),
            internal_data_read((old_fp - 12u) & MASK16, 16),
            address_space_lduw_le(&address_space_memory, 0x005129a0u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            address_space_lduw_le(&address_space_memory, 0x005129a2u,
                                  MEMTXATTRS_UNSPECIFIED, NULL),
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16,
            old_sp, old_fp, old_ds0, old_ds1);
        result_heap_failure_logs++;
    }
    if ((start == dmcu_code_address(0x25, 0x7bb4) ||
         start == dmcu_code_address(0x33, 0x51ec) ||
         start == dmcu_code_address(0x18, 0xcfc8)) &&
        env->gpr[0] == 0 && result_heap_return_logs < 16) {
        qemu_log_mask(
            LOG_UNIMP,
            "DMCU result heap zero return #%u pc=%02x:%04x r0-r3="
            "%04x,%04x,%04x,%04x sp=%04x fp=%04x frame-12..+6="
            "%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x\n",
            result_heap_return_logs + 1,
            dmcu_code_segment(start), dmcu_code_pc(start),
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            env->gpr[2] & MASK16, env->gpr[3] & MASK16, old_sp, old_fp,
            internal_data_read((old_fp - 12u) & MASK16, 16),
            internal_data_read((old_fp - 10u) & MASK16, 16),
            internal_data_read((old_fp - 8u) & MASK16, 16),
            internal_data_read((old_fp - 6u) & MASK16, 16),
            internal_data_read((old_fp - 4u) & MASK16, 16),
            internal_data_read((old_fp - 2u) & MASK16, 16),
            internal_data_read(old_fp, 16),
            internal_data_read((old_fp + 2u) & MASK16, 16),
            internal_data_read((old_fp + 4u) & MASK16, 16),
            internal_data_read((old_fp + 6u) & MASK16, 16));
        result_heap_return_logs++;
    }

    /* The three foreground decision points below are reached sequentially
     * or by an ordinary AJMP, so the call/return trace cannot observe them.
     * Reuse the final application-trace slots reserved for this diagnostic
     * and sample only guest state.  No event, selector, register, or memory
     * value is modified here. */
    if (start == dmcu_code_address(0x20, 0x2f16) ||
        start == dmcu_code_address(0x20, 0x3190) ||
        start == dmcu_code_address(0x20, 0x3388)) {
        unsigned entry;

        if (start == dmcu_code_address(0x20, 0x2f16)) {
            entry = DMCU_APPLICATION_TRACE_ENTRIES - 6; /* FGDECODE */
        } else if (start == dmcu_code_address(0x20, 0x3190)) {
            entry = DMCU_APPLICATION_TRACE_ENTRIES - 5; /* FGCHANGE */
        } else {
            entry = DMCU_APPLICATION_TRACE_ENTRIES - 4; /* FGEXIT */
        }
        env->application_trace_calls[entry]++;
        env->application_trace_from[entry] =
            env->completed_instruction_pc & MASK24;
        env->application_trace_sp[entry] = old_sp;

        if (start == dmcu_code_address(0x20, 0x2f16)) {
            env->application_trace_r0[entry] =
                internal_data_read((old_fp - 0x1cu) & MASK16, 16);
            env->application_trace_r1[entry] =
                address_space_lduw_le(&address_space_memory, 0x512aaau,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->application_trace_r2[entry] =
                address_space_lduw_le(&address_space_memory, 0x512abau,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
        } else if (start == dmcu_code_address(0x20, 0x3190)) {
            env->application_trace_r0[entry] = env->gpr[0] & MASK16;
            env->application_trace_r1[entry] =
                address_space_lduw_le(&address_space_memory, 0x512aaau,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->application_trace_r2[entry] =
                address_space_lduw_le(&address_space_memory, 0x512abau,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
        } else {
            env->application_trace_r0[entry] =
                address_space_lduw_le(&address_space_memory, 0x512aaau,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->application_trace_r1[entry] =
                address_space_lduw_le(&address_space_memory, 0x512abau,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->application_trace_r2[entry] =
                address_space_lduw_le(&address_space_memory, 0x512250u,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
        }
        if (start == dmcu_code_address(0x20, 0x2f16)) {
            /* The 0x8F foreground event has two independent sources at
             * 20:2EC8..2EE8: a non-zero worker result at FP-0x12, or a
             * mismatch between A2:2A6C and A2:2A90.  Preserve the four exact
             * operands so a cold boot identifies the source in one sample. */
            env->application_trace_args[entry][0] =
                internal_data_read((old_fp - 0x12u) & MASK16, 16);
            env->application_trace_args[entry][1] =
                internal_data_read((old_fp - 0x10u) & MASK16, 16);
            env->application_trace_args[entry][2] =
                address_space_lduw_le(&address_space_memory, 0x512a6cu,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
            env->application_trace_args[entry][3] =
                address_space_lduw_le(&address_space_memory, 0x512a90u,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
        } else {
            env->application_trace_args[entry][0] =
                internal_data_read((old_fp - 0x1cu) & MASK16, 16);
            env->application_trace_args[entry][1] =
                internal_data_read((old_fp - 0x14u) & MASK16, 16);
            env->application_trace_args[entry][2] =
                internal_data_read((old_fp - 0x16u) & MASK16, 16);
            env->application_trace_args[entry][3] =
                address_space_lduw_le(&address_space_memory, 0x512a4eu,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
        }
    }
    if (!env->in_interrupt && !env->missing_rom_valid) {
        unsigned foreground_slot = env->foreground_trace_count %
                                   DMCU_FOREGROUND_TRACE_WORDS;

        env->foreground_trace_pc[foreground_slot] = start & MASK24;
        env->foreground_trace_word[foreground_slot] = word0 & MASK16;
        env->foreground_trace_sp[foreground_slot] = old_sp & MASK16;
        env->foreground_trace_count++;
    }

    if (start >= dmcu_code_address(0x33, 0x6f30) &&
        start <= dmcu_code_address(0x33, 0x6f34) && !(start & 1)) {
        unsigned instruction = (dmcu_code_pc(start) - 0x6f30) >> 1;

        env->post_registry_hook_exec[instruction]++;
        env->post_registry_hook_word[instruction] = word0 & MASK16;
    }

    if (start == 0x5195d8) {
        uint8_t command_bytes[2];

        cpu_physical_memory_read(0x500008, command_bytes,
                                 sizeof(command_bytes));
        qemu_log_mask(LOG_UNIMP,
                      "DMCU 95D8 command=%04x caller=%02x:%04x "
                      "args=%04x,%04x,%04x globals="
                      "%04x,%04x,%04x,%04x sp=%04x fp=%04x\n",
                      lduw_le_p(command_bytes),
                      internal_data_read(old_sp & MASK16, 16) & 0xff,
                      internal_data_read((old_sp + 2) & MASK16, 16),
                      internal_data_read((old_sp + 4) & MASK16, 16),
                      internal_data_read((old_sp + 6) & MASK16, 16),
                      internal_data_read((old_sp + 8) & MASK16, 16),
                      internal_data_read(0x0864, 16),
                      internal_data_read(0x0866, 16),
                      internal_data_read(0x0868, 16),
                      internal_data_read(0x086c, 8), old_sp, old_fp);
    }

    /* Observe the byte sub_50_B730 actually consumes after BBF6 returns.
     * This separates an incorrect guest logical-page expansion from a CPU
     * compare/branch bug without changing either path.  At B862 RB1 already
     * holds cache[page_size + 0x36]; B8D4 is the non-erased full-read arm. */
    if (start == 0x50b862) {
        uint32_t status = reg_read(env, 1, 8) & 0xff;

        env->b730_status_reads++;
        env->b730_status_last = status;
        if (status == 0xff) {
            env->b730_status_ff++;
        } else if (status == 0) {
            env->b730_status_zero++;
        } else {
            env->b730_status_other++;
        }
    } else if (start == 0x50b8d4) {
        env->b730_full_path_entries++;
    }

    /* Trace only block copies that target object zero's 24-byte backing
     * record.  51:98FC is the vendor far memcpy; the record is known to be
     * constructed correctly and then replaced immediately before B0B2, so
     * capture the real source, length, and caller without altering it. */
    if (start == 0x5198fc) {
        uint32_t destination =
            ((internal_data_read((old_sp + 4) & MASK16, 16) & 0xff) << 16) |
            internal_data_read((old_sp + 6) & MASK16, 16);

        if (destination >= 0x5002a6 && destination < 0x5002be) {
            uint32_t source =
                ((internal_data_read((old_sp + 8) & MASK16, 16) & 0xff) << 16) |
                internal_data_read((old_sp + 10) & MASK16, 16);
            uint32_t length =
                ((uint32_t)internal_data_read((old_sp + 12) & MASK16, 16) << 16) |
                internal_data_read((old_sp + 14) & MASK16, 16);
            uint8_t source_bytes[24];

            cpu_physical_memory_read(source & MASK24, source_bytes,
                                     sizeof(source_bytes));
            qemu_log_mask(LOG_UNIMP,
                          "DMCU OBJECT0_MEMCPY destination=%06x source=%06x "
                          "length=%08x caller=%02x:%04x source-head="
                          "%016" PRIx64 "%016" PRIx64 "%016" PRIx64 "\n",
                          destination & MASK24, source & MASK24, length,
                          internal_data_read(old_sp & MASK16, 16) & 0xff,
                          internal_data_read((old_sp + 2) & MASK16, 16),
                          ldq_le_p(source_bytes), ldq_le_p(source_bytes + 8),
                          ldq_le_p(source_bytes + 16));
        }
    }

    /* 51:BC4C is the corresponding far memset.  Distinguish an intentional
     * pre-read clear from an over-wide or misaddressed clear. */
    if (start == 0x51bc4c) {
        uint32_t destination =
            ((internal_data_read((old_sp + 4) & MASK16, 16) & 0xff) << 16) |
            internal_data_read((old_sp + 6) & MASK16, 16);

        if (destination >= 0x5002a6 && destination < 0x5002be) {
            uint32_t length =
                ((uint32_t)internal_data_read((old_sp + 10) & MASK16, 16) << 16) |
                internal_data_read((old_sp + 12) & MASK16, 16);

            qemu_log_mask(LOG_UNIMP,
                          "DMCU OBJECT0_MEMSET destination=%06x value=%04x "
                          "length=%08x caller=%02x:%04x\n",
                          destination & MASK24,
                          internal_data_read((old_sp + 8) & MASK16, 16), length,
                          internal_data_read(old_sp & MASK16, 16) & 0xff,
                          internal_data_read((old_sp + 2) & MASK16, 16));
        }
    }

    /* The first NFTL scan reads the first, second, and redundant tail spare
     * records before deciding whether block one may be erased.  Keep the
     * exact decoded bytes visible while refining the resident BBF6 codec. */
    if (start == 0x5100b6 || start == 0x510128 ||
        start == 0x5101aa) {
        uint32_t block = internal_data_read(
            (env->gpr[DMCU_FP] + 6) & MASK16, 16);

        if (block == 1) {
            uint8_t spare[64];

            cpu_physical_memory_read(0x500760, spare, sizeof(spare));
            qemu_log_mask(LOG_UNIMP,
                          "DMCU NFTL_BLOCK1_SPARE pc=%02x:%04x "
                          "state5=%02x copies=%02x/%02x/%02x "
                          "head=%016" PRIx64 " tail=%016" PRIx64 "\n",
                          dmcu_code_segment(start), dmcu_code_pc(start),
                          spare[5], spare[0x37], spare[0x38], spare[0x39],
                          ldq_le_p(spare), ldq_le_p(spare + 56));
        }
    }

    if (start == 0x50811c) {
        uint32_t block = internal_data_read(
            (env->gpr[DMCU_FP] - 10) & MASK16, 16);

        if (block == 1) {
            qemu_log_mask(LOG_UNIMP,
                          "DMCU NFTL_BLOCK1_ERASE_PATH status=%04x "
                          "range-base=%04x pc=%02x:%04x\n",
                          internal_data_read(
                              (env->gpr[DMCU_FP] - 30) & MASK16, 16),
                          internal_data_read(
                              (env->gpr[DMCU_FP] - 6) & MASK16, 16),
                          dmcu_code_segment(start), dmcu_code_pc(start));
        }
    }

    /* Record the exact BDD6 call frame around the block-one metadata erase.
     * This is observational only: it lets the reconstructed-ROM probe use
     * the real argument, return address, DS0 mapping, and burner command. */
    if (start == 0x02bdd6) {
        uint32_t caller_cs = internal_data_read(old_sp & MASK16, 16) & 0xff;
        uint32_t caller_pc = internal_data_read((old_sp + 2) & MASK16, 16);
        uint32_t block = internal_data_read((old_sp + 4) & MASK16, 16);

        if (block == 1) {
            uint8_t physical_command[2];
            uint8_t mapped_command[2];
            uint32_t mapped_command_address =
                data_physical_address(env, 0x0008) & MASK24;

            cpu_physical_memory_read(0x500008, physical_command,
                                     sizeof(physical_command));
            cpu_physical_memory_read(mapped_command_address, mapped_command,
                                     sizeof(mapped_command));
            qemu_log_mask(LOG_UNIMP,
                          "DMCU BDD6_GUARD block=%04x caller=%02x:%04x "
                          "DS0=%03x mapped=%06x/%04x physical=%04x "
                          "sp=%04x fp=%04x\n",
                          block, caller_cs, caller_pc,
                          env->sfr[DMCU_SFR_DS0] & 0x1ff,
                          mapped_command_address,
                          lduw_le_p(mapped_command),
                          lduw_le_p(physical_command), old_sp, old_fp);
        }
    }

    if (start == 0x02bcc6) {
        uint32_t page_hi = internal_data_read((old_sp + 4) & MASK16, 16);
        uint32_t page_lo = internal_data_read((old_sp + 6) & MASK16, 16);
        uint32_t buffer_hi = internal_data_read((old_sp + 10) & MASK16, 16);
        uint32_t buffer_lo = internal_data_read((old_sp + 12) & MASK16, 16);
        uint32_t length = internal_data_read((old_sp + 14) & MASK16, 16);
        uint32_t flat = ((buffer_hi & MASK16) << 16) |
                        (buffer_lo & MASK16);
        uint32_t selected = buffer_hi ? flat :
                            data_physical_address(env, buffer_lo);
        uint8_t flat_bytes[8];
        uint8_t selected_bytes[8];
        uint8_t tail_bytes[16];
        uint8_t logical_spare[64];

        cpu_physical_memory_read(flat & MASK24, flat_bytes,
                                 sizeof(flat_bytes));
        cpu_physical_memory_read(selected & MASK24, selected_bytes,
                                 sizeof(selected_bytes));
        cpu_physical_memory_read((flat + (length >= 16 ? length - 16 : 0)) &
                                 MASK24, tail_bytes, sizeof(tail_bytes));
        cpu_physical_memory_read((selected + 0x200) & MASK24, logical_spare,
                                 sizeof(logical_spare));
        qemu_log_mask(LOG_UNIMP,
                      "DMCU BCC6 page=%04x:%04x length=%04x "
                      "buffer=%04x:%04x flat=%06x/%016" PRIx64
                      " selected=%06x/%016" PRIx64
                      " tail=%016" PRIx64 "%016" PRIx64
                      " DS0=%03x DS1=%03x caller=%02x:%04x\n",
                      page_hi & MASK16, page_lo & MASK16, length & MASK16,
                      buffer_hi & MASK16, buffer_lo & MASK16,
                      flat & MASK24, ldq_le_p(flat_bytes),
                      selected & MASK24, ldq_le_p(selected_bytes),
                      ldq_le_p(tail_bytes), ldq_le_p(tail_bytes + 8),
                      env->sfr[DMCU_SFR_DS0] & 0x1ff,
                      env->sfr[DMCU_SFR_DS1] & 0x1ff,
                      internal_data_read(old_sp & MASK16, 16) & 0xff,
                      internal_data_read((old_sp + 2) & MASK16, 16));
        qemu_log_mask(LOG_UNIMP,
                      "DMCU BCC6 logical-spare=%016" PRIx64
                      "%016" PRIx64 "%016" PRIx64 "%016" PRIx64
                      "%016" PRIx64 "%016" PRIx64 "%016" PRIx64
                      "%016" PRIx64 "\n",
                      ldq_le_p(logical_spare),
                      ldq_le_p(logical_spare + 8),
                      ldq_le_p(logical_spare + 16),
                      ldq_le_p(logical_spare + 24),
                      ldq_le_p(logical_spare + 32),
                      ldq_le_p(logical_spare + 40),
                      ldq_le_p(logical_spare + 48),
                      ldq_le_p(logical_spare + 56));
    }

    if (start == 0x518d8a) {
        env->partition_stage = 1;
    } else if (start == 0x518dac) {
        env->partition_stage = 2;
    } else if (start == 0x518dcc) {
        env->partition_stage = 3;
    } else if (start == 0x518e02) {
        env->partition_stage = 4;
        env->partition_value0 = ((env->gpr[0] & MASK16) << 16) |
                                (env->gpr[1] & MASK16);
    } else if (start == 0x518e56) {
        env->partition_stage = 0x56;
    } else if (start == 0x518e76) {
        env->partition_stage = 5;
        env->partition_value0 = env->gpr[0] & MASK16;
    } else if (start == 0x518e84) {
        env->partition_stage = 6;
        env->partition_value1 = env->gpr[0] & MASK16;
    } else if (start == 0x518e90) {
        env->partition_stage = 7;
        env->partition_result = env->gpr[0] & MASK16;
    } else if (start == 0x51cb62) {
        env->partition_stage = 0x10;
    } else if (start == 0x51cba0) {
        env->partition_stage = 0x11;
        env->partition_result = env->gpr[0] & MASK16;
    } else if (start == 0x51cbb6) {
        env->partition_result = env->gpr[0] & MASK16;
    } else if (start == 0x51cbcc) {
        env->partition_stage = 0x13;
        env->partition_result = env->gpr[0] & MASK16;
    } else if (start == 0x5109aa) {
        uint32_t probe_index = internal_data_read((old_fp - 2) & MASK16, 16);

        if (probe_index < 3) {
            env->partition_value1 &= ~(0xffu << (probe_index * 8));
            env->partition_value1 |= ((env->gpr[0] & 0xff) <<
                                      (probe_index * 8));
        }
    } else if (start == 0x510a0a) {
        env->partition_stage = 0x20;
        env->partition_value0 =
            internal_data_read((old_fp - 10) & MASK16, 16) << 16;
    } else if (start == 0x510a46) {
        env->partition_stage = 0x21;
        env->partition_value0 |= env->gpr[2] & MASK16;
    } else if (start == 0x510a64) {
        env->partition_stage = 0x22;
        env->partition_value1 = env->gpr[2] & MASK16;
    } else if (start == 0x510a74) {
        env->partition_stage = 0x23;
        env->partition_value0 = env->gpr[2] & MASK16;
    } else if (start == 0x510a98) {
        env->partition_stage = 0x24;
        env->partition_value1 = env->gpr[0] & MASK16;
    } else if (start == 0x510aba) {
        env->partition_stage = 0x25;
        env->partition_value1 = env->gpr[0] & MASK16;
    } else if (start == 0x510af0) {
        env->partition_stage = 0x2e;
        env->partition_result = env->gpr[0] & MASK16;
    } else if (start == 0x510af4) {
        env->partition_stage = 0x2f;
    } else if (start == 0x510b0e) {
        env->partition_stage = 0x30;
        env->partition_result = env->gpr[0] & MASK16;
    } else if (start == 0x50c45e) {
        env->partition_stage = 0x40;
        env->partition_value0 =
            (internal_data_read((old_fp - 4) & MASK16, 16) << 16) |
            internal_data_read((old_fp - 2) & MASK16, 16);
        env->partition_result = env->gpr[0] & MASK16;
    } else if (start == 0x50c4a4) {
        env->partition_stage = 0x41;
        env->partition_value0 = ((env->gpr[0] & MASK16) << 16) |
                                (env->gpr[1] & MASK16);
    } else if (start == 0x50c4c8) {
        env->partition_stage = 0x42;
        env->partition_value1 = ((env->gpr[0] & MASK16) << 16) |
                                (env->gpr[1] & MASK16);
    } else if (start == 0x50c4da) {
        env->partition_stage = 0x43;
        env->partition_result = ((env->gpr[0] | env->gpr[1]) & MASK16) != 0;
    }

    /*
     * The burner constructs four storage objects in sub_51_10EA, from
     * index 3 down to index 0.  A non-zero result from sub_51_A342 breaks
     * that loop, so a single final error value does not reveal which object
     * was left uninitialized.  Retain the per-call CB62 and final results;
     * this is observation only and does not alter the guest ROM outcome.
     */
    if (start == 0x51a34a) {
        uint32_t slot = env->object_init_count;

        if (slot < DMCU_OBJECT_INIT_TRACE_SLOTS) {
            env->object_init_index[slot] =
                internal_data_read((old_fp + 6) & MASK16, 16) & 0xff;
            env->object_init_cb62[slot] = 0xffffffffu;
            env->object_init_result[slot] = 0xffffffffu;
        }
        env->object_init_count++;
    } else if (start == 0x51a3a0) {
        uint32_t slot = env->object_init_count;

        if (slot && slot <= DMCU_OBJECT_INIT_TRACE_SLOTS) {
            env->object_init_cb62[slot - 1] = env->gpr[0] & MASK16;
        }
    } else if (start == 0x51a494) {
        uint32_t slot = env->object_init_count;

        if (slot && slot <= DMCU_OBJECT_INIT_TRACE_SLOTS) {
            env->object_init_result[slot - 1] = env->gpr[0] & MASK16;
        }
    } else if (start == 0x51137c) {
        env->object_init_loop_index =
            internal_data_read((old_fp - 2) & MASK16, 16) & 0xff;
        env->object_init_loop_result = env->gpr[0] & MASK16;
    }

    if (start == 0x51cb62) {
        uint32_t slot = env->cb62_calls;

        if (slot < DMCU_CB62_TRACE_SLOTS) {
            uint8_t command_bytes[2];

            cpu_physical_memory_read(0x500008, command_bytes,
                                     sizeof(command_bytes));
            env->cb62_history_command[slot] = lduw_le_p(command_bytes);
            env->cb62_history_geometry[slot] = 0xffffffffu;
            env->cb62_history_aa1a[slot] = 0xffffffffu;
            env->cb62_history_08a6[slot] = 0xffffffffu;
            env->cb62_history_7dd8[slot] = 0xffffffffu;
            env->cb62_history_result[slot] = 0xffffffffu;
        }
        env->cb62_calls++;
        env->cb62_stage = 0;
        env->cb62_geometry = 0;
        env->cb62_aa1a_result = 0xffffffffu;
        env->cb62_08a6_result = 0xffffffffu;
        env->cb62_7dd8_result = 0xffffffffu;
        env->cb62_result = 0xffffffffu;
    } else if (start == 0x51cb8c) {
        uint32_t slot = env->cb62_calls;

        env->cb62_stage = 1;
        env->cb62_geometry = ((env->gpr[0] & MASK16) << 16) |
                             (env->gpr[1] & MASK16);
        if (slot && slot <= DMCU_CB62_TRACE_SLOTS) {
            env->cb62_history_geometry[slot - 1] = env->cb62_geometry;
        }
    } else if (start == 0x51cba0) {
        uint32_t slot = env->cb62_calls;

        env->cb62_stage = 2;
        env->cb62_aa1a_result = env->gpr[0] & MASK16;
        if (slot && slot <= DMCU_CB62_TRACE_SLOTS) {
            env->cb62_history_aa1a[slot - 1] = env->cb62_aa1a_result;
        }
    } else if (start == 0x51cbb6) {
        uint32_t slot = env->cb62_calls;

        env->cb62_stage = 3;
        env->cb62_08a6_result = env->gpr[0] & MASK16;
        if (slot && slot <= DMCU_CB62_TRACE_SLOTS) {
            env->cb62_history_08a6[slot - 1] = env->cb62_08a6_result;
        }
    } else if (start == 0x51cbcc) {
        uint32_t slot = env->cb62_calls;

        env->cb62_stage = 4;
        env->cb62_7dd8_result = env->gpr[0] & MASK16;
        if (slot && slot <= DMCU_CB62_TRACE_SLOTS) {
            env->cb62_history_7dd8[slot - 1] = env->cb62_7dd8_result;
        }
    } else if (start == 0x51cbea) {
        uint32_t slot = env->cb62_calls;

        env->cb62_stage = 5;
        env->cb62_result = env->gpr[0] & MASK16;
        if (slot && slot <= DMCU_CB62_TRACE_SLOTS) {
            env->cb62_history_result[slot - 1] = env->cb62_result;
        }
    }

    /*
     * sub_50_B0B2 consumes the validated page-0x3f partition record and
     * materialises one storage object.  It owns several independent FFFE
     * exits, so retain the precise boundary without changing guest flow.
     */
    if (start == 0x50b0b2) {
        uint8_t command_bytes[2];

        cpu_physical_memory_read(0x500008, command_bytes,
                                 sizeof(command_bytes));
        env->b0b2_calls++;
        env->b0b2_command = lduw_le_p(command_bytes);
        env->b0b2_index = internal_data_read((old_fp + 6) & MASK16, 16) &
                          0xff;
        env->b0b2_stage = 0;
        env->b0b2_primary_pointer = 0xffffffffu;
        env->b0b2_secondary_pointer = 0xffffffffu;
        env->b0b2_7d66_result = 0xffffffffu;
        env->b0b2_global_after_7d66 = 0xffffffffu;
        env->b0b2_6816_result = 0xffffffffu;
        env->b0b2_failure_pc = 0;
        env->b0b2_result = 0xffffffffu;
    } else if (start == 0x50b5d2 || start == 0x50b5ec ||
               start == 0x50b606 || start == 0x50b622 ||
               start == 0x50b63e || start == 0x50b658 ||
               start == 0x50b65e) {
        /*
         * All seven validation branches converge on 50:B676.  The target
         * alone cannot identify which field rejected the object record, so
         * retain an opt-in execution log immediately after each comparison.
         * This is deliberately observational: flags and guest state are not
         * changed.
         */
        qemu_log_mask(LOG_UNIMP,
                      "DMCU B0B2_CHECK command=%04x index=%u "
                      "pc=%02x:%04x psw=%04x "
                      "r0=%04x r1=%04x r2=%04x r3=%04x "
                      "r4=%04x r5=%04x primary=%08x secondary=%08x\n",
                      env->b0b2_command & MASK16,
                      env->b0b2_index,
                      dmcu_code_segment(start), dmcu_code_pc(start),
                      env->psw & MASK16,
                      env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                      env->gpr[2] & MASK16, env->gpr[3] & MASK16,
                      env->gpr[4] & MASK16, env->gpr[5] & MASK16,
                      env->b0b2_primary_pointer,
                      env->b0b2_secondary_pointer);
    } else if (start == 0x50b114) {
        env->b0b2_primary_pointer = ((env->gpr[0] & MASK16) << 16) |
                                    (env->gpr[1] & MASK16);
    } else if (start == 0x50b166) {
        env->b0b2_secondary_pointer = ((env->gpr[0] & MASK16) << 16) |
                                      (env->gpr[1] & MASK16);
    } else if (start == 0x50b18e) {
        env->b0b2_stage = 1;
        env->b0b2_7d66_result = env->gpr[0] & MASK16;
    } else if (start == 0x50b198) {
        env->b0b2_stage = 2;
        env->b0b2_global_after_7d66 = env->gpr[0] & MASK16;
    } else if (start == 0x50b20c) {
        env->b0b2_stage = 3;
        env->b0b2_6816_result = env->gpr[0] & MASK16;
    } else if (start == 0x50b3a0) {
        uint8_t secondary[0x24] = { 0 };

        if (env->b0b2_secondary_pointer != 0xffffffffu) {
            cpu_physical_memory_read(env->b0b2_secondary_pointer,
                                     secondary, sizeof(secondary));
        }
        qemu_log_mask(LOG_UNIMP,
                      "DMCU B0B2_D5C6 command=%04x index=%u "
                      "result=%04x secondary13="
                      "%02x%02x%02x%02x secondary20="
                      "%02x%02x%02x%02x\n",
                      env->b0b2_command & MASK16, env->b0b2_index,
                      env->gpr[0] & MASK16,
                      secondary[0x13], secondary[0x14],
                      secondary[0x15], secondary[0x16],
                      secondary[0x20], secondary[0x21],
                      secondary[0x22], secondary[0x23]);
    } else if (start == 0x50b3c4) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU B0B2_C6AE command=%04x index=%u "
                      "result=%04x:%04x secondary=%08x\n",
                      env->b0b2_command & MASK16, env->b0b2_index,
                      env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                      env->b0b2_secondary_pointer);
    } else if (start == 0x50b414) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU B0B2_PRIMARY6_STORE command=%04x index=%u "
                      "value=%04x:%04x primary=%08x\n",
                      env->b0b2_command & MASK16, env->b0b2_index,
                      env->gpr[2] & MASK16, env->gpr[3] & MASK16,
                      env->b0b2_primary_pointer);
    } else if (start == 0x50b676) {
        env->b0b2_stage = 4;
        env->b0b2_failure_pc = start;
    } else if (start == 0x50b6c4) {
        env->b0b2_stage = 5;
        env->b0b2_failure_pc = start;
    } else if (start == 0x50b71e) {
        env->b0b2_stage = 6;
        env->b0b2_result = env->gpr[0] & MASK16;
    }

    if (start == 0x51c87e) {
        env->stream_guard_calls++;
    } else if (start == 0x51c914) {
        env->stream_guard_result = env->gpr[0] & MASK16;
    } else if (start == 0x51889c) {
        env->stream_arg0 = (internal_data_read(old_fp + 6, 16) << 16) |
                           internal_data_read(old_fp + 8, 16);
        env->stream_arg1 = (internal_data_read(old_fp + 10, 16) << 16) |
                           internal_data_read(old_fp + 12, 16);
        env->stream_arg2 = (internal_data_read(old_fp + 14, 16) << 16) |
                           internal_data_read(old_fp + 16, 16);
    } else if (start == 0x5188a8) {
        env->stream_source_check = ((env->gpr[0] & MASK16) << 16) |
                                   (env->gpr[1] & MASK16);
        env->stream_source_psw = env->psw;
    } else if (start == 0x5188b8) {
        env->stream_count_check = ((env->gpr[0] & MASK16) << 16) |
                                  (env->gpr[1] & MASK16);
        env->stream_count_psw = env->psw;
    } else if (start == 0x5188d0) {
        env->stream_bound_result = ((env->gpr[0] & MASK16) << 16) |
                                   (env->gpr[1] & MASK16);
        env->stream_bound_value = ((env->gpr[2] & MASK16) << 16) |
                                  (env->gpr[3] & MASK16);
        env->stream_bound_psw = env->psw;
    } else if (start == 0x5188d4 || start == 0x51899c) {
        if (!env->stream_stage_exit) {
            env->stream_stage_exit = start;
        }
        if (start == 0x5188d4) {
            env->stream_error_entries++;
            env->stream_error_psw = env->psw;
            if (env->exec_trace_count >= 2) {
                unsigned previous = (env->exec_trace_count - 2) %
                                    DMCU_EXEC_TRACE_WORDS;

                env->stream_error_from_pc = env->exec_trace_pc[previous];
                env->stream_error_from_word = env->exec_trace_word[previous];
            }
        }
    } else if (start == 0x518974) {
        env->stream_loop_entries++;
    } else if (start == 0x5189f2) {
        env->stream_loop_psw = env->psw;
    } else if (start == 0x51898c) {
        env->stream_page_calls++;
    } else if (start == 0x518992) {
        env->stream_page_result = env->gpr[0] & MASK16;
    }

    if (start == 0x5155e2) {
        env->stream_page_stage = 0;
    } else if (start == 0x5155f2) {
        env->stream_shift_input = ((env->gpr[0] & MASK16) << 16) |
                                  (env->gpr[1] & MASK16);
    } else if (start == 0x5155fa) {
        env->stream_shift_count = env->gpr[3] & MASK16;
    } else if (start == 0x515618) {
        env->stream_shift_result = ((env->gpr[0] & MASK16) << 16) |
                                   (env->gpr[1] & MASK16);
        env->stream_shift_buffer_result = env->shift_buffer & MASK16;
    } else if (start == 0x515694) {
        env->stream_page_stage = 1;
    } else if (start == 0x5156d2) {
        env->stream_page_stage = 2;
    } else if (start == 0x515716) {
        env->stream_page_stage = 3;
    } else if (start == 0x515744) {
        env->stream_page_stage = 4;
    } else if (start == 0x5157ac) {
        env->stream_page_stage = 5;
    } else if (start == 0x5158a8) {
        env->stream_page_stage = 6;
    } else if (start == 0x5158ac) {
        env->stream_page_stage = 7;
    }

    if (start == 0x512e1c) {
        env->stream_map_calls++;
    } else if (start == 0x512e28) {
        /* 2E24 has just loaded the caller's logical block into R1. */
        env->stream_map_arg = env->gpr[1] & MASK16;
    } else if (start == 0x513156) {
        env->stream_map_result = env->gpr[0] & MASK16;
    } else if (start == 0x5123f6) {
        env->stream_allocate_calls++;
        env->stream_allocate_arg = internal_data_read(old_fp + 6, 16);
    } else if (start == 0x512746) {
        env->stream_allocate_result = env->gpr[0] & MASK16;
    } else if (start == 0x516332) {
        env->stream_classify_calls++;
    } else if (start == 0x5165aa) {
        env->stream_classify_result = env->gpr[0] & MASK16;
    }

    if (start == dmcu_code_address(0x2c, 0xa7da) ||
        start == dmcu_code_address(0x2c, 0xa7dc) ||
        start == dmcu_code_address(0x2c, 0xa82a) ||
        start == dmcu_code_address(0x2c, 0xa9b4) ||
        start == dmcu_code_address(0x2c, 0xa9bc)) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU far-copy checkpoint %02x:%04x "
                      "sp=%04x fp=%04x word=%04x "
                      "args=%04x,%04x,%04x,%04x,%04x,%04x\n",
                      dmcu_code_segment(start), dmcu_code_pc(start),
                      old_sp, old_fp, word0 & MASK16,
                      rom_argument(env, 0), rom_argument(env, 1),
                      rom_argument(env, 2), rom_argument(env, 3),
                      rom_argument(env, 4), rom_argument(env, 5));
    }

    if (!env->rom_hle_enabled && start < DMCU_PROGRAM_BASE &&
        !execute_auxiliary && (!execute_resident_rom || skeleton_hole)) {
        CPUState *cs = env_cpu(env);

        if (!env->missing_rom_valid && env->exec_trace_count >= 2) {
            unsigned previous_slot = (env->exec_trace_count - 2) %
                                     DMCU_EXEC_TRACE_WORDS;

            env->missing_rom_previous_pc =
                env->exec_trace_pc[previous_slot] & MASK24;
            env->missing_rom_previous_word =
                env->exec_trace_word[previous_slot] & MASK16;
            env->missing_rom_sp = old_sp & MASK16;
            env->missing_rom_psw = env->psw & 15;
            env->missing_rom_in_interrupt = env->in_interrupt;
            if (env->control_trace_count) {
                unsigned control_slot = (env->control_trace_count - 1) %
                                        DMCU_CONTROL_TRACE_WORDS;

                env->missing_rom_control_from =
                    env->control_trace_from[control_slot] & MASK24;
                env->missing_rom_control_to =
                    env->control_trace_to[control_slot] & MASK24;
                env->missing_rom_control_word =
                    env->control_trace_word[control_slot] & MASK16;
                env->missing_rom_control_sp =
                    env->control_trace_sp[control_slot] & MASK16;
                env->missing_rom_control_fp =
                    env->control_trace_fp[control_slot] & MASK16;
            }
        }
        if (!env->missing_rom_valid || env->missing_rom_pc != start) {
            env->missing_rom_fetches++;
            qemu_log_mask(LOG_UNIMP,
                          "DMCU missing SoC ROM at %02x:%04x; CPU halted\n",
                          dmcu_code_segment(start), dmcu_code_pc(start));
        }
        env->missing_rom_pc = start;
        env->missing_rom_valid = true;
        /* Preserve the complete guest call chain that selected this missing
         * strict-ROM address. Timer IRQ return traffic otherwise overwrites
         * the circular control trace after the halted foreground task. */
        env->control_trace_frozen = true;
        env->pc = start;
        cs->halted = 1;
        cs->exception_index = EXCP_HLT;
        cpu_loop_exit(cs);
    }

    np560_hle_tick(env);
    if (np560_native_tick(env, start)) {
        return false;
    }
    env->pc = next;

    if (exec_alu(env, op, arg, ext) ||
        exec_move(env, op, arg, ext) ||
        exec_shift(env, op, arg) ||
        exec_bit(env, op, arg, ext) ||
        exec_control(env, op, arg, ext, start, next) ||
        exec_compare_update(env, op, arg, ext) ||
        exec_divide(env, op, arg) ||
        exec_exponent(env, op, arg)) {
        goto complete;
    }

    if (op == 0x0e) {
        value = env->gpr[arg >> 4];
        env->gpr[arg >> 4] = env->gpr[arg & 15];
        env->gpr[arg & 15] = value;
        goto complete;
    }
    if (op == 0x3e && (arg >> 4) <= 1) {
        int bits = (arg >> 4) ? 8 : 16;
        value = alu_sub(env, 0, reg_read(env, arg, bits), 0, bits, false);
        reg_write(env, arg, value, bits);
        goto complete;
    }
    if (op == 0xc0 || op == 0xc1) {
        int64_t product;
        left = env->gpr[arg >> 4] & MASK16;
        right = env->gpr[arg & 15] & MASK16;
        product = op == 0xc0 ? (int64_t)sext16(left) * sext16(right)
                             : (uint64_t)left * right;
        /* MUL/UMUL expose their 32-bit result in R6:R7.  R5 is not an
         * extension register: vendor helpers deliberately retain far-pointer
         * bases in R4:R5 across these instructions without saving R5. */
        env->gpr[6] = (product >> 16) & MASK16;
        env->gpr[7] = product & MASK16;
        set_flag(env, DMCU_PSW_Z, (uint32_t)product == 0);
        set_flag(env, DMCU_PSW_N, product & 0x80000000u);
        goto complete;
    }
    if (op == 0x1f) {
        if (arg & 0x80) {
            sfr_write(env, arg & 0x7f, pop(env), 16);
        } else {
            push(env, sfr_read(env, arg & 0x7f, 16));
        }
        goto complete;
    }
    if (op == 0x2e) {
        push(env, env->gpr[DMCU_FP]);
        env->gpr[DMCU_FP] = env->gpr[DMCU_SP];
        env->gpr[DMCU_SP] = (env->gpr[DMCU_SP] - arg * 2) & MASK16;
        goto complete;
    }
    if (op == 0x2f && arg == 0) {
        uint32_t frame_sp = env->gpr[DMCU_FP] & MASK16;
        uint32_t restored_fp = internal_data_read(frame_sp, 16);

        if (frame_sp >= 0x8000 && restored_fp < 0x8000) {
            qemu_log_mask(LOG_UNIMP,
                          "DMCU UNLINK restores low FP at %02x:%04x "
                          "sp=%04x fp=%04x saved=%04x "
                          "near=%04x,%04x,%04x,%04x\n",
                          dmcu_code_segment(start), dmcu_code_pc(start),
                          env->gpr[DMCU_SP] & MASK16, frame_sp, restored_fp,
                          internal_data_read((frame_sp + 2) & MASK16, 16),
                          internal_data_read((frame_sp + 4) & MASK16, 16),
                          internal_data_read((frame_sp + 6) & MASK16, 16),
                          internal_data_read((frame_sp + 8) & MASK16, 16));
        }
        env->gpr[DMCU_SP] = env->gpr[DMCU_FP];
        env->gpr[DMCU_FP] = pop(env);
        goto complete;
    }
    if (op == 0xc7 && arg == 0) {
        goto complete;
    }
    if (op == 0x3f && arg <= 3) {
        /*
         * CRIT #imm2 prevents hardware interrupts during the following
         * imm2+1 instructions.  The compiler uses CRIT #1 around two-step
         * byte-stack sequences which temporarily leave R15 unaligned.
         */
        env->critical_count = (arg & 3) + 1;
        goto complete;
    }
    if (op == 0x3f && arg >= 0x10 && arg <= 0x13) {
        env->ignore_ds_count = (arg & 3) + 1;
        tlb_flush(env_cpu(env));
        goto complete;
    }
    if (op == 0xbf && arg == 0) {
        env->repeat_pc = next;
        env->repeat_end = next;
        env->repeat_count = (uint32_t)ext + 1;
        env->repeat_block = false;
        goto complete;
    }
    if (op == 0xcf && (arg >> 4) == 0) {
        env->repeat_pc = next;
        env->repeat_end = next;
        env->repeat_count = (env->gpr[arg & 15] & MASK16) + 1;
        env->repeat_block = false;
        goto complete;
    }
    if (op == 0xae || (op == 0xaf && (arg >> 4) == 0)) {
        env->repeat_pc = next;
        env->repeat_end = near_pc(start, ext);
        env->repeat_count = (op == 0xae ? arg : env->gpr[arg & 15]) + 1;
        env->repeat_block = true;
        goto complete;
    }
    if (op == 0x0f) {
        qemu_log_mask(LOG_UNIMP, "DMCU TRAP %02x stubbed\n", arg);
        goto complete;
    }
    unsupported(env, start, word0);

complete:
    if (env->root_resource_trace_active == 1u) {
        int math_stage = -1;

        if (start == dmcu_code_address(0x29, 0xadca)) {
            math_stage = 0;
        } else if (start == dmcu_code_address(0x29, 0xadec)) {
            math_stage = 1;
        } else if (start == dmcu_code_address(0x29, 0xae5c)) {
            math_stage = 2;
        } else if (start == dmcu_code_address(0x29, 0xae5e)) {
            math_stage = 3;
        } else if (start == dmcu_code_address(0x29, 0xae60)) {
            math_stage = 4;
        } else if (start == dmcu_code_address(0x29, 0xae62)) {
            math_stage = 5;
        } else if (start == dmcu_code_address(0x29, 0xae64)) {
            math_stage = 6;
        } else if (start == dmcu_code_address(0x33, 0x07e2)) {
            math_stage = 7;
        } else if (start == dmcu_code_address(0x29, 0xae70)) {
            math_stage = 8;
        } else if (start == dmcu_code_address(0x29, 0xae7a)) {
            math_stage = 9;
        } else if (start == dmcu_code_address(0x29, 0xae7c)) {
            math_stage = 10;
        } else if (start == dmcu_code_address(0x29, 0xae82)) {
            math_stage = 11;
        }
        if (math_stage >= 0) {
            uint16_t frame = env->root_resource_trace_fp[0];

            env->root_top_math_seen |= 1u << math_stage;
            env->root_top_math[math_stage][0] = env->gpr[0] & MASK16;
            env->root_top_math[math_stage][1] = env->gpr[1] & MASK16;
            env->root_top_math[math_stage][2] = env->gpr[2] & MASK16;
            env->root_top_math[math_stage][3] = env->gpr[3] & MASK16;
            env->root_top_math[math_stage][4] = frame ?
                internal_data_read((frame + 6u) & MASK16, 16) : 0xffffu;
            env->root_top_math[math_stage][5] = frame ?
                internal_data_read((frame + 8u) & MASK16, 16) : 0xffffu;
            env->root_top_math[math_stage][6] = env->gpr[DMCU_SP] & MASK16;
            env->root_top_math[math_stage][7] = env->psw & 15u;
        }
    }
    if (state50_branch_trace_active &&
        dmcu_code_segment(start) == 0x0c &&
        (op == 0xac || op == 0xad || op == 0xbc || op == 0xbd ||
         op == 0xcc || op == 0xcd || op == 0xce ||
         (op >= 0xd0 && op <= 0xde) ||
         (op == 0xc6 && (arg == 0x00 || arg == 0x10 || arg == 0x20)))) {
        if (state50_branch_trace_steps < 12000) {
            qemu_log_mask(
                LOG_UNIMP,
                "DMCU state50 branch #%u %02x:%04x/%04x "
                "fall=%02x:%04x to=%02x:%04x psw=%x "
                "r=%04x,%04x,%04x,%04x sp=%04x fp=%04x\n",
                state50_branch_trace_steps + 1,
                dmcu_code_segment(start), dmcu_code_pc(start),
                word0 & MASK16,
                dmcu_code_segment(next), dmcu_code_pc(next),
                dmcu_code_segment(env->pc), dmcu_code_pc(env->pc),
                env->psw & 15,
                env->gpr[0] & MASK16, env->gpr[1] & MASK16,
                env->gpr[2] & MASK16, env->gpr[3] & MASK16,
                env->gpr[DMCU_SP] & MASK16,
                env->gpr[DMCU_FP] & MASK16);
        }
        state50_branch_trace_steps++;
    }
    if (state50_branch_trace_active &&
        start == dmcu_code_address(0x0c, 0x4a6a) &&
        env->pc == dmcu_code_address(0x32, 0xc006)) {
        uint16_t state = address_space_lduw_le(
            &address_space_memory, 0x512aaa,
            MEMTXATTRS_UNSPECIFIED, NULL);
        uint16_t phase = address_space_lduw_le(
            &address_space_memory, 0x512aa0,
            MEMTXATTRS_UNSPECIFIED, NULL);

        qemu_log_mask(
            LOG_UNIMP,
            "DMCU state50 branch trace end steps=%u result=%04x:%04x "
            "state=%04x phase=%04x sp=%04x fp=%04x\n",
            state50_branch_trace_steps,
            env->gpr[0] & MASK16, env->gpr[1] & MASK16,
            state, phase,
            env->gpr[DMCU_SP] & MASK16,
            env->gpr[DMCU_FP] & MASK16);
        state50_branch_trace_active = false;
    }
    /* Follow the complete guest-side path which constructs and consumes the
     * transient 51:1E2C UI-record queue.  These PCs cover the foreground
     * parent clear, callback tail, seven-word wrapper, record builder, queue
     * consumer and root-controller destination.  Sample after the selected
     * instruction has executed, while retaining its pre-instruction SP/FP.
     * No guest register, memory, timing source, event or control flow changes. */
    if (start == dmcu_code_address(0x2f, 0xc59a) ||
        start == dmcu_code_address(0x2f, 0xc5c2) ||
        start == dmcu_code_address(0x2f, 0xc5ce) ||
        start == dmcu_code_address(0x2f, 0xc5d2) ||
        start == dmcu_code_address(0x2f, 0xc5da) ||
        start == dmcu_code_address(0x24, 0x162c) ||
        start == dmcu_code_address(0x24, 0x1a5c) ||
        start == dmcu_code_address(0x24, 0x1a62) ||
        start == dmcu_code_address(0x24, 0x1a66) ||
        start == dmcu_code_address(0x24, 0x1a96) ||
        start == dmcu_code_address(0x32, 0x8268) ||
        start == dmcu_code_address(0x32, 0x82be) ||
        start == dmcu_code_address(0x32, 0x82c2) ||
        start == dmcu_code_address(0x32, 0x82ca) ||
        start == dmcu_code_address(0x22, 0xfd9e) ||
        start == dmcu_code_address(0x22, 0xfdc0) ||
        start == dmcu_code_address(0x22, 0xfdc6) ||
        start == dmcu_code_address(0x22, 0xffea) ||
        start == dmcu_code_address(0x22, 0xffec) ||
        start == dmcu_code_address(0x22, 0xfffc) ||
        start == dmcu_code_address(0x28, 0x82f4) ||
        start == dmcu_code_address(0x28, 0x83ce) ||
        start == dmcu_code_address(0x28, 0x83d0) ||
        start == dmcu_code_address(0x28, 0x83e2) ||
        start == dmcu_code_address(0x28, 0x83e6) ||
        start == dmcu_code_address(0x28, 0x83fa) ||
        start == dmcu_code_address(0x28, 0x84b8) ||
        start == dmcu_code_address(0x28, 0x84ba) ||
        start == dmcu_code_address(0x28, 0x84cc) ||
        start == dmcu_code_address(0x28, 0x84d0) ||
        start == dmcu_code_address(0x28, 0x84e4) ||
        start == dmcu_code_address(0x29, 0x24c6) ||
        start == dmcu_code_address(0x1f, 0xf470) ||
        start == dmcu_code_address(0x1f, 0xf48a) ||
        start == dmcu_code_address(0x1f, 0xf510) ||
        start == dmcu_code_address(0x1f, 0xf7dc) ||
        start == dmcu_code_address(0x1f, 0xf95c) ||
        start == dmcu_code_address(0x1f, 0xf9ce) ||
        start == dmcu_code_address(0x1f, 0xfa30) ||
        start == dmcu_code_address(0x1f, 0xfa36) ||
        start == dmcu_code_address(0x26, 0x371e) ||
        start == dmcu_code_address(0x26, 0x3732) ||
        start == dmcu_code_address(0x26, 0x3746) ||
        start == dmcu_code_address(0x26, 0x37c6) ||
        start == dmcu_code_address(0x26, 0x37ca) ||
        start == dmcu_code_address(0x26, 0x37e0) ||
        start == dmcu_code_address(0x26, 0x3800) ||
        start == dmcu_code_address(0x26, 0x381c) ||
        start == dmcu_code_address(0x26, 0x388e) ||
        start == dmcu_code_address(0x26, 0x390e) ||
        start == dmcu_code_address(0x26, 0x393a) ||
        start == dmcu_code_address(0x26, 0x39ba) ||
        start == dmcu_code_address(0x26, 0x3a1e) ||
        start == dmcu_code_address(0x26, 0x3a62) ||
        start == dmcu_code_address(0x26, 0x3aa0) ||
        start == dmcu_code_address(0x26, 0x3aaa) ||
        start == dmcu_code_address(0x26, 0x3aac) ||
        start == dmcu_code_address(0x2e, 0xdb9c) ||
        start == dmcu_code_address(0x2e, 0xdc9c) ||
        start == dmcu_code_address(0x2e, 0xdcfa) ||
        start == dmcu_code_address(0x5f, 0x17c4) ||
        start == dmcu_code_address(0x5f, 0x17c8) ||
        start == dmcu_code_address(0x1d, 0xf2ec)) {
        unsigned flow_slot = env->ui_record_flow_count %
                             DMCU_UI_RECORD_FLOW_SLOTS;
        unsigned index;

        env->ui_record_flow_pc[flow_slot] = start & MASK24;
        env->ui_record_flow_next[flow_slot] = env->pc & MASK24;
        env->ui_record_flow_sp[flow_slot] = old_sp & MASK16;
        env->ui_record_flow_fp[flow_slot] = old_fp & MASK16;
        for (index = 0; index < 4; index++) {
            env->ui_record_flow_r[flow_slot][index] =
                env->gpr[index] & MASK16;
        }
        for (index = 0; index < DMCU_UI_RECORD_STACK_WORDS; index++) {
            env->ui_record_flow_stack[flow_slot][index] =
                internal_data_read((old_sp + index * 2u) & MASK16, 16);
        }
        for (index = 0; index < DMCU_UI_RECORD_FRAME_WORDS; index++) {
            env->ui_record_flow_frame[flow_slot][index] =
                internal_data_read((old_fp + 6u + index * 2u) & MASK16, 16);
        }
        {
            static const uint32_t global_addresses
                [DMCU_UI_RECORD_GLOBAL_WORDS] = {
                    0x512990u, 0x512992u, 0x51293cu, 0x51293eu,
                    0x512944u, 0x512946u, 0x512250u, 0x51226au,
                    0x51226cu, 0x51226eu, 0x512270u, 0x512272u,
                    0x51297cu, 0x51297eu, 0x512a3au, 0x512a38u,
                    0x5128f6u, 0x5128f8u, 0x5128fau, 0x5128fcu,
                    0x5128feu, 0x512a3cu,
                };

            for (index = 0; index < DMCU_UI_RECORD_GLOBAL_WORDS; index++) {
                env->ui_record_flow_globals[flow_slot][index] =
                    address_space_lduw_le(
                        &address_space_memory, global_addresses[index],
                        MEMTXATTRS_UNSPECIFIED, NULL);
            }
        }
        for (index = 0; index < DMCU_UI_RECORD_OBJECT_WORDS; index++) {
            env->ui_record_flow_object[flow_slot][index] =
                address_space_lduw_le(&address_space_memory,
                                      0x511e2cu + index * 2u,
                                      MEMTXATTRS_UNSPECIFIED, NULL);
        }
        env->ui_record_flow_count++;
    }

    /* Keep the last architecturally completed instruction separate from the
     * circular execution trace.  This is especially useful at IRQ entry:
     * env->pc must name either this instruction's result or a later complete
     * instruction, never the extension word of a 32-bit instruction. */
    env->completed_instruction_pc = start & MASK24;
    env->completed_instruction_next_pc = env->pc & MASK24;
    env->completed_instruction_word = word0 & MASK16;
    env->completed_instruction_ext = ext & MASK16;
    if (start == dmcu_code_address(0x1d, 0xf30a)) {
        /* F30A is the second half of the exact object-pointer save. */
        env->root_object_slot_watch_active = true;
        env->root_object_slot_first_bad_valid = false;
        env->root_object_slot_watch_address = (old_fp - 2u) & MASK16;
        env->root_object_slot_expected = internal_data_read(
            env->root_object_slot_watch_address, 16);
        env->root_object_slot_writes = 0;
    }
    if (start == dmcu_code_address(0x1d, 0xf9ba)) {
        /* The saved-local stack slot is no longer owned by the controller
         * after its RETS.  Disarm before ordinary stack reuse creates false
         * first-writer reports. */
        env->root_object_slot_watch_active = false;
    }
    if (start == dmcu_code_address(0x10, 0xf438) ||
        start == dmcu_code_address(0x10, 0xf938)) {
        uint32_t sequence = env->root_render_flag_trace_count++;
        uint32_t slot = sequence % DMCU_ROOT_RENDER_FLAG_TRACE_SLOTS;

        /* F438 and F938 have just loaded the same per-item descriptor flag
         * word before testing 0x4000 (text) and 0x8000 (bitmap).  Preserve
         * the exact word and its guest data address for each of the five
         * natural root rows. */
        env->root_render_flag_trace_pc[slot] = start & MASK24;
        env->root_render_flag_trace_logical[slot] = env->gpr[3] & MASK16;
        env->root_render_flag_trace_source[slot] =
            data_physical_address(env, env->gpr[3]) & MASK24;
        env->root_render_flag_trace_item[slot] =
            internal_data_read((old_fp - 4u) & MASK16, 16);
        env->root_render_flag_trace_value[slot] = env->gpr[2] & MASK16;
        env->root_render_flag_trace_ds0[slot] =
            env->sfr[DMCU_SFR_DS0] & 0x1ffu;
        env->root_render_flag_trace_ds1[slot] =
            env->sfr[DMCU_SFR_DS1] & 0x1ffu;
    }
    if (start == dmcu_code_address(0x1d, 0xf8fc)) {
        uint32_t object =
            ((uint32_t)(internal_data_read((old_fp - 4u) & MASK16, 16) &
                        0xffu) << 16) |
            internal_data_read((old_fp - 2u) & MASK16, 16);
        unsigned int word;

        /* Exact root-controller item-loop comparison.  Retain both operands,
         * the controller's saved object pointer and incoming frame, the
         * resulting flags, and the architectural next PC.  This distinguishes
         * an object-content fault from an indirect-call ABI mismatch without
         * altering guest registers or memory. */
        env->root_loop_compare_count++;
        env->root_loop_compare_index = env->gpr[0] & MASK16;
        env->root_loop_compare_limit = env->gpr[2] & MASK16;
        env->root_loop_compare_psw = env->psw & 0x000fu;
        env->root_loop_compare_next = env->pc & MASK24;
        env->root_loop_compare_fp = old_fp;
        env->root_loop_local_object = object & MASK24;
        env->root_loop_local_count = address_space_lduw_le(
            &address_space_memory, (object + 0x08u) & MASK24,
            MEMTXATTRS_UNSPECIFIED, NULL);
        for (word = 0; word < ARRAY_SIZE(env->root_loop_frame_words);
             word++) {
            env->root_loop_frame_words[word] =
                internal_data_read((old_fp + 6u + word * 2u) & MASK16, 16);
        }
    }
    if (start == dmcu_code_address(0x1d, 0xf6d8)) {
        uint32_t object =
            ((uint32_t)(internal_data_read((old_fp - 4u) & MASK16, 16) &
                        0xffu) << 16) |
            internal_data_read((old_fp - 2u) & MASK16, 16);

        env->root_loop_body_count++;
        env->root_loop_object = object & MASK24;
        env->root_loop_event = address_space_lduw_le(
            &address_space_memory, (object + 0x42u) & MASK24,
            MEMTXATTRS_UNSPECIFIED, NULL);
    }
    if (env->root_bitmap_resource_calls != 0 &&
        (start == dmcu_code_address(0x26, 0xd1ba) ||
         start == dmcu_code_address(0x26, 0xd1c4) ||
         start == dmcu_code_address(0x26, 0xd1d0) ||
         start == dmcu_code_address(0x26, 0xd1de) ||
         start == dmcu_code_address(0x26, 0xd1e4) ||
         start == dmcu_code_address(0x26, 0xd24a))) {
        unsigned trace = (env->root_bitmap_resource_calls - 1u) %
                         DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS;
        unsigned index;
        uint16_t stage;

        if (start == dmcu_code_address(0x26, 0xd24a)) {
            stage = 7;
        } else if ((env->pc & MASK24) ==
                   dmcu_code_address(0x26, 0xd28e)) {
            stage = 1u + (start == dmcu_code_address(0x26, 0xd1c4)) +
                    2u * (start == dmcu_code_address(0x26, 0xd1d0)) +
                    3u * (start == dmcu_code_address(0x26, 0xd1de)) +
                    4u * (start == dmcu_code_address(0x26, 0xd1e4));
        } else if (start == dmcu_code_address(0x26, 0xd1e4)) {
            stage = 6;
        } else {
            stage = 0;
        }
        if (stage != 0) {
            env->root_bitmap_resource_gate[trace] = stage;
        }
        env->root_bitmap_resource_next[trace] = env->pc & MASK24;
        env->root_bitmap_resource_r0[trace] = env->gpr[0] & MASK16;
        env->root_bitmap_resource_r1[trace] = env->gpr[1] & MASK16;
        {
            static const int16_t offsets[5] = {
                -0x9e, -0x8a, -0x06, -0x98, -0x04,
            };
            for (index = 0; index < ARRAY_SIZE(offsets); index++) {
                env->root_bitmap_resource_locals[trace][index] =
                    internal_data_read((old_fp + offsets[index]) & MASK16,
                                       16);
            }
        }
    }
    if (start == dmcu_code_address(0x2e, 0xbe2e) && word0 == 0x2e09u) {
        uint32_t anchor = env->gpr[DMCU_FP] & MASK16;

        env->application_file_attach_frame_calls++;
        env->application_file_attach_frame_watch_active = true;
        env->application_file_attach_frame_exit_valid = false;
        env->application_file_attach_frame_address = anchor;
        env->application_file_attach_frame_expected =
            internal_data_read(anchor, 16);
    }
    if (start == dmcu_code_address(0x2e, 0xbf96) && word0 == 0x2f00u &&
        env->application_file_attach_frame_watch_active) {
        env->application_file_attach_frame_exit_valid = true;
        env->application_file_attach_frame_exit_sp =
            env->gpr[DMCU_SP] & MASK16;
        env->application_file_attach_frame_exit_fp =
            env->gpr[DMCU_FP] & MASK16;
        env->application_file_attach_frame_watch_active = false;
    }
    if (env->direct_menu_stack_watch_active &&
        !env->direct_menu_stack_escape_valid) {
        uint16_t new_sp = env->gpr[DMCU_SP] & MASK16;
        uint16_t new_fp = env->gpr[DMCU_FP] & MASK16;
        uint32_t escape_kind = 0;

        if (old_sp <= (env->direct_menu_stack_arm_sp & MASK16) &&
            new_sp > (env->direct_menu_stack_arm_sp & MASK16)) {
            escape_kind |= DMCU_DIRECT_MENU_STACK_ESCAPE_SP;
        }
        if (old_fp <= (env->direct_menu_stack_arm_fp & MASK16) &&
            new_fp > (env->direct_menu_stack_arm_fp & MASK16)) {
            escape_kind |= DMCU_DIRECT_MENU_STACK_ESCAPE_FP;
        }
        if (escape_kind) {
            dmcu_record_direct_menu_stack_escape(
                DMCU_CPU(env_cpu(env)), escape_kind, start, env->pc,
                word0, ext, old_sp, old_fp);
        }
    }
    /* 33:529e is an exact compiler epilogue which restores R3..R0 from a
     * frame at the very top of the 16-bit internal stack.  Its final POP at
     * 33:52a4 legitimately advances SP from fffe to 0000 for one
     * instruction; the immediately following UNLINK restores SP from the
     * still-high FP before RETS.  Keep this witnessed wrap visible, but do
     * not classify it as the stack corruption FIRST_LOW_SP is meant to gate.
     */
    bool benign_sp_wrap =
        (start & MASK24) == 0x3352a4u &&
        (env->pc & MASK24) == 0x3352a6u &&
        (word0 & MASK16) == 0x380fu &&
        old_sp == 0xfffeu &&
        (env->gpr[DMCU_SP] & MASK16) == 0x0000u &&
        old_fp == 0xfff8u &&
        (env->gpr[DMCU_FP] & MASK16) == 0xfff8u;

    if (benign_sp_wrap) {
        env->benign_sp_wraps++;
        env->benign_sp_wrap_pc = start & MASK24;
        env->benign_sp_wrap_word = word0 & MASK16;
    }
    if (!benign_sp_wrap && !env->first_low_sp_valid && old_sp >= 0x8000 &&
        (env->gpr[DMCU_SP] & MASK16) < 0x8000) {
        unsigned int n;

        env->first_low_sp_valid = true;
        env->first_low_sp_pc = start & MASK24;
        env->first_low_sp_next_pc = env->pc & MASK24;
        env->first_low_sp_word = word0 & MASK16;
        env->first_low_sp_old = old_sp;
        env->first_low_sp_new = env->gpr[DMCU_SP] & MASK16;
        env->first_low_sp_old_fp = old_fp;
        env->first_low_sp_new_fp = env->gpr[DMCU_FP] & MASK16;
        for (n = 0; n < ARRAY_SIZE(env->first_low_sp_gpr); n++) {
            env->first_low_sp_gpr[n] = env->gpr[n] & MASK16;
        }

        /* This wrap is an observed outer-frame task handoff.  Keep tracing:
         * a later invalid transfer is more actionable than the first
         * scheduler stack wrap and freezes the ring on its own. */
    }
    if (!env->first_low_fp_valid && old_fp >= 0x8000 &&
        (env->gpr[DMCU_FP] & MASK16) < 0x8000 &&
        !(op == 0x2f && arg == 0)) {
        env->first_low_fp_valid = true;
        env->first_low_fp_pc = start & MASK24;
        env->first_low_fp_word = word0 & MASK16;
        env->first_low_fp_old = old_fp;
        env->first_low_fp_new = env->gpr[DMCU_FP] & MASK16;
        env->first_low_fp_sp = env->gpr[DMCU_SP] & MASK16;
    }
    if (old_fp >= 0x8000 && (env->gpr[DMCU_FP] & MASK16) < 0x8000 &&
        !(op == 0x2f && arg == 0)) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU FP crossed 8000 at %02x:%04x: %04x -> %04x "
                      "sp=%04x word=%04x\n",
                      dmcu_code_segment(start), dmcu_code_pc(start), old_fp,
                      env->gpr[DMCU_FP] & MASK16,
                      env->gpr[DMCU_SP] & MASK16, word0 & MASK16);
    }
    if (!benign_sp_wrap && old_sp >= 0x8000 &&
        (env->gpr[DMCU_SP] & MASK16) < 0x8000) {
        qemu_log_mask(LOG_UNIMP,
                      "DMCU SP crossed 8000 at %02x:%04x: %04x -> %04x "
                      "word=%04x\n",
                      dmcu_code_segment(start), dmcu_code_pc(start), old_sp,
                      env->gpr[DMCU_SP] & MASK16, word0 & MASK16);
    }
    if (was_ignoring_ds && env->ignore_ds_count) {
        if (!--env->ignore_ds_count) {
            tlb_flush(env_cpu(env));
        }
    }
    if (was_critical && env->critical_count) {
        env->critical_count--;
    }
    /* A single translated block may contain several helper calls.  Do not
     * let an instruction following a DS0/DS1 or IGNDS transition reuse the
     * TLB mapping under which the block began.  The individual SFR/IGNDS
     * operations already flush the TLB; returning false here also makes the
     * architectural transition an exact TB boundary. */
    address_space_changed =
        old_ds0 != (env->sfr[DMCU_SFR_DS0] & 0x1ff) ||
        old_ds1 != (env->sfr[DMCU_SFR_DS1] & 0x1ff) ||
        was_ignoring_ds != (env->ignore_ds_count != 0);
    if (!env->repeat_count) {
        trace_control_transfer(env, start, next, word0, old_sp, old_fp);
        return env->pc == next && !address_space_changed;
    }
    if (env->repeat_block) {
        if (env->pc == env->repeat_end) {
            if (--env->repeat_count) {
                env->pc = env->repeat_pc;
            } else {
                env->repeat_block = false;
            }
        }
    } else if (start == env->repeat_pc) {
        if (--env->repeat_count) {
            env->pc = env->repeat_pc;
        }
    }
    trace_control_transfer(env, start, next, word0, old_sp, old_fp);
    return env->pc == next && !address_space_changed;
}

hwaddr dmcu_cpu_get_phys_page_debug(CPUState *cs, vaddr addr)
{
    return addr;
}

bool dmcu_cpu_tlb_fill(CPUState *cs, vaddr address, int size,
                       MMUAccessType access_type, int mmu_idx,
                       bool probe, uintptr_t retaddr)
{
    hwaddr vpage = address & TARGET_PAGE_MASK;
    hwaddr ppage;
    int prot;
    MemTxAttrs attrs = { };

    if (mmu_idx == MMU_CODE_IDX) {
        ppage = vpage & MASK24;
        prot = PAGE_READ | PAGE_EXEC;
        attrs.secure = 1;
    } else {
        CPUDMCUState *env = &DMCU_CPU(cs)->env;
        uint32_t logical = vpage & 0xffff;
        uint32_t segment;

        if (env->ignore_ds_count) {
            /* IGNDS exposes the unbanked internal/SFR view.  Give the two
             * pages containing modeled devices private physical aliases so
             * ordinary banked RAM at 00:0000 and 00:F000 remains distinct. */
            if (logical == 0x0000) {
                ppage = DMCU_UNBANKED_LOW_PAGE_BASE;
            } else if (logical == 0xf000) {
                ppage = DMCU_UNBANKED_SFR_PAGE_BASE;
            } else {
                ppage = logical;
            }
        } else {
            segment = env->sfr[(logical & 0x8000) ? DMCU_SFR_DS1
                                                  : DMCU_SFR_DS0] & 0x1ff;
            ppage = ((segment << 15) | (logical & 0x7fff)) & MASK24;
        }
        prot = PAGE_READ | PAGE_WRITE;
    }
    tlb_set_page_with_attrs(cs, vpage, ppage, attrs, prot, mmu_idx,
                            TARGET_PAGE_SIZE);
    return true;
}
