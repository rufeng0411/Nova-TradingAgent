param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $Root

Write-Host "=== Sprint 2 verify ===" -ForegroundColor Cyan
& uv run pytest tests/upgrade/test_sprint2_schemas.py -q
Write-Host "verify_sprint2: PASS" -ForegroundColor Green
