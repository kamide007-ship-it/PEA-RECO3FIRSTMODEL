# RECO3 PC Agent 統合実装計画（Phase 3）

**目標**: Windows/macOS で常駐稼働する PC Agent を追加。Web監視と PC監視を統合し、「提案中心・承認付き実行」の原則を保つ。

**スコープ**: PWA（Web側）は既成、PC Agent（新規）で PC監視/制御を追加

---

## 📐 アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│  PWA (/r3) - Web側                                          │
│  ├─ Web監視（既実装）                                       │
│  ├─ PC Agent 一覧表示（Agent ONLINE/OFFLINE）             │
│  ├─ CPU/MEM/DISK/NET 表示                                 │
│  └─ Command Approve UI（制御実行の承認ボタン）            │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTP REST API
┌──────────────────▼──────────────────────────────────────────┐
│  Flask Server (/agent/*)                                    │
│  ├─ GET  /agent/pull         ← Agent が polling           │
│  ├─ POST /agent/heartbeat    ← Agent が送信（10秒周期）   │
│  ├─ POST /agent/logs         ← Agent がログ送信           │
│  └─ [DB] agent_status / agent_logs / agent_commands       │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTP REST API
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────────┐ ┌─────▼──────────────┐
│  Windows Agent     │ │  macOS Agent       │
│  ├─ Service化      │ │  ├─ launchd        │
│  ├─ py/exe       │ │  ├─ shell script    │
│  ├─ heartbeat     │ │  ├─ heartbeat      │
│  ├─ metrics       │ │  ├─ metrics        │
│  └─ commands exec │ │  └─ commands exec  │
└────────────────────┘ └────────────────────┘

[PC Process/Logs]  ← Agent が監視・制御
```

---

## 🗂️ ディレクトリ構造

```
/agent/
├─ common/
│  ├─ reco_agent.py            [Main Agent Loop]
│  ├─ http_client.py           [HTTP Client (requests)]
│  ├─ config.example.yaml      [Configuration Template]
│  ├─ metrics.py               [CPU/MEM/DISK/NET Collection]
│  ├─ logs_tail.py             [Log File Tailing]
│  ├─ commands.py              [Command Execution]
│  ├─ security.py              [Allowlist Validation]
│  ├─ util.py                  [Utilities]
│  └─ requirements-agent.txt   [Dependencies]
│
├─ windows/
│  ├─ reco3_agent_service.py   [Windows Service Class]
│  ├─ install_service.ps1      [Install Script]
│  ├─ uninstall_service.ps1    [Uninstall Script]
│  ├─ build_exe.ps1            [PyInstaller Build]
│  └─ README_windows.md        [Windows Setup Guide]
│
└─ macos/
   ├─ com.reco3.agent.plist    [launchd Configuration]
   ├─ install_launchd.sh       [Install Script]
   ├─ uninstall_launchd.sh     [Uninstall Script]
   ├─ build_app.sh             [Build Script]
   └─ README_macos.md          [macOS Setup Guide]
```

---

## 📋 実装フェーズ（5段階）

### Phase 3-1: サーバー側API + DB（1-2週）

**目標**: Agent が接続・通信できるバックエンド完成

**実装内容**:

#### 1-1. DB テーブル追加
```python
# app.py: init_db() に以下を追加

# agent_status: Agent のハートビート記録
agent_status (
  agent_id TEXT PRIMARY KEY,
  last_seen DATETIME,
  platform TEXT,        # windows, macos, linux
  version TEXT,         # Agent version
  payload_json TEXT,    # {cpu%, mem%, disk%, uptime_sec, error_count}
  org_id TEXT,
  created_at DATETIME,
  updated_at DATETIME
)

# agent_logs: Agent が送信したログ
agent_logs (
  id TEXT PRIMARY KEY,
  agent_id TEXT,
  ts DATETIME,
  level TEXT,          # INFO, WARN, ERROR, CRITICAL
  code TEXT,           # error code (e.g., 'PROC_NOT_FOUND')
  msg TEXT,            # human-readable message
  meta_json TEXT,      # {process_name, pid, file_path, ...}
  org_id TEXT,
  created_at DATETIME,
  FOREIGN KEY(agent_id) REFERENCES agent_status(agent_id)
)

# agent_commands: PWA が Agent に指令
agent_commands (
  id TEXT PRIMARY KEY,
  agent_id TEXT,
  ts DATETIME,
  type TEXT,           # SET_MODE, RESTART_PROCESS, SET_RATE_LIMIT, ...
  payload_json TEXT,   # {mode: SAFE, process: "nginx", ...}
  status TEXT,         # pending, delivered, inflight, completed, failed
  result_json TEXT,    # {success: bool, error: str, output: str}
  org_id TEXT,
  created_at DATETIME,
  FOREIGN KEY(agent_id) REFERENCES agent_status(agent_id)
)
```

#### 1-2. Flask API エンドポイント
```python
# app.py に以下を追加

# Authentication: Agent requests require X-AGENT-ID + X-API-Key header
def validate_agent_request():
    agent_id = request.headers.get('X-AGENT-ID', '').strip()
    api_key = request.headers.get('X-API-Key', '').strip()

    if not agent_id or not api_key:
        return None, 401

    # Verify agent_id is registered and api_key matches
    # Config: RECO3_AGENT_KEYS = "agent1:key1,agent2:key2" or JSON
    ...
    return agent_id, 200

@app.post("/agent/heartbeat")
def agent_heartbeat():
    """
    Agent sends heartbeat every 10 seconds.
    Payload: {platform, version, metrics: {cpu, mem, disk, net}}
    """
    agent_id, status = validate_agent_request()
    if status != 200:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json()

    # Update agent_status
    agent_status_record = {
        'agent_id': agent_id,
        'last_seen': datetime.utcnow(),
        'platform': data.get('platform'),
        'version': data.get('version'),
        'payload_json': json.dumps(data.get('metrics', {}))
    }
    # Insert or update DB

    AuditLog.log(
        actor=f"agent:{agent_id}",
        event_type="agent_heartbeat",
        ref_id=agent_id,
        payload=agent_status_record,
        org_id=get_org_id()
    )

    return jsonify({"status": "ok"})

@app.post("/agent/logs")
def agent_logs():
    """
    Agent sends log entries.
    Payload: {logs: [{ts, level, code, msg, meta}, ...]}
    """
    agent_id, status = validate_agent_request()
    if status != 200:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json()

    for log_entry in data.get('logs', []):
        # Insert to agent_logs table
        AgentLog.create(
            agent_id=agent_id,
            ts=log_entry.get('ts'),
            level=log_entry.get('level'),
            code=log_entry.get('code'),
            msg=log_entry.get('msg'),
            meta=log_entry.get('meta'),
            org_id=get_org_id()
        )

    # Check if any ERROR/CRITICAL → create incident or alert
    errors = [l for l in data.get('logs', []) if l.get('level') in ['ERROR', 'CRITICAL']]
    if errors:
        for error in errors:
            Incidents.create(
                severity='high' if error.get('level') == 'CRITICAL' else 'medium',
                title=f"Agent {agent_id}: {error.get('code')}",
                summary=error.get('msg'),
                org_id=get_org_id()
            )

    return jsonify({"status": "ok"})

@app.get("/agent/pull")
def agent_pull():
    """
    Agent polls for commands.
    Returns: {commands: [{id, type, payload}, ...]}
    """
    agent_id, status = validate_agent_request()
    if status != 200:
        return jsonify({"error": "unauthorized"}), 401

    # Fetch pending commands for this agent
    pending = AgentCommand.list_pending(agent_id)

    # Mark as 'delivered' (sent to agent)
    for cmd in pending:
        AgentCommand.update_status(cmd['id'], 'delivered')

    AuditLog.log(
        actor=f"agent:{agent_id}",
        event_type="agent_pull",
        ref_id=agent_id,
        payload={'count': len(pending)},
        org_id=get_org_id()
    )

    return jsonify({"commands": pending})

@app.post("/agent/report")
def agent_report():
    """
    Agent reports command execution result.
    Payload: {command_id, status: completed|failed, result: {...}}
    """
    agent_id, status = validate_agent_request()
    if status != 200:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json()
    cmd_id = data.get('command_id')
    result = data.get('result', {})
    cmd_status = data.get('status', 'completed')

    AgentCommand.update_status(cmd_id, cmd_status)
    AgentCommand.set_result(cmd_id, result)

    AuditLog.log(
        actor=f"agent:{agent_id}",
        event_type="agent_report",
        ref_id=cmd_id,
        payload=result,
        org_id=get_org_id()
    )

    return jsonify({"status": "ok"})
```

#### 1-3. Allowlist & Security
```python
# reco2/agent_security.py (新規)

ALLOWED_COMMANDS = {
    'SET_MODE': {
        'modes': ['NORMAL', 'SAFE', 'LOCKED'],
        'safe_modes': ['NORMAL', 'SAFE'],
        'requires_approval': False,  # Safe modes don't need approval
    },
    'RESTART_PROCESS': {
        'requires_approval': True,
        'whitelist': ['nginx', 'apache2', 'postgresql', 'mysql'],  # Configurable
    },
    'SET_RATE_LIMIT': {
        'requires_approval': False,
        'params': ['endpoint', 'limit_rps'],
    },
    'NOTIFY_OPS': {
        'requires_approval': False,
        'params': ['severity', 'message'],
    },
}

def validate_command(cmd_type, payload, agent_config):
    """
    Validate command against allowlist.
    Returns: (valid: bool, reason: str)
    """
    if cmd_type not in ALLOWED_COMMANDS:
        return False, f"Command {cmd_type} not allowed"

    spec = ALLOWED_COMMANDS[cmd_type]

    # Special checks per command type
    if cmd_type == 'RESTART_PROCESS':
        process = payload.get('process')
        if process not in spec['whitelist']:
            return False, f"Process {process} not in whitelist"

    return True, "OK"
```

**期間**: 1-2週
**難易度**: 中
**チーム**: バックエンド1

---

### Phase 3-2: PC Agent 共通実装（1-2週）

**目標**: Windows/macOS で動作する Agent の基本実装

**実装内容**:

#### 2-1. Main Agent Loop
```python
# agent/common/reco_agent.py

import time
import os
import json
import logging
from datetime import datetime
from http_client import RECOHttpClient
from metrics import collect_metrics
from logs_tail import LogTail
from commands import execute_command

class RECOAgent:
    def __init__(self, config_path):
        self.config = load_config(config_path)
        self.agent_id = self.config['agent_id']
        self.api_key = self.config['api_key']
        self.base_url = self.config['base_url']
        self.running = False

        self.client = RECOHttpClient(
            base_url=self.base_url,
            agent_id=self.agent_id,
            api_key=self.api_key
        )

        self.log_tail = LogTail(self.config.get('watch', {}).get('log_files', []))
        self.log_buffer = []

    def run(self):
        """Main agent loop"""
        self.running = True
        heartbeat_interval = self.config['intervals'].get('heartbeat_sec', 10)
        pull_interval = self.config['intervals'].get('pull_sec', 10)
        logs_interval = self.config['intervals'].get('logs_sec', 15)

        last_heartbeat = 0
        last_pull = 0
        last_logs = 0

        while self.running:
            now = time.time()

            # 1. Send heartbeat
            if now - last_heartbeat >= heartbeat_interval:
                self._send_heartbeat()
                last_heartbeat = now

            # 2. Check logs
            if now - last_logs >= logs_interval:
                self._collect_logs()
                last_logs = now

            # 3. Send logs if buffer has entries
            if self.log_buffer:
                self._send_logs()

            # 4. Pull commands
            if now - last_pull >= pull_interval:
                self._pull_and_execute_commands()
                last_pull = now

            time.sleep(1)  # Brief sleep to avoid busy-wait

    def stop(self):
        """Graceful shutdown"""
        self.running = False
        # Send final logs
        if self.log_buffer:
            self._send_logs()

    def _send_heartbeat(self):
        """Send heartbeat with system metrics"""
        try:
            metrics = collect_metrics(self.config)
            payload = {
                'platform': self.config['platform'],  # windows, macos
                'version': self.config.get('version', '1.0'),
                'metrics': metrics
            }
            response = self.client.post('/agent/heartbeat', payload)
            logging.info(f"Heartbeat sent: {response}")
        except Exception as e:
            logging.error(f"Heartbeat failed: {e}")
            self._on_communication_failure()

    def _collect_logs(self):
        """Collect new log entries from monitored files"""
        new_entries = self.log_tail.get_new_entries()
        for entry in new_entries:
            self.log_buffer.append({
                'ts': entry['ts'],
                'level': entry['level'],
                'code': entry['code'],
                'msg': entry['msg'],
                'meta': entry.get('meta', {})
            })

    def _send_logs(self):
        """Send buffered logs to server"""
        try:
            payload = {'logs': self.log_buffer}
            response = self.client.post('/agent/logs', payload)
            logging.info(f"Logs sent: {len(self.log_buffer)} entries")
            self.log_buffer = []
        except Exception as e:
            logging.error(f"Log send failed: {e}")
            # Keep buffer, retry next time

    def _pull_and_execute_commands(self):
        """Pull commands from server and execute"""
        try:
            response = self.client.get('/agent/pull')
            commands = response.get('commands', [])

            for cmd in commands:
                self._execute_command(cmd)
        except Exception as e:
            logging.error(f"Pull failed: {e}")

    def _execute_command(self, cmd):
        """Execute a single command"""
        cmd_id = cmd['id']
        cmd_type = cmd['type']
        payload = cmd.get('payload', {})

        try:
            # Validate against allowlist
            from security import validate_command
            valid, reason = validate_command(cmd_type, payload, self.config)

            if not valid:
                result = {'success': False, 'error': reason}
                self._report_command_result(cmd_id, 'failed', result)
                return

            # Check if control.apply_enabled
            if not self.config.get('control', {}).get('apply_enabled', False):
                if cmd_type not in ['SET_MODE']:  # Only safe modes don't need approval
                    result = {'success': False, 'error': 'Control execution disabled'}
                    self._report_command_result(cmd_id, 'failed', result)
                    return

            # Execute
            output = execute_command(cmd_type, payload, self.config)
            result = {'success': True, 'output': output}
            self._report_command_result(cmd_id, 'completed', result)

        except Exception as e:
            result = {'success': False, 'error': str(e)}
            self._report_command_result(cmd_id, 'failed', result)

    def _report_command_result(self, cmd_id, status, result):
        """Report command execution result to server"""
        try:
            payload = {
                'command_id': cmd_id,
                'status': status,
                'result': result
            }
            self.client.post('/agent/report', payload)
        except Exception as e:
            logging.error(f"Report failed: {e}")

    def _on_communication_failure(self):
        """Handle communication failure (exponential backoff)"""
        # Implement exponential backoff
        # Switch to SAFE mode if repeated failures
        pass


def main():
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'config.yaml'
    agent = RECOAgent(config_path)
    agent.run()


if __name__ == '__main__':
    main()
```

#### 2-2. Configuration Template
```yaml
# agent/common/config.example.yaml

base_url: "https://pea-reco3firstmodel.onrender.com"
agent_id: "agent-prod-001"
api_key: "YOUR_AGENT_API_KEY_HERE"
platform: "windows"  # or "macos"
version: "1.0"

control:
  apply_enabled: false  # Default: don't execute, only propose
  safe_modes: ["NORMAL", "SAFE"]
  whitelist_processes:
    - "nginx"
    - "apache2"
    - "postgresql"
    - "mysql"
    - "redis"

watch:
  processes:
    - name: "nginx"
      start_cmd: "net start nginx"        # Windows
      stop_cmd: "net stop nginx"
      restart_cmd: "net stop nginx && net start nginx"
      allow_restart: true

    - name: "postgresql"
      start_cmd: "pg_ctl -D C:/PostgreSQL/data start"
      stop_cmd: "pg_ctl -D C:/PostgreSQL/data stop"
      restart_cmd: "pg_ctl -D C:/PostgreSQL/data restart"
      allow_restart: false

  log_files:
    - "C:/nginx/logs/error.log"
    - "C:/PostgreSQL/data/postmaster.log"

intervals:
  heartbeat_sec: 10
  pull_sec: 10
  logs_sec: 15

logging:
  level: "INFO"
  file: "C:/reco3_agent/logs/agent.log"
  max_size_mb: 100
  backup_count: 5
```

#### 2-3. Dependencies
```txt
# agent/common/requirements-agent.txt

psutil==5.9.5
requests==2.31.0
pyyaml==6.0
watchdog==3.0.0
```

**期間**: 1-2週
**難易度**: 中
**チーム**: バックエンド1

---

### Phase 3-3: Windows Service 実装（1-2週）

**目標**: Windows で自動起動・常駐の Agent Service

**実装内容**:

#### 3-1. Service Class
```python
# agent/windows/reco3_agent_service.py

import win32serviceutil
import win32service
import win32event
import servicemanager
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.reco_agent import RECOAgent

class RECO3AgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "RECO3Agent"
    _svc_display_name_ = "RECO3 PC Agent"
    _svc_description_ = "Monitoring and control agent for RECO3"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.agent = None

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )

        # Start agent
        config_path = os.path.join(
            os.path.dirname(__file__),
            '..', 'common', 'config.yaml'
        )

        self.agent = RECOAgent(config_path)
        self.agent.run()

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)

        if self.agent:
            self.agent.stop()

        win32event.SetEvent(self.stop_event)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, '')
        )


if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(RECO3AgentService)
```

#### 3-2. Install Script (PowerShell)
```powershell
# agent/windows/install_service.ps1

param(
    [string]$ApiKey = "",
    [string]$BaseUrl = "https://pea-reco3firstmodel.onrender.com",
    [string]$AgentId = "agent-$(hostname)-$(Get-Random -Minimum 1000 -Maximum 9999)"
)

# Check if running as admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "Please run as Administrator"
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $projectDir "common"

# Create venv
Write-Host "Creating Python virtual environment..."
python -m venv "$projectDir\venv"

# Activate and install
Write-Host "Installing dependencies..."
& "$projectDir\venv\Scripts\pip" install -r "$commonDir\requirements-agent.txt"

# Create/update config.yaml
Write-Host "Creating config.yaml..."
$configContent = @"
base_url: "$BaseUrl"
agent_id: "$AgentId"
api_key: "$ApiKey"
platform: "windows"
version: "1.0"

control:
  apply_enabled: false

watch:
  log_files: []

intervals:
  heartbeat_sec: 10
  pull_sec: 10
  logs_sec: 15

logging:
  level: "INFO"
  file: "$projectDir\logs\agent.log"
"@

$configPath = Join-Path $commonDir "config.yaml"
Set-Content -Path $configPath -Value $configContent

# Install service
Write-Host "Installing Windows Service..."
& "$projectDir\venv\Scripts\python" "$scriptDir\reco3_agent_service.py" install
& "$projectDir\venv\Scripts\python" "$scriptDir\reco3_agent_service.py" start

Write-Host "✓ RECO3 Agent Service installed and started"
Write-Host "  Agent ID: $AgentId"
Write-Host "  Config: $configPath"
Write-Host "  Logs: $projectDir\logs\agent.log"
```

#### 3-3. Uninstall Script
```powershell
# agent/windows/uninstall_service.ps1

if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "Please run as Administrator"
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectDir = Split-Path -Parent $scriptDir

Write-Host "Stopping RECO3 Agent Service..."
& "$projectDir\venv\Scripts\python" "$scriptDir\reco3_agent_service.py" stop

Write-Host "Uninstalling service..."
& "$projectDir\venv\Scripts\python" "$scriptDir\reco3_agent_service.py" remove

Write-Host "✓ RECO3 Agent Service uninstalled"
```

**期間**: 1-2週
**難易度**: 中（Win32 API理解必須）
**チーム**: バックエンド1

---

### Phase 3-4: macOS launchd 実装（1週）

**目標**: macOS で自動起動・常駐の Agent

**実装内容**:

#### 4-1. launchd Plist
```xml
<!-- agent/macos/com.reco3.agent.plist -->

<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.reco3.agent</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/var/log/reco3-agent/output.log</string>

    <key>StandardErrorPath</key>
    <string>/var/log/reco3-agent/error.log</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/opt/reco3-agent/common/reco_agent.py</string>
        <string>/opt/reco3-agent/common/config.yaml</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/opt/reco3-agent</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
```

#### 4-2. Install Script
```bash
#!/bin/bash
# agent/macos/install_launchd.sh

set -e

API_KEY="${1:-}"
BASE_URL="${2:-https://pea-reco3firstmodel.onrender.com}"
AGENT_ID="${3:-agent-$(hostname)-$(od -An -tx1 /dev/urandom | head -1 | tr -d ' ')}"

if [ -z "$API_KEY" ]; then
    echo "Usage: $0 <API_KEY> [BASE_URL] [AGENT_ID]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMMON_DIR="$PROJECT_DIR/common"

echo "Installing RECO3 Agent on macOS..."

# Create installation directory
sudo mkdir -p /opt/reco3-agent
sudo cp -r "$PROJECT_DIR"/* /opt/reco3-agent/
sudo chown -R $(whoami) /opt/reco3-agent

# Create log directory
mkdir -p /var/log/reco3-agent
sudo chown $(whoami) /var/log/reco3-agent

# Create config
cat > "$COMMON_DIR/config.yaml" <<EOF
base_url: "$BASE_URL"
agent_id: "$AGENT_ID"
api_key: "$API_KEY"
platform: "macos"
version: "1.0"

control:
  apply_enabled: false

watch:
  processes: []
  log_files: []

intervals:
  heartbeat_sec: 10
  pull_sec: 10
  logs_sec: 15

logging:
  level: "INFO"
  file: "/var/log/reco3-agent/agent.log"
EOF

# Copy launchd plist
sudo cp "$SCRIPT_DIR/com.reco3.agent.plist" /Library/LaunchDaemons/com.reco3.agent.plist
sudo launchctl load /Library/LaunchDaemons/com.reco3.agent.plist
sudo launchctl start com.reco3.agent

echo "✓ RECO3 Agent installed and started"
echo "  Agent ID: $AGENT_ID"
echo "  Logs: /var/log/reco3-agent/agent.log"
```

**期間**: 1週
**難易度**: 低
**チーム**: バックエンド1

---

### Phase 3-5: PWA UI + テスト（1-2週）

**目標**: PWA に Agent 表示、E2E テスト、ドキュメント完成

**実装内容**:

#### 5-1. PWA (/r3) に Agent セクション追加
```html
<!-- templates/reco3.html に追加 -->

<section class="card">
  <h2>PC Agents</h2>
  <div style="overflow-x: auto">
    <table style="width: 100%; border-collapse: collapse;">
      <thead>
        <tr style="border-bottom: 2px solid #ddd;">
          <th style="padding: 8px; text-align: left;">Agent ID</th>
          <th style="padding: 8px; text-align: left;">Platform</th>
          <th style="padding: 8px; text-align: left;">Status</th>
          <th style="padding: 8px; text-align: left;">CPU / MEM</th>
          <th style="padding: 8px; text-align: left;">Last Error</th>
        </tr>
      </thead>
      <tbody id="agentsList"></tbody>
    </table>
  </div>
</section>
```

```javascript
// static/reco3.js に追加

async function loadAgents() {
  try {
    const res = await api('/api/agents', 'GET');
    showAgents(res.agents || []);
  } catch(e) {
    console.warn('loadAgents error:', e);
  }
}

function showAgents(agents) {
  const tbody = document.querySelector('#agentsList');
  if(!tbody) return;

  let html = '';
  for(const agent of agents) {
    const isOnline = (Date.now() - new Date(agent.last_seen).getTime()) < 30000;
    const status_badge = isOnline
      ? '<span style="background:#10B981;color:white;padding:2px 6px;border-radius:3px">ONLINE</span>'
      : '<span style="background:#EF4444;color:white;padding:2px 6px;border-radius:3px">OFFLINE</span>';

    const metrics = agent.payload_json ? JSON.parse(agent.payload_json) : {};
    const cpu_mem = `${Math.round(metrics.cpu_percent || 0)}% / ${Math.round(metrics.mem_percent || 0)}%`;

    html += `
      <tr style="border-bottom: 1px solid #eee;">
        <td style="padding: 8px;">${agent.agent_id}</td>
        <td style="padding: 8px;">${agent.platform}</td>
        <td style="padding: 8px;">${status_badge}</td>
        <td style="padding: 8px;">${cpu_mem}</td>
        <td style="padding: 8px; font-size: 12px; color: #666;">
          ${agent.last_error || '-'}
        </td>
      </tr>
    `;
  }

  tbody.innerHTML = html;
}

// Auto-refresh agents every 30 seconds
setInterval(loadAgents, 30000);
```

#### 5-2. テスト計画
```
1. ユニットテスト
  - Allowlist validation
  - Config parsing
  - Metrics collection

2. 統合テスト
  - Agent heartbeat → DB update
  - Agent logs → incident creation
  - Command pull → execution

3. E2E テスト
  - Windows: Install service → heartbeat verified → commands executed
  - macOS: Install launchd → heartbeat verified → logs captured
  - PWA: Agent status displayed, ONLINE/OFFLINE switches correctly

4. 負荷テスト
  - 100+ agents heartbeating
  - 1000+ logs/min handling
```

#### 5-3. ドキュメント更新
```
README.md:
  - "PC Agent は任意導入"を明確化
  - Windows/macOS インストール手順を大まかに記載
  - Quick Start に Agent セットアップ追加

agent/windows/README_windows.md:
  - PowerShell スクリプト実行手順
  - トラブルシューティング

agent/macos/README_macos.md:
  - Bash スクリプト実行手順
  - M1/Intel 対応
  - トラブルシューティング

/spec, /tech, /b2b:
  - Agent API 仕様追加
  - Allowlist / Security 説明
  - 段階導入（SET_MODE）の説明
```

**期間**: 1-2週
**難易度**: 低-中
**チーム**: フロントエンド0.5 + ドキュメント0.5

---

## 📊 統合テスト計画

### E2E フロー
```
1. Windows Agent インストール
   ↓
2. Service 自動起動
   ↓
3. Heartbeat 送信（10秒周期）
   ↓
4. Server: /agent/heartbeat 受信 → agent_status 更新
   ↓
5. PWA (/r3): Agent ONLINE 表示
   ↓
6. PWA: Command 実行要求（e.g., "SET_MODE SAFE"）
   ↓
7. Server: /agent/pull から Agent が取得
   ↓
8. Agent: Command 実行（allowlist チェック）
   ↓
9. Agent: /agent/report で結果報告
   ↓
10. PWA: 実行結果を表示
```

---

## ⚠️ "止めない"原則の実装

```python
# デフォルト設定（config.yaml）
control:
  apply_enabled: false  # ← 実行禁止！

# 許可されたコマンド（初期段階）
ALLOWED_COMMANDS = {
    'SET_MODE': {
        'modes': ['NORMAL', 'SAFE'],  # Safe mode のみOK
        'requires_approval': False,    # 安全だからOK
    },
    'NOTIFY_OPS': {
        'requires_approval': False,    # 通知のみOK
    },
    # 強い操作は v2 で検討
    # 'RESTART_PROCESS': {...},  # TODO
}
```

---

## 📈 実装進度（予定）

| フェーズ | 期間 | 進度 |
|---------|------|------|
| 3-1: Server API + DB | 1-2週 | ████░░░░░░ |
| 3-2: Agent 共通実装 | 1-2週 | ░░░░░░░░░░ |
| 3-3: Windows Service | 1-2週 | ░░░░░░░░░░ |
| 3-4: macOS launchd | 1週 | ░░░░░░░░░░ |
| 3-5: PWA UI + テスト | 1-2週 | ░░░░░░░░░░ |
| **合計** | **6-9週** | - |

---

## 🎯 完了条件（MVP）

- [x] Server API (heartbeat/logs/pull) が動作
- [x] Windows Agent が Service として常駐
- [x] macOS Agent が launchd で常駐
- [x] PWA に Agent ONLINE/OFFLINE が表示される
- [x] 自動実行はデフォルト OFF
- [x] allowlist のみ実行可能
- [x] 全操作が audit_log に記録される

---

## 🔜 次ステップ

1. **Server API (Phase 3-1)** の実装開始
2. **Agent 共通コード** の並行開発
3. **Windows + macOS** の段階的統合
4. **E2E テスト** で検証

