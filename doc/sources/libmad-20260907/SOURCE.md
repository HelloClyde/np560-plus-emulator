# libmad：MP3 重建实现的公开算法参考

获取日期：2026-09-07。来源为 [sezero/libmad](https://github.com/sezero/libmad)，
该仓库说明为从官方发行版生成的 fork；不称作诺亚舟代码或原厂 ROM。
通过 GitHub commits API 解析 `master`，再按固定 commit 下载，未执行下载内容：

`486f902c6c686eafced3450851849527e29bc7f6`

原件 URL 形式：`https://raw.githubusercontent.com/sezero/libmad/<commit>/<filename>`。
本目录 `README`、`COPYING` 都是未修改原件；本文件是本地来源说明。

| 原件 | bytes | SHA-256 |
| --- | ---: | --- |
| README | 10367 | 7bfc051a5529405510546ca3790549496f7cbf8e88f49945b90ba12cdf10d005 |
| COPYING | 17992 | 32b1062f7da84967e7019d01ab805935caa7ab7321a7ced0e30ebe75e5df1670 |
| bit.c | 6884 | 87aa161268a4736eff10b6423f6a6d63cfbbe484fa62ea29c046841491b280b5 |
| bit.h | 1613 | 7d135068237a85b616764f6ccbee0a91e63c7fe4f480177372cb16952824d05f |
| huffman.c | 73174 | ab7bbad837fda91d8382b936d86c53cb8f415404f20da568294fe099730a5c22 |
| huffman.h | 1862 | ec68be8bb2e0fe260c620dfd4e9cf59b0007d954e4df07a3bd8f86f00fb6597c |
| layer3.c | 72682 | 2da2e4b9176b5935259d3cc032253a9f514309c339770874bc0873413d55cb11 |
| fixed.h | 14855 | 0b2ed91b612e95c66d3ca2be7ecd0dcbcb2c461a6e511fad3c7ce267dc31a9f7 |
| rq_table.dat | 485879 | 125186cf44544395db737348bec72f67d7a234f207b9992ed90c4fa4fecaf4e7 |
| imdct_s.dat | 2591 | 492893124349428a04a9ac363834f8050372367e91d6e523ba8532d701614a20 |
| synth.c | 24366 | c7a49ee84744f3d6a7ef2fa5be69bfc3d65056b9748fc58978843df0deafd5f5 |
| D.dat | 26473 | 3d12dec8a4e0afd1cdfa78b9e8db598196259feb0e65511f494532381202588d |

原件声明 Copyright (C) 2000–2004 Underbit Technologies, Inc.，GPL version 2
或更新版本。保留源码声明与 `COPYING`；新 DMCU 核心及测试按 GPL-2.0-or-later 标注。

选择依据是 README 明确的 32-bit 定点运算实现，可供 DMCU 的 16-bit 寄存器对和 DSP
移植参考；不代表可直接把 C 编译到 DMCU，也不证明其数值舍入或时序等同原厂 ROM。
目前没有编译或链接这套 libmad 到 QEMU，也没有通过它播放用户文件。

本次实际用途：

- `bit.c` 的 UIMSBF 位流规则与 `layer3.c` 的 linbits/sign 次序作为算法依据。
- 测试独立展开 `huffman.c` 的多位查表结构，与已有 FFmpeg 长度/符号表产生的全部
  码字、linbits 逐项比较。FFmpeg 原件及其 LGPL 许可证保留在相邻来源目录。
- DMCU 指令由本项目生成，guest 读取码表并自行解码，宿主只做构建和离线校验。
- 后续从同一固定 commit 取得 `rq_table.dat`，用于 8207 项 `x^(4/3)` 常量，
  原件保留 GPL 声明；重新打包为 DMCU 32-bit 记录，不生成所谓“原厂解码表”。
  `layer3.c` 的缩放表达式、pretab 和七个分数次幂常量也进入原生重定标实现。
  离线 C 参考显式加宽中间量以避免最终可表示的值被提前截断，并单独检查最终 Q28
  范围；另有浮点公式交叉检查。不能把该改进描述为与未经修改的 libmad 全边界位一致。

- 后续 MS 立体声使用 `III_stereo` 的 Q28 `1/sqrt(2)` 常量/公式。DMCU 及离线参考
  都显式加宽中间乘积和求和/求差，最终检查有符号范围；不是直接执行原函数的窄整数行为。
  随后 `is_table` / `is_lsf_table` 的 69 组系数进入原生 IS/组合立体声实现。
  离线 `III_stereo` 参考明确适配了原量化非零边界、8 kHz mixed 长前缀、加宽 MS
  运算及最高带 SF/mask 继承；不是原函数全边界原样位一致。末带规则选择与其它
  库的差异继续记录，仍须完整 PCM 符合性核验。

- `cs[8]/ca[8]` 后续用于原生抗混叠，四个 64-bit 乘积在和/差后统一 Q28 右移。
  离线参考保留 `III_aliasreduce` 原函数文本，但明确加宽样本和乘加类型、改变宏的
  舍入/溢出处理；不是原版 `fixed.h` 全位一致。8 kHz mixed 依据 72 项长前缀处理
  三处内部边界，而非原库固定的 36 项调用；该扩展仍须完整 PCM 核验。

- IMDCT 阶段从同一 commit 另取得 `imdct_s.dat` 原件。原函数的长短窗口、相位、
  重叠与频率反转规则为算法依据；新 guest 采用融合窗口的 Q28 矩阵、64-bit 点积
  和 Q23 时域样本，明确不是原厂/原 libmad 定点舍入。
  离线提取 `fastsdct/sdctII/dctIV/imdct36/III_imdct_l/III_imdct_s` 函数及原系数，
  将数值类型/乘法替换为 long double，系数 enum 改为浮点常量声明，短输入作布局
  转换，独立交叉检查新实现的相位、比例和窗口；没有链接宿主实时播放器。

- 合成阶段从同一 commit 取得 `synth.c` / `D.dat`。`D.dat` 重排为完整 512 项
  Q16 窗口，逐项与固定 FFmpeg 半窗口独立展开的结果核对；guest 使用 32 行独立
  余弦矩阵、精确对称补全、每声道 V1024 环历史和最终 PCM16 舍入/限幅。
  离线另提取原 `dct32/synth_full`，数值及乘加宏改为 long double，保留原 DCT
  拓扑、D 常量和交替历史结构；与独立 64 行数学公式一起核验新 guest 结果。
  明确不是原版 libmad 定点逐位一致，亦未将它链接到 QEMU 或 Web 播放路径。

已实现连续熵解码、定点频谱、MS/IS、重排、抗混叠、时域混合滤波及 PCM16 合成组件，原厂播放器接口尚未完成；
细节见 [guest 解码核心](../../audio/np560_mp3_guest_decoder.md)。
