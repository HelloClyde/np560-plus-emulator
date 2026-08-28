[CmdletBinding()]
param(
    [string]$Firmware = (Join-Path (Split-Path $PSScriptRoot -Parent) 'NP560+V3.80版系统升级程序\NP560.PRG'),
    [string]$MaskRom,
    [string]$SocRom,
    [switch]$SocRomSkeleton,
    [string]$UsbLoader,
    [string]$BurnCode,
    [string]$DriverCode,
    [string]$NandImage,
    [string]$NandCheckpoint,
    [string]$NandSaveOnExit,
    [ValidateSet('firmware', 'usb', 'burn', 'driver')]
    [string]$BootMode = 'firmware',
    [switch]$RomHle,
    [switch]$HleUi,
    [switch]$LogUnimp,
    [ValidateRange(-1, 20)]
    [int]$IcountShift = -1,
    [uint32]$StartupContext = 0,
    [ValidateRange(0, 8)]
    [int]$AdcLevel = 8,
    [ValidateRange(0, 1)]
    [int]$ExternalPower = 0,
    [int]$Port = 8765,
    [string]$ShutdownToken,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$distro = 'Ubuntu2'
$qemu = '/mnt/e/qemu-dmcu-build/qemu-system-dmcu'
$scriptWindows = Join-Path $PSScriptRoot 'web\np560_web.py'

foreach ($path in @($Firmware, $scriptWindows)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file not found: $path"
    }
}
if ($MaskRom -and -not (Test-Path -LiteralPath $MaskRom -PathType Leaf)) {
    throw "Mask ROM not found: $MaskRom"
}
if ($SocRom -and -not (Test-Path -LiteralPath $SocRom -PathType Leaf)) {
    throw "SoC ROM not found: $SocRom"
}
if ($SocRom -and $MaskRom) {
    throw 'SocRom and MaskRom cannot be used together.'
}
if ($SocRomSkeleton -and -not $SocRom) {
    throw 'SocRomSkeleton requires SocRom.'
}
if ($UsbLoader -and -not (Test-Path -LiteralPath $UsbLoader -PathType Leaf)) {
    throw "USB loader not found: $UsbLoader"
}
if ($BurnCode -and -not (Test-Path -LiteralPath $BurnCode -PathType Leaf)) {
    throw "Burn code not found: $BurnCode"
}
if ($DriverCode -and -not (Test-Path -LiteralPath $DriverCode -PathType Leaf)) {
    throw "Driver code not found: $DriverCode"
}
if ($NandImage -and -not (Test-Path -LiteralPath $NandImage -PathType Leaf)) {
    throw "NAND image not found: $NandImage"
}
if ($NandCheckpoint -and -not (Test-Path -LiteralPath $NandCheckpoint -PathType Leaf)) {
    throw "NAND checkpoint not found: $NandCheckpoint"
}
if ($NandImage -and $NandCheckpoint) {
    throw 'NandImage and NandCheckpoint cannot be used together.'
}
if ($BootMode -eq 'usb' -and -not $UsbLoader) {
    throw 'BootMode usb requires -UsbLoader.'
}
if ($BootMode -eq 'burn' -and -not $BurnCode) {
    throw 'BootMode burn requires -BurnCode.'
}
if ($BootMode -eq 'driver' -and -not $DriverCode) {
    throw 'BootMode driver requires -DriverCode.'
}
if (-not (Test-Path -LiteralPath 'E:\qemu-dmcu-build\qemu-system-dmcu' -PathType Leaf)) {
    throw 'QEMU binary not found. Run .\build-np560.ps1 first.'
}

$firmwareWindows = (Resolve-Path -LiteralPath $Firmware).Path -replace '\\', '/'
$scriptPathWindows = (Resolve-Path -LiteralPath $scriptWindows).Path -replace '\\', '/'
$wslFirmware = (& wsl.exe -d $distro -- wslpath -a -- $firmwareWindows).Trim()
$wslScript = (& wsl.exe -d $distro -- wslpath -a -- $scriptPathWindows).Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslFirmware -or -not $wslScript) {
    throw 'Unable to translate paths into WSL.'
}

$pythonArguments = @(
    $wslScript, '--qemu', $qemu, '--firmware', $wslFirmware,
    '--boot-mode', $BootMode, '--startup-context', [string]$StartupContext,
    '--adc-level', [string]$AdcLevel,
    '--external-power', [string]$ExternalPower,
    '--port', [string]$Port
)
if ($RomHle -or $HleUi) {
    $pythonArguments += '--rom-hle'
}
if ($HleUi) {
    $pythonArguments += '--hle-ui'
}
if ($LogUnimp) {
    $pythonArguments += '--log-unimp'
}
if ($IcountShift -ge 0) {
    $pythonArguments += @('--icount-shift', [string]$IcountShift)
}
if ($ShutdownToken) {
    $pythonArguments += @('--shutdown-token', $ShutdownToken)
}
if ($MaskRom) {
    $maskRomWindows = (Resolve-Path -LiteralPath $MaskRom).Path -replace '\\', '/'
    $wslMaskRom = (& wsl.exe -d $distro -- wslpath -a -- $maskRomWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslMaskRom) {
        throw 'Unable to translate the mask ROM path into WSL.'
    }
    $pythonArguments += @('--mask-rom', $wslMaskRom)
}
if ($SocRom) {
    $socRomWindows = (Resolve-Path -LiteralPath $SocRom).Path -replace '\\', '/'
    $wslSocRom = (& wsl.exe -d $distro -- wslpath -a -- $socRomWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslSocRom) {
        throw 'Unable to translate the SoC ROM path into WSL.'
    }
    $pythonArguments += @('--soc-rom', $wslSocRom)
    if ($SocRomSkeleton) {
        $pythonArguments += '--soc-rom-skeleton'
    }
}
foreach ($optionalImage in @(
    @{ Value = $UsbLoader; Argument = '--usb-loader'; Label = 'USB loader' },
    @{ Value = $BurnCode; Argument = '--burn-code'; Label = 'burn code' }
    @{ Value = $DriverCode; Argument = '--driver-code'; Label = 'driver code' }
    @{ Value = $NandImage; Argument = '--nand-image'; Label = 'NAND image' }
    @{ Value = $NandCheckpoint; Argument = '--nand-checkpoint'; Label = 'NAND checkpoint' }
)) {
    if ($optionalImage.Value) {
        $imageWindows = (Resolve-Path -LiteralPath $optionalImage.Value).Path -replace '\\', '/'
        $wslImage = (& wsl.exe -d $distro -- wslpath -a -- $imageWindows).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $wslImage) {
            throw "Unable to translate the $($optionalImage.Label) path into WSL."
        }
        $pythonArguments += @($optionalImage.Argument, $wslImage)
    }
}
if ($NandSaveOnExit) {
    $saveWindows = [IO.Path]::GetFullPath($NandSaveOnExit)
    $saveParent = Split-Path -Parent $saveWindows
    if ($saveParent -and -not (Test-Path -LiteralPath $saveParent)) {
        [IO.Directory]::CreateDirectory($saveParent) | Out-Null
    }
    $saveWindows = $saveWindows -replace '\\', '/'
    $wslSave = (& wsl.exe -d $distro -- wslpath -a -- $saveWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslSave) {
        throw 'Unable to translate the NAND save path into WSL.'
    }
    $pythonArguments += @('--nand-save-on-exit', $wslSave)
}

$url = "http://127.0.0.1:$Port"
if (-not $NoBrowser) {
    Start-Process $url
}
Write-Host "Starting NP560+ QEMU Web frontend at $url"
Write-Host 'Press Ctrl+C to stop QEMU and the Web server.'
& wsl.exe -d $distro -- python3 @pythonArguments
exit $LASTEXITCODE
