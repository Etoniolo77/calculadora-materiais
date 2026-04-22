param(
    [string]$BindAddress = "127.0.0.1",
    [int]$Port = 8600
)

$ErrorActionPreference = "Stop"

$url = "http://$BindAddress`:$Port/health"
Write-Host "[HEALTH] Verificando $url"

try {
    $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
    if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
        Write-Host "[HEALTH] OK ($($resp.StatusCode))"
        exit 0
    }
    Write-Host "[HEALTH] Falha status: $($resp.StatusCode)"
    exit 2
} catch {
    Write-Host "[HEALTH] Erro: $($_.Exception.Message)"
    exit 1
}
