@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "STORAGE_DIR=%PROJECT_ROOT%\storage"
set "CF_EXE=C:\Program Files (x86)\cloudflared\cloudflared.exe"
set "CF_LOG=%STORAGE_DIR%\cloudflared.err.log"
set "TEAMS_FILE=%STORAGE_DIR%\teams_public_url.txt"

echo ===============================================
echo  Publicacao Teams HTTPS (Cloudflare Tunnel)
echo ===============================================
echo.

if not exist "!CF_EXE!" (
  echo [ERRO] cloudflared.exe nao encontrado em:
  echo   !CF_EXE!
  echo Instale com: winget install --id Cloudflare.cloudflared --exact
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

echo [2/5] Validando IIS em localhost:8080...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -Uri 'http://localhost:8080/health' -UseBasicParsing -TimeoutSec 10; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 300){ exit 0 } else { exit 2 } } catch { exit 1 }"
if errorlevel 1 (
  echo [ERRO] IIS nao respondeu em http://localhost:8080/health
  exit /b 1
)

echo [3/5] Encerrando tunel Cloudflare anterior (se existir)...
taskkill /F /IM cloudflared.exe >nul 2>nul
timeout /t 1 /nobreak >nul
if exist "%CF_LOG%" del /f /q "%CF_LOG%" >nul 2>nul

echo [4/5] Iniciando tunel HTTPS...
start "cloudflared-8080" /min "!CF_EXE!" tunnel --url http://localhost:8080 --no-autoupdate --log "%CF_LOG%" --loglevel info

echo [5/5] Capturando URL publica...
timeout /t 8 /nobreak >nul
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$log='%CF_LOG%'; if(-not (Test-Path $log)){''; exit}; $txt=Get-Content $log -Raw; $m=[regex]::Match($txt,'https://[a-zA-Z0-9\\-\\.]+\\.trycloudflare\\.com'); if($m.Success){$m.Value}else{''}"`) do set "PUBLIC_URL=%%i"

if "%PUBLIC_URL%"=="" (
  echo [ERRO] Nao foi possivel identificar a URL publica.
  echo Verifique log: %CF_LOG%
  exit /b 1
)

for /f "tokens=1* delims=/" %%a in ("%PUBLIC_URL%") do set "TMP=%%a"
set "DOMAIN=%PUBLIC_URL:https://=%"
for /f "tokens=1 delims=/" %%d in ("%DOMAIN%") do set "DOMAIN=%%d"

(
  echo URL=%PUBLIC_URL%
  echo DOMAIN=%DOMAIN%
) > "%TEAMS_FILE%"

echo.
echo [OK] URL HTTPS para Teams:
echo   %PUBLIC_URL%
echo.
echo [OK] Dominio para validDomains:
echo   %DOMAIN%
echo.
echo Arquivo salvo em:
echo   %TEAMS_FILE%
echo.
start "" "%PUBLIC_URL%"
exit /b 0
