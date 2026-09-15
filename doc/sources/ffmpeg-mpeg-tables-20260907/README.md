# MPEG 表查找参考原件

2026-09-07 从 FFmpeg 官方仓库取得，原文件未修改。最初用于数值指纹比对，随后
MPEG 公共表也用于生成 DMCU 原生查表数据；新增固定版本 template 的区域初始化
函数被机械摘取，在宿主离线执行作独立对照，不链接到 QEMU 或替代 guest 解码。
未把完整 FFmpeg 解码器接入模拟器。前两个来源 URL 使用 master，复现以如下 SHA256
锁定的本地内容为准；扫描器会拒绝内容不同的参考文件。

| 文件 | 官方来源 | SHA256 |
| --- | --- | --- |
| mpegaudiodec_common.c | [FFmpeg 原件](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavcodec/mpegaudiodec_common.c) | `e6a415c3c47670217b49a97ca71adbbed4d98433d852e276539293465cb67151` |
| mpegaudiodsp_data.c | [FFmpeg 原件](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavcodec/mpegaudiodsp_data.c) | `b4c590d2bc880017cdda8c857f4340274449f4749c992f1d1cef785f9196d7a8` |
| mpegaudiodec_template-n8.0.c | [FFmpeg n8.0 原件](https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0/libavcodec/mpegaudiodec_template.c) | `28f16d27ded3558280edf3b4e7e141a004082630b3df97f37222ee0bf8b60293` |

保留文件头版权声明及同仓库 `COPYING.LGPLv2.1`。原件属于第三方参考资料，
不是诺亚舟或骏亿发布的源码，不能据此宣称找到原厂 mask ROM。

后续 `test_np560_mp3_stereo.py` 从同一 n8.0 template 机械提取
`compute_band_indexes`、`reorder_block`，保留算法离线执行，验证 DMCU 的短块重排。
包含 8 kHz mixed 的 72 项长块前缀；源代码自身仍标注需要该模式样本，不能将规则
对照等同于原厂实播或完整 MP3 标准符合性证明。该 C 参考不链接到 QEMU。
