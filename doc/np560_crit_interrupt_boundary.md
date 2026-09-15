# CRIT：保护结束后立即重新检查待处理中断

日期：2026-09-06。修正的是 CPU 中断准入的指令边界，不是声音解码或完整时序恢复。

## 依据与旧版反例

已用 PDF 技能目视核对 [CN1916884A 原始扫描件](../tmp/cnpatent/CN1916884A.pdf)
完整 PDF 第 113 页 CRIT、第 114 页 IGNDS。CRIT 的操作定义是在执行指定数量的后续
指令期间禁止硬件中断，然后解除这项保护；不是一直保护到宿主翻译块结束。

保留既有低两位编码加一、对应 1–4 条指令的约定。上述页面没有明确说明这项编码换算，
本次不将其称为新增的硬件证据；也不推导连续 CRIT 重设条数、同步异常或总线竞争语义。

旧核心 SHA-256：`ae6eaa2258479e4199327f3862ffeee0f54968e243b604629e7520b205b2c3d1`。
保留为 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-crit-boundary-20260906`。

诊断 guest 自己配置中断向量、打开 IE，并执行 CRIT。第一条受保护指令设置待处理 ICR
请求，随后三条 ADD 将 R9 从 0 加到 3；保护外再放十二条 ADD 和一次 SFR 读取。
ISR 从 R9 和实际 SRAM 中断栈分别记录前台进度与返回 PC。所有写入来自 guest，
不使用 NAND、运行中 RAM 注入或重建声音服务。

| 观察项 | 旧核心 | 修正后同一程序 |
| --- | --- | --- |
| ISR 看到的 R9 | 15 | 3 |
| ISR 栈中的返回 PC | `20:0462` | `20:0448` |
| 主程序读到的 ICR | `0033`，读时请求尚未应答 | `0031`，已应答 |
| 完成后的 R9 / SP | 15 / `6000` | 15 / `6000` |

旧版多执行了保护外的十二条 ADD 和一次 PUSH SFR，才在下一个翻译块边界进入 ISR。
它没有崩溃，CPU 故障诊断也没有报错，但执行先后关系已经错误。
[旧反例](../tmp/np560-crit-boundary-before-20260906-v1/count-4-timer-False-masked-False-nseg-False-wide-False-icount-None.json)
保留了实际寄存器、日志和正常退出码 0。

## 实现变化

[helper.c](../qemu-dmcu/target/dmcu/helper.c) 的公共指令完成路径，在 CRIT 的计数从
非零变为零时结束当前 TCG 块，让 QEMU 重新执行既有中断准入检查。
IGNDS 结束时原本就会因地址空间变化退出 TCG，本次不重复改变它的寻址实现。

- 不改写 SOCR.IE，不清除请求，不在每条普通指令后强行派发中断。
- 不按应用名称、PC 或音频入口特判，不改变原厂 PRG、resident ROM、NAND 或 Web。
- 不宣称实现了精确中断延迟、流水线、DTU 抢占或全部硬件周期。

## 已完成验证

新核心为 `E:/qemu-dmcu-build/qemu-system-dmcu`，46,826,344 bytes，SHA-256：
`40f88f23ecd1dd75fbb4335780bfc94d56b8ac1a84b23a1b269002825ed9f975`。

[定向程序](../scripts/test_np560_crit_boundary.py) 复用现有 guest 执行器。
[同版结果](../tmp/np560-crit-boundary-20260906-v1/report.json) 验证了 1–4 条保护、
32-bit 指令按一条计数、NSEG 栈、原本关闭的 IE、icount，以及 Timer0 实际产生请求。
检查的不只是运行结束，还包括 ISR 的返回 PC、保护内外进度、请求应答和返回后的 SP。
各隔离进程均正常退出 0。

相邻 IGNDS 机制的同版回归记录分两部分，不能将第一部分冒称完整报告：

- `tmp/np560-crit-ignds-20260906-v1/` 已完成四项保护条数检查，均 passed / exit 0。
  随后会话环境发生变化，原测试会话句柄失效，WSL 进程表确认旧进程已经不存在；
  没有总报告，不将中断后的剩余检查记为成功。
- 确认旧进程不存在后，只执行未完成的六项，保存在
  `tmp/np560-crit-ignds-remaining-20260906-v1/`：DS1、NSEG、IE 关闭、icount、
  真实 Timer0 和 Timer0/icount，均通过，主命令退出 0。没有重跑前四项。

原厂时基安装 `32:81D4`、配置 `32:DC20`、ISR `08:40D0` 的两种执行模式也通过，
见 `tmp/np560-crit-original-isr-20260906-v1/`。实际四次时基事件使倒计数从 100 到 96，
其它软件计数归零，向量、栈和返回仍正确。该夹具保留既有原厂软件 guard，
不执行上层应用回调，因此不是全部调度或声音播放验收。

同一核心、原始 PRG、严格缺口 ROM 和既有 vendor-file-import-v3 NAND 的零输入冷启动
在 92.24 秒到达学习桌面：[启动报告](../tmp/np560-crit-native-boot-20260906-v1/report.json)。
最后三个顶栏样本均与原升级包对应资源一致（0 / 5280 像素差异），
[原始 LCD](../tmp/np560-crit-native-boot-20260906-v1/final.png) 已目视核对。
ROM_MISSING、UNSUPPORTED、INVALID_CONTROL 均为 none，HLE off，NAND ERROR=0。
未开启 NAND 保存、未注入按键或 RAM；退出后底图哈希仍为
`7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`。
隔离启动进程的生命周期记录为 qemu_reaped / exit 0，不保留后台测试实例。
这只证明本次默认启动回归，不外推为全部菜单、游戏、声音或完整调度正确。

本轮没有对用户 8807/8808/8809 发出关闭、重启或替换操作。会话变化后重新核对的
WSL 进程表已没有原先那些 QEMU，具体环境变化原因未查明；不能继续把旧 PID
或旧运行记录当作它们仍在线的证据，也没有据此自动重启它们。

## 本轮 DSP 核对的边界

同时核对了 PDF 第 28–31 页 DIV/DIVL/UDIV/UDIVL，以及第 106–112 页
EDS/EDU/BEDS/BEDU 的完整操作、标志和编码表。

- 指数提取的核心计数规则与现实现一致，SE 写入 RB10 即 R5 高字节，并非字节别名错误。
  本次没有修改该算法，也没有新增指数指令已完整通过真机比较的结论。
- 有符号除法页面的公式印有 `-ARL` / `-ARH:ARL`，而文字说明是直接相除；
  溢出后的寄存器结果也未写清。不能忽略扫描件中的符号，更不能据这一处冲突
  将所有商强制取反。本次保留已有除法实现，歧义需要原厂实际用途或额外资料消解。

本次没有恢复声音 codec、增加 ROM 字节或解决完整 NPE 有声运行；
`02:ACD8`、`01:B6DE` 等缺口仍见 [声音来源边界](np560_audio_codec_provenance.md)。
