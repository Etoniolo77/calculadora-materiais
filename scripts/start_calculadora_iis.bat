@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

echo ===============================================
echo  Calculadora - Start rapido (FastAPI + IIS)
echo ===============================================
echo.

echo [1/4] Encerrando instancia anterior (se existir)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%stop_internal_fastapi.ps1" -ProjectRoot "%PROJECT_ROOT%"

echo [2/4] Iniciando FastAPI...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_internal_fastapi.ps1" -ProjectRoot "%PROJECT_ROOT%" -UseSystemPython
if errorlevel 1 (
  echo [ERRO] Falha ao iniciar FastAPI.
  exit /b 1
)

echo [3/4] Validando health interno...
timeout /t 2 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%healthcheck_internal_fastapi.ps1" -BindAddress 127.0.0.1 -Port 8600
if errorlevel 1 (
  echo [ERRO] FastAPI nao respondeu no healthcheck interno.
  exit /b 1
)

echo [4/4] Verificando acesso via IIS (localhost:8080)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -Uri 'http://localhost:8080/health' -UseBasicParsing -TimeoutSec 10; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 300){ exit 0 } else { exit 2 } } catch { exit 1 }"
if errorlevel 1 (
  echo [AVISO] IIS nao respondeu em 8080. Abrindo URL direta da API...
  start "" "http://127.0.0.1:8600/"
) else (
  echo [OK] IIS respondeu com sucesso em http://localhost:8080/health
  start "" "http://localhost:8080/"
)

echo.
echo [OK] Inicializacao concluida.
exit /b 0

