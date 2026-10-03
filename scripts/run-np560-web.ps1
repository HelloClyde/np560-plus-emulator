[CmdletBinding()]
param(
    [string]$Device,
    [string]$CreateDevice,
    [string]$Qemu = 'E:\qemu-dmcu-build\qemu-system-dmcu',
    [string]$Firmware,
    [string]$MaskRom,
    [string]$SocRom,
    [string]$SocRomBundle,
    [switch]$ExperimentalEq,
    [switch]$SocRomSkeleton,
    [uint32]$RomMp3HleBase = 0,
    [uint32]$RomMp3ArenaImage = 0,
    [string]$RomNpeCodecSocket,
    [string]$RomNpeCodecDll,
    [switch]$RomNpeCodecOwned,
    [string]$RomNpeCodecPythonPath,
    [switch]$InstructionClock,
    [switch]$ProfileInstructionOpcodes,
    [switch]$Realtime,
    [switch]$FullControlObservers,
    [string]$UsbLoader,
    [string]$BurnCode,
    [string]$DriverCode,
    [string]$NandImage,
    [string]$NandCheckpoint,
    [string]$NandSaveOnExit,
    [string]$NandJournal,
    [ValidateSet('firmware', 'firmware-vma03', 'usb', 'burn', 'driver')]
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
    [string]$ListenAddress = '127.0.0.1',
    [string]$RunLogDir,
    [string]$ShutdownToken,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
# wslpath emits UTF-8. A hidden Windows PowerShell process may otherwise
# decode the Chinese factory-firmware directory using the legacy code page.
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
if ($Realtime -and (-not $InstructionClock -or (-not $Device -and $IcountShift -ne 0))) {
    throw 'Realtime requires InstructionClock and IcountShift 0 (or a device bound to shift 0).'
}
$distro = 'Ubuntu2'
$scriptWindows = Join-Path $PSScriptRoot 'web\np560_web.py'
if (-not $Firmware) {
    $Firmware = Join-Path (Split-Path $PSScriptRoot -Parent) 'NP560+V3.80版系统升级程序\NP560.PRG'
}

if ($Device -and $CreateDevice) {
    throw 'Device and CreateDevice cannot be used together.'
}
if ($Device) {
    foreach ($boundSetting in @(
        'Firmware', 'MaskRom', 'SocRom', 'SocRomBundle', 'SocRomSkeleton', 'UsbLoader', 'BurnCode',
        'DriverCode', 'NandImage', 'NandCheckpoint', 'NandSaveOnExit', 'NandJournal',
        'BootMode', 'RomHle', 'HleUi', 'IcountShift', 'StartupContext', 'AdcLevel',
        'ExternalPower', 'RomNpeCodecSocket', 'RomNpeCodecDll',
        'RomNpeCodecOwned', 'RomNpeCodecPythonPath'
    )) {
        if ($PSBoundParameters.ContainsKey($boundSetting)) {
            throw "Device configuration binds $boundSetting; remove the override."
        }
    }
    if (-not (Test-Path -LiteralPath $Device -PathType Leaf)) {
        throw "Device configuration not found: $Device"
    }
}
$requiredFiles = @($scriptWindows)
if (-not $Device) { $requiredFiles += $Firmware }
foreach ($path in $requiredFiles) {
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
if ($ExperimentalEq -and -not $SocRomBundle) { throw 'ExperimentalEq requires SocRomBundle.' }
if ($SocRomBundle) {
    if (-not (Test-Path -LiteralPath $SocRomBundle -PathType Container)) {
        throw "ROM bundle directory not found: $SocRomBundle"
    }
    foreach ($setting in @('SocRom', 'MaskRom', 'SocRomSkeleton', 'RomMp3HleBase', 'RomMp3ArenaImage', 'RomNpeCodecSocket', 'RomNpeCodecDll', 'RomNpeCodecOwned', 'RomNpeCodecPythonPath', 'RomHle', 'HleUi')) {
        if ($PSBoundParameters.ContainsKey($setting)) { throw "SocRomBundle binds $setting; remove the override." }
    }
}
if ($SocRomSkeleton -and -not $SocRom) {
    throw 'SocRomSkeleton requires SocRom.'
}
if (@($RomNpeCodecDll, $RomNpeCodecSocket, $RomNpeCodecOwned.IsPresent).Where({ [bool]$_ }).Count -gt 1) {
    throw 'RomNpeCodecDll, RomNpeCodecOwned and RomNpeCodecSocket are mutually exclusive.'
}
if ($RomNpeCodecPythonPath -and -not $RomNpeCodecDll) {
    throw 'RomNpeCodecPythonPath requires RomNpeCodecDll.'
}
if ($RomNpeCodecDll -and -not (Test-Path -LiteralPath $RomNpeCodecDll -PathType Leaf)) {
    throw "NPE codec DLL not found: $RomNpeCodecDll"
}
if ($RomNpeCodecPythonPath -and -not (Test-Path -LiteralPath $RomNpeCodecPythonPath -PathType Container)) {
    throw "NPE codec dependency directory not found: $RomNpeCodecPythonPath"
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
if ((-not $Device -or $PSBoundParameters.ContainsKey('Qemu')) -and
    -not (Test-Path -LiteralPath $Qemu -PathType Leaf)) {
    throw "QEMU binary not found: $Qemu"
}

$scriptPathWindows = (Resolve-Path -LiteralPath $scriptWindows).Path -replace '\\', '/'
$wslScript = (& wsl.exe -d $distro -- wslpath -a -- $scriptPathWindows).Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslScript) {
    throw 'Unable to translate paths into WSL.'
}

$pythonArguments = @($wslScript, '--host', $ListenAddress, '--port', [string]$Port)
if (-not $Device -or $PSBoundParameters.ContainsKey('Qemu')) {
    $qemuWindows = (Resolve-Path -LiteralPath $Qemu).Path -replace '\\', '/'
    $wslQemu = (& wsl.exe -d $distro -- wslpath -a -- $qemuWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslQemu) { throw 'Unable to translate QEMU path into WSL.' }
    $pythonArguments += @('--qemu', $wslQemu)
}
if ($Device) {
    $deviceWindows = (Resolve-Path -LiteralPath $Device).Path -replace '\\', '/'
    $wslDevice = (& wsl.exe -d $distro -- wslpath -a -- $deviceWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslDevice) { throw 'Unable to translate device path into WSL.' }
    $pythonArguments += @('--device', $wslDevice)
} else {
    $firmwareWindows = (Resolve-Path -LiteralPath $Firmware).Path -replace '\\', '/'
    $wslFirmware = (& wsl.exe -d $distro -- wslpath -a -- $firmwareWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslFirmware) { throw 'Unable to translate firmware path into WSL.' }
    $pythonArguments += @('--firmware', $wslFirmware, '--boot-mode', $BootMode,
        '--startup-context', [string]$StartupContext, '--adc-level', [string]$AdcLevel,
        '--external-power', [string]$ExternalPower)
}
if ($CreateDevice) {
    $deviceWindows = [IO.Path]::GetFullPath($CreateDevice) -replace '\\', '/'
    $wslCreateDevice = (& wsl.exe -d $distro -- wslpath -a -- $deviceWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslCreateDevice) { throw 'Unable to translate new device path into WSL.' }
    $pythonArguments += @('--create-device', $wslCreateDevice)
}
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
if ($InstructionClock) { $pythonArguments += '--instruction-clock' }
if ($ProfileInstructionOpcodes) { $pythonArguments += '--profile-instruction-opcodes' }
if ($Realtime) { $pythonArguments += '--realtime' }
if ($FullControlObservers) { $pythonArguments += '--full-control-observers' }
if ($RomMp3HleBase) {
    $pythonArguments += @('--rom-mp3-hle-base', [string]$RomMp3HleBase)
}
if ($RomMp3ArenaImage) {
    $pythonArguments += @('--rom-mp3-arena-image', [string]$RomMp3ArenaImage)
}
if ($RomNpeCodecSocket) {
    $pythonArguments += @('--rom-npe-codec-socket', $RomNpeCodecSocket)
}
if ($RomNpeCodecDll) {
    $dllWindows = (Resolve-Path -LiteralPath $RomNpeCodecDll).Path -replace '\\', '/'
    $wslDll = (& wsl.exe -d $distro -- wslpath -a -- $dllWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslDll) { throw 'Unable to translate NPE codec DLL path into WSL.' }
    $pythonArguments += @('--rom-npe-codec-dll', $wslDll)
}
if ($RomNpeCodecOwned) { $pythonArguments += '--rom-npe-codec-owned' }
if ($RomNpeCodecPythonPath) {
    $depsWindows = (Resolve-Path -LiteralPath $RomNpeCodecPythonPath).Path -replace '\\', '/'
    $wslDeps = (& wsl.exe -d $distro -- wslpath -a -- $depsWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslDeps) { throw 'Unable to translate NPE codec dependency path into WSL.' }
    $pythonArguments += @('--rom-npe-codec-pythonpath', $wslDeps)
}
if ($ShutdownToken) {
    $pythonArguments += @('--shutdown-token', $ShutdownToken)
}
if ($RunLogDir) {
    $runLogWindows = [IO.Path]::GetFullPath($RunLogDir)
    [IO.Directory]::CreateDirectory($runLogWindows) | Out-Null
    $wslRunLog = (& wsl.exe -d $distro -- wslpath -a -- ($runLogWindows -replace '\\', '/')).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslRunLog) {
        throw 'Unable to translate the run log directory into WSL.'
    }
    $pythonArguments += @('--run-log-dir', $wslRunLog)
}
if ($MaskRom) {
    $maskRomWindows = (Resolve-Path -LiteralPath $MaskRom).Path -replace '\\', '/'
    $wslMaskRom = (& wsl.exe -d $distro -- wslpath -a -- $maskRomWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslMaskRom) {
        throw 'Unable to translate the mask ROM path into WSL.'
    }
    $pythonArguments += @('--mask-rom', $wslMaskRom)
}
if ($SocRomBundle) {
    $bundleWindows = (Resolve-Path -LiteralPath $SocRomBundle).Path -replace '\\', '/'
    $wslBundle = (& wsl.exe -d $distro -- wslpath -a -- $bundleWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslBundle) { throw 'Unable to translate ROM bundle path into WSL.' }
    $pythonArguments += @('--soc-rom-bundle', $wslBundle)
    if ($ExperimentalEq) { $pythonArguments += '--experimental-eq' }
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
if ($NandJournal) {
    $journalWindows = [IO.Path]::GetFullPath($NandJournal)
    [IO.Directory]::CreateDirectory((Split-Path -Parent $journalWindows)) | Out-Null
    $wslJournal = (& wsl.exe -d $distro -- wslpath -a -- ($journalWindows -replace '\\', '/')).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslJournal) {
        throw 'Unable to translate the NAND journal path into WSL.'
    }
    $pythonArguments += @('--nand-journal', $wslJournal)
}

if ($CreateDevice) {
    & wsl.exe -d $distro -- python3 @pythonArguments
    exit $LASTEXITCODE
}
$url = "http://127.0.0.1:$Port"
if (-not $NoBrowser) {
    Start-Process $url
}
Write-Host "Starting NP560+ Emulator Web frontend at $url"
Write-Host 'Press Ctrl+C to stop QEMU and the Web server.'
& wsl.exe -d $distro -- python3 @pythonArguments
exit $LASTEXITCODE
