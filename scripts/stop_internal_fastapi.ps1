param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Continue"

# 1. Encontrar processo escutando na porta 8600
Write-Host "[STOP] Verificando conexoes na porta 8600..."
$connections = Get-NetTCPConnection -LocalPort 8600 -State Listen -ErrorAction SilentlyContinue
if ($connections) {
    foreach ($conn in $connections) {
        $targetPid = $conn.OwningProcess
        if ($targetPid -and $targetPid -ne 0) {
            Write-Host "[STOP] Finalizando processo escutando na porta 8600 (PID $targetPid)..."
            Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    try {
        $netstatOut = netstat -ano | Select-String "8600" | Select-String "LISTENING"
        foreach ($line in $netstatOut) {
            $parts = $line.ToString().Trim() -split '\s+'
            if ($parts.Length -ge 5) {
                $targetPid = $parts[-1]
                if ($targetPid -as [int] -and $targetPid -ne 0) {
                    Write-Host "[STOP] Finalizando processo via netstat (PID $targetPid)..."
                    Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
                }
            }
        }
    } catch {}
}

# 2. Ler fastapi.pid
$pidFile = Join-Path $ProjectRoot "storage\fastapi.pid"
if (Test-Path $pidFile) {
    $pidValue = Get-Content $pidFile | Select-Object -First 1
    if ($pidValue -and ($pidValue -as [int])) {
        Write-Host "[STOP] Finalizando processo registrado no PID file (PID $pidValue)..."
        Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

# 3. Garantir limpeza de outros processos Python/Calculadora residuais do projeto
$uvicornPattern = "uvicorn backend.app_fastapi:app"
$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*$uvicornPattern*" }
foreach ($procInfo in $running) {
    Write-Host "[STOP] Finalizando processo Python residual (PID $($procInfo.ProcessId))..."
    Stop-Process -Id $procInfo.ProcessId -Force -ErrorAction SilentlyContinue
}

$runningExe = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "CalculadoraMateriaisBackend.exe" }
foreach ($procInfo in $runningExe) {
    Write-Host "[STOP] Finalizando processo Calculadora residual (PID $($procInfo.ProcessId))..."
    Stop-Process -Id $procInfo.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "[STOP] Parada concluida com sucesso."
exit 0
