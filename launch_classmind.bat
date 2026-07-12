@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ClassMind Launcher

set "APP_URL=http://127.0.0.1:8766"
set "PYTHON=C:\Users\22314\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PYTHON%" goto PYTHON_READY
where py.exe >nul 2>nul
if not errorlevel 1 set "PYTHON=py.exe"& goto PYTHON_READY
where python.exe >nul 2>nul
if not errorlevel 1 set "PYTHON=python.exe"& goto PYTHON_READY
echo ERROR: Python was not found.
pause
exit /b 1

:PYTHON_READY
"%PYTHON%" -c "import ortools" >nul 2>nul
if not errorlevel 1 goto CHECK_RUNNING
echo Installing required packages. Please wait...
"%PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto FAILED

:CHECK_RUNNING
powershell.exe -NoProfile -Command "try{$r=Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%/api/health' -TimeoutSec 2;if($r.StatusCode -eq 200){exit 0}}catch{};exit 1"
if not errorlevel 1 goto OPEN_APP

echo Starting ClassMind server window...
start "ClassMind Server" /min "%ComSpec%" /d /c call "%~dp0run_server.bat"

set "READY=0"
for /L %%G in (1,1,30) do call :WAIT_ONCE
if "%READY%"=="1" goto OPEN_APP
echo ERROR: Server did not become ready within 30 seconds.
goto FAILED

:WAIT_ONCE
if "%READY%"=="1" exit /b 0
powershell.exe -NoProfile -Command "try{$r=Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%/api/health' -TimeoutSec 1;if($r.StatusCode -eq 200){exit 0}}catch{};exit 1"
if not errorlevel 1 set "READY=1"& exit /b 0
timeout /t 1 /nobreak >nul
exit /b 0

:OPEN_APP
echo ClassMind is ready: %APP_URL%
start "" "%APP_URL%"
exit /b 0

:FAILED
echo ClassMind could not be started.
echo Run run_server.bat to view the detailed error.
pause
exit /b 1

