# NoahMediaMaker 1.07.0711 候选音频实现来源

取得日期：2026-09-07。用途：静态查找 NP560+ 内容制作时采用的声音算法。
**取得了软件包，尚未取得经验证可用于 NP560+ 的解码实现。**

## 原始材料与完整性

- 发现页：[ZOL 多媒体列表](https://xiazai.zol.com.cn/download_cate_media/media_free_226.html)。
  原始 HTML 保存在本目录 `zol-list.html`。
- 列表中的对应产品页是 `https://xiazai.zol.com.cn/detail/48/470886.shtml`，未另行读取。
- 原包地址：[NoahMediaMaker.zip](https://down10.zol.com.cn/20190605/NoahMediaMaker.zip)。
  从列表脚本中已有的 `downurl` 参数取得，不使用捆绑下载助手。
- 本目录 `NoahMediaMaker.zip`：8,379,478 bytes；HTTP 200；SHA-256：
  `b7171bd19658e78aea8e60b04ee935b79ba78292a054d542a2b78801e44339e5`。
- Python `zipfile.testzip()` 返回 `None`，44 个成员均可读取、CRC 通过。
  CRC 仅验证本压缩包的内部完整性，不证明原厂签名或发布身份。
- ZIP 中既有 2006/2007 的程序时间，也有 2013 年的安装日志、配置和目录时间；
  因而应视为第三方保存/再打包版本，不能称为原厂未改动安装介质。

此前尝试 PC 下载网普通下载链接，返回错误页面；多特列表的
`https://qn2.runjiapp.com/NoahMediaMaker.zip` 返回 HTTP 403。
这两个地址没有取得软件包，不需要重复尝试或绕过访问限制。

## 已提取并核对的成员

静态分析副本位于 `tmp/np560-noahmedia-static-20260907-v1/`，文件名追加 `.bin`。
未加载、注册、安装或运行任何 EXE/DLL；仅解压字节、读取字符串及用 `objdump` 读取 PE 元数据。

| ZIP 内 `NoahMediaMaker/` 成员 | 大小 bytes | SHA-256 |
| --- | ---: | --- |
| AudioCtl.dll | 558080 | d208f8465e4c86cd7c6139a5a26cc0b0cd01013a462af0ee9a0692db8f3379db |
| Compile.dll | 508416 | 4287f1b6608eb708ca67c0ff7b0957c5d7cd1a89bc3c4855659359f5b8eb200a |
| MRC2PCM.DLL | 116736 | 8091a729595840606c3ad12a68f0655e657bda1ca46a6d876b0677c7fae66909 |
| NED.DLL | 29696 | f50d08dc0aa380a3eacba85120affb6f2d1184dc2c291d9cde6310f7a15f6dec |
| SonixCodec.dll | 162816 | 52a621c7c3c5bcd1ca851b3a028b1d4d1e171959887ca49974b3b714590e5eea |
| NoahMediaMaker.exe | 4125696 | 7d5eeebb32556441bc6e2b5a757f751084768455038990132a76195a7c0a0c49 |
| cBIN2MD4.dll | 28672 | a3221e7cae8f0e6d5f52035d0bf16d11ab36e8f37af5b79c90b140926f1bd059 |

## 静态证据及边界

- 主 EXE 的未压缩字符串含 `NP560+`、`NP560T`、`TNPSetConst_NP560A`、
  `TNPSetConst_NP560T`。这比下载页只提 NP960 更接近目标，但仍须追到实际机型分支。
- `AudioCtl.dll` 的节名为 `UPX0/UPX1/.rsrc`，仅导出 COM DLL 的五个标准入口。
  压缩数据中的零散字符串不能当作完整代码/算法清单；尚未静态解包。
- `Compile.dll` 导出 `CompileScript`，有 `.aspack/.adata` 节；可见字符串包括
  `SitronixBRCGetEncodeStatus`、`SitronixSoundLib.dll`、`SonixStartCodec` 和 `SonixCodec.dll`。
  包中没有名为 `SitronixSoundLib.dll` 的成员。尚未证明 NP560+ 选择哪条分支。
- `SonixCodec.dll` 也有 `.aspack` 节，导出 `SonixEnableDecoder`、`SonixGetStatus`、
  `SonixStartCodec`、`SonixStopCodec`；可见 Sonix Wavetool/MRC 标识。
  不能因它是音频库就认作 CYBIT ESAC-4。
- `MRC2PCM.DLL` 的导出目录内名称是 `SonixCodec.dll`，唯一导出是
  `SonixDecFrame`（RVA `C3A0`）。**更正：这是该 DLL 自身的导出，不是对另一个
  SonixCodec.dll 的导入。** 先前仅凭字符串推测版本/选配问题的判断撤回。
  同日静态解包后已核对该入口；尚未证明它与 NP560+ 的 NPE 音轨兼容。
- `NED.DLL` 实际只导出 `Encrypt/Decrypt`，不能把名字中的 ED 推成音频编解码。
- `PHC.dll` 可见 CxImage/JPEG/TIFF 等图像处理符号；不是当前优先的声音线索。

下一步先静态解包 `AudioCtl.dll`，结合主 EXE 的 NP560+ 配置分支核对实际声音格式；
必要时再处理 `Compile.dll` 的压缩。不要直接执行旧软件或给模拟器接入宿主 DLL。
只有确认算法、帧契约并由原始 NPE 在 guest 内解码后，才进入声音恢复验证。

本次未改 QEMU、resident ROM、NAND 或 Web；MP3/NPE 实际播放仍未恢复。

后续同日已完成 AudioCtl、Compile 静态解包；NP560+ 分组与声音写入阶段的核对见
[音频路径记录](../../audio/np560_noahmedia_audio_path.md)。以上“尚未解包”保留为取得时状态，
后续以该路径记录为准，仍没有取得经验证的目标 ESAC 解码器。

同日补充：`MRC2PCM.DLL` 也已静态展开，结果 `MRC2PCM.rva.bin` 为 221,184 bytes，
SHA-256 `1325c42e391886a07294b8b7189978187264a90d0404626ba2cef5b8c4661b5d`。
它是未重建 IAT 的 RVA 数据镜像，不是可运行 PE。导出、格式分派和原始 NPE
音轨头的比较见上述路径记录第 6 节；没有加载或执行该 DLL，也没有恢复声音。
