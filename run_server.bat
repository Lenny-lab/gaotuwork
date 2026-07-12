@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ClassMind Server - Keep This Window Open

set "PYTHON=C:\Users\22314\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON%" set "PYTHON=python.exe"

echo ========================================
echo ClassMind server is running on port 8766
echo Keep this window open while using the app.
echo Close this window to stop the app.
echo ========================================
echo.

"%PYTHON%" -m classmind.api --host 127.0.0.1 --port 8766
echo.
echo ClassMind server stopped.
pause

