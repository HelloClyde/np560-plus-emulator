# NP560+ 发布流程

`v*` tag 触发 `.github/workflows/release.yml`：Ubuntu 运行源码测试；
Windows 2022/MSYS2 UCRT64 从 tag 源码编译 `qemu-system-dmcu.exe`，
收集其非系统 DLL 和经过 SHA-256 校验的 Python 3.12.10 嵌入式运行时，
生成 `np560-windows-x64.zip`。发布任务等待两项工作成功，再将模拟器包上传
到对应的私有 GitHub Release。`master` 推送和 PR 只运行不依赖镜像的源码测试。

同一发布任务从私有 `v0.1.0` Release 下载已校验的原厂 V3.80
`NP560.PRG`，重建并校验 `resident.bin`，上传这两项和构建清单。
当前 PRG SHA-256：`d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`；
resident SHA-256：`18cca3e8bc6f9512ae017935c37d5241b268a83a45920255f8054228bfcb260a`。
Python 嵌入包固定为 3.12.10，SHA-256：
`4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3`。

完整 `system.nand` 是本地运行设备的独立数据/OOB 检查点，不能由源码 CI
重新构造；打 tag 后需要在本地停机导出，核对 FAT 目录和 SHA-256，手动上传到
同一 Release。不可直接复制运行中的基础镜像而遗漏 `.npj` 增量日志。
发布页应列出 NAND 的 SHA-256、内容和来源。镜像不加入 Git 历史。

最终用户下载四项即可在 Windows x64 运行：模拟器 ZIP、`NP560.PRG`、
`resident.bin`、`system.nand`。后三项放进解压后 `images/`，双击
`Start-NP560.cmd`；设备配置和 NAND 增量写入保留在 `device/`。
这些是三种不同用途的镜像，不能合并为一个 NAND。

源码包含 QEMU 硬件实现、原厂 PRG 可复用代码的提取/组合规则以及缺失
01/02 resident 服务的 HLE；`resident.bin` 不是完整原厂 mask-ROM 转储。
原厂 USB 升级/恢复全流程、全部游戏兼容性、异常断电和一致整机快照尚未完成。
