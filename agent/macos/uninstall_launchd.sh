#!/bin/bash
# RECO3 Agent - macOS Uninstall Script
set -e

echo "=== RECO3 Agent Uninstaller (macOS) ==="

echo "Stopping service..."
sudo launchctl stop com.reco3.agent 2>/dev/null || true

echo "Unloading service..."
sudo launchctl unload /Library/LaunchDaemons/com.reco3.agent.plist 2>/dev/null || true

echo "Removing plist..."
sudo rm -f /Library/LaunchDaemons/com.reco3.agent.plist

echo ""
echo "=== Uninstall Complete ==="
echo "Note: Agent files remain at /opt/reco3-agent (remove manually if desired)"
