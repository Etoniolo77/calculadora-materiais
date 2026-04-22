param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$BindAddress = "127.0.0.1",
    [int]$Port = 8600,
    [switch]$UseSystemPython,
    [string]$PythonCmd = "py"
)

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$storageDir = Join-Path $ProjectRoot "storage"
$pidFile = Join-Path $storageDir "fastapi.pid"
$outLog = Join-Path $storageDir "fastapi.out.log"
$errLog = Join-Path $storageDir "fastapi.err.log"

if (-not (Test-Path $storageDir)) { New-Item -ItemType Directory -Path $storageDir | Out-Null }

$pythonExe = $venvPython
if ($UseSystemPython -or -not (Test-Path $venvPython)) {
    $resolved = & $PythonCmd -c "import sys; print(sys.executable)"
    if ($LASTEXITCODE -ne 0 -or -not $resolved) {
        throw "Falha ao resolver executavel do Python global via '$PythonCmd'."
    }
    $pythonExe = $resolved.Trim()
    Write-Host "[START] Usando Python global: $pythonExe"
} else {
    Write-Host "[START] Usando Python da venv: $pythonExe"
}

if (Test-Path $pidFile) {
    $oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        throw "Ja existe processo FastAPI ativo (PID $oldPid). Execute stop_internal_fastapi.ps1 antes."
    } else {
        Remove-Item -LiteralPath $pidFile -Force
    }
}

$args = @(
    "-m", "uvicorn", "backend.app_fastapi:app",
    "--host", $BindAddress,
    "--port", "$Port"
)

$proc = Start-Process -FilePath $pythonExe -ArgumentList $args -WorkingDirectory $ProjectRoot -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
$proc.Id | Set-Content -Path $pidFile -Encoding ASCII

Write-Host "[START] FastAPI iniciada."
Write-Host "[START] PID: $($proc.Id)"
Write-Host "[START] URL local: http://$BindAddress`:$Port/"
Write-Host "[START] Logs:"
Write-Host "  OUT: $outLog"
Write-Host "  ERR: $errLog"
