[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
foreach ($Service in 'simulator', 'streamlit', 'api') {
    $PidFile = Join-Path $PSScriptRoot "$Service.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) { continue }

    $ProcessIdText = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    $ProcessId = 0
    if ([int]::TryParse($ProcessIdText, [ref]$ProcessId)) {
        $Process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
        if ($Process) {
            $CommandLine = [string]$Process.CommandLine
            $IsManagedProcess = switch ($Service) {
                'simulator' { $CommandLine -match '(?i)simulator\.py' }
                'streamlit' { $CommandLine -match '(?i)streamlit' -and $CommandLine -match '(?i)frontend[\\/]app\.py' }
                'api' { $CommandLine -match '(?i)uvicorn' -and $CommandLine -match '(?i)api\.main:app' }
            }
            if ($IsManagedProcess) {
                Stop-Process -Id $ProcessId -Force
                Write-Output "$Service interrompido (PID $ProcessId)."
            } else {
                Write-Warning "PID $ProcessId não corresponde ao comando esperado para $Service; o processo foi preservado."
            }
        } else {
            Write-Output "PID antigo removido para $Service."
        }
    } else {
        Write-Warning "Arquivo PID inválido para $Service; será removido sem encerrar processos."
    }
    Remove-Item -LiteralPath $PidFile -Force
}
