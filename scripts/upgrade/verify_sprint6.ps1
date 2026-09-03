param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $Root

Write-Host "=== Sprint 6 full verify ===" -ForegroundColor Cyan
& powershell -File (Join-Path $Root "scripts/upgrade/verify_sprint1.ps1")
& powershell -File (Join-Path $Root "scripts/upgrade/verify_sprint2.ps1")
& powershell -File (Join-Path $Root "scripts/upgrade/verify_sprint3.ps1")
& powershell -File (Join-Path $Root "scripts/upgrade/verify_sprint4.ps1")
& uv run pytest tests/upgrade/ -q
Write-Host "verify_sprint6: PASS" -ForegroundColor Green
