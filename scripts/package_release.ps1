param(
    [string]$Version = "",
    [string]$PackageUrl = "",
    [string]$OutputDir = "",
    [switch]$SourcePackage
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$versionPath = Join-Path $projectRoot "app_version.json"

if (-not (Test-Path $versionPath)) {
    throw "app_version.json nao encontrado em $versionPath"
}

if (-not $Version) {
    $versionData = Get-Content -Path $versionPath -Raw | ConvertFrom-Json
    $Version = [string]$versionData.version
}

if (-not $Version) {
    throw "Versao nao definida."
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $projectRoot "dist"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$packageName = "CalculadoraMateriais-$Version.zip"
$packagePath = Join-Path $OutputDir $packageName
$manifestPath = Join-Path $OutputDir "update_manifest.json"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) "calculadora-release-$Version-$timestamp"

if (Test-Path $stageRoot) {
    Remove-Item -Path $stageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $stageRoot | Out-Null

$compiledBackend = Join-Path $projectRoot "backend_runtime\CalculadoraMateriaisBackend\CalculadoraMateriaisBackend.exe"
$compiledPackage = $false
if ((-not $SourcePackage) -and (Test-Path $compiledBackend)) {
    $compiledPackage = $true
    $runtimeDirs = @("backend_runtime", "data", "frontend", "update", "auth")
    Write-Host "[PACKAGE] Modo compilado: backend/core Python nao serao incluidos no pacote."
} else {
    $runtimeDirs = @("backend", "core", "data", "frontend", "scripts", "update", "auth")
    Write-Host "[PACKAGE] Modo fonte: backend/core Python serao incluidos no pacote."
}
$runtimeFiles = @("INICIAR_APP.cmd", "INSTALAR_APP.cmd", "app_version.json", "vocabulary.json", "pytest.ini")

foreach ($dir in $runtimeDirs) {
    $source = Join-Path $projectRoot $dir
    if (-not (Test-Path $source)) {
        continue
    }
    $destination = Join-Path $stageRoot $dir
    robocopy $source $destination /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD ".git" ".venv" "__pycache__" "archive" "dist" ".pytest_cache" "tmp" /XF "*.log" "*.pid" | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Falha ao copiar diretorio $dir. Robocopy exit code: $LASTEXITCODE"
    }
}

foreach ($file in $runtimeFiles) {
    $source = Join-Path $projectRoot $file
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination (Join-Path $stageRoot $file) -Force
    }
}

if ($compiledPackage) {
    $scriptDestination = Join-Path $stageRoot "scripts"
    New-Item -ItemType Directory -Path $scriptDestination -Force | Out-Null
    $runtimeScripts = @(
        "iniciar_app.ps1",
        "install_app_local.ps1",
        "start_internal_fastapi.ps1",
        "stop_internal_fastapi.ps1",
        "healthcheck_internal_fastapi.ps1",
        "update_app.ps1"
    )
    foreach ($script in $runtimeScripts) {
        $source = Join-Path $projectRoot "scripts\$script"
        if (Test-Path $source) {
            Copy-Item -Path $source -Destination (Join-Path $scriptDestination $script) -Force
        }
    }
}

$storageDir = Join-Path $stageRoot "storage"
if (-not (Test-Path $storageDir)) {
    New-Item -ItemType Directory -Path $storageDir | Out-Null
}

if (Test-Path $packagePath) {
    Remove-Item -Path $packagePath -Force
}

Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $packagePath -Force

if (-not $PackageUrl) {
    $PackageUrl = $packageName
}

$manifest = [ordered]@{
    version = $Version
    package_url = $PackageUrl
    notes = "Pacote privado para distribuicao interna via SharePoint, Teams ou pasta de rede."
}

$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath -Encoding UTF8

Remove-Item -Path $stageRoot -Recurse -Force

Write-Host "[PACKAGE] Pacote gerado: $packagePath"
Write-Host "[PACKAGE] Manifesto gerado: $manifestPath"
Write-Host "[PACKAGE] Publique ambos em SharePoint/Teams/pasta privada e configure update\\update_config.json com o caminho do manifesto."
