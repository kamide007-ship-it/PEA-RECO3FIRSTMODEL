#!/bin/bash
# RECO3 Agent - macOS Install Script (launchd)
set -e

API_KEY="${1:-devkey}"
BASE_URL="${2:-https://pea-reco3firstmodel.onrender.com}"
AGENT_ID="${3:-pc-001}"

if [ -z "$API_KEY" ]; then
    echo "Usage: $0 <API_KEY> [BASE_URL] [AGENT_ID]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMMON_DIR="$PROJECT_DIR/common"
INSTALL_DIR="/opt/reco3-agent"
LOG_DIR="/var/log/reco3-agent"

echo "=== RECO3 Agent Installer (macOS) ==="

# 1. Create directories
echo "[1/5] Creating directories..."
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$LOG_DIR"
sudo chown "$(whoami)" "$INSTALL_DIR" "$LOG_DIR"

# 2. Copy agent files
echo "[2/5] Copying agent files..."
cp -r "$PROJECT_DIR"/* "$INSTALL_DIR/"

# 3. Install dependencies
echo "[3/5] Installing Python dependencies..."
pip3 install -r "$COMMON_DIR/requirements-agent.txt" --user

# 4. Create config.yaml
echo "[4/5] Creating config.yaml..."
cat > "$INSTALL_DIR/common/config.yaml" <<EOF
base_url: "$BASE_URL"
agent_id: "$AGENT_ID"
api_key: "$API_KEY"
platform: "macos"
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
  file: "$LOG_DIR/agent.log"
EOF

# 5. Install launchd service
echo "[5/5] Installing launchd service..."
sudo cp "$SCRIPT_DIR/com.reco3.agent.plist" /Library/LaunchDaemons/com.reco3.agent.plist
sudo launchctl load /Library/LaunchDaemons/com.reco3.agent.plist
sudo launchctl start com.reco3.agent

echo ""
echo "=== Installation Complete ==="
echo "  Agent ID : $AGENT_ID"
echo "  Server   : $BASE_URL"
echo "  Config   : $INSTALL_DIR/common/config.yaml"
echo "  Logs     : $LOG_DIR/"
echo ""
echo "Commands:"
echo "  Status : sudo launchctl list | grep reco3"
echo "  Stop   : sudo launchctl stop com.reco3.agent"
echo "  Start  : sudo launchctl start com.reco3.agent"
