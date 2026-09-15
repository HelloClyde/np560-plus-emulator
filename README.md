# NP560+ 模拟器

基于 QEMU 的诺亚舟 NP560+ 模拟器与逆向工程工具。DMCU CPU、LCD、
键盘矩阵、NAND 等在 QEMU 中模拟，浏览器提供屏幕、触控按键和音频输出。
缺失的 resident ROM 服务允许按调用契约采用 HLE；不代表原厂 ROM 已完整恢复。

## 当前状态

- 原厂桌面、菜单及键盘输入已贯通，Web 支持手机布局和局域网访问。
- 已测桌面和 MP3 路径达到约 1× 实时速度；不是所有游戏的性能保证。
- 用户已确认《天降风云 V1.3》可游玩；其它游戏及完整剧情、存读档仍需逐项验证。
- **NPE 音效仍有缺失服务**。试玩需在原厂界面“系统 → 发音设置 → 音效开关”关闭音效。
  网页声音按钮只控制浏览器播放，不能关闭游戏内部音效。
- MP3 已有 HLE 解码与 Web 输出，连续播放、时序及兼容性仍有未完成项。

当前计划见 [doc/plan.md](doc/plan.md)，游戏导入记录见
[天降风云 V1.3](doc/np560_tjfy13_import.md)。

## 获取源码

主仓库和 QEMU 子模块均为私有仓库，需要有两个仓库的访问权限。

```bash
git clone https://github.com/HelloClyde/np560.git
cd np560
git submodule update --init qemu-dmcu
```

只初始化项目所需的 QEMU 子模块即可；不必递归下载 QEMU 自带的全部其它平台固件仓库。
主仓库固定 QEMU 的具体提交，不会自动跟随其分支变化。

## 目录

| 路径 | 内容 |
| --- | --- |
| `qemu-dmcu/` | QEMU CPU/硬件核心，Git submodule |
| `scripts/web/` | Python Web 桥接及浏览器前端 |
| `scripts/` | 构建、启动、导入和验证工具 |
| `scripts/tests/` | Python/JS 自动测试；硬件测试需要额外输入 |
| `doc/` | 逆向文档、验证证据说明及开发计划 |
| `scripts/qemu-patches/` | 早期三次核心提交的固定补丁备份，非持续更新源码 |
| `tmp/` | 本地运行与诊断输出，不纳入 Git |

脚本用途、运行风险及推荐测试入口见 [scripts/README.md](scripts/README.md)，
逐文件归类见 [scripts/CATALOG.md](scripts/CATALOG.md)。

## 构建与运行

当前脚本面向 **Windows + PowerShell + WSL Ubuntu2**。构建使用 WSL 中的
C 编译器、Python 3、Meson/Ninja 及 QEMU 配置所需依赖。
构建路径当前固定为 `E:/qemu-dmcu-build`，请先按本机环境调整脚本。

```powershell
./scripts/build-np560.ps1 -Optimization 3
Get-Help ./scripts/run-np560-web.ps1 -Detailed
```

**克隆源码不等于可直接启动完整系统。** 需另行准备合法取得的 `NP560.PRG`、
对应 resident ROM 构建产物和 NAND 镜像；它们以及 NPE 游戏、运行日志不在仓库中。
目前 ROM/HLE 工件仍依赖已有构建流程，不宣称新机器上一条命令即可复现试玩。
本地已验证配置与工件摘要见 [实时速度记录](doc/np560_web_speed.md) 和游戏导入文档。

启动时应配置 `-NandJournal` 或 `-NandSaveOnExit`；否则游戏内保存可能只留在进程内。
NAND 基线与增量日志必须配套，不可把旧日志重放到另一个导入后的镜像上。

手机及 LAN 设置见 [移动端与局域网](doc/np560_mobile_lan.md)。默认只监听本机，
局域网入口无用户鉴权，仅供可信内网使用，不要转发到公网。

## 基础测试

在项目根目录运行（需 Python 3 和 Node.js）：

```powershell
python scripts/tests/test_np560_web_frontend.py
python scripts/tests/test_np560_web_speed.py
python scripts/tests/test_np560_lan_proxy.py
node scripts/tests/test_np560_pointer_input.js
```

部分前端与硬件测试依赖本地原厂固件或已构建 QEMU；缺少这些输入时并非全部测试可运行。
硬件定向测试与历史验收范围以各 `doc/` 专题为准。

## 提交与恢复

修改核心时先在 `qemu-dmcu/` 中提交并推送到其私有远程，再在主仓库提交更新后的
子模块指针。不要只提交主仓库而遗漏核心提交。详见 [仓库恢复说明](doc/github_restore.md)。

QEMU 及第三方组件保留各自的许可证和来源说明，参见 `qemu-dmcu/COPYING` 等文件。
