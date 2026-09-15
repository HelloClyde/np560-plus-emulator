[CmdletBinding()]
param(
    [Parameter(Mandatory, ParameterSetName='Backup')][string]$Device,
    [Parameter(Mandatory, ParameterSetName='Backup')][string]$BackupTo,
    [Parameter(Mandatory, ParameterSetName='Restore')][string]$RestoreFrom,
    [Parameter(Mandatory, ParameterSetName='Restore')][string]$RestoreTo,
    [string]$Qemu = 'E:\qemu-dmcu-build\qemu-system-dmcu'
)

$ErrorActionPreference = 'Stop'
$taskDistro = 'Ubuntu2'
function ConvertTo-DeviceWslPath([string]$Value) {
    $taskAbsolute = [IO.Path]::GetFullPath($Value) -replace '\\', '/'
    $taskTranslated = (& wsl.exe -d $taskDistro -- wslpath -a -- $taskAbsolute).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $taskTranslated) { throw 'Unable to translate device path into WSL.' }
    return $taskTranslated
}
$taskScript = ConvertTo-DeviceWslPath (Join-Path $PSScriptRoot 'np560_device_backup.py')
if ($PSCmdlet.ParameterSetName -eq 'Backup') {
    $taskArguments = @($taskScript, 'backup', '--device', (ConvertTo-DeviceWslPath $Device),
        '--output', (ConvertTo-DeviceWslPath $BackupTo))
    if ($PSBoundParameters.ContainsKey('Qemu')) {
        $taskArguments += @('--qemu', (ConvertTo-DeviceWslPath $Qemu))
    }
} else {
    $taskArguments = @($taskScript, 'restore', '--backup', (ConvertTo-DeviceWslPath $RestoreFrom),
        '--output-directory', (ConvertTo-DeviceWslPath $RestoreTo), '--qemu', (ConvertTo-DeviceWslPath $Qemu))
}
& wsl.exe -d $taskDistro -- python3 @taskArguments
exit $LASTEXITCODE
