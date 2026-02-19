# RECO3 PC Agent - macOS Setup

## Prerequisites

- Python 3.9+
- macOS 10.15+ (Catalina or later)
- sudo access (for launchd)

## Quick Install

```bash
chmod +x install_launchd.sh
sudo ./install_launchd.sh "your-api-key" "https://your-server.com" "pc-001"
```

## Manual Setup

```bash
# 1. Install dependencies
pip3 install -r ../common/requirements-agent.txt

# 2. Copy and edit config
cp ../common/config.example.yaml ../common/config.yaml
# Edit config.yaml with your settings

# 3. Test run (foreground)
python3 ../common/reco_agent.py ../common/config.yaml

# 4. Install as launchd service
sudo cp com.reco3.agent.plist /Library/LaunchDaemons/
sudo launchctl load /Library/LaunchDaemons/com.reco3.agent.plist
sudo launchctl start com.reco3.agent
```

## Service Management

```bash
# Check status
sudo launchctl list | grep reco3

# Stop
sudo launchctl stop com.reco3.agent

# Start
sudo launchctl start com.reco3.agent

# View logs
tail -f /var/log/reco3-agent/agent.log
```

## Uninstall

```bash
chmod +x uninstall_launchd.sh
sudo ./uninstall_launchd.sh
```

## Apple Silicon (M1/M2/M3)

Works on both Intel and Apple Silicon Macs. Ensure Python 3 is the native ARM64 version for best performance.

## Troubleshooting

- **Permission denied**: Run install script with `sudo`
- **launchctl error**: Check `sudo launchctl list | grep reco3` for status codes
- **Connection refused**: Verify `base_url` in config.yaml is reachable
- **Auth error (401)**: Verify `agent_id` and `api_key` match server `RECO3_AGENT_KEYS`

## Important Notes

- PC Agent is **optional** - PWA works without it
- `control.apply_enabled: true` enables command execution
- Strong commands (RESTART, ROLLBACK) require **server-side approval** (dual-lock)
