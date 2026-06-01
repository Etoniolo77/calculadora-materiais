param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$SiteName = "calculadora-local",
    [string]$SitePath = "C:\inetpub\wwwroot\calculadora-local",
    [int]$Port = 8080,
    [string]$HostHeader = "",
    [switch]$OpenFirewall
)

$ErrorActionPreference = "Stop"
Import-Module WebAdministration -ErrorAction Stop

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

Write-Host "[IIS] Garantindo site '$SiteName' com pasta '$SitePath'"
& $appcmd list site "$SiteName" | Out-Null
if ($LASTEXITCODE -ne 0) {
    $bindingAdd = ("http/*:{0}:{1}" -f $Port, $HostHeader)
    Write-Host "[IIS] Criando site $SiteName (binding $bindingAdd)"
    & $appcmd add site /name:"$SiteName" /physicalPath:"$SitePath" /bindings:"$bindingAdd" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar site IIS '$SiteName'."
    }
} else {
    # Em site existente, o physicalPath deve ser ajustado no VDIR raiz (siteName/)
    & $appcmd set vdir "$SiteName/" /physicalPath:"$SitePath" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # Fallback para app raiz quando o vdir nao estiver acessivel no provedor
        & $appcmd set app "$SiteName/" /physicalPath:"$SitePath" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao ajustar physicalPath do site '$SiteName'."
        }
    }
}

$bindingNeedle = ("*:{0}:{1}" -f $Port, $HostHeader)

# Remover conflito de binding em outros sites (porta/host iguais)
$allSites = Get-Website
foreach ($s in $allSites) {
    if ($s.Name -eq $SiteName) { continue }
    $conflict = Get-WebBinding -Name $s.Name -Protocol "http" -ErrorAction SilentlyContinue |
        Where-Object { $_.bindingInformation -eq $bindingNeedle }
    if ($conflict) {
        Write-Host "[IIS] Removendo binding conflitante $bindingNeedle do site '$($s.Name)'"
        Remove-WebBinding -Name $s.Name -Protocol "http" -Port $Port -HostHeader $HostHeader -ErrorAction Stop
    }
}

$siteBinding = Get-WebBinding -Name $SiteName -Protocol "http" -ErrorAction SilentlyContinue |
    Where-Object { $_.bindingInformation -eq $bindingNeedle }
if (-not $siteBinding) {
    Write-Host "[IIS] Adicionando binding http/$bindingNeedle"
    New-WebBinding -Name $SiteName -Protocol "http" -Port $Port -IPAddress "*" -HostHeader $HostHeader | Out-Null
}

Write-Host "[IIS] Garantindo ARR Proxy habilitado no IIS"
& $appcmd set config -section:system.webServer/proxy /enabled:"True" /commit:apphost | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao habilitar ARR Proxy via appcmd."
}

if ($OpenFirewall) {
    $ruleName = "IIS-FastAPI-$Port"
    & netsh advfirewall firewall add rule name="$ruleName" dir=in action=allow protocol=TCP localport=$Port | Out-Null
}

Start-Website -Name $SiteName
Write-Host "[IIS] Concluido. Site: $SiteName | URL: http://localhost:$Port/"
