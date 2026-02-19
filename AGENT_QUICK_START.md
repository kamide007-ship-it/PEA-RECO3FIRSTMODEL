# 🚀 PC Agent - Quick Start Guide

## ⚡ 5-Minute Setup

### Step 1: Start Server with Test Mode
```bash
export RECO3_TEST_MODE=1
export RECO3_AGENT_KEYS="pc-001=devkey"
export RECO3_REQUIRE_APPROVAL=1
export API_KEY="test-key"
python app.py
```

### Step 2: Install Agent

**Windows (PowerShell as Admin):**
```powershell
cd agent/windows
.\install_service.ps1 -ApiKey devkey -BaseUrl http://127.0.0.1:5001 -AgentId pc-001
```

**macOS (Terminal):**
```bash
cd agent/macos
chmod +x install_launchd.sh
sudo ./install_launchd.sh devkey http://127.0.0.1:5001 pc-001
```

### Step 3: Open PWA Dashboard
```
http://127.0.0.1:5001/r3
```

### Step 4: Verify Agent is ONLINE
- Wait 10-15 seconds
- Should see "PC Agents" table with agent "ONLINE" status
- CPU/MEM metrics should display
- Should see "TEST MODE" badge (red)

## ✅ You're Done!

Now test these scenarios:

### Test 1: Send Safe Command
```
Test Controls → Click "SAFE Mode"
  ✓ Command appears in queue
  ✓ Status changes: pending → delivered → completed
  ✓ No approval needed
```

### Test 2: Strong Command with Approval
```
Test Controls → Click "RESTART (approval required)"
  ✓ Command status: pending
  ✓ "Approve" button appears
  ✓ Click "Approve"
  ✓ Status changes: pending → delivered → completed
  ✓ Check logs: agent executed RESTART
```

### Test 3: Agent OFFLINE
```
Windows: net stop RECO3Agent
macOS:   sudo launchctl stop com.reco3.agent
  ✓ Wait 30 seconds
  ✓ Agent status changes to OFFLINE (red)
  ✓ Restart agent
  ✓ Within 10s: ONLINE again
```

## 📖 Full Documentation

- **PC_AGENT_COMPLETE.md** - Complete technical overview
- **TEST_SCENARIOS.md** - 5 comprehensive test scenarios with SQL queries
- **agent/windows/README_windows.md** - Windows troubleshooting
- **agent/macos/README_macos.md** - macOS troubleshooting

## 🔍 Quick Queries

```bash
# Check agent connected
curl http://127.0.0.1:5001/api/r3/agents

# Check DB tables created
sqlite3 instance/reco3.db ".tables"

# View last heartbeat
sqlite3 instance/reco3.db "SELECT agent_id, last_seen FROM agent_status"

# View commands
sqlite3 instance/reco3.db "SELECT id, type, status FROM agent_commands ORDER BY ts DESC LIMIT 5"

# View audit log
sqlite3 instance/reco3.db "SELECT ts, actor, event_type FROM audit_log WHERE event_type LIKE 'agent%' ORDER BY ts DESC LIMIT 10"
```

## 🆘 Troubleshooting

### Agent won't connect (401 error)
```
✓ Check RECO3_AGENT_KEYS env var is set
✓ Verify agent config.yaml has matching api_key
✓ Restart agent service
```

### Commands not being pulled
```
✓ Check RECO3_REQUIRE_APPROVAL=1 is set
✓ For strong commands: click "Approve" first
✓ Check agent logs: tail -f agent/logs/agent.log
```

### PWA not showing agents
```
✓ Refresh page (Ctrl+R)
✓ Check browser console (F12) for JS errors
✓ Verify server is running: curl http://127.0.0.1:5001/health
```

## 🎯 What's Being Tested

```
Monitoring:          CPU/MEM/DISK/NET metrics
                     Process status
                     Log files (ERROR/WARN)
                     
Control:             SET_MODE (no approval)
                     SET_RATE_LIMIT (no approval)
                     RESTART_PROCESS (approval required)
                     ROLLBACK (approval required)

Safety:              Dual-lock enforcement
                     Approval workflow
                     Audit trail

Resilience:          Offline detection (< 30s)
                     Service auto-restart
                     Graceful shutdown
                     Exponential backoff
```

---

## 📊 Summary

| Component | Status | Location |
|-----------|--------|----------|
| Server API | ✅ Complete | app.py |
| Agent Code | ✅ Complete | agent/common/ |
| Windows Service | ✅ Complete | agent/windows/ |
| macOS launchd | ✅ Complete | agent/macos/ |
| PWA Dashboard | ✅ Complete | templates/reco3.html |
| Test Mode | ✅ Complete | RECO3_TEST_MODE env |
| Dual-Lock Safety | ✅ Complete | Approval workflow |
| Audit Trail | ✅ Complete | audit_log table |
| Documentation | ✅ Complete | TEST_SCENARIOS.md |

All components ready for testing! 🎉
