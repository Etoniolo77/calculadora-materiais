@echo off
setlocal

set "ROOT_DIR=%~dp0"
start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%ROOT_DIR%scripts\iniciar_app.ps1" -KeepRunning
exit /b 0
