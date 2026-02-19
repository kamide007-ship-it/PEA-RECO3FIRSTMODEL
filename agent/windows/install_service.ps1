# RECO3 Agent - Windows Service Install Script
# Run as Administrator

param(
    [string]$ApiKey = "devkey",
    [string]$BaseUrl = "https://pea-reco3firstmodel.onrender.com",
    [string]$AgentId = "pc-001"
)

# Check admin privileges
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "Please run as Administrator"
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $projectDir "common"

Write-Host "=== RECO3 Agent Installer ===" -ForegroundColor Cyan

# 1. Create virtual environment
Write-Host "[1/4] Creating Python virtual environment..." -ForegroundColor Yellow
python -m venv "$projectDir\venv"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create venv. Ensure Python is installed."
    exit 1
}

# 2. Install dependencies
Write-Host "[2/4] Installing dependencies..." -ForegroundColor Yellow
& "$projectDir\venv\Scripts\pip" install -r "$commonDir\requirements-agent.txt"
& "$projectDir\venv\Scripts\pip" install pywin32

# 3. Create config.yaml
Write-Host "[3/4] Creating config.yaml..." -ForegroundColor Yellow
$logsDir = Join-Path $projectDir "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$configContent = @"
base_url: "$BaseUrl"
agent_id: "$AgentId"
api_key: "$ApiKey"
platform: "windows"
version: "1.0"

control:
  apply_enabled: true
  safe_modes: ["NORMAL", "SAFE"]

watch:
  processes: []
  log_files: []

intervals:
  heartbeat_sec: 10
  pull_sec: 10
  logs_sec: 15

logging:
  level: "INFO"
  file: "$($logsDir -replace '\\', '/')/agent.log"
"@

$configPath = Join-Path $commonDir "config.yaml"
Set-Content -Path $configPath -Value $configContent -Encoding UTF8

# 4. Install and start service
Write-Host "[4/4] Installing Windows Service..." -ForegroundColor Yellow
& "$projectDir\venv\Scripts\python" "$scriptDir\reco3_agent_service.py" install
& "$projectDir\venv\Scripts\python" "$scriptDir\reco3_agent_service.py" start

Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Green
Write-Host "  Agent ID : $AgentId"
Write-Host "  Server   : $BaseUrl"
Write-Host "  Config   : $configPath"
Write-Host "  Logs     : $logsDir\agent.log"
Write-Host ""
Write-Host "Commands:" -ForegroundColor Cyan
Write-Host "  Status : sc query RECO3Agent"
Write-Host "  Stop   : net stop RECO3Agent"
Write-Host "  Start  : net start RECO3Agent"
