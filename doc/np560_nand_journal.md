# NAND 增量保存与异常退出后的原厂设置读回

日期：2026-09-06。状态：**可选的逐次擦写持久化已接入 QEMU、Web 与 Windows 启动脚本**。
原厂音效设置经正常菜单确认，QEMU 被 SIGKILL 后，新的进程从原底图及增量日志读回了设置。
这不是整机快照，也没有通过宿主修改设置 RAM；不代表全部应用、真实断电或完整 NAND 硬件已完成。

同日后续新增**自动日志合并**：超过 16 MiB 的日志在下一次擦写前尝试收敛为当前块内容，
仍使用原底图，不导出另一份完整 NAND。实现、WSL 文件替换边界和证据见下文；设备保存配置仍需指定。

后续已增加 [固定设备配置](np560_device_config.md)：首次绑定底图和日志，后续用 `-Device` 启动，
不必每次重填 ROM/NAND/日志参数。原有显式参数方式仍保留，也不会自动迁移正在运行的实例。

## 使用方式与保存边界

QEMU 增加启动属性 `nand-journal=PATH`；Python Web 为 `--nand-journal PATH`，
Windows 启动脚本为 `-NandJournal PATH`。未指定时保持原先行为，不自动迁移正在运行的实例。

示例（工作区根目录；Web 会输出实际分配的端口）：

```powershell
.\scripts\run-np560-web.ps1 -BootMode firmware-vma03 `
  -SocRom .\tmp\np560-system-v380-vma03-resident-codec-holes-v1.bin -SocRomSkeleton `
  -NandCheckpoint E:\qemu-dmcu-build\np560-vendor-file-import-v3.nand `
  -NandJournal E:\qemu-dmcu-build\np560-device-save.npj -Port 0 -NoBrowser
```

- 每次启动使用**同一底图和同一日志**。底图只读，日志保存此设备后续的 NAND 擦写；两者共同构成介质。
- 不必配置 `--nand-save-on-exit` 或每次导出约 553 MB 的完整 NAND。Web 显示“擦写实时保存（增量日志）”。
- 同一个日志只能由一个 QEMU 持有。不同设备应使用不同日志，不可把同一个日志共享给同时运行的实例。
- 自动合并版本还会在日志旁保留一个零字节 `.lock` 文件，整个进程期间持有它，不要在运行时删除或替换。
  该锁保护日志替换，不保存设备资料；新进程继续使用同一个锁文件。不要与不支持该锁协议的旧核心同时打开同一介质。
- 完整 checkpoint 导出仍可使用，但不能覆盖当前日志或其底图。更换底图须先导出到新路径，
  再以新底图和新的空日志启动；不能把旧日志继续套到已经包含其修改的新底图上。
- 当前后端使用 POSIX 文件锁，实际运行于 WSL Ubuntu2；原生 Windows QEMU 会明确拒绝，未提供无锁降级。

## 实现与格式

实现位于 `qemu-dmcu/hw/dmcu/np560_nand_journal.c`；`np560.c` 在原有正常程序写、
跨页 OOB 流写、copy-back 和擦除修改内存之前提交日志。

一次成功擦写的次序为：校验命令和 DMA 数据 → 写记录 → `fdatasync` → 改内存中的 NAND → 返回成功。
若记录写入或同步失败，锁定为 failed 状态，拒绝后续修改，报告 backing 错误，不能伪装 ready。
`ERROR=5` 是现有 clean-room NAND 控制接口的宿主 backing 错误，**不是已确认的原厂寄存器编码**。

| 部分 | 内容 |
| --- | --- |
| 64-byte 文件头 | `NP560J1\0`、版本 1、页/OOB/块几何、底图 data 后接 OOB 的 SHA-256 |
| 32-byte 记录头 | `NJR1`、操作、连续 64-bit 序号、页、列、长度、CRC32C |
| 数据 | 正常程序写/OOB 的输入字节；copy-back 保存源页数据而非源地址；擦除无 payload |

重放保留原有 NAND 的 1→0 AND 编程、OOB 和整块擦除语义。完整记录逐项检查序号、范围和校验，
不同底图、完整坏记录、序号跳跃都拒绝启动，不静默略过。只有 EOF 的不完整头/数据可视为未完成尾部，
截断到最后一个完整记录，报告丢弃的字节数。文件排他锁覆盖整个生命周期。

只读属性 `nand-journal-state` / Web 字段 `nand_journal_state` 提供
`durable|failed SEQUENCE=… REPLAYED=… TORN_BYTES=…`。这里 durable 指完成记录的宿主保存机制，
不代表对所有物理故障、断电情形作出保证。

## 本轮实际启动缺陷与修复

原厂 writer 留下 22,278 条记录、23,410,216 bytes 的日志。逐记录各读取头和 payload，
会在 WSL 的 Windows 文件系统上产生大量小块读取。第一次普通 Web reader 因 8 秒 QMP 握手期限而退出：

- 失败实例：`tmp/np560-nand-journal-native-20260906-v1/reader-process/20260906T031313.941028Z-80029-6345ad8f/`。
- Web PID 80029，QEMU PID 80031，退出分别为 1 / -15；此时尚未进入 guest，日志 SHA-256 未变。
- 单独暂停 guest 测量：PID 80042 的旧核心在 **8.905 秒**就绪，成功重放 22,278 条，随后正常退出。
  证明并非日志损坏或 QEMU 已经崩溃；是启动等待期限先到。

修复为固定 **64 KB 有界预读**，不一次性载入整个日志，也不放宽校验。重放完仍按已校验的记录边界
seek；不使用预读后的文件位置作为提交位置。写入、同步及文件格式保持不变。

同底图/日志的 Web reader 随后正常启动。其生命周期记录从 QEMU spawned 到 Web serving 约 **5.47 秒**，
没有延长原来的启动期限。该值与单独测量有少量计时范围差异，不作为严格性能基准或任意大小日志的保证。

## 原厂设置的实际读回证据

输入底图为 `E:/qemu-dmcu-build/np560-vendor-file-import-v3.nand`，553,648,192 bytes，
SHA-256 `7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`，实验后重新核对未变。

| 边界 | 原厂观察 / 进程证据 |
| --- | --- |
| writer 冷启动 | 原厂音效开启，`sound_off=0` |
| 原厂设置确认 | 经物理矩阵选择“关”并确认，`sound_off=1`；确认前后新增 80 次原厂 NAND program |
| 异常终止 | writer QEMU PID 79794 被 SIGKILL，父进程记录退出 -9；没有 checkpoint 导出 |
| 新进程启动 | reader QEMU PID 80070 重放原日志 `REPLAYED=22278`，冷启动已是 `sound_off=1` |
| 原厂窗口 | 正常进入发音/音效设置，实际 LCD 的“关”选项勾选；不是只查看内存或按键 ACK |
| reader 结束 | Web PID 80068 与 QEMU PID 80070 均正常退出 0，未配置退出导出 |

设置写入/读回由 `scripts/probe_np560_native_settings_reset.py` 的 `set-off` / `read-off` 完成；
主进程另行核对了终止方式、文件身份和 LCD。该脚本单独输出 passed 不证明上述进程边界。

证据目录 `tmp/np560-nand-journal-native-20260906-v1/`：

- `writer/report.json`、`writer/06-after-confirm.png`。
- `writer-process/20260906T030031.995683Z-79792-71960b37/status.json`。
- `reader/report.json`、`reader/10-native-readback.png`。
- `reader-process/20260906T032001.836510Z-80068-b66b0db2/status.json`。

**构建边界：** writer 核心为 `d31d9d122f5b09c65e494c411dd5d1a97665c7d0e74e433b40285a301e64d242`；
reader 为缓冲重放修复后的 `cc8a5518bd7e62fc656bd0410c58e7542f3a1890a8f85c95d2c1115984ae00d2`。
这证明已有日志能被修复版本读回，不是原厂设置的同构建 writer/reader 对照。此次核心差异仅为日志读取缓冲，
PRG 与 guest ROM 未改；前端状态标签也有改动，不声称所有产物完全相同。

两端 PRG：`d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`；
guest ROM：`a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef`。
writer 终止后日志 SHA-256：`d0646f34bcf4115f082c1023d9ec445319becb93dd19c46f671d1119b08b97c1`。
reader 自然启动和应用操作继续产生擦写，结束前序号已到 33,543；不能把读回过程描述成日志只读、字节未变。
结束后的日志为 23,795,656 bytes，SHA-256
`7c846ff95b16ec4043d76cb7d5225e1134f5a0925a5d14ce0e5e10f2c8f35fe6`。

## 自动日志合并：不改底图，不导出大 NAND

实现仍在 `qemu-dmcu/hw/dmcu/np560_nand_journal.c`。这属于宿主介质维护，
不向 guest 伪造擦写计数、调用应用保存函数或改变 CPU/RAM；原有 guest 命令提交顺序不变。

- 每块首次变更前（包括日志重放）记录**底图该块 data + OOB 的 SHA-256**。
  只用约 132 KiB 的块索引，加一个约 132 KiB 的擦除块缓冲，不复制 512 MiB NAND。
- 合并时，与底图完全相同的块无需记录；不同的块写一条 erase，随后保存其中非全 FF 的页。
  同时保留 data/OOB、页内空洞和同块内未改的原始页；原底图非空但最终被擦空的块仍保留 erase。
- 输出保持原有 `NP560J1` 格式、几何和底图 SHA，重新从 1 编排记录序号；
  `SEQUENCE` 因而是当前日志的记录数，不能再当成设备终身擦写计数。
- 第一次触发门槛为 16 MiB，发生在下一条 guest 擦写提交**之前**。
  先估算结果，只有确实更小时才生成临时文件；成功或无需合并后，等日志至少再增长
  `max(当前大小, 16 MiB)` 才重试，避免对本来就紧凑的日志反复做无效合并。
- 在同目录独占创建临时文件，完整写入并 `fdatasync`；持续持有 `.lock`，关闭两个日志句柄，
  原子 `rename` 替换，再同步父目录、打开并锁住新日志。guest 命令与维护在 QEMU BQL 下串行，
  不存在“取快照时另一条命令已经修改一半”的状态。
- 替换前失败保留旧日志；替换后同步/重新打开失败则标记 failed、拒绝后续擦写，
  不能继续写入已脱离目录的旧文件。合并不会放宽完整坏记录、错误底图或不完整尾部的原有规则。
- 拒绝合并硬链接日志，避免把一个共享介质静默拆成两份；导出也不能覆盖活动日志或其锁文件。

只读 QOM `nand-journal-maintenance` 返回 `BYTES / COMPACTIONS / RECLAIMED / NEXT / ERROR`。
维护人员可向 `nand-journal-compact` 写入布尔 `true` 提前尝试合并；日常保存不要求手动调用它。
它不替代原生存档，也不是升级软件可见的真实控制寄存器。

### 平台问题和修复边界

第一版把仍打开的新日志重命名后继续使用其句柄，在当前 WSL/DrvFS 上可重复出现：目录里列出新文件，
但另一个进程打开同一路径收到 `ENOENT`，QEMU 关闭后才可读。失败记录保留在
`tmp/np560-nand-compaction-20260906-v1/`、`v2/`。没有以延迟重试或忽略错误把它判成通过。
修复为稳定旁路锁保护下的关闭、替换和重开；原有日志文件锁同时保留，打开后检查路径与 fd 指向同一 inode。

后续真实日志启动第一次超过原有 8 秒 QMP 握手期限，实验 QEMU 80826 已终止并回收，
见 `tmp/np560-nand-compaction-native-20260906-v1/`。大量原厂 erase 涉及已经全 FF 的块，
逐块重新做 SHA 增加了重复工作；现在先用完整 `memcmp` 判定全 FF，再复用该块的同一 SHA-256。
非全 FF 块仍完整计算摘要，未改成短校验和，也未放宽启动期限。

### 已验证与尚未证明的保证

`scripts/tests/test_np560_nand_compaction.py` 的微型非空底图检查包含：

- 原始页保留、最终擦空、跨 data/OOB、跨块 OOB、copy-back、同进程替换后继续追加和新进程冷读回。
- 用独立重放器比较新旧日志涉及的**完整块 data/OOB**；合并不改变 guest NAND 命令计数。
- 文件争用、硬链接拒绝、锁文件导出保护；真实 `EFBIG` 在临时文件写入时失败，原日志完整保留。
- 测试专用 `scripts/np560_journal_faults.c` 仅加载到指定实验子进程：在 rename 前/后准确 SIGSTOP，
  观察到进程停在边界后 SIGKILL，新进程分别读取完整旧/新日志。
- 注入 rename 后父目录同步 `EIO`，当前进程拒绝后续 program/erase/copy；新进程仍可读取完整新日志。

以上不是宿主真实断电实验，也未覆盖任意磁盘/文件系统损坏。
SIGKILL 若发生在发布之前，可能留下一个未引用的 `.compact.*` 文件；启动不会把它当作有效日志，
目前不自动扫描删除这类残留。稳定锁只能协调遵守同一协议的进程，不承诺与旧核心并发写的安全性。

### 原厂介质副本上的自动合并与冷启动

最终核心：46,670,672 bytes，SHA-256
`1f42a1e3d8979628810f66775c2f5219605332f1e7e580ab99af242a157545db`。
记录：`tmp/np560-nand-compaction-native-20260906-v2/report.json`。

同一最终核心的微型介质及故障边界结果为
`tmp/np560-nand-compaction-final-20260906-v1/report.json`：9,536 → 4,442 bytes；
rename 前/后中止的 PID 80954 / 80965 均退出 -9，两个 reader 均退出 0；
目录同步失败 PID 80976 拒绝后续修改后正常退出，其 reader 退出 0。
原有追加/损坏拒绝/尾部恢复检查亦通过，记录为
`tmp/np560-nand-compaction-final-durability-20260906-v1/report.json`（writer 80989 退出 -9，reader 退出 0）。
这两项不是用优化前核心的成功替代最终构建检查。

- 原底图仍为上文 `np560-vendor-file-import-v3.nand`，只读，不生成另一份完整 NAND。
- 仅复制前一轮原厂设置日志：23,795,656 bytes，SHA
  `7c846ff95b16ec4043d76cb7d5225e1134f5a0925a5d14ce0e5e10f2c8f35fe6`。
- 先独立重放证明物理块 4095 的 data/OOB 已全部 FF，再由一个 guest 控制器 erase 触发自动门槛。
  该诊断命令不改变任何介质字节；**不是重新执行原厂设置保存**，不混称应用保存验证。
- 合并并完成该命令后，日志为 **669,383 bytes**，共 338 条记录；SHA
  `4c10f59c3021711ccef65102fa1cfd6acad55b3cbad579b75abe29aa9fa89239`。
  与原日志相比，独立重放覆盖两者触及的 3,745 个完整块，data/OOB 全相同；
  未涉及的块在两者中均直接取同一底图，因此此比较不是只抽查设置字段。
- 自动合并进程 PID 80915 在命令完成后 SIGKILL，退出 -9；原厂冷启动 PID 80920 使用同一核心、
  同一底图及合并后的日志，没有输入按键、修改 guest RAM 或导出 checkpoint。
- 原厂完整桌面正常出现，最后三个顶栏样本相对原包 0/5,280 像素差异，实际
  `native-desktop.png` 已查看；无 ROM_MISSING / INVALID_CONTROL / UNSUPPORTED，NAND ERROR=0，HLE 关闭。
- 原厂初始化后的音效配置读回为 `sound_off=1`，与前一轮的原生保存设置一致。
  这次没有再打开设置窗口或播放内容，不能称音频解码或所有设置功能完成。
- 冷启动会继续正常写入，末次状态为 `SEQUENCE=11603 / REPLAYED=338`；因此最终工作日志不再是上面的
  669,383-byte 静止输入。该进程正常退出 0；源底图和源日志的 SHA 均未改变。

该结果证明：已有原厂保存内容在自动合并、进程终止和新进程原厂启动后仍可用。
保存内容最初由前一轮不同核心生成，不应改写为本轮同构建完成了设置的原生写入与读回。

## 原有持久化检查与未完成范围

`scripts/tests/test_np560_nand_journal.py` 用 guest 控制器命令检查 AND 编程、数据/OOB 边界、跨页 OOB、
copy-back、擦除、SIGKILL 后重放、文件争用、错误底图、损坏记录与不完整尾部。不开辟大型 NAND 文件。
旧无日志核心丢失已写数据的反例在 `tmp/np560-nand-journal-before-20260906-v1/report.json`；
首版日志机制证据在 `tmp/np560-nand-journal-20260906-v1/report.json`。

当前缓冲版的同构建控制器检查已通过，结果为
`tmp/np560-nand-journal-buffered-20260906-v3/report.json`（writer PID 80353 / SIGKILL -9，reader 正常退出 0）。
另对**只属于该实验的子进程**设置文件大小上限，让日志追加出现真实 `EFBIG`，没有填满磁盘：

- 首次失败只留下 16-byte 不完整记录头；guest 读到 `STATUS=0 / ERROR=5`，日志状态为 failed，序号保持 10。
- 随后的程序写、OOB、copy-back 和擦除全部拒绝；当前进程的 guest 读命令仍读到此前提交的数据，
  未成功执行任何一次新 program/erase/copy。
- 新进程只清理不完整的 16-byte 尾部，重放 10 条旧记录，介质内容恢复正确。
- 此项覆盖真实写入系统调用失败，不等于已覆盖 `fdatasync` 独立失败、ENOSPC 的全部表现或宿主断电。

保留了两次诊断用例自身的失败记录：v1 没有合并既有 `preexec_fn`，尚未启动故障子进程；
v2 将状态存入随后被测试命令覆写的 R0。v3 保留原有父子进程清理回调，并以不被后续命令改写的
R2/R3 记录状态。两者不是为通过测试而修改控制器返回值。Web 生命周期检查及新参数保护检查通过，
Windows 启动脚本语法解析通过；未自动改变用户运行实例的保存配置。

未完成的整机范围仍包括：

- 真实 NAND 外部控制器/GPIO、busy 和物理中途断电行为；增量保存不替代这些硬件模型。
- 所有游戏、资料和错误恢复路径的原生保存；本次设置读回不是全部资料安全的证明。
- 便捷设备配置、底图迁移、异常终止留下的临时文件管理，以及更多真实资料的原生保存。
  自动日志合并已实现，但不代表这些日常使用能力都已完成。
- 宿主突然断电的完整保证：创建日志后的父目录持久化、文件系统及设备缓存故障未闭合。
- 游戏和播放器的真实音频解码。本次更改音效设置仅作为原厂非易失保存用途，不是声音实现。
