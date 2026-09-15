# CyberVoice 旧版程序来源与完整性边界

取得日期：2026-09-07。来源是 Cybernetics InfoTech 官方历史网页，不是诺亚舟 SDK 或 mask ROM。
全部操作仅下载、解压与静态分析；没有运行安装程序、播放器、邮件程序，未联系厂商或购买授权。

## 官方网页原件

| 文件 | 最终归档 URL | SHA-256 |
| --- | --- | --- |
| cbvmail.htm | https://web.archive.org/web/20001027074229id_/http://www.cybit.com:80/cbvmail.htm | c274b6167e30059531a8a077317c44882a10aea2a44affade0634fff728ca83f |
| Core_Tech.htm | https://web.archive.org/web/20001018000055id_/http://www.cybit.com/Core_Tech.htm | 1fbdac7c078ef4cc79f83a6c5d9c68722ee4d0070f747069934d2a3664274908 |
| Internet_Software.htm | https://web.archive.org/web/20001208191500id_/http://www.cybit.com/Internet_Software.htm | 0bf7bc64b31543b54f17498b211330bd70e9cf825215f2940a86be5015006b9c |
| Licensing.htm | https://web.archive.org/web/20010127155300id_/http://www.cybit.com/Licensing.htm | 0e47d68236982f3e383b2da1bf7bdacac71406e238bd3ad10da1bead683943a0 |

`cbvmail.htm` 直接提供 `download/CyberVoicetrial.zip` 试用下载链接。
Core_Tech 页面说明存在 DOS coder 评估程序，但获取方式为联系厂商；没有取得该评估程序。
`Int_Productlist.htm` 链接此次由 Wayback 返回未归档；不是已检查该清单内容。

## ZIP 截断与内部成员校验

精确归档 URL：
https://web.archive.org/web/20001009115738id_/http://www.cybit.com:80/download/CyberVoicetrial.zip

响应头给出原 ZIP 长度 **1277923 bytes**，原修改日期 2000-09-13。
正常 GET 两次都提前结束，缺 **229606 bytes**。`Range: bytes=0-1048316`
得到 HTTP 206 和 **1048317 bytes**；后段 range 虽报 206，正文为 0 bytes 并发生 curl error 18。
较晚日期的 availability 查询仍指向同一快照。不能确定截断发生在归档存储还是当前传输层。
这里保留的是前缀 `CyberVoicetrial.prefix.bin`，不是完整 ZIP：

`a8a833868e5eb6699bc67e7e3443396bb4578926ca6bc6ee39883180bf692580`

外层 ZIP 只有一个 `setuptrial.EXE`，声明解压长度 1284666 bytes；现可解出其前 1055043 bytes。
外层 DEFLATE 未到 EOF，ZIP 中央目录和整体 CRC **均未验证**。

该 EXE 的 Wise 数据段由独立 raw-DEFLATE 成员与紧接其后的 little-endian CRC32 组成。
从已观察的 `0x38C1` 连续解析，得到 **19 个完整且各自 CRC32 相符**的成员；
在 EXE 偏移 `0x947D5` 遇到下一个不完整成员，未将该成员的前缀保存为完整文件。
独立 CRC 仅证明这些成员与容器内记录一致，不代表整个安装包或软件供应链签名认证通过。

| 保存的完整成员 | 识别依据 | SHA-256 |
| --- | --- | --- |
| member-13-0002b1ce.bin | Wise 文件清单顺序对应 CBVMail.exe；569344 bytes | 94f5921acbef67700f85ce57a2536228f64e5e2bec48b591935c8606862937e7 |
| member-15-0006fb91.bin | Cbvmail.hlp 帮助内容；172930 bytes | 020f304fccc01965beb065cdeb05a7aab0e1bd1af878b7675f043bc4c57e6d17 |
| member-16-00077c23.bin | PE 版本资源 OriginalFilename=CBVPlayer.EXE；233984 bytes | e20d6097cc31c2cdc3f9c6961386c609fd8aa147c0c14145cb83c96e8d4ec7eb |

文件保持 `.bin` 扩展名供分析，未安装到系统。`report.json` 保留全部成员的偏移、CRC、SHA；
其它成员仍在 `tmp/np560-cybervoice-members-20260907-v1/`，本目录只保留有关声音的三项。
报告的 `source` 字段是首次提取时的原 tmp 路径；本目录前缀是同哈希的只读来源副本。

用仓库脚本重建到一个不存在的新目录：

```powershell
python scripts/extract_np560_cybervoice_evidence.py doc/sources/cybervoice-2000-20260907/CyberVoicetrial.prefix.bin tmp/cybervoice-reextract
```

脚本锁定前缀 SHA，仅保存完整且 CRC 匹配的成员，不使用安装脚本中的目标路径或执行其指令。
分析结论见 [旧版解码器边界](../../np560_cybervoice_decoder_source.md)。
