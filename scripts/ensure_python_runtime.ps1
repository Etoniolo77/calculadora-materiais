param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    $candidates = @(
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe"
    )

    foreach ($c in $candidates) {
        if (Test-Path $c) {
            return $c
        }
    }

    foreach ($cmd in @("python", "py", "python3")) {
        $exists = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($exists) {
            try {
                $probe = & $cmd -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $probe) {
                    return $probe.Trim()
                }
            } catch {
                continue
            }
        }
    }

    return $null
}

function Install-PythonWithWinget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "winget nao encontrado. Instale o App Installer da Microsoft Store ou disponibilize Python previamente."
    }

    Write-Host "[PY] Python nao encontrado. Instalando Python 3.12 (escopo usuario)..."
    & winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar Python via winget."
    }
}

function Install-PythonWithLocalInstaller {
    param([string]$ProjectRoot)
    $localInstaller = Join-Path $ProjectRoot "scripts\bootstrap\python-installer.exe"
    if (-not (Test-Path $localInstaller)) {
        return $false
    }
    Write-Host "[PY] Usando instalador local de Python..."
    & $localInstaller /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 | Out-Null
    Start-Sleep -Seconds 3
    return $true
}

function Install-PythonFromWeb {
    $tmpInstaller = Join-Path $env:TEMP "python-3.12.10-amd64.exe"
    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    Write-Host "[PY] Baixando instalador Python do site oficial..."
    Invoke-WebRequest -Uri $url -OutFile $tmpInstaller
    & $tmpInstaller /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 | Out-Null
    Start-Sleep -Seconds 3
}

function Ensure-PipAndDeps {
    param([string]$PythonExe)

    $requirements = Join-Path $ProjectRoot "core\requirements.txt"
    if (-not (Test-Path $requirements)) {
        throw "requirements nao encontrado: $requirements"
    }

    & $PythonExe -m pip --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[PY] Pip nao encontrado. Executando ensurepip..."
        & $PythonExe -m ensurepip --upgrade
    }

    Write-Host "[PY] Atualizando pip/setuptools/wheel..."
    & $PythonExe -m pip install --upgrade pip setuptools wheel

    Write-Host "[PY] Instalando dependencias da aplicacao..."
    & $PythonExe -m pip install -r $requirements
}

$pythonExe = Resolve-PythonExe
if (-not $pythonExe) {
    $installed = $false
    try {
        Install-PythonWithWinget
        $installed = $true
    } catch {
        Write-Host "[PY] winget indisponivel/falhou. Tentando instalador local..."
    }
    if (-not $installed) {
        $installed = Install-PythonWithLocalInstaller -ProjectRoot $ProjectRoot
    }
    if (-not $installed) {
        Write-Host "[PY] Instalador local nao encontrado. Tentando download direto do Python..."
        Install-PythonFromWeb
    }
    Start-Sleep -Seconds 2
    $pythonExe = Resolve-PythonExe
}

if (-not $pythonExe) {
    throw "Python nao foi localizado apos tentativa de instalacao automatica."
}

Write-Host "[PY] Python localizado: $pythonExe"
Ensure-PipAndDeps -PythonExe $pythonExe
Write-Host "[PY] Runtime pronto."
