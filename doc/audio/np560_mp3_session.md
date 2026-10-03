# MP3 状态对象与原厂 PCM 四缓冲的原生接通

日期：2026-09-07。

本次实现的是 guest 内完整状态对象：实际申请解码工作区，驱动输入环解码，将实际
PCM 交到原厂四缓冲，处理复位、关闭和重新打开。
**仍不是原厂 `01:4804/49F8` 单例入口已经安装，也不是音乐播放器已经能够播放。**
原厂入口没有传新状态对象指针，其根对象归属、回调和错误状态转换仍需接入。

## 所有权和行为

`scripts/build_np560_mp3_session.py` 生成 2954-byte DMCU 代码。新增内部 ABI
以 `DS0:R3` 指向一个稳定、单独拥有的 80-byte 对象，内含 18-byte lease 描述符、
原厂 26-byte 初始化参数及新状态字段。它不是把未知 `333E..33E5` 字段改名，
也不把第五个缓冲 `2984` 私占成永久句柄。测试中的对象同样通过原厂堆申请、锁定。

| 方法 | 实际行为 |
| --- | --- |
| create | 检查四块 X0 输出缓冲的范围、对齐、互不重叠及与对象分离；通过原厂 allocator 取得并锁定核心工作区，初始化解码器，清除四缓冲 |
| reset | 保留已申请对象，复位位储备/滤波/输入环状态，清除 A/B 两期 PCM，不释放后重新猜地址 |
| free_words | 返回实际输入环剩余 word 容量，与原厂 writer 消费位置保持同一状态 |
| step | 调用原生环适配，成功后复制两个声道的 576 项 PCM，完成两次复制后才发布新缓冲指针 |
| output | 在新对象参数之外，接受与原厂 `4954` 一致的两个栈上传入 far 输出参数；写入当前两通道的实际 far 指针 |
| release | 实际 free/unlock 核心工作区并清句柄/有效状态；重复关闭不再次操作已释放句柄，可在同一控制对象上重新创建 |

四块缓冲使用初始化参数提供的地址，不在 Web 补采样：

| 期 / 通道 | 原厂参数位置 | 当前原厂值 |
| --- | --- | --- |
| A / CH0 | 第一个 far | `00:1784` |
| B / CH0 | 第二个 far | `00:2084` |
| A / CH1 | 第三个 far | `00:1C04` |
| B / CH1 | 第四个 far | `00:2504` |

初始 output 返回已清零的 B 期；第一个成功 step 填 A，然后 B/A 交替。该内部顺序
满足原厂“处理前取旧指针、处理后再取当前指针”的可观察使用方式，不冒认原厂内部
初始 phase 字段。缺输入或错误不换期，未写的另一期保持原样；单声道的第二通道
由原生核心清零后同样复制。完成 reset 才使两期一起失效/清零。

新方法成功 step 返回 `R0=576/R2=0`，其它成功命令一般为 `0/0`，free_words
除外。错误沿用 ring 的 1..6，加 busy/already-open 7、closed 8、allocation 9、
core reset 10、release 11；后两层保留 DETAIL。释放失败保留可再次清理的打开状态。
**这些不是原厂错误码，不能把 `01:49F8` 直接跳转到 step**；原厂会读取 R0 bit0
和 `3346`，需要依据其消费者转换状态。NSEG 变体、全部失败组合还没有在本层验证。

对象访问使用已存在的 CRIT 机制保护 BUSY 的“读取、比较、分支、置位”四条指令。
BUSY 下的输出查询、处理、复位和释放均拒绝，不触碰其它调用者拥有的工作区。
结果状态先发布，再清 BUSY，避免释放锁后覆盖另一个调用者的新结果。构建时检查
全部六处窗口的精确指令形态。这个机制不代替所有者生命周期：销毁控制对象前仍必须
停止/注销原厂流回调，也没有据此宣称完整的音频中断并发已验证。

## ROM 与验证范围

当前 bundle：`tmp/np560-mp3-session-core-20260907-v3`。

- ROM SHA256：`144ef00c2eeeb2efd43257a20e0853f6500bc263be70e99284537a5d105fc486`。
- session 代码 SHA256：`618a27e40f8d8659e8459de45bd5703a83caf563fc2fec7d3311b55779bdca6d`。
- 入口：create `02:AE00`、reset `02:B21E`、free_words `02:B392`、step `02:B41E`、output `02:B5C6`、release `02:B6E8`。
- 16 组件、35 片段共 84584 bytes，原检查范围内余 22132 bytes；已知原厂入口仍受保护，未知间接入口是否占用空洞仍未证明。
- QEMU 沿用 `533dd1a47c08c2636e8921e046526ea31f0bf7a00f102a89705d1704f5d5d083`，本次未改 CPU、硬件映射、原 PRG、Web 或用户 NAND。

`scripts/tests/test_np560_mp3_session.py` 使用原厂 `25:77DA/31:5300` 申请并锁定
80-byte 控制对象，再由 session 自己管理内部 lease。输入是原文件的连续 bytes，
由原始 `16:E844` 写环；不向核心逐帧提供 host header 或 bit context。
每个成功 granule 的 PCM 从 output 返回的 **X0 原厂缓冲**采集，不从私有 PCM 偷读。
另保存每一步四块缓冲的完整内容，与当前/上一期的预期采样逐项核对；全部是只读对照，
不将 oracle 写回运行状态。

| `tmp/` 下最终报告 | 实际压缩输入 / 对象条件 | 控制检查 / 四缓冲核对的 PCM16 值 | 实际 PCM SHA256 |
| --- | --- | --- | --- |
| `np560-mp3-session-player-layout-20260907-v4` | MPEG1 三帧、六 granules；五个原厂尺寸的锁定邻居 | 171 / 16128 | `45c55c196537bc1f78f2bf5ddcfd9625a3a2ee75f3eca0a99049fc2453aba743` |
| `np560-mp3-session-mpeg2-20260907-v1` | MPEG2 三帧；同样五个邻居 | 141 / 9216 | `01355ba0caec1980b91d2d0e3ed14b7efd86bbecdc0cecb21f3b2d3212c62419` |
| `np560-mp3-session-mpeg25-20260907-v1` | MPEG2.5 三帧、单声道；空堆起步、icount5 | 136 / 9216 | `9e61fe03759475726ca81cf62533a887f7244ea63cc2e4ad013d26be10f8a41e` |

三组全部通过并正常退出 0。三组对独立离线 FFmpeg 的最大差异均为 1 PCM16
单位；MPEG2/2.5 的已知零 Info 帧处理与前次相同，没有裁剪 guest WAV、增益修正
或自动搜索延迟。它们仍是有限前缀；MPEG1 六 granules 仅 0.0784 秒声音，诊断运行
约 18.38 秒，显然不是实时播放性能。

五个邻居的 payload 是真实播放器已测到的 6172、3072、38、1536、3072 bytes。
本测试在隔离 caller 中用原厂 allocator 重新建立这个布局，不称作原厂播放器运行本身。
控制对象和核心都释放后，再归还邻居，核对实际空闲链和 handle bitmap 回到初态。
同时检查了错误配置不申请/擦除输出、重复打开、BUSY 拒绝、缺输入保留上一期、
reset 清零、重新打开、控制对象尾部及 `1782/2984/2E02` 的区外哨兵。
后两个地址确认未借用第五缓冲存储内部状态。原厂公共入口、DAC 回调和用户播放控制
未由本实验验证；不以这些检查数当作整机完成度。

同一 ROM 的原厂零输入冷启动也已通过，记录在
`tmp/np560-mp3-session-coldboot-20260907-v1/report.json`。未修改的完整 PRG 和
原 vendor-file-import-v3 NAND 启动到正常桌面，最后三次顶栏均为 0/5280 像素差异，
无缺失 ROM、未实现指令、非法控制或 NAND error，ROM HLE 关闭。已目视最终 LCD；
未保存 NAND，隔离进程正常关闭。这验证新链接未破坏该启动路径，不是播放器验收。

保留失败：

- `np560-mp3-session-player-layout-20260907-v1` 的隔离 caller 超过 4 KiB，构建前拒绝。
  去掉诊断 caller 中没有活跃寄存器需要保护的重复保存，未扩大对原 PRG 的覆盖范围。
- `np560-mp3-session-player-layout-20260907-v3` 使用中间 ROM v2，在 `02:B72A`
  遇到本次生成器错误编码的 `3F05`。CRIT 只有既有两位计数编码，不能发明五条窗口。
  改成预先装入 1、用 `3F03` 保护四条 test/set 指令；未给 CPU 添加该非法指令。
  新 ROM v3 的最终三组验证才是当前结果。旧 ROM v1 的部分通过不替代它们。

## 仍须完成的接入

1. 原厂单例入口如何定位、持有和释放这个实际控制对象；不能用未证实的静态 RAM
   位置代替所有权，也不能把外部 DAC 仍引用的缓冲随核心一起释放。
2. `46D4/46F2` 回调，`49F8` 的原厂 R0/3346 状态、EOF/跳转/格式变化与错误恢复。
3. 按原厂 DTU/DAC 时序交接缓冲、音量和播放控制，完成真正应用内发声及实时性能。
4. 低码率共用 `ACD8/AD92`、其它支持输入和 NPE ESAC 声音仍独立保留，未被缩减目标。

重建和复核沿用现有入口：

```text
python scripts/build_np560_mp3_resident.py --resident-rom tmp/np560-system-v380-vma03-resident-codec-holes-v1.bin --firmware "NP560+V3.80版系统升级程序/NP560.PRG" --output tmp/new-session-core
python scripts/tests/test_np560_mp3_session.py --qemu /path/to/qemu-system-dmcu --mp3 /path/to/input.mp3 --resident-bundle tmp/new-session-core --output tmp/new-session-test --limit 3 --player-neighbours
```

## 原厂帧状态消费接口：2026-09-07 后续

新增 `player_step`，仍由明确的 `DS0:R3` 所有者调用。它调用完整 session.step，
再转换原厂 `01:49F8` 消费方使用的状态，而不是将内部样本数原样返回。
原始 `16:E8B4..E8B8` 调用 49F8 后，用 BMOVN 将 R0 bit0 的反值写入 BIT8C.8；
`16:E930/E982` 以此走缺输入/耗尽后的淡出分支。内部成功结果 576 的 bit0 为零，
因此直接接入会错误触发该路径。

| session 实际结果 | player_step 的 R0 | 00:3346 |
| --- | --- | --- |
| R2=0 且实际产生 576 PCM/channel | 1 | 0 |
| 缺输入 R2=1，或当前 BUSY R2=7 | 0 | 0 |
| 其它实际失败/不符预期的成功长度 | 0 | 1 |

R2 保留内部详情。这里的非零错误 1 是新实现的通用失败指示：已核对的原厂消费方
只检查是否非零，**没有找回原厂数值错误码**。缺输入与文件 EOF 仍不能画等号，
是否结束文件由原厂流状态决定；没有在桥接中伪造 BIT89.7 或最终停止事件。
这也没有完成整个中断回调/根对象的并发与生命周期管理。

重建 bundle `tmp/np560-mp3-player-status-core-20260907-v1` 的 ROM SHA256：
`74e078db82296f421165ca7b1f26669253d0365694914a7592952f075bbf22a8`。
新增 68 bytes，16 组件合计 84652 bytes，检查范围剩余 22064 bytes。正式镜像的
已知原厂公共入口仍保留缺口；未更改 QEMU、原 PRG、Web 或用户 NAND。
该布局的 session 为 3022 bytes，入口 player_step 为 `02:0B8A`，代码 SHA256：
`63cef0160b9e71fd204ae4b00563be2611d0ac5e24809bff3bd6bc26dce3d40f`。
链接位置随组件尺寸调整，不能把上一版的 `02:AE00` 等入口沿用于本版。

现有 session 检查增加 `--original-player-consumer`：隔离 caller 用原厂 allocator
建立真实的对象/邻居，再用**仅存在于该诊断镜像**的 49F8/49BE 跳转绑定对象。
每个 granule 调用未修改的原厂 `16:E89C`，而不是在宿主复刻其分支；整个核对仍从
session.output 返回的 X0 缓冲采集实际 PCM。诊断对象地址不能用于正式 ROM，
测试绑定也没有安装到用户实例。

首个正确读取 BIT 空间的结果在 `tmp/np560-mp3-original-consumer-20260907-v2/report.json`：
172 个控制检查及 7 期/16128 个四缓冲 PCM16 值通过；原厂将六个成功 granules
识别为有输出，末尾缺输入则实际进入淡出，`4A76=16`，旧 PCM 保留。
6912 个有效 PCM16 值的 SHA256 仍为
`45c55c196537bc1f78f2bf5ddcfd9625a3a2ee75f3eca0a99049fc2453aba743`，
与离线 FFmpeg 最大差异 1。进程退出 0。**未运行完整播放器、DTU/DAC 或实时播放。**

同一 bundle 的 `tmp/np560-mp3-original-consumer-icount-20260907-v1/report.json`
亦通过，icount=5，178 个控制检查；新增 BUSY 非致命和已关闭 decoder 非零错误
检查，原厂六次消费与末尾淡出、四缓冲和 PCM 仍一致。诊断 ROM 含对象绑定，
其 SHA256 为 `caff816b48de37934e1770cefac09092c777fdd989e9782de7f51037d5b3d4e5`；
它不同于上述保留公共缺口的正式 bundle。所有隔离进程已正常退出 0。

未加测试绑定的 bundle 也通过原厂零输入冷启动：
`tmp/np560-mp3-player-status-coldboot-20260907-v1/report.json`，95.73 秒，
最后三次顶栏 0/5280 像素差异，无 ROM_MISSING/UNSUPPORTED/INVALID_CONTROL
或 NAND error，ROM HLE 关闭。最终 LCD 已目视核对；未保存 NAND，进程正常关闭。

保留 v1 失败：测试曾把 BIT8C.8 当作 SFR REG8C 的 bit8 读取，错误地读到零。
改用原厂相同位地址空间的 `BMOV BIT70.0,BIT8C.8` 读取；没有修改 CPU 或改低期望值。
该失败发生于控制检查，不能用底层 run 的 `passed session` 宣称整个实验通过。

### 所有者接入的新约束

原厂 `08:2F22` 把四个 far 回调存入 `4A9C/4AA0/4AA4/4AA8`，分别占两 word。
`08:3AA0..3AB0` 会经返回栈实际调用第四个回调，不能将它当成闲置 root 指针。
`2F:A778..A7BC` 的普通 MP3 配置依次提供 `16:E9B2/16:EA42/16:EC34`，
第四个来自 `51:2A18/2A1A`；模式为 8011。`4A52..4A5E` 是计时/状态，
原厂 `08:37F4` 对它们进行真实进位累加，也不是回调或私有对象槽。

已核对的 `08:3262` 停止链调用 `24:9AB8`、`08:475E`、`08:3906` 和
`08:3292`（另有 BIT88.11 分支）。其中没有已找到的 codec 堆释放接口；
`08:3292` 清传输/计时状态，但没有清上述回调表。不能将它直接命名为 decoder destroy。
原厂 codec 可能使用静态状态；这是推断，不能当作已恢复的内存布局。
新实现用了堆 lease，退出后归还内存仍是正式接入必须完成的工作，而不是忽略的优化项。
