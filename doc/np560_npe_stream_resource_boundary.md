# NP560+ NPE 流与资源边界

更新时间：2026-09-02

2026-09-06 更正：本篇历史探索中的 `map_index` 读取了事件条件字段 `52:7A66`，
不是实际地图号 `52:7A58`。因此“地图始终为 1”的结论撤回；实际已经沿原厂出口进入后院，
见 [地图切换与对话](np560_npe_map_transition.md)。历史文件读取范围仍是对应运行的有界证据，
但不能据此排除地图切换或其它剧情路径。后续声音来源/入口状态以整机计划链接的最新文档为准。

## 目的

本文记录真实 `英雄传奇.npe` 在原厂 guest 路径中的文件读取位置，避免再把内存目标地址、
图形块、字符串和潜在音频数据混为一谈。所有结果来自只读观察器；输入仍由 Web/QEMU 8×8
矩阵进入原厂 scanner/consumer，观察器不修改流位置、目标缓冲、返回值或游戏状态。

## 观察器

固件中 275 个静态 `03:4010` 调用点采用同一 5-word ABI：

```text
stream far pointer, destination far pointer, byte length
```

安装后的 `33:048A` wrapper 调用 `1C:CCD4`，在 `33:04BE` 返回。QEMU 现在为 NPE 游戏
生命周期内的每次调用记录：

- caller、stream、destination 和 length；
- `stream+0x28/+0x2A` 中调用前后的 32-bit 文件位置；
- R0:R1、错误码和是否写入游戏对象表；
- 累计请求/推进字节数，以及 4 KiB 文件页访问计数。

诊断输出为 `NPE_GAME_TABLE ... pBEFORE>AFTER` 和 `NPE_STREAM_POSITION`。名称中的
`GAME_TABLE` 是历史命名；调用环现已覆盖完整 NPE 游戏态，`T`/`WRITES` 等字段仍只统计
`52:6CA2` 游戏对象表。

`03:401C` 也已由 live code `30:C8C0..C99C` 闭合为标准流定位 wrapper，而不是资源解码器：

```text
stream far pointer, signed 32-bit offset, whence
```

其中 `whence=0/1/2` 分别按绝对位置、当前位置和文件尾计算目标位置，再调用
`5F:C5EC` 更新 stream。新的 `NPE_STREAM_RESOLVE` 环记录 caller、offset、whence、定位前后
位置和返回/错误码；它与后续 `03:4010` read 配对后，可以直接指出首次高区段读取是谁选择的。

## 进入运行主循环后的基线

当前恢复 ROM 的冷启动桌面会保持“开始”菜单已展开。自动路线现在先用 native LCD
状态识别这一点：已展开时使用六个边沿
`M53/86 → M37/83 → M53/86 ×4`；若开始菜单关闭，才先发送 `M55/B0`，使用完整七边
路线。旧版脚本无条件按一次开始键，会把已展开菜单关闭，使后续输入误入“学习”子菜单；
这属于测试路线状态假设错误，不是 guest 菜单或矩阵键盘故障。下述旧证据目录中的
“七键”描述保留其当时实际输入序列，新回归不再把七边写死。

`tmp/v891-all-stream-target-route/manifest.json` 从冷启动进入《英雄传奇》并走到已知物件前。
到目标位置时：

```text
CALLS=1598, RETURNS=1598, ERROR=0
RANGE=0x0000035A..0x0013291A
REQUESTED=ADVANCED=926237 bytes
PAGES=43
```

这组旧记录的观察器是在加载器交出控制权后才启用，因此它只能证明：进入首地图主循环后，
该段路径访问 section 0..12，尚未继续读取 section 13+。它不能证明启动加载器没有访问高段；
v905/v906 的全生命周期记录已经修正这个范围错误。高段仍不能仅凭位置命名为音频。

## “布鞋”物件动作

最终证据是 `tmp/v894-all-stream-trace-object-action/manifest.json`。首次动作的原厂路径为
`selector/pass/commit = 1/1/1`，第二次为 `guard reject/commit = 1/0`。首次提交立即新增
7 次完整流读取，共 118954 字节，7/7 返回、无 reverse、无错误：

| caller | NPE 文件范围 | 长度 | 目标 |
|---|---:|---:|---:|
| `29:5DB6` | `0x003AFA..0x00AEE0` | 29670 | `51:A20E` |
| `29:5DB6` | `0x00AEE0..0x0122C6` | 29670 | `51:A20E` |
| `29:5DB6` | `0x0122C6..0x0196AC` | 29670 | `51:A20E` |
| `29:5DB6` | `0x0196AC..0x020A92` | 29670 | `51:A20E` |
| `5F:00C8` | `0x002E12..0x002E16` | 4 | `00:0D74` |
| `5F:00EE` | `0x002E16..0x002E1A` | 4 | `00:0D78` |
| `5F:01A8` | `0x038FE0..0x0390EA` | 266 | `51:A20E` |

前四段从 section 1 的起点开始连续搬运，两个 4-byte 读取落在 section 0，最后 266 bytes
仍落在 section 1。结合共享大缓冲 `51:A20E` 和随后画面变化，这组证据归入图形/场景资源
装载候选，而不是音频 producer。

物品说明延迟阶段另有 52 次、总计 78 bytes 的 page `0x090` 读取。现有 16-slot 尾环显示
最后 16 次均由 `22:C7FC` 把 `0x090AF8..0x090B08` 逐字节搬到
`52:73BD..52:73CC`。`22:C7FC` 的 live disassembly 是“读 1 byte → 写入索引缓冲 → 检查
NUL → 递增”的字符串循环，因此该尾段属于说明文字装载，不能作为音频流证据。

## 地图扩展与 seek 复验

`tmp/v897-high-section-event-explore-128/manifest.json` 将首地图的原厂矩阵探索扩大到
128 个状态、58 个坐标、366 条累计转移和 128 个动作点。共取得 17,590 次完整 stream
read，累计推进 2,194,907 bytes；地图 index 始终为 1，文件上界仍严格停在
`0x0013291A`，没有一次新的 section 13+ 读取、reverse 或 guest fault。这是“加载完成后的
普通可达地图 1
走路/空动作不会自然触发战斗或音频”的有界阴性证据，不能继续靠盲目扩大同类遍历推进。

新 seek 观察器的独立烟测为 `tmp/v901-stream-resolve-smoke/manifest.json`。从桌面经真实七键
路径进入游戏并接受一次物理方向边沿后，`03:401C` 为 22/22 call/return，所有返回码和
错误码均为 0，`ROM_MISSING/UNSUPPORTED/INVALID_CONTROL` 均为 none。尾部可精确看到
`29:5D84` 依次绝对定位到 `0x003AFA`、`0x00AEE0`、`0x0122C6`、`0x0196AC`、
`0x020A92`，随后 `03:4010` 读取对应图形块。这同时验证了 observer 的 ABI、字节序和
前后 position 采样。

## 全生命周期高段读取

旧观察器只在加载器首次接受运行期 `0x86` 事件后启用，因而漏掉 mode-2 启动加载阶段。
现在观察器在原厂 mode-2 入口 `2F:B726 → 1F:D1A6` 即开始记录；这只扩大只读诊断范围，
没有更改 guest 执行、流位置或输入。

`tmp/v905-full-lifecycle-stream/manifest.json` 的干净七键启动取得 1,142/1,142 次完整 read、
313,694 bytes 推进和 28/28 次 seek。最先三次绝对 seek 是：

| caller | 定位位置 | 含义 |
|---|---:|---|
| `24:AD6C` | `0x13291A` | section 13 起点 |
| `24:AE1C` | `0x132B0E` | section 13 内部 |
| `24:AEF4` | `0x132B8E` | section 14 起点 |

`tmp/v906-high-stream-io` 使用独立 64-slot `NPE_HIGH_STREAM_IO` 环保留 section 13+ read，
确认 4/4 次调用全部成功：

| caller | NPE 文件范围 | 长度 | 目标偏移 |
|---|---:|---:|---:|
| `24:AD92` | `0x13291A..0x13291E` | 4 | `0x0DE6` |
| `24:ADB8` | `0x13291E..0x13291F` | 1 | `0x0DEB` |
| `24:AE42` | `0x132B0E..0x132B12` | 4 | `0x0DE2` |
| `24:AE68` | `0x132B12..0x132B16` | 4 | `0x0DEC` |

这与 `24:ACBA` 的静态反汇编一致：它按 `section13 + 5*(index-1)` 读取一个 4-byte 值和
1-byte 标志，再从 section 13 内部读取两个 4-byte 值。Hero 文件中的实际四值为
`0x000001F4, 0x10, 0x00000000, 0x0000384A`；`section13 + 0x1F4` 正好等于第二次 seek 的
`0x132B0E`，零值又使最后一次 seek 恰好落在 section 14 起点。

离线分析进一步闭合了 section 14：其大小 `0x384A0 = 16 × 0x384A`，每个 `0x384A`
记录都由 10-byte little-endian 头 `(kind=0x1001, x=0, y=0, width=240, height=120)` 和
`240×120/2 = 14400` bytes 载荷组成。这是严格的 16 张整屏 packed-4bpp 位图结构，
`tmp/v906-hero-npe-analysis.json` 及 `analyse_np560_npe.py` 的结构检测器可重复验证。因此
section 13/14 已归类为位图索引/整屏图像库，不是音频候选。在下一个 seek 前文件位置仍是
section 14 起点，说明该 loader 后续通过另一条消费者/装载路径处理所选位图，而不是继续用
`03:4010` 读取。另一个读取 section 15 的静态函数 `2C:B8C2` 在本次启动路径没有命中。

section 15 也已由静态消费者和离线结构闭合，而非音频。`2C:B8C2` 先读取一个 total 和
10 个 16-bit category count，再用 `03:4124` 的结果做累计权重选择，最后从 u32 offset
表定位记录。Hero 的实际布局为：total `5385`，category counts
`[1100, 4285, 0, ...]`（和恰为 5385），offset table 位于 `0x16..0x543A`，随后是
`FFFFFFFF` sentinel，5385 个严格递增偏移指向 GB18030 选择题记录；首题是“死海位于哪个
国家”，并含 A/B/C/D 四个答案及尾部元数据。`tmp/v906-hero-npe-analysis.json` 的前 32 条
结构/编码验证与 `2C:B8C2` 的动态可触发性仍分开记录。section 15 因此归类为随机题库，
不再列为音频候选。

## 已排除与仍未知

- 仅跟踪 `0C:BDBE` table loader 会漏掉物件事件；通用 275-call observer 已修正此盲区。
- 物件动作没有访问 section 16..37，也没有出现输入/空闲特有的未知 SFR 写入。
- `tmp/v907-live-section-data-hits.json` 已在 live segment 52 找到 Hero section 13..37
  全部运行期指针；`tmp/v907-live-section-consumers.json` 又把共同消费者闭合到
  `03:438C → 32:5F86 → 32:B974 → 25:0000`。`25:0000..0410` 与 source
  `42:0000` 精确一致，其条件目标的完整 source counterpart 分别是
  `2D:FC0E..FFFE` 和 `42:DF62..E322`，说明后续工作是补齐 relocation closure，
  不是把 section 数据误当代码或补新 CPU 指令。
- 新的只读 `NPE_TRANSITION_LEAF` 观察器在
  `tmp/v911-transition-leaf-input-probe/manifest.json` 中覆盖下键保持、右、上、左、动作和
  空闲；各阶段都有真实 stream 读取与 guest 输入消费，但 `25:0000` 的 call/return 始终
  为 0。因此它不是启动、普通走路、普通动作或空闲必经的消费者，只能称条件后端。
- `tmp/v913-transition-gate-lifetime-route/08-game-ready.json` 进一步解释了这个阴性结果。
  `NPE_TRANSITION_GATE` 跨 mode-2 追踪重置保留冷启动记录：`22:9A1A` 把
  `A1:387A` 从 `0000` 写成 `0001`，`29:C246` 再写一次 `0001`；`32:5F8E` 在真实
  切换服务中精确读到 `0001`，所以 `32:5F86` 原样走提前返回，child/leaf 维持 0。
  两个运行期写 PC 分别对应 exact source `3F:9A1A` 和 `46:C246`，都从
  `10:D016` 经 exact `25:206E` 取值。这里没有 CPU byte lane、ROM 缺口或控制流故障。
- exact source `42:206E` 在普通资源传输后，对 `10:D012..D01C` 使用专用近跳分派表。
  该表是小端 16-bit 目标 `2180,21B0,21E0,2210,2240,...`；旧的 `0080,00B0,...`
  解释错误。live `25:206E..2478` code bus 与 source `42:206E..2478` SHA-256 都为
  `de17f86ca2822a3813fd5ccaffb8a91591d2dc960a84fd9e92b67d8903f66dce`，证明运行体无差异。
- `tmp/v915-resource-special-lifecycle-route/08-game-ready.json` 中两次 `D016` 都完整记录为
  `FF → 01 / dispatch 25:2240 / return R0=0001`。`42:2240` 的机械反汇编证明：它把传输
  后首字节零扩展，值 `<=1` 时保留，值 `>1` 时写回 `1`，最后在 `42:2476` 返回成功。
  因此原始 checkpoint 字节 `FF` 正是 guest 产生门值 `1` 的输入，而非矛盾或 byte-lane
  错误。自然零门控需要 `D016` 的实际输入字节为 `0`；下一步追其持久化生产者和原厂设置
  入口，不能直接强制清零来制造 leaf 调用。
- section 16..37 的 `4 + count*21 (+1)` 结构在 18 个样本中成立，但 raw Speex
  解码探针失败，直接按 `12×14` 未压缩字模展开也只有噪声，且许多 section 在不同游戏中
  完全相同。当前只称固定 21-byte 高熵记录资源候选；音频仍有可能，但没有实证。
- 冷启动各出现一次的 unbanked `F018=0`（`31:B70A`）和 `F01E=0`
  （`32:DC28`）仍未取得精确硬件名称；两者不随走路、动作或空闲重复，暂列系统初始化，
  不能据此声明音频设备。

## 下一步

1. 不再盲扫普通地图 1；`24:ACBA` 的 section 13/14 路径已闭合为整屏位图索引/16 帧
   packed-4bpp 图像库，下一步找 seek 后采用的另一条位图装载消费者，补全 loader 说明。
2. section 15 已静态闭合为 5,385 条 GB18030 随机题库；是否能在游戏内触发
   `2C:B8C2` 只属于功能覆盖，不再作为音频主线。`42:206E` 对 `D016` 的专用分派和
   `FF→01` 默认语义已经闭合；下一步查找 `D016` 的持久化写入者/设置入口，选择能够由
   guest 自然产生零输入的原厂配置或状态。
3. 只有零门控真实触发 `32:B974/25:0000` 后，才补齐两个条件后端，并保留输入参数、
   目标缓冲、返回值和后续消费者继续追到 DMA/SFR；此前不把固定记录或该 leaf 命名为音频。
4. 只有 producer 和硬件寄存器闭合后，才实现 QEMU 音频设备及 Web Audio 输出；Web 不得
   根据画面或按键自行合成声音。
