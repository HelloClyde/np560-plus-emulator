# ST7529 命令区隔离与灰阶寄存器

日期：2026-09-07。继续完善真实 LCD 设备状态，不改变 Web 像素或原厂软件。

## 实际缺陷

原来的命令解析基本不检查 EXT。比如 EXT=1 下发送 `5C` 后写入三个 `F8`，
仍会按 EXT=0 的 RAMWR 覆盖 GRAM。真实 guest-MMIO 反例中原本的总线读回
`08 40 A8` 变为 `F8 F8 F8`；程序正常到达终点，CPU 没有缺指令或 ROM 错误。

旧核心 SHA256：`c3003ecf197eb2ac9ca4ad55912df185243840e1350e0920442970c14bbd0c55`。
反例：`tmp/np560-lcd-banks-before-20260907-v1/ext1-does-not-enable-ramwr.json`。
这证明跨命令区误执行真实存在，**不证明用户以前的菜单花屏就是由它造成**。

## 手册依据

已检查 ST7529 v1.8 完整相关页：第 36–38 页命令表/EXT、第 50 页 Gray1/Gray2。
源文件 `tmp/pdfs/ST7529.pdf`，SHA256
`8565fc8d1f917f89667d1ac3439699888f669ec0ac774438d852848371d02031`。
厂家手册的公开副本见 [ST7529 v1.8](https://crystage.com/pdf2/Sitronix/ST7529.pdf)。

- 只有 `30`（EXT=0）和 `31`（EXT=1）在两个命令区共用。
- `20` 在 EXT=0 是单参数 PWRCTRL；在 EXT=1 是 16 参数 Gray1。
- EXT=1 的 `21` 是 16 参数 Gray2；两个表每项只有低 5 位有效。
- Gray1/Gray2 分别指定奇数帧/偶数帧 PWM。它们不是两个连续地址窗口，
  不应把后 15 个参数丢弃，更不能将参数写入 GRAM。
- EXT=1 的 ANASET/EPCTIN 参数长度分别为 3/1；EXT=0 的 EPINT 为 1。

## 实现

修改 `qemu-dmcu/hw/dmcu/np560.c`：

1. 参数长度按 EXT 解码，接收缓冲从 4 字节扩为 16 字节。
2. EXT 切换仍在两个区生效；EXT=1 不执行普通 RAM、显示、休眠、窗口、扫描或部分显示命令。
3. 完整接收 Gray1/Gray2 后各自保存 16 个 5-bit 值。两个表独立，重新编程不会串表；
   PB16 后的额外数据不回绕、不溢出到 GRAM。
4. 设备复位清除“已编程”标记；没有依据的复位调色表显示为 `unknown`，不伪造厂商默认值。
5. 只读 `lcd-state` 增加 `PARAM=i/n`、`GRAY1`、`GRAY2`，并明确 `PWM=unmodeled`。

对未定义命令不再套用另一命令区的功能；没有声称复现芯片对所有保留编码的电气行为。
中途打断 16 字节灰阶命令的硬件提交时点没有找到明确依据：本实现只提交完整表，
测试只断言第 15 字节后的接收进度，不将部分提交语义列为已还原。
ANASET/EEPROM 这里只接收正确数量参数，模拟电路、EEPROM 操作仍未实现。

## 验证与原厂使用

新核心：`E:/qemu-dmcu-build/qemu-system-dmcu`，46,832,888 字节，SHA256
`d26b7ce7f17c8345a2a2604a1c18c7c960549640ae0ebebb8458f8ea5e577372`。
旧核心保存在 E 盘同目录 `qemu-system-dmcu-pre-banks-20260907`。

`scripts/tests/test_np560_lcd_command_banks.py` 复用现有 guest-MMIO 运行器：

- 跨区写显存、显示控制、窗口/扫描、部分显示隔离；
- 双表 16 项、未使用高位屏蔽、同码不同区、重编程与额外数据；
- 第 16 参数的接收边界，以及 ANASET 的参数长度。

普通时钟与 icount=5 各 9 项通过；证据分别在
`tmp/np560-lcd-banks-20260907-v1/`、`tmp/np560-lcd-banks-icount-20260907-v1/`。
这些是数字寄存器、GRAM 与命令隔离检查，不是 PWM 光学验证。
已有反色 7 项及 RAMRD/RMW 15 项也在新核心通过，证据在对应
`tmp/np560-lcd-banks-polarity-20260907-v1/`、`tmp/np560-lcd-banks-rmw-20260907-v1/`。
随后扫描 9 项、部分显示 12 项、像素格式 12 项回归也全部通过，证据在对应
`tmp/np560-lcd-banks-scan-20260907-v1/`、`tmp/np560-lcd-banks-partial-20260907-v1/`、
`tmp/np560-lcd-banks-formats-20260907-v1/`。这些目录保留各 guest 退出结果。

从既有、只读的双游戏原生存档 NAND 冷启动原厂 V3.80：

- 无按键、无宿主 RAM 写入、HLE 关闭、不启用保存或 journal。
- 约 87.1 秒取得连续三次顶栏 0/5280 差异；最终真实 LCD 浅底深字、文字布局正常。
- 原厂实际送入的 Gray1、Gray2 都是
  `00,02,04,08,0a,0c,0e,10,13,15,17,18,19,1b,1d,1f`，没有在模拟器中硬编码该表。
- 最终采样无 ROM_MISSING、INVALID_CONTROL、UNSUPPORTED 或 NAND 错误。
- 证据：`tmp/np560-lcd-banks-boot-20260907-v1/report.json`、`final.json`、`final.png`。
  进程由既有采样器正常关闭；未启动或替换用户 Web 实例。

## 仍缺少的真实行为

**灰阶寄存器有了，不等于灰阶输出完成。** 本轮不改变上一轮已修正的输出极性。
仍需查明并实现 32 级 GRAM 码对 16 项表的 FRC 选择、奇偶帧时序、PWM 驱动和光学响应。
不能直接用一次 guest 刷屏计数充当 LCD 的物理扫描帧时钟：第 29 页明确两者独立。
也不能仅为匹配一张图就选择平均值、插值、偏移或某一张表作为替代。

完整 LCD、原厂音频、全部 NPE 玩法和 M1–M6 都仍未完成，参见 [主计划](plan.md)。
