# Windows 原生运行

NP560+ 模拟器可以直接在 Windows 运行，不需要 WSL。核心程序是
`qemu-system-dmcu.exe`；网页前端和 NPE 音效服务由 Windows Python 启动。
QMP 和音效服务仅在 `127.0.0.1` 上使用本机 TCP，网页端口由启动参数指定。

## 构建

安装 MSYS2 UCRT64 的 C 编译器、Meson、Ninja、Python/distlib，以及
GLib、Pixman、zlib 开发包。在 PowerShell 中执行：

```powershell
.\scripts\build_np560_windows.ps1 -BuildDir 'E:\qemu-dmcu-win-build'
```

脚本只编译 `dmcu-softmmu` 目标，产物为构建目录中的
`qemu-system-dmcu.exe`。运行时需要 MSYS2 UCRT64 的 DLL；启动脚本会把
`C:\msys64\ucrt64\bin` 放在本进程的 PATH 前面。

## 创建设备和启动

先准备依法取得的 `NP560.PRG`、仓库工具构建的 `resident.bin`，以及完整
NAND checkpoint。只需首次创建设备配置，随后始终用相同的配置恢复进度：

```powershell
python .\scripts\web\np560_web.py --create-device 'E:\qemu-dmcu-win-build\device\device.json' `
  --qemu 'E:\qemu-dmcu-win-build\qemu-system-dmcu.exe' `
  --firmware 'C:\path\to\NP560.PRG' --soc-rom 'C:\path\to\resident.bin' `
  --nand-checkpoint 'E:\path\to\system.nand' `
  --boot-mode firmware-vma03 --soc-rom-skeleton `
  --rom-mp3-hle-base 138790 --rom-mp3-arena-image 93952 `
  --rom-npe-codec-owned --instruction-clock --icount-shift 0 --realtime

.\scripts\start_np560_windows.ps1 -Device 'E:\qemu-dmcu-win-build\device\device.json' -Port 8921
```

然后在 Windows 浏览器打开 `http://127.0.0.1:8921/`。NAND 的写入保存在
设备配置旁边的 `.npj` journal，原始 checkpoint 不变。不要让两个实例同时
使用同一个设备配置。Windows 版目前不支持 journal 自动压缩；超过压缩
阈值后会继续追加记录，但可能占用更多磁盘空间。

空闲后原厂程序可能主动关闭 LCD：这不是网页或 QEMU 退出。在已验证的关屏
路径上，按住机身上方向键（电脑 `↑`）可唤醒；短点 `Enter` 不会唤醒。
