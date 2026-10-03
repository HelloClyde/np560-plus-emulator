# ICR 中断嵌套与返回现场

日期：2026-09-05。实现对象是 QEMU DMCU CPU，不是新的 ROM 服务或宿主调度器。

后续：[实际 TBC/TBICR 时基](../hardware/np560_timebase.md) 已清退本文构建仍保留的旧 tick，
并将 0494/0496/0498 恢复为软件 RAM。本文下面的构建与未完成边界是当时记录。

## 原因与依据

原实现 `dmcu_irq_select()` 已比较 PRI/CPRI，但 `dmcu_cpu_exec_interrupt()`
又因 `in_interrupt` 无条件拒绝中断。因此即使请求优先级更高，也只能等当前 ISR 返回。
这与硬件优先级模型不符，且阻止定时器/DTU 服务抢占低优先级工作。
这项缺口已确认；**没有证据把菜单花屏或缺失的音频算法归因于这一项**。

本轮使用 PDFium 渲染并目视核对本地 `tmp/cnpatent/CN1916884A.pdf` 完整相关页：

- PDF 第 10 页，说明书 7/123：CPRI 与 CIRQ。两条条件在原页中确实都印为
  `CIRQ=1`，分别要求更高和大于等于；不是文字抽取错误。继续保留原有推断：
  CIRQ=1 只接受更高优先级，CIRQ=0 可接受同级。此推断没有升级为真机测量结论。
- 第 13–14 页：PRI 为 0–3、数值越大优先级越高；更高请求搁置当前工作，
  接受请求后清 RQ，中断将 PRI 复制到 PSR，DTU COUNT=0 请求最高优先级服务。
- 第 93 页：RETI 从栈依次取 PSR、可选 CS、PC；SOCR.NSEG 决定是否取 CS。
- 第 120、122 页：REP/REPB 在中断期间暂停、返回后恢复；ISR 中的非法重复指令
  和 IREP 是单独的架构边界，不能把任意 ISR 内执行 REP 称为已支持。

## 改动

1. ICR 服务期间允许再次按现有 ICR/PSR/IE 规则仲裁，不再由 `in_interrupt` 一票否决。
   同级/低级请求仍保留，返回后重新仲裁；DTU COUNT=0 的优先级 3 同样参与。
2. 每次嵌套保存上一层的帧位置、重复指令影子及相关诊断归属；内层完成后恢复上一层。
   不能让内层 RETI 清掉整个 `in_interrupt` 或丢失前台 REPB 状态。
3. PSR/CS/PC **仍只从 guest RAM 栈弹出**。上下文不保存/恢复 GPR、FP、DS，
   不拿“预期返回地址”修补实际返回地址。ISR 自己负责它使用的寄存器。
4. ICR 的 synthetic RETI 只改变真实栈给出的状态，不在尚未弹到硬件帧时结束该层。
5. CPU 复位清除活动层与悬挂层，对象销毁释放上下文。无固定“四层数组”限制；
   正常递增的四种优先级可形成四层，但软件改变 PSR 后不能凭空假定同一上限。
6. 增加只读 `IRQ_NESTING=DEPTH/MAX/ICR`。历史 `IRQ64` 的 ENTRIES/RETURNS
   仍包含所有来源，不能把这个旧字段名理解为全都由 64 Hz 产生。

实现位于 `qemu-dmcu/target/dmcu/{cpu.c,cpu.h,helper.c}`，只读状态位于
`qemu-dmcu/hw/dmcu/np560.c`。没有固件地址跳过、返回成功桩或宿主菜单逻辑。

## 验证：执行变化，而非测试次数

`scripts/tests/test_np560_interrupt_nesting.py` 的 guest 自己安装向量、置软件请求，
或配置实际 Timer0 产生请求；宿主仅控制运行/暂停/复位并读取结果。
没有宿主改 guest RAM，没有使用 NAND。结果在 `tmp/np560-nesting-v3/report.json`。

| 场景 | 观察到的结果 |
| --- | --- |
| 四种优先级连续抢占 | 进入顺序 0→1→2→3，退出顺序 3→2→1→0；分段帧 SP 为 3FFA、3FF4、3FEE、3FE8，最后回到 4000 |
| 同级、低级等待 | 外层先返回，待处理来源随后执行；没有丢请求或错误抢占 |
| NSEG 与 icount | 四字节帧正确；`icount shift=5` 同样得到完整嵌套及返回 |
| 前台 REPB | 五次前台迭代均真实完成，嵌套未消费或丢失前台计数；SAVES=RESTORES，CONFLICTS=0 |
| synthetic RETI | 清 CIRQ 的 guest 回调可被同级请求抢占，但不提前结束外层硬件帧；最终前台重复状态恢复 |
| DTU 完成请求 | 空 COUNT 的 ED 来源按优先级 3 抢占；此项是完成仲裁检查，不冒充实际搬运 |
| Timer0 硬件请求 | guest 只开 EN、不写 RQ；低级 ISR 等待真实定时到期，高级 ISR 停表并返回后等待才结束；正常及 icount 均通过 |
| guest 修改栈中 PC | 内层返回实际按修改后的 RAM PC 跳过指令，诊断 BAD=1 记录偏离，但不拦截或修回地址 |
| 四层运行中复位 | 复位后 DEPTH/MAX=0，重复指令影子与计数清零 |

反例保留在 `tmp/np560-nesting-before-v2/four-priorities.json`：
旧 `a144d548...` 构建跑同一 guest，实际只能依次完成 0、1、2、3 四个 ISR，
每个都在 SP=3FFA，进入标记为 1、3、5、7。新构建为真正的嵌套，不是旧行为重新命名。

同一新构建上还运行了现有检查：

- `test_np560_icr_vectors.py`：RAM/ROM/NSEG、EN/IE、阈值及未改写的原厂 `08:481A`。
- `test_np560_interrupt_psr.py`：所有低位标志组合的 synthetic 帧、旧 tick 的实际帧、直接 IE 屏蔽。
- `test_np560_timers.py`：三路周期、暂停、六种原厂双路传输组合及 icount 组合均通过。
- `test_np560_audio.py`：原厂 `08:33FA` 与 DAC 数字采样、暂停和活动设备复位通过，
  结果在 `tmp/np560-nesting-audio-v1/`；仍不是原厂音乐/游戏 codec 验收。
- 原厂零输入冷启动 `tmp/np560-nesting-cold-boot-v1/report.json`：约 68.26 秒，
  最后三帧顶栏均 0/5280 差异，现有 CPU/NAND 故障项为零。已目视 `final.png`，
  学习菜单、开始和 08:00 时钟正确。冷启动截图不证明间歇性花屏或完整 NPE 已修复。

## 构建与镜像身份

新 QEMU：`E:/qemu-dmcu-build/qemu-system-dmcu`，46,556,240 字节，SHA-256：
`b3f4483ae168926bbef2a428a267c52ac8a9c64868d84a4b8c6177a88537149f`。

旧构建保留为 `qemu-system-dmcu-pre-nesting-20260905`，SHA-256：
`a144d54806e745731f651d5acbbcc85b5292990aa713bc25c76e65abc7aae8f4`。

冷启动输入未改：原始 PRG `d555609e...`，重建 resident `a243f8ba...`，
原厂文件 API 导入 NAND `7783876b...`。完整身份在冷启动 report 中。
没有生成、覆盖或保存大 NAND，没有改 ROM；用户 8807/8808/8809 未重启或操作。

## 未完成边界与下一步

- 旧固定入口 tick 没有已确定的 ICR/优先级契约，还使用原厂单槽保存区；本轮保留它与
  ICR 嵌套路径的隔离。**这不是完整中断模型**，下一步必须依据真实 TBICR/定时配置清退旧源，
  不能给旧源猜一个优先级再称作硬件实现。
- 同级平局规则、CIRQ 原文歧义、真实异常/IREP、完整重复执行限制、SP/FP 历史延后保护、
  周期精度与完整中断屏蔽时序仍待闭合。嵌套记录尚不支持整机迁移/快照。
- 现有写入诊断主要观察当前层，不能用“没有报告覆盖”证明所有悬挂帧在任意代码下无损。
- 原厂正常 NPE 入口仍有之前已证实的 `02:ACD8` 等 ROM 流后端缺失；
  本轮没有还原这些算法，也没有重新验收游戏。不能将 CPU 嵌套修复算作 ROM 或完整游戏完成。

本项补齐一项明确的共同硬件机制；总体工作继续按 [整机计划](../plan.md) 推进。
