# NP560+ 键盘完成 worker 与 `0x8C` 状态键

更新日期：2026-08-29

2026-09-06 更正：M26/8C 的状态键结论仍成立，但此前 Web 把它命名为 F2 是错误的。
原厂播放器分支及实际画面证明 F1/F2/F3 对应 M60/M52/M44，F4 保留 M4；
详见 [MP3 功能键纠正](np560_mp3_player.md)。本篇历史中的“F2”观察不能作为面板键名依据。

## 结论

矩阵位 26 在当前原厂事件表中产生 `0x8C`，但它不是应当经普通
`28:F6DE` 槽投递给前台菜单的事件。原厂 `28:F4A4` worker 有意消费
`0x8C`，并把它作为自定义玻璃 LCD 状态平面的切换键：第一次按下设置
状态位 268，第二次按下清除状态位 268。按键释放本身不切换该位。

此前把 `MATRIX_EVENT_MAPS` 没有增加解释为“F2 丢键”是错误的，因为该
计数只挂在普通事件写入 `28:F6DE → A2:28DA` 的边界。状态键在到达该
边界前已经被 guest 正常消费。

动态复验同时暴露并修复了一个真实的 SoC Harvard 数据映射缺口：运行时
`31:5014`/`31:4D24` 虽然已有 exact code overlay，但它们通过数据总线读取的
`33:39E6..33:3A25` AND/OR 掩码表仍看到 flat bank 33 的可执行代码。QEMU
现将同链接原厂源 `50:39E6..50:3A25` 作为仅 0x40 字节的只读数据视图映射
到该范围；指令总线保持不变。

## 原厂代码链

入口 wrapper：

```text
33:38F8 ← 50:38F8
  清 A2:2A5C
  取 A2:2A8A
  SCALL 28:F4A4
```

完整 worker：

```text
28:F4A4 ← 45:F4A4，大小 0x02DE
LINK #3 … UNLINK/RETS
239 条可达指令，5 个调用，0 个未知控制流前沿
```

worker 依据 `A2:28D3` 的模式位，从 `32:29B2`、`32:2A32` 或
`32:2AB2` 表中取得当前固件事件并保存到 `A2:28D8`。普通事件在
`28:F6DE` 写入 previous/completion 槽 `A2:28DA`；`0x8C` 则走专用分支：

```text
当前=0x8C，previous!=0x8C:
  28:F65C  设置 A2:28D3 bit 0
  28:F67E  previous = 0x8C
  28:F682  SCALL 31:4D24(0x010C)  ; OR
  28:F68E  SCALL 33:3C86          ; 刷新 LCD 状态平面

当前=0x8C，previous=0x8C:
  28:F628  清 A2:28D3 bit 0
  28:F648  previous = 0xFFFF
  28:F64C  SCALL 31:5014(0x010C)  ; AND
  28:F68E  SCALL 33:3C86          ; 刷新 LCD 状态平面
```

`31:4D24 ← 4E:4D24` 和 `31:5014 ← 4E:5014` 均为 0xBC 字节、76 条
可达指令、无子调用且平衡返回的完整函数。它们把参数除以 16，以商选择
`51:2734` 中的 word，以余数选择以下掩码：

```text
33:39E6..3A05 ← 50:39E6..3A05
FFFE FFFD FFFB FFF7 FFEF FFDF FFBF FF7F
FEFF FDFF FBFF F7FF EFFF DFFF BFFF 7FFF

33:3A06..3A25 ← 50:3A06..3A25
0001 0002 0004 0008 0010 0020 0040 0080
0100 0200 0400 0800 1000 2000 4000 8000
```

参数 `0x010C` 因而选择第 16 个 word 和 bit 12，即整个 480-bit 状态
缓冲中的 bit 268。`33:3C86 ← 50:3C86` 将 `51:2734` 传给 exact
resident `14:6E10`；后者把两个 240-bit 平面送入 ST7529 line 19/140，
Web 只读取并呈现这些玻璃电极状态。

## 动态证据

干净 v692、`ROM_HLE=off`、`HLE_UI=off`、真实矩阵位 26：

```text
第一次：M26 → candidate 0x008C → bit 268: 0 → 1
第二次：M26 → candidate 0x008C → bit 268: 1 → 0
普通完成计数：MATRIX_EVENT_MAPS 仍为 0（符合专用消费路径）
候选写计数：MATRIX_CANDIDATE_WRITES 1 → 2 → 3
```

证据目录：

- `tmp/np560-v692-key8c-toggle-final/route.json`
- `tmp/np560-v692-key8c-toggle-final/01-f2-on-held.json`
- `tmp/np560-v692-key8c-toggle-final/02-f2-off-held.json`

同一 QEMU 上矩阵位 15 仍沿普通路径完成：

```text
M15 → candidate 0x008D → 28:F6DE completion 0x008D
MATRIX_EVENT_MAPS 0 → 1
```

证据为 `tmp/np560-v692-key8d-map-final/route.json`。两条路径均保持
`ROM_MISSING=none`、`INVALID_CONTROL=none`、`UNSUPPORTED=none`。

## 64 位分段动态验收

QEMU 现把既有 application trace 中 `20:2E9E` `KEYMAPRET`（索引 85）的
累计次数与 R0 事件值通过只读 QOM 字段
`key-foreground-ack-count`/`key-foreground-ack-last` 暴露；Web
`/api/key-status` 对应返回 `acknowledgements`/`acknowledgement`。这只是观察
原厂 `33:4ECC` mapper 的返回边界，不确认、不清除也不修改 guest 事件。

64 位不能在一个前台上下文中机械串行按完：M35/`0x97`、M43/`0xBF`、
M53/`0x86`、M59/`0xB4` 等事件会切换页面、应用或启动当前项。若仍要求下一键
返回根桌面的 `KEYMAPRET`，会把“前台已变化”误报成矩阵断路。隔离复验证明：

- 顺序主菜单上下文中 M00..M35、M37..M43、M45..M53、M56..M59 通过；
- M36/`0xE9`、M44/`0xEA`、M54/`0x20`、M55/`0xB0`、M60..M63 在新的稳定
  主菜单上分别通过；
- 每个普通位均依次写出活动表 `4F:2AB2` 的精确 candidate、到达
  `28:F6DE` map，并在其隔离主菜单上下文返回 `20:2E9E`；
- M26/`0x8C` 是唯一不要求 `28:F6DE` 的 candidate-only 状态键；
- 每步释放后 Web matrix 为零、F160 低字节恢复 `0xFF`、`A2:2A5C=0`，且扫描
  计数继续前进。

`scripts/merge_np560_matrix_routes.py` 对八段成功 route 做重复索引、活动表事件、
candidate、map、foreground acknowledgement 和 release 的机器校验。聚合结果：

```text
COVERAGE=64/64 COMPLETE=1
candidate-only=1
map+foreground-ack=63
map-only=0
```

正式聚合证据为 `tmp/np560-v692-matrix64-isolated-summary.json`，SHA-256：
`B51623D7B601D6DC6A328B0F905C431D5945966DA88E8C35B72BCD944E591A73`。
该结果证明 64 个物理矩阵位、活动事件表和主菜单输入链均可工作；它不证明辞典等
切换后的前台应用已经重新进入可连续交互的事件循环，也不替代长按、组合键和失焦
释放测试。

## v695：跨应用前台连续输入

M35/`0x97` 切换到辞典后下一键停住的根因已经定位并修复。原厂 guest loader 实际执行
了两次代码搬运，但 QEMU 的旧 SoC 映射只让数据总线看到写入结果，指令总线仍取到旧
NOR/SoC-ROM 内容；随后调用的四指令 predicate 又与 writable NAND sector buffer
发生 Harvard 数值地址碰撞。这不是应当新增的 DMCU 指令，也不是需要 HLE 的 ROM 服务。

v695 使用以下三段有界硬件视图恢复原机的 data/code bus 选择：

```text
33:44AE+0x001C                 coherent writable executable RAM
0D:2F30+0x2E6C                 coherent resident executable RAM
33:6BE2+0x0008 ← 50:6BE2       source-pinned instruction view
```

前两段由 guest installer 分别写入 exact `50:44AE` wrapper 和 source `2A:2F30`
body；第三段的指令总线读取 exact source-50 predicate，数据总线仍保留 NAND buffer
语义。`50:6BE2` 的完整函数只有四条指令：

```text
LINK #0
MOV R0,#1
UNLINK
RETS
```

同一次未重启、未恢复快照、未直接修改 guest 状态的 v695 运行结果：

```text
M35 → event 0x0097 → map → foreground ack → release
M36 → event 0x00E9 → map → foreground ack → release
M37 → event 0x0083 → map → foreground ack → release
```

证据：

- `tmp/np560-v695-m35-m36-continuous-ready-predicate/route.json`
- `tmp/np560-v695-m37-continuous-after-dictionary/route.json`
- `doc/np560_source_2a2f30_reachable.asm`
- `doc/np560_source_506be2_reachable.asm`

这关闭了辞典 state `0x4E` 的“切换后 worker 不再消费下一键”卡点。尚未完成的键盘工作
仍包括其他会切换前台的按键之后继续输入、保持/消抖/长按/组合的 guest 动态验收，
以及 1,000 次 press/release 压力测试。最终输入验收仍是同一次
运行中沿原厂菜单进入 `开始 → 娱乐 → 游戏世界 → NPE 游戏`，在游戏前台持续操作并
正常退出。

对应静态/构建回归结果为：ROM builder `166/166` 通过；overlay preflight 为
`540` 项 builder overlay、`0` missing、`0` non-identical overlap；overlay parser/audit
单元测试 `46/46` 通过。

## 2026-09-01：NPE 游戏前台方向语义

v833 已证明 `M61/0x82`、`M37/0x83` 能在真实 NPE 地图中连续纵向移动和滚屏；
`M53/0x86` 也会进入原厂 modal consumer，并使游戏 draw/state-dispatch 计数增加。
这些输入全程保持 `ROM_MISSING=none`、`UNSUPPORTED=none`、
`INVALID_CONTROL=none`。

现有 Web 把 PC 左右方向键映射为 `M28/0x84`、`M20/0x85`。它们在 NPE 前台会正常
完成 candidate、map、modal acknowledgement 和 release，但没有触发游戏 draw。原厂
`37:1312` controller 的反汇编与该动态结果一致：它比较 `0x82/0x83` 作为上下，另一对
方向比较的是 `0x80/0x81`，并同时接受 ASCII `J/L`（以及大小写变体），没有比较
`0x84/0x85`。

主菜单活动表中 M45/M29 分别产生 `0x80/0x81`，但第一次直接在已运行的 NPE 前台探测
M45 时没有进入 candidate/map，`A2:2A5C` 完成门保持为 1；其后的已知上键也被该门挡住。
失败快照在 `tmp/v833-npe-event80-single`。这表明 NPE 前台的输入模式/表切换还需单独
追踪，不能仅凭主菜单 64 键表修改 Web。下一步是在干净实例分别重放物理 J/L
（M33/M49）和 `0x80/0x81` 路径，观察 `A2:28D3` 模式、candidate、map、controller
`A4:7A76` 事件槽与 draw 计数，然后才确定 ArrowLeft/ArrowRight 的最终实体矩阵映射。

## 诊断与回归

`scripts/probe_np560_matrix_route.py` 现在支持：

```text
LABEL:INDEX:EVENT              # 普通 28:F6DE map 事件
LABEL:INDEX:EVENT:candidate    # 被 guest 本地消费的候选事件
```

失败时会在释放矩阵前保存 `*-held.json/.gray5`，再释放并等待矩阵、F160、
`A2:2A5C` 门控及扫描计数恢复。普通 map 步骤还要求 `28:F6DE` 和
`20:2E9E` 两个边界。`--candidate-start/--candidate-stop` 可从指定物理位分段
续扫；`merge_np560_matrix_routes.py` 用于合并隔离上下文的 route。QEMU 通过只读
QOM 字段提供有界 candidate、map 和 foreground-ack 计数，Web
`/api/key-status` 无需在按键按住时轮询完整 CPU 状态。

相关正式反汇编：

- `doc/np560_source_45f4a4_reachable.asm`
- `doc/np560_source_4e4d24_reachable.asm`
- `doc/np560_source_4e5014_reachable.asm`
- `doc/np560_source_503c86_reachable.asm`

这项修复只补齐原厂数据表的 Harvard 数据视图及只读诊断，不修改 guest
事件、菜单状态、LCD 像素或返回值。

## 2026-08-30：Web 实体键盘输入控制器

Web 前端现在只允许 `matrixIndexes` 中已有原厂事件表证据的键进入 `/api/key`，并在
每个可见按钮上显示实际 `M00..M63` 矩阵编号。PC 字母、数字、逗号、句点、空格、
方向、确认、返回、退格、翻页、F1..F4 均映射到同一实体矩阵；PC `Home` 作为前端
便利键映射到实体 `M55`“开始菜单”，不是 guest 菜单状态捷径。真机照片中尚未确定
含义的其余侧键仍明确标为未映射，不会发送猜测事件。

`scripts/web/keyboard_input.js` 用“输入来源 → 已按实体键”保存状态并统一合成 64 位
矩阵电平：

- PC 的 `event.repeat` 被忽略，控制器本身也会拒绝同一来源的重复 make；长按期间只
  保持矩阵电平，由 guest 扫描器决定消抖和重复节奏，浏览器不伪造连续 press；
- 鼠标、触控和 PC 键盘可同时持有按键；两个标签若对应同一个矩阵位，释放其中一个
  不会提前产生实体 break；不同矩阵位可组合按住；
- 指针短点按仍保证至少 120 ms 的可扫描电平，长按不再因移出按钮而自动断开，而是用
  pointer capture 等待 pointer-up/cancel；
- `blur`、页面隐藏会清空所有本地来源并排队发送全零矩阵；`pagehide`/`beforeunload`
  额外使用 keepalive beacon；按住期间前端以独立 heartbeat 续租，heartbeat 不重复写
  QEMU 矩阵。连接真正中断超过 1.5 秒时，Web 服务端 lease worker 会直接把四个硬件输入
  字段写为零；连接恢复而实体键仍按住时才重新发送当前完整矩阵快照。

静态映射、控制器状态机和 Web 生命周期回归由
`scripts/test_np560_web_frontend.py` 覆盖，当前为 `14/14` 通过。该结果证明的是前端
press/hold/release 合成及释放保护，不等价于游戏前台验收：尚未在真实 NPE 游戏中验证
长按重复频率、所有组合语义、正常退出，也未完成 1,000 次输入压力测试。服务端断线
释放是 opt-in lease，旧探针不带 `lease_id`，不会被 watchdog 改变既有按住时长；Web
断线自动 break 的最坏延迟是当前 1.5 秒 lease，而不是“断链瞬间”。

## 2026-09-02：33:6BE2 设置页/词典代码碰撞

音效设置编辑器收到 `M11/0x94` 后曾从 `33:6BE8` 错误 `RETS` 到
`C7:0E00`。这不是新 CPU 指令、按键映射或 ROM 服务缺口。原厂设置函数从
`33:6BDE` 顺序执行到 `33:6BE2`；旧 QEMU 却在该八字节窗口永久换入了
source `50:6BE2` 的独立 `LINK #0; MOV R0,#1; UNLINK; RETS` predicate，导致
没有远调用帧的顺序路径误执行 `RETS`。

修复沿用已验证的冲突函数重定位规则：exact predicate 只映射到空闲执行槽
`5F:6BE2 ← 50:6BE2`，reconstructed resident installer 在复制词典 state-4E
body 后，仅把其中两处 source-proven `SCALL 33:6BE2`（逻辑 `0D:2F48`、
`0D:3A1E`）改为 `SCALL 5F:6BE2`。`33:6BE2` 不再有 QEMU code-bus alias，
因此设置 renderer 的全部 flat 字节和同地址 NAND data buffer 都保持原语义；
没有加入 caller 特判、返回值替代或 host-side HLE。

v922 冷启动动态证据：

- `tmp/v922-sound-editor/route.json`：原厂路径进入“音效开关”编辑器；
- `tmp/v922-sound-toggle/route.json`：`M11/0x94` 由 modal guest 接收，画面保持
  可运行，`INVALID_CONTROL/ROM_MISSING/UNSUPPORTED` 均为零；
- `tmp/v922-dictionary-after-settings/route.json`：同一实例从设置 editor 切入
  辞典后继续接收 `M36/0xE9` 与 `M37/0x83`，证明重定位没有回退 state-4E；
- ROM `tmp/np560-system-v380-current-v922.bin` SHA-256 为
  `2949C25330AEF47B348258F889779EA064ED6C2A9AF25FC22D761B2874A72BB9`。

这关闭的是设置页与词典共享地址的控制流破坏。编辑器画面当前仍为“1.”，
`0x94/0x95/E1/E2` 都由 modal 链接收但尚未确认哪一个动作提交“开/关”；下一步
继续从 guest 事件分支定位真实提交键，并以 `10:D016` 持久化写入和音频寄存器/DMA
活动作为判据，不能根据画面猜测按键语义。

## 2026-09-02：15:F362 确认动作表的 Harvard 数据视图

对 exact `15:F0EE ← 32:F0EE` 的完整事件 handler 复核后，确认 `0x86` 并不直接
提交设置：`15:F2EE` 接受它，`15:F346..F360` 再从六项表 `15:F362` 读取 near-PC，
压栈并执行 computed `RET`。原厂六个目标是：

`F36E, F556, F73A, F8AA, FB8A, FA1A`。

修复前 reconstructed SoC ROM 的 code view 已含这六个 word，但同址 ordinary data
backing 为全零，QEMU 也没有为这张表注册 Harvard data alias；因此输入函数虽然正常
返回，父 handler 却不能进入所选动作。v923 新增的只是
`15:F362..15:F36D` 到 reconstructed SoC ROM 的 12-byte 只读 data view，和已存在的
`11:18D4`、`0F:2132` 等 computed-RET 表采用同一硬件建模规则。

动态重启后，physical/data-bus-visible view 与 code view 均为
`6EF356F53AF7AAF88AFB1AFA`。沿相同设置路径按 `M53/0x86`，窗口正常返回主菜单，
`SETTINGS_INPUT` 由 active 变为返回完成，且无 ROM/控制流/指令故障。证据位于
`tmp/v923-sound-editor/`、`tmp/v923-sound-enter/`。该动作没有触发 `10:D016` 写入，
所以它只证明父级确认分派恢复，不证明当前页面已经改变音效值；下一步仍是解析页面资源
与真实改值事件，再观察 `RESOURCE_PERSIST_WRITE`。

继续进入下一层 exact `14:B768 ← 31:B768` 资源设置 dispatcher 后，已经确定对象
`+8` 的 kind `0x51..0x58` 会在 `14:B868..B930` 通过另一张八项表分派。原厂
`14:B932` 表为 `BDB2,BA5C,B95A,BAC4,BB28,BD58,BA06,BE18`，第 5 项把 kind
`0x55` 精确送入 `14:BB28`；后者读取对象 `+0x1E`，更新 `A1:387A`，并通过
`32:EBAE` exact writer 链持久化 `10:D016`。修复前该表的 code view 正确而 data
view 全零；v923 已加入 16-byte 只读 Harvard data alias，动态读回两侧一致为
`B2BD5CBA5AB9C4BA28BB58BD06BA18BE`。

这已经把 `D016` 的提交对象类型固定为 `0x55`。同一 dispatcher 更前面的事件表也已
闭合：`14:B716` 只是为了直接使用原始 `0x80..0x86` event 而设置的偏置基址，真实读取
窗口是 `B716 + 0x80×2 = 14:B816` 到 `14:B823`。source `31:B816` 的七个 exact
target 是 `C11A,C300,C4E6,C4E6,C762,C762,B868`，所以确认事件的原厂链明确为
`0x86 → 14:B868 → kind table`。v923 为该 14-byte 窗口也加入了只读 Harvard data
alias；没有复制无关的 `31:B716` 指令，更没有猜测 case target。下一步转为定位生成
kind `0x55` 的原厂菜单/对象，并用自然 `RESOURCE_PERSIST_WRITE` 作为提交成功判据。

## 2026-09-02：发音设置两个 resident 编辑器的精确边界

对 source `31:A744` 的完整反汇编纠正了早期归因。`31:AB58` 的立即数 `0x55` 与
`AB30/AB3C/AB4A` 的 `2/18/235` 一起组成绘图矩形 `(2,18,235,85)`；它不是对象
kind。`14:A744 ← 31:A744` 是发音设置第 3 项“音量调节”的完整 `0x1024`-byte
resident 函数，内部没有直接调用 `14:B768`。该函数仍按 source-proven caller 精确恢复，
但 builder、manifest 和测试不再把它命名为 kind-`0x55` producer。

发音设置 selector 的五项 computed 表在 source `36:CC7A`，选择 1..5 依次进入
`18:5964`、`1B:8B08`、`14:A744`、`1D:3B1A`、`1B:A454`。由同页原厂文本顺序可确定
第 5 项“音效开关”的真实入口是 `1B:A454`。升级包中 `38:A454..ACBE` 是一段完整
`LINK #8`/`UNLINK`/`RETS` 函数，大小 `0x086C`，而旧 reconstructed ROM 的整个目标
范围均为填充值；v925 已将该 source 副本原样恢复，且恰好在既有 `1B:ACC0` 函数前结束。

该编辑器入口在 `1B:A46C` 读取 `10:D016`。事件 `0x80..0x90` 通过内嵌表
`1B:A6BC` 的 17 个 near target computed-RET 分派；v925 QEMU 只为这 34 bytes 增加
reconstructed SoC-ROM 的只读 Harvard data view。已证事件为：`0x82/0x83` 修改
`A4:56C0`，`0x84/0x85` 修改 `A4:568C`，`0x86` 推进 `A4:567E` 并进入确认逻辑，
`0x8E` 清理退出。旧探针使用的 `0x94/0x95/0xE1` 不在这张主表中，因此不改值不能再
当作设置提交失败。

`1B:A454` 本身仍没有构造 kind `0x55` 或直接调用 `14:B768`。它调用的共享
`32:F38A` 路径构造 kind `0x58`，确认后写 `10:D019`。所以当前确定事实仍只到：
音效开关入口读取 `D016`；另一条 kind-`0x55` 链会写 `D016`。两者是否由间接对象或
运行期覆盖连接，必须由 v925 第 5 项动态对象 trace 证明，不能仅凭设置名称合并。
