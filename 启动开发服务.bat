@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

title Nova-TradingAgent - Dev
echo.
echo [Nova-TradingAgent] Starting API (8001) + Frontend (5173)...
echo Open: http://localhost:5173/
echo Press Ctrl+C to stop.
echo.

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found. Install Node.js first.
  pause
  exit /b 1
)

call npm run dev
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo [ERROR] Dev server exited with code: %EXITCODE%
  pause
)
exit /b %EXITCODE%
