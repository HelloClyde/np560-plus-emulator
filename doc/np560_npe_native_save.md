# 英雄传奇：原厂音效关闭分支与原生存读档

日期：2026-09-06。当前证据包括正常菜单加载、第一场景移动、动作、退出重进，
同进程原生存读档，以及非默认进度落盘后的跨进程原生读回。后续又完成了第二槽后院位置与金钱奖励
由修复后核心冷读回（见末节，writer/reader 核心不同）。**声音开启分支、完整玩法及完整存档状态仍未完成。**

同日诊断更正：下文历史 map 列来自误读 `52:7A66` 的旧接口，不能独立证明地图恢复。
位置/方向/offset、NAND 编程及跨进程读回证据保留；真实地图字段及后续实际切换见
[地图切换与对话](np560_npe_map_transition.md)。

## 运行条件与保真边界

QEMU 为 `4b70b03ecc9a1212a458051d113f1d741ac5b6d136ba7178ae490e5c5fa2634a`。
PRG、严格 codec 空洞 ROM 与 [设置持久化记录](np560_native_settings_persistence.md) 相同。
输入 NAND 为原厂界面设置音效“关”后保存的：

`E:/qemu-dmcu-build/np560-native-settings-persist-20260906-v1.nand`

SHA-256 `6abc62e96dd73322532f122029536418bfefc2f85bd82be89cbf3935bf2028d8`。
全新 reader 由原厂启动读回配置 `50:B87A=1`；没有宿主修改该值、调用游戏入口或补画。
没有为本次游戏操作更换 ROM、增加成功桩或修改 PRG。

这与旧实验镜像直接强改 gate 的来源不同，但仍只覆盖音效关闭这一种原厂配置。
声音开启时最近已知入口仍停在 `02:ACD8`，其它流后端及初始化桩仍未补齐；
不能用此分支替代整机音频目标，也不能因没有显式 trap 宣称所有 resident 服务正确。

## 正常进入、动作与退出

退出音效设置的第一个 M55 回到学习桌面；第二个 M55 才打开开始菜单。
随后确认娱乐、下选游戏世界、确认进入原厂 NPE 列表、确认《英雄传奇》，
实际画面显示“新的征程 / 再续前缘 / 退出游戏”。

确认“新的征程”后等待原厂装载完成，出现第一场景；再次确认产生“得到”弹窗。
两次方向操作由原厂控制器将 `(7,1)` 改到 `(7,2)`，再改到 `(8,2)`，
原生 LCD 上人物也显示在对应的新位置。这里不是完整关卡、所有动作或长程玩法已通过。

在场景按 M55/0xB0，原厂返回完整桌面，随后还能重新进入游戏。
这一次退出的 NAND PROGRAMS 始终为 48、COPIES 为 0，**直接 Start 退出没有保存进度**。

文件列表和游戏画面可能在按键消费后继续异步装载。中间截屏仍保留旧菜单时先观察，
不连续发下一键或把按键已消费当作新页面完成。此次短序列逐帧查看了真实页面。

## 找到真正的存档入口

原厂控制器 `1A:1372..1392` 检查事件 `008E`，将 `52:7934` 的模式切到 6，
设置初始化标记。当前 live `1A:1312..13AD` 共 156 字节与原始 PRG
`0x171312..0x1713AD` 完全一致，SHA-256
`e805ed291ab29d3bbc742fe2d93b203eb2c49575e50ccbd0b4c8a147a0832e20`。
静态入口参见 `np560_source_371312_new_journey_controller_reachable.asm`；其 PC 使用旧 source 映射。

由矩阵 M4 产生原厂事件 008E（Web F4）后，实际弹出“属性 / 仙术 / 物品 / 系统”。
下三次、确认“系统”后，菜单是“读取进度 / 存储进度 / 游戏设置 / 结束游戏”。
下选“存储进度”、确认后出现三槽，初始“一 0 / 二 0 / 三 0”。

## 同进程原生存读档结果

第二次新游戏的保存位置为 map=1、x=7、y=1、offset=(1,11)。
在第一槽确认保存后：

- 原厂自动回到场景，NAND PROGRAMS `48→560`、ERASES `11217→11225`、COPIES `0→502`。
- 随后通过普通下、右输入移动到 `(8,2)`，地图和 offset 不变。
- F4 → 系统 → 读取进度，实际槽位变成“一 1 / 二 0 / 三 0”。
- 确认第一槽后，原厂回到场景，位置恢复为 `(7,1)`，方向恢复为 1，offset 仍为 `(1,11)`。
- 本条链无 ROM_MISSING、UNSUPPORTED、INVALID_CONTROL，NAND ERROR=0。

槽位从空到有效、实际 NAND 编程、移动后的原厂读回与画面共同支持本次结果；
不是以整机 RAM 快照恢复代替游戏原生读档。尚未核对存档文件名、完整格式与所有字段，
也没有将默认初始位置的这次读回外推为所有游戏状态已正确持久化。

## 同进程实验的证据与保留产物

证据目录：`tmp/np560-native-settings-persist-20260906-v1/native-npe-off/`。

- `12-open-start`、`16-list-settled`、`18-load-*`：真实菜单和标题。
- `20-journey-settled`、`21-start-game`、`22-down`、`23-right`：场景、动作、位置记录。
- `24-before-exit`、`25-exit-game`：Start 退出无保存、完整桌面。
- `32-f4-game-menu`、`36-game-system`、`38-open-save`：原厂存档操作入口。
- `39-before-save-slot1`、`40-save-slot1`：保存前后 NAND 状态。
- `41-after-save-down`、`42-after-save-right`：保存后的不同位置。
- `48-open-load`、`49-load-slot1`：有效槽位、原生读回和恢复的位置。

每个操作都保留实际输入计数、原始 LCD、状态及 PNG；文件名仅作标签，以上页面已实际查看。
reader 进程 PID 54105 已关闭，退出码 0；没有保存它的 live NAND。
磁盘上保留的 `6abc62e9…` 镜像只含先前的音效设置，哈希未改变，不含本次游戏存档。
没有覆盖用户实例或原始 NAND。

## 追加：非默认进度落盘、结束进程与原生冷读回通过

仍使用同一 `4b70b03e…` 核心、PRG、ROM；本次没有改游戏状态、补 ROM 桩或更换实现。
独立 writer 从无游戏存档的 `6abc62e9…` 设置镜像冷启动，通过原厂标题的“新的征程”进入，
普通下、右键将角色从 `(7,1)` 移到 `(8,2)`，随后 F4 → 系统 → 存储进度 → 第一槽。
保存前实际槽位为“一 0”，保存完成后 NAND PROGRAMS 增加 512，原厂返回场景。

writer 启动时为 `--nand-save-on-exit` 指定了事先不存在的独立输出，正常关闭后：

- writer QEMU PID 56493 已退出，退出码 0；它的 RAM、CPU 和外设没有交给 reader。
- 保存文件：`E:/qemu-dmcu-build/np560-native-game-persist-20260906-v1.nand`，553,648,192 字节。
- SHA-256：`ce1ff5d3cc70d40394035f85c98d956ef40c4da8e67aaad683281ece09a38d5b`。
- reader QEMU PID 57155 是全新进程，运行身份中的 NAND 路径、大小、SHA-256 与保存文件一致。
  QEMU、PRG 和 ROM 三个输入的哈希与 writer 一致。

reader 冷启动时游戏位置字段为 `(0,0)`，没有继承 writer 的 `(8,2)`。
从原厂 NPE 列表进入标题后，**选“再续前缘”，未先执行“新的征程”**；
画面出现“一 1 / 二 0 / 三 0”，确认第一槽后恢复实际游戏场景。

| 已观察字段 | writer 保存时 | reader 原生读档后 |
| --- | --- | --- |
| map | 1 | 1 |
| x / y | 8 / 2 | 8 / 2 |
| offset x / y | 1 / 11 | 1 / 11 |
| direction | 1 | 1 |
| scroll | 0 | 0 |

已实际查看 writer 空槽、保存后场景，以及 reader“再续前缘”的有效槽和恢复场景。
两条路线的保存结果、原生 LCD、配置/位置观察均保留，所观察使用链无 ROM_MISSING、
UNSUPPORTED、INVALID_CONTROL，NAND ERROR=0。
这证明第一槽这组非默认进度从游戏写入到磁盘，再由新进程原生读回；不是只证明内存缓存能回读。

证据目录：`tmp/np560-native-game-persist-20260906-v1/`：

- `writer/report.json`、`writer/16-before-save*`、`writer/18-saved-scene*`。
- `writer-process/20260905T195017.214170Z-56487-405adf55/status.json`：writer 终止状态。
- `reader/report.json`、`reader/08-open-continue*`、`reader/10-restored-scene*`。
- `reader-process/20260905T195504.716696Z-57148-4294652d/status.json`：reader 终止状态。

reader 未启用落盘，结束后退出码 0；两实例都已关闭。结束后重新计算游戏保存文件和设置输入文件的哈希，
两者均未改变。本次只增加一个必要的 E 盘游戏进度镜像，没有覆盖用户实例、原始 NAND 或设置基线。

定向复现工具 `scripts/probe_np560_native_game_save.py` 复用既有矩阵和只读状态接口，
不另建导航平台。先对全新隔离 writer 使用 `--phase writer`；确认保存、关闭、核对输出后，
再对独立 reader 使用 `--phase reader --writer-report <writer/report.json>` 和
`--expected-nand-sha256 <已核对的保存文件哈希>`。两阶段都需要 `--allow-physical-input`。
工具不管理进程和 NAND 落盘；调用者仍须证明旧进程已退出、文件身份正确、新进程确实使用该文件。
当前等待条件包含 VMA03 游戏模式和 idle PC，仅是本构建的诊断边界，不定义硬件行为。

## 尚未完成与后续主线

本次没有证明完整物品/任务/战斗状态、其它槽位、覆盖/取消/错误路径、其它 NPE 游戏或异常断电恢复。
更不能因为无声路径完成一个存档往返就关闭 M2。
下一步回到阻止声音开启的 resident 流处理/解码服务和实际玩法中的剩余缺口；
对存档继续补有差异的真实状态与其它槽位，不重复刷同一位置的检查次数作为进度。

## 追加：第二槽后院与奖励冷读回；同时发现并修复 X RAM 取指缺口

证据目录：`tmp/np560-native-map2-save-20260906-v1/`。没有改动 guest 地图、坐标、金钱、
存档选择或 PRG；输入仍为真实矩阵。writer 从同一个无游戏存档、音效关闭的设置镜像启动。

### 保存的真实状态

原厂“新的征程”后 F4 菜单显示金钱 100。经过首地图出口、后院老人和兔子对话，
原厂显示“得到25块钱”，再次打开菜单显示 125。由“系统 → 存储进度”选中空的“二 0”并确认：

- 保存位置：地图 2，x/y 为 5/4，offset 为 0/1，方向为 2，scroll 为 0；世界坐标为 5/5。
- 游戏返回场景，NAND PROGRAMS `48→560`、ERASES `11217→11225`、COPIES `0→502`，ERROR=0。
- writer QEMU PID 74666、Web PID 74664 正常退出 0，仅将独立输出保存为
  `E:/qemu-dmcu-build/np560-native-map2-save-20260906-v1.nand`，553,648,192 字节。
- 保存文件 SHA-256：`ebcdddd37636abd1bf7b5c460fc918cbd4df0cbc16039d11e4e2601aca306aa5`。

对应画面及状态：`writer/05-baseline-menu`、`12-rabbit-reward`、`13-reward-menu`、
`15-save-slots`、`16-save-slot2`。退出状态在 `writer-process/20260905T223942.713085Z-74664-3d7a07e5/`。
中途错误地用 Escape 关闭 F4 菜单的路线保留为失败记录；原厂关闭键是再次按 F4，见
[输入语义](np560_npe_input_semantics.md)。

### 新进程恢复与版本边界

第一次 reader 在标题初始化时触发 `00:688E`。现场证明实际 RAM 中存在原厂 `00:1202`
临时中断处理程序，但旧 QEMU 取指映射只到 `102D`，读到了无关 ROM。
完整原因及通用 32 KiB X RAM 修复见 [内部 X RAM 取指](np560_internal_x_execution.md)。
不能因此给 `688E` 填 ROM 桩，也不能将第二槽冷读回提前记为成功。

修复后 reader QEMU PID 75390 为全新进程，位置/地图初始全零，使用保存 NAND 的身份与哈希已核对。
由实际菜单进入游戏标题，选择“再续前缘”（未先执行新游戏），画面显示“一 0 / 二 1 / 三 0”。
选第二槽确认后，原厂加载后院场景；F4 菜单显示金钱 125。

| 已观察状态 | writer 保存时 | 新 reader 原生读档后 |
| --- | --- | --- |
| 地图（修正后的 52:7A58） | 2 | 2 |
| x / y | 5 / 4 | 5 / 4 |
| offset x / y | 0 / 1 | 0 / 1 |
| direction / scroll | 2 / 0 | 2 / 0 |
| 实际菜单金钱 | 125 | 125 |

`fixed-reader/04-continue-slots`、`05-load-slot2`、`06-restored-money` 保留真实 LCD 与只读状态；
`05-load-slot2/native-load-observation.json` 明确记录 `same_qemu=false`：

- writer 核心：`ecff5a4baf22683236a8de3beef04180d5feacd0c171a773c6fabc7347516ed1`。
- reader 核心：`fd83eb62b7390533d2c6b3b9edea827407c9c76e17a5f4d5f7791a34886d69d1`。
- PRG 和 ROM 哈希分别仍为 `d555609e…`、`a243f8ba…`，没有换实现来伪造游戏状态。

这是旧核心写出原生进度、修复后的核心成功读取该 NAND 的证据，不冒充同一最终发布版本的
完整存读档验收。也没有证明任务标志、物品/装备、战斗、第三槽或所有错误/取消路径。
读取过程无已知 CPU 故障、NAND ERROR=0；reader 未启用落盘，正常关闭后保存文件哈希保持不变。
`reader-process`、`vector-watch-process` 的旧隔离实例也均已关闭，没有遗留用户之外的本轮实例。

## 追加：第三槽保存战斗奖励、生命与物品消耗

2026-09-06，当前同一核心 `fd83eb62…` 完成《英雄传奇》树林单眼蝠战斗、领取奖励、
使用草药，再由第三槽保存及新进程原生读回。恢复的状态不再只有坐标和金钱：
地图 4 / 世界 8,4 / 方向 3、金钱 129、生命 92/130、真气 59/60、等级 1 / 经验 3/10，
以及草药用完、灵芝 1，均在新 reader 的原厂界面或位置状态中核对。

完整操作、版本、独立 NAND 哈希、实际界面及进程退出证据见
[战斗与第三槽冷读回](np560_npe_battle_observation.md)。
该次 NAND 使用现有 QOM 导出，不是 Web 自动保存，也不是整机 RAM 快照；
未完成的覆盖/取消/异常路径、全部存档字段和有声游玩仍保持未完成。
