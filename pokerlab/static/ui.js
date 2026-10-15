'use strict';
let current = null, working = false;
const $ = id => document.getElementById(id);
const suit = {c:'♣',d:'♦',h:'♥',s:'♠'};
const streetName = {preflop:'PREFLOP',flop:'FLOP',turn:'TURN',river:'RIVER'};
const actionName = {fold:'FOLD / 降りる',check:'CHECK / チェック',call:'CALL / コール',raise:'RAISE / レイズ'};
const escapeHtml = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
function cardHtml(c) {
  if (c === '??') return '<div class="card back">♠</div>';
  if (c === '--') return '<div class="card blank"></div>';
  const red = c[1] === 'h' || c[1] === 'd';
  return `<div class="card ${red?'red':''}" aria-label="${escapeHtml(c)}">${escapeHtml(c[0])}<small>${suit[c[1]] ?? ''}</small></div>`;
}
function formatSigned(n) {return `${n>=0?'+':''}${n}`;}
function setButton(id, fn) { $(id).onclick = fn; }
async function request(path, data={}) {
  if (working) return;
  working = true;
  $('status').textContent = '';
  try {
    const res = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const parsed = await res.json();
    if (!res.ok) throw new Error(parsed.error || 'request failed');
    render(parsed);
  } catch (err) {$('status').textContent = err.message;}
  finally {working=false;}
}
function render(s) {
  current = s;
  $('hand-no').textContent = `#${s.hand_number}`;
  $('bot-position').textContent = s.button === 1?'SB / BUTTON':'BB';
  $('my-position').textContent = s.button === 0?'SB / BUTTON':'BB';
  $('bot-stack').textContent = s.stacks[1];
  $('my-stack').textContent = s.stacks[0];
  $('pot').textContent = s.pot;
  $('street').textContent = streetName[s.street];
  $('my-cards').innerHTML = s.you.map(cardHtml).join('');
  $('bot-cards').innerHTML = (s.opponent ?? ['??','??']).map(cardHtml).join('');
  $('board').innerHTML = [...s.board,...Array(5-s.board.length).fill('--')].map(cardHtml).join('');
  $('played').textContent = s.completed_hands;
  $('net').textContent = formatSigned(s.net_chips);
  $('net').className = s.net_chips>=0?'positive':'negative';
  $('recent').innerHTML = s.recent_hands.length ? s.recent_hands.map(h => `<div class="recent-row"><span>#${h.number} · ${h.reason==='showdown'?'ショーダウン':h.reason==='split'?'引き分け':'フォールド'}</span><strong class="${h.net_chips>=0?'positive':'negative'}">${formatSigned(h.net_chips)}</strong></div>`).join('') : '<span class="muted">まだ対戦履歴はありません。</span>';
  const acts = $('actions');
  acts.replaceChildren();
  $('raise-tools').hidden = true;
  $('new-hand').hidden = !s.finished;
  $('to-call').textContent = '';
  if (s.finished) {
    const outcome = s.winner === null?'引き分け':s.winner === 0?'このハンドはあなたの勝ち！':'このハンドはAIの勝ち';
    $('message').textContent = outcome + (s.showdown_hand ? ` / あなた: ${s.showdown_hand[0]} · AI: ${s.showdown_hand[1]}` : '');
  } else if (s.to_act === 0) {
    $('message').textContent = 'あなたのアクションを選択';
    if (s.legal.to_call > 0) $('to-call').textContent = `CALL ${s.legal.to_call} CHIPS`;
    for (const kind of s.legal.actions) {
      const btn = document.createElement('button');
      btn.textContent = actionName[kind];
      if (kind==='fold') btn.className='fold';
      if (kind==='raise') btn.className='primary';
      btn.onclick = () => kind==='raise' ? showRaise() : request('/api/action',{kind});
      acts.append(btn);
    }
  } else {
    $('message').textContent = 'AIのターン';
  }
  $('coach').innerHTML = s.decisions.length ? s.decisions.map((d,i)=>{
    const eq = `${(d.equity*100).toFixed(1)}%`;
    const odds = d.pot_odds===null?'—':`${(d.pot_odds*100).toFixed(1)}%`;
    const ev = d.call_ev===null?'—':`${d.call_ev>=0?'+':''}${d.call_ev.toFixed(1)}`;
    return `<div class="decision"><div class="decision-top"><strong>${i+1}. ${streetName[d.street]} · ${escapeHtml(d.choice.toUpperCase())}</strong><span class="tag">RANDOM RANGE</span></div><div class="decision-metrics"><div class="metric"><label>エクイティ</label><strong>${eq}</strong></div><div class="metric"><label>コール必要率</label><strong>${odds}</strong></div><div class="metric"><label>単純コールEV</label><strong>${ev}</strong></div></div><p>${escapeHtml(d.note)}</p></div>`;
  }).join('') : '<span class="muted">アクションを選ぶと解析が表示されます。</span>';
  $('log-body').innerHTML = s.actions.length ? s.actions.slice().reverse().map(a => `<div class="log-row"><span>${streetName[a.street]} · ${a.actor===0?'YOU':'AI'}</span><strong>${escapeHtml(a.kind.toUpperCase())}${a.amount?` +${a.amount}`:''}</strong></div>`).join('') : '<span class="muted">まだアクションはありません。</span>';
}
function showRaise(){
  const l=current.legal;
  if (!l || !l.min_raise_to) return;
  $('raise-tools').hidden=false;
  $('raise-slider').min=l.min_raise_to;
  $('raise-slider').max=l.max_raise_to;
  $('raise-slider').value=l.min_raise_to;
  $('raise-min').textContent=`MIN ${l.min_raise_to}`;
  $('raise-max').textContent=`MAX ${l.max_raise_to} (実効オールイン)`;
  updateRaise();
}
function updateRaise(){$('raise-amount').textContent=$('raise-slider').value;}
$('raise-slider').addEventListener('input',updateRaise);
setButton('raise-submit',()=>request('/api/action',{kind:'raise',raise_to:Number($('raise-slider').value)}));
setButton('new-hand',()=>request('/api/new'));
setButton('reset',()=>{if (confirm('対戦成績をリセットしますか？')) request('/api/reset');});
fetch('/api/state').then(r=>r.json()).then(render).catch(e=>{$('status').textContent=`初期化に失敗しました: ${e.message}`;});
