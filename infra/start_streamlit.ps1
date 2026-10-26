[CmdletBinding()]
param(
    [string]$ListenHost,
    [int]$Port
)

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
$ListenHost = if ($ListenHost) { $ListenHost } elseif ($env:STREAMLIT_HOST) { $env:STREAMLIT_HOST } else { '127.0.0.1' }
$Port = if ($PSBoundParameters.ContainsKey('Port')) { $Port } elseif ($env:STREAMLIT_PORT) { [int]$env:STREAMLIT_PORT } else { 8501 }
$AppFile = if ($env:STREAMLIT_APP) { $env:STREAMLIT_APP } else { Join-Path $RootDir 'frontend\app.py' }
$LogFile = Join-Path $PSScriptRoot 'streamlit.log'
$ErrorLogFile = Join-Path $PSScriptRoot 'streamlit-error.log'
$PidFile = Join-Path $PSScriptRoot 'streamlit.pid'
$Url = "http://${ListenHost}:$Port"

if (-not (Test-Path -LiteralPath $AppFile -PathType Leaf)) {
    throw "Dashboard não encontrado: $AppFile. Crie frontend\app.py antes de iniciar o Streamlit."
}

$Python = Join-Path $RootDir 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { $Python = 'python' }

& $Python -c 'import streamlit' 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Streamlit não está instalado no ambiente Python selecionado.' }

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPid = [int](Get-Content -LiteralPath $PidFile -Raw)
    if (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue) {
        Write-Output "Dashboard Streamlit já está disponível em: $Url"
        return
    }
    Remove-Item -LiteralPath $PidFile -Force
}

$Arguments = @('-m', 'streamlit', 'run', $AppFile, '--server.address', $ListenHost, '--server.port', $Port, '--server.headless', 'true')
$Process = Start-Process -FilePath $Python -ArgumentList $Arguments -RedirectStandardOutput $LogFile -RedirectStandardError $ErrorLogFile -WindowStyle Hidden -PassThru
$Process.Id | Set-Content -LiteralPath $PidFile -NoNewline

for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
    try {
        $Response = Invoke-WebRequest -Uri "$Url/_stcore/health" -TimeoutSec 2 -UseBasicParsing
        if ($Response.StatusCode -eq 200) {
            Write-Output "Dashboard Streamlit disponível em: $Url"
            return
        }
    } catch { }
    Start-Sleep -Seconds 1
}

throw "O processo foi iniciado, mas não respondeu a tempo. Consulte: $LogFile"
