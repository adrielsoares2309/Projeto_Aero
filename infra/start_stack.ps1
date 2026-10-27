[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
$ApiHost = if ($env:API_HOST) { $env:API_HOST } else { '127.0.0.1' }
$ApiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$ApiConnectHost = $ApiHost
if ($ApiConnectHost -eq '0.0.0.0') { $ApiConnectHost = '127.0.0.1' }
if ($ApiConnectHost -eq '::') { $ApiConnectHost = '[::1]' }
$ApiUrl = if ($env:AEROMOTION_API_URL) { $env:AEROMOTION_API_URL } else { "http://${ApiConnectHost}:$ApiPort" }
$DashboardHost = if ($env:STREAMLIT_HOST) { $env:STREAMLIT_HOST } else { '127.0.0.1' }
$DashboardPort = if ($env:STREAMLIT_PORT) { [int]$env:STREAMLIT_PORT } else { 8501 }

try {
    & (Join-Path $PSScriptRoot 'start_api.ps1') -ListenHost $ApiHost -Port $ApiPort
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'Falha ao iniciar a API.' }

    & (Join-Path $PSScriptRoot 'start_simulator.ps1') -ApiUrl $ApiUrl
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'Falha ao iniciar o simulador.' }

    $PreviousApiUrl = $env:AEROMOTION_API_URL
    try {
        # O cliente da interface lê essa variável ao iniciar o processo Streamlit.
        $env:AEROMOTION_API_URL = $ApiUrl
        & (Join-Path $PSScriptRoot 'start_streamlit.ps1') -ListenHost $DashboardHost -Port $DashboardPort
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'Falha ao iniciar o dashboard.' }
    } finally {
        if ($null -eq $PreviousApiUrl) {
            Remove-Item Env:AEROMOTION_API_URL -ErrorAction SilentlyContinue
        } else {
            $env:AEROMOTION_API_URL = $PreviousApiUrl
        }
    }
} catch {
    Write-Error "Inicialização da pilha interrompida: $($_.Exception.Message)"
    throw
}

Write-Output ''
Write-Output "Dashboard: http://127.0.0.1:$DashboardPort"
Write-Output "API/Swagger: ${ApiUrl}/docs"
Write-Output 'Serviços locais iniciados: API, simulador e Streamlit.'
Write-Output 'Parar serviços gerenciados: .\infra\stop_services.ps1'
