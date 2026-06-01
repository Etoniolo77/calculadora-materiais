param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$BindAddress = "127.0.0.1",
    [int]$Port = 8600,
    [int]$HealthTimeoutSec = 20,
    [switch]$WaitForHealth,
    [switch]$UseSystemPython,
    [string]$PythonCmd = "py"
)

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$storageDir = Join-Path $ProjectRoot "storage"
$pidFile = Join-Path $storageDir "fastapi.pid"
$outLog = Join-Path $storageDir "fastapi.out.log"
$errLog = Join-Path $storageDir "fastapi.err.log"
$backendExe = Join-Path $ProjectRoot "backend_runtime\CalculadoraMateriaisBackend\CalculadoraMateriaisBackend.exe"

if (-not (Test-Path $storageDir)) { New-Item -ItemType Directory -Path $storageDir | Out-Null }

$usePackagedBackend = (Test-Path $backendExe) -and (-not $UseSystemPython)

if ($usePackagedBackend) {
    Write-Host "[START] Usando backend empacotado: $backendExe"
} else {
    $pythonExe = $venvPython
    if ($UseSystemPython -or -not (Test-Path $venvPython)) {
    $pythonCandidates = @()
    if ($PythonCmd) { $pythonCandidates += $PythonCmd }
    $pythonCandidates += @("py", "python", "python3")

    $resolved = $null
    foreach ($candidate in ($pythonCandidates | Select-Object -Unique)) {
        $cmdExists = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmdExists) {
            continue
        }
        try {
            $probe = & $candidate -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $probe) {
                $resolved = $probe.Trim()
                break
            }
        } catch {
            continue
        }
    }

    if ($LASTEXITCODE -ne 0 -or -not $resolved) {
        throw "Falha ao localizar Python global. Instale Python 3.x e marque 'Add Python to PATH'."
    }
        $pythonExe = $resolved.Trim()
        Write-Host "[START] Usando Python global: $pythonExe"
    } else {
        Write-Host "[START] Usando Python da venv: $pythonExe"
    }
}

# Evita instancias duplicadas do backend na mesma porta.
$uvicornPattern = "uvicorn backend.app_fastapi:app --host $BindAddress --port $Port"
$running = Get-CimInstance Win32_Process |
Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*$uvicornPattern*" }
foreach ($procInfo in $running) {
    try {
        Stop-Process -Id $procInfo.ProcessId -Force -ErrorAction Stop
        Write-Host "[START] Instancia antiga encerrada (PID $($procInfo.ProcessId))."
    } catch {
        Write-Host "[START] Aviso: nao foi possivel encerrar PID $($procInfo.ProcessId)."
    }
}

$exePattern = "CalculadoraMateriaisBackend.exe --host $BindAddress --port $Port"
$runningExe = Get-CimInstance Win32_Process |
Where-Object { $_.Name -eq "CalculadoraMateriaisBackend.exe" -and $_.CommandLine -like "*$exePattern*" }
foreach ($procInfo in $runningExe) {
    try {
        Stop-Process -Id $procInfo.ProcessId -Force -ErrorAction Stop
        Write-Host "[START] Instancia empacotada antiga encerrada (PID $($procInfo.ProcessId))."
    } catch {
        Write-Host "[START] Aviso: nao foi possivel encerrar PID $($procInfo.ProcessId)."
    }
}

if (Test-Path $pidFile) {
    $oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        throw "Ja existe processo FastAPI ativo (PID $oldPid). Execute stop_internal_fastapi.ps1 antes."
    } else {
        Remove-Item -LiteralPath $pidFile -Force
    }
}

if ($usePackagedBackend) {
    $backendArgs = @("--host", $BindAddress, "--port", "$Port")
    $proc = Start-Process -FilePath $backendExe -ArgumentList $backendArgs -WorkingDirectory $ProjectRoot -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
} else {
    $uvicornArgs = @(
        "-m", "uvicorn", "backend.app_fastapi:app",
        "--host", $BindAddress,
        "--port", "$Port"
    )
    $proc = Start-Process -FilePath $pythonExe -ArgumentList $uvicornArgs -WorkingDirectory $ProjectRoot -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
}
$proc.Id | Set-Content -Path $pidFile -Encoding ASCII

Write-Host "[START] FastAPI iniciada."
Write-Host "[START] PID: $($proc.Id)"
Write-Host "[START] URL local: http://$BindAddress`:$Port/"
Write-Host "[START] Logs:"
Write-Host "  OUT: $outLog"
Write-Host "  ERR: $errLog"

if ($WaitForHealth) {
    $healthUrl = "http://$BindAddress`:$Port/health"
    Write-Host "[START] Aguardando healthcheck em $healthUrl (timeout: ${HealthTimeoutSec}s)..."

    $deadline = (Get-Date).AddSeconds($HealthTimeoutSec)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 400
        }
    }

    if ($ready) {
        Write-Host "[START] Healthcheck OK."
    } else {
        Write-Host "[START] Healthcheck FALHOU. Encerrando processo iniciado (PID $($proc.Id))."
        try {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        } catch {}
        if (Test-Path $pidFile) {
            Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path $errLog) {
            Write-Host "[START] Ultimas linhas do log de erro:"
            Get-Content -LiteralPath $errLog -Tail 30 | Out-Host
        }
        throw "FastAPI iniciou mas nao respondeu ao healthcheck dentro de ${HealthTimeoutSec}s."
    }
}
