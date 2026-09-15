# ASR 负计数分支：移位缓冲残留修复

日期：2026-09-06。范围是 QEMU CPU 的共享算术移位实现。
这不是音频 ROM 恢复，也没有证据把历史菜单花屏或当前游戏声音缺口归因于本问题。

## 原始定义与代码差异

已目视核对 [CN1916884A 原始扫描件](../tmp/cnpatent/CN1916884A.pdf)
PDF 第 57–58 页（说明书第 54–55 页）完整 ASR 定义：

- ASR 的寄存器计数是有符号 byte，负数转为保留符号、必要时饱和的 ASL。
- 运算伪代码在判断 `count < 0` 之前执行 `V=0; C=0; SB=0`。
- 正计数的右移循环把移出的低位收集到 SB；零计数同样经过初始化。

旧 `exec_shift` 在解码后将负计数 ASR 改为内部 `SH_ASL`，但最后更新 SB 的条件
只包括 `SH_SL / SH_SR / SH_ASR`。因此负计数分支既未收集新 SB，也未清除旧 SB。
上一条移位留下的位会被后续 SLOSB/SROSB 的 OR 操作再次使用。

修复将 `SH_ASL` 纳入 SB 更新，写入本条指令初始化为零的缓冲。
没有改变既有符号、饱和、进位或溢位运算，也没有新增指令、修改原厂函数或使用地址特判。
这落实扫描件中明示的初始化；ASL 的全部标志/时序仍没有真机对照证明。

## 修复前后的可区分结果

[定向检查](../scripts/test_np560_asr_shift_buffer.py) 复用现有隔离 guest 运行器：
先执行正常 `SL R7,RB2`，将 `A55A` 移入 SB；再执行 `ASR R0,RB2`，其中
R0=`1234`、计数=`FF`（-1），最后读取 SB 并让两个零值操作数分别执行
`SLOSB #0` 和 `SROSB #0`。

| 观察项 | 旧核心实际 | 修复后实际 |
| --- | --- | --- |
| ASR 的 R0 | `2468` | `2468` |
| SB | `A55A` | `0000` |
| 后续 SLOSB 的零值操作数 | 被混入 `A55A` | 保持 `0000` |
| 后续 SROSB 的零值操作数 | 被混入 `A55A` | 保持 `0000` |

旧核心失败证据：`tmp/np560-asr-sb-before-20260906-v1/`。
其 guest 正常执行到终点，没有 ROM_MISSING、非法控制流或未知指令；失败是结果不符，
不是进程崩溃。隔离 PID 79372 已关闭，exit 0。

新核心证据：`tmp/np560-asr-sb-20260906-v1/report.json`。
同一核心的普通与 `icount=5` 模式均覆盖负计数 -1/-4/-16/-128、正负饱和、
零输入、零计数及正计数 1/2/16。每项检查实际寄存器和后续 SB 消费结果，全部通过。
所有设置由 guest 指令完成，没有 NAND、运行期宿主写 RAM 或生产 ROM 修改。

## 未修改的原厂函数回归

原 `NP560.PRG` 文件 `[0x2E8ABC,0x2E8B6A)` 的完整 174-byte 函数：

- source 地址：`4E:8ABC..8B68`，VMA03 对应 `31:8ABC..8B68`。
- SHA-256：`673873c842ad2ecf57b79141fe606d3b23d684fd47e3fc80a2a7659e54d5fd08`。
- 使用 `ASR R0,RB7; SROSB R1,RB7` 清除表中的一位，计数由参数低 nibble 得到。

隔离程序保留函数的完整原始字节、source 地址及内部调用/返回语义。
guest 将表 word 初始化为 `FFFF`，传入 `23`，函数写回 `EFFF`、返回 1，
并恢复 R1/R2/R3、FP 和 SP。普通与 icount 模式都通过。

该函数实际计数为 0..15，**只作为正计数原厂路径回归**，
不能说它触发了本次负计数缺陷，也不能把这一次位清除叫作整个原厂应用通过。

## 同核心冷启动

`tmp/np560-asr-sb-coldboot-20260906-v1/report.json`：使用同一新核心、严格缺口 ROM、
原 PRG 与已有两游戏存档 NAND，零输入冷启动，约 84.3 秒完成本次桌面回归。
连续三帧顶栏相对原 UPD 均为 0/5280 像素差异；已目视检查实际 LCD 截图。
ROM_HLE=off，ROM_MISSING / INVALID_CONTROL / UNSUPPORTED 均为 none，NAND ERROR=0。

关闭 NAND 保存，无运行期宿主写 RAM，没有复制大 NAND。QEMU PID 79534 已回收，exit 0；
外层检查命令也已 exit 0。该脚本 journal 的 phase 仍为 starting，终止依据是
`last_event=qemu_reaped`、`qemu_returncode=0` 和实际命令完成，不能仅依赖 phase 字段。
本项只证明启动与这张顶栏，没有顺便证明全部菜单交互、游戏玩法和读档。

## 构建身份与边界

新核心 `E:/qemu-dmcu-build/qemu-system-dmcu`：46,597,576 bytes，SHA-256：
`d536ba4f8fcf190d9176f9689c41c80b31f5aa62ea2b872568c8e117da548e29`。

旧核心备份 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-asr-sb-20260906`，SHA-256：
`bbe9f1c369a1ad737fcdd48b80b2b891fc34b8db5bc261ff4224880fa5e1432a`。

原 PRG SHA-256 保持
`d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`。
本次不生成或修改 resident ROM、NAND 或用户存档，也不重启 8807/8808/8809。

位反转模式仍未实现：图 10 给出了 XC/YC 的作用，但图 5/9/10 没有其 SFR 地址。
本次未凭相邻地址猜补它们。实际 NPE 的声音 ROM 缺口也保持未完成。
