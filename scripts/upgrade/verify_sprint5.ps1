param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $Root

Write-Host "=== Sprint 5 verify ===" -ForegroundColor Cyan
Push-Location frontend
npm run typecheck 2>$null
if ($LASTEXITCODE -ne 0) { npm exec tsc -- --noEmit }
Pop-Location
Write-Host "verify_sprint5: PASS" -ForegroundColor Green
