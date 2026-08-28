[CmdletBinding()]
param(
    [int]$Port = 8766,
    [string]$NandCheckpoint
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
$firmwareSource = Get-ChildItem -LiteralPath $project -Recurse -File `
    -Filter 'NP560.PRG' | Select-Object -First 1 -ExpandProperty FullName
if (-not $firmwareSource) {
    throw 'Unable to locate the vendor NP560 firmware.'
}
if (-not $NandCheckpoint -or
    -not (Test-Path -LiteralPath $NandCheckpoint -PathType Leaf)) {
    throw "NAND checkpoint not found: $NandCheckpoint"
}

$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$workDirectory = Join-Path $temporaryRoot (
    'np560-system-web-{0}' -f [guid]::NewGuid().ToString('N')
)
[IO.Directory]::CreateDirectory($workDirectory) | Out-Null

try {
    # PowerShell 5 and legacy Windows Python corrupt the Chinese source path
    # in argv, so stage immutable inputs under a disposable ASCII path.
    $firmware = Join-Path $workDirectory 'NP560.PRG'
    Copy-Item -LiteralPath $firmwareSource -Destination $firmware

    $rom = Join-Path $workDirectory 'np560-system-rom.bin'
    & python (Join-Path $project 'disassembly\build_np560_reconstructed_rom.py') `
        --initializer-overlay-probe --probe-system-main `
        --probe-resident-app-state-guard --probe-rom-08-427e-return `
        --probe-rom-01-0200-return `
        --output $rom | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build system ROM.' }

    & (Join-Path $PSScriptRoot 'test-np560-web.ps1') `
        -Firmware $firmware -SocRom $rom -SocRomSkeleton `
        -NandCheckpoint $NandCheckpoint -FrameSource lcd -ExpectNative -Port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Native system Web test failed.' }
} finally {
    $resolved = [IO.Path]::GetFullPath($workDirectory)
    if ($resolved.StartsWith($temporaryRoot,
            [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Container)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
