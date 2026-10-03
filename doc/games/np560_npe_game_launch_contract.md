# NP560+ NPE 游戏浏览与启动链契约

更新日期：2026-08-30

## 结论

V3.80 固件中的“游戏世界”不是 `.nwf` 浏览器。原厂 resident 操作表明确把它绑定到：

- 目录：`0:\应用程序`
- 过滤器：`\*.npe`
- 应用代码：`0x0078`
- 通用文件浏览器：`1B:23B8`

同一操作表中的另一项“动漫欣赏”才绑定 `0:\动漫欣赏` 和 `\*.nwf`。因此目前只能确认
NPE 与 NWF 是两条不同的列表入口；NPE 文件是否内嵌、引用或最终调用 NEPLAYER/NWF，
必须等待真实 `.npe` 样本的静态结构和 guest 动态调用链证据，不能预先视为同一格式。

## 原厂表和 dispatcher

操作表从升级固件源 `4D:0B0C` 装载到 resident runtime `30:0B0C`，共有 20 条、每条
14 字节。相关两条记录为：

| 操作索引 | runtime 记录 | 目录字符串 | 过滤器 | 用途 |
| --- | --- | --- | --- | --- |
| 0 | `30:0B0C` | `27:E1F6` → `0:\动漫欣赏` | `27:E1EE` → `\*.nwf` | 动漫欣赏 |
| 1 | `30:0B1A` | `27:E1E0` → `0:\应用程序` | `27:E1D8` → `\*.npe` | 游戏世界 |

两个记录的辅助字符串都指向 `27:E1EC` 的空串。字符串池的原厂源区是
`44:E07E`，runtime 数据视图是 `27:E07E`。

应用目录中“游戏世界”的应用代码为 `0x0078`。dispatcher 源 `3F:3C2A`、runtime
`22:3C2A` 对 `0x79` 和 `0x78` 分流：

- `0x79` → `33:3CE6`（源 `50:3CE6`）→ 操作索引 0；
- `0x78` → `33:3DA6`（源 `50:3DA6`）→ 操作索引 1。

两个 wrapper 都进入通用浏览器 `1B:23B8`（源 `38:23B8`），差别是传入的操作索引。

## 选中文件后的首段启动链

通用浏览器收到确认事件后使用所选 descriptor，并在源 `38:2A88`、runtime
`1B:2A88` 把它交给应用启动序列 `2E:D34A`（源 `4B:D34A`）。已确认的第一段调用为：

```text
1B:23B8 通用浏览器
  → 1B:2A88 selected descriptor handoff
  → 2E:D34A application launch sequence
      → 30:C370 file-state constructor
      → 30:C99E guest file wrapper
      → 18:21F4 application launch manager
```

这证明选中的 `.npe` 文件 descriptor 会走 guest 原厂文件和 application manager 路径，
而不是由 Web 或 QEMU 宿主直接启动。但以下内容仍未恢复：

- NPE 文件头、版本、元数据和完整容器布局；
- 文件验证、解压/解密、重定位与入口 ABI；
- NPE 是原生 DMCU 代码、字节码，还是调用另一个运行时；
- NPE 与现有 NEPLAYER/NWF 子系统是否有关联；
- 游戏退出、存档、音频和定时器服务契约。

## 已取得的真实格式样本

本机 `D:\Downloads\NP560plus游戏全集` 中现有 18 个 `.npe` 文件。逐文件读取已确认它们
开头 12 字节都是 ASCII `NP560 RPG2.1`，因此已经具备反推真实 NPE 容器和动态装载链的
输入，不再把仓库中的合成 `.nwf` 当成替代品。

首个端到端目标固定为体积最小的 `英雄传奇.npe`：

- 大小：2,053,994 字节；
- SHA-256：`ADEA7C7442CEFAEA1C21AB7442CDD10D7796E7FC1DD3A5B98FD3C1C61DFA8C19`；
- 已确认信息：12 字节魔数/版本和紧随其后的 GBK 标题；
- 尚未确认：字段边界、段表、校验、压缩/加密、重定位、入口 ABI 和运行时类型。

这些样本已有稳定字节身份，可用于本机逆向与回归；仍需补记其原始下载页或归档来源，
才能完成公开可复现的内容来源审计。

## 当前动态阻塞

### v752 当前权威边界（2026-08-30）

v752 已关闭 v751 的 `2F:B6DA → 1B:7A20` 未物化边界。恢复项是 exact
`1B:7A20 ← 38:7A20+0x0876`；source 由 721 条可达指令完整覆盖，43 个直接 SCALL，
`LINK #0x21` 与 `38:8284..8294` 的平衡 epilogue 闭合，下一函数从 `38:8296 LINK #3`
开始。构建时只改三个已经证明目标冲突的 SCALL segment word：

```text
1B:7AA2  33:380A → 5F:380A  （exact 50:380A+0x22，Hero 必经）
1B:7E8A  30:6A9C → 5F:6A9C  （exact 4D:6A9C+0x102，旧格式分支）
1B:7EA2  33:1BBA → 5F:1BBA  （复用既有 exact relocation）
```

补丁后主函数 SHA-256 为
`D955C238BBC6082DB9AD075442D2EE89A76B70A246387BFBC6D5E922C5192AA7`；两个新 5F helper
由现有最终 guest installer 用构建时校验的 immutable words 写入 coherent code/data
backing。没有 HLE、宿主返回值、RAM/list/显存状态补丁、Web 游戏逻辑或新 CPU 指令。

隔离端口 8796 的 v752 干净重放中，五个真实矩阵事件
`M55/B0 → M53/86 → M37/83 → M53/86 → M53/86` 全部完成 map、guest consumer
acknowledgement 和 release；第五键由 modal consumer 接收。最终 `APPLICATION_STATE=0078`，
`ROM_MISSING/UNSUPPORTED/INVALID_CONTROL` 均为 none。原生 LCD 已显示唯一
`英雄传奇.npe` item；证据位于 `tmp/np560-v752-hero-select-route/`。这证明新的 resident
函数没有 trap、非法控制流或返回栈破坏，但还不能把第五键成功等同于游戏启动。

静态审计同时确定 `53:0020/0024/0028` 不是缺失的 resident ROM 服务。它们只在旧
`NP560 Ver1.0`/`NP580 Ver1.0` payload 被读入 segment 53 后作为运行时入口使用；真实 Hero
头部 `NP560 RPG2.1` 的第三次 9 字节 `memcmp("NP560 RPG", header, 9)` 应返回 0，使
`1B:7BAE` 设置 `R0=2`，随后：

```text
1B:8294 → 2F:B6DE
2F:B716  匹配 status 2
2F:B726 → 1F:D1A6
```

Hero 正常路径不应命中 `53:0020/24/28`、`1B:7E8A` 或 `1B:7EA2`。严格只读、有界的
`NPE_FORMAT_DISPATCH` 观察器现已加入，并在重建 QEMU 后用同一五键路径取得：

```text
ENTRY=1
1B:7AA2 → 5F:380A → 1B:7AA6 = 1/1, R0=001F
memcmp returns = FFFD, FFF3, FFA2
STATUS_7BAE = 0
1B:8294 → 2F:B6DE, R0=0000
2F:B726 → 1F:D1A6 = 0
LEGACY_53 = 0/0/0, LEGACY_1B = 0/0
```

因此静态预期的第三次相等在当前运行中并未发生；dispatcher 正常返回 0，随后回桌面。
后续实参观察已经把边界进一步闭合：三次左侧都是同一个真实 Hero header，开头为
`NP560 RPG2.1`；右侧分别是 `32:496E`/12、`32:4960`/12、`32:4956`/9，当前却读取到
flat bank 32 的指令字节。精确、最小、连续的原厂常量源是 `4F:4956..497B`：

```text
NP560 RPG\0NP580 Ver1.0\0\0NP560 Ver1.0\0\0
```

`4F:4954` 属于前一个字符串，`4F:497C` 已进入下一个字符串，所以 `+0x26` 边界完整。
实参证据为 `tmp/np560-v752-format-args-route/post-route-diagnostics.txt`，SHA-256
`0DB8BB6A68AFD15C6A311EF786E37A361A59B82D3298A532C481948D58CCE366`。

### 永久 source alias 已否决；v755 已恢复真实 data RAM 生命周期

实验 v753 曾将上述 source 做成 `32:4956+0x26` 的永久只读 Harvard data alias。静态字节、
manifest、builder/QEMU 映射和 59 项 overlay-map 测试均通过，但同一 v752 ROM 内容在隔离
端口 8796 冷启动时无法进入桌面：root state 在 `00FD` 循环，`ROOT_OBJECT_FAIL` 增长到
12，NAND reads 超过 110 万；健康 v752 对照为 root fail 0、约 19.7 万 reads。两份 ROM
二进制完全相同，因此当时将该回归与 alias 关联，但尚不足以证明唯一因果。

随后用已撤销 alias 的 QEMU 和相同 ROM/NAND 重试，仍进入相同 `00FD` root loop；在失败前
新增观察器明确给出 `NPE_LITERAL_DATA=READS:0 WRITES:0`。所以现有证据没有证明启动期
guest 会访问、写入或复用这 0x26 字节，也不能再把 root loop 归因于“只读 alias 吞写”。
该冷启动稳定性是独立边界，需用可重复 icount/多次 A/B 继续定位。

固定 source alias 仍不作为最终实现，因为它从复位起绕过了应用的 guest 装载生命周期。
builder 只保留 source/destination/size 证据，不把它声明为已实现 overlay。

QEMU 增加了 `NPE_LITERAL_DATA` 只读生命周期观察器：分别计数并保留该窗口最早 32 次
读和 32 次写，记录 PC、physical/logical 地址、值、位宽、DS0/DS1 以及是否处于
`1B:7A20` dispatch。它不改变返回值、写值、寄存器或控制流。当前 guest-side 设计固定为：
给 `32:4956+0x26` 提供与 code view 分离的普通可写 data backing，初始仍保留 flat 数据；
只把 `1B:7B26` 的第一次 memcmp SCALL 改到 resident wrapper。wrapper 通过现有 far-copy
把 `4F:4956+0x26` 写入目标，再保持原六参数与返回栈、尾跳真实 `2C:C07E`。只有 status-2
自然出现才继续下游。

v754 首次动态运行证明 wrapper、`08:43A6` 的 ABI、source、destination 和 byte lane 都正确，
但 38 次写入只在总线观察器中出现，随后读取仍返回旧 flat 字节。原因不是 ROM 函数缺失，
而是宽泛的只读 `program-nor` data alias 覆盖了底层 RAM，吞掉了
`32:4956..497B` 的 guest 写入。v755 为这 0x26 字节增加独立、仅 data view 可写的有界
Harvard RAM 窗口；code view 仍是 flat PRG，没有 source alias、上电 seed、HLE 或强制返回。

同一五键路径的 v755/v756 动态结果已经关闭该边界：

```text
ENTRY=1
LITERAL_WRAP=1/1/1/1
NPE_LITERAL_DATA READS=14 WRITES=38
memcmp returns=FFFC/FFFE/0000
STATUS_7BAE=1, R0=0002
1B:8294 → 2F:B6DE, R0=0002
2F:B726 → 1F:D1A6=1
ROM_MISSING=none, ROOT_OBJECT_FAIL=0
```

因此“第三次比较/status-2”不再是待验证假设；当前工作只继续其后的真实 loader/runtime。

### status-2 后的已排序闭包

`1F:D1A6 ← 3C:D1A6+0x05CE` 本体已逐字节 exact，509 条可达指令、43 calls、0 unknown/
conflict。status-2 出现后的第一处真正冲突不是它本身，而是：

```text
1F:D1CA → 03:4128 → 32:F38A
```

v756 已把 ROM03 跳表中的这个目标精确重定向到 `5F:F38A`，并由最终 ROM01 guest
installer 写入 exact `4F:F38A+0x003C`；动态控制流为
`1F:D1CA → 03:4128 → 5F:F38A → 1F:D1CE`，旧的
`32:F400 → 10:D019 → 10:E58D/AAAC` 异常链已经消失。当前首个错误随后出现在
`1F:D210 → 32:CEEE` 内部：`32:CF7C RETS → 1F:4D59`。下一步需以完整 source/caller
证据恢复这一闭包，随后按动态可达顺序处理 resident `14:E742 ← 31:E742+0x0FC6`、复用
现有 relocated `5F:C1A6`、`24:ACBA`、`31:71D2`，再进入 operation 7
并处理 `2B:0DA2`。Hero 在 `14:E742` 必须走 file handle 非零和 version byte
`0x31 != 0x30` 两个非零分支；真正错误状态是 `52:7A3C`，不是 R0 返回值。

在 lifecycle-bound 常量安装、status-2、上述 loader 闭包和真实首帧全部完成前，仍不能称
NPE 已启动、可交互或可玩。

当前 v756 ROM 为 `tmp/np560-system-v380-current-v756.bin`，SHA-256
`34B9F1D6695694FDE57802FDF2E8E1BEA5A8174B0B408DD0886430341702E6BE`；manifest SHA-256
`634C1D3BAD1B22B87A1FB1D16980C80ECDB839FA947215185DA2172E179A53F2`；QEMU SHA-256
`77F0DA5D910D9F679E4D34DD213ADFDB0FE73F34359098E46492C8A08250C8F7`。overlay map 为
builder 588、QEMU 706、missing 0、non-identical overlap 0，late overlay count 633。

### v751 历史边界（已被 v752 推进）

v748 报告的 `1B:0154/WORD=3F7E` 不是缺失 CPU 指令。控制流回溯确认真正错误是
`1B:299A/C600 RET → 1B:0000`：`1B:23B8` operation controller 的 19 项近跳表
`1B:299C..29C1` 没有 Harvard data view。v749 给这 0x26 字节增加只读 SoC-ROM data
alias 后，第五键动态变为正确的 `1B:299A → 1B:29C2 → 1B:29D2 → 2F:B644`。
专利指令表、Python decoder 和 QEMU executor 的交叉审计均表明 `3F7E` 不是合法 DMCU
指令，因此未增加任何 ISA 特例。

v749 的下一首因是 `2F:B6AA → 23:70E0` 落在 flat 资源数据，最终报
`23:70FA/WORD=BE00`。原厂 source `40:70E0..7583` 是独立完整的 `LINK #9` 函数：
大小 `0x04A4`、412 条可达指令、32 个 calls、0 个 unknown/overlap，并在
`40:757E MOV R1,[R15++] → 40:7580 UNLINK → 40:7582 RETS` 闭合；下一函数从
`40:7584 LINK #8` 开始。v750 把它加入 ROM-01 最终 modal closure 的普通 guest
byte-copy，并为 `23:70E0+0x04A4` 提供 coherent writable code/data backing；没有改
`2F:B6AA` call site、ISA、HLE、host/RAM 状态或 Web。

干净 v750 五键重放取得以下新证据：

```text
1B:299A RET → 1B:29C2
1B:29D2 → 2F:B644
2F:B6AA → 23:70E0
23:7582 RETS → 2F:B6AE
```

旧 `1B:0154/3F7E` 和 `23:70FA/BE00` 都没有复现，且
`ROM_MISSING/UNSUPPORTED/INVALID_CONTROL` 均为 none。前四个矩阵事件继续完成 map、
foreground acknowledgement 和 release；第五个 `M53/0x86` 也已被 modal consumer
接收。随后曾观测到 operation-7 UI 初始化在 `2A:D840 → 31:4200` 不能返回：caller 从
所谓对象 `+0x0F` 读取 `0xFF` 作为 inclusive 上界，exact `31:4200` 以 8 位计数逐项
调用 `1D:7C00`，到 `0xFF` 后计数回卷为 0。

继续向上回溯已经证明该 `0xFF` 不是合法对象字段，也没有应修的 producer。真实首个错误
依赖是 `23:7100 → 30:2966`：当前目标从中段 `MOV R6,R0` 开始、没有 `LINK`，随后误走
`30:2A2C → 2A:CA24`，借用上层 FP，并最终把 `[FP+6/+8]=02:4D58` 拼成伪 far pointer。
same-PC source `4D:2966..2A77` 则是完整的 `LINK #5 ... UNLINK/RETS` 函数，严格
`0x0112` 字节，只调用已经 exact 的 `33:269E`、`25:206E`、`33:1A02`、`33:4342`；
它不调用 `2A:CA24`、不读取 `+0x0F`，也不进入 `31:4200`。递归 manifest overlap
审计确认目标 `[30:2966,30:2A78)` 当时无恢复项和冲突。v751 已只在已证明的最终
ROM-01/application 生命周期恢复 exact `30:2966 ← 4D:2966+0x0112`：由于 source 4D
在该时刻可变，installer 使用构建时校验并嵌入的 immutable PRG words，同时给目标增加
coherent writable code/data backing；没有修改对象字段、循环、CPU ISA、HLE 或 Web。

干净无并发的 v751 五键重放已经动态证明新函数按原厂路径闭合：

```text
23:7100 → 30:2966
30:2986 → 33:269E
30:2A3C → 25:206E
30:2A4A → 33:1A02
30:2A5E → 33:4342
30:2A76 RETS → 23:7104
```

同一保存快照中，旧错误路径 `30:2A2C`、`2A:CA24`、`2A:D82E`、`31:4200` 的全文
命中数均为 0。因此 v751 已越过 v750 的错误栈帧和 8 位回卷循环。第五键之后又推进到
`2F:B6DA`，其 `BD1B 7A20` 是正常的 far call，但目标 `1B:7A20` 尚未物化：v751 ROM
该处是连续 `0F00`（`TRAP #0`），trap/IRQ 返回不断把 PC 向后推进，才最终表现为
`1B:85xx`。same-PC source `38:7A20` 从 `LINK #0x21` 开始，在 `38:8284..8294`
平衡 `UNLINK/RETS`，严格首函数范围为 `0x0876` 字节；`38:8296 LINK #3` 已是下一函数。
builder、manifest 和 QEMU 当前均无 `1B:7A20 ← 38:7A20`。下一步先验证这 0x876 字节
producer 的最终装载生命周期与 overlay 冲突，再决定最小 exact 恢复；尚未命中 loader，
不能称游戏已启动或可玩。

v751 ROM 为 `tmp/np560-system-v380-current-v751.bin`，SHA-256
`C6E21B8D1BDB0E21B6BF0CB530FD6D7AA9DE82E7B87E6ABD953739DCBB14B38A`；manifest SHA-256
为 `1D2C0ACE0ECCC7555C2DAE36A0A1879CA69E8F7363E3006D7372E726A8436DE7`；动态证据在
`tmp/np560-v751-hero-select-route-clean/05-SelectHero-failed.json`。
QEMU 为 45,294,904 字节，SHA-256
`9BEEE5EF34D7B6644967E90504C3A04F8B6AF8FB0C29FE3AE3FE2A321B63AB1E`。本轮定向
standalone/overlay-map 64 项和 builder 7 项共 71 项通过，`py_compile` 与两个仓库的
`diff --check` 通过；258 项全量第二次干净运行尚未完成，不能写成全量回归已通过。

因此 v751 虽然已经完整执行并返回 operation action body 及 mode predicate，仍没有命中
selected descriptor handoff `1B:2A88`，也没有进入
`2E:D34A → 30:C370/30:C99E → 18:21F4` loader 首链。旧 v750 ROM
`tmp/np560-system-v380-current-v750.bin` 及 `tmp/np560-v750-hero-select-route/` 仅作为
历史对照；v751 的最新证据仍不等于 NPE 已启动、可交互或可玩。

### v748 历史边界（已被 v749/v750 推进）

v748 保留 v747 已证明的唯一 Hero item materialization，并修正当前 canonical ROM 中
第五个确认事件的 overlay 时序。exact decoder 为 `2F:C216 ← 4C:C216+0x012C`；其中
源 `4C:C304` 的原始 `SCALL 2C:D350` 在整段 decoder 内只有这一处。v748 不在冷启动
阶段预装共享的 `2C:D350`，而是在所有 registry/callback/LCD 广域发布之后的 ROM-01
最终 guest 边界，把 runtime `2F:C304` 改为 `SCALL 06:4B00`。resident wrapper
`06:4B00` 是普通 DMCU guest code：只有事件真正命中时，它才写入完整 exact
`2C:D350 ← 49:D350+0x01E0` event-state 闭包并尾跳 `2C:D350`；没有新增 QEMU HLE、
宿主返回值、RAM 状态修补或 Web 菜单逻辑。

在 `tmp/np560-v748-hero-select-route/` 的干净五键重放中，前四个真实矩阵边沿仍自然进入
Game World，第五个 `M53/0x86` SelectHero 确认事件也由 modal consumer 接收。
`NPE_CONTROL_TRACE` 给出完整返回链：

```text
1E:FD7A → 2F:C23A
2F:C304 → 06:4B00
06:5288 → 2C:D350
2C:D52E → 2F:C308
2F:C340 → 11:17F2
```

结果为 `TYPE=0001`、`CODE=0086`、`RESULT=0001`，且 event-state 回调已经正常返回到
decoder，再由 decoder 正常返回其 caller。overlay 审计为 builder 583、QEMU 700、
missing 0、non-identical overlap 0；v748 ROM SHA-256 为
`63CE8669280AD8C8E3680B09262C680DECC7054F32FD2B5172B4FD8C97CAE222`。

但同一次 SelectHero 尝试随后仍在 `1B:0154` 首次报告
`UNSUPPORTED=1B:0154 WORD=3F7E`，当时 `SP=FFE0`，route 记录的首次计数为 17，前一控制流
是 `1B:0152 → 1B:0154`。本次没有命中 selected descriptor handoff `1B:2A88`，也没有
命中 `2E:D34A → 30:C370/30:C99E → 18:21F4` loader 首链。因此 v748 只能证明 Hero
选择确认事件及其 event-state 回调已经被 guest 正常消费并返回；它尚未把 Hero descriptor
交给 loader，不能宣称 `.NPE` 已启动，更不能宣称游戏可交互或可玩。当前最近边界固定为
解释并恢复 `1B:0154/WORD=3F7E` 的真实 DMCU 行为，或以控制流证据证明此前仍有错误；
禁止为了越过它而固定返回成功、直接跳 loader 或制造游戏画面。

### v747 历史边界（已被 v748 推进）

v746 的只读 `NPE_MATERIALIZE` 追踪纠正了 v745 对唯一 `..` item 的解释。目录枚举器
实际上已经取得 `英雄传奇.NPE`，但该记录在 `27:CBE4` 被过滤为 0；与此同时，缺失的
`31:5246` 会吞掉 `27:CBE4` 的 frame，并出现 `31:53B8 → 29:98C2` 异常返回，所以旧
列表中的 `..` 不是可信的最终 materialization。same-PC 静态证明得到完整 exact 闭包：

- `31:5246 ← 4E:5246`，大小 `0x00BA`，负责该操作上下文中的不区分大小写处理；
- `33:430A ← 50:430A`，大小 `0x001C`，ASCII 大写字母判定；
- `33:45A2 ← 50:45A2`，大小 `0x001A`，ASCII 转小写。

把上述共享目标在 ROM01 阶段直接安装会使冷启动停在 `1E:D7AE`、application state 为
`0x0000`，因此这个过早安装方案已经否决。v747 改为 resident `06:6A10` guest lazy
wrapper：只修补操作 1 的原始调用点 `33:3DB8`，首次进入“游戏世界”浏览器时由 guest
安装 exact casefold 闭包，再尾跳原始 `1B:23B8`。新窗口均为 coherent guest-writable
code/data backing；没有 HLE 返回、宿主 RAM/list patch、Web 补画或伪造筛选结果。这样
冷启动桌面保持 `APPLICATION_STATE=00FF`。

随后在同一次干净运行中只输入四个真实矩阵边沿
`M55/0xB0 → M53/0x86 → M37/0x83 → M53/0x86`，每步都有 foreground acknowledgement
和 release，guest 自然进入 `APPLICATION_STATE=0078`。v747 trace 确认：

- 枚举路径为 `0:\应用程序\*.npe`，过滤模式为 `*.npe`；
- 三个候选的过滤结果依次为 `0/0/1`；
- `英雄传奇.NPE` 的过滤返回值为 1，contribute 返回值也为 1；
- 最终 item count 为 1，且该唯一计数的身份已经证明是 Hero，不是 `..`；
- 没有 `filter-bypass`。

可重复证据位于 `tmp/np560-v747-hero-four-key-route/`。overlay 审计为 builder 582、
QEMU 700、missing 0、non-identical overlap 0，`NP560_LATE_OVERLAY_COUNT=627`。旧
`NPE_BROWSER_LAYOUT CALLS=0` 仍只是过时监控窗口，不能推翻新的 filter/contribute/count
证据。

v747 当时只可宣称“唯一 Hero item 已由 guest 正确 materialize”。v748 已进一步证明
SelectHero 的 event-state 回调正常返回，但仍未命中 descriptor handoff 或 NPE loader；
因此同样不能宣称 `英雄传奇.NPE` 已启动或可玩。

### v745 历史边界（已被 v746/v747/v748 推进）

v745 在干净冷启动中只用真实矩阵边沿完成
`M55/0xB0 → M53/0x86 → M37/0x83 → M53/0x86`，四键均有 map、foreground
acknowledgement 和 release，application state 自然到 `0x0078`，且
`ROM_MISSING/UNSUPPORTED/INVALID_CONTROL` 均为 none。renderer 为 call/return 1/1、
layout 2、helper 1；guest front/back buffer 一致地产生原生文件浏览器边框、内容区和右侧
滚动条，证明 Web、LCD 呈现和浏览器外壳不是当前首因。

本轮补齐了 exact `22:147A ← 3F:147A+0x51A` item renderer callback，以及其已证明的
两个直接闭包 `2E:0192 ← 4B:0192+0x192`、`32:F0E0 ← 4F:F0E0+0x3E`。对象字段仍为
`+0x1E=22:147A`、`+0x22=28:DDA6`；`22:147A` 从 `1D:87AA` 命中一次并正常返回，
`23:147A` 从未命中。`NPE_OPERATION_CALLBACKS ACTIVE=1` 只是外层浏览器事件循环仍在
`1B:2748 → 11:1752` 等待下一事件，不代表 callback 卡死；高频 `28:DDA6` 是正常输入轮询。

v745 画面内容只有 `..` 的两个 `0x2E` glyph，仍没有 `英雄传奇.NPE`。`1D:831E` 是先从
对象读取 item count/stride、再逐项调用 `22:147A` 的通用 list renderer；因此“一次 callback、
一个 `..` item”当时表明列表在进入 renderer 前只 materialize 了一项。v745 的下一首因
边界因此固定为“目录 record decode/filter → item 数组与计数 → `1D:831E`”，而不是
callback 内部、按键、Web 或 LCD。旧的 `NPE_BROWSER_LAYOUT CALLS=0` 只监控早期
segment-2C 到 `1C:D462` 的路径；当前 exact `2C:8744` frame/layout helper 不经过该
调用，所以该计数不再是缺失入口证据。

对应可重复证据位于 `tmp/np560-v745-hero-four-key-route/`；overlay 审计为 builder 578、
QEMU 696（code 674、data-only 22）、missing 0、non-identical overlap 0。当前仍不得声称
NPE 列表已形成、文件已选择或游戏已启动。

以下 v695–v743 条目保留为历史取证；若其即时判断与上面的 v747 边界冲突，以 v747 和
自动测试为准。

v695 已在同一次未重启运行中通过真实矩阵依次输入
`M55/0xB0 → M53/0x86 → M37/0x83 → M53/0x86`。四步均完成 map、guest consumer
acknowledgement 和 release，随后 guest 显示
`无此目录:0:\应用程序,请创建!`。为把逆向继续推进到读取后的链路，现有
`tmp/np560-v695-hero-fat16-diagnostic-v2.nand` 作为可丢弃的诊断桥，在 cluster 5 建立
该目录并把 `英雄传奇.NPE` 放入 cluster 6..256。文件逐字节读回、SHA-256 和全部页 ECC
均匹配；它不代表已经完成原厂 USB/文件 API 导入。

guest 已完整读取物理页 `0x1004B`，CPU 可见页缓冲中存在 `.`、`..`、
`英雄传奇.NPE` 三个正确目录项。因此旧的“文件系统内容不存在”阻塞已越过。随后发现并按
原厂 PRG 精确恢复两个 resident 边界：

- v696：`02:0FB6 ← 3F:0FB6`，`0x04C4` 字节，445 条可达指令、23 个调用、0 个未知前沿；
- v697：`1C:D462 ← 39:D462`，`0x078E` 字节，787 条可达指令、14 个调用、0 个未知前沿。

v697 在隔离实例中重新完成四键路径后为 `ROM_MISSING=none`，证明两个补入范围都沿真实
guest 路径执行。但文件列表仍未正确 materialize：娱乐子菜单背景保留，底部出现异常文本；
额外 Enter 已由 modal consumer 接收，随后画面清白，而 selected descriptor/file-open
启动链没有开始。当前最近阻塞因此是 `1C:D462` 返回后的对象字段、list-item attach、modal
repaint/teardown 生命周期，而不是目录内容、矩阵导航或新的已知 ROM 缺口。

2026-08-29 的目录 A/B 对照又排除了两层。原厂/guest 自建 `TRASH.CAN`
中的 dot 记录为 `ATTR=0x16`，且 8.3 扩展名三字节是 NUL；诊断导入器按该格式
修正后，guest 从 `.` 推进到了 `..`。在另一份只用于定位的 game-first 镜像中，
`FILE_SIZE_RECORD` 已精确呈现 `英雄传奇.NPE`、`ATTR=0x20`和
`LENGTH=0x001F576A`，然而失败 LCD 帧与含 dot 记录的镜像 hash 完全相同。
再按 Enter 只得到 modal ack、白屏和 `FILE_OPEN SELECTED=0`。这证明完整文件
记录已被 guest 解码，最近边界严格位于 descriptor 解码之后、list item
attach/selection 之前。game-first 镜像不是 canonical 介质，不得作为最终目录布局。

2026-08-30 的 v731 又把这一边界推进到 compare/layout wrapper 内部。四个真实矩阵事件
`0xB0 → 0x86 → 0x83 → 0x86` 都已由 guest 确认，application state 自然变为
`0x0078`。紧接着出现的 `1A:4220 → 16:0030` 不是按键缺失，而是 exact
`1A:DEAA ← 37:DEAA` 函数的 Harvard 数据视图不完整：除已知 `1A:E038` 四项表外，
它还使用六张五项 computed-RET 表：

| 数据表 | 五个原厂近目标 |
| --- | --- |
| `1A:E112` | `E6CE, E11C, E6CE, E1C6, E11C` |
| `1A:E30C` | `E6CE, E316, E6CE, E3C0, E316` |
| `1A:E506` | `E510, E510, E520, E51A, E51A` |
| `1A:E562` | `E56C, E56C, E57C, E576, E576` |
| `1A:E5BE` | `E6CE, E6CE, E6CE, E5C8, E6CE` |
| `1A:E620` | `E62A, E634, E6AC, E670, E652` |

旧模型的数据总线把这些表读成零，使 `RET` 跳到 `1A:0000`。该位置又被误当作空闲区
放置大型 clean-room 安装器；安装器末尾 `1A:4220` 的 `RETS` 因此消费了错误栈内容，
伪返回到 `16:0030`。修复契约是：安装器搬到已验证空闲的 `0A:0000..4221`，仅为六张
`0x0A` 表增加 `soc_rom` 窄数据 alias，无 HLE 返回值或菜单状态注入。完整 16 位表项不会
跳入低地址；复核还确认 `37:0010` 是前一条指令的扩展字，且 `37:0000..098B` 没有可证明
的 compare-table xref，所以不能把它描述成 compare 续体。另一条独立证据链则确认该低
resident 区确实存在：完整 `49:6E0C..6FFE` 在 `49:6ED6` 唯一执行
`SCALL 1A:0000`，按三个 far 参数并在返回后清理 12 字节；`37:0000..098B` 是完整
`LINK #4 ... UNLINK/RETS` 同址函数。因此最终恢复整段
`1A:0000..098B ← 37:0000..098B`，但不使用错误的 `1A:0010` 入口解释。对应静态证据见
`doc/disassembly/np560_source_370000_report.md` 与 `doc/disassembly/np560_source_496e0c_report.md`。

v732 隔离冷启动和同一路径重放已确认四个导航事件全部由 foreground guest 确认；第四步
之后 `APPLICATION_STATE=0078`，且 `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL` 都为
none。画面已正确显示娱乐二级项目，但 NPE 文件列表尚未 materialize。第五个额外确认被
modal 消费并产生错误重绘，状态又由 `0078` 退回 `00FF`。当前最早的动态失败已经收敛为
`18:CFA8` 在 `32:FA06 → 25:5460` 存储上下文检查后得到零结果，并从 `18:D098` 退出；
下一步是记录 `25:5460` 六个子调用的返回值和 `A2:2AE0` 首个非零错误来源，而不是继续
修改按键映射或 Web 画面。

v734 恢复了独立 exact `1A:0000..098B ← 37:0000..098B`，五键重放现由 guest 清楚
弹出“无此目录 `0:\应用程序`，请创建！”。只读 `NPE_RESOURCE_CHECK` 记录到
`25:5460` 的 child 1 `31:E022=0`、child 2 `33:07B0=0`、child 3
`29:16B0=FFFC`，随后 `25:5556` 首次写入非零 `A2:2AE0=FFFC`；因此该对象失败与
缺少 FAT 目录吻合。`APPLICATION_COMPARE_RET` 同时确认本轮 `1A:E61E → 1A:E62A`，
误跳 `1A:0000` 为 0。v734 ROM SHA-256 是
`D1B2D578EC4B3805F09F888785D24795B7236C15BCBD730E48DE0323CBE74D51`。
下一轮使用独立诊断 checkpoint 导入真实文件以追踪列表和 loader；该 checkpoint 不能替代
最终需要恢复的原厂建目录/USB 传输工作流。

v735 诊断 A/B checkpoint 已把 `应用程序/英雄传奇.NPE` 以 guest FAT 记录布局写入独立
副本，并通过逐字节回读、双 FAT、FTL、FNV 和 ECC 校验；源 checkpoint 哈希未变化。
在该副本上，前三个真实矩阵事件成功后，目录枚举从 `1C:D92C` 首次暴露缺失 resident
`1F:5BFA`，`ROM_MISSING` 立即停止探针。当前恢复契约因此前移到这个原厂入口：只有在
same-PC 源、完整边界、调用 ABI 和可能的 Harvard 数据表全部闭合后才能加入 ROM；禁止
对该调用返回固定成功值或直接伪造 `英雄传奇.NPE` list item。

v736 已按 exact 源关闭该边界：`1F:5BFA ← 3C:5BFA` 是独立的 `0x0606` 字节函数，
607 条可达指令、13 个调用、0 unknown/overlap；唯一冲突叶子
`50:5ABA..5AC6` 被搬到已验证空槽 `06:1CF0..1CFD`，仅改复制体中的一处调用，未覆盖
同为 live branch target 的 `33:5ABA`。v736 ROM SHA-256 为
`A12382EB1A206B2ED6F4AD30EE09C8AE5295553794B0A918A44888FF9265756F`。

使用同一诊断 NAND 的四键冷重放已经越过该函数，且 `ROM_MISSING/UNSUPPORTED/
INVALID_CONTROL` 均为 none；但 0、10、30 秒的画面 hash 不变，列表不是延迟显示。
v736 的只读 `NPE_OBJECT_MASK` 当时观察到 `1F:5BFA` 与 `1C:D9DE` 都读取
`obj+0x12=0`，并据此提出“有效标志 producer”假设。最新静态复核已经推翻这个解释：

- 被监控的是 `1B:23B8` 的 render object（`FP-0x28`），其 `+0x10..+0x13` 是允许为 0
  的四字节 range pair，不要求把 `+0x12` 写成 1；
- 真正 Game World controller 对象是外层 `2F:68A2` 的 `FP-0xC4`，其 ctor
  `23:3436` 已按原厂分支正确写自己对象的 `+0x12`；
- `0x68` 是“低级格式化”的 catalogue index，不是当前浏览器事件；其
  `52:FFDC → 1C:7052` ctor 和 D01C 记录与 NPE 路径无关；
- 禁止再追 render object 的“写 1 producer”、调用 `1C:7052`、使用 D01C 或强制补字段。

v737 builder 纠正了 renderer 的另一处 overlay 误接。完整 `3E:CEF4..D428` 在
`3E:D3FE` 原始调用独立 helper `2E:2B6E`；`11:2B6E` 只是 relocated 输入大函数的
内部尾段。exact `4B:2B6E..2CF6` 是 `0x018A` 字节的平衡 `LINK #3` 函数。QEMU 现已为
`2E:2B6E+0x18A` 提供严格 coherent writable data/code backing，并同时闭合
`29:D0BA+0x296`、`2F:B644+0x130`、`2D:F47C+0x196`、`30:6082+0x104`；
overlay map 和 alias audit 均为 missing 0、non-identical overlap 0。第一次 v737 的
无 backing 动态运行仍属无效历史证据，但该 QEMU 缺口不再是待办。

最新的 source/target 交叉引用恢复了原厂 renderer/controller 生命周期：

1. 13 个原始 call site 全部执行 `SCALL 0F:7E18`，而 `2C:7E18` caller 为 0；
2. `2C:7E18..9B94` 是 resident controller 的完整 `+0x1D` source image：
   `0x1D7E` 字节、2,266 条可达指令、26 calls、0 unknown/overlap；
3. clean-room ROM 固定嵌入 `0F:7E18..9B96 ← 2C:7E18..9B96`，并把其 15 项
   computed-RET 表 `0F:7E92+0x1E` 映射为只读 Harvard data alias；
4. controller 离开 source bank 后，guest 才把 exact `49:8744..8930` 安装到原目标
   `2C:8744`。三个 renderer caller 保持原始 `SCALL 2C:8744`，QEMU 对该窄窗口使用
   coherent writable data/code RAM；
5. v738 的“只覆盖 2C 但未恢复 0F controller”运行和 v739 的临时 resident relocation
   都不是有效动态进展，禁止据此判断列表成败。

controller 本体和 Harvard 表已闭合。第一批 storage 依赖及其后代已经用 11 个 exact
overlay 闭合：`2D:0B00`、`2A:8F26`、`33:1E22`、`30:09F2`、`30:BC4C`、
`2C:682E`、`20:CE3A`、`30:E81A`、`2D:6070`、`2E:6822`、`32:DCAC`。第二批
resident `0D:B1C0`、resident `1E:9E66`，以及 application
`2D:622E`、`30:A0FC`、`28:7408`、`30:EE12`、`31:50D0`、`32:3E52`、
`28:2844`、`32:E06C`、`2B:DB86` 也已进入 builder、QEMU、只读表别名和定向回归。

这些静态恢复最初由 v748 canonical ROM、干净冷启动和五个真实矩阵边沿验证到“唯一 Hero
item 已 materialize、SelectHero event-state 回调正常返回”的边界；当时的
`1B:0154/WORD=3F7E/SP=FFE0` 后来已证明是更早的 computed-RET Harvard data view 缺失，
并由 v749 关闭。后续 v750–v756 又依次越过 modal closure、`1B:7A20`、格式常量 data
生命周期、status-2 和 `5F:F38A` collision。旧对象字段或
`NPE_BROWSER_LAYOUT CALLS=0` 均不得再作为当前根因。

当前下一步固定为恢复 `1F:D210 → 32:CEEE` 内部导致
`32:CF7C RETS → 1F:4D59` 的第一处真实差异，让同一次矩阵选择路径继续进入 NPE loader、
重定位、入口 ABI 和真实首帧。同时仍要追原厂文件系统 API 的 canonical 建目录/导入方法。
禁止把宿主目录直接当 guest 目录，也禁止在 Web、QEMU 设备模型或 guest RAM 中伪造目录、
列表、选择结果或游戏画面。

显示与输入验收保持分层：先确认主菜单和 NPE 列表由上述 controller/layout 链稳定、正确
渲染，再用现有 8×8 矩阵路径补完长按、组合、返回和退出的动态键盘验收。右下角时钟残影
仍是独立未完成项；每次刷新只能由 guest 按原厂语义先清除/恢复时间区域背景，再绘制新
时间，并用 back buffer、ST7529 GRAM 和最终 LCD 三层证据确认。Web 前端不得清区、擦除
旧字形或重画时间来掩盖 guest 侧缺失。

量化验收固定为：时钟连续至少 20 次真实变化、覆盖至少一次多位数字边界，三层时间矩形
逐像素一致且矩形外不变；键盘在同一次 NPE 游戏前台运行中通过方向长按、动作组合、
返回/退出、失焦释放和 1,000 次 press/release；游戏只用虚拟物理键盘沿
`开始 → 娱乐 → 游戏世界 → NPE 游戏 → 英雄传奇.NPE` 启动，连续可观察游玩至少 10 分钟
并正常退出回主菜单。64/64 独立短按、列表可见或显示首帧都不等于最终完成。

最终完成条件不变：只用虚拟物理键盘沿
`开始 → 娱乐 → 游戏世界 → NPE 游戏 → 英雄传奇.NPE` 启动一份真实、来源可校验的 NPE，
持续游玩并正常退出。菜单可见、列表可见或静态依赖闭合都只是中间里程碑。

## 可重复证据

静态解码和断言由以下脚本维护：

- `scripts/analyse_np560_operation_catalog.py`
- `scripts/tests/test_analyse_np560_operation_catalog.py`
- `scripts/tests/test_build_np560_reconstructed_rom.py`
- `scripts/tests/test_np560_overlay_map.py`
- `scripts/tests/test_np560_runtime_overlays.py`
- `scripts/probe_np560_matrix_route.py`
- `scripts/capture_np560_native_buffers.py`
- `doc/disassembly/NP560-source-498744_report.md`

运行：

```powershell
python -m unittest scripts.test_analyse_np560_operation_catalog
python -m unittest scripts.test_build_np560_reconstructed_rom.ReconstructedRomTests.test_file_construction_chain_uses_exact_guest_code
python -m unittest scripts.test_np560_overlay_map
python scripts/analyse_np560_operation_catalog.py --output tmp/np560-operation-catalog-current.json
```

operation-catalog 测试共 6 项，覆盖 NPE/NWF 分离、dispatcher/wrapper 地址、字符串指针
边界以及 selected-file 到 application manager 的第一段启动链；另有 builder/QEMU 测试
固定 `0F:7E18` controller、`0F:7E92` Harvard 表、`2C:8744` layout 生命周期、
`22:147A` callback 闭包和 runtime overlay 映射。controller 是 resident exact code，不作为
QEMU late-overlay；只有其内联表需要只读 data alias。
