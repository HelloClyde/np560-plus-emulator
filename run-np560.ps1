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
    [ValidateSet('firmware', 'usb', 'burn', 'driver')]
    [string]$BootMode = 'firmware',
    [switch]$RomHle,
    [switch]$HleUi,
    [uint32]$StartupContext = 0,
    [switch]$Trace,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$QemuArguments
)

$ErrorActionPreference = 'Stop'
$distro = 'Ubuntu2'
$qemu = '/mnt/e/qemu-dmcu-build/qemu-system-dmcu'

if (-not (Test-Path -LiteralPath $Firmware -PathType Leaf)) {
    throw "Firmware not found: $Firmware"
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
    throw 'SocRomSkeleton requires -SocRom.'
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
$wslFirmware = (& wsl.exe -d $distro -- wslpath -a -- $firmwareWindows).Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslFirmware) {
    throw 'Unable to translate the firmware path into WSL.'
}

$machineOptions = @(
    'np560', "boot-mode=$BootMode",
    "rom-hle=$(if ($RomHle -or $HleUi) { 'on' } else { 'off' })",
    "hle-ui=$(if ($HleUi) { 'on' } else { 'off' })",
    "startup-context=$StartupContext"
)
if ($MaskRom) {
    $maskRomWindows = (Resolve-Path -LiteralPath $MaskRom).Path -replace '\\', '/'
    $wslMaskRom = (& wsl.exe -d $distro -- wslpath -a -- $maskRomWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslMaskRom) {
        throw 'Unable to translate the mask ROM path into WSL.'
    }
    $machineOptions += "mask-rom=$wslMaskRom"
}
if ($SocRom) {
    $socRomWindows = (Resolve-Path -LiteralPath $SocRom).Path -replace '\\', '/'
    $wslSocRom = (& wsl.exe -d $distro -- wslpath -a -- $socRomWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslSocRom) {
        throw 'Unable to translate the SoC ROM path into WSL.'
    }
    $machineOptions += "soc-rom=$wslSocRom"
    if ($SocRomSkeleton) {
        $machineOptions += 'soc-rom-skeleton=on'
    }
}
foreach ($optionalImage in @(
    @{ Value = $UsbLoader; Property = 'usb-loader'; Label = 'USB loader' },
    @{ Value = $BurnCode; Property = 'burn-code'; Label = 'burn code' }
    @{ Value = $DriverCode; Property = 'driver-code'; Label = 'driver code' }
    @{ Value = $NandImage; Property = 'nand-image'; Label = 'NAND image' }
    @{ Value = $NandCheckpoint; Property = 'nand-checkpoint'; Label = 'NAND checkpoint' }
)) {
    if ($optionalImage.Value) {
        $imageWindows = (Resolve-Path -LiteralPath $optionalImage.Value).Path -replace '\\', '/'
        $wslImage = (& wsl.exe -d $distro -- wslpath -a -- $imageWindows).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $wslImage) {
            throw "Unable to translate the $($optionalImage.Label) path into WSL."
        }
        $machineOptions += "$($optionalImage.Property)=$wslImage"
    }
}
$machine = $machineOptions -join ','

$arguments = @(
    '-M', $machine
    '-bios', $wslFirmware
    '-nographic'
    '-monitor', 'none'
    '-no-reboot'
)
if ($Trace) {
    $arguments += @('-d', 'in_asm,unimp', '-D', '/mnt/e/qemu-dmcu-build/np560-trace.log')
    Write-Host 'Trace: E:\qemu-dmcu-build\np560-trace.log'
}
if ($QemuArguments) {
    $arguments += $QemuArguments
}

Write-Host 'Starting NP560+ QEMU. Press Ctrl+C to stop.'
& wsl.exe -d $distro -- $qemu @arguments
exit $LASTEXITCODE
