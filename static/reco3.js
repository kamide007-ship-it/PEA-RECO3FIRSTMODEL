let lastSession = null;
let lastDomain = "general";

async function api(path, method='GET', body=null){
  const opt = {method, headers:{}};
  if(body!==null){
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  const t = await r.text();
  let j = null;
  try{ j = JSON.parse(t); }catch(e){ j = {raw:t}; }
  if(!r.ok) throw new Error(JSON.stringify(j));
  return j;
}

function addMsg(role, text){
  const chat = document.getElementById('chat');
  const d = document.createElement('div');
  d.className = 'msg ' + (role==='user' ? 'user' : 'assistant');
  d.textContent = text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
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
  const res = await api('/api/r3/chat', 'POST', {prompt: p, domain});
  addMsg('assistant', res.response || '');
  showInputAnalysis(res.input_analysis);
  showOutputAnalysis(res.output_analysis);
  showDetail(res);
}

async function doFb(kind){
  if(!lastSession) return;
  const map = {
    good: "ありがとう。",
    recalculate: "もういちど、ていねいにするね。",
    bad: "ごめんね。なおすね。"
  };
  addMsg('user', map[kind] || kind);
  const res = await api('/api/feedback', 'POST', {session_id: lastSession, domain: lastDomain, feedback: kind});
  addMsg('assistant', JSON.stringify(res));
}

document.addEventListener('DOMContentLoaded', ()=>{
  addMsg('assistant', 'RECO3 ready.');
});
