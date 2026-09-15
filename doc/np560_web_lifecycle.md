# NP560 Web/QEMU 生命周期诊断（2026-09-05）

## 问题边界

用户报告的 8807 历史退出原因尚未确定。重启恢复不是根因修复；本次修复依据是代码中
可复现的资源清理漏洞，不据此推断当时发生了哪一种故障。运行中的旧 8807 实例没有
重启，新诊断只对加载新 Python 代码的实例生效。

## 记录和只读检查

启动器仍为 `scripts/run-np560-web.ps1`，当前路线见 [计划](plan.md) 第 2 节；
整包烧录测试镜像与运行身份见 [烧录记录](np560_usb_burn_transport.md)。
每次运行生成唯一目录 `tmp/web-runs/<UTC时间-PID-随机标识>/`；可用 `-RunLogDir`
指定其它持久目录。对应 Python 参数为 `--run-log-dir`。

- `status.json`：原子替换的最新状态，含 run ID、Web/QEMU PID、端口、WSL boot ID、
  启动配置、QEMU/PRG/ROM/NAND/前端哈希、已观察的退出码。
- `events.jsonl`：启动、产物识别、QEMU 产生/退出、Web 就绪、关闭请求与异常记录。
  稀疏事件逐次 flush/fsync；不会将每个 LCD 轮询写入这个文件。
- `qemu.log`：该次 QEMU stdout/stderr，默认不开 `-d unimp`。PID 复用不再覆盖旧日志。
  日志不包含 Web shutdown token。QMP socket 和临时帧仍在 `/tmp`，关闭时清理。

`GET /api/health` 不取 QMP 锁、不读取或改写 guest 状态：QEMU 进程存在返回 200，
已退出返回 503 和实际退出码。`guest_health=not_checked` 是刻意保留的边界：
进程存在不能证明 CPU 未 fault、按键可用或游戏画面正确，仍应结合 `/api/key-status`、
`/api/diagnostics` 和实际 LCD。暂停中的 QEMU 也会报告进程存活。

进程退出观察线程只等待自己启动的子进程，不自动重启。QEMU 意外结束时 Web 保持
可访问以便诊断；随后关闭 Web 会返回非零桥接退出码，即使 QEMU 自身退出码为 0。
显式的 SIGINT/SIGTERM/SIGHUP 和本实例带 token 的关闭请求会留记录。
SIGKILL、WSL/系统终止或断电无法保证留下最后一条事件；残留的 `serving` 状态不是
进程仍存活的证据，需核对真实进程、boot ID 与端口。磁盘写满时日志错误在内存状态
和终端报告，不阻止子进程清理。

## 已修复的清理路径

1. 先绑定 Web 端口再启动 QEMU，端口冲突不会额外启动 guest。
2. QMP 建连/握手失败会关闭连接并终止、回收自己的 QEMU；初始化失败不保存 NAND。
3. guest 诊断初始化失败、Web 运行异常、正常关闭均进入清理路径。
4. 关闭 QMP 先 shutdown socket，唤醒阻塞的读取线程，再关闭文件对象；不等待其请求锁。
5. 强制终止后等待回收子进程；关闭可重复调用。退出时配置的 NAND 保存使用有界 QMP
   等待，失败仍清理子进程并报告错误。请求已发送后超时仅表示结果未知，不能宣称保存
   成功；没有重试写操作或自动恢复 guest。

## 验证

Windows 测试（仓库根目录）：

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
python -m unittest scripts.test_np560_web_lifecycle scripts.test_np560_web_frontend scripts.test_monitor_np560_start_menu scripts.test_monitor_np560_npe_play_session
```

WSL 原生进程集成探针为 `scripts/probe_np560_web_lifecycle.py`，传入当前 `--soc-rom`、
`--nand-checkpoint` 和未使用过的 `--output-dir`。探针自行选择空闲端口，仅终止自己
创建且核实身份的 QEMU，不操作现有用户实例，不保存/改写输入 NAND。

最终代码的 Windows 上述测试 47 项通过，WSL 的生命周期/前端测试 34 项通过。
`tmp/np560-web-lifecycle-integration-v2/manifest.json` 已通过真实 QEMU 故障注入：
重复端口不产生 QEMU、原实例 PID 保持不变；终止探针子进程后 health 返回 503，Web
可响应关闭并返回 1；`/bin/false` 作为无法建立 QMP 的子进程时，启动失败有异常记录
且退出码 1 被保留。单元测试还覆盖磁盘满、阻塞读取中断、QMP 超时/繁忙、保存失败和
强制回收；这些不等价于长时间 guest 游戏与存档验收。

v2 集成探针记录的桥接文件 SHA-256 为
`97d652c8dee03403581f9991acb9c2702e77b72edbbcfe55a4b72258421b6d93`。
长跑实例在这一轮末尾的清理增强前已启动，其代码身份以自身 run manifest 为准；
ROM、QEMU 和 NAND 身份不变，不混用两次桥接版本的生命周期验收。

WSL 的桥接/前端测试可运行；`test_monitor_np560_start_menu` 在当前 Ubuntu2 缺少
Pillow，未在该环境计入通过。该模块在 Windows 测试通过，本轮未安装环境依赖。

## 本轮游戏回归发现

`tmp/np560-vma03-lifecycle-ten-minute-v1/manifest.json` 是失败记录：自动导航等待
`5e5577bd…9498947` 的 Hero 行程菜单整屏指纹超时，未开始计时游玩。但原生画面实际
显示“新的征程/再续前缘/退出游戏”，帧哈希为
`ea744585f341d15469c6b131acd58c047073167d32440a1e97984c3e28b4f6e9`，应用状态
`0078`、fault=false、矩阵已释放。截图 `route-timeout.png` 保留在同目录。

NewJourney 步存在两次候选/映射/消费者确认，旧摘要 `logical_guest_events_total=1`
不能代表原始计数只有一次；该重复与整屏指纹差异的关系尚未证明。未替换或放宽旧
golden，也未重启 guest。通过真实 `M53/0x86` 确认后进入地图，证据在
`tmp/np560-vma03-lifecycle-manual-start/`。同一实例随后运行
`tmp/np560-vma03-lifecycle-ten-minute-resumed-v1/`，已完成 600 秒、120 次四方向操作
（每方向 30 次），一次真实 Start 退出，应用 `0078→00FF`、root render `20→30`。
所有检查点均无 ROM_MISSING/UNSUPPORTED/INVALID_CONTROL 报告；最终原始帧已目视
复核为完整桌面。不得将这条有人工确认的运行计为全自动冷启动通过。

- 长跑 manifest SHA-256：`f23d182354481be03049c445bae9acaa94f7159aed9cb3c3fcde73168307b8fe`。
- 最终桌面 raw-gray5 SHA-256：`770e8d5758dc302ab69c845b9185437d7f7a58cd839b48bf4b75ea657653d312`。
- 运行身份：`tmp/web-runs/20260905T044844.094684Z-1819-9c772944/`。
- 回归结束后，仅该 8808 实例经带 token 的关闭请求退出，桥接退出码 0，已核对其
  Web/QEMU PID 均消失。用户原 8807 的 PID 27/28 保留，输入 maps=50、fault=false。

后续优先补齐行程菜单可追溯的像素基准与原厂菜单状态断言，查明 NewJourney 重复映射；
当前期望 hash 未在现存 4,052 份 gray5 快照中找到对应原始帧，不能凭修改常量关闭问题。
