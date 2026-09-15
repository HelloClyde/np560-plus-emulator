# 固定设备配置与日常持久化

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
