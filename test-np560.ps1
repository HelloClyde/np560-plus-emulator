[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$firmware = Join-Path (Split-Path $PSScriptRoot -Parent) 'NP560+V3.80版系统升级程序\NP560.PRG'
$qemuWindows = 'E:\qemu-dmcu-build\qemu-system-dmcu'
$traceWindows = 'E:\qemu-dmcu-build\np560-selftest.log'
$qemu = '/mnt/e/qemu-dmcu-build/qemu-system-dmcu'
$trace = '/mnt/e/qemu-dmcu-build/np560-selftest.log'

if (-not (Test-Path -LiteralPath $qemuWindows -PathType Leaf)) {
    throw 'QEMU binary not found. Run .\build-np560.ps1 first.'
}
if (-not (Test-Path -LiteralPath $firmware -PathType Leaf)) {
    throw "Firmware not found: $firmware"
}

$firmwareWindows = (Resolve-Path -LiteralPath $firmware).Path -replace '\\', '/'
$wslFirmware = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $firmwareWindows).Trim()
& wsl.exe -d Ubuntu2 -- timeout 0.3s $qemu `
    -M 'np560,rom-hle=on,hle-ui=off' -bios $wslFirmware `
    -nographic -monitor none -no-reboot -d in_asm,unimp -D $trace

$log = Get-Content -LiteralPath $traceWindows -Raw
$checks = [ordered]@{
    'reset SCALL' = '0x00200000:\s+scall 03:0030'
    'main far jump' = '0x00200004:\s+sjmp 33:4f50'
    'byte-addressed firmware entry' = '0x00334f50:'
    'outer startup call' = '0x00334f76:\s+scall 30:9e30'
    'startup routine' = '0x00309e30:'
    'nested startup call' = '0x00309e58:\s+scall 33:07b0'
    'return to resident ROM' = '0x00030032:\s+sjmp 03:0032'
}
foreach ($check in $checks.GetEnumerator()) {
    if ($log -notmatch $check.Value) {
        throw "Self-test failed: missing $($check.Key)."
    }
}
if ($log -match 'out of bounds|unsupported instruction|Invalid (read|write)|callback rejected') {
    throw 'Self-test failed: invalid fetch or unsupported instruction in trace.'
}

Write-Host 'NP560+ QEMU smoke test passed.'
