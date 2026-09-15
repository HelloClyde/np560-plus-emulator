# 程序内存一致性：跨页取指与内部 SRAM 写入

日期：2026-09-06。已分别修复跨页取指跟踪和内部 SRAM 写入通知两个缺口。
这是通用可执行 RAM 一致性修正，不是原厂 ROM 服务重建；不据此关闭所有历史菜单花屏。

## 确定性反例

使用 VMA03 的共享代码/数据 RAM，guest 自己运行以下流程，无 NAND、重建 ROM、
宿主 RAM 注入、宿主 flush 命令或按入口地址的同步补丁：

1. 调用 `03:0FFE`，那里是四字节 `MOV R0,#1234`，随后 RETS；返回值存入 R2。
2. guest 以 DS0=6、普通数据写指令将 `03:1000` 的立即数字改为 `BEEF`。
3. guest 读回该字到 R3，再调用相同的 `03:0FFE`，将返回值存入 R4。

DMCU 的 QEMU 翻译页为 2 KiB，指令首字在前一页末尾，立即数字在下一页首部。
旧核心实际结果：**R2=1234、R3=BEEF、R4=1234**。
数据确实写入了新值，但再次执行使用缓存里的旧立即数；没有返回地址损坏或未知指令。

- 旧核心 SHA-256：`cbf6e9ea2b8317dd38f79f06fc293b5104ce109a0d97ed120f96a24ef1bcda01`。
- 反例：`tmp/np560-code-extension-before-20260906-v1/`，QEMU PID 60506，正常退出 0。
- 断言实际失败；CPU、单项 JSON、日志及顶层 passed=false 均保留。
- 另一个在页尾放两个 NOP、把整个 MOV 放到新页的对照，在旧核心已通过，记录为
  `tmp/np560-code-coherence-before-20260906-v1/`。当前保守分类会令 NOP 结束翻译块，
  因而这个对照不是同一种“单条指令跨页”；不能用它否定立即数字的失败。

## 根因与通用修正

依据是当前工作树的 QEMU 实现，而不是用另一款芯片推测缓存行为：

- `accel/tcg/translator.c::translator_access()` 为跨页取指登记、锁定 TB 的第二个 RAM 页，
  并处理 MMIO 不缓存的回退；`translator_lduw()` 使用它。
- DMCU 的 `target/dmcu/translate.c` 之前对首字和扩展字都直接调用 `cpu_lduw_code()`。
  该接口取得字值，但没有将扩展字所在页登记为这个翻译块的依赖。
- `target/m68k/translate.c::read_im16()` 等现有目标使用前述通用接口读取立即数，
  可作为 QEMU 接口用法的交叉检查，不作为 NP560 硬件的独立依据。

本轮仅修改 `qemu-dmcu/target/dmcu/translate.c`：

1. 首字和扩展字统一改用 `translator_lduw()`，由实际 RAM 页决定写后失效。
2. 到达或跨过翻译页边界后结束块，不再继续推测翻译下一页的另一条指令。
   跨页的单条四字节指令仍完整翻译，其两页都由通用机制登记。

没有让每次写入都全局 flush，没有按游戏名、ROM 入口或本反例地址特判，
也没有改 guest 指令、ROM 映射、数据字节序、CPU 指令长度或设备时钟。

## 同核心结果

新 `E:/qemu-dmcu-build/qemu-system-dmcu`：46,599,840 bytes，SHA-256
`31dc2d9c0cbb946809cb1aecb7155264de2b3302008d2e03b5e63164239647c6`。

`scripts/tests/test_np560_code_coherence.py` 是一项短时定向检查，复用已有 Emulator，
不是新增自动导航或压力测试平台。

- `tmp/np560-code-coherence-20260906-v1/report.json`：同页、整个指令位于新页的对照、
  单条指令跨页三种布局均通过普通/icount 运行。立即数反例现在得到
  **R2=1234、R3=BEEF、R4=BEEF**，SP 恢复为 6000，隔离实例均 exit 0。
- `tmp/np560-code-coherence-original-gain-20260906-v1/report.json`：未改动的原厂
  `08:34C4` 样本增益函数 x1/第七档通过，样本及栈恢复正确。
- `tmp/np560-code-coherence-coldboot-20260906-v1/report.json`：99.30 秒零输入冷启动通过；
  最后三帧学习顶栏与原包资源 0/5,280 像素差异，已目视 final.png 的顶栏、列表、开始和时钟。
  无 ROM_MISSING、UNSUPPORTED、INVALID_CONTROL，NAND ERROR=0。这里只覆盖冷启动，不代表所有应用通过。

冷启动使用原始 PRG `d555609e…`、重建 ROM `a243f8ba…`、原厂导入 NAND `7783876b…`，
完整指纹在报告中。未开启 NAND 保存，没有新大镜像；QEMU PID 60941 已回收、returncode=0，
外层命令已退出。所有本轮隔离实例均已关闭，用户运行实例没有替换或重启。

## 内部 SRAM：独立的写入通知缺口

跨页修复后的核心 `31dc2d9c…` 仍存在第二种确定性错误：guest 用 FP/R11
在 `00:0500` 安装 `MOV R0,#1234; RETS`，首次调用返回 1234，随后通过 FP
将立即数改为 BEEF。读回正确，但再次调用仍返回 1234。

- 原始失败：`tmp/np560-internal-code-before-20260906-v1/`，PID 61781，exit 0。
- 本轮另复现同一执行块内的写后取指：`00:0500` 的 FP 相对写入将紧随的
  `MOV` 立即数改为 BEEF，后续 MOV 仍执行旧 1234。记录在
  `tmp/np560-internal-same-block-before-20260906-v1/`，PID 62818，exit 0。
- 两个现场都是 guest 自己安装和改写代码，无 NAND、宿主 RAM 注入或 flush 命令。
  全 TRAP 的小 ROM 夹具只声明可执行范围，内部 SRAM 别名覆盖其代码区；它不是原厂 ROM。

### 根因与实现

`helper.c::internal_data_write()` 及 `cpu.c::dmcu_interrupt_push()` 原来直接写宿主指针，
绕过 QEMU 的 RAM 脏页与代码失效通知。另一方面，翻译器允许 FP/SP 写指令与其后指令
处在同一 TB；即使补了失效通知，也不能阻止已经开始执行的 TB 使用旧立即数。

修复采用 QEMU 自身的内存机制：

1. 板级将内部路径的根明确绑定到现有 `s->data` RAM backing；CPU 新增
   `dmcu-internal` 地址空间。它不经过板级数据总线、DS/IGNDS 或同地址 MMIO 覆盖。
   没有增加新的 guest 地址、硬件 MMU 模式或安全属性。
2. 普通 FP/SP/Y 写入、调用压栈与 IRQ/TRAP 压栈共用
   `dmcu_internal_memory_write()`。字节保留 `logical ^ 1` 通道，字保留小端 backing。
   `address_space_stb/stw_le()` 通过真实 RAMBlock 对所有可执行别名失效并更新脏页。
   `memory_ldst.c.inc` 与 `system/physmem.c::invalidate_and_set_dirty()` 是接口行为依据。
3. 翻译器使可能写 SRAM 的 MOV、复制、内存移位、PUSH SFR、LINK、TRAP 等指令结束 TB。
   读内部 SRAM 的指令仍可共块；没有为每次压栈做全局 TB flush。

内部读取、已有只读诊断、原厂 PRG、ROM 镜像、NAND 及硬件寄存器语义未在本修复中更改。
字访问从 16 位起始地址计算，仍保持原有 backing 行为；不借此推测或改变未证实的
非对齐/地址末端异常语义。这里接入了通用脏页机制，但不据此声称整机迁移/快照已验证。

### 新核心验证

核心 `E:/qemu-dmcu-build/qemu-system-dmcu`，46,599,520 bytes，SHA-256：
`4b02ff3398d9dd5ff5fe4bc7e3ef143a333350f747090663b89490964f6c86ea`。

- `tmp/np560-internal-code-coherence-20260906-v2/report.json`：同页、跨页对照、
  跨页立即数、内部字写入、内部字节写入、同 TB 自修改均通过普通与 icount=5 执行。
  原失败的字写入与同块场景得到 R2=1234、R3=BEEF、R4=BEEF；字节场景为 BE34。
- 首次新增字节用例误用 RB1（R0 低字节）作为 R1 低字节，产生 3434 而非 BE34。
  `tmp/np560-internal-code-coherence-20260906-v1/` 保留此失败；核对寄存器编号后
  仅将用例改为 RB3，未为满足用例改变 CPU 字节语义，随后 v2 全部通过。
- `tmp/np560-internal-code-y-pointer-20260906-v1/report.json`：内部 Y 路径、数据银行隔离、
  字节通道、预减/后增、环形寻址与越界操作前拒绝通过。
- `tmp/np560-internal-code-interrupts-20260906-v1/report.json`、
  `tmp/np560-internal-code-trap-20260906-v1/report.json`：硬件中断与软件 TRAP
  的真实 SRAM 栈帧、嵌套、返回及相关定时器/重复执行场景通过。
- `test_np560_stack_mmio_alias.py`、`test_np560_stack_byte_alias.py`、
  `test_np560_internal_byte_lane.py` 均 exit 0；F340 同地址外设未截获返回地址。
- `tmp/np560-internal-code-original-gain-20260906-v1/report.json`：未改动的原厂
  `08:34C4` 样本增益函数 x1/第七档通过，返回与栈恢复正确。

### 原厂冷启动画面

`tmp/np560-internal-code-coldboot-20260906-v1/report.json`：107.65 秒零输入冷启动通过，
最后三帧学习顶栏与原包资源均为 0/5,280 像素差异。已目视 `final.png`，五项顶栏、
学习列表、开始和 08:01 时钟清晰。ROM HLE/UI HLE 关闭，无 ROM_MISSING、UNSUPPORTED、
INVALID_CONTROL，NAND ERROR=0。此结果只证明该原厂冷启动路径，不代表全部菜单切换或游戏通过。

使用未改动的 PRG `d555609e…`、重建 ROM `a243f8ba…`、NAND `7783876b…`，
完整指纹在报告与 process 目录中。没有保存 NAND 或生成新大镜像。
冷启动 QEMU PID 63701 已回收、returncode=0，外层命令 exit 0；本轮其它隔离实例也已结束。
状态文件的旧 `phase=starting` 不是进程仍运行的证据，最终事件为 `qemu_reaped`。
用户实例未替换或重启，已有存档未动。

## 剩余范围

- 旧特定 RETS 地址上的 TB/TLB 同步和特殊代码映射尚未删除。普通数据总线跨页取指与
  内部 SRAM 写通知已分别修复，但其它别名、原厂 loader 与 DTU 等写入路径仍需逐项核对。
- 清退这些特判前，分别确认实际写入路径、RAMBlock 共享关系和原厂装载后的执行。
  不用更大的全局 flush 掩盖不同存储空间或缺失 loader 的问题。
- 本反例没有证明它是旧 `22:1840` 谚语资源覆盖、全部菜单花屏或音频 ROM 停点的根因。
  相关现场继续见 [游戏世界代码写入](np560_game_world_code_write.md)。
- ROM 流服务、原厂声音、完整玩法及其余整机能力仍按 [计划](plan.md) 继续，不因本项通过结项。
