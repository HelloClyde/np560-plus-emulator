[CmdletBinding()]
param(
    [ValidateSet('keep', '2', '3')]
    [string]$Optimization = 'keep',
    [ValidateSet('keep', 'enabled', 'disabled')]
    [string]$Lto = 'keep',
    [ValidateNotNullOrEmpty()]
    [string]$Distro = 'Ubuntu2',
    # Absolute Linux path inside the selected WSL distribution.
    [ValidatePattern('^/.+')]
    [string]$BuildDirectory = '/mnt/e/qemu-dmcu-build',
    [ValidateRange(1, 256)]
    [int]$Jobs = 4,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
function Quote-ShellLiteral([string]$Value) {
    $escapedQuote = "'" + '"' + "'" + '"' + "'"
    return "'" + $Value.Replace("'", $escapedQuote) + "'"
}

$buildDir = $BuildDirectory
$sourceWindows = (Join-Path (Split-Path $PSScriptRoot -Parent) 'qemu-dmcu') `
    -replace '\\', '/'
$translatedSource = & wsl.exe -d $distro -- wslpath -a -- $sourceWindows
if ($LASTEXITCODE -ne 0 -or -not $translatedSource) {
    throw 'Unable to translate the QEMU source path into WSL.'
}
$sourceDir = ($translatedSource -join "`n").Trim()

$options = @(
    '--target-list=dmcu-softmmu'
    '--with-pkgversion=np560-cleanroom'
    '--disable-werror'
    '--disable-docs'
    '--disable-gtk'
    '--disable-sdl'
    '--disable-opengl'
    '--disable-curses'
    '--disable-vnc'
    '--disable-slirp'
    '--disable-capstone'
    '--disable-tools'
    '--disable-guest-agent'
    '--disable-vhost-user'
    '--disable-vhost-kernel'
    '--disable-vhost-vdpa'
    '--disable-vhost-net'
    '--disable-multiprocess'
    '--disable-plugins'
    '--disable-libvduse'
    '--disable-vduse-blk-export'
)

$quotedOptions = $options -join ' '
$buildPath = '/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
$quotedConfigure = Quote-ShellLiteral "$sourceDir/configure"
$quotedBuildDir = Quote-ShellLiteral $buildDir
$configure = "if [ ! -f build.ninja ]; then " +
    "env PATH=$buildPath $quotedConfigure $quotedOptions; fi"
$optimize = if ($Optimization -eq 'keep') { 'true' } else {
    "./pyvenv/bin/meson configure -Doptimization=$Optimization ."
}
$linkOptimize = if ($Lto -eq 'keep') { 'true' } else {
    $ltoValue = if ($Lto -eq 'enabled') { 'true' } else { 'false' }
    "./pyvenv/bin/meson configure -Db_lto=$ltoValue ."
}
$command = "mkdir -p -- $quotedBuildDir && cd -- $quotedBuildDir && " +
    "$configure && $optimize && $linkOptimize && ninja -j$Jobs qemu-system-dmcu"

if ($DryRun) {
    Write-Output $command
    return
}

# No login shell: unrelated profile hooks must not decide whether builds work.
& wsl.exe -d $distro -- bash -c $command
if ($LASTEXITCODE -ne 0) {
    throw "QEMU build failed with exit code $LASTEXITCODE."
}

Write-Host "Built ${Distro}:${buildDir}/qemu-system-dmcu"
