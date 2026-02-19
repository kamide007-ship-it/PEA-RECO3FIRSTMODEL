# RECO3 Agent - Build standalone EXE using PyInstaller
# Optional: creates a single-file executable for deployment

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $projectDir "common"

Write-Host "=== Building RECO3 Agent EXE ===" -ForegroundColor Cyan

# Install pyinstaller
& "$projectDir\venv\Scripts\pip" install pyinstaller

# Build
& "$projectDir\venv\Scripts\pyinstaller" `
    --onefile `
    --name "reco3-agent" `
    --add-data "$commonDir\config.example.yaml;." `
    "$commonDir\reco_agent.py"

Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Green
Write-Host "  Output: dist\reco3-agent.exe"
