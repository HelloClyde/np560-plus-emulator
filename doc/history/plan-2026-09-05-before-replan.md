# NP560+ 完整模拟器实施计划

更新日期：2026-09-05

当前主线：VMA03 SoC 地址映射与原厂固件执行路线。用户已在当前运行版实测并认可
这一架构方向；当前基线见第 2 节，后续执行顺序以第 8 节为准。旧版本的记录保留为
逆向证据，其中的“当前”“下一步”和已完成测试仅适用于对应版本，不覆盖新的主线。

### 当前进度速览

| 项目 | 当前 VMA03 状态 | 剩余验收 |
| --- | --- | --- |
| 硬件/固件职责分离 | 已确立为主线，用户已实测认可 | 审计并逐项淘汰旧 overlay、重定位与临时桩 |
| 主菜单显示与矩阵导航 | 花屏定位到 NAND 混合字节序；原厂完整烧录的新镜像全字节/ECC 通过，五分类单扫描/普通短按共 18 帧逐像素通过 | 最小出厂输入全量重跑；长按/多轮 held-level 重复消费需另行关闭 |
| 音乐播放器 | 用户报告不能播放；尚未闭合读取、解码和声音输出链 | 原厂支持的样本从选择、播放到可听输出，不能以 NPE 画面运行替代 |
| 真实 NPE 游戏 | 已有短程冷启动闭环；本轮人工确认后完成十分钟、120 次方向操作并退出 | 修复自动导航像素校验，重跑无人值守链及 1,000 次单事件、长按/组合键 |
| Web/QEMU 稳定性 | 8807 曾退出，重启后恢复；原因未确定 | 退出日志、返回码、实例身份、重连及多标签输入释放 |
| 完整交付 | 未完成；并非已获得完整原厂 mask-ROM | 必要音频、真实存档/恢复、可重复生成与自然初始化 |

近期执行顺序：生命周期诊断已补齐，花屏已完成包/NAND/对象对照及隔离像素验证，
USB staging 编码已通过实际 QEMU RAM 微测试，原厂 burner 已在旧输入和最小 factory-only
输入上完成首 48 KiB 写入/提交及逐字节/ECC 核对；完整原包已烧录并通过全字节/ECC 与
零输入冷启动与五分类往返检查。随后验证完整 guest FTL 回读和最小出厂输入全流（详见
`doc/storage/np560_usb_burn_transport.md`），并追踪普通输入的重复消费；音乐播放器仍独立未完成，随后
继续音频、存档与初始化，并按证据精简旧补丁。诊断和回归不得重置用户正在测试的
8807 实例，也不得因一次连接失败自动重启并丢失游戏状态。具体任务及验收见第 8 节。

## 1. 目标定义

本项目的目标不是伪造一份“原厂 resident ROM”，而是在没有真机和片内 ROM
转储的条件下，完成一个可审计、行为兼容的 NP560+ clean-room 模拟器：

- DMCU 指令由 QEMU CPU 执行，不在宿主机拦截 `SCALL` 伪造返回值。
- LCD、NAND、键盘、定时器等由硬件模型提供，不由 Web 前端模拟系统逻辑。
- resident ROM 的重建代码以普通 DMCU guest code 运行，并为每个入口记录证据、
  推断和未知边界。
- 对尚未支持的代码或硬件行为明确停止并报告，不静默填零或返回成功。
- 最终可从原厂升级包和仓库脚本重复生成所需镜像，不依赖手工修改的临时快照。

最终用户目标是：从完整主菜单使用虚拟物理按键进入
`开始 → 娱乐 → 游戏世界 → NPE 游戏 → 英雄传奇.NPE`，选择并加载这份可校验来源的
真实游戏文件，进入游戏、持续操作至少 10 分钟并正常退出。2026-08-29 的原厂操作表逆向已确认，“游戏世界”使用
`0:\应用程序` 目录和 `\*.npe` 过滤器；另一项“动漫欣赏”才使用 `0:\动漫欣赏` 和
`\*.nwf`。因此最终样本目前必须是一份真实 `.npe` 文件，不能把仓库中的合成 `.nwf`
测试容器当成 NPE 游戏。固件里同时存在 `NEPLAYER`/NWF 子系统，但它与 `.npe` 游戏的
关系尚未证明；只有沿真实 `.npe` 启动链继续解析后才能下结论。只显示主菜单、只进入
游戏列表，或由 Web/宿主机重写游戏逻辑，都不算完成。

当前用户可见的三条验收主线为：

1. 右下角时钟必须在原位置持续刷新且不叠加旧字形；2026-08-29 用户截图已经再次确认
   旧数字没有被完整擦除便叠加新数字。必须验证每次刷新都先按原厂语义恢复时间区域背景
   或清除旧字形，再绘制新数字；同步分层确定残影首次出现在 guest 合成缓冲、resident
   绘制调用还是 ST7529 GRAM。候选根因包括缺失/不完整的 resident 清除或拷贝函数、
   Harvard 数据视图/对象边界参数错误，以及 LCD 写窗/自增语义错误；在取得调用和三层
   帧证据前不能直接归因于 ROM 缺失，Web 也不得替 guest 擦除或重画。
2. Web 必须提供完整虚拟物理键盘，按下、保持、释放都经 8×8 矩阵和原厂扫描链进入
   guest，能够在同一次运行中连续导航菜单，并在 NPE 游戏前台完成方向、动作、长按、
   返回/退出等实际操作；只有 QEMU 内部矩阵模型、单个测试按键、64 个键各自独立短按
   成功，或只走通菜单导航，都不算完成。
3. 最终必须从原厂菜单路径启动一个真实 NPE 游戏并可持续游玩、正常退出；这是本项目
   的最终完成条件，主菜单正确和应用列表可见都只是中间里程碑。

由于缺少真机，无法承诺片内 ROM 字节、寄存器电气特性和周期时序与原机完全一致。
“完整”在本文中指已覆盖的用户功能行为一致、所有推断可追溯、未知行为不会被隐藏。

## 2. 当前基线

### 2026-09-05 VMA03 运行版（当前权威基线）

- 正常运行使用 `firmware-vma03`，ROM 为
  `tmp/np560-system-v380-vma03-nand-bootstrap.bin`，基于 `current-v941` 生成，
  SHA-256 为 `a04f1b839a83cdeca63c2cd03ff91b4b3fa053c86bee4ba545561e399202ebc2`。
  NAND 基线为 `tmp/np560-vma03-native-pim-v6.nand`；生成方式和冷启动证据见第 7 节。
  `pim-provision-v6.bin` 专用于通过 guest 文件 API 创建 PIM，不作为正常游玩 ROM。
- `8807` 是本轮测试使用的 Web 端口，端口号不代表版本。运行身份应同时核对 ROM
  hash、启动模式、NAND 来源、QEMU 构建和前端版本；Web 重启不等于 guest 状态恢复。
- 花屏隔离副本为 `E:/qemu-dmcu-build/np560-vma03-menu-block-lanes-v1.nand`，SHA-256
  `1652574a9e5916f4c04004015f21843cee86083c94a53af48193243ad30e7249`；只把物理块
  `0x890` 按原包统一编码，ROM/QEMU 不变。它已通过下述五分类测试，但还不是自然
  烧录生成的 canonical NAND，也没有替换用户 8807 的原副本。详见
  `doc/display/np560_vma03_menu_corruption.md`，不得把原副本的已知花屏当成已修复。
- 新增整包烧录测试版 `8809`，使用 `E:/qemu-dmcu-build/np560-usb-burn-full-v1.nand`
  （SHA-256 `9da1cc971c75fa58c1debe8d04edd8b59acb428de18b21da79d1f50a18576ef3`），
  普通 ROM/PRG 和 QEMU 不变。全原包与 ECC、零输入冷启动、五分类两轮共 18 帧逐像素
  通过；无烧录后局部补丁。它的 NPE/应用文件与音乐尚未验收，不据此替换旧游戏基线。
  运行身份 `20260905T064719.700665Z-9010-660fae21`；未覆盖旧端口现场或配置自动保存。
- VMA03 已闭合冷启动、通过真实 Start 键进入主菜单、沿原厂菜单启动《英雄传奇》、
  四方向操作并退出的核心链。用户本轮实测进一步支持将这条路线确立为后续架构主线；
  这项结论不等于已取得完整原厂 mask-ROM，或所有硬件时序均已还原。
- 根菜单方向语义已在同一 VMA03 ROM 的隔离实例复验：左/右为 `M45/0x80` 和
  `M29/0x81`，顶部分类索引实测 `0→1→2→3→2`；上/下为 `M61/0x82` 和
  `M37/0x83`，开始左栏“娱乐/时间”选中状态之间变化 816 个像素。
  证据在 `tmp/root-tab-right-8808/`、`tmp/root-tab-cycle-8808/` 和
  `tmp/root-start-vertical-8808/`。不得继续把“根菜单不接受方向键”作为原厂行为。
- 尚有重建启动代码、PIM provision 依赖，以及 `01:4674`、`01:46CC`、`01:46D0`
  三处临时音频 `RETS`。这些限制已在 ROM manifest 中记录；无缺失 ROM/非法控制流
  报告并不能证明音频已经实现。必要音频、真实存档和无手工快照的重复生成仍未完成。
- 旧路线的十分钟游玩、1,000 次按键、长按/组合键和时钟边界测试保留为历史成果。
  本节 VMA03 hash 已有第 7 节短程端到端证据，以及本轮人工确认行程菜单后 600 秒、
  120 次方向操作并退出的长跑证据（第 8 节）。全自动长跑启动、千次压力、长按/组合键
  与时钟边界仍需在该基线上重跑，不能沿用旧版本结论。

当前基线启动命令（在仓库根目录执行；仅在目标端口空闲时启动，不是自动恢复命令）：

```powershell
& .\scripts\run-np560-web.ps1 `
  -SocRom '.\tmp\np560-system-v380-vma03-nand-bootstrap.bin' `
  -NandCheckpoint '.\tmp\np560-vma03-native-pim-v6.nand' `
  -BootMode firmware-vma03 -Port 8807 -NoBrowser
```

该命令使用脚本默认的 Ubuntu2 和 `E:\qemu-dmcu-build\qemu-system-dmcu`，不启用
`RomHle`/`HleUi`，也未配置 `NandSaveOnExit`；游戏运行中的 NAND 修改不会因此自动
成为下一次启动的存档。它仍依赖现有 `tmp/` 产物，不代表镜像已能从原始输入一键重建。

### 2026-09-02 NPE 高段资源与条件后端（历史基线）

- 启动路线已改为状态自适应。冷启动检查点可能以“开始”菜单展开或关闭结束：展开时从
  `M53/86 → M37/83 → M53/86 ×4` 六个边沿进入《英雄传奇》，关闭时先发送
  `M55/B0`，组成七边路线。监控器等待精确 `APPLICATION_STATE=00FF` 后再按 native LCD
  空白带判断状态；旧逻辑无条件按 Start 会在已展开时把菜单关闭，使后续按键误入“学习”
  子菜单，这不是键盘或 guest 菜单回归。
- NPE section 13/14 已闭合为位图索引和 16 张 `240×120` packed-4bpp 整屏图像；
  section 15 已闭合为 5,385 条 GB18030 随机题库。section 16..37 仍是
  `4 + count×21 (+1)` 的高熵固定记录；raw Speex 和直接未压缩字模两种简单解释均不成立，
  尚不能命名为音频。
- live segment 52 已找到 section 13..37 全部指针，共同消费者链闭合到
  `03:438C → 32:5F86 → 32:B974 → 25:0000`。运行期 `25:0000..0410` 与 source
  `42:0000` 精确一致；它的两个条件目标目前未完整安装，但已找到完整 source 函数
  `2D:FC0E..FFFE` 和 `42:DF62..E322`。这把问题收敛为 relocation closure，而不是
  缺失 CPU 指令或需要宿主模拟 ROM 服务。
- QEMU 新增只读 `NPE_TRANSITION_LEAF` 环，解析器同步记录 caller、状态/格式、六个参数、
  分支和返回值。`tmp/v911-transition-leaf-input-probe/manifest.json` 覆盖下键保持、右、上、
  左、动作和空闲；各阶段都有真实 stream read，方向/动作均被原厂控制器消费，全程无
  `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL`，但 `25:0000` call/return 始终为 0。
  因此它是条件触发后端，不是开局、移动、普通动作或空闲必经的音频解码器。
- 新增的只读 `NPE_TRANSITION_GATE` 监控已经把“为何没有进入 `25:0000`”闭合。冷启动
  `tmp/v913-transition-gate-lifetime-route/08-game-ready.json` 保留了整个门控生命周期：
  `20:0164` 先写 `0000→0000`，随后运行期 `22:9A1A`（exact source `3F:9A1A`）写
  `0000→0001`，`29:C246`（exact source `46:C246`）再写 `0001→0001`；游戏切换时
  `32:5F8E` 从 `A1:387A` 精确读回 `0001`。因此 `32:5F86` 按原厂条件提前返回，
  `32:B974/25:0000` 的 call 计数为 0；旧诊断把相邻原始字节错看成 `0401`，现已纠正为
  真正的门控字 `0001`。全程无 `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL`。
- 两个写入者都通过 exact `25:206E ← 42:206E` 请求 `10:D016`。此前把小端分派表
  `2180,21B0,21E0,2210,2240,...` 错读成 `0080,00B0,...`，现已由 live code-bus
  与 source 全字节比对纠正：这些都是 `25:206E` 自身内部的 continuation，`D016`
  精确落到 `25:2240`，不是 `25:0040`，也与另一份 `25:0000` 条件服务无关。
- 新的只读 `RESOURCE_SPECIAL` 环在
  `tmp/v915-resource-special-lifecycle-route/08-game-ready.json` 保留 17/17 次完整调用/返回。
  两条 `D016` 证据均为普通传输取到 `FF`、`25:2240` 归一化为 `01`、`25:2476`
  返回成功：`22:9A08 → 25:2240 → 22:9A0C` 与
  `29:C22E → 25:2240 → 29:C232`。机械反汇编
  `doc/disassembly/np560_source_422240_resource_d016_continuation_reachable.asm` 与之完全一致：首字节
  `<=1` 时保留，`>1` 时由 guest 写为 `1`。因此 checkpoint 的原始 `FF` 与门值 `1`
  并不冲突；这里没有宿主 ROM 服务或强制值。
- 七步原厂矩阵路线仍自然进入 `STATE=0078`，随后
  `tmp/v916-resource-special-play-regression/02-after-down.json` 的真实下键得到 modal ack，
  `GRID=7/7`、`DRAW=4/4`，且无 `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL`。当前首要任务
  是追出 `10:D016` 的持久化生产者/设置入口，找到由 guest 自然写成 `0` 的原厂条件；
  在真实零门控触发以前，不预装两个条件后端，也不把它们命名为音频。

### 2026-09-02 世界坐标与首个真实动作对象

- 已纠正地图状态模型：`52:7A2E/7A2C` 才是 X/Y 视口偏移，旧称“scroll”的
  `52:7A84` 实际是碰撞/对象槽索引。状态现为
  `(screen_x, screen_y, map_index, offset_x, offset_y, direction)`；屏幕边缘移动时
  屏幕坐标可以不变而世界坐标继续变化。
- 探索器支持 `--route-to-game`，服务重启后可自行从稳定桌面进入游戏，不再依赖
  “QEMU 恰好已经停在游戏前台”。路线现按开始菜单展开状态选择六边或七边，以上一节为准。
- v3 第一阶段探索 256 个状态、913 个转移，覆盖地图 1 的世界 X=4..15、Y=1..12，
  无 fault。静态动作选择器证明它只按当前朝向检查正前方；对象表则证明对象 0 位于
  世界 `(1,6)`。
- 目标导向遍历仍只发送真实矩阵键并服从原厂碰撞反馈。权威
  `tmp/v848-target-guided-explore-512/manifest.json` 在状态 299 到达世界 `(2,6)`、
  朝左，动作选择器首次从 `FFFF` 变为 `0`；M53/0x86 被 modal controller 消费，QEMU
  无 `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL`。目标帧 SHA-256 为
  `07bd58b126f16f3ed14e5d291205cf6bd5933ca6fe23964fb92f48608ea5ceb7`。
- 新增只读 observer 后，干净冷启动 `tmp/v851-action-guard-observer-first/` 已严格证明：
  第一次动作 `guard=0/pass=1/commit=1/flag=1`；原地第二次动作
  `guard=1/reject=1/commit仍为1`，全程无 fault。一次性对象提交路径已经闭合。完整证据见
  `doc/games/np560_npe_world_state_and_action_selector.md`。
- `tmp/v858-object-action-delayed-regression/` 现把首次动作即时状态、等待原厂 5000 ms UI
  状态后的稳定状态、第二次动作后的状态严格分开。帧 hash 为
  `436d279e…f544 → 436d279e…f544 → 5e466022…2686 → 5e466022…2686`；首次动作
  `pass/commit=1/1`，第二次 `reject/commit delta=1/0`，第二次前后 segment 52/53 均
  0 字节变化。由此确认此前观察到的画面变化来自首次提交后的延迟界面，不是第二次动作。
- 延迟阶段写入 `52:739E` 的 GBK 内容包含物品名“布鞋+1”和说明
  “传说中何山小时候穿的鞋子。防御+1.”，同时 `52:7A72` 从 0 变 1。静态控制器在
  `37:15C6` 调用 exact `22:C370` UI/layout 初始化函数，并在 `37:1608` 传入
  `0x1388`。这证明对象 0 是一次性物品描述/UI 事件；尚无证据证明哪个角色防御或背包字段
  被修改，因此不再把说明文字误写成已定位“防御+1”状态；物品持久化只在真实装备/存档
  路径出现写入证据后继续追踪。
- 游戏前台输入语义现已关闭。v859..v862 对四方向各保持 5 秒，候选/映射/消费分别为
  15/15/15、15/15/15、11/11/11、16/16/16；首次重复约 0.56..0.67 秒，之后中位
  间隔约 0.30..0.32 秒。v868..v871 证明组合键按 guest 降序矩阵扫描优先级只产生一个
  事件：上 M61 胜过动作 M53，其余三方向均由动作 M53 胜出；胜出控制器路径严格命中一次。
  v872 证明独立返回 M28/0x84 被消费但在该主场景无操作；v873 证明真正退出 M55/0xB0
  以一个严格边沿完成 `0078→00FF` 和 root renderer `30→40`。完整证据见
  `doc/games/np560_npe_input_semantics.md`。下一项转为必要音频与真实存档/恢复路径。
- 音频硬件边界开始实测。QEMU 已加入互不混淆的 unbanked SFR 与 banked Fxxx 只读写
  观察器；v880 用真实矩阵输入执行下键长按 5 秒、右/上/左/动作及空闲对照。unbanked
  unknown 在输入和空闲期增量均为 0；banked 候选只增加 42 次，全部是
  `32:245A F14C=8000` 与 `32:2482 F11E=2000` 的固定 pair，空闲期为 0。
  静态调用点 `44:E528` 先读取已确认的矩阵端口 `DS1:7160 → F160`，随后以固定参数
  `3,2000,8000` 调用 `32:241A`。因此该 pair 属于键盘扫描/中断控制链，不是已发现的
  音频流。当前仍未定位 NPE 的实际声音 producer、DMA 或 SFR，QEMU/Web 也尚无可验收
  音频输出；完整边界见 `doc/audio/np560_audio_hardware_boundary.md`。

### 2026-09-02 NPE 动作与稀有重绘故障进展

- 已在 QEMU 增加四个只读、source-exact 方向计数器：上/下/左/右分别对应
  `1A:16A6→16BA`、`1A:16D6→16EA`、`1A:1706→171A`、
  `1A:1736→174A`。动作键 `M53/0x86` 则由既有
  `1A:141E→29:CE22` 调用/返回计数证明进入原厂选择器；初始位置和目前搜索过的
  位置均返回 `FFFF`，意为当前格没有动作目标，不是动作键失效。
- 第一轮螺旋搜索完成 16 个“移动＋动作”位置后，在第 17 个上方向已被原厂控制器接收、
  动作尚未进入选择器时，首次冻结真实
  `INVALID_CONTROL=1D:87AA→58:0051`。静态反汇编证明 `1D:87AA` 是 exact resident
  `1D:831E` 通用渲染器的计算远调用：它从传入对象 `+0x1E/+0x20` 取回调 pair，压栈后
  以 `RETS` 分派。故障现场 `R0:R1=4D58:0051` 更像反序的数据 far pointer
  `0051:4D58`，不是合法代码 callback；调用链为
  `1A:1762 → 1E:1452 → 2E:2546/266C → 1D:831E/87AA`。
- QEMU 已新增该窄路径的只读对象监控：在 `2E:266C` 保存 R4:R5、栈参数和对象前
  0x40 字节，在 `1D:87AA` 再保存 renderer frame 参数、对象和实际 callback/target。
  相关 Web 原子状态字段已接入，构建成功，定向 Python 回归 51/51 通过。监控不修补
  RAM、不替 guest 返回，也不改变控制流。
- 新冷启动中，同样的前 17 步以及随后扩大的 64 步螺旋搜索均完整通过：累计每一步都由
  原厂方向分支和动作选择器确认，选择结果仍为 `FFFF`，没有再次进入上述 resident
  特殊重绘调用，也无 `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL`。因此当前证据不再支持
  “固定第 17 步必坏”；更可能是随机地图内容或输入/重绘相位触发的稀有对象路径。
  初次故障证据仍有效，不能因本轮未复现而忽略。
- 工具侧补了两个复现加速点：动作目标搜索器升级为 v2 manifest，每个移动/动作重试
  阶段即时落盘；输入语义监控增加 `--route-only`，可在真实硬复位、稳定桌面扫描、六级
  菜单消费者验证后停在游戏前台，并增加固定物理 `--pulse-duration`，避免启动/重绘变慢
  时把一次长按连发误作两个独立测试键。
- 当前最高优先级不是补 CPU 指令或在 Web 伪造游戏，而是反复用相同冷启动基线取得可复现
  的故障地图/时序。一旦 `1D:87AA` 再现，直接比较 renderer 入口与 callback 时的对象
  `+0x1E/+0x20`：若入口已错，回溯 `2E:2546` 的对象选择/初始化；若入口正确而回调前变错，
  用对象写监控定位第一条 guest 写。闭合后再继续寻找非 `FFFF` 动作目标、返回键语义、
  存档和音频。

### 2026-09-01 历史检查点

- 原厂主菜单、开始菜单、`娱乐 → 游戏世界 → NPE 游戏` 文件列表以及
  `英雄传奇.NPE` 标题页已经能由 guest 原生绘制；固定物理矩阵路线为
  `M55/B0 → M53/86 → M37/83 → M53/86 → M53/86`，五步均已由自动路线工具验证
  map、原厂 foreground/modal consumer acknowledgement 和释放重置。按键不是当前首个
  阻塞，完整长按/组合/退出验收仍留到游戏前台。
- v794 恢复持久 resident `0C:BDBE`；v795 精确恢复 resident
  `1D:5820 ← 3A:5820+0x738` 和应用 helper
  `22:4C58 ← 3F:4C58+0x506`，动态首个失败从这两处推进到 `25:8392`。
- v796 静态加入新征程的七模块 exact closure：`25:8392`、`23:6C3C`、
  `27:E84C`、`2E:79FA`、`29:BBF2`、`2D:908E`、`5F:0248`。第一次动态运行仍在
  `25:839A/AFBC` 停止，不是反编译错误：guest 安装器虽运行，但这七个目标没有完整的
  Harvard writable-code 窗口，数据写入被 20..4F 的 data-visible NOR 映射遮挡。
- v797 已给上述七处增加严格定长 QEMU data/code 映射；`27:E84C` 和 `29:BBF2`
  保持与 guest 修补后的调用字一致，`5F:0248` 保持 exact `48:0248` 指令源。同步发现并
  消除了两个安装器同占 `1A:7500` 的字典键冲突：state-4E 保留 `1A:7500`，新征程安装器
  移到不重叠的 `1A:7600..77C7`。QEMU 构建成功，overlay-map 72/72，builder 定向回归
  通过；v797 ROM SHA-256 为
  `1E85928316CA64887CB8931DAE0D5AE4764D1093116F89DFDB4B324671DDA244`。
- v797 的真实六键路线（上述五键后再 `M53/86` 选择“新的征程”）已证明
  `25:8392` closure 正常执行，原 `25:839A` 故障消失。新的严格首个边界为 resident
  `1A:1312`，唯一已知调用点是 `2D:F4FA`；当时
  `ROM_MISSING=1A:1312`、`UNSUPPORTED=none`、`INVALID_CONTROL=none`，应用仍为
  `STATE=0078`，NPE 控制阶段已为 1。
- `1A:1312` 已从唯一同 PC 的 source `37:1312` 精确闭合：大小 `0x980`，827 条可达
  指令、30 个调用、0 unknown/overlap，入口 `LINK #0x12`，在 `37:1C8E/1C90`
  `UNLINK/RETS`。该 resident controller 已进入 v798，ROM SHA-256 为
  `948A1730A5DDB034AA6E5F8C91EDE630EFE676EA433DD7D9FF699F1F87577CCF`。v798 的一个
  合法按键时序分支随后从 exact caller `2F:377E` 命中 resident `1B:2C92`；正确文件映射
  证明它对应 source `3B:2C92`，不是 `1B:2C92`。该函数已按 `0x02AA` 字节边界精确闭合：
  240 条可达指令、0 call、0 unknown/overlap，结尾为 `3B:2F38/2F3A UNLINK/RETS`，
  下一函数从 `3B:2F3C LINK #7` 开始。
- `1B:2C92 ← 3B:2C92` 已进入 v799，ROM SHA-256 为
  `D733A9431634ACE77796381CB1E93DE5B5ABB708F1297431F657A609D5E9038F`。v799 的五键路线
  正常显示 `英雄传奇.NPE` 原始标题页；第六键选择“新的征程”后已经越过 v797 的
  `1A:1312` 和 v798 的 `1B:2C92`，保持 `ROM_MISSING=none`、`UNSUPPORTED=none`、
  `INVALID_CONTROL=none`，应用为 `STATE=0078`，NPE 控制进入 phase 1。
- v800–v832 已继续按 code-bus、loader 和 exact overlay 证据闭合“新的征程”初始化链；
  v832 可用七个真实矩阵边沿
  `M55/B0 → M53/86 → M37/83 → M53/86 ×4` 从原厂主菜单自然进入真实 NPE 游戏地图。
  初始地图 `gray5` SHA-256 为
  `5C2FBBB1453AE34DA4C2D7713997FD2345016829E1E0042E32E968C81BB5073D`，
  `HLE_UI=off`、`ROM_HLE=off`。移动事件到达 guest，但 v832 在第四次向下滚屏时从
  ROM03 veneer `03:4268` 首次进入空白 resident `0D:78D2`，留下永久未完成的横条帧；
  这不是 LCD 前端、键盘或新 CPU 指令问题。
- v833 已把升级包 exact `2A:78D2..7B01` 恢复到 resident
  `0D:78D2..7B01`。该函数大小 `0x230` 字节、210 条可达指令、0 direct call、
  0 unknown/overlap，从 `LINK #0x0A` 到平衡 `CRIT #0/RETS`；无需内部 call retarget。
  v833 ROM SHA-256 为
  `EDBB2281EAB00F7F79F761446089F0946F30BBEDF08B2D80C7BE987C1C24144A`。
  与 v832 的所有字节差异都严格位于 `0D:78D2..7B01`，目标区与 NP560.PRG
  `0x0A78D2..0x0A7B01` 完全一致。builder、draw observer 和 monitor 定向回归 5/5 通过。
- 同一 NAND 冷启动的 v833 七键路线再次 7/7 完成 map、guest consumer ack 和 release；
  之后五次 `M37/0x83` 向下事件也全部由 modal guest 确认。v832 的缺页复现点现在保持
  `ROM_MISSING=none`、`UNSUPPORTED=none`、`INVALID_CONTROL=none`，地图先产生正常中间滚屏帧，
  随后由 guest 完成区域搬移、清除旧角色位置并填入底部新地图行。稳定帧 raw `gray5`
  SHA-256 为
  `8FEDE7BC134D16951BC3F041D874FA08BE3BD473005A304BCD263BFDFF0DE456`；
  证据目录为 `tmp/v833-game-route`、`tmp/v833-down-four`、
  `tmp/v833-down5-trace`，静态契约见 `doc/firmware/np560_resident_0d78d2_region_move.md`。
- v833 在同一游戏前台又完成多次向上移动：draw transaction 从 16 增至 22，地图稳定
  反向滚动且旧角色像素被 guest 清除，最终仍为
  `ROM_MISSING=none / UNSUPPORTED=none / INVALID_CONTROL=none`。中心确认键
  `M53/0x86` 也已由 modal consumer 确认，并使 draw/state-dispatch 分别增加 1，证明
  动作输入已经进入真实游戏控制器，不是 Web 热区。
- v838 已从升级包 source `4F:6062..60CF` 精确恢复完整的 `LINK #2` NPE 方向事件
  helper（`0x6E` 字节、38 条指令、2 个 direct call、8 个内部 AJMP）到不重叠 resident
  `1A:7B00`，并只把原始 ROM03 veneer `03:411C` 的目标重定向到该 guest code。内部
  AJMP 均按重定位后的同函数目标重写；QEMU 没有 HLE 返回、宿主 RAM 修补或虚构 CPU
  指令。此前把 source `4F:6062` 冷启动复制到运行期 `32:6062` 的错误别名已经删除；
  `32:6062` 只保留以目标现有字节为初值、随后接受 guest publisher 写入的 coherent
  窄窗口。
- 旧实验在第六、七键之间等待 `NPE_LOADER_EVENT CALLS>=50`，会让固件跑入另一条超时
  初始化分支，因而得到“按键不工作”和 `A2:2A4C=1201` 的假结论。原有成功快照与本轮
  冷启动复验一致证明七个边沿必须按正常连续节奏送出：
  `M55/B0 → M53/86 → M37/83 → M53/86 ×4`。v838 + v784 + 原始 v735 NAND 已在这条
  路线上自然进入真实游戏输入前台，初始地图 raw `gray5` SHA-256 再次为
  `5C2FBBB1453AE34DA4C2D7713997FD2345016829E1E0042E32E968C81BB5073D`；游戏 gate
  低位处于 ready，`GRID/INIT` 成对推进，且持续保持
  `ROM_MISSING=none / UNSUPPORTED=none / INVALID_CONTROL=none`。
- 当前同一次未重启运行已实测四方向和确认：下 `M37/0x83`、上 `M61/0x82`、
  左 `M45/0x80`、右 `M29/0x81` 均经过原厂 scanner、queue、wrapper、worker、
  `28:F6DE` 映射和 `1E:F8E4` modal consumer；四方向还实际经过 ROM03 veneer 和
  v838 resident helper，并增加游戏 draw/grid/state-dispatch，确认 `M53/0x86` 也被
  modal consumer 消费并触发 draw。首批方向取证启用了 `--capture-held`，在释放前写出
  大型状态文件，故触发了原厂长按连发并抓到滚屏中间帧；去掉 held capture 后左方向严格
  `MAPS=15→16`，证明一次物理边沿只消费一次，不是 guest 去抖错误。
- Web 的 `ArrowLeft/ArrowRight` 已据上述动态证据从早期菜单推测
  `M28/0x84`、`M20/0x85` 改为方向盘 `M45/0x80`、`M29/0x81`；Escape/Backspace 仍独立
  使用 `M28/0x84`。前端及矩阵路线定向回归合计 33/33 通过。
- 2026-09-01 的 F4 定向复测又闭合了一处真实 Harvard 指令来源：原厂调用
  `2E:BD98 → 33:6610` 时，flat `33:6610` 是另一函数的中段；实际 `NP560.PRG`
  `50:6610..6619` 是完整的十字节 `LINK #0 → SCALL 2F:D266 → UNLINK → RETS`
  wrapper。v838 QEMU 现在只把这十个不可变原厂字节映射到 `33:6610` 的 code view，
  不改同址 data RAM。修复后 `M4/0x8E` 不再从 `33:6654` 破坏返回地址，也没有新增
  `ROM_MISSING`、`UNSUPPORTED` 或 `INVALID_CONTROL`。
- `0x8E` 的语义已经由 source `37:1312` 和动态写轨迹交叉确认：在 operation 1 中它只把
  `52:7934` 从 1 改为 6，并把 `52:7AB4` 置 1；它不是单步“退出应用”。operation 6
  对应 source `4B:B5A0`，其 `0x84` 分支调用 `2A:572E ← 47:572E`，而后者按
  `52:7A54/7ABE` 更新操作列表/滚动区域，也不是返回主菜单。因此当前不得继续把 PC
  Escape、F4 或 F4→Escape 标作已确认的退出键。
- `M55/0xB0` 的游戏退出链已经由长、短两类运行区分清楚。游戏前台收到第一条真实
  `B0` 时由 modal controller 消费，并把 application state 从 `0x0078` 自然收尾到
  `0x00FF`；这一步本身不保证 LCD 主体已被桌面覆盖。600 秒长跑的旧验收只看到
  `00FF` 和 `DESKTOP_BLIT_TRACE 130→133`，实际 raw 帧仍是游戏地图加桌面底栏，因此该
  “通过”判定已撤销，不能再作为正常退出证据。若第一条 `B0` 后根 renderer 尚未运行，
  下一条同样经过矩阵的 `B0` 会由 root foreground 消费并绘制完整菜单。手工长跑复验的
  第二条 `B0` 使 `ROOT_RENDER_FLAGS 30→38`，主菜单随后持续稳定；没有写 guest 状态、
  宿主菜单跳转或 LCD 补画。
- `scripts/monitor_np560_npe_play_session.py` 已把退出门槛从“`00FF` + 任意 desktop blit”
  改为“`00FF` + `ROOT_RENDER_FLAGS` 增加 + 稳定等待后的最终 raw LCD”；它只在第一条
  `B0` 尚未触发 root renderer 时补发第二个真实矩阵边沿。v2 冷启动短回归连续运行
  21.141 秒、完成 10 次四方向动作，第一条退出 `B0` 本次已使 root render `30→40`，
  最终完整主菜单 raw `gray5` SHA-256 为
  `E7C9054F013962D2FC734CB92659098C53DF5ED0A514A4E08E867E64C012A128`；证据位于
  `tmp/v838-npe-exit-v2-smoke`。定向单元回归 19/19 通过。
- v2 已在同一冷启动 QEMU 实例完成“持续游玩 + 应用收尾 + root renderer + 稳定主菜单”
  的组合验收：600.0 秒内完成 120 次真实方向边沿和 10 个分钟 checkpoint，application
  state 全程保持 `0x0078`，且
  `ROM_MISSING=none / UNSUPPORTED=none / INVALID_CONTROL=none`。退出 `M55/0xB0` 由 modal
  原厂 controller 确认，状态自然变为 `0x00FF`；本次第一条边沿已经使 root render
  `30→40`，无需第二条，稳定等待 5 秒后的完整主菜单 raw `gray5` SHA-256 为
  `D8EC865ABBAAF4CBBC1BB14082C97554DC78CFB0DEAE3258829C3C3CAA3BBBF1`。初始游戏帧仍为
  `5C2FBBB1453AE34DA4C2D7713997FD2345016829E1E0042E32E968C81BB5073D`；完整 manifest 与
  每分钟帧证据在 `tmp/v838-npe-ten-minute-exit-v2-active`，定向回归 19/19 通过。
- 该冷启动在进入游戏的第六键后曾出现一次工具层 5 秒 release timeout；当时真实边沿
  已经 `mapped=True / acknowledged=True / path=modal`，只是 NPE 加载器暂停 scanner，稍后
  `KEY_MATRIX=0`、`2A5C=0`、`F160=00FF` 和递增的 `MATRIX_READS` 均证明释放已被 guest
  观察，游戏也正常进入。监控器默认 release timeout 已改为 30 秒以覆盖这种已确认的加载
  暂停，不改变物理保持时间或事件次数。首次失败 manifest 保存在
  `tmp/v838-npe-ten-minute-exit-v2`，不得把该工具时序超时记成 ROM/键盘故障。
- v840 又关闭了 operation 1 第一次动作的真实 Harvard 一致性故障。原始 caller
  `1A:141E` 调用 `29:CE22`；升级包 exact source 是 `46:CE22+0x298`，相邻 UI 初始化器是
  `46:D0BA+0x296`。guest `09:E000..F4C0` 安装器已完成 664 次 16 位写，但旧 QEMU 的
  instruction view 仍取到 flat `00A4`。最终保持 2 KiB target page，把
  `29:C800..CFFF` 建成完整 code-page RAM，复位时保留 `C800..CE21` 原 PRG 字节，只把
  实际 guest data store 的 `CE22..CFFF` 同步到 code view；`29:D000..D34F` 直接 alias
  连续 publisher RAM。该布局没有新增 subpage，也没有扩大 `PhysPageMap` 的 2048 section
  上限；不是 HLE、宿主返回值或新 CPU 指令。静态契约见
  `doc/games/np560_operation_one_action_overlay.md`。
- v840 同一冷启动已经显示像素正确的原生主菜单，代码总线快照为
  `29:CE22 = 05 2E ...`，七键路线 7/7 进入真实游戏地图，第一次动作得到
  `NPE_GAME_LINKED_LOADER=1 PC:29:CE22 W:2E05`，同时
  `NPE_GAME_UI_REENTRY=0`、`NPE_LOW51_EXEC=0`。随后 31.859 秒内完成 18 次真实四方向
  边沿，6 个中间 LCD hash 均发生变化；一次 `M55/B0` 使 application
  `0078→00FF`、root render `30→40` 并稳定返回完整主菜单。全过程保持
  `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL=none`。证据在
  `tmp/v840-coherent-npe-route`、`tmp/v840-coherent-npe-first-action*` 和
  `tmp/v840-coherent-npe-30s`。v840 定向测试、四项总线集成测试和 QEMU 重建已通过；
  新版本随后也完成 600.0 秒/120 个四方向物理边沿、10 个检查点和一次 Start 正常退出；
  状态 `0078→00FF`、root render `60→70`，检查点诊断全为 none，证据在
  `tmp/v840-coherent-npe-ten-minute`。
- v840 旧长跑的输入计数审计曾暴露测试驱动边界：120 个宿主物理边沿合计跨过
  121 次 candidate、125 次 map 和 125 次 consumer ack。新的原子
  `key-pipeline-status` 一次返回 candidate/map/两类 consumer ack、matrix reads/rearm、
  application state 和故障位；探针不再为每个游戏键下载完整诊断。监控器同时增加精确
  `--action-count`、落盘节流、输入静默门槛和 `--strict-single-edge`。
- 直接“等候 candidate 再释放”在第 362 个边沿抓到一次 1.48 秒意外长按，严格失败为
  `candidate/map/ack=2/2/2`；固定 50 ms 脉冲又被原厂消抖漏掉。最终采用仍经真实矩阵和
  原厂消抖链的 200 ms 物理脉冲。完整回归在 557.204 秒内完成 1,000 个方向边沿，四方向
  各 250 次，严格合计 `candidate/map/ack=1000/1000/1000`，10 个检查点为 10 个不同
  LCD hash；一个 `M55/B0` 使 application `0078→00FF`，2 秒原厂退出清理后 root render
  自动 `30→40`，无需第二个 Start，最终 hash 为
  `09b30a4ccdc1abd398b598b271d35221613847b86ad6c4c898132f2e79809b01`。证据在
  `tmp/v840-pulse-200ms-1000-v2/manifest.json`。
- Web Reset 已改为真实整机基线复位：恢复 16 MiB data RAM、operation action UI/code
  两个专用可写页，显式 reset 未挂入设备树的 DMCU CPU，并在 checkpoint 模式重载 NAND
  基线；raw nand-image 模式仍保留介质写入。动态复位后 IRQ request/entry/return 与
  matrix reads 都重新增长，完整主菜单两次回到 `STATE=00FF`。这关闭了旧
  `31:7822→E8:0000` 旧 PC/栈续跑和多次复位落入 `STATE=007E` 的问题。实现与动态
  证据集中记录在 `doc/cpu/np560_reset_and_input_stress.md`。

当前最近目标已从“动作首键崩溃”推进为完整游戏前台功能补齐：四方向严格短按、600 秒
持续操作、1,000 次单事件压力和 `B0` 正常退出/主菜单返回均已通过。动作键也已进入
原厂选择器；当前先关闭上述稀有 renderer callback 故障并找到一个非 `FFFF` 的真实动作
目标，再校准返回键/组合语义、音频和游戏存档路径。相关 Python/QEMU 定向回归当前为
51/51 通过。
每步持续检查首个新的 `ROM_MISSING`、`UNSUPPORTED`、`INVALID_CONTROL` 或像素不一致。
右下角时钟的 20 次变化及跨位边界验收也已经关闭：v838 连续捕获 `00:16..00:35`，
19/20 次取得“文字前单一背景、文字后保留背景并加入前景”的严格四阶段证据；首条按
收紧规则为 inconclusive，但完整矩形仍有清除/绘制且层间 0 mismatch。两个十位边界
`00:19→00:20`、`00:29→00:30` 均严格通过，20/20 back=front、GRAM=LCD，0 transient。
证据和限定见 `doc/display/np560_clock_raster_pipeline.md` 与 `tmp/v838-clock-20-v2`。

### 2026-08-30 历史检查点

本节覆盖下方按版本累积的历史判断；若旧条目与本节冲突，以本节和自动测试为准。

- Web 物理键盘输入层已经补齐：PC/pointer/touch、make/hold/break、同矩阵别名、组合、
  blur/hidden/pagehide 释放和 1.5 秒断网租约均已实现，代码级回归 16/16；64 个矩阵位的
  guest 独立短按覆盖为 64/64。尚未完成的是在真实 NPE 游戏前台验证长按重复频率、动作
  组合、返回/退出和 1,000 次压力测试，而不是继续补一套宿主菜单按键。当前应先让
  controller/layout 和菜单渲染链稳定、正确，再做完整键盘交互的动态验收；按键不应被
  用来掩盖仍未正确生成的菜单或列表。也就是说，底层和 Web 输入代码存在不等于用户要求的
  “键盘交互已经完成”：在真实 NPE 前台完成上述动态验收之前，本计划仍把完整键盘标为未完成。
- v750 已推翻“`31:590E` 时钟调用自身的 `30:8B26/30:3A56/31:8ABC` 释放链缺 ROM”
  这一旧判断：三次跟踪均完成去 pin、registry 节点移除和 bitmap 清位，`ACTIVE=0`；背景
  也已进入 `2D:CAA6 → 18:66EE` 后才绘制透明时间文字。五个相关函数在 v656/v750 中的
  live bytes 和映射相同且均为 exact，当前不得在这里补 ROM/HLE/ISA/Web 擦除。旧 v656
  的泄漏实际按 `27:58E4` 的 240×17 资源与紧随的 `31:590E` 时钟资源成对发生。新的
  64 槽只读 `RESOURCE_PAIR_RELEASE` 已在全新 v751 长跑到 `CALLS=65/ACTIVE=0`；完整保留的
  31 对相邻 footer/clock 调用 31/31 均完成八阶段释放，`mask1=1`、node 从 pinned 到移除、
  bitmap 清位，证明同号 handle 是释放后的正常重用。资源共同生命周期的 30 对门槛已经
  关闭，当前没有泄漏证据。四阶段 `CLOCK_RASTER_PIPELINE` 又在 v752 保留的 8 个周期中
  一致看到：文本调用前的 guest back-buffer 样区只含单一灰阶 3（`levels=0008`、前景像素
  为 0），透明文本调用后仍保留灰阶 3 并新增前景灰阶 15（`levels=8008`）。因此该样本支持
  “先恢复统一背景、再画文字”，而不支持“当前仍缺同一个清除函数”；不过观察范围只有
  40×8，不能外推为完整时间矩形已通过。最终仍须至少 20 次真实变化无残影，并覆盖一次
  `09:59→10:00`、`19:59→20:00` 或 `23:59→00:00` 多位边界；
  同时要求 guest back buffer、ST7529 GRAM、gray5 三层时间矩形一致，矩形外像素不变。
  v752/8796 的首个三层样本 `00:08→00:09` 在三层都只改变 3 个像素，最终 LCD 同时发生
  clear 和 draw，未见叠字；back/front、raw GRAM 和 LCD 坐标/极性现已归一，离线同帧
  GRAM↔LCD mismatch 为 0。监控器现要求绘字前只含一个非前景灰阶，不能再把“前景计数
  为 0 但仍有多灰阶残留”误判为清除，定向回归 21/21。按约 60 秒一次的可见刷新周期，
  90 秒窗口本来就只能期望 1–2 次变化；20 次的理论最短窗口是 1140 秒，完整周期预算为
  1200 秒。现有运行只取得 1/20 且未覆盖多位边界，仍不能标记为已修复。证据为
  `tmp/np560-v752-clock-20-changes-8796/manifest.json`。
- 本轮先闭合五处 QEMU Harvard/runtime 映射：`2E:2B6E+0x18A`、
  `29:D0BA+0x296`、`2F:B644+0x130`、`2D:F47C+0x196`、`30:6082+0x104`；随后又按
  原厂 source/target 证据加入浏览器 `33:384E ← 50:384E+0x22` 和
  `25:F992 ← 42:F992+0x3BA`。v745 又恢复 renderer 的真实 item callback
  `22:147A ← 3F:147A+0x51A`，以及本次确定路径仅缺的
  `2E:0192 ← 4B:0192+0x192`、`32:F0E0 ← 4F:F0E0+0x3E`。v747 再加入操作 1 专用的
  lazy casefold 闭包，v748 把前台 class-one event-state 调用固定到最终 guest lazy
  边界；v749 又补齐 `1B:299C` 的 19 项 computed-RET Harvard data view，v750 在
  ROM-01 最终 modal closure 中恢复 exact `23:70E0 ← 40:70E0+0x04A4`。当前
  当前 v756 overlay map 已增长为 builder 588、QEMU 706、missing 0、non-identical overlap 0，
  `NP560_LATE_OVERLAY_COUNT=633`，QEMU 已重新构建。实验性
  同址版本 v738、临时 resident-relocation v739，以及把 casefold 闭包在 ROM01 过早
  安装而破坏冷启动的试验版，都不得作为动态进展。
- renderer layout 的原厂生命周期已经重建：13 个原始 caller 调用的是 resident
  `0F:7E18`，而 `2C:7E18..9B94` 是其完整 `+0x1D` source image，不是要长期在 2C
  执行的第二份 controller。clean-room ROM 先固定恢复
  `0F:7E18..9B96 ← 2C:7E18..9B96`，并给 computed-RET 表
  `0F:7E92+0x1E` 提供只读 Harvard data alias；随后 guest 才把 exact
  `49:8744..8930` 安装到原目标 `2C:8744`。三个 renderer caller 保留原始
  `SCALL 2C:8744`，QEMU 为该窄窗口提供 coherent writable data/code backing。
- `0F:7E18` controller 本体边界已闭合（`0x1D7E` 字节、2,266 条可达指令、26 calls、
  0 unknown/overlap）。第一批三个 storage 分支及其后代已用 11 个 exact overlay 闭合：
  `2D:0B00`、`2A:8F26`、`33:1E22`、`30:09F2`、`30:BC4C`、`2C:682E`、
  `20:CE3A`、`30:E81A`、`2D:6070`、`2E:6822`、`32:DCAC`。第二批也已静态实现并进入
  builder、manifest、QEMU 映射和定向回归：
  resident `0D:B1C0`、resident `1E:9E66` 及九个 application 依赖
  `2D:622E`、`30:A0FC`、`28:7408`、`30:EE12`、`31:50D0`、`32:3E52`、
  `28:2844`、`32:E06C`、`2B:DB86`。静态实现不等于 Game World controller 全路径完成，
  更不等于 NPE 已可玩。
- v741、v742、v743 都已在同一次冷启动中经真实矩阵完成
  `M55/0xB0 → M53/0x86 → M37/0x83 → M53/0x86`，四步均有 map、foreground ack 和
  release，application state 自然到 `0x0078`，且
  `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL` 均为 none。v742/v743 的 LCD 仍只有残缺页面；
  同步抓取的 guest back/front buffer 自身也已缺少目录内容，证明当前缺帧首先发生在 guest
  对象/布局/绘制链，而不是 Web 呈现层。`33:384E` 与 `25:F992` 两处 exact 修复都没有单独
  改善画面，因此只能记为必要的错误调用边界修正，不能宣称其中任一处就是最终根因。当前应
  继续从 exact renderer 的间接回调/子对象迭代取得首个真实差异，不得由 Web、显存或 RAM
  补画 `英雄传奇.NPE`。
- v744 先把 resident renderer `1D:83DC` 的调用从冲突的 flat `33:1BBA` 改到现有 exact
  `5F:1BBA ← 50:1BBA+0x2C`。旧目标从前一条指令的扩展字中间进入，无 `LINK` 却执行
  外层 epilogue，导致整个 item loop 被提前退出。干净四键重放后，逻辑 callback
  `22:147A` 从 0 次精确变为 1 次，证明这一因果链成立；对象中实际字段仍是
  `+0x1E=22:147A`、`+0x22=28:DDA6`，`23:147A` 从未命中，禁止再把 callback 猜迁到 23。
- v745 已恢复上述 `22:147A` item renderer callback 及两个确定子依赖，并在干净冷启动中仅用同样四个
  真实矩阵边沿自然进入 `APPLICATION_STATE=0078`；四键均完成 map、foreground
  acknowledgement 和 release，且 `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL` 均为
  none。renderer call/return 为 1/1、layout=2、helper=1；guest front/back buffer 首次
  一致地产生原生文件浏览器框、边框和右侧滚动条，LCD 只是忠实呈现。这证明已经越过
  “仍停留在娱乐子菜单/浏览器外壳未绘制”，但内容区目前只形成 `..` 记录的两个点，仍无
  `英雄传奇.NPE`。因此不能称列表已 materialize、文件已选择或游戏已启动。`1D:831E`
  是按既有 item count/stride 迭代的通用 list renderer，`22:147A` 只是逐项绘制 callback；
  本轮 callback 仅调用一次，说明进入 renderer 之前的列表模型本来就只有一个 `..` item。
  v745 当时的第一边界位于上游的“目录记录解码/过滤 → item 数组与计数 → `1D:831E`”
  materialization 链，而不是 Web、按键、浏览器外壳或 callback 内部；该边界随后已由
  v746/v747 推进。
- v746 的只读 materialization 追踪已经越过上述边界：目录枚举器确实取得
  `英雄传奇.NPE`，但它在 `27:CBE4` 被拒绝；旧画面中的唯一 `..` 不是正确过滤结果，
  而是缺失 `31:5246` 使该 frame 被异常吞掉（可见 `31:53B8 → 29:98C2` 异常返回）。
  静态边界确认 `31:5246 ← 4E:5246+0xBA` 是完整独立函数，并依赖 exact
  `33:430A ← 50:430A+0x1C` 与 `33:45A2 ← 50:45A2+0x1A`。
- v747 没有在冷启动阶段覆盖这组三个共享目标，而是在 resident `06:6A10` 的 guest
  lazy wrapper 中，仅由操作 1 的原始调用点 `33:3DB8` 首次进入浏览器前安装 exact
  casefold 闭包，再尾跳 `1B:23B8`。这样既保留了冷启动桌面
  `APPLICATION_STATE=00FF`，也没有用 HLE、RAM/list patch 或 Web 补画。随后只用四个
  真实矩阵边沿 `M55/0xB0 → M53/0x86 → M37/0x83 → M53/0x86` 自然进入
  `APPLICATION_STATE=0078`。只读证据中的路径为 `0:\应用程序\*.npe`、模式为
  `*.npe`；三个候选的过滤结果依次为 `0/0/1`，其中 `英雄传奇.NPE=1`，最终唯一
  item count=1 的身份已经证明是 Hero，而不是 `..`。证据目录为
  `tmp/np560-v747-hero-four-key-route/`。这只证明 guest 列表 materialization 已正确
  形成唯一 Hero 项；仍须确认其原生 LCD 渲染、选择 descriptor 并越过 NPE loader，
  当前不得宣称游戏已经启动或可玩。
- v748 在 exact decoder `2F:C216 ← 4C:C216+0x12C` 的 ROM-01 最终安装边界，只把
  其中唯一的 class-one 调用点 `2F:C304`（原始 `SCALL 2C:D350`）改为
  `SCALL 06:4B00`。resident `06:4B00` 仍是普通 DMCU guest code：它在事件真正到达时
  才安装完整 exact `2C:D350 ← 49:D350+0x1E0` 闭包并尾跳处理器，不在冷启动阶段覆盖
  共享 overlay，也没有 HLE/host/RAM 状态补丁。第五个 `M53/0x86` SelectHero 事件的
  只读 trace 已完整显示
  `2F:C304 → 06:4B00 → 2C:D350 → 2F:C308 → 2F:C340 → 11:17F2`，
  `TYPE=1/CODE=0x86/RESULT=1`，说明 event-state 回调和 decoder 现在都正常返回。
  可重复证据在 `tmp/np560-v748-hero-select-route/`；v748 ROM SHA-256 为
  `63CE8669280AD8C8E3680B09262C680DECC7054F32FD2B5172B4FD8C97CAE222`。
- v748 的 `1B:0154/WORD=3F7E/SP=FFE0` 已降为历史症状，不是待补 CPU 指令。只读控制流
  证明真正首个错误是 `1B:299A/C600 RET → 1B:0000`：resident operation 的 19 项
  近跳表 `1B:299C..29C1` 只存在于 code view，data bus 读成 0。v749 增加窄只读
  Harvard alias 后，同一第五键动态得到 `1B:299A → 1B:29C2`，正常进入
  `1B:29D2 → 2F:B644`；`3F7E` 经专利指令表、解码器和 QEMU executor 三方审计确认
  不是合法扩展指令，禁止为它新增 ISA 语义。
- v749 随后在 `2F:B6AA → 23:70E0` 跳入 flat 资源数据并停于
  `23:70FA/WORD=BE00`。same-PC source `40:70E0..7583` 已证明是完整的
  `LINK #9 ... UNLINK/RETS` 函数（`0x04A4` 字节、412 条可达指令、32 calls、0 个
  unknown/overlap），而 `40:7584` 已是下一独立函数。v750 只在原厂最终装载生命周期中
  用普通 guest byte-copy 安装这段 exact 函数，并给目标提供 coherent writable
  code/data backing；没有修改 `2F:B6AA`、CPU ISA、HLE、RAM 状态或 Web。
- v750 冷启动五键重放中，前四键仍全部完成 map、foreground acknowledgement 和
  release；第五个 `M53/0x86` 也被 modal consumer 接收。动态栈已证明
  `2F:B6AA → 23:70E0 ... 23:7582 RETS → 2F:B6AE` 正常闭合，旧
  `23:70FA/BE00` 消失，且 `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL` 均为 none。
  继续回溯已证明 `2A:D840 → 31:4200` 读到的 `+0x0F=FF` 不是合法对象字段，而是更早
  `23:7100 → 30:2966` 落入无 `LINK` 的函数中段后，借用上层 FP 拼出的伪 far pointer。
  exact source `4D:2966..2A77` 是严格 `0x0112` 字节的完整 `LINK #5 ... RETS` 函数，
  只调用已 exact 的四个依赖，不调用 `2A:CA24`、不读取 `+0x0F`、也不进入 `31:4200`；
  目标范围当时无 overlay/manifest 冲突。v751 已只恢复
  `30:2966 ← 4D:2966+0x0112`，使用构建时嵌入的 immutable PRG words 和 coherent
  writable code/data backing，未补字段、循环、ISA、HLE 或 Web。干净五键动态确认
  `30:2966 → 33:269E → 25:206E → 33:1A02 → 33:4342 → 23:7104` 完整返回，且旧
  `30:2A2C/2A:CA24/2A:D82E/31:4200` 命中数均为 0。v751 ROM SHA-256 为
  `C6E21B8D1BDB0E21B6BF0CB530FD6D7AA9DE82E7B87E6ABD953739DCBB14B38A`；证据在
  `tmp/np560-v751-hero-select-route-clean/05-SelectHero-failed.json`。第五键随后推进到
  `2F:B6DA`；其 far call 正常，但 v751 的目标 `1B:7A20` 仍是连续 `TRAP #0`。source
  `38:7A20..8295` 已证明是严格 `0x0876` 字节的完整 `LINK #0x21 ... UNLINK/RETS`
  函数，下一函数从 `38:8296` 开始。这个 v751 边界现已由 v752 关闭。v751 对应 QEMU
  SHA-256 为
  `9BEEE5EF34D7B6644967E90504C3A04F8B6AF8FB0C29FE3AE3FE2A321B63AB1E`；本轮 71 项
  定向回归、`py_compile` 和 `diff --check` 通过，但 258 项全量第二次干净运行尚未完成。
- v752 已把 `1B:7A20 ← 38:7A20+0x0876` 作为 exact reconstructed resident function
  固化，并只重定向三个已证明冲突的 SCALL：Hero 必经的 `1B:7AA2 → 5F:380A`
  （exact `50:380A+0x22`）、旧格式分支的 `1B:7E8A → 5F:6A9C`
  （exact `4D:6A9C+0x102`），以及复用既有 exact `1B:7EA2 → 5F:1BBA`。两个新 5F
  helper 由最终 guest installer 写入 coherent code/data backing；没有 HLE、猜返回值、
  CPU 指令扩展或 Web 状态补丁。补丁后的主函数 SHA-256 为
  `D955C238BBC6082DB9AD075442D2EE89A76B70A246387BFBC6D5E922C5192AA7`。
- v752 在隔离端口 8796 的干净五键重放已经让
  `M55/B0 → M53/86 → M37/83 → M53/86 → M53/86` 五步全部完成 guest map、consumer
  acknowledgement 和 release；第五键由 modal consumer 正常接收，最终
  路径进入 `APPLICATION_STATE=0078`，且 `ROM_MISSING/UNSUPPORTED/INVALID_CONTROL` 均为 none。
  证据位于 `tmp/np560-v752-hero-select-route/route.json` 和 `05-SelectHero.json`。这证明
  `1B:7A20` 不再 trap 或破坏返回栈。随后新增的严格只读 `NPE_FORMAT_DISPATCH` 已在第二次
  干净五键重放给出实际结果：entry 1，`1B:7AA2 → 5F:380A → 1B:7AA6` 为 1/1、返回
  `R0=001F`；三次 compare 返回分别是 `FFFD/FFF3/FFA2`，所以 `1B:7BAE` status-2 site
  命中 0，`1B:8294` 以 `R0=0` 正常返回 `2F:B6DE`，`2F:B726 → 1F:D1A6` 命中 0，随后
  自然回到桌面。legacy `53:*` 和 `1B:7E8A/7EA2` 仍全为 0。当前真实边界因此前移到
  “三次比较所见的常量数据生命周期”，不是 1F 下游，也不是新 ROM missing。实参观察器
  已证明三次左侧均为真实 `NP560 RPG2.1` 文件头，右侧分别读取
  `32:496E/12`、`32:4960/12`、`32:4956/9`，但读到的是 flat bank 32 的指令字节；精确
  常量源是 `4F:4956+0x26`。证据在
  `tmp/np560-v752-format-dispatch-route/post-route-diagnostics.txt`。
- v753 曾把 `4F:4956+0x26` 做成永久只读 Harvard data alias。静态 source/target/hash 和
  overlay-map 回归全部通过，但隔离端口 8796 的冷启动立即回归：root state 在 `00FD`
  循环、`ROOT_OBJECT_FAIL` 持续增长、NAND 读取超过百万次，无法到达桌面；v753 ROM 二进制
  与健康 v752 完全相同。当时把相关性误报成了唯一因果；随后撤销 alias 的重试也进入同一
  root loop，且失败前 `NPE_LITERAL_DATA=READS:0 WRITES:0`。因此现有证据没有证明启动期
  guest 访问或复用这 0x26 字节。后续 A/B 又确认这些失败启动误用了原始 `NP560.PRG`，
  而健康 v752 基线使用的是 `NP560-runtime-source-patched-v655.PRG`；不能再把该现象写成
  NPE alias 或近期 QEMU observer 的因果证据。永久 source alias 仍不作为最终实现：它
  绕过了原厂应用装载生命周期。当前保留
  独立、定长、只读的 `NPE_LITERAL_DATA` 访问监控，并采用更窄的 guest 方案：保持
  `32:4956+0x26` 为普通可写 data backing，仅在 `1B:7B26` 第一次 memcmp 前由 DMCU wrapper
  调用原有 far-copy 安装 exact 常量，再尾跳真实 `2C:C07E`；禁止强制返回或宿主代写结果。
- v754 把上述生命周期方案实现为普通 guest DMCU 代码：只将 `1B:7B26` 的原始
  `SCALL 2C:C07E` 改到 resident `06:6B20` wrapper；wrapper 保存寄存器，调用原有
  `08:43A6` far-copy，把 exact `4F:4956+0x26` 复制到目标 `32:4956+0x26`，随后尾跳回
  真实 `2C:C07E`。静态回归固定了 wrapper/copy/return/tail 四个边沿、38 字节目标读写和
  原始三次比较参数。一次使用原始 `NP560.PRG` 的隔离启动还暴露了三处旧的“source pin 依赖
  预补丁 PRG”耦合：`25:5858+0x3F6`、`5F:661A+0x0A`、`5F:13F8+0x30` 都会被 guest
  写入或重定向，取指却分别固定到 `42:5858`、`50:661A`、`50:13F8`。现已让这三段
  code/data backing coherent；未修改的 call-free child `5F:6DA0 → 4F:6B58` 仍保持 exact
  immutable source。使用原始 PRG 的逐层 A/B 依次把 record callback 从 `33:661A` 修到
  `5F:661A`、容量从错误的 `0000:53B7` 修到 `1BB4:0000`；使用历史健康输入
  `NP560-runtime-source-patched-v655.PRG` 的最终 v752 对照已重新得到
  `APPLICATION_STATE=00FF`、range `0F00..0FFF`、root fail=0。逐字节复核同时证明 v655
  原本就在三个 source 地址预镜像了同样的目标，因此这不是近期 NPE observer 引入的回归；
  coherent 改动的价值是让 guest 写入语义不再依赖预补丁 source。
- v755 的动态跟踪找到了 v754 最后一个硬件语义错误：宽泛的只读 `program-nor` data alias
  覆盖了 `32:4956..497B` 的底层 RAM，使 far-copy 的 38 次写入在总线上可见却没有保存。
  现已为这 0x26 字节建立仅 data view 可写的有界 Harvard RAM 窗口，code view 仍保持原 flat
  PRG；没有永久 source alias、上电 seed、HLE 或强制比较结果。干净五键重放得到
  `NPE_LITERAL_DATA READS=14/WRITES=38`，三次比较为 `FFFC/FFFE/0000`，`1B:7BAE`
  status-2 命中一次，`1B:8294` 以 `R0=0002` 返回，随后自然进入
  `2F:B726 → 1F:D1A6`。这已经动态关闭“常量安装/status-2”边界。
- v756 又关闭了 status-2 后的第一个 flat collision。ROM03 跳表把
  `1F:D1CA → 03:4128` 的目标从冲突的 `32:F38A` 精确重定向到 `5F:F38A`，该窗口由
  guest installer 写入 exact `4F:F38A+0x003C` 并保持 code/data coherent。动态控制流已经
  证明 `1F:D1CA → 03:4128 → 5F:F38A → 1F:D1CE` 正常返回；旧的
  `32:F400 → 10:D019` 和 `10:E58D/AAAC` 异常链消失。当前首个真实边界前移到
  `1F:D210 → 32:CEEE` 内部的 `32:CF7C RETS → 1F:4D59` 错误返回；下一步只恢复这条
  动态可达闭包，不回退重做已经通过的常量或 `F38A`。
- status-2 后的剩余静态传递闭包按当前证据排序为：resident
  `14:E742 ← 31:E742+0xFC6`、当前冲突 `32:CEEE`、现有 relocated `5F:C1A6`、
  `24:ACBA`、`31:71D2`，再到 operation-7 的 `2B:0DA2`。Hero 必须在 `14:E742`
  走 handle 非零和版本字节 `0x31 != '0'` 两个分支，并保持全局错误字 `52:7A3C=0`。
- `53:0020/0024/0028` 已静态证明是旧 `NP560 Ver1.0`/`NP580 Ver1.0` payload 装入
  segment 53 后才存在的运行时入口，不是应补进 resident ROM 的三个静态服务。真实
  `英雄传奇.NPE` 文件头为 `NP560 RPG2.1`，应在第三次 9 字节比较后返回状态 2，正常
  Hero 路径不应命中任何 `53:*` 入口；以后若兼容旧格式，应实现完整 writable coherent
  segment-53 code/data RAM 生命周期，禁止安装三个静态 stub。
- v736 对 `obj+0x12` 的“有效标志 producer”解释已经推翻。`1B:23B8` 的 render object
  `FP-0x28` 中 `+0x10..+0x13` 是允许为 0 的四字节 range pair；真正 controller 对象是
  外层 `2F:68A2` 的 `FP-0xC4`，其 ctor 会按原厂分支正确写自己的 `+0x12`。两者不是同一
  对象，禁止调用无关 `1C:7052`、使用 D01C 或把字段强制补 1。
- NPE 最终验收顺序固定为：v751 已恢复 exact `30:2966 ← 4D:2966+0x0112` 并越过
  错误栈帧边界 → v752 已关闭 `2F:B6DA → 1B:7A20` 未物化边界 → 用只读轨迹确认
  `NP560 RPG2.1` 的三次比较实参/字节视图，拒绝绕过生命周期的永久 source alias，并在正确 guest
  生命周期安装 `4F:4956+0x26`；v755 已使 status-2 分发和
  `2F:B726 → 1F:D1A6` 下游自然出现，v756 又已越过 relocated `5F:F38A`，当前停在
  `32:CEEE/CF7C` 返回链 → 继续闭合真实 loader/runtime → 只用完整矩阵键盘沿
  `开始 → 娱乐 → 游戏世界 → NPE 游戏 → 英雄传奇.NPE` 选中它 → 命中
  `1B:2A88 → 2E:D34A → 30:C370/30:C99E → 18:21F4` → 显示真实游戏首帧 →
  连续至少 10 分钟真实矩阵操作 → 验证必要计时/音频/存档 → 正常退出回主菜单。当前
  已越过 v748/v749 的 event-state、computed-RET、action-function、v750/v751 的错误
  函数体、v751 的 `1B:7A20` trap、v755 的 status-2 和 v756 的 `F38A` collision；当前已经
  进入 status-2 后的 loader，但尚未显示游戏首帧，也未通过游戏交互或可玩验收。

### 已完成

- [x] QEMU DMCU target、主要指令、Harvard code/data 地址空间和运行诊断。
- [x] NP560+ machine、PRG/NOR、SRAM、程序覆盖窗口和 resident ROM 映射。
- [x] ST7529 命令/数据接口、240×120 灰度 LCD、bottom-up COM 映射。
- [x] NAND 2048+64 页面、OOB、擦写、完整 checkpoint 和 ECC 单比特纠正路径。
- [x] 8×8 物理键盘矩阵、GPIO 扫描和原厂三张 64 项事件表。
- [x] Web LCD、键盘、QMP 控制及只读诊断前端。
- [x] V3.80 升级包解析、burner、driver 和 PRG 反汇编工具链。
- [x] 223 个以上当前已恢复 runtime modules 的装载和覆盖映射；数量会随逐入口恢复继续
  增长，manifest 和自动测试是准确清单，不再把旧的固定计数当完成条件。
- [x] 严格路径始终使用 `ROM_HLE=off`；每个被宣称闭合的范围都要求
  `UNSUPPORTED=none`、`INVALID_CONTROL=none`。闭包正常返回后遇到的第一个
  `ROM_MISSING` 或 `UNSUPPORTED` 必须明确记为下一处真实边界，不能用强制返回绕过；
  v748 的 `1B:0154/WORD=3F7E` 正按此规则保留。
- [x] v658 重建 ROM + v659 factory-page lane 诊断 NAND + source-patched PRG 路径可以
  显示 240×120
  主界面；顶栏“学习、辞典、网络、记事、系统”、左侧菜单、开始按钮和时间已经
  可辨认且像素对齐。这里的 source-patched PRG 是必要启动产物：Harvard 指令视图固定
  到原 PRG 源，guest 对 runtime 目的地址的最终代码写入必须由
  `mirror_np560_runtime_patches.py` 同步回对应 PRG 源地址。
- [x] v717/v719 建立了第五个确认事件的 modal 分派 ABI；v748 又在当前 canonical
  ROM 的最终 overlay 生命周期中复验并固定该链：exact decoder
  `2F:C216 ← 4C:C216` 得到 `TYPE=1/CODE=0x86` 后，经 resident wrapper `06:4B00`
  懒加载并执行 exact `2C:D350 ← 49:D350` 处理器；随后为 `11:18D4..18EF` 的 14 项
  `0x80..0x8D` RET 跳表增加窄只读 Harvard 数据别名。v748 trace 中
  `2F:C304 → 06:4B00 → 2C:D350 → 2F:C308 → 2F:C340 → 11:17F2` 完整返回。
  这里只完成了事件处理链；随后在 `1B:0154/WORD=3F7E/SP=FFE0` 的停止属于下一边界，
  不代表已经进入 NPE loader。

### 尚不能作为最终结论的部分

- 当前正确主菜单绑定特定重建 ROM 和 NAND checkpoint；v654 的页面 lane 修复尚未
  被证明能由原厂烧录/读取流程自然产生。
- `soc-rom-skeleton=on` 仍用于在进入未知 resident 区域时严格停止。
- `01:0200` late loader 的原始顺序、application-state guard、应用退出后的 resident
  manager/selection policy 仍有推断。
- R2 已证明携带退出事件 `0x82/0x83/0x84/0x85`，但 factory manager 如何结合持久
  状态选择下一个应用仍未知。
- 主菜单已显示，但“物理按键 → guest 菜单状态 → 选中项重绘 → 启动应用 → 返回桌面”
  还没有形成最终验收闭环。
- 8×8 矩阵、事件表和扫描链已有实现；Web 现已把实体按钮、PC `keydown/keyup`、
  pointer hold、组合键和同矩阵别名统一成真实矩阵电平，并在失焦、页面隐藏和断开租约
  超时后自动释放。代码级状态机与竞态回归为 16/16 通过，但 NPE 游戏前台的长按重复
  频率、返回/退出语义和 1,000 次压力测试尚未通过；因此“输入前端已补齐”仍不能等同于
  “游戏已经可完整交互”。
- 2026-08-29 首次端到端方向键实测已证明输入到达 guest：Web `ArrowDown` 产生
  `matrix_high=0x20`，原厂扫描/映射链返回事件 `0x83`，随后经过前台 decode/change
  路径，并间接调用对象表 `50:1436` 发布的 resident 回调 `0F:2094`。该回调已从
  `2C:2094..40B1` 完整同 PC 还原；v656 的最早停止点从缺失 `0F:2094` 前移到
  `0F:2130 RET → 0F:0000`。
- 对 `0F:2094` 以两张内联表的全部目标为种子做递归控制流解码后，函数体只有两个
  非代码间隙：`0F:2132..213F` 的 7 项 `0x80..0x86` 表，以及
  `0F:2194..21A3` 的 8 项 `0x8E..0x95` 表。停止原因已确定为 Harvard 数据总线未
  映射这两段 reconstructed-ROM 常量，而不是 CPU `RET` 语义；QEMU 已加入两段窄
  数据别名。冷启动复验中，`ArrowDown`/`ArrowUp` 分别产生 `0x83`/`0x82`，左侧选中
  项依次从“同步学习”移到“多科助考”、再回到“轻松学堂”，LCD 帧随 guest 重绘，且
  `ROM_MISSING=none`、`INVALID_CONTROL=none`，原 `0F:0000` 故障已经消除。
- 同一复验还纠正了确认键映射：索引 20 是方向右 `0x85`，而 resident 表对 `0x85`
  无操作；索引 53 才返回确认/激活事件 `0x86`。实测 `0x86` 经过 `0F:3906` 将选中
  项状态从 `0x00FF` 改为 `0x0018` 并进入启动清屏，因此 Web `Enter` 已从索引 20
  改绑索引 53。该应用随后仍停在空白帧，属于下一段启动/应用闭环卡点，不能算应用
  已成功启动。
- 独立“开始”硬键已确认为矩阵索引 55、事件 `0xB0`：三张原厂键表在该位置一致，
  端到端实测后 `PENDING` 从 0 变为 1，而主菜单帧暂未切换。这证明按键模型与菜单
  请求已经到位，当前阻塞在 resident manager 对 pending 请求的消费/生命周期切换。
  Web 已增加“开始菜单”按钮并直接绑定索引 55；不得再用启动时预置 `0xB0` 代替正常
  开机主界面。
- 2026-08-29 的 v690/v691 已把开始菜单链继续闭合。v690 先按原厂数据总线关系恢复
  resident `13:0A3E ← 30:0A3E` 的 17 项主动作事件表；运行跟踪证明事件 `0x8E`
  从表偏移 `0x1C` 取得原厂目标 `30:12DE`，旧的表填充值递归已经消失。随后确认
  `31:65B4` 把 flat `24:11BE` 当函数调用，但该地址实际位于另一函数中间，其局部
  缓冲清零会覆盖自己的近返回地址；同 PC 原厂源 `41:11BE..41:1340` 是完整
  `LINK #3/UNLINK/RETS` 函数（146 条可达指令、7 个外部调用、0 个未知前沿）。v691
  仅安装这段闭合的 0x184 字节 exact overlay，未修改内存填充、栈或返回地址。
- v691 在稳定桌面上通过真实矩阵索引 55 复验：guest 映射 `0xB0`，完整执行
  `32:F15C → … → 31:65B4 → 24:11BE` 并正常返回，开始窄菜单已由 guest 可见绘出；
  静态区变化 4370 像素、`START_POPUP=1`，且 `ROM_MISSING=none`、
  `UNSUPPORTED=none`、`INVALID_CONTROL=none`。旧 `30:FEDE → 30:0000` 和
  `30:130C → 00:0000` 均未复现。v691 ROM SHA-256 为
  `F7E3BEE1A6F5054A0A508DC55D607084A7F27E54B0FFBDA8B87DE042EE456BBE`；可见证据为
  `tmp/np560-v691-start-before.png` 与 `tmp/np560-v691-start-after.png`。这完成的是
  “开始菜单可见”里程碑，不代表完整键盘或 NPE 游戏已完成。
- v691 的轻量只读按键边沿监控已消除诊断轮询造成的长按重复：QEMU 只读暴露累计
  映射次数与最近事件，Web `/api/key-status` 只读取这两个有界字段；自动探针在观察到
  第一次正确事件后立即释放矩阵键。一次干净运行中，开始、确定、下、确定分别只产生
  `0xB0`、`0x86`、`0x83`、`0x86`，每一步映射计数只增加 1，`A2:2A5C`
  门控均恢复为 0。guest 已沿真实菜单进入“娱乐”，选中并打开“游戏世界”；对应证据为
  `tmp/np560-v691-start-entertainment-clean.png`、
  `tmp/np560-v691-game-world-selected-clean.png` 和
  `tmp/np560-v691-game-world-entered-clean.png`。
- 2026-08-30 对 v719 启动期 `fopen` 的只读追踪纠正了此前的 GBK 转录和因果判断。
  原始路径字节为
  `30 3A 5C CE D2 B5 C4 D3 CA BC FE 5C 6E 6D 69 6E 62 6F 78 2E 70 69 6D`，
  即 `0:\我的邮件\nminbox.pim`；“同步学习”的 GBK 字节实际是另一组
  `CD AC B2 BD D1 A7 CF B0`。该 mode-1 打开及失败弹窗在没有任何矩阵输入时已经发生，
  后续才因 modal 生命周期/重绘污染覆盖到菜单画面。因此不能再用这个弹窗证明
  “游戏世界”选错了描述符；脚本 route label 仍只表示测试意图，最终仍须以选中对象、
  operation ID、路径、LCD 和 NPE 列表五者一致验收。
- v692 已把“游戏世界”页面原先看似乱码的 resident 诊断链还原为可读原文。精确证据
  是：页面 renderer `18:4E62` 的标题参数为 `27:E066`，动态正文为 `51:4E5E`；同链接
  `44:E000..E07D` 是完整提示/路径字符串岛，`27:E07E` 起的后半池此前已恢复。QEMU
  只增加 `27:E000..E07D ← 44:E000..E07D` 的 Harvard 数据视图，不改同址指令流。
  随后恢复正文短/双行分支调用的 exact `2F:0000 ← 4C:0000`，范围严格为
  `0x0158` 字节（`4C:0158` 是下一函数）。真实弹窗正文现为
  `无此目录:0:\应用程序,请创建!`，而不是 NPE 列表；可见证据为
  `tmp/np560-v692-game-world-missing-directory.png`。v692 ROM SHA-256 为
  `8057EE0EB4BFFA9E62BB91D9F1D5E4A1D9AF4FA85982BE46D8174E6F98E020AB`，该路径仍为
  `ROM_MISSING=none`、`UNSUPPORTED=none`、`INVALID_CONTROL=none`。下一阻塞已经明确
  移到 NAND 文件系统缺少/未解析出 `0:\应用程序` 目录记录；不得在 Web 或 guest RAM
  中伪造该目录。
- 对 V3.80 升级包 slot 3（`MASKROM NP560 VER3.65`）的原始逻辑页流和 v691 checkpoint
  已完成双向内容扫描。升级包中的四处 GBK“应用程序”分别位于逻辑页
  `184E:4A1`、`1E2B:16D`、`273E:0BF`、`2939:7C3`，在 checkpoint 中逐字映射到物理页
  `0BEE:6A1`、`0F0B:36D`、`139E:2BF`、`149A:1C3`；上下文分别是计算机词典正文、
  import 术语、Winsock 说明和词条索引，不是目录项。升级包没有命中原厂 loader 要求的
  `NEPLAYERV0.98/0.99`、`NEPLAYER` 文件头、`.nwf` 文件路径或 `.npe` 文件名；唯一
  `.nwf` 命中是帮助正文“多媒体，扩展名为*.nwf”。当前 checkpoint 的
  `NEPLAYERV0.99`/`0:\lirt.nwf` 来自仓库的最小测试容器，不是原厂游戏。证据输出为
  `tmp/np560-upd-slot3-file-signatures.json`、`tmp/np560-v691-file-signatures.json`、
  `tmp/np560-v691-ftl-maskrom-map.json`。因此升级包目前不能作为“已拥有真实 NPE 游戏”
  的证据；最终样本必须另从可校验的原厂内容包/备份取得，或找到升级流内仍未识别的封装
  并证明它能还原出上述原始文件头。
- 2026-08-29 已静态解码原厂 resident 操作表 `4D:0B0C → 30:0B0C`：操作 0 的目录/
  过滤器是 `0:\动漫欣赏`/`\*.nwf`，操作 1 是 `0:\应用程序`/`\*.npe`。“游戏世界”
  应用代码 `0x0078` 经 dispatcher `3F:3C2A → 22:3C2A` 到 wrapper
  `50:3DA6 → 33:3DA6`，明确向通用浏览器 `1B:23B8` 传入操作索引 1。选中文件后，
  `38:2A88 → 1B:2A88` 把 descriptor 交给 `4B:D34A → 2E:D34A`，后者依次调用
  `30:C370`、`30:C99E` 和 application launch manager `18:21F4`。这已证明 `.npe`
  走 guest 原厂文件浏览/启动链，但 NPE 文件头、装载器、入口 ABI 以及是否内嵌/引用
  NWF 仍未知；证据由 `scripts/analyse_np560_operation_catalog.py` 生成。
- 2026-08-29 已继续跟踪 `0xB0` 后的 resident manager：状态导入器对真正的按键记录
  `0003,...,00B0,...` 返回回调 `32:F15C` 到 dispatcher 的 `28:84D0` 分支。早期运行中
  同时出现的 `0107 → 27:571A/28:83E6` 与 B0 顺序不稳定，因此当时只能归类为并发
  通知；恢复正确的 Start 回调和 record handler 后，最新重放已经观察到 B0 完整返回、
  `A2:2AA0` 从 1 变为 0，随后新增 `0107 → 27:571A` 重建请求。现阶段仍需用有界
  因果跟踪证明两者的生产/消费关系，不能只凭时间先后把任意 `0107` 归因给 B0。
  `A2:2ABA` 的 pending 被置 1；旧阶段原来停在 manager 等待的一个已修复原因是
  `A2:2AB6` 的 resource flag 一直为 1。
- 2026-08-29 已查清 resource flag 的来源：`4A:7ED4` 以
  `length=1, source=10:D03F, output=FP-2` 调用 exact `25:206E ← 42:206E`。FTL 已正确
  映射逻辑块 `0xE9B → 物理块 0xC02`，页索引 `0x1A`、物理页 `0x3009A`，页缓冲和
  transfer window 内容也一致；但旧 checkpoint 把工厂标志 `0x01` 放在奇地址
  `51:187F`，guest 外部 A0 byte lane 实际读取 `51:187E`，所以得到 `0xFF`。
- 诊断 checkpoint `np560-v380-factory-page-lanes-v659.nand` 仅交换物理页 `0x3009A`
  的成对字节并重算 ECC，SHA-256 为
  `5DCA5D0088826D7F565C770795F713950734D39366F308BD1EC2034421E6F389`。使用它后
  factory flag 自然读为 1，`RESOURCE_FLAG=0000`、`PENDING=0000`、`STAGE=0001`，
  manager 继续到新的首个缺口 `18:4E62`；全程没有修改 CPU 读值或模拟 ROM 服务。
- `18:4E62` 已找到完整同 PC 原厂源 `35:4E62..35:5963`：入口 `LINK #0x4A`，
  804 条可达指令、44 个直接调用、0 个未知/保留控制流前沿，结尾为平衡
  `UNLINK/RETS`；caller `1A:DF80` 调用后清理五个 word（`0x0A` 字节）。v660 已按
  `0x0B02` 字节原样恢复，ROM SHA-256 为
  `2DAD34D24D470EBBC96129BDCA951149F09C95E5DD3C8F8572D653F07D8C8A1B`。冷启动后
  `ROM_MISSING=none`，并已观察到该函数内部 `18:5178` 的应用目录排序尾部自然执行；
  当前等待它完成目录整理并返回 manager，再以之后的新首个差异为准。
- 上述“目录排序”判断已被 v661 的精确控制流纠正：`18:5178` 实际调用逻辑
  `24:1F02` 进行六参数页面 raster copy；flat `24:1F02` 从另一排序函数中间的
  `POP REG[0x10]` 开始，所以旧 `SORTTAIL` 计数会无限增长。完整同 PC 源
  `41:1F02..41:2369` 为 `LINK #9`、398 条可达指令、0 子调用、0 未知前沿的闭合函数。
  v661 通过 resident `1A:CC80` 嵌入安装器和普通 Harvard code/data RAM 别名恢复后，
  该 raster 调用只执行一次并正常返回；因此这不是“启动较慢”，而是已修复的代码覆盖
  碰撞。
- v661 随后自然到达新首个缺口 `0D:8232`（caller `18:5616`，清理四个 word）。
  完整原厂源 `2A:8232..2A:8551` 是 call-free packed-nibble framebuffer compositor：
  `LINK #0x14`、298 条可达指令、0 未知前沿、平衡 `CRIT #0/RETS`。v662 已按
  `0x0320` 字节原样恢复，ROM SHA-256 为
  `94BF449B01B52E9C49A5573E45215C60A3C206CC4C5DA21E199531FBDEED0573`；下一轮以
  v662 冷启动后首个 guest 可见差异为准。
- v662 冷启动及真实矩阵索引 55（事件 `0xB0`）复验已越过旧的 `16:0030` 故障。
  根因不是缺少一条 CPU 指令，也不是应该复制 source `33:0000`，而是 exact
  `1A:DEAA ← 37:DEAA` 在 `1A:E036` 通过 Harvard 数据总线读取内联模式表
  `1A:E038`；未映射时读到 0 并误跳 `1A:0000`，最终把保存寄存器误当远返回帧。
  QEMU 现已为原 ROM 中的 8 字节表增加窄只读数据别名，四个原厂目标严格为
  `E040/E6CE/E6B6/E6C6`。修复后 `ROM_MISSING=none`、`INVALID_CONTROL=none`、
  `UNSUPPORTED=none`，不再进入 `16:0000..002F`。
- `0xB0` 后 guest 已把 `A2:2AAA` 从 `0x0001` 改为 `0x00FF`，将 pending 置 1，
  随后由 resident 生命周期消费为 0；这证明开始键已经穿过矩阵、扫描、映射和事件
  投递链。进一步反汇编已确认 `1A:DEAA` 的模式 3 分支 `1A:E6B6` 应设置返回结果 5
  并退出，而桌面 `20:2DE0 ← 3D:2DE0` 与该 resident 前台任务并行协作。现已加入只读
  `FOREGROUND_MODE`、`FOREGROUND_RETURN` 和 `ROOT_EXIT_STATE` 诊断。
- `32:136C` 的 overlay 原厂源已精确定位为 `4F:136C..13E2`。递归反汇编得到 41 条
  可达指令、7 个调用、0 个未知控制流；该函数只保存环境、调用 `1A:DEAA`、恢复环境，
  再把保存在局部变量中的 R0 原样返回。进一步对 caller `18:CFA8 ← 35:CFA8` 的精确
  反汇编已经确认：`18:D078` 调用该包装器后，`18:D07C` 会丢弃前台内部结果 5，完成
  handle 清理，并把最终 R0 改为 0 返回；因此结果 5 不是传给 resident manager 的公开
  返回值。manager 的切换由 `A2:2AAA/2ABA/2250` 等全局状态驱动，后续不得再沿“结果
  5 直接交给 manager”的错误假设推进。`monitor_np560_start_menu.py` 已能等待真实
  `ROOTRENDER`、注入矩阵索引 55 并保存前后帧及生命周期诊断；它不写 guest RAM，
  也不从 Web 直接选择菜单。2026-08-29 对前后原始帧复查后发现，旧脚本在
  `ROOTRENDER` 刚进入、最终桌面尚未完成时就注入了按键：before 帧仍是“系统初始化，
  请等待”，后来出现的“学习”列表可能只是正常启动完成，不能归因于 `0xB0`。脚本现改为
  先验证完整桌面边框/顶栏/左栏并在排除时钟区域后稳定 1 秒，再允许注入；回调命中、
  静态区域帧变化和开始菜单窄面板 golden 分开判定，不再要求第二次 `ROOTRENDER`。
- `18:CFA8` 的 owner `1B:23B8 ← 38:23B8` 也已完成静态闭环：operation context 最终以
  R0=0 返回 owner。桌面 `20:2DE0` 在 `20:3372` 检查资源计数 `A2:2250`；计数小于 2
  才退出并触发下一轮 root controller，计数达到 2 则回到事件循环。全新 checkpoint 的
  干净 v665 复验已纠正对象时序：资源计数两次递增、`51:27C6`、`51:2770`、回调
  `2C:A03A`/`24:162C` 以及活动对象 `51:4A46` 都在完整桌面出现之前完成，按下开始键后
  数量不再变化。因此它们是正常桌面初始化的两对象结构，不是开始键新建的 modal 对象。
- v664 的第一次 `0xB0` 因注入过早而无效；全新 checkpoint 的 v665/v666 已在完整桌面
  静态区域稳定后重测。`0xB0` 在 `20:2DE0` 被解码并经 `22:FD9E` 入队，随后由
  `29:24C6` 弹出并交给 `1F:F470`。v669 一度把相邻的 `0107 → 27:571A` 通知误认为
  B0 自身的状态结果；`27:571A` 的 exact source `44:571A` 虽然确实以 mode 1、
  `51:4A46` 重建当前“学习”页，但这不能解释开始键。
- v670/v671 新增只读 `STATE_IMPORT_HISTORY` 八项环，并在同一稳定 NAND 的全新副本上
  分离冷启动与按键阶段。无按键冷启动只有 `#1 0003/.../00BF → 28:84D0` 和
  `#2 0106 → 1D:F2EC/28:83E6`；M55 后新增 `0107 → 27:571A/28:83E6` 与真正的
  `0003,...,00B0,... → 32:F15C/28:84D0`。两次运行中这两条新增记录顺序相反，证明
  它们是可并发/乱序的不同通知，不能只凭“导入计数增加”建立因果。监控器现在要求
  完整 B0 输入、`32:F15C` 结果和 `28:84D0` 返回三者一致，且提供 `--observe-only`
  冷启动基线；6 项单元测试通过。当前首个未知点已前移到 `32:F15C` 内部及其
  `28:84D0` dispatcher 分支为什么没有画出开始窄面板。不得强改 selector、直接画菜单
  或在 Web 跳页。
- 2026-08-29 观察到右下角时间数值会刷新，但新字形疑似叠加在旧字形上，时间区域
  没有得到正确的背景清除/覆盖。刷新事件存在，说明 RTC/定时触发至少已经走到绘制
  路径；目前不能仅凭该现象认定 resident ROM 缺失，必须先定位旧像素残留在哪一层
  首次出现。
- 2026-08-29 使用同源 v655 ROM 与 source-patched PRG 冷启动后，已实测
  `00:03 → 00:04`：最终 LCD 仅变化 28 像素，差异包围盒为
  `(219,107)–(234,117)`，时间矩形外变化为 0，旧数字像素得到恢复，当前未复现叠字。
  这说明此前现象可能与错误的未预处理 PRG 启动链相关，但在完成多次刷新和跨位边界
  回归前仍不把此项标记为已修复。`monitor_np560_clock.py` 用于在时间变化时同时冻结并
  保存 `50:3840` guest 合成缓冲、ST7529 GRAM 和最终 LCD 帧。
- 2026-08-29 已恢复开始回调所需的 `30:E662..E73D` application context 初始化代码：
  原厂完整源为 `4D:E662..E73D`（`LINK #2` 到平衡 `UNLINK/RETS`），此前目的地址的
  code view 仍读到另一函数的中段，导致 `32:F1AE → 30:E662` 一进入就破坏返回帧。
  guest 写入跟踪证明该区间会被完整安装两次，共 220 个 16-bit 写；QEMU 现把这个窄
  区间建模为真正的 Harvard 可执行 RAM，使 data write 与 instruction fetch 看到同一
  物理内容。修复后运行时反汇编从 `30:E662 LINK #2` 正常开始，旧故障已经消失；这项
  修正是 SoC 存储映射，不是按 PC 特判指令或模拟 ROM 服务。
- 2026-08-29 对 `32:F15C` 的对象写入历史已推翻上述“字段被覆盖”假设：flat
  `32:F15C` 实际是从 `32:F0EE LINK #0x57` 大函数中段进入，根本没有建立所需栈帧，
  因而嵌套调用自然覆盖了被误认作对象的栈区。原厂同 PC `4F:F15C..F198` 才是独立的
  `LINK #2` Start callback；它再调用同 PC 原厂 `48:593E..5B6F` 对应运行时
  `2B:593E` 的 `LINK #7` record handler。两段均已作为 immutable exact overlay 安装并
  加入 executable/data alias，旧 `11:1886 → 6C:002F` 故障消失。最新 v681 中回调以
  1619 条指令完整返回 `32:F198 → 28:856C`，同时保持 `ROM_MISSING=none`、
  `INVALID_CONTROL=none`、`UNSUPPORTED=none`。
- 后续只读 selector 跟踪已经纠正“空 root 就是唯一阻塞”的判断：Start 期间
  `51:4A40` 的 node key 会按原厂清理/重建链短暂从 1 变为 0，随后由
  `25:790E/7946/7948` 恢复。这是一条真实并发支，不能用强制 root 指针解决。
- v684 的完整调用/返回边界证明真正的首要错误是 flat `2C:79B8`：它从其他函数
  中段进入，在 `2C:7948` 越过 `2B:5AF6` 直接退到 `32:F190`，从而跳过整个
  record handler 后半段。v685 已恢复 exact `2C:79B8 ← 49:79B8`；现在
  `2C:7BA6 → 2B:5AF6` 正常返回，`2C:7A5E` 把 `A2:2250` 资源计数从 2 减到 1，
  handler 也已继续进入 `31:6518 → 24:11BE → 32:8204`。
- v686 已把 exact `31:7D02 ← 4E:7D02` 和 `33:4AE4 ← 50:4AE4` 放进自然
  application installer；运行时只读反汇编分别确认入口为 `LINK #4` 和 `LINK #0`。
  同一轮恢复 exact `2A:B066 ← 47:B066` 后，原先 flat `2A:B066` 消耗外层回调栈帧的
  故障也已经消失。源 `47:B066..B2BF` 是 602 字节、247 条可达指令、一个直接调用、
  零未知 frontier、平衡 `UNLINK/RETS` 的完整函数。
- v687 随后的 `33:4D3E RETS → F5:7388` 不是 CPU 指令错误。只读入口跟踪证明
  `33:4D2A` 由 flat `33:4D28` 顺序落入，根本没有 SCALL far-return 帧；相邻原厂源
  `50:4D14..4D28` 才是另一个完整 `LINK #0` 属性包装器。v688 已恢复 exact
  `33:4D14 ← 50:4D14`，运行时 `33:4CFE`、`33:4D14`、`33:4D2A` 三个 22 字节函数
  连续完整，`33:4D28` 正常返回 caller；对 `33:4D2A` 的观察也只记录到合法 SCALL
  返回帧，旧非法控制流已经消失。
- v688 的 `31:E740 RETS → 00:0000` 已定位为从 `30:09D4` 错误进入 flat
  `31:E1E4`。原厂同 PC 的 `4E:E1E4..E278` 是独立、平衡的 `LINK/UNLINK/RETS`
  函数；v689 已将其 150 字节 exact body 与相邻的 `31:E27A ← 4E:E27A` 一并安装。
  旧 `31:E740` 故障消失，说明该步是在恢复真实 guest code，不是在修改 RETS 或伪造
  返回地址。
- v689 继续执行约 508 万条 Start callback 指令后，新的首个严格停止推进到
  `18:5962 RETS → BC:3A50`，随后才表现为 `ROM_MISSING=00:0000`。有界调用跟踪已经证明
  `31:D9AA ← 4E:D9AA` 的 GPIO flag scanner 以原 SP/FP 和合法返回帧平衡返回，可排除。
  `18:4E62` 页面函数入口时的返回帧为正确的 `001A:DF84`，但运行到结尾前被改成
  `6ABC:3A50`；逐写入观察进一步把第一写入者定位到 exact far-memory copy overlay 的
  word loop `2E:46BC/46BE`，它经 translated data bus 覆写了 `0D88/0D8A`。因此当前问题
  不是 `RETS`、CPU 新指令或 `31:D9AA`，而是某个调用者向原厂远复制函数传入了错误的
  destination/length/source。下一步在写入瞬间冻结 caller、六个参数、GPR、DS 和 repeat
  状态，沿调用者恢复第一个错误指针或长度的生产点；不得修改 far-copy 或返回帧。
  v689 ROM SHA-256 为
  `D30DCEC3376537EA7A1861BB9463C3CA94878625DF0AFDDCDF4D379713E14F17`。
- `娱乐 → 游戏世界 → NPE 游戏` 的目录、NPE 加载器、运行时服务和实际游戏入口尚未
  形成闭环；v695 已在同一次未重启的运行中用真实物理矩阵依次注入
  `M55/0xB0 → M53/0x86 → M37/0x83 → M53/0x86`，四步均完成 map、guest consumer
  acknowledgement 和 release，并打开“游戏世界”。页面显示的不是菜单乱码，而是 guest
  原生报错 `无此目录:0:\应用程序,请创建!`。静态逆向已经确认该页面原生扫描
  `0:\应用程序\*.npe`，所以当前最近阻塞是 NAND 中该根目录的目录项及原厂创建/导入链，
  不是开始键、菜单事件或 Web 直接选择逻辑。
- 本机 `D:\Downloads\NP560plus游戏全集` 已找到 18 个真实格式的 NP560 `.npe` 文件，
  均以 ASCII `NP560 RPG2.1` 开头；最小的首个端到端目标定为 `英雄传奇.npe`，大小
  2,053,994 字节，SHA-256 为
  `ADEA7C7442CEFAEA1C21AB7442CDD10D7796E7FC1DD3A5B98FD3C1C61DFA8C19`。这消除了
  “没有样本”的阻塞，但样本来源说明、容器布局、加载 ABI 和可信导入方法仍需完成；
  不能把这些文件直接映射成宿主目录或用 `.nwf` 合成测试容器代替 guest 文件系统链。
- 2026-08-29 已增加一个只用于定位启动链的 FAT16 诊断导入桥：
  `tmp/np560-v695-hero-fat16-diagnostic-v2.nand` 在 `0:\应用程序`（cluster 5）内放入
  `英雄传奇.NPE`（cluster 6..256）。逐字节读回与原文件 SHA-256 完全一致，所有页 ECC
  也匹配；但它还不是最终 canonical 的原厂 USB/文件 API 导入方法。guest 随后确实完整
  读取物理页 `0x1004B`，CPU 可见缓冲中包含 `.`、`..` 和
  `英雄传奇.NPE` 三个正确目录项，证明当前阻塞已经越过“目录/文件根本不存在”，进入
  读取后的 resident 文件浏览器对象构造与显示生命周期。
- v696 已从原厂 PRG 精确恢复目录异步返回后的 resident continuation
  `02:0FB6 ← 3F:0FB6`，共 `0x04C4` 字节、445 条可达指令、23 个调用、0 个未知前沿；
  真实四键路径越过旧缺口。以目录页读取为触发点的临时只读控制流环随后定位到正常 caller
  `2C:87F8` 调用的新首个缺口 `1C:D462`，而不是数据页内容错误或需要新增 CPU 指令。
  该 trace 目前只在诊断 QEMU 中以物理页 `0x1004B` 为有界触发条件，仅读取控制转移并在
  256 项后冻结，不修改 guest RAM、寄存器、NAND、LCD 或返回值；完成此边界后应移除或
  泛化，不能成为正常模拟器逻辑。
- v697 已按原厂同 PC 源精确恢复 `1C:D462 ← 39:D462`，范围
  `39:D462..39:DBEF`、`0x078E` 字节、787 条可达指令、14 个调用、0 个未知前沿，入口
  `LINK #7`、结尾为平衡 `UNLINK/RETS`。目标回归通过，ROM SHA-256 为
  `27A9F7481B95B961A0AF6A1FBD00328EF83A28A6E2A5AE33FD5F9656B28C23C0`。隔离端口 8785
  再次以四个真实矩阵边沿进入游戏世界，四步均完成 map+ack+release，严格诊断为
  `ROM_MISSING=none`；但画面仍保留娱乐子菜单并在底部生成异常文本，第一次额外 Enter
  虽由 modal consumer 接收，却清成白屏，selected-file open/launch 仍未开始。因此当前
  真实卡点是 `1C:D462` 返回后的文件浏览器对象/列表 materialization 与 modal 生命周期，
  不是“已经显示 NPE 列表”或“已经启动游戏”。证据目录为
  `tmp/np560-v697-hero-8785-gameworld-route`、
  `tmp/np560-v697-hero-8785-gameworld-settled.png` 与
  `tmp/np560-v697-hero-8785-after-activate-settled.png`。
- [x] v697 的完整 ROM builder 回归为 `168/168` 通过（276.707 秒）；新增目标测试逐字
  断言 `1C:D462` 与 `39:D462` 源完全一致，并验证入口、平衡结尾、长度和 manifest 的
  787/14/0 控制流统计。
- 2026-08-29 的 v701 已把“NPE 列表为什么没有画出”的边界继续缩小。只读分配决策监控
  证明 `1B:23B8` 的四个 `0x0100` 字节工作区分配都返回 R0=1，四个 `NZ` 均按原厂条件
  正确跳转；`18:CFA8` 上下文构造返回成功，`21:CEF4` 绘制调用也能经 resident
  `02:0FB6` 返回到 `1B:2736`，最后浏览器在 `1B:2748` 正常等待事件。因此当前问题不是
  分配失败、CPU 标志位错误、按键没有进入浏览器或又缺了一条 CPU 指令。
- v701 的 live 数据快照同时证明，`02:0FB6` 所依赖的可写外部 RAM 记录
  `52:69D2..52:6B8D` 和操作配置表 `52:78A2..` 在进入浏览器时仍为零；该 continuation
  因而沿“无可绘制项”的原厂分支返回，旧娱乐子菜单留在屏幕上。flat PRG 同地址是打包
  字体/资源字节而不是这些运行时结构，且 guest 会写其中字段，禁止用只读同址 alias、
  猜测常量、Web 列表或显存补丁掩盖。当前第一优先级是以窄只读写入/复制跟踪找到负责
  初始化这些表的 application/resident loader，并恢复其准确的可写 RAM 初始化契约；
  v701 ROM SHA-256 为
  `F8C6F0AE84A783ACD467D216661554511156E6110F2EE075C8D9D0F3412ECBBE`。
- 当前右下角时钟能够周期刷新，但 2026-08-29 用户最新运行截图再次可见旧数字未完整
  清除便叠加新数字，故残影是未关闭问题。此前干净 v692 冷启动连续捕获
  `00:01 → 00:02 → 00:03` 时，三层均同步更新；两次 LCD 时间区变化分别为 17/11 像素，
  且同时存在旧像素清除和新像素绘制，说明问题可能依赖具体时间边界、前台状态或增量
  绘制路径，不能凭一轮干净样本宣告解决，也不能直接断言是 ROM 缺失。
  `monitor_np560_clock.py` 已能分别记录 guest `50:3840` 合成缓冲、ST7529 GRAM 和最终
  gray5 时间矩形的 draw/clear/bbox；下一轮须在发生残影的同一次运行中定位最早出错层。
  既有无残影证据在 `tmp/np560-clock-v692-clean`，只作为对照基线；在连续 20 次变化及
  `09→10`/`59→00` 多位边界通过前，P1 始终保持未完成。
  2026-08-30 又在 v732 的同一次隔离运行中用该三层监控捕获 `00:17→00:18→00:19`；
  两次变化的时间区均同时出现 clear/draw，guest 前缓冲、GRAM、gray5 同步，未复现残影。
  该轮因时钟按分钟推进，在 90 秒窗口内只取得 2/20 次变化，产物位于
  `tmp/np560-v732-clock-20`，仍只能作为干净对照，不能关闭用户报告的问题。
  随后对用户当前 8778 实例做纯只读取证，已经直接复现“数字变成实心块”：
  `CLOCK_FORMAT_RETURN_TRACE` 的输出缓冲是合法 ASCII `" 06:55\0"`，但同步捕获的 guest
  `50:3840` 前缓冲在时钟矩形内已经是四个填充块，ST7529 GRAM 和最终 LCD 只是忠实传递。
  证据位于 `tmp/np560-user-8778-clock-blocks-layers`。因此该复现的首个错误层已经排除 Web
  和 ST7529，落在格式化完成后的 guest 字形/位图合成链；下一步应跟踪从正常字符串到
  `50:3840` 时钟矩形的 glyph lookup、背景清除和 raster 写入，不再优先修改 LCD 地址窗口。
- 8×8 键盘矩阵与 GPIO 扫描模型已经存在。v695 已在同一次 QEMU 运行中证明跨应用前台
  连续短按不再中断：M35/`0x97` 切入辞典后，M36/`0xE9` 和 M37/`0x83` 仍依次经过
  原厂 candidate、`28:F6DE` map、`20:2E9E` foreground acknowledgement 和 release。
  这完成了原先的 state `0x4E` 事件循环卡点；Web 的方向、确认、返回、开始、保持、组合、
  失焦/断网释放随后也已补齐。当前只剩真实 NPE 游戏前台的 guest 长按重复、动作组合、
  返回/退出和 1,000 次压力测试，不能把这些未验收项误写成“前端按键仍不存在”。
- modal consumer 诊断原先在 `1E:F8E4` 过早读取 `FP-0x0A`，实际该指令刚把事件装入
  R0，事件仍位于 `FP-0x02`；只读监控已按原厂指令流修正。同一次运行的 M43/`0xBF`
  与 M44/`0xEA` 现分别得到 foreground/modal acknowledgement，证明跨 modal 前台的
  后续按键已经可观察。该修复只改变诊断读点，不改变 guest 数据或事件结果。
- 2026-08-29 已纠正 live 矩阵位 26/`0x8C` 的误判。完整原厂源
  `45:F4A4..F781` 证明 `0x8C` 是由 guest 本地消费的自定义 LCD 状态切换键，不应到达
  普通 `28:F6DE` 事件槽：第一次按下经 `28:F682 → 31:4D24(0x010C)` 设置
  `51:2734` 状态平面 bit 268，第二次按下经 `28:F64C → 31:5014(0x010C)` 清除并由
  `33:3C86 → 14:6E10` 刷新玻璃电极。真实缺口是 AND/OR helper 的数据总线仍看到
  flat `33:39E6..3A25` 代码；QEMU 已把同链接原厂 `50:39E6..3A25` 的 32 个精确掩码
  作为 0x40 字节 Harvard 数据视图。干净 v692 连按两次 M26 已验证 bit 268
  `0→1→0`，而 M15/`0x8D` 仍正常在 `28:F6DE` 完成；全程无 missing、unsupported 或
  invalid-control。`probe_np560_matrix_route.py` 现在区分 `map` 与 `candidate`，失败时会在
  释放前保存 held 快照；QEMU/Web 另提供有界只读 candidate-write 计数。证据见
  `doc/web/NP560_keyboard_completion_worker.md`。
- 2026-08-29 已完成 64 个物理矩阵位的分段 live 验收。QEMU/Web 新增既有
  `20:2E9E` `KEYMAPRET` trace 的有界只读计数；探针普通步骤要求 candidate、
  `28:F6DE` map、foreground acknowledgement、F160 释放和 `A2:2A5C=0`。
  首次顺序扫描在 M35/`0x97` 切到辞典后让 M36 看似丢失；M36 在新的稳定主菜单上
  单独完整通过，证明问题不是矩阵位 36。M43/`0xBF`、M53/`0x86`、M59/`0xB4`
  后也会改变前台，所以最终按八段隔离 route 验证：63 位均为
  `candidate → map → foreground-ack`，M26/`0x8C` 一位为原厂 candidate-only
  状态键，没有 map-only 或断路位置。聚合器
  `scripts/merge_np560_matrix_routes.py` 输出 `64/64 COMPLETE=1`；证据
  `tmp/np560-v692-matrix64-isolated-summary.json` SHA-256 为
  `B51623D7B601D6DC6A328B0F905C431D5945966DA88E8C35B72BCD944E591A73`。
  这完成的是 64 位短按硬件/主菜单链，不代表辞典等新前台已经可连续接收下一键，也
  不替代长按、组合键、浏览器失焦释放和 1,000 次压力测试。
- 2026-08-30 已补齐 Web 物理键盘输入层。`scripts/web/keyboard_input.js` 以“输入来源 →
  当前物理矩阵电平”状态机统一 PC 键盘、鼠标和触控：按住不重复发送 make，同一矩阵位
  的多个别名直到最后一个来源释放才产生 break；Home 对应开始键 M55，未知侧键明确保持
  未映射。`app.js` 在 blur、visibility hidden、pagehide 和 beforeunload 时全零释放；
  `np560_web.py` 增加 opt-in 1.5 秒按键租约，heartbeat 只续租、不重复写 QEMU，断网后
  服务端自动清零，且活跃 owner 会拒绝旧页面迟到的 make/break。快速二次 pointerdown
  会重新捕获指针并重置保持计时，避免取消旧 release timer 后形成永久粘键；每个按钮的
  pointer source 也相互隔离。旧的无 lease 探针行为不变。相关 Python/JavaScript 回归
  16/16 通过；剩余验收只在真实 NPE 游戏前台进行长按重复、返回/退出和 1,000 次压力测试，
  不能用前端单元测试代替 guest 行为。
- 2026-08-29 v695 已进一步恢复辞典 state `0x4E` 的完整原厂前台循环。根因是三段 SoC
  Harvard 映射缺口，而不是缺少 CPU 指令或需要模拟 ROM 服务：resident loader 已经把
  exact `50:44AE..44C9` wrapper 写到 `33:44AE`，并把 source `2A:2F30..5D9B` body
  写到 `0D:2F30`，但旧 QEMU 的指令总线没有看到相同 RAM backing；body 又会调用
  `33:6BE2`，该数值地址的数据总线属于可写 NAND sector buffer，而真实四指令 predicate
  位于 `50:6BE2`。QEMU 现严格增加三段有界硬件视图：
  - `33:44AE+0x001C`：guest 可写、数据/指令总线一致的 executable RAM；
  - `0D:2F30+0x2E6C`：resident loader 所属、数据/指令总线一致的 executable RAM；
  - `33:6BE2+0x0008 ← 50:6BE2`：仅指令总线固定到 exact source，数值相同的数据区继续
    保持 NAND buffer 的可写语义。
  v695 ROM SHA-256 为
  `2078E9A61F8C59701BC02032B1A19BB511703F81EE9AD1020322046FA68CF9B7`。同一次未重启、
  未恢复快照且未直接修改 guest 状态的运行中，M35、M36、M37 依次得到事件
  `0x97`、`0xE9`、`0x83`，三步均 map+ack+release；证据为
  `tmp/np560-v695-m35-m36-continuous-ready-predicate/route.json` 和
  `tmp/np560-v695-m37-continuous-after-dictionary/route.json`。正式反汇编为
  `doc/disassembly/np560_source_2a2f30_reachable.asm`、`doc/disassembly/np560_source_506be2_reachable.asm`。
- [x] v695 的完整 ROM builder 回归为 `166/166` 通过（253.156 秒）；overlay preflight
  同时报告 builder overlays `540`、missing mappings `0`、non-identical overlaps `0`。
  另有 46 项 overlay parser/audit 单元测试通过。回归已明确断言 ROM-01 尾部顺序必须为
  `LCD power init → exact state-4E wrapper install → RETS`，防止后续宽范围 copy 再次覆盖
  wrapper。
- [x] 2026-08-29 完整 Python 回归已清零旧漂移：`463/463` 通过（441.993 秒）。
  修正了 provision monitor 默认写入计数、181 项 application trace 三方对齐、当前
  installer payload 地址/长度，以及 relocated menu cursor SCALL 的 `1F:C86A` 签名。
- 正常应用使用的完整文件系统写入、坏块、磨损、掉电恢复、音频、USB、RTC、定时器、
  中断和剩余 DMA/SFR 尚未全部覆盖。

## 3. 实施原则

1. 先保证 guest 自然执行，再做 Web 交互；Web 只呈现 LCD 和输入硬件。
2. 优先修复最早出现的真实分歧，不在后续地址增加返回值或画面特判。
3. 所有新 resident 代码必须说明来源：原始同 PC 代码、可证明的重定位，或明确标注的
   clean-room 行为重建。
4. 所有一次性镜像修补都要升级为可重复生成规则；不能解释其硬件/格式层级的补丁不得
   进入最终启动链。
5. 每个里程碑必须同时具备自动回归、诊断门槛和可见结果，不能只凭截图判断通过。

## 4. 分阶段路线

### P0：冻结可重复基线并清零回归

目标：任何后续逆向工作都有一个可信、可一键复现的起点。

- [x] 修复当前 11 项回归：
  - `monitor_np560_provision` 的 `expected_write_calls` 参数契约；
  - application trace 目标数 `153` 与当前 `181` 的断言漂移；
  - application-region/menu installer 的 payload 长度与边界；
  - relocated menu cursor-call signature 与生成器当前输出的分歧。
- [ ] 增加一个统一 baseline 命令，依次完成 ROM 构建、NAND 准备、QEMU 启动、
  主菜单检查和长周期检查。
- [ ] 将 `mirror_np560_runtime_patches.py` 纳入 canonical 构建链；拒绝把原始 PRG 与
  包含 runtime 代码镜像的重建 ROM 直接混用，并在 manifest 中记录全部源端补丁。
- [ ] 为 canonical PRG、重建 ROM、NAND checkpoint、顶栏资源和 LCD 帧记录大小与
  SHA-256，避免误用旧版本产物。
- [ ] 把散落的 `vNNN` 临时产物收敛为“生成输入 + manifest + canonical 输出”；
  `tmp/` 仍只保存可再生运行产物。
- [ ] 建立 LCD golden：启动文字、完整主菜单、选中态顶栏、时间和状态图标分别比较
  240×120 原始 gray5 帧，而不是比较浏览器缩放截图。
- [ ] 将正常的栈顶环绕与真正的低栈/低 FP 故障分离，canonical run 必须没有未分类的
  `FIRST_LOW_SP/FP` 告警。

验收条件：全部单元测试通过；同一输入连续三次构建得到相同 hash；三次冷启动得到
相同主菜单 golden；`ROM_HLE=off` 且无 missing/unsupported/invalid-control。

### P1：还原自然主菜单资源链，淘汰一次性画面修补

目标：主菜单由 guest 从 NAND 资源自然装载、解析和绘制，而不是依赖人工修过的
checkpoint 或 CPU/LCD 特判。

- [ ] 固定并自动验证以下数据链：
  `NAND resource → resident/resource loader → 51:4A92 object → bitmap blitter → ST7529`。
- [ ] 解释 v654 page-lane 变换属于哪一层：升级包页流、NAND controller byte lane、
  resident copy ABI、对象格式或 LCD packed-pixel 格式。
- [ ] 让原厂 burner 或有证据的 NAND 导入器自然生成相同字节；若不能，则撤销该变换
  并继续追踪第一个错误写入者。
- [ ] 对 `ROOT_TOP_BITMAP` 的 source/object hash、长度 2650 和五个菜单项的边界建立
  自动断言。
- [ ] 验证未选中、选中、切换后的五个顶栏按钮都来自 guest 数据并保持正确。
- [ ] 修复右下角时间的增量重绘残影，并先用逐层证据确定责任位置：
  - 连续保存时间变化前后的 guest 源对象/合成缓冲和 ST7529 GRAM，比较第一次出现
    旧字形残留的位置；
  - 若 guest 源对象已经叠字，追踪并恢复时间矩形清除、背景填充、opaque text/ROP 或
    resident compositor 的真实语义；
  - 若 guest 源对象正确而 GRAM 残留，修正 ST7529 的窗口、cursor、auto-increment、
    read-modify-write、裁剪、stride 或 packed-pixel 写入行为；
  - 使用 `CLOCK_RASTER_PIPELINE` 的 `s0` 背景调用前、`s1` 背景调用后、`s2` 文字调用前、
    `s3` 文字调用后四个边界证明写入顺序；只有 `s2` 为单一非前景灰阶，且 `s3` 保留该
    灰阶并新增前景灰阶，才记为“统一背景后绘字”，不能只用前景像素计数为零判定；
  - Web 只能呈现 GRAM，不得在每次刷新前替 guest 清除时间区域。
- [ ] 为 `09:59 → 10:00`、`19:59 → 20:00` 等改变字宽/多位数字的边界建立 raw gray5
  回归；时间矩形外必须逐像素不变，时间矩形内必须与同一时刻的干净冷绘制一致。
- [ ] 删除最终路径中只为某个 caller、地址、字符串或截图服务的特判。

验收条件：从 canonical NAND 自然冷启动即可得到完整主菜单；不需要 checkpoint
page-lane 后处理；关闭全部 HLE/画面特判后 golden 仍完全一致。右下角时间还必须连续跨越
至少 20 次真实变化并覆盖一次多位数字边界；每次变化的 guest back buffer、ST7529 GRAM
和最终 raw gray5 时间矩形逐像素一致，时间矩形外像素不变，Web 端没有清屏或补画逻辑。

### P2：还原 resident manager 和可交互桌面

目标：在主菜单正确的基础上，完成原机桌面状态机。

- [ ] 追踪 `20:0326` 返回时 R0/R1/R2、persistent selector 和 resident manager
  消费点，恢复 `0x82/0x83/0x84/0x85` 的选择策略。
- [ ] 确定 `01:0200` loader、application-state guard 和 `1F:B496` dispatcher 的正确
  先后关系，逐步替换当前 inferred scheduler loop。
- [ ] 还原 `02:B9E2`、`02:BAC4`、`02:BAC8` 的 GPIO/select/setup 副作用；没有证据时
  保持可诊断的未知状态，不能永久使用无条件 `RETS`。
- [ ] 分类 `02:C588` 的 diagnostic-byte 外设副作用和 `17:9244` 多字节字体依赖，
  确认它们是否进入正常桌面路径。
- [ ] 使用真实 8×8 矩阵完成左右切换顶栏、上下切换左侧菜单、Enter 启动、Esc/返回。
- [x] 在 Web 前端提供与当前已确认 NP560+ 实体按键对应的完整可见键盘，并保留 PC 键盘映射；两种
  输入方式必须共用 `/api/key → QMP/QOM matrix` 路径，前端按钮不得直接调用菜单动作。
- [ ] 打通并记录完整输入链：
  `Web keydown/keyup → /api/key → QMP/QOM matrix row/column → GPIO/SFR →`
  `06:B126 → 2E:5F28 → 28:F4A4 → resident/application event → LCD redraw`。
- [ ] 验证每次输入都经过 `06:B126 → 2E:5F28 → 28:F4A4` 原厂 guest 链，
  `KEY_CODE` 和 `F340` 探索 latch 始终为零。
- [x] 实现前端按下、保持、释放、短按去抖和同矩阵组合语义；浏览器失焦、页面退出或
  1.5 秒租约断开时释放全部矩阵位置，并用快速二击和旧页面迟到 make/break 测试关闭两处
  粘键竞态。guest 游戏前台的长按重复频率另列为下项，尚未完成。
- [x] 在真实 NPE 游戏前台完成四方向 200 ms 物理短按、正常退出和 1,000 次连续压力；
  四方向各 250 次且 candidate/map/consumer ack 严格 `1000/1000/1000`，一个 Start
  `0078→00FF` 并由原厂 root renderer 自动返回完整主菜单。
- [ ] 验证方向/动作键的真实长按重复频率、动作与方向组合、独立返回键语义；发现的未知
  实体侧键必须依据原厂扫描表补映射，不能猜键值。
- [x] 为 64 个矩阵位置建立 live QEMU 短按测试并完成 64/64 聚合；方向、Enter、返回、
  开始键均从浏览器进入真实矩阵/guest 事件链，前端不直接修改菜单选择状态。游戏前台
  长按/组合/退出另按未完成项验收。
- [x] 为顺序键盘探针增加有界、只读的前台消费确认：普通事件除候选写入外，还必须等待
  `28:F6DE` 投递和 `20:2E9E` `KEYMAPRET` 的计数/事件值匹配，并在
  `A2:2A5C=0` 后才注入下一物理边沿；`0x8C` 按 guest-consumed 状态键验收，活动表
  保留值 `0xFFFF` 则以 live 实测的普通 map+ack 语义验收。会切换应用/页面的按键还要
  等待目标前台稳定，必要时从同一冷
  启动快照独立测试，避免页面上下文污染后续矩阵位。
- [x] 完成 64 个物理位的分段短按验收和自动聚合：63 个普通 map+ack、1 个
  `0x8C` candidate-only；所有位置均观察到 release，聚合覆盖 64/64。
- [x] 恢复辞典 state `0x4E` 的跨应用前台事件循环：v695 在同一次运行中连续完成
  M35/`0x97`、M36/`0xE9`、M37/`0x83` 的 map+ack+release，没有重启、恢复快照或
  直接修改 guest 状态。此项关闭的是原先“M35 后下一键失效”的卡点；完整菜单导航、
  长按、组合键和浏览器释放语义仍由下列总验收项覆盖。
- [x] 在不重启、不恢复快照且不直接改 guest 状态的同一次运行中，用真实矩阵事件连续
  完成 `开始 → 娱乐 → 游戏世界`。v695 四步均为单次 map+ack+release，最终由 guest
  自然显示 `无此目录:0:\应用程序,请创建!`；证据为
  `tmp/np560-v695-start-entertainment-gameworld-modal-route/route.json` 和
  `05-GameWorld-settled.png`。
- [ ] 建立 `0:\应用程序` 并导入真实 NPE 后，继续在文件列表和游戏前台验证方向、确认、
  返回、保持及长按，并完成 1,000 次压力测试；浏览器失焦/断开释放已经实现，须在这条
  真实路径复验。完成这些之前，
  “64/64 独立短按”及“已进入游戏世界”都不得表述为完整键盘交互已经完成。
- [x] 用诊断 NAND 验证完整物理目录页和 `英雄传奇.NPE` 文件链可被 guest 读取，并以
  v696/v697 依次恢复读取后的 exact resident `02:0FB6` 与 `1C:D462`。此项只证明输入、
  目录内容和两个 resident 边界；当前列表仍未正确 materialize，额外 Enter 只到达 modal
  consumer，不能勾选文件选择、游戏启动或完整键盘验收。
- [x] 完成 live 矩阵位 26/`0x8C` 的原厂语义分类和缺失数据视图修复：它不是被
  `28:F6DE` 丢弃的普通事件，而是两次按下分别置位/清除 LCD annunciator bit 268 的
  guest-consumed 状态键；M15/`0x8D` 继续走普通 map 路径。后续 64 键验收必须按
  “普通 map、guest-consumed 状态、长按/组合”分类，不能强迫所有键经过 `28:F6DE`。
- [x] 为导航探针增加只读、低延迟的按键边沿状态，并证明开始、确定、下、确定四步
  均为单次映射且释放后 guest 门控归零；这只验收了当前四个短按，不替代 64 键、长按、
  失焦释放和压力测试。
- [ ] 完成“启动应用 → 正常退出 → resident manager 选择下一状态 → 回到桌面”的循环。
- [ ] 继续还原 `A2:2250` 资源计数的 acquire/release/owner 语义；保留已经证实的
  正常初始化两对象模型：`51:27C6` 与 `51:2770` 都在开始键之前注册。不要再把第二
  对象称为开始键 modal 对象，不把计数 2 本身当故障，也禁止强制改成 0/1。
- [x] 沿已验证的开始键链
  `20:2DE0 → 22:FD9E → 29:24C6 → 1F:F470 → 32:F15C → 28:84D0`，记录 callback
  的完整参数、分支、子调用和返回状态。把并发的
  `0107 → 27:571A → 28:83E6` 单独归类，禁止再把其 mode 1/`51:4A46` 选择器结果
  当成 B0 的直接结果。v691 已经通过恢复 resident 事件表与 exact `24:11BE` 闭合
  此路径并由 guest 画出开始窄菜单；下一步从菜单内真实方向/确认/返回事件继续推进。

验收条件：Web 和自动测试都能通过物理矩阵连续切换五个顶栏、五个开始菜单项，启动
至少一个真实应用并返回；并须在同一次真实 NPE 游戏前台运行中通过方向长按、动作键组合、
返回/退出、浏览器失焦释放和 1,000 次 press/release 压力测试，无卡键、丢失 release、
栈泄漏、缺失 ROM 或非法控制流。

### P3：扩大应用功能覆盖

目标：从“桌面可交互”推进到“主要应用可用”。

- [ ] 建立应用矩阵：学习、辞典、网络、记事、系统及开始菜单下每个入口。
- [ ] 每个应用记录入口、依赖的 resident API、NAND 文件、外设和当前最早失败点。
- [ ] 优先完成只依赖 LCD/键盘/只读资源的应用，例如计算器、辞典查询、资料浏览和
  基础系统设置。
- [ ] 再完成需要持久化写入的记事、用户资料和设置保存。
- [ ] 对每个应用增加启动帧、关键操作帧、退出事件和资源读取的回归。
- [ ] 禁止用 Web/宿主代码替代应用逻辑；新增硬件能力必须通过 guest MMIO 使用。

验收条件：所有主菜单入口都有明确结果；核心离线应用可以完成基本操作并返回桌面；
未支持的联网/外设功能给出明确诊断，不崩溃、不伪成功。

### P4：完成存储系统和升级流程

目标：能够从原厂包创建、运行和持久保存一个一致的虚拟设备。

- [ ] 从 `NP560+.upd` 经原厂 burner guest code 自动生成 canonical NAND，替代手工
  checkpoint 链。
- [ ] 还原完整 OOB 字段、坏块标记、FTL 映射、磨损策略和 factory filesystem 目录。
- [ ] 覆盖正常应用的创建、读取、更新、删除、重启持久化和空间耗尽路径。
- [ ] 增加编程中断、擦除中断、坏块、ECC 双比特错误和掉电恢复测试。
- [ ] 验证保存 checkpoint 不修改输入文件，原子替换失败时旧镜像仍可恢复。

验收条件：全新虚拟 NAND 可由升级包生成；应用写入跨进程保存；故障注入不会静默
损坏文件系统；重复升级结果确定。

### P5：补全 CPU、时序和外设

目标：覆盖正常固件和主要应用实际访问的全部硬件行为。

- [ ] 为 DMCU 指令、标志位、奇偶地址、栈、LINK/UNLINK、far call/return 建立
  编码级 conformance 测试。
- [ ] 完成 IRQ 入口/返回、优先级、屏蔽、定时器和可重复的 icount 时序。
- [ ] 按访问证据补齐 DMA、剩余 SFR、ADC、电池、电源、睡眠/唤醒和 RTC。
- [ ] 建模蜂鸣器/音频输出，并将音频交给 Web 播放，不在前端生成声音逻辑。
- [ ] 建模 USB controller 的枚举、loader 和升级所需最小行为。
- [ ] 对暂时未知的寄存器保持可观察、可失败的默认行为，并记录首次 caller。

验收条件：已覆盖应用不再触发未知 SFR/DMA/IRQ；RTC、睡眠唤醒、音频和 USB 的
已支持场景都有自动回归；同一 icount 配置下执行结果可重复。

### P6：前端、打包和长期稳定性

目标：形成可供普通用户启动和测试的模拟器，而不是只适合逆向调试的工程。

- [ ] 提供一个 Windows 启动入口，自动检查 WSL/QEMU、构建缺失产物并启动 Web。
- [ ] Web 默认只显示原机 LCD、状态图标和按键；海量诊断移入可折叠开发面板。
- [x] 增加 Web 整机 Reset：恢复 RAM/可写代码页、显式复位 DMCU CPU，checkpoint 模式
  重载 NAND 基线，并动态证明复位后 IRQ、矩阵扫描和完整主菜单重新运行。
- [ ] 增加开关机、插拔外接电源、调节电量，以及完整设备状态保存/恢复。
- [ ] 将 ROM/NAND/hash、HLE 状态和 unsupported 状态始终显示在诊断页，避免混用
  产物后误判。
- [ ] 运行 1 小时 idle、1 万次按键、1,000 次应用切换和多次保存恢复压力测试。
- [ ] 整理许可证、clean-room 证据边界和原厂固件由用户自行提供的说明。

验收条件：新环境按文档可一键启动；默认配置不启用 HLE；长时间运行没有资源泄漏、
栈破坏和状态漂移；诊断模式不改变 guest 行为。

### P7：打通并实际游玩 NPE 游戏（最终目标）

目标：不是停在“NPE 游戏”列表，而是让一份可校验来源的真实 `.npe` 文件经 guest 的
真实文件浏览、加载和运行路径启动，在 Web 虚拟物理按键上可持续游玩，并能正常退出回到
桌面。`NEPLAYER`/NWF 是否是 NPE 的内部载荷或独立格式，保持为待验证问题。

- [x] 从 124 项原厂应用目录、25 页菜单表和 NAND 资源中还原并动态验证到“游戏世界”的
  准确导航链。v729 已在同一次干净冷启动中以真实矩阵短按走通
  `开始 → 娱乐 → 游戏世界`，并动态确认应用代码 `0x0078`、操作索引 1、目录
  `0:\应用程序` 和过滤器 `\*.npe`；当前诊断 NAND 中该目录及 `英雄传奇.NPE` 均存在，
  不再停于“无此目录”或启动邮件弹窗。v747 已让 Hero 成为唯一正确 materialized item；
  v752 又以第五个真实矩阵确认事件完成 modal acknowledgement 和 release，并越过旧
  `1B:7A20` trap。这里仍只代表“选中事件已进入格式分发器”，不代表游戏已经启动。
- [x] 已记录并自动重放“NPE 游戏”文件列表的选择、格式分发、启动、游戏循环和返回事件。
  v755/v756 起取得的格式分发证据已经继续闭合到真实首帧和主循环；v840 七个真实矩阵边沿
  进入 Hero 地图，18 次真实方向事件改变 LCD checkpoint，`M55/B0` 又从 application
  `0x0078` 正常返回 `0x00FF` 主菜单。历史上从 `32:CEEE/CF7C` 开始的 loader/runtime
  缺口和后续 exact closure 仍保留在版本记录中，但不再是当前阻塞。尚未命中的同目标 caller
  继续按可达性审计，禁止因为 Hero 主路径已通过而无证据批量改写。
- [ ] 从升级包原始烧录记录和 NAND checkpoint 双向核对 `0:\应用程序`：确认它应由
  哪个分区、目录表或 factory record 创建，检查中文名编码、字节 lane、FTL 映射、
  目录属性和父记录；当前已排除 slot 3 中四处正文误报，下一步验证它是否本来就应由
  用户在“我的硬盘”创建，再通过原厂文件 API 建目录/导入文件；要求 guest 自然列出目录。
- [x] 用可丢弃的 FAT16 诊断桥建立目录和导入 `英雄传奇.NPE`，逐字节/hash/ECC 验证后，
  证明 guest 已读取含 `.`、`..`、`英雄传奇.NPE` 的完整目录页。该镜像只用于把逆向推进
  到读取后的 resident 边界，不替代上一项要求的原厂 canonical 导入链。
- [x] 闭合读取后的文件浏览器对象/列表生命周期。v696 先恢复
  `02:0FB6 ← 3F:0FB6`，随后通过有界只读 post-read trace 定位并恢复
  `1C:D462 ← 39:D462`。v701 又证明四个浏览器工作区分配、`18:CFA8` 上下文构造和
  `21:CEF4 → 02:0FB6` 返回链均成功。v702 精确恢复了 `0C:BDBE ← 29:BDBE` 的 UI 表构造器
  与 `29:D0BA ← 46:D0BA` 初始化器；v703 又精确恢复
  `2F:B644 ← 4C:B644 → 1F:D1A6 ← 3C:D1A6 → 2D:F47C ← 4A:F47C →`
  `1D:8A3A ← 3A:8A3A` 的上游闭环。四键冷重放仍得到
  `RECORDS:222/0 CONFIG:60/0`，证明这些表确实没有变化，但也纠正了“它们就是 NPE 列表
  初始化”的假设：`1B:299C` 操作表的入口 0 才选择 `1B:29C2 → 2F:B644`；NPE 的操作
  索引 1 在选中文件后选择 `1B:2A7C → 2E:D34A`。因此 v703 恢复的是另一操作分支，
  不是当前 NPE 列表为空的直接修复。
- v703 的有界动态控制流曾把边界收紧为：
  `1B:2732 → 21:CEF4 → 11:2B6E → 02:0FB6 → 1B:2736` 正常返回，随后在
  `1B:2748 → 11:1752` 等待真实事件。当时“renderer 跳过 `2C:8744`/`1C:D462`”的
  判断已被 2026-08-30 的逐指令复核推翻：`21:CEF4` 在 `CFF2` 读取到标志 2 后走正常
  布局分支，确实调用 `2C:8744` 和 `1C:D462`。这条旧判断不得再作为后续修复依据。
- 2026-08-30 的 v713 已消除 startup initializer 与 Game World controller 在
  `2C:9A7C` 的覆盖冲突：将同源初始化体改装到 resident `06:9A7C` 并重定向原 caller。
  四键重放随后进入 `1B:23B8` 浏览器对象和 `21:CEF4` renderer，且控制器正常返回
  `2C:9B94`；不再错误落到 `2C:9C64` 数据区。随后确认 renderer 尾部调用的
  flat `30:6082` 不是合法函数，而更新 PRG 的 `4D:6082..6184` 是 ABI 完整、栈平衡的
  exact 同 PC 源。
- v714 已把 `4D:6082..6184` 安装到 `30:6082`，其直接依赖
  `32:B8D0`、`33:4CFE`、`33:66E2` 及子调用均已有 exact overlay。重复冷启动重放纠正了
  最初“第四键必然转入 modal”的判断：同一 v714 镜像也能让第四个确认事件由 foreground
  接收，完整执行 `2C:87F8 → 1C:D462 → 31:4474 → 2C:87FC` 布局共享尾返回，并由
  `2C:9B94 → 1B:2736` 返回控制器；此时第五个确认键才由 modal consumer 接收。因此现有
  输入/对象生命周期还存在时序差异，不能把一次 route 的 consumer 归属当成 finalizer
  正确性的单独证据。
- 第五个确认事件 `0x86` 在 exact modal worker `1E:F734 ← 3B:F734` 中经过
  `1E:F8E4 → 1E:FC56 → 33:5B70`；worker 的 false arm 把输出写成
  `TYPE=1/CODE=0x86` 并以 `R0=1` 在 `1E:FD7A → 2F:C23A` 返回。2026-08-30 的源码和
  逐控制转移复核已经纠正旧解释：`2F:C216 ← 4C:C216` 是完整事件解码器，`C23A` 是
  解码器内部逻辑，不是“记录构造循环索引递增”；它最终在 `2F:C304` 对 type 1 调用
  `2C:D350`。原 flat `2C:D350` 是无关代码，才会错误走到 `03:4050`。
- v715 曾把额外安装调用附加到大型 ROM01 loader，因改变 loader 布局导致冷启动回归；
  v716 又尝试从 resident 段 06 的代码视图做普通数据拷贝，但该段不天然可由数据总线
  读取。两者均已否决。v717 保持 ROM01 loader 字节长度不变，只在派生 PRG 中校验并替换
  `4C:C304` 的两个调用字为 `SCALL 06:4B00`；resident wrapper 以普通 guest MOV 存储
  240 个 exact `49:D350..D52F` 字到 `2C:D350`，再尾跳原处理器。动态轨迹为
  `1E:FD7A → 2F:C23A → 06:4B00 → 2C:D350 → 2F:C308 → 2F:C340 → 11:17F2`，
  `EVENT_STATE_OVERLAY=WRITES:240`，证明处理器和 ABI 均已闭合。
- v717 的下一处停止 `11:18D2/c600 → 11:0000` 也已精确归因：`11:18D2` 是 RET，
  它从 inline 表 `11:18D4..18EF ← 2E:18D4..18EF` 读取 14 个近目标；代码 ROM 已存在，
  只是数据总线此前读到 0。v719 在 QEMU 仅增加这 0x1C 字节的只读 Harvard alias；
  `0x86` 的原厂表项为 `11:2A1A`。同一 canonical 配置静置冷启动后，五个真实矩阵边沿
  全部完成 map+ack+release，第五键由 modal consumer 接收，且
  `ROM_MISSING=none`、`UNSUPPORTED=none`、`INVALID_CONTROL=none`。v719 ROM 内容与 v717
  相同，SHA-256 均为
  `74EE6A54859F16F70ED535FC1FEC73ED8E6ACC5F9AB37BE4550A024B162C9235`；关键差异在
  QEMU 数据总线 alias 和新增 manifest 元数据。证据目录为
  `tmp/np560-v719-v717-hero-event-table-route/`。
- v729 已关闭 v719 的启动期邮件弹窗污染。只读候选比较证明 resident 路径解析器把
  `nminbox.pim` 规范化为 11 字节 selector `NMINBOX PIM`，而 v727 诊断 FAT 项仍是
  `nminbox PIM`；逐字节比较结果正好为 `0x0020`，不是 PIM 头、目录属性或 CPU 指令问题。
  诊断导入器改用大写 8.3 短名后，冷启动自然得到
  `FILE_PATH_RESOLVE RESULT=1/FINAL=1/ATTR=0x20/LENGTH=0x4A`，随后
  `fopen(mode=1)` 返回 `ERROR=0000`，且无 `ROM_MISSING`、`UNSUPPORTED` 或
  `INVALID_CONTROL`。这只证明诊断预配置兼容启动；原厂 factory provisioning 仍未恢复。
- 在同一 v729 冷启动上，五个真实矩阵边沿均完成 map+ack+release。前三步可见地打开
  “开始”、进入“娱乐”并选中“游戏世界”；第四步使 application state 自然变为 `0x0078`，
  四个 `0x0100` 浏览器工作区全部分配成功，`18:CFA8` 构造和
  `2C:87F8 → 1C:D462 → 2C:87FC` 布局链也正常返回。但第四帧与第三帧逐像素相同，
  第五个确认才进入异常 modal 画面。复核诊断实现后确认，`FILE_ATTACH_FRAME=0` 只监控
  `2E:BE2E`，`OBJECT_INIT=0` 只监控 burner 的 `51:A34A/A3A0/A494`，两者都不是
  operation 1 文件浏览器的完整生命周期指标，不能据此断言首个记录没有挂接。当前可证明的
  边界只是：`0:\应用程序\*.npe` descriptor、浏览器对象、renderer 和布局入口均已执行，
  但客体画面仍未改变；下一步必须在实际 operation 1 布局/回调链中找到第一个 guest 状态
  差异。不能再归因于菜单路径、目录不存在、PIM 弹窗或工作区分配，也禁止用 Web 重画列表、
  直接选择文件、显存擦除、猜表内容或强改对象标志。
- v703 重建 ROM SHA-256 为
  `E2C47FE8B5CEB199B0D6A8ABEC26BB2AE6B21269E55E03E1CB0CA32DAD7E34D5`；四个真实
  矩阵边沿均为单次 map+ack+release，且 `ROM_MISSING=none`、`UNSUPPORTED=none`、
  `INVALID_CONTROL=none`。动态摘要和屏幕证据分别位于
  `tmp/np560-v703-operation-ui-data-8786-route/diagnostics-summary.txt` 与
  `tmp/np560-v703-operation-ui-data-8786-route/04-EnterGameWorld.png`。该画面仍停留在
  娱乐子菜单背景，不能表述为 NPE 列表已经显示或游戏已经启动。
- 2026-08-29 的 v4/v5 A/B 又将边界缩小：原厂/guest 自建 `TRASH.CAN`
  子目录中 `.`、`..` 使用 `ATTR=0x16`、NUL 扩展名，而旧诊断导入器误用
  `0x10`/空格。按 guest 格式修正后，固件由第一条 `.` 推进到第二条
  `..`。再用仅把 `英雄传奇.NPE` 放在第一条的诊断对照，guest 已精确产生
  `ATTR=0x20`、`LENGTH=0x001F576A` 和完整 GB18030 文件名，但 LCD 失败帧 hash
  与 v4 逐像素相同；追加 Enter 仅被 modal 消费并清成白屏，`FILE_OPEN
  SELECTED=0`。因此 NAND/FTL/文件链/dot 过滤/文件记录解码均不是最近阻塞；
  当前只追 descriptor 到 list item attach/selection 之间的第一个差异。v5 只是
  定位用 A/B，不得取代带原厂 dot 记录的 canonical 目录。
- [x] 取得可按字节校验的真实格式样本集：本机 `NP560plus游戏全集` 中共有 18 个
  `.npe` 文件，魔数/版本均为 `NP560 RPG2.1`。首个 canonical 目标选用最小样本
  `英雄传奇.npe`（2,053,994 字节，SHA-256
  `ADEA7C7442CEFAEA1C21AB7442CDD10D7796E7FC1DD3A5B98FD3C1C61DFA8C19`）。
  升级包 slot 3 仍未包含这些文件，仓库的 `lirt*.nwf` 仍只算合成测试容器。
- [ ] 补记上述游戏包的原始下载页/归档来源和获取时间；确认“NPE 游戏”列表所需目录
  记录、文件名编码、图标及元数据格式。只有 hash 而没有来源说明时，可用于本机逆向和
  回归，但不能宣称已完成公开可复现的内容来源审计。
- [ ] 以真实 `.npe` 文件反推 NPE 文件头/容器：确定魔数、版本、元数据、代码/资源段、
  校验、压缩/加密、重定位和实际执行模型；特别验证它是否内嵌或引用 NWF，而不是预先
  假定 NPE 与 NWF 是同一格式。
- [ ] 逆向 `.npe` selected-descriptor 之后的 loader/runtime ABI：operation/descriptor 路径包含
  `1B:2A88 → 2E:D34A → 30:C370/30:C99E → 18:21F4`；v752 已另外动态进入
  `2F:B6DA → 1B:7A20` 格式分发器，静态 Hero 分支应以状态 2 返回并转到
  `2F:B726 → 1F:D1A6`。先用只读 PC/返回值轨迹确定两条链的实际先后和汇合点，再继续恢复
  文件读取、内存分配、解压/解密、重定位、入口参数、启动、退出和异常返回。
- [ ] 单独保留已有 NEPLAYER/NWF 逆向结果作为候选子系统：只有真实 `.npe` 的调用/载荷
  证据能把它与 NPE 游戏关联；如果不关联，则不得让 NWF 路线占用最终目标的关键路径。
- [ ] 列出并实现首个游戏实际调用的运行时/硬件依赖，包括键盘与长按、定时器/IRQ、
  LCD 缓冲与局部刷新、随机数、音频以及存档读写；缺失入口必须停止并报告 caller。
- [x] 以 `英雄传奇.npe` 作为首个端到端样本，建立“诊断镜像导入 → 菜单导航 → 列表 →
  选择 → 标题/首帧 → 实际操作 → 游戏状态变化 → 退出”的自动脚本；脚本只能注入物理
  矩阵边沿和读取诊断，不得直接写 guest 菜单状态、显存或程序入口。当前由
  `scripts/probe_np560_matrix_route.py` 和 `scripts/monitor_np560_npe_play_session.py` 完成；
  v838 已有 600 秒长跑，v840 已有针对动作覆盖修复的 31.859 秒/18 动作/正常退出回归。
  原厂 API 的 canonical 导入链仍属于上一项独立未完成任务，诊断镜像不能替代它。
- [ ] 首个样本通过后再建立游戏兼容矩阵，对 NAND 中其余 NPE 游戏记录启动、输入、
  音频、存档、退出和最早失败点，并逐项消除 guest 可见差异。
- [ ] 若 NPE 或其经证据确认的子运行时使用虚拟机，缺失语义应依据原厂 loader/runtime
  clean-room 重建并由 guest 路径调用；禁止在 Web 中实现一份独立游戏、直接跳到游戏画面
  或伪造按键结果。

验收条件：从全新 canonical 镜像冷启动，只用 Web 虚拟物理按键沿
`开始 → 娱乐 → 游戏世界 → NPE 游戏 → 英雄传奇.NPE` 选择并启动该真实 `.npe` 文件；
能连续进行至少 10 分钟可观察的游戏操作，按键、计时、
画面和必要音频正常，支持的存档重启后可读取，并能正常退出回到主菜单。全过程保持
`ROM_HLE=off`、`HLE_UI=off`、`ROM_MISSING=none`、`UNSUPPORTED=none`、
`INVALID_CONTROL=none`。完成标志是“游戏可玩”，不是“菜单可见”。

## 5. 旧路线任务与执行记录（历史，当前顺序见第 8 节）

按以下顺序进行，未完成前不并行扩展新应用：

当前游戏关键路径固定为：`0:\应用程序 原厂建目录/导入链 → .npe 文件头与 loader/ABI →`
`游戏运行时硬件 → 连续游玩和正常退出`。完整 Web 物理键盘与这条路径并行推进，并必须在
游戏前台验收前闭合；不能因为当前五个导航/确认键已经可用就推迟保持、长按、返回和失焦释放。
右下角时钟增量重绘残影也是并行但必须关闭的显示验收项；它不允许由 Web 擦除，也不能因为
游戏路径推进而遗漏。中间任何一项只显示页面、只有静态分析结果或用宿主机替代 guest 行为
都不算通过。

1. [x] 清零 11 项现有回归，恢复全绿基线（2026-08-29：463/463）。
   2026-08-30 当前针对 controller/layout、QEMU overlay map 和 manifest 的回归已通过；
   overlay map/alias audit 均为 missing 0、non-identical overlap 0。新增 resident controller
   及其 Harvard 表之后仍须重跑完整大回归，完成前只称“本轮针对性测试全绿”，不沿用旧的
   `178/182` 失败统计，也不宣称整个工作树已全绿。
2. 写 canonical artifact manifest 和一键 baseline 验证命令。
3. 将 v654/v659 page-lane 修复追溯到 NAND controller 的 external-A0 字节通道和
   正确导入层，并从自然烧录/读取链生成顶栏与 factory 页；v659 只作为诊断证据，
   不是最终 canonical 手工快照。
4. 为完整主菜单建立 raw gray5 golden 和 source/object hash 回归。
5. [x] `0x8C` 状态键、`KEYMAPRET` 有界诊断、64/64 分段短按分类、辞典
   M35→M36→M37 连续输入，以及 M43→M44 跨 modal consumer 输入均已完成；modal 监控
   的 `FP-0x02` 读点已有源码对齐测试。Web `keydown/keyup`、pointer hold、组合/别名、
   失焦释放和 1.5 秒断网租约也已完成，包含快速二击与旧页面迟到 make/break 两类竞态，
   16/16 回归通过。真实 NPE 前台又完成四方向 5 秒长按、四种方向/动作组合、独立
   M28/0x84 返回语义、M55/0xB0 正常退出和严格 1,000 次压力测试。未知实体侧键若后续
   获得真机标签/矩阵证据再补命名，不再阻塞已恢复键盘的用户功能验收。
6. [x] 完成稳定主界面上的开始键闭环：v690 恢复 resident
   `13:0A3E ← 30:0A3E` 主动作事件表并证明 `0x8E → 30:12DE`；v691 恢复 exact
   `24:11BE ← 41:11BE` 的完整 0x184 字节缓冲/绘制准备函数。稳定桌面按真实矩阵
   索引 55 后，guest 自然映射 `0xB0`、完成 Start callback、重绘开始窄菜单，且无
   missing/unsupported/invalid-control。禁止用 Web 画菜单或直接改 guest 状态。
7. [进行中] 旧 v656 已证明右下角叠字发生在 guest back buffer，Web、ST7529、格式化
   字符串和字形源不是首因；当时 `25:77DA` 从 `h0002` 增长到 `h0019` 后返回 0，背景
   恢复被跳过，而 `31:596E` 继续以 `MODE=1` 透明绘制文字。v750 的新证据则推翻了
   “时钟调用自身 release worker 未生效”的解释：三次 `31:590E` 调用均进入
   `2D:CAA6 → 18:66EE`，`30:8B26` 去 pin、`30:3A56 → 31:8ABC`、registry 移除和
   bitmap 清位全部完成，最终 `ACTIVE=0`；相关 exact ROM 映射也没有缺口。旧 v656
   句柄从第 4 次起实际严格由 `27:58E4` 的 240×17 资源和紧随的 44×15 时钟资源成对
   共享/递增。64 槽纯只读 `RESOURCE_PAIR_RELEASE` 已完成并在全新 v750 捕获
   `27:58E4 h0003` 与紧随的 `31:590E h0003`：两次均由 `w8003` 去 pin 为 `w0003`，
   `mask1=1`，节点移除且 bitmap 清位，最终 `ACTIVE=0`；同号 handle 是释放后的正常重用。
   v751 隔离长跑最终为 `CALLS=65/ACTIVE=0`，完整保留的 31 对相邻 footer/clock 调用
   31/31 都满足八阶段、mask、node 和 bitmap 释放契约；因此至少 30 对资源生命周期门槛
   已完成。v752 的四阶段样本又连续看到 `s2 levels=0008/f0 → s3 levels=8008/f>0`，说明
   该样本在 guest back buffer 中先恢复成统一灰阶 3 再绘字；监控器已经收紧为“单一背景
   灰阶 + 后续新增前景灰阶”的判据并通过 21/21 回归。下一步按约 20 分钟预算采集至少
   20 次真实时间变化和一次多位数字边界，同时做 guest back buffer、ST7529 GRAM、gray5
   三层逐像素验收；90 秒运行只捕获 1 次并不足以关闭问题。禁止在 Web/LCD 层擦除。
8. [进行中] v729 已消除开机阶段 `0:\我的邮件\nminbox.pim` 的 resident mode-1 打开失败
   和陈旧 modal 污染：根因是路径 parser 生成 `NMINBOX PIM`，而诊断 FAT 项使用小写 stem；
   精确 `0x20` 比较差及改为大写后的 `RESULT=1/ERROR=0000` 已形成 A/B 证据。干净五键重放
   又确认 selected application=`0x0078`，浏览器四次分配、`18:CFA8` 构造、
   `1C:D462` 布局都成功，最终结构自然包含 `0:\应用程序\*.npe`。静态复核又证明 operation
   byte 1 在 `35:D148 → D410`，会绕过只服务 operation 6–9 的 `31:9E18`、`30:C9A2`、
   `32:A9D2`、`1A:098C`；未命中它们是正确分支，不能再把它们当成当前缺口。这里记录的
   “把 `22:147A` 重定位到 `23:147A`”只是已经推翻的旧假设：v744/v745 动态证明对象字段
   原本就是逻辑 `22:147A`，从 `1D:87AA` 实际命中一次，`23:147A` 为 0 次。当前恢复的是
   原址 exact `22:147A ← 3F:147A+0x51A` 及其闭包，不修改对象字段或 callback 逻辑地址。
   `18:CFA8` 构造和 renderer callback 入口是否执行的诊断任务已经关闭。`1D:831E` 会先从
   对象读取 item count/stride，再逐项调用 `22:147A`；v745 只调用一次并只画 `..`，所以
   下一步必须在 renderer 上游的“目录记录解码/过滤 → item 数组与计数 → `1D:831E`”链找
   第一个真实差异，并仅按 exact 原厂源或已证明的硬件/数据契约修复。

   v731 已把 `31:4200 ← 4E:4200` 及其 `32:E5E4 ← 4F:E5E4` 子调用恢复为 exact
   源，并在隔离实例中让
   `开始/0xB0 → 娱乐/0x86 → 游戏世界/0x83 → 确认/0x86` 四个真实矩阵事件全部完成
   map、guest acknowledgement 和 release。第四步后 application state 自然变为
   `0x0078`，随后却由 `1A:4220/c620` 伪返回到缺失的 `16:0030`。该地址不是新 CPU
   指令或键盘映射问题：对 exact `1A:DEAA ← 37:DEAA` 的完整控制流反汇编确认，函数除
   已映射的 `1A:E038` 顶层表外，还通过数据总线读取六张 `0x0A` 字节的 computed-RET
   表（`1A:E112/E30C/E506/E562/E5BE/E620`）；旧模型读到全零后跳入 `1A:0000`，恰与
   clean-room 大型安装器冲突，最终把保存寄存器误当成 far return。

   当前修复把安装器移入已验证空闲的 `0A:0000..4221`，并只为上述六张表增加
   `soc_rom` 支持的窄 Harvard 数据 alias；不增加 HLE、宿主菜单状态或猜测返回值。
   复核同时否决了一个早期错误候选：六表项使用完整 16 位 `E***` 目标，不会截成
   `00**`；`37:0010` 还是 `37:000E` 指令的扩展字，整段也没有直接 call/jump xref，
   因而不得安装成 `1A:0010` compare 续体。独立 xref 审计随后在完整函数
   `49:6E0C..6FFE` 中找到唯一 `49:6ED6 BD1A 0000`，它按三个 far 参数调用
   `1A:0000`；source `37:0000..098B` 又恰好是从 `LINK #4` 到平衡 `RETS` 的完整
   same-PC 函数。因此 canonical ROM 恢复的是完整、独立的
   `1A:0000..098B ← 37:0000..098B`，不是从扩展字开始的 compare 补丁。证据见
   `doc/disassembly/np560_source_370000_report.md` 与 `doc/disassembly/np560_source_496e0c_report.md`。

   v732 动态复验已证明第四键能从 compare wrapper 正常返回：真实 guest 画出了娱乐
   二级菜单中的 `NPE 游戏/游戏世界/动漫欣赏/数码录音`，`ROM_MISSING`、
   `UNSUPPORTED`、`INVALID_CONTROL` 均为 none。第五个额外确认由 modal 接收后出现
   局部乱码并把 application state 从 `0x0078` 清回 `0x00FF`；最新首个失败边界是
   `18:CFA8` 构造器在 `32:FA06` 返回 0 后走 `18:D098` 零结果退出，而不是旧的
   `16:0030`。下一步要沿 `32:FA06 → 25:5460` 的原厂存储上下文初始化链定位首个
   非零错误码，直到 `英雄传奇.NPE` 自然成为可见 list item；在此之前仍标记为进行中。

   v734 已把独立 exact `1A:0000..098B ← 37:0000..098B` 正式纳入重建 ROM，ROM
   SHA-256 为 `D1B2D578EC4B3805F09F888785D24795B7236C15BCBD730E48DE0323CBE74D51`。
   同一 checkpoint 冷启动及五键重放中，前四键仍全部得到 foreground acknowledgement，
   第五键由 modal 自然显示“无此目录 `0:\应用程序`，请创建！”，画面不再是不可解释的
   局部乱码。新增的纯只读 `NPE_RESOURCE_CHECK` 进一步证明 `25:5460` 的 child 1/2
   均返回 0，child 3 `29:16B0` 返回 `FFFC`；父函数在 `25:5556` 把该值写入
   `A2:2AE0` 后返回 `FFFC`。六张 compare RET 中本次命中的 `1A:E61E` 正确跳到
   `1A:E62A`，误跳 `1A:0000` 计数为 0。由此当前边界不再是 ROM 入口、CPU 指令或
   键盘，而是 checkpoint 确实缺少 guest FAT 根目录 `应用程序`。下一步先以隔离 A/B
   checkpoint 导入真实 `英雄传奇.NPE` 来推进原厂列表/加载器动态取证；该离线导入仅是
   诊断桥，最终仍须恢复可重复的原厂建目录/传输路径。

   v735 诊断 A/B checkpoint 已完成逐字节回读、双 FAT、FTL、FNV 和 ECC 校验：源 NAND
   SHA-256 保持不变；副本 `tmp/np560-v735-hero-fat16-ab-guest-dots.nand` 中
   `应用程序` 位于 cluster 5，guest 风格 `.`/`..` 记录保留，`英雄传奇.NPE` 位于
   cluster 6..256，文件 SHA-256 仍为 `ADEA7C...A8C19`。副本自身 SHA-256 为
   `24CFE6CDA26EDD56D41494791205446886CCECC4E984E284A28AFD322DB2A224`。使用该副本后，
   前三个真实矩阵事件仍成功；guest 开始枚举新目录时由 `1C:D92C` 调到未恢复 resident
   `1F:5BFA`，探针以 `ROM_MISSING=1F:5BFA` 停止。这是当前新的第一失败边界；先完成
   exact same-PC 源、闭包、ABI 和内联 Harvard 表审计，再恢复原厂字节并重放。不得把
   这一新缺页误写成目录导入失败，也不得用宿主列表或假返回绕过。

   v736 已安全关闭该缺页。主函数采用 exact `1F:5BFA ← 3C:5BFA`，范围 `0x0606`
   字节、607 条可达指令、13 个调用、0 unknown/overlap；四个 caller 都传入一个 4-byte
   far pointer。其唯一未恢复叶子不能直接覆盖 `33:5ABA`，因为该地址也是 source
   `33:52AA` 大 worker 的真实内部分支目标；因此 exact `50:5ABA..5AC6` 仅安装到已验证
   空槽 `06:1CF0..1CFD`，并只把复制后的 `1F:5C16` 两字 SCALL 改为 `06:1CF0`。
   v736 ROM 为 2,095,672 字节，SHA-256
   `A12382EB1A206B2ED6F4AD30EE09C8AE5295553794B0A918A44888FF9265756F`。

   使用同一 v735 诊断 NAND 冷启动后，五个真实矩阵事件均 map+ack+release；v735 的
   `1F:5BFA` missing 不再出现，`25:5460` 六个存储子调用全部返回成功，布局
   `2C:87F8 → 1C:D462` 和 render object 都各完成一次，且全程
   `ROM_MISSING=none`、`UNSUPPORTED=none`、`INVALID_CONTROL=none`。但第四步捕获与第三步
   raw gray5 完全相同（SHA-256 均为
   `68AD7294B136F7A2869053BDB9747EE206A04EA5E87607CC314C746CB79FF419`），仍停留在娱乐
   子菜单；第五个确认在 modal consumer 中捕获到未完成/乱码画面。随后已完成独立四键冷重放，
   不注入第五键，并在 0、10、30 秒分别截图；三张 PNG 的 SHA-256 完全相同，均为
   `CDAB8ED593B62B15B789B9ED15E889E061430244620211FF13B6E17CC1C60414`，持续显示旧娱乐
   子菜单，`FILE_ATTACH_FRAME=CALLS:0`。因此已经排除“只需多等一会儿”的解释，当前边界
   确定为“对象分类/布局返回后，到可见 list item 挂接之间”，不是新的 ROM 缺页。
   exact `1C:D462` 的静态消费者显示，`1F:5BFA` 返回先保存到 FP-6；随后依次检查派生记录
   `+0x0C`、对象逻辑字段 `+0x12` 和非零 mask，只有三项均满足才会调用
   `33:5228`、`33:4492` 继续 attach。新的只读 `NPE_OBJECT_MASK` 已在一次独立 v736 四键冷
   重放中取得确定分支：`1F:5BFA` 调用/返回 1/1，记录类型检查 D9B2 通过，但 D9DE 读对象
   逻辑 `+0x12=0` 后直接跳到 DBDC；D9E8 mask 分支未执行，两个 attach 均为 0。进一步对
   exact `1F:5BFA` 复核发现，它自己也先在 5C1E 读取同一逻辑字段并在为 0 时于 5C40
   返回 0，因此 mask=0 与 D9DE 拒绝是同一个上游“对象从未标成有效 list item”根因，
   不是两个缺失函数。对象写环证明该字段只在 `18:D948` 的整字初始化中被清 0，此后没有
   逻辑 `+0x12` 写入；`1C:D4A4` 写的是逻辑 `+0x13=FF`（byte-lane 后显示为物理 `+0x12`），
   不能误当作 `+0x12`，也不能擅自补 1。证据位于
   `tmp/np560-v736-object-mask-route/04-EnterGameWorld.json`。后续静态复核已推翻这里的
   “有效项字段 producer”解释：该观测对象是 `1B:23B8` 的 render object，
   `+0x10..+0x13` 是允许为 0 的 range pair；真正 Game World controller 对象位于外层
   `2F:68A2` 的 `FP-0xC4`，其 ctor 已按原厂分支写自己的 `+0x12`。producer/D01C/强制
   补 1 路线正式停止。四键稳定证据仍位于 `tmp/np560-v736hero-four-key-stable`；五键过早输入证据
   保留在 `tmp/np560-v736hero-game-route`，但不得用它宣称列表已经出现或第五键已经选择文件。

   v737 builder 已纠正一处可证明的旧 overlay 误接。完整 renderer `3E:CEF4..D428` 在
   `3E:D3FE` 原本以一个 far object 参数调用独立 linked helper `2E:2B6E`；此前却把该调用
   错改到 relocated input clone 的 `11:2B6E`。后者只是 `2E:1752` 大输入函数内部尾段，
   没有 LINK，依赖输入 caller 的 R11 frame，不能作为 renderer helper。exact
   `4B:2B6E..2CF6` 是闭合的 `LINK #3 ... UNLINK/RETS` 函数，共 `0x018A` 字节、170 条
   可达指令、2 个直接调用、0 unknown/overlap；其 `32:EC6E` 和 `33:66E2` 依赖及下游
   `27:507C`、`31:4BAC` 已在现有 builder 中闭合。v737 因此保留 input clone 内部 18 个
   `11:2B6E` 调用，恢复 renderer 原始 `2E:2B6E` 调用，并把 exact 4B body 安装到该 linked
   目标；没有修改 `obj+0x12`、返回值或 guest 状态。ROM 为 2,095,672 字节，SHA-256
   `408E8952AACE5DB040DC44FC200C0CD4B3759641E25F30659F275C11A996C3F3`；针对性 builder
   回归通过。随后独立 overlay 审计发现旧 QEMU 尚未为 `2E:2B6E..2CF7` 提供精确的 writable
   executable late-overlay backing；首次 v737 隔离启动因此无效并已停止。该硬件缺口现已按
   严格 `0x018A` 字节补齐，并连同 `29:D0BA`、`2F:B644`、`2D:F47C`、`30:6082`
   四处新发现映射一起完成 overlap/missing 审计和 QEMU 重编；不得再把它列为待办。

   对 `obj+0x12` 的历史追踪还纠正了“event 0x68 属于当前浏览器”的误判。
   `0x68` 是 10-byte application catalogue 的索引，不是四键输入事件；row 0x68 指向
   “低级格式化”的 `52:FFDC → 1C:7052` ctor，其 D01C 持久记录与 NPE 浏览器无关。当前
   “游戏世界”实际 catalogue index 是 `0x2E`、field4/application state 是 `0x78`：row
   `21:AC10 = 002E 1602 0001 0052 5226`，descriptor `52:5226` 的 ctor 是 `2B:06D6`。
   catalogue 证据仍有效，但“沿此链寻找谁把 render object `+0x12` 写 1”的任务已取消；
   两类对象不得混同，也不得恢复或强行调用无关 `1C:7052`、使用 D01C 或直接补字段。

   最新 source/target 审计恢复了原厂 overlay 生命周期：`2C:7E18..9B94` 是 resident
   `0F:7E18` 的完整 source image，13 个原始 caller 全部直接调用 0F，2C entry caller 为 0。
   ROM 先嵌入 `0F:7E18..9B96`，QEMU 给 `0F:7E92+0x1E` computed-RET 表增加只读
   Harvard data alias；随后 `49:8744..8930` 才安全安装到原目标 `2C:8744`。controller
   本体、第一批 11 个 storage overlay、第二批 resident `0D:B1C0`/`1E:9E66` 和九个
   application overlay 均已进入 builder/QEMU/manifest/定向回归。v741 干净四键重放已自然
   到 `APPLICATION_STATE=0078`，但 guest 前后帧缓冲都残缺；v742、v743 又分别验证 exact
   `33:384E ← 50:384E+0x22` 与 `25:F992 ← 42:F992+0x3BA` 后画面 hash 仍未改变。v744
   纠正 `1D:83DC` 对冲突 helper 的调用后，`22:147A` 首次真实命中；v745 再恢复 exact
   `22:147A+0x51A`、`2E:0192+0x192`、`32:F0E0+0x3E`，guest front/back 由残缺块推进为
   一致的原生浏览器框和滚动条。callback 入口已经闭合，当前只显示 `..`、尚无
   `英雄传奇.NPE`；callback 仅调用一次，证明 item model 在进入 renderer 前就只有一项。
   下一步沿上游记录解码/过滤、item 数组建立和列表计数找首个错误执行点。
   这些仍只是必要边界修正，不是 NPE 动态可玩结论。

   通过标准是 `英雄传奇.NPE` 由 guest 自然变成可见且可选择的 list item，并能继续进入
   `1B:2A88 → 2E:D34A` 加载链。诊断 NAND、Web 重画、显存修补、猜表/对象内容或把 flat
   PRG 资源同址映射成 RAM 均不得升级为最终方案。
9. [进行中] v840 已关闭第一次游戏动作的 `29:CE22` Harvard code/data 不一致：原厂
   `09:E000` guest 安装器、完整 code-page RAM 和有界 store 镜像已经动态取得
   `W:2E05`；30 秒/18 边沿、600 秒/120 边沿和严格 557.204 秒/1,000 边沿三轮持续
   游玩均通过，最后一轮 `candidate/map/ack=1000/1000/1000` 且一个 Start 正常退出、
   root render `30→40`。v858 又以真实动作键闭合对象 0 的一次性物品 UI：首次
   `guard/pass/commit=0/1/1`，等待 5.5 秒后出现“布鞋+1”说明界面，第二次
   `guard/reject/commit delta=1/1/0` 且画面和 segment 52/53 均不变。短按和对象动作
   压力已关闭；v859..v873 又关闭长按重复、四方向组合、独立返回语义和 Start 退出。
   v882 又用三层只读寄存器观察器排除输入期的 `F14C/F11E` 和
   `REG27/39/41/A7/B9`：两组都闭合到键盘扫描/IRQ 恢复，不是音频。v894 将
   `03:4010` 观察范围扩展到游戏态全部 275 个静态调用点；“布鞋”首次提交新增的 7 次
   读取为 section 1 的 4×29670-byte 连续场景块、section 0 的两个 4-byte 索引和
   section 1 的 266-byte 块，全部成功且没有访问 section 16..37。说明文字尾段又闭合到
   `22:C7FC` 的 NUL 字符串读取循环。资源/SFR 证据分别见
   `doc/games/np560_npe_stream_resource_boundary.md` 和
   `doc/audio/np560_audio_hardware_boundary.md`。v897 将地图 1 扩展到 128 状态、58 坐标、366 条
   转移和 128 动作点；17,590 次读取、2,194,907 bytes 推进后上界仍严格为
   `0x13291A`，地图 index 始终为 1，证明继续盲走同一地图不是有效音频定位手段。
   v901 又把 `03:401C` 闭合为 `(stream, signed offset, whence)` seek wrapper，并用
   22/22 动态 call/return 验证绝对定位到图形块的完整序列。随后发现旧观察器是在 mode-2
   loader 结束后才启用，所以 v891/v897 的 `0x13291A` 上界只描述运行期地图主循环，不能
   外推到完整启动。v905 将只读观察点前移到原厂 `2F:B726 → 1F:D1A6` mode-2 入口，干净
   启动取得 1,142/1,142 reads、28/28 seeks，明确命中 section 13 起点/内部和 section 14
   起点。v906 的独立高段环又闭合 4/4 次 section 13 read：
   `24:AD92` 4 bytes、`24:ADB8` 1 byte、`24:AE42` 4 bytes、`24:AE68` 4 bytes；位置依次为
   `13291A..13291F` 与 `132B0E..132B16`，返回/错误全为成功。`24:AEF4` 随后只 seek 到
   section 14 起点，未见 `03:4010` 推进；静态结构与动态数据共同表明 `24:ACBA` 是
   section-13 索引/描述装载候选。离线字节验证随后把它完整分类：四个读值为
   `0x1F4,0x10,0,0x384A`；section 14 大小 `0x384A0 = 16 × 0x384A`，每条记录均为
   10-byte `(kind=0x1001,x=0,y=0,w=240,h=120)` 头加 `240×120/2=14400` bytes 载荷。
   新增 `analyse_np560_npe.py` 结构检测和回归会自动验证该布局，故 section 13/14 已闭合为
   整屏位图索引与 16 帧 packed-4bpp 图像库，可排除为音频。对 `2C:B8C2` 及 section 15
   的复核也已闭合：函数读取 total+10 类权重并以 `03:4124` 做累计随机选择；Hero section
   15 是 5,385 项 u32 offset 表、`FFFFFFFF` sentinel 和 GB18030 A/B/C/D 选择题记录，
   分类计数 `[1100,4285,0,...]` 之和正好为 5,385。离线检测器验证前 32 项编码/结构，故
   section 15 是随机题库而非音频。下一音频边界固定为：沿 section 16+ 的真实 caller 及
   战斗/地图切换入口继续追踪，直到首次
   资源 buffer consumer 与 DMA/SFR 闭合；不得把 21-byte 结构、冷启动一次性
   `F018/F01E=0` 或图形大块读取直接命名成音频。

   剩余必要音频和可用存档。并行补齐 18 个
   `NP560 RPG2.1` 样本的来源记录、容器结构和原厂文件 API canonical 导入链。仓库合成的
   `lirt*.nwf` 不计入最终游戏样本。
10. [最终目标进行中] 只用完整虚拟物理键盘沿
   `开始 → 娱乐 → 游戏世界 → NPE 游戏 → 英雄传奇.NPE` 启动真实游戏、持续操作并正常
   退出的核心链已经通过；剩余 P7 完成条件是 v840 长跑/压力回归、必要音频与存档，以及
   不依赖诊断 FAT 注入的可重复 canonical 导入。只有这些用户功能也闭合后才称模拟器完成。

- 2026-09-02 v922 修复音效设置与辞典 state-4E 的 `33:6BE2` 执行地址碰撞。旧映射把
  source `50:6BE2` 的四指令 predicate 永久覆盖到 flat 设置 renderer 的顺序路径，
  `M11/0x94` 因此在无远调用帧时执行 `RETS` 并进入 `C7:0E00`。现将 exact leaf 重定位为
  `5F:6BE2 ← 50:6BE2`，由 reconstructed guest installer 只把 state-4E 的
  `0D:2F48`、`0D:3A1E` 两处 call 改到新槽；`33:6BE2` 的原厂设置代码和同地址 NAND
  data buffer 均不再受 code alias 影响。冷启动原厂路径进入“音效开关”后，
  `M11/0x94`、`M27/0x95`、`M52/0xE1`、`M60/0xE2` 都由 modal guest 正常接收，且同一
  实例随后切入辞典继续消费 `0xE9/0x83`；全程
  `INVALID_CONTROL/ROM_MISSING/UNSUPPORTED=none`。证据为
  `tmp/v922-sound-editor/`、`tmp/v922-sound-toggle/`、
  `tmp/v922-dictionary-after-settings/`；v922 ROM SHA-256 为
  `2949C25330AEF47B348258F889779EA064ED6C2A9AF25FC22D761B2874A72BB9`。尚未把这些键中
  任一个命名成开关/确认：当前“1.”画面未变化，下一步仍须由事件分支和 `10:D016` 自然
  持久化写入确定真实语义，再沿该开关的冷启动差分定位音频 SFR/DMA。

- 2026-09-02 v923 补齐 resident `15:F0EE` 的六项确认动作表在 Harvard 数据总线上的
  12-byte 只读视图。输入函数对 `0x86` 返回后，原厂 handler 在 `15:F346..F360` 从
  `15:F362` 取 near-PC 并以 `RET` 分派；修复前 code view 已有
  `F36E,F556,F73A,F8AA,FB8A,FA1A`，但 ordinary data backing 全零，且 QEMU 缺少与
  其它 computed-RET 表相同的 data alias。现在只将 reconstructed SoC-ROM 的
  `15:F362..F36D` 暴露给 data bus，没有替代提交逻辑。冷启动重走相同设置路径后，
  `M53/0x86` 能从“1.”窗口正常回到主菜单，
  `ROM_MISSING/INVALID_CONTROL/UNSUPPORTED=none`；证据为
  `tmp/v923-sound-editor/` 与 `tmp/v923-sound-enter/`。本次确认没有写 `10:D016`，说明
  仍需先找出页面的真实改值动作/资源，再用自然持久化写入判定开关语义。
  同轮静态闭合了下一层 exact kind 表：`14:B868..B930` 读取对象 `+8` 的
  `0x51..0x58`，通过 `14:B932` 八项 computed-RET 表分派；原厂表为
  `BDB2,BA5C,B95A,BAC4,BB28,BD58,BA06,BE18`，其中 kind `0x55` 精确进入
  `14:BB28` 并持久化 `10:D016`。v923 QEMU 已把这 16 bytes 从 reconstructed SoC ROM
  映射到 Harvard data bus，live physical view 与 code view 都为
  `B2BD5CBA5AB9C4BA28BB58BD06BA18BE`。更早的 `0x80..0x86` 分派也已机械闭合：
  指令编码的 `14:B716` 是偏置基址，原厂以原始 event 直接计算 `B716+event×2`，所以
  实际七项表位于 `14:B816..B823`，exact source 内容为
  `C11A,C300,C4E6,C4E6,C762,C762,B868`。新增第二个 14-byte Harvard data alias 后，
  完整确认链为 `0x86 → 14:B868 → kind 0x55 → 14:BB28 → D016 writer`。下一步不再反推
  分发表，而是定位哪个原厂菜单/对象生成 kind `0x55`，再验证其自然提交和冷启动差分。

- 2026-09-02 v924/v925 纠正发音设置入口并恢复两段缺失 resident ROM。source
  `31:A744..B766` 是第 3 项“音量调节”的完整 `0x1024`-byte 函数；其中立即数
  `0x55` 是矩形 `(2,18,235,85)` 的 bottom，不是对象 kind，函数内也没有直接
  `SCALL 14:B768`。真正第 5 项“音效开关”由 source `36:CC7A` 五项 selector 表指向
  `1B:A454`；其完整 source 副本是 `38:A454..ACBE`，大小 `0x086C`，入口会读取
  `10:D016`，而旧目标范围此前全部为 skeleton fill。v925 已精确恢复该函数，并为它的
  `1B:A6BC` 十七项 computed-RET 表增加 34-byte 只读 Harvard data alias。下一步固定为
  从第 5 项单测真实事件 `0x82/83/84/85/86`，同时记录 `A4:56C0/568C/567E`、
  `14:B768` 对象 kind 和 `D016/D019` writer。当前仍不得声称 `1B:A454` 是 kind-`0x55`
  producer：它直接可见的共享 `32:F38A` 路径构造的是 kind `0x58` 并写 `D019`。

## 6. 完整模拟器最终验收清单

以下已勾选项保留对应旧版本的验收记录；切换到 VMA03 后，最终交付仍须按第 8 节
在同一份可重复生成的运行基线上复验，不能直接继承旧 hash 的长跑或边界测试结论。

- [ ] 只提供原厂升级包即可重复生成系统运行所需 ROM/NAND 产物；游戏验收另需一份
  可校验来源的原厂 `.npe` 内容文件，除非后续证明它确实封装在升级流中。
- [ ] 默认 `ROM_HLE=off`、`HLE_UI=off`，Web 不包含系统逻辑替代品。
- [ ] 所有支持场景均为 `ROM_MISSING=none`、`UNSUPPORTED=none`、
  `INVALID_CONTROL=none`。
- [x] 主菜单像素正确、可操作；`英雄传奇.NPE` 可启动、持续操作并返回。
- [x] 时间连续刷新无旧字形残影；边界时间转换与 raw gray5 golden 一致。Web 只呈现 guest
  输出，绝不代 guest 清除或恢复时间背景。
- [x] Web 全部输入经过真实 8×8 矩阵和原厂 guest 扫描/映射链，无前端菜单捷径；64/64
  独立短按、NPE 四方向严格 1,000 次压力、返回/退出和失焦释放已通过；保持/长按与
  方向/动作组合也已由 v859..v871 关闭。
- [x] 可沿 `开始 → 娱乐 → 游戏世界 → NPE 游戏 → 英雄传奇.NPE` 选择并加载真实游戏，
  连续至少 10 分钟可观察游玩并正常退出；另有严格 1,000 次单事件回归。存档（若游戏
  支持）和必要音频仍作为独立未完成项，不再阻塞这条核心链的勾选。
- [ ] 验证 NPE 游戏的必要音频输出，以及至少一条游戏实际支持的存档/恢复路径。
- [ ] LCD、键盘、NAND、ECC、RTC、定时器、中断、音频、USB 的已声明功能都有回归。
- [ ] 数据可持久保存，错误和掉电路径可恢复。
- [ ] 全部自动测试通过，golden 和 artifact hash 可重复。
- [ ] 每个推断 resident 行为都有文档；无法证明的原厂细节明确标为未知。

本文件是后续工作的唯一主路线。每完成一个里程碑，应在这里勾选并把证据、测试命令、
artifact hash 和仍存在的未知项同步到相应逆向文档。

## 7. 2026-09-05 VMA03 原生 PIM 与 NPE 冷启动闭环

- `31:9E44` 是共享调用点，启动时实测类别顺序为
  `05 → 04 → 03 → 08 → 0E → 08`。旧的一次性 hook 在第一个 `05` 就被消耗，发生在
  resident 文件系统完成 mode-2 `USERINFO.SYS`/根目录状态之前。现在的 checkpoint
  provision ROM 使用两阶段 guest hook：`02:7000` 只在类别 `0E` 时把调用点武装到
  `02:7600`，随后只在晚期类别 `08` 调用中创建 PIM，其余调用均原样转发给 `1E:6444`。
- provision v6 全程调用原厂 resident 文件 API：`1F:1F1A` mode 0 打开/创建、
  `17:E3EE` 写入恰好 `0x4A` bytes、`24:EAEC` 关闭；返回 FILE 对象为 `50:FE74`，
  `ROM_MISSING/INVALID_CONTROL/UNSUPPORTED=none`。checkpoint 为
  `tmp/np560-vma03-native-pim-v6.nand`，provision ROM 为
  `tmp/np560-system-v380-vma03-pim-provision-v6.bin`，其 SHA-256 为
  `b195bc4aa9cd2e62d85e2277b28a823cad768d73a536e7fa7b63ebcb90a34dfd`。
- 改回普通 VMA03 ROM 冷启动同一 NAND 后，晚期 PIM mode-1 open 再次取得
  `50:FE74`，证明文件已由 guest FTL/NAND 路径持久化，不依赖 host 文件服务。启动先进入
  原生“系统初始化，请等待……”格言页，物理 `M55/0xB0` 使应用状态
  `00FD → 00FF` 并由 root renderer 绘制完整主菜单；这不是 Web 菜单捷径或 HLE ROM
  服务。尚未证明真机是否由其它上电状态自动产生该边沿，因此默认启动仍不预置 `B0`。
- 从该主菜单继续沿真实矩阵进入《英雄传奇》：`M53/0x86 → M37/0x83 → M53/0x86`
  进入 NPE 列表及游戏，原生 LCD 已显示“新的征程”菜单和地图场景。场景初始化计数为
  `GRID 1/1、INIT 1/1`，方向回归后 `DRAW 10/10、ITEM 20`；四方向短按测试和一次
  `M55/0xB0` 退出通过，18.1 秒、4 actions、应用状态 `0078 → 00FF`、root render
  `30 → 40`。证据位于 `tmp/np560-vma03-native-pim-v6-play-verified-v2/`，场景截图为
  `tmp/np560-vma03-native-pim-v6-after-confirm.png`。
- 本轮暴露的自动化问题不是 guest 故障：旧 route 每步仅等待 0.35 秒，最后一个确认会在
  NPE 页面完成切换前被消费；即使固定等待 2 秒，首次装载仍可能停在“诺迷工作室”启动
  画面。监控器现默认等待 3 个连续相同的 completed LCD frame，并在最后一次确认前等待
  可重复的 Hero 行程菜单 raw-gray5 指纹 `5e5577bd…9498947`；`--route-settle` 仅作为关闭
  帧同步时的后备。游戏 ready gate 也改为要求实际地图
  `DRAW>0` 且调用/返回平衡，不再要求只有方向输入后才出现的 `GRID>0`。动作间隔设为
  1 秒还可能撞上 resident 去抖窗口，压力回归继续使用已验证的 5 秒节奏。下一步用更新
  后的 route 从干净冷启动做一次端到端无人值守回归，再处理必要音频和实际存档/恢复路径。
- 冷启动无人值守回归已由 `tmp/np560-vma03-native-pim-v6-cold-e2e-v3/` 闭合：脚本自动
  识别 `00FD` 并发出真实 `M55/0xB0`，完整执行
  `BootStart → Entertainment → GameWorld → NPEList → Hero → NewJourney → StartGame`，
  等待 splash 自动结束后进入地图，依次消费 Down/Right/Up/Left，再以一次 Start 返回
  完整桌面。游玩段 17.188 秒，应用 `0078 → 00FF`，root render `20 → 30`，全程
  `ROM_MISSING/INVALID_CONTROL/UNSUPPORTED=none`。manifest SHA-256 为
  `9e1d6988e0b3806dd9f809813454992506721ed4c45ada2d86c8e569eaaa9ee0`；game-ready 与
  final-desktop raw gray5 SHA-256 分别为 `5c2fbbb1453ae34da4c2d7713997fd2345016829e1e0042e32e968c81bb5073d`
  和 `b82368f7aed3527263986cf6938f57f952351c0cca8d58759aba89e396bea8f9`。VMA03 普通 ROM
  加 guest 原生 PIM checkpoint 的“冷启动→主菜单→NPE 游戏→方向输入→退出”核心链至此
  闭合。短程闭环不替代稳定性验收；后续先执行第 8 节第一阶段，再推进必要音频和实际
  存档/恢复路径。

## 8. VMA03 架构决策与后续执行顺序（2026-09-05）

### 架构职责与修正原则

- [x] 确立 VMA03 为后续主线：QEMU 负责 DMCU、代码/数据地址映射、RAM/ROM 和外设；
  原厂 guest 固件负责菜单状态、绘制、文件管理与 NPE 游戏执行；Web 负责呈现 LCD、
  传递物理矩阵键和必要的宿主音频播放。
- 遇到新故障时，先核对取指/数据视图、银行选择、启动顺序、栈及外设状态与原始固件
  是否一致，再判断是否有真正的 resident 缺口。每个新补丁都须记录源地址、目标地址、
  触发证据、适用启动模式和退出条件。
- 当前重建 ROM 中的原厂函数副本、推断的启动胶水和临时桩应在 manifest 中分别标识。
  仍需要重建的部分必须由普通 guest DMCU 代码执行，并保留其来源和未验证语义。

### 第一阶段：固定可重复的 VMA03 基线

- 本轮进一步闭合花屏首因：当前 NAND 物理块 `0x890` 中仅 `0x22421..0x22423`
  三页是正确 lane 编码，其余 61 页仍是 raw-package 字节。“学习/辞典”被旧局部
  修补覆盖，“网络”跨出其边界，“记事/系统”连头部也未换序。新
  `audit_np560_package_block.py` 从 checksummed 原包生成诊断副本，
  `verify_np560_toolbar_frames.py` 直接用原包校验每帧全部 5,280 顶栏像素。
  初始往返 9/9 帧、随后单矩阵扫描五轮往返 41/41 帧均零差异，每次映射/消费恰为 1。
  原用户花屏被同一校验检出 1,262 像素差异。9 项定向单元/原包测试通过。
  - [ ] 将换序落实到 USB staging / 原厂 burner / NAND 的正确生产层，淘汰旧局部
    页面修补依赖；诊断副本不能替代自然导入链验收。
    - 已落实调试 RAM 注入边界：原厂 loader `00:1950` 的 `MOVB [R8++], RB1`
      与 DLL 原样传输链有静态证据。`burn_np560_stream.py` 改用共享 transport 编码，
      保持命令数值字段不变；实际 QEMU 原指令在两个银行各写 512 字节，与编码零差异。
      证据 `tmp/np560-usb-store-lanes-v2/manifest.json`；RB1 是 R0 低字节，不能与
      内存的高字节优先规则混淆。
    - 新 `verify_np560_burn_payload.py` 用 factory/OOB 唯一映射核对原包，而非搜索拟合。
      旧输入和最小 factory-only 输入的实际原厂首 48 KiB 烧录均为 0 字节差异、96/96 ECC
      正确；包内 burner 与独立文件版本不同，完整流使用包内版本。
    - 全量输出 `E:/qemu-dmcu-build/np560-usb-burn-full-v1.nand`，SHA-256
      `9da1cc971c75fa58c1debe8d04edd8b59acb428de18b21da79d1f50a18576ef3`：完整原包
      43,963,316 字节零差异，85,866/85,866 对应 ECC 正确，全 NAND 存量 ECC
      86,367/86,367 正确。普通 ROM/PRG 零按键、零 host 内存修改冷启动约 59.14 秒显示
      清晰主菜单，首顶栏连续三帧 0/5,280 像素差异。未添加 PIM 或手工资源。
      证据 `tmp/np560-usb-burn-full-v1/` 与 `tmp/np560-usb-burn-full-boot-v1/`。
      同一新镜像实例随后做五分类往返：单矩阵扫描与普通短按各 8 次操作，分别 9/9 帧
      顶栏零差异，每次恰有 1 次 map/foreground ack，普通路线均观察到释放；证据
      `tmp/np560-usb-burn-full-menu-v1/`。未改 golden 或更换期望分类。
      此输出从 v3 起步并强制格式化，尚须全 guest FTL、NPE、最小出厂输入全流验证；
      多轮压力与长按/USB FIFO/枚举不在已完成范围，因此父任务仍不勾选。
    - 静态确认 UpdateAll 命令 27 返回 `-12` 才进入分区/格式化分支；现有 harness 仍为
      固定序列，须记录 `50:001C`/ProgramGetResult 并实现错误分支，不能忽略任意错误
      或把强制重格式化等同于原厂所有输入的默认流程。证据和命令见
      `doc/storage/np560_usb_burn_transport.md`。
  - [ ] 追踪普通 held-level 路线的重复消费：`repeated/` 第 32 次操作出现 2 次
    candidate/map/foreground ack，导致从学习多走到开始菜单。不是新花屏，但使
    预设分类路线失败；不得靠更换期望分类或把布尔 delivery 当计数使测试转绿。
    保留 `tmp/np560-menu-lanes-regression-v1/repeated-pixels.json`，单扫描回归只隔离
    证明了绘制链，不覆盖真实长按/释放时序。音乐和 NPE 长跑未在新 NAND 上验收。
- 2026-09-05 用户在 8807 复现一级菜单花屏，已只读保留现场
  `tmp/np560-user-corrupt-menu-8807/`，说明见 `doc/display/np560_vma03_menu_corruption.md`。
  原生 LCD 与 front buffer 均可见顶栏错位；无 CPU fault 不代表画面正常。
  首次顶栏 source/object 按各自总线字节顺序归一后 2,650 字节全部一致，但该观察器
  只冻结首次装载，不能代表后续分类。切换“记事/系统”的资源记录已出现
  `size1600,ff00/h0000/st503`，区别于正常 `size00f0,0016/st4ff`。上项新证据已将
  它与“网络”的主体像素损坏统一到 NAND 混合字节序。不得改 Web 像素或补成功返回掩盖。
  先给每个分类分别保留资源源字节、完成对象和绘制结果，再在隔离实例做单次切换、
  往返/连续切换及选中态的逐像素回归；未关闭前不称主菜单已稳定。
- 2026-09-05 生命周期诊断实现与故障注入证据见
  `doc/web/np560_web_lifecycle.md`：已加入独立 health、唯一持久日志、构建/镜像哈希、
  退出码观察、端口预留和失败清理。`tmp/np560-web-lifecycle-integration-v2/` 已通过
  真实子进程故障注入；历史 8807 退出原因仍未知，当前用户实例未重启。
- 本轮自动游玩回归在行程菜单整屏指纹等待处失败，但原生 LCD 已显示正确行程菜单。
  原始失败保留在 `tmp/np560-vma03-lifecycle-ten-minute-v1/`；未修改 golden。
  确认键的重复计数、帧指纹差异和等待条件须继续定位，修复后才能重跑无人值守冷启动。
  人工确认一次真实矩阵键后的长跑另记在
  `tmp/np560-vma03-lifecycle-ten-minute-resumed-v1/`，已通过 600 秒、120 次方向操作
  （四方向各 30 次）、一次 Start 退出，应用 `0078→00FF`、root render `20→30`；
  原始最终 LCD 已目视复核为完整桌面。此项不等于全自动导航已通过。
- [ ] 固定运行配置和生成入口，记录升级包、ROM、QEMU、前端及 NAND 初始内容的身份；
  将已验收 manifest、最小原始帧和关键诊断从临时实验目录整理为可维护的回归证据。
  逆向说明放 `doc/`，生成、审计和测试工具放 `scripts/`。
- [ ] 在当前 VMA03 基线上完成顶部全部分类、开始菜单上/下、确认/返回、连续菜单切换
  的状态与像素回归，再走完 `开始→娱乐→游戏世界→NPE 游戏→英雄传奇.NPE`。
  按键映射计数、guest 选中字段、最终 LCD 必须相互印证。
- [ ] 迁移并重跑至少十分钟持续游玩、严格 1,000 次单事件、长按/组合键、失焦释放、
  Start 退出和时钟跨位刷新回归，记录同一构建的故障、帧和输入证据。
  - [x] 上述 VMA03 人工确认后的十分钟四方向长跑与 Start 退出；千次严格单事件等
    其余项目仍未通过，不整体勾选。
- [ ] 固定 Web/QEMU 启停和实例识别，保留退出日志及返回码；解决用户测试期间服务退出
  的原因，并验证重启、浏览器重连和多标签输入释放。此前 `8807` 连接被拒绝后已重启，
  但退出原因尚未确定，不能将重启恢复记成稳定性问题已修复。

### 第二阶段：逐项审计、淘汰旧重定位和补丁

- [ ] 列出旧 overlay 安装器、单地址别名、调用重定位和返回桩，标注在 VMA03 下哪些
  已由正确映射或原厂装载流程覆盖，哪些仍被真实调用；未命中某次测试不能单独证明无用。
- [ ] 每次只停用一组有证据可淘汰的补丁，比较取指字节、数据读写和调用/返回轨迹，
  通过第一阶段相关回归后再移除代码。先保留基线产物和可回退记录，再清理过期产物。
- [ ] 将仍必要的启动胶水整理为最小、可审计的 guest 代码；原厂没有覆盖的 resident
  契约继续明确列为推断，不把“能够游玩”写成“完整 mask-ROM 已恢复”。

### 第三阶段：补齐音频、存档与自然初始化

- [ ] 复现用户报告的音乐播放器无法播放：确认原厂支持格式和样本来源，按文件打开、
  读取/解码、DSP/音频设备、宿主输出逐层采集，不能预先断言只差 Web 音频输出。
  验收实际播放、停止和返回菜单，并与 NPE 音频分别记录。
- [ ] 以原厂声音设置和游戏实际触发的资源消费者为依据，闭合声音读取、DSP/寄存器、
  DMA/定时输出至宿主播放的路径；确认三处临时音频返回桩的真实契约后逐项替换。
  必须取得可听输出和相应 guest/硬件活动证据，才能完成音频验收。
- [ ] 找出《英雄传奇》实际支持的存档入口，由游戏和原厂文件系统写入 NAND，完成退出、
  停机、重新冷启动和读取存档，验证可恢复的游戏状态。游戏未支持的保存方式不作为
  原厂功能推断；PIM 文件可持久化也不能替代游戏存档验收。
- [ ] 从原始升级包与可校验的真实 NPE 文件重建 ROM/NAND，明确游戏导入及 PIM 初始
  内容的来源；将 provision 流程脚本化并继续追踪原厂自然初始化条件，最终消除对
  手工临时 checkpoint 的依赖。
- [ ] 继续验证 `00FD→00FF` 的上电条件和 Start 事件语义。2026-09-05 隔离实例已在
  零矩阵输入、零键盘事件下自然进入 `00FF`；不能再断言必须 `M55/0xB0`。
  证据 `tmp/np560-vma03-journey-natural-route-v1/00-before.json`：写入者为
  `1D:F344`，与 source `3A:F340` 的 `00FF` 写入后 PC 一致（反汇编见
  `doc/disassembly/np560_source_3af2ec_natural_desktop_reachable.asm`）。仍须重复冷启动，确认
  回调触发条件及耗时，区分自动进入桌面和 Start 展开/关闭菜单，不默认注入 B0。

完成条件：在上述同一 VMA03 交付基线上重复生成、冷启动、进入并持续游玩真实 NPE
游戏，具备必要音频和游戏实际支持的存档/恢复能力，并正常退出；所有保留的重建行为
与未知边界都有记录。只有这些条件全部满足，才将第 6 节更新为最终交付验收通过。
