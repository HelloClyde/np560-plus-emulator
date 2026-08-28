[CmdletBinding()]
param(
    [ValidateRange(0, 0xFFFF)]
    [int]$Command = 1,
    [int]$DurationMs = 500,
    [switch]$Trace,
    [switch]$CpuTrace
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$package = Join-Path $root 'NP560+V3.80版系统升级程序'
$burnCode = Join-Path $package 'BURN_NAND_FLASH_CODE.bin'
$qemu = '/mnt/e/qemu-dmcu-build/qemu-system-dmcu'
$traceWindows = 'E:\qemu-dmcu-build\np560-burn-command.log'
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$firmware = Join-Path $temporaryRoot (
    'np560-burn-command-' + [guid]::NewGuid().ToString('N') + '.bin')

function Set-Word([byte[]]$Image, [int]$Offset, [uint16]$Value) {
    $Image[$Offset] = $Value -band 0xFF
    $Image[$Offset + 1] = ($Value -shr 8) -band 0xFF
}

function Add-StoreWord(
    [byte[]]$Image,
    [ref]$Offset,
    [uint16]$Address,
    [uint16]$Value
) {
    Set-Word $Image $Offset.Value 0x68F0 # MOV R0, #value
    Set-Word $Image ($Offset.Value + 2) $Value
    Set-Word $Image ($Offset.Value + 4) 0xA8F0 # MOV [address], R0
    Set-Word $Image ($Offset.Value + 6) $Address
    $Offset.Value += 8
}

function Convert-ToWslPath([string]$Path) {
    $windowsPath = (Resolve-Path -LiteralPath $Path).Path.Replace(
        [char]92, [char]47)
    $translated = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $windowsPath).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $translated) {
        throw "Unable to translate path into WSL: $Path"
    }
    return $translated
}

$image = [byte[]]::new(0x400000)
$offset = 0
Set-Word $image $offset 0x6810 # MOV DS0, #0x00A0 (physical 0x500000)
Set-Word $image ($offset + 2) 0x00A0
$offset += 4
Add-StoreWord $image ([ref]$offset) 0x0008 ([uint16]$Command)

# Values written by UpdateAll.exe for command 1.  The USB protocol reverses
# byte order, so these are the words observed by DMCU after transmission.
Add-StoreWord $image ([ref]$offset) 0x0034 0x0100
Add-StoreWord $image ([ref]$offset) 0x0036 0x6A4F
Add-StoreWord $image ([ref]$offset) 0x0094 0x0200
Set-Word $image $offset 0xAD50 # SJMP 50:6000
Set-Word $image ($offset + 2) 0x6000
[IO.File]::WriteAllBytes($firmware, $image)

try {
    $wslFirmware = Convert-ToWslPath $firmware
    $wslBurnCode = Convert-ToWslPath $burnCode
    $seconds = [Math]::Max($DurationMs, 1) / 1000.0
    $debug = if ($CpuTrace) { 'in_asm,cpu,unimp' } elseif ($Trace) {
        'in_asm,unimp'
    } else {
        'unimp'
    }
    & wsl.exe -d Ubuntu2 -- timeout "${seconds}s" $qemu `
        -M "np560,burn-code=$wslBurnCode" -bios $wslFirmware `
        -nographic -monitor none -no-reboot -d $debug `
        -D /mnt/e/qemu-dmcu-build/np560-burn-command.log
} finally {
    $resolved = [IO.Path]::GetFullPath($firmware)
    if ($resolved.StartsWith($temporaryRoot,
            [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        Remove-Item -LiteralPath $resolved -Force
    }
}

Get-Content -LiteralPath $traceWindows
