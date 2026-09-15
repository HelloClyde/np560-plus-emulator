# X0 循环寻址：原厂音频环形缓冲越界修复

日期：2026-09-06。范围是 CPU 的 X0 后增量循环寻址，不是完整 X/Y AGU、
mask ROM 恢复或游戏声音完成。修复共享寻址机制，没有改原厂函数、NAND 或按调用地址特判。

后续 `ac5f17b0...` 扩展了 X2/Y2 的部分共享寻址及内存 MAC，详见
[内存 MAC](np560_memory_mac.md)。检查器改名为 `instruction_agu_pointer_mask`，
本篇主体保留此前 X0 核心的证据；后续核心完整重跑本篇用例并通过，
记录为 `tmp/np560-memory-mac-x0-v2/`。完整 X/Y 与异常仍未完成。

## 原厂代码与实际反例

原始 `NP560.PRG` 中 VMA03 `28:2E04..2E64` 的写入函数和
`28:2C74..2E02` 的读取函数均保存 `REG[13]`，将它设为 `0600`，
使用 X0（R8）后增量访问环形缓冲，最后恢复寄存器。
这提供了 XM0 对应 `REG[13]` 的原厂代码证据；没有据此猜测其它 modifier 的全部映射。

缓冲为近地址 `1000..15FF`，长度 `0600` bytes。旧核心将 X0 当普通指针递增，
越过 `15FF` 后继续访问 `1600`，而不是回到 `1000`。
`tmp/np560-x0-ring-before-v1/` 用未修改的原厂写入函数复现：

| 观察项 | 修复前实际 | 修复后实际 |
| --- | --- | --- |
| 从 `15FE` 写入 `1122,3344` 后的写指针 | `1602` | `1002` |
| 环尾 word `15FE` | `1122` | `1122` |
| 环首 word `1000` | 仍为哨兵 `BEEF` | `3344` |
| 区外 word `1600` | 被覆写为 `3344` | 保持哨兵 `DEAD` |

这是原厂音频缓冲确实能触发的 CPU 错误；尚无证据证明历史菜单 `22:1840`
代码损坏也由它引起，不能把所有花屏问题一起关闭。

## 架构依据与实现边界

来源：[CN1916884A 原始扫描件](../tmp/cnpatent/CN1916884A.pdf)，已目视核对
PDF 第 134 页图 9/10 的寻址与 AGU 定义、第 131 页图 6 的 byte 寄存器映射，
以及第 128/129 页内存视图。内存 MAC 的第 36–39 页也已核对，但本次未实现它。

- modifier 为零时采用线性递增，其它循环长度以 byte 为单位；`FFFF` 是尚未实现的位反转模式。
- 循环基址按最小容纳长度的 `2^n` 对齐：令 `span` 为不小于 length 的最小二次幂，
  `base = address & ~(span - 1)`，下一地址为
  `base + ((address - base + increment) % length)`，最终截为 16-bit。
- 因而 `length=0600, base=1000` 时，`15FF++ → 1000`。
  不能用整个绝对地址对 `0600` 取模，否则会错误返回 `1200`。
- `[Rn]` / `[Rn++]` 对 X/Y 启用 AGU；`[--Rn]`、`[Rn+immediate]` 绕过 AGU。

实现位于 `qemu-dmcu/target/dmcu/helper.c::pointer_postincrement` 和
`instruction_uses_x0_agu`，XM0 常量在 `target/dmcu/cpu.h`。
已执行的 ALU、MOV、内存移位及 EXP 的相关 X0 后增量共用此机制；
其它寄存器、FP/SP 栈、前减量及立即数偏移保留原有行为。

X0 的 `FFFF` 模式或初始地址位于循环长度之外时，在操作数读写前显式报 unsupported，
不静默退回线性模式。这是保护性的诊断停机，**不是实现了原厂 EXR 异常投递**。

仍缺：X1/X2/Y0/Y1/Y2 modifier 与完整共享 AGU、Y-RAM 访问路由、位反转、
内存 MAC/`.m` 搬移、异常和精确周期/总线竞争。其它指针保持旧行为不等于这些能力已正确模拟。

## 未改写的原厂函数验证

[验证脚本](../scripts/tests/test_np560_x0_ring.py) 复用现有隔离 guest 运行器。
原函数完整字节放在其 VMA03 程序地址；caller 由 guest 自己准备数据、寄存器、参数和栈。
宿主不写运行中的 guest RAM，无 NAND、HLE、原厂解码替代或生产 ROM 修改。

| 原厂函数 | 字节数 | SHA-256 |
| --- | --- | --- |
| `[28:2E04,28:2E66)` 写入 | 98 | `600c25bef9b1525864bfc2eab5959f76913bd9c17f091b2468cc0e1fcdc69541` |
| `[28:2C74,28:2E04)` 读取 | 400 | `4b7fd11e8f8e7532b98a1ec7ab8933d81c56888f4278dc36a4a734588215ee0d` |

写入结果如上表。读取夹具从 `15FF` 取两个 unsigned 8-bit 样本，环尾/环首分别为
`90/A0`，得到 signed 16-bit PCM `1000,2000`，读指针变为 `1001`，剩余 count 为零，
区外 `1600=B0B0` 不变。两个函数均正确恢复 XM0=`0040`、R8=`7777`、SP=`6000`。

`tmp/np560-x0-ring-v4/report.json` 全部通过：两个原厂函数各普通/icount 两种运行，
以及 14 项定向指针边界。后者包括长度 6 的非二次幂循环、byte/word、ALU、复制、
移位、EXP、零长度线性、其它寄存器不受影响、前减量/立即数绕过和显式未支持边界。
全部隔离 QEMU exit 0；次数仅说明覆盖，不折算整机进度。

### 中间构建与夹具错误

- 首次增量编译因诊断参数误写 `word` 而非 `word0` 失败；当时未正确门控后续命令，
  `np560-x0-ring-v1` 实际运行旧 `f989c8fe...`，并非新实现失败。其身份记录保留。
- `v2` 两种原厂写入已正确；读取夹具误期望 `0010,0020`。图 6 和原厂代码表明
  RB0 是 R0 高 byte，RB1 清零，实际转换是 `(sample-128)*256`。
  因此仅修正期望为 `1000,2000`，没有修改原厂函数或 CPU 字节寄存器实现。
- `v3` 移位夹具把 R0 设为 `0001`，但计数来自 RB0，实际 count=0。
  将输入改为 `0100` 才是计数 1；未放宽预期结果或改移位实现。
- 最终 `v4` 使用同一成功编译核心，全部通过；不把上述错误混入最终验收。

## 同核心回归与适用版本

QEMU `E:/qemu-dmcu-build/qemu-system-dmcu`：46,588,464 bytes，SHA-256：
`4e878c3814583ccd4f9f1e3d05839113f9a458bdf50ec728cbd14a553167a540`。
旧核心保留为 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-x0-ring-20260906`，SHA-256：
`f989c8fe9ea85fc33ad07e6134d9fd7e2d82abca02442e92699bccc2daf20421`。

生产输入未修改：

- PRG：`d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`。
- 严格缺口 ROM `tmp/np560-system-v380-vma03-resident-codec-holes-v1.bin`：
  `a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef`。
- NAND `E:/qemu-dmcu-build/np560-vendor-file-import-v3.nand`：
  `7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`。

同一核心结果：

- `tmp/np560-x0-cold-boot-v1/report.json`：严格 ROM、HLE off、零按键冷启动
  100.96 秒通过；最后三次顶栏差异 0/5280，无 ROM_MISSING/UNSUPPORTED/
  INVALID_CONTROL，NAND ERROR=0。已目视 final.png 为清晰学习桌面。
- `tmp/np560-x0-audio-v1/`：原厂 `08:33FA` 普通/icount 渐变、静音、暂停和
  活动采样复位通过。两路 DAC 各写 7 次，(3,-3) 分别采到 963/960 帧。
  WAV 是数字输出诊断，不是原厂游戏/音乐内容。
- `tmp/np560-x0-original-gain-v1/report.json`：仅重跑原厂 `08:34C4` 第七档
  signed 样本场景并通过；完整 31 项 DSP 套件仍是此前 `f989c8fe...` 的记录。

本次没有重跑已知同一 ROM 缺口的 NPE 导航。最近一次实际游戏选择仍是此前核心在
`25:DFBA → 02:ACD8` 停止，详见 [流后端](np560_resident_stream_backend.md)。
**ACD8、AD92 及 B6DE/B7AA/B816/B84E 未恢复，播放器与 NPE 声音仍未完成。**
环形缓冲成功不等于解码成功，冷启动不等于跨菜单/完整游戏通过。

本轮隔离实例已退出，未保存 NAND，也没有重启或替换用户 8807/8808/8809。
下一步按 [整机计划](plan.md) 推进有原厂证据的共同依赖，并继续寻找缺失 ROM 服务的真实契约。
