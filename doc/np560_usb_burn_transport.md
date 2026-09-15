# 原厂烧录输入字节序与 NAND 生成验证

日期：2026-09-05。承接 `np560_vma03_menu_corruption.md` 的混合 lane 花屏定位。
本记录区分调试传输边界、原厂 guest 烧录、离线核对和正常系统冷启动，不把其中一项
通过等同于完整 USB、完整 mask-ROM 或 NPE 交付完成。

## 输入与执行边界

- 原包 `NP560+V3.80版系统升级程序/NP560+.upd` 的校验和为 `657061162`。
- 使用包内 slot 0 的原厂 burner，97,416 字节，SHA-256
  `9cea0c9a5be8ab2d72e382cdc69d6314807a56d61517b2210807afbe597982e7`。
  它与目录中独立的 `BURN_NAND_FLASH_CODE.bin` 不同，后者为 97,412 字节、SHA-256
  `efec500f345b1dee11dd4aef95cc555a002e47943241176cde2ba6447c3b7cc0`。
  包内版本应使用 `NP560_UPD_block0_full_reachable.asm` 的地址；旧观察器写死独立版本
  PC 的计数可能为零，不可据此认定原厂函数未执行。
- slot 3 为 43,963,316 字节，SHA-256
  `44c3c0332ceab48e95202effc1a6c4f52a07384c4149becf039384ea0c0330ce`。
  开头的 512 字节 `MASKROM NP560 VER3.65` 记录保留，不从 payload 中剥离。
- `burn_np560_stream.py` 在物理 RAM 调试输入边界实施原厂 loader 的 MOVB lane 编码；
  原厂命令 13 负责实际 NAND 写入，命令 18 负责提交。没有 host NAND/ROM-HLE 代写。
  真正的 USB 枚举、端点 FIFO 和线协议并未实现或验证。
- 当前实验使用 VMA03 普通重建 ROM `a04f1b83…ebc2`、同一 QEMU 构建
  `3a9abb55…de43`。harness 是显式诊断程序，不是替换后的产品 PRG。

## 已完成的最小烧录验证

| 实验 | 初始 NAND | burner | 实际写入与离线结果 |
| --- | --- | --- | --- |
| `tmp/np560-usb-burn-lanes-v3/` | 旧 native-PIM v6，只读加载 | 独立版 | 首 49,152 字节零差异，96/96 对应 ECC 正确；全镜像已有 ECC 590/590 |
| `tmp/np560-usb-factory-prefix-v1/` | 仅最小 factory 记录，其余全 FF | 包内 slot 0 | 首 49,152 字节零差异，96/96 对应 ECC 正确；全镜像已有 ECC 597/597 |

两次都由 guest 执行格式化/流写入/提交，不是写后扫描并修补 NAND。
两份 prefix 的逻辑 SHA-256 均为
`0db521812a54d8f1046786f71634191c2d828b38bd14bb0f91a6bcaf638f99b7`。
输出分别位于 E 盘的 `np560-usb-burn-lanes-v3.nand` 和
`np560-usb-factory-prefix-v1.nand`，原始用户输入文件未覆盖。

factory-only 输入由 `build_np560_factory_nand.py --rehash-tool ...` 生成：
物理页 `0x3F` 的已逆向记录和 OOB 保留，其余 512 MiB 数据与 OOB 全 FF。
这是最小逆向 fixture，不是真机出厂转储。新增分块生成路线与旧生成器在小几何测试中
逐字节一致；实际大镜像经 QEMU checkpoint loader 完整 FNV 校验后成功载入。

## 原厂升级器的格式化决策

`UpdateAll.exe` SHA-256：
`1e219b606b8e800a19db8c075de22e2d5c755c9a45e38c219d47616f6396aac6`。
只做静态反汇编，未在宿主执行升级器。

1. `0x4023BC..0x402440` 发命令 1 并通过 `0x404070` 收取结果。
2. `0x4024D7` 的异常处理读取对象 `+0x0C`（结果类别）、`+0x10`（细节）。
   `0x4025DC..0x40261E` 接受类别 `-11` 且细节为 `-2/-3` 的检测失败，显示
   `Nand Flash FD NFTL ERROR!`，随后经 `0x402818..0x40283B` 继续到命令 27。
   其他错误有别的分支，不能一概忽略。
3. `0x40284E` 发命令 27，`0x4028AC` 比较返回结果是否为 `-12`。
   仅该分支进入 `0x402928` 的命令 11，`0x40297F` 写入所需分区大小；
   随后 `0x402A2B` 发命令 2。非 `-12` 在这里跳往 `0x402B0C`，跳过这段格式化。
4. `0x404070` 的错误辅助路径读取 guest `50:001C`；`0x402FF0` 依据类别构造异常，
   `0x403FD6/0x403FD9` 将类别和细节分别存到异常对象上述字段。

factory-only 实验记录的固定序列为 `23 → 1 → 27 → 11 → 2 → 25`，
命令结果依次为 `0000, FFF5, FFF4, 0000, 0000, 0000`；观察到内部 storage status
先为 `FFFE`，命令 2 后为零。这与“检测失败后重新分区”的原厂分支相符，但现有
setup 快照保存的是 `50:0860`，并非每一步的 `50:001C` 与完整 ProgramGetResult。
因此后续版本必须记录完整结果并按原厂条件执行，不能把固定命令列表称为已经复刻
全部错误处理。特别是已格式化输入上命令 27 返回零时，本轮固定 harness 仍强制
执行了命令 11，这属于显式重格式化测试，而不是原厂的默认跳过分支。

### 条件分支版本：实际双输入、最小出厂整包烧录与冷启动均通过

`build_np560_stream_burn_harness.py` 与 `burn_np560_stream.py` 的 CLI 默认已改为
`updateall`。harness 只自主执行一次命令 23，随后等待宿主按照原厂返回码提交命令；
旧 `official` 模式保留为明确的固定重格式化诊断。启动前校验 harness 内容，避免
错用旧程序导致它先自主格式化，之后才发现协议不匹配。

- `E0:0030` 保存原厂返回的 `R0..R3`、`50:001A` 结果、`50:001C` 细节、分区 base/extent。
  原厂 `50:7DB8` 将结果符号扩展到 `R0:R1`，传输端核对两种结果一致。
  `50:0860` 是内部状态，不能拿它代替宿主错误细节。
- 命令 1 的 `(-10,-2)` 分支先执行命令 2；`(-11,-2/-3)` 继续命令 27；未知错误明确停止。
  命令 27 为 `-12` 才执行 11、2，为 0 则跳过；其他未知结果不猜成成功。
- 分区请求由原厂 `UpdateAll.exe 0x404A8F..0x404AAC` 的公式计算：
  `ceil((slot3_length + 0x110000) / 1024)`。当前原包结果为 `0xABF5`，不是拍定的固定常量。
  命令 25 使用完整 slot-3 长度和原厂 `0xC000` 缓冲大小，即使只做 prefix 实验也如此。
- 每条命令保存独立结果和生命周期记录，harness 不实现 NAND/FTL/ROM 服务。

| 新实验 | 实际命令及原厂结果 | 实际写入证据 |
| --- | --- | --- |
| `tmp/np560-updateall-factory-prefix-v1/` | `23 → 1(-11,-3) → 27(-12,-3) → 11 → 2 → 25`，其余成功 | 49,152 字节零差异，96/96 对应 ECC 正确；setup PROGRAMS=380，首块 421，提交后 423 |
| `tmp/np560-updateall-formatted-prefix-v1/` | `23 → 1 → 27 → 25`，均成功，确实没有执行 11/2 | 49,152 字节零差异，96/96 ECC 正确；setup PROGRAMS=16，factory 页 PAGE3F 的 P/C/E 均为 0 |

两次命令 18 均成功，NAND `ERROR=0`、`MASKROM_WRITES=0`。输出在 E 盘对应的
`np560-updateall-*-prefix-v1.nand`，输入未覆盖。已格式化实验只证明 prefix 和跳过分支，
不拿局部传输断言整个映射都未改变。

最小 factory-only 输入的完整 43,963,316 字节烧录已完成：
`tmp/np560-updateall-factory-full-v1/`，run_id `20260905T071453.748784Z-9380-fbdc252c`，
QEMU PID 9382，输出 `E:/qemu-dmcu-build/np560-updateall-factory-full-v1.nand`。

- 实际按 `23 → 1(-11,-3) → 27(-12,-3) → 11 → 2 → 25` 准备，流写入全部 payload，
  原厂命令 18 提交成功，退出码 0。最终 PROGRAMS=43,338、READS=249,017、
  ERASES=16,724、COPIES=21,347，ERROR=0、MASKROM_WRITES=0。
- 输出 553,648,192 字节，SHA-256
  `9da1cc971c75fa58c1debe8d04edd8b59acb428de18b21da79d1f50a18576ef3`。
  与下文之前 v3 起步的 full-v1 输出长度及 SHA-256 完全相同；现在已证明无需旧用户
  checkpoint 作初始输入即可再生这个系统镜像。最小 factory 记录仍是逆向 fixture，不是真机 dump。
- 全部 43,963,316 字节及末尾 76 字节 padding 为零差异；85,866/85,866 对应 ECC 正确。
  全 NAND ECC 扫描为 86,367/86,367 正确。离线报告为本目录 `payload-verification.json`。
- `tmp/np560-updateall-factory-full-boot-v1/` 使用原始 PRG 与普通重建 ROM，
  零注入按键、零 host guest-memory 写入、无 NAND 保存，约 63.28 秒自然进入完整学习主菜单；
  连续三个指定顶栏结果均 0/5,280 像素差异，ROM-HLE 关闭，三个 CPU 故障字段均为 none，
  NAND ERROR=0。`final.png` 已目视确认；输入由 QEMU 独立完成 FNV 检查。
- 文件 API 导入实验使用的 full-v1 输入与本次输出为同一内容 hash，因此其完整游戏写入、
  冷读回和原厂文件列表结果可以复用，见 [文件导入专题](np560_vendor_file_transfer.md)。
  那里的选择文件后 resident 冲突仍是实际未解决项，不能将系统生成通过叫作 NPE 可玩。

## 不依赖搜索的离线校验工具

`scripts/verify_np560_burn_payload.py` 按 factory 页的 partition base 和最后页 OOB 的
三份一致 block tag 建立映射，不扫描 payload 寻找“最像”的位置：

```text
tag = factory_partition_base + logical_address // 0x20000
physical = unique_block_for_tag * 0x20000 + logical_address % 0x20000
logical_address starts at 0x110000
```

缺失/多义映射直接失败。按确定的 DMCU 字节总线约定还原每个 512 字节 sector，
检查全部选定 payload、末尾 FF padding 和对应全部 8 字节 ECC descriptor。
每次报告明确标记 `guest_ftl_readback_verified=false`、`checkpoint_fnv_verified=false`；
离线映射不代替 guest 文件/FTL 实际读取，FNV 则由后续 QEMU 加载独立验证。
四项单测覆盖准确数据、尾部填充、错误数据/ECC、错误 lane、缺失和重复映射、factory
签名拒绝，Windows/WSL 均通过。

## 完整烧录、全量校验与零输入冷启动通过

`tmp/np560-usb-burn-full-v1/` 已完成包内原厂 burner 的完整 slot-3 输入，
命令 18 提交成功、NAND `ERROR=0`、`MASKROM_WRITES=0`，程序退出码为 0。
初始输入为上述 v3，本轮强制重新格式化；没有烧录后的局部修补步骤。

- 输出 `E:/qemu-dmcu-build/np560-usb-burn-full-v1.nand`，553,648,192 字节，SHA-256
  `9da1cc971c75fa58c1debe8d04edd8b59acb428de18b21da79d1f50a18576ef3`。
- `payload-verification.json` 核对全部 43,963,316 字节及末尾 76 字节 FF padding，
  **0 字节差异、85,866/85,866 对应 ECC 正确**；映射后内容 SHA-256 与原包 slot 3
  的 `44c3c033…30ce` 完全一致。缺失/多义映射均为零。
- `analyze_np560_ecc_checkpoint.py --minimum-descriptors 85866` 进一步扫描整个 NAND，
  **86,367/86,367 已存 ECC 正确**，21,594 个有 ECC 的物理页，其中 4 页只写了部分扇区。
- `tmp/np560-usb-burn-full-boot-v1/report.json`：普通 ROM + 原始 `NP560.PRG`、
  `firmware-vma03`，**零注入按键、零 host guest-memory 写入、无 NAND 持久化**，
  新实例约 59.14 秒到达清晰的学习分类主菜单。指定顶栏连续 3 次为 **0/5,280 像素差异**。
  `ROM_MISSING/INVALID_CONTROL/UNSUPPORTED=none`，ROM-HLE 关闭，NAND 无错误。
  冷启动也独立通过了 checkpoint FNV 校验。保留 `final.png`、`final.gray5`、完整状态
  和生命周期记录。测试没有追加 PIM/菜单资源或故意发 Start 键。
- 控制组 `tmp/np560-boot-probe-baseline-v1/` 使用之前的菜单局部修补副本，
  同一工具约 58.36 秒通过，证明检查工具并非只为新 NAND 选择另一套期望像素。

### 五分类往返：单扫描与普通短按均通过

完整烧录 NAND 在独立 Web `8809` 运行，run_id
`20260905T064719.700665Z-9010-660fae21`，bridge PID 9010、QEMU PID 9012；
输入 NAND hash 由 `tmp/np560-usb-burn-full-web-v1/.../status.json` 绑定。
没有挂接输出 NAND 保存，也没有替换用户 8807/8808。

同一实例连续测试 `学习 → 辞典 → 网络 → 记事 → 系统 → 记事 → 网络 → 辞典 → 学习`：

- `tmp/np560-usb-burn-full-menu-v1/single-scan/`：8 次真实矩阵单扫描操作，
  每次 map/foreground ack 都恰为 1；初始及每步的 9 张顶栏均 **0/5,280 像素差异**。
- `ordinary/`：普通 held-level 按下、观察消费、释放，8 次操作同样每次只消费 1 次，
  均观察到释放；对应 9 张顶栏再次全部 **0/5,280 像素差异**。
- `single-scan-pixels.json`、`ordinary-pixels.json` 使用相同原包期望和预定分类，
  不是对截图搜索最近类别。后者共完成累计 map `8 → 16`。

这覆盖了引发本次花屏的五分类往返，但不能替代长按/多轮压力；旧副本普通路线
第 32 次操作的多消费现象仍需单独关闭，音乐和 NPE 也未在新 NAND 上重新验收。

尚须全部文件 API、NPE 完整运行与应用验收；离线全内容校验及五分类读取不能证明
全部文件 API 都正确。最小 factory-only 输入的条件分支全量与冷启动已由上文独立实验完成，
不再依赖这里的 v3 起步强制格式化作为唯一生成路线。

所有新大 NAND 写在 E 盘；用户 8807/8808 的进程、状态和持有的镜像不重置、不覆盖。

## 诊断补充与已知限制

- stream 脚本新增独占输出、输入 hash、RunJournal、setup/首块/final/failure 状态保存、
  有界 QMP 超时、可禁用大型失败 NAND，且只回收自己启动的子进程。
  已完成的 full-v1 启动早于最后的 hash/RunJournal 补充，其 inputs 和四个阶段文件
  保留，但不能声称已有尚未载入的新版日志字段。
- 两次旧 `firmware` 映射启动在 `system/physmem.c:989` 的
  `phys_section_add` 发生 2,048 section 上限断言。先暂停启动有助保留诊断，但不修复
  此断言；当前 `firmware-vma03` 路线可正常运行。旧映射故障尚未修复。
- 音乐播放器、声音输出、held-level 多消费事件、真实存档和原厂级完整 USB 仍未完成。
- 本轮定向测试：burn 相关 18 项、factory 生成 2 项、冷启动检查/PNG 编码 4 项通过。
  冷启动探针不依赖 WSL Pillow，PNG 直接从 raw gray5 生成，含行复制和 CRC 单测，
  Windows/WSL 均通过。没有改 Web 字体、素材或用截图覆盖 guest 绘制。
