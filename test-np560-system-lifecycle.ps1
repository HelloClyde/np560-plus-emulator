[CmdletBinding()]
param(
    [ValidateRange(1, 256)]
    [int]$Count = 64,
    [double]$IdleTimeout = 90,
    [string]$NandCheckpoint
)

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
if (-not $NandCheckpoint) {
    $candidate = Join-Path $project 'tmp\np560-v380-flashed-ecc.nand'
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $NandCheckpoint = $candidate
    }
}

$events = [string[]]@(1..$Count | ForEach-Object { '0x100' })
$parameters = @{
    IdleTimeout = $IdleTimeout
    RawEvent = $events
}
if ($NandCheckpoint) {
    $parameters.NandCheckpoint = $NandCheckpoint
}

& (Join-Path $PSScriptRoot 'test-np560-system-boot.ps1') @parameters
if ($LASTEXITCODE -ne 0) {
    throw "NP560 lifecycle stress failed after at most $Count events."
}
