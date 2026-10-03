$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root 'runtime\python\python.exe'
$web = Join-Path $root 'scripts\web\np560_web.py'
$qemu = Join-Path $root 'bin\qemu-system-dmcu.exe'
$images = Join-Path $root 'images'
$device = Join-Path $root 'device\device.json'
foreach ($name in @('NP560.PRG', 'resident.bin', 'system.nand')) {
    $path = Join-Path $images $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "缺少镜像：$path。请下载 Release 中的三个镜像并放入 images 文件夹。"
    }
}
if (-not (Test-Path -LiteralPath $device -PathType Leaf)) {
    & $python $web --create-device $device --qemu $qemu `
        --firmware (Join-Path $images 'NP560.PRG') `
        --soc-rom (Join-Path $images 'resident.bin') `
        --nand-checkpoint (Join-Path $images 'system.nand') `
        --boot-mode firmware-vma03 --soc-rom-skeleton `
        --rom-mp3-hle-base 138790 --rom-mp3-arena-image 93952 `
        --rom-npe-codec-owned --instruction-clock --icount-shift 0 --realtime
    if ($LASTEXITCODE -ne 0) { throw '创建设备失败' }
}
$url = 'http://127.0.0.1:8765/'
Write-Host "模拟器地址：$url"
Write-Host '保持此窗口运行；关闭窗口会停止模拟器。NAND 写入保存在 device 目录。'
& $python $web --device $device --host 127.0.0.1 --port 8765 `
    --run-log-dir (Join-Path $root 'device\web-runs')
if ($LASTEXITCODE -ne 0) { throw "模拟器退出码：$LASTEXITCODE" }
