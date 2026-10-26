[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
foreach ($Service in 'simulator', 'streamlit', 'api') {
    $PidFile = Join-Path $PSScriptRoot "$Service.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) { continue }

    $ProcessId = [int](Get-Content -LiteralPath $PidFile -Raw)
    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($Process) {
        Stop-Process -Id $ProcessId -Force
        Write-Output "$Service interrompido (PID $ProcessId)."
    }
    Remove-Item -LiteralPath $PidFile -Force
}
