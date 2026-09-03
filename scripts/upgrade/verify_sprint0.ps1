"""Upgrade sprint verification scripts."""

param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
& powershell -File (Join-Path $Root "scripts/verify_restore_point.ps1") @args
