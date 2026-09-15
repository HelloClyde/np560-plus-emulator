[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Firmware,
    [string]$OutputDirectory,
    [string]$RuntimeUrl,
    [ValidateRange(1, 1000)]
    [int]$ProbeCount = 1,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$firmwarePath = (Resolve-Path -LiteralPath $Firmware).Path
if (-not $OutputDirectory) {
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($firmwarePath)
    $OutputDirectory = Join-Path $repoRoot "tmp\$stem-ui-preprocessed"
}

function Invoke-PythonChecked {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE`: python $Arguments"
    }
}

Push-Location $repoRoot
try {
    Write-Host '[1/4] Generating exact UI/startup/menu slices...'
    Invoke-PythonChecked `
        'scripts\preprocess_np560_ui.py' `
        $firmwarePath `
        '--output-dir' $OutputDirectory

    Write-Host '[2/4] Auditing Harvard code/data mappings and overlay collisions...'
    Invoke-PythonChecked `
        'scripts\np560_overlay_map.py' `
        '--qemu-source' 'qemu-dmcu\hw\dmcu\np560.c' `
        '--output' 'tmp\np560-overlay-map.json'

    if ($SkipTests) {
        Write-Host '[3/4] Unit tests skipped.'
    } else {
        Write-Host '[3/4] Running preprocessing, mapping, and monitor tests...'
        Invoke-PythonChecked `
            '-m' 'unittest' `
            'scripts\tests\test_np560_overlay_map.py' `
            'scripts\tests\test_preprocess_np560_ui.py' `
            'scripts\tests\test_audit_np560_overlay_mappings.py' `
            'scripts\tests\test_probe_np560_runtime.py' `
            'scripts\tests\test_watch_np560_code_sources.py' `
            'scripts\tests\test_analyze_np560_runtime_code_sources.py'
    }

    if ($RuntimeUrl) {
        Write-Host '[4/4] Sampling live hardware-model diagnostics...'
        Invoke-PythonChecked `
            'scripts\probe_np560_runtime.py' `
            '--url' $RuntimeUrl `
            '--count' ([string]$ProbeCount) `
            '--changes-only'
    } else {
        Write-Host '[4/4] Live probe skipped (no -RuntimeUrl supplied).'
    }

    Write-Host "Preflight passed. UI index: $OutputDirectory"
} finally {
    Pop-Location
}
