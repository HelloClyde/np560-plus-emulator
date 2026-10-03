# scripts 导航

不要把本目录中全部脚本都当成模拟器实现或可随意执行的工具。
**实际运行核心是 `../qemu-dmcu/`；Web 服务实现是 `web/`。**
Python/JS 测试已实体迁到 `tests/`。其它历史工具仍保留原路径，
以兼容交叉导入和已有实验流程；本页及 [完整分类全表](CATALOG.md) 按用途区分它们。

| 类别 | 入口/范围 | 使用边界 |
| --- | --- | --- |
| 模拟器实现 | `../qemu-dmcu/target/dmcu/`、`../qemu-dmcu/hw/dmcu/`、`web/` | CPU/设备、Web 桥接、前端和浏览器音频 |
| 运行与构建 | `start_np560_windows.ps1`、`build_np560_windows.ps1`、`run-np560-web.ps1`、`run-np560.ps1`、`build-np560.ps1`、`np560_lan_proxy.py` | Windows 原生与旧 WSL 启动/构建、LAN；不是逆向探针 |
| 测试 | `tests/test_*.py`、`tests/test_*.js` | 自动断言；分纯工具回归、固件依赖和 QEMU 硬件集成测试 |
| 测试包装器/参考 | 根目录 `test-*.ps1`、`test_*_reference.c` | WSL 启动包装器、编译参考；不是运行时设备代码 |
| 静态逆向 | `analyse_*`、`analyze_*`、`audit_*`、`compare_*`、`scan_*`、`np560_disasm.py`、`np560_aux_disasm.py` | 固件/指令/资源分析；部分工具消费运行时采样 |
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

`tests/test_np560_live_browser_pointer.js` 是**会实际按键**的可选整链测试，
只对新启动、屏幕可见的隔离 Web 实例执行；需要 Node 可加载
Playwright 和本机 Edge，可用 `NODE_PATH` 指向已安装模块目录。
命令为 `node scripts/tests/test_np560_live_browser_pointer.js
http://127.0.0.1:<隔离端口>/`。它模拟移动视口触控与鼠标，
不代表物理手机已验收；不要把试玩设备的 URL 传给它。
`tests/test_np560_live_browser_audio.js` 只对**已从原厂路径进入有声游戏**
的隔离实例测试 headless Edge AudioContext 调度，默认 15 秒；
可依次传入观察毫秒数、音频轮询毫秒数、LCD 轮询毫秒数与
`fast|full|compat` 显示模式，例如
`node scripts/tests/test_np560_live_browser_audio.js http://127.0.0.1:8952/ 15000 50 200 fast`。
`full` 仅在这次浏览器加载时对照旧全量查询，`compat` 模拟旧桥接
没有 `/api/display` 的回退；这些诊断覆盖不改生产文件。
它会启用网页声音但不改客机音量或存档；
同样不要指向试玩设备，也不能把无播放空档当作物理扬声器试听通过。
`probe_np560_audio_cpu_window.py` 在 WSL 中以隔离实例的
`runs/<run-id>/status.json` 绑定 QEMU、解码器与桥接 PID，按秒
记录三进程 CPU 和设备音频帧推进；只读、不按键。它要与上面的
浏览器观察器同时运行才能比较同一负载窗口，旧生命周期文件或
试玩设备的 PID 不能作为测试输入。

Python unittest 类测试可用定向发现：

```powershell
python -m unittest discover -s scripts/tests -p test_import_np560_vendor_file.py
```

《天降风云录》V1.3 是当前 NPE 主样本。候选 mode-5 解码器的
首三帧 PCM 回归不需要本地游戏文件；若本机存在 SHA-256 已登记的
`D:/Downloads/NP560plus游戏全集/天降风云V1.3.npe`，还会核对
全部 22 段、10,486 帧的完整音轨。该测试不加载历史 DLL，也不启动试玩实例：

```powershell
python -m pytest -q scripts/tests/test_np560_mobivoice_decoder.py
```

`build_np560_player_rom.py` 新建的包已经绑定不依赖历史 DLL 的 mode-5
服务；用 `run-np560-web.ps1 -SocRomBundle <包目录>` 启动时自动选择，
不再额外传 `-RomNpeCodecOwned`。后者仍用于手工严格 ROM 空洞镜像
的隔离诊断，需配 `-SocRomSkeleton` 与独立 NAND/journal；不能与
`-SocRomBundle` 混用，更不要在正在试玩的设备上直接切换。
目前只覆盖已实测的 format 13/21 字节 NPE 帧，不是所有 NPE 声音
格式或原厂 mask-ROM 的替代证明。`-RomNpeCodecDll` 仍可用于显式
历史候选对照，与自有后端不可同时启用。

跨游戏音频差分是离线诊断，不属于日常试玩：
`probe_np560_mobivoice_corpus.py` 使用已登记的本地 NPE 语料盘点，
逐文件/分段验哈希后，对不同的 format-13 分段只比较一次独立
解码器与隔离候选 DLL。它需要用户自行持有的 DLL，不能证明
缺失 mask ROM 的实际 PCM 或游戏内播放控制；运行参数见
[解码来源记录](../doc/audio/np560_audio_codec_provenance.md)。

## 两份 NAND 日志的只读对照

`compare_np560_nand_journals.py` 需要同一个只读底图和两份**已停止写入**
的 journal。它校验底图 SHA、重放实际擦写、只比较涉及的页；可选
`--tag 0x0e9b` 用尾页 OOB 标签对齐磨损均衡搬移前后的块。不会写入
底图、日志或客机，但未独立重验每条记录的 CRC32C，待比较日志应先由
QEMU 正常重放验证。输出报告是差异线索，不自动认定字节的原厂语义。

```powershell
python scripts/compare_np560_nand_journals.py <base.nand> <first.npj> <second.npj> --tag 0x0e9b
```

## 索引维护

```powershell
python scripts/maintenance/catalog_scripts.py
python scripts/maintenance/catalog_scripts.py --check
python scripts/check_doc_links.py
```

全表逐个列出文件及其 docstring 用途。它不修改 ROM/NAND、不连接运行实例。
文档链接检查只读；它会跳过不随 Git 提交的 `tmp/` 实验输出。
`organize_tests.py` 保留本轮一次性机械迁移过程；无需在日常构建中执行。
