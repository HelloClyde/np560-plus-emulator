# 设备资料备份与恢复

日期：2026-09-06。已接入 Windows PowerShell / WSL 命令入口。
这是日常设备资料管理功能，不是调试 RAM 快照，也不修改固件、ROM 服务、游戏状态或原厂存档格式。

## 使用方法

先正常关闭要备份的设备。选择已有的父目录，备份文件名和恢复目录必须尚不存在。
设备须已至少启动并正常关闭一次，具有已初始化的增量日志及稳定锁文件。

```powershell
.\scripts\manage-np560-device.ps1 -Device E:\NP560\main.json -BackupTo E:\NP560\main-backup.zip

.\scripts\manage-np560-device.ps1 -RestoreFrom E:\NP560\main-backup.zip -RestoreTo E:\NP560\restored

.\scripts\run-np560-web.ps1 -Device E:\NP560\restored\device.json
```

恢复时可指定 `-Qemu` 选择已安装核心，默认沿用项目现有的 E 盘开发构建路径。
备份只包含设备资料，不打包 QEMU、Python 或 Web 程序；迁移到另一台电脑时，先安装这些运行依赖。
备份中的旧 QEMU 路径不会决定恢复时运行哪个可执行文件，必须使用当前选定的安装路径。

WSL/Linux 的对应入口为：

```text
python3 scripts/np560_device_backup.py backup --device DEVICE.json --output BACKUP.zip
python3 scripts/np560_device_backup.py restore --backup BACKUP.zip --output-directory NEW_DIRECTORY --qemu QEMU
```

不支持直接用 Windows Python 忽略 POSIX 锁运行；Windows 入口会经 WSL 调用，
与当前 QEMU 日志锁处于同一文件系统/锁环境。不会打开浏览器或自动重启任何设备。

## 备份内容

ZIP 中只有固定成员：原厂 PRG、重建 SoC ROM、完整 NAND data+OOB 底图、增量日志和清单。
清单保存设备 ID/名称、硬件设置、输入尺寸/SHA-256、日志尺寸/SHA-256、创建时间和源核心身份。
文件位置规范化为相对路径；不把研究目录或其它无关文件带入备份。

恢复后目录为：

```text
restored/
  device.json
  media/
    firmware.prg
    soc_rom.bin
    nand.nand
    device.npj
    device.npj.lock
```

设备 ID 保留，表示恢复同一台虚拟设备。源设备也不会被删除或替换；
若恢复后两份同时继续使用，它们的日志各自独立，未来资料可能分叉，不提供自动合并。
锁状态不进备份，恢复副本创建新的空锁文件，由新 QEMU 进程取得锁。

压缩包可能远小于底图，但恢复仍需要一份完整设备资料空间。
恢复前检查解压所需大小并预留 32 MiB；不能保证其它进程随后不消耗磁盘。
建议使用 E 盘等有足够空间的目录，避免再向接近满的 C 盘复制完整 NAND。

## 安全与一致性边界

- 备份先验证配置中的输入身份，再取得 QEMU 同协议的 POSIX byte-range 读锁，
  同时保护稳定侧锁和当前日志 inode。不是不与 QEMU 互斥的 BSD `flock`。
  活动中的 QEMU 持排他锁，因此备份会拒绝；备份期间新的 QEMU 也不能写入该设备。
- 锁内从同一日志文件描述符读取，避免 POSIX“关闭同 inode 任意描述符会释放进程锁”的陷阱。
  备份不创建缺失的源锁/日志，不将未初始化设备误标成资料丢失后的重置设备。
- 逐文件流式压缩、计算 SHA-256、检查源文件身份/尺寸/修改时间，并核对日志头属于同一 NAND 底图。
  不在内存中复制整个 NAND，也不先导出另一份完整镜像。
- 恢复只接受固定成员名及路径，拒绝缺失/重复成员、符号链接、加密包和越界路径。
  对每个成员校验解压大小和 SHA-256，重新验证设备配置与日志底图配对，再发布完整目录。
- 正式备份文件和恢复目录均不得存在；即使目标在最后一刻被另一个进程创建，也不能覆盖。
  失败的私有临时目录会清理，原设备保持不变。
- Linux 使用 `renameat2(RENAME_NOREPLACE)`。E 盘 DrvFS 实测不支持此操作：
  文件改用不覆盖的硬链接发布，目录改用 Windows 原生 `Directory.Move`；
  后者只允许同父目录的专用恢复暂存目录移动到新目标，不合并或替换已有目录。

SHA-256 可检测意外损坏和与清单不符，不是原厂真实性签名，也不抵御恶意宿主同时替换文件。
备份/恢复不修复已有坏存档，不解释或改写增量日志记录；完整记录 CRC/序号和原厂资料语义
仍由 QEMU 重放与原厂应用检查。已存在的 ROM 空洞也随备份原样保留。
文件内容提交和“不覆盖式发布”不等于已证明宿主突然断电下所有文件系统元数据都持久化。

## 实际设备迁移记录

源设备：`tmp/np560-device-native-20260906-v1/device.json`，
ID `cddc15b6-750b-4b6a-ad36-041b6f99f70e`，来自先前通过原厂界面保存音效设置的隔离设备。
原厂写入/跨进程读回的历史依据见 [固定设备配置](np560_device_config.md)，并非为了本功能新造的 RAM 状态。

本轮通过真实 Windows PowerShell 入口完成：

- `E:/qemu-dmcu-build/np560-device-backup-20260906-v1.zip`：29,826,877 bytes，
  SHA-256 `0c9b7084f5d29815ea7adda465d5877765693bc63c89466c6dd70c7cfbe254c3`。
- 源日志 7,856,566 bytes，SHA-256 `5ebe68acd435dc16eaa00519414eca6cf1dfbb437608f9957c850ddd3615ec09`；
  备份与恢复输出记录的日志身份相同。源配置 SHA-256 `ca2c529f8817b4b3eef2b30988dad8c1f8f6bc9fa1f95b1b805f9e24192bc934`，未修改。
- 恢复目录 `E:/qemu-dmcu-build/np560-device-restored-20260906-v1/`，配置 847 bytes，
  三个输入均位于 `media/`，QEMU 路径为相对的 `../qemu-system-dmcu`，可用正常 `-Device` 入口启动。
- 核心 `e078605f59f6c425004a8e9f1ef4bea36222c00aecbbc0dadb7057c87af40276`，
  PRG / ROM / NAND 底图仍分别为 `d555609e…` / `a243f8ba…` / `7783876b…`。
- 只为实际恢复新增了这一个完整 NAND 副本，位于 E 盘；没有在 C 盘生成完整 NAND。

首次真实备份因 DrvFS 返回 EINVAL 而失败，目标不存在、暂存已清理；
随后修正发布方式后才成功。不能把首次失败写成通过，也没有通过放宽“拒绝覆盖”来修复。
`scripts/tests/test_np560_device_backup.py` 的小型夹具分别在 Linux 临时盘和实际 E 盘运行，
覆盖数据保真、进程锁、目标竞争、错误底图、损坏成员、路径越界和重复/符号链接成员。

恢复副本的原厂启动/设置读回记录在 `tmp/np560-device-backup-native-20260906-v1/`。
这是资料迁移证据，不是 NPE 解码、有声游玩或所有应用保存均已完成的证明。

### 原厂冷启动与读回结果

恢复副本通过已有 `run-np560-web.ps1 -Device` 启动，未传诊断启动参数或手工注入 RAM。
Web/QEMU PID 为 83458/83460，随机端口 45655，run ID 为
`20260906T061516.628877Z-83458-00da5d9d`，输入路径全部指向恢复目录的 `media/`。

- 原厂冷启动后 `sound_off=1`；经实际矩阵按键进入原厂音效编辑器，仍为 1。
  已查看 `read-setting/10-native-readback.png`，画面明确勾选“关”。
  `read-setting/report.json` 为 passed，记录 `host_guest_memory_writes=0`。
- NAND 增量后端实际 `REPLAYED=14827 TORN_BYTES=0`，原厂启动后 `SEQUENCE=26092`，NAND ERROR=0。
  快照里的 `nand_save_enabled=false` 仅表示没有整份 NAND 退出导出，不是增量持久化关闭。
- 在这个 QEMU 确认存活并持锁时，实际再调用备份入口，返回
  `Device is in use; close it before backing up`，命令退出 1。
  目标 `np560-device-backup-live-must-not-exist-20260906-v1.zip` 始终不存在。
- 读回结束后，核对 run ID/PID，再用本轮专属令牌正常关闭；Web、QEMU 和启动工具会话均退出 0，
  生命周期记录为 stopped。没有遗留本轮运行实例，没有操作 8807/8808/8809。
- 恢复副本因正常启动而新增日志记录，退出后日志 8,516,502 bytes，SHA-256
  `779d234d06454e3161df9aaf2344f4b601c98fd072e7e50cdee848002dd828b4`。
  原配置、源日志及备份包再次核对后仍为上文相同哈希，源资料没有随副本启动而改变。

此设备的原厂设置写入发生于较早核心，备份/恢复及本次读回使用 `e078605f…`；
这里证明原资料被原样迁移并可由当前核心原厂读回，不冒充同一最终发布版本全部功能的验收。
音效“关”是被保存/恢复的原厂设置，不是本轮新增的声音绕过。
