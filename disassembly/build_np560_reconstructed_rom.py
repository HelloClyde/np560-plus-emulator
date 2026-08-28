#!/usr/bin/env python3
"""Build the clean-room resident ROM used by the NP560+ QEMU machine.

The original SoC mask ROM is absent from the update package.  This image
therefore contains only routines whose observable ABI has been recovered
from the unmodified vendor burner.  The routines execute as ordinary DMCU
guest instructions and access QEMU's reconstructed NAND controller through
MMIO; QEMU does not intercept SCALL.

Unreconstructed addresses contain reserved word 0x0F00 so strict skeleton
mode stops on the next unknown ROM dependency and records its caller state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROGRAM = ROOT / "NP560+V3.80版系统升级程序" / "NP560.PRG"
PROGRAM_SOURCE = DEFAULT_PROGRAM
PROVISION_TRIGGER_TARGET = 0

RESERVED = 0x0F00
RETS = 0xC620
# IGNDS is a counted prefix, not a latch.  Argument zero makes exactly the
# following instruction use the unbanked 64 KiB internal-data window.
IGNDS_ONE = 0x3F10

NAND_BASE = 0xF300
NAND_COMMAND = NAND_BASE + 0x00
NAND_STATUS = NAND_BASE + 0x02
NAND_PAGE_HI = NAND_BASE + 0x04
NAND_PAGE_LO = NAND_BASE + 0x06
NAND_COLUMN = NAND_BASE + 0x08
NAND_BUFFER_HI = NAND_BASE + 0x0A
NAND_BUFFER_LO = NAND_BASE + 0x0C
NAND_LENGTH = NAND_BASE + 0x0E
NAND_FLAGS = NAND_BASE + 0x10
NAND_DS0 = NAND_BASE + 0x12
NAND_DS1 = NAND_BASE + 0x14
NAND_ID = NAND_BASE + 0x16
NAND_ID_EXT = NAND_BASE + 0x20
NAND_ERROR = NAND_BASE + 0x1E
# The NP560+ large-page NAND exposes a 2048+64-byte raw page.  The compact
# 512+16 codec remains below because the updater supports older EC:76 parts
# too; it is selected only when a caller actually supplies a 0x210 length.
NAND_PAGE_TOTAL = 2048 + 64
NAND_SMALL_PAGE_TOTAL = 512 + 16
# Internal clean-room helper, not a vendor ABI entry.  Keep it after the
# optional 06:0000..1C5D data-template probe so the growing application
# overlay loader can use the contiguous segment-03 scratch-ROM area below the
# exact vendor jump-table module at 03:4000.
# The recovered menu installer now extends through its RETS at 06:22A6 after
# restoring the exact 2F:8E8E/2F:8FC6/30:07BE/2F:B8A4/29:6454,
# 23:DA24, and 2F:FA32 event-path overlays.  Keep this small
# helper in the otherwise unused gap before 06:2400.
NAND_PREPARE_READ_ADDRESS = 0x062300
# Clean-room NAND helpers are kept together outside the growing segment-03
# recovered ROM loader. These addresses are not vendor entry points.
NAND_PACK_SPARE_ADDRESS = 0x062400
NAND_UNPACK_SPARE_ADDRESS = 0x062600
NAND_UNPACK_FULL_ADDRESS = 0x062800
# The segment-03 bootstrap body now ends immediately below the exact vendor
# jump table at 03:4000.  Keep late, small overlay installers in the same
# clean-room segment-06 area as the NAND helpers so adding one recovered
# dependency cannot displace that fixed ROM module.
APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS = 0x1A0000
# Two source-50 file-driver bodies must be embedded, but their 104-word write
# program no longer fits below the exact 1A:423C dispatcher.  Keep that small
# guest installer in the reserved gap after resident wide arithmetic ends at
# 1A:E7BE and call it at the final ROM-01 application boundary, after every
# broad application overlay has been restored.
APPLICATION_FILE_DRIVER_CALLBACK_INSTALLER_ADDRESS = 0x1AE800
# The region-extra installer ends just below the exact resident 1A:423C
# dispatcher.  Keep the small collision-safe wide-accumulate closure after
# the state-50 cleanup installer, which ends at 0C:517E, and invoke it from
# that main installer.
WIDE_ACCUMULATE_INSTALLER_ADDRESS = 0x0C5200
# Segment 50 has become mutable by the time the late application installer
# runs.  Keep the source-50 foreground state wrappers as literals in the free
# resident gap after the exact 1A:4B9C configuration body (ending at 54F6)
# and before the separate 1A:6000 installer.
APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS = 0x1A5500
# The root status stream has a two-function overlay closure.  Keep its copy
# loop in the otherwise unused 1A:7000 ROM gap so the already dense 1A:5500
# foreground installer remains below the independent 1A:6000 factory loader.
APPLICATION_ROOT_STREAM_INSTALLER_ADDRESS = 0x1A7000
# The factory-default/catalogue closure is too large to inline into the
# segment-09 bootstrap installer without crossing the decoder-installer
# window.  Keep its guest copy/embed program in the free resident gap after
# 1A:4B9C and call it from the ordinary late-overlay path.
APPLICATION_FACTORY_DEFAULT_INSTALLER_ADDRESS = 0x1A6000
# The exact 15:6C56 resource decoder is a large mask-ROM dependency whose
# shipped source-32 copy spans almost 4 KiB.  Its word-by-word guest installer
# is clean-room bootstrap code, not a vendor ABI entry.  Keep it in the free
# 1A:8000..BC7E window, before the known 1A:C352 resident arithmetic entry.
# This leaves the segment-09 post-initializer loader free to grow toward its
# independent 09:B800 text-stream installer without repeated relocation.
APPLICATION_MENU_RESOURCE_DECODER_INSTALLER_ADDRESS = 0x1A8000
# The startup storage resolver temporarily occupies 2D:3460.  The shipped
# application later executes the original segment-2D body through the same
# range, so retire that bootstrap overlay immediately after 18:F97C returns.
# Keep the cleanup thunk and its exact saved payload in otherwise unused
# resident segment-06 space.
STORAGE_DRIVER_RETIRE_ADDRESS = 0x0658E0
STORAGE_DRIVER_RETIRE_PAYLOAD_ADDRESS = 0x065920
KEYBOARD_EVENT = 0xF340

# Exploration-only bytes used to prove the vendor's 24:7FE4 initializer ABI.
# These are recognizable sentinels, explicitly not recovered factory values.
INITIALIZER_PROBE_SOURCES = {
    0x04FFF8: bytes(range(0x10, 0x18)),
    0x0757C8: bytes(range(0x20, 0x24)),
    0x07A622: bytes(range(0x30, 0x40)),
}

# The same three ranges are recoverable for the full overlay/system path.
# Every source has its exact linked storage copy at source segment +0x1D in
# NP560.PRG.  The first and second ranges are bounded data islands immediately
# after balanced RETS epilogues; the third contains the zero data island plus
# two resident RETS leaves at 07:A62C/07:A62E.  Keep the explicit sentinel map
# above for the isolated ABI probe, but never feed those test bytes to the
# system-main image now that the factory storage representation is available.
INITIALIZER_FACTORY_SOURCE_COPIES = (
    (0x04FFF8, 0x21FFF8, 0x0008),
    (0x0757C8, 0x2457C8, 0x0004),
    (0x07A622, 0x24A622, 0x0010),
)


def initializer_probe_storage_bytes(data: bytes) -> bytes:
    """Encode logical probe bytes in the DMCU external 8-bit data lane.

    Translated byte accesses select the opposite byte of each 16-bit external
    word (address bit zero is inverted).  All three synthetic source blocks
    are even-aligned and even-sized, so swapping each adjacent pair makes the
    documented logical sentinel sequence visible to the original MOVB copy
    helper without changing any guest code.
    """
    if len(data) & 1:
        raise ValueError("initializer probe source must contain whole words")
    stored = bytearray(data)
    for offset in range(0, len(stored), 2):
        stored[offset], stored[offset + 1] = stored[offset + 1], stored[offset]
    return bytes(stored)

# Six records that first exposed the missing Harvard data view.  Keep them as
# pinned evidence while the complete record set is decoded from the original
# straight-line initializer below.
STORAGE_GLOBAL_TEMPLATE_EVIDENCE_COPIES = (
    (0x5129CC, 0x5070C8, 0x0004),
    (0x5129B4, 0x507034, 0x0004),
    (0x5129C0, 0x507058, 0x0004),
    (0x5129C4, 0x50705C, 0x0004),
    (0x5129B8, 0x507054, 0x0004),
    (0x5129B0, 0x5070B0, 0x0004),
)
COMPILER_INITIALIZER_ADDRESS = 0x2E4560
COMPILER_INITIALIZER_END = 0x2E5C12
# The updater stores three pieces of the factory cold-start path exactly
# 0x1D segments above their linked resident execution addresses.  Unlike the
# isolated initializer probes, the factory-linked path must execute the
# copies at the addresses named by their own terminal SJMPs:
#
#   33:603C -> 11:4560 -> 07:7FE4 -> 03:026A
#
# QEMU supplies the two exact immutable 50:* -> 33:* reset aliases.  The
# reconstructed resident image below supplies these three sub-20 linked
# bodies.  The 07:* terminal jump is retargeted only in factory-linked mode
# so the still-missing late overlay loader can run before exact system main.
FACTORY_COMPILER_INITIALIZER_DESTINATION = 0x114560
FACTORY_COMPILER_INITIALIZER_SOURCE = COMPILER_INITIALIZER_ADDRESS
FACTORY_COMPILER_INITIALIZER_SIZE = (
    COMPILER_INITIALIZER_END - COMPILER_INITIALIZER_ADDRESS
)
FACTORY_CONSTANT_INITIALIZER_DESTINATION = 0x077FE4
FACTORY_CONSTANT_INITIALIZER_SOURCE = 0x247FE4
FACTORY_CONSTANT_INITIALIZER_END = 0x2480AE
FACTORY_CONSTANT_INITIALIZER_SIZE = (
    FACTORY_CONSTANT_INITIALIZER_END - FACTORY_CONSTANT_INITIALIZER_SOURCE
)
FACTORY_SYSTEM_MAIN_DESTINATION = 0x03026A
FACTORY_SYSTEM_MAIN_SOURCE = 0x20026A
FACTORY_SYSTEM_MAIN_END = 0x200328
FACTORY_SYSTEM_MAIN_SIZE = (
    FACTORY_SYSTEM_MAIN_END - FACTORY_SYSTEM_MAIN_SOURCE
)
SEGMENT33_DATA_TEMPLATE_DELTA = 0x1D0000
# Keep the late template reapply helper in the reconstructed segment-03 boot
# ROM, after its fixed jump table.  Segment 06 is genuine resident ROM and is
# now occupied by the recovered 06:1138 implementation.
STORAGE_GLOBAL_TEMPLATE_PROBE_ADDRESS = 0x038000

# High-confidence overlay source recovered from NP560.PRG.  The naked call at
# 20:02C0 targets 2C:9A7C, where the flat image starts in the middle of an
# incompatible function.  The same PC in the otherwise uncalled segment 49
# contains the sole ABI-compatible complete routine: LINK #0, memory-control
# register setup, and RETS at 49:9C64.  Keep the source/destination explicit so
# the loader still performs a real guest-visible copy rather than asking QEMU
# to redirect the call.
MEMORY_INIT_OVERLAY_DESTINATION = 0x2C9A7C
MEMORY_INIT_OVERLAY_SOURCE = 0x499A7C
MEMORY_INIT_OVERLAY_SIZE = 0x01EA
TEXT_DRAW_OVERLAY_DESTINATION = 0x2E5316
TEXT_DRAW_OVERLAY_SOURCE = 0x4B5316
TEXT_DRAW_OVERLAY_SIZE = 0x0184
# 50:5906 is a complete no-argument bit-control helper, but its logical
# destination 33:5906 is also the middle of the flat segment-33 foreground
# worker.  Keeping the helper there permanently corrupts the worker's
# fall-through path after several application lifecycles.  The original ROM
# loader's overlay lifetime policy is still unknown, so retain the exact
# helper words in an unused resident-ROM slot and statically relocate the two
# recovered installed callers.  33:5906 itself must keep its flat PRG bytes.
SYSTEM_BITS_OVERLAY_COLLISION_ADDRESS = 0x335906
SYSTEM_BITS_OVERLAY_DESTINATION = SYSTEM_BITS_OVERLAY_COLLISION_ADDRESS
SYSTEM_BITS_OVERLAY_SOURCE = 0x505906
SYSTEM_BITS_OVERLAY_SIZE = 0x0010
SYSTEM_BITS_RESIDENT_ADDRESS = 0x061CE0
SYSTEM_BITS_OVERLAY_WORDS = (
    0x2E00, 0xFA39, 0xFA41, 0xEA49,
    0xEA31, 0x4800, 0x2F00, 0xC620,
)
SYSTEM_INIT_OVERLAY_DESTINATION = 0x336030
SYSTEM_INIT_OVERLAY_SOURCE = 0x506030
SYSTEM_INIT_OVERLAY_SIZE = 0x000C
SYSTEM_INIT_OVERLAY_WORDS = (
    0x2E00, 0xBD33, 0x5906, 0x4800, 0x2F00, 0xC620,
)
SYSTEM_INIT_RELOCATED_OVERLAY_WORDS = (
    0x2E00, 0xBD06, 0x1CE0, 0x4800, 0x2F00, 0xC620,
)
APPLICATION_STATE_BYTE_OVERLAY_DESTINATION = 0x335B70
APPLICATION_STATE_BYTE_OVERLAY_SOURCE = 0x505B70
APPLICATION_STATE_BYTE_OVERLAY_SIZE = 0x000E
APPLICATION_STATE_BYTE_OVERLAY_WORDS = (
    0x2E00, 0x6810, 0x00A0, 0x99F0, 0x7E58, 0x2F00, 0xC620,
)
MODE_INIT_OVERLAY_DESTINATION = 0x33305E
MODE_INIT_OVERLAY_SOURCE = 0x50305E
MODE_INIT_OVERLAY_SIZE = 0x0024
MODE_INIT_OVERLAY_WORDS = (
    0x2E00, 0x58F0, 0x780B, 0x0006, 0x6B1B, 0x0006,
    0x791B, 0x0006, 0x6810, 0x00A2, 0xC700, 0xA9F1,
    0x2A36, 0xBD33, 0x180A, 0x380F, 0x2F00, 0xC620,
)
MODE_MASK_OVERLAY_DESTINATION = 0x33180A
MODE_MASK_OVERLAY_SOURCE = 0x50180A
MODE_MASK_OVERLAY_SIZE = 0x002E
MODE_MASK_OVERLAY_WORDS = (
    0x2E00, 0x58F0, 0x58F1, 0x68F1, 0x0010, 0x6810,
    0x00A2, 0x99F0, 0x2A36, 0x1210, 0x68F0, 0xFFFF,
    0x0C03, 0x4A03, 0x6810, 0x00A2, 0xC700, 0xA8F0,
    0x2A34, 0x381F, 0x380F, 0x2F00, 0xC620,
)
MEMORY_RESET_OVERLAY_DESTINATION = 0x31AF72
MEMORY_RESET_OVERLAY_SOURCE = 0x4EAF72
MEMORY_RESET_OVERLAY_SIZE = 0x00A2
MEMORY_MODE_OVERLAY_DESTINATION = 0x31B014
MEMORY_MODE_OVERLAY_SOURCE = 0x4EB014
MEMORY_MODE_OVERLAY_SIZE = 0x00A2
GLOBAL_RESET_OVERLAY_DESTINATION = 0x3338D6
GLOBAL_RESET_OVERLAY_SOURCE = 0x5038D6
GLOBAL_RESET_OVERLAY_SIZE = 0x0022
GLOBAL_RESET_OVERLAY_WORDS = (
    0x2E00, 0x58F0, 0x4800, 0x6810, 0x00A2, 0xC700,
    0xA8F0, 0x2A84, 0x4800, 0x6810, 0x00A2, 0xC700,
    0xA8F0, 0x2A80, 0x380F, 0x2F00, 0xC620,
)
STARTUP_TABLE_OVERLAY_DESTINATION = 0x324218
STARTUP_TABLE_OVERLAY_SOURCE = 0x4F4218
STARTUP_TABLE_OVERLAY_SIZE = 0x0078
STARTUP_POINTER_OVERLAY_DESTINATION = 0x32CC9C
STARTUP_POINTER_OVERLAY_SOURCE = 0x4FCC9C
STARTUP_POINTER_OVERLAY_SIZE = 0x004C
STARTUP_ARRAY_OVERLAY_DESTINATION = 0x328EBE
STARTUP_ARRAY_OVERLAY_SOURCE = 0x4F8EBE
STARTUP_ARRAY_OVERLAY_SIZE = 0x0062
STARTUP_RUNTIME_OVERLAY_DESTINATION = 0x314BAC
STARTUP_RUNTIME_OVERLAY_SOURCE = 0x4E4BAC
STARTUP_RUNTIME_OVERLAY_SIZE = 0x00BC
SYSTEM_MODE_OVERLAY_DESTINATION = 0x335CB2
SYSTEM_MODE_OVERLAY_SOURCE = 0x505CB2
SYSTEM_MODE_OVERLAY_SIZE = 0x000E
SYSTEM_MODE_OVERLAY_WORDS = (
    0x2E00, 0x6810, 0x00A1, 0x99F0, 0x386C, 0x2F00, 0xC620,
)
STARTUP_TABLE_SERVICE_OVERLAY_DESTINATION = 0x333C86
STARTUP_TABLE_SERVICE_OVERLAY_SOURCE = 0x503C86
STARTUP_TABLE_SERVICE_OVERLAY_SIZE = 0x0020
STARTUP_TABLE_SERVICE_OVERLAY_WORDS = (
    0x2E00, 0x58F0, 0x58F1, 0x68F1, 0x2734, 0x68F0,
    0x0051, 0x58F1, 0x58F0, 0xBD14, 0x6E10, 0x50F4,
    0x381F, 0x380F, 0x2F00, 0xC620,
)
# These two adjacent source-50 wrappers are both bounded recovered functions,
# but adjacency is not evidence that the missing resident manager calls them
# as one sequence.  Linked 33:3CA6 calls 1B:23B8 with operation 0x0B; linked
# 33:3CC6 independently passes 31:F5E2 to 2E:D34A.  No literal PRG caller for
# either wrapper survives.  Keep their shared source window available for
# isolated probes, without treating their address order as factory policy.
RESIDENT_FIXED_LAUNCH_WRAPPER_DESTINATION = 0x333CA6
RESIDENT_FIXED_LAUNCH_WRAPPER_SOURCE = 0x503CA6
RESIDENT_FIXED_LAUNCH_WRAPPER_SIZE = 0x0040
# Exact resource pointer supplied by linked 33:3CC6 to 2E:D34A.  The data
# island begins with the word-swapped development path
# ``c:\\np580fat\\多媒体\\lirt.nwf``; it is not the root-menu descriptor.
APPLICATION_LAUNCH_RESOURCE_DATA_ADDRESS = 0x31F5E2
RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS = 0x061B00
MENU_RESULT_TABLE_INSTALLER_ADDRESS = 0x061750
MENU_EVENT_DEPENDENCY_INSTALLER_ADDRESS = 0x061C40
MENU_EVENT_STATE_INSTALLER_ADDRESS = 0x065B00
# Segment 50 is mutable by the time the resident manager reloads the menu.
# Preserve the two exact adjacent remainder wrappers in a post-load embedded
# installer placed in the free 06:5D00 gap after the menu-state installer.
MENU_ARITHMETIC_WRAPPER_INSTALLER_ADDRESS = 0x065D00
# Compact late copy in the free gap after the arithmetic installer.  Keeping
# it separate prevents 06:1750 from growing across the fixed 06:1B00 wrapper.
MENU_SERVICE_INIT_INSTALLER_ADDRESS = 0x066300
# The complete 24:2C32 parser needs a larger embedded-write routine than the
# 06:5D00 gap permits.  Keep it in the otherwise unused 06:7000 window and
# have the compact arithmetic installer call it after every menu load.
MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS = 0x067000
STARTUP_REGION_SERVICE_OVERLAY_DESTINATION = 0x332FF2
STARTUP_REGION_SERVICE_OVERLAY_SOURCE = 0x502FF2
STARTUP_REGION_SERVICE_OVERLAY_SIZE = 0x0024
STARTUP_REGION_SERVICE_OVERLAY_WORDS = (
    0x2E00, 0x58F0, 0x58F1, 0x68F1, 0x3840, 0x68F0,
    0x0050, 0x58F1, 0x58F0, 0x4800, 0x58F0, 0xBD14,
    0x6AEC, 0x50F6, 0x381F, 0x380F, 0x2F00, 0xC620,
)
# NP560.PRG carries a complete resident module at 25:2EDC..25:4B8E that is
# linked for execution at the same PCs in segment 08.  Its own 27 far calls
# all select segment 08 (and none select segment 25), while every observed
# 08:* API target has a same-PC entry in this source window.  Embed the exact
# guest words; this replaces the earlier ABI-only 08:43A6 implementation and
# the exploratory 08:427E return stub.
ROM08_MODULE_ADDRESS = 0x082EDC
ROM08_MODULE_SOURCE = 0x252EDC
ROM08_MODULE_SIZE = 0x1CB2
FAR_MEMCPY_08_ADDRESS = 0x0843A6
# The updater contains one no-argument call to 01:0200 immediately after the
# exact 08:4470 clock/PLL configuration and never consumes a return value.
# No shipped image contains the mask-ROM bytes.  Keep the minimal returning
# guest instruction behind an explicit exploration switch; this is not an
# exact recovery and is never intercepted as a host ROM service.
ROM01_POST_CLOCK_ADDRESS = 0x010200
# All known calls to 02:C588 pass one immediate marker byte (0x23, 0x24,
# 0x30, or 0x65), discard the argument themselves, and consume no return
# value.  The 0x23/0x24 pair brackets two three-byte emissions through the
# nearby 02:C5DC entry, while 0x30/0x65 occurs only on the chip-id 0xEC NAND
# self-test branch.  This constrains C588 to a diagnostic/marker output whose
# only CPU-visible contract is a normal return.  The external diagnostic
# channel is deliberately not fabricated without an evidenced SFR or pin.
# Install the minimal guest return in every image; these are reconstructed
# DMCU ROM words, not a host-side service and not claimed original bytes.
ROM02_C588_ADDRESS = 0x02C588
# The application has two independently reachable paths through the absent
# segment-06 mask ROM.  Every 06:6A02 caller supplies no arguments and ignores
# R0.  An earlier reconstruction treated it as a release barrier over exact
# scanner 2E:5F28.  Native state transition 22:5288 disproved that inference:
# the 64-Hz IRQ can re-enter the same global-scratch scanner and the invented
# loop then deadlocks with a physically released F160=10FF matrix.  Retain only
# the caller-proven normal-return ABI until a ROM side effect is evidenced.
# Every 06:B126 caller consumes R0 as a returned key code; keep that separate
# scanner plus exact 28:F4A4 mapper reconstruction.  Both routines remain
# guest DMCU words; QEMU does not intercept either entry as a host service.
ROM06_KEY_RELEASE_ADDRESS = 0x066A02
ROM06_KEY_READ_ADDRESS = 0x06B126
# The application-state/power routine at 2D:2D40 copies 0x2c bytes from
# PRG 2F:550C to internal data address 00:1002, then tail-jumps to 00:1002.
# Those 22 words are therefore a writable code-RAM prefix, not the unrelated
# USB loader routine at the same address.  The PRG continues with a complete
# module linked for 00:1002: it falls through at 00:102E and branches to
# 00:56FA.  Most paths use the copied UNLINK/RETS epilogue at 00:5FA6, but
# the final wide-arithmetic path contains an absolute AJMP 00:A4B0.  The
# source's 2F:A4B0 tail is the exact matching pop/UNLINK/RETS sequence, proving
# that the resident mask ROM also exposes that split epilogue at its linked
# low PC.  Embed both exact regions; the QEMU machine overlays the first 0x2c
# bytes with the guest-written internal code RAM, as the hardware does.
ROM00_DYNAMIC_MODULE_ADDRESS = 0x001002
ROM00_DYNAMIC_MODULE_SOURCE = 0x2F550C
ROM00_DYNAMIC_MODULE_SIZE = 0x4FB0
ROM00_DYNAMIC_PREFIX_SIZE = 0x002C
ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_ADDRESS = 0x00A4B0
ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_SOURCE = 0x2FA4B0
ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_SIZE = 0x000C
# The exact dynamic module's zero-byte callback at 00:3F00 enters a critical
# section, performs the byte store, and tail-jumps to 00:85B0.  Every shipped
# critical-section function uses the paired 3F00 / RETS epilogue; 3F00 is
# CRIT #0 (the inverse of the callback's 3F01 CRIT #1), and the synthetic
# far-call at 11/2E:1886 requires a far return to its 11/2E:1888 continuation.
# The mask-ROM bytes themselves are absent, but both instructions are fixed
# by the entry/exit state and by the compiler's repeated epilogue pattern.
ROM00_CRITICAL_RETURN_ADDRESS = 0x0085B0
ROM00_CRITICAL_RETURN_WORDS = (0x3F00, RETS)
# NP560.PRG begins with 484 contiguous four-byte AJMP trampolines at
# 20:4000..20:4790. Their PCs are the resident 03:4000 service PCs used by
# the application (for example 03:4214 -> 30:1A54). Embed the exact table.
ROM03_JUMP_TABLE_ADDRESS = 0x034000
ROM03_JUMP_TABLE_SOURCE = 0x204000
ROM03_JUMP_TABLE_SIZE = 0x0790
# ROM service 03:4068 is the five-word far-copy ABI.  Its exact jump-table
# entry lands at 33:46A2, but that flat PRG address is the middle of an
# unrelated function.  The relocation image keeps the real same-PC entry at
# 50:46A2: a two-word tail trampoline to the reconstructed resident memcpy at
# 18:6D56.  Segment 50 is mutable by late-loader time, so embed both words.
ROM03_FAR_MEMCPY_THUNK_DESTINATION = 0x3346A2
ROM03_FAR_MEMCPY_THUNK_SOURCE = 0x5046A2
ROM03_FAR_MEMCPY_THUNK_SIZE = 0x0004
APPLICATION_LCD_INIT_OVERLAY_DESTINATION = 0x31A914
APPLICATION_LCD_INIT_OVERLAY_SOURCE = 0x4EA914
APPLICATION_LCD_INIT_OVERLAY_SIZE = 0x00A4
PERIPHERAL_INIT_OVERLAY_DESTINATION = 0x249BD4
PERIPHERAL_INIT_OVERLAY_SOURCE = 0x419BD4
PERIPHERAL_INIT_OVERLAY_SIZE = 0x0014
ACTIVATION_CONTEXT_OVERLAY_DESTINATION = 0x309E30
ACTIVATION_CONTEXT_OVERLAY_SOURCE = 0x4D9E30
ACTIVATION_CONTEXT_OVERLAY_SIZE = 0x00F0
# 33:4510 passes context+0x1CC4 to 31:5300 as a 16-bit lookup key.  The
# flat target is the middle of an unrelated wide-value routine; 4E:5300 is
# the complete same-PC LINK #4 table lookup over the 51:4A40 registry.
APPLICATION_CONTEXT_LOOKUP_OVERLAY_DESTINATION = 0x315300
APPLICATION_CONTEXT_LOOKUP_OVERLAY_SOURCE = 0x4E5300
APPLICATION_CONTEXT_LOOKUP_OVERLAY_SIZE = 0x00BA
# The next 33:4510 field lookup calls 32:2396.  Flat 32:2396 is UTF-16 data,
# while 4F:2396 is the complete LINK #0 selector-to-pointer mapper.
APPLICATION_CONTEXT_PROPERTY_OVERLAY_DESTINATION = 0x322396
APPLICATION_CONTEXT_PROPERTY_OVERLAY_SOURCE = 0x4F2396
APPLICATION_CONTEXT_PROPERTY_OVERLAY_SIZE = 0x0084
# All callers pass one event/character word to 33:1A02.  Flat 33:1A02 is a
# large-function suffix; 50:1A02 is the exact framed ASCII letter predicate.
APPLICATION_EVENT_CLASSIFY_OVERLAY_DESTINATION = 0x331A02
APPLICATION_EVENT_CLASSIFY_OVERLAY_SOURCE = 0x501A02
APPLICATION_EVENT_CLASSIFY_OVERLAY_SIZE = 0x002C
POINTER_SERVICE_OVERLAY_DESTINATION = 0x32D530
POINTER_SERVICE_OVERLAY_SOURCE = 0x4FD530
POINTER_SERVICE_OVERLAY_SIZE = 0x0048
POINTER_STATE_OVERLAY_DESTINATION = 0x335FD0
POINTER_STATE_OVERLAY_SOURCE = 0x505FD0
POINTER_STATE_OVERLAY_SIZE = 0x000C
POINTER_FLAG_OVERLAY_DESTINATION = 0x335C18
POINTER_FLAG_OVERLAY_SOURCE = 0x505C18
POINTER_FLAG_OVERLAY_SIZE = 0x000E
POINTER_NORMALIZE_OVERLAY_DESTINATION = 0x334492
POINTER_NORMALIZE_OVERLAY_SOURCE = 0x504492
POINTER_NORMALIZE_OVERLAY_SIZE = 0x001C
POINTER_RESOLVE_OVERLAY_DESTINATION = 0x31F282
POINTER_RESOLVE_OVERLAY_SOURCE = 0x4EF282
POINTER_RESOLVE_OVERLAY_SIZE = 0x0090
# The flat 21:FD80 body is an unrelated call chain. 3E:FD80 is the complete
# LINK #0E drawing-context constructor and returns exactly at 21:FFFE.
APPLICATION_DRAW_CONTEXT_OVERLAY_DESTINATION = 0x21FD80
APPLICATION_DRAW_CONTEXT_OVERLAY_SOURCE = 0x3EFD80
APPLICATION_DRAW_CONTEXT_OVERLAY_SIZE = 0x0280
# 21:FD80 calls 32:A922 as a far-comparison wrapper.  The flat target is a
# shared tail; 4F:A922 supplies the complete LINK #0 implementation.
APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_DESTINATION = 0x32A922
APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_SOURCE = 0x4FA922
APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_SIZE = 0x0058
ACTIVATION_DISPATCH_OVERLAY_DESTINATION = 0x27507C
ACTIVATION_DISPATCH_OVERLAY_SOURCE = 0x44507C
ACTIVATION_DISPATCH_OVERLAY_SIZE = 0x0350
APPLICATION_PROPERTY_OVERLAY_DESTINATION = 0x31C0E8
APPLICATION_PROPERTY_OVERLAY_SOURCE = 0x4EC0E8
APPLICATION_PROPERTY_OVERLAY_SIZE = 0x009E
PROPERTY_SETTER_OVERLAY_DESTINATION = 0x314D24
PROPERTY_SETTER_OVERLAY_SOURCE = 0x4E4D24
PROPERTY_SETTER_OVERLAY_SIZE = 0x00BC
LCD_RESOURCE_OVERLAY_DESTINATION = 0x25206E
LCD_RESOURCE_OVERLAY_SOURCE = 0x42206E
LCD_RESOURCE_OVERLAY_SIZE = 0x040A
# The resource routine calls 28:12A8 with five words.  The corresponding
# source is a two-word far-jump thunk to 29:AC4E; that destination also needs
# its complete +0x1D-segment implementation rather than the flat mid-body.
LCD_RESOURCE_DISPATCH_THUNK_DESTINATION = 0x2812A8
LCD_RESOURCE_DISPATCH_THUNK_SOURCE = 0x4512A8
LCD_RESOURCE_DISPATCH_THUNK_SIZE = 0x0004
LCD_RESOURCE_TRANSFER_OVERLAY_DESTINATION = 0x29AC4E
LCD_RESOURCE_TRANSFER_OVERLAY_SOURCE = 0x46AC4E
LCD_RESOURCE_TRANSFER_OVERLAY_SIZE = 0x029C
# The transfer worker resolves each 0x200-byte logical resource page through
# linked 2D:261C.  Flat 2D:261C is the middle of an unrelated function (it has
# no LINK and consumes frame-relative locals), while 4A:261C..4A:27E5 is the
# complete same-PC page reader with a balanced LINK #5 / RETS body.  Its only
# storage child is linked 2C:2EBA, already restored below as
# STORAGE_PRIMARY_SECTOR_READ_OVERLAY from the exact 49:2EBA copy.  Restore
# this missing parent verbatim so 10:Dxxx resource addresses are read through
# the shipped NAND path rather than fabricated as flat ROM bytes or host-side
# service returns.
APPLICATION_RESOURCE_PAGE_READ_OVERLAY_DESTINATION = 0x2D261C
APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SOURCE = 0x4A261C
APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SIZE = 0x01CA
LCD_TIMING_OVERLAY_DESTINATION = 0x30D350
LCD_TIMING_OVERLAY_SOURCE = 0x4DD350
LCD_TIMING_OVERLAY_SIZE = 0x00E0
APPLICATION_STATE_OVERLAY_DESTINATION = 0x308C1C
APPLICATION_STATE_OVERLAY_SOURCE = 0x4D8C1C
APPLICATION_STATE_OVERLAY_SIZE = 0x00F6
MEMORY_FILL_OVERLAY_DESTINATION = 0x30FE0E
MEMORY_FILL_OVERLAY_SOURCE = 0x4DFE0E
# Include the local ACALL helper at same-segment FE:B0..FE:E0.
MEMORY_FILL_OVERLAY_SIZE = 0x00D2
APPLICATION_RANGE_OVERLAY_DESTINATION = 0x329B56
APPLICATION_RANGE_OVERLAY_SOURCE = 0x4F9B56
APPLICATION_RANGE_OVERLAY_SIZE = 0x005C
APPLICATION_TABLE_INIT_OVERLAY_DESTINATION = 0x315EA0
APPLICATION_TABLE_INIT_OVERLAY_SOURCE = 0x4E5EA0
APPLICATION_TABLE_INIT_OVERLAY_SIZE = 0x00B8
APPLICATION_TABLE_CLEAR_OVERLAY_DESTINATION = 0x326358
APPLICATION_TABLE_CLEAR_OVERLAY_SOURCE = 0x4F6358
APPLICATION_TABLE_CLEAR_OVERLAY_SIZE = 0x006C
APPLICATION_BUFFER_COPY_OVERLAY_DESTINATION = 0x322520
APPLICATION_BUFFER_COPY_OVERLAY_SOURCE = 0x4F2520
APPLICATION_BUFFER_COPY_OVERLAY_SIZE = 0x0082
APPLICATION_COMMAND_OVERLAY_DESTINATION = 0x2F5B98
APPLICATION_COMMAND_OVERLAY_SOURCE = 0x4C5B98
APPLICATION_COMMAND_OVERLAY_SIZE = 0x0144
COMMAND_TABLE_PRIMARY_OVERLAY_DESTINATION = 0x315BB8
COMMAND_TABLE_PRIMARY_OVERLAY_SOURCE = 0x4E5BB8
COMMAND_TABLE_PRIMARY_OVERLAY_SIZE = 0x00BA
COMMAND_TABLE_SECONDARY_OVERLAY_DESTINATION = 0x315A44
COMMAND_TABLE_SECONDARY_OVERLAY_SOURCE = 0x4E5A44
COMMAND_TABLE_SECONDARY_OVERLAY_SIZE = 0x00BA
COMMAND_TABLE_TERTIARY_OVERLAY_DESTINATION = 0x31598A
COMMAND_TABLE_TERTIARY_OVERLAY_SOURCE = 0x4E598A
COMMAND_TABLE_TERTIARY_OVERLAY_SIZE = 0x00BA
# The root controller's final static-display step calls 31:58D0 with one
# word.  Flat 31:58D0 begins in the middle of an unrelated function and its
# 27:507C child consequently unwinds straight to the controller's caller,
# skipping the item loop at 1D:F63C.  The exact same-PC body is immediately
# before the already recovered tertiary table builder at 4E:58D0..4E:598A:
# it has the matching LINK #0x37 frame and balanced UNLINK/RETS epilogue.
APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_DESTINATION = 0x3158D0
APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_SOURCE = 0x4E58D0
APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_SIZE = 0x00BA
# The root status painter's exact printf core emits literal and converted
# fragments through 31:552E.  Flat 31:552E is only the RETS epilogue of an
# unrelated source-31 function, so every write is silently discarded.  The
# linked root module contains the complete same-PC stream writer at
# 4E:552E..4E:55E8, including its 22:BE8A child call and balanced epilogue.
APPLICATION_ROOT_STREAM_WRITE_OVERLAY_DESTINATION = 0x31552E
APPLICATION_ROOT_STREAM_WRITE_OVERLAY_SOURCE = 0x4E552E
APPLICATION_ROOT_STREAM_WRITE_OVERLAY_SIZE = 0x00BA
# 31:552E delegates actual stream output to 22:BE8A.  Flat 22:BE8A is the
# middle of an unrelated source-22 function; source 3F:BE8A begins with
# LINK #0x0A and ends at the balanced RETS immediately before 3F:C370.
APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_DESTINATION = 0x22BE8A
APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_SOURCE = 0x3FBE8A
APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_SIZE = 0x04E6
# The complete dispatcher reaches 30:6490 from 22:C062 to move the emitted
# fragment into the destination stream.  That destination is zero in the
# reconstructed resident space, while source 4D:6490..4D:6592 is the exact
# same-PC LINK #0 implementation with a balanced epilogue.  Source bank 4D
# is mutable by the time the root menu runs, so preserve its PRG words in the
# installer instead of trying to copy it live.
APPLICATION_ROOT_STREAM_MOVE_OVERLAY_DESTINATION = 0x306490
APPLICATION_ROOT_STREAM_MOVE_OVERLAY_SOURCE = 0x4D6490
APPLICATION_ROOT_STREAM_MOVE_OVERLAY_SIZE = 0x0102
# The printf core locates the next conversion marker through 31:1122.  Its
# flat destination is the previous source-31 function's POP/UNLINK tail;
# 4E:1122..4E:11F0 is the complete framed scanner used by the root module.
APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_DESTINATION = 0x311122
APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_SOURCE = 0x4E1122
APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_SIZE = 0x00CE
# After the root controller's item loop, 1D:F900 calls 2F:D266 without
# arguments.  Flat 2F:D266 is another unrelated function middle and returns
# through the controller's caller frame.  4C:D266..4C:D38E is the exact
# same-PC LINK #5 mask-table initializer with a balanced epilogue.
APPLICATION_ROOT_ITEM_MASK_OVERLAY_DESTINATION = 0x2FD266
APPLICATION_ROOT_ITEM_MASK_OVERLAY_SOURCE = 0x4CD266
APPLICATION_ROOT_ITEM_MASK_OVERLAY_SIZE = 0x0128
# The root controller begins with a no-argument 32:9A9A hardware-state reset.
# Flat 32:9A9A is the middle of an unrelated table decoder and writes zero to
# the controller's [FP-2] saved object pointer at 32:9B0A.  Source
# 4F:9A9A..4F:9AF8 is the complete same-PC LINK #0 function: it only clears
# the four vendor hardware words at A2:2A64..2A6A, then returns normally.
APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_DESTINATION = 0x329A9A
APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_SOURCE = 0x4F9A9A
APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_SIZE = 0x005E
# The resident 10:E4AA root renderer calls 26:CF40 three times with four
# words while drawing menu resources.  Flat 26:CF40 is compressed/resource
# data and traps the CPU at 26:CF44.  Source 43:CF40..43:D2B2 is the complete
# four-argument LINK #0x50 renderer with a balanced UNLINK/RETS epilogue.
APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_DESTINATION = 0x26CF40
APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_SOURCE = 0x43CF40
APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_SIZE = 0x0372
# All three recovered command-table builders index a 32-entry table of
# ten-byte templates from 2F:6BFA.  The flat destination contains unrelated
# code, while the complete table is stored immediately after a function at
# 4C:6BFA and ends exactly where string data begins at 4C:6D3A.  The resident
# loader must therefore install this data overlay as well as code.
COMMAND_TABLE_TEMPLATE_OVERLAY_DESTINATION = 0x2F6BFA
COMMAND_TABLE_TEMPLATE_OVERLAY_SOURCE = 0x4C6BFA
COMMAND_TABLE_TEMPLATE_OVERLAY_SIZE = 0x0140
COMMAND_MATRIX_OVERLAY_DESTINATION = 0x30D6D0
COMMAND_MATRIX_OVERLAY_SOURCE = 0x4DD6D0
COMMAND_MATRIX_OVERLAY_SIZE = 0x00DE
APPLICATION_MODE_OVERLAY_DESTINATION = 0x32CA88
APPLICATION_MODE_OVERLAY_SOURCE = 0x4FCA88
APPLICATION_MODE_OVERLAY_SIZE = 0x004C
APPLICATION_SLOT_OVERLAY_DESTINATION = 0x329D22
APPLICATION_SLOT_OVERLAY_SOURCE = 0x4F9D22
APPLICATION_SLOT_OVERLAY_SIZE = 0x005C
APPLICATION_TRIPLE_OVERLAY_DESTINATION = 0x322102
APPLICATION_TRIPLE_OVERLAY_SOURCE = 0x4F2102
APPLICATION_TRIPLE_OVERLAY_SIZE = 0x0084
APPLICATION_HW_STATE_OVERLAY_DESTINATION = 0x333376
APPLICATION_HW_STATE_OVERLAY_SOURCE = 0x503376
APPLICATION_HW_STATE_OVERLAY_SIZE = 0x0024
APPLICATION_POWER_STATE_OVERLAY_DESTINATION = 0x33063A
APPLICATION_POWER_STATE_OVERLAY_SOURCE = 0x50063A
APPLICATION_POWER_STATE_OVERLAY_SIZE = 0x0036
APPLICATION_PAGE_SETUP_OVERLAY_DESTINATION = 0x2913DC
APPLICATION_PAGE_SETUP_OVERLAY_SOURCE = 0x4613DC
APPLICATION_PAGE_SETUP_OVERLAY_SIZE = 0x02D4
APPLICATION_TEXT_LOOP_OVERLAY_DESTINATION = 0x281F08
APPLICATION_TEXT_LOOP_OVERLAY_SOURCE = 0x451F08
APPLICATION_TEXT_LOOP_OVERLAY_SIZE = 0x0316
APPLICATION_RESOURCE_LOOP_OVERLAY_DESTINATION = 0x25CC94
APPLICATION_RESOURCE_LOOP_OVERLAY_SOURCE = 0x42CC94
APPLICATION_RESOURCE_LOOP_OVERLAY_SIZE = 0x03C6
APPLICATION_RESOURCE_LOOP_SYSTEM_BITS_CALL_OFFSET = 0x0016
# The full V3.80 NAND checkpoint takes the resource loop's storage-present
# branch and reaches 25:5858.  Flat 25:5858 is compressed/resource data, while
# the otherwise uncalled +0x1D-segment copy at 42:5858 is a complete LINK #6
# storage-registry initializer with a balanced epilogue at 42:5C4C.  Its two
# direct helpers have the same relocation signature and complete boundaries.
# The operation-context wrapper at 32:FA06 first calls 25:5460.  The flat
# destination contains packed resource data (including the undefined B6
# opcode), while the immediately preceding +0x1D-segment bank contains the
# complete LINK #5 storage-context initializer through its balanced return at
# 42:5856.  It ends exactly where the registry initializer below begins.
APPLICATION_STORAGE_CONTEXT_OVERLAY_DESTINATION = 0x255460
APPLICATION_STORAGE_CONTEXT_OVERLAY_SOURCE = 0x425460
APPLICATION_STORAGE_CONTEXT_OVERLAY_SIZE = 0x03F8
APPLICATION_STORAGE_REGISTRY_OVERLAY_DESTINATION = 0x255858
APPLICATION_STORAGE_REGISTRY_OVERLAY_SOURCE = 0x425858
APPLICATION_STORAGE_REGISTRY_OVERLAY_SIZE = 0x03F6
# Resident metadata initialization at 1C:28AC calls linked 24:236A to classify
# the three redundant NAND OOB state copies. Flat 24:236A is data/mid-function
# garbage; source 41:236A is the complete LINK #0x0C implementation through
# its balanced 41:27CC return.
STORAGE_BAD_BLOCK_STATUS_OVERLAY_DESTINATION = 0x24236A
STORAGE_BAD_BLOCK_STATUS_OVERLAY_SOURCE = 0x41236A
STORAGE_BAD_BLOCK_STATUS_OVERLAY_SIZE = 0x0464
APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_DESTINATION = 0x30A3C2
APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_SOURCE = 0x4DA3C2
APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_SIZE = 0x00EC
# The successful storage-unit path at 30:A490 calls resident 18:F97C.  The
# +0x1D segment copy at 35:F97C is a complete LINK #9 implementation ending
# in the balanced 35:FFF8 RETS.  It builds the per-unit runtime record and
# publishes any guest error through A2:2AE0; copy the exact vendor body.
RESIDENT_STORAGE_UNIT_INIT_OVERLAY_DESTINATION = 0x18F97C
RESIDENT_STORAGE_UNIT_INIT_OVERLAY_SOURCE = 0x35F97C
RESIDENT_STORAGE_UNIT_INIT_OVERLAY_SIZE = 0x067E
# 18:F97C calls 2C:FE08 with one unit byte.  Its flat destination starts in
# the middle of a large unrelated function, while 49:FE08 is the exact LINK
# #4 storage worker through the balanced 49:FFDE RETS (with an intentional
# callback-return branch at 49:FFA0).
STORAGE_UNIT_WORKER_OVERLAY_DESTINATION = 0x2CFE08
STORAGE_UNIT_WORKER_OVERLAY_SOURCE = 0x49FE08
STORAGE_UNIT_WORKER_OVERLAY_SIZE = 0x01D8
# That exact worker calls 31:CBE8 to decode two packed 16-bit fields.  Flat
# CBE8 is another suffix; 4E:CBE8 is the complete LINK #4 decoder ending at
# 4E:CC82.
STORAGE_PACKED_FIELD_OVERLAY_DESTINATION = 0x31CBE8
STORAGE_PACKED_FIELD_OVERLAY_SOURCE = 0x4ECBE8
STORAGE_PACKED_FIELD_OVERLAY_SIZE = 0x009C
# The application later resolves record 0's secondary driver at 32:6EA8.
# Flat 32:6EA8 begins in the middle of a large unrelated function; 4F:6EA8 is
# the exact LINK #1 wrapper and returns at 4F:6F10.  Its only worker and that
# worker's block-transfer dependency have the same +0x1D segment relocation
# and complete balanced frames at 4B:C102 and 46:0884 respectively.
STORAGE_SECONDARY_DRIVER_OVERLAY_DESTINATION = 0x326EA8
STORAGE_SECONDARY_DRIVER_OVERLAY_SOURCE = 0x4F6EA8
STORAGE_SECONDARY_DRIVER_OVERLAY_SIZE = 0x006A
# Record 0's primary media-reader callback is the immediately adjacent
# 32:6F12 entry.  It is a separate framed routine, not a continuation of the
# secondary wrapper above: the first overlay deliberately ends exactly at
# 32:6F12.  Flat 32:6F12 is still the middle of unrelated code, while
# 4F:6F12 is the complete LINK #1 one-byte reader through 4F:6F7A.  The
# storage-unit constructor uses it to stream the on-media descriptor into
# 51:1A40 before 18:F97C validates that descriptor.
STORAGE_PRIMARY_READER_OVERLAY_DESTINATION = 0x326F12
STORAGE_PRIMARY_READER_OVERLAY_SOURCE = 0x4F6F12
STORAGE_PRIMARY_READER_OVERLAY_SIZE = 0x006A
STORAGE_TRANSFER_WORKER_OVERLAY_DESTINATION = 0x2EBF9A
STORAGE_TRANSFER_WORKER_OVERLAY_SOURCE = 0x4BBF9A
STORAGE_TRANSFER_WORKER_OVERLAY_SIZE = 0x016A
# The primary record callback at 32:6F12 calls the adjacent 2E:C104 transfer
# entry.  As with 2E:BF9A above, the flat destination is unrelated fallthrough
# code; 4B:C104 is the complete LINK #5 worker ending at 4B:C26C.
STORAGE_PRIMARY_TRANSFER_OVERLAY_DESTINATION = 0x2EC104
STORAGE_PRIMARY_TRANSFER_OVERLAY_SOURCE = 0x4BC104
STORAGE_PRIMARY_TRANSFER_OVERLAY_SIZE = 0x016A
# That worker reads the requested sector range through 2C:2EBA.  Its flat
# destination also starts mid-function, while 49:2EBA is the complete LINK #7
# implementation through 49:30BA.
STORAGE_PRIMARY_SECTOR_READ_OVERLAY_DESTINATION = 0x2C2EBA
STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SOURCE = 0x492EBA
STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SIZE = 0x0202
# The sector reader's NAND status/retry helper has the same relocation
# signature: 47:1440 is a complete LINK #1 routine through 47:16C0, whereas
# flat 2A:1440 is unrelated application code.
STORAGE_NAND_STATUS_OVERLAY_DESTINATION = 0x2A1440
STORAGE_NAND_STATUS_OVERLAY_SOURCE = 0x471440
STORAGE_NAND_STATUS_OVERLAY_SIZE = 0x0282
STORAGE_BLOCK_TRANSFER_OVERLAY_DESTINATION = 0x2905B0
STORAGE_BLOCK_TRANSFER_OVERLAY_SOURCE = 0x4605B0
STORAGE_BLOCK_TRANSFER_OVERLAY_SIZE = 0x02D6
# The worker's shared path invokes 2C:F6A6 with seven words.  Flat F6A6 is
# the middle of another function and eventually executes an unmatched
# UNLINK; 49:F6A6 is the complete LINK #5 implementation with the matching
# ABI and balanced return at 49:F87E.
STORAGE_ASYNC_RANGE_OVERLAY_DESTINATION = 0x2CF6A6
STORAGE_ASYNC_RANGE_OVERLAY_SOURCE = 0x49F6A6
STORAGE_ASYNC_RANGE_OVERLAY_SIZE = 0x01DA
# The next shared path at 2C:F9FA passes four words to 32:EC6E.  The flat
# destination is another large-function suffix and returns through its
# caller's frame; 4F:EC6E is the exact four-word adapter, starting with
# LINK #0 and ending in a balanced RETS at 4F:ECAC.
STORAGE_RANGE_DISPATCH_OVERLAY_DESTINATION = 0x32EC6E
STORAGE_RANGE_DISPATCH_OVERLAY_SOURCE = 0x4FEC6E
STORAGE_RANGE_DISPATCH_OVERLAY_SIZE = 0x0040
# The dispatch continuation reaches 32:0B6A, which passes eight words to
# 2C:38C0. Flat 2C:38C0 is a suffix of an unrelated 0x7f2-byte function and
# consumes the caller's frame at 2C:40B0. Source 49:38C0 is the matching
# framed field parser and returns normally at 49:3ABE.
STORAGE_FIELD_PARSE_OVERLAY_DESTINATION = 0x2C38C0
STORAGE_FIELD_PARSE_OVERLAY_SOURCE = 0x4938C0
STORAGE_FIELD_PARSE_OVERLAY_SIZE = 0x0200
# The exact field parser calls 30:DA48 with one far pointer. Flat DA48 is only
# a stale multi-register epilogue; 4D:DA48 is the complete LINK #4 0x800-byte
# buffer decoder and returns at 4D:DB24.
STORAGE_BUFFER_DECODE_OVERLAY_DESTINATION = 0x30DA48
STORAGE_BUFFER_DECODE_OVERLAY_SOURCE = 0x4DDA48
STORAGE_BUFFER_DECODE_OVERLAY_SIZE = 0x00DE
# After decoding, 2C:FA04 calls 32:0B6A as a no-argument event poll. Flat
# 32:0B6A is a large-function suffix ending in an unmatched frame teardown;
# 4F:0B6A is the exact LINK #1 filter loop through 4F:0BF2.
STORAGE_EVENT_POLL_OVERLAY_DESTINATION = 0x320B6A
STORAGE_EVENT_POLL_OVERLAY_SOURCE = 0x4F0B6A
STORAGE_EVENT_POLL_OVERLAY_SIZE = 0x008A
# The application/storage registry passes seven words to 32:082E from nine
# call sites in 33:68xx..6Dxx.  Flat 32:082E is only a suffix of an unrelated
# large function: it has no LINK prologue and consumes the caller's return
# frame at the unmatched UNLINK/RETS at 32:0FB8.  Source 4F:082E is the exact
# same-PC LINK #0 adapter.  It narrows three arguments to bytes, dispatches to
# 33:00A8 or 33:0070, and returns with a balanced frame at 4F:08B6.
STORAGE_RECORD_DISPATCH_OVERLAY_DESTINATION = 0x32082E
STORAGE_RECORD_DISPATCH_OVERLAY_SOURCE = 0x4F082E
STORAGE_RECORD_DISPATCH_OVERLAY_SIZE = 0x008A
# Seven source-image no-argument call sites target 33:6BF2, whose independent
# entry starts inside the unrelated function beginning at 33:6754.  That same
# address is also a live fall-through from 33:6BB2, so it cannot be overlaid
# in place.  Keep the exact 50:6BF2 LINK #0 constant-one leaf in an unused
# executable bank and retarget only the two currently installed caller bodies.
STORAGE_RECORD_ACCEPT_LINKED_DESTINATION = 0x336BF2
STORAGE_RECORD_ACCEPT_OVERLAY_DESTINATION = 0x5F6BF2
STORAGE_RECORD_ACCEPT_OVERLAY_SOURCE = 0x506BF2
STORAGE_RECORD_ACCEPT_OVERLAY_SIZE = 0x0008
APPLICATION_RESULT_OBJECT_FINALIZE_RECORD_ACCEPT_CALL = 0x32BEDA
APPLICATION_RESULT_OBJECT_FINALIZE_RECORD_ACCEPT_CALL_SOURCE = 0x4FBEDA
APPLICATION_RESULT_OBJECT_CLOSE_RECORD_ACCEPT_CALL = 0x3304C4
APPLICATION_RESULT_OBJECT_CLOSE_RECORD_ACCEPT_CALL_SOURCE = 0x5004C4
# Once the decoded record is accepted, 33:218E passes its object pointer to
# 20:81E0. Flat 20:81E0 is a suffix of the segment-20 bootstrap worker;
# 3D:81E0 is the exact LINK #7 result-record parser through 3D:8768.
APPLICATION_RESULT_RECORD_PARSE_OVERLAY_DESTINATION = 0x2081E0
APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SOURCE = 0x3D81E0
APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SIZE = 0x058A
# 2C:48BC passes two region coordinates plus a mode word to 32:8524.
# Flat 32:8524 is a suffix ending in an unmatched epilogue at 32:8A70;
# 4F:8524 is the exact LINK #1 adapter through its RETS at 4F:8586.
APPLICATION_RESULT_REGION_PREPARE_OVERLAY_DESTINATION = 0x328524
APPLICATION_RESULT_REGION_PREPARE_OVERLAY_SOURCE = 0x4F8524
APPLICATION_RESULT_REGION_PREPARE_OVERLAY_SIZE = 0x0064
# 28:591A passes the selected result pointer to 31:C7A4. Flat 31:C7A4 is
# an unrelated suffix that falls through to an unmatched epilogue at 31:D450;
# 4E:C7A4 is the complete LINK #0x16 result-display setup through 4E:C83E.
APPLICATION_RESULT_DISPLAY_SETUP_OVERLAY_DESTINATION = 0x31C7A4
APPLICATION_RESULT_DISPLAY_SETUP_OVERLAY_SOURCE = 0x4EC7A4
APPLICATION_RESULT_DISPLAY_SETUP_OVERLAY_SIZE = 0x009C
# Result construction calls 32:BB60 as a no-argument release/reset helper.
# Flat 32:BB60 is a large unrelated state-machine suffix; 4F:BB60 is the
# closed LINK #0 helper that releases six resource IDs and returns at 4F:BBB0.
APPLICATION_RESULT_RESOURCE_RESET_OVERLAY_DESTINATION = 0x32BB60
APPLICATION_RESULT_RESOURCE_RESET_OVERLAY_SOURCE = 0x4FBB60
APPLICATION_RESULT_RESOURCE_RESET_OVERLAY_SIZE = 0x0052
# 2C:4A04 passes seven words to 28:5902. Flat 28:5902 starts after the
# function prologue and eventually consumes the caller frame at 28:737C;
# 45:5902 is the complete LINK #8 result-construction worker through 45:5C04.
APPLICATION_RESULT_BUILD_OVERLAY_DESTINATION = 0x285902
APPLICATION_RESULT_BUILD_OVERLAY_SOURCE = 0x455902
APPLICATION_RESULT_BUILD_OVERLAY_SIZE = 0x0304
# Modal cleanup passes its object stream to 2B:758E before the result scanner
# runs.  The flat destination begins in an unrelated large-function suffix and
# immediately consumes the cleanup wrapper's frame.  Source 48:758E is the
# exact LINK #4 byte-stream header parser through its balanced 48:77B4 RETS.
APPLICATION_RESULT_HEADER_PARSE_OVERLAY_DESTINATION = 0x2B758E
APPLICATION_RESULT_HEADER_PARSE_OVERLAY_SOURCE = 0x48758E
APPLICATION_RESULT_HEADER_PARSE_OVERLAY_SIZE = 0x0228
# That parser's first state helper has the same relocation signature.  Flat
# 28:85EE is another frame-dependent suffix; source 45:85EE is the complete
# LINK #8 state/update function through its balanced 45:88E6 RETS.
APPLICATION_RESULT_STATE_OVERLAY_DESTINATION = 0x2885EE
APPLICATION_RESULT_STATE_OVERLAY_SOURCE = 0x4585EE
APPLICATION_RESULT_STATE_OVERLAY_SIZE = 0x02FA
# 20:E9xx supplies two far pointers and a 32-bit bound to 2C:48A8. Flat
# 2C:48A8 is an unrelated result-builder suffix ending at 2C:605A, whereas
# 49:48A8 is the complete normalized far-memory compare through 49:4AA0.
FAR_NORMALIZED_MEMORY_COMPARE_OVERLAY_DESTINATION = 0x2C48A8
FAR_NORMALIZED_MEMORY_COMPARE_OVERLAY_SOURCE = 0x4948A8
FAR_NORMALIZED_MEMORY_COMPARE_OVERLAY_SIZE = 0x01FA
# Four independently located PRG call sites constrain resident 0B:CCD2 to a
# five-word ABI (two far pointers plus one flag) and an RB1 status result.
# No original ROM bytes have been found. Keep the zero-status body strictly
# opt-in so it can expose the next dependency without claiming reconstruction.
RESIDENT_ROM0B_CCD2_ADDRESS = 0x0BCCD2
APPLICATION_STORAGE_ENTRY_ATTACH_OVERLAY_DESTINATION = 0x25E324
APPLICATION_STORAGE_ENTRY_ATTACH_OVERLAY_SOURCE = 0x42E324
APPLICATION_STORAGE_ENTRY_ATTACH_OVERLAY_SIZE = 0x03C0
APPLICATION_DEVICE_QUERY_OVERLAY_DESTINATION = 0x332EAE
APPLICATION_DEVICE_QUERY_OVERLAY_SOURCE = 0x502EAE
APPLICATION_DEVICE_QUERY_OVERLAY_SIZE = 0x0024
APPLICATION_POINTER_UPDATE_OVERLAY_DESTINATION = 0x31F670
APPLICATION_POINTER_UPDATE_OVERLAY_SOURCE = 0x4EF670
APPLICATION_POINTER_UPDATE_OVERLAY_SIZE = 0x008E
# 31:F670 immediately calls two no-argument reset helpers.  Their flat
# destinations are unrelated mid-function bytes (32:AFEE enters a UI event
# handler and 32:FA40 enters a resource parser), which traps the V3.80 storage
# startup in the resident scheduler.  The otherwise uncalled +0x1D copies are
# complete LINK/RETS functions that only initialize internal state words.
STORAGE_RUNTIME_STATE_RESET_OVERLAY_DESTINATION = 0x32AFEE
STORAGE_RUNTIME_STATE_RESET_OVERLAY_SOURCE = 0x4FAFEE
STORAGE_RUNTIME_STATE_RESET_OVERLAY_SIZE = 0x0056
STORAGE_RUNTIME_TABLE_RESET_OVERLAY_DESTINATION = 0x32FA40
STORAGE_RUNTIME_TABLE_RESET_OVERLAY_SOURCE = 0x4FFA40
STORAGE_RUNTIME_TABLE_RESET_OVERLAY_SIZE = 0x003A
APPLICATION_DEVICE_APPLY_OVERLAY_DESTINATION = 0x332ED2
APPLICATION_DEVICE_APPLY_OVERLAY_SOURCE = 0x502ED2
APPLICATION_DEVICE_APPLY_OVERLAY_SIZE = 0x0024
APPLICATION_STORAGE_MAINTENANCE_OVERLAY_DESTINATION = 0x24BD76
APPLICATION_STORAGE_MAINTENANCE_OVERLAY_SOURCE = 0x41BD76
APPLICATION_STORAGE_MAINTENANCE_OVERLAY_SIZE = 0x042A
# The storage initializer copies five adjacent 16-bit geometry/default words
# from resident ROM 33:71CE into internal 4B64..4B6C.  That ROM data is absent
# from the upgrade package.  Burner sub_50_AA1A reconstructs the same geometry
# after reading the EC:DC:10:95 ID: 64 spare bytes, a 0x800-byte OOB
# column/data-page boundary, 64 pages/block, device ID 0xDC, and 4096 blocks.
# These values also produce the product's documented 512-MiB capacity.  The
# order of the
# first two values is confirmed by the application bad-block scanner, which
# passes 4B66 as BBF6's column while requesting 0x40 bytes.  Embed those
# evidenced values directly instead of the unrelated all-zero PRG words found
# at the same logical PC.
STORAGE_GEOMETRY_DATA_OVERLAY_DESTINATION = 0x3371CE
STORAGE_GEOMETRY_DATA_OVERLAY_SIZE = 0x000A
STORAGE_GEOMETRY_DEFAULT_WORDS = (0x0040, 0x0800, 0x0040, 0x00DC, 0x1000)
APPLICATION_STORAGE_BLOCK_OVERLAY_DESTINATION = 0x270000
APPLICATION_STORAGE_BLOCK_OVERLAY_SOURCE = 0x440000
APPLICATION_STORAGE_BLOCK_OVERLAY_SIZE = 0x0362
# The installed 25:CC94 resource loop calls 33:524C once per application
# lifecycle.  The flat target is the tail of an unrelated framed function; it
# consumes its caller's frame and, after 49 successful-looking iterations,
# wraps SP and falls into missing resident 14:2262.  The updater contains the
# exact same-PC LINK/RETS wrapper at 50:524C and every non-ROM dependency it
# reaches.  The group below is a closed guest-code call graph: all functions
# have explicit prologues/epilogues and their source segment is destination
# segment +0x1D.  Preserve the three segment-50 leaves in the installer because
# that source bank is mutable by the time the resource loop executes.
APPLICATION_RESOURCE_STORAGE_ENTRY_OVERLAY_DESTINATION = 0x33524C
APPLICATION_RESOURCE_STORAGE_ENTRY_OVERLAY_SOURCE = 0x50524C
APPLICATION_RESOURCE_STORAGE_ENTRY_OVERLAY_SIZE = 0x0012
APPLICATION_RESOURCE_STORAGE_MANAGER_OVERLAY_DESTINATION = 0x2EA00C
APPLICATION_RESOURCE_STORAGE_MANAGER_OVERLAY_SOURCE = 0x4BA00C
APPLICATION_RESOURCE_STORAGE_MANAGER_OVERLAY_SIZE = 0x0172
APPLICATION_RESOURCE_STORAGE_QUERY_OVERLAY_DESTINATION = 0x334F24
APPLICATION_RESOURCE_STORAGE_QUERY_OVERLAY_SOURCE = 0x504F24
APPLICATION_RESOURCE_STORAGE_QUERY_OVERLAY_SIZE = 0x0016
APPLICATION_RESOURCE_STORAGE_UPDATE_OVERLAY_DESTINATION = 0x2D78AA
APPLICATION_RESOURCE_STORAGE_UPDATE_OVERLAY_SOURCE = 0x4A78AA
APPLICATION_RESOURCE_STORAGE_UPDATE_OVERLAY_SIZE = 0x01B8
APPLICATION_RESOURCE_STORAGE_GEOMETRY_OVERLAY_DESTINATION = 0x31D582
APPLICATION_RESOURCE_STORAGE_GEOMETRY_OVERLAY_SOURCE = 0x4ED582
APPLICATION_RESOURCE_STORAGE_GEOMETRY_OVERLAY_SIZE = 0x0098
APPLICATION_RESOURCE_STORAGE_METADATA_OVERLAY_DESTINATION = 0x2D29B0
APPLICATION_RESOURCE_STORAGE_METADATA_OVERLAY_SOURCE = 0x4A29B0
APPLICATION_RESOURCE_STORAGE_METADATA_OVERLAY_SIZE = 0x01C8
APPLICATION_RESOURCE_STORAGE_WRITE_OVERLAY_DESTINATION = 0x284CEA
APPLICATION_RESOURCE_STORAGE_WRITE_OVERLAY_SOURCE = 0x454CEA
APPLICATION_RESOURCE_STORAGE_WRITE_OVERLAY_SIZE = 0x0306
APPLICATION_RESOURCE_STORAGE_BLOCK_WRITE_OVERLAY_DESTINATION = 0x25970C
APPLICATION_RESOURCE_STORAGE_BLOCK_WRITE_OVERLAY_SOURCE = 0x42970C
APPLICATION_RESOURCE_STORAGE_BLOCK_WRITE_OVERLAY_SIZE = 0x03E2
APPLICATION_RESOURCE_STORAGE_PAGE_OVERLAY_DESTINATION = 0x270362
APPLICATION_RESOURCE_STORAGE_PAGE_OVERLAY_SOURCE = 0x440362
APPLICATION_RESOURCE_STORAGE_PAGE_OVERLAY_SIZE = 0x0362
APPLICATION_RESOURCE_STORAGE_INDEX_OVERLAY_DESTINATION = 0x327466
APPLICATION_RESOURCE_STORAGE_INDEX_OVERLAY_SOURCE = 0x4F7466
APPLICATION_RESOURCE_STORAGE_INDEX_OVERLAY_SIZE = 0x0068
APPLICATION_RESOURCE_STORAGE_MIRROR_OVERLAY_DESTINATION = 0x29D878
APPLICATION_RESOURCE_STORAGE_MIRROR_OVERLAY_SOURCE = 0x46D878
APPLICATION_RESOURCE_STORAGE_MIRROR_OVERLAY_SIZE = 0x0292
APPLICATION_RESOURCE_STORAGE_COMMIT_OVERLAY_DESTINATION = 0x2E85CA
APPLICATION_RESOURCE_STORAGE_COMMIT_OVERLAY_SOURCE = 0x4B85CA
APPLICATION_RESOURCE_STORAGE_COMMIT_OVERLAY_SIZE = 0x0178
APPLICATION_RESOURCE_STORAGE_RANGE_OVERLAY_DESTINATION = 0x2D0758
APPLICATION_RESOURCE_STORAGE_RANGE_OVERLAY_SOURCE = 0x4A0758
APPLICATION_RESOURCE_STORAGE_RANGE_OVERLAY_SIZE = 0x01D4
APPLICATION_RESOURCE_STORAGE_PREDICATE_OVERLAY_DESTINATION = 0x3329BE
APPLICATION_RESOURCE_STORAGE_PREDICATE_OVERLAY_SOURCE = 0x5029BE
APPLICATION_RESOURCE_STORAGE_PREDICATE_OVERLAY_SIZE = 0x0026
APPLICATION_RESOURCE_STORAGE_SYNC_OVERLAY_DESTINATION = 0x32F56A
APPLICATION_RESOURCE_STORAGE_SYNC_OVERLAY_SOURCE = 0x4FF56A
APPLICATION_RESOURCE_STORAGE_SYNC_OVERLAY_SIZE = 0x003C
APPLICATION_RESOURCE_STORAGE_REFRESH_OVERLAY_DESTINATION = 0x315474
APPLICATION_RESOURCE_STORAGE_REFRESH_OVERLAY_SOURCE = 0x4E5474
APPLICATION_RESOURCE_STORAGE_REFRESH_OVERLAY_SIZE = 0x00BA
APPLICATION_RESOURCE_STORAGE_RECOVERY_OVERLAY_DESTINATION = 0x2781C8
APPLICATION_RESOURCE_STORAGE_RECOVERY_OVERLAY_SOURCE = 0x4481C8
APPLICATION_RESOURCE_STORAGE_RECOVERY_OVERLAY_SIZE = 0x0344
APPLICATION_RESOURCE_STORAGE_STATUS_OVERLAY_DESTINATION = 0x31B33C
APPLICATION_RESOURCE_STORAGE_STATUS_OVERLAY_SOURCE = 0x4EB33C
APPLICATION_RESOURCE_STORAGE_STATUS_OVERLAY_SIZE = 0x00A0
# Resident fopen dispatches through the sixth callback in the active storage
# driver record at 51:27A0.  That callback points to logical 33:6624, but the
# application repeatedly restores unrelated flat code over writable segments
# even after the ROM-01 overlay boundary.  Preserve source 50:6624 as ordinary
# guest DMCU instructions in a free resident-ROM range and update the
# manager-owned record only after exact 25:5858 has initialized it.  Its sole
# child has the same collision at 33:244A, so preserve source 50:244A beside it
# and retarget the wrapper's one source-proven SCALL segment.  Both deeper
# children are already present in this storage graph.
APPLICATION_FILE_DRIVER_CALLBACK_LINKED_DESTINATION = 0x336624
APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_DESTINATION = 0x1AF040
APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_SOURCE = 0x506624
APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_SIZE = 0x000A
APPLICATION_FILE_DRIVER_CALLBACK_CHILD_LINKED_DESTINATION = 0x33244A
APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_DESTINATION = 0x1AF000
APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_SOURCE = 0x50244A
APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_SIZE = 0x0028
APPLICATION_FILE_DRIVER_CALLBACK_CHILD_CALL = 0x1AF042
APPLICATION_FILE_DRIVER_RECORD_SEGMENT_ADDRESS = 0x5127B4
APPLICATION_FILE_DRIVER_RECORD_OFFSET_ADDRESS = 0x5127B6

APPLICATION_RESOURCE_STORAGE_COPY_OVERLAYS = (
    (APPLICATION_RESOURCE_STORAGE_MANAGER_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_MANAGER_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_MANAGER_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_UPDATE_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_UPDATE_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_UPDATE_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_GEOMETRY_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_GEOMETRY_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_GEOMETRY_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_METADATA_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_METADATA_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_METADATA_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_WRITE_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_WRITE_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_WRITE_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_BLOCK_WRITE_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_BLOCK_WRITE_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_BLOCK_WRITE_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_PAGE_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_PAGE_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_PAGE_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_INDEX_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_INDEX_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_INDEX_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_MIRROR_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_MIRROR_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_MIRROR_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_COMMIT_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_COMMIT_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_COMMIT_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_RANGE_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_RANGE_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_RANGE_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_SYNC_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_SYNC_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_SYNC_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_REFRESH_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_REFRESH_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_REFRESH_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_RECOVERY_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_RECOVERY_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_RECOVERY_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_STATUS_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_STATUS_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_STATUS_OVERLAY_SIZE),
)
APPLICATION_RESOURCE_STORAGE_EMBEDDED_OVERLAYS = (
    (APPLICATION_RESOURCE_STORAGE_ENTRY_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_ENTRY_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_ENTRY_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_QUERY_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_QUERY_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_QUERY_OVERLAY_SIZE),
    (APPLICATION_RESOURCE_STORAGE_PREDICATE_OVERLAY_DESTINATION,
     APPLICATION_RESOURCE_STORAGE_PREDICATE_OVERLAY_SOURCE,
     APPLICATION_RESOURCE_STORAGE_PREDICATE_OVERLAY_SIZE),
)
APPLICATION_FILE_DRIVER_CALLBACK_ROM_MODULES = (
    (APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_DESTINATION,
     APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_SOURCE,
     APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_SIZE),
    (APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_DESTINATION,
     APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_SOURCE,
     APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_SIZE),
)
# Callers enter 27:287C as a no-argument storage/resource scan.  The flat
# target is random in-function data beginning with a conditional indirect call,
# which accidentally invokes 27:0000 and corrupts its far return.  Source
# 44:287C is the complete LINK #8 implementation through 44:2BD4.
APPLICATION_STORAGE_SCAN_OVERLAY_DESTINATION = 0x27287C
APPLICATION_STORAGE_SCAN_OVERLAY_SOURCE = 0x44287C
APPLICATION_STORAGE_SCAN_OVERLAY_SIZE = 0x035A
APPLICATION_STORAGE_VERIFY_OVERLAY_DESTINATION = 0x2B4C0A
APPLICATION_STORAGE_VERIFY_OVERLAY_SOURCE = 0x484C0A
APPLICATION_STORAGE_VERIFY_OVERLAY_SIZE = 0x0234
APPLICATION_STORAGE_TRANSFER_OVERLAY_DESTINATION = 0x318C18
APPLICATION_STORAGE_TRANSFER_OVERLAY_SOURCE = 0x4E8C18
APPLICATION_STORAGE_TRANSFER_OVERLAY_SIZE = 0x00AC
APPLICATION_STORAGE_MAP_OVERLAY_DESTINATION = 0x28CC5A
APPLICATION_STORAGE_MAP_OVERLAY_SOURCE = 0x45CC5A
APPLICATION_STORAGE_MAP_OVERLAY_SIZE = 0x02E2
APPLICATION_STATE_DISPATCH_OVERLAY_DESTINATION = 0x303E86
APPLICATION_STATE_DISPATCH_OVERLAY_SOURCE = 0x4D3E86
APPLICATION_STATE_DISPATCH_OVERLAY_SIZE = 0x010C
APPLICATION_STATE_PREPARE_OVERLAY_DESTINATION = 0x2882F4
APPLICATION_STATE_PREPARE_OVERLAY_SOURCE = 0x4582F4
APPLICATION_STATE_PREPARE_OVERLAY_SIZE = 0x02FA
APPLICATION_STATE_POINTER_OVERLAY_DESTINATION = 0x298CAA
APPLICATION_STATE_POINTER_OVERLAY_SOURCE = 0x468CAA
APPLICATION_STATE_POINTER_OVERLAY_SIZE = 0x02A8
APPLICATION_STATE_RECORD_OVERLAY_DESTINATION = 0x2924C6
APPLICATION_STATE_RECORD_OVERLAY_SOURCE = 0x4624C6
APPLICATION_STATE_RECORD_OVERLAY_SIZE = 0x02CC
APPLICATION_STATE_CLASSIFY_OVERLAY_DESTINATION = 0x319C1E
APPLICATION_STATE_CLASSIFY_OVERLAY_SOURCE = 0x4E9C1E
APPLICATION_STATE_CLASSIFY_OVERLAY_SIZE = 0x00AA
APPLICATION_STATE_SERVICE_OVERLAY_DESTINATION = 0x2F3A48
APPLICATION_STATE_SERVICE_OVERLAY_SOURCE = 0x4C3A48
APPLICATION_STATE_SERVICE_OVERLAY_SIZE = 0x014C
APPLICATION_STATE_TRANSFORM_OVERLAY_DESTINATION = 0x22FD9E
APPLICATION_STATE_TRANSFORM_OVERLAY_SOURCE = 0x3FFD9E
APPLICATION_STATE_TRANSFORM_OVERLAY_SIZE = 0x0260
APPLICATION_STATE_FLAGS_OVERLAY_DESTINATION = 0x31D9AA
APPLICATION_STATE_FLAGS_OVERLAY_SOURCE = 0x4ED9AA
APPLICATION_STATE_FLAGS_OVERLAY_SIZE = 0x0098
APPLICATION_STATE_POWER_OVERLAY_DESTINATION = 0x2D2D40
APPLICATION_STATE_POWER_OVERLAY_SOURCE = 0x4A2D40
APPLICATION_STATE_POWER_OVERLAY_SIZE = 0x01C8
APPLICATION_STATE_TICK_OVERLAY_DESTINATION = 0x2FFA32
APPLICATION_STATE_TICK_OVERLAY_SOURCE = 0x4CFA32
APPLICATION_STATE_TICK_OVERLAY_SIZE = 0x011E
# The state/timer worker's slow path copies a 30-word sample and then commits
# it through two ordinary far-call children.  Both flat destinations are
# unrelated function suffixes; their complete same-PC implementations survive
# in the +0x1D application bank.
APPLICATION_STATE_TICK_SAMPLE_OVERLAY_DESTINATION = 0x321EF2
APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SOURCE = 0x4F1EF2
APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SIZE = 0x0084
APPLICATION_STATE_TICK_COMMIT_OVERLAY_DESTINATION = 0x30C61A
APPLICATION_STATE_TICK_COMMIT_OVERLAY_SOURCE = 0x4DC61A
APPLICATION_STATE_TICK_COMMIT_OVERLAY_SIZE = 0x00E2
APPLICATION_STATE_UI_OVERLAY_DESTINATION = 0x22F40C
APPLICATION_STATE_UI_OVERLAY_SOURCE = 0x3FF40C
APPLICATION_STATE_UI_OVERLAY_SIZE = 0x04CA
# This function is linked at 32:C336, sharing that slot with the live flat
# 32:C0xx state machine.  The real overlay manager swaps the two occupants by
# module lifetime.  Keep both exact guest implementations simultaneously by
# relocating this late ADC leaf to an otherwise unused top-bank PC and patching
# the sole call in the installed 22:F40C UI overlay.
APPLICATION_STATE_ADC_LINKED_DESTINATION = 0x32C336
APPLICATION_STATE_ADC_OVERLAY_DESTINATION = 0x5FC336
APPLICATION_STATE_ADC_OVERLAY_SOURCE = 0x4FC336
APPLICATION_STATE_ADC_OVERLAY_SIZE = 0x0050
APPLICATION_STATE_UI_ADC_CALL = 0x22F430
APPLICATION_STATE_MODE_OVERLAY_DESTINATION = 0x335D76
APPLICATION_STATE_MODE_OVERLAY_SOURCE = 0x505D76
APPLICATION_STATE_MODE_OVERLAY_SIZE = 0x000E
APPLICATION_EVENT_INDEX_OVERLAY_DESTINATION = 0x33317E
APPLICATION_EVENT_INDEX_OVERLAY_SOURCE = 0x50317E
APPLICATION_EVENT_INDEX_OVERLAY_SIZE = 0x0024
# Calls to 32:78DE currently land in the middle of the flat 32:* image and
# eventually tear down their caller's frame.  The +0x1D source at 4F:78DE is
# a complete call-free converter with balanced register saves and RETS.
APPLICATION_WIDE_CONVERT_OVERLAY_DESTINATION = 0x3278DE
APPLICATION_WIDE_CONVERT_OVERLAY_SOURCE = 0x4F78DE
APPLICATION_WIDE_CONVERT_OVERLAY_SIZE = 0x0066
# The post-modal validation path calls 32:2728 after its cleanup/commit
# sequence.  Flat 32:2728 is a language-name/data table, not executable code;
# source 4F:2728 is the complete LINK #0 dispatcher through 4F:27A8.  Its
# three mode arms and the shared byte-buffer reader have the same linked-bank
# signature, so install the complete five-function closure together.
APPLICATION_MODAL_VALIDATION_OVERLAY_DESTINATION = 0x322728
APPLICATION_MODAL_VALIDATION_OVERLAY_SOURCE = 0x4F2728
APPLICATION_MODAL_VALIDATION_OVERLAY_SIZE = 0x0082
APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_DESTINATION = 0x274330
APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_SOURCE = 0x444330
APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_SIZE = 0x0354
APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_DESTINATION = 0x2F4EDC
APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_SOURCE = 0x4C4EDC
APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_SIZE = 0x0148
APPLICATION_MODAL_TEXT_FILTER_OVERLAY_DESTINATION = 0x2F9844
APPLICATION_MODAL_TEXT_FILTER_OVERLAY_SOURCE = 0x4C9844
APPLICATION_MODAL_TEXT_FILTER_OVERLAY_SIZE = 0x0136
APPLICATION_MODAL_BUFFER_READ_OVERLAY_DESTINATION = 0x30409E
APPLICATION_MODAL_BUFFER_READ_OVERLAY_SOURCE = 0x4D409E
APPLICATION_MODAL_BUFFER_READ_OVERLAY_SIZE = 0x010C
# The factory startup calls 2A:A952 before it reads the persistent selector at
# logical 10:D072.  Flat 2A:A952 begins in the middle of an unrelated function
# and returns a garbage catalogue/result pointer.  Source 47:A952 is the exact
# LINK/RETS implementation.  The tuples below are its complete bounded call
# closure, plus the exact state-50 workspace initializer at 2E:12BC.  Flat
# 2E:12BC is the middle of a different large function and its RETS consumes the
# state-50 caller's frame; source 4B:12BC is the complete 0x18E-byte same-PC
# function.  Every further application target is already present in the
# runtime overlay set (or is a reconstructed resident-ROM service), except for
# its short 33:415C flag leaf listed below.  Segment-50 leaves must be embedded
# because that source bank is writable RAM by install time.
APPLICATION_FACTORY_DEFAULT_COPY_OVERLAYS = (
    (0x2AA952, 0x47A952, 0x025C),
    (0x3212E4, 0x4F12E4, 0x0088),
    (0x322186, 0x4F2186, 0x0084),
    (0x32974C, 0x4F974C, 0x005E),
    (0x327CDA, 0x4F7CDA, 0x0066),
    (0x3213E8, 0x4F13E8, 0x0004),
    (0x2EE3DC, 0x4BE3DC, 0x0160),
    (0x240D50, 0x410D50, 0x046E),
    (0x3298C4, 0x4F98C4, 0x005E),
    (0x2D30D0, 0x4A30D0, 0x01C8),
    (0x2E0AF6, 0x4B0AF6, 0x018E),
    (0x2A7E3E, 0x477E3E, 0x026C),
    (0x32E5A2, 0x4FE5A2, 0x0042),
    (0x327C74, 0x4F7C74, 0x0066),
    (0x2812A4, 0x4512A4, 0x0004),
    (0x2812A8, 0x4512A8, 0x0004),
    (0x2DCAA6, 0x4ACAA6, 0x01A0),
    (0x2E12BC, 0x4B12BC, 0x018E),
    (0x32AE96, 0x4FAE96, 0x0056),
    (0x2AE5F6, 0x47E5F6, 0x024E),
    (0x326A84, 0x4F6A84, 0x006A),
    (0x30638E, 0x4D638E, 0x0102),
    (0x238364, 0x408364, 0x049C),
    (0x31518C, 0x4E518C, 0x00BA),
    (0x2F7874, 0x4C7874, 0x013C),
    (0x278ED6, 0x448ED6, 0x0340),
    (0x2B8056, 0x488056, 0x0226),
    (0x32C90A, 0x4FC90A, 0x004E),
    (0x2D40D4, 0x4A40D4, 0x01C6),
)
APPLICATION_FILE_ATTACH_COMPARE_WRAPPERS_OVERLAY_DESTINATION = 0x332652
APPLICATION_FILE_ATTACH_COMPARE_WRAPPERS_OVERLAY_SOURCE = 0x502652
APPLICATION_FILE_ATTACH_COMPARE_WRAPPERS_OVERLAY_SIZE = 0x004C
APPLICATION_FACTORY_DEFAULT_EMBEDDED_OVERLAYS = (
    (0x335FC4, 0x505FC4, 0x000C),
    (0x331C12, 0x501C12, 0x002C),
    (0x335FDC, 0x505FDC, 0x000C),
    (0x335CA4, 0x505CA4, 0x000E),
    (0x335D30, 0x505D30, 0x000E),
    (0x335C0A, 0x505C0A, 0x000E),
    (0x334476, 0x504476, 0x001C),
    (0x332BD2, 0x502BD2, 0x0026),
    (0x333D46, 0x503D46, 0x0020),
    (0x333D66, 0x503D66, 0x0020),
    (0x331BE6, 0x501BE6, 0x002C),
    (0x335CEA, 0x505CEA, 0x000E),
    (0x330D4C, 0x500D4C, 0x0032),
    (0x331E7A, 0x501E7A, 0x002C),
    (0x33415C, 0x50415C, 0x001E),
    (0x332EF6, 0x502EF6, 0x0024),
    (APPLICATION_FILE_ATTACH_COMPARE_WRAPPERS_OVERLAY_DESTINATION,
     APPLICATION_FILE_ATTACH_COMPARE_WRAPPERS_OVERLAY_SOURCE,
     APPLICATION_FILE_ATTACH_COMPARE_WRAPPERS_OVERLAY_SIZE),
    (0x331894, 0x501894, 0x002E),
    (0x33443E, 0x50443E, 0x001C),
    (0x334326, 0x504326, 0x001C),
)
APPLICATION_FOREGROUND_STATE50_STORAGE_PAIR_CALL = 0x2B8138
APPLICATION_FOREGROUND_STATE50_STORAGE_PAIR_CALL_SOURCE = 0x488138
# Sixteen direct calls use 32:773A as a conversion/formatting gateway.  Its
# flat bytes start at POP DS0 inside another body; 4F:773A is the exact
# two-word tail trampoline to the real 2F:C216 implementation.
APPLICATION_WIDE_GATE_OVERLAY_DESTINATION = 0x32773A
APPLICATION_WIDE_GATE_OVERLAY_SOURCE = 0x4F773A
APPLICATION_WIDE_GATE_OVERLAY_SIZE = 0x0004
# 33:0070 has the same signature: the flat target is an unrelated frame
# suffix, while 50:0070 is a complete LINK/RETS wrapper used with four words
# of caller arguments.  Segment 50 is mutable RAM at installation time, so
# its shipped words must be embedded in the guest installer.
APPLICATION_TEXT_DISPATCH_OVERLAY_DESTINATION = 0x330070
APPLICATION_TEXT_DISPATCH_OVERLAY_SOURCE = 0x500070
APPLICATION_TEXT_DISPATCH_OVERLAY_SIZE = 0x0038
# The adjacent resource-type-F0 branch uses another independently framed
# four-word wrapper.  Source 50:00A8 begins with LINK #0 and returns at
# 50:00DE; flat 33:00A8 is unrelated code.
APPLICATION_TEXT_DISPATCH_F0_OVERLAY_DESTINATION = 0x3300A8
APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SOURCE = 0x5000A8
APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SIZE = 0x0038
# Five callers enter flat 30:0C24 as an ordinary far-call function, but those
# bytes start with ADDB and eventually tear down a frame they never created.
# The +0x1D source at 4D:0C24 is a complete 280-byte indexed action dispatcher:
# LINK, six balanced register saves, three calls, UNLINK, and RETS.
APPLICATION_INDEX_ACTION_OVERLAY_DESTINATION = 0x300C24
APPLICATION_INDEX_ACTION_OVERLAY_SOURCE = 0x4D0C24
APPLICATION_INDEX_ACTION_OVERLAY_SIZE = 0x0118
# Flat 30:14E4 and 30:15FC are overlapping mid-function decodes in the
# monolithic 30:* image, despite external callers treating both addresses as
# ordinary far-call entries.  The +0x1D source page contains two adjacent,
# complete and independently framed functions at the same PCs.
APPLICATION_PAGE_INDEX_OVERLAY_DESTINATION = 0x3014E4
APPLICATION_PAGE_INDEX_OVERLAY_SOURCE = 0x4D14E4
APPLICATION_PAGE_INDEX_OVERLAY_SIZE = 0x0118
APPLICATION_PAGE_FETCH_OVERLAY_DESTINATION = 0x3015FC
APPLICATION_PAGE_FETCH_OVERLAY_SOURCE = 0x4D15FC
APPLICATION_PAGE_FETCH_OVERLAY_SIZE = 0x0116
# Seven call sites pass four coordinates to 30:1A54, but flat 1A54 starts in
# the previous instruction's FFF0 displacement.  Source 4D:1A54 is the exact
# framed rectangle/image worker with two drawing calls and a shared epilogue.
APPLICATION_RECT_DRAW_OVERLAY_DESTINATION = 0x301A54
APPLICATION_RECT_DRAW_OVERLAY_SOURCE = 0x4D1A54
APPLICATION_RECT_DRAW_OVERLAY_SIZE = 0x0116
# Flat bank 26 starts with packed data, but the application returns into and
# continues a normal framed function at 26:002C.  The +0x1D source page holds
# the complete function, from LINK #0x1A through its balanced RETS.
APPLICATION_IMAGE_WINDOW_OVERLAY_DESTINATION = 0x260000
APPLICATION_IMAGE_WINDOW_OVERLAY_SOURCE = 0x430000
APPLICATION_IMAGE_WINDOW_OVERLAY_SIZE = 0x03BA
# Twelve call sites treat 33:65FC as a standalone service, while the flat
# image begins in the middle of a larger state-machine body.  Source 50:65FC
# is the exact ten-byte framed wrapper around 32:CC9C.
APPLICATION_STATE_COMMIT_OVERLAY_DESTINATION = 0x3365FC
APPLICATION_STATE_COMMIT_OVERLAY_SOURCE = 0x5065FC
APPLICATION_STATE_COMMIT_OVERLAY_SIZE = 0x000A
# The image-window path passes one far pointer to 27:A8B6.  Flat A8B6 is
# packed table text; source 44:A8B6 is the complete framed dispatcher with
# its internal jump-table gap and balanced epilogue at 27:ABEA.
APPLICATION_IMAGE_DISPATCH_OVERLAY_DESTINATION = 0x27A8B6
APPLICATION_IMAGE_DISPATCH_OVERLAY_SOURCE = 0x44A8B6
APPLICATION_IMAGE_DISPATCH_OVERLAY_SIZE = 0x0336
APPLICATION_EVENT_POLL_OVERLAY_DESTINATION = 0x2EFC6A
APPLICATION_EVENT_POLL_OVERLAY_SOURCE = 0x4BFC6A
APPLICATION_EVENT_POLL_OVERLAY_SIZE = 0x015A
APPLICATION_EVENT_CONTROL_OVERLAY_DESTINATION = 0x33463E
APPLICATION_EVENT_CONTROL_OVERLAY_SOURCE = 0x50463E
APPLICATION_EVENT_CONTROL_OVERLAY_SIZE = 0x001A
APPLICATION_TIMER_SETUP_OVERLAY_DESTINATION = 0x317286
APPLICATION_TIMER_SETUP_OVERLAY_SOURCE = 0x4E7286
APPLICATION_TIMER_SETUP_OVERLAY_SIZE = 0x00B4
# 30:12E4 and 30:12F0 call linked 33:1DF6 while releasing two menu-builder
# objects.  The flat destination is the middle of an unrelated application
# routine; source 50:1DF6 is the complete same-PC LINK/UNLINK wrapper.
APPLICATION_OBJECT_RELEASE_OVERLAY_DESTINATION = 0x331DF6
APPLICATION_OBJECT_RELEASE_OVERLAY_SOURCE = 0x501DF6
APPLICATION_OBJECT_RELEASE_OVERLAY_SIZE = 0x002C
# The 20:4488 conversion-table trampoline tail-jumps to 33:1F4E.  Flat
# 33:1F4E is the middle of an unrelated application routine and eventually
# falls through into 33:249A.  Source 50:1F4E is the exact complete framed
# base-10 parser wrapper, ending at its balanced 50:1F76 RETS.
APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_DESTINATION = 0x331F4E
APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SOURCE = 0x501F4E
APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SIZE = 0x002A
# The wrapper calls linked 32:F7FC.  Flat 32:F7FC begins in unrelated code
# and diverts the conversion into the foreground scheduler.  Source 4F:F7FC
# is the complete generic conversion entry, including its 24:2C32 call and
# balanced return at 4F:F834.
APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_DESTINATION = 0x32F7FC
APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SOURCE = 0x4FF7FC
APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SIZE = 0x003A
# The generic core delegates the actual sign/radix/digit walk to 24:2C32.
# Flat 24:2C32 is another mid-function decode that calls the resident main
# loop.  Source 41:2C32 is the complete 0x462-byte parser engine, from LINK
# #0x10 through the shared 41:3092 RETS.
APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_DESTINATION = 0x242C32
APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SOURCE = 0x412C32
APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SIZE = 0x0462
# The parser engine calls 33:3BE6 to classify leading ASCII whitespace.
# Flat 33:3BE6 is an unrelated bitmap/setup body that eventually calls
# resident 14:6E10.  Source 50:3BE6 is the exact 32-byte isspace leaf.
APPLICATION_ASCII_WHITESPACE_OVERLAY_DESTINATION = 0x333BE6
APPLICATION_ASCII_WHITESPACE_OVERLAY_SOURCE = 0x503BE6
APPLICATION_ASCII_WHITESPACE_OVERLAY_SIZE = 0x0020
# Four adjacent source-50 wrappers select quotient versus remainder for the
# unsigned and signed 32-bit helpers.  Keep all four as complete framed
# functions whenever this runtime library bank is resident.
UINT32_MODULO_WRAPPER_OVERLAY_DESTINATION = 0x33249A
UINT32_MODULO_WRAPPER_OVERLAY_SOURCE = 0x50249A
UINT32_MODULO_WRAPPER_OVERLAY_SIZE = 0x0028
INT32_MODULO_WRAPPER_OVERLAY_DESTINATION = 0x3324C2
INT32_MODULO_WRAPPER_OVERLAY_SOURCE = 0x5024C2
INT32_MODULO_WRAPPER_OVERLAY_SIZE = 0x0028
UINT32_DIVIDE_WRAPPER_OVERLAY_DESTINATION = 0x3324EA
UINT32_DIVIDE_WRAPPER_OVERLAY_SOURCE = 0x5024EA
UINT32_DIVIDE_WRAPPER_OVERLAY_SIZE = 0x0028
UINT32_DIVIDE_OVERLAY_DESTINATION = 0x316A14
UINT32_DIVIDE_OVERLAY_SOURCE = 0x4E6A14
UINT32_DIVIDE_OVERLAY_SIZE = 0x00B6
# 3B:5084 calls linked 33:2F1A three times while deriving NAND geometry.
# The flat destination is the middle of an unrelated application routine,
# while source 50:2F1A is the complete call-free highest-set-bit helper ending
# immediately before the already recovered 50:2F3E normalization routine.
UINT32_MSB_INDEX_OVERLAY_DESTINATION = 0x332F1A
UINT32_MSB_INDEX_OVERLAY_SOURCE = 0x502F1A
UINT32_MSB_INDEX_OVERLAY_SIZE = 0x0024
UINT32_NORMALIZE_OVERLAY_DESTINATION = 0x332F3E
UINT32_NORMALIZE_OVERLAY_SOURCE = 0x502F3E
UINT32_NORMALIZE_OVERLAY_SIZE = 0x0024
# The one-shot initializer calls linked 2B:939A directly.  The flat image at
# that address is the middle of a different routine (a parameter push followed
# by 33:0070), which silently diverts initialization into the wrong application
# path.  Source 48:939A is the complete LINK #0x16 task through its balanced
# 48:95BA return.  Restoring it also keeps the A4:5440 root-object state from
# being consumed before the task's own setup path has run.
APPLICATION_INIT_TASK_OVERLAY_DESTINATION = 0x2B939A
APPLICATION_INIT_TASK_OVERLAY_SOURCE = 0x48939A
APPLICATION_INIT_TASK_OVERLAY_SIZE = 0x0222
# Exact upstream selector/context function observed in the recovered native
# chain ``1B:CE3C -> 23:A38C -> 18:21F4``.  The flat linked destination begins
# with an unrelated no-frame routine, while source 40:A38C is a complete
# LINK #0x22 function.  It resolves two launch contexts, calls the exact
# resident application manager, handles returned events 0x86/0x8E, and closes
# through one balanced epilogue at 40:A80E..40:A81E.  Installing this original
# body is necessary for natural application selection; the direct-menu probe
# must not be the only path capable of reaching 18:21F4.
APPLICATION_CONTEXT_LAUNCH_OVERLAY_DESTINATION = 0x23A38C
APPLICATION_CONTEXT_LAUNCH_OVERLAY_SOURCE = 0x40A38C
APPLICATION_CONTEXT_LAUNCH_OVERLAY_SIZE = 0x0494
APPLICATION_RECORD_PREPARE_OVERLAY_DESTINATION = 0x298202
APPLICATION_RECORD_PREPARE_OVERLAY_SOURCE = 0x468202
APPLICATION_RECORD_PREPARE_OVERLAY_SIZE = 0x02AA
APPLICATION_ADDRESS_RESOLVE_OVERLAY_DESTINATION = 0x30C8C0
APPLICATION_ADDRESS_RESOLVE_OVERLAY_SOURCE = 0x4DC8C0
APPLICATION_ADDRESS_RESOLVE_OVERLAY_SIZE = 0x00DE
APPLICATION_RECORD_DISPATCH_OVERLAY_DESTINATION = 0x33048A
APPLICATION_RECORD_DISPATCH_OVERLAY_SOURCE = 0x50048A
APPLICATION_RECORD_DISPATCH_OVERLAY_SIZE = 0x0036
FAR_STRING_LENGTH_OVERLAY_DESTINATION = 0x31AED0
FAR_STRING_LENGTH_OVERLAY_SOURCE = 0x4EAED0
FAR_STRING_LENGTH_OVERLAY_SIZE = 0x00A2
APPLICATION_RECORD_SCAN_OVERLAY_DESTINATION = 0x27716C
APPLICATION_RECORD_SCAN_OVERLAY_SOURCE = 0x44716C
APPLICATION_RECORD_SCAN_OVERLAY_SIZE = 0x0346
FAR_MEMORY_FILL_OVERLAY_DESTINATION = 0x30FE0E
FAR_MEMORY_FILL_OVERLAY_SOURCE = 0x4DFE0E
FAR_MEMORY_FILL_OVERLAY_SIZE = 0x00D2
PACKED_TRIPLE_READ_OVERLAY_DESTINATION = 0x313A72
PACKED_TRIPLE_READ_OVERLAY_SOURCE = 0x4E3A72
PACKED_TRIPLE_READ_OVERLAY_SIZE = 0x00C2
APPLICATION_COMPARE_WRAPPER_OVERLAY_DESTINATION = 0x32C9F0
APPLICATION_COMPARE_WRAPPER_OVERLAY_SOURCE = 0x4FC9F0
APPLICATION_COMPARE_WRAPPER_OVERLAY_SIZE = 0x004C
FAR_MEMORY_COMPARE_OVERLAY_DESTINATION = 0x2CC07E
FAR_MEMORY_COMPARE_OVERLAY_SOURCE = 0x49C07E
FAR_MEMORY_COMPARE_OVERLAY_SIZE = 0x01E2
FAR_POINTER_NORMALIZE_OVERLAY_DESTINATION = 0x32F43E
FAR_POINTER_NORMALIZE_OVERLAY_SOURCE = 0x4FF43E
FAR_POINTER_NORMALIZE_OVERLAY_SIZE = 0x003C
UINT32_MULTIPLY_OVERLAY_DESTINATION = 0x3307B0
UINT32_MULTIPLY_OVERLAY_SOURCE = 0x5007B0
UINT32_MULTIPLY_OVERLAY_SIZE = 0x0034
STORAGE_UNIT_SELECT_OVERLAY_DESTINATION = 0x330B24
STORAGE_UNIT_SELECT_OVERLAY_SOURCE = 0x500B24
STORAGE_UNIT_SELECT_OVERLAY_SIZE = 0x0034
APPLICATION_EVENT_GATE_OVERLAY_DESTINATION = 0x332562
APPLICATION_EVENT_GATE_OVERLAY_SOURCE = 0x502562
APPLICATION_EVENT_GATE_OVERLAY_SIZE = 0x0028
APPLICATION_EVENT_ENABLE_OVERLAY_DESTINATION = 0x333980
APPLICATION_EVENT_ENABLE_OVERLAY_SOURCE = 0x503980
APPLICATION_EVENT_ENABLE_OVERLAY_SIZE = 0x0022
APPLICATION_DISPATCH_POLL_OVERLAY_DESTINATION = 0x324C34
APPLICATION_DISPATCH_POLL_OVERLAY_SOURCE = 0x4F4C34
APPLICATION_DISPATCH_POLL_OVERLAY_SIZE = 0x0074
APPLICATION_KEY_GPIO_SCAN_OVERLAY_DESTINATION = 0x31D9AA
APPLICATION_KEY_GPIO_SCAN_OVERLAY_SOURCE = 0x4ED9AA
APPLICATION_KEY_GPIO_SCAN_OVERLAY_SIZE = 0x0098
APPLICATION_KEY_ACTIVITY_OVERLAY_DESTINATION = 0x2D2D40
APPLICATION_KEY_ACTIVITY_OVERLAY_SOURCE = 0x4A2D40
APPLICATION_KEY_ACTIVITY_OVERLAY_SIZE = 0x01C8
APPLICATION_KEY_COUNTER_OVERLAY_DESTINATION = 0x33417A
APPLICATION_KEY_COUNTER_OVERLAY_SOURCE = 0x50417A
APPLICATION_KEY_COUNTER_OVERLAY_SIZE = 0x001E
APPLICATION_KEY_SYNC_OVERLAY_DESTINATION = 0x336F3C
APPLICATION_KEY_SYNC_OVERLAY_SOURCE = 0x506F3C
APPLICATION_KEY_SYNC_OVERLAY_SIZE = 0x0006
LCD_BUS_INIT_ADDRESS = 0x146622
LCD_BUS_INIT_SOURCE = 0x316622
LCD_BUS_INIT_SIZE = 0x0030
LCD_BUS_WRITE_ADDRESS = 0x14665A
LCD_BUS_WRITE_SOURCE = 0x31665A
LCD_BUS_WRITE_SIZE = 0x003A
LCD_POWER_INIT_ADDRESS = 0x1465CE
LCD_POWER_INIT_SOURCE = 0x3165CE
LCD_POWER_INIT_SIZE = 0x001C
LCD_CONTROLLER_INIT_ADDRESS = 0x1468B0
LCD_CONTROLLER_INIT_SOURCE = 0x3168B0
LCD_CONTROLLER_INIT_SIZE = 0x0228
LCD_CLEAR_ADDRESS = 0x146AD8
LCD_CLEAR_SOURCE = 0x316AD8
LCD_CLEAR_SIZE = 0x0014
LCD_REGION_INIT_ADDRESS = 0x146AEC
LCD_REGION_INIT_SOURCE = 0x316AEC
LCD_REGION_INIT_SIZE = 0x00EA
LCD_BITMAP_INIT_ADDRESS = 0x146E10
LCD_BITMAP_INIT_SOURCE = 0x316E10
LCD_BITMAP_INIT_SIZE = 0x0120
LCD_DELAY_ADDRESS = 0x146F30
LCD_DELAY_SOURCE = 0x316F30
LCD_DELAY_SIZE = 0x0010
# The application has twelve calls to resident 14:B768.  Segment 31 carries
# the complete same-PC dispatcher: LINK #7 at B768, its embedded near-return
# tables and all direct branches, and the shared UNLINK/RETS at C762..C76C.
RESIDENT_RESOURCE_DISPATCH_14_ADDRESS = 0x14B768
RESIDENT_RESOURCE_DISPATCH_14_SOURCE = 0x31B768
RESIDENT_RESOURCE_DISPATCH_14_SIZE = 0x1006
# All 29 calls to resident 1A:423C pop five stack words afterwards.  The
# update image contains an uncalled, complete same-PC copy at
# 37:423C..37:4B9C: LINK #0x41, matching argument reads, local dispatch paths,
# and its own RETS epilogue.  Place those exact guest words in reconstructed
# resident ROM; this is not a host-side service.
RESIDENT_DISPATCH_1A_ADDRESS = 0x1A423C
RESIDENT_DISPATCH_1A_SOURCE = 0x37423C
RESIDENT_DISPATCH_1A_SIZE = 0x0960
# The foreground compositor calls resident 1A:C352 with four 16-bit stack
# words and consumes the returned R0:R3 value.  NP560.PRG contains a complete
# same-PC +0x1D implementation at 37:C352..37:CC70: LINK #0x24, 710 reachable
# instructions, a closed internal CFG, five already-linked external callees,
# and one balanced UNLINK/RETS epilogue.  Copying it closes the gap before the
# separate resident application comparator at 1A:DEAA.
RESIDENT_WIDE_ARITHMETIC_1A_ADDRESS = 0x1AC352
RESIDENT_WIDE_ARITHMETIC_1A_SOURCE = 0x37C352
RESIDENT_WIDE_ARITHMETIC_1A_SIZE = 0x0920
# The resident launch-preparation wrapper 33:3CA6 reaches 1B:23B8 with
# operation 0x0B and a null far context.  NP560.PRG carries the complete
# otherwise-unrelocated +0x1D source body at 38:23B8..38:2C90: LINK #0xA9,
# 692 reachable instructions, a closed internal decision tree and balanced
# UNLINK/RETS epilogue.  The range includes its embedded near-return table.
RESIDENT_OPERATION_1B23B8_ADDRESS = 0x1B23B8
RESIDENT_OPERATION_1B23B8_SOURCE = 0x3823B8
RESIDENT_OPERATION_1B23B8_SIZE = 0x08DA
RESIDENT_TRANSFORM_1B_ADDRESS = 0x1BC5EC
RESIDENT_TRANSFORM_1B_SOURCE = 0x38C5EC
RESIDENT_TRANSFORM_1B_SIZE = 0x0850
RESIDENT_TRANSFORM_1C_ADDRESS = 0x1CCCD4
RESIDENT_TRANSFORM_1C_SOURCE = 0x39CCD4
RESIDENT_TRANSFORM_1C_SIZE = 0x078E
# The exact event-gate path reaches missing resident entry 1C:F28A from
# 30:48D2 with eight argument words.  Its same-PC PRG body at 39:F28A has a
# LINK #20 prologue, 702 reachable instructions, no undecoded frontier, and
# one balanced epilogue at 39:FA06.  All direct branches close inside it.
RESIDENT_EVENT_PACKET_ADDRESS = 0x1CF28A
RESIDENT_EVENT_PACKET_SOURCE = 0x39F28A
RESIDENT_EVENT_PACKET_SIZE = 0x077E
# The exact application-launch path reaches two more resident segment-1D
# functions before it can dispatch an application record.  3A:0EEA fills the
# mutable 50:7778 record window from the current storage/resource context and
# resets A0:7086/7088 at its balanced epilogue.  3A:668A validates and opens
# the far-pointer resource object passed to 18:21F4, establishing the globals
# consumed by that loader.  Both are complete same-PC +0x1D source copies.
RESIDENT_APPLICATION_RECORD_LOADER_ADDRESS = 0x1D0EEA
RESIDENT_APPLICATION_RECORD_LOADER_SOURCE = 0x3A0EEA
RESIDENT_APPLICATION_RECORD_LOADER_SIZE = 0x0770
RESIDENT_APPLICATION_RESOURCE_OPEN_ADDRESS = 0x1D668A
RESIDENT_APPLICATION_RESOURCE_OPEN_SOURCE = 0x3A668A
RESIDENT_APPLICATION_RESOURCE_OPEN_SIZE = 0x0730
# Source 3A:F2EC is the complete +0x1D image of resident 1D:F2EC.  It owns the
# menu-event loop around the hierarchy renderer, draws the surrounding UI
# regions, and handles the 0x80/0x81/0x82/0x83/0x86/0x8E/0x92/0x94/0x95
# event family.  The recovered foreground path reaches it through the exact
# resident wrapper at 20:2DE0; its internal six-target table at 1D:F3DA must
# be visible on both Harvard buses because the controller reads it as data.
RESIDENT_ROOT_MENU_CONTROLLER_ADDRESS = 0x1DF2EC
RESIDENT_ROOT_MENU_CONTROLLER_SOURCE = 0x3AF2EC
RESIDENT_ROOT_MENU_CONTROLLER_SIZE = 0x06D0
# The resource-open body compares data pointers in resident segment 2B
# against four fixed NEPLAYER/NWF strings.  Flat 2B:FF80 is unrelated PRG
# data, while the exact same-linked +0x1D island at 48:FF80 contains both
# accepted version strings, NOAHAUTH, and the associated diagnostics through
# the segment boundary.  This is immutable banked data, not executable code;
# QEMU exposes the source bytes through a narrow Harvard data-bus alias.
APPLICATION_NWF_FORMAT_DATA_OVERLAY_DESTINATION = 0x2BFF80
APPLICATION_NWF_FORMAT_DATA_OVERLAY_SOURCE = 0x48FF80
APPLICATION_NWF_FORMAT_DATA_OVERLAY_SIZE = 0x0080
# Ten application-side callers converge on resident 19:F8B8.  The updater
# contains its complete same-PC implementation at 36:F8B8: LINK #8, 250
# reachable instructions, no undecoded branch frontier, and a balanced RETS
# at 36:FFFE.  The body ends exactly at the segment boundary.
RESIDENT_EVENT_STATE_ADDRESS = 0x19F8B8
RESIDENT_EVENT_STATE_SOURCE = 0x36F8B8
RESIDENT_EVENT_STATE_SIZE = 0x0748
# Timer callback 30:4A36 enters missing resident 10:5090.  Segment 2D carries
# its complete same-PC body: LINK #11, 2,486 reachable instructions, no
# undecoded frontier, and a single balanced RETS at 2D:6ABA.
RESIDENT_EVENT_RENDER_10_ADDRESS = 0x105090
RESIDENT_EVENT_RENDER_10_SOURCE = 0x2D5090
RESIDENT_EVENT_RENDER_10_SIZE = 0x1A2C
# The controller above calls missing resident 10:E4AA three times with a
# four-word frame.  The updater carries the complete same-PC +0x1D body at
# 2D:E4AA..2D:FC0D: LINK #0x10, the page-table layout loop, calls to the
# resident font/region compositors, and one balanced epilogue.  Unlike the
# direct 2C:C9E8 text-page experiment, this is the original hierarchy-aware
# root-menu renderer.
RESIDENT_ROOT_MENU_RENDER_ADDRESS = 0x10E4AA
RESIDENT_ROOT_MENU_RENDER_SOURCE = 0x2DE4AA
RESIDENT_ROOT_MENU_RENDER_SIZE = 0x1764
# The exact root bitmap-resource renderer at 26:CF40 ultimately calls missing
# resident 17:18E6 with six words.  The updater carries the complete same-PC
# implementation at 34:18E6..34:253F: LINK #0x45, 1,027 reachable
# instructions, clipping and packed bitmap/mask composition loops, and one
# balanced register-restore/UNLINK/RETS epilogue.  Restore that original body
# so menu resources are rendered by guest code instead of falling into TRAPs.
RESIDENT_ROOT_BITMAP_BLIT_ADDRESS = 0x1718E6
RESIDENT_ROOT_BITMAP_BLIT_SOURCE = 0x3418E6
RESIDENT_ROOT_BITMAP_BLIT_SIZE = 0x0C5A
# After validating the page-0x3F metadata record, the storage bootstrap calls
# resident 1C:28AC.  Segment 39 contains its complete same-PC implementation:
# a gap-free LINK #0x11 CFG through 39:30AF, including the guest NAND
# erase/program calls and one shared UNLINK/RETS epilogue.
RESIDENT_STORAGE_METADATA_INIT_ADDRESS = 0x1C28AC
RESIDENT_STORAGE_METADATA_INIT_SOURCE = 0x3928AC
RESIDENT_STORAGE_METADATA_INIT_SIZE = 0x0804
# The resource-lifecycle storage graph reaches two additional resident-ROM
# entries.  Both exact +0x1D copies are present in the updater.  39:7FFE has an
# early return at 39:8168 and a taken internal jump over the intervening data
# gap to 39:873C, so its complete span must include the final 39:87C6 RETS.
RESIDENT_RESOURCE_STORAGE_UNIT_ADDRESS = 0x1C7FFE
RESIDENT_RESOURCE_STORAGE_UNIT_SOURCE = 0x397FFE
RESIDENT_RESOURCE_STORAGE_UNIT_SIZE = 0x07CA
# Immediately after the balanced 39:9746 epilogue, the shipped source bank
# contains 25 fixed 0x42-byte menu-page records.  Their pointers cover every
# entry of the 20:1142 application catalogue, including root page zero and
# subgroup pages 6..24.  The next five records are zero, pinning the active
# table boundary at 39:9DBA.  Recreate this exact resident data at 1C:9748.
RESIDENT_MENU_PAGE_TABLE_ADDRESS = 0x1C9748
RESIDENT_MENU_PAGE_TABLE_SOURCE = 0x399748
RESIDENT_MENU_PAGE_TABLE_SIZE = 0x0672
RESIDENT_MENU_PAGE_COUNT = 25
RESIDENT_MENU_PAGE_RECORD_SIZE = 0x0042
RESIDENT_MENU_POINTER_INDEX_ADDRESS = 0x530000
# The direct 2C:C9E8 experiment needs a byte stream for resident 11:5C12,
# not the fixed-size hierarchy records above. Keep this probe-only stream in
# the unused resident gap immediately after the recovered hierarchy table.
DIRECT_GENERIC_MENU_TEXT_STREAM_ADDRESS = 0x1CA000
DIRECT_GENERIC_MENU_TEXT_STREAM_LABELS = (
    "娱乐", "时间", "计算", "翻译", "资料",
)
# 3B:7E4E is a closed LINK #0x0C NAND/storage scanner whose shared epilogue is
# at 3B:84BA..84BC.  Its children are either resident NAND ABI entries, already
# recovered modules, or members of APPLICATION_RESOURCE_STORAGE_* above.
RESIDENT_RESOURCE_STORAGE_SCAN_ADDRESS = 0x1E7E4E
RESIDENT_RESOURCE_STORAGE_SCAN_SOURCE = 0x3B7E4E
RESIDENT_RESOURCE_STORAGE_SCAN_SIZE = 0x0670
# The display/menu builder calls resident 07:36D4 with a six-word descriptor.
# Segment 24 carries a complete same-PC byte-XOR copy primitive: LINK #0,
# six saved registers, an optional REPB loop, and its balanced RETS epilogue.
RESIDENT_XOR_COPY_07_ADDRESS = 0x0736D4
RESIDENT_XOR_COPY_07_SOURCE = 0x2436D4
RESIDENT_XOR_COPY_07_SIZE = 0x0060
# The restored 05:2286 application body calls resident 07:912E with a
# two-word far pointer after normalizing it from a copied descriptor.  The
# updater carries the complete same-PC function at 24:912E: it scans the
# six-byte records hanging from that descriptor, returns the matching index,
# and uses the balanced epilogue at 24:91C2..91CA for both success and -1.
RESIDENT_RECORD_INDEX_LOOKUP_07_ADDRESS = 0x07912E
RESIDENT_RECORD_INDEX_LOOKUP_07_SOURCE = 0x24912E
RESIDENT_RECORD_INDEX_LOOKUP_07_SIZE = 0x009E
# The next 05:2286 path enters 07:1702 with two far-pointer arguments.  The
# complete function and every resident child it can call are present at the
# same PCs in the updater's +0x1D linked banks.  Restore the closed resident
# call graph verbatim; application-bank children such as 2E:4572 and 32:A922
# are installed separately by the existing guest overlay loader.
RESIDENT_RECORD_MATERIALIZE_07_ADDRESS = 0x071702
RESIDENT_RECORD_MATERIALIZE_07_SOURCE = 0x241702
RESIDENT_RECORD_MATERIALIZE_07_SIZE = 0x01FA
RESIDENT_RECORD_BOUNDS_07_ADDRESS = 0x07399C
RESIDENT_RECORD_BOUNDS_07_SOURCE = 0x24399C
RESIDENT_RECORD_BOUNDS_07_SIZE = 0x018C
RESIDENT_DESCRIPTOR_STAGE_07_ADDRESS = 0x07A100
RESIDENT_DESCRIPTOR_STAGE_07_SOURCE = 0x24A100
RESIDENT_DESCRIPTOR_STAGE_07_SIZE = 0x0056
RESIDENT_RECORD_SELECT_07_ADDRESS = 0x073350
RESIDENT_RECORD_SELECT_07_SOURCE = 0x243350
RESIDENT_RECORD_SELECT_07_SIZE = 0x0198
RESIDENT_RECORD_SELECT_PREDICATE_07_ADDRESS = 0x079794
RESIDENT_RECORD_SELECT_PREDICATE_07_SOURCE = 0x249794
RESIDENT_RECORD_SELECT_PREDICATE_07_SIZE = 0x008C
RESIDENT_RECORD_OFFSET_07_ADDRESS = 0x0794CE
RESIDENT_RECORD_OFFSET_07_SOURCE = 0x2494CE
RESIDENT_RECORD_OFFSET_07_SIZE = 0x0092
RESIDENT_RECORD_VALUE_07_ADDRESS = 0x076748
RESIDENT_RECORD_VALUE_07_SOURCE = 0x246748
RESIDENT_RECORD_VALUE_07_SIZE = 0x0106
# The record parser calls 07:7D74 once with three far strings.  The complete
# +0x1D-bank body at 24:7D74 removes an optional suffix from the first string
# and appends an optional replacement.  Its two children (31:AED0 strlen and
# 32:8204 string append) are already recovered application overlays.  The
# next closed function begins at 24:7E48.
RESIDENT_SUFFIX_REPLACE_07_ADDRESS = 0x077D74
RESIDENT_SUFFIX_REPLACE_07_SOURCE = 0x247D74
RESIDENT_SUFFIX_REPLACE_07_SIZE = 0x00D4
RESIDENT_RECORD_COMPOSE_06_ADDRESS = 0x06D816
RESIDENT_RECORD_COMPOSE_06_SOURCE = 0x23D816
RESIDENT_RECORD_COMPOSE_06_SIZE = 0x02AC
# Eleven original callers pass two far character pointers followed by two
# delimiter bytes to 06:DD56.  The updater carries the complete, call-free
# implementation at the corresponding +0x1D bank address 23:DD56.  It copies
# one delimited field (preserving two-byte characters and bracketed text),
# NUL-terminates the destination, and returns the advanced source pointer.
# The next closed function starts at 23:DFE8, proving the exact extent.
RESIDENT_DELIMITED_FIELD_COPY_06_ADDRESS = 0x06DD56
RESIDENT_DELIMITED_FIELD_COPY_06_SOURCE = 0x23DD56
RESIDENT_DELIMITED_FIELD_COPY_06_SIZE = 0x0292
RESIDENT_HELPER_04_FFD8_ADDRESS = 0x04FFD8
RESIDENT_HELPER_04_FFD8_SOURCE = 0x21FFD8
RESIDENT_HELPER_04_FFD8_SIZE = 0x0020
RESIDENT_HELPER_05_FFCA_ADDRESS = 0x05FFCA
RESIDENT_HELPER_05_FFCA_SOURCE = 0x22FFCA
RESIDENT_HELPER_05_FFCA_SIZE = 0x0034
RESIDENT_RECORD_MATERIALIZATION_CLOSURE = (
    (RESIDENT_RECORD_MATERIALIZE_07_ADDRESS,
     RESIDENT_RECORD_MATERIALIZE_07_SOURCE,
     RESIDENT_RECORD_MATERIALIZE_07_SIZE,
     "resident_record_materialize_07_1702"),
    (RESIDENT_RECORD_BOUNDS_07_ADDRESS,
     RESIDENT_RECORD_BOUNDS_07_SOURCE,
     RESIDENT_RECORD_BOUNDS_07_SIZE,
     "resident_record_bounds_07_399c"),
    (RESIDENT_DESCRIPTOR_STAGE_07_ADDRESS,
     RESIDENT_DESCRIPTOR_STAGE_07_SOURCE,
     RESIDENT_DESCRIPTOR_STAGE_07_SIZE,
     "resident_descriptor_stage_07_a100"),
    (RESIDENT_RECORD_SELECT_07_ADDRESS,
     RESIDENT_RECORD_SELECT_07_SOURCE,
     RESIDENT_RECORD_SELECT_07_SIZE,
     "resident_record_select_07_3350"),
    (RESIDENT_RECORD_SELECT_PREDICATE_07_ADDRESS,
     RESIDENT_RECORD_SELECT_PREDICATE_07_SOURCE,
     RESIDENT_RECORD_SELECT_PREDICATE_07_SIZE,
     "resident_record_select_predicate_07_9794"),
    (RESIDENT_RECORD_OFFSET_07_ADDRESS,
     RESIDENT_RECORD_OFFSET_07_SOURCE,
     RESIDENT_RECORD_OFFSET_07_SIZE,
     "resident_record_offset_07_94ce"),
    (RESIDENT_RECORD_VALUE_07_ADDRESS,
     RESIDENT_RECORD_VALUE_07_SOURCE,
     RESIDENT_RECORD_VALUE_07_SIZE,
     "resident_record_value_07_6748"),
    (RESIDENT_SUFFIX_REPLACE_07_ADDRESS,
     RESIDENT_SUFFIX_REPLACE_07_SOURCE,
     RESIDENT_SUFFIX_REPLACE_07_SIZE,
     "resident_suffix_replace_07_7d74"),
    (RESIDENT_RECORD_COMPOSE_06_ADDRESS,
     RESIDENT_RECORD_COMPOSE_06_SOURCE,
     RESIDENT_RECORD_COMPOSE_06_SIZE,
     "resident_record_compose_06_d816"),
    (RESIDENT_DELIMITED_FIELD_COPY_06_ADDRESS,
     RESIDENT_DELIMITED_FIELD_COPY_06_SOURCE,
     RESIDENT_DELIMITED_FIELD_COPY_06_SIZE,
     "resident_delimited_field_copy_06_dd56"),
    (RESIDENT_HELPER_04_FFD8_ADDRESS,
     RESIDENT_HELPER_04_FFD8_SOURCE,
     RESIDENT_HELPER_04_FFD8_SIZE,
     "resident_helper_04_ffd8"),
    (RESIDENT_HELPER_05_FFCA_ADDRESS,
     RESIDENT_HELPER_05_FFCA_SOURCE,
     RESIDENT_HELPER_05_FFCA_SIZE,
     "resident_helper_05_ffca"),
)
RESIDENT_APPLICATION_LOOP_0E_ADDRESS = 0x0E75BA
RESIDENT_APPLICATION_LOOP_0E_SOURCE = 0x2B75BA
RESIDENT_APPLICATION_LOOP_0E_SIZE = 0x2374
RESIDENT_RECURSIVE_16_ADDRESS = 0x1652AA
RESIDENT_RECURSIVE_16_SOURCE = 0x3352AA
RESIDENT_RECURSIVE_16_SIZE = 0x0D86
# Application image processing reaches resident 17:4A3A with a five-word
# argument frame.  The updater carries the complete same-PC body at 34:4A3A,
# including its internal dispatch gaps and the shared UNLINK/RETS epilogue.
RESIDENT_APPLICATION_SELECTOR_17_ADDRESS = 0x174A3A
RESIDENT_APPLICATION_SELECTOR_17_SOURCE = 0x344A3A
RESIDENT_APPLICATION_SELECTOR_17_SIZE = 0x0C34
RESIDENT_FONT_LOOKUP_ADDRESS = 0x179244
RESIDENT_FONT_LOOKUP_SOURCE = 0x349244
RESIDENT_FONT_LOOKUP_SIZE = 0x0BDE
# Eleven original callers enter resident 17:E3EE with three far-pointer
# arguments: FILE pointer, source buffer, and 32-bit byte count in reverse push
# order.  The updater contains the complete same-PC +0x1D file-write
# implementation at 34:E3EE, including both balanced return paths through
# 34:EF6C.  Three helpers used by this file/storage graph have complete
# same-PC sources too, but their linked destinations are application-bank
# collisions.  Keep those helpers in the otherwise unused resident 07:4000
# window and retarget only this source-proven call closure.  The already
# recovered sector probe has the same collision and remains at 5F:F928.
RESIDENT_FILE_WRITE_ADDRESS = 0x17E3EE
RESIDENT_FILE_WRITE_SOURCE = 0x34E3EE
RESIDENT_FILE_WRITE_SIZE = 0x0B80
RESIDENT_STORAGE_DRIVER_ADDRESS = 0x074000
RESIDENT_STORAGE_DRIVER_SOURCE = 0x4A3460
RESIDENT_STORAGE_DRIVER_SIZE = 0x01C8
RESIDENT_STORAGE_SELECT_ADDRESS = 0x074200
RESIDENT_STORAGE_SELECT_SOURCE = 0x45AC4C
RESIDENT_STORAGE_SELECT_SIZE = 0x02EE
RESIDENT_STORAGE_PAIR_ADDRESS = 0x074500
RESIDENT_STORAGE_PAIR_SOURCE = 0x4D6E9E
RESIDENT_STORAGE_PAIR_SIZE = 0x0100
RESIDENT_STORAGE_PROBE_WRAPPER_ADDRESS = 0x074600
RESIDENT_STORAGE_PROBE_WRAPPER_SOURCE = 0x4F1614
RESIDENT_STORAGE_PROBE_WRAPPER_SIZE = 0x0088
RESIDENT_STORAGE_MUL_DIV_ADDRESS = 0x074700
RESIDENT_STORAGE_MUL_DIV_SOURCE = 0x4EB1FA
RESIDENT_STORAGE_MUL_DIV_SIZE = 0x00A2
RESIDENT_STORAGE_SCAN_ADDRESS = 0x074800
RESIDENT_STORAGE_SCAN_SOURCE = 0x39E37E
RESIDENT_STORAGE_SCAN_SIZE = 0x0786
RESIDENT_STORAGE_RESULT_LEAF_ADDRESS = 0x075000
RESIDENT_STORAGE_RESULT_LEAF_SOURCE = 0x50525E
RESIDENT_STORAGE_RESULT_LEAF_SIZE = 0x0012
RESIDENT_STORAGE_RANGE_LEAF_ADDRESS = 0x075020
RESIDENT_STORAGE_RANGE_LEAF_SOURCE = 0x4F9C6A
RESIDENT_STORAGE_RANGE_LEAF_SIZE = 0x005C
# These storage helpers are recovered into the free 07:4000 window at a
# different PC as well as a different segment.  Their ACxx instructions are
# same-segment absolute jumps, so copying the words verbatim would retain the
# source PC and branch into an unrelated/empty part of segment 07.  Keep the
# source-proven instruction addresses and targets explicit so relocation is
# signature checked in the same way as far-call retargeting.
RESIDENT_STORAGE_DRIVER_INTERNAL_AJMPS = (
    (0x4A34BA, 0x361C), (0x4A35B8, 0x35D2), (0x4A35CE, 0x361E),
)
# The driver's callback dispatches at source 4A:3536 and 4A:35AE are encoded
# as RETS after explicitly pushing their return PCs and logical segment 2D.
# Relocating the body to 07:4000 therefore requires relocating both constructed
# far return frames too; otherwise a successful callback returns into reused
# 2D code.
RESIDENT_STORAGE_DRIVER_CALLBACK_RETURN_FRAMES = (
    (0x4A3526, 0x4A352C, 0x3538, 0x002D),
    (0x4A359E, 0x4A35A4, 0x35B0, 0x002D),
)
RESIDENT_STORAGE_SELECT_INTERNAL_AJMPS = (
    (0x45ACD4, 0xAE2E), (0x45ACE2, 0xAE08),
    (0x45AD20, 0xAD28), (0x45AD24, 0xAEAE),
    (0x45AD82, 0xADD8), (0x45ADAC, 0xADC4),
    (0x45ADC0, 0xAEAE), (0x45ADE0, 0xADEE),
    (0x45ADEA, 0xAD86), (0x45ADF4, 0xADFE),
    (0x45ADFA, 0xAF30), (0x45AE26, 0xACE6),
    (0x45AE2A, 0xAEAE), (0x45AE36, 0xAE8A),
    (0x45AE5A, 0xAE62), (0x45AE5E, 0xAEAE),
    (0x45AE68, 0xAE80), (0x45AE7C, 0xAF30),
    (0x45AEAA, 0xAE3A), (0x45AECE, 0xAED8),
    (0x45AED4, 0xAF30), (0x45AF0E, 0xAF2C),
)
RESIDENT_STORAGE_PAIR_INTERNAL_AJMPS = (
    (0x4D6F18, 0x6F24), (0x4D6F20, 0x6F92),
)
RESIDENT_STORAGE_PROBE_WRAPPER_INTERNAL_AJMPS = (
    (0x4F1636, 0x1640), (0x4F163C, 0x1696),
    (0x4F164E, 0x1684), (0x4F1668, 0x1670),
    (0x4F166C, 0x1692), (0x4F168E, 0x1652),
)
RESIDENT_STORAGE_MUL_DIV_INTERNAL_AJMPS = (
    (0x4EB218, 0xB284), (0x4EB280, 0xB28C),
    (0x4EB288, 0xB28E),
)
RESIDENT_STORAGE_SCAN_INTERNAL_AJMPS = (
    (0x39E3FC, 0xE404), (0x39E400, 0xEAF4),
    (0x39E422, 0xE624), (0x39E458, 0xE4BA),
    (0x39E4B6, 0xEAF4), (0x39E4D6, 0xE5FC),
    (0x39E50A, 0xE512), (0x39E50E, 0xEAF4),
    (0x39E61C, 0xE4DA), (0x39E620, 0xEAF4),
    (0x39E660, 0xE7DE), (0x39E69C, 0xE6C8),
    (0x39E6C4, 0xE6D0), (0x39E76A, 0xE77C),
    (0x39E778, 0xE7A2), (0x39E7FA, 0xEAD0),
    (0x39E834, 0xE83C), (0x39E838, 0xEAF4),
    (0x39E8B2, 0xE8DE), (0x39E8DA, 0xE8E6),
    (0x39E98A, 0xE992), (0x39E98E, 0xEAF4),
    (0x39EA0A, 0xEA1C), (0x39EA18, 0xEA42),
    (0x39EAF0, 0xE7FE),
)
RESIDENT_FONT_BLIT_ADDRESS = 0x186454
RESIDENT_FONT_BLIT_SOURCE = 0x356454
RESIDENT_FONT_BLIT_SIZE = 0x029A
# The result-header parser terminates at a six-word call to resident 18:66EE.
# Its +0x1D same-PC source begins exactly where the recovered font-blit module
# ends and has a balanced epilogue immediately before resident memcpy 18:6D56.
# It is a closed, call-free region/bit-copy routine, including all internal
# linked SJMP targets from 18:66EE through 18:6D54.
RESIDENT_RESULT_REGION_COPY_ADDRESS = 0x1866EE
RESIDENT_RESULT_REGION_COPY_SOURCE = 0x3566EE
RESIDENT_RESULT_REGION_COPY_SIZE = 0x0668
# The recovered 30:1A54 rectangle worker reaches resident 18:7A02 with five
# stack arguments.  Source 35:7A02 is a complete call-free pixel/region
# compositor with 888 reachable instructions and a shared epilogue.
RESIDENT_REGION_COMPOSE_18_ADDRESS = 0x187A02
RESIDENT_REGION_COMPOSE_18_SOURCE = 0x357A02
RESIDENT_REGION_COMPOSE_18_SIZE = 0x0AD2
# Two recovered application paths call resident 18:21F4 with two far-pointer
# arguments.  Source 35:21F4 is the complete LINK #0x0F application launch
# manager through 35:2D20.  It reads the selected application's 16-bit code,
# calls 2F:E4C8 to resolve the registry record, and then dispatches the linked
# far entry point.  Restore this original resident selector as static ROM.
RESIDENT_APPLICATION_LAUNCH_MANAGER_ADDRESS = 0x1821F4
RESIDENT_APPLICATION_LAUNCH_MANAGER_SOURCE = 0x3521F4
RESIDENT_APPLICATION_LAUNCH_MANAGER_SIZE = 0x0B2E
# The menu page renderer at 18:A292 passes its 0x3C-byte work records to
# resident 11:5C12.  The updater contains the complete same-PC +0x1D body at
# 2E:5C12..2E:72B6: LINK #0x39, a closed internal decision tree, four calls
# to the already recovered 30:FE0E memory-fill primitive, and one shared
# balanced epilogue.  Restore the vendor record decoder rather than treating
# malformed output as an LCD/font problem.
RESIDENT_MENU_RECORD_DECODE_11_ADDRESS = 0x115C12
RESIDENT_MENU_RECORD_DECODE_11_SOURCE = 0x2E5C12
RESIDENT_MENU_RECORD_DECODE_11_SIZE = 0x16A4
# The 31:138C menu wrapper has one direct call to resident 18:9A58.  The
# update program contains the complete same-PC +0x1D image at 35:9A58,
# including its fifteen-entry 0x80..0x8e event jump table at 35:9BDA and its
# balanced epilogue immediately before the already recovered 18:A510 module.
# Keep the original guest dispatcher and table contiguous in internal ROM.
RESIDENT_MENU_EVENT_DISPATCH_ADDRESS = 0x189A58
RESIDENT_MENU_EVENT_DISPATCH_SOURCE = 0x359A58
RESIDENT_MENU_EVENT_DISPATCH_SIZE = 0x0AB8
# The edge renderer calls resident 18:A510 with four coordinate words.  Its
# +0x1D image at 35:A510 is a complete LINK #0x52 pixel/region compositor:
# all branches close at the shared 35:AFAA epilogue, and every far call is
# already linked to an external destination segment.
RESIDENT_REGION_MASK_18_ADDRESS = 0x18A510
RESIDENT_REGION_MASK_18_SOURCE = 0x35A510
RESIDENT_REGION_MASK_18_SIZE = 0x0AAA
# Operation 0x0B passes a local far pointer to resident 18:CFA8 after its four
# work tables are allocated.  The updater keeps the complete same-PC +0x1D
# body at 35:CFA8..35:DA2C: LINK #0xB3, a closed internal decision tree and
# one balanced epilogue.  This routine builds the 0x164-byte operation object
# and binds its resource/file state; keep the original guest implementation.
RESIDENT_OPERATION_CONTEXT_18_ADDRESS = 0x18CFA8
RESIDENT_OPERATION_CONTEXT_18_SOURCE = 0x35CFA8
RESIDENT_OPERATION_CONTEXT_18_SIZE = 0x0A86
# The resource initializer reaches resident 1E:5084 through 31:F670.  The
# updater carries a complete, uncalled same-PC copy at 3B:5084..3B:571B:
# LINK #8, all internal branch targets, the NAND ID/page-read path, and one
# shared UNLINK/RETS epilogue.  The intra-procedural CFG covers the range
# without gaps, so retain the complete vendor body rather than replacing the
# storage probe with a host-side shortcut.
RESIDENT_STORAGE_INIT_ADDRESS = 0x1E5084
RESIDENT_STORAGE_INIT_SOURCE = 0x3B5084
RESIDENT_STORAGE_INIT_SIZE = 0x0698
RESIDENT_APPLICATION_CONFIG_ADDRESS = 0x1EB7F6
RESIDENT_APPLICATION_CONFIG_SOURCE = 0x3BB7F6
RESIDENT_APPLICATION_CONFIG_SIZE = 0x065C
# The foreground file/object worker calls resident 1E:D15C with one far
# pointer.  The updater carries a complete same-PC copy at 3B:D15C: LINK #3,
# 669 reachable call-free instructions, no undecoded frontiers, and a single
# balanced UNLINK/RETS epilogue at 3B:D7AA..D7AC.
RESIDENT_OBJECT_TABLE_UPDATE_ADDRESS = 0x1ED15C
RESIDENT_OBJECT_TABLE_UPDATE_SOURCE = 0x3BD15C
RESIDENT_OBJECT_TABLE_UPDATE_SIZE = 0x0652
RESIDENT_CONFIGURATION_VARIANTS = (
    (0x1A4B9C, 0x374B9C, 0x095A, "resident_config_variant_1a_4b9c"),
    (0x1D49A2, 0x3A49A2, 0x0742, "resident_config_variant_1d_49a2"),
    (0x13DA56, 0x30DA56, 0x1140, "resident_config_variant_13_da56"),
    (0x19A154, 0x36A154, 0x09D4, "resident_config_variant_19_a154"),
)
RESIDENT_APPLICATION_STATE_ADDRESS = 0x1EF734
RESIDENT_APPLICATION_STATE_SOURCE = 0x3BF734
RESIDENT_APPLICATION_STATE_SIZE = 0x0648
RESIDENT_HANDLER_1F12B4_ADDRESS = 0x1F12B4
RESIDENT_HANDLER_1F12B4_SOURCE = 0x3C12B4
RESIDENT_HANDLER_1F12B4_SIZE = 0x0634
RESIDENT_FILE_OPEN_1F1F1A_ADDRESS = 0x1F1F1A
RESIDENT_FILE_OPEN_1F1F1A_SOURCE = 0x3C1F1A
RESIDENT_FILE_OPEN_1F1F1A_SIZE = 0x062E
# The resident fopen body calls linked 33:02D8 with one far record pointer at
# 1F:218E and 1F:21DE.  Flat 33:02D8 starts in the middle of an unrelated
# wide-value function and overwrites the fopen caller's saved frame.  The
# source-50 same-PC entry is the exact LINK #0 attribute test: it reads byte
# record+0x14, masks bits 0/2, and returns 0 or FFFF through a balanced RETS.
# Keep the live flat segment-33 body intact by installing this independently
# called leaf at the same PC in collision-free executable bank 5F and
# retargeting only the two source-proven calls in the resident fopen copy.
APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_LINKED_DESTINATION = 0x3302D8
APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_DESTINATION = 0x5F02D8
APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_SOURCE = 0x5002D8
APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_SIZE = 0x0038
APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_CALL_SOURCES = (0x3C218E, 0x3C21DE)
APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_CALLS = (0x1F218E, 0x1F21DE)
# The native foreground dispatcher reaches 1F:B496 with one application-event
# word.  The missing mask-ROM entry has an exact +0x1D-segment linked copy at
# 3C:B496: LINK #0x0C, a closed application-event decision tree, and one
# balanced UNLINK/RETS epilogue at 3C:BA62..BA64.  The source has no literal
# in-place callers, while nine PRG call sites target the resident address.
RESIDENT_APPLICATION_EVENT_ADDRESS = 0x1FB496
RESIDENT_APPLICATION_EVENT_SOURCE = 0x3CB496
RESIDENT_APPLICATION_EVENT_SIZE = 0x05D0
RESIDENT_RESOURCE_INIT_1BCE3C_ADDRESS = 0x1BCE3C
RESIDENT_RESOURCE_INIT_1BCE3C_SOURCE = 0x38CE3C
RESIDENT_RESOURCE_INIT_1BCE3C_SIZE = 0x0846
RESIDENT_STATE_IMPORT_ADDRESS = 0x1FF470
RESIDENT_STATE_IMPORT_SOURCE = 0x3CF470
RESIDENT_STATE_IMPORT_SIZE = 0x05C8

# The original top-level application path was recovered by following the
# only literal call chain which writes the far FILE pointer at A0:7DEE.  Each
# flat destination is unrelated pre-overlay data; the +0x1D-segment source is
# a complete same-PC function from the shipped PRG.  The chain is:
#   2D:7DD2 -> 22:9738 -> 22:515E -> 32:512C -> 1B:CE3C
#             -> 2E:BE2E -> 30:C9A2 -> resident 1F:1F1A.
APPLICATION_TOP_LEVEL_OVERLAY_DESTINATION = 0x2D7DD2
APPLICATION_TOP_LEVEL_OVERLAY_SOURCE = 0x4A7DD2
# The adjacent result-default selector at 2D:7F88 is also live: 33:43CE calls
# it whenever 28:94C2 returns no result.  Flat 2D:7F88 starts in the middle of
# another body and returned 0x1FF0 into A2:2AAA.  The source image contains the
# complete adjacent LINK #0x1A function through 4A:813C, so keep both closed
# functions in the same contiguous overlay.
APPLICATION_TOP_LEVEL_DISPATCH_SIZE = 0x01B6
APPLICATION_RESULT_DEFAULT_SELECTOR_OFFSET = 0x01B6
APPLICATION_RESULT_DEFAULT_SELECTOR_SIZE = 0x01B6
APPLICATION_TOP_LEVEL_OVERLAY_SIZE = (
    APPLICATION_TOP_LEVEL_DISPATCH_SIZE
    + APPLICATION_RESULT_DEFAULT_SELECTOR_SIZE
)
# The update program's directly callable foreground is the page-one
# ``同步学习`` application, not the resident ROM desktop.  Both its outer
# continuation and inner main write the same initial path value one before
# the first native render.  A real NP560+ instead cold-starts at path zero;
# the missing resident application-selection policy is responsible for that
# choice.  The optional reconstruction below changes only those two
# manager-owned cold-start constants after the exact application copies have
# been installed.  It does not synthesize a key and it leaves all subsequent
# native path transitions and renderers intact.
RESIDENT_ROOT_DESKTOP_PATH_WRITES = (
    (0x2D7E88, 0x4A7E88),
    (0x2251FE, 0x3F51FE),
)
APPLICATION_PROVISION_TRIGGER_DESTINATION = 0x2D7F66
APPLICATION_PROVISION_TRIGGER_SOURCE = 0x4A7F66
APPLICATION_PROVISION_TRIGGER_ORIGINAL_WORDS = (0xBD33, 0x6F30)
# The editing loop calls 29:5126 after every cursor/page mutation and then
# immediately performs its redraw/commit sequence.  The flat target is an
# unrelated resident non-local-exit leaf and can never return to those call
# sites.  The unused +0x1D copy at 46:5126 is the ABI-compatible LINK #4
# refresh routine: all internal branches close at 46:53D8 and its balanced
# epilogue ends at 46:53E6.  Restore it as writable application code before
# entering the foreground loop.
APPLICATION_CURSOR_REFRESH_OVERLAY_DESTINATION = 0x295126
APPLICATION_CURSOR_REFRESH_OVERLAY_SOURCE = 0x465126
APPLICATION_CURSOR_REFRESH_OVERLAY_SIZE = 0x02C2
# The exact foreground callback at 41:162C calls 2D:9DFC with five words.
# Flat 2D:9DFC begins in the middle of an unrelated unframed routine and its
# RETS escapes to the resident dispatcher instead of returning to 41:18C4.
# The same-PC linked image at 4A:9DFC is the complete LINK #4 implementation
# with a balanced epilogue at 4A:9FA6.  Reinstall it after the application
# load alongside the cursor body; QEMU only supplies writable/executable RAM.
APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_DESTINATION = 0x2D9DFC
APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_SOURCE = 0x4A9DFC
APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_SIZE = 0x01AC
# Thirteen UI/state paths call 20:3390 with a single mode argument (0, 1 or
# 3), but the flat destination is erased PRG space.  The otherwise uncalled
# +0x1D same-PC copy at 3D:3390 is the complete ABI match: LINK #4, a closed
# mode/UI dispatch graph, and a balanced epilogue at 3D:393A.  Install the
# original guest routine before the foreground loop; otherwise erased FFFF
# words clear SP bit 15 and execution wanders into unrelated PRG code.
APPLICATION_UI_STATE_OVERLAY_DESTINATION = 0x203390
APPLICATION_UI_STATE_OVERLAY_SOURCE = 0x3D3390
APPLICATION_UI_STATE_OVERLAY_SIZE = 0x05AC
# Menu events 0x82 and 0x84 call linked 20:0B82 with the current catalogue
# pointer and action values 1, 7, or 9.  The flat target is unrelated PRG
# bytes.  Source 3D:0B82 is the complete LINK #0x25 helper through 3D:1140;
# it is immediately followed by the unique 124-entry, five-word application
# catalogue through 3D:161A.  Install code and data together so all returned
# pointers address the original vendor records.
APPLICATION_MENU_CATALOG_OVERLAY_DESTINATION = 0x200B82
APPLICATION_MENU_CATALOG_OVERLAY_SOURCE = 0x3D0B82
APPLICATION_MENU_CATALOG_OVERLAY_SIZE = 0x0A98
# The menu launcher initializes its two 0x400-byte work areas and calls the
# exact resident 18:9A58 event dispatcher through linked wrapper 31:138C.
# The only source-level copy is the complete 4E:138C..4E:145A body.
APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_DESTINATION = 0x31138C
APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SOURCE = 0x4E138C
APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SIZE = 0x00CE
# The event wrapper's post-dispatch state reset and two cleanup calls are
# three short source-50 leaves.  Their flat segment-33 PCs are continuations
# of unrelated large functions, so each must follow the menu overlay lifetime.
APPLICATION_MENU_STATE_CLEAR_OVERLAY_DESTINATION = 0x334E5E
APPLICATION_MENU_STATE_CLEAR_OVERLAY_SOURCE = 0x504E5E
APPLICATION_MENU_STATE_CLEAR_OVERLAY_SIZE = 0x0016
APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_DESTINATION = 0x33468C
APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SOURCE = 0x50468C
APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SIZE = 0x0016
APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_DESTINATION = 0x334D2A
APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SOURCE = 0x504D2A
APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SIZE = 0x0016
# Resident 18:9A58 begins by calling these three segment-33 wrappers.  The
# bootstrap foreground reuses all three destinations before the menu manager
# runs, so restore their exact source-50 bodies at that manager boundary too.
APPLICATION_MENU_GLOBAL_RESET_OVERLAY_DESTINATION = 0x334DDA
APPLICATION_MENU_GLOBAL_RESET_OVERLAY_SOURCE = 0x504DDA
APPLICATION_MENU_GLOBAL_RESET_OVERLAY_SIZE = 0x0016
# Positive A4:53A3 state takes this complete source-50 UI-state initializer
# before the event poll loop.  Its flat destination is also foreground-owned.
APPLICATION_MENU_EVENT_STATE_OVERLAY_DESTINATION = 0x330EDC
APPLICATION_MENU_EVENT_STATE_OVERLAY_SOURCE = 0x500EDC
APPLICATION_MENU_EVENT_STATE_OVERLAY_SIZE = 0x0032
# 33:65D4 delegates to this complete source-4C table reset.  Keep it in the
# compact copy helper because its source is stable and the 0x128-byte body is
# much larger than the source-50 wrappers embedded above.
APPLICATION_MENU_UI_PREPARE_CORE_OVERLAY_DESTINATION = 0x2FD266
APPLICATION_MENU_UI_PREPARE_CORE_OVERLAY_SOURCE = 0x4CD266
APPLICATION_MENU_UI_PREPARE_CORE_OVERLAY_SIZE = 0x0128
# 18:A186 calls this four-argument record/buffer initializer while constructing
# the first menu screen.  The flat 30:5F7E bytes are an unrelated function
# tail, whereas 4D:5F7E..6080 is the complete same-PC LINK/RETS body.
APPLICATION_MENU_BUFFER_SETUP_OVERLAY_DESTINATION = 0x305F7E
APPLICATION_MENU_BUFFER_SETUP_OVERLAY_SOURCE = 0x4D5F7E
APPLICATION_MENU_BUFFER_SETUP_OVERLAY_SIZE = 0x0104
# After the first menu buffers have been allocated, 18:A406 calls this
# nine-local layout/record builder.  Its flat resident destination begins with
# unrelated data (0x1BED); the shipped complete same-PC body is the closed
# 43:E3D8..E744 function.
APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_DESTINATION = 0x26E3D8
APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_SOURCE = 0x43E3D8
APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_SIZE = 0x036E
# The exact 18:A358 caller passes four words to 26:459C.  The linked target is
# application data by the late menu boundary, while the unused same-PC copy at
# 43:459C is the complete LINK #5 byte-stream renderer/parser.  It closes at
# 43:4938 and all of its absolute branches stay inside that range.  Preserve
# those exact words in a resident installer instead of reading the cleared
# segment-43 data bank at run time.
APPLICATION_MENU_TEXT_STREAM_OVERLAY_DESTINATION = 0x26459C
APPLICATION_MENU_TEXT_STREAM_OVERLAY_SOURCE = 0x43459C
APPLICATION_MENU_TEXT_STREAM_OVERLAY_SIZE = 0x039E
# The application launcher reads a 16-bit application code from its current
# record and resolves it through an 81-entry sorted registry.  The linked
# table is absent at 2A:0514, while source 47:0514 contains the exact four-word
# records.  Source 4C:E4C8 is the complete binary-search implementation for
# linked entry 2F:E4C8; it searches exactly 0x51 records and returns the
# matched flags plus far entry point to its caller.
APPLICATION_REGISTRY_OVERLAY_DESTINATION = 0x2A0514
APPLICATION_REGISTRY_OVERLAY_SOURCE = 0x470514
APPLICATION_REGISTRY_OVERLAY_SIZE = 0x0288
APPLICATION_REGISTRY_LOOKUP_OVERLAY_DESTINATION = 0x2FE4C8
APPLICATION_REGISTRY_LOOKUP_OVERLAY_SOURCE = 0x4CE4C8
APPLICATION_REGISTRY_LOOKUP_OVERLAY_SIZE = 0x0124
# Both the launch manager and the generic menu launcher load an unaligned
# little-endian 16-bit value through linked 32:AF98.  Source 4F:AF98 is the
# exact one-argument helper with a balanced epilogue at 4F:AFEC.
APPLICATION_UNALIGNED_U16_OVERLAY_DESTINATION = 0x32AF98
APPLICATION_UNALIGNED_U16_OVERLAY_SOURCE = 0x4FAF98
APPLICATION_UNALIGNED_U16_OVERLAY_SIZE = 0x0056
# Twelve UI/key dispatch sites call linked 2F:8E8E with a byte index and a
# far destination pointer.  The flat target is the middle of an unrelated
# framed routine and eventually falls through to the 2F:90C0 text draw call,
# corrupting its caller's frame.  Source 4C:8E8E..4C:8FC5 is the complete
# same-PC three-word-argument function with a balanced LINK/UNLINK/RETS body.
APPLICATION_MENU_TEXT_INPUT_OVERLAY_DESTINATION = 0x2F8E8E
APPLICATION_MENU_TEXT_INPUT_OVERLAY_SOURCE = 0x4C8E8E
APPLICATION_MENU_TEXT_INPUT_OVERLAY_SIZE = 0x0138
# The immediately adjacent linked entry 2F:8FC6 is another independent
# framed UI adapter.  In the flat linked image it instead begins with the
# tail of an unrelated routine and eventually reaches 2F:90C0 with invalid
# far text pointers.  Source 4C:8FC6..4C:90FD is the complete same-PC
# function with a balanced LINK/UNLINK/RETS boundary.
APPLICATION_MENU_UI_ADAPTER_OVERLAY_DESTINATION = 0x2F8FC6
APPLICATION_MENU_UI_ADAPTER_OVERLAY_SOURCE = 0x4C8FC6
APPLICATION_MENU_UI_ADAPTER_OVERLAY_SIZE = 0x0138
# The non-type-3/5 branch of the exact UI adapter calls linked 30:07BE as a
# framed resource-position resolver.  Flat 30:07BE begins with the tail word
# 0x0061 of an unrelated routine, so it continues through 30:09C8 using the
# adapter's frame and hands negative coordinates to the rectangle renderer.
# Source 4D:07BE..4D:08D7 is the complete same-PC function with LINK #8 and
# a balanced four-register epilogue.
APPLICATION_MENU_POSITION_OVERLAY_DESTINATION = 0x3007BE
APPLICATION_MENU_POSITION_OVERLAY_SOURCE = 0x4D07BE
APPLICATION_MENU_POSITION_OVERLAY_SIZE = 0x011A
# The adapter feeds both adjacent records returned by 30:07BE through linked
# 2F:B8A4.  Flat 2F:B8A4 starts at the interior SCALL of the real function,
# skipping LINK #6 and its coordinate-buffer setup.  Source 4C:B8A4..B9D3 is
# the complete same-PC converter with a balanced two-register epilogue.
APPLICATION_MENU_COORDINATE_OVERLAY_DESTINATION = 0x2FB8A4
APPLICATION_MENU_COORDINATE_OVERLAY_SOURCE = 0x4CB8A4
APPLICATION_MENU_COORDINATE_OVERLAY_SIZE = 0x0130
# The UI adapter's final draw call targets linked 29:6454.  Its flat entry is
# an interior signed-branch word, so execution inherits the caller's frame
# and ultimately returns to an odd 29:0045 PC.  Source 46:6454..46:670D is the
# complete same-PC renderer with LINK #0x38 and a balanced epilogue.
APPLICATION_MENU_RENDER_OVERLAY_DESTINATION = 0x296454
APPLICATION_MENU_RENDER_OVERLAY_SOURCE = 0x466454
APPLICATION_MENU_RENDER_OVERLAY_SIZE = 0x02BA
# Resource decoder continuations at 27:51BA and 30:4206/46F2 call linked
# 23:DA24 with one far-pointer argument.  Flat 23:DA24 is the middle of an
# unrelated routine and reaches 2E:4572 after pushing only four of memcpy's
# six argument words, so the caller's far-return address is consumed as a
# 32-bit length.  Source 40:DA24..40:DEA5 is the complete same-PC formatter:
# LINK #3, two saved registers, all flag branches, and balanced UNLINK/RETS.
APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_DESTINATION = 0x23DA24
APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SOURCE = 0x40DA24
APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SIZE = 0x0482
# Generic-menu resource construction reaches linked 31:7D02 from 33:4AEE,
# 33:4D3E, and 28:191A.  Flat 31:7D02 starts inside an unrelated routine and
# eventually executes an unmatched epilogue, corrupting the far return into
# F6:0001.  Source 4E:7D02..4E:7DB3 is the complete same-PC binder with
# LINK #4, six saved registers, and a balanced UNLINK/RETS.
APPLICATION_MENU_RESOURCE_BIND_OVERLAY_DESTINATION = 0x317D02
APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SOURCE = 0x4E7D02
APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SIZE = 0x00B2
# The generic menu builder calls linked 33:4AE4 with two arguments.  Flat
# 33:4AE4 begins at BCLR inside an unrelated large foreground function and
# reaches its unmatched RETS at 33:52A8.  Source 50:4AE4..50:4AFB is the
# exact tiny LINK #0 wrapper around 33:1E7A.  Embed it because source bank 50
# is mutable application RAM by the time the runtime installer executes.
APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_DESTINATION = 0x334AE4
APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SOURCE = 0x504AE4
APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SIZE = 0x0018
# After the wrapper returns, 30:0054 calls linked 31:4974 to allocate and
# attach the result record.  Flat 31:4974 begins in another function after
# its LINK and register saves, so its call to 2E:2E82 consumes a corrupted
# return.  Source 4E:4974..4E:4A31 is the complete same-PC LINK #2 function.
APPLICATION_MENU_RESULT_ATTACH_OVERLAY_DESTINATION = 0x314974
APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SOURCE = 0x4E4974
APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SIZE = 0x00BE
# The caller then enters linked 2A:AE0A to build the result list.  Flat
# 2A:AE0A is deep inside a different 0x100-byte-frame routine, while source
# 47:AE0A..47:B065 is the complete LINK #0x12 builder and balanced epilogue.
APPLICATION_MENU_RESULT_LIST_OVERLAY_DESTINATION = 0x2AAE0A
APPLICATION_MENU_RESULT_LIST_OVERLAY_SOURCE = 0x47AE0A
APPLICATION_MENU_RESULT_LIST_OVERLAY_SIZE = 0x025C
# 31:C5EE directly calls linked 25:B202 while processing the generated list.
# Flat 25:B202 is resource payload and stops at 25:B232; source
# 42:B202..42:B5D5 is the exact complete LINK #1 record processor.
APPLICATION_MENU_RESULT_PROCESS_OVERLAY_DESTINATION = 0x25B202
APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SOURCE = 0x42B202
APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SIZE = 0x03D4
# 30:017E next calls linked 20:3EDE to populate the page records.  Its flat
# destination is erased 0xFFFF up to the jump table, while source
# 3D:3EDE..3D:447D is the complete LINK #7 implementation.
APPLICATION_MENU_PAGE_POPULATE_OVERLAY_DESTINATION = 0x203EDE
APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SOURCE = 0x3D3EDE
APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SIZE = 0x05A0
# 30:01AA next calls linked 27:1E66 with the populated page and output
# records.  Flat 27:1E66 is resource payload (and reaches reserved 0xCF7C at
# 27:1E7A), while source 44:1E66..44:21C3 is the complete LINK #0x0C text
# expansion function with its balanced six-register epilogue.
APPLICATION_MENU_TEXT_EXPAND_OVERLAY_DESTINATION = 0x271E66
APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SOURCE = 0x441E66
APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SIZE = 0x035E
# The original menu object builders at linked 27:571A and 28:4FF0 both call
# 29:6C7C once per visible item.  The common child directly consumes the
# 0x42-byte page records at 1C:9748: words +0/+2/+4 are used to derive the
# menu rectangle before the object is handed to the resident drawing
# services.  All three flat linked addresses contain unrelated function
# middles, while the +0x1D application-bank copies have complete
# LINK/UNLINK/RETS boundaries.  This is the native layout layer bypassed by
# the old direct 2C:C9E8 CR/LF text probe.
APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_DESTINATION = 0x296C7C
APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SOURCE = 0x466C7C
APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SIZE = 0x02B6
APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_DESTINATION = 0x27571A
APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE = 0x44571A
APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SIZE = 0x034E
APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_DESTINATION = 0x284FF0
APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SOURCE = 0x454FF0
APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SIZE = 0x0306
# 44:0040 proves that linked 26:FBBA is a callable overlay destination, even
# though its flat bytes are resource payload.  The complete same-PC source
# function is 43:FBBA..43:FF1D with a balanced LINK/UNLINK/RETS body.
APPLICATION_RESOURCE_INDEX_OVERLAY_DESTINATION = 0x26FBBA
APPLICATION_RESOURCE_INDEX_OVERLAY_SOURCE = 0x43FBBA
APPLICATION_RESOURCE_INDEX_OVERLAY_SIZE = 0x0364
# Exact large resource decoder reached from 30:46E0 after the adjacent UI
# adapter is restored.  Segment 15 is absent mask ROM; source 32:6C56..7B73
# is the complete shipped function with a balanced eight-register epilogue.
APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_DESTINATION = 0x156C56
APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_SOURCE = 0x326C56
APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_SIZE = 0x0F1E
# The resident event sampler at 3B:F74A calls linked 2F:FA32 as a complete
# no-argument hardware-state function.  The flat linked bytes start midway
# through an unrelated framed routine, so they return a spurious zero and the
# menu converts the resulting state mismatch into event 0x8F (later 0xF7).
# Source 4C:FA32..4C:FB4F is the exact same-PC function with balanced
# LINK/UNLINK/RETS boundaries and the intended 2A76/708B state checks.
APPLICATION_MENU_POWER_STATE_OVERLAY_DESTINATION = 0x2FFA32
APPLICATION_MENU_POWER_STATE_OVERLAY_SOURCE = 0x4CFA32
APPLICATION_MENU_POWER_STATE_OVERLAY_SIZE = 0x011E
# Registry application code 0x1203 resolves to the linked generic menu entry
# 2C:C9E8.  Its exact source is the complete 49:C9E8..49:CBC8 function.  The
# menu descriptor builder and its four closed pointer/resource helpers also
# survive as same-PC +0x1D copies.  Install this dependency closure together;
# this makes page construction and entry into 31:138C execute vendor code.
APPLICATION_GENERIC_MENU_OVERLAY_DESTINATION = 0x2CC9E8
APPLICATION_GENERIC_MENU_OVERLAY_SOURCE = 0x49C9E8
APPLICATION_GENERIC_MENU_OVERLAY_SIZE = 0x01E2
# 18:21F4 first calls 2B:E3E6 to validate the optional parent/exit context.
# The complete source function is 48:E3E6..48:E5FE: it has a closed CFG and a
# balanced LINK/UNLINK/RETS boundary.  Install it with the other menu/launcher
# overlays before the first foreground lifecycle.
APPLICATION_CONTEXT_GATE_OVERLAY_DESTINATION = 0x2BE3E6
APPLICATION_CONTEXT_GATE_OVERLAY_SOURCE = 0x48E3E6
APPLICATION_CONTEXT_GATE_OVERLAY_SIZE = 0x0218
# 1D:0EEA advances/deobfuscates each loaded record window through 31:AA5C.
# Its complete call-free implementation survives at 4E:AA5C..4E:AB00 and
# conditionally XORs the requested bytes with A0:70B7 when A0:70B8 bit 0 is
# set.  Keep this exact leaf beside the launcher/context overlays.
APPLICATION_RECORD_XOR_OVERLAY_DESTINATION = 0x31AA5C
APPLICATION_RECORD_XOR_OVERLAY_SOURCE = 0x4EAA5C
APPLICATION_RECORD_XOR_OVERLAY_SIZE = 0x00A4
APPLICATION_MENU_TABLE_BUILD_OVERLAY_DESTINATION = 0x2A322A
APPLICATION_MENU_TABLE_BUILD_OVERLAY_SOURCE = 0x47322A
APPLICATION_MENU_TABLE_BUILD_OVERLAY_SIZE = 0x027C
APPLICATION_MENU_XOR_U16_OVERLAY_DESTINATION = 0x326F7C
APPLICATION_MENU_XOR_U16_OVERLAY_SOURCE = 0x4F6F7C
APPLICATION_MENU_XOR_U16_OVERLAY_SIZE = 0x006A
APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_DESTINATION = 0x32125C
APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_SOURCE = 0x4F125C
APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_SIZE = 0x0088
APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_DESTINATION = 0x30D270
APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_SOURCE = 0x4DD270
APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_SIZE = 0x00E0
APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_DESTINATION = 0x2FC342
APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_SOURCE = 0x4CC342
APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_SIZE = 0x012C
# 2C:C9E8 calls the short 33:66D8 finalization wrapper after both success and
# failure paths.  Its exact source delegates to the already installed
# 33:3C86 startup table service and returns normally.
APPLICATION_UI_FINALIZE_OVERLAY_DESTINATION = 0x3366D8
APPLICATION_UI_FINALIZE_OVERLAY_SOURCE = 0x5066D8
APPLICATION_UI_FINALIZE_OVERLAY_SIZE = 0x000A
# The recovered UI dispatcher uses three linked wrappers whose flat segment-33
# targets are unrelated function middles.  Segment 50 contains the exact
# same-PC wrappers with ordinary one-argument/no-argument ABIs.
APPLICATION_UI_PREPARE_OVERLAY_DESTINATION = 0x3365D4
APPLICATION_UI_PREPARE_OVERLAY_SOURCE = 0x5065D4
APPLICATION_UI_PREPARE_OVERLAY_SIZE = 0x000A
APPLICATION_UI_PROPERTY_OVERLAY_DESTINATION = 0x334CFE
APPLICATION_UI_PROPERTY_OVERLAY_SOURCE = 0x504CFE
APPLICATION_UI_PROPERTY_OVERLAY_SIZE = 0x0016
APPLICATION_UI_COMMIT_OVERLAY_DESTINATION = 0x3366E2
APPLICATION_UI_COMMIT_OVERLAY_SOURCE = 0x5066E2
APPLICATION_UI_COMMIT_OVERLAY_SIZE = 0x000A
# The relocated startup entry calls 31:5EA0 before it installs the registry
# and foreground objects (call sites 22:982E/9948, sourced from 3F:982E/9948).
# Flat 31:5EA0 begins in the middle of an unrelated frame and eventually
# consumes the startup caller.  Source 4E:5EA0 is the exact no-argument global
# initializer: it clears A2:2250..2268, initializes the 51:226A byte table,
# and returns through its balanced epilogue at 4E:5F56.
APPLICATION_GLOBAL_STATE_INIT_OVERLAY_DESTINATION = 0x315EA0
APPLICATION_GLOBAL_STATE_INIT_OVERLAY_SOURCE = 0x4E5EA0
APPLICATION_GLOBAL_STATE_INIT_OVERLAY_SIZE = 0x00B8
# Both children of that initializer are flat data/function middles at their
# linked segment-32 addresses.  Their same-PC segment-4F copies are complete,
# ABI-compatible routines with closed control flow and balanced returns.
APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_DESTINATION = 0x326358
APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_SOURCE = 0x4F6358
APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_SIZE = 0x006C
APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_DESTINATION = 0x322520
APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_SOURCE = 0x4F2520
APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_SIZE = 0x0082
# After the registry initializer returns, the top-level function calls
# 31:706A without arguments.  The flat destination starts at a bit-move in an
# unrelated epilogue and executes UNLINK without a matching LINK.  The unused
# +0x1D source at 4E:706A is the complete LINK #0 function, with three
# conditional 1A:DEAA calls and the paired epilogue at 4E:711A..711C.
APPLICATION_POST_REGISTRY_OVERLAY_DESTINATION = 0x31706A
APPLICATION_POST_REGISTRY_OVERLAY_SOURCE = 0x4E706A
APPLICATION_POST_REGISTRY_OVERLAY_SIZE = 0x00B4
# The following no-argument 33:4EE2 call likewise lands in the middle of a
# large flat function.  Segment 50 carries its exact, call-free state-clear
# leaf with a complete LINK/UNLINK/RETS frame.
APPLICATION_POST_REGISTRY_STATE_OVERLAY_DESTINATION = 0x334EE2
APPLICATION_POST_REGISTRY_STATE_OVERLAY_SOURCE = 0x504EE2
APPLICATION_POST_REGISTRY_STATE_OVERLAY_SIZE = 0x0016
# 33:0FD6 is the next no-argument top-level child.  Its flat entry is a
# frame-relative function middle; 50:0FD6 is the complete wrapper that binds
# the two 51:1F90/51:1E2C objects through 33:3BC6.
APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_DESTINATION = 0x330FD6
APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_SOURCE = 0x500FD6
APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_SIZE = 0x0032
# Each binding wrapper calls 33:3BC6 with one far-pointer argument.  The flat
# destination begins with POP DS0 in the middle of an unrelated large
# function, which consumes the wrapper's return frame.  The unused +0x1D copy
# at 50:3BC6 is the complete LINK/SCALL/UNLINK wrapper for 32:9B56.  Without
# this second-level overlay the top-level initializer appears to return, but
# actually unwinds directly into the missing-ROM scheduler and starts again.
APPLICATION_POST_REGISTRY_BIND_TARGET_OVERLAY_DESTINATION = 0x333BC6
APPLICATION_POST_REGISTRY_BIND_TARGET_OVERLAY_SOURCE = 0x503BC6
APPLICATION_POST_REGISTRY_BIND_TARGET_OVERLAY_SIZE = 0x0020
# The final post-registry hook at 33:6F30 is another flat mid-function entry.
# Its segment-50 source is an exact empty LINK/UNLINK/RETS hook used at seven
# sites; embed it because the source bank is mutable at install time.
APPLICATION_POST_REGISTRY_HOOK_OVERLAY_DESTINATION = 0x336F30
APPLICATION_POST_REGISTRY_HOOK_OVERLAY_SOURCE = 0x506F30
APPLICATION_POST_REGISTRY_HOOK_OVERLAY_SIZE = 0x0006
# 22:515E begins by calling 33:65C0.  Its flat target is another function
# middle; the exact segment-50 wrapper calls the adjacent complete four-bit
# clear leaf at 50:5B38.  Both source ranges must be embedded from the PRG.
APPLICATION_MAIN_PREPARE_OVERLAY_DESTINATION = 0x3365C0
APPLICATION_MAIN_PREPARE_OVERLAY_SOURCE = 0x5065C0
APPLICATION_MAIN_PREPARE_OVERLAY_SIZE = 0x000A
APPLICATION_MAIN_BIT_CLEAR_OVERLAY_DESTINATION = 0x335B38
APPLICATION_MAIN_BIT_CLEAR_OVERLAY_SOURCE = 0x505B38
APPLICATION_MAIN_BIT_CLEAR_OVERLAY_SIZE = 0x000E
# The next main-loop call at 32:C86E is a flat tail fragment which constructs
# a fake far return to 00:0000.  4F:C86E is the complete one-local lazy state
# initializer.  Its only complex child has the same complete +0x1D copy at
# 4B:DB9C, with a paired epilogue and all intra-function branches resolved.
APPLICATION_MAIN_STATE_INIT_OVERLAY_DESTINATION = 0x32C86E
APPLICATION_MAIN_STATE_INIT_OVERLAY_SOURCE = 0x4FC86E
APPLICATION_MAIN_STATE_INIT_OVERLAY_SIZE = 0x004E
APPLICATION_MAIN_STATE_BUILD_OVERLAY_DESTINATION = 0x2EDB9C
APPLICATION_MAIN_STATE_BUILD_OVERLAY_SOURCE = 0x4BDB9C
APPLICATION_MAIN_STATE_BUILD_OVERLAY_SIZE = 0x0160
# The non-null state-builder path synthesizes an indirect call frame and
# transfers through RETS to callback 2C:A03A.  The flat target is a large
# unrelated initializer which falls into 2C:A7DA; source 49:A03A is the
# complete call-free LINK #0 callback returning at 49:A220.
APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_DESTINATION = 0x2CA03A
APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SOURCE = 0x49A03A
APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SIZE = 0x01E8
# The state builder calls 31:812A with one word and consumes a returned far
# pointer.  Flat 31:812A is unrelated drawing code; 4E:812A is the complete
# one-argument pointer resolver (LINK #2 through its single UNLINK/RETS).
APPLICATION_MAIN_STATE_POINTER_OVERLAY_DESTINATION = 0x31812A
APPLICATION_MAIN_STATE_POINTER_OVERLAY_SOURCE = 0x4E812A
APPLICATION_MAIN_STATE_POINTER_OVERLAY_SIZE = 0x00B0
# The state builder's first four-byte argument child at 26:371E is flat
# image/data.  43:371E is its complete LINK #2 implementation through the
# balanced epilogue at 43:3AAC..3ABC.
APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_DESTINATION = 0x26371E
APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_SOURCE = 0x43371E
APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_SIZE = 0x03A0
# 26:371E calls 2F:4350 while building its storage bitmap.  The flat target
# belongs to another large routine and eventually returns through 26:162C.
# Source 4C:4350 is the complete call-free LINK #6 bitmap builder.
APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_DESTINATION = 0x2F4350
APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SOURCE = 0x4C4350
APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SIZE = 0x014A
# Resident operation 1B:23B8 calls 31:4974 with output, size, and auxiliary
# pointer arguments.  Flat 31:4974 is the extension word of another function;
# 4E:4974 is the complete LINK #2 same-PC table creator with both short
# allocation/pointer wrappers and a balanced epilogue.
RESIDENT_WORK_TABLE_CREATE_OVERLAY_DESTINATION = 0x314974
RESIDENT_WORK_TABLE_CREATE_OVERLAY_SOURCE = 0x4E4974
RESIDENT_WORK_TABLE_CREATE_OVERLAY_SIZE = 0x00BE
# Resident operation 1B:23B8 indexes a 14-byte descriptor at 30:0B0C for
# each operation number, then copies the three referenced strings into its
# freshly allocated work tables.  The linked destination still contains an
# unrelated function body in the flat image.  Source 4D:0B0C is the exact
# 20-record table from the update PRG (20 * 14 == 0x118 bytes); operation 0A
# contains selector 0000 and pointers 27:E132, 27:E12A, and 27:E1EC.
RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_DESTINATION = 0x300B0C
RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SOURCE = 0x4D0B0C
RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SIZE = 0x0118
# The descriptor pointers target the linked 27:E07E..27:E201 path/filter
# string pool.  Its exact bytes survive at the corresponding +0x1D0000 PRG
# source range, 44:E07E..44:E201; flat 27:* contains unrelated code/data and
# makes the terminator scan overrun each 0x100-byte work allocation.
RESIDENT_OPERATION_STRING_POOL_OVERLAY_DESTINATION = 0x27E07E
RESIDENT_OPERATION_STRING_POOL_OVERLAY_SOURCE = 0x44E07E
RESIDENT_OPERATION_STRING_POOL_OVERLAY_SIZE = 0x0184

# Exact linked closure reached by the operation-0x0A/0x0B status dialog.
# The standalone ROM-01 recovery probe proved these destination/source/size
# triples as one balanced call closure.  Keep the same records in the unified
# natural-boot builder so preprocessing cannot install the operation body but
# accidentally leave its first 31:7772 dependency as flat PRG data.
APPLICATION_OPERATION_MODAL_CLOSURE_OVERLAYS = (
    (0x2B6CE6, 0x486CE6, 0x022A),
    (0x2603BA, 0x4303BA, 0x03B8),
    (0x277E84, 0x447E84, 0x0344),
    (0x317772, 0x4E7772, 0x00B2),
    (0x2E0AF6, 0x4B0AF6, 0x018E),
    (0x15FF04, 0x32FF04, 0x00FC),
    (0x0C8622, 0x298622, 0x379C),
    (0x2F4874, 0x4C4874, 0x0148),
    (0x2CF880, 0x49F880, 0x01D8),
    (0x32F402, 0x4FF402, 0x003C),
    (0x279F0A, 0x449F0A, 0x033A),
    (0x2717AA, 0x4417AA, 0x035E),
    (0x271B08, 0x441B08, 0x035E),
    (0x17CCD0, 0x34CCD0, 0x0B90),
    (0x2D3298, 0x4A3298, 0x01C8),
    (0x1B0000, 0x380000, 0x0900),
    (0x31A204, 0x4EA204, 0x00A6),
    (0x2FDB9C, 0x4CDB9C, 0x0126),
    (0x2EF446, 0x4BF446, 0x015C),
    (0x31F1F2, 0x4EF1F2, 0x0090),
    (0x29DB0A, 0x46DB0A, 0x0292),
    (0x2F3CDE, 0x4C3CDE, 0x014A),
    (0x32BE86, 0x4FBE86, 0x0050),
    (0x23DEA6, 0x40DEA6, 0x0480),
    (0x2CE9B0, 0x49E9B0, 0x01DA),
    (0x3213E8, 0x4F13E8, 0x0004),
    # Segment 50 is mutable at this point, so the installer below embeds
    # these three tiny exact leaves instead of reading their runtime bank.
    (0x333F5E, 0x503F5E, 0x001E),
    (0x334476, 0x504476, 0x001C),
    (0x335AAC, 0x505AAC, 0x000E),
)

# Two broad application overlays use 29:* as their destinations before the
# late ROM-01 modal closure copies 29:8622..BDBE into resident 0C.  Reading
# that live source after those writes splices source-46 functions into the
# resident formatter at 0C:8CAA..8F52 and 0C:AC4E..AEEA.  Reapply the exact
# immutable source-29 bytes to the corresponding 0C subranges after the broad
# copy.  This is still guest DMCU installation code; no host ROM service is
# involved.
APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_OVERLAYS = (
    (0x0C8CAA, 0x298CAA, APPLICATION_STATE_POINTER_OVERLAY_SIZE),
    (0x0CAC4E, 0x29AC4E, LCD_RESOURCE_TRANSFER_OVERLAY_SIZE),
)
# The root desktop status painter at 31:58D0 passes 33:5EE0 to the exact
# 31:7772 -> 15:FF04 formatter chain.  The linked 50:5EE0 source contains the
# pair-lane encoded ``" %02i:%02i"`` format string, while the flat 33:5EE0
# destination is unrelated executable code.  Segment 50 is mutable by the
# late application boundary, so preserve the shipped bytes in ROM and install
# this data overlay after every broad application/code copy.
APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_DESTINATION = 0x335EE0
APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SOURCE = 0x505EE0
APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SIZE = 0x000C
# The formatter's zero/space padding fragments use the data-bus table at
# 33:2390.  Its flat code-bus bytes are executable instructions, while the
# exact linked source-50 data is ten spaces followed by sixteen ASCII zeroes.
APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_DESTINATION = 0x332390
APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SOURCE = 0x502390
APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SIZE = 0x001A
APPLICATION_MODAL_MEDIA_BROWSER_OVERLAY_DESTINATION = 0x17CCD0
APPLICATION_MODAL_MEDIA_BROWSER_OVERLAY_SOURCE = 0x34CCD0
APPLICATION_MODAL_MEDIA_BROWSER_OVERLAY_SIZE = 0x0B90
# Keep the large immutable-word installer outside the already dense 09:0000
# post-initializer and 01:0200 ROM-loader bodies.  01:5000..01:7E43 is a
# verified reserved SoC-ROM gap in the unified image.
# The ROM-01 late application loader now reaches 01:5216 after embedding the
# mutable 4F/50 file-record leaves.  Keep the independent media-browser
# installer in the next free aligned window instead of letting the two guest
# programs overlap.
APPLICATION_MODAL_MEDIA_BROWSER_INSTALLER_ADDRESS = 0x018000
APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS = 0x01B000
# The storage-context builder next calls 25:77DA.  Flat 25:77DA begins with
# unrelated indirect-control words; source 42:77DA is the complete LINK #0B
# record walker.  Restore its two closed same-PC children at the same time.
APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_DESTINATION = 0x2577DA
APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SOURCE = 0x4277DA
APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SIZE = 0x03E8
APPLICATION_MAIN_STORAGE_MASK_OVERLAY_DESTINATION = 0x30251E
APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SOURCE = 0x4D251E
APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SIZE = 0x0112
# The following 2F:7C88 call enters 30:2630.  Flat 30:2630 is an unrelated
# function middle and eventually reaches the 30:3890 multi-register epilogue
# without a matching LINK, corrupting FP/SP.  Source 4D:2630 is the complete
# LINK #0 global-service initializer through its balanced 4D:2740 RETS.
APPLICATION_MAIN_SERVICE_INIT_OVERLAY_DESTINATION = 0x302630
APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SOURCE = 0x4D2630
APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SIZE = 0x0112
APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_DESTINATION = 0x33197A
APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SOURCE = 0x50197A
APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SIZE = 0x002E
# After the lazy state initializer, 22:515E calls 2D:B54C with its ordinary
# argument frame.  The flat destination begins with a call and no LINK;
# 4A:B54C is the complete five-local dispatcher through 4A:B6F0.
APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_DESTINATION = 0x2DB54C
APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_SOURCE = 0x4AB54C
APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_SIZE = 0x01A6
# The following no-argument 32:50BA target is again a flat function middle.
# 4F:50BA is its complete lazy-configuration wrapper.  Its twelve-byte
# argument child is data at 26:D2B2 and has the complete same-PC body at
# 43:D2B2 through the balanced 43:D61E RETS.
APPLICATION_MAIN_CONFIG_OVERLAY_DESTINATION = 0x3250BA
APPLICATION_MAIN_CONFIG_OVERLAY_SOURCE = 0x4F50BA
APPLICATION_MAIN_CONFIG_OVERLAY_SIZE = 0x0072
APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_DESTINATION = 0x26D2B2
APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_SOURCE = 0x43D2B2
APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_SIZE = 0x036E
# 22:515E next calls 33:4A84 with no arguments.  The flat destination is a
# large unrelated function body, while mutable segment 50 contains the exact
# LINK #0 leaf which copies A1:386A into the current object's +6 field.
APPLICATION_MAIN_OBJECT_BIND_OVERLAY_DESTINATION = 0x334A84
APPLICATION_MAIN_OBJECT_BIND_OVERLAY_SOURCE = 0x504A84
APPLICATION_MAIN_OBJECT_BIND_OVERLAY_SIZE = 0x0018
# 32:F65A is then called as a no-argument leaf, but the flat image starts in
# the middle of a large drawing function and eventually consumes its caller's
# frame.  The exact complete wrapper is at 4F:F65A..F694; unlike the adjacent
# segment-50 leaf, this ordinary code source remains available to the loader.
APPLICATION_MAIN_CONDITIONAL_OVERLAY_DESTINATION = 0x32F65A
APPLICATION_MAIN_CONDITIONAL_OVERLAY_SOURCE = 0x4FF65A
APPLICATION_MAIN_CONDITIONAL_OVERLAY_SIZE = 0x003C
# The conditional wrapper calls flat 2C:7BA8 with six zero words.  That flat
# address is the middle of a different large function and inherits the
# wrapper's frame, which turns saved return words into a huge loop count.
# 49:7BA8 is the complete same-PC LINK #3 worker through its balanced RETS at
# 49:7D96.  Its first path calls the adjacent mutable-segment helper 50:4C7A,
# so preserve that exact bit-clear leaf in the resident extra installer too.
APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_DESTINATION = 0x2C7BA8
APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SOURCE = 0x497BA8
APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SIZE = 0x01F0
APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_DESTINATION = 0x334C7A
APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SOURCE = 0x504C7A
APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SIZE = 0x0016
# The first steady-loop service at 33:5090 is another mutable segment-50
# wrapper.  Its three direct children are also flat mid-function targets;
# their complete +0x1D implementations are self-contained through balanced
# epilogues and must be restored together before the wrapper can return.
APPLICATION_MAIN_SERVICES_OVERLAY_DESTINATION = 0x335090
APPLICATION_MAIN_SERVICES_OVERLAY_SOURCE = 0x505090
APPLICATION_MAIN_SERVICES_OVERLAY_SIZE = 0x0014
APPLICATION_MAIN_INPUT_STATE_OVERLAY_DESTINATION = 0x31DF8C
APPLICATION_MAIN_INPUT_STATE_OVERLAY_SOURCE = 0x4EDF8C
APPLICATION_MAIN_INPUT_STATE_OVERLAY_SIZE = 0x0096
APPLICATION_MAIN_STATUS_SCAN_OVERLAY_DESTINATION = 0x2F5024
APPLICATION_MAIN_STATUS_SCAN_OVERLAY_SOURCE = 0x4C5024
APPLICATION_MAIN_STATUS_SCAN_OVERLAY_SIZE = 0x0148
APPLICATION_MAIN_STATE_TICK_OVERLAY_DESTINATION = 0x301EAA
APPLICATION_MAIN_STATE_TICK_OVERLAY_SOURCE = 0x4D1EAA
APPLICATION_MAIN_STATE_TICK_OVERLAY_SIZE = 0x0114
# The two following steady-loop leaves are again complete, call-free segment-
# 50 functions: one clears the low state bit and the other returns A2:2ABA.
APPLICATION_MAIN_STATE_CLEAR_OVERLAY_DESTINATION = 0x334EF8
APPLICATION_MAIN_STATE_CLEAR_OVERLAY_SOURCE = 0x504EF8
APPLICATION_MAIN_STATE_CLEAR_OVERLAY_SIZE = 0x0016
APPLICATION_MAIN_STATUS_GET_OVERLAY_DESTINATION = 0x335D76
APPLICATION_MAIN_STATUS_GET_OVERLAY_SOURCE = 0x505D76
APPLICATION_MAIN_STATUS_GET_OVERLAY_SIZE = 0x000E
# A later branch in the same first loop calls 32:2930.  That flat address is
# string/data, while 4F:2930 is a complete one-local state synchronizer with
# one resident-ROM child and a balanced return at 4F:29B0.
APPLICATION_MAIN_STATE_SYNC_OVERLAY_DESTINATION = 0x322930
APPLICATION_MAIN_STATE_SYNC_OVERLAY_SOURCE = 0x4F2930
APPLICATION_MAIN_STATE_SYNC_OVERLAY_SIZE = 0x0082
# 32:2930's only child is a genuinely absent resident-ROM entry.  The update
# image nevertheless ships its exact +0x1D copy at 3A:B4A6: a complete LINK
# #0x2D routine through the balanced 3A:BBAA epilogue.  Install those guest
# bytes as static code at 1D:B4A6; no host-side ROM service is involved.
APPLICATION_MAIN_ROM_STATE_OVERLAY_DESTINATION = 0x1DB4A6
APPLICATION_MAIN_ROM_STATE_OVERLAY_SOURCE = 0x3AB4A6
APPLICATION_MAIN_ROM_STATE_OVERLAY_SIZE = 0x0706
# The following display/menu path reaches missing resident entry 15:D474.
# Its exact +0x1D copy is present at 32:D474, ending at the paired 32:E2BA
# epilogue.  Internal AJMPs remain same-segment after relocation.  This is
# likewise reconstructed as static internal ROM, not a writable RAM overlay.
APPLICATION_MAIN_ROM_MENU_OVERLAY_DESTINATION = 0x15D474
APPLICATION_MAIN_ROM_MENU_OVERLAY_SOURCE = 0x32D474
APPLICATION_MAIN_ROM_MENU_OVERLAY_SIZE = 0x0E4A
# The restored main loop reaches the first genuinely absent resident entry at
# 13:9444 through 2F:2A6E.  The update image carries its exact +0x1D body at
# 30:9444: a four-argument LINK #0x12 layout/compositor routine with closed
# branches and the balanced epilogue at 30:A600.  Reconstruct it as static
# internal ROM, not a late writable overlay.
APPLICATION_MAIN_ROM_COMPOSITOR_DESTINATION = 0x139444
APPLICATION_MAIN_ROM_COMPOSITOR_SOURCE = 0x309444
APPLICATION_MAIN_ROM_COMPOSITOR_SIZE = 0x11BE
# The compositor's 13:956A path calls flat 22:C370, which starts after its
# real prologue and reaches an UNLINK that tears down the compositor frame.
# Source 3F:C370 is the exact LINK #3 implementation through 3F:C854; its
# only far children are the already reconstructed segment-03 ROM entries.
APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_DESTINATION = 0x22C370
APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SOURCE = 0x3FC370
APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SIZE = 0x04E6
# The compositor's mode-two branch enters resident 07:7136.  Segment 24
# contains its exact +0x1D state/update routine and the two short resident
# predicates it calls.  All three have explicit LINK/RETS boundaries and are
# installed as immutable internal ROM bytes.
APPLICATION_MAIN_ROM_RESOURCE_STATE_DESTINATION = 0x077136
APPLICATION_MAIN_ROM_RESOURCE_STATE_SOURCE = 0x247136
APPLICATION_MAIN_ROM_RESOURCE_STATE_SIZE = 0x00F0
APPLICATION_MAIN_ROM_RESOURCE_PROBE_DESTINATION = 0x07A496
APPLICATION_MAIN_ROM_RESOURCE_PROBE_SOURCE = 0x24A496
APPLICATION_MAIN_ROM_RESOURCE_PROBE_SIZE = 0x003C
APPLICATION_MAIN_ROM_RESOURCE_TEST_DESTINATION = 0x07A5A6
APPLICATION_MAIN_ROM_RESOURCE_TEST_SOURCE = 0x24A5A6
APPLICATION_MAIN_ROM_RESOURCE_TEST_SIZE = 0x002A
# Exact execution tracing shows 21:C076 passing three far pointers to a normal
# SCALL 05:2286 and consuming its R0 result at 21:C07A.  The flat 05:2286
# window is occupied by the clean-room late-overlay loader, but the update
# image contains the complete +0x1D implementation at 22:2286: LINK #0x1D,
# three saved registers, all three caller far pointers at FP+6..+10, and a
# balanced epilogue ending immediately before the next LINK at 22:2C90.
# Restore it only after the loader PC has passed 05:2C90, so the guest can
# safely replace already-executed installer instructions through its ordinary
# data bus without any QEMU-side call interception.
APPLICATION_MAIN_RECORD_LOAD_OVERLAY_DESTINATION = 0x052286
APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SOURCE = 0x222286
APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SIZE = 0x0A0A
# The two resource predicates enter their next resident layers at 05:89EC
# and 06:1138.  Exact +0x1D implementations are present at 22:89EC and
# 23:1138, including their full saved-register sets and balanced epilogues.
APPLICATION_MAIN_ROM_RESOURCE_SCAN_DESTINATION = 0x0589EC
APPLICATION_MAIN_ROM_RESOURCE_SCAN_SOURCE = 0x2289EC
APPLICATION_MAIN_ROM_RESOURCE_SCAN_SIZE = 0x078A
APPLICATION_MAIN_ROM_RESOURCE_CHECK_DESTINATION = 0x061138
APPLICATION_MAIN_ROM_RESOURCE_CHECK_SOURCE = 0x231138
APPLICATION_MAIN_ROM_RESOURCE_CHECK_SIZE = 0x044C
# Resident resource decoding then uses three adjacent segment-07 conversion
# leaves.  Their +0x1D copies at 24:367E, 24:3734 and 24:37A0 are bounded by
# explicit saved-register returns; the middle routine is the hex parser hit
# by the current strict trace.
APPLICATION_MAIN_ROM_RESOURCE_XOR_DESTINATION = 0x07367E
APPLICATION_MAIN_ROM_RESOURCE_XOR_SOURCE = 0x24367E
APPLICATION_MAIN_ROM_RESOURCE_XOR_SIZE = 0x0056
APPLICATION_MAIN_ROM_RESOURCE_HEX_DESTINATION = 0x073734
APPLICATION_MAIN_ROM_RESOURCE_HEX_SOURCE = 0x243734
APPLICATION_MAIN_ROM_RESOURCE_HEX_SIZE = 0x006C
APPLICATION_MAIN_ROM_RESOURCE_FORMAT_DESTINATION = 0x0737A0
APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SOURCE = 0x2437A0
APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SIZE = 0x0070
# After the mode-two compositor completes, 2F:2A8C calls resident 12:5434.
# Its exact +0x1D body at 2F:5434 is the complete LINK #0E resource/layout
# builder through the six-register epilogue at 2F:68A0.
APPLICATION_MAIN_ROM_LAYOUT_BUILD_DESTINATION = 0x125434
APPLICATION_MAIN_ROM_LAYOUT_BUILD_SOURCE = 0x2F5434
APPLICATION_MAIN_ROM_LAYOUT_BUILD_SIZE = 0x146E
# The same branch immediately continues through a two-local action at
# 32:342E and a segment-50 result wrapper at 33:43CE.  Restore both complete
# shipped bodies so tracing can distinguish their nested dependencies.
APPLICATION_MAIN_ACTION_OVERLAY_DESTINATION = 0x32342E
APPLICATION_MAIN_ACTION_OVERLAY_SOURCE = 0x4F342E
APPLICATION_MAIN_ACTION_OVERLAY_SIZE = 0x007E
# 4F:342E immediately calls 33:4AB4 as a framed zero-argument state query.
# The flat 33:4AB4 bytes are the middle of another routine and fall through
# into the large 32:BB60 state machine.  Mutable 50:4AB4 contains the complete
# LINK #1 wrapper, its 31:9E18 call, and balanced RETS.
APPLICATION_MAIN_ACTION_QUERY_OVERLAY_DESTINATION = 0x334AB4
APPLICATION_MAIN_ACTION_QUERY_OVERLAY_SOURCE = 0x504AB4
APPLICATION_MAIN_ACTION_QUERY_OVERLAY_SIZE = 0x0018
# The nonzero action arm later calls 21:CEF4 with an object far pointer.
# Flat 21:CEF4 omits the frame and register-save prefix but still executes an
# eight-register epilogue, corrupting the far return to 51:0001.  Source
# 3E:CEF4 is the complete LINK #8 renderer through 3E:D428 RETS.
APPLICATION_MAIN_ACTION_RENDER_OVERLAY_DESTINATION = 0x21CEF4
APPLICATION_MAIN_ACTION_RENDER_OVERLAY_SOURCE = 0x3ECEF4
APPLICATION_MAIN_ACTION_RENDER_OVERLAY_SIZE = 0x0536
# The source renderer's only call to the input helper still names the helper's
# +0x1D load-image segment 2E.  The helper body hard-codes its synthetic far
# callback return to linked segment 11, proving this external call must follow
# the same relocation as the eighteen calls already patched inside 11:1752.
APPLICATION_MAIN_ACTION_RENDER_INPUT_CALL = 0x21D3FE
APPLICATION_MAIN_ACTION_RENDER_INPUT_CALL_SOURCE = 0x3ED3FE
# Resident 18:CFA8 calls 32:FA06 with one far-pointer argument and consumes
# its boolean result.  Flat 32:FA06 is an unframed branch into the unrelated
# 32:F0EE function, which consequently treats the resident caller's locals as
# a large UI object and reaches a garbage indirect callback.  Source 4F:FA06
# is the exact same-PC LINK #0x8E wrapper with a balanced return at 4F:FA3E.
APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_DESTINATION = 0x32FA06
APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SOURCE = 0x4FFA06
APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SIZE = 0x003A
# The successful context builder stores 28:DDA6 in object field +0x22, and
# 11:1752 invokes that field through its synthetic far-call frame.  Flat
# 28:DDA6 is a large-function middle with no LINK and eventually executes
# heap/data at 51:0Fxx.  Source 45:DDA6 is the complete LINK #0x8F callback
# through its single balanced epilogue at 45:E084..E086.
APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_DESTINATION = 0x28DDA6
APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SOURCE = 0x45DDA6
APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SIZE = 0x02E2
# Two renderer children have the same flat-mid-function signature.  Their
# same-PC segment-4F copies are short, closed framed drawing helpers.
APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_DESTINATION = 0x32B922
APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_SOURCE = 0x4FB922
APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_SIZE = 0x0052
APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_DESTINATION = 0x32CF38
APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_SOURCE = 0x4FCF38
APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_SIZE = 0x0046
# The layout callback also reaches both children of the line helper.  Their
# flat segment-32 targets start after their real prologues and keep the
# callback's inherited frame alive while a nested event pass begins.  The
# same-PC segment-4F bodies are complete framed helpers with closed returns.
APPLICATION_MAIN_ACTION_RENDER_PACK_OVERLAY_DESTINATION = 0x32F4F2
APPLICATION_MAIN_ACTION_RENDER_PACK_OVERLAY_SOURCE = 0x4FF4F2
APPLICATION_MAIN_ACTION_RENDER_PACK_OVERLAY_SIZE = 0x003C
APPLICATION_MAIN_ACTION_RENDER_EDGES_OVERLAY_DESTINATION = 0x3247A6
APPLICATION_MAIN_ACTION_RENDER_EDGES_OVERLAY_SOURCE = 0x4F47A6
APPLICATION_MAIN_ACTION_RENDER_EDGES_OVERLAY_SIZE = 0x0076
# Resident 18:A510 uses these adjacent numeric conversion helpers twelve and
# four times respectively.  Flat segment 32 contains unrelated large-function
# middles at both PCs; 4F:BCA6 and 4F:BCF6 are two exact, contiguous 0x50-byte
# framed routines, each ending in its own balanced RETS.
APPLICATION_REGION_CONVERT_OVERLAY_DESTINATION = 0x32BCA6
APPLICATION_REGION_CONVERT_OVERLAY_SOURCE = 0x4FBCA6
APPLICATION_REGION_CONVERT_OVERLAY_SIZE = 0x0050
APPLICATION_REGION_SCALE_OVERLAY_DESTINATION = 0x32BCF6
APPLICATION_REGION_SCALE_OVERLAY_SOURCE = 0x4FBCF6
APPLICATION_REGION_SCALE_OVERLAY_SIZE = 0x0050
# Three arithmetic/coordinate helpers are the remaining repeated children of
# resident 18:A510.  Their flat linked PCs all enter unrelated function
# middles.  The +0x1D source-bank bodies have complete prologues, closed local
# branches, and one balanced epilogue each.
APPLICATION_REGION_ARITH_OVERLAY_DESTINATION = 0x2F45E4
APPLICATION_REGION_ARITH_OVERLAY_SOURCE = 0x4C45E4
APPLICATION_REGION_ARITH_OVERLAY_SIZE = 0x0126
APPLICATION_REGION_NORMALIZE_OVERLAY_DESTINATION = 0x2F52B4
APPLICATION_REGION_NORMALIZE_OVERLAY_SOURCE = 0x4C52B4
APPLICATION_REGION_NORMALIZE_OVERLAY_SIZE = 0x0144
APPLICATION_REGION_DIGIT_OVERLAY_DESTINATION = 0x2DEAEE
APPLICATION_REGION_DIGIT_OVERLAY_SOURCE = 0x4AEAEE
APPLICATION_REGION_DIGIT_OVERLAY_SIZE = 0x0198
# The region-digit path passes its temporary value to 32:52F2.  The flat
# destination is a suffix of an unrelated large function and eventually
# re-enters the region renderer, consuming one stack frame per pass.  The
# matching application-bank image at 4F:52F2 is a complete LINK #4 wrapper;
# its register-ABI child at 4F:60D0 is also a closed, frame-less helper.
APPLICATION_REGION_VALUE_OVERLAY_DESTINATION = 0x3252F2
APPLICATION_REGION_VALUE_OVERLAY_SOURCE = 0x4F52F2
APPLICATION_REGION_VALUE_OVERLAY_SIZE = 0x0070
APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_DESTINATION = 0x3260D0
APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SOURCE = 0x4F60D0
APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SIZE = 0x006A
# 4C:45E4 tests temporary wide values through 33:5108.  Flat 33:5108 is a
# renderer dispatcher that recursively re-enters 18:A510; mutable 50:5108 is
# the exact seven-instruction, call-free nonzero/sign predicate.  Embed its
# shipped words before segment 50 becomes application RAM.
APPLICATION_REGION_NONZERO_OVERLAY_DESTINATION = 0x335108
APPLICATION_REGION_NONZERO_OVERLAY_SOURCE = 0x505108
APPLICATION_REGION_NONZERO_OVERLAY_SIZE = 0x0012
# Resident 17:9244 calls 29:C3C0 after preparing font geometry.  The flat
# destination is the middle of an unrolled arithmetic routine and inherits a
# caller local as its loop counter.  Source 46:C3C0 is the complete LINK #0x26
# table builder through the balanced 46:C656/46:C658 epilogue.
APPLICATION_FONT_TABLE_OVERLAY_DESTINATION = 0x29C3C0
APPLICATION_FONT_TABLE_OVERLAY_SOURCE = 0x46C3C0
APPLICATION_FONT_TABLE_OVERLAY_SIZE = 0x029A
# The complete renderer then reaches genuinely absent resident entry 1D:831E.
# Its exact +0x1D image at 3A:831E is a closed LINK #8 function ending at
# 3A:8A38; it has no far calls back into segment 3A, so relocation is direct.
APPLICATION_MAIN_ROM_RENDER_DESTINATION = 0x1D831E
APPLICATION_MAIN_ROM_RENDER_SOURCE = 0x3A831E
APPLICATION_MAIN_ROM_RENDER_SIZE = 0x071C
# 11:1752 has a large +0x1D clone at 2E:1752.  Eighteen compiler-created
# SCALLs target the clone's own 2E:2B6E local tail and therefore require their
# segment byte to follow the relocation back to resident segment 11.
APPLICATION_MAIN_ROM_INPUT_DESTINATION = 0x111752
APPLICATION_MAIN_ROM_INPUT_SOURCE = 0x2E1752
APPLICATION_MAIN_ROM_INPUT_SIZE = 0x1738
APPLICATION_MAIN_ROM_INPUT_LOCAL_SOURCE = 0x2E2B6E
APPLICATION_MAIN_ROM_INPUT_LOCAL_DESTINATION = 0x112B6E
# The compare/mode overlay calls genuinely absent resident entry 1A:DEAA.
# Its +0x1D image at 37:DEAA is a complete LINK #0x3A implementation through
# 37:E7BC.  All far calls already target external linked/resident addresses,
# and its computed jump table explicitly names destination segment 1A, proving
# the shipped bytes are a load image for this resident slot.
APPLICATION_COMPARE_ROM_DESTINATION = 0x1ADEAA
APPLICATION_COMPARE_ROM_SOURCE = 0x37DEAA
APPLICATION_COMPARE_ROM_SIZE = 0x0914
APPLICATION_MAIN_RESULT_OVERLAY_DESTINATION = 0x3343CE
APPLICATION_MAIN_RESULT_OVERLAY_SOURCE = 0x5043CE
APPLICATION_MAIN_RESULT_OVERLAY_SIZE = 0x001C
# The result wrapper's first child at 28:94C2 is also a flat mid-function
# entry.  Source 45:94C2 is its complete 49-local scan/build routine through
# the balanced epilogue at 45:97B4.  Falling through the flat destination
# consumes the main loop's far return and restarts one-shot initialization.
APPLICATION_MAIN_RESULT_SCAN_OVERLAY_DESTINATION = 0x2894C2
APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SOURCE = 0x4594C2
APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SIZE = 0x02F4
# The result scanner is the native upstream caller which constructs the
# descriptor eventually passed to 2E:D34A.  Restore its direct call closure,
# including the first mandatory 1E:6444 object-allocation path.  These ranges
# are independently framed same-PC functions with closed local control flow.
APPLICATION_RESULT_LIST_CREATE_OVERLAY_DESTINATION = 0x319E18
APPLICATION_RESULT_LIST_CREATE_OVERLAY_SOURCE = 0x4E9E18
APPLICATION_RESULT_LIST_CREATE_OVERLAY_SIZE = 0x00A8
APPLICATION_RESULT_FLAG_UPDATE_OVERLAY_DESTINATION = 0x2BD756
APPLICATION_RESULT_FLAG_UPDATE_OVERLAY_SOURCE = 0x48D756
APPLICATION_RESULT_FLAG_UPDATE_OVERLAY_SIZE = 0x0218
APPLICATION_RESULT_TABLE_INIT_OVERLAY_DESTINATION = 0x318F74
APPLICATION_RESULT_TABLE_INIT_OVERLAY_SOURCE = 0x4E8F74
APPLICATION_RESULT_TABLE_INIT_OVERLAY_SIZE = 0x00AC
APPLICATION_RESULT_TABLE_RELEASE_OVERLAY_DESTINATION = 0x32446C
APPLICATION_RESULT_TABLE_RELEASE_OVERLAY_SOURCE = 0x4F446C
APPLICATION_RESULT_TABLE_RELEASE_OVERLAY_SIZE = 0x0076
APPLICATION_RESULT_FLAG_READ_OVERLAY_DESTINATION = 0x2C9C66
APPLICATION_RESULT_FLAG_READ_OVERLAY_SOURCE = 0x499C66
APPLICATION_RESULT_FLAG_READ_OVERLAY_SIZE = 0x01EA
APPLICATION_RESULT_RECORD_MATCH_OVERLAY_DESTINATION = 0x2A80AA
APPLICATION_RESULT_RECORD_MATCH_OVERLAY_SOURCE = 0x4780AA
APPLICATION_RESULT_RECORD_MATCH_OVERLAY_SIZE = 0x026C
APPLICATION_RESULT_FILE_RELEASE_OVERLAY_DESTINATION = 0x32AEEC
APPLICATION_RESULT_FILE_RELEASE_OVERLAY_SOURCE = 0x4FAEEC
APPLICATION_RESULT_FILE_RELEASE_OVERLAY_SIZE = 0x0056
APPLICATION_RESULT_CONTEXT_RELEASE_OVERLAY_DESTINATION = 0x2479F2
APPLICATION_RESULT_CONTEXT_RELEASE_OVERLAY_SOURCE = 0x4179F2
APPLICATION_RESULT_CONTEXT_RELEASE_OVERLAY_SIZE = 0x0442
APPLICATION_RESULT_OBJECT_RELEASE_OVERLAY_DESTINATION = 0x32A9D2
APPLICATION_RESULT_OBJECT_RELEASE_OVERLAY_SOURCE = 0x4FA9D2
APPLICATION_RESULT_OBJECT_RELEASE_OVERLAY_SIZE = 0x0054

# Mandatory children of resident 1E:6444's mode-one allocation path.
APPLICATION_RESULT_OBJECT_INIT_OVERLAY_DESTINATION = 0x268296
APPLICATION_RESULT_OBJECT_INIT_OVERLAY_SOURCE = 0x438296
APPLICATION_RESULT_OBJECT_INIT_OVERLAY_SIZE = 0x0388
# The initializer's computed dispatcher reads 20 near targets from its data
# view at 26:8346 before executing RET.  Those words are embedded in the exact
# source function but resource provisioning overwrites the writable data
# backing.  Preserve the table as Harvard data while keeping the surrounding
# instruction view on the code overlay above.
APPLICATION_RESULT_OBJECT_INIT_JUMP_TABLE_DATA_OVERLAY_DESTINATION = 0x268346
APPLICATION_RESULT_OBJECT_INIT_JUMP_TABLE_DATA_OVERLAY_SOURCE = 0x438346
APPLICATION_RESULT_OBJECT_INIT_JUMP_TABLE_DATA_OVERLAY_SIZE = 0x0028
APPLICATION_RESULT_OBJECT_HEADER_OVERLAY_DESTINATION = 0x30826A
APPLICATION_RESULT_OBJECT_HEADER_OVERLAY_SOURCE = 0x4D826A
APPLICATION_RESULT_OBJECT_HEADER_OVERLAY_SIZE = 0x00FA
APPLICATION_RESULT_OBJECT_HEADER_COPY_OVERLAY_DESTINATION = 0x32D016
APPLICATION_RESULT_OBJECT_HEADER_COPY_OVERLAY_SOURCE = 0x4FD016
APPLICATION_RESULT_OBJECT_HEADER_COPY_OVERLAY_SIZE = 0x004A
APPLICATION_RESULT_OBJECT_FINALIZE_OVERLAY_DESTINATION = 0x32BED6
APPLICATION_RESULT_OBJECT_FINALIZE_OVERLAY_SOURCE = 0x4FBED6
APPLICATION_RESULT_OBJECT_FINALIZE_OVERLAY_SIZE = 0x0050
APPLICATION_RESULT_RECORD_TABLE_OVERLAY_DESTINATION = 0x27AF22
APPLICATION_RESULT_RECORD_TABLE_OVERLAY_SOURCE = 0x44AF22
APPLICATION_RESULT_RECORD_TABLE_OVERLAY_SIZE = 0x0336
APPLICATION_RESULT_TEXT_LENGTH_OVERLAY_DESTINATION = 0x321722
APPLICATION_RESULT_TEXT_LENGTH_OVERLAY_SOURCE = 0x4F1722
APPLICATION_RESULT_TEXT_LENGTH_OVERLAY_SIZE = 0x0086
# 30:E9D0 calls 2D:71C4 while composing each result/menu record.  Flat
# 2D:71C4 begins halfway through an unrelated routine and eventually invokes
# the item renderer with parent-frame bytes as its colour/mode arguments.
# Source 4A:71C4 is the complete same-PC LINK #3 implementation through its
# balanced 4A:737C RETS; 4A:737E starts the next framed function.
APPLICATION_RESULT_ITEM_STATE_OVERLAY_DESTINATION = 0x2D71C4
APPLICATION_RESULT_ITEM_STATE_OVERLAY_SOURCE = 0x4A71C4
APPLICATION_RESULT_ITEM_STATE_OVERLAY_SIZE = 0x01BA
APPLICATION_RESULT_ITEM_RENDER_OVERLAY_DESTINATION = 0x323B74
APPLICATION_RESULT_ITEM_RENDER_OVERLAY_SOURCE = 0x4F3B74
APPLICATION_RESULT_ITEM_RENDER_OVERLAY_SIZE = 0x007C
APPLICATION_RESULT_TEXT_RENDER_OVERLAY_DESTINATION = 0x25AA58
APPLICATION_RESULT_TEXT_RENDER_OVERLAY_SOURCE = 0x42AA58
APPLICATION_RESULT_TEXT_RENDER_OVERLAY_SIZE = 0x03D6
APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_DESTINATION = 0x327B42
APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_SOURCE = 0x4F7B42
APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_SIZE = 0x0066
# Resident file open 1F:1F1A calls linked 2F:37B0 before it can inspect the
# storage catalogue.  The flat destination is the middle of an unrelated UI
# routine and immediately jumps to that routine's shared epilogue.  Source
# 4C:37B0 is the complete LINK #1 path/object resolver through 4C:38FA.  Its
# first child has the same signature: flat 31:B83C is unrelated code, while
# 4E:B83C is the complete call-free LINK #2 root-object lookup helper.
APPLICATION_FILE_PATH_RESOLVE_OVERLAY_DESTINATION = 0x2F37B0
APPLICATION_FILE_PATH_RESOLVE_OVERLAY_SOURCE = 0x4C37B0
APPLICATION_FILE_PATH_RESOLVE_OVERLAY_SIZE = 0x014C
APPLICATION_FILE_ROOT_LOOKUP_OVERLAY_DESTINATION = 0x31B83C
APPLICATION_FILE_ROOT_LOOKUP_OVERLAY_SOURCE = 0x4EB83C
APPLICATION_FILE_ROOT_LOOKUP_OVERLAY_SIZE = 0x00A0
# Every resident-file-open error arm releases the partially constructed object
# through 32:5592.  The flat destination is an unrelated formatter fragment;
# 4F:5592 is the complete LINK/RETS release body which clears the 0x44-byte
# object state and restores its sentinel byte.
APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_DESTINATION = 0x325592
APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_SOURCE = 0x4F5592
APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_SIZE = 0x0070

# Source segment 50 is mutable application RAM at this stage, so preserve the
# exact short wrappers in the resident installer.
APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_DESTINATION = 0x3351E0
APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_SOURCE = 0x5051E0
APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_SIZE = 0x0012
APPLICATION_RESULT_TABLE_POINTER_OVERLAY_DESTINATION = 0x3351F2
APPLICATION_RESULT_TABLE_POINTER_OVERLAY_SOURCE = 0x5051F2
APPLICATION_RESULT_TABLE_POINTER_OVERLAY_SIZE = 0x0012
# This four-byte tail thunk is called directly by resident 1E:657E.  Its
# writable data-bus backing is later reused by the application, so QEMU must
# keep the CPU code-bus view pinned to the exact source-50 SJMP words.
APPLICATION_RESULT_MEMORY_FILL_OVERLAY_DESTINATION = 0x33269E
APPLICATION_RESULT_MEMORY_FILL_OVERLAY_SOURCE = 0x50269E
APPLICATION_RESULT_MEMORY_FILL_OVERLAY_SIZE = 0x0004
APPLICATION_RESULT_STRING_COPY_OVERLAY_DESTINATION = 0x33315A
APPLICATION_RESULT_STRING_COPY_OVERLAY_SOURCE = 0x50315A
APPLICATION_RESULT_STRING_COPY_OVERLAY_SIZE = 0x0024
APPLICATION_RESULT_RECORD_COMMIT_OVERLAY_DESTINATION = 0x3340C6
APPLICATION_RESULT_RECORD_COMMIT_OVERLAY_SOURCE = 0x5040C6
APPLICATION_RESULT_RECORD_COMMIT_OVERLAY_SIZE = 0x001E
APPLICATION_RESULT_OBJECT_CLOSE_OVERLAY_DESTINATION = 0x3304C0
APPLICATION_RESULT_OBJECT_CLOSE_OVERLAY_SOURCE = 0x5004C0
APPLICATION_RESULT_OBJECT_CLOSE_OVERLAY_SIZE = 0x0036
# Linked 33:1BBA is not an independent function slot: the flat 33:18xx UI
# routine tail-jumps to its shared epilogue at 33:1BBC, and the next framed
# routine starts at 33:1BC8.  Installing source 50:1BBA in place therefore
# corrupts both live functions and makes their frame bytes look like colour
# indices.  Keep the exact wrapper at the same PC in collision-free bank 5F
# and retarget the evidenced callers below.
APPLICATION_RESULT_MODE_PAIR_LINKED_DESTINATION = 0x331BBA
APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION = 0x5F1BBA
APPLICATION_RESULT_MODE_PAIR_OVERLAY_SOURCE = 0x501BBA
APPLICATION_RESULT_MODE_PAIR_OVERLAY_SIZE = 0x002C
APPLICATION_FOREGROUND_STATE50_MODE_PAIR_CALL = 0x0C007C
APPLICATION_FOREGROUND_STATE50_MODE_PAIR_CALL_SOURCE = 0x29007C
APPLICATION_STORAGE_SCAN_MODE_PAIR_CALL = 0x272904
APPLICATION_STORAGE_SCAN_MODE_PAIR_CALL_SOURCE = 0x442904
APPLICATION_RESULT_ITEM_RENDER_MODE_PAIR_CALL = 0x323BA4
APPLICATION_RESULT_ITEM_RENDER_MODE_PAIR_CALL_SOURCE = 0x4F3BA4
APPLICATION_RESULT_CURSOR_ADVANCE_OVERLAY_DESTINATION = 0x3337C6
APPLICATION_RESULT_CURSOR_ADVANCE_OVERLAY_SOURCE = 0x5037C6
APPLICATION_RESULT_CURSOR_ADVANCE_OVERLAY_SIZE = 0x0022

APPLICATION_RESULT_SCAN_COPY_OVERLAYS = (
    (APPLICATION_RESULT_HEADER_PARSE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_HEADER_PARSE_OVERLAY_SOURCE,
     APPLICATION_RESULT_HEADER_PARSE_OVERLAY_SIZE),
    (APPLICATION_RESULT_STATE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_STATE_OVERLAY_SOURCE,
     APPLICATION_RESULT_STATE_OVERLAY_SIZE),
    (APPLICATION_RESULT_LIST_CREATE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_LIST_CREATE_OVERLAY_SOURCE,
     APPLICATION_RESULT_LIST_CREATE_OVERLAY_SIZE),
    (APPLICATION_RESULT_FLAG_UPDATE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_FLAG_UPDATE_OVERLAY_SOURCE,
     APPLICATION_RESULT_FLAG_UPDATE_OVERLAY_SIZE),
    (APPLICATION_RESULT_TABLE_INIT_OVERLAY_DESTINATION,
     APPLICATION_RESULT_TABLE_INIT_OVERLAY_SOURCE,
     APPLICATION_RESULT_TABLE_INIT_OVERLAY_SIZE),
    (APPLICATION_RESULT_TABLE_RELEASE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_TABLE_RELEASE_OVERLAY_SOURCE,
     APPLICATION_RESULT_TABLE_RELEASE_OVERLAY_SIZE),
    (APPLICATION_RESULT_FLAG_READ_OVERLAY_DESTINATION,
     APPLICATION_RESULT_FLAG_READ_OVERLAY_SOURCE,
     APPLICATION_RESULT_FLAG_READ_OVERLAY_SIZE),
    (APPLICATION_RESULT_RECORD_MATCH_OVERLAY_DESTINATION,
     APPLICATION_RESULT_RECORD_MATCH_OVERLAY_SOURCE,
     APPLICATION_RESULT_RECORD_MATCH_OVERLAY_SIZE),
    (APPLICATION_RESULT_FILE_RELEASE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_FILE_RELEASE_OVERLAY_SOURCE,
     APPLICATION_RESULT_FILE_RELEASE_OVERLAY_SIZE),
    (APPLICATION_RESULT_CONTEXT_RELEASE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_CONTEXT_RELEASE_OVERLAY_SOURCE,
     APPLICATION_RESULT_CONTEXT_RELEASE_OVERLAY_SIZE),
    (APPLICATION_RESULT_OBJECT_RELEASE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_OBJECT_RELEASE_OVERLAY_SOURCE,
     APPLICATION_RESULT_OBJECT_RELEASE_OVERLAY_SIZE),
    (APPLICATION_RESULT_OBJECT_INIT_OVERLAY_DESTINATION,
     APPLICATION_RESULT_OBJECT_INIT_OVERLAY_SOURCE,
     APPLICATION_RESULT_OBJECT_INIT_OVERLAY_SIZE),
    (APPLICATION_RESULT_OBJECT_HEADER_OVERLAY_DESTINATION,
     APPLICATION_RESULT_OBJECT_HEADER_OVERLAY_SOURCE,
     APPLICATION_RESULT_OBJECT_HEADER_OVERLAY_SIZE),
    (APPLICATION_RESULT_OBJECT_HEADER_COPY_OVERLAY_DESTINATION,
     APPLICATION_RESULT_OBJECT_HEADER_COPY_OVERLAY_SOURCE,
     APPLICATION_RESULT_OBJECT_HEADER_COPY_OVERLAY_SIZE),
    (APPLICATION_RESULT_OBJECT_FINALIZE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_OBJECT_FINALIZE_OVERLAY_SOURCE,
     APPLICATION_RESULT_OBJECT_FINALIZE_OVERLAY_SIZE),
    (APPLICATION_RESULT_RECORD_TABLE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_RECORD_TABLE_OVERLAY_SOURCE,
     APPLICATION_RESULT_RECORD_TABLE_OVERLAY_SIZE),
    (APPLICATION_RESULT_TEXT_LENGTH_OVERLAY_DESTINATION,
     APPLICATION_RESULT_TEXT_LENGTH_OVERLAY_SOURCE,
     APPLICATION_RESULT_TEXT_LENGTH_OVERLAY_SIZE),
    (APPLICATION_RESULT_ITEM_STATE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_ITEM_STATE_OVERLAY_SOURCE,
     APPLICATION_RESULT_ITEM_STATE_OVERLAY_SIZE),
    (APPLICATION_RESULT_ITEM_RENDER_OVERLAY_DESTINATION,
     APPLICATION_RESULT_ITEM_RENDER_OVERLAY_SOURCE,
     APPLICATION_RESULT_ITEM_RENDER_OVERLAY_SIZE),
    (APPLICATION_RESULT_TEXT_RENDER_OVERLAY_DESTINATION,
     APPLICATION_RESULT_TEXT_RENDER_OVERLAY_SOURCE,
     APPLICATION_RESULT_TEXT_RENDER_OVERLAY_SIZE),
    (APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_DESTINATION,
     APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_SOURCE,
     APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_SIZE),
    (APPLICATION_FILE_PATH_RESOLVE_OVERLAY_DESTINATION,
     APPLICATION_FILE_PATH_RESOLVE_OVERLAY_SOURCE,
     APPLICATION_FILE_PATH_RESOLVE_OVERLAY_SIZE),
    (APPLICATION_FILE_ROOT_LOOKUP_OVERLAY_DESTINATION,
     APPLICATION_FILE_ROOT_LOOKUP_OVERLAY_SOURCE,
     APPLICATION_FILE_ROOT_LOOKUP_OVERLAY_SIZE),
    (APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_DESTINATION,
     APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_SOURCE,
     APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_SIZE),
)
APPLICATION_RESULT_SCAN_EMBEDDED_OVERLAYS = (
    (APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_DESTINATION,
     APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_SOURCE,
     APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_SIZE),
    (APPLICATION_RESULT_TABLE_POINTER_OVERLAY_DESTINATION,
     APPLICATION_RESULT_TABLE_POINTER_OVERLAY_SOURCE,
     APPLICATION_RESULT_TABLE_POINTER_OVERLAY_SIZE),
    (APPLICATION_RESULT_MEMORY_FILL_OVERLAY_DESTINATION,
     APPLICATION_RESULT_MEMORY_FILL_OVERLAY_SOURCE,
     APPLICATION_RESULT_MEMORY_FILL_OVERLAY_SIZE),
    (APPLICATION_RESULT_STRING_COPY_OVERLAY_DESTINATION,
     APPLICATION_RESULT_STRING_COPY_OVERLAY_SOURCE,
     APPLICATION_RESULT_STRING_COPY_OVERLAY_SIZE),
    (APPLICATION_RESULT_RECORD_COMMIT_OVERLAY_DESTINATION,
     APPLICATION_RESULT_RECORD_COMMIT_OVERLAY_SOURCE,
     APPLICATION_RESULT_RECORD_COMMIT_OVERLAY_SIZE),
    (APPLICATION_RESULT_OBJECT_CLOSE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_OBJECT_CLOSE_OVERLAY_SOURCE,
     APPLICATION_RESULT_OBJECT_CLOSE_OVERLAY_SIZE),
    (APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION,
     APPLICATION_RESULT_MODE_PAIR_OVERLAY_SOURCE,
     APPLICATION_RESULT_MODE_PAIR_OVERLAY_SIZE),
    (APPLICATION_RESULT_CURSOR_ADVANCE_OVERLAY_DESTINATION,
     APPLICATION_RESULT_CURSOR_ADVANCE_OVERLAY_SOURCE,
     APPLICATION_RESULT_CURSOR_ADVANCE_OVERLAY_SIZE),
)

# These are true mask-ROM entries below segment 20, not application overlays.
RESIDENT_RESULT_OBJECT_ALLOC_ADDRESS = 0x1E6444
RESIDENT_RESULT_OBJECT_ALLOC_SOURCE = 0x3B6444
RESIDENT_RESULT_OBJECT_ALLOC_SIZE = 0x0690
RESIDENT_RESULT_RECORD_BUILD_ADDRESS = 0x1EC4AC
RESIDENT_RESULT_RECORD_BUILD_SOURCE = 0x3BC4AC
RESIDENT_RESULT_RECORD_BUILD_SIZE = 0x0658
RESIDENT_RESULT_RECORD_COMPARE_ADDRESS = 0x1FDD42
RESIDENT_RESULT_RECORD_COMPARE_SOURCE = 0x3CDD42
RESIDENT_RESULT_RECORD_COMPARE_SIZE = 0x05CC
RESIDENT_RESULT_TYPE_QUERY_ADDRESS = 0x1EA4CE
RESIDENT_RESULT_TYPE_QUERY_SOURCE = 0x3BA4CE
RESIDENT_RESULT_TYPE_QUERY_SIZE = 0x0664
# Both foreground paths at 2B:6B58/7412 pass the selected record's +0x50
# word to resident 1E:AB32 and consume its byte result as 0, 1, 2+, with an
# explicit status-4 arm.  The result-type query above ends exactly at AB32;
# the shipped +0x1D image continues there with a new, independently framed
# LINK #0x18 routine.  It has the matching one-word input at [FP+6], returns
# the observed 1/4/5 status family in R0/RB1, and closes at 3B:B194.  Restore
# the complete vendor body instead of substituting a host-side predicate.
RESIDENT_RECORD_STATUS_ADDRESS = 0x1EAB32
RESIDENT_RECORD_STATUS_SOURCE = 0x3BAB32
RESIDENT_RECORD_STATUS_SIZE = 0x0664
# The next UI setup path reaches 2F:9D1A with two stack arguments.  The flat
# target begins at a parent-frame local load and tail-calls the shared 2E:2E82
# epilogue, which consequently unwinds the non-returning 22:515E main loop.
# Source 4C:9D1A is the exact same-PC LINK #0 drawing/layout routine through
# its balanced 4C:9E4C RETS.
APPLICATION_MAIN_LAYOUT_OVERLAY_DESTINATION = 0x2F9D1A
APPLICATION_MAIN_LAYOUT_OVERLAY_SOURCE = 0x4C9D1A
APPLICATION_MAIN_LAYOUT_OVERLAY_SIZE = 0x0134
# Resource construction at 22:55CA calls linked address 33:17AE with four
# stack words.  Its
# flat target is another large-function middle and reaches the shared 2E:2E82
# epilogue with the main loop's frame.  Mutable source 50:17AE holds the exact
# seven-local wrapper through the balanced 50:17DA RETS.  Linked 33:17AE
# overlaps the active base UI routine at 33:1600, so keep the same PC in the
# otherwise unused top PRG bank and patch the sole caller's SCALL segment.
APPLICATION_MAIN_RESOURCE_CREATE_LINKED_DESTINATION = 0x3317AE
APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_DESTINATION = 0x5F17AE
APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_SOURCE = 0x5017AE
APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_SIZE = 0x002E
APPLICATION_MAIN_RESOURCE_CREATE_CALL = 0x2255CA
# That wrapper enters 20:2DE0 after constructing the main object.  The flat
# destination is erased 0xFFFF space and eventually falls into unrelated code,
# while source 3D:2DE0 is the complete fourteen-local UI/event loop.  It loops
# at 3D:3384 until the application exit state reaches two and has a balanced
# return at 3D:338E.
APPLICATION_FOREGROUND_LOOP_OVERLAY_DESTINATION = 0x202DE0
APPLICATION_FOREGROUND_LOOP_OVERLAY_SOURCE = 0x3D2DE0
APPLICATION_FOREGROUND_LOOP_OVERLAY_SIZE = 0x05B0
# The foreground loop's first checksum/state path reaches 23:1312 through
# 2F:C658.  Flat 23:1312 omits its frame and saved registers, so its 23:1582
# RETS consumes the foreground/main callers.  Source 40:1312 is the complete
# LINK #6 implementation through the balanced 40:17D0 return.
APPLICATION_FOREGROUND_STATE_OVERLAY_DESTINATION = 0x231312
APPLICATION_FOREGROUND_STATE_OVERLAY_SOURCE = 0x401312
APPLICATION_FOREGROUND_STATE_OVERLAY_SIZE = 0x04C0
# A sibling foreground path enters flat 31:D3BA after its real prologue.
# Source 4E:D3BA is the complete LINK #0 copy/state helper through 4E:D450.
APPLICATION_FOREGROUND_COPY_OVERLAY_DESTINATION = 0x31D3BA
APPLICATION_FOREGROUND_COPY_OVERLAY_SOURCE = 0x4ED3BA
APPLICATION_FOREGROUND_COPY_OVERLAY_SIZE = 0x0098
# Foreground event callers at 2D:BE5A and 2A:39A8 enter flat 2F:C216, which
# is the middle of an unrelated large routine and returns through 2F:CBAE.
# Source 4C:C216 is the complete LINK #4 event-result decoder through the
# balanced 4C:C340 return.
APPLICATION_FOREGROUND_EVENT_OVERLAY_DESTINATION = 0x2FC216
APPLICATION_FOREGROUND_EVENT_OVERLAY_SOURCE = 0x4CC216
APPLICATION_FOREGROUND_EVENT_OVERLAY_SIZE = 0x012C
# Event class one is forwarded by the decoder above to 2C:D350.  The
# bootstrap foreground later reuses that destination, but source 49:D350 is
# the complete LINK #0 event-state handler through its balanced 49:D52E
# return.  Restore it together with the decoder at the resident menu boundary.
APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_DESTINATION = 0x2CD350
APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SOURCE = 0x49D350
APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SIZE = 0x01E0
# The frozen control-transfer trace proves that 22:5602 enters 2F:C59A.
# Its flat destination starts in a different large routine: after several
# valid child calls it falls through to the unrelated 2F:CBAE RETS and
# consumes the non-returning main loop's frame.  Source 4C:C59A is the exact
# same-PC LINK #1 parent through its balanced 4C:C6C4 return.
APPLICATION_FOREGROUND_PARENT_OVERLAY_DESTINATION = 0x2FC59A
APPLICATION_FOREGROUND_PARENT_OVERLAY_SOURCE = 0x4CC59A
APPLICATION_FOREGROUND_PARENT_OVERLAY_SIZE = 0x012C
# The restored parent calls 32:FE0A before it reads the foreground dispatch
# table. Flat 32:FE0A jumps into an unrelated large body whose 2D:508E RETS
# consumes the parent's frame and returns directly to 22:5606. Source
# 4F:FE0A is the complete no-argument LINK #0 setup function through its
# balanced 4F:FE40 return; all four direct children are already exact.
APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_DESTINATION = 0x32FE0A
APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_SOURCE = 0x4FFE0A
APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_SIZE = 0x0038
# Both the manager loop and the restored foreground parent index five-word
# records at 21:AA46 by ``state * 10``.  The flat destination contains
# unrelated instructions, while 3E:AA46 holds 130 consecutive records: the
# last word advances monotonically from state 0x00 through 0x80 and the final
# state 0x81 terminates with zero.  Bytes at 3E:AF5A and above are padding
# followed by another function, so restore exactly the 0x514-byte table.
APPLICATION_FOREGROUND_DISPATCH_TABLE_DESTINATION = 0x21AA46
APPLICATION_FOREGROUND_DISPATCH_TABLE_SOURCE = 0x3EAA46
APPLICATION_FOREGROUND_DISPATCH_TABLE_SIZE = 0x0514
# Five ordinary one-byte callers enter 22:23C4, but the flat PRG word there
# is the unconditional half of a signed-extension diamond belonging to the
# preceding 22:* routine (22:23BE branches to 22:23C6, while 22:23C4 skips
# that zero-fill word).  It therefore has neither a LINK prologue nor a
# balanced callee frame and eventually loops inside unrelated record parsing.
# The same-PC source at 3F:23C4 is the complete one-byte foreground/menu-mode
# installer: LINK #3, the 03:4010/401C/406C resident jump-table calls, and a
# balanced return at 3F:28DA.  Restore the exact 0x518-byte body before any
# foreground state dispatch; source bank 3F is still readable at this point.
APPLICATION_FOREGROUND_MODE_OVERLAY_DESTINATION = 0x2223C4
APPLICATION_FOREGROUND_MODE_OVERLAY_SOURCE = 0x3F23C4
APPLICATION_FOREGROUND_MODE_OVERLAY_SIZE = 0x0518
# The root controller's three no-argument call sites enter 32:D964 and store
# its word result in A2:2A40.  Flat 32:D964 starts with 6469/68F2 and falls
# through a large unrelated routine, so its unmatched return eventually pops
# 00:0094 as a bogus caller.  Same-PC source 4F:D964 is the complete 0x46-byte
# query: LINK #0, one 33:07B0 helper call, a 51:2272 table lookup, and a
# balanced RETS at 4F:D9A8.  Copy it before the first root-menu controller
# invocation; source bank 4F remains readable during this installer.
APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_DESTINATION = 0x32D964
APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SOURCE = 0x4FD964
APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SIZE = 0x0046
# The table's zero-flag branch calls 22:381E with the selected state.  Flat
# 22:381E begins halfway through an unrelated pointer scanner.  Source
# 3F:381E is the complete state-to-handler dispatcher for states 00..81 and
# closes at its balanced 3F:3D2C RETS.
APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_DESTINATION = 0x22381E
APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_SOURCE = 0x3F381E
APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_SIZE = 0x0510
# The dispatcher's compact handlers for states 0x00..0x81 live together at
# source 50:3C86.  Flat 33:3C86 instead contains the middle of an unrelated
# long routine, so entering state 0x01 at 33:3E86 eventually executes an
# unmatched UNLINK and destroys the caller's frame.  Restore the complete
# source-proven wrapper block through the balanced 50:3EE4 RETS.
APPLICATION_FOREGROUND_STATE_HANDLER_OVERLAY_DESTINATION = 0x333C86
APPLICATION_FOREGROUND_STATE_HANDLER_OVERLAY_SOURCE = 0x503C86
APPLICATION_FOREGROUND_STATE_HANDLER_OVERLAY_SIZE = 0x0260
# State 0x50 is the active no-input boot state.  Its exact dispatcher child
# is the compact source-4F wrapper, not the middle of flat 32:BFC6.  The
# wrapper's first predicate is likewise a complete source-4E function; both
# ranges have ordinary balanced returns.
APPLICATION_FOREGROUND_STATE50_OVERLAY_DESTINATION = 0x32BFC6
APPLICATION_FOREGROUND_STATE50_OVERLAY_SOURCE = 0x4FBFC6
APPLICATION_FOREGROUND_STATE50_OVERLAY_SIZE = 0x0050
APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_DESTINATION = 0x31CE52
APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_SOURCE = 0x4ECE52
APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_SIZE = 0x009A
# The successful state-50 predicate enters missing internal mask-ROM at
# 0C:0000.  The upgrade image preserves one complete +0x1D-linked copy at
# 29:0000: LINK #D8 through the sole balanced UNLINK/RETS at 29:4A68/4A6A.
# Install those exact words in the reconstructed resident ROM; this is guest
# firmware, not a QEMU-side ROM service or fabricated return stub.
APPLICATION_FOREGROUND_STATE50_ROM_DESTINATION = 0x0C0000
APPLICATION_FOREGROUND_STATE50_ROM_SOURCE = 0x290000
APPLICATION_FOREGROUND_STATE50_ROM_SIZE = 0x4A6C
# The linked source copy recursively calls its own 29:0000 entry from these
# 19 sites.  Once the body is restored at its resident 0C:0000 address those
# far-call segment bytes must follow it.  Leaving them at 29:* is observably
# wrong: the run-time event overlay intentionally replaces 29:3DD2, while
# 0C:3DD2 must remain the pristine in-function state-50 body.
APPLICATION_FOREGROUND_STATE50_ROM_SELF_CALL_OFFSETS = (
    0x06FE, 0x07DE, 0x07F6, 0x0BA6, 0x0C22, 0x0C44, 0x0D4E,
    0x11A8, 0x129A, 0x17D0, 0x18BC, 0x1D7A, 0x1DEC, 0x1F5A,
    0x24B8, 0x2CC2, 0x2CDE, 0x3376, 0x338C,
)
# The state-50 body calls linked 33:4D6C at both its setup and common-exit
# paths.  Flat 33:4D6C is the middle of a large function and returns through
# that function's shared 33:529E epilogue, consuming the state-50 frame.
# Mutable source 50:4D6C is the complete one-argument wrapper.  Its child at
# linked 32:B9C6 and that child's 30:6C9E leaf suffer the same same-PC linked
# collision; source 4F:B9C6 and 4D:6C9E contain the complete balanced bodies.
# Keep the entire source-proven closure at identical PCs in collision-free
# bank 5F, preserving every internal absolute branch, and retarget only the
# two evidenced calls in the recovered resident module.
APPLICATION_FOREGROUND_STATE50_SETTING_LINKED_DESTINATION = 0x334D6C
APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_DESTINATION = 0x5F4D6C
APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_SOURCE = 0x504D6C
APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_SIZE = 0x0016
APPLICATION_FOREGROUND_STATE50_SETTING_CALL_SOURCES = (
    0x29055A, 0x294A16,
)
APPLICATION_FOREGROUND_STATE50_SETTING_CALLS = tuple(
    APPLICATION_FOREGROUND_STATE50_ROM_DESTINATION +
    (source - APPLICATION_FOREGROUND_STATE50_ROM_SOURCE)
    for source in APPLICATION_FOREGROUND_STATE50_SETTING_CALL_SOURCES
)
APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_LINKED_DESTINATION = 0x32B9C6
APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_DESTINATION = 0x5FB9C6
APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_SOURCE = 0x4FB9C6
APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_SIZE = 0x0052
APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_CALL_SOURCE = 0x504D76
APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_LINKED_DESTINATION = 0x306C9E
APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_DESTINATION = 0x5F6C9E
APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_SOURCE = 0x4D6C9E
APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_SIZE = 0x0100
APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_CALL_SOURCE = 0x4FBA0E
# The state-50 ROM module and its wrapper also pass seven pointers into the
# internal 1E:4486..49E1 string pool.  The current skeleton fill makes all of
# those strings identical and breaks both message selection and comparisons.
# Source 3B:4486 is the exact +0x1D-linked pool; 3B:49E4 starts a LINK #1
# function, so stop immediately before it.
APPLICATION_FOREGROUND_STATE50_ROM_DATA_DESTINATION = 0x1E4486
APPLICATION_FOREGROUND_STATE50_ROM_DATA_SOURCE = 0x3B4486
APPLICATION_FOREGROUND_STATE50_ROM_DATA_SIZE = 0x055E
# Once the state-50 setup frame returns normally, the foreground path reaches
# the next absent mask-ROM entry at 1B:ACC0.  Source 38:ACC0 is its complete
# +0x1D-linked copy: LINK #0C through the balanced return at 38:B524.
APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_DESTINATION = 0x1BACC0
APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_SOURCE = 0x38ACC0
APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_SIZE = 0x0866
# The workspace path's 33:443E leaf reaches two more missing resident-ROM
# bodies. Source 3C:6DF6 is the complete 1F:6DF6 renderer/formatter and
# source 3B:3C98 is its complete 1E:3C98 child. The former's call to the
# collision-prone 20:F928 probe is retargeted to resident 5F:F928.
APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_DESTINATION = 0x1F6DF6
APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_SOURCE = 0x3C6DF6
APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_SIZE = 0x05F0
APPLICATION_FOREGROUND_STATE50_FORMAT_SECTOR_CALL_SOURCE = 0x3C701A
APPLICATION_FOREGROUND_STATE50_CHILD_ROM_DESTINATION = 0x1E3C98
APPLICATION_FOREGROUND_STATE50_CHILD_ROM_SOURCE = 0x3B3C98
APPLICATION_FOREGROUND_STATE50_CHILD_ROM_SIZE = 0x06A8
# Both the recovered ROM module and its state-50 caller finish through
# 33:2020.  Flat 33:2020 is an epilogue fragment, while mutable source
# 50:2020 is the complete LINK #0 cleanup routine through 50:2048.
APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_DESTINATION = 0x332020
APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_SOURCE = 0x502020
APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_SIZE = 0x002A
APPLICATION_FOREGROUND_STATE50_CLEANUP_INSTALLER_ADDRESS = 0x0C4A6C
# The foreground parent at 1F:F4E0 calls 2E:A8B6 for a two-coordinate range
# operation.  Flat A8B6 starts in the middle of a computed-dispatch body and
# returns through an odd table address.  Source 4B:A8B6 is the complete
# same-PC LINK #2 implementation, including its balanced UNLINK/RETS tail.
APPLICATION_CURSOR_RANGE_OVERLAY_DESTINATION = 0x2EA8B6
APPLICATION_CURSOR_RANGE_OVERLAY_SOURCE = 0x4BA8B6
APPLICATION_CURSOR_RANGE_OVERLAY_SIZE = 0x0170
# The restored parent calls linked address 33:16F6 once per foreground pass.  That
# destination contains only a tail into the shared compiler epilogue, while
# mutable source 50:16F6 is a complete LINK #9 context/status predicate with
# a balanced return at 50:1722.  It also overlaps the same 33:1600 UI body;
# relocate it at the identical PC in segment 5F and patch its sole caller.
APPLICATION_FOREGROUND_STATUS_LINKED_DESTINATION = 0x3316F6
APPLICATION_FOREGROUND_STATUS_OVERLAY_DESTINATION = 0x5F16F6
APPLICATION_FOREGROUND_STATUS_OVERLAY_SOURCE = 0x5016F6
APPLICATION_FOREGROUND_STATUS_OVERLAY_SIZE = 0x002E
APPLICATION_FOREGROUND_STATUS_CALL = 0x2FC5DA
# The parent and several base UI modules call 32:CAD4 as a one-argument input
# mode flag setter.  Flat 32:CAD4 is the middle of a different large function;
# 4F:CAD4 is the exact call-free LINK #0 leaf through 4F:CB1E.
APPLICATION_INPUT_MODE_OVERLAY_DESTINATION = 0x32CAD4
APPLICATION_INPUT_MODE_OVERLAY_SOURCE = 0x4FCAD4
APPLICATION_INPUT_MODE_OVERLAY_SIZE = 0x004C
# The foreground poll head calls 33:2562 with no arguments before querying
# event readiness.  Flat 33:2562 is a SLOSB in the middle of an unrelated
# function; source 50:2562 is the complete LINK #0 hardware/event gate through
# its balanced return at 50:2588.  Its one-time GPIO child has the same defect
# at 33:3980 and an exact call-free copy at 50:3980..39A0.
APPLICATION_EVENT_GATE_OVERLAY_DESTINATION = 0x332562
APPLICATION_EVENT_GATE_OVERLAY_SOURCE = 0x502562
APPLICATION_EVENT_GATE_OVERLAY_SIZE = 0x0028
APPLICATION_EVENT_GATE_POWER_OVERLAY_DESTINATION = 0x333980
APPLICATION_EVENT_GATE_POWER_OVERLAY_SOURCE = 0x503980
APPLICATION_EVENT_GATE_POWER_OVERLAY_SIZE = 0x0022
# Resident 1C:F28A calls 2B:6434 while decoding the event packet.  Both that
# target and its 2C:F4CC child are flat large-function middles.  The +0x1D
# banks contain complete ABI-compatible bodies with one closed epilogue each:
# 48:6434..6660 and the call-free 49:F4CC..F6A4.
APPLICATION_EVENT_PACKET_DECODE_OVERLAY_DESTINATION = 0x2B6434
APPLICATION_EVENT_PACKET_DECODE_OVERLAY_SOURCE = 0x486434
APPLICATION_EVENT_PACKET_DECODE_OVERLAY_SIZE = 0x022E
APPLICATION_EVENT_PACKET_COPY_OVERLAY_DESTINATION = 0x2CF4CC
APPLICATION_EVENT_PACKET_COPY_OVERLAY_SOURCE = 0x49F4CC
APPLICATION_EVENT_PACKET_COPY_OVERLAY_SIZE = 0x01DA
# Both resident event loops then query 32:4C34.  Its flat bytes are another
# unrelated function middle; 4F:4C34 is the complete no-argument ready/poll
# leaf and returns cleanly at 4F:4CA6.
APPLICATION_EVENT_READY_OVERLAY_DESTINATION = 0x324C34
APPLICATION_EVENT_READY_OVERLAY_SOURCE = 0x4F4C34
APPLICATION_EVENT_READY_OVERLAY_SIZE = 0x0074
# Foreground action wrapper 33:3D86 passes its object pointer to 27:DBB4.
# The flat destination is a font/table island; linked source 44:DBB4 is the
# complete framed object-relink routine and returns at 44:DEDA.
APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_DESTINATION = 0x27DBB4
APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_SOURCE = 0x44DBB4
APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_SIZE = 0x0328
# The 08:40D0 timer vector installs callback 27:E528 on its synthetic far
# return frame.  Source 44:E528 is the complete interrupt-time application
# worker; its key path feeds the hardware matrix at DS1:7160 through the
# debounce/scanner leaves below.
APPLICATION_TIMER_CALLBACK_OVERLAY_DESTINATION = 0x27E528
APPLICATION_TIMER_CALLBACK_OVERLAY_SOURCE = 0x44E528
APPLICATION_TIMER_CALLBACK_OVERLAY_SIZE = 0x0324
APPLICATION_KEY_DEBOUNCE_OVERLAY_DESTINATION = 0x31BE70
APPLICATION_KEY_DEBOUNCE_OVERLAY_SOURCE = 0x4EBE70
APPLICATION_KEY_DEBOUNCE_OVERLAY_SIZE = 0x009E
APPLICATION_KEY_MATRIX_SCAN_OVERLAY_DESTINATION = 0x2E5F28
APPLICATION_KEY_MATRIX_SCAN_OVERLAY_SOURCE = 0x4B5F28
APPLICATION_KEY_MATRIX_SCAN_OVERLAY_SIZE = 0x0180
# 2E:5F28 indexes two eight-word tables through data pointer 33:5416.  The
# flat destination is unrelated program data; 50:5416 contains the exact row
# strobes (0004..8000) and column masks (0001..0080).  The event decoder at
# 2E:8742 likewise selects one of three contiguous 64-word tables whose exact
# same-PC templates are present at 4F:29B2..2B31.
KEY_MATRIX_TABLE_DESTINATION = 0x335416
KEY_MATRIX_TABLE_SOURCE = 0x505416
KEY_MATRIX_TABLE_SIZE = 0x0020
KEY_EVENT_TABLES_DESTINATION = 0x3229B2
KEY_EVENT_TABLES_SOURCE = 0x4F29B2
KEY_EVENT_TABLES_SIZE = 0x0180
APPLICATION_TIMER_POWER_OVERLAY_DESTINATION = 0x32241A
APPLICATION_TIMER_POWER_OVERLAY_SOURCE = 0x4F241A
APPLICATION_TIMER_POWER_OVERLAY_SIZE = 0x0084
APPLICATION_TIMER_IDLE_OVERLAY_DESTINATION = 0x3047EA
APPLICATION_TIMER_IDLE_OVERLAY_SOURCE = 0x4D47EA
APPLICATION_TIMER_IDLE_OVERLAY_SIZE = 0x00CC
# The exact timer-idle service calls four tiny register-bit helpers at linked
# segment-33 addresses.  All four flat destinations are live fall-through
# instructions in the 33:6030..6DAE record renderer, so a direct call enters
# that renderer without its frame and eventually returns to the timer caller
# after drawing zeroed text records.  The exact source-50 helpers are closed
# LINK #0 leaves.  Relocate those leaves and patch only the copied timer-idle
# body, preserving every flat renderer byte.
APPLICATION_TIMER_IDLE_REGISTER_LEAF_OVERLAYS = (
    (0x5F6BB2, 0x506BB2, 0x0008),
    (0x5F6BBA, 0x506BBA, 0x0008),
    (0x5F6C2A, 0x506C2A, 0x0008),
    (0x5F6C32, 0x506C32, 0x0008),
)
APPLICATION_TIMER_IDLE_REGISTER_LEAF_CALLS = (
    (0x304844, 0x4D4844, 0x336BB2, 0x5F6BB2),
    (0x30484C, 0x4D484C, 0x336BBA, 0x5F6BBA),
    (0x30487A, 0x4D487A, 0x336C2A, 0x5F6C2A),
    (0x304882, 0x4D4882, 0x336C32, 0x5F6C32),
)
APPLICATION_TIMER_CALENDAR_OVERLAY_DESTINATION = 0x317B9E
APPLICATION_TIMER_CALENDAR_OVERLAY_SOURCE = 0x4E7B9E
APPLICATION_TIMER_CALENDAR_OVERLAY_SIZE = 0x00B2
APPLICATION_TIMER_COMMIT_OVERLAY_DESTINATION = 0x313212
APPLICATION_TIMER_COMMIT_OVERLAY_SOURCE = 0x4E3212
APPLICATION_TIMER_COMMIT_OVERLAY_SIZE = 0x00C4
# Once 32:4C34 reports a pending matrix event, 33:4ECC fetches its raw index
# and 2E:8742 translates it through the active application key map.
APPLICATION_EVENT_FETCH_OVERLAY_DESTINATION = 0x334ECC
APPLICATION_EVENT_FETCH_OVERLAY_SOURCE = 0x504ECC
APPLICATION_EVENT_FETCH_OVERLAY_SIZE = 0x0016
APPLICATION_EVENT_DECODE_OVERLAY_DESTINATION = 0x2E8742
APPLICATION_EVENT_DECODE_OVERLAY_SOURCE = 0x4B8742
APPLICATION_EVENT_DECODE_OVERLAY_SIZE = 0x0178
# When the status predicate sees object state 0x37 it invokes 20:BE12.  The
# flat target cannot advance that state, leaving the foreground screen at its
# loading message forever.  Source 3D:BE12 is the exact same-PC LINK #39
# loading/event task with closed control flow and a balanced 3D:C374 return.
APPLICATION_LOADING_TASK_OVERLAY_DESTINATION = 0x20BE12
APPLICATION_LOADING_TASK_OVERLAY_SOURCE = 0x3DBE12
APPLICATION_LOADING_TASK_OVERLAY_SIZE = 0x0564
# After 23:1312 returns, 2F:C65C calls missing internal ROM 1C:5892.  The
# update image ships its exact +0x1D body at 39:5892: a complete LINK #11
# foreground worker with closed control flow and a balanced 39:6080 return.
APPLICATION_FOREGROUND_ROM_WORKER_DESTINATION = 0x1C5892
APPLICATION_FOREGROUND_ROM_WORKER_SOURCE = 0x395892
APPLICATION_FOREGROUND_ROM_WORKER_SIZE = 0x07F0
# 1C:5892 calls the next missing internal foreground dispatcher at 16:BBCC.
# Source 33:BBCC is its exact +0x1D implementation: LINK #6, closed branches,
# and a balanced return at 33:C8A0.
APPLICATION_FOREGROUND_ROM_DISPATCH_DESTINATION = 0x16BBCC
APPLICATION_FOREGROUND_ROM_DISPATCH_SOURCE = 0x33BBCC
APPLICATION_FOREGROUND_ROM_DISPATCH_SIZE = 0x0CD6
# 4A:7F02 calls 2B:2F44 during the top-level one-shot setup.  The flat
# destination is an unrelated record-scanner caller; the exact +0x1D source
# at 48:2F44 is a complete LINK #2 registry initializer which installs the
# 2F:20xx system-item table and sets A0:70BE to the far pointer 10:5000.
APPLICATION_SYSTEM_REGISTRY_OVERLAY_DESTINATION = 0x2B2F44
APPLICATION_SYSTEM_REGISTRY_OVERLAY_SOURCE = 0x482F44
APPLICATION_SYSTEM_REGISTRY_OVERLAY_SIZE = 0x023A
# Its 48:2F82 call targets linked 32:C296.  The flat destination is a live
# suffix of the large 32:Bxxx worker (and falls backward through 32:BED6),
# while 4F:C296 is the complete LINK #2 result-object loader.  Preserve the
# flat fall-through and relocate only this independently called function.
APPLICATION_SYSTEM_REGISTRY_RESULT_LINKED_DESTINATION = 0x32C296
APPLICATION_SYSTEM_REGISTRY_RESULT_OVERLAY_DESTINATION = 0x5FC296
APPLICATION_SYSTEM_REGISTRY_RESULT_OVERLAY_SOURCE = 0x4FC296
APPLICATION_SYSTEM_REGISTRY_RESULT_OVERLAY_SIZE = 0x0050
APPLICATION_SYSTEM_REGISTRY_RESULT_CALL = 0x2B2F82
APPLICATION_SYSTEM_REGISTRY_RESULT_CALL_SOURCE = 0x482F82
# The same registry initializer then invokes linked 32:C1A6 for each of its
# 25 fixed entries.  Flat 32:C1A6 is another suffix of the same large worker;
# source 4F:C1A6 is the complete framed entry creator.  Its first child is the
# already-relocated 33:6BF2 predicate.  The result loader's null branch also
# calls linked 29:F732, whose flat body consumes the loader frame; preserve
# the complete source-46 fallback out of line below the 5F sector probe.
APPLICATION_SYSTEM_REGISTRY_ENTRY_LINKED_DESTINATION = 0x32C1A6
APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_DESTINATION = 0x5FC1A6
APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SOURCE = 0x4FC1A6
APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SIZE = 0x0050
APPLICATION_SYSTEM_REGISTRY_ENTRY_RECORD_ACCEPT_CALL = 0x5FC1AA
APPLICATION_SYSTEM_REGISTRY_ENTRY_RECORD_ACCEPT_CALL_SOURCE = 0x4FC1AA
APPLICATION_SYSTEM_REGISTRY_ENTRY_CALL_SOURCES = tuple(
    0x482F92 + 0x12 * index for index in range(25)
)
APPLICATION_SYSTEM_REGISTRY_ENTRY_CALLS = tuple(
    0x2B2F92 + 0x12 * index for index in range(25)
)
APPLICATION_SYSTEM_REGISTRY_FALLBACK_LINKED_DESTINATION = 0x29F732
APPLICATION_SYSTEM_REGISTRY_FALLBACK_OVERLAY_DESTINATION = 0x5EF732
APPLICATION_SYSTEM_REGISTRY_FALLBACK_OVERLAY_SOURCE = 0x46F732
APPLICATION_SYSTEM_REGISTRY_FALLBACK_OVERLAY_SIZE = 0x028C
APPLICATION_SYSTEM_REGISTRY_RESULT_FALLBACK_CALL = 0x5FC2DC
APPLICATION_SYSTEM_REGISTRY_RESULT_FALLBACK_CALL_SOURCE = 0x4FC2DC
# The registry initializer first asks 29:02D8 for the storage capacity.  The
# flat target falls into unrelated recursive copy code; 46:02D8 is the exact
# LINK #9 storage scan/calculation body and returns its result in R0:R1.
APPLICATION_STORAGE_CAPACITY_OVERLAY_DESTINATION = 0x2902D8
APPLICATION_STORAGE_CAPACITY_OVERLAY_SOURCE = 0x4602D8
APPLICATION_STORAGE_CAPACITY_OVERLAY_SIZE = 0x02D8
# The capacity scan resolves each storage record through these two exact
# +0x1D bodies.  Their flat targets are unrelated code; 47:D374 validates a
# unit/address pair and 4A:3460 selects the matching driver callback.
APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_DESTINATION = 0x2AD374
APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_SOURCE = 0x47D374
APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_SIZE = 0x0252
APPLICATION_STORAGE_RECORD_LOOKUP_DRIVER_CALL = 0x2AD402
APPLICATION_STORAGE_RECORD_LOOKUP_DRIVER_CALL_SOURCE = 0x47D402
APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_DESTINATION = 0x2D3460
APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SOURCE = 0x4A3460
APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SIZE = 0x01C8
APPLICATION_STORAGE_DRIVER_RESOLVE_ORIGINAL_SOURCE = 0x2D3460
APPLICATION_STORAGE_UNIT_OPEN_RETIRE_CALL_ADDRESS = 0x30A4A4
# The compiler initializer publishes 33:091C as record 0's indirect storage
# callback at 51:27A4.  The flat target is the middle of a large unrelated
# function and consumes the caller's frame.  The same-PC +0x1D image at
# 50:091C is the exact three-word callback: LINK #0, store the far address at
# A2:29C8, call 33:6E5E with the remaining word, and return at 50:094E.
# Segment 50 is mutable application RAM by the late install phase, so embed
# the original 0x34 bytes in the guest installer.
STORAGE_RECORD_CALLBACK_OVERLAY_DESTINATION = 0x33091C
STORAGE_RECORD_CALLBACK_OVERLAY_SOURCE = 0x50091C
STORAGE_RECORD_CALLBACK_OVERLAY_SIZE = 0x0034
# That exact callback's only call is 33:6E5E.  The flat destination again
# starts in the middle of an unrelated large function, while the same-PC
# segment-50 image is the complete vendor service: LINK #0, UNLINK, RETS.
# Preserve these six bytes alongside its caller before segment 50 is reused.
STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_DESTINATION = 0x336E5E
STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_SOURCE = 0x506E5E
STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_SIZE = 0x0006
# The per-unit partition worker calls record+0x10 to obtain the medium
# capacity before accepting the MBR start LBA.  Record zero publishes the
# 33:661A wrapper, whose sole child is linked at 33:13F8.  Flat 33:13F8 is a
# large-function suffix and tears down the worker's frame; mutable source
# 50:13F8 is the exact framed capacity service.  Its child at linked 32:6B58
# has the same collision, while source 4F:6B58 is a complete call-free
# capacity calculation.  Keep that child in a collision-free top-bank slot
# and retarget only the source-proven call in the recovered service.
STORAGE_RECORD_CAPACITY_SERVICE_LINKED_DESTINATION = 0x3313F8
STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_DESTINATION = 0x5F13F8
STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_SOURCE = 0x5013F8
STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_SIZE = 0x0030
STORAGE_RECORD_CAPACITY_CHILD_LINKED_DESTINATION = 0x326B58
STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_DESTINATION = 0x5F6DA0
STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SOURCE = 0x4F6B58
STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SIZE = 0x006A
STORAGE_RECORD_CAPACITY_CHILD_CALL_SOURCE = 0x5013FE
STORAGE_RECORD_CAPACITY_WRAPPER_LINKED_DESTINATION = 0x33661A
STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_DESTINATION = 0x5F661A
STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_SOURCE = 0x50661A
STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_SIZE = 0x000A
STORAGE_RECORD_CAPACITY_WRAPPER_CALL_SOURCE = 0x50661C
STORAGE_RECORD_CAPACITY_INSTALLER_ADDRESS = 0x075100
# Exact 25:5858 opens each of the four unit records through 30:A3C2.  The
# updater's immutable template still publishes the collided 33:661A address,
# and the Harvard data view cannot patch that source before it is copied.
# Retarget this single source-proven call to a guest wrapper.  For unit zero
# the wrapper updates record+0x10 to the recovered top-bank closure and then
# forwards the original argument to exact 30:A3C2 unchanged.
STORAGE_UNIT_OPEN_CAPACITY_CALL = 0x255AE6
STORAGE_UNIT_OPEN_CAPACITY_CALL_SOURCE = 0x425AE6
STORAGE_UNIT_OPEN_CAPACITY_LINKED_DESTINATION = 0x30A3C2
STORAGE_UNIT_OPEN_CAPACITY_WRAPPER_ADDRESS = 0x075300
STORAGE_UNIT_ZERO_RECORD_CAPACITY_SEGMENT_ADDRESS = 0x5127B0
STORAGE_UNIT_ZERO_RECORD_CAPACITY_OFFSET_ADDRESS = 0x5127B2
# After the lookup returns, 2C:F9B8 calls 33:0070.  Its flat bytes are another
# unrelated function body with no LINK prologue and overwrite the caller's
# frame.  The +0x1D same-PC image is a complete LINK #0 wrapper that resolves
# a pointer, calls the already-recovered 28:1F08 text loop, and returns at
# 50:00A6 with a balanced frame.
STORAGE_RECORD_POST_LOOKUP_OVERLAY_DESTINATION = 0x330070
STORAGE_RECORD_POST_LOOKUP_OVERLAY_SOURCE = 0x500070
STORAGE_RECORD_POST_LOOKUP_OVERLAY_SIZE = 0x0038
# If the quick record scan cannot determine capacity, five recovered callers
# target logical 20:F928.  Source 3D:F928 is the complete LINK #10
# sector/geometry probe through the paired RETS at 3D:FE7E, but 20:F928 is
# also a live fall-through point in the large 20:E914 function.  Installing
# the probe at its linked address therefore corrupts that function and makes
# its later 20:FC8A instruction consume the wrong frame.  Keep the exact
# probe in the otherwise unused top PRG bank and retarget only the five
# source-proven SCALL sites.
APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION = 0x20F928
APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION = 0x5FF928
APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SOURCE = 0x3DF928
APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SIZE = 0x0558
RESIDENT_TRANSFORM_1B_SECTOR_PROBE_CALL_SOURCE = 0x38CD04
RESIDENT_TRANSFORM_1C_SECTOR_PROBE_CALL_SOURCE = 0x39D374
RESIDENT_TRANSFORM_1C_STORAGE_PAIR_CALL_SOURCE = 0x39CFD6
RESIDENT_RESULT_RECORD_BUILD_SECTOR_PROBE_CALL_SOURCE = 0x3BC774
APPLICATION_STORAGE_CAPACITY_SECTOR_PROBE_CALL = 0x290536
APPLICATION_STORAGE_CAPACITY_SECTOR_PROBE_CALL_SOURCE = 0x460536
APPLICATION_LAUNCH_RECORD_APPLY_SECTOR_PROBE_CALL = 0x2D1DA6
APPLICATION_LAUNCH_RECORD_APPLY_SECTOR_PROBE_CALL_SOURCE = 0x4A1DA6
# The foreground cleanup paths call logical 20:E914 with a two-word far
# object pointer.  That flat address is only the middle of the simultaneously
# live 20:E914..20:FE80 fall-through function: it has no LINK prologue and its
# RETS at 20:FC88 consumes the caller's frame.  Source 3D:E914 is the complete
# LINK #7 routine through UNLINK/RETS at 3D:EE6E/3D:EE70.  Preserve it at the
# same PC in the free part of the top PRG bank and retarget only the three
# instruction-reachable SCALL sites recovered from the shipped image.
APPLICATION_FOREGROUND_OBJECT_UPDATE_LINKED_DESTINATION = 0x20E914
APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_DESTINATION = 0x5FE914
APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SOURCE = 0x3DE914
APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SIZE = 0x055E
APPLICATION_FOREGROUND_OBJECT_UPDATE_CALLS = (
    0x312FC6,
    0x332968,
    0x33297E,
)
APPLICATION_FOREGROUND_OBJECT_UPDATE_CALL_SOURCES = (
    0x312FC6,
    0x332968,
    0x33297E,
)
# The first post-modal main-loop pass calls 33:21EE without arguments.  Flat
# 33:21EE begins in the middle of a different function and falls through to
# the object-update cleanup tail, while same-PC source 50:21EE is the complete
# LINK #0 state-bit wrapper through RETS at 50:2216.  Segment 50 is mutable by
# this phase, so the resident installer must retain the exact shipped words.
APPLICATION_POST_MODAL_STATE_OVERLAY_DESTINATION = 0x3321EE
APPLICATION_POST_MODAL_STATE_OVERLAY_SOURCE = 0x5021EE
APPLICATION_POST_MODAL_STATE_OVERLAY_SIZE = 0x002A
# Immediately after that state wrapper, the main loop calls 30:D7AE.  Flat
# 30:D7AE starts just after the preceding command-matrix function, in a large
# unrelated body's local-variable path; it has no LINK and eventually falls
# through the 00:1002 dynamic module's otherwise valid 00:5FB0 epilogue.
# Source 4D:D7AE..4D:D88A is the exact LINK #3 post-modal refresh function.
APPLICATION_POST_MODAL_REFRESH_OVERLAY_DESTINATION = 0x30D7AE
APPLICATION_POST_MODAL_REFRESH_OVERLAY_SOURCE = 0x4DD7AE
APPLICATION_POST_MODAL_REFRESH_OVERLAY_SIZE = 0x00DE
# The post-modal refresh body prints the fixed string at logical 1D:FFF6.
# Its exact +0x1D-linked bytes occupy the final ten bytes of source segment
# 3A and terminate at the bank boundary.  Keep the constant in reconstructed
# resident ROM so the Harvard data-bus alias can expose guest ROM bytes rather
# than a QEMU-authored replacement string.
APPLICATION_POST_MODAL_TEXT_ROM_DATA_DESTINATION = 0x1DFFF6
APPLICATION_POST_MODAL_TEXT_ROM_DATA_SOURCE = 0x3AFFF6
APPLICATION_POST_MODAL_TEXT_ROM_DATA_SIZE = 0x000A
# Ten reachable callers pass a two-word far value to 33:40A8.  Its flat image
# is a branch-body fragment ending at 33:450E, whereas source 50:40A8 is the
# complete LINK #0 wrapper which delegates to 31:AED0 and returns R1 in R0.
APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_DESTINATION = 0x3340A8
APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SOURCE = 0x5040A8
APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SIZE = 0x001E
# Source 4E:E27A is a complete register-quad conversion helper relocated to
# logical 31:E27A.  Its initial SJMP already names 31:E286, and the bounded
# body manually preserves R2..R6 before returning at 31:E30C.  Flat 31:E27A
# instead falls into an unrelated long routine and consumes the outer frame.
APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_DESTINATION = 0x31E27A
APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_SOURCE = 0x4EE27A
APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_SIZE = 0x0094
# The follow-on numeric path calls logical 32:169C.  Source 4F:169C is its
# complete LINK #0 signed-value conversion through 32:1720 when installed at
# the linked address; flat 32:169C is another unrelated call/return fragment.
APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_DESTINATION = 0x32169C
APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SOURCE = 0x4F169C
APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SIZE = 0x0086
# The same numeric path next calls logical 2E:2E82 with its four-word value in
# R4..R7.  Flat 2E:2E82 is only the pop-R2/pop-R1/UNLINK tail of an unrelated
# function, so it consumes the caller's frame and returns to 06:4608.  Source
# 4B:2E82 is the complete LINK #0x0D normalizer.  Its primary RETS is at
# 4B:2FB4, while reachable overflow/underflow arms continue through the AJMP
# at 4B:3006..3008 and branch back to the common 2F:A0 epilogue.
APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_DESTINATION = 0x2E2E82
APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SOURCE = 0x4B2E82
APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SIZE = 0x0188
# The normalizer calls the register-ABI multiply/accumulate leaf at linked
# 33:1A5A three times.  That linked PC is an extension word in the still-live
# flat segment-33 wide-render body, so installing source 50:1A5A in place
# would destroy the caller which eventually reaches the normalizer.  Preserve
# the exact call-free leaf at the same PC in collision-free bank 5F and patch
# only the three instruction-reachable calls inside the restored 2E:2E82
# normalizer.  Without this closure, the first call enters the flat body at
# 33:1A5A, falls through to 33:1A9C, and recursively re-enters 2E:2E82 while
# consuming one 0x2E-byte normalizer frame per pass.
WIDE_ACCUMULATE_LINKED_DESTINATION = 0x331A5A
WIDE_ACCUMULATE_OVERLAY_DESTINATION = 0x5F1A5A
WIDE_ACCUMULATE_OVERLAY_SOURCE = 0x501A5A
WIDE_ACCUMULATE_OVERLAY_SIZE = 0x002C
WIDE_ACCUMULATE_CALLS = (
    0x2E2F20,
    0x2E2F28,
    0x2E2F2E,
)
WIDE_ACCUMULATE_CALL_SOURCES = tuple(
    0x4B0000 | (call & 0xFFFF) for call in WIDE_ACCUMULATE_CALLS
)
# The shared numeric path is then reached through logical 2F:A0B6 by dozens
# of shipped callers.  Flat 2F:A0B6 begins at a local store in unrelated code
# and, at A1E8, treats the next flat word as yet another SCALL before sliding
# through data to the unmatched A4BA RETS.  Source 4C:A0B6..4C:A1E8 is the
# exact LINK #0x15 implementation with its own balanced return.
APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_DESTINATION = 0x2FA0B6
APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SOURCE = 0x4CA0B6
APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SIZE = 0x0134
# The recovered register dispatcher at 33:5DE4 tail-jumps to logical 33:4B88
# for its second operation.  Flat 33:4B88 is a large-function middle which
# reaches the unrelated 33:52A8 epilogue.  Mutable source 50:4B88..4B9C is
# the exact call-free leaf: it tests R0..R3, toggles R0's sign bit when the
# wide value is nonzero, and RETS directly to the dispatcher's caller.
WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_DESTINATION = 0x334B88
WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SOURCE = 0x504B88
WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SIZE = 0x0016
# 4A:7E5E passes the far resource base 50:8000 to 33:3082.  The flat target
# starts in the middle of an unrelated function, while 50:3082 is the exact
# complete LINK #0 setter which stores that pointer at A2:2984..2986.  Source
# segment 50 is mutable application RAM by the time this late overlay phase
# runs, so retain the shipped words in the installer rather than copying from
# the live source bank.
APPLICATION_RESOURCE_POINTER_OVERLAY_DESTINATION = 0x333082
APPLICATION_RESOURCE_POINTER_OVERLAY_SOURCE = 0x503082
APPLICATION_RESOURCE_POINTER_OVERLAY_SIZE = 0x0024
# The first top-level child calls 32:DC20 without arguments.  Its flat bytes
# begin at a saved-register push in another body, while 4F:DC20 is a complete
# call-free hardware/tick initializer with LINK and RETS boundaries.
STARTUP_TICK_INIT_OVERLAY_DESTINATION = 0x32DC20
STARTUP_TICK_INIT_OVERLAY_SOURCE = 0x4FDC20
STARTUP_TICK_INIT_OVERLAY_SIZE = 0x0046
STARTUP_TIMER_CONFIG_OVERLAY_DESTINATION = 0x32F47A
STARTUP_TIMER_CONFIG_OVERLAY_SOURCE = 0x4FF47A
STARTUP_TIMER_CONFIG_OVERLAY_SIZE = 0x003C
# 33:5E66 calls 2C:A7DA with a 16-byte argument block.  The flat target
# lacks its prologue and eventually enters a shared epilogue at 2C:B8AE,
# restoring a zero FP.  49:A7DA is the complete same-PC implementation:
# LINK #8, four saved registers, two copy loops, and a paired UNLINK/RETS.
APPLICATION_FAR_BLOCK_COPY_OVERLAY_DESTINATION = 0x2CA7DA
APPLICATION_FAR_BLOCK_COPY_OVERLAY_SOURCE = 0x49A7DA
APPLICATION_FAR_BLOCK_COPY_OVERLAY_SIZE = 0x01E6
APPLICATION_INIT_ENTRY_OVERLAY_DESTINATION = 0x229738
APPLICATION_INIT_ENTRY_OVERLAY_SOURCE = 0x3F9738
APPLICATION_INIT_ENTRY_OVERLAY_SIZE = 0x04F0
# The initializer's call at 22:99BC targets logical 2F:4D94.  Flat 2F:4D94
# starts inside an unrelated five-register function and reaches its UNLINK,
# prematurely returning from 22:9738 before the 2A48 startup latch is set.
# Source 4C:4D94 is the exact same-PC LINK #8 clock/resource validator and
# returns normally at 4C:4EDA.  Restore that complete bounded function.
APPLICATION_CLOCK_VALIDATE_OVERLAY_DESTINATION = 0x2F4D94
APPLICATION_CLOCK_VALIDATE_OVERLAY_SOURCE = 0x4C4D94
APPLICATION_CLOCK_VALIDATE_OVERLAY_SIZE = 0x0148
# Once the clock validator returns, the initializer calls logical 31:6010.
# Flat 31:6010 is again a mid-function word (the target of an AJMP from
# 31:600E), so it falls into the resident modal machinery instead of
# returning to 22:99C4.  Source 4E:6010 is the exact same-PC LINK #0 routine:
# it initializes the 0x50:B888 service and copies the four-word 62:6ACA/6AD2
# hardware state into A2:2928..294E before returning at 4E:60C6.
APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_DESTINATION = 0x316010
APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SOURCE = 0x4E6010
APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SIZE = 0x00B8
# The following initializer call at 22:99C4 targets logical 32:BA18.  The
# flat word there belongs to an unrelated signed-index loop.  Source 4F:BA18
# is the bounded same-PC LINK #0 service initializer; it creates 51:1C40 and
# clears the A2:2AC6/2ACC/2ACE byte latches before returning at 4F:BA68.
APPLICATION_SERVICE_LATCH_INIT_OVERLAY_DESTINATION = 0x32BA18
APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SOURCE = 0x4FBA18
APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SIZE = 0x0052
# Same-PC functions reached by the remainder of 3F:9738 after the service
# latch initializer.  Each source has a compiler LINK prologue and a bounded
# UNLINK/RETS epilogue.  The source-bank relationship is consistent across
# this application image: logical 31/32/33 map to shipped 4E/4F/50.
APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_DESTINATION = 0x3313C8
APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_SOURCE = 0x5013C8
APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_SIZE = 0x0030
APPLICATION_INIT_31_1528_OVERLAY_DESTINATION = 0x311528
APPLICATION_INIT_31_1528_OVERLAY_SOURCE = 0x4E1528
APPLICATION_INIT_31_1528_OVERLAY_SIZE = 0x00CE
APPLICATION_INIT_08_2EDC_OVERLAY_DESTINATION = 0x082EDC
APPLICATION_INIT_08_2EDC_OVERLAY_SOURCE = 0x502EDC
APPLICATION_INIT_08_2EDC_OVERLAY_SIZE = 0x001A
APPLICATION_INIT_33_356E_OVERLAY_DESTINATION = 0x33356E
APPLICATION_INIT_33_356E_OVERLAY_SOURCE = 0x50356E
APPLICATION_INIT_33_356E_OVERLAY_SIZE = 0x0024
APPLICATION_INIT_33_3406_OVERLAY_DESTINATION = 0x333406
APPLICATION_INIT_33_3406_OVERLAY_SOURCE = 0x503406
APPLICATION_INIT_33_3406_OVERLAY_SIZE = 0x0024
APPLICATION_INIT_08_3324_OVERLAY_DESTINATION = 0x083324
APPLICATION_INIT_08_3324_OVERLAY_SOURCE = 0x253324
APPLICATION_INIT_08_3324_OVERLAY_SIZE = 0x0026
APPLICATION_INIT_33_3FD6_OVERLAY_DESTINATION = 0x333FD6
APPLICATION_INIT_33_3FD6_OVERLAY_SOURCE = 0x503FD6
APPLICATION_INIT_33_3FD6_OVERLAY_SIZE = 0x001E
APPLICATION_INIT_29_C126_OVERLAY_DESTINATION = 0x29C126
APPLICATION_INIT_29_C126_OVERLAY_SOURCE = 0x46C126
APPLICATION_INIT_29_C126_OVERLAY_SIZE = 0x029A
APPLICATION_INIT_33_09B8_OVERLAY_DESTINATION = 0x3309B8
APPLICATION_INIT_33_09B8_OVERLAY_SOURCE = 0x5009B8
APPLICATION_INIT_33_09B8_OVERLAY_SIZE = 0x0034
APPLICATION_INIT_32_4D1C_OVERLAY_DESTINATION = 0x324D1C
APPLICATION_INIT_32_4D1C_OVERLAY_SOURCE = 0x4F4D1C
APPLICATION_INIT_32_4D1C_OVERLAY_SIZE = 0x0074
APPLICATION_INIT_32_3232_OVERLAY_DESTINATION = 0x323232
APPLICATION_INIT_32_3232_OVERLAY_SOURCE = 0x4F3232
APPLICATION_INIT_32_3232_OVERLAY_SIZE = 0x0080
APPLICATION_INIT_31_C3FC_OVERLAY_DESTINATION = 0x31C3FC
APPLICATION_INIT_31_C3FC_OVERLAY_SOURCE = 0x4EC3FC
APPLICATION_INIT_31_C3FC_OVERLAY_SIZE = 0x009C
APPLICATION_INIT_32_519E_OVERLAY_DESTINATION = 0x32519E
APPLICATION_INIT_32_519E_OVERLAY_SOURCE = 0x4F519E
APPLICATION_INIT_32_519E_OVERLAY_SIZE = 0x0072
APPLICATION_INIT_32_F3C6_OVERLAY_DESTINATION = 0x32F3C6
APPLICATION_INIT_32_F3C6_OVERLAY_SOURCE = 0x4FF3C6
APPLICATION_INIT_32_F3C6_OVERLAY_SIZE = 0x003C
APPLICATION_INIT_31_B6FC_OVERLAY_DESTINATION = 0x31B6FC
APPLICATION_INIT_31_B6FC_OVERLAY_SOURCE = 0x4EB6FC
APPLICATION_INIT_31_B6FC_OVERLAY_SIZE = 0x00A0
APPLICATION_INIT_31_CC84_OVERLAY_DESTINATION = 0x31CC84
APPLICATION_INIT_31_CC84_OVERLAY_SOURCE = 0x4ECC84
APPLICATION_INIT_31_CC84_OVERLAY_SIZE = 0x009A
# Exact 4E:CC84 reaches 32:C514 only when the factory D03F enable byte is one.
# The flat destination is an unrelated body which eventually returns through
# 00:0031.  Source 4F:C514 is the complete bounded LINK #1 initializer through
# C560; preserve it before the source bank becomes writable application RAM.
APPLICATION_INIT_32_C514_OVERLAY_DESTINATION = 0x32C514
APPLICATION_INIT_32_C514_OVERLAY_SOURCE = 0x4FC514
APPLICATION_INIT_32_C514_OVERLAY_SIZE = 0x004E
APPLICATION_INITIALIZER_FOLLOWUP_EMBEDDED_DESTINATIONS = frozenset((
    APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_DESTINATION,
    APPLICATION_INIT_31_1528_OVERLAY_DESTINATION,
    APPLICATION_INIT_08_2EDC_OVERLAY_DESTINATION,
    APPLICATION_INIT_33_356E_OVERLAY_DESTINATION,
    APPLICATION_INIT_33_3406_OVERLAY_DESTINATION,
    APPLICATION_INIT_08_3324_OVERLAY_DESTINATION,
    APPLICATION_INIT_33_3FD6_OVERLAY_DESTINATION,
    APPLICATION_INIT_29_C126_OVERLAY_DESTINATION,
    APPLICATION_INIT_33_09B8_OVERLAY_DESTINATION,
    APPLICATION_INIT_32_4D1C_OVERLAY_DESTINATION,
    APPLICATION_INIT_32_3232_OVERLAY_DESTINATION,
    APPLICATION_INIT_31_C3FC_OVERLAY_DESTINATION,
    APPLICATION_INIT_32_519E_OVERLAY_DESTINATION,
    APPLICATION_INIT_32_F3C6_OVERLAY_DESTINATION,
    APPLICATION_INIT_31_B6FC_OVERLAY_DESTINATION,
    APPLICATION_INIT_31_CC84_OVERLAY_DESTINATION,
    APPLICATION_INIT_32_C514_OVERLAY_DESTINATION,
))
APPLICATION_MAIN_LOOP_OVERLAY_DESTINATION = 0x22515E
APPLICATION_MAIN_LOOP_OVERLAY_SOURCE = 0x3F515E
APPLICATION_MAIN_LOOP_OVERLAY_SIZE = 0x04FA
APPLICATION_RESOURCE_DRIVER_OVERLAY_DESTINATION = 0x32512C
APPLICATION_RESOURCE_DRIVER_OVERLAY_SOURCE = 0x4F512C
APPLICATION_RESOURCE_DRIVER_OVERLAY_SIZE = 0x0072
APPLICATION_FILE_ATTACH_OVERLAY_DESTINATION = 0x2EBE2E
APPLICATION_FILE_ATTACH_OVERLAY_SOURCE = 0x4BBE2E
APPLICATION_FILE_ATTACH_OVERLAY_SIZE = 0x016C
APPLICATION_FILE_WRAPPER_OVERLAY_DESTINATION = 0x30C99E
APPLICATION_FILE_WRAPPER_OVERLAY_SOURCE = 0x4DC99E
APPLICATION_FILE_WRAPPER_OVERLAY_SIZE = 0x00E6
# Exact source 46:F732 passes several far literals in logical segment 31 to
# the wrapper above.  Flat 31:937C is unrelated executable code, while the
# matching +0x1D PRG source range contains the complete GBK messages, version,
# product name, and ``0:\\USERINFO.SYS`` path.  The SoC exposes a separate
# writable data-bus RAM view at 31:937C; retain the vendor constants by having
# the reconstructed guest installer copy them there before the late path runs.
APPLICATION_USERINFO_LITERAL_OVERLAY_DESTINATION = 0x31937C
APPLICATION_USERINFO_LITERAL_OVERLAY_SOURCE = 0x4E937C
APPLICATION_USERINFO_LITERAL_OVERLAY_SIZE = 0x00AA
# One original caller of resident 18:21F4 is the complete source-4B function
# at D34A.  It accepts a resource descriptor far pointer, opens/records the
# associated FILE objects, primes A0:7090/72D8/72DC/7DEE, and then calls the
# launch manager with two null optional contexts.  Restore its whole bounded
# call closure below; otherwise several linked targets are unrelated flat-body
# fragments and return through frames they do not own.
APPLICATION_LAUNCH_SEQUENCE_OVERLAY_DESTINATION = 0x2ED34A
APPLICATION_LAUNCH_SEQUENCE_OVERLAY_SOURCE = 0x4BD34A
APPLICATION_LAUNCH_SEQUENCE_OVERLAY_SIZE = 0x0164
APPLICATION_LAUNCH_FILE_STATE_OVERLAY_DESTINATION = 0x30C370
APPLICATION_LAUNCH_FILE_STATE_OVERLAY_SOURCE = 0x4DC370
APPLICATION_LAUNCH_FILE_STATE_OVERLAY_SIZE = 0x00E4
APPLICATION_LAUNCH_INPUT_MASKS_OVERLAY_DESTINATION = 0x32B8D0
APPLICATION_LAUNCH_INPUT_MASKS_OVERLAY_SOURCE = 0x4FB8D0
APPLICATION_LAUNCH_INPUT_MASKS_OVERLAY_SIZE = 0x0052
APPLICATION_LAUNCH_RESOURCE_RELEASE_OVERLAY_DESTINATION = 0x32AA26
APPLICATION_LAUNCH_RESOURCE_RELEASE_OVERLAY_SOURCE = 0x4FAA26
APPLICATION_LAUNCH_RESOURCE_RELEASE_OVERLAY_SIZE = 0x0004
APPLICATION_LAUNCH_RECORD_APPLY_OVERLAY_DESTINATION = 0x2D1D22
APPLICATION_LAUNCH_RECORD_APPLY_OVERLAY_SOURCE = 0x4A1D22
APPLICATION_LAUNCH_RECORD_APPLY_OVERLAY_SIZE = 0x01CC
APPLICATION_LAUNCH_UI_RESET_OVERLAY_DESTINATION = 0x32F2D0
APPLICATION_LAUNCH_UI_RESET_OVERLAY_SOURCE = 0x4FF2D0
APPLICATION_LAUNCH_UI_RESET_OVERLAY_SIZE = 0x003E
APPLICATION_LAUNCH_DEVICE_8040_OVERLAY_DESTINATION = 0x328394
APPLICATION_LAUNCH_DEVICE_8040_OVERLAY_SOURCE = 0x4F8394
APPLICATION_LAUNCH_DEVICE_8040_OVERLAY_SIZE = 0x0064
APPLICATION_LAUNCH_DEVICE_8010_OVERLAY_DESTINATION = 0x323032
APPLICATION_LAUNCH_DEVICE_8010_OVERLAY_SOURCE = 0x4F3032
APPLICATION_LAUNCH_DEVICE_8010_OVERLAY_SIZE = 0x0080

# These six source-50 leaves are already in the bank that later becomes
# writable application RAM.  Embed their shipped words in the resident
# installer rather than trying to copy from the live source addresses.
APPLICATION_LAUNCH_UI_SYNC_OVERLAY_DESTINATION = 0x3365DE
APPLICATION_LAUNCH_UI_SYNC_OVERLAY_SOURCE = 0x5065DE
APPLICATION_LAUNCH_UI_SYNC_OVERLAY_SIZE = 0x000A
APPLICATION_LAUNCH_POST_STATE_OVERLAY_DESTINATION = 0x336EE2
APPLICATION_LAUNCH_POST_STATE_OVERLAY_SOURCE = 0x506EE2
APPLICATION_LAUNCH_POST_STATE_OVERLAY_SIZE = 0x0006
APPLICATION_LAUNCH_DEVICE_CLEANUP_OVERLAY_DESTINATION = 0x33662E
APPLICATION_LAUNCH_DEVICE_CLEANUP_OVERLAY_SOURCE = 0x50662E
APPLICATION_LAUNCH_DEVICE_CLEANUP_OVERLAY_SIZE = 0x000A
APPLICATION_LAUNCH_POWER_CHECK_OVERLAY_DESTINATION = 0x332792
APPLICATION_LAUNCH_POWER_CHECK_OVERLAY_SOURCE = 0x502792
APPLICATION_LAUNCH_POWER_CHECK_OVERLAY_SIZE = 0x0028
APPLICATION_LAUNCH_DEVICE_FALLBACK_OVERLAY_DESTINATION = 0x33664C
APPLICATION_LAUNCH_DEVICE_FALLBACK_OVERLAY_SOURCE = 0x50664C
APPLICATION_LAUNCH_DEVICE_FALLBACK_OVERLAY_SIZE = 0x000A
APPLICATION_LAUNCH_BIT_CLEAR_OVERLAY_DESTINATION = 0x335B00
APPLICATION_LAUNCH_BIT_CLEAR_OVERLAY_SOURCE = 0x505B00
APPLICATION_LAUNCH_BIT_CLEAR_OVERLAY_SIZE = 0x000E

APPLICATION_LAUNCH_COPY_OVERLAYS = (
    (APPLICATION_LAUNCH_SEQUENCE_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_SEQUENCE_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_SEQUENCE_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_FILE_STATE_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_FILE_STATE_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_FILE_STATE_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_INPUT_MASKS_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_INPUT_MASKS_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_INPUT_MASKS_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_RESOURCE_RELEASE_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_RESOURCE_RELEASE_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_RESOURCE_RELEASE_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_RECORD_APPLY_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_RECORD_APPLY_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_RECORD_APPLY_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_UI_RESET_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_UI_RESET_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_UI_RESET_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_DEVICE_8040_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_DEVICE_8040_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_DEVICE_8040_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_DEVICE_8010_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_DEVICE_8010_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_DEVICE_8010_OVERLAY_SIZE),
)
APPLICATION_LAUNCH_EMBEDDED_OVERLAYS = (
    (APPLICATION_LAUNCH_UI_SYNC_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_UI_SYNC_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_UI_SYNC_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_POST_STATE_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_POST_STATE_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_POST_STATE_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_DEVICE_CLEANUP_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_DEVICE_CLEANUP_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_DEVICE_CLEANUP_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_POWER_CHECK_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_POWER_CHECK_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_POWER_CHECK_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_DEVICE_FALLBACK_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_DEVICE_FALLBACK_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_DEVICE_FALLBACK_OVERLAY_SIZE),
    (APPLICATION_LAUNCH_BIT_CLEAR_OVERLAY_DESTINATION,
     APPLICATION_LAUNCH_BIT_CLEAR_OVERLAY_SOURCE,
     APPLICATION_LAUNCH_BIT_CLEAR_OVERLAY_SIZE),
)
# 4D:C99E's first wrapper is a tail jump to 31:339A.  The flat destination,
# and both of its direct callees, are unrelated mid-function bytes.  The
# shipped PRG contains complete same-PC implementations one segment-family
# higher.  The record scanner in turn depends on the exact resource parser
# and two call-free byte helpers below; all ranges have balanced LINK/RETS
# boundaries and gap-free intra-procedural control flow.
APPLICATION_FILE_OBJECT_OPEN_OVERLAY_DESTINATION = 0x31339A
APPLICATION_FILE_OBJECT_OPEN_OVERLAY_SOURCE = 0x4E339A
APPLICATION_FILE_OBJECT_OPEN_OVERLAY_SIZE = 0x00C4
APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_DESTINATION = 0x31E022
APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_SOURCE = 0x4EE022
APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_SIZE = 0x0096
APPLICATION_POINTER_CLASSIFY_OVERLAY_DESTINATION = 0x2F2FE0
APPLICATION_POINTER_CLASSIFY_OVERLAY_SOURCE = 0x4C2FE0
APPLICATION_POINTER_CLASSIFY_OVERLAY_SIZE = 0x014E
APPLICATION_FILE_RECORD_SCAN_OVERLAY_DESTINATION = 0x2DD93C
APPLICATION_FILE_RECORD_SCAN_OVERLAY_SOURCE = 0x4AD93C
APPLICATION_FILE_RECORD_SCAN_OVERLAY_SIZE = 0x019E
# The exact record scanner above delegates to logical 20:76CA.  Flat
# 20:76CA is a suffix of an unrelated 20:70xx function (it starts with BCLR,
# has no LINK, and eventually returns success through 20:833E without writing
# the caller's record).  Source 3D:76CA is the complete same-PC LINK #0x0B
# directory-record resolver through UNLINK/RETS at 3D:7C52/3D:7C54.
APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_DESTINATION = 0x2076CA
APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_SOURCE = 0x3D76CA
APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_SIZE = 0x058C
# Its source-proven capacity fallback targets the collision-prone 20:F928
# routine already retained at 5F:F928.  Retarget the copied call in place.
APPLICATION_FILE_RECORD_RESOLVE_SECTOR_PROBE_CALL = 0x207B44
APPLICATION_FILE_RECORD_RESOLVE_SECTOR_PROBE_CALL_SOURCE = 0x3D7B44
# File creation reaches this no-argument state reset through 2A:5C16.  Flat
# 32:9866 is an unrelated mid-function fragment and returns after consuming
# its caller's frame; 4F:9866 is the complete balanced same-PC body.
APPLICATION_FILE_CREATE_STATE_OVERLAY_DESTINATION = 0x329866
APPLICATION_FILE_CREATE_STATE_OVERLAY_SOURCE = 0x4F9866
APPLICATION_FILE_CREATE_STATE_OVERLAY_SIZE = 0x005E
# The file-create continuation calls logical 29:21F8 as a normal framed
# routine.  The flat destination is a middle fragment with no LINK and can
# eventually return through 29:2790 with its caller's frame consumed.  The
# same-PC body at 46:21F8 is the complete source-proven function, bounded by
# LINK #0x38 and UNLINK/RETS at 46:24C2..24C4.
APPLICATION_FILE_CREATE_RECORD_OVERLAY_DESTINATION = 0x2921F8
APPLICATION_FILE_CREATE_RECORD_OVERLAY_SOURCE = 0x4621F8
APPLICATION_FILE_CREATE_RECORD_OVERLAY_SIZE = 0x02CE
# The record builder calls logical 32:E560.  Its flat bytes are another
# mid-function fragment that runs as far as 32:F0EC before consuming the
# caller's frame.  NP560.PRG's same-PC 4F:E560 body is a bounded LINK #0
# wrapper ending at 4F:E5A0.
APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_DESTINATION = 0x32E560
APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_SOURCE = 0x4FE560
APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_SIZE = 0x0042
# 4F:E560's second child is linked 32:C1A6.  That address must retain a live
# fall-through from the large flat 32:Bxxx worker, so the complete entry has
# already been relocated to 5F:C1A6.  Retarget only this recovered caller.
APPLICATION_FILE_CREATE_VALIDATE_REGISTRY_ENTRY_CALL = 0x32E588
APPLICATION_FILE_CREATE_VALIDATE_REGISTRY_ENTRY_CALL_SOURCE = 0x4FE588
# The exact storage-context routine at 25:5460 calls logical 29:16B0.  Flat
# 29:16B0 is an unframed continuation which consumes nested call frames;
# source 46:16B0 is the complete LINK #5 function through 46:1982.
APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_DESTINATION = 0x2916B0
APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_SOURCE = 0x4616B0
APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_SIZE = 0x02D4
APPLICATION_STORAGE_CONTEXT_RESOLVE_SECTOR_PROBE_CALL = 0x2918B6
APPLICATION_STORAGE_CONTEXT_RESOLVE_SECTOR_PROBE_CALL_SOURCE = 0x4618B6
# The relocated registry-entry creator calls linked 21:BF4E.  Flat 21:BF4E
# starts mid-function and its UNLINK consumes the registry creator's frame.
# Source 3E:BF4E is complete through 3E:C484, including a synthesized callback
# return at C45C.  Preserve the collision-prone flat body by copying the exact
# function to the same PC in free segment 5C and patch its embedded callback
# continuation segment from logical 21 to relocated 5C.
APPLICATION_FILE_ENTRY_BUILD_LINKED_DESTINATION = 0x21BF4E
APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION = 0x5CBF4E
APPLICATION_FILE_ENTRY_BUILD_OVERLAY_SOURCE = 0x3EBF4E
APPLICATION_FILE_ENTRY_BUILD_OVERLAY_SIZE = 0x0538
APPLICATION_FILE_ENTRY_BUILD_CALL = 0x5FC1E2
APPLICATION_FILE_ENTRY_BUILD_CALL_SOURCE = 0x4FC1E2
APPLICATION_FILE_ENTRY_BUILD_CALLBACK_SEGMENT = 0x5CC454
APPLICATION_FILE_ENTRY_BUILD_CALLBACK_SEGMENT_SOURCE = 0x3EC454
# Both the file-entry builder and resident fopen call logical 2F:5CDC with a
# single far record pointer.  Flat 2F:5CDC starts mid-function (0xFFEE), has
# no LINK, and consumes its caller's frame.  Source 4C:5CDC is the only
# same-PC ABI match: LINK #2, the same one-far-pointer argument, two closed
# child calls, and a balanced return at 4C:5E1E.  Keep it at the same PC in a
# collision-free application bank so its internal absolute AJMPs stay exact.
APPLICATION_FILE_RECORD_STATUS_LINKED_DESTINATION = 0x2F5CDC
APPLICATION_FILE_RECORD_STATUS_OVERLAY_DESTINATION = 0x5D5CDC
APPLICATION_FILE_RECORD_STATUS_OVERLAY_SOURCE = 0x4C5CDC
APPLICATION_FILE_RECORD_STATUS_OVERLAY_SIZE = 0x0144
APPLICATION_FILE_RECORD_STATUS_CALLS = (
    (0x5CC0A2, 0x3EC0A2),
    (0x1F221E, 0x3C221E),
)
APPLICATION_FILE_RECORD_STATUS_SELECT_CALL = 0x5D5D78
APPLICATION_FILE_RECORD_STATUS_SELECT_CALL_SOURCE = 0x4C5D78
# Its second child has the same collision pattern at logical 2A:E3A6.
# Source 47:E3A6 is the sole complete same-PC LINK #3 implementation.  It
# uses two callback continuations, so preserve its PC in segment 5D and patch
# only the saved callback segment words.  Its collided storage pair/driver
# children already have exact resident copies in the 07:4000 closure.
APPLICATION_FILE_RECORD_APPLY_LINKED_DESTINATION = 0x2AE3A6
APPLICATION_FILE_RECORD_APPLY_OVERLAY_DESTINATION = 0x5DE3A6
APPLICATION_FILE_RECORD_APPLY_OVERLAY_SOURCE = 0x47E3A6
APPLICATION_FILE_RECORD_APPLY_OVERLAY_SIZE = 0x0250
APPLICATION_FILE_RECORD_APPLY_CALL = 0x5D5E0C
APPLICATION_FILE_RECORD_APPLY_CALL_SOURCE = 0x4C5E0C
APPLICATION_FILE_RECORD_APPLY_PAIR_CALL = 0x5DE426
APPLICATION_FILE_RECORD_APPLY_PAIR_CALL_SOURCE = 0x47E426
APPLICATION_FILE_RECORD_APPLY_DRIVER_CALL = 0x5DE43C
APPLICATION_FILE_RECORD_APPLY_DRIVER_CALL_SOURCE = 0x47E43C
APPLICATION_FILE_RECORD_APPLY_CALLBACK_SEGMENTS = (
    (0x5DE550, 0x47E550),
    (0x5DE5CC, 0x47E5CC),
)
# Close/commit at 24:EAEC calls logical 30:6D9E to copy the active storage
# state into its per-file descriptor.  Flat 30:6D9E is a large-function
# suffix: its RETS at 30:6FEA consumes the close frame and returns directly
# to the provision wrapper.  Source 4D:6D9E is the complete call-free LINK #0
# function through 4D:6E9C.  Preserve it in collision-free bank 5D and
# retarget only the source-proven close call.
APPLICATION_FILE_CLOSE_STATE_LINKED_DESTINATION = 0x306D9E
APPLICATION_FILE_CLOSE_STATE_OVERLAY_DESTINATION = 0x5D6D9E
APPLICATION_FILE_CLOSE_STATE_OVERLAY_SOURCE = 0x4D6D9E
APPLICATION_FILE_CLOSE_STATE_OVERLAY_SIZE = 0x0100
APPLICATION_FILE_CLOSE_STATE_CALL = 0x24EC7A
APPLICATION_FILE_CLOSE_STATE_CALL_SOURCE = 0x41EC7A
# The next close child has the same collision at logical 27:06C4: flat
# application bytes are table data, while source 44:06C4 is the complete
# LINK #4 record-sync function through 44:0A24.  Its direct children are
# already recovered by the application-main closure.  Relocate it at the
# same PC in bank 5D so its internal AJMP offsets remain unchanged.
APPLICATION_FILE_CLOSE_RECORD_SYNC_LINKED_DESTINATION = 0x2706C4
APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_DESTINATION = 0x5D06C4
APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_SOURCE = 0x4406C4
APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_SIZE = 0x0362
APPLICATION_FILE_CLOSE_RECORD_SYNC_CALL = 0x24ED22
APPLICATION_FILE_CLOSE_RECORD_SYNC_CALL_SOURCE = 0x41ED22
# Both resident fopen and close/commit call logical 23:7584.  Flat 23:7584
# begins mid-function and returns through its caller's frame; source 40:7584
# is the complete LINK #8 descriptor/record update body through 40:7A24.
# Relocate it at the same PC in bank 5D and repair its four constructed
# callback return-frame segment words from logical 23 to relocated 5D.
APPLICATION_FILE_METADATA_UPDATE_LINKED_DESTINATION = 0x237584
APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION = 0x5D7584
APPLICATION_FILE_METADATA_UPDATE_OVERLAY_SOURCE = 0x407584
APPLICATION_FILE_METADATA_UPDATE_OVERLAY_SIZE = 0x04A2
APPLICATION_FILE_METADATA_UPDATE_CALLS = (
    (0x1F225A, 0x3C225A),
    (0x24EDDE, 0x41EDDE),
)
APPLICATION_FILE_METADATA_UPDATE_CALLBACK_SEGMENTS = (
    (0x5D7734, 0x407734),
    (0x5D77A4, 0x4077A4),
    (0x5D7940, 0x407940),
    (0x5D79B0, 0x4079B0),
)
APPLICATION_FILE_CLOSE_DRIVER_CALL = 0x24ED46
APPLICATION_FILE_CLOSE_DRIVER_CALL_SOURCE = 0x41ED46
# File-entry construction descends through logical 2E:787E.  Flat 2E:787E
# is a suffix of the surrounding storage worker and eventually UNLINKs the
# caller frame at 2E:8740.  Source 4B:787E is the bounded LINK #0E function.
# Its record builder and initial query leaves are unconditional direct calls,
# so install that source-proven closure in the same cold-boot pass.
APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_DESTINATION = 0x2E787E
APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_SOURCE = 0x4B787E
APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_SIZE = 0x017C
APPLICATION_FILE_RECORD_BUILD_OVERLAY_DESTINATION = 0x237EC6
APPLICATION_FILE_RECORD_BUILD_OVERLAY_SOURCE = 0x407EC6
APPLICATION_FILE_RECORD_BUILD_OVERLAY_SIZE = 0x049E
APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_DESTINATION = 0x320A56
APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_SOURCE = 0x4F0A56
APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_SIZE = 0x008A
APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_DESTINATION = 0x3209CC
APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_SOURCE = 0x4F09CC
APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_SIZE = 0x008A
APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_DESTINATION = 0x328330
APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_SOURCE = 0x4F8330
APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_SIZE = 0x0064
APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_DESTINATION = 0x3350A4
APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_SOURCE = 0x5050A4
APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_SIZE = 0x0014
APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_DESTINATION = 0x33507C
APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_SOURCE = 0x50507C
APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_SIZE = 0x0014
APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_DESTINATION = 0x3366EC
APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_SOURCE = 0x5066EC
APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_SIZE = 0x000A
APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_DESTINATION = 0x33673C
APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_SOURCE = 0x50673C
APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_SIZE = 0x000A
APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_DESTINATION = 0x28D7E2
APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_SOURCE = 0x45D7E2
APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_SIZE = 0x02E2
APPLICATION_BYTE_CLASSIFY_OVERLAY_DESTINATION = 0x31D288
APPLICATION_BYTE_CLASSIFY_OVERLAY_SOURCE = 0x4ED288
APPLICATION_BYTE_CLASSIFY_OVERLAY_SIZE = 0x009A
# 4E:D288 rejects the sixteen punctuation bytes stored at 50:3B86.  The
# logical 33:3B86 destination otherwise contains unrelated code, causing
# ordinary ASCII path components (for example ``lirt``) to be rejected.
# Segment 50 is mutable by the time the late installer runs, so retain the
# exact table bytes inside the reconstructed loader.
APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_DESTINATION = 0x333B86
APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_SOURCE = 0x503B86
APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_SIZE = 0x0010
APPLICATION_ASCII_LOWER_OVERLAY_DESTINATION = 0x334588
APPLICATION_ASCII_LOWER_OVERLAY_SOURCE = 0x504588
APPLICATION_ASCII_LOWER_OVERLAY_SIZE = 0x001A
# These callees are installed only after banks 4E..50 have become mutable.
# In particular, copying 50:4588 through the live data bus reads cleared RAM
# and leaves 33:4588 as zero words; the path parser then falls through into
# unrelated code instead of returning at 33:45A0.  Retain every vulnerable
# small dependency as exact PRG words in the resident installer.
APPLICATION_FILE_RECORD_EMBEDDED_DESTINATIONS = frozenset((
    APPLICATION_FILE_CLOSE_STATE_OVERLAY_DESTINATION,
    APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_DESTINATION,
    APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_DESTINATION,
    APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_DESTINATION,
    APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_DESTINATION,
    APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_DESTINATION,
    APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_DESTINATION,
    APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_DESTINATION,
    APPLICATION_ASCII_LOWER_OVERLAY_DESTINATION,
))
FAR_STRING_COPY_OVERLAY_DESTINATION = 0x32945C
FAR_STRING_COPY_OVERLAY_SOURCE = 0x4F945C
FAR_STRING_COPY_OVERLAY_SIZE = 0x005E
FAR_MEMORY_COPY_OVERLAY_DESTINATION = 0x2E4572
FAR_MEMORY_COPY_OVERLAY_SOURCE = 0x4B4572
FAR_MEMORY_COPY_OVERLAY_SIZE = 0x0184
# The manager-table insertion path at 26:39B4 and the text-buffer compactor
# at 26:A530 both pass five words to 31:7824 and remove ten argument bytes.
# In both cases the first two far pointers already address the final byte of
# their respective ranges.  The manager call moves an existing ten-byte
# record one slot upward, proving that this is the overlap-safe descending
# counterpart to the forward far-copy services at 08:43A6 and 18:6D56.
# Flat 31:7824 is unrelated application code and none of the shipped source
# banks contains a complete same-PC body, so install a clean-room DMCU guest
# implementation into the evidenced writable executable-overlay address.
REVERSE_FAR_MEMMOVE_OVERLAY_DESTINATION = 0x317824
# Resident event packet 1C:F28A copies four short labels into eight-byte
# stack locals.  Their flat 32:E86E bytes are unrelated code, while the
# same offsets in overlay segment 4F contain the intended NUL-terminated
# strings.  Restore the complete static-data island through 32:E8AF.
APPLICATION_EVENT_TEXT_DATA_OVERLAY_DESTINATION = 0x32E86E
APPLICATION_EVENT_TEXT_DATA_OVERLAY_SOURCE = 0x4FE86E
APPLICATION_EVENT_TEXT_DATA_OVERLAY_SIZE = 0x0042
# Resident event renderer 10:5090 calls 22:E0BE as a normal two-word helper,
# but the flat destination begins mid-function.  Source 3F:E0BE is the
# complete LINK #6 body with 448 reachable instructions and one RETS.
APPLICATION_EVENT_RENDER_HELPER_OVERLAY_DESTINATION = 0x22E0BE
APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SOURCE = 0x3FE0BE
APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SIZE = 0x04DA
# The exact 28:1F08 text loop calls this three-word glyph renderer.  The
# flat 28:FD38 bytes are an unrelated in-function fragment, while the
# complete same-PC copy at 45:FD38 starts with LINK #5 and occupies the
# remainder of its source segment through a RETS at 45:FFFE.
APPLICATION_GLYPH_DRAW_OVERLAY_DESTINATION = 0x28FD38
APPLICATION_GLYPH_DRAW_OVERLAY_SOURCE = 0x45FD38
APPLICATION_GLYPH_DRAW_OVERLAY_SIZE = 0x02C8
CHARACTER_DRAW_OVERLAY_DESTINATION = 0x327C0E
CHARACTER_DRAW_OVERLAY_SOURCE = 0x4F7C0E
CHARACTER_DRAW_OVERLAY_SIZE = 0x0066
FAR_STRING_CONCAT_OVERLAY_DESTINATION = 0x328204
FAR_STRING_CONCAT_OVERLAY_SOURCE = 0x4F8204
FAR_STRING_CONCAT_OVERLAY_SIZE = 0x0064
# The flat 32:8268 bytes continue into an unrelated formatter body.  The
# updater keeps the complete seven-word wrapper at the same PC in segment 4F;
# its sole callee likewise has a complete same-PC copy at 3F:FD9E.
RECORD_LAYOUT_WRAPPER_OVERLAY_DESTINATION = 0x328268
RECORD_LAYOUT_WRAPPER_OVERLAY_SOURCE = 0x4F8268
RECORD_LAYOUT_WRAPPER_OVERLAY_SIZE = 0x0064
RECORD_LAYOUT_BUILD_OVERLAY_DESTINATION = 0x22FD9E
RECORD_LAYOUT_BUILD_OVERLAY_SOURCE = 0x3FFD9E
RECORD_LAYOUT_BUILD_OVERLAY_SIZE = 0x0260
# The flat 31:C224 entry is another body fragment sharing 31:C762's epilogue;
# its exact same-PC source is a complete one-word input-mask dispatcher.  Its
# six branches all call the adjacent exact table-bit updater at 31:5014.
APPLICATION_INPUT_MASK_OVERLAY_DESTINATION = 0x31C224
APPLICATION_INPUT_MASK_OVERLAY_SOURCE = 0x4EC224
APPLICATION_INPUT_MASK_OVERLAY_SIZE = 0x009E
INPUT_MASK_APPLY_OVERLAY_DESTINATION = 0x315014
INPUT_MASK_APPLY_OVERLAY_SOURCE = 0x4E5014
INPUT_MASK_APPLY_OVERLAY_SIZE = 0x00BC
# The application loop's 30:8C1C call otherwise enters a large flat function
# body and eventually returns through the unrelated 30:9442 epilogue.  The
# segment-4D same-PC copy is the complete allocator-state initializer: it
# clears the 51:4A40..52:3A3F arena, resets its list head and descriptor
# bitmap, and publishes 52:3A40 through A2:29A0/29A2.
APPLICATION_DISPLAY_STATE_OVERLAY_DESTINATION = 0x308C1C
APPLICATION_DISPLAY_STATE_OVERLAY_SOURCE = 0x4D8C1C
APPLICATION_DISPLAY_STATE_OVERLAY_SIZE = 0x00F6
# The late screen setup path calls 32:8E5C with no arguments. Flat bytes are
# a frame-less large-function suffix ending at 32:8F1E; source 4F:8E5C is the
# complete LINK #0 display/mode reset wrapper through 4F:8EBC.
APPLICATION_DISPLAY_RESET_OVERLAY_DESTINATION = 0x328E5C
APPLICATION_DISPLAY_RESET_OVERLAY_SOURCE = 0x4F8E5C
APPLICATION_DISPLAY_RESET_OVERLAY_SIZE = 0x0062
# The application resource driver calls 30:8B26 twice.  The flat destination
# is an in-function fragment that eventually reaches 30:9442's unrelated
# epilogue; the same-PC source at 4D:8B26 is the complete list-state worker.
# The adjacent one-item setter wrapper at 33:4D2A also calls flat 30:3A56.
# That destination begins in the middle of another large routine and returns
# through 30:3892, skipping the wrapper's own epilogue.  Source 4D:3A56 is the
# complete LINK #4 implementation and uses the same already-recovered
# 31:8ABC/27:6100 dependency pair.  Keep the complete, bounded dependency
# closure alongside both list workers.
APPLICATION_LIST_STATE_OVERLAY_DESTINATION = 0x308B26
APPLICATION_LIST_STATE_OVERLAY_SOURCE = 0x4D8B26
APPLICATION_LIST_STATE_OVERLAY_SIZE = 0x00F6
APPLICATION_LIST_ITEM_SET_OVERLAY_DESTINATION = 0x303A56
APPLICATION_LIST_ITEM_SET_OVERLAY_SOURCE = 0x4D3A56
APPLICATION_LIST_ITEM_SET_OVERLAY_SIZE = 0x010C
APPLICATION_TABLE_MASK_OVERLAY_DESTINATION = 0x318ABC
APPLICATION_TABLE_MASK_OVERLAY_SOURCE = 0x4E8ABC
APPLICATION_TABLE_MASK_OVERLAY_SIZE = 0x00AE
APPLICATION_LIST_COMPACT_OVERLAY_DESTINATION = 0x276100
APPLICATION_LIST_COMPACT_OVERLAY_SOURCE = 0x446100
APPLICATION_LIST_COMPACT_OVERLAY_SIZE = 0x034A
APPLICATION_LIST_CURSOR_OVERLAY_DESTINATION = 0x30699A
APPLICATION_LIST_CURSOR_OVERLAY_SOURCE = 0x4D699A
APPLICATION_LIST_CURSOR_OVERLAY_SIZE = 0x0102
APPLICATION_RANGE_FLAG_OVERLAY_DESTINATION = 0x323332
APPLICATION_RANGE_FLAG_OVERLAY_SOURCE = 0x4F3332
APPLICATION_RANGE_FLAG_OVERLAY_SIZE = 0x007E
APPLICATION_DEVICE_VALIDATION_OVERLAY_DESTINATION = 0x2AA6F6
APPLICATION_DEVICE_VALIDATION_OVERLAY_SOURCE = 0x47A6F6
APPLICATION_DEVICE_VALIDATION_OVERLAY_SIZE = 0x025C
# The exact validation path at 31:F2D4 calls linked 29:3DD2.  Flat 29:3DD2
# starts at an argument setup in the middle of an unrelated application body,
# so its eventual RETS consumes data as a far-return frame.  Source 46:3DD2
# is the complete LINK #0 low-level event/timer helper with closed branches
# and a balanced return at 46:4094.
APPLICATION_RESIDENT_EVENT_OVERLAY_DESTINATION = 0x293DD2
APPLICATION_RESIDENT_EVENT_OVERLAY_SOURCE = 0x463DD2
APPLICATION_RESIDENT_EVENT_OVERLAY_SIZE = 0x02C4
# 32:C476 calls linked 33:4342 while validating an application record.  Its
# flat destination is an argument-building fragment in a large parser and
# reaches that parser's epilogue without owning its frame.  Source 50:4342 is
# the exact complete digit predicate (ASCII '0'..'9') expected by the caller.
APPLICATION_ASCII_DIGIT_OVERLAY_DESTINATION = 0x334342
APPLICATION_ASCII_DIGIT_OVERLAY_SOURCE = 0x504342
APPLICATION_ASCII_DIGIT_OVERLAY_SIZE = 0x001C
# After the event loop, 31:F304 calls linked 32:C476 with one far-pointer
# argument.  Flat 32:C476 is another interior parser fragment (the path which
# exposed 33:4342 above), while 4F:C476 is the exact LINK #2 post-event worker
# with a closed dependency sequence and balanced return at 4F:C4C4.
APPLICATION_EVENT_POSTPROCESS_OVERLAY_DESTINATION = 0x32C476
APPLICATION_EVENT_POSTPROCESS_OVERLAY_SOURCE = 0x4FC476
APPLICATION_EVENT_POSTPROCESS_OVERLAY_SIZE = 0x0050
# The checksum helper calls linked 31:F162 for its byte-wise CRC16 update.
# Flat 31:F162 is a display-call fragment which runs through 31:F280 and then
# falls into the separately restored modal loop at 31:F282.  Source 4E:F162
# is the exact call-free LINK #2 CRC loop with a balanced 4E:F1F0 return.
APPLICATION_VALIDATION_CRC16_OVERLAY_DESTINATION = 0x31F162
APPLICATION_VALIDATION_CRC16_OVERLAY_SOURCE = 0x4EF162
APPLICATION_VALIDATION_CRC16_OVERLAY_SIZE = 0x0090
# The validation body calls linked 32:5ACC with a byte range and an initial
# accumulator.  Flat 32:5ACC is a conditional branch in an unrelated parser;
# source 4F:5ACC is the complete LINK #0 checksum loop and returns at 4F:5B38.
APPLICATION_VALIDATION_CHECKSUM_OVERLAY_DESTINATION = 0x325ACC
APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SOURCE = 0x4F5ACC
APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SIZE = 0x006E
APPLICATION_RESOURCE_LOOKUP_OVERLAY_DESTINATION = 0x24EAEC
APPLICATION_RESOURCE_LOOKUP_OVERLAY_SOURCE = 0x41EAEC
APPLICATION_RESOURCE_LOOKUP_OVERLAY_SIZE = 0x041A
# 31:3F30 calls 2A:6852 with four argument bytes on the stack.  In the flat
# image that address is the middle of another function and immediately takes
# its large epilogue, consuming the caller's return frame.  The same-PC body
# at 47:6852 is a complete LINK/UNLINK function ending at 47:6AC2.
APPLICATION_RESOURCE_DECODE_OVERLAY_DESTINATION = 0x2A6852
APPLICATION_RESOURCE_DECODE_OVERLAY_SOURCE = 0x476852
APPLICATION_RESOURCE_DECODE_OVERLAY_SIZE = 0x0272
# The resource decoder reaches 32:DB08 through 30:2FC8/32:B63C.  Flat
# 32:DB08 is another in-function fragment and falls into the independently
# installed 32:DC20 initializer, whose RETS consumes the wrong frame.  The
# segment-4F same-PC function has a complete 70-byte LINK/UNLINK body.
APPLICATION_RESOURCE_OPEN_OVERLAY_DESTINATION = 0x32DB08
APPLICATION_RESOURCE_OPEN_OVERLAY_SOURCE = 0x4FDB08
APPLICATION_RESOURCE_OPEN_OVERLAY_SIZE = 0x0046
# The drawing-context path calls 32:DA7C.  Its flat body is a fragment of a
# large byte initializer and eventually falls straight into the independently
# installed 32:DB08 function without a call frame.  Source 4F:DA7C is the
# complete LINK #2 factory and returns before that adjacent function.
APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_DESTINATION = 0x32DA7C
APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SOURCE = 0x4FDA7C
APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SIZE = 0x0046
# Flat 32:B63C is a suffix of the large resource decoder and inherits its
# caller's frame before entering 32:DB08.  The exact 4F:B63C wrapper is a
# closed LINK #0 function.  Its first child is likewise absent at 2E:AB96;
# source 4B:AB96 supplies the complete LINK #7 coordinate mapper.
APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_DESTINATION = 0x32B63C
APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SOURCE = 0x4FB63C
APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SIZE = 0x0054
APPLICATION_RESOURCE_COORDINATE_OVERLAY_DESTINATION = 0x2EAB96
APPLICATION_RESOURCE_COORDINATE_OVERLAY_SOURCE = 0x4BAB96
APPLICATION_RESOURCE_COORDINATE_OVERLAY_SIZE = 0x0170
INT32_DIVIDE_WRAPPER_OVERLAY_DESTINATION = 0x332512
INT32_DIVIDE_WRAPPER_OVERLAY_SOURCE = 0x502512
INT32_DIVIDE_WRAPPER_OVERLAY_SIZE = 0x0028
INT32_DIVIDE_OVERLAY_DESTINATION = 0x321BD8
INT32_DIVIDE_OVERLAY_SOURCE = 0x4F1BD8
INT32_DIVIDE_OVERLAY_SIZE = 0x0086
# Callers use 32:86B4 to convert a signed 16-bit operand into the firmware's
# four-word wide representation.  The flat destination is a preceding body
# fragment that falls into 32:8716 without its own frame; 4F:86B4 is the
# complete framed converter through its 32:8708 RETS.  Its 0x8000 special
# case occupies the following six words at 32:870A..8714 and branches back to
# that epilogue, so those words are part of the exact function too.
WIDE_FROM_INT16_OVERLAY_DESTINATION = 0x3286B4
WIDE_FROM_INT16_OVERLAY_SOURCE = 0x4F86B4
WIDE_FROM_INT16_OVERLAY_SIZE = 0x0062
WIDE_COMPARE_OVERLAY_DESTINATION = 0x328716
WIDE_COMPARE_OVERLAY_SOURCE = 0x4F8716
WIDE_COMPARE_OVERLAY_SIZE = 0x0062
WIDE_OPERATION_DISPATCH_OVERLAY_DESTINATION = 0x32D218
WIDE_OPERATION_DISPATCH_OVERLAY_SOURCE = 0x4FD218
WIDE_OPERATION_DISPATCH_OVERLAY_SIZE = 0x0048
# Four five-word callers use 32:136C as an application compare/mode wrapper.
# Flat 32:136C begins in the middle of a large routine and eventually reaches
# the shared 2E:2E82 epilogue, leaking one caller frame per foreground pass.
# Source 4F:136C is the exact LINK #2 implementation with a balanced return at
# 4F:13E2 and the same external call/argument contract.
APPLICATION_COMPARE_MODE_OVERLAY_DESTINATION = 0x32136C
APPLICATION_COMPARE_MODE_OVERLAY_SOURCE = 0x4F136C
APPLICATION_COMPARE_MODE_OVERLAY_SIZE = 0x0078
WIDE_ARITHMETIC_OVERLAY_DESTINATION = 0x2A7BD2
WIDE_ARITHMETIC_OVERLAY_SOURCE = 0x477BD2
WIDE_ARITHMETIC_OVERLAY_SIZE = 0x026C
# 2C:77D2 calls 32:E72E directly during UI state comparisons. Flat 32:E72E
# is an unrelated dispatcher; 4F:E72E is the real prefix and tail-jumps into
# the already recovered 2A:7BD2 wide-arithmetic implementation.
WIDE_ARITHMETIC_PREFIX_OVERLAY_DESTINATION = 0x32E72E
WIDE_ARITHMETIC_PREFIX_OVERLAY_SOURCE = 0x4FE72E
WIDE_ARITHMETIC_PREFIX_OVERLAY_SIZE = 0x0040
# The public wide-value operator is another same-PC overlay. Flat 2C:77C8 is
# a preceding function's loop body; 49:77C8 is the complete LINK #0C routine.
WIDE_VALUE_OPERATOR_OVERLAY_DESTINATION = 0x2C77C8
WIDE_VALUE_OPERATOR_OVERLAY_SOURCE = 0x4977C8
WIDE_VALUE_OPERATOR_OVERLAY_SIZE = 0x01F0
# The operator's two register-ABI children are complete tail helpers. The
# segment-50 shift source must be embedded because that bank becomes RAM.
WIDE_DIVIDE_STEP_OVERLAY_DESTINATION = 0x2FB3E4
WIDE_DIVIDE_STEP_OVERLAY_SOURCE = 0x4CB3E4
WIDE_DIVIDE_STEP_OVERLAY_SIZE = 0x0130
WIDE_SHIFT_RIGHT_OVERLAY_DESTINATION = 0x335004
WIDE_SHIFT_RIGHT_OVERLAY_SOURCE = 0x505004
WIDE_SHIFT_RIGHT_OVERLAY_SIZE = 0x0014
# After mapping a physical key, 31:4E9C calls 32:7050. The flat destination
# is a long-function middle; 4F:7050 is the complete call-free mode predicate.
APPLICATION_KEY_MODE_OVERLAY_DESTINATION = 0x327050
APPLICATION_KEY_MODE_OVERLAY_SOURCE = 0x4F7050
APPLICATION_KEY_MODE_OVERLAY_SIZE = 0x006A
# The mapped-key path next calls 32:E0F4.  Flat 32:E0F4 is an unrelated
# function body starting with a byte store; 4F:E0F4 is the complete framed
# object-state refresh routine.  Its two segment-50 children are tiny framed
# wrappers around the already recovered 30:8B26 and 30:3A56 list-state helpers.
APPLICATION_KEY_ITEM_REFRESH_OVERLAY_DESTINATION = 0x32E0F4
APPLICATION_KEY_ITEM_REFRESH_OVERLAY_SOURCE = 0x4FE0F4
APPLICATION_KEY_ITEM_REFRESH_OVERLAY_SIZE = 0x0044
APPLICATION_KEY_ITEM_CLEAR_OVERLAY_DESTINATION = 0x33468C
APPLICATION_KEY_ITEM_CLEAR_OVERLAY_SOURCE = 0x50468C
APPLICATION_KEY_ITEM_CLEAR_OVERLAY_SIZE = 0x0016
APPLICATION_KEY_ITEM_SET_OVERLAY_DESTINATION = 0x334D2A
APPLICATION_KEY_ITEM_SET_OVERLAY_SOURCE = 0x504D2A
APPLICATION_KEY_ITEM_SET_OVERLAY_SIZE = 0x0016
# Event 0xF3 reaches 32:C736 from the application event dispatcher.  The flat
# target is a large parser's middle; 4F:C736 is the complete action.  Recover
# its whole call/data closure, including the resident CRC-CCITT implementation
# and the 256-word table that the relocated function addresses at 1B:860E.
APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_DESTINATION = 0x32C736
APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_SOURCE = 0x4FC736
APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_SIZE = 0x004E
APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_DESTINATION = 0x25C140
APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_SOURCE = 0x42C140
APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_SIZE = 0x03C8
APPLICATION_KEY_SPECIAL_CRC_OVERLAY_DESTINATION = 0x0D8552
APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SOURCE = 0x2A8552
APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SIZE = 0x00BC
APPLICATION_KEY_SPECIAL_CRC_TABLE_DESTINATION = 0x1B860E
APPLICATION_KEY_SPECIAL_CRC_TABLE_SOURCE = 0x2A860E
APPLICATION_KEY_SPECIAL_CRC_TABLE_SIZE = 0x0200
APPLICATION_KEY_SPECIAL_RESET_OVERLAY_DESTINATION = 0x3208B8
APPLICATION_KEY_SPECIAL_RESET_OVERLAY_SOURCE = 0x4F08B8
APPLICATION_KEY_SPECIAL_RESET_OVERLAY_SIZE = 0x008A
# The mapped-key dispatcher calls 32:CEA4 as a no-argument input-state
# predicate. Flat 32:CEA4 is a parser body fragment; 4F:CEA4 is the complete,
# call-free predicate and returns after inspecting A2:2ABA/A0:708B..708C.
APPLICATION_KEY_INPUT_STATE_OVERLAY_DESTINATION = 0x32CEA4
APPLICATION_KEY_INPUT_STATE_OVERLAY_SOURCE = 0x4FCEA4
APPLICATION_KEY_INPUT_STATE_OVERLAY_SIZE = 0x004A
# The foreground loop calls 31:4E9C to consume/update the mapped event state.
# Flat 31:4E9C is another long-function fragment.  The framed 4E source owns
# the A2:2AD6/2AD8 one-shot state and calls two adjacent segment-50 hardware
# state helpers; embed those helpers because segment 50 becomes writable RAM.
APPLICATION_KEY_DISPATCH_OVERLAY_DESTINATION = 0x314E9C
APPLICATION_KEY_DISPATCH_OVERLAY_SOURCE = 0x4E4E9C
APPLICATION_KEY_DISPATCH_OVERLAY_SIZE = 0x00BC
# Resident timer service 08:4380 calls 33:391A when its key/hardware state
# reaches one.  Flat 33:391A is a fragment of an unrelated application body;
# the complete framed helper is the adjacent 50:391A source.  Leaving only
# 33:393C/395E overlaid creates a hybrid routine whose second RETS consumes
# the caller's arguments as a far-return frame.
APPLICATION_KEY_HW_CLEAR_OVERLAY_DESTINATION = 0x33391A
APPLICATION_KEY_HW_CLEAR_OVERLAY_SOURCE = 0x50391A
APPLICATION_KEY_HW_CLEAR_OVERLAY_SIZE = 0x0022
APPLICATION_KEY_HW_PATH_A_OVERLAY_DESTINATION = 0x33393C
APPLICATION_KEY_HW_PATH_A_OVERLAY_SOURCE = 0x50393C
APPLICATION_KEY_HW_PATH_A_OVERLAY_SIZE = 0x0022
APPLICATION_KEY_HW_PATH_B_OVERLAY_DESTINATION = 0x33395E
APPLICATION_KEY_HW_PATH_B_OVERLAY_SOURCE = 0x50395E
APPLICATION_KEY_HW_PATH_B_OVERLAY_SIZE = 0x0022
# The mapped-key completion path enters flat 33:38F8 immediately before the
# restored 33:393C helper.  The updater's 50:38F8 body is a complete framed
# wrapper, not the preceding function's tail.  It calls the complete 45:F4A4
# worker, whose only not-yet-restored children are the call-free bitwise table
# update helpers at 4E:4D24 (OR) and 4E:5014 (AND).
APPLICATION_KEY_COMPLETION_OVERLAY_DESTINATION = 0x3338F8
APPLICATION_KEY_COMPLETION_OVERLAY_SOURCE = 0x5038F8
APPLICATION_KEY_COMPLETION_OVERLAY_SIZE = 0x0022
APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_DESTINATION = 0x28F4A4
APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_SOURCE = 0x45F4A4
APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_SIZE = 0x02DE
APPLICATION_BIT_OR_OVERLAY_DESTINATION = 0x314D24
APPLICATION_BIT_OR_OVERLAY_SOURCE = 0x4E4D24
APPLICATION_BIT_OR_OVERLAY_SIZE = 0x00BC
APPLICATION_BIT_AND_OVERLAY_DESTINATION = 0x315014
APPLICATION_BIT_AND_OVERLAY_SOURCE = 0x4E5014
APPLICATION_BIT_AND_OVERLAY_SIZE = 0x00BC
WIDE_REGISTER_DISPATCH_OVERLAY_DESTINATION = 0x335DE4
WIDE_REGISTER_DISPATCH_OVERLAY_SOURCE = 0x505DE4
WIDE_REGISTER_DISPATCH_OVERLAY_SIZE = 0x0030
WIDE_SIGN_NORMALIZE_OVERLAY_DESTINATION = 0x332AA2
WIDE_SIGN_NORMALIZE_OVERLAY_SOURCE = 0x502AA2
WIDE_SIGN_NORMALIZE_OVERLAY_SIZE = 0x0026
WIDE_LEFT_NONZERO_OVERLAY_DESTINATION = 0x331188
WIDE_LEFT_NONZERO_OVERLAY_SOURCE = 0x501188
WIDE_LEFT_NONZERO_OVERLAY_SIZE = 0x0018
WIDE_RIGHT_NONZERO_OVERLAY_DESTINATION = 0x3311A0
WIDE_RIGHT_NONZERO_OVERLAY_SOURCE = 0x5011A0
WIDE_RIGHT_NONZERO_OVERLAY_SIZE = 0x0018
APPLICATION_PAIR_STORE_OVERLAY_DESTINATION = 0x3281D4
APPLICATION_PAIR_STORE_OVERLAY_SOURCE = 0x4F81D4
APPLICATION_PAIR_STORE_OVERLAY_SIZE = 0x0030
FAR_MEMCPY_ADDRESS = 0x186D56
# The updater carries the complete same-PC implementation at +0x1D.  Unlike
# the earlier ABI-constrained loop, this original body normalizes data-space
# selectors through F2E0 before copying.  That distinction is observable when
# the resource reader copies a byte from external staging RAM into a local in
# internal SRAM (for example 29:AD7E -> 18:6D56 for source 10:D072).
FAR_MEMCPY_SOURCE = 0x356D56
FAR_MEMCPY_SIZE = 0x011A
# Keep the generated overlay installer and caller-constrained handoff in
# separate reserved parts of segment 03 below the exact vendor jump table at
# 03:4000.  The clean-room clear helper now lives with the NAND helpers in an
# unused part of segment 06, leaving segment 03 room for recovered descriptors.
POST_INITIALIZER_HANDOFF_PC = 0x0280
NATIVE_APPLICATION_SCHEDULER_ADDRESS = 0x030080
POST_INITIALIZER_LOADER_ADDRESS = 0x090000
# The normal cold path and the post-initializer probe are mutually exclusive,
# so they can share this resident window.  Segment 09 has no recovered vendor
# entry and holds the growing installer entirely within one 64-KiB code bank.
# Keeping it out of 05:2286..2C90 is essential: that range becomes executable
# RAM only after the installer has copied the exact application callee there.
DEFAULT_OVERLAY_INSTALLER_ADDRESS = POST_INITIALIZER_LOADER_ADDRESS
CLEAR_OVERLAY_ADDRESS = 0x061D00
CLEAR_OVERLAY_TARGET_PC = CLEAR_OVERLAY_ADDRESS & 0xFFFF
# The bootstrap foreground's root renderer consumes the five catalogue
# records before control can reach the inferred 03:0080 resident manager.
# Keep this small data-only exchange at the source-proven 06:1D40 boundary;
# the larger menu code overlay set remains deferred until the foreground has
# retired its overlapping segment-32 functions.
MENU_CATALOG_EARLY_INSTALLER_ADDRESS = 0x061D40
# The fixed 03:4000 vendor jump table leaves the inlined cold-boot installer
# only 0x3f00 bytes.  Keep the newly recovered menu copies, plus their existing
# cursor refresh dependency, in a small resident helper instead of growing the
# 03:0100 body across that immutable table.
MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS = 0x062900
MENU_POINTER_INDEX_INSTALLER_ADDRESS = 0x061600
APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS = 0x063A00
APPLICATION_MAIN_CURSOR_REFRESH_WRAPPER_ADDRESS = 0x064600
APPLICATION_MAIN_SINGLE_CYCLE_RETURN_ADDRESS = 0x064700
MENU_ROOT_DESCRIPTOR_PUBLISH_ADDRESS = 0x064800
DIRECT_GENERIC_MENU_PROBE_ADDRESS = 0x064900
# This bootstrap-only routine writes the exact 43:459C parser to its linked
# 26:459C overlay as ordinary guest instructions.  Keep it after the relocated
# resource-decoder installer in segment 09; 07:6748 is now recovered as a
# source-proven resident function rather than available scratch ROM.  Keep a
# full page after the growing post-initializer loader so adding a small exact
# metadata closure cannot silently overlap this helper.
APPLICATION_MENU_TEXT_STREAM_INSTALLER_ADDRESS = 0x09C800
# The direct native-menu probe needs the file object normally created by the
# absent outer resident manager.  Keep its two small device callbacks in the
# free 06:68xx window.  They execute as ordinary guest DMCU code; QEMU does
# not intercept either call or manufacture a filesystem result.
DIRECT_RESOURCE_NEXT_CLUSTER_ADDRESS = 0x066800
DIRECT_RESOURCE_READ_CALLBACK_ADDRESS = 0x066840
DIRECT_RESOURCE_POST_READ_ADDRESS = 0x066900
DIRECT_RESOURCE_FILE_ADDRESS = 0x530200
DIRECT_RESOURCE_DEVICE_ADDRESS = 0x530300
DIRECT_RESOURCE_SECTOR_BUFFER_ADDRESS = 0x530400
# The direct-menu probe keeps a small guest-visible diagnostic record directly
# after its 512-byte sector buffer.  It records only values already observed by
# the ordinary DMCU callbacks; no host service consumes or manufactures them.
DIRECT_RESOURCE_DIAGNOSTIC_ADDRESS = 0x530600
APPLICATION_TOP_LEVEL_MAIN_CALL = 0x2D7F7C
APPLICATION_TOP_LEVEL_MAIN_CALL_SOURCE = 0x4A7F7C
APPLICATION_MAIN_LOOP_BACK_EDGE = 0x225654
APPLICATION_MAIN_LOOP_BACK_EDGE_SOURCE = 0x3F5654

# Twenty-four shipped call sites target resident 02:DEA6 with the same six
# stack words: data far pointer, key far pointer, 64-bit block count, and a
# boolean direction.  Four independent source functions use it in the exact
# E-D-E sequence with the two halves of a 16-byte key, proving that the
# missing mask-ROM entry is the single-DES primitive behind the firmware's
# two-key Triple-DES resource decoder.  The clean-room implementation below
# is ordinary DMCU code; QEMU does not intercept this SCALL.
RESIDENT_DES_TRANSFORM_ADDRESS = 0x02DEA6
DES_TABLE_INITIALIZER_ADDRESS = 0x06C000

# The tables and all temporary bit arrays live in otherwise unused external
# RAM.  Logical E000 selects DS1, leaving DS0 free for each caller-supplied
# 24-bit data/key pointer.  DS1=0xBF maps this window to physical 5F:E000.
DES_WORKSPACE_BANK = 0x00BF
DES_TABLE_IP = 0xE000
DES_TABLE_FP = 0xE040
DES_TABLE_E = 0xE080
DES_TABLE_P = 0xE0B0
DES_TABLE_PC1 = 0xE0D0
DES_TABLE_PC2 = 0xE108
DES_TABLE_SHIFTS = 0xE138
DES_TABLE_SBOX = 0xE148
DES_KEY_BYTES = 0xE400
DES_KEY_BITS = 0xE408
DES_KEY_CD = 0xE448
DES_KEY_C = DES_KEY_CD
DES_KEY_D = 0xE464
DES_SUBKEYS = 0xE480
DES_BLOCK_BYTES = 0xE780
DES_BLOCK_BITS = 0xE788
DES_LEFT = 0xE7C8
DES_RIGHT = 0xE7E8
DES_EXPANDED = 0xE808
DES_SBOX_OUTPUT = 0xE838
DES_F_OUTPUT = 0xE858
DES_STATE_DATA_HIGH = 0xE900
DES_STATE_DATA_LOW = 0xE902
DES_STATE_KEY_HIGH = 0xE904
DES_STATE_KEY_LOW = 0xE906
DES_STATE_COUNT = 0xE908
DES_STATE_MODE = 0xE90A

DES_IP = (
    58, 50, 42, 34, 26, 18, 10, 2,
    60, 52, 44, 36, 28, 20, 12, 4,
    62, 54, 46, 38, 30, 22, 14, 6,
    64, 56, 48, 40, 32, 24, 16, 8,
    57, 49, 41, 33, 25, 17, 9, 1,
    59, 51, 43, 35, 27, 19, 11, 3,
    61, 53, 45, 37, 29, 21, 13, 5,
    63, 55, 47, 39, 31, 23, 15, 7,
)
DES_FP = (
    40, 8, 48, 16, 56, 24, 64, 32,
    39, 7, 47, 15, 55, 23, 63, 31,
    38, 6, 46, 14, 54, 22, 62, 30,
    37, 5, 45, 13, 53, 21, 61, 29,
    36, 4, 44, 12, 52, 20, 60, 28,
    35, 3, 43, 11, 51, 19, 59, 27,
    34, 2, 42, 10, 50, 18, 58, 26,
    33, 1, 41, 9, 49, 17, 57, 25,
)
DES_E = (
    32, 1, 2, 3, 4, 5,
    4, 5, 6, 7, 8, 9,
    8, 9, 10, 11, 12, 13,
    12, 13, 14, 15, 16, 17,
    16, 17, 18, 19, 20, 21,
    20, 21, 22, 23, 24, 25,
    24, 25, 26, 27, 28, 29,
    28, 29, 30, 31, 32, 1,
)
DES_P = (
    16, 7, 20, 21, 29, 12, 28, 17,
    1, 15, 23, 26, 5, 18, 31, 10,
    2, 8, 24, 14, 32, 27, 3, 9,
    19, 13, 30, 6, 22, 11, 4, 25,
)
DES_PC1 = (
    57, 49, 41, 33, 25, 17, 9,
    1, 58, 50, 42, 34, 26, 18,
    10, 2, 59, 51, 43, 35, 27,
    19, 11, 3, 60, 52, 44, 36,
    63, 55, 47, 39, 31, 23, 15,
    7, 62, 54, 46, 38, 30, 22,
    14, 6, 61, 53, 45, 37, 29,
    21, 13, 5, 28, 20, 12, 4,
)
DES_PC2 = (
    14, 17, 11, 24, 1, 5,
    3, 28, 15, 6, 21, 10,
    23, 19, 12, 4, 26, 8,
    16, 7, 27, 20, 13, 2,
    41, 52, 31, 37, 47, 55,
    30, 40, 51, 45, 33, 48,
    44, 49, 39, 56, 34, 53,
    46, 42, 50, 36, 29, 32,
)
DES_SHIFTS = (1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1)
DES_SBOXES = (
    (
        14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7,
        0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8,
        4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0,
        15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13,
    ),
    (
        15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10,
        3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5,
        0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15,
        13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9,
    ),
    (
        10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8,
        13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1,
        13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7,
        1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12,
    ),
    (
        7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15,
        13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9,
        10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4,
        3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14,
    ),
    (
        2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9,
        14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6,
        4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14,
        11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3,
    ),
    (
        12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11,
        10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8,
        9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6,
        4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13,
    ),
    (
        4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1,
        13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6,
        1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2,
        6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12,
    ),
    (
        13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7,
        1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2,
        7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8,
        2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11,
    ),
)


class _DMCUAssembler:
    """Tiny label resolver for clean-room same-segment DMCU routines."""

    def __init__(self, address: int):
        self.address = address
        self.words: list[int] = []
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    @property
    def pc(self) -> int:
        return (self.address + len(self.words) * 2) & 0xFFFFFF

    def emit(self, *words: int) -> None:
        if any(not 0 <= word <= 0xFFFF for word in words):
            raise ValueError("DMCU instruction word is outside 16 bits")
        self.words.extend(words)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate DMCU label {name}")
        self.labels[name] = self.pc

    def ajmp(self, label: str, condition: int = 0) -> None:
        if not 0 <= condition <= 0x0E:
            raise ValueError("invalid DMCU condition")
        self.emit(0xAC00 | condition, 0)
        self.fixups.append((len(self.words) - 1, label))

    def acall(self, label: str) -> None:
        self.emit(0xBC00, 0)
        self.fixups.append((len(self.words) - 1, label))

    def finish(self) -> list[int]:
        segment = self.address >> 16
        result = list(self.words)
        for index, label in self.fixups:
            if label not in self.labels:
                raise ValueError(f"undefined DMCU label {label}")
            target = self.labels[label]
            if target >> 16 != segment:
                raise ValueError(f"DMCU near target crosses segment: {label}")
            result[index] = target & 0xFFFF
        return result


def _dmcu_mov_imm(assembler: _DMCUAssembler, register: int, value: int) -> None:
    assembler.emit(0x68F0 | register, value & 0xFFFF)


def _dmcu_load_abs(assembler: _DMCUAssembler, register: int, address: int) -> None:
    assembler.emit(0x88F0 | register, address & 0xFFFF)


def _dmcu_store_abs(assembler: _DMCUAssembler, register: int, address: int) -> None:
    assembler.emit(0xA8F0 | register, address & 0xFFFF)


def des_table_bytes() -> bytes:
    """Return the standard FIPS DES tables in guest byte-access order."""
    table = bytes((
        *DES_IP, *DES_FP, *DES_E, *DES_P, *DES_PC1, *DES_PC2,
        *DES_SHIFTS, *(value for box in DES_SBOXES for value in box),
    ))
    expected_offsets = (
        (DES_TABLE_IP, 0),
        (DES_TABLE_FP, len(DES_IP)),
        (DES_TABLE_E, len(DES_IP) + len(DES_FP)),
        (DES_TABLE_P, len(DES_IP) + len(DES_FP) + len(DES_E)),
        (DES_TABLE_PC1,
         len(DES_IP) + len(DES_FP) + len(DES_E) + len(DES_P)),
        (DES_TABLE_PC2,
         len(DES_IP) + len(DES_FP) + len(DES_E) + len(DES_P) +
         len(DES_PC1)),
        (DES_TABLE_SHIFTS,
         len(DES_IP) + len(DES_FP) + len(DES_E) + len(DES_P) +
         len(DES_PC1) + len(DES_PC2)),
        (DES_TABLE_SBOX,
         len(DES_IP) + len(DES_FP) + len(DES_E) + len(DES_P) +
         len(DES_PC1) + len(DES_PC2) + len(DES_SHIFTS)),
    )
    for address, offset in expected_offsets:
        if address != DES_TABLE_IP + offset:
            raise ValueError(
                f"DES table layout drift at {address:04X}: {offset:04X}"
            )
    if len(DES_SBOXES) != 8 or any(len(box) != 64 for box in DES_SBOXES):
        raise ValueError("DES S-box dimensions changed")
    return table


def des_table_initializer_words() -> list[int]:
    """Materialize standard DES tables through ordinary guest RAM writes."""
    data = des_table_bytes()
    if len(data) & 1:
        raise ValueError("DES table image must contain whole external words")
    words = [
        0x58F0,                       # save R0
        0x1F11,                       # save DS1
        0x6811, DES_WORKSPACE_BANK,   # DS1 -> 5F:E000 workspace
    ]
    for offset in range(0, len(data), 2):
        # External byte operands invert A0.  A word with the first logical
        # byte in its high lane therefore yields the table's natural order to
        # MOVB at E000, E001, ... without any host-side memory service.
        value = (data[offset] << 8) | data[offset + 1]
        words.extend((
            0x68F0, value,
            0xA8F0, DES_TABLE_IP + offset,
        ))
    words.extend((
        0x1F91,                       # restore DS1
        0x380F,                       # restore R0
        RETS,
    ))
    return words


def des_transform_words() -> list[int]:
    """Implement resident 02:DEA6 as a standard DES ECB block transform.

    Guest ABI after SCALL and the saved frame pointer::

        [FP+06]:[FP+08] data far pointer
        [FP+0A]:[FP+0C] key far pointer
        [FP+0E]         number of 8-byte blocks
        [FP+10]         1=encrypt, 0=decrypt

    Bit arrays make the recovered semantics explicit and auditable.  This is
    slower than an SP-box implementation, but it keeps every permutation and
    S-box identical to FIPS DES and is easily verified with known-answer
    vectors while still completing the firmware's largest 0x80-block call.
    """
    a = _DMCUAssembler(RESIDENT_DES_TRANSFORM_ADDRESS)

    # Establish a stable frame and preserve every non-return GPR plus both
    # data-bank selectors.  R11/R15 continue to use internal stack SRAM.
    a.emit(0x58FB, 0x08BF)             # PUSH R11; MOV R11,R15
    for register in range(1, 11):
        a.emit(0x58F0 | register)
    a.emit(0x1F10, 0x1F11)             # PUSH DS0; PUSH DS1
    a.emit(0x6811, DES_WORKSPACE_BANK)

    for register, offset, address in (
        (0, 0x0006, DES_STATE_DATA_HIGH),
        (0, 0x0008, DES_STATE_DATA_LOW),
        (0, 0x000A, DES_STATE_KEY_HIGH),
        (0, 0x000C, DES_STATE_KEY_LOW),
        (0, 0x000E, DES_STATE_COUNT),
        (0, 0x0010, DES_STATE_MODE),
    ):
        a.emit(0x7800 | (register << 4) | 0x0B, offset)
        _dmcu_store_abs(a, register, address)

    # Read the 64-bit key from its arbitrary far pointer, convert it to bits,
    # apply PC-1, then build all sixteen 48-bit round keys.
    _dmcu_load_abs(a, 0, DES_STATE_KEY_HIGH)
    _dmcu_load_abs(a, 1, DES_STATE_KEY_LOW)
    _dmcu_mov_imm(a, 8, DES_KEY_BYTES)
    _dmcu_mov_imm(a, 4, 8)
    a.acall("far_read")
    _dmcu_mov_imm(a, 8, DES_KEY_BYTES)
    _dmcu_mov_imm(a, 9, DES_KEY_BITS)
    a.acall("bytes_to_bits")
    _dmcu_mov_imm(a, 8, DES_KEY_BITS)
    _dmcu_mov_imm(a, 9, DES_TABLE_PC1)
    _dmcu_mov_imm(a, 10, DES_KEY_CD)
    _dmcu_mov_imm(a, 0, 56)
    a.acall("permute")
    _dmcu_mov_imm(a, 6, 0)             # round index
    _dmcu_mov_imm(a, 7, DES_SUBKEYS)   # next round-key destination
    a.label("key_round")
    _dmcu_mov_imm(a, 2, DES_TABLE_SHIFTS)
    a.emit(0x1026, 0x2912, 0x1901)     # R2+=R6; RB1=[R2]; MOVZE R0,RB1
    a.emit(0x58F0)                     # preserve shift count for D
    _dmcu_mov_imm(a, 8, DES_KEY_C)
    a.acall("rotate28")
    a.emit(0x380F)                     # restore shift count
    _dmcu_mov_imm(a, 8, DES_KEY_D)
    a.acall("rotate28")
    _dmcu_mov_imm(a, 8, DES_KEY_CD)
    _dmcu_mov_imm(a, 9, DES_TABLE_PC2)
    a.emit(0x08A7)                     # MOV R10,R7
    _dmcu_mov_imm(a, 0, 48)
    a.acall("permute")
    _dmcu_mov_imm(a, 0, 48)
    a.emit(0x1070, 0x5061)             # R7+=48; R6++
    _dmcu_mov_imm(a, 0, 16)
    a.emit(0x1660)                     # CMP R6,R0
    a.ajmp("key_round", 0x02)         # NZ

    a.label("block_check")
    _dmcu_load_abs(a, 0, DES_STATE_COUNT)
    a.emit(0x5600)                     # CMP R0,#0
    a.ajmp("done", 0x01)              # EQ

    # Load one block, apply IP, and split it into contiguous L/R bit arrays.
    _dmcu_load_abs(a, 0, DES_STATE_DATA_HIGH)
    _dmcu_load_abs(a, 1, DES_STATE_DATA_LOW)
    _dmcu_mov_imm(a, 8, DES_BLOCK_BYTES)
    _dmcu_mov_imm(a, 4, 8)
    a.acall("far_read")
    _dmcu_mov_imm(a, 8, DES_BLOCK_BYTES)
    _dmcu_mov_imm(a, 9, DES_BLOCK_BITS)
    a.acall("bytes_to_bits")
    _dmcu_mov_imm(a, 8, DES_BLOCK_BITS)
    _dmcu_mov_imm(a, 9, DES_TABLE_IP)
    _dmcu_mov_imm(a, 10, DES_LEFT)
    _dmcu_mov_imm(a, 0, 64)
    a.acall("permute")

    _dmcu_load_abs(a, 0, DES_STATE_MODE)
    a.emit(0x5600)
    a.ajmp("decrypt_keys", 0x01)
    _dmcu_mov_imm(a, 7, DES_SUBKEYS)
    _dmcu_mov_imm(a, 6, 48)
    a.ajmp("rounds_ready")
    a.label("decrypt_keys")
    _dmcu_mov_imm(a, 7, DES_SUBKEYS + 15 * 48)
    _dmcu_mov_imm(a, 6, -48)
    a.label("rounds_ready")
    _dmcu_mov_imm(a, 5, 16)

    a.label("round")
    _dmcu_mov_imm(a, 8, DES_RIGHT)
    _dmcu_mov_imm(a, 9, DES_TABLE_E)
    _dmcu_mov_imm(a, 10, DES_EXPANDED)
    _dmcu_mov_imm(a, 0, 48)
    a.acall("permute")
    _dmcu_mov_imm(a, 8, DES_EXPANDED)
    a.emit(0x0897)                     # MOV R9,R7
    _dmcu_mov_imm(a, 10, DES_EXPANDED)
    _dmcu_mov_imm(a, 0, 48)
    a.acall("xor_arrays")
    a.acall("sbox_transform")
    _dmcu_mov_imm(a, 8, DES_SBOX_OUTPUT)
    _dmcu_mov_imm(a, 9, DES_TABLE_P)
    _dmcu_mov_imm(a, 10, DES_F_OUTPUT)
    _dmcu_mov_imm(a, 0, 32)
    a.acall("permute")
    a.acall("feistel_update")
    a.emit(0x1076, 0x5251, 0x5650)     # R7+=delta; --rounds; CMP #0
    a.ajmp("round", 0x02)

    # DES emits R16||L16 before FP.  Swap the adjacent halves, apply FP, pack
    # the result to bytes, and write back to the original far block.
    a.acall("swap_halves")
    _dmcu_mov_imm(a, 8, DES_LEFT)
    _dmcu_mov_imm(a, 9, DES_TABLE_FP)
    _dmcu_mov_imm(a, 10, DES_BLOCK_BITS)
    _dmcu_mov_imm(a, 0, 64)
    a.acall("permute")
    _dmcu_mov_imm(a, 8, DES_BLOCK_BITS)
    _dmcu_mov_imm(a, 9, DES_BLOCK_BYTES)
    a.acall("bits_to_bytes")
    _dmcu_load_abs(a, 0, DES_STATE_DATA_HIGH)
    _dmcu_load_abs(a, 1, DES_STATE_DATA_LOW)
    _dmcu_mov_imm(a, 8, DES_BLOCK_BYTES)
    _dmcu_mov_imm(a, 4, 8)
    a.acall("far_write")

    # Advance the 24-bit byte pointer and remaining block count.
    _dmcu_load_abs(a, 0, DES_STATE_DATA_HIGH)
    _dmcu_load_abs(a, 1, DES_STATE_DATA_LOW)
    a.emit(0x5018, 0x5100)             # low += 8; high += carry
    _dmcu_store_abs(a, 0, DES_STATE_DATA_HIGH)
    _dmcu_store_abs(a, 1, DES_STATE_DATA_LOW)
    _dmcu_load_abs(a, 0, DES_STATE_COUNT)
    a.emit(0x5201)
    _dmcu_store_abs(a, 0, DES_STATE_COUNT)
    a.ajmp("block_check")

    a.label("done")
    a.emit(0x1F91, 0x1F90)             # POP DS1; POP DS0
    for register in range(10, 0, -1):
        a.emit(0x380F | (register << 4))
    a.emit(0x4800, 0x38BF, RETS)       # R0=0; POP R11; RETS

    # Copy bytes from/to a far pointer in R0:R1.  Recomputing DS0 for every
    # byte correctly handles both 32-KiB data-bank and 64-KiB far-pointer
    # boundaries; workspace accesses stay on DS1 through R8>=0x8000.
    a.label("far_read")
    a.label("far_read_loop")
    a.emit(0x5640)
    a.ajmp("far_read_return", 0x01)
    a.emit(
        0x0820, 0x0831,               # R2=high; R3=low
        0x4C31, 0x5C21,               # form 32-KiB bank in R2
        0x58F2, 0x1F90, 0x4D31,       # DS0=R2; logical offset in R3
        0x29B3, 0x1B8B,               # RB11=[R3]; [R8++]=RB11
        0x5011, 0x5100, 0x5241,
    )
    a.ajmp("far_read_loop")
    a.label("far_read_return")
    a.emit(0xC600)

    a.label("far_write")
    a.label("far_write_loop")
    a.emit(0x5640)
    a.ajmp("far_write_return", 0x01)
    a.emit(
        0x0820, 0x0831,
        0x4C31, 0x5C21,
        0x58F2, 0x1F90, 0x4D31,
        0x39B8, 0x0B3B,               # RB11=[R8++]; [R3]=RB11
        0x5011, 0x5100, 0x5241,
    )
    a.ajmp("far_write_loop")
    a.label("far_write_return")
    a.emit(0xC600)

    a.label("bytes_to_bits")
    _dmcu_mov_imm(a, 0, 8)
    a.label("bytes_to_bits_loop")
    a.emit(0x3958)                     # MOVB RB5 (R2 low),[R8++]
    for shift in range(7, -1, -1):
        a.emit(0x0832)
        if shift:
            a.emit(0x4D30 | shift)
        a.emit(0x5431, 0x1B97)         # bit &= 1; [R9++]=RB7 (R3 low)
    a.emit(0x5201, 0x5600)
    a.ajmp("bytes_to_bits_loop", 0x02)
    a.emit(0xC600)

    a.label("bits_to_bytes")
    _dmcu_mov_imm(a, 0, 8)
    a.label("bits_to_bytes_loop")
    a.emit(0x4820)                     # R2=0
    for _ in range(8):
        a.emit(0x4C21, 0x3978, 0x1937, 0x1523)
    a.emit(0x1B95, 0x5201, 0x5600)
    a.ajmp("bits_to_bytes_loop", 0x02)
    a.emit(0xC600)

    # Generic byte-array permutation: R8=input, R9=1-based table,
    # R10=output, R0=count.
    a.label("permute")
    a.label("permute_loop")
    a.emit(
        0x3939, 0x1913, 0x5211,       # index = *table++ - 1
        0x0828, 0x1021,               # pointer = input + index
        0x2972, 0x1BA7,               # *output++ = *pointer
        0x5201, 0x5600,
    )
    a.ajmp("permute_loop", 0x02)
    a.emit(0xC600)

    # Rotate one 28-byte key half left by R0 single-bit positions.
    a.label("rotate28")
    a.label("rotate28_outer")
    a.emit(0x5600)
    a.ajmp("rotate28_return", 0x01)
    a.emit(
        0x0828, 0x2992,               # first (RB9/R4 low) = base[0]
        0x0838, 0x0828, 0x5021,       # dst=base; src=base+1
    )
    _dmcu_mov_imm(a, 1, 27)
    a.label("rotate28_inner")
    a.emit(0x39B2, 0x1B3B, 0x5211, 0x5610)
    a.ajmp("rotate28_inner", 0x02)
    a.emit(0x0B39, 0x5201)
    a.ajmp("rotate28_outer")
    a.label("rotate28_return")
    a.emit(0xC600)

    # XOR R0 bytes from R8 and R9 into R10.
    a.label("xor_arrays")
    a.label("xor_arrays_loop")
    a.emit(0x3938, 0x3959, 0x0735, 0x1BA3, 0x5201, 0x5600)
    a.ajmp("xor_arrays_loop", 0x02)
    a.emit(0xC600)

    # Convert eight groups of six expanded bits through the standard S-boxes
    # and emit their four-bit values MSB first.
    a.label("sbox_transform")
    a.emit(0x58F5, 0x58F6)
    _dmcu_mov_imm(a, 8, DES_EXPANDED)
    _dmcu_mov_imm(a, 9, DES_SBOX_OUTPUT)
    _dmcu_mov_imm(a, 6, DES_TABLE_SBOX)
    _dmcu_mov_imm(a, 5, 8)
    a.label("sbox_loop")
    a.emit(0x3918, 0x1901, 0x4C01, 0x0810, 0x4820)
    for shift in (3, 2, 1, 0):
        a.emit(0x3918, 0x1901)
        if shift:
            a.emit(0x4C00 | shift)
        a.emit(0x1520)
    a.emit(
        0x3918, 0x1901, 0x1510,       # row |= final bit
        0x4C14, 0x1012,               # index = row*16 + column
        0x0826, 0x1021, 0x2992,       # value = sbox_base[index]
    )
    for shift in (3, 2, 1, 0):
        a.emit(0x0834)
        if shift:
            a.emit(0x4D30 | shift)
        a.emit(0x5431, 0x1B97)
    _dmcu_mov_imm(a, 0, 64)
    a.emit(0x1060, 0x5251, 0x5650)
    a.ajmp("sbox_loop", 0x02)
    a.emit(0x386F, 0x385F, 0xC600)

    # newR=L xor F(R); newL=R, performed in place over 32 bytes.
    a.label("feistel_update")
    _dmcu_mov_imm(a, 8, DES_LEFT)
    _dmcu_mov_imm(a, 9, DES_RIGHT)
    _dmcu_mov_imm(a, 10, DES_F_OUTPUT)
    _dmcu_mov_imm(a, 0, 32)
    a.label("feistel_loop")
    a.emit(
        0x2938, 0x395A, 0x0735,
        0x2979, 0x1B87, 0x1B93,
        0x5201, 0x5600,
    )
    a.ajmp("feistel_loop", 0x02)
    a.emit(0xC600)

    a.label("swap_halves")
    _dmcu_mov_imm(a, 8, DES_LEFT)
    _dmcu_mov_imm(a, 9, DES_RIGHT)
    _dmcu_mov_imm(a, 0, 32)
    a.label("swap_loop")
    a.emit(0x2938, 0x2959, 0x1B85, 0x1B93, 0x5201, 0x5600)
    a.ajmp("swap_loop", 0x02)
    a.emit(0xC600)

    words = a.finish()
    if len(words) * 2 > 0x10000 - (RESIDENT_DES_TRANSFORM_ADDRESS & 0xFFFF):
        raise ValueError("clean-room DES routine crosses segment 02")
    return words


def mov_gpr_from_sp(register: int, offset: int) -> list[int]:
    """MOV Rn, [R15+offset]."""
    if not 0 <= register < 16 or not 0 <= offset <= 0xFFFF:
        raise ValueError("invalid register or stack offset")
    return [0x7800 | (register << 4) | 0x0F, offset]


def program_source_words(address: int, size: int) -> list[int]:
    """Read an even-sized, signature-checked PRG source range as DMCU words.

    Some absent resident entries have complete, relocation-proven
    implementations elsewhere in the shipped firmware.  The companion
    contract checker pins their entry/epilogue signatures, call targets and
    source-use counts; the clean-room ROM embeds those original guest
    instructions instead of translating them into host services.
    """
    if address < 0x200000 or size <= 0 or address & 1 or size & 1:
        raise ValueError("program source must be an even PRG range")
    data = program_source_bytes(address, size)
    return [
        int.from_bytes(data[index:index + 2], "little")
        for index in range(0, size, 2)
    ]


def retarget_program_source_call(
    address: int,
    size: int,
    call_address: int,
    old_target: int,
    new_target: int,
) -> list[int]:
    """Copy a source range while changing one signature-checked far call."""
    return retarget_program_source_calls(
        address, size, ((call_address, old_target, new_target),)
    )


def retarget_program_source_calls(
    address: int,
    size: int,
    patches: Sequence[tuple[int, int, int]],
) -> list[int]:
    """Copy a source range while changing signature-checked far calls."""
    words = program_source_words(address, size)
    seen: set[int] = set()
    for call_address, old_target, new_target in patches:
        if call_address in seen:
            raise ValueError(
                f"duplicate program-source call patch at {call_address:06X}"
            )
        seen.add(call_address)
        if (call_address < address or call_address + 4 > address + size or
                (call_address - address) & 1):
            raise ValueError("program-source call patch is outside its range")
        index = (call_address - address) // 2
        expected = [0xBD00 | (old_target >> 16), old_target & 0xFFFF]
        if words[index:index + 2] != expected:
            raise ValueError(
                f"program-source call signature changed at {call_address:06X}"
            )
        words[index:index + 2] = [
            0xBD00 | (new_target >> 16), new_target & 0xFFFF,
        ]
    return words


def application_foreground_state50_rom_words() -> list[int]:
    """Restore the state-50 body and relocate its linked-copy self calls."""
    patches = ((
        APPLICATION_FOREGROUND_STATE50_MODE_PAIR_CALL_SOURCE,
        APPLICATION_RESULT_MODE_PAIR_LINKED_DESTINATION,
        APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION,
    ),) + tuple(
        (
            source,
            APPLICATION_FOREGROUND_STATE50_SETTING_LINKED_DESTINATION,
            APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_DESTINATION,
        )
        for source in APPLICATION_FOREGROUND_STATE50_SETTING_CALL_SOURCES
    ) + tuple(
        (
            APPLICATION_FOREGROUND_STATE50_ROM_SOURCE + offset,
            APPLICATION_FOREGROUND_STATE50_ROM_SOURCE,
            APPLICATION_FOREGROUND_STATE50_ROM_DESTINATION,
        )
        for offset in APPLICATION_FOREGROUND_STATE50_ROM_SELF_CALL_OFFSETS
    )
    words = retarget_program_source_calls(
        APPLICATION_FOREGROUND_STATE50_ROM_SOURCE,
        APPLICATION_FOREGROUND_STATE50_ROM_SIZE,
        patches,
    )
    remaining_linked_self_calls = sum(
        words[index:index + 2] == [0xBD29, 0x0000]
        for index in range(len(words) - 1)
    )
    if remaining_linked_self_calls:
        raise ValueError(
            "unrelocated state-50 linked-copy self call remains"
        )
    return words


def application_foreground_state50_setting_words() -> list[int]:
    """Restore the collision-free state-50 setting wrapper."""
    return retarget_program_source_call(
        APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_SOURCE,
        APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_SIZE,
        APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_CALL_SOURCE,
        APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_LINKED_DESTINATION,
        APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_DESTINATION,
    )


def application_foreground_state50_setting_child_words() -> list[int]:
    """Restore the wrapper's exact clamp/write child and its commit leaf."""
    return retarget_program_source_call(
        APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_SOURCE,
        APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_SIZE,
        APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_CALL_SOURCE,
        APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_LINKED_DESTINATION,
        APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_DESTINATION,
    )


def application_foreground_state50_format_rom_words() -> list[int]:
    """Restore resident 1F:6DF6 with its collision-safe sector call."""
    return retarget_program_source_call(
        APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_SOURCE,
        APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_SIZE,
        APPLICATION_FOREGROUND_STATE50_FORMAT_SECTOR_CALL_SOURCE,
        APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
        APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION,
    )


def relocate_program_source_internal_ajmps(
    words: list[int],
    source_address: int,
    destination_address: int,
    patches: Sequence[tuple[int, int]],
) -> list[int]:
    """Relocate signature-checked same-segment absolute AJMP targets.

    ACxx encodes its condition in the first word and only the 16-bit target
    PC in the extension word.  A helper moved to a different PC therefore
    needs every internal ACxx target translated by the same byte delta; a
    segment-only relocation at an identical PC does not.
    """
    size = len(words) * 2
    seen: set[int] = set()
    for branch_address, old_target_pc in patches:
        if branch_address in seen:
            raise ValueError(
                f"duplicate internal AJMP patch at {branch_address:06X}"
            )
        seen.add(branch_address)
        if (branch_address < source_address or
                branch_address + 4 > source_address + size or
                (branch_address - source_address) & 1):
            raise ValueError("internal AJMP patch is outside its source range")
        index = (branch_address - source_address) // 2
        if words[index] >> 8 != 0xAC or words[index + 1] != old_target_pc:
            raise ValueError(
                f"internal AJMP signature changed at {branch_address:06X}"
            )
        source_target = (branch_address & 0xFF0000) | old_target_pc
        if not source_address <= source_target < source_address + size:
            raise ValueError(
                f"internal AJMP target escaped source at {branch_address:06X}"
            )
        destination_target = (
            destination_address + source_target - source_address
        )
        if ((destination_target ^ destination_address) & 0xFF0000) != 0:
            raise ValueError(
                f"relocated AJMP target crossed segment at {branch_address:06X}"
            )
        words[index + 1] = destination_target & 0xFFFF
    return words


def resident_storage_driver_words() -> list[int]:
    """Recover 2D:3460, including branches and its callback return frame."""
    words = relocate_program_source_internal_ajmps(
        program_source_words(
            RESIDENT_STORAGE_DRIVER_SOURCE,
            RESIDENT_STORAGE_DRIVER_SIZE,
        ),
        RESIDENT_STORAGE_DRIVER_SOURCE,
        RESIDENT_STORAGE_DRIVER_ADDRESS,
        RESIDENT_STORAGE_DRIVER_INTERNAL_AJMPS,
    )
    for pc_load, segment_load, return_pc, return_segment in (
            RESIDENT_STORAGE_DRIVER_CALLBACK_RETURN_FRAMES):
        pc_index = (pc_load - RESIDENT_STORAGE_DRIVER_SOURCE) // 2
        segment_index = (segment_load - RESIDENT_STORAGE_DRIVER_SOURCE) // 2
        if words[pc_index:pc_index + 2] != [0x68FE, return_pc]:
            raise ValueError(
                "storage driver callback return-PC signature changed"
            )
        if words[segment_index:segment_index + 2] != [
                0x68FE, return_segment
        ]:
            raise ValueError(
                "storage driver callback return-segment signature changed"
            )
        source_return = (pc_load & 0xFF0000) | return_pc
        words[pc_index + 1] = (
            RESIDENT_STORAGE_DRIVER_ADDRESS +
            source_return - RESIDENT_STORAGE_DRIVER_SOURCE
        ) & 0xFFFF
        words[segment_index + 1] = RESIDENT_STORAGE_DRIVER_ADDRESS >> 16
    return words


def resident_file_write_words() -> list[int]:
    """Recover resident file writer 17:E3EE and retarget its children."""
    return retarget_program_source_calls(
        RESIDENT_FILE_WRITE_SOURCE,
        RESIDENT_FILE_WRITE_SIZE,
        (
            (0x34E6F4, 0x28AC4C, RESIDENT_STORAGE_SELECT_ADDRESS),
            (0x34E73E, 0x28AC4C, RESIDENT_STORAGE_SELECT_ADDRESS),
            (0x34E8B8, 0x306E9E, RESIDENT_STORAGE_PAIR_ADDRESS),
            (0x34E9BC, 0x321614, RESIDENT_STORAGE_PROBE_WRAPPER_ADDRESS),
            (0x34ED22, APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
             APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION),
            (0x34EDEA, 0x2D3460, RESIDENT_STORAGE_DRIVER_ADDRESS),
        ),
    )


def storage_record_capacity_service_words() -> list[int]:
    """Recover 33:13F8 and retarget its collision-prone capacity child."""
    return retarget_program_source_call(
        STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_SOURCE,
        STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_SIZE,
        STORAGE_RECORD_CAPACITY_CHILD_CALL_SOURCE,
        STORAGE_RECORD_CAPACITY_CHILD_LINKED_DESTINATION,
        STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_DESTINATION,
    )


def storage_record_capacity_wrapper_words() -> list[int]:
    """Recover record+0x10's wrapper and retarget its collided service."""
    return retarget_program_source_call(
        STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_SOURCE,
        STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_SIZE,
        STORAGE_RECORD_CAPACITY_WRAPPER_CALL_SOURCE,
        STORAGE_RECORD_CAPACITY_SERVICE_LINKED_DESTINATION,
        STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_DESTINATION,
    )


def storage_unit_open_capacity_wrapper_words() -> list[int]:
    """Publish unit zero's recovered capacity callback, then open the unit."""
    a = _DMCUAssembler(STORAGE_UNIT_OPEN_CAPACITY_WRAPPER_ADDRESS)
    a.emit(
        0x2E00,                       # LINK #0
        0x58F1,                       # preserve R1
        0x1F10,                       # preserve DS0
        0x780B, 0x0006,               # R0 = original unit argument
        0x5600,                       # CMP R0,#0
    )
    a.ajmp("forward", 0x02)           # NZ: other records stay exact
    a.emit(
        0x6810,
        STORAGE_UNIT_ZERO_RECORD_CAPACITY_SEGMENT_ADDRESS >> 15,
        0xC700,                       # data-segment pipeline NOP
        0x68F1,
        STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_DESTINATION >> 16,
        0xA8F1,
        STORAGE_UNIT_ZERO_RECORD_CAPACITY_SEGMENT_ADDRESS & 0x7FFF,
        0x68F1,
        STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_DESTINATION & 0xFFFF,
        0xA8F1,
        STORAGE_UNIT_ZERO_RECORD_CAPACITY_OFFSET_ADDRESS & 0x7FFF,
    )
    a.label("forward")
    a.emit(
        0x780B, 0x0006,               # forward the same unit argument
        0x58F0,
        0xBD00 | (STORAGE_UNIT_OPEN_CAPACITY_LINKED_DESTINATION >> 16),
        STORAGE_UNIT_OPEN_CAPACITY_LINKED_DESTINATION & 0xFFFF,
        0x50F2,                       # discard wrapper's forwarded argument
        0x1F90,                       # restore DS0
        0x381F,                       # restore R1; preserve callee's R0 result
        0x2F00,
        RETS,
    )
    return a.finish()


def storage_record_capacity_installer_words() -> list[int]:
    """Install the guest capacity closure and its exact unit-open hook."""
    source_call = program_source_words(
        STORAGE_UNIT_OPEN_CAPACITY_CALL_SOURCE, 4
    )
    expected_call = [
        0xBD00 | (STORAGE_UNIT_OPEN_CAPACITY_LINKED_DESTINATION >> 16),
        STORAGE_UNIT_OPEN_CAPACITY_LINKED_DESTINATION & 0xFFFF,
    ]
    if source_call != expected_call:
        raise ValueError(
            "storage unit-open call signature changed: "
            f"{source_call!r} != {expected_call!r}"
        )
    return [
        *copy_code_to_overlay_words(
            STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_DESTINATION,
            STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SOURCE,
            STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SIZE,
        ),
        *write_program_words(
            STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_DESTINATION,
            storage_record_capacity_service_words(),
        ),
        *write_program_words(
            STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_DESTINATION,
            storage_record_capacity_wrapper_words(),
        ),
        *write_program_words(
            STORAGE_UNIT_OPEN_CAPACITY_CALL,
            [
                0xBD00 | (STORAGE_UNIT_OPEN_CAPACITY_WRAPPER_ADDRESS >> 16),
                STORAGE_UNIT_OPEN_CAPACITY_WRAPPER_ADDRESS & 0xFFFF,
            ],
        ),
        RETS,
    ]


def resident_storage_select_words() -> list[int]:
    """Recover the 28:AC4C helper out of line with its closed children."""
    return relocate_program_source_internal_ajmps(
        retarget_program_source_calls(
            RESIDENT_STORAGE_SELECT_SOURCE,
            RESIDENT_STORAGE_SELECT_SIZE,
            (
                (0x45AE4A,
                 APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
                 APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION),
                (0x45AF02, 0x1CE37E, RESIDENT_STORAGE_SCAN_ADDRESS),
                (0x45AF26, 0x1CE37E, RESIDENT_STORAGE_SCAN_ADDRESS),
            ),
        ),
        RESIDENT_STORAGE_SELECT_SOURCE,
        RESIDENT_STORAGE_SELECT_ADDRESS,
        RESIDENT_STORAGE_SELECT_INTERNAL_AJMPS,
    )


def resident_storage_pair_words() -> list[int]:
    """Recover the 30:6E9E helper out of line."""
    return relocate_program_source_internal_ajmps(
        retarget_program_source_call(
            RESIDENT_STORAGE_PAIR_SOURCE,
            RESIDENT_STORAGE_PAIR_SIZE,
            0x4D6F10,
            0x31B1FA,
            RESIDENT_STORAGE_MUL_DIV_ADDRESS,
        ),
        RESIDENT_STORAGE_PAIR_SOURCE,
        RESIDENT_STORAGE_PAIR_ADDRESS,
        RESIDENT_STORAGE_PAIR_INTERNAL_AJMPS,
    )


def resident_storage_probe_wrapper_words() -> list[int]:
    """Recover the 32:1614 helper and its relocated sector probe call."""
    return relocate_program_source_internal_ajmps(
        retarget_program_source_calls(
            RESIDENT_STORAGE_PROBE_WRAPPER_SOURCE,
            RESIDENT_STORAGE_PROBE_WRAPPER_SIZE,
            (
                (0x4F162E, 0x31B1FA, RESIDENT_STORAGE_MUL_DIV_ADDRESS),
                (0x4F1660,
                 APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
                 APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION),
            ),
        ),
        RESIDENT_STORAGE_PROBE_WRAPPER_SOURCE,
        RESIDENT_STORAGE_PROBE_WRAPPER_ADDRESS,
        RESIDENT_STORAGE_PROBE_WRAPPER_INTERNAL_AJMPS,
    )


def resident_storage_mul_div_words() -> list[int]:
    """Recover the 31:B1FA helper with its internal AJMPs relocated."""
    return relocate_program_source_internal_ajmps(
        program_source_words(
            RESIDENT_STORAGE_MUL_DIV_SOURCE,
            RESIDENT_STORAGE_MUL_DIV_SIZE,
        ),
        RESIDENT_STORAGE_MUL_DIV_SOURCE,
        RESIDENT_STORAGE_MUL_DIV_ADDRESS,
        RESIDENT_STORAGE_MUL_DIV_INTERNAL_AJMPS,
    )


def resident_storage_scan_words() -> list[int]:
    """Recover resident 1C:E37E out of line with its exact leaf closure."""
    return relocate_program_source_internal_ajmps(
        retarget_program_source_calls(
            RESIDENT_STORAGE_SCAN_SOURCE,
            RESIDENT_STORAGE_SCAN_SIZE,
            (
                (0x39E3F4, 0x31B1FA, RESIDENT_STORAGE_MUL_DIV_ADDRESS),
                (0x39E43E, 0x33525E, RESIDENT_STORAGE_RESULT_LEAF_ADDRESS),
                (0x39E496, 0x329C6A, RESIDENT_STORAGE_RANGE_LEAF_ADDRESS),
                (0x39E58A, 0x329C6A, RESIDENT_STORAGE_RANGE_LEAF_ADDRESS),
                (0x39E646, 0x33525E, RESIDENT_STORAGE_RESULT_LEAF_ADDRESS),
                (0x39E722, 0x33525E, RESIDENT_STORAGE_RESULT_LEAF_ADDRESS),
            ),
        ),
        RESIDENT_STORAGE_SCAN_SOURCE,
        RESIDENT_STORAGE_SCAN_ADDRESS,
        RESIDENT_STORAGE_SCAN_INTERNAL_AJMPS,
    )


def program_source_bytes(address: int, size: int) -> bytes:
    """Read an arbitrary byte range from its 20:0000-based PRG mapping."""
    if address < 0x200000 or size <= 0:
        raise ValueError("program source must be a positive PRG range")
    data = PROGRAM_SOURCE.read_bytes()
    offset = address - 0x200000
    if offset + size > len(data):
        raise ValueError("program source range is outside NP560.PRG")
    return data[offset:offset + size]


def initializer_factory_source_blocks() -> dict[int, bytes]:
    """Return exact first-initializer source storage recovered from PRG.

    These bytes are already in the physical little-endian storage order used
    by the program image.  Do not apply :func:`initializer_probe_storage_bytes`:
    source and destination byte accesses both use the DMCU external-lane swap,
    so the original raw word representation is preserved by the copy helper.
    """
    return {
        destination: program_source_bytes(source, size)
        for destination, source, size in INITIALIZER_FACTORY_SOURCE_COPIES
    }


def application_main_rom_input_words() -> list[int]:
    """Relocate the complete 2E:1752 clone to resident 11:1752."""
    words = program_source_words(
        APPLICATION_MAIN_ROM_INPUT_SOURCE,
        APPLICATION_MAIN_ROM_INPUT_SIZE,
    )
    source_call = [
        0xBD00 | (APPLICATION_MAIN_ROM_INPUT_LOCAL_SOURCE >> 16),
        APPLICATION_MAIN_ROM_INPUT_LOCAL_SOURCE & 0xFFFF,
    ]
    destination_call = [
        0xBD00 | (APPLICATION_MAIN_ROM_INPUT_LOCAL_DESTINATION >> 16),
        APPLICATION_MAIN_ROM_INPUT_LOCAL_DESTINATION & 0xFFFF,
    ]
    call_offsets = [
        index for index in range(len(words) - 1)
        if words[index:index + 2] == source_call
    ]
    if len(call_offsets) != 18:
        raise ValueError(
            "resident 11:1752 clone local-call signature count changed"
        )
    for index in call_offsets:
        words[index:index + 2] = destination_call
    return words


def compiler_initializer_copy_records() -> tuple[tuple[int, int, int], ...]:
    """Decode the 261 constant memcpy records in the original initializer."""
    data = program_source_bytes(
        COMPILER_INITIALIZER_ADDRESS,
        COMPILER_INITIALIZER_END - COMPILER_INITIALIZER_ADDRESS,
    )
    words = [
        int.from_bytes(data[offset:offset + 2], "little")
        for offset in range(0, len(data), 2)
    ]
    registers: dict[int, int] = {}
    records: list[tuple[int, int, int]] = []
    index = 0
    while index < len(words):
        word = words[index]
        op = word >> 8
        arg = word & 0xFF
        if op == 0x68 and 0xF0 <= arg <= 0xF4:
            if index + 1 >= len(words):
                raise ValueError("truncated compiler initializer immediate")
            registers[arg - 0xF0] = words[index + 1]
            index += 2
            continue
        if op == 0x48 and (arg >> 4) <= 4:
            registers[arg >> 4] = arg & 0x0F
            index += 1
            continue
        if word == 0xBD32 and index + 1 < len(words) and words[index + 1] == 0xF786:
            if set(registers) != set(range(5)):
                raise ValueError("incomplete compiler initializer copy record")
            records.append((
                registers[0] << 16 | registers[1],
                registers[2] << 16 | registers[3],
                registers[4],
            ))
            registers.clear()
            index += 2
            continue
        if word == 0xAD07 and index + 1 < len(words) and words[index + 1] == 0x7FE4:
            index += 2
            break
        raise ValueError(
            f"unexpected compiler initializer word 0x{word:04X} at "
            f"2E:{(COMPILER_INITIALIZER_ADDRESS + index * 2) & 0xFFFF:04X}"
        )
    if index != len(words) or len(records) != 261:
        raise ValueError(
            f"compiler initializer record boundary changed: "
            f"{len(records)} records, {index}/{len(words)} words"
        )
    return tuple(records)


def segment33_data_template_records() -> tuple[tuple[int, int, int], ...]:
    """Translate data-bus 33:* sources to their shipped segment-50 templates."""
    return tuple(
        (destination, source + SEGMENT33_DATA_TEMPLATE_DELTA, size)
        for destination, source, size in compiler_initializer_copy_records()
        if source >> 16 == 0x33
    )


def mov_mmio_from_gpr(address: int, register: int) -> list[int]:
    """MOV [address], Rn through the unbanked IGNDS data window."""
    if not 0 <= register < 16 or not 0 <= address <= 0xFFFF:
        raise ValueError("invalid register or MMIO address")
    return [IGNDS_ONE, 0xA8F0 | register, address]


def mov_gpr_from_mmio(register: int, address: int) -> list[int]:
    """MOV Rn, [address] through the unbanked IGNDS data window."""
    if not 0 <= register < 16 or not 0 <= address <= 0xFFFF:
        raise ValueError("invalid register or MMIO address")
    return [IGNDS_ONE, 0x88F0 | register, address]


def mov_mmio_from_sfr(address: int, sfr: int) -> list[int]:
    if not 0 <= sfr <= 0xEF or not 0 <= address <= 0xFFFF:
        raise ValueError("invalid SFR or MMIO address")
    return [IGNDS_ONE, 0xA800 | sfr, address]


def read_id_words() -> list[int]:
    # Trigger a hardware ID cycle and return EC:DC:10:95 as the two packed
    # words consumed by sub_50_AA1A.  Its geometry parser uses R0's low byte
    # (0x95) to derive 2 KiB pages, 64-byte OOB and 64 pages/block.
    return [
        0x4804,                         # MOV R0, #4 (READ_ID)
        *mov_mmio_from_gpr(NAND_COMMAND, 0),
        *mov_gpr_from_mmio(1, NAND_ID),
        # The mask-ROM API returns only the geometry byte used by AA1A in
        # R0's high byte; the intervening raw-ID byte is not consumed.
        0x68F0, 0x9500,
        # Preserve the same extended geometry byte in the burner global that
        # AA1A consults.  Its exact byte-return packing is part of the missing
        # ROM ABI; seeding the observed destination keeps that uncertainty in
        # guest ROM while the unmodified geometry parser remains in control.
        0x1F10, 0x6810, 0x00A0,
        0x68F2, 0x0095, 0xA8F2, 0x0002,
        0x1F90,
        RETS,
    ]


def transfer_page_words(
    command: int,
    before_command: int | None = None,
    after_command: int | None = None,
) -> list[int]:
    # SCALL leaves CS and PC on the stack.  The seven caller-owned ABI words
    # therefore begin at R15+4:
    #   u32 page, u16 column, far/near pointer, u16 length, u16 flags.
    fields = (
        (4, NAND_PAGE_HI),
        (6, NAND_PAGE_LO),
        (8, NAND_COLUMN),
        (10, NAND_BUFFER_HI),
        (12, NAND_BUFFER_LO),
        (14, NAND_LENGTH),
        (16, NAND_FLAGS),
    )
    words: list[int] = []
    for offset, register_address in fields:
        words.extend(mov_gpr_from_sp(0, offset))
        words.extend(mov_mmio_from_gpr(register_address, 0))
    # Keep the caller's selectors visible in the hardware register block for
    # diagnostics.  The DMA pointer itself is always the complete far pointer
    # above; in particular a zero high word correctly selects physical bank 0.
    words.extend(mov_mmio_from_sfr(NAND_DS0, 0x10))
    words.extend(mov_mmio_from_sfr(NAND_DS1, 0x11))
    if before_command is not None:
        words.extend([0xBD00 | (before_command >> 16), before_command & 0xFFFF])
    words.extend(
        [
            0x4800 | command,           # MOV R0, #command
            *mov_mmio_from_gpr(NAND_COMMAND, 0),
        ]
    )
    if after_command is not None:
        words.extend([0xBD00 | (after_command >> 16), after_command & 0xFFFF])
    words.extend([*mov_gpr_from_mmio(0, NAND_STATUS), RETS])
    return words


def read_page_words() -> list[int]:
    return transfer_page_words(
        1,
        before_command=NAND_PREPARE_READ_ADDRESS,
        after_command=NAND_UNPACK_SPARE_ADDRESS,
    )


def program_page_words() -> list[int]:
    # BCC6 has the same seven-word ABI as BBF6.  The strongest direction
    # evidence is sub_51_08A6: it reads page 0x3F with BBF6, edits/constructs
    # the in-memory block marker, then invokes BCC6 with identical arguments.
    # The vendor's 51:C1A4 ECC worker proves that a full-page BCC6 call uses
    # an expanded logical spare record beyond the caller's 528 transfer bytes.
    # Pack that record in a separate guest helper before issuing the raw NAND
    # command.  QEMU still sees and programs an ordinary 512+16-byte page.
    return transfer_page_words(2, before_command=NAND_PACK_SPARE_ADDRESS)


def _patch_rjmp(words: list[int], index: int, target: int) -> None:
    displacement = target - (index + 1)
    if not -128 <= displacement <= 127:
        raise ValueError("relative branch exceeds signed byte range")
    words[index] = (words[index] & 0xFF00) | (displacement & 0xFF)


def prepare_logical_read_words() -> list[int]:
    """Translate BBF6's synthesized page-status byte to physical OOB.

    The FTL probes logical column ``page_data_size + 0x36`` before paying for
    a complete page read.  That byte is not stored verbatim in the 16-byte
    physical OOB: the three redundant page-state bytes start at logical spare
    offset 0x37, with copy zero packed into physical OOB[4].  Reading that
    first state copy is sufficient for the fast erased-page test: an erased
    page remains 0xff, while a formatted/programmed FTL page is non-0xff.

    Keep the translation in guest ROM.  QEMU still receives an ordinary raw
    NAND read at physical column 0x204 and does not implement a BBF6 service.
    The post-read helper normalizes any programmed state to logical status 0;
    0xff remains the erased-page sentinel used by sub_50_B730.
    """
    words = [
        0x58F0, 0x58F1,                         # preserve R0/R1
        *mov_gpr_from_mmio(0, NAND_COLUMN),
        0x68F1, 0x0236, 0x1601,                 # column == 0x236?
    ]
    column_skip = len(words)
    words.append(0xD200)
    words.extend([
        *mov_gpr_from_mmio(0, NAND_LENGTH),
        0x5601,                                  # length == 1?
    ])
    length_skip = len(words)
    words.append(0xD200)
    words.extend([
        0x68F0, 0x0204,                         # physical OOB[4]
        *mov_mmio_from_gpr(NAND_COLUMN, 0),
    ])
    restore = len(words)
    words.extend([0x381F, 0x380F, RETS])
    _patch_rjmp(words, column_skip, restore)
    _patch_rjmp(words, length_skip, restore)
    return words


def pack_logical_spare_words() -> list[int]:
    """Pack C1A4's expanded ECC/FTL record into the physical 16-byte OOB.

    The recovered logical record maps the six ECC bytes around physical bad-
    block byte 5, and maps the three redundant state bytes plus three redundant
    16-bit identifiers into the nine remaining metadata bytes.  The 0x6979
    logical signature validates the ECC record but is not itself stored.
    """
    words = [
        0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4,  # preserve R0..R4
        0x1F10,                                   # preserve DS0
        *mov_gpr_from_mmio(0, NAND_LENGTH),
        0x68F3, NAND_SMALL_PAGE_TOTAL, 0x1603,     # length == 0x210?
    ]
    length_skip = len(words)
    words.append(0xD200)
    words.extend(mov_gpr_from_mmio(0, NAND_COLUMN))
    words.append(0x5600)                           # column == 0?
    column_skip = len(words)
    words.append(0xD200)

    # Page 0x3f is already a contiguous three-candidate partition record:
    # data holds candidate 0, OOB[0..7] is its sequential ECC descriptor, and
    # OOB[8..15] starts candidate 1.  Its evidenced factory encoding must pass
    # through unchanged rather than use the ordinary FTL spare packing below.
    words.extend(mov_gpr_from_mmio(0, NAND_PAGE_HI))
    words.append(0x5600)
    page_hi_normal = len(words)
    words.append(0xD200)
    words.extend(mov_gpr_from_mmio(0, NAND_PAGE_LO))
    words.extend([0x68F3, 0x003F, 0x1603])
    page_lo_restore = len(words)
    words.append(0xD100)

    normal_pack = len(words)
    words.extend(mov_gpr_from_mmio(0, NAND_BUFFER_HI))
    words.extend(mov_gpr_from_mmio(1, NAND_BUFFER_LO))
    words.extend([
        0x70F1, 0x0200, 0x5100,                   # buffer + data bytes
        0x4C11, 0x5C01, 0x4D11,                   # normalize to DS0:R1
        0x58F0, 0x1F90,

        # logical[0x16..0x19] -> OOB[0..3]
        0x0821, 0x502F, 0x5027,                   # R2=R1+0x16
        0x0831,                                   # R3=R1
        0x2802, 0x0A30, 0x5022, 0x5032,
        0x2802, 0x0A30, 0x5022, 0x5032,

        # logical[0x1a..0x1b] -> OOB[6..7], preserving bad marker byte 5
        0x5032, 0x2802, 0x0A30,

        # logical state copy 0 -> OOB[4]
        0x0821, 0x502F, 0x502F, 0x502F, 0x502A,   # R2=R1+0x37
        0x0831, 0x5034, 0x2B32,

        # state copies 1/2 and three identifiers -> OOB[8..15]
        0x0821, 0x502F, 0x502F, 0x502F, 0x502B,   # R2=R1+0x38
        0x0831, 0x5038, 0x4844,
    ])
    loop = len(words)
    words.append(0x5640)
    loop_done = len(words)
    words.append(0xD100)
    words.extend([
        0x2802, 0x0A30, 0x5022, 0x5032, 0x5241,
    ])
    loop_back = len(words)
    words.append(0xD000)
    restore = len(words)
    words.extend([
        0x1F90, 0x384F, 0x383F, 0x382F, 0x381F, 0x380F, RETS,
    ])
    _patch_rjmp(words, length_skip, restore)
    _patch_rjmp(words, column_skip, restore)
    _patch_rjmp(words, page_hi_normal, normal_pack)
    _patch_rjmp(words, page_lo_restore, restore)
    _patch_rjmp(words, loop_done, restore)
    _patch_rjmp(words, loop_back, loop)
    return words


def unpack_logical_spare_words() -> list[int]:
    """Expand a physical 16-byte OOB into BBF6's 64-byte logical record."""
    words = [
        0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4,
        0x1F10,                                   # preserve DS0
        *mov_gpr_from_mmio(0, NAND_LENGTH),
        0x68F3, NAND_SMALL_PAGE_TOTAL, 0x1603,     # compact raw page?
    ]
    full_length_skip = len(words)
    words.append(0xD200)
    words.extend(mov_gpr_from_mmio(0, NAND_COLUMN))
    words.append(0x5600)                           # column == 0?
    full_column_skip = len(words)
    words.append(0xD200)

    # Page 0x3f is the factory partition record and is deliberately stored as
    # a contiguous raw 0x210-byte page.  Its program path already bypasses the
    # ordinary FTL packer, so preserve the same exception on read.
    words.extend(mov_gpr_from_mmio(0, NAND_PAGE_HI))
    words.append(0x5600)
    page_hi_full = len(words)
    words.append(0xD200)
    words.extend(mov_gpr_from_mmio(0, NAND_PAGE_LO))
    words.extend([0x68F3, 0x003F, 0x1603])
    page3f_restore = len(words)
    words.append(0xD100)

    full_call = len(words)
    words.extend([
        0xBD00 | (NAND_UNPACK_FULL_ADDRESS >> 16),
        NAND_UNPACK_FULL_ADDRESS & 0xFFFF,
    ])
    early_restore = len(words)
    words.extend([
        0x1F90, 0x384F, 0x383F, 0x382F, 0x381F, 0x380F, RETS,
    ])

    status_path = len(words)
    words.extend([
        *mov_gpr_from_mmio(0, NAND_LENGTH),
        0x5601,                                    # status probe length == 1?
    ])
    status_length_skip = len(words)
    words.append(0xD200)
    words.extend(mov_gpr_from_mmio(0, NAND_COLUMN))
    words.extend([0x68F3, 0x0204, 0x1603])         # translated OOB[4]?
    status_column_skip = len(words)
    words.append(0xD200)
    words.extend(mov_gpr_from_mmio(0, NAND_BUFFER_HI))
    words.extend(mov_gpr_from_mmio(1, NAND_BUFFER_LO))
    words.extend([
        0x4C11, 0x5C01, 0x4D11,                   # buffer -> DS0:R1
        0x58F0, 0x1F90,
        0x2931,                                   # RB3 = physical OOB[4]
        0x66F3, 0x00FF,                           # erased page remains 0xff
    ])
    status_restore = len(words)
    words.append(0xD100)
    words.extend([
        0x4930,                                   # programmed page => status 0
        0x0B13,                                   # MOVB [R1], RB3
    ])
    status_done = len(words)
    words.append(0xD000)

    ordinary_path = len(words)
    words.extend([
        *mov_gpr_from_mmio(0, NAND_LENGTH),
        0x68F3, 0x0040, 0x1603,                   # length == 0x40?
    ])
    length_skip = len(words)
    words.append(0xD200)
    words.extend(mov_gpr_from_mmio(0, NAND_COLUMN))
    words.extend([0x68F3, 0x0200, 0x1603])         # column == 0x200?
    column_skip = len(words)
    words.append(0xD200)

    words.extend(mov_gpr_from_mmio(0, NAND_BUFFER_HI))
    words.extend(mov_gpr_from_mmio(1, NAND_BUFFER_LO))
    words.extend([
        0x4C11, 0x5C01, 0x4D11,                   # buffer -> DS0:R1
        0x58F0, 0x1F90,

        # OOB[0..3] -> logical[0x16..0x19]
        0x0821,                                   # R2=R1
        0x0831, 0x503F, 0x5037,                   # R3=R1+0x16
        0x2802, 0x0A30, 0x5022, 0x5032,
        0x2802, 0x0A30, 0x5022, 0x5032,

        # OOB[6..7] -> logical[0x1a..0x1b]
        0x5022, 0x2802, 0x0A30, 0x5032,
        0x68F0, 0x6979, 0x0A30,                   # logical signature

        # OOB[4] -> logical state copy 0
        0x0821, 0x5024,
        0x0831, 0x503F, 0x503F, 0x503F, 0x503A,   # R3=R1+0x37
        0x2B32,

        # OOB[8..15] -> logical[0x38..0x3f]
        0x0821, 0x5028,
        0x0831, 0x503F, 0x503F, 0x503F, 0x503B,   # R3=R1+0x38
        0x4844,
    ])
    loop = len(words)
    words.append(0x5640)
    loop_done = len(words)
    words.append(0xD100)
    words.extend([
        0x2802, 0x0A30, 0x5022, 0x5032, 0x5241,
    ])
    loop_back = len(words)
    words.append(0xD000)
    restore = len(words)
    words.extend([
        0x1F90, 0x384F, 0x383F, 0x382F, 0x381F, 0x380F, RETS,
    ])
    _patch_rjmp(words, full_length_skip, status_path)
    _patch_rjmp(words, full_column_skip, status_path)
    _patch_rjmp(words, page_hi_full, full_call)
    _patch_rjmp(words, page3f_restore, early_restore)
    _patch_rjmp(words, status_length_skip, ordinary_path)
    _patch_rjmp(words, status_column_skip, ordinary_path)
    _patch_rjmp(words, status_restore, restore)
    _patch_rjmp(words, status_done, restore)
    _patch_rjmp(words, length_skip, restore)
    _patch_rjmp(words, column_skip, restore)
    _patch_rjmp(words, loop_done, restore)
    _patch_rjmp(words, loop_back, loop)
    return words


def unpack_full_logical_page_words() -> list[int]:
    """Expand the raw OOB left after a full 0x210-byte BBF6 read.

    BBF6's caller requests only the physical 512+16 bytes, but immediately
    consumes an ECC/FTL record through offsets 0x216..0x23f of the same cache.
    The mask ROM therefore synthesizes those bytes after NAND DMA.  Preserve
    the raw OOB until every compact field has been copied, then fill the two
    unused logical ranges with the erased value.
    """
    words = [
        0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4,
        0x1F10,                                   # preserve DS0
        *mov_gpr_from_mmio(0, NAND_BUFFER_HI),
        *mov_gpr_from_mmio(1, NAND_BUFFER_LO),
        0x70F1, 0x0200, 0x5100,                   # physical OOB address
        0x4C11, 0x5C01, 0x4D11,                   # -> DS0:R1
        0x58F0, 0x1F90,

        # OOB[0..3] -> logical[0x16..0x19]
        0x0821,
        0x0831, 0x503F, 0x5037,
        0x2802, 0x0A30, 0x5022, 0x5032,
        0x2802, 0x0A30, 0x5022, 0x5032,

        # OOB[6..7] -> logical[0x1a..0x1b], then regenerated signature.
        0x5022, 0x2802, 0x0A30, 0x5032,
        0x68F0, 0x6979, 0x0A30,

        # OOB[4] -> first redundant page-state byte at logical[0x37].
        0x0821, 0x5024,
        0x0831, 0x503F, 0x503F, 0x503F, 0x503A,
        0x2B32,

        # OOB[8..15] -> state copies 1/2 and three redundant identifiers.
        0x0821, 0x5028,
        0x0831, 0x503F, 0x503F, 0x503F, 0x503B,
        0x4844,
    ]
    copy_loop = len(words)
    words.append(0x5640)
    copy_done = len(words)
    words.append(0xD100)
    words.extend([0x2802, 0x0A30, 0x5022, 0x5032, 0x5241])
    copy_back = len(words)
    words.append(0xD000)

    # logical[0x36] is synthesized, not stored.  The first redundant state
    # copy distinguishes an erased page (0xff) from a programmed page; a
    # successfully decoded programmed page reports status zero.
    status_path = len(words)
    words.extend([
        0x0821, 0x5024,                           # R2 = OOB + 4
        0x0831, 0x503F, 0x503F, 0x503F, 0x5039,  # R3 = OOB + 0x36
        0x2942,                                   # RB4 = [R2]
        0x66F4, 0x00FF,
    ])
    status_store = len(words)
    words.append(0xD100)
    words.append(0x4940)                          # programmed => status 0
    status_store_target = len(words)
    words.append(0x0B34)                          # MOVB [R3], RB4

    # The compact OOB has now been consumed.  Fill logical spare gaps
    # [0x00,0x15] and [0x1e,0x35] with the erased value.
    words.extend([0x68F0, 0xFFFF, 0x0831, 0x484B])
    fill_head = len(words)
    words.extend([0x0A30, 0x5032, 0x5241, 0x5640])
    fill_head_back = len(words)
    words.append(0xD200)
    words.extend([
        0x0831, 0x503F, 0x503F,                  # R3 = OOB + 0x1e
        0x484C,                                   # 12 words / 24 bytes
    ])
    fill_middle = len(words)
    words.extend([0x0A30, 0x5032, 0x5241, 0x5640])
    fill_middle_back = len(words)
    words.append(0xD200)
    restore = len(words)
    words.extend([
        0x1F90, 0x384F, 0x383F, 0x382F, 0x381F, 0x380F, RETS,
    ])
    _patch_rjmp(words, copy_done, status_path)
    _patch_rjmp(words, copy_back, copy_loop)
    _patch_rjmp(words, status_store, status_store_target)
    _patch_rjmp(words, fill_head_back, fill_head)
    _patch_rjmp(words, fill_middle_back, fill_middle)
    return words


def erase_block_words(preserve_block_one_probe: bool = False) -> list[int]:
    # BDD6 receives one 16-bit erase-block index and uses zero as success.
    # Convert the block to a 32-bit page address (64 pages/block), issue the
    # hardware command, then return the controller error code rather than its
    # positive transfer-status value.
    words = [
        *mov_gpr_from_sp(1, 4),
    ]
    if preserve_block_one_probe:
        # Exploration only.  Full official sequencing proves that the earlier
        # blanket block-one guard was too broad: command 1 needs the ordinary
        # scan to rebuild NFTL.  The remaining collision is the final 7DD8
        # scan at 50:812C (return PC 50:8130): command 11 first removes the
        # freshly written CAFE/KB record, and command 2 later removes it again
        # between two CB62 passes.  Suppress only this caller/block tuple for
        # those two post-format commands; all other block-one erases remain.
        # This remains a boundary probe, not a claim that the factory BDD6
        # literally performs these checks.
        words.append(0x5611)                # CMP R1, #1
        block_mismatch = len(words)
        words.append(0xD200)                # RJMP NZ,normal erase
        words.extend([
            *mov_gpr_from_sp(0, 2),         # caller return PC
            0x68F2, 0x8130,                 # R2 = return after 50:812C
            0x1602,                         # CMP R0, R2
        ])
        caller_mismatch = len(words)
        words.append(0xD200)                # RJMP NZ,normal erase
        words.extend([
            0x1F10,                         # preserve DS0
            0x6810, 0x00A0,                 # DS0 = physical bank 50
            0x88F0, 0x0008,                 # R0 = current burner command
            0x1F90,                         # restore DS0
            0x560B,                         # CMP R0, #11
        ])
        command11_match = len(words)
        words.append(0xD100)                # RJMP Z,success
        words.append(0x5602)                # CMP R0, #2
        command_mismatch = len(words)
        words.append(0xD200)                # RJMP NZ,normal erase
        skip_success = len(words)
        words.extend([
            0x4800,                         # MOV R0, #0 (success)
            RETS,
        ])
        normal_erase = len(words)
        _patch_rjmp(words, block_mismatch, normal_erase)
        _patch_rjmp(words, caller_mismatch, normal_erase)
        _patch_rjmp(words, command11_match, skip_success)
        _patch_rjmp(words, command_mismatch, normal_erase)
    words.extend([
        # Retain the unscaled erase-block argument in the diagnostic flags
        # register.  Hardware ignores it for erase commands, while the NAND
        # trace can distinguish caller arithmetic from address conversion.
        *mov_mmio_from_gpr(NAND_FLAGS, 1),
        0x4800,                         # MOV R0, #0 (page high)
        0x4C16,                         # SL R1, #6
        0x5C06,                         # SLOSB R0, #6
        *mov_mmio_from_gpr(NAND_PAGE_HI, 0),
        *mov_mmio_from_gpr(NAND_PAGE_LO, 1),
        0x4803,                         # MOV R0, #3 (ERASE_BLOCK)
        *mov_mmio_from_gpr(NAND_COMMAND, 0),
        *mov_gpr_from_mmio(0, NAND_ERROR),
        RETS,
    ])
    return words


def copy_page_words() -> list[int]:
    """Start the resident-ROM NAND copy-back operation.

    The burner supplies two 32-bit page numbers after the far-call return
    frame: source at R15+4/+6 and destination at R15+8/+10.  The EC:DC NAND
    can copy a complete data+spare page internally, so the reconstructed ROM
    exposes that hardware operation through command 5 instead of borrowing a
    guest-RAM scratch buffer.
    """
    fields = (
        (4, NAND_PAGE_HI),
        (6, NAND_PAGE_LO),
        (8, NAND_BUFFER_HI),
        (10, NAND_BUFFER_LO),
    )
    words: list[int] = []
    for offset, register_address in fields:
        words.extend(mov_gpr_from_sp(0, offset))
        words.extend(mov_mmio_from_gpr(register_address, 0))
    words.extend([
        0x4800,                         # MOV R0, #0
        *mov_mmio_from_gpr(NAND_COLUMN, 0),
        0x68F0, NAND_PAGE_TOTAL,        # MOV R0, #2112
        *mov_mmio_from_gpr(NAND_LENGTH, 0),
        0x4800,                         # MOV R0, #0
        *mov_mmio_from_gpr(NAND_FLAGS, 0),
        0x4805,                         # MOV R0, #5 (COPY_BACK)
        *mov_mmio_from_gpr(NAND_COMMAND, 0),
        *mov_gpr_from_mmio(0, NAND_STATUS),
        RETS,
    ])
    return words


def nand_completion_words() -> list[int]:
    """Return the last asynchronous NAND operation's zero-on-success code."""
    return [*mov_gpr_from_mmio(0, NAND_ERROR), RETS]


def copy_code_to_overlay_words(
    destination: int,
    source: int,
    length: int,
) -> list[int]:
    """Copy code-image bytes into executable data RAM through the data bus.

    R1 deliberately uses DS0 with a low-half logical pointer and R3 uses DS1
    with a high-half logical pointer.  A logical pointer changes from DS0 to
    DS1 when bit 15 changes, so one loop must never cross a 32-KiB bank edge.
    Split long/rim-adjacent copies and reprogram both selectors at every edge;
    otherwise destination writes after ``...:7FFF`` are sent through the
    source selector and the remainder of an overlay silently stays flat.
    """
    for name, address in (("destination", destination), ("source", source)):
        if not 0 <= address <= 0xFFFFFF:
            raise ValueError(f"{name} must be a 24-bit physical address")
    if not 0 < length <= 0xFFFF:
        raise ValueError("overlay length must be between 1 and 65535 bytes")
    if destination + length > 0x1000000 or source + length > 0x1000000:
        raise ValueError("overlay copy crosses the 24-bit address-space limit")

    words: list[int] = []
    remaining = length
    while remaining:
        destination_window = 0x8000 - (destination & 0x7FFF)
        source_window = 0x8000 - (source & 0x7FFF)
        chunk = min(remaining, destination_window, source_window)
        words.extend([
            0x6810, destination >> 15,          # DS0 -> destination bank
            0x6811, source >> 15,               # DS1 -> source bank
            0x68F1, destination & 0x7FFF,       # R1 -> DS0 low half
            0x68F3, 0x8000 | (source & 0x7FFF), # R3 -> DS1 high half
            0x68F4, chunk,                      # R4 = byte count
            0x5640,                             # loop: CMP R4,#0
            0xD105,                             # RJMP Z,+5 -> next chunk
            0x2B13,                             # MOVB [R1],[R3]
            0x5011,                             # ADD R1,#1
            0x5031,                             # ADD R3,#1
            0x5241,                             # SUB R4,#1
            0xD0F9,                             # RJMP ALWAYS,-7 -> loop
        ])
        destination += chunk
        source += chunk
        remaining -= chunk
    words.extend([
        0x6810, 0x0000,                         # restore reset DS0
        0x6811, 0x0001,                         # restore reset DS1
    ])
    return words


def embed_program_overlay_words(
    destination: int,
    source: int,
    length: int,
) -> list[int]:
    """Write exact PRG words when its data-bus source is not PRG storage.

    Segment 50 is visible as mutable data after the vendor initializers, so a
    guest-side source copy from 50:* observes cleared RAM rather than the PRG
    code image.  Some lower linked sources can likewise be covered by a
    higher-priority resource alias; encode their exact shipped words as
    ordinary guest MOV writes too.  This remains guest code installation;
    QEMU does not service the call.
    """
    if destination < 0 or destination > 0xFFFFFF:
        raise ValueError("destination must be a 24-bit physical address")
    if destination & 1 or length & 1 or length <= 0:
        raise ValueError("embedded overlay must use positive whole words")
    logical = destination & 0x7FFF
    if logical + length > 0x8000:
        raise ValueError("embedded overlay crosses a 32-KiB data bank")
    words = [0x6810, destination >> 15]
    for index, value in enumerate(program_source_words(source, length)):
        words.extend((0x68F0, value, 0xA8F0, logical + index * 2))
    return words


def modal_media_browser_installer_words() -> list[int]:
    """Install 17:CCD0 from ROM-held words, then return to ROM-01."""
    return [
        *embed_program_overlay_words(
            APPLICATION_MODAL_MEDIA_BROWSER_OVERLAY_DESTINATION,
            APPLICATION_MODAL_MEDIA_BROWSER_OVERLAY_SOURCE,
            APPLICATION_MODAL_MEDIA_BROWSER_OVERLAY_SIZE,
        ),
        RETS,
    ]


def operation_modal_overlay_install_words(
    destination: int,
    source: int,
    size: int,
) -> list[int]:
    """Build one modal-closure installation action.

    Segment 50 is mutable and must be embedded in place.  Source 34:CCD0 is
    hidden on the natural data bus by the hardware font-data view
    34:0000..34:FFFF, so call its separately placed immutable-word installer.
    All other linked PRG banks remain directly copyable by guest code.
    """
    if source == APPLICATION_MODAL_MEDIA_BROWSER_OVERLAY_SOURCE:
        if (destination != APPLICATION_MODAL_MEDIA_BROWSER_OVERLAY_DESTINATION or
                size != APPLICATION_MODAL_MEDIA_BROWSER_OVERLAY_SIZE):
            raise ValueError("unexpected modal media-browser overlay tuple")
        return [
            0xBD00 | (APPLICATION_MODAL_MEDIA_BROWSER_INSTALLER_ADDRESS >> 16),
            APPLICATION_MODAL_MEDIA_BROWSER_INSTALLER_ADDRESS & 0xFFFF,
        ]
    if source >> 16 == 0x50:
        return embed_program_overlay_words(destination, source, size)
    return copy_code_to_overlay_words(destination, source, size)


def embed_program_data_words(
    destination: int,
    source: int,
    length: int,
) -> list[int]:
    """Write exact PRG data bytes to RAM, preserving odd records and edges."""
    if not 0 <= destination <= 0xFFFFFF:
        raise ValueError("destination must be a 24-bit physical address")
    if destination + length > 0x1000000:
        raise ValueError("embedded data crosses the 24-bit address space")
    data = program_source_bytes(source, length)
    words: list[int] = []
    offset = 0
    active_bank: int | None = None
    while offset < length:
        physical = destination + offset
        bank = physical >> 15
        logical = physical & 0x7FFF
        if bank != active_bank:
            words.extend((0x6810, bank))
            active_bank = bank
        if not (physical & 1) and length - offset >= 2 and logical <= 0x7FFE:
            value = int.from_bytes(data[offset:offset + 2], "little")
            words.extend((0x68F0, value, 0xA8F0, logical))
            offset += 2
        else:
            words.extend((0x69F0, data[offset], 0xA9F0, logical))
            offset += 1
    return words


def write_program_words(destination: int, values: Sequence[int]) -> list[int]:
    """Write a short reconstructed instruction sequence through the data bus."""
    if destination & 1 or not values:
        raise ValueError("program-word patch must be non-empty and aligned")
    if destination < 0 or destination + len(values) * 2 > 0x1000000:
        raise ValueError("program-word patch is outside the 24-bit address space")
    logical = destination & 0x7FFF
    if logical + len(values) * 2 > 0x8000:
        raise ValueError("program-word patch crosses a 32-KiB data bank")
    words = [0x6810, destination >> 15]
    for index, value in enumerate(values):
        if not 0 <= value <= 0xFFFF:
            raise ValueError("program-word patch values must fit in 16 bits")
        words.extend((0x68F0, value, 0xA8F0, logical + index * 2))
    return words


def storage_driver_retire_words() -> list[int]:
    """Restore the application body hidden by the bootstrap storage overlay."""
    return [
        *copy_code_to_overlay_words(
            APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_DESTINATION,
            STORAGE_DRIVER_RETIRE_PAYLOAD_ADDRESS,
            APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SIZE,
        ),
        0x6810, 0x00A2,  # restore the unit-open caller's expected data page
        0x88F0, 0x2AE0,  # MOV R0, [A2:2AE0], displaced by the cleanup SCALL
        RETS,
    ]


def install_copy_overlay_words() -> list[int]:
    """Install the compiler copy helper needed by both initializer chains."""
    return copy_code_to_overlay_words(0x32F786, 0x4FF786, 0x003C)


def install_initializer_data_overlay_words() -> list[int]:
    """Install static sources consumed during the vendor initializer chain."""
    destination = STORAGE_GEOMETRY_DATA_OVERLAY_DESTINATION
    words = [0x6810, destination >> 15]
    logical = destination & 0x7FFF
    for index, value in enumerate(STORAGE_GEOMETRY_DEFAULT_WORDS):
        words.extend((0x68F0, value, 0xA8F0, logical + index * 2))
    # Segment 50 is mutable data by this late continuation, so embed its exact
    # shipped matrix constants.  Segment 4F remains an immutable PRG source
    # and can supply the contiguous event tables through the guest data bus.
    words.extend(embed_program_data_words(
        KEY_MATRIX_TABLE_DESTINATION,
        KEY_MATRIX_TABLE_SOURCE,
        KEY_MATRIX_TABLE_SIZE,
    ))
    words.extend(copy_code_to_overlay_words(
        KEY_EVENT_TABLES_DESTINATION,
        KEY_EVENT_TABLES_SOURCE,
        KEY_EVENT_TABLES_SIZE,
    ))
    return words


def storage_global_template_probe_words() -> list[int]:
    """Reapply every decoded segment-33 data template as guest instructions."""
    words: list[int] = []
    for destination, source, size in segment33_data_template_records():
        words.extend(embed_program_data_words(destination, source, size))
    words.append(RETS)
    return words


def install_runtime_overlay_words() -> list[int]:
    """Install recovered run-time overlay trampolines and full functions.

    NP560.PRG contains pre-overlay data at the final call addresses. The
    resident loader would normally replace it.  The clean-room loader writes
    minimal far jumps which retain the caller's SCALL frame, so the resident
    bodies see the original arguments at SP+4 and can return with RETS.
    """
    patches = ((0x256042, CLEAR_OVERLAY_ADDRESS),)
    words: list[int] = []
    for physical, target in patches:
        bank = physical >> 15
        logical = physical & 0x7FFF
        words.extend([0x6810, bank])   # MOV DS0, #32-KiB bank
        for index, value in enumerate(
                (0xAD00 | (target >> 16), target & 0xFFFF)):
            words.extend([
                0x68F0, value,        # MOV R0, #word
                0xA8F0, logical + index * 2,
            ])
    # Restore the five-word descending far-memory move used while inserting
    # sorted resident-manager records.  This is ordinary guest code written
    # through the data bus into executable overlay RAM; QEMU only provides
    # the corresponding Harvard code-bus alias.
    words.extend(write_program_words(
        REVERSE_FAR_MEMMOVE_OVERLAY_DESTINATION,
        reverse_far_memmove_words(),
    ))
    # The no-argument 33:6030 call in the memory initializer otherwise lands
    # in a LINK #0xFF function that reads caller parameters.  Its complete
    # same-PC implementation is stored at 50:6030.  Its child helper at
    # 50:5906 cannot remain at logical 33:5906 because that address is also a
    # live fall-through instruction in the flat foreground worker.  Install a
    # wrapper whose sole direct call is relocated to the exact resident copy
    # at 06:1CE0.  Segment 50 is data RAM after 20:0030, so reproduce the
    # evidenced source words as ordinary guest writes.
    for destination, source_words in (
        (MODE_INIT_OVERLAY_DESTINATION, MODE_INIT_OVERLAY_WORDS),
        (MODE_MASK_OVERLAY_DESTINATION, MODE_MASK_OVERLAY_WORDS),
        (SYSTEM_INIT_OVERLAY_DESTINATION,
         SYSTEM_INIT_RELOCATED_OVERLAY_WORDS),
        (APPLICATION_STATE_BYTE_OVERLAY_DESTINATION,
         APPLICATION_STATE_BYTE_OVERLAY_WORDS),
        (GLOBAL_RESET_OVERLAY_DESTINATION, GLOBAL_RESET_OVERLAY_WORDS),
        (SYSTEM_MODE_OVERLAY_DESTINATION, SYSTEM_MODE_OVERLAY_WORDS),
        (STARTUP_TABLE_SERVICE_OVERLAY_DESTINATION,
         STARTUP_TABLE_SERVICE_OVERLAY_WORDS),
        (STARTUP_REGION_SERVICE_OVERLAY_DESTINATION,
         STARTUP_REGION_SERVICE_OVERLAY_WORDS),
    ):
        words.extend([0x6810, destination >> 15])
        logical = destination & 0x7FFF
        for index, value in enumerate(source_words):
            words.extend([0x68F0, value, 0xA8F0, logical + index * 2])
    # The other two 08:427E call paths first call 31:AF72.  Its flat bytes are
    # an in-function jump, while 4E:AF72 is a complete no-argument hardware
    # control sequence at the same PC.
    words.extend(copy_code_to_overlay_words(
        MEMORY_RESET_OVERLAY_DESTINATION,
        MEMORY_RESET_OVERLAY_SOURCE,
        MEMORY_RESET_OVERLAY_SIZE,
    ))
    # The next function in the same source module is equally conclusive:
    # 130 calls target the incompatible flat 31:B014 bytes, while 4E:B014 is
    # a complete one-argument function and has no literal in-place callers.
    words.extend(copy_code_to_overlay_words(
        MEMORY_MODE_OVERLAY_DESTINATION,
        MEMORY_MODE_OVERLAY_SOURCE,
        MEMORY_MODE_OVERLAY_SIZE,
    ))
    # 20:026A's no-argument call needs the complete same-PC routine stored at
    # 49:9A7C.  Install it at the called address; QEMU only supplies shared
    # executable RAM for this evidenced range.
    words.extend(copy_code_to_overlay_words(
        MEMORY_INIT_OVERLAY_DESTINATION,
        MEMORY_INIT_OVERLAY_SOURCE,
        MEMORY_INIT_OVERLAY_SIZE,
    ))
    # The memory initializer's nested 33:6030 path calls 2E:5316 with four
    # stack words.  Flat 2E:5316 is the middle of initializer descriptor 156;
    # the sole same-PC ABI match is the complete four-argument function kept
    # in uncalled source segment 4B.
    words.extend(copy_code_to_overlay_words(
        TEXT_DRAW_OVERLAY_DESTINATION,
        TEXT_DRAW_OVERLAY_SOURCE,
        TEXT_DRAW_OVERLAY_SIZE,
    ))
    # 20:02E2 calls 32:4218 with no arguments.  The flat destination is a
    # frame-relative fragment from the middle of another function and can
    # unwind through the caller.  The same PC at uncalled 4F:4218 is a
    # complete LINK #1 routine with a normal epilogue.
    words.extend(copy_code_to_overlay_words(
        STARTUP_TABLE_OVERLAY_DESTINATION,
        STARTUP_TABLE_OVERLAY_SOURCE,
        STARTUP_TABLE_OVERLAY_SIZE,
    ))
    # The following 20:026A call has the same conflict.  Flat 32:CC9C is a
    # shared tail, while uncalled 4F:CC9C is a complete LINK #0 function.
    words.extend(copy_code_to_overlay_words(
        STARTUP_POINTER_OVERLAY_DESTINATION,
        STARTUP_POINTER_OVERLAY_SOURCE,
        STARTUP_POINTER_OVERLAY_SIZE,
    ))
    # 20:02EA's flat 32:8EBE target begins at SLOSB in a much larger
    # parameterized function.  Uncalled 4F:8EBE is the complete no-argument
    # table-clear routine and has no resident-ROM calls.
    words.extend(copy_code_to_overlay_words(
        STARTUP_ARRAY_OVERLAY_DESTINATION,
        STARTUP_ARRAY_OVERLAY_SOURCE,
        STARTUP_ARRAY_OVERLAY_SIZE,
    ))
    # 20:02EE and the installed 4B:5316 body call 31:4BAC without the large
    # frame required by its flat target.  Uncalled 4E:4BAC is the complete
    # no-argument startup wrapper; its three short 33:* dependencies are
    # installed above from complete same-PC segment-50 bodies.
    words.extend(copy_code_to_overlay_words(
        STARTUP_RUNTIME_OVERLAY_DESTINATION,
        STARTUP_RUNTIME_OVERLAY_SOURCE,
        STARTUP_RUNTIME_OVERLAY_SIZE,
    ))
    # Four application paths call 31:A914, whose flat PRG bytes are the middle
    # of another function.  The uncalled same-PC 4E:A914 body is a complete
    # no-argument LCD/application initializer and ends with a normal RETS.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_LCD_INIT_OVERLAY_DESTINATION,
        APPLICATION_LCD_INIT_OVERLAY_SOURCE,
        APPLICATION_LCD_INIT_OVERLAY_SIZE,
    ))
    # The exact resident 08:3292 body calls 24:9BD4 without arguments.  Flat
    # 24:9BD4 is a shared tail; 41:9BD4 is a complete same-PC peripheral/SFR
    # initializer bounded by RETS at 41:9BE6 and has no in-place caller.
    words.extend(copy_code_to_overlay_words(
        PERIPHERAL_INIT_OVERLAY_DESTINATION,
        PERIPHERAL_INIT_OVERLAY_SOURCE,
        PERIPHERAL_INIT_OVERLAY_SIZE,
    ))
    # Reset activation passes a two-word far pointer to 30:9E30.  The flat
    # target starts at an epilogue fragment, while 4D:9E30 is the complete
    # same-PC LINK #4 implementation with the matching argument accesses.
    words.extend(copy_code_to_overlay_words(
        ACTIVATION_CONTEXT_OVERLAY_DESTINATION,
        ACTIVATION_CONTEXT_OVERLAY_SOURCE,
        ACTIVATION_CONTEXT_OVERLAY_SIZE,
    ))
    # 306 three-word calls target 32:D530.  Its flat bytes are a shared tail;
    # 4F:D530 is the complete same-PC LINK #1 wrapper and returns at 4F:D576.
    words.extend(copy_code_to_overlay_words(
        POINTER_SERVICE_OVERLAY_DESTINATION,
        POINTER_SERVICE_OVERLAY_SOURCE,
        POINTER_SERVICE_OVERLAY_SIZE,
    ))
    # Direct dependencies of the recovered pointer-service wrapper. Each
    # target is a flat shared tail and each +0x1D-segment source is a complete
    # same-PC function with matching argument cleanup and no source caller.
    for destination, source, size in (
        (POINTER_STATE_OVERLAY_DESTINATION,
         POINTER_STATE_OVERLAY_SOURCE, POINTER_STATE_OVERLAY_SIZE),
        (POINTER_FLAG_OVERLAY_DESTINATION,
         POINTER_FLAG_OVERLAY_SOURCE, POINTER_FLAG_OVERLAY_SIZE),
        (POINTER_NORMALIZE_OVERLAY_DESTINATION,
         POINTER_NORMALIZE_OVERLAY_SOURCE, POINTER_NORMALIZE_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    words.extend(copy_code_to_overlay_words(
        POINTER_RESOLVE_OVERLAY_DESTINATION,
        POINTER_RESOLVE_OVERLAY_SOURCE,
        POINTER_RESOLVE_OVERLAY_SIZE,
    ))
    # Restore the complete drawing-context constructor that builds the
    # rectangle passed to 30:1A54.  Its direct far-comparison adapter is also
    # a same-PC overlay; omitting either one eventually corrupts the stack.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_DRAW_CONTEXT_OVERLAY_DESTINATION,
        APPLICATION_DRAW_CONTEXT_OVERLAY_SOURCE,
        APPLICATION_DRAW_CONTEXT_OVERLAY_SIZE,
    ))
    words.extend(copy_code_to_overlay_words(
        APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_DESTINATION,
        APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_SOURCE,
        APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_SIZE,
    ))
    # 30:9F0E and 164 other sites pass four words to 27:507C. Its flat bytes
    # are mid-function; 44:507C is the complete LINK #0x0A dispatch body.
    words.extend(copy_code_to_overlay_words(
        ACTIVATION_DISPATCH_OVERLAY_DESTINATION,
        ACTIVATION_DISPATCH_OVERLAY_SOURCE,
        ACTIVATION_DISPATCH_OVERLAY_SIZE,
    ))
    # The application initializer's next one-word wrapper and its sole nested
    # setter are complete same-PC functions at 4E:C0E8 and 4E:4D24.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_PROPERTY_OVERLAY_DESTINATION,
        APPLICATION_PROPERTY_OVERLAY_SOURCE,
        APPLICATION_PROPERTY_OVERLAY_SIZE,
    ))
    words.extend(copy_code_to_overlay_words(
        PROPERTY_SETTER_OVERLAY_DESTINATION,
        PROPERTY_SETTER_OVERLAY_SOURCE,
        PROPERTY_SETTER_OVERLAY_SIZE,
    ))
    # 31:A914 calls 25:206E with five words. The flat destination is resource
    # data, while 42:206E is the complete same-PC LINK #6 implementation.
    words.extend(copy_code_to_overlay_words(
        LCD_RESOURCE_OVERLAY_DESTINATION,
        LCD_RESOURCE_OVERLAY_SOURCE,
        LCD_RESOURCE_OVERLAY_SIZE,
    ))
    words.extend(copy_code_to_overlay_words(
        LCD_RESOURCE_DISPATCH_THUNK_DESTINATION,
        LCD_RESOURCE_DISPATCH_THUNK_SOURCE,
        LCD_RESOURCE_DISPATCH_THUNK_SIZE,
    ))
    words.extend(copy_code_to_overlay_words(
        LCD_RESOURCE_TRANSFER_OVERLAY_DESTINATION,
        LCD_RESOURCE_TRANSFER_OVERLAY_SOURCE,
        LCD_RESOURCE_TRANSFER_OVERLAY_SIZE,
    ))
    words.extend(copy_code_to_overlay_words(
        APPLICATION_RESOURCE_PAGE_READ_OVERLAY_DESTINATION,
        APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SOURCE,
        APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SIZE,
    ))
    # 3F:979C calls 30:D350 without arguments. Its complete, call-free same-PC
    # timing/register initializer is stored at 4D:D350..4D:D430.
    words.extend(copy_code_to_overlay_words(
        LCD_TIMING_OVERLAY_DESTINATION,
        LCD_TIMING_OVERLAY_SOURCE,
        LCD_TIMING_OVERLAY_SIZE,
    ))
    # 3F:97D2 next calls a no-argument state initializer. Its only direct
    # dependency is the five-word memory-fill routine and adjacent ACALL
    # helper stored at the corresponding PCs in segment 4D.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_STATE_OVERLAY_DESTINATION,
        APPLICATION_STATE_OVERLAY_SOURCE,
        APPLICATION_STATE_OVERLAY_SIZE,
    ))
    words.extend(copy_code_to_overlay_words(
        MEMORY_FILL_OVERLAY_DESTINATION,
        MEMORY_FILL_OVERLAY_SOURCE,
        MEMORY_FILL_OVERLAY_SIZE,
    ))
    # 3F:9812 passes two words to 32:9B56; 4F:9B56 is the complete call-free
    # same-PC LINK #0 function with the matching two-word ABI.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_RANGE_OVERLAY_DESTINATION,
        APPLICATION_RANGE_OVERLAY_SOURCE,
        APPLICATION_RANGE_OVERLAY_SIZE,
    ))
    # The next no-argument initializer at 31:5EA0 has a complete same-PC body
    # at 4E:5EA0. Its two direct dependencies are likewise complete same-PC
    # functions in segment 4F: a no-argument table clear and a four-word copy.
    for destination, source, size in (
        (APPLICATION_TABLE_INIT_OVERLAY_DESTINATION,
         APPLICATION_TABLE_INIT_OVERLAY_SOURCE,
         APPLICATION_TABLE_INIT_OVERLAY_SIZE),
        (APPLICATION_TABLE_CLEAR_OVERLAY_DESTINATION,
         APPLICATION_TABLE_CLEAR_OVERLAY_SOURCE,
         APPLICATION_TABLE_CLEAR_OVERLAY_SIZE),
        (APPLICATION_BUFFER_COPY_OVERLAY_DESTINATION,
         APPLICATION_BUFFER_COPY_OVERLAY_SOURCE,
         APPLICATION_BUFFER_COPY_OVERLAY_SIZE),
    ):
        words.extend(copy_code_to_overlay_words(destination, source, size))
    # 3F:9844 passes one command byte to 2F:5B98. The flat target falsely
    # enters ROM03; 4C:5B98 is its complete seven-case dispatcher. Recover
    # both one-word table helpers and their shared four-word multiply helper.
    for destination, source, size in (
        (APPLICATION_COMMAND_OVERLAY_DESTINATION,
         APPLICATION_COMMAND_OVERLAY_SOURCE,
         APPLICATION_COMMAND_OVERLAY_SIZE),
        (COMMAND_TABLE_PRIMARY_OVERLAY_DESTINATION,
         COMMAND_TABLE_PRIMARY_OVERLAY_SOURCE,
         COMMAND_TABLE_PRIMARY_OVERLAY_SIZE),
        (COMMAND_TABLE_SECONDARY_OVERLAY_DESTINATION,
         COMMAND_TABLE_SECONDARY_OVERLAY_SOURCE,
         COMMAND_TABLE_SECONDARY_OVERLAY_SIZE),
        (COMMAND_TABLE_TERTIARY_OVERLAY_DESTINATION,
         COMMAND_TABLE_TERTIARY_OVERLAY_SOURCE,
         COMMAND_TABLE_TERTIARY_OVERLAY_SIZE),
        (COMMAND_TABLE_TEMPLATE_OVERLAY_DESTINATION,
         COMMAND_TABLE_TEMPLATE_OVERLAY_SOURCE,
         COMMAND_TABLE_TEMPLATE_OVERLAY_SIZE),
    ):
        words.extend(copy_code_to_overlay_words(destination, source, size))
    words.extend(embed_program_overlay_words(
        UINT32_MULTIPLY_OVERLAY_DESTINATION,
        UINT32_MULTIPLY_OVERLAY_SOURCE,
        UINT32_MULTIPLY_OVERLAY_SIZE,
    ))
    # 29:02D8 calls this one-byte storage-unit selector.  Its segment-50
    # source is later mutable RAM, so embed the shipped words just like the
    # adjacent 33:07B0 multiply helper instead of copying live source bytes.
    words.extend(embed_program_overlay_words(
        STORAGE_UNIT_SELECT_OVERLAY_DESTINATION,
        STORAGE_UNIT_SELECT_OVERLAY_SOURCE,
        STORAGE_UNIT_SELECT_OVERLAY_SIZE,
    ))
    # The exact resident application dispatcher enters 33:2562 once per
    # event-loop pass.  Both this gate and its 33:3980 bit setter live in the
    # mutable segment-50 source bank, so preserve their shipped words here.
    for destination, source, size in (
        (APPLICATION_EVENT_GATE_OVERLAY_DESTINATION,
         APPLICATION_EVENT_GATE_OVERLAY_SOURCE,
         APPLICATION_EVENT_GATE_OVERLAY_SIZE),
        (APPLICATION_EVENT_ENABLE_OVERLAY_DESTINATION,
         APPLICATION_EVENT_ENABLE_OVERLAY_SOURCE,
         APPLICATION_EVENT_ENABLE_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    # The resident dispatcher calls 32:4C34 after the event gate.  Its flat
    # bytes are an unrelated function middle, while 4F:4C34 is the complete
    # no-argument poll whose return keeps execution in the dispatcher.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_DISPATCH_POLL_OVERLAY_DESTINATION,
        APPLICATION_DISPATCH_POLL_OVERLAY_SOURCE,
        APPLICATION_DISPATCH_POLL_OVERLAY_SIZE,
    ))
    # The resident dispatcher polls the real input GPIO through 31:D9AA,
    # then evaluates the activity state in 2D:2D40.  The two segment-50
    # leaves must be embedded because their source bank is mutable RAM.
    for destination, source, size in (
        (APPLICATION_KEY_GPIO_SCAN_OVERLAY_DESTINATION,
         APPLICATION_KEY_GPIO_SCAN_OVERLAY_SOURCE,
         APPLICATION_KEY_GPIO_SCAN_OVERLAY_SIZE),
        (APPLICATION_KEY_ACTIVITY_OVERLAY_DESTINATION,
         APPLICATION_KEY_ACTIVITY_OVERLAY_SOURCE,
         APPLICATION_KEY_ACTIVITY_OVERLAY_SIZE),
    ):
        words.extend(copy_code_to_overlay_words(destination, source, size))
    for destination, source, size in (
        (APPLICATION_KEY_COUNTER_OVERLAY_DESTINATION,
         APPLICATION_KEY_COUNTER_OVERLAY_SOURCE,
         APPLICATION_KEY_COUNTER_OVERLAY_SIZE),
        (APPLICATION_KEY_SYNC_OVERLAY_DESTINATION,
         APPLICATION_KEY_SYNC_OVERLAY_SOURCE,
         APPLICATION_KEY_SYNC_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    # The application then passes two command coordinates to 30:D6D0. The
    # flat bytes are an epilogue tail; 4D:D6D0 is the complete call-free
    # bounds-check/table-update body with the matching two-word ABI.
    words.extend(copy_code_to_overlay_words(
        COMMAND_MATRIX_OVERLAY_DESTINATION,
        COMMAND_MATRIX_OVERLAY_SOURCE,
        COMMAND_MATRIX_OVERLAY_SIZE,
    ))
    # 3F:986A passes one mode byte to 32:CA88. The uncalled 4F:CA88 copy is
    # the complete, call-free validator/state update with a normal epilogue.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_MODE_OVERLAY_DESTINATION,
        APPLICATION_MODE_OVERLAY_SOURCE,
        APPLICATION_MODE_OVERLAY_SIZE,
    ))
    # 3F:988C passes a mode and slot to 32:9D22. Its complete 4F:9D22 body
    # validates both bytes and updates state without making nested calls.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_SLOT_OVERLAY_DESTINATION,
        APPLICATION_SLOT_OVERLAY_SOURCE,
        APPLICATION_SLOT_OVERLAY_SIZE,
    ))
    # The final state setters before 3F:98B0 enters the resident application
    # loop are complete same-PC functions at 4F:2102 and 50:3376. Segment 50
    # is mutable data at this point, so embed the latter's exact PRG words.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_TRIPLE_OVERLAY_DESTINATION,
        APPLICATION_TRIPLE_OVERLAY_SOURCE,
        APPLICATION_TRIPLE_OVERLAY_SIZE,
    ))
    words.extend(embed_program_overlay_words(
        APPLICATION_HW_STATE_OVERLAY_DESTINATION,
        APPLICATION_HW_STATE_OVERLAY_SOURCE,
        APPLICATION_HW_STATE_OVERLAY_SIZE,
    ))
    # On the zero-state branch the callback continues through another
    # segment-50 hardware query and the page/text setup pair. The latter's
    # sole previously missing direct dependency is the complete 45:1F08 body.
    words.extend(embed_program_overlay_words(
        APPLICATION_POWER_STATE_OVERLAY_DESTINATION,
        APPLICATION_POWER_STATE_OVERLAY_SOURCE,
        APPLICATION_POWER_STATE_OVERLAY_SIZE,
    ))
    # Segment 35 has already become application data RAM when this late
    # installer runs, so preserve the exact storage-unit initializer body.
    words.extend(embed_program_overlay_words(
        RESIDENT_STORAGE_UNIT_INIT_OVERLAY_DESTINATION,
        RESIDENT_STORAGE_UNIT_INIT_OVERLAY_SOURCE,
        RESIDENT_STORAGE_UNIT_INIT_OVERLAY_SIZE,
    ))
    for destination, source, size in (
        (APPLICATION_PAGE_SETUP_OVERLAY_DESTINATION,
         APPLICATION_PAGE_SETUP_OVERLAY_SOURCE,
         APPLICATION_PAGE_SETUP_OVERLAY_SIZE),
        (APPLICATION_TEXT_LOOP_OVERLAY_DESTINATION,
         APPLICATION_TEXT_LOOP_OVERLAY_SOURCE,
         APPLICATION_TEXT_LOOP_OVERLAY_SIZE),
        (APPLICATION_RESOURCE_LOOP_OVERLAY_DESTINATION,
         APPLICATION_RESOURCE_LOOP_OVERLAY_SOURCE,
         APPLICATION_RESOURCE_LOOP_OVERLAY_SIZE),
        (APPLICATION_STORAGE_CONTEXT_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_CONTEXT_OVERLAY_SOURCE,
         APPLICATION_STORAGE_CONTEXT_OVERLAY_SIZE),
        (APPLICATION_STORAGE_REGISTRY_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_REGISTRY_OVERLAY_SOURCE,
         APPLICATION_STORAGE_REGISTRY_OVERLAY_SIZE),
        (STORAGE_BAD_BLOCK_STATUS_OVERLAY_DESTINATION,
         STORAGE_BAD_BLOCK_STATUS_OVERLAY_SOURCE,
         STORAGE_BAD_BLOCK_STATUS_OVERLAY_SIZE),
        (APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_SOURCE,
         APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_SIZE),
        (STORAGE_UNIT_WORKER_OVERLAY_DESTINATION,
         STORAGE_UNIT_WORKER_OVERLAY_SOURCE,
         STORAGE_UNIT_WORKER_OVERLAY_SIZE),
        (STORAGE_PACKED_FIELD_OVERLAY_DESTINATION,
         STORAGE_PACKED_FIELD_OVERLAY_SOURCE,
         STORAGE_PACKED_FIELD_OVERLAY_SIZE),
        (STORAGE_SECONDARY_DRIVER_OVERLAY_DESTINATION,
         STORAGE_SECONDARY_DRIVER_OVERLAY_SOURCE,
         STORAGE_SECONDARY_DRIVER_OVERLAY_SIZE),
        (STORAGE_PRIMARY_READER_OVERLAY_DESTINATION,
         STORAGE_PRIMARY_READER_OVERLAY_SOURCE,
         STORAGE_PRIMARY_READER_OVERLAY_SIZE),
        (STORAGE_TRANSFER_WORKER_OVERLAY_DESTINATION,
         STORAGE_TRANSFER_WORKER_OVERLAY_SOURCE,
         STORAGE_TRANSFER_WORKER_OVERLAY_SIZE),
        (STORAGE_PRIMARY_TRANSFER_OVERLAY_DESTINATION,
         STORAGE_PRIMARY_TRANSFER_OVERLAY_SOURCE,
         STORAGE_PRIMARY_TRANSFER_OVERLAY_SIZE),
        (STORAGE_PRIMARY_SECTOR_READ_OVERLAY_DESTINATION,
         STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SOURCE,
         STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SIZE),
        (STORAGE_NAND_STATUS_OVERLAY_DESTINATION,
         STORAGE_NAND_STATUS_OVERLAY_SOURCE,
         STORAGE_NAND_STATUS_OVERLAY_SIZE),
        (STORAGE_BLOCK_TRANSFER_OVERLAY_DESTINATION,
         STORAGE_BLOCK_TRANSFER_OVERLAY_SOURCE,
         STORAGE_BLOCK_TRANSFER_OVERLAY_SIZE),
        (STORAGE_ASYNC_RANGE_OVERLAY_DESTINATION,
         STORAGE_ASYNC_RANGE_OVERLAY_SOURCE,
         STORAGE_ASYNC_RANGE_OVERLAY_SIZE),
        (STORAGE_RANGE_DISPATCH_OVERLAY_DESTINATION,
         STORAGE_RANGE_DISPATCH_OVERLAY_SOURCE,
         STORAGE_RANGE_DISPATCH_OVERLAY_SIZE),
        (STORAGE_FIELD_PARSE_OVERLAY_DESTINATION,
         STORAGE_FIELD_PARSE_OVERLAY_SOURCE,
         STORAGE_FIELD_PARSE_OVERLAY_SIZE),
        (STORAGE_BUFFER_DECODE_OVERLAY_DESTINATION,
         STORAGE_BUFFER_DECODE_OVERLAY_SOURCE,
         STORAGE_BUFFER_DECODE_OVERLAY_SIZE),
        (STORAGE_EVENT_POLL_OVERLAY_DESTINATION,
         STORAGE_EVENT_POLL_OVERLAY_SOURCE,
         STORAGE_EVENT_POLL_OVERLAY_SIZE),
        (STORAGE_RECORD_DISPATCH_OVERLAY_DESTINATION,
         STORAGE_RECORD_DISPATCH_OVERLAY_SOURCE,
         STORAGE_RECORD_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_RESULT_RECORD_PARSE_OVERLAY_DESTINATION,
         APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SOURCE,
         APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SIZE),
        (APPLICATION_RESULT_REGION_PREPARE_OVERLAY_DESTINATION,
         APPLICATION_RESULT_REGION_PREPARE_OVERLAY_SOURCE,
         APPLICATION_RESULT_REGION_PREPARE_OVERLAY_SIZE),
        (APPLICATION_RESULT_DISPLAY_SETUP_OVERLAY_DESTINATION,
         APPLICATION_RESULT_DISPLAY_SETUP_OVERLAY_SOURCE,
         APPLICATION_RESULT_DISPLAY_SETUP_OVERLAY_SIZE),
        (APPLICATION_RESULT_RESOURCE_RESET_OVERLAY_DESTINATION,
         APPLICATION_RESULT_RESOURCE_RESET_OVERLAY_SOURCE,
         APPLICATION_RESULT_RESOURCE_RESET_OVERLAY_SIZE),
        (APPLICATION_RESULT_BUILD_OVERLAY_DESTINATION,
         APPLICATION_RESULT_BUILD_OVERLAY_SOURCE,
         APPLICATION_RESULT_BUILD_OVERLAY_SIZE),
        (FAR_NORMALIZED_MEMORY_COMPARE_OVERLAY_DESTINATION,
         FAR_NORMALIZED_MEMORY_COMPARE_OVERLAY_SOURCE,
         FAR_NORMALIZED_MEMORY_COMPARE_OVERLAY_SIZE),
        (APPLICATION_STORAGE_ENTRY_ATTACH_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_ENTRY_ATTACH_OVERLAY_SOURCE,
         APPLICATION_STORAGE_ENTRY_ATTACH_OVERLAY_SIZE),
        (APPLICATION_POINTER_UPDATE_OVERLAY_DESTINATION,
         APPLICATION_POINTER_UPDATE_OVERLAY_SOURCE,
         APPLICATION_POINTER_UPDATE_OVERLAY_SIZE),
        (STORAGE_RUNTIME_STATE_RESET_OVERLAY_DESTINATION,
         STORAGE_RUNTIME_STATE_RESET_OVERLAY_SOURCE,
         STORAGE_RUNTIME_STATE_RESET_OVERLAY_SIZE),
        (STORAGE_RUNTIME_TABLE_RESET_OVERLAY_DESTINATION,
         STORAGE_RUNTIME_TABLE_RESET_OVERLAY_SOURCE,
         STORAGE_RUNTIME_TABLE_RESET_OVERLAY_SIZE),
        (APPLICATION_STORAGE_MAINTENANCE_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_MAINTENANCE_OVERLAY_SOURCE,
         APPLICATION_STORAGE_MAINTENANCE_OVERLAY_SIZE),
        (APPLICATION_STORAGE_BLOCK_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_BLOCK_OVERLAY_SOURCE,
         APPLICATION_STORAGE_BLOCK_OVERLAY_SIZE),
        (APPLICATION_STORAGE_SCAN_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_SCAN_OVERLAY_SOURCE,
         APPLICATION_STORAGE_SCAN_OVERLAY_SIZE),
        (APPLICATION_STORAGE_VERIFY_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_VERIFY_OVERLAY_SOURCE,
         APPLICATION_STORAGE_VERIFY_OVERLAY_SIZE),
        (APPLICATION_STORAGE_TRANSFER_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_TRANSFER_OVERLAY_SOURCE,
         APPLICATION_STORAGE_TRANSFER_OVERLAY_SIZE),
        (APPLICATION_STORAGE_MAP_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_MAP_OVERLAY_SOURCE,
         APPLICATION_STORAGE_MAP_OVERLAY_SIZE),
        (APPLICATION_STATE_DISPATCH_OVERLAY_DESTINATION,
         APPLICATION_STATE_DISPATCH_OVERLAY_SOURCE,
         APPLICATION_STATE_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_STATE_PREPARE_OVERLAY_DESTINATION,
         APPLICATION_STATE_PREPARE_OVERLAY_SOURCE,
         APPLICATION_STATE_PREPARE_OVERLAY_SIZE),
        (APPLICATION_STATE_POINTER_OVERLAY_DESTINATION,
         APPLICATION_STATE_POINTER_OVERLAY_SOURCE,
         APPLICATION_STATE_POINTER_OVERLAY_SIZE),
        (APPLICATION_STATE_RECORD_OVERLAY_DESTINATION,
         APPLICATION_STATE_RECORD_OVERLAY_SOURCE,
         APPLICATION_STATE_RECORD_OVERLAY_SIZE),
        (APPLICATION_STATE_CLASSIFY_OVERLAY_DESTINATION,
         APPLICATION_STATE_CLASSIFY_OVERLAY_SOURCE,
         APPLICATION_STATE_CLASSIFY_OVERLAY_SIZE),
        (APPLICATION_STATE_SERVICE_OVERLAY_DESTINATION,
         APPLICATION_STATE_SERVICE_OVERLAY_SOURCE,
         APPLICATION_STATE_SERVICE_OVERLAY_SIZE),
        (APPLICATION_STATE_TRANSFORM_OVERLAY_DESTINATION,
         APPLICATION_STATE_TRANSFORM_OVERLAY_SOURCE,
         APPLICATION_STATE_TRANSFORM_OVERLAY_SIZE),
        (APPLICATION_STATE_FLAGS_OVERLAY_DESTINATION,
         APPLICATION_STATE_FLAGS_OVERLAY_SOURCE,
         APPLICATION_STATE_FLAGS_OVERLAY_SIZE),
        (APPLICATION_STATE_POWER_OVERLAY_DESTINATION,
         APPLICATION_STATE_POWER_OVERLAY_SOURCE,
         APPLICATION_STATE_POWER_OVERLAY_SIZE),
        (APPLICATION_STATE_TICK_OVERLAY_DESTINATION,
         APPLICATION_STATE_TICK_OVERLAY_SOURCE,
         APPLICATION_STATE_TICK_OVERLAY_SIZE),
        (APPLICATION_STATE_TICK_SAMPLE_OVERLAY_DESTINATION,
         APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SOURCE,
         APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SIZE),
        (APPLICATION_STATE_TICK_COMMIT_OVERLAY_DESTINATION,
         APPLICATION_STATE_TICK_COMMIT_OVERLAY_SOURCE,
         APPLICATION_STATE_TICK_COMMIT_OVERLAY_SIZE),
        (APPLICATION_STATE_UI_OVERLAY_DESTINATION,
         APPLICATION_STATE_UI_OVERLAY_SOURCE,
         APPLICATION_STATE_UI_OVERLAY_SIZE),
        (APPLICATION_STATE_ADC_OVERLAY_DESTINATION,
         APPLICATION_STATE_ADC_OVERLAY_SOURCE,
         APPLICATION_STATE_ADC_OVERLAY_SIZE),
        (APPLICATION_CONTEXT_LOOKUP_OVERLAY_DESTINATION,
         APPLICATION_CONTEXT_LOOKUP_OVERLAY_SOURCE,
         APPLICATION_CONTEXT_LOOKUP_OVERLAY_SIZE),
        (APPLICATION_CONTEXT_PROPERTY_OVERLAY_DESTINATION,
         APPLICATION_CONTEXT_PROPERTY_OVERLAY_SOURCE,
         APPLICATION_CONTEXT_PROPERTY_OVERLAY_SIZE),
        (APPLICATION_WIDE_CONVERT_OVERLAY_DESTINATION,
         APPLICATION_WIDE_CONVERT_OVERLAY_SOURCE,
         APPLICATION_WIDE_CONVERT_OVERLAY_SIZE),
        (APPLICATION_MODAL_VALIDATION_OVERLAY_DESTINATION,
         APPLICATION_MODAL_VALIDATION_OVERLAY_SOURCE,
         APPLICATION_MODAL_VALIDATION_OVERLAY_SIZE),
        (APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_DESTINATION,
         APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_SOURCE,
         APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_DESTINATION,
         APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_SOURCE,
         APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_SIZE),
        (APPLICATION_MODAL_TEXT_FILTER_OVERLAY_DESTINATION,
         APPLICATION_MODAL_TEXT_FILTER_OVERLAY_SOURCE,
         APPLICATION_MODAL_TEXT_FILTER_OVERLAY_SIZE),
        (APPLICATION_MODAL_BUFFER_READ_OVERLAY_DESTINATION,
         APPLICATION_MODAL_BUFFER_READ_OVERLAY_SOURCE,
         APPLICATION_MODAL_BUFFER_READ_OVERLAY_SIZE),
        (APPLICATION_WIDE_GATE_OVERLAY_DESTINATION,
         APPLICATION_WIDE_GATE_OVERLAY_SOURCE,
         APPLICATION_WIDE_GATE_OVERLAY_SIZE),
        (APPLICATION_INDEX_ACTION_OVERLAY_DESTINATION,
         APPLICATION_INDEX_ACTION_OVERLAY_SOURCE,
         APPLICATION_INDEX_ACTION_OVERLAY_SIZE),
        (APPLICATION_PAGE_INDEX_OVERLAY_DESTINATION,
         APPLICATION_PAGE_INDEX_OVERLAY_SOURCE,
         APPLICATION_PAGE_INDEX_OVERLAY_SIZE),
        (APPLICATION_PAGE_FETCH_OVERLAY_DESTINATION,
         APPLICATION_PAGE_FETCH_OVERLAY_SOURCE,
         APPLICATION_PAGE_FETCH_OVERLAY_SIZE),
        (APPLICATION_RECT_DRAW_OVERLAY_DESTINATION,
         APPLICATION_RECT_DRAW_OVERLAY_SOURCE,
         APPLICATION_RECT_DRAW_OVERLAY_SIZE),
        (APPLICATION_IMAGE_WINDOW_OVERLAY_DESTINATION,
         APPLICATION_IMAGE_WINDOW_OVERLAY_SOURCE,
         APPLICATION_IMAGE_WINDOW_OVERLAY_SIZE),
        (APPLICATION_IMAGE_DISPATCH_OVERLAY_DESTINATION,
         APPLICATION_IMAGE_DISPATCH_OVERLAY_SOURCE,
         APPLICATION_IMAGE_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_EVENT_POLL_OVERLAY_DESTINATION,
         APPLICATION_EVENT_POLL_OVERLAY_SOURCE,
         APPLICATION_EVENT_POLL_OVERLAY_SIZE),
        (APPLICATION_TIMER_SETUP_OVERLAY_DESTINATION,
         APPLICATION_TIMER_SETUP_OVERLAY_SOURCE,
         APPLICATION_TIMER_SETUP_OVERLAY_SIZE),
        (UINT32_DIVIDE_OVERLAY_DESTINATION,
         UINT32_DIVIDE_OVERLAY_SOURCE,
         UINT32_DIVIDE_OVERLAY_SIZE),
        (APPLICATION_CONTEXT_LAUNCH_OVERLAY_DESTINATION,
         APPLICATION_CONTEXT_LAUNCH_OVERLAY_SOURCE,
         APPLICATION_CONTEXT_LAUNCH_OVERLAY_SIZE),
        (APPLICATION_RECORD_PREPARE_OVERLAY_DESTINATION,
         APPLICATION_RECORD_PREPARE_OVERLAY_SOURCE,
         APPLICATION_RECORD_PREPARE_OVERLAY_SIZE),
        (APPLICATION_ADDRESS_RESOLVE_OVERLAY_DESTINATION,
         APPLICATION_ADDRESS_RESOLVE_OVERLAY_SOURCE,
         APPLICATION_ADDRESS_RESOLVE_OVERLAY_SIZE),
        (FAR_STRING_LENGTH_OVERLAY_DESTINATION,
         FAR_STRING_LENGTH_OVERLAY_SOURCE,
         FAR_STRING_LENGTH_OVERLAY_SIZE),
        (APPLICATION_RECORD_SCAN_OVERLAY_DESTINATION,
         APPLICATION_RECORD_SCAN_OVERLAY_SOURCE,
         APPLICATION_RECORD_SCAN_OVERLAY_SIZE),
        (FAR_MEMORY_FILL_OVERLAY_DESTINATION,
         FAR_MEMORY_FILL_OVERLAY_SOURCE,
         FAR_MEMORY_FILL_OVERLAY_SIZE),
        (PACKED_TRIPLE_READ_OVERLAY_DESTINATION,
         PACKED_TRIPLE_READ_OVERLAY_SOURCE,
         PACKED_TRIPLE_READ_OVERLAY_SIZE),
        (APPLICATION_COMPARE_WRAPPER_OVERLAY_DESTINATION,
         APPLICATION_COMPARE_WRAPPER_OVERLAY_SOURCE,
         APPLICATION_COMPARE_WRAPPER_OVERLAY_SIZE),
        (FAR_MEMORY_COMPARE_OVERLAY_DESTINATION,
         FAR_MEMORY_COMPARE_OVERLAY_SOURCE,
         FAR_MEMORY_COMPARE_OVERLAY_SIZE),
        (FAR_POINTER_NORMALIZE_OVERLAY_DESTINATION,
         FAR_POINTER_NORMALIZE_OVERLAY_SOURCE,
         FAR_POINTER_NORMALIZE_OVERLAY_SIZE),
        # The exact 03:407C jump table entry selects 32:945C.  That wrapper
        # is a same-PC far-string copy and calls the adjacent recovered
        # far-memory copy implementation at 2E:4572.
        (FAR_STRING_COPY_OVERLAY_DESTINATION,
         FAR_STRING_COPY_OVERLAY_SOURCE,
         FAR_STRING_COPY_OVERLAY_SIZE),
        (FAR_MEMORY_COPY_OVERLAY_DESTINATION,
         FAR_MEMORY_COPY_OVERLAY_SOURCE,
         FAR_MEMORY_COPY_OVERLAY_SIZE),
        (APPLICATION_GLYPH_DRAW_OVERLAY_DESTINATION,
         APPLICATION_GLYPH_DRAW_OVERLAY_SOURCE,
         APPLICATION_GLYPH_DRAW_OVERLAY_SIZE),
        (CHARACTER_DRAW_OVERLAY_DESTINATION,
         CHARACTER_DRAW_OVERLAY_SOURCE,
         CHARACTER_DRAW_OVERLAY_SIZE),
        (FAR_STRING_CONCAT_OVERLAY_DESTINATION,
         FAR_STRING_CONCAT_OVERLAY_SOURCE,
         FAR_STRING_CONCAT_OVERLAY_SIZE),
        (RECORD_LAYOUT_WRAPPER_OVERLAY_DESTINATION,
         RECORD_LAYOUT_WRAPPER_OVERLAY_SOURCE,
         RECORD_LAYOUT_WRAPPER_OVERLAY_SIZE),
        (RECORD_LAYOUT_BUILD_OVERLAY_DESTINATION,
         RECORD_LAYOUT_BUILD_OVERLAY_SOURCE,
         RECORD_LAYOUT_BUILD_OVERLAY_SIZE),
        (APPLICATION_INPUT_MASK_OVERLAY_DESTINATION,
         APPLICATION_INPUT_MASK_OVERLAY_SOURCE,
         APPLICATION_INPUT_MASK_OVERLAY_SIZE),
        (INPUT_MASK_APPLY_OVERLAY_DESTINATION,
         INPUT_MASK_APPLY_OVERLAY_SOURCE,
         INPUT_MASK_APPLY_OVERLAY_SIZE),
        (APPLICATION_DISPLAY_STATE_OVERLAY_DESTINATION,
         APPLICATION_DISPLAY_STATE_OVERLAY_SOURCE,
         APPLICATION_DISPLAY_STATE_OVERLAY_SIZE),
        (APPLICATION_DISPLAY_RESET_OVERLAY_DESTINATION,
         APPLICATION_DISPLAY_RESET_OVERLAY_SOURCE,
         APPLICATION_DISPLAY_RESET_OVERLAY_SIZE),
        (APPLICATION_LIST_STATE_OVERLAY_DESTINATION,
         APPLICATION_LIST_STATE_OVERLAY_SOURCE,
         APPLICATION_LIST_STATE_OVERLAY_SIZE),
        (APPLICATION_LIST_ITEM_SET_OVERLAY_DESTINATION,
         APPLICATION_LIST_ITEM_SET_OVERLAY_SOURCE,
         APPLICATION_LIST_ITEM_SET_OVERLAY_SIZE),
        (APPLICATION_TABLE_MASK_OVERLAY_DESTINATION,
         APPLICATION_TABLE_MASK_OVERLAY_SOURCE,
         APPLICATION_TABLE_MASK_OVERLAY_SIZE),
        (APPLICATION_LIST_COMPACT_OVERLAY_DESTINATION,
         APPLICATION_LIST_COMPACT_OVERLAY_SOURCE,
         APPLICATION_LIST_COMPACT_OVERLAY_SIZE),
        (APPLICATION_LIST_CURSOR_OVERLAY_DESTINATION,
         APPLICATION_LIST_CURSOR_OVERLAY_SOURCE,
         APPLICATION_LIST_CURSOR_OVERLAY_SIZE),
        (APPLICATION_RANGE_FLAG_OVERLAY_DESTINATION,
         APPLICATION_RANGE_FLAG_OVERLAY_SOURCE,
         APPLICATION_RANGE_FLAG_OVERLAY_SIZE),
        (APPLICATION_DEVICE_VALIDATION_OVERLAY_DESTINATION,
         APPLICATION_DEVICE_VALIDATION_OVERLAY_SOURCE,
         APPLICATION_DEVICE_VALIDATION_OVERLAY_SIZE),
        (APPLICATION_RESOURCE_LOOKUP_OVERLAY_DESTINATION,
         APPLICATION_RESOURCE_LOOKUP_OVERLAY_SOURCE,
         APPLICATION_RESOURCE_LOOKUP_OVERLAY_SIZE),
        (APPLICATION_RESOURCE_DECODE_OVERLAY_DESTINATION,
         APPLICATION_RESOURCE_DECODE_OVERLAY_SOURCE,
         APPLICATION_RESOURCE_DECODE_OVERLAY_SIZE),
        (APPLICATION_RESOURCE_OPEN_OVERLAY_DESTINATION,
         APPLICATION_RESOURCE_OPEN_OVERLAY_SOURCE,
         APPLICATION_RESOURCE_OPEN_OVERLAY_SIZE),
        (INT32_DIVIDE_OVERLAY_DESTINATION,
         INT32_DIVIDE_OVERLAY_SOURCE,
         INT32_DIVIDE_OVERLAY_SIZE),
        (WIDE_FROM_INT16_OVERLAY_DESTINATION,
         WIDE_FROM_INT16_OVERLAY_SOURCE,
         WIDE_FROM_INT16_OVERLAY_SIZE),
        (WIDE_COMPARE_OVERLAY_DESTINATION,
         WIDE_COMPARE_OVERLAY_SOURCE,
         WIDE_COMPARE_OVERLAY_SIZE),
        (WIDE_OPERATION_DISPATCH_OVERLAY_DESTINATION,
         WIDE_OPERATION_DISPATCH_OVERLAY_SOURCE,
         WIDE_OPERATION_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_COMPARE_MODE_OVERLAY_DESTINATION,
         APPLICATION_COMPARE_MODE_OVERLAY_SOURCE,
         APPLICATION_COMPARE_MODE_OVERLAY_SIZE),
        (WIDE_ARITHMETIC_OVERLAY_DESTINATION,
         WIDE_ARITHMETIC_OVERLAY_SOURCE,
         WIDE_ARITHMETIC_OVERLAY_SIZE),
        (WIDE_ARITHMETIC_PREFIX_OVERLAY_DESTINATION,
         WIDE_ARITHMETIC_PREFIX_OVERLAY_SOURCE,
         WIDE_ARITHMETIC_PREFIX_OVERLAY_SIZE),
        (WIDE_VALUE_OPERATOR_OVERLAY_DESTINATION,
         WIDE_VALUE_OPERATOR_OVERLAY_SOURCE,
         WIDE_VALUE_OPERATOR_OVERLAY_SIZE),
        (WIDE_DIVIDE_STEP_OVERLAY_DESTINATION,
         WIDE_DIVIDE_STEP_OVERLAY_SOURCE,
         WIDE_DIVIDE_STEP_OVERLAY_SIZE),
        (APPLICATION_KEY_MODE_OVERLAY_DESTINATION,
         APPLICATION_KEY_MODE_OVERLAY_SOURCE,
         APPLICATION_KEY_MODE_OVERLAY_SIZE),
        (APPLICATION_KEY_ITEM_REFRESH_OVERLAY_DESTINATION,
         APPLICATION_KEY_ITEM_REFRESH_OVERLAY_SOURCE,
         APPLICATION_KEY_ITEM_REFRESH_OVERLAY_SIZE),
        (APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_DESTINATION,
         APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_SOURCE,
         APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_SIZE),
        (APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_DESTINATION,
         APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_SOURCE,
         APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_SIZE),
        (APPLICATION_KEY_SPECIAL_CRC_OVERLAY_DESTINATION,
         APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SOURCE,
         APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SIZE),
        (APPLICATION_KEY_SPECIAL_CRC_TABLE_DESTINATION,
         APPLICATION_KEY_SPECIAL_CRC_TABLE_SOURCE,
         APPLICATION_KEY_SPECIAL_CRC_TABLE_SIZE),
        (APPLICATION_KEY_SPECIAL_RESET_OVERLAY_DESTINATION,
         APPLICATION_KEY_SPECIAL_RESET_OVERLAY_SOURCE,
         APPLICATION_KEY_SPECIAL_RESET_OVERLAY_SIZE),
        (APPLICATION_KEY_INPUT_STATE_OVERLAY_DESTINATION,
         APPLICATION_KEY_INPUT_STATE_OVERLAY_SOURCE,
         APPLICATION_KEY_INPUT_STATE_OVERLAY_SIZE),
        (APPLICATION_KEY_DISPATCH_OVERLAY_DESTINATION,
         APPLICATION_KEY_DISPATCH_OVERLAY_SOURCE,
         APPLICATION_KEY_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_DESTINATION,
         APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_SOURCE,
         APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_SIZE),
        (APPLICATION_BIT_OR_OVERLAY_DESTINATION,
         APPLICATION_BIT_OR_OVERLAY_SOURCE,
         APPLICATION_BIT_OR_OVERLAY_SIZE),
        (APPLICATION_BIT_AND_OVERLAY_DESTINATION,
         APPLICATION_BIT_AND_OVERLAY_SOURCE,
         APPLICATION_BIT_AND_OVERLAY_SIZE),
        (APPLICATION_PAIR_STORE_OVERLAY_DESTINATION,
         APPLICATION_PAIR_STORE_OVERLAY_SOURCE,
         APPLICATION_PAIR_STORE_OVERLAY_SIZE),
    ):
        words.extend(copy_code_to_overlay_words(destination, source, size))
    # 30:A4A4 originally reloads A2:2AE0 immediately after the only call to
    # resident 18:F97C. Replace that load after copying the unit-open overlay
    # with a call to a resident cleanup thunk; the thunk restores the displaced
    # load before returning to A4A8.
    if program_source_words(
            APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_SOURCE +
            (APPLICATION_STORAGE_UNIT_OPEN_RETIRE_CALL_ADDRESS -
             APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_DESTINATION), 4
    ) != [0x88F0, 0x2AE0]:
        raise ValueError("storage-unit-open retirement call signature changed")
    words.extend(write_program_words(
        APPLICATION_STORAGE_UNIT_OPEN_RETIRE_CALL_ADDRESS,
        (0xBD00 | (STORAGE_DRIVER_RETIRE_ADDRESS >> 16),
         STORAGE_DRIVER_RETIRE_ADDRESS & 0xFFFF),
    ))
    # 42:CC94 contains the other installed direct call to logical 33:5906.
    # Patch only that call after copying the otherwise exact resource worker;
    # this preserves flat 33:5906 and keeps all execution in guest DMCU code.
    resource_call = (APPLICATION_RESOURCE_LOOP_OVERLAY_DESTINATION +
                     APPLICATION_RESOURCE_LOOP_SYSTEM_BITS_CALL_OFFSET)
    if program_source_words(
            APPLICATION_RESOURCE_LOOP_OVERLAY_SOURCE +
            APPLICATION_RESOURCE_LOOP_SYSTEM_BITS_CALL_OFFSET, 4
    ) != [0xBD33, 0x5906]:
        raise ValueError("resource-loop system-bits call signature changed")
    words.extend(write_program_words(
        resource_call,
        (0xBD00 | (SYSTEM_BITS_RESIDENT_ADDRESS >> 16),
         SYSTEM_BITS_RESIDENT_ADDRESS & 0xFFFF),
    ))
    words.extend(embed_program_overlay_words(
        WIDE_SHIFT_RIGHT_OVERLAY_DESTINATION,
        WIDE_SHIFT_RIGHT_OVERLAY_SOURCE,
        WIDE_SHIFT_RIGHT_OVERLAY_SIZE,
    ))
    # The resource loop reaches a pair of adjacent segment-50 device-state
    # helpers. Segment 50 has already become mutable RAM, so retain their
    # exact updater-image words in the installer instead of reading it back.
    for destination, source, size in (
        (APPLICATION_DEVICE_QUERY_OVERLAY_DESTINATION,
         APPLICATION_DEVICE_QUERY_OVERLAY_SOURCE,
         APPLICATION_DEVICE_QUERY_OVERLAY_SIZE),
        (APPLICATION_DEVICE_APPLY_OVERLAY_DESTINATION,
         APPLICATION_DEVICE_APPLY_OVERLAY_SOURCE,
         APPLICATION_DEVICE_APPLY_OVERLAY_SIZE),
        (APPLICATION_STATE_MODE_OVERLAY_DESTINATION,
         APPLICATION_STATE_MODE_OVERLAY_SOURCE,
         APPLICATION_STATE_MODE_OVERLAY_SIZE),
        (APPLICATION_EVENT_INDEX_OVERLAY_DESTINATION,
         APPLICATION_EVENT_INDEX_OVERLAY_SOURCE,
         APPLICATION_EVENT_INDEX_OVERLAY_SIZE),
        (APPLICATION_EVENT_CLASSIFY_OVERLAY_DESTINATION,
         APPLICATION_EVENT_CLASSIFY_OVERLAY_SOURCE,
         APPLICATION_EVENT_CLASSIFY_OVERLAY_SIZE),
        (APPLICATION_TEXT_DISPATCH_OVERLAY_DESTINATION,
         APPLICATION_TEXT_DISPATCH_OVERLAY_SOURCE,
         APPLICATION_TEXT_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_TEXT_DISPATCH_F0_OVERLAY_DESTINATION,
         APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SOURCE,
         APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SIZE),
        (APPLICATION_STATE_COMMIT_OVERLAY_DESTINATION,
         APPLICATION_STATE_COMMIT_OVERLAY_SOURCE,
         APPLICATION_STATE_COMMIT_OVERLAY_SIZE),
        (APPLICATION_EVENT_CONTROL_OVERLAY_DESTINATION,
         APPLICATION_EVENT_CONTROL_OVERLAY_SOURCE,
         APPLICATION_EVENT_CONTROL_OVERLAY_SIZE),
        (APPLICATION_OBJECT_RELEASE_OVERLAY_DESTINATION,
         APPLICATION_OBJECT_RELEASE_OVERLAY_SOURCE,
         APPLICATION_OBJECT_RELEASE_OVERLAY_SIZE),
        (APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_DESTINATION,
         APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SOURCE,
         APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SIZE),
        (APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_DESTINATION,
         APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SOURCE,
         APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SIZE),
        (APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_DESTINATION,
         APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SOURCE,
         APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SIZE),
        (APPLICATION_ASCII_WHITESPACE_OVERLAY_DESTINATION,
         APPLICATION_ASCII_WHITESPACE_OVERLAY_SOURCE,
         APPLICATION_ASCII_WHITESPACE_OVERLAY_SIZE),
        (UINT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
         UINT32_MODULO_WRAPPER_OVERLAY_SOURCE,
         UINT32_MODULO_WRAPPER_OVERLAY_SIZE),
        (INT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
         INT32_MODULO_WRAPPER_OVERLAY_SOURCE,
         INT32_MODULO_WRAPPER_OVERLAY_SIZE),
        (UINT32_DIVIDE_WRAPPER_OVERLAY_DESTINATION,
         UINT32_DIVIDE_WRAPPER_OVERLAY_SOURCE,
         UINT32_DIVIDE_WRAPPER_OVERLAY_SIZE),
        (UINT32_MSB_INDEX_OVERLAY_DESTINATION,
         UINT32_MSB_INDEX_OVERLAY_SOURCE,
         UINT32_MSB_INDEX_OVERLAY_SIZE),
        (UINT32_NORMALIZE_OVERLAY_DESTINATION,
         UINT32_NORMALIZE_OVERLAY_SOURCE,
         UINT32_NORMALIZE_OVERLAY_SIZE),
        (APPLICATION_RECORD_DISPATCH_OVERLAY_DESTINATION,
         APPLICATION_RECORD_DISPATCH_OVERLAY_SOURCE,
         APPLICATION_RECORD_DISPATCH_OVERLAY_SIZE),
        (INT32_DIVIDE_WRAPPER_OVERLAY_DESTINATION,
         INT32_DIVIDE_WRAPPER_OVERLAY_SOURCE,
         INT32_DIVIDE_WRAPPER_OVERLAY_SIZE),
        (WIDE_REGISTER_DISPATCH_OVERLAY_DESTINATION,
         WIDE_REGISTER_DISPATCH_OVERLAY_SOURCE,
         WIDE_REGISTER_DISPATCH_OVERLAY_SIZE),
        (WIDE_SIGN_NORMALIZE_OVERLAY_DESTINATION,
         WIDE_SIGN_NORMALIZE_OVERLAY_SOURCE,
         WIDE_SIGN_NORMALIZE_OVERLAY_SIZE),
        (WIDE_LEFT_NONZERO_OVERLAY_DESTINATION,
         WIDE_LEFT_NONZERO_OVERLAY_SOURCE,
         WIDE_LEFT_NONZERO_OVERLAY_SIZE),
        (WIDE_RIGHT_NONZERO_OVERLAY_DESTINATION,
         WIDE_RIGHT_NONZERO_OVERLAY_SOURCE,
         WIDE_RIGHT_NONZERO_OVERLAY_SIZE),
        (APPLICATION_KEY_ITEM_CLEAR_OVERLAY_DESTINATION,
         APPLICATION_KEY_ITEM_CLEAR_OVERLAY_SOURCE,
         APPLICATION_KEY_ITEM_CLEAR_OVERLAY_SIZE),
        (APPLICATION_KEY_ITEM_SET_OVERLAY_DESTINATION,
         APPLICATION_KEY_ITEM_SET_OVERLAY_SOURCE,
         APPLICATION_KEY_ITEM_SET_OVERLAY_SIZE),
        (APPLICATION_KEY_HW_PATH_A_OVERLAY_DESTINATION,
         APPLICATION_KEY_HW_PATH_A_OVERLAY_SOURCE,
         APPLICATION_KEY_HW_PATH_A_OVERLAY_SIZE),
        (APPLICATION_KEY_HW_PATH_B_OVERLAY_DESTINATION,
         APPLICATION_KEY_HW_PATH_B_OVERLAY_SOURCE,
         APPLICATION_KEY_HW_PATH_B_OVERLAY_SIZE),
        (APPLICATION_KEY_COMPLETION_OVERLAY_DESTINATION,
         APPLICATION_KEY_COMPLETION_OVERLAY_SOURCE,
         APPLICATION_KEY_COMPLETION_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    words.extend((
        0xBD00 | (APPLICATION_FACTORY_DEFAULT_INSTALLER_ADDRESS >> 16),
        APPLICATION_FACTORY_DEFAULT_INSTALLER_ADDRESS & 0xFFFF,
    ))
    words.extend(install_application_main_chain_words())
    # This destination overlaps the beginning of the installer itself.  Keep
    # this as the final operation: by now execution is beyond 05:2C90 and the
    # exact function can replace only loader instructions already consumed.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_MAIN_RECORD_LOAD_OVERLAY_DESTINATION,
        APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SOURCE,
        APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SIZE,
    ))
    return words


def application_factory_default_installer_words() -> list[int]:
    """Install exact factory-default and state-50 setup call closures."""
    words: list[int] = []
    for destination, source, size in APPLICATION_FACTORY_DEFAULT_COPY_OVERLAYS:
        words.extend(copy_code_to_overlay_words(destination, source, size))
    for destination, source, size in (
            APPLICATION_FACTORY_DEFAULT_EMBEDDED_OVERLAYS):
        words.extend(embed_program_overlay_words(destination, source, size))
    # Source 48:8056 is otherwise a same-PC overlay, but its 30:6E9E child
    # collides with a live flat function.  Reuse the already recovered
    # collision-safe resident storage-pair implementation at 07:4000.
    if program_source_words(
            APPLICATION_FOREGROUND_STATE50_STORAGE_PAIR_CALL_SOURCE, 4
    ) != [0xBD30, 0x6E9E]:
        raise ValueError("state-50 storage-pair call signature changed")
    words.extend(write_program_words(
        APPLICATION_FOREGROUND_STATE50_STORAGE_PAIR_CALL,
        (0xBD00 | (RESIDENT_STORAGE_PAIR_ADDRESS >> 16),
         RESIDENT_STORAGE_PAIR_ADDRESS & 0xFFFF),
    ))
    words.append(RETS)
    return words


def menu_runtime_overlay_installer_words() -> list[int]:
    """Install the exact catalogue, registry, menu, and cursor dependencies."""
    # Initialize the standard DES tables before any restored resource loader
    # can reach resident 02:DEA6.  This is a guest SCALL to guest code.
    result: list[int] = [
        0xBD00 | (DES_TABLE_INITIALIZER_ADDRESS >> 16),
        DES_TABLE_INITIALIZER_ADDRESS & 0xFFFF,
        0xBD00 | (APPLICATION_MENU_RESOURCE_DECODER_INSTALLER_ADDRESS >> 16),
        APPLICATION_MENU_RESOURCE_DECODER_INSTALLER_ADDRESS & 0xFFFF,
    ]
    for destination, source, size in (
        (APPLICATION_MENU_CATALOG_OVERLAY_DESTINATION,
         APPLICATION_MENU_CATALOG_OVERLAY_SOURCE,
         APPLICATION_MENU_CATALOG_OVERLAY_SIZE),
        (APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_DESTINATION,
         APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SOURCE,
         APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SIZE),
        (APPLICATION_REGISTRY_OVERLAY_DESTINATION,
         APPLICATION_REGISTRY_OVERLAY_SOURCE,
         APPLICATION_REGISTRY_OVERLAY_SIZE),
        (APPLICATION_REGISTRY_LOOKUP_OVERLAY_DESTINATION,
         APPLICATION_REGISTRY_LOOKUP_OVERLAY_SOURCE,
         APPLICATION_REGISTRY_LOOKUP_OVERLAY_SIZE),
        (APPLICATION_UNALIGNED_U16_OVERLAY_DESTINATION,
         APPLICATION_UNALIGNED_U16_OVERLAY_SOURCE,
         APPLICATION_UNALIGNED_U16_OVERLAY_SIZE),
        (APPLICATION_MENU_TEXT_INPUT_OVERLAY_DESTINATION,
         APPLICATION_MENU_TEXT_INPUT_OVERLAY_SOURCE,
         APPLICATION_MENU_TEXT_INPUT_OVERLAY_SIZE),
        (APPLICATION_MENU_UI_ADAPTER_OVERLAY_DESTINATION,
         APPLICATION_MENU_UI_ADAPTER_OVERLAY_SOURCE,
         APPLICATION_MENU_UI_ADAPTER_OVERLAY_SIZE),
        (APPLICATION_MENU_POSITION_OVERLAY_DESTINATION,
         APPLICATION_MENU_POSITION_OVERLAY_SOURCE,
         APPLICATION_MENU_POSITION_OVERLAY_SIZE),
        (APPLICATION_MENU_COORDINATE_OVERLAY_DESTINATION,
         APPLICATION_MENU_COORDINATE_OVERLAY_SOURCE,
         APPLICATION_MENU_COORDINATE_OVERLAY_SIZE),
        (APPLICATION_MENU_RENDER_OVERLAY_DESTINATION,
         APPLICATION_MENU_RENDER_OVERLAY_SOURCE,
         APPLICATION_MENU_RENDER_OVERLAY_SIZE),
        (APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_DESTINATION,
         APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SOURCE,
         APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SIZE),
        (APPLICATION_MENU_RESOURCE_BIND_OVERLAY_DESTINATION,
         APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SOURCE,
         APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SIZE),
        (APPLICATION_MENU_RESULT_ATTACH_OVERLAY_DESTINATION,
         APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SOURCE,
         APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SIZE),
        (APPLICATION_MENU_RESULT_LIST_OVERLAY_DESTINATION,
         APPLICATION_MENU_RESULT_LIST_OVERLAY_SOURCE,
         APPLICATION_MENU_RESULT_LIST_OVERLAY_SIZE),
        (APPLICATION_MENU_RESULT_PROCESS_OVERLAY_DESTINATION,
         APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SOURCE,
         APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SIZE),
        (APPLICATION_MENU_PAGE_POPULATE_OVERLAY_DESTINATION,
         APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SOURCE,
         APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SIZE),
        (APPLICATION_MENU_TEXT_EXPAND_OVERLAY_DESTINATION,
         APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SOURCE,
         APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SIZE),
        (APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_DESTINATION,
         APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SOURCE,
         APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SIZE),
        (APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_DESTINATION,
         APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE,
         APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SIZE),
        (APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_DESTINATION,
         APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SOURCE,
         APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_EVENT_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_EVENT_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_EVENT_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SIZE),
        (APPLICATION_MENU_POWER_STATE_OVERLAY_DESTINATION,
         APPLICATION_MENU_POWER_STATE_OVERLAY_SOURCE,
         APPLICATION_MENU_POWER_STATE_OVERLAY_SIZE),
        (APPLICATION_GENERIC_MENU_OVERLAY_DESTINATION,
         APPLICATION_GENERIC_MENU_OVERLAY_SOURCE,
         APPLICATION_GENERIC_MENU_OVERLAY_SIZE),
        (APPLICATION_CONTEXT_GATE_OVERLAY_DESTINATION,
         APPLICATION_CONTEXT_GATE_OVERLAY_SOURCE,
         APPLICATION_CONTEXT_GATE_OVERLAY_SIZE),
        (APPLICATION_RECORD_XOR_OVERLAY_DESTINATION,
         APPLICATION_RECORD_XOR_OVERLAY_SOURCE,
         APPLICATION_RECORD_XOR_OVERLAY_SIZE),
        (APPLICATION_MENU_TABLE_BUILD_OVERLAY_DESTINATION,
         APPLICATION_MENU_TABLE_BUILD_OVERLAY_SOURCE,
         APPLICATION_MENU_TABLE_BUILD_OVERLAY_SIZE),
        (APPLICATION_MENU_XOR_U16_OVERLAY_DESTINATION,
         APPLICATION_MENU_XOR_U16_OVERLAY_SOURCE,
         APPLICATION_MENU_XOR_U16_OVERLAY_SIZE),
        (APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_DESTINATION,
         APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_SOURCE,
         APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_SIZE),
        (APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_DESTINATION,
         APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_SOURCE,
         APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_SIZE),
        (APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_DESTINATION,
         APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_SOURCE,
         APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_SIZE),
        # The bootstrap foreground reuses 32:082E after the cold installer.
        # Restore the exact seven-argument record/text adapter at the menu
        # lifecycle boundary before page objects begin rendering.
        (STORAGE_RECORD_DISPATCH_OVERLAY_DESTINATION,
         STORAGE_RECORD_DISPATCH_OVERLAY_SOURCE,
         STORAGE_RECORD_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_TEXT_LOOP_OVERLAY_DESTINATION,
         APPLICATION_TEXT_LOOP_OVERLAY_SOURCE,
         APPLICATION_TEXT_LOOP_OVERLAY_SIZE),
        (APPLICATION_GLYPH_DRAW_OVERLAY_DESTINATION,
         APPLICATION_GLYPH_DRAW_OVERLAY_SOURCE,
         APPLICATION_GLYPH_DRAW_OVERLAY_SIZE),
        # Direct child of the 33:1BBA mode-pair wrapper below.
        (COMMAND_MATRIX_OVERLAY_DESTINATION,
         COMMAND_MATRIX_OVERLAY_SOURCE,
         COMMAND_MATRIX_OVERLAY_SIZE),
    ):
        result.extend(copy_code_to_overlay_words(destination, source, size))
    # The normal application lifecycle retires 2D:3460 before the resident
    # manager can reopen a menu.  Its shipped source bank 4A is writable by
    # this late boundary as well, so copying that live bank back would install
    # zeros.  Keep 2A:D374 exact except for its source-proven child call and
    # route that call to the immutable, exact relocated copy at 07:4000.
    if program_source_words(
            APPLICATION_STORAGE_RECORD_LOOKUP_DRIVER_CALL_SOURCE, 4
    ) != [0xBD2D, 0x3460]:
        raise ValueError("storage record-lookup driver call signature changed")
    result.extend(write_program_words(
        APPLICATION_STORAGE_RECORD_LOOKUP_DRIVER_CALL,
        (0xBD00 | (RESIDENT_STORAGE_DRIVER_ADDRESS >> 16),
         RESIDENT_STORAGE_DRIVER_ADDRESS & 0xFFFF),
    ))
    # These source-50 leaves are mutable by this late boundary.  Reinstall the
    # complete direct call closure of 32:082E, plus the far-copy thunk used by
    # its 33:68xx foreground callers, from immutable ROM-held words.
    for destination, source, size in (
        (ROM03_FAR_MEMCPY_THUNK_DESTINATION,
         ROM03_FAR_MEMCPY_THUNK_SOURCE,
         ROM03_FAR_MEMCPY_THUNK_SIZE),
        (APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION,
         APPLICATION_RESULT_MODE_PAIR_OVERLAY_SOURCE,
         APPLICATION_RESULT_MODE_PAIR_OVERLAY_SIZE),
        (APPLICATION_TEXT_DISPATCH_OVERLAY_DESTINATION,
         APPLICATION_TEXT_DISPATCH_OVERLAY_SOURCE,
         APPLICATION_TEXT_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_TEXT_DISPATCH_F0_OVERLAY_DESTINATION,
         APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SOURCE,
         APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SIZE),
    ):
        result.extend(embed_program_overlay_words(destination, source, size))
    # The application loader reuses source bank 46 before this resident/menu
    # boundary.  Reinstall the immutable ROM-held copy rather than reading
    # those live source bytes again.
    result.extend((
        0xBD00 | (APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS >> 16),
        APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS & 0xFFFF,
    ))
    # The bootstrap foreground also reuses the segment-33 result-table window.
    # Reinstall these two complete source-50 leaves at the resident-manager
    # boundary; otherwise 31:138C enters stale foreground code at 33:51E0 and
    # unwinds its caller from the unrelated 33:52A8 path before the menu event
    # dispatcher at 18:9A58 can run.
    result.extend((
        0xBD00 | (MENU_RESULT_TABLE_INSTALLER_ADDRESS >> 16),
        MENU_RESULT_TABLE_INSTALLER_ADDRESS & 0xFFFF,
        0xBD00 | (MENU_EVENT_STATE_INSTALLER_ADDRESS >> 16),
        MENU_EVENT_STATE_INSTALLER_ADDRESS & 0xFFFF,
    ))
    result.extend(embed_program_overlay_words(
        APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_DESTINATION,
        APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SOURCE,
        APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SIZE,
    ))
    # Segment 50 is writable application RAM before the resident manager can
    # reinstall a menu after the bootstrap foreground returns.  Retain this
    # exact wrapper in ROM instead of copying whatever application data now
    # occupies its updater-image source address.
    result.extend(embed_program_overlay_words(
        APPLICATION_UI_FINALIZE_OVERLAY_DESTINATION,
        APPLICATION_UI_FINALIZE_OVERLAY_SOURCE,
        APPLICATION_UI_FINALIZE_OVERLAY_SIZE,
    ))
    result.extend((
        0xBD00 | (MENU_ARITHMETIC_WRAPPER_INSTALLER_ADDRESS >> 16),
        MENU_ARITHMETIC_WRAPPER_INSTALLER_ADDRESS & 0xFFFF,
        0xBD00 | (APPLICATION_MENU_TEXT_STREAM_INSTALLER_ADDRESS >> 16),
        APPLICATION_MENU_TEXT_STREAM_INSTALLER_ADDRESS & 0xFFFF,
    ))
    result.append(RETS)
    return result


def menu_catalog_early_installer_words() -> list[int]:
    """Initialize DES and publish the catalogue before bootstrap rendering."""
    return [
        0xBD00 | (DES_TABLE_INITIALIZER_ADDRESS >> 16),
        DES_TABLE_INITIALIZER_ADDRESS & 0xFFFF,
        *copy_code_to_overlay_words(
            APPLICATION_MENU_CATALOG_OVERLAY_DESTINATION,
            APPLICATION_MENU_CATALOG_OVERLAY_SOURCE,
            APPLICATION_MENU_CATALOG_OVERLAY_SIZE,
        ),
        RETS,
    ]


def menu_arithmetic_wrapper_installer_words() -> list[int]:
    """Reinstall exact mutable-bank helpers after the menu application load."""
    words: list[int] = []
    for destination, source, size in (
        (APPLICATION_OBJECT_RELEASE_OVERLAY_DESTINATION,
         APPLICATION_OBJECT_RELEASE_OVERLAY_SOURCE,
         APPLICATION_OBJECT_RELEASE_OVERLAY_SIZE),
        (APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_DESTINATION,
         APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SOURCE,
         APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SIZE),
        (APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_DESTINATION,
         APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SOURCE,
         APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SIZE),
        (APPLICATION_ASCII_WHITESPACE_OVERLAY_DESTINATION,
         APPLICATION_ASCII_WHITESPACE_OVERLAY_SOURCE,
         APPLICATION_ASCII_WHITESPACE_OVERLAY_SIZE),
        (WIDE_FROM_INT16_OVERLAY_DESTINATION,
         WIDE_FROM_INT16_OVERLAY_SOURCE,
         WIDE_FROM_INT16_OVERLAY_SIZE),
        (UINT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
         UINT32_MODULO_WRAPPER_OVERLAY_SOURCE,
         UINT32_MODULO_WRAPPER_OVERLAY_SIZE),
        (INT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
         INT32_MODULO_WRAPPER_OVERLAY_SOURCE,
         INT32_MODULO_WRAPPER_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    words.extend((
        0xBD00 | (MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS >> 16),
        MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS & 0xFFFF,
    ))
    words.append(RETS)
    return words


def application_cursor_refresh_installer_words() -> list[int]:
    """Restore late application bodies after the mutable banks are loaded."""
    words: list[int] = []
    for destination, source, size in (
        (APPLICATION_CURSOR_REFRESH_OVERLAY_DESTINATION,
         APPLICATION_CURSOR_REFRESH_OVERLAY_SOURCE,
         APPLICATION_CURSOR_REFRESH_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    # 4A:9DFC remains readable on the natural data bus and therefore needs
    # only the compact byte-copy loop.  Embedding all 0x1AC exact bytes would
    # overflow this reserved ROM06 installer window into the 06:4600 wrapper.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_DESTINATION,
        APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_SOURCE,
        APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_SIZE,
    ))
    words.append(RETS)
    return words


def application_menu_text_stream_installer_words() -> list[int]:
    """Install the exact late-menu text stream parser from immutable words."""
    return [
        *embed_program_overlay_words(
            APPLICATION_MENU_TEXT_STREAM_OVERLAY_DESTINATION,
            APPLICATION_MENU_TEXT_STREAM_OVERLAY_SOURCE,
            APPLICATION_MENU_TEXT_STREAM_OVERLAY_SIZE,
        ),
        RETS,
    ]


def application_main_cursor_refresh_wrapper_words() -> list[int]:
    """Restore the redraw overlay after application loading, then enter main."""
    return [
        0xBD00 | (APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS >> 16),
        APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS & 0xFFFF,
        0xBD00 | (APPLICATION_MAIN_LOOP_OVERLAY_DESTINATION >> 16),
        APPLICATION_MAIN_LOOP_OVERLAY_DESTINATION & 0xFFFF,
        RETS,
    ]


def menu_decimal_parse_engine_installer_words() -> list[int]:
    """Reinstall the complete source-41 parser in a separate ROM06 gap."""
    words = embed_program_overlay_words(
        APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_DESTINATION,
        APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SOURCE,
        APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SIZE,
    )
    words.append(RETS)
    return words


def menu_result_table_installer_words() -> list[int]:
    """Restore the menu table wrappers and their record-walker closure."""
    words: list[int] = []
    for destination, source, size in (
        (APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_DESTINATION,
         APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_SOURCE,
         APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_SIZE),
        (APPLICATION_RESULT_TABLE_POINTER_OVERLAY_DESTINATION,
         APPLICATION_RESULT_TABLE_POINTER_OVERLAY_SOURCE,
         APPLICATION_RESULT_TABLE_POINTER_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    # 33:51E0 delegates allocation to 25:77DA.  The bootstrap foreground
    # reloads that destination too, so preserve its complete same-PC function
    # and the two closed children before entering 31:138C.
    for destination, source, size in (
        (APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SOURCE,
         APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SIZE),
        (APPLICATION_MAIN_STORAGE_MASK_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SOURCE,
         APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SIZE),
        (APPLICATION_CONTEXT_LOOKUP_OVERLAY_DESTINATION,
         APPLICATION_CONTEXT_LOOKUP_OVERLAY_SOURCE,
         APPLICATION_CONTEXT_LOOKUP_OVERLAY_SIZE),
    ):
        words.extend(copy_code_to_overlay_words(destination, source, size))
    words.extend(embed_program_overlay_words(
        APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_DESTINATION,
        APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SOURCE,
        APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SIZE,
    ))
    for destination, source, size in (
        (APPLICATION_MENU_STATE_CLEAR_OVERLAY_DESTINATION,
         APPLICATION_MENU_STATE_CLEAR_OVERLAY_SOURCE,
         APPLICATION_MENU_STATE_CLEAR_OVERLAY_SIZE),
        (APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_DESTINATION,
         APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SOURCE,
         APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SIZE),
        (APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_DESTINATION,
         APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SOURCE,
         APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    # The event dispatcher calls these before reaching its poll loop.  Their
    # source-50 copies must be embedded because that source bank is mutable at
    # runtime.  The larger stable-source children are installed by a compact
    # secondary helper in the adjacent resident gap.
    for destination, source, size in (
        (APPLICATION_STATE_COMMIT_OVERLAY_DESTINATION,
         APPLICATION_STATE_COMMIT_OVERLAY_SOURCE,
         APPLICATION_STATE_COMMIT_OVERLAY_SIZE),
        (APPLICATION_UI_PREPARE_OVERLAY_DESTINATION,
         APPLICATION_UI_PREPARE_OVERLAY_SOURCE,
         APPLICATION_UI_PREPARE_OVERLAY_SIZE),
        (APPLICATION_MENU_GLOBAL_RESET_OVERLAY_DESTINATION,
         APPLICATION_MENU_GLOBAL_RESET_OVERLAY_SOURCE,
         APPLICATION_MENU_GLOBAL_RESET_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    words.extend((
        0xBD00 | (MENU_SERVICE_INIT_INSTALLER_ADDRESS >> 16),
        MENU_SERVICE_INIT_INSTALLER_ADDRESS & 0xFFFF,
        0xBD00 | (MENU_EVENT_DEPENDENCY_INSTALLER_ADDRESS >> 16),
        MENU_EVENT_DEPENDENCY_INSTALLER_ADDRESS & 0xFFFF,
    ))
    words.append(RETS)
    return words


def menu_service_init_installer_words() -> list[int]:
    """Restore exact 4D:2630 after the bootstrap foreground retires it."""
    words = copy_code_to_overlay_words(
        APPLICATION_MAIN_SERVICE_INIT_OVERLAY_DESTINATION,
        APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SOURCE,
        APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SIZE,
    )
    words.append(RETS)
    return words


def menu_event_dependency_installer_words() -> list[int]:
    """Restore stable-source children used before the menu event poll loop."""
    words: list[int] = []
    for destination, source, size in (
        (STARTUP_POINTER_OVERLAY_DESTINATION,
         STARTUP_POINTER_OVERLAY_SOURCE,
         STARTUP_POINTER_OVERLAY_SIZE),
        (APPLICATION_MENU_UI_PREPARE_CORE_OVERLAY_DESTINATION,
         APPLICATION_MENU_UI_PREPARE_CORE_OVERLAY_SOURCE,
         APPLICATION_MENU_UI_PREPARE_CORE_OVERLAY_SIZE),
        (MEMORY_FILL_OVERLAY_DESTINATION,
         MEMORY_FILL_OVERLAY_SOURCE,
         MEMORY_FILL_OVERLAY_SIZE),
    ):
        words.extend(copy_code_to_overlay_words(destination, source, size))
    words.append(RETS)
    return words


def menu_event_state_installer_words() -> list[int]:
    """Restore source-50 state helpers used immediately before event polling."""
    words: list[int] = []
    for destination, source, size in (
        (APPLICATION_MENU_GLOBAL_RESET_OVERLAY_DESTINATION,
         APPLICATION_MENU_GLOBAL_RESET_OVERLAY_SOURCE,
         APPLICATION_MENU_GLOBAL_RESET_OVERLAY_SIZE),
        (APPLICATION_MENU_EVENT_STATE_OVERLAY_DESTINATION,
         APPLICATION_MENU_EVENT_STATE_OVERLAY_SOURCE,
         APPLICATION_MENU_EVENT_STATE_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    words.extend(copy_code_to_overlay_words(
        APPLICATION_MENU_BUFFER_SETUP_OVERLAY_DESTINATION,
        APPLICATION_MENU_BUFFER_SETUP_OVERLAY_SOURCE,
        APPLICATION_MENU_BUFFER_SETUP_OVERLAY_SIZE,
    ))
    words.extend(copy_code_to_overlay_words(
        APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_DESTINATION,
        APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_SOURCE,
        APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_SIZE,
    ))
    # The poll loop enters this two-word tail gateway on every iteration.  It
    # is part of the ordinary application overlay set, but the bootstrap
    # foreground reuses 32:773A before the menu boundary.
    words.extend(copy_code_to_overlay_words(
        APPLICATION_WIDE_GATE_OVERLAY_DESTINATION,
        APPLICATION_WIDE_GATE_OVERLAY_SOURCE,
        APPLICATION_WIDE_GATE_OVERLAY_SIZE,
    ))
    for destination, source, size in (
        (APPLICATION_STATE_TICK_SAMPLE_OVERLAY_DESTINATION,
         APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SOURCE,
         APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SIZE),
        (APPLICATION_STATE_TICK_COMMIT_OVERLAY_DESTINATION,
         APPLICATION_STATE_TICK_COMMIT_OVERLAY_SOURCE,
         APPLICATION_STATE_TICK_COMMIT_OVERLAY_SIZE),
    ):
        words.extend(copy_code_to_overlay_words(destination, source, size))
    words.append(RETS)
    return words


def operation_modal_closure_installer_words() -> list[int]:
    """Install the complete linked status-dialog closure as guest code."""
    words: list[int] = []
    for destination, source, size in (
            APPLICATION_OPERATION_MODAL_CLOSURE_OVERLAYS):
        words.extend(operation_modal_overlay_install_words(
            destination, source, size,
        ))
    words.extend((
        0xBD00 | (
            APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS >> 16
        ),
        APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS & 0xFFFF,
    ))
    return words


def operation_modal_source_repair_installer_words() -> list[int]:
    """Restore source-29 fragments overwritten before the 29-to-0C copy."""
    words: list[int] = []
    for destination, source, size in (
            APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_OVERLAYS):
        words.extend(embed_program_overlay_words(destination, source, size))
    words.append(RETS)
    return words


def install_application_main_chain_words(
        return_after_first_main_cycle: bool = False,
        reconstruct_resident_root_desktop: bool = False) -> list[int]:
    """Install the exact guest path that constructs the resource FILE."""
    # Cold boot still executes flat startup routines whose ranges overlap the
    # later menu image (notably 32:6F12..6FE4 versus the menu helper beginning
    # at 32:6F7C).  Defer those executable overlays to the explicit manager
    # boundary at 03:0080, but publish the independent 20:0B82 catalogue now:
    # the bootstrap root renderer reads its five records before that boundary.
    # The wrapper retains the existing DES initialization, keeping the ROM-01
    # stream length and every later instruction address unchanged.
    words: list[int] = [
        0xBD00 | (MENU_CATALOG_EARLY_INSTALLER_ADDRESS >> 16),
        MENU_CATALOG_EARLY_INSTALLER_ADDRESS & 0xFFFF,
    ]
    # This is data, not executable code.  Embed it from the immutable update
    # PRG because its 4D:* source bank is mutable by the time the foreground
    # resident operation runs.
    words.extend(embed_program_data_words(
        RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_DESTINATION,
        RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SOURCE,
        RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SIZE,
    ))
    words.extend(embed_program_data_words(
        RESIDENT_OPERATION_STRING_POOL_OVERLAY_DESTINATION,
        RESIDENT_OPERATION_STRING_POOL_OVERLAY_SOURCE,
        RESIDENT_OPERATION_STRING_POOL_OVERLAY_SIZE,
    ))
    words.extend(embed_program_data_words(
        APPLICATION_USERINFO_LITERAL_OVERLAY_DESTINATION,
        APPLICATION_USERINFO_LITERAL_OVERLAY_SOURCE,
        APPLICATION_USERINFO_LITERAL_OVERLAY_SIZE,
    ))
    # In particular 2E:BE2E stores the real resident file opener's return
    # value in A0:7DEE; no host object or ROM service is substituted.
    for destination, source, size in (
        (APPLICATION_TOP_LEVEL_OVERLAY_DESTINATION,
         APPLICATION_TOP_LEVEL_OVERLAY_SOURCE,
         APPLICATION_TOP_LEVEL_OVERLAY_SIZE),
        (APPLICATION_UI_STATE_OVERLAY_DESTINATION,
         APPLICATION_UI_STATE_OVERLAY_SOURCE,
         APPLICATION_UI_STATE_OVERLAY_SIZE),
        (APPLICATION_GLOBAL_STATE_INIT_OVERLAY_DESTINATION,
         APPLICATION_GLOBAL_STATE_INIT_OVERLAY_SOURCE,
         APPLICATION_GLOBAL_STATE_INIT_OVERLAY_SIZE),
        (APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_DESTINATION,
         APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_SOURCE,
         APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_SIZE),
        (APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_DESTINATION,
         APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_SOURCE,
         APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_SIZE),
        (APPLICATION_POST_REGISTRY_OVERLAY_DESTINATION,
         APPLICATION_POST_REGISTRY_OVERLAY_SOURCE,
         APPLICATION_POST_REGISTRY_OVERLAY_SIZE),
        (APPLICATION_MAIN_STATE_INIT_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STATE_INIT_OVERLAY_SOURCE,
         APPLICATION_MAIN_STATE_INIT_OVERLAY_SIZE),
        (APPLICATION_MAIN_STATE_BUILD_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STATE_BUILD_OVERLAY_SOURCE,
         APPLICATION_MAIN_STATE_BUILD_OVERLAY_SIZE),
        (APPLICATION_MAIN_STATE_POINTER_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STATE_POINTER_OVERLAY_SOURCE,
         APPLICATION_MAIN_STATE_POINTER_OVERLAY_SIZE),
        (APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_SOURCE,
         APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_SIZE),
        # Exact resident operation 1B:23B8 reaches this table creator during
        # the first foreground lifecycle.  The flat 31:4974 image is a
        # graphics-function continuation, while 4E:4974 is the complete
        # LINK #2 implementation with the matching three far-pointer
        # arguments.  Install it at the same late ROM-01 boundary as the
        # application callers so the preceding flat-image load cannot erase
        # it before operation 0x0B runs.
        (RESIDENT_WORK_TABLE_CREATE_OVERLAY_DESTINATION,
         RESIDENT_WORK_TABLE_CREATE_OVERLAY_SOURCE,
         RESIDENT_WORK_TABLE_CREATE_OVERLAY_SIZE),
        (APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_DESTINATION,
         APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_SOURCE,
         APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_MAIN_CONFIG_OVERLAY_DESTINATION,
         APPLICATION_MAIN_CONFIG_OVERLAY_SOURCE,
         APPLICATION_MAIN_CONFIG_OVERLAY_SIZE),
        (APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_DESTINATION,
         APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_SOURCE,
         APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_SIZE),
        (APPLICATION_MAIN_CONDITIONAL_OVERLAY_DESTINATION,
         APPLICATION_MAIN_CONDITIONAL_OVERLAY_SOURCE,
         APPLICATION_MAIN_CONDITIONAL_OVERLAY_SIZE),
        (APPLICATION_MAIN_INPUT_STATE_OVERLAY_DESTINATION,
         APPLICATION_MAIN_INPUT_STATE_OVERLAY_SOURCE,
         APPLICATION_MAIN_INPUT_STATE_OVERLAY_SIZE),
        (APPLICATION_MAIN_STATUS_SCAN_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STATUS_SCAN_OVERLAY_SOURCE,
         APPLICATION_MAIN_STATUS_SCAN_OVERLAY_SIZE),
        (APPLICATION_MAIN_STATE_TICK_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STATE_TICK_OVERLAY_SOURCE,
         APPLICATION_MAIN_STATE_TICK_OVERLAY_SIZE),
        (APPLICATION_MAIN_STATE_SYNC_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STATE_SYNC_OVERLAY_SOURCE,
         APPLICATION_MAIN_STATE_SYNC_OVERLAY_SIZE),
        (APPLICATION_MAIN_ACTION_OVERLAY_DESTINATION,
         APPLICATION_MAIN_ACTION_OVERLAY_SOURCE,
         APPLICATION_MAIN_ACTION_OVERLAY_SIZE),
        (APPLICATION_MAIN_ACTION_RENDER_OVERLAY_DESTINATION,
         APPLICATION_MAIN_ACTION_RENDER_OVERLAY_SOURCE,
         APPLICATION_MAIN_ACTION_RENDER_OVERLAY_SIZE),
        (APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_DESTINATION,
         APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SOURCE,
         APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SIZE),
        (APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_DESTINATION,
         APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SOURCE,
         APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SIZE),
        (APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_DESTINATION,
         APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_SOURCE,
         APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_SIZE),
        (APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_DESTINATION,
         APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_SOURCE,
         APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_SIZE),
        (APPLICATION_MAIN_ACTION_RENDER_PACK_OVERLAY_DESTINATION,
         APPLICATION_MAIN_ACTION_RENDER_PACK_OVERLAY_SOURCE,
         APPLICATION_MAIN_ACTION_RENDER_PACK_OVERLAY_SIZE),
        (APPLICATION_MAIN_ACTION_RENDER_EDGES_OVERLAY_DESTINATION,
         APPLICATION_MAIN_ACTION_RENDER_EDGES_OVERLAY_SOURCE,
         APPLICATION_MAIN_ACTION_RENDER_EDGES_OVERLAY_SIZE),
        (APPLICATION_REGION_CONVERT_OVERLAY_DESTINATION,
         APPLICATION_REGION_CONVERT_OVERLAY_SOURCE,
         APPLICATION_REGION_CONVERT_OVERLAY_SIZE),
        (APPLICATION_REGION_SCALE_OVERLAY_DESTINATION,
         APPLICATION_REGION_SCALE_OVERLAY_SOURCE,
         APPLICATION_REGION_SCALE_OVERLAY_SIZE),
        (APPLICATION_REGION_ARITH_OVERLAY_DESTINATION,
         APPLICATION_REGION_ARITH_OVERLAY_SOURCE,
         APPLICATION_REGION_ARITH_OVERLAY_SIZE),
        (APPLICATION_REGION_NORMALIZE_OVERLAY_DESTINATION,
         APPLICATION_REGION_NORMALIZE_OVERLAY_SOURCE,
         APPLICATION_REGION_NORMALIZE_OVERLAY_SIZE),
        (APPLICATION_REGION_DIGIT_OVERLAY_DESTINATION,
         APPLICATION_REGION_DIGIT_OVERLAY_SOURCE,
         APPLICATION_REGION_DIGIT_OVERLAY_SIZE),
        (APPLICATION_FONT_TABLE_OVERLAY_DESTINATION,
         APPLICATION_FONT_TABLE_OVERLAY_SOURCE,
         APPLICATION_FONT_TABLE_OVERLAY_SIZE),
        (APPLICATION_MAIN_RESULT_SCAN_OVERLAY_DESTINATION,
         APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SOURCE,
         APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SIZE),
        (APPLICATION_MAIN_LAYOUT_OVERLAY_DESTINATION,
         APPLICATION_MAIN_LAYOUT_OVERLAY_SOURCE,
         APPLICATION_MAIN_LAYOUT_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_LOOP_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_LOOP_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_LOOP_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_STATE_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_STATE_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_STATE_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_COPY_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_COPY_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_COPY_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_EVENT_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_EVENT_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_EVENT_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_PARENT_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_PARENT_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_PARENT_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_DISPATCH_TABLE_DESTINATION,
         APPLICATION_FOREGROUND_DISPATCH_TABLE_SOURCE,
         APPLICATION_FOREGROUND_DISPATCH_TABLE_SIZE),
        (APPLICATION_CURSOR_RANGE_OVERLAY_DESTINATION,
         APPLICATION_CURSOR_RANGE_OVERLAY_SOURCE,
         APPLICATION_CURSOR_RANGE_OVERLAY_SIZE),
        (APPLICATION_INPUT_MODE_OVERLAY_DESTINATION,
         APPLICATION_INPUT_MODE_OVERLAY_SOURCE,
         APPLICATION_INPUT_MODE_OVERLAY_SIZE),
        # Do not copy 50:2562 or 50:3980 here. Segment 50 is writable by this
        # late stage; install_runtime_overlay_words() already embedded their
        # exact shipped bytes at 33:2562 and 33:3980 before it became mutable.
        (APPLICATION_EVENT_PACKET_DECODE_OVERLAY_DESTINATION,
         APPLICATION_EVENT_PACKET_DECODE_OVERLAY_SOURCE,
         APPLICATION_EVENT_PACKET_DECODE_OVERLAY_SIZE),
        (APPLICATION_EVENT_PACKET_COPY_OVERLAY_DESTINATION,
         APPLICATION_EVENT_PACKET_COPY_OVERLAY_SOURCE,
         APPLICATION_EVENT_PACKET_COPY_OVERLAY_SIZE),
        (APPLICATION_EVENT_TEXT_DATA_OVERLAY_DESTINATION,
         APPLICATION_EVENT_TEXT_DATA_OVERLAY_SOURCE,
         APPLICATION_EVENT_TEXT_DATA_OVERLAY_SIZE),
        (APPLICATION_EVENT_RENDER_HELPER_OVERLAY_DESTINATION,
         APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SOURCE,
         APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SIZE),
        (APPLICATION_EVENT_READY_OVERLAY_DESTINATION,
         APPLICATION_EVENT_READY_OVERLAY_SOURCE,
         APPLICATION_EVENT_READY_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_SIZE),
        (APPLICATION_TIMER_CALLBACK_OVERLAY_DESTINATION,
         APPLICATION_TIMER_CALLBACK_OVERLAY_SOURCE,
         APPLICATION_TIMER_CALLBACK_OVERLAY_SIZE),
        (APPLICATION_KEY_DEBOUNCE_OVERLAY_DESTINATION,
         APPLICATION_KEY_DEBOUNCE_OVERLAY_SOURCE,
         APPLICATION_KEY_DEBOUNCE_OVERLAY_SIZE),
        (APPLICATION_KEY_MATRIX_SCAN_OVERLAY_DESTINATION,
         APPLICATION_KEY_MATRIX_SCAN_OVERLAY_SOURCE,
         APPLICATION_KEY_MATRIX_SCAN_OVERLAY_SIZE),
        (APPLICATION_TIMER_POWER_OVERLAY_DESTINATION,
         APPLICATION_TIMER_POWER_OVERLAY_SOURCE,
         APPLICATION_TIMER_POWER_OVERLAY_SIZE),
        (APPLICATION_TIMER_IDLE_OVERLAY_DESTINATION,
         APPLICATION_TIMER_IDLE_OVERLAY_SOURCE,
         APPLICATION_TIMER_IDLE_OVERLAY_SIZE),
        (APPLICATION_TIMER_CALENDAR_OVERLAY_DESTINATION,
         APPLICATION_TIMER_CALENDAR_OVERLAY_SOURCE,
         APPLICATION_TIMER_CALENDAR_OVERLAY_SIZE),
        (APPLICATION_TIMER_COMMIT_OVERLAY_DESTINATION,
         APPLICATION_TIMER_COMMIT_OVERLAY_SOURCE,
         APPLICATION_TIMER_COMMIT_OVERLAY_SIZE),
        (APPLICATION_EVENT_DECODE_OVERLAY_DESTINATION,
         APPLICATION_EVENT_DECODE_OVERLAY_SOURCE,
         APPLICATION_EVENT_DECODE_OVERLAY_SIZE),
        (APPLICATION_LOADING_TASK_OVERLAY_DESTINATION,
         APPLICATION_LOADING_TASK_OVERLAY_SOURCE,
         APPLICATION_LOADING_TASK_OVERLAY_SIZE),
        (APPLICATION_SYSTEM_REGISTRY_OVERLAY_DESTINATION,
         APPLICATION_SYSTEM_REGISTRY_OVERLAY_SOURCE,
         APPLICATION_SYSTEM_REGISTRY_OVERLAY_SIZE),
        (APPLICATION_STORAGE_CAPACITY_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_CAPACITY_OVERLAY_SOURCE,
         APPLICATION_STORAGE_CAPACITY_OVERLAY_SIZE),
        (APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_SOURCE,
         APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_SIZE),
        (APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SOURCE,
         APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SIZE),
        (APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SOURCE,
         APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SIZE),
        (STARTUP_TICK_INIT_OVERLAY_DESTINATION,
         STARTUP_TICK_INIT_OVERLAY_SOURCE,
         STARTUP_TICK_INIT_OVERLAY_SIZE),
        (STARTUP_TIMER_CONFIG_OVERLAY_DESTINATION,
         STARTUP_TIMER_CONFIG_OVERLAY_SOURCE,
         STARTUP_TIMER_CONFIG_OVERLAY_SIZE),
        (APPLICATION_FAR_BLOCK_COPY_OVERLAY_DESTINATION,
         APPLICATION_FAR_BLOCK_COPY_OVERLAY_SOURCE,
         APPLICATION_FAR_BLOCK_COPY_OVERLAY_SIZE),
        (APPLICATION_INIT_ENTRY_OVERLAY_DESTINATION,
         APPLICATION_INIT_ENTRY_OVERLAY_SOURCE,
         APPLICATION_INIT_ENTRY_OVERLAY_SIZE),
        (APPLICATION_CLOCK_VALIDATE_OVERLAY_DESTINATION,
         APPLICATION_CLOCK_VALIDATE_OVERLAY_SOURCE,
         APPLICATION_CLOCK_VALIDATE_OVERLAY_SIZE),
        (APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_DESTINATION,
         APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SOURCE,
         APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SIZE),
        (APPLICATION_SERVICE_LATCH_INIT_OVERLAY_DESTINATION,
         APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SOURCE,
         APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SIZE),
        (APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_DESTINATION,
         APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_SOURCE,
         APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_SIZE),
        (APPLICATION_INIT_31_1528_OVERLAY_DESTINATION,
         APPLICATION_INIT_31_1528_OVERLAY_SOURCE,
         APPLICATION_INIT_31_1528_OVERLAY_SIZE),
        (APPLICATION_INIT_08_2EDC_OVERLAY_DESTINATION,
         APPLICATION_INIT_08_2EDC_OVERLAY_SOURCE,
         APPLICATION_INIT_08_2EDC_OVERLAY_SIZE),
        (APPLICATION_INIT_33_356E_OVERLAY_DESTINATION,
         APPLICATION_INIT_33_356E_OVERLAY_SOURCE,
         APPLICATION_INIT_33_356E_OVERLAY_SIZE),
        (APPLICATION_INIT_33_3406_OVERLAY_DESTINATION,
         APPLICATION_INIT_33_3406_OVERLAY_SOURCE,
         APPLICATION_INIT_33_3406_OVERLAY_SIZE),
        (APPLICATION_INIT_08_3324_OVERLAY_DESTINATION,
         APPLICATION_INIT_08_3324_OVERLAY_SOURCE,
         APPLICATION_INIT_08_3324_OVERLAY_SIZE),
        (APPLICATION_INIT_33_3FD6_OVERLAY_DESTINATION,
         APPLICATION_INIT_33_3FD6_OVERLAY_SOURCE,
         APPLICATION_INIT_33_3FD6_OVERLAY_SIZE),
        (APPLICATION_INIT_29_C126_OVERLAY_DESTINATION,
         APPLICATION_INIT_29_C126_OVERLAY_SOURCE,
         APPLICATION_INIT_29_C126_OVERLAY_SIZE),
        (APPLICATION_INIT_33_09B8_OVERLAY_DESTINATION,
         APPLICATION_INIT_33_09B8_OVERLAY_SOURCE,
         APPLICATION_INIT_33_09B8_OVERLAY_SIZE),
        (APPLICATION_INIT_32_4D1C_OVERLAY_DESTINATION,
         APPLICATION_INIT_32_4D1C_OVERLAY_SOURCE,
         APPLICATION_INIT_32_4D1C_OVERLAY_SIZE),
        (APPLICATION_INIT_32_3232_OVERLAY_DESTINATION,
         APPLICATION_INIT_32_3232_OVERLAY_SOURCE,
         APPLICATION_INIT_32_3232_OVERLAY_SIZE),
        (APPLICATION_INIT_31_C3FC_OVERLAY_DESTINATION,
         APPLICATION_INIT_31_C3FC_OVERLAY_SOURCE,
         APPLICATION_INIT_31_C3FC_OVERLAY_SIZE),
        (APPLICATION_INIT_32_519E_OVERLAY_DESTINATION,
         APPLICATION_INIT_32_519E_OVERLAY_SOURCE,
         APPLICATION_INIT_32_519E_OVERLAY_SIZE),
        (APPLICATION_INIT_32_F3C6_OVERLAY_DESTINATION,
         APPLICATION_INIT_32_F3C6_OVERLAY_SOURCE,
         APPLICATION_INIT_32_F3C6_OVERLAY_SIZE),
        (APPLICATION_INIT_31_B6FC_OVERLAY_DESTINATION,
         APPLICATION_INIT_31_B6FC_OVERLAY_SOURCE,
         APPLICATION_INIT_31_B6FC_OVERLAY_SIZE),
        (APPLICATION_INIT_31_CC84_OVERLAY_DESTINATION,
         APPLICATION_INIT_31_CC84_OVERLAY_SOURCE,
         APPLICATION_INIT_31_CC84_OVERLAY_SIZE),
        (APPLICATION_INIT_32_C514_OVERLAY_DESTINATION,
         APPLICATION_INIT_32_C514_OVERLAY_SOURCE,
         APPLICATION_INIT_32_C514_OVERLAY_SIZE),
        (APPLICATION_MAIN_LOOP_OVERLAY_DESTINATION,
         APPLICATION_MAIN_LOOP_OVERLAY_SOURCE,
         APPLICATION_MAIN_LOOP_OVERLAY_SIZE),
        (APPLICATION_RESOURCE_DRIVER_OVERLAY_DESTINATION,
         APPLICATION_RESOURCE_DRIVER_OVERLAY_SOURCE,
         APPLICATION_RESOURCE_DRIVER_OVERLAY_SIZE),
        (APPLICATION_FILE_ATTACH_OVERLAY_DESTINATION,
         APPLICATION_FILE_ATTACH_OVERLAY_SOURCE,
         APPLICATION_FILE_ATTACH_OVERLAY_SIZE),
        (APPLICATION_FILE_WRAPPER_OVERLAY_DESTINATION,
         APPLICATION_FILE_WRAPPER_OVERLAY_SOURCE,
         APPLICATION_FILE_WRAPPER_OVERLAY_SIZE),
        (APPLICATION_FILE_OBJECT_OPEN_OVERLAY_DESTINATION,
         APPLICATION_FILE_OBJECT_OPEN_OVERLAY_SOURCE,
         APPLICATION_FILE_OBJECT_OPEN_OVERLAY_SIZE),
        (APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_DESTINATION,
         APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_SOURCE,
         APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_SIZE),
        (APPLICATION_POINTER_CLASSIFY_OVERLAY_DESTINATION,
         APPLICATION_POINTER_CLASSIFY_OVERLAY_SOURCE,
         APPLICATION_POINTER_CLASSIFY_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_SCAN_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_SCAN_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_SCAN_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_SIZE),
        (APPLICATION_FILE_CREATE_STATE_OVERLAY_DESTINATION,
         APPLICATION_FILE_CREATE_STATE_OVERLAY_SOURCE,
         APPLICATION_FILE_CREATE_STATE_OVERLAY_SIZE),
        (APPLICATION_FILE_CREATE_RECORD_OVERLAY_DESTINATION,
         APPLICATION_FILE_CREATE_RECORD_OVERLAY_SOURCE,
         APPLICATION_FILE_CREATE_RECORD_OVERLAY_SIZE),
        (APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_DESTINATION,
         APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_SOURCE,
         APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_SIZE),
        (APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_DESTINATION,
         APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_SOURCE,
         APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_SIZE),
        (APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION,
         APPLICATION_FILE_ENTRY_BUILD_OVERLAY_SOURCE,
         APPLICATION_FILE_ENTRY_BUILD_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_STATUS_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_STATUS_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_STATUS_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_APPLY_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_APPLY_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_APPLY_OVERLAY_SIZE),
        (APPLICATION_FILE_CLOSE_STATE_OVERLAY_DESTINATION,
         APPLICATION_FILE_CLOSE_STATE_OVERLAY_SOURCE,
         APPLICATION_FILE_CLOSE_STATE_OVERLAY_SIZE),
        (APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_DESTINATION,
         APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_SOURCE,
         APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_SIZE),
        (APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION,
         APPLICATION_FILE_METADATA_UPDATE_OVERLAY_SOURCE,
         APPLICATION_FILE_METADATA_UPDATE_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_BUILD_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_BUILD_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_BUILD_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_SIZE),
        (APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_DESTINATION,
         APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_SOURCE,
         APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_SIZE),
        (APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_DESTINATION,
         APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_SOURCE,
         APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_SIZE),
        (APPLICATION_BYTE_CLASSIFY_OVERLAY_DESTINATION,
         APPLICATION_BYTE_CLASSIFY_OVERLAY_SOURCE,
         APPLICATION_BYTE_CLASSIFY_OVERLAY_SIZE),
        (APPLICATION_ASCII_LOWER_OVERLAY_DESTINATION,
         APPLICATION_ASCII_LOWER_OVERLAY_SOURCE,
         APPLICATION_ASCII_LOWER_OVERLAY_SIZE),
    ):
        if (destination in APPLICATION_INITIALIZER_FOLLOWUP_EMBEDDED_DESTINATIONS or
                destination in APPLICATION_FILE_RECORD_EMBEDDED_DESTINATIONS):
            # Banks 4E..50 are mutable by this late stage.  Preserve these
            # small, bounded initializer callees inside the resident loader
            # so earlier application copies cannot erase their source bytes.
            words.extend(embed_program_overlay_words(destination, source, size))
        else:
            words.extend(copy_code_to_overlay_words(destination, source, size))
    if PROVISION_TRIGGER_TARGET:
        actual = tuple(program_source_words(
            APPLICATION_PROVISION_TRIGGER_SOURCE, 4
        ))
        expected_targets = {
            APPLICATION_PROVISION_TRIGGER_ORIGINAL_WORDS,
            (
                0xBD00 | (PROVISION_TRIGGER_TARGET >> 16),
                PROVISION_TRIGGER_TARGET & 0xFFFF,
            ),
        }
        if actual not in expected_targets:
            raise ValueError(
                "application provision trigger signature changed at "
                f"{APPLICATION_PROVISION_TRIGGER_SOURCE:06X}: {actual!r}"
            )
        words.extend(write_program_words(
            APPLICATION_PROVISION_TRIGGER_DESTINATION,
            (
                0xBD00 | (PROVISION_TRIGGER_TARGET >> 16),
                PROVISION_TRIGGER_TARGET & 0xFFFF,
            ),
        ))
    words.extend(embed_program_overlay_words(
        APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_DESTINATION,
        APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_SOURCE,
        APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_SIZE,
    ))
    for destination, source, old_target, new_target, label in (
        (APPLICATION_FILE_CREATE_VALIDATE_REGISTRY_ENTRY_CALL,
         APPLICATION_FILE_CREATE_VALIDATE_REGISTRY_ENTRY_CALL_SOURCE,
         APPLICATION_SYSTEM_REGISTRY_ENTRY_LINKED_DESTINATION,
         APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_DESTINATION,
         "file-create registry entry"),
        (APPLICATION_STORAGE_CONTEXT_RESOLVE_SECTOR_PROBE_CALL,
         APPLICATION_STORAGE_CONTEXT_RESOLVE_SECTOR_PROBE_CALL_SOURCE,
         APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
         APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION,
         "storage-context sector probe"),
    ):
        if program_source_words(source, 4) != [
            0xBD00 | (old_target >> 16), old_target & 0xFFFF,
        ]:
            raise ValueError(f"{label} call signature changed at {source:06X}")
        words.extend(write_program_words(
            destination,
            (0xBD00 | (new_target >> 16), new_target & 0xFFFF),
        ))
    if program_source_words(
            APPLICATION_FILE_ENTRY_BUILD_CALLBACK_SEGMENT_SOURCE, 2) != [
        APPLICATION_FILE_ENTRY_BUILD_LINKED_DESTINATION >> 16,
    ]:
        raise ValueError("file-entry builder callback segment signature changed")
    words.extend(write_program_words(
        APPLICATION_FILE_ENTRY_BUILD_CALLBACK_SEGMENT,
        (APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION >> 16,),
    ))
    for destination, source in APPLICATION_FILE_RECORD_STATUS_CALLS:
        if program_source_words(source, 4) != [
            0xBD00 | (APPLICATION_FILE_RECORD_STATUS_LINKED_DESTINATION >> 16),
            APPLICATION_FILE_RECORD_STATUS_LINKED_DESTINATION & 0xFFFF,
        ]:
            raise ValueError(
                f"file-record status call signature changed at {source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (0xBD00 | (
                APPLICATION_FILE_RECORD_STATUS_OVERLAY_DESTINATION >> 16
             ),
             APPLICATION_FILE_RECORD_STATUS_OVERLAY_DESTINATION & 0xFFFF),
        ))
    for destination, source, old_target, new_target, label in (
        (APPLICATION_FILE_RECORD_STATUS_SELECT_CALL,
         APPLICATION_FILE_RECORD_STATUS_SELECT_CALL_SOURCE,
         0x28AC4C, RESIDENT_STORAGE_SELECT_ADDRESS,
         "file-record storage selector"),
        (APPLICATION_FILE_RECORD_APPLY_CALL,
         APPLICATION_FILE_RECORD_APPLY_CALL_SOURCE,
         APPLICATION_FILE_RECORD_APPLY_LINKED_DESTINATION,
         APPLICATION_FILE_RECORD_APPLY_OVERLAY_DESTINATION,
         "file-record apply closure"),
        (APPLICATION_FILE_RECORD_APPLY_PAIR_CALL,
         APPLICATION_FILE_RECORD_APPLY_PAIR_CALL_SOURCE,
         0x306E9E, RESIDENT_STORAGE_PAIR_ADDRESS,
         "file-record storage pair"),
        (APPLICATION_FILE_RECORD_APPLY_DRIVER_CALL,
         APPLICATION_FILE_RECORD_APPLY_DRIVER_CALL_SOURCE,
         0x2D3460, RESIDENT_STORAGE_DRIVER_ADDRESS,
         "file-record storage driver"),
        (APPLICATION_FILE_CLOSE_STATE_CALL,
         APPLICATION_FILE_CLOSE_STATE_CALL_SOURCE,
         APPLICATION_FILE_CLOSE_STATE_LINKED_DESTINATION,
         APPLICATION_FILE_CLOSE_STATE_OVERLAY_DESTINATION,
         "file-close storage-state copy"),
        (APPLICATION_FILE_CLOSE_RECORD_SYNC_CALL,
         APPLICATION_FILE_CLOSE_RECORD_SYNC_CALL_SOURCE,
         APPLICATION_FILE_CLOSE_RECORD_SYNC_LINKED_DESTINATION,
         APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_DESTINATION,
         "file-close record synchronizer"),
        (APPLICATION_FILE_CLOSE_DRIVER_CALL,
         APPLICATION_FILE_CLOSE_DRIVER_CALL_SOURCE,
         0x2D3460, RESIDENT_STORAGE_DRIVER_ADDRESS,
         "file-close storage driver"),
    ):
        if program_source_words(source, 4) != [
            0xBD00 | (old_target >> 16), old_target & 0xFFFF,
        ]:
            raise ValueError(f"{label} call signature changed at {source:06X}")
        words.extend(write_program_words(
            destination,
            (0xBD00 | (new_target >> 16), new_target & 0xFFFF),
        ))
    for destination, source in APPLICATION_FILE_METADATA_UPDATE_CALLS:
        if program_source_words(source, 4) != [
            0xBD00 | (APPLICATION_FILE_METADATA_UPDATE_LINKED_DESTINATION >> 16),
            APPLICATION_FILE_METADATA_UPDATE_LINKED_DESTINATION & 0xFFFF,
        ]:
            raise ValueError(
                f"file-metadata update call signature changed at {source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (0xBD00 | (APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION >> 16),
             APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION & 0xFFFF),
        ))
    for destination, source in APPLICATION_FILE_METADATA_UPDATE_CALLBACK_SEGMENTS:
        if program_source_words(source, 2) != [
            APPLICATION_FILE_METADATA_UPDATE_LINKED_DESTINATION >> 16,
        ]:
            raise ValueError(
                f"file-metadata callback segment changed at {source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION >> 16,),
        ))
    for destination, source in APPLICATION_FILE_RECORD_APPLY_CALLBACK_SEGMENTS:
        if program_source_words(source, 2) != [
            APPLICATION_FILE_RECORD_APPLY_LINKED_DESTINATION >> 16,
        ]:
            raise ValueError(
                f"file-record callback segment changed at {source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (APPLICATION_FILE_RECORD_APPLY_OVERLAY_DESTINATION >> 16,),
        ))
    # Segment 50 is mutable data RAM by the time the late ROM loader runs.
    # Preserve this shipped leaf in the loader itself instead of copying the
    # already-cleared live source bank.
    words.extend(embed_program_overlay_words(
        APPLICATION_POST_REGISTRY_STATE_OVERLAY_DESTINATION,
        APPLICATION_POST_REGISTRY_STATE_OVERLAY_SOURCE,
        APPLICATION_POST_REGISTRY_STATE_OVERLAY_SIZE,
    ))
    words.extend(embed_program_overlay_words(
        APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_DESTINATION,
        APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_SOURCE,
        APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_SIZE,
    ))
    words.extend(embed_program_overlay_words(
        APPLICATION_POST_REGISTRY_BIND_TARGET_OVERLAY_DESTINATION,
        APPLICATION_POST_REGISTRY_BIND_TARGET_OVERLAY_SOURCE,
        APPLICATION_POST_REGISTRY_BIND_TARGET_OVERLAY_SIZE,
    ))
    words.extend(embed_program_overlay_words(
        APPLICATION_POST_REGISTRY_HOOK_OVERLAY_DESTINATION,
        APPLICATION_POST_REGISTRY_HOOK_OVERLAY_SOURCE,
        APPLICATION_POST_REGISTRY_HOOK_OVERLAY_SIZE,
    ))
    # Segment 50 is mutable when the timer-driven foreground event fetch is
    # first reached, so retain this exact wrapper in the resident installer.
    words.extend(embed_program_overlay_words(
        APPLICATION_EVENT_FETCH_OVERLAY_DESTINATION,
        APPLICATION_EVENT_FETCH_OVERLAY_SOURCE,
        APPLICATION_EVENT_FETCH_OVERLAY_SIZE,
    ))
    for destination, source, size in (
        (ROM03_FAR_MEMCPY_THUNK_DESTINATION,
         ROM03_FAR_MEMCPY_THUNK_SOURCE,
         ROM03_FAR_MEMCPY_THUNK_SIZE),
        (APPLICATION_UI_PREPARE_OVERLAY_DESTINATION,
         APPLICATION_UI_PREPARE_OVERLAY_SOURCE,
         APPLICATION_UI_PREPARE_OVERLAY_SIZE),
        (APPLICATION_UI_PROPERTY_OVERLAY_DESTINATION,
         APPLICATION_UI_PROPERTY_OVERLAY_SOURCE,
         APPLICATION_UI_PROPERTY_OVERLAY_SIZE),
        (APPLICATION_UI_COMMIT_OVERLAY_DESTINATION,
         APPLICATION_UI_COMMIT_OVERLAY_SOURCE,
         APPLICATION_UI_COMMIT_OVERLAY_SIZE),
        (APPLICATION_MAIN_PREPARE_OVERLAY_DESTINATION,
         APPLICATION_MAIN_PREPARE_OVERLAY_SOURCE,
         APPLICATION_MAIN_PREPARE_OVERLAY_SIZE),
        (APPLICATION_MAIN_BIT_CLEAR_OVERLAY_DESTINATION,
         APPLICATION_MAIN_BIT_CLEAR_OVERLAY_SOURCE,
         APPLICATION_MAIN_BIT_CLEAR_OVERLAY_SIZE),
        (APPLICATION_MAIN_OBJECT_BIND_OVERLAY_DESTINATION,
         APPLICATION_MAIN_OBJECT_BIND_OVERLAY_SOURCE,
         APPLICATION_MAIN_OBJECT_BIND_OVERLAY_SIZE),
        (APPLICATION_MAIN_SERVICES_OVERLAY_DESTINATION,
         APPLICATION_MAIN_SERVICES_OVERLAY_SOURCE,
         APPLICATION_MAIN_SERVICES_OVERLAY_SIZE),
        (APPLICATION_MAIN_STATE_CLEAR_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STATE_CLEAR_OVERLAY_SOURCE,
         APPLICATION_MAIN_STATE_CLEAR_OVERLAY_SIZE),
        (APPLICATION_MAIN_STATUS_GET_OVERLAY_DESTINATION,
         APPLICATION_MAIN_STATUS_GET_OVERLAY_SOURCE,
         APPLICATION_MAIN_STATUS_GET_OVERLAY_SIZE),
        (APPLICATION_MAIN_RESULT_OVERLAY_DESTINATION,
         APPLICATION_MAIN_RESULT_OVERLAY_SOURCE,
         APPLICATION_MAIN_RESULT_OVERLAY_SIZE),
        (APPLICATION_MAIN_ACTION_QUERY_OVERLAY_DESTINATION,
         APPLICATION_MAIN_ACTION_QUERY_OVERLAY_SOURCE,
         APPLICATION_MAIN_ACTION_QUERY_OVERLAY_SIZE),
        (APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_DESTINATION,
         APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_SOURCE,
         APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_STATUS_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_STATUS_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_STATUS_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    if reconstruct_resident_root_desktop:
        for destination, source in RESIDENT_ROOT_DESKTOP_PATH_WRITES:
            if program_source_words(source, 2) != [0x4801]:
                raise ValueError(
                    "resident root-desktop path signature changed at "
                    f"{source >> 16:02X}:{source & 0xFFFF:04X}"
                )
            words.extend(write_program_words(destination, (0x4800,)))
    words.extend(write_program_words(
        APPLICATION_MAIN_RESOURCE_CREATE_CALL,
        (0xBD00 | (APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_DESTINATION >> 16),
         APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_DESTINATION & 0xFFFF),
    ))
    words.extend(write_program_words(
        APPLICATION_FOREGROUND_STATUS_CALL,
        (0xBD00 | (APPLICATION_FOREGROUND_STATUS_OVERLAY_DESTINATION >> 16),
         APPLICATION_FOREGROUND_STATUS_OVERLAY_DESTINATION & 0xFFFF),
    ))
    words.extend(write_program_words(
        APPLICATION_STATE_UI_ADC_CALL,
        (0xBD00 | (APPLICATION_STATE_ADC_OVERLAY_DESTINATION >> 16),
         APPLICATION_STATE_ADC_OVERLAY_DESTINATION & 0xFFFF),
    ))
    if program_source_words(
            APPLICATION_MAIN_ACTION_RENDER_INPUT_CALL_SOURCE, 4
    ) != [
        0xBD00 | (APPLICATION_MAIN_ROM_INPUT_LOCAL_SOURCE >> 16),
        APPLICATION_MAIN_ROM_INPUT_LOCAL_SOURCE & 0xFFFF,
    ]:
        raise ValueError("action-renderer input call signature changed")
    words.extend(write_program_words(
        APPLICATION_MAIN_ACTION_RENDER_INPUT_CALL,
        (0xBD00 | (APPLICATION_MAIN_ROM_INPUT_LOCAL_DESTINATION >> 16),
         APPLICATION_MAIN_ROM_INPUT_LOCAL_DESTINATION & 0xFFFF),
    ))
    words.extend(embed_program_overlay_words(
        APPLICATION_RESOURCE_POINTER_OVERLAY_DESTINATION,
        APPLICATION_RESOURCE_POINTER_OVERLAY_SOURCE,
        APPLICATION_RESOURCE_POINTER_OVERLAY_SIZE,
    ))
    if program_source_words(APPLICATION_TOP_LEVEL_MAIN_CALL_SOURCE, 4) != [
        0xBD00 | (APPLICATION_MAIN_LOOP_OVERLAY_DESTINATION >> 16),
        APPLICATION_MAIN_LOOP_OVERLAY_DESTINATION & 0xFFFF,
    ]:
        raise ValueError("top-level application main call signature changed")
    words.extend(write_program_words(
        APPLICATION_TOP_LEVEL_MAIN_CALL,
        (0xBD00 | (APPLICATION_MAIN_CURSOR_REFRESH_WRAPPER_ADDRESS >> 16),
         APPLICATION_MAIN_CURSOR_REFRESH_WRAPPER_ADDRESS & 0xFFFF),
    ))
    if return_after_first_main_cycle:
        if program_source_words(APPLICATION_MAIN_LOOP_BACK_EDGE_SOURCE, 4) != [
            0xAC00, 0x5226,
        ]:
            raise ValueError("application main-loop back edge signature changed")
        words.extend(write_program_words(
            APPLICATION_MAIN_LOOP_BACK_EDGE,
            (0xAD00 | (APPLICATION_MAIN_SINGLE_CYCLE_RETURN_ADDRESS >> 16),
             APPLICATION_MAIN_SINGLE_CYCLE_RETURN_ADDRESS & 0xFFFF),
        ))
    words.extend([
        0xBD00 | (APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16),
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF,
    ])
    # 20:026A reloads the flat foreground images after the cold installer and
    # before this late ROM-01 boundary.  Restore the complete text closure
    # last so the first real foreground render cannot consume the unrelated
    # flat 32:082E, 28:1F08, or 28:FD38 fragments.
    for destination, source, size in (
        (STORAGE_RECORD_DISPATCH_OVERLAY_DESTINATION,
         STORAGE_RECORD_DISPATCH_OVERLAY_SOURCE,
         STORAGE_RECORD_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_TEXT_LOOP_OVERLAY_DESTINATION,
         APPLICATION_TEXT_LOOP_OVERLAY_SOURCE,
         APPLICATION_TEXT_LOOP_OVERLAY_SIZE),
        (APPLICATION_GLYPH_DRAW_OVERLAY_DESTINATION,
         APPLICATION_GLYPH_DRAW_OVERLAY_SOURCE,
         APPLICATION_GLYPH_DRAW_OVERLAY_SIZE),
    ):
        words.extend(copy_code_to_overlay_words(destination, source, size))
    # The first resident operation immediately calls 31:7772.  Install its
    # complete linked modal closure last, after every broad application copy,
    # so no flat startup image can overwrite the recovered entry again.
    words.extend(operation_modal_closure_installer_words())
    words.extend(embed_program_data_words(
        APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_DESTINATION,
        APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SOURCE,
        APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SIZE,
    ))
    words.extend(embed_program_data_words(
        APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_DESTINATION,
        APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SOURCE,
        APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SIZE,
    ))
    return words


def rom01_application_loader_words(
        return_after_first_main_cycle: bool = False,
        reconstruct_resident_root_desktop: bool = False) -> list[int]:
    """Reconstruct the late ROM continuation called at ``01:0200``.

    The shipped 20:026A startup function calls this ROM entry immediately
    before its only call to the installed 2D:7DD2 application entry.  Its
    preceding initializers overwrite several application destinations, so
    restoring the evidenced same-PC modules here is the earliest ordering
    that leaves the real application call intact.  The exact segment-14 LCD
    power wrapper likewise has no PRG caller and belongs to this missing
    resident boundary.  Everything below executes as guest DMCU code; QEMU
    does not intercept the call or provide a host-side ROM service.
    """
    return [
        *install_application_main_chain_words(
            return_after_first_main_cycle,
            reconstruct_resident_root_desktop,
        ),
        # Exact 20:0030 clears 50:0000..53:FFFF before system main reaches
        # this resident boundary.  In particular it erases the FE74 root
        # object's three next links when 25:5858 is called by the outer
        # scheduler too early.  Install the source-proven capacity closure
        # and rebuild all four guest storage records here, after BSS clear and
        # after the late application overlays, but before 20:031C enters the
        # first foreground application.  These are ordinary DMCU calls, not
        # host-side filesystem state.
        0xBD00 | (STORAGE_RECORD_CAPACITY_INSTALLER_ADDRESS >> 16),
        STORAGE_RECORD_CAPACITY_INSTALLER_ADDRESS & 0xFFFF,
        0xBD00 | (APPLICATION_STORAGE_REGISTRY_OVERLAY_DESTINATION >> 16),
        APPLICATION_STORAGE_REGISTRY_OVERLAY_DESTINATION & 0xFFFF,
        # The vendor's broad application copies restore flat 33:6624 after
        # earlier overlay passes.  Install this two-function callback closure
        # at the last ROM-01 boundary before application execution.
        0xBD00 | (APPLICATION_FILE_DRIVER_CALLBACK_INSTALLER_ADDRESS >> 16),
        APPLICATION_FILE_DRIVER_CALLBACK_INSTALLER_ADDRESS & 0xFFFF,
        0xBD14, LCD_POWER_INIT_ADDRESS & 0xFFFF,
        RETS,
    ]


def file_driver_callback_child_words() -> list[int]:
    """Return the exact source-50 storage-driver status body."""
    return program_source_words(
        APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_SOURCE,
        APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_SIZE,
    )


def file_driver_callback_wrapper_words() -> list[int]:
    """Return the exact wrapper with its sole child segment relocated."""
    words = program_source_words(
        APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_SOURCE,
        APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_SIZE,
    )
    if words[1:3] != [
        0xBD00 | (APPLICATION_FILE_DRIVER_CALLBACK_CHILD_LINKED_DESTINATION
                  >> 16),
        APPLICATION_FILE_DRIVER_CALLBACK_CHILD_LINKED_DESTINATION & 0xFFFF,
    ]:
        raise ValueError("file-driver callback child signature changed")
    words[1:3] = [
        0xBD00 | (
            APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_DESTINATION >> 16
        ),
        APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_DESTINATION & 0xFFFF,
    ]
    return words


def file_driver_callback_installer_words() -> list[int]:
    """Publish the resident storage-driver callback in the live record."""
    words: list[int] = []
    # The storage registry has just published its device table at 51:27A0.
    # Replace only callback slot +0x14 with the relocated exact wrapper.
    words.extend((
        0x6810, APPLICATION_FILE_DRIVER_RECORD_SEGMENT_ADDRESS >> 15,
        0xC700,
        0x68F0,
        APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_DESTINATION >> 16,
        0xA8F0, APPLICATION_FILE_DRIVER_RECORD_SEGMENT_ADDRESS & 0x7FFF,
        0x68F0,
        APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_DESTINATION & 0xFFFF,
        0xA8F0, APPLICATION_FILE_DRIVER_RECORD_OFFSET_ADDRESS & 0x7FFF,
    ))
    words.append(RETS)
    return words


def application_region_extra_installer_words() -> list[int]:
    """Install late application overlays without growing segment-03 ROM."""
    words = [
        # The vendor initializer publishes this segment-50 callback only
        # after that source bank has become writable.  Embed its exact body
        # here so the fixed segment-03 cold-boot routine does not grow into
        # the resident jump table.
        *embed_program_overlay_words(
            STORAGE_RECORD_CALLBACK_OVERLAY_DESTINATION,
            STORAGE_RECORD_CALLBACK_OVERLAY_SOURCE,
            STORAGE_RECORD_CALLBACK_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_DESTINATION,
            STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_SOURCE,
            STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            STORAGE_RECORD_POST_LOOKUP_OVERLAY_DESTINATION,
            STORAGE_RECORD_POST_LOOKUP_OVERLAY_SOURCE,
            STORAGE_RECORD_POST_LOOKUP_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            APPLICATION_POST_MODAL_STATE_OVERLAY_DESTINATION,
            APPLICATION_POST_MODAL_STATE_OVERLAY_SOURCE,
            APPLICATION_POST_MODAL_STATE_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_POST_MODAL_REFRESH_OVERLAY_DESTINATION,
            APPLICATION_POST_MODAL_REFRESH_OVERLAY_SOURCE,
            APPLICATION_POST_MODAL_REFRESH_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_DESTINATION,
            APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SOURCE,
            APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_DESTINATION,
            APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_SOURCE,
            APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_DESTINATION,
            APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SOURCE,
            APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_DESTINATION,
            APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SOURCE,
            APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_DESTINATION,
            APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SOURCE,
            APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_DESTINATION,
            WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SOURCE,
            WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_DESTINATION,
            APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SOURCE,
            APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_DESTINATION,
            APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SOURCE,
            APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_DESTINATION,
            APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SOURCE,
            APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_DESTINATION,
            APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SOURCE,
            APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MAIN_STORAGE_MASK_OVERLAY_DESTINATION,
            APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SOURCE,
            APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MAIN_SERVICE_INIT_OVERLAY_DESTINATION,
            APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SOURCE,
            APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_DESTINATION,
            APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SOURCE,
            APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_DESTINATION,
            APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SOURCE,
            APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_RESOURCE_COORDINATE_OVERLAY_DESTINATION,
            APPLICATION_RESOURCE_COORDINATE_OVERLAY_SOURCE,
            APPLICATION_RESOURCE_COORDINATE_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_RESOURCE_INDEX_OVERLAY_DESTINATION,
            APPLICATION_RESOURCE_INDEX_OVERLAY_SOURCE,
            APPLICATION_RESOURCE_INDEX_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_DESTINATION,
            APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SOURCE,
            APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_REGION_VALUE_OVERLAY_DESTINATION,
            APPLICATION_REGION_VALUE_OVERLAY_SOURCE,
            APPLICATION_REGION_VALUE_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_DESTINATION,
            APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SOURCE,
            APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_DESTINATION,
            APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SOURCE,
            APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_DESTINATION,
            APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SOURCE,
            APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_INIT_TASK_OVERLAY_DESTINATION,
            APPLICATION_INIT_TASK_OVERLAY_SOURCE,
            APPLICATION_INIT_TASK_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_VALIDATION_CHECKSUM_OVERLAY_DESTINATION,
            APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SOURCE,
            APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_RESIDENT_EVENT_OVERLAY_DESTINATION,
            APPLICATION_RESIDENT_EVENT_OVERLAY_SOURCE,
            APPLICATION_RESIDENT_EVENT_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            APPLICATION_ASCII_DIGIT_OVERLAY_DESTINATION,
            APPLICATION_ASCII_DIGIT_OVERLAY_SOURCE,
            APPLICATION_ASCII_DIGIT_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_EVENT_POSTPROCESS_OVERLAY_DESTINATION,
            APPLICATION_EVENT_POSTPROCESS_OVERLAY_SOURCE,
            APPLICATION_EVENT_POSTPROCESS_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_VALIDATION_CRC16_OVERLAY_DESTINATION,
            APPLICATION_VALIDATION_CRC16_OVERLAY_SOURCE,
            APPLICATION_VALIDATION_CRC16_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            APPLICATION_REGION_NONZERO_OVERLAY_DESTINATION,
            APPLICATION_REGION_NONZERO_OVERLAY_SOURCE,
            APPLICATION_REGION_NONZERO_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            APPLICATION_KEY_HW_CLEAR_OVERLAY_DESTINATION,
            APPLICATION_KEY_HW_CLEAR_OVERLAY_SOURCE,
            APPLICATION_KEY_HW_CLEAR_OVERLAY_SIZE,
        ),
    ]
    # The helper body and its three signature-checked caller rewrites live in
    # a compact sub-installer so this already large routine remains below the
    # exact resident dispatcher at 1A:423C.
    words.extend((
        0xBD00 | (WIDE_ACCUMULATE_INSTALLER_ADDRESS >> 16),
        WIDE_ACCUMULATE_INSTALLER_ADDRESS & 0xFFFF,
    ))
    # 20:026A reloads the application banks after the cold-boot installer.
    # Reinstall record 0's primary media-read closure at this late boundary,
    # immediately before the fixed-launch probe constructs the storage
    # registry.  The neighbouring secondary path survives that reload, but
    # these four destinations are restored to their flat (incompatible)
    # bytes unless they are explicitly installed again here.  Their 47/49/
    # 4B/4F source banks have a zero data-bus view by this late lifecycle, so
    # preserve the verified PRG words in resident ROM instead of attempting a
    # live guest memcpy from those no-longer-readable sources.
    for destination, source, size in (
        (STORAGE_PRIMARY_READER_OVERLAY_DESTINATION,
         STORAGE_PRIMARY_READER_OVERLAY_SOURCE,
         STORAGE_PRIMARY_READER_OVERLAY_SIZE),
        (STORAGE_PRIMARY_TRANSFER_OVERLAY_DESTINATION,
         STORAGE_PRIMARY_TRANSFER_OVERLAY_SOURCE,
         STORAGE_PRIMARY_TRANSFER_OVERLAY_SIZE),
        (STORAGE_PRIMARY_SECTOR_READ_OVERLAY_DESTINATION,
         STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SOURCE,
         STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SIZE),
        (STORAGE_NAND_STATUS_OVERLAY_DESTINATION,
         STORAGE_NAND_STATUS_OVERLAY_SOURCE,
         STORAGE_NAND_STATUS_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    # Recover the exact high-level resource/application launcher and every
    # linked function in its bounded call closure.  The source-50 leaves must
    # be embedded because the vendor loader has made that bank writable by
    # the time this late resident installer executes.
    for destination, source, size in APPLICATION_LAUNCH_COPY_OVERLAYS:
        words.extend(copy_code_to_overlay_words(destination, source, size))
    for destination, source, size in APPLICATION_LAUNCH_EMBEDDED_OVERLAYS:
        words.extend(embed_program_overlay_words(destination, source, size))
    # The native main-result scanner is the upstream selector for that launch
    # sequence.  Install its currently recovered exact call closure here too.
    for destination, source, size in APPLICATION_RESULT_SCAN_COPY_OVERLAYS:
        words.extend(copy_code_to_overlay_words(destination, source, size))
    for destination, source, size in APPLICATION_RESULT_SCAN_EMBEDDED_OVERLAYS:
        words.extend(embed_program_overlay_words(destination, source, size))
    # The exact two-index wrapper cannot occupy linked 33:1BBA: that address
    # is also the live shared epilogue of the flat 33:18xx UI routine and the
    # prologue window of 33:1BC8.  The state-50 ROM call was retargeted while
    # its resident words were built; retarget the two recovered RAM-overlay
    # callers only after their exact bodies have been installed here.
    for destination, source in (
        (APPLICATION_STORAGE_SCAN_MODE_PAIR_CALL,
         APPLICATION_STORAGE_SCAN_MODE_PAIR_CALL_SOURCE),
        (APPLICATION_RESULT_ITEM_RENDER_MODE_PAIR_CALL,
         APPLICATION_RESULT_ITEM_RENDER_MODE_PAIR_CALL_SOURCE),
    ):
        if program_source_words(source, 4) != [
            0xBD00 | (APPLICATION_RESULT_MODE_PAIR_LINKED_DESTINATION >> 16),
            APPLICATION_RESULT_MODE_PAIR_LINKED_DESTINATION & 0xFFFF,
        ]:
            raise ValueError(
                f"mode-pair call signature changed at {source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (0xBD00 | (APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION >> 16),
             APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION & 0xFFFF),
        ))
    for destination, source, size in (
        (APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_DESTINATION,
         APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SOURCE,
         APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SIZE),
        (APPLICATION_SYSTEM_REGISTRY_RESULT_OVERLAY_DESTINATION,
         APPLICATION_SYSTEM_REGISTRY_RESULT_OVERLAY_SOURCE,
         APPLICATION_SYSTEM_REGISTRY_RESULT_OVERLAY_SIZE),
        (APPLICATION_SYSTEM_REGISTRY_FALLBACK_OVERLAY_DESTINATION,
         APPLICATION_SYSTEM_REGISTRY_FALLBACK_OVERLAY_SOURCE,
         APPLICATION_SYSTEM_REGISTRY_FALLBACK_OVERLAY_SIZE),
    ):
        words.extend(embed_program_overlay_words(destination, source, size))
    if program_source_words(APPLICATION_FILE_ENTRY_BUILD_CALL_SOURCE, 4) != [
        0xBD00 | (APPLICATION_FILE_ENTRY_BUILD_LINKED_DESTINATION >> 16),
        APPLICATION_FILE_ENTRY_BUILD_LINKED_DESTINATION & 0xFFFF,
    ]:
        raise ValueError(
            "file-entry builder call signature changed at "
            f"{APPLICATION_FILE_ENTRY_BUILD_CALL_SOURCE:06X}"
        )
    # This must follow the embedded 5F:C1A6 copy above; writing it earlier is
    # silently undone when that complete relocated function is installed.
    words.extend(write_program_words(
        APPLICATION_FILE_ENTRY_BUILD_CALL,
        (0xBD00 | (APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION >> 16),
         APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION & 0xFFFF),
    ))
    if program_source_words(
            APPLICATION_SYSTEM_REGISTRY_RESULT_CALL_SOURCE, 4) != [
        0xBD00 | (
            APPLICATION_SYSTEM_REGISTRY_RESULT_LINKED_DESTINATION >> 16
        ),
        APPLICATION_SYSTEM_REGISTRY_RESULT_LINKED_DESTINATION & 0xFFFF,
    ]:
        raise ValueError(
            "system-registry result call signature changed at "
            f"{APPLICATION_SYSTEM_REGISTRY_RESULT_CALL_SOURCE:06X}"
        )
    words.extend(write_program_words(
        APPLICATION_SYSTEM_REGISTRY_RESULT_CALL,
        (0xBD00 | (
            APPLICATION_SYSTEM_REGISTRY_RESULT_OVERLAY_DESTINATION >> 16
         ),
         APPLICATION_SYSTEM_REGISTRY_RESULT_OVERLAY_DESTINATION & 0xFFFF),
    ))
    if (len(APPLICATION_SYSTEM_REGISTRY_ENTRY_CALLS) !=
            len(APPLICATION_SYSTEM_REGISTRY_ENTRY_CALL_SOURCES)):
        raise ValueError("system-registry entry call/source count mismatch")
    for destination, source in zip(
        APPLICATION_SYSTEM_REGISTRY_ENTRY_CALLS,
        APPLICATION_SYSTEM_REGISTRY_ENTRY_CALL_SOURCES,
    ):
        if program_source_words(source, 4) != [
            0xBD00 | (
                APPLICATION_SYSTEM_REGISTRY_ENTRY_LINKED_DESTINATION >> 16
            ),
            APPLICATION_SYSTEM_REGISTRY_ENTRY_LINKED_DESTINATION & 0xFFFF,
        ]:
            raise ValueError(
                f"system-registry entry call signature changed at "
                f"{source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (0xBD00 | (
                APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_DESTINATION >> 16
             ),
             APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_DESTINATION & 0xFFFF),
        ))
    for destination, source, old_target, new_target, label in (
        (APPLICATION_SYSTEM_REGISTRY_ENTRY_RECORD_ACCEPT_CALL,
         APPLICATION_SYSTEM_REGISTRY_ENTRY_RECORD_ACCEPT_CALL_SOURCE,
         STORAGE_RECORD_ACCEPT_LINKED_DESTINATION,
         STORAGE_RECORD_ACCEPT_OVERLAY_DESTINATION,
         "system-registry entry predicate"),
        (APPLICATION_SYSTEM_REGISTRY_RESULT_FALLBACK_CALL,
         APPLICATION_SYSTEM_REGISTRY_RESULT_FALLBACK_CALL_SOURCE,
         APPLICATION_SYSTEM_REGISTRY_FALLBACK_LINKED_DESTINATION,
         APPLICATION_SYSTEM_REGISTRY_FALLBACK_OVERLAY_DESTINATION,
         "system-registry result fallback"),
    ):
        if program_source_words(source, 4) != [
            0xBD00 | (old_target >> 16), old_target & 0xFFFF,
        ]:
            raise ValueError(f"{label} call signature changed at {source:06X}")
        words.extend(write_program_words(
            destination,
            (0xBD00 | (new_target >> 16), new_target & 0xFFFF),
        ))
    # The timer-idle overlay's four bit helpers are independently called
    # source-50 leaves whose linked segment-33 PCs are also live renderer
    # fall-through locations.  Install them out of line and retarget only the
    # exact copied timer body after that body is resident.
    for destination, source, size in (
            APPLICATION_TIMER_IDLE_REGISTER_LEAF_OVERLAYS):
        words.extend(embed_program_overlay_words(destination, source, size))
    for destination, source, linked_target, relocated_target in (
            APPLICATION_TIMER_IDLE_REGISTER_LEAF_CALLS):
        if program_source_words(source, 4) != [
            0xBD00 | (linked_target >> 16), linked_target & 0xFFFF,
        ]:
            raise ValueError(
                f"timer-idle register leaf call signature changed at "
                f"{source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (0xBD00 | (relocated_target >> 16),
             relocated_target & 0xFFFF),
        ))
    # 33:6BF2 is simultaneously a source-image entry and a live fall-through
    # in the flat segment-33 function at 33:6BB2.  Install its exact tiny
    # source-50 leaf out of line, then patch only the two recovered result
    # scanner callers after their complete bodies have been installed.
    words.extend(embed_program_overlay_words(
        STORAGE_RECORD_ACCEPT_OVERLAY_DESTINATION,
        STORAGE_RECORD_ACCEPT_OVERLAY_SOURCE,
        STORAGE_RECORD_ACCEPT_OVERLAY_SIZE,
    ))
    for destination, source in (
        (APPLICATION_RESULT_OBJECT_FINALIZE_RECORD_ACCEPT_CALL,
         APPLICATION_RESULT_OBJECT_FINALIZE_RECORD_ACCEPT_CALL_SOURCE),
        (APPLICATION_RESULT_OBJECT_CLOSE_RECORD_ACCEPT_CALL,
         APPLICATION_RESULT_OBJECT_CLOSE_RECORD_ACCEPT_CALL_SOURCE),
    ):
        if program_source_words(source, 4) != [
            0xBD00 | (STORAGE_RECORD_ACCEPT_LINKED_DESTINATION >> 16),
            STORAGE_RECORD_ACCEPT_LINKED_DESTINATION & 0xFFFF,
        ]:
            raise ValueError(
                f"storage-record predicate call signature changed at "
                f"{source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (0xBD00 | (STORAGE_RECORD_ACCEPT_OVERLAY_DESTINATION >> 16),
             STORAGE_RECORD_ACCEPT_OVERLAY_DESTINATION & 0xFFFF),
        ))
    # Install the complete storage graph before the first resource lifecycle.
    # Ordinary PRG banks remain readable and use the native guest byte-copy
    # loop; segment 50 is mutable, so its short leaves are embedded in
    # this resident installer exactly as shipped.
    for destination, source, size in APPLICATION_RESOURCE_STORAGE_COPY_OVERLAYS:
        words.extend(copy_code_to_overlay_words(destination, source, size))
    for destination, source, size in (
            APPLICATION_RESOURCE_STORAGE_EMBEDDED_OVERLAYS):
        words.extend(embed_program_overlay_words(destination, source, size))
    # The other three live callers are installed application overlays.  Patch
    # them only after their exact bodies have been copied, leaving the
    # unrelated 20:E914..20:FE80 fall-through code intact.
    for destination, source in (
        (APPLICATION_STORAGE_CAPACITY_SECTOR_PROBE_CALL,
         APPLICATION_STORAGE_CAPACITY_SECTOR_PROBE_CALL_SOURCE),
        (APPLICATION_LAUNCH_RECORD_APPLY_SECTOR_PROBE_CALL,
         APPLICATION_LAUNCH_RECORD_APPLY_SECTOR_PROBE_CALL_SOURCE),
        (APPLICATION_FILE_RECORD_RESOLVE_SECTOR_PROBE_CALL,
         APPLICATION_FILE_RECORD_RESOLVE_SECTOR_PROBE_CALL_SOURCE),
    ):
        if program_source_words(source, 4) != [
            0xBD00 | (
                APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION >> 16
            ),
            APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION & 0xFFFF,
        ]:
            raise ValueError(
                f"storage-sector probe call signature changed at {source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (0xBD00 | (
                APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION >> 16
             ),
             APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION & 0xFFFF),
        ))
    # A completed modal lifecycle reaches these three cleanup calls.  Their
    # linked 20:E914 entry is a flat fall-through fragment and eventually
    # returns through 20:FC88 without unwinding a local frame.  Retarget the
    # exact SCALL instructions after all application bodies have been copied;
    # the complete 3D:E914 routine was installed at 5F:E914 by the main-chain
    # installer, so its same-PC absolute AJMPs remain valid.
    if (len(APPLICATION_FOREGROUND_OBJECT_UPDATE_CALLS) !=
            len(APPLICATION_FOREGROUND_OBJECT_UPDATE_CALL_SOURCES)):
        raise ValueError("foreground object-update call/source count mismatch")
    for destination, source in zip(
        APPLICATION_FOREGROUND_OBJECT_UPDATE_CALLS,
        APPLICATION_FOREGROUND_OBJECT_UPDATE_CALL_SOURCES,
    ):
        if program_source_words(source, 4) != [
            0xBD00 | (
                APPLICATION_FOREGROUND_OBJECT_UPDATE_LINKED_DESTINATION >> 16
            ),
            APPLICATION_FOREGROUND_OBJECT_UPDATE_LINKED_DESTINATION & 0xFFFF,
        ]:
            raise ValueError(
                "foreground object-update call signature changed at "
                f"{source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (0xBD00 | (
                APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_DESTINATION >> 16
             ),
             APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_DESTINATION & 0xFFFF),
        ))
    # Exact 25:5858 deliberately retires the temporary same-PC 2D:3460
    # storage resolver after unit construction, because that linked window is
    # reused by the application.  The later exact capacity scan still needs
    # the same resolver through its sole source-proven call at 2A:D402.  The
    # immutable, instruction-identical copy at 07:4000 already preserves its
    # internal AJMPs after relocation; patch this call only after the ROM-01
    # loader has recopied 2A:D374.  This keeps the vendor lifecycle ordering
    # without pinning the collided 2D window or synthesizing a callback.
    if program_source_words(
            APPLICATION_STORAGE_RECORD_LOOKUP_DRIVER_CALL_SOURCE, 4
    ) != [0xBD2D, 0x3460]:
        raise ValueError("storage record-lookup driver call signature changed")
    words.extend(write_program_words(
        APPLICATION_STORAGE_RECORD_LOOKUP_DRIVER_CALL,
        (0xBD00 | (RESIDENT_STORAGE_DRIVER_ADDRESS >> 16),
         RESIDENT_STORAGE_DRIVER_ADDRESS & 0xFFFF),
    ))
    # These exact foreground state modules were recovered after the fixed
    # ROM-01 loader slot had reached its next resident routine.  The main
    # chain already calls this segment-1A installer before any foreground
    # execution, preserving the same runtime ordering.
    for destination, source, size in (
        (APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_STATE50_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_STATE50_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_STATE50_OVERLAY_SIZE),
        (APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_DESTINATION,
         APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_SOURCE,
         APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_SIZE),
    ):
        words.extend(copy_code_to_overlay_words(destination, source, size))
    # Source segment 50 is writable at this point, so its exact state wrapper
    # block must come from immutable literal words in a resident sub-installer.
    words.extend((
        0xBD00 | (APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS
                  >> 16),
        APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS & 0xFFFF,
    ))
    # The segment-1A installer has only 0xA4 bytes before its next resident
    # routine.  Keep the literal cleanup body in the otherwise-free tail of
    # resident segment 0C and invoke that guest installer here.
    words.extend((
        0xBD00 | (APPLICATION_FOREGROUND_STATE50_CLEANUP_INSTALLER_ADDRESS
                  >> 16),
        APPLICATION_FOREGROUND_STATE50_CLEANUP_INSTALLER_ADDRESS & 0xFFFF,
    ))
    words.append(RETS)
    return words


def wide_accumulate_installer_words() -> list[int]:
    """Install compact collision-safe source-50 leaves and caller patches."""
    words = embed_program_overlay_words(
        WIDE_ACCUMULATE_OVERLAY_DESTINATION,
        WIDE_ACCUMULATE_OVERLAY_SOURCE,
        WIDE_ACCUMULATE_OVERLAY_SIZE,
    )
    # Keep this additional 0x38-byte leaf out of the nearly-full 1A:0000
    # region-extra installer.  This resident 0C:5200 sub-installer is already
    # invoked before registry initialization and has a large gap to 0C:8622.
    words.extend(embed_program_overlay_words(
        APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_DESTINATION,
        APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_SOURCE,
        APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_SIZE,
    ))
    if len(WIDE_ACCUMULATE_CALLS) != len(WIDE_ACCUMULATE_CALL_SOURCES):
        raise ValueError("wide-accumulate call/source count mismatch")
    for destination, source in zip(
        WIDE_ACCUMULATE_CALLS,
        WIDE_ACCUMULATE_CALL_SOURCES,
    ):
        if program_source_words(source, 4) != [
            0xBD00 | (WIDE_ACCUMULATE_LINKED_DESTINATION >> 16),
            WIDE_ACCUMULATE_LINKED_DESTINATION & 0xFFFF,
        ]:
            raise ValueError(
                f"wide-accumulate call signature changed at {source:06X}"
            )
        words.extend(write_program_words(
            destination,
            (0xBD00 | (WIDE_ACCUMULATE_OVERLAY_DESTINATION >> 16),
             WIDE_ACCUMULATE_OVERLAY_DESTINATION & 0xFFFF),
        ))
    words.append(RETS)
    return words


def application_foreground_state_handler_installer_words() -> list[int]:
    """Restore exact foreground and root-page dependencies.

    This already-exercised 1A:5500 installer has room before the independent
    1A:6000 factory-default installer.  Keeping the source-3F copy here avoids
    growing 1A:0000 into the exact 1A:423C resident dispatcher and preserves
    the established pre-foreground execution boundary.  The bootstrap root
    controller reaches 27:571A before the later 03:0080 manager can exchange
    the full menu overlay set, so install that page-object builder and its
    directly called 29:6C7C layout child here as early prerequisites; the
    source-44 body includes the six-target table at destination 27:58C2.
    """
    return [
        *copy_code_to_overlay_words(
            APPLICATION_FOREGROUND_MODE_OVERLAY_DESTINATION,
            APPLICATION_FOREGROUND_MODE_OVERLAY_SOURCE,
            APPLICATION_FOREGROUND_MODE_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_DESTINATION,
            APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SOURCE,
            APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_DESTINATION,
            APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE,
            APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_DESTINATION,
            APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SOURCE,
            APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_DESTINATION,
            APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_SOURCE,
            APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_SIZE,
        ),
        0xBD00 | (APPLICATION_ROOT_STREAM_INSTALLER_ADDRESS >> 16),
        APPLICATION_ROOT_STREAM_INSTALLER_ADDRESS & 0xFFFF,
        *copy_code_to_overlay_words(
            APPLICATION_ROOT_ITEM_MASK_OVERLAY_DESTINATION,
            APPLICATION_ROOT_ITEM_MASK_OVERLAY_SOURCE,
            APPLICATION_ROOT_ITEM_MASK_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_DESTINATION,
            APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_SOURCE,
            APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_DESTINATION,
            APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_SOURCE,
            APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            APPLICATION_FOREGROUND_STATE_HANDLER_OVERLAY_DESTINATION,
            APPLICATION_FOREGROUND_STATE_HANDLER_OVERLAY_SOURCE,
            APPLICATION_FOREGROUND_STATE_HANDLER_OVERLAY_SIZE,
        ),
        RETS,
    ]


def application_root_stream_installer_words() -> list[int]:
    """Install the exact root status output closure."""
    return [
        *copy_code_to_overlay_words(
            APPLICATION_ROOT_STREAM_WRITE_OVERLAY_DESTINATION,
            APPLICATION_ROOT_STREAM_WRITE_OVERLAY_SOURCE,
            APPLICATION_ROOT_STREAM_WRITE_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_DESTINATION,
            APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_SOURCE,
            APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_SIZE,
        ),
        *embed_program_overlay_words(
            APPLICATION_ROOT_STREAM_MOVE_OVERLAY_DESTINATION,
            APPLICATION_ROOT_STREAM_MOVE_OVERLAY_SOURCE,
            APPLICATION_ROOT_STREAM_MOVE_OVERLAY_SIZE,
        ),
        *copy_code_to_overlay_words(
            APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_DESTINATION,
            APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_SOURCE,
            APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_SIZE,
        ),
        RETS,
    ]


def application_menu_resource_decoder_installer_words() -> list[int]:
    """Install the exact large 15:6C56 mask-ROM resource decoder."""
    return [
        *embed_program_overlay_words(
            APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_DESTINATION,
            APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_SOURCE,
            APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_SIZE,
        ),
        RETS,
    ]


def install_overlay_patch_words() -> list[int]:
    """Install all currently recovered bootstrap and run-time overlays."""
    return [
        *install_runtime_overlay_words(),
        *install_copy_overlay_words(),
    ]


def default_overlay_installer_words() -> list[int]:
    """Run the default overlay installation as a resident subroutine."""
    return [*install_overlay_patch_words(), RETS]


def clear_buffer_words(base_pc: int = CLEAR_OVERLAY_TARGET_PC) -> list[int]:
    """Clear ``length`` bytes at a far pointer using only DMCU instructions."""
    # ABI after SCALL: [SP+4]=length, [SP+6]=pointer high, [SP+8]=low.
    words = [
        *mov_gpr_from_sp(0, 4),
        *mov_gpr_from_sp(1, 6),
        *mov_gpr_from_sp(2, 8),
        0x4C21,                       # SL R2, #1 (low -> shift buffer)
        0x5C11,                       # SLOSB R1, #1 (physical -> bank)
        0x58F1,                       # PUSH R1
        0x1F90,                       # POP DS0
        0x4D21,                       # SR R2, #1 (15-bit bank offset)
        0x4930,                       # MOVB RB3, #0
    ]
    loop_pc = base_pc + len(words) * 2
    # The two-word conditional branch is followed by three words of loop body
    # and a two-word back edge.
    exit_pc = loop_pc + 0x0E
    words.extend([
        0x5600,                       # CMP R0, #0
        0xAC01, exit_pc,              # AJMP EQ, exit
        0x1B23,                       # MOVB [R2++], RB3
        0x5201,                       # SUB R0, #1
        0xAC00, loop_pc,              # AJMP ALWAYS, loop
        0x4800,                       # MOV R0, #0
        RETS,
    ])
    return words


def multiply_u32_words() -> list[int]:
    """Return the low 32 bits of two 32-bit operands in R0:R1.

    ABI after the original caller's SCALL:
      [SP+4]:[SP+6] = left high:low
      [SP+8]:[SP+10] = right high:low

    Only the low halves of the two cross products contribute to the low
    32-bit result. DMCU UMUL places its 32-bit product in R6:R7.
    """
    return [
        *mov_gpr_from_sp(0, 4),       # left high
        *mov_gpr_from_sp(1, 6),       # left low
        *mov_gpr_from_sp(2, 8),       # right high
        *mov_gpr_from_sp(3, 10),      # right low
        0xC113,                       # UMUL R1, R3 (low * low)
        0x0846,                       # MOV R4, R6 (result high)
        0x58F7,                       # PUSH R7 (result low)
        0xC103,                       # UMUL R0, R3 (high * low)
        0x1047,                       # ADD R4, R7
        0xC112,                       # UMUL R1, R2 (low * high)
        0x1047,                       # ADD R4, R7
        0x381F,                       # POP R1 (result low)
        0x0804,                       # MOV R0, R4 (result high)
        RETS,
    ]


def far_memcpy_words() -> list[int]:
    """Return the exact shipped five-word far-memory-copy implementation.

    V3.80 has sixteen direct calls to resident ``18:6D56``.  The complete
    same-PC body survives at ``35:6D56..35:6E70`` and implements::

        memcpy(dest_high, dest_low, source_high, source_low, length)

    It is call-free, preserves the required registers, handles forward
    overlap, normalizes both selectors through F2E0, and crosses 32-KiB data
    banks.  Keeping those original instructions is required for destinations
    in internal SRAM as well as ordinary external RAM.
    """
    return program_source_words(FAR_MEMCPY_SOURCE, FAR_MEMCPY_SIZE)


def reverse_far_memmove_words() -> list[int]:
    """Return the guest implementation of descending far-memory move.

    ABI after ``SCALL`` and ``LINK #2``::

        [FP+06]:[FP+08] destination final-byte far pointer
        [FP+0A]:[FP+0C] source final-byte far pointer
        [FP+0E]         byte length

    The two surviving callers construct end pointers explicitly.  Copying
    downward makes overlapping right shifts safe.  Selector setup mirrors
    the exact shipped forward-copy implementations, including the F2E0
    normalization needed for internal SRAM.  The loop also adjusts DS0/DS1
    when a decrement crosses a 32-KiB data-bank boundary.
    """
    a = _DMCUAssembler(REVERSE_FAR_MEMMOVE_OVERLAY_DESTINATION)
    a.emit(0x2E02)                    # LINK #2
    for register in range(6):
        a.emit(0x58F0 | register)     # preserve R0..R5
    a.emit(
        0x1F10, 0x1F11,              # preserve DS0/DS1
        0x58FB, 0x1F0A, 0x1F02,      # preserve R11 and memory-control SFRs
        0x781B, 0x0006,              # R1 = destination high
        0x782B, 0x0008,              # R2 = destination low
        0x783B, 0x000A,              # R3 = source high
        0x784B, 0x000C,              # R4 = source low
        0x785B, 0x000E,              # R5 = length
        0x5650,                       # CMP R5,#0
    )
    a.ajmp("done", 0x01)             # empty move

    # Convert both 24-bit byte pointers to 32-KiB data selectors.  R4 carries
    # bit 15 so its indirect byte access selects DS1, matching the vendor
    # forward-copy bodies at 25:43A6 and 35:6D56.
    a.emit(
        0x0801, 0x4C21, 0x5C01, 0x4D21,
        0x3F10, 0x8810, 0xF2E0,
        0x0803, 0x4C41, 0x5C01, 0x4D41,
        0x3F10, 0x8811, 0xF2E0,
        0x75F4, 0x8000,
    )

    a.label("loop")
    a.emit(
        0x2B24,                       # MOVB [R2],[R4]
        0x5251,                       # --length
        0x5650,
    )
    a.ajmp("done", 0x01)

    # Destination offsets use DS0 and live in 0000..7FFF.  Underflow from
    # 0000 produces FFFF; fold that back to 7FFF and decrement the selector.
    a.emit(0x5221, 0x76F2, 0x8000)
    a.ajmp("destination_ready", 0x05)  # C/UL: still below 8000
    a.emit(0x74F2, 0x7FFF, 0x7210, 0x0001)
    a.label("destination_ready")

    # Source offsets use DS1 and live in 8000..FFFF.  Crossing below 8000
    # decrements DS1 and folds the logical pointer back to FFFF.
    a.emit(0x5241, 0x76F4, 0x8000)
    a.ajmp("source_ready", 0x06)       # NC/UGE: still at/above 8000
    a.emit(0x7211, 0x0001, 0x75F4, 0x8000)
    a.label("source_ready")
    a.ajmp("loop")

    a.label("done")
    a.emit(
        0x1F82, 0x1F8A, 0x38BF,
        0x1F91, 0x1F90,
        0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x380F,
        0x2F00, 0x3F00, RETS,
    )
    return a.finish()


def cold_boot_words(startup_context: int = 0) -> list[int]:
    """Enter NP560.PRG's compiler-generated cold-start continuation.

    The reset vector calls 03:0030 and then jumps to 33:4F50.  That target is
    the instruction immediately after ``SL R1,#1`` inside a larger function,
    rather than a normal function entry.  Its surrounding code proves the
    required zero-context cold-start state:

      * FP/SP point at the synthetic outer frame at FFF8;
      * its far return enters the resident event loop (reconstructed here at
        03:0080 because the original ROM bytes and exact continuation layout
        are unavailable);
      * R0:R1 is context+0x38 after the omitted ``SL R1,#1``;
      * R2:R3 is context+0x30.

    The context is selected when the clean-room image is generated. This
    makes the inferred loader handoff explicit rather than hiding it in QEMU.
    The public 03:0030 entry jumps here so that its two-word trampoline cannot
    overlap the event-loop continuation. It then jumps to the caller
    continuation instead of using RETS because the resident entry replaces
    the ordinary SCALL frame with the outer frame.
    """
    words: list[int] = [
        0xBD00 | (DEFAULT_OVERLAY_INSTALLER_ADDRESS >> 16),
        DEFAULT_OVERLAY_INSTALLER_ADDRESS & 0xFFFF,
        # This fixed, otherwise-unreferenced NP560.PRG entry clears the
        # BSS/data windows and establishes low-level SFR state. It has an
        # ordinary no-argument ABI and returns cleanly. 20:026A is another
        # startup-looking entry. The strict initializer-overlay path now
        # reaches it with recovered overlays and exact +0x1D source storage,
        # while this shorter default path still skips both vendor initializer
        # chains and therefore does not claim their full cold-start ordering.
        0xBD20, 0x0030,
        *boot_frame_handoff_words(startup_context),
    ]
    return words


def boot_frame_handoff_words(startup_context: int = 0) -> list[int]:
    """Build the inferred outer frame and enter reset continuation 20:0004.

    This is split from :func:`cold_boot_words` so the initializer-overlay
    exploration path can execute the same guest-visible handoff after both
    vendor initializer chains and 20:026A have returned.  It does not repeat
    overlay installation or the 20:0030 data-window clear.
    """
    if not 0 <= startup_context <= 0xFFFFFF:
        raise ValueError("startup context must be a 24-bit physical address")
    source = (startup_context + 0x38) & 0xFFFFFF
    destination = (startup_context + 0x30) & 0xFFFFFF
    words: list[int] = [
        0x68F0, (startup_context >> 16) & 0xFF,
        *mov_mmio_from_gpr(0xFFF4, 0),
        0x68F0, startup_context & 0xFFFF,
        *mov_mmio_from_gpr(0xFFF6, 0),
        0x4800,
        *mov_mmio_from_gpr(0xFFF8, 0),
    ]
    words.extend(
        [
            0x4803,                   # MOV R0, #3 (event-loop segment)
            *mov_mmio_from_gpr(0xFFFA, 0),
            0x68F0, 0x0080,           # MOV R0, #0x0080 (event-loop PC)
            *mov_mmio_from_gpr(0xFFFC, 0),
            0x68FB, 0xFFF8,           # MOV R11/FP, #0xFFF8
            0x68FF, 0xFFF8,           # MOV R15/SP, #0xFFF8
            0x68F0, (source >> 16) & 0xFF,
            0x68F1, source & 0xFFFF,
            0x68F2, (destination >> 16) & 0xFF,
            0x68F3, destination & 0xFFFF,
            0x4C11,                   # SL R1, #1; establishes shift buffer
            0xAD20, 0x0004,           # SJMP 20:0004
        ]
    )
    return words


def resident_event_loop_words(
    startup_context: int = 0,
    initial_event: int | None = None,
) -> list[int]:
    """Poll the keyboard latch and dispatch native application events.

    The complete application handler at 33:4510 has the ordinary stack ABI
    ``handler(u16 event, far_pointer context)``.  The reset vector already
    enters the second half of that handler's 0x008E activation branch at
    33:4F50, so repeating 0x008E here would perform initialization twice.

    A zero far pointer is not treated as NULL: bank 0 is writable external RAM
    and the cold-start continuation accesses context fields through 00:0000.
    Keep the context selected for the loader handoff, including zero, and wait
    for hardware events.
    """
    if not 0 <= startup_context <= 0xFFFFFF:
        raise ValueError("startup context must be a 24-bit physical address")
    if initial_event is not None and not 0 <= initial_event <= 0xFFFF:
        raise ValueError("initial event must fit in 16 bits")
    words: list[int] = []
    if initial_event is not None:
        # Exploration-only initial dispatch. It uses the same ordinary
        # handler ABI as hardware keyboard events, then falls into polling.
        # The IRQ vector does not preserve R1, so use the CPU's bounded CRIT
        # windows while carrying the event register into its stack slot.
        words.extend([
            0x3F03,                   # protect four argument-build instructions
            0x68F1, initial_event,
            0x68F0, startup_context & 0xFFFF,
            0x58F0,
            0x68F0, (startup_context >> 16) & 0xFF,
            0x3F02,                   # push high/event and enter the callee
            0x58F0,
            0x58F1,
            0xBD33, 0x4510,
            0x50F6,
        ])
    loop_pc = 0x0080 + len(words) * 2
    words.extend([
        0x3F03,                       # protect read/test/branch from IRQ clobber
        *mov_gpr_from_mmio(0, KEYBOARD_EVENT),
        0x5600,                       # CMP R0, #0
        0xAC01, loop_pc,              # AJMP EQ, poll
        0x3F03,                       # preserve event across argument setup
        0x0810,                       # MOV R1, R0 (event)
        0x68F0, startup_context & 0xFFFF,
        0x58F0,                       # PUSH context low
        0x68F0, (startup_context >> 16) & 0xFF,
        0x3F02,                       # protect remaining pushes and SCALL
        0x58F0,                       # PUSH context high
        0x58F1,                       # PUSH event
        0xBD33, 0x4510,
        0x50F6,                       # ADD SP, #6
        0xAD03, loop_pc,              # poll again
    ])
    return words


def native_application_scheduler_words(
    stop_after_return: bool = False,
    factory_linked_startup: bool = False,
) -> list[int]:
    """Enter the complete shipped system main from the resident manager.

    Historical probes execute the source-position copy at ``20:026A``.  The
    recovered factory path instead installs those exact bytes at their linked
    execution address ``03:026A``.  Re-enter the address belonging to the
    selected startup mode; calling the +0x1D storage copy after factory boot
    executes unrelated data and leaks one partial frame per lifecycle.

    The system main establishes the compiler frame, initializes the
    system-facing registers, invokes resident loader ``01:0200``, and only
    then transfers to the exact installed ``2D:7DD2`` continuation.  In
    particular, ``2D:7DD2`` begins with ``ADD SP,#8``: it is a compiler
    continuation which consumes the transfer frame and two words prepared by
    its parent, not an ordinary stand-alone function entry.

    With no hardware ROM to identify the original application-selection
    policy, the clean-room system image retains the same complete shipped
    system main.  Its foreground exit deliberately unwinds through 2D:7F80 to
    the real 20:0320 epilogue before returning here.  Re-entering the complete
    parent preserves the proven continuation ABI instead of relying on stale
    frame words left by the previous lifecycle.

    The loop remains an explicitly inferred application-selection policy,
    implemented entirely as guest DMCU instructions.  It does not claim to
    reconstruct the missing factory manager's menu/selection decisions.
    """
    system_main = (
        FACTORY_SYSTEM_MAIN_DESTINATION
        if factory_linked_startup else FACTORY_SYSTEM_MAIN_SOURCE
    )
    words: list[int] = []
    if factory_linked_startup:
        # Storage lifecycle setup now belongs to the 01:0200 boundary reached
        # after exact 20:0030 has cleared application BSS.  Calling 25:5858
        # here used to build the list too early; 20:0164 then zeroed every
        # next-link before the first fopen.
        # Exact 20:0030 zeroes the complete 50:0000..53:FFFF external-RAM
        # application arena, including A2:28E0.  The first linked application
        # initializer at 31:A914 then calls exact 25:206E with source
        # 10:D012.  Exact 29:AC4E divides that byte address by A2:28E0; zero
        # therefore routes the read to logical block E93 instead of E9B.
        # The shipped foreground worker independently writes 0x0200 at
        # 25:CCB8, and 0x10D012 / 0x0200 advances the recovered E93 volume
        # base by exactly eight blocks to the checkpoint's E9B resource
        # payload.  Reconstruct the missing manager's required publication
        # immediately before the foreground starts, as guest DMCU code.
        words.extend((
            0x68F0, 0x0200,       # MOV REG[F0],#0200
            0x6810, 0x00A2,       # MOV DS0,#00A2
            0xC700,               # data-segment pipeline NOP
            0xA8F0, 0x28E0,       # MOV [28E0],REG[F0]
        ))
    words.extend([
        0xBD00 | (system_main >> 16),
        system_main & 0xFFFF,         # complete shipped system main
        0xAD03,
        ((NATIVE_APPLICATION_SCHEDULER_ADDRESS + 4) & 0xFFFF
         if stop_after_return
         else NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF),
    ])
    return words


def factory_default_catalogue_probe_words() -> list[int]:
    """Call the exact recovered 2A:A952 catalogue initializer, then hold.

    Source 47:A952 is the complete factory routine selected by the shipped
    application-result mapper when its persistent selector has no explicit
    application mapping.  The resident ROM policy that reaches that mapper is
    absent, so this diagnostic isolates the exact guest routine after the
    shipped system-main prefix has initialized hardware and application
    overlays.  It supplies no key or fabricated application result.
    """
    return [
        0xBD2A, 0xA952,               # exact recovered guest routine
        0xAD03, 0x0084,               # hold after its ordinary return
    ]


def fixed_launch_wrapper_probe_words() -> list[int]:
    """Reinstall and enter the exact 33:3CC6 resource wrapper, then hold.

    Source 50:3CC6 passes the development-resource pointer 31:F5E2 to exact
    2E:D34A.  Its placement after a foreground lifecycle is exploration-only:
    neither a surviving caller nor the adjacent 50:3CA6 function proves that
    this wrapper participates in the factory root-menu transition.

    The preceding foreground dynamically occupies the same segment-33 code
    window, so the resident boundary must exchange the wrapper after that
    lifecycle returns. Doing the exchange here also tests the missing
    manager's overlay-lifetime responsibility instead of relying on a stale
    copy installed by 01:0200.
    """
    return [
        0xBD00 | (RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS >> 16),
        RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS & 0xFFFF,
        0xBD33, 0x3CC6,
        0xAD03, (NATIVE_APPLICATION_SCHEDULER_ADDRESS + 8) & 0xFFFF,
    ]


def direct_generic_menu_text_stream_logical_bytes() -> bytes:
    """Return the probe's logical GB18030 menu stream.

    Resident ``11:5C12`` recognizes CR/LF while splitting the current input
    window into its 0x3C-byte display records. The terminal NUL lets unused
    layout rows return cleanly after the five recovered root labels.
    """
    return (
        b"\r\n".join(
            label.encode("gb18030")
            for label in DIRECT_GENERIC_MENU_TEXT_STREAM_LABELS
        ) + b"\x00"
    )


def direct_generic_menu_text_stream_words() -> list[int]:
    """Encode the logical stream for the DMCU's word-swapped byte lane."""
    logical = direct_generic_menu_text_stream_logical_bytes()
    padded = logical + (b"\x00" if len(logical) & 1 else b"")
    stored = initializer_probe_storage_bytes(padded)
    return [
        int.from_bytes(stored[offset:offset + 2], "little")
        for offset in range(0, len(stored), 2)
    ]


def generic_main_menu_pointer_index_logical_bytes(
        direct_text_stream: bool = False) -> bytes:
    """Build the resident selector's page-number to record-pointer table.

    Exact ``2A:322A`` reads a little-endian maximum page number followed by
    signed 24-bit pointers.  It reads both the selected pointer and its
    successor, so the 25 recovered records require a twenty-sixth end
    pointer.  The records are fixed-size, contiguous resident data at
    ``1C:9748..1C:9DBA``. The isolated direct-render probe instead points
    page zero at a separate CR/LF text stream; the exact hierarchy table stays
    intact for the recovered catalogue/menu-manager path.
    """
    result = bytearray((RESIDENT_MENU_PAGE_COUNT - 1).to_bytes(2, "little"))
    if direct_text_stream:
        start = DIRECT_GENERIC_MENU_TEXT_STREAM_ADDRESS
        end = start + len(direct_generic_menu_text_stream_logical_bytes())
        pointers = [start] + [end] * RESIDENT_MENU_PAGE_COUNT
    else:
        pointers = [
            RESIDENT_MENU_PAGE_TABLE_ADDRESS +
            index * RESIDENT_MENU_PAGE_RECORD_SIZE
            for index in range(RESIDENT_MENU_PAGE_COUNT + 1)
        ]
    for address in pointers:
        result.extend(address.to_bytes(3, "little"))
    return bytes(result)


def generic_main_menu_pointer_index_words(
        direct_text_stream: bool = False) -> list[int]:
    """Materialize the inferred resident page selector in external RAM."""
    logical = generic_main_menu_pointer_index_logical_bytes(
        direct_text_stream=direct_text_stream,
    )
    stored = initializer_probe_storage_bytes(logical)
    values = [
        int.from_bytes(stored[offset:offset + 2], "little")
        for offset in range(0, len(stored), 2)
    ]
    return write_program_words(RESIDENT_MENU_POINTER_INDEX_ADDRESS, values)


def generic_main_menu_pointer_index_installer_words(
        direct_text_stream: bool = False) -> list[int]:
    return [
        *generic_main_menu_pointer_index_words(
            direct_text_stream=direct_text_stream,
        ),
        RETS,
    ]


def generic_main_menu_root_publish_words() -> list[int]:
    """Publish the 33:3CC6 development resource for an isolated probe."""
    resource_segment = APPLICATION_LAUNCH_RESOURCE_DATA_ADDRESS >> 16
    resource_pc = APPLICATION_LAUNCH_RESOURCE_DATA_ADDRESS & 0xFFFF
    return [
        # 2E:D420 publishes this pointer at A0:7090/7092.  The pointed data is
        # the lirt.nwf development-path island, so this helper must not be
        # presented as a recovered root-menu descriptor publisher.
        0x68F0, resource_segment,
        0x68F1, resource_pc,
        0x6810, 0x00A0,
        0xC700,
        0xA8F0, 0x7090,
        0xA8F1, 0x7092,
        RETS,
    ]


def generic_main_menu_probe_words() -> list[int]:
    """Exercise a rejected adjacency-based launch hypothesis.

    This probe calls ``33:3CA6`` and later ``33:3CC6`` because the functions
    are adjacent in source segment 50.  Runtime evidence now rejects that as
    a root-menu chain: the latter supplies a host-build lirt.nwf path and the
    numeric-volume resolver returns FFFB.  Retain the routine only to reproduce
    the failed hypothesis while the missing 03:0080 manager policy is traced.
    """
    words = [
        # Reinstall the complete file/resource launcher closure after the
        # foreground has retired its shared overlay destinations.
        0xBD00 | (APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16),
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF,
        # Recreate the four linked storage-root records at 50:FE74 and reset
        # their per-open activity bytes before the next resident application
        # begins.  The bootstrap foreground legitimately consumed one root;
        # the absent outer manager performs this lifecycle reset.
        0xBD25, 0x5858,
        0xBD30, 0x8C1C,
        # Reinstall the immutable copies of the two adjacent source-50 launch
        # wrappers and the operation-0x0B work-table dependency before using
        # either member of the pair.
        0xBD00 | (RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS >> 16),
        RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS & 0xFFFF,
        0xBD33, 0x3CA6,
        # Foreground overlays share several menu destinations.  Exchange the
        # exact immutable PRG copies at the resident-manager boundary.
        0xBD00 | (MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS >> 16),
        MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS & 0xFFFF,
        # The absent resident selector normally publishes a compact page
        # index in the 53:* scratch arena.  Recreate that proven 2A:322A
        # input from the exact contiguous 1C:9748 page records.
        0xBD00 | (MENU_POINTER_INDEX_INSTALLER_ADDRESS >> 16),
        MENU_POINTER_INDEX_INSTALLER_ADDRESS & 0xFFFF,
        # The bootstrap foreground normally returns because of a key event.
        # The absent outer resident manager waits for the physical release
        # and consumes that foreground-owned event before starting the next
        # application.  Preserve that lifecycle boundary with the recovered
        # segment-06 release barrier, exact 30:D350 input-state initializer,
        # and exact 2F:C216 event decoder; otherwise the same Return event
        # immediately closes the menu.  The low-power bootstrap path also
        # leaves its foreground source latched at A2:2A90.  The absent manager
        # retires that one-shot source after the foreground returns; if it is
        # left set, exact dispatcher 3B:F734 regenerates event 0x008F and the
        # newly entered menu closes before its first stable frame.
        0xBD06, 0x6A02,
        0xBD30, 0xD350,
    ]
    words.extend([
        0xBD2F, 0xC216,
        # Guest-side resident-manager policy, expressed as ordinary DMCU
        # stores.  This is not a QEMU/HLE ROM-service interception.  Clear the
        # low-power debounce accumulator together with its one-shot latch so
        # the next foreground starts from a consumed source state.
        0x4800,
        0x6810, 0x00A2,
        0xC700,
        0xA8F0, 0x2A88,
        0xA8F0, 0x2A90,
        # Keep the framebuffer mode on the exact value-zero path.  Recovered
        # 31:B014 proves this publishes 50:3840 through 00:04FC, the buffer
        # already used by the readable bootstrap UI.  Value one instead
        # publishes 50:0000 and lets menu drawing overwrite executable RAM.
        0x4800,
        0x58F0,
        0xBD31, 0xB014,
        0x50F2,
    ])
    words.extend([
        # Force the generic-menu entry to initialize its persisted page flags
        # from the descriptor instead of inheriting bootstrap UI state.
        0x69F1, 0x00FF,               # MOVB REG[0xF1], #0xFF
        0x6810, 0x00A0,               # DS0 = A0 globals
        0xC700,
        0xA9F1, 0x70C2,
        0xA9F1, 0x70C3,
        # Isolated 33:3CC6 resource wrapper.  This is not a recovered second
        # half of the root-menu launch sequence.
        0xBD33, 0x3CC6,
    ])
    hold_pc = NATIVE_APPLICATION_SCHEDULER_ADDRESS + len(words) * 2
    words.extend((0xAD03, hold_pc & 0xFFFF))
    return words


DIRECT_GENERIC_MENU_DESCRIPTOR_ADDRESS = 0x530100
DIRECT_GENERIC_MENU_TITLE_ADDRESS = 0x530108


def direct_resource_next_cluster_words() -> list[int]:
    """Return the next cluster in the probe's contiguous resource file.

    The exact resident seek/read routines call the linked sector probe with
    ``(signed byte device, uint16 cluster)``.  The real NAND file's FAT chain
    is unavailable until the outer manager has mounted it, while the menu
    resource islands themselves are already present in the shipped PRG.  A
    contiguous chain is therefore the smallest guest-side reconstruction of
    that missing manager state.
    """
    return [
        0x2E00,                       # LINK #0
        0x780B, 0x0008,               # R0 = cluster
        0x5001,                       # R0++
        0x2F00, RETS,
    ]


def direct_resource_read_callback_words() -> list[int]:
    """Fill one probe sector from the shipped resource source image.

    The original device-table slot ``+4`` is a position initializer: exact
    ``33:091C`` records the requested far position at ``A2:29C8`` and slot
    ``+8`` (exact ``32:6F12``) subsequently streams bytes into the table's
    buffer.  This isolated probe replaces that pair with one bulk operation;
    it must not be described as the factory callback contract.

    Menu offsets are *runtime linked* resident addresses. The direct text
    experiment uses ``1C:A000`` while the exact root hierarchy remains at
    ``1C:9748``. Both are installed at their linked destinations.
    The ``+0x1D`` relation is an offline extraction delta, not a runtime
    address translation: applying it here makes the guest read the updater's
    source bank instead of the installed resident page.

    This callback is DMCU code in the reconstructed resident-manager image;
    it is deliberately not a host/QEMU ROM-service interception.
    """
    file_offset = DIRECT_RESOURCE_FILE_ADDRESS & 0xFFFF
    buffer_segment = DIRECT_RESOURCE_SECTOR_BUFFER_ADDRESS >> 16
    buffer_offset = DIRECT_RESOURCE_SECTOR_BUFFER_ADDRESS & 0xFFFF
    diagnostic_offset = DIRECT_RESOURCE_DIAGNOSTIC_ADDRESS & 0xFFFF
    return [
        0x2E00,                       # LINK #0
        0x58F1, 0x58F2, 0x58F3,
        # Guest-side diagnostic snapshot: callback marker followed by the
        # four incoming stack words.  This proves whether exact 2A:D374 made
        # the indirect device call without changing its result or arguments.
        0x6810, DIRECT_RESOURCE_DIAGNOSTIC_ADDRESS >> 15,
        0xC700,
        0x68F0, 0x6840,
        0xA8F0, diagnostic_offset + 0x00,
        0x780B, 0x0006,
        0xA8F0, diagnostic_offset + 0x02,
        0x780B, 0x0008,
        0xA8F0, diagnostic_offset + 0x04,
        0x780B, 0x000A,
        0xA8F0, diagnostic_offset + 0x06,
        0x780B, 0x000C,
        0xA8F0, diagnostic_offset + 0x08,
        # DS registers select 32-KiB physical banks.  Far pointers retain
        # their compiler-visible 64-KiB segment:offset representation.
        0x6810, DIRECT_RESOURCE_FILE_ADDRESS >> 15,
        0xC700,
        0x88F0, file_offset + 0x28,   # source high / linked segment
        0x88F1, file_offset + 0x2A,   # source low / linked offset
        # Preserve the seek position seen by the callback.  Switch back to
        # the same segment-53 bank before recording it, then reload the FILE
        # words so diagnostics cannot become an input to the copy itself.
        0x6810, DIRECT_RESOURCE_DIAGNOSTIC_ADDRESS >> 15,
        0xC700,
        0xA8F0, diagnostic_offset + 0x0A,
        0xA8F1, diagnostic_offset + 0x0C,
        0x6810, DIRECT_RESOURCE_FILE_ADDRESS >> 15,
        0xC700,
        0x88F0, file_offset + 0x28,
        0x88F1, file_offset + 0x2A,
        0x74F1, 0xFE00,               # align linked runtime sector
        0x68F2, 0x0200,               # memcpy length
        0x58F2,
        0x58F1,                       # source low
        0x58F0,                       # source high
        0x68F3, buffer_offset,
        0x58F3,                       # destination low
        0x68F2, buffer_segment,
        0x58F2,                       # destination high
        0xBD08, 0x43A6,               # exact resident far memcpy
        0x50FA,
        # Snapshot the first four copied sector words.  Source buffer and
        # diagnostic record share the segment-53 data bank.
        0x6810, DIRECT_RESOURCE_SECTOR_BUFFER_ADDRESS >> 15,
        0xC700,
        0x88F0, buffer_offset + 0x00,
        0xA8F0, diagnostic_offset + 0x0E,
        0x88F0, buffer_offset + 0x02,
        0xA8F0, diagnostic_offset + 0x10,
        0x88F0, buffer_offset + 0x04,
        0xA8F0, diagnostic_offset + 0x12,
        0x88F0, buffer_offset + 0x06,
        0xA8F0, diagnostic_offset + 0x14,
        0x4800,                       # success
        0x383F, 0x382F, 0x381F,
        0x2F00, RETS,
    ]


def direct_resource_post_read_words() -> list[int]:
    """Stand in for the original byte-streaming slot during this probe.

    Exact record lookup ``2A:D374`` invokes slot ``+8`` after slot ``+4`` has
    initialized the current position.  The factory slot ``+8`` is the exact
    one-byte reader ``32:6F12``.  The probe's replacement slot ``+4`` already
    copied the complete logical sector, so this paired substitute only reports
    success.  It is an exploration mechanism, not a recovered factory reader.
    """
    return [0x4800, RETS]


def direct_resource_context_words() -> list[int]:
    """Construct the missing manager-owned file/device objects in guest RAM."""
    file_offset = DIRECT_RESOURCE_FILE_ADDRESS & 0xFFFF
    device_offset = DIRECT_RESOURCE_DEVICE_ADDRESS & 0xFFFF
    buffer_offset = DIRECT_RESOURCE_SECTOR_BUFFER_ADDRESS & 0xFFFF
    words = [
        # Device-table slot zero at A2:29C4 -> 51:27A0.  Preserve the table
        # layout but replace the original position initializer (+4), byte
        # reader (+8), buffer (+18), and device object (+22) for this isolated
        # linked-resource probe.  These substitutions are not factory policy.
        0x6810, 0x5127A0 >> 15,
        0xC700,
        0x68F0, DIRECT_RESOURCE_READ_CALLBACK_ADDRESS >> 16,
        0xA8F0, 0x27A4,
        0x68F0, DIRECT_RESOURCE_READ_CALLBACK_ADDRESS & 0xFFFF,
        0xA8F0, 0x27A6,
        0x68F0, DIRECT_RESOURCE_POST_READ_ADDRESS >> 16,
        0xA8F0, 0x27A8,
        0x68F0, DIRECT_RESOURCE_POST_READ_ADDRESS & 0xFFFF,
        0xA8F0, 0x27AA,
        0x68F0, DIRECT_RESOURCE_SECTOR_BUFFER_ADDRESS >> 16,
        0xA8F0, 0x27B8,
        0x68F0, buffer_offset,
        0xA8F0, 0x27BA,
        0x68F0, DIRECT_RESOURCE_DEVICE_ADDRESS >> 16,
        0xA8F0, 0x27C2,
        0x68F0, device_offset,
        0xA8F0, 0x27C4,
        # Minimal device geometry used by exact 31:B1FA and 30:6E9E:
        # 255 sectors/cluster, first data sector one, valid clusters 2..FFFF.
        0x6810, DIRECT_RESOURCE_DEVICE_ADDRESS >> 15,
        0xC700,
        0x69F1, 0x00FF,
        0xA9F1, device_offset + 0x02,
        0x68F0, DIRECT_RESOURCE_DEVICE_ADDRESS >> 16,
        0xA8F0, device_offset + 0x06,
        0x68F0, device_offset,
        0xA8F0, device_offset + 0x08,
        0x4801,
        0xA8F0, device_offset + 0x12,
        0x68F0, 0xFFFF,
        0xA8F0, device_offset + 0x14,
        0xA8F0, device_offset + 0x16,
        # File type one, contiguous starting cluster two, a 4-MiB logical
        # extent, and no optional cluster-checkpoint buffer.
        0x69F1, 0x0001,
        0xA9F1, file_offset + 0x15,
        0x4802,
        0xA8F0, file_offset + 0x22,
        0xA8F0, file_offset + 0x24,
        0xA8F0, file_offset + 0x26,
        0x4800,
        0xA8F0, file_offset + 0x28,
        0xA8F0, file_offset + 0x2A,
        0x68F0, 0x0040,
        0xA8F0, file_offset + 0x2C,
        0x4800,
        0xA8F0, file_offset + 0x2E,
        0xA8F0, file_offset + 0x42,
        0xA8F0, file_offset + 0x44,
        0xA8F0, file_offset + 0x46,
        # Publish the manager-owned FILE pointer consumed by 2C:C9E8 and
        # copied into the modal renderer context at A4:452E/4530.
        0x6810, 0x00A0,
        0xC700,
        0x68F0, DIRECT_RESOURCE_FILE_ADDRESS >> 16,
        0xA8F0, 0x7DEE,
        0x68F0, file_offset,
        0xA8F0, 0x7DF0,
    ]
    return words


def direct_generic_menu_probe_words() -> list[int]:
    """Enter the recovered resident menu with a guest-side resource context.

    ``2C:C9E8`` needs an application record whose unaligned word at +4
    selects the menu page and whose byte at +6 supplies persisted-page flags.
    Its renderer additionally consumes the manager-owned FILE pointer at
    A0:7DEE; bypassing that normal launch step makes exact ``1B:C5EC`` return
    FFF6 before any resource bytes can be read.
    The resident table builder ``2A:322A`` selects its segment-53 fast path
    when A0:70BA/70BC equals A0:7CB2/7CB4; both values are offsets relative to
    the hard-coded 53:0000 arena, not absolute far pointers. For this bounded
    render experiment page zero is a guest-ROM CR/LF stream containing the
    five labels recovered from the exact 1C:9748 hierarchy/catalogue pair.

    This is an isolated guest-side manager experiment.  It executes the exact
    vendor menu entry, table builder, renderer, and event loop; no QEMU ROM
    service or filesystem resource is substituted.
    """
    words = [
        # Restore application/menu destinations retired by the bootstrap
        # foreground, then materialize the compact resident page index.
        0xBD00 | (APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16),
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF,
        0xBD25, 0x5858,
        0xBD30, 0x8C1C,
        0xBD00 | (MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS >> 16),
        MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS & 0xFFFF,
        0xBD00 | (MENU_POINTER_INDEX_INSTALLER_ADDRESS >> 16),
        MENU_POINTER_INDEX_INSTALLER_ADDRESS & 0xFFFF,
        # Restore the exact default UI/font state normally selected by the
        # missing resident manager before it enters an application.  Natural
        # startup proves 32:FE0A passes command F0 to exact 2F:5B98, which in
        # turn selects command-table entries 2 and 0x0C through
        # 31:5BB8/31:5A44.  This publishes the 00:ED90, 24-byte font tuple at
        # A2:2914..2919.  Call the evidenced dispatcher directly: the parent
        # wrapper's later 33:305E hardware-mode child waits on foreground-only
        # state and prevents this manager probe from reaching the menu.
        0x68F0, 0x00F0,
        0x58F0,
        0xBD2F, 0x5B98,
        0x50F2,
        # Restore the factory-default text colours before the first glyph.
        # Every recovered application-mode setup which selects the ordinary
        # light-on-dark UI pushes background index 0 followed by foreground
        # index 15, then calls exact 30:D6D0.  That routine resolves both
        # indices through the resident A1:3857 palette and publishes the
        # pixel masks at unbanked 4BA8/4BAE.  The missing outer manager would
        # normally own this state; without it both masks remain zero and the
        # exact font blitter correctly commits only zero words.
        0x4800,
        0x58F0,
        0x480F,
        0x58F0,
        0xBD30, 0xD6D0,
        0x50F4,
        # Recreate the resource FILE/device state normally owned by the
        # missing resident outer manager.
        *direct_resource_context_words(),
        # Consume the Return event which ended the bootstrap foreground.
        0xBD06, 0x6A02,
        0xBD30, 0xD350,
        0xBD2F, 0xC216,
        0x4800,
        0x6810, 0x00A2,
        0xC700,
        # Exact application initializer 22:9738 establishes this event/timer
        # baseline before any foreground dispatcher is allowed to poll.  The
        # direct-menu probe intentionally bypasses that large application
        # initializer, so reproduce only its ordinary A2-global stores here.
        # With 2AA4 left at the updater's reset value zero, exact 2F:FA32 takes
        # its maintenance path on the first poll and returns one; resident
        # 1E:F734 then turns that into synthetic event 0x008F.
        0xA8F0, 0x2A6C,
        0xA8F0, 0x2A76,
        0xA8F0, 0x2A88,
        0xA8F0, 0x2A90,
        0xA8F0, 0x2A92,
        0xA8F0, 0x2AA6,
        # The bootstrap foreground leaves the application-exit state set.
        # Exact 32:7050 returns A2:2ABA before consulting the input flags, so
        # carrying value one into 18:9A58 makes the newly rendered menu exit
        # on its first poll.  Normal application transitions clear this word
        # at 2B:7854 and 32:F2AA.  Reproduce that manager-owned lifecycle
        # boundary here so the vendor event loop remains live.
        0xA8F0, 0x2ABA,
        0x68F0, 0x00FF,
        0xA8F0, 0x2AA4,
        # Keep the known-good framebuffer at 50:3840.  A runtime mode-one
        # experiment correctly published 50:0000 but then cleared both pages
        # without increasing the native text-blit count; the remaining fault
        # is upstream in the menu resource/render contract, not page choice.
        0x4800,
        0x58F0,
        0xBD31, 0xB014,
        0x50F2,
        # Create a zeroed application record at 53:0100.  Its page word (+4)
        # and flags byte (+6) therefore select resident root page zero.
        0x4800,
        0x6810, DIRECT_GENERIC_MENU_DESCRIPTOR_ADDRESS >> 15,
        0xC700,
        0xA8F0, DIRECT_GENERIC_MENU_DESCRIPTOR_ADDRESS & 0xFFFF,
        0xA8F0, (DIRECT_GENERIC_MENU_DESCRIPTOR_ADDRESS + 2) & 0xFFFF,
        0xA8F0, (DIRECT_GENERIC_MENU_DESCRIPTOR_ADDRESS + 4) & 0xFFFF,
        0xA8F0, (DIRECT_GENERIC_MENU_DESCRIPTOR_ADDRESS + 6) & 0xFFFF,
        0xA8F0, DIRECT_GENERIC_MENU_TITLE_ADDRESS & 0xFFFF,
        # Select the segment-53 resident table path.  These globals contain a
        # relative offset; zero plus the builder's hard-coded 53:0000 base is
        # the index installed above.
        0x6810, 0x00A0,
        0xC700,
        0xA8F0, 0x70BA,
        0xA8F0, 0x70BC,
        0xA8F0, 0x7CB2,
        0xA8F0, 0x7CB4,
        # Supply a valid empty source string for the menu entry's final
        # 32:945C copy instead of publishing the lirt.nwf development path.
        0x68F0, DIRECT_GENERIC_MENU_TITLE_ADDRESS >> 16,
        0x68F1, DIRECT_GENERIC_MENU_TITLE_ADDRESS & 0xFFFF,
        0xA8F0, 0x7090,
        0xA8F1, 0x7092,
        # Force descriptor flags to be initialized on first entry.
        0x69F1, 0x00FF,
        0xA9F1, 0x70C2,
        0xA9F1, 0x70C3,
        # Direct far-pointer argument to exact vendor entry 2C:C9E8.
        0x68F1, DIRECT_GENERIC_MENU_DESCRIPTOR_ADDRESS & 0xFFFF,
        0x68F0, DIRECT_GENERIC_MENU_DESCRIPTOR_ADDRESS >> 16,
        0x58F1,
        0x58F0,
        0xBD2C, 0xC9E8,
        0x50F4,
    ]
    hold_pc = DIRECT_GENERIC_MENU_PROBE_ADDRESS + len(words) * 2
    words.extend((
        0xAD00 | (DIRECT_GENERIC_MENU_PROBE_ADDRESS >> 16),
        hold_pc & 0xFFFF,
    ))
    return words


def fixed_launch_wrapper_installer_words() -> list[int]:
    """Install the exact operation-0x0B caller and table-creation entry."""
    return [
        *embed_program_overlay_words(
            RESIDENT_FIXED_LAUNCH_WRAPPER_DESTINATION,
            RESIDENT_FIXED_LAUNCH_WRAPPER_SOURCE,
            RESIDENT_FIXED_LAUNCH_WRAPPER_SIZE,
        ),
        *copy_code_to_overlay_words(
            RESIDENT_WORK_TABLE_CREATE_OVERLAY_DESTINATION,
            RESIDENT_WORK_TABLE_CREATE_OVERLAY_SOURCE,
            RESIDENT_WORK_TABLE_CREATE_OVERLAY_SIZE,
        ),
        0x6810, 0x0000,
        0x6811, 0x0001,
        RETS,
    ]


def rom06_key_release_words() -> list[int]:
    """Implement only the caller-proven 06:6A02 normal-return contract."""
    return [RETS]


def rom06_key_read_words() -> list[int]:
    """Block for a matrix key and return its firmware event code in R0."""
    return [
        0xBD2E, 0x5F28,              # raw 0..63 matrix index or 00FF
        0x58F0,                       # mapper(u16 raw_index)
        0xBD28, 0xF4A4,              # exact mode/event-table mapper
        0x50F2,
        0x5600,                       # ignore unmapped/no-key results
        0xAC01, ROM06_KEY_READ_ADDRESS & 0xFFFF,
        RETS,
    ]


def initializer_probe_words() -> list[int]:
    """Install the required copy helper and enter the nine-copy chain.

    This diagnostic path deliberately stops when the unmodified chain jumps
    to the still-unknown resident continuation at 03:026A.  Sentinel source
    bytes make the recovered copy ABI testable without guessing factory ROM
    contents.  Run-time overlays are intentionally deferred: this strict
    probe never reaches the point at which the second initializer has made
    their source bytes safe to consume.  In particular, 33:71CE remains the
    original PRG source here; the inferred NAND geometry is installed only
    after the second chain has consumed that range.
    """
    return [
        *install_copy_overlay_words(),
        0xBD20, 0x0030,               # clear data windows as real startup does
        0xAD24, 0x7FE4,               # vendor nine-descriptor initializer
    ]


def factory_constant_initializer_words() -> list[int]:
    """Return the exact linked 07:* chain with one explicit loader handoff.

    Source 24:7FE4 is an exact nine-descriptor straight-line initializer and
    ends with ``SJMP 03:026A``.  The original resident late-overlay loader is
    absent from the update package.  Factory-linked mode therefore changes
    only that final far jump to the clean-room loader; the loader subsequently
    tail-jumps to the exact linked 03:026A system main.
    """
    words = program_source_words(
        FACTORY_CONSTANT_INITIALIZER_SOURCE,
        FACTORY_CONSTANT_INITIALIZER_SIZE,
    )
    if words[-2:] != [0xAD03, 0x026A]:
        raise ValueError("factory constant initializer terminal jump changed")
    words[-2:] = [
        0xAD00 | (POST_INITIALIZER_LOADER_ADDRESS >> 16),
        POST_INITIALIZER_LOADER_ADDRESS & 0xFFFF,
    ]
    return words


def factory_system_main_words(
    direct_manager_handoff: bool = False,
) -> list[int]:
    """Return the linked system main, optionally ending at the menu manager.

    The direct-menu experiment still needs the shipped system-main prefix:
    it initializes the LCD, framebuffer services, input state, font state and
    resident application loader before the first application is selected.
    Running the unmodified final call would start the hard-coded state-0x50
    foreground and require a synthetic Return key before 03:0080 could run.

    In direct-manager mode retain the exact function through the 01:0200
    loader call, replace only the final foreground call/return sequence with
    its balanced epilogue, and tail-jump to the guest manager.  This remains
    ordinary DMCU code and does not introduce a QEMU ROM service.
    """
    words = program_source_words(
        FACTORY_SYSTEM_MAIN_SOURCE,
        FACTORY_SYSTEM_MAIN_SIZE,
    )
    if not direct_manager_handoff:
        return words

    terminal_index = (
        0x031C - (FACTORY_SYSTEM_MAIN_DESTINATION & 0xFFFF)
    ) // 2
    expected = [0xBD2D, 0x7DD2, 0x4800, 0x381F, 0x2F00, RETS]
    if words[terminal_index:terminal_index + len(expected)] != expected:
        raise ValueError("factory system-main terminal sequence changed")
    words[terminal_index:terminal_index + len(expected)] = [
        0x4800,                       # normal result
        0x381F,                       # restore saved R1
        0x2F00,                       # restore caller FP
        0xAD03,
        NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF,
        RESERVED,
    ]
    return words


def initializer_overlay_probe_words(
    factory_linked_startup: bool = False,
) -> list[int]:
    """Prepare the recovered factory initializer path in ordinary guest code.

    Historical overlay probes enter source 24:7FE4 directly and retain their
    old experiment ordering for reproducibility.  Factory-linked mode instead
    returns from resident 03:0030 to the unmodified reset vector at 20:0004.
    The exact QEMU code aliases then execute 33:4F50 -> 33:603C and the latter
    starts the linked 11:4560 -> 07:7FE4 -> 03:026A chain.
    """
    words = [
        *install_copy_overlay_words(),
        0xBD20, 0x0030,
    ]
    if factory_linked_startup:
        words.append(RETS)
    else:
        words.extend((0xAD24, 0x7FE4))
    return words


def resident_application_state_guard_words() -> list[int]:
    """Gate the run-time dispatcher until its application state is initialized.

    The updater clears A2:2AA4 at 20:0166.  The recovered application
    initializer at 22:9738 changes it to 0x00FF before enabling the main loop,
    and every later configuration path leaves it non-zero.  Early graphics
    setup nevertheless calls the resident delay/poll service.  Returning no
    application event dispatch while the sentinel remains zero models the
    missing resident-layer initialization gate.  The exact 46:3DD2 helper is
    called with the same four-word far-pointer argument block assembled by
    3B:FD18..FD34, so timer expiry and low-level events still reach the
    caller's two output variables.  After
    initialization, tear down that frame and tail-call the exact shipped
    dispatcher copy at 3B:F734 without changing its caller's far-return frame.
    """
    return [
        0x2E05,                       # LINK #5: match 3B:F734 frame
        0x58F1,                       # save R1
        0x58F3,                       # save R3
        0x6810, 0x00A2,               # DS0 = application globals
        0x88F0, 0x2AA4,               # R0 = tick threshold / init sentinel
        0x5600,                       # CMP R0, #0
        0xAC02, 0xF76E,               # non-zero: use full dispatcher
        0x780B, 0x000A,               # second output far-pointer offset
        0x781B, 0x000C,
        0x58F1,
        0x58F0,
        0x780B, 0x0006,               # first output far-pointer offset
        0x781B, 0x0008,
        0x58F1,
        0x58F0,
        0xBD46, 0x3DD2,               # exact low-level/timer event helper
        0x50F8,                       # discard four forwarded arguments
        0x383F,                       # restore R3
        0x381F,                       # restore R1
        0x2F00,                       # UNLINK
        RETS,
        0x383F,                       # initialized: restore R3
        0x381F,                       # restore R1
        0x2F00,                       # UNLINK
        0xAD3B, 0xF734,               # tail-call exact PRG dispatcher
    ]


def post_initializer_overlay_words(
    probe_rom_08_return: bool = False,
    probe_continue_event_loop: bool = False,
    probe_lcd_power_on: bool = False,
    probe_stop_after_overlay_install: bool = False,
    probe_app_init_callback: bool = False,
    probe_system_main: bool = False,
    probe_storage_global_templates: bool = False,
    probe_fixed_launch_wrapper: bool = False,
    factory_linked_startup: bool = False,
    probe_direct_generic_menu: bool = False,
    probe_factory_default_catalogue: bool = False,
) -> list[int]:
    """Install run-time overlays after both vendor data-copy chains.

    Historical paths create a real SCALL frame for source 20:026A.  In
    factory-linked mode the exact system main is already resident at linked
    execution address 03:026A.  The shipped initializer reaches this
    clean-room loader through non-local jumps, so the loader must create the
    missing resident-manager call frame itself.  After that first lifecycle
    returns, it hands control to the inferred 03:0080 manager scheduler.
    In historical system-main mode the source-position function
    function reaches 2D:7DD2 and returns after one application lifecycle (for
    example, after consuming a key).  In system-main mode the reconstructed
    outer frame then enters the exact firmware continuation at 20:0004.  This
    explicit frame is required because the vendor initializer chain reaches
    this loader through non-local jumps and no longer has an ordinary SCALL
    epilogue.  Other probe paths retain their explicit completion trap or
    exploratory continuation.
    """
    if probe_continue_event_loop and not probe_rom_08_return:
        raise ValueError(
            "event-loop continuation requires 08:427E return probe"
        )
    if probe_lcd_power_on and not probe_continue_event_loop:
        raise ValueError("LCD power-on probe requires event-loop continuation")
    if probe_stop_after_overlay_install and (
            probe_continue_event_loop or probe_lcd_power_on or
            probe_app_init_callback or probe_system_main):
        raise ValueError(
            "overlay-install stop is incompatible with continuation probes"
        )
    if probe_system_main and (
            probe_continue_event_loop or probe_lcd_power_on or
            probe_app_init_callback):
        raise ValueError(
            "system-main probe is incompatible with synthetic continuations"
        )
    if factory_linked_startup and not probe_system_main:
        raise ValueError("factory-linked startup requires system-main mode")
    words: list[int] = []
    if probe_storage_global_templates or probe_fixed_launch_wrapper:
        words.extend((
            0xBD00 | (STORAGE_GLOBAL_TEMPLATE_PROBE_ADDRESS >> 16),
            STORAGE_GLOBAL_TEMPLATE_PROBE_ADDRESS & 0xFFFF,
        ))
    # 33:71CE is also a source range in the second vendor initializer.  Do not
    # replace it with inferred run-time NAND geometry until both copy chains
    # have returned through this 07:7FE4 continuation.
    words.extend(install_initializer_data_overlay_words())
    words.extend(install_runtime_overlay_words())
    if probe_stop_after_overlay_install:
        words.append(RESERVED)
        return words
    if probe_fixed_launch_wrapper:
        # The exact 1B:23B8 preparation allocates four 0x100-byte work tables
        # through linked 31:4974.  The flat target is a mid-function extension
        # word; its complete same-PC source is 4E:4974.  Install the late
        # application dependency closure first.  The missing resident manager
        # must also establish the storage registry before operation 0x0B:
        # exact 25:5858 publishes A2:29C4/29C6 = 51:27A0 and initializes the
        # four 0x26-byte unit records consumed by 2A:D374.  Then initialize the
        # allocator, exchange the segment-33 wrapper window, and call shipped
        # 33:3CA6.  Foreground code later occupies that window, so the probe
        # reinstalls it before independently exercising adjacent 33:3CC6.
        # Their adjacency alone does not establish a factory call sequence.
        words.extend((
            0xBD00 | (APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16),
            APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF,
            0xBD25, 0x5858,
            0xBD30, 0x8C1C,
            0xBD00 | (RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS >> 16),
            RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS & 0xFFFF,
            0xBD33, 0x3CA6,
        ))
    if factory_linked_startup:
        if (probe_direct_generic_menu or
                probe_factory_default_catalogue):
            # Run the shipped system-main prefix.  Its direct-manager variant retains
            # all hardware/UI initialization and the resident loader but
            # replaces the state-0x50 foreground call with a balanced jump to
            # 03:0080.  ROM 01:0200 now initializes storage after BSS clear;
            # no key event is fabricated at this boundary.
            words.extend((
                0x68F0, 0x0200,
                0x6810, 0x00A2,
                0xC700,
                0xA8F0, 0x28E0,
                0xAD03,
                FACTORY_SYSTEM_MAIN_DESTINATION & 0xFFFF,
            ))
            return words
        # The exact 24:80AA jump has been redirected here solely to insert the
        # recovered late-overlay closure.  The original terminal jump assumed
        # a non-returning resident main, but the reconstructed foreground
        # completes one lifecycle.  Give it an ordinary far-call frame; a
        # bare SJMP makes its RETS consume an older initializer frame and
        # lowers SP by 0x46 on every repetition.  Storage is initialized by
        # exact calls in ROM 01:0200 after the BSS
        # clear, for both this first lifecycle and scheduler-owned repeats.
        words.extend((
            # Publish the exact foreground resource byte window before the
            # first linked 31:A914 initializer, matching scheduler repeats.
            0x68F0, 0x0200,
            0x6810, 0x00A2,
            0xC700,
            0xA8F0, 0x28E0,
            0xBD03, 0x026A,
            0xAD03, NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF,
        ))
        return words
    words.extend((0xBD20, 0x026A))
    if probe_app_init_callback:
        # 20:026A performs a late guest overlay phase and overwrites these
        # application targets.  Reinstall the recovered same-PC modules here,
        # exactly where the missing ROM overlay loader would have done so,
        # before entering the real application chain.
        words.extend(install_application_main_chain_words())
    if probe_app_init_callback:
        # Exploration only.  Invoke the installed target rather than its PRG
        # source copy now that the original caller chain is known.
        words.extend((0xBD22, 0x9738))
    if probe_system_main:
        # 20:026A -> 2D:7DD2 is directly observed, and the latter legitimately
        # returns after completing an application lifecycle.  Continue through
        # the same caller-constrained outer-frame handoff used by the reset
        # reconstruction.  It enters exact 20:0004 -> 33:4F50 and supplies the
        # return frame that this mid-function reset continuation requires.
        words.extend((0xAD03, POST_INITIALIZER_HANDOFF_PC))
    if probe_lcd_power_on:
        # Exploration only: invoke the exact recovered segment-14 ST7529
        # power/init wrapper after 20:026A has drawn its native startup
        # frames. The call site in the missing boot ROM is not yet known.
        words.extend((0xBD14, 0x65CE))
    if probe_continue_event_loop:
        words.extend((0xAD03, POST_INITIALIZER_HANDOFF_PC))
    elif not probe_system_main:
        words.append(RESERVED)
    return words


def make_routines(
    startup_context: int = 0,
    probe_font_lookup: bool = False,
    initializer_probe: bool = False,
    initializer_overlay_probe: bool = False,
    dual_initializer_probe: bool = False,
    probe_rom_08_return: bool = False,
    probe_rom_03_rand_zero: bool = False,
    probe_continue_event_loop: bool = False,
    probe_dispatch_activation: bool = False,
    probe_lcd_power_on: bool = False,
    probe_stop_after_overlay_install: bool = False,
    probe_app_init_callback: bool = False,
    probe_system_main: bool = False,
    probe_rom_01_return: bool = False,
    probe_resident_app_state_guard: bool = False,
    preserve_metadata_block_probe: bool = False,
    probe_storage_global_templates: bool = False,
    probe_rom_02_c588_return: bool = False,
    probe_stop_after_scheduler_return: bool = False,
    probe_rom_0b_ccd2_zero: bool = False,
    probe_stop_before_scheduler_entry: bool = False,
    probe_fixed_launch_wrapper: bool = False,
    probe_generic_main_menu: bool = False,
    probe_direct_generic_menu: bool = False,
    probe_factory_default_catalogue: bool = False,
    factory_linked_startup: bool = False,
    reconstruct_resident_root_desktop: bool = False,
) -> dict[int, tuple[str, list[int]]]:
    if sum((initializer_probe, initializer_overlay_probe,
            dual_initializer_probe)) > 1:
        raise ValueError("initializer probe modes are mutually exclusive")
    if factory_linked_startup and not (
            initializer_overlay_probe and probe_system_main):
        raise ValueError(
            "factory-linked startup requires initializer-overlay and "
            "system-main modes"
        )
    if reconstruct_resident_root_desktop and not (
            factory_linked_startup and probe_system_main):
        raise ValueError(
            "resident root-desktop reconstruction requires factory-linked "
            "system-main mode"
        )
    if probe_rom_08_return and not initializer_overlay_probe:
        raise ValueError(
            "08:427E return probe requires initializer-overlay probe mode"
        )
    if probe_rom_01_return and not (
            initializer_overlay_probe and probe_rom_08_return):
        raise ValueError(
            "01:0200 return probe requires initializer-overlay and "
            "08:427E return probe modes"
        )
    if probe_rom_03_rand_zero and not (
            initializer_overlay_probe and probe_rom_08_return):
        raise ValueError(
            "03:4124 zero probe requires initializer-overlay and 08:427E "
            "return probe modes"
        )
    if probe_continue_event_loop and not (
            initializer_overlay_probe and probe_rom_08_return and
            probe_rom_03_rand_zero):
        raise ValueError(
            "event-loop continuation requires initializer-overlay, "
            "08:427E return, and 03:4124 random probes"
        )
    if (probe_dispatch_activation and
            not (probe_continue_event_loop or probe_system_main)):
        raise ValueError(
            "activation dispatch requires event-loop continuation or "
            "system-main probe"
        )
    if probe_lcd_power_on and not probe_continue_event_loop:
        raise ValueError("LCD power-on probe requires event-loop continuation")
    if probe_stop_after_overlay_install and not initializer_overlay_probe:
        raise ValueError(
            "overlay-install stop requires initializer-overlay probe mode"
        )
    if probe_app_init_callback and not initializer_overlay_probe:
        raise ValueError(
            "application-init callback requires initializer-overlay probe mode"
        )
    if probe_system_main and not initializer_overlay_probe:
        raise ValueError(
            "system-main probe requires initializer-overlay probe mode"
        )
    if probe_system_main and not probe_rom_01_return:
        raise ValueError(
            "system main requires reconstructed 01:0200 loader"
        )
    if probe_resident_app_state_guard and not probe_system_main:
        raise ValueError(
            "resident application-state guard requires system-main probe mode"
        )
    if probe_storage_global_templates and not probe_system_main:
        raise ValueError(
            "storage-global template probe requires system-main probe mode"
        )
    if probe_stop_after_scheduler_return and not probe_system_main:
        raise ValueError(
            "scheduler-return stop requires system-main probe mode"
        )
    if probe_stop_before_scheduler_entry and not probe_system_main:
        raise ValueError(
            "scheduler-entry stop requires system-main probe mode"
        )
    if (probe_stop_before_scheduler_entry and
            probe_stop_after_scheduler_return):
        raise ValueError(
            "scheduler-entry and scheduler-return stops are mutually exclusive"
        )
    if probe_fixed_launch_wrapper and not probe_system_main:
        raise ValueError(
            "fixed-launch wrapper probe requires system-main probe mode"
        )
    if (probe_fixed_launch_wrapper and
            (probe_stop_before_scheduler_entry or
             probe_stop_after_scheduler_return or
             probe_generic_main_menu or probe_direct_generic_menu or
             probe_factory_default_catalogue)):
        raise ValueError(
            "fixed-launch wrapper and alternate scheduler probes are mutually exclusive"
        )
    if probe_generic_main_menu and not probe_system_main:
        raise ValueError(
            "legacy adjacent-wrapper probe requires system-main probe mode"
        )
    if (probe_generic_main_menu and
            (probe_stop_before_scheduler_entry or
             probe_stop_after_scheduler_return or
             probe_direct_generic_menu or
             probe_factory_default_catalogue)):
        raise ValueError(
            "adjacent-wrapper and scheduler-stop probes are mutually exclusive"
        )
    if probe_direct_generic_menu and not probe_system_main:
        raise ValueError(
            "direct generic-menu probe requires system-main probe mode"
        )
    if (probe_direct_generic_menu and
            (probe_stop_before_scheduler_entry or
             probe_stop_after_scheduler_return or
             probe_factory_default_catalogue)):
        raise ValueError(
            "direct generic-menu and scheduler-stop probes are mutually exclusive"
        )
    if probe_factory_default_catalogue and not probe_system_main:
        raise ValueError(
            "factory-default catalogue probe requires system-main probe mode"
        )
    if (probe_factory_default_catalogue and
            not factory_linked_startup):
        raise ValueError(
            "factory-default catalogue probe requires factory-linked startup"
        )
    if (probe_factory_default_catalogue and
            (probe_stop_before_scheduler_entry or
             probe_stop_after_scheduler_return)):
        raise ValueError(
            "factory-default catalogue and scheduler-stop probes are "
            "mutually exclusive"
        )
    routines = {
        ROM00_DYNAMIC_MODULE_ADDRESS: (
            "resident_rom00_dynamic_module",
            program_source_words(
                ROM00_DYNAMIC_MODULE_SOURCE,
                ROM00_DYNAMIC_MODULE_SIZE,
            ),
        ),
        ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_ADDRESS: (
            "resident_rom00_dynamic_absolute_epilogue",
            program_source_words(
                ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_SOURCE,
                ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_SIZE,
            ),
        ),
        ROM00_CRITICAL_RETURN_ADDRESS: (
            "resident_rom00_critical_return",
            list(ROM00_CRITICAL_RETURN_WORDS),
        ),
        0x02B9E2: ("nand_gpio_setup_placeholder", [RETS]),
        0x02BAC4: ("nand_select_placeholder", [RETS]),
        0x02BAC8: ("nand_deselect_placeholder", [RETS]),
        0x02BB1E: ("nand_read_id", read_id_words()),
        0x02BBF6: ("nand_read_page", read_page_words()),
        0x02BCC6: ("nand_program_page", program_page_words()),
        0x02BDD6: (
            "nand_erase_block_preserve_block_one_probe"
            if preserve_metadata_block_probe else "nand_erase_block",
            erase_block_words(preserve_metadata_block_probe),
        ),
        0x02BE5C: ("nand_copy_back", copy_page_words()),
        0x02BF56: ("nand_copy_back_ec76", copy_page_words()),
        0x02C04C: ("nand_completion_status", nand_completion_words()),
        RESIDENT_DES_TRANSFORM_ADDRESS: (
            "resident_clean_room_des_transform",
            des_transform_words(),
        ),
        ROM02_C588_ADDRESS: (
            "resident_diagnostic_marker_return",
            [RETS],
        ),
        0x030030: ("cold_boot_entry", [0xAD03, 0x0100]),
        0x030080: (
            ("probe_exact_factory_default_catalogue"
             if probe_factory_default_catalogue else
             "probe_direct_recovered_generic_menu_entry"
             if probe_direct_generic_menu else
             "probe_rejected_adjacent_resource_wrappers"
             if probe_generic_main_menu else
             "probe_resident_fixed_launch_wrapper"
             if probe_fixed_launch_wrapper else
             "inferred_native_application_scheduler_entry_stop"
             if probe_stop_before_scheduler_entry else
             "inferred_native_application_scheduler_return_stop"
             if probe_stop_after_scheduler_return
             else "inferred_native_application_scheduler")
            if probe_system_main else "resident_event_loop",
            factory_default_catalogue_probe_words()
            if probe_factory_default_catalogue else
            [0xAD00 | (DIRECT_GENERIC_MENU_PROBE_ADDRESS >> 16),
             DIRECT_GENERIC_MENU_PROBE_ADDRESS & 0xFFFF]
            if probe_direct_generic_menu else
            generic_main_menu_probe_words()
            if probe_generic_main_menu else
            fixed_launch_wrapper_probe_words()
            if probe_fixed_launch_wrapper else
            [0xAD03, NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF]
            if probe_stop_before_scheduler_entry else
            native_application_scheduler_words(
                probe_stop_after_scheduler_return,
                factory_linked_startup,
            )
            if probe_system_main else resident_event_loop_words(
                startup_context,
                0x008E if probe_dispatch_activation else None,
            ),
        ),
        0x030100: (
            "initializer_probe_body"
            if (initializer_probe or initializer_overlay_probe
                or dual_initializer_probe)
            else "cold_boot_body",
            initializer_overlay_probe_words(factory_linked_startup)
            if initializer_overlay_probe or dual_initializer_probe
            else initializer_probe_words()
            if initializer_probe
            else cold_boot_words(startup_context),
        ),
        CLEAR_OVERLAY_ADDRESS: (
            "overlay_clear_buffer", clear_buffer_words()
        ),
        MENU_CATALOG_EARLY_INSTALLER_ADDRESS: (
            "resident_menu_catalog_early_installer",
            menu_catalog_early_installer_words(),
        ),
        RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS: (
            "resident_fixed_launch_wrapper_installer",
            fixed_launch_wrapper_installer_words(),
        ),
        MENU_RESULT_TABLE_INSTALLER_ADDRESS: (
            "resident_menu_result_table_installer",
            menu_result_table_installer_words(),
        ),
        MENU_EVENT_DEPENDENCY_INSTALLER_ADDRESS: (
            "resident_menu_event_dependency_installer",
            menu_event_dependency_installer_words(),
        ),
        MENU_EVENT_STATE_INSTALLER_ADDRESS: (
            "resident_menu_event_state_installer",
            menu_event_state_installer_words(),
        ),
        MENU_ARITHMETIC_WRAPPER_INSTALLER_ADDRESS: (
            "resident_menu_arithmetic_wrapper_installer",
            menu_arithmetic_wrapper_installer_words(),
        ),
        MENU_SERVICE_INIT_INSTALLER_ADDRESS: (
            "resident_menu_service_init_installer",
            menu_service_init_installer_words(),
        ),
        MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS: (
            "resident_menu_decimal_parse_engine_installer",
            menu_decimal_parse_engine_installer_words(),
        ),
        MENU_POINTER_INDEX_INSTALLER_ADDRESS: (
            "resident_menu_pointer_index_installer",
            generic_main_menu_pointer_index_installer_words(
                direct_text_stream=probe_direct_generic_menu,
            ),
        ),
        MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS: (
            "menu_runtime_overlay_installer",
            menu_runtime_overlay_installer_words(),
        ),
        APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS: (
            "application_cursor_refresh_installer",
            application_cursor_refresh_installer_words(),
        ),
        APPLICATION_MENU_TEXT_STREAM_INSTALLER_ADDRESS: (
            "application_menu_text_stream_installer",
            application_menu_text_stream_installer_words(),
        ),
        APPLICATION_MODAL_MEDIA_BROWSER_INSTALLER_ADDRESS: (
            "resident_modal_media_browser_installer",
            modal_media_browser_installer_words(),
        ),
        APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS: (
            "resident_operation_modal_source_repair_installer",
            operation_modal_source_repair_installer_words(),
        ),
        APPLICATION_MAIN_CURSOR_REFRESH_WRAPPER_ADDRESS: (
            "application_main_cursor_refresh_wrapper",
            application_main_cursor_refresh_wrapper_words(),
        ),
        APPLICATION_MAIN_SINGLE_CYCLE_RETURN_ADDRESS: (
            "application_main_single_cycle_return",
            [0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, RETS],
        ),
        STORAGE_RECORD_CAPACITY_INSTALLER_ADDRESS: (
            "storage_record_capacity_overlay_installer",
            storage_record_capacity_installer_words(),
        ),
        STORAGE_UNIT_OPEN_CAPACITY_WRAPPER_ADDRESS: (
            "storage_unit_open_capacity_wrapper",
            storage_unit_open_capacity_wrapper_words(),
        ),
        MENU_ROOT_DESCRIPTOR_PUBLISH_ADDRESS: (
            "resident_menu_root_descriptor_publish",
            generic_main_menu_root_publish_words(),
        ),
        SYSTEM_BITS_RESIDENT_ADDRESS: (
            "resident_exact_system_bits_50_5906",
            list(SYSTEM_BITS_OVERLAY_WORDS),
        ),
        NAND_PACK_SPARE_ADDRESS: (
            "nand_pack_logical_spare", pack_logical_spare_words()
        ),
        NAND_PREPARE_READ_ADDRESS: (
            "nand_prepare_logical_read", prepare_logical_read_words()
        ),
        NAND_UNPACK_SPARE_ADDRESS: (
            "nand_unpack_logical_spare", unpack_logical_spare_words()
        ),
        NAND_UNPACK_FULL_ADDRESS: (
            "nand_unpack_full_logical_page", unpack_full_logical_page_words()
        ),
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS: (
            "application_region_extra_overlay_installer",
            application_region_extra_installer_words(),
        ),
        APPLICATION_FILE_DRIVER_CALLBACK_INSTALLER_ADDRESS: (
            "application_file_driver_callback_installer",
            file_driver_callback_installer_words(),
        ),
        APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_DESTINATION: (
            "resident_application_file_driver_callback_child",
            file_driver_callback_child_words(),
        ),
        APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_DESTINATION: (
            "resident_application_file_driver_callback_wrapper",
            file_driver_callback_wrapper_words(),
        ),
        WIDE_ACCUMULATE_INSTALLER_ADDRESS: (
            "wide_accumulate_overlay_installer",
            wide_accumulate_installer_words(),
        ),
        APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS: (
            "application_foreground_state_handler_overlay_installer",
            application_foreground_state_handler_installer_words(),
        ),
        APPLICATION_ROOT_STREAM_INSTALLER_ADDRESS: (
            "application_root_stream_overlay_installer",
            application_root_stream_installer_words(),
        ),
        APPLICATION_FACTORY_DEFAULT_INSTALLER_ADDRESS: (
            "application_factory_default_overlay_installer",
            application_factory_default_installer_words(),
        ),
        STORAGE_DRIVER_RETIRE_ADDRESS: (
            "resident_storage_driver_overlay_retire",
            storage_driver_retire_words(),
        ),
        STORAGE_DRIVER_RETIRE_PAYLOAD_ADDRESS: (
            "resident_original_application_2d_3460_payload",
            program_source_words(
                APPLICATION_STORAGE_DRIVER_RESOLVE_ORIGINAL_SOURCE,
                APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SIZE,
            ),
        ),
        DES_TABLE_INITIALIZER_ADDRESS: (
            "resident_des_table_initializer",
            des_table_initializer_words(),
        ),
        APPLICATION_MENU_RESOURCE_DECODER_INSTALLER_ADDRESS: (
            "resident_application_menu_resource_decoder_installer",
            application_menu_resource_decoder_installer_words(),
        ),
        ROM06_KEY_RELEASE_ADDRESS: (
            "resident_rom06_key_release", rom06_key_release_words()
        ),
        ROM06_KEY_READ_ADDRESS: (
            "resident_rom06_key_read", rom06_key_read_words()
        ),
        ROM03_JUMP_TABLE_ADDRESS: (
            "resident_rom03_jump_table",
            program_source_words(
                ROM03_JUMP_TABLE_SOURCE, ROM03_JUMP_TABLE_SIZE
            ),
        ),
        ROM08_MODULE_ADDRESS: (
            "resident_rom08_module",
            program_source_words(ROM08_MODULE_SOURCE, ROM08_MODULE_SIZE),
        ),
        LCD_BUS_INIT_ADDRESS: (
            "resident_lcd_bus_init",
            program_source_words(LCD_BUS_INIT_SOURCE, LCD_BUS_INIT_SIZE),
        ),
        LCD_BUS_WRITE_ADDRESS: (
            "resident_lcd_bus_write",
            program_source_words(LCD_BUS_WRITE_SOURCE, LCD_BUS_WRITE_SIZE),
        ),
        LCD_POWER_INIT_ADDRESS: (
            "resident_lcd_power_init",
            program_source_words(LCD_POWER_INIT_SOURCE, LCD_POWER_INIT_SIZE),
        ),
        LCD_CONTROLLER_INIT_ADDRESS: (
            "resident_lcd_controller_init",
            program_source_words(
                LCD_CONTROLLER_INIT_SOURCE, LCD_CONTROLLER_INIT_SIZE
            ),
        ),
        LCD_CLEAR_ADDRESS: (
            "resident_lcd_clear",
            program_source_words(LCD_CLEAR_SOURCE, LCD_CLEAR_SIZE),
        ),
        LCD_REGION_INIT_ADDRESS: (
            "resident_lcd_region_init",
            program_source_words(LCD_REGION_INIT_SOURCE, LCD_REGION_INIT_SIZE),
        ),
        LCD_BITMAP_INIT_ADDRESS: (
            "resident_lcd_bitmap_init",
            program_source_words(LCD_BITMAP_INIT_SOURCE, LCD_BITMAP_INIT_SIZE),
        ),
        LCD_DELAY_ADDRESS: (
            "resident_lcd_delay",
            program_source_words(LCD_DELAY_SOURCE, LCD_DELAY_SIZE),
        ),
        RESIDENT_RESOURCE_DISPATCH_14_ADDRESS: (
            "resident_resource_dispatch_14_b768",
            program_source_words(
                RESIDENT_RESOURCE_DISPATCH_14_SOURCE,
                RESIDENT_RESOURCE_DISPATCH_14_SIZE,
            ),
        ),
        RESIDENT_DISPATCH_1A_ADDRESS: (
            "resident_dispatch_1a_423c",
            program_source_words(
                RESIDENT_DISPATCH_1A_SOURCE, RESIDENT_DISPATCH_1A_SIZE
            ),
        ),
        RESIDENT_WIDE_ARITHMETIC_1A_ADDRESS: (
            "resident_wide_arithmetic_1a_c352",
            program_source_words(
                RESIDENT_WIDE_ARITHMETIC_1A_SOURCE,
                RESIDENT_WIDE_ARITHMETIC_1A_SIZE,
            ),
        ),
        RESIDENT_OPERATION_1B23B8_ADDRESS: (
            "resident_operation_1b_23b8",
            program_source_words(
                RESIDENT_OPERATION_1B23B8_SOURCE,
                RESIDENT_OPERATION_1B23B8_SIZE,
            ),
        ),
        RESIDENT_TRANSFORM_1B_ADDRESS: (
            "resident_transform_1b_c5ec",
            retarget_program_source_call(
                RESIDENT_TRANSFORM_1B_SOURCE,
                RESIDENT_TRANSFORM_1B_SIZE,
                RESIDENT_TRANSFORM_1B_SECTOR_PROBE_CALL_SOURCE,
                APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
                APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION,
            ),
        ),
        RESIDENT_TRANSFORM_1C_ADDRESS: (
            "resident_transform_1c_ccd4",
            retarget_program_source_calls(
                RESIDENT_TRANSFORM_1C_SOURCE,
                RESIDENT_TRANSFORM_1C_SIZE,
                (
                    (RESIDENT_TRANSFORM_1C_SECTOR_PROBE_CALL_SOURCE,
                     APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
                     APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION),
                    (RESIDENT_TRANSFORM_1C_STORAGE_PAIR_CALL_SOURCE,
                     0x306E9E,
                     RESIDENT_STORAGE_PAIR_ADDRESS),
                ),
            ),
        ),
        RESIDENT_EVENT_PACKET_ADDRESS: (
            "resident_event_packet_1c_f28a",
            program_source_words(
                RESIDENT_EVENT_PACKET_SOURCE,
                RESIDENT_EVENT_PACKET_SIZE,
            ),
        ),
        RESIDENT_APPLICATION_RECORD_LOADER_ADDRESS: (
            "resident_application_record_loader_1d_0eea",
            program_source_words(
                RESIDENT_APPLICATION_RECORD_LOADER_SOURCE,
                RESIDENT_APPLICATION_RECORD_LOADER_SIZE,
            ),
        ),
        RESIDENT_APPLICATION_RESOURCE_OPEN_ADDRESS: (
            "resident_application_resource_open_1d_668a",
            program_source_words(
                RESIDENT_APPLICATION_RESOURCE_OPEN_SOURCE,
                RESIDENT_APPLICATION_RESOURCE_OPEN_SIZE,
            ),
        ),
        RESIDENT_ROOT_MENU_CONTROLLER_ADDRESS: (
            "resident_root_menu_controller_1d_f2ec",
            program_source_words(
                RESIDENT_ROOT_MENU_CONTROLLER_SOURCE,
                RESIDENT_ROOT_MENU_CONTROLLER_SIZE,
            ),
        ),
        RESIDENT_EVENT_STATE_ADDRESS: (
            "resident_event_state_19_f8b8",
            program_source_words(
                RESIDENT_EVENT_STATE_SOURCE,
                RESIDENT_EVENT_STATE_SIZE,
            ),
        ),
        RESIDENT_EVENT_RENDER_10_ADDRESS: (
            "resident_event_render_10_5090",
            program_source_words(
                RESIDENT_EVENT_RENDER_10_SOURCE,
                RESIDENT_EVENT_RENDER_10_SIZE,
            ),
        ),
        RESIDENT_ROOT_MENU_RENDER_ADDRESS: (
            "resident_root_menu_render_10_e4aa",
            program_source_words(
                RESIDENT_ROOT_MENU_RENDER_SOURCE,
                RESIDENT_ROOT_MENU_RENDER_SIZE,
            ),
        ),
        RESIDENT_ROOT_BITMAP_BLIT_ADDRESS: (
            "resident_root_bitmap_blit_17_18e6",
            program_source_words(
                RESIDENT_ROOT_BITMAP_BLIT_SOURCE,
                RESIDENT_ROOT_BITMAP_BLIT_SIZE,
            ),
        ),
        RESIDENT_STORAGE_METADATA_INIT_ADDRESS: (
            "resident_storage_metadata_init_1c_28ac",
            program_source_words(
                RESIDENT_STORAGE_METADATA_INIT_SOURCE,
                RESIDENT_STORAGE_METADATA_INIT_SIZE,
            ),
        ),
        RESIDENT_RESOURCE_STORAGE_UNIT_ADDRESS: (
            "resident_resource_storage_unit_1c_7ffe",
            program_source_words(
                RESIDENT_RESOURCE_STORAGE_UNIT_SOURCE,
                RESIDENT_RESOURCE_STORAGE_UNIT_SIZE,
            ),
        ),
        RESIDENT_MENU_PAGE_TABLE_ADDRESS: (
            "resident_menu_page_table_1c_9748",
            program_source_words(
                RESIDENT_MENU_PAGE_TABLE_SOURCE,
                RESIDENT_MENU_PAGE_TABLE_SIZE,
            ),
        ),
        RESIDENT_RESOURCE_STORAGE_SCAN_ADDRESS: (
            "resident_resource_storage_scan_1e_7e4e",
            program_source_words(
                RESIDENT_RESOURCE_STORAGE_SCAN_SOURCE,
                RESIDENT_RESOURCE_STORAGE_SCAN_SIZE,
            ),
        ),
        RESIDENT_XOR_COPY_07_ADDRESS: (
            "resident_xor_copy_07_36d4",
            program_source_words(
                RESIDENT_XOR_COPY_07_SOURCE,
                RESIDENT_XOR_COPY_07_SIZE,
            ),
        ),
        RESIDENT_RECORD_INDEX_LOOKUP_07_ADDRESS: (
            "resident_record_index_lookup_07_912e",
            program_source_words(
                RESIDENT_RECORD_INDEX_LOOKUP_07_SOURCE,
                RESIDENT_RECORD_INDEX_LOOKUP_07_SIZE,
            ),
        ),
        **{
            address: (name, program_source_words(source, size))
            for address, source, size, name
            in RESIDENT_RECORD_MATERIALIZATION_CLOSURE
        },
        RESIDENT_STORAGE_DRIVER_ADDRESS: (
            "resident_storage_driver_07_4000",
            resident_storage_driver_words(),
        ),
        RESIDENT_STORAGE_SELECT_ADDRESS: (
            "resident_storage_select_07_4200",
            resident_storage_select_words(),
        ),
        RESIDENT_STORAGE_PAIR_ADDRESS: (
            "resident_storage_pair_07_4500",
            resident_storage_pair_words(),
        ),
        RESIDENT_STORAGE_PROBE_WRAPPER_ADDRESS: (
            "resident_storage_probe_wrapper_07_4600",
            resident_storage_probe_wrapper_words(),
        ),
        RESIDENT_STORAGE_MUL_DIV_ADDRESS: (
            "resident_storage_mul_div_07_4700",
            resident_storage_mul_div_words(),
        ),
        RESIDENT_STORAGE_SCAN_ADDRESS: (
            "resident_storage_scan_07_4800",
            resident_storage_scan_words(),
        ),
        RESIDENT_STORAGE_RESULT_LEAF_ADDRESS: (
            "resident_storage_result_leaf_07_5000",
            program_source_words(
                RESIDENT_STORAGE_RESULT_LEAF_SOURCE,
                RESIDENT_STORAGE_RESULT_LEAF_SIZE,
            ),
        ),
        RESIDENT_STORAGE_RANGE_LEAF_ADDRESS: (
            "resident_storage_range_leaf_07_5020",
            program_source_words(
                RESIDENT_STORAGE_RANGE_LEAF_SOURCE,
                RESIDENT_STORAGE_RANGE_LEAF_SIZE,
            ),
        ),
        RESIDENT_APPLICATION_LOOP_0E_ADDRESS: (
            "resident_application_loop_0e_75ba",
            program_source_words(
                RESIDENT_APPLICATION_LOOP_0E_SOURCE,
                RESIDENT_APPLICATION_LOOP_0E_SIZE,
            ),
        ),
        RESIDENT_RECURSIVE_16_ADDRESS: (
            "resident_recursive_16_52aa",
            program_source_words(
                RESIDENT_RECURSIVE_16_SOURCE,
                RESIDENT_RECURSIVE_16_SIZE,
            ),
        ),
        RESIDENT_APPLICATION_SELECTOR_17_ADDRESS: (
            "resident_application_selector_17_4a3a",
            program_source_words(
                RESIDENT_APPLICATION_SELECTOR_17_SOURCE,
                RESIDENT_APPLICATION_SELECTOR_17_SIZE,
            ),
        ),
        RESIDENT_FONT_LOOKUP_ADDRESS: (
            "resident_font_lookup_17_9244",
            program_source_words(
                RESIDENT_FONT_LOOKUP_SOURCE, RESIDENT_FONT_LOOKUP_SIZE
            ),
        ),
        RESIDENT_FILE_WRITE_ADDRESS: (
            "resident_file_write_17_e3ee",
            resident_file_write_words(),
        ),
        RESIDENT_FONT_BLIT_ADDRESS: (
            "resident_font_blit_module_18_6454",
            program_source_words(
                RESIDENT_FONT_BLIT_SOURCE, RESIDENT_FONT_BLIT_SIZE
            ),
        ),
        RESIDENT_RESULT_REGION_COPY_ADDRESS: (
            "resident_result_region_copy_18_66ee",
            program_source_words(
                RESIDENT_RESULT_REGION_COPY_SOURCE,
                RESIDENT_RESULT_REGION_COPY_SIZE,
            ),
        ),
        RESIDENT_REGION_COMPOSE_18_ADDRESS: (
            "resident_region_compose_18_7a02",
            program_source_words(
                RESIDENT_REGION_COMPOSE_18_SOURCE,
                RESIDENT_REGION_COMPOSE_18_SIZE,
            ),
        ),
        RESIDENT_APPLICATION_LAUNCH_MANAGER_ADDRESS: (
            "resident_application_launch_manager_18_21f4",
            program_source_words(
                RESIDENT_APPLICATION_LAUNCH_MANAGER_SOURCE,
                RESIDENT_APPLICATION_LAUNCH_MANAGER_SIZE,
            ),
        ),
        RESIDENT_MENU_RECORD_DECODE_11_ADDRESS: (
            "resident_menu_record_decode_11_5c12",
            program_source_words(
                RESIDENT_MENU_RECORD_DECODE_11_SOURCE,
                RESIDENT_MENU_RECORD_DECODE_11_SIZE,
            ),
        ),
        RESIDENT_MENU_EVENT_DISPATCH_ADDRESS: (
            "resident_menu_event_dispatch_18_9a58",
            program_source_words(
                RESIDENT_MENU_EVENT_DISPATCH_SOURCE,
                RESIDENT_MENU_EVENT_DISPATCH_SIZE,
            ),
        ),
        RESIDENT_REGION_MASK_18_ADDRESS: (
            "resident_region_mask_18_a510",
            program_source_words(
                RESIDENT_REGION_MASK_18_SOURCE,
                RESIDENT_REGION_MASK_18_SIZE,
            ),
        ),
        RESIDENT_OPERATION_CONTEXT_18_ADDRESS: (
            "resident_operation_context_18_cfa8",
            program_source_words(
                RESIDENT_OPERATION_CONTEXT_18_SOURCE,
                RESIDENT_OPERATION_CONTEXT_18_SIZE,
            ),
        ),
        RESIDENT_STORAGE_INIT_ADDRESS: (
            "resident_storage_init_1e_5084",
            program_source_words(
                RESIDENT_STORAGE_INIT_SOURCE,
                RESIDENT_STORAGE_INIT_SIZE,
            ),
        ),
        RESIDENT_RESULT_OBJECT_ALLOC_ADDRESS: (
            "resident_result_object_alloc_1e_6444",
            program_source_words(
                RESIDENT_RESULT_OBJECT_ALLOC_SOURCE,
                RESIDENT_RESULT_OBJECT_ALLOC_SIZE,
            ),
        ),
        RESIDENT_RESULT_TYPE_QUERY_ADDRESS: (
            "resident_result_type_query_1e_a4ce",
            program_source_words(
                RESIDENT_RESULT_TYPE_QUERY_SOURCE,
                RESIDENT_RESULT_TYPE_QUERY_SIZE,
            ),
        ),
        RESIDENT_RECORD_STATUS_ADDRESS: (
            "resident_record_status_1e_ab32",
            program_source_words(
                RESIDENT_RECORD_STATUS_SOURCE,
                RESIDENT_RECORD_STATUS_SIZE,
            ),
        ),
        RESIDENT_APPLICATION_CONFIG_ADDRESS: (
            "resident_application_config_1e_b7f6",
            program_source_words(
                RESIDENT_APPLICATION_CONFIG_SOURCE,
                RESIDENT_APPLICATION_CONFIG_SIZE,
            ),
        ),
        RESIDENT_RESULT_RECORD_BUILD_ADDRESS: (
            "resident_result_record_build_1e_c4ac",
            retarget_program_source_call(
                RESIDENT_RESULT_RECORD_BUILD_SOURCE,
                RESIDENT_RESULT_RECORD_BUILD_SIZE,
                RESIDENT_RESULT_RECORD_BUILD_SECTOR_PROBE_CALL_SOURCE,
                APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
                APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION,
            ),
        ),
        RESIDENT_OBJECT_TABLE_UPDATE_ADDRESS: (
            "resident_object_table_update_1e_d15c",
            program_source_words(
                RESIDENT_OBJECT_TABLE_UPDATE_SOURCE,
                RESIDENT_OBJECT_TABLE_UPDATE_SIZE,
            ),
        ),
        RESIDENT_APPLICATION_STATE_ADDRESS: (
            "resident_application_state_guard_probe_1e_f734"
            if probe_resident_app_state_guard
            else "resident_application_state_1e_f734",
            resident_application_state_guard_words()
            if probe_resident_app_state_guard
            else program_source_words(
                    RESIDENT_APPLICATION_STATE_SOURCE,
                    RESIDENT_APPLICATION_STATE_SIZE,
                 ),
        ),
        RESIDENT_RESULT_RECORD_COMPARE_ADDRESS: (
            "resident_result_record_compare_1f_dd42",
            program_source_words(
                RESIDENT_RESULT_RECORD_COMPARE_SOURCE,
                RESIDENT_RESULT_RECORD_COMPARE_SIZE,
            ),
        ),
        RESIDENT_HANDLER_1F12B4_ADDRESS: (
            "resident_handler_1f_12b4",
            program_source_words(
                RESIDENT_HANDLER_1F12B4_SOURCE,
                RESIDENT_HANDLER_1F12B4_SIZE,
            ),
        ),
        RESIDENT_FILE_OPEN_1F1F1A_ADDRESS: (
            "resident_file_open_1f_1f1a",
            # Unlike application RAM, resident segment 1F cannot be patched
            # by the guest overlay installer.  Retarget every source-proven
            # collided child while embedding the recovered mask-ROM body.
            retarget_program_source_calls(
                RESIDENT_FILE_OPEN_1F1F1A_SOURCE,
                RESIDENT_FILE_OPEN_1F1F1A_SIZE,
                (
                    (0x3C218E,
                     APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_LINKED_DESTINATION,
                     APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_DESTINATION),
                    (0x3C21DE,
                     APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_LINKED_DESTINATION,
                     APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_DESTINATION),
                    (0x3C221E,
                     APPLICATION_FILE_RECORD_STATUS_LINKED_DESTINATION,
                     APPLICATION_FILE_RECORD_STATUS_OVERLAY_DESTINATION),
                    (0x3C225A,
                     APPLICATION_FILE_METADATA_UPDATE_LINKED_DESTINATION,
                     APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION),
                    (0x3C22D6,
                     APPLICATION_FILE_CLOSE_STATE_LINKED_DESTINATION,
                     APPLICATION_FILE_CLOSE_STATE_OVERLAY_DESTINATION),
                    (0x3C2334,
                     APPLICATION_FILE_CLOSE_RECORD_SYNC_LINKED_DESTINATION,
                     APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_DESTINATION),
                    (0x3C2358,
                     0x2D3460,
                     RESIDENT_STORAGE_DRIVER_ADDRESS),
                ),
            ),
        ),
        RESIDENT_APPLICATION_EVENT_ADDRESS: (
            "resident_application_event_1f_b496",
            program_source_words(
                RESIDENT_APPLICATION_EVENT_SOURCE,
                RESIDENT_APPLICATION_EVENT_SIZE,
            ),
        ),
        RESIDENT_RESOURCE_INIT_1BCE3C_ADDRESS: (
            "resident_resource_init_1b_ce3c",
            program_source_words(
                RESIDENT_RESOURCE_INIT_1BCE3C_SOURCE,
                RESIDENT_RESOURCE_INIT_1BCE3C_SIZE,
            ),
        ),
        RESIDENT_STATE_IMPORT_ADDRESS: (
            "resident_state_import_1f_f470",
            program_source_words(
                RESIDENT_STATE_IMPORT_SOURCE,
                RESIDENT_STATE_IMPORT_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_STATE_OVERLAY_DESTINATION: (
            "resident_application_main_state_1d_b4a6",
            program_source_words(
                APPLICATION_MAIN_ROM_STATE_OVERLAY_SOURCE,
                APPLICATION_MAIN_ROM_STATE_OVERLAY_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_MENU_OVERLAY_DESTINATION: (
            "resident_application_main_menu_15_d474",
            program_source_words(
                APPLICATION_MAIN_ROM_MENU_OVERLAY_SOURCE,
                APPLICATION_MAIN_ROM_MENU_OVERLAY_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_COMPOSITOR_DESTINATION: (
            "resident_application_main_compositor_13_9444",
            program_source_words(
                APPLICATION_MAIN_ROM_COMPOSITOR_SOURCE,
                APPLICATION_MAIN_ROM_COMPOSITOR_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_RESOURCE_STATE_DESTINATION: (
            "resident_application_main_resource_state_07_7136",
            program_source_words(
                APPLICATION_MAIN_ROM_RESOURCE_STATE_SOURCE,
                APPLICATION_MAIN_ROM_RESOURCE_STATE_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_RESOURCE_PROBE_DESTINATION: (
            "resident_application_main_resource_probe_07_a496",
            program_source_words(
                APPLICATION_MAIN_ROM_RESOURCE_PROBE_SOURCE,
                APPLICATION_MAIN_ROM_RESOURCE_PROBE_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_RESOURCE_TEST_DESTINATION: (
            "resident_application_main_resource_test_07_a5a6",
            program_source_words(
                APPLICATION_MAIN_ROM_RESOURCE_TEST_SOURCE,
                APPLICATION_MAIN_ROM_RESOURCE_TEST_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_RESOURCE_SCAN_DESTINATION: (
            "resident_application_main_resource_scan_05_89ec",
            program_source_words(
                APPLICATION_MAIN_ROM_RESOURCE_SCAN_SOURCE,
                APPLICATION_MAIN_ROM_RESOURCE_SCAN_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_RESOURCE_CHECK_DESTINATION: (
            "resident_application_main_resource_check_06_1138",
            program_source_words(
                APPLICATION_MAIN_ROM_RESOURCE_CHECK_SOURCE,
                APPLICATION_MAIN_ROM_RESOURCE_CHECK_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_RESOURCE_XOR_DESTINATION: (
            "resident_application_main_resource_xor_07_367e",
            program_source_words(
                APPLICATION_MAIN_ROM_RESOURCE_XOR_SOURCE,
                APPLICATION_MAIN_ROM_RESOURCE_XOR_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_RESOURCE_HEX_DESTINATION: (
            "resident_application_main_resource_hex_07_3734",
            program_source_words(
                APPLICATION_MAIN_ROM_RESOURCE_HEX_SOURCE,
                APPLICATION_MAIN_ROM_RESOURCE_HEX_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_RESOURCE_FORMAT_DESTINATION: (
            "resident_application_main_resource_format_07_37a0",
            program_source_words(
                APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SOURCE,
                APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_LAYOUT_BUILD_DESTINATION: (
            "resident_application_main_layout_build_12_5434",
            program_source_words(
                APPLICATION_MAIN_ROM_LAYOUT_BUILD_SOURCE,
                APPLICATION_MAIN_ROM_LAYOUT_BUILD_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_RENDER_DESTINATION: (
            "resident_application_main_render_1d_831e",
            program_source_words(
                APPLICATION_MAIN_ROM_RENDER_SOURCE,
                APPLICATION_MAIN_ROM_RENDER_SIZE,
            ),
        ),
        APPLICATION_MAIN_ROM_INPUT_DESTINATION: (
            "resident_application_main_input_11_1752",
            application_main_rom_input_words(),
        ),
        APPLICATION_COMPARE_ROM_DESTINATION: (
            "resident_application_compare_1a_deaa",
            program_source_words(
                APPLICATION_COMPARE_ROM_SOURCE,
                APPLICATION_COMPARE_ROM_SIZE,
            ),
        ),
        APPLICATION_FOREGROUND_STATE50_ROM_DESTINATION: (
            "resident_application_state50_rom_0c_0000",
            application_foreground_state50_rom_words(),
        ),
        APPLICATION_FOREGROUND_STATE50_CLEANUP_INSTALLER_ADDRESS: (
            "resident_application_state50_cleanup_installer_0c_4a6c",
            [
                *embed_program_overlay_words(
                    APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_DESTINATION,
                    APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_SOURCE,
                    APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_SIZE,
                ),
                # The 0C module directly calls these two menu-lifetime
                # wrappers both during setup and from its common exit path.
                # Their larger stable-source list workers are already part
                # of install_runtime_overlay_words(); only the mutable-bank
                # wrappers themselves must be made resident this early.
                *embed_program_overlay_words(
                    APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_DESTINATION,
                    APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SOURCE,
                    APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SIZE,
                ),
                *embed_program_overlay_words(
                    APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_DESTINATION,
                    APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SOURCE,
                    APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SIZE,
                ),
                *write_program_words(
                    APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_DESTINATION,
                    application_foreground_state50_setting_words(),
                ),
                *write_program_words(
                    APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_DESTINATION,
                    application_foreground_state50_setting_child_words(),
                ),
                *embed_program_overlay_words(
                    APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_DESTINATION,
                    APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_SOURCE,
                    APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_SIZE,
                ),
                RETS,
            ],
        ),
        APPLICATION_POST_MODAL_TEXT_ROM_DATA_DESTINATION: (
            "resident_application_post_modal_text_1d_fff6",
            program_source_words(
                APPLICATION_POST_MODAL_TEXT_ROM_DATA_SOURCE,
                APPLICATION_POST_MODAL_TEXT_ROM_DATA_SIZE,
            ),
        ),
        APPLICATION_FOREGROUND_STATE50_ROM_DATA_DESTINATION: (
            "resident_application_state50_string_pool_1e_4486",
            program_source_words(
                APPLICATION_FOREGROUND_STATE50_ROM_DATA_SOURCE,
                APPLICATION_FOREGROUND_STATE50_ROM_DATA_SIZE,
            ),
        ),
        APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_DESTINATION: (
            "resident_application_state50_workspace_1b_acc0",
            program_source_words(
                APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_SOURCE,
                APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_SIZE,
            ),
        ),
        APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_DESTINATION: (
            "resident_application_state50_format_1f_6df6",
            application_foreground_state50_format_rom_words(),
        ),
        APPLICATION_FOREGROUND_STATE50_CHILD_ROM_DESTINATION: (
            "resident_application_state50_child_1e_3c98",
            program_source_words(
                APPLICATION_FOREGROUND_STATE50_CHILD_ROM_SOURCE,
                APPLICATION_FOREGROUND_STATE50_CHILD_ROM_SIZE,
            ),
        ),
        APPLICATION_FOREGROUND_ROM_WORKER_DESTINATION: (
            "resident_application_foreground_worker_1c_5892",
            program_source_words(
                APPLICATION_FOREGROUND_ROM_WORKER_SOURCE,
                APPLICATION_FOREGROUND_ROM_WORKER_SIZE,
            ),
        ),
        APPLICATION_FOREGROUND_ROM_DISPATCH_DESTINATION: (
            "resident_application_foreground_dispatch_16_bbcc",
            program_source_words(
                APPLICATION_FOREGROUND_ROM_DISPATCH_SOURCE,
                APPLICATION_FOREGROUND_ROM_DISPATCH_SIZE,
            ),
        ),
        FAR_MEMCPY_ADDRESS: ("resident_far_memcpy", far_memcpy_words()),
    }
    for address, source, size, name in RESIDENT_CONFIGURATION_VARIANTS:
        routines[address] = (name, program_source_words(source, size))
    if not (initializer_probe or initializer_overlay_probe or
            dual_initializer_probe):
        routines[DEFAULT_OVERLAY_INSTALLER_ADDRESS] = (
            "default_boot_overlay_installer",
            default_overlay_installer_words(),
        )
    if probe_storage_global_templates or probe_fixed_launch_wrapper:
        routines[STORAGE_GLOBAL_TEMPLATE_PROBE_ADDRESS] = (
            "segment33_data_template_probe",
            storage_global_template_probe_words(),
        )
    # --probe-rom-02-c588-return is retained as a no-op compatibility switch.
    # Caller analysis now constrains the CPU-visible contract sufficiently for
    # the guest return to be part of every reconstructed image.
    # --probe-font-lookup is retained as a no-op compatibility switch. The
    # complete 34:9244 same-PC copy above has replaced the old RETS probe.
    # --probe-rom-03-4124-zero is retained only as a compatibility flow
    # switch. The exact 03:4124 trampoline is now recovered inside the table
    # above and is never replaced by a fabricated zero-return implementation.
    if initializer_overlay_probe or dual_initializer_probe:
        if factory_linked_startup:
            # Exact +0x1D linked layout proven by the terminal jumps and the
            # otherwise-unreferenced storage copies.  Only the final 07:* jump
            # is redirected to the explicit late-overlay loader.
            routines[FACTORY_COMPILER_INITIALIZER_DESTINATION] = (
                "factory_linked_compiler_initializer_11_4560",
                program_source_words(
                    FACTORY_COMPILER_INITIALIZER_SOURCE,
                    FACTORY_COMPILER_INITIALIZER_SIZE,
                ),
            )
            routines[FACTORY_CONSTANT_INITIALIZER_DESTINATION] = (
                "factory_linked_constant_initializer_07_7fe4",
                factory_constant_initializer_words(),
            )
            routines[FACTORY_SYSTEM_MAIN_DESTINATION] = (
                ("factory_linked_system_init_then_manager_03_026a"
                 if (probe_direct_generic_menu or
                     probe_factory_default_catalogue) else
                 "factory_linked_system_main_03_026a"),
                factory_system_main_words(
                    probe_direct_generic_menu or
                    probe_factory_default_catalogue
                ),
            )
        else:
            # Historical probe order retained to keep all prior artifacts and
            # ABI tests reproducible.  New system images should select
            # factory_linked_startup instead.
            routines[0x03026A] = (
                "second_initializer_continuation",
                [0xAD2E, 0x4560],
            )
        if initializer_overlay_probe:
            if not factory_linked_startup:
                routines[0x077FE4] = (
                    "post_initializer_continuation",
                    [0xAD00 | (POST_INITIALIZER_LOADER_ADDRESS >> 16),
                     POST_INITIALIZER_LOADER_ADDRESS & 0xFFFF],
                )
            routines[POST_INITIALIZER_LOADER_ADDRESS] = (
                "post_initializer_overlay_loader",
                post_initializer_overlay_words(
                    probe_rom_08_return, probe_continue_event_loop,
                    probe_lcd_power_on,
                    probe_stop_after_overlay_install,
                    probe_app_init_callback,
                    probe_system_main,
                    probe_storage_global_templates,
                    probe_fixed_launch_wrapper,
                    factory_linked_startup,
                    probe_direct_generic_menu,
                    probe_factory_default_catalogue,
                ),
            )
            if ((probe_continue_event_loop or probe_system_main) and
                    not factory_linked_startup):
                routines[0x030000 | POST_INITIALIZER_HANDOFF_PC] = (
                    "post_initializer_boot_handoff",
                    boot_frame_handoff_words(startup_context),
                )
    if probe_rom_01_return:
        routines[ROM01_POST_CLOCK_ADDRESS] = (
            "reconstructed_rom01_application_loader",
            rom01_application_loader_words(
                probe_generic_main_menu or
                probe_direct_generic_menu or
                probe_stop_after_scheduler_return or
                probe_stop_before_scheduler_entry,
                reconstruct_resident_root_desktop,
            ),
        )
    if probe_direct_generic_menu:
        routines[DIRECT_GENERIC_MENU_TEXT_STREAM_ADDRESS] = (
            "probe_direct_generic_menu_text_stream",
            direct_generic_menu_text_stream_words(),
        )
        routines[DIRECT_RESOURCE_NEXT_CLUSTER_ADDRESS] = (
            "probe_direct_resource_next_cluster",
            direct_resource_next_cluster_words(),
        )
        routines[DIRECT_RESOURCE_READ_CALLBACK_ADDRESS] = (
            "probe_direct_resource_read_callback",
            direct_resource_read_callback_words(),
        )
        routines[DIRECT_RESOURCE_POST_READ_ADDRESS] = (
            "probe_direct_resource_post_read",
            direct_resource_post_read_words(),
        )
        routines[DIRECT_GENERIC_MENU_PROBE_ADDRESS] = (
            "probe_direct_recovered_generic_menu",
            direct_generic_menu_probe_words(),
        )
    if probe_rom_0b_ccd2_zero:
        routines[RESIDENT_ROM0B_CCD2_ADDRESS] = (
            "probe_resident_rom0b_ccd2_zero_status",
            [0x4800, 0x4810, RETS],
        )
    return routines


ROUTINES = make_routines()


def build_image(startup_context: int = 0,
                probe_font_lookup: bool = False,
                initializer_probe: bool = False,
                initializer_overlay_probe: bool = False,
                dual_initializer_probe: bool = False,
                probe_rom_08_return: bool = False,
                probe_rom_03_rand_zero: bool = False,
                probe_continue_event_loop: bool = False,
                probe_dispatch_activation: bool = False,
                probe_lcd_power_on: bool = False,
                probe_stop_after_overlay_install: bool = False,
                probe_app_init_callback: bool = False,
                probe_system_main: bool = False,
                probe_rom_01_return: bool = False,
                probe_resident_app_state_guard: bool = False,
                preserve_metadata_block_probe: bool = False,
                probe_storage_global_templates: bool = False,
                probe_rom_02_c588_return: bool = False,
                probe_stop_after_scheduler_return: bool = False,
                probe_rom_0b_ccd2_zero: bool = False,
                probe_stop_before_scheduler_entry: bool = False,
                probe_fixed_launch_wrapper: bool = False,
                probe_generic_main_menu: bool = False,
                probe_direct_generic_menu: bool = False,
                probe_factory_default_catalogue: bool = False,
                factory_linked_startup: bool = False,
                reconstruct_resident_root_desktop: bool = False) -> bytes:
    routines = make_routines(
        startup_context, probe_font_lookup, initializer_probe,
        initializer_overlay_probe, dual_initializer_probe,
        probe_rom_08_return, probe_rom_03_rand_zero,
        probe_continue_event_loop, probe_dispatch_activation,
        probe_lcd_power_on, probe_stop_after_overlay_install,
        probe_app_init_callback, probe_system_main, probe_rom_01_return,
        probe_resident_app_state_guard, preserve_metadata_block_probe,
        probe_storage_global_templates, probe_rom_02_c588_return,
        probe_stop_after_scheduler_return, probe_rom_0b_ccd2_zero,
        probe_stop_before_scheduler_entry, probe_fixed_launch_wrapper,
        probe_generic_main_menu, probe_direct_generic_menu,
        probe_factory_default_catalogue,
        factory_linked_startup, reconstruct_resident_root_desktop
    )
    if initializer_overlay_probe:
        data_blocks = initializer_factory_source_blocks()
        data_blocks_are_logical_probe_bytes = False
    elif initializer_probe or dual_initializer_probe:
        data_blocks = INITIALIZER_PROBE_SOURCES
        data_blocks_are_logical_probe_bytes = True
    else:
        data_blocks = {}
        data_blocks_are_logical_probe_bytes = False
    occupied: dict[int, str] = {}
    end = 0
    for address, (name, words) in routines.items():
        for index, _word in enumerate(words):
            offset = address + index * 2
            if offset in occupied:
                raise ValueError(f"routine {name} overlaps {occupied[offset]}")
            occupied[offset] = name
            end = max(end, offset + 2)
    for address, data in data_blocks.items():
        for index in range(len(data)):
            offset = address + index
            if offset in occupied:
                raise ValueError(
                    f"initializer probe data overlaps {occupied[offset]}"
                )
            occupied[offset] = (
                "initializer_probe_sentinel"
                if data_blocks_are_logical_probe_bytes
                else "initializer_factory_source"
            )
            end = max(end, offset + 1)

    if end & 1:
        end += 1

    image = bytearray(end)
    fill = RESERVED.to_bytes(2, "little")
    for offset in range(0, end, 2):
        image[offset : offset + 2] = fill
    for address, (_name, words) in routines.items():
        for index, word in enumerate(words):
            offset = address + index * 2
            image[offset : offset + 2] = word.to_bytes(2, "little")
    for address, data in data_blocks.items():
        image[address:address + len(data)] = (
            initializer_probe_storage_bytes(data)
            if data_blocks_are_logical_probe_bytes else data
        )
    return bytes(image)


def manifest(image: bytes, startup_context: int = 0,
             probe_font_lookup: bool = False,
             initializer_probe: bool = False,
             initializer_overlay_probe: bool = False,
             dual_initializer_probe: bool = False,
             probe_rom_08_return: bool = False,
             probe_rom_03_rand_zero: bool = False,
             probe_continue_event_loop: bool = False,
             probe_dispatch_activation: bool = False,
             probe_lcd_power_on: bool = False,
             probe_stop_after_overlay_install: bool = False,
             probe_app_init_callback: bool = False,
             probe_system_main: bool = False,
             probe_rom_01_return: bool = False,
             probe_resident_app_state_guard: bool = False,
             preserve_metadata_block_probe: bool = False,
             probe_storage_global_templates: bool = False,
             probe_rom_02_c588_return: bool = False,
             probe_stop_after_scheduler_return: bool = False,
             probe_rom_0b_ccd2_zero: bool = False,
             probe_stop_before_scheduler_entry: bool = False,
             probe_fixed_launch_wrapper: bool = False,
             probe_generic_main_menu: bool = False,
             probe_direct_generic_menu: bool = False,
             probe_factory_default_catalogue: bool = False,
             factory_linked_startup: bool = False,
             reconstruct_resident_root_desktop: bool = False) -> dict:
    routines = make_routines(
        startup_context, probe_font_lookup, initializer_probe,
        initializer_overlay_probe, dual_initializer_probe,
        probe_rom_08_return, probe_rom_03_rand_zero,
        probe_continue_event_loop, probe_dispatch_activation,
        probe_lcd_power_on, probe_stop_after_overlay_install,
        probe_app_init_callback, probe_system_main, probe_rom_01_return,
        probe_resident_app_state_guard, preserve_metadata_block_probe,
        probe_storage_global_templates, probe_rom_02_c588_return,
        probe_stop_after_scheduler_return, probe_rom_0b_ccd2_zero,
        probe_stop_before_scheduler_entry, probe_fixed_launch_wrapper,
        probe_generic_main_menu, probe_direct_generic_menu,
        probe_factory_default_catalogue,
        factory_linked_startup, reconstruct_resident_root_desktop
    )
    probe_placeholders = []
    return {
        "format": "np560-clean-room-resident-rom-v1",
        "warning": "Reconstructed observable ABI; not original mask-ROM bytes.",
        "byte_order": "little-endian DMCU words",
        "program_source": str(PROGRAM_SOURCE.resolve()),
        "program_source_sha256": hashlib.sha256(
            PROGRAM_SOURCE.read_bytes()
        ).hexdigest(),
        "provision_trigger_target": (
            f"{PROVISION_TRIGGER_TARGET >> 16:02X}:"
            f"{PROVISION_TRIGGER_TARGET & 0xFFFF:04X}"
            if PROVISION_TRIGGER_TARGET else None
        ),
        "size": len(image),
        "fill_word": f"0x{RESERVED:04X}",
        "controller_mmio": f"0x{NAND_BASE:04X}",
        "startup_context": f"0x{startup_context:06X}",
        "probe_placeholders": probe_placeholders,
        "initializer_probe": initializer_probe,
        "initializer_overlay_probe": initializer_overlay_probe,
        "dual_initializer_probe": dual_initializer_probe,
        "factory_linked_startup": factory_linked_startup,
        "reconstruct_resident_root_desktop":
            reconstruct_resident_root_desktop,
        "probe_continue_event_loop": probe_continue_event_loop,
        "probe_generic_main_menu": probe_generic_main_menu,
        "probe_direct_generic_menu": probe_direct_generic_menu,
        "probe_factory_default_catalogue":
            probe_factory_default_catalogue,
        "preserve_metadata_block_probe": preserve_metadata_block_probe,
        "probe_dispatch_activation": probe_dispatch_activation,
        "probe_lcd_power_on": probe_lcd_power_on,
        "probe_stop_after_overlay_install": probe_stop_after_overlay_install,
        "probe_app_init_callback": probe_app_init_callback,
        "probe_system_main": probe_system_main,
        "probe_resident_app_state_guard": probe_resident_app_state_guard,
        "probe_storage_global_templates": probe_storage_global_templates,
        "probe_rom_02_c588_return": probe_rom_02_c588_return,
        "probe_rom_0b_ccd2_zero": probe_rom_0b_ccd2_zero,
        "probe_stop_after_scheduler_return":
            probe_stop_after_scheduler_return,
        "probe_stop_before_scheduler_entry":
            probe_stop_before_scheduler_entry,
        "probe_fixed_launch_wrapper": probe_fixed_launch_wrapper,
        "resident_rom0b_ccd2_probe": {
            "address": "0B:CCD2",
            "words": 3,
            "arguments": ["far pointer", "far pointer", "flag"],
            "result": "RB1=0",
            "status": (
                "exploration only; call ABI is evidenced at four PRG sites, "
                "but original mask-ROM behavior remains unresolved"
            ),
        } if probe_rom_0b_ccd2_zero else None,
        "resident_rom02_diagnostic_marker": {
            "address": "02:C588",
            "words": 1,
            "arguments": ["0x23", "0x24", "0x30", "0x65"],
            "status": (
                "caller-constrained normal-return guest code; probable "
                "external diagnostic-byte side effect remains unmodeled "
                "until its SFR or pin is evidenced"
            ),
        },
        "resident_rom00_dynamic_module": {
            "destination": "00:1002",
            "source": "2F:550C",
            "bytes": ROM00_DYNAMIC_MODULE_SIZE,
            "dynamic_prefix_bytes": ROM00_DYNAMIC_PREFIX_SIZE,
            "status": (
                "exact PRG-resident module; boot rewrites its prefix through "
                "internal executable RAM"
            ),
        },
        "resident_rom00_dynamic_absolute_epilogue": {
            "destination": "00:A4B0",
            "source": "2F:A4B0",
            "bytes": ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_SIZE,
            "status": (
                "exact split pop/UNLINK/RETS tail reached by the module's "
                "absolute AJMP"
            ),
        },
        "resident_rom00_critical_return": {
            "address": "00:85B0",
            "words": len(ROM00_CRITICAL_RETURN_WORDS),
            "status": (
                "ABI-constrained CRIT #0 plus RETS epilogue for the exact "
                "00:3F00 zero-byte callback"
            ),
        },
        "storage_global_template_probe": [
            {
                "destination": (
                    f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
                ),
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": size,
                "data": program_source_bytes(source, size).hex(),
            }
            for destination, source, size in segment33_data_template_records()
        ] if probe_storage_global_templates else [],
        "resident_rom08_module": {
            "destination": "08:2EDC",
            "source": "25:2EDC",
            "bytes": ROM08_MODULE_SIZE,
            "status": "exact guest module relocated to its linked segment",
        },
        "resident_rom03_jump_table": {
            "destination": "03:4000",
            "source": "20:4000",
            "bytes": ROM03_JUMP_TABLE_SIZE,
            "entries": ROM03_JUMP_TABLE_SIZE // 4,
            "status": "exact guest AJMP table relocated to its linked segment",
        },
        "resident_rom06_keyboard": {
            "release_address": "06:6A02",
            "read_address": "06:B126",
            "release_bytes": len(rom06_key_release_words()) * 2,
            "read_bytes": len(rom06_key_read_words()) * 2,
            "release_contract": (
                "no arguments; return value ignored at all four callers"
            ),
            "scanner": "2E:5F28 (exact updater relocation; 06:B126 only)",
            "mapper": "28:F4A4 (exact updater relocation)",
            "status": (
                "06:6A02 reduced to its caller-proven guest normal return "
                "after the inferred release loop was disproved; 06:B126 "
                "remains a caller-constrained guest-code reconstruction "
                "over the hardware matrix; no host ROM interception"
            ),
        },
        "resident_resource_dispatch_14": {
            "destination": "14:B768",
            "source": "31:B768",
            "bytes": RESIDENT_RESOURCE_DISPATCH_14_SIZE,
            "status": "exact same-PC resident resource/event dispatcher",
        },
        "resident_dispatch_1a": {
            "destination": "1A:423C",
            "source": "37:423C",
            "bytes": RESIDENT_DISPATCH_1A_SIZE,
            "status": "exact same-PC five-word resident function",
        },
        "resident_wide_arithmetic_1a": {
            "destination": "1A:C352",
            "source": "37:C352",
            "bytes": RESIDENT_WIDE_ARITHMETIC_1A_SIZE,
            "status": (
                "exact same-PC four-word to R0:R3 resident arithmetic body"
            ),
        },
        "resident_operation_1b_23b8": {
            "destination": "1B:23B8",
            "source": "38:23B8",
            "bytes": RESIDENT_OPERATION_1B23B8_SIZE,
            "status": (
                "exact same-PC resident operation-0x0B launch preparation"
            ),
        },
        "resident_transform_1b": {
            "destination": "1B:C5EC",
            "source": "38:C5EC",
            "bytes": RESIDENT_TRANSFORM_1B_SIZE,
            "status": "exact same-PC resident arithmetic/record transform",
        },
        "resident_transform_1c": {
            "destination": "1C:CCD4",
            "source": "39:CCD4",
            "bytes": RESIDENT_TRANSFORM_1C_SIZE,
            "status": "exact same-PC resident arithmetic/record transform",
        },
        "resident_event_packet_1c_f28a": {
            "destination": "1C:F28A",
            "source": "39:F28A",
            "bytes": RESIDENT_EVENT_PACKET_SIZE,
            "status": "exact same-PC resident event/packet processing body",
        },
        "resident_application_record_loader_1d_0eea": {
            "destination": "1D:0EEA",
            "source": "3A:0EEA",
            "bytes": RESIDENT_APPLICATION_RECORD_LOADER_SIZE,
            "status": (
                "exact same-PC application-record storage window loader"
            ),
        },
        "resident_application_resource_open_1d_668a": {
            "destination": "1D:668A",
            "source": "3A:668A",
            "bytes": RESIDENT_APPLICATION_RESOURCE_OPEN_SIZE,
            "status": (
                "exact same-PC application resource validation/open body"
            ),
        },
        "resident_root_menu_controller_1d_f2ec": {
            "destination": "1D:F2EC",
            "source": "3A:F2EC",
            "bytes": RESIDENT_ROOT_MENU_CONTROLLER_SIZE,
            "status": (
                "exact same-PC resident root-menu controller reached through "
                "the recovered 20:2DE0 foreground wrapper"
            ),
        },
        "resident_des_transform_02_dea6": {
            "destination": "02:DEA6",
            "bytes": len(des_transform_words()) * 2,
            "abi": (
                "data far pointer, key far pointer, 64-bit block count, "
                "direction (1 encrypt / 0 decrypt)"
            ),
            "call_sites": 24,
            "triple_des_use": "two-key E-D-E over consecutive 8-byte keys",
            "tables": "guest-initialized standard FIPS DES tables at 5F:E000",
            "verification": (
                "QEMU guest known-answer: 0123456789ABCDEF with key "
                "133457799BBCDFF1 -> 85E813540F0AB405 and inverse"
            ),
            "status": "clean-room DMCU guest code; no QEMU SCALL interception",
        },
        "resident_event_state_19_f8b8": {
            "destination": "19:F8B8",
            "source": "36:F8B8",
            "bytes": RESIDENT_EVENT_STATE_SIZE,
            "status": "exact same-PC resident event/state processing body",
        },
        "resident_event_render_10_5090": {
            "destination": "10:5090",
            "source": "2D:5090",
            "bytes": RESIDENT_EVENT_RENDER_10_SIZE,
            "status": "exact same-PC resident event/rendering body",
        },
        "resident_root_menu_render_10_e4aa": {
            "destination": "10:E4AA",
            "source": "2D:E4AA",
            "bytes": RESIDENT_ROOT_MENU_RENDER_SIZE,
            "status": (
                "exact same-PC hierarchy-aware root-menu rendering body"
            ),
        },
        "resident_root_bitmap_blit_17_18e6": {
            "destination": "17:18E6",
            "source": "34:18E6",
            "bytes": RESIDENT_ROOT_BITMAP_BLIT_SIZE,
            "status": (
                "exact same-PC packed bitmap and mask compositor used by "
                "root-menu resources"
            ),
        },
        "resident_storage_metadata_init": {
            "destination": "1C:28AC",
            "source": "39:28AC",
            "bytes": RESIDENT_STORAGE_METADATA_INIT_SIZE,
            "status": "exact same-PC resident NAND metadata initialization body",
        },
        "resident_resource_storage_unit": {
            "destination": "1C:7FFE",
            "source": "39:7FFE",
            "bytes": RESIDENT_RESOURCE_STORAGE_UNIT_SIZE,
            "status": (
                "exact same-PC resident storage unit worker including its "
                "internal 39:8110 -> 39:873C jump"
            ),
        },
        "resident_menu_page_table_1c": {
            "destination": "1C:9748",
            "source": "39:9748",
            "bytes": RESIDENT_MENU_PAGE_TABLE_SIZE,
            "status": "exact 25-record resident menu hierarchy table",
        },
        "resident_resource_storage_scan": {
            "destination": "1E:7E4E",
            "source": "3B:7E4E",
            "bytes": RESIDENT_RESOURCE_STORAGE_SCAN_SIZE,
            "status": "exact same-PC resident resource/NAND scan body",
        },
        "resident_application_loop_0e": {
            "destination": "0E:75BA",
            "source": "2B:75BA",
            "bytes": RESIDENT_APPLICATION_LOOP_0E_SIZE,
            "status": "exact same-PC resident application/event-loop body",
        },
        "resident_xor_copy_07_36d4": {
            "address": "07:36D4",
            "source": "24:36D4",
            "bytes": RESIDENT_XOR_COPY_07_SIZE,
            "status": "exact same-PC resident byte-XOR copy primitive",
        },
        "resident_record_index_lookup_07_912e": {
            "destination": "07:912E",
            "source": "24:912E",
            "bytes": RESIDENT_RECORD_INDEX_LOOKUP_07_SIZE,
            "arguments": ["two-word far pointer to record descriptor"],
            "result": "matching record index, or -1",
            "status": "exact same-PC resident record-index lookup",
        },
        "resident_record_materialization_closure": [
            {
                "destination": (
                    f"{address >> 16:02X}:{address & 0xFFFF:04X}"
                ),
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": size,
                "routine": name,
                "status": "exact same-PC resident guest function",
            }
            for address, source, size, name
            in RESIDENT_RECORD_MATERIALIZATION_CLOSURE
        ],
        "resident_recursive_16": {
            "destination": "16:52AA",
            "source": "33:52AA",
            "bytes": RESIDENT_RECURSIVE_16_SIZE,
            "status": "exact same-PC resident recursive transform body",
        },
        "resident_application_selector_17": {
            "destination": "17:4A3A",
            "source": "34:4A3A",
            "bytes": RESIDENT_APPLICATION_SELECTOR_17_SIZE,
            "status": "exact same-PC resident application selector body",
        },
        "resident_font_lookup": {
            "destination": "17:9244",
            "source": "34:9244",
            "bytes": RESIDENT_FONT_LOOKUP_SIZE,
            "status": "exact same-PC resident font lookup/render body",
        },
        "resident_font_blit_module": {
            "destination": "18:6454",
            "source": "35:6454",
            "bytes": RESIDENT_FONT_BLIT_SIZE,
            "status": "exact same-PC resident glyph compose/copy/blit module",
        },
        "resident_result_region_copy": {
            "destination": "18:66EE",
            "source": "35:66EE",
            "bytes": RESIDENT_RESULT_REGION_COPY_SIZE,
            "status": (
                "exact same-PC resident result-region bit/copy module"
            ),
        },
        "resident_region_compose_18": {
            "destination": "18:7A02",
            "source": "35:7A02",
            "bytes": RESIDENT_REGION_COMPOSE_18_SIZE,
            "status": "exact same-PC resident pixel/region compositor",
        },
        "resident_application_launch_manager_18": {
            "destination": "18:21F4",
            "source": "35:21F4",
            "bytes": RESIDENT_APPLICATION_LAUNCH_MANAGER_SIZE,
            "status": (
                "exact same-PC resident application selector/launcher with "
                "2F:E4C8 registry lookup"
            ),
        },
        "resident_menu_record_decode_11": {
            "destination": "11:5C12",
            "source": "2E:5C12",
            "bytes": RESIDENT_MENU_RECORD_DECODE_11_SIZE,
            "status": (
                "exact same-PC resident menu-page record decoder with "
                "30:FE0E memory-fill dependency"
            ),
        },
        "resident_menu_event_dispatch_18": {
            "destination": "18:9A58",
            "source": "35:9A58",
            "bytes": RESIDENT_MENU_EVENT_DISPATCH_SIZE,
            "status": (
                "exact same-PC resident 0x80..0x8e menu event dispatcher "
                "and jump table"
            ),
        },
        "resident_region_mask_18": {
            "destination": "18:A510",
            "source": "35:A510",
            "bytes": RESIDENT_REGION_MASK_18_SIZE,
            "status": "exact same-PC resident pixel/region mask compositor",
        },
        "resident_operation_context_18": {
            "destination": "18:CFA8",
            "source": "35:CFA8",
            "bytes": RESIDENT_OPERATION_CONTEXT_18_SIZE,
            "status": (
                "exact same-PC resident operation-0x0B object/resource "
                "initializer"
            ),
        },
        "resident_storage_init": {
            "destination": "1E:5084",
            "source": "3B:5084",
            "bytes": RESIDENT_STORAGE_INIT_SIZE,
            "status": "exact same-PC resident NAND/storage initialization body",
        },
        "resident_result_object_alloc": {
            "destination": "1E:6444",
            "source": "3B:6444",
            "bytes": RESIDENT_RESULT_OBJECT_ALLOC_SIZE,
            "status": "exact same-PC resident result-list object allocator",
        },
        "resident_result_type_query": {
            "destination": "1E:A4CE",
            "source": "3B:A4CE",
            "bytes": RESIDENT_RESULT_TYPE_QUERY_SIZE,
            "status": "exact same-PC resident resource-record type query",
        },
        "resident_record_status": {
            "destination": "1E:AB32",
            "source": "3B:AB32",
            "bytes": RESIDENT_RECORD_STATUS_SIZE,
            "arguments": ["record index word"],
            "result": "byte status in R0/RB1 (observed 1/4/5 family)",
            "status": "exact same-PC resident resource-record status worker",
        },
        "resident_application_config": {
            "destination": "1E:B7F6",
            "source": "3B:B7F6",
            "bytes": RESIDENT_APPLICATION_CONFIG_SIZE,
            "status": "exact same-PC resident application configuration body",
        },
        "resident_result_record_build": {
            "destination": "1E:C4AC",
            "source": "3B:C4AC",
            "bytes": RESIDENT_RESULT_RECORD_BUILD_SIZE,
            "status": "exact same-PC resident result record constructor",
        },
        "resident_object_table_update": {
            "destination": "1E:D15C",
            "source": "3B:D15C",
            "bytes": RESIDENT_OBJECT_TABLE_UPDATE_SIZE,
            "status": "exact same-PC resident call-free object-table update body",
        },
        "resident_result_record_compare": {
            "destination": "1F:DD42",
            "source": "3C:DD42",
            "bytes": RESIDENT_RESULT_RECORD_COMPARE_SIZE,
            "status": "exact same-PC resident result record comparator",
        },
        "resident_configuration_variants": [
            {
                "destination": (
                    f"{address >> 16:02X}:{address & 0xFFFF:04X}"
                ),
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": size,
                "status": "exact same-PC resident configuration variant",
            }
            for address, source, size, _name
            in RESIDENT_CONFIGURATION_VARIANTS
        ],
        "resident_application_state": {
            "destination": "1E:F734",
            "source": "3B:F734",
            "bytes": (len(resident_application_state_guard_words()) * 2
                      if probe_resident_app_state_guard
                      else RESIDENT_APPLICATION_STATE_SIZE),
            "status": (
                "exploratory guest-code initialization guard tail-calling "
                "the exact 3B:F734 dispatcher"
                if probe_resident_app_state_guard
                else "exact same-PC resident application-state dispatcher"
            ),
        },
        "resident_handler_1f_12b4": {
            "destination": "1F:12B4",
            "source": "3C:12B4",
            "bytes": RESIDENT_HANDLER_1F12B4_SIZE,
            "status": "exact same-PC resident application-record handler",
        },
        "resident_file_open_1f_1f1a": {
            "destination": "1F:1F1A",
            "source": "3C:1F1A",
            "bytes": RESIDENT_FILE_OPEN_1F1F1A_SIZE,
            "status": "exact same-PC resident filesystem open routine",
        },
        "application_file_record_attribute_test": {
            "destination": "5F:02D8",
            "linked_destination": "33:02D8",
            "source": "50:02D8",
            "bytes": APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_SIZE,
            "callers": ["1F:218E", "1F:21DE"],
            "status": (
                "exact source-50 file-record attribute test relocated around "
                "a live segment-33 code collision"
            ),
        },
        "resident_application_event_1f_b496": {
            "destination": "1F:B496",
            "source": "3C:B496",
            "bytes": RESIDENT_APPLICATION_EVENT_SIZE,
            "status": "exact same-PC resident application-event dispatcher",
        },
        "resident_resource_init_1b_ce3c": {
            "destination": "1B:CE3C",
            "source": "38:CE3C",
            "bytes": RESIDENT_RESOURCE_INIT_1BCE3C_SIZE,
            "status": "exact same-PC resident resource initialization body",
        },
        "resident_state_import": {
            "destination": "1F:F470",
            "source": "3C:F470",
            "bytes": RESIDENT_STATE_IMPORT_SIZE,
            "status": "exact same-PC resident application-state importer",
        },
        "memory_init_overlay": {
            "destination": "2C:9A7C",
            "source": "49:9A7C",
            "bytes": MEMORY_INIT_OVERLAY_SIZE,
            "status": "same-PC ABI-compatible clean-room reconstruction",
        },
        "text_draw_overlay": {
            "destination": "2E:5316",
            "source": "4B:5316",
            "bytes": TEXT_DRAW_OVERLAY_SIZE,
            "status": "same-PC four-argument clean-room reconstruction",
        },
        "resource_storage_lifecycle_overlays": [
            *[
                {
                    "destination": (
                        f"{destination >> 16:02X}:"
                        f"{destination & 0xFFFF:04X}"
                    ),
                    "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                    "bytes": size,
                    "installation": "guest byte-copy from immutable PRG bank",
                    "status": "exact same-PC resource/storage module",
                }
                for destination, source, size in
                APPLICATION_RESOURCE_STORAGE_COPY_OVERLAYS
            ],
            *[
                {
                    "destination": (
                        f"{destination >> 16:02X}:"
                        f"{destination & 0xFFFF:04X}"
                    ),
                    "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                    "bytes": size,
                    "installation": "exact PRG words embedded before segment-50 mutation",
                    "status": "exact same-PC resource/storage leaf",
                }
                for destination, source, size in
                APPLICATION_RESOURCE_STORAGE_EMBEDDED_OVERLAYS
            ],
            *[
                {
                    "destination": (
                        f"{destination >> 16:02X}:"
                        f"{destination & 0xFFFF:04X}"
                    ),
                    "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                    "bytes": size,
                    "installation": "exact PRG guest words in resident ROM",
                    "status": "source-proven collision-free file-driver module",
                }
                for destination, source, size in
                APPLICATION_FILE_DRIVER_CALLBACK_ROM_MODULES
            ],
        ],
        "nested_system_overlays": [
            {
                "destination": "33:305E",
                "source": "50:305E",
                "bytes": MODE_INIT_OVERLAY_SIZE,
                "status": "same-PC one-argument mode-initializer body",
            },
            {
                "destination": "33:180A",
                "source": "50:180A",
                "bytes": MODE_MASK_OVERLAY_SIZE,
                "status": "same-PC no-argument mode-mask body",
            },
            {
                "destination": "33:6030",
                "source": "50:6030",
                "bytes": SYSTEM_INIT_OVERLAY_SIZE,
                "status": (
                    "exact wrapper with its 33:5906 direct call relocated "
                    "to resident 06:1CE0"
                ),
            },
            {
                "destination": "06:1CE0",
                "source": "50:5906",
                "logical_collision": "33:5906 preserved as flat PRG code",
                "bytes": SYSTEM_BITS_OVERLAY_SIZE,
                "status": "exact no-argument bit-control body, relocated",
            },
            {
                "destination": "33:5B70",
                "source": "50:5B70",
                "bytes": APPLICATION_STATE_BYTE_OVERLAY_SIZE,
                "status": (
                    "same-PC no-argument application-state byte query; "
                    "flat target is an incompatible shared tail"
                ),
            },
            {
                "destination": "31:AF72",
                "source": "4E:AF72",
                "bytes": MEMORY_RESET_OVERLAY_SIZE,
                "status": "same-PC no-argument controller-reset body",
            },
            {
                "destination": "31:B014",
                "source": "4E:B014",
                "bytes": MEMORY_MODE_OVERLAY_SIZE,
                "status": "same-PC one-argument memory-mode body",
            },
            {
                "destination": "33:38D6",
                "source": "50:38D6",
                "bytes": GLOBAL_RESET_OVERLAY_SIZE,
                "status": "same-PC no-argument global-state reset body",
            },
            {
                "destination": "32:4218",
                "source": "4F:4218",
                "bytes": STARTUP_TABLE_OVERLAY_SIZE,
                "status": "same-PC no-argument startup-table body",
            },
            {
                "destination": "32:CC9C",
                "source": "4F:CC9C",
                "bytes": STARTUP_POINTER_OVERLAY_SIZE,
                "status": "same-PC no-argument startup-pointer body",
            },
            {
                "destination": "32:8EBE",
                "source": "4F:8EBE",
                "bytes": STARTUP_ARRAY_OVERLAY_SIZE,
                "status": "same-PC no-argument startup-array body",
            },
            {
                "destination": "31:4BAC",
                "source": "4E:4BAC",
                "bytes": STARTUP_RUNTIME_OVERLAY_SIZE,
                "status": "same-PC no-argument startup-runtime body",
            },
            {
                "destination": "31:A914",
                "source": "4E:A914",
                "bytes": APPLICATION_LCD_INIT_OVERLAY_SIZE,
                "status": "same-PC no-argument LCD/application initializer",
            },
            {
                "destination": "24:9BD4",
                "source": "41:9BD4",
                "bytes": PERIPHERAL_INIT_OVERLAY_SIZE,
                "status": "same-PC no-argument peripheral/SFR initializer",
            },
            {
                "destination": "30:9E30",
                "source": "4D:9E30",
                "bytes": ACTIVATION_CONTEXT_OVERLAY_SIZE,
                "status": "same-PC two-word activation-context function",
            },
            {
                "destination": "32:D530",
                "source": "4F:D530",
                "bytes": POINTER_SERVICE_OVERLAY_SIZE,
                "status": "same-PC three-word pointer-service wrapper",
            },
            {
                "destination": "33:5FD0",
                "source": "50:5FD0",
                "bytes": POINTER_STATE_OVERLAY_SIZE,
                "status": "same-PC no-argument pointer-state wrapper",
            },
            {
                "destination": "33:5C18",
                "source": "50:5C18",
                "bytes": POINTER_FLAG_OVERLAY_SIZE,
                "status": "same-PC no-argument pointer-flag getter",
            },
            {
                "destination": "33:4492",
                "source": "50:4492",
                "bytes": POINTER_NORMALIZE_OVERLAY_SIZE,
                "status": "same-PC one-word pointer-normalize wrapper",
            },
            {
                "destination": "31:F282",
                "source": "4E:F282",
                "bytes": POINTER_RESOLVE_OVERLAY_SIZE,
                "status": "same-PC three-word pointer-resolve function",
            },
            {
                "destination": "21:FD80",
                "source": "3E:FD80",
                "bytes": APPLICATION_DRAW_CONTEXT_OVERLAY_SIZE,
                "status": "same-PC drawing-context constructor",
            },
            {
                "destination": "32:A922",
                "source": "4F:A922",
                "bytes": APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_SIZE,
                "status": "same-PC far-comparison adapter",
            },
            {
                "destination": "27:507C",
                "source": "44:507C",
                "bytes": ACTIVATION_DISPATCH_OVERLAY_SIZE,
                "status": "same-PC four-word activation-dispatch function",
            },
            {
                "destination": "31:C0E8",
                "source": "4E:C0E8",
                "bytes": APPLICATION_PROPERTY_OVERLAY_SIZE,
                "status": "same-PC one-word application-property wrapper",
            },
            {
                "destination": "31:4D24",
                "source": "4E:4D24",
                "bytes": PROPERTY_SETTER_OVERLAY_SIZE,
                "status": "same-PC one-word property setter",
            },
            {
                "destination": "25:206E",
                "source": "42:206E",
                "bytes": LCD_RESOURCE_OVERLAY_SIZE,
                "status": "same-PC five-word LCD/resource function",
            },
            {
                "destination": "2D:261C",
                "source": "4A:261C",
                "bytes": APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SIZE,
                "status": (
                    "exact framed logical-resource page reader feeding the "
                    "restored 2C:2EBA FTL/NAND sector path"
                ),
            },
            {
                "destination": "30:D350",
                "source": "4D:D350",
                "bytes": LCD_TIMING_OVERLAY_SIZE,
                "status": "same-PC no-argument LCD/timing initializer",
            },
            {
                "destination": "30:8C1C",
                "source": "4D:8C1C",
                "bytes": APPLICATION_STATE_OVERLAY_SIZE,
                "status": "same-PC no-argument application-state initializer",
            },
            {
                "destination": "30:FE0E",
                "source": "4D:FE0E",
                "bytes": MEMORY_FILL_OVERLAY_SIZE,
                "status": "same-PC five-word memory-fill body and local helper",
            },
            {
                "destination": "32:9B56",
                "source": "4F:9B56",
                "bytes": APPLICATION_RANGE_OVERLAY_SIZE,
                "status": "same-PC two-word application-range function",
            },
            {
                "destination": "31:5EA0",
                "source": "4E:5EA0",
                "bytes": APPLICATION_TABLE_INIT_OVERLAY_SIZE,
                "status": "same-PC no-argument application-table initializer",
            },
            {
                "destination": "32:6358",
                "source": "4F:6358",
                "bytes": APPLICATION_TABLE_CLEAR_OVERLAY_SIZE,
                "status": "same-PC no-argument application-table clear",
            },
            {
                "destination": "32:2520",
                "source": "4F:2520",
                "bytes": APPLICATION_BUFFER_COPY_OVERLAY_SIZE,
                "status": "same-PC four-word application-buffer copy",
            },
            {
                "destination": "2F:5B98",
                "source": "4C:5B98",
                "bytes": APPLICATION_COMMAND_OVERLAY_SIZE,
                "status": "same-PC one-word application-command dispatcher",
            },
            {
                "destination": "31:5BB8",
                "source": "4E:5BB8",
                "bytes": COMMAND_TABLE_PRIMARY_OVERLAY_SIZE,
                "status": "same-PC one-word primary command-table builder",
            },
            {
                "destination": "31:5A44",
                "source": "4E:5A44",
                "bytes": COMMAND_TABLE_SECONDARY_OVERLAY_SIZE,
                "status": "same-PC one-word secondary command-table builder",
            },
            {
                "destination": "31:598A",
                "source": "4E:598A",
                "bytes": COMMAND_TABLE_TERTIARY_OVERLAY_SIZE,
                "status": "same-PC one-word tertiary command-table builder",
            },
            {
                "destination": "31:58D0",
                "source": "4E:58D0",
                "bytes": APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_SIZE,
                "status": (
                    "exact framed root static-display step preserving the "
                    "controller return to 1D:F63C"
                ),
            },
            {
                "destination": "31:552E",
                "source": "4E:552E",
                "bytes": APPLICATION_ROOT_STREAM_WRITE_OVERLAY_SIZE,
                "status": (
                    "exact framed root status stream writer replacing the "
                    "flat one-instruction no-op"
                ),
            },
            {
                "destination": "22:BE8A",
                "source": "3F:BE8A",
                "bytes": APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_SIZE,
                "status": (
                    "exact framed root status stream dispatcher replacing "
                    "the flat mid-function entry"
                ),
            },
            {
                "destination": "30:6490",
                "source": "4D:6490",
                "bytes": APPLICATION_ROOT_STREAM_MOVE_OVERLAY_SIZE,
                "status": (
                    "exact framed root stream fragment mover called by "
                    "22:C062, embedded before source bank 4D is reused"
                ),
            },
            {
                "destination": "31:1122",
                "source": "4E:1122",
                "bytes": APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_SIZE,
                "status": (
                    "exact framed root printf marker scanner replacing the "
                    "flat function epilogue"
                ),
            },
            {
                "destination": "2F:D266",
                "source": "4C:D266",
                "bytes": APPLICATION_ROOT_ITEM_MASK_OVERLAY_SIZE,
                "status": (
                    "exact framed root item-mask initializer preserving the "
                    "controller return after 1D:F900"
                ),
            },
            {
                "destination": "32:9A9A",
                "source": "4F:9A9A",
                "bytes": APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_SIZE,
                "status": (
                    "exact framed root hardware-state reset preserving the "
                    "controller's saved object pointer"
                ),
            },
            {
                "destination": "26:CF40",
                "source": "43:CF40",
                "bytes": APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_SIZE,
                "status": (
                    "exact framed four-argument root bitmap renderer "
                    "replacing flat resource data"
                ),
            },
            {
                "destination": "2F:6BFA",
                "source": "4C:6BFA",
                "bytes": COMMAND_TABLE_TEMPLATE_OVERLAY_SIZE,
                "status": "shared 32-entry command-table data template",
            },
            {
                "destination": "30:D6D0",
                "source": "4D:D6D0",
                "bytes": COMMAND_MATRIX_OVERLAY_SIZE,
                "status": "same-PC two-word command-matrix initializer",
            },
            {
                "destination": "32:CA88",
                "source": "4F:CA88",
                "bytes": APPLICATION_MODE_OVERLAY_SIZE,
                "status": "same-PC one-word application-mode setter",
            },
            {
                "destination": "32:9D22",
                "source": "4F:9D22",
                "bytes": APPLICATION_SLOT_OVERLAY_SIZE,
                "status": "same-PC two-word application-slot setter",
            },
            {
                "destination": "32:2102",
                "source": "4F:2102",
                "bytes": APPLICATION_TRIPLE_OVERLAY_SIZE,
                "status": "same-PC three-word application-state setter",
            },
            {
                "destination": "33:3376",
                "source": "50:3376",
                "bytes": APPLICATION_HW_STATE_OVERLAY_SIZE,
                "status": "embedded same-PC no-argument hardware-state query",
            },
            {
                "destination": "33:063A",
                "source": "50:063A",
                "bytes": APPLICATION_POWER_STATE_OVERLAY_SIZE,
                "status": "embedded same-PC no-argument power-state query",
            },
            {
                "destination": "29:13DC",
                "source": "46:13DC",
                "bytes": APPLICATION_PAGE_SETUP_OVERLAY_SIZE,
                "status": "same-PC one-word application-page setup",
            },
            {
                "destination": "28:1F08",
                "source": "45:1F08",
                "bytes": APPLICATION_TEXT_LOOP_OVERLAY_SIZE,
                "status": "same-PC four-word application-text loop",
            },
            {
                "destination": "25:CC94",
                "source": "42:CC94",
                "bytes": APPLICATION_RESOURCE_LOOP_OVERLAY_SIZE,
                "status": (
                    "same-PC application resource/event-loop worker with "
                    "its 33:5906 direct call relocated to 06:1CE0"
                ),
            },
            {
                "destination": "25:5460",
                "source": "42:5460",
                "bytes": APPLICATION_STORAGE_CONTEXT_OVERLAY_SIZE,
                "status": "exact same-PC storage-context initializer",
            },
            {
                "destination": "25:5858",
                "source": "42:5858",
                "bytes": APPLICATION_STORAGE_REGISTRY_OVERLAY_SIZE,
                "status": "same-PC storage-registry initializer",
            },
            {
                "destination": "24:236A",
                "source": "41:236A",
                "bytes": STORAGE_BAD_BLOCK_STATUS_OVERLAY_SIZE,
                "status": "exact same-PC NAND OOB/bad-block status decoder",
            },
            {
                "destination": "30:A3C2",
                "source": "4D:A3C2",
                "bytes": APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_SIZE,
                "status": "same-PC storage-unit open/status helper",
            },
            {
                "destination": "18:F97C",
                "source": "35:F97C",
                "bytes": RESIDENT_STORAGE_UNIT_INIT_OVERLAY_SIZE,
                "status": (
                    "exact same-PC post-scan storage-unit runtime-record "
                    "initializer"
                ),
            },
            {
                "destination": "2C:FE08",
                "source": "49:FE08",
                "bytes": STORAGE_UNIT_WORKER_OVERLAY_SIZE,
                "status": (
                    "exact framed per-unit storage worker with balanced "
                    "normal and callback returns"
                ),
            },
            {
                "destination": "31:CBE8",
                "source": "4E:CBE8",
                "bytes": STORAGE_PACKED_FIELD_OVERLAY_SIZE,
                "status": "exact packed two-field decoder",
            },
            {
                "destination": "32:6EA8",
                "source": "4F:6EA8",
                "bytes": STORAGE_SECONDARY_DRIVER_OVERLAY_SIZE,
                "status": "exact secondary storage-driver wrapper",
            },
            {
                "destination": "32:6F12",
                "source": "4F:6F12",
                "bytes": STORAGE_PRIMARY_READER_OVERLAY_SIZE,
                "status": "exact primary one-byte storage-reader wrapper",
            },
            {
                "destination": "2E:BF9A",
                "source": "4B:BF9A",
                "bytes": STORAGE_TRANSFER_WORKER_OVERLAY_SIZE,
                "status": "exact framed storage-transfer worker",
            },
            {
                "destination": "2E:C104",
                "source": "4B:C104",
                "bytes": STORAGE_PRIMARY_TRANSFER_OVERLAY_SIZE,
                "status": "exact framed primary storage-transfer worker",
            },
            {
                "destination": "2C:2EBA",
                "source": "49:2EBA",
                "bytes": STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SIZE,
                "status": "exact framed primary storage sector reader",
            },
            {
                "destination": "2A:1440",
                "source": "47:1440",
                "bytes": STORAGE_NAND_STATUS_OVERLAY_SIZE,
                "status": "exact framed NAND status and retry helper",
            },
            {
                "destination": "29:05B0",
                "source": "46:05B0",
                "bytes": STORAGE_BLOCK_TRANSFER_OVERLAY_SIZE,
                "status": "exact framed storage block-transfer implementation",
            },
            {
                "destination": "33:091C",
                "source": "50:091C",
                "bytes": STORAGE_RECORD_CALLBACK_OVERLAY_SIZE,
                "status": (
                    "exact three-word indirect storage-record callback with "
                    "balanced LINK/UNLINK frame"
                ),
            },
            {
                "destination": "33:6E5E",
                "source": "50:6E5E",
                "bytes": STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_SIZE,
                "status": (
                    "exact LINK/UNLINK/RETS service called by the indirect "
                    "storage-record callback"
                ),
            },
            {
                "destination": "5F:13F8",
                "source": "50:13F8",
                "bytes": STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_SIZE,
                "status": (
                    "exact storage-record capacity service with its sole "
                    "collision-prone child retargeted"
                ),
            },
            {
                "destination": "5F:661A",
                "source": "50:661A",
                "bytes": STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_SIZE,
                "status": (
                    "exact record capacity wrapper retargeted to the "
                    "collision-free capacity service"
                ),
            },
            {
                "destination": "5F:6DA0",
                "source": "4F:6B58",
                "bytes": STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SIZE,
                "status": "exact call-free storage capacity calculation",
            },
            {
                "destination": "33:0070",
                "source": "50:0070",
                "bytes": STORAGE_RECORD_POST_LOOKUP_OVERLAY_SIZE,
                "status": (
                    "exact post-lookup pointer/text wrapper with balanced "
                    "LINK/UNLINK frame"
                ),
            },
            {
                "destination": "2C:F6A6",
                "source": "49:F6A6",
                "bytes": STORAGE_ASYNC_RANGE_OVERLAY_SIZE,
                "status": (
                    "exact seven-word async storage range validator with "
                    "balanced LINK/UNLINK frame"
                ),
            },
            {
                "destination": "32:EC6E",
                "source": "4F:EC6E",
                "bytes": STORAGE_RANGE_DISPATCH_OVERLAY_SIZE,
                "status": (
                    "exact four-word storage range adapter with balanced "
                    "LINK/UNLINK frame"
                ),
            },
            {
                "destination": "2C:38C0",
                "source": "49:38C0",
                "bytes": STORAGE_FIELD_PARSE_OVERLAY_SIZE,
                "status": (
                    "exact eight-word storage field parser with balanced "
                    "LINK/UNLINK frame"
                ),
            },
            {
                "destination": "30:DA48",
                "source": "4D:DA48",
                "bytes": STORAGE_BUFFER_DECODE_OVERLAY_SIZE,
                "status": (
                    "exact one-pointer 0x800-byte storage buffer decoder "
                    "with balanced LINK/UNLINK frame"
                ),
            },
            {
                "destination": "32:0B6A",
                "source": "4F:0B6A",
                "bytes": STORAGE_EVENT_POLL_OVERLAY_SIZE,
                "status": (
                    "exact no-argument storage/event input filter with "
                    "balanced LINK/UNLINK frame"
                ),
            },
            {
                "destination": "32:082E",
                "source": "4F:082E",
                "bytes": STORAGE_RECORD_DISPATCH_OVERLAY_SIZE,
                "status": (
                    "exact seven-word storage-record dispatch adapter with "
                    "balanced LINK/UNLINK frame"
                ),
            },
            {
                "destination": "5F:6BB2",
                "source": "50:6BB2",
                "bytes": 0x0008,
                "status": (
                    "exact timer-idle register-bit set helper relocated to "
                    "preserve the live segment-33 renderer fall-through"
                ),
                "linked_destination": "33:6BB2",
                "caller_patch": "30:4844 SCALL 33:6BB2 -> 5F:6BB2",
            },
            {
                "destination": "5F:6BBA",
                "source": "50:6BBA",
                "bytes": 0x0008,
                "status": (
                    "exact timer-idle register-bit set helper relocated to "
                    "preserve the live segment-33 renderer fall-through"
                ),
                "linked_destination": "33:6BBA",
                "caller_patch": "30:484C SCALL 33:6BBA -> 5F:6BBA",
            },
            {
                "destination": "5F:6C2A",
                "source": "50:6C2A",
                "bytes": 0x0008,
                "status": (
                    "exact timer-idle register-bit clear helper relocated "
                    "to preserve the live segment-33 renderer fall-through"
                ),
                "linked_destination": "33:6C2A",
                "caller_patch": "30:487A SCALL 33:6C2A -> 5F:6C2A",
            },
            {
                "destination": "5F:6C32",
                "source": "50:6C32",
                "bytes": 0x0008,
                "status": (
                    "exact timer-idle register-bit clear helper relocated "
                    "to preserve the live segment-33 renderer fall-through"
                ),
                "linked_destination": "33:6C32",
                "caller_patch": "30:4882 SCALL 33:6C32 -> 5F:6C32",
            },
            {
                "destination": "5F:6BF2",
                "source": "50:6BF2",
                "bytes": STORAGE_RECORD_ACCEPT_OVERLAY_SIZE,
                "status": (
                    "exact no-argument constant-one storage-record "
                    "predicate relocated to preserve the live 33:6BB2 "
                    "fall-through"
                ),
                "linked_destination": "33:6BF2",
                "caller_patches": [
                    "32:BEDA SCALL 33:6BF2 -> 5F:6BF2",
                    "33:04C4 SCALL 33:6BF2 -> 5F:6BF2",
                ],
            },
            {
                "destination": "20:81E0",
                "source": "3D:81E0",
                "bytes": APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SIZE,
                "status": (
                    "exact one-pointer result-record parser with balanced "
                    "LINK/UNLINK frame"
                ),
            },
            {
                "destination": "32:8524",
                "source": "4F:8524",
                "bytes": APPLICATION_RESULT_REGION_PREPARE_OVERLAY_SIZE,
                "status": (
                    "exact three-word result-region preparation adapter with "
                    "balanced LINK/UNLINK frame"
                ),
            },
            {
                "destination": "31:C7A4",
                "source": "4E:C7A4",
                "bytes": APPLICATION_RESULT_DISPLAY_SETUP_OVERLAY_SIZE,
                "status": (
                    "exact result-display setup with a balanced LINK #0x16 "
                    "frame"
                ),
            },
            {
                "destination": "32:BB60",
                "source": "4F:BB60",
                "bytes": APPLICATION_RESULT_RESOURCE_RESET_OVERLAY_SIZE,
                "status": (
                    "exact no-argument six-resource reset helper with a "
                    "balanced frame"
                ),
            },
            {
                "destination": "28:5902",
                "source": "45:5902",
                "bytes": APPLICATION_RESULT_BUILD_OVERLAY_SIZE,
                "status": (
                    "exact seven-word result-construction worker with a "
                    "balanced LINK #8 frame"
                ),
            },
            {
                "destination": "2C:48A8",
                "source": "49:48A8",
                "bytes": FAR_NORMALIZED_MEMORY_COMPARE_OVERLAY_SIZE,
                "status": (
                    "exact two-pointer bounded normalized comparison with "
                    "balanced selector/register saves"
                ),
            },
            {
                "destination": "25:E324",
                "source": "42:E324",
                "bytes": APPLICATION_STORAGE_ENTRY_ATTACH_OVERLAY_SIZE,
                "status": "same-PC storage-entry attach helper",
            },
            {
                "destination": "33:2EAE",
                "source": "50:2EAE",
                "bytes": APPLICATION_DEVICE_QUERY_OVERLAY_SIZE,
                "status": "embedded same-PC device-state query",
            },
            {
                "destination": "31:F670",
                "source": "4E:F670",
                "bytes": APPLICATION_POINTER_UPDATE_OVERLAY_SIZE,
                "status": "same-PC application pointer-state updater",
            },
            {
                "destination": "32:AFEE",
                "source": "4F:AFEE",
                "bytes": STORAGE_RUNTIME_STATE_RESET_OVERLAY_SIZE,
                "status": "same-PC storage runtime-state reset helper",
            },
            {
                "destination": "32:FA40",
                "source": "4F:FA40",
                "bytes": STORAGE_RUNTIME_TABLE_RESET_OVERLAY_SIZE,
                "status": "same-PC storage runtime-table reset helper",
            },
            {
                "destination": "33:2ED2",
                "source": "50:2ED2",
                "bytes": APPLICATION_DEVICE_APPLY_OVERLAY_SIZE,
                "status": "embedded same-PC device-state apply wrapper",
            },
            {
                "destination": "24:BD76",
                "source": "41:BD76",
                "bytes": APPLICATION_STORAGE_MAINTENANCE_OVERLAY_SIZE,
                "status": "same-PC NAND metadata maintenance worker",
            },
            {
                "destination": "33:71CE",
                "source": "burner NAND-ID 0xDC / extended 0x95 geometry branch",
                "bytes": STORAGE_GEOMETRY_DATA_OVERLAY_SIZE,
                "status": "clean-room reconstructed NAND geometry data block",
            },
            {
                "destination": "27:0000",
                "source": "44:0000",
                "bytes": APPLICATION_STORAGE_BLOCK_OVERLAY_SIZE,
                "status": "same-PC NAND logical-block maintenance worker",
            },
            {
                "destination": "27:287C",
                "source": "44:287C",
                "bytes": APPLICATION_STORAGE_SCAN_OVERLAY_SIZE,
                "status": "same-PC framed storage/resource scan; replaces a flat invalid conditional-call fragment",
            },
            {
                "destination": "2B:4C0A",
                "source": "48:4C0A",
                "bytes": APPLICATION_STORAGE_VERIFY_OVERLAY_SIZE,
                "status": "same-PC NAND record verification worker",
            },
            {
                "destination": "31:8C18",
                "source": "4E:8C18",
                "bytes": APPLICATION_STORAGE_TRANSFER_OVERLAY_SIZE,
                "status": "same-PC NAND transfer/checksum helper",
            },
            {
                "destination": "28:CC5A",
                "source": "45:CC5A",
                "bytes": APPLICATION_STORAGE_MAP_OVERLAY_SIZE,
                "status": "same-PC NAND logical-to-physical map reader",
            },
            {
                "destination": "30:3E86",
                "source": "4D:3E86",
                "bytes": APPLICATION_STATE_DISPATCH_OVERLAY_SIZE,
                "status": "same-PC resident-state dispatch wrapper",
            },
            {
                "destination": "28:82F4",
                "source": "45:82F4",
                "bytes": APPLICATION_STATE_PREPARE_OVERLAY_SIZE,
                "status": "same-PC application-state pointer preparation",
            },
            {
                "destination": "29:8CAA",
                "source": "46:8CAA",
                "bytes": APPLICATION_STATE_POINTER_OVERLAY_SIZE,
                "status": "same-PC application-state pointer resolver",
            },
            {
                "destination": "29:24C6",
                "source": "46:24C6",
                "bytes": APPLICATION_STATE_RECORD_OVERLAY_SIZE,
                "status": "same-PC application-state record translator",
            },
            {
                "destination": "31:9C1E",
                "source": "4E:9C1E",
                "bytes": APPLICATION_STATE_CLASSIFY_OVERLAY_SIZE,
                "status": "same-PC application-state classifier",
            },
            {
                "destination": "2F:3A48",
                "source": "4C:3A48",
                "bytes": APPLICATION_STATE_SERVICE_OVERLAY_SIZE,
                "status": "same-PC resident application-state service",
            },
            {
                "destination": "22:FD9E",
                "source": "3F:FD9E",
                "bytes": APPLICATION_STATE_TRANSFORM_OVERLAY_SIZE,
                "status": "same-PC application-state record transformer",
            },
            {
                "destination": "31:D9AA",
                "source": "4E:D9AA",
                "bytes": APPLICATION_STATE_FLAGS_OVERLAY_SIZE,
                "status": "same-PC application-state flag initializer",
            },
            {
                "destination": "2D:2D40",
                "source": "4A:2D40",
                "bytes": APPLICATION_STATE_POWER_OVERLAY_SIZE,
                "status": "same-PC application power/reset-state worker",
            },
            {
                "destination": "2F:FA32",
                "source": "4C:FA32",
                "bytes": APPLICATION_STATE_TICK_OVERLAY_SIZE,
                "status": "same-PC application state/timer worker",
            },
            {
                "destination": "22:F40C",
                "source": "3F:F40C",
                "bytes": APPLICATION_STATE_UI_OVERLAY_SIZE,
                "status": "same-PC application state/UI dispatcher",
            },
            {
                "destination": "5F:C336",
                "linked_destination": "32:C336",
                "source": "4F:C336",
                "bytes": APPLICATION_STATE_ADC_OVERLAY_SIZE,
                "caller_patch": "22:F430 SCALL 32:C336 -> 5F:C336",
                "status": "exact application hardware-state sampler relocated to preserve the simultaneously live flat 32:C0xx state machine",
            },
            {
                "destination": "33:5D76",
                "source": "50:5D76",
                "bytes": APPLICATION_STATE_MODE_OVERLAY_SIZE,
                "status": "embedded same-PC application-state mode query",
            },
            {
                "destination": "33:317E",
                "source": "50:317E",
                "bytes": APPLICATION_EVENT_INDEX_OVERLAY_SIZE,
                "status": "embedded same-PC application event-index formatter",
            },
            {
                "destination": "32:78DE",
                "source": "4F:78DE",
                "bytes": APPLICATION_WIDE_CONVERT_OVERLAY_SIZE,
                "status": "same-PC call-free wide-value converter",
            },
            {
                "destination": "32:2728",
                "source": "4F:2728",
                "bytes": APPLICATION_MODAL_VALIDATION_OVERLAY_SIZE,
                "status": "same-PC post-modal validation dispatcher; replaces a flat language/data table",
            },
            {
                "destination": "27:4330",
                "source": "44:4330",
                "bytes": APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_SIZE,
                "status": "same-PC framed validation-mode jump-table dispatcher",
            },
            {
                "destination": "2F:4EDC",
                "source": "4C:4EDC",
                "bytes": APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_SIZE,
                "status": "same-PC in-place modal text normalizer",
            },
            {
                "destination": "2F:9844",
                "source": "4C:9844",
                "bytes": APPLICATION_MODAL_TEXT_FILTER_OVERLAY_SIZE,
                "status": "same-PC modal text filtering worker",
            },
            {
                "destination": "30:409E",
                "source": "4D:409E",
                "bytes": APPLICATION_MODAL_BUFFER_READ_OVERLAY_SIZE,
                "status": "same-PC resource-backed modal buffer reader",
            },
            {
                "destination": "32:136C",
                "source": "4F:136C",
                "bytes": APPLICATION_COMPARE_MODE_OVERLAY_SIZE,
                "status": "same-PC framed application compare/mode wrapper; replaces a frame-leaking flat large-function middle",
            },
            {
                "destination": "31:5300",
                "source": "4E:5300",
                "bytes": APPLICATION_CONTEXT_LOOKUP_OVERLAY_SIZE,
                "status": "same-PC application context/registry lookup",
            },
            {
                "destination": "32:2396",
                "source": "4F:2396",
                "bytes": APPLICATION_CONTEXT_PROPERTY_OVERLAY_SIZE,
                "status": "same-PC application context-property mapper",
            },
            {
                "destination": "33:1A02",
                "source": "50:1A02",
                "bytes": APPLICATION_EVENT_CLASSIFY_OVERLAY_SIZE,
                "status": "same-PC application event/letter predicate",
            },
            {
                "destination": "32:773A",
                "source": "4F:773A",
                "bytes": APPLICATION_WIDE_GATE_OVERLAY_SIZE,
                "status": "exact tail trampoline to 2F:C216",
            },
            {
                "destination": "33:0070",
                "source": "50:0070",
                "bytes": APPLICATION_TEXT_DISPATCH_OVERLAY_SIZE,
                "status": "embedded same-PC application text-dispatch wrapper",
            },
            {
                "destination": "33:00A8",
                "source": "50:00A8",
                "bytes": APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SIZE,
                "status": "embedded same-PC F0 text-dispatch wrapper",
            },
            {
                "destination": "30:0C24",
                "source": "4D:0C24",
                "bytes": APPLICATION_INDEX_ACTION_OVERLAY_SIZE,
                "status": "same-PC indexed application action dispatcher",
            },
            {
                "destination": "30:14E4",
                "source": "4D:14E4",
                "bytes": APPLICATION_PAGE_INDEX_OVERLAY_SIZE,
                "status": "same-PC framed application page-index action",
            },
            {
                "destination": "30:15FC",
                "source": "4D:15FC",
                "bytes": APPLICATION_PAGE_FETCH_OVERLAY_SIZE,
                "status": "same-PC framed application page-data fetch",
            },
            {
                "destination": "30:1A54",
                "source": "4D:1A54",
                "bytes": APPLICATION_RECT_DRAW_OVERLAY_SIZE,
                "status": "same-PC framed application rectangle renderer",
            },
            {
                "destination": "26:0000",
                "source": "43:0000",
                "bytes": APPLICATION_IMAGE_WINDOW_OVERLAY_SIZE,
                "status": "same-PC framed application image-window worker",
            },
            {
                "destination": "33:65FC",
                "source": "50:65FC",
                "bytes": APPLICATION_STATE_COMMIT_OVERLAY_SIZE,
                "status": "same-PC framed application state-commit wrapper",
            },
            {
                "destination": "27:A8B6",
                "source": "44:A8B6",
                "bytes": APPLICATION_IMAGE_DISPATCH_OVERLAY_SIZE,
                "status": "same-PC framed application image dispatcher",
            },
            {
                "destination": "2E:FC6A",
                "source": "4B:FC6A",
                "bytes": APPLICATION_EVENT_POLL_OVERLAY_SIZE,
                "status": "same-PC application event polling loop",
            },
            {
                "destination": "33:463E",
                "source": "50:463E",
                "bytes": APPLICATION_EVENT_CONTROL_OVERLAY_SIZE,
                "status": "embedded same-PC event-control wrapper",
            },
            {
                "destination": "31:7286",
                "source": "4E:7286",
                "bytes": APPLICATION_TIMER_SETUP_OVERLAY_SIZE,
                "status": "same-PC application timer setup",
            },
            {
                "destination": "33:1DF6",
                "source": "50:1DF6",
                "bytes": APPLICATION_OBJECT_RELEASE_OVERLAY_SIZE,
                "status": "embedded same-PC menu object release wrapper",
            },
            {
                "destination": "33:1F4E",
                "source": "50:1F4E",
                "bytes": APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SIZE,
                "status": "embedded same-PC base-10 parser wrapper",
            },
            {
                "destination": "32:F7FC",
                "source": "4F:F7FC",
                "bytes": APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SIZE,
                "status": "embedded same-PC generic parser core",
            },
            {
                "destination": "24:2C32",
                "source": "41:2C32",
                "bytes": APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SIZE,
                "status": "embedded same-PC sign/radix parser engine",
            },
            {
                "destination": "33:3BE6",
                "source": "50:3BE6",
                "bytes": APPLICATION_ASCII_WHITESPACE_OVERLAY_SIZE,
                "status": "embedded same-PC ASCII whitespace classifier",
            },
            {
                "destination": "33:249A",
                "source": "50:249A",
                "bytes": UINT32_MODULO_WRAPPER_OVERLAY_SIZE,
                "status": "embedded same-PC unsigned remainder wrapper",
            },
            {
                "destination": "33:24C2",
                "source": "50:24C2",
                "bytes": INT32_MODULO_WRAPPER_OVERLAY_SIZE,
                "status": "embedded same-PC signed remainder wrapper",
            },
            {
                "destination": "33:24EA",
                "source": "50:24EA",
                "bytes": UINT32_DIVIDE_WRAPPER_OVERLAY_SIZE,
                "status": "embedded same-PC unsigned division wrapper",
            },
            {
                "destination": "31:6A14",
                "source": "4E:6A14",
                "bytes": UINT32_DIVIDE_OVERLAY_SIZE,
                "status": "same-PC unsigned division helper",
            },
            {
                "destination": "33:2F1A",
                "source": "50:2F1A",
                "bytes": UINT32_MSB_INDEX_OVERLAY_SIZE,
                "status": "exact same-PC unsigned highest-set-bit helper",
            },
            {
                "destination": "33:2F3E",
                "source": "50:2F3E",
                "bytes": UINT32_NORMALIZE_OVERLAY_SIZE,
                "status": "embedded same-PC unsigned normalization helper",
            },
            {
                "destination": "23:A38C",
                "source": "40:A38C",
                "bytes": APPLICATION_CONTEXT_LAUNCH_OVERLAY_SIZE,
                "status": (
                    "exact same-PC application context/launch selector"
                ),
            },
            {
                "destination": "29:8202",
                "source": "46:8202",
                "bytes": APPLICATION_RECORD_PREPARE_OVERLAY_SIZE,
                "status": "same-PC application record preparation body",
            },
            {
                "destination": "30:C8C0",
                "source": "4D:C8C0",
                "bytes": APPLICATION_ADDRESS_RESOLVE_OVERLAY_SIZE,
                "status": "same-PC application address resolver",
            },
            {
                "destination": "33:048A",
                "source": "50:048A",
                "bytes": APPLICATION_RECORD_DISPATCH_OVERLAY_SIZE,
                "status": "embedded same-PC application record dispatcher",
            },
            {
                "destination": "31:AED0",
                "source": "4E:AED0",
                "bytes": FAR_STRING_LENGTH_OVERLAY_SIZE,
                "status": "same-PC far-string length helper",
            },
            {
                "destination": "27:716C",
                "source": "44:716C",
                "bytes": APPLICATION_RECORD_SCAN_OVERLAY_SIZE,
                "status": "same-PC application record scanning body",
            },
            {
                "destination": "30:FE0E",
                "source": "4D:FE0E",
                "bytes": FAR_MEMORY_FILL_OVERLAY_SIZE,
                "status": "same-PC far-memory fill helper",
            },
            {
                "destination": "31:3A72",
                "source": "4E:3A72",
                "bytes": PACKED_TRIPLE_READ_OVERLAY_SIZE,
                "status": "same-PC packed three-byte reader",
            },
            {
                "destination": "32:C9F0",
                "source": "4F:C9F0",
                "bytes": APPLICATION_COMPARE_WRAPPER_OVERLAY_SIZE,
                "status": "same-PC application compare wrapper",
            },
            {
                "destination": "2C:C07E",
                "source": "49:C07E",
                "bytes": FAR_MEMORY_COMPARE_OVERLAY_SIZE,
                "status": "same-PC recursive far-memory compare helper",
            },
            {
                "destination": "32:F43E",
                "source": "4F:F43E",
                "bytes": FAR_POINTER_NORMALIZE_OVERLAY_SIZE,
                "status": "same-PC far-pointer normalization helper",
            },
            {
                "destination": "32:945C",
                "source": "4F:945C",
                "bytes": FAR_STRING_COPY_OVERLAY_SIZE,
                "status": "same-PC far-string copy selected by 03:407C",
            },
            {
                "destination": "2E:4572",
                "source": "4B:4572",
                "bytes": FAR_MEMORY_COPY_OVERLAY_SIZE,
                "status": "same-PC recursive far-memory copy helper",
            },
            {
                "destination": "28:FD38",
                "source": "45:FD38",
                "bytes": APPLICATION_GLYPH_DRAW_OVERLAY_SIZE,
                "status": "same-PC three-argument glyph renderer",
            },
            {
                "destination": "32:7C0E",
                "source": "4F:7C0E",
                "bytes": CHARACTER_DRAW_OVERLAY_SIZE,
                "status": "same-PC character draw dispatcher",
            },
            {
                "destination": "32:8204",
                "source": "4F:8204",
                "bytes": FAR_STRING_CONCAT_OVERLAY_SIZE,
                "status": "same-PC far-string concatenation helper",
            },
            {
                "destination": "32:8268",
                "source": "4F:8268",
                "bytes": RECORD_LAYOUT_WRAPPER_OVERLAY_SIZE,
                "status": "same-PC seven-word record-layout wrapper",
            },
            {
                "destination": "22:FD9E",
                "source": "3F:FD9E",
                "bytes": RECORD_LAYOUT_BUILD_OVERLAY_SIZE,
                "status": "same-PC record-layout builder",
            },
            {
                "destination": "31:C224",
                "source": "4E:C224",
                "bytes": APPLICATION_INPUT_MASK_OVERLAY_SIZE,
                "status": "same-PC one-word input-mask dispatcher",
            },
            {
                "destination": "31:5014",
                "source": "4E:5014",
                "bytes": INPUT_MASK_APPLY_OVERLAY_SIZE,
                "status": "same-PC input table-bit updater",
            },
            {
                "destination": "30:8C1C",
                "source": "4D:8C1C",
                "bytes": APPLICATION_DISPLAY_STATE_OVERLAY_SIZE,
                "status": "same-PC application display-state initializer",
            },
            {
                "destination": "32:8E5C",
                "source": "4F:8E5C",
                "bytes": APPLICATION_DISPLAY_RESET_OVERLAY_SIZE,
                "status": "same-PC framed display/mode reset wrapper; replaces a flat suffix with an unbalanced return",
            },
            {
                "destination": "30:8B26",
                "source": "4D:8B26",
                "bytes": APPLICATION_LIST_STATE_OVERLAY_SIZE,
                "status": "same-PC application list-state worker",
            },
            {
                "destination": "30:3A56",
                "source": "4D:3A56",
                "bytes": APPLICATION_LIST_ITEM_SET_OVERLAY_SIZE,
                "status": "same-PC framed list-item setter; replaces a flat function middle whose shared epilogue skipped its caller frame",
            },
            {
                "destination": "31:8ABC",
                "source": "4E:8ABC",
                "bytes": APPLICATION_TABLE_MASK_OVERLAY_SIZE,
                "status": "same-PC application table-mask updater",
            },
            {
                "destination": "27:6100",
                "source": "44:6100",
                "bytes": APPLICATION_LIST_COMPACT_OVERLAY_SIZE,
                "status": "same-PC application list compaction worker",
            },
            {
                "destination": "30:699A",
                "source": "4D:699A",
                "bytes": APPLICATION_LIST_CURSOR_OVERLAY_SIZE,
                "status": "same-PC application list cursor resolver",
            },
            {
                "destination": "32:3332",
                "source": "4F:3332",
                "bytes": APPLICATION_RANGE_FLAG_OVERLAY_SIZE,
                "status": "same-PC application range-flag scanner",
            },
            {
                "destination": "2A:A6F6",
                "source": "47:A6F6",
                "bytes": APPLICATION_DEVICE_VALIDATION_OVERLAY_SIZE,
                "status": "same-PC application device-validation worker",
            },
            {
                "destination": "24:EAEC",
                "source": "41:EAEC",
                "bytes": APPLICATION_RESOURCE_LOOKUP_OVERLAY_SIZE,
                "status": "same-PC application resource-lookup worker",
            },
            {
                "destination": "2A:6852",
                "source": "47:6852",
                "bytes": APPLICATION_RESOURCE_DECODE_OVERLAY_SIZE,
                "status": "same-PC application resource decoder",
            },
            {
                "destination": "32:DB08",
                "source": "4F:DB08",
                "bytes": APPLICATION_RESOURCE_OPEN_OVERLAY_SIZE,
                "status": "same-PC application resource opener",
            },
            {
                "destination": "32:DA7C",
                "source": "4F:DA7C",
                "bytes": APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SIZE,
                "status": "same-PC drawing-context factory",
            },
            {
                "destination": "32:B63C",
                "source": "4F:B63C",
                "bytes": APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SIZE,
                "status": "same-PC application resource-open wrapper",
            },
            {
                "destination": "2E:AB96",
                "source": "4B:AB96",
                "bytes": APPLICATION_RESOURCE_COORDINATE_OVERLAY_SIZE,
                "status": "same-PC application resource coordinate mapper",
            },
            {
                "destination": "33:2512",
                "source": "50:2512",
                "bytes": INT32_DIVIDE_WRAPPER_OVERLAY_SIZE,
                "status": "embedded same-PC signed division wrapper",
            },
            {
                "destination": "32:1BD8",
                "source": "4F:1BD8",
                "bytes": INT32_DIVIDE_OVERLAY_SIZE,
                "status": "same-PC signed division helper",
            },
            {
                "destination": "32:86B4",
                "source": "4F:86B4",
                "bytes": WIDE_FROM_INT16_OVERLAY_SIZE,
                "status": "same-PC signed-16 to wide-value converter",
            },
            {
                "destination": "32:8716",
                "source": "4F:8716",
                "bytes": WIDE_COMPARE_OVERLAY_SIZE,
                "status": "same-PC wide signed comparison helper",
            },
            {
                "destination": "32:D218",
                "source": "4F:D218",
                "bytes": WIDE_OPERATION_DISPATCH_OVERLAY_SIZE,
                "status": "same-PC wide-operation dispatch helper",
            },
            {
                "destination": "2A:7BD2",
                "source": "47:7BD2",
                "bytes": WIDE_ARITHMETIC_OVERLAY_SIZE,
                "status": "same-PC wide arithmetic module",
            },
            {
                "destination": "32:E72E",
                "source": "4F:E72E",
                "bytes": WIDE_ARITHMETIC_PREFIX_OVERLAY_SIZE,
                "status": "same-PC wide-arithmetic prefix dispatcher",
            },
            {
                "destination": "2C:77C8",
                "source": "49:77C8",
                "bytes": WIDE_VALUE_OPERATOR_OVERLAY_SIZE,
                "status": "same-PC complete wide-value operator",
            },
            {
                "destination": "2C:7BA8",
                "source": "49:7BA8",
                "bytes": APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SIZE,
                "status": "same-PC framed application conditional worker",
            },
            {
                "destination": "33:4C7A",
                "source": "50:4C7A",
                "bytes": APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SIZE,
                "status": "embedded application active-flag clear helper",
            },
            {
                "destination": "2F:B3E4",
                "source": "4C:B3E4",
                "bytes": WIDE_DIVIDE_STEP_OVERLAY_SIZE,
                "status": "same-PC wide divide-step helper",
            },
            {
                "destination": "33:5004",
                "source": "50:5004",
                "bytes": WIDE_SHIFT_RIGHT_OVERLAY_SIZE,
                "status": "embedded same-PC wide shift-right helper",
            },
            {
                "destination": "32:7050",
                "source": "4F:7050",
                "bytes": APPLICATION_KEY_MODE_OVERLAY_SIZE,
                "status": "same-PC call-free key-mode predicate",
            },
            {
                "destination": "32:E0F4",
                "source": "4F:E0F4",
                "bytes": APPLICATION_KEY_ITEM_REFRESH_OVERLAY_SIZE,
                "status": "same-PC framed key-item state refresher",
            },
            {
                "destination": "33:468C",
                "source": "50:468C",
                "bytes": APPLICATION_KEY_ITEM_CLEAR_OVERLAY_SIZE,
                "status": "embedded key-item clear wrapper",
            },
            {
                "destination": "33:4D2A",
                "source": "50:4D2A",
                "bytes": APPLICATION_KEY_ITEM_SET_OVERLAY_SIZE,
                "status": "embedded key-item set wrapper",
            },
            {
                "destination": "32:C736",
                "source": "4F:C736",
                "bytes": APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_SIZE,
                "status": "same-PC framed key special-action entry",
            },
            {
                "destination": "25:C140",
                "source": "42:C140",
                "bytes": APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_SIZE,
                "status": "same-PC key special-action worker",
            },
            {
                "destination": "0D:8552",
                "source": "2A:8552",
                "bytes": APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SIZE,
                "status": "resident CRC-CCITT routine",
            },
            {
                "destination": "1B:860E",
                "source": "2A:860E",
                "bytes": APPLICATION_KEY_SPECIAL_CRC_TABLE_SIZE,
                "status": "resident 256-word CRC-CCITT table",
            },
            {
                "destination": "32:08B8",
                "source": "4F:08B8",
                "bytes": APPLICATION_KEY_SPECIAL_RESET_OVERLAY_SIZE,
                "status": "same-PC key special-action state reset",
            },
            {
                "destination": "32:CEA4",
                "source": "4F:CEA4",
                "bytes": APPLICATION_KEY_INPUT_STATE_OVERLAY_SIZE,
                "status": "same-PC call-free key input-state predicate",
            },
            {
                "destination": "31:4E9C",
                "source": "4E:4E9C",
                "bytes": APPLICATION_KEY_DISPATCH_OVERLAY_SIZE,
                "status": "same-PC framed one-shot key dispatcher",
            },
            {
                "destination": "33:391A",
                "source": "50:391A",
                "bytes": APPLICATION_KEY_HW_CLEAR_OVERLAY_SIZE,
                "status": "embedded timer/key hardware-state clear helper",
            },
            {
                "destination": "33:393C",
                "source": "50:393C",
                "bytes": APPLICATION_KEY_HW_PATH_A_OVERLAY_SIZE,
                "status": "embedded key hardware path-A helper",
            },
            {
                "destination": "33:395E",
                "source": "50:395E",
                "bytes": APPLICATION_KEY_HW_PATH_B_OVERLAY_SIZE,
                "status": "embedded key hardware path-B helper",
            },
            {
                "destination": "33:38F8",
                "source": "50:38F8",
                "bytes": APPLICATION_KEY_COMPLETION_OVERLAY_SIZE,
                "status": "embedded framed key-completion helper",
            },
            {
                "destination": "28:F4A4",
                "source": "45:F4A4",
                "bytes": APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_SIZE,
                "status": "same-PC framed key-completion worker",
            },
            {
                "destination": "31:4D24",
                "source": "4E:4D24",
                "bytes": APPLICATION_BIT_OR_OVERLAY_SIZE,
                "status": "same-PC call-free far-table bitwise-OR helper",
            },
            {
                "destination": "31:5014",
                "source": "4E:5014",
                "bytes": APPLICATION_BIT_AND_OVERLAY_SIZE,
                "status": "same-PC call-free far-table bitwise-AND helper",
            },
            {
                "destination": "33:5DE4",
                "source": "50:5DE4",
                "bytes": WIDE_REGISTER_DISPATCH_OVERLAY_SIZE,
                "status": "embedded same-PC wide-register dispatch thunk group",
            },
            {
                "destination": "33:2AA2",
                "source": "50:2AA2",
                "bytes": WIDE_SIGN_NORMALIZE_OVERLAY_SIZE,
                "status": "embedded same-PC wide sign-normalization helper",
            },
            {
                "destination": "33:1188",
                "source": "50:1188",
                "bytes": WIDE_LEFT_NONZERO_OVERLAY_SIZE,
                "status": "embedded same-PC left wide-value predicate",
            },
            {
                "destination": "33:11A0",
                "source": "50:11A0",
                "bytes": WIDE_RIGHT_NONZERO_OVERLAY_SIZE,
                "status": "embedded same-PC right wide-value predicate",
            },
            {
                "destination": "32:81D4",
                "source": "4F:81D4",
                "bytes": APPLICATION_PAIR_STORE_OVERLAY_SIZE,
                "status": "same-PC far pair-store helper",
            },
            {
                "destination": "33:07B0",
                "source": "50:07B0",
                "bytes": UINT32_MULTIPLY_OVERLAY_SIZE,
                "status": "same-PC four-word unsigned multiply helper",
            },
            {
                "destination": "33:0B24",
                "source": "50:0B24",
                "bytes": STORAGE_UNIT_SELECT_OVERLAY_SIZE,
                "status": "same-PC one-byte storage-unit selector",
            },
            {
                "destination": "33:2562",
                "source": "50:2562",
                "bytes": APPLICATION_EVENT_GATE_OVERLAY_SIZE,
                "status": "same-PC application event gate",
            },
            {
                "destination": "33:3980",
                "source": "50:3980",
                "bytes": APPLICATION_EVENT_ENABLE_OVERLAY_SIZE,
                "status": "same-PC application event-enable bit setter",
            },
            {
                "destination": "32:4C34",
                "source": "4F:4C34",
                "bytes": APPLICATION_DISPATCH_POLL_OVERLAY_SIZE,
                "status": "same-PC application event poll",
            },
            {
                "destination": "31:D9AA",
                "source": "4E:D9AA",
                "bytes": APPLICATION_KEY_GPIO_SCAN_OVERLAY_SIZE,
                "status": "same-PC F010 five-key GPIO scanner",
            },
            {
                "destination": "2D:2D40",
                "source": "4A:2D40",
                "bytes": APPLICATION_KEY_ACTIVITY_OVERLAY_SIZE,
                "status": "same-PC key-activity/watchdog evaluator",
            },
            {
                "destination": "33:417A",
                "source": "50:417A",
                "bytes": APPLICATION_KEY_COUNTER_OVERLAY_SIZE,
                "status": "same-PC key-counter combiner",
            },
            {
                "destination": "33:6F3C",
                "source": "50:6F3C",
                "bytes": APPLICATION_KEY_SYNC_OVERLAY_SIZE,
                "status": "same-PC key synchronization leaf",
            },
            {
                "destination": "33:5CB2",
                "source": "50:5CB2",
                "bytes": SYSTEM_MODE_OVERLAY_SIZE,
                "status": "same-PC no-argument system-mode query",
            },
            {
                "destination": "33:3C86",
                "source": "50:3C86",
                "bytes": STARTUP_TABLE_SERVICE_OVERLAY_SIZE,
                "status": "same-PC no-argument table-service wrapper",
            },
            {
                "destination": "33:2FF2",
                "source": "50:2FF2",
                "bytes": STARTUP_REGION_SERVICE_OVERLAY_SIZE,
                "status": "same-PC no-argument region-service wrapper",
            },
        ],
        "application_main_chain": [
            {
                "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": size,
                "status": (
                    "exact root desktop clock format string"
                    if destination ==
                    APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_DESTINATION
                    else (
                        "exact formatter space/zero padding table"
                        if destination ==
                        APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_DESTINATION
                        else (
                        "exact 20-record resident operation descriptor table"
                        if destination ==
                        RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_DESTINATION
                        else (
                            "exact resident operation path/filter string pool"
                            if destination ==
                            RESIDENT_OPERATION_STRING_POOL_OVERLAY_DESTINATION
                            else (
                                "exact guest sector probe relocated to preserve the "
                                "simultaneously live 20:E914 fall-through function"
                                if destination ==
                                APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION
                                else (
                                    "exact guest object update relocated to preserve the "
                                    "simultaneously live flat 20:E914 fall-through function"
                                    if destination ==
                                    APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_DESTINATION
                                    else "exact same-PC guest function"
                                )
                            )
                        )
                        )
                    )
                ),
                **({
                    "linked_destination": "20:F928",
                    "caller_patches": [
                        "1B:CD04 SCALL 20:F928 -> 5F:F928",
                        "1C:D374 SCALL 20:F928 -> 5F:F928",
                        "1E:C774 SCALL 20:F928 -> 5F:F928",
                        "29:0536 SCALL 20:F928 -> 5F:F928",
                        "2D:1DA6 SCALL 20:F928 -> 5F:F928",
                        "20:7B44 SCALL 20:F928 -> 5F:F928",
                    ],
                } if destination ==
                    APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION
                    else ({
                        "linked_destination": "20:E914",
                        "caller_patches": [
                            "31:2FC6 SCALL 20:E914 -> 5F:E914",
                            "33:2968 SCALL 20:E914 -> 5F:E914",
                            "33:297E SCALL 20:E914 -> 5F:E914",
                        ],
                    } if destination ==
                        APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_DESTINATION
                        else {})),
            }
            for destination, source, size in (
                *APPLICATION_LAUNCH_COPY_OVERLAYS,
                *APPLICATION_LAUNCH_EMBEDDED_OVERLAYS,
                *APPLICATION_RESULT_SCAN_COPY_OVERLAYS,
                *APPLICATION_RESULT_SCAN_EMBEDDED_OVERLAYS,
                *APPLICATION_FACTORY_DEFAULT_COPY_OVERLAYS,
                *APPLICATION_FACTORY_DEFAULT_EMBEDDED_OVERLAYS,
                (APPLICATION_INIT_TASK_OVERLAY_DESTINATION,
                 APPLICATION_INIT_TASK_OVERLAY_SOURCE,
                 APPLICATION_INIT_TASK_OVERLAY_SIZE),
                (APPLICATION_VALIDATION_CHECKSUM_OVERLAY_DESTINATION,
                 APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SOURCE,
                 APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SIZE),
                (APPLICATION_RESIDENT_EVENT_OVERLAY_DESTINATION,
                 APPLICATION_RESIDENT_EVENT_OVERLAY_SOURCE,
                 APPLICATION_RESIDENT_EVENT_OVERLAY_SIZE),
                (APPLICATION_ASCII_DIGIT_OVERLAY_DESTINATION,
                 APPLICATION_ASCII_DIGIT_OVERLAY_SOURCE,
                 APPLICATION_ASCII_DIGIT_OVERLAY_SIZE),
                (APPLICATION_EVENT_POSTPROCESS_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_POSTPROCESS_OVERLAY_SOURCE,
                 APPLICATION_EVENT_POSTPROCESS_OVERLAY_SIZE),
                (APPLICATION_VALIDATION_CRC16_OVERLAY_DESTINATION,
                 APPLICATION_VALIDATION_CRC16_OVERLAY_SOURCE,
                 APPLICATION_VALIDATION_CRC16_OVERLAY_SIZE),
                (APPLICATION_TOP_LEVEL_OVERLAY_DESTINATION,
                 APPLICATION_TOP_LEVEL_OVERLAY_SOURCE,
                 APPLICATION_TOP_LEVEL_OVERLAY_SIZE),
                (APPLICATION_CURSOR_REFRESH_OVERLAY_DESTINATION,
                 APPLICATION_CURSOR_REFRESH_OVERLAY_SOURCE,
                 APPLICATION_CURSOR_REFRESH_OVERLAY_SIZE),
                (APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_DESTINATION,
                 APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_SOURCE,
                 APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_SIZE),
                (APPLICATION_MENU_CATALOG_OVERLAY_DESTINATION,
                 APPLICATION_MENU_CATALOG_OVERLAY_SOURCE,
                 APPLICATION_MENU_CATALOG_OVERLAY_SIZE),
                (APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_DESTINATION,
                 APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SOURCE,
                 APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SIZE),
                (APPLICATION_REGISTRY_OVERLAY_DESTINATION,
                 APPLICATION_REGISTRY_OVERLAY_SOURCE,
                 APPLICATION_REGISTRY_OVERLAY_SIZE),
                (APPLICATION_REGISTRY_LOOKUP_OVERLAY_DESTINATION,
                 APPLICATION_REGISTRY_LOOKUP_OVERLAY_SOURCE,
                 APPLICATION_REGISTRY_LOOKUP_OVERLAY_SIZE),
                (APPLICATION_UNALIGNED_U16_OVERLAY_DESTINATION,
                 APPLICATION_UNALIGNED_U16_OVERLAY_SOURCE,
                 APPLICATION_UNALIGNED_U16_OVERLAY_SIZE),
                (APPLICATION_MENU_TEXT_INPUT_OVERLAY_DESTINATION,
                 APPLICATION_MENU_TEXT_INPUT_OVERLAY_SOURCE,
                 APPLICATION_MENU_TEXT_INPUT_OVERLAY_SIZE),
                (APPLICATION_MENU_UI_ADAPTER_OVERLAY_DESTINATION,
                 APPLICATION_MENU_UI_ADAPTER_OVERLAY_SOURCE,
                 APPLICATION_MENU_UI_ADAPTER_OVERLAY_SIZE),
                (APPLICATION_MENU_POSITION_OVERLAY_DESTINATION,
                 APPLICATION_MENU_POSITION_OVERLAY_SOURCE,
                 APPLICATION_MENU_POSITION_OVERLAY_SIZE),
                (APPLICATION_MENU_COORDINATE_OVERLAY_DESTINATION,
                 APPLICATION_MENU_COORDINATE_OVERLAY_SOURCE,
                 APPLICATION_MENU_COORDINATE_OVERLAY_SIZE),
                (APPLICATION_MENU_RENDER_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RENDER_OVERLAY_SOURCE,
                 APPLICATION_MENU_RENDER_OVERLAY_SIZE),
                (APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SIZE),
                (APPLICATION_MENU_RESOURCE_BIND_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SIZE),
                (APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SIZE),
                (APPLICATION_MENU_RESULT_ATTACH_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SIZE),
                (APPLICATION_MENU_RESULT_LIST_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESULT_LIST_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESULT_LIST_OVERLAY_SIZE),
                (APPLICATION_MENU_RESULT_PROCESS_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SIZE),
                (APPLICATION_MENU_PAGE_POPULATE_OVERLAY_DESTINATION,
                 APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SOURCE,
                 APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SIZE),
                (APPLICATION_MENU_TEXT_EXPAND_OVERLAY_DESTINATION,
                 APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SOURCE,
                 APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SIZE),
                (APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_DESTINATION,
                 APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SOURCE,
                 APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SIZE),
                (APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_DESTINATION,
                 APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE,
                 APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SIZE),
                (APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_DESTINATION,
                 APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SOURCE,
                 APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SIZE),
                (APPLICATION_RESOURCE_INDEX_OVERLAY_DESTINATION,
                 APPLICATION_RESOURCE_INDEX_OVERLAY_SOURCE,
                 APPLICATION_RESOURCE_INDEX_OVERLAY_SIZE),
                (APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_SIZE),
                (APPLICATION_MENU_POWER_STATE_OVERLAY_DESTINATION,
                 APPLICATION_MENU_POWER_STATE_OVERLAY_SOURCE,
                 APPLICATION_MENU_POWER_STATE_OVERLAY_SIZE),
                (APPLICATION_GENERIC_MENU_OVERLAY_DESTINATION,
                 APPLICATION_GENERIC_MENU_OVERLAY_SOURCE,
                 APPLICATION_GENERIC_MENU_OVERLAY_SIZE),
                (APPLICATION_CONTEXT_GATE_OVERLAY_DESTINATION,
                 APPLICATION_CONTEXT_GATE_OVERLAY_SOURCE,
                 APPLICATION_CONTEXT_GATE_OVERLAY_SIZE),
                (APPLICATION_RECORD_XOR_OVERLAY_DESTINATION,
                 APPLICATION_RECORD_XOR_OVERLAY_SOURCE,
                 APPLICATION_RECORD_XOR_OVERLAY_SIZE),
                (APPLICATION_MENU_TABLE_BUILD_OVERLAY_DESTINATION,
                 APPLICATION_MENU_TABLE_BUILD_OVERLAY_SOURCE,
                 APPLICATION_MENU_TABLE_BUILD_OVERLAY_SIZE),
                (APPLICATION_MENU_XOR_U16_OVERLAY_DESTINATION,
                 APPLICATION_MENU_XOR_U16_OVERLAY_SOURCE,
                 APPLICATION_MENU_XOR_U16_OVERLAY_SIZE),
                (APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_SIZE),
                (APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_SIZE),
                (APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_DESTINATION,
                 APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_SOURCE,
                 APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_SIZE),
                (APPLICATION_UI_FINALIZE_OVERLAY_DESTINATION,
                 APPLICATION_UI_FINALIZE_OVERLAY_SOURCE,
                 APPLICATION_UI_FINALIZE_OVERLAY_SIZE),
                (APPLICATION_UI_STATE_OVERLAY_DESTINATION,
                 APPLICATION_UI_STATE_OVERLAY_SOURCE,
                 APPLICATION_UI_STATE_OVERLAY_SIZE),
                (ROM03_FAR_MEMCPY_THUNK_DESTINATION,
                 ROM03_FAR_MEMCPY_THUNK_SOURCE,
                 ROM03_FAR_MEMCPY_THUNK_SIZE),
                (APPLICATION_UI_PREPARE_OVERLAY_DESTINATION,
                 APPLICATION_UI_PREPARE_OVERLAY_SOURCE,
                 APPLICATION_UI_PREPARE_OVERLAY_SIZE),
                (APPLICATION_UI_PROPERTY_OVERLAY_DESTINATION,
                 APPLICATION_UI_PROPERTY_OVERLAY_SOURCE,
                 APPLICATION_UI_PROPERTY_OVERLAY_SIZE),
                (APPLICATION_UI_COMMIT_OVERLAY_DESTINATION,
                 APPLICATION_UI_COMMIT_OVERLAY_SOURCE,
                 APPLICATION_UI_COMMIT_OVERLAY_SIZE),
                (APPLICATION_GLOBAL_STATE_INIT_OVERLAY_DESTINATION,
                 APPLICATION_GLOBAL_STATE_INIT_OVERLAY_SOURCE,
                 APPLICATION_GLOBAL_STATE_INIT_OVERLAY_SIZE),
                (APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_DESTINATION,
                 APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_SOURCE,
                 APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_SIZE),
                (APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_DESTINATION,
                 APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_SOURCE,
                 APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_SIZE),
                (APPLICATION_POST_REGISTRY_OVERLAY_DESTINATION,
                 APPLICATION_POST_REGISTRY_OVERLAY_SOURCE,
                 APPLICATION_POST_REGISTRY_OVERLAY_SIZE),
                (APPLICATION_POST_REGISTRY_STATE_OVERLAY_DESTINATION,
                 APPLICATION_POST_REGISTRY_STATE_OVERLAY_SOURCE,
                 APPLICATION_POST_REGISTRY_STATE_OVERLAY_SIZE),
                (APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_DESTINATION,
                 APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_SOURCE,
                 APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_SIZE),
                (APPLICATION_POST_REGISTRY_HOOK_OVERLAY_DESTINATION,
                 APPLICATION_POST_REGISTRY_HOOK_OVERLAY_SOURCE,
                 APPLICATION_POST_REGISTRY_HOOK_OVERLAY_SIZE),
                (APPLICATION_MAIN_PREPARE_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_PREPARE_OVERLAY_SOURCE,
                 APPLICATION_MAIN_PREPARE_OVERLAY_SIZE),
                (APPLICATION_MAIN_BIT_CLEAR_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_BIT_CLEAR_OVERLAY_SOURCE,
                 APPLICATION_MAIN_BIT_CLEAR_OVERLAY_SIZE),
                (APPLICATION_MAIN_STATE_INIT_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STATE_INIT_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STATE_INIT_OVERLAY_SIZE),
                (APPLICATION_MAIN_STATE_BUILD_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STATE_BUILD_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STATE_BUILD_OVERLAY_SIZE),
                (APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SIZE),
                (APPLICATION_MAIN_STATE_POINTER_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STATE_POINTER_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STATE_POINTER_OVERLAY_SIZE),
                (APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_SIZE),
                (RESIDENT_WORK_TABLE_CREATE_OVERLAY_DESTINATION,
                 RESIDENT_WORK_TABLE_CREATE_OVERLAY_SOURCE,
                 RESIDENT_WORK_TABLE_CREATE_OVERLAY_SIZE),
                (RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_DESTINATION,
                 RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SOURCE,
                 RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SIZE),
                (RESIDENT_OPERATION_STRING_POOL_OVERLAY_DESTINATION,
                 RESIDENT_OPERATION_STRING_POOL_OVERLAY_SOURCE,
                 RESIDENT_OPERATION_STRING_POOL_OVERLAY_SIZE),
                *APPLICATION_OPERATION_MODAL_CLOSURE_OVERLAYS,
                (APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_DESTINATION,
                 APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SOURCE,
                 APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SIZE),
                (APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_DESTINATION,
                 APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SOURCE,
                 APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SIZE),
                (APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SIZE),
                (APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SIZE),
                (APPLICATION_MAIN_STORAGE_MASK_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SIZE),
                (APPLICATION_MAIN_SERVICE_INIT_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SOURCE,
                 APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SIZE),
                (APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SIZE),
                (APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_SOURCE,
                 APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_SIZE),
                (APPLICATION_MAIN_CONFIG_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_CONFIG_OVERLAY_SOURCE,
                 APPLICATION_MAIN_CONFIG_OVERLAY_SIZE),
                (APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_SOURCE,
                 APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_SIZE),
                (APPLICATION_MAIN_OBJECT_BIND_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_OBJECT_BIND_OVERLAY_SOURCE,
                 APPLICATION_MAIN_OBJECT_BIND_OVERLAY_SIZE),
                (APPLICATION_MAIN_CONDITIONAL_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_CONDITIONAL_OVERLAY_SOURCE,
                 APPLICATION_MAIN_CONDITIONAL_OVERLAY_SIZE),
                (APPLICATION_MAIN_SERVICES_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_SERVICES_OVERLAY_SOURCE,
                 APPLICATION_MAIN_SERVICES_OVERLAY_SIZE),
                (APPLICATION_MAIN_INPUT_STATE_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_INPUT_STATE_OVERLAY_SOURCE,
                 APPLICATION_MAIN_INPUT_STATE_OVERLAY_SIZE),
                (APPLICATION_MAIN_STATUS_SCAN_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STATUS_SCAN_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STATUS_SCAN_OVERLAY_SIZE),
                (APPLICATION_MAIN_STATE_TICK_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STATE_TICK_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STATE_TICK_OVERLAY_SIZE),
                (APPLICATION_MAIN_STATE_CLEAR_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STATE_CLEAR_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STATE_CLEAR_OVERLAY_SIZE),
                (APPLICATION_MAIN_STATUS_GET_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STATUS_GET_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STATUS_GET_OVERLAY_SIZE),
                (APPLICATION_MAIN_STATE_SYNC_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_STATE_SYNC_OVERLAY_SOURCE,
                 APPLICATION_MAIN_STATE_SYNC_OVERLAY_SIZE),
                (APPLICATION_MAIN_ROM_STATE_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_ROM_STATE_OVERLAY_SOURCE,
                 APPLICATION_MAIN_ROM_STATE_OVERLAY_SIZE),
                (APPLICATION_MAIN_ROM_MENU_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_ROM_MENU_OVERLAY_SOURCE,
                 APPLICATION_MAIN_ROM_MENU_OVERLAY_SIZE),
                (APPLICATION_MAIN_ROM_COMPOSITOR_DESTINATION,
                 APPLICATION_MAIN_ROM_COMPOSITOR_SOURCE,
                 APPLICATION_MAIN_ROM_COMPOSITOR_SIZE),
                (APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SOURCE,
                 APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SIZE),
                (APPLICATION_MAIN_ROM_RESOURCE_STATE_DESTINATION,
                 APPLICATION_MAIN_ROM_RESOURCE_STATE_SOURCE,
                 APPLICATION_MAIN_ROM_RESOURCE_STATE_SIZE),
                (APPLICATION_MAIN_ROM_RESOURCE_PROBE_DESTINATION,
                 APPLICATION_MAIN_ROM_RESOURCE_PROBE_SOURCE,
                 APPLICATION_MAIN_ROM_RESOURCE_PROBE_SIZE),
                (APPLICATION_MAIN_ROM_RESOURCE_TEST_DESTINATION,
                 APPLICATION_MAIN_ROM_RESOURCE_TEST_SOURCE,
                 APPLICATION_MAIN_ROM_RESOURCE_TEST_SIZE),
                (APPLICATION_MAIN_RECORD_LOAD_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SOURCE,
                 APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SIZE),
                (APPLICATION_MAIN_ROM_RESOURCE_SCAN_DESTINATION,
                 APPLICATION_MAIN_ROM_RESOURCE_SCAN_SOURCE,
                 APPLICATION_MAIN_ROM_RESOURCE_SCAN_SIZE),
                (APPLICATION_MAIN_ROM_RESOURCE_CHECK_DESTINATION,
                 APPLICATION_MAIN_ROM_RESOURCE_CHECK_SOURCE,
                 APPLICATION_MAIN_ROM_RESOURCE_CHECK_SIZE),
                (APPLICATION_MAIN_ROM_RESOURCE_XOR_DESTINATION,
                 APPLICATION_MAIN_ROM_RESOURCE_XOR_SOURCE,
                 APPLICATION_MAIN_ROM_RESOURCE_XOR_SIZE),
                (APPLICATION_MAIN_ROM_RESOURCE_HEX_DESTINATION,
                 APPLICATION_MAIN_ROM_RESOURCE_HEX_SOURCE,
                 APPLICATION_MAIN_ROM_RESOURCE_HEX_SIZE),
                (APPLICATION_MAIN_ROM_RESOURCE_FORMAT_DESTINATION,
                 APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SOURCE,
                 APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SIZE),
                (APPLICATION_MAIN_ROM_LAYOUT_BUILD_DESTINATION,
                 APPLICATION_MAIN_ROM_LAYOUT_BUILD_SOURCE,
                 APPLICATION_MAIN_ROM_LAYOUT_BUILD_SIZE),
                (APPLICATION_MAIN_ROM_RENDER_DESTINATION,
                 APPLICATION_MAIN_ROM_RENDER_SOURCE,
                 APPLICATION_MAIN_ROM_RENDER_SIZE),
                (APPLICATION_MAIN_ROM_INPUT_DESTINATION,
                 APPLICATION_MAIN_ROM_INPUT_SOURCE,
                 APPLICATION_MAIN_ROM_INPUT_SIZE),
                (APPLICATION_COMPARE_ROM_DESTINATION,
                 APPLICATION_COMPARE_ROM_SOURCE,
                 APPLICATION_COMPARE_ROM_SIZE),
                (RESIDENT_REGION_MASK_18_ADDRESS,
                 RESIDENT_REGION_MASK_18_SOURCE,
                 RESIDENT_REGION_MASK_18_SIZE),
                (APPLICATION_FOREGROUND_ROM_WORKER_DESTINATION,
                 APPLICATION_FOREGROUND_ROM_WORKER_SOURCE,
                 APPLICATION_FOREGROUND_ROM_WORKER_SIZE),
                (APPLICATION_FOREGROUND_ROM_DISPATCH_DESTINATION,
                 APPLICATION_FOREGROUND_ROM_DISPATCH_SOURCE,
                 APPLICATION_FOREGROUND_ROM_DISPATCH_SIZE),
                (APPLICATION_MAIN_ACTION_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_ACTION_OVERLAY_SOURCE,
                 APPLICATION_MAIN_ACTION_OVERLAY_SIZE),
                (APPLICATION_MAIN_ACTION_QUERY_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_ACTION_QUERY_OVERLAY_SOURCE,
                 APPLICATION_MAIN_ACTION_QUERY_OVERLAY_SIZE),
                (APPLICATION_MAIN_ACTION_RENDER_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_ACTION_RENDER_OVERLAY_SOURCE,
                 APPLICATION_MAIN_ACTION_RENDER_OVERLAY_SIZE),
                (APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_DESTINATION,
                 APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SOURCE,
                 APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SIZE),
                (APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_DESTINATION,
                 APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SOURCE,
                 APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SIZE),
                (APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_SOURCE,
                 APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_SIZE),
                (APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_SOURCE,
                 APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_SIZE),
                (APPLICATION_MAIN_ACTION_RENDER_PACK_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_ACTION_RENDER_PACK_OVERLAY_SOURCE,
                 APPLICATION_MAIN_ACTION_RENDER_PACK_OVERLAY_SIZE),
                (APPLICATION_MAIN_ACTION_RENDER_EDGES_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_ACTION_RENDER_EDGES_OVERLAY_SOURCE,
                 APPLICATION_MAIN_ACTION_RENDER_EDGES_OVERLAY_SIZE),
                (APPLICATION_REGION_CONVERT_OVERLAY_DESTINATION,
                 APPLICATION_REGION_CONVERT_OVERLAY_SOURCE,
                 APPLICATION_REGION_CONVERT_OVERLAY_SIZE),
                (APPLICATION_REGION_SCALE_OVERLAY_DESTINATION,
                 APPLICATION_REGION_SCALE_OVERLAY_SOURCE,
                 APPLICATION_REGION_SCALE_OVERLAY_SIZE),
                (APPLICATION_REGION_ARITH_OVERLAY_DESTINATION,
                 APPLICATION_REGION_ARITH_OVERLAY_SOURCE,
                 APPLICATION_REGION_ARITH_OVERLAY_SIZE),
                (APPLICATION_REGION_NORMALIZE_OVERLAY_DESTINATION,
                 APPLICATION_REGION_NORMALIZE_OVERLAY_SOURCE,
                 APPLICATION_REGION_NORMALIZE_OVERLAY_SIZE),
                (APPLICATION_REGION_DIGIT_OVERLAY_DESTINATION,
                 APPLICATION_REGION_DIGIT_OVERLAY_SOURCE,
                 APPLICATION_REGION_DIGIT_OVERLAY_SIZE),
                (APPLICATION_REGION_VALUE_OVERLAY_DESTINATION,
                 APPLICATION_REGION_VALUE_OVERLAY_SOURCE,
                 APPLICATION_REGION_VALUE_OVERLAY_SIZE),
                (APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_DESTINATION,
                 APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SOURCE,
                 APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SIZE),
                (APPLICATION_REGION_NONZERO_OVERLAY_DESTINATION,
                 APPLICATION_REGION_NONZERO_OVERLAY_SOURCE,
                 APPLICATION_REGION_NONZERO_OVERLAY_SIZE),
                (APPLICATION_FONT_TABLE_OVERLAY_DESTINATION,
                 APPLICATION_FONT_TABLE_OVERLAY_SOURCE,
                 APPLICATION_FONT_TABLE_OVERLAY_SIZE),
                (APPLICATION_MAIN_RESULT_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_RESULT_OVERLAY_SOURCE,
                 APPLICATION_MAIN_RESULT_OVERLAY_SIZE),
                (APPLICATION_MAIN_RESULT_SCAN_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SOURCE,
                 APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SIZE),
                (APPLICATION_MAIN_LAYOUT_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_LAYOUT_OVERLAY_SOURCE,
                 APPLICATION_MAIN_LAYOUT_OVERLAY_SIZE),
                (APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_SOURCE,
                 APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_LOOP_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_LOOP_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_LOOP_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_STATE_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_STATE_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_STATE_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_COPY_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_COPY_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_COPY_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_EVENT_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_EVENT_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_EVENT_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_PARENT_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_PARENT_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_PARENT_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_DISPATCH_TABLE_DESTINATION,
                 APPLICATION_FOREGROUND_DISPATCH_TABLE_SOURCE,
                 APPLICATION_FOREGROUND_DISPATCH_TABLE_SIZE),
                (APPLICATION_FOREGROUND_MODE_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_MODE_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_MODE_OVERLAY_SIZE),
                (APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_DESTINATION,
                 APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SOURCE,
                 APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_STATE50_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_STATE50_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_STATE50_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_STATE50_ROM_DESTINATION,
                 APPLICATION_FOREGROUND_STATE50_ROM_SOURCE,
                 APPLICATION_FOREGROUND_STATE50_ROM_SIZE),
                (APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_SIZE),
                (APPLICATION_CURSOR_RANGE_OVERLAY_DESTINATION,
                 APPLICATION_CURSOR_RANGE_OVERLAY_SOURCE,
                 APPLICATION_CURSOR_RANGE_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_STATUS_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_STATUS_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_STATUS_OVERLAY_SIZE),
                (APPLICATION_INPUT_MODE_OVERLAY_DESTINATION,
                 APPLICATION_INPUT_MODE_OVERLAY_SOURCE,
                 APPLICATION_INPUT_MODE_OVERLAY_SIZE),
                (APPLICATION_EVENT_GATE_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_GATE_OVERLAY_SOURCE,
                 APPLICATION_EVENT_GATE_OVERLAY_SIZE),
                (APPLICATION_EVENT_GATE_POWER_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_GATE_POWER_OVERLAY_SOURCE,
                 APPLICATION_EVENT_GATE_POWER_OVERLAY_SIZE),
                (APPLICATION_EVENT_PACKET_DECODE_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_PACKET_DECODE_OVERLAY_SOURCE,
                 APPLICATION_EVENT_PACKET_DECODE_OVERLAY_SIZE),
                (APPLICATION_EVENT_PACKET_COPY_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_PACKET_COPY_OVERLAY_SOURCE,
                 APPLICATION_EVENT_PACKET_COPY_OVERLAY_SIZE),
                (APPLICATION_EVENT_TEXT_DATA_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_TEXT_DATA_OVERLAY_SOURCE,
                 APPLICATION_EVENT_TEXT_DATA_OVERLAY_SIZE),
                (APPLICATION_EVENT_RENDER_HELPER_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SOURCE,
                 APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SIZE),
                (APPLICATION_EVENT_READY_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_READY_OVERLAY_SOURCE,
                 APPLICATION_EVENT_READY_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_SIZE),
                (APPLICATION_TIMER_CALLBACK_OVERLAY_DESTINATION,
                 APPLICATION_TIMER_CALLBACK_OVERLAY_SOURCE,
                 APPLICATION_TIMER_CALLBACK_OVERLAY_SIZE),
                (APPLICATION_KEY_DEBOUNCE_OVERLAY_DESTINATION,
                 APPLICATION_KEY_DEBOUNCE_OVERLAY_SOURCE,
                 APPLICATION_KEY_DEBOUNCE_OVERLAY_SIZE),
                (APPLICATION_KEY_MATRIX_SCAN_OVERLAY_DESTINATION,
                 APPLICATION_KEY_MATRIX_SCAN_OVERLAY_SOURCE,
                 APPLICATION_KEY_MATRIX_SCAN_OVERLAY_SIZE),
                (APPLICATION_TIMER_POWER_OVERLAY_DESTINATION,
                 APPLICATION_TIMER_POWER_OVERLAY_SOURCE,
                 APPLICATION_TIMER_POWER_OVERLAY_SIZE),
                (APPLICATION_TIMER_IDLE_OVERLAY_DESTINATION,
                 APPLICATION_TIMER_IDLE_OVERLAY_SOURCE,
                 APPLICATION_TIMER_IDLE_OVERLAY_SIZE),
                (APPLICATION_TIMER_CALENDAR_OVERLAY_DESTINATION,
                 APPLICATION_TIMER_CALENDAR_OVERLAY_SOURCE,
                 APPLICATION_TIMER_CALENDAR_OVERLAY_SIZE),
                (APPLICATION_TIMER_COMMIT_OVERLAY_DESTINATION,
                 APPLICATION_TIMER_COMMIT_OVERLAY_SOURCE,
                 APPLICATION_TIMER_COMMIT_OVERLAY_SIZE),
                (APPLICATION_EVENT_FETCH_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_FETCH_OVERLAY_SOURCE,
                 APPLICATION_EVENT_FETCH_OVERLAY_SIZE),
                (APPLICATION_EVENT_DECODE_OVERLAY_DESTINATION,
                 APPLICATION_EVENT_DECODE_OVERLAY_SOURCE,
                 APPLICATION_EVENT_DECODE_OVERLAY_SIZE),
                (APPLICATION_LOADING_TASK_OVERLAY_DESTINATION,
                 APPLICATION_LOADING_TASK_OVERLAY_SOURCE,
                 APPLICATION_LOADING_TASK_OVERLAY_SIZE),
                (APPLICATION_SYSTEM_REGISTRY_OVERLAY_DESTINATION,
                 APPLICATION_SYSTEM_REGISTRY_OVERLAY_SOURCE,
                 APPLICATION_SYSTEM_REGISTRY_OVERLAY_SIZE),
                (APPLICATION_STORAGE_CAPACITY_OVERLAY_DESTINATION,
                 APPLICATION_STORAGE_CAPACITY_OVERLAY_SOURCE,
                 APPLICATION_STORAGE_CAPACITY_OVERLAY_SIZE),
                (APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_DESTINATION,
                 APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_SOURCE,
                 APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_SIZE),
                (APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_DESTINATION,
                 APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SOURCE,
                 APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SIZE),
                (APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION,
                 APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SOURCE,
                 APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SIZE),
                (APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_DESTINATION,
                 APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SOURCE,
                 APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SIZE),
                (APPLICATION_POST_MODAL_STATE_OVERLAY_DESTINATION,
                 APPLICATION_POST_MODAL_STATE_OVERLAY_SOURCE,
                 APPLICATION_POST_MODAL_STATE_OVERLAY_SIZE),
                (APPLICATION_POST_MODAL_REFRESH_OVERLAY_DESTINATION,
                 APPLICATION_POST_MODAL_REFRESH_OVERLAY_SOURCE,
                 APPLICATION_POST_MODAL_REFRESH_OVERLAY_SIZE),
                (APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_DESTINATION,
                 APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SOURCE,
                 APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SIZE),
                (APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_DESTINATION,
                 APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_SOURCE,
                 APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_SIZE),
                (APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_DESTINATION,
                 APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SOURCE,
                 APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SIZE),
                (APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_DESTINATION,
                 APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SOURCE,
                 APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SIZE),
                (WIDE_ACCUMULATE_OVERLAY_DESTINATION,
                 WIDE_ACCUMULATE_OVERLAY_SOURCE,
                 WIDE_ACCUMULATE_OVERLAY_SIZE),
                (APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_DESTINATION,
                 APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SOURCE,
                 APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SIZE),
                (WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_DESTINATION,
                 WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SOURCE,
                 WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SIZE),
                (STARTUP_TICK_INIT_OVERLAY_DESTINATION,
                 STARTUP_TICK_INIT_OVERLAY_SOURCE,
                 STARTUP_TICK_INIT_OVERLAY_SIZE),
                (STARTUP_TIMER_CONFIG_OVERLAY_DESTINATION,
                 STARTUP_TIMER_CONFIG_OVERLAY_SOURCE,
                 STARTUP_TIMER_CONFIG_OVERLAY_SIZE),
                (APPLICATION_FAR_BLOCK_COPY_OVERLAY_DESTINATION,
                 APPLICATION_FAR_BLOCK_COPY_OVERLAY_SOURCE,
                 APPLICATION_FAR_BLOCK_COPY_OVERLAY_SIZE),
                (APPLICATION_INIT_ENTRY_OVERLAY_DESTINATION,
                 APPLICATION_INIT_ENTRY_OVERLAY_SOURCE,
                 APPLICATION_INIT_ENTRY_OVERLAY_SIZE),
                (APPLICATION_CLOCK_VALIDATE_OVERLAY_DESTINATION,
                 APPLICATION_CLOCK_VALIDATE_OVERLAY_SOURCE,
                 APPLICATION_CLOCK_VALIDATE_OVERLAY_SIZE),
                (APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_DESTINATION,
                 APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SOURCE,
                 APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SIZE),
                (APPLICATION_SERVICE_LATCH_INIT_OVERLAY_DESTINATION,
                 APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SOURCE,
                 APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SIZE),
                (APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_DESTINATION,
                 APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_SOURCE,
                 APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_SIZE),
                (APPLICATION_INIT_31_1528_OVERLAY_DESTINATION,
                 APPLICATION_INIT_31_1528_OVERLAY_SOURCE,
                 APPLICATION_INIT_31_1528_OVERLAY_SIZE),
                (APPLICATION_INIT_08_2EDC_OVERLAY_DESTINATION,
                 APPLICATION_INIT_08_2EDC_OVERLAY_SOURCE,
                 APPLICATION_INIT_08_2EDC_OVERLAY_SIZE),
                (APPLICATION_INIT_33_356E_OVERLAY_DESTINATION,
                 APPLICATION_INIT_33_356E_OVERLAY_SOURCE,
                 APPLICATION_INIT_33_356E_OVERLAY_SIZE),
                (APPLICATION_INIT_33_3406_OVERLAY_DESTINATION,
                 APPLICATION_INIT_33_3406_OVERLAY_SOURCE,
                 APPLICATION_INIT_33_3406_OVERLAY_SIZE),
                (APPLICATION_INIT_08_3324_OVERLAY_DESTINATION,
                 APPLICATION_INIT_08_3324_OVERLAY_SOURCE,
                 APPLICATION_INIT_08_3324_OVERLAY_SIZE),
                (APPLICATION_INIT_33_3FD6_OVERLAY_DESTINATION,
                 APPLICATION_INIT_33_3FD6_OVERLAY_SOURCE,
                 APPLICATION_INIT_33_3FD6_OVERLAY_SIZE),
                (APPLICATION_INIT_29_C126_OVERLAY_DESTINATION,
                 APPLICATION_INIT_29_C126_OVERLAY_SOURCE,
                 APPLICATION_INIT_29_C126_OVERLAY_SIZE),
                (APPLICATION_INIT_33_09B8_OVERLAY_DESTINATION,
                 APPLICATION_INIT_33_09B8_OVERLAY_SOURCE,
                 APPLICATION_INIT_33_09B8_OVERLAY_SIZE),
                (APPLICATION_INIT_32_4D1C_OVERLAY_DESTINATION,
                 APPLICATION_INIT_32_4D1C_OVERLAY_SOURCE,
                 APPLICATION_INIT_32_4D1C_OVERLAY_SIZE),
                (APPLICATION_INIT_32_3232_OVERLAY_DESTINATION,
                 APPLICATION_INIT_32_3232_OVERLAY_SOURCE,
                 APPLICATION_INIT_32_3232_OVERLAY_SIZE),
                (APPLICATION_INIT_31_C3FC_OVERLAY_DESTINATION,
                 APPLICATION_INIT_31_C3FC_OVERLAY_SOURCE,
                 APPLICATION_INIT_31_C3FC_OVERLAY_SIZE),
                (APPLICATION_INIT_32_519E_OVERLAY_DESTINATION,
                 APPLICATION_INIT_32_519E_OVERLAY_SOURCE,
                 APPLICATION_INIT_32_519E_OVERLAY_SIZE),
                (APPLICATION_INIT_32_F3C6_OVERLAY_DESTINATION,
                 APPLICATION_INIT_32_F3C6_OVERLAY_SOURCE,
                 APPLICATION_INIT_32_F3C6_OVERLAY_SIZE),
                (APPLICATION_INIT_31_B6FC_OVERLAY_DESTINATION,
                 APPLICATION_INIT_31_B6FC_OVERLAY_SOURCE,
                 APPLICATION_INIT_31_B6FC_OVERLAY_SIZE),
                (APPLICATION_INIT_31_CC84_OVERLAY_DESTINATION,
                 APPLICATION_INIT_31_CC84_OVERLAY_SOURCE,
                 APPLICATION_INIT_31_CC84_OVERLAY_SIZE),
                (APPLICATION_MAIN_LOOP_OVERLAY_DESTINATION,
                 APPLICATION_MAIN_LOOP_OVERLAY_SOURCE,
                 APPLICATION_MAIN_LOOP_OVERLAY_SIZE),
                (APPLICATION_RESOURCE_DRIVER_OVERLAY_DESTINATION,
                 APPLICATION_RESOURCE_DRIVER_OVERLAY_SOURCE,
                 APPLICATION_RESOURCE_DRIVER_OVERLAY_SIZE),
                (APPLICATION_FILE_ATTACH_OVERLAY_DESTINATION,
                 APPLICATION_FILE_ATTACH_OVERLAY_SOURCE,
                 APPLICATION_FILE_ATTACH_OVERLAY_SIZE),
                (APPLICATION_FILE_WRAPPER_OVERLAY_DESTINATION,
                 APPLICATION_FILE_WRAPPER_OVERLAY_SOURCE,
                 APPLICATION_FILE_WRAPPER_OVERLAY_SIZE),
                (APPLICATION_FILE_OBJECT_OPEN_OVERLAY_DESTINATION,
                 APPLICATION_FILE_OBJECT_OPEN_OVERLAY_SOURCE,
                 APPLICATION_FILE_OBJECT_OPEN_OVERLAY_SIZE),
                (APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_DESTINATION,
                 APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_SOURCE,
                 APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_SIZE),
                (APPLICATION_POINTER_CLASSIFY_OVERLAY_DESTINATION,
                 APPLICATION_POINTER_CLASSIFY_OVERLAY_SOURCE,
                 APPLICATION_POINTER_CLASSIFY_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_SCAN_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_SCAN_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_SCAN_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_SIZE),
                (APPLICATION_FILE_CREATE_STATE_OVERLAY_DESTINATION,
                 APPLICATION_FILE_CREATE_STATE_OVERLAY_SOURCE,
                 APPLICATION_FILE_CREATE_STATE_OVERLAY_SIZE),
                (APPLICATION_FILE_CREATE_RECORD_OVERLAY_DESTINATION,
                 APPLICATION_FILE_CREATE_RECORD_OVERLAY_SOURCE,
                 APPLICATION_FILE_CREATE_RECORD_OVERLAY_SIZE),
                (APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_DESTINATION,
                 APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_SOURCE,
                 APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_SIZE),
                (APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_DESTINATION,
                 APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_SOURCE,
                 APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_SIZE),
                (APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION,
                 APPLICATION_FILE_ENTRY_BUILD_OVERLAY_SOURCE,
                 APPLICATION_FILE_ENTRY_BUILD_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_BUILD_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_BUILD_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_BUILD_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_SIZE),
                (APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_DESTINATION,
                 APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_SOURCE,
                 APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_SIZE),
                (APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_DESTINATION,
                 APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_SOURCE,
                 APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_SIZE),
                (APPLICATION_BYTE_CLASSIFY_OVERLAY_DESTINATION,
                 APPLICATION_BYTE_CLASSIFY_OVERLAY_SOURCE,
                 APPLICATION_BYTE_CLASSIFY_OVERLAY_SIZE),
                (APPLICATION_ASCII_LOWER_OVERLAY_DESTINATION,
                 APPLICATION_ASCII_LOWER_OVERLAY_SOURCE,
                 APPLICATION_ASCII_LOWER_OVERLAY_SIZE),
            )
        ],
        "application_userinfo_literals": {
            "destination": "31:937C",
            "source": "4E:937C",
            "bytes": APPLICATION_USERINFO_LITERAL_OVERLAY_SIZE,
            "data": program_source_bytes(
                APPLICATION_USERINFO_LITERAL_OVERLAY_SOURCE,
                APPLICATION_USERINFO_LITERAL_OVERLAY_SIZE,
            ).hex(),
            "status": (
                "exact guest GBK messages and 0:\\USERINFO.SYS path copied "
                "into the SoC data-RAM view by the guest installer"
            ),
        },
        "application_byte_classify_table": {
            "destination": "33:3B86",
            "source": "50:3B86",
            "bytes": APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_SIZE,
            "data": program_source_bytes(
                APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_SOURCE,
                APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_SIZE,
            ).hex(),
            "status": (
                "exact sixteen-byte forbidden-punctuation table retained "
                "inside the guest late installer"
            ),
        },
        "lcd_resource_dispatch_chain": [
            {
                "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": size,
                "status": "exact guest dispatch thunk" if size == 4
                          else "exact same-PC guest function",
            }
            for destination, source, size in (
                (LCD_RESOURCE_DISPATCH_THUNK_DESTINATION,
                 LCD_RESOURCE_DISPATCH_THUNK_SOURCE,
                 LCD_RESOURCE_DISPATCH_THUNK_SIZE),
                (LCD_RESOURCE_TRANSFER_OVERLAY_DESTINATION,
                 LCD_RESOURCE_TRANSFER_OVERLAY_SOURCE,
                 LCD_RESOURCE_TRANSFER_OVERLAY_SIZE),
                (APPLICATION_RESOURCE_PAGE_READ_OVERLAY_DESTINATION,
                 APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SOURCE,
                 APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SIZE),
            )
        ],
        "initializer_probe_sources": [
            {
                "address": f"{address >> 16:02X}:{address & 0xFFFF:04X}",
                "bytes": data.hex(),
                "warning": "sentinel bytes; not recovered factory ROM data",
            }
            for address, data in sorted(INITIALIZER_PROBE_SOURCES.items())
        ] if (initializer_probe or dual_initializer_probe) else [],
        "initializer_factory_sources": [
            {
                "destination": (
                    f"{destination >> 16:02X}:"
                    f"{destination & 0xFFFF:04X}"
                ),
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": size,
                "storage_hex": program_source_bytes(source, size).hex(),
                "status": "exact +0x1D linked PRG storage copy",
            }
            for destination, source, size in INITIALIZER_FACTORY_SOURCE_COPIES
        ] if initializer_overlay_probe else [],
        "factory_linked_startup_modules": [
            {
                "destination": (
                    f"{destination >> 16:02X}:"
                    f"{destination & 0xFFFF:04X}"
                ),
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": size,
                "status": status,
            }
            for destination, source, size, status in (
                (
                    FACTORY_COMPILER_INITIALIZER_DESTINATION,
                    FACTORY_COMPILER_INITIALIZER_SOURCE,
                    FACTORY_COMPILER_INITIALIZER_SIZE,
                    "exact +0x1D linked 261-descriptor chain",
                ),
                (
                    FACTORY_CONSTANT_INITIALIZER_DESTINATION,
                    FACTORY_CONSTANT_INITIALIZER_SOURCE,
                    FACTORY_CONSTANT_INITIALIZER_SIZE,
                    "exact +0x1D linked nine-descriptor chain; terminal "
                    "jump retargeted to explicit late loader",
                ),
                (
                    FACTORY_SYSTEM_MAIN_DESTINATION,
                    FACTORY_SYSTEM_MAIN_SOURCE,
                    FACTORY_SYSTEM_MAIN_SIZE,
                    ("exact +0x1D linked system-main initialization and "
                     "01:0200 loader; terminal foreground call replaced "
                     "with balanced guest-manager handoff"
                     if (probe_direct_generic_menu or
                         probe_factory_default_catalogue) else
                     "exact +0x1D linked system main"),
                ),
            )
        ] if factory_linked_startup else [],
        "entries": [
            {
                "address": f"{address >> 16:02X}:{address & 0xFFFF:04X}",
                "name": name,
                "words": len(words),
            }
            for address, (name, words) in sorted(routines.items())
        ],
    }


def main() -> int:
    global PROGRAM_SOURCE, PROVISION_TRIGGER_TARGET

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--program", type=Path, default=DEFAULT_PROGRAM,
        help=(
            "PRG source used when recovering and embedding vendor overlays "
            f"(default: {DEFAULT_PROGRAM})"
        ),
    )
    parser.add_argument(
        "--provision-trigger-target",
        type=lambda value: int(value, 0),
        default=0,
        help=(
            "provisioning-only: after installing the application overlay, "
            "replace its one-shot 2D:7F66 call with SCALL to this 24-bit "
            "guest address (default: disabled)"
        ),
    )
    parser.add_argument(
        "--startup-context", type=lambda value: int(value, 0), default=0,
        help="24-bit resident-loader context handed to NP560.PRG (default: 0)",
    )
    parser.add_argument(
        "--probe-font-lookup", action="store_true",
        help=(
            "deprecated compatibility switch; 17:9244 is now recovered as "
            "exact guest code"
        ),
    )
    parser.add_argument(
        "--probe-rom-08-427e-return", action="store_true",
        help=(
            "compatibility exploration switch: 08:427E is now recovered "
            "exactly; retain the post-20:026A call/return probe flow"
        ),
    )
    parser.add_argument(
        "--probe-rom-03-4124-zero", action="store_true",
        help=(
            "compatibility exploration switch: 03:4124 is now recovered "
            "exactly in the segment-03 jump table; retain the old flow gate"
        ),
    )
    parser.add_argument(
        "--probe-rom-01-0200-return", action="store_true",
        help=(
            "reconstruct the inferred 01:0200 late application-overlay and "
            "LCD loader as guest DMCU code, then return to 20:026A"
        ),
    )
    parser.add_argument(
        "--probe-continue-event-loop", action="store_true",
        help=(
            "exploration only: after both initializers and 20:026A return, "
            "enter the reconstructed guest keyboard event loop"
        ),
    )
    parser.add_argument(
        "--probe-dispatch-activation", action="store_true",
        help=(
            "exploration only: dispatch one complete 0x008E activation "
            "event before polling keyboard hardware"
        ),
    )
    parser.add_argument(
        "--probe-lcd-power-on", action="store_true",
        help=(
            "exploration only: invoke the recovered segment-14 ST7529 "
            "power/init wrapper before entering the event loop"
        ),
    )
    parser.add_argument(
        "--probe-app-init-callback", action="store_true",
        help=(
            "exploration only: call the recovered target 22:9738 "
            "application initializer after 20:026A returns"
        ),
    )
    parser.add_argument(
        "--probe-system-main", action="store_true",
        help=(
            "enter the exact 2D:7DD2 application dispatcher and retain its "
            "native foreground/event loop"
        ),
    )
    parser.add_argument(
        "--probe-stop-after-scheduler-return", action="store_true",
        help=(
            "exploration only: after a scheduler-owned complete 20:026A "
            "lifecycle returns at 03:0084, remain in a guest self-loop so "
            "the post-return CPU and data state can be captured"
        ),
    )
    parser.add_argument(
        "--probe-stop-before-scheduler-entry", action="store_true",
        help=(
            "exploration only: when the bootstrap-owned foreground returns "
            "to 03:0080, remain in a guest self-loop before invoking another "
            "20:026A lifecycle so the first-return state can be captured"
        ),
    )
    parser.add_argument(
        "--probe-fixed-launch-wrapper", action="store_true",
        help=(
            "exploration only: reproduce the unproven adjacent-wrapper "
            "33:3CA6/33:3CC6 resource-launch experiment"
        ),
    )
    parser.add_argument(
        "--probe-generic-main-menu", action="store_true",
        help=(
            "exploration only: reproduce the rejected adjacency-based "
            "33:3CA6/33:3CC6 lirt.nwf launch hypothesis"
        ),
    )
    parser.add_argument(
        "--probe-direct-generic-menu", action="store_true",
        help=(
            "exploration only: enter exact vendor menu entry 2C:C9E8 with "
            "the recovered resident page-zero table, bypassing lirt.nwf"
        ),
    )
    parser.add_argument(
        "--probe-factory-default-catalogue", action="store_true",
        help=(
            "exploration only: after exact hardware/system initialization, "
            "call the recovered guest factory-default/catalogue routine "
            "2A:A952 with no fabricated key or application result"
        ),
    )
    parser.add_argument(
        "--probe-resident-app-state-guard", action="store_true",
        help=(
            "exploration only: at resident entry 1E:F734, return no event "
            "until application sentinel A2:2AA4 is initialized, then "
            "tail-call the exact shipped dispatcher at 3B:F734"
        ),
    )
    parser.add_argument(
        "--probe-storage-global-templates", action="store_true",
        help=(
            "exploration only: decode the original compiler initializer and "
            "restore all data-bus segment-33 copy records from their "
            "segment-50 PRG templates to test the missing Harvard data view"
        ),
    )
    parser.add_argument(
        "--probe-rom-02-c588-return", action="store_true",
        help=(
            "compatibility no-op: 02:C588 is now always reconstructed as a "
            "guest normal-return diagnostic marker"
        ),
    )
    parser.add_argument(
        "--probe-rom-0b-ccd2-zero", action="store_true",
        help=(
            "exploration only: install a guest RB1=0 return at the four-site "
            "five-word resident-ROM entry 0B:CCD2"
        ),
    )
    parser.add_argument(
        "--probe-stop-after-overlay-install", action="store_true",
        help=(
            "exploration only: stop immediately after recovered executable "
            "overlays are installed, before entering 20:026A"
        ),
    )
    parser.add_argument(
        "--initializer-probe", action="store_true",
        help=(
            "exploration only: run vendor initializer with sentinel ROM data "
            "and stop at 03:026A"
        ),
    )
    parser.add_argument(
        "--initializer-overlay-probe", action="store_true",
        help=(
            "run the nine-copy initializer with exact +0x1D linked PRG "
            "source storage, continue through 20:026A, and exercise all "
            "recovered runtime overlays"
        ),
    )
    parser.add_argument(
        "--factory-linked-startup", action="store_true",
        help=(
            "execute the recovered factory linked order 33:4F50 -> "
            "33:603C -> 11:4560 -> 07:7FE4 -> 03:026A; requires "
            "--initializer-overlay-probe and --probe-system-main"
        ),
    )
    parser.add_argument(
        "--reconstruct-resident-root-desktop", action="store_true",
        help=(
            "reconstruct the missing resident cold-start policy which "
            "selects native menu path zero; uses guest DMCU stores, does "
            "not inject a keyboard event"
        ),
    )
    parser.add_argument(
        "--dual-initializer-probe", action="store_true",
        help=(
            "exploration only: run both vendor initializer chains and stop "
            "at the unresolved 07:7FE4 continuation"
        ),
    )
    parser.add_argument(
        "--preserve-metadata-block-probe", action="store_true",
        help=(
            "exploration only: make 02:BDD6 report success without erasing "
            "physical block one, to isolate the page-0x3f metadata boundary"
        ),
    )
    args = parser.parse_args()

    if sum((args.initializer_probe, args.initializer_overlay_probe,
            args.dual_initializer_probe)) > 1:
        parser.error("initializer probe modes are mutually exclusive")
    if args.factory_linked_startup and not (
            args.initializer_overlay_probe and args.probe_system_main):
        parser.error(
            "--factory-linked-startup requires "
            "--initializer-overlay-probe and --probe-system-main"
        )
    if args.reconstruct_resident_root_desktop and not (
            args.factory_linked_startup and args.probe_system_main):
        parser.error(
            "--reconstruct-resident-root-desktop requires "
            "--factory-linked-startup and --probe-system-main"
        )
    if args.probe_rom_08_427e_return and not args.initializer_overlay_probe:
        parser.error(
            "--probe-rom-08-427e-return requires "
            "--initializer-overlay-probe"
        )
    if args.probe_rom_03_4124_zero and not (
            args.initializer_overlay_probe and
            args.probe_rom_08_427e_return):
        parser.error(
            "--probe-rom-03-4124-zero requires "
            "--initializer-overlay-probe and --probe-rom-08-427e-return"
        )
    if args.probe_rom_01_0200_return and not (
            args.initializer_overlay_probe and
            args.probe_rom_08_427e_return):
        parser.error(
            "--probe-rom-01-0200-return requires "
            "--initializer-overlay-probe and --probe-rom-08-427e-return"
        )
    if args.probe_continue_event_loop and not (
            args.initializer_overlay_probe and
            args.probe_rom_08_427e_return and
            args.probe_rom_03_4124_zero):
        parser.error(
            "--probe-continue-event-loop requires "
            "--initializer-overlay-probe, --probe-rom-08-427e-return, and "
            "--probe-rom-03-4124-zero"
        )
    if (args.probe_dispatch_activation and
            not (args.probe_continue_event_loop or args.probe_system_main)):
        parser.error(
            "--probe-dispatch-activation requires "
            "--probe-continue-event-loop or --probe-system-main"
        )
    if args.probe_lcd_power_on and not args.probe_continue_event_loop:
        parser.error(
            "--probe-lcd-power-on requires --probe-continue-event-loop"
        )
    if (args.probe_stop_after_overlay_install and
            not args.initializer_overlay_probe):
        parser.error(
            "--probe-stop-after-overlay-install requires "
            "--initializer-overlay-probe"
        )
    if args.probe_app_init_callback and not args.initializer_overlay_probe:
        parser.error(
            "--probe-app-init-callback requires --initializer-overlay-probe"
        )
    if args.probe_system_main and not args.initializer_overlay_probe:
        parser.error(
            "--probe-system-main requires --initializer-overlay-probe"
        )
    if args.probe_system_main and not args.probe_rom_01_0200_return:
        parser.error(
            "--probe-system-main requires --probe-rom-01-0200-return"
        )
    if args.probe_system_main and (
            args.probe_continue_event_loop or args.probe_lcd_power_on or
            args.probe_app_init_callback):
        parser.error(
            "--probe-system-main is incompatible with synthetic "
            "continuation probes"
        )
    if (args.probe_resident_app_state_guard and
            not args.probe_system_main):
        parser.error(
            "--probe-resident-app-state-guard requires --probe-system-main"
        )
    if (args.probe_storage_global_templates and
            not args.probe_system_main):
        parser.error(
            "--probe-storage-global-templates requires --probe-system-main"
        )
    if (args.probe_stop_after_scheduler_return and
            not args.probe_system_main):
        parser.error(
            "--probe-stop-after-scheduler-return requires "
            "--probe-system-main"
        )
    if (args.probe_stop_before_scheduler_entry and
            not args.probe_system_main):
        parser.error(
            "--probe-stop-before-scheduler-entry requires "
            "--probe-system-main"
        )
    if (args.probe_stop_before_scheduler_entry and
            args.probe_stop_after_scheduler_return):
        parser.error(
            "--probe-stop-before-scheduler-entry and "
            "--probe-stop-after-scheduler-return are mutually exclusive"
        )
    if args.probe_fixed_launch_wrapper and not args.probe_system_main:
        parser.error(
            "--probe-fixed-launch-wrapper requires --probe-system-main"
        )
    if (args.probe_fixed_launch_wrapper and
            (args.probe_stop_before_scheduler_entry or
             args.probe_stop_after_scheduler_return or
             args.probe_generic_main_menu or
             args.probe_direct_generic_menu or
             args.probe_factory_default_catalogue)):
        parser.error(
            "--probe-fixed-launch-wrapper and alternate scheduler probes are "
            "mutually exclusive"
        )
    if args.probe_generic_main_menu and not args.probe_system_main:
        parser.error(
            "--probe-generic-main-menu requires --probe-system-main"
        )
    if (args.probe_generic_main_menu and
            not args.probe_storage_global_templates):
        parser.error(
            "--probe-generic-main-menu requires "
            "--probe-storage-global-templates"
        )
    if (args.probe_generic_main_menu and
            (args.probe_stop_before_scheduler_entry or
             args.probe_stop_after_scheduler_return or
             args.probe_direct_generic_menu or
             args.probe_factory_default_catalogue)):
        parser.error(
            "--probe-generic-main-menu and scheduler-stop probes are "
            "mutually exclusive"
        )
    if args.probe_direct_generic_menu and not args.probe_system_main:
        parser.error(
            "--probe-direct-generic-menu requires --probe-system-main"
        )
    if (args.probe_direct_generic_menu and
            (args.probe_stop_before_scheduler_entry or
             args.probe_stop_after_scheduler_return or
             args.probe_factory_default_catalogue)):
        parser.error(
            "--probe-direct-generic-menu and scheduler-stop probes are "
            "mutually exclusive"
        )
    if (args.probe_factory_default_catalogue and
            not args.probe_system_main):
        parser.error(
            "--probe-factory-default-catalogue requires --probe-system-main"
        )
    if (args.probe_factory_default_catalogue and
            not args.factory_linked_startup):
        parser.error(
            "--probe-factory-default-catalogue requires "
            "--factory-linked-startup"
        )
    if (args.probe_factory_default_catalogue and
            (args.probe_stop_before_scheduler_entry or
             args.probe_stop_after_scheduler_return)):
        parser.error(
            "--probe-factory-default-catalogue and scheduler-stop probes "
            "are mutually exclusive"
        )
    PROGRAM_SOURCE = args.program.resolve()
    PROVISION_TRIGGER_TARGET = args.provision_trigger_target
    if not 0 <= PROVISION_TRIGGER_TARGET <= 0xFFFFFF:
        parser.error("--provision-trigger-target must be a 24-bit address")
    if not PROGRAM_SOURCE.is_file():
        parser.error(f"program source not found: {PROGRAM_SOURCE}")
    if PROGRAM_SOURCE.stat().st_size != 0x400000:
        parser.error(
            f"program source must be 4 MiB: {PROGRAM_SOURCE} "
            f"has {PROGRAM_SOURCE.stat().st_size} bytes"
        )

    image = build_image(
        args.startup_context, args.probe_font_lookup, args.initializer_probe,
        args.initializer_overlay_probe, args.dual_initializer_probe,
        args.probe_rom_08_427e_return, args.probe_rom_03_4124_zero,
        args.probe_continue_event_loop, args.probe_dispatch_activation,
        args.probe_lcd_power_on, args.probe_stop_after_overlay_install,
        args.probe_app_init_callback, args.probe_system_main,
        args.probe_rom_01_0200_return,
        args.probe_resident_app_state_guard,
        args.preserve_metadata_block_probe,
        args.probe_storage_global_templates,
        args.probe_rom_02_c588_return,
        args.probe_stop_after_scheduler_return,
        args.probe_rom_0b_ccd2_zero,
        args.probe_stop_before_scheduler_entry,
        args.probe_fixed_launch_wrapper,
        args.probe_generic_main_menu,
        args.probe_direct_generic_menu,
        args.probe_factory_default_catalogue,
        args.factory_linked_startup,
        args.reconstruct_resident_root_desktop,
    )
    args.output.write_bytes(image)
    manifest_path = args.manifest or args.output.with_suffix(".json")
    manifest_path.write_text(
        json.dumps(manifest(image, args.startup_context,
                            args.probe_font_lookup,
                            args.initializer_probe,
                            args.initializer_overlay_probe,
                            args.dual_initializer_probe,
                            args.probe_rom_08_427e_return,
                            args.probe_rom_03_4124_zero,
                            args.probe_continue_event_loop,
                            args.probe_dispatch_activation,
                            args.probe_lcd_power_on,
                            args.probe_stop_after_overlay_install,
                            args.probe_app_init_callback,
                            args.probe_system_main,
                            args.probe_rom_01_0200_return,
                            args.probe_resident_app_state_guard,
                            args.preserve_metadata_block_probe,
                            args.probe_storage_global_templates,
                            args.probe_rom_02_c588_return,
                            args.probe_stop_after_scheduler_return,
                            args.probe_rom_0b_ccd2_zero,
                            args.probe_stop_before_scheduler_entry,
                            args.probe_fixed_launch_wrapper,
                            args.probe_generic_main_menu,
                            args.probe_direct_generic_menu,
                            args.probe_factory_default_catalogue,
                            args.factory_linked_startup,
                            args.reconstruct_resident_root_desktop), indent=2)
        + "\n",
        encoding="utf-8"
    )
    print(f"wrote {len(image):,} bytes to {args.output.resolve()}")
    print(f"wrote {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
