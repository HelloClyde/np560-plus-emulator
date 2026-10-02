# NP560+ 模拟器

基于 QEMU 的诺亚舟 NP560+ 模拟器与逆向工程工具。DMCU CPU、LCD、
键盘矩阵、NAND 等在 QEMU 中模拟，浏览器提供屏幕、触控按键和音频输出。
缺失的 resident ROM 服务允许按调用契约采用 HLE；不代表原厂 ROM 已完整恢复。

## 当前状态

- 原厂桌面、菜单及键盘输入已贯通，Web 支持手机布局和局域网访问。
- 已测桌面和 MP3 路径达到约 1× 实时速度；不是所有游戏的性能保证。
- 用户已确认《天降风云 V1.3》可游玩；其它游戏及完整剧情、存读档仍需逐项验证。
- 新构建的播放器 ROM 包默认接入自有 NPE format-13/mode-5 音频 HLE；
  《天降风云录》新游戏已在隔离整机采到非零 DAC。旧 ROM 包和已有设备不会自动升级。
  其它 NPE 格式、读档后音乐初始化及真机音色仍未解决。网页声音按钮只控制浏览器播放，
  不能代替原厂游戏内部的音效与音量设置；此 HLE 不依赖第三方解码库。
- MP3 已有 HLE 解码与 Web 输出，连续播放、时序及兼容性仍有未完成项。

当前计划见 [doc/plan.md](doc/plan.md)，游戏导入记录见
[天降风云 V1.3](doc/np560_tjfy13_import.md)。

## 获取源码

全部项目源码统一在一个私有仓库中，QEMU 核心是普通目录，无需初始化子模块。

```bash
git clone https://github.com/HelloClyde/np560-qemu.git
cd np560-qemu
```

合并保留了工具仓库和 QEMU 上游/定制提交的历史。NP560 不使用的上游可选平台
固件子模块未纳入当前工作树，其原始引用仍可在历史提交中找到。

## 目录

| 路径 | 内容 |
| --- | --- |
| `qemu-dmcu/` | QEMU CPU/硬件核心，直接纳入本仓库 |
| `scripts/web/` | Python Web 桥接及浏览器前端 |
| `scripts/` | 构建、启动、导入和验证工具 |
| `scripts/tests/` | Python/JS 自动测试；硬件测试需要额外输入 |
| `doc/` | 逆向文档、验证证据说明及开发计划 |
| `scripts/qemu-patches/` | 早期三次核心提交的固定补丁备份，非持续更新源码 |
| `tmp/` | 本地运行与诊断输出，不纳入 Git |

脚本用途、运行风险及推荐测试入口见 [scripts/README.md](scripts/README.md)，
逐文件归类见 [scripts/CATALOG.md](scripts/CATALOG.md)。

## 构建与运行

当前脚本面向 **Windows + PowerShell + WSL**（默认发行版 `Ubuntu2`）。构建使用 WSL 中的
C 编译器、Python 3、Meson/Ninja 及 QEMU 配置所需依赖。
默认构建路径为 `/mnt/e/qemu-dmcu-build`，可通过参数指定已有发行版和构建目录，
无需修改脚本。`-BuildDirectory` 使用该发行版内的绝对 Linux 路径。

```powershell
./scripts/build-np560.ps1 -Optimization 3
# 示例：使用其他发行版和 Linux 文件系统目录；DryRun 只打印命令，不构建。
./scripts/build-np560.ps1 -Distro Ubuntu -BuildDirectory /tmp/np560-build -Jobs 4 -DryRun
Get-Help ./scripts/run-np560-web.ps1 -Detailed
```

构建脚本使用非登录 shell，避免个人 profile 中无关的启动命令影响构建。
运行脚本的 QEMU 路径仍须与所选构建输出对应配置；此参数不会自动切换试玩实例。

**克隆源码不等于可直接启动完整系统。** 需另行准备合法取得的 `NP560.PRG`、
对应 resident ROM 构建产物和 NAND 镜像；它们以及 NPE 游戏、运行日志不在仓库中。
现可从指定原始 PRG 重建当前源码的 ROM/HLE 包；NAND 内容仍须另行准备，
不宣称新机器上一条命令即可复现完整试玩。
本地已验证配置与工件摘要见 [实时速度记录](doc/np560_web_speed.md) 和游戏导入文档。

从原始 V3.80 PRG 构建（不依赖已有 `tmp` 文件）：

```powershell
python scripts/build_np560_player_rom.py --firmware "NP560+V3.80版系统升级程序/NP560.PRG" --output NEW_OUTPUT_DIRECTORY
```

要求输出目录不存在，拒绝错误固件和 `python -O`；逐段校验固定哈希。
输出根目录是可传给 `-SocRomBundle` 的包，`stages/` 留存中间证据，
`build-report.json` 记录构建参数与哈希。不会启动模拟器、改写 NAND 或切换设备。
这是重建服务加 MP3 HLE 和自有 NPE format-13/mode-5 HLE，不是提取出原厂
mask ROM，也未补齐其它 NPE 格式。当前默认 v6 的最终产物为 `18cca3e8…`；
`815284da…` 是加入 NPE 服务之前的播放器中间阶段，不是新建包最终镜像。
两者均不同于旧试玩包 `3aa95312…`；
验证范围见 [可重建 ROM 包](doc/np560_player_rom_build.md)，不自动替换旧实例。

可选实验 EQ：构建时加 `--experimental-eq`，启动时显式使用
`-SocRomBundle <包目录> -ExperimentalEq`（Python入口为 `--experimental-eq`）。
默认仍为v6；实验v8使用兼容性滤波假设，不代表原厂DSP完全还原，详见上述文档。

系统 NAND 整合入口已通过 V3.80 原包完整烧录、数据/ECC 和冷启动验证。在 WSL/Linux 中，
准备至少 2 GiB 空间、`cc` 和 QEMU，可执行：

```sh
python3 scripts/build_np560_system_nand.py --package '/path/NP560+.upd' --qemu /path/qemu-system-dmcu --soc-rom-bundle /path/player-bundle --output /path/new-nand-build
```

它从逆向重建的最小出厂记录开始，让包内原厂 burner 分区及烧录，然后核对完整
payload/ECC 和冷启动。该出厂记录不是真机 dump，USB 接口由测试传输驱动，不能
视为完整 USB 硬件还原。输出必须是新目录；失败保留现场。详见
[系统 NAND 构建](doc/np560_system_nand_build.md)。

已有 native factory ROM bundle 时，仍可只执行最后一步生成 MP3 HLE 版本：

```powershell
python scripts/build_np560_mp3_hle.py --resident-bundle PATH_TO_NATIVE_FACTORY_BUNDLE --output NEW_OUTPUT_DIRECTORY --profile player
```

`player` 包含 v6 首帧处理、输入回收、PCM 复制、退出释放和紧凑工作区，避免遗漏
已验证的播放器背景内存修复。输出目录必须不存在；不会改写输入、设备配置或重启实例。
启动或创建设备推荐传 `--soc-rom-bundle NEW_OUTPUT_DIRECTORY`，PowerShell 对应
`-SocRomBundle NEW_OUTPUT_DIRECTORY`，无需再传 `SocRom`、`SocRomSkeleton` 或 HLE 地址。
工具校验 ROM 尺寸/SHA-256、所选 PRG、v6 HLE 标记及 arena 跳转，再绑定清单中的地址。
校验是完整性检查，不是原厂真实性认证。手工启动仍可用 `-SocRom`、
`-RomMp3HleBase`、`-RomMp3ArenaImage`，但地址必须来自同一构建，不得与 bundle 参数混用。
这个单独的 MP3 HLE 入口不是完整 ROM 构建流程，也不包含 NPE 声音解码；
普通新建包应使用上面的 `build_np560_player_rom.py`。

### NPE 音效与旧实验入口

新构建的 ROM 包会校验并登记六个 NPE 服务入口；使用 `-SocRomBundle` 启动时，
Web 自动启动仓库内的独立 mode-5 解码服务，不需要 DLL 参数。旧包不会隐式开启。
手动指定 `-RomNpeCodecOwned`、`-RomNpeCodecDll` 和
`build_np560_npe_hle_rom.py` 仍可供隔离诊断，但不能与 `-SocRomBundle` 混用。
音频流仍回到客机原厂增益、缓冲与 DAC，不由网页直接播放替代 WAV。
证据和限制见
[NPE 音频契约](doc/np560_npe_audio_contract.md)。

没有真机 PCM 对照，不能据此宣称原声完全一致；音频游戏资源也不纳入仓库。

新建持久设备使用 `np560-device-v3`，会把 `rom_mp3_hle_base`、
`rom_mp3_arena_image`、`rom_npe_codec_owned`、`instruction_clock` 和 `realtime`
与 ROM 身份一起保存。
之后用 `--device`（PowerShell 的 `-Device`）恢复，无需再次传这些参数；
v3 会拒绝显式覆盖，以免新 ROM 配错服务。旧 v1/v2 文件仍可读取且不会自动改写；
不要为迁移配置删除或重建原 NAND 日志。

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

核心、Web、工具及文档现在使用同一个 Git 仓库，统一提交、统一推送到 `origin/master`。
无需更新子模块指针，也无需同步历史补丁。详见 [仓库恢复说明](doc/github_restore.md)。

QEMU 及第三方组件保留各自的许可证和来源说明，参见 `qemu-dmcu/COPYING` 等文件。

`v*` tag 的自动 Release 与非 Git NAND 资产的上传边界见
[发布流程](doc/release_process.md)。
