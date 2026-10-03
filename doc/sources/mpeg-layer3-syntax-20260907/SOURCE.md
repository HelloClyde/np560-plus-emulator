# Layer III 技术说明来源

2026-09-07 读取并保存 [MPEG-Layer3 Bitstream Syntax and Decoding](https://mp3guessenc.sourceforge.io/MPEG%20Layer3%20Bitstream%20Syntax%20and%20Decoding.pdf)。
作者 Martin Sieler、Ralph Sperschneider，Issue 1.2，1997-03-04；83 页，372133 bytes。
SHA256：`9bca5f486a71ab159db1270901357b2a20d0c3a8c02c4ac521f8bb3f3d3910a6`。

这是作者对 MPEG1/2/2.5 Layer III 的技术说明，不是 ISO 正式标准原件。作者在范围
说明中明确以 ISO 定义为准。没有发现可据以将该 PDF 宣称为本项目 GPL 源码的授权；
此处只保留研究参考原件与来源，不把它或其中缺失内容冒充诺亚舟资料。

本次使用 PDF 技能，以本地 Poppler 实际渲染、阅读物理页 36–37 和 45（对应
4.3.11 的后半部分、4.3.12 起点及 Figure 11 所在页）。该副本多处公式及图形
实际为空，Figure 11 仅有标签，不能从空白推导图内容。可读文字支持 IS 的非零
频带边界、短窗口分别判定、非法位置回退；可读的抗混叠伪代码明确 8 kHz mixed
使用四个长子带，其它 mixed 使用两个。系数/末带决策仍另核公开源代码。

未对 PDF 修改、修复或重新导出，也未复制其全文到生成代码中。
相关实现与证据边界见 [MP3 guest 核心](../../audio/np560_mp3_guest_decoder.md)。
