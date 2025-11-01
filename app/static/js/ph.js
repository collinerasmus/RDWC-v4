// pH Control UI
(function(){
  const POLL_DEFAULT = 5000;
  let pollMs = POLL_DEFAULT;
  let pollTimer = null;
  let lastStatus = null;
  let countdownTimer = null;
  let lastPollAt = Date.now();
  let chart;
  let currentRange = { preset: null, start: null, end: null };

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
    if(!g.interval){
      cdPill.style.display = 'inline-block';
      cdPill.textContent = 'All clear';
      cdPill.style.borderColor = 'rgba(34,197,94,.45)';
      return;
    }
    // Estimate since_last_ok_s locally since last poll
    const elapsed = Math.floor((Date.now() - lastPollAt)/1000);
    const since = (g.since_last_ok_s ?? 0) + Math.max(0, elapsed);
    const need = Math.max(0, (g.min_interval_s ?? 0) - since);
    if(need <= 0){
      cdPill.textContent = 'All clear';
      cdPill.style.borderColor = 'rgba(34,197,94,.45)';
    } else {
      cdPill.textContent = `⏱ ${need}s`;
      cdPill.style.borderColor = 'rgba(239,68,68,.45)';
    }
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

  async function wire(){
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
    // Wire range controls (matching Trends template) - await to ensure range is loaded
    await wireRangeControls();
    
    // CSV export uses current range
    el('ph-dose-csv')?.addEventListener('click', ()=>{ exportCSV(); });

    // listen for settings UI updates to ui.sensors_poll_ms
    window.addEventListener('settings:ui', (ev)=>{
      const ms = ev.detail?.['ui.sensors_poll_ms'];
      if(ms){ pollMs = parseInt(ms)||POLL_DEFAULT; schedule(); }
    });
  }

  async function wireRangeControls(){
    // Get range utility
    if (!window.rdwcRange) {
      console.error('[pH] rdwcRange not loaded');
      return;
    }
    
    // Restore last preset or default to 24h
    const lastPreset = window.rdwcRange.getLastPreset('rdwc.ph.range', '24h');
    currentRange.preset = lastPreset;
    
    // Wire preset buttons
    const btns = document.querySelectorAll('#ph-card .btn-chip[data-range]');
    btns.forEach(btn => {
      const preset = btn.getAttribute('data-range');
      if (preset === currentRange.preset) btn.classList.add('active');
      
      // Disable Grow if no grow_start_date
      if (preset === 'grow') {
        const growDate = window.rdwcSettings?.get('general.grow_start_date');
        if (!growDate) {
          btn.disabled = true;
          btn.title = 'Set Grow start date in Settings';
          btn.style.opacity = '0.5';
          btn.style.cursor = 'not-allowed';
        }
      }
      
      btn.addEventListener('click', () => {
        if (!btn.disabled) selectPreset(preset);
      });
    });
    
    // Wire custom range
    const fromEl = el('phDoseFrom');
    const toEl = el('phDoseTo');
    const applyEl = el('phDoseApply');
    
    if (applyEl && fromEl && toEl) {
      applyEl.addEventListener('click', () => {
        const start = fromEl.value;
        const end = toEl.value;
        if (start && end) {
          window.rdwcRange.saveCustomRange('rdwc.ph.range', start, end);
          selectPreset('custom');
        }
      });
    }
    
    // Load initial range (await to ensure start/end are set before chart refresh)
    await loadRange(currentRange.preset);
  }
  
  async function selectPreset(preset){
    currentRange.preset = preset;
    window.rdwcRange.saveLastPreset('rdwc.ph.range', preset);
    
    // Update button states
    const btns = document.querySelectorAll('#ph-card .btn-chip[data-range]');
    btns.forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-range') === preset);
    });
    
    // Load range
    await loadRange(preset);
  }
  
  async function loadRange(preset){
    if (!window.rdwcRange) return;
    
    const growDate = window.rdwcSettings?.get('general.grow_start_date');
    const customRange = window.rdwcRange.getCustomRange('rdwc.ph.range');
    
    // Compute start/end
    const range = await window.rdwcRange.rangeToStartEnd(
      preset, 
      customRange.start, 
      customRange.end, 
      growDate
    );
    
    if (!range) {
      console.warn('[pH] Invalid range');
      return;
    }
    
    currentRange.start = range.start;
    currentRange.end = range.end;
    
    // Refresh chart and summary
    await refreshDoseChart();
    await refreshSummary();
  }
  
  function exportCSV(){
    if (!currentRange.start || !currentRange.end) {
      window.open('/api/ph/dose_log.csv?hours=168', '_blank');
      return;
    }
    const startISO = new Date(currentRange.start).toISOString();
    const endISO = new Date(currentRange.end).toISOString();
    window.open(`/api/ph/dose_log.csv?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=5000`, '_blank');
  }

  document.addEventListener('DOMContentLoaded', async ()=>{
    await wire();
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
      const vols = (log||[]).map(e => e.volume_ml);
      const hasVol = vols.some(v => v!=null);
      const today = (log||[]).reduce((acc,e)=> acc + (e.volume_ml||0), 0);
      const weekRows = await (await fetch('/api/ph/dose_summary?days=7',{cache:'no-store'})).json();
      const week = (weekRows||[]).reduce((acc,r)=> acc + (r.total_ml||0), 0);
      const tEl = document.getElementById('ph-total-today'); if (tEl) tEl.textContent = hasVol ? `Today: ${today.toFixed(1)} ml` : `Today: — ml`;
      const wEl = document.getElementById('ph-total-week'); if (wEl) wEl.textContent = hasVol ? `Week: ${week.toFixed(1)} ml` : `Week: — ml`;
      
      // Calibration banner: show only when events exist + all null + invalid rate
      const banner = document.getElementById('ph-calib-banner');
      if (banner) {
        const hasEvents = (log||[]).length > 0;
        const allNull = (log||[]).every(e => e.volume_ml == null);
        const rate = window.rdwcSettings?.get('dosing.ph_up_ml_per_sec');
        const invalidRate = !rate || rate <= 0;
        banner.style.display = (hasEvents && allNull && invalidRate) ? 'block' : 'none';
      }
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
              const vol = (d.volume_ml==null)? `~${d.seconds}s` : `+${d.volume_ml} ml`;
              const ph = (d.ph_before!=null || d.ph_after!=null) ? ` pH: ${d.ph_before??'—'} → ${d.ph_after??'—'}` : '';
              return `${vol} (${d.reason||'manual'})${ph}`;
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
      console.log('[pH] refreshDoseChart called, currentRange:', currentRange);
      if (!chart) chart = makeChart();
      if (!chart) return;
      
      // Determine if we have a valid range
      let doses = [];
      let daily = [];
      
      if (currentRange.start && currentRange.end) {
        // Use start/end range
        const startISO = new Date(currentRange.start).toISOString();
        const endISO = new Date(currentRange.end).toISOString();
        const windowHours = (currentRange.end - currentRange.start) / (1000 * 60 * 60);
        
        // Fetch dose log
        const logUrl = `/api/ph/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`;
        console.log('[pH] Fetching:', logUrl);
        const response = await fetch(logUrl, {cache:'no-store'});
        console.log('[pH] Response status:', response.status, response.statusText);
        const text = await response.text();
        console.log('[pH] Response text:', text);
        doses = text ? JSON.parse(text) : [];
        console.log('[pH] Got doses:', doses);
        
        // If window > 48h, fetch daily summary
        if (windowHours > 48) {
          const summaryUrl = `/api/ph/dose_summary?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`;
          daily = await (await fetch(summaryUrl, {cache:'no-store'})).json();
        }
      } else {
        // Fallback to 24h
        console.log('[pH] Falling back to 24h');
        const response = await fetch('/api/ph/dose_log?hours=24',{cache:'no-store'});
        console.log('[pH] Response status:', response.status, response.statusText);
        const text = await response.text();
        console.log('[pH] Response text:', text);
        doses = text ? JSON.parse(text) : [];
        console.log('[pH] Got doses (24h fallback):', doses);
      }
      
      // Build datasets
      const dosePoints = (doses||[]).map(e=>({
        x: new Date(e.ts), y: e.volume_ml==null ? e.seconds : e.volume_ml, kind:'dose',
        volume_ml:e.volume_ml, seconds:e.seconds, reason:e.reason, ph_before:e.ph_before, ph_after:e.ph_after
      }));
      const dailyBars = (daily||[]).map(d=>({ x: new Date(d.day+'T00:00:00'), y: d.total_ml, kind:'daily' }));

      // Configure datasets based on mode
      const doseDs = { type:'scatter', label:'Doses', data: dosePoints, parsing:false,
        backgroundColor:'rgba(59,130,246,0.9)', pointRadius:4, pointHoverRadius:6, showLine:false };
      const dailyDs = { type:'bar', label:'Daily total', data: dailyBars, parsing:false,
        backgroundColor:'rgba(34,197,94,0.35)', borderColor:'rgba(34,197,94,0.6)' };
      
      // Detail mode (≤48h) vs overview mode (>48h)
      const windowHours = currentRange.start && currentRange.end ? 
        (currentRange.end - currentRange.start) / (1000 * 60 * 60) : 24;
      chart.data.datasets = (windowHours <= 48) ? [doseDs] : [dailyDs, doseDs];
      
      // Empty state helper
      const empty = (!doses || doses.length===0) && (!daily || daily.length===0);
      const emptyEl = document.getElementById('phDoseEmpty'); if (emptyEl) emptyEl.style.display = empty ? 'block':'none';
      const canv = document.getElementById('phDoseChart'); if (canv) canv.style.opacity = empty ? 0.5 : 1;
      
      // Update "In range" counter with calibration-aware estimate
      const inRangeMl = (doses||[]).reduce((sum, e) => sum + (e.volume_ml || 0), 0);
      const inRangeEl = document.getElementById('ph-in-range');
      if (inRangeEl) {
        if (inRangeMl > 0) {
          // Has calibrated volumes
          inRangeEl.textContent = `In range: ${inRangeMl.toFixed(1)} ml`;
        } else if ((doses||[]).length > 0) {
          // Has doses but all volume_ml are null - check for calibration
          const allNull = (doses||[]).every(e => e.volume_ml == null);
          if (allNull) {
            const rate = window.rdwcSettings?.get('dosing.ph_up_ml_per_sec');
            if (rate && rate > 0) {
              // Valid rate - show estimate
              const totalSeconds = (doses||[]).reduce((sum, e) => sum + (e.seconds || 0), 0);
              const estimate = (totalSeconds * rate).toFixed(1);
              inRangeEl.textContent = `In range: ~${estimate} ml (est.)`;
            } else {
              // No valid rate
              inRangeEl.textContent = 'In range: — ml';
            }
          } else {
            inRangeEl.textContent = 'In range: — ml';
          }
        } else {
          // No doses
          inRangeEl.textContent = 'In range: — ml';
        }
      }
      
      chart.update('none');
    }catch(e){ 
      console.error('[pH] Chart refresh failed:', e);
    }
    // Refresh summary alongside
    refreshSummary().catch(()=>{});
  }