# NP560+ 经典游戏 NAND（2026-10-02）

这是一份本机可试玩的**完整 NAND data/OOB checkpoint**，不是原厂 mask-ROM
转储，也不表示系统升级/恢复的全部硬件和软件功能已实现。

## 镜像与设备

- 最终镜像：`E:/qemu-dmcu-build/np560-classics-20261002-08.nand`，
  553,648,192 字节，SHA-256
  `d18aa701effcbdaa759c33a6a75b8c882cb2c34e7459126f21c0f8bab7bf75ce`。
- 只读输入底图：`E:/qemu-dmcu-build/np560-tjfy13-20260916-v2.nand`，
  SHA-256 `4a079e95b62597388ce7a1b8c9cd3ce20d3480783084ba518a3f3068d6b9b2e9`。
  其上已有《英雄传奇》《新月奇缘》《天降风云 V1.3》；上游来自完整原厂包
  烧录及原厂文件 API 导入，不重写底图或既有存档。
- 新设备：`E:/qemu-dmcu-build/np560-classics-device-20261002-v1/device.json`；
  同目录 `device.npj` 是专属持久 NAND 增量日志。启动时只传 `-Device`，
  不要把此日志重放到其它底图。
- 本地入口：`http://127.0.0.1:8920/`。当前默认播放器 ROM 包为
  `tmp/np560-player-owned-npe-20261001-v1/`（SHA-256 `18cca3e8…`），
  缺失 NPE format-13/mode-5 服务使用自有 HLE。

## 游戏目录

按本机 `D:/Downloads/NP560plus游戏全集/` 每款保留一个版本；重复旧版不导入。
客机的四汉字短文件名只是目录别名，NPE 文件内容未改。

| 来源文件 | 客机列表名 |
| --- | --- |
| `英雄传奇.npe` | `英雄传奇.npe` |
| `新月奇缘.npe` | `新月奇缘.npe` |
| `天降风云V1.3.npe` | `天降风云.npe` |
| `三分天下.npe` | `三分天下.npe` |
| `阿诺创世纪.npe` | `阿诺创世.npe` |
| `诺亚论剑.npe` | `诺亚论剑.npe` |
| `天机之江湖启示录.npe` | `天机江湖.npe` |
| `天明游戏V1.3.npe` | `天明游戏.npe` |
| `我的世界.npe` | `我的世界.npe` |
| `新仙剑后传.npe` | `新仙剑传.npe` |
| `异域传说3.npe` | `异域传说.npe` |

`异域传说2.npe` 与 3 的 SHA-256 相同；1 的字节不同，本次按一个系列
保留 3。未声称所有 11 款的剧情、音效和存档均可完整游玩。

## 构建和验收证据

- 本次新增八款均经原厂文件命令创建、写入、关闭、重新打开、读至 EOF，
  与宿主源逐字节一致；报告为 `tmp/np560-classics-20261002-import-01/`
  和 `tmp/np560-classics-20261002-build/import-02..08/report.json`。
  导入使用诊断 RAM 传输替代 USB 数据交付，文件系统操作仍由客机执行。
- 全部原厂 V3.80 包 NAND payload 43,963,392 字节（含填充）零差异，
  85,866 个对应 sector ECC 零错误；详见
  `tmp/np560-classics-20261002-build/payload-verification.json`。
  全镜像 ECC 扫描另得 `137954/137954` 匹配。
- 使用上述最终镜像和设备配置冷启动，Web/QEMU/NPE 解码服务均存活；
  原厂桌面、游戏列表前后两屏正常呈现。截图：
  `tmp/np560-classics-20261002-build/boot.png`、`game-list.png`、
  `game-list-scroll.png`、`ready.png`。菜单时 `ROM_MISSING=none`、
  `INVALID_CONTROL=none`、`UNSUPPORTED=none`，NAND `ERROR=0`。

## 不能称为“系统恢复全部功能”的部分

完整 NAND 包含原厂 V3.80 烧录的系统数据、分区和本次游戏文件；但真机
mask-ROM 01/02 尚无完整转储，模拟器对登记的缺失服务使用 HLE，USB
硬件传输、原厂升级/恢复全流程、异常断电和整机快照尚未完成。镜像完整性
与这些运行功能是两回事。这里的下载合集文件也没有逐字节对应的原厂发布
证明，不应称为已认证的官方下载版本。
