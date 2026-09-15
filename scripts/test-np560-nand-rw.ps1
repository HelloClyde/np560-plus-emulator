[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$workDirectory = Join-Path $temporaryRoot (
    'np560-nand-rw-test-{0}' -f [guid]::NewGuid().ToString('N')
)
[IO.Directory]::CreateDirectory($workDirectory) | Out-Null

try {
    $rom = Join-Path $workDirectory 'np560-reconstructed-rom.bin'
    $firmware = Join-Path $workDirectory 'np560-nand-rw.prg'
    $persistWriter = Join-Path $workDirectory 'np560-nand-persist-write.prg'
    $persistReader = Join-Path $workDirectory 'np560-nand-persist-read.prg'
    & python (Join-Path $project 'scripts\build_np560_reconstructed_rom.py') `
        --output $rom | Out-Null
    & python (Join-Path $project 'scripts\build_np560_nand_rw_harness.py') `
        --output $firmware | Out-Null
    & python (Join-Path $project 'scripts\build_np560_nand_rw_harness.py') `
        --mode persist-write --output $persistWriter | Out-Null
    & python (Join-Path $project 'scripts\build_np560_nand_rw_harness.py') `
        --mode persist-read --output $persistReader | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build NAND test images.' }

    $paths = @{}
    foreach ($item in @(
        @{ Name = 'script'; Path = (Join-Path $PSScriptRoot 'tests/test_np560_nand_rw.py') },
        @{ Name = 'firmware'; Path = $firmware },
        @{ Name = 'persistWriter'; Path = $persistWriter },
        @{ Name = 'persistReader'; Path = $persistReader },
        @{ Name = 'rom'; Path = $rom }
    )) {
        $windows = (Resolve-Path -LiteralPath $item.Path).Path -replace '\\', '/'
        $paths[$item.Name] = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $windows).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $paths[$item.Name]) {
            throw "Unable to translate $($item.Name) path into WSL."
        }
    }
    & wsl.exe -d Ubuntu2 -- python3 $paths.script `
        --qemu /mnt/e/qemu-dmcu-build/qemu-system-dmcu `
        --firmware $paths.firmware `
        --persist-write-firmware $paths.persistWriter `
        --persist-read-firmware $paths.persistReader `
        --soc-rom $paths.rom
    if ($LASTEXITCODE -ne 0) { throw 'NAND guest read/write test failed.' }
} finally {
    $resolved = [IO.Path]::GetFullPath($workDirectory)
    if ($resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Container)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
