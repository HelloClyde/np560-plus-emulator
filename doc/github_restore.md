# GitHub 私有备份与恢复

远程：`https://github.com/HelloClyde/np560`（私有）。
主仓库包含工具、Web 前端、逆向文档和 QEMU 定制补丁；不包含运行用固件、
NAND、游戏及 tmp 日志。文档资料目录中的既有研究附件仍随 Git 历史保存。

## QEMU 核心

本地 `qemu-dmcu/` 保持独立仓库，官方 origin 不变。
`scripts/qemu-patches/` 按顺序保存截至 `0fa30bd31b032cbd07d8a85719734c1bd4c57cc2`
的全部三个定制提交（含二进制补丁）。基线为 QEMU 8.2.10：
`f671ce11d2a15a58ab752d7cf0b2890c9022c7ba`。

在新环境先克隆主仓库，然后在根目录运行：

```bash
git clone --depth 1 --branch v8.2.10 https://gitlab.com/qemu-project/qemu.git qemu-dmcu
git -C qemu-dmcu rev-parse HEAD
# 上一步必须等于上述基线；不相等时先停止，不要套用到其它版本。
git -C qemu-dmcu switch -c np560
git -C qemu-dmcu am ../scripts/qemu-patches/*.patch
```

补丁恢复已用独立 Git index 验证：从指定基线依次应用后的完整 tree 与当前
QEMU HEAD tree 完全一致。恢复后的 commit ID 可能因提交者时间不同而变化。
后续核心修改需要重新导出补丁并提交主仓库，不能只推主仓库而遗漏核心改动。

运行仍需自行提供原厂固件和 NAND；构建与启动入口分别为
`scripts/build-np560.ps1`、`scripts/run-np560-web.ps1`。
