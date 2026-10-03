# 原厂设置保存与普通 Reset 保留 NAND

2026-09-06 追加：无需退出导出完整 NAND 的增量保存，以及 SIGKILL 后的原厂设置读回，
见 [NAND 增量保存](np560_nand_journal.md)。本篇下述历史实验仍使用其各自的保存方式和构建。

日期：2026-09-06。原厂音效开关已通过确认、同进程 Reset，以及保存 NAND、结束进程、
从保存文件冷启动后的界面读回。范围仍是这一项设置，不代表所有资料或音乐/NPE 解码完成。

## 结果

修复了 `np560_machine_reset()` 在 checkpoint 模式重新加载初始 NAND 的错误。
原厂界面选择音效“关”并确认后，新核心 Reset 能正常回到桌面，再打开设置仍勾选“关”。
旧核心相同设置确认后为 1，Reset 后被恢复为 0。

| 阶段 | 旧核心 97094f4a… | 新核心 4b70b03e… |
| --- | --- | --- |
| 未修改的冷启动 | 开，配置值 0 | 开，配置值 0 |
| 原厂界面选择关、确认 | 配置值 1，发生 NAND 写入 | 配置值 1，发生 NAND 写入 |
| 普通 Reset 后 | 配置值 0，保存丢失 | 配置值 1，原厂启动代码读回 |
| 重新打开原厂音效开关 | 本项旧记录未再次打开 | “关”旁显示勾选，配置值仍为 1 |

不能把只保留 RAM 误当作保存成功：本次未改原有复位 RAM 快照恢复逻辑。
复位后 `03:0164` 先将 `50:B87A` 清为 0，随后原厂 `22:9A1A` 读回 1，
`29:C246` 保持 1；不是宿主把值写回 RAM。

## 原厂操作与保存路径

从冷启动“学习”桌面，以普通矩阵电平依次：右四次 → 下 → 确认进入发音设置 →
下四次 → 确认进入音效开关 → 下选“关” → 确认。
实际矩阵位置是右 M29、下 M37、确认 M53。复位后重新沿相同路径打开设置，未再修改选项。

这次使用固定请求 150 ms 的物理接触，经过原厂扫描、消抖、映射和前台消费，
没有单扫描注入、修改事件槽或改写配置。宿主/API 调度会影响实际墙钟接触时长，
不能将请求时长称为真机硬件的精确门槛。

动态记录确认：

- 原厂 `14:BB48` 将物理配置 `50:B87A` 从 0 写为 1，`14:BB50` 读到 1。
- `14:BB74` 的资源写入参数为源 `0000:0F98`、资源 `0010:D016`、长度 1、内容 `01`。
- 原厂资源写入链返回，`PROGRAMS` 从 10,755 增至 10,835，`ERASES` 从 11,441 增至 11,443。
- 新核心复位和重新打开设置时，无 ROM_MISSING、UNSUPPORTED、INVALID_CONTROL，NAND ERROR=0。
- 重新打开后的原生 LCD 已实际查看，勾选从“开”移到了“关”；不是只靠内存值判断画面。

因此此配置与真实原厂“音效开关”有动态证据关联。通过正常设置关闭音效，
与旧实验镜像直接强改 gate 是不同路径；本次没有用它绕过声音来宣称 NPE 完成。

## 代码改动

- `qemu-dmcu/hw/dmcu/np560.c`：删除普通复位中的 `np560_load_nand_image(s)`。
  初次机器创建仍加载输入 NAND；复位只重置 NAND 控制器和诊断计数，保留 data/OOB。
  继续按 CPU → TB/TLB → 外设的既有顺序复位，未改变 RAM 和 action code/UI 快照恢复。
- `scripts/tests/test_np560_web_frontend.py`：纠正旧测试中“Reset 必须重载 checkpoint”的错误预期，
  保留初始化加载和 CPU/外设顺序约束。22 项测试通过；首次沙箱运行中的三个 Node 路径访问
  EPERM 在允许读取工作区的环境复核后通过，没有为此修改前端功能。
- `scripts/probe_np560_native_settings_reset.py`：复用已有矩阵、LCD 和内存只读接口，
  保留原厂确认与复位读回的定向复现；配置未写入、NAND 未编程或复位丢值均返回失败。

“恢复实验基线”不能冒充设备 Reset。旧说明已在
[复位与历史压力证据](../cpu/np560_reset_and_input_stress.md) 中纠正；历史 APP=007E 问题若再出现，
应调查真实启动/FTL/应用状态，不得用丢弃保存来绕开。

## 构建与证据

新 QEMU `E:/qemu-dmcu-build/qemu-system-dmcu`：46,597,744 bytes，SHA-256
`4b70b03ecc9a1212a458051d113f1d741ac5b6d136ba7178ae490e5c5fa2634a`。
旧核心 SHA-256 `97094f4ac11498050c7c444ec75339898a905cba6d0ffe4ff64038aa4c58af4e`。

两次输入相同：

| 输入 | SHA-256 |
| --- | --- |
| 原厂 NP560.PRG | d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5 |
| resident-codec-holes-v1 ROM | a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef |
| vendor-file-import-v3 NAND | 7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413 |

- 旧证据：`tmp/np560-native-settings-20260906-v2/13-effect-confirm*` 与 `19-after-reset*`。
  该目录中 14–18 的游戏路线文件名只是当时的计划标签，画面实际未进入 NPE，不算游戏证据。
- 新证据：`tmp/np560-native-settings-20260906-v3/probe/report.json`、`06-after-confirm*`、
  `08-after-reset*`、`10-native-readback*`。
- 新隔离进程记录：`tmp/np560-native-settings-20260906-v3/process/20260905T191822.347250Z-52209-12d5d116/`。
  端口 38933；上轮隔离端口 35641 也已关闭。两轮 QEMU 均确认退出，未操作用户端口。
- 上述 Reset 实验未启用 NAND 保存到宿主文件，未创建新的大型 NAND 镜像；结束后重新计算输入 NAND 哈希，保持不变。

复现时先用同一组输入启动一次独立 Web 实例，再将实际 URL 传入：

```powershell
python scripts/probe_np560_native_settings_reset.py --url http://127.0.0.1:PORT `
  --package 'NP560+V3.80版系统升级程序/NP560+.upd' `
  --output tmp/np560-native-settings-reset-NEW --allow-input-and-reset
```

探针会操作并复位目标，只用于全新隔离实例；不会自动关闭服务，结束后由启动者关闭。
输出目录必须未存在。不能把已结束的 38933 当作固定服务端口。

## 追加：设置落盘与全新进程冷启动通过

使用相同 `4b70b03e…` 核心、原始 PRG 和 resident ROM，未新增 CPU 或 ROM 补丁：

1. 独立 writer 从原 `vendor-file-import-v3.nand` 启动，普通矩阵设置音效为关并确认。
   原厂写入使 PROGRAMS 增加 80；配置从 0 变为 1。
2. writer 配置 `--nand-save-on-exit` 为事先确认不存在的独立 E 盘路径，正常关闭 Web 服务。
   NAND data/OOB 由现有 QEMU 保存接口输出，writer QEMU PID 53557 退出码 0。
3. 保存文件长 553,648,192 字节；独立 reader QEMU PID 54105 直接以此文件作为 NAND 输入，
   没有原进程 RAM、CPU 状态或整机快照，也没有再次写入音效设置。
4. 原厂启动从清零配置读回 1；重新进入音效页面仍勾选关。reader 未启用落盘，结束后退出码 0。

输出：`E:/qemu-dmcu-build/np560-native-settings-persist-20260906-v1.nand`，SHA-256
`6abc62e96dd73322532f122029536418bfefc2f85bd82be89cbf3935bf2028d8`。
reader 的运行身份记录中 NAND 路径、大小和哈希与此一致；结束后再次计算哈希未改变。
原始输入 NAND 仍为 `7783876b…48e413`。只增加这一个必要的验证镜像，未覆盖用户镜像。

证据根目录：`tmp/np560-native-settings-persist-20260906-v1/`：

- `write-setting/report.json`：mode=set-off、passed=true、原厂确认和 NAND 写入。
- `writer-process/20260905T192756.790532Z-53550-1bc2d35e/status.json`：旧进程退出事实。
- `read-setting/report.json`：mode=read-off、passed=true、新进程身份和保存文件身份。
- `read-setting/10-native-readback.png`：已查看的原厂勾选“关”画面。
- `reader-process/20260905T193113.464267Z-54098-4d03808a/status.json`：新进程退出事实。

复用原探针，writer 执行 `--mode set-off`，关闭后再对新 reader 执行 `--mode read-off`。
这两个模式本身不管理进程和保存文件，因此不能仅凭两个 passed 标记推断跨进程保存；
必须像本次一样核对退出状态、保存产物和新实例输入身份。

reader 后续还用于定位 [NPE 原生存读档](../games/np560_npe_native_save.md)。它未启用落盘，
所以此保存文件只保留音效设置，不包含后续在 reader 内创建的游戏进度；不要把它当作游戏存档镜像。

## 未完成边界与下一步

后续 [游戏第一槽](../games/np560_npe_native_save.md) 已完成非默认位置的落盘与全新进程原生读回；
其它设置、资料和完整游戏状态仍须继续覆盖。
本项不证明异常断电恢复、原机复位寄存器、全部 RAM 行为、音频解码或完整设备生命周期。
