# TBC 时基与软件计数器归属

日期：2026-09-05。后续于 [ICR 嵌套](np560_interrupt_nesting.md)。
本项清退旧板级固定 tick，不新增 ROM 算法，也不把冷启动成功算作完整游戏成功。

## 修复了什么

旧板级模型无条件产生 64 Hz 请求，CPU 直接跳到 `08:40D0`，不经实际向量和 TBICR。
它还把 `0494/0496/0498` 覆盖成三个特殊倒计时 MMIO，宿主自行递减。
但原厂 ISR 已经负责递减这些软件变量；旧 MMIO 与内部 SRAM 的内容甚至不是同一份。

现在由 guest 配置 TBC，时基到期锁存 TBICR.RQ，CPU 按已有 ICR/PSR/IE 规则进入
guest 安装的可执行向量。三个计数器恢复为普通共享 RAM，仅原厂指令负责修改。

## 原厂证据

原始 `NP560.PRG` 按 VMA03，文件偏移 = 运行地址减 `030000`。

| 原厂代码 | 已确认行为 |
| --- | --- |
| `2D:7DD2` 后的初始化链 | 以 `40D0, 0008, 0010` 调用 `32:81D4`，然后调用 `32:DC20` |
| `32:81D4..8202`，偏移 `2F81D4` | 将 trap 号左移两位，写入可执行 SJMP；trap 10 得到 `00:0040 = AD08 40D0` |
| `32:DC20..DC64`，偏移 `2FDC20` | 清 F01E 和软件状态；DS0=1，通过 715E 写 `8009`，通过 71A0 写 `0031` |
| `08:40D0..4278`，偏移 `0540D0` | 保存现场；增加 0490/4B40；非零时递减 0494、0496、0498；由 guest 自己返回 |
| `08:411C` 起 | 检查 BIT8F.0，即共享 DPRAM F01E 的回调 guard；已设置则不重入单槽回调保存区 |

本地 `tmp/cnpatent/CN1916884A.pdf` 已渲染并查看完整相关页：

- PDF 第 137 页图 13：TBICR 是 REG50 / F1A0，trap 10，向量 0040。
- 第 141 页图 24：TBC 的 TBON 是 bit 15，B[3:0] 选择频率。
- 第 142 页图 25：选择值 0..14 对应 `32768 >> B` Hz；15 为未使用。
- 第 16 页说明书：独立时基范围为 2..32768 Hz，与三路通用 Timer 分开。

因此原厂的 TBC=8009 是开启 64 Hz；TBICR=0031 是 EN=1、优先级 3。
这些地址、配置和频率不是根据菜单速度猜出来的。

## 实现

- `qemu-dmcu/hw/dmcu/np560_timer.c/.h` 增加独立 timebase，使用 QEMU 虚拟时间。
  不随 PLL/CLKCON 改变；TBON 和选择位控制启停、频率。EN/IE 屏蔽只影响接收，
  不阻止时基锁存 RQ；停止不清 RQ。
- TBC 接入共享 SFR 读写路径及 icount 的设备访问边界，原厂 banked 715E 写入直接生效。
- 删除 `np560.c` 的固定 tick 定时器和三个计数器 MMIO；诊断改为只读 SRAM。
- 删除 CPU 的 legacy 请求及固定 `08:40D0` 跳转；所有当前硬件请求经 ICR。
- 删除旧回调 `08:41E0` 的地址特判；RETI 是否结束当前硬件层以实际帧 SP 判断。
  guest 的 synthetic RETI 及回调 guard 自己执行，不由宿主修复保存区。
- 增加只读 `timebase-state`。为旧工具兼容保留 `IRQ64` 字段名：TICKS/REQUESTS 现在
  是实际时基到期次数，未必为 64 Hz；ENTRIES/RETURNS 仍包括所有 CPU 中断来源。

时基使能或选择值改变时从完整周期重新开始，相同相关位的重复写入不重启。
**重编程的精确相位是当前模型假设，资料尚未规定清楚，不能称为真机测量结果。**
未使用选择值 15 不产生事件并记录 unsupported 配置，不擅自解释为另一种频率。

## 行为差异与验证边界

`scripts/test_np560_timebase.py` 的外围是明确诊断 guest，原厂初始化/ISR 片段保持原字节。
宿主只读取结果和控制运行/暂停/复位，无 guest RAM 写入、无 NAND。

| 场景 | 结果 |
| --- | --- |
| IE=0 写 100/200/300，以实际 Timer0 等待约 250 ms | 旧构建读回 84/184/284，原始 SRAM 仍为零；新构建保持 100/200/300，RAM 同值 |
| TBC 关闭 | 无时基事件，软件变量不被宿主扣减；普通与 icount 均通过 |
| 32768、64、2 Hz 配置 | 启停、选择频率及 RQ 锁存通过；这里不是逐周期物理测量 |
| 原厂向量安装、时基初始化、ISR | 实际执行四次 ISR；100→96、3→0、0→0，向量 AD08/40D0，SP 回到 6000，BAD=0；普通与 icount 一致 |
| 暂停及活动设备复位 | 暂停不推进；复位后控制、ICR、到期计数清零，时基停止 |

原厂 ISR 的窄检查由诊断 guest 设置 F01E guard，故只验证 ISR 计数及返回，不冒充完整
应用回调验证。独立冷启动及下面的菜单操作使用完整现有 guest ROM，没有这项诊断设置。

反例保留在 `tmp/np560-timebase-before-v1/`；新结果在 `tmp/np560-timebase-v2/report.json`。
首轮 `v1` 的原厂检查曾误读后续日志的同名 R9 字段，真实 CPU 头部一直为 40D0。
修正测试只解析寄存器头部后通过；没有为通过断言改变 CPU 或原厂指令。

同一新二进制还通过：ICR 向量/屏蔽、PSR 硬件与 synthetic 返回、嵌套/真实定时抢占、
三路周期 Timer、六种原厂双路传输和 icount、原厂 DAC 渐变及活动中复位。
旧 PSR 检查已改为显式配置 TBC/TBICR 和 ROM 向量，不继续依赖删除的隐式 tick。
嵌套记录在 `tmp/np560-timebase-nesting-v1/`，数字音频记录在 `tmp/np560-timebase-audio-v1/`。

零输入冷启动 `tmp/np560-timebase-cold-boot-v1/report.json` 通过，约 49.4 秒；
最后三个顶栏样本均 0/5280 差异，CPU/ROM/控制流及 NAND 现有故障项正常。
已目视 final.png，桌面、学习菜单和时间正确。这不关闭间歇性花屏或完整游戏项目。

## 同版实际菜单到游戏入口

隔离 Web 记录在 `tmp/np560-timebase-native-web-v1/`。首次截取时 guest 已显示
“每日一句”，通过物理取消键 M45/80 退出，正常回到学习桌面和 08:01 时钟；
记录在 `tmp/np560-timebase-native-dismiss-v1/`。

随后普通 120 ms 矩阵输入 Start M55/B0、确认 M53/86、下 M37/83、确认 M53/86，
均由前台消费，进入原厂 NPE 文件列表。`tmp/np560-timebase-native-route-v2/`
保留每步状态；已目视 `05-list-settled.png`，显示“英雄传奇.npe”。
没有使用单扫描诊断脉冲或宿主语义菜单动作。

再按确认选择文件，游戏未能启动。`tmp/np560-timebase-native-hero-v1/01-Hero-failed.json`：

```text
PC=02:acd8 DS0=0a2 DS1=001 SP=0d40 FP=0d5e
ROM_MISSING=02:acd8 FETCHES=1 PREV=25:dfba/bd02
INVALID_CONTROL=none
UNSUPPORTED=none COUNT=0
```

因此当前构建仍被既有 ROM 流后端缺口阻塞，不是本次新增指令故障。
按键工具最终以没有后续 LCD 帧超时，故此项明确记为失败，不能把前面的文件列表通过
写成游戏通过。返回地址诊断 BAD=0，也不证明所有其它运行场景都没有损坏。
实验结束使用本轮 shutdown token 关闭自有 8810，不保存 NAND；用户旧端口未操作。

## 构建身份及未完成项

QEMU `E:/qemu-dmcu-build/qemu-system-dmcu`，46,561,624 字节，SHA-256：
`4e9048cc58ce6f72ec14d7681eabb15da7a25b9cc35c7af2b73262a490d131c4`。
前版保留为 `qemu-system-dmcu-pre-timebase-20260905`，SHA-256：
`b3f4483ae168926bbef2a428a267c52ac8a9c64868d84a4b8c6177a88537149f`。

PRG `d555609e...`、重建 guest ROM `a243f8ba...`、文件 API 导入 NAND `7783876b...`
均未修改。完整输入身份在冷启动报告与 Web 运行 manifest 中。没有生成或保存大 NAND。

清退旧 tick 不代表完整中断模型：CIRQ 文档歧义、同级仲裁、异常/IREP、SP/FP 历史延后
保护、精确时序、其它时钟模式与整机迁移仍待闭合。计数器归属已修正，但未证实菜单损坏
仅由它导致。ROM 流后端、原厂音乐、NPE 完整玩法和持久保存仍按 [计划](plan.md) 推进。
