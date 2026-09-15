# 天降风云 V1.3 导入（2026-09-16）

## 来源与完整性

- 来源：`D:/Downloads/NP560plus游戏全集/天降风云V1.3.npe`。
- 长度：3,751,913 bytes。
- SHA-256：`df4b52df6b69e1105a5ea6100e43f35f832ed859c10cb8714879e44ad4d8cb40`。
- guest 文件：`0:\应用程序\天降风云.npe`，只改导入名称，游戏内容未改。
- 原名称 `天降风云V1.3.npe` 在原厂打开检查返回 `(-10,-8)`，未创建；
  简化名称返回已确认的缺失结果 `(-10,-7)`，随后创建、写入成功。
- 原厂文件 API 写入后关闭、重新打开读到 EOF，全文件逐字节比较通过。
- 记录：`tmp/np560-tjfy13-import-20260916-v2/report.json`，completed=true。

## NAND 与切换状态

导入前通过 8808 的 `/api/nand/save` 导出当时的完整 NAND：
`E:/qemu-dmcu-build/np560-xinyue-20260916-live.nand`。
输入 SHA-256：`034a9c73bc9887d5f96f6940d7ecde97b12ac2f25fe1b4e68142ba82cd39e539`。
包含导出时已有文件、原厂设置和已保存数据；不包含 guest RAM 中未保存进度。
未格式化、未覆盖已有游戏。原 8808 在导入期间保持运行。

新输出：`E:/qemu-dmcu-build/np560-tjfy13-20260916-v2.nand`。
输出 SHA-256：`4a079e95b62597388ce7a1b8c9cd3ce20d3480783084ba518a3f3068d6b9b2e9`。
用户确认后已重启并替换 8808。切换前旧 journal 仍为 SEQUENCE=3071，
与导出时一致；旧进程正常退出（code 0），新入口通过 LAN 状态 API 验证，
加载 SHA 与上述输出一致、qemu_alive=true、faulted=false。
用户已确认当前版本《天降风云 V1.3》可以游玩；这不是完整剧情、存读档及声音兼容性验收。
对应 QEMU 源码提交：`0fa30bd31b032cbd07d8a85719734c1bd4c57cc2`。

新日志：`tmp/np560-tjfy13-web-20260916-v1/20260915T224938.099649Z-36-7a34ed05/`。
新 journal：`E:/qemu-dmcu-build/np560-tjfy13-20260916-v2.journal`。
完整保存目标：`E:/qemu-dmcu-build/np560-tjfy13-20260916-live.nand`。
试玩地址仍是 `http://192.168.31.89:8808/`，本机使用 `http://127.0.0.1:8808/`。

切换时使用新 journal 和保存目标，不可将旧镜像的 journal 重放到新镜像上。
若 8808 在本次导出后又保存了新数据，需要先重新导出，并基于最新快照重新导入，
不得直接切换后丢弃这些写入。
