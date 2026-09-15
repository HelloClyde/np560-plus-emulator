# ICR 请求与原厂 RAM 中断向量

日期：2026-09-05。本页记录基础 ICR 派发这一历史步骤。
后续 [ICR 嵌套与返回现场](np560_interrupt_nesting.md) 已解除硬件 ISR 的整体嵌套禁令，
并验证真实定时器抢占；本页“禁止嵌套”属于历史阶段，旧 tick 隔离等边界仍保留。
后续 [Timer2 周期设备](np560_timer2_device.md) 已产生硬件请求并使原厂等待结束；
完整 Timer 模式、中断嵌套和 DTU 仍未完成。下文的软件 RQ 测试不冒充后续设备验证。

后续 [DTU 传输](np560_dtu.md) 已实现逐请求搬运及 COUNT=0 的最高优先级续填/完成
中断；下文“ED 保留给未实现设备”是本历史阶段的行为，不是当前 COUNT=0 的派发规则。

## 依据及向量基址

本地 `tmp/cnpatent/CN1916884A.pdf` 第 8/9 页说明内部 X RAM 可执行代码，且
SOCR.RAM 令中断/陷阱向量从 0000 开始；图 7A 给出 RAM=bit 1、NSEG=bit 5、IE=bit 15。
图 7B、12、13 给出 PSR 和 ICR 字段，以及 32 个来源的向量位置。已查看这些完整 PDF 页。

原厂 Timer2 waiter 向 data `00:0058` 安装 `AD08 481A`，即跳到 `08:481A` 的指令。
它与 SOCR.RAM 的含义一致：这是可执行的 RAM 向量，不是需要宿主解释的函数指针，
也不需要猜测一个 `01:0058 → 00:0058` 的 mask-ROM 跳板。

分段模式下 RAM=1 使用 CS=0，RAM=0 使用 CS=1；向量偏移取图 13：
来源 0..15 为 `0040 + source*8`，16..31 为 `00C0 + (source-16)*4`。
NSEG 的帧及 RETI 按文档条件省略 CS，同段测试通过；Romless 等其它配置尚未闭合。

## 本轮实现

- `REG[50..6F]` 的 EN/RQ/PRI 参与 CPU 选择；软件写 RQ、EN、SOCR 或 PSR 后，
  在完成当前指令的边界重新判断。低优先级请求保留，接受时只清所选来源的 RQ。
- ICR 派发更新 live PSR 的 CIRQ/CPRI，栈保存原厂 PSR；RETI 恢复 PSR 和 PC，
  按 NSEG 使用四/六字节帧。ICR 路径用实际硬件帧位置区分 synthetic RETI，不按 ISR 地址特判。
- ED=1 的请求不被误当作普通 CPU 中断，仍保留给尚未实现的 DTU。
- 设备入口 `dmcu_irq_raise` 可置来源 RQ 并唤醒 CPU；本轮验证主要使用架构允许的软件 RQ，
  不是已经让 Timer2 的虚拟时钟产生事件。
- 旧 64 Hz tick 独立记为 legacy pending，不冒充已确认的 TBICR 来源；目前仍跳旧固定入口。

一次开发构建增加独立向量映射后，启动触发 `phys_section_add` 的 2048 项上限，
不是 guest 中断死锁。现已把向量并入原有 X RAM 可执行窗口，范围由 `1002..102D`
扩成 `0000..102D`，共享同一 RAMBlock；没有提高上限或添加逐向量小别名。
102E 以上仍有历史重建代码映射，需要后续审计，不能称整个 X RAM 硬件映射已完成。

## 验证与适用范围

`scripts/test_np560_icr_vectors.py`：

- RAM 来源 0/3/15/16/31，覆盖图 13 两段步长及边界；ROM 向量选择。
- 原厂 PSR 栈格式、四/六字节帧、返回 SP 和 CIRQ/CPRI 字段。
- 全局 IE 和来源 EN 屏蔽时请求保留；ED 不派到 CPU；优先级阈值及 CIRQ 同级屏蔽。
- `-icount shift=5` 下软件请求在指令完成后接受，没有异步 I/O 断言。
- 额外从原始 PRG 复制完全未修改的 `08:481A..483E`。由 guest 软件置 T2 的 RQ，
  该原厂 ISR 自己将 near `4BB8` 从 1 减为 0，清 `REG[2D]/REG[53]`，正确 RETI。
  倒计时归零的这个检查证明派发和 ISR 执行，不证明 Timer2 计数、频率或原厂 waiter 已返回。

旧 `0ed14f8a...` 对同一 RAM 向量检查失败：前台已到结束位置，但 R4=0、无 ISR 执行。
本轮新检查通过，原有完整 PSR 帧、SOCR、位寻址和原厂 32 KiB 搬运进位检查也通过。
原厂 waiter 仍停于 `08:47FA / countdown=3`，这是明确未实现的 Timer2 边界。

原厂零按键冷启动：`tmp/np560-icr-ram-vectors-cold-boot-v1/report.json`，
`passed=true`，78.06 秒，末帧顶栏 0/5,280 差异，已有 CPU/NAND 故障项均为零。
已目视检查 `final.png`，学习桌面文字、开始菜单和时钟正常。
这不证明正常多次导航、间歇性资源覆盖或 NPE 完整游玩已解决。

QEMU `E:/qemu-dmcu-build/qemu-system-dmcu`：46,171,040 bytes，SHA-256
`6017fd9332a4d8b88911a20fbf34fd3de4f0858e4d07d1e7ed0dfb395b3e798d`。
前一构建保留为 `qemu-system-dmcu-pre-icr-vectors-20260905`，SHA `0ed14f8a...`。
原始固件、resident ROM、导入 NAND 未修改；没有保存新 NAND 或操作用户 8807/8808/8809 实例。

## 仍然不能宣称完成的部分

1. CPU 仍禁止硬件 ISR 嵌套，repeat/context 仍是单层影子；更高优先级不能据此宣称可抢占。
2. 文档 CIRQ 的两条文字都写为 1，存在矛盾。目前按 CIRQ=0 可同级、CIRQ=1 必须更高解释，
   必须保留这个推断边界；同优先级多源暂取低向量，现有资料没有证明真机的平局规则。
3. Timer2 时钟/预分频、控制位、计数/重载和硬件 RQ 尚未接入；下一步优先实现这一依赖。
4. DTU、真实异常/TRAP、Romless、完整 X RAM 映射和旧 tick/回调特判清退仍待实现。
5. 历史 SP/FP 中断延后保护仍保留，不把它当已证实的硬件栈保护语义。

下一步沿原厂 waiter 的配置实现定时事件，经本轮 ICR 路径调用原厂 ISR，要求等待函数
自然完成并恢复配置。不能改 countdown、提前返回或用宿主 sleep 代替。
