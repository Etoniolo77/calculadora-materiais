@echo off
setlocal

set "ROOT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\install_app_local.ps1"

if errorlevel 1 (
  echo.
  echo Falha na instalacao. Verifique as mensagens acima.
  pause
  exit /b 1
)

echo.
echo Instalacao concluida.
timeout /t 2 >nul
exit /b 0
