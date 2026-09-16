#ifndef QEMU_DMCU_CPU_H
#define QEMU_DMCU_CPU_H

#include "cpu-qom.h"
#include "exec/cpu-defs.h"

#ifdef CONFIG_USER_ONLY
#error "DMCU does not support user mode"
#endif

#define CPU_RESOLVING_TYPE TYPE_DMCU_CPU
#define TCG_GUEST_DEFAULT_MO 0

#define MMU_CODE_IDX 0
#define MMU_DATA_IDX 1
#define MMU_UNBANKED_IDX 2
#define MMU_INTERNAL_IDX 3
#define MMU_PHYSICAL_DATA_IDX 4

#define DMCU_AS_DATA 0
#define DMCU_AS_CODE 1
#define DMCU_AS_INTERNAL 2

/* Host execution flow only, not an architectural register or guest state. */
typedef enum DMCUExecResult {
    DMCU_EXEC_EXIT = 0,       /* Return to cpu_exec for arbitration. */
    DMCU_EXEC_NEXT = 1,       /* Safe sequential successor in this TB. */
    DMCU_EXEC_LOOKUP = 2,     /* Safe non-sequential PC: look up a new TB. */
} DMCUExecResult;

#define DMCU_PROGRAM_BASE 0x00200000u
#define DMCU_PROGRAM_SIZE 0x00400000u
#define DMCU_DATA_SIZE    0x01000000u
#define DMCU_SOC_ROM_SIZE 0x00200000u
#define DMCU_UNBANKED_LOW_PAGE_BASE 0x01000000u
#define DMCU_UNBANKED_SFR_PAGE_BASE 0x01000800u
#define DMCU_UNBANKED_PAGE_SIZE     0x00000800u
#define DMCU_ROM03_BASE   0x00030000u
#define DMCU_ROM03_SIZE   0x00010000u
/* Host-side ROM-HLE diagnostics only.  The real ST7529 is MMIO at F00000. */
#define DMCU_LCD_FB_BASE  0x00ef0000u
#define DMCU_LCD_WIDTH    240u
#define DMCU_LCD_HEIGHT   120u
#define DMCU_LCD_STRIDE   (DMCU_LCD_WIDTH / 8)
#define DMCU_LCD_FB_SIZE  (DMCU_LCD_STRIDE * DMCU_LCD_HEIGHT)

/* Pre-SCALL words retained when execution enters an unavailable SoC ROM. */
#define DMCU_ROM_TRACE_STACK_WORDS 8
/* Last guest instructions retained to diagnose an eventual strict-ROM stop. */
#define DMCU_EXEC_TRACE_WORDS 32
#define DMCU_FOREGROUND_TRACE_WORDS 32
#define DMCU_CONTROL_TRACE_WORDS 1024
#define DMCU_NPE_LOW51_EXEC_HISTORY_WORDS 32
#define DMCU_NPE_UI_REENTRY_HISTORY_WORDS 32
#define DMCU_NPE_UI_REENTRY_STACK_WORDS 16
#define DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS 16
#define DMCU_NPE_OPERATION_ONE_ACTION_WRITE_FRAMES 4
#define DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS 16
#define DMCU_RESOURCE_OPEN_CONTINUATION_STACK_WORDS 8
#define DMCU_APPLICATION_TRACE_ENTRIES 191
/* Stable entry in the application trace table for the return from the exact
 * 33:4ECC foreground event mapper at 20:2E9E. */
#define DMCU_APPLICATION_KEYMAP_RETURN_TRACE_INDEX 85
#define DMCU_MATRIX_COMPLETION_TRACE_SLOTS 16
#define DMCU_MATRIX_COMPLETION_TRACE_STACK_WORDS 4
#define DMCU_RESIDENT16_RETURN_TRACE_SLOTS 32
#define DMCU_GRAPHICS_CONTINUATION_TRACE_SLOTS 16
#define DMCU_REGION_MASK_TRACE_SLOTS 16
#define DMCU_RESOURCE_OPEN_TRACE_SLOTS 8
#define DMCU_RESOURCE_BASE_COUNT_INPUTS 7
#define DMCU_FACTORY_RECORD_TRACE_SLOTS 64
#define DMCU_RESOURCE_IO_TRACE_SLOTS 32
#define DMCU_STORAGE_GEOMETRY_TRACE_SLOTS 32
#define DMCU_ROOT_METADATA_TRACE_SLOTS 128
#define DMCU_FILE_ROOT_POOL_TRACE_SLOTS 64
#define DMCU_FILE_ROOT_POOL_NODES 6
#define DMCU_FILE_ROOT_PATH_BYTES 16
#define DMCU_FILE_ROOT_RELEASE_TRACE_SLOTS 64
#define DMCU_ROOT_OBJECT_INIT_TRACE_SLOTS 8
#define DMCU_ROOT_OBJECT_INIT_STACK_WORDS 16
#define DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS 128
#define DMCU_MENU_PATH_WRITE_TRACE_SLOTS 64
#define DMCU_ROOT_RENDER_FLAG_TRACE_SLOTS 32
#define DMCU_ROOT_OBJECT_FAIL_GPRS 8
#define DMCU_ROOT_OBJECT_FAIL_LOCALS 9
#define DMCU_ROOT_OBJECT_FAIL_WORDS 16
#define DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS 8
#define DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS 32
#define DMCU_FILE_RECORD_SELECTOR_BYTES 16
#define DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS 8
#define DMCU_NPE_BROWSER_LAYOUT_TRACE_DEPTH 4
#define DMCU_NPE_BROWSER_LAYOUT_OBJECT_WORDS 48
#define DMCU_NPE_OBJECT_MASK_SNAPSHOT_WORDS 5
/* One exact, caller-owned browser/render object constructed by 1B:23B8 and
 * passed to 21:CEF4.  The byte snapshots and overlapping-write ring are
 * diagnostics only; they never supply or repair guest-visible state. */
#define DMCU_NPE_RENDER_OBJECT_BYTES 48
#define DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS 128
#define DMCU_NPE_RENDER_OBJECT_STACK_WORDS 8
/* One observer-only snapshot of the object passed by the NewJourney movement
 * controller to the exact resident 1D:831E renderer. */
#define DMCU_NPE_GAME_RENDER_OBJECT_WORDS 32
/* One bounded, observer-only trace of the operation-1 item-count builder.
 * Exact 29:9746 enumerates directory records through 33:1894/33:443E,
 * filters them through 27:CBE4, and accumulates each accepted contribution
 * through 33:6C0A.  The snapshots expose that guest path without supplying a
 * record, count, or callback result. */
#define DMCU_NPE_MATERIALIZE_TRACE_SLOTS 64
#define DMCU_NPE_MATERIALIZE_RECORD_BYTES 72
#define DMCU_NPE_MATERIALIZE_PATH_BYTES 48
/* Three exact callback targets owned by the operation-1 browser object:
 * the constructor's render pointer, the value observed after layout, and
 * the input callback.  These slots are diagnostic labels, not dispatch
 * substitutes. */
#define DMCU_NPE_OPERATION_CALLBACK_SLOTS 3
#define DMCU_NPE_OPERATION_CALLBACK_STACK_WORDS 4
/* Exact, observer-only checkpoints for resident NPE_FORMAT_DISPATCH at
 * 1B:7A20.  The three slots correspond to its three calls to 2C:C07E.
 * Every field is diagnostic state: no field below is consumed by guest
 * execution or used to repair a register, result, or control-flow edge. */
#define DMCU_NPE_FORMAT_MEMCMP_SLOTS 3
#define DMCU_NPE_FORMAT_SAMPLE_BYTES 16
#define DMCU_NPE_FORMAT_FOLLOWUP_MAX_STEPS 256
/* Exact mode-one NPE transform at 2D:C31E -> 33:03B2 -> 1C:CCD4.
 * Retain the five-word outer call, six-word resident call, and bounded input
 * samples so an original data-validation failure can be distinguished from
 * a missing code body without modifying guest state. */
#define DMCU_NPE_TRANSFORM_OUTER_ARGUMENT_WORDS 5
#define DMCU_NPE_TRANSFORM_RESIDENT_ARGUMENT_WORDS 6
#define DMCU_NPE_TRANSFORM_SAMPLE_BYTES 64
/* A4:54E8 is the far stream/object slot passed to the mode-one transform.
 * Keep every bounded write plus the exact linked initializer/open call
 * boundaries so a missing producer can be separated from a later clear. */
#define DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS 16
#define DMCU_NPE_STREAM_OPEN_ARGUMENT_WORDS 5
/* First entry into the indirectly-dispatched 2F:DF06 engine.  Preserve both
 * sides of the control-transfer stack so its table owner can be identified
 * without changing the selected application, registers, memory, or result. */
#define DMCU_NPE_DF06_STACK_WORDS 8
/* First bounded data-bus accesses to 32:4956..497B.  Reads and writes are
 * retained separately to identify the real guest installation lifetime and
 * to test, rather than assume, whether an earlier owner exists.  These fields
 * are observer output only and are never consumed by execution. */
#define DMCU_NPE_LITERAL_DATA_TRACE_SLOTS 64
/* Six source-proven children of the exact 25:5460 resource/context check.
 * These slots retain only architectural observations made at the SCALL and
 * return boundaries; they do not substitute a child or alter its result. */
#define DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS 6
/* Retain the ordered error-word writes across nested children and the
 * caller-side overwrite which follows their return. */
#define DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS 12
/* Six computed near returns in the exact resident 1A:DEAA compare family.
 * Their inline target tables are visible through the Harvard data bus. */
#define DMCU_APPLICATION_COMPARE_RET_SITES 6
/* One complete, read-only control/locals trace for the first invocation of
 * the restored 28:94C2 result scanner.  It is deliberately independent of
 * the generic control ring so later modal polling cannot overwrite the first
 * failed scanner decision. */
#define DMCU_RESULT_SCANNER_TRACE_SLOTS 192
#define DMCU_RESULT_SCANNER_LOCAL_WORDS 14
/* Four fixed work-table allocation decisions at the front of the exact
 * 1B:23B8 application/file browser. */
#define DMCU_OPERATION_BROWSER_ALLOC_SLOTS 4
/* Bounded, read-only provenance for the writable operation-browser UI data
 * consumed by exact resident 02:0FB6.  Keep the three ranges separate:
 * three 0x94-byte UI records, twenty six-byte operation records, and the two
 * result words written by the continuation itself. */
#define DMCU_OPERATION_UI_DATA_RANGES 3
#define DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS 128
#define DMCU_FILE_COMPONENT_FRAME_WORDS 16
#define DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS 128
#define DMCU_FILE_OPEN_ERROR_TRACE_SLOTS 64
#define DMCU_FILE_COMMIT_CHILD_SLOTS 12
#define DMCU_FILE_PATH_TRACE_SLOTS 16
#define DMCU_FILE_PATH_TRACE_BYTES 24
#define DMCU_USERINFO_PATH_TRACE_SLOTS 16
#define DMCU_USERINFO_FLOW_TRACE_SLOTS 128
#define DMCU_FILE_WRITE_RETURN_TRACE_SLOTS 32
#define DMCU_USERINFO_CLOSE_STACK 16
#define DMCU_USERINFO_STATE_CODE_WORDS 16
#define DMCU_FILE_WRAPPER_STACK_WORDS 12
#define DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS 64
#define DMCU_STORAGE_LOOKUP_TRACE_SLOTS 8
#define DMCU_STORAGE_LOOKUP_HEAD_BYTES 36
#define DMCU_STORAGE_LOOKUP_PARTITION_BYTES 16
#define DMCU_STORAGE_LOOKUP_RECORD_WORDS 19
#define DMCU_APPLICATION_INIT_F3C6_STACK_WORDS 12
#define DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS 32
#define DMCU_RESOURCE_CANDIDATE_RECORD_WORDS 16
#define DMCU_RESOURCE_CANDIDATE_ARGUMENT_WORDS 6
#define DMCU_FAR_COPY_CALL_TRACE_SLOTS 32
#define DMCU_INDIRECT_CALLBACK_TRACE_SLOTS 8
#define DMCU_INDIRECT_CALLBACK_STACK_WORDS 12
#define DMCU_INDIRECT_CALLBACK_OBJECT_WORDS 12
#define DMCU_INDIRECT_OBJECT_WRITE_SLOTS 48
#define DMCU_INDIRECT_OBJECT_WRITE_FRAME_WORDS 4
#define DMCU_UI_RECORD_FLOW_SLOTS 96
#define DMCU_UI_RECORD_STACK_WORDS 10
#define DMCU_UI_RECORD_FRAME_WORDS 8
#define DMCU_UI_RECORD_OBJECT_WORDS 8
#define DMCU_UI_RECORD_GLOBAL_WORDS 22
#define DMCU_UI_RECORD_WRITE_SLOTS 64
#define DMCU_STATE_IMPORT_HISTORY_SLOTS 8
#define DMCU_STATE_IMPORT_HISTORY_INPUT_WORDS 16
#define DMCU_STATE_IMPORT_HISTORY_GLOBAL_WORDS 15
#define DMCU_STATE_IMPORT_HISTORY_DISPATCH_WORDS 13
#define DMCU_STATE_SELECTOR_TRACE_SLOTS 16
#define DMCU_START_CALLBACK_TRACE_SLOTS 128
#define DMCU_MENU_CONTEXT_RELEASE_TRACE_SLOTS 16
#define DMCU_MENU_CONTEXT_RELEASE_STACK_WORDS 12
#define DMCU_START_LATE31_ENTRY_TRACE_SLOTS 32
#define DMCU_START_LATE31_ENTRY_STACK_WORDS 12
#define DMCU_START_BOUNDED_CALL_TRACE_SLOTS 16
#define DMCU_START_BOUNDED_CALL_STACK_WORDS 12
#define DMCU_START_MENU_DISPATCH_TRACE_SLOTS 16
#define DMCU_START_MENU_DISPATCH_GPR_WORDS 16
#define DMCU_START_MENU_DISPATCH_STACK_WORDS 16
#define DMCU_START_MENU_DISPATCH_LOCAL_BYTES 80
#define DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS 32
#define DMCU_START_PAGE_RETURN_GPR_WORDS 11
#define DMCU_START_PAGE_RETURN_ARGUMENT_WORDS 6
#define DMCU_START_PAGE_RETURN_FRAME_DEPTH 8
#define DMCU_START_OBJECT_WRITE_TRACE_SLOTS 256
#define DMCU_START_CONTEXT_CODE_WRITE_SLOTS 64
#define DMCU_MANAGER_STATE_WRITE_SLOTS 64
#define DMCU_CONTEXT_DATA_TRACE_ENTRIES 64
#define DMCU_OBJECT_INIT_TRACE_SLOTS 4
#define DMCU_CB62_TRACE_SLOTS 16
#define DMCU_FONT_CONFIG_TRACE_SLOTS 16
#define DMCU_COLOR_TRACE_SLOTS 32
#define DMCU_FONT_BLIT_TRACE_SLOTS 64
#define DMCU_GLYPH_DRAW_TRACE_SLOTS 512
#define DMCU_START_GLYPH_TRACE_SLOTS 16
#define DMCU_START_GLYPH_TRACE_FRAMES 8
#define DMCU_NPE_GLYPH_TRACE_SLOTS 256
#define DMCU_NPE_GLYPH_TRACE_FRAMES 5
#define DMCU_NPE_TEXT_BOX_TRACE_SLOTS 8
#define DMCU_NPE_TEXT_BOX_TRACE_SAMPLE_BYTES 48
#define DMCU_NPE_CONTROL_TRACE_SLOTS 256
#define DMCU_NPE_CONTROL_TRACE_MAX_TRANSITIONS 1048576u
#define DMCU_NPE_LOW51_ENTRY_GPR_WORDS 16
#define DMCU_NPE_LOW51_ENTRY_STACK_WORDS 16
#define DMCU_NPE_FILE_READ_TRACE_SLOTS 64
#define DMCU_NPE_FAR_COPY_TRACE_SLOTS 64
#define DMCU_NPE_GAME_FRAME_STAGES 12
#define DMCU_NPE_GAME_BRANCH_TRACE_SLOTS 16
#define DMCU_NPE_GAME_DRAW_CHILD_SITES 7
#define DMCU_NPE_GAME_DRAW_TRACE_SLOTS 128
#define DMCU_NPE_GAME_DATA_TRACE_SLOTS 64
#define DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS 128
#define DMCU_NPE_GAME_TABLE_IO_SLOTS 16
#define DMCU_NPE_GAME_HIGH_STREAM_IO_SLOTS 64
#define DMCU_NPE_TRANSITION_LEAF_SLOTS 16
#define DMCU_NPE_TRANSITION_GATE_SLOTS 16
#define DMCU_RESOURCE_SPECIAL_TRACE_SLOTS 64
#define DMCU_RESOURCE_PERSIST_TRACE_SLOTS 64
#define DMCU_RESOURCE_PERSIST_ARGUMENT_WORDS 6
#define DMCU_RESOURCE_PERSIST_TABLE_WORDS 7
#define DMCU_INVALID_CONTROL_GPR_WORDS 16
#define DMCU_INVALID_CONTROL_STACK_WORDS 16
#define DMCU_INVALID_CONTROL_FRAME_WORDS 16
#define DMCU_SETTINGS_INPUT_TRACE_SLOTS 128
#define DMCU_SETTINGS_INPUT_GPR_WORDS 16
#define DMCU_SETTINGS_INPUT_STACK_WORDS 16
#define DMCU_SETTINGS_INPUT_FRAME_WORDS 16
#define DMCU_SOUND_SETTINGS_TRACE_SLOTS 64
#define DMCU_NPE_GAME_STREAM_PAGE_SHIFT 12
#define DMCU_NPE_GAME_STREAM_PAGE_COUNT 4096
#define DMCU_NPE_GAME_TABLE_COPY_SLOTS 256
#define DMCU_NPE_GAME_TABLE_COPY_SAMPLE_BYTES 8
#define DMCU_NPE_GAME_GRID_WRITE_SLOTS 32
#define DMCU_NPE_GAME_LOADER_EDGE_SLOTS 64
#define DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS 32
#define DMCU_NPE_GAME_CONTROL_WRITE_SLOTS 64
#define DMCU_FONT_COPY_TRACE_SLOTS 512
#define DMCU_NATIVE_REFRESH_TRACE_SLOTS 32
#define DMCU_NATIVE_FRAMEBUFFER_BYTES (240 * 120 / 2)
#define DMCU_TEXT_TRACE_SLOTS 16
#define DMCU_PIM_TRACE_SLOTS 16
#define DMCU_DESKTOP_TEXT_TRACE_SLOTS 64
#define DMCU_DESKTOP_FB_TRACE_SLOTS 64
#define DMCU_DESKTOP_BLIT_TRACE_SLOTS 64
#define DMCU_ROOT_RESOURCE_TRACE_SLOTS 64
#define DMCU_ROOT_HEADER_IO_TRACE_SLOTS 32
#define DMCU_ROOT_TOP_BITMAP_BYTES 2650
#define DMCU_ROOT_TOP_COPY_TRACE_SLOTS 16
#define DMCU_ROOT_TOP_FAR_COPY_TRACE_SLOTS 64
#define DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS 32
#define DMCU_CLOCK_FORMAT_OUTPUT_TRACE_SLOTS 64
#define DMCU_CLOCK_FORMAT_BUFFER_BYTES 24
#define DMCU_CLOCK_FORMAT_STRING_BYTES 12
#define DMCU_CLOCK_FORMAT_VARARG_WORDS 8
#define DMCU_CLOCK_RASTER_TRACE_SLOTS 8
#define DMCU_CLOCK_RASTER_TRACE_STAGES 4
#define DMCU_CLOCK_RASTER_TEXT_BYTES 8
#define DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS 64
#define DMCU_CLOCK_RESOURCE_RELEASE_STAGES 8
#define DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS 16
#define DMCU_NPE_RESOURCE_RETURN_TRACE_STAGES 12
#define DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS 64
#define DMCU_CLOCK_STREAM_OBJECT_BYTES 48
#define DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS 16
#define DMCU_CLOCK_STREAM_MOVE_ARGUMENT_WORDS 6
#define DMCU_CLOCK_STREAM_MOVE_SAMPLE_BYTES 8
#define DMCU_CLOCK_SCAN_ARGUMENT_WORDS 12
#define DMCU_CLOCK_SCAN_LOCAL_WORDS 20
#define DMCU_CLOCK_CORE_CALL_TRACE_SLOTS 96
#define DMCU_SELECTOR_STATE_TRACE_SLOTS 32
#define DMCU_RESOURCE_COUNT_TRACE_SLOTS 16
#define DMCU_RESOURCE_COUNT_TRACE_FRAMES 6
#define DMCU_RESOURCE_COUNT_TRACE_FRAME_WORDS 10
#define DMCU_APPLICATION_STATE_WRITE_FRAMES 6
#define DMCU_ROOT_EXIT_STATE_TRACE_SLOTS 16
#define DMCU_EVENT_STATE_TRACE_SLOTS 64
#define DMCU_USB_BOOT_TRACE_SLOTS 32
#define DMCU_USB_BOOT_MILESTONES 5
#define DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS 128
#define DMCU_UNBANKED_SFR_WRITE_BUCKETS 16
#define DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS 128
#define DMCU_BANKED_FXXX_WRITE_BUCKETS 16
#define DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS 128
#define DMCU_DIRECT_SFR_WRITE_REGS 0xf0

#define DMCU_SFR_SOCR     0x00
#define DMCU_SOCR_IE      0x8000u
#define DMCU_SOCR_UP      0x4000u
#define DMCU_SOCR_RAM     0x0002u
#define DMCU_SOCR_NSEG    0x0020u
#define DMCU_SOCR_FR      0x0008u
#define DMCU_SOCR_MAS     0x0010u
#define DMCU_PSR_MV       0x0040u
#define DMCU_PSR_MS       0x0080u
#define DMCU_PSR_CIRQ     0x4000u
#define DMCU_PSR_CPRI     0x3000u
#define DMCU_ICR_FIRST    0x50u
#define DMCU_ICR_COUNT    32u
#define DMCU_ICR_EN       0x0001u
#define DMCU_ICR_RQ       0x0002u
#define DMCU_ICR_PRI      0x0030u
#define DMCU_ICR_ED       0x0040u
#define DMCU_DTUC_FIRST   0x21u
#define DMCU_DTU_CHANNELS 4u
/* NP560's 24:98FC driver chunks at 03FF, unlike the older patent's
 * eight-bit COUNT illustration. Other control bits follow figs. 16/17. */
#define DMCU_DTUC_COUNT   0x03ffu
#define DMCU_DTUC_DDS     0x0800u
#define DMCU_DTUC_SDS     0x1000u
#define DMCU_DTUC_WBT     0x2000u
#define DMCU_DTUC_INC     0xc000u
#define DMCU_SFR_T0       0x25u
#define DMCU_SFR_T0P      0x26u
#define DMCU_SFR_T0C      0x27u
#define DMCU_SFR_T1       0x28u
#define DMCU_SFR_T1P      0x29u
#define DMCU_SFR_T1C      0x2au
#define DMCU_SFR_T2       0x2bu
#define DMCU_SFR_T2P      0x2cu
#define DMCU_SFR_T2C      0x2du
#define DMCU_SFR_CLKCON   0x2eu
#define DMCU_SFR_TBC      0x2fu
#define DMCU_SFR_PLL      0xe9u
#define DMCU_SFR_AUDIO_PLL 0xeau
#define DMCU_SFR_DAC0     0x70u
#define DMCU_SFR_DAC1     0x71u
#define DMCU_SFR_DACC     0x72u

static inline bool dmcu_sfr_has_timing(unsigned reg)
{
    /* ICR.RQ is modified by the I/O thread too. A CPU control write must
     * not race a device's read/OR/write and lose EN/ED/PRI. The same device
     * arbitration reads DTUC, so its register view uses the same lock. */
    return (reg >= DMCU_DTUC_FIRST && reg <= DMCU_SFR_TBC) ||
           (reg >= DMCU_ICR_FIRST && reg < DMCU_ICR_FIRST + DMCU_ICR_COUNT) ||
           (reg >= DMCU_SFR_DAC0 && reg <= DMCU_SFR_DACC) ||
           reg == DMCU_SFR_PLL || reg == DMCU_SFR_AUDIO_PLL;
}
#define DMCU_SFR_SB       0x02
#define DMCU_SFR_DS0      0x10
#define DMCU_SFR_DS1      0x11
/* Original 28:2C74/2E04 saves REG13 and sets the X0 ring length to 0600. */
#define DMCU_SFR_XM0      0x13
/* Original 0C:7142 clears these before MAC [X2++],[Y2++]. */
#define DMCU_SFR_XM2      0x17
#define DMCU_SFR_YM2      0x1d
/* Original 08:41E2 writes CIRQ/CPRI through REG[01]; F102 is its data view.
 * REG[81] is a distinct software register, not the architectural PSR. */
#define DMCU_SFR_PSW      0x01

#define DMCU_FP 11
#define DMCU_SP 15

/* These flags describe the first transition which unwinds above the direct
 * root-menu probe's entry SP/FP.  Nested calls may only move below those
 * captured boundaries until the deliberately non-returning probe exits. */
#define DMCU_DIRECT_MENU_STACK_ESCAPE_SP  (1u << 0)
#define DMCU_DIRECT_MENU_STACK_ESCAPE_FP  (1u << 1)
#define DMCU_DIRECT_MENU_STACK_ESCAPE_IRQ (1u << 2)

#define DMCU_PSW_Z (1u << 0)
#define DMCU_PSW_C (1u << 1)
#define DMCU_PSW_N (1u << 2)
#define DMCU_PSW_V (1u << 3)

/* Suspended IRQ bookkeeping, not a replacement for the guest stack frame.
 * RETI always obtains PSR/CS/PC from RAM. Only repeat execution state and
 * diagnostic ownership need a host-side context while another IRQ runs. */
typedef struct DMCUInterruptContext {
    uint32_t interrupt_frame_size;
    uint32_t interrupt_frame_base;
    uint32_t interrupt_frame_expected_psw;
    uint32_t interrupt_frame_expected_cs;
    uint32_t interrupt_frame_expected_pc;
    uint32_t interrupt_last_entry_pc;
    uint32_t interrupt_last_entry_sp;
    uint32_t interrupt_foreground_fp_address;
    uint32_t interrupt_foreground_fp_expected;
    uint32_t interrupt_repeat_pc;
    uint32_t interrupt_repeat_end;
    uint32_t interrupt_repeat_count;
    uint32_t interrupt_repeat_block;
    uint32_t interrupt_single_repeat_pc;
    uint32_t interrupt_single_repeat_count;
    uint32_t irq_save_fp_save_expected;
    bool interrupt_repeat_saved;
    bool interrupt_frame_watch_active;
    bool interrupt_from_icr;
    bool irq_save_fp_watch_active;
} DMCUInterruptContext;

#define DMCU_DTU_CONFIG_TRACE_SLOTS 64
#define DMCU_DTU_REFILL_TRACE_SLOTS 64
/* Optional diagnostics only; not guest state or an interrupt latch. */
typedef struct DMCUDTURefillEvent {
    uint64_t completed_ns, accepted_ns, reloaded_ns, entries_at_completion;
    uint32_t completion_pc, accepted_pc, reload_pc, source, channel, cpu_entries;
    uint16_t count, socr, psr, critical, ignore_ds;
    bool pending, accepted;
} DMCUDTURefillEvent;

typedef struct DMCUDTUConfigEvent {
    uint32_t pc;
    uint16_t reg, old_value, value, sp, fp, ds0, ds1;
    uint16_t stack[8], dtu[4];
    bool in_interrupt;
} DMCUDTUConfigEvent;

#define DMCU_AUDIO_FILE_TRACE_SLOTS 64
typedef struct DMCUAudioFileEvent {
    uint32_t pc, previous_pc;
    uint16_t sp, fp, ds0, ds1, psw;
    uint16_t gpr[4], stack[16], locals[32], flags[3];
    bool in_interrupt;
} DMCUAudioFileEvent;

typedef struct CPUArchState {
    uint32_t pc;             /* byte-addressed CS:PC */
    uint32_t gpr[16];        /* 16-bit R0..R15 */
    uint32_t sfr[256];       /* 16-bit direct/SFR register file */
    uint32_t psw;            /* Z,C,N,V in bits 0..3 */
    bool irq_state_changed;  /* finish the instruction before arbitration */
    bool interrupt_from_icr;
    uint32_t interrupt_max_depth;
    uint32_t dtu_fault_sources; /* failed bus request, retry after reconfigure */
    uint64_t dtu_transfers[DMCU_DTU_CHANNELS];
    uint64_t dtu_completions[DMCU_DTU_CHANNELS];
    uint64_t dtu_refill_count, dtu_irq_entries[DMCU_ICR_COUNT];
    DMCUDTURefillEvent dtu_refill_pending[DMCU_DTU_CHANNELS];
    DMCUDTURefillEvent dtu_refill_trace[DMCU_DTU_REFILL_TRACE_SLOTS];
    /* Observer only, excluded from architectural migration state. RQ-only
     * ticks/acknowledgements do not evict the configuration writers. */
    uint64_t dtu_config_count;
    DMCUDTUConfigEvent dtu_config_trace[DMCU_DTU_CONFIG_TRACE_SLOTS];
    uint64_t audio_file_count;
    DMCUAudioFileEvent audio_file_trace[DMCU_AUDIO_FILE_TRACE_SLOTS];
    uint32_t interrupt_frame_size;
    uint32_t shift_buffer;   /* 16-bit DSP shift buffer */
    uint32_t se;             /* exponent-derivation result */
    /* REP uses SRC; REPB uses independent RC/RS/RE (CN1916884A pp120/122).
     * In particular a REP within a block must not erase the outer loop. */
    uint32_t single_repeat_pc;
    uint32_t single_repeat_count;
    uint32_t repeat_pc;
    uint32_t repeat_end;
    uint32_t repeat_count;
    uint32_t repeat_block;
    uint32_t interrupt_repeat_pc;
    uint32_t interrupt_repeat_end;
    uint32_t interrupt_repeat_count;
    uint32_t interrupt_repeat_block;
    uint32_t interrupt_single_repeat_pc;
    uint32_t interrupt_single_repeat_count;
    uint32_t interrupt_repeat_saves;
    uint32_t interrupt_repeat_restores;
    uint32_t interrupt_repeat_conflicts;
    bool interrupt_repeat_saved;
    uint64_t far_copy_repeat_saves;
    uint64_t far_copy_repeat_restores;
    uint32_t far_copy_repeat_entry_pc;
    uint32_t far_copy_repeat_return_pc;
    uint32_t far_copy_repeat_saved_count;
    uint32_t far_copy_repeat_gpr_mismatch_mask;
    uint16_t far_copy_repeat_saved_gpr[16];
    uint16_t far_copy_repeat_restore_gpr[16];
    uint16_t far_copy_repeat_saved_ds0;
    uint16_t far_copy_repeat_saved_ds1;
    uint16_t far_copy_repeat_restore_ds0;
    uint16_t far_copy_repeat_restore_ds1;
    uint64_t far_copy_call_trace_count;
    uint32_t far_copy_call_trace_from[DMCU_FAR_COPY_CALL_TRACE_SLOTS];
    uint32_t far_copy_call_trace_interrupts[DMCU_FAR_COPY_CALL_TRACE_SLOTS];
    uint16_t far_copy_call_trace_sp[DMCU_FAR_COPY_CALL_TRACE_SLOTS];
    uint16_t far_copy_call_trace_fp[DMCU_FAR_COPY_CALL_TRACE_SLOTS];
    uint16_t far_copy_call_trace_args[DMCU_FAR_COPY_CALL_TRACE_SLOTS][DMCU_RESOURCE_CANDIDATE_ARGUMENT_WORDS];
    uint32_t ignore_ds_count;
    /* Observer-only inventory of writes made through the IGNDS F000..FFFF
     * hardware window.  Total/bucket counts retain all writes; the bounded
     * ring retains only addresses not covered by a currently modelled NP560
     * peripheral so missing devices can be discovered from guest behaviour. */
    uint64_t unbanked_sfr_write_count;
    uint64_t unbanked_sfr_unknown_write_count;
    uint64_t unbanked_sfr_write_bucket[
        DMCU_UNBANKED_SFR_WRITE_BUCKETS];
    uint64_t unbanked_sfr_unknown_sequence[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    uint32_t unbanked_sfr_unknown_pc[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    uint16_t unbanked_sfr_unknown_logical[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    uint16_t unbanked_sfr_unknown_value[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    uint16_t unbanked_sfr_unknown_sp[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    uint16_t unbanked_sfr_unknown_fp[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    uint16_t unbanked_sfr_unknown_ds0[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    uint16_t unbanked_sfr_unknown_ds1[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    uint8_t unbanked_sfr_unknown_bits[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    bool unbanked_sfr_unknown_in_interrupt[
        DMCU_UNBANKED_SFR_WRITE_TRACE_SLOTS];
    /* The same discovery boundary for ordinary DS-translated stores whose
     * physical result lands in F000..FFFF.  The logical address is retained
     * separately because vendor code often reaches a physical peripheral
     * through a 7xxx operand with DS=1. */
    uint64_t banked_fxxx_write_count;
    uint64_t banked_fxxx_unknown_write_count;
    uint64_t banked_fxxx_write_bucket[DMCU_BANKED_FXXX_WRITE_BUCKETS];
    uint64_t banked_fxxx_unknown_sequence[
        DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    uint32_t banked_fxxx_unknown_pc[DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    uint16_t banked_fxxx_unknown_logical[
        DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    uint16_t banked_fxxx_unknown_physical[
        DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    uint16_t banked_fxxx_unknown_value[
        DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    uint16_t banked_fxxx_unknown_sp[DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    uint16_t banked_fxxx_unknown_fp[DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    uint16_t banked_fxxx_unknown_ds0[DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    uint16_t banked_fxxx_unknown_ds1[DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    uint8_t banked_fxxx_unknown_bits[DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    bool banked_fxxx_unknown_in_interrupt[
        DMCU_BANKED_FXXX_WRITE_TRACE_SLOTS];
    /* Direct REG[00..EF] writes are a separate hardware-discovery channel
     * from memory-mapped Fxxx stores.  SB, DS0/DS1 and PSW are architectural
     * CPU state and are deliberately excluded.  Per-register totals survive
     * a busy trace ring so input/idle scene deltas remain authoritative. */
    uint64_t direct_sfr_write_count;
    uint64_t direct_sfr_write_reg_count[DMCU_DIRECT_SFR_WRITE_REGS];
    uint64_t direct_sfr_write_sequence[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint32_t direct_sfr_write_pc[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint16_t direct_sfr_write_reg[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint16_t direct_sfr_write_old_value[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint16_t direct_sfr_write_new_value[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint16_t direct_sfr_write_sp[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint16_t direct_sfr_write_fp[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint16_t direct_sfr_write_ds0[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint16_t direct_sfr_write_ds1[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint8_t direct_sfr_write_bits[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    bool direct_sfr_write_in_interrupt[DMCU_DIRECT_SFR_WRITE_TRACE_SLOTS];
    uint32_t critical_count;
    uint32_t lcd_foreground;
    uint32_t lcd_background;
    uint32_t lcd_service_calls;
    uint32_t lcd_frames;
    uint32_t native_lcd_flush_calls;
    uint32_t native_lcd_flush_mode;
    uint32_t native_lcd_flush_source;
    uint32_t native_lcd_flush_nonzero;
    uint32_t native_lcd_flush_nonzero_calls;
    uint32_t native_lcd_flush_max_nonzero;
    uint32_t native_lcd_flush_mode_calls[4];
    uint32_t native_refresh_calls;
    uint32_t native_refresh_mode;
    uint32_t native_refresh_pointer;
    uint32_t native_refresh_back_entry_nonzero;
    uint32_t native_refresh_back_entry_hash;
    uint32_t native_refresh_front_entry_nonzero;
    uint32_t native_refresh_front_entry_hash;
    uint32_t native_refresh_copy_calls;
    uint32_t native_refresh_back_copy_nonzero;
    uint32_t native_refresh_back_copy_hash;
    uint32_t native_refresh_front_after_nonzero;
    uint32_t native_refresh_front_after_hash;
    uint32_t native_refresh_copy_mismatches;
    uint32_t native_refresh_back_nonzero_calls;
    uint32_t native_refresh_front_nonzero_calls;
    uint32_t native_refresh_preflush_back_nonzero;
    uint32_t native_refresh_preflush_back_hash;
    uint32_t native_refresh_preflush_front_nonzero;
    uint32_t native_refresh_preflush_front_hash;
    uint32_t native_refresh_trace_count;
    uint32_t native_refresh_trace_caller[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint32_t native_refresh_trace_parent[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint32_t native_refresh_trace_mode[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint32_t native_refresh_trace_pointer[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint32_t native_refresh_trace_back_nonzero[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint32_t native_refresh_trace_front_nonzero[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint16_t native_refresh_trace_state[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint16_t native_refresh_trace_resource[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint32_t native_refresh_mode_write_count;
    uint32_t native_refresh_mode_write_pc[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint8_t native_refresh_mode_write_old[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    uint8_t native_refresh_mode_write_new[DMCU_NATIVE_REFRESH_TRACE_SLOTS];
    bool root_entry_frame_valid;
    uint8_t root_entry_back_frame[DMCU_NATIVE_FRAMEBUFFER_BYTES];
    uint8_t root_entry_front_frame[DMCU_NATIVE_FRAMEBUFFER_BYTES];
    uint32_t native_back_nonzero_bytes;
    uint32_t native_back_peak_nonzero_bytes;
    uint32_t native_back_rises;
    uint32_t native_back_clears;
    uint32_t native_back_last_rise_pc;
    uint32_t native_back_last_clear_pc;
    uint32_t native_back_last_write_pc;
    uint32_t native_back_clear_from;
    uint32_t native_back_clear_destination;
    uint32_t native_back_clear_source;
    uint32_t native_back_clear_length;
    uint32_t native_fb_nonzero_bytes;
    uint32_t native_fb_peak_nonzero_bytes;
    uint32_t native_fb_rises;
    uint32_t native_fb_clears;
    uint32_t native_fb_last_rise_pc;
    uint32_t native_fb_last_clear_pc;
    uint32_t native_fb_last_write_pc;
    uint32_t native_fb_clear_from;
    uint32_t native_fb_clear_destination;
    uint32_t native_fb_clear_source;
    uint32_t native_fb_clear_length;
    uint64_t desktop_fb_trace_writes;
    uint32_t desktop_fb_trace_count;
    uint32_t desktop_fb_trace_pc[DMCU_DESKTOP_FB_TRACE_SLOTS];
    uint32_t desktop_fb_trace_address[DMCU_DESKTOP_FB_TRACE_SLOTS];
    uint32_t desktop_fb_trace_old[DMCU_DESKTOP_FB_TRACE_SLOTS];
    uint32_t desktop_fb_trace_new[DMCU_DESKTOP_FB_TRACE_SLOTS];
    uint32_t desktop_fb_trace_bits[DMCU_DESKTOP_FB_TRACE_SLOTS];
    uint32_t desktop_fb_trace_hits[DMCU_DESKTOP_FB_TRACE_SLOTS];
    uint16_t desktop_fb_trace_sp[DMCU_DESKTOP_FB_TRACE_SLOTS];
    uint16_t desktop_fb_trace_fp[DMCU_DESKTOP_FB_TRACE_SLOTS];
    uint32_t desktop_fb_trace_chain[DMCU_DESKTOP_FB_TRACE_SLOTS]
                                  [DMCU_START_GLYPH_TRACE_FRAMES];
    uint32_t desktop_blit_trace_count;
    uint32_t desktop_blit_trace_caller[DMCU_DESKTOP_BLIT_TRACE_SLOTS];
    uint16_t desktop_blit_trace_sp[DMCU_DESKTOP_BLIT_TRACE_SLOTS];
    uint16_t desktop_blit_trace_fp[DMCU_DESKTOP_BLIT_TRACE_SLOTS];
    uint16_t desktop_blit_trace_args[DMCU_DESKTOP_BLIT_TRACE_SLOTS][6];
    uint32_t desktop_blit_trace_chain[DMCU_DESKTOP_BLIT_TRACE_SLOTS]
                                    [DMCU_START_GLYPH_TRACE_FRAMES];
    uint32_t root_resource_trace_count;
    uint32_t root_resource_trace_active;
    uint32_t root_resource_trace_caller[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    uint16_t root_resource_trace_args[DMCU_ROOT_RESOURCE_TRACE_SLOTS][4];
    uint16_t root_resource_trace_fp[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    uint16_t root_resource_trace_source_hi[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    uint16_t root_resource_trace_source_lo[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    uint16_t root_resource_trace_width[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    uint16_t root_resource_trace_height[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    uint16_t root_resource_trace_handle[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    uint16_t root_resource_trace_object_hi[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    uint16_t root_resource_trace_object_lo[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    uint16_t root_resource_trace_stage[DMCU_ROOT_RESOURCE_TRACE_SLOTS];
    bool root_top_bitmap_valid;
    uint32_t root_top_bitmap_base;
    uint16_t root_top_bitmap_length;
    uint16_t root_top_source_covered;
    uint32_t root_top_source_calls;
    uint32_t root_top_source_from[DMCU_ROOT_TOP_COPY_TRACE_SLOTS];
    uint16_t root_top_source_args[DMCU_ROOT_TOP_COPY_TRACE_SLOTS][5];
    uint8_t root_top_bitmap[DMCU_ROOT_TOP_BITMAP_BYTES];
    uint8_t root_top_source[DMCU_ROOT_TOP_BITMAP_BYTES];
    uint8_t root_top_source_coverage[DMCU_ROOT_TOP_BITMAP_BYTES];
    uint16_t root_top_math_seen;
    uint16_t root_top_math[12][8];
    uint32_t root_top_far_copy_steps;
    uint32_t root_top_far_copy_pc[DMCU_ROOT_TOP_FAR_COPY_TRACE_SLOTS];
    uint32_t root_top_far_copy_from[DMCU_ROOT_TOP_FAR_COPY_TRACE_SLOTS];
    uint16_t root_top_far_copy_psw[DMCU_ROOT_TOP_FAR_COPY_TRACE_SLOTS];
    uint16_t root_top_far_copy_gpr[DMCU_ROOT_TOP_FAR_COPY_TRACE_SLOTS][11];
    uint16_t root_top_far_copy_args[DMCU_ROOT_TOP_FAR_COPY_TRACE_SLOTS][6];
    bool root_header_io_trace_pending;
    bool root_header_io_trace_captured;
    uint64_t root_header_io_trace_start;
    uint32_t root_header_io_trace_count;
    uint16_t root_header_io_trace_service_args[6];
    uint8_t root_header_io_trace_result[4];
    uint32_t root_header_io_trace_from[DMCU_ROOT_HEADER_IO_TRACE_SLOTS];
    uint32_t root_header_io_trace_target[DMCU_ROOT_HEADER_IO_TRACE_SLOTS];
    uint16_t root_header_io_trace_args[DMCU_ROOT_HEADER_IO_TRACE_SLOTS][6];
    uint16_t root_header_io_trace_base[DMCU_ROOT_HEADER_IO_TRACE_SLOTS];
    uint16_t root_header_io_trace_shift[DMCU_ROOT_HEADER_IO_TRACE_SLOTS];
    uint16_t root_header_io_trace_window[DMCU_ROOT_HEADER_IO_TRACE_SLOTS];
    uint16_t root_header_io_trace_logical_block[
        DMCU_ROOT_HEADER_IO_TRACE_SLOTS];
    uint16_t root_header_io_trace_map_slot[DMCU_ROOT_HEADER_IO_TRACE_SLOTS];
    uint32_t clock_format_write_trace_count;
    uint32_t clock_format_write_trace_pc[
        DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS];
    uint32_t clock_format_write_trace_address[
        DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS];
    uint16_t clock_format_write_trace_old[
        DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS];
    uint16_t clock_format_write_trace_new[
        DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS];
    uint8_t clock_format_write_trace_bits[
        DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS];
    uint16_t clock_format_write_trace_sp[
        DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS];
    uint16_t clock_format_write_trace_fp[
        DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS];
    uint16_t clock_format_write_trace_ds0[
        DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS];
    uint16_t clock_format_write_trace_ds1[
        DMCU_CLOCK_FORMAT_WRITE_TRACE_SLOTS];
    uint32_t clock_format_root_calls;
    uint32_t clock_format_service_calls;
    uint32_t clock_format_core_calls;
    uint16_t clock_format_root_sp;
    uint16_t clock_format_service_sp;
    uint16_t clock_format_core_sp;
    uint16_t clock_format_root_args[8];
    uint16_t clock_format_service_args[8];
    uint16_t clock_format_core_args[8];
    uint32_t clock_format_root_returns;
    uint32_t clock_format_service_returns;
    uint32_t clock_format_core_returns;
    uint16_t clock_format_root_result[2];
    uint16_t clock_format_service_result[2];
    uint16_t clock_format_core_result[2];
    uint16_t clock_format_root_return_sp;
    uint16_t clock_format_service_return_sp;
    uint16_t clock_format_core_return_sp;
    bool clock_format_root_active;
    uint8_t clock_format_buffer_after[DMCU_CLOCK_FORMAT_BUFFER_BYTES];
    uint8_t clock_format_service_buffer_after[DMCU_CLOCK_FORMAT_BUFFER_BYTES];
    uint8_t clock_format_core_buffer_after[DMCU_CLOCK_FORMAT_BUFFER_BYTES];
    uint8_t clock_format_string[DMCU_CLOCK_FORMAT_STRING_BYTES];
    uint16_t clock_format_varargs[DMCU_CLOCK_FORMAT_VARARG_WORDS];
    uint32_t clock_format_output_trace_count;
    uint32_t clock_format_output_trace_pc[
        DMCU_CLOCK_FORMAT_OUTPUT_TRACE_SLOTS];
    uint32_t clock_format_output_trace_address[
        DMCU_CLOCK_FORMAT_OUTPUT_TRACE_SLOTS];
    uint16_t clock_format_output_trace_old[
        DMCU_CLOCK_FORMAT_OUTPUT_TRACE_SLOTS];
    uint16_t clock_format_output_trace_new[
        DMCU_CLOCK_FORMAT_OUTPUT_TRACE_SLOTS];
    uint8_t clock_format_output_trace_bits[
        DMCU_CLOCK_FORMAT_OUTPUT_TRACE_SLOTS];
    uint8_t clock_format_output_trace_bus[
        DMCU_CLOCK_FORMAT_OUTPUT_TRACE_SLOTS];
    /* Four observer-only snapshots around one exact root-clock pass:
     * 31:590E before/31:5912 after the resource background blit, then
     * 31:596E before/31:5972 after the text renderer.  Hashes and pixel
     * counts cover only x=196..235,y=107..114 in the native bottom-up
     * 4-bpp buffers, so the trace cannot alter or stand in for drawing. */
    uint32_t clock_raster_cycle_count;
    uint32_t clock_raster_active_sequence;
    uint32_t clock_raster_sequence[DMCU_CLOCK_RASTER_TRACE_SLOTS];
    uint8_t clock_raster_valid[DMCU_CLOCK_RASTER_TRACE_SLOTS];
    uint32_t clock_raster_back_hash[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                                    [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint32_t clock_raster_front_hash[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                                     [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint16_t clock_raster_back_foreground[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                                          [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint16_t clock_raster_front_foreground[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                                           [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint16_t clock_raster_back_levels[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                                      [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint16_t clock_raster_front_levels[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                                       [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint32_t clock_raster_pointer[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                                  [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint16_t clock_raster_mode[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                               [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint16_t clock_raster_mask_a[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                                 [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint16_t clock_raster_mask_b[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                                 [DMCU_CLOCK_RASTER_TRACE_STAGES];
    uint8_t clock_raster_text[DMCU_CLOCK_RASTER_TRACE_SLOTS]
                              [DMCU_CLOCK_RASTER_TEXT_BYTES];
    /* First 64 exact resource-pair calls into 2E:0AF6: the 27:58E4
     * footer/background resource followed by the 31:590E clock background.
     * Each stage is an observer-only snapshot around the two source-proven
     * handle release workers; no field below is consumed by guest execution.
     * The historical clock_resource_release prefix is retained to keep this
     * diagnostic-only state change minimal. */
    uint32_t clock_resource_release_calls;
    uint32_t clock_resource_release_active;
    uint32_t clock_resource_release_caller[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_call_sp[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_call_post_sp[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_call_fp[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_resource_sp[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_resource_fp[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint8_t clock_resource_release_stage_valid[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint32_t clock_resource_release_stage_pc[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint32_t clock_resource_release_stage_target[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_word[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_ext[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_pre_sp[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_post_sp[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_pre_fp[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_post_fp[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_handle[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_argument[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint32_t clock_resource_release_stage_node[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint32_t clock_resource_release_stage_next[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_node_word[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_node_key[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_node_matches[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_bitmap_word[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint16_t clock_resource_release_stage_bitmap_mask[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint32_t clock_resource_release_stage_interrupts[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS]
        [DMCU_CLOCK_RESOURCE_RELEASE_STAGES];
    uint8_t clock_resource_release_stage_argument_valid[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint8_t clock_resource_release_stage_bitmap_valid[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint8_t clock_resource_release_stage_bitmap_set[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint8_t clock_resource_release_stage_in_irq[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_mask_calls[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_mask_returns[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint32_t clock_resource_release_mask_caller[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint32_t clock_resource_release_mask_return_target[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_mask_handle[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_mask_bitmap_before[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    uint16_t clock_resource_release_mask_bitmap_after[
        DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS];
    /* Observer-only lifetime of the caller-owned far return frame for the
     * exact 2E:0AF6 <- 4B:0AF6 resource compositor.  This is deliberately
     * independent of the older footer/clock handle trace: the same vendor
     * routine is also used while an NPE game exits. */
    uint64_t npe_resource_return_trace_count;
    uint64_t npe_resource_return_trace_sequence[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS];
    uint32_t npe_resource_return_active_slot;
    uint64_t npe_resource_return_active_sequence;
    uint32_t npe_resource_return_caller[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS];
    uint16_t npe_resource_return_call_sp[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS];
    uint16_t npe_resource_return_call_post_sp[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS];
    uint16_t npe_resource_return_call_fp[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS];
    uint16_t npe_resource_return_frame_base[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS];
    uint16_t npe_resource_return_initial_frame[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS][2];
    uint16_t npe_resource_return_final_frame[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS][2];
    uint16_t npe_resource_return_stage_valid[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS];
    uint32_t npe_resource_return_stage_pc[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS]
        [DMCU_NPE_RESOURCE_RETURN_TRACE_STAGES];
    uint32_t npe_resource_return_stage_target[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS]
        [DMCU_NPE_RESOURCE_RETURN_TRACE_STAGES];
    uint16_t npe_resource_return_stage_word[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS]
        [DMCU_NPE_RESOURCE_RETURN_TRACE_STAGES];
    uint16_t npe_resource_return_stage_sp[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS]
        [DMCU_NPE_RESOURCE_RETURN_TRACE_STAGES];
    uint16_t npe_resource_return_stage_post_sp[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS]
        [DMCU_NPE_RESOURCE_RETURN_TRACE_STAGES];
    uint16_t npe_resource_return_stage_fp[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS]
        [DMCU_NPE_RESOURCE_RETURN_TRACE_STAGES];
    uint16_t npe_resource_return_stage_frame[
        DMCU_NPE_RESOURCE_RETURN_TRACE_SLOTS]
        [DMCU_NPE_RESOURCE_RETURN_TRACE_STAGES][2];
    uint64_t npe_resource_return_write_count;
    uint64_t npe_resource_return_write_sequence[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint64_t npe_resource_return_write_call_sequence[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint32_t npe_resource_return_write_pc[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint16_t npe_resource_return_write_address[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint16_t npe_resource_return_write_old[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint16_t npe_resource_return_write_new[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint16_t npe_resource_return_write_sp[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint16_t npe_resource_return_write_fp[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint8_t npe_resource_return_write_bits[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint8_t npe_resource_return_write_bus[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint8_t npe_resource_return_write_in_irq[
        DMCU_NPE_RESOURCE_RETURN_WRITE_SLOTS];
    uint32_t clock_stream_write_calls;
    uint32_t clock_stream_dispatch_calls;
    uint32_t clock_stream_write_returns;
    uint32_t clock_stream_dispatch_returns;
    uint16_t clock_stream_write_args[6];
    uint16_t clock_stream_dispatch_args[6];
    uint16_t clock_stream_write_result[2];
    uint16_t clock_stream_dispatch_result[2];
    uint8_t clock_stream_object_a[DMCU_CLOCK_STREAM_OBJECT_BYTES];
    uint8_t clock_stream_object_b[DMCU_CLOCK_STREAM_OBJECT_BYTES];
    uint8_t clock_stream_buffer_after[DMCU_CLOCK_FORMAT_BUFFER_BYTES];
    uint32_t clock_stream_move_trace_count;
    uint32_t clock_stream_move_trace_caller[
        DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS];
    uint16_t clock_stream_move_trace_sp[DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS];
    uint16_t clock_stream_move_trace_fp[DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS];
    uint16_t clock_stream_move_trace_args[
        DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS]
        [DMCU_CLOCK_STREAM_MOVE_ARGUMENT_WORDS];
    uint8_t clock_stream_move_trace_samples[
        DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS][3]
        [DMCU_CLOCK_STREAM_MOVE_SAMPLE_BYTES];
    uint32_t clock_stream_copy_trace_count;
    uint32_t clock_stream_copy_trace_caller[
        DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS];
    uint16_t clock_stream_copy_trace_sp[DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS];
    uint16_t clock_stream_copy_trace_fp[DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS];
    uint16_t clock_stream_copy_trace_args[
        DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS]
        [DMCU_CLOCK_STREAM_MOVE_ARGUMENT_WORDS];
    uint8_t clock_stream_copy_trace_samples[
        DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS][3]
        [DMCU_CLOCK_STREAM_MOVE_SAMPLE_BYTES];
    uint32_t clock_scan_calls;
    uint32_t clock_scan_returns;
    uint32_t clock_scan_length_branches;
    uint32_t clock_scan_literal_branches;
    uint16_t clock_scan_sp;
    uint16_t clock_scan_fp;
    uint16_t clock_scan_args[DMCU_CLOCK_SCAN_ARGUMENT_WORDS];
    uint16_t clock_scan_result[2];
    uint16_t clock_scan_return_sp;
    uint16_t clock_scan_return_fp;
    uint16_t clock_scan_locals[DMCU_CLOCK_SCAN_LOCAL_WORDS];
    uint16_t clock_scan_length_result[2];
    uint16_t clock_scan_length_fp;
    uint32_t clock_scan_length_target;
    bool clock_root_core_trace_active;
    uint32_t clock_root_core_call_trace_count;
    uint32_t clock_root_core_call_trace_from[
        DMCU_CLOCK_CORE_CALL_TRACE_SLOTS];
    uint32_t clock_root_core_call_trace_target[
        DMCU_CLOCK_CORE_CALL_TRACE_SLOTS];
    uint16_t clock_root_core_call_trace_sp[
        DMCU_CLOCK_CORE_CALL_TRACE_SLOTS];
    uint32_t native_font_blit_calls;
    uint32_t native_font_blit_pointer;
    uint32_t native_font_blit_row;
    uint32_t native_font_blit_count;
    uint32_t native_font_blit_position_x;
    uint32_t native_font_blit_position_y;
    uint32_t native_font_blit_x;
    uint32_t native_font_blit_column;
    uint32_t native_font_blit_glyph;
    uint32_t native_font_blit_mask_a;
    uint32_t native_font_blit_mask_b;
    uint32_t native_font_blit_mode;
    uint32_t native_font_blit_nonzero_glyph_calls;
    uint32_t native_font_blit_glyph_or;
    uint32_t native_font_blit_pointer_calls[4];
    uint32_t native_font_store_calls;
    uint32_t native_font_store_pc;
    uint32_t native_font_store_logical;
    uint32_t native_font_store_physical;
    uint32_t native_font_store_actual_physical;
    uint32_t native_font_store_value;
    uint32_t native_font_store_bits;
    uint32_t native_font_store_ds0;
    uint32_t native_font_store_ds1;
    uint32_t font_blit_trace_count;
    uint32_t font_blit_trace_caller[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_pointer[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_position_x[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_position_y[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_character[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_rows[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_count_words[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_offset[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_column[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_glyph[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t font_blit_trace_mode[DMCU_FONT_BLIT_TRACE_SLOTS];
    uint32_t glyph_draw_trace_count;
    uint32_t glyph_draw_trace_caller[DMCU_GLYPH_DRAW_TRACE_SLOTS];
    uint32_t glyph_draw_trace_x[DMCU_GLYPH_DRAW_TRACE_SLOTS];
    uint32_t glyph_draw_trace_y[DMCU_GLYPH_DRAW_TRACE_SLOTS];
    uint32_t glyph_draw_trace_character[DMCU_GLYPH_DRAW_TRACE_SLOTS];
    uint32_t glyph_draw_active_character;
    uint32_t start_glyph_trace_count;
    uint32_t start_glyph_trace_caller[DMCU_START_GLYPH_TRACE_SLOTS];
    uint32_t start_glyph_trace_x[DMCU_START_GLYPH_TRACE_SLOTS];
    uint32_t start_glyph_trace_y[DMCU_START_GLYPH_TRACE_SLOTS];
    uint32_t start_glyph_trace_character[DMCU_START_GLYPH_TRACE_SLOTS];
    uint16_t start_glyph_trace_sp[DMCU_START_GLYPH_TRACE_SLOTS];
    uint16_t start_glyph_trace_fp[DMCU_START_GLYPH_TRACE_SLOTS];
    uint32_t start_glyph_trace_chain[DMCU_START_GLYPH_TRACE_SLOTS]
                                    [DMCU_START_GLYPH_TRACE_FRAMES];
    uint32_t npe_glyph_trace_count;
    uint32_t npe_glyph_trace_caller[DMCU_NPE_GLYPH_TRACE_SLOTS];
    uint32_t npe_glyph_trace_target[DMCU_NPE_GLYPH_TRACE_SLOTS];
    uint16_t npe_glyph_trace_x[DMCU_NPE_GLYPH_TRACE_SLOTS];
    uint16_t npe_glyph_trace_y[DMCU_NPE_GLYPH_TRACE_SLOTS];
    uint16_t npe_glyph_trace_character[DMCU_NPE_GLYPH_TRACE_SLOTS];
    uint16_t npe_glyph_trace_sp[DMCU_NPE_GLYPH_TRACE_SLOTS];
    uint16_t npe_glyph_trace_fp[DMCU_NPE_GLYPH_TRACE_SLOTS];
    uint32_t npe_glyph_trace_chain[DMCU_NPE_GLYPH_TRACE_SLOTS]
                                  [DMCU_NPE_GLYPH_TRACE_FRAMES];
    uint32_t npe_text_box_trace_count;
    uint32_t npe_text_box_trace_caller[DMCU_NPE_TEXT_BOX_TRACE_SLOTS];
    uint16_t npe_text_box_trace_sp[DMCU_NPE_TEXT_BOX_TRACE_SLOTS];
    uint16_t npe_text_box_trace_fp[DMCU_NPE_TEXT_BOX_TRACE_SLOTS];
    uint16_t npe_text_box_trace_args[DMCU_NPE_TEXT_BOX_TRACE_SLOTS][4];
    bool npe_text_box_trace_pointer_valid[DMCU_NPE_TEXT_BOX_TRACE_SLOTS];
    uint8_t npe_text_box_trace_sample[DMCU_NPE_TEXT_BOX_TRACE_SLOTS]
                                      [DMCU_NPE_TEXT_BOX_TRACE_SAMPLE_BYTES];
    uint32_t npe_control_trace_count;
    bool npe_control_trace_frozen;
    uint8_t npe_control_trace_phase;
    /* First non-sequential foreground transfer into the low 51:0000-1FFF
     * window.  The NPE map presently falls into bitmap/resource bytes there;
     * keep the untouched pre-transfer machine state so the exact originating
     * instruction survives subsequent timer-return traffic.  These fields
     * are diagnostic-only and are never consumed by guest execution. */
    bool npe_low51_entry_valid;
    uint32_t npe_low51_entry_from;
    uint32_t npe_low51_entry_target;
    uint32_t npe_low51_entry_sequential;
    uint16_t npe_low51_entry_word;
    uint16_t npe_low51_entry_ext;
    uint16_t npe_low51_entry_sp;
    uint16_t npe_low51_entry_fp;
    uint16_t npe_low51_entry_ds0;
    uint16_t npe_low51_entry_ds1;
    uint16_t npe_low51_entry_gpr[DMCU_NPE_LOW51_ENTRY_GPR_WORDS];
    uint16_t npe_low51_entry_stack[DMCU_NPE_LOW51_ENTRY_STACK_WORDS];
    bool npe_low51_exec_valid;
    uint32_t npe_low51_exec_pc;
    uint16_t npe_low51_exec_word;
    uint16_t npe_low51_exec_sp;
    uint16_t npe_low51_exec_fp;
    uint16_t npe_low51_exec_history_count;
    uint32_t npe_low51_exec_history_pc[
        DMCU_NPE_LOW51_EXEC_HISTORY_WORDS];
    uint16_t npe_low51_exec_history_word[
        DMCU_NPE_LOW51_EXEC_HISTORY_WORDS];
    uint16_t npe_low51_exec_history_sp[
        DMCU_NPE_LOW51_EXEC_HISTORY_WORDS];
    /* First execution anywhere in the UI initializer after that initializer
     * has already returned once.  A valid UI-init call reaches 29:D0BA and
     * owns a far-return frame; a later entry in 29:D0BA..D34D without another
     * observed call is therefore the earliest proven control-flow anomaly,
     * before the final 29:D34E RETS consumes resource bytes as an address. */
    bool npe_game_ui_reentry_valid;
    uint32_t npe_game_ui_reentry_pc;
    uint16_t npe_game_ui_reentry_word;
    uint16_t npe_game_ui_reentry_sp;
    uint16_t npe_game_ui_reentry_fp;
    uint16_t npe_game_ui_reentry_history_count;
    uint32_t npe_game_ui_reentry_history_pc[
        DMCU_NPE_UI_REENTRY_HISTORY_WORDS];
    uint16_t npe_game_ui_reentry_history_word[
        DMCU_NPE_UI_REENTRY_HISTORY_WORDS];
    uint16_t npe_game_ui_reentry_history_sp[
        DMCU_NPE_UI_REENTRY_HISTORY_WORDS];
    uint16_t npe_game_ui_reentry_stack[DMCU_NPE_UI_REENTRY_STACK_WORDS];
    bool npe_game_action_trace_armed;
    bool npe_game_linked_loader_valid;
    uint32_t npe_game_linked_loader_pc;
    uint16_t npe_game_linked_loader_word;
    uint16_t npe_game_linked_loader_sp;
    uint16_t npe_game_linked_loader_fp;
    uint16_t npe_game_linked_loader_history_count;
    uint32_t npe_game_linked_loader_history_pc[
        DMCU_NPE_UI_REENTRY_HISTORY_WORDS];
    uint16_t npe_game_linked_loader_history_word[
        DMCU_NPE_UI_REENTRY_HISTORY_WORDS];
    uint16_t npe_game_linked_loader_history_sp[
        DMCU_NPE_UI_REENTRY_HISTORY_WORDS];
    uint16_t npe_game_linked_loader_stack[DMCU_NPE_UI_REENTRY_STACK_WORDS];
    /* Ring of the final guest stores to linked 29:CE22..D0B9.  The first
     * recovered installer and any later broad application publish share this
     * physical range; retaining the writer and four return frames identifies
     * the last owner without altering either store or instruction fetch. */
    uint32_t npe_operation_one_action_write_count;
    uint32_t npe_operation_one_action_write_pc[
        DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS];
    uint32_t npe_operation_one_action_write_address[
        DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS];
    uint16_t npe_operation_one_action_write_old[
        DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS];
    uint16_t npe_operation_one_action_write_new[
        DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS];
    uint16_t npe_operation_one_action_write_bits[
        DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS];
    uint16_t npe_operation_one_action_write_sp[
        DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS];
    uint16_t npe_operation_one_action_write_fp[
        DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS];
    uint32_t npe_operation_one_action_write_frames[
        DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS]
        [DMCU_NPE_OPERATION_ONE_ACTION_WRITE_FRAMES];
    bool npe_modal_control_trace_pending;
    bool npe_modal_control_trace_active;
    uint32_t npe_modal_control_trace_caller;
    uint16_t npe_modal_control_trace_result;
    bool npe_modal_control_trace_outputs_valid;
    uint16_t npe_modal_control_trace_type;
    uint16_t npe_modal_control_trace_code;
    bool npe_modal_control_trace_decoder_valid;
    uint32_t npe_modal_control_trace_decoder_caller;
    uint16_t npe_modal_control_trace_decoder_result;
    bool npe_loader_control_trace_active;
    bool npe_loader_control_trace_completed;
    uint32_t npe_loader_control_trace_entries;
    uint32_t npe_loader_control_trace_returns;
    uint32_t npe_loader_control_trace_return_target;
    uint16_t npe_loader_control_trace_entry_r0;
    uint16_t npe_loader_control_trace_entry_r1;
    uint16_t npe_loader_control_trace_entry_error;
    uint16_t npe_loader_control_trace_entry_file_error;
    uint16_t npe_loader_control_trace_return_r0;
    uint16_t npe_loader_control_trace_return_r1;
    uint16_t npe_loader_control_trace_return_error;
    uint16_t npe_loader_control_trace_return_file_error;
    uint16_t npe_loader_control_trace_return_application_state;
    /* Exact 1F:D5B2 -> 1E:F734 -> 1F:D5B6 event boundary inside the
     * status-2 NPE controller.  These fields are read-only observations of
     * the caller's two output locals and the subsequent source-proven branch
     * milestones; no field below is consumed by guest execution. */
    bool npe_loader_event_watch_active;
    bool npe_loader_event_follow_active;
    uint32_t npe_loader_event_calls;
    uint32_t npe_loader_event_returns;
    uint32_t npe_loader_event_nonzero_returns;
    uint32_t npe_loader_event_key86_returns;
    uint16_t npe_loader_event_call_sp;
    uint16_t npe_loader_event_call_fp;
    uint16_t npe_loader_event_return_sp;
    uint16_t npe_loader_event_return_fp;
    uint16_t npe_loader_event_last_result;
    uint16_t npe_loader_event_result;
    uint16_t npe_loader_event_type;
    uint16_t npe_loader_event_code;
    uint16_t npe_loader_event_global_mode;
    uint8_t npe_loader_event_global_flag;
    uint8_t npe_loader_event_global_iteration;
    uint16_t npe_loader_event_global_selection;
    uint16_t npe_loader_event_error;
    uint16_t npe_loader_event_file_error;
    uint32_t npe_loader_event_result_zero_paths;
    uint32_t npe_loader_event_type4_paths;
    uint32_t npe_loader_event_other_type_paths;
    uint32_t npe_loader_event_mode1_paths;
    uint32_t npe_loader_event_other_mode_paths;
    uint32_t npe_loader_event_flag_zero_paths;
    uint32_t npe_loader_event_flag_nonzero_paths;
    uint32_t npe_loader_event_prepare_calls;
    uint32_t npe_loader_event_initialize_calls;
    uint32_t npe_loader_event_initialize_returns;
    uint32_t npe_loader_event_progress_paths;
    uint32_t npe_loader_event_service_calls;
    uint32_t npe_loader_event_controller_returns;
    /* Read-only checkpoints across the exact operation-7 service and its
     * first mode-one update.  The framebuffer samples are diagnostics only;
     * no value here is ever supplied back to guest execution. */
    bool npe_game_trace_armed;
    uint32_t npe_game_service_dispatch_calls;
    uint32_t npe_game_ui_handler_calls;
    uint32_t npe_game_ui_handler_returns;
    uint32_t npe_game_code86_paths;
    uint32_t npe_game_flag_7a7e_one_paths;
    uint32_t npe_game_flag_7a7c_one_paths;
    uint8_t npe_game_flag_7a7a;
    uint8_t npe_game_flag_7a7c;
    uint8_t npe_game_flag_7a7e;
    uint32_t npe_game_memory_mode_calls;
    uint32_t npe_game_memory_mode_returns;
    uint32_t npe_game_ui_init_calls;
    uint32_t npe_game_ui_init_returns;
    /* Read-only ABI evidence for the exact 1D:8EF0 -> 29:D0BA UI
     * initializer call and its 29:D34E RETS.  This distinguishes a strict
     * edge-matcher miss from a damaged far-return frame without changing
     * the guest stack or control flow. */
    uint16_t npe_game_ui_init_call_pre_sp;
    uint16_t npe_game_ui_init_call_post_sp;
    uint16_t npe_game_ui_init_call_pre_fp;
    uint16_t npe_game_ui_init_call_post_fp;
    uint16_t npe_game_ui_init_call_frame[4];
    uint32_t npe_game_ui_init_rets_seen;
    uint32_t npe_game_ui_init_rets_target;
    uint16_t npe_game_ui_init_rets_word;
    uint16_t npe_game_ui_init_rets_pre_sp;
    uint16_t npe_game_ui_init_rets_post_sp;
    uint16_t npe_game_ui_init_rets_pre_fp;
    uint16_t npe_game_ui_init_rets_post_fp;
    uint16_t npe_game_ui_init_rets_frame[4];
    uint32_t npe_game_ui_init_continuation_entries;
    uint32_t npe_game_ui_init_continuation_from;
    uint16_t npe_game_ui_init_continuation_word;
    uint16_t npe_game_ui_init_continuation_pre_sp;
    uint16_t npe_game_ui_init_continuation_post_sp;
    uint16_t npe_game_ui_init_continuation_pre_fp;
    uint16_t npe_game_ui_init_continuation_post_fp;
    /* Monotonic, read-only ordering evidence for operation-7 publication and
     * the first UI initializer.  Zero means the selected edge was not seen;
     * no field is consumed by guest execution. */
    uint32_t npe_game_ui_lifecycle_sequence;
    uint32_t npe_game_ui_wrapper_8a5c_calls;
    uint32_t npe_game_ui_wrapper_8a5c_sequence;
    uint32_t npe_game_ui_wrapper_9140_calls;
    uint32_t npe_game_ui_wrapper_9140_sequence;
    uint32_t npe_game_ui_publisher_calls;
    uint32_t npe_game_ui_publisher_call_sequence;
    uint32_t npe_game_ui_publisher_returns;
    uint32_t npe_game_ui_publisher_return_sequence;
    uint32_t npe_game_ui_wrapper_tail_calls;
    uint32_t npe_game_ui_wrapper_tail_sequence;
    uint32_t npe_game_ui_init_call_sequence;
    uint32_t npe_game_ui_e15a_calls;
    uint32_t npe_game_ui_e15a_call_sequence;
    uint32_t npe_game_ui_e15a_returns;
    uint32_t npe_game_ui_e15a_return_sequence;
    uint32_t npe_game_ui_e15a_continuation_entries;
    uint32_t npe_game_ui_e15a_continuation_sequence;
    uint32_t npe_game_ui_e15a_continuation_from;
    uint32_t npe_game_ui_6ab8_calls;
    uint32_t npe_game_ui_6ab8_call_sequence;
    uint32_t npe_game_ui_6ab8_returns;
    uint32_t npe_game_ui_6ab8_return_sequence;
    uint32_t npe_game_ui_6ab8_continuation_entries;
    uint32_t npe_game_ui_6ab8_continuation_sequence;
    uint32_t npe_game_ui_6ab8_continuation_from;
    uint32_t npe_game_ui_5c22_calls;
    uint32_t npe_game_ui_5c22_call_sequence;
    uint32_t npe_game_ui_5c22_returns;
    uint32_t npe_game_ui_5c22_return_sequence;
    uint32_t npe_game_ui_5c22_continuation_entries;
    uint32_t npe_game_ui_5c22_continuation_sequence;
    uint32_t npe_game_ui_5c22_continuation_from;
    /* Per-child, observer-only closure evidence for linked 29:5C22.  The
     * eight entries correspond to its eight statically proven SCALL sites;
     * targets/return origins preserve the first edge seen for triage. */
    uint32_t npe_game_frame_clear_child_calls[8];
    uint32_t npe_game_frame_clear_child_targets[8];
    uint32_t npe_game_frame_clear_child_continuations[8];
    uint32_t npe_game_frame_clear_child_continuation_from[8];
    uint32_t npe_game_transition_service_calls;
    uint32_t npe_game_transition_service_entries;
    uint32_t npe_game_transition_service_returns;
    uint32_t npe_game_transition_service_continuations;
    uint32_t npe_game_transition_service_continuation_from;
    uint32_t npe_game_transition_service_child_calls;
    uint32_t npe_game_transition_service_child_returns;
    uint32_t npe_game_transition_service_leaf_calls;
    uint32_t npe_game_transition_service_leaf_returns;
    /* Observation-only snapshots of the A1:387A resource gate used by the
     * exact 32:5F86 transition service.  Entry records retain the gate and
     * caller arguments before the service can branch; read/write rings retain
     * producer/consumer provenance.  No field is consumed by guest code. */
    uint32_t npe_transition_gate_entries;
    uint32_t npe_transition_gate_entry_from[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_entry_sp[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_entry_fp[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_entry_value[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint8_t npe_transition_gate_entry_operation[
        DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_entry_args[
        DMCU_NPE_TRANSITION_GATE_SLOTS][6];
    uint16_t npe_transition_gate_entry_context[
        DMCU_NPE_TRANSITION_GATE_SLOTS][8];
    uint32_t npe_transition_gate_reads;
    uint32_t npe_transition_gate_read_pc[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_read_logical[
        DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint32_t npe_transition_gate_read_physical[
        DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_read_value[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_read_ds0[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_read_ds1[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint8_t npe_transition_gate_read_bits[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint32_t npe_transition_gate_writes;
    uint32_t npe_transition_gate_write_pc[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_write_logical[
        DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint32_t npe_transition_gate_write_physical[
        DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_write_value[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_write_old[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_write_new[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_write_ds0[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint16_t npe_transition_gate_write_ds1[DMCU_NPE_TRANSITION_GATE_SLOTS];
    uint8_t npe_transition_gate_write_bits[DMCU_NPE_TRANSITION_GATE_SLOTS];
    /* Exact 42:206E special handling for logical resources 10:D012..D01C.
     * The reader tail dispatches through a near-target table into its own
     * runtime 25:2180..23A8 continuations; these fields retain that boot-time
     * lifecycle without altering it. */
    uint32_t resource_special_calls;
    bool resource_special_active;
    uint32_t resource_special_active_slot;
    uint32_t resource_special_from[DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint16_t resource_special_sp[DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint16_t resource_special_fp[DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint16_t resource_special_source[DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint16_t resource_special_length[DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint16_t resource_special_output_segment[
        DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint16_t resource_special_output_offset[
        DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint8_t resource_special_output_before[
        DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint8_t resource_special_output_transferred[
        DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint32_t resource_special_dispatch_target[
        DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint32_t resource_special_returns;
    uint32_t resource_special_return_target[
        DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint16_t resource_special_result[DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    uint8_t resource_special_output_after[
        DMCU_RESOURCE_SPECIAL_TRACE_SLOTS];
    /* Read-only evidence for resident 14:B768 and its exact persistence
     * writer chain.  The resident table at 14:B716 selects one of seven
     * near handlers for events 80..86; the selected handler may call the
     * original 32:EBAE -> 33:0D7E -> 28:0F92 storage path. */
    uint32_t resource_persist_dispatch_calls;
    uint32_t resource_persist_dispatch_returns;
    bool resource_persist_dispatch_active;
    uint32_t resource_persist_dispatch_active_slot;
    uint32_t resource_persist_dispatch_from[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS];
    uint16_t resource_persist_dispatch_sp[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS];
    uint16_t resource_persist_dispatch_fp[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS];
    uint16_t resource_persist_dispatch_args[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS]
        [DMCU_RESOURCE_PERSIST_ARGUMENT_WORDS];
    uint16_t resource_persist_dispatch_table[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS]
        [DMCU_RESOURCE_PERSIST_TABLE_WORDS];
    uint32_t resource_persist_dispatch_handler[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS];
    uint16_t resource_persist_dispatch_key[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS];
    uint16_t resource_persist_dispatch_value[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS];
    uint16_t resource_persist_dispatch_previous[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS];
    uint32_t resource_persist_dispatch_return_target[
        DMCU_RESOURCE_PERSIST_TRACE_SLOTS];
    uint32_t resource_persist_wrapper_calls;
    uint32_t resource_persist_wrapper_returns;
    uint32_t resource_persist_bridge_calls;
    uint32_t resource_persist_bridge_returns;
    uint32_t resource_persist_page_calls;
    uint32_t resource_persist_page_returns;
    uint32_t resource_persist_last_wrapper_from;
    uint16_t resource_persist_last_wrapper_sp;
    uint16_t resource_persist_last_wrapper_fp;
    uint16_t resource_persist_last_wrapper_args[5];
    uint8_t resource_persist_last_buffer_value;
    uint32_t resource_persist_last_bridge_from;
    uint16_t resource_persist_last_bridge_args[5];
    uint32_t resource_persist_last_page_from;
    uint16_t resource_persist_last_page_args[5];
    uint16_t resource_persist_last_page_result;
    uint16_t resource_persist_last_bridge_result;
    uint16_t resource_persist_last_wrapper_result;
    uint32_t npe_game_buffer_sync_calls;
    uint32_t npe_game_buffer_sync_returns;
    uint32_t npe_game_state_publish_calls;
    uint32_t npe_game_state_publish_returns;
    uint32_t npe_game_service_returns;
    uint16_t npe_game_service_mode;
    uint32_t npe_game_service_pointer;
    uint32_t npe_game_grid_calls;
    uint32_t npe_game_grid_returns;
    uint32_t npe_game_initialize_calls;
    uint32_t npe_game_initialize_returns;
    uint32_t npe_game_range_calls;
    uint32_t npe_game_randomize_calls;
    uint32_t npe_game_compare_calls;
    uint32_t npe_game_draw_calls;
    uint32_t npe_game_draw_returns;
    uint32_t npe_game_draw_item_calls;
    uint32_t npe_game_state_dispatch_calls;
    /* Bounded, read-only control-flow evidence for the most recent exact
     * 29:BBF2 map draw.  The seven child slots match its seven static SCALL
     * sites in source 46:BBF2; none of these fields feed guest execution. */
    bool npe_game_draw_trace_active;
    uint32_t npe_game_draw_trace_call;
    uint32_t npe_game_draw_trace_edge_count;
    uint16_t npe_game_draw_trace_active_child;
    uint32_t npe_game_draw_child_calls[DMCU_NPE_GAME_DRAW_CHILD_SITES];
    uint32_t npe_game_draw_child_returns[DMCU_NPE_GAME_DRAW_CHILD_SITES];
    uint32_t npe_game_draw_child_target[DMCU_NPE_GAME_DRAW_CHILD_SITES];
    uint32_t npe_game_draw_child_return_from[
        DMCU_NPE_GAME_DRAW_CHILD_SITES];
    uint16_t npe_game_draw_child_call_sp[DMCU_NPE_GAME_DRAW_CHILD_SITES];
    uint16_t npe_game_draw_child_call_fp[DMCU_NPE_GAME_DRAW_CHILD_SITES];
    uint16_t npe_game_draw_child_return_sp[
        DMCU_NPE_GAME_DRAW_CHILD_SITES];
    uint16_t npe_game_draw_child_return_fp[
        DMCU_NPE_GAME_DRAW_CHILD_SITES];
    uint32_t npe_game_draw_trace_from[DMCU_NPE_GAME_DRAW_TRACE_SLOTS];
    uint32_t npe_game_draw_trace_target[DMCU_NPE_GAME_DRAW_TRACE_SLOTS];
    uint16_t npe_game_draw_trace_word[DMCU_NPE_GAME_DRAW_TRACE_SLOTS];
    uint16_t npe_game_draw_trace_sp[DMCU_NPE_GAME_DRAW_TRACE_SLOTS];
    uint16_t npe_game_draw_trace_fp[DMCU_NPE_GAME_DRAW_TRACE_SLOTS];
    uint16_t npe_game_draw_trace_r0[DMCU_NPE_GAME_DRAW_TRACE_SLOTS];
    uint16_t npe_game_draw_trace_r1[DMCU_NPE_GAME_DRAW_TRACE_SLOTS];
    uint16_t npe_game_draw_trace_child[DMCU_NPE_GAME_DRAW_TRACE_SLOTS];
    /* Read-only provenance for the application-state byte at logical
     * A4:7A3E (physical word 52:7A3E).  The 00:1002 resident callback reads
     * its high physical byte through the external byte-lane convention.
     * No field below is consumed by guest execution. */
    uint32_t npe_game_state_writes;
    uint32_t npe_game_state_changing_writes;
    uint32_t npe_game_state_nonzero_writes;
    bool npe_game_state_first_write_valid;
    bool npe_game_state_first_nonzero_valid;
    uint32_t npe_game_state_first_write_pc;
    uint32_t npe_game_state_first_write_address;
    uint16_t npe_game_state_first_write_logical;
    uint16_t npe_game_state_first_write_old;
    uint16_t npe_game_state_first_write_new;
    uint16_t npe_game_state_first_write_sp;
    uint16_t npe_game_state_first_write_fp;
    uint16_t npe_game_state_first_write_ds0;
    uint16_t npe_game_state_first_write_ds1;
    uint8_t npe_game_state_first_write_bits;
    uint32_t npe_game_state_first_nonzero_pc;
    uint32_t npe_game_state_first_nonzero_address;
    uint16_t npe_game_state_first_nonzero_logical;
    uint16_t npe_game_state_first_nonzero_old;
    uint16_t npe_game_state_first_nonzero_new;
    uint16_t npe_game_state_first_nonzero_sp;
    uint16_t npe_game_state_first_nonzero_fp;
    uint16_t npe_game_state_first_nonzero_ds0;
    uint16_t npe_game_state_first_nonzero_ds1;
    uint8_t npe_game_state_first_nonzero_bits;
    uint32_t npe_game_state_last_write_pc;
    uint32_t npe_game_state_last_write_address;
    uint16_t npe_game_state_last_write_logical;
    uint16_t npe_game_state_last_write_old;
    uint16_t npe_game_state_last_write_new;
    uint16_t npe_game_state_last_write_sp;
    uint16_t npe_game_state_last_write_fp;
    uint16_t npe_game_state_last_write_ds0;
    uint16_t npe_game_state_last_write_ds1;
    uint8_t npe_game_state_last_write_bits;
    uint32_t npe_game_callback_entries;
    uint32_t npe_game_callback_state_zero_paths;
    uint32_t npe_game_callback_state_one_paths;
    uint32_t npe_game_callback_state_other_paths;
    uint8_t npe_game_callback_state;
    /* Boot-lifetime, read-only provenance for the three words which select
     * the operation and gate the resident 1A:1312 controller.  Unlike the
     * per-launch game trace this ring is deliberately not cleared when the
     * 0x86 event is accepted, so the compiler initializer and any earlier
     * producer remain visible.  No field is consumed by guest execution. */
    uint32_t npe_game_control_write_count;
    uint32_t npe_game_control_write_pc[DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint32_t npe_game_control_write_address[
        DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint16_t npe_game_control_write_logical[
        DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint16_t npe_game_control_write_old[DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint16_t npe_game_control_write_new[DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint16_t npe_game_control_write_sp[DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint16_t npe_game_control_write_fp[DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint16_t npe_game_control_write_ds0[DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint16_t npe_game_control_write_ds1[DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint8_t npe_game_control_write_bits[DMCU_NPE_GAME_CONTROL_WRITE_SLOTS];
    uint32_t npe_game_operation_one_dispatches;
    uint32_t npe_game_operation_one_entries;
    uint32_t npe_game_operation_one_fast_exits;
    uint32_t npe_game_operation_one_fast_returns;
    uint32_t npe_game_operation_one_normal_paths;
    uint32_t npe_game_operation_one_frame_init_calls;
    uint32_t npe_game_operation_one_normal_returns;
    uint32_t npe_game_primary_action_selector_calls;
    uint32_t npe_game_primary_action_selector_returns;
    uint16_t npe_game_primary_action_selector_result;
    uint32_t npe_game_primary_action_late_paths;
    uint32_t npe_game_primary_action_object_guard_checks;
    uint8_t npe_game_primary_action_object_guard_value;
    uint32_t npe_game_primary_action_object_guard_passes;
    uint32_t npe_game_primary_action_object_guard_rejects;
    uint32_t npe_game_primary_action_object_commits;
    uint8_t npe_game_primary_action_object_commit_flag;
    uint32_t npe_game_direction_up_paths;
    uint32_t npe_game_direction_down_paths;
    uint32_t npe_game_direction_left_paths;
    uint32_t npe_game_direction_right_paths;
    bool npe_game_direction_helper_active;
    uint32_t npe_game_direction_helper_calls;
    uint32_t npe_game_direction_helper_returns;
    uint16_t npe_game_direction_helper_result;
    uint8_t npe_game_direction_code;
    uint8_t npe_game_direction_before_x;
    uint8_t npe_game_direction_before_y;
    uint8_t npe_game_direction_before_offset_x;
    uint8_t npe_game_direction_before_offset_y;
    uint8_t npe_game_direction_after_x;
    uint8_t npe_game_direction_after_y;
    uint8_t npe_game_direction_after_offset_x;
    uint8_t npe_game_direction_after_offset_y;
    uint16_t npe_game_direction_before_map_index;
    uint16_t npe_game_direction_before_scroll;
    uint16_t npe_game_direction_after_map_index;
    uint16_t npe_game_direction_after_scroll;
    bool npe_game_render_active;
    bool npe_game_render_object_valid;
    bool npe_game_render_callback_object_valid;
    uint32_t npe_game_render_calls;
    uint32_t npe_game_render_callback_dispatches;
    uint16_t npe_game_render_entry_sp;
    uint16_t npe_game_render_entry_fp;
    uint16_t npe_game_render_object_hi;
    uint16_t npe_game_render_object_lo;
    uint16_t npe_game_render_stack_object_hi;
    uint16_t npe_game_render_stack_object_lo;
    uint16_t npe_game_render_callback_sp;
    uint16_t npe_game_render_callback_fp;
    uint16_t npe_game_render_callback_r0;
    uint16_t npe_game_render_callback_r1;
    uint16_t npe_game_render_callback_target_segment;
    uint16_t npe_game_render_callback_target_pc;
    uint16_t npe_game_render_callback_object_hi;
    uint16_t npe_game_render_callback_object_lo;
    uint16_t npe_game_render_entry_words[
        DMCU_NPE_GAME_RENDER_OBJECT_WORDS];
    uint16_t npe_game_render_callback_words[
        DMCU_NPE_GAME_RENDER_OBJECT_WORDS];
    /* Bounded, read-only samples at the exact 1F:D674 draw-decision
     * boundary.  The local byte at FP-9 is consumed as a signed state after
     * the 20-slot object scan; no value here is supplied back to the guest. */
    uint32_t npe_game_branch_trace_count;
    uint8_t npe_game_branch_state[DMCU_NPE_GAME_BRANCH_TRACE_SLOTS];
    uint8_t npe_game_branch_index[DMCU_NPE_GAME_BRANCH_TRACE_SLOTS];
    uint8_t npe_game_branch_live[DMCU_NPE_GAME_BRANCH_TRACE_SLOTS];
    uint16_t npe_game_branch_fp[DMCU_NPE_GAME_BRANCH_TRACE_SLOTS];
    uint16_t npe_game_branch_mode[DMCU_NPE_GAME_BRANCH_TRACE_SLOTS];
    uint16_t npe_game_branch_grid[DMCU_NPE_GAME_BRANCH_TRACE_SLOTS][7];
    /* First reads made by the dynamically loaded NPE code from the exact
     * DS0=66/63 global ranges seen in its disassembly. */
    uint32_t npe_game_data_trace_count;
    uint32_t npe_game_data_trace_pc[DMCU_NPE_GAME_DATA_TRACE_SLOTS];
    uint32_t npe_game_data_trace_physical[DMCU_NPE_GAME_DATA_TRACE_SLOTS];
    uint16_t npe_game_data_trace_logical[DMCU_NPE_GAME_DATA_TRACE_SLOTS];
    uint16_t npe_game_data_trace_value[DMCU_NPE_GAME_DATA_TRACE_SLOTS];
    uint16_t npe_game_data_trace_ds0[DMCU_NPE_GAME_DATA_TRACE_SLOTS];
    uint16_t npe_game_data_trace_ds1[DMCU_NPE_GAME_DATA_TRACE_SLOTS];
    uint8_t npe_game_data_trace_bits[DMCU_NPE_GAME_DATA_TRACE_SLOTS];
    /* First guest writes which overlap the dynamically loaded NPE data
     * ranges above.  PRE is the mapped-bus value before the normal store,
     * NEW is the pending guest value, and POST is the mapped-bus value after
     * the normal store.  These fields are diagnostic only and are never read
     * by guest execution. */
    uint32_t npe_game_data_write_trace_count;
    uint32_t npe_game_data_write_trace_pc[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint32_t npe_game_data_write_trace_physical[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint16_t npe_game_data_write_trace_logical[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint16_t npe_game_data_write_trace_pre[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint16_t npe_game_data_write_trace_new[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint16_t npe_game_data_write_trace_post[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint16_t npe_game_data_write_trace_sp[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint16_t npe_game_data_write_trace_fp[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint16_t npe_game_data_write_trace_ds0[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint16_t npe_game_data_write_trace_ds1[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint8_t npe_game_data_write_trace_bits[
        DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS];
    uint32_t npe_game_frame_valid;
    uint32_t npe_game_frame_back_hash[DMCU_NPE_GAME_FRAME_STAGES];
    uint32_t npe_game_frame_front_hash[DMCU_NPE_GAME_FRAME_STAGES];
    uint16_t npe_game_frame_back_nonzero[DMCU_NPE_GAME_FRAME_STAGES];
    uint16_t npe_game_frame_front_nonzero[DMCU_NPE_GAME_FRAME_STAGES];
    uint32_t npe_game_frame_pointer[DMCU_NPE_GAME_FRAME_STAGES];
    uint16_t npe_game_frame_mode[DMCU_NPE_GAME_FRAME_STAGES];
    /* Read-only ownership trace for native NPE 03:4010 stream calls and the
     * 20 x 14-byte game-object table at physical 52:6CA2.  The short ring
     * covers every source-proven game-lifetime stream call; table-specific
     * counters and copies remain separately identifiable.  No field below
     * is consumed by guest execution. */
    bool npe_game_table_loader_active;
    uint32_t npe_game_table_loader_calls;
    uint32_t npe_game_table_loader_returns;
    uint32_t npe_game_table_loader_argument;
    uint16_t npe_game_table_loader_entry_sp;
    uint16_t npe_game_table_loader_entry_fp;
    uint16_t npe_game_table_loader_return_r0;
    uint16_t npe_game_table_loader_return_r1;
    uint32_t npe_game_table_loader_last_pc;
    uint32_t npe_game_table_loader_last_target;
    uint16_t npe_game_table_loader_last_word;
    uint16_t npe_game_table_loader_last_sp;
    uint16_t npe_game_table_loader_last_fp;
    uint32_t npe_game_table_loader_edge_count;
    uint32_t npe_game_table_loader_edge_from[
        DMCU_NPE_GAME_LOADER_EDGE_SLOTS];
    uint32_t npe_game_table_loader_edge_to[
        DMCU_NPE_GAME_LOADER_EDGE_SLOTS];
    uint16_t npe_game_table_loader_edge_word[
        DMCU_NPE_GAME_LOADER_EDGE_SLOTS];
    uint16_t npe_game_table_loader_edge_sp[
        DMCU_NPE_GAME_LOADER_EDGE_SLOTS];
    uint16_t npe_game_table_loader_edge_fp[
        DMCU_NPE_GAME_LOADER_EDGE_SLOTS];
    bool npe_game_table_resolver_active;
    uint32_t npe_game_table_resolver_calls;
    uint32_t npe_game_table_resolver_returns;
    uint32_t npe_game_table_resolver_from;
    uint32_t npe_game_table_resolver_expected_return;
    uint16_t npe_game_table_resolver_args[5];
    uint16_t npe_game_table_resolver_result_r0;
    uint16_t npe_game_table_resolver_result_r1;
    uint16_t npe_game_table_resolver_error;
    uint32_t npe_game_table_resolver_current_slot;
    uint32_t npe_game_table_resolver_from_trace[
        DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS];
    uint32_t npe_game_table_resolver_stream_trace[
        DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS];
    uint32_t npe_game_table_resolver_offset_trace[
        DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS];
    uint32_t npe_game_table_resolver_position_before_trace[
        DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS];
    uint32_t npe_game_table_resolver_position_after_trace[
        DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS];
    uint16_t npe_game_table_resolver_whence_trace[
        DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS];
    uint16_t npe_game_table_resolver_result_r0_trace[
        DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS];
    uint16_t npe_game_table_resolver_result_r1_trace[
        DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS];
    uint16_t npe_game_table_resolver_error_trace[
        DMCU_NPE_GAME_STREAM_RESOLVE_SLOTS];
    bool npe_game_table_io_active;
    uint32_t npe_game_table_io_calls;
    uint32_t npe_game_table_io_returns;
    uint32_t npe_game_table_io_methods;
    uint32_t npe_game_table_io_method_returns;
    uint32_t npe_game_table_io_table_calls;
    uint32_t npe_game_table_io_current_slot;
    uint32_t npe_game_table_io_write_base;
    uint32_t npe_game_table_io_from[DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint32_t npe_game_table_io_stream[DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint32_t npe_game_table_io_destination[DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint32_t npe_game_table_io_position_before[
        DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint32_t npe_game_table_io_position_after[
        DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint16_t npe_game_table_io_length[DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint32_t npe_game_table_io_method[DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint16_t npe_game_table_io_result_r0[DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint16_t npe_game_table_io_result_r1[DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint16_t npe_game_table_io_error[DMCU_NPE_GAME_TABLE_IO_SLOTS];
    uint32_t npe_game_table_io_writes[DMCU_NPE_GAME_TABLE_IO_SLOTS];
    bool npe_game_high_stream_io_active;
    uint32_t npe_game_high_stream_io_calls;
    uint32_t npe_game_high_stream_io_returns;
    uint32_t npe_game_high_stream_io_current_slot;
    uint32_t npe_game_high_stream_io_from[
        DMCU_NPE_GAME_HIGH_STREAM_IO_SLOTS];
    uint32_t npe_game_high_stream_io_destination[
        DMCU_NPE_GAME_HIGH_STREAM_IO_SLOTS];
    uint32_t npe_game_high_stream_io_position_before[
        DMCU_NPE_GAME_HIGH_STREAM_IO_SLOTS];
    uint32_t npe_game_high_stream_io_position_after[
        DMCU_NPE_GAME_HIGH_STREAM_IO_SLOTS];
    uint16_t npe_game_high_stream_io_length[
        DMCU_NPE_GAME_HIGH_STREAM_IO_SLOTS];
    uint16_t npe_game_high_stream_io_result_r0[
        DMCU_NPE_GAME_HIGH_STREAM_IO_SLOTS];
    uint16_t npe_game_high_stream_io_result_r1[
        DMCU_NPE_GAME_HIGH_STREAM_IO_SLOTS];
    uint16_t npe_game_high_stream_io_error[
        DMCU_NPE_GAME_HIGH_STREAM_IO_SLOTS];
    /* Observation-only calls into the relocated 42:0000 -> 25:0000 leaf.
     * Its two format-dependent callees are currently the boundary under
     * investigation; no field below is consumed by guest execution. */
    uint32_t npe_transition_leaf_calls;
    uint32_t npe_transition_leaf_returns;
    uint32_t npe_transition_leaf_low_dispatch_calls;
    uint32_t npe_transition_leaf_high_dispatch_calls;
    uint32_t npe_transition_leaf_from[DMCU_NPE_TRANSITION_LEAF_SLOTS];
    uint16_t npe_transition_leaf_sp[DMCU_NPE_TRANSITION_LEAF_SLOTS];
    uint16_t npe_transition_leaf_state[DMCU_NPE_TRANSITION_LEAF_SLOTS];
    uint16_t npe_transition_leaf_format[DMCU_NPE_TRANSITION_LEAF_SLOTS];
    uint16_t npe_transition_leaf_args[DMCU_NPE_TRANSITION_LEAF_SLOTS][6];
    uint8_t npe_transition_leaf_branch[DMCU_NPE_TRANSITION_LEAF_SLOTS];
    uint16_t npe_transition_leaf_result[DMCU_NPE_TRANSITION_LEAF_SLOTS];
    /* Observation-only inventory of the NPE stream ranges requested by the
     * source-proven 0C:BDBE..0C:F256 loader.  A 4 KiB page histogram retains
     * old reads after the short per-call trace ring wraps, so later input can
     * be compared with the cold-load baseline without changing guest I/O. */
    uint32_t npe_game_stream_position_min;
    uint32_t npe_game_stream_position_max;
    uint32_t npe_game_stream_position_returns;
    uint32_t npe_game_stream_position_changed;
    uint32_t npe_game_stream_position_reverse;
    uint32_t npe_game_stream_pages_touched;
    uint64_t npe_game_stream_requested_bytes;
    uint64_t npe_game_stream_advanced_bytes;
    uint32_t npe_game_stream_page_calls[DMCU_NPE_GAME_STREAM_PAGE_COUNT];
    bool npe_game_grid_count_io_active;
    uint32_t npe_game_grid_count_io_calls;
    uint32_t npe_game_grid_count_io_returns;
    uint32_t npe_game_grid_count_io_stream;
    uint32_t npe_game_grid_count_io_destination;
    uint32_t npe_game_grid_count_io_position;
    uint32_t npe_game_grid_count_io_cache_position;
    uint16_t npe_game_grid_count_io_length;
    uint16_t npe_game_grid_count_io_value;
    /* Preserve every far-copy that actually targets the 20 x 14-byte game
     * table or its adjacent 14-byte grid-state block at 52:783A.  The general
     * 64-entry NPE far-copy ring is intentionally shared with later rendering
     * work and is overwritten before diagnostics are queried.  This dedicated
     * bounded ring is observation-only and retains the stream position, cache
     * position, source address, and logical bytes that fed each field. */
    uint32_t npe_game_table_copy_count;
    uint32_t npe_game_table_copy_from[DMCU_NPE_GAME_TABLE_COPY_SLOTS];
    uint32_t npe_game_table_copy_destination[DMCU_NPE_GAME_TABLE_COPY_SLOTS];
    uint32_t npe_game_table_copy_source[DMCU_NPE_GAME_TABLE_COPY_SLOTS];
    uint32_t npe_game_table_copy_length[DMCU_NPE_GAME_TABLE_COPY_SLOTS];
    uint32_t npe_game_table_copy_stream_position[
        DMCU_NPE_GAME_TABLE_COPY_SLOTS];
    uint32_t npe_game_table_copy_cache_position[
        DMCU_NPE_GAME_TABLE_COPY_SLOTS];
    uint8_t npe_game_table_copy_sample[DMCU_NPE_GAME_TABLE_COPY_SLOTS]
                                      [DMCU_NPE_GAME_TABLE_COPY_SAMPLE_BYTES];
    uint32_t npe_game_grid_write_count;
    uint32_t npe_game_grid_write_pc[DMCU_NPE_GAME_GRID_WRITE_SLOTS];
    uint32_t npe_game_grid_write_address[DMCU_NPE_GAME_GRID_WRITE_SLOTS];
    uint16_t npe_game_grid_write_old[DMCU_NPE_GAME_GRID_WRITE_SLOTS];
    uint16_t npe_game_grid_write_new[DMCU_NPE_GAME_GRID_WRITE_SLOTS];
    uint8_t npe_game_grid_write_bits[DMCU_NPE_GAME_GRID_WRITE_SLOTS];
    uint32_t npe_game_table_writes;
    uint32_t npe_game_table_changing_writes;
    uint32_t npe_game_table_nonzero_writes;
    bool npe_game_table_first_write_valid;
    bool npe_game_table_first_nonzero_valid;
    uint32_t npe_game_table_first_write_pc;
    uint32_t npe_game_table_first_write_address;
    uint16_t npe_game_table_first_write_old;
    uint16_t npe_game_table_first_write_new;
    uint16_t npe_game_table_first_write_bits;
    uint32_t npe_game_table_first_nonzero_pc;
    uint32_t npe_game_table_first_nonzero_address;
    uint16_t npe_game_table_first_nonzero_old;
    uint16_t npe_game_table_first_nonzero_new;
    uint16_t npe_game_table_first_nonzero_bits;
    uint32_t npe_game_table_last_write_pc;
    uint32_t npe_game_table_last_write_address;
    uint16_t npe_game_table_last_write_old;
    uint16_t npe_game_table_last_write_new;
    uint16_t npe_game_table_last_write_bits;
    uint32_t npe_file_read_trace_count;
    uint32_t npe_file_read_trace_from[DMCU_NPE_FILE_READ_TRACE_SLOTS];
    uint16_t npe_file_read_trace_sp[DMCU_NPE_FILE_READ_TRACE_SLOTS];
    uint16_t npe_file_read_trace_fp[DMCU_NPE_FILE_READ_TRACE_SLOTS];
    uint16_t npe_file_read_trace_args[DMCU_NPE_FILE_READ_TRACE_SLOTS][6];
    uint16_t npe_file_read_trace_error[DMCU_NPE_FILE_READ_TRACE_SLOTS];
    uint16_t npe_file_read_trace_file_error[DMCU_NPE_FILE_READ_TRACE_SLOTS];
    uint16_t npe_file_read_trace_application_state
        [DMCU_NPE_FILE_READ_TRACE_SLOTS];
    uint32_t npe_far_copy_trace_count;
    uint32_t npe_far_copy_trace_from[DMCU_NPE_FAR_COPY_TRACE_SLOTS];
    uint32_t npe_far_copy_trace_interrupts[DMCU_NPE_FAR_COPY_TRACE_SLOTS];
    uint16_t npe_far_copy_trace_sp[DMCU_NPE_FAR_COPY_TRACE_SLOTS];
    uint16_t npe_far_copy_trace_fp[DMCU_NPE_FAR_COPY_TRACE_SLOTS];
    uint16_t npe_far_copy_trace_args[DMCU_NPE_FAR_COPY_TRACE_SLOTS][6];
    uint16_t npe_far_copy_trace_error[DMCU_NPE_FAR_COPY_TRACE_SLOTS];
    uint16_t npe_far_copy_trace_file_error[DMCU_NPE_FAR_COPY_TRACE_SLOTS];
    bool npe_loader_runtime_wait_detected;
    uint32_t npe_loader_runtime_wait_from;
    uint32_t npe_loader_runtime_wait_target;
    uint16_t npe_loader_runtime_wait_sp;
    uint16_t npe_loader_runtime_wait_fp;
    uint16_t npe_loader_runtime_wait_r0;
    uint16_t npe_loader_runtime_wait_r1;
    uint16_t npe_loader_runtime_wait_error;
    uint16_t npe_loader_runtime_wait_file_error;
    uint16_t npe_loader_control_trace_last_sp;
    bool npe_loader_stack_switch_detected;
    uint32_t npe_loader_stack_switch_from;
    uint32_t npe_loader_stack_switch_target;
    uint16_t npe_loader_stack_switch_old_sp;
    uint16_t npe_loader_stack_switch_sp;
    uint16_t npe_loader_stack_switch_fp;
    uint16_t npe_loader_stack_switch_r0;
    uint16_t npe_loader_stack_switch_r1;
    uint16_t npe_loader_stack_switch_error;
    uint16_t npe_loader_stack_switch_file_error;
    bool npe_loader_state_dispatch_detected;
    uint32_t npe_loader_state_dispatch_from;
    uint32_t npe_loader_state_dispatch_target;
    uint16_t npe_loader_state_dispatch_sp;
    uint16_t npe_loader_state_dispatch_fp;
    uint16_t npe_loader_state_dispatch_r0;
    uint16_t npe_loader_state_dispatch_r1;
    uint16_t npe_loader_state_dispatch_table[6];
    uint32_t npe_state_table_write_count;
    bool npe_state_table_first_write_valid;
    uint32_t npe_state_table_first_write_pc;
    uint32_t npe_state_table_first_write_address;
    uint16_t npe_state_table_first_write_value;
    uint16_t npe_state_table_first_write_bits;
    uint32_t npe_state_table_last_write_pc;
    uint32_t npe_state_table_last_write_address;
    uint16_t npe_state_table_last_write_value;
    uint16_t npe_state_table_last_write_bits;
    bool npe_loader_error_first_write_valid;
    bool npe_loader_error_first_nonzero_valid;
    uint32_t npe_loader_error_first_write_pc;
    uint16_t npe_loader_error_first_write_old;
    uint16_t npe_loader_error_first_write_new;
    uint16_t npe_loader_error_first_write_bits;
    uint32_t npe_loader_error_first_nonzero_pc;
    uint16_t npe_loader_error_first_nonzero_old;
    uint16_t npe_loader_error_first_nonzero_new;
    uint16_t npe_loader_error_first_nonzero_bits;
    uint32_t npe_control_trace_from[DMCU_NPE_CONTROL_TRACE_SLOTS];
    uint32_t npe_control_trace_target[DMCU_NPE_CONTROL_TRACE_SLOTS];
    uint16_t npe_control_trace_word[DMCU_NPE_CONTROL_TRACE_SLOTS];
    uint16_t npe_control_trace_sp[DMCU_NPE_CONTROL_TRACE_SLOTS];
    uint16_t npe_control_trace_fp[DMCU_NPE_CONTROL_TRACE_SLOTS];
    uint16_t npe_control_trace_r0[DMCU_NPE_CONTROL_TRACE_SLOTS];
    uint16_t npe_control_trace_r1[DMCU_NPE_CONTROL_TRACE_SLOTS];
    uint16_t npe_control_trace_error[DMCU_NPE_CONTROL_TRACE_SLOTS];
    uint16_t npe_control_trace_file_error[DMCU_NPE_CONTROL_TRACE_SLOTS];
    uint32_t native_font_lookup_calls;
    uint32_t native_font_lookup_caller;
    uint32_t native_font_lookup_x;
    uint32_t native_font_lookup_y;
    uint32_t native_font_lookup_character;
    uint32_t native_font_alt_copy_calls;
    uint32_t native_font_alt_copy_caller;
    uint32_t native_font_alt_copy_args[5];
    uint32_t native_font_copy_calls;
    uint32_t native_font_copy_destination;
    uint32_t native_font_copy_source;
    uint32_t native_font_copy_length;
    uint32_t native_font_copy_nonzero;
    uint32_t native_font_copy_nonzero_calls;
    uint32_t native_font_copy_max_nonzero;
    uint32_t font_copy_trace_count;
    uint32_t font_copy_trace_character[DMCU_FONT_COPY_TRACE_SLOTS];
    uint32_t font_copy_trace_source[DMCU_FONT_COPY_TRACE_SLOTS];
    uint32_t font_copy_trace_length[DMCU_FONT_COPY_TRACE_SLOTS];
    uint32_t font_copy_trace_nonzero[DMCU_FONT_COPY_TRACE_SLOTS];
    uint32_t font_copy_trace_hash[DMCU_FONT_COPY_TRACE_SLOTS];
    uint32_t font_config_trace_count;
    uint32_t font_config_trace_pc[DMCU_FONT_CONFIG_TRACE_SLOTS];
    uint32_t font_config_trace_address[DMCU_FONT_CONFIG_TRACE_SLOTS];
    uint32_t font_config_trace_value[DMCU_FONT_CONFIG_TRACE_SLOTS];
    uint32_t font_config_trace_bits[DMCU_FONT_CONFIG_TRACE_SLOTS];
    uint32_t color_trace_count;
    uint32_t color_trace_caller[DMCU_COLOR_TRACE_SLOTS];
    uint16_t color_trace_index_a[DMCU_COLOR_TRACE_SLOTS];
    uint16_t color_trace_index_b[DMCU_COLOR_TRACE_SLOTS];
    uint32_t color_trace_address_a[DMCU_COLOR_TRACE_SLOTS];
    uint32_t color_trace_address_b[DMCU_COLOR_TRACE_SLOTS];
    uint8_t color_trace_raw_a[DMCU_COLOR_TRACE_SLOTS];
    uint8_t color_trace_raw_b[DMCU_COLOR_TRACE_SLOTS];
    uint8_t color_trace_lane_a[DMCU_COLOR_TRACE_SLOTS];
    uint8_t color_trace_lane_b[DMCU_COLOR_TRACE_SLOTS];
    uint16_t color_trace_result_a[DMCU_COLOR_TRACE_SLOTS];
    uint16_t color_trace_result_b[DMCU_COLOR_TRACE_SLOTS];
    uint32_t text_trace_count;
    uint32_t text_trace_pc[DMCU_TEXT_TRACE_SLOTS];
    uint32_t text_trace_x[DMCU_TEXT_TRACE_SLOTS];
    uint32_t text_trace_y[DMCU_TEXT_TRACE_SLOTS];
    uint32_t text_trace_pointer[DMCU_TEXT_TRACE_SLOTS];
    uint32_t text_trace_data0[DMCU_TEXT_TRACE_SLOTS];
    uint32_t text_trace_data1[DMCU_TEXT_TRACE_SLOTS];
    uint32_t desktop_text_trace_count;
    uint32_t desktop_text_trace_target[DMCU_DESKTOP_TEXT_TRACE_SLOTS];
    uint32_t desktop_text_trace_caller[DMCU_DESKTOP_TEXT_TRACE_SLOTS];
    uint32_t desktop_text_trace_x[DMCU_DESKTOP_TEXT_TRACE_SLOTS];
    uint32_t desktop_text_trace_y[DMCU_DESKTOP_TEXT_TRACE_SLOTS];
    uint32_t desktop_text_trace_pointer[DMCU_DESKTOP_TEXT_TRACE_SLOTS];
    uint32_t desktop_text_trace_data0[DMCU_DESKTOP_TEXT_TRACE_SLOTS];
    uint32_t desktop_text_trace_data1[DMCU_DESKTOP_TEXT_TRACE_SLOTS];
    uint16_t desktop_text_trace_sp[DMCU_DESKTOP_TEXT_TRACE_SLOTS];
    uint16_t desktop_text_trace_fp[DMCU_DESKTOP_TEXT_TRACE_SLOTS];
    uint32_t desktop_text_trace_chain[DMCU_DESKTOP_TEXT_TRACE_SLOTS]
                                    [DMCU_START_GLYPH_TRACE_FRAMES];
    uint32_t selector_state_trace_count;
    uint32_t selector_state_trace_pc[DMCU_SELECTOR_STATE_TRACE_SLOTS];
    uint32_t selector_state_trace_address[DMCU_SELECTOR_STATE_TRACE_SLOTS];
    uint32_t selector_state_trace_old[DMCU_SELECTOR_STATE_TRACE_SLOTS];
    uint32_t selector_state_trace_new[DMCU_SELECTOR_STATE_TRACE_SLOTS];
    uint32_t selector_state_trace_bits[DMCU_SELECTOR_STATE_TRACE_SLOTS];
    uint16_t selector_state_trace_sp[DMCU_SELECTOR_STATE_TRACE_SLOTS];
    uint16_t selector_state_trace_fp[DMCU_SELECTOR_STATE_TRACE_SLOTS];
    uint16_t selector_state_trace_ds0[DMCU_SELECTOR_STATE_TRACE_SLOTS];
    uint16_t selector_state_trace_ds1[DMCU_SELECTOR_STATE_TRACE_SLOTS];
    uint16_t selector_state_trace_gpr[DMCU_SELECTOR_STATE_TRACE_SLOTS][4];
    uint16_t selector_state_trace_locals[DMCU_SELECTOR_STATE_TRACE_SLOTS][16];
    uint16_t selector_state_trace_frame[DMCU_SELECTOR_STATE_TRACE_SLOTS][12];
    uint32_t resource_count_trace_count;
    uint32_t resource_count_trace_pc[DMCU_RESOURCE_COUNT_TRACE_SLOTS];
    uint32_t resource_count_trace_old[DMCU_RESOURCE_COUNT_TRACE_SLOTS];
    uint32_t resource_count_trace_new[DMCU_RESOURCE_COUNT_TRACE_SLOTS];
    uint32_t resource_count_trace_bits[DMCU_RESOURCE_COUNT_TRACE_SLOTS];
    uint16_t resource_count_trace_sp[DMCU_RESOURCE_COUNT_TRACE_SLOTS];
    uint16_t resource_count_trace_fp[DMCU_RESOURCE_COUNT_TRACE_SLOTS];
    uint16_t resource_count_trace_gpr[DMCU_RESOURCE_COUNT_TRACE_SLOTS][4];
    uint16_t resource_count_trace_chain[DMCU_RESOURCE_COUNT_TRACE_SLOTS]
                                       [DMCU_RESOURCE_COUNT_TRACE_FRAMES]
                                       [DMCU_RESOURCE_COUNT_TRACE_FRAME_WORDS];
    uint32_t application_state_write_count;
    uint32_t application_state_write_pc;
    uint32_t application_state_write_address;
    uint32_t application_state_write_old;
    uint32_t application_state_write_new;
    uint32_t application_state_write_bits;
    uint16_t application_state_write_sp;
    uint16_t application_state_write_fp;
    uint16_t application_state_write_gpr[10];
    uint16_t application_state_write_frame[9];
    uint16_t application_state_write_chain
        [DMCU_APPLICATION_STATE_WRITE_FRAMES][10];
    uint32_t event_state_trace_count;
    uint32_t event_state_trace_pc[DMCU_EVENT_STATE_TRACE_SLOTS];
    uint32_t event_state_trace_address[DMCU_EVENT_STATE_TRACE_SLOTS];
    uint32_t event_state_trace_old[DMCU_EVENT_STATE_TRACE_SLOTS];
    uint32_t event_state_trace_new[DMCU_EVENT_STATE_TRACE_SLOTS];
    uint32_t event_state_trace_bits[DMCU_EVENT_STATE_TRACE_SLOTS];
    uint32_t usb_boot_trace_count;
    uint32_t usb_boot_trace_pc[DMCU_USB_BOOT_TRACE_SLOTS];
    uint32_t usb_boot_trace_address[DMCU_USB_BOOT_TRACE_SLOTS];
    uint32_t usb_boot_trace_old[DMCU_USB_BOOT_TRACE_SLOTS];
    uint32_t usb_boot_trace_new[DMCU_USB_BOOT_TRACE_SLOTS];
    uint32_t usb_boot_trace_bits[DMCU_USB_BOOT_TRACE_SLOTS];
    uint32_t usb_boot_milestone_calls[DMCU_USB_BOOT_MILESTONES];
    uint32_t matrix_event_maps;
    uint32_t matrix_event_map_pc;
    uint16_t matrix_event_last;
    uint32_t matrix_candidate_writes;
    uint32_t matrix_candidate_pc;
    uint16_t matrix_candidate_last;
    /* Bounded, observer-only acknowledgement at the exact state-50/modal
     * event-dispatch boundary 1E:F8E4.  The root foreground path has its
     * independent KEYMAPRET application trace; keeping both identifies which
     * original guest consumer accepted a physical event. */
    uint32_t matrix_modal_dispatches;
    uint16_t matrix_modal_event_last;
    /* Observer-only counters for the original keyboard pipeline and the
     * NPE horizontal-direction call chain.  These identify the first stage
     * reached by a physical edge without acknowledging it or changing guest
     * memory. */
    uint32_t matrix_pipeline_stage_count[10];
    uint16_t matrix_pipeline_stage_sp[10];
    uint16_t matrix_pipeline_stage_fp[10];
    /* Read-only ring for distinguishing one physical scan from duplicate
     * entries into the exact completion wrapper/worker. */
    uint32_t matrix_completion_trace_count;
    uint32_t matrix_completion_trace_pc[DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint32_t matrix_completion_trace_previous_pc
        [DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_sp[DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_fp[DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_ds0[DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_ds1[DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_gate[DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_index[DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_candidate
        [DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_mapped
        [DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_critical
        [DMCU_MATRIX_COMPLETION_TRACE_SLOTS];
    uint16_t matrix_completion_trace_sfr[DMCU_MATRIX_COMPLETION_TRACE_SLOTS][3];
    uint16_t matrix_completion_trace_stack
        [DMCU_MATRIX_COMPLETION_TRACE_SLOTS]
        [DMCU_MATRIX_COMPLETION_TRACE_STACK_WORDS];
    uint32_t post_registry_hook_returns;
    uint32_t post_registry_hook_return_pc;
    uint16_t post_registry_hook_return_sp;
    uint16_t post_registry_hook_return_word0;
    uint16_t post_registry_hook_return_word1;
    uint32_t post_registry_hook_exec[3];
    uint16_t post_registry_hook_word[3];
    uint32_t overlay_code_syncs;
    /* Observer-only history for the 4F:A922 -> 32:A922 comparison adapter.
     * The exact guest loader installs this writable code island early, while
     * later application publishing may reuse the same destination. */
    uint32_t far_compare_overlay_writes;
    uint32_t far_compare_overlay_first_pc;
    uint32_t far_compare_overlay_first_address;
    uint16_t far_compare_overlay_first_old;
    uint16_t far_compare_overlay_first_value;
    uint8_t far_compare_overlay_first_bits;
    uint32_t far_compare_overlay_last_pc;
    uint32_t far_compare_overlay_last_address;
    uint16_t far_compare_overlay_last_old;
    uint16_t far_compare_overlay_last_value;
    uint8_t far_compare_overlay_last_bits;
    /* Observer-only edges into the collision-sensitive flat 32:B63C
     * continuation.  Recording the completed predecessor distinguishes a
     * genuine sequential 32:B638 fallthrough from a direct SCALL without
     * redirecting either path. */
    uint32_t resource_open_continuation_trace_count;
    uint32_t resource_open_continuation_trace_from[
        DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS];
    uint32_t resource_open_continuation_trace_sequential[
        DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS];
    uint16_t resource_open_continuation_trace_word[
        DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS];
    uint16_t resource_open_continuation_trace_ext[
        DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS];
    uint16_t resource_open_continuation_trace_sp[
        DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS];
    uint16_t resource_open_continuation_trace_post_sp[
        DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS];
    uint16_t resource_open_continuation_trace_fp[
        DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS];
    uint16_t resource_open_continuation_trace_regs[
        DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS][4];
    uint16_t resource_open_continuation_trace_stack[
        DMCU_RESOURCE_OPEN_CONTINUATION_TRACE_SLOTS]
        [DMCU_RESOURCE_OPEN_CONTINUATION_STACK_WORDS];
    uint32_t file_record_overlay_writes;
    uint32_t file_record_overlay_first_pc;
    uint32_t file_record_overlay_first_address;
    uint16_t file_record_overlay_first_value;
    uint8_t file_record_overlay_first_bits;
    uint32_t file_record_overlay_last_pc;
    uint32_t file_record_overlay_last_address;
    uint16_t file_record_overlay_last_value;
    uint8_t file_record_overlay_last_bits;
    uint32_t resource_recovery_word_writes;
    uint32_t resource_recovery_word_first_pc;
    uint32_t resource_recovery_word_first_address;
    uint16_t resource_recovery_word_first_old;
    uint16_t resource_recovery_word_first_value;
    uint8_t resource_recovery_word_first_bits;
    uint32_t resource_recovery_word_last_pc;
    uint32_t resource_recovery_word_last_address;
    uint16_t resource_recovery_word_last_old;
    uint16_t resource_recovery_word_last_value;
    uint8_t resource_recovery_word_last_bits;
    uint32_t event_state_overlay_writes;
    uint32_t event_state_overlay_first_pc;
    uint32_t event_state_overlay_first_address;
    uint16_t event_state_overlay_first_old;
    uint16_t event_state_overlay_first_value;
    uint8_t event_state_overlay_first_bits;
    uint32_t event_state_overlay_last_pc;
    uint32_t event_state_overlay_last_address;
    uint16_t event_state_overlay_last_old;
    uint16_t event_state_overlay_last_value;
    uint8_t event_state_overlay_last_bits;
    uint32_t menu_overlay_copy_reads;
    uint32_t menu_overlay_copy_writes;
    uint32_t menu_overlay_entry_writes;
    uint32_t generic_menu_all_writes;
    uint32_t generic_menu_last_write_pc;
    uint32_t generic_menu_last_write_address;
    uint16_t generic_menu_last_write_value;
    uint32_t menu_catalog_all_writes;
    uint32_t menu_catalog_first_write_pc;
    uint32_t menu_catalog_first_write_address;
    uint16_t menu_catalog_first_write_value;
    uint32_t menu_catalog_last_write_pc;
    uint32_t menu_catalog_last_write_address;
    uint16_t menu_catalog_last_write_value;
    uint32_t menu_overlay_first_read_pc;
    uint32_t menu_overlay_first_read_address;
    uint16_t menu_overlay_first_read_value;
    uint32_t menu_overlay_first_write_pc;
    uint32_t menu_overlay_first_write_address;
    uint16_t menu_overlay_first_write_value;
    uint32_t menu_overlay_last_write_pc;
    uint32_t menu_overlay_last_write_address;
    uint16_t menu_overlay_last_write_value;
    uint32_t overlay_service_calls;
    uint32_t interrupt_entries;
    uint32_t software_traps;
    uint32_t interrupt_returns;
    uint32_t interrupt_frame_overlap_deferrals;
    uint32_t interrupt_last_entry_pc;
    uint32_t interrupt_last_entry_sp;
    uint32_t interrupt_last_return_from;
    uint32_t interrupt_last_return_pc;
    uint32_t interrupt_last_return_sp;
    uint32_t interrupt_bad_returns;
    uint32_t interrupt_first_bad_from;
    uint32_t interrupt_first_bad_sp;
    uint32_t interrupt_first_bad_entry_pc;
    uint32_t interrupt_first_bad_entry_sp;
    uint32_t interrupt_first_bad_return_pc;
    uint32_t interrupt_first_bad_frame_sp;
    uint32_t interrupt_first_bad_frame_base;
    uint32_t interrupt_frame_base;
    uint32_t interrupt_frame_expected_psw;
    uint32_t interrupt_frame_expected_cs;
    uint32_t interrupt_frame_expected_pc;
    uint32_t interrupt_frame_writes;
    uint32_t interrupt_frame_first_write_entry;
    uint32_t interrupt_frame_first_write_entry_pc;
    uint32_t interrupt_frame_first_write_base;
    uint32_t interrupt_frame_first_write_pc;
    uint32_t interrupt_frame_first_write_address;
    uint32_t interrupt_frame_first_write_old;
    uint32_t interrupt_frame_first_write_new;
    uint32_t interrupt_frame_first_write_bits;
    uint32_t interrupt_frame_first_write_sp;
    uint32_t interrupt_frame_first_write_fp;
    bool interrupt_frame_watch_active;
    uint32_t interrupt_foreground_fp_address;
    uint32_t interrupt_foreground_fp_expected;
    uint32_t interrupt_foreground_fp_writes;
    uint32_t interrupt_foreground_fp_first_entry;
    uint32_t interrupt_foreground_fp_first_entry_pc;
    uint32_t interrupt_foreground_fp_first_write_pc;
    uint32_t interrupt_foreground_fp_first_old;
    uint32_t interrupt_foreground_fp_first_new;
    uint32_t interrupt_foreground_fp_first_bits;
    uint32_t interrupt_foreground_fp_first_sp;
    uint32_t interrupt_foreground_fp_first_fp;
    uint32_t completed_instruction_pc;
    uint32_t completed_instruction_next_pc;
    uint16_t completed_instruction_word;
    uint16_t completed_instruction_ext;
    uint32_t current_instruction_pc;
    uint32_t interrupt_midword_entries;
    uint32_t interrupt_first_midword_pc;
    uint32_t interrupt_first_midword_completed_pc;
    uint32_t interrupt_first_midword_completed_next_pc;
    uint16_t interrupt_first_midword_completed_word;
    uint16_t interrupt_first_midword_completed_ext;
    uint32_t web_key_state;
    uint32_t web_key_code;
    uint32_t web_matrix_state_low;
    uint32_t web_matrix_state_high;
    uint32_t hle_ui_page;
    uint32_t hle_ui_selection;
    uint32_t hle_ui_key_latch;
    uint32_t native_ui_key_latch;
    uint32_t native_ui_events;
    uint32_t native_ui_last_event;
    uint32_t rom_probe_calls;
    uint32_t rom_probe_target;
    uint32_t rom_probe_args[3];
    uint32_t missing_rom_pc;
    uint32_t missing_rom_fetches;
    uint32_t missing_rom_previous_pc;
    uint32_t missing_rom_previous_word;
    uint32_t missing_rom_sp;
    uint32_t missing_rom_psw;
    uint32_t missing_rom_in_interrupt;
    uint32_t missing_rom_control_from;
    uint32_t missing_rom_control_to;
    uint32_t missing_rom_control_word;
    uint32_t missing_rom_control_sp;
    uint32_t missing_rom_control_fp;
    uint32_t event_frame_base;
    uint32_t event_frame_write_pc;
    uint32_t event_frame_write_address;
    uint32_t event_frame_write_old;
    uint32_t event_frame_write_new;
    uint32_t event_frame_write_bits;
    uint32_t event_frame_write_sp;
    uint32_t event_frame_write_fp;
    uint32_t invalid_control_from;
    uint32_t invalid_control_to;
    uint32_t invalid_control_word;
    uint32_t invalid_control_sequential;
    uint32_t invalid_control_ext;
    uint32_t invalid_control_sp;
    uint32_t invalid_control_fp;
    uint32_t invalid_control_post_sp;
    uint32_t invalid_control_post_fp;
    uint32_t invalid_control_ds0;
    uint32_t invalid_control_ds1;
    uint32_t invalid_control_psw;
    uint32_t invalid_control_in_interrupt;
    uint16_t invalid_control_gpr[DMCU_INVALID_CONTROL_GPR_WORDS];
    uint16_t invalid_control_stack[DMCU_INVALID_CONTROL_STACK_WORDS];
    uint16_t invalid_control_frame[DMCU_INVALID_CONTROL_FRAME_WORDS];
    /* Read-only lifecycle for the settings leaf's event poll and its
     * independent physical E0 launch edge.  This distinguishes a failure in
     * the event callback from actually reaching resident 15:F0EE. */
    uint32_t settings_event_poll_calls;
    uint32_t settings_event_poll_returns;
    bool settings_event_poll_active;
    uint32_t settings_event_callback_calls;
    uint32_t settings_event_callback_target;
    uint32_t settings_event_launch_calls;
    uint16_t settings_event_last_value;
    uint16_t settings_event_callback_hi;
    uint16_t settings_event_callback_lo;
    /* Read-only control-flow provenance for the exact 15:F2CA -> 11:1752
     * input-dispatch call made by the restored resident E0 handler.  The
     * dedicated ring remains live even when an older diagnostic has frozen
     * the generic CONTROL_TRACE ring. */
    uint32_t settings_input_dispatch_entries;
    uint32_t settings_input_dispatch_returns;
    bool settings_input_dispatch_active;
    uint32_t settings_input_trace_count;
    uint32_t settings_input_trace_from[DMCU_SETTINGS_INPUT_TRACE_SLOTS];
    uint32_t settings_input_trace_target[DMCU_SETTINGS_INPUT_TRACE_SLOTS];
    uint16_t settings_input_trace_word[DMCU_SETTINGS_INPUT_TRACE_SLOTS];
    uint16_t settings_input_trace_sp[DMCU_SETTINGS_INPUT_TRACE_SLOTS];
    uint16_t settings_input_trace_fp[DMCU_SETTINGS_INPUT_TRACE_SLOTS];
    bool settings_input_region_valid;
    uint32_t settings_input_region_from;
    uint32_t settings_input_region_target;
    uint32_t settings_input_region_sequential;
    uint16_t settings_input_region_word;
    uint16_t settings_input_region_ext;
    uint16_t settings_input_region_sp;
    uint16_t settings_input_region_post_sp;
    uint16_t settings_input_region_fp;
    uint16_t settings_input_region_ds0;
    uint16_t settings_input_region_ds1;
    uint16_t settings_input_region_gpr[DMCU_SETTINGS_INPUT_GPR_WORDS];
    uint16_t settings_input_region_stack[DMCU_SETTINGS_INPUT_STACK_WORDS];
    uint16_t settings_input_region_frame[DMCU_SETTINGS_INPUT_FRAME_WORDS];
    /* Read-only checkpoints through the real state-0x55 settings route,
     * the five-item sound-settings selector and persistence dispatcher. */
    uint32_t sound_settings_trace_count;
    uint32_t sound_settings_trace_pc[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint32_t sound_settings_trace_target[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_kind[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_event[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_selection[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_highlight[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_cursor[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_switch_state[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_switch_aux[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_switch_step[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_r0[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_r1[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_sp[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_post_sp[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_fp[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_return_cs[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint16_t sound_settings_trace_return_pc[DMCU_SOUND_SETTINGS_TRACE_SLOTS];
    uint32_t application_init_f3c6_entries;
    uint32_t application_init_f3c6_entry_sp;
    uint32_t application_init_f3c6_entry_fp;
    uint32_t application_init_f3c6_entry_gpr[4];
    uint16_t application_init_f3c6_entry_stack[
        DMCU_APPLICATION_INIT_F3C6_STACK_WORDS];
    uint32_t application_init_f3c6_returns;
    uint32_t application_init_f3c6_return_sp;
    uint32_t application_init_f3c6_return_fp;
    uint32_t application_init_f3c6_return_gpr[4];
    uint16_t application_init_f3c6_return_stack[
        DMCU_APPLICATION_INIT_F3C6_STACK_WORDS];
    uint32_t application_init_f3c6_child_entries;
    uint32_t hardware_init_return_entries;
    uint32_t hardware_init_return_base;
    uint32_t hardware_init_return_initial[2];
    uint32_t hardware_init_return_entry_previous_pc;
    uint32_t hardware_init_return_entry_previous_next_pc;
    uint32_t hardware_init_return_entry_previous_word;
    uint32_t hardware_init_return_entry_previous_ext;
    uint32_t hardware_init_return_entry_sp;
    uint32_t hardware_init_return_entry_fp;
    uint32_t hardware_init_return_writes;
    uint32_t hardware_init_return_first_pc;
    uint32_t hardware_init_return_first_bus;
    uint32_t hardware_init_return_first_logical;
    uint32_t hardware_init_return_first_physical;
    uint32_t hardware_init_return_first_old;
    uint32_t hardware_init_return_first_new;
    uint32_t hardware_init_return_first_bits;
    uint32_t hardware_init_return_first_sp;
    uint32_t hardware_init_return_first_fp;
    uint32_t hardware_init_return_exits;
    uint32_t hardware_init_return_exit[2];
    uint32_t hardware_init_return_exit_sp;
    uint32_t hardware_init_return_exit_fp;
    uint64_t graphics_continuation_calls;
    uint32_t graphics_continuation_from[
        DMCU_GRAPHICS_CONTINUATION_TRACE_SLOTS];
    uint16_t graphics_continuation_sp[
        DMCU_GRAPHICS_CONTINUATION_TRACE_SLOTS];
    uint16_t graphics_continuation_fp[
        DMCU_GRAPHICS_CONTINUATION_TRACE_SLOTS];
    uint16_t graphics_continuation_limit[
        DMCU_GRAPHICS_CONTINUATION_TRACE_SLOTS];
    uint16_t graphics_continuation_step[
        DMCU_GRAPHICS_CONTINUATION_TRACE_SLOTS];
    uint16_t graphics_continuation_index[
        DMCU_GRAPHICS_CONTINUATION_TRACE_SLOTS];
    uint16_t graphics_continuation_args[
        DMCU_GRAPHICS_CONTINUATION_TRACE_SLOTS][6];
    uint64_t graphics_continuation_returns;
    uint32_t graphics_continuation_return_from;
    uint16_t graphics_continuation_return_limit;
    uint16_t graphics_continuation_return_step;
    uint16_t graphics_continuation_return_index;
    uint32_t graphics_frame_entries;
    uint16_t graphics_frame_base;
    uint16_t graphics_frame_initial_limit;
    uint16_t graphics_frame_initial_step;
    uint16_t graphics_frame_initial_index;
    uint32_t graphics_frame_limit_writes;
    uint32_t graphics_frame_limit_last_pc;
    uint16_t graphics_frame_limit_last_old;
    uint16_t graphics_frame_limit_last_new;
    uint16_t graphics_frame_limit_last_bits;
    uint32_t event_text_write_count;
    uint32_t event_text_first_pc;
    uint32_t event_text_first_address;
    uint32_t event_text_first_value;
    uint32_t event_text_first_bits;
    uint32_t event_text_last_pc;
    uint32_t event_text_last_address;
    uint32_t event_text_last_value;
    uint32_t event_text_last_bits;
    uint32_t event_text_overwrite_pc;
    uint32_t event_text_overwrite_destination;
    uint32_t event_text_overwrite_source;
    uint32_t event_text_overwrite_r1;
    uint32_t event_text_overwrite_r8;
    uint32_t event_text_overwrite_r9;
    uint32_t event_text_overwrite_sp;
    uint32_t event_text_overwrite_fp;
    uint32_t far_copy_bad_from;
    uint32_t far_copy_bad_sp;
    uint32_t far_copy_bad_fp;
    uint32_t far_copy_bad_args[6];
    uint32_t missing_rom_calls;
    uint32_t missing_rom_call_target;
    uint32_t missing_rom_call_caller;
    uint32_t missing_rom_call_return;
    uint32_t missing_rom_call_sp;
    uint32_t missing_rom_call_psw;
    uint32_t missing_rom_call_ds0;
    uint32_t missing_rom_call_ds1;
    uint32_t missing_rom_call_gpr[16];
    uint32_t missing_rom_call_stack[DMCU_ROM_TRACE_STACK_WORDS];
    uint32_t bbf6_status_calls;
    uint32_t bbf6_status_page;
    uint32_t bbf6_status_column;
    uint32_t bbf6_status_length;
    uint32_t bbf6_full_calls;
    uint32_t bbf6_full_page;
    uint32_t bbf6_full_column;
    uint32_t bbf6_full_length;
    uint32_t b730_status_reads;
    uint32_t b730_status_ff;
    uint32_t b730_status_zero;
    uint32_t b730_status_other;
    uint32_t b730_status_last;
    uint32_t b730_full_path_entries;
    uint32_t exec_trace_pc[DMCU_EXEC_TRACE_WORDS];
    uint32_t exec_trace_word[DMCU_EXEC_TRACE_WORDS];
    uint32_t exec_trace_count;
    uint32_t foreground_trace_pc[DMCU_FOREGROUND_TRACE_WORDS];
    uint32_t foreground_trace_word[DMCU_FOREGROUND_TRACE_WORDS];
    uint32_t foreground_trace_sp[DMCU_FOREGROUND_TRACE_WORDS];
    uint32_t foreground_trace_count;
    uint32_t vma03_clear_entries;
    uint32_t vma03_clear_exits;
    uint32_t vma03_clear_max_counter;
    uint32_t vma03_object_pointer_writes;
    uint32_t vma03_object_pointer_write_pc;
    uint16_t vma03_object_pointer_old[2];
    uint16_t vma03_object_pointer_new[2];
    uint32_t vma03_handle_entries;
    uint32_t vma03_handle_previous_pc;
    uint16_t vma03_handle_previous_word;
    uint16_t vma03_handle_entry_sp;
    uint16_t vma03_handle_entry_fp;
    uint16_t vma03_handle_entry_stack[8];
    uint32_t vma03_handle_constructor_31_entries;
    uint32_t vma03_handle_constructor_32_entries;
    uint32_t control_trace_from[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_to[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_word[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_sp[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_fp[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_count;
    bool control_trace_frozen;
    /* Diagnostic-only countdown armed after the isolated NPE FAT16
     * directory page is read.  It freezes the existing read-only control
     * ring after the first bounded post-read path, before UI redraws can
     * overwrite the directory parser evidence. */
    uint16_t npe_directory_trace_remaining;
    bool npe_directory_trace_triggered;
    bool npe_glyph_trace_armed;
    uint32_t npe_directory_data_read_count;
    uint32_t npe_browser_layout_calls;
    uint16_t npe_browser_layout_depth;
    uint16_t npe_browser_layout_active[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_DEPTH];
    uint32_t npe_browser_layout_caller[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS];
    uint32_t npe_browser_layout_return_target[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS];
    uint32_t npe_browser_layout_object[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS];
    uint16_t npe_browser_layout_entry_sp[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS];
    uint16_t npe_browser_layout_entry_fp[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS];
    uint16_t npe_browser_layout_return_sp[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS];
    uint16_t npe_browser_layout_return_fp[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS];
    uint16_t npe_browser_layout_entry_gpr[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS][4];
    uint16_t npe_browser_layout_return_gpr[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS][4];
    uint16_t npe_browser_layout_before[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS]
        [DMCU_NPE_BROWSER_LAYOUT_OBJECT_WORDS];
    uint16_t npe_browser_layout_after[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS]
        [DMCU_NPE_BROWSER_LAYOUT_OBJECT_WORDS];
    bool npe_browser_layout_object_valid[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS];
    bool npe_browser_layout_returned[
        DMCU_NPE_BROWSER_LAYOUT_TRACE_SLOTS];
    /* Exact 1C:D92C -> 1F:5BFA object-mask call and its three immediate
     * consumers in the file-browser layout.  This diagnostic is bounded to
     * the first call in the currently armed NPE render operation and never
     * changes guest state. */
    bool npe_object_mask_watch_active;
    uint32_t npe_object_mask_calls;
    uint32_t npe_object_mask_returns;
    uint32_t npe_object_mask_caller;
    uint32_t npe_object_mask_return_from;
    uint32_t npe_object_mask_return_target;
    uint16_t npe_object_mask_entry_sp;
    uint16_t npe_object_mask_entry_post_sp;
    uint16_t npe_object_mask_entry_fp;
    uint16_t npe_object_mask_arg_hi;
    uint16_t npe_object_mask_arg_lo;
    uint16_t npe_object_mask_return_sp;
    uint16_t npe_object_mask_return_post_sp;
    uint16_t npe_object_mask_return_fp;
    uint16_t npe_object_mask_return_r0;
    uint16_t npe_object_mask_return_r1;
    uint16_t npe_object_mask_entry_fields[
        DMCU_NPE_OBJECT_MASK_SNAPSHOT_WORDS];
    uint16_t npe_object_mask_return_fields[
        DMCU_NPE_OBJECT_MASK_SNAPSHOT_WORDS];
    uint32_t npe_object_mask_branch_count[3];
    uint32_t npe_object_mask_branch_from[3];
    uint32_t npe_object_mask_branch_target[3];
    uint16_t npe_object_mask_branch_psw[3];
    uint16_t npe_object_mask_branch_r0[3];
    uint32_t npe_object_mask_attach_calls[2];
    bool npe_render_object_watch_active;
    bool npe_operation_callback_watch_active;
    bool npe_render_object_initial_valid;
    bool npe_render_object_before_valid;
    bool npe_render_object_after_valid;
    uint16_t npe_render_object_base;
    uint32_t npe_render_object_calls;
    uint32_t npe_render_object_returns;
    uint32_t npe_render_object_context_calls;
    uint32_t npe_render_object_context_returns;
    uint32_t npe_render_object_context_return_from;
    uint16_t npe_render_object_context_return_word;
    uint16_t npe_render_object_context_return_sp;
    uint16_t npe_render_object_context_return_fp;
    uint16_t npe_render_object_context_result;
    uint32_t npe_render_object_context_init_entries;
    uint32_t npe_render_object_context_branch_count;
    uint32_t npe_render_object_context_branch_target;
    uint16_t npe_render_object_context_branch_psw;
    uint16_t npe_render_object_context_branch_r0;
    uint16_t npe_render_object_context_branch_r1;
    uint32_t npe_render_object_context_failure_count;
    uint32_t npe_render_object_context_failure_from;
    /* Read-only operation-1 constructor/callback boundary.  Unlike the
     * legacy RESULT_SCANNER probe this follows the D410 -> D4E8 -> D7F8
     * path actually selected when 52:517E is 1. */
    uint32_t npe_operation_context_test_calls;
    uint32_t npe_operation_context_test_returns;
    uint16_t npe_operation_context_test_entry_sp;
    uint16_t npe_operation_context_test_entry_post_sp;
    uint16_t npe_operation_context_test_entry_fp;
    uint16_t npe_operation_context_test_arg_hi;
    uint16_t npe_operation_context_test_arg_lo;
    uint32_t npe_operation_context_test_return_from;
    uint16_t npe_operation_context_test_return_word;
    uint16_t npe_operation_context_test_return_sp;
    uint16_t npe_operation_context_test_return_post_sp;
    uint16_t npe_operation_context_test_return_fp;
    uint16_t npe_operation_context_test_result;
    bool npe_operation_callbacks_installed_valid;
    uint16_t npe_operation_callbacks_object_hi;
    uint16_t npe_operation_callbacks_object_lo;
    uint16_t npe_operation_callbacks_installed[4];
    uint32_t npe_operation_layout_calls;
    uint32_t npe_operation_layout_returns;
    uint16_t npe_operation_layout_object_hi;
    uint16_t npe_operation_layout_object_lo;
    uint16_t npe_operation_layout_before[4];
    uint16_t npe_operation_layout_after[4];
    uint32_t npe_operation_event_loop_calls;
    uint32_t npe_operation_event_loop_returns;
    uint16_t npe_operation_event_loop_entry_sp;
    uint16_t npe_operation_event_loop_entry_fp;
    uint32_t npe_operation_event_loop_return_from;
    uint16_t npe_operation_event_loop_return_sp;
    uint16_t npe_operation_event_loop_return_fp;
    uint32_t npe_operation_callback_calls[
        DMCU_NPE_OPERATION_CALLBACK_SLOTS];
    uint32_t npe_operation_callback_from[
        DMCU_NPE_OPERATION_CALLBACK_SLOTS];
    uint16_t npe_operation_callback_word[
        DMCU_NPE_OPERATION_CALLBACK_SLOTS];
    uint16_t npe_operation_callback_sp[
        DMCU_NPE_OPERATION_CALLBACK_SLOTS];
    uint16_t npe_operation_callback_fp[
        DMCU_NPE_OPERATION_CALLBACK_SLOTS];
    uint16_t npe_operation_callback_stack[
        DMCU_NPE_OPERATION_CALLBACK_SLOTS]
        [DMCU_NPE_OPERATION_CALLBACK_STACK_WORDS];
    /* Fixed-size, read-only observation of the most recent exact 1B:7A20
     * format dispatch and its 2F:B6DE/B726 continuation. */
    bool npe_format_dispatch_active;
    bool npe_format_dispatch_followup_active;
    uint16_t npe_format_dispatch_followup_steps;
    uint32_t npe_format_dispatch_entries;
    uint32_t npe_format_literal_wrapper_calls;
    uint32_t npe_format_literal_copy_calls;
    uint32_t npe_format_literal_copy_returns;
    uint32_t npe_format_literal_tail_calls;
    uint32_t npe_format_field_calls;
    uint32_t npe_format_field_returns;
    uint16_t npe_format_field_return_r0;
    uint32_t npe_format_memcmp_returns[DMCU_NPE_FORMAT_MEMCMP_SLOTS];
    uint16_t npe_format_memcmp_result[DMCU_NPE_FORMAT_MEMCMP_SLOTS];
    uint16_t npe_format_memcmp_args[DMCU_NPE_FORMAT_MEMCMP_SLOTS][6];
    uint8_t npe_format_memcmp_pointer_valid[DMCU_NPE_FORMAT_MEMCMP_SLOTS][2];
    uint8_t npe_format_memcmp_sample[DMCU_NPE_FORMAT_MEMCMP_SLOTS][2]
                                      [DMCU_NPE_FORMAT_SAMPLE_BYTES];
    uint32_t npe_format_status_site_hits;
    uint32_t npe_format_status2_hits;
    uint16_t npe_format_status_value;
    uint32_t npe_format_dispatch_returns;
    uint32_t npe_format_dispatch_return_target;
    uint16_t npe_format_dispatch_return_r0;
    uint32_t npe_format_router_b6de_hits;
    uint16_t npe_format_router_b6de_r0;
    uint32_t npe_format_mode2_calls;
    uint32_t npe_format_legacy_service_calls[3];
    uint32_t npe_format_legacy_path_calls[2];
    bool npe_transform_active;
    uint32_t npe_transform_calls;
    uint32_t npe_transform_returns;
    uint32_t npe_transform_call_from;
    uint16_t npe_transform_call_sp;
    uint16_t npe_transform_call_post_sp;
    uint16_t npe_transform_call_fp;
    uint16_t npe_transform_args[DMCU_NPE_TRANSFORM_OUTER_ARGUMENT_WORDS];
    bool npe_transform_object_valid;
    bool npe_transform_buffer_valid;
    uint8_t npe_transform_object_sample[DMCU_NPE_TRANSFORM_SAMPLE_BYTES];
    uint8_t npe_transform_buffer_sample[DMCU_NPE_TRANSFORM_SAMPLE_BYTES];
    uint32_t npe_transform_resident_calls;
    uint32_t npe_transform_resident_returns;
    uint16_t npe_transform_resident_args[
        DMCU_NPE_TRANSFORM_RESIDENT_ARGUMENT_WORDS];
    uint16_t npe_transform_resident_sp;
    uint16_t npe_transform_resident_post_sp;
    uint16_t npe_transform_resident_fp;
    uint16_t npe_transform_object_type;
    uint16_t npe_transform_table_base_hi;
    uint16_t npe_transform_table_base_lo;
    uint16_t npe_transform_record_hi;
    uint16_t npe_transform_record_lo;
    uint16_t npe_transform_child_hi;
    uint16_t npe_transform_child_lo;
    uint32_t npe_transform_exit_from;
    uint32_t npe_transform_exit_target;
    uint16_t npe_transform_exit_r0;
    uint16_t npe_transform_exit_r1;
    uint16_t npe_transform_exit_file_error;
    uint32_t npe_transform_return_from;
    uint32_t npe_transform_return_target;
    uint16_t npe_transform_return_r0;
    uint16_t npe_transform_return_r1;
    uint16_t npe_transform_return_file_error;
    uint32_t npe_transform_error_page_calls;
    uint16_t npe_stream_global_at_transform_hi;
    uint16_t npe_stream_global_at_transform_lo;
    uint32_t npe_stream_global_writes;
    uint32_t npe_stream_global_write_pc[
        DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS];
    uint32_t npe_stream_global_write_address[
        DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS];
    uint16_t npe_stream_global_write_old[
        DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS];
    uint16_t npe_stream_global_write_new[
        DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS];
    uint16_t npe_stream_global_write_sp[
        DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS];
    uint16_t npe_stream_global_write_fp[
        DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS];
    uint16_t npe_stream_global_write_ds0[
        DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS];
    uint16_t npe_stream_global_write_ds1[
        DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS];
    uint8_t npe_stream_global_write_bits[
        DMCU_NPE_STREAM_GLOBAL_WRITE_TRACE_SLOTS];
    uint32_t npe_stream_initializer_calls;
    uint32_t npe_stream_initializer_returns;
    uint32_t npe_stream_initializer_caller;
    uint32_t npe_stream_initializer_return_target;
    uint16_t npe_stream_initializer_sp;
    uint16_t npe_stream_initializer_fp;
    uint16_t npe_stream_initializer_arg_hi;
    uint16_t npe_stream_initializer_arg_lo;
    uint16_t npe_stream_initializer_return_r0;
    uint16_t npe_stream_initializer_return_r1;
    uint32_t npe_stream_open_calls;
    uint32_t npe_stream_open_returns;
    uint32_t npe_stream_open_caller;
    uint32_t npe_stream_open_return_target;
    uint16_t npe_stream_open_sp;
    uint16_t npe_stream_open_fp;
    uint16_t npe_stream_open_args[DMCU_NPE_STREAM_OPEN_ARGUMENT_WORDS];
    uint16_t npe_stream_open_return_r0;
    uint16_t npe_stream_open_return_r1;
    uint32_t npe_stream_open_child_calls;
    uint32_t npe_stream_open_child_returns;
    uint32_t npe_stream_open_child_caller;
    uint32_t npe_stream_open_child_return_target;
    uint16_t npe_stream_open_child_sp;
    uint16_t npe_stream_open_child_fp;
    uint16_t npe_stream_open_child_return_r0;
    uint16_t npe_stream_open_child_return_r1;
    uint32_t npe_df06_entry_count;
    uint32_t npe_df06_entry_from;
    uint32_t npe_df06_entry_target;
    uint32_t npe_df06_entry_sequential;
    uint32_t npe_df06_entry_prior_from;
    uint32_t npe_df06_entry_prior_target;
    uint16_t npe_df06_entry_word;
    uint16_t npe_df06_entry_ext;
    uint16_t npe_df06_entry_prior_word;
    uint16_t npe_df06_entry_pre_sp;
    uint16_t npe_df06_entry_post_sp;
    uint16_t npe_df06_entry_pre_fp;
    uint16_t npe_df06_entry_post_fp;
    uint16_t npe_df06_entry_application_state;
    uint16_t npe_df06_entry_object_hi;
    uint16_t npe_df06_entry_object_lo;
    uint16_t npe_df06_entry_stream_hi;
    uint16_t npe_df06_entry_stream_lo;
    uint16_t npe_df06_entry_gpr[4];
    uint16_t npe_df06_entry_pre_stack[DMCU_NPE_DF06_STACK_WORDS];
    uint16_t npe_df06_entry_post_stack[DMCU_NPE_DF06_STACK_WORDS];
    uint32_t npe_literal_data_reads;
    uint32_t npe_literal_data_writes;
    uint32_t npe_literal_data_dispatch_read_base;
    uint32_t npe_literal_data_dispatch_write_base;
    uint32_t npe_literal_data_read_pc[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint32_t npe_literal_data_write_pc[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint32_t npe_literal_data_read_physical[
        DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint32_t npe_literal_data_write_physical[
        DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint16_t npe_literal_data_read_logical[
        DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint16_t npe_literal_data_write_logical[
        DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint16_t npe_literal_data_read_value[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint16_t npe_literal_data_write_value[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint16_t npe_literal_data_read_ds0[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint16_t npe_literal_data_read_ds1[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint16_t npe_literal_data_write_ds0[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint16_t npe_literal_data_write_ds1[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint8_t npe_literal_data_read_bits[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint8_t npe_literal_data_write_bits[DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint8_t npe_literal_data_read_dispatch[
        DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    uint8_t npe_literal_data_write_dispatch[
        DMCU_NPE_LITERAL_DATA_TRACE_SLOTS];
    bool npe_resource_check_watch_active;
    uint32_t npe_resource_check_calls;
    uint32_t npe_resource_check_returns;
    uint32_t npe_resource_check_caller;
    uint32_t npe_resource_check_return_from;
    uint32_t npe_resource_check_return_target;
    uint16_t npe_resource_check_entry_sp;
    uint16_t npe_resource_check_entry_post_sp;
    uint16_t npe_resource_check_entry_fp;
    uint16_t npe_resource_check_entry_error;
    uint16_t npe_resource_check_return_sp;
    uint16_t npe_resource_check_return_post_sp;
    uint16_t npe_resource_check_return_fp;
    uint16_t npe_resource_check_return_r0;
    uint16_t npe_resource_check_return_r1;
    uint16_t npe_resource_check_return_error;
    uint8_t npe_resource_check_stage;
    uint32_t npe_resource_check_child_calls[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint32_t npe_resource_check_child_returns[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint32_t npe_resource_check_child_call_from[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint32_t npe_resource_check_child_call_target[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_call_word[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_call_sp[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_call_post_sp[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_call_fp[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint32_t npe_resource_check_child_return_from[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint32_t npe_resource_check_child_return_target[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_return_word[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_return_sp[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_return_post_sp[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_return_fp[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_return_r0[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_return_r1[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    uint16_t npe_resource_check_child_return_error[
        DMCU_NPE_RESOURCE_CHECK_CHILD_SLOTS];
    bool npe_resource_check_error_first_write_valid;
    bool npe_resource_check_error_first_nonzero_valid;
    uint32_t npe_resource_check_error_first_write_pc;
    uint32_t npe_resource_check_error_first_write_address;
    uint16_t npe_resource_check_error_first_write_old;
    uint16_t npe_resource_check_error_first_write_new;
    uint16_t npe_resource_check_error_first_write_word_old;
    uint16_t npe_resource_check_error_first_write_word_new;
    uint16_t npe_resource_check_error_first_write_sp;
    uint16_t npe_resource_check_error_first_write_fp;
    uint8_t npe_resource_check_error_first_write_bits;
    uint8_t npe_resource_check_error_first_write_stage;
    uint32_t npe_resource_check_error_first_nonzero_pc;
    uint32_t npe_resource_check_error_first_nonzero_address;
    uint16_t npe_resource_check_error_first_nonzero_old;
    uint16_t npe_resource_check_error_first_nonzero_new;
    uint16_t npe_resource_check_error_first_nonzero_word_old;
    uint16_t npe_resource_check_error_first_nonzero_word_new;
    uint16_t npe_resource_check_error_first_nonzero_sp;
    uint16_t npe_resource_check_error_first_nonzero_fp;
    uint8_t npe_resource_check_error_first_nonzero_bits;
    uint8_t npe_resource_check_error_first_nonzero_stage;
    uint64_t npe_resource_check_error_write_sequence;
    uint64_t npe_resource_check_error_write_event[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint32_t npe_resource_check_error_write_pc[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint32_t npe_resource_check_error_write_address[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint16_t npe_resource_check_error_write_word_old[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint16_t npe_resource_check_error_write_word_new[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint16_t npe_resource_check_error_write_r0[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint16_t npe_resource_check_error_write_r1[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint16_t npe_resource_check_error_write_sp[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint16_t npe_resource_check_error_write_fp[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint8_t npe_resource_check_error_write_bits[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint8_t npe_resource_check_error_write_stage[
        DMCU_NPE_RESOURCE_ERROR_WRITE_TRACE_SLOTS];
    uint32_t application_compare_ret_count[
        DMCU_APPLICATION_COMPARE_RET_SITES];
    uint32_t application_compare_ret_target[
        DMCU_APPLICATION_COMPARE_RET_SITES];
    uint16_t application_compare_ret_word[
        DMCU_APPLICATION_COMPARE_RET_SITES];
    uint16_t application_compare_ret_sp[
        DMCU_APPLICATION_COMPARE_RET_SITES];
    uint16_t application_compare_ret_post_sp[
        DMCU_APPLICATION_COMPARE_RET_SITES];
    uint16_t application_compare_ret_fp[
        DMCU_APPLICATION_COMPARE_RET_SITES];
    uint32_t application_compare_ret_zero_target_count;
    uint32_t application_compare_ret_first_zero_from;
    uint32_t application_compare_ret_first_zero_target;
    uint16_t application_compare_ret_first_zero_sp;
    uint16_t application_compare_ret_first_zero_post_sp;
    uint16_t application_compare_ret_first_zero_fp;
    uint32_t npe_render_object_context_trampoline_entries;
    uint32_t npe_render_object_context_trampoline_from;
    uint16_t npe_render_object_context_trampoline_word;
    uint16_t npe_render_object_context_trampoline_sp;
    uint16_t npe_render_object_context_trampoline_fp;
    uint16_t npe_render_object_context_trampoline_r0;
    uint32_t npe_render_object_compositor_entries;
    uint32_t npe_render_object_compositor_entry_from;
    uint16_t npe_render_object_compositor_entry_word;
    uint16_t npe_render_object_compositor_entry_sp;
    uint16_t npe_render_object_compositor_entry_fp;
    uint32_t npe_render_object_compositor_child_calls;
    uint32_t npe_render_object_compositor_child_from;
    uint16_t npe_render_object_compositor_child_word;
    uint16_t npe_render_object_compositor_child_sp;
    uint16_t npe_render_object_compositor_child_fp;
    uint32_t npe_render_object_compositor_resident_returns;
    uint32_t npe_render_object_compositor_resident_return_from;
    uint16_t npe_render_object_compositor_resident_return_word;
    uint16_t npe_render_object_compositor_resident_return_sp;
    uint16_t npe_render_object_compositor_resident_return_fp;
    uint32_t npe_render_object_compositor_source_entries;
    uint32_t npe_render_object_compositor_source_entry_from;
    uint32_t npe_render_object_compositor_source_entry_target;
    uint16_t npe_render_object_compositor_source_entry_word;
    uint16_t npe_render_object_compositor_source_entry_sp;
    uint16_t npe_render_object_compositor_source_entry_fp;
    uint16_t npe_render_object_compositor_source_entry_r0;
    uint16_t npe_render_object_compositor_source_entry_stack[
        DMCU_NPE_RENDER_OBJECT_STACK_WORDS];
    uint32_t npe_render_object_caller;
    uint32_t npe_render_object_return_from;
    uint32_t npe_render_object_return_target;
    uint16_t npe_render_object_entry_sp;
    uint16_t npe_render_object_entry_fp;
    uint16_t npe_render_object_return_sp;
    uint16_t npe_render_object_return_fp;
    uint16_t npe_render_object_arg_hi;
    uint16_t npe_render_object_arg_lo;
    uint8_t npe_render_object_initial[DMCU_NPE_RENDER_OBJECT_BYTES];
    uint8_t npe_render_object_before[DMCU_NPE_RENDER_OBJECT_BYTES];
    uint8_t npe_render_object_after[DMCU_NPE_RENDER_OBJECT_BYTES];
    uint32_t npe_render_object_branch_count[2];
    uint32_t npe_render_object_branch_from[2];
    uint32_t npe_render_object_branch_target[2];
    uint16_t npe_render_object_branch_psw[2];
    uint16_t npe_render_object_branch_r0[2];
    uint32_t npe_render_object_layout_calls;
    uint32_t npe_render_object_helper_tail_calls;
    uint64_t npe_render_object_write_sequence;
    uint64_t npe_render_object_write_event[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    uint32_t npe_render_object_write_pc[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    uint16_t npe_render_object_write_address[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    uint16_t npe_render_object_write_old[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    uint16_t npe_render_object_write_new[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    uint16_t npe_render_object_write_sp[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    uint16_t npe_render_object_write_fp[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    uint8_t npe_render_object_write_bits[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    uint8_t npe_render_object_write_bus[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    uint8_t npe_render_object_write_in_interrupt[
        DMCU_NPE_RENDER_OBJECT_WRITE_TRACE_SLOTS];
    bool npe_materialize_watch_active;
    bool npe_materialize_count_inputs_valid;
    bool npe_materialize_total_valid;
    uint32_t npe_materialize_calls;
    uint32_t npe_materialize_returns;
    uint16_t npe_materialize_entry_sp;
    uint16_t npe_materialize_entry_fp;
    uint16_t npe_materialize_arg_path_hi;
    uint16_t npe_materialize_arg_path_lo;
    uint16_t npe_materialize_arg_mode;
    uint16_t npe_materialize_frame_fp;
    uint16_t npe_materialize_return_r0;
    uint16_t npe_materialize_return_r1;
    uint16_t npe_materialize_count_inputs[3];
    uint16_t npe_materialize_total_hi;
    uint16_t npe_materialize_total_lo;
    uint8_t npe_materialize_path[DMCU_NPE_MATERIALIZE_PATH_BYTES];
    uint8_t npe_materialize_local_pattern[
        DMCU_NPE_MATERIALIZE_PATH_BYTES];
    uint32_t npe_materialize_trace_count;
    uint8_t npe_materialize_trace_stage[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint32_t npe_materialize_trace_from[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint32_t npe_materialize_trace_target[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint16_t npe_materialize_trace_sp[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint16_t npe_materialize_trace_fp[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint16_t npe_materialize_trace_r0[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint16_t npe_materialize_trace_r1[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint16_t npe_materialize_trace_first_status[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint16_t npe_materialize_trace_next_status[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint16_t npe_materialize_trace_accumulator_hi[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint16_t npe_materialize_trace_accumulator_lo[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS];
    uint8_t npe_materialize_trace_record[
        DMCU_NPE_MATERIALIZE_TRACE_SLOTS]
        [DMCU_NPE_MATERIALIZE_RECORD_BYTES];
    uint32_t result_scanner_calls;
    uint32_t result_scanner_returns;
    uint32_t result_scanner_trace_count;
    bool result_scanner_trace_active;
    uint16_t result_scanner_frame_fp;
    uint32_t result_scanner_trace_from[DMCU_RESULT_SCANNER_TRACE_SLOTS];
    uint32_t result_scanner_trace_target[DMCU_RESULT_SCANNER_TRACE_SLOTS];
    uint16_t result_scanner_trace_word[DMCU_RESULT_SCANNER_TRACE_SLOTS];
    uint16_t result_scanner_trace_pre_sp[DMCU_RESULT_SCANNER_TRACE_SLOTS];
    uint16_t result_scanner_trace_post_sp[DMCU_RESULT_SCANNER_TRACE_SLOTS];
    uint16_t result_scanner_trace_fp[DMCU_RESULT_SCANNER_TRACE_SLOTS];
    uint16_t result_scanner_trace_r0[DMCU_RESULT_SCANNER_TRACE_SLOTS];
    uint16_t result_scanner_trace_r1[DMCU_RESULT_SCANNER_TRACE_SLOTS];
    bool result_scanner_trace_locals_valid[
        DMCU_RESULT_SCANNER_TRACE_SLOTS];
    uint16_t result_scanner_trace_locals[DMCU_RESULT_SCANNER_TRACE_SLOTS]
        [DMCU_RESULT_SCANNER_LOCAL_WORDS];
    /* Read-only, first-call probe for the exact 31:9E18 list creator used by
     * the restored result scanner.  This separates an argument/frame or CPU
     * condition-code fault from a failure in the child allocator without
     * changing guest-visible state. */
    uint32_t result_list_create_calls;
    bool result_list_create_trace_active;
    uint32_t result_list_create_caller;
    uint16_t result_list_create_entry_sp;
    uint16_t result_list_create_entry_post_sp;
    uint16_t result_list_create_entry_fp;
    uint16_t result_list_create_entry_arg;
    uint16_t result_list_create_link_sp;
    uint16_t result_list_create_link_old_fp;
    uint16_t result_list_create_frame_fp;
    uint16_t result_list_create_frame_arg_word;
    uint16_t result_list_create_frame_arg_byte;
    uint16_t result_list_create_compare_r0;
    uint16_t result_list_create_compare_psw;
    uint32_t result_list_create_compare_target;
    uint32_t result_list_create_allocator_calls;
    uint32_t result_list_create_returns;
    uint32_t result_list_create_return_target;
    uint16_t result_list_create_return_sp;
    uint16_t result_list_create_return_post_sp;
    uint16_t result_list_create_return_fp;
    uint16_t result_list_create_return_r0;
    uint16_t result_list_create_return_r1;
    /* Read-only snapshots on both sides of each initial browser allocator
     * return/compare/branch sequence.  Slots are tied to the four static
     * call sites, not to timing or invocation order. */
    uint32_t operation_browser_alloc_returns;
    uint32_t operation_browser_alloc_decisions;
    uint32_t operation_browser_alloc_return_from[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint32_t operation_browser_alloc_return_target[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_return_sp[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_return_post_sp[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_return_fp[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_return_r0[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_return_r1[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_return_psw[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint8_t operation_browser_alloc_return_in_interrupt[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint32_t operation_browser_alloc_decision_from[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint32_t operation_browser_alloc_decision_sequential[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint32_t operation_browser_alloc_decision_target[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_decision_sp[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_decision_post_sp[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_decision_fp[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_decision_r0[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_decision_r1[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint16_t operation_browser_alloc_decision_psw[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint8_t operation_browser_alloc_decision_in_interrupt[
        DMCU_OPERATION_BROWSER_ALLOC_SLOTS];
    uint64_t operation_ui_data_write_count[
        DMCU_OPERATION_UI_DATA_RANGES];
    uint64_t operation_ui_data_change_count[
        DMCU_OPERATION_UI_DATA_RANGES];
    uint64_t operation_ui_data_trace_sequence;
    uint64_t operation_ui_data_trace_event[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint32_t operation_ui_data_trace_pc[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint32_t operation_ui_data_trace_address[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint16_t operation_ui_data_trace_logical[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint16_t operation_ui_data_trace_old[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint16_t operation_ui_data_trace_new[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint16_t operation_ui_data_trace_sp[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint16_t operation_ui_data_trace_fp[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint16_t operation_ui_data_trace_ds0[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint16_t operation_ui_data_trace_ds1[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint16_t operation_ui_data_trace_gpr[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS][4];
    uint8_t operation_ui_data_trace_bits[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint8_t operation_ui_data_trace_range[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint8_t operation_ui_data_trace_in_interrupt[
        DMCU_OPERATION_UI_DATA_WRITE_TRACE_SLOTS];
    uint32_t application_trace_calls[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_from[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_sp[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_r0[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_r1[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_r2[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_args[DMCU_APPLICATION_TRACE_ENTRIES][4];
    /* Read-only trace of the foreground entry selected by the resident
     * manager.  This is deliberately separate from APPLICATION_TRACE so a
     * new reverse-engineering probe does not renumber that stable table. */
    uint32_t foreground_main_entries;
    uint32_t foreground_main_entry_from;
    uint16_t foreground_main_entry_word;
    uint16_t foreground_main_entry_pre_sp;
    uint16_t foreground_main_entry_post_sp;
    uint16_t foreground_main_entry_fp;
    uint16_t foreground_main_entry_frame[3];
    uint32_t foreground_mode_selects;
    uint32_t foreground_mode_select_from;
    uint32_t foreground_mode_select_target;
    uint16_t foreground_mode_select_word;
    uint16_t foreground_mode_select_mode;
    uint16_t foreground_mode_select_event;
    uint16_t foreground_mode_select_pre_sp;
    uint16_t foreground_mode_select_post_sp;
    uint16_t foreground_mode_select_fp;
    uint32_t foreground_main_returns;
    uint32_t foreground_main_return_from;
    uint32_t foreground_main_return_target;
    uint16_t foreground_main_return_word;
    uint16_t foreground_main_return_result;
    uint16_t foreground_main_return_pre_sp;
    uint16_t foreground_main_return_post_sp;
    uint16_t foreground_main_return_fp;
    /* The operation-context owner deliberately consumes the foreground
     * result before returning to its parent.  Keep both returns observable
     * so a value used only inside guest code is not mistaken for the
     * resident manager's public result. */
    uint32_t foreground_context_returns;
    uint32_t foreground_context_return_from;
    uint32_t foreground_context_return_target;
    uint16_t foreground_context_return_word;
    uint16_t foreground_context_return_result;
    uint16_t foreground_context_return_selector;
    uint16_t foreground_context_return_state;
    uint16_t foreground_context_return_resource;
    uint16_t foreground_context_return_pending;
    uint16_t foreground_context_return_stage;
    uint16_t foreground_context_return_pre_sp;
    uint16_t foreground_context_return_post_sp;
    uint16_t foreground_context_return_fp;
    uint32_t foreground_owner_returns;
    uint32_t foreground_owner_return_from;
    uint32_t foreground_owner_return_target;
    uint16_t foreground_owner_return_word;
    uint16_t foreground_owner_return_result;
    uint16_t foreground_owner_return_selector;
    uint16_t foreground_owner_return_state;
    uint16_t foreground_owner_return_resource;
    uint16_t foreground_owner_return_pending;
    uint16_t foreground_owner_return_stage;
    uint16_t foreground_owner_return_pre_sp;
    uint16_t foreground_owner_return_post_sp;
    uint16_t foreground_owner_return_fp;
    uint32_t root_exit_state_trace_count;
    uint32_t root_exit_state_trace_pc[DMCU_ROOT_EXIT_STATE_TRACE_SLOTS];
    uint16_t root_exit_state_trace_old[DMCU_ROOT_EXIT_STATE_TRACE_SLOTS];
    uint16_t root_exit_state_trace_new[DMCU_ROOT_EXIT_STATE_TRACE_SLOTS];
    uint8_t root_exit_state_trace_bits[DMCU_ROOT_EXIT_STATE_TRACE_SLOTS];
    uint32_t resident16_prefix_entries;
    uint32_t resident16_prefix_entry_from;
    uint32_t resident16_prefix_entry_target;
    uint16_t resident16_prefix_entry_word;
    uint16_t resident16_prefix_entry_pre_sp;
    uint16_t resident16_prefix_entry_post_sp;
    uint16_t resident16_prefix_entry_fp;
    uint32_t resident16_prefix_exits;
    uint32_t resident16_prefix_exit_from;
    uint32_t resident16_prefix_exit_target;
    uint16_t resident16_prefix_exit_word;
    uint16_t resident16_prefix_exit_pre_sp;
    uint16_t resident16_prefix_exit_post_sp;
    uint16_t resident16_prefix_exit_fp;
    uint32_t resident16_return_trace_count;
    uint32_t resident16_return_trace_pc[DMCU_RESIDENT16_RETURN_TRACE_SLOTS];
    uint16_t resident16_return_trace_address[
        DMCU_RESIDENT16_RETURN_TRACE_SLOTS];
    uint16_t resident16_return_trace_old[DMCU_RESIDENT16_RETURN_TRACE_SLOTS];
    uint16_t resident16_return_trace_new[DMCU_RESIDENT16_RETURN_TRACE_SLOTS];
    uint16_t resident16_return_trace_sp[DMCU_RESIDENT16_RETURN_TRACE_SLOTS];
    uint16_t resident16_return_trace_fp[DMCU_RESIDENT16_RETURN_TRACE_SLOTS];
    uint8_t resident16_return_trace_bits[DMCU_RESIDENT16_RETURN_TRACE_SLOTS];
    uint8_t resident16_return_trace_in_irq[
        DMCU_RESIDENT16_RETURN_TRACE_SLOTS];
    uint32_t root_loop_compare_count;
    uint16_t root_loop_compare_index;
    uint16_t root_loop_compare_limit;
    uint16_t root_loop_compare_psw;
    uint32_t root_loop_compare_next;
    uint16_t root_loop_compare_fp;
    uint32_t root_loop_local_object;
    uint16_t root_loop_local_count;
    uint16_t root_loop_frame_words[4];
    bool root_object_slot_watch_active;
    bool root_object_slot_first_bad_valid;
    uint16_t root_object_slot_watch_address;
    uint16_t root_object_slot_expected;
    uint32_t root_object_slot_writes;
    uint32_t root_object_slot_first_bad_pc;
    uint16_t root_object_slot_first_bad_old;
    uint16_t root_object_slot_first_bad_new;
    uint16_t root_object_slot_first_bad_sp;
    uint16_t root_object_slot_first_bad_fp;
    uint8_t root_object_slot_first_bad_bits;
    uint8_t root_object_slot_first_bad_bus;
    bool root_object_slot_first_bad_in_irq;
    uint32_t root_object_data_write_count;
    uint32_t root_object_data_trace_pc[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint32_t root_object_data_trace_physical[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint16_t root_object_data_trace_logical[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint16_t root_object_data_trace_old[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint16_t root_object_data_trace_new[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint16_t root_object_data_trace_sp[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint16_t root_object_data_trace_fp[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint16_t root_object_data_trace_ds0[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint16_t root_object_data_trace_ds1[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint16_t root_object_data_trace_gpr[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS][7];
    uint8_t root_object_data_trace_bits[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    bool root_object_data_trace_in_irq[DMCU_ROOT_OBJECT_DATA_TRACE_SLOTS];
    uint32_t menu_path_write_count;
    uint32_t menu_path_write_pc[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint32_t menu_path_write_physical[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint16_t menu_path_write_logical[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint16_t menu_path_write_old[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint16_t menu_path_write_new[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint16_t menu_path_write_sp[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint16_t menu_path_write_fp[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint16_t menu_path_write_ds0[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint16_t menu_path_write_ds1[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint16_t menu_path_write_gpr[DMCU_MENU_PATH_WRITE_TRACE_SLOTS][4];
    uint8_t menu_path_write_bits[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    bool menu_path_write_in_irq[DMCU_MENU_PATH_WRITE_TRACE_SLOTS];
    uint32_t root_render_flag_trace_count;
    uint32_t root_render_flag_trace_pc[DMCU_ROOT_RENDER_FLAG_TRACE_SLOTS];
    uint32_t root_render_flag_trace_source[DMCU_ROOT_RENDER_FLAG_TRACE_SLOTS];
    uint16_t root_render_flag_trace_logical[DMCU_ROOT_RENDER_FLAG_TRACE_SLOTS];
    uint16_t root_render_flag_trace_item[DMCU_ROOT_RENDER_FLAG_TRACE_SLOTS];
    uint16_t root_render_flag_trace_value[DMCU_ROOT_RENDER_FLAG_TRACE_SLOTS];
    uint16_t root_render_flag_trace_ds0[DMCU_ROOT_RENDER_FLAG_TRACE_SLOTS];
    uint16_t root_render_flag_trace_ds1[DMCU_ROOT_RENDER_FLAG_TRACE_SLOTS];
    uint32_t root_loop_body_count;
    uint32_t root_loop_object;
    uint16_t root_loop_event;
    uint32_t root_bitmap_blit_calls;
    uint32_t root_bitmap_blit_returns;
    uint32_t root_bitmap_blit_from;
    uint32_t root_bitmap_blit_return_to;
    uint16_t root_bitmap_blit_sp;
    uint16_t root_bitmap_blit_fp;
    uint16_t root_bitmap_blit_ds0;
    uint16_t root_bitmap_blit_ds1;
    uint16_t root_bitmap_blit_args[6];
    uint16_t root_bitmap_blit_result[2];
    uint32_t root_bitmap_resource_calls;
    uint32_t root_bitmap_resource_returns;
    uint32_t root_bitmap_resource_from[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS];
    uint32_t root_bitmap_resource_next[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS];
    uint16_t root_bitmap_resource_sp[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS];
    uint16_t root_bitmap_resource_fp[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS];
    uint16_t root_bitmap_resource_args[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS][4];
    uint16_t root_bitmap_resource_gate[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS];
    uint16_t root_bitmap_resource_r0[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS];
    uint16_t root_bitmap_resource_r1[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS];
    uint16_t root_bitmap_resource_locals[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS][5];
    uint32_t root_bitmap_resource_byte_physical[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS][4];
    uint16_t root_bitmap_resource_byte_logical[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS][4];
    uint16_t root_bitmap_resource_byte_ds[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS][4];
    uint8_t root_bitmap_resource_byte_value[DMCU_ROOT_BITMAP_RESOURCE_TRACE_SLOTS][4];
    uint32_t root_bitmap_source_writes;
    uint32_t root_bitmap_source_first_pc;
    uint32_t root_bitmap_source_first_physical;
    uint16_t root_bitmap_source_first_logical;
    uint16_t root_bitmap_source_first_old;
    uint16_t root_bitmap_source_first_new;
    uint16_t root_bitmap_source_first_ds0;
    uint16_t root_bitmap_source_first_ds1;
    uint8_t root_bitmap_source_first_bits;
    uint32_t root_bitmap_source_last_pc;
    uint32_t root_bitmap_source_last_physical;
    uint16_t root_bitmap_source_last_logical;
    uint16_t root_bitmap_source_last_old;
    uint16_t root_bitmap_source_last_new;
    uint16_t root_bitmap_source_last_ds0;
    uint16_t root_bitmap_source_last_ds1;
    uint8_t root_bitmap_source_last_bits;
    uint32_t root_bitmap_header_write_count[6];
    uint32_t root_bitmap_header_first_nonzero_pc[6];
    uint8_t root_bitmap_header_first_nonzero_value[6];
    uint32_t root_bitmap_header_last_pc[6];
    uint16_t root_bitmap_header_last_logical[6];
    uint16_t root_bitmap_header_last_value[6];
    uint8_t root_bitmap_header_last_bits[6];
    uint32_t root_bitmap_header_copy_calls;
    uint32_t root_bitmap_header_copy_from;
    uint16_t root_bitmap_header_copy_args[5];
    uint32_t root_bitmap_transfer_calls;
    uint32_t root_bitmap_transfer_from;
    uint16_t root_bitmap_transfer_args[5];
    bool file_size_record_snapshot_valid;
    uint32_t file_size_record_snapshot_base;
    uint8_t file_size_record_snapshot_attr;
    uint16_t file_size_record_snapshot_length_hi;
    uint16_t file_size_record_snapshot_length_lo;
    uint8_t file_size_record_snapshot_data[0x40];
    uint32_t file_write_calls;
    uint32_t file_write_caller;
    uint16_t file_write_sp;
    uint32_t file_write_file;
    uint32_t file_write_buffer;
    uint32_t file_write_length;
    uint32_t file_write_sample_bytes;
    uint32_t file_write_sample_non_ff;
    uint32_t file_write_sample_fnv1a;
    uint8_t file_write_sample[0x40];
    bool file_write_watch_active;
    uint16_t file_write_stage;
    uint16_t file_write_last_child;
    uint32_t file_write_child_calls;
    uint32_t file_write_child_returns;
    uint32_t file_write_last_from;
    uint32_t file_write_last_target;
    uint16_t file_write_last_sp;
    uint16_t file_write_last_fp;
    uint16_t file_write_last_r0;
    uint16_t file_write_last_r1;
    uint16_t file_write_last_r2;
    uint16_t file_write_last_r3;
    uint32_t file_write_returns;
    uint16_t file_write_result_hi;
    uint16_t file_write_result_lo;
    uint32_t file_write_return_trace_sequence[DMCU_FILE_WRITE_RETURN_TRACE_SLOTS];
    uint16_t file_write_return_trace_hi[DMCU_FILE_WRITE_RETURN_TRACE_SLOTS];
    uint16_t file_write_return_trace_lo[DMCU_FILE_WRITE_RETURN_TRACE_SLOTS];
    uint32_t file_write_nonfull_returns;
    uint32_t file_write_first_nonfull_sequence;
    uint16_t file_write_first_nonfull_hi;
    uint16_t file_write_first_nonfull_lo;
    uint32_t provision_calls;
    uint32_t provision_caller;
    uint16_t provision_sp;
    uint16_t provision_stage;
    uint16_t provision_open_hi;
    uint16_t provision_open_lo;
    uint16_t provision_result_hi;
    uint16_t provision_result_lo;
    uint16_t provision_open_stage;
    uint32_t provision_child_call_mask;
    uint32_t provision_child_return_mask;
    uint16_t provision_child_result_hi[17];
    uint16_t provision_child_result_lo[17];
    uint16_t provision_child_error[17];
    uint32_t provision_error_writes;
    uint32_t provision_error_first_pc;
    uint32_t provision_error_last_pc;
    uint16_t provision_error_first_old;
    uint16_t provision_error_first_value;
    uint16_t provision_error_last_old;
    uint16_t provision_error_last_value;
    uint16_t provision_path_result;
    uint16_t provision_path_final_result;
    uint16_t provision_path_failure_pc;
    uint16_t provision_path_input_hi;
    uint16_t provision_path_input_lo;
    uint16_t provision_path_remaining_hi;
    uint16_t provision_path_remaining_lo;
    uint16_t provision_path_selector;
    uint16_t provision_path_attribute;
    uint16_t provision_path_child_hi;
    uint16_t provision_path_child_lo;
    uint8_t provision_path_remaining_char;
    uint8_t provision_path_remaining[24];
    uint8_t provision_path_object[72];
    uint32_t provision_lookup_veneer_calls;
    uint16_t provision_lookup_selector;
    uint32_t provision_lookup_branch_target;
    uint32_t provision_lookup_object;
    uint8_t provision_lookup_mode_at_call;
    uint16_t provision_lookup_result;
    uint32_t pim_header_snapshots;
    uint32_t pim_current_caller;
    uint32_t pim_trace_caller[DMCU_PIM_TRACE_SLOTS];
    uint16_t pim_trace_fp[DMCU_PIM_TRACE_SLOTS];
    uint8_t pim_trace_category[DMCU_PIM_TRACE_SLOTS];
    uint8_t pim_trace_mode[DMCU_PIM_TRACE_SLOTS];
    uint8_t pim_trace_path[DMCU_PIM_TRACE_SLOTS][32];
    uint16_t pim_header_fp;
    uint8_t pim_header_category;
    uint8_t pim_header_mode;
    uint8_t pim_header[0x40];
    uint8_t pim_header_path[0x30];
    uint32_t file_open_calls;
    bool file_open_watch_active;
    bool file_open_provision_seen;
    bool file_open_args_captured;
    uint32_t file_open_caller;
    uint16_t file_open_sp;
    uint16_t file_open_fp;
    uint16_t file_open_stage;
    uint16_t file_open_mode;
    uint16_t file_open_path_hi;
    uint16_t file_open_path_lo;
    uint16_t file_open_f01a;
    uint16_t file_open_error;
    uint32_t file_open_last_from;
    uint32_t file_open_last_target;
    uint16_t file_open_last_sp;
    uint16_t file_open_last_fp;
    uint16_t file_open_last_r0;
    uint16_t file_open_last_r1;
    uint16_t file_open_last_r2;
    uint16_t file_open_last_r3;
    uint32_t file_open_child_calls;
    uint32_t file_open_child_returns;
    uint32_t file_open_child_call_mask;
    uint32_t file_open_child_return_mask;
    uint16_t file_open_child_result_hi[17];
    uint16_t file_open_child_result_lo[17];
    uint16_t file_open_child_error[17];
    uint32_t file_open_dynamic_calls;
    uint32_t file_open_dynamic_record;
    uint32_t file_open_dynamic_target;
    uint32_t file_open_dynamic_returns;
    uint16_t file_open_dynamic_result_hi;
    uint16_t file_open_dynamic_result_lo;
    uint16_t file_open_dynamic_error;
    uint32_t file_open_driver_wrapper_hits;
    uint16_t file_open_driver_wrapper_word;
    uint32_t file_open_driver_child_calls;
    uint32_t file_open_driver_child_returns;
    uint16_t file_open_driver_child_result_hi;
    uint16_t file_open_driver_child_result_lo;
    uint32_t file_open_driver_mirror_calls;
    uint32_t file_open_driver_mirror_returns;
    uint16_t file_open_driver_mirror_result;
    uint32_t file_open_driver_status_calls;
    uint32_t file_open_driver_status_returns;
    uint16_t file_open_driver_status_result;
    uint32_t file_open_returns;
    uint16_t file_open_result_hi;
    uint16_t file_open_result_lo;
    uint16_t file_open_patch_words[16];
    uint32_t file_open_error_writes;
    uint32_t file_open_error_first_pc;
    uint32_t file_open_error_last_pc;
    uint32_t file_open_error_last_physical;
    uint16_t file_open_error_first_old;
    uint16_t file_open_error_first_value;
    uint16_t file_open_error_last_old;
    uint16_t file_open_error_last_value;
    uint16_t file_open_error_last_logical;
    uint16_t file_open_error_last_bits;
    uint32_t file_open_error_trace_pc[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint32_t file_open_error_trace_physical[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_logical[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_old[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_new[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_sp[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_fp[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_stage[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_ds0[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_ds1[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_r0[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint16_t file_open_error_trace_r1[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint8_t file_open_error_trace_bits[DMCU_FILE_OPEN_ERROR_TRACE_SLOTS];
    uint8_t file_open_path[24];
    uint32_t file_open_nested_calls;
    uint16_t file_open_nested_active_slot;
    uint32_t file_open_nested_caller[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_open_nested_entry_sp[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_open_nested_fp[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_open_nested_mode[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_open_nested_path_hi[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_open_nested_path_lo[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_open_nested_result_hi[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_open_nested_result_lo[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_open_nested_error[DMCU_FILE_PATH_TRACE_SLOTS];
    uint32_t file_wrapper_calls;
    uint16_t file_wrapper_active_slot;
    uint32_t file_wrapper_caller[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_entry_sp[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_fp[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_path_hi[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_path_lo[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_flags[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_result_hi[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_result_lo[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_exit_sp[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_exit_fp[DMCU_FILE_PATH_TRACE_SLOTS];
    uint32_t file_wrapper_exit_target[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_wrapper_entry_stack[DMCU_FILE_PATH_TRACE_SLOTS]
                                     [DMCU_FILE_WRAPPER_STACK_WORDS];
    uint16_t file_wrapper_exit_stack[DMCU_FILE_PATH_TRACE_SLOTS]
                                    [DMCU_FILE_WRAPPER_STACK_WORDS];
    bool file_wrapper_frame_watch_active;
    uint16_t file_wrapper_frame_base;
    uint32_t file_wrapper_frame_writes;
    uint32_t file_wrapper_frame_write_pc[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint16_t file_wrapper_frame_write_logical[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint16_t file_wrapper_frame_write_backing[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint16_t file_wrapper_frame_write_old[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint16_t file_wrapper_frame_write_new[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint16_t file_wrapper_frame_write_sp[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint16_t file_wrapper_frame_write_fp[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint8_t file_wrapper_frame_write_bits[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint8_t file_wrapper_frame_write_source[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint8_t file_wrapper_frame_write_in_irq[
        DMCU_FILE_WRAPPER_WRITE_TRACE_SLOTS];
    uint32_t userinfo_path_writes;
    uint32_t userinfo_path_trace_pc[DMCU_USERINFO_PATH_TRACE_SLOTS];
    uint32_t userinfo_path_trace_address[DMCU_USERINFO_PATH_TRACE_SLOTS];
    uint16_t userinfo_path_trace_old[DMCU_USERINFO_PATH_TRACE_SLOTS];
    uint16_t userinfo_path_trace_new[DMCU_USERINFO_PATH_TRACE_SLOTS];
    uint16_t userinfo_path_trace_sp[DMCU_USERINFO_PATH_TRACE_SLOTS];
    uint16_t userinfo_path_trace_fp[DMCU_USERINFO_PATH_TRACE_SLOTS];
    uint16_t userinfo_path_trace_ds0[DMCU_USERINFO_PATH_TRACE_SLOTS];
    uint16_t userinfo_path_trace_ds1[DMCU_USERINFO_PATH_TRACE_SLOTS];
    uint8_t userinfo_path_trace_bits[DMCU_USERINFO_PATH_TRACE_SLOTS];
    /* Bounded, read-only milestones through the recovered USERINFO.SYS
     * validator and the resident close routine.  This turns the formerly
     * transient recursive-close failure into one compact Web snapshot. */
    uint64_t userinfo_flow_events;
    uint16_t userinfo_flow_depth;
    uint16_t userinfo_close_depth;
    uint16_t userinfo_flow_frame_fp[DMCU_USERINFO_CLOSE_STACK];
    uint16_t userinfo_close_handle_hi[DMCU_USERINFO_CLOSE_STACK];
    uint16_t userinfo_close_handle_lo[DMCU_USERINFO_CLOSE_STACK];
    uint8_t userinfo_flow_trace_event[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_depth[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_close_depth[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint32_t userinfo_flow_trace_from[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint32_t userinfo_flow_trace_target[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_sp[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_fp[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_r0[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_r1[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_r2[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_r3[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_valid[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_result[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_handle_hi[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_handle_lo[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint16_t userinfo_flow_trace_error[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint8_t userinfo_flow_trace_descriptor_14[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint8_t userinfo_flow_trace_descriptor_15[DMCU_USERINFO_FLOW_TRACE_SLOTS];
    uint32_t userinfo_state_calls;
    uint32_t userinfo_state_returns;
    uint32_t userinfo_state_last_from;
    uint32_t userinfo_state_last_target;
    uint16_t userinfo_state_code[DMCU_USERINFO_STATE_CODE_WORDS];
    uint32_t file_path_resolve_calls;
    uint16_t file_path_trace_active_slot;
    uint32_t file_path_trace_caller[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_path_trace_fp[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_path_trace_stage[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_path_trace_object_hi[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_path_trace_object_lo[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_path_trace_input_hi[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_path_trace_input_lo[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_path_trace_result[DMCU_FILE_PATH_TRACE_SLOTS];
    uint16_t file_path_trace_error[DMCU_FILE_PATH_TRACE_SLOTS];
    uint8_t file_path_trace_data[DMCU_FILE_PATH_TRACE_SLOTS]
                                [DMCU_FILE_PATH_TRACE_BYTES];
    bool file_path_primary_watch_active;
    uint32_t file_path_resolve_caller;
    uint16_t file_path_resolve_sp;
    uint16_t file_path_resolve_fp;
    uint16_t file_path_resolve_object_hi;
    uint16_t file_path_resolve_object_lo;
    uint16_t file_path_resolve_input_hi;
    uint16_t file_path_resolve_input_lo;
    uint16_t file_path_component_result_hi;
    uint16_t file_path_component_result_lo;
    uint16_t file_path_component_fp;
    bool file_component_watch_active;
    uint16_t file_component_entry_sp;
    uint16_t file_component_entry_fp;
    uint16_t file_component_exit_sp;
    uint16_t file_component_exit_fp;
    uint32_t file_component_entry_irq;
    uint32_t file_component_daac_irq;
    uint32_t file_component_rets_irq;
    uint32_t file_component_exit_irq;
    uint16_t file_component_arg_entry_hi;
    uint16_t file_component_arg_entry_lo;
    uint16_t file_component_output_hi;
    uint16_t file_component_output_lo;
    uint8_t file_component_output_after_fill[
        DMCU_FILE_RECORD_SELECTOR_BYTES];
    uint8_t file_component_output_after_return[
        DMCU_FILE_RECORD_SELECTOR_BYTES];
    uint16_t file_component_arg_daac_hi;
    uint16_t file_component_arg_daac_lo;
    uint16_t file_component_arg_rets_hi;
    uint16_t file_component_arg_rets_lo;
    uint16_t file_component_result_rets_hi;
    uint16_t file_component_result_rets_lo;
    uint16_t file_component_frame_entry[DMCU_FILE_COMPONENT_FRAME_WORDS];
    uint16_t file_component_frame_exit[DMCU_FILE_COMPONENT_FRAME_WORDS];
    uint32_t file_component_write_count;
    uint32_t file_component_write_pc[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint16_t file_component_write_logical[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint16_t file_component_write_backing[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint16_t file_component_write_old[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint16_t file_component_write_new[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint16_t file_component_write_sp[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint16_t file_component_write_fp[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint8_t file_component_write_bits[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint8_t file_component_write_source[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint8_t file_component_write_in_irq[DMCU_FILE_COMPONENT_WRITE_TRACE_SLOTS];
    uint16_t file_path_resolver_call_fp;
    uint16_t file_path_resolver_return_fp;
    uint16_t file_path_resolve_remaining_hi;
    uint16_t file_path_resolve_remaining_lo;
    uint16_t file_path_resolve_selector;
    uint16_t file_path_resolve_result;
    uint16_t file_path_resolve_failure_pc;
    uint16_t file_path_resolve_final_result;
    uint16_t file_path_resolve_child_hi;
    uint16_t file_path_resolve_child_lo;
    uint8_t file_path_resolve_attribute;
    uint8_t file_path_resolve_remaining_char;
    uint8_t file_path_resolve_input[24];
    uint8_t file_path_resolve_remaining[24];
    uint8_t file_path_resolve_object[0x48];
    uint64_t file_root_pool_calls;
    uint64_t file_root_pool_returns;
    uint64_t file_root_lifecycle_events;
    uint32_t file_root_current_open_caller;
    uint16_t file_root_current_open_sp;
    uint16_t file_root_current_open_fp;
    uint16_t file_root_current_open_mode;
    uint16_t file_root_current_open_path_hi;
    uint16_t file_root_current_open_path_lo;
    uint64_t file_root_pool_trace_event[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint32_t file_root_pool_trace_from[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint32_t file_root_pool_trace_open_caller[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint16_t file_root_pool_trace_open_sp[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint16_t file_root_pool_trace_open_fp[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint16_t file_root_pool_trace_open_mode[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint16_t file_root_pool_trace_open_path_hi[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint16_t file_root_pool_trace_open_path_lo[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint8_t file_root_pool_trace_open_path[DMCU_FILE_ROOT_POOL_TRACE_SLOTS]
                                          [DMCU_FILE_ROOT_PATH_BYTES];
    uint16_t file_root_pool_trace_head_hi[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint16_t file_root_pool_trace_head_lo[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint8_t file_root_pool_trace_length[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint8_t file_root_pool_trace_available[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint32_t file_root_pool_trace_node[DMCU_FILE_ROOT_POOL_TRACE_SLOTS]
                                      [DMCU_FILE_ROOT_POOL_NODES];
    uint32_t file_root_pool_trace_next[DMCU_FILE_ROOT_POOL_TRACE_SLOTS]
                                      [DMCU_FILE_ROOT_POOL_NODES];
    uint8_t file_root_pool_trace_flag[DMCU_FILE_ROOT_POOL_TRACE_SLOTS]
                                     [DMCU_FILE_ROOT_POOL_NODES];
    uint8_t file_root_pool_trace_sentinel[DMCU_FILE_ROOT_POOL_TRACE_SLOTS]
                                         [DMCU_FILE_ROOT_POOL_NODES];
    uint16_t file_root_pool_trace_result_hi[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint16_t file_root_pool_trace_result_lo[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint16_t file_root_pool_trace_error[DMCU_FILE_ROOT_POOL_TRACE_SLOTS];
    uint64_t file_root_release_calls;
    uint64_t file_root_release_trace_event[DMCU_FILE_ROOT_RELEASE_TRACE_SLOTS];
    uint32_t file_root_release_trace_caller[DMCU_FILE_ROOT_RELEASE_TRACE_SLOTS];
    uint32_t file_root_release_trace_object[DMCU_FILE_ROOT_RELEASE_TRACE_SLOTS];
    uint16_t file_root_release_trace_sp[DMCU_FILE_ROOT_RELEASE_TRACE_SLOTS];
    uint16_t file_root_release_trace_fp[DMCU_FILE_ROOT_RELEASE_TRACE_SLOTS];
    uint8_t file_root_release_trace_flag[DMCU_FILE_ROOT_RELEASE_TRACE_SLOTS];
    uint32_t file_root_pool_link_writes[DMCU_FILE_ROOT_POOL_NODES];
    uint32_t file_root_pool_link_last_pc[DMCU_FILE_ROOT_POOL_NODES];
    uint16_t file_root_pool_link_last_offset[DMCU_FILE_ROOT_POOL_NODES];
    uint16_t file_root_pool_link_last_old[DMCU_FILE_ROOT_POOL_NODES];
    uint16_t file_root_pool_link_last_value[DMCU_FILE_ROOT_POOL_NODES];
    uint8_t file_root_pool_link_last_bits[DMCU_FILE_ROOT_POOL_NODES];
    uint32_t file_root_pool_field_writes[DMCU_FILE_ROOT_POOL_NODES];
    uint32_t file_root_pool_field_last_pc[DMCU_FILE_ROOT_POOL_NODES];
    uint16_t file_root_pool_field_last_offset[DMCU_FILE_ROOT_POOL_NODES];
    uint16_t file_root_pool_field_last_old[DMCU_FILE_ROOT_POOL_NODES];
    uint16_t file_root_pool_field_last_value[DMCU_FILE_ROOT_POOL_NODES];
    uint8_t file_root_pool_field_last_bits[DMCU_FILE_ROOT_POOL_NODES];
    uint32_t file_commit_calls;
    bool file_commit_watch_active;
    uint16_t file_commit_stage;
    uint16_t file_commit_last_child;
    uint32_t file_commit_caller;
    uint32_t file_commit_file;
    uint32_t file_commit_record;
    uint32_t file_commit_last_from;
    uint32_t file_commit_last_target;
    uint16_t file_commit_last_sp;
    uint16_t file_commit_last_fp;
    uint16_t file_commit_last_r0;
    uint16_t file_commit_last_r1;
    uint16_t file_commit_last_r2;
    uint16_t file_commit_last_r3;
    uint32_t file_commit_child_calls;
    uint32_t file_commit_child_returns;
    uint32_t file_commit_child_call_mask;
    uint32_t file_commit_child_return_mask;
    uint16_t file_commit_child_result_hi[DMCU_FILE_COMMIT_CHILD_SLOTS];
    uint16_t file_commit_child_result_lo[DMCU_FILE_COMMIT_CHILD_SLOTS];
    uint16_t file_commit_child_error[DMCU_FILE_COMMIT_CHILD_SLOTS];
    uint32_t file_commit_error_writes;
    uint32_t file_commit_error_first_pc;
    uint32_t file_commit_error_last_pc;
    uint16_t file_commit_error_first_old;
    uint16_t file_commit_error_first_value;
    uint16_t file_commit_error_last_old;
    uint16_t file_commit_error_last_value;
    uint16_t file_commit_error_last_stage;
    uint32_t file_commit_status_calls;
    uint32_t file_commit_status_returns;
    uint32_t file_commit_select_calls;
    uint32_t file_commit_select_returns;
    uint32_t file_commit_apply_calls;
    uint32_t file_commit_apply_returns;
    uint32_t file_commit_pair_calls;
    uint32_t file_commit_pair_returns;
    uint32_t file_commit_driver_calls;
    uint32_t file_commit_driver_returns;
    uint32_t file_commit_callback_calls;
    uint32_t file_commit_callback_returns;
    uint32_t file_commit_returns;
    uint16_t file_commit_result_hi;
    uint16_t file_commit_result_lo;
    uint8_t file_commit_record_data[0x40];
    uint8_t file_commit_file_data[0x50];
    uint32_t storage_driver_calls;
    uint32_t storage_driver_caller;
    uint16_t storage_driver_argument;
    uint32_t storage_driver_first_record;
    uint16_t storage_driver_first_status;
    uint32_t storage_driver_callback1_calls;
    uint32_t storage_driver_callback1_target;
    uint16_t storage_driver_callback1_result_hi;
    uint16_t storage_driver_callback1_result_lo;
    uint32_t storage_driver_second_record;
    uint32_t storage_driver_callback2_calls;
    uint32_t storage_driver_callback2_target;
    uint16_t storage_driver_callback2_result_hi;
    uint16_t storage_driver_callback2_result_lo;
    uint32_t storage_driver_returns;
    uint32_t storage_driver_return_target;
    uint16_t storage_driver_result_hi;
    uint16_t storage_driver_result_lo;
    /* Read-only diagnostic gate armed by the exact relocated 5F:F928
     * storage probe.  It excludes all earlier boot-time page traffic so the
     * first subsequent transition into the relocated 5F:261C reader remains
     * visible in a bounded host log. */
    bool storage_probe_page_watch_active;
    uint32_t storage_probe_page_watch_count;
    uint32_t capacity_scan_calls;
    uint16_t capacity_scan_stage;
    uint32_t capacity_scan_last_from;
    uint32_t capacity_scan_last_target;
    uint16_t capacity_scan_last_sp;
    uint16_t capacity_scan_last_fp;
    uint16_t capacity_scan_last_r0;
    uint16_t capacity_scan_last_r1;
    uint16_t capacity_scan_last_r2;
    uint16_t capacity_scan_last_r3;
    uint32_t capacity_scan_returns;
    uint32_t registry_init_calls;
    uint16_t registry_init_stage;
    uint32_t registry_init_last_from;
    uint32_t registry_init_last_target;
    uint16_t registry_init_last_sp;
    uint16_t registry_init_last_fp;
    uint16_t registry_init_last_r0;
    uint16_t registry_init_last_r1;
    uint32_t registry_init_result_calls;
    uint32_t registry_init_result_returns;
    uint32_t registry_init_entry_calls;
    uint32_t registry_init_entry_returns;
    uint32_t registry_init_returns;
    uint32_t file_entry_build_calls;
    uint16_t file_entry_build_stage;
    uint32_t file_entry_build_last_from;
    uint32_t file_entry_build_last_target;
    uint16_t file_entry_build_last_sp;
    uint16_t file_entry_build_last_fp;
    uint16_t file_entry_build_record_hi;
    uint16_t file_entry_build_record_lo;
    uint16_t file_entry_build_last_child;
    uint32_t file_entry_build_child_calls;
    uint32_t file_entry_build_child_returns;
    uint32_t file_entry_build_returns;
    bool application_init_frame_watch_active;
    uint32_t application_init_frame_calls;
    uint32_t application_init_frame_caller;
    uint16_t application_init_frame_entry_sp;
    uint16_t application_init_frame_entry_fp;
    uint16_t application_init_frame_base;
    uint16_t application_init_frame_initial[3];
    uint32_t application_init_frame_writes;
    uint32_t application_init_frame_first_write_pc;
    uint32_t application_init_frame_first_write_address;
    uint16_t application_init_frame_first_write_old;
    uint16_t application_init_frame_first_write_new;
    uint16_t application_init_frame_first_write_sp;
    uint16_t application_init_frame_first_write_fp;
    uint8_t application_init_frame_first_write_bits;
    uint8_t application_init_frame_first_write_bus;
    uint8_t application_init_frame_first_write_in_interrupt;
    uint32_t application_init_frame_last_write_pc;
    uint32_t application_init_frame_last_write_address;
    uint16_t application_init_frame_last_write_old;
    uint16_t application_init_frame_last_write_new;
    uint16_t application_init_frame_last_write_sp;
    uint16_t application_init_frame_last_write_fp;
    uint8_t application_init_frame_last_write_bits;
    uint8_t application_init_frame_last_write_bus;
    uint8_t application_init_frame_last_write_in_interrupt;
    uint32_t application_init_frame_child_calls;
    uint32_t application_init_frame_child_returns;
    uint32_t application_init_frame_child_last_from;
    uint16_t application_init_frame_child_call_sp;
    uint16_t application_init_frame_child_call_fp;
    uint16_t application_init_frame_child_return_sp;
    uint16_t application_init_frame_child_return_fp;
    uint16_t application_init_frame_child_return_words[3];
    uint32_t application_init_frame_unlinks;
    uint16_t application_init_frame_unlink_words[3];
    uint16_t application_init_frame_restored_fp;
    uint16_t application_init_frame_unlink_sp;
    uint32_t application_init_frame_exits;
    uint32_t application_init_frame_exit_to;
    uint16_t application_init_frame_exit_sp;
    uint16_t application_init_frame_exit_fp;
    uint32_t file_record_resolve_calls;
    uint32_t file_record_resolve_caller;
    uint16_t file_record_resolve_call_sp;
    uint32_t file_record_resolve_output;
    uint32_t file_record_resolve_selector;
    uint32_t file_record_resolve_current_output;
    uint32_t file_record_resolve_current_selector;
    uint32_t file_record_candidate_returns;
    uint32_t file_record_candidate_pointer;
    uint8_t file_record_candidate_data[0x40];
    uint32_t file_record_candidate_pointer_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint32_t file_record_candidate_call_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint32_t file_record_candidate_output_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint32_t file_record_candidate_selector_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint16_t file_record_candidate_cursor_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint16_t file_record_candidate_limit_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint16_t file_record_candidate_span_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint16_t file_record_candidate_active_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint16_t file_record_candidate_compare_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint8_t file_record_candidate_compare_valid[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS];
    uint8_t file_record_candidate_data_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS][0x40];
    uint8_t file_record_candidate_selector_data_trace[
        DMCU_FILE_RECORD_CANDIDATE_TRACE_SLOTS]
        [DMCU_FILE_RECORD_SELECTOR_BYTES];
    uint32_t file_record_resolve_loops;
    uint32_t file_record_resolve_returns;
    uint16_t file_record_resolve_result;
    uint8_t file_record_resolve_mode;
    uint16_t file_record_resolve_cursor;
    uint16_t file_record_resolve_limit;
    uint16_t file_record_resolve_span;
    uint16_t file_record_resolve_active;
    uint64_t root_metadata_trace_count;
    uint32_t root_metadata_trace_pc[DMCU_ROOT_METADATA_TRACE_SLOTS];
    uint32_t root_metadata_trace_address[DMCU_ROOT_METADATA_TRACE_SLOTS];
    uint16_t root_metadata_trace_old[DMCU_ROOT_METADATA_TRACE_SLOTS];
    uint16_t root_metadata_trace_new[DMCU_ROOT_METADATA_TRACE_SLOTS];
    uint16_t root_metadata_trace_sp[DMCU_ROOT_METADATA_TRACE_SLOTS];
    uint16_t root_metadata_trace_fp[DMCU_ROOT_METADATA_TRACE_SLOTS];
    uint8_t root_metadata_trace_bits[DMCU_ROOT_METADATA_TRACE_SLOTS];
    uint32_t root_object_init_calls;
    uint32_t root_object_init_returns;
    uint32_t root_object_init_from[DMCU_ROOT_OBJECT_INIT_TRACE_SLOTS];
    uint16_t root_object_init_sp[DMCU_ROOT_OBJECT_INIT_TRACE_SLOTS];
    uint16_t root_object_init_fp[DMCU_ROOT_OBJECT_INIT_TRACE_SLOTS];
    uint16_t root_object_init_gpr[DMCU_ROOT_OBJECT_INIT_TRACE_SLOTS][4];
    uint16_t root_object_init_stack[DMCU_ROOT_OBJECT_INIT_TRACE_SLOTS]
                                   [DMCU_ROOT_OBJECT_INIT_STACK_WORDS];
    uint16_t root_object_init_result[DMCU_ROOT_OBJECT_INIT_TRACE_SLOTS][2];
    uint32_t root_object_failures;
    uint32_t root_object_fail_from;
    uint16_t root_object_fail_sp;
    uint16_t root_object_fail_fp;
    uint16_t root_object_fail_gpr[DMCU_ROOT_OBJECT_FAIL_GPRS];
    uint16_t root_object_fail_locals[DMCU_ROOT_OBJECT_FAIL_LOCALS];
    uint16_t root_object_fail_words[DMCU_ROOT_OBJECT_FAIL_WORDS];
    uint32_t storage_lookup_trace_count;
    uint16_t storage_lookup_stage[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_unit[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_lba_hi[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_lba_lo[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_position_result[DMCU_STORAGE_LOOKUP_TRACE_SLOTS][2];
    uint16_t storage_lookup_read_result[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_result[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_partition_extracted[DMCU_STORAGE_LOOKUP_TRACE_SLOTS][2];
    uint16_t storage_lookup_capacity[DMCU_STORAGE_LOOKUP_TRACE_SLOTS][2];
    uint16_t storage_lookup_partition_result[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint32_t storage_lookup_record[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint32_t storage_lookup_buffer[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_cursor_hi[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_cursor_lo[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_sector_calls[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_ftl_calls[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_ftl_lba_hi[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_ftl_lba_lo[DMCU_STORAGE_LOOKUP_TRACE_SLOTS];
    uint16_t storage_lookup_record_words[DMCU_STORAGE_LOOKUP_TRACE_SLOTS]
                                        [DMCU_STORAGE_LOOKUP_RECORD_WORDS];
    uint8_t storage_lookup_head[DMCU_STORAGE_LOOKUP_TRACE_SLOTS]
                               [DMCU_STORAGE_LOOKUP_HEAD_BYTES];
    uint8_t storage_lookup_partition[DMCU_STORAGE_LOOKUP_TRACE_SLOTS]
                                    [DMCU_STORAGE_LOOKUP_PARTITION_BYTES];
    uint8_t storage_lookup_signature[DMCU_STORAGE_LOOKUP_TRACE_SLOTS][2];
    uint64_t region_mask_calls;
    uint32_t region_mask_trace_from[DMCU_REGION_MASK_TRACE_SLOTS];
    uint16_t region_mask_trace_sp[DMCU_REGION_MASK_TRACE_SLOTS];
    uint16_t region_mask_trace_fp[DMCU_REGION_MASK_TRACE_SLOTS];
    uint16_t region_mask_trace_args[DMCU_REGION_MASK_TRACE_SLOTS][6];
    uint64_t resource_open_calls;
    uint32_t resource_open_trace_from[DMCU_RESOURCE_OPEN_TRACE_SLOTS];
    uint16_t resource_open_trace_sp[DMCU_RESOURCE_OPEN_TRACE_SLOTS];
    uint16_t resource_open_trace_fp[DMCU_RESOURCE_OPEN_TRACE_SLOTS];
    uint16_t resource_open_trace_args[DMCU_RESOURCE_OPEN_TRACE_SLOTS][8];
    uint32_t resource_base_init_calls;
    uint32_t resource_base_init_caller;
    uint16_t resource_base_init_call_sp;
    uint16_t resource_base_init_arg_hi;
    uint16_t resource_base_init_arg_lo;
    uint32_t resource_base_init_writes;
    uint32_t resource_base_init_write_pc;
    uint16_t resource_base_init_write_sp;
    uint16_t resource_base_init_write_fp;
    uint16_t resource_base_init_capacity;
    uint16_t resource_base_init_units_per_block;
    uint16_t resource_base_init_reserved_blocks;
    uint16_t resource_base_init_result;
    uint16_t resource_base_init_block_bytes_hi;
    uint16_t resource_base_init_block_bytes_lo;
    uint16_t resource_base_init_count_values[DMCU_RESOURCE_BASE_COUNT_INPUTS];
    uint32_t resource_base_count_writes[DMCU_RESOURCE_BASE_COUNT_INPUTS];
    uint32_t resource_base_count_last_pc[DMCU_RESOURCE_BASE_COUNT_INPUTS];
    uint16_t resource_base_count_last_value[DMCU_RESOURCE_BASE_COUNT_INPUTS];
    uint32_t resource_range_writes[2];
    uint32_t resource_range_first_pc[2];
    uint32_t resource_range_last_pc[2];
    uint16_t resource_range_first_old[2];
    uint16_t resource_range_first_new[2];
    uint16_t resource_range_last_old[2];
    uint16_t resource_range_last_new[2];
    uint16_t resource_range_first_ds0[2];
    uint16_t resource_range_first_ds1[2];
    uint8_t resource_range_first_bus[2];
    uint16_t resource_range_last_logical[2];
    uint16_t resource_range_last_source_logical[2];
    uint32_t resource_range_last_source_physical[2];
    uint16_t resource_range_last_r8[2];
    uint16_t resource_range_last_r10[2];
    uint16_t resource_range_last_sp[2];
    uint16_t resource_range_last_fp[2];
    uint16_t resource_range_last_ds0[2];
    uint16_t resource_range_last_ds1[2];
    uint32_t resource_range_byte_writes[4];
    uint32_t resource_range_byte_first_pc[4];
    uint32_t resource_range_byte_last_pc[4];
    uint16_t resource_range_byte_first_logical[4];
    uint8_t resource_range_byte_first_old[4];
    uint8_t resource_range_byte_first_new[4];
    uint8_t resource_range_byte_last_old[4];
    uint8_t resource_range_byte_last_new[4];
    uint8_t resource_range_byte_first_bus[4];
    uint64_t resource_candidate_trace_count;
    uint32_t resource_candidate_trace_pc[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint32_t resource_candidate_trace_caller[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint32_t resource_candidate_trace_outer_caller[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint32_t resource_candidate_trace_source_physical[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_source_logical[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_old[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_base[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_range[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_sp[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_fp[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_r8[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_r10[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_ds0[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_ds1[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_parent_fp[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint16_t resource_candidate_trace_copy_args[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS][DMCU_RESOURCE_CANDIDATE_ARGUMENT_WORDS];
    uint16_t resource_candidate_trace_outer_args[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS][DMCU_RESOURCE_CANDIDATE_ARGUMENT_WORDS];
    uint16_t resource_candidate_trace_record[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS][DMCU_RESOURCE_CANDIDATE_RECORD_WORDS];
    bool resource_candidate_trace_record_valid[DMCU_RESOURCE_CANDIDATE_TRACE_SLOTS];
    uint64_t factory_record_writes;
    uint32_t factory_record_write_pc[DMCU_FACTORY_RECORD_TRACE_SLOTS];
    uint32_t factory_record_write_address[DMCU_FACTORY_RECORD_TRACE_SLOTS];
    uint16_t factory_record_write_old[DMCU_FACTORY_RECORD_TRACE_SLOTS];
    uint16_t factory_record_write_new[DMCU_FACTORY_RECORD_TRACE_SLOTS];
    uint16_t factory_record_write_sp[DMCU_FACTORY_RECORD_TRACE_SLOTS];
    uint16_t factory_record_write_fp[DMCU_FACTORY_RECORD_TRACE_SLOTS];
    uint16_t factory_record_write_ds0[DMCU_FACTORY_RECORD_TRACE_SLOTS];
    uint16_t factory_record_write_ds1[DMCU_FACTORY_RECORD_TRACE_SLOTS];
    uint8_t factory_record_write_bits[DMCU_FACTORY_RECORD_TRACE_SLOTS];
    uint64_t resource_io_calls;
    bool resource_io_trace_frozen;
    uint32_t resource_io_trace_frozen_pc;
    uint32_t resource_io_from[DMCU_RESOURCE_IO_TRACE_SLOTS];
    uint32_t resource_io_target[DMCU_RESOURCE_IO_TRACE_SLOTS];
    uint16_t resource_io_sp[DMCU_RESOURCE_IO_TRACE_SLOTS];
    uint16_t resource_io_fp[DMCU_RESOURCE_IO_TRACE_SLOTS];
    uint16_t resource_io_args[DMCU_RESOURCE_IO_TRACE_SLOTS][6];
    uint16_t resource_io_base[DMCU_RESOURCE_IO_TRACE_SLOTS];
    uint16_t resource_io_shift[DMCU_RESOURCE_IO_TRACE_SLOTS];
    uint16_t resource_io_window[DMCU_RESOURCE_IO_TRACE_SLOTS];
    uint16_t resource_io_logical_block[DMCU_RESOURCE_IO_TRACE_SLOTS];
    uint16_t resource_io_map_slot[DMCU_RESOURCE_IO_TRACE_SLOTS];
    uint64_t storage_geometry_trace_count;
    uint32_t storage_geometry_trace_pc[DMCU_STORAGE_GEOMETRY_TRACE_SLOTS];
    uint32_t storage_geometry_trace_address[DMCU_STORAGE_GEOMETRY_TRACE_SLOTS];
    uint16_t storage_geometry_trace_old[DMCU_STORAGE_GEOMETRY_TRACE_SLOTS];
    uint16_t storage_geometry_trace_new[DMCU_STORAGE_GEOMETRY_TRACE_SLOTS];
    uint8_t storage_geometry_trace_bits[DMCU_STORAGE_GEOMETRY_TRACE_SLOTS];
    uint64_t resource_window_writes;
    uint32_t resource_window_first_write_pc;
    uint32_t resource_window_last_write_pc;
    uint16_t resource_window_first_write_old;
    uint16_t resource_window_first_write_new;
    uint16_t resource_window_last_write_old;
    uint16_t resource_window_last_write_new;
    uint8_t resource_window_first_write_bits;
    uint8_t resource_window_last_write_bits;
    uint64_t resource_window_zero_io_calls;
    uint32_t resource_window_first_zero_from;
    uint32_t resource_window_first_zero_target;
    uint16_t resource_window_first_zero_args[6];
    uint16_t resource_window_first_zero_base;
    uint16_t resource_window_first_zero_shift;
    uint64_t indirect_callback_calls;
    uint32_t indirect_callback_from[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS];
    uint32_t indirect_callback_target[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS];
    uint16_t indirect_callback_sp[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS];
    uint16_t indirect_callback_fp[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS];
    uint16_t indirect_callback_object_hi[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS];
    uint16_t indirect_callback_object_lo[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS];
    uint16_t indirect_callback_field_hi[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS];
    uint16_t indirect_callback_field_lo[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS];
    uint16_t indirect_callback_stack[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS]
                                    [DMCU_INDIRECT_CALLBACK_STACK_WORDS];
    uint16_t indirect_callback_object[DMCU_INDIRECT_CALLBACK_TRACE_SLOTS]
                                     [DMCU_INDIRECT_CALLBACK_OBJECT_WORDS];
    uint64_t indirect_object_writes;
    uint32_t indirect_object_write_pc[DMCU_INDIRECT_OBJECT_WRITE_SLOTS];
    uint32_t indirect_object_write_address[DMCU_INDIRECT_OBJECT_WRITE_SLOTS];
    uint16_t indirect_object_write_old[DMCU_INDIRECT_OBJECT_WRITE_SLOTS];
    uint16_t indirect_object_write_new[DMCU_INDIRECT_OBJECT_WRITE_SLOTS];
    uint8_t indirect_object_write_bits[DMCU_INDIRECT_OBJECT_WRITE_SLOTS];
    uint16_t indirect_object_write_sp[DMCU_INDIRECT_OBJECT_WRITE_SLOTS];
    uint16_t indirect_object_write_fp[DMCU_INDIRECT_OBJECT_WRITE_SLOTS];
    uint16_t indirect_object_write_frame[DMCU_INDIRECT_OBJECT_WRITE_SLOTS]
                                        [DMCU_INDIRECT_OBJECT_WRITE_FRAME_WORDS];
    uint64_t ui_record_flow_count;
    uint32_t ui_record_flow_pc[DMCU_UI_RECORD_FLOW_SLOTS];
    uint32_t ui_record_flow_next[DMCU_UI_RECORD_FLOW_SLOTS];
    uint16_t ui_record_flow_sp[DMCU_UI_RECORD_FLOW_SLOTS];
    uint16_t ui_record_flow_fp[DMCU_UI_RECORD_FLOW_SLOTS];
    uint16_t ui_record_flow_r[DMCU_UI_RECORD_FLOW_SLOTS][4];
    uint16_t ui_record_flow_stack[DMCU_UI_RECORD_FLOW_SLOTS]
                                 [DMCU_UI_RECORD_STACK_WORDS];
    uint16_t ui_record_flow_frame[DMCU_UI_RECORD_FLOW_SLOTS]
                                 [DMCU_UI_RECORD_FRAME_WORDS];
    uint16_t ui_record_flow_globals[DMCU_UI_RECORD_FLOW_SLOTS]
                                   [DMCU_UI_RECORD_GLOBAL_WORDS];
    uint16_t ui_record_flow_object[DMCU_UI_RECORD_FLOW_SLOTS]
                                  [DMCU_UI_RECORD_OBJECT_WORDS];
    uint64_t ui_record_writes;
    uint32_t ui_record_write_pc[DMCU_UI_RECORD_WRITE_SLOTS];
    uint32_t ui_record_write_address[DMCU_UI_RECORD_WRITE_SLOTS];
    uint16_t ui_record_write_old[DMCU_UI_RECORD_WRITE_SLOTS];
    uint16_t ui_record_write_new[DMCU_UI_RECORD_WRITE_SLOTS];
    uint8_t ui_record_write_bits[DMCU_UI_RECORD_WRITE_SLOTS];
    uint16_t ui_record_write_sp[DMCU_UI_RECORD_WRITE_SLOTS];
    uint16_t ui_record_write_fp[DMCU_UI_RECORD_WRITE_SLOTS];
    /* Observer-only summary of the latest nonempty 1F:F470 state import.
     * The generic UI flow ring is intentionally busy and loses the one-shot
     * 0x0107/0x00B0 record within milliseconds. */
    uint64_t state_import_calls;
    uint64_t state_import_nonempty_calls;
    bool state_import_active;
    uint16_t state_import_pointer_hi;
    uint16_t state_import_pointer_lo;
    uint16_t state_import_input[8];
    uint32_t state_import_compare_count;
    uint32_t state_import_match_count;
    uint32_t state_import_mismatch_count;
    uint16_t state_import_last_compare_left;
    uint16_t state_import_last_compare_right;
    uint16_t state_import_last_compare_index;
    uint16_t state_import_result_hi;
    uint16_t state_import_result_lo;
    uint32_t state_import_return_target;
    uint16_t state_import_globals[10];
    /* Observer-only ring for comparing boot-time state imports with the
     * physical Start-key import without enabling high-volume QEMU logging. */
    uint64_t state_import_history_count;
    uint8_t state_import_history_active_slot;
    bool state_import_dispatch_history_active;
    uint16_t state_import_history_input[DMCU_STATE_IMPORT_HISTORY_SLOTS]
                                       [DMCU_STATE_IMPORT_HISTORY_INPUT_WORDS];
    uint32_t state_import_history_compare_count
        [DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint32_t state_import_history_match_count
        [DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint32_t state_import_history_mismatch_count
        [DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint16_t state_import_history_result_hi
        [DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint16_t state_import_history_result_lo
        [DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint32_t state_import_history_return_target
        [DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint16_t state_import_history_globals[DMCU_STATE_IMPORT_HISTORY_SLOTS]
                                         [DMCU_STATE_IMPORT_HISTORY_GLOBAL_WORDS];
    uint16_t state_import_history_mode[DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint16_t state_import_history_root_hi[DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint16_t state_import_history_root_lo[DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint16_t state_import_history_selector_count
        [DMCU_STATE_IMPORT_HISTORY_SLOTS];
    uint16_t state_import_history_selector_node_hi
        [DMCU_STATE_IMPORT_HISTORY_SLOTS][DMCU_STATE_SELECTOR_TRACE_SLOTS];
    uint16_t state_import_history_selector_node_lo
        [DMCU_STATE_IMPORT_HISTORY_SLOTS][DMCU_STATE_SELECTOR_TRACE_SLOTS];
    uint16_t state_import_history_selector_node_key
        [DMCU_STATE_IMPORT_HISTORY_SLOTS][DMCU_STATE_SELECTOR_TRACE_SLOTS];
    uint16_t state_import_history_selector_lookup_key
        [DMCU_STATE_IMPORT_HISTORY_SLOTS][DMCU_STATE_SELECTOR_TRACE_SLOTS];
    uint16_t state_import_history_dispatch
        [DMCU_STATE_IMPORT_HISTORY_SLOTS]
        [DMCU_STATE_IMPORT_HISTORY_DISPATCH_WORDS];
    uint16_t state_import_history_menu_state
        [DMCU_STATE_IMPORT_HISTORY_SLOTS];
    /* Bounded control-flow trace for the callback actually reached through
     * the type-0003 dispatcher return at 28:856A.  This is observer-only and
     * distinguishes an overwritten callback pointer from a bad callback
     * branch without high-volume LOG_UNIMP output. */
    uint64_t start_callback_dispatch_count;
    uint64_t start_callback_f15c_count;
    uint32_t start_callback_last_target;
    bool start_callback_trace_active;
    bool start_callback_running;
    bool start_callback_trace_complete;
    bool start_callback_trace_overflow;
    uint64_t start_callback_instruction_count;
    uint32_t start_callback_current_pc;
    uint32_t start_callback_current_next;
    uint32_t start_callback_trace_count;
    uint16_t start_callback_entry_gpr[4];
    uint16_t start_callback_entry_sp;
    uint16_t start_callback_entry_fp;
    uint16_t start_callback_entry_globals[8];
    uint32_t start_callback_trace_pc[DMCU_START_CALLBACK_TRACE_SLOTS];
    uint32_t start_callback_trace_next[DMCU_START_CALLBACK_TRACE_SLOTS];
    uint16_t start_callback_trace_word[DMCU_START_CALLBACK_TRACE_SLOTS];
    uint16_t start_callback_trace_psw[DMCU_START_CALLBACK_TRACE_SLOTS];
    uint16_t start_callback_trace_gpr[DMCU_START_CALLBACK_TRACE_SLOTS][4];
    uint16_t start_callback_trace_sp[DMCU_START_CALLBACK_TRACE_SLOTS];
    uint16_t start_callback_trace_fp[DMCU_START_CALLBACK_TRACE_SLOTS];
    /* Observer-only call/return provenance for exact 33:4D2A.  Its body is
     * balanced, so a bad RETS target must be distinguished from damage in
     * the caller frame that existed before this wrapper was entered. */
    uint64_t menu_context_release_trace_count;
    uint32_t menu_context_release_trace_from
        [DMCU_MENU_CONTEXT_RELEASE_TRACE_SLOTS];
    uint32_t menu_context_release_trace_return
        [DMCU_MENU_CONTEXT_RELEASE_TRACE_SLOTS];
    uint16_t menu_context_release_trace_sp
        [DMCU_MENU_CONTEXT_RELEASE_TRACE_SLOTS];
    uint16_t menu_context_release_trace_fp
        [DMCU_MENU_CONTEXT_RELEASE_TRACE_SLOTS];
    uint16_t menu_context_release_trace_return_sp
        [DMCU_MENU_CONTEXT_RELEASE_TRACE_SLOTS];
    uint16_t menu_context_release_trace_return_fp
        [DMCU_MENU_CONTEXT_RELEASE_TRACE_SLOTS];
    uint16_t menu_context_release_trace_stack
        [DMCU_MENU_CONTEXT_RELEASE_TRACE_SLOTS]
        [DMCU_MENU_CONTEXT_RELEASE_STACK_WORDS];
    /* Observer-only provenance for non-return control transfers from outside
     * 31:C000..31:E740 into that late segment-31 range while the Start
     * callback is running.  The flat image contains several colliding
     * routines there; retaining the caller and its newly-created stack frame
     * identifies the exact logical entry that later reaches 31:E740. */
    uint64_t start_late31_entry_trace_count;
    uint32_t start_late31_entry_trace_from
        [DMCU_START_LATE31_ENTRY_TRACE_SLOTS];
    uint32_t start_late31_entry_trace_target
        [DMCU_START_LATE31_ENTRY_TRACE_SLOTS];
    uint16_t start_late31_entry_trace_word
        [DMCU_START_LATE31_ENTRY_TRACE_SLOTS];
    uint16_t start_late31_entry_trace_sp
        [DMCU_START_LATE31_ENTRY_TRACE_SLOTS];
    uint16_t start_late31_entry_trace_fp
        [DMCU_START_LATE31_ENTRY_TRACE_SLOTS];
    uint16_t start_late31_entry_trace_gpr
        [DMCU_START_LATE31_ENTRY_TRACE_SLOTS][4];
    uint16_t start_late31_entry_trace_stack
        [DMCU_START_LATE31_ENTRY_TRACE_SLOTS]
        [DMCU_START_LATE31_ENTRY_STACK_WORDS];
    /* Observer-only entry/return provenance for the exact 31:D9AA GPIO flag
     * scanner.  It is call-free and balanced, so this trace proves whether
     * its caller frame survives the routine without changing guest state. */
    uint64_t start_gpio_scan_trace_count;
    uint32_t start_gpio_scan_trace_from[DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint32_t start_gpio_scan_trace_return
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_gpio_scan_trace_sp[DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_gpio_scan_trace_fp[DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_gpio_scan_trace_return_sp
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_gpio_scan_trace_return_fp
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_gpio_scan_trace_stack
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS]
        [DMCU_START_BOUNDED_CALL_STACK_WORDS];
    /* Observer-only snapshots of the computed near dispatch at 30:0A3C.
     * The guest reads an event-indexed word through DS0:R1, pushes it, and
     * executes RET.  Keep both the word that RET consumes and the untouched
     * words underneath it so a missing far-return frame can be distinguished
     * from a bad table entry without modifying guest state. */
    uint64_t start_menu_dispatch_trace_count;
    uint32_t start_menu_dispatch_trace_target
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS];
    uint16_t start_menu_dispatch_trace_word
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS];
    uint16_t start_menu_dispatch_trace_sp
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS];
    uint16_t start_menu_dispatch_trace_return_sp
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS];
    uint16_t start_menu_dispatch_trace_fp
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS];
    uint16_t start_menu_dispatch_trace_event
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS];
    uint16_t start_menu_dispatch_trace_ds0
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS];
    uint16_t start_menu_dispatch_trace_ds1
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS];
    uint16_t start_menu_dispatch_trace_table_lo
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS];
    uint16_t start_menu_dispatch_trace_gpr
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS]
        [DMCU_START_MENU_DISPATCH_GPR_WORDS];
    uint16_t start_menu_dispatch_trace_stack
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS]
        [DMCU_START_MENU_DISPATCH_STACK_WORDS];
    uint8_t start_menu_dispatch_trace_locals
        [DMCU_START_MENU_DISPATCH_TRACE_SLOTS]
        [DMCU_START_MENU_DISPATCH_LOCAL_BYTES];
    /* The exact application-page renderer is one large framed function at
     * 18:4E62..5962; 18:57A4 is only its computed near dispatch.  Retain the
     * real far-call frame at entry and return, plus every write that overlaps
     * those two return words, to find the first corrupting guest instruction. */
    bool start_page_renderer_trace_active;
    uint32_t start_page_renderer_trace_active_slot;
    uint64_t start_page_renderer_trace_active_sequence;
    uint16_t start_page_renderer_return_frame_base;
    uint64_t start_page_renderer_trace_count;
    uint32_t start_page_renderer_trace_from
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint32_t start_page_renderer_trace_return
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_page_renderer_trace_sp
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_page_renderer_trace_fp
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_page_renderer_trace_return_sp
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_page_renderer_trace_return_fp
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS];
    uint16_t start_page_renderer_trace_frame_initial
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS][2];
    uint16_t start_page_renderer_trace_frame_final
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS][2];
    uint16_t start_page_renderer_trace_stack
        [DMCU_START_BOUNDED_CALL_TRACE_SLOTS]
        [DMCU_START_BOUNDED_CALL_STACK_WORDS];
    uint64_t start_page_return_write_count;
    uint64_t start_page_return_write_call_sequence
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint32_t start_page_return_write_pc
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint32_t start_page_return_write_caller
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint16_t start_page_return_write_address
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint16_t start_page_return_write_old
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint16_t start_page_return_write_new
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint16_t start_page_return_write_sp
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint16_t start_page_return_write_fp
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint16_t start_page_return_write_ds0
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint16_t start_page_return_write_ds1
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint16_t start_page_return_write_gpr
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS]
        [DMCU_START_PAGE_RETURN_GPR_WORDS];
    uint16_t start_page_return_write_args
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS]
        [DMCU_START_PAGE_RETURN_ARGUMENT_WORDS];
    uint16_t start_page_return_write_frame_fp
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS]
        [DMCU_START_PAGE_RETURN_FRAME_DEPTH];
    uint32_t start_page_return_write_frame_caller
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS]
        [DMCU_START_PAGE_RETURN_FRAME_DEPTH];
    uint16_t start_page_return_write_frame_args
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS]
        [DMCU_START_PAGE_RETURN_FRAME_DEPTH]
        [DMCU_START_PAGE_RETURN_ARGUMENT_WORDS];
    uint32_t start_page_return_write_repeat_pc
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint32_t start_page_return_write_repeat_end
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint32_t start_page_return_write_repeat_count
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint8_t start_page_return_write_bits
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint8_t start_page_return_write_bus
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    uint8_t start_page_return_write_in_irq
        [DMCU_START_PAGE_RETURN_WRITE_TRACE_SLOTS];
    /* Guest-write provenance used only when the obsolete flat 32:F15C body
     * is observed.  It proved that the missing LINK #0x57 frame allowed
     * nested calls to overwrite the apparent FP-0x4E object. */
    bool start_object_watch_active;
    uint16_t start_object_watch_base;
    uint16_t start_object_watch_entry_sp;
    uint16_t start_object_watch_entry_fp;
    uint64_t start_object_write_count;
    uint64_t start_object_renderer_entries;
    uint64_t start_object_input_entries;
    uint64_t start_object_context_entries;
    uint64_t start_object_context_test_entries;
    uint64_t start_object_callback_b19c_entries;
    uint64_t start_object_callback_5896_entries;
    uint32_t start_object_write_pc[DMCU_START_OBJECT_WRITE_TRACE_SLOTS];
    uint32_t start_object_write_address[DMCU_START_OBJECT_WRITE_TRACE_SLOTS];
    uint16_t start_object_write_old[DMCU_START_OBJECT_WRITE_TRACE_SLOTS];
    uint16_t start_object_write_new[DMCU_START_OBJECT_WRITE_TRACE_SLOTS];
    uint16_t start_object_write_sp[DMCU_START_OBJECT_WRITE_TRACE_SLOTS];
    uint16_t start_object_write_fp[DMCU_START_OBJECT_WRITE_TRACE_SLOTS];
    uint8_t start_object_write_bits[DMCU_START_OBJECT_WRITE_TRACE_SLOTS];
    uint8_t start_object_write_bus[DMCU_START_OBJECT_WRITE_TRACE_SLOTS];
    bool start_object_write_in_irq[DMCU_START_OBJECT_WRITE_TRACE_SLOTS];
    /* Observer-only provenance for writes overlapping the exact 30:E662
     * Start-context function.  The first write and a bounded tail identify
     * both its installer and any later broad image copy which retires it. */
    uint64_t start_context_code_write_count;
    uint32_t start_context_code_first_pc;
    uint32_t start_context_code_first_address;
    uint16_t start_context_code_first_old;
    uint16_t start_context_code_first_new;
    uint8_t start_context_code_first_bits;
    uint32_t start_context_code_write_pc[DMCU_START_CONTEXT_CODE_WRITE_SLOTS];
    uint32_t start_context_code_write_address[
        DMCU_START_CONTEXT_CODE_WRITE_SLOTS];
    uint16_t start_context_code_write_old[DMCU_START_CONTEXT_CODE_WRITE_SLOTS];
    uint16_t start_context_code_write_new[DMCU_START_CONTEXT_CODE_WRITE_SLOTS];
    uint16_t start_context_code_write_ds0[DMCU_START_CONTEXT_CODE_WRITE_SLOTS];
    uint16_t start_context_code_write_ds1[DMCU_START_CONTEXT_CODE_WRITE_SLOTS];
    uint8_t start_context_code_write_bits[DMCU_START_CONTEXT_CODE_WRITE_SLOTS];
    uint64_t manager_state_writes;
    uint32_t manager_state_write_pc[DMCU_MANAGER_STATE_WRITE_SLOTS];
    uint32_t manager_state_write_address[DMCU_MANAGER_STATE_WRITE_SLOTS];
    uint16_t manager_state_write_old[DMCU_MANAGER_STATE_WRITE_SLOTS];
    uint16_t manager_state_write_new[DMCU_MANAGER_STATE_WRITE_SLOTS];
    uint8_t manager_state_write_bits[DMCU_MANAGER_STATE_WRITE_SLOTS];
    uint16_t manager_state_write_sp[DMCU_MANAGER_STATE_WRITE_SLOTS];
    uint16_t manager_state_write_fp[DMCU_MANAGER_STATE_WRITE_SLOTS];
    uint32_t indirect_object_copy_calls;
    uint32_t indirect_object_copy_from;
    uint16_t indirect_object_copy_sp;
    uint16_t indirect_object_copy_fp;
    uint16_t indirect_object_copy_gpr[5];
    uint32_t application_init_calls;
    uint32_t application_init_last_from;
    uint32_t application_init_last_target;
    uint32_t application_init_last_r0;
    uint32_t application_init_last_r1;
    uint32_t resource_init_calls;
    uint32_t resource_init_last_from;
    uint32_t resource_init_last_target;
    uint32_t resource_init_last_r0;
    uint32_t resource_init_last_r1;
    uint32_t nand_manager_caller;
    uint32_t stream_copy_reads;
    uint32_t stream_copy_pc;
    uint32_t stream_copy_logical;
    uint32_t stream_copy_physical;
    uint32_t stream_copy_value;
    uint32_t stream_copy_ds0;
    uint32_t stream_copy_ds1;
    uint32_t context_data_trace_count;
    uint32_t context_data_trace_pc[DMCU_CONTEXT_DATA_TRACE_ENTRIES];
    uint32_t context_data_trace_physical[DMCU_CONTEXT_DATA_TRACE_ENTRIES];
    uint16_t context_data_trace_logical[DMCU_CONTEXT_DATA_TRACE_ENTRIES];
    uint16_t context_data_trace_value[DMCU_CONTEXT_DATA_TRACE_ENTRIES];
    uint8_t context_data_trace_bits[DMCU_CONTEXT_DATA_TRACE_ENTRIES];
    bool context_data_trace_write[DMCU_CONTEXT_DATA_TRACE_ENTRIES];
    uint32_t stream_guard_calls;
    uint32_t stream_guard_result;
    uint32_t stream_page_calls;
    uint32_t stream_page_result;
    uint32_t stream_page_stage;
    uint32_t stream_shift_input;
    uint32_t stream_shift_count;
    uint32_t stream_shift_result;
    uint32_t stream_shift_buffer_result;
    uint32_t stream_map_calls;
    uint32_t stream_map_arg;
    uint32_t stream_map_result;
    uint32_t stream_allocate_calls;
    uint32_t stream_allocate_arg;
    uint32_t stream_allocate_result;
    uint32_t stream_classify_calls;
    uint32_t stream_classify_result;
    uint32_t stream_arg0;
    uint32_t stream_arg1;
    uint32_t stream_arg2;
    uint32_t stream_source_check;
    uint32_t stream_source_psw;
    uint32_t stream_source_branch_seen;
    uint32_t stream_source_branch_taken;
    uint32_t stream_count_check;
    uint32_t stream_count_psw;
    uint32_t stream_count_branch_seen;
    uint32_t stream_count_branch_taken;
    uint32_t stream_bound_result;
    uint32_t stream_bound_value;
    uint32_t stream_bound_psw;
    uint32_t stream_stage_exit;
    uint32_t stream_error_entries;
    uint32_t stream_error_from_pc;
    uint32_t stream_error_from_word;
    uint32_t stream_error_psw;
    uint32_t stream_loop_entries;
    uint32_t stream_loop_psw;
    uint32_t partition_stage;
    uint32_t partition_value0;
    uint32_t partition_value1;
    uint32_t partition_result;
    uint32_t burn_error_writes;
    uint32_t burn_error_pc;
    uint32_t burn_error_value;
    uint32_t object_init_count;
    uint32_t object_init_index[DMCU_OBJECT_INIT_TRACE_SLOTS];
    uint32_t object_init_cb62[DMCU_OBJECT_INIT_TRACE_SLOTS];
    uint32_t object_init_result[DMCU_OBJECT_INIT_TRACE_SLOTS];
    uint32_t object_init_loop_index;
    uint32_t object_init_loop_result;
    uint32_t cb62_calls;
    uint32_t cb62_stage;
    uint32_t cb62_geometry;
    uint32_t cb62_aa1a_result;
    uint32_t cb62_08a6_result;
    uint32_t cb62_7dd8_result;
    uint32_t cb62_result;
    uint32_t cb62_history_command[DMCU_CB62_TRACE_SLOTS];
    uint32_t cb62_history_geometry[DMCU_CB62_TRACE_SLOTS];
    uint32_t cb62_history_aa1a[DMCU_CB62_TRACE_SLOTS];
    uint32_t cb62_history_08a6[DMCU_CB62_TRACE_SLOTS];
    uint32_t cb62_history_7dd8[DMCU_CB62_TRACE_SLOTS];
    uint32_t cb62_history_result[DMCU_CB62_TRACE_SLOTS];
    uint32_t b0b2_calls;
    uint32_t b0b2_command;
    uint32_t b0b2_index;
    uint32_t b0b2_stage;
    uint32_t b0b2_primary_pointer;
    uint32_t b0b2_secondary_pointer;
    uint32_t b0b2_7d66_result;
    uint32_t b0b2_global_after_7d66;
    uint32_t b0b2_6816_result;
    uint32_t b0b2_failure_pc;
    uint32_t b0b2_result;
    uint32_t unsupported_pc;
    uint32_t unsupported_word;
    uint32_t unsupported_count;
    /* Diagnostic boundary only: 1 forbidden REP target, 2 service mode.
     * This is not a guest-visible EXR or an emulated IREP vector. */
    uint32_t unsupported_repeat_reason;
    uint32_t unsupported_predecessor_pc;
    uint32_t unsupported_predecessor_next_pc;
    uint32_t unsupported_predecessor_word;
    uint32_t unsupported_predecessor_ext;
    uint32_t unsupported_predecessor_sp;
    uint32_t unsupported_predecessor_fp;
    uint32_t first_low_fp_pc;
    uint32_t first_low_fp_word;
    uint32_t first_low_fp_old;
    uint32_t first_low_fp_new;
    uint32_t first_low_fp_sp;
    uint32_t application_file_attach_frame_calls;
    uint32_t application_file_attach_frame_address;
    uint32_t application_file_attach_frame_expected;
    uint32_t application_file_attach_frame_writes;
    uint32_t application_file_attach_frame_first_pc;
    uint32_t application_file_attach_frame_first_address;
    uint32_t application_file_attach_frame_first_old;
    uint32_t application_file_attach_frame_first_new;
    uint32_t application_file_attach_frame_first_bits;
    uint32_t application_file_attach_frame_first_source;
    uint32_t application_file_attach_frame_first_sp;
    uint32_t application_file_attach_frame_first_fp;
    uint32_t application_file_attach_frame_exit_sp;
    uint32_t application_file_attach_frame_exit_fp;
    uint32_t first_low_sp_pc;
    uint32_t first_low_sp_next_pc;
    uint32_t first_low_sp_word;
    uint32_t first_low_sp_old;
    uint32_t first_low_sp_new;
    uint32_t first_low_sp_old_fp;
    uint32_t first_low_sp_new_fp;
    uint32_t first_low_sp_gpr[16];
    uint32_t direct_menu_stack_arm_pc;
    uint32_t direct_menu_stack_arm_sp;
    uint32_t direct_menu_stack_arm_fp;
    uint32_t direct_menu_stack_escape_kind;
    uint32_t direct_menu_stack_escape_pc;
    uint32_t direct_menu_stack_escape_next_pc;
    uint32_t direct_menu_stack_escape_word;
    uint32_t direct_menu_stack_escape_ext;
    uint32_t direct_menu_stack_escape_old_sp;
    uint32_t direct_menu_stack_escape_new_sp;
    uint32_t direct_menu_stack_escape_old_fp;
    uint32_t direct_menu_stack_escape_new_fp;
    uint32_t direct_menu_stack_escape_gpr[16];
    uint32_t direct_menu_stack_escape_stack[8];
    uint32_t irq_save_fp_saves;
    uint32_t irq_save_fp_save_entry;
    uint32_t irq_save_fp_save_pc;
    uint32_t irq_save_fp_save_next_pc;
    uint32_t irq_save_fp_save_old;
    uint32_t irq_save_fp_save_expected;
    uint32_t irq_save_fp_saved_value;
    uint32_t irq_save_fp_save_logical;
    uint32_t irq_save_fp_save_physical;
    uint32_t irq_save_fp_save_bits;
    uint32_t irq_save_fp_save_bus;
    uint32_t irq_save_fp_save_ds0;
    uint32_t irq_save_fp_save_ds1;
    uint32_t irq_save_fp_overwrites;
    uint32_t irq_save_fp_first_overwrite_entry;
    uint32_t irq_save_fp_first_overwrite_pc;
    uint32_t irq_save_fp_first_overwrite_next_pc;
    uint32_t irq_save_fp_first_overwrite_old;
    uint32_t irq_save_fp_first_overwrite_new;
    uint32_t irq_save_fp_first_overwrite_logical;
    uint32_t irq_save_fp_first_overwrite_physical;
    uint32_t irq_save_fp_first_overwrite_bits;
    uint32_t irq_save_fp_first_overwrite_bus;
    uint32_t irq_save_fp_first_overwrite_ds0;
    uint32_t irq_save_fp_first_overwrite_ds1;
    uint32_t irq_save_fp_first_overwrite_sp;
    uint32_t irq_save_fp_first_overwrite_fp;
    uint32_t irq_save_fp_restores;
    uint32_t irq_save_fp_restore_entry;
    uint32_t irq_save_fp_restore_pc;
    uint32_t irq_save_fp_restore_expected;
    uint32_t irq_save_fp_restore_value;
    uint32_t irq_save_fp_restore_fp;
    uint64_t benign_sp_wraps;
    uint32_t benign_sp_wrap_pc;
    uint32_t benign_sp_wrap_word;
    uint32_t auxiliary_code_base;
    uint32_t auxiliary_code_limit;
    uint32_t resident_rom_base;
    uint32_t resident_rom_limit;
    uint32_t startup_context;
    bool mask_rom03_present;
    bool rom_hle_enabled;
    bool soc_rom_skeleton;
    bool hle_ui_enabled;
    bool control_observers_minimal; /* opt-in; strict faults/key ACK retained */
    bool instruction_clock_enabled;
    uint32_t instruction_clock_hz;
    uint32_t instruction_clock_cached_pll;
    uint32_t instruction_clock_cached_clkcon;
    uint32_t instruction_clock_fraction;
    uint64_t instruction_clock_period_fp;
    uint64_t instruction_clock_count;
    uint64_t instruction_clock_ns;
    uint32_t instruction_clock_fault;
    bool instruction_clock_data_active;
    uint64_t instruction_clock_cycles;
    uint64_t instruction_clock_data_waits;
    uint64_t instruction_clock_external_data;
    uint64_t instruction_clock_unknown_map;
    uint64_t instruction_clock_unknown;
    uint16_t instruction_clock_last_unknown;
    bool hle_ui_active;
    bool native_ui_active;
    bool in_interrupt;
    bool missing_rom_valid;
    bool missing_rom_call_valid;
    bool event_frame_watch_active;
    bool event_frame_write_valid;
    bool invalid_control_valid;
    bool hardware_init_return_first_valid;
    bool hardware_init_return_exit_valid;
    bool graphics_frame_watch_active;
    bool event_text_overwrite_valid;
    bool far_copy_bad_valid;
    bool unsupported_valid;
    bool first_low_fp_valid;
    bool application_file_attach_frame_watch_active;
    bool application_file_attach_frame_exit_valid;
    bool first_low_sp_valid;
    bool direct_menu_stack_watch_active;
    bool direct_menu_stack_escape_valid;
    bool irq_save_fp_watch_active;
} CPUDMCUState;

struct ArchCPU {
    CPUState parent_obj;
    CPUDMCUState env;
    GArray *interrupt_contexts; /* suspended parents, excludes current IRQ */
    uint32_t migration_features; /* transient configuration signature */
    MemoryRegion *code_memory;
    MemoryRegion *internal_memory;
    uint8_t *internal_data;
    void *sfr_device_opaque;
    uint16_t (*sfr_device_read)(void *opaque, unsigned reg, uint16_t value);
    void (*sfr_device_write)(void *opaque, unsigned reg,
                             uint16_t old_value, uint16_t value);
    /* Explicit machine-installed missing-ROM services, separate from the
     * legacy ROM/UI diagnostics. Never a generic instruction replacement. */
    void *rom_service_opaque;
    bool dtu_refill_trace_enabled;
    bool control_observers_minimal;
    bool instruction_clock_enabled;
    bool (*rom_service)(void *opaque, CPUDMCUState *env, uint32_t pc);
    void (*rom_service_reset)(void *opaque);
    uint32_t reset_pc;
    uint32_t auxiliary_code_base;
    uint32_t auxiliary_code_limit;
    uint32_t resident_rom_base;
    uint32_t resident_rom_limit;
    uint32_t startup_context;
    bool mask_rom03_present;
    bool rom_hle_enabled;
    bool soc_rom_skeleton;
    bool hle_ui_enabled;
};

uint16_t dmcu_sfr_read_word(CPUDMCUState *env, unsigned reg);
uint32_t dmcu_system_clock_hz(const CPUDMCUState *env);
void dmcu_instruction_clock_step(CPUDMCUState *env, uint16_t word);
void dmcu_instruction_clock_data(CPUDMCUState *env, uint32_t physical);
void dmcu_sfr_write_word(CPUDMCUState *env, unsigned reg, uint16_t value);
void dmcu_irq_update(CPUDMCUState *env);
void dmcu_irq_raise(DMCUCPU *cpu, unsigned source);
void dmcu_internal_memory_write(DMCUCPU *cpu, uint32_t addr,
                                uint32_t value, int bits);
void dmcu_interrupt_complete(CPUDMCUState *env);
void dmcu_software_trap(CPUDMCUState *env, uint32_t return_pc, unsigned trap);
bool dmcu_dtu_has_work(CPUDMCUState *env);
bool dmcu_dtu_run(DMCUCPU *cpu);
void dmcu_dtu_trace_irq(DMCUCPU *cpu, unsigned source);
void dmcu_dtu_trace_reload(CPUDMCUState *env, unsigned channel, unsigned count);
char *dmcu_dtu_refill_state(DMCUCPU *cpu);

void dmcu_record_direct_menu_stack_escape(DMCUCPU *cpu, uint32_t kind,
                                          uint32_t pc, uint32_t next_pc,
                                          uint16_t word, uint16_t ext,
                                          uint16_t old_sp, uint16_t old_fp);
void dmcu_file_component_record_stack_write(CPUDMCUState *env,
                                            uint32_t logical,
                                            uint32_t backing,
                                            uint32_t old_value,
                                            uint32_t value,
                                            int bits,
                                            uint8_t source);
void dmcu_file_wrapper_record_stack_write(CPUDMCUState *env,
                                          uint32_t logical,
                                          uint32_t backing,
                                          uint32_t old_value,
                                          uint32_t value,
                                          int bits,
                                          uint8_t source);
void dmcu_application_file_attach_record_frame_write(CPUDMCUState *env,
                                                     uint32_t address,
                                                     uint32_t old_value,
                                                     uint32_t value,
                                                     int bits,
                                                     uint8_t source);
void dmcu_start_page_return_record_write(CPUDMCUState *env,
                                         uint32_t address,
                                         uint32_t old_value,
                                         uint32_t new_value,
                                         int bits,
                                         uint8_t bus,
                                         uint32_t pc);
void dmcu_npe_resource_return_record_write(CPUDMCUState *env,
                                           uint32_t address,
                                           uint32_t old_value,
                                           uint32_t new_value,
                                           int bits,
                                           uint8_t bus,
                                           uint32_t pc);

struct DMCUCPUClass {
    CPUClass parent_class;
    DeviceRealize parent_realize;
    ResettablePhases parent_phases;
};

static inline int dmcu_cpu_mmu_index(CPUDMCUState *env, bool ifetch)
{
    return ifetch ? MMU_CODE_IDX :
           (env->ignore_ds_count ? MMU_UNBANKED_IDX : MMU_DATA_IDX);
}

#define cpu_mmu_index dmcu_cpu_mmu_index
#define cpu_list dmcu_cpu_list

static inline void cpu_get_tb_cpu_state(CPUDMCUState *env, vaddr *pc,
                                        uint64_t *cs_base, uint32_t *flags)
{
    *pc = env->pc & 0x00ffffffu;
    *cs_base = 0;
    *flags = 0;
}

static inline uint32_t dmcu_code_segment(uint32_t pc)
{
    return (pc >> 16) & 0xff;
}

static inline uint32_t dmcu_code_pc(uint32_t pc)
{
    return pc & 0xffff;
}

static inline uint32_t dmcu_code_address(uint32_t segment, uint32_t pc)
{
    return ((segment & 0xff) << 16) | (pc & 0xffff);
}

static inline uint32_t dmcu_code_advance(uint32_t address, unsigned bytes)
{
    /* Fig. 3: CS concatenates a 16-bit PC; PC carry does not change CS. */
    return dmcu_code_address(dmcu_code_segment(address),
                             dmcu_code_pc(address) + bytes);
}

void dmcu_cpu_list(void);
extern const VMStateDescription vmstate_dmcu_cpu;
void dmcu_translate_init(void);
hwaddr dmcu_cpu_get_phys_page_debug(CPUState *cs, vaddr addr);
bool dmcu_cpu_tlb_fill(CPUState *cs, vaddr address, int size,
                       MMUAccessType access_type, int mmu_idx,
                       bool probe, uintptr_t retaddr);
int dmcu_print_insn(bfd_vma addr, disassemble_info *info);

#include "exec/cpu-all.h"

#endif
