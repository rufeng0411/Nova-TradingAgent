param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $Root

Write-Host "=== Sprint 1 verify ===" -ForegroundColor Cyan
& uv run python -c "from tradingagents import __version__; from tradingagents.llm_clients.model_catalog import build_catalog_response; from tradingagents.llm_clients.factory import create_llm_client; print(__version__, len(build_catalog_response()['providers']))"
& uv run pytest tests/upgrade/test_sprint1_config.py tests/test_safe_ticker_component.py -q
& powershell -File (Join-Path $Root "scripts/verify_restore_point.ps1")
Write-Host "verify_sprint1: PASS" -ForegroundColor Green
