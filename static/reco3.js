let lastSession = null;
let lastDomain = "general";

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

  // ルール1: health チェック
  if(status && status.active_health !== 'ok'){
    action = 'SAFE_MODE';
    reason = 'health:' + (status.active_health || 'unknown');
  }

  // ルール2: ログに警告/エラーがあるか
  if(logs && Array.isArray(logs)){
    const recentLogs = logs.slice(-10);
    for(const log of recentLogs){
      const logText = JSON.stringify(log).toUpperCase();
      if(logText.includes('ALERT') || logText.includes('DENY') || logText.includes('ERROR')){
        action = 'TRIGGER_CHAT';
        reason = 'found:' + (log.level || 'ALERT');
        break;
      }
    }
  }

  if(action !== 'none'){
    lastAction = action;
    updateAutoMonitorUI();
    if(action === 'TRIGGER_CHAT'){
      triggerChat(reason);
    }else if(action === 'SAFE_MODE'){
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
  el.innerHTML = `
    <div class="autoStatus">
      <span class="badge ${autoRunning ? 'on' : 'off'}">Auto: ${autoRunning ? 'ON' : 'OFF'}</span>
      <span class="badge">Status: ${lastStatusTime || '--'}</span>
      <span class="badge">Logs: ${lastLogsTime || '--'}</span>
      <span class="badge">Action: ${lastAction}</span>
      <span class="badge fail" style="${failureCount > 0 ? '' : 'display:none'}">Fail: ${failureCount}</span>
    </div>
  `;
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

document.addEventListener('DOMContentLoaded', ()=>{
  addMsg('assistant', 'RECO3 ready.');
  autoStart();
});
