[CmdletBinding()]
param(
    [string]$ListenHost,
    [int]$Port
)

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
$ListenHost = if ($ListenHost) { $ListenHost } elseif ($env:API_HOST) { $env:API_HOST } else { '127.0.0.1' }
$Port = if ($PSBoundParameters.ContainsKey('Port')) { $Port } elseif ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$AppModule = if ($env:API_MODULE) { $env:API_MODULE } else { 'api.main:app' }
$LogFile = Join-Path $PSScriptRoot 'api.log'
$ErrorLogFile = Join-Path $PSScriptRoot 'api-error.log'
$PidFile = Join-Path $PSScriptRoot 'api.pid'
$Url = "http://${ListenHost}:$Port"
$Python = Join-Path $RootDir 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { $Python = 'python' }

if (-not (Test-Path -LiteralPath (Join-Path $RootDir 'api\main.py') -PathType Leaf)) {
    throw "API não encontrada: $(Join-Path $RootDir 'api\main.py')"
}

& $Python -c 'import fastapi, uvicorn' 2>$null
if ($LASTEXITCODE -ne 0) { throw 'FastAPI ou Uvicorn não estão instalados no ambiente Python selecionado.' }

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPid = [int](Get-Content -LiteralPath $PidFile -Raw)
    if (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue) {
        Write-Output "API já está disponível em: $Url/docs"
        return
    }
    Remove-Item -LiteralPath $PidFile -Force
}

$Arguments = @('-m', 'uvicorn', $AppModule, '--host', $ListenHost, '--port', $Port)
$Process = Start-Process -FilePath $Python -ArgumentList $Arguments -RedirectStandardOutput $LogFile -RedirectStandardError $ErrorLogFile -WindowStyle Hidden -PassThru
$Process.Id | Set-Content -LiteralPath $PidFile -NoNewline

for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
    try {
        $Response = Invoke-WebRequest -Uri "$Url/health" -TimeoutSec 2 -UseBasicParsing
        if ($Response.StatusCode -eq 200) {
            Write-Output "API disponível em: $Url/docs"
            return
        }
    } catch { }
    Start-Sleep -Seconds 1
}

throw "O processo foi iniciado, mas /health não respondeu a tempo. Consulte: $LogFile"
