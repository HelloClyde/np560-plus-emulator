[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$workDirectory = Join-Path $temporaryRoot (
    'np560-des-{0}' -f [guid]::NewGuid().ToString('N')
)
[IO.Directory]::CreateDirectory($workDirectory) | Out-Null

try {
    $socRom = Join-Path $workDirectory 'np560-des-rom.bin'
    & python (Join-Path $project 'scripts\build_np560_reconstructed_rom.py') `
        --output $socRom | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build DES test ROM.' }

    $paths = @{}
    foreach ($item in @(
        @{ Name = 'script'; Path = (Join-Path $PSScriptRoot 'tests/test_np560_des.py') },
        @{ Name = 'soc_rom'; Path = $socRom }
    )) {
        $windows = (Resolve-Path -LiteralPath $item.Path).Path -replace '\\', '/'
        $paths[$item.Name] = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $windows).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $paths[$item.Name]) {
            throw "Unable to translate $($item.Name) path into WSL."
        }
    }
    & wsl.exe -d Ubuntu2 -- python3 $paths.script `
        --qemu /mnt/e/qemu-dmcu-build/qemu-system-dmcu `
        --soc-rom $paths.soc_rom
    if ($LASTEXITCODE -ne 0) { throw 'Guest DES known-answer test failed.' }
} finally {
    $resolved = [IO.Path]::GetFullPath($workDirectory)
    if ($resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Container)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
