param(
    [string]$ManifestUrl = "",
    [string]$TargetVersion = "",
    [string]$PackageUrl = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Get-VersionObject {
    param([string]$VersionText)
    try {
        return [version]$VersionText
    } catch {
        return [version]"0.0.0"
    }
}

function Test-AbsolutePackageReference {
    param([string]$Value)
    if ($Value -match "^[a-zA-Z][a-zA-Z0-9+.-]*://") {
        return $true
    }
    return [System.IO.Path]::IsPathRooted($Value)
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configPath = Join-Path $projectRoot "update\update_config.json"
$localVersionPath = Join-Path $projectRoot "app_version.json"
$storageDir = Join-Path $projectRoot "storage"
$backupDir = Join-Path $projectRoot "archive\updates"

if (-not (Test-Path $localVersionPath)) {
    throw "app_version.json nao encontrado em $localVersionPath"
}

$localVersionRaw = Get-Content -Path $localVersionPath -Raw | ConvertFrom-Json
$localVersion = [string]$localVersionRaw.version

if ($TargetVersion -and $PackageUrl) {
    $remoteVersion = $TargetVersion
    $packageUrl = $PackageUrl
} else {
if (-not $ManifestUrl) {
    if (-not (Test-Path $configPath)) {
        throw "update_config.json nao encontrado em $configPath"
    }
    $cfg = Get-Content -Path $configPath -Raw | ConvertFrom-Json
    $ManifestUrl = [string]$cfg.manifest_url
}

if (-not $ManifestUrl) {
    throw "ManifestUrl nao definido."
}

if ($ManifestUrl -match "SEU-ENDPOINT") {
    Write-Host ""
    Write-Host "[UPDATE] Configuracao pendente."
    Write-Host "Edite o arquivo update\\update_config.json e informe uma URL real no campo manifest_url."
    Write-Host "Exemplo: https://meuservidor/update_manifest.json"
    Write-Host ""
    exit 1
}

Write-Host "[UPDATE] Versao local: $localVersion"
Write-Host "[UPDATE] Consultando manifesto: $ManifestUrl"

try {
    if (Test-Path $ManifestUrl) {
        $manifest = Get-Content -Path $ManifestUrl -Raw | ConvertFrom-Json
        $manifestBase = Split-Path -Path (Resolve-Path $ManifestUrl).Path -Parent
    } else {
        $manifest = Invoke-RestMethod -Uri $ManifestUrl -Method Get
        $manifestBase = ([System.Uri]$ManifestUrl).GetLeftPart([System.UriPartial]::Path)
        $manifestBase = $manifestBase.Substring(0, $manifestBase.LastIndexOf("/") + 1)
    }
} catch {
    Write-Host ""
    Write-Host "[UPDATE] Nao foi possivel consultar o manifesto."
    Write-Host "Verifique se a URL esta correta e acessivel:"
    Write-Host "  $ManifestUrl"
    Write-Host ""
    Write-Host "Dica: para teste local, voce pode apontar para um arquivo .json local no update_config.json."
    Write-Host ""
    exit 1
}
$remoteVersion = [string]$manifest.version
$packageUrl = [string]$manifest.package_url

if (-not $remoteVersion -or -not $packageUrl) {
    throw "Manifesto invalido: campos 'version' e 'package_url' sao obrigatorios."
}

if (-not (Test-AbsolutePackageReference -Value $packageUrl)) {
    if ($manifestBase -match "^[a-zA-Z][a-zA-Z0-9+.-]*://") {
        $packageUrl = [System.Uri]::new([System.Uri]$manifestBase, $packageUrl).AbsoluteUri
    } else {
        $packageUrl = Join-Path $manifestBase $packageUrl
    }
}
}

$localV = Get-VersionObject -VersionText $localVersion
$remoteV = Get-VersionObject -VersionText $remoteVersion

if (-not $Force -and $remoteV -le $localV) {
    Write-Host "[UPDATE] Aplicacao ja esta atualizada."
    exit 0
}

if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$tempZip = Join-Path ([System.IO.Path]::GetTempPath()) ("calculadora-update-$timestamp.zip")
$tempExtract = Join-Path ([System.IO.Path]::GetTempPath()) ("calculadora-update-$timestamp")
$backupZip = Join-Path $backupDir ("backup-pre-update-$timestamp.zip")

Write-Host "[UPDATE] Gerando backup de seguranca..."
Compress-Archive -Path (Join-Path $projectRoot "*") -DestinationPath $backupZip -Force

Write-Host "[UPDATE] Obtendo pacote: $packageUrl"
if (Test-Path $packageUrl) {
    Copy-Item -Path $packageUrl -Destination $tempZip -Force
} elseif ($packageUrl -like "file://*") {
    $localPackage = ([System.Uri]$packageUrl).LocalPath
    Copy-Item -Path $localPackage -Destination $tempZip -Force
} else {
    Invoke-WebRequest -Uri $packageUrl -OutFile $tempZip
}

Write-Host "[UPDATE] Preparando arquivos..."
Expand-Archive -Path $tempZip -DestinationPath $tempExtract -Force

$sourceRoot = $tempExtract
$candidate = Get-ChildItem -Path $tempExtract -Directory | Select-Object -First 1
if ($candidate -and (Test-Path (Join-Path $candidate.FullName "app_version.json"))) {
    $sourceRoot = $candidate.FullName
}

$stopScript = Join-Path $projectRoot "scripts\stop_internal_fastapi.ps1"
if (Test-Path $stopScript) {
    Write-Host "[UPDATE] Encerrando backend antes de atualizar..."
    & $stopScript -ProjectRoot $projectRoot | Out-Host
}

Write-Host "[UPDATE] Aplicando atualizacao..."
$runtimeDirs = @("backend", "core", "data", "frontend", "scripts", "storage", "update", "auth")
$runtimeFiles = @("INICIAR_APP.cmd", "INSTALAR_APP.cmd", "app_version.json", "vocabulary.json")

foreach ($dir in $runtimeDirs) {
    $source = Join-Path $sourceRoot $dir
    if (-not (Test-Path $source)) {
        continue
    }
    $destination = Join-Path $projectRoot $dir
    robocopy $source $destination /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD ".git" ".venv" "__pycache__" "archive" "dist" ".pytest_cache" /XF "*.log" "*.pid" | Out-Null
}

foreach ($file in $runtimeFiles) {
    $source = Join-Path $sourceRoot $file
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination (Join-Path $projectRoot $file) -Force
    }
}

if (Test-Path $tempZip) { Remove-Item -Path $tempZip -Force }
if (Test-Path $tempExtract) { Remove-Item -Path $tempExtract -Recurse -Force }

Write-Host "[UPDATE] Atualizacao concluida para versao $remoteVersion."
Write-Host "[UPDATE] Backup salvo em: $backupZip"
