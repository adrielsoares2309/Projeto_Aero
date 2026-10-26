[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'start_api.ps1')
& (Join-Path $PSScriptRoot 'start_simulator.ps1')
& (Join-Path $PSScriptRoot 'start_streamlit.ps1')
