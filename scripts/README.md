# scripts 导航

不要把本目录中全部脚本都当成模拟器实现或可随意执行的工具。
**实际运行核心是 `../qemu-dmcu/`；Web 服务实现是 `web/`。**
221 个 Python/JS 测试已实体迁到 `tests/`。其它历史工具仍保留原路径，
以兼容交叉导入和已有实验流程；本页及 [完整分类全表](CATALOG.md) 按用途区分它们。

| 类别 | 入口/范围 | 使用边界 |
| --- | --- | --- |
| 模拟器实现 | `../qemu-dmcu/target/dmcu/`、`../qemu-dmcu/hw/dmcu/`、`web/` | CPU/设备、Web 桥接、前端和浏览器音频 |
| 运行与构建 | `run-np560-web.ps1`、`run-np560.ps1`、`build-np560.ps1`、`np560_lan_proxy.py` | 日常启动、编译、LAN；不是逆向探针 |
| 测试 | `tests/test_*.py`、`tests/test_*.js` | 自动断言；分纯工具回归、固件依赖和 QEMU 硬件集成测试 |
| 测试包装器/参考 | 根目录 `test-*.ps1`、`test_*_reference.c` | WSL 启动包装器、编译参考；不是运行时设备代码 |
| 静态逆向 | `analyse_*`、`analyze_*`、`audit_*`、`scan_*`、`np560_disasm.py`、`np560_aux_disasm.py` | 固件/指令/资源分析；部分 analyze 工具消费运行时采样 |
| 动态调试 | `probe_*`、`monitor_*`、`capture_*`、`dump_*`、`watch_*`、`triage_*` | 部分会按键、暂停、复位、写入诊断内存；勿盲目指向试玩实例 |
| 性能测量 | `benchmark_np560_web_speed.py`、`benchmark_np560_cpu_kernel.py` | 性能测试不是完整硬件兼容性证明 |
| ROM/HLE 工件 | `build_np560_*`、`patch_np560_*`、`finalize_*`、`mirror_*` | 构建/重建/历史实验工具，不是每个都属于当前运行链 |
| NAND 与内容 | `import_np560_vendor_file.py`、`burn_np560_stream.py`、`seed_*`、`inject_*`、`repair_*` | 会产生或修改数据；尤其 inject 与原厂文件导入不能混为一谈 |
| 维护 | `maintenance/`、`cleanup_expired_nand.ps1` | 索引生成、迁移记录、清理；清理操作必须先检查目标 |
| 共享库 | `np560_assembler.py`、`np560_qmp.py`、`np560_rom_api.py` 等 | 由工具导入，通常不是直接试玩入口 |

`np560_emulator.py` 是早期 Python 指令级实验模型，**不是当前 QEMU 试玩内核**。
`vendor/` 是工具依赖，`fixtures/` 是测试资料，`qemu-patches/` 是固定历史备份。

## 先运行哪些测试

从项目根目录执行，无需重启当前试玩：

```powershell
python scripts/tests/test_np560_web_speed.py
python scripts/tests/test_np560_lan_proxy.py
node scripts/tests/test_np560_pointer_input.js
node scripts/tests/test_np560_audio_output.js
python scripts/tests/test_import_np560_vendor_file.py
```

`test_np560_web_frontend.py` 还会核对本地原厂固件事件表，需要对应固件。
`test_np560_instruction_clock.py`、`test_np560_dtu.py`、`test_np560_nand*.py` 等是
硬件/集成检查，通常需要 WSL、已构建 QEMU 或额外输入。先查看对应 `--help`
或源文件，不能把全部测试一键运行失败都解释成模拟器回归。

Python unittest 类测试可用定向发现：

```powershell
python -m unittest discover -s scripts/tests -p test_import_np560_vendor_file.py
```

## 索引维护

```powershell
python scripts/maintenance/catalog_scripts.py
python scripts/maintenance/catalog_scripts.py --check
```

全表逐个列出文件及其 docstring 用途。它不修改 ROM/NAND、不连接运行实例。
`organize_tests.py` 保留本轮一次性机械迁移过程；无需在日常构建中执行。
