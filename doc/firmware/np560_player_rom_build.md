# 从原始 PRG 重建播放器 ROM 包

## 2026-10-01：新建包默认包含自有 NPE mode-5 服务

`scripts/build_np560_player_rom.py` 现从原始 V3.80 PRG 构建播放器阶段后，
再校验并接通六个已登记的 01/02 NPE 空洞；默认 v6 最终 ROM SHA-256 为
`18cca3e8bc6f9512ae017935c37d5241b268a83a45920255f8054228bfcb260a`，
加入 NPE 前的 `815284da…` 仅为中间阶段。v8 的最终哈希为
`a0a2dbd72b33d2ec846f80fd1e566b79a2ca6060948aeed041f9f3298978b121`，
仍须显式允许实验 EQ。清单把 `owned-mode5`、format 13、入口偏移和原
播放器阶段哈希绑定到最终镜像；Web 装载时复核入口字节及反向哈希，
自动启动仓库内的解码子进程，不依赖历史 CYBIT DLL。旧 ROM 包和既有
设备文件不会被改写或自动迁移。

本地复建产物在 `tmp/np560-player-owned-npe-20261001-v1/`，其
`build-report.json` 的 `runtime_verified=false` 只是构建器不自行启动
QEMU，不应误读为下面的隔离整机结果。8921 用此包和本机《天降风云
V1.3》从原厂菜单进入新游戏：实体确认进入地图，10 秒采集 79 个非零
DAC 包、0 采集及控制缺口；自有后端累计解码 1,732 帧、失败 0。
证据为 `tmp/np560-player-owned-audio-20261001-v1/tjfy-newgame-dac.json`、
同目录 PNG/WAV 和生命周期日志。另用该包创建 `np560-device-v3`，
仅凭 `-Device` 重开后 QEMU 与 owned 解码服务均自动启动并正常退出。
这些检查不证明其它 NPE 格式、读档后音乐恢复、真机音色或浏览器
长时间连续听感。37 项包/配置/ROM 测试及 11 项相关音频测试通过。

## 新核心与默认 v6 再验收（2026-09-30）

翻译期观察模式分派后的核心 `d3b6a85b…` 使用同一个默认 v6 ROM 和输入 NAND；
`tmp/np560-mode-dispatch-integrated-20260930-v1/report.json` 通过原厂游戏标题、
四向世界坐标闭环、F4菜单取消、Start回桌面及 MP3 非零 DAC 继续推进
（`next_frame` 1188779→1201662）。bridge/QEMU 退出 0；NPE 音效经原厂
设置关闭，详细观察开启，不能作为游戏速度或音效证据。
`tmp/np560-mode-dispatch-minimal-title-20260930-v1/report.json` 则在普通低开销
模式下冷启动进入英雄标题。新核心的播放器测速及模式切换回归见
[宿主执行优化](../cpu/np560_host_cpu_sampling.md)；完整模拟器仍未完成。

## 默认 v6 同进程游戏→MP3 验收（2026-09-30）

`scripts/probe_np560_eq_web_bundle.py` 现在按显式选定的 ROM manifest 接受
默认 v6（6 个服务标记），仍仅对 v8（9 个标记）传入 `--experimental-eq`。
这一修改没有重建 ROM 或改变 QEMU/前端运行语义。

当前保留核心 `8ec42d19…`、默认 v6 ROM `815284da…`、只读输入 NAND
`a9c64f2f…` 的隔离整机运行见
`tmp/np560-v6-integrated-current-20260930-v1/report.json`，`passed=true`。
从原厂启动卡和桌面经真实矩阵进入《英雄传奇》标题/新游戏，世界坐标
(8,12)→(8,13)→(9,13)→(8,13)→(8,12)，F4 打开并取消游戏菜单，
Start 回桌面；再经原厂菜单选 LONG22，原厂上键调音量，取得同一音频
stream/generation 的两次启用且非零 DAC 包，`next_frame` 从 1309930
推进到 1327816。bridge/QEMU 正常退出 0，未保存或覆盖输入 NAND。

另以相同核心/ROM/NAND、不启用完整 control observers 的普通低开销配置
冷启动，原厂设置关闭音效后经菜单进入英雄标题，报告
`tmp/np560-v6-minimal-title-20260930-v1/report.json` 通过并正常退出。
此独立运行只验证到标题，不应拼成低开销配置下完整场景/MP3 流程。

完整流程运行通过原厂设置页把 NPE 音效关掉，且为读取游戏坐标启用了完整
control observers；它不是游戏音效、完整剧情/存读档、无缝连续音频、
浏览器听感或实时性能的证明。当前 15 秒无观察播放窗口约 0.95 倍
实时，仍需继续优化执行器并补齐 ESAC 音效；不能把此整机通过称为
“模拟器已经完成”。

## 输入空间查询的公开入口绑定（2026-09-22）

ROM 包加载器现在同时核对固定公开入口 `01:49BE` 的 AJMP 与已验证的
`free_words` HLE 服务地址。此前仅验证 ROM 整体哈希和服务标记，一份重新生成哈希、
但公开入口指向旧地址/错误服务的包仍可通过检查；新增反例先在旧实现上复现该漏检。
现在在启动前报 `ROM bundle input-space veneer mismatch`，不等运行后才表现为查询异常。

10 项 ROM 包测试、16 项设备配置测试通过。实际默认 v6 包
`tmp/np560-player-from-prg-20260918-v1` 和显式 opt-in 的 v8 包
`tmp/np560-player-eq-repro-20260922-v1` 均仍可加载，派生的 HLE/arena 地址不变。
没有重建或替换 ROM、升级用户设备，也不证明全部重建组件语义已经核验。

## v8 同进程游戏退出后播放 MP3（2026-09-22）

`tmp/np560-eq-game-to-mp3-20260922-v1/report.json` 通过：原厂设置界面关闭
游戏音效，英雄传奇标题→新游戏→四向世界坐标闭环→F4菜单及取消→Start桌面，
再进入MP3播放器，选择LONG22并通过原厂上键提高音量。已查看播放器截图。
探针新增 `--native-sound-off` 和 `--mp3-after-game-reference`，分别有前置
检查；设置仅作用于本进程模拟NAND，不导出覆盖用户镜像。

两次实际DAC包均启用、同一stream/generation=2，各9600帧，峰值3891，
非零样本19196；next_frame由1270453推进到1287571，PLL=0x900D，23995Hz。
这证明退出游戏后实际PCM输出继续推进，不代表两包之间连续覆盖或浏览器听感。
完整控制追踪开启，3秒宿主等待仅推进约0.356625秒音频时间，不能作为实时性能证据。

bridge及QEMU退出0，报告passed=true；输入NAND的SHA256仍为
`a9c64f2faf529306df31049c201c7d2901c049039110256fc008cad61c47e146`。
核心SHA256：`56c31c9bb92f2bf01ff219afbbc3382e8b1ff42f8856f86761ee84629a538d4e`。
17项CLI检查、3项场景坐标检查通过。默认ROM仍v6；v8实验包未自动迁移用户设备。
NPE音效仍未实现，用户报告的其它具体错键也不能据此宣布修复。

## v8 游戏菜单返回与退出桌面（2026-09-22）

`tmp/np560-eq-npe-exit-20260922-v1/report.json` 在同一独立进程中完成标题、
新游戏、四向世界坐标闭环，再M4/8E打开游戏菜单(mode6)、再次M4/8E回场景
(mode1)、M55/B0退出到原厂桌面。三键各消费一次且释放已观察；取消前后屏幕
坐标、视口偏移、地图和朝向完整一致。已查看两张LCD图，菜单为属性/仙术/物品/
系统，退出后为完整学习桌面，非仅PC或键码断言。

探针增加显式 `--npe-exit-check`，要求场景检查和原厂界面参考，未保存NAND，
未写运行中guest内存，也不发送存档动作。bridge/QEMU退出0、PID消失，报告通过。
17项CLI检查与3项坐标检查通过。这里只验证英雄传奇音效关配置；尚未在同一
进程中启动MP3播放或验证游戏音效，也不是其它游戏/全部返回键语义的证明。

## 场景检查更正：Up正常移动并滚屏（2026-09-22）

下节“向上不移动”现已排除：v6原始完整key_status其实记录视口Y从11减到10。
原厂世界坐标应是屏幕坐标加视口偏移；原代码1D:0020..0044（历史反汇编标为
3A段）也明确相加。初始世界(8,12)，下(8,13)，右(9,13)，左(8,13)，上(8,12)。
最后一次屏幕Y保持2是滚屏，不是阻挡或错键。此前探针只断言屏幕坐标，是检查错误；
v6原失败报告不改写，按完整字段离线重算已经闭合上述五个位置。

修复探针用 `scene_position` 保留屏幕/偏移/地图/朝向并计算world_x/world_y，
不把缺失偏移默认为0。新增3项检查覆盖视口移动、画面变化但世界不变、偏移缺失。
冷启动重跑 `tmp/np560-eq-npe-scene-20260922-v7/report.json` passed=true，
四次真实方向输入各等待原移动函数返回，地图号不变且世界坐标闭环；网页bridge及
QEMU正常退出0，PID已消失，未保存NAND。17项CLI检查通过。

这是v8、英雄传奇原厂音效关、新游戏首场景的四向证据，不外推所有游戏/菜单按键、
短按速度、游戏全流程或音效。默认ROM仍v6。旧失败分析如下保留供追溯，不再视为
未解决的模拟器移动缺陷。

## v8 场景方向反例，尚未通过完整检查（2026-09-22）

`--npe-scene-check` 在标题后开始新游戏，检查坐标与完整移动函数返回。
`tmp/np560-eq-npe-scene-20260922-v6/report.json` 保留失败，不提升默认v6：
初始(7,1)，Down→(7,2)，Right→(8,2)，Left→(7,2)，Up仍(7,2)、朝向2。
各步对应的原厂矩阵键码正确且消费一次；最终详细移动调用/返回均4次。
所以不是“Up没映射”，但尚未确认是场景阻挡、游戏数据语义还是模拟器问题。
不能只看未移动便修改键表，也不能在未核对地图规则前把预期改成(7,2)让测试通过。
已查看scene-right图，确认实际游戏场景已渲染；本检查无存档写回或音效验收。

前置运行边界：v1/v2在轻量观察模式下得到相同坐标，详细计数为未启用的零；
v3完整追踪下150ms宿主脉冲未被启动卡消费；v4改为等待guest确认，但一秒settle
时函数尚未返回，不能把其返回值当本次动作结果。v5探针使用Python3.9的
removeprefix而WSL实际为3.8.10，已修正。v6明确等待每次direction helper完成后
仍复现Up不移动，排除仅仅提前采样这一解释；保留所有原报告，不篡改失败。
完整观察明显影响性能，这些运行不能作为实时速度或网页短按的验收。

探针参数前置条件回归及原有CLI检查17项通过，不能替代上面的整机失败结论。

## v8 与 NPE 标题入口交叉验证（2026-09-22）

`probe_np560_eq_web_bundle.py --npe-title-check` 在其自有动态端口实例中，
核对启动卡、按原厂Enter关闭、核对桌面，再用真实矩阵依次走开始→娱乐→
游戏世界→NPE列表→首个游戏。启动仍明确要求experimental-eq，不修改默认v6。

第一次使用channel-switch NAND，读回原厂音效设置为开，检查在进入游戏前
拒绝继续；报告`tmp/np560-eq-npe-title-20260922-v1`保留失败，bridge状态
stopped、QEMU退出0。未把声音关掉或以RAM修改绕过缺失解码器。

第二次使用此前原厂菜单保存音效关的settings-persist NAND，输入SHA256
`6abc62e96dd73322532f122029536418bfefc2f85bd82be89cbf3935bf2028d8`，
运行报告`tmp/np560-eq-npe-title-20260922-v2/report.json`通过。已查看
`npe-title.png`，确为《英雄传奇》“新的征程/再续前缘/退出游戏”标题页；
原厂NPE控制状态mode7，无缺失ROM/非法指令报告。正常关闭后bridge/QEMU退出0，
已核对QEMU PID消失。未保存NAND、未改用户实例。

此项证明v8新布局在该设置下仍可进入原厂游戏标题，不证明开始游戏后的完整
玩法、与MP3来回切换、存档兼容或NPE音效；不据此自动迁移现有设备/提升默认版本。

## 可选实验 EQ（2026-09-22）

默认仍构建v6；显式 `--experimental-eq` 构建v8，频段及滤波拓扑为兼容假设，
不是真实mask-ROM。构建和启动需要分别选择，不自动迁移设备：

```powershell
python scripts/build_np560_player_rom.py --firmware "NP560+V3.80版系统升级程序/NP560.PRG" --output NEW_EQ_BUNDLE --experimental-eq
```

在现有独立启动命令中使用 `-SocRomBundle NEW_EQ_BUNDLE -ExperimentalEq`；
Python Web入口对应 `--soc-rom-bundle NEW_EQ_BUNDLE --experimental-eq`。
不要同时传手工HLE地址或 `-Device`。需使用包含v8支持的新QEMU核心。
启动校验检查全部9个marker、3个公共音效入口AJMP以及原固件/ROM摘要，
未显式允许时拒绝v8，v7参数层仍不作为播放包接受。

本轮从原PRG完整构建 `tmp/np560-player-eq-repro-20260922-v1`，最终SHA256
`5e4be1ecda33813c1c5da627523d510f98b1a7e9785a16d43f87513269aaa85f`，与已实播实验包
完全一致。启动参数绑定经过单元测试；本轮没有启动新的网页服务器或替换用户实例。
EQ验证范围见 [EQ HLE](../audio/np560_eq_hle.md)。

实际 Python Web 入口验收：`tmp/np560-eq-web-bundle-20260922-v1/report.json`
passed=true，通过独立动态端口37835启动，HTTP /api/health、首页、/api/state均成功。
页面包含新MP3按键说明；state的ROM摘要等于上面的v8摘要，客机code空间9个
服务marker逐项等于v8/服务编号。未启用NAND保存；通过带token的shutdown接口
关闭后bridge/QEMU返回码均0，确认其QEMU PID已消失。端口已关闭，不是试玩地址。
复用脚本 `scripts/probe_np560_eq_web_bundle.py`，只操作其自己创建的实例。
本检查未操作浏览器、未验收页面布局/WebAudio，也未实跑PowerShell包装器启动。

2026-09-18。入口 `scripts/build_np560_player_rom.py`；只需要仓库源码和用户提供的
V3.80 `NP560.PRG`，不读取此前的临时 ROM、native bundle 或历史 manifest。
不构建 QEMU、不创建 NAND、不导入游戏、不启动或改动用户设备。

## 固定构建链

1. `build_np560_reconstructed_rom` 的原厂链接启动组合生成基础 ROM。
2. `build_np560_vma03_soc_rom` 退休过时的 overlay 安装器，并保留现有服务边界。
3. `build_np560_mp3_resident` 使用 fast-dct32 布局重新分配 guest 组件。
4. `build_np560_mp3_factory` 生成 MP3 ABI 适配器。
5. `build_np560_mp3_hle` 使用 v6 player 全套选项，再经运行入口的 bundle 校验器检查。

PRG SHA-256 固定为 `d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5`。
基础 ROM 为 `36847961…`、VMA03 为 `a243f8ba…`，与旧运行链一致。
当前 native 为 `db2e80fc…`，factory 为 `e1d8857b…`，最终 ROM：
`815284dae5f7853d120e7f73f1e0444c292c4c8f313455c47a08df16a58f5031`。
HLE base=138790，arena image=93952；调用者应使用 bundle 绑定，不手填或混用地址。

当前适配器比历史构建预留尺寸增加104字节，重新打包后 factory code_address
由76352变为136314。因此最终镜像不等于旧 `3aa95312…`，没有回填旧字节或
放宽旧哈希来假装相同。新产物须单独验证，旧试玩设备不自动迁移。

## 安全与可重复性检查

- 错误 PRG 在创建输出目录前拒绝；已有目录拒绝覆盖。
- 下层构建器依赖 assert 做布局检查，因此拒绝优化模式 Python。
- 明确传递外部 PRG 路径；临时设置的构建模块全局变量在成功或异常时恢复。
- 五段结果各自校验固定哈希；源码变化须审查后更新，不接受静默漂移。
- 最终包使用实际启动入口的完整性检查；构建报告不伪称运行验证通过。

`test_np560_player_rom_build.py` 五项通过，包括复制 PRG 到外部带空格路径、
将默认输入设置为不存在文件后实际完成全链重建，以及失败后恢复模块全局状态。
`tmp/np560-player-from-prg-20260918-v1/` 为实际构建证据。
此流程没有填补未知 mask-ROM 算法；原有暂定服务、HLE 与模拟真实性边界均保留。

## 运行验证

新包运行结果在 `tmp/np560-from-prg-player-20260918-v1/` 单独记录，passed=true、
exit_code=0、host_guest_memory_writes=0、nand_save_enabled=false。
原厂菜单进入播放器并选中 tone440，最后解码2527帧、5053 granule，failures=0。
暂停期间三次观察均为1369帧/state2；继续后增长至2523帧/state1；停止后三次
保持2527帧/state0、DAC关闭。已目视检查 `06-resume-6.png`，播放器皮肤完整。

实际DAC录音2737924个双声道帧，捕获错误为空，PCM SHA-256：
`95d0d1d12d5a8909bdb1480fb5b357e99683b232030a7a4e2cc89152a19d5ca0`。
60秒墙钟录音上限未覆盖完整暂停/停止观察区间；delivery-analysis 明确将两项
continuous_silence_verified 标为false，因此本次不声称完整静音区间或逐样本接续通过。
未对新布局执行所有NPE/退出释放回归，也未替换用户正在使用的旧包。
不能把构建哈希通过、测试音或局部控制回归外推为全部 MP3、NPE 声音或完整模拟器完成。
