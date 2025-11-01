// pH Control UI
(function(){
  const POLL_DEFAULT = 5000;
  let pollMs = POLL_DEFAULT;
  let pollTimer = null;
  let lastStatus = null;
  let countdownTimer = null;
  let lastPollAt = Date.now();
  let chart, chartMode = '24h'; // '24h' | '7d'

  function el(id){ return document.getElementById(id); }

  async function fetchStatus(){
    try{
      const r = await fetch('/api/ph/status', {cache: 'no-store'});
      if(!r.ok) throw new Error('status');
      return await r.json();
    }catch(e){ return null; }
  }

  function guardActive(g){
    if(!g) return false;
    return g.estop || g.safe_off || g.sensor_stale || g.interval || g.daily_cap || g.reservoir;
  }

  function guardList(g){
    const out = [];
    if(g.estop) out.push('E-STOP');
    if(g.safe_off) out.push('SAFE-OFF');
    if(g.sensor_stale) out.push('Sensor stale');
    if(g.interval) out.push('Min interval');
    if(g.daily_cap) out.push('Daily cap');
    if(g.reservoir) out.push('Reservoir');
    return out;
  }

  function guardHints(g){
    const tips = [];
    if(g.estop) tips.push('E-STOP: Emergency stop is active; all dosing blocked.');
    if(g.safe_off) tips.push('SAFE-OFF: System is in safe-off mode.');
    if(g.sensor_stale) tips.push('Sensor stale: pH reading is older than 90s.');
    if(g.interval) tips.push(`Min interval: Waiting between doses. (${g.since_last_ok_s ?? '?'}s/${g.min_interval_s ?? '?'}s)`);
    if(g.daily_cap) tips.push(`Daily cap reached: Max per day is ${g.daily_cap_ml ?? '?'} ml.`);
    if(g.reservoir) tips.push('Reservoir set to 0 L; dosing disabled.');
    return tips.join('\n');
  }

  function renderStatus(s){
    lastStatus = s;
    lastPollAt = Date.now();
    const p = el('ph-current');
    const band = el('ph-band');
    const guards = el('ph-guards');
    const recent = el('ph-recent');
    const resBanner = el('ph-reservoir-banner');
    const cdPill = el('ph-countdown-pill');
    if(p){ p.textContent = (s && s.ph!=null) ? s.ph.toFixed(2) : '—'; }
    if(band && s){ band.textContent = `Targets ${s.targets.low} – ${s.targets.high}`; }
    if(guards && s){
      const list = guardList(s.guards);
      guards.textContent = list.length ? list.join(' · ') : 'All clear';
      guards.style.color = list.length ? '#f59e0b' : '#16a34a';
      guards.title = list.length ? guardHints(s.guards) : '';
    }
    if(resBanner && s){ resBanner.style.display = s.guards?.reservoir ? 'block' : 'none'; }
    if(recent && s){
      recent.innerHTML = '';
      (s.recent||[]).forEach(r => {
        const li = document.createElement('div');
        li.className = 'muted';
        const when = r.ts_utc?.replace('T',' ').replace('Z','');
        li.textContent = `${when} • ${r.action} • ${r.volume_ml||''} ml • ${r.result}${r.reason? ' • '+r.reason: ''}`;
        recent.appendChild(li);
      });
    }
    const disabled = guardActive(s?.guards);
    ['btnPrime','btnDose1','btnDose5','btnDoseCustom','phCustomMl'].forEach(id=>{
      const e = el(id); if(e){ e.disabled = disabled; e.title = disabled ? 'Blocked by guard(s)' : ''; }
    });

    // Countdown pill for min-interval
    if(cdPill){
      if(s?.guards?.interval){
        cdPill.style.display = 'inline-block';
        updateCountdownPill();
        startCountdown();
      } else {
        cdPill.style.display = 'none';
        stopCountdown();
      }
    }
  }

  async function tick(){
    const s = await fetchStatus();
    renderStatus(s||{});
  }

  function schedule(){
    if(pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(tick, pollMs);
  }

  function startCountdown(){
    if(countdownTimer) return;
    countdownTimer = setInterval(updateCountdownPill, 1000);
  }
  function stopCountdown(){
    if(countdownTimer){ clearInterval(countdownTimer); countdownTimer = null; }
  }
  function updateCountdownPill(){
    const cdPill = el('ph-countdown-pill');
    if(!cdPill || !lastStatus?.guards) return;
    const g = lastStatus.guards;
    if(!g.interval){ cdPill.style.display = 'none'; return; }
    // Estimate since_last_ok_s locally since last poll
    const elapsed = Math.floor((Date.now() - lastPollAt)/1000);
    const since = (g.since_last_ok_s ?? 0) + Math.max(0, elapsed);
    const need = Math.max(0, (g.min_interval_s ?? 0) - since);
    cdPill.textContent = `⏱ ${need}s`;
  }

  async function postDose(body){
    const r = await fetch('/api/ph/dose', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    let j = null; try{ j = await r.json(); }catch(e){}
    if(!r.ok){
      const reasons = (j?.reasons && Array.isArray(j.reasons)) ? j.reasons.join(', ') : null;
      const msg = j?.error || reasons || `HTTP ${r.status}`;
      if(window.showToast){ showToast(`Dose blocked: ${msg}`, 'error'); }
      else { alert('Dose blocked: ' + msg); }
    } else {
      // immediate refresh of status list
      if(window.showToast){ showToast('Dose started', 'success'); }
      tick();
    }
  }

  function wire(){
    const c = document.getElementById('ph-card');
    if(!c) return;
    el('btnPrime')?.addEventListener('click', ()=> postDose({ms:200, reason:'prime'}));
    el('btnDose1')?.addEventListener('click', ()=> postDose({ml:1, reason:'manual'}));
    el('btnDose5')?.addEventListener('click', ()=> postDose({ml:5, reason:'manual'}));
    el('btnDoseCustom')?.addEventListener('click', ()=>{
      const v = parseFloat(el('phCustomMl').value||'0');
      if(!isFinite(v) || v<=0){ alert('Enter ml > 0'); return; }
      postDose({ml:v, reason:'custom'});
    });
    el('btnAutoToggle')?.addEventListener('click', async ()=>{
      const r = await fetch('/api/ph/auto', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({enable:true})});
      const j = await r.json();
      if(window.showToast){ showToast(j.guard || 'Set', j.guard? 'error':'success'); }
      else { alert(j.guard || 'Set'); }
    });
    el('btnPhExport24')?.addEventListener('click', ()=>{ window.open('/api/ph/export?hours=24','_blank'); });
    el('ph-dose-csv')?.addEventListener('click', ()=>{ window.open('/api/ph/dose_log.csv?hours=168','_blank'); });

    // Chart range buttons
    el('ph-chart-24h')?.addEventListener('click', ()=>{ chartMode='24h'; refreshDoseChart(); });
    el('ph-chart-7d')?.addEventListener('click', ()=>{ chartMode='7d'; refreshDoseChart(); });

    // listen for settings UI updates to ui.sensors_poll_ms
    window.addEventListener('settings:ui', (ev)=>{
      const ms = ev.detail?.['ui.sensors_poll_ms'];
      if(ms){ pollMs = parseInt(ms)||POLL_DEFAULT; schedule(); }
    });
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    wire();
    tick();
    schedule();
    refreshSummary();
    refreshDoseChart();
  });
})();
  async function refreshSummary(){
    try{
      // Today: sum from 24h log; Week: 7d summary
      const log = await (await fetch('/api/ph/dose_log?hours=24',{cache:'no-store'})).json();
      const today = (log||[]).reduce((acc,e)=> acc + (e.volume_ml||0), 0);
      const weekRows = await (await fetch('/api/ph/dose_summary?days=7',{cache:'no-store'})).json();
      const week = (weekRows||[]).reduce((acc,r)=> acc + (r.total_ml||0), 0);
      const tEl = el('ph-total-today'); if (tEl) tEl.textContent = `Today: ${today.toFixed(1)} ml`;
      const wEl = el('ph-total-week'); if (wEl) wEl.textContent = `Week: ${week.toFixed(1)} ml`;
      // Calibration banner if any volumes are null/undefined
      const anyNull = (log||[]).some(e=> e.volume_ml==null);
      const banner = el('ph-calib-banner'); if (banner) banner.style.display = anyNull ? 'block':'none';
    }catch(e){ /* ignore */ }
  }

  function makeChart(){
    const ctx = el('phDoseChart'); if (!ctx) return null;
    const cfg = {
      type:'bar',
      data:{datasets:[]},
      options:{
        animation:false,
        maintainAspectRatio:true,
        parsing:false,
        normalized:true,
        scales:{
          x:{type:'time', time:{tooltipFormat:'yyyy-MM-dd HH:mm', displayFormats:{hour:'MMM d HH:mm', day:'MMM d'}}},
          y:{title:{display:true,text:'ml'}, beginAtZero:true}
        },
        plugins:{legend:{display:true}, tooltip:{callbacks:{
          label:(ctx)=>{
            const d = ctx.raw || {};
            if (d.kind==='dose'){
              const vol = (d.volume_ml==null)? '—' : `${d.volume_ml} ml`;
              const ph = (d.ph_before!=null || d.ph_after!=null) ? ` pH: ${d.ph_before??'—'} → ${d.ph_after??'—'}` : '';
              return ` +${vol} (${d.seconds}s, ${d.reason||'manual'})${ph}`;
            }
            if (d.kind==='daily'){ return ` Total: ${d.y.toFixed(1)} ml`; }
            return '';
          }
        }}}
      }
    };
    return new Chart(ctx, cfg);
  }

  async function refreshDoseChart(){
    try{
      if (!chart) chart = makeChart();
      if (!chart) return;
      let doses = [];
      let daily = [];
      if (chartMode==='24h'){
        doses = await (await fetch('/api/ph/dose_log?hours=24',{cache:'no-store'})).json();
      } else {
        doses = await (await fetch('/api/ph/dose_log?hours=168',{cache:'no-store'})).json();
        daily = await (await fetch('/api/ph/dose_summary?days=7',{cache:'no-store'})).json();
      }
      // Build datasets
      const dosePoints = (doses||[]).map(e=>({
        x: new Date(e.ts), y: e.volume_ml==null ? 0 : e.volume_ml, kind:'dose',
        volume_ml:e.volume_ml, seconds:e.seconds, reason:e.reason, ph_before:e.ph_before, ph_after:e.ph_after
      }));
      const dailyBars = (daily||[]).map(d=>({ x: new Date(d.day+'T00:00:00'), y: d.total_ml, kind:'daily' }));

      // Configure datasets
      const doseDs = { type:'scatter', label:'Doses', data: dosePoints, parsing:false,
        backgroundColor:'rgba(59,130,246,0.9)', pointRadius:4, pointHoverRadius:6, showLine:false };
      const dailyDs = { type:'bar', label:'Daily total', data: dailyBars, parsing:false,
        backgroundColor:'rgba(34,197,94,0.35)', borderColor:'rgba(34,197,94,0.6)' };
      chart.data.datasets = (chartMode==='24h') ? [doseDs] : [dailyDs, doseDs];
      chart.update('none');
    }catch(e){ /* ignore */ }
    // Refresh summary alongside
    refreshSummary().catch(()=>{});
  }
