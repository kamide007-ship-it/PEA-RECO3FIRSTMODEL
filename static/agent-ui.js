// RECO3 PWA - Agent & Command Management Module
// Real-time agent monitoring, command queue, approvals

let g_testMode = false;
let g_requireApproval = false;
let g_selectedAgent = null;

// ── Test Mode Configuration ────────────────────────────────
async function loadTestModeConfig() {
  try {
    const res = await fetch('/api/config/test-mode');
    const data = await res.json();
    g_testMode = data.test_mode;
    g_requireApproval = data.require_approval;

    // Show test mode badge
    const badge = document.getElementById('testModeBadge');
    if (g_testMode) {
      badge.innerHTML = '<span style="background:#EF4444;color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">TEST MODE</span>';
    }

    // Show test controls if test mode
    const testCtrl = document.getElementById('testControls');
    if (testCtrl && g_testMode) {
      testCtrl.style.display = 'block';
    }
  } catch (e) {
    console.warn('Failed to load test mode config:', e);
  }
}

// ── PC Agents ──────────────────────────────────────────────
async function loadAgents() {
  try {
    const res = await api('/api/r3/agents', 'GET');
    showAgents(res.agents || []);
  } catch (e) {
    console.warn('Load agents error:', e);
    document.getElementById('agentsList').innerHTML = '<p style="color:var(--muted)">No agents (offline)</p>';
  }
}

function showAgents(agents) {
  const el = document.getElementById('agentsList');

  if (!agents || agents.length === 0) {
    el.innerHTML = '<p style="color:var(--muted)">No agents connected</p>';
    document.getElementById('agentMetrics').innerHTML = '<p style="color:var(--muted)">-</p>';
    document.getElementById('agentLogsList').innerHTML = '<p style="color:var(--muted)">-</p>';
    document.getElementById('commandQueue').innerHTML = '<p style="color:var(--muted)">-</p>';
    return;
  }

  let html = '<table style="width:100%;border-collapse:collapse;">';
  html += '<thead><tr style="border-bottom:2px solid var(--border);">';
  html += '<th style="padding:8px;text-align:left">Agent</th>';
  html += '<th style="padding:8px;text-align:left">Status</th>';
  html += '<th style="padding:8px;text-align:left">Platform</th>';
  html += '<th style="padding:8px;text-align:left">CPU/MEM</th>';
  html += '<th style="padding:8px;text-align:left">Last Error</th>';
  html += '</tr></thead><tbody>';

  for (const agent of agents) {
    const now = Date.now();
    const lastSeen = new Date(agent.last_seen).getTime();
    const isOnline = (now - lastSeen) < 30000;

    const statusBadge = isOnline
      ? '<span style="background:#10B981;color:white;padding:2px 6px;border-radius:3px;font-size:11px">ONLINE</span>'
      : '<span style="background:#EF4444;color:white;padding:2px 6px;border-radius:3px;font-size:11px">OFFLINE</span>';

    let metrics = {};
    try {
      metrics = agent.payload_json ? JSON.parse(agent.payload_json) : {};
    } catch (e) {}

    const cpuMem = `${Math.round(metrics.cpu_percent || 0)}%/${Math.round(metrics.mem_percent || 0)}%`;
    const lastErr = agent.last_error ? agent.last_error.substring(0, 40) : '-';

    html += `<tr style="border-bottom:1px solid var(--border);cursor:pointer" onclick="selectAgent('${agent.agent_id}')">`;
    html += `<td style="padding:8px">${agent.agent_id}</td>`;
    html += `<td style="padding:8px">${statusBadge}</td>`;
    html += `<td style="padding:8px;font-size:12px">${agent.platform}</td>`;
    html += `<td style="padding:8px;font-size:12px">${cpuMem}</td>`;
    html += `<td style="padding:8px;font-size:12px;color:#666">${lastErr}</td>`;
    html += `</tr>`;
  }
  html += '</tbody></table>';
  el.innerHTML = html;

  // Load metrics for first agent
  if (agents.length > 0) {
    selectAgent(agents[0].agent_id);
  }
}

function selectAgent(agentId) {
  g_selectedAgent = agentId;
  loadAgentMetrics(agentId);
  loadAgentLogs(agentId);
  loadCommandQueue(agentId);
}

async function loadAgentMetrics(agentId) {
  try {
    const res = await api('/api/r3/agents', 'GET');
    const agent = (res.agents || []).find(a => a.agent_id === agentId);
    if (!agent) {
      document.getElementById('agentMetrics').innerHTML = '<p style="color:var(--muted)">Agent not found</p>';
      return;
    }

    let metrics = {};
    try {
      metrics = agent.payload_json ? JSON.parse(agent.payload_json) : {};
    } catch (e) {}

    let html = '<div class="kv">';
    html += `<div class="k">Agent ID:</div><div>${agent.agent_id}</div>`;
    html += `<div class="k">CPU:</div><div>${Math.round(metrics.cpu_percent || 0)}%</div>`;
    html += `<div class="k">Memory:</div><div>${Math.round(metrics.mem_percent || 0)}%</div>`;
    html += `<div class="k">Disk:</div><div>${Math.round(metrics.disk_percent || 0)}%</div>`;
    html += `<div class="k">Mode:</div><div>${metrics.mode || 'NORMAL'}</div>`;
    html += `<div class="k">Platform:</div><div>${agent.platform}</div>`;
    html += `<div class="k">Last Seen:</div><div style="font-size:12px">${new Date(agent.last_seen).toLocaleString()}</div>`;
    html += '</div>';
    document.getElementById('agentMetrics').innerHTML = html;
  } catch (e) {
    console.warn('Load metrics error:', e);
  }
}

async function loadAgentLogs(agentId) {
  try {
    const res = await api(`/api/r3/agent/${agentId}/logs?limit=50`, 'GET');
    const logs = res.logs || [];

    if (logs.length === 0) {
      document.getElementById('agentLogsList').innerHTML = '<p style="color:var(--muted);font-size:12px">No logs</p>';
      return;
    }

    let html = '';
    for (const log of logs.slice(0, 20)) {
      const level = log.level || 'INFO';
      const levelColor = level === 'ERROR' ? '#DC2626' : level === 'WARN' ? '#F59E0B' : '#666';
      const ts = new Date(log.ts).toLocaleTimeString();
      html += `<div style="padding:6px;border-bottom:1px solid var(--border);font-size:11px">`;
      html += `<span style="color:${levelColor};font-weight:600">${level}</span> `;
      html += `<span style="color:var(--muted)">${ts}</span> `;
      html += `<span>${log.msg}</span>`;
      html += `</div>`;
    }
    document.getElementById('agentLogsList').innerHTML = html;

    // Notify on errors
    const errors = logs.filter(l => l.level === 'ERROR' || l.level === 'CRITICAL');
    if (errors.length > 0) {
      notify('error', 'Agent Error', `${errors.length} error(s) from agent ${agentId}`);
    }
  } catch (e) {
    console.warn('Load logs error:', e);
  }
}

async function loadCommandQueue(agentId) {
  try {
    const res = await api(`/api/agent-commands?agent_id=${agentId}`, 'GET');
    const commands = res.commands || [];

    if (commands.length === 0) {
      document.getElementById('commandQueue').innerHTML = '<p style="color:var(--muted);font-size:12px">No commands</p>';
      return;
    }

    let html = '';
    for (const cmd of commands) {
      const statusColor =
        cmd.status === 'pending' ? '#F59E0B' :
        cmd.status === 'completed' ? '#10B981' :
        cmd.status === 'failed' ? '#DC2626' :
        '#6B7280';

      let payload = cmd.payload_json;
      if (typeof payload === 'string') {
        try { payload = JSON.parse(payload); } catch (e) {}
      }

      html += `<div style="padding:8px;border:1px solid var(--border);border-radius:4px;margin-bottom:8px">`;
      html += `<div style="font-weight:600;font-size:13px">`;
      html += `${cmd.type} `;
      html += `<span style="background:${statusColor};color:white;padding:1px 6px;border-radius:2px;font-size:11px;font-weight:normal">${cmd.status}</span>`;
      html += `</div>`;

      if (payload && Object.keys(payload).length > 0) {
        html += `<div style="font-size:11px;color:var(--muted);margin-top:4px">`;
        html += JSON.stringify(payload).substring(0, 80);
        html += `</div>`;
      }

      // Approval button for pending strong commands
      if (cmd.status === 'pending' && cmd.needs_approval && !cmd.approved) {
        html += `<button class="btn" style="background:#3B82F6;color:white;border:none;padding:4px 8px;border-radius:3px;cursor:pointer;font-size:11px;margin-top:6px" onclick="approveCommand('${cmd.id}')">Approve</button>`;
      }

      html += `</div>`;
    }
    document.getElementById('commandQueue').innerHTML = html;

    // Notify on pending approvals
    const pendingApprovals = commands.filter(c => c.status === 'pending' && c.needs_approval && !c.approved);
    if (pendingApprovals.length > 0) {
      notify('warn', 'Approval Needed', `${pendingApprovals.length} command(s) waiting for approval`);
    }
  } catch (e) {
    console.warn('Load commands error:', e);
  }
}

async function approveCommand(cmdId) {
  try {
    await api(`/api/agent-commands/${cmdId}/approve`, 'POST', { approved_by: 'admin' });
    notify('info', 'Approved', 'Command approved');
    if (g_selectedAgent) {
      loadCommandQueue(g_selectedAgent);
    }
  } catch (e) {
    notify('error', 'Approval Failed', String(e));
  }
}

async function sendTestCmd(cmdType, payload) {
  if (!g_selectedAgent) {
    notify('error', 'Error', 'No agent selected');
    return;
  }

  try {
    const res = await api('/api/agent-commands', 'POST', {
      agent_id: g_selectedAgent,
      type: cmdType,
      payload: payload,
    });
    notify('info', 'Command Sent', `${cmdType} sent to ${g_selectedAgent}`);
    loadCommandQueue(g_selectedAgent);
  } catch (e) {
    notify('error', 'Error', String(e));
  }
}

// ── Auto-refresh Agent Data ────────────────────────────────
function startAgentMonitoring() {
  loadTestModeConfig();
  loadAgents();
  setInterval(() => {
    loadAgents();
    if (g_selectedAgent) {
      loadAgentMetrics(g_selectedAgent);
      loadAgentLogs(g_selectedAgent);
      loadCommandQueue(g_selectedAgent);
    }
  }, 5000);  // Refresh every 5s
}
