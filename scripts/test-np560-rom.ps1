[CmdletBinding()]
param(
    [int]$Port = 8768,
    [switch]$KeepFiles
)

$ErrorActionPreference = 'Stop'
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$tag = [guid]::NewGuid().ToString('N')
$firmware = Join-Path $temporaryRoot "np560-rom-fw-$tag.bin"
$socRom = Join-Path $temporaryRoot "np560-soc-rom-$tag.bin"

function Set-Word([byte[]]$Image, [int]$Offset, [uint16]$Value) {
    $Image[$Offset] = $Value -band 0xFF
    $Image[$Offset + 1] = ($Value -shr 8) -band 0xFF
}

$program = [byte[]]::new(0x400000)
Set-Word $program 0x0000 0xBD03       # SCALL 03:0030
Set-Word $program 0x0002 0x0030
Set-Word $program 0x0004 0xD0FF       # RJMP ALWAYS, self

$resident = [byte[]]::new(0x30036)
Set-Word $resident 0x30030 0x68F0     # MOV R0, #0xBEEF
Set-Word $resident 0x30032 0xBEEF
Set-Word $resident 0x30034 0xC620     # RETS

[IO.File]::WriteAllBytes($firmware, $program)
[IO.File]::WriteAllBytes($socRom, $resident)

try {
    & (Join-Path $PSScriptRoot 'test-np560-web.ps1') `
        -Firmware $firmware -SocRom $socRom -Port $Port -InitialDelayMs 250 `
        -RegisterPattern 'R0 =beef' | Out-Host
} finally {
    if ($KeepFiles) {
        Write-Host "Firmware: $firmware"
        Write-Host "SoC ROM: $socRom"
    } else {
        foreach ($path in @($firmware, $socRom)) {
            $resolved = [IO.Path]::GetFullPath($path)
            if ($resolved.StartsWith($temporaryRoot,
                    [StringComparison]::OrdinalIgnoreCase) -and
                (Test-Path -LiteralPath $resolved -PathType Leaf)) {
                Remove-Item -LiteralPath $resolved -Force
            }
        }
    }
}

Write-Host 'NP560+ flat SoC ROM mapping test passed.'
