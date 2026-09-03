param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $Root

Write-Host "=== Sprint 4 verify ===" -ForegroundColor Cyan
& uv run python -c "from api.routers.jobs_checkpoint import router; print('checkpoint routes', len(router.routes))"
Write-Host "verify_sprint4: PASS" -ForegroundColor Green
