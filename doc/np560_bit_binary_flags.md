# BAND / BOR / BXOR / BCMP：双输入位状态旗标修复

日期：2026-09-06。修复通用 CPU 运算语义；未修改原厂 PRG、guest ROM、NAND 或前端画面。
不是声音解码恢复，也未证明它是此前用户菜单故障的原因。

## 原始依据

按 PDF 技能逐页目视核对 [CN1916884A 原始扫描件](../tmp/cnpatent/CN1916884A.pdf)
PDF 第 71、73、76、78 页（说明书第 68、70、73、75 页），对应 BAND、BCMP、BOR、BXOR。
四页一致规定，旗标根据**两个运算前的输入位**产生，与该指令最终存回的结果不同：

- Z = NOR，C = AND，N = XOR，V = OR。
- BCMP 只更新旗标，不写操作数；不是一次普通的 1-bit 减法。
- BAND、BOR、BXOR 分别将 AND、OR、XOR 结果写到目标位。

| 目标原位 | 来源原位 | Z | V | C | N | PSR 低四位 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 1 | 0 | 0 | 0 | 1 |
| 0 | 1 | 0 | 1 | 0 | 1 | A |
| 1 | 0 | 0 | 1 | 0 | 1 | A |
| 1 | 1 | 0 | 1 | 1 | 0 | 6 |

上述是原始指令表依据，不是与真机逐周期比较。BMOV/BMOVN 的“先前状态特定位”说明及其它
尚有歧义的指令不因本次四页结论而顺带重定义；BSET/BCLR 也未改。

## 修复前的反例

旧核心 SHA-256：`cc8a5518bd7e62fc656bd0410c58e7542f3a1890a8f85c95d2c1115984ae00d2`。
此前三种逻辑位指令复用了普通逻辑结果的旗标，BCMP 复用了减法旗标。
guest 自己准备 R0/R1 和 PSR，再将实际结果存入 RAM，宿主只读：

| 输入与操作 | 旧 PSR 低四位 | 原表要求 |
| --- | --- | --- |
| BAND 0,1 | 1 | A |
| BAND 1,1 | 8 | 6 |
| BXOR 1,1 | 1 | 6 |
| BCMP 0,1 | E | A |
| BCMP 1,1 | 1 | 6 |

`tmp/np560-bit-binary-flags-before-20260906-v1/` 保留实际 16 组输入的旗标、目标字和来源字，
断言失败而 QEMU PID 80408 正常退出 0；不是超时、返回地址损坏或执行数据产生的假象。

## 实现

`qemu-dmcu/target/dmcu/helper.c::bit_binary_flags` 统一实现上面的四输入组合，
`exec_bit` 的 BAND/BOR/BXOR/BCMP 调用它。两输入在更新旗标或目标之前读取；
其它 PSR 位保留，BCMP 不做写入。

显式目标为 PSR 位时仍保持已有的“普通旗标更新后，显式写目标位”次序，与现有 bit ABI 一致。
这项别名检查用于避免破坏现有契约，不单独宣称已经取得所有 PSR 别名时序的真机证据。
没有依据调用地址、菜单状态或内容名称加入特殊分支。

## 原厂代码交叉证据与验证范围

原厂 `USB_Loader_Noah.bin` 的字节 PC `00:1178/1180/1188/1194/129E/176C`
包含 BAND 自身位测试；`BURN_NAND_FLASH_CODE.bin` 的 `51:7BD0` 为
`BCMP BIT[71].0, BIT[73].0`，随后 `51:7BD6` 根据 N 决定分支。这些是有效代码，
不是仅凭全包内匹配两字节 opcode 得出的函数归属。

本次重用已有隔离运行器，新增 `scripts/test_np560_bit_binary_flags.py`：

- 按原表的字面常量检查四种指令、全部双位输入；同时核对目标之外的位、来源字和其它 PSR 位不变。
- 检查同一位同时作为源/目标、PSR 作为源及显式目标的既有次序。
- 执行原厂 burner 中 `51:7BD0..7BD8` 的 **10-byte 未改指令片段**与原分支目标，
  仅在片段之外添加诊断返回。原文件字节为大端，按指令字装入 guest 的代码视图。
  这不是完整烧录函数或真实 USB 会话；该片段仅消费 N，不能单靠它证明所有旗标改动。
- 普通运行与 `icount=5` 均通过。输入由 guest 指令准备，无 NAND、HLE 或宿主 RAM 注入。

原 burner 文件 SHA-256：`efec500f345b1dee11dd4aef95cc555a002e47943241176cde2ba6447c3b7cc0`；
10-byte 原片段 SHA-256：`6e06c8a81b24393bb4ef9f97eff251e9e64cff03cd47b4813dd3b14cc7831f39`。
结果在 `tmp/np560-bit-binary-flags-20260906-v1/report.json`，所有 owned QEMU 均退出 0。

## 同核心系统检查与保留边界

新核心：`E:/qemu-dmcu-build/qemu-system-dmcu`，46,642,800 bytes，SHA-256
`aae9a25fa3ee8b901edf22d9efd22cc8ddf17eb997a2c43e3bfc989399e0db97`。
旧核心保留在 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-bit-binary-flags-20260906`。

`tmp/np560-bit-binary-flags-coldboot-20260906-v1/report.json`：严格 ROM、HLE 关闭、
零按键、无 NAND 保存的冷启动在 95.48 秒结束；末尾连续三帧与原包学习顶栏零像素差异。
已目视实际 LCD 为完整学习桌面，ROM_MISSING/UNSUPPORTED/INVALID_CONTROL 均无错误，
NAND ERROR=0。QEMU PID 80436 已回收，returncode=0；生命周期记录的旧 phase=starting
不代表进程仍存活。仅证明这次启动/顶栏，不代表全部菜单、应用或 NPE 已通过。

PRG `d555609e…`、严格缺口 ROM `a243f8ba…`、NAND `7783876b…` 与此前保持一致，
完整路径与指纹在报告中；没有重启用户 8807/8808/8809，也没有生成新 NAND 副本。

相邻位寻址回归另暴露旧 Timer2 测试的结束 PC 硬编码过时：caller 已有 17 个 word，
末尾自循环地址应为 `20:0020`，检查却仍要求 `20:001C`。新旧核心均到 `0020`、R4=600D，
确认不是本轮指令回归。检查改为从 caller 长度计算确切结束地址，没有改等待函数、缩减计数或放宽断言。
修正后的完整位寻址回归已通过；原厂 `08:47A4` 等待函数经真实 Timer2 中断返回，
倒计数为 0、SP 恢复，Timer2 `EXPIRED=3`，控制/预装载/ICR 均清零；外层命令退出 0。

当前声音仍缺 `02:ACD8/AD92` 与 `01:B6DE/B7AA/B816/B84E` 等服务。
CPU 位旗标正确不等于这些 ROM 算法已恢复，整机目标保持未完成。
