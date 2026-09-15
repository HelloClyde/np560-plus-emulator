# DMCU TRAP 软件向量：架构实现与 ROM 空洞区分

日期：2026-09-05。实现有效 `0Fxx` 指令，不再将其全部作为 unsupported；
显式重建 ROM 的缺口仍停机。没有补写未知 ROM 算法，也没有修改 PRG、ROM 或 NAND。

## 原始依据与歧义

来源是本地原始专利扫描件 `tmp/cnpatent/CN1916884A.pdf`，已目视原页，未只依赖 OCR：

- PDF 第 124 页（说明书 121/123），TRAP 操作表：先压 PC；若 SOCR.NSEG=0，
  再压 CS 并令 CS=1；然后压 PSR，PC=`zero_extend(imm8 * 4)`。
- PDF 第 125 页（说明书 122/123）：编码 `0F##`，指令长度 2 bytes。
- TRAP 文字说明保留优先级结构，使用 RETI 返回；Z/C/N/V 不变。

文字段落关于 NSEG 的表述与操作表不一致。本实现明确采用操作表：NSEG=0 保存 CS，
NSEG=1 保持当前 CS；不更改 NSEG。不能称该歧义已由真机测量解决。
操作表没有规定 TRAP 使用 SOCR.RAM 选择向量段，也没有 ICR 请求确认或优先级改写。
因此不能直接套用硬件 ICR 的所有仲裁/入口动作。

## 实现边界

- `target/dmcu/helper.c` 解码 `0Fxx`，将指令后的返回地址传入 CPU。
  16-bit PC 在段内回绕；`20:FFFE` 的返回地址是 `20:0000`，不是 `21:0000`。
- `target/dmcu/cpu.c` 共用硬件中断已有的真实 SRAM 压栈、重复状态挂起和嵌套上下文。
  TRAP 不受 IE/ICR.EN/硬件临界区屏蔽，也不应用历史 SP/FP 异步中断延后保护。
- segmented 栈为 6 bytes，从新 SP 起依次 PSR、CS、PC；NSEG 栈为 4 bytes，PSR、PC。
  栈不被普通数据段 DS0/DS1 重定向。
- 硬件 ICR 仍确认自己的 RQ、设置 CPRI/CIRQ、选择硬件向量；TRAP 保留这些状态。
- RETI 读取 guest SRAM 帧。只读诊断可以报告返回地址不同，但不能恢复旧 PC 掩盖 guest 写入。
  测试中的 guest 主动修改返回 PC 后，实际执行新地址，诊断 BAD=1，未做宿主修复。
- `IRQ_NESTING` 增加只读 `TRAPS` 计数，复位清零。历史 `IRQ64.ENTRIES/RETURNS`
  统计所有此类 CPU 入口/返回，包括软件 TRAP，不表示全是 64 Hz 硬件中断。

完整 EXR 异常、IREP、精确周期/流水线以及硬件同级仲裁仍未完成。
本次验证 TRAP 位于多指令 REPB 块内的挂起/恢复，不宣称非法 REP 组合或 ISR 中 REP 已受支持。
保留的 SP/FP 硬件中断延后逻辑仍缺明确硬件依据，不能冒充 STOVUN 栈异常实现。

## 重建 ROM 空洞仍严格停机

`soc-rom-skeleton=on` 是重建镜像的显式调试契约：指定 resident 范围中的 `0F00`
填充值先报告 ROM_MISSING，不执行 TRAP。它不是芯片对所有 `0F00` 的硬件规则。
普通 PRG 中有效的 TRAP #0 与 #37/#255 一样执行软件向量；没有把所有 TRAP #0 判成缺口。
若将真正的原厂 ROM 标成 skeleton，其中真实的 TRAP #0 也会被该旧填充标记约定误判，
因此只能对来源明确的重建镜像显式开启，不能按文件名猜测或自动作用于所有 ROM。

冷启动脚本 `probe_np560_checkpoint_boot.py` 增加同名开关并记录配置。
此次对现有 `resident-codec-holes-v1.bin` 开启；默认值不变，既有用户实例不被重启。
后续可以用精确空洞区间清单替代填充值约定，但本次没有伪称该机制已实现。

## 定向验证及实际固件

`scripts/tests/test_np560_software_trap.py` 使用明确诊断 guest，无 NAND；所有寄存器和 RAM 写入
来自 guest 指令，宿主只读取及控制运行/暂停/复位。最终同版记录是
`tmp/np560-software-trap-v5/report.json`，14 个定向场景全部通过：

| 场景 | 核对内容 |
| --- | --- |
| IE 关闭，TRAP #0/#37/#255 | 仍进入正确软件向量，PSR/待处理且禁用的 TBICR 保持不变 |
| resident ROM 内有效 TRAP | 非零 TRAP 不误判空洞；未标记 skeleton 的 ROM 中 TRAP #0 正常执行并返回原 CS |
| SOCR.RAM 与 NSEG | 软件向量不误用硬件 RAM 选择；短栈/段保持及 RETI 正确 |
| icount | 同样返回到指令后，未跳过或重复后续指令 |
| TRAP 内 TRAP、TRAP 内 IRQ、IRQ 内 TRAP | 分层帧、各层 PSR/ICR 行为、SP 和返回顺序正确 |
| 前台 REPB | 挂起/恢复后完成三轮；不让重复状态作用于向量代码 |
| guest 修改返回 PC | 跟随真实 SRAM 返回，不使用诊断期望值修复 |
| 段末 PC 回绕 | 返回原代码段的 0000 |
| 活动 TRAP 中复位 | 嵌套层和 TRAPS 计数清零 |

`test_np560_trap_strict.py` 另验证显式 ROM 空洞停在 `01:0004`，R0 哨兵未变、TRAPS=0。
硬件回归：ICR 嵌套的 12 个场景（含真实定时抢占/DTU/复位）通过，记录
`tmp/np560-trap-nesting-v1/report.json`；TBC/TBICR 的 9 个场景通过，含原厂初始化、
原厂 ISR 和 icount，记录 `tmp/np560-trap-timebase-v1/report.json`。
ICR 向量、屏蔽、NSEG、空 ED 通道及原厂 Timer2 ISR 检查也通过。
完整 PSR 标志组合、硬件及 synthetic RETI、直接 IE 位读写回归通过。

严格 ROM、原始 PRG、既有原厂文件 API 导入 NAND 的零输入冷启动通过：
`tmp/np560-trap-cold-boot-v1/report.json`，约 70.7 秒；最后三个顶栏样本均 0/5280 差异，
CPU/ROM/控制流及 NAND 现有故障检查通过。已目视 `final.png`：学习桌面和 08:00 时钟正确。
这是一次冷启动检查，不验证完整菜单切换、跨应用稳定性或完整 NPE。
该轮没有再次操作游戏入口；上一构建实际选择《英雄传奇》仍停 `02:ACD8`，
见 [时基记录](np560_timebase.md)。此次未修改该缺失服务，不能宣称游戏已推进到新阶段。

开发中失败结果保留，不合并成通过报告：

- `np560-software-trap-before-v1`：旧二进制停在 unsupported，未执行后续哨兵。
- `np560-software-trap-v1`：实际 TRAP/RETI 已工作，测试帧读取忘加 IGNDS，误读 DS0=A2；
  修测试的 guest 读取方式，没有据此改变 CPU 栈实现。
- `np560-software-trap-v2`：与第二次链接重叠，启动新进程报 Text file busy，整轮无通过结论。
- `np560-software-trap-v3`：同版 12 项通过；v4 另增加 TRAPS、复位计数及运行前后构建哈希断言。
- `np560-software-trap-v5`：另覆盖 resident ROM 中的有效非零 TRAP 和未标记空洞的 TRAP #0。

## 构建及后续

QEMU `E:/qemu-dmcu-build/qemu-system-dmcu`，46,562,376 bytes，SHA-256：
`4a96b19b1dd6fc83c2a29f0c7b7475a097d4c7a6c6721dfe399c181eb5241081`。
前版保留为 `qemu-system-dmcu-pre-trap-vectors-20260905`，SHA-256：
`4e9048cc58ce6f72ec14d7681eabb15da7a25b9cc35c7af2b73262a490d131c4`。

PRG `d555609e...`、重建 ROM `a243f8ba...`、原厂导入 NAND `7783876b...` 未改；完整身份在
冷启动报告。未保存 NAND 或生成大镜像，隔离实例已关闭，用户 8807/8808/8809 未替换。

继续按 [整机计划](plan.md) 处理共同机制和真实使用链；ROM 流后端、原厂声音、NPE 完整玩法、
原生存档仍未完成。TRAP 是一项 CPU 能力，不是通过任意测试次数获得整机验收。

后续 [IGNDS 中断保护](np560_ignds_interrupt_mask.md) 修复了硬件 IRQ 过早消耗 IGNDS
导致的错银行写入，记录更新的核心身份及同版 TRAP/ICR/时基回归。本文哈希仍代表当时
TRAP 实现的历史构建，不改写为后续构建；未据此补齐同步异常在保护区内的语义。
