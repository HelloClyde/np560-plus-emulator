# ST7529：显存读缓存与读改写模式

日期：2026-09-06。补齐本机 8-bit LCD 接口的 RAMRD 读取流水线和 RMWIN/RMWOUT。
这是真实 MMIO/GRAM 行为的实现，不是 Web 擦除残影，也没有证明历史菜单损坏由此引起。

## 原始依据

按 PDF 技能检查 [ST7529 v1.8 原件](../../tmp/pdfs/ST7529.pdf) 的完整相关页：

- 第 20 页 7.2 / 图 7.2.1：MPU 读取通过内部 bus holder，首次读为 dummy，
  当次取得的数据在后续读周期返回；不能把首次结果当成窗口首字节。
- 第 36 页命令表：`E0` / `EE` 属于 EXT=0 命令。
- 第 44 页：RAMWR/RAMRD 从配置窗口的起点开始，其它命令结束本次传输。
- 第 45–46 页：RMWIN 从窗口起点开始，读取不改变列/行地址，写入才递增；
  RMWOUT 或任意其它命令取消模式。这里没有其它型号的“退出时恢复保存列地址”语义。
- 第 49 页：普通 STREAD 的 bit5 表示 RMW in/out。
- 第 63 页：两种像素格式的示例均是每组先 dummy read，再读两/三字节，修改后写回。

PDF SHA-256：`8565fc8d1f917f89667d1ac3439699888f669ec0ac774438d852848371d02031`。
Dummy 返回值未指定；实现保留旧读缓存内容，测试明确丢弃它，不要求固定零或特定真机电平。

## 原模型的两个独立错误

旧核心 `920620dd6bdc7f42269f259e78c1851961ed4ac5a2e986997f0a9fec2d7dac16`：

1. 正常 RAMRD 立即返回像素，没有读取缓存。按手册先丢弃一次后，应从 `08 40 A8`
   读起，实际却从 `40 A8 38` 读起，字节整体错开。
   见 [读取反例](../../tmp/np560-lcd-read-before-20260906-v1/ramrd-dummy-and-wrap-gs2.json)。
2. RMWIN 完全未实现，状态仍是 `CA` 而不是 `EA`，后续数据读为零、数据写入被忽略。
   见 [读改写反例](../../tmp/np560-lcd-rmw-before-20260906-v1/rmw-cycle-gs2-scan0-clr0.json)。

两个反例均执行到预定终点，寄存器/栈检查通过，QEMU 正常退出 0；测试失败来自 LCD
实际结果不符合手册，不是 CPU 崩溃或缺失 ROM。总报告的空 cases 不覆盖单项已保存的失败记录。

## 实现

`qemu-dmcu/hw/dmcu/np560.c`：

- 独立保存读取字节阶段和 bus holder。每次数据口读取返回前一次缓存，同时预取下一字节；
  普通 RAMRD 仍按两种像素格式、窗口及 C/L 方向递增和回绕。
- EXT=0 的 RMWIN 重置到窗口起点，同时允许数据口读与写。
- RMW 读取完整像素组后仍停在该组，写完完整组才递增。下一组的读取阶段重新开始，
  因此沿手册示例执行 dummy/read/modify/write 可以连续处理窗口。
- 读/写字节阶段分离，避免读缓存的预取阶段被误用为写入字节下标。
- 任意新命令取消 RMW 和未完成的写入组；重新 RMWIN 从起点开始，RAMWR/RAMRD
  则回到各自普通传输。RMWOUT 仅退出，不虚构保存地址及恢复栈。
- STREAD 返回实际 RMW 标志；状态口读取不使用显存读取缓存、不取消模式。
- 复用现有 memset 设备复位清除模式与缓存。未放开整机快照；以后序列化必须包括这些状态。

没有改变 CPU 指令、PRG、resident ROM、NAND、玻璃接线或 Web 像素呈现。
EXT=1 下没有把 E0 冒充为 RMW；这不代表其余扩展命令已经完整实现。

## 测试约定的纠正与验证

旧 `test_np560_lcd_formats.py::read_bytes` 同样漏掉 dummy read。
本次在该公共 helper 中增加一次 guest 丢弃读取，不移动预期像素、不改变预期 GRAM。
格式、扫描和部分显示检查复用该 helper，因此也验证了正确的总线调用方式。
此前的格式结果仍能说明打包规则修复，但不能作为完整 RAMRD 时序正确的证据。

新增 [读改写检查](../../scripts/tests/test_np560_lcd_rmw.py) 复用既有运行器，由 guest 实际读字节、
用 AND 清 bit7、写回数据口，随后读回并比较实际 LCD。不是宿主修改像素或计算后注入。
覆盖两种格式、两种扫描主方向、CLR、重复读取保持地址、写后回绕、半组取消、重新进入、
普通 RAMWR/RAMRD 恢复及 EXT=0 限制；不宣称所有不完整总线交错的真机行为已核对。

新核心 SHA-256：`939c68c0be78e26d13d580c786f5249a04d7e5fa08fd096b766030ba420624fd`，
46,830,280 bytes。旧核心保留于 `E:/qemu-dmcu-build/qemu-system-dmcu-pre-lcd-rmw-20260906`。

| 同一新核心上的检查 | 结果 |
| --- | --- |
| RAMRD / RMW 普通执行 | [15 项通过](../../tmp/np560-lcd-rmw-after-20260906-v1/report.json) |
| 同组检查 icount=5 | [15 项通过](../../tmp/np560-lcd-rmw-icount-20260906-v1/report.json) |
| 两种数据格式 | [12 项通过](../../tmp/np560-lcd-rmw-formats-20260906-v1/report.json) |
| 部分显示、隐藏区 GRAM、正常状态 | [12 项通过](../../tmp/np560-lcd-rmw-partial-20260906-v1/report.json) |
| 行列方向、CLR 与状态电极 | [9 项通过](../../tmp/np560-lcd-rmw-scan-20260906-v1/report.json) |

所有上述隔离进程已正常退出 0；这些检查没有 NAND 或运行中 host RAM 注入。

## 同一核心的原厂冷启动

使用原始 PRG、严格缺口 ROM 与既有 vendor-file-import-v3 NAND，不注入按键、
不写 guest RAM、不启用 NAND 保存。97.13 秒完成启动检查，最后三个学习顶栏样本
与原升级包资源均为 0 / 5280 像素差异，见
[启动报告](../../tmp/np560-lcd-rmw-boot-20260906-v1/report.json)。
[实际 LCD](../../tmp/np560-lcd-rmw-boot-20260906-v1/final.png) 已目视核对，
顶栏、学习菜单、开始按钮和时间均正常显示。

ROM_MISSING、INVALID_CONTROL、UNSUPPORTED 均为 none，HLE off，NAND ERROR=0。
run `20260906T153417.012445Z-203-cfaaf5a5` 的 QEMU PID 205 已回收，退出码 0；
输入 NAND 检查后哈希仍为 `7783876b3efd04dc0e169b7a339f168b8557bea5a396ca4aaf0bc7424848e413`。
没有新增大型 NAND，没有操作用户 Web 实例。这里只证明默认启动没有回退，
不外推为全部菜单/窗口交互或游戏已经完成。

## 保留的整机缺口

区域滚动手册中的歧义、EEPROM/EPSRRD、完整灰度/电气控制、其它物理接口及完整设备迁移
仍未解决。没有原厂应用使用 RMW 的动态调用证据，不能把本次硬件能力补齐表述为已修好
某个特定原厂窗口、光标或历史时间残影。
原厂声音的表模式、MP3 初始化/解码与 NPE 流 ROM 服务缺口没有变化。
