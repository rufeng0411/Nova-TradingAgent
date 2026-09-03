#requires -Version 5.1
# 保存本文件请使用「UTF-8 带 BOM」，否则 Windows PowerShell 5.x 可能乱码导致脚本无法解析。
<#
  TradingAgents 本地开发启动器（Windows）
  - 依赖检测：Node / npm / uv
  - 一键启动 / 重启 / 停止（释放 8000、5173）
  - 合并日志 logs/dev-combined.log（新开 PowerShell 窗口内 Tee）
  - 关键字异常扫描（ERROR / Exception / ECONNREFUSED 等）
  - 可选：监视 api、frontend/src 文件写入并写入 logs/file-watch.log
  用法：powershell -ExecutionPolicy Bypass -File scripts\dev-launcher.ps1
#>

$ErrorActionPreference = 'Continue'

try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [Console]::OutputEncoding
} catch {}

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$LogDir = Join-Path $Root 'logs'
$DevLog = Join-Path $LogDir 'dev-combined.log'
$WatchLog = Join-Path $LogDir 'file-watch.log'
$script:FsWatchers = New-Object System.Collections.ArrayList

function Ensure-LogDir {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
}

function Test-DevDependencies {
    Write-Host "`n[依赖检测]" -ForegroundColor Cyan
    $ok = $true
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Host "  [×] 未找到 node（请安装 Node.js 18+）" -ForegroundColor Red
        $ok = $false
    } else {
        Write-Host ("  [√] Node: " + (& node --version 2>$null)) -ForegroundColor Green
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host "  [×] 未找到 npm" -ForegroundColor Red
        $ok = $false
    } else {
        Write-Host ("  [√] npm: " + (& npm --version 2>$null)) -ForegroundColor Green
    }
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host ("  [√] uv: " + (& uv --version 2>$null)) -ForegroundColor Green
    } else {
        Write-Host "  [!] 未找到 uv（推荐安装：https://github.com/astral-sh/uv；或将 uv 加入 PATH）" -ForegroundColor Yellow
    }
    if (-not (Test-Path (Join-Path $Root 'package.json'))) {
        Write-Host "  [×] 未找到项目根 package.json，当前 Root=$Root" -ForegroundColor Red
        $ok = $false
    }
    if (-not (Test-Path (Join-Path $Root 'frontend\package.json'))) {
        Write-Host "  [!] 未找到 frontend\package.json" -ForegroundColor Yellow
    }
    return $ok
}

function Get-PidsOnPort([int]$Port) {
    $list = New-Object System.Collections.ArrayList
    try {
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                $oid = [int]$_.OwningProcess
                if ($oid -gt 0 -and $list -notcontains $oid) {
                    [void]$list.Add($oid)
                }
            }
    } catch {}

    if ($list.Count -eq 0) {
        try {
            & netstat.exe -ano 2>$null | ForEach-Object {
                $line = $_
                if ($line -like "*:${Port}*" -and $line -match "LISTENING\s+(\d+)\s*$") {
                    $id = [int]$Matches[1]
                    if ($id -gt 4 -and $list -notcontains $id) {
                        [void]$list.Add($id)
                    }
                }
            }
        } catch {}
    }
    if ($list.Count -eq 0) { return @() }
    return , @($list.ToArray())
}

function Stop-AllDevServices {
    Write-Host "`n[停止] 正在释放端口 8000、5173–5180 …" -ForegroundColor Yellow
    foreach ($port in @(8000) + @(5173..5180)) {
        foreach ($procId in (Get-PidsOnPort $port)) {
            if ($procId -eq $PID) {
                Write-Host "  跳过当前脚本进程 PID $procId" -ForegroundColor DarkGray
                continue
            }
            if (-not (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
                continue
            }
            try {
                $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
                $name = if ($p) { $p.ProcessName } else { '?' }
                Stop-Process -Id $procId -Force -ErrorAction Stop
                Write-Host "  已结束 PID $procId ($name) 端口 $port" -ForegroundColor Gray
            } catch {
                Write-Host "  无法结束 PID $procId : $_（若需强制结束可尝试以管理员运行）" -ForegroundColor DarkYellow
            }
        }
    }
    Start-Sleep -Milliseconds 800
}

function Start-AllDevServices {
    Ensure-LogDir
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $header = "=== $ts 启动 npm run dev（根目录）===`n"
    Set-Content -Path $DevLog -Value $header -Encoding UTF8

    $cmd = "Set-Location `"$Root`"; npm run dev *>&1 | Tee-Object -FilePath `"$DevLog`" -Append"
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-NoProfile', '-Command', $cmd) -WorkingDirectory $Root

    Write-Host "`n[启动] 已打开新 PowerShell 窗口运行 npm run dev，日志同时写入:" -ForegroundColor Green
    Write-Host "      $DevLog" -ForegroundColor Gray
    Write-Host "  前端默认 http://localhost:5173 ，API http://127.0.0.1:8000" -ForegroundColor Gray
}

function Restart-AllDevServices {
    Stop-AllDevServices
    Start-Sleep -Milliseconds 400
    Start-AllDevServices
}

function Show-DevLogTail([int]$Lines = 45) {
    Ensure-LogDir
    if (-not (Test-Path $DevLog)) {
        Write-Host "`n尚无日志文件，请先 [启动全部]。" -ForegroundColor Yellow
        return
    }
    Write-Host "`n----- dev-combined.log (末 $Lines 行) -----" -ForegroundColor Cyan
    Get-Content -Path $DevLog -Tail $Lines -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Test-LogAnomalies {
    Ensure-LogDir
    if (-not (Test-Path $DevLog)) { return }
    $tail = Get-Content -Path $DevLog -Tail 120 -Encoding UTF8 -ErrorAction SilentlyContinue
    if (-not $tail) { return }
    $pattern = 'ERROR|Error:|Exception|Traceback|ECONNREFUSED|WinError|FATAL|Unhandled|npm ERR'
    $hits = $tail | Select-String -Pattern $pattern -CaseSensitive:$false
    if ($hits) {
        Write-Host "`n[异常关键字] 在最近日志中发现以下行（请核对）：" -ForegroundColor Red
        $hits | Select-Object -First 25 | ForEach-Object { Write-Host $_.Line -ForegroundColor Yellow }
    } else {
        Write-Host "`n[异常关键字] 近期日志未匹配常见错误模式。" -ForegroundColor DarkGreen
    }
}

function Stop-FileWatchers {
    Get-EventSubscriber -ErrorAction SilentlyContinue |
        Where-Object { $_.SourceIdentifier -like 'ta-dev-watch-*' } |
        ForEach-Object {
            try { Unregister-Event -SubscriptionId $_.SubscriptionId -ErrorAction SilentlyContinue } catch {}
        }
    foreach ($w in @($script:FsWatchers)) {
        try {
            $w.EnableRaisingEvents = $false
            $w.Dispose()
        } catch {}
    }
    [void]$script:FsWatchers.Clear()
}

function Start-FileWatchers {
    Stop-FileWatchers
    Ensure-LogDir
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $WatchLog -Value "`n=== $stamp 启用源码变更监视（api + frontend\src）===`n" -Encoding UTF8

    $dirs = @(
        (Join-Path $Root 'api'),
        (Join-Path $Root 'frontend\src')
    )
    $idx = 0
    foreach ($d in $dirs) {
        if (-not (Test-Path $d)) {
            Write-Host "  跳过不存在的目录: $d" -ForegroundColor DarkYellow
            continue
        }
        $w = New-Object System.IO.FileSystemWatcher
        $w.Path = $d
        $w.Filter = '*.*'
        $w.IncludeSubdirectories = $true
        $w.NotifyFilter = [System.IO.NotifyFilters]::LastWrite -bor [System.IO.NotifyFilters]::FileName
        $idCh = "ta-dev-watch-$idx-changed"
        $idCr = "ta-dev-watch-$idx-created"
        $idx++
        Register-ObjectEvent -InputObject $w -EventName Changed -SourceIdentifier $idCh -Action {
            $line = '{0}  CHANGED  {1}' -f (Get-Date -Format 'HH:mm:ss'), $Event.SourceEventArgs.FullPath
            Add-Content -Path $using:WatchLog -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
        } | Out-Null
        Register-ObjectEvent -InputObject $w -EventName Created -SourceIdentifier $idCr -Action {
            $line = '{0}  CREATED  {1}' -f (Get-Date -Format 'HH:mm:ss'), $Event.SourceEventArgs.FullPath
            Add-Content -Path $using:WatchLog -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
        } | Out-Null
        $w.EnableRaisingEvents = $true
        [void]$script:FsWatchers.Add($w)
    }
    Write-Host "`n[监视] 已注册文件系统监视。变更写入: $WatchLog" -ForegroundColor Green
    Write-Host "      说明：修改代码后建议 [重启全部] 使进程加载最新构建。" -ForegroundColor Gray
}

function Show-WatchLogTail([int]$Lines = 20) {
    if (-not (Test-Path $WatchLog)) {
        Write-Host "`n尚无变更日志，请先执行菜单 [启用源码变更监视]。" -ForegroundColor Yellow
        return
    }
    Write-Host "`n----- file-watch.log (末 $Lines 行) -----" -ForegroundColor Cyan
    Get-Content -Path $WatchLog -Tail $Lines -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Show-MainMenu {
    Clear-Host
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " TradingAgents 开发启动器" -ForegroundColor White
    Write-Host " 项目: $Root" -ForegroundColor DarkGray
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " 1) 检测依赖 (Node/npm/uv)" -ForegroundColor White
    Write-Host " 2) 启动全部 (npm run dev，新窗口 + logs\dev-combined.log)" -ForegroundColor White
    Write-Host " 3) 重启全部 (停端口 -> 再启动)" -ForegroundColor White
    Write-Host " 4) 停止全部 (释放 8000 / 5173)" -ForegroundColor White
    Write-Host " 5) 查看合并日志 (尾部)" -ForegroundColor White
    Write-Host " 6) 扫描日志异常关键字" -ForegroundColor White
    Write-Host ' 7) 启用源码变更监视 (api + frontend/src)' -ForegroundColor White
    Write-Host " 8) 查看源码变更记录" -ForegroundColor White
    Write-Host " 9) 关闭源码监视" -ForegroundColor White
    Write-Host " 0) 退出" -ForegroundColor White
    Write-Host "========================================`n" -ForegroundColor Cyan
}

# --- 主循环 ---
# 说明：启动菜单时不再自动杀端口，避免误杀其它进程；请用菜单「重启全部」或「停止全部」主动释放。
while ($true) {
    Show-MainMenu
    $choice = Read-Host '请选择'
    switch ($choice) {
        '1' { [void](Test-DevDependencies); Pause }
        '2' {
            if (-not (Test-DevDependencies)) { Pause; continue }
            Stop-AllDevServices
            Start-AllDevServices
            Pause
        }
        '3' {
            if (-not (Test-DevDependencies)) { Pause; continue }
            Restart-AllDevServices
            Pause
        }
        '4' { Stop-AllDevServices; Pause }
        '5' { Show-DevLogTail 50; Pause }
        '6' { Test-LogAnomalies; Pause }
        '7' { Start-FileWatchers; Pause }
        '8' { Show-WatchLogTail 25; Pause }
        '9' { Stop-FileWatchers; Write-Host "`n已关闭监视（本会话内）。" -ForegroundColor Gray; Pause }
        '0' {
            Stop-FileWatchers
            Write-Host "`n再见。" -ForegroundColor Green
            exit 0
        }
        Default { Write-Host "`n无效选项。" -ForegroundColor Red; Start-Sleep 1 }
    }
}
