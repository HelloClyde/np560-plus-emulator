[CmdletBinding()]
param(
    [switch]$PrintLcdTrace,
    [switch]$PrintCpuState,
    [string]$LcdFrameOutput,
    [string]$NativeFramebufferOutput,
    [string]$NativeBackbufferOutput,
    [switch]$LogUnimp,
    [switch]$SkipEvent,
    [switch]$SkipLcdContentCheck,
    [ValidateSet('firmware', 'firmware-vma03')]
    [string]$BootMode = 'firmware',
    [double]$IdleTimeout = 30,
    [string[]]$RawEvent,
    [string[]]$MatrixEvent,
    [switch]$AllMatrixEvents,
    [switch]$RowIsolatedMatrix,
    [ValidateRange(0, 63)]
    [int]$MatrixStart = 0,
    [ValidateRange(1, 64)]
    [int]$MatrixCount = 64,
    [string]$NandCheckpoint
)

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$updateSource = Get-ChildItem -LiteralPath $project -Recurse -File `
    -Filter 'NP560+.upd' | Select-Object -First 1 -ExpandProperty FullName
$firmwareSource = Get-ChildItem -LiteralPath $project -Recurse -File `
    -Filter 'NP560.PRG' | Select-Object -First 1 -ExpandProperty FullName
if (-not $updateSource -or -not $firmwareSource) {
    throw 'Unable to locate the vendor NP560 update inputs.'
}
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$workDirectory = Join-Path $temporaryRoot (
    'np560-system-boot-{0}' -f [guid]::NewGuid().ToString('N')
)
[IO.Directory]::CreateDirectory($workDirectory) | Out-Null

try {
    # The locally installed Windows Python runs in legacy argv mode and
    # corrupts the Chinese directory name.  Stage both immutable vendor
    # inputs under the already-isolated ASCII temporary path before invoking
    # either Python or WSL; this changes neither image.
    $update = Join-Path $workDirectory 'NP560+.upd'
    $firmware = Join-Path $workDirectory 'NP560.PRG'
    Copy-Item -LiteralPath $updateSource -Destination $update
    Copy-Item -LiteralPath $firmwareSource -Destination $firmware

    $rom = Join-Path $workDirectory 'np560-system-rom.bin'
    & python (Join-Path $project 'scripts\build_np560_reconstructed_rom.py') `
        --initializer-overlay-probe --probe-system-main `
        --probe-resident-app-state-guard --probe-rom-08-427e-return `
        --probe-rom-01-0200-return `
        --output $rom | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build system ROM.' }

    if ($NandCheckpoint) {
        $nand = (Resolve-Path -LiteralPath $NandCheckpoint).Path
    } else {
        & python (Join-Path $project 'scripts\np560_upd.py') $update `
            --extract-dir $workDirectory --extract-slot 3 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Unable to extract NAND image.' }
        $nand = Join-Path $workDirectory 'NP560_NAND_IMAGE.bin'
    }

    $paths = @{}
    foreach ($item in @(
        @{ Name = 'script'; Path = (Join-Path $PSScriptRoot 'tests/test_np560_system_boot.py') },
        @{ Name = 'firmware'; Path = $firmware },
        @{ Name = 'rom'; Path = $rom },
        @{ Name = 'nand'; Path = $nand }
    )) {
        $windows = (Resolve-Path -LiteralPath $item.Path).Path -replace '\\', '/'
        $paths[$item.Name] = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $windows).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $paths[$item.Name]) {
            throw "Unable to translate $($item.Name) path into WSL."
        }
    }

    $testArguments = @(
        $paths.script,
        '--qemu', '/mnt/e/qemu-dmcu-build/qemu-system-dmcu',
        '--firmware', $paths.firmware,
        '--soc-rom', $paths.rom,
        '--boot-mode', $BootMode,
        $(if ($NandCheckpoint) { '--nand-checkpoint' } else { '--nand' }),
        $paths.nand,
        '--idle-timeout', [string]$IdleTimeout
    )
    if ($PrintLcdTrace) {
        $testArguments += '--print-lcd-trace'
    }
    if ($PrintCpuState) {
        $testArguments += '--print-cpu-state'
    }
    if ($LcdFrameOutput) {
        $frameParent = Split-Path -Parent $LcdFrameOutput
        if ($frameParent -and -not (Test-Path -LiteralPath $frameParent)) {
            [IO.Directory]::CreateDirectory($frameParent) | Out-Null
        }
        $frameWindows = [IO.Path]::GetFullPath($LcdFrameOutput) -replace '\\', '/'
        $frameWsl = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $frameWindows).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $frameWsl) {
            throw 'Unable to translate the LCD frame output path into WSL.'
        }
        $testArguments += @('--lcd-frame-output', $frameWsl)
    }
    foreach ($memoryOutput in @(
        @{ Value = $NativeFramebufferOutput; Option = '--native-framebuffer-output' },
        @{ Value = $NativeBackbufferOutput; Option = '--native-backbuffer-output' }
    )) {
        if (-not $memoryOutput.Value) { continue }
        $memoryParent = Split-Path -Parent $memoryOutput.Value
        if ($memoryParent -and -not (Test-Path -LiteralPath $memoryParent)) {
            [IO.Directory]::CreateDirectory($memoryParent) | Out-Null
        }
        $memoryWindows = [IO.Path]::GetFullPath($memoryOutput.Value) -replace '\\', '/'
        $memoryWsl = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $memoryWindows).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $memoryWsl) {
            throw "Unable to translate $($memoryOutput.Option) path into WSL."
        }
        $testArguments += @($memoryOutput.Option, $memoryWsl)
    }
    if ($LogUnimp) {
        $testArguments += '--log-unimp'
    }
    if ($SkipEvent) {
        $testArguments += '--skip-event'
    }
    if ($SkipLcdContentCheck) {
        $testArguments += '--skip-lcd-content-check'
    }
    foreach ($eventValue in $RawEvent) {
        $testArguments += @('--raw-event', $eventValue)
    }
    foreach ($eventValue in $MatrixEvent) {
        $testArguments += @('--matrix-event', $eventValue)
    }
    if ($AllMatrixEvents) {
        if (-not $RowIsolatedMatrix) {
            $matrixArguments = $testArguments + @(
                '--all-matrix-events',
                '--matrix-start', [string]$MatrixStart,
                '--matrix-count', [string]$MatrixCount
            )
            & wsl.exe -d Ubuntu2 -- python3 @matrixArguments
            if ($LASTEXITCODE -ne 0) {
                throw 'Native single-process matrix regression failed.'
            }
        } else {
            # Retain row-isolated mode as a focused keyboard-hardware test.
            $matrixEnd = [Math]::Min(64, $MatrixStart + $MatrixCount)
            for ($matrixChunkStart = $MatrixStart;
                 $matrixChunkStart -lt $matrixEnd;
                 $matrixChunkStart += 8) {
                $chunkCount = [Math]::Min(8, $matrixEnd - $matrixChunkStart)
                $chunkArguments = $testArguments + @(
                    '--all-matrix-events',
                    '--matrix-start', [string]$matrixChunkStart,
                    '--matrix-count', [string]$chunkCount
                )
                & wsl.exe -d Ubuntu2 -- python3 @chunkArguments
                if ($LASTEXITCODE -ne 0) {
                    throw "Native matrix chunk starting at $matrixChunkStart failed."
                }
            }
        }
    } else {
        & wsl.exe -d Ubuntu2 -- python3 @testArguments
        if ($LASTEXITCODE -ne 0) { throw 'Native system boot test failed.' }
    }
} finally {
    $resolved = [IO.Path]::GetFullPath($workDirectory)
    if ($resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Container)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
