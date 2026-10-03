# NPE 世界坐标、对象表与动作选择器

更新日期：2026-09-02

2026-09-06 更正：历史接口 `map_index` 误读 `52:7A66`；真实地图号是 `52:7A58`。
本轮已实际进入后院并对话，见 [出口与地图字段](np560_npe_map_transition.md)。下文旧坐标、
对象选择及动作记录保留，但“地图 1”不能再仅由旧接口数值支持。

## 结论

《英雄传奇》地图探索必须把屏幕坐标、视口偏移、地图号和朝向共同作为状态：

```text
(screen_x, screen_y, map_index, offset_x, offset_y, direction)
world_x = screen_x + offset_x
world_y = screen_y + offset_y
```

其中视口偏移是逻辑 `52:7A2E`（X）和 `52:7A2C`（Y）。旧诊断字段
`current_scroll` 实际观察的是 `52:7A84` 的碰撞/对象槽索引，不能作为滚屏坐标。

动作选择器是原厂代码 `29:CE22 ← 46:CE22`。它读取 `52:69D4` 的朝向，只检查
角色正前方一格，并扫描 `52:759E` 起始的 8 个、每项 16 字节的对象记录；返回对象
索引 `0..7`，没有目标时返回 `FFFF`。四个方向为：0 下、1 右、2 上、3 左。

## 动态证据

- 冷启动的真实路线共 7 个矩阵边沿：
  `M55/B0 → M53/86 → M37/83 → M53/86 ×4`。最后一个 `M53/86` 才是
  `StartGame`，不能把 6 边路线当成已经进入游戏。
- v3 世界状态探索的第一阶段覆盖 256 个状态，世界范围 X=4..15、Y=1..12，
  无 `ROM_MISSING`、`UNSUPPORTED` 或 `INVALID_CONTROL`；此前只按屏幕坐标得出的
  “地图只有几行”结论无效。
- QEMU 只读内存快照显示对象 0 的逻辑记录已启用，坐标字节为 X=1、Y=6。DMCU
  外部字节通道需要以 `address ^ 1` 解读，因此物理相邻字节看起来是 `06 01`。
- `scripts/explore_np560_npe_map.py` 现在支持冷启动 `--route-to-game`、v3 清单恢复以及
  `--target-world-x/--target-world-y`。目标导向只调整遍历顺序，不写 guest RAM、
  不修改角色坐标，也不跳过原厂碰撞函数；每个状态仍穷举四个真实矩阵方向。
- 权威结果保存在 `tmp/v848-target-guided-explore-512/manifest.json`：状态 299 为
  屏幕 `(2,4)`、偏移 `(0,2)`、地图 1、朝左，等价世界坐标 `(2,6)`；此时动作选择器
  第一次返回对象索引 `0`。这正是站在 `(1,6)` 对象右侧并朝左的预期结果。
- 同一次动作由 `M53/0x86` 的 map/modal acknowledgement 确认。随后加入的只读 observer
  已在干净冷启动 `tmp/v851-action-guard-observer-first/` 严格闭合一次性事件：第一次动作
  得到 `selector=0, guard_value=0, guard_passes=1, commits=1, commit_flag=1`；原地第二次
  动作得到 `selector=0, guard_value=1, guard_rejects=1`，而 `commits` 保持 1。整个过程
  `faulted=false`。这与控制器 `1A:148C` 的完成标志判断、`1A:14CE..14F0` 写 1 和
  `1A:14FC → 25:3082` 提交路径逐项吻合，不再只是推断。
- `scripts/probe_np560_npe_object_action.py` 现将首次动作的即时状态、原厂定时界面稳定后的
  状态和第二次动作后的状态分开抓取。干净冷启动的权威回归为
  `tmp/v858-object-action-delayed-regression/`：动作前与首次动作即时帧均为
  `436d279ef8bc7e8cb354272cdbf2075ad6c2070c8d8aa238d89cbefaae6df544`；等待 5.5 秒后的
  稳定帧变为 `5e4660223773edd2e2b174f1f026a4386d22d83ec651c297c72ac64c283b2686`；第二次动作后
  仍为后一 hash。旧 v853 将延迟界面变化归到“第一次动作后稳定帧”，事件归属不够严格，
  现由四阶段回归取代。
- 同一 v858 运行中，首次动作严格得到
  `selector=0, guard=0, pass=1, commit=1, flag=1`；第二次动作严格得到
  `selector=0, guard=1, reject=1, commit delta=0`。第二次动作前后的 segment 52/53
  快照均为 0 字节变化，排除了原厂 5 秒回调污染“二次拒绝”比较。
- 排除 `52:0000` 起的绘图缓存后，首次动作即时只改变五个高地址字节：输入状态
  `52:70D4/70D5`、对象完成标志 `52:742C=1`、控制计数 `52:7A32` 和最后事件
  `52:7A77=86`。延迟阶段才写入 `52:739E` 起的文字区、`52:7428..742B` 和
  `52:7A72=1`；第二次动作没有再改任何字节。
- `52:739E` 的逻辑字节按 DMCU 外部 byte lane 还原并以 GBK 解码后包含物品名
  “布鞋+1”和说明“传说中何山小时候穿的鞋子。防御+1.”。这严格证明对象 0 是一次性
  物品描述/UI 事件，但尚不能把说明文字等同于已经找到角色防御字段或背包写入；当前没有
  直接状态落点证据。
- 静态控制器与动态时序一致：提交路径在 `37:15C6` 调用 `22:C370`，随后使用
  `52:739E`，并在 `37:1608` 传入 `0x1388`（5000 ms）。exact source
  `3F:C370` 是带 `LINK #3` 的完整 UI/layout 状态初始化函数，写 `52:7A72` 并处理
  `52:739E`；它不是已证明的角色属性修改器。因此旧的“下一步直接找防御字段”假设降级，
  后续只有在真实存档/装备路径出现新的写入证据时再追踪。

## 静态证据入口

- 动作选择器：`tmp/dis-action-46ce22/action-46ce22-dispatch_reachable.asm`
- 游戏控制器：`doc/disassembly/np560_source_371312_new_journey_controller_reachable.asm`
- 移动控制器：`doc/disassembly/np560_source_3b1452_input_controller_reachable.asm`
- 世界坐标/碰撞 helper：`doc/disassembly/np560_source_3a0000_input_state_update_reachable.asm`
- `29:CE22` Harvard overlay：`doc/games/np560_operation_one_action_overlay.md`

## 下一步

1. 扩展返回键、长按/组合键的用户可玩性验收，并覆盖物品 UI 显示期间的输入。
2. 在真实存档/装备路径上另行追踪物品持久化和角色属性；没有动态写入证据前不命名字段。
3. 保留四阶段 observer 回归，防止 guard/commit 与 5000 ms 延迟 UI 路径在后续修改中退化。
