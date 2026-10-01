# Exercise the real wrapper with a fake WSL boundary; never configure/build files.
$ErrorActionPreference = 'Stop'
$wrapper = Join-Path (Split-Path $PSScriptRoot -Parent) 'build-np560.ps1'
$global:np560BuildTest = @{ calls = [System.Collections.Generic.List[object]]::new(); translateExit = 0; buildExit = 0 }
function wsl.exe {
    $global:np560BuildTest.calls.Add(@($args))
    # PowerShell consumes the first -- when calling a function mock.
    if ($args[2] -eq 'wslpath') {
        $global:LASTEXITCODE = $global:np560BuildTest.translateExit
        if ($global:np560BuildTest.translateExit -eq 0) { "/mnt/c/source's folder/qemu-dmcu" }
    } else {
        $global:LASTEXITCODE = $global:np560BuildTest.buildExit
    }
}
function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Assert-Fails([scriptblock]$Action, [string]$Message) {
    $failed = $false
    try { & $Action | Out-Null } catch { $failed = $true }
    Assert-True $failed $Message
}

& $wrapper
Assert-True ($global:np560BuildTest.calls.Count -eq 2) 'default must translate then build'
Assert-True ($global:np560BuildTest.calls[0][1] -eq 'Ubuntu2') 'default distro changed'
$command = $global:np560BuildTest.calls[1][-1]
Assert-True ($global:np560BuildTest.calls[1][3] -eq '-c') 'build must avoid login shell'
Assert-True ($command.Contains("'/mnt/e/qemu-dmcu-build'")) 'default directory changed'
Assert-True ($command.Contains('ninja -j4 qemu-system-dmcu')) 'default jobs changed'
Assert-True (-not $command.Contains('meson configure')) 'keep must preserve optimization'
$escape = "'" + '"' + "'" + '"' + "'"
Assert-True ($command.Contains("source${escape}s folder")) 'source apostrophe not escaped'

$global:np560BuildTest.calls.Clear()
$command = & $wrapper -Distro TestDistro -BuildDirectory "/tmp/build's dir" -Jobs 2 -Optimization 3 -DryRun
Assert-True ($global:np560BuildTest.calls.Count -eq 1) 'dry run must not invoke build shell'
Assert-True ($global:np560BuildTest.calls[0][1] -eq 'TestDistro') 'custom distro ignored'
Assert-True ($command.Contains("'/tmp/build${escape}s dir'")) 'custom directory not quoted'
Assert-True ($command.Contains('ninja -j2')) 'custom jobs ignored'
Assert-True ($command.Contains('-Doptimization=3')) 'optimization ignored'

foreach ($mode in @('enabled', 'disabled')) {
    $ltoCommand = & $wrapper -Lto $mode -DryRun
    $expected = if ($mode -eq 'enabled') { 'true' } else { 'false' }
    Assert-True ($ltoCommand.Contains("-Db_lto=$expected")) 'LTO override ignored'
    Assert-True (-not $ltoCommand.Contains('-Doptimization=')) 'LTO changed optimization level'
}
Assert-Fails { & $wrapper -Lto 'invalid' } 'invalid LTO setting accepted'

Assert-Fails { & $wrapper -Jobs 0 } 'zero jobs accepted'
Assert-Fails { & $wrapper -BuildDirectory 'relative' } 'relative directory accepted'
Assert-Fails { & $wrapper -BuildDirectory '/' } 'filesystem root accepted'
$global:np560BuildTest.translateExit = 1
$global:np560BuildTest.calls.Clear()
Assert-Fails { & $wrapper } 'translation failure ignored'
Assert-True ($global:np560BuildTest.calls.Count -eq 1) 'build ran after translation failure'
$global:np560BuildTest.translateExit = 0
$global:np560BuildTest.buildExit = 17
Assert-Fails { & $wrapper } 'build failure ignored'
Write-Output 'Build wrapper: defaults, overrides, quoting, dry run and failures passed'
