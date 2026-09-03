param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $Root

Write-Host "=== Sprint 3 verify ===" -ForegroundColor Cyan
& uv run pytest tests/upgrade/test_sprint3_memory.py -q
Write-Host "verify_sprint3: PASS" -ForegroundColor Green
