# NP560+ resident `0D:78D2` NPE 区域搬移函数恢复记录

2026-09-06 更正：本文证明了原厂函数恢复和缺页消除，但不能据此认定整幅滚屏已正确。
后续实际阿诺场景确认 CPU 将内层 REP 覆盖外层 REPB，导致仅搬移首行；
现已修复独立循环状态，并对照完整缓冲和实际 LCD。见 [嵌套循环与滚屏修复](np560_nested_repeat_scroll.md)。

## 结论

NPE 游戏地图移动时出现永久横条和旧角色残影的第一个可证明原因，是当前重建 resident
ROM 缺少 `0D:78D2`。该地址不是需要新增的 DMCU 指令，也不是应由 QEMU LCD 或 Web
前端实现的 ROM 服务。升级包 `NP560.PRG` 在 `+0x1D` 源段 `2A:78D2` 保存了完整原厂
guest 函数，v833 将它逐字恢复到执行地址 `0D:78D2`。

## 动态调用证据

- v832 从原厂主菜单沿七个真实矩阵边沿进入游戏：
  `M55/B0 → M53/86 → M37/83 → M53/86 ×4`。
- 初始地图可完整绘制；连续向下移动时，每个物理按键均通过原厂扫描、映射和 modal
  consumer acknowledgement。
- 第四次移动的 draw transaction 从 `29:BDDC` 进入 ROM03 图形路径。原厂 veneer
  `03:4268` 是 `LCALL 0D:78D2`，v832 的该 resident 区没有函数体。
- QEMU 只读诊断当时记录 `ROM_MISSING=0D:78D2`，前一控制边为
  `03:4268/ad0d 78d2`；中断返回又反复落回同一缺页，画面永久停在半完成横条。
- v833 在完全相同 NAND、固件、QEMU 和按键路径下越过该点，五次向下移动后仍为
  `ROM_MISSING=none / UNSUPPORTED=none / INVALID_CONTROL=none`，并完成地图纵向滚屏。

## 源地址映射与边界

已反复验证的升级包 load-image 关系是：

```text
linked resident segment = PRG source segment - 0x1D
2A:78D2 -> 0D:78D2
```

`NP560.PRG` 以 `20:0000` 映射到文件偏移 0，因此源偏移为：

```text
(0x2A - 0x20) * 0x10000 + 0x78D2 = 0x0A78D2
```

反汇编闭包：

- 文件范围：`0x0A78D2..0x0A7B01`
- resident 范围：`0D:78D2..0D:7B01`
- 大小：`0x0230` 字节
- 入口：`LINK #0x0A`
- 可达指令：210
- direct call：0
- unknown/reserved frontier：0
- overlapping decode target：0
- 退出：`2A:7AFE CRIT #0`、`2A:7B00 RETS`

函数只有同段相对/绝对内部控制流，因此段号整体减 `0x1D` 后不需要修补任何 call 或
jump 字。反汇编证据：

- `doc/np560_source_2a78d2_resident_frame_sync_reachable.asm`
- `doc/np560_source_2a78d2_resident_frame_sync_report.md`

## v833 构建审计

构建器常量：

```text
RESIDENT_NPE_REGION_MOVE_ADDRESS = 0x0D78D2
RESIDENT_NPE_REGION_MOVE_SOURCE  = 0x2A78D2
RESIDENT_NPE_REGION_MOVE_SIZE    = 0x0230
```

产物：

```text
tmp/np560-system-v380-current-v833.bin
SHA-256 EDBB2281EAB00F7F79F761446089F0946F30BBEDF08B2D80C7BE987C1C24144A
```

v832/v833 二进制差异审计满足：

- 两个 ROM 大小相同，均为 2,095,672 字节；
- 所有差异字节都位于 `0D:78D2..0D:7B01`；
- v833 的目标 `0x230` 字节与 NP560.PRG 源范围逐字节相等；
- 未修改 LCD、键盘、NAND、Web 或 guest RAM。

定向测试：

```powershell
python -m unittest `
  scripts.test_build_np560_reconstructed_rom.ReconstructedRomTests.test_resident_npe_region_move_is_exact_guest_code `
  scripts.test_build_np560_reconstructed_rom.ReconstructedRomTests.test_resident_packed_nibble_blit_family_is_exact_guest_code `
  scripts.test_np560_game_draw_trace_observer `
  scripts.test_monitor_np560_game_draw
```

结果：5/5 通过。

## 画面证据

- 初始地图：`tmp/v833-game-map.png`；raw `gray5` SHA-256
  `5C2FBBB1453AE34DA4C2D7713997FD2345016829E1E0042E32E968C81BB5073D`。
- v832 第四次向下后的永久未完成帧：
  `tmp/v832-drawtrace-down4/01-down4.gray5`；SHA-256
  `9303AE2C578018DE6322EA607FCA07CCA4C911B0B0FEAD5C3B9A321C6D796F42`。
- v833 第四次按键后约 0.8 秒仍可捕获正常的中间搬移帧：
  `tmp/v833-down-four/04-down-4.gray5`；SHA-256
  `CF15F086B2092CE11026ACED66E06BE84CC6BC6308DABFB5EDE54EE5E63B44E8`。
- 再稳定约 3 秒后，guest 已清除旧位置并填入底部地图行：
  `tmp/v833-after-down4.png`；raw `gray5` SHA-256
  `8FEDE7BC134D16951BC3F041D874FA08BE3BD473005A304BCD263BFDFF0DE456`。

中间帧短暂存在而最终帧自然完成，是原厂 guest 区域搬移继续执行的表现；Web 没有清除、
合成或修补任何像素。

## 尚未完成

该函数恢复只关闭了纵向滚屏的首个 resident 缺口，不等于游戏已经完成验收。仍需在同一
真实 NPE 前台验证四方向、长按、动作组合、地图边界、正常退出、10 分钟持续游玩，以及
可能随后暴露的 resident ROM 或硬件差异。
