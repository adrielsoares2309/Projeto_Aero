[CmdletBinding()]
param(
    [ValidateSet('Cruzeiro', 'Carga_Media', 'Carga_Alta')]
    [string]$Regime,
    [double]$IntervalSeconds,
    [int]$Quantity,
    [int]$Seed
)

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
$ApiUrl = if ($env:AEROMOTION_API_URL) { $env:AEROMOTION_API_URL } else { 'http://127.0.0.1:8000' }
$Regime = if ($Regime) { $Regime } elseif ($env:SIMULATOR_REGIME) { $env:SIMULATOR_REGIME } else { 'Cruzeiro' }
$IntervalSeconds = if ($PSBoundParameters.ContainsKey('IntervalSeconds')) { $IntervalSeconds } elseif ($env:SIMULATOR_INTERVAL) { [double]$env:SIMULATOR_INTERVAL } else { 5 }
$Quantity = if ($PSBoundParameters.ContainsKey('Quantity')) { $Quantity } elseif ($env:SIMULATOR_QUANTITY) { [int]$env:SIMULATOR_QUANTITY } else { 0 }
$Seed = if ($PSBoundParameters.ContainsKey('Seed')) { $Seed } elseif ($env:SIMULATOR_SEED) { [int]$env:SIMULATOR_SEED } else { 42 }
$SimulatorFile = Join-Path $RootDir 'simulator.py'
$LogFile = Join-Path $PSScriptRoot 'simulator.log'
$ErrorLogFile = Join-Path $PSScriptRoot 'simulator-error.log'
$PidFile = Join-Path $PSScriptRoot 'simulator.pid'
$Python = Join-Path $RootDir 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { $Python = 'python' }

if (-not (Test-Path -LiteralPath $SimulatorFile -PathType Leaf)) {
    throw "Simulador não encontrado: $SimulatorFile"
}
if ($Regime -notin 'Cruzeiro', 'Carga_Media', 'Carga_Alta') {
    throw "Regime inválido: $Regime. Use Cruzeiro, Carga_Media ou Carga_Alta."
}
if ($IntervalSeconds -le 0 -or $Quantity -lt 0) {
    throw 'IntervalSeconds deve ser maior que zero e Quantity não pode ser negativo.'
}
try {
    $Health = Invoke-WebRequest -Uri "$ApiUrl/health" -UseBasicParsing -TimeoutSec 4
    if ($Health.StatusCode -ne 200) { throw 'Resposta de saúde inesperada.' }
} catch {
    throw "A API não está disponível em $ApiUrl. Inicie a API antes do simulador."
}

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPid = [int](Get-Content -LiteralPath $PidFile -Raw)
    if (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue) {
        Write-Output "Simulador já está em execução (PID $ExistingPid). Use o dashboard para trocar de regime."
        return
    }
    Remove-Item -LiteralPath $PidFile -Force
}

$Arguments = @(
    $SimulatorFile, '--api-url', $ApiUrl,
    '--regime', $Regime, '--intervalo', $IntervalSeconds,
    '--quantidade', $Quantity, '--seed', $Seed
)
$Process = Start-Process -FilePath $Python -ArgumentList $Arguments -RedirectStandardOutput $LogFile -RedirectStandardError $ErrorLogFile -WindowStyle Hidden -PassThru
$Process.Id | Set-Content -LiteralPath $PidFile -NoNewline
Start-Sleep -Milliseconds 750
if (-not (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    throw "O simulador encerrou durante a inicialização. Consulte: $ErrorLogFile"
}
Write-Output "Simulador iniciado para TURB-101 a TURB-104 / $Regime (PID $($Process.Id))."
