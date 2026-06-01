@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "STORAGE_DIR=%PROJECT_ROOT%\storage"
set "NGROK_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"
set "NGROK_OUT=%STORAGE_DIR%\ngrok.out.log"
set "NGROK_ERR=%STORAGE_DIR%\ngrok.err.log"

echo ===============================================
echo  Publicacao Teams HTTPS (IIS + ngrok)
echo ===============================================
echo.

if not exist "%NGROK_EXE%" (
  echo [ERRO] ngrok.exe nao encontrado.
  echo Instale com: winget install --id Ngrok.Ngrok --exact
  exit /b 1
)

if not exist "%STORAGE_DIR%" mkdir "%STORAGE_DIR%"

echo [1/5] Subindo FastAPI local...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%stop_internal_fastapi.ps1" -ProjectRoot "%PROJECT_ROOT%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_internal_fastapi.ps1" -ProjectRoot "%PROJECT_ROOT%" -UseSystemPython
if errorlevel 1 (
  echo [ERRO] Falha ao iniciar FastAPI.
  exit /b 1
)
timeout /t 2 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%healthcheck_internal_fastapi.ps1" -BindAddress 127.0.0.1 -Port 8600
if errorlevel 1 (
  echo [ERRO] FastAPI nao respondeu no healthcheck interno.
  exit /b 1
)

echo [2/5] Validando proxy IIS (porta 8080)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -Uri 'http://localhost:8080/health' -UseBasicParsing -TimeoutSec 10; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 300){ exit 0 } else { exit 2 } } catch { exit 1 }"
if errorlevel 1 (
  echo [ERRO] IIS nao respondeu em http://localhost:8080/health
  echo Rode novamente a configuracao IIS FastAPI e tente de novo.
  exit /b 1
)

echo [3/5] Encerrando tunel ngrok anterior (se existir)...
taskkill /F /IM ngrok.exe >nul 2>nul
timeout /t 1 /nobreak >nul

echo [4/5] Iniciando tunel HTTPS para porta 8080...
if exist "%NGROK_OUT%" del /f /q "%NGROK_OUT%" >nul 2>nul
if exist "%NGROK_ERR%" del /f /q "%NGROK_ERR%" >nul 2>nul
start "ngrok-8080" /min "%NGROK_EXE%" http 8080 --log=stdout

echo [5/5] Obtendo URL publica...
timeout /t 4 /nobreak >nul
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue'; try { $t=Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -UseBasicParsing -TimeoutSec 5; ($t.tunnels | Where-Object { $_.public_url -like 'https://*' } | Select-Object -First 1 -ExpandProperty public_url) } catch { '' }"`) do set "PUBLIC_URL=%%i"

if "%PUBLIC_URL%"=="" (
  echo [ERRO] Nao foi possivel obter URL HTTPS do ngrok.
  echo.
  echo Verifique se o authtoken ja foi configurado:
  echo   "%SCRIPT_DIR%configurar_ngrok_token.bat"
  echo.
  echo Se quiser diagnosticar:
  echo   http://127.0.0.1:4040
  exit /b 1
)

echo [5/5] Publicacao pronta.
echo.
echo URL HTTPS para Teams:
echo   %PUBLIC_URL%
echo.
echo Health externo:
echo   %PUBLIC_URL%/health
echo.
echo Abra no navegador para validar:
start "" "%PUBLIC_URL%"

echo.
echo [IMPORTANTE] No manifest do Teams:
echo - contentUrl: %PUBLIC_URL%
echo - validDomains: somente o dominio (sem https), ex: abc123.ngrok-free.app
echo.
exit /b 0
