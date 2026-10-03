# 普通 Y 指针的内部 RAM 访问修正

日期：2026-09-06。修复 CPU 通用内存语义，不代表 NPE 音频 ROM 已恢复。

## 依据与修复前反例

按 PDF 技能目视核对 `tmp/cnpatent/CN1916884A.pdf` 第 128–130、134 页：
图 2 定义内部 Y-RAM 为 `00:8000..BFFF`；图 5 对应 R12/R13/R14 为 Y0/Y1/Y2；
图 9 对 `[Rn]`、`[Rn++]`、`[--Rn]`、`[Rn+immediate16]` 都规定 Y 指针只访问 Y-RAM，
其中后两种绕过 AGU，但不绕过内存空间限制。

旧核心 `ac5f17b0...` 的内存 MAC 已走内部 Y-RAM，普通 `pointer_read/write` 却仍按 DS 译址。
`tmp/np560-y-pointer-before-v1/` 留下确定性反例：guest 在内部 `8500/8502` 放
`1234/5678`，同逻辑地址的 DS1=A0 外部银行放 `ABCD/EF01`。
Y0 直接读、Y1 后增量读、Y2 偏移读均错误取得外部数据；X0 外部读则本应如此。
测试断言失败，隔离 QEMU PID 47863 正常 exit 0，不是崩溃或超时假阳性。

## 实现

`qemu-dmcu/target/dmcu/helper.c`：

- R12..R14 的普通读写统一使用内部 SRAM，保留高字节优先的 byte lane，与 MAC Y 操作数一致。
- MOV、内存 ALU、读改写移位等共用此路径；X/通用指针仍按 DS，FP/SP 仍走内部栈路径。
- 所有参与同一条普通内存指令的 Y 地址在副作用之前检查。
  前减量和立即偏移检查有效地址，不把起始寄存器值误当成实际访问地址。
- 合法的 `C000` 前减量可写 `BFFE`；`7FFE+2` 可读 `8000`；最后一个 byte 可读 `BFFF`。
  真正越过 Y-RAM 的操作显式 unsupported，不能读错银行或先修改指针再停机。

范围外访问的原厂 EXR/异常投递仍未知，显式停机是保留缺口，不是模拟了原厂异常。
Y0/Y1 modifier、可变增量和位反转仍未补齐；本轮没有猜寄存器表或修改这些模式。

## 验证及适用版本

核心 SHA-256：`97094f4ac11498050c7c444ec75339898a905cba6d0ffe4ff64038aa4c58af4e`。

`scripts/tests/test_np560_y_pointer.py` 复用现有短时 QEMU 运行器，验证内部/外部视图分离、
读写、前减量/偏移、byte lane、双指针复制、ALU/移位、Y2 循环和边界停机。
`tmp/np560-y-pointer-v1/report.json` 全部定向场景通过，隔离进程均 exit 0。
所有准备由 guest 指令完成，无 NAND、宿主 RAM 写入或在线实例修改。

`tmp/np560-y-pointer-original-mac-v1/` 中原厂 `0C:7142..71B0` 完整 112 字节函数
仍正确输出 64 个 word；不是宿主替代原厂运算。
`tmp/np560-y-pointer-coldboot-v1/report.json` 的隔离零输入冷启动通过：
100.58 秒结束，连续三次顶栏与原厂资源零像素差异，实际 LCD 保留了学习菜单与时钟；
ROM_MISSING、INVALID_CONTROL、UNSUPPORTED 均为 none，NAND ERROR=0。
这只覆盖冷启动及该顶栏，不代表长时间切换菜单、其它应用或游戏已通过。
输入 ROM SHA-256 为 `a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef`，
NAND 为 `7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`。

没有证据表明此错误是用户旧菜单花屏或当前 `02:ACD8` 停点的原因。
本轮没有重跑游戏入口，没有更换 8807 等用户实例、生产 PRG、ROM 或 NAND。
