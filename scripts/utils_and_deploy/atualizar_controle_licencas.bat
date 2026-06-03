@echo off
setlocal
cd /d "%~dp0.."
.\.venv\Scripts\python.exe .\scripts\gerar_controle_licencas_office365.py
if %errorlevel% neq 0 (
  echo Falha ao atualizar a planilha.
  exit /b %errorlevel%
)
echo Planilha atualizada com sucesso.
