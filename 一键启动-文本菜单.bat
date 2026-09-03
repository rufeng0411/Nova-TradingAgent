@echo off

setlocal EnableExtensions

cd /d "%~dp0"

chcp 65001 >nul



if not exist "%~dp0scripts\dev-launcher.ps1" (

    echo [ERROR] Missing scripts\dev-launcher.ps1. Run from repo root.

    pause

    exit /b 1

)



title TradingAgents Dev CLI

echo.



set "PSX=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if not exist "%PSX%" set "PSX=powershell.exe"



"%PSX%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev-launcher.ps1"

set "EXITCODE=%ERRORLEVEL%"



if not "%EXITCODE%"=="0" (

    echo.

    echo [ERROR] Launcher exited with code: %EXITCODE%

    pause

)

exit /b %EXITCODE%

