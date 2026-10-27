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
$HealthHost = $ListenHost
if ($HealthHost -eq '0.0.0.0') { $HealthHost = '127.0.0.1' }
if ($HealthHost -eq '::') { $HealthHost = '[::1]' }
elseif ($HealthHost.Contains(':') -and -not $HealthHost.StartsWith('[')) { $HealthHost = "[$HealthHost]" }
$Url = "http://${HealthHost}:$Port"

if (-not (Test-Path -LiteralPath $AppFile -PathType Leaf)) {
    throw "Dashboard não encontrado: $AppFile. Crie frontend\app.py antes de iniciar o Streamlit."
}
$AppFile = (Resolve-Path -LiteralPath $AppFile).Path
foreach ($ModuleFile in 'vision\geometry.py', 'vision\thermal.py', 'vision\pipeline.py') {
    $ModulePath = Join-Path $RootDir $ModuleFile
    if (-not (Test-Path -LiteralPath $ModulePath -PathType Leaf)) {
        throw "Módulo de visão computacional ausente: $ModulePath"
    }
}

$Python = Join-Path $RootDir 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { $Python = 'python' }

if ($Port -lt 1 -or $Port -gt 65535) { throw "Port deve estar entre 1 e 65535: $Port" }

& $Python -c 'import streamlit, pandas, plotly, cv2, numpy, sklearn, joblib' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'O dashboard requer Streamlit, Pandas, Plotly, OpenCV, NumPy, scikit-learn e Joblib no ambiente Python selecionado.'
}

# Reutiliza uma instância somente quando o endpoint de saúde responde.
try {
    $Response = Invoke-WebRequest -Uri "$Url/_stcore/health" -TimeoutSec 2 -UseBasicParsing
    if ($Response.StatusCode -eq 200) {
        Write-Output "Dashboard Streamlit disponível em: $Url"
        return
    }
} catch { }

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPidText = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    $ExistingPid = 0
    if ([int]::TryParse($ExistingPidText, [ref]$ExistingPid)) {
        $ExistingProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $ExistingPid" -ErrorAction SilentlyContinue
        if ($ExistingProcess) {
            $CommandLine = [string]$ExistingProcess.CommandLine
            if ($CommandLine -match '(?i)streamlit' -and
                $CommandLine.IndexOf($AppFile, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                throw "O dashboard (PID $ExistingPid) parece estar em execução, mas não responde em $Url. Consulte: $LogFile"
            }
            Write-Warning "O PID salvo em $PidFile pertence a outro processo; o arquivo será atualizado sem encerrar esse processo."
        }
        Remove-Item -LiteralPath $PidFile -Force
    } else {
        Remove-Item -LiteralPath $PidFile -Force
    }
}

$QuotedAppFile = '"' + $AppFile + '"'
$Arguments = @('-m', 'streamlit', 'run', $QuotedAppFile, '--server.address', $ListenHost, '--server.port', $Port, '--server.headless', 'true')
$Process = Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $RootDir -RedirectStandardOutput $LogFile -RedirectStandardError $ErrorLogFile -WindowStyle Hidden -PassThru
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
