# RECO3 PC Agent - Windows Setup

## Prerequisites

- Python 3.9+
- Administrator privileges (for service installation)

## Quick Install

```powershell
# Run as Administrator
.\install_service.ps1 -ApiKey "your-key" -BaseUrl "https://your-server.com" -AgentId "pc-001"
```

## Manual Setup

```powershell
# 1. Create virtual environment
python -m venv ..\venv
..\venv\Scripts\activate

# 2. Install dependencies
pip install -r ..\common\requirements-agent.txt
pip install pywin32

# 3. Copy and edit config
copy ..\common\config.example.yaml ..\common\config.yaml
# Edit config.yaml with your settings

# 4. Test run (foreground)
python ..\common\reco_agent.py ..\common\config.yaml

# 5. Install as Windows Service
python reco3_agent_service.py install
python reco3_agent_service.py start
```

## Service Management

```powershell
# Check status
sc query RECO3Agent

# Stop
net stop RECO3Agent

# Start
net start RECO3Agent

# Remove
python reco3_agent_service.py stop
python reco3_agent_service.py remove
```

## Build Standalone EXE (Optional)

```powershell
.\build_exe.ps1
# Output: dist\reco3-agent.exe
```

## Uninstall

```powershell
.\uninstall_service.ps1
```

## Troubleshooting

- **Service won't start**: Check `agent\logs\agent.log` and Windows Event Viewer
- **Connection refused**: Verify `base_url` in config.yaml is reachable
- **Auth error (401)**: Verify `agent_id` and `api_key` match server `RECO3_AGENT_KEYS`
- **psutil error**: Ensure psutil is installed: `pip install psutil`

## Important Notes

- PC Agent is **optional** - PWA works without it
- `control.apply_enabled: true` enables command execution
- Strong commands (RESTART, ROLLBACK) require **server-side approval** (dual-lock)
