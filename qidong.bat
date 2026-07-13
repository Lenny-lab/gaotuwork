@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if /I "%~1"=="backend" goto RUN_BACKEND
if /I "%~1"=="check" goto CHECK_ONLY

title ClassMind One-Click Launcher
set "APP_URL=http://127.0.0.1:8000"

call :FIND_PYTHON
if errorlevel 1 goto NO_PYTHON

echo [1/3] Checking Python dependencies...
"%PYTHON%" -c "import flask, ortools, requests, cryptography" >nul 2>nul
if not errorlevel 1 goto DEPENDENCIES_READY

echo Required packages are missing. Installing requirements.txt...
"%PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto INSTALL_FAILED

:DEPENDENCIES_READY
echo [2/3] Checking the ClassMind backend...
powershell.exe -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%/healthz' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1"
if not errorlevel 1 goto OPEN_FRONTEND

echo Starting the ClassMind backend in a new window...
start "ClassMind Backend" "%ComSpec%" /k call "%~f0" backend

set "READY=0"
for /L %%G in (1,1,60) do call :WAIT_ONCE
if "%READY%"=="1" goto OPEN_FRONTEND

echo.
echo ERROR: The backend did not become ready within 60 seconds.
echo Check the "ClassMind Backend" window for details.
pause
exit /b 1

:WAIT_ONCE
if "%READY%"=="1" exit /b 0
powershell.exe -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%/healthz' -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1"
if not errorlevel 1 set "READY=1"& exit /b 0
timeout /t 1 /nobreak >nul
exit /b 0

:OPEN_FRONTEND
echo [3/3] ClassMind is ready: %APP_URL%
echo Opening the frontend in your default browser...
start "" "%APP_URL%"
exit /b 0

:RUN_BACKEND
title ClassMind Backend - Keep This Window Open
call :FIND_PYTHON
if errorlevel 1 goto NO_PYTHON
set "PORT=8000"
set "PYTHONPATH=%~dp0"
set "DEMO_LOGIN_ENABLED=1"
set "SESSION_COOKIE_SECURE=0"
if not defined FLASK_SECRET_KEY set "FLASK_SECRET_KEY=classmind-local-development"

echo ========================================
echo ClassMind frontend and backend
echo URL: http://127.0.0.1:8000
echo Keep this window open while using ClassMind.
echo Close this window to stop the local system.
echo ========================================
echo.
"%PYTHON%" "%~dp0app.py"
echo.
echo ClassMind has stopped.
pause
exit /b 0

:CHECK_ONLY
call :FIND_PYTHON
if errorlevel 1 goto NO_PYTHON
"%PYTHON%" -c "import flask, ortools, requests, cryptography; from app import app; response = app.test_client().get('/healthz'); assert response.status_code == 200"
if errorlevel 1 exit /b 1
echo qidong.bat check passed.
exit /b 0

:FIND_PYTHON
set "PYTHON=C:\Users\22314\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PYTHON%" exit /b 0
where py.exe >nul 2>nul
if not errorlevel 1 set "PYTHON=py.exe"& exit /b 0
where python.exe >nul 2>nul
if not errorlevel 1 set "PYTHON=python.exe"& exit /b 0
exit /b 1

:NO_PYTHON
echo.
echo ERROR: Python 3 was not found.
echo Install Python 3 and run qidong.bat again.
pause
exit /b 1

:INSTALL_FAILED
echo.
echo ERROR: Failed to install Python dependencies.
echo Check your network connection, then run qidong.bat again.
pause
exit /b 1
