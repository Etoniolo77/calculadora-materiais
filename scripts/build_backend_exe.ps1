param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$pythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python da venv nao encontrado: $pythonExe"
}

$entryPoint = Join-Path $ProjectRoot "backend\run_server.py"
if (-not (Test-Path $entryPoint)) {
    throw "Entrypoint nao encontrado: $entryPoint"
}

$runtimeDir = Join-Path $ProjectRoot "backend_runtime"
$buildDir = Join-Path $ProjectRoot "build\pyinstaller"
$specDir = Join-Path $ProjectRoot "build\spec"

if ($Clean) {
    foreach ($path in @($runtimeDir, $buildDir, $specDir)) {
        if (Test-Path $path) {
            Remove-Item -Path $path -Recurse -Force
        }
    }
}

if (-not (Test-Path $runtimeDir)) { New-Item -ItemType Directory -Path $runtimeDir | Out-Null }
if (-not (Test-Path $buildDir)) { New-Item -ItemType Directory -Path $buildDir | Out-Null }
if (-not (Test-Path $specDir)) { New-Item -ItemType Directory -Path $specDir | Out-Null }

$args = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--name", "CalculadoraMateriaisBackend",
    "--distpath", $runtimeDir,
    "--workpath", $buildDir,
    "--specpath", $specDir,
    "--paths", (Join-Path $ProjectRoot "backend"),
    "--paths", (Join-Path $ProjectRoot "core"),
    "--hidden-import", "engine",
    "--hidden-import", "extractor",
    "--hidden-import", "final_report",
    "--hidden-import", "validators",
    "--hidden-import", "database_sqlite",
    "--hidden-import", "project_paths",
    "--hidden-import", "vocabulary",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan.on",
    "--collect-submodules", "pdfplumber",
    $entryPoint
)

Write-Host "[BUILD] Gerando backend executavel..."
& $pythonExe @args
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller falhou com exit code $LASTEXITCODE"
}

$exePath = Join-Path $runtimeDir "CalculadoraMateriaisBackend\CalculadoraMateriaisBackend.exe"
if (-not (Test-Path $exePath)) {
    throw "Executavel nao gerado: $exePath"
}

Write-Host "[BUILD] Executavel gerado: $exePath"
