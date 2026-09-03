#requires -Version 5.1
# UTF-8 BOM：便于 Windows PowerShell 5.x 正确解析中文。
<#
  TradingAgents 开发控制台（图形界面）
  powershell -STA -ExecutionPolicy Bypass -File scripts\dev-launcher-gui.ps1
#>

$ErrorActionPreference = 'Continue'

# WinForms 必须在 STA；否则按钮/定时器会卡住或点击无响应
if ([System.Threading.Thread]::CurrentThread.GetApartmentState() -ne [System.Threading.ApartmentState]::STA) {
    $launch = if ($PSCommandPath) { $PSCommandPath } else { $MyInvocation.MyCommand.Path }
    if (-not $launch) { throw 'Cannot resolve script path for STA relaunch.' }
    $wd = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $psx = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath $psx)) { $psx = 'powershell.exe' }
    Start-Process -FilePath $psx -ArgumentList @('-NoLogo', '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-File', $launch) -WorkingDirectory $wd | Out-Null
    exit 0
}

try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    Add-Type -AssemblyName System.Drawing -ErrorAction Stop
} catch {
    [System.Windows.Forms.MessageBox]::Show(
        "无法加载 WinForms。请使用完整 Windows PowerShell 并以 -STA 启动本脚本。`n$_",
        'TradingAgents 启动器',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

[System.Windows.Forms.Application]::EnableVisualStyles()
[System.Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$LogDir = Join-Path $Root 'logs'
$DevLog = Join-Path $LogDir 'dev-combined.log'

$script:DevProcess = $null
# 深色主题色板（扁平、偏 VS Code 系）
$script:Th = @{
    Bg       = [System.Drawing.Color]::FromArgb(18, 18, 22)
    BgPanel  = [System.Drawing.Color]::FromArgb(26, 27, 34)
    BgCard   = [System.Drawing.Color]::FromArgb(34, 36, 46)
    BgElev   = [System.Drawing.Color]::FromArgb(42, 44, 56)
    Btn2nd   = [System.Drawing.Color]::FromArgb(48, 50, 62)
    Border   = [System.Drawing.Color]::FromArgb(68, 72, 88)
    Txt      = [System.Drawing.Color]::FromArgb(236, 238, 245)
    TxtMuted = [System.Drawing.Color]::FromArgb(156, 160, 176)
    Accent   = [System.Drawing.Color]::FromArgb(0, 122, 255)
    AccentHi = [System.Drawing.Color]::FromArgb(64, 156, 255)
    Ok       = [System.Drawing.Color]::FromArgb(52, 199, 89)
    Warn     = [System.Drawing.Color]::FromArgb(255, 179, 64)
    Err      = [System.Drawing.Color]::FromArgb(255, 69, 58)
    LogLine  = [System.Drawing.Color]::FromArgb(210, 213, 224)
    LogErr   = [System.Drawing.Color]::FromArgb(255, 140, 148)
    Split    = [System.Drawing.Color]::FromArgb(52, 54, 64)
}

function Ensure-LogDir {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
}

function Append-LogLine([string]$Line, [System.Drawing.Color]$Color) {
    $rt = $script:RichLog
    if (-not $rt) { return }
    $action = {
        param($txt, $c)
        $rt.SelectionStart = $rt.TextLength
        $rt.SelectionLength = 0
        $rt.SelectionColor = $c
        $rt.AppendText($txt + [Environment]::NewLine)
        $rt.ScrollToCaret()
    }
    if ($rt.InvokeRequired) {
        [void]$rt.Invoke($action, @($Line, $Color))
    } else {
        & $action $Line $Color
    }
    Ensure-LogDir
    try {
        Add-Content -Path $DevLog -Value $Line -Encoding UTF8 -ErrorAction SilentlyContinue
    } catch {}
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
                if ($line -like "*:${Port}*" -and $line -match 'LISTENING\s+(\d+)\s*$') {
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
    Append-LogLine '[停止] 正在释放端口 8000、5173–5180 …' ($script:Th.Warn)
    foreach ($port in @(8000) + @(5173..5180)) {
        foreach ($procId in (Get-PidsOnPort $port)) {
            if (-not (Get-Process -Id $procId -ErrorAction SilentlyContinue)) { continue }
            try {
                $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
                $name = if ($p) { $p.ProcessName } else { '?' }
                Stop-Process -Id $procId -Force -ErrorAction Stop
                Append-LogLine ("  已结束 PID $procId ($name) 端口 $port") ($script:Th.TxtMuted)
            } catch {
                Append-LogLine ("  无法结束 PID $procId : $_") ($script:Th.Warn)
            }
        }
    }
    Start-Sleep -Milliseconds 600
}

function Test-HttpOk([string]$Url, [int]$TimeoutMs = 450) {
    try {
        $wr = [System.Net.WebRequest]::Create($Url)
        $wr.Method = 'GET'
        $wr.Timeout = $TimeoutMs
        $resp = $wr.GetResponse()
        try {
            $code = [int]$resp.StatusCode
            return ($code -ge 200 -and $code -lt 400)
        } finally {
            $resp.Close()
        }
    } catch {
        return $false
    }
}

function Test-WebDevHttpOk {
    foreach ($p in 5173..5180) {
        if (Test-HttpOk "http://127.0.0.1:$p/") {
            return $p
        }
    }
    return $null
}

function Update-ServiceRows {
    $lv = $script:ListStatus
    if (-not $lv) { return }

    $apiListen = (Get-PidsOnPort 8000).Count -gt 0
    $webReadyPort = Test-WebDevHttpOk
    $webOk = [bool]$webReadyPort
    $webListenPort = $null
    if ($webReadyPort) {
        $webListenPort = $webReadyPort
    } else {
        foreach ($p in 5173..5180) {
            if ((Get-PidsOnPort $p).Count -gt 0) {
                $webListenPort = $p
                break
            }
        }
    }
    $webListen = $null -ne $webListenPort
    # 仅端口在监听时才 HTTP 探活，避免 UI 线程长时间阻塞导致「点击无反应」
    $apiOk = $false
    if ($apiListen) { $apiOk = Test-HttpOk 'http://127.0.0.1:8000/healthz' }

    $rows = @(
        @{ Name = '后端 API'; Port = '8000'; Listen = $apiListen; Ready = $apiOk; Hint = 'GET /healthz' },
        @{
            Name   = '前端 Vite'
            Port   = if ($webListenPort) { "$webListenPort" } else { '5173–5180' }
            Listen = $webListen
            Ready  = $webOk
            Hint   = '开发服务器（端口可递增）'
        }
    )

    $lv.BeginUpdate()
    try {
        $lv.Items.Clear()
        foreach ($r in $rows) {
            $pidTxt = ''
            if ($r.Port -eq '8000') {
                $pids = Get-PidsOnPort 8000
                $pidTxt = if ($pids.Count) { ($pids -join ', ') } else { '-' }
            } else {
                $pids = if ($webListenPort) { Get-PidsOnPort $webListenPort } else { @() }
                $pidTxt = if ($pids.Count) { ($pids -join ', ') } else { '-' }
            }

            if ($r.Ready) {
                $state = '就绪'
                $img = 0
            } elseif ($r.Listen) {
                $state = '监听中'
                $img = 1
            } else {
                $state = '未启动'
                $img = 2
            }

            $item = New-Object System.Windows.Forms.ListViewItem($r.Name, $img)
            [void]$item.SubItems.Add($state)
            [void]$item.SubItems.Add($r.Port)
            [void]$item.SubItems.Add($pidTxt)
            [void]$item.SubItems.Add($r.Hint)
            [void]$lv.Items.Add($item)
        }
    } finally {
        $lv.EndUpdate()
    }

    $lbl = $script:SummaryLabel
    $th = $script:Th
    if ($lbl) {
        if ($apiOk -and $webOk) {
            $lbl.Text = '当前：前后端均已就绪，可正常使用。'
            $lbl.ForeColor = $th.Ok
        } elseif ($apiOk -or $webOk) {
            $lbl.Text = '当前：仅部分服务就绪；若页面提示无法连接后端，请等待或查看日志。'
            $lbl.ForeColor = $th.Warn
        } else {
            $lbl.Text = '当前：开发服务未就绪。请点击「智能一键」或启动 npm run dev。'
            $lbl.ForeColor = $th.Err
        }
    }

    if ($null -ne $script:ChartTargets -and $script:ChartTargets.Length -ge 2) {
        $vApi = if ($apiOk) { 0.94 } elseif ($apiListen) { 0.42 } else { 0.1 }
        $vWeb = if ($webOk) { 0.94 } elseif ($webListen) { 0.42 } else { 0.1 }
        $script:ChartTargets[0] = [double]$vApi
        $script:ChartTargets[1] = [double]$vWeb
    }
}

function Invoke-BlockingCli {
    param(
        [string]$Title,
        [string]$FileName,
        [string]$Arguments,
        [string]$WorkDir
    )
    Append-LogLine "----- $Title -----" ($script:Th.Accent)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FileName
    $psi.Arguments = $Arguments
    $psi.WorkingDirectory = $WorkDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    foreach ($line in ($stdout -split '\r?\n')) {
        if ($line.Length) { Append-LogLine $line ($script:Th.LogLine) }
    }
    foreach ($line in ($stderr -split '\r?\n')) {
        if ($line.Length) { Append-LogLine $line ($script:Th.LogErr) }
    }
    Append-LogLine "----- 结束 (exit $($p.ExitCode)) -----" ($script:Th.Accent)
    return $p.ExitCode
}

function Ensure-RootNpmDeps {
    $nm = Join-Path $Root 'node_modules'
    if (-not (Test-Path $nm)) {
        Append-LogLine '[依赖] 未检测到根目录 node_modules，正在执行 npm install …' ($script:Th.Accent)
        $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npm) {
            Append-LogLine '[错误] 未找到 npm.cmd' ($script:Th.Err)
            return $false
        }
        $code = Invoke-BlockingCli 'npm install（根目录）' $npm.Source 'install' $Root
        return ($code -eq 0)
    }
    return $true
}

function Start-NpmDevCapturing {
    Stop-NpmDevCapturing
    if (-not (Ensure-RootNpmDeps)) { return }

    Ensure-LogDir
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Set-Content -Path $DevLog -Value "=== $ts GUI 启动 npm run dev ===`n" -Encoding UTF8
    Append-LogLine "=== $ts 启动 npm run dev ===" ($script:Th.Ok)

    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) {
        Append-LogLine '[错误] 未找到 npm，请先安装 Node.js' ($script:Th.Err)
        return
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $npm.Source
    $psi.Arguments = 'run dev'
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $script:DevProcess = New-Object System.Diagnostics.Process
    $script:DevProcess.StartInfo = $psi
    $script:DevProcess.EnableRaisingEvents = $true

    $null = Register-ObjectEvent -InputObject $script:DevProcess -EventName OutputDataReceived -SourceIdentifier 'GUI-Dev-Stdout' -Action {
        $line = $Event.SourceEventArgs.Data
        if ([string]::IsNullOrEmpty($line)) { return }
        Append-LogLine $line ($script:Th.LogLine)
    }
    $null = Register-ObjectEvent -InputObject $script:DevProcess -EventName ErrorDataReceived -SourceIdentifier 'GUI-Dev-Stderr' -Action {
        $line = $Event.SourceEventArgs.Data
        if ([string]::IsNullOrEmpty($line)) { return }
        Append-LogLine $line ($script:Th.LogErr)
    }
    $null = Register-ObjectEvent -InputObject $script:DevProcess -EventName Exited -SourceIdentifier 'GUI-Dev-Exited' -Action {
        Append-LogLine '[提示] npm run dev 进程已退出。' ($script:Th.TxtMuted)
        $script:DevProcess = $null
        $f = $script:LauncherForm
        if ($f -and -not $f.IsDisposed) {
            [void]$f.BeginInvoke([action]{ Update-ServiceRows })
        }
    }

    try {
        [void]$script:DevProcess.Start()
        $script:DevProcess.BeginOutputReadLine()
        $script:DevProcess.BeginErrorReadLine()
    } catch {
        Append-LogLine "[错误] 无法启动 npm run dev：$_" ($script:Th.Err)
        foreach ($sid in @('GUI-Dev-Stdout', 'GUI-Dev-Stderr', 'GUI-Dev-Exited')) {
            Unregister-Event -SourceIdentifier $sid -ErrorAction SilentlyContinue
        }
        $script:DevProcess = $null
    }
}

function Stop-NpmDevCapturing {
    if ($script:DevProcess -and -not $script:DevProcess.HasExited) {
        try {
            $script:DevProcess.Kill()
        } catch {}
    }
    $script:DevProcess = $null
    foreach ($sid in @('GUI-Dev-Stdout', 'GUI-Dev-Stderr', 'GUI-Dev-Exited')) {
        Unregister-Event -SourceIdentifier $sid -ErrorAction SilentlyContinue
    }
}

function Set-ControlDoubleBuffered([System.Windows.Forms.Control]$ctrl) {
    try {
        $prop = [System.Windows.Forms.Control].GetProperty(
            'DoubleBuffered',
            [System.Reflection.BindingFlags]::NonPublic -bor [System.Reflection.BindingFlags]::Instance
        )
        if ($prop) { $prop.SetValue($ctrl, $true, $null) }
    } catch {}
}

function Sync-NavPageLayout {
    $ph = $script:PageHost
    if (-not $ph) { return }
    $W = [Math]::Max(1, $ph.ClientSize.Width)
    $H = [Math]::Max(1, $ph.ClientSize.Height)
    if ($null -eq $script:Pages) { return }
    foreach ($p in $script:Pages) {
        $p.Size = New-Object System.Drawing.Size($W, $H)
    }
    if ($null -eq $script:AnimNavTimer -or -not $script:AnimNavTimer.Enabled) {
        $ix = $script:NavIx
        for ($i = 0; $i -lt $script:Pages.Length; $i++) {
            $script:Pages[$i].Location = New-Object System.Drawing.Point((($i - $ix) * $W), 0)
        }
    }
}

# --- WinForms ---
$th = $script:Th
$form = New-Object System.Windows.Forms.Form
$script:LauncherForm = $form
$form.Text = 'TradingAgents 开发控制台'
$form.Size = New-Object System.Drawing.Size(1040, 720)
$form.MinimumSize = New-Object System.Drawing.Size(860, 560)
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$form.BackColor = $th.Bg
$form.ForeColor = $th.Txt

$splitMain = New-Object System.Windows.Forms.SplitContainer
$splitMain.Dock = [System.Windows.Forms.DockStyle]::Fill
$splitMain.Orientation = [System.Windows.Forms.Orientation]::Vertical
$splitMain.BackColor = $th.Split
$splitMain.Panel1.BackColor = $th.BgPanel
$splitMain.Panel2.BackColor = $th.Bg
$splitMain.BorderStyle = [System.Windows.Forms.BorderStyle]::None
$splitMain.SplitterWidth = 6

$leftRoot = New-Object System.Windows.Forms.Panel
$leftRoot.Dock = [System.Windows.Forms.DockStyle]::Fill
$leftRoot.BackColor = $th.BgPanel
$leftRoot.Padding = New-Object System.Windows.Forms.Padding(0, 0, 0, 0)

$leftAccent = New-Object System.Windows.Forms.Panel
$leftAccent.Dock = [System.Windows.Forms.DockStyle]::Left
$leftAccent.Width = 3
$leftAccent.BackColor = $th.Accent

$tlpLeft = New-Object System.Windows.Forms.TableLayoutPanel
$tlpLeft.Dock = [System.Windows.Forms.DockStyle]::Fill
$tlpLeft.ColumnCount = 1
$tlpLeft.RowCount = 4
$tlpLeft.BackColor = $th.BgPanel
$tlpLeft.Padding = New-Object System.Windows.Forms.Padding(14, 14, 14, 14)
[void]$tlpLeft.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100.0)))
[void]$tlpLeft.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 58.0)))
[void]$tlpLeft.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 1.0)))
[void]$tlpLeft.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 132.0)))
[void]$tlpLeft.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100.0)))

$lblBrand = New-Object System.Windows.Forms.Label
$lblBrand.Dock = [System.Windows.Forms.DockStyle]::Fill
$lblBrand.Text = "TradingAgents`r`n开发控制台"
$lblBrand.ForeColor = $th.Txt
$lblBrand.BackColor = $th.BgPanel
$lblBrand.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 11.25, [System.Drawing.FontStyle]::Bold)
$lblBrand.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft

$sepBrand = New-Object System.Windows.Forms.Panel
$sepBrand.Dock = [System.Windows.Forms.DockStyle]::Fill
$sepBrand.BackColor = $th.Border

$navList = New-Object System.Windows.Forms.ListBox
$navList.Dock = [System.Windows.Forms.DockStyle]::Fill
$navList.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$navList.BackColor = $th.BgCard
$navList.ForeColor = $th.Txt
$navList.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10.5)
$navList.ItemHeight = 40
$navList.IntegralHeight = $false
$navList.Margin = New-Object System.Windows.Forms.Padding(0, 8, 0, 0)
[void]$navList.Items.Add('  概览')
[void]$navList.Items.Add('  日志')
[void]$navList.Items.Add('  选项')

$tlpBtn = New-Object System.Windows.Forms.TableLayoutPanel
$tlpBtn.Dock = [System.Windows.Forms.DockStyle]::Fill
$tlpBtn.ColumnCount = 1
$tlpBtn.RowCount = 10
$tlpBtn.BackColor = $th.BgPanel
$tlpBtn.Margin = New-Object System.Windows.Forms.Padding(0, 12, 0, 0)
[void]$tlpBtn.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100.0)))
for ($ri = 0; $ri -lt 9; $ri++) {
    [void]$tlpBtn.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 44.0)))
}
[void]$tlpBtn.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100.0)))

function New-ToolbarButton([string]$text, [switch]$Primary, [switch]$SideFill) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $text
    $b.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $b.Cursor = [System.Windows.Forms.Cursors]::Hand
    $b.UseVisualStyleBackColor = $false
    $b.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9.75)
    $b.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 8)
    if ($SideFill) {
        $b.Dock = [System.Windows.Forms.DockStyle]::Fill
        $b.AutoSize = $false
        $b.Height = 40
    } else {
        $b.AutoSize = $true
        $minW = if ($Primary) { 120 } else { 92 }
        $b.MinimumSize = New-Object System.Drawing.Size($minW, 34)
        $b.Padding = New-Object System.Windows.Forms.Padding(16, 8, 16, 8)
        $b.Margin = New-Object System.Windows.Forms.Padding(4, 4, 4, 4)
    }
    if ($Primary) {
        $b.FlatAppearance.BorderSize = 0
        $b.BackColor = $script:Th.Accent
        $b.ForeColor = [System.Drawing.Color]::White
        $b.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10, [System.Drawing.FontStyle]::Bold)
        $b.FlatAppearance.MouseOverBackColor = $script:Th.AccentHi
        $b.FlatAppearance.MouseDownBackColor = [System.Drawing.Color]::FromArgb(0, 99, 210)
    } else {
        $b.FlatAppearance.BorderSize = 1
        $b.FlatAppearance.BorderColor = $script:Th.Border
        $b.BackColor = $script:Th.Btn2nd
        $b.ForeColor = $script:Th.Txt
        $b.FlatAppearance.MouseOverBackColor = [System.Drawing.Color]::FromArgb(58, 60, 74)
        $b.FlatAppearance.MouseDownBackColor = [System.Drawing.Color]::FromArgb(36, 38, 48)
    }
    return $b
}

function New-ThemedCheckBox([string]$text) {
    $c = New-Object System.Windows.Forms.CheckBox
    $c.Text = $text
    $c.AutoSize = $true
    $c.Margin = New-Object System.Windows.Forms.Padding(4, 10, 4, 4)
    $c.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $c.BackColor = $th.BgCard
    $c.ForeColor = $th.Txt
    $c.Cursor = [System.Windows.Forms.Cursors]::Hand
    return $c
}

$btnSmart = New-ToolbarButton '智能一键' -Primary -SideFill
$btnStopPorts = New-ToolbarButton '停止端口' -SideFill
$btnStopProc = New-ToolbarButton '停止 npm 进程' -SideFill
$btnOpenWeb = New-ToolbarButton '打开前端' -SideFill
$btnOpenApi = New-ToolbarButton '健康检查' -SideFill
$btnOpenDocs = New-ToolbarButton 'API 文档' -SideFill
$btnDeps = New-ToolbarButton '检测依赖' -SideFill
$btnClear = New-ToolbarButton '清空日志' -SideFill
$btnCli = New-ToolbarButton '文本菜单启动器' -SideFill

[void]$tlpBtn.Controls.Add($btnSmart, 0, 0)
[void]$tlpBtn.Controls.Add($btnStopPorts, 0, 1)
[void]$tlpBtn.Controls.Add($btnStopProc, 0, 2)
[void]$tlpBtn.Controls.Add($btnOpenWeb, 0, 3)
[void]$tlpBtn.Controls.Add($btnOpenApi, 0, 4)
[void]$tlpBtn.Controls.Add($btnOpenDocs, 0, 5)
[void]$tlpBtn.Controls.Add($btnDeps, 0, 6)
[void]$tlpBtn.Controls.Add($btnClear, 0, 7)
[void]$tlpBtn.Controls.Add($btnCli, 0, 8)

[void]$tlpLeft.Controls.Add($lblBrand, 0, 0)
[void]$tlpLeft.Controls.Add($sepBrand, 0, 1)
[void]$tlpLeft.Controls.Add($navList, 0, 2)
[void]$tlpLeft.Controls.Add($tlpBtn, 0, 3)

[void]$leftRoot.Controls.Add($leftAccent)
[void]$leftRoot.Controls.Add($tlpLeft)
Set-ControlDoubleBuffered $splitMain
Set-ControlDoubleBuffered $tlpLeft
Set-ControlDoubleBuffered $tlpBtn

$rightRoot = New-Object System.Windows.Forms.Panel
$rightRoot.Dock = [System.Windows.Forms.DockStyle]::Fill
$rightRoot.BackColor = $th.Bg

$script:SummaryLabel = New-Object System.Windows.Forms.Label
$script:SummaryLabel.Dock = [System.Windows.Forms.DockStyle]::Top
$script:SummaryLabel.Height = 48
$script:SummaryLabel.Padding = New-Object System.Windows.Forms.Padding(20, 14, 20, 10)
$script:SummaryLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
$script:SummaryLabel.Text = '正在初始化状态…'
$script:SummaryLabel.BackColor = $th.BgCard
$script:SummaryLabel.ForeColor = $th.TxtMuted
$script:SummaryLabel.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9.5)

$pageHost = New-Object System.Windows.Forms.Panel
$pageHost.Dock = [System.Windows.Forms.DockStyle]::Fill
$pageHost.BackColor = $th.Bg
Set-ControlDoubleBuffered $pageHost
$script:PageHost = $pageHost
$pageHost.add_Resize({ Sync-NavPageLayout })

$script:ListStatus = New-Object System.Windows.Forms.ListView
$script:ListStatus.Dock = [System.Windows.Forms.DockStyle]::Fill
$script:ListStatus.View = [System.Windows.Forms.View]::Details
$script:ListStatus.FullRowSelect = $true
$script:ListStatus.GridLines = $false
$script:ListStatus.BorderStyle = [System.Windows.Forms.BorderStyle]::None
$script:ListStatus.BackColor = $th.BgCard
$script:ListStatus.ForeColor = $th.Txt
$script:ListStatus.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$script:ListStatus.SmallImageList = New-Object System.Windows.Forms.ImageList
$script:ListStatus.SmallImageList.ImageSize = New-Object System.Drawing.Size(16, 16)

function New-StatusBitmap([System.Drawing.Color]$c) {
    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear($c)
    $g.Dispose()
    return $bmp
}
$script:ListStatus.SmallImageList.Images.Add('ok', (New-StatusBitmap $th.Ok))
$script:ListStatus.SmallImageList.Images.Add('wait', (New-StatusBitmap $th.Warn))
$script:ListStatus.SmallImageList.Images.Add('bad', (New-StatusBitmap $th.Err))

[void]$script:ListStatus.Columns.Add('服务', 120)
[void]$script:ListStatus.Columns.Add('状态', 100)
[void]$script:ListStatus.Columns.Add('端口', 55)
[void]$script:ListStatus.Columns.Add('PID', 90)
[void]$script:ListStatus.Columns.Add('说明', 200)

$tlpOv = New-Object System.Windows.Forms.TableLayoutPanel
$tlpOv.Dock = [System.Windows.Forms.DockStyle]::Fill
$tlpOv.ColumnCount = 1
$tlpOv.RowCount = 2
$tlpOv.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100.0)))
$tlpOv.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 62.0)))
$tlpOv.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 38.0)))
[void]$tlpOv.Controls.Add($script:ListStatus, 0, 0)

$chartPanel = New-Object System.Windows.Forms.Panel
$chartPanel.Dock = [System.Windows.Forms.DockStyle]::Fill
$chartPanel.BackColor = $th.BgCard
Set-ControlDoubleBuffered $chartPanel
$script:ChartPanel = $chartPanel
$script:ChartDisplay = @(0.12, 0.12, 0.2, 0.2, 0.2, 0.2)
$script:ChartTargets = @(0.12, 0.12, 0.2, 0.2, 0.2, 0.2)

$chartPanel.add_Paint({
    param($sender, $ev)
    $g = $ev.Graphics
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear($script:Th.BgCard)
    $rc = $sender.ClientRectangle
    if ($rc.Width -lt 20) { return }
    $pad = 16
    $n = 6
    $gap = 10
    $bw = [int]([Math]::Max(4, ($rc.Width - 2 * $pad - ($n - 1) * $gap) / $n))
    $hmax = [Math]::Max(20, $rc.Height - 2 * $pad)
    for ($i = 0; $i -lt $n; $i++) {
        $v = [double]$script:ChartDisplay[$i]
        if ($v -lt 0.04) { $v = 0.04 }
        if ($v -gt 1.0) { $v = 1.0 }
        $bh = [int]($v * $hmax)
        $x = $pad + $i * ($bw + $gap)
        $y = $rc.Bottom - $pad - $bh
        $rect = New-Object System.Drawing.Rectangle($x, $y, $bw, $bh)
        $lb = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            $rect,
            $script:Th.AccentHi,
            $script:Th.Accent,
            [single]90.0
        )
        $g.FillRectangle($lb, $rect)
        $lb.Dispose()
    }
})

[void]$tlpOv.Controls.Add($chartPanel, 0, 1)

$pageOverview = New-Object System.Windows.Forms.Panel
$pageOverview.BackColor = $th.Bg
[void]$pageOverview.Controls.Add($tlpOv)

$pageLog = New-Object System.Windows.Forms.Panel
$pageLog.BackColor = $th.Bg
$pageLog.Padding = New-Object System.Windows.Forms.Padding(14, 12, 14, 12)
$script:RichLog = New-Object System.Windows.Forms.RichTextBox
$script:RichLog.Dock = [System.Windows.Forms.DockStyle]::Fill
$script:RichLog.Font = New-Object System.Drawing.Font('Consolas', 9.5)
$script:RichLog.ReadOnly = $true
$script:RichLog.BorderStyle = [System.Windows.Forms.BorderStyle]::None
$script:RichLog.BackColor = [System.Drawing.Color]::FromArgb(16, 16, 22)
$script:RichLog.ForeColor = $th.LogLine
[void]$pageLog.Controls.Add($script:RichLog)

$pageOptions = New-Object System.Windows.Forms.Panel
$pageOptions.BackColor = $th.Bg
$pageOptions.AutoScroll = $true
$pageOptions.Padding = New-Object System.Windows.Forms.Padding(16, 12, 16, 12)

$optInfo = New-Object System.Windows.Forms.TextBox
$optInfo.Dock = [System.Windows.Forms.DockStyle]::Top
$optInfo.Height = 200
$optInfo.Multiline = $true
$optInfo.ReadOnly = $true
$optInfo.ScrollBars = [System.Windows.Forms.ScrollBars]::Vertical
$optInfo.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$optInfo.BackColor = $th.BgCard
$optInfo.ForeColor = $th.TxtMuted
$optInfo.BorderStyle = [System.Windows.Forms.BorderStyle]::None
$optInfo.Text = @'
【说明】
• 「智能一键」：按勾选项依次执行，最后在本窗口内启动 npm run dev（日志实时显示）。
• 开发模式下前端由 Vite 即时编译；「生产构建」用于验证生产包或 CI，日常可不勾选。
• 左侧「概览」为服务状态与活动图；「日志」为合并输出；「选项」为启动前勾选项。
• 文本菜单版：点「文本菜单启动器」运行 scripts\dev-launcher.ps1。
• 前端端口：默认 5173；被占用时 Vite 会使用 5174 等；概览与「打开前端」会扫描 5173–5180。
'@

$chkFlow = New-Object System.Windows.Forms.FlowLayoutPanel
$chkFlow.Dock = [System.Windows.Forms.DockStyle]::Fill
$chkFlow.FlowDirection = [System.Windows.Forms.FlowDirection]::TopDown
$chkFlow.WrapContents = $false
$chkFlow.AutoScroll = $true
$chkFlow.Padding = New-Object System.Windows.Forms.Padding(4, 8, 4, 4)
$chkFlow.BackColor = $th.Bg

$chkStopFirst = New-ThemedCheckBox '启动前释放端口 8000 / 5173–5180'
$chkStopFirst.Checked = $true
$chkUvSync = New-ThemedCheckBox '启动前执行 uv sync'
$chkUvSync.Checked = $false
$chkBuild = New-ThemedCheckBox '启动前前端生产构建（较慢）'
$chkBuild.Checked = $false
$chkExitStop = New-ThemedCheckBox '退出时停止开发服务'
$chkExitStop.Checked = $false

$script:ChkStopFirst = $chkStopFirst
$script:ChkUvSync = $chkUvSync
$script:ChkBuild = $chkBuild
$script:ChkExitStop = $chkExitStop

[void]$chkFlow.Controls.Add($chkStopFirst)
[void]$chkFlow.Controls.Add($chkUvSync)
[void]$chkFlow.Controls.Add($chkBuild)
[void]$chkFlow.Controls.Add($chkExitStop)

[void]$pageOptions.Controls.Add($optInfo)
[void]$pageOptions.Controls.Add($chkFlow)

$script:Pages = @($pageOverview, $pageLog, $pageOptions)
$script:NavIx = 0
foreach ($pg in $script:Pages) {
    $pg.Visible = $true
    Set-ControlDoubleBuffered $pg
    [void]$pageHost.Controls.Add($pg)
}

$script:AnimNavTimer = New-Object System.Windows.Forms.Timer
$script:AnimNavTimer.Interval = 12
$script:NavAnimProgress = 0.0
$script:NavAnimFrom = 0
$script:NavAnimTo = 0
$script:NavAnimDir = 1
$script:SuppressNav = $false

$script:AnimNavTimer.add_Tick({
    try {
        $script:NavAnimProgress += 0.095
        $t = [Math]::Min(1.0, $script:NavAnimProgress)
        $ease = $t * $t * (3.0 - 2.0 * $t)
        $W = [Math]::Max(1, $script:PageHost.ClientSize.Width)
        $H = [Math]::Max(1, $script:PageHost.ClientSize.Height)
        $fromP = $script:Pages[$script:NavAnimFrom]
        $toP = $script:Pages[$script:NavAnimTo]
        $d = $script:NavAnimDir
        $fromP.Left = [int](- $d * $W * $ease)
        $toP.Left = [int]($d * $W * (1.0 - $ease))
        if ($t -ge 0.999) {
            $fromP.Left = -8000
            $toP.Left = 0
            $script:NavIx = $script:NavAnimTo
            $script:AnimNavTimer.Stop()
            $navList.Enabled = $true
            Sync-NavPageLayout
        }
    } catch {}
})

$chartTimer = New-Object System.Windows.Forms.Timer
$chartTimer.Interval = 42
$chartTimer.add_Tick({
    try {
        for ($i = 0; $i -lt 6; $i++) {
            $tg = [double]$script:ChartTargets[$i]
            $cur = [double]$script:ChartDisplay[$i]
            $script:ChartDisplay[$i] = $cur + 0.16 * ($tg - $cur)
        }
        if ($script:ChartPanel) { $script:ChartPanel.Invalidate() }
    } catch {}
})
$script:ChartTimer = $chartTimer

$navList.add_SelectedIndexChanged({
    if ($script:SuppressNav) { return }
    if ($script:AnimNavTimer.Enabled) { return }
    $newIx = $navList.SelectedIndex
    if ($newIx -lt 0) { return }
    if ($newIx -eq $script:NavIx) { return }
    $W = [Math]::Max(1, $script:PageHost.ClientSize.Width)
    $H = [Math]::Max(1, $script:PageHost.ClientSize.Height)
    foreach ($pg in $script:Pages) { $pg.Size = New-Object System.Drawing.Size($W, $H) }
    $script:NavAnimFrom = $script:NavIx
    $script:NavAnimTo = $newIx
    $script:NavAnimDir = if ($newIx -gt $script:NavIx) { 1 } else { -1 }
    $script:NavAnimProgress = 0.0
    $fromP = $script:Pages[$script:NavAnimFrom]
    $toP = $script:Pages[$script:NavAnimTo]
    $fromP.Left = 0
    $toP.Left = $script:NavAnimDir * $W
    $toP.BringToFront()
    $navList.Enabled = $false
    $script:AnimNavTimer.Start()
})

[void]$rightRoot.Controls.Add($script:SummaryLabel)
[void]$rightRoot.Controls.Add($pageHost)

[void]$splitMain.Panel1.Controls.Add($leftRoot)
[void]$splitMain.Panel2.Controls.Add($rightRoot)
[void]$form.Controls.Add($splitMain)

$form.add_Load({
    try {
        $splitMain.Panel1MinSize = 268
        $splitMain.Panel2MinSize = 380
        $splitMain.PerformLayout()
        $wm = [Math]::Max(1, $splitMain.ClientSize.Width)
        $swm = $splitMain.SplitterWidth
        $maxL = $wm - $splitMain.Panel2MinSize - $swm
        $wantL = 300
        if ($maxL -ge $splitMain.Panel1MinSize) {
            $splitMain.SplitterDistance = [Math]::Max($splitMain.Panel1MinSize, [Math]::Min($wantL, $maxL))
        }
        Sync-NavPageLayout
        $script:SuppressNav = $true
        $navList.SelectedIndex = 0
        $script:SuppressNav = $false
    } catch {}
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 3500
$timer.add_Tick({
    try { Update-ServiceRows } catch {}
})

$btnSmart.add_Click({
    $form.UseWaitCursor = $true
    [System.Windows.Forms.Application]::DoEvents()
    try {
        if ($script:ChkStopFirst.Checked) {
            Stop-AllDevServices
            Stop-NpmDevCapturing
        }
        if ($script:ChkUvSync.Checked) {
            $uv = Get-Command uv -ErrorAction SilentlyContinue
            if (-not $uv) {
                Append-LogLine '[跳过] 未找到 uv，无法执行 sync' ($script:Th.Warn)
            } else {
                $code = Invoke-BlockingCli 'uv sync' $uv.Source 'sync --no-managed-python' $Root
                if ($code -ne 0) {
                    [System.Windows.Forms.MessageBox]::Show('uv sync 返回非零，请查看日志。', 'TradingAgents', 'OK', 'Warning') | Out-Null
                }
            }
        }
        if ($script:ChkBuild.Checked) {
            $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
            if (-not $npm) {
                Append-LogLine '[错误] 未找到 npm，请先安装 Node.js' ($script:Th.Err)
                return
            }
            $code = Invoke-BlockingCli 'npm run build（前端）' $npm.Source '--prefix frontend run build' $Root
            if ($code -ne 0) {
                [System.Windows.Forms.MessageBox]::Show('前端 build 失败，仍将尝试启动开发服务器；请查看日志。', 'TradingAgents', 'OK', 'Warning') | Out-Null
            }
        }
        Start-NpmDevCapturing
        Update-ServiceRows
    } finally {
        $form.UseWaitCursor = $false
    }
})

$btnStopPorts.add_Click({
    Stop-AllDevServices
    Stop-NpmDevCapturing
    Update-ServiceRows
})

$btnStopProc.add_Click({
    Stop-NpmDevCapturing
    Append-LogLine '[停止] 已结束本窗口启动的 npm；若端口仍占用请点「停止端口」。' ($script:Th.TxtMuted)
    Update-ServiceRows
})

$btnOpenWeb.add_Click({
    $wp = Test-WebDevHttpOk
    if ($wp) {
        Start-Process "http://127.0.0.1:$wp/"
    } else {
        Start-Process 'http://127.0.0.1:5173/'
    }
})
$btnOpenApi.add_Click({ Start-Process 'http://127.0.0.1:8000/healthz' })
$btnOpenDocs.add_Click({ Start-Process 'http://127.0.0.1:8000/docs' })

$btnDeps.add_Click({
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('依赖检测：')
    foreach ($pair in @(
            @{ Name = 'node'; Cmd = { node --version } },
            @{ Name = 'npm'; Cmd = { npm --version } },
            @{ Name = 'uv'; Cmd = { uv --version } }
        )) {
        try {
            $v = & $pair.Cmd.Invoke() 2>$null
            [void]$sb.AppendLine("  [√] $($pair.Name): $v")
        } catch {
            [void]$sb.AppendLine("  [×] $($pair.Name): 未找到")
        }
    }
    Append-LogLine $sb.ToString() ($script:Th.Accent)
    [System.Windows.Forms.MessageBox]::Show($sb.ToString(), '依赖检测', 'OK', 'Information') | Out-Null
})

$btnClear.add_Click({ $script:RichLog.Clear() })

$btnCli.add_Click({
    $ps1 = Join-Path $Root 'scripts\dev-launcher.ps1'
    if (-not (Test-Path $ps1)) {
        [System.Windows.Forms.MessageBox]::Show('未找到 scripts\dev-launcher.ps1', 'TradingAgents', 'OK', 'Error') | Out-Null
        return
    }
    Start-Process powershell.exe -ArgumentList @('-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ps1) -WorkingDirectory $Root
})

$form.add_FormClosing({
    param($sender, $e)
    try {
        if ($timer) { $timer.Stop() }
        if ($script:AnimNavTimer) { $script:AnimNavTimer.Stop() }
        if ($script:ChartTimer) { $script:ChartTimer.Stop() }
    } catch {}
    if ($script:ChkExitStop.Checked) {
        Stop-NpmDevCapturing
        Stop-AllDevServices
    } else {
        Stop-NpmDevCapturing
    }
})

$form.add_Shown({
    Append-LogLine "项目目录：$Root" ($script:Th.TxtMuted)
    Append-LogLine '提示：默认监听 0.0.0.0:8000 与 Vite 5173（被占用则递增）；根目录 npm run dev 通过 scripts/dev-api.mjs 优先用 uv 启动 API。' ($script:Th.Accent)
    Update-ServiceRows
    $timer.Start()
    if ($script:ChartTimer) { $script:ChartTimer.Start() }
})

[System.Windows.Forms.Application]::Run($form)
