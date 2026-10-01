# 系统 NAND 的完整构建入口

2026-09-18。`scripts/build_np560_system_nand.py` 串接已有工具，已实际通过
V3.80 原包完整烧录、全部payload/ECC核对和零按键冷启动。不是全部应用验收。

输入为合法取得的 V3.80 NP560+.upd、当前播放器 ROM bundle、Linux QEMU。
仅支持 SHA-256 为 `6f484f700be9429d7adbed3fa0655e1f23631f9b6e59efe785b302ff2974f6cf`
的原包，并核对包内 PRG 与 ROM manifest 身份。宿主需要 `cc`，拒绝 Python -O。

流程在全新输出目录内完成：

1. 检查输出不存在、包身份、QEMU、编译器与至少2 GiB磁盘空间。
2. 提取原包 slot0 burner、slot2 PRG 和 slot3 NAND payload。
3. 编译既有 FNV 检查工具，生成除出厂页以外均擦除的 seed。
4. 用现有 UpdateAll 分支驱动原厂命令23/1/27/11/2/25，再传输完整数据及命令18提交。
5. 核对全部包内 payload、尾部填充及对应sector ECC；局部检查不能通过。
6. 独立冷启动，检查原厂顶栏、缺失服务/非法控制诊断及NAND错误。

成功产物为 `system.nand`，`build-report.json` 只有在所有阶段成功后才标 passed。
失败保留中间产物、命令与错误；不覆盖已有输入、不修改用户设备、不自动启用LAN。
seed仍是逆向fixture，测试传输仍经受控guest RAM入口，不能冒充真机原始NAND或
完整USB硬件。此次构建不导入额外NPE游戏、不提供ESAC实现、不验证所有应用。

五项编排安全检查通过：已有输出拒绝、错误包拒绝、缺编译器拒绝、阶段失败不继续
烧录并保留错误报告，以及2 GiB空间阈值的两侧边界。另复验原厂分区错误分支9项、
失败诊断3项、factory写入2项、payload/ECC校验4项，通过；不代替真实原厂程序执行。

实际运行：`E:/qemu-dmcu-build/np560-from-package-20260918-v1/`。
初始命令结果23=0、1=(-11,-3)、27=(-12,-3)、11/2/25=0，符合原厂未格式化分支。
全部43,963,316字节写入后原厂命令18提交成功，最终PROGRAMS=43338、
ERASES=16724、COPIES=21347、ERROR=0、MASKROM_WRITES=0。
payload-verification.json 覆盖43,963,392字节（含76字节尾部填充），数据零差异、
85,866个对应sector ECC零错误。未用局部修补加工烧录结果。

独立冷启动约70.58秒完成；最后三次指定顶栏均0/5280像素差异，
ROM_MISSING/INVALID_CONTROL/UNSUPPORTED均为none，NAND无错。final.png已目视
确认完整学习菜单。injected_keys=0、host_guest_memory_writes=0、nand_save_enabled=false。
两个自有QEMU均记录qemu_reaped，整个构建进程退出0。

最终system.nand共553,648,192字节，SHA-256：
`9da1cc971c75fa58c1debe8d04edd8b59acb428de18b21da79d1f50a18576ef3`。
与此前完整原厂烧录结果一致；输入不依赖之前的用户checkpoint。
新包ROM为815284da…，镜像保持原包内容，未导入额外游戏；没有修改或重启试玩设备。
