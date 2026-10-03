# 原厂 RESET 指令与软件复位内存保留

日期：2026-09-06。补齐 CPU 的真实指令和片上设备复位路径，不是恢复音频 ROM，
也不是宣布原厂 USB 升级、完整开关机或硬件复位语义已全部完成。

## 缺口与依据

已按 PDF 技能完整查看 [CN1916884A 原始扫描件](../../tmp/cnpatent/CN1916884A.pdf)
PDF 第 115 页（说明书 112/123 页）。RESET 编码为 `3F FF`，正文规定重置寄存器，
内存内容不改变。该页状态标志表又写 Z/C/N/V 不受影响，与“所有寄存器重置”存在
解释边界；此次复用已有 CPU reset 默认值，不据此宣称 PSR、SP 和全部 SFR 初值已完全核对。

这不是把数据中的短字匹配当成指令。原厂可达控制流包含：

- `USB_Loader_Noah.bin` 的 `00:14E8..14EE`：`MOV R0,0; MOV [F226],R0; RESET`，
  来自 `00:11DA` 的分支。文件 offset `04E8..04EF` 原始大端字节为
  `48 00 A8 F0 F2 26 3F FF`。
- 升级包 block1 的 `52:505C`：原厂调用 `52:875C` 返回、五条 NOP 后执行 RESET。
  对应既有 [可达反汇编](../disassembly/NP560_UPD_block1_reachable.asm)。

此前 Python 反汇编器识别 RESET，但 QEMU 指令执行器没有实现它。
旧核心 `fd83eb62…` 的定向反例见
`tmp/np560-software-reset-before-20260906-v7/reset-icountNone/failure.cpu.txt`：

```text
UNSUPPORTED=03:031c WORD=3fff COUNT=1
FIRST_PREV=03:0318>03:031c WORD=a8f0 EXT=f226 SP=4000 FP=0000
```

这里原厂尾段被原样按 word 换序放入隔离 caller 的 `03:0316`；其绝对 MMIO 地址不变。
这是原厂复位尾段执行证据，不是完整 USB 协议到复位命令的端到端证明。
早期夹具的字节比较、LCD 访问及 QOM 属性准备错误已经纠正，不把那些失败归为产品缺陷。

## 实现

- `target/dmcu/helper.c`：`3FFF` 请求 `SHUTDOWN_CAUSE_GUEST_RESET`，退出当前执行块，
  不继续执行复位指令后面的代码。
- `target/dmcu/translate.c`：RESET 在 TCG 的系统/设备操作边界结束，支持 icount。
- `target/dmcu/disas.c`：增加 RESET 和同组 CRIT/IGNDS 的反汇编名称。
- `hw/dmcu/np560.c`：区分 guest 软件复位与现有 Web/QMP 冷重启。

| 状态 | guest RESET | 现有 Web/QMP 冷重启 |
| --- | --- | --- |
| CPU / 已建模片上寄存器 | 复用 CPU reset，再复位 Timer、timebase、DAC、ECC、ADC、NAND 控制器 | 保留原来的 CPU / 设备复位流程 |
| 内部 X/Y RAM、外部 RAM、可写代码及两个动作覆盖区 | 保留，不恢复启动快照 | 保留原来的启动快照恢复 |
| NAND data/OOB | 不回载输入种子；仅重置控制器 | 同样不回载输入种子 |
| 外部 ST7529 | 不凭空重置控制器或清 GRAM | 保留原来的面板重置 |
| 物理按键 | 保留按下状态；扫描驱动口回到 FFFF | 保留原来的输入释放 |

CPU 与外部 LCD reset 引脚是否有板级联动仍没有证据，本实现不额外制造外部复位信号。
软件 RESET 目前仍进入所选 boot-mode 的既有 reset PC；真实启动引脚、完整 mask-ROM
启动选择和 loader 复位后退出下载模式，仍需原厂代码/硬件资料及完整流程支持。

## 已验证的实际行为

脚本：[test_np560_software_reset.py](../../scripts/tests/test_np560_software_reset.py)。
所有 RAM、寄存器、LCD 内容及可写代码准备由 guest 指令完成；宿主只读取结果、
按住物理矩阵键 M61 退出观察循环，以及在软件复位通过后发一次 QMP 冷重启。
不加载生产 NAND，不写运行中 guest RAM。

`tmp/np560-software-reset-20260906-v2/report.json`：普通模式和 icount=5 均通过。

- 原厂 RESET 尾段执行后返回已配置启动入口，数据银行恢复 DS0=000、DS1=001。
- 通用寄存器和移位缓冲恢复既有 reset 值；复位发生时的 CRIT/IGNDS 不残留。
- 内部 X `2404=A55A`、Y `8500=B66B`、外部 `52:2340=C77C` 均保留。
- guest 把可写代码的立即数从 DEAD 改为 CAFE，复位后实际执行结果仍为 CAFE。
  不只是数据读回正确；也检查了复位后的取指视图。
- `2406` 的复位后顺序执行毒标记仍为零，证明没有继续执行 RESET 的 fall-through。
- 活动 Timer2、timebase 与 DAC 复位；非零 LCD GRAM 和按住的 M61 保留。
- 随后 QMP 冷重启仍恢复原始 RAM / DEAD 代码，释放输入并关闭面板，未混同软件复位。
- 两个自有 QEMU PID `77897 / 77902` 均正常退出 0。

上述 NAND 保留是代码路径审查结果；这个短指令夹具没有烧写 NAND，不能把它称作
“软件 RESET 跨复位保存新闪存内容已实测”。既有设置/存档持久化记录仍保留其版本边界。

同一核心的原厂零按键冷启动也通过：
`tmp/np560-software-reset-coldboot-20260906-v1/report.json`，86.83 秒。
设备先显示每日一句，再自然进入学习桌面；最终 LCD 已目视查看，顶栏与原厂资源一致，
ROM_MISSING / UNSUPPORTED / INVALID_CONTROL 均为 none，NAND ERROR=0。
没有注入按键、没有宿主 guest-memory 写入、没有启用 NAND 保存。
自有 QEMU PID `77910` 正常退出 0；输入第三槽 NAND 的结束后哈希未改变。
这证明该冷启动，没有把旧游戏战斗/读档记录改称为新核心已完整游玩。

## 版本与剩余工作

- 新核心 `E:/qemu-dmcu-build/qemu-system-dmcu`：46,596,960 bytes，SHA-256
  `bbe9f1c369a1ad737fcdd48b80b2b891fc34b8db5bc261ff4224880fa5e1432a`。
- 旧核心保留在 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-software-reset-20260906`，
  SHA-256 `fd83eb62b7390533d2c6b3b9edea827407c9c76e17a5f4d5f7791a34886d69d1`。
- 原始 PRG 未改：`d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`。
- resident ROM 未改：`a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef`。
- 原厂 loader 未改：`482e5f84dab922cf1af06eb76e93e1e22edea2c53ee90aed0c1880878aec0cd9`。
- 冷启动输入为第三槽 battle NAND，SHA-256
  `6e4e2672fc244fd1bb1f1745059790ce8031208e5775c345ca2c5e9742d81133`，没有复制或覆盖。

用户 8807/8808/8809 未被操作、关闭、重启或替换。没有提交 Git。
下一步仍须闭合真实 USB/升级流程中的复位启动选择，以及整机的原生保存和电源语义；
音频缺失服务、未确认的 DSP 寻址/异常、全部原厂应用和整机忠实度也仍未完成。
