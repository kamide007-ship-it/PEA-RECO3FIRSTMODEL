# RECO3 Agent - Windows Service Uninstall Script
# Run as Administrator

if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "Please run as Administrator"
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectDir = Split-Path -Parent $scriptDir

Write-Host "=== RECO3 Agent Uninstaller ===" -ForegroundColor Cyan

Write-Host "Stopping service..." -ForegroundColor Yellow
& "$projectDir\venv\Scripts\python" "$scriptDir\reco3_agent_service.py" stop 2>$null

Write-Host "Removing service..." -ForegroundColor Yellow
& "$projectDir\venv\Scripts\python" "$scriptDir\reco3_agent_service.py" remove

Write-Host ""
Write-Host "=== Uninstall Complete ===" -ForegroundColor Green
