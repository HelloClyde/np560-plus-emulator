# 三路周期定时器与原厂声音传输的位 RAM 修正

日期：2026-09-05。接续 [Timer2](np560_timer2_device.md) 与 [DTU](np560_dtu.md)。

后续：已接入 [DAC / Web 数字输出](np560_dac_web_output.md)，并修复设备与 CPU 的复位
顺序；本文的“未有 Web 输出”是当时边界。ROM codec 和完整音频硬件仍未还原。

## 实际新增能力

1. Timer0、Timer1 与 Timer2 都可执行原厂使用的 `0080/8080` 周期配置，独立计数、
   重载并产生各自 ICR 请求，共用 PLL/CLKCON 时钟选择。
2. 修正 CPU 高位地址 `BIT[80..FF]`：它们访问 `F000..F0FF` 的 128 个 DPRAM word，
   不是直接寄存器 `REG[80..FF]`。这让原厂写入的声音路由与随后读取的路由成为同一状态。
3. 未修改的原厂配置、续填、启动和停止函数，已经能通过任意两路不同的 Tx 定时器，
   把两组采样逐次搬到 `F1E0/F1E2`，无需宿主补写寄存器或给调用点加特判。

这是声音硬件数据通路的进展，不是可听音频完成。DAC 采样格式、控制位完整含义、
实际模拟输出及 Web 播放仍未实现；NPE 所需的 resident 流后端缺口也没有用空返回绕过。

## 证据和地址关系

已完整查看本地 `tmp/cnpatent/CN1916884A.pdf` 的图 2、13、22、23 所在页。
图 23 明确标注 `Tx(x=0,1,2)`、16-bit preload/counter、比较中断与自动重载；
图 13 给出以下中断映射。NP560 的控制寄存器地址和实际配置由原厂代码补足。

| 定时器 | 计数地址（布局推断） | 原厂写入的 P/C | ICR / 向量 |
| --- | --- | --- | --- |
| T0 | REG25 / F14A | REG26、REG27 | REG51 / 0048 |
| T1 | REG28 / F150 | REG29、REG2A | REG52 / 0050 |
| T2 | REG2B / F156 | REG2C、REG2D | REG53 / 0058 |

运行地址以原始 PRG 的 VMA03 为基准，文件偏移为运行地址减 `030000`。

- `24:97AC` 保存两路双缓冲地址，按参数 `[9:8]`、`[7:6]` 分别选择 T0/T1/T2，
  写入相应 TxC/TxP。`24:98BE..98DE` 设置 DTU 目的端为 F1E0/F1E2。
- `24:97F6` 把路由/状态写到 unbanked `F01C`。
- `24:9A48..9AAC` 读取 `BIT[8E]` 的 6/7、8/9、12/13 位，设置对应 ICR 的 EN/ED/通道，
  并通过 TxC bit 15 启动相应定时器。
- `24:99D2` 设置长度，`24:99F6` 标记首块可用，`24:98FC` 装填 DTUC，
  `24:9AB8` 停止定时器。上述均使用原包完整代码。
- `08:4702/475E` 的启停代码写 REG70/71/72；`08:33FA/3462` 通过 F1E0/F1E2
  读当前值，再按有符号比较逐步调整 REG70/71。它们是后续确认 DAC 格式和启停副作用的
  依据，尚不能凭此宣称所有模拟转换行为已经确定。

### 被定向验证发现的第二个错误

只有三路 timer 实现、尚未修正高位地址时，原厂 setup 写 `F01C=C100`，
但 `BIT[8E]` 仍读取独立的 `env.sfr[8E]`。两路 start 都误选 T0，第二次写 ICR51
把它分配给 DTU channel 1；结果 channel 1 完成 32 次，channel 0 保持 32、始终不传输。

修复不是给 REG8E 复制一次 C100，而是修正所有高位地址的寻址类别：

| 位地址 | 使用的硬件状态 |
| --- | --- |
| 00..6F | 对应低 SFR |
| 70..7F | 通用寄存器 R0..R15 的紧凑位别名 |
| 80..FF | DPRAM `F000 + 2*(bitaddr-80)` |

高位 RAM 访问不受当前 DS0/DS1 影响，也不能把 BIT[FF] 错当成 R15。
直接 REG8E 与 BIT8E 并非同一个地址空间。旧的 DTU 合成测试以 `MOV REG8E,0800`
准备原厂标志也随之纠正为 guest 写 F01C；原厂待测函数本身未修改。

实现使用现有内部 RAM backing。历史 board 模型仍在部分 unbanked F0xx 地址覆盖了
专用设备（例如 F010 的旧 GPIO 视图）；其与 DPRAM 的完整关系尚未闭合。
本轮没有声称所有 F0xx 视图已经一致，也没有据此关闭完整内存映射任务。

2026-09-06 后续：已由原厂声音初始化/设置/扫描闭合 F010 的软件状态归属，删除了
冲突的键盘 MMIO，恢复共享 DPRAM；见 [声音状态 RAM](np560_audio_state_ram.md)。

## 验证范围与结果

### 原厂数据传输与架构检查

- 新增 `scripts/test_np560_timers.py` 复用既有执行器；不是新增诊断平台。
- T0/T1/T2：到期置 RQ，EN/CPU IE 关闭仍锁存；直接位指令停止；pause 冻结虚拟时间，
  resume 后继续。普通运行和 icount=5 都通过。
- 原厂 `24:97AC..9BE6` 的相关完整函数：六种不同定时器配对均通过；T1/T2 另在
  icount=5 下通过。两路各 32 次传输、各一次完成，源指针 3040/4040，
  F1E0/REG70=A531、F1E2/REG71=7ABE，两个 TxC 均停止为 0080，SP 恢复 6000。
- 对照旧二进制 `pre-timers-20260905`，同一原厂 T0/T1 流程失败：两路均 0 次传输，
  DTUC 都保留 8020。这排除了只验证脚本自行制造成功的情况。
- `test_np560_bit_sfr_addressing.py`：原厂 F01C/BIT8E 共享、字节 lane、非零 DS、
  高位地址不改 R15、低 SFR/GPR 位别名、32-KiB 进位及原厂 Timer2 等待全部通过。
- `test_np560_dtu.py` 全部通过，包括原厂 1023+1 续填的普通及 icount=5 执行。
- `test_np560_interrupt_psr.py`、`test_np560_icr_vectors.py` 全部通过；构建和定向
  whitespace/语法检查通过。

### 原厂冷启动与实际操作

`tmp/np560-timers-dpram-cold-boot-v1/report.json`：97.9 秒，passed=true。
零按键、零宿主 guest-memory 写入、不保存 NAND；最后三个顶栏样本都为 0/5280 像素差异，
CPU 指令/ROM/控制流故障均为 none，NAND ERROR=0。`final.png` 已人工查看，
学习桌面、开始按钮和时间显示正常。这只证明该冷启动，不是整机或游戏完成。

同一构建的隔离 Web：`tmp/np560-timers-dpram-native-web-v1/`。
普通 120 ms 矩阵输入 Start 55、确认 53、下 37、确认 53，均被原厂前台消费，
进入 NPE 文件列表；记录在 `tmp/np560-timers-dpram-native-route-v1/`。
使用已有工具只是检验这次 CPU/设备改变对真实操作的影响，不以导航次数计算完成度。

再按确认选择《英雄传奇》，仍停在 `02:ACD8`，并没有进入游戏。
`tmp/np560-timers-dpram-native-hero-v1/01-Hero-failed.json` 记录：

```text
PC=02:acd8 DS0=0a2 DS1=001 SP=0d40 FP=0d5e
R0=0014 R1=66f2 R2=0000 R3=8800 R4=0052 R5=78d4 R6=0001 R7=0005
UNSUPPORTED=02:acd8 WORD=0f00 FIRST_PREV=25:dfba>02:acd8 WORD=bd02 EXT=acd8
```

该 Web 启动命令未启用 `--soc-rom-skeleton` 的缺口分类，所以表现为对 ROM 中已知
占位字 0F00 的 unsupported，而非前轮的 ROM_MISSING 标签。原始入口、调用者、参数和
缺口字节没有改变；不能据诊断标签不同宣布找到了新指令，也不能声称 ROM 服务已补完。
后续同类诊断应保持缺口分类配置一致。此次按键脚本以未产生新画面超时结束，应记为
游戏启动失败。结束后通过本轮 token 关闭自有 8810，未保存 NAND。

## 构建身份与保留缺口

- QEMU `E:/qemu-dmcu-build/qemu-system-dmcu`：46,456,184 bytes，SHA-256
  `b64a7a850150d80e2219f0bd875f192726be5a63fa4135a8deb6944027951dff`。
- 前版备份 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-timers-20260905`：SHA-256
  `f325a563cffd5e7e152a6d4885e941296033e8ec11fc6d7819565aea011db8e8`。
- PRG 未改：`d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`。
- guest ROM 未改：`a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef`。
- NAND 未改且不保存：`7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`。

其它 TxC 模式、ECK/SCK/TB 输入、预分频、完整 PLL/时钟树、IRQ 嵌套、DTU 竞争/周期占用、
旧固定 tick、完整 F0xx/F2xx 映射、设备迁移、音频和 ROM 后端仍未完成。
目前启动时清零计数、修改 preload 保持计数等细节沿用前轮模型，不能称为逐周期真机实测。
用户 8807/8808/8809 未被输入、重启或替换；本轮实验使用独立实例。
