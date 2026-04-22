param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$SitePath = "C:\inetpub\wwwroot\calculadora-local"
)

$ErrorActionPreference = "Stop"

$templatePath = Join-Path $ProjectRoot "deploy\iis\web.fastapi.config.template"
if (-not (Test-Path $templatePath)) {
    throw "Template nao encontrado: $templatePath"
}

if (-not (Test-Path $SitePath)) {
    New-Item -ItemType Directory -Path $SitePath -Force | Out-Null
}

$targetConfig = Join-Path $SitePath "web.config"
Copy-Item -LiteralPath $templatePath -Destination $targetConfig -Force
Write-Host "[IIS] web.config (FastAPI) aplicado em $targetConfig"

$appcmd = Join-Path $env:windir "system32\inetsrv\appcmd.exe"
if (-not (Test-Path $appcmd)) {
    throw "appcmd nao encontrado. IIS pode nao estar instalado."
}

Write-Host "[IIS] Garantindo ARR Proxy habilitado no IIS"
& $appcmd set config -section:system.webServer/proxy /enabled:"True" /commit:apphost | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao habilitar ARR Proxy via appcmd."
}

Write-Host "[IIS] Concluido. Validar URL interna."
