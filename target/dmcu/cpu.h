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

#define DMCU_AS_DATA 0
#define DMCU_AS_CODE 1

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
#define DMCU_APPLICATION_TRACE_ENTRIES 181
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
#define DMCU_FONT_COPY_TRACE_SLOTS 512
#define DMCU_NATIVE_REFRESH_TRACE_SLOTS 32
#define DMCU_NATIVE_FRAMEBUFFER_BYTES (240 * 120 / 2)
#define DMCU_TEXT_TRACE_SLOTS 16
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
#define DMCU_CLOCK_STREAM_OBJECT_BYTES 48
#define DMCU_CLOCK_STREAM_MOVE_TRACE_SLOTS 16
#define DMCU_CLOCK_STREAM_MOVE_ARGUMENT_WORDS 6
#define DMCU_CLOCK_STREAM_MOVE_SAMPLE_BYTES 8
#define DMCU_CLOCK_SCAN_ARGUMENT_WORDS 12
#define DMCU_CLOCK_SCAN_LOCAL_WORDS 20
#define DMCU_CLOCK_CORE_CALL_TRACE_SLOTS 96
#define DMCU_SELECTOR_STATE_TRACE_SLOTS 32
#define DMCU_APPLICATION_STATE_WRITE_FRAMES 6
#define DMCU_EVENT_STATE_TRACE_SLOTS 64
#define DMCU_USB_BOOT_TRACE_SLOTS 32
#define DMCU_USB_BOOT_MILESTONES 5

#define DMCU_SFR_SB       0x02
#define DMCU_SFR_DS0      0x10
#define DMCU_SFR_DS1      0x11
#define DMCU_SFR_PSW      0x81

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

typedef struct CPUArchState {
    uint32_t pc;             /* byte-addressed CS:PC */
    uint32_t gpr[16];        /* 16-bit R0..R15 */
    uint32_t sfr[256];       /* 16-bit direct/SFR register file */
    uint32_t psw;            /* Z,C,N,V in bits 0..3 */
    uint32_t shift_buffer;   /* 16-bit DSP shift buffer */
    uint32_t se;             /* exponent-derivation result */
    uint32_t repeat_pc;
    uint32_t repeat_end;
    uint32_t repeat_count;
    uint32_t repeat_block;
    uint32_t interrupt_repeat_pc;
    uint32_t interrupt_repeat_end;
    uint32_t interrupt_repeat_count;
    uint32_t interrupt_repeat_block;
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
    uint32_t post_registry_hook_returns;
    uint32_t post_registry_hook_return_pc;
    uint16_t post_registry_hook_return_sp;
    uint16_t post_registry_hook_return_word0;
    uint16_t post_registry_hook_return_word1;
    uint32_t post_registry_hook_exec[3];
    uint16_t post_registry_hook_word[3];
    uint32_t overlay_code_syncs;
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
    uint32_t invalid_control_sp;
    uint32_t invalid_control_fp;
    uint32_t invalid_control_in_interrupt;
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
    uint32_t control_trace_from[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_to[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_word[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_sp[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_fp[DMCU_CONTROL_TRACE_WORDS];
    uint32_t control_trace_count;
    bool control_trace_frozen;
    uint32_t application_trace_calls[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_from[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_sp[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_r0[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_r1[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_r2[DMCU_APPLICATION_TRACE_ENTRIES];
    uint32_t application_trace_args[DMCU_APPLICATION_TRACE_ENTRIES][4];
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
    MemoryRegion *code_memory;
    uint8_t *internal_data;
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

struct DMCUCPUClass {
    CPUClass parent_class;
    DeviceRealize parent_realize;
    ResettablePhases parent_phases;
};

static inline int dmcu_cpu_mmu_index(CPUDMCUState *env, bool ifetch)
{
    return ifetch ? MMU_CODE_IDX : MMU_DATA_IDX;
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

void dmcu_cpu_list(void);
void dmcu_translate_init(void);
hwaddr dmcu_cpu_get_phys_page_debug(CPUState *cs, vaddr addr);
bool dmcu_cpu_tlb_fill(CPUState *cs, vaddr address, int size,
                       MMUAccessType access_type, int mmu_idx,
                       bool probe, uintptr_t retaddr);
int dmcu_print_insn(bfd_vma addr, disassemble_info *info);

#include "exec/cpu-all.h"

#endif
