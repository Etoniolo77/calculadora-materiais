param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$SiteName = "calculadora-interna",
    [string]$SitePath = "C:\inetpub\wwwroot\calculadora-interna",
    [string]$Binding = "*:443:calculadora.suaempresa.local",
    [switch]$CreateSiteIfMissing
)

$ErrorActionPreference = "Stop"

$templatePath = Join-Path $ProjectRoot "deploy\iis\web.config.template"
if (-not (Test-Path $templatePath)) {
    throw "Template não encontrado: $templatePath"
}

if (-not (Test-Path $SitePath)) {
    New-Item -ItemType Directory -Path $SitePath -Force | Out-Null
}

$targetConfig = Join-Path $SitePath "web.config"
Copy-Item -LiteralPath $templatePath -Destination $targetConfig -Force
Write-Host "[IIS] web.config aplicado em $targetConfig"

$appcmd = Join-Path $env:windir "system32\inetsrv\appcmd.exe"
if (-not (Test-Path $appcmd)) {
    throw "appcmd não encontrado. IIS pode não estar instalado."
}

Write-Host "[IIS] Garantindo ARR Proxy habilitado no IIS"
& $appcmd set config -section:system.webServer/proxy /enabled:"True" /commit:apphost | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao habilitar ARR Proxy via appcmd."
}

if ($CreateSiteIfMissing) {
    & $appcmd list site $SiteName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[IIS] Criando site $SiteName com binding $Binding"
        & $appcmd add site /name:$SiteName /physicalPath:$SitePath /bindings:$Binding
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao criar site IIS '$SiteName'."
        }
    } else {
        Write-Host "[IIS] Site $SiteName já existe."
    }
}

Write-Host "[IIS] Concluído. Validar URL interna e ARR Proxy."
