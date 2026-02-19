let lastSession = null;
let lastDomain = "general";

// ═══ Toast Notification ══════════════════════════════════════════
const _toastCooldowns = {};
const TOAST_DURATION = 6000;     // 6秒
const TOAST_COOLDOWN = 60000;    // 同一key 60秒

function notify(level, title, message, key){
  if(key){
    const now = Date.now();
    const last = _toastCooldowns[key] || 0;
    if(now - last < TOAST_COOLDOWN) return;
    _toastCooldowns[key] = now;
  }
  const root = document.getElementById('toast-root');
  if(!root) return;
  const el = document.createElement('div');
  el.className = 'toast toast-' + (level || 'info');
  el.innerHTML = `<div class="toast-title">${title||''}</div><div class="toast-msg">${message||''}</div>`;
  root.appendChild(el);
  setTimeout(()=>{
    el.classList.add('out');
    setTimeout(()=>el.remove(), 250);
  }, TOAST_DURATION);
}

// ═══ Auto Monitor/Control Loop ═══════════════════════════════════
let autoRunning = false;
let statusPollTimer = null;
let logsPollTimer = null;
let lastStatusTime = null;
let lastLogsTime = null;
let lastAction = "none";
let failureCount = 0;
let lastTriggerTime = 0;
const TRIGGER_COOLDOWN = 60000;  // 60秒
const POLL_STATUS_INTERVAL = 3000;  // 3秒
const POLL_LOGS_INTERVAL = 7000;  // 7秒
let inFlightRequest = false;

async function pollStatus(){
  try{
    const res = await api('/api/status', 'GET');
    lastStatusTime = new Date().toLocaleTimeString('ja-JP');
    evaluateAndAct(res, null);
  }catch(e){
    console.warn('pollStatus error:', e);
  }
}

async function pollLogs(){
  try{
    const res = await api('/api/logs?limit=20', 'GET');
    lastLogsTime = new Date().toLocaleTimeString('ja-JP');
    evaluateAndAct(null, res);
  }catch(e){
    console.warn('pollLogs error:', e);
  }
}

function evaluateAndAct(status, logs){
  if(!autoRunning) return;

  let action = 'none';
  let reason = '';

  // ルール1: LLM接続チェック（adapter/model が取得できない = 異常）
  if(status){
    const adapter = status.active_llm_adapter || '';
    const model = status.active_llm_model || '';
    if(adapter === 'unknown' || model === 'unknown'){
      action = 'SAFE_MODE';
      reason = 'llm:' + adapter + '/' + model;
    }
    // API鍵がどちらも無い場合も危険
    const dk = status.dual_keys || {};
    if(!dk.has_openai_key && !dk.has_anthropic_key){
      action = 'SAFE_MODE';
      reason = 'no_api_keys';
    }
  }

  // ルール2: ログの verdict が "suspect" なら自動トリガ
  if(logs && Array.isArray(logs)){
    const recent = logs.slice(0, 10); // get_logs は降順（最新が先頭）
    let suspectCount = 0;
    for(const entry of recent){
      if(entry.verdict === 'suspect'){
        suspectCount++;
      }
    }
    // 直近10件中3件以上 suspect → 異常検知
    if(suspectCount >= 3){
      action = 'TRIGGER_CHAT';
      reason = 'suspect:' + suspectCount + '/10';
    }
  }

  if(action !== 'none'){
    lastAction = action;
    updateAutoMonitorUI();
    if(action === 'TRIGGER_CHAT'){
      notify('warn', 'Anomaly Detected', reason, 'trigger:'+reason);
      triggerChat(reason);
    }else if(action === 'SAFE_MODE'){
      notify('error', 'Safe Mode', reason, 'safe:'+reason);
      console.log('[AUTO] SAFE_MODE triggered:', reason);
    }
  }
}

async function triggerChat(reason){
  if(!autoRunning) return;
  if(inFlightRequest) return;  // ガード: 同時実行防止

  const now = Date.now();
  if(now - lastTriggerTime < TRIGGER_COOLDOWN){
    console.log('[AUTO] Cooldown active. Skip trigger.');
    return;
  }

  inFlightRequest = true;
  try{
    const prompt = `[AUTO TRIGGER] Reason: ${reason}. Analyze and respond.`;
    const res = await api('/api/r3/chat', 'POST', {prompt, domain: 'monitor'});
    addMsg('assistant', '[AUTO] ' + (res.response || 'no response'));
    lastTriggerTime = now;
    failureCount = 0;  // リセット
    lastAction = 'TRIGGER_CHAT:success';
  }catch(e){
    failureCount++;
    console.error('[AUTO] trigger failed (count=' + failureCount + '):', e);
    if(failureCount >= 3){
      console.warn('[AUTO] Failure count >= 3. Stopping auto mode.');
      autoStop();
    }
    lastAction = 'TRIGGER_CHAT:fail(' + failureCount + ')';
  }finally{
    inFlightRequest = false;
    updateAutoMonitorUI();
  }
}

function autoStart(){
  if(autoRunning) return;
  autoRunning = true;
  failureCount = 0;
  lastTriggerTime = 0;
  addMsg('assistant', '🤖 Auto monitor started.');

  statusPollTimer = setInterval(pollStatus, POLL_STATUS_INTERVAL);
  logsPollTimer = setInterval(pollLogs, POLL_LOGS_INTERVAL);

  // Initial poll
  pollStatus();
  pollLogs();

  updateAutoMonitorUI();
}

function autoStop(){
  if(!autoRunning) return;
  autoRunning = false;
  if(statusPollTimer) clearInterval(statusPollTimer);
  if(logsPollTimer) clearInterval(logsPollTimer);
  addMsg('assistant', '⏹️ Auto monitor stopped.');
  updateAutoMonitorUI();
}

function updateAutoMonitorUI(){
  const el = document.getElementById('autoMonitor');
  if(!el) return;
  let pillClass, pillLabel;
  if(lastAction.startsWith('SAFE')){
    pillClass = 'safe'; pillLabel = 'SAFE MODE';
  } else if(autoRunning){
    pillClass = 'running'; pillLabel = 'RUNNING';
  } else {
    pillClass = 'stopped'; pillLabel = 'STOPPED';
  }
  const extra = failureCount > 0 ? ` <span style="color:#DC2626;font-size:11px">F${failureCount}</span>` : '';
  el.innerHTML = `<span class="statusPill ${pillClass}">${pillLabel}</span>${extra}`;
}

async function api(path, method='GET', body=null){
  const opt = {method, headers:{}, credentials: 'include'};
  if(body!==null){
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  try {
    const r = await fetch(path, opt);
    const t = await r.text();
    let j = null;
    try{ j = JSON.parse(t); }catch(e){ j = {raw:t}; }
    if(!r.ok) {
      if(r.status === 401) {
        const msg = 'セッション切れ。ページを再読み込みしてください。';
        showError(msg);
        notify('error', 'Session Expired', msg, 'auth:401');
        if(autoRunning) autoStop();  // ← 自動停止
      }
      throw new Error(JSON.stringify(j));
    }
    return j;
  } catch(e) {
    if(e.message.includes('401') || e.message.includes('unauthorized')) {
      if(autoRunning) autoStop();
    }
    throw e;
  }
}

function addMsg(role, text){
  const chat = document.getElementById('chat');
  const d = document.createElement('div');
  d.className = 'msg ' + (role==='user' ? 'user' : 'assistant');
  d.textContent = text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
}

function showError(msg){
  const chat = document.getElementById('chat');
  const d = document.createElement('div');
  d.className = 'msg error';
  d.textContent = '⚠️ ' + msg;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
  console.error(msg);
}

function bar(name, v){
  const pct = Math.max(0, Math.min(100, Math.round((v||0)*100)));
  return `
  <div class="barRow">
    <div class="barLabel"><span>${name}</span><span>${pct}%</span></div>
    <div class="bar"><div class="fill" style="width:${pct}%;"></div></div>
  </div>`;
}

function showInputAnalysis(a){
  const el = document.getElementById('inBars');
  if(!a){ el.innerHTML=''; return; }
  const s = a.scores || {};
  el.innerHTML =
    bar('曖昧度', s.ambiguity) +
    bar('断定要求', s.assertion_demand) +
    bar('感情圧力', s.emotional_pressure) +
    bar('非現実前提', s.unrealistic) +
    `<div class="row"><span class="badge">risk: ${a.risk_level}</span><span class="badge">preD: ${a.pre_d}</span></div>`;
}

function showOutputAnalysis(a){
  const el = document.getElementById('outBars');
  if(!a){ el.innerHTML=''; return; }
  const s = a.scores || {};
  el.innerHTML =
    bar('断定密度', s.assertion_density) +
    bar('エビデンス不足', s.evidence_gap) +
    bar('内部矛盾', s.contradiction) +
    bar('煽り', s.provocative) +
    `<div class="row"><span class="badge">level: ${a.level}</span><span class="badge">postD: ${a.post_d}</span><span class="badge">ψmod: ${a.psi_modifier}</span></div>`;
}

function showDetail(r){
  const el = document.getElementById('detail');
  if(!r){ el.innerHTML=''; return; }
  lastSession = r.session_id;
  lastDomain = document.getElementById('domain').value || 'general';
  const rows = [
    ['session_id', r.session_id],
    ['temperature_used', r.temperature_used],
    ['regenerated', r.regenerated],
    ['attempts', r.attempts],
    ['llm_model', r.llm_model],
    ['annotated', r.annotated],
  ];
  el.innerHTML = rows.map(([k,v])=>`<div class="k">${k}</div><div>${v}</div>`).join('');
  document.getElementById('bridge').textContent = JSON.stringify(r.reco2_evaluation, null, 2);
}

async function doSend(){
  const p = document.getElementById('prompt').value;
  const domain = document.getElementById('domain').value || 'general';
  addMsg('user', p);
  try {
    const res = await api('/api/r3/chat', 'POST', {prompt: p, domain});
    addMsg('assistant', res.response || '');
    showInputAnalysis(res.input_analysis);
    showOutputAnalysis(res.output_analysis);
    showDetail(res);
  } catch(e) {
    console.error('Error:', e);
  }
}

async function doFb(kind){
  if(!lastSession) return;
  const map = {
    good: "ありがとう。",
    recalculate: "もういちど、ていねいにするね。",
    bad: "ごめんね。なおすね。"
  };
  addMsg('user', map[kind] || kind);
  try {
    const res = await api('/api/feedback', 'POST', {session_id: lastSession, domain: lastDomain, feedback: kind});
    addMsg('assistant', JSON.stringify(res));
  } catch(e) {
    console.error('Error:', e);
  }
}

// ═══ System Monitor ══════════════════════════════════════════════
let sysPollTimer = null;
const SYS_POLL_INTERVAL = 10000; // 10秒

async function pollSystem(){
  try{
    const res = await api('/api/system', 'GET');
    showSystemMetrics(res.metrics, res.health);
  }catch(e){
    console.warn('pollSystem error:', e);
  }
}

function showSystemMetrics(m, h){
  const el = document.getElementById('sysMetrics');
  if(!el || !m) return;
  const rows = [
    ['CPU', m.cpu_percent + '%'],
    ['Memory', m.mem_used_mb + ' / ' + m.mem_total_mb + ' MB (' + m.mem_percent + '%)'],
    ['Disk', m.disk_used_gb + ' / ' + m.disk_total_gb + ' GB (' + m.disk_percent + '%)'],
    ['Load', m.load_1m + ' / ' + m.load_5m + ' / ' + m.load_15m],
    ['Platform', m.platform + ' / Python ' + m.python],
  ];
  el.innerHTML = rows.map(([k,v])=>`<div class="k">${k}</div><div>${v}</div>`).join('');

  const hEl = document.getElementById('sysHealth');
  if(!hEl || !h) return;
  if(h.status === 'ok'){
    hEl.innerHTML = '<span class="badge" style="color:#16A34A">OK</span>';
  } else {
    const alerts = (h.alerts||[]).map(a=>`<span class="badge" style="color:${a.level==='critical'?'#DC2626':'#D97706'}">${a.msg}</span>`).join(' ');
    hEl.innerHTML = alerts;
    if(h.status === 'critical'){
      notify('error', 'System Critical', (h.alerts||[]).map(a=>a.msg).join(', '), 'sys:critical');
    } else if(h.status === 'warning'){
      notify('warn', 'System Warning', (h.alerts||[]).map(a=>a.msg).join(', '), 'sys:warning');
    }
  }
}

document.addEventListener('DOMContentLoaded', ()=>{
  addMsg('assistant', 'RECO3 ready.');
  autoStart();
  pollSystem();
  sysPollTimer = setInterval(pollSystem, SYS_POLL_INTERVAL);
});
