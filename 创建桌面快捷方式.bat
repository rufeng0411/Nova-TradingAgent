@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

title Nova-TradingAgent - Create Desktop Shortcut
echo.
echo Creating desktop shortcut(s) for Nova-TradingAgent...
echo.

set "PSX=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%PSX%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_desktop_shortcut.ps1" -Mode both
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
  echo Done. Check your Desktop for:
  echo   - Nova-TradingAgent.lnk          ^(Electron 控制台，推荐^)
  echo   - Nova-TradingAgent ^(Dev^).lnk   ^(npm run dev 快速模式^)
) else (
  echo [ERROR] Failed to create shortcut. Exit code: %EXITCODE%
)
echo.
pause
exit /b %EXITCODE%
