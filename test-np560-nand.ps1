[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$update = Join-Path $project 'NP560+V3.80版系统升级程序\NP560+.upd'
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$workDirectory = Join-Path $temporaryRoot (
    'np560-nand-test-{0}' -f [guid]::NewGuid().ToString('N')
)
[IO.Directory]::CreateDirectory($workDirectory) | Out-Null

try {
    & python (Join-Path $project 'disassembly\np560_upd.py') $update `
        --extract-dir $workDirectory --extract-slot 0 --extract-slot 3 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to extract burner and NAND blocks.' }

    $rom = Join-Path $workDirectory 'np560-reconstructed-rom.bin'
    $firmware = Join-Path $workDirectory 'np560-burn-command1.prg'
    & python (Join-Path $project 'disassembly\build_np560_reconstructed_rom.py') `
        --output $rom | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build reconstructed ROM.' }
    & python (Join-Path $project 'disassembly\build_np560_burn_harness.py') `
        --command 1 --output $firmware | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build burner command harness.' }

    $paths = @{}
    foreach ($item in @(
        @{ Name = 'script'; Path = (Join-Path $PSScriptRoot 'test_np560_nand.py') },
        @{ Name = 'firmware'; Path = $firmware },
        @{ Name = 'rom'; Path = $rom },
        @{ Name = 'burner'; Path = (Join-Path $workDirectory 'BURN_NAND_FLASH_CODE.bin') },
        @{ Name = 'nand'; Path = (Join-Path $workDirectory 'NP560_NAND_IMAGE.bin') }
    )) {
        $windows = (Resolve-Path -LiteralPath $item.Path).Path -replace '\\', '/'
        $paths[$item.Name] = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $windows).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $paths[$item.Name]) {
            throw "Unable to translate $($item.Name) path into WSL."
        }
    }

    & wsl.exe -d Ubuntu2 -- python3 $paths.script `
        --qemu /mnt/e/qemu-dmcu-build/qemu-system-dmcu `
        --firmware $paths.firmware --soc-rom $paths.rom `
        --burner $paths.burner --nand $paths.nand
    if ($LASTEXITCODE -ne 0) { throw 'NAND integration test failed.' }
} finally {
    $resolved = [IO.Path]::GetFullPath($workDirectory)
    if ($resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Container)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
