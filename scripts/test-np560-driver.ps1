[CmdletBinding()]
param([int]$Port = 8769)

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$update = Join-Path $project 'NP560+V3.80版系统升级程序\NP560+.upd'
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$extractDirectory = Join-Path $temporaryRoot (
    'np560-driver-test-{0}' -f [guid]::NewGuid().ToString('N')
)
[IO.Directory]::CreateDirectory($extractDirectory) | Out-Null

try {
    & python (Join-Path $project 'scripts\np560_upd.py') $update `
        --extract-dir $extractDirectory --extract-slot 1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to extract update driver slot.' }
    $driver = Join-Path $extractDirectory 'NP560_UPDATE_DRIVER.bin'
    & (Join-Path $PSScriptRoot 'test-np560-web.ps1') `
        -Port $Port -DriverCode $driver -BootMode driver -FrameSource lcd `
        -InitialDelayMs 500 -ExpectNonzero `
        -RegisterPattern '(?s)ROM_MISSING=02:bac4 FETCHES=1.*ST7529=on.*WINDOW=C0-79,L20-139.*FRAMES=[1-9]'
} finally {
    $resolved = [IO.Path]::GetFullPath($extractDirectory)
    if ($resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Container)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
