# Verify restore point integrity (minimal smoke).
# Usage: powershell -File scripts/verify_restore_point.ps1 [-RestoreDir path]

param(
    [string]$RestoreDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $RestoreDir) {
    $backups = Get-ChildItem (Join-Path $Root "data/db_backups") -Directory -Filter "restore_*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending
    if (-not $backups) {
        Write-Host "No restore_* directory found under data/db_backups/" -ForegroundColor Yellow
        exit 0
    }
    $RestoreDir = $backups[0].FullName
}

Write-Host "Verifying restore point: $RestoreDir" -ForegroundColor Cyan

$zip = Join-Path $RestoreDir "code_snapshot.zip"
if (-not (Test-Path $zip)) {
    Write-Error "Missing code_snapshot.zip"
}
$zipInfo = Get-Item $zip
if ($zipInfo.Length -lt 1000) {
    Write-Error "code_snapshot.zip too small ($($zipInfo.Length) bytes)"
}
Write-Host "OK code_snapshot.zip ($([math]::Round($zipInfo.Length/1MB, 2)) MB)"

$manifest = Join-Path $RestoreDir "manifest.json"
if (Test-Path $manifest) {
    Write-Host "OK manifest.json"
    Get-Content $manifest
}

# Import smoke (current tree, not extracted zip — zip integrity only above)
Write-Host "Running import smoke..."
& uv run python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('import ok')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "verify_restore_point: PASS" -ForegroundColor Green
