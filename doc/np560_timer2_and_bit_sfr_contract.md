# 声音启停的 Timer2 依赖与位寻址修正

日期：2026-09-05。source 地址仍按 PRG 历史基址 `20:0000`；运行地址减 `1D:0000`。

## 最新进展：Timer2 硬件请求已使原厂等待正常结束

已接入虚拟时钟周期计数/重载和 T2ICR 请求，PLL 直接/内存视图共用状态。
原厂完整 waiter 经真实 IRQ 归零、恢复并返回；同构建正常矩阵导航选择《英雄传奇》，
已越过该等待，停在仍未还原的 `02:ACD8`，尚不能游玩或输出声音。
实现、推断边界、新旧对照及实际系统记录见 [Timer2 周期设备](np560_timer2_device.md)。

下文为历史分步记录，其“Timer2 计时未实现”等表述只适用于各自旧构建。

## 前一步：基础 ICR 与 RAM 向量已接入

SOCR.RAM 的原文与固件安装 `00:0058` 跳转指令对上，已实现 EN/RQ/PRI 选择、
RAM/ROM 向量、PSR 入口更新及 NSEG 条件返回帧。未修改的原厂 Timer2 ISR 经软件
请求已能倒计时归零并返回；78.06 秒原厂冷启动通过。完整证据、构建身份和推断边界见
[ICR 向量派发](np560_icr_vector_dispatch.md)。

Timer2 的计数/时钟还未产生硬件请求，嵌套/DTU/旧 tick 清退仍缺；下面各节保留为
此前分步修正记录，不能把历史“通用向量未实现”当本轮现状，也不能把本轮当 IRQ 全部完成。

## 前一步修正：SOCR 共享视图与全局中断屏蔽

专利图 7A 的 SOCR.IE 位与原厂 `BCLR/BSET BIT[00].15` 对应。此前 F100 的专用设备
另存 `keyboard.system_control`，直接 `REG[00]` 写入不能改变它；板级 tick 只看这个
旧副本，CPU 接受中断时也没有检查直接 SOCR.IE。因此原厂禁止中断的临界区仍会被打断。

现在删除独立 SOCR/enable 副本，F100/F101 的字节/字读写、直接寄存器和位操作共用
`REG[00]`。board tick 和 CPU 接受中断均检查该 IE 位；已经挂起但被屏蔽的请求不会被
CPU 提前消费。普通字节写保留另一半字节，并遵循原有 DMCU lane 规则。

- 旧 `c9fcb368...` 构建在 F100 启用后执行 `BCLR BIT[00].15`，仍有 5 次 tick/5 次中断，
  测试 ISR 的 R5 从 0 变成 5；负向对照实际失败。
- 新构建在多个真实 tick 周期后中断入口仍为 0；直接 SOCR 启用可以启动原有 tick 路径，
  不再必须先通过 F100 写入。完整 PSR 帧、低 SFR、SOCR 双向视图及字节 lane 检查通过。
- 原厂 `08:47A4` 的针对性 fixture 增加一个仅 RETI 的旧 board-tick handler；没有改变
  原厂 Timer2 代码、0058 向量、ISR 或 countdown。实际 waiter 仍停在 `08:47FA`，countdown=3。
  该 fixture 明确兼容尚未清退的固定 tick，不能用来证明 Timer2 已正确计时。
- 最新 QEMU：46,161,792 bytes，SHA-256
  `0ed14f8a5c27ed32828e8050e9eeaa5563565fe1523f5ecd3ffd6289ac42ae38`。
  上一步保存在 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-socr-ie-20260905`。
- `tmp/np560-socr-ie-cold-boot-v1/report.json`：71.89 秒零按键冷启动通过，末帧顶栏
  0/5,280 差异，无已有 CPU/NAND 故障。尚未将此结果外推为正常导航、NPE 或资源覆盖问题已修。

剩余边界：64 Hz source 仍直接走旧固定入口，不是完整 ICR；Timer2 计数/重载、时钟、
通用向量及 CIRQ/CPRI 仲裁仍须实现。键盘等其它专用 SFR 视图也不能算随 SOCR 一并完成。

## 上一步修正：中断帧使用完整原厂 PSR

低 SFR/PSR 地址修正后继续发现，CPU 的硬件中断压栈仍使用内部 `env->psw & 15`，
RETI 也把弹出的字直接赋给该内部字段。这不是原厂 PSR 的格式：内部为 Z/C/N/V，
原厂为 Z/V/C/N，且原厂帧需要保留高位。只让这两个错误互相抵消，不能正确处理 guest
读取、修改或合成的中断帧，也会丢失 PSR 高位。

现在硬件入口通过与 `REG[01]/F102` 相同的接口编码完整 PSR，RETI 通过同一接口恢复。
这不改变原厂指令，不按调用地址选择格式。通用 IRQ 的选择、CIRQ/CPRI 的入口更新、
嵌套及 Timer2 计时仍未实现，现有固定 tick 入口和 callback 特判尚未清退。

依据是专利图 7B 的 PSR 字段，以及原厂 `08:41C4..41E2` 构造 PSR/CS/PC 帧、RETI
进入 callback 后恢复 `REG[01]` 的实际代码。已查看原 PDF 图 7B、12、13、23；没有从
图 23 猜出其未给出的全部 TxC 控制位。

验证与身份：

- `scripts/tests/test_np560_interrupt_psr.py` 覆盖 guest 合成帧的全部低标志组合与 MX/MS/MV
  高位；另由已有板级 tick 实际压栈，ISR 读取该帧并清零 live PSR，要求 RETI 真正恢复。
- 旧构建对合成 PSR `01C0` 读回 `0000`；实际硬件帧应为 `01C4`，却压入 `0002`。
  两项负向对照均实际失败。新版通过合成帧和实际入口/返回检查。
- 原有低 SFR、PSR、原厂跨 32 KiB 进位及原厂 waiter 检查仍通过；waiter 仍等待 Timer2，
  不是声音启停已完成。
- QEMU：46,161,912 bytes，SHA-256
  `c9fcb368d33e67014500ccebc6fa17be239fae203cfbcdde5dffa8525213c89d`。
  前一构建保存在 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-irq-psr-frame-20260905`。
- `tmp/np560-irq-psr-frame-cold-boot-v1/report.json`：零按键冷启动通过，约 97.88 秒，
  最后三帧顶栏零差异，无已监控 CPU/NAND 故障。中途“每日一句”正常显示后才进入桌面，
  不能将中途与主菜单不同的截图当作花屏。
- 本项不证明此前 `22:1840` 代码被改写的问题已修复；独立证据与复现边界见
  [游戏世界入口与代码写入](np560_game_world_code_write.md)。

## 位寻址修正

后续已确认高位 `BIT[80..FF]` 应访问 F000..F0FF DPRAM，而非直接高 SFR；
原厂 F01C/BIT8E 路由的动态反例及修复见 [三路 Timer 与 DPRAM](np560_periodic_timers_and_dpram.md)。
下文仅描述当时对低位地址的修正，不代表高位映射在该版本已经正确。

修正 CPU 位指令把所有低地址强制 `| 80` 的错误。原厂 `MOV REG[53],0031` 随后的
`JB BIT[53].0` 现在读取同一个寄存器，不再读取未写入的 `D3` 并提前结束等待。
这不是声音输出或 Timer2 已完成，也没有将任何缺失 ROM 入口改为成功返回。

低外设位地址 `00..6F` 使用对应直接 SFR；保留原厂 PLL 函数证明需要的 `70..7F → F0..FF`
通用寄存器位别名。高软件位字没有与低外设合并。这是本轮已闭合的地址类别，不宣称
所有 SFR、内存映射、PSR 和位 RAM 的硬件一致性均已验证。

## 后续实现：寄存器内存窗口与 PSR 地址

同日继续实现了 `F100..F1FF` 的低 SFR 共享窗口，替换原本独立的普通 RAM 视图。
窗口以低于专用设备的优先级安装，同时提供 banked 与 IGNDS 别名；Timer2、ICR、DS、
移位缓冲等通过 CPU 的同一套读写语义访问。字节访问保留 guest 的高字节在前顺序，
DS 写入仍使 TLB 失效。内存写入不重复计入直接指令的 `DIRECT_SFR_WRITE` 观察器。

此外，PSR 的直接地址由错误的 `81` 修正为 `01`，对应内存 `F102`：

- 原厂 `08:41E2` 使用 `OR REG[01],7000` 恢复 CIRQ/CPRI 状态；
- 原厂 burner `51:D73E` 使用 `BMOV BIT[01].2,BIT[71].15`，随后
  `ADDC REG[10],0` 将进位传给 DS0，处理 32 KiB 地址边界。

上一轮只修低位地址、尚未配套修正 PSR 位置，因此上述进位链仍会丢失。现在这两部分
一致：边界 `R1=7FFF` 正确变为 `R1=0000 / DS0=0101`，不跨界时 DS0 保持 `0100`。
高软件寄存器 `81` 不再意外修改 CPU 条件码；Z/V/C/N 的寄存器位序转换沿用原有实现。

边界没有隐藏：高优先级的 F100 系统控制、F160/F164 键盘设备仍保留其已有模型，
其直接 SFR 视图尚待集成；F200 以上的 SFR/位 RAM 也没有整体收敛。共享一个寄存器值
不等于实现该外设的计数、传输或中断副作用。通用 IRQ、完整 PSR 保存/恢复、嵌套与向量
派发仍未完成，不能把本次改动称为整个中断系统已实现。

## 原厂等待程序证明旧行为错误

`08:4702` 在声音启动控制中调用 near `08:47A4`，参数有 1,000 和 200；停止路径
`08:475E` 使用参数 50。`08:47A4..483E` 的完整原厂代码具有以下行为：

1. 保存 SOCR、`REG[53]`、`REG[2D/2C]`、`00:0058` 的原向量，以及工作寄存器。
2. 把参数写入 near data `00:4BB8`，向 `00:0058` 安装 `AD08 481A` 跳转指令。
3. 调用 `08:3930` 计算计数配置，结果通过 `F2E0` 的 R0 数据别名写入 `REG[2C]`；
   `F2E0` 不是独立的定时器结果设备。
4. 写 `REG[2D]=8080`、`REG[53]=0031`，设置 SOCR 的 IE 位，循环等待 `BIT[53].0` 清零。
5. ISR `08:481A` 每次将 `4BB8` 减一；到零后写 `REG[2D]=0`、`REG[53]=0`，最后 RETI。
6. 主程序恢复原向量、定时器/中断配置和保存现场后返回。

旧 CPU 把第 4 步的位读转为 `REG[D3]`。因此即便从未发生 Timer2 中断，也能直接进入
恢复/返回路径。这种“没有卡住”是提前放行，不是硬件实现成功。

## 资料与原厂代码的交叉依据

处理器专利 [CN1916884A](https://patents.google.com/patent/CN1916884A/zh) 的图 12/13
给出 ICR 的 EN/RQ/PRI/ED 字段，以及 `REG[53] / F1A6 / T2ICR / vector 0058` 对应关系。
图 5 给出 R0 的直接地址 F0、内存地址 F2E0，和上述原厂等待代码相符。
图 23 给出定时器、时钟选择与比较/重载结构，但不足以单独确定 NP560 的所有 TxC 位。
已逐页查看本地原 PDF 的 130、132、134、136、137、140、141 页，而非只相信 OCR 文本。

`08:4470..44F0`（source `25:4470`）对 R0 用 `BIT[70]` 设置 bit 15、清除 bit 14，
随后把它与 F2D2 比较并写入 `REG[E9]`。因此不能把 70 简单改成直接外设 REG[70]；
后者在声音样本输出路径另有用途。

## 与 02:ACD8 的边界

不能因为 `02:ACD8` 同样接收 20/50，就称它为延时。原厂明确的定时等待是上面的
`08:47A4`；音量渐变也有 `08:3536` 和 `08:33FA/3462` 的原厂实现。
缺失的 `02:AD92` 接收经 `08:372A` 重复样本处理后的缓冲，紧邻 ACD8 只构成研究线索，
不能据此宣布 ACD8 是滤波初始化、AD92 是 memcpy 或某个已知 codec。
ACD8 与 `01:B6DE/B7AA/B816/B84E` 的缺口仍然存在。

## 验证与剩余工作

### 前一共享窗口 / PSR 地址构建

- QEMU：`E:/qemu-dmcu-build/qemu-system-dmcu`，46,161,856 bytes，SHA-256
  `503cc5ac63ecbd7bd9b4f8dccf45c11967272a1498f7ba8e4383769c4b00f0e0`。
- 旧版负向对照：写 REG[53]=0031 后，IGNDS、banked 和普通指针读均为 0000；
  位操作修改直接值后，内存仍保留另一值 0033。新版本四种访问共享 0031。
  旧 PSR 位置还导致 `CMP R0,0; PUSH REG[01]` 读回 0000 而非 Z=1；新版为 0001。
- `test_np560_bit_sfr_addressing.py` 新增共享窗口、字节 lane、memory-mapped DS0、
  PSR 视图与软件字分离、原厂 burner 跨界/非跨界进位的针对性检查，全部通过。
  原厂 Timer2 waiter 仍正确等待真实中断，不提前成功返回。
- `tmp/np560-sfr-psr-cold-boot-v1/report.json`：当前 ROM 与原厂导入 NAND 的
  零按键冷启动通过，最后三次学习顶栏零差异，无 CPU/NAND 故障。
- `tmp/np560-sfr-psr-vendor-cold-read-v1/report.json`：在另一个全新实例中，通过
  原厂 command 1/5/7/10 挂载、打开、读完并关闭《英雄传奇》，2,053,994 bytes 全部一致，
  SHA-256 `adea7c7442cefaea1c21ab7442cdd10d7796e7fc1dd3a5b98fd3c1c61dfa8c19`。
  `verify_only=true`，没有创建文件/目录、输出 NAND 或再次烧录；RAM 传输不代表 USB 硬件完成。
- 中间共享窗口版本的冷启动记录为 `tmp/np560-sfr-window-cold-boot-v1/`，不能冒作
  最终 PSR 构建的身份；修正前二进制分别保留为 `qemu-system-dmcu-pre-sfr-window-20260905`
  和 `qemu-system-dmcu-pre-psr-address-20260905`，位于同一个 E 盘构建目录。

### 前一版位寻址构建（历史）

- `scripts/tests/test_np560_bit_sfr_addressing.py`：旧二进制实际错误进入 BAD0 分支；新二进制
  通过 Timer2 直接/位读写、SOCR/GPIO、R0 位别名及高软件位字分离检查。
- 可选 `--original-prg` 从原 PRG 取出 `08:3930` 与 `08:47A4..483E` 的精确代码，
  只增加测试 caller。新 CPU 停在原厂 `08:47FA` 等待，`4BB8=3`，未进入 caller 的
  “提前返回”标记。这里明确验证的是缺失硬件边界，不是期望模拟器永远等待。
  对同一原厂代码再次运行旧二进制，实际到达 `20:000C / R4=BAD0`，没有执行 Timer2 ISR；
  因而不是只用合成分支推测原厂路径受影响。
- `tmp/np560-bit-sfr-cold-boot-v1/report.json`：同一原厂导入 NAND、新 ROM，零输入
  冷启动 66.83 秒到完整桌面，最后三次顶栏无差异，无 CPU/NAND 故障。仅证明这条启动路径。
- QEMU：`E:/qemu-dmcu-build/qemu-system-dmcu`，46,200,464 bytes，SHA-256
  `fc506186f92cee139cfb61129e030ac743e6da53fccdb6a6e8d7f2d54bd71eb0`。
  上一版本保存在 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-bit-sfr-20260905`。
- 使用的 ROM、NAND 没有改写，所有隔离测试实例均已关闭；用户 8807/8808/8809 未重启。

接下来需要统一低外设直接/位/内存视图，恢复 Timer2 的实际时钟、计数及 ICR 请求，
由 guest 安装的向量派发并正确 RETI。当前 CPU 仍把系统 tick 直接派发到 `08:40D0`，
不等于实现了通用中断控制器。完成硬件后，上述原厂等待测试应改为要求实际中断、
计数归零及正确恢复返回，不能保留“跳过等待”或用宿主 sleep 代替。
