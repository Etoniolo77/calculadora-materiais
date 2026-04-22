param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$PythonCmd = "py",
    [switch]$ForceReinstall,
    [switch]$RebuildVenv,
    [switch]$AllowSystemPythonFallback
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao executar: $FilePath $($Arguments -join ' ') (exit $LASTEXITCODE)"
    }
}

Write-Host "[SETUP] Projeto: $ProjectRoot"

$venvPath = Join-Path $ProjectRoot ".venv"
$requirements = Join-Path $ProjectRoot "core\requirements.txt"
$streamlitDir = Join-Path $ProjectRoot ".streamlit"
$streamlitCfg = Join-Path $streamlitDir "config.toml"
$storageDir = Join-Path $ProjectRoot "storage"
$tmpDir = Join-Path $storageDir "tmp"

if (-not (Test-Path $requirements)) {
    throw "Arquivo não encontrado: $requirements"
}

if (-not (Test-Path $storageDir)) {
    New-Item -ItemType Directory -Path $storageDir | Out-Null
}
if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir | Out-Null
}

# Evita problemas de permissão no TEMP padrão do usuário em ambientes corporativos
$env:TEMP = $tmpDir
$env:TMP = $tmpDir

if ($RebuildVenv -and (Test-Path $venvPath)) {
    Write-Host "[SETUP] Recriando venv (modo RebuildVenv)"
    Remove-Item -LiteralPath $venvPath -Recurse -Force
}

if (-not (Test-Path $venvPath)) {
    Write-Host "[SETUP] Criando ambiente virtual em $venvPath"
    & $PythonCmd -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[SETUP] venv padrão falhou. Tentando '--without-pip'..."
        & $PythonCmd -m venv --without-pip $venvPath
        if ($LASTEXITCODE -ne 0) {
            if ($AllowSystemPythonFallback) {
                Write-Host "[SETUP] Falha na venv. Seguindo com Python global por fallback."
            } else {
                throw "Falha ao criar venv em $venvPath"
            }
        }
    }
}

$pythonExe = Join-Path $venvPath "Scripts\python.exe"
if (Test-Path $pythonExe) {
    Write-Host "[SETUP] Instalando dependências na venv"
    & $pythonExe -m pip --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[SETUP] Pip não encontrado na venv. Executando ensurepip..."
        try {
            Invoke-Checked -FilePath $pythonExe -Arguments @("-m", "ensurepip", "--upgrade")
        } catch {
            Write-Host "[SETUP] Ensurepip falhou. Tentando bootstrap via pip global..."
            & $PythonCmd -m pip --python $pythonExe install --upgrade pip setuptools wheel
            if ($LASTEXITCODE -ne 0) {
                if ($AllowSystemPythonFallback) {
                    Write-Host "[SETUP] Falha ao preparar pip na venv. Fallback para Python global."
                } else {
                    throw "Falha ao instalar pip na venv via pip global."
                }
            }
        }
    }

    & $pythonExe -m pip --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Invoke-Checked -FilePath $pythonExe -Arguments @("-m", "pip", "install", "--upgrade", "pip")
        if ($ForceReinstall) {
            Invoke-Checked -FilePath $pythonExe -Arguments @("-m", "pip", "install", "--force-reinstall", "-r", $requirements)
        } else {
            Invoke-Checked -FilePath $pythonExe -Arguments @("-m", "pip", "install", "-r", $requirements)
        }
    }
} elseif (-not $AllowSystemPythonFallback) {
    throw "Python da venv não encontrado: $pythonExe"
}

if (-not (Test-Path $streamlitDir)) {
    New-Item -ItemType Directory -Path $streamlitDir | Out-Null
}
$cfg = @"
[server]
headless = true
enableCORS = false
enableXsrfProtection = false
enableWebsocketCompression = false
fileWatcherType = "none"
runOnSave = false
address = "127.0.0.1"
port = 8501
maxUploadSize = 200

[browser]
gatherUsageStats = false
"@

Set-Content -Path $streamlitCfg -Value $cfg -Encoding UTF8

Write-Host "[SETUP] Concluído."
Write-Host "[SETUP] Próximo passo: executar scripts\start_internal_streamlit.ps1"
