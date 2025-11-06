// EC Control UI
(function(){
  const POLL_DEFAULT = 5000;
  let endpointMode = null; // 'dose_api' or 'relay_pulse'
  let pollMs = POLL_DEFAULT;
  let pollTimer = null;
  lastStatus = null;
  let countdownTimer = null;
  let lastPollAt = Date.now();
  // Recent collapse state
  let recentCollapsed = true;
  let recentHeaderBound = false;

  function el(id){ return document.getElementById(id); }

  async function fetchStatus(){
    try{
      const r = await fetch('/api/ec/status', {cache: 'no-store'});
      if(!r.ok) throw new Error('status');
      return await r.json();
    }catch(e){ return null; }
  }

  async function detectDoseMode(){
    if(endpointMode) return endpointMode;
    try{
      const t = await fetch('/api/dose/grow', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({seconds:0.0, reason:'probe'})});
      if(t.ok){ endpointMode = 'dose_api'; return endpointMode; }
    }catch(e){ /* ignore */ }
    endpointMode = 'relay_pulse';
    return endpointMode;
  }

  async function fetchHealthDB(){
    try{
      const r = await fetch('/health/db', {cache: 'no-store'});
      if(!r.ok) return null;
      return await r.json();
    }catch(e){ return null; }
  }

  function guardActive(g){
    if(!g) return false;
    return g.estop || g.sensor_stale || g.interval || g.daily_cap || g.reservoir || g.mix_lock;
  }

  function guardList(g){
    const out = [];
    if(g.estop) out.push('E-STOP');
    if(g.sensor_stale) out.push('Sensor stale');
    if(g.interval) out.push('Min interval');
    if(g.daily_cap) out.push('Daily cap');
    if(g.reservoir) out.push('Reservoir');
    if(g.mix_lock) out.push('Mix lock');
    return out;
  }

  function guardHints(g){
    const tips = [];
    if(g.estop) tips.push('E-STOP: Emergency stop is active; all dosing blocked.');
    if(g.sensor_stale) tips.push('Sensor stale: EC reading is older than 5 min.');
    if(g.interval) tips.push('Min interval: Waiting between doses.');
    if(g.daily_cap) tips.push('Daily cap reached.');
    if(g.reservoir) tips.push('Reservoir set to 0 L; dosing disabled.');
    if(g.mix_lock) tips.push('pH or EC dose in progress.');
    return tips.join('\n');
  }

  function setRecentCollapsed(collapsed){
    recentCollapsed = !!collapsed;
    const hdr = el('ec-recent-header');
    const list = el('ec-recent');
    if(hdr){ hdr.textContent = recentCollapsed ? 'Recent Doses ▸' : 'Recent Doses ▾'; }
    if(list){ list.style.display = recentCollapsed ? 'none' : 'block'; }
  }

  async function renderStatus(s){
    lastStatus = s;
    lastPollAt = Date.now();
    const ecVal = el('ec-current');
    const ppmVal = el('ec-ppm');
    const band = el('ec-band');
    const guards = el('ec-guards');
    const recent = el('ec-recent');
    const resBanner = el('ec-reservoir-banner');
    const cdPill = el('ec-countdown-pill');
    
    if(ecVal){ ecVal.textContent = (s && s.ec_ms_cm!=null) ? s.ec_ms_cm.toFixed(2) : '—'; }
    if(ppmVal){ 
      const ppm = (s && s.ec_ms_cm!=null) ? Math.round(s.ec_ms_cm * 500) : null;
      ppmVal.textContent = ppm!=null ? ppm : '—'; 
    }
    if(band && s){ band.textContent = `Targets ${s.targets.low} – ${s.targets.high} mS/cm`; }
    if(guards && s){
      const list = guardList(s.guards);
      guards.textContent = list.length ? list.join(' · ') : 'All clear';
      guards.style.color = list.length ? '#f59e0b' : '#16a34a';
      guards.title = list.length ? guardHints(s.guards) : '';
    }
    if(resBanner && s){ resBanner.style.display = s.guards?.reservoir ? 'block' : 'none'; }

    // Freshness indicator
    const health = await fetchHealthDB();
    const dot = el('ecFreshnessDot');
    if(dot && health){
      const age = health.age_seconds || 0;
      const rows = health.row_count || 0;
      if(age < 180){
        dot.style.background = '#22c55e'; // green
        dot.title = `Fresh (${Math.round(age)}s, ${rows} rows)`;
      }else if(age < 600){
        dot.style.background = '#f59e0b'; // amber
        dot.title = `Stale (${Math.round(age)}s, ${rows} rows)`;
      }else{
        dot.style.background = '#ef4444'; // red
        dot.title = `Very stale (${Math.round(age)}s, ${rows} rows)`;
      }
    }

    // Override badge in header
    const overrideBadge = el('ecOverrideBadge');
    if(overrideBadge){
      const override = (window.rdwcSettings?.get('safety.maintenance_override')||'false').toLowerCase() === 'true';
      overrideBadge.style.display = override ? 'inline-block' : 'none';
    }
    if(recent && s){
      recent.innerHTML = '';
      (s.recent||[]).forEach(r => {
        const li = document.createElement('div');
        li.className = 'muted';
        const when = r.ts_utc?.replace('T',' ').replace('Z','');
        const mix = r.mix_ratio || '';
        li.textContent = `${when} • ${r.action} • ${r.volume_ml||''} ml • ${mix} • ${r.result}${r.reason? ' • '+r.reason: ''}`;
        recent.appendChild(li);
      });

      // Bind header click once
      const hdr = el('ec-recent-header');
      if (hdr && !recentHeaderBound){
        recentHeaderBound = true;
        hdr.addEventListener('click', ()=>{
          setRecentCollapsed(!recentCollapsed);
        });
      }
      setRecentCollapsed(recentCollapsed);
    }
    
    // Today total
    const todayEl = el('ec-total-today');
    if(todayEl && s){ todayEl.textContent = `Today: ${(s.today_ml||0).toFixed(1)} ml`; }

    // Determine disabled state
    const g = s?.guards || {};
    const maint = (window.rdwcSettings?.get('safety.maintenance_override')||'false').toLowerCase() === 'true';
    const bypass = maint;
    const blockedCooldown = (g.interval || g.daily_cap) && !bypass;
    const blockedHard = !!(g.estop || g.sensor_stale || g.reservoir || g.mix_lock);
    const disabled = blockedCooldown || blockedHard;
    ['btnEcDose10','btnEcDose50','btnEcDose100','btnEcDoseCustom','ecCustomMl'].forEach(id=>{
      const e = el(id); if(e){ e.disabled = disabled; e.title = disabled ? 'Blocked by guard(s)' : ''; }
    });

    // Maintenance override badge in manual tab
    const badge = el('ecMaintBadge');
    if (badge) badge.style.display = maint ? 'inline-block' : 'none';

    // Automation toggle button
    const autoBtn = el('btnEcAutoToggle');
    if (autoBtn) {
      const enabled = !!(s && s.auto && s.auto.enabled);
      autoBtn.textContent = enabled ? 'Disable EC automation' : 'Enable EC automation';
      autoBtn.title = 'Automatically raises EC when below target band using G/M/B mix';
    }

    // Automation badges
    const stateBadge = el('ecAutoStateBadge');
    const learnedBadge = el('ecLearnedBadge');
    if (stateBadge && s) {
      const enabled = !!(s.auto && s.auto.enabled);
      if (!enabled) {
        stateBadge.textContent = 'Disabled';
        stateBadge.style.borderColor = 'rgba(148,163,184,.35)';
        stateBadge.style.color = '#cbd5e1';
        stateBadge.style.background = 'rgba(148,163,184,.08)';
        stateBadge.title = '';
      } else {
        const reason = s.auto?.holding_reason;
        if (reason) {
          stateBadge.textContent = `Holding: ${reason}`;
          stateBadge.style.borderColor = 'rgba(251,191,36,.4)';
          stateBadge.style.color = '#fef3c7';
          stateBadge.style.background = 'rgba(251,191,36,.12)';
          stateBadge.title = 'Auto is enabled but holding due to guard';
        } else {
          stateBadge.textContent = 'Active';
          stateBadge.style.borderColor = 'rgba(34,197,94,.4)';
          stateBadge.style.color = '#86efac';
          stateBadge.style.background = 'rgba(34,197,94,.12)';
          stateBadge.title = 'Automation running';
        }
      }
    }
    if (learnedBadge && s) {
      const learned = s.auto?.learned_ml_per_mScm;
      if (learned != null) {
        learnedBadge.textContent = `Learned: ${learned.toFixed(1)} ml/mScm`;
        learnedBadge.style.display = 'inline-block';
      } else {
        learnedBadge.style.display = 'none';
      }
    }
    
    // Update caps display from settings
    if(window.rdwcSettings){
      const maxPress = window.rdwcSettings.get('safety.max_seconds_per_press') || '1.5';
      const dailyCap = window.rdwcSettings.get('safety.max_total_seconds_per_24h') || '120';
      const minOff = window.rdwcSettings.get('safety.min_off_window_sec') || '2';
      if(el('ecCapMaxPress')) el('ecCapMaxPress').textContent = maxPress + 's';
      if(el('ecCapDaily')) el('ecCapDaily').textContent = dailyCap + 's';
      if(el('ecCapMinOff')) el('ecCapMinOff').textContent = minOff + 's';
    }
    
    // Update K-factor and calibration status chips in header
    updateHeaderChips();
  }

  async function updateHeaderChips() {
    try {
      const res = await fetch('/api/ec/cal/status', {cache:'no-store'});
      if (!res.ok) return;
      
      const data = await res.json();
      const k = data.k;
      const cal = data.cal;
      
      // Update K chip
      const kChip = el('ecKChip');
      if (kChip) {
        kChip.textContent = k != null ? `K=${k}` : 'K=—';
        // Success if K=0.1, neutral otherwise
        kChip.className = 'ui-status-chip ' + (k === 0.1 ? 'success' : 'neutral');
      }
      
      // Update Cal chip
      const calChip = el('ecCalChip');
      if (calChip) {
        calChip.textContent = cal ? `Cal: ${cal}` : 'Cal: —';
        // Success if calibrated (one-point or two-point), neutral if uncalibrated/unknown
        const isCalibrated = cal && (cal.includes('one-point') || cal.includes('two-point'));
        calChip.className = 'ui-status-chip ' + (isCalibrated ? 'success' : 'neutral');
      }
    } catch (e) {
      // Silently fail - chips will show default values
    }
  }

  function startPoll(){
    stopPoll();
    pollTimer = setInterval(async ()=>{
      const s = await fetchStatus();
      if(s) renderStatus(s);
    }, pollMs);
  }

  function stopPoll(){
    if(pollTimer){ clearInterval(pollTimer); pollTimer = null; }
  }

  async function doseEC(ml){
    const mix = document.querySelector('input[name="ecMixRatio"]:checked')?.value || 'schedule';
    const body = { ml, mix_ratio: mix, reason: 'manual' };
    if (mix === 'custom') {
      body.custom = {
        grow: parseFloat(el('ecCustomGrow')?.value || 0),
        micro: parseFloat(el('ecCustomMicro')?.value || 0),
        bloom: parseFloat(el('ecCustomBloom')?.value || 0)
      };
    }
    try{
      const r = await fetch('/api/ec/dose', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      if(!r.ok){
        const e = await r.json();
        showToast(`Dose failed: ${e.error||'unknown'}`, 'error');
        return;
      }
      showToast(`Dosed ${ml} ml`, 'success');
      const s = await fetchStatus();
      if(s) renderStatus(s);
      if(window.ecChart) window.ecChart.refresh();
    }catch(e){
      showToast(`Dose error: ${e.message}`, 'error');
    }
  }

  async function toggleAuto(){
    if(!lastStatus) return;
    const enabled = !!(lastStatus.auto && lastStatus.auto.enabled);
    const body = {enable: !enabled};
    try{
      const r = await fetch('/api/ec/auto', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      if(!r.ok){
        const e = await r.json();
        showToast(`Auto toggle failed: ${e.error||'unknown'}`, 'error');
        return;
      }
      showToast(enabled ? 'EC automation disabled' : 'EC automation enabled', 'success');
      const s = await fetchStatus();
      if(s) renderStatus(s);
    }catch(e){
      showToast(`Auto toggle error: ${e.message}`, 'error');
    }
  }

  function showToast(msg, type){
    if(window.showToast) window.showToast(msg, type);
    else console.log(`[EC] ${type}: ${msg}`);
  }

  function exportCSV24h(){
    window.open('/api/ec/dose_log.csv?hours=24', '_blank');
  }

  // Custom ratio toggle
  function setupMixRatioToggle(){
    const radios = document.querySelectorAll('input[name="ecMixRatio"]');
    const customDiv = el('ec-custom-ratio');
    radios.forEach(r => {
      r.addEventListener('change', ()=>{
        if(customDiv) customDiv.style.display = (r.value === 'custom' && r.checked) ? 'block' : 'none';
      });
    });
  }

  // --- Unified dosing ---
  async function doseUnified(pump, seconds, reason='manual'){
    // Debounce per pump
    window.__ecPulseLast = window.__ecPulseLast || {};
    const now = Date.now();
    const last = window.__ecPulseLast[pump] || 0;
    if(now - last < 400){ return; }
    window.__ecPulseLast[pump] = now;
    const btnMap = {
      'grow': ['btnDoseGrow','btnDoseGrow05','btnDoseGrow10','btnPulseGrowCustom'],
      'micro': ['btnDoseMicro','btnDoseMicro05','btnDoseMicro10','btnPulseMicroCustom'],
      'bloom': ['btnDoseBloom','btnDoseBloom05','btnDoseBloom10','btnPulseBloomCustom']
    };
    const btns = (btnMap[pump] || []).map(id => el(id)).filter(b => b);
    btns.forEach(b => { b.disabled = true; b.classList.add('loading'); });
    
    try{
      const mode = await detectDoseMode();
      let r, j;
      if(mode === 'dose_api'){
        r = await fetch(`/api/dose/${pump}`, { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({seconds, reason, actor:'ui'}) });
        j = await r.json().catch(()=>({}));
      } else {
        const relayMap = {grow:'dosing_grow', micro:'dosing_micro', bloom:'dosing_bloom'};
        r = await fetch('/api/relays/pulse', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({relay: relayMap[pump], seconds, reason}) });
        j = await r.json().catch(()=>({}));
      }
      
      if(!r.ok || (!j.ok && j.blocked_by)){
        const msg = j.message || j.error || j.blocked_by || 'Unknown error';
        showToast(`Dose blocked: ${msg}`, 'error');
      } else {
        showToast(`Dosed ${pump} for ${seconds}s`, 'success');
        const s2 = await fetchStatus();
        if(s2) renderStatus(s2);
        refreshDoseLog();
        updateEcTotals().catch(()=>{});
      }
    }catch(e){
      showToast(`Dose error: ${e.message}`, 'error');
    } finally {
      setTimeout(()=>{ btns.forEach(b => { b.disabled = false; b.classList.remove('loading'); }); }, 600);
    }
  }

  async function refreshDoseLog(){
    const table = el('ecDoseLogTable');
    if(!table) return;
    
    try{
      const r = await fetch('/api/dose/recent?limit=20', {cache:'no-store'});
      if(!r.ok) throw new Error('HTTP '+r.status);
      const data = await r.json();
      const events = (data.events||[]).filter(e => ['grow','micro','bloom'].includes(e.pump));
      
      if(events.length === 0){
        table.innerHTML = '<tr><td colspan="6" style="padding:12px;text-align:center;">No doses yet</td></tr>';
        return;
      }
      
      table.innerHTML = events.map(e => {
        const time = e.ts_utc ? new Date(e.ts_utc).toLocaleString() : '—';
        const ec_before = e.ec_before != null ? e.ec_before.toFixed(2) : '—';
        const ec_after = e.ec_after != null ? e.ec_after.toFixed(2) : '—';
        const note = e.blocked_by || e.reason || '—';
        const row_style = e.blocked_by ? 'color:#f59e0b;' : '';
        return `<tr style="${row_style}">
          <td style="padding:6px 8px;">${time}</td>
          <td style="padding:6px 8px;">${e.pump}</td>
          <td style="padding:6px 8px;text-align:right;">${e.seconds.toFixed(2)}s</td>
          <td style="padding:6px 8px;text-align:right;">${ec_before}</td>
          <td style="padding:6px 8px;text-align:right;">${ec_after}</td>
          <td style="padding:6px 8px;">${note}</td>
        </tr>`;
      }).join('');
    }catch(e){
      table.innerHTML = '<tr><td colspan="6" style="padding:12px;text-align:center;">Error loading log</td></tr>';
    }
  }

  // Initialize
  async function init(){
    const s = await fetchStatus();
    if(s) renderStatus(s);
    startPoll();
    setupMixRatioToggle();

    // New unified dose buttons (time-based)
    el('btnDoseGrow')?.addEventListener('click', ()=> doseUnified('grow', 0.3, 'manual'));
    el('btnDoseGrow05')?.addEventListener('click', ()=> doseUnified('grow', 0.5, 'manual'));
    el('btnDoseGrow10')?.addEventListener('click', ()=> doseUnified('grow', 1.0, 'manual'));
    el('btnPulseGrowCustom')?.addEventListener('click', ()=>{ const v=parseFloat(el('ecGrowCustomSec')?.value||0); if(v>0) doseUnified('grow', v, 'manual'); });
    el('btnDoseMicro')?.addEventListener('click', ()=> doseUnified('micro', 0.3, 'manual'));
    el('btnDoseMicro05')?.addEventListener('click', ()=> doseUnified('micro', 0.5, 'manual'));
    el('btnDoseMicro10')?.addEventListener('click', ()=> doseUnified('micro', 1.0, 'manual'));
    el('btnPulseMicroCustom')?.addEventListener('click', ()=>{ const v=parseFloat(el('ecMicroCustomSec')?.value||0); if(v>0) doseUnified('micro', v, 'manual'); });
    el('btnDoseBloom')?.addEventListener('click', ()=> doseUnified('bloom', 0.3, 'manual'));
    el('btnDoseBloom05')?.addEventListener('click', ()=> doseUnified('bloom', 0.5, 'manual'));
    el('btnDoseBloom10')?.addEventListener('click', ()=> doseUnified('bloom', 1.0, 'manual'));
    el('btnPulseBloomCustom')?.addEventListener('click', ()=>{ const v=parseFloat(el('ecBloomCustomSec')?.value||0); if(v>0) doseUnified('bloom', v, 'manual'); });
    
    // Legacy volume-based dose buttons (keep for now)
    el('btnEcDose10')?.addEventListener('click', ()=>doseEC(10));
    el('btnEcDose50')?.addEventListener('click', ()=>doseEC(50));
    el('btnEcDose100')?.addEventListener('click', ()=>doseEC(100));
    el('btnEcDoseCustom')?.addEventListener('click', ()=>{
      const ml = parseFloat(el('ecCustomMl')?.value || 0);
      if(ml > 0) doseEC(ml);
    });
    el('btnEcAutoToggle')?.addEventListener('click', toggleAuto);
    el('btnEcExport24')?.addEventListener('click', exportCSV24h);
    
    // Dose log refresh
    el('btnEcRefreshDoseLog')?.addEventListener('click', refreshDoseLog);
    refreshDoseLog();

  // Compute EC Today/Week totals from unified dose_events as fallback
  updateEcTotals().catch(()=>{});

    // Bind Maintenance Override header toggle
    try{
      const toggle = document.getElementById('ec-maint-toggle');
      if (toggle){
        // Initialize from settings
        try{
          const s = await (await fetch('/api/settings', {cache:'no-store'})).json();
          const cur = (s && s.safety && (s.safety.maintenance_override||'false')).toLowerCase()==='true';
          toggle.checked = cur;
        }catch(e){}
        toggle.addEventListener('change', async ()=>{
          const val = toggle.checked ? 'true' : 'false';
          try{
            const r = await fetch('/api/settings', {
              method:'PUT', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({ 'safety.maintenance_override': val })
            });
            if(!r.ok) throw new Error('HTTP '+r.status);
            // refresh view
            const s2 = await fetchStatus();
            if(s2) renderStatus(s2);
          }catch(e){ console.warn('[EC] failed to set maintenance_override', e); toggle.checked = !toggle.checked; }
        });
      }
    }catch(e){ console.warn('[EC] maint toggle bind failed', e); }

    // Settings save
    el('btnSaveEcSettings')?.addEventListener('click', async ()=>{
      const payload = {
        'targets.ec_low': el('ecTargetLow')?.value,
        'targets.ec_high': el('ecTargetHigh')?.value,
        'dosing.grow_ml_per_sec': el('ecGrowMlPerSec')?.value,
        'dosing.micro_ml_per_sec': el('ecMicroMlPerSec')?.value,
        'dosing.bloom_ml_per_sec': el('ecBloomMlPerSec')?.value,
        'dosing.ec_step_ml_min': el('ecStepMinMl')?.value,
        'dosing.ec_step_ml_max': el('ecStepMaxMl')?.value,
        'dosing.ec_safety_factor': el('ecSafetyFactor')?.value,
        'dosing.ec_min_interval_s': el('ecMinInterval')?.value,
        'dosing.ec_max_ml_day': el('ecMaxMlDay')?.value
      };
      try{
        const r = await fetch('/api/settings', {
          method: 'PUT',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });
        if(!r.ok){
          const e = await r.json();
          showToast(`Save failed: ${e.error||e.message||'unknown'}`, 'error');
          return;
        }
        showToast('EC settings saved', 'success');
        const s = await fetchStatus();
        if(s) renderStatus(s);
      }catch(e){
        showToast(`Save error: ${e.message}`, 'error');
      }
    });
  }

  // Compute EC Today/Week totals from unified dose_events (seconds * ml/s per pump)
  async function updateEcTotals(){
    try{
      const rate = {
        grow: parseFloat(window.rdwcSettings?.get('dosing.grow_ml_per_sec') || '20'),
        micro: parseFloat(window.rdwcSettings?.get('dosing.micro_ml_per_sec') || '20'),
        bloom: parseFloat(window.rdwcSettings?.get('dosing.bloom_ml_per_sec') || '20')
      };
      const calc = async (hours)=>{
        const r = await fetch(`/api/dose/recent?hours=${hours}`, {cache:'no-store'});
        if(!r.ok) return 0;
        const j = await r.json();
        const ev = (j.events||[]).filter(e => !e.blocked_by && ['grow','micro','bloom'].includes(e.pump));
        return ev.reduce((acc, e)=> acc + (Number(e.seconds||0) * (rate[e.pump]||0)), 0);
      };
      const todayMl = await calc(24);
      const weekMl = await calc(24*7);
      const tEl = el('ec-total-today'); if (tEl) tEl.textContent = todayMl>0 ? `Today: ${todayMl.toFixed(1)} ml` : 'Today: — ml';
      const wEl = el('ec-total-week'); if (wEl) wEl.textContent = weekMl>0 ? `Week: ${weekMl.toFixed(1)} ml` : 'Week: — ml';
    }catch(e){ /* noop */ }
  }

  // Load settings into UI
  async function loadECSettings(){
    if(!window.rdwcSettings) return;
    el('ecTargetLow').value = window.rdwcSettings.get('targets.ec_low') || '0.8';
    el('ecTargetHigh').value = window.rdwcSettings.get('targets.ec_high') || '1.2';
    // Setpoint (new key ec.setpoint_mscm)
    const sp = window.rdwcSettings.get('ec.setpoint_mscm');
    const spInput = el('ecSetpoint');
    if(spInput) spInput.value = sp || '';
    el('ecGrowMlPerSec').value = window.rdwcSettings.get('dosing.grow_ml_per_sec') || '25';
    el('ecMicroMlPerSec').value = window.rdwcSettings.get('dosing.micro_ml_per_sec') || '25';
    el('ecBloomMlPerSec').value = window.rdwcSettings.get('dosing.bloom_ml_per_sec') || '25';
    el('ecStepMinMl').value = window.rdwcSettings.get('dosing.ec_step_ml_min') || '10';
    el('ecStepMaxMl').value = window.rdwcSettings.get('dosing.ec_step_ml_max') || '120';
    el('ecSafetyFactor').value = window.rdwcSettings.get('dosing.ec_safety_factor') || '0.6';
    el('ecMinInterval').value = window.rdwcSettings.get('dosing.ec_min_interval_s') || '300';
    el('ecMaxMlDay').value = window.rdwcSettings.get('dosing.ec_max_ml_day') || '0';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ()=>{
      loadECSettings();
      init();
    });
  } else {
    loadECSettings();
    init();
  }
  // Save setpoint handler
  document.addEventListener('click', async (e)=>{
    if(e.target && e.target.id === 'btnSaveEcSetpoint'){
      const v = parseFloat(el('ecSetpoint')?.value||'');
      const payload = { 'ec.setpoint_mscm': isNaN(v)? null : v };
      try{
        const r = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
        if(!r.ok) throw new Error('HTTP '+r.status);
        showToast('EC setpoint saved','success');
      }catch(err){ showToast('Setpoint save failed: '+err.message,'error'); }
    }
  });

  // Patch renderStatus to compute delta & caps
  const _origRender = renderStatus;
  renderStatus = function(s){
    _origRender(s);
    try{
      const sp = parseFloat(el('ecSetpoint')?.value||'');
      if(s && s.ec_ms_cm!=null && !isNaN(sp)){
        const d = s.ec_ms_cm - sp;
        const chip = el('ecDeltaChip');
        if(chip){ chip.textContent = (d>=0? '+' : '') + d.toFixed(2); chip.parentElement.style.color = d>=0? '#f59e0b':'#3b82f6'; }
      }
      const capMax = window.rdwcSettings?.get('safety.max_seconds_per_press');
      const capDaily = window.rdwcSettings?.get('safety.max_total_seconds_per_24h');
      const capMinOff = window.rdwcSettings?.get('safety.min_off_window_sec');
      if(el('ecV1CapMaxPress')) el('ecV1CapMaxPress').textContent = capMax ? capMax+'s' : '—';
      if(el('ecV1CapDaily')) el('ecV1CapDaily').textContent = capDaily ? capDaily+'s' : '—';
      if(el('ecV1CapMinOff')) el('ecV1CapMinOff').textContent = capMinOff ? capMinOff+'s' : '—';
    }catch(e){ /* ignore */ }
  };

  // EC Calibration Wizard
  async function refreshCalStatus(){
    try{
      const [statusRes, sensorRes] = await Promise.all([
        fetch('/api/ec/cal/status', {cache:'no-store'}),
        fetchStatus()
      ]);
      if(statusRes.ok){
        const status = await statusRes.json();
        el('ecCalStatusValue').textContent = status.cal || 'unknown';
        el('ecKValue').textContent = status.k != null ? status.k.toFixed(1) : '—';
      }
      if(sensorRes && sensorRes.ec_ms_cm != null){
        el('ecCalCurrentReading').textContent = sensorRes.ec_ms_cm.toFixed(2);
      }
      showCalMessage('Status refreshed', 'info');
    }catch(err){
      showCalMessage('Error: '+err.message, 'error');
    }
  }
  async function ecCalClear(){
    if(!confirm('Clear EC calibration? You will need to recalibrate.')) return;
    try{
      const r = await fetch('/api/ec/cal/clear', {method:'POST'});
      const j = await r.json();
      showCalMessage(j.ok ? ('✓ '+j.response) : ('✗ '+j.error), j.ok?'success':'error');
      if(j.ok) setTimeout(refreshCalStatus, 1000);
    }catch(err){ showCalMessage('✗ '+err.message, 'error'); }
  }
  async function ecCalLow(){
    if(!confirm('Apply low-point (1413 µS/cm)? Probe must be in solution and stable (30s).')) return;
    try{
      const r = await fetch('/api/ec/cal/low', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({us_cm:1413})});
      const j = await r.json();
      showCalMessage(j.ok ? ('✓ '+j.response) : ('✗ '+j.error), j.ok?'success':'error');
      if(j.ok) setTimeout(refreshCalStatus, 1000);
    }catch(err){ showCalMessage('✗ '+err.message, 'error'); }
  }
  async function ecCalHigh(){
    if(!confirm('Apply high-point (12,880 µS/cm)? Requires low-point first. Probe must be in solution and stable (30s).')) return;
    try{
      const r = await fetch('/api/ec/cal/high', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({us_cm:12880})});
      const j = await r.json();
      showCalMessage(j.ok ? ('✓ '+j.response) : ('✗ '+j.error), j.ok?'success':'error');
      if(j.ok) setTimeout(refreshCalStatus, 1000);
    }catch(err){ showCalMessage('✗ '+err.message, 'error'); }
  }
  async function ecSetK(){
    const k = prompt('Enter K factor (probe constant, typically 1.0 or 10.0):', '1.0');
    if(!k) return;
    const kVal = parseFloat(k);
    if(isNaN(kVal) || kVal <= 0){ alert('Invalid K value'); return; }
    try{
      const r = await fetch('/api/ec/k', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({k:kVal})});
      const j = await r.json();
      showCalMessage(j.ok ? ('✓ K='+kVal+' '+j.response) : ('✗ '+j.error), j.ok?'success':'error');
      if(j.ok) setTimeout(refreshCalStatus, 1000);
    }catch(err){ showCalMessage('✗ '+err.message, 'error'); }
  }
  function showCalMessage(msg, type){
    const msgEl = el('ecCalMessage');
    if(!msgEl) return;
    msgEl.textContent = msg;
    const colors = {
      success: {bg:'rgba(34,197,94,0.08)', border:'rgba(34,197,94,0.3)', text:'#a7f3d0'},
      error: {bg:'rgba(239,68,68,0.08)', border:'rgba(239,68,68,0.3)', text:'#fecaca'},
      info: {bg:'rgba(59,130,246,0.08)', border:'rgba(59,130,246,0.3)', text:'#93c5fd'}
    };
    const c = colors[type] || colors.info;
    msgEl.style.background = c.bg;
    msgEl.style.borderColor = c.border;
    msgEl.style.color = c.text;
  }
  el('btnEcCalRefreshStatus')?.addEventListener('click', refreshCalStatus);
  el('btnEcCalClear')?.addEventListener('click', ecCalClear);
  el('btnEcCalLow')?.addEventListener('click', ecCalLow);
  el('btnEcCalHigh')?.addEventListener('click', ecCalHigh);
  el('btnEcCalSetK')?.addEventListener('click', ecSetK);

  // EC Debug Modal handlers
  async function openEcDebug(){
    const modal = el('ecDebugModal');
    const content = el('ecDebugContent');
    if(!modal || !content) return;
    
    modal.style.display = 'flex';
    content.innerHTML = 'Loading...';
    
    try{
      const [rawRes, idRes] = await Promise.all([
        fetch('/debug/ec_raw', {cache:'no-store'}),
        fetch('/debug/i2c_ec_id', {cache:'no-store'})
      ]);
      
      if(!rawRes.ok || !idRes.ok){
        content.innerHTML = '<div style="color:#f59e0b;">Debug endpoints not available (404). Set DEBUG=true in environment.</div>';
        return;
      }
      
      const raw = await rawRes.json();
      const id = await idRes.json();
      
      let html = '<div style="display:grid;gap:12px;">';
      
      html += '<div style="padding:12px;background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.25);border-radius:8px;">';
      html += '<div style="font-weight:600;margin-bottom:8px;color:#60a5fa;">Raw EC Reading</div>';
      html += `<div>Value: <strong>${raw.raw_value}</strong> ${raw.raw_unit}</div>`;
      html += `<div>Processed: <strong>${raw.processed_mS_cm}</strong> mS/cm</div>`;
      html += `<div>Suggested scale: <strong>${raw.suggested_scale_hint}</strong></div>`;
      html += `<div style="margin-top:8px;padding:8px;background:rgba(251,191,36,0.08);border-left:3px solid #fbbf24;font-size:0.85rem;">${raw.note}</div>`;
      html += '</div>';
      
      html += '<div style="padding:12px;background:rgba(148,163,184,0.08);border:1px solid rgba(148,163,184,0.25);border-radius:8px;">';
      html += '<div style="font-weight:600;margin-bottom:8px;color:#cbd5e1;">Device Info</div>';
      html += `<div>Device: <strong>${id.device_info}</strong></div>`;
      html += `<div>K value: <strong>${id.k_value}</strong></div>`;
      html += `<div>Calibration: <strong>${id.cal_status}</strong></div>`;
      html += `<div>Output params: <strong>${id.output_params}</strong></div>`;
      html += '</div>';
      
      if(raw.error){
        html += `<div style="padding:12px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);border-radius:8px;color:#fecaca;">Error: ${raw.error}</div>`;
      }
      
      html += '</div>';
      content.innerHTML = html;
      
    }catch(err){
      content.innerHTML = `<div style="color:#ef4444;">Error loading debug data: ${err.message}</div>`;
    }
  }
  
  function closeEcDebug(){
    const modal = el('ecDebugModal');
    if(modal) modal.style.display = 'none';
  }
  
  // Bind debug button
  el('btnEcDebug')?.addEventListener('click', openEcDebug);
  el('btnCloseEcDebug')?.addEventListener('click', closeEcDebug);
  el('ecDebugModal')?.addEventListener('click', (e)=>{
    if(e.target.id === 'ecDebugModal') closeEcDebug();
  });

  window.ecController = { init, fetchStatus, renderStatus, doseEC, toggleAuto };
})();