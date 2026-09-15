# ELAN eSL 声音来源检查

获取日期：2026-09-07。仅只读查找和规格核对，没有执行第三方安装程序。

## 已取得原件

- 文件：`esl-series-v1.7.pdf`
- 来源：<https://datasheet4u.com/pdf/1135353/eSL128.pdf>
- 363,258 bytes，21 页。
- SHA-256：`21b064b25bdc4582f1267457788a0f19410a7bb0ea57db5edb0a2c2cd0fcc338`
- 署名：ELAN MICROELECTRONICS CORP.，eSL Series Product Specification V1.7，
  2009-10-15；取得的是第三方保存的原厂文档镜像，不是原厂签名校验的软件包。
- 完整检查 PDF 第 10、11 页（印刷页 6、7）的算法表及脚注；提取文本后以 PDFium
  渲染核对表格合并单元格。没有修改或重新导出原 PDF。

表只给普通型号的若干码率及高级型号的范围，没有 ESAC-4 位流规范、源码或实现位置。
普通型号与高级型号的列不能混用；原表高级型号一列重复写 `eSL256A*`，保持原件，
不自行把它修订为另一个型号。该资料不证明 NP560 使用 ELAN 芯片。

## 只读页面线索与未取得的内容

- IDE 手册 HTML 转录：
  <https://manualzilla.com/doc/7447844/elan-esls-series-user-s-guide>
  原厂署名，Doc V1.8，Nov 2007。印刷页 42、43 描述编码类型设置与 PC/ICE 预听。
  已读转录，没有取得该手册 PDF；直接保存 HTML 返回 403，未绕过限制。
- 现行官方工具页：
  <https://www.emc.com.tw/emc/cn/Product/Product/SupportTools>
  可读 eSIDE 介绍，所读页面没有直接安装包链接；不把现行 eSIDE 与旧 eSL/eAM IDE
  视为同一个版本或相同的算法包。
- 历史授权检索线索：
  <https://www.emc.com.tw/upload/2018_11_29%280_0%29b2/2007_twn.pdf>
  搜索摘录包含 CYBIT/ESAC；本轮未取得、未完整核对该财报，不将摘录作为
  NP560 与 eSL 解码兼容性的证明。
- 另一个公开规格镜像 V0.7（2006-06）可由网页工具读取：
  <https://www.electronicsdatasheets.com/download/534cf559e34e2406135f4574.pdf?format=pdf>
  不作为已保存原件或精确算法来源。

Wayback CDX 的一次 eSL/eSIDE/EzWave 过滤查询 20 秒超时；没有下载任务仍在运行，
没有以失败响应断言全站从未提供软件。GitHub 的 `eSLMSMacroDefine` 与 `ESAC4`
查询未提供相关代码。安装包、算法库及与原始 NPE 对照的压缩样本均未取得。

后续以实际包/库/规范为新证据门槛，不重复相同关键词搜索或再次下载同型号规格副本。
