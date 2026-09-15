# MP3：以公开算法实现 DMCU 端解码

日期：2026-09-07。**已有原生侧信息、位储备、scalefactor、连续帧驱动、Q28 重定标、
MS/IS/组合立体声、短块重排、抗混叠、IMDCT/窗口/重叠、频率反转和 32 子带合成。
三组真实 MP3 输入已在连续 guest 中解码到 PCM16，并与独立解码器比较；
原厂播放器接口和实时性能未完成，不能在系统播放器中播放 MP3，NPE 声音也未恢复。**

## 1. 路线与实现边界

MP3 标准算法与原厂 ROM 私有接口是两类问题。缺少原厂函数体不再作为停止 MP3
算法实现的理由；采用可核对的公开实现，在 guest 中执行重建代码，随后适配原厂接口。
此代码不是原厂字节转储，不宣称与原厂逐周期或逐样本完全相同。

选择 libmad 的定点实现作为算法参考，而不是将其作为宿主播放器。其源码、commit、
许可证与 SHA 见 [来源说明](sources/libmad-20260907/SOURCE.md)。构建 Huffman 树复用
已保存的 FFmpeg MPEG 公共表，其 SHA 固定校验，不从随机网页手录码表。

## 2. 位读取与 Huffman 核心

`scripts/build_np560_mp3_huffman.py` 生成普通 DMCU 指令和码表：

- `read_bits`：按 MSB-first 读取 0–16 位，维护缓存、剩余位数和跨 32 KiB 银行的字指针。
- `huffman`：Layer III pair codebooks 0–31（4/14 是无效编号）及两张 count1 表。
- 支持每个值自己的 linbits 和 sign，次序为 x 扩展/符号后再 y 扩展/符号。
- 返回有符号量化整数；不足一整个符号时恢复进入前的全部游标状态，供上层补数据重试。
- 无全局解码状态、宿主函数回调、QEMU PC 特判、NAND 或前端播放替代。

当前诊断链接位置为 code `20:1000`、tables `20:4000`，**不是任何原厂服务入口的替换**。
代码 690 bytes，SHA256 `6ee551ee703dbbef87882def3ae66a8b70495264a92595b388fdb83fad7f5036`；
码表 5708 bytes，SHA256 `d4045cdfb9279b2fc8ff1d8ae72abe517230cc247ed864ab7d4a230f5a8e662f`。
这是以单 bit 遍历为主的第一版正确性实现，性能尚未优化或证明满足整机实时播放。

内部 ABI 由重建核心定义，不冒充已知的原厂字段布局：

- R12 保存 near context 指针值；通过普通地址寄存器访问它，不用 Y0 作外部地址。
- context 为五个 word：DS 银行、下一个 word 的 banked 指针、左对齐缓存、缓存位数、
  可用总位数。输入以 network/MSB-first word 表示，上层必须显式适配原厂环的字节通道。
- `read_bits`：R0 请求位数，返回 R0 值、R2 状态；其它通用寄存器和 DS 恢复。
- `huffman`：R0 表号，返回 R0/R1/R3/R4 四值和 R2 状态；pair 后两值为零。
  R5..R14 与 DS 恢复。状态 0=成功，1=输入不足，2=非法请求，仅为新核心内部约定。
- context 和数据区须由上层合法分配，不能与活动栈/输出冲突；目前没有实现原厂内存分配
  或解码器私有状态绑定。16-bit 位数容量供每个有界解码片段使用，不是整首歌长度。

## 3. 位读取/Huffman 验证及失败记录

`scripts/tests/test_np560_mp3_huffman.py` 先独立展开 libmad 的多位查表，与 FFmpeg 长度/符号
表示逐项比较：32 张有效表、4995 个含共享码表重复项的码字全部一致，linbits 也一致。
这比用同一树生成器同时充当唯一 oracle 更独立，但仍不是整帧 PCM 对照。

随后 guest 自己读入诊断数据、调用新核心，并比较所有输出整数和五个游标字段。
宿主不写运行中的 guest 内存；读取的是结果，不用 QMP 代执行解码。

`tmp/np560-mp3-huffman-20260907-full-v1/report.json`：

- 37 个自有短时 QEMU，6626 个合成熵符号/错误向量，全部通过、全部退出 0。
- 每张表的全部码字、边界正负号、最大 escape，以及完整最长符号各截断点。
- 表 4/14/34/65535 拒绝并保持输入状态；表 0 可在零可用位时输出零对。
- 表 1/23/32/33 在 icount=5 下另测 `DS=A0,pointer=FFFE` 跨到下一 32 KiB 银行。
- context 两侧哨兵、FP、SP 与已声明保留寄存器检查通过。

`tmp/np560-mp3-bitreader-20260907-v1/report.json` 另外直接测试 `read_bits`：

- 普通执行与 icount=5 各 54 个向量，合计 108 个，两个自有 QEMU 全部通过并退出 0。
- 覆盖请求宽度 0–16、输入不足、非法宽度 17/32/65535，以及被调用者应保留的寄存器。
- 与完整 Huffman 集合使用同一核心 SHA；构建命令生成的 `code.bin` 也已核对一致。

QEMU 未修改，SHA256 `d26b7ce7f17c8345a2a2604a1c18c7c960549640ae0ebebb8458f8ea5e577372`。

保留的首轮失败：first-v1 在 Python 3.8 导入整个旧 ROM builder 时遇到 `zip(strict=)`；
将已有 50 行左右的标签解析器机械提取为 `scripts/np560_assembler.py`，没有建设新编译器。
其 AST 与 Git 暂存版本中的原类完全相同，两个既有 ROM builder 定向测试通过。
first-v2 使用了错误的 Y 指针空间，first-v3/v4 暴露新生成代码中 MOVSE/MOV 及
字节/字算术编码误用；均修正生成器/测试，**没有修改 CPU 去接受错误预期**。
first-v5 单向量通过后才执行上述完整集合。

## 4. 新增侧信息与跨帧位储备

本阶段新增的都是普通 DMCU 指令，未修改 QEMU CPU 或挂接任何原厂入口。

| 组件 | 诊断链接地址 | 字节数 | SHA256 |
| --- | --- | --- | --- |
| `build_np560_mp3_sideinfo.py` | `20:2000` | 898 | `c7492d8bf94d9ee6d91360cd4c332a8f9675b576e474f5aaf90adae41449e5e5` |
| `build_np560_mp3_reservoir.py` | `20:2800` | 710 | `a0e745a9b83dde3289802310317beedf984c35e0df7b07f0e5a85b1fe7305d4c` |

### 4.1 侧信息解析

按 MPEG1 与 MPEG2/2.5 LSF、单/双声道、长块/切换块解析，输出紧凑的 72-word
内部结构：8-word 帧字段，再按 `gr*nch+ch` 顺序放最多四个 16-word 通道字段；
未使用通道和字段清零。字段顺序见生成器 `HEADER`/`CHANNEL`，并非原厂内存布局。

- 输入 R0=LSF(0/1)、R1=声道数(1/2)、R3=near 输出、R12=位读取 context。
- 返回 R0=消费位数、R2=状态；其它通用寄存器、DS 恢复，算术标志未承诺保留。
- 预先检查完整侧信息长度：MPEG1 单/双声道 136/256 bit，LSF 72/136 bit。
  短输入返回 1，非法参数或缓存位数返回 2，均不改变输入和输出。
- `big_values>288`、切换块 `block_type=0`、MPEG1 短块与非零 SCFSI 冲突，
  分别返回 3/4/5，保留首个错误；仍解析完整侧信息，但错误帧字段不可交给频谱解码。
- 切换块 `region1=36` 是沿用 libmad 的后续频带截断哨兵，不是直接访问第 36 个频带。

`test_np560_mp3_sideinfo.py` 将固定 SHA 的 libmad `III_sideinfo` 函数、结构与 flags
机械摘取到测试目录，在宿主离线编译执行，逐字段对照 native 输出。
没有在宿主重写另一份同源 Python 解析器充当唯一判定依据，也不把该 C 程序链接到 QEMU。
额外保存的 `window_switching` 原始位由输入向量核对；libmad 结构本身不保留该位。

`tmp/np560-mp3-sideinfo-20260907-full-v2/report.json`：13 个隔离进程、413 个向量
全部通过且退出 0，包含全部版本/声道组合、错误字段、输入截断、非字边界缓存、
跨 32 KiB 银行，以及既有 MP3 的 116 个真实帧。前一版 `full-v1` 在合法 288 边界
失败：生成器把有符号 `<` 条件当作 `<=`，已改为无符号 `<=`；CPU 模型没有修改。

### 4.2 位储备组装

此组件将“最近最多 511 字节原始 main_data 历史的末尾 `main_data_begin` 字节”与
本帧 payload 拼接，建立供后续频谱解码使用的位 context。历史更新保留全部原始
main_data 的尾部，不能只保留当前回指前缀：下一帧可能需要更大的回指范围。
MPEG2/2.5 侧信息的 8-bit 回指自然限制到 255；通用组件上限保留 MPEG1 的 511。

R12=输入位 context，R3=8-word 内部描述符：

```text
history_buffer, history_bytes, main_data_begin, payload_bytes,
output_buffer, output_capacity_bytes, output_bit_context, part2_3_bits
```

- history 分配 512 bytes（最多 511 有效）；output 按容量向上补齐到 word。
  两者按 MSB-first word 存放，不是每字节占一个 word。全部 near 对象须由调用者在
  DS0=0 可达区域合法分配，不得相互或与活动栈重叠；尚未接原厂分配器。
- 返回 R0=组装字节数、R2=状态，其它通用寄存器和 DS 恢复。
- 状态 1=短输入、2=参数/容量非法：不改动历史、输出或输入游标。
- 状态 3=历史不足、4=声明的 part2_3 位数超过组装范围：本帧 payload 仍入历史，
  支持后续恢复，但返回 0 字节，输出 context 的可用位数为 0。状态 3 的缺失前缀
  只在不可解码的 scratch 中清零，绝不作为成功数据提交。
- 成功时可用位数限定为声明的 part2_3 总位数；每个 granule/channel 的进一步预算
  与 scalefactor 消费检查见 4.4，持续帧驱动尚未接入。seek/reset/断流必须清历史长度。
- 已检查局部输入量/容量，不等于所有 MP3 帧有效性均已验证；CRC、前后帧 main_data
  使用范围冲突、原厂错误码映射和复位调用还没有接入。

`test_np560_mp3_reservoir.py` 的真实帧路径实际调用 native 侧信息函数，并读取其
`main_data_begin/data_bitlen` 写入新描述符后调用 native 位储备，不用宿主预期值代替
前级执行结果。guest 自行比较历史、完整输出缓冲、输入/输出 context、描述符和哨兵；
宿主只读取首个不匹配记录。期望历史由输入原始字节的拼接/取尾独立构造。

| 报告目录（均在 `tmp/`） | 隔离 QEMU 数 | 实际 MP3 帧数 | 比较结果 |
| --- | --- | --- | --- |
| `np560-mp3-reservoir-20260907-full-v1` | 24 | MPEG1：116 | 全部通过，退出 0 |
| `np560-mp3-reservoir-20260907-mpeg2-v1` | 7 | MPEG2 立体声：13 | 全部通过，退出 0 |
| `np560-mp3-reservoir-20260907-mpeg25-v1` | 6 | MPEG2.5 单声道：7 | 全部通过，退出 0 |

各集合还包含小 payload、多帧累计、511 边界、超过历史容量的 payload、零长度、
奇数字节拼接、历史不足后恢复、非法容量/缓存、断流清历史及 icount=5 检查。
为缩短单个自有进程运行时间，真实帧分组执行；组间用同一个 native 位储备 API
先吞入准确的历史原字节。它验证解码组件状态，不宣称已连续运行整首歌或原厂播放器。

实际样本身份：

- 既有 `np560-mp3-player-20260906-v1/input/tone440.mp3`：48483 bytes，
  SHA256 `705a990bae6af03a44125a0252070f4a12c1c6e09d4fd2a9ab91dc378d66373a`。
- 新建 `np560-mp3-frame-fixtures-20260907-v1/mpeg2-stereo.mp3`：2108 bytes，
  SHA256 `275b94d4e4ac8ca8c5d8c69387d30700e67a202b831662547588eadf483561b3`。
- 同目录 `mpeg25-mono.mp3`：693 bytes，
  SHA256 `d43609ca9b27628d59b5f80d49c2dcc9e1642a4fa4a395d4758a770d1f0495a0`。

两个新文件只是从已有测试音取 0.25 秒，经本机 ffmpeg/libmp3lame 编码的离线样本：
分别 22050 Hz/双声道/48 kbps 和 8000 Hz/单声道/8 kbps。没有装入 NAND，没有播放，
也没有把宿主生成的声音接回 guest 冒充解码输出。使用 `-n` 防止覆盖既有文件。

### 4.3 原生 scalefactor

`build_np560_mp3_scalefactors.py`：code `20:6800`，1126 bytes，
SHA256 `2f8e0f1ce1413aa3ed2f18db6d3157bb2571a7105c816e4d08e046bbf95a4d08`；
tables `20:5800`，3304 bytes，
SHA256 `8b5fd5b5edeeda1a3410fda444260debcbc1cafca24a6beea67f2523dbd3374c`。

- 覆盖 MPEG1 长块/短块/混合块、16 种 SCFSI 复用组合，LSF 512 个压缩编号，
  普通和强度立体声右声道分支、派生 preflag 与非法 intensity position 标志。
- R3 指向内部七 word 描述符：`lsf, channel, scfsi, previous_sf, output_sf,
  intensity_right, output_illegal_positions`。R12 仍是位 context。
- 输出 SF 与 intensity 标志各 39 word；允许 previous_sf 等于 output_sf，供 MPEG1
  第二 granule 原地复用。MPEG1 没使用的尾部统一清零，不保留无意义旧数据。
- 先算出完整 part2 所需位数，再检查本段 part2_3 和输入可用量；错误不改变输出、
  通道 flags 或输入 context。成功才更新 LSF preflag。R0 返回 part2 bit 数，
  R2 状态 0=成功、1=输入不足、2=参数非法、3=超过本段预算；其它 GPR/DS 恢复。
- 查表数据是编译期对公开 slen/nsfb 公式的展开，并非从原厂 ROM 取出的隐藏表。

`test_np560_mp3_scalefactors.py` 离线编译执行固定 SHA 的 libmad 原始两个 scalefactor
函数，逐项比较 39 个 SF、39 个 intensity 标志、preflag、游标、哨兵和保留寄存器。
`tmp/np560-mp3-scalefactors-20260907-full-v1/report.json`：63 个自有进程，3989 个
向量全部通过并退出 0，包括非法参数/短输入/预算错误、原地复用和跨银行读取。

首轮 `first-v1/v2` 的返回栈异常不是 MP3 算法或 CPU 错误：诊断链接到 `20:3000`
时撞上机器现有 `20:2DE0..3390` 前台 overlay，取到空入口，仅后半段代码被执行。
指令日志证明了这一点；将新组件移到未占用的 `20:6800` 后首轮及完整检查通过，
没有修改机器原有映射或 CPU 语义。该地址仍只是诊断链接地址，不是原厂服务入口。

### 4.4 每段 576 项量化频谱

`build_np560_mp3_spectrum.py`：code `20:A000`，784 bytes，
SHA256 `425fd448ef795ee61bc3b2b1ca51c628f585981785fbb067e31ed229bcd8b47e`；
long-region tables `20:7000`，432 bytes，
SHA256 `1e884dcdb8517aa681873150fa1e535ac1f263bd95d25f67f35db564f893524e`。

该函数实际调用 native scalefactor/Huffman 组件：按区域选 pair 码表，处理 linbits/sign、
count1 与 rzero，生成每个 channel/granule 的 **576 项有符号量化整数**。没有进行
重定标、短块重排、立体声混合或滤波合成，因此这些数据不是频域真实幅度，更不是 PCM。

- R3 为 `sf_descriptor, frequency_index, quantized_output, metrics`；R12 为位 context。
  frequency_index 顺序是 44100/48000/32000/22050/24000/16000/11025/12000/8000 Hz。
- 输出量化区 576 words，metrics 四 words 为 part2 bit 数、big_values 频点数、已编码
  频点数和 stuffing bit 数。成功 R0=已编码频点数，R2=0；其它 GPR/DS 恢复。
- 调用前把 context 可用位数限到当前 part2_3，结束时跳过本段 stuffing，再恢复剩余帧
  的可用位数，保留已缓存的下一段数据。不能把整个 main_data 余量交给一次 Huffman 解码。
- 状态 1=整段输入不足、2=频率编号/几何参数非法，不改变输出和 context。
  3=scalefactor 失败、4=非法码表、5=big_values 截断；这三种语义错误仍消费完声明的
  本段，但输出可能只有部分值，**必须按错误丢弃**，不能当成功帧继续合成。
- count1 尾部凑不齐完整码字/符号时，利用底层事务回滚把剩余位当 stuffing；
  big_values 截断则明确报错。表 0 的零位数 pair 也必须推进频点数，避免死循环。

区域边界单独采用 FFmpeg 的原函数核对：普通长块取累计频带界限，切换块根据采样率
和 block_type 取 36/54/72/108 频点边界。特别是 8 kHz 短块不能一律使用 36；
libmad 的 `sfb_8000_mixed` 本身标注存疑，不能据它声明后续短块重排/缩放正确。
依据见 [FFmpeg 8.0 区域初始化](https://ffmpeg.org/doxygen/8.0/mpegaudiodec__template_8c_source.html)，
本地固定源 SHA 见 [参考原件](sources/ffmpeg-mpeg-tables-20260907/README.md)。

独立对照的边界也明确记录：`test_np560_mp3_spectrum_reference.c` 在宿主离线执行
libmad 的原始 scalefactor 和 Huffman 位解码；把其 requantize 替换为恒等函数、
exponents 置零，仅用来暴露整数。区域通过 FFmpeg 原函数计算，再拆成小于 192 的
等指数频带交给参考 Huffman 遍历，不复用 libmad 存疑的 8 kHz mixed 布局。
这不是完整 libmad PCM 对照，也没有把这个参考程序接入 QEMU。

参考函数只插入 coded-lines/cache 统计；发现末尾放弃 count1 查表时 cache 余量可能为负，
不能当作真实 stuffing。最终用独立解出的整数重新编码、逐 bit 验证原始输入，再计算
stuffing；这修正的是对照程序统计，不是为了通过而改变 native 解码结果。
原 libmad 的 signedness 警告保留在 `reference-compiler.log`，只对该警告取消 `-Werror`。

| 报告目录（均在 `tmp/`） | 自有 QEMU 数 | 唯一真实 channel/granule 段 | 结果 |
| --- | --- | --- | --- |
| `np560-mp3-spectrum-20260907-mpeg1-v1` | 65 | 464 | 全部通过、退出 0 |
| `np560-mp3-spectrum-20260907-mpeg2-v1` | 10 | 26 | 全部通过、退出 0 |
| `np560-mp3-spectrum-20260907-mpeg25-v1` | 8 | 7 | 全部通过、退出 0 |
| `np560-mp3-spectrum-20260907-errors-v1` | 2 | 人工错误/边界用例 | 全部通过、退出 0 |

前三组各包含 45 个有预定整数输出的九采样率/块模式向量及一次 icount=5 重测；
报告里的 real_granules 包含重测，不能直接当作唯一输入数量。比较完整 576 个整数、
SF、intensity 标志、flags、输入游标、段统计及哨兵。错误集合覆盖表 4/32、截断 pair、
SF 预算失败、非法频率、整段不足、只有 stuffing、零 bit 编码 288 对零值。

上述分段测试按已有主数据重建和离线前 granule SF 建立夹具，在 guest 中执行
scalefactor→Huffman，不能据此宣称连续帧已接通。随后新增 4.5 的独立连续驱动；
它仍未安装到原厂播放器。

### 4.5 持续的原生熵解码帧驱动

`scripts/build_np560_mp3_frame.py` 生成 `20:A400` 的 950 bytes DMCU 代码，
SHA256 `d7d88dd9fd900515c26929113bcefac4c3939dc685f07746b9c7afaa67ef8dd0`。
这个地址是未占用的诊断 NOR 链接区，**不是原厂 ROM 入口**；QEMU 核心未改变。

调用者提供已验证 MPEG 头的几何参数和位于 sideinfo 开头的原始输入 context。
驱动自行调用 sideinfo/reservoir/spectrum，读取真实 `main_data_begin` 和各段预算，
维持跨帧历史，并在 MPEG1 第二个 granule 使用本帧同声道第一个 granule 的 SF。
左右声道、各 granule 结果分开保留；LSF intensity 只传给启用该模式的右声道，
退出该模式后 SF 非法位置标记由原生代码重新写入，不沿用旧值。

内部 ABI：R3=近地址状态区，R12=原始位 context；成功 R0=有效段数、R2=0，
其它 GPR 和 DS 恢复。状态区 8080 bytes，首五 words 为 lsf/nch/frequency_index/
intensity_enabled/payload_bytes。`reset` 保留这五项并清空余下状态；seek、复位或
流不连续时调用。容量覆盖非 free-format 普通帧，payload 最大 1537 bytes。

| 相对状态区的 byte offset | 内容 |
| --- | --- |
| `000A/000C/000E/0010` | 历史字节数、有效段数、错误阶段、子组件错误码 |
| `0020` | 72-word 原生侧信息，LSF preflag 在实际解码后更新 |
| `00B0/00C0/00D0/00E0` | reservoir 描述、主数据位 context、SF 描述、频谱描述 |
| `0100/0300` | 512-byte 历史区、2048-byte 主数据拼接区 |
| `0B00` 起，每段 `0524` bytes | quant[576]、SF[39]、illegal-is[39]、metrics[4]；最多四段 |

短输入=1、无效参数/context=2：预检不消费原始输入，也不改状态区。语义错误
3=侧信息、4=位储备、5=频谱：消费整个原始帧并保留其原始 payload 历史，但
有效段数置 0，主数据 context 作废，**整帧输出必须拒绝**。没有用零频谱掩盖坏帧。
调用者须检查返回状态，不能在预检失败后使用上一帧留存的有效段标记。

`scripts/tests/test_np560_mp3_frame.py` 的 NOR 夹具只向解码函数提供原始 sideinfo/payload
和头参数；参考结果位于另一区域，仅由 guest 检查函数读取比较。每个完整文件
使用一个持续运行的自有 QEMU，不在帧间重启，不引导注入历史，不写入前 granule SF。
与 4.4 同一个独立离线熵解码参考比较量化整数、SF/IS、flags、游标、历史及哨兵。

已通过（目录均在 `tmp/`，所有进程退出 0）：

- `np560-mp3-frame-mpeg1-20260907-v4`：完整 116 帧、464 段，一个 QEMU 内连续通过；
  全部 393055 个比较 word 一致，含两声道的第二 granule SF 复用。
- `np560-mp3-frame-mpeg2-20260907-v1`：完整 13 帧、26 段。
- `np560-mp3-frame-mpeg25-20260907-v1`：完整 7 帧、7 段。
- `np560-mp3-frame-recovery-20260907-v1` 及 `...recovery-icount-20260907-v1`：
  各 24 次调用，覆盖短输入、错误采样率族、错误缓存位数、过大 payload、侧信息
  big_values=289、保留 Huffman 表 4、丢失历史后自然恢复及 reset 后重放。
- `np560-mp3-frame-modes-20260907-v1`：6 个合成帧，覆盖单/双声道、MPEG1/LSF
  和 intensity 模式切换。零位数段仍生成可观察的右声道 illegal-is 标记，非假 PCM。
- `np560-mp3-frame-recovery-icount-20260907-v2`：迁移夹具后，同一 24 调用恢复集
  在 icount=5 下仍通过。`np560-mp3-spectrum-runner-regression-20260907-v1` 的
  两个已有错误路径运行也通过，确认默认 runner 调用没有回归。

保留失败记录：`...mpeg1-20260907-v1/v2` 到达测试时限，不计为通过。降低 67 KB
CPU 状态报告的轮询频率后，v3 在约 81 秒执行完毕，暴露出 145 个比较 word 差异。
首差为零基 frame 48 的 MAIN+0x30：native 值 C310，而测试读取的参考值变为零；
该参考 word 恰位于 `26:527C`，被现有 `NP560_APPLICATION_PAGE_ARGUMENT_TEXT_DATA`
别名重定向到 `43:527C`。后者在该诊断固件中是零，**比较夹具并未按平坦 NOR 被读到**。

因此把整个夹具移到 `3C:8000` 起：避开字体数据窗口终点 `3C:38CF`，并断言末端
严格不越过 `49:DC00` 对象工作区。v4 的 843 KB 左右夹具全部位于这个区间内。
同一 SHA 的 950-byte 帧代码随即完整通过，没有关闭既有别名、改动机器或调整算法。
通用 test runner 保持原 10 秒/0.01 秒默认值，仅连续帧调用采用独立 deadline 和
0.25 秒轮询；失败时也保存 guest 首差记录，避免只留下未到结束 PC 的错误。
运行耗时包含逐 word 对照和诊断开销，不是整机 MP3 实时吞吐测试。
本阶段没有生成 NAND、更新原厂 ROM、重启用户 Web 或安装播放器入口。

### 4.6 原生 Q28 重定标与真实帧集成

`scripts/build_np560_mp3_requantize.py` 实现 scalar 和 576 项整段重定标，都是
普通 DMCU 指令，使用已有 CPU 的乘法、加法、进位及移位指令，未增加宿主 codec
helper。最终 core 为 code `20:A800`、1004 bytes，
SHA256 `53d0fbbf17db8b259106b86ba1c0276164ccce7af66289d431ac2212bd864dd6`；
tables `21:0000`、38406 bytes，
SHA256 `e72ca8abbeb655c25b5500687511de056d0ac6c4386b9d7f8ff1d10c46a87729`。

表来自同一固定 libmad commit 的 `rq_table.dat`，不是 NP560 原厂 ROM：8207 项
27-bit mantissa / 5-bit exponent 打包为每项 32 bits；索引 8192 起跨越下一个数据
银行。七项分数次幂放在 `21:8080`，频带布局放在 `21:8100`。新原件 SHA 和 GPL
声明见 [来源记录](sources/libmad-20260907/SOURCE.md)。

- scalar 接收 R0=有符号量化整数、R1=有符号四分之一次幂指数，返回 R1:R0 的
  有符号 Q28 值和 R2 状态。R3..R14、DS、SOCR 保存恢复；它不是 PCM 输出函数。
- 四次 unsigned 16×16 乘法拼成完整 64-bit 乘积，再取 Q28 有效部分。暂时只清除
  SOCR 的全局乘法饱和位 MAS，避免中间乘积被截断，返回恢复；不修改其它控制位。
- 正负号、七种分数指数、移位舍入、下溢为零、跨表银行读取均已验证。最终溢出
  状态 3 输出零并明确报错，零值不作为成功的替代频谱；非法量化值状态 2。
- 改善了 libmad 的窄中间量边界：左移五位后的无符号值可能超出 signed32，但
  乘负分数次幂后仍可表示，不能在乘法前就截断/判错。现在保留该中间量，最终
  判断范围，并允许精确的 −8（INT32_MIN）；+8 不在 signed Q28 范围内。
- spectrum 的 R3 指向六个近地址 words：channel16、SF39、frequency_index、
  quantized576、Q28 输出576、band_exponents39。成功 R0=576/R2=0，其它 GPR
  与 DS/SOCR 恢复。先检查字段及全部输入值，无效输入不改输出；运算溢出时可能
  已有部分结果，必须由上层按失败处理，不能用于合成。

按公开公式计算每个长/短频带的 gain、SF、pretab 和各窗口 subblock_gain 指数。
频带几何单独对照 FFmpeg 的 `compute_band_indexes` 和 `exponents_from_scale_factors`
原函数：MPEG1 mixed 的 8 个长频带、LSF mixed 的 6 个长频带，以及三个短窗。
8 kHz mixed 在该布局下保留最初 72 个长块频点，不采用 libmad 源码明确标为存疑的
36 频点切换。FFmpeg 自身仍要求收集 8 kHz mixed 样本，因此这里只证明实现与其
规则/合成向量一致，不宣称已取得该模式的原厂实际播放证据。

独立对照使用 `test_np560_mp3_requantize_reference.c`：保留 libmad 表达式/常量，
显式把中间量和返回值加宽为 int64，推迟范围判断，再由 wrapper 检查最终 signed32。
该改动及 overflow 观察在提取脚本中明示，不称作未经修改的 libmad 全边界位一致。
FFmpeg 的两段频带函数不改算法，原来的 +400 偏置在对照结果中减回。
另用 double 直接计算公开 `sign(q)*abs(q)^(4/3)*2^(exp/4)` 公式交叉检查，避免
guest 与 C 参考共享“过早溢出”的错误。该检查最多容许 32 个 Q28 LSB，当前最大
19.943；这是频谱常量舍入检查，不是最终 PCM 音质或标准符合性证明。

最终同一 core SHA 已通过（均在 `tmp/`，所有自有进程退出 0）：

| 报告 | 具体覆盖 |
| --- | --- |
| `np560-mp3-requant-scalars-20260907-v2` | 8751 唯一输入，含全部 8207 个表索引及 544 个边界组合；另 1024 个 icount=5 重测；SOCR=2/26 保存恢复 |
| `np560-mp3-requant-vectors-20260907-v2` | 180 个频带/flags 配置、7 个预检错误、2 个部分输出溢出；另 4 个 icount=5 重测，共 193 次整段调用 |
| `np560-mp3-requant-chain-mpeg1-20260907-v2` | 原测试 MP3 前 8 个连续帧、32 段，未检查该新阶段的剩余 108 帧 |
| `np560-mp3-requant-chain-mpeg2-20260907-v2` | 完整 13 帧、26 段 |
| `np560-mp3-requant-chain-mpeg25-20260907-v2` | 完整 7 帧、7 段 |

后三组由同一个 guest 依次执行原生帧驱动和新 spectrum 函数，用实际侧信息/SF/
量化整数作为后续输入；宿主参考结果只供只读比较，没有向解码器补写这些中间状态。
频谱、band_exponents 和返回状态逐 word 比较。Q28 检查输出另有分配，不与 frame
工作区或比较记录重叠。裸 frame 函数仍只负责熵解码，诊断调用者负责串接新阶段；
原厂播放器入口依然未替换。

首个 `first-v1` 只在 C 参考编译阶段碰到旧源 signedness 警告，未运行 QEMU；保留
该警告并只撤销其 `-Werror` 后，`first-v2` 通过初版算术。后续 `first-v3` 和上表 v2
使用扩大量程后的最终实现；旧 v1 报告不作为当前 core 的证据。

本节重定标函数的输出按 Huffman 频带/窗口顺序排列，是**编码声道的频谱**；
后续 MS/短块重排见 4.7，不能省略未完成的 IS、滤波和 PCM。Q28 是本函数的明确接口范围，
不是丢弃合法大幅度帧的最终策略；整机滤波链还须统一量程、缩放/溢出与 PCM 截幅规则。
不能据当前测试声称已经恢复全部 MP3、原厂低码率共用服务或任何 NPE 音频格式。

### 4.7 原生 MS 立体声与短块重排

`scripts/build_np560_mp3_stereo.py` 新增 code `20:AC00`，788 bytes，SHA256
`26f058ff3b130565386cca42f63a91ec88a976e265aeeec1121f1333e7f4870b`。
复用 4.6 的频带几何表；没有修改 QEMU 的 CPU、内存映射或增加宿主 codec helper。
这是重建实现的内部入口，不是原厂 ROM 字节：

- `ms_pair`：R1:R0=M、R4:R3=S，返回同一寄存器对中的 L/R；R2=0 成功，3 溢出。
  使用 libmad 的 Q28 `1/sqrt(2)=0x0B504F33`，计算 `(M+S)*k` 和 `(M−S)*k`。
  两路有符号乘积、求和/求差均保留 64 位，之后算术右移 28 位，最终检查 signed32。
  不在 32 位求和后乘常量；也不先逐路缩放取整再相加。溢出时两个输出对为零且明确
  返回失败，不能把这些零作为成功输出。R5..R14、DS、SOCR 保存恢复。
- `ms_spectrum`：R3 指向 `{M576, S576}` 两个近地址，原位转换 576 项，成功
  R0=576/R2=0。溢出返回 R0=0/R2=3，已有部分结果必须拒绝使用。它只实现 MS，
  调用者必须检查头模式/两侧块布局，不能将它无条件套在 IS 频带上。
- `reorder`：R3 指向 `{rate_index, block_type, mixed_0_or_1, input576, output576}`。
  长块直接复制，混合块先保留长块前缀，随后把各频带三个连续短窗交错为三元组。
  输入/输出必须分开分配；成功 R0=576/R2=0，非法几何 R0=0/R2=2 且输出不变。
  支持九种采样率；8 kHz mixed 的 72 项长块前缀沿用 4.6 的 FFmpeg 布局与证据边界。

MS 输入来自保留原始 global_gain 的重定标，因此在这里施加 `1/sqrt(2)`。
不能照搬已经预减 global_gain 的其它实现，再重复或漏掉这次缩放。后两入口保留
R1、R3..R14 和 DS/SOCR。近地址、对齐、分配和不重叠由调用者负责；尚非原厂 ABI。

`test_np560_mp3_stereo_reference.c` 只在宿主离线运行：MS 用加宽的公开公式；
重排直接执行固定 FFmpeg n8.0 的 `compute_band_indexes` / `reorder_block` 原函数。
另用独立 double 公式核对 MS 缩放：Q28 常量误差对 signed33 求和最多引入约 4 LSB，
取整再加不足 1 LSB，因此上限为 5 Q28 LSB，实测最大 3.669。不是 PCM 音质指标。

已通过，报告均在 `tmp/`，自有进程全部退出 0：

| 报告 | 本阶段实际覆盖 |
| --- | --- |
| `np560-mp3-stereo-suite-20260907-v1` | 681 组 MS 样本对；45 个九采样率/块型重排、4 个几何错误、5 组整段 MS（含首/中/末项溢出）；另 icount=5 复测 128 对、2 组重排、2 组 MS；共 20 个隔离 QEMU |
| `np560-mp3-post-chain-mpeg1-20260907-v1` | 同一 guest 连续前 8 帧、32 段，实际 16 个 MS granule；64990 个 word 对照一致 |
| `np560-mp3-post-chain-mpeg2-20260907-v1` | 同一 guest 完整 13 帧、26 段，实际 12 个 MS granule；71607 个 word 一致，非 MS 帧不误施加转换 |
| `np560-mp3-post-chain-mpeg25-20260907-v1` | icount=5，同一 guest 完整 7 帧、7 段，单声道无 MS；29560 个 word 一致 |
| `np560-mp3-frame-modes-regression-20260907-v1` | 原有 6 帧熵解码模式切换仍通过，含 IS 非法位置标记；不是 IS 频谱处理已实现 |

`--postprocess` 自动包含 `--requant`。诊断调用者按实际 MP3 头提供 mode_extension，
guest 在原生熵解码/重定标之后，对匹配的双声道块执行 MS，再按 guest 侧信息重排。
重排 scratch 为 `0x4800..0x50FF`，不覆盖帧工作区、Q28 输出或指数；原始频谱由
guest 自行生成，参考结果仍只供逐 word 比较，没有宿主中间状态注入。
裸 frame 入口仍是熵解码驱动；原厂头解析、输入环和播放器接口未改装。

4.7 阶段当时**不支持 IS 或 MS+IS**（后续实现见 4.8）：测试入口遇到含 IS 的文件立即拒绝，guest 串接也检查
mode_extension，不能静默当作普通 MS。已有 LSF SF/illegal-is 标记不代表 IS 已完成。
下一步需统一长/短/混合块右声道非零上界、LSF 非法位置和最高频带 SF 的继承/默认值。
已检查的 libmad、FFmpeg 与 [minimp3 源码](https://github.com/lieff/minimp3/blob/master/minimp3.h)
对此存在实现差异；minimp3 仅作在线交叉阅读，未纳入本阶段生成器或离线 oracle。
不要把尚未核实的末带处理硬编码成“原厂行为”，也不以合成向量通过代替完整 PCM 验证。

保留 `np560-mp3-stereo-smoke-20260907-v1`：它在浮点交叉检查阶段发现初设 2 LSB
容差不足，尚未运行 QEMU；按常量误差传播推导修为 5 LSB 后，v2 及完整集通过。
DMCU 算术没有为该容差检查改写。该阶段仍缺 IS、抗混叠、IMDCT/重叠、合成滤波和 PCM；
最终动态范围策略也未闭合，不声明可播放或已兼容原厂声音。

### 4.8 原生 IS/组合立体声与公开码流集成

`scripts/build_np560_mp3_intensity.py` 实现新的 pair/joint 入口，复用已验证的 MS
样本对运算与频带几何。code `20:B000`，1236 bytes，SHA256
`95a98b59c390751bad2524256eea32417ce2f921bf3754cb05bd565f6ab15ce1`；
tables `21:9608`，552 bytes，SHA256
`2b349399b30fc1f1eaa1745f1209115bdf78959856b175d85002da3760a6a630`。
表与原有 requant 表留有间隙，生成器检查全部片段无重叠；没有修改 QEMU CPU。

表从固定 libmad 的 `is_table`、`is_lsf_table` 生成，共 69 组左右系数：MPEG1
7 组；LSF 两种 intensity_scale 各 31 组，包含 position 0 的双路单位系数。
pair 接收 R1:R0 的 Q28 输入、R3 的表索引，返回 R1:R0/R4:R3 两个声道；非法
索引状态 2。两个乘积均以有符号 64 位形成，右移后取 Q28；系数范围 [0,1]，
包含 INT32_MIN×1 的精确表示。GPR R5..R14、DS 与 SOCR 恢复，未继承 MAS 饱和。

joint 的 R3 指向十个 near word：

`{rate, mode_ext, channel0, channel1, sf_right, illegal_right, quant_right, left_q28, right_q28, work}`

成功 R0=576/R2=0；非法几何、异步 joint 块型、SF/mask/LSF 非法位置或压缩参数
返回 R0=0/R2=2，预检不改缓冲；MS 运算溢出返回状态 3，必须拒绝全部部分结果。
R1、R3..R14、DS/SOCR 保存恢复。work 为 44 words：四路非零上界、39 个频带
模式、系数族基址。模式 0=不转换，1=MS，2..70=IS 系数索引+2。
缓冲、描述符、SF/quant、work 和栈的对齐、分配与不重叠由调用者负责。

具体语义及依据：

- 长块使用最后非零频带；短块分别计算三个窗口上界，任意短窗非零都禁止 mixed
  长块部分使用 IS。上界扫描**原生量化右声道**，而非已舍入为 Q28 的值，防止下溢
  改变编码边界。8 kHz mixed 保留 72 个长块频点。
- MPEG1 位置 0..6 使用正切比系数，其它位置回退；LSF 使用原生 SF 解码器输出的
  每带 illegal mask，不用粗略的 `sf>=16` 代替。位置 31 必须有非法标记。
- 非 IS 频带按 mode_ext 回退为 MS 或独立声道；IS 频带不会再叠加 MS，也不重复
  乘 sqrt(2)。接口输入保持原始 global_gain 的 Q28 频谱。
- 长块最高带 21 继承带 20；短块最高带 12 继承同窗口的带 11，连同非法标记一起
  继承。原始 SF/mask 数组不改写，避免污染后续 SCFSI。

以上末带选择依据固定 FFmpeg `compute_stereo` 和核对过的 mpg123 `III_i_stereo`，
不是宣称找到了原厂规则。libmad 的原始零尾和 minimp3 的条件默认值不同，当前未
以最终 PCM/全部标准向量证明该末带选择在所有边界都正确；保留为符合性核验项。
补充阅读 Sieler/Sperschneider 的技术说明 4.3.11：文字明确非零边界、短窗独立与
非法位置回退。该 PDF 并非 ISO 正式原件，且此副本部分公式/图形缺失，因此不据它
猜测缺失公式或声称消除了所有歧义。来源、SHA 和缺页图情况见
[PDF 来源记录](sources/mpeg-layer3-syntax-20260907/SOURCE.md)。

离线 oracle 在 `test_np560_mp3_intensity_reference.c` 中执行提取的 libmad
`III_stereo`，明确作了四类适配：右边界扫描改用 quant；8 kHz mixed 的长前缀长度
由频带表计算；MS 中间量加宽；最高带 SF/mask 在私有 channel 副本中继承。另
导出原函数的频带 modes 用于比较。不是“未经修改 libmad 位一致”；源提取规则
在脚本中可核对，不链接到 QEMU。系数另以独立 double 公式检查，最多 5 Q28 LSB，
实测最大 4.198；该数值界限不是 PCM 音质/标准符合性阈值。

最终同一 code/table SHA 的证据，报告均在 `tmp/`，自有 QEMU 全部退出 0：

| 报告 | 具体覆盖 |
| --- | --- |
| `np560-mp3-is-suite-20260907-v1` | 485 对输入（全部 69 组系数×7 个值及两个非法索引）；104 个 joint 向量，含九采样率/长短混合块/IS与MS+IS/末带/非法标记/下溢边界/非法输入；另 icount=5 复测 128 对与 2 个 joint，共 55 个隔离 QEMU |
| `np560-mp3-is-errors-20260907-v1` | 11 个预检错误和首个 MS 样本对溢出；再以 icount=5 重测最后两个；7 个 QEMU，验证状态 3 向上返回而不是伪成功 |
| `np560-mp3-is-chain-mpeg1-20260907-v1` | `l3-he_mode.bit` 第 0–69 帧，单一 guest 连续 70 帧/260 个熵段；前 50 帧建立状态，随后 20 帧共 80 声道段接到 Q28/joint/重排；40 个 IS-enabled granule，其中 20 个为 MS+IS；337212 个 word 对照一致 |
| `np560-mp3-joint-ms-regression-20260907-v1` | 原 MPEG2 文件完整 13 帧、26 段、新 joint 入口实际处理 12 个 MS granule；72075 个 word 对照一致 |

公开文件来自固定 minimp3 提交，文件本身共 128 帧；头字段实际包含 IS 和组合模式。
来源记录在 [测试码流来源](sources/minimp3-vectors-20260907/SOURCE.md)。当前并未运行
它的全部 PCM 标准对照，不借用上游的符合性成绩来声称本机解码器已经符合标准。
另取得的 `M2L3_compl24.bit` 实际全为单声道，不能作为 LSF-IS 证据；没有伪称其为 IS。

`--post-start 50 --limit 70` 表示保留从开头起的全部原生熵解码，仅从第 50 帧启用
Q28/joint/重排比较。这使逐 word 夹具保持在已核实的 NOR 区间内（710464 bytes），
没有裁掉前缀或注入位储备/SF。后续真实调用读取原生右 quant、SF、mask 和 channel；
39 个频带判定及输出均逐 word 比较。该 warmup 只适用于当前无跨帧滤波状态的阶段，
**未来 IMDCT overlap/合成测试必须也从开头执行状态更新，不能沿用“只熵解码 warmup”
去声称完整解码连续正确。** 原厂播放器/输入环 ABI 仍未连接。

保留 smoke-v1：提取器误命中表名前的注释，把不需要的 rq_table 包含进参考代码，
在编译阶段失败，未运行 QEMU。改为精确匹配声明后 smoke-v2 通过；DMCU core 未改。
LSF-IS 的新阶段已有系数/合成边界证据，但尚缺发布的真实 LSF-IS 文件整链检查。
本阶段当时尚缺抗混叠（后续实现见 4.9）、IMDCT/窗口/重叠、频率反转和合成滤波；PCM 的后续证据见 4.11。

### 4.9 原生抗混叠：频谱链进入混合滤波阶段

`scripts/build_np560_mp3_antialias.py` 新增 guest 内的频域蝶形运算，位于短块重排之后。
代码 `20:B500`，684 bytes，SHA256
`bb3af13cf650044d67119124180072c103300fbb26ca47ed26c17a1162eef2a9`；
系数 `21:9830`，64 bytes，SHA256
`ab258e778b7210390a9ed89c9e0f95b379cf71e456f508f4056e75d9cff151b7`。
系数来自已固定哈希的 libmad `cs[8]/ca[8]`，以 `cs/abs(ca)` 成对重排；并非原厂 ROM 表。

- `pair` 输入 `R1:R0=A`、`R4:R3=B`、`R2=0..7`，输出相同寄存器对；
  计算 `A'=A*cs-B*ca`、`B'=B*cs+A*ca`。四个乘积及和/差保留为有符号 64-bit，
  最后统一算术右移 28 位，不逐乘积截断；也不会在 32-bit 中直接对 `INT32_MIN` 取负。
  成功 `R2=0`，非法索引 `2`，最终 Q28 溢出 `3`；错误时两对输出均为零。
  保留 `R5..14`、DS、SOCR，暂时清除 MAS 后完整恢复。
- `spectrum` 输入 `R3 → {rate_index, block_type, mixed_0_or_1, reordered_q28_576}`，
  原地处理，成功 `R0=576/R2=0`。非法几何 `R0=0/R2=2` 且不写输出；
  溢出 `R0=0/R2=3`，已经完成的蝶形可能保留，当前失败的一对不写入，调用者必须拒绝整个结果。
  保留其它 GPR、DS、SOCR。描述符、缓冲和栈的对齐/分配/互不重叠由调用者保证。
- 长/起始/结束块处理 31 个内部子带边界，每处 8 个蝶形；纯短块保持所有位不变。
  混合块只处理长前缀内部边界：通常 36 项/两个子带，处理一处；8 kHz 为 72 项/
  四个子带，处理三处，不越过长短交界。**8 kHz 这一扩展是依长前缀几何推导的规则**，
  与 libmad/mpg123 固定一处的调用和 FFmpeg 的 `XXX: check this for 8000Hz` 不同，
  不能说已经由它们或真实 8 kHz mixed PCM 证明。

离线参考 `test_np560_mp3_antialias_reference.c` 提取固定源码的 `III_aliasreduce` 和
`cs/ca` 原函数/常量文本；将样本和乘加类型改为 64-bit，使用明确的 Q28 floor，
外围适配成逐对原子溢出返回，并为 8 kHz mixed 传 72 项。它没有链接进 QEMU，
也不宣称与未经修改的 libmad `fixed.h` 舍入/溢出行为逐位相同。
另以公开 `c={-.6,-.535,-.33,-.185,-.095,-.041,-.0142,-.0037}`、
`cs=1/sqrt(1+c²)`、`ca=c*cs` 的双精度公式交叉检查系数方向和尺度。
原始算法可核对 [libmad 源码](https://github.com/sezero/libmad/blob/master/layer3.c)，
本地实际使用的仍是来源记录中的固定 commit 和 SHA，而非随 master 更新。

已完成的隔离检查（均 `passed=true`，QEMU 未改）：

| 记录，位于 `tmp/` | 实际覆盖 |
| --- | --- |
| `np560-mp3-antialias-suite-20260907-v1` | 1482 对输入，含八组系数、全宽正负/进位/溢出和非法索引；101 个整频谱，含九采样率、长/起始/短/混合/结束、基向量、首尾边界、非法几何、迟发溢出和纯短不修改；另 `icount=5` 复测 130 对和 4 个向量，共 34 个 QEMU。浮点公式最大偏差 6.700106 Q28 LSB，小于按常量量化和 floor 推导的 9 LSB 界限 |
| `np560-mp3-alias-chain-mpeg1-20260907-v1` | 真实 MPEG1 前 8 帧/32 声道段，含 16 个 MS granule；单 guest 原生串至抗混叠，共 65678 个 word 一致，不代表文件全部 116 帧完成此阶段 |
| `np560-mp3-alias-chain-mpeg2-20260907-v1` | 真实 MPEG2 全 13 帧/26 段，含 12 个 MS granule，72127 个 word 一致 |
| `np560-mp3-alias-chain-mpeg25-20260907-v1` | 真实 MPEG2.5 全 7 帧/7 段、单声道，`icount=5`，29574 个 word 一致 |
| `np560-mp3-alias-chain-is-20260907-v1` | 真实 `l3-he_mode.bit` 从 0 到 69 帧；前 50 帧原生熵解码建立历史，随后 20 帧/80 声道段接至抗混叠，含 40 个 IS granule（20 个为 MS+IS），337372 个 word 一致；不是全部 128 帧或 PCM 已验证 |

4.9 阶段当时尚无 IMDCT/窗口/重叠后的时域子带样本（后续见 4.10），仍无合成 PCM 或原厂播放器接口。
当前溢出返回是显式暴露范围不足，不是合法高幅度帧的最终处理方案；整条滤波链的
动态范围/缩放还要统一，不能以丢帧作为“完整解码”。

### 4.10 原生混合滤波：连续时域子带与声道历史

`scripts/build_np560_mp3_hybrid.py` 实现 IMDCT、四种窗口、跨块重叠和频率反转，
代码 `20:B800..BB9B`（924 bytes），SHA256
`811e0b33209e1e447ad33914635fd8323ba9a44fe09d21936f71f73dbd1617ed`；
四张 `36×18` 系数矩阵位于 `21:9870..C0EF`（10368 bytes），SHA256
`51515ce2dd081a536d3409d52deb20f311aa5ba17549e8e45639ad4fdbd8468c`。
依赖已有抗混叠组件的私有 64-bit 乘法入口，没有修改 CPU 或其它已验证组件。

接口：

- `transform`：`R3 → {block_type, X18_Q28, Z36_Q23}`，正常/起始/短/结束块均可。
  短块输入是此前 FFmpeg 风格重排的 `X[3*k+window]`，并非 libmad 的每窗口连续六项。
  成功 `R0=36/R2=0`；非法 block type 返回 `R0=0/R2=2`，不写输出。
- `hybrid`：`R3 → {rate_index, block_type, mixed, X576_Q28, samples576_Q23,
  overlap576_Q23, workspace160bytes}`。输出按 `samples[time][subband]` 排列，
  历史按 `overlap[subband][time]` 排列。混合块前两个子带用正常长窗口；8 kHz
  前四个，沿用已说明的 72 项长前缀推导，未宣称真实 8 kHz mixed PCM 已核验。
  对奇数子带的奇数时刻，在叠加后反转符号，存入下一块的尾部保持未反转状态。
  成功 `R0=576/R2=0`；非法几何 `2` 不修改输出/历史；被外部损坏的历史导致
  加法/取负溢出则返回 `3`，此前已写部分须拒绝，失败样本不写入。
- `reset`：`R3` 指向单个声道的 576 项历史，原生清零，返回 `576/0`。
  只在初始化/不连续等时刻调用，不能每个 granule 重置。零频谱会产生零窗口输出，
  但 `hybrid` 仍输出并清除上一块尾部，不能跳过整个子带。
- 所有公开入口保留 `R1/R3..14`、DS 和完整 SOCR；工作区/描述符/缓冲/栈对齐、
  分配、互不重叠由调用者保证，近数据指针使用 DS0=0。

数值选择明确区别于原厂或 libmad 的位级舍入：

- 长 IMDCT 系数为 `cos(π/72*(2*n+19)*(2*k+1))`；与正常、起始、结束窗口融合，
  量化为 Q28。短块由三个六项 IMDCT/短窗口平移叠加的线性矩阵实现。
- 每个输出是完整有符号 64-bit 点积，最后算术右移 33 位得到 **Q23**，不是
  Q28 数字强贴新标签。无额外 `2/N` 归一化，也不先截断可能过大的未加窗结果。
  构建断言每行系数绝对值之和小于 `16×2^28`：任意有符号 32-bit 输入的点积
  均不溢出 int64，Q23 窗口输出严格位于 `(-2^30,2^30)`，两个真实历史块相加和
  随后的取负均可表示。该头部空间解决本阶段的幅度扩张，**不是宣称之前重定标/
  MS/抗混叠或后续 PCM 的全链动态范围已经完备**。
- Q23 样本和历史仍是内部时域子带，不是送 DAC 的 PCM。后续合成必须沿此比例
  处理，不可把这些值当 Q28、直接 16-bit 截取，或假装已输出音乐。

离线参考首先用 long-double 的独立 IMDCT → 窗口 → 三短窗拼接公式核验，
没有复用 Python 生成的矩阵字节；每个结果与整数系数点积逐字一致，数学公式
误差在全测试集最大 `1.794153 Q23 LSB`，低于 4 LSB 检查界限。
随后加入固定 libmad 的 `fastsdct/sdctII/dctIV/imdct36/III_imdct_l/III_imdct_s`
原函数拓扑、原窗口和新增原件 `imdct_s.dat` 交叉检查相位/比例/短窗口布局。
其数值类型/乘法改为 long double，`fastsdct` 的系数 enum 改为浮点常量声明，
短输入先从交错布局转为窗口连续布局；不称作未修改 libmad 定点逐位相等。
该独立算法的最大偏差为 `3.354394 Q23 LSB`，未链接 QEMU、未播放原文件。

已完成证据（均位于 `tmp/`）：

| 记录 | 实际覆盖 |
| --- | --- |
| `np560-mp3-hybrid-suite-20260907-v1` | 210 个变换，含四窗口的每个正负基向量、零/全宽极值/随机值/非法类型；52 个全子带向量，含九采样率和混合几何、畸形历史溢出、零频谱尾部；8 组同 guest 两块序列，覆盖窗口切换、8 kHz mixed、保留尾部和原生 reset，另 icount=5 复测；共 41 个隔离 QEMU 全通过 |
| `np560-mp3-hybrid-libmad-reference-20260907-v1` | 同组输入的新增 libmad 浮点拓扑交叉检查；明确 `offline_only=true`，没有把零个 QEMU 计为原生测试，组件代码和原数学整数结果未变化 |
| `np560-mp3-hybrid-chain-mpeg1-20260907-v1` | 真实 MPEG1 前 8 帧/32 声道段，从第 0 帧自主运行到 Q23 时域子带；84198 个 word 一致；非整个 116 帧文件或 PCM |
| `np560-mp3-hybrid-chain-mpeg2-20260907-v1` | 真实 MPEG2 全 13 帧/26 段，102170 个 word 一致，左右声道各自的持久尾部也逐帧比较 |
| `np560-mp3-hybrid-chain-mpeg25-20260907-v1` | 真实 MPEG2.5 全 7 帧/7 段、icount=5，45737 个 word 一致；未使用的右声道历史保持零 |

原生帧检查使用 `0x6000/6900` 两块历史、`0x7200` 时域输出暂存、`0x7B00` 工作区、
`0x7BC0` 描述符和 `0x23D0` 返回记录，已核对普通近数据映射；没有修改机器内存映射。
所有帧/声道都实际执行滤波，最后把时域样本复制回该段原频谱缓冲用于逐字检查，
不从宿主注入历史。`--hybrid` 明确拒绝 `--post-start` 非零；旧 IS 的“前 50 帧只做
熵解码”记录不能作为新阶段证据。真实 IS/LSF-IS 的连续时域整链还要扩展验证。

实现目前为直接矩阵计算，真实输入检查尚非实时速度；后续要以真实播放结果核对
32 子带合成、输出精度及性能，再优化运算量，不能把小片段通过宣布为播放器完成。

### 4.11 原生子带合成与实际 PCM16

`scripts/build_np560_mp3_synthesis.py` 新增合成组件，代码位于 `20:1400`，
1234 bytes，SHA256 `cab8ebaca7cdad3eee02fd218cdcd433095e796cced8bfad372e484ebcc2ec3e`；
表位于 `21:C0F0`，7168 bytes，SHA256
`99c5e2fb9880db43796340ccf560543ea8eabbee46349134e2f06e9693d7aaa2`。
未改 QEMU 指令、总线映射或原厂服务入口。

内部 API 与状态：

- `slot` 的 R3 指向五 word 描述符：`state_bank,state_ptr,X32_Q23,PCM32_s16,work32bytes`。
  `granule` 使用同一描述符，输入为 time-major 的 576 个 Q23 子带样本，连续调用 18 个 slot。
- 每声道 4098 bytes：首 word 为环首字节偏移，随后 V1024 的 Q17 有符号历史；
  `reset` 原生清空本声道，零输入仍推进历史并释放旧尾部，不用清零 PCM 模拟尾音。
- state 为 banked DS1、bank ≤ `01FF`、对齐指针 `8000..EFFE`，完整状态必须容纳在该银行。
  其它描述符/输入/输出/工作区为 near DS0=0，调用者负责全部区域与栈互不重叠。
- 成功 R0 分别为 32/576/1024，R2=0；状态几何或 head 非法返回 R0=0,R2=2，
  不改输出/历史（granule 预先复制工作描述符）。保留 R1、R3..14、DS 和 SOCR。
  已测试非法 head；银行/指针范围有前置检查，尚未声称所有非法参数组合均已测试。

算法及数值边界：

- 32 行独立余弦矩阵采用 Q26，32-bit 输入与系数在有符号 64-bit 中点积，
  算术右移 32 位得到 Q17 V，剩余行按精确正负对称补齐；不把中间乘积压回 16-bit。
- `D.dat` 展开为 512 个有符号 Q16 窗口值，与固定 FFmpeg 的 257 项半窗口独立展开
  逐项相等。每个 PCM 累加 16 个窗口乘积，最后才加 `2^17`、右移 18 位、限幅至 PCM16。
  舍入是 nearest、半值向正无穷；正常 PCM 截幅不是解码错误。
- V1024 环每 slot 移动 64 项，显式按 U/V 索引取数，左右声道状态隔离。
  这是新重建的定点比例/舍入，不是原厂 ROM 或原版 libmad 的逐位实现。
- 单 slot 的完整 Q23 存储宽度已保留安全的 64-bit 点积空间；仍不代表上游 Q28
  重定标/MS/抗混叠的全码流动态范围已经解决。

组件验证 `tmp/np560-mp3-synthesis-suite-20260907-v1/report.json`：47 个 slot、
5 个全 granule、1 组远银行持续历史序列，另 icount=5 共 31 个隔离 QEMU 全通过。
覆盖 32 个基向量、全宽极值/随机数、非零旧尾部、非法 head、原生 reset 和跨环回绕。
PCM 与声明的整数参考逐 word 一致；独立 64×32 浮点数学公式、固定 libmad 原
`dct32/synth_full` 拓扑的 long-double 适配版交叉比较，最大差异均为 1 PCM16 单位。
后者保留原系数和滤波拓扑，但改变了算术宏/类型，不冒称原库定点逐位一致。

`test_np560_mp3_frame.py --pcm` 串起全部 guest 组件：每声道状态实际位于
bank `30` 的 `8100/A100`，每帧核验整个历史及哨兵；所有历史均由 guest 建立。
原生调用者把 PCM 写到独立 RAM 区 `19:0000` 起，测试结束后只读捕获。
宿主仅做声道交错及 WAV 头封装，WAV 内容来自捕获字节，不来自参考解码器。
`--pcm` 禁止非零 `--post-start`，不能跳过滤波历史后仍宣称完整解码。

新增实际证据（全部在 `tmp/`）：

| 记录 | 实际覆盖/结果 |
| --- | --- |
| `np560-mp3-pcm-chain-mpeg1-20260907-v1` | 原始 MPEG1 前 8 帧/32 段，44.1 kHz 双声道；捕获 18432 个 PCM16 值；FFmpeg 等长、零延迟移动、无增益调整，最大差异 1，RMS 差异 0.399517；不是完整 116 帧歌曲 |
| `np560-mp3-pcm-chain-mpeg2-20260907-v1` | 原始 MPEG2 全 13 帧/26 段，22.05 kHz 双声道；guest 数值/历史检查通过，捕获 14976 个值；初次 FFmpeg 自动裁剪导致长度不一致，原失败记录保留 |
| `np560-mp3-pcm-compare-mpeg2-20260907-v2` | 上述捕获的离线复核，没有重跑 QEMU；对齐参考端的元数据语义后比较 13824 个值，最大差异 1，RMS 0.386026，原 WAV 不变 |
| `np560-mp3-pcm-chain-mpeg25-20260907-v1` | 原始 MPEG2.5 全 7 帧/7 段，8 kHz 单声道、icount=5；guest 数值/历史检查通过，捕获 4032 个值；初次参考长度失败同样保留 |
| `np560-mp3-pcm-compare-mpeg25-20260907-v2` | 原捕获的离线复核，没有重跑 QEMU；比较 3456 个值，最大差异 1，RMS 0.360041，原 WAV 不变 |
| `np560-mp3-pcm-integrated-mpeg25-20260907-v2` | 修正参考语义后的正常入口验收：重新从第 0 帧在一个 QEMU 中完成 7 帧解码、捕获及独立比较，整次通过；WAV PCM SHA 与首次捕获一致 |
| `np560-mp3-frame-modes-regression-20260907-v8` | 原有非 PCM 的六帧模式切换检查通过，确认新增组件及可选捕获未破坏原入口；不将它计为新的 PCM/播放器证据 |

参考长度差异的处理有明确依据，不是搜索最佳偏移：`ffprobe` 包位置/大小证明
MPEG2/2.5 各跳过一个 Info 帧；其 guest 量化频谱和 PCM 都为零。比较时仅排除该
576-sample/channel 信息帧，FFmpeg 使用 `-flags2 +skip_manual` 禁止解码延迟自动裁剪。
guest 原始 WAV 没有裁剪或补零，也未改增益或改原 MP3 来促成一致。`ffmpeg-packets.json`、原捕获 SHA、
WAV SHA 和比较参数均保留；所用离线 FFmpeg 版本为 4.2.7。

以上是测试短文件/前缀的实际压缩音频解码证据，不是音乐播放器可用或完整标准符合性。
真实 IS/LSF-IS/mixed 的完整 PCM、全量动态范围、CRC/跨帧使用冲突仍须补齐。
直接矩阵目前非实时速度；后续重点是原厂私有状态/输入消费/缓冲适配，以及真实播放节奏下
的性能优化，不再重复建设组件验证平台。NPE 专有 ESAC 声音仍单独缺失。

### 4.12 可独立调用的 PCM 驱动与调用者工作区

本节地址及尺寸对应最初的零偏移版本；现行 `DS0:R3` 接口与新入口地址见 4.14。

新增 `scripts/build_np560_mp3_decoder.py`：在 guest 内统一串联熵解码、重定标、
立体声、重排、抗混叠、混合滤波和子带合成。公开调用者只需 reset、提交一个完整帧、
取出剩余 granule，不再逐组件传递中间频谱。这是新定义的内部接口，**不是原厂
`01:4804/49F8` 的恢复字节或已完成适配**。

| 入口 | 当前诊断地址 | 行为 |
| --- | --- | --- |
| `reset` | `20:D400` | 验证两块合成状态的几何，清除熵/混合/合成历史、待输出状态及两声道 PCM；保留输入和配置 |
| `decode_frame` | `20:D544` | 消费一个完整帧，产生首个 576-sample/channel PCM；MPEG1 的第二 granule 留待取出 |
| `next_granule` | `20:D5F4` | 处理待取出的第二 granule，不再次读取或消费原始输入；无待处理内容时返回空 |

正常返回 `R0=576/R2=0`，输出为每声道 576 个 PCM16；单声道清零未使用的右缓冲。
`R0=0` 时 `R2=1` 表示完整输入不足或没有待处理 granule，`2` 为无效配置/输入，
`3..5` 为熵解码错误，`6` 表示上一帧仍有 granule，`7` 为后处理错误。
busy 和空 `next_granule` 不改状态及输出；后处理错误记录阶段/子状态、撤销有效输出
并使初始化标志失效，须 reset 才可继续。不是静默丢帧或伪造成功。
保留 `R1/R3..14`、DS、SOCR；输入头几何和位上下文仍由调用者提供，CRC 尚未验证。

工作区选择通过 `scripts/np560_mp3_workspace.py` 传到全部十二个组件：默认仍选择
bank 0，`workspace_bank=None` 保留调用者 DS0。构建 PCM 驱动时拒绝混入默认 bank-0
组件，避免内部调用悄悄改用原厂共享 RAM。位储备产生的 far 位上下文也改为记录真实 DS0，
不能仅删除函数入口的 bank 选择而保留硬编码的零 bank。

- 内部 near 工作区占用 `0x6300`（25344）bytes，包含完整帧记录、频谱、中间输出、
  两声道混合历史和 PCM；由调用者持有，偏移是重建实现的新布局。
- 两声道合成历史各 4098 bytes，位于另一 bank，两个指针必须对齐、非重叠且不越界。
  这不是机器端预留 RAM；本阶段尚未接分配器，后续原厂堆接入见 4.13。
  播放器实际停止、退出和回调期间的生命周期仍待接齐。
- 不能将本诊断的 `20/21` 段地址直接装入正式 ROM：那里已有原厂程序；仍需实际布局方案。

迁移中查出的两个问题与处理，失败产物全部保留：

1. 初始驱动放在 `20:2C00` 时跨入已有 Harvard 别名窗口 `20:2DE0..338F`，
   代码视图实际来自 `3D:2DE0`。只读的执行前校验已证明字节在启动前便不同，
   并非运行中返回地址被写坏。诊断链接改到现有 `20:CE3A..D39B` 窗口之后的
   `20:D400`，执行前/后驱动字节均核对一致；未改 QEMU 机器映射来容纳测试。
2. MPEG1 首帧第二 granule 的 SCFSI 复用曾执行 `MOV R0,[R11++]`；R11/FP 的
   内存操作固定走内部 SRAM，不服从 DS0。此前 bank-0 夹具掩盖了错误；换 bank 并
   毒化低内存后，缩放因子出现 `CAFE`，重定标拒绝该输入，细节 `0102`。
   修复为复制 FP 值到普通数据指针 R1 读取，再同步递增值。没有补新 CPU 指令、
   宿主代算或跳过失败 granule。全部 16 种 SCFSI 掩码、两种 compress 和原地复用的
   32 例定向回归通过（`np560-mp3-scfsi-regression-20260907-v1`）。

`scripts/tests/test_np560_mp3_decoder.py` 仅调用上述公开接口，逐 granule 检查实际 PCM、
全部滤波历史、消费位置、pending/错误状态与边界哨兵，并验证 busy/empty 调用不变。
bank-0 RAM 在测试前由 guest 毒化，结束时逐 word 检查；仅排除真实栈区及八字节
诊断区，原厂的 `1000/1784/333E` 等地址都在检查范围内。没有 NAND 或运行中宿主内存注入。
PCM 在清除前从真实输出缓冲记录、结束后只读捕获；参考解码器仍仅离线比较。

实际记录（均位于 `tmp/`，不是原厂播放器操作证据）：

| 记录 | 覆盖与结果 |
| --- | --- |
| `np560-mp3-banked-decoder-mpeg1-20260907-v1` | 前 8 帧、32 次生产/busy/empty 调用；bank `30/31`；18432 个 PCM 值，最大参考差异 1 |
| `np560-mp3-banked-decoder-mpeg2-20260907-v1` | 全 13 帧、26 次生产/empty 调用；bank `30/31`；14976 个原始 PCM 值，按 4.11 的元数据规则比较 13824 个，最大差异 1 |
| `np560-mp3-banked-decoder-mpeg25-20260907-v1` | 全 7 帧、14 次生产/empty 调用；改用 bank `34/35`、icount=5；4032 个原始值、比较 3456 个，最大差异 1 |
| `np560-mp3-banked-decoder-reset-20260907-v1` | 前两帧在 bank `34/35` 解码后原生 reset，再调用空 next；逐项证明所有熵/滤波历史、PCM 和 pending 清除，头配置与输入位置保留；10 次调用通过 |

上述三组连续流的原始 PCM SHA 分别与 4.11 的 `46f663ea...`、`5cc41bcb...`、
`4d2c3fbf...` 完全一致；内存迁移/内部调度未改变采样。测试仍不是实时速度，
也没有据此声称实际分配器、原厂环、播放控制、中断和双缓冲已经连通。

当前 bank-owned 包是 `np560-mp3-banked-decoder-core-20260907-v2`，13 个组件、
21 个互不重叠 code/table 片段。驱动 1570 bytes，SHA256
`eb8883a78fa9eb2c2b9a8a6954dede2d3c860cfc91a6f5262458db409648b9e0`。
caller-DS0 的 scalefactor 代码 1138 bytes，SHA256
`a692b2e6006a323bcf05ffc71fb0f0108a6d69c8dd237f9a4c08ae6a3ee50ff7`；表未改。
默认 bank-0 包另存 `np560-mp3-frame-core-20260907-v9`，相对 v8 仅 scalefactor
代码片段变化（1142 bytes，`23651968c06832323f18489eff0479c30e74d58e67d3070b2c3a5f0c2b82d37a`），
其余 19 个片段逐哈希相同。旧 v1 bank-owned 包处在错误链接地址，不能用于后续接入。

下一步落实原厂 RAM 分配/释放及 ROM 放置，然后连接输入环可用量/读位置、
初始化与复位、输出双缓冲、回调和错误/结束状态，并优化实时速度。
尚不安装占位 `01:4804/49F8`。NPE ESAC、CRC、合法范围与完整 IS PCM 核验等缺口保留。

### 4.13 通过原厂堆取得、锁定、释放真实解码工作内存

新适配 `scripts/build_np560_mp3_allocation.py` 使用原 PRG 的对象分配器，不再把
诊断 bank `30/34` 视作正式固件中的空闲 RAM。正式 VMA03 的程序占据 `03:0000`
起的 4 MiB；那两块诊断 RAM 的物理地址落在该范围，不能照搬。

原厂初始化器 `30:8C1C..8D10` 发布的 arena 是 `[51:4A40,52:3A40)`，共 `F000`
（61440）bytes，与显示/应用对象共用；不是整个机器的通用空闲内存总量。
该区每个链表节点的头部是 `tag,next_segment,next_offset` 三个 word，实际数据从
节点后六个 byte 开始。下面原始指令均来自未修改的 PRG，测试前后逐字节核对代码视图：

| 原厂入口 | 新适配实际使用的副作用 |
| --- | --- |
| `25:77DA(size)` | 按 byte 数申请、偶数对齐，返回真实非零 handle；无空间返回零 |
| `31:5300(handle)` | 查找 handle，置节点 tag 的 `8000` 位，返回数据的物理 segment:offset；不是无副作用的普通查询 |
| `30:3A56(handle)` | 对已锁定对象置 `4000` 延迟释放位；未锁定对象可直接清除 handle 并回收 |
| `30:8B26(handle)` | 清锁定位，兑现延迟释放、清 handle bitmap，再调用原厂 `27:6100` 合并/整理 |

因此必须在保存解码器原始指针期间持有锁；释放采用先标记释放、再解锁，不直接改原厂
链表或位图，也不只清新适配自己的 handle。只对本次实际取得的对象这样操作。

本阶段的 `acquire/release` 使用调用者单独持有的 16-byte 描述符，依次保存
`handle,allocated_bytes,physical_segment,physical_offset,workspace_bank,synthesis_bank,left,right`。
这是重建代码的新描述符，不冒认成 `333E` 等原厂共享字段。描述符须在另一个稳定、
已分配的 near 区域，初始清零；调用者必须串行化解码与释放，不能在音频回调使用中释放。
`acquire` 返回真实 handle 和 `R2=0`；已持有对象返回 busy `6` 且不改描述符；
内存不足返回 `R0=0/R2=1`。内部地址检查/尝试次数失败另有显式状态，均归还已取得对象。
`release` 实际调用上述两项原厂服务并清描述符；重复释放空描述符不操作其它对象。

当前核心需要 bank 对齐的 `0x6300` near 工作区，并要求两个合成历史位于另一 bank。
适配先申请最少 33550 bytes，根据原厂返回的真实位置安排：若对齐前的空隙能放下两份
历史，就放在前面；否则放到工作区之后的 bank。空间不足时，归还该对象并按所需大小
重新申请，每次重新查指针，最多三次，不假设释放/整理后地址永远不变。
其中额外十个 byte 用于工作区尾部、两份历史前后的边界字，全部在申请范围内。
否则测试写入哨兵会触及原厂下一个节点头，不能把这种破坏错误归为 CPU/解码器缺陷。

边界适配后的代码为 `20:E000`，858 bytes，SHA256
`dff6946f45a44af53376b268950d00d9cdc2a0abe1dba097c11fcbe9a11de48f`，
构建产物 `tmp/np560-mp3-native-allocation-core-20260907-v1`。
该地址仍仅供隔离链接，未写入用户系统 ROM，也未让 `01:4804/49F8` 返回占位成功。

`test_np560_mp3_allocation.py` 的隔离 caller 仅在开头执行一次原厂堆初始化；
新运行时适配自身从不清空或重置系统堆。`np560-mp3-native-allocation-20260907-v4`
三种情况全部通过：

| 已占用的邻接对象 | 实际结果 |
| --- | --- |
| 无 | handle 1，实际申请 39100 bytes，数据从 `51:4A46` 起；工作区 bank `A3`，合成 bank `A2`，指针 `CA48/DA4E` |
| 已锁定的 8192 bytes | handle 2，申请 46528 bytes，数据从 `51:6A4C` 起；工作区仍 `A3`，合成改为 `A4:8002/9008`；邻接对象首 word `BEEF` 保留；icount=5 |
| 已锁定的 28672 bytes | 原厂无足够连续空间，申请失败，描述符保持空；邻接标记保留，没有伪造可用内存 |

各情况随后都执行释放并再次申请，没有再初始化堆。检查首节点、全部 16-word handle
bitmap 以及实际再次取得的 handle/指针，确认没有只清描述符而泄漏内存。
该检查不宣称穷尽碎片化、并发分配或所有原厂应用的内存需求。

`test_np560_mp3_decoder.py --factory-heap` 已把这项申请结果真正交给 PCM 核心：
guest 从描述符读取 bank 和历史指针，实际解码、清除历史，再归还对象；不是仅验证
分配器返回值。两种位置均完成原始 MPEG1 前两帧、10 次 decode/busy/next/reset 调用，
检查 83818 个状态/采样 word，最后检查原厂堆回收及 bank-0 区未被误写：

- `tmp/np560-mp3-factory-heap-pcm-20260907-v1`：空堆，历史放在工作区之前。
- `tmp/np560-mp3-factory-heap-neighbour-pcm-20260907-v1`：8 KiB 已锁定邻接对象，
  历史放在工作区之后；icount=5；完成解码后邻接标记仍保留，再由其拥有者释放。

两份实际捕获均为 4608 个 PCM16 值，SHA256
`51d9b2758c7c672abd18d8cadbd3473183994c3f3815642eb93538209259fe52`，
与此前两帧结果相同；离线 FFmpeg 最大差异仍为 1 PCM16 单位。
宿主没有写入运行中内存、代算音频、修改原 PRG 或 NAND。QEMU SHA 仍为
`d26b7ce7f17c8345a2a2604a1c18c7c960549640ae0ebebb8458f8ea5e577372`。

保留的失败/过渡记录：初次 v1 分配测试在执行前发现诊断调用地址没有装入对应原始
函数，已纠正 caller 的原字节装载，未改机器映射；v2/v3 是加入十字节边界空间前的
分配验证版本，不用于带哨兵的 PCM 接入。旧 bank 模式的一帧回归，其 guest 检查已通过，
但离线 ffprobe 拒绝单帧流，记录在 `np560-mp3-banked-regression-20260907-v1`；
不能把它当作整次独立比较通过。随后使用两帧完成
`np560-mp3-banked-regression-20260907-v2`，原有非堆模式的 guest 检查、复位和独立
PCM 比较全部通过，捕获 SHA 同为上述 `51d9b275...`。

**剩余工作仍直接面向实际播放器：** bank 对齐使本轮两种申请量分别达到约 38/45 KiB，
不能根据空堆/人为占用测试推定真实 MP3 窗口一定有足够空间。需要减少对齐浪费、核对
真实现场的可用量及稳定描述符位置；正式代码/常量表布局、输入环、双缓冲、回调、错误
结束语义和实时性能仍未完成。两帧原厂堆解码不等于原厂音乐播放器已经可以操作播放。

### 4.14 工作区支持非零偏移，减少原厂堆的对齐浪费

前版将 near 工作区强制放在 32 KiB bank 起点。原厂申请返回的地址不一定对齐，
丢掉整个前缀后，即使剩余总量大于解码状态大小，也可能无法再申请。现在
`build_np560_mp3_decoder.py` 的三个公开入口均接受 **调用者 `DS0:R3`**：R3 是偶数
near 基址，范围 `0000..1D00`；内部布局常量保持相对偏移，所有状态、历史和描述符
指针均加上该基址。入口拒绝不合法基址，不借跨入 DS1 的地址继续运行。
工作区仍为 `6300` bytes，算法本身与十二个子组件的 code/table 哈希均未改变。

现行诊断入口为 `reset=20:D400`、`decode_frame=20:D5AC`、
`next_granule=20:D6A0`。驱动 2168 bytes，SHA256
`4dafbe2e7571672d7bdf7b514ab313d4ede18082b703ecf1ee6820f5051f94bd`，
包 `tmp/np560-mp3-offset-decoder-core-20260907-v1`。这些仍不是正式 ROM 安装地址。

`build_np560_mp3_allocation.py` 在原厂返回位置能容纳整个 near 状态时，直接使用
这个位置，不再前移至下一 bank；不能容纳时仍使用边界，并优先利用前缀放合成历史。
全部填充和边界检查字都归本次申请持有；near 状态尾部另留一个 word，故此适配返回的
基址上限为 `1CFE`。18-byte 描述符在前版八项之后新增第九项 `workspace_offset`；
**调用者必须同时更新描述符长度，并向每次 PCM 调用传入 R3，不能混用旧 ABI。**
申请/锁定/释放/解锁继续执行未改动的 PRG 函数，不改原厂堆头或 handle bitmap。
新适配 888 bytes，`acquire=20:E000/release=20:E1F4`，SHA256
`ce68f639f1ff4b53fd6900a1488a649e1eeef1ac9f45022260b5bf1a38ff3baa`，
包 `tmp/np560-mp3-offset-allocation-core-20260907-v1`。

原厂堆验证 `tmp/np560-mp3-offset-allocation-20260907-v1/report.json` 的五组均通过：

| 预先锁定的对象 | 实际申请量 | 工作区 DS0:R3 | 结果 |
| --- | --- | --- | --- |
| 无 | 39100 bytes | `A3:0000` | 成功；旧布局保留 |
| 8192 bytes | 46528 bytes | `A3:0000` | 成功；此位置仍需对齐 |
| 16384 bytes | 38336 bytes | `A3:0A4C` | 新布局成功，无需丢弃可用前缀 |
| 20480 bytes | 34240 bytes | `A3:1A4C` | 新布局成功，无需丢弃可用前缀 |
| 28672 bytes | 无 | 无 | 原厂返回无空间，保持空描述符 |

每组均检查重复申请的 busy、两次释放、邻接标记、原厂堆头与全部 handle bitmap，
并在不重置堆的条件下再申请、释放。没有假定实际播放器一定拥有同样的连续空间。

两帧实际 PCM 验证也通过，以下各记录均在 `tmp/`：

- `np560-mp3-offset-smoke-20260907-v1`：诊断 bank `30`，偏移 `0A4C`。
- `np560-mp3-offset-heap16-pcm-20260907-v1`：原厂堆预持有 16 KiB 对象，
  实际申请 `A3:0A4C`；解码后 reset、释放本对象，再检查并释放邻接对象。
- `np560-mp3-offset-heap20-pcm-20260907-v1`：同一路径，20 KiB 邻接对象，
  实际申请 `A3:1A4C`；没有清空堆来换取申请成功。
- `np560-mp3-offset-edge-pcm-20260907-v1`：bank `34`、偏移 `1CFE`、icount=5，
  状态尾部检查字恰在 `7FFE`，验证没有错误切入另一个 DS bank。
- `np560-mp3-offset-root0-pcm-20260907-v1`：使用新核心重新验证原厂空堆的
  `A3:0000` 零偏移路径，实际解码、reset、释放及原厂堆回收全部通过。

各记录均完成 10 次公开调用、83818 个状态/采样 word 比较，捕获 4608 个 PCM16 值。
实际 PCM SHA 仍为 `51d9b2758c7c672abd18d8cadbd3473183994c3f3815642eb93538209259fe52`；
离线 FFmpeg 最大差异 1，长度一致，没有增益或延迟调整。原厂分配器和新驱动的
执行前/后代码校验通过，低 bank 原厂共享区域检查通过；QEMU、用户 NAND 和 Web 未改动。
诊断调用者核对完整返回描述符后用该位置运行，不是已接入实际播放器的生命周期。

**新增能力是更灵活的原厂堆内存承载，不是 MP3 播放完成或性能已优化。**
仍需确定实际窗口中的描述符所有权、正式 ROM/常量布局、输入环消费、双缓冲、回调
和结束/错误语义，再按真实播放节奏优化。原厂 `01:4804/49F8` 尚未安装本核心。

### 4.15 Resident ROM 的通用数据访问与首个组件迁移

为正式链接检查数据视图时，已复现并修正 VMA03 低端 resident ROM “代码可执行、
DS 数据却读到 RAM”的板级缺口。依据专利图 2/3/4 和数据取数说明，共享既有 ROM
backing；没有按 MP3 入口返回表值或扩大某张表的专用 alias。
边界/写保护检查及原厂冷启动通过，原 PRG、源 ROM、NAND 均未修改。

Huffman 的代码与原常量表已一起放入当前 ROM 副本的已检查空洞：代码 `01:2400`、
表 `01:C000`。39 组、6734 次符号/位读取，包括所有书、错误回滚和 far 跨 bank
验证通过；实际通过通用 DS 访问 ROM 表。没有在这里调用原厂播放器或输出 PCM。
现行 QEMU `533dd1a4...` 及完整证据见 [resident ROM 数据访问](np560_resident_rom_data.md)。

下一步是其余组件/大表的正式布局及依赖链接，不能直接覆盖原 PRG 的 `20/21` 段。
原有连续重定标大表必须处理分散 ROM 空间，原厂入口需要保留；不是有空洞即可整包平移。

### 4.16 完整解码核心的 resident ROM 放置

2026-09-07，新增 `scripts/build_np560_mp3_resident.py`，将完整 native 核心和
原厂堆分配适配器放入当前已核对 skeleton 的 `01:0000..02:FFFF`。这不是取得
原厂 mask ROM，也尚未连接 `01:4804/49F8` 等原厂入口。

代码及近表地址现可配置，依赖使用实际生成的组件入口。重定标的 8207 项幂表
改为 9 页（每页至多 1024 项/4096 bytes，末页 15 项/60 bytes），DMCU 读取
ROM 中 36-byte bank:pointer 目录后再取表项；没有宿主查表或 MP3 专用映射。
几何表中的 near 指针随实际放置地址重建。默认诊断布局的 13 组件/21 片段
与旧 offset-core 清单逐 SHA 一致，没有因为链接改造改变默认算法输出。

构建只接受已核对输入 SHA，检查目标均为对齐 `0F00` 空洞、片段不交叠、不跨
near bank、写入之外全部字节不变、镜像长度不变。扫描 PRG 和已有 resident
中的直接 SCALL/SJMP，保留 57 个候选目标附近及完整已知声音入口组；假阳性
宁可少用空间。**这不是未知间接目标不存在的证明**，清单仍明确该限制。

- 新 ROM：`tmp/np560-mp3-resident-core-20260907-v2/resident.bin`，2095672 bytes，
  SHA `9eae42876c5ac9edc6640f1d82aa01434eca3d3320f0fa2ac92ddabd65be6577`。
- 14 组件、33 片段，实际装入 79904 bytes；保留检查后的可用空洞 26812 bytes。
- 原 skeleton SHA `a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef`，
  原 PRG SHA `d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`，均未改写。
- 内部入口：reset `02:147A`、decode_frame `02:1626`、next_granule `02:171A`；
  分配 acquire `02:C112`、release `02:C306`。它们不是原厂 ABI 的替代空返回。

初版失败保留在 `tmp/np560-mp3-resident-pcm-20260907-v1`：hybrid 用 ACALL
调用 antialias 的 RETC 私有乘法 helper，二者却被放到不同 CS，实际从
`01:7AE4` 跳到缺失的 `01:229E`，正确 helper 在 `02:229E`。不是 CPU 指令
缺失，也不是返回栈损坏。修正为 antialias/hybrid/synthesis 三段代码同 CS
放置，并在两个调用者 builder 拒绝跨段依赖；不用改变 RETC 或插入 CPU 特判。
新镜像可重复重建到相同 SHA，错误的跨段配置在生成时即拒绝。

当前同一 QEMU `533dd1a4...`、同一 v2 ROM 的验证：

- `tmp/np560-mp3-resident-requant-20260907-v2/report.json`：10 组、9775 次
  scalar 调用通过，包括全部 8207 个有效索引、符号、指数、越界、溢出和 icount5；
  代码及所有分块表运行前后不变。该数字含重复边界检查，不代表 9775 首歌曲。
- `tmp/np560-mp3-resident-pcm-20260907-v2/report.json`：MPEG1 前两帧，原厂
  堆已有 16 KiB 锁定邻接对象，实际申请 38336 bytes；工作区 `DS0=A3:R3=0A4C`。
  10 次公开调用、83818 个状态/采样 word 校验通过，包含 reset、busy/empty、
  PCM、滤波历史、释放、邻接对象及低端播放器内存不变。4608 个 PCM16 值 SHA
  `51d9b2758c7c672abd18d8cadbd3473183994c3f3815642eb93538209259fe52`，
  与迁移前一致；对 FFmpeg 最大差 1、RMS 0.35843021946。诊断执行 13.07 秒，
  音频仅 0.0522 秒，**不是已达到实时播放**。
- `tmp/np560-mp3-resident-coldboot-20260907-v2/report.json`：未修改的完整 PRG
  和原 NAND，零输入冷启动 90.96 秒通过，末三次顶栏差异 0/5280；无 ROM 缺失、
  非法控制、未实现指令或 NAND error。不保存 NAND，不替换用户 Web 实例。

PCM 检查是隔离 caller，VMA03 的 PRG 起始 4 KiB 被测试入口替换，`3C:8000`
放输入/预期夹具，`4F:0000` 仅作为测试 PCM 记录区；所调用原厂堆函数在实际
链接地址，字节运行前后不变。**不能将这些测试夹具位置称为生产播放器内存所有权**。
真正冷启动的独立检查则没有上述 caller 或夹具覆盖。

MPEG2/2.5 的两帧 v1 检查已通过 guest 状态与输出核对，但离线 ffprobe 拒绝
过短片段，整体报告保留为 false。增加到三帧后的 v2 均通过 guest 和离线对照：

| 输入前缀与报告目录（`tmp/`） | 原厂堆条件 | 原始 PCM16 值数 / 实际对照值数 | PCM SHA256 |
| --- | --- | --- | --- |
| MPEG2，`np560-mp3-resident-mpeg2-20260907-v2` | 已锁定 20 KiB，工作区 `A3:1A4C` | 3456 / 2304 | `01355ba0caec1980b91d2d0e3ed14b7efd86bbecdc0cecb21f3b2d3212c62419` |
| MPEG2.5，`np560-mp3-resident-mpeg25-20260907-v2` | 空堆，工作区 `A3:0000`，icount5 | 1728 / 1152 | `9e61fe03759475726ca81cf62533a887f7244ea63cc2e4ad013d26be10f8a41e` |

两组最大差异均为 1；参考端均仅排除第一帧已验证零频谱/零 PCM 的 Info 元数据帧，
guest 原始 WAV 不裁剪。这里只验证各三帧前缀，不借用旧布局的整文件成功记录，
也不是所有 LSF-IS/mixed 合法码流已覆盖。离线工具报错现会保存 stderr 并让总报告失败，
不会把 guest 检查通过写成整项对照成功。
下一步仍是原厂输入环、帧消费、输出缓冲、错误/结束、回调及性能，非重建新测试平台。

2026-09-07 后续已新增实际输入环适配：原厂 word writer 与 header parser 在 guest
中接到本核心，不再由测试程序逐帧提供上下文；结果及未接入的原厂 ABI 范围见
[输入环适配记录](np560_mp3_ring_adapter.md)。4.16 的地址/哈希保留为上一阶段证据，
新加入 ring 组件后的整体布局使用该后续记录，不能混用入口地址。

## 5. 重建与下一步

```text
python scripts/build_np560_mp3_huffman.py --output tmp/new-mp3-core
python scripts/tests/test_np560_mp3_huffman.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-core-test
python scripts/tests/test_np560_mp3_huffman.py --qemu /path/to/qemu-system-dmcu --resident-rom /path/to/current-resident-rom.bin --output tmp/new-mp3-resident-entropy
python scripts/build_np560_mp3_sideinfo.py --output tmp/new-mp3-sideinfo
python scripts/build_np560_mp3_reservoir.py --output tmp/new-mp3-reservoir
python scripts/tests/test_np560_mp3_sideinfo.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-sideinfo-test --mp3 /path/to/existing.mp3
python scripts/tests/test_np560_mp3_reservoir.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-reservoir-test --mp3 /path/to/existing.mp3
python scripts/build_np560_mp3_spectrum.py --output tmp/new-mp3-front-end
python scripts/tests/test_np560_mp3_scalefactors.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-sf-test
python scripts/tests/test_np560_mp3_spectrum.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-spectrum-test --mp3 /path/to/existing.mp3
python scripts/tests/test_np560_mp3_spectrum.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-spectrum-errors --errors-only
python scripts/build_np560_mp3_frame.py --output tmp/new-mp3-frame-core
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-frames --mp3 /path/to/existing.mp3
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-recovery --mp3 /path/to/existing.mp3 --recovery
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-modes --modes
python scripts/build_np560_mp3_requantize.py --output tmp/new-mp3-requant
python scripts/tests/test_np560_mp3_requantize.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-requant-test
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-requant-chain --mp3 /path/to/existing.mp3 --requant
python scripts/build_np560_mp3_stereo.py --output tmp/new-mp3-stereo
python scripts/tests/test_np560_mp3_stereo.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-stereo-test
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-post-chain --mp3 /path/to/existing.mp3 --postprocess
python scripts/build_np560_mp3_intensity.py --output tmp/new-mp3-intensity
python scripts/tests/test_np560_mp3_intensity.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-intensity-test
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-is-chain --mp3 doc/sources/minimp3-vectors-20260907/l3-he_mode.bit --postprocess --post-start 50 --limit 70

python scripts/build_np560_mp3_antialias.py --output tmp/new-mp3-antialias
python scripts/tests/test_np560_mp3_antialias.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-antialias-test
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-antialias-chain --mp3 /path/to/existing.mp3 --antialias

python scripts/build_np560_mp3_hybrid.py --output tmp/new-mp3-hybrid
python scripts/tests/test_np560_mp3_hybrid.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-hybrid-test
python scripts/tests/test_np560_mp3_hybrid.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-hybrid-reference --reference-only
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-hybrid-chain --mp3 /path/to/existing.mp3 --hybrid

python scripts/build_np560_mp3_synthesis.py --output tmp/new-mp3-synthesis
python scripts/tests/test_np560_mp3_synthesis.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-synthesis-test
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-pcm --mp3 /path/to/existing.mp3 --pcm
python scripts/tests/test_np560_mp3_frame.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-pcm-offline-recheck --mp3 /path/to/existing.mp3 --pcm --recheck-pcm-from tmp/previous-mp3-pcm

python scripts/build_np560_mp3_decoder.py --output tmp/new-mp3-banked-decoder
python scripts/tests/test_np560_mp3_decoder.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-banked-pcm --mp3 /path/to/existing.mp3 --limit 8 --workspace-bank 0x30
python scripts/build_np560_mp3_allocation.py --output tmp/new-mp3-allocation
python scripts/tests/test_np560_mp3_allocation.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-allocation-test
python scripts/tests/test_np560_mp3_decoder.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-heap-pcm --mp3 /path/to/existing.mp3 --limit 2 --factory-heap --heap-prefix-bytes 0x2000
python scripts/tests/test_np560_mp3_decoder.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-offset-heap-pcm --mp3 /path/to/existing.mp3 --limit 2 --factory-heap --heap-prefix-bytes 0x5000
python scripts/tests/test_np560_mp3_decoder.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-offset-edge-pcm --mp3 /path/to/existing.mp3 --limit 2 --workspace-bank 0x34 --workspace-offset 0x1cfe --icount 5

python scripts/build_np560_mp3_resident.py --resident-rom tmp/np560-system-v380-vma03-resident-codec-holes-v1.bin --firmware "NP560+V3.80版系统升级程序/NP560.PRG" --output tmp/new-mp3-resident
python scripts/tests/test_np560_mp3_requantize.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-resident-rq --resident-bundle tmp/new-mp3-resident --scalars-only
python scripts/tests/test_np560_mp3_decoder.py --qemu /path/to/qemu-system-dmcu --output tmp/new-mp3-resident-pcm --mp3 /path/to/existing.mp3 --limit 3 --factory-heap --heap-prefix-bytes 0x4000 --resident-bundle tmp/new-mp3-resident
```

以上命令拒绝复用输出目录。测试使用现有 QEMU 运行环境；熵核心测试的 `--bits-only`
可单测公开位读取入口。侧信息/位储备的离线 C 参考需现有 gcc，源码及二进制只放新测试目录。
旧 ROM builder 只复用提取后的同一个标签解析器，未安装新解码核心或更改原厂入口。
front-end 构建命令汇集五个组件的八个 code/table 片段并保存地址、大小与 SHA 清单；
`tmp/np560-mp3-front-end-20260907-v1` 已重建并核对。它不是可启动 ROM，清单明确
`factory_rom_patch=false/end_to_end_frame_driver=false/pcm_produced=false`。

frame 构建另汇集六个组件的九个片段；`tmp/np560-mp3-frame-core-20260907-v1` 已生成，
清单明确 continuous_entropy_frame_driver=true、factory_rom_patch=false、pcm_produced=false。
加入重定标后的包为 `tmp/np560-mp3-frame-core-20260907-v3`，七个组件、十一个
code/table 片段，构建时检查片段互不重叠。`requantize_spectrum_available=true` 只表示
组件可调用，不表示 ROM 服务或 PCM 已完成。`--requant` 默认取前 8 个连续帧；
测试未改原厂头解析器，仍由只读夹具提供头几何参数及每帧 raw 输入位置。
加入 MS/重排后的包为 `tmp/np560-mp3-frame-core-20260907-v4`，八个组件、十二个
片段；同时明确 `ms_stereo_available=true/short_reorder_available=true/`
`intensity_stereo_available=false/pcm_produced=false`。独立 stereo 包只带代码和依赖表
地址/SHA，使用时须同时装载 requant 表；frame 汇集包已包含该依赖并检查无重叠。
加入 IS 后的包为 `tmp/np560-mp3-frame-core-20260907-v5`，九个组件、十四个片段，
`intensity_stereo_available=true`，仍为 `factory_rom_patch=false/pcm_produced=false`。
`--postprocess` 现在支持 MS/IS/组合模式；`--post-start` 必须非负且小于 `--limit`，
省略时保持从第 0 帧开始。它是诊断阶段选择，不是原厂播放器的跳转功能。
加入抗混叠后的包为 `tmp/np560-mp3-frame-core-20260907-v6`，十个组件、十六个片段，
构建检查互不重叠，`antialias_available=true/pcm_produced=false`。
`--antialias` 隐含 `--postprocess`，在原生重排后调用新组件；复用其描述符前四项，
结果状态另放 `0x23C0..23CF`，输出仍在原生 Q28 缓冲，不注入宿主滤波结果。
`--post-start` 现在也检查实际文件结束位置；它仍只适用于当前不带滤波历史的阶段。
加入混合滤波后的包为 `tmp/np560-mp3-frame-core-20260907-v7`，十一个组件、
十八个 code/table 片段且无重叠，`hybrid_available=true/hybrid_output_fracbits=23`。
仍为 `pcm_produced=false`，主 frame 入口依然是熵解码驱动，不冒充完整 PCM/原厂 ABI。
加入子带合成后的阶段包为 `tmp/np560-mp3-frame-core-20260907-v8`，十二个组件、
二十个互不重叠片段，`synthesis_available=true/synthesis_pcm_format=s16le`。
包构建本身不执行解码，因此其 `pcm_produced=false` 保留；实际运行的 PCM 证据见 4.11，
不把静态包能力标记混同于播放器实测。`complete_mp3_decoder=false/factory_rom_patch=false` 保留。
8080-byte 帧状态是保留完整中间结果的内部布局，尚非原厂工作区/缓冲 ABI；没有证明
整机可实时播放，不能把测试吞吐或代码尺寸当作恢复完整 MP3 的完成度。

下一步是 **原厂播放器接口与实时性能**，并统一
整条滤波链的动态范围，不能靠逐组件截断、固定成功或丢帧代替正确输出。
它们是本核心的真实上下游，不是重复原厂已存在的 MPEG 头解析器。
还须实现 CRC/跨帧使用范围冲突检查、原厂初始化、输入环读状态、双缓冲、回调、错误/结束语义及
低码率的共用处理服务；在此之前不安装空壳 `01:4804/49F8` 或声明播放器可用。

NPE 的 ESAC 类格式保持独立工作项，不用本 MP3 核心试图替换。用户实例、系统 ROM、
NAND 和 Web 未改动，也没有生成/播放假冒游戏声音的 PCM。
