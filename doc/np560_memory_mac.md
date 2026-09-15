# 内存 MAC：原厂 64-word 处理函数恢复执行

日期：2026-09-06。当前只实现有依据的部分内存 MAC / X-Y 寻址，
不是完整 DSP、图像解码、原厂音频 ROM 或 NPE 游戏完成。

同日后续核心 `97094f4a...` 已统一普通 Y 指针与 MAC 的内部 Y-RAM 视图，
见 [普通 Y 指针](np560_y_pointer_memory.md)。下文“完整 Y 指针内存视图仍缺”属于本篇初始构建边界；
其余 modifier、可变步长和异常等缺口仍保留。

同日后续 [普通 AGU 写回修复](np560_agu_writeback.md) 将预先计算下一地址的规则应用到
普通 MOV、内存移位及间接读取，避免本条写入 modifier 自身后重新计算；原厂 64-word
函数及本篇 `.m` MMIO 反例在新核心上回归通过，未扩大 modifier 映射或声音恢复范围。

## 原厂有效指令与修复前现场

原始 `NP560.PRG` 的 VMA03 `[0C:7142,0C:71B2)` 是完整的 112-byte 函数，
SHA-256 `e05172d6f09fbe83628b3a6ae6ff3377be59267f1717cb7100bba06eb23a2650`。
有同段直接调用者 `0C:6634`，函数用 near RET 返回。

原厂函数读取描述符，以 `REG[17]=0`、`REG[1D]=0` 设置寻址状态，
从描述符取得 X2（R10），设置 Y2（R14）=`85D2`，执行 64 次循环：

```text
0C:7196  AE3F 71AA  REPB #3F, end=71AA
0C:719A  4850       MOV R5,#0
0C:719C  4870       MOV R7,#0
0C:719E  4860       MOV R6,#0
0C:71A0  BE0C 0606  MAC.uu [X2++],[Y2++]
0C:71A4  4D6C       SR R6,#C
0C:71A6  5D7C       SROSB R7,#C
0C:71A8  1A27       MOV [R2++],R7
```

此分支结果是每项 `(unsigned16(X) * unsigned16(Y)) >> 12` 的低 16-bit，
不是由宿主计算后注入。邻近代码有尺寸/块处理特征，可作为图像处理候选；
目前没有整幅图像解码或该函数属于当前 NPE 音频调用链的验证，不能叫作 codec 恢复。

修复前 `tmp/np560-memory-mac-before-v1/` 使用上一 X0 核心 `4e878c38...`，
原厂代码停在 `0C:71A0 / BE0C`，R10=`2800`、R14=`85D2`，REPB 剩余 64 次。
这是有效指令未实现，不是返回地址损坏跑进数据。
原 PRG 按对齐编码筛出的其它四处 `BEC5 0000` 候选位于数据形态区域，
不据短 opcode 匹配将它们作为原厂代码证据。

## 架构依据、实现与未知范围

已按 PDF 技能目视核对 [CN1916884A 扫描件](../tmp/cnpatent/CN1916884A.pdf)
第 36–39 页内存 MAC 操作/编码、第 128/129 页内存图及 DS 地址、
第 130 页 R8/R10/R14 对应 X0/X2/Y2、第 134 页 AGU 图 9/10。
[公开原文入口](https://patents.google.com/patent/CN1916884A/zh) 是同一资料，不是另一份独立硬件验证。

实现位于 `qemu-dmcu/target/dmcu/helper.c::exec_mac`，与寄存器 MAC/MULS/RNDST
共享乘法、40-bit 累加、舍入、饱和和标志更新，不复制另一套近似运算。

- BE 配置 bits 5:4=00 为内存 MAC；两个操作数字段各自指定 X/Y 索引和更新模式。
- 支持当前映射证据范围内的 **X0 或 X2 + Y2**，不更新、后增 2、后减 2。
  支持 ss/su/us/uu、加减、`.r`、`.s`、SOCR.FR/MAS 与 `.m`。
- X 走 DS 选择的数据总线；MAC 的 Y 从内部 `8000..BFFF` Y-RAM 取值，
  不受 DS1 改成外部银行影响。此项没有顺便改写所有普通 MOV 的 Y 指针通路。
- 两操作数先读完，再做 `.m`。`.m` 将原 X word 写往反方向一个步长处；
  X 不更新的形式不搬移。循环前进/后退共用 `pointer_postincrement`，处理负余数。
- 地址及后增量结果在数据总线副作用前计算，避免 `.m` 写到 modifier 自身时
  用刚写入的配置重新计算本条指令的指针；这种寄存器别名时序仍需真机核对。

XM0=`REG[13]` 有原厂环形缓冲证据。本轮将 `REG[17]/REG[1D]` 分别对应 XM2/YM2，
依据是原厂 X2/Y2 循环前的成对清零与现有 XM0 布局交叉推导，**不是拿到了完整原厂 SFR 表**。
原厂零 modifier 分支已实际执行；非零循环模式由架构定义的定向用例核对，未与真机比较。
X0/X2/Y2 的已知 modifier 也进入普通后增量的共享检查，未确认的其它寄存器保留旧行为。

仍缺：X1/Y0/Y1 modifier、XC/YC 映射及加可变步长、位反转、完整 Y 指针内存视图、
EXR 异常投递、精确周期/竞争、DSP 标志歧义和全部复合边界。
MAC 的未确认索引/模式、非对齐 word 或 Y 区外访问会在操作数/搬移副作用前显式停机，
不静默换成寄存器 MAC、线性访问或成功返回。显式停机不等于原厂异常机制已实现。

### 后续复核：不能把寻址图当作完整 SFR 地址表

2026-09-06 再次目视核对同一原始扫描件的完整相关页：

- 第 129 页图 3/4 是 CS:PC 与 DS0/DS1 地址组合，不是 SFR 表。
- 第 130 页图 5 列出 X0/X1/X2、Y0/Y1/Y2 的 GPR 编号和直接访问地址。
  它没有列出 XM/XC/YM/YC 的 SFR 编号。
- 第 134 页图 9 定义哪些间接寻址启用 AGU；图 10 定义 modifier 为零、
  环形长度和 FFFF 时的模式，以及 XC/YC 的步长/位反转参数作用。
  这些图同样没有给出 XM1、YM0、YM1 或 XC/YC 的 SFR 地址。

因此，不能把未确认的 XM1/YM0/YM1 按相邻已知地址插值，或把 XC/YC
安排在各 XM/YM 的前一槽，再称为原厂寄存器表支持。本轮没有据此修改 CPU，
也没有新增 ROM 字节。现有原厂 0C:7142 仅能支撑其实际使用的 X2/Y2 零 modifier
路径，不能重复运行它来验证未使用的其它寄存器。

继续实现缺失模式需要能区分地址假设的原厂初始化/保存恢复与使用代码，
或明确的芯片 SFR 表；位反转还需核对其有效地址及指针更新规则。
普通间接访问对未确认 modifier 仍保留线性旧行为，是尚未完成的忠实度缺口，
不能因为内存 MAC 会显式停机就声称普通访问也已完整覆盖。

## 新指令的 TCG I/O 边界修正

本轮中间核心 `6a5d064b...` 已通过原厂 RAM 函数，但 MAC 未进入
`translate.c::dmcu_may_do_io`。当 X 指向 `F128`、`.m` 写 `F126` 时，
真实 MMIO 访问发生在不允许 I/O 的翻译块中，触发：

```text
qemu: fatal: cpu_io_recompile: could not find TB for pc=(nil)
PC=20:0068 ... R8=f128 R14=8504
```

隔离 QEMU PID 40559 exit -6。现场及原始错误日志在
`tmp/np560-memory-mac-agu-write-before-v1/`。
这是新增内存 MAC 实现的中间缺陷，不是已经解释了历史用户菜单崩坏。

已将内存形式标记为可能 I/O，调用现有 `translator_io_start` 使其位于块末并正确计时；
不对全部指令关闭优化，也不绕开正常总线读写。最终普通及 icount 的同一反例通过：
AR=`12`、XM0 变为 `1`、本条 X0 后增量为旧模式生成的 `F12A`。
寄存器形式维持原有翻译块行为。

## 验证与中间夹具错误

[内存 MAC 脚本](../scripts/test_np560_memory_mac.py) 复用现有运行器。
112-byte 原函数完整复制到隔离 ROM 的链接地址，caller 以同段 near-call trampoline
适配 near RET；没有改函数内容或生产 ROM。描述符、64 项数据及系数由 guest 指令准备，
宿主只读观察结果；无 NAND、HLE 或运行时 guest RAM 写入。

原厂三个场景：DS1=1、DS1=A0、DS1=A0 + icount=5。外部银行场景在同一逻辑系数地址
放入 `7777`，内部仍为原夹具系数；同时读回两者确认不同，64 项输出仍全部正确，
并检查输出前后哨兵、X2/Y2 终值和栈恢复。

首轮 `np560-memory-mac-v1` 的 DS1=A0 夹具误用了默认带 IGNDS 的写入 helper，
实际覆写了内部系数，因此失败。修正为 `banked=True` 并增加内/外系数独立读回断言；
没有改期望乘积或 CPU Y-RAM 读取以制造通过。`v2/v3` 为中间核心验证，保留记录。

最终 `tmp/np560-memory-mac-v4/report.json` 的 24 项全部通过且隔离进程均 exit 0：
上述三个原厂场景，以及混合符号、分数乘法、前后向/循环寻址、X0 共用规则、
`.m` 覆盖 Y 前先读、MMIO、零更新不搬移和未实现形式无副作用停机。
这些是当前实现及证据边界，不以数量换算整机进度。

运行器现在把 QEMU 日志与结果一起保存；发生 native abort/QMP 断连时仍能保留原因，
不需要补庞大跟踪框架或反复猜测断连来源。

## 最终同核心结果

QEMU `E:/qemu-dmcu-build/qemu-system-dmcu`，46,596,840 bytes，SHA-256：
`ac5f17b033e681095b18f05143b765e808116d90aecc74b708be63c0f0c57281`。
修改前核心保留在 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-memory-mac-20260906`，
SHA-256 `4e878c3814583ccd4f9f1e3d05839113f9a458bdf50ec728cbd14a553167a540`。

生产 PRG/ROM/NAND 未修改；完整指纹在同核心冷启动报告：
`tmp/np560-memory-mac-cold-boot-v2/report.json`。

- 零按键、严格缺口 ROM、HLE off 冷启动 102.81 秒通过；最后三次顶栏 0/5280 差异，
  无 ROM_MISSING/UNSUPPORTED/INVALID_CONTROL，NAND ERROR=0；已目视 final.png 为清晰学习桌面。
- `tmp/np560-memory-mac-x0-v2/report.json`：原厂音频环形缓冲及其指针边界全部通过。
- `tmp/np560-memory-mac-register-v2/report.json`：完整原厂样本增益/寄存器 DSP 套件通过。
- `tmp/np560-memory-mac-audio-v1/`：原厂 `08:33FA` 普通/icount 数字输出、静音、暂停、
  活动采样与 Timer2 复位通过；两路各写 7 次，(3,-3) 分别收到 965/960 帧。
  这不是音乐播放器或游戏的实际解码音频。

没有重跑同一已知 ROM 缺口的游戏导航。最近 NPE 选择现场仍见
[流后端](np560_resident_stream_backend.md)：`25:DFBA → 02:ACD8`；
ACD8/AD92、B6DE/B7AA/B816/B84E 没有因此恢复，NPE 完整玩法/声音/原生保存仍未完成。
菜单花屏也没有足够证据关闭。

本轮隔离实例全部退出，未保存 NAND 或替换用户 8807/8808/8809。
仅清理本轮 PID 40559 产生的 3,395,379,200-byte 临时 crash dump，未进回收站；
原始错误日志与反例记录保留，旧转储未动。下一步仍按 [整机计划](plan.md) 推进真实能力。
