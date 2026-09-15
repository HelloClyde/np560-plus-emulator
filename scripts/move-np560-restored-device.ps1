# Internal DrvFS fallback: only publish an owned staging directory beside its
# final destination. Directory.Move never merges into or replaces a target.
param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Destination)
$ErrorActionPreference = 'Stop'
$taskSource = [IO.Path]::GetFullPath($Source).TrimEnd('\')
$taskDestination = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
if ([IO.Path]::GetDirectoryName($taskSource) -ine [IO.Path]::GetDirectoryName($taskDestination) -or
    -not [IO.Path]::GetFileName($taskSource).StartsWith('.np560-restore-') -or
    [IO.Path]::GetFileName($taskDestination).StartsWith('.np560-restore-')) {
    throw 'Invalid restore staging/destination relationship.'
}
[IO.Directory]::Move($taskSource, $taskDestination)
