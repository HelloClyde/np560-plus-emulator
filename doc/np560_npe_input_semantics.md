# NPE 游戏前台输入语义

更新日期：2026-09-06

## 结论

《英雄传奇》前台的四方向短按、长按重复、方向/动作组合、独立返回键和退出键均已通过
真实 8×8 矩阵路径验证。Web 只设置 QEMU 的物理矩阵电平；候选事件、键表映射、modal
确认、游戏控制器和退出均由 guest 原厂代码完成。

## 长按重复

`scripts/monitor_np560_npe_input_semantics.py` 在同一次游戏运行中分别保持四个方向 5 秒：

| 方向 | 矩阵/事件 | 候选=映射=消费 | 首次重复 | 后续中位间隔 | 证据 |
|---|---:|---:|---:|---:|---|
| 下 | M37 / `0x83` | 15 | 0.640 s | 0.3125 s | `tmp/v859-npe-long-press-down-after-item/` |
| 右 | M29 / `0x81` | 15 | 0.672 s | 0.3045 s | `tmp/v860-npe-long-press-right/` |
| 上 | M61 / `0x82` | 11 | 0.562 s | 0.3205 s | `tmp/v861-npe-long-press-up/` |
| 左 | M45 / `0x80` | 16 | 0.641 s | 0.2970 s | `tmp/v862-npe-long-press-left/` |

四组计数全部平衡，应用状态保持 `0x0078`，画面均有真实变化，且无
`ROM_MISSING`、`UNSUPPORTED` 或 `INVALID_CONTROL`。

## 方向与动作组合

`scripts/probe_np560_npe_input_combinations.py` 验证两类物理序列：

1. 先按住一个方向，再叠加/移除 M53 动作键，最后完整释放矩阵。原厂扫描器在矩阵未
   全释放时不会重新武装，因此整个序列只有一个方向候选、一个映射、一个 modal 消费；
   中途叠加动作不会伪造第二个 make。
2. 从完全释放状态同时按方向和动作。guest 按降序矩阵扫描优先级只选择一个开关：
   `M61(上)+M53(动作) → M61/0x82`；`M45/M37/M29 + M53 → M53/0x86`。
   动作胜出时选择器调用/返回严格为 1/1；上方向胜出时上方向控制路径严格命中一次，
   动作选择器为 0 次。

最终四方向证据为：

- 下：`tmp/v870-npe-input-combo-down-final/`
- 右：`tmp/v871-npe-input-combo-right-final/`
- 上：`tmp/v868-npe-input-combo-up-priority/`
- 左：`tmp/v869-npe-input-combo-left-priority/`

QEMU 的矩阵硬件模型不会自行挑选按键；`np560_key_matrix_input()` 只按当前 drive 返回所有
闭合行列。上述优先级来自 guest 扫描/去抖代码，是需要由 Web 保留的原机语义。

## 返回与退出

- `M28/0x84` 的独立短按在 `tmp/v872-npe-back84-isolated/` 中得到
  `candidate/map/consumer=1/1/1`，由 modal 路径确认；应用状态保持 `0x0078`，前后帧
  SHA-256 都是 `edb3371293852b52b3bb9cf79dd47e19c0da5758699804710e555ddae5acd0c2`。
  exact 新旅程控制器没有 `0x84` 分支，所以该键在本游戏主场景是已消费但无操作，不能
  将其伪装成退出。
- 真正退出键为 `M55/0xB0`。`tmp/v873-npe-back-and-start-exit-regression/` 中一个严格
  单边沿得到候选/映射/消费 `1/1/1`，应用状态从 `0x0078` 变为 `0x00FF`，桌面 blit
  `64→70`，原生 root renderer `30→40`，`root_menu_complete=true`。本次现场只需一次
  Start 边沿；脚本仍保留在旧场景需要时发送第二边沿请求主菜单重绘的有界逻辑。

## 回归入口

- 长按/独立键：`scripts/monitor_np560_npe_input_semantics.py`
- 组合键：`scripts/probe_np560_npe_input_combinations.py`
- 持续游玩和退出：`scripts/monitor_np560_npe_play_session.py`
- 单元测试：`scripts/tests/test_probe_np560_npe_input_combinations.py`

以上只证明所列场景的输入语义，不能宣布全部游戏模式、菜单、对话和战斗的输入都已完成。

## 追加：F4 菜单的关闭不是 Escape

2026-09-06 在当前核心 `ecff5a4b…`、严格 codec 缺口 ROM 与原厂音效关闭设置下，
实际新游戏打开 F4 菜单后，Escape 没有关闭菜单，后续方向键仍在操作菜单。
再次按 F4 才恢复地图场景，模式由 6 回到 1；不是漏键，也不能修改前端 Escape 映射来补偿。

原始 PRG 的对应分派代码与此结果一致：

- runtime `2E:B604..B610` 比较事件 `0084`，调用 `2A:572E`。后者根据
  `52:7A54` 等子状态处理，不能将其等同于无条件返回场景。
- runtime `2E:B6FC..B704` 比较事件 `008E`，调用 `33:15A8`。
- `33:15A8..15D6` 调用原厂绘图服务，随后在 `33:15CE` 向 `52:7934` 写入 1，返回场景模式。
- 使用 `dump_np560_range.py` 时，PRG source 地址分别为 `4B:B604`、`4B:B6FC`、
  `47:572E`、`50:15A8`；不要把工具的 source 映射当作 runtime。

实际证据在 `tmp/np560-native-map2-save-20260906-v1/writer/`：
`05-baseline-menu` 为 F4 菜单，`06-to-backyard` 是没有关闭菜单的失败路线，
`07-close-f4` 确认恢复场景，`08-backyard` 随后才真正移动并切到后院。
本次未改矩阵、CPU 或 ROM 行为，只纠正了对原厂按键作用的理解与操作路线。
普通交谈仍使用空格推进，具体范围见 [地图切换与对话](np560_npe_map_transition.md)。

## 追加：物品和属性页的实际返回操作

2026-09-06，`fd83eb62…` 核心下由真实战斗取得灵芝后，在“物品 → 使用”确认草药、
再确认角色，生命 52→92、草药 1→0。此目标页的 Escape 未退出；F4 返回物品列表，
再次 F4 返回地图。属性状态页的 F4 也返回地图。
这是对应页面的实测，不外推 Escape 或 F4 在所有模式中的作用；没有调整键盘映射。
证据见 [战斗与道具操作](np560_npe_battle_observation.md) 中的 `play/21` 至 `25`
及 `reader/04` 至 `07`（目录实际名称带描述后缀）。
