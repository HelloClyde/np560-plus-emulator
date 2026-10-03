param(
    [Parameter(Mandatory = $true)][string]$Qemu,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$MsysRoot = 'C:\msys64',
    [string]$PythonZip
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$qemuPath = (Resolve-Path -LiteralPath $Qemu).Path
$output = [System.IO.Path]::GetFullPath($OutputDir)
$package = Join-Path $output 'np560-windows-x64'
$bin = Join-Path $package 'bin'
$runtime = Join-Path $package 'runtime\python'
$sourceWeb = Join-Path $project 'scripts\web'
$objdump = Join-Path $MsysRoot 'ucrt64\bin\objdump.exe'
$ucrtBin = Join-Path $MsysRoot 'ucrt64\bin'
if (-not (Test-Path -LiteralPath $objdump -PathType Leaf)) {
    throw "MSYS2 UCRT64 objdump not found: $objdump"
}
if (Test-Path -LiteralPath $package) {
    throw "Package staging already exists; choose an empty output directory: $package"
}
New-Item -ItemType Directory -Path $bin, $runtime, (Join-Path $package 'images'),
    (Join-Path $package 'scripts\web'), (Join-Path $package 'device') -Force | Out-Null
Copy-Item -LiteralPath $qemuPath -Destination (Join-Path $bin 'qemu-system-dmcu.exe')

# Recursively bundle the DLLs imported from MSYS2, not DLLs from the build
# machine's unrelated PATH entries. Windows system/API-set DLLs stay external.
$pending = [System.Collections.Generic.Queue[string]]::new()
$pending.Enqueue((Join-Path $bin 'qemu-system-dmcu.exe'))
$seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
while ($pending.Count -gt 0) {
    $binary = $pending.Dequeue()
    $imports = & $objdump -p $binary | Select-String '^\s*DLL Name:\s*(\S+)'
    if ($LASTEXITCODE -ne 0) { throw "objdump failed: $binary" }
    foreach ($match in $imports) {
        $name = $match.Matches[0].Groups[1].Value
        if (-not $seen.Add($name)) { continue }
        if ($name -match '^(api-ms-|ext-ms-)') { continue }
        if (Test-Path -LiteralPath (Join-Path $env:WINDIR "System32\$name")) { continue }
        $source = Join-Path $ucrtBin $name
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Missing UCRT64 dependency: $name (imported by $binary)"
        }
        $target = Join-Path $bin $name
        Copy-Item -LiteralPath $source -Destination $target
        $pending.Enqueue($target)
    }
}

$pythonVersion = '3.12.10'
$pythonSha = '4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3'
if (-not $PythonZip) {
    $PythonZip = Join-Path $output "python-$pythonVersion-embed-amd64.zip"
    if (-not (Test-Path -LiteralPath $PythonZip)) {
        Invoke-WebRequest "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip" -OutFile $PythonZip
    }
}
if ((Get-FileHash -LiteralPath $PythonZip -Algorithm SHA256).Hash -ne $pythonSha) {
    throw 'Embedded Python ZIP SHA-256 mismatch'
}
Expand-Archive -LiteralPath $PythonZip -DestinationPath $runtime
# The embedded distribution isolates imports by default. These paths enable
# only our packaged modules and the standard-library ZIP.
Set-Content -LiteralPath (Join-Path $runtime 'python312._pth') -Encoding ascii -Value @(
    'python312.zip', '.', '..\..\scripts', '..\..\scripts\web'
)

Copy-Item -Path (Join-Path $sourceWeb '*') -Destination (Join-Path $package 'scripts\web') -Recurse
$scripts = @('serve_np560_npe_codec.py', 'inject_np560_npe_fat16.py',
    'analyse_np560_npe.py', 'analyze_np560_ecc_checkpoint.py')
foreach ($name in $scripts) {
    Copy-Item -LiteralPath (Join-Path $project "scripts\$name") -Destination (Join-Path $package 'scripts')
}
Get-ChildItem -LiteralPath (Join-Path $project 'scripts') -Filter 'np560_mobivoice*.py' |
    ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $package 'scripts') }
Copy-Item -LiteralPath (Join-Path $project 'scripts\portable\Start-NP560.cmd') -Destination $package
Copy-Item -LiteralPath (Join-Path $project 'scripts\portable\Start-NP560.ps1') -Destination $package
Copy-Item -LiteralPath (Join-Path $project 'qemu-dmcu\COPYING') -Destination $package

# Start-NP560.cmd invokes Windows PowerShell 5.1, which reads a BOM-less .ps1
# using the local ANSI code page. Chinese diagnostics would then break parsing.
$launcher = Join-Path $package 'Start-NP560.ps1'
$launcherBytes = [System.IO.File]::ReadAllBytes($launcher)
if ($launcherBytes.Length -lt 3 -or $launcherBytes[0] -ne 0xef -or
    $launcherBytes[1] -ne 0xbb -or $launcherBytes[2] -ne 0xbf) {
    throw 'Portable launcher must start with a UTF-8 BOM for Windows PowerShell 5.1'
}
$escapedLauncher = $launcher.Replace("'", "''")
$parseCheck = @"
`$tokens = `$null
`$errors = `$null
[System.Management.Automation.Language.Parser]::ParseFile('$escapedLauncher', [ref]`$tokens, [ref]`$errors) | Out-Null
`$errors | ForEach-Object { Write-Error `$_.Message }
if (`$errors.Count -ne 0) { exit 1 }
"@
$encodedCheck = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($parseCheck))
& powershell.exe -NoProfile -NonInteractive -EncodedCommand $encodedCheck
if ($LASTEXITCODE -ne 0) { throw 'Portable launcher failed Windows PowerShell syntax check' }

# Smoke-test the exact self-contained Python executable without installed Python.
& (Join-Path $runtime 'python.exe') -c 'import np560_web, nand_files, device_config; from serve_np560_npe_codec import OwnedMode5Codec; print("portable Python OK")'
if ($LASTEXITCODE -ne 0) { throw 'Portable Python smoke test failed' }
& (Join-Path $bin 'qemu-system-dmcu.exe') --version | Select-Object -First 1
if ($LASTEXITCODE -ne 0) { throw 'Portable QEMU smoke test failed' }
$zip = Join-Path $output 'np560-windows-x64.zip'
if (Test-Path -LiteralPath $zip) { throw "Package ZIP already exists: $zip" }
Compress-Archive -LiteralPath $package -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Portable emulator: $zip"
