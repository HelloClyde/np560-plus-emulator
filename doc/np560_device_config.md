# 固定设备配置与日常持久化

## 2026-10-01：NPE 自有后端绑定到 v3 设备

新建配置为 `np560-device-v3`，在原有 ROM、NAND、MP3 地址及实时参数
之外，固定保存布尔值 `rom_npe_codec_owned`。值为 true 时创建和每次
重开都要求严格 SoC ROM skeleton 及六处已登记的 NPE gate 字节；
拒绝再从命令行覆盖另一 NPE 后端。v1/v2 配置仍按原格式读取，不
自动升级、覆盖其 NAND 日志或推断旧 ROM 已具备声音服务。

隔离 `tmp/np560-player-device-v3-20261001-v1/device.json` 用新默认
ROM 包 `18cca3e8…` 与《天降风云 V1.3》底图创建，配置中保存
`rom_npe_codec_owned=true`。仅传 `-Device` 在 8922 重开，Web 生命周期
记录自有解码服务及 QEMU 均启动，健康状态返回相同 ROM SHA、
`qemu_alive=true` 和解码子进程 PID；随后经本实例 shutdown token
正常退出，未触碰用户 8891 或 8920。此步骤验证配置/服务恢复，
不单独证明有声输出；新游戏 DAC 证据见
[播放器 ROM 包](np560_player_rom_build.md)。

## Windows QMP 并发关闭停滞修复（2026-09-23）

生命周期检查曾耗时 120.286 秒，关闭连接后读取线程仍以超时结束。重复运行真实
`socketpair` 用例，第 16 次出现停滞；10 秒 watchdog 的栈显示关闭线程位于
`stream.close()`，请求线程位于 `socket.readinto` → `_read_message`。
单次运行可能正常，不能用一次通过排除该竞态。

`QMPClient.close()` 现在先 shutdown，再 detach 并关闭底层 socket 句柄，最后关闭
缓冲流。仅 `sock.close()` 不足：makefile 的引用会推迟实际句柄关闭，缓冲流自身
又在等待读取锁。detach 使旧 socket 对象不再拥有数字句柄，避免后续流清理误关
已经复用的句柄。本修改不重试 QMP 命令，不改变超时的“执行结果未知”语义。

Windows 连续 200 次原始关闭用例通过；新增带 15 秒子进程上限的 200 次回归场景。
Windows 全部 24 项生命周期测试通过（0.869 秒）；WSL 23 项通过、Windows 专用项
跳过（0.256 秒）。验证使用本地测试连接，未连接或重启用户实例，也不代表已经验证
Windows 原生 QEMU 的完整启动或所有网络传输。本轮未改 QEMU 二进制及固件。

## 实验 EQ v8 固定配置重开（2026-09-22）

### 原厂音效选择跨重开：回到正常，不认定日志故障

同目录后续 eq-write/eq-read 两个独立进程均正常退出 0。在原始音效页从
“正常”按一次 Down，圆点移到“重高音”（treble.png），确认后 F4 返回播放页、
再 F4 最小化，正常关闭。冷启动再用 M04/M35/F3/Down/Down/Enter 进入音效页，
圆点回到“正常”。modes-before.png 与 modes-after-reboot.png 的原始灰度画面
SHA-256 同为 bbf6b02e564a364c4b0c18acf6efefdfb8603c6dc7d03660f71056fb680ba30d。
路线与每步原始画面保存在 eq-select/eq-confirm/eq-reopen-menu，无客机内存注入。

核对 PRG d555609e…：原厂 VMA03 `0D:3226..324E` 从 `50:7E06/7E08` 取
播放器对象指针，对 `+087B` 写入字节 0；`0D:3250..329A` 随后读该字段，查
`33:5A2E` 并调用 `33:4D82`。这条原厂初始化路径支持重开回正常的解释，而不是
足以认定 NAND 持久化失败的证据。本轮没有记录该 PC 的实时命中，不扩大为所有
最小化/退出/重入路径都必须清零；也未播放歌曲或证明 EQ 预置保存为产品要求。
不要加宿主自动保存 EQ 来覆盖原厂行为。仍需验证实际有声会话的重入/恢复。

现有 v2 配置已足够保存实验 v8 的 ROM 和运行参数，无需再增加配置格式。
实际通过 Python Web CLI 的 `--create-device`、`--soc-rom-bundle`、
`--experimental-eq` 创建 `tmp/np560-eq-device-20260922-v1/device.json`。
首次创建显式允许实验算法；以后只用 `--device`，仍绑定原 ROM 哈希，不能静默升级。
本次不是 Windows PowerShell 包装器验收。

设备 ID `0538878b-6a74-419a-9164-5b7b756061de`；两次独立 Web/QEMU 启动并正常
退出 0，日志分别在该目录 first/second。第二次 `REPLAYED=2985 TORN_BYTES=0`，
ROM SHA-256 为 `5e4be1ecda33813c1c5da627523d510f98b1a7e9785a16d43f87513269aaa85f`。
HLE base=97514、arena=93952、instruction_clock/realtime=true、icount_shift=0。
只复用 LONG22 底图并创建独立增量日志，没有复制 NAND 或修改用户设备。

第二次启动截图 reopened.png 为每日一句；随后真实矩阵 F4/M04、播放器/M35，
候选分别 8E/97，各映射一次，正常松键。已目视 player.png 的完整播放器，显示
“当前未选择歌曲”。ROM_MISSING/UNSUPPORTED 均 none。两个临时端口已关闭。

范围：证明实验 ROM 与实时配置的跨进程恢复、日志重放和播放器入口；未在本次
选择歌曲、保存 EQ 预置或验证有声重开，不能称作 EQ 设置持久化或音频全功能通过。

日期：2026-09-06。设备配置已接入 Web 和 Windows 启动脚本，复用现有 NAND 增量保存后端。
配置不复制底图，不修改 guest RAM、ROM 服务或原厂设置，也不把整机快照当成游戏存档。

## 用法

在项目根目录首次创建一个设备（以下路径是示例，应选择长期保存目录，不用 `tmp/` 保存日常设备）：

```powershell
.\scripts\run-np560-web.ps1 -CreateDevice E:\NP560\main.json `
  -BootMode firmware-vma03 `
  -SocRom .\tmp\np560-system-v380-vma03-resident-codec-holes-v1.bin -SocRomSkeleton `
  -NandCheckpoint E:\qemu-dmcu-build\np560-vendor-file-import-v3.nand
```

此命令只创建小型 JSON 配置并退出，不启动 QEMU、不复制约 553 MB 的 NAND，不生成测试数据。
生产设备的 ROM、底图也应放在不会被临时清理的位置；此例使用现有研究输入，仍有声音 ROM 缺口。
默认增量日志为同目录同文件名前缀的 `main.npj`，也可在创建时指定尚未使用的 `-NandJournal` 路径。

以后每次只需：

```powershell
.\scripts\run-np560-web.ps1 -Device E:\NP560\main.json
```

可额外指定 `-Port`、`-NoBrowser`、`-RunLogDir` 等宿主选项。
端口不是设备身份；换端口仍使用同一资料。不要同时运行同一设备。
WSL 直接调用的对应参数为 `scripts/web/np560_web.py --create-device ...` 和 `--device ...`。
创建入口不会覆盖已有配置或已有日志；恢复已有设备必须使用 `--device`，而不是再次创建。

## 配置绑定什么

- 唯一设备 ID、名称、QEMU 路径。
- 原厂 PRG、重建 SoC ROM、完整 NAND data+OOB 底图的路径、尺寸和 SHA-256。
- 固定的增量日志路径，以及 boot mode、显式 ROM 空洞模式、电池/外接电源输入和 icount 选项。

路径相对配置文件解析，不相对当前终端目录解析；支持 Windows 绝对路径经 WSL 的 `wslpath` 转换。
跨盘或不保持原目录结构的迁移仍需调整配置中的路径，不能只移动 JSON 就假定其它文件一起迁移。
目前 QEMU 的机器参数编码不支持这些配置路径中的逗号，因此加载/创建时明确拒绝，不让逗号误变成其它参数。

启动前核对三个不可变输入，缺文件或内容不匹配直接拒绝，不静默换底图、清空日志或降级成临时 NAND。
这不是恶意宿主并发修改文件下的快照隔离：设备运行期间，不能修改或替换所引用的输入。
NAND 后端仍独立验证日志的底图身份、完整记录和排他锁，见 [NAND 增量保存](np560_nand_journal.md)。
Web 在设备信息区域显示设备名和 ID，保存状态继续取自真实后端，不以配置存在就宣称写入成功。

## 防止误用和资料丢失

- `--device` 拒绝附带另一个 ROM、底图、日志、保存导出路径或硬件配置覆盖；也拒绝 HLE、RAM 注入和初始按键注入。
  要做诊断，使用原有隔离启动方式，不把诊断参数带入日常设备。
- 可以显式使用 `-Qemu` 选择升级核心，不改写配置或资料；核心本身不做版本哈希锁定。
  必须确认新核心兼容当前日志格式/锁协议，不要使用旧的无稳定侧锁核心。
- 日志及其 `.lock` 不得与配置、固件、ROM、底图或核心文件同路径或互为硬链接。
- 同一日志的并发访问由 QEMU 已有的稳定 `.lock` 机制拒绝，不启动第二台设备来覆盖第一台。
- 若日志缺失但 `.lock` 还在，设备加载会报错，要求恢复日志，不自动从底图重新开始。
  侧锁不是完整备份；同时丢掉日志和侧锁仍无法由本配置检测，不能把它当成删除恢复机制。
- 正常关闭后再备份配置与 `.npj`，保留/备份它们引用的只读底图、PRG 和 ROM。
  不要在运行中复制正在变动的日志作为可靠备份，也不要在运行中删除/替换侧锁。
- 恢复到另一个目录时保持路径关系，或只修正路径并保留输入身份。不要为绕过不匹配错误直接更新哈希。
  已提供[设备备份与恢复命令](np560_device_backup.md)，可打包完整资料并恢复到新目录；
  尚未提供图形迁移向导或自动采用旧独立日志的命令。已有独立日志仍可用原来的启动参数继续使用。

这项实现让每次启动固定选择同一台虚拟设备，并自动持久化其 NAND 擦写；
不代表原厂所有应用的保存逻辑、USB 硬件传输、宿主物理断电和完整整机快照已经完成。

## 实现与定向检查

- `scripts/web/device_config.py`：配置创建、严格解析、输入身份和保存路径保护。
- `scripts/web/np560_web.py`：设备创建/启动入口，启动参数约束及设备身份输出。
- `scripts/run-np560-web.ps1`：Windows 配置入口；同时将固件默认路径初始化移到参数解析之后，
  并使用 UTF-8 BOM 兼容 Windows PowerShell 5.1 的中文路径读取。
- `scripts/tests/test_np560_device_config.py`：创建不复制 NAND、不覆盖设备/日志、输入变化拒绝、路径别名保护和重复加载。
  WSL 及 Windows Python 均通过。已有 Web 生命周期与前端检查在 WSL 通过。
  Windows 沙箱直接运行旧前端 Node 检查曾因 `lstat C:\Users\ASUS` 返回 EPERM 失败，
  并非输入控制器断言失败；随后在实际 WSL 环境执行通过，没有修改断言。

真实使用记录在 `tmp/np560-device-native-20260906-v1/`，具体冷启动写入/读取结果在下节维护。

## 实际原厂设置写入与进程重启读回

创建过程实际调用 Windows PowerShell 5.1 的 `-CreateDevice` 入口，产出 1,006-byte 配置，
设备 ID 为 `cddc15b6-750b-4b6a-ad36-041b6f99f70e`。
随后两次均只传 `-Device` 与端口、日志、关闭令牌等宿主参数，不传 ROM/NAND/保存参数：

| 阶段 | 实际结果 |
| --- | --- |
| writer，Web/QEMU PID 82360/82362 | 原始设置为 `sound_off=0`；通过矩阵按键进入原厂音效编辑器，选择“关”并确认；值变为 1，确认阶段新增 80 次 NAND program |
| 关闭 writer | Web/QEMU 均退出 0；日志 7,196,630 bytes，3,432 条已提交记录，没有完整 NAND 导出 |
| reader，Web/QEMU PID 82625/82627 | 新进程重放同一日志 `REPLAYED=3432 TORN_BYTES=0`；冷启动 `sound_off=1`，再次进入原厂编辑器仍显示勾选“关” |
| 关闭 reader | Web/QEMU 均退出 0；底图与配置哈希不变，日志包含此次正常启动的后续写入 |

`write-setting/report.json` 与 `read-setting/report.json` 均记录原厂操作结果及 `host_guest_memory_writes=0`。
实际读回画面为 `read-setting/10-native-readback.png`，已查看，勾选位置与配置值一致。
之后闲置时另拍的 `native-saved-setting.png` 是黑屏；其同名状态文件明确为
`DISPLAY=off SLEEP=on`，不能用它代替先前的编辑器画面，也不据此宣称电源生命周期已全部实现。

两次核心均为 `1f42a1e3d8979628810f66775c2f5219605332f1e7e580ab99af242a157545db`；
PRG、重建 ROM 和底图均与 `device.json` 中的 SHA-256 一致。
底图 SHA-256 为 `7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`，退出后重新计算不变。
配置 SHA-256 为 `ca2c529f8817b4b3eef2b30988dad8c1f8f6bc9fa1f95b1b805f9e24192bc934`，前后不变。
writer 关闭后的日志 SHA-256 为 `e55d7146e8ce51e3b45a992f60f272472db088c139719bb81d33e046b3d40670`；
reader 关闭后为 7,856,566 bytes，SHA-256 为
`5ebe68acd435dc16eaa00519414eca6cf1dfbb437608f9957c850ddd3615ec09`。

writer 与 reader 之间增加了 Web 产物清单中的配置模块身份记录，并调整未绑定设备时的提示文字，
所以两次 Web 文件哈希不同；QEMU、guest 输入及设备加载/保存逻辑相同。
此证据是同一核心上的原厂设置跨进程读回，不是“同一套前端所有功能全部通过”的整机验收。
本轮没有复制新的 553 MB NAND，也未更改用户的 8807/8808/8809。

后续已实现独立的[资料备份/迁移入口](np560_device_backup.md)，保留本篇原始设备验证的版本边界。
仍需完成：更多原生资料/游戏保存状态、图形设备管理、完整系统恢复；
此处选择音效“关”只是在验证一项原厂设置持久化，绝不表示真实声音问题已经绕过或解决。

## 2026-09-18：指令时钟配置提前校验

已复现 v2 配置允许 `instruction_clock=true` 搭配空值/非零 icount_shift，
创建时成功但实际启动被 QEMU 拒绝的问题。现创建和加载配置均提前要求 shift=0，
即使 realtime=false 也适用；不会写出新坏配置或改写旧配置。
16项设备配置检查通过，包括三个非法shift、新旧版本兼容及原有运行参数恢复。

使用本轮从原包重建的ROM和NAND，经真实WSL CLI创建
`tmp/np560-built-device-20260918-v1/device.json`，再仅用 --device 读取，
HLE=138790、arena=93952、instruction_clock/realtime=true、icount_shift=0均保留。
创建时仅验证配置读取；随后已完成下面的真实启动验证。

## 2026-09-18：新构建介质的设备重开验证

`tmp/np560-built-device-20260918-v1/boot-reopen/report.json` 记录两个顺序运行的
独立 QEMU 进程：均通过 `parse_args(['--device', config])` 加载同一个配置，
再经正式 `start_emulator` 启动。第一次创建 journal，第二次使用同一路径重开；
两次关闭后的 returncode 均为 0，外层验证进程也退出 0。

两次均无按键注入，矩阵有效读取数和映射事件数均为 0，application_state=255，
faulted=false；连续三个采样的学习顶栏均与原始资源逐像素相同（0/5280差异）。
最终截图为 `boot-0.png`、`boot-1.png`；已目视检查第二次截图，学习菜单、
开始按钮与时间可见。配置恢复 HLE=138790、arena=93952、instruction_clock=true、
realtime=true、icount_shift=0。

这验证的是“原始 PRG/UPD 重建介质 → 固定设备配置 → 冷启动 → 关闭后重开”
链路，不是新增游戏存档或设置的跨启动读回测试，也不等于所有像素、按键、应用
和音频完成验收。未替换用户试玩实例。
## 2026-09-23：NAND 导出保护启动输入与日志锁

Web 桥在启动前及每次 `save_nand` 前检查导出目标，拒绝覆盖 QEMU、PRG、
mask/SoC ROM、USB loader、烧录/驱动代码；启用 journal 时还保护 journal、
其 `.lock` 和基础 NAND。比较解析路径及已存在文件的 samefile 身份，包含
启动后新建的硬链接。不会把导出操作误当作更换固件或日志锁。

旧实现只在启用 journal 的构造阶段保护 journal/base；临时文件反例确认其余
目标此前能走到启动阶段。修复后 23 项生命周期、16 项配置检查通过，正常独立
输出仍发送原 `nand-save` 请求。这是防误覆盖，不是对恶意并发路径替换的原子
防护，也不新增整机快照。无 journal 模式的既有基础 NAND 导出语义未变。
本轮没有启动或关闭用户实例、导出真实 NAND，亦没有修改任何用户输入文件。
