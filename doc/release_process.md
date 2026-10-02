# NP560+ 发布流程

根目录 `.github/workflows/release.yml` 在推送 `v*` tag 时运行两组不依赖
私有固件的源码测试；成功后自动创建 GitHub Release。已有同名 Release
时不覆盖它的描述和资产。`v0.*` 标为预发布。

这一步**不会自动生成或上传 NAND、原厂 PRG 或重建 ROM 二进制**：它们不在
Git 仓库，CI 没有这些输入。发布前应分别校验本地资产身份、测试冷启动，
再将获准分发的资产用 `gh release upload TAG FILE --clobber` 单独附到
私有 Release，并在说明中写明 SHA-256、来源及功能边界。不要把 NAND
放进 Git 历史，也不要把 HLE 重建镜像称为原厂 mask-ROM 转储。

源码中有 QEMU 硬件实现、可重建 guest ROM 的工具、原厂 PRG 可复用代码的
提取/组合规则及缺失 01/02 服务的 HLE 实现；但没有完整原厂 mask-ROM
字节。`scripts/build_np560_player_rom.py` 仍需合法取得的原厂
`NP560.PRG` 作为输入，输出当前 HLE ROM 包。单独下载 NAND 和源码
并不等于已经拿到全部运行输入或完成原厂升级/恢复功能。
