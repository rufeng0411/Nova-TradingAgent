<#
.SYNOPSIS
    E2E preflight: verify all services are ready before Playwright runs.
.DESCRIPTION
    1. TCP-probe MySQL
    2. GET /healthz -> status=ok
    3. GET /v1/system/version -> contains "0.2.5+ta-cn"
    4. GET /v1/features -> HTTP 200
    5. Run pytest tests/upgrade/ gate
    6. Write e2e-env.json snapshot
.PARAMETER Profile
    "baseline" (TA_UPGRADE_*=0) or "upgrade" (TA_UPGRADE_*=1)
#>
param(
    [string]$Profile = "baseline",
    [switch]$SkipPytest
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$apiPort = if ($env:TA_DEV_API_PORT) { $env:TA_DEV_API_PORT } else { "8001" }
$apiBase = "http://127.0.0.1:$apiPort"

Write-Host "=== E2E Preflight (profile=$Profile, api=$apiBase) ===" -ForegroundColor Cyan

# 1. MySQL TCP probe
$mysqlHost = if ($env:TA_MYSQL_HOST) { $env:TA_MYSQL_HOST } else { "127.0.0.1" }
$mysqlPort = if ($env:TA_MYSQL_PORT)  { [int]$env:TA_MYSQL_PORT } else { 3306 }
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect($mysqlHost, $mysqlPort)
    $tcp.Close()
    Write-Host "OK MySQL $mysqlHost:$mysqlPort reachable"
} catch {
    Write-Warning "MySQL $mysqlHost:$mysqlPort not reachable — DB tests will fail"
}

# 2. healthz
try {
    $h = Invoke-RestMethod -Uri "$apiBase/healthz" -TimeoutSec 10
    if ($h.status -ne "ok") { throw "healthz status != ok: $($h.status)" }
    Write-Host "OK healthz"
} catch {
    Write-Error "API not healthy at $apiBase — start the API first: npm run dev:api"
}

# 3. system/version
try {
    $ver = Invoke-RestMethod -Uri "$apiBase/v1/system/version" -TimeoutSec 10
    if ($ver.version -notmatch "0\.2\.5\+ta-cn") {
        Write-Warning "version '$($ver.version)' does not match 0.2.5+ta-cn — tradingagents/__init__.py may be stale"
    } else {
        Write-Host "OK version: $($ver.version)"
    }
} catch {
    Write-Warning "/v1/system/version not available: $_"
}

# 4. /v1/features
try {
    $feat = Invoke-RestMethod -Uri "$apiBase/v1/features" -TimeoutSec 10
    Write-Host "OK /v1/features"
} catch {
    Write-Error "/v1/features unreachable: $_"
}

# 5. pytest gate
if (-not $SkipPytest) {
    Write-Host "Running pytest upgrade gate..."
    & uv run pytest tests/upgrade/ -q --tb=line 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Error "pytest upgrade tests FAILED" }
    Write-Host "OK pytest tests/upgrade/"
}

# 6. Write env snapshot
$outDir = Join-Path $Root "frontend/test-results"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$snapshot = @{
    profile             = $Profile
    api_base            = $apiBase
    created_at          = (Get-Date -Format "o")
    TA_UPGRADE_LLM_CATALOG       = ($env:TA_UPGRADE_LLM_CATALOG ?? "0")
    TA_UPGRADE_STRUCTURED_OUTPUT = ($env:TA_UPGRADE_STRUCTURED_OUTPUT ?? "0")
    TA_UPGRADE_PERSISTENT_MEMORY = ($env:TA_UPGRADE_PERSISTENT_MEMORY ?? "0")
    TA_UPGRADE_CHECKPOINT_UI     = ($env:TA_UPGRADE_CHECKPOINT_UI ?? "0")
    TA_LLM_PROVIDER              = ($env:TA_LLM_PROVIDER ?? "unknown")
    TA_LLM_DEEP                  = ($env:TA_LLM_DEEP ?? "unknown")
    TUSHARE_TOKEN_present        = ([bool]($env:TUSHARE_TOKEN))
} | ConvertTo-Json

Set-Content -Path (Join-Path $outDir "e2e-env.json") -Value $snapshot -Encoding UTF8
Write-Host "Wrote frontend/test-results/e2e-env.json"
Write-Host "=== Preflight PASS ===" -ForegroundColor Green
