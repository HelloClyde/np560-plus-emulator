param(
    [Parameter(Mandatory = $true)]
    [string]$BuildDir,
    [string]$MsysRoot = 'C:\msys64',
    [int]$Jobs = 4
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$source = Join-Path $project 'qemu-dmcu'
$bash = Join-Path $MsysRoot 'usr\bin\bash.exe'
if (-not (Test-Path -LiteralPath $bash -PathType Leaf)) {
    throw "MSYS2 bash not found: $bash"
}
if ($Jobs -lt 1) {
    throw 'Jobs must be at least 1'
}
$build = [System.IO.Path]::GetFullPath($BuildDir)
New-Item -ItemType Directory -Path $build -Force | Out-Null
$env:MSYSTEM = 'UCRT64'
$env:CHERE_INVOKING = '1'
$env:NP560_SOURCE_PATH = $source
$env:NP560_BUILD_PATH = $build
$env:NP560_BUILD_JOBS = [string]$Jobs

$command = @'
set -e
source_dir="$(cygpath -u "$NP560_SOURCE_PATH")"
build_dir="$(cygpath -u "$NP560_BUILD_PATH")"
cd "$build_dir"
if [ ! -f build.ninja ]; then
    "$source_dir/configure" \
      --target-list=dmcu-softmmu --with-pkgversion=np560-windows \
      --disable-werror --disable-docs --disable-gtk --disable-sdl \
      --disable-opengl --disable-curses --disable-vnc --disable-slirp \
      --disable-capstone --disable-tools --disable-guest-agent \
      --disable-vhost-user --disable-vhost-kernel --disable-vhost-vdpa \
      --disable-vhost-net --disable-multiprocess --disable-plugins \
      --disable-libvduse --disable-vduse-blk-export
fi
ninja -j "$NP560_BUILD_JOBS" qemu-system-dmcu.exe
'@
& $bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw "Native Windows build failed with exit code $LASTEXITCODE"
}
Write-Host "Windows emulator: $(Join-Path $build 'qemu-system-dmcu.exe')"
