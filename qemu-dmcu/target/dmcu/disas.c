/* Minimal disassembler for the King Billion DMCU instruction set. */

#include "qemu/osdep.h"
#include "disas/dis-asm.h"
#include "cpu.h"

static const char * const alu_name[8] = {
    "add", "addc", "sub", "subc", "and", "or", "cmp", "xor"
};

static const char * const condition_name[15] = {
    "always", "z", "nz", "v", "nv", "c", "nc", "n",
    "nn", "sl", "ug", "sg", "ule", "sle", "sge"
};

static bool is_32bit(uint16_t word)
{
    uint8_t op = word >> 8;
    uint8_t arg = word;
    uint8_t hi = op >> 4;
    uint8_t lo = op & 15;

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

static int read_word(bfd_vma addr, disassemble_info *info, uint16_t *word)
{
    bfd_byte bytes[2];
    int status = info->read_memory_func(addr, bytes, sizeof(bytes), info);

    if (status) {
        info->memory_error_func(status, addr, info);
        return status;
    }
    *word = bytes[0] | ((uint16_t)bytes[1] << 8);
    return 0;
}

int dmcu_print_insn(bfd_vma addr, disassemble_info *info)
{
    uint16_t word, ext = 0;
    uint8_t op, arg, hi, lo;
    bool wide;
    int size;

    if (read_word(addr, info, &word)) {
        return -1;
    }
    op = word >> 8;
    arg = word;
    hi = op >> 4;
    lo = op & 15;
    wide = is_32bit(word);
    size = wide ? 4 : 2;
    if (wide && read_word(dmcu_code_advance(addr, 2), info, &ext)) {
        return -1;
    }

    if (lo <= 7) {
        const char *suffix = !(hi & 1) ? "b" : "";
        if (hi <= 1) {
            info->fprintf_func(info->stream, "%s%s r%u, r%u", alu_name[lo],
                               suffix, arg >> 4, arg & 15);
            return size;
        }
        if (hi <= 3) {
            info->fprintf_func(info->stream, "%s%s r%u, [r%u%s]",
                               alu_name[lo], suffix, arg >> 4,
                               8 + (arg & 7), arg & 8 ? "++" : "");
            return size;
        }
        if (hi <= 5) {
            info->fprintf_func(info->stream, "%s%s r%u, #0x%x",
                               alu_name[lo], suffix, arg >> 4, arg & 15);
            return size;
        }
        if (hi <= 7) {
            info->fprintf_func(info->stream, "%s%s reg[0x%02x], #0x%04x",
                               alu_name[lo], suffix, arg, ext);
            return size;
        }
        if (hi <= 9) {
            info->fprintf_func(info->stream, "%s%s reg[0x%02x], [0x%04x]",
                               alu_name[lo], suffix, arg, ext);
            return size;
        }
        if (hi <= 11 && lo != 6) {
            info->fprintf_func(info->stream, "%s%s [0x%04x], reg[0x%02x]",
                               alu_name[lo], suffix, ext, arg);
            return size;
        }
    }

    switch (op) {
    case 0x08: case 0x09:
        info->fprintf_func(info->stream, "mov%s r%u, r%u",
                           op & 1 ? "b" : "", arg >> 4, arg & 15);
        break;
    case 0x0a: case 0x0b:
        info->fprintf_func(info->stream, "mov%s [r%u], %s%u",
                           op & 1 ? "b" : "", arg >> 4,
                           op & 1 ? "rb" : "r", arg & 15);
        break;
    case 0x28: case 0x29:
        info->fprintf_func(info->stream, "mov%s %s%u, [r%u]",
                           op & 1 ? "b" : "", op & 1 ? "rb" : "r",
                           arg >> 4, arg & 15);
        break;
    case 0x38: case 0x39:
        info->fprintf_func(info->stream, "mov%s %s%u, [r%u++]",
                           op & 1 ? "b" : "", op & 1 ? "rb" : "r",
                           arg >> 4, arg & 15);
        break;
    case 0x3a: case 0x3b:
        info->fprintf_func(info->stream, "mov%s [r%u], [r%u++]",
                           op & 1 ? "b" : "", arg >> 4, arg & 15);
        break;
    case 0x48: case 0x49:
        info->fprintf_func(info->stream, "mov%s r%u, #0x%x",
                           op & 1 ? "b" : "", arg >> 4, arg & 15);
        break;
    case 0x58: case 0x59:
        info->fprintf_func(info->stream, "mov%s [--r%u], %s%u",
                           op & 1 ? "b" : "", arg >> 4,
                           op & 1 ? "rb" : "r", arg & 15);
        break;
    case 0x68: case 0x69:
        info->fprintf_func(info->stream, "mov%s reg[0x%02x], #0x%04x",
                           op & 1 ? "b" : "", arg, ext);
        break;
    case 0x6a: case 0x6b:
        info->fprintf_func(info->stream, "mov%s [r%u+0x%04x], %s%u",
                           op & 1 ? "b" : "", arg & 15, ext,
                           op & 1 ? "rb" : "r", arg >> 4);
        break;
    case 0x78: case 0x79:
        info->fprintf_func(info->stream, "mov%s %s%u, [r%u+0x%04x]",
                           op & 1 ? "b" : "", op & 1 ? "rb" : "r",
                           arg >> 4, arg & 15, ext);
        break;
    case 0x88: case 0x89:
        info->fprintf_func(info->stream, "mov%s reg[0x%02x], [0x%04x]",
                           op & 1 ? "b" : "", arg, ext);
        break;
    case 0xa8: case 0xa9:
        info->fprintf_func(info->stream, "mov%s [0x%04x], reg[0x%02x]",
                           op & 1 ? "b" : "", ext, arg);
        break;
    case 0x4b:
        info->fprintf_func(info->stream, "asr r%u, #0x%x",
                           arg >> 4, arg & 15);
        break;
    case 0x4c: case 0x5c:
        info->fprintf_func(info->stream, "%s r%u, #0x%x",
                           op == 0x4c ? "sl" : "slosb",
                           arg >> 4, arg & 15);
        break;
    case 0x4d: case 0x5d:
        info->fprintf_func(info->stream, "%s r%u, #0x%x",
                           op == 0x4d ? "sr" : "srosb",
                           arg >> 4, arg & 15);
        break;
    case 0xbc: case 0xac:
        info->fprintf_func(info->stream, "%s.%s %02x:%04x",
                           op == 0xbc ? "acall" : "ajmp",
                           arg < 15 ? condition_name[arg] : "never",
                           dmcu_code_segment(addr), ext);
        break;
    case 0xbd: case 0xad:
        info->fprintf_func(info->stream, "%s %02x:%04x",
                           op == 0xbd ? "scall" : "sjmp", arg, ext);
        break;
    case 0xcd:
        info->fprintf_func(info->stream, "rcall %02x:%04x",
                           dmcu_code_segment(addr),
                           (dmcu_code_pc(addr) + 2 +
                            (int8_t)arg * 2) & 0xffff);
        break;
    case 0xc6:
        info->fprintf_func(info->stream, "%s",
                           arg == 0 ? "ret" : arg == 0x10 ? "reti" :
                           arg == 0x20 ? "rets" : "ret.reserved");
        break;
    case 0xc0: case 0xc1:
        info->fprintf_func(info->stream, "%s r%u, r%u",
                           op == 0xc0 ? "mul" : "umul", arg >> 4, arg & 15);
        break;
    case 0x1f:
        info->fprintf_func(info->stream, "%s reg[0x%02x]",
                           arg & 0x80 ? "pop" : "push", arg & 0x7f);
        break;
    case 0x2e:
        info->fprintf_func(info->stream, "link #0x%02x", arg);
        break;
    case 0x2f:
        info->fprintf_func(info->stream, arg == 0 ? "unlink" : ".word 0x%04x",
                           word);
        break;
    case 0xbf:
        info->fprintf_func(info->stream, "rep #0x%04x", ext);
        break;
    case 0xc7:
        info->fprintf_func(info->stream, arg == 0 ? "nop" : ".word 0x%04x",
                           word);
        break;
    case 0x3f:
        if (arg == 0xff) {
            info->fprintf_func(info->stream, "reset");
        } else if (arg <= 3 || (arg >= 0x10 && arg <= 0x13)) {
            info->fprintf_func(info->stream, "%s #%u",
                               arg & 0x10 ? "ignds" : "crit", arg & 3);
        } else {
            info->fprintf_func(info->stream, ".word 0x%04x", word);
        }
        break;
    default:
        if (op >= 0xd0 && op <= 0xde) {
            info->fprintf_func(info->stream, "rjmp.%s %02x:%04x",
                               condition_name[op & 15],
                               dmcu_code_segment(addr),
                               (dmcu_code_pc(addr) + 2 +
                                (int8_t)arg * 2) & 0xffff);
        } else if (op >= 0xe0) {
            info->fprintf_func(info->stream, "%s bit[0x%02x].%u",
                               op < 0xf0 ? "bset" : "bclr", arg, op & 15);
        } else {
            info->fprintf_func(info->stream, ".word 0x%04x", word);
        }
        break;
    }
    return size;
}
