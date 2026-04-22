param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$pidFile = Join-Path $ProjectRoot "storage\streamlit.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "[STOP] Nenhum PID registrado."
    exit 0
}

$pidValue = Get-Content $pidFile | Select-Object -First 1
if (-not $pidValue) {
    Remove-Item -LiteralPath $pidFile -Force
    Write-Host "[STOP] PID vazio removido."
    exit 0
}

$proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if ($null -eq $proc) {
    Remove-Item -LiteralPath $pidFile -Force
    Write-Host "[STOP] Processo não encontrado. PID limpo."
    exit 0
}

Stop-Process -Id $pidValue -Force
Start-Sleep -Seconds 1
Remove-Item -LiteralPath $pidFile -Force
Write-Host "[STOP] Streamlit encerrado (PID $pidValue)."
