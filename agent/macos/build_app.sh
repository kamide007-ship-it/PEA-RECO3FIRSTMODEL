#!/bin/bash
# RECO3 Agent - Build standalone app using PyInstaller (macOS)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMMON_DIR="$PROJECT_DIR/common"

echo "=== Building RECO3 Agent App ==="

pip3 install pyinstaller

pyinstaller \
    --onefile \
    --name "reco3-agent" \
    --add-data "$COMMON_DIR/config.example.yaml:." \
    "$COMMON_DIR/reco_agent.py"

echo ""
echo "=== Build Complete ==="
echo "  Output: dist/reco3-agent"
