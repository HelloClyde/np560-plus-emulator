[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8775,
    [ValidateRange(0.01, 60.0)]
    [double]$PollInterval = 0.1,
    [ValidateRange(0.1, 3600.0)]
    [double]$HeartbeatSeconds = 5.0,
    [ValidateRange(1.0, 86400.0)]
    [double]$TimeoutSeconds = 2400.0,
    [ValidateSet('incident', 'menu', 'cafe', 'return', 'either', 'never')]
    [string]$StopOn = 'either',
    [ValidateRange(1, 100)]
    [int]$StackDescentCycles = 2,
    [ValidateRange(1, 65535)]
    [int]$StackDescentMinBytes = 16,
    [ValidateRange(0.1, 3600.0)]
    [double]$BlankAfterVisibleSeconds = 15.0,
    [ValidateRange(1, 28800)]
    [int]$BlankMinVisiblePixels = 16,
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$ExpectedSocRomSha256,
    [string]$OutputDir,
    [switch]$NoResume,
    [switch]$NoPause,
    [switch]$NoBlankAfterVisibleCheck
)

$ErrorActionPreference = 'Stop'
$monitor = Join-Path $PSScriptRoot 'monitor_np560_web.py'
if (-not (Test-Path -LiteralPath $monitor -PathType Leaf)) {
    throw "Monitor script not found: $monitor"
}

$url = "http://127.0.0.1:$Port"
try {
    $state = Invoke-RestMethod -Method Get -Uri "$url/api/state" -TimeoutSec 5
} catch {
    throw "NP560 Web is not reachable at $url. Start run-np560-web.ps1 first. $($_.Exception.Message)"
}

$reportedSha = [string]$state.soc_rom_sha256
if ($ExpectedSocRomSha256 -and
        $reportedSha.ToLowerInvariant() -ne $ExpectedSocRomSha256.ToLowerInvariant()) {
    throw "The Web instance uses SoC ROM $reportedSha, expected $ExpectedSocRomSha256."
}
$pinnedSha = if ($ExpectedSocRomSha256) {
    $ExpectedSocRomSha256.ToLowerInvariant()
} else {
    $reportedSha.ToLowerInvariant()
}
if (-not $pinnedSha) {
    throw 'The Web instance did not report a SoC ROM SHA-256.'
}

if (-not $OutputDir) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $OutputDir = Join-Path (Split-Path $PSScriptRoot -Parent) "tmp\np560-monitor-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)

$arguments = @(
    $monitor,
    '--url', $url,
    '--poll-interval', [string]$PollInterval,
    '--heartbeat', [string]$HeartbeatSeconds,
    '--timeout', [string]$TimeoutSeconds,
    '--stop-on', $StopOn,
    '--stack-descent-cycles', [string]$StackDescentCycles,
    '--stack-descent-min-bytes', [string]$StackDescentMinBytes,
    '--blank-after-visible-seconds', [string]$BlankAfterVisibleSeconds,
    '--blank-min-visible-pixels', [string]$BlankMinVisiblePixels,
    '--expect-soc-rom-sha256', $pinnedSha,
    '--output-dir', $OutputDir
)
if (-not $NoResume) {
    $arguments += '--resume'
}
if ($NoPause) {
    $arguments += '--no-pause'
}
if ($NoBlankAfterVisibleCheck) {
    $arguments += '--no-blank-after-visible-check'
}

Write-Host "Monitoring $url"
Write-Host "Pinned SoC ROM SHA-256: $pinnedSha"
Write-Host "Capture directory: $OutputDir"
Write-Host 'Triggers: stack descent, LCD blank-after-visible, 0x04D6 writes on both data paths, resource I/O before A2:28E0 initialization, bad control flow, missing ROM, unsupported instruction, MENUOK, first foreground return when -StopOn return is selected, or CAFE metadata when -StopOn cafe is selected.'

& python @arguments
$monitorExitCode = $LASTEXITCODE
switch ($monitorExitCode) {
    0 { Write-Host "Milestone captured: $OutputDir" }
    2 {
        if ($NoPause) {
            Write-Warning "Incident captured: $OutputDir"
        } else {
            Write-Warning "Incident captured and QEMU paused: $OutputDir"
        }
    }
    3 { Write-Warning "Monitor timed out; final state captured: $OutputDir" }
    default { Write-Warning "Monitor exited with code $monitorExitCode" }
}
exit $monitorExitCode
