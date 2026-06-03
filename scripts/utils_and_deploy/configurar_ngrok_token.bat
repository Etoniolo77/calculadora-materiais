@echo off
setlocal

set "NGROK_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"

if not exist "%NGROK_EXE%" (
  echo [ERRO] ngrok.exe nao encontrado.
  echo Instale com: winget install --id Ngrok.Ngrok --exact
  exit /b 1
)

echo ===============================================
echo  Configuracao do Token ngrok
echo ===============================================
echo 1) Acesse: https://dashboard.ngrok.com/get-started/your-authtoken
echo 2) Copie seu token.
echo.
set /p NGROK_TOKEN=Cole aqui o authtoken do ngrok: 

if "%NGROK_TOKEN%"=="" (
  echo [ERRO] Token vazio.
  exit /b 1
)

"%NGROK_EXE%" config add-authtoken %NGROK_TOKEN%
if errorlevel 1 (
  echo [ERRO] Falha ao gravar authtoken.
  exit /b 1
)

echo [OK] Authtoken configurado com sucesso.
exit /b 0

