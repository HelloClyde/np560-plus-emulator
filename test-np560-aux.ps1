[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$package = Join-Path (Split-Path $PSScriptRoot -Parent) 'NP560+V3.80版系统升级程序'
$firmware = Join-Path $package 'NP560.PRG'
$usbLoader = Join-Path $package 'USB_Loader_Noah.bin'
$burnCode = Join-Path $package 'BURN_NAND_FLASH_CODE.bin'
$qemu = '/mnt/e/qemu-dmcu-build/qemu-system-dmcu'
$usbTraceWindows = 'E:\qemu-dmcu-build\np560-usb-test.log'
$burnTraceWindows = 'E:\qemu-dmcu-build\np560-burn-test.log'

if (-not (Test-Path -LiteralPath 'E:\qemu-dmcu-build\qemu-system-dmcu' -PathType Leaf)) {
    throw 'QEMU binary not found. Run .\build-np560.ps1 first.'
}

function Convert-ToWslPath([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file not found: $Path"
    }
    $windowsPath = (Resolve-Path -LiteralPath $Path).Path -replace '\\', '/'
    $translated = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $windowsPath).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $translated) {
        throw "Unable to translate path into WSL: $Path"
    }
    return $translated
}

$wslFirmware = Convert-ToWslPath $firmware
$wslUsbLoader = Convert-ToWslPath $usbLoader
$wslBurnCode = Convert-ToWslPath $burnCode

& wsl.exe -d Ubuntu2 -- timeout 0.5s $qemu `
    -M "np560,boot-mode=usb,usb-loader=$wslUsbLoader" -bios $wslFirmware `
    -nographic -monitor none -no-reboot -d in_asm,unimp `
    -D /mnt/e/qemu-dmcu-build/np560-usb-test.log
& wsl.exe -d Ubuntu2 -- timeout 0.5s $qemu `
    -M "np560,boot-mode=burn,burn-code=$wslBurnCode" -bios $wslFirmware `
    -nographic -monitor none -no-reboot -d in_asm,unimp `
    -D /mnt/e/qemu-dmcu-build/np560-burn-test.log

$usbLog = Get-Content -LiteralPath $usbTraceWindows -Raw
$burnLog = Get-Content -LiteralPath $burnTraceWindows -Raw
$checks = [ordered]@{
    'USB loader reset mapping' = @($usbLog, '0x00001000:\s+sjmp 00:19f0')
    'USB loader entry mapping' = @($usbLog, '0x000019f0:\s+link #0x04')
    'USB loader internal call' = @($usbLog, '0x00001b06:\s+link #0x00')
    'USB loader initialization path' = @($usbLog, '0x00001132:\s+link #0x00')
    'burner vector mapping' = @($burnLog, '0x00506000:\s+sjmp 51:dc18')
    'burner entry mapping' = @($burnLog, '0x0051dc18:')
    'burner relocation helper' = @($burnLog, '0x0051d714:')
    'burner main entry' = @($burnLog, '0x00507566:')
}
foreach ($check in $checks.GetEnumerator()) {
    if ($check.Value[0] -notmatch $check.Value[1]) {
        throw "Auxiliary-image test failed: missing $($check.Key)."
    }
}
if (($usbLog + $burnLog) -match 'out of bounds|unsupported instruction|Invalid (read|write)') {
    throw 'Auxiliary-image test failed: invalid fetch or unsupported instruction.'
}
if ($burnLog -match '0x00000000:') {
    throw 'Auxiliary-image test failed: burner lost its return stack after changing DS1.'
}

Write-Host 'NP560+ QEMU auxiliary-image mapping test passed.'
