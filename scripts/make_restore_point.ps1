# Create a full restore point snapshot for TradingAgents 0.2.5 upgrade.
# Usage: powershell -File scripts/make_restore_point.ps1 [-SkipDbDump]

param(
    [switch]$SkipDbDump
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$restoreDir = Join-Path $Root "data/db_backups/restore_$ts"
New-Item -ItemType Directory -Force -Path $restoreDir | Out-Null

Write-Host "=== Restore point: $restoreDir ===" -ForegroundColor Cyan

# --- Code zip (exclude heavy dirs) ---
$zipPath = Join-Path $restoreDir "code_snapshot.zip"
$excludeDirs = @(
    "node_modules", ".venv", "data/db_archives", "data/db_backups",
    "frontend/test-results", "logs", "__pycache__", ".git", "vendor"
)
$tempList = Join-Path $env:TEMP "restore_include_$ts.txt"
Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $rel = $_.FullName.Substring($Root.Length + 1)
        $skip = $false
        foreach ($ex in $excludeDirs) {
            if ($rel -like "$ex*" -or $rel -like "*\$ex\*") { $skip = $true; break }
        }
        -not $skip
    } |
    Select-Object -ExpandProperty FullName |
    Set-Content -Path $tempList -Encoding UTF8

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Get-Content $tempList) -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item $tempList -Force -ErrorAction SilentlyContinue
Write-Host "Created $zipPath"

# --- MySQL dump (if configured) ---
if (-not $SkipDbDump) {
    $envFile = Join-Path $Root ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*([^#=]+)=(.*)$') {
                $name = $matches[1].Trim()
                $val = $matches[2].Trim().Trim('"').Trim("'")
                [Environment]::SetEnvironmentVariable($name, $val, "Process")
            }
        }
    }
    $dbHost = $env:TA_MYSQL_HOST
    $dbPort = if ($env:TA_MYSQL_PORT) { $env:TA_MYSQL_PORT } else { "3306" }
    $dbUser = $env:TA_MYSQL_USER
    $dbPass = $env:TA_MYSQL_PASSWORD
    $dbName = if ($env:TA_MYSQL_DATABASE) { $env:TA_MYSQL_DATABASE } else { "tradingagents" }

    if ($dbHost -and $dbUser -and (Get-Command mysqldump -ErrorAction SilentlyContinue)) {
        $sqlPath = Join-Path $restoreDir "tradingagents_$ts.sql"
        $args = @(
            "--single-transaction", "--routines", "--triggers", "--events", "--hex-blob",
            "-h", $dbHost, "-P", $dbPort, "-u", $dbUser, $dbName
        )
        if ($dbPass) { $env:MYSQL_PWD = $dbPass }
        & mysqldump @args | Set-Content -Path $sqlPath -Encoding UTF8
        Write-Host "Created MySQL dump: $sqlPath"
    } else {
        Write-Host "Skipped MySQL dump (mysqldump or TA_MYSQL_* not available)" -ForegroundColor Yellow
    }

    # --- LangGraph checkpoint ---
    $checkpointer = if ($env:LANGGRAPH_CHECKPOINTER) { $env:LANGGRAPH_CHECKPOINTER } else { "sqlite" }
    $checkpointer = $checkpointer.ToLower()
    if ($checkpointer -eq "postgres" -and (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
        $pgUrl = if ($env:LANGGRAPH_CHECKPOINT_POSTGRES_URL) { $env:LANGGRAPH_CHECKPOINT_POSTGRES_URL } else { $env:DATABASE_URL }
        if ($pgUrl) {
            $dumpPath = Join-Path $restoreDir "langgraph_$ts.dump"
            & pg_dump -Fc $pgUrl -f $dumpPath 2>$null
            if (Test-Path $dumpPath) { Write-Host "Created PG checkpoint dump: $dumpPath" }
        }
    } else {
        $sqliteCp = $env:LANGGRAPH_CHECKPOINT_SQLITE
        if (-not $sqliteCp) {
            $sqliteCp = Join-Path $Root "tradingagents/data/langgraph_checkpoints.sqlite"
        }
        if (Test-Path $sqliteCp) {
            Copy-Item $sqliteCp (Join-Path $restoreDir "langgraph_checkpoints.sqlite") -Force
            Write-Host "Copied SQLite checkpoint"
        }
    }
}

# --- User home memory ---
$homeTa = Join-Path $env:USERPROFILE ".tradingagents"
if (Test-Path $homeTa) {
    $destHome = Join-Path $restoreDir "tradingagents_home"
    Copy-Item $homeTa $destHome -Recurse -Force
    Write-Host "Copied $homeTa -> $destHome"
}

# --- Manifest ---
$manifest = @{
    created_at = $ts
    git_commit = (git -C $Root rev-parse HEAD 2>$null)
    git_branch = (git -C $Root branch --show-current 2>$null)
    restore_dir = $restoreDir
} | ConvertTo-Json
Set-Content -Path (Join-Path $restoreDir "manifest.json") -Value $manifest -Encoding UTF8

Write-Host "=== Restore point complete: $restoreDir ===" -ForegroundColor Green
Write-Host $restoreDir
