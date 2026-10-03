# NP560+ 文档导览

这里保存模拟器的使用指南、实现契约和逆向证据。首次使用请先看仓库根目录的 [快速开始](../README.md)；想了解当前完成度与下一步工作，看 [项目计划](plan.md)。逆向笔记记录的是特定版本、特定测试条件下的结论，历史推断未必代表当前实现；遇到冲突时，请结合代码和较新的验证记录判断。

## 使用与发布

| 目录 | 内容与入口 |
| --- | --- |
| [guides/](guides/) | [Windows 原生运行](guides/windows_native.md)、[发布流程](guides/release_process.md)、[从 GitHub 恢复工作环境](guides/github_restore.md) |
| [storage/](storage/) | [系统 NAND 构建](storage/np560_system_nand_build.md)、[增量写入与保存](storage/np560_nand_journal.md)、[设备备份](storage/np560_device_backup.md) |
| [web/](web/) | [Web 实例生命周期](web/np560_web_lifecycle.md)、[真机皮肤](web/np560_web_skin.md)、[速度](web/np560_web_speed.md) |

## 模拟与逆向

| 目录 | 内容与入口 |
| --- | --- |
| [cpu/](cpu/) | DMCU 指令、寄存器、异常与执行路径；从 [指令时钟](cpu/np560_instruction_clock.md)、[中断嵌套](cpu/np560_interrupt_nesting.md) 开始 |
| [hardware/](hardware/) | 外设、供电、定时器与时基；参见 [时钟/电源边界](hardware/np560_power_clock_boundary.md) |
| [firmware/](firmware/) | 启动、resident ROM/HLE 与固件 API；参见 [启动契约](firmware/NP560_resident_boot_contract.md)、[resident ROM API](firmware/NP560_resident_rom_api.md) |
| [display/](display/) | LCD 控制器、像素格式、扫描方向与状态栏；参见 [像素格式](display/np560_lcd_pixel_formats.md) |
| [audio/](audio/) | MP3、音频外设和解码研究；参见 [播放器](audio/np560_mp3_player.md)、[解码来源与边界](audio/np560_audio_codec_provenance.md) |
| [games/](games/) | NPE 加载、输入、音效和存档；参见 [输入语义](games/np560_npe_input_semantics.md)、[原生存档](games/np560_npe_native_save.md) |
| [disassembly/](disassembly/) | 反汇编清单及配套报告，文件量较大；先读 [总报告](disassembly/NP560_disassembly_report.md)，再按地址找对应的 `.asm` 与 `_report.md` |

## 资料与归档

- [sources/](sources/) 存放来源资料；[images/](images/) 存放文档配图与截图。
- [history/](history/) 保留旧版总览、计划快照等历史记录，不作为当前状态说明。
- 脚本和测试工具的分类见 [scripts/README.md](../scripts/README.md)。

文档中的本地路径和实验记录可能依赖未随仓库发布的原厂镜像或测试数据；这类记录用于复现研究过程，不等于 Release 包含对应材料。
