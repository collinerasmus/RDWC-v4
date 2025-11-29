// pH Control UI
(function(){
  // Resilience stub: define rdwcRange if range.js failed to load so charts still work.
  if (!window.rdwcRange) {
    console.warn('[pH] rdwcRange missing — injecting fallback stub');
    const DAY = 24*60*60*1000;
    window.rdwcRange = {
      RANGES: ['1h','24h','7d','30d','90d','grow','custom'],
      getLastPreset: (key, def='24h') => def,
      saveLastPreset: ()=>{},
      getCustomRange: ()=>({start:null,end:null}),
      saveCustomRange: ()=>{},
      rangeToStartEnd: async (preset, cStart, cEnd, growStartDate) => {
        const now = Date.now();
        let start = now - DAY;
        if (preset==='1h') start = now - 60*60*1000;
        else if (preset==='7d') start = now - 7*DAY;
        else if (preset==='30d') start = now - 30*DAY;
        else if (preset==='90d') start = now - 90*DAY;
        else if (preset==='custom' && cStart && cEnd) {
          const s = new Date(cStart).getTime();
          const e = new Date(cEnd).getTime();
          if (!isNaN(s) && !isNaN(e) && s < e) return {start:s,end:e};
        }
        return {start, end: now};
      }
    };
  }
  const POLL_DEFAULT = 5000; // retained for potential fallback
  // Fallback phDoseChart stub: if chart module not yet defined, create minimal placeholder to avoid errors.
  if (!window.phDoseChart) {
    console.warn('[pH] phDoseChart missing at initPH prelude – installing temporary stub');
    window.phDoseChart = {
      render: async ()=>{ console.warn('[pH] phDoseChart stub render called'); },
      getState: ()=>({}),
      init: ()=>{}
    };
    // Schedule a recheck after other scripts load
    setTimeout(()=>{
      if (window.phDoseChart && window.phDoseChart.init && window.phDoseChart.render.toString().includes('stub')) {
        console.warn('[pH] phDoseChart still stub after delay – chart script may have failed to load');
      }
    }, 2500);
  }
  let pollMs = POLL_DEFAULT; // no local interval; pollingManager drives updates
  let pollTimer = null; // deprecated
  let lastStatus = null;
  let countdownTimer = null;
  let lastPollAt = Date.now();
  let currentRange = { preset: null, start: null, end: null };
  // Recent collapse state (manual only, no auto-hide)
  let recentCollapsed = true;
  let recentHeaderBound = false;
  let recentUserHold = false;
  let recentHideTimer = null;
  // Short-lived fast poll timer for immediate pump state feedback
  let fastPumpTimer = null;
  
  let doseLogCollapsed = localStorage.getItem('ph_dose_log_collapsed') !== 'false'; // default hidden

  function el(id){ return document.getElementById(id); }

  function updateHealthIndicator() {
    const indicator = el('ph-health-indicator');
    if (!indicator) return;
    
    // Determine health based on lastStatus
    if (!lastStatus) {
      indicator.textContent = '—';
      indicator.className = 'ui-status-chip neutral';
      indicator.title = 'Loading...';
      return;
    }
    
    const g = lastStatus.guards || {};
    const hasHardBlocks = !!(g.estop || g.safe_off || g.sensor_stale || g.reservoir);
    const hasSoftBlocks = !!(g.interval || g.daily_cap);
    
    if (hasHardBlocks) {
      indicator.textContent = 'BLOCKED';
      indicator.className = 'ui-status-chip error';
      indicator.title = 'Hard safety blocks active: ' + guardList(g).join(', ');
    } else if (hasSoftBlocks) {
      indicator.textContent = 'WAITING';
      indicator.className = 'ui-status-chip warning';
      indicator.title = 'Automation waiting: ' + guardList(g).join(', ');
    } else {
      indicator.textContent = 'AUTO';
      indicator.className = 'ui-status-chip success';
      indicator.title = 'Automation running';
    }
  }

  function setDoseLogCollapsed(collapsed) {
    doseLogCollapsed = collapsed;
    localStorage.setItem('ph_dose_log_collapsed', collapsed);
    
    const header = el('ph-dose-log-header');
    const body = el('ph-dose-log-body');
    
    if (header) {
      header.innerHTML = collapsed ? 
        '📝 Dose Log (Last 20) ▸' : 
        '📝 Dose Log (Last 20) ▾';
    }
    if (body) {
      body.style.display = collapsed ? 'none' : 'block';
    }
  }

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
    const pumpEl = el('ph-pump');
    const statusEl = el('ph-status');
    const recent = el('ph-recent');
    const resBanner = el('ph-reservoir-banner');
    
    // Update learned value KPI in header
    const learnedEl = el('ph-learned');
    if (learnedEl && s && s.auto && s.auto.learned_ml_per_pH !== null && s.auto.learned_ml_per_pH !== undefined) {
      const learned = s.auto.learned_ml_per_pH;
      learnedEl.textContent = learned > 0 ? `${learned.toFixed(2)} ml/pH` : '— ml/pH';
      learnedEl.title = `Learned: ${learned.toFixed(2)} ml needed to raise pH by 1.0`;
    } else if (learnedEl) {
      learnedEl.textContent = '— ml/pH';
    }
    
    // Update learned value KPI in readings row (legacy, if exists)
    const learnedKPI = el('ph-learned-kpi');
    if (learnedKPI && s && s.auto && s.auto.learned_ml_per_pH !== null && s.auto.learned_ml_per_pH !== undefined && s.auto.learned_ml_per_pH > 0) {
      learnedKPI.style.display = 'inline-block';
      const valueEl = learnedKPI.querySelector('.kpi-value');
      if (valueEl) valueEl.textContent = `${s.auto.learned_ml_per_pH.toFixed(2)} ml/pH`;
    } else if (learnedKPI) {
      learnedKPI.style.display = 'none';
    }
    
    // Update learned value display in Settings section
    updateLearnedDisplay(s);
    const cdPill = el('ph-countdown-pill');
    if(p){ p.textContent = (s && s.ph!=null) ? s.ph.toFixed(2) : '—'; }
    if(band && s){ band.textContent = `Targets ${s.targets.low} – ${s.targets.high}`; }
    
    // Fetch relay status for pump ON/OFF (object schema with is_on)
    fetch('/api/relays/status', {cache:'no-store'})
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!pumpEl || !data || !data.relays) return;
        // API shape: { relays: { dosing_ph_up: { is_on: bool, ... }, ... } }
        const info = data.relays.dosing_ph_up || data.relays['dosing_ph_up'];
        if (info) {
          const isOn = !!(info.is_on || info.state);
          pumpEl.textContent = isOn ? 'ON' : 'OFF';
          pumpEl.style.color = isOn ? '#16a34a' : '#94a3b8';
        }
      })
      .catch(() => {});
    
    // Update controller status KPI
    if(statusEl && s){
      const auto = s.auto || {};
      const holding = auto.holding_reason;
      const remaining = s.remaining_cooldown_s || 0;
      
      if (holding === 'cooldown' || remaining > 0) {
        statusEl.textContent = `Cooldown ${remaining}s`;
        statusEl.style.color = '#f59e0b';
      } else if (holding === 'in_range') {
        statusEl.textContent = 'In Range';
        statusEl.style.color = '#16a34a';
      } else if (holding) {
        statusEl.textContent = holding.replace(/_/g, ' ');
        statusEl.style.color = '#f59e0b';
      } else if (auto.enabled) {
        statusEl.textContent = 'Auto Ready';
        statusEl.style.color = '#3b82f6';
      } else {
        statusEl.textContent = 'Idle';
        statusEl.style.color = '#94a3b8';
      }
    }
    if(guards && s){
      const list = guardList(s.guards);
      guards.textContent = list.length ? list.join(' · ') : 'All clear';
      guards.style.color = list.length ? '#f59e0b' : '#16a34a';
      guards.title = list.length ? guardHints(s.guards) : '';
    }
    if(resBanner && s){ resBanner.style.display = s.guards?.reservoir ? 'block' : 'none'; }
    
    // Update health indicator
    updateHealthIndicator();
    if(recent && s){
      recent.innerHTML = '';
      // Ensure compact, scrollable log even if HTML wasn't updated
      try{ recent.style.maxHeight = '140px'; recent.style.overflowY = 'auto'; recent.style.paddingRight = '6px'; }catch(e){}
      (s.recent||[]).forEach(r => {
        const li = document.createElement('div');
        li.className = 'muted';
        const when = r.ts_utc?.replace('T',' ').replace('Z','');
        li.textContent = `${when} • ${r.action} • ${r.volume_ml||''} ml • ${r.result}${r.reason? ' • '+r.reason: ''}`;
        recent.appendChild(li);
      });

      // Bind header click once
      const hdr = el('ph-recent-header');
      if (hdr && !recentHeaderBound){
        recentHeaderBound = true;
        hdr.addEventListener('click', ()=>{
          setRecentCollapsed(!recentCollapsed);
        });
      }

      // Keep current collapsed state (no auto-show on new events)
      setRecentCollapsed(recentCollapsed);
    }
    // Determine disabled state; maintenance override bypasses cooldown/daily_cap
    const g = s?.guards || {};
  const maint = (s?.maintenance_override === true) || ((window.rdwcSettings?.get('safety.maintenance_override')||'false').toLowerCase() === 'true');
    const allowForce = (window.rdwcSettings?.get('safety.allow_force')||'false').toLowerCase() === 'true';
    const bypass = maint; // no manual force checkbox in UI
    const blockedCooldown = (g.interval || g.daily_cap) && !bypass;
    const blockedHard = !!(g.estop || g.safe_off || g.sensor_stale || g.reservoir);
    const disabled = blockedCooldown || blockedHard;
    ['btnPrime','btnPhPulse03','btnDose1','btnDose5','btnDoseCustom','phCustomMl'].forEach(id=>{
      const e = el(id); if(e){ e.disabled = disabled; e.title = disabled ? 'Blocked by guard(s)' : ''; }
    });
    
    // Update dose status indicator
    const doseStatus = el('ph-dose-status');
    if (doseStatus) {
      if (blockedHard) {
        const reasons = guardList(g).join(', ');
        doseStatus.textContent = '✗ Blocked: ' + reasons;
        doseStatus.style.background = 'rgba(239,68,68,0.08)';
        doseStatus.style.borderColor = 'rgba(239,68,68,0.25)';
        doseStatus.style.color = '#fca5a5';
      } else if (blockedCooldown) {
        const remaining = s?.remaining_cooldown_s || 0;
        doseStatus.textContent = remaining > 0 ? `⏱ Cooldown: ${remaining}s remaining` : '⏱ Cooldown active';
        doseStatus.style.background = 'rgba(245,158,11,0.08)';
        doseStatus.style.borderColor = 'rgba(245,158,11,0.25)';
        doseStatus.style.color = '#fcd34d';
      } else {
        doseStatus.textContent = '✓ Ready to dose';
        doseStatus.style.background = 'rgba(34,197,94,0.08)';
        doseStatus.style.borderColor = 'rgba(34,197,94,0.25)';
        doseStatus.style.color = '#86efac';
      }
    }

    // Countdown pill for min-interval (hide when maintenance override is active)
    if(cdPill){
      if(s?.guards?.interval && !maint){
        cdPill.style.display = 'inline-block';
        updateCountdownPill();
        startCountdown();
      } else {
        cdPill.style.display = 'none';
        stopCountdown();
      }
    }

    // Maintenance override badge visibility
    const badge = el('phMaintBadge');
    if (badge) badge.style.display = maint ? 'inline-block' : 'none';

    // Update automation toggle button label and badges
    const autoBtn = el('btnAutoToggle');
    if (autoBtn) {
      const enabled = !!(s && s.auto && s.auto.enabled);
      autoBtn.textContent = enabled ? 'Disable pH Up automation' : 'Enable pH Up automation';
      autoBtn.title = 'Automatically raises pH when below target band using pH Up';
    }
    
    // Update learned value display (Settings automation panel) - reuse header variable
    const learnedPanelEl = el('phLearnedValue');
    if (learnedPanelEl && s?.auto) {
      const learned = s.auto.learned_ml_per_pH;
      learnedPanelEl.innerHTML = (learned !== null && learned !== undefined && learned > 0)
        ? `Learned: <strong>${learned.toFixed(2)} ml/pH</strong>`
        : `<span style="opacity:0.6;">No learned value yet</span>`;
    }

    // Update caps display from settings (mirror EC caps summary)
    if (window.rdwcSettings) {
      const maxPress = window.rdwcSettings.get('safety.max_seconds_per_press') || '1.5';
      const dailyCap = window.rdwcSettings.get('safety.max_total_seconds_per_24h') || '120';
      const minOff = window.rdwcSettings.get('safety.min_off_window_sec') || '2';
      const m = (id, val) => { const n = el(id); if(n) n.textContent = val + 's'; };
      m('phCapMaxPress', maxPress);
      m('phCapDaily', dailyCap);
      m('phCapMinOff', minOff);
    }
  }
  // Fast poll the pump relay during/after manual runs for snappy UI feedback
  function fastPollPump(seconds){
    try { if (fastPumpTimer) { clearInterval(fastPumpTimer); fastPumpTimer = null; } } catch(_){ }
    const pumpEl = el('ph-pump');
    const until = Date.now() + Math.min(Math.max((seconds||0)*1000, 2000), 12000);
    const tickOnce = () => {
      fetch('/api/relays/status', {cache:'no-store'})
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (!pumpEl || !data || !data.relays) return;
          const info = data.relays.dosing_ph_up || data.relays['dosing_ph_up'];
          if (info){
            const isOn = !!(info.is_on || info.state);
            pumpEl.textContent = isOn ? 'ON' : 'OFF';
            pumpEl.style.color = isOn ? '#16a34a' : '#94a3b8';
          }
        }).catch(()=>{});
    };
    tickOnce();
    fastPumpTimer = setInterval(() => {
      tickOnce();
      if (Date.now() > until) { clearInterval(fastPumpTimer); fastPumpTimer = null; }
    }, 500);
  }
  
  function updateLearnedDisplay(s) {
    // Update learned value display in Settings > Automation section
    const displayBox = el('ph-learned-display');
    const displayValue = el('ph-learned-display-value');
    if (!displayBox || !displayValue) return;
    
    if (s && s.learned_ml_per_pH !== null && s.learned_ml_per_pH !== undefined && s.learned_ml_per_pH > 0) {
      displayBox.style.display = 'block';
      displayValue.textContent = s.learned_ml_per_pH.toFixed(2);
    } else {
      displayBox.style.display = 'none';
      displayValue.textContent = '—';
    }
  }

  async function tick(){
    const s = await fetchStatus();
    renderStatus(s||{});
  }

  function schedule(){ /* legacy no-op; pollingManager now owns cadence */ }

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

  // --- Recent list collapse helper (manual toggle only, no auto-hide) ---
  function setRecentCollapsed(collapsed){
    recentCollapsed = !!collapsed;
    const list = el('ph-recent');
    const hdr = el('ph-recent-header');
    if (list){ list.style.display = collapsed ? 'none' : 'block'; }
    if (hdr){ hdr.textContent = collapsed ? 'Grow Log ▸' : 'Grow Log ▾'; }
  }

  // --- Chart refresh (scoped here to access currentRange) ---
  async function refreshDoseChart(){
    // Delegate to ph_chart.js module
    if (window.phDoseChart && window.phDoseChart.render) {
      try {
        await window.phDoseChart.render({
          start: currentRange.start,
          end: currentRange.end
        });
      } catch(e) {
        console.error('[pH] Chart refresh failed:', e);
      }
    } else {
      const learnedValEl = el('phLearnedValue');
      if (learnedValEl && s?.auto) {
        const v = s.auto.learned_ml_per_pH;
        learnedValEl.textContent = (v && v > 0) ? `${v.toFixed(2)} ml/pH` : '—';
      }

  async function postDose(body){
    // Add force flag when Maintenance override is active
    const maint = (window.rdwcSettings?.get('safety.maintenance_override')||'false').toLowerCase() === 'true';
    const payload = { ...body };
    if (maint) payload.force = true;
    const r = await fetch('/api/ph/dose', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    let j = null; try{ j = await r.json(); }catch(e){}
    if(!r.ok){
      const reasons = (j?.reasons && Array.isArray(j.reasons)) ? j.reasons.join(', ') : null;
      const msg = j?.reason === 'cooldown' && j?.remaining_cooldown_s!=null
        ? `Blocked by min interval (${j.remaining_cooldown_s}s remaining)`
        : (j?.error || reasons || `HTTP ${r.status}`);
      if(window.showToast){ showToast(`Dose blocked: ${msg}`, 'error'); }
      else { alert('Dose blocked: ' + msg); }
      // Update countdown immediately if provided
      if (j?.remaining_cooldown_s!=null) {
        lastStatus = lastStatus || { guards: {} };
        if (!lastStatus.guards) lastStatus.guards = {};
        lastStatus.guards.interval = true;
        lastStatus.guards.since_last_ok_s = Math.max(0, (lastStatus.guards.min_interval_s||0) - j.remaining_cooldown_s);
        updateCountdownPill(); startCountdown();
      }
    } else {
      // immediate refresh of status list, chart, and summary
      if(window.showToast){ 
        const vol = j?.volume_ml ? `${j.volume_ml.toFixed(1)} ml` : `${j?.duration_ms||0} ms`;
        showToast(`Dose complete: ${vol}`, 'success'); 
      }
      tick();
      // Refresh chart and summary to show new dose
      refreshDoseChart().catch(e => console.warn('[pH] Chart refresh after dose failed:', e));
      refreshSummary().catch(e => console.warn('[pH] Summary refresh after dose failed:', e));
    }
  }

  // --- Unified dosing with new endpoints ---
  async function doseUnified(pump, seconds, reason='manual'){
    // Disable button temporarily to enforce min_off visually
    const btnMap = {
      'ph_up': ['btnPrime', 'btnPhPulse03', 'btnDose1', 'btnDose5', 'btnDoseCustom']
    };
    const btns = (btnMap[pump] || []).map(id => el(id)).filter(b => b);
    btns.forEach(b => { b.disabled = true; });
    
    try{
      const r = await fetch(`/api/dose/${pump}`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({seconds, reason, actor:'ui'})
      });
      const j = await r.json();
      
      if(!r.ok || !j.ok){
        const msg = j.message || j.error || j.blocked_by || 'Unknown error';
        if(window.showToast) showToast(`Dose blocked: ${msg}`, 'error');
        else alert('Dose blocked: ' + msg);
      } else {
        if(window.showToast) showToast(`Dosed ${pump} for ${seconds}s`, 'success');
        // Refresh status and dose log
        tick();
        refreshDoseLog();
        // Kick off a brief fast poll so Pump KPI reflects state immediately
        if (pump === 'ph_up') fastPollPump(seconds);
      }
    }catch(e){
      if(window.showToast) showToast(`Dose error: ${e.message}`, 'error');
      else alert('Dose error: ' + e.message);
    } finally {
      // Re-enable after min_off (default 2s)
      setTimeout(()=>{ btns.forEach(b => { b.disabled = false; }); }, 2000);
    }
  }

  async function refreshDoseLog(){
    const table = el('phDoseLogTable');
    if(!table) return;
    
    try{
      const r = await fetch('/api/dose/recent?limit=20', {cache:'no-store'});
      if(!r.ok) throw new Error('HTTP '+r.status);
      const data = await r.json();
      const events = (data.events||[]).filter(e => e.pump === 'ph_up');
      
      if(events.length === 0){
        table.innerHTML = '<tr><td colspan="6" style="padding:12px;text-align:center;">No doses yet</td></tr>';
        return;
      }
      
      table.innerHTML = events.map(e => {
        const time = e.ts_utc ? new Date(e.ts_utc).toLocaleString() : '—';
        const ph_before = e.ph_before != null ? e.ph_before.toFixed(2) : '—';
        const ph_after = e.ph_after != null ? e.ph_after.toFixed(2) : '—';
        const note = e.blocked_by || e.reason || '—';
        const row_style = e.blocked_by ? 'color:#f59e0b;' : '';
        return `<tr style="${row_style}">
          <td style="padding:6px 8px;">${time}</td>
          <td style="padding:6px 8px;">${e.pump}</td>
          <td style="padding:6px 8px;text-align:right;">${e.seconds.toFixed(2)}s</td>
          <td style="padding:6px 8px;text-align:right;">${ph_before}</td>
          <td style="padding:6px 8px;text-align:right;">${ph_after}</td>
          <td style="padding:6px 8px;">${note}</td>
        </tr>`;
      }).join('');
    }catch(e){
      table.innerHTML = '<tr><td colspan="6" style="padding:12px;text-align:center;">Error loading log</td></tr>';
    }
  }

  async function wire(){
    const c = document.getElementById('ph-card');
    if(!c) return;
    
    // Mode buttons and dose log header use inline onclick handlers (see HTML)
    // This ensures they work immediately without waiting for event listener binding
    
    // Use new unified endpoints with time-based dosing (Manual mode)
    el('btnPrime')?.addEventListener('click', ()=> doseUnified('ph_up', 0.2, 'prime'));
    el('btnDose1')?.addEventListener('click', ()=> doseUnified('ph_up', 0.5, 'manual'));
    el('btnDose5')?.addEventListener('click', ()=> doseUnified('ph_up', 1.0, 'manual'));
    el('btnDoseCustom')?.addEventListener('click', ()=>{
      const v = parseFloat(el('phCustomMl').value||'0');
      if(!isFinite(v) || v < 0.1){ alert('Enter seconds ≥ 0.1'); return; }
      doseUnified('ph_up', v, 'custom');
    });
    
    // Dose log refresh
    el('btnRefreshDoseLog')?.addEventListener('click', refreshDoseLog);
    refreshDoseLog(); // Initial load
    // Bind Maintenance Override header toggle
    try{
      const toggle = document.getElementById('ph-maint-toggle');
      if (toggle){
        // Initialize checked state from settings
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
            // Re-poll to reflect guard/badges immediately
            tick();
          }catch(e){ console.warn('[pH] failed to set maintenance_override', e); toggle.checked = !toggle.checked; }
        });
      }
    }catch(e){ console.warn('[pH] maint toggle bind failed', e); }
    el('btnAutoToggle')?.addEventListener('click', async ()=>{
      const enable = !(lastStatus?.auto?.enabled);
      const r = await fetch('/api/ph/auto', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({enable})});
      let j = null; try{ j = await r.json(); }catch(e){}
      if(window.showToast){ showToast(j?.ok ? (enable ? 'pH Up automation enabled' : 'pH Up automation disabled') : (j?.guard||'Error'), j?.ok ? 'success':'error'); }
      // Refresh status to update label and state
      tick();
    });
    
    // Clear learner button (legacy ID)
    el('btnPhClearLearner')?.addEventListener('click', async ()=>{
      if (!confirm('Clear learned pH Up value? This will reset the automation learning.')) return;
      const r = await fetch('/api/ph/auto/learn/reset', {method:'POST'});
      let j = null; try{ j = await r.json(); }catch(e){}
      if(window.showToast){ showToast(j?.ok ? 'pH learner reset' : 'Error resetting learner', j?.ok ? 'success':'error'); }
      tick();
    });
    
    // Clear learner button (new Settings section)
    el('btnClearPhLearned')?.addEventListener('click', async ()=>{
      if (!confirm('Clear learned pH Up value? This will reset the automation learning.')) return;
      const r = await fetch('/api/ph/auto/learn/reset', {method:'POST'});
      let j = null; try{ j = await r.json(); }catch(e){}
      if(window.showToast){ showToast(j?.ok ? 'pH learner reset' : 'Error resetting learner', j?.ok ? 'success':'error'); }
      // Update the learned display in Settings section
      updateLearnedDisplay();
      tick();
    });
    // Wire range controls (matching Trends template) - await to ensure range is loaded
    await wireRangeControls();
    
  // CSV export uses current range (support both legacy and new ids)
  el('btnPhExport')?.addEventListener('click', ()=>{ exportCSV(); });

    // pH Calibration event handlers (for inline calibration in pH Settings)
    const msgEl = el('ph-calib-msg-inline');
    const logEl = el('ph-calib-log-inline');

    // Helper to format time HH:MM:SS
    const ts = () => new Date().toLocaleTimeString();

    // Central log append with type coloring
    function appendLog(message, type='info'){
      if(!logEl) return;
      const div = document.createElement('div');
      let color = '#9ca3af';
      if(type==='error') color = '#f87171';
      else if(type==='warn') color = '#fbbf24';
      else if(type==='success') color = '#34d399';
      div.style.color = color;
      div.textContent = `[${ts()}] ${message}`;
      logEl.appendChild(div);
      logEl.scrollTop = logEl.scrollHeight;
    }

    // Unified message setter (keeps last status prominent)
    function setMsg(message, ok=true, typeOverride){
      if(msgEl){
        msgEl.textContent = message || '';
        msgEl.style.color = ok ? '#e5e7eb' : '#fca5a5';
      }
      const t = typeOverride || (ok ? 'info' : 'error');
      appendLog(message, t);
    }

    // Current pH inline + range coloring (basic heuristic using settings if present)
    function setCurrent(v){
      const sp = el('ph-current-inline');
      if(!sp) return;
      if(v==null){ sp.textContent = '—'; sp.style.color = '#9ca3af'; return; }
      const val = Number(v);
      sp.textContent = val.toFixed(2);
      let low = parseFloat(window.rdwcSettings?.get('targets.ph_low') || '5.5');
      let high = parseFloat(window.rdwcSettings?.get('targets.ph_high') || '6.5');
      if(val < low - 0.05) sp.style.color = '#60a5fa'; // low = blue
      else if(val > high + 0.05) sp.style.color = '#f87171'; // high = red
      else sp.style.color = '#34d399'; // in band
    }

    const setBanner = (on) => { const b = el('ph-calib-banner-inline'); if (b) b.style.display = on? 'block':'none'; };

    // Disable/enable all calibration action buttons during operations
    const calibBtnIds = [
      'btnPhReadInline','btnPhStabilizeInline','btnPhStatusInline',
      'btnPhCalibrateInline','btnPhClearInline',
      'btnLedsOnInline','btnLedsOffInline','btnLedsBlinkInline'
    ];
    function setCalibBusy(busy, workingLabel){
      calibBtnIds.forEach(id => {
        const b = el(id); if(!b) return; if(busy){ b.disabled = true; if(workingLabel && id==='btnPhCalibrateInline'){ b.dataset._orig = b.textContent; b.textContent = workingLabel; } }
        else { b.disabled = false; if(b.dataset._orig){ b.textContent = b.dataset._orig; delete b.dataset._orig; } }
      });
      if(busy) appendLog('⏳ Working...', 'warn');
    }

    const checkCaps = async ()=>{
      try{
        const r = await (await fetch('/calib/ph/caps?t='+Date.now(), {cache:'no-store'})).json();
        setBanner(!(r && r.enabled));
      }catch(e){ /* noop */ }
    };

    el('btnPhReadInline')?.addEventListener('click', async ()=>{
      setCalibBusy(true);
      try{
        setMsg('Reading (waits for sensor poller to pause, ~8s)...');
        const resp = await fetch('/calib/ph/read?t='+Date.now(), {cache:'no-store'});
        const r = await resp.json();
        if (r && r.ok){ 
          setCurrent(r.value); 
          setMsg(`pH: ${Number(r.value).toFixed(2)}`, true, 'success'); 
        } else { 
          const hint = (r && r.note === 'NoData') 
            ? 'NoData — probe not responding. Check: 1) sensor power relay ON, 2) I²C wiring, 3) /fix_ezo to verify address 0x63.' 
            : ((r && r.note) || 'Read failed');
          setMsg(hint, false); 
        }
      }catch(e){ setMsg(`Read failed (network): ${e.message}`, false); }
      finally { setCalibBusy(false); }
    });

    el('btnPhStabilizeInline')?.addEventListener('click', async ()=>{
      setCalibBusy(true);
      try{
        setMsg('Waiting for stable reading...');
        const resp = await fetch('/calib/ph/read_stable?t='+Date.now(), {cache:'no-store'});
        const r = await resp.json();
        if (r && r.ok){ 
          setCurrent(r.value); 
          setMsg(`Stable pH: ${Number(r.value).toFixed(2)} (σ=${r.std?.toFixed(3)||'?'})`, true, 'success'); 
        } else { 
          const hint = (r && r.note && r.note.includes('NoData')) 
            ? 'NoData — probe not responding. Check sensor power & I²C wiring.' 
            : ((r && r.note) || 'Stabilize failed');
          setMsg(hint, false); 
        }
      }catch(e){ setMsg(`Stabilize failed (network): ${e.message}`, false); }
      finally { setCalibBusy(false); }
    });

    el('btnPhStatusInline')?.addEventListener('click', async ()=>{
      setCalibBusy(true);
      try{
        const resp = await fetch('/calib/ph/status?t='+Date.now(), {cache:'no-store'});
        const r = await resp.json();
        if (r && r.ok){ 
          const pts = r.points ? (r.points.length? r.points.join(', ') : 'none') : 'none';
          setMsg(`Calibration: ${pts}`); 
        } else { 
          const hint = (r && r.note && r.note.includes('NoData')) 
            ? 'NoData — probe not responding. Check sensor power & I²C wiring.' 
            : ((r && r.note) || 'Status failed');
          setMsg(hint, false); 
        }
      }catch(e){ setMsg(`Status failed (network): ${e.message}`, false); }
      finally { setCalibBusy(false); }
    });

    el('btnPhCalibrateInline')?.addEventListener('click', async ()=>{
      setCalibBusy(true, 'Working…');
      try{
        const kindSel = el('ph-buffer-kind-inline');
        const valInp = el('ph-buffer-val-inline');
        const kind = (kindSel && kindSel.value) || 'mid';
        const val = parseFloat(valInp && valInp.value || '7.00');
        if(!isFinite(val)) { setMsg('Invalid buffer value', false); return; }
        const ep = kind==='low'? 'low' : kind==='high'? 'high' : 'mid';
        setMsg(`Sending ${ep} calibration (${val.toFixed(2)})...`);
        const resp = await fetch(`/calib/ph/${ep}?value=${encodeURIComponent(val.toFixed(2))}`, {method:'POST'});
        let r = null; try{ r = await resp.json(); }catch(_){ /* ignore */ }
        if (r && r.ok){ setMsg(r.note || 'Calibration OK', true, 'success'); }
        else { setMsg((r && r.note) || `Calibration failed (HTTP ${resp.status})`, false); }
      }catch(e){ setMsg('Calibration failed (network)', false); }
      finally{ setCalibBusy(false); }
    });

    el('btnPhClearInline')?.addEventListener('click', async ()=>{
      setCalibBusy(true);
      try{
        const r = await (await fetch('/calib/ph/clear', {method:'POST'})).json();
        if (r && r.ok){ setMsg(r.note || 'Calibration cleared', true, 'warn'); }
        else { setMsg((r && r.note) || 'Clear rejected', false); }
      }catch(e){ setMsg('Clear failed (network)', false); }
      finally { setCalibBusy(false); }
    });

    el('btnLedsOnInline')?.addEventListener('click', async ()=>{ 
      setCalibBusy(true);
      try{ const r=await (await fetch('/calib/leds/on',{method:'POST'})).json(); setMsg(r.ok? 'LEDs on' : 'LEDs on failed', !!r.ok, r.ok?'success':'error'); }catch(e){ setMsg('LEDs on failed (network)', false);} 
      finally { setCalibBusy(false); }
    });

    el('btnLedsOffInline')?.addEventListener('click', async ()=>{ 
      setCalibBusy(true);
      try{ const r=await (await fetch('/calib/leds/off',{method:'POST'})).json(); setMsg(r.ok? 'LEDs off' : 'LEDs off failed', !!r.ok, r.ok?'success':'error'); }catch(e){ setMsg('LEDs off failed (network)', false);} 
      finally { setCalibBusy(false); }
    });

    el('btnLedsBlinkInline')?.addEventListener('click', async ()=>{ 
      setCalibBusy(true);
      try{ const r=await (await fetch('/calib/leds/blink',{method:'POST'})).json(); setMsg(r.ok? `Blink x${r.count||''}` : 'Blink failed', !!r.ok, r.ok?'success':'error'); }catch(e){ setMsg('Blink failed (network)', false);} 
      finally { setCalibBusy(false); }
    });

    // Check calibration capabilities on init
    checkCaps();

    // --- Manual Dosing 0.3s button (moved from Quick Pulse section) ---
    el('btnPhPulse03')?.addEventListener('click', ()=> doseUnified('ph_up', 0.3, 'pulse'));

    // --- pH Pump Calibration buttons ---
    el('btnPhPumpPrime')?.addEventListener('click', async ()=>{
      const btn = el('btnPhPumpPrime');
      if(btn) btn.disabled = true;
      try{
        await doseUnified('ph_up', 3.0, 'calibration_prime');
        if(window.showToast) showToast('Primed pH pump for 3s', 'success');
      } finally {
        if(btn) btn.disabled = false;
      }
    });
    
    el('btnPhPumpRun')?.addEventListener('click', async ()=>{
      const durationEl = el('phPumpDuration');
      const duration = parseFloat(durationEl?.value || '10');
      if(!isFinite(duration) || duration < 1 || duration > 60){ 
        alert('Duration must be 1-60 seconds'); 
        return; 
      }
      const btn = el('btnPhPumpRun');
      if(btn) { btn.disabled = true; btn.textContent = `Running ${duration}s...`; }
      try{
        await doseUnified('ph_up', duration, 'calibration_run');
        if(window.showToast) showToast(`Ran pH pump for ${duration}s - measure output now`, 'success');
      } finally {
        if(btn) { btn.disabled = false; btn.textContent = 'Run'; }
      }
    });
    
    el('btnPhPumpCommit')?.addEventListener('click', async ()=>{
      const durationEl = el('phPumpDuration');
      const measuredEl = el('phPumpMeasured');
      const duration = parseFloat(durationEl?.value || '10');
      const measured = parseFloat(measuredEl?.value || '0');
      
      if(!isFinite(duration) || duration < 1){ alert('Enter valid duration'); return; }
      if(!isFinite(measured) || measured <= 0){ alert('Enter measured ml > 0'); return; }
      
      const rate = measured / duration;
      if(!confirm(`Commit pH Up pump rate: ${rate.toFixed(3)} ml/s?`)) return;
      
      try{
        const r = await fetch('/api/settings', {
          method:'PUT', 
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ 'dosing.ph_up_ml_per_sec': rate.toFixed(3) })
        });
        if(!r.ok) throw new Error('HTTP '+r.status);
        // Update display
        const rateEl = el('phPumpCurrentRate');
        if(rateEl) rateEl.textContent = rate.toFixed(3);
        if(window.showToast) showToast(`pH pump rate saved: ${rate.toFixed(3)} ml/s`, 'success');
        // Clear measured input for next calibration
        if(measuredEl) measuredEl.value = '';
      }catch(e){
        if(window.showToast) showToast('Failed to save pump rate', 'error');
        console.error('[pH] Pump calibration commit failed:', e);
      }
    });
    
    // Load current pump rate on init
    try{
      const rate = window.rdwcSettings?.get('dosing.ph_up_ml_per_sec');
      const rateEl = el('phPumpCurrentRate');
      if(rateEl && rate) rateEl.textContent = parseFloat(rate).toFixed(3);
    }catch(e){}

    // --- Save pH Settings button ---
    el('btnSavePhSettings')?.addEventListener('click', async ()=>{
      const btn = el('btnSavePhSettings');
      if(btn) { btn.disabled = true; btn.textContent = 'Saving...'; }
      
      try{
        const settings = {};
        const fields = [
          ['phTargetLow', 'targets.ph_low'],
          ['phTargetHigh', 'targets.ph_high'],
          ['phAlertLow', 'alerts.ph_low'],
          ['phAlertHigh', 'alerts.ph_high'],
          ['phUpMlPerSec', 'dosing.ph_up_ml_per_sec'],
          ['phMixDelay', 'dosing.ph_mix_delay_s'],
          ['phMaxMlHour', 'dosing.ph_up_max_ml_per_hour'],
          ['phMaxMlDay', 'dosing.ph_up_max_ml_per_day']
        ];
        
        for(const [elemId, settingKey] of fields){
          const elem = el(elemId);
          if(elem && elem.value !== ''){
            settings[settingKey] = elem.value;
          }
        }
        
        if(Object.keys(settings).length === 0){
          if(window.showToast) showToast('No changes to save', 'warning');
          return;
        }
        
        const r = await fetch('/api/settings', {
          method:'PUT', 
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(settings)
        });
        if(!r.ok) throw new Error('HTTP '+r.status);
        
        if(window.showToast) showToast('pH settings saved', 'success');
        tick(); // Refresh status to pick up new targets
      }catch(e){
        if(window.showToast) showToast('Failed to save pH settings', 'error');
        console.error('[pH] Save settings failed:', e);
      } finally {
        if(btn) { btn.disabled = false; btn.textContent = 'Save pH Settings'; }
      }
    });

    // Load current settings into form fields
    try{
      const settingsMap = [
        ['phTargetLow', 'targets.ph_low', '5.8'],
        ['phTargetHigh', 'targets.ph_high', '6.2'],
        ['phAlertLow', 'alerts.ph_low', '5.5'],
        ['phAlertHigh', 'alerts.ph_high', '6.5'],
        ['phUpMlPerSec', 'dosing.ph_up_ml_per_sec', ''],
        ['phMixDelay', 'dosing.ph_mix_delay_s', ''],
        ['phMaxMlHour', 'dosing.ph_up_max_ml_per_hour', ''],
        ['phMaxMlDay', 'dosing.ph_up_max_ml_per_day', '']
      ];
      for(const [elemId, settingKey, fallback] of settingsMap){
        const elem = el(elemId);
        const val = window.rdwcSettings?.get(settingKey);
        if(elem && (val || fallback)) elem.value = val || fallback;
      }
    }catch(e){ console.warn('[pH] Failed to load settings into form:', e); }

    // listen for settings UI updates to ui.sensors_poll_ms
    window.addEventListener('settings:ui', (ev)=>{
      const ms = ev.detail?.['ui.sensors_poll_ms'];
      if(ms){ pollMs = parseInt(ms)||POLL_DEFAULT; schedule(); }
    });

    // Maintenance override badge visibility handled in renderStatus
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
    // Wire dropdown (standardized template)
    const selectEl = el('phDoseRangeSelect');
    if (selectEl){
      // Disable Grow option if no grow_start_date
      const growDate = window.rdwcSettings?.get('general.grow_start_date');
      if (!growDate){
        const growOpt = selectEl.querySelector('option[value="grow"]');
        if (growOpt){
          growOpt.disabled = true;
          growOpt.textContent = 'Entire Grow (set start date)';
        }
        if (lastPreset === 'grow') currentRange.preset = '24h';
      }
      selectEl.value = currentRange.preset;
      selectEl.addEventListener('change', ()=>{
        const val = selectEl.value;
        selectPreset(val);
        // Enable/disable custom inputs
        toggleCustomInputs(val === 'custom');
      });
      // Initial custom inputs state
      toggleCustomInputs(selectEl.value === 'custom');
    }

    // Wire custom range apply
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
          const selectEl2 = el('phDoseRangeSelect');
          if (selectEl2) selectEl2.value = 'custom';
        }
      });
    }
    
    // Load initial range (await to ensure start/end are set before chart refresh)
    await loadRange(currentRange.preset);
  }
  
  async function selectPreset(preset){
    currentRange.preset = preset;
    window.rdwcRange.saveLastPreset('rdwc.ph.range', preset);
    // Update dropdown value (if present)
    const selectEl = el('phDoseRangeSelect');
    if (selectEl && selectEl.value !== preset){ selectEl.value = preset; }
    
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
    
    // Auto-populate datetime inputs with current range so user knows what they're viewing
    const fromEl = el('phDoseFrom');
    const toEl = el('phDoseTo');
    if (fromEl && toEl && range.start && range.end) {
      // Convert timestamps to datetime-local format (YYYY-MM-DDTHH:mm)
      const formatForInput = (ts) => {
        const d = new Date(ts);
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        const hh = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
      };
      fromEl.value = formatForInput(range.start);
      toEl.value = formatForInput(range.end);
      // Disable inputs unless custom preset selected
      const isCustom = currentRange.preset === 'custom';
      fromEl.disabled = !isCustom;
      toEl.disabled = !isCustom;
      const applyEl = el('phDoseApply');
      if (applyEl) applyEl.disabled = !isCustom;
      // Dim disabled inputs for clarity
      const dimStyle = 'opacity:0.55;';
      fromEl.style.opacity = isCustom ? '1' : '0.55';
      toEl.style.opacity = isCustom ? '1' : '0.55';
    }
    
    // Refresh chart and summary
    await refreshDoseChart();
    await refreshSummary();
  }

  function toggleCustomInputs(enabled){
    const fromEl = el('phDoseFrom');
    const toEl = el('phDoseTo');
    const applyEl = el('phDoseApply');
    if(!fromEl || !toEl || !applyEl) return;
    fromEl.disabled = !enabled; toEl.disabled = !enabled; applyEl.disabled = !enabled;
    fromEl.style.opacity = enabled ? '1' : '0.55';
    toEl.style.opacity = enabled ? '1' : '0.55';
  }
  
  function exportCSV(){
    // Try to use chart state first, fallback to currentRange
    let start = currentRange.start;
    let end = currentRange.end;
    
    if (window.phDoseChart && window.phDoseChart.getState) {
      const state = window.phDoseChart.getState();
      if (state.lastStart) start = new Date(state.lastStart).getTime();
      if (state.lastEnd) end = new Date(state.lastEnd).getTime();
    }
    
    if (!start || !end) {
      // Fallback to 7d
      window.open('/api/ph/dose_log.csv?hours=168', '_blank');
      return;
    }
    
    const startISO = new Date(start).toISOString();
    const endISO = new Date(end).toISOString();
    window.open(`/api/ph/dose_log.csv?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=5000`, '_blank');
  }

  // Initialize when DOM is ready (works even if script loads after DOMContentLoaded)
  async function initPH(){
    await wire();  // This includes wireRangeControls which sets currentRange
    
    // Initialize dose log state AFTER wire() completes
    setDoseLogCollapsed(doseLogCollapsed);
    
    tick();
    // Register with centralized polling manager (main loop ~6s)
    if(window.pollingManager && !window.__phPollingRegistered){
      window.__phPollingRegistered = true;
      window.pollingManager.register('ph-status', async ()=>{ await tick(); }, 'main');
    }
    refreshSummary();
    // Ensure header text is set even before first status render
    const _hdr = document.getElementById('ph-recent-header');
    if (_hdr && !_hdr.textContent.includes('Grow Log')){
      _hdr.textContent = 'Grow Log ▾';
    }
    // Fallback removed - recent list state managed manually by user
    // Chart will have been rendered by wireRangeControls → loadRange
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPH);
  } else {
    // DOM already loaded; initialize immediately
    initPH();
  }
  
  // Export functions to window for inline onclick handlers
  window.phSetDoseLogCollapsed = setDoseLogCollapsed;
  window.phToggleDoseLog = function() {
    setDoseLogCollapsed(!doseLogCollapsed);
  };
})();
  async function refreshSummary(){
    try{
      // Prefer unified dose_events (compute ml from seconds * rate) as fallback
      const rate = parseFloat(window.rdwcSettings?.get('dosing.ph_up_ml_per_sec') || '25');
      
      // Try legacy pH dose log first (has volume_ml)
      let todayMl = 0, weekMl = 0, hasLegacy = false;
      try {
        const log = await (await fetch('/api/ph/dose_log?hours=24',{cache:'no-store'})).json();
        const vols = (log||[]).map(e => e.volume_ml);
        hasLegacy = vols.some(v => v!=null);
        if (hasLegacy) {
          todayMl = (log||[]).reduce((acc,e)=> acc + (e.volume_ml||0), 0);
          const weekRows = await (await fetch('/api/ph/dose_summary?days=7',{cache:'no-store'})).json();
          weekMl = (weekRows||[]).reduce((acc,r)=> acc + (r.total_ml||0), 0);
        }
      } catch(e) { /* ignore */ }
      
      // Fallback: compute from unified dose_events
      if (!hasLegacy) {
        const calc = async (hours) => {
          try {
            const r = await fetch(`/api/dose/recent?hours=${hours}`, {cache:'no-store'});
            if (!r.ok) return 0;
            const j = await r.json();
            const ev = (j.events||[]).filter(e => !e.blocked_by && e.pump === 'ph_up');
            return ev.reduce((acc, e) => acc + (Number(e.seconds||0) * rate), 0);
          } catch(e) { return 0; }
        };
        todayMl = await calc(24);
        weekMl = await calc(24*7);
      }
      
      const tEl = document.getElementById('ph-total-today'); 
      if (tEl) {
        const valEl = tEl.querySelector('.kpi-value');
        if (valEl) valEl.textContent = todayMl > 0 ? `${todayMl.toFixed(1)} ml` : `— ml`;
        else tEl.textContent = todayMl > 0 ? `Today: ${todayMl.toFixed(1)} ml` : `Today: — ml`;
      }
      const wEl = document.getElementById('ph-total-week'); 
      if (wEl) {
        const valEl = wEl.querySelector('.kpi-value');
        if (valEl) valEl.textContent = weekMl > 0 ? `${weekMl.toFixed(1)} ml` : `— ml`;
        else wEl.textContent = weekMl > 0 ? `Week: ${weekMl.toFixed(1)} ml` : `Week: — ml`;
      }
      
      // Calibration banner: show only when legacy events exist + all null + invalid rate
      const banner = document.getElementById('ph-calib-banner');
      if (banner && hasLegacy) {
        const invalidRate = !rate || rate <= 0;
        banner.style.display = invalidRate ? 'block' : 'none';
      } else if (banner) {
        banner.style.display = 'none';
      }
    }catch(e){ /* ignore */ }
  }



  