[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$burnCode = Join-Path $project `
    'NP560+V3.80版系统升级程序\BURN_NAND_FLASH_CODE.bin'
$script = Join-Path $PSScriptRoot 'test_np560_ecc_correction.py'

foreach ($path in @($burnCode, $script)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required ECC correction input not found: $path"
    }
}

function Convert-ToWslPath([string]$Path) {
    $windows = (Resolve-Path -LiteralPath $Path).Path.Replace(
        [char]92, [char]47)
    $translated = (& wsl.exe -d Ubuntu2 -- wslpath -a -- $windows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $translated) {
        throw "Unable to translate path into WSL: $Path"
    }
    return $translated
}

& wsl.exe -d Ubuntu2 -- python3 (Convert-ToWslPath $script) `
    --qemu /mnt/e/qemu-dmcu-build/qemu-system-dmcu `
    --burn-code (Convert-ToWslPath $burnCode)
if ($LASTEXITCODE -ne 0) {
    throw 'NP560+ vendor ECC correction test failed.'
}
