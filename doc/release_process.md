# NP560+ 发布流程

根目录 `.github/workflows/release.yml` 在 `master` 推送和 PR 时运行两组
不依赖私有固件的源码测试；推送 `v*` tag 时先运行同样测试。成功后，
CI 从本仓库私有 `v0.1.0` Release 下载已核对的 V3.80 `NP560.PRG`，
校验其 SHA-256，再从 tag 对应的源码重建并校验 `resident.bin`，创建
Release 并附上 `NP560.PRG`、`resident.bin` 和其 `manifest.json`。
已有同名 Release 时保留描述；同名三项资产在重跑时会更新。`v0.*` 标为预发布。

CI **不会自动生成或上传 NAND**：512 MiB 原厂系统及游戏检查点不在 Git 仓库，
打 tag 本身也不会重现游戏导入和整机验收。NAND 必须在本地单独校验、冷启动，
然后将获准分发的资产用 `gh release upload TAG FILE` 附到私有 Release，
并在说明中写明 SHA-256、来源及功能边界。不要把 NAND 放进 Git 历史，
也不要把 HLE 重建镜像称为原厂 mask-ROM 转储。

源码中有 QEMU 硬件实现、可重建 guest ROM 的工具、原厂 PRG 可复用代码的
提取/组合规则及缺失 01/02 服务的 HLE 实现；但没有完整原厂 mask-ROM
字节。`scripts/build_np560_player_rom.py` 仍需原厂 `NP560.PRG` 作为输入，
并非纯源码编译。当前私有 Release 将三个运行映像分别保存；其中 PRG 是
固定原厂输入，resident ROM/HLE 是派生构建产物，NAND 是独立的存储检查点。
不要将三者合并冒充真机单一 NAND；也不能由此声称完整原厂升级/恢复功能。

2026-10-02 从该本地 V3.80 PRG 独立重建一次，输出 `resident.bin` 的
SHA-256 为 `18cca3e8bc6f9512ae017935c37d5241b268a83a45920255f8054228bfcb260a`，
与当前试玩设备所用包逐字节一致；这验证可重建性，不改变上述来源限制。
