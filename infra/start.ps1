[CmdletBinding()]
param(
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
if ($Stop) {
    & (Join-Path $PSScriptRoot 'stop_services.ps1')
    return
}

& (Join-Path $PSScriptRoot 'start_stack.ps1')
