# REP 非法目标：消除副作用，IREP 异常派发仍待恢复

日期：2026-09-06。修改 QEMU CPU 的非法指令边界，没有修改 ROM、PRG、NPE 或 Web 绘图。
这不是实现完整 EXR/IREP 异常，也不是本轮阿诺战斗中发现的故障；
它是继续核对整机 CPU 语义时独立确认的缺口。

## 原始依据与实现边界

本地原件 `tmp/cnpatent/CN1916884A.pdf` 的相关页已整页渲染并目视核对：

- PDF 第 120 页：REP 的目标不能是分支、调用、返回、TRAP、REP/REPB、CRIT、LINK、UNLINK；
  即使操作数为 0，也执行一次重复目标，禁用表没有豁免这个情形。
- 同页：重复指令仅用于正常处理模式，服务期间保存 SRC，PSR.CIRQ 回到 0 后继续。
- 第 122 页：REPB 有独立块循环状态；不能把 REP 的单目标禁用表扩成“块内所有指令禁用”。
- 第 136 页图 15：EXR 的 IREP 位为 bit 6；图 14 仅列出 Reset、Stack Overflow、Stack Underflow。
  本次核对的资料尚不能确定 IREP 的异常向量和 EXR 的 SFR 地址。

因此只落实已经明确的禁止执行边界，不猜造寄存器地址，不借用软件 TRAP 的向量。
当前用既有显式停止机制报告 `IREP_DISPATCH=unimplemented`；
目标指令不执行，但真实 EXR 请求、异常入栈/派发、处理后恢复等仍未实现。
这是一项确定错误的消除，不可标作 IREP 架构完成。

## 修复前的确定反例

最小 guest 自行设置 SOCR、PSR、SP、FP 和寄存器，然后执行：

```text
REP #0
LINK #2
MOV R0, #BEEF
```

旧核心正常到达末尾自循环，没有触发诊断错误：

| 值 | 初始/应保留 | 旧核心实际 | 新核心实际 |
| --- | --- | --- | --- |
| R0 | 1234 | BEEF | 1234 |
| FP | 6100 | 5FFE | 6100 |
| SP | 6000 | 5FFA | 6000 |
| PC | 停在非法目标 20:0020 | 已执行到 20:0026 | 20:0020 |

旧失败不是超时或未进入程序，诊断进程正常退出 0；
记录：`tmp/np560-repeat-illegal-before-20260906-v1/link-icountNone.*`。

## 实现

- `target/dmcu/helper.c`：按原表识别 REP 的禁用目标，条件分支即使不跳转也拒绝。
  检查放在实际操作之前，避免 LINK/CALL/RET 先动栈或 JBC/JNBS 先修改目标位。
- 已置 PSR.CIRQ 的服务模式遇到 REP/REPB 时同样报告未实现的 IREP 边界，
  不把它当作新增合法循环模式执行。
- `target/dmcu/cpu.h`、`hw/dmcu/np560.c`：既有故障信息附加原因
  `REPEAT_REASON=target` 或 `processing-mode`，并明确 `IREP_DISPATCH=unimplemented`。
  该字段是宿主诊断，不是客体 EXR。
- 不清除循环然后继续，不对原厂地址或游戏名特殊处理；显式 ROM 空洞仍保留更具体的缺 ROM 诊断。

完整的非法编码分类、其它重复边界及异常派发仍是后续工作。

## 验证范围

`scripts/test_np560_repeat_legality.py` 复用既有无 NAND CPU runner。
23 个禁用目标类别及 2 个服务模式场景，分别以普通执行和 icount 检查；
全部保留原寄存器/栈指针并停在目标，不调用软件 TRAP。
这是按语义逐类检查，不是任意数量的压力测试。

- 新边界：`tmp/np560-repeat-illegal-after-20260906-v1/report.json`。
- 合法循环与原厂四方向完整缓冲：`tmp/np560-repeat-illegal-nested-regression-20260906-v1/report.json`。
  包含单指令/块循环、块中部/末尾、嵌套硬件中断与返回；全部通过。
- 软件 TRAP：`tmp/np560-repeat-illegal-trap-regression-20260906-v1/report.json`。
  包含 REPB 块内 TRAP、嵌套与真实栈帧返回；全部通过。

旧核心 SHA-256：`f9f82d55fc1d7e209dc38b40583fe25a1f371721e57255d8cec3ad9b5415e532`。
新核心 SHA-256：`035b2df5bd14a8cb057f3a7114f1acaead4f0d9830930ed97c99f4e603fe3d20`。
以上每个定向诊断进程均已退出，不把脚本通过解释为整机功能完整。

## 原厂实际路径回归

新核心以相同 PRG、ROM、NAND 底图和已有 journal 独立冷启动，进入原厂桌面、
游戏列表及阿诺标题，再原生读取第二槽，地图/位置/朝向与战后生命均恢复。
这条实际使用路径没有触发新防护，详见[阿诺第二槽读回](np560_npe_arno_battle.md)。
reader Web/QEMU 87095/87097 已正常退出 0；不代表所有游戏/应用均不受影响。
