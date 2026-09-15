[CmdletBinding()]
param(
    [string]$NandCheckpoint,
    [ValidateRange(1, 65535)]
    [int]$RawEvent = 0x101,
    [double]$IdleTimeout = 90
)

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent

if (-not $NandCheckpoint) {
    foreach ($candidate in @(
        (Join-Path $project 'tmp\np560-v380-flashed-ecc.nand'),
        'E:\np560-data\np560-v380-flashed-ecc.nand'
    )) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $NandCheckpoint = $candidate
            break
        }
    }
}
if (-not $NandCheckpoint) {
    throw 'The native keyboard regression requires a fully burned V3.80 NAND checkpoint.'
}

# The old 03:0080 latch loop was an exploration harness and no longer models
# the recovered application. Exercise Web/QOM input through the real
# F160/F164 matrix scanner, 06:B126 key reader, and application scheduler.
& (Join-Path $PSScriptRoot 'test-np560-system-boot.ps1') `
    -NandCheckpoint $NandCheckpoint -RawEvent ('0x{0:x}' -f $RawEvent) `
    -IdleTimeout $IdleTimeout
if ($LASTEXITCODE -ne 0) { throw 'Native keyboard integration test failed.' }
