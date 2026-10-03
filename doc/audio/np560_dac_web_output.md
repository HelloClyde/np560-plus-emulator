# Guest DAC 到 Web 的声音输出与复位顺序

日期：2026-09-05。接续 [三路 Timer / DPRAM](../hardware/np560_periodic_timers_and_dpram.md)。

## 本次实现到哪里

QEMU 现在按虚拟时间记录 guest 实际写入的两路 DAC 寄存器值，转换为 PCM 环形缓冲，
Web 在用户点击“启用声音”后交给浏览器 AudioContext。非零诊断采样已从 guest 指令
一路进入真实浏览器 AudioBuffer；没有由前端合成游戏声音或注入 guest 样本。

这关闭的是数字输出端的功能缺口，不是原厂音乐/NPE 声音完成。
`02:ACD8/AD92`、`01:B6DE/B7AA/B816/B84E` 仍缺失；DAC 模拟电路、完整控制位和
精确转换位宽仍待证。本次没有实现这些 ROM 算法，也没有真实声学输出的测量。

## 原厂证据与模型边界

以下地址按原 PRG 的 VMA03，文件偏移为运行地址减 `030000`。

| 原厂代码 | 可约束的行为 |
| --- | --- |
| `24:97AC..9BE6` | 原厂配置/续填/启停使用 Timer 和 DTU，把两路缓冲送到 F1E0/F1E2 |
| `08:33FA..3460` | 从 F1E0/F1E2 读取当前值，用有符号比较决定加减 1，写 REG70/71，逐渐达到目标 |
| `08:3462..34C2` | 对两路做相同目标的渐变；停止流程传入零 |
| `08:4702/475E` | REG70/71 初始化/保存；启动置 REG72 bit 0、清 bit 15，停止做相反操作；另有 GPIO 放大器控制 |

据此，当前输出保留完整 16-bit word，按有符号零中心采样解释，两个写入之间保持值。
REG72 的 `(value & 8001) == 0001` 作为当前功能模型的输出使能；其它位保留但尚未建模。
模拟滤波、精确 DAC 分辨率、放大器 GPIO 和其它启停边界不能从这几段代码全部推定。

48 kHz 是宿主呈现频率，不是宣称原机 DAC 固定以 48 kHz 工作。
guest 的 Timer/DTU 决定寄存器何时改变；呈现端在虚拟时间线上保持采样，不以 HTTP
轮询、浏览器帧率或宿主 sleep 驱动 CPU/外设。尚未模拟模拟重建滤波和全部音画竞争时序。

## 实现路径

- `qemu-dmcu/hw/dmcu/np560_audio.c/.h`：写前累积旧采样、写后锁存新值；虚拟时间
  回调补齐持续输出。固定 200 ms 环形缓冲，有帧序号和复位 generation。
- CPU 直接 REG、banked/unbanked MMIO 和 DTU 共用原有 SFR 写入边界，板级分派到
  timer 或 audio；直接计时 SFR 操作也经过 TCG I/O 边界，已检查 icount 模式。
- `/machine` 的只读 `audio-pcm` 属性返回 s16le、48 kHz、双通道数据。读取不推进时间、
  不出队、不修改 guest；暂停后连续读取完全一致。慢客户端能从序号检测已丢失的范围。
- `scripts/web/np560_web.py` 的 `/api/audio` 校验格式、长度、序号和 generation，
  另加进程 stream_id，避免把重新启动的实例误认成旧流。
- `scripts/web/audio_output.js` 只播放未消费的新采样，处理重复包、缓冲缺口、复位及
  实例更换。默认不创建 AudioContext，点击后启用；关闭/离页停止队列并取消请求。
- 宿主监听增益 0.25 是播放端衰减，不是替 guest 设置音量。实际原厂音量和媒体服务仍需贯通。
- 浏览器关闭/停止会取消在途读取。HTTP 响应现在将 BrokenPipe/ConnectionReset 作为
  客户端断开处理，不再向同一断开连接发送第二次错误；其它写入错误仍然暴露。

## 查到并修复的共同复位错误

旧板级顺序为：`qemu_devices_reset()`，随后才手动 `cpu_reset()`。
独立 DMCU CPU 不在 legacy qbus 复位遍历中；audio reset 因而读取了旧 REG70/71/72，
timer reset 也从旧 PLL/CLKCON 推导频率。CPU 最后清零并不会再次更新这些设备缓存。

用 guest 设置 DAC 为 `1234/EDCC`、使能为 1，并启动 2 MHz 周期 Timer2，暂停后复位：

| 观察项 | 修复前 | 修复后 |
| --- | --- | --- |
| DAC 寄存器缓存 | `1234,EDCC,0001`，错误保留 | `0000,0000,0000`，输出关闭 |
| Timer2 状态 | 已停止，但保留旧 2 MHz 频率 | 停止、计数/控制清零，按当前复位寄存器得到 24.576 MHz |
| PCM | generation 已换，却仍有错误的后续采样状态 | generation 换代，帧序号归零，旧输出状态清除 |

修复是先复位共享 SFR 所属的 CPU，再复位依赖这些寄存器的设备；不是在 Web 静音来
掩盖残留值。24.576 MHz 指当前时钟模型的零寄存器结果，不是新增的真机上电实测结论。

反例：`tmp/np560-audio-output-v1/active-reset-before.json`，passed=false。
修复后：`tmp/np560-audio-output-v2/active-reset.json`，passed=true。

## 验证证据及适用构建

当前 QEMU：46,552,680 bytes，SHA-256
`a144d54806e745731f651d5acbbcc85b5292990aa713bc25c76e65abc7aae8f4`。
复位修复前的 audio 构建为 `938d2f9a35af22132d664680a8c9279cd0c1df87e5adfd357e5c63e99902e837`。
两者不能混称一次整机验证。

### 当前构建

- `scripts/tests/test_np560_audio.py` 普通及 icount=5 执行通过：未修改原厂 `08:33FA` 渐变，
  有符号左右声道、banked/unbanked/直接寄存器、使能/掉电静音、暂停只读和活动中复位。
  原厂函数逐字节取自原 PRG；外围是明确的诊断 guest，不是完整原厂游戏。
  报告及采样 WAV 位于 `tmp/np560-audio-output-v2/`。
- `tmp/np560-audio-browser-pcm-v1/report.json`：当前二进制和当前 Web 代码，真实
  Edge headless AudioContext 为 running；guest 诊断 word `1234/EDCC` 通过 HTTP
  得到 AudioBuffer 左/右值 `+0.1422119140625/-0.1422119140625`，采样率 48000。
  默认未创建声音上下文，关闭后上下文及播放队列释放，页面无 JS 异常。
  这是数字播放链验证，不是原厂解码或实际扬声器测量。
- `tmp/np560-audio-cold-boot-v1/report.json`：94.4 秒，零按键、零宿主 guest-memory
  写入、不保存 NAND；最后三次学习顶栏均 0/5280 差异，CPU/ROM/控制流故障 none，
  NAND ERROR=0。`final.png` 已查看，桌面、学习菜单、开始按钮及时间正常。
- Web 前端 21 项、生命周期 16 项及 PCM 解码/调度单元检查通过；未将次数作为完成度。

### 复位修复前的原厂操作检查（保留适用范围）

`tmp/np560-audio-native-web-v1/20260905T123137.104527Z-20092-102fa070/`：
原厂冷启动显示正常；Start 55、确认 53、下 37、确认 53 的普通 120 ms 矩阵按键
进入 NPE 文件列表，四次均由前台消费，maps 0→4，见 `tmp/np560-audio-native-route-v1/`。
Browser 的声音开关也工作，但该原厂菜单闲置时是静音，不能算音乐播放。

选择《英雄传奇》仍失败：`tmp/np560-audio-native-hero-v1/01-Hero-failed.json`，
`PC=02:ACD8`、`ROM_MISSING=02:acd8 PREV=25:dfba/bd02`，非法指令/控制流故障 none。
本次显式启用 `--soc-rom-skeleton`，没有跳过未知 ROM。该 NPE 失败不是完成游戏验收。
三路 Timer、六种原厂双路传输组合及 icount 检查也在该 audio 构建通过。

## 尚未完成

- 原厂 codec/流服务仍缺，音乐播放器和 NPE 原生声音仍未贯通。
- 全部音频控制位、模拟转换/滤波、放大器、录音输入及设备迁移未闭合。
- 浏览器丢包恢复是呈现策略，不替代 SoC 的总线竞争和时序正确性。
- 本次未修复间歇性菜单/资源损坏；一次冷启动正确不能关闭那个问题。
- PRG、guest ROM、NAND 未改；隔离检查不保存 NAND，不操作用户 8807/8808/8809。

下一步回到 [ROM 流后端](np560_resident_stream_backend.md) 的实际缺口和原厂使用链，
不能把“声音输出端已接通”扩大成“游戏已经完整可玩”。
