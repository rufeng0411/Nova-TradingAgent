# Create Windows desktop shortcut(s) for Nova Trading Agents dev launcher.
param(
    [ValidateSet('electron', 'dev', 'both')]
    [string]$Mode = 'electron'
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Desktop = [Environment]::GetFolderPath('Desktop')

function New-RepoShortcut {
    param(
        [string]$LinkName,
        [string]$TargetBat,
        [string]$Description
    )

    $target = Join-Path $RepoRoot $TargetBat
    if (-not (Test-Path -LiteralPath $target)) {
        throw "Missing launcher: $target"
    }

    $lnk = Join-Path $Desktop "$LinkName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = $env:ComSpec
    $sc.Arguments = "/c `"`"$target`"`""
    $sc.WorkingDirectory = $RepoRoot
    $sc.WindowStyle = 1
    $sc.Description = $Description
    $sc.Save()

    Write-Host "[OK] $lnk"
}

switch ($Mode) {
    'electron' {
        New-RepoShortcut -LinkName "Nova Trading Agents" -TargetBat 'start-electron.bat' `
            -Description 'Nova Trading Agents dev console (Electron launcher)'
    }
    'dev' {
        New-RepoShortcut -LinkName "Nova Trading Agents (Dev)" -TargetBat 'start-dev.bat' `
            -Description 'Nova Trading Agents quick dev (npm run dev)'
    }
    'both' {
        & $PSCommandPath -Mode electron
        & $PSCommandPath -Mode dev
    }
}

Write-Host ""
Write-Host "Desktop: $Desktop"
