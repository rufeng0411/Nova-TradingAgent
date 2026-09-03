@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === OSS release zip (frontend build + zip) ===
where python >nul 2>&1 && goto :py
where py >nul 2>&1 && goto :pylauncher
echo [ERR] Need Python on PATH. Install Python 3 or add it to PATH.
exit /b 1
:pylauncher
py -3 scripts\deploy\make_release_archive.py
goto :end
:py
python scripts\deploy\make_release_archive.py
:end
if errorlevel 1 exit /b %errorlevel%
echo.
echo Done. Upload releases\tradingagents-a-release-*.zip to OSS.
exit /b 0
