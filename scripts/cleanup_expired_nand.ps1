[CmdletBinding()]
param(
    [switch]$Delete
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$expectedRoot = 'C:\Users\ASUS\Documents\ChatGPT\np560'
if ($projectRoot.TrimEnd('\') -ne $expectedRoot) {
    throw "Refusing to run outside the expected project root: $projectRoot"
}

$tmpRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'tmp'))
$expectedTmp = 'C:\Users\ASUS\Documents\ChatGPT\np560\tmp'
if ($tmpRoot.TrimEnd('\') -ne $expectedTmp) {
    throw "Unexpected tmp path: $tmpRoot"
}

$keepNames = @(
    # Active checkpoint used by the isolated Web/QEMU process.
    'np560-v735-hero-fat16-ab-guest-dots.nand',
    # Historical NAND page-lane reconstruction evidence.
    'np560-v380-factory-page-lanes-v659.nand'
)

# Checkpoints created after the frozen cutoff but superseded by a later,
# independently reproduced route.  Keep this explicit: never classify a new
# same-day NAND as disposable merely from its timestamp.
$knownExpiredNames = @(
    'np560-v833-root-ready-pre-copy-protected.nand',
    # Superseded September 5 scratch checkpoints. The documented v6 baseline
    # and the older page-lane/guest-dots evidence remain protected above.
    'np560-v735-hero-fat16-ab-userinfo.nand',
    'np560-vma03-native-pim.nand',
    'np560-vma03-native-pim-v2.nand',
    'np560-vma03-native-pim-v3.nand',
    'np560-vma03-native-pim-v4.nand'
)

# Freeze the cleanup set at the date this script was prepared. NAND images made
# by later emulator work are never classified as expired by this script.
$cutoff = [datetime]'2026-09-01T00:00:00'
$tmpCandidates = @(
    Get-ChildItem -LiteralPath $tmpRoot -File -Filter '*.nand' |
        Where-Object {
            $keepNames -notcontains $_.Name -and (
                $_.LastWriteTime -lt $cutoff -or
                $knownExpiredNames -contains $_.Name
            )
        } |
        Sort-Object FullName
)

foreach ($candidate in $tmpCandidates) {
    $candidateDirectory = [System.IO.Path]::GetDirectoryName(
        [System.IO.Path]::GetFullPath($candidate.FullName)
    )
    if ($candidateDirectory -ne $tmpRoot) {
        throw "Candidate escaped the verified tmp directory: $($candidate.FullName)"
    }
}

$buildCandidatePath = 'E:\qemu-dmcu-build\np560-web-save-codex-20260822.nand'
$buildCandidates = @()
if (Test-Path -LiteralPath $buildCandidatePath -PathType Leaf) {
    $resolvedBuildCandidate = (Resolve-Path -LiteralPath $buildCandidatePath).Path
    if ($resolvedBuildCandidate -ne $buildCandidatePath) {
        throw "Unexpected build NAND path: $resolvedBuildCandidate"
    }
    $buildCandidates = @((Get-Item -LiteralPath $resolvedBuildCandidate))
}

$candidates = @($tmpCandidates) + @($buildCandidates)
$logicalBytes = [int64]0
foreach ($candidate in $candidates) {
    $logicalBytes += $candidate.Length
}

Write-Host ("Expired NAND candidates: {0}" -f $candidates.Count)
Write-Host ("Logical size: {0:N2} GiB" -f ($logicalBytes / 1GB))
Write-Host 'Preserved tmp NAND images:'
foreach ($name in $keepNames) {
    $state = if (Test-Path -LiteralPath (Join-Path $tmpRoot $name)) {
        'present'
    } else {
        'not present'
    }
    Write-Host ("  {0} ({1})" -f $name, $state)
}

if (-not $Delete) {
    Write-Host ''
    Write-Host 'Dry run only. Re-run with -Delete to remove the listed candidates.'
    $candidates | Select-Object FullName, Length, LastWriteTime
    exit 0
}

foreach ($candidate in $candidates) {
    Remove-Item -LiteralPath $candidate.FullName -Force
}

$remainingTmp = @(Get-ChildItem -LiteralPath $tmpRoot -File -Filter '*.nand')
Write-Host ("Deleted {0} expired NAND images." -f $candidates.Count)
Write-Host ("Remaining tmp NAND images: {0}" -f $remainingTmp.Count)
