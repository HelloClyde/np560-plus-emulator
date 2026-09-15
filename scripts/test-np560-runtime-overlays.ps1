[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$workDirectory = Join-Path $temporaryRoot (
    'np560-runtime-overlays-{0}' -f [guid]::NewGuid().ToString('N')
)
[IO.Directory]::CreateDirectory($workDirectory) | Out-Null

try {
    $initializerRom = Join-Path $workDirectory 'np560-dual-initializer-rom.bin'
    $overlayInstallRom = Join-Path $workDirectory 'np560-overlay-install-rom.bin'
    $runtimeRom = Join-Path $workDirectory 'np560-runtime-overlays-rom.bin'
    & python (Join-Path $project 'scripts\build_np560_reconstructed_rom.py') `
        --dual-initializer-probe --output $initializerRom | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build dual-initializer probe ROM.' }

    & python (Join-Path $project 'scripts\build_np560_reconstructed_rom.py') `
        --initializer-overlay-probe --probe-stop-after-overlay-install `
        --output $overlayInstallRom | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build overlay-install probe ROM.' }

    & python (Join-Path $project 'scripts\build_np560_reconstructed_rom.py') `
        --initializer-overlay-probe --output $runtimeRom | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build runtime-overlay probe ROM.' }

    $paths = @{}
    foreach ($item in @(
        @{ Name = 'script'; Path = (Join-Path $PSScriptRoot 'tests/test_np560_runtime_overlays.py') },
        @{ Name = 'firmware'; Path = (Join-Path $project 'NP560+V3.80版系统升级程序\NP560.PRG') },
        @{ Name = 'initializer_rom'; Path = $initializerRom },
        @{ Name = 'overlay_install_rom'; Path = $overlayInstallRom },
        @{ Name = 'runtime_rom'; Path = $runtimeRom }
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
        --initializer-rom $paths.initializer_rom `
        --overlay-install-rom $paths.overlay_install_rom `
        --runtime-rom $paths.runtime_rom
    if ($LASTEXITCODE -ne 0) { throw 'Runtime-overlay probe failed.' }
} finally {
    $resolved = [IO.Path]::GetFullPath($workDirectory)
    if ($resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Container)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
