# 寄存器 DSP：原厂样本增益函数恢复执行

日期：2026-09-06。范围是 DMCU CPU 的寄存器 MAC、MULS、RNDST，
不是 mask ROM 解码算法恢复，也不是原厂音乐或 NPE 声音整链完成。

## 实际依赖与修复前反例

原始 `NP560.PRG` 的 VMA03 `08:34C4..3728` 是样本增益函数：读取
`00:4A64` 的当前/目标档位、查系数表，对 signed 16-bit 样本执行乘法、累加、
舍入和饱和。它们被原厂媒体输出准备链使用，不能由宿主样本算法代替。

| 函数 | 每个样本的处理 | 关键指令 |
| --- | --- | --- |
| `08:34C4` | 一次乘积 | `08:351C BEF0 0700`，MULS.ss.r.s R7,R0 |
| `08:3536` | 一次乘积，再累加一次 | BEF0 0100 / BED0 0100 |
| `08:35AC` | 一次乘积，再累加两次 | 同类寄存器 DSP |
| `08:3626` | 一次乘积，再累加三次 | 同类寄存器 DSP |
| `08:36A4` | 一次乘积，再累加五次 | 同类寄存器 DSP |

旧核心在第一个负样本处停于 `08:351C / BEF0`，未实现这条有效指令。
反例在 `tmp/np560-mac-before-v1/`，旧核心 SHA-256：
`809aa9c349b24caaba9d22d9b158e369d0096610ea936b78e180107fcaadf9cd`。
这是原厂函数实际取指，不是返回地址损坏后将数据误当指令。

原系数表位于 PRG offset `0x3057E6`，八 word：
`0000,2027,287A,32F5,4027,50C3,65AD,7FFF`。
函数以 DS1=66 读取逻辑 D7E6，对应物理 `33:57E6`，不是 `33:D7E6`。

## 指令依据与实现

来源：[CN1916884A 原始扫描件](../../tmp/cnpatent/CN1916884A.pdf)。已目视核对 PDF
40–48 页操作/状态/编码表、130 页图 5、132 页图 7A/7B、133 页图 8。

- BE 配置字节 bits 5:4：00 内存 MAC、01 寄存器 MAC、10 RNDST、11 MULS。
  不能按第二个 word 是否为零区分 MAC/RNDST；MAC R0,R0 的操作数 word 就是零。
- 40-bit AR 由 R5 低字节 ARX、R6 ARH、R7 ARL 组成；R5 高字节为独立 SE，必须保留。
- bits 3:2 指定 ss/su/us/uu。分别解释两个 16-bit 操作数符号；
  SOCR.FR 仅在 ss 模式将乘积左移一位。
- MULS 替换 AR；寄存器 MAC 加/减乘积；RNDST 处理已有 AR，不读虚构操作数。
- `.r` 先加 0x8000，再清 ARL；`.s` 或 SOCR.MAS 按有符号值限制到
  `FF80000000..007FFFFFFF`。舍入先于饱和。
- 先读完操作数再写 AR，允许源寄存器为 R6/R7。
- 保留 PSR 的优先级、CIRQ、MX 等无关位，SE 写回经过共享寄存器边界。

入口：`qemu-dmcu/target/dmcu/helper.c::exec_mac_register`，常量在 `cpu.h`。
后续内存形式接入后，统一入口改名为 `exec_mac`，详见下文的后续边界。
`scripts/np560_disasm.py` 同步修正解码；QEMU 最小 C 反汇编器尚未增加相应助记符。
普通 MUL/UMUL 的现有寄存器行为未在此次改动中修改。

后续 `cbf6e9ea…` 核心修正了普通 MUL 忽略 SOCR.FR、MUL/UMUL 不更新 V 的问题，
仍保留 R4/R5，见 [普通乘法](np560_multiply_fractional.md)。这是独立的 CPU 修正，
不改变本篇 MAC 的运算定义，也不将尚有歧义的 C、MV/MS 等标志宣称为完全核对。

### 歧义与尚未完成的能力

手册部分示例与操作定义/字段表矛盾：K 位号印为 8..5，个别 MAC 示例漏写 round，
MULS 示例错误沿用累加/减法说明，RNDST.r 示例为 A1 但字段表要求低两位 00，
RNDST.s 示例说明也与饱和操作定义冲突。
实现采用操作定义、字段表和原厂 BEF0/BED0 交叉证据，不能称手册完全无歧义。

当前 Z/N 取存储后的 40-bit 结果，C 表示进位/借位，V 表示 signed 40-bit 溢出；
MV/MS 采用逐指令溢出/饱和标记。MV/MS 是否粘滞、MX 精确语义，以及
40-bit 溢出与舍入/饱和同时发生时的优先关系仍缺完整证据。
相关边界测试只确认当前实现契约，不证明与真机一致。

仍需实现/核对：

- 内存 MAC、`.m` 搬移、共享 X/Y AGU、Y-RAM 访问及循环/位反转寻址。
- 指令精确周期、流水/总线竞争；icount 通过不等于手册机器周期已模拟。
- 上述状态位、复合溢出，以及其它 DSP 指令的完整覆盖。

内存 MAC 当前明确报未实现，不误执行成寄存器形式；有矛盾的部分保留配置
也保持显式未支持，不能以跳过指令代替功能。

后续 `4e878c38...` 核心已实现 X0 的循环后增量，修正原厂 `28:2C74/2E04`
环形缓冲跨界读写，见 [X0 循环寻址](np560_x0_circular_buffer.md)。其它 X/Y modifier、
Y-RAM、位反转、内存 MAC 和 EXR 仍缺；本篇下面的完整 DSP 验证保持属于历史
`f989c8fe...` 核心，不与后续局部回归拼接为同版本完整验收。

再后续 `ac5f17b0...` 已支持 X0/X2 + Y2 的部分内存 MAC，原厂 `0C:7142`
64-word 处理函数可完整执行；同时修正新增指令的 TCG I/O 边界，见
[内存 MAC](np560_memory_mac.md)。本篇原来的“内存 MAC 未实现”是此前基线，
当前其余索引、可变步长、完整 Y 视图、位反转与异常仍缺。
该最终核心完整重跑了本篇寄存器 DSP 套件，记录为 `np560-memory-mac-register-v2`；
这不补全未确认的硬件语义，也不意味着音频 ROM 已恢复。

## 原厂字节验证与中间失败

`scripts/tests/test_np560_mac.py` 使用原 PRG 整段函数和原表。隔离 caller 由 guest
自己设置样本、参数及栈；宿主仅读结果，不写运行中 guest RAM，没有 NAND 或 codec 替代。
夹具将原表放入相应物理数据映射，不能算生产 ROM 数据映射修复。

`08:34C4` 的 114-byte 函数 SHA-256：
`4dc2031ffbbe732f62a0e45692c07aac9d127d4c95fbd2507abe5f9cb3f7e129`。
16-byte 表 SHA-256：
`52e48166729a45b1cb180b5027bceb5474f5733e94d60dc5a9f24005f464e949`。

第七档 x1 的实际输入与输出：

```text
input : -32768 -30000 -16384 -1 0 1 8192 16384 30000 32767
output: -32767 -29999 -16383 -1 0 1 8192 16384 29999 32766
```

首版实现的 C 条件表达式把负操作数提升为 unsigned，导致负样本全变为 +32767；
已将两条分支均显式转换 int64_t。`tmp/np560-mac-v1/` 保留失败。
该中间核心 `5f2bdd43...` 曾通过冷启动 (`np560-mac-cold-boot-v1`)，
说明桌面正常不能证明声音运算正确，不能混入最终核心验收。

`np560-mac-v2` 原厂及算术部分通过，但未实现指令测试预期故障格式写成
`PC/WORD`，实际为 `PC WORD=...`，因此脚本失败；CPU 正确停在原指令，
后续 R0=BEEF 没执行。仅修匹配格式，不放宽停机或寄存器断言。

最终 `tmp/np560-mac-v3/report.json` 全部通过：8 个原厂函数/档位场景
（含 icount）、18 个算术/别名边界、5 个保留或未实现形式停机边界。
覆盖正负样本、零档、分数乘法、多次累加、舍入、削波、SE/栈及状态保留；
不按这些测试数量折算整机进度。

## 最终同核心结果

QEMU：`E:/qemu-dmcu-build/qemu-system-dmcu`，46,567,760 bytes，SHA-256：
`f989c8fe9ea85fc33ad07e6134d9fd7e2d82abca02442e92699bccc2daf20421`。
旧核心仍在 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-register-mac-20260906`。

生产输入未修改：

- PRG：`d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`。
- `tmp/np560-system-v380-vma03-resident-codec-holes-v1.bin`：
  `a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef`。
- `E:/qemu-dmcu-build/np560-vendor-file-import-v3.nand`：
  `7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`。

`tmp/np560-mac-cold-boot-v2/report.json`：零输入严格 ROM 冷启动 102.25 秒，
最后三次顶栏差异 0/5280，ROM_MISSING/UNSUPPORTED/INVALID_CONTROL 无错误，
HLE 关闭、NAND ERROR=0；已目视 final.png 为完整学习桌面。
仅确认该启动/顶栏，不关闭跨菜单损坏或完整 NPE 缺口。

同核心 `np560-mac-ignds-v1` 的 IGNDS、`np560-mac-trap-v1` 的 TRAP 回归通过；
普通乘法寄存器保留、Python 解码及修改脚本语法检查通过。

### 音频采集独立修正

音频脚本先读 PCM，再读 CPU 完成状态；若程序在两次读取间结束，随后停机却不收取
末尾 PCM，尾阶段就被漏掉。初次回归只看到一个 (3,-3) 帧并失败。
已在停机后按连续帧序号收取尾段，保留原 200 帧下限、符号、静音、暂停及复位断言；
未改 DAC 模型、增加宿主延时或注入采样。同时失败时保存报告，样本断言前保存 WAV/CPU。

`tmp/np560-mac-audio-v2/` 普通与 icount 的原厂 `08:33FA` 渐变均通过，
(3,-3) 分别收到 975 / 960 帧；两路 DAC 各写 7 次。活动采样与 Timer2 复位也通过。
这是数字输出边界检查，不是音乐播放器/游戏 codec 验收。

## 当前真实游戏入口

`tmp/np560-mac-native-hero-v1/` 在相同核心/PRG/严格 ROM/NAND 上冷启动，
以 Start M55 → 娱乐 M53 → 游戏世界 M37 → 文件列表 M53 → Hero M53 选择游戏。
五次按键各被映射、消费一次，释放均被原厂扫描观察到。最终：

```text
PC=02:acd8 DS0=0a2 DS1=001
ROM_MISSING=02:acd8 FETCHES=1 PREV=25:dfba/bd02 SP=0d40
ROM_CALL=02:acd8 FROM=25:dfba RETURN=25:dfbe
ROM_CALL_STACK=0014,78d4,0052,8800,0000,fad8,0000,101c
INVALID_CONTROL=none
UNSUPPORTED=none COUNT=0
```

最终 LCD 仍是《英雄传奇.npe》列表，不是游戏画面。
脚本 exit 0 表示有界观察完成，不表示游戏通过；最终 ROM_MISSING 是实际阻塞证据。
自启动前的硬件写观察点没有捕获 `22:1840` 改写，仅限本次过程，
不能据此关闭历史资源/代码损坏。隔离 QEMU/GDB 均 exit 0；未保存 NAND，
未替换或重启用户 8807/8808/8809。

下一步回到 [共同 ROM 流后端](../audio/np560_resident_stream_backend.md) 的 ACD8 契约及原厂来源，
后续仍缺 AD92、B6DE/B7AA/B816/B84E。样本增益可执行不能算这些算法已恢复。
缺算法证据时，按 [整机计划](../plan.md) 推进已有依据的共同依赖，不补伪成功 RETS。
