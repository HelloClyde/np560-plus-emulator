# LCD 输出明暗极性

更新：2026-09-07。

## 问题与修正

用户指出实际 Web LCD 是深底浅字。缺陷在 QEMU 将控制器像素码转换成
面板明暗值的出口，不是顶栏资源损坏，也不是新发现的 resident ROM 缺失。

现统一可见帧为 `gray5-darkness`：0 表示浅色/未驱动玻璃，31 表示深色。
保留原厂 A6/A7 命令、原始 GRAM 和总线读回；不改 CPU、ROM、NAND 内容或 Web 绘图代码。
诊断 `lcd-state` 增加 `ENCODING=gray5-darkness`，用于区分新旧记录。

## 依据与边界

- V3.80 PRG 文件偏移 `0x1169B0/0x1169B4` 装入并发送 A7，resident 执行地址
  为 `14:69B0/69B4`。此前写作 `31:69B0/69B4` 指文件首字节映射到 `20:0000`
  的源视图，不是文件偏移，也不是运行中的 CS:PC。A7 是原厂代码主动设置，不能直接删除或忽略。
- 原厂刷新例程 `14:6B94..6BBC` 将 packed gray4 的 nibble `n` 输出成
  `n << 4`。3B3P 模式使用 D7..D3，因此 GRAM 得到 `2*n`。
- 原厂通常用 nibble F 绘制文字、0 作背景；原资源和用户提供的真机照片支持
  NP560+ 正显玻璃应呈浅底深字。旧出口在 A7 下把文字码 30 输出成 1，
  Web 又把 1 当成很浅，导致整幅负像。
- ST7529 手册第 38 页规定反显作用于输出、不改变 RAM；未驱动的部分显示区域
  不随反显翻转。第 29、50 页说明 PWM/灰阶控制，但**没有直接给出 NP560+
  具体玻璃的光学极性或灰阶曲线**。本次极性取向依据原厂像素约定与正显实物资料，
  不冒充真机灰阶或逐周期测量。

手册：`tmp/pdfs/ST7529.pdf`，SHA256
`8565fc8d1f917f89667d1ac3439699888f669ec0ac774438d852848371d02031`。
既有字体/刷新依据见 [时钟光栅管线](np560_clock_raster_pipeline.md) 等逆向记录。

## 实现与记录兼容性

`qemu-dmcu/hw/dmcu/np560.c` 在面板输出处转换：

```text
显示关闭、休眠或部分显示未驱动：darkness = 0
显示开启且 A7：darkness = RAM code
显示开启且 A6：darkness = 31 - RAM code
```

逻辑 GRAM 观察帧使用同一明暗编码，但仍保持其原有的、未经过玻璃接线/LI/CI
变换的坐标；它不是 guest RAMRD 的原始总线字节。

原来的中性灰截图工具把 31 当白，而 Web/绿色截图把 31 当深色，两个观察器相反。
已统一当前快照、native buffer、时钟监控等相关输出；绿色 Web 截图工具及网页代码
未改。旧调查脚本和旧 `.gray5` 记录不可一概按新编码解释。

顶栏比较仍从原始 UPD 解包得到素材，只把数值映射改为 `2*n`，不拟合位置、不改资源。
过去顶栏比较通过证明的是几何/像素布局一致，不单独证明旧版光学极性正确。

## 验证结果

核心：`E:/qemu-dmcu-build/qemu-system-dmcu`，SHA256
`c3003ecf197eb2ac9ca4ad55912df185243840e1350e0920442970c14bbd0c55`。

旧核心保留为 `qemu-system-dmcu-pre-polarity-20260907`，SHA256
`939c68c0be78e26d13d580c786f5249a04d7e5fa08fd096b766030ba420624fd`。
旧核心在同一 A7 用例中 RAM 读回正确，但可见帧 28,800 个像素全部明暗相反：
`tmp/np560-lcd-polarity-before-20260907-v1/factory-disinv-ink-background.json`。

新核心的 guest MMIO 验证均通过：

| 内容 | 用例 | 证据目录（均位于 tmp/） |
| --- | ---: | --- |
| A6/A7、关闭、休眠/恢复、部分区域，逐命令核对原始 RAM 读回 | 7 | np560-lcd-polarity-20260907-v1 |
| 同上，icount=5 | 7 | np560-lcd-polarity-icount-20260907-v1 |
| 扫描方向/增量 | 9 | np560-lcd-scan-20260907-v1 |
| 部分显示 | 12 | np560-lcd-polarity-partial-20260907-v1 |
| RAMRD/读改写 | 15 | np560-lcd-polarity-rmw-20260907-v1 |
| 像素格式 | 12 | np560-lcd-polarity-formats-20260907-v1 |

上述验证不用 NAND 或宿主 RAM 注入。扫描/部分显示/读改写既有用例只调整可见明暗
期望值，原始读回与地址断言不变。

原厂系统实测证据在 `tmp/np560-lcd-polarity-game-20260907-v1/`：

- 隔离实例 `20260906T160621.943348Z-327-61d4148d` 从固件冷启动，HLE 关闭。
- `desktop.png` 为浅底深字完整桌面；`desktop-check.json` 顶栏 0/5280 像素差异，
  该采样没有 ROM_MISSING、INVALID_CONTROL、UNSUPPORTED 或 NAND 错误。
- 通过实际矩阵键进入开始 → 娱乐 → 游戏世界 →《英雄传奇》标题，再打开原生存档槽；
  `slots/02-OpenSlots.png` 可见正常明暗的原厂山水背景与菜单。
- 浏览器检查未启用“反色”开关。之后实例闲置进入 `DISPLAY=off SLEEP=on`，
  空白浅色画面不能当作游戏渲染失败。本轮没有继续加载第三槽验证地图/人物页，
  不把此前版本的游戏进度计为本次新构建完整玩法验证。

相关 Python 单测通过：快照 2、顶栏比较 2、时钟监控 21、冷启动采样 4、Web 前端 24。
前端单测首次默认 Node 路径启动失败；改用已有 bundled Node 重跑通过，没有修改前端来绕过。

PRG、重建 ROM 与输入 NAND 运行前后 SHA256 未变：

- PRG：`d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`
- 重建 ROM：`a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef`
- 输入 NAND：`a29489516e16fe2cdfb3138b628c1683fe8912efca163624bf37c62d802bd5f9`

本轮隔离实例未启用 NAND journal/save-on-exit，不覆盖原生存档文件。
核对运行标识后，已通过各自 shutdown token 关闭本轮 40621 与此前自用的 44595
隔离实例；两条启动命令均正常退出。未替换或重启用户的 8807/8808/8809。

## 尚未完成

- 本轮反色修正时 EXT1 Gray1/Gray2 表尚未实现。随后已补数字寄存器与命令区隔离，
  见 [后续实现](np560_lcd_command_banks.md)；PWM/FRC 输出仍未接入。
- 精确对比度、FRC/PWM 与光学灰阶曲线、其它 LCD 控制组合仍待完善。
- 原厂声音、完整游戏功能、ROM 缺口和其它 M1–M6 工作没有因此完成。
