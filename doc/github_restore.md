# 单仓库恢复与维护

统一远程：`https://github.com/HelloClyde/np560-qemu`（私有），默认分支 `master`。
QEMU 核心、Web 前端、脚本和文档均在同一仓库，`qemu-dmcu/` 不再是 submodule。

```bash
git clone https://github.com/HelloClyde/np560-qemu.git
cd np560-qemu
```

之后在项目内统一 commit、push 即可。无需 `git submodule update`，也无需套用
`scripts/qemu-patches/`；这些补丁仅保留为早期版本的历史备份。

运行固件、resident ROM 构建产物、NAND、游戏与 tmp 日志仍需自行保管，不随 Git 上传。
文档研究附件维持原来的 Git 跟踪范围。

## 合并历史与回退资料

- 合并前项目提交：`5ed4dd0`。
- 合并前 QEMU 提交：`0fa30bd31b032cbd07d8a85719734c1bd4c57cc2`。
- 通过双父合并保留两个仓库历史，QEMU 源码位于 `qemu-dmcu/` 前缀目录。
- 原核心分支 `codex/dmcu` 保留；旧 `HelloClyde/np560` 仓库未删除或改写。
- 本机旧项目远程保留为 `legacy-project`，统一仓库使用 `origin`。
- 本机原嵌套 `.git` 元数据移到主仓库 `.git/np560-core-before-monorepo`，未删除；
  这是本地恢复资料，不随 push 上传。日常操作不应使用该备份替代主仓库。

QEMU 原上游的 15 个未初始化可选子模块（其它平台 ROM 和 libvirt-ci）不属于 NP560
实现，本次从工作树的 gitlink 中排除，原始 `.gitmodules` 与固定提交可在 QEMU
父历史中查询。未删除任何已初始化的第三方源码；NP560 CPU/硬件源码、许可证及
Web/脚本功能没有因合仓改写。

若以后需要构建其它 QEMU 平台，请按上游历史单独取得相应依赖；当前仓库面向 NP560。
