[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$script = (Resolve-Path -LiteralPath (
    Join-Path $PSScriptRoot 'tests/test_np560_memory_split.py'
)).Path -replace '\\', '/'
$wslScript = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $script).Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslScript) {
    throw 'Unable to translate the memory-split test path into WSL.'
}

& wsl.exe -d Ubuntu2 -- python3 $wslScript `
    --qemu /mnt/e/qemu-dmcu-build/qemu-system-dmcu
if ($LASTEXITCODE -ne 0) {
    throw 'NP560+ memory-split test failed.'
}
