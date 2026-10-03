# 脚本分类全表

由 `maintenance/catalog_scripts.py` 生成；分类是用途，不代表生产可用或安全只读。
具体使用入口与风险见 [README](README.md)。目录名 tests 不意味着全部是不依赖固件的单元测试。

## 模拟器运行与管理（20）

| 文件 | 用途 |
| --- | --- |
| [build-np560.ps1](build-np560.ps1) | 运行入口或运行实现，参数/用途见文件。 |
| [manage-np560-device.ps1](manage-np560-device.ps1) | 运行入口或运行实现，参数/用途见文件。 |
| [move-np560-restored-device.ps1](move-np560-restored-device.ps1) | 运行入口或运行实现，参数/用途见文件。 |
| [np560_device_backup.py](np560_device_backup.py) | Back up or restore a stopped NP560+ device without launching QEMU. |
| [np560_lan_proxy.py](np560_lan_proxy.py) | LAN-only TCP bridge to the existing loopback Web emulator (no guest restart). |
| [preflight-np560.ps1](preflight-np560.ps1) | 运行入口或运行实现，参数/用途见文件。 |
| [run-np560-web.ps1](run-np560-web.ps1) | 运行入口或运行实现，参数/用途见文件。 |
| [run-np560.ps1](run-np560.ps1) | 运行入口或运行实现，参数/用途见文件。 |
| [serve_np560_npe_codec.py](serve_np560_npe_codec.py) | Serve experimental candidate-compatible NPE PCM over a local Unix socket. |
| [web/__init__.py](web/__init__.py) | NP560+ local Web frontend. |
| [web/app.js](web/app.js) | 运行入口或运行实现，参数/用途见文件。 |
| [web/audio_output.js](web/audio_output.js) | 运行入口或运行实现，参数/用途见文件。 |
| [web/device_backup.py](web/device_backup.py) | Offline, byte-preserving device backups; never boot or modify a guest. |
| [web/device_config.py](web/device_config.py) | Persistent device inputs; no guest-state injection or NAND image rewriting. |
| [web/index.html](web/index.html) | 运行入口或运行实现，参数/用途见文件。 |
| [web/keyboard_input.js](web/keyboard_input.js) | 运行入口或运行实现，参数/用途见文件。 |
| [web/nand_files.py](web/nand_files.py) | Offline FAT16 file access for a complete NP560N1 NAND checkpoint. |
| [web/np560_web.py](web/np560_web.py) | Local Web bridge for the QEMU NP560+ machine. |
| [web/rom_bundle.py](web/rom_bundle.py) | Bind checked MP3/NPE ROM services to their actual image and firmware. |
| [web/styles.css](web/styles.css) | 运行入口或运行实现，参数/用途见文件。 |

## 自动测试、测试包装器与 C 参考程序（333）

| 文件 | 用途 |
| --- | --- |
| [np560_cpu_vmstate_test.c](np560_cpu_vmstate_test.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [np560_journal_faults.c](np560_journal_faults.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-aux.ps1](test-np560-aux.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-des.ps1](test-np560-des.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-driver.ps1](test-np560-driver.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-ecc-correction.ps1](test-np560-ecc-correction.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-ecc.ps1](test-np560-ecc.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-initializer-probe.ps1](test-np560-initializer-probe.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-keyboard.ps1](test-np560-keyboard.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-lcd.ps1](test-np560-lcd.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-memory-split.ps1](test-np560-memory-split.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-nand-rw.ps1](test-np560-nand-rw.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-nand.ps1](test-np560-nand.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-rom.ps1](test-np560-rom.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-runtime-overlays.ps1](test-np560-runtime-overlays.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-st7529.ps1](test-np560-st7529.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-system-boot.ps1](test-np560-system-boot.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-system-lifecycle.ps1](test-np560-system-lifecycle.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-system-web.ps1](test-np560-system-web.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560-web.ps1](test-np560-web.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test-np560.ps1](test-np560.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_antialias_reference.c](test_np560_mp3_antialias_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_dct32_reference.c](test_np560_mp3_dct32_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_hybrid_reference.c](test_np560_mp3_hybrid_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_imdct36_reference.c](test_np560_mp3_imdct36_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_intensity_reference.c](test_np560_mp3_intensity_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_requantize_reference.c](test_np560_mp3_requantize_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_scalefactors_reference.c](test_np560_mp3_scalefactors_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_sideinfo_reference.c](test_np560_mp3_sideinfo_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_spectrum_reference.c](test_np560_mp3_spectrum_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_stereo_reference.c](test_np560_mp3_stereo_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [test_np560_mp3_synthesis_reference.c](test_np560_mp3_synthesis_reference.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/np560_minimp3_direct.c](tests/np560_minimp3_direct.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/probe_np560_mpg123_reference.py](tests/probe_np560_mpg123_reference.py) | Independent installed libmpg123 reference; never linked into the emulator. |
| [tests/test_analyse_np560_app_catalog.py](tests/test_analyse_np560_app_catalog.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyse_np560_boot_contract.py](tests/test_analyse_np560_boot_contract.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyse_np560_direct_calls.py](tests/test_analyse_np560_direct_calls.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyse_np560_npe.py](tests/test_analyse_np560_npe.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyse_np560_nwf_format.py](tests/test_analyse_np560_nwf_format.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyse_np560_operation_catalog.py](tests/test_analyse_np560_operation_catalog.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyse_np560_resident_context.py](tests/test_analyse_np560_resident_context.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyse_np560_resource_reads.py](tests/test_analyse_np560_resource_reads.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyze_np560_ftl_map.py](tests/test_analyze_np560_ftl_map.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyze_np560_live_npe_sections.py](tests/test_analyze_np560_live_npe_sections.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_analyze_np560_runtime_code_sources.py](tests/test_analyze_np560_runtime_code_sources.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_audit_np560_overlay_mappings.py](tests/test_audit_np560_overlay_mappings.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_audit_np560_package_block.py](tests/test_audit_np560_package_block.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_build_np560_burn_harness.py](tests/test_build_np560_burn_harness.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_build_np560_factory_nand.py](tests/test_build_np560_factory_nand.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_build_np560_lirt_provision_firmware.py](tests/test_build_np560_lirt_provision_firmware.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_build_np560_minimal_nwf.py](tests/test_build_np560_minimal_nwf.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_build_np560_nand_rw_harness.py](tests/test_build_np560_nand_rw_harness.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_build_np560_reconstructed_rom.py](tests/test_build_np560_reconstructed_rom.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_build_np560_rom_skeleton.py](tests/test_build_np560_rom_skeleton.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_build_np560_stream_burn_harness.py](tests/test_build_np560_stream_burn_harness.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_build_np560_vma03_soc_rom.py](tests/test_build_np560_vma03_soc_rom.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_capture_np560_snapshot.py](tests/test_capture_np560_snapshot.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_compare_np560_data_segments.py](tests/test_compare_np560_data_segments.py) | Tests for read-only guest data-bank state comparison. |
| [tests/test_compare_np560_nand_journals.py](tests/test_compare_np560_nand_journals.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_diagnostic_cli_imports.py](tests/test_diagnostic_cli_imports.py) | Catch CLI imports broken by moving shared diagnostic helpers into tests. |
| [tests/test_dump_np560_qemu_bus.py](tests/test_dump_np560_qemu_bus.py) | Unit tests for the read-only NP560 QEMU bus dump utility. |
| [tests/test_ensure_np560_fat16_directories.py](tests/test_ensure_np560_fat16_directories.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_explore_np560_npe_map.py](tests/test_explore_np560_npe_map.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_finalize_np560_runtime_firmware.py](tests/test_finalize_np560_runtime_firmware.py) | Tests for converting one-shot provisioning PRGs into runtime PRGs. |
| [tests/test_import_np560_vendor_file.py](tests/test_import_np560_vendor_file.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_inject_np560_minimal_pim.py](tests/test_inject_np560_minimal_pim.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_inject_np560_npe_fat16.py](tests/test_inject_np560_npe_fat16.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_inspect_np560_media_sectors.py](tests/test_inspect_np560_media_sectors.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_merge_np560_matrix_routes.py](tests/test_merge_np560_matrix_routes.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_mirror_np560_runtime_patches.py](tests/test_mirror_np560_runtime_patches.py) | Tests for guest runtime-patch mirroring into source-pinned PRG copies. |
| [tests/test_monitor_np560_clock.py](tests/test_monitor_np560_clock.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_event_state.py](tests/test_monitor_np560_event_state.py) | Tests for the NP560 initialization/event-state delta monitor. |
| [tests/test_monitor_np560_file_records.py](tests/test_monitor_np560_file_records.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_game_draw.py](tests/test_monitor_np560_game_draw.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_lcd_segments.py](tests/test_monitor_np560_lcd_segments.py) | Unit tests for the read-only NP560 LCD annunciator monitor. |
| [tests/test_monitor_np560_modal_dispatch.py](tests/test_monitor_np560_modal_dispatch.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_npe_input_semantics.py](tests/test_monitor_np560_npe_input_semantics.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_npe_play_session.py](tests/test_monitor_np560_npe_play_session.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_provision.py](tests/test_monitor_np560_provision.py) | Tests for the NP560 provisioning monitor. |
| [tests/test_monitor_np560_render_object.py](tests/test_monitor_np560_render_object.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_resource_candidates.py](tests/test_monitor_np560_resource_candidates.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_root_metadata.py](tests/test_monitor_np560_root_metadata.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_start_menu.py](tests/test_monitor_np560_start_menu.py) | Tests for the NP560+ Start-key lifecycle monitor parsers. |
| [tests/test_monitor_np560_storage_geometry.py](tests/test_monitor_np560_storage_geometry.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_monitor_np560_web.py](tests/test_monitor_np560_web.py) | Tests for the compact NP560 Web diagnostic monitor. |
| [tests/test_mp3_capture_cost.py](tests/test_mp3_capture_cost.py) | Recording cost observations must preserve overlapping PCM and generations. |
| [tests/test_mp3_speed_window.py](tests/test_mp3_speed_window.py) | Check real speed-window boundaries without running or patching a guest. |
| [tests/test_np560_agu_validation.py](tests/test_np560_agu_validation.py) | Check R8/R10/R14 invalid circular modes halt before loads, without false positives. |
| [tests/test_np560_agu_writeback.py](tests/test_np560_agu_writeback.py) | Check ordinary AGU writeback uses pre-instruction modifier state. |
| [tests/test_np560_arena_release_mapping.py](tests/test_np560_arena_release_mapping.py) | Check the actual code bus before boot; do not mutate guest state. |
| [tests/test_np560_asr_shift_buffer.py](tests/test_np560_asr_shift_buffer.py) | Check ASR's SB reset, including the negative-count ASL branch. |
| [tests/test_np560_audio.py](tests/test_np560_audio.py) | Verify guest-written DAC PCM, mute, virtual time and original ramp code. |
| [tests/test_np560_audio_clock_delivery.py](tests/test_np560_audio_clock_delivery.py) | A finite guest-owned DAC buffer must retain the dedicated sample clock. |
| [tests/test_np560_audio_control_events.py](tests/test_np560_audio_control_events.py) | Bounded audio/HLE lifecycle evidence: guest writes, wrap, read-only, reset. |
| [tests/test_np560_audio_delivery_analysis.py](tests/test_np560_audio_delivery_analysis.py) | Offline guards for control coverage and distinct DTU/request counters. |
| [tests/test_np560_audio_fractional_clock.py](tests/test_np560_audio_fractional_clock.py) | Compile the actual device scheduler with a timer sink; no guest emulation. |
| [tests/test_np560_audio_mode_hle.py](tests/test_np560_audio_mode_hle.py) | Synthetic v7 parameter ABI only: no claim of implemented EQ DSP. |
| [tests/test_np560_audio_modes.py](tests/test_np560_audio_modes.py) | Original data extraction guards, not EQ processing or UI execution tests. |
| [tests/test_np560_audio_output.js](tests/test_np560_audio_output.js) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_audio_requests.py](tests/test_np560_audio_requests.py) | Original dedicated DAC request routes, separate from timer-driven audio. |
| [tests/test_np560_audio_state_ram.py](tests/test_np560_audio_state_ram.py) | Original audio initialization/setup and dispatcher must share F010 RAM. |
| [tests/test_np560_banked_tlb_boundary.py](tests/test_np560_banked_tlb_boundary.py) | Banked word crossing DS0/DS1: compare full and minimal, guest writes only. |
| [tests/test_np560_bit_binary_flags.py](tests/test_np560_bit_binary_flags.py) | DMCU BAND/BOR/BXOR/BCMP two-input flag truth tables. |
| [tests/test_np560_bit_sfr_addressing.py](tests/test_np560_bit_sfr_addressing.py) | Check the direct-SFR/bit-address contract used by original NP560 drivers. |
| [tests/test_np560_bitmap_allocation_size.py](tests/test_np560_bitmap_allocation_size.py) | Execute the unchanged original bitmap-size leaf, relocated outside aliases. |
| [tests/test_np560_build_wrapper.ps1](tests/test_np560_build_wrapper.ps1) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_burn_diagnostics.py](tests/test_np560_burn_diagnostics.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_burn_setup.py](tests/test_np560_burn_setup.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_clock_probe.py](tests/test_np560_clock_probe.py) | Clock probe must not navigate a still-booting guest. |
| [tests/test_np560_clock_protection.py](tests/test_np560_clock_protection.py) | CLKCON unlock/lock through guest instructions and original 24:FF92. |
| [tests/test_np560_code_coherence.py](tests/test_np560_code_coherence.py) | Guest-only executable-RAM writes across QEMU translation-page boundaries. |
| [tests/test_np560_control_observers.py](tests/test_np560_control_observers.py) | Check required fault/key diagnostics in full and minimal observer modes. |
| [tests/test_np560_cpu_vmstate.py](tests/test_np560_cpu_vmstate.py) | Link the production DMCU serializer to QEMU's existing VMState test libs. |
| [tests/test_np560_crit_boundary.py](tests/test_np560_crit_boundary.py) | A pending IRQ must be reconsidered when CRIT's instruction window ends. |
| [tests/test_np560_des.py](tests/test_np560_des.py) | Execute reconstructed resident 02:DEA6 against FIPS DES vectors. |
| [tests/test_np560_device_backup.py](tests/test_np560_device_backup.py) | Backup data preservation and refusal boundaries; no emulated game claims. |
| [tests/test_np560_device_config.py](tests/test_np560_device_config.py) | Check persistent-device selection and input protections, without guest writes. |
| [tests/test_np560_direct_menu_verifier.py](tests/test_np560_direct_menu_verifier.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_disasm.py](tests/test_np560_disasm.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_dpram_fastpath.py](tests/test_np560_dpram_fastpath.py) | DPRAM fast-port equivalence, including the adjacent real SFR boundary. |
| [tests/test_np560_dtu.py](tests/test_np560_dtu.py) | Check DMCU DTU transfers and the original NP560 buffer-refill driver. |
| [tests/test_np560_ecc.py](tests/test_np560_ecc.py) | Verify NP560 F20A/F20C/F20E paired-parity ECC in the guest data path. |
| [tests/test_np560_ecc_correction.py](tests/test_np560_ecc_correction.py) | Run the vendor's exact 51:6CB8 ECC corrector against injected faults. |
| [tests/test_np560_eq.c](tests/test_np560_eq.c) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_eq_capture.py](tests/test_np560_eq_capture.py) | Capture evidence checks: never bridge gaps or trust a stale artifact. |
| [tests/test_np560_eq_game_scene.py](tests/test_np560_eq_game_scene.py) | World movement must not be confused with screen position or scrolling. |
| [tests/test_np560_game_draw_trace_observer.py](tests/test_np560_game_draw_trace_observer.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_host_symbols.py](tests/test_np560_host_symbols.py) | Check ELF load translation independently of ASLR and nonzero segment offsets. |
| [tests/test_np560_host_time.py](tests/test_np560_host_time.py) | Check thread time parsing, identity guards, CPU/wall metrics and missing schedstat. |
| [tests/test_np560_icount_accounting.py](tests/test_np560_icount_accounting.py) | Count executed guest instructions, including dynamic early TB exits. |
| [tests/test_np560_icr_vectors.py](tests/test_np560_icr_vectors.py) | Exercise DMCU ICR software requests through guest-installed vector code. |
| [tests/test_np560_ignds_byte_lane.py](tests/test_np560_ignds_byte_lane.py) | Verify IGNDS preserves the DMCU high-byte-first SRAM byte lane. |
| [tests/test_np560_ignds_irq.py](tests/test_np560_ignds_irq.py) | IGNDS must mask CPU hardware interrupts through its memory instruction. |
| [tests/test_np560_initializer_probe.py](tests/test_np560_initializer_probe.py) | Run the unmodified nine-copy PRG initializer to its missing ROM tail. |
| [tests/test_np560_instruction_clock.py](tests/test_np560_instruction_clock.py) | Check the explicit one-cycle clock-domain baseline, not full CPU cycles. |
| [tests/test_np560_instruction_costs.py](tests/test_np560_instruction_costs.py) | Execute guest-authored A/B cycle and EMCR wait-state fixtures. |
| [tests/test_np560_internal_byte_lane.py](tests/test_np560_internal_byte_lane.py) | Verify DMCU byte operands use the high-byte-first word-bus lane. |
| [tests/test_np560_interrupt_nesting.py](tests/test_np560_interrupt_nesting.py) | Guest-driven priority/preemption, real RETI frames and repeat suspension. |
| [tests/test_np560_interrupt_psr.py](tests/test_np560_interrupt_psr.py) | Check architectural PSR words in DMCU interrupt and synthetic RETI frames. |
| [tests/test_np560_key_diagnostic.js](tests/test_np560_key_diagnostic.js) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_key_snapshot.py](tests/test_np560_key_snapshot.py) | Integration check of atomic QOM key input, without user firmware or NAND. |
| [tests/test_np560_key_transport.js](tests/test_np560_key_transport.js) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_keyboard.py](tests/test_np560_keyboard.py) | Verify Web/QOM keys traverse the legacy MMIO latch into guest code. |
| [tests/test_np560_keyboard_contact.js](tests/test_np560_keyboard_contact.js) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_keyboard_events.js](tests/test_np560_keyboard_events.js) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_lan_proxy.py](tests/test_np560_lan_proxy.py) | Exercise the TCP bridge locally without exposing a LAN listener. |
| [tests/test_np560_lcd_command_banks.py](tests/test_np560_lcd_command_banks.py) | Guest-MMIO checks of ST7529 EXT decoding and programmed gray registers. |
| [tests/test_np560_lcd_formats.py](tests/test_np560_lcd_formats.py) | Exercise ST7529 bus packing through guest MMIO, without NAND or HLE. |
| [tests/test_np560_lcd_partial.py](tests/test_np560_lcd_partial.py) | Guest-MMIO ST7529 partial display, retained RAM and status-register checks. |
| [tests/test_np560_lcd_polarity.py](tests/test_np560_lcd_polarity.py) | Check NP560 positive-glass output polarity without changing stored pixels. |
| [tests/test_np560_lcd_rmw.py](tests/test_np560_lcd_rmw.py) | ST7529 read pipeline and RMW via guest MMIO (datasheet pp20/45/46/63). |
| [tests/test_np560_lcd_row_mapping.py](tests/test_np560_lcd_row_mapping.py) | Regression tests for the NP560+ ST7529 visible-row contract. |
| [tests/test_np560_lcd_scan.py](tests/test_np560_lcd_scan.py) | Check ST7529 LI/CI output mapping with real guest MMIO and sparse pixels. |
| [tests/test_np560_live_browser_audio.js](tests/test_np560_live_browser_audio.js) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_live_browser_pointer.js](tests/test_np560_live_browser_pointer.js) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_loader_event_observer.py](tests/test_np560_loader_event_observer.py) | Source contracts for the status-2 NPE loader event observer. |
| [tests/test_np560_low51_entry_observer.py](tests/test_np560_low51_entry_observer.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_mac.py](tests/test_np560_mac.py) | DMCU register DSP arithmetic and unmodified original sample gain routines. |
| [tests/test_np560_memory_mac.py](tests/test_np560_memory_mac.py) | Original 0C:7142 64-word product loop and memory MAC bus/AGU boundaries. |
| [tests/test_np560_memory_split.py](tests/test_np560_memory_split.py) | Prove data writes cannot corrupt PRG/NOR instruction fetches. |
| [tests/test_np560_minimal_key_counters.py](tests/test_np560_minimal_key_counters.py) | Guest-authored repeated key-slot writes; public ACKs must survive minimal mode. |
| [tests/test_np560_mobivoice_adaptive.py](tests/test_np560_mobivoice_adaptive.py) | Pure checks for the candidate's self-feeding adaptive subframe loop. |
| [tests/test_np560_mobivoice_codebooks.py](tests/test_np560_mobivoice_codebooks.py) | Pure checks for first-stage candidate LSF codebook selection. |
| [tests/test_np560_mobivoice_codec_candidate.py](tests/test_np560_mobivoice_codec_candidate.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_mobivoice_corpus_probe.py](tests/test_np560_mobivoice_corpus_probe.py) | Guard reuse of an earlier differential before skipping corpus sections. |
| [tests/test_np560_mobivoice_decoder.py](tests/test_np560_mobivoice_decoder.py) | Owned candidate mode-5 PCM regressions using Tianjiang Fengyunlu frames. |
| [tests/test_np560_mobivoice_fields.py](tests/test_np560_mobivoice_fields.py) | Owned candidate-frame parser checks; no vendor DLL or NPE is bundled. |
| [tests/test_np560_mobivoice_fir.py](tests/test_np560_mobivoice_fir.py) | Pure fixed-point sample arithmetic tests without candidate binary. |
| [tests/test_np560_mobivoice_fixed.py](tests/test_np560_mobivoice_fixed.py) | Pure checks for fixed-pulse signs, index recurrence, and accumulation. |
| [tests/test_np560_mobivoice_history.py](tests/test_np560_mobivoice_history.py) | Pure checks for the candidate's 160-sample excitation history. |
| [tests/test_np560_mobivoice_interpolate.py](tests/test_np560_mobivoice_interpolate.py) | Pure synthetic checks for the owned candidate interpolation stage. |
| [tests/test_np560_mobivoice_lpc.py](tests/test_np560_mobivoice_lpc.py) | Pure checks for the candidate's ten-order LSF-to-LPC conversion. |
| [tests/test_np560_mobivoice_lsf.py](tests/test_np560_mobivoice_lsf.py) | Candidate intermediate-stage differential tests, never PCM compatibility claims. |
| [tests/test_np560_mobivoice_lsf_predict.py](tests/test_np560_mobivoice_lsf_predict.py) | Pure checks for the candidate's recursive ten-word LSF predictor. |
| [tests/test_np560_mobivoice_lsf_subframes.py](tests/test_np560_mobivoice_lsf_subframes.py) | Pure checks for two-subframe candidate LSF interpolation. |
| [tests/test_np560_mobivoice_mix.py](tests/test_np560_mobivoice_mix.py) | Pure checks for candidate Q14 gain and fixed-pulse feedback. |
| [tests/test_np560_mobivoice_pitch.py](tests/test_np560_mobivoice_pitch.py) | Pure pitch-code boundary checks for the owned candidate mapping. |
| [tests/test_np560_mobivoice_sp_decoder.py](tests/test_np560_mobivoice_sp_decoder.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_mobivoice_synthesis.py](tests/test_np560_mobivoice_synthesis.py) | Pure regression checks for the owned final candidate synthesis stage. |
| [tests/test_np560_mobivoice_tables.py](tests/test_np560_mobivoice_tables.py) | Checks for candidate mode-5 lookup values used by the owned stages. |
| [tests/test_np560_mp3_allocation.py](tests/test_np560_mp3_allocation.py) | Native MP3 allocation/pinning/free against the actual PRG heap functions. |
| [tests/test_np560_mp3_antialias.py](tests/test_np560_mp3_antialias.py) | Native antialias unit tests versus offline widened libmad and real formulas. |
| [tests/test_np560_mp3_channel_route.py](tests/test_np560_mp3_channel_route.py) | Execute the original post-decoder channel selector for all four flag inputs. |
| [tests/test_np560_mp3_dct32.py](tests/test_np560_mp3_dct32.py) | Full-width DMCU fast DCT versus independently executed pinned libmad C. |
| [tests/test_np560_mp3_decoder.py](tests/test_np560_mp3_decoder.py) | Real raw MP3 -> native bank-owned PCM API, no test-orchestrated stages. |
| [tests/test_np560_mp3_error_recovery.py](tests/test_np560_mp3_error_recovery.py) | Guest HLE error/release/reopen contract, not a player UI or audio test. |
| [tests/test_np560_mp3_factory.py](tests/test_np560_mp3_factory.py) | Original MP3 public entries own their memory and dispatch PRG callbacks. |
| [tests/test_np560_mp3_final_gate.py](tests/test_np560_mp3_final_gate.py) | Small guest-only callers for the v5 EOF gate; no NAND, Web or host RAM writes. |
| [tests/test_np560_mp3_frame.py](tests/test_np560_mp3_frame.py) | One autonomous guest run across raw MP3 frames, offline entropy oracle. |
| [tests/test_np560_mp3_header.py](tests/test_np560_mp3_header.py) | Execute the original MPEG header parser to constrain the missing MP3 ABI. |
| [tests/test_np560_mp3_hle_codec.py](tests/test_np560_mp3_hle_codec.py) | Standalone HLE codec kernel checks, NOT an integrated QEMU/player test. |
| [tests/test_np560_mp3_hle_final.py](tests/test_np560_mp3_hle_final.py) | Offline bounded EOF codec checks; not a factory-player or DAC test. |
| [tests/test_np560_mp3_hle_gate.py](tests/test_np560_mp3_hle_gate.py) | Opt-in MP3 HLE gate, strict unknown holes, ABI, and device reset checks. |
| [tests/test_np560_mp3_hle_profile.py](tests/test_np560_mp3_hle_profile.py) | Check build preset selection without firmware or native codec execution. |
| [tests/test_np560_mp3_huffman.py](tests/test_np560_mp3_huffman.py) | Run the new Layer III entropy core as DMCU instructions, without NAND/HLE. |
| [tests/test_np560_mp3_hybrid.py](tests/test_np560_mp3_hybrid.py) | Native hybrid unit and two-granule overlap tests; not PCM/player tests. |
| [tests/test_np560_mp3_imdct36.py](tests/test_np560_mp3_imdct36.py) | Fast long IMDCT: native vs independent pinned-C topology and mathematics. |
| [tests/test_np560_mp3_intensity.py](tests/test_np560_mp3_intensity.py) | QEMU joint stereo against adapted offline libmad; no PCM/player. |
| [tests/test_np560_mp3_multiply.py](tests/test_np560_mp3_multiply.py) | Full-width native MP3 multiply helpers against independent integer products. |
| [tests/test_np560_mp3_pcm_copy.py](tests/test_np560_mp3_pcm_copy.py) | Version-4..6 software copy: bytes, guest mute, ABI and invalid-write guards. |
| [tests/test_np560_mp3_rate_matrix.py](tests/test_np560_mp3_rate_matrix.py) | Exercise the real HLE kernel at all nine MP3 sample rates, mono/stereo. |
| [tests/test_np560_mp3_requantize.py](tests/test_np560_mp3_requantize.py) | Native Q28 requantization against pinned offline C references, NOT PCM. |
| [tests/test_np560_mp3_reservoir.py](tests/test_np560_mp3_reservoir.py) | Native sideinfo -> reservoir checks, with raw-history byte oracle. |
| [tests/test_np560_mp3_ring.py](tests/test_np560_mp3_ring.py) | Real PRG word producer + parser + ROM ring adapter -> captured native PCM. |
| [tests/test_np560_mp3_ring_control.py](tests/test_np560_mp3_ring_control.py) | CRC, resync, ring fullness, odd cursors and consumption carry in guest. |
| [tests/test_np560_mp3_scalefactors.py](tests/test_np560_mp3_scalefactors.py) | Native scalefactor fields and bit consumption vs original libmad functions. |
| [tests/test_np560_mp3_session.py](tests/test_np560_mp3_session.py) | Owned native MP3 session, original PCM buffers and complete heap cleanup. |
| [tests/test_np560_mp3_sideinfo.py](tests/test_np560_mp3_sideinfo.py) | Compare native DMCU sideinfo to the pinned, unmodified libmad function. |
| [tests/test_np560_mp3_spectrum.py](tests/test_np560_mp3_spectrum.py) | Compare native quantized spectra to offline libmad entropy + FFmpeg regions. |
| [tests/test_np560_mp3_stereo.py](tests/test_np560_mp3_stereo.py) | Native MS/reorder versus offline C; not an MP3 player/PCM test. |
| [tests/test_np560_mp3_synthesis.py](tests/test_np560_mp3_synthesis.py) | Native PCM synthesis versus integer, mathematical and libmad references. |
| [tests/test_np560_mp3_terminal_prefixes.py](tests/test_np560_mp3_terminal_prefixes.py) | Check EOF prefixes against complete-frame PCM and failed-call rollback. |
| [tests/test_np560_multiply_registers.py](tests/test_np560_multiply_registers.py) | DMCU MUL fractional mode, MUL/UMUL V, and register preservation. |
| [tests/test_np560_nand.py](tests/test_np560_nand.py) | Integration check for vendor-burner -> guest ROM -> QEMU NAND DMA. |
| [tests/test_np560_nand_checkpoint.py](tests/test_np560_nand_checkpoint.py) | Verify complete NP560 NAND data/OOB checkpoint save and restore. |
| [tests/test_np560_nand_compaction.py](tests/test_np560_nand_compaction.py) | Check atomic journal compaction using real guest NAND commands. |
| [tests/test_np560_nand_export_stream.py](tests/test_np560_nand_export_stream.py) | Check bounded-memory NAND export/load and preservation on a short host write. |
| [tests/test_np560_nand_files.py](tests/test_np560_nand_files.py) | Offline NAND file bridge regression tests (small synthetic FAT16 volume). |
| [tests/test_np560_nand_journal.py](tests/test_np560_nand_journal.py) | NAND durability after SIGKILL, using only guest controller transactions. |
| [tests/test_np560_nand_rw.py](tests/test_np560_nand_rw.py) | Exercise reconstructed BBF6/BCC6/BDD6 entirely from guest code. |
| [tests/test_np560_native_buff_restore.py](tests/test_np560_native_buff_restore.py) | Execute the original battle zero-counter restore block, not an entire round. |
| [tests/test_np560_natural_menu_verifier.py](tests/test_np560_natural_menu_verifier.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_nested_repeat.py](tests/test_np560_nested_repeat.py) | Independent REP/SRC and REPB/RC, including the original map scroll body. |
| [tests/test_np560_npe_audio_corpus.py](tests/test_np560_npe_audio_corpus.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_npe_audio_live.py](tests/test_np560_npe_audio_live.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_npe_audio_rom_hole.py](tests/test_np560_npe_audio_rom_hole.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_npe_codec_subprocess.py](tests/test_np560_npe_codec_subprocess.py) | Launch the DLL-free NPE codec service and exchange a real Unix-socket frame. |
| [tests/test_np560_npe_codec_trace.py](tests/test_np560_npe_codec_trace.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_npe_codec_transport.py](tests/test_np560_npe_codec_transport.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_npe_dac_reference.py](tests/test_np560_npe_dac_reference.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_npe_format_dispatch_observer.py](tests/test_np560_npe_format_dispatch_observer.py) | Source contracts for the bounded v752 NPE format-dispatch observer. |
| [tests/test_np560_npe_hle_rom.py](tests/test_np560_npe_hle_rom.py) | Only the verified NPE service returns may change in the experimental ROM. |
| [tests/test_np560_npe_loop_boundary.py](tests/test_np560_npe_loop_boundary.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_npe_stream_window.py](tests/test_np560_npe_stream_window.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_nwf_header.py](tests/test_np560_nwf_header.py) | Validate an experimental NWF header with the exact resident guest DES. |
| [tests/test_np560_observer_sites.py](tests/test_np560_observer_sites.py) | Exhaustively check indexed observer dispatch against the archived linear map. |
| [tests/test_np560_original_calendar.py](tests/test_np560_original_calendar.py) | Original month-length code with a diagnostic month table; not RTC hardware. |
| [tests/test_np560_original_clock_tick.py](tests/test_np560_original_clock_tick.py) | Execute the original clock-tail branches, not the complete timer or RTC. |
| [tests/test_np560_original_key_debounce.py](tests/test_np560_original_key_debounce.py) | Execute the original key gate; proves scan-count semantics, not real-time polling. |
| [tests/test_np560_original_key_modes.py](tests/test_np560_original_key_modes.py) | Execute factory key-table selection and M26 state transitions, not LCD or debounce. |
| [tests/test_np560_original_mp3_seek_sync.py](tests/test_np560_original_mp3_seek_sync.py) | Run byte-exact factory sync search on a verified LONG22 seek window. |
| [tests/test_np560_overlay_map.py](tests/test_np560_overlay_map.py) | Tests for the reconstructed/QEMU overlay preflight map. |
| [tests/test_np560_owned_npe_codec.py](tests/test_np560_owned_npe_codec.py) | Opt-in NPE decoder launch arguments must not change the default path. |
| [tests/test_np560_path_component.py](tests/test_np560_path_component.py) | Run the exact NP560 path-component parser in a tiny QEMU harness. |
| [tests/test_np560_pc_wrap.py](tests/test_np560_pc_wrap.py) | Segment-local PC rollover: instruction fetch, calls and repeat, no NAND. |
| [tests/test_np560_perf_samples.py](tests/test_np560_perf_samples.py) | Check stopped perf record decoding, loss accounting and corrupt input rejection. |
| [tests/test_np560_player_rom_build.py](tests/test_np560_player_rom_build.py) | Fresh PRG-to-player pipeline: input identity, refusal, source isolation and output. |
| [tests/test_np560_pointer_input.js](tests/test_np560_pointer_input.js) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_postincrement_load.py](tests/test_np560_postincrement_load.py) | MOV destination / source-pointer aliases: operand fetch precedes writeback. |
| [tests/test_np560_qmp_target.py](tests/test_np560_qmp_target.py) | Verify standard target/CPU queries do not abort DMCU, paused or running. |
| [tests/test_np560_repeat_legality.py](tests/test_np560_repeat_legality.py) | REP must reject forbidden targets before their architectural side effects. |
| [tests/test_np560_resident_code_overlay.py](tests/test_np560_resident_code_overlay.py) | Verify the evidenced 05:2286 resident overlay is writable executable RAM. |
| [tests/test_np560_resident_data.py](tests/test_np560_resident_data.py) | VMA03 resident ROM data reads and writable-memory boundaries. |
| [tests/test_np560_resource_pair_release_observer.py](tests/test_np560_resource_pair_release_observer.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_resource_trace.py](tests/test_np560_resource_trace.py) | Resource trace entry/stack tests; synthetic RETS body, not resource decoding. |
| [tests/test_np560_rom_api.py](tests/test_np560_rom_api.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_rom_bundle.py](tests/test_np560_rom_bundle.py) | ROM bundle integrity and argument binding; no guest or NAND writes. |
| [tests/test_np560_runtime_overlays.py](tests/test_np560_runtime_overlays.py) | Verify both vendor initializer chains and recovered runtime overlays. |
| [tests/test_np560_seek_fixture.py](tests/test_np560_seek_fixture.py) | Keep the seek control explicit and non-destructive. |
| [tests/test_np560_seek_history.py](tests/test_np560_seek_history.py) | Reject late, unbounded or unexplained loss; don't erase raw failures. |
| [tests/test_np560_settings_event_observer.py](tests/test_np560_settings_event_observer.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_settings_input_dispatch_observer.py](tests/test_np560_settings_input_dispatch_observer.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_sfr_device_lock.py](tests/test_np560_sfr_device_lock.py) | Check BQL ownership at actual timer/DAC register callbacks using GDB. |
| [tests/test_np560_shift_equivalence.py](tests/test_np560_shift_equivalence.py) | Compare guest shifts with the former bit-at-a-time semantics, all byte counts. |
| [tests/test_np560_software_reset.py](tests/test_np560_software_reset.py) | Run original USB-loader RESET tail; preserve RAM across a guest SoC reset. |
| [tests/test_np560_software_trap.py](tests/test_np560_software_trap.py) | Guest TRAP vectors, RAM frames, nesting and strict ROM-hole separation. |
| [tests/test_np560_stack_byte_alias.py](tests/test_np560_stack_byte_alias.py) | Verify bank-zero byte pointers alias unbanked R11 stack-byte operands. |
| [tests/test_np560_stack_mmio_alias.py](tests/test_np560_stack_mmio_alias.py) | Verify DMCU far-call frames bypass an overlapping board MMIO window. |
| [tests/test_np560_system_boot.py](tests/test_np560_system_boot.py) | Boot the recovered NP560+ guest to its native keyboard event loop. |
| [tests/test_np560_system_nand_build.py](tests/test_np560_system_nand_build.py) | Fresh NAND orchestration must refuse unsafe inputs and retain failure evidence. |
| [tests/test_np560_timebase.py](tests/test_np560_timebase.py) | Verify the actual TBC/TBICR and software-owned countdown words. |
| [tests/test_np560_timer2.py](tests/test_np560_timer2.py) | Check real Timer2 expiry, PLL register coherence and virtual-clock pause. |
| [tests/test_np560_timers.py](tests/test_np560_timers.py) | Exercise Timer0/1/2 and the original two-channel DAC transport setup. |
| [tests/test_np560_transport_controls.py](tests/test_np560_transport_controls.py) | Reject incomplete player transport observations, even when keys were delivered. |
| [tests/test_np560_trap_strict.py](tests/test_np560_trap_strict.py) | Explicit reconstructed-ROM holes must stop before architectural TRAP. |
| [tests/test_np560_unbanked_sfr_trace.py](tests/test_np560_unbanked_sfr_trace.py) | Verify the observer-only IGNDS SFR inventory and unknown-write ring. |
| [tests/test_np560_unbanked_tlb.py](tests/test_np560_unbanked_tlb.py) | Guest-only bank/IGNDS transitions, including DS writes inside IGNDS. |
| [tests/test_np560_upd.py](tests/test_np560_upd.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_usb_transport.py](tests/test_np560_usb_transport.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_np560_web_frontend.py](tests/test_np560_web_frontend.py) | Pin the browser keyboard to the recovered NP560+ hardware matrix. |
| [tests/test_np560_web_lifecycle.py](tests/test_np560_web_lifecycle.py) | Check lifecycle evidence and failure cleanup without touching a live guest. |
| [tests/test_np560_web_speed.py](tests/test_np560_web_speed.py) | Fast Web mode must not change clocks or suppress full diagnostic APIs. |
| [tests/test_np560_x0_ring.py](tests/test_np560_x0_ring.py) | Original audio ring writer and X0 circular postincrement, no NAND/HLE. |
| [tests/test_np560_y_pointer.py](tests/test_np560_y_pointer.py) | DMCU ordinary Y-pointer accesses must use internal Y-RAM, not DS banks. |
| [tests/test_patch_np560_application_region_extra_installer.py](tests/test_patch_np560_application_region_extra_installer.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_direct_manager_onto_recovered_rom.py](tests/test_patch_np560_direct_manager_onto_recovered_rom.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_embedded_menu_result_record_parser.py](tests/test_patch_np560_embedded_menu_result_record_parser.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_mask_rom_resource.py](tests/test_patch_np560_mask_rom_resource.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_menu_hardware_bit_wrappers.py](tests/test_patch_np560_menu_hardware_bit_wrappers.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_menu_list_item_set_installer.py](tests/test_patch_np560_menu_list_item_set_installer.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_menu_pointer_index_installer.py](tests/test_patch_np560_menu_pointer_index_installer.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_menu_result_record_parser.py](tests/test_patch_np560_menu_result_record_parser.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_menu_runtime_subinstallers.py](tests/test_patch_np560_menu_runtime_subinstallers.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_relocated_menu_runtime_installers.py](tests/test_patch_np560_relocated_menu_runtime_installers.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_resident_bad_block_helper.py](tests/test_patch_np560_resident_bad_block_helper.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_resident_event_e0_handler.py](tests/test_patch_np560_resident_event_e0_handler.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_resident_menu_record_decoder.py](tests/test_patch_np560_resident_menu_record_decoder.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_resident_msb_helper.py](tests/test_patch_np560_resident_msb_helper.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_resident_result_object_alloc.py](tests/test_patch_np560_resident_result_object_alloc.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_resident_storage_unit_init.py](tests/test_patch_np560_resident_storage_unit_init.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_rom01_application_cursor_range.py](tests/test_patch_np560_rom01_application_cursor_range.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_rom01_application_result_list_create.py](tests/test_patch_np560_rom01_application_result_list_create.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_rom01_application_result_object_children.py](tests/test_patch_np560_rom01_application_result_object_children.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_rom01_application_result_object_init.py](tests/test_patch_np560_rom01_application_result_object_init.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_rom01_application_result_record_match.py](tests/test_patch_np560_rom01_application_result_record_match.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_rom01_application_result_scan_chain.py](tests/test_patch_np560_rom01_application_result_scan_chain.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_rom01_late_result_table.py](tests/test_patch_np560_rom01_late_result_table.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_rom01_modal_callback_closure.py](tests/test_patch_np560_rom01_modal_callback_closure.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_rom01_modal_foreground_object.py](tests/test_patch_np560_rom01_modal_foreground_object.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_patch_np560_words.py](tests/test_patch_np560_words.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_preprocess_np560_nand.py](tests/test_preprocess_np560_nand.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_preprocess_np560_ui.py](tests/test_preprocess_np560_ui.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_probe_np560_audio_cpu_window.py](tests/test_probe_np560_audio_cpu_window.py) | Accounting invariants for the read-only live audio CPU probe. |
| [tests/test_probe_np560_checkpoint_boot.py](tests/test_probe_np560_checkpoint_boot.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_probe_np560_code_write.py](tests/test_probe_np560_code_write.py) | Positive control: a diagnostic guest must trip the host RAM write watch. |
| [tests/test_probe_np560_matrix_route.py](tests/test_probe_np560_matrix_route.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_probe_np560_npe_action_target.py](tests/test_probe_np560_npe_action_target.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_probe_np560_npe_input_combinations.py](tests/test_probe_np560_npe_input_combinations.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_probe_np560_npe_object_action.py](tests/test_probe_np560_npe_object_action.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_probe_np560_npe_speex.py](tests/test_probe_np560_npe_speex.py) | Tests for NPE fixed-record extraction used by the codec probe. |
| [tests/test_probe_np560_npe_unbanked_sfr.py](tests/test_probe_np560_npe_unbanked_sfr.py) | Unit tests for the NPE unbanked-SFR differential probe. |
| [tests/test_probe_np560_runtime.py](tests/test_probe_np560_runtime.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_probe_np560_tjfy_encounter.py](tests/test_probe_np560_tjfy_encounter.py) | The bounded Tianjiang walk must read the guest's actual map/battle mode. |
| [tests/test_publish_np560_resource_persistence_writer.py](tests/test_publish_np560_resource_persistence_writer.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_search_np560_live_memory.py](tests/test_search_np560_live_memory.py) | Unit tests for exact live-memory search helpers. |
| [tests/test_seed_np560_factory_bootstrap.py](tests/test_seed_np560_factory_bootstrap.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_seed_np560_factory_clock.py](tests/test_seed_np560_factory_clock.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_seed_np560_factory_selector.py](tests/test_seed_np560_factory_selector.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_seed_np560_factory_userinfo.py](tests/test_seed_np560_factory_userinfo.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_triage_np560_invalid_return.py](tests/test_triage_np560_invalid_return.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_verify_np560_burn_payload.py](tests/test_verify_np560_burn_payload.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_verify_np560_toolbar_frames.py](tests/test_verify_np560_toolbar_frames.py) | 测试/参考实现；依赖及运行参数见文件。 |
| [tests/test_watch_np560_code_sources.py](tests/test_watch_np560_code_sources.py) | 测试/参考实现；依赖及运行参数见文件。 |

## 逆向分析、反汇编与格式研究（44）

| 文件 | 用途 |
| --- | --- |
| [analyse_np560_app_catalog.py](analyse_np560_app_catalog.py) | Recover the NP560+ V3.80 resident menu catalogue and event dispatcher. |
| [analyse_np560_boot_contract.py](analyse_np560_boot_contract.py) | Verify the NP560+ boot contract recovered from the shipped images. |
| [analyse_np560_direct_calls.py](analyse_np560_direct_calls.py) | Index direct DMCU calls in an NP560 program image. |
| [analyse_np560_first_return_state.py](analyse_np560_first_return_state.py) | Capture NP560+ state at the first bootstrap-to-resident return. |
| [analyse_np560_npe.py](analyse_np560_npe.py) | Inspect real NP560 ``NP560 RPG2.1`` game containers. |
| [analyse_np560_nwf_format.py](analyse_np560_nwf_format.py) | Recover and verify the NP560+ V3.80 NEPLAYER/NWF file contract. |
| [analyse_np560_operation_catalog.py](analyse_np560_operation_catalog.py) | Recover the NP560+ file-browser operation catalogue from V3.80. |
| [analyse_np560_resident_context.py](analyse_np560_resident_context.py) | Extract the NP560 resident outer-context contract from DMCU listings. |
| [analyse_np560_resource_reads.py](analyse_np560_resource_reads.py) | Classify calls to the recovered NP560 mask-ROM byte reader. |
| [analyse_np560_selector_contract.py](analyse_np560_selector_contract.py) | Compare exact NP560+ scheduler-return state for events 82/83/85. |
| [analyze_np560_audio_delivery.py](analyze_np560_audio_delivery.py) | Align recorded DAC WAV windows with same-packet request counters (read-only). |
| [analyze_np560_audio_modes.py](analyze_np560_audio_modes.py) | Extract original audio-mode data; does not infer EQ frequencies or implement DSP. |
| [analyze_np560_ecc_checkpoint.py](analyze_np560_ecc_checkpoint.py) | Validate every stored NP560 sector ECC descriptor in a NAND checkpoint. |
| [analyze_np560_eq_capture.py](analyze_np560_eq_capture.py) | Measure contiguous normal/EQ DAC captures; not a factory EQ equivalence test. |
| [analyze_np560_ftl_block.py](analyze_np560_ftl_block.py) | Inspect one physical FTL/metadata block in an NP560 NAND checkpoint. |
| [analyze_np560_ftl_map.py](analyze_np560_ftl_map.py) | Build a repeatable NP560 NAND FTL-tail and logical-image correlation map. |
| [analyze_np560_host_samples.py](analyze_np560_host_samples.py) | Symbolize sampled QEMU host IPs using recorded maps and ELF PT_LOAD segments. |
| [analyze_np560_lcd_alignment.py](analyze_np560_lcd_alignment.py) | Compare an NP560 packed framebuffer with the visible ST7529 pixels. |
| [analyze_np560_live_npe_sections.py](analyze_np560_live_npe_sections.py) | Locate live NPE section pointers and their DMCU code consumers. |
| [analyze_np560_npe_audio_corpus.py](analyze_np560_npe_audio_corpus.py) | Inventory NPE sound candidates without decoding or trimming their bytes. |
| [analyze_np560_payload_mapping.py](analyze_np560_payload_mapping.py) | Locate NP560 update-payload bytes in a complete NAND checkpoint. |
| [analyze_np560_pcm_reference.py](analyze_np560_pcm_reference.py) | Compare captured DAC WAV with explicit raw PCM16 reference change order. |
| [analyze_np560_runtime_code_sources.py](analyze_np560_runtime_code_sources.py) | Compare executed NP560 instructions with recovered linked PRG sources. |
| [analyze_np560_toolbar_pipeline.py](analyze_np560_toolbar_pipeline.py) | Render and compare each byte/nibble interpretation of the NP560 toolbar. |
| [analyze_np560_top_menu_glyphs.py](analyze_np560_top_menu_glyphs.py) | Compare the NP560 root-menu labels with the resident 12x12 font table. |
| [audit_np560_control_observer.py](audit_np560_control_observer.py) | Inventory the control observer's writes/calls using a C syntax tree. |
| [audit_np560_overlay_aliases.py](audit_np560_overlay_aliases.py) | Cross-check reconstructed-ROM overlays against QEMU executable aliases. |
| [audit_np560_overlay_mappings.py](audit_np560_overlay_mappings.py) | Audit reconstructed high-bank overlays on the QEMU code bus. |
| [audit_np560_package_block.py](audit_np560_package_block.py) | Audit an explicit package-backed NAND block's byte lanes. |
| [compare_np560_data_segments.py](compare_np560_data_segments.py) | Find stable guest bytes distinguishing two NPE audio states. |
| [compare_np560_nand_journals.py](compare_np560_nand_journals.py) | Compare final programmed NP560 NAND pages from two journals of one seed. |
| [disassemble_pe_x86.py](disassemble_pe_x86.py) | Disassemble a virtual-address range from a PE32 x86 executable. |
| [extract_np560_cybervoice_evidence.py](extract_np560_cybervoice_evidence.py) | Recover independently CRC-checked Wise members from the archived ZIP prefix. |
| [extract_np560_mobivoice_codec_candidate.py](extract_np560_mobivoice_codec_candidate.py) | Statically recover CYBIT MobiVoice decoder DLLs from one archived Wise installer. |
| [inspect_np560_media_sectors.py](inspect_np560_media_sectors.py) | Locate and classify MBR/FAT boot sectors in an NP560 NAND checkpoint. |
| [np560_aspack_compat.h](np560_aspack_compat.h) | 用途与参数见源文件。 |
| [np560_aux_disasm.py](np560_aux_disasm.py) | Disassemble an auxiliary NP560+ big-endian 16-bit word image. |
| [np560_disasm.py](np560_disasm.py) | Static disassembler for the King Billion 16-bit DMCU used by NP560+. |
| [np560_upd.py](np560_upd.py) | Inspect the block layout used by Noah NP560+ ``.upd`` packages. |
| [preprocess_np560_nand.py](preprocess_np560_nand.py) | Index NP560 NAND checkpoints or MASKROM streams and find guest data. |
| [preprocess_np560_ui.py](preprocess_np560_ui.py) | Preprocess the exact NP560 foreground/UI reverse-engineering slice. |
| [scan_np560_call_sites.py](scan_np560_call_sites.py) | Find raw DMCU SCALL sites and recover instruction context around them. |
| [scan_np560_mpeg_tables.py](scan_np560_mpeg_tables.py) | Read-only, representation-bounded MPEG table search in original NP560 files. |
| [unpack_np560_aspack.c](unpack_np560_aspack.c) | 用途与参数见源文件。 |

## 运行时调试、采样、交互探针与性能测量（89）

| 文件 | 用途 |
| --- | --- |
| [benchmark_np560_cpu_kernel.py](benchmark_np560_cpu_kernel.py) | Fixed guest work; no debugger, NAND, or injected guest state. |
| [benchmark_np560_web_speed.py](benchmark_np560_web_speed.py) | Compare observer overhead with unchanged guest timing and boot inputs. |
| [capture_np560_data_segments.py](capture_np560_data_segments.py) | Capture raw guest data-bank bytes from an isolated NP560 Web instance. |
| [capture_np560_lcd.py](capture_np560_lcd.py) | Capture the current NP560 web LCD frame as a PNG image. |
| [capture_np560_native_buffers.py](capture_np560_native_buffers.py) | Capture the NP560 LCD, native framebuffers, and root-entry snapshots. |
| [capture_np560_native_framebuffer.py](capture_np560_native_framebuffer.py) | Capture the guest's packed 4-bit NP560 framebuffer as a PNG. |
| [capture_np560_snapshot.py](capture_np560_snapshot.py) | Capture an NP560 Web/QEMU LCD frame and compact diagnostic sidecar. |
| [capture_np560_web_frame.py](capture_np560_web_frame.py) | Capture the native ST7529 frame exposed by the NP560 Web bridge. |
| [dump_np560_live_range.py](dump_np560_live_range.py) | Disassemble a read-only physical-memory snapshot from NP560 Web/QEMU. |
| [dump_np560_program_range.py](dump_np560_program_range.py) | Linearly disassemble selected ranges from an NP560 program image. |
| [dump_np560_qemu_bus.py](dump_np560_qemu_bus.py) | Read exact NP560 QEMU code-bus words or internal SRAM through GDB. |
| [dump_np560_range.py](dump_np560_range.py) | Linearly disassemble one or more physical ranges from NP560.PRG. |
| [dump_np560_runtime_range.py](dump_np560_runtime_range.py) | Linearly disassemble a physical range exposed by the NP560 web API. |
| [explore_np560_npe_map.py](explore_np560_npe_map.py) | Explore the running native NPE map using original movement feedback. |
| [merge_np560_matrix_routes.py](merge_np560_matrix_routes.py) | Merge segmented NP560+ matrix probes into one auditable 64-key report. |
| [monitor_np560_bitmap_nand.py](monitor_np560_bitmap_nand.py) | Capture NAND history at each new root bitmap-transfer count. |
| [monitor_np560_clock.py](monitor_np560_clock.py) | Capture correlated NP560 guest/LCD buffers whenever the clock changes. |
| [monitor_np560_event_state.py](monitor_np560_event_state.py) | Print only NP560 initialization/event-state changes and their writers. |
| [monitor_np560_file_records.py](monitor_np560_file_records.py) | Print concise NP560 directory-record decisions from the Web endpoint. |
| [monitor_np560_game_draw.py](monitor_np560_game_draw.py) | Monitor native NPE map-draw transactions through the read-only Web API. |
| [monitor_np560_hardware_init_return.py](monitor_np560_hardware_init_return.py) | Compactly monitor the NP560 hardware-init far return frame via Web/QEMU. |
| [monitor_np560_lcd_segments.py](monitor_np560_lcd_segments.py) | Monitor the NP560+ factory LCD annunciator buffer without mutating QEMU. |
| [monitor_np560_modal_dispatch.py](monitor_np560_modal_dispatch.py) | Monitor the bounded Game World modal-event decoder trace. |
| [monitor_np560_npe_input_semantics.py](monitor_np560_npe_input_semantics.py) | Measure native NP560+ NPE long-press behavior through the real matrix. |
| [monitor_np560_npe_play_session.py](monitor_np560_npe_play_session.py) | Run a bounded native NPE play session and prove the guest exit path. |
| [monitor_np560_provision.py](monitor_np560_provision.py) | Monitor NP560 guest-native provisioning and its startup frame guard. |
| [monitor_np560_render_object.py](monitor_np560_render_object.py) | Monitor the bounded Game World render-object diagnostic from Web/QEMU. |
| [monitor_np560_resource_candidates.py](monitor_np560_resource_candidates.py) | Stop at the first resource-range candidate selected after a valid CAFE record. |
| [monitor_np560_root_metadata.py](monitor_np560_root_metadata.py) | Monitor NP560 root-directory metadata writes through the Web endpoint. |
| [monitor_np560_start_menu.py](monitor_np560_start_menu.py) | Verify the NP560+ physical Start-key lifecycle on a running Web/QEMU. |
| [monitor_np560_storage_geometry.py](monitor_np560_storage_geometry.py) | Monitor NP560 NAND/FTL geometry changes without mutating the emulator. |
| [monitor_np560_web.py](monitor_np560_web.py) | Watch an NP560 Web/QEMU run and capture the first useful outcome. |
| [probe-np560-burn.ps1](probe-np560-burn.ps1) | 用途与参数见源文件。 |
| [probe_np560_audio_cpu_window.py](probe_np560_audio_cpu_window.py) | Read-only per-process CPU and device-audio timing for an isolated Web run. |
| [probe_np560_checkpoint_boot.py](probe_np560_checkpoint_boot.py) | Cold-boot an isolated NAND checkpoint without keys, patches or persistence. |
| [probe_np560_clock_progress.py](probe_np560_clock_progress.py) | Observe clock progression in an owned instance, optionally with an isolated journal. |
| [probe_np560_code_write.py](probe_np560_code_write.py) | Capture the first host RAM write to a specified guest code word. |
| [probe_np560_cpu_cost.py](probe_np560_cpu_cost.py) | Bounded CPU throughput and optional read-only host stack sampling. |
| [probe_np560_eq_web_bundle.py](probe_np560_eq_web_bundle.py) | Owned real Web launch for a selected default-v6 or experimental-v8 ROM bundle. |
| [probe_np560_hero_equipment.py](probe_np560_hero_equipment.py) | Inspect Hero's equipment through native slot-three load on an owned instance. |
| [probe_np560_key_duration.py](probe_np560_key_duration.py) | Bounded physical-contact experiment on an owned emulator's desktop. |
| [probe_np560_live_perf.py](probe_np560_live_perf.py) | Sample the vCPU of an explicitly owned, live NP560 Web run. |
| [probe_np560_matrix_route.py](probe_np560_matrix_route.py) | Replay a bounded NP560+ physical-matrix route through the Web bridge. |
| [probe_np560_menu_short_press.py](probe_np560_menu_short_press.py) | Reproduce native menu input with wall-clock physical holds in an owned QEMU. |
| [probe_np560_mobivoice_corpus.py](probe_np560_mobivoice_corpus.py) | Differentially check each distinct local NPE sound section once. |
| [probe_np560_mobivoice_fir.py](probe_np560_mobivoice_fir.py) | Check an owned candidate sample dot product against isolated x86 code. |
| [probe_np560_mobivoice_history.py](probe_np560_mobivoice_history.py) | Check the candidate's excitation history against a zero-seeded model. |
| [probe_np560_mobivoice_interpolate.py](probe_np560_mobivoice_interpolate.py) | Compare owned fixed-point interpolation with isolated candidate x86 code. |
| [probe_np560_mobivoice_lpc.py](probe_np560_mobivoice_lpc.py) | Differential-test owned LSF-to-LPC conversion against isolated x86 code. |
| [probe_np560_mobivoice_lsf_step.py](probe_np560_mobivoice_lsf_step.py) | Differentially check one owned candidate preparation step against local DLL. |
| [probe_np560_mobivoice_owned_decoder.py](probe_np560_mobivoice_owned_decoder.py) | Compare every format-13 NPE sound section with the isolated codec candidate. |
| [probe_np560_mobivoice_pitch.py](probe_np560_mobivoice_pitch.py) | Exhaustively compare owned pitch-code mapping with isolated candidate x86. |
| [probe_np560_mobivoice_sp_decoder.py](probe_np560_mobivoice_sp_decoder.py) | Emulate the archived CYBIT mv_sp.dll on NPE frame candidates, without native DLL execution. |
| [probe_np560_mobivoice_synthesis.py](probe_np560_mobivoice_synthesis.py) | Differentially test the owned final synthesis filter with synthetic data. |
| [probe_np560_mp3_player_heap.py](probe_np560_mp3_player_heap.py) | Observe the real player's live heap and optional native codec integration. |
| [probe_np560_mp3_setup.py](probe_np560_mp3_setup.py) | Observe original MPEG parsing -> audio setup -> the first missing service. |
| [probe_np560_native_game_save.py](probe_np560_native_game_save.py) | Native Hero save/load, cancel and existing-slot overwrite routes. |
| [probe_np560_native_settings_reset.py](probe_np560_native_settings_reset.py) | Exercise the native sound setting on an isolated Web run. |
| [probe_np560_npe_action_target.py](probe_np560_npe_action_target.py) | Find a native NPE action target using only real matrix edges. |
| [probe_np560_npe_audio_contract.py](probe_np560_npe_audio_contract.py) | Execute original NPE header and audio timing functions, not a codec. |
| [probe_np560_npe_audio_live.py](probe_np560_npe_audio_live.py) | Sample Web DAC audio and NPE HLE counters during an isolated route. |
| [probe_np560_npe_audio_rom_hole.py](probe_np560_npe_audio_rom_hole.py) | Make an isolated ROM-hole probe, never a production audio implementation. |
| [probe_np560_npe_input_combinations.py](probe_np560_npe_input_combinations.py) | Prove native NP560+ NPE direction/action matrix-combination semantics. |
| [probe_np560_npe_loop_boundary.py](probe_np560_npe_loop_boundary.py) | Read-only correlation of NPE decoded-frame count and original PRG time. |
| [probe_np560_npe_object_action.py](probe_np560_npe_object_action.py) | Prove the native one-shot NPE object action at a recovered target. |
| [probe_np560_npe_speex.py](probe_np560_npe_speex.py) | Test fixed 21-byte NPE records against the reference Speex decoder. |
| [probe_np560_npe_stream_window.py](probe_np560_npe_stream_window.py) | Read-only compare a stopped NPE audio RAM window with its original section. |
| [probe_np560_npe_unbanked_sfr.py](probe_np560_npe_unbanked_sfr.py) | Diff hardware-register writes while a real NPE game receives input. |
| [probe_np560_perf_samples.py](probe_np560_perf_samples.py) | Bounded Linux perf user-IP sampling of an owned QEMU CPU thread, without ptrace. |
| [probe_np560_runtime.py](probe_np560_runtime.py) | Take low-overhead NP560 Web/QEMU runtime snapshots. |
| [probe_np560_state.py](probe_np560_state.py) | Run an NP560 guest briefly and print CPU/NAND state for RE probes. |
| [probe_np560_tjfy_encounter.py](probe_np560_tjfy_encounter.py) | Walk the original Tianjiang map until its guest enters a random battle. |
| [probe_np560_usb_store_lanes.py](probe_np560_usb_store_lanes.py) | Run the original loader's exact MOVB store opcode on real QEMU. |
| [probe_np560_web_lifecycle.py](probe_np560_web_lifecycle.py) | Exercise real Web/QEMU lifecycle failures in owned, dynamically bound instances. |
| [probe_np560_web_matrix_exit.py](probe_np560_web_matrix_exit.py) | Find the physical NP560+ matrix event that exits the current foreground. |
| [qmp_read_np560_memory.py](qmp_read_np560_memory.py) | Read physical-memory ranges from a running NP560 QEMU instance. |
| [render_np560_toolbar_permutations.py](render_np560_toolbar_permutations.py) | Render pixel-group permutations for an NP560 toolbar capture. |
| [search_np560_live_memory.py](search_np560_live_memory.py) | Search a read-only NP560 Web/QEMU memory view for exact bytes. |
| [trace_np560_mobivoice_bitfields.py](trace_np560_mobivoice_bitfields.py) | Trace candidate decoder bit reads against an independent MSB-first reader. |
| [triage_np560_invalid_return.py](triage_np560_invalid_return.py) | Suggest source-proven NP560 overlay candidates after an invalid return. |
| [verify_np560_burn_payload.py](verify_np560_burn_payload.py) | Verify package bytes via finalizer OOB tags, without searching/fitting data. |
| [verify_np560_direct_menu_web.py](verify_np560_direct_menu_web.py) | Verify the recovered NP560+ direct menu through an existing Web instance. |
| [verify_np560_natural_menu_web.py](verify_np560_natural_menu_web.py) | Verify NP560+ reaches its root menu through the native application chain. |
| [verify_np560_npe_codec_trace.py](verify_np560_npe_codec_trace.py) | Compare opt-in codec input trace with an original NPE section. |
| [verify_np560_npe_dac_reference.py](verify_np560_npe_dac_reference.py) | Compare guest DAC sample-change order with an explicit NPE PCM candidate. |
| [verify_np560_toolbar_frames.py](verify_np560_toolbar_frames.py) | Exact top-toolbar regression against the original, checksummed UPD bytes. |
| [wait_np560_diagnostic.py](wait_np560_diagnostic.py) | Wait for a numeric field in the NP560 Web diagnostics. |
| [watch-np560-web.ps1](watch-np560-web.ps1) | 用途与参数见源文件。 |
| [watch_np560_code_sources.py](watch_np560_code_sources.py) | Pause an NP560 Web/QEMU run on the first recovered-code mismatch. |

## ROM/HLE 构建、补丁与 NAND 内容加工（85）

| 文件 | 用途 |
| --- | --- |
| [build_np560_burn_harness.py](build_np560_burn_harness.py) | Build a minimal NP560.PRG that enters the real updater command dispatcher. |
| [build_np560_damaged_mp3_fixture.py](build_np560_damaged_mp3_fixture.py) | Build an isolated invalid-sideinfo MP3; never modify the source file. |
| [build_np560_factory_nand.py](build_np560_factory_nand.py) | Build the minimum factory-seeded NP560+ NAND checkpoint. |
| [build_np560_lirt_provision_firmware.py](build_np560_lirt_provision_firmware.py) | Build a one-shot NP560 firmware which provisions ``lirt.nwf`` in guest. |
| [build_np560_minimal_nwf.py](build_np560_minimal_nwf.py) | Build and inspect a minimal experimental NP560+ V3.80 NWF resource. |
| [build_np560_mp3_allocation.py](build_np560_mp3_allocation.py) | Obtain/pin/release MP3 RAM through the original movable-object allocator. |
| [build_np560_mp3_antialias.py](build_np560_mp3_antialias.py) | Native DMCU Q28 Layer III alias reduction, after short reorder. |
| [build_np560_mp3_dct32.py](build_np560_mp3_dct32.py) | DMCU port of pinned libmad dct32, with full-width intermediate values. |
| [build_np560_mp3_decoder.py](build_np560_mp3_decoder.py) | Bank-owned native PCM decoder; not the factory 01:49F8 ABI yet. |
| [build_np560_mp3_factory.py](build_np560_mp3_factory.py) | Experimental native singleton implementation of the original MP3 ABI. |
| [build_np560_mp3_frame.py](build_np560_mp3_frame.py) | Native continuous Layer III entropy-frame driver, NOT PCM/factory ABI. |
| [build_np560_mp3_hle.py](build_np560_mp3_hle.py) | Opt-in 01/02 MP3 HLE gates in an existing native factory ROM bundle. |
| [build_np560_mp3_huffman.py](build_np560_mp3_huffman.py) | Native DMCU Layer III Huffman core, NOT a factory ROM entry replacement. |
| [build_np560_mp3_hybrid.py](build_np560_mp3_hybrid.py) | Native Layer III IMDCT/window/overlap/frequency inversion; NOT PCM. |
| [build_np560_mp3_imdct36.py](build_np560_mp3_imdct36.py) | Wide native libmad fast long IMDCT and windows (blocks 0,1,3). |
| [build_np560_mp3_intensity.py](build_np560_mp3_intensity.py) | Native Q28 Layer III joint stereo, before short reorder; not factory ROM. |
| [build_np560_mp3_requantize.py](build_np560_mp3_requantize.py) | DMCU signed Q28 Layer III requantization, not PCM/factory ROM bytes. |
| [build_np560_mp3_reservoir.py](build_np560_mp3_reservoir.py) | Native Layer III main_data assembly/history, not an original ROM ABI. |
| [build_np560_mp3_resident.py](build_np560_mp3_resident.py) | Place reconstructed native MP3 code/tables in a pinned resident skeleton. |
| [build_np560_mp3_ring.py](build_np560_mp3_ring.py) | Native original MP3 producer-ring -> resident Layer III PCM adapter. |
| [build_np560_mp3_scalefactors.py](build_np560_mp3_scalefactors.py) | Native Layer III scalefactors; libmad-based, not the factory ABI. |
| [build_np560_mp3_session.py](build_np560_mp3_session.py) | Owned MP3 session: real heap lease -> ring decode -> caller's X0 PCM. |
| [build_np560_mp3_sideinfo.py](build_np560_mp3_sideinfo.py) | DMCU Layer III side information, based on libmad III_sideinfo. |
| [build_np560_mp3_spectrum.py](build_np560_mp3_spectrum.py) | Native part2/part3 -> 576 signed quantized integers, NOT PCM. |
| [build_np560_mp3_stereo.py](build_np560_mp3_stereo.py) | DMCU Q28 MS stereo and short-block reorder, NOT PCM/factory ROM. |
| [build_np560_mp3_synthesis.py](build_np560_mp3_synthesis.py) | Native 32-subband polyphase synthesis -> signed PCM16, not factory ABI. |
| [build_np560_nand_rw_harness.py](build_np560_nand_rw_harness.py) | Build a guest DMCU harness for reconstructed NAND read/program/erase. |
| [build_np560_npe_hle_rom.py](build_np560_npe_hle_rom.py) | Add return instructions behind verified experimental NPE ROM HLE gates. |
| [build_np560_player_rom.py](build_np560_player_rom.py) | Build a checked player/NPE ROM bundle from V3.80 PRG, without tmp inputs. |
| [build_np560_reconstructed_rom.py](build_np560_reconstructed_rom.py) | Build the clean-room resident ROM used by the NP560+ QEMU machine. |
| [build_np560_rom_skeleton.py](build_np560_rom_skeleton.py) | Build a sparse experimental DMCU ROM skeleton for ABI exploration. |
| [build_np560_seek_fixture.py](build_np560_seek_fixture.py) | Create an explicitly synthetic LONG22 control, preserving all audio frames. |
| [build_np560_stream_burn_harness.py](build_np560_stream_burn_harness.py) | Build a guest harness for UpdateAll.exe's official NAND stream protocol. |
| [build_np560_system_nand.py](build_np560_system_nand.py) | Create a fresh system NAND via the vendor burner, then verify payload/ECC/boot. |
| [build_np560_vma03_soc_rom.py](build_np560_vma03_soc_rom.py) | Build a narrow SoC-ROM variant for the NP560 PRG-at-03 experiment. |
| [build_np560_windows.ps1](build_np560_windows.ps1) | 用途与参数见源文件。 |
| [burn_np560_stream.py](burn_np560_stream.py) | Stream a package NAND image through the unmodified NP560 burner in QEMU. |
| [ensure_np560_fat16_directories.py](ensure_np560_fat16_directories.py) | Add missing diagnostic FAT16 directories to an NP560 NAND checkpoint. |
| [finalize_np560_runtime_firmware.py](finalize_np560_runtime_firmware.py) | Remove one-shot NAND provisioning triggers from NP560 runtime firmware. |
| [import_np560_vendor_file.py](import_np560_vendor_file.py) | Import and read back a file using the original package burner file commands. |
| [inject_np560_minimal_pim.py](inject_np560_minimal_pim.py) | Create a diagnostic minimal ``nminbox.pim`` in an NP560 checkpoint. |
| [inject_np560_npe_fat16.py](inject_np560_npe_fat16.py) | Create a diagnostic NP560 NAND checkpoint containing one real NPE game. |
| [mirror_np560_runtime_patches.py](mirror_np560_runtime_patches.py) | Mirror guest-installed NP560 code patches into source-pinned PRG copies. |
| [np560_checkpoint_rehash.c](np560_checkpoint_rehash.c) | 用途与参数见源文件。 |
| [patch_np560_application_region_extra_installer.py](patch_np560_application_region_extra_installer.py) | Install the late application-region guest DMCU overlay installer. |
| [patch_np560_checkpoint_page_lanes.py](patch_np560_checkpoint_page_lanes.py) | Pair-swap selected NP560 NAND data pages and refresh their ECC. |
| [patch_np560_checkpoint_span_lanes.py](patch_np560_checkpoint_span_lanes.py) | Pair-swap an exact word-aligned NAND data span and refresh touched ECC. |
| [patch_np560_direct_manager_onto_recovered_rom.py](patch_np560_direct_manager_onto_recovered_rom.py) | Move only the direct-menu manager delta onto a recovered live ROM. |
| [patch_np560_direct_menu_late_chain.py](patch_np560_direct_menu_late_chain.py) | Chain the exact late-result installer before the direct-menu probe. |
| [patch_np560_embedded_menu_result_record_parser.py](patch_np560_embedded_menu_result_record_parser.py) | Embed the exact result-record parser after its source bank is mutable. |
| [patch_np560_exact_resident.py](patch_np560_exact_resident.py) | Patch one exact linked PRG routine into a recovered resident-ROM image. |
| [patch_np560_exact_resident_sources.py](patch_np560_exact_resident_sources.py) | Apply verified same-PC resident routines to an existing ROM lineage. |
| [patch_np560_hero_dog_sprite.py](patch_np560_hero_dog_sprite.py) | Create an opt-in, two-byte repair of the known Hero Legend NPE sample. |
| [patch_np560_mask_rom_resource.py](patch_np560_mask_rom_resource.py) | Seed an evidence-driven NP560 mask-ROM resource path experiment. |
| [patch_np560_menu_hardware_bit_wrappers.py](patch_np560_menu_hardware_bit_wrappers.py) | Install the four exact segment-33 menu hardware-bit wrappers. |
| [patch_np560_menu_list_item_set_installer.py](patch_np560_menu_list_item_set_installer.py) | Install the exact 30:3A56 menu list-item setter as guest code. |
| [patch_np560_menu_pointer_index_installer.py](patch_np560_menu_pointer_index_installer.py) | Materialize the guest menu pointer-index installer at 06:1600. |
| [patch_np560_menu_result_record_parser.py](patch_np560_menu_result_record_parser.py) | Restore the exact result-record parser before direct menu execution. |
| [patch_np560_menu_runtime_subinstallers.py](patch_np560_menu_runtime_subinstallers.py) | Complete the relocated menu chain and avoid the legacy 06:3A00 overlap. |
| [patch_np560_program_words.py](patch_np560_program_words.py) | Create a validated NP560.PRG diagnostic variant with word patches. |
| [patch_np560_relocated_menu_runtime_installers.py](patch_np560_relocated_menu_runtime_installers.py) | Restore the menu-runtime guest installers without clobbering 06:3000. |
| [patch_np560_resident_bad_block_helper.py](patch_np560_resident_bad_block_helper.py) | Keep the exact NAND bad-block status helper resident. |
| [patch_np560_resident_delimited_field_copy.py](patch_np560_resident_delimited_field_copy.py) | Restore the exact resident 06:DD56 delimited-field copy routine. |
| [patch_np560_resident_event_e0_handler.py](patch_np560_resident_event_e0_handler.py) | Restore the exact resident handler reached by foreground event 0xE0. |
| [patch_np560_resident_menu_record_decoder.py](patch_np560_resident_menu_record_decoder.py) | Restore the exact resident menu-record decoder at 11:5C12. |
| [patch_np560_resident_msb_helper.py](patch_np560_resident_msb_helper.py) | Keep the exact NAND-geometry MSB helper resident after late overlays. |
| [patch_np560_resident_result_object_alloc.py](patch_np560_resident_result_object_alloc.py) | Restore the exact resident result-object allocator at 1E:6444. |
| [patch_np560_resident_storage_unit_init.py](patch_np560_resident_storage_unit_init.py) | Install the exact 18:F97C function after executable RAM is created. |
| [patch_np560_reverse_far_memmove_overlay.py](patch_np560_reverse_far_memmove_overlay.py) | Install the reconstructed 31:7824 descending far-memory move. |
| [patch_np560_rom01_application_cursor_range.py](patch_np560_rom01_application_cursor_range.py) | Extend ROM-01 with the exact linked cursor-range function. |
| [patch_np560_rom01_application_result_list_create.py](patch_np560_rom01_application_result_list_create.py) | Extend ROM-01 with the exact application result-list creator. |
| [patch_np560_rom01_application_result_object_children.py](patch_np560_rom01_application_result_object_children.py) | Install three exact children of the application result-object path. |
| [patch_np560_rom01_application_result_object_init.py](patch_np560_rom01_application_result_object_init.py) | Install the exact application result-object initializer at 26:8296. |
| [patch_np560_rom01_application_result_record_match.py](patch_np560_rom01_application_result_record_match.py) | Install the exact application result-record matcher at 2A:80AA. |
| [patch_np560_rom01_application_result_scan_chain.py](patch_np560_rom01_application_result_scan_chain.py) | Install the remaining exact application result-scan overlay chain. |
| [patch_np560_rom01_late_result_table.py](patch_np560_rom01_late_result_table.py) | Reinstall two exact vendor result-table wrappers at the ROM01 boundary. |
| [patch_np560_rom01_modal_callback_closure.py](patch_np560_rom01_modal_callback_closure.py) | Install the exact vendor modal callback closure at the ROM-01 boundary. |
| [patch_np560_rom01_modal_foreground_object.py](patch_np560_rom01_modal_foreground_object.py) | Extend the guest ROM-01 installer with the exact foreground object body. |
| [patch_np560_words.py](patch_np560_words.py) | Apply verified 16-bit word patches to an NP560 program image. |
| [publish_np560_resource_persistence_writer.py](publish_np560_resource_persistence_writer.py) | Publish the exact NP560 resource-setting writer into its runtime PCs. |
| [repair_np560_checkpoint_ecc.py](repair_np560_checkpoint_ecc.py) | Normalize factory metadata and rebuild ECC in an NP560 checkpoint copy. |
| [seed_np560_factory_bootstrap.py](seed_np560_factory_bootstrap.py) | Seed the inferred NP560+ factory bootstrap record in a NAND checkpoint. |
| [seed_np560_factory_clock.py](seed_np560_factory_clock.py) | Seed the NP560+ factory clock record in a NAND checkpoint copy. |
| [seed_np560_factory_selector.py](seed_np560_factory_selector.py) | Seed the NP560+ factory selector byte in a NAND checkpoint. |
| [seed_np560_factory_userinfo.py](seed_np560_factory_userinfo.py) | Seed a complete factory-compatible USERINFO.SYS in an NP560 checkpoint. |

## 共享模块与早期实验模型（34）

| 文件 | 用途 |
| --- | --- |
| [__init__.py](__init__.py) | NP560+ reverse-engineering, emulator, and diagnostic tools. |
| [check_doc_links.py](check_doc_links.py) | Check local Markdown links in the NP560 documentation and entry READMEs. |
| [diagnose_np560_mp3_silence.py](diagnose_np560_mp3_silence.py) | Inspect an isolated NP560+ MP3 route without modifying the user's NAND. |
| [np560_assembler.py](np560_assembler.py) | Existing small DMCU label resolver, without ROM-builder import side effects. |
| [np560_emulator.py](np560_emulator.py) | Instruction-level emulator for the King Billion DMCU in the Noah NP560+. |
| [np560_host_time.py](np560_host_time.py) | Read-only Linux owned-thread CPU-time endpoints for diagnostic windows. |
| [np560_mobivoice_adaptive.py](np560_mobivoice_adaptive.py) | Owned model of the candidate's 80-sample adaptive excitation loop. |
| [np560_mobivoice_codebook_data.py](np560_mobivoice_codebook_data.py) | Fixed numeric codebooks from the reviewed candidate mode-5 decoder. |
| [np560_mobivoice_codebooks.py](np560_mobivoice_codebooks.py) | First-stage vector lookup for the candidate mode-5 LSF predictor. |
| [np560_mobivoice_decoder.py](np560_mobivoice_decoder.py) | Owned stateful decoder for the reviewed candidate's mode-5 frames. |
| [np560_mobivoice_fields.py](np560_mobivoice_fields.py) | Independent parser for the observed candidate MobiVoice SP mode-5 frame. |
| [np560_mobivoice_fir.py](np560_mobivoice_fir.py) | Owned fixed-point dot-product stage observed in candidate speech decoder. |
| [np560_mobivoice_fixed.py](np560_mobivoice_fixed.py) | Owned pulse-accumulation stage of candidate fixed excitation. |
| [np560_mobivoice_history.py](np560_mobivoice_history.py) | Stateful excitation history for the candidate mode-5 decoder. |
| [np560_mobivoice_interpolate.py](np560_mobivoice_interpolate.py) | Owned model of the candidate decoder's fixed-point table interpolation. |
| [np560_mobivoice_lpc.py](np560_mobivoice_lpc.py) | Candidate mode-5 ten-order LSF-to-LPC fixed-point conversion. |
| [np560_mobivoice_lsf.py](np560_mobivoice_lsf.py) | Owned model of one observed 10-word candidate synthesis preparation step. |
| [np560_mobivoice_lsf_predict.py](np560_mobivoice_lsf_predict.py) | Ten-word recursive LSF predictor of the candidate mode-5 decoder. |
| [np560_mobivoice_lsf_subframes.py](np560_mobivoice_lsf_subframes.py) | Candidate mode-5 LSF interpolation across the two 80-sample subframes. |
| [np560_mobivoice_mix.py](np560_mobivoice_mix.py) | Owned candidate excitation gain, pitch sharpening, and final summation. |
| [np560_mobivoice_pitch.py](np560_mobivoice_pitch.py) | Owned model of candidate decoder's pitch-delay code mapping. |
| [np560_mobivoice_synthesis.py](np560_mobivoice_synthesis.py) | Owned model of the candidate decoder's final 10-tap synthesis filter. |
| [np560_mobivoice_tables.py](np560_mobivoice_tables.py) | Mode-5 lookup values reconstructed from the isolated codec candidate. |
| [np560_mp3_link.py](np560_mp3_link.py) | Explicit fragment and address checks for the native MP3 ROM builders. |
| [np560_mp3_workspace.py](np560_mp3_workspace.py) | MP3 component workspace selection, not machine memory reservation. |
| [np560_overlay_map.py](np560_overlay_map.py) | Build and validate the NP560 reconstructed runtime-overlay map. |
| [np560_qmp.py](np560_qmp.py) | Issue one QOM get/set request to a running local NP560 QEMU instance. |
| [np560_rom_api.py](np560_rom_api.py) | Inventory calls from an NP560+ auxiliary listing into resident SoC ROM. |
| [np560_usb_transport.py](np560_usb_transport.py) | Serialize USB wire bytes as the original loader's data-RAM stores do. |
| [observe_np560_seek_reload.py](observe_np560_seek_reload.py) | Read-only host hardware watches for the original MP3 reload path. |
| [package_np560_windows.ps1](package_np560_windows.ps1) | 用途与参数见源文件。 |
| [portable/Start-NP560.ps1](portable/Start-NP560.ps1) | 用途与参数见源文件。 |
| [replace_np560_mp3_sample.py](replace_np560_mp3_sample.py) | Replace one MP3 track in an offline NP560 checkpoint. |
| [start_np560_windows.ps1](start_np560_windows.ps1) | 用途与参数见源文件。 |

## 仓库维护与整理（3）

| 文件 | 用途 |
| --- | --- |
| [cleanup_expired_nand.ps1](cleanup_expired_nand.ps1) | 仓库或本地资产维护，运行前检查目标范围。 |
| [maintenance/catalog_scripts.py](maintenance/catalog_scripts.py) | Generate the checked-in script-purpose index; --check detects stale output. |
| [maintenance/organize_tests.py](maintenance/organize_tests.py) | One-time mechanical migration of flat Python/JS tests into scripts/tests. |
