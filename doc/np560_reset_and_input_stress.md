# NP560+ 整机复位与 NPE 输入压力证据

2026-09-06 修正：普通 Reset 现在保留 live NAND，不再恢复启动 checkpoint。
下文压力测试是旧构建的局部证据，不代表当前严格 ROM 已能完整游玩 NPE；
当前任务优先级和完成定义以 [整机计划](plan.md) 为准。

## 整机复位

QEMU 的普通 `system_reset` 默认保留 RAM。NP560+ 启动链会修改 16 MiB data RAM、
运行期 code overlay，以及 operation action 的两个专用可写页；只复位外设会让旧 PC/栈
在已经恢复或改变的 RAM 上继续运行。动态故障曾表现为
`31:7822/c620 → E8:0000`。原因是 standalone DMCU CPU 没有 qbus parent，
`qemu_devices_reset()` 不会遍历到它。

当前 `np560_machine_reset()` 执行以下有界操作：

1. 恢复 realize 后保存的完整 data RAM 快照；
2. 恢复 operation action UI RAM 和完整 2 KiB action code page；
3. 不重新载入 NAND；checkpoint 和 raw `nand-image` 均只在机器创建时作为介质输入；
4. 显式 `cpu_reset()`，随后 flush TB/TLB；
5. `qemu_devices_reset(reason)` 复位外设，包括 NAND 控制器，保留 NAND data/OOB。

旧实现把“恢复确定性实验基线”混进普通复位，因而丢弃原厂确认写入的设置和文件。
这是错误的介质生命周期策略，不能作为设备 Reset 的行为。NAND 输入镜像仍保持只读；
保存到宿主文件与重新打开设备是另一条持久化链，需要单独确认，不能由同进程 Reset 通过推断。

旧记录曾在保留多轮写入后观察到 `APPLICATION_STATE=007E` 而非 `00FF`。
若该启动缺陷再次出现，应定位原厂启动/FTL/应用恢复的实际故障，不得以回滚 NAND 隐藏它。
CPU 必须先于依赖共享 SFR 的外设复位，原因见 [DAC 与复位顺序](np560_dac_web_output.md)。

## 原子输入诊断

`key-pipeline-status` 是只读 QOM JSON 快照，一次返回：

- candidate count/value；
- map count/value；
- foreground 与 modal consumer acknowledgement；
- matrix reads 与 released/rearmed 状态；
- application state；
- ROM missing、unsupported 或 invalid-control 的聚合 fault 位。

它替代游戏循环中每个边沿下载完整 CPU 诊断的旧做法，不注入、确认或修改 guest 事件。
菜单/应用切换仍保留完整诊断同步，因为原厂过渡路径有独立时序要求。

## 物理短按窗口

三种方案的动态结果：

| 方案 | 结果 |
|---|---|
| 等候 candidate 后由宿主释放 | 第 362 边沿发生 1.48 秒意外保持，严格 `2/2/2` 重复 |
| 固定 50 ms 矩阵脉冲 | 第一条 Down 被原厂消抖漏掉 |
| 固定 200 ms 矩阵脉冲 | 100 次和 1,000 次严格回归均通过 |

200 ms 脉冲仍只设置/清除真实 8×8 matrix level；事件必须继续经过原厂扫描、消抖、
candidate、map 和游戏 modal consumer，不直接写 guest 事件槽。

## 1,000 次最终证据

权威 artifact：`tmp/v840-pulse-200ms-1000-v2/manifest.json`。

- route：默认主菜单六步物理路径进入真实 `英雄传奇.NPE`；
- play：557.204 秒，Down/Right/Up/Left 各 250 次；
- strict counts：candidate/map/consumer ack = `1000/1000/1000`；
- frames：10 个检查点、10 个不同 SHA-256；
- exit：一个 Start，application `0078→00FF`；
- cleanup：静置 2 秒后 root render `30→40`，原厂主菜单自动完成；
- final frame SHA-256：
  `09b30a4ccdc1abd398b598b271d35221613847b86ad6c4c898132f2e79809b01`；
- `ROM_MISSING`、`UNSUPPORTED`、`INVALID_CONTROL`：均 absent。

立即在 `STATE=00FF` 后注入第二个 Start 曾触发 `29:05AE/c620→00:0003`；这不是第
1,000 个方向边沿失败，而是测试驱动打断原厂退出清理。加入 2 秒稳定门槛后，菜单本身已
自动重绘，第二个 Start 不再需要。

## 尚未覆盖

- 真实长按的重复起始延迟与重复频率；
- 动作键、返回键及方向/动作组合；
- NPE 音频；
- 游戏实际支持的存档和恢复路径；
- 1 小时 idle、1 万次按键和多应用切换压力。
