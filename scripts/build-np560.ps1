[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$distro = 'Ubuntu2'
$buildDir = '/mnt/e/qemu-dmcu-build'
$sourceWindows = (Join-Path (Split-Path $PSScriptRoot -Parent) 'qemu-dmcu') `
    -replace '\\', '/'
$sourceDir = (& wsl.exe -d $distro -- wslpath -a -- $sourceWindows).Trim()
if ($LASTEXITCODE -ne 0 -or -not $sourceDir) {
    throw 'Unable to translate the QEMU source path into WSL.'
}

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
$configure = "if [ ! -f build.ninja ]; then " +
    "env PATH=$buildPath '$sourceDir/configure' $quotedOptions; fi"
$command = "mkdir -p '$buildDir' && cd '$buildDir' && " +
    "$configure && ninja -j4 qemu-system-dmcu"

& wsl.exe -d $distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw "QEMU build failed with exit code $LASTEXITCODE."
}

Write-Host 'Built E:\qemu-dmcu-build\qemu-system-dmcu'
