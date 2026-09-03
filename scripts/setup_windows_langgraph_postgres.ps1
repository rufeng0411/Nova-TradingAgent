<#
.SYNOPSIS
  一键初始化本机 PostgreSQL（Windows 便携/自定义目录），供 LangGraph checkpoint 使用。

.DESCRIPTION
  - 若数据目录不存在：initdb → 配置端口 → 启动 → 创建 ta_lgcp + langgraph_checkpoint
  - 若数据目录已存在：仅尝试启动，并用保存的 superuser 口令连接后确保用户/库存在
  - 将 LANGGRAPH_CHECKPOINTER / LANGGRAPH_POSTGRES_URI 写入项目根 .env
  - 超级用户与应用口令写入 <ProjectRoot>/data/.postgres_langgraph_bootstrap.env（已 gitignore）

  前置：已将 PostgreSQL 解压/安装到默认 D:\pgsql（含 bin\initdb.exe）。

.EXAMPLE
  pwsh -NoProfile -File scripts/setup_windows_langgraph_postgres.ps1
  pwsh -NoProfile -File scripts/setup_windows_langgraph_postgres.ps1 -Port 5433
#>
param(
  [string]$PostgresRoot = "D:\pgsql",
  [string]$DataDir = "",
  [ValidateRange(1, 65535)]
  [int]$Port = 5432,
  [string]$AppUser = "ta_lgcp",
  [string]$AppDb = "langgraph_checkpoint",
  [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

function New-AlphanumericPassword([int]$Len = 24) {
  $chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
  return -join ((1..$Len) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
}

function Set-DotEnvKey {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Value
  )
  $lines = @()
  if (Test-Path -LiteralPath $Path) {
    $lines = @(Get-Content -LiteralPath $Path)
  }
  $found = $false
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match "^\s*${Key}\s*=") {
      $lines[$i] = "${Key}=${Value}"
      $found = $true
    }
  }
  if (-not $found) {
    if ($lines.Count -gt 0 -and $lines[-1].Trim() -ne "") {
      $lines += ""
    }
    $lines += "${Key}=${Value}"
  }
  $utf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllLines($Path, $lines, $utf8)
}

function Set-PostgresqlConfPort {
  param([string]$ConfPath, [int]$Port)
  $lines = @(Get-Content -LiteralPath $ConfPath)
  $out = New-Object System.Collections.Generic.List[string]
  $set = $false
  foreach ($line in $lines) {
    if ($line -match '^\s*#\s*port\s*=\s*\d+\s*$' -or $line -match '^\s*port\s*=\s*\d+\s*$') {
      if (-not $set) {
        $out.Add("port = $Port")
        $set = $true
      }
    }
    else {
      $out.Add($line)
    }
  }
  if (-not $set) {
    $out.Add("port = $Port")
  }
  $utf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllLines($ConfPath, $out.ToArray(), $utf8)
}

if (-not $ProjectRoot) {
  $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if (-not $DataDir) {
  $DataDir = Join-Path $PostgresRoot "data"
}

$Bin = Join-Path $PostgresRoot "bin"
$InitDb = Join-Path $Bin "initdb.exe"
$PgCtl = Join-Path $Bin "pg_ctl.exe"
$Psql = Join-Path $Bin "psql.exe"
$PostgresExe = Join-Path $Bin "postgres.exe"

foreach ($p in @($InitDb, $PgCtl, $Psql, $PostgresExe)) {
  if (-not (Test-Path -LiteralPath $p)) {
    throw ("Missing PostgreSQL binary: " + $p + "`nCheck PostgresRoot=" + $PostgresRoot)
  }
}

$ver = & $PostgresExe --version 2>&1
Write-Host ('[info] ' + $ver)
Write-Host ('[info] DataDir=' + $DataDir + ' Port=' + $Port + ' ProjectRoot=' + $ProjectRoot)

$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
  $listenPid = $busy[0].OwningProcess
  $pn = (Get-Process -Id $listenPid -ErrorAction SilentlyContinue).ProcessName
  Write-Host ('[warn] port ' + $Port + ' in use (PID=' + $listenPid + ' ' + $pn + '). Use -Port if you need another port.')
}

$bootstrapRel = "data/.postgres_langgraph_bootstrap.env"
$bootstrapAbs = Join-Path $ProjectRoot $bootstrapRel.Replace("/", [IO.Path]::DirectorySeparatorChar)
$bootstrapDir = Split-Path $bootstrapAbs -Parent
if (-not (Test-Path -LiteralPath $bootstrapDir)) {
  New-Item -ItemType Directory -Path $bootstrapDir -Force | Out-Null
}

$superPass = ""
$appPass = ""

if (Test-Path -LiteralPath (Join-Path $DataDir "PG_VERSION")) {
  Write-Host '[info] Existing data directory, skip initdb.'
  if (-not (Test-Path -LiteralPath $bootstrapAbs)) {
    throw ("Existing data dir but missing " + $bootstrapRel + " (keep that file, or remove data dir and re-run).")
  }
  foreach ($line in Get-Content -LiteralPath $bootstrapAbs) {
    if ($line -match '^\s*POSTGRES_SUPERUSER_PASSWORD=(.+)$') { $superPass = $Matches[1].Trim() }
    if ($line -match '^\s*TA_LGCP_PASSWORD=(.+)$') { $appPass = $Matches[1].Trim() }
  }
  if ([string]::IsNullOrWhiteSpace($superPass) -or [string]::IsNullOrWhiteSpace($appPass)) {
    throw ($bootstrapRel + " must contain POSTGRES_SUPERUSER_PASSWORD and TA_LGCP_PASSWORD.")
  }
}
else {
  if (Test-Path -LiteralPath $DataDir) {
    throw ("Data path exists but is not a PostgreSQL cluster (missing PG_VERSION): " + $DataDir)
  }
  Write-Host '[info] Running initdb (first-time init)...'
  $superPass = New-AlphanumericPassword 26
  $appPass = New-AlphanumericPassword 26
  $pwFile = Join-Path $env:TEMP "pg_init_pw_$(Get-Random).txt"
  try {
    Set-Content -LiteralPath $pwFile -Value $superPass -Encoding ascii -NoNewline
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $initOut = & $InitDb -D $DataDir -U postgres --encoding=UTF8 --locale=C --pwfile=$pwFile 2>&1
    $initExit = $LASTEXITCODE
    $ErrorActionPreference = $oldEap
    $initOut | ForEach-Object { Write-Host $_ }
    if ($initExit -ne 0) {
      throw ('initdb failed with exit code ' + $initExit)
    }
  }
  finally {
    Remove-Item -LiteralPath $pwFile -Force -ErrorAction SilentlyContinue
  }

  $conf = Join-Path $DataDir "postgresql.conf"
  Set-PostgresqlConfPort -ConfPath $conf -Port $Port

  $boot = @(
    "# Generated by scripts/setup_windows_langgraph_postgres.ps1 - do not commit",
    "POSTGRES_SUPERUSER_PASSWORD=$superPass",
    "TA_LGCP_PASSWORD=$appPass",
    "PGHOST=127.0.0.1",
    "PGPORT=$Port"
  )
  $utf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllLines($bootstrapAbs, $boot, $utf8)
  Write-Host ('[ok] wrote ' + $bootstrapRel)
}

$logFile = Join-Path $DataDir "pg_ctl_setup.log"
Write-Host '[info] Starting PostgreSQL (pg_ctl)...'
$oldEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$st = & $PgCtl -D $DataDir status 2>&1
$statusExit = $LASTEXITCODE
$ErrorActionPreference = $oldEap
if ($statusExit -eq 0) {
  Write-Host ('[skip] already running: ' + $st)
}
else {
  $oldEap = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  $startOut = & $PgCtl -D $DataDir -l $logFile start -w -t 120 -o "-p $Port" 2>&1
  $startExit = $LASTEXITCODE
  $ErrorActionPreference = $oldEap
  $startOut | ForEach-Object { Write-Host $_ }
  if ($startExit -ne 0) {
    $st2 = & $PgCtl -D $DataDir status 2>&1
    if ($LASTEXITCODE -eq 0) {
      Write-Host ('[skip] start returned non-zero but server is up: ' + $st2)
    }
    else {
      throw ('pg_ctl start failed. Log: ' + $logFile + "`n" + $st2)
    }
  }
}

$env:PGPASSWORD = $superPass
$sqlCheckUser = "SELECT 1 FROM pg_roles WHERE rolname = '$AppUser';"
$oldEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$existsUser = & $Psql -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc $sqlCheckUser 2>&1
$psqlExit = $LASTEXITCODE
$ErrorActionPreference = $oldEap
if ($psqlExit -ne 0) { throw ('psql (superuser) failed: ' + $existsUser) }
if (-not ($existsUser -match "^\s*1\s*$")) {
  $sql = "CREATE ROLE $AppUser LOGIN PASSWORD '$($appPass -replace "'", "''")';"
  $oldEap = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  $crRoleOut = & $Psql -h 127.0.0.1 -p $Port -U postgres -d postgres -c $sql 2>&1
  $ErrorActionPreference = $oldEap
  $crRoleOut | ForEach-Object { Write-Host $_ }
}
else {
  Write-Host ('[skip] role exists: ' + $AppUser)
}

$sqlCheckDb = "SELECT 1 FROM pg_database WHERE datname = '$AppDb';"
$oldEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$existsDb = & $Psql -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc $sqlCheckDb 2>&1
$psqlDbExit = $LASTEXITCODE
$ErrorActionPreference = $oldEap
if ($psqlDbExit -ne 0) { throw ('psql (check db) failed: ' + $existsDb) }
if (-not ($existsDb -match "^\s*1\s*$")) {
  $sql = "CREATE DATABASE $AppDb OWNER $AppUser ENCODING 'UTF8';"
  $oldEap = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  $crDbOut = & $Psql -h 127.0.0.1 -p $Port -U postgres -d postgres -c $sql 2>&1
  $ErrorActionPreference = $oldEap
  $crDbOut | ForEach-Object { Write-Host $_ }
}
else {
  Write-Host ('[skip] database exists: ' + $AppDb)
}

$env:PGPASSWORD = $null

$uri = "postgresql+psycopg://${AppUser}:${appPass}@127.0.0.1:${Port}/${AppDb}"
$envPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
  throw ("Missing .env: " + $envPath)
}
Set-DotEnvKey -Path $envPath -Key "LANGGRAPH_CHECKPOINTER" -Value "postgres"
Set-DotEnvKey -Path $envPath -Key "LANGGRAPH_POSTGRES_URI" -Value $uri
Write-Host ('[ok] updated .env LANGGRAPH_* -> 127.0.0.1:' + $Port + '/' + $AppDb)

Write-Host ''
Write-Host '=== Done ==='
Write-Host ('1) Superuser + app passwords: ' + $bootstrapRel)
Write-Host '2) After reboot, if Postgres is down, start with:'
Write-Host ('   & "' + $PgCtl + '" -D "' + $DataDir + '" -l "' + $logFile + '" start -w -o "-p ' + $Port + '"')
Write-Host '3) Restart the API so LangGraph picks up Postgres.'
