param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$BindAddress = "127.0.0.1",
    [int]$Port = 8501,
    [string]$BaseUrlPath = "",
    [switch]$NoBrowser,
    [switch]$UseSystemPython,
    [string]$PythonCmd = "py"
)

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$appPath = Join-Path $ProjectRoot "core\app.py"
$storageDir = Join-Path $ProjectRoot "storage"
$pidFile = Join-Path $storageDir "streamlit.pid"
$outLog = Join-Path $storageDir "streamlit.out.log"
$errLog = Join-Path $storageDir "streamlit.err.log"

if (-not (Test-Path $appPath)) { throw "App não encontrado: $appPath" }
if (-not (Test-Path $storageDir)) { New-Item -ItemType Directory -Path $storageDir | Out-Null }

$pythonExe = $venvPython
if ($UseSystemPython -or -not (Test-Path $venvPython)) {
    $resolved = & $PythonCmd -c "import sys; print(sys.executable)"
    if ($LASTEXITCODE -ne 0 -or -not $resolved) {
        throw "Falha ao resolver executável do Python global via '$PythonCmd'."
    }
    $pythonExe = $resolved.Trim()
    Write-Host "[START] Usando Python global: $pythonExe"
} else {
    Write-Host "[START] Usando Python da venv: $pythonExe"
}

if (Test-Path $pidFile) {
    $oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        throw "Já existe processo Streamlit ativo (PID $oldPid). Execute stop_internal_streamlit.ps1 antes."
    } else {
        Remove-Item -LiteralPath $pidFile -Force
    }
}

$args = @(
    "-m", "streamlit", "run", $appPath,
    "--server.address", $BindAddress,
    "--server.port", "$Port",
    "--server.enableCORS", "false",
    "--server.enableXsrfProtection", "false",
    "--server.enableWebsocketCompression", "false",
    "--server.fileWatcherType", "none"
)

if ($BaseUrlPath -ne "") {
    $args += @("--server.baseUrlPath", $BaseUrlPath.TrimStart("/"))
}
if ($NoBrowser) {
    $args += @("--server.headless", "true")
}

$proc = Start-Process -FilePath $pythonExe -ArgumentList $args -WorkingDirectory $ProjectRoot -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
$proc.Id | Set-Content -Path $pidFile -Encoding ASCII

Write-Host "[START] Streamlit iniciado."
Write-Host "[START] PID: $($proc.Id)"
Write-Host "[START] URL local: http://$BindAddress`:$Port/"
if ($BaseUrlPath -ne "") {
    Write-Host "[START] URL com base path: http://$BindAddress`:$Port/$($BaseUrlPath.Trim('/'))/"
}
Write-Host "[START] Logs:"
Write-Host "  OUT: $outLog"
Write-Host "  ERR: $errLog"
