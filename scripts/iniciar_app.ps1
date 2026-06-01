param(
    [string]$BindAddress = "127.0.0.1",
    [int]$Port = 8600,
    [switch]$UseSystemPython,
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startScript = Join-Path $PSScriptRoot "start_internal_fastapi.ps1"
$healthScript = Join-Path $PSScriptRoot "healthcheck_internal_fastapi.ps1"
$ensurePythonScript = Join-Path $PSScriptRoot "ensure_python_runtime.ps1"
$cacheBust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$url = "http://$BindAddress`:$Port/auth/logout?v=$cacheBust"
$startupLog = Join-Path $projectRoot "storage\startup.log"

function Show-StartupError {
    param([string]$MessageText)
    try {
        $ws = New-Object -ComObject WScript.Shell
        $null = $ws.Popup($MessageText, 0, "Calculadora de Materiais", 16)
    } catch {
        # fallback silencioso
    }
}

try {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host " Calculadora de Materiais - Inicializacao Simplificada"
    Write-Host "============================================================"
    Write-Host ""

    if (-not (Test-Path $startScript)) {
        throw "Script de start nao encontrado: $startScript"
    }

    if (-not (Test-Path $healthScript)) {
        throw "Script de healthcheck nao encontrado: $healthScript"
    }
    if (-not (Test-Path $ensurePythonScript)) {
        throw "Script de bootstrap Python nao encontrado: $ensurePythonScript"
    }

    Write-Host "[0/3] Verificando runtime Python..."
    & $ensurePythonScript -ProjectRoot $projectRoot | Out-Host

    Write-Host "[1/3] Iniciando backend FastAPI..."
    try {
        if ($UseSystemPython) {
            & $startScript -ProjectRoot $projectRoot -BindAddress $BindAddress -Port $Port -UseSystemPython -WaitForHealth
        } else {
            & $startScript -ProjectRoot $projectRoot -BindAddress $BindAddress -Port $Port -WaitForHealth
        }
    } catch {
        $msg = $_.Exception.Message
        if ($msg -like "*Ja existe processo FastAPI ativo*") {
            Write-Host "[1/3] Backend ja estava em execucao. Reutilizando instancia atual."
        } else {
            throw
        }
    }

    Write-Host "[2/3] Validando resposta da aplicacao..."
    $healthOk = $false
    for ($i = 1; $i -le 10; $i++) {
        try {
            & $healthScript -BindAddress $BindAddress -Port $Port | Out-Host
            $healthOk = $true
            break
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $healthOk) {
        throw "Falha no healthcheck apos tentativas. Verifique logs em $projectRoot\storage."
    }

    Write-Host "[3/3] Abrindo no navegador..."

    $browserCandidates = @(
        "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe"
    )

    $browserExe = $browserCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($browserExe) {
        $browserProc = Start-Process -FilePath $browserExe -ArgumentList "--new-window", "--app=$url" -PassThru
        if (-not $KeepRunning) {
            Write-Host "Janela da aplicacao aberta. Ao fechar essa janela, o backend sera encerrado."
            Wait-Process -Id $browserProc.Id
        } else {
            Write-Host "Janela da aplicacao aberta em modo KeepRunning."
        }
    } else {
        try {
            Start-Process $url | Out-Null
        } catch {
            Start-Process "explorer.exe" $url | Out-Null
        }
        Write-Host "Navegador padrao aberto. Fechar a aba nao encerra backend nesse modo."
        Write-Host "Instale Edge/Chrome ou use stop_internal_fastapi.ps1 para encerramento manual."
    }

    Write-Host ""
    Write-Host "Aplicacao iniciada com sucesso."
    Write-Host "URL: $url"
    Write-Host ""
    if (-not $KeepRunning) {
        if (Test-Path $browserExe) {
            Write-Host "Encerrando backend apos fechamento da janela..."
            & (Join-Path $PSScriptRoot "stop_internal_fastapi.ps1") -ProjectRoot $projectRoot | Out-Host
        } else {
            Write-Host "Para parar a aplicacao, execute:"
            Write-Host "  .\scripts\stop_internal_fastapi.ps1"
        }
    } else {
        Write-Host "Modo KeepRunning ativo: backend permanece ligado."
        Write-Host "Para parar a aplicacao, execute:"
        Write-Host "  .\scripts\stop_internal_fastapi.ps1"
    }
    Write-Host ""
} catch {
    $errText = $_ | Out-String
    try { $errText | Set-Content -Path $startupLog -Encoding UTF8 } catch {}
    $msg = "Falha ao iniciar a Calculadora.`n`nVerifique: $startupLog"
    Show-StartupError -MessageText $msg
    exit 1
}
