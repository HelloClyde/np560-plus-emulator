# MP3 测试码流来源

2026-09-07 通过 GitHub API 将 [lieff/minimp3](https://github.com/lieff/minimp3)
的 master 解析为固定提交 `ea99364f61c14656440e8d77e9c233ccf3124633`，之后按该
提交取得下列文件。没有执行仓库程序，没有把它编译为宿主实时解码器。

| 文件 | bytes | SHA256 |
| --- | ---: | --- |
| `l3-he_mode.bit` | 53498 | `fb90396d9bb13311be35284d061e19196830d213d823e05297b18172c88d90ce` |
| `M2L3_compl24.bit` | 81408 | `856df786497a394091212086edbb77cc5f5c5572f0381f96be4273d2a7dccabf` |
| `README.upstream.md` | 13929 | `ce8a219c5783d7b991070a7aca4c31f8dfcafc183925bf947b80b835ed36b45d` |
| `LICENSE.upstream` | 6556 | `6a1ee543e5282cd9061881edf462e6fdab181f328da71fc2c9a6950a80e94d01` |

原始 URL：`https://raw.githubusercontent.com/lieff/minimp3/<commit>/vectors/<name>`，
README/许可证则在仓库根目录。上游提供 CC0 1.0 声明，原件保留；测试码流是否含
第三方标准素材的独立权利未另行确认，不把上游许可等同于取得诺亚舟素材授权。

本地解析实况：`l3-he_mode.bit` 共 128 帧，先 10 帧单声道、30 帧非 joint 双声道、
10 帧 MS，再交替 IS/MS+IS，每组 10 帧，最后 18 帧单声道。第 50–59 帧为 IS，
60–69 为 MS+IS。本次在一个 QEMU 中原生运行前 70 帧，50–69 帧接通 Q28/joint/
重排，先前 50 帧仅原生熵解码用于建立历史。未下载/播放上游 PCM，也未完成标准
PCM 音质对照；上游 README 的符合性成绩不是本项目的测试结果。

`M2L3_compl24.bit` 经头字段检查共 212 帧，全部单声道，故**不能作为 LSF-IS
样本证据**，本次未用于 native IS 整链测试。LSF-IS 真实文件验证仍待补。
详情见 [MP3 guest 核心 4.8](../../np560_mp3_guest_decoder.md)。
