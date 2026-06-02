param(
    [string]$InstallDir = "$env:LOCALAPPDATA\CalculadoraMateriais",
    [switch]$CreateDesktopShortcut = $true
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "[INSTALL] Origem: $projectRoot"
Write-Host "[INSTALL] Destino: $InstallDir"

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}

$sourceBackendRuntime = Join-Path $projectRoot "backend_runtime"
$installedBackendRuntime = Join-Path $InstallDir "backend_runtime"
if ((-not (Test-Path $sourceBackendRuntime)) -and (Test-Path $installedBackendRuntime)) {
    Write-Host "[INSTALL] Removendo backend_runtime antigo da instalacao fonte."
    Remove-Item -LiteralPath $installedBackendRuntime -Recurse -Force
}

$runtimeDirs = @("backend_runtime", "backend", "core", "data", "frontend", "scripts", "storage", "update", "auth")
$runtimeFiles = @("INICIAR_APP.cmd", "INSTALAR_APP.cmd", "app_version.json", "vocabulary.json")

foreach ($dir in $runtimeDirs) {
    $source = Join-Path $projectRoot $dir
    if (-not (Test-Path $source)) {
        continue
    }
    $destination = Join-Path $InstallDir $dir
    robocopy $source $destination /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD ".git" ".venv" "__pycache__" "archive" "dist" ".pytest_cache" /XF "*.log" "*.pid" | Out-Null
}

foreach ($file in $runtimeFiles) {
    $source = Join-Path $projectRoot $file
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination (Join-Path $InstallDir $file) -Force
    }
}

if ($CreateDesktopShortcut) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shell = New-Object -ComObject WScript.Shell

    $startLinkPath = Join-Path $desktop "Calculadora Materiais.lnk"
    $startTarget = Join-Path $InstallDir "INICIAR_APP.cmd"
    $startShortcut = $shell.CreateShortcut($startLinkPath)
    $startShortcut.TargetPath = $startTarget
    $startShortcut.WorkingDirectory = $InstallDir
    $startShortcut.Save()

}

Write-Host "[INSTALL] Instalacao concluida."
Write-Host "[INSTALL] Abra por: $InstallDir\INICIAR_APP.cmd"
