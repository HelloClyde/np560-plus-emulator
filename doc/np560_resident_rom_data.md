# Resident ROM：补齐数据总线读取

日期：2026-09-07。VMA03 模式中的 `01:0000..02:FFFF` 已能通过普通 DS 数据访问
读取同一份只读 ROM；未加入 MP3 专用映射。系统冷启动与实际 MP3 熵解码的 ROM
放置验证通过。后续完整核心已放入受保护的 ROM 空洞并验证 PCM，见
[MP3 核心 4.16](np560_mp3_guest_decoder.md#416-完整解码核心的-resident-rom-放置)；
**原厂播放器接口和实时播放仍未接通**。以下保留本次通用数据映射的原始证据范围。

## 依据与范围

[CN1916884A 原件](../tmp/cnpatent/CN1916884A.pdf) 的说明书 d59/d61/d64/d70/d71
（本地提取编号）描述了内部程序存储器同时可供指令和操作数读取。已目视 PDF
第 128 页图 2、第 129 页图 3/4：低段包含 X RAM、Y RAM、DPRAM 和 SFR，
内部程序 ROM 从 `01:0000` 开始；CS 使用 8+16 位，DS 使用 9+15 位拼成地址。
没有从“ROM”名字推定某条新指令或另造表读取硬件。

专利图中的内部 ROM 上界是 `20:FFFF`，但当前 VMA03 板级模型把已装入 PRG 的
`03:0000..42:FFFF` 作为共享可写程序/数据 RAM。此次只补该模型中没有被 PRG
覆盖的 resident 区间：`[01:0000,min(镜像已载入长度,03:0000))`。
这不是证明所有原厂片选/重映射语义，亦未将旧 shifted-NOR 诊断模式一起改写。

## 确定性反例与实现

旧 QEMU `d26b7ce7f17c8345a2a2604a1c18c7c960549640ae0ebebb8458f8ea5e577372`
只有零散已知 ROM 数据岛，通用低端 resident 内容只映射在 code bus。
`scripts/test_np560_resident_data.py` 在同一段 ROM 中放普通立即数返回代码和
常量，guest 自己读写，不注入运行中内存。旧核心实际表现为：

- 调用 `01:0800` 中的 `MOV R0,#1234; RETS` 得到 `1234`。
- DS0=2、logical `0802` 却读到 `0000`，不是代码立即数字 `1234`。
- ROM 常量地址经数据写入后可读回 `BEEF/5555`，原指令视图却保持原值。

反例记录 `tmp/np560-resident-data-before-20260907-v1/report.json` 为失败，
没有因为 CPU 能执行 ROM 而把数据访问判为正确。

`qemu-dmcu/hw/dmcu/np560.c` 新增一个通用 data alias，直接共享既有不可写
`soc_rom_region` 的 backing。按已载入长度截断，不将 `00` 段或 VMA03 PRG
区域覆盖成 ROM；也不检查应用名、表地址或当前 PC 来选择返回值。
新 QEMU SHA256：
`533dd1a47c08c2636e8921e046526ea31f0bf7a00f102a89705d1704f5d5d083`。

## 验证结果

`tmp/np560-resident-data-after-20260907-v2/report.json` 四例全部通过：完整/短 ROM，
普通/icount=5 执行。覆盖 `10000/17FFE/18000/1FFFE/20000/27FFE/28000/2FFFE`
边界、DS0/DS1 读同一字、word/byte 写 ROM 不变、代码前后不变；X/Y RAM、DPRAM、
FP 内部访问仍可写。`03:2000` 的 RAM 代码由 guest 修改立即数后，执行立即取得新值。
短 ROM 的数据映射不会延伸到未载入文件范围。

首次 after-v1 的普通例通过，下一子进程在 Linux 动态链接器 `dl_open_worker`
断言退出，未打开 QMP；日志已保存为该目录的 `startup-loader-failure.log`。
确认该进程结束后重跑完整 v2，不能把环境启动失败说成 CPU 执行通过。

冷启动：`tmp/np560-resident-data-coldboot-20260907-v1/report.json`，90.24 秒通过。
沿用原 PRG `d555609e...`、resident ROM `a243f8ba...`、原厂导入 NAND `7783876b...`，
零输入启动，末三次顶栏比较均为 0/5280 像素差异，无缺失 ROM、非法控制或未实现指令，
NAND ERROR=0。已目视 final.png 的顶栏、学习列表、开始与时间；该结果不代表所有应用。
隔离 QEMU 正常退出 0；没有导出/覆盖 NAND、替换用户实例或新建大镜像。

## 对 MP3 的直接作用

已有 Huffman 组件支持显式 code/table 地址。复用原测试的 `--resident-rom` 模式，
将代码放在 `01:2400`、码表放在 `01:C000`；每次先检查目标全为原镜像的 `0F00`
空洞，再只在隔离副本中装入这两段。源 ROM 文件不变，也未改原厂入口。

- 代码 690 bytes，SHA `0f001075b6a4fa7c4f4064e990baecd3e2216f522c73aa7e1ba9a05e801743aa`。
- 表 5708 bytes，SHA `d4045cdfb9279b2fc8ff1d8ae72abe517230cc247ed864ab7d4a230f5a8e662f`。
- `tmp/np560-mp3-resident-entropy-20260907-v1/report.json`：39 组、6734 次
  符号/位读取验证通过；包括所有有效书、无效书、linbits/sign、短输入回滚、count1、
  far 指针跨 bank 与 icount。独立核对 4995 个码字；执行前/后代码和表均未改变。

这是实际算法用通用数据总线读取 resident 码表，不是只读测试哨兵或宿主解码。
此地址只是核对后的组件放置实验，不是完整 ROM 链接方案；其余组件及大表必须重新
布局并保留原厂入口。特别是重定标表目前依赖连续且 bank 对齐的地址，而现有 ROM
空洞分散，不能将整包诊断地址平移、覆盖原厂函数，或把空洞数量当作接入完成。
