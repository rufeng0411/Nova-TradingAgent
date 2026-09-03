<#
.SYNOPSIS
    One-command Playwright full-stack test orchestrator for TradingAgents 0.2.5 upgrade acceptance.
.DESCRIPTION
    Runs preflight, then launches Playwright with the appropriate project/profile/grep.
    Results are accumulated in frontend/test-results/ and a markdown summary is written.
.PARAMETER Profile
    "baseline" — TA_UPGRADE_*=0 (default)
    "upgrade"  — TA_UPGRADE_*=1
.PARAMETER IncludeHeavy
    If set, also run @heavy tests (slow, real LLM + Tushare calls).
.PARAMETER SkipPreflight
    Skip preflight checks (useful when API is already verified running).
.PARAMETER Grep
    Additional grep filter passed to Playwright (e.g. "fast analysis").
.EXAMPLE
    .\scripts\e2e\run-fullstack-playwright.ps1 -Profile baseline
    .\scripts\e2e\run-fullstack-playwright.ps1 -Profile upgrade -IncludeHeavy
    .\scripts\e2e\run-fullstack-playwright.ps1 -Profile baseline -IncludeHeavy -SkipPreflight
#>
param(
    [ValidateSet("baseline","upgrade")]
    [string]$Profile = "baseline",
    [switch]$IncludeHeavy,
    [switch]$SkipPreflight,
    [string]$Grep = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# ── Apply profile environment ──────────────────────────────────────────────
if ($Profile -eq "upgrade") {
    $env:TA_UPGRADE_LLM_CATALOG       = "1"
    $env:TA_UPGRADE_STRUCTURED_OUTPUT  = "1"
    $env:TA_UPGRADE_PERSISTENT_MEMORY  = "1"
    $env:TA_UPGRADE_CHECKPOINT_UI      = "1"
    Write-Host "Profile=upgrade: all TA_UPGRADE_*=1" -ForegroundColor Yellow
} else {
    $env:TA_UPGRADE_LLM_CATALOG       = "0"
    $env:TA_UPGRADE_STRUCTURED_OUTPUT  = "0"
    $env:TA_UPGRADE_PERSISTENT_MEMORY  = "0"
    $env:TA_UPGRADE_CHECKPOINT_UI      = "0"
    Write-Host "Profile=baseline: all TA_UPGRADE_*=0" -ForegroundColor Cyan
}

# ── Preflight ──────────────────────────────────────────────────────────────
if (-not $SkipPreflight) {
    & powershell -File (Join-Path $Root "scripts/e2e/preflight.ps1") -Profile $Profile
    if ($LASTEXITCODE -ne 0) { Write-Error "Preflight failed — aborting tests" }
}

# ── Build grep expression ──────────────────────────────────────────────────
$grepParts = @()
if ($Profile -eq "upgrade") { $grepParts += "@upgrade" }
if ($IncludeHeavy)          { $grepParts += "@heavy" }
if ($Grep)                  { $grepParts += $Grep }

$pw_args = @()
# Always run mock (Tier A1) + live (Tier A2/A3/A4) suites
# Heavy only when -IncludeHeavy is set

if ($grepParts.Count -gt 0) {
    $grepExpr = $grepParts -join "|"
    $pw_args += "--grep", $grepExpr
}

# Use E2E_START_API=1 so playwright.config.ts spins up the API
$env:E2E_START_API = "1"

$startTs = Get-Date
Write-Host "=== Starting Playwright (profile=$Profile, heavy=$IncludeHeavy) ===" -ForegroundColor Cyan

Push-Location (Join-Path $Root "frontend")
npm run test:e2e -- @pw_args 2>&1
$exitCode = $LASTEXITCODE
Pop-Location

$elapsed = [int]((Get-Date) - $startTs).TotalSeconds

# ── Generate markdown summary ──────────────────────────────────────────────
$outDir = Join-Path $Root "frontend/test-results"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$envFile = Join-Path $outDir "e2e-env.json"
$envData  = if (Test-Path $envFile) { Get-Content $envFile | ConvertFrom-Json } else { @{} }

$status = if ($exitCode -eq 0) { "PASS" } else { "FAIL (exit=$exitCode)" }

$md = @"
# E2E Test Run — Profile: $Profile

**Status**: $status
**Date**: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
**Elapsed**: ${elapsed}s
**Heavy tests**: $IncludeHeavy

## Environment Flags

| Flag | Value |
|------|-------|
| TA_UPGRADE_LLM_CATALOG | $($envData.TA_UPGRADE_LLM_CATALOG) |
| TA_UPGRADE_STRUCTURED_OUTPUT | $($envData.TA_UPGRADE_STRUCTURED_OUTPUT) |
| TA_UPGRADE_PERSISTENT_MEMORY | $($envData.TA_UPGRADE_PERSISTENT_MEMORY) |
| TA_UPGRADE_CHECKPOINT_UI | $($envData.TA_UPGRADE_CHECKPOINT_UI) |
| TA_LLM_PROVIDER | $($envData.TA_LLM_PROVIDER) |
| TUSHARE_TOKEN | $($envData.TUSHARE_TOKEN_present) |

## Test Tiers

- **Tier A (Mock)**: existing 6 e2e files (always run)
- **Tier A2/A3 (Live)**: live-api-smoke, live-auth-navigation
- **Tier B (Upgrade)**: upgrade-0.2.5-live (profile=upgrade only)
- **Tier C (Heavy)**: heavy-analysis-live (--IncludeHeavy)

## DoD Checklist

- [ ] baseline: Mock 6 suites green
- [ ] baseline: Live A2/A3/A4 green
- [ ] upgrade: Tier B all green
- [ ] heavy: C1 fast analysis — VERDICT visible, ≥8 data sources
- [ ] heavy: C2 full analysis — 7 analysts, Risk Judge not fallback
- [ ] heavy: C3 reports — provenance non-empty, derived_signals present
- [ ] heavy: C4 kline — price badge visible
- [ ] heavy: C5 LLM bridge regression — baseline fast analysis succeeds

Detailed HTML report: test-results/index.html (if --reporter html was used)
Screenshots: test-results/screenshots/$Profile/
"@

$summaryPath = Join-Path $outDir "summary-$Profile.md"
Set-Content -Path $summaryPath -Value $md -Encoding UTF8
Write-Host "Summary written: $summaryPath" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })

exit $exitCode
