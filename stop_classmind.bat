@echo off
setlocal EnableExtensions
echo Stopping ClassMind on port 8766...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8766" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>nul
echo ClassMind stopped.
timeout /t 2 /nobreak >nul

