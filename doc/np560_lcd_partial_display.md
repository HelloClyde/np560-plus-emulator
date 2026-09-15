# ST7529：部分显示与正常状态读回

日期：2026-09-06。已实现合法连续块范围的 PTLIN/PTLOUT，并修正正常 STREAD 状态位。
硬件区域滚动、RMW、EEPROM 与可变 duty/COM 时序仍未完整实现。

同日后续：[显存读缓存与读改写模式](np560_lcd_read_modify_write.md) 已补 RAMRD 的 dummy
读取及 RMWIN/RMWOUT，正常状态 bit5 也接到实际模式；下文 RMW 缺失为本篇原构建的边界。
区域滚动、EEPROM 与其余时序缺口仍保留，部分显示检查在新的读取约定下回归通过。

## 原始依据

[ST7529 v1.8 手册](../tmp/pdfs/ST7529.pdf)，SHA-256：
`8565fc8d1f917f89667d1ac3439699888f669ec0ac774438d852848371d02031`。
按 PDF 技能核对完整页面：第 27 页 7.5，第 45 页 PTLIN/PTLOUT，
第 49 页 STREAD，第 58–59 页部分显示例程；复位滚动模式见第 34 页。

- PTLIN 两个参数各取低六位，地址以四行为一块，控制器 RAM 有 40 块。
- 显示范围只影响输出，不应清除或禁止写入范围外的 GRAM。
- PTLOUT 恢复完整显示；越过最大 RAM 范围的设置不操作，保留先前配置。
- 未驱动区域不因 DISINV 而变成全亮像素。
- 正常 STREAD：bit7..6 为滚动模式、bit5 RMW、bit4 C/L、bit3 显示开关、
  bit2 EEPROM access、bit1 正常/反显、bit0 部分显示。

## 旧版反例与实现

旧核心 SHA-256：`886690bb158cd445f73443844377cc0d343eade28d9bcdcd84d276db2e2c367b`。

1. guest 写入若干 RAM 行，再设置 PTLIN(10,18)。正确可见范围为行 40..75，
   旧版却仍输出范围外标记，21 个像素不同；RAM 读回本来就是正确的。
   [像素反例](../tmp/np560-lcd-partial-before-20260906-v1/partial-blocks-10-through-18.json)。
2. guest 切换显示、C/L、反显、部分显示和滚动模式后经 NOP 读取正常状态寄存器。
   旧版实际值仅为 `40 40 40 40 00 00 00 00 40`，
   正确配置值应为 `CA DA DB D9 D1 51 50 40 4A`。
   [状态反例](../tmp/np560-lcd-status-before-20260906-v1/status-register-bits.json)。

两条反例的 QEMU 都正常退出 0；失败来自实际值不正确，不是进程崩溃。

[设备模型](../qemu-dmcu/hw/dmcu/np560.c) 现在在逻辑 RAM 输出地址上应用部分显示区间，
并以独立的“未驱动”值通过可见输出层，避免被反显再次点亮。
状态电极与光栅共用区间控制；总线读取和 `lcd-gram-frame` 逻辑观察视图不受遮蔽。
正常 STREAD 从设备状态组成，复位滚动模式恢复为 whole。
没有改变 PRG、resident ROM、NAND 或 Web 绘图。

## 同一核心的定向验证

新 QEMU：46,830,592 bytes，SHA-256：
`ae6eaa2258479e4199327f3862ffeee0f54968e243b604629e7520b205b2c3d1`。
旧二进制保留为 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-lcd-partial-20260906`。

[guest 检查](../scripts/tests/test_np560_lcd_partial.py) 通过实际指令写 LCD/读 LCD，再将结果存入 RAM，
宿主仅读取结果。没有 NAND、HLE、运行中 RAM 注入或前端补画。

[完整记录](../tmp/np560-lcd-partial-20260906-v1/report.json) 已验证：
连续块、单块四行边界、退出恢复、LI 与反显组合、参数高位忽略、越界不操作、
状态电极、隐藏区写入及退出后重新显示，以及上述正常状态位。
[行列扫描回归](../tmp/np560-lcd-partial-scan-20260906-v1/report.json) 也通过。
两组隔离进程均已正常退出。

同一核心、原厂 PRG、严格缺口 ROM 与既有 vendor-file-import-v3 NAND 零输入冷启动，
99.87 秒到达完整学习桌面。[启动报告](../tmp/np560-lcd-partial-native-boot-20260906-v1/report.json)
最后三次顶栏比较均为 `0 / 5280`，已监控 CPU/ROM 故障为 none、HLE off、NAND ERROR=0。
[原始 LCD](../tmp/np560-lcd-partial-native-boot-20260906-v1/final.png) 已目视核对。
未启用 NAND 保存，底图 SHA-256 仍为
`7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`。
隔离启动进程已正常回收；用户 8807/8808/8809 未重启或替换。
这些结果只证明本次设备行为和默认启动，不证明应用或游戏全部可用。

## 明确保留的缺口

- 合法连续范围以外的 start>end 行为未获本型号依据，目前报告未实现并保留原设置，
  不从其它型号推测环绕窗口。
- 部分显示与完整可变 duty、区域滚动的组合及电气功耗/帧时序仍待实现。
  LI/COM 组合沿既有控制器地址与本机接线推导，没有新增真机测量。
- RMW、EEPROM access 和 EPSRRD1/2 尚未实现；正常状态中相关状态保持 out，
  不能称所有 LCD 寄存器读法已完成。SCM 位可读只说明配置可观察，不表示滚动输出已实现。
- 第 47 页 NSB 的文字定义、表格和图中固定区边界并不一致；第 60 页 bottom/whole
  示例又使用 BB=25，而第 47 页表格列为 39。需要额外的本型号依据或真实操作轨迹才能消歧。
  本轮补查的 [SEACOMP 分发手册](https://www.seacomp.com/sites/default/files/references/Sitronix-ST7529.pdf)
  仍为同一 v1.8，不是第二份独立验证；其它 ST75256 的定义不能直接套用。

因此本轮没有按猜测实现 ASCSET/SCSTART，声音 ROM 与完整 NPE 目标也没有随之完成。
