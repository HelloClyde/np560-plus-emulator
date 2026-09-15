# Resident `1B:2C92` record-range worker

更新日期：2026-09-01

## 动态发现

v798 在真实矩阵路线
`开始 → 娱乐 → 游戏世界` 的一种合法时序分支中，从原厂 caller
`2F:377E` 进入尚未重建的 resident 地址 `1B:2C92`：

```text
ROM_MISSING=1b:2c92 FETCHES=1 PREV=2f:377e/bd1b
```

同一次运行已经正确显示娱乐子菜单并选中“游戏世界”。因此该地址是当前原厂控制流实际
使用的依赖，不是返回地址损坏、按键映射错误或应当新增的 CPU 指令。

## 源地址映射

`NP560.PRG` 文件字节 0 对应 DMCU code 地址 `20:0000`，不是 `00:0000`。按这个
映射，resident `1B:2C92` 的唯一同 PC 原厂 source 是：

```text
target: 1B:2C92
source: 3B:2C92
file offset: 0x1B2C92
size: 0x02AA bytes
```

caller `2F:377E` 在升级程序中也是同 PC 的 `2F:377E`，其调用字为
`BD1B 2C92`，与动态记录完全一致。

## 函数边界与审计

- 入口：`3B:2C92`
- 结尾：`3B:2F38 UNLINK`、`3B:2F3A RETS`
- 下一函数：`3B:2F3C LINK #7`
- 精确范围：`0x02AA` 字节
- 可达指令：240 条
- 直接调用：0
- unknown/reserved：0
- 重叠指令：0

该范围紧接在既有 resident operation body
`1B:23B8 + 0x08DA = 1B:2C92` 之后，没有间隙或重叠。builder 将原厂字节逐字安装到
`1B:2C92..2F3B`；没有 HLE、宿主返回值、对象修补或伪造 UI。

## 重建结果

该 worker 首次进入 v799：

```text
SHA-256 D733A9431634ACE77796381CB1E93DE5B5ABB708F1297431F657A609D5E9038F
```

v799 冷启动后，五键路线可再次进入 `英雄传奇.NPE` 的原始标题页；第六个确认选择
“新的征程”后不再命中 `1B:2C92` 或 v797 的 `1A:1312` 缺口，也没有
`UNSUPPORTED`/`INVALID_CONTROL`。应用进入 `STATE=0078`、NPE phase 1。

当前后续边界不是新的 strict-ROM stop，而是载入后的 NPE code 在 `00:57xx` 一带持续
执行 resident API 调用、loader 尚未返回且 LCD 没有产生新游戏帧。下一步必须从独立
DMCU code bus 只读转储实际载入代码并分析循环终止条件，不能把 data/physical bus 的
全零快照误当成 NPE 指令。

## 自动回归

`scripts/tests/test_build_np560_reconstructed_rom.py` 的
`test_resident_record_range_worker_is_exact_and_bounded` 固定检查：

- 入口与结尾原厂字；
- `0x02AA` 边界和下一函数 `0x2E07`；
- 与前一 resident body 相邻；
- caller `2F:377E = BD1B 2C92`；
- 安装镜像和 manifest 均使用同一 exact source。
