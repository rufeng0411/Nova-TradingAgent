@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

set "EL=%~dp0scripts\dev-launcher-electron"
if not exist "%EL%\package.json" (
  echo [ERROR] Missing scripts\dev-launcher-electron. Run from repo root.
  pause
  exit /b 1
)

title Nova-TradingAgent Dev Launcher
echo.

if not exist "%EL%\node_modules\electron\package.json" (
  echo [INFO] First run: installing Electron launcher dependencies...
  pushd "%EL%"
  call npm install --no-audit --fund=false
  if errorlevel 1 (
    echo [ERROR] npm install failed in dev-launcher-electron
    popd
    pause
    exit /b 1
  )
  popd
)

pushd "%EL%"
call npm start
set "EXITCODE=%ERRORLEVEL%"
popd

if not "%EXITCODE%"=="0" (
  echo.
  echo [ERROR] Launcher exited with code: %EXITCODE%
  pause
)
exit /b %EXITCODE%
