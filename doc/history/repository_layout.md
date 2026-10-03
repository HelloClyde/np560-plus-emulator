# 仓库结构整理记录（2026-09-16）

后续决策：已改为 `HelloClyde/np560-qemu` 单仓库，QEMU 直接纳入目录。
下面的 submodule 方案仅为合并前历史记录，当前恢复方式见 [github_restore.md](../guides/github_restore.md)。

- 主仓库添加根 README；QEMU 改为正式 `qemu-dmcu` submodule，固定
  `0fa30bd31b032cbd07d8a85719734c1bd4c57cc2`。
- 核心私有远程：`HelloClyde/np560-qemu`，保留完整上游与定制提交历史，
  未改写现有提交。官方 GitLab 远程保留为 upstream。
- 219 个 Python、2 个 JS 测试从 scripts 根迁到 `scripts/tests/`，调整
  导入路径、项目根定位、源文件定位及 PS1/doc 调用路径。
- `scripts/README.md` 提供使用入口与风险说明；`scripts/CATALOG.md` 逐文件归类。
  其它历史工具、C 参考与 PS1 包装器暂保留根路径，不宣称已全部分目录迁移。
- 运行实现仍为 QEMU 与 `scripts/web/`；早期 Python 模型不属于当前试玩内核。

## 验证范围

全部 scripts Python 文件 compileall 通过；目录变更与 Git whitespace 检查通过。
定向复核：前端 24、Web 速度 4、LAN 转发 2、矩阵路线 25 项全部通过，
两个 Node 测试入口（触控、音频输出）通过。另对文件导入、ROM skeleton、
FTL 分析、设备配置、截图及 UI 预处理测试作了定向检查。

广泛 unittest 导入检查能发现测试，但 arena release 硬件脚本需要命令行参数，
音频分析依赖本机未安装的 NumPy；不视作这次移动引入的回归。
875 项和缩小后的 525 项批量运行因耗时被主动停止，**未完成，不能宣称整批通过**。
完整 ROM 重建和 QEMU 硬件集成验收未在本轮重跑。没有重启或修改 8808 的 guest。
