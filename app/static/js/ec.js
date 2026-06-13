// EC Control UI
(function(){
  const POLL_DEFAULT = 5000; // retained for potential fallback (unused)
  let endpointMode = null; // 'dose_api' or 'relay_pulse'
  let pollMs = POLL_DEFAULT; // no local interval; pollingManager drives updates
  lastStatus = null;
  let countdownTimer = null;
  let lastPollAt = Date.now();

  function el(id){ return document.getElementById(id); }

  async function fetchStatus(){
    try{
      const r = await fetch('/api/ec/status', {cache: 'no-store'});
      if(!r.ok) throw new Error('status');
      return await r.json();
    }catch(e){ return null; }
  }

  async function updatePumpStatuses(){
    try {
      const relayRes = await fetch('/api/relays/status', {cache: 'no-store'});
      if (!relayRes.ok) return;
      const relayData = await relayRes.json();
      const relays = relayData?.relays || {};
      const growStatus = el('growPumpStatus');
      const microStatus = el('microPumpStatus');
      const bloomStatus = el('bloomPumpStatus');

      const setStatus = (el, isOn) => {
        if (!el) return;
        el.textContent = isOn ? 'Running' : 'Idle';
        el.style.color = isOn ? '#16a34a' : '#9ca3af';
      };

      setStatus(growStatus, relays.dosing_grow?.is_on === true);
      setStatus(microStatus, relays.dosing_micro?.is_on === true);
      setStatus(bloomStatus, relays.dosing_bloom?.is_on === true);
    } catch (e) {
      console.warn('[EC] Failed to fetch pump status for calibration:', e);
    }
  }

  // Always use unified EC dosing endpoint
  async function detectDoseMode(){ return 'ec_unified_v1'; }

  // Health DB fetch removed from EC header (redundant with global health chip)

  function guardActive(g){
    if(!g) return false;
    return g.estop || g.sensor_stale || g.interval || g.daily_cap || g.reservoir || g.mix_lock || g.ph_settle || g.ec_high;
  }

  function guardList(g){
    const out = [];
    if(g.estop) out.push('E-STOP');
    if(g.sensor_stale) out.push('Sensor stale');
    if(g.ec_high) out.push('EC hard limit');
    if(g.ph_settle) out.push('pH settling');
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
    if(g.ec_high) tips.push('EC hard limit: EC is at or above the configured safety ceiling.');
    if(g.ph_settle) tips.push('pH settling: waiting for pH dosing to settle before EC dosing.');
    if(g.interval) tips.push('Min interval: Waiting between doses.');
    if(g.daily_cap) tips.push('Daily cap reached.');
    if(g.reservoir) tips.push('Reservoir set to 0 L; dosing disabled.');
    if(g.mix_lock) tips.push('pH or EC dose in progress.');
    return tips.join('\n');
  }

  async function renderStatus(s){
    lastStatus = s;
    lastPollAt = Date.now();
    const ecVal = el('ec-current');
    const band = el('ec-band');
    const guards = el('ec-guards');
    const statusEl = el('ec-status');
    const resBanner = el('ec-reservoir-banner');
    const cdPill = el('ec-countdown-pill');
    
    if(ecVal){ ecVal.textContent = (s && s.ec_ms_cm!=null) ? s.ec_ms_cm.toFixed(3) : '—'; }
    if(band && s){
      const rawLow = (s.targets && s.targets.low!=null) ? Number(s.targets.low) : null;
      const rawHigh = (s.targets && s.targets.high!=null) ? Number(s.targets.high) : null;
      const low = rawLow!=null ? rawLow.toFixed(2) : '—';
      const high = rawHigh!=null ? rawHigh.toFixed(2) : '—';
      band.textContent = `${low} – ${high}`;
      // Optional KPI row element if present
      const kpiTargets = el('ec-kpi-targets');
      if(kpiTargets){
        const valEl = kpiTargets.querySelector('.kpi-value');
        if(valEl) valEl.textContent = `${low}–${high} mS/cm`;
        else kpiTargets.textContent = `${low}–${high} mS/cm`;
      }
      // Update Parameters scheduler target chip
      const schedChip = el('ecSchedulerTargetChip');
      if(schedChip) schedChip.textContent = `Target: ${low}–${high} mS/cm`;
      // Update EC setpoint display from scheduler-derived targets
      const setpointEl = el('ecSetpoint');
      if(setpointEl && rawLow!=null && rawHigh!=null){
        const sp = (rawLow + rawHigh) / 2;
        setpointEl.textContent = (!Number.isNaN(sp)) ? sp.toFixed(2) : '—';
      }
    }
    if(guards && s){
      const list = guardList(s.guards);
      guards.textContent = list.length ? list.join(' · ') : 'All clear';
      guards.style.color = list.length ? '#f59e0b' : '#16a34a';
      guards.title = list.length ? guardHints(s.guards) : '';
    }
    if(resBanner && s){ resBanner.style.display = s.guards?.reservoir ? 'block' : 'none'; }

    // Update controller status KPI
    if(statusEl && s){
      const auto = s.auto || {};
      const holding = auto.holding_reason;

      if (holding && holding.includes('interval')) {
        // Parse "interval (749s)" format
        const match = holding.match(/(\d+)/);
        const seconds = match ? parseInt(match[1], 10) : 0;
        statusEl.textContent = `Interval ${seconds}s`;
        statusEl.style.color = '#f59e0b';
        startCountdown();
      } else if (holding === 'in_range') {
        statusEl.textContent = 'In Range';
        statusEl.style.color = '#16a34a';
        stopCountdown();
      } else if (holding) {
        const holdingLabels = {
          ec_high: 'EC hard limit',
          ph_settle: 'pH settling',
          sensor_stale: 'Sensor stale',
          mix_lock: 'Mix lock',
          reservoir: 'Reservoir',
          estop: 'E-STOP'
        };
        statusEl.textContent = holdingLabels[holding] || holding.replace(/_/g, ' ');
        statusEl.style.color = '#f59e0b';
        stopCountdown();
      } else if (auto.enabled) {
        statusEl.textContent = 'Auto Ready';
        statusEl.style.color = '#3b82f6';
        stopCountdown();
      } else {
        statusEl.textContent = 'Idle';
        statusEl.style.color = '#94a3b8';
        stopCountdown();
      }
    }

    // Freshness indicator
    // Removed freshness dot in EC header (uses global health indicator)

    // Override badge in header
    const overrideBadge = el('ecOverrideBadge');
    if(overrideBadge){
      const override = (window.rdwcSettings?.get('safety.maintenance_override')||'false').toLowerCase() === 'true';
      overrideBadge.style.display = override ? 'inline-block' : 'none';
    }
    
    // Update learned value display in Settings section
    updateLearnedDisplay(s);

    // Update pump status indicators in calibration section
    await updatePumpStatuses();

    // Update controller health chip after status changes
    updateHealthIndicator();
    
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
        // Success if K=0.1 (correct for K=0.1 probes), warning for other values
        // Use tolerance for floating point comparison
        kChip.className = 'ui-status-chip ' + (Math.abs(k - 0.1) < 0.01 ? 'success' : (k > 0 ? 'warning' : 'neutral'));
        kChip.title = Math.abs(k - 0.1) < 0.01 ? 'K=0.1 (correct for K=0.1 probe)' : (k > 0 ? `K=${k} (verify probe type)` : 'K factor not set');
      }

      // Update Cal chip
      const calChip = el('ecCalChip');
      if (calChip) {
        calChip.textContent = cal ? `Cal: ${cal}` : 'Cal: —';
        const isCalibrated = cal && (cal.includes('one-point') || cal.includes('two-point') || cal.includes('dry'));
        calChip.className = 'ui-status-chip ' + (isCalibrated ? 'success' : 'neutral');
        calChip.title = cal || 'Calibration status unknown';
      }
    } catch (e) {
      // Silently fail - chips will show default values
    }
  }

  function updateLearnedDisplay(s){
    const displayBox = el('ec-learned-display');
    const displayValue = el('ec-learned-display-value');
    if(!displayBox || !displayValue) return;

    const learned = (s && s.auto && s.auto.learned_ml_per_mScm != null)
      ? s.auto.learned_ml_per_mScm
      : (s && s.learned_ml_per_mScm);

    if(learned !== null && learned !== undefined && Number(learned) > 0){
      displayBox.style.display = 'block';
      displayValue.textContent = Number(learned).toFixed(2);
    } else {
      displayBox.style.display = 'none';
      displayValue.textContent = '—';
    }
  }

  // Toggle EC automation (header button)
  async function toggleAuto(){
    try{
      const res = await fetch('/api/ec/auto/toggle', {method:'POST'});
      const j = await res.json().catch(()=>({}));
      if(!res.ok){
        showToast(j.error || 'Failed to toggle EC auto', 'error');
        return;
      }
      showToast('EC automation toggled', 'success');
      const s2 = await fetchStatus();
      if(s2) renderStatus(s2);
    }catch(e){
      showToast('EC auto toggle error: '+e.message, 'error');
    }
  }

  function startCountdown(){
    if(countdownTimer) return;
    countdownTimer = setInterval(updateCountdownPill, 1000);
  }

  function stopCountdown(){
    if(countdownTimer){ clearInterval(countdownTimer); countdownTimer = null; }
  }

  function updateCountdownPill(){
    const statusEl = el('ec-status');
    if(!statusEl || !lastStatus) return;

    const auto = lastStatus.auto || {};
    const holding = auto.holding_reason;

    if (!holding || !holding.includes('interval')) {
      stopCountdown();
      return;
    }

    // Extract initial seconds from "interval (749s)" format
    const match = holding.match(/(\d+)/);
    const initialSeconds = match ? parseInt(match[1], 10) : 0;

    // Estimate remaining time locally since last poll
    const elapsed = Math.floor((Date.now() - lastPollAt) / 1000);
    const remaining = Math.max(0, initialSeconds - elapsed);

    if (remaining <= 0) {
      statusEl.textContent = 'Interval clear';
      statusEl.style.color = '#16a34a';
      stopCountdown();
    } else {
      statusEl.textContent = `Interval ${remaining}s`;
      statusEl.style.color = '#f59e0b';
    }
  }

  function startPoll(){ /* legacy no-op; pollingManager manages cadence */ }

  function stopPoll(){ /* legacy no-op */ }

  function showToast(msg, type){
    if(window.showToast) window.showToast(msg, type);
    else console.log(`[EC] ${type}: ${msg}`);
  }

  function exportCSV24h(){
    window.open('/api/ec/dose_log.csv?hours=24', '_blank');
  }

  // Custom mix ratio UI removed (managed in Settings); stub retained for safety.
  function setupMixRatioToggle(){ /* no-op */ }

  // --- Unified dosing ---
  async function doseUnified(pump, seconds, reason='ui-manual'){
    // Debounce per pump
    window.__ecPulseLast = window.__ecPulseLast || {};
    const now = Date.now();
    const last = window.__ecPulseLast[pump] || 0;
    if(now - last < 400){ return; }
    window.__ecPulseLast[pump] = now;
    // Clamp client-side
    if(typeof seconds !== 'number' || isNaN(seconds)){
      showToast('Invalid seconds value', 'error');
      return;
    }
    if(seconds < 0.1) seconds = 0.1;
    if(seconds > 3.0) seconds = 3.0;

    const btnMap = {
      'grow': ['btnRapidGrow'],
      'micro': ['btnRapidMicro'],
      'bloom': ['btnRapidBloom']
    };
    const btns = (btnMap[pump] || []).map(id => el(id)).filter(b => b);
    btns.forEach(b => { b.disabled = true; b.classList.add('loading'); });
    
    try{
      const mode = await detectDoseMode();
      let r, j;
      if(mode === 'ec_unified_v1'){
        r = await fetch('/api/ec/dose', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({pump, seconds, reason, actor:'user'}) });
        j = await r.json().catch(()=>({}));
      } else {
        r = await fetch(`/api/dose/${pump}`, { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({seconds, reason, actor:'ui'}) });
        j = await r.json().catch(()=>({}));
      }
      
      if(!r.ok || (!j.ok && j.error)){
        const msg = j.error || j.message || j.blocked_by || 'Unknown error';
        showToast(`Dose blocked: ${msg}`, 'error');
      } else {
        showToast(`Dose executed (${pump}, ${seconds.toFixed(2)}s)`, 'success');
        try{ if(window.ecChart && window.ecChart.refresh){ window.ecChart.refresh(); } }catch(_){/*noop*/}
        const s2 = await fetchStatus();
        if(s2) renderStatus(s2);
        refreshDoseLog();
        updateEcTotals().catch(()=>{});
        refreshLastThree();
      }
    }catch(e){
      showToast(`Dose error: ${e.message}`, 'error');
    } finally {
      setTimeout(()=>{ btns.forEach(b => { b.disabled = false; b.classList.remove('loading'); }); }, 600);
    }
  }

  // Expose legacy global for inline handlers before module boot
  // Some templates call window.doseEC directly; keep alias stable.
  window.doseEC = doseUnified;

  // === EC Pump Calibration Functions ===
  // Calibration constants
  const CALIB = {
    PRIME_DURATION: 0.5,      // seconds
    DEFAULT_RUN_DURATION: 10, // seconds
    MIN_RUN_DURATION: 5,      // seconds
    MAX_RUN_DURATION: 60,     // seconds
    MIN_MEASUREMENT: 0.1      // ml or seconds
  };

  async function loadPumpRates(){
    // Fetch current rates from backend and display them
    try{
      const r = await fetch('/calib/dose/pumps', {cache:'no-store'});
      if(!r.ok) {
        console.warn('[EC Calib] Failed to fetch pump rates, HTTP', r.status);
        return;
      }
      const j = await r.json();
      if(!j.ok || !j.pumps) {
        console.warn('[EC Calib] Invalid response from pump rates endpoint');
        return;
      }
      
      for(const p of j.pumps){
        const rateEl = el(`${p.key}PumpCurrentRate`);
        if(rateEl) {
          rateEl.textContent = `${p.ml_per_sec.toFixed(2)} ml/s`;
        }
      }
    }catch(e){
      console.warn('[EC Calib] Failed to load pump rates:', e);
      // Don't throw - this is not critical for init
    }
  }

  function showCalibMessage(msg, type='info'){
    const msgEl = el('ecPumpsCalibMsg');
    if(!msgEl) return;

    const styles = {
      error: { bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.3)' },
      success: { bg: 'rgba(34,197,94,0.1)', border: 'rgba(34,197,94,0.3)' },
      info: { bg: 'rgba(59,130,246,0.05)', border: 'rgba(59,130,246,0.15)' }
    };
    const style = styles[type] || styles.info;
    
    msgEl.textContent = msg;
    msgEl.style.display = 'block';
    msgEl.style.backgroundColor = style.bg;
    msgEl.style.borderColor = style.border;
    setTimeout(()=>{ if(msgEl) msgEl.style.display = 'none'; }, 5000);
  }

  async function calibPumpPrime(pump){
    // Prime: short pulse to prime the pump
    try{
      const r = await fetch(`/calib/dose/prime?pump=${encodeURIComponent(pump)}&seconds=${CALIB.PRIME_DURATION}`, {
        method: 'POST'
      });
      const j = await r.json();
      if(j.ok){
        showCalibMessage(`✓ ${pump} pump primed (${CALIB.PRIME_DURATION}s)`, 'success');
        updatePumpStatuses();
      } else {
        const msg = j.note || 'unknown';
        const hint = msg.includes('CALIB_ENABLE') ? ' (Set CALIB_ENABLE=1 in environment and restart)' : '';
        showCalibMessage(`✗ Prime failed: ${msg}${hint}`, 'error');
      }
    }catch(e){
      showCalibMessage(`✗ Prime error: ${e.message}`, 'error');
    }
  }

  async function calibPumpRun(pump){
    // Run: use the duration from the input field
    const durationEl = el(`${pump}PumpDuration`);
    if(!durationEl) return;
    const seconds = parseFloat(durationEl.value || CALIB.DEFAULT_RUN_DURATION);
    if(seconds < CALIB.MIN_RUN_DURATION || seconds > CALIB.MAX_RUN_DURATION){
      showCalibMessage(`✗ Duration must be ${CALIB.MIN_RUN_DURATION}-${CALIB.MAX_RUN_DURATION} seconds`, 'error');
      return;
    }
    
    try{
      showCalibMessage(`⏳ Running ${pump} pump for ${seconds}s...`, 'info');
      const r = await fetch(`/calib/dose/run?pump=${encodeURIComponent(pump)}&seconds=${seconds}`, {
        method: 'POST'
      });
      const j = await r.json();
      if(j.ok){
        showCalibMessage(`✓ ${pump} pump ran for ${seconds}s. Now measure and enter volume, then click Commit.`, 'success');
        updatePumpStatuses();
      } else {
        const msg = j.note || 'unknown';
        const hint = msg.includes('CALIB_ENABLE') ? ' (Set CALIB_ENABLE=1 in environment and restart)' : '';
        showCalibMessage(`✗ Run failed: ${msg}${hint}`, 'error');
      }
    }catch(e){
      showCalibMessage(`✗ Run error: ${e.message}`, 'error');
    }
  }

  async function calibPumpCommit(pump){
    // Commit: calculate and save the ml/s rate
    const durationEl = el(`${pump}PumpDuration`);
    const measuredEl = el(`${pump}PumpMeasured`);
    if(!durationEl || !measuredEl) return;
    
    const seconds = parseFloat(durationEl.value || 0);
    const measured_ml = parseFloat(measuredEl.value || 0);
    
    if(seconds < CALIB.MIN_MEASUREMENT || measured_ml < CALIB.MIN_MEASUREMENT){
      showCalibMessage(`✗ Enter valid duration and measured volume (min ${CALIB.MIN_MEASUREMENT})`, 'error');
      return;
    }
    
    try{
      const r = await fetch(`/calib/dose/commit?pump=${encodeURIComponent(pump)}&seconds=${seconds}&measured_ml=${measured_ml}`, {
        method: 'POST'
      });
      const j = await r.json();
      if(j.ok){
        const rate = j.rate_ml_per_sec || 0;
        showCalibMessage(`✓ ${pump} pump calibrated: ${rate.toFixed(2)} ml/s`, 'success');
        // Update the display
        await loadPumpRates();
        updatePumpStatuses();
        // Clear the measured input
        measuredEl.value = '';
      } else {
        const msg = j.note || 'unknown';
        const hint = msg.includes('CALIB_ENABLE') ? ' (Set CALIB_ENABLE=1 in environment and restart)' : '';
        showCalibMessage(`✗ Commit failed: ${msg}${hint}`, 'error');
      }
    }catch(e){
      showCalibMessage(`✗ Commit error: ${e.message}`, 'error');
    }
  }

  // Initialize
  async function init(){
    const s = await fetchStatus();
    if(s) renderStatus(s);
    await updatePumpStatuses();
    // Load and display recent dose log
    refreshDoseLog();
    // Keep dose log fresh while the page is open (30s interval, guard against double timers)
    if(!window.__ecDoseLogTimer){
      window.__ecDoseLogTimer = setInterval(()=>{ refreshDoseLog(); }, 30000);
    }
    // Register with centralized polling manager (main loop ~6s)
    if(window.pollingManager && !window.__ecPollingRegistered){
      window.__ecPollingRegistered = true;
      window.pollingManager.register('ec-status', async ()=>{
        const s = await fetchStatus(); if(s) renderStatus(s);
      }, 'main');
    }
    setupMixRatioToggle();



    // Helper to update interval display
    const updateIntervalDisplay = (val) => {
      const rapidToggle = document.getElementById('ecRapidTestToggle');
      if (rapidToggle) {
        rapidToggle.checked = (val === 10);
      }
    };

    // Rapid Test Mode toggle
    const rapidToggle = document.getElementById('ecRapidTestToggle');
    rapidToggle?.addEventListener('change', async ()=>{
      const val = rapidToggle.checked ? 10 : 300;
      try{
        const r = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({'ec.min_interval_sec': val})});
        if(!r.ok){ showToast('Failed to set interval', 'error'); rapidToggle.checked = !rapidToggle.checked; return; }
        showToast(`Interval set to ${val}s`, 'success');
        updateIntervalDisplay(val);
      }catch(e){ showToast('Interval error: '+e.message, 'error'); rapidToggle.checked = !rapidToggle.checked; }
    });
    const initialInt = parseInt(window.rdwcSettings?.get('ec.min_interval_sec')||'300');
    updateIntervalDisplay(initialInt);
    
    // Clear learner button
    el('btnClearEcLearned')?.addEventListener('click', async ()=>{
      if (!confirm('Clear learned EC value? This will reset the automation learning.')) return;
      const r = await fetch('/api/ec/auto/learn/reset', {method:'POST'});
      let j = null; try{ j = await r.json(); }catch(e){}
      if(window.showToast){ showToast(j?.ok ? 'EC learner reset' : 'Error resetting learner', j?.ok ? 'success':'error'); }
      const s2 = await fetchStatus();
      if(s2) renderStatus(s2);
    });
    // Export uses displayed window range
    el('btnEcExport')?.addEventListener('click', ()=>{
      if(window.ecChart && window.ecChart.exportCSV){ window.ecChart.exportCSV(); }
      else exportCSV24h(); // fallback
    });

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
        'targets.ec_tolerance': el('ecTolerance')?.value,
        'dosing.grow_ml_per_sec': el('ecGrowMlPerSec')?.value,
        'dosing.micro_ml_per_sec': el('ecMicroMlPerSec')?.value,
        'dosing.bloom_ml_per_sec': el('ecBloomMlPerSec')?.value,
        'dosing.ec_step_ml_min': el('ecStepMinMl')?.value,
        'dosing.ec_step_ml_max': el('ecStepMaxMl')?.value,
        'dosing.ec_safety_factor': el('ecSafetyFactor')?.value,
        'dosing.ec_min_interval_s': el('ecMinInterval')?.value,
        'dosing.ec_observe_s_after_dose': el('ecObserveAfterDose')?.value,
        'dosing.ec_high_limit_mscm': el('ecHighLimitMscm')?.value,
        'dosing.ec_max_ml_day': el('ecMaxMlDay')?.value
      };
      try{
        const r = await fetch('/api/settings', {
          method: 'PUT',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });
        if(!r.ok){
          const e = await r.json().catch(()=>({}));
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

    // === EC Pump Calibration Handlers ===
    // Load current rates
    await loadPumpRates();
    
    // Grow pump
    el('btnGrowPumpPrime')?.addEventListener('click', ()=> calibPumpPrime('grow'));
    el('btnGrowPumpRun')?.addEventListener('click', ()=> calibPumpRun('grow'));
    el('btnGrowPumpCommit')?.addEventListener('click', ()=> calibPumpCommit('grow'));
    
    // Micro pump
    el('btnMicroPumpPrime')?.addEventListener('click', ()=> calibPumpPrime('micro'));
    el('btnMicroPumpRun')?.addEventListener('click', ()=> calibPumpRun('micro'));
    el('btnMicroPumpCommit')?.addEventListener('click', ()=> calibPumpCommit('micro'));
    
    // Bloom pump
    el('btnBloomPumpPrime')?.addEventListener('click', ()=> calibPumpPrime('bloom'));
    el('btnBloomPumpRun')?.addEventListener('click', ()=> calibPumpRun('bloom'));
    el('btnBloomPumpCommit')?.addEventListener('click', ()=> calibPumpCommit('bloom'));
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
      const tEl = el('ec-total-today'); 
      if (tEl) {
        const valEl = tEl.querySelector('.kpi-value');
        if (valEl) valEl.textContent = todayMl>0 ? `${todayMl.toFixed(1)} ml` : '— ml';
        else tEl.textContent = todayMl>0 ? `Today: ${todayMl.toFixed(1)} ml` : 'Today: — ml';
      }
      const wEl = el('ec-total-week'); 
      if (wEl) {
        const valEl = wEl.querySelector('.kpi-value');
        if (valEl) valEl.textContent = weekMl>0 ? `${weekMl.toFixed(1)} ml` : '— ml';
        else wEl.textContent = weekMl>0 ? `Week: ${weekMl.toFixed(1)} ml` : 'Week: — ml';
      }
    }catch(e){ /* noop */ }
  }

  // Refresh EC dose log (recent events)
  async function refreshDoseLog(){
    try{
      const container = el('ec-recent');
      if(!container) return;
      const header = el('ec-recent-header');
      // Prefer chart window if available for consistent timeframe
      let url = '/api/ec/dose_log?grow=1&limit=500';
      try{
        const tw = window.ecChart?.timeWindow;
        if (tw && tw.start && tw.end) {
          const startISO = new Date(tw.start).toISOString();
          const endISO = new Date(tw.end).toISOString();
          url = `/api/ec/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`;
        }
      }catch(e){ /* fallback to grow preset */ }
      const res = await fetch(url, {cache:'no-store'});
      if(!res.ok) throw new Error('HTTP ' + res.status);
      const doses = await res.json();
      if(!doses || doses.length === 0){
        container.innerHTML = '<div style="opacity:0.5;font-size:var(--font-xs);">No doses recorded</div>';
        if(header) header.textContent = 'Dose Log (Empty)';
        return;
      }

      // Newest-first for readability (sort by ts desc)
      const ordered = [...doses].sort((a, b) => new Date(b.ts) - new Date(a.ts));
      const rows = ordered.map(d => {
        const ts = new Date(d.ts);
        const tsStr = `${ts.getFullYear()}-${String(ts.getMonth()+1).padStart(2,'0')}-${String(ts.getDate()).padStart(2,'0')} ${String(ts.getHours()).padStart(2,'0')}:${String(ts.getMinutes()).padStart(2,'0')}:${String(ts.getSeconds()).padStart(2,'0')}`;
        const total = (d.volume_ml != null) ? `${Number(d.volume_ml).toFixed(2)} ml` : '— ml';
        const g = (d.pumps && d.pumps.grow != null) ? `G:${Number(d.pumps.grow).toFixed(2)} ml` : null;
        const m = (d.pumps && d.pumps.micro != null) ? `M:${Number(d.pumps.micro).toFixed(2)} ml` : null;
        const b = (d.pumps && d.pumps.bloom != null) ? `B:${Number(d.pumps.bloom).toFixed(2)} ml` : null;
        const pumpParts = [g, m, b].filter(Boolean).join(' ');
        const ecBefore = (d.ec_before != null) ? Number(d.ec_before).toFixed(3) : '—';
        const ecAfter = (d.ec_after != null) ? Number(d.ec_after).toFixed(3) : '—';
        const delta = (d.ec_before != null && d.ec_after != null)
          ? (Number(d.ec_after) - Number(d.ec_before))
          : null;
        const deltaStr = (delta !== null) ? `${delta >= 0 ? '+' : ''}${Number(delta).toFixed(3)}` : '—';
        const detail = d.detail || 'dose';
        const reason = d.reason || detail;
        const duration = (d.seconds != null) ? `${Number(d.seconds).toFixed(1)}s` : null;

        // Single-row compact chip: time • EC • Δ • volume • duration • pumps • reason
        const dot = '<span style="color:#4b5563;">•</span>';
        const segments = [
          `<span style="font-weight:700;">${tsStr}</span>`,
          `<span style="color:#9ca3af;">EC ${ecBefore}→${ecAfter}</span>`,
          `<span style="color:#9ca3af;">Δ ${deltaStr}</span>`,
          `<span style="color:#9ca3af;">${total}</span>`
        ];
        if (duration) segments.push(`<span style="color:#9ca3af;">${duration}</span>`);
        if (pumpParts) segments.push(`<span style="color:#9ca3af;">${pumpParts}</span>`);
        segments.push(`<span style="color:#9ca3af;">${reason}</span>`);

        return `<div style="margin-bottom:4px;padding:4px 6px;border-radius:4px;background:rgba(59,130,246,0.06);border-left:2px solid rgba(59,130,246,0.25);display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:var(--font-xs);color:#cbd5e1;">${segments.join(dot)}</div>`;
      }).join('');

      container.innerHTML = rows;
      if(header) header.textContent = `Dose Log (${ordered.length}) ▾`;
    }catch(e){
      const container = el('ec-recent');
      if(container) container.innerHTML = `<div style="color:#ef4444;font-size:var(--font-xs);">Error: ${e.message}</div>`;
    }
  }

  // Refresh last three pump status (unused placeholder)
  function refreshLastThree(){
    // Placeholder for potential future per-pump status display
  }

  // Load settings into UI (fetch directly if rdwcSettings not yet hydrated)
  async function loadECSettings(){
    // Helper resolves a dotted key from either rdwcSettings or freshly fetched JSON
    const hydrateFromApi = async () => {
      const resp = await fetch('/api/settings', {cache:'no-store'});
      if(!resp.ok) throw new Error('Settings fetch failed');
      const data = await resp.json();
      const getNested = (path, fallback) => {
        const parts = path.split('.');
        let cur = data;
        for(const p of parts){ cur = cur?.[p]; }
        return (cur === undefined || cur === null || cur === '') ? fallback : cur;
      };
      return getNested;
    };

    let getter;
    if(window.rdwcSettings?.get){
      getter = (key, fallback) => {
        const val = window.rdwcSettings.get(key);
        return (val === undefined || val === null || val === '') ? fallback : val;
      };
    } else {
      try{
        getter = await hydrateFromApi();
      }catch(err){
        console.warn('[EC] Failed to load settings', err);
        return;
      }
    }

    const setVal = (id, key, fallback) => {
      const elRef = el(id);
      if(!elRef) return;
      elRef.value = getter(key, fallback);
    };

    setVal('ecSetpoint', 'ec.setpoint_mscm', '');
    setVal('ecGrowMlPerSec', 'dosing.grow_ml_per_sec', '20');
    setVal('ecMicroMlPerSec', 'dosing.micro_ml_per_sec', '20');
    setVal('ecBloomMlPerSec', 'dosing.bloom_ml_per_sec', '20');
    setVal('ecTolerance', 'targets.ec_tolerance', '0.2');
    setVal('ecStepMinMl', 'dosing.ec_step_ml_min', '3');
    setVal('ecStepMaxMl', 'dosing.ec_step_ml_max', '10');
    setVal('ecSafetyFactor', 'dosing.ec_safety_factor', '0.7');
    setVal('ecMinInterval', 'dosing.ec_min_interval_s', '600');
    setVal('ecHighLimitMscm', 'dosing.ec_high_limit_mscm', '3.0');
    setVal('ecMaxMlDay', 'dosing.ec_max_ml_day', '0');
    const obs = getter('dosing.ec_observe_s_after_dose', getter('dosing.observe_s_after_dose', '300'));
    const obsEl = el('ecObserveAfterDose');
    if(obsEl) obsEl.value = obs;
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

  // Re-hydrate UI once settings.js finishes booting and dispatches UI event
  window.addEventListener('settings:ui', loadECSettings);

  // Save EC Parameters (batch save: step, safety, interval, observe, tolerance)
  document.addEventListener('click', async (e)=>{
    if(e.target && e.target.id === 'btnSaveEcSettings'){
      const payload = {};
      const fields = [
        ['ecStepMinMl', 'dosing.ec_step_ml_min'],
        ['ecStepMaxMl', 'dosing.ec_step_ml_max'],
        ['ecSafetyFactor', 'dosing.ec_safety_factor'],
        ['ecMinInterval', 'dosing.ec_min_interval_s'],
        ['ecObserveAfterDose', 'dosing.ec_observe_s_after_dose'],
        ['ecTolerance', 'targets.ec_tolerance'],
        ['ecHighLimitMscm', 'dosing.ec_high_limit_mscm'],
        ['ecMaxMlDay', 'dosing.ec_max_ml_day']
      ];
      for(const [elemId, settingKey] of fields){
        const v = parseFloat(el(elemId)?.value||'');
        if(!isNaN(v)) payload[settingKey] = v;
      }
      try{
        const r = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
        if(!r.ok){
          const err = await r.json();
          throw new Error(err.message || 'HTTP '+r.status);
        }
        showToast('EC settings saved','success');
        await loadECSettings(); // Reload to confirm
      }catch(err){ showToast('Save failed: '+err.message,'error'); console.error('[EC] Save error:', err); }
    }
  });

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
      // Age seconds display
      // Age chip removed
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
    showCalMessage('⏳ Refreshing calibration status...', 'info');
    try{
      const [statusRes, sensorRes] = await Promise.all([
        fetch('/api/ec/cal/status', {cache:'no-store'}),
        fetchStatus()
      ]);
      if(statusRes.ok){
        const status = await statusRes.json();
        el('ecCalStatusValue').textContent = status.cal || 'unknown';
        el('ecKValue').textContent = status.k != null ? status.k.toFixed(1) : '—';
        
        // Update calibration step indicators
        const dryIndicator = el('ecCalDryIndicator');
        const lowIndicator = el('ecCalLowIndicator');
        const highIndicator = el('ecCalHighIndicator');
        
        if(dryIndicator) dryIndicator.textContent = status.dry ? '✓' : '—';
        if(lowIndicator) lowIndicator.textContent = status.low ? '✓' : '—';
        if(highIndicator) highIndicator.textContent = status.high ? '✓' : '—';
      }
      if(sensorRes && sensorRes.ec_ms_cm != null){
        el('ecCalCurrentReading').textContent = sensorRes.ec_ms_cm.toFixed(2);
      }
      showCalMessage('✓ Status refreshed', 'success');
    }catch(err){
      showCalMessage('✗ Error: '+err.message, 'error');
    }
  }
  async function ecCalClear(){
    if(!confirm('Clear EC calibration? You will need to recalibrate.')) return;
    showCalMessage('⏳ Clearing EC calibration...', 'info');
    try{
      const r = await fetch('/api/ec/cal/clear', {method:'POST'});
      const j = await r.json();
      showCalMessage(j.ok ? ('✓ '+j.response) : ('✗ '+j.error), j.ok?'success':'error');
      if(j.ok) setTimeout(refreshCalStatus, 1000);
    }catch(err){ showCalMessage('✗ '+err.message, 'error'); }
  }
  async function ecCalDry(){
    if(!confirm('Apply dry calibration? Remove probe from all solutions and let it air dry (30s).')) return;
    showCalMessage('⏳ Applying dry calibration (takes ~2s)...', 'info');
    try{
      const r = await fetch('/api/ec/cal/dry', {method:'POST'});
      const j = await r.json();
      showCalMessage(j.ok ? ('✓ '+j.response) : ('✗ '+j.error), j.ok?'success':'error');
      if(j.ok) setTimeout(refreshCalStatus, 1000);
    }catch(err){ showCalMessage('✗ '+err.message, 'error'); }
  }
  async function ecCalLow(){
    if(!confirm('Apply low-point calibration? Value auto-selected based on K factor. Probe must be in calibration solution and stable (30s).')) return;
    showCalMessage('⏳ Applying low-point calibration (takes ~2s)...', 'info');
    try{
      // Don't pass us_cm to use K-based auto-selection
      const r = await fetch('/api/ec/cal/low', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})});
      const j = await r.json();
      showCalMessage(j.ok ? ('✓ '+j.response) : ('✗ '+j.error), j.ok?'success':'error');
      if(j.ok) setTimeout(refreshCalStatus, 1000);
    }catch(err){ showCalMessage('✗ '+err.message, 'error'); }
  }
  async function ecCalHigh(){
    if(!confirm('Apply high-point calibration? Value auto-selected based on K factor. Requires dry and low-point first. Probe must be in calibration solution and stable (30s).')) return;
    showCalMessage('⏳ Applying high-point calibration (takes ~2s)...', 'info');
    try{
      // Don't pass us_cm to use K-based auto-selection
      const r = await fetch('/api/ec/cal/high', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})});
      const j = await r.json();
      showCalMessage(j.ok ? ('✓ '+j.response) : ('✗ '+j.error), j.ok?'success':'error');
      if(j.ok) setTimeout(refreshCalStatus, 1000);
    }catch(err){ showCalMessage('✗ '+err.message, 'error'); }
  }
  async function ecSetK(){
    const k = prompt('Enter K factor (0.1, 1.0, or 10.0):', '0.1');
    if(!k) return;
    const kVal = parseFloat(k);
    if(isNaN(kVal) || kVal <= 0){ alert('Invalid K value'); return; }
    showCalMessage('⏳ Setting K factor...', 'info');
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
    // Make message visible when set
    msgEl.style.display = 'block';
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
  el('btnEcCalDry')?.addEventListener('click', ecCalDry);
  el('btnEcCalLow')?.addEventListener('click', ecCalLow);
  el('btnEcCalHigh')?.addEventListener('click', ecCalHigh);
  el('btnEcCalSetK')?.addEventListener('click', ecSetK);
  
  // Auto-refresh calibration status on load
  setTimeout(refreshCalStatus, 500);

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

  // Back-compat export: map legacy doseEC to unified dosing
  window.ecController = { init, fetchStatus, renderStatus, doseEC: doseUnified, toggleAuto };
  
  // --- 3-mode header logic ---
  function updateHealthIndicator(){
    const chip = el('ec-health-indicator');
    if(!chip){ return; }
    if(!lastStatus){
      chip.textContent = '—';
      chip.className = 'ui-status-chip neutral';
      chip.title = 'Loading...';
      return;
    }
    const g = lastStatus.guards || {};
    const hasHard = !!(g.estop || g.sensor_stale || g.reservoir || g.mix_lock);
    const hasSoft = !!(g.interval || g.daily_cap);
    if(hasHard){
      chip.textContent = 'BLOCKED';
      chip.className = 'ui-status-chip error';
      chip.title = 'Hard safety blocks: ' + guardList(g).join(', ');
    } else if (hasSoft){
      chip.textContent = 'WAITING';
      chip.className = 'ui-status-chip warning';
      chip.title = 'Automation waiting: ' + guardList(g).join(', ');
    } else {
      chip.textContent = 'AUTO';
      chip.className = 'ui-status-chip success';
      chip.title = 'Automation running';
    }
  }
})();