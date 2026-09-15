[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$workDirectory = Join-Path $temporaryRoot (
    'np560-initializer-probe-{0}' -f [guid]::NewGuid().ToString('N')
)
[IO.Directory]::CreateDirectory($workDirectory) | Out-Null

try {
    $rom = Join-Path $workDirectory 'np560-initializer-probe-rom.bin'
    & python (Join-Path $project 'scripts\build_np560_reconstructed_rom.py') `
        --initializer-probe --output $rom | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build initializer probe ROM.' }

    $paths = @{}
    foreach ($item in @(
        @{ Name = 'script'; Path = (Join-Path $PSScriptRoot 'test_np560_initializer_probe.py') },
        @{ Name = 'firmware'; Path = (Join-Path $project 'NP560+V3.80版系统升级程序\NP560.PRG') },
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
        --firmware $paths.firmware --soc-rom $paths.rom
    if ($LASTEXITCODE -ne 0) { throw 'Initializer probe failed.' }
} finally {
    $resolved = [IO.Path]::GetFullPath($workDirectory)
    if ($resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Container)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
