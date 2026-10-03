# VMA03 一级菜单花屏现场（2026-09-05）

2026-09-06：另一个可复现的输入问题已定位为 Web 的 120 ms 点按低于原厂两次扫描门槛，
并修正传输排队未计入接触时间的问题，见 [Web 点按去抖](../web/np560_pointer_debounce.md)。
同镜像 150 ms 物理电平的菜单往返通过；这不是本篇旧混合字节顺序花屏的另一解释，
也没有证明下文旧 held-level 的重复消费现场已得到完整解释。

状态：首因已闭合为 checkpoint 的混合字节顺序；原包重建的隔离副本已通过五分类
逐像素验证。后续已用原厂 burner 完整生成新 NAND 并通过全原包/ECC、零输入冷启动
检查，见 `np560_usb_burn_transport.md`；本篇局部块修补副本仍不能称为 canonical NAND。
用户在 8807 切换分类后提供截图；对 8807 只读采集，没有发送按键、改写 guest RAM、
重置或重启。以下“初始现场”保留取得进一步证据前的判断边界。

## 首因与隔离验证（本轮最终结论）

原厂 `NP560+.upd` 的 slot 3（起点 `0x42ABAC`，长度 `0x29ED3B4`，SHA-256
`44c3c0332ceab48e95202effc1a6c4f52a07384c4149becf039384ea0c0330ce`）包含全部完整顶栏。
运行期 trace 的资源指针指向像素主体，完整序列须先减 10 字节头；再减官方烧录起点
`0x110000` 才得到 slot 3 内偏移，不能直接按指针去取头。

例如“学习”序列从逻辑 `0x2471597` 开始，原包 slot 3 offset `0x2361597`；
与首次 `root-top-source.bin` **全部 2,650 字节一致**。
对应 checkpoint 的物理块 `0x890`、块内 offset `0x11597`，按外部 A0 反转逐字节
读取也与同一序列完全一致。这补齐了之前缺失的包→NAND→source→object 对照。

对完整逻辑块 `0x2460000..0x247FFFF` / 物理块 `0x890` 的 64 页逐页核对发现：

- 物理页 `0x22421..0x22423` 三页等于原包的 word-lane 编码（每个 16 位字交换字节）；
- 其余 61 页等于未换序的原包字节，并非随机损坏或缺失内容；
- “辞典、学习”落在三页的覆盖范围内；“网络”的头正常但主体跨入未换序页；
  “记事、系统”的头本身已落在未换序页。这精确解释了分类相关的差异。

旧 NPE 导入 manifest `tmp/np560-v735-hero-fat16-ab-guest-dots.json` 指明来源是
`np560-v380-root-toolbar-selected-page-lanes-v654-run.nand`。结合上述逐页实测，
当前失败链保留了旧“只修部分顶栏页”的中间镜像，不是缺失新的绘图 ROM 函数。
仍须沿 USB staging / burner / NAND 传输链确定换序的正确生产层；目前不改变 QEMU
全局字节语义，也不在 Web 补画。

### 可重复的诊断副本

新增 `scripts/audit_np560_package_block.py` 默认只读审计；可指定新的输出路径，
从校验通过的原包统一重建一个完整资源块。已有页必须逐页匹配“raw-package”或
“lane-encoded”，有未知修改、越界、缺签名 ECC 或输出已存在时拒绝，禁止就地覆写。
它保留其余块与 OOB，重算变更页 ECC，并使镜像哈希失效，随后由 native rehasher
重新计算两个完整数据平面的 FNV。不是按菜单轮廓/像素改字节，也不是重复把已正确的
三页交换回去。

```powershell
python scripts/audit_np560_package_block.py tmp/np560-vma03-native-pim-v6.nand `
  --package 'NP560+V3.80版系统升级程序/NP560+.upd' `
  --logical-start 0x2460000 --physical-block 0x890 `
  --destination E:/qemu-dmcu-build/np560-vma03-menu-block-lanes-v1.nand `
  --report tmp/np560-menu-block-lanes-v1.json
wsl.exe -d Ubuntu2 -- /mnt/c/Users/ASUS/Documents/ChatGPT/np560/tmp/np560_checkpoint_rehash `
  /mnt/e/qemu-dmcu-build/np560-vma03-menu-block-lanes-v1.nand
```

实际改变 61 页中的 34,550 个数据字节及对应 ECC。新副本全文件 SHA-256 为
`1652574a9e5916f4c04004015f21843cee86083c94a53af48193243ad30e7249`；原副本仍为
`d553c53db130342f71f0b988e4dec400d3ff048ec1b271d82b9a05605f3f1706`，未被修改。
再次只读审计新副本，整个块相对期望 **0 字节差异**。

### 像素与输入验证必须分开

隔离运行记录：`tmp/web-runs/20260905T053800.935878Z-6947-6324713f/`，端口 8808。
ROM、QEMU、原始 PRG 与旧实例相同；只有 NAND 副本不同。未注入启动按键，
`route/00-before.json` 的零映射/零键盘事件状态已自然进入完整桌面。

新增 `scripts/verify_np560_toolbar_frames.py` 直接从校验通过的原包生成五张期望：
高 nibble 优先 gray4，post-INV gray5 为 `31 - 2 * gray4`。不从截屏更新 golden，
不拟合位置/像素排列，也不靠“哪个分类最相似”自动更换期望。

- 用户的原花屏 `full.gray5`：对“网络”原包期望 **1,262/5,280 像素不同**；
- `tmp/np560-menu-lanes-regression-v1/route/`：初始学习及往返 8 次切换共 9 帧，
  五分类 **9/9 帧、每帧 0/5,280 差异**；
- `single-scan/`：5 轮往返、40 次单矩阵扫描输入，映射与前台消费每次恰为 1。
  初始帧加 40 帧共 **41/41 帧零差异**，全程探针无 ROM 缺失、未知指令和非法控制流；
- `repeated/` 的普通 held-level 40 次路线**没有通过预期导航回归**：第 32 次左键
  `maps/foreground ack 39→41`，从学习继续多走到开始菜单（索引 0），其后期望错一格。
  该失败保留在 `repeated-pixels.json`，不能以单扫描通过代替普通输入验收，也不能把
  原脚本的布尔 `logical_guest_events_total=1` 当作真实单事件计数；保持时长与重复
  产生条件仍待跟踪。`repeated-first-failure.png` 显示的是清晰的开始菜单，不是旧花屏。

该副本尚未重跑 NPE 长程、音乐播放或全资源范围验证。两个新工具及其单元测试与
原包解析测试合计 9/9 通过（其中包含坏像素/错位反例、未知页/ECC/覆盖拒绝用例）。

## 正式导入链：RAM 注入边界与原厂烧录验证

后续进展见 `np560_usb_burn_transport.md`：实际原厂 burner 已在旧输入和最小 factory-only
输入上完成首 48 KiB 格式化/写入/提交，原包字节和 96 个 sector 的 ECC 零差异。
完整 slot-3 烧录现已完成，全原包 0 字节差异、85,866/85,866 对应 ECC 正确，
独立零输入冷启动的首个顶栏连续三次 0 像素差异；全分类/文件及自然初始化仍须验收。
下面保留原始 RAM 边界证据。

原厂 `USB_Loader_Noah.bin`（SHA-256
`482e5f84dab922cf1af06eb76e93e1e22edea2c53ee90aed0c1880878aec0cd9`）
须按字节 PC 分析。旧 `USB_Loader_Noah_reachable.asm` 使用过时的 PC 步长，不作为本项
地址证据；重新生成的 `USB_Loader_Noah_byte_pc_reachable.asm` 有 980 条可达指令、
21 个调用目标、零未知指令与重叠。复现命令：

```powershell
python scripts/np560_aux_disasm.py 'NP560+V3.80版系统升级程序/USB_Loader_Noah.bin' `
  --base 00:1000 --entry 00:1000 --entry 00:17E4 --endian big `
  --name USB_Loader_Noah_byte_pc --output-dir doc
```

原厂接收循环：`00:194C` 从 `F230` 读取 R0，`00:1950` 的原字 `1B81` 执行
`MOVB [R8++], RB1`，`00:1952` 累加校验。**RB1 是 R0 低字节**，这与内存偶地址
选择 16 位字高字节的规则是两个不同概念，不能混淆。
DLL 静态链是 `usb_Lib_DMCUWriteData → 10001300 → 10005720 → 10006840`；
`10006A01` 的 bulk OUT 传递原 payload 指针，未见对 payload 换序。

现有 `burn_np560_stream.py` 用调试接口直接把 wire bytes 写入物理 staging RAM，
绕过了 loader 的 byte store。新增 `np560_usb_transport.py` 仅在这个接口边界对齐编码；
`send_chunk` 先按协议补齐 512 字节，再交换每个 16 位字的物理存储顺序。
命令字段仍以原来的数值字写入，不对所有控制参数、NAND DMA 或 Web 像素做全局换序。
guest 首字探针改为核对编码后物理 RAM 的 little-endian 数值，首尾 RAM 回读仍需相等。

实际 QEMU 微测试 `probe_np560_usb_store_lanes.py`：

- 使用 loader 的原始 `1B81` 指令，依次写入全部 256 种字节值两遍；R0 高字节故意
  设成 `byte ^ 0xA5`，检查不会误用 RB0。
- 在 `0x526000` 与 `0x528000` 两个 32 KiB 银行分别写 512 字节；物理回读与
  新编码各为 **0/512 字节差异**，与未经编码的 wire bytes 各有 512 字节差异。
- 记录在 `tmp/np560-usb-store-lanes-v2/manifest.json` 和两份 physical 二进制。
  QEMU hash 与上面的菜单验证相同；未加载或修改两个用户实例的 NAND。
- 初版微测试误把 RB1 当成高字节，得到 510 个差异并失败。修正的是测试输入，
  不是 CPU 实现或预期换序规则；该失败不能当作硬件异常。

这证明当前 CPU/RAM 实现与新的调试传输编码一致，**不是实机测量，也不是完整 USB
控制器验收**：FIFO、枚举、原厂 burner 到 NAND 的完整写入/读取尚未在此修改后实测。
`test_np560_usb_transport.py` 覆盖原指令校验、所有字节值、奇数尾包/跨页/最大包、
命令数值字段不变、非法长度和 staging 首尾损坏拒绝。Windows 与 WSL 均运行测试。
下一步必须用隔离输出完成原厂烧录、FTL 回读及全资源核对，再淘汰局部修补 NAND；
不能因 RAM 微测试通过就发布新的 canonical NAND。

本次回读用户实例只用了 GET。8807 的较旧服务不提供 `/api/health`（404 不代表
进程退出）；`/api/state` 仍返回 running，LCD 为 `DISPLAY=off SLEEP=on`。
新截图 `tmp/np560-corruption-followup-8807.png` 因此为黑屏，不能替代之前保存的花屏
证据。8808 的 health 仍指向上文同一 run_id，当前只读截图为清晰的学习菜单：
`tmp/np560-corruption-followup-8808.png`。没有按键、唤醒、重启或替换用户镜像。

## 初始现场

## 证据与边界

目录：`tmp/np560-user-corrupt-menu-8807/`。

- `full.json` / `full.gray5`：完整诊断与原生 240×120 gray5 帧。
- `buffers-lcd.png`、`buffers-front.png`、`buffers-back.png`：最终 LCD 和原始绘图
  缓冲。缓冲的存储 Y 方向与 LCD 相反，不能把这个存储差异再算成一次显示故障。
  顶栏破碎字形在原始 front buffer 中已经存在，不是浏览器缩放造成。
- `NATIVE_REFRESH`：本次保存状态的 back→front 复制 `MISMATCHES:0`，
  `COPY_BACK` / `AFTER_FRONT` 均为 `6487/e0b252f3`。这是最近一次刷新记录，
  不是所有历史刷新或原子同步抓取的证明。
- `ROM_MISSING=none`、`INVALID_CONTROL=none`、`UNSUPPORTED=none`：只说明这些
  已有故障探针没有报错，不能作为显示正确的验收依据。

## 已收窄的异常

`ROOT_RESOURCE_TRACE` 保留如下分类顶栏调用：

| 分类 | caller | 资源指针 | 宽高 / 句柄 / 阶段 |
| --- | --- | --- | --- |
| 学习 | `1D:F3F6` | `0247:15A1` | `00F0,0016 / 0002 / 4FF` |
| 辞典 | `1D:F42C` | `0247:0B47` | `00F0,0016 / 0002 / 4FF` |
| 网络 | `1D:F462` | `0247:1FFB` | `00F0,0016 / 0002 / 4FF` |
| 记事 | `1D:F498` | `0247:2A55` | `1600,FF00 / 0000 / 503` |
| 系统 | `1D:F4CE` | `0247:34AF` | `1600,FF00 / 0000 / 503` |

分类索引与 caller 由 PRG offset `0x1AF3DA` 的六项跳表对应：
`F4F4,F3E6,F41C,F452,F488,F4BE`。索引 1..5 分别对应五个顶栏分类。
正常尺寸为 240×22；末两项在资源头阶段已经异常，并未正常走完对象装载。
尚未证明具体坏字节首次出现于 checkpoint、FTL/NAND 传输、资源读取还是解析。
“网络”的尺寸有效也不代表 payload 正确；它与末两项失败是否同因仍待验证。

`root-top-source.bin` 与 `root-top-object.bin` 均为 2,650 字节。
按照观察器定义，source 是逻辑字节序、object 是物理字节序；对 object 成对交换后，
与 source 的差异为 **0 字节**，两者渲染的首次“学习”顶栏完整。
重要限制：`helper.c` 的该观察器只在 `slot == 0` 的首次资源装载完成时冻结。
因此这排除的是本次启动首次装载的拷贝损坏，不能用于证明后续切换的对象正确。

旧 `analyze_np560_toolbar_pipeline.py --nand` 把逻辑扇区 `FB789..FB78E` 和物理块
`0x490` 写死；本次冻结的首次资源 I/O 是 `FB68A..FB68F`、map slot `0890`。
故其自动提取的 NAND 图片/差异分数不能作为当前分类的源数据对照，未用于根因结论。
对当前 LCD 和首次“学习”对象直接做整栏像素比较同样会混入选中分类变化。

## 下一步与验收

1. 在隔离实例按每个分类分别抓取解析前的真实资源头/主体、装载完成对象、back/front
   与 LCD；替换“只冻结第一张”的诊断盲区，按实际 FTL 映射读取同一资源。
2. 找到第一次字节差异及调用参数。宽高已异常时优先追踪资源读取，不直接补 ROM、
   新指令或给分配器伪造成功返回；不修改用户的当前 NAND 来试错。
3. 五个分类各自通过未选中/选中态，再通过单次、往返和连续切换的像素与状态回归。
   CPU 无 fault、菜单索引变化、NPE 可运行均不能替代此项。

另行记录用户报告的音乐播放器无法播放，尚未取得其文件/解码/设备链诊断，不能因
本项资源异常就断言两个问题同源。
