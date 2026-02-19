# RECO3 PC Agent - Single Developer Test Scenarios

## 🎯 Objective

Enable a single developer to verify the full PC Agent integration:
- **Monitoring**: All metrics collected (CPU/MEM/DISK/NET, processes, logs)
- **Control**: All command types executable (SET_MODE, RESTART, ROLLBACK)
- **Safety**: Dual-lock enforcement for strong operations (server approval + agent apply_enabled)
- **Audit**: All operations logged to audit_log table

## 🚀 Quick Start (Ender.com + Local PC Agent)

### 1. Deploy with Test Mode Enabled

Set environment variables on Render:
```
RECO3_TEST_MODE=1
RECO3_AGENT_KEYS="pc-001=devkey"
RECO3_REQUIRE_APPROVAL=1
```

Or locally:
```bash
export RECO3_TEST_MODE=1
export RECO3_AGENT_KEYS="pc-001=devkey"
export RECO3_REQUIRE_APPROVAL=1
export API_KEY="test-key"
python app.py
```

### 2. Install PC Agent

**Windows:**
```powershell
cd agent/windows
.\install_service.ps1 -ApiKey devkey -BaseUrl http://127.0.0.1:5001 -AgentId pc-001
```

**macOS:**
```bash
cd agent/macos
chmod +x install_launchd.sh
sudo ./install_launchd.sh devkey http://127.0.0.1:5001 pc-001
```

### 3. Verify Agent is Online

Visit PWA: `http://127.0.0.1:5001/r3`

Observe:
- ✅ "TEST MODE" badge visible
- ✅ PC Agents table shows "ONLINE" status
- ✅ CPU/MEM/DISK metrics updating
- ✅ Agent Logs section populated

---

## 📋 Test Scenarios

### Scenario (a): Normal Operation - Agent ONLINE

**Expected Flow:**
```
Agent sends heartbeat every 10s
→ Server updates agent_status.last_seen
→ PWA displays ONLINE (< 30s since last heartbeat)
→ Metrics (CPU/MEM/DISK) updated in real-time
```

**Steps:**
1. Start Agent (Windows service or macOS launchd)
2. Open PWA `/r3` dashboard
3. Wait 10-15 seconds

**Verify:**
- [ ] PC Agents table shows "ONLINE" badge
- [ ] CPU/MEM metrics are non-zero
- [ ] Last Seen timestamp is recent
- [ ] agent_status table has recent entry: `SELECT * FROM agent_status WHERE agent_id='pc-001'`

**Audit Trail:**
```sql
SELECT * FROM audit_log WHERE event_type='agent_heartbeat' ORDER BY ts DESC LIMIT 5;
```

---

### Scenario (b): Error Logging & Incident Creation

**Expected Flow:**
```
Agent finds log file with ERROR
→ Sends to server via /agent/logs POST
→ Server creates incident automatically
→ PWA notifies: "Agent Error"
```

**Steps:**
1. Agent is running with `watch.log_files` configured
2. Manually add error to monitored log file:
   ```bash
   echo "[ERROR] TEST_ERROR: Something failed" >> /path/to/monitored.log
   ```
3. Wait 15-20 seconds (logs polling interval)
4. Check PWA dashboard

**Verify:**
- [ ] "Agent Error" notification appears (orange/red toast)
- [ ] Agent Logs section shows the new ERROR entry
- [ ] incident table has new row: `SELECT * FROM incidents WHERE title LIKE '%Agent%' ORDER BY ts_open DESC LIMIT 1;`
- [ ] agent_logs table: `SELECT * FROM agent_logs WHERE level='ERROR' ORDER BY ts DESC LIMIT 1;`

**Audit Trail:**
```sql
SELECT * FROM audit_log WHERE event_type='agent_logs' ORDER BY ts DESC LIMIT 5;
```

---

### Scenario (c): CPU High → SET_RATE_LIMIT Suggestion

**Expected Flow:**
```
Monitor detects CPU > 95%
→ Creates observation
→ Suggestion engine recommends SET_RATE_LIMIT
→ PWA displays suggestion
```

**Manual Test (simulating high CPU):**
1. From PWA test controls, click "Rate Limit" button
2. Command created: `SET_RATE_LIMIT endpoint=/api limit_rps=50`
3. Command appears in Command Queue section
4. Agent polls and receives command
5. Agent executes (no approval needed for SET_RATE_LIMIT)
6. Result reported back

**Verify:**
- [ ] Command Queue shows: "SET_RATE_LIMIT pending"
- [ ] After 10-15 seconds: status changes to "completed"
- [ ] agent_commands table: `SELECT * FROM agent_commands WHERE type='SET_RATE_LIMIT' ORDER BY ts DESC LIMIT 1;`

---

### Scenario (d): Process Monitoring & RESTART with Dual-Lock

**Expected Flow:**
```
Agent watches process (e.g., python)
Process is stopped externally
Agent reports missing process
→ Suggests RESTART_PROCESS
→ PWA shows "RESTART (approval required)"
→ Developer clicks "Approve"
→ Server adds approval record
→ Agent polls and sees approval
→ Agent executes RESTART (IF apply_enabled=true)
→ Result reported
```

**Steps:**
1. Configure Agent with monitored process:
   ```yaml
   watch:
     processes:
       - name: "python"
         restart_cmd: "python /path/to/dummy.py"
         allow_restart: true
   ```

2. Create test process that runs:
   ```bash
   # dummy.py
   import time
   while True:
     time.sleep(1)
   ```

3. From PWA test controls, click "RESTART (approval required)"
   - Command type: `RESTART_PROCESS`
   - Payload: `{process: "python"}`

4. Observe in Command Queue:
   - Status: "pending"
   - "Needs Approval" badge
   - "Approve" button visible

5. Click "Approve" button

6. Watch status change: "pending" → "delivered" → "completed"

**Verify Dual-Lock:**
- [ ] Before approval: agent_commands.status = "pending"
- [ ] After approval: approvals table has entry: `SELECT * FROM approvals WHERE command_id=...`
- [ ] Agent only executes IF:
  - ✅ approvals record exists (server-side approval)
  - ✅ Agent config has `control.apply_enabled=true` (agent-side approval)
  - If either is false: agent_commands.status remains "pending" or changes to "failed" with error

**Audit Trail:**
```sql
-- Approval event
SELECT * FROM audit_log WHERE event_type='command_approved' ORDER BY ts DESC LIMIT 1;

-- Execution result
SELECT * FROM audit_log WHERE event_type='agent_report' ORDER BY ts DESC LIMIT 1;

-- Full command lifecycle
SELECT * FROM agent_commands WHERE type='RESTART_PROCESS' ORDER BY ts DESC LIMIT 1;
```

---

### Scenario (e): Communication Loss → OFFLINE & SAFE Mode

**Expected Flow:**
```
Agent loses connection to server
→ Stops sending heartbeat
→ Server: 30s timeout (no /agent/heartbeat)
→ PWA displays: OFFLINE
→ Agent: consecutive failures > 5
→ Agent switches to SAFE mode locally
```

**Steps:**
1. Agent is running and ONLINE
2. Stop agent:
   - **Windows:** `net stop RECO3Agent`
   - **macOS:** `sudo launchctl stop com.reco3.agent`

3. Wait 30 seconds
4. Check PWA dashboard

**Verify:**
- [ ] PC Agents table: status = "OFFLINE" (red badge)
- [ ] "Agent Offline" notification (optional, low-priority)
- [ ] agent_status.last_seen is ~30s old

5. Check agent logs:
   ```bash
   tail -f agent/logs/agent.log
   ```
   - Should show: "Entering SAFE mode (5+ failures)"

**Restart Agent:**
```powershell
# Windows
net start RECO3Agent

# macOS
sudo launchctl start com.reco3.agent
```

**Verify Recovery:**
- [ ] PWA shows ONLINE again within 10s
- [ ] agent_status.last_seen is recent

---

## 🔐 Dual-Lock Verification

### Test: ROLLBACK without approval should FAIL

**Setup:**
```
RECO3_REQUIRE_APPROVAL=1
Agent: control.apply_enabled=true
```

**Steps:**
1. From PWA test controls, click "ROLLBACK (approval required)"
2. Command appears in queue with status "pending"
3. Wait 30 seconds (several pull intervals)

**Verify:**
- [ ] agent_commands.status = "pending" (stays pending, never "delivered")
- [ ] Agent logs show: "Command rejected: approval required" or similar
- [ ] No ROLLBACK is executed

**Now Approve:**
1. Click "Approve" button
2. approvals table gets new entry
3. Agent polls again
4. Command status changes: "pending" → "delivered" → "completed"

---

### Test: Strong command with apply_enabled=false should FAIL

**Setup:**
```
Agent config:
control:
  apply_enabled: false  # ← Safety lock ON
```

**Steps:**
1. Approve a RESTART command from PWA
2. Agent polls and sees approval
3. Agent checks: apply_enabled = false

**Verify:**
- [ ] agent_commands.result_json contains: `{"success": false, "error": "Strong command ... blocked: apply_enabled=false"}`
- [ ] Status = "failed"
- [ ] No actual process restart occurs

---

## 📊 Audit Log Query Examples

### View all agent heartbeats:
```sql
SELECT ts, actor, event_type, payload_json FROM audit_log
WHERE event_type='agent_heartbeat'
ORDER BY ts DESC LIMIT 20;
```

### View all approvals:
```sql
SELECT ts, actor, event_type, ref_id FROM audit_log
WHERE event_type='command_approved'
ORDER BY ts DESC;
```

### View command execution history:
```sql
SELECT ts, actor, event_type, ref_id, payload_json FROM audit_log
WHERE event_type IN ('agent_pull', 'agent_report')
ORDER BY ts DESC LIMIT 50;
```

### Full lifecycle of a command:
```sql
-- 1. Command created
SELECT id, type, status FROM agent_commands WHERE id='<cmd_id>';

-- 2. Approval granted
SELECT * FROM approvals WHERE command_id='<cmd_id>';

-- 3. Agent pulled it
SELECT * FROM audit_log WHERE event_type='agent_pull' AND ref_id='<agent_id>' ORDER BY ts DESC LIMIT 1;

-- 4. Result reported
SELECT * FROM audit_log WHERE event_type='agent_report' AND ref_id='<cmd_id>';
```

---

## 🧪 Test Checklist

- [ ] Test Mode badge visible (`RECO3_TEST_MODE=1`)
- [ ] Agent heartbeat updates every 10s
- [ ] CPU/MEM/DISK metrics displaying
- [ ] Error log triggers incident creation
- [ ] SET_MODE SAFE/NORMAL works (no approval needed)
- [ ] SET_RATE_LIMIT command executes without approval
- [ ] RESTART requires server approval (dual-lock works)
- [ ] ROLLBACK requires server approval (dual-lock works)
- [ ] approval workflow: pending → click Approve → delivered → completed
- [ ] Agent OFFLINE after 30s of no heartbeat
- [ ] Audit log captures all operations
- [ ] Can restart agent and return to ONLINE

---

## 🚨 Troubleshooting

### Agent not connecting (401 error):
- Verify `X-AGENT-ID` and `X-API-Key` headers match `RECO3_AGENT_KEYS`
- Check server logs: `echo $RECO3_AGENT_KEYS`

### Commands not being pulled:
- Check `RECO3_REQUIRE_APPROVAL=1` (strong commands need approval)
- Verify agent logs: `tail agent/logs/agent.log`
- Check: Agent config `control.apply_enabled = true`?

### PWA not showing agents:
- Refresh page (`Ctrl+R`)
- Check browser console for errors (`F12`)
- Verify `api/r3/agents` returns data: `curl http://127.0.0.1:5001/api/r3/agents -H "Cookie: session=..."`

### Approval not working:
- Ensure `RECO3_REQUIRE_APPROVAL=1` is set on server
- Check approvals table: `SELECT * FROM approvals;`
- Verify command type is "strong": RESTART_PROCESS, ROLLBACK, or STOP_PROCESS

---

## 📝 Summary

All scenarios demonstrate:
1. ✅ **Real-time monitoring** (no dummy data)
2. ✅ **Bidirectional control** (server → Agent)
3. ✅ **Safety-first design** (dual-lock for strong operations)
4. ✅ **Full audit trail** (all operations logged)
5. ✅ **Graceful degradation** (OFFLINE handling, SAFE mode)

A single developer can run all tests locally and verify the complete Agent integration.
