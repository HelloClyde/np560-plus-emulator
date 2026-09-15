# CLKCON 写保护：SOCR.UP 解锁与原厂时钟恢复

日期：2026-09-06。新增时钟寄存器写保护，不是声音 ROM 或完整时钟树恢复。

## 原厂与架构依据

已用 PDF 技能渲染、目视核对 `tmp/cnpatent/CN1916884A.pdf` 完整相关页：

- 第 16 页说明书明确 CLKCON 通常处于写保护状态；修改前设置 SOCR.UP，修改后清除。
- 第 132 页图 7A 给出 UP 为 SOCR bit 14。
- 第 140 页图 21/22 给出 CLKSEL 及非 PLL 频率，选择 2 为 6.144 MHz，选择 10h 为 32.768 kHz。

原始 V3.80 PRG 的代码采用 VMA03 运行地址（文件偏移为地址减 030000）：

- `0C:5154..515A`：PUSH REG2E，EE00 解锁，E12E 修改时钟选择位，FE00 锁定。
- `0C:5176..517A`：EE00，POP REG2E，FE00，恢复原值。
- `0C:6AC4..6ACA / 6AEC..6AF0` 与 `0C:6B78..6B90` 使用同样的保存、解锁和恢复约定。
- 完整函数 `24:FF92..FFD0` 保存 R0/REG2E，经 EE00 写入 E418、执行等待和另一控制寄存器操作，
  最后 POP REG2E、FE00 并恢复 R0 返回。

因此 REG2E 与 UP.14 的关系不只是按寄存器邻接位置猜测。
本次没有据此把 PLL、所有 Timer 或其它 SFR 都标成受保护寄存器。

## 修复前反例

旧核心 `a036c222…` 中，guest 先合法设置 CLKCON=2，再清 UP，尝试写 CLKCON=10h：

| 观察项 | 原本应保留 | 旧核心实际结果 |
| --- | --- | --- |
| 直接寄存器读回 | 0002 | 0010 |
| banked 715C / IGNDS F15C 读回 | 0002 / 0002 | 0010 / 0010 |
| 三路 Timer 的时钟 | 6,144,000 Hz | 32,768 Hz |

记录：`tmp/np560-clock-protection-before-20260906-v1/locked-direct-word-icountNone.json`。
断言实际失败，QEMU PID 74153 正常退出 0；不是观察超时或程序未运行。

## 实现与定向检查

`target/dmcu/helper.c::sfr_write_internal` 对 CLKCON 检查 SOCR.UP；锁定时在更改 SFR
及通知定时设备之前拒绝写入。直接字/字节、BIT、POP、banked/IGNDS 内存映射共用该路径。
解锁操作不自动清 UP，重新锁定由 guest 原厂代码负责。

`scripts/tests/test_np560_clock_protection.py` 复用现有 QEMU 启动和读状态接口：

- 锁定后的字、字节、位、POP 和两种总线映射均保持原值；同时核对三路实际 Timer 频率。
- 解锁可切换至 32.768 kHz 或 3.072 MHz，重新锁定后不能改动。
- TBC 不被这项仅属于 CLKCON 的规则误伤。
- 原厂 `24:FF92..FFD0` 完整字节执行后，CLKCON、R0、SP 恢复，UP 清零。
  另在执行前逐字节核对实际 instruction bus 中的函数内容，不以载入文件等同实际执行来源。
- 上述路径在普通运行及 icount=5 下验证；无 HLE、NAND 或宿主 guest-memory 写入。

结果：`tmp/np560-clock-protection-20260906-v1/report.json`；原厂指令总线核对结果：
`tmp/np560-clock-protection-original-code-20260906-v1/report.json`。这些定向实例均已退出 0。

旧 Timer/DTU/DAC/中断检查中的诊断 caller 曾直接写 CLKCON 而没有解锁；现给这些准备代码
加入 EE00/FE00，不修改待测原厂函数或期望频率。实际三路定时器、暂停/恢复及原厂双路传输
`24:97AC/99D2/99F6/98FC/9A1E/9AB8` 通过，七次不同路由/运行配置的两路各完成 32 次传输。
这只是修改相关的回归范围，不以测试数量计整机进度。

`tmp/np560-clock-protection-dac-20260906-v1/` 中原厂 `08:33FA` 渐变、诊断 PCM、普通/icount
以及活动复位通过；复位后音频控制清零、Timer2 停止并回到初始频率。这不是实际游戏解码音频。

同核心的 `tmp/np560-clock-protection-timebase-20260906-v1/` 与
`tmp/np560-clock-protection-ignds-20260906-v1/` 检查通过，包含真实 Timer0 请求、
原厂时基初始化/ISR 及 IGNDS 的银行隔离。两组执行脚本均已退出 0。

## 同一构建的原厂启动与保留缺口

新 QEMU SHA-256：`ecff5a4baf22683236a8de3beef04180d5feacd0c171a773c6fabc7347516ed1`。
位置：`E:/qemu-dmcu-build/qemu-system-dmcu`。

`tmp/np560-clock-protection-coldboot-20260906-v1/report.json` 保存全部输入身份。
原厂 PRG `d555609e…`、严格空洞 ROM `a243f8ba…`、原厂导入 NAND `7783876b…` 未改。
零输入冷启动通过，连续三次顶栏与原包资源零差异，现有 CPU/ROM 故障为 none、NAND ERROR=0。
已目视最终原生 LCD：学习桌面、开始、时钟完整。冷启动实例正常退出，未保存 NAND。

这证明新增保护规则没有破坏该冷启动，不证明所有应用、历史花屏或游戏都已通过。
用户 8807/8808/8809 未被操作或替换。

`02:ACD8/AD92` 及流解码器的未知契约仍在；本次资料核对没有取得其实现。
PLL 保护/锁定过程、CLKCON 其它位、休眠/唤醒、精确 CPU/总线周期仍需各自依据，
不将本次拒绝受保护写入扩称为完整时钟、电源或声音实现。
