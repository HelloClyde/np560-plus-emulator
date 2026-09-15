# 新月奇缘导入（2026-09-16）

- 来源：`D:/Downloads/NP560plus游戏全集/新月奇缘.npe`，2,111,219 bytes。
- SHA-256：`b7a8837f8badcda8f80bbe22f0a133af6851cb738cacfcf660dc9b833d05801b`。
- 原厂文件 API 新增 `0:\应用程序\新月奇缘.npe`，拒绝覆盖已有文件，没有格式化。
- 全文件关闭后重新打开、读至 EOF，逐字节核对通过。
- 记录：`tmp/np560-xinyue-import-20260916-v1/report.json`，completed=true。
- 输入：`E:/qemu-dmcu-build/np560-mp3-tone-20260906-v1.nand`，未覆盖。
- 新输出：`E:/qemu-dmcu-build/np560-xinyue-20260916-v1.nand`。
- 输出 SHA-256：`375d953d0922a11ce0c3f2db99e56d9b1bf2cc27cec7892a9e343d570899447f`。

独立试玩：本机 `http://127.0.0.1:8808/`；LAN `http://192.168.31.89:8808/`。
首页/状态 API 可达，QEMU 启动后 faulted=false；尚未验证本游戏标题、玩法或声音兼容。
该 NAND 基于启动用镜像，不包含当前 8807 进程中新产生的进度或音效设置。
原 8807 未停止、未重启；需要原厂设置关闭音效，不是关闭浏览器声音按钮。

新实例启用持久化：增量 `E:/qemu-dmcu-build/np560-xinyue-20260916-v1.journal`；
完整保存目标 `E:/qemu-dmcu-build/np560-xinyue-20260916-live.nand`。
后续恢复必须使用完整保存镜像，或初始新镜像配套该 journal，不能遗漏增量。
重启后读回存档尚待验证，不把 journal 开启等同于游戏存档已验收。
