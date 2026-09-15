# 普通 MUL 小数模式与 MUL/UMUL 溢出标志

日期：2026-09-06。修正 DMCU 的通用 CPU 运算，不是恢复音频解码 ROM。
本轮没有替换生产 PRG、重建 ROM 或 NAND，也没有根据原厂函数地址特判乘法。

## 依据与边界

逐页查看 [CN1916884A 原始扫描件](../tmp/cnpatent/CN1916884A.pdf) PDF 第 32、33 页
（说明书第 29、30 页）完整 MUL/UMUL 表，以及第 132 页图 7A/7B。
[公开原文](https://patents.google.com/patent/CN1916884A/zh) 为同一来源，不是独立真机验证。

- MUL 是有符号乘法，SOCR.FR 开启时乘积左移一位；FR 位在图 7A 的 bit 3。
- MUL 的 V 表示结果无法用有符号 double word 表示；UMUL 明确要求 V 清零。
- UMUL 定义没有 FR 步骤；不因 FR 开启而把无符号乘积加倍。
- R6:R7 保存 32-bit 结果，继续保留 R4/R5，包括 R5 高字节 SE。
  这是已有原厂调用代码支持的实现边界，不因文档泛称 AR 而改为覆盖整个 40-bit 累加器。

两页的 C 栏均误写“V 设为 1”，与独立 V 栏冲突；其 C 精确语义仍未闭合。
本次没有改 C，定向检查在读取 PSR 后屏蔽该位，**不把保持旧 C 当成原厂正确行为**。
MUL 小数溢出时的 N 沿用写入后 32-bit 符号位；极端复合标志、时序和芯片版本差异仍需真机等证据。

## 修复前的实际反例

旧核心 SHA-256：`4b70b03ecc9a1212a458051d113f1d741ac5b6d136ba7178ae490e5c5fa2634a`。
检查程序自己以 guest 指令准备 SOCR、操作数及初始 PSR，不修改运行中的 guest RAM。

| 操作 | 旧核心实际值 | 有依据的预期 |
| --- | --- | --- |
| FR=1，MUL 4000 × 4000 | R6:R7=1000:0000，旧 V=1 未清 | 2000:0000，V=0 |
| FR=0，UMUL 0048 × 0003，初始 V=1 | 结果 0000:00D8 正确，但 V 仍为 1 | 结果不变，V=0 |

两个独立反例均实际断言失败，QEMU PID 59226、59317 都正常退出 0；不是启动失败、超时或崩溃。
证据分别在 `tmp/np560-mul-fr-before-20260906-v1/`、`tmp/np560-mul-v-before-20260906-v1/`。
每个目录的单项 JSON 和 CPU 日志保留实际结果；顶层 report 的 passed=false。

## 实现

`qemu-dmcu/target/dmcu/helper.c` 的普通 C0/C1 分支：

- 分开处理 signed MUL 与 unsigned UMUL，仅前者读取 SOCR.FR 并将乘积乘以 2。
- 中间乘积使用 int64_t，避免负数左移和 32-bit 有符号溢出的 C 未定义行为。
- MUL 按有符号 32-bit 范围更新 V；UMUL 清 V，不再遗留上一条指令的值。
- 两个源操作数先取完再写 R6/R7，继续支持源与结果寄存器重叠。
- 没有启用饱和、写入 ARX、改变 C 或 DSP 的 MV/MS/MX 等其它位。

没有新建监控框架；扩展已有 `scripts/tests/test_np560_multiply_registers.py`，
复用现有隔离运行器，保留 `--qemu` 调用方式，增加可选结果目录和单例选择。

## 当前验证

新核心 `E:/qemu-dmcu-build/qemu-system-dmcu`：46,599,688 bytes，SHA-256
`cbf6e9ea2b8317dd38f79f06fc293b5104ce109a0d97ed120f96a24ef1bcda01`。

`tmp/np560-mul-fr-20260906-v1/report.json` 通过：小数/整数正负值、零、极值、
溢出置位及清除、UMUL 不受 FR 影响、R6/R7 源别名、R4/R5 和非目标标志保留，
以及普通与 icount 下的关键小数边界。所有隔离实例 exit 0，无 NAND、HLE 或宿主 RAM 注入。

同核心 `tmp/np560-mul-fr-original-gain-20260906-v1/report.json` 通过原厂
`08:34C4..3534` 完整样本增益函数（x1、第七档，普通时钟），样本输出和栈恢复仍正确。
这是相邻 DSP 路径回归，不证明该函数使用本次新增的普通 MUL.FR，也不是实际游戏解码声音。

同核心 `tmp/np560-mul-fr-coldboot-20260906-v1/report.json` 零输入冷启动通过，
98.77 秒时结束；最后连续三帧学习顶栏与原包资源 0/5,280 像素差异。
已目视 `final.png`：五类顶栏、学习列表、开始按钮和时钟完整；无 ROM_MISSING、
UNSUPPORTED、INVALID_CONTROL，NAND ERROR=0。仅验证这条冷启动，不关闭其它菜单/应用问题。

冷启动使用未改动的原始 PRG（`d555609e…`）、重建 ROM（`a243f8ba…`）和
原厂导入 NAND（`7783876b…`），完整大小/指纹在上述 report。
未开启 NAND 保存，也未生成新大镜像。隔离 QEMU PID 59562 已回收、returncode=0，
外层命令也已退出；journal 的 `last_event=qemu_reaped` 是退出记录，残留 `phase=starting`
不是它仍存活的证据。其它本轮隔离实例同样均已退出，用户实例没有替换或重启。

## 尚未完成

本次解除两个 CPU 语义缺口，没有取得 `02:ACD8/AD92` 或 B6DE/B7AA/B816/B84E
流服务算法，也未移除 `01:4674/46CC/46D0` 临时桩。
未重跑同一已知声音开启入口、未把无声游戏路径当作原厂声音完成。
后续仍按 [整机计划](plan.md) 恢复有依据的 ROM 状态与处理行为；CPU 完整性与全部游戏兼容性尚未完成。
