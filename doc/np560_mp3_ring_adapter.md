# MP3 原厂输入环接入 resident 解码核心

日期：2026-09-07。上一阶段需要测试程序逐帧提供头字段和 bit context；本阶段
新增实际执行的 guest 流适配：原厂 `16:E844` 写入连续压缩 word，原厂 `16:E45E`
解析 guest 从环中取得的头，随后进入 resident Layer III 解码核心。
**尚未连接原厂 `01:4804/49F8` 公共入口和播放器音频双缓冲，不代表播放器可用。**

## 实现与所有权

`scripts/build_np560_mp3_ring.py` 当前生成 1726-byte DMCU 代码，包含新的内部
`reset / free_words / step` 接口，使用与 PCM 核心一致的 `DS0:R3` 已申请工作区。
新增私有字段只占工作区偏移 `0040..005F`；不是为原厂 RAM 空洞猜测字段。
压缩帧暂存复用核心 `SCRATCH` 的 2304-byte 区间，在原生重排使用它之前完成熵解码。
没有扩大工作区申请量，没有宿主帧解析代算或新造输入搬运服务。

`00:1000..15FF` 是已验证的实际输入环，原厂 writer 发布偶数游标到 `00:3340`。
该 writer 的 `XM0=0600` 循环访问保持原样。适配器保留独立 byte 读游标：

- 可用字节数是写/读游标在 1536-byte 环中的差，读游标允许为奇数。
- 可追加 word 数按 `766 - ceil(可用字节/2)` 计算，保留原厂 consumer 使用的
  `02FE` 容量界限；未读的半个 word 仍占一个槽。它是有 consumer 依据的重建，
  不声称取得了原厂内部实现或原始读游标地址。
- 只有完整帧可用才复制、消费、解码；缺数据不推进读游标、不发布新 PCM。
- 奇数字节帧末尾的下一字节留给下一帧；MPEG1 第二个 granule 只处理原生 pending
  状态，不再次消费压缩输入。按实际消费量和之前的半 word 余量增加已核对的
  `3350/3352` 高/低 word 位置，保留原厂设置的文件起点；`33E4` 取实际 parser
  输出的 bitrate，不填固定码率。下节记录初版覆盖 seek 起点的问题及修复。
- 帧头字段来自原厂 parser。该函数不负责原始 byte stream 的同步字扫描，故适配器
  自行检查 11-bit sync；拒绝头时跳过一个实际字节并清滤波历史。
- 保护帧的 CRC 使用 `8005` 多项式、初值 `FFFF`，覆盖 header low16 和 side info。
  不把 `51:25D5` 错当 CRC 标志；保护位取原始 header。CRC 错误不输出 PCM，
  不推进输入，交由未来原厂错误/重试封装决定处理。不是完整错误恢复已接通。
- rate/channel 几何改变会清旧滤波历史，设置私有 `FORMAT_CHANGE`；原厂采样率回调
  尚未连接。VBR 仅码率变化不作为滤波格式重置。

新内部返回：`step` 成功为 `R0=576/R2=0`；无完整输入为 `0/1`；非法状态为
`0/2`；拒绝同步/头为 `0/3`；尚不支持的 Layer 为 `0/4`；CRC 错误为 `0/5`；
核心处理错误为 `0/6`，保留 subordinate status。**这些不是推定出的原厂 49F8
错误码**；原厂 `R0 bit0/3346`、输出指针、回调与错误恢复映射仍必须封装。

## 镜像与执行证据

初版环接入的基线 ROM：`tmp/np560-mp3-ring-core-20260907-v4/resident.bin`，SHA256
`789eb4caa3a2edf8baecb73ebd610fbef8e4be6687e9ead8b9612a437fd56251`。
新组件入口 reset `02:7130`、free_words `02:724E`、step `02:72A8`，代码 SHA
`db9234d99986776b0056db22c767f07c72167504bfbcdf9aa81579931225800f`。
15 个组件、34 个片段共 81620 bytes，已保护范围内余 25096 bytes；原厂已知入口
仍保留，不在这里安装空壳 `4804/49F8`。沿用 QEMU `533dd1a4...`，本阶段未改 CPU。

真实连续输入检查使用 `scripts/test_np560_mp3_ring.py`。每个 QEMU 只运行一个
诊断 caller：通过原厂堆申请/锁定工作区，按不同长度 word 块调用原始 writer，
每次检查 free、读写游标、消费位置与实际 PCM，最后释放真实句柄、检查邻接对象
及原厂空闲链。测试程序不提供每帧 header 几何或 bit context，不向运行中 RAM 写入。

| 输入与最终报告目录（`tmp/`） | 覆盖前缀 / 堆条件 / 起始环位置 | 原始 PCM16 值 / 离线对照值 | PCM SHA256 |
| --- | --- | --- | --- |
| `np560-mp3-ring-stream-20260907-v2` | MPEG1 前 6 帧；已有 16 KiB 锁定对象；`15FC` | 13824 / 13824 | `e6f64b140668c62cb987460589f42186d0b8d7b51a61ae17133bc8151439b484` |
| `np560-mp3-ring-mpeg2-20260907-v2` | MPEG2 前 3 帧；已有 20 KiB 锁定对象；`1000` | 3456 / 2304 | `01355ba0caec1980b91d2d0e3ed14b7efd86bbecdc0cecb21f3b2d3212c62419` |
| `np560-mp3-ring-mpeg25-20260907-v2` | MPEG2.5 前 3 帧；空堆；`15FE`；icount5 | 1728 / 1152 | `9e61fe03759475726ca81cf62533a887f7244ea63cc2e4ad013d26be10f8a41e` |

最终 v2 报告三组均通过，QEMU 正常退出 0，最大差异均为 1 PCM16
单位；LSF 对照仅按可核对 packet 位置排除首个零 Info 帧，guest WAV 不裁剪。
MPEG1 包含 41 次写入/处理事件、14 次真实 writer 调用、12 个输出 granule，
消费 2507 bytes，输入共 2508 bytes，实际经过两次环尾。该有限前缀不证明整文件
或所有码流正确，更不是实时播放（初次六帧诊断约 40.65 秒，声音仅 0.1567 秒）。

早期 v1 输入夹具在奇数前缀末尾附了一个仅用于凑 word 的零字节；该字节不属于已
处理帧，也未被消费。最终 v2 改为读取原文件中下一帧的真实首字节，避免夹具凭空
提供数据。真正文件 EOF 的部分 word 与结束语义尚未集成，不能以本前缀实验替代。

控制检查 `tmp/np560-mp3-ring-control-20260907-v1/report.json` 已通过：普通与
icount5 各 12 个场景，共 24 项。覆盖部分 header/保护帧、有效 CRC、坏 CRC 不
消费、MPEG1 pending、不完整末 word、同步失配跳过一字节、满环保留量、奇数读
游标尚占槽、非法读/写游标及字节计数低 word 进位到原厂消费位置。全部正常退出，
SP 恢复；guest 解出的 CRC 合法零频谱帧 PCM 为零。它是控制用压缩测试帧，
不是伪造真实音乐/NPE 声音。CRC 预期由既有 libmad `bit.c` 的 byte-table 实现
独立计算，不复制 guest 的 bit-loop 作为 oracle。计数种子是隔离 caller 自行设置，
不是宿主注入，也不是生产接口。

冷启动 `tmp/np560-mp3-ring-coldboot-20260907-v1/report.json` 已通过：使用未修改
完整 PRG、同一 v4 ROM 和原 NAND；末三次顶栏均为 0/5280 像素差异，无缺失 ROM、
非法控制、未实现指令或 NAND error。已目视最终桌面；不使用上述诊断 caller、
源数据或预期夹具，不保存 NAND，不替换用户 Web 实例。

## 原厂 seek 起点：已复现并修正的集成错误

原始 `1D:377C` 调用 `01:485A` 后，在 `3784..3796` 将文件 byte 位置
`51:25B8/25BA` 右移一位，写入 `00:3350/3352`。初版环适配只验证了零起点，
每次 commit 都用私有相对 byte 总量覆盖这两个 word，因此会丢掉原厂设置的 seek
起点。这是新适配器的错误，不是原厂代码或 CPU 指令缺陷。

修复后，commit 采用 `floor((旧相对 byte 计数的奇偶位 + 本次消费 bytes)/2)`
作为 word 增量，加到原厂发布的完整 32-bit word 位置；私有 byte 计数仅记录
当前 reset 以来的相对消费量。这样不丢 seek 起点或 word 位置最高位，也正确保留
奇数字节帧的半 word。pending granule 不修改位置；reset 清空计数和 pending，
然后允许原厂调用者重新设置起点。尚未因此证明 UI 快进/跳转已工作。

当前 ROM：`tmp/np560-mp3-ring-seek-core-20260907-v1/resident.bin`，SHA256
`121999025f99743b535650e22d6f5c38717206ac42d112c8700791e43732a18c`。
环代码 1726 bytes，SHA256
`f568447634f412874b9888243e8f70ec939b801129cce69139cc4d0c995415b7`；
重新链接后入口为 reset `02:1EE6`、free_words `02:2004`、step `02:205E`。
15 个组件、34 个片段共 81630 bytes，余 25086 bytes。仍不改原 PRG、QEMU 或
原厂缺失公共入口；其它组件地址也可能随打包改变，必须使用本次 manifest。

证据目录均在 `tmp/`：

- `np560-mp3-ring-seek-before-20260907-v1`：新增检查先运行旧 v4 ROM，确实失败；
  原厂预置 `8123:FF80` words，第一帧后旧代码错误返回 `0000:00D0`，而非
  `8124:0050`，pending 和下一帧也继续错误。失败原件保留。
- `np560-mp3-ring-seek-control-20260907-v1`：新 ROM 普通及 icount5 各 16 项，
  共 32 项通过。新增非零起点/低 word 进位、pending 不推进、两个 417-byte
  帧分别推进 208/209 words、reset 清除起点与 pending；既有 CRC/环边界仍通过。
  高位起点是检查整数宽度的控制向量，不表示真机支持对应大小的 MP3 文件。
- `np560-mp3-ring-seek-pcm-20260907-v1`：真实 MPEG1 六帧，输出 SHA 仍为
  `e6f64b140668c62cb987460589f42186d0b8d7b51a61ae17133bc8151439b484`。
- `np560-mp3-ring-seek-mpeg2-20260907-v1`、`np560-mp3-ring-seek-mpeg25-20260907-v1`：
  分别三帧，PCM SHA 与上表原基线一致。三组对独立参考的最大差异仍为 1；
  范围、Info 帧处理和非实时限制不变。全部隔离 QEMU 正常退出 0。

## 保留的失败与下一实现项

- `np560-mp3-ring-pcm-20260907-v1` 在启动 QEMU 前因预期负 PCM 值未转成
  u16 打包失败。已修正测试编码，未改变采样数值；不计为运行通过。
- `np560-mp3-ring-pcm-20260907-v2` 实际误返回 unsupported-layer。header 已
  正确读到 `FFFB/9064`，错误在把原厂两个 byte 字段当宿主 little-endian word
  拆分。改用已验证的原生 byte load 读取 `25C8/25C9`，未改 parser/CPU/原始资料。
  v3 的两帧原厂 writer→parser→PCM 链随后通过，与先前 PCM 相同。

后续已实现独立拥有的 [session 状态对象与四缓冲交接](np560_mp3_session.md)，
含实际 heap lease、复位和释放；这不是原厂单例入口已经绑定。
下一步把 `4804/485A/49BE/49F8/4954` 的原厂所有者和公共 ABI 接上，再接 DTU/DAC，
实现 callback、错误/EOF/seek 与采样率变化，优化实时吞吐。Layer II、跨帧 main-data
范围冲突、完整 CRC 错误恢复以及低码率共用服务仍保留为未完成项。NPE ESAC 仍独立。

重建/复核命令：

```text
python scripts/build_np560_mp3_resident.py --resident-rom tmp/np560-system-v380-vma03-resident-codec-holes-v1.bin --firmware "NP560+V3.80版系统升级程序/NP560.PRG" --output tmp/new-ring-core
python scripts/test_np560_mp3_ring.py --qemu /path/to/qemu-system-dmcu --mp3 /path/to/input.mp3 --resident-bundle tmp/new-ring-core --output tmp/new-ring-test --limit 6
python scripts/test_np560_mp3_ring_control.py --qemu /path/to/qemu-system-dmcu --resident-bundle tmp/new-ring-core --output tmp/new-ring-control
```
