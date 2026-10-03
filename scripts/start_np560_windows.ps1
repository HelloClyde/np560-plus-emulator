param(
    [Parameter(Mandatory = $true)]
    [string]$Device,
    [int]$Port = 8765,
    [string]$HostAddress = '127.0.0.1',
    [string]$MsysRoot = 'C:\msys64',
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$devicePath = (Resolve-Path -LiteralPath $Device).Path
$runLogDir = Join-Path (Split-Path -Parent $devicePath) 'web-runs'
$runtime = Join-Path $MsysRoot 'ucrt64\bin'
if (-not (Test-Path -LiteralPath $runtime -PathType Container)) {
    throw "MSYS2 UCRT64 runtime not found: $runtime"
}
$bridge = Join-Path $PSScriptRoot 'web\np560_web.py'
$env:PATH = "$runtime;$env:PATH"
& $Python $bridge --device $devicePath --host $HostAddress --port $Port `
    --run-log-dir $runLogDir
exit $LASTEXITCODE
