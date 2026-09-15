# Timer2 周期设备与原厂等待返回

日期：2026-09-05。基础 ICR/向量见 [ICR 记录](np560_icr_vector_dispatch.md)，
原厂指令与前几轮修正见 [位寻址与等待契约](np560_timer2_and_bit_sfr_contract.md)。

后续实现已补齐 Timer0/1 的同类周期模式，并修正原厂路由使用的高位 DPRAM 寻址；
最新构建与边界见 [三路 Timer 与 DPRAM](np560_periodic_timers_and_dpram.md)。
下文 Timer0/1、DTU 未实现的结论仅指本篇最初构建。

## 本次实际新增的能力

Timer2 现在依据 QEMU 虚拟时钟计数、比较和周期重载，向 T2ICR 产生硬件请求。
原厂 `08:47A4` 的完整等待函数，由它自己安装的 RAM 向量进入原厂 ISR，倒计时归零、
恢复现场并返回；不再依靠错误位寻址提前放行，也没有由宿主修改 countdown。

同一构建从原始 PRG 冷启动，经普通矩阵按键进入 NPE 文件列表并选择《英雄传奇》，
已经越过该等待，停在仍缺失的 `02:ACD8`。这不是游戏、音频或完整 Timer/IRQ 已完成。

## 依据与实现边界

本地 `tmp/cnpatent/CN1916884A.pdf` 图 22/23 给出时钟选择、16-bit 计数/比较/重载结构，
图 12/13 给出 T2ICR 来源 3、直接寄存器 53 和向量 0058。已查看对应完整 PDF 图页。
原厂 `08:3930`、`08:4470`、`08:47A4` 补充 NP560 的实际配置关系。

| 项目 | 当前实现及证据等级 |
| --- | --- |
| T2P / T2C | 原厂明确写 REG[2C]/REG[2D]；周期预装值为 period−1，运行配置为 8080，停止可清 bit 15 |
| 周期模式 | 只实现原厂已用的控制组合 0080/8080；其它启用组合明确记录为未实现，不默认为等效周期模式 |
| 计数寄存器 | REG[2B] 按 Tx/TxP/TxC 三寄存器布局推断；尚未定位原包直接访问该 counter 的证据，地址与完整语义待核对 |
| PLL | REG[E9] 与内存 F2D2 共用状态；原厂设置函数使用两种视图，字/字节、banked/IGNDS 检查通过 |
| PLL 频率 | 由原厂频率换算推断为 4 MHz × (N+1)/(D+1)，N=PLL[12:5]、D=PLL[4:0]，再按 CLKCON[2:0] 分频；不是已取得完整 PLL 数据手册 |
| 非 PLL 时钟 | 图 22 的 24.576/16.384 MHz 分频及 32.768 kHz 选择；PLL 模式下其它选择及锁定/瞬态尚未完整确认 |
| IRQ | 周期到期置来源 3 的 RQ，即使 EN/IE 屏蔽也锁存；由 CPU 仲裁接受并清 RQ，不由定时器直接执行 ISR |

原厂 `08:3930` 先计算 `round(128 × (N+1)/(D+1)) × 31250`，再分频并除以目标频率，
所得预装值减一。模型使用该时钟比值，未把 firmware 的整数近似误当成另一颗振荡器。
正常系统现场 PLL=85E3、CLKCON=E401，对应当前模型的 Timer2 时钟 24 MHz。
该公式和控制组合仍属于原厂代码约束下的重建，未获得逐周期真机验证。

实现位于 `qemu-dmcu/hw/dmcu/np560_timer.c/.h`，使用 QEMU ptimer。
CPU 的直接 SFR 及内存 SFR 访问共用设备读写钩子；相关直接指令在 icount 下正确标记 I/O 边界。
PLL 并入现有相邻 ADC MMIO 窗口，未增加逐 bank 小别名以规避物理分派表上限。
这里的 ADC 字节访问适配不意味着完整 ADC 已还原。

当前上计数模型在周期启用时从零开始，停止后保持计数；修改比较值保留计数，比较值已越过时
按 16-bit 回绕后再匹配。后两类边界、直接 counter 写入和所有 TxC 位尚需更多原厂证据。
不能把目前采用的行为统称为已证实的硬件细节。

## 定向验证

当前二进制上实际运行：

- `scripts/test_np560_timer2.py`：PLL 视图一致；2 MHz / T2P=999 的周期配置实际置 RQ；
  EN/IE 关闭不丢失请求；停止不再到期；QEMU pause 冻结虚拟时间，resume 后继续。
  普通执行和 icount=5 均通过。
- 未修改的原厂 waiter/ISR：请求计数 3，经真实 Timer2 IRQ 归零；R4=600D、SP=4000，
  向量/寄存器由原程序恢复，T2P/T2C/T2ICR 回到零，EXPIRED=3。
  测试只附加 caller 和无关旧 tick 的 RETI fixture，没有替换原厂 Timer2 指令或用软件 RQ 冒充设备。
- 相同测试在前一二进制 `pre-timer2-20260905` 实际失败，仍停 `08:47FA`，R4=0，
  T2C=8080、T2ICR=0031；旧固定 tick 在运行，但不能替代 Timer2。
- `test_np560_bit_sfr_addressing.py` 完整检查通过，原 waiter 检查已由“正确等待缺失硬件”
  改为必须实际结束；`test_np560_icr_vectors.py`、`test_np560_interrupt_psr.py` 重新运行通过。
- 构建、定向 diff whitespace 检查及两个 Timer2 相关 Python 文件语法检查通过。

## 正常系统与游戏入口

隔离 Web journal：
`tmp/np560-timer2-native-web-v1/20260905T104514.575766Z-17204-d28d0502/`。
原厂 PRG、guest ROM 和导入 NAND 均未改写；`rom-hle=off,hle-ui=off,soc-rom-skeleton=on`。

1. 零输入冷启动后 `tmp/np560-timer2-native-initial.png` 显示正确顶栏和学习菜单。
2. 120 ms 普通矩阵按键 Start 55/B0、确认 53/86、下 37/83、确认 53/86，
   各产生一次映射事件并由前台消费，进入原厂《英雄传奇.npe》列表。
   完整记录 `tmp/np560-timer2-native-route-v1/`，截图 `tmp/np560-timer2-native-npe-list.png`。
3. 再次确认选游戏，记录 `tmp/np560-timer2-native-hero-v1/01-Hero-failed.json`：

```text
PC=02:acd8  DS0=0a2 DS1=001
ROM_MISSING=02:acd8 FETCHES=1 PREV=25:dfba/bd02 SP=0d40
ROM_CALL_STACK=0014,78d4,0052,8800,0000,fad8,0000,101c
UNSUPPORTED=none COUNT=0
INVALID_CONTROL=none
```

此时已没有 Timer2 等待。对本轮自有 QEMU PID 17206 只读检查：
Timer2 `frequency=24000000,running=false,expirations=100,unsupported_configs=0`，
REG[E9]=85E3、REG[2E]=E401、REG[2D]=0、REG[53]=0。
设备到期次数不等于每个 IRQ 都无延迟，更不能证明未实现的嵌套正确。

导航脚本最终报告画面稳定超时；诊断显示原因是上述 ROM 缺口，不能记为“游戏启动通过”。
截图 `tmp/np560-timer2-native-hero-blocked.png` 仍是文件列表，不是游戏画面。
本次正常路线未再触发代码区资源覆盖，但这一次未复现不能关闭其独立问题。
实验结束关闭自有 8810，不保存 NAND；用户 8807/8808/8809 未输入、重启或替换。

## 构建身份与后续缺口

- QEMU：`E:/qemu-dmcu-build/qemu-system-dmcu`，46,344,144 bytes，SHA-256
  `467109e10195085bfa68855f77e384f696fff7bb0e22c25cbdd4666328651126`。
- 前版备份：`E:/qemu-dmcu-build/qemu-system-dmcu-pre-timer2-20260905`，SHA-256
  `6017fd9332a4d8b88911a20fbf34fd3de4f0858e4d07d1e7ed0dfb395b3e798d`。
- ROM：`tmp/np560-system-v380-vma03-resident-codec-holes-v1.bin`，SHA-256
  `a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef`。
- NAND：`E:/qemu-dmcu-build/np560-vendor-file-import-v3.nand`，SHA-256
  `7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`。

下一个真实入口是 [ROM 流后端](np560_resident_stream_backend.md) 的 02:ACD8，随后
B6DE/B7AA/B816/B84E 仍缺。不得把 ACD8 因常量相似而替换成刚实现的 Timer2 等待。
Timer0/1、其它 Timer2 模式、完整时钟树、嵌套 IRQ、DTU、真实异常、旧 tick 清退、
设备迁移/整机快照和音频输出仍待实现。本次不是完整 SoC 完成。
