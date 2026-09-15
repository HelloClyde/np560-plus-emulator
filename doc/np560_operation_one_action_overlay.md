# NP560+ operation 1 动作覆盖区与 Harvard 代码一致性

更新日期：2026-09-01

## 结论

真实 NPE 游戏进入 operation 1 后，控制器 `1A:141E` 直接调用运行期
`29:CE22`。该地址不是新的 CPU 指令，也不是要由宿主模拟的 ROM 服务；它是原厂
resident 安装器在启动时写入可执行 RAM 的普通 DMCU guest 函数。

v840 已恢复并动态验证这条生命周期：

- 动作函数：`29:CE22..D0B9 ← 46:CE22..D0B9`，大小 `0x298`；
- 相邻 UI 初始化器：`29:D0BA..D34F ← 46:D0BA..D34F`，大小 `0x296`；
- guest 安装器：`09:E000..F4C0`，逐字写入两段目标，最后正常 `RETS`；
- 动作函数首字：`2E05`，入口保存 `R1..R5`，尾部为 `UNLINK/RETS`；
- 原始调用点保持 `1A:141E → 29:CE22`，没有宿主返回值或 PC 跳转替代。

构建产物 `tmp/np560-system-v380-current-v840.bin` 的 SHA-256 为
`BFF491827D9CE7BC0CC0786FE196C63205DD1D77CC6411DAC2B43447ACBB8D26`。

## 首次故障与证据

最初的 v840 ROM 安装器已经执行，写观察器记录到完整的 664 次 16 位 guest 写入，
最终 `29:D0B8=C620`，没有后续覆盖。然而第一次游戏动作仍报告：

```text
1A:141E → 29:CE22
code word = 00A4
```

而目标 data RAM 的首字已经是 `2E05`。这证明问题不在动作函数反编译或安装器，而在
QEMU 的 Harvard 映射：数据总线写到了新 RAM，代码总线仍从 flat PRG/source alias
取旧字节。返回地址损坏后进入数据区只是这个不一致的后果，不能通过增加 CPU 指令或
伪造 ROM 服务修复。

## QEMU 映射约束

DMCU target 使用 2 KiB 页：

```text
TARGET_PAGE_BITS = 11
TARGET_PHYS_ADDR_SPACE_BITS = 25
```

直接把 `29:CE22..D34F` 作为窄 code alias 会在 `29:C800` 页生成新的 subpage，令
QEMU `PhysPageMap` 从 2048 个 section 增至 2049 个并触发上限。把目标页改为 4 KiB
虽然能启动，但 A/B 冷启动出现应用解析进度回归，因此没有保留。

最终实现保持 2 KiB 页，并按页几何拆分：

```text
29:C800..CFFF  独立 0x800 RAMBlock
  C800..CE21  复位时由 flat PRG 原字节初始化
  CE22..CFFF  guest data store 后同步写入 code AddressSpace

29:CE22..D34F  连续 data publisher RAM（0x52E）
29:D000..D34F  code alias → publisher RAM + 0x1DE
```

这样 `29:C800` 整页不需要 subpage，`29:D000` 页的尾段只产生已有的局部 alias；
guest 仍通过真实数据写路径发布代码。同步逻辑仅镜像实际落在
`29:CE22..CFFF` 的 8/16 位 store，不修改寄存器、PC、返回值或游戏状态。
`09:F4C0` 的 installer `RETS` 边界执行一次 TB/TLB 同步，避免 TCG 继续使用安装前
翻译块。

## 动态验证

同一冷启动 Web/QEMU 实例（端口 8801）取得：

```text
code[29:CE22..] = 05 2E F1 58 F2 58 F3 58 ...
NPE_OPERATION_ONE_ACTION_WRITES=664
NPE_GAME_LINKED_LOADER=1 PC:29:CE22 W:2E05
NPE_GAME_UI_REENTRY=0
NPE_LOW51_EXEC=0
ROM_MISSING=none
UNSUPPORTED=none
INVALID_CONTROL=none
```

随后只用物理矩阵边沿完成七步原厂菜单路线，进入 `英雄传奇.NPE` 地图；第一条游戏
动作和连续四方向事件均由 `1E:F8E4` modal consumer 确认。v840 30 秒闭环完成 18 次
四方向动作，6 个中间 LCD checkpoint 的 hash 均随地图变化，应用状态全程保持
`0x0078`。最后一个 `M55/0xB0` 使状态自然变为 `0x00FF`，root renderer 从 30 增至
40，并稳定返回完整主菜单。

证据：

- `tmp/v840-coherent-main-menu.png`
- `tmp/v840-coherent-npe-route/route.json`
- `tmp/v840-coherent-npe-first-action.json`
- `tmp/v840-coherent-npe-30s/manifest.json`
- `tmp/v840-coherent-after-30s-exit.png`

## 回归

- `scripts.test_np560_game_draw_trace_observer`：5/5；
- operation UI builder 定向测试：1/1；
- QEMU 构建成功；
- 使用新构建 QEMU 的 NOR/code split、internal byte lane、stack byte alias、
  stack/MMIO alias 四项命令行集成测试全部通过。

v840 随后已完成新的 600.0 秒长跑：120 个四方向物理边沿、10 个检查点、application
全程 `0x0078`，最后一个 Start 边沿使状态 `0078→00FF`、root render `60→70` 并稳定
回到主菜单；所有检查点的三类故障诊断均为 none。完整证据为
`tmp/v840-coherent-npe-ten-minute/manifest.json`。

旧监控器只在第一次正确 map/ack 后判断每步成功；对 120 边沿长跑的事后审计确实发现
121 次 candidate、125 次 map 和 125 次 consumer ack。后续工具把 candidate/map、
foreground/modal ack、matrix reads/rearm、application state 和 fault 位合并成一次原子
只读 QOM 快照，并增加精确 `--action-count`、settle 后计数和
`--strict-single-edge`。

直接等候 candidate 再释放时，第 362 个边沿曾因宿主轮询延迟形成 1.48 秒物理保持，严格
抓到 `2/2/2`；50 ms 固定脉冲又无法越过原厂消抖。最终 200 ms 固定物理矩阵脉冲在
`tmp/v840-pulse-200ms-1000-v2/manifest.json` 完成：

- 557.204 秒、1,000 个游戏方向边沿，Down/Right/Up/Left 各 250；
- candidate/map/consumer ack 严格 `1000/1000/1000`；
- 10 个检查点产生 10 个不同 LCD hash；
- 一个 `M55/B0` 使 application `0078→00FF`；保留 2 秒原厂退出清理后，root renderer
  自行 `30→40`，不需要第二个 Start；
- 最终主菜单 hash 为
  `09b30a4ccdc1abd398b598b271d35221613847b86ad6c4c898132f2e79809b01`，三类故障均
  absent。

因此 v840 的短按 one-edge/one-event 与 1,000 次方向压力已经关闭。仍未关闭的是长按
重复频率、动作/方向组合、独立返回键、音频和存档；这些不能由短按压力结果替代。
