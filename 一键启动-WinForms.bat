@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul
if not exist "%~dp0scripts\dev-launcher-gui.ps1" (
  echo [ERROR] Missing scripts\dev-launcher-gui.ps1
  pause
  exit /b 1
)
title TradingAgents Dev GUI (WinForms)
set "PSX=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PSX%" set "PSX=powershell.exe"
"%PSX%" -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0scripts\dev-launcher-gui.ps1"
exit /b %ERRORLEVEL%
