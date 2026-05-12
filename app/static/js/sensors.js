/* Sensors real-time display with color thresholds and calibration status */
 (function(){
  // Execution sentinel to confirm script body runs
  window.__SENSORS_SCRIPT_VERSION = '831ab9e';
  console.log('[Sensors] Script executing; version', window.__SENSORS_SCRIPT_VERSION, 'readyState=', document.readyState);
  // Removed single-load guard to ensure latest script logic always applies even if included twice.
  // Any previous timers will be stopped by ensurePolling(); we now allow redefinition safely.
  if (window.__RDWC_SENSORS_POLL_RUNNING__) {
    console.log("[Sensors.js] Reload detected; reinitializing sensors module.");
  }
  window.__RDWC_SENSORS_POLL_RUNNING__ = true;
  const $ = (id)=>document.getElementById(id);
  let __lastSensorsOnline = null;
  let __lastSensorsHealth = null;
  
  // Mode management for Sensors Controller
  let sensorsMode = localStorage.getItem('sensors_mode') || 'auto';
  const setActive = (btn, on)=>{ if(!btn) return; if(on) btn.classList.add('active'); else btn.classList.remove('active'); };
  
  async function refreshServerMode(){
    try{
      const r = await fetch('/api/sensors/mode', {cache:'no-store'});
      if(r.ok){ 
        const j = await r.json(); 
        sensorsMode = j.mode || sensorsMode; 
        localStorage.setItem('sensors_mode', sensorsMode);
        console.log('[Sensors] Synced mode from backend:', sensorsMode);
      }
    }catch(e){ console.error('[Sensors] Failed to sync mode from backend:', e); }
    setActive($('sensors-mode-auto'), sensorsMode==='auto');
    setActive($('sensors-mode-manual'), sensorsMode==='manual');
    setActive($('sensors-mode-maint'), sensorsMode==='maintenance');
    updateSensorsHealth();
    toggleOverridesVisibility();
  }
  window.refreshServerMode = refreshServerMode;

  async function sensorsSetMode(next){
    console.log('[Sensors] setMode called:', next);
    try{
      console.log('[Sensors] Fetching /api/sensors/mode with mode:', next);
      const r = await fetch('/api/sensors/mode', {
        method:'POST', 
        headers:{'Content-Type':'application/json'}, 
        body: JSON.stringify({mode: next}),
        cache: 'no-store'
      });
      console.log('[Sensors] Fetch completed, status:', r.status, 'ok:', r.ok);
      const respData = await r.json();
      console.log('[Sensors] POST response:', respData);
      if (!r.ok) {
        console.error('[Sensors] set mode failed:', r.status, respData);
        alert(`Failed to set mode: HTTP ${r.status}`);
        return;
      }
      if (!respData.ok) {
        console.error('[Sensors] server rejected mode:', respData);
        alert(`Server rejected mode change`);
        return;
      }
      // Trust the server response, not the requested mode
      sensorsMode = respData.mode;
      localStorage.setItem('sensors_mode', sensorsMode);
      console.log('[Sensors] UI updating to mode:', sensorsMode);
      
      // Force a small delay to ensure DOM is ready
      await new Promise(resolve => setTimeout(resolve, 50));
      
      const autoBtn = $('sensors-mode-auto');
      const manualBtn = $('sensors-mode-manual');
      const maintBtn = $('sensors-mode-maint');
      console.log('[Sensors] Buttons found:', {auto: !!autoBtn, manual: !!manualBtn, maint: !!maintBtn});
      console.log('[Sensors] Setting active states:', {auto: sensorsMode==='auto', manual: sensorsMode==='manual', maint: sensorsMode==='maintenance'});
      
      // Remove active class from all buttons first
      if(autoBtn) autoBtn.classList.remove('active');
      if(manualBtn) manualBtn.classList.remove('active');
      if(maintBtn) maintBtn.classList.remove('active');
      
      // Then add active class to the correct button
      if(sensorsMode==='auto' && autoBtn) autoBtn.classList.add('active');
      if(sensorsMode==='manual' && manualBtn) manualBtn.classList.add('active');
      if(sensorsMode==='maintenance' && maintBtn) maintBtn.classList.add('active');
      
      console.log('[Sensors] Active classes after:', {
        auto: autoBtn?.className,
        manual: manualBtn?.className,
        maint: maintBtn?.className
      });
      updateSensorsHealth();
      toggleOverridesVisibility();
      // Check if all controllers now match and sync system mode if so
      if (window.syncSystemModeFromControllers) window.syncSystemModeFromControllers();
    }catch(e){ 
      console.error('[Sensors] set mode exception:', e);
      alert(`Error setting mode: ${e.message}`);
    }
  }
  
  function updateSensorsHealth(){
    const ind = $('sensors-health-indicator');
    if (!ind) return;
    if (sensorsMode==='maintenance'){ ind.textContent='MAINT'; ind.className='ui-status-chip warning'; ind.title='Maintenance mode: simulated data'; return; }
    // derive from latest health/online flags
    const h = __lastSensorsHealth;
    const online = __lastSensorsOnline;
    if (online === false){ ind.textContent='OFFLINE'; ind.className='ui-status-chip error'; ind.title='Poller offline'; return; }
    if (h && h.cache_has_data === false){ ind.textContent='OFFLINE'; ind.className='ui-status-chip error'; ind.title='No cache data'; return; }
    if (h && h.cache_fresh === false){ ind.textContent='STALE'; ind.className='ui-status-chip warning'; ind.title=`Cache age ${Math.round(h.cache_age_s||0)}s`; return; }
    ind.textContent='OK'; ind.className='ui-status-chip success'; ind.title='Live poller feed';
  }
  
  window.sensorsSetMode = sensorsSetMode;
  
  // Initialize mode buttons on load
  refreshServerMode();

  // Demo mode shortcut: populate synthetic readings & skip network traffic
  if (window.UI_DEMO){
    console.warn('[Sensors] UI_DEMO active: using simulated data');
    let t=22.4, e=1.40, p=5.90; // base values
    const drift=()=> (Math.random()*0.06-0.03);
    setInterval(()=>{
      t = t + drift(); e = e + drift()*0.2; p = p + drift()*0.1;
      setMetric($("kpiTemp"), t, classify("temp", t));
      setMetric($("kpiEc"),   e, classify("ec", e));
      setMetric($("kpiPh"),   p, classify("ph", p));
      setOnline(true);
    }, 3000);
    return; // Abort real wiring
  }
  
  // Runtime state (SSE vs fallback polling)
  let sse = null;
  let fallbackTimer = null; // slow polling fallback if SSE unavailable
  let ready = false;
  let firstUpdateReceived = false;

  const setMetric = (el, val, classes) => {
    if (!el) return;
    el.textContent = (val===null || Number.isNaN(val)) ? "--" : String(val.toFixed ? val.toFixed(2) : val);
    el.classList.remove("good","warn","bad");
    el.classList.add(classes);
  };
  
  const classify = (name, v) => {
    if (v===null || Number.isNaN(v)) return "bad";
    if (name==="temp") {
      if (v>=18 && v<=24) return "good";
      if ((v>24 && v<=28) || (v>=16 && v<18)) return "warn";
      return "bad";
    }
    if (name==="ec") {
      if (v>=1.2 && v<=2.0) return "good";
      if ((v>=0.8 && v<1.2) || (v>2.0 && v<=2.4)) return "warn";
      return "bad";
    }
    if (name==="ph") {
      if (v>=5.5 && v<=6.2) return "good";
      if ((v>=5.2 && v<5.5) || (v>6.2 && v<=6.5)) return "warn";
      return "bad";
    }
    return "bad";
  };
  
  const setBadge = (el, ok, detail) => {
    if (!el) return;
    el.textContent = ok ? "OK" : "Check";
    el.classList.remove("ok","check");
    el.classList.add(ok ? "ok" : "check");
    if (detail) el.title = detail;
  };
  
  const setOnline = (ok) => {
    const el = $("sensors-online");
    if (!el) return;
    el.textContent = ok ? "online" : "offline";
    el.classList.remove("online","offline");
    el.classList.add(ok ? "online" : "offline");
  };

  // --- Simulation support (Maintenance mode) ---
  let sim = { t: 22.4, e: 1.40, p: 5.90 };
  const simDrift = () => (Math.random()*0.06 - 0.03);
  function simulateStep(label){
    sim.t = sim.t + simDrift();
    sim.e = sim.e + simDrift()*0.2;
    sim.p = sim.p + simDrift()*0.1;
    setMetric($("kpiTemp"), sim.t, classify("temp", sim.t));
    setMetric($("kpiEc"),   sim.e, classify("ec", sim.e));
    setMetric($("kpiPh"),   sim.p, classify("ph", sim.p));
    setOnline(true);
  }

  // Old SSE/fallback polling removed - now using simplified polling in boot function
  function toggleOverridesVisibility(){
    const wrap = $('sensor-overrides-wrapper');
    if(!wrap) return;
    wrap.style.display = (sensorsMode==='maintenance') ? 'block' : 'none';
  }
  function updateOverridesPanel(data){
    const origPh = $('originalPh'); const effPh = $('effectivePh');
    const origEc = $('originalEc'); const effEc = $('effectiveEc');
    const origT  = $('originalTemp'); const effT  = $('effectiveTemp');
    if (origPh) origPh.textContent = fmtVal(data.original_ph);
    if (effPh)  effPh.textContent  = fmtVal(data.ph);
    if (origEc) origEc.textContent = fmtVal(data.original_ec_mscm);
    if (effEc)  effEc.textContent  = fmtVal(data.ec_mscm);
    if (origT)  origT.textContent  = fmtVal(data.original_temperature_c);
    if (effT)   effT.textContent   = fmtVal(data.temperature_c);
  }
  function fmtVal(v){ return (v==null || Number.isNaN(v))? '—' : (typeof v==='number'? v.toFixed(2): String(v)); }

  async function loadSensorOverrides(){
    try{
      const r = await fetch('/api/sensors/override', {cache:'no-store'});
      if(!r.ok) return;
      const j = await r.json();
      const o = j.overrides || {};
      const ageSpan = $('sensorOverrideAge');
      if (ageSpan){
        const age = (j.age_seconds!=null)? j.age_seconds : null;
        ageSpan.textContent = age!=null? `Overrides age: ${age}s` : 'Overrides inactive';
      }
      // Populate inputs only if maintenance mode (avoid confusion)
      if (sensorsMode==='maintenance'){
        const phIn = $('inpOverridePh'); const ecIn = $('inpOverrideEc'); const tIn = $('inpOverrideTemp');
        if(phIn) phIn.value = o.ph!=null? o.ph : '';
        if(ecIn) ecIn.value = o.ec_mscm!=null? o.ec_mscm : '';
        if(tIn)  tIn.value = o.temperature_c!=null? o.temperature_c : '';
      }
    }catch(e){ /* ignore */ }
  }
  async function applySensorOverrides(){
    const phIn = $('inpOverridePh'); const ecIn = $('inpOverrideEc'); const tIn = $('inpOverrideTemp');
    const payload = {};
    if(phIn && phIn.value.trim()!== '') payload.ph = parseFloat(phIn.value);
    if(ecIn && ecIn.value.trim()!== '') payload.ec_mscm = parseFloat(ecIn.value);
    if(tIn && tIn.value.trim()!== '') payload.temperature_c = parseFloat(tIn.value);
    try{
      await fetch('/api/sensors/override', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
      await tick();
      await loadSensorOverrides();
    }catch(e){ console.warn('[Sensors] override apply failed', e); }
  }
  async function clearSensorOverride(field){
    try{
      await fetch(`/api/sensors/override/${encodeURIComponent(field)}`, {method:'DELETE'});
      await tick();
      await loadSensorOverrides();
      const map = {ph:'inpOverridePh', ec_mscm:'inpOverrideEc', temperature_c:'inpOverrideTemp'};
      const id = map[field]; if(id){ const el=$(id); if(el) el.value=''; }
    }catch(e){ console.warn('[Sensors] clear override failed', e); }
  }
  
  // --- Bootstrap logic: ensure we initialize even if DOMContentLoaded already fired ---
  function __rdwcSensorsBoot(){
    console.log('[Sensors] Initializing real-time updates (boot)');
    ready = true;
    
    // Cache last displayed values to prevent flicker when rounding produces same string
    let lastTemp = null, lastEc = null, lastPh = null;
    // Track raw values to avoid dispatching events when data hasn't changed
    let lastRawTemp = null, lastRawEc = null, lastRawPh = null, lastTs = null;
    
    // SIMPLIFIED: Just poll every 5 seconds and update the DOM directly
    async function simplePoll() {
      try {
        // Use PollingManager cache instead of direct fetch
        const data = await window.PollingManager.getSensors();
        console.log('[Sensors] Fetched data:', data);

        // Guard against unexpected empty/undefined payloads to avoid TypeError loops
        if (!data || typeof data !== 'object') {
          console.warn('[Sensors] Missing/invalid sensors payload, skipping update');
          return;
        }
        
        // Direct DOM updates - only if value changed after formatting
        const tempEl = document.getElementById('kpiTemp');
        const ecEl = document.getElementById('kpiEc');
        const phEl = document.getElementById('kpiPh');
        
        if (tempEl && data.temperature_c != null) {
          const newVal = data.temperature_c.toFixed(2);
          if (newVal !== lastTemp) {
            tempEl.textContent = newVal;
            lastTemp = newVal;
            console.log('[Sensors] Set temp to:', newVal);
          }
        }
        if (ecEl && data.ec_mscm != null) {
          const newVal = data.ec_mscm.toFixed(2);
          if (newVal !== lastEc) {
            ecEl.textContent = newVal;
            lastEc = newVal;
            console.log('[Sensors] Set EC to:', newVal);
          }
        }
        if (phEl && data.ph != null) {
          const newVal = data.ph.toFixed(2);
          if (newVal !== lastPh) {
            phEl.textContent = newVal;
            lastPh = newVal;
            console.log('[Sensors] Set pH to:', newVal);
          }
        }
        
        // Dispatch event for other modules (ec_chart, trends, etc.) only if data changed
        const dataChanged = (
          data.temperature_c !== lastRawTemp ||
          data.ec_mscm !== lastRawEc ||
          data.ph !== lastRawPh ||
          data.ts !== lastTs
        );
        
        if (dataChanged && (data.temperature_c != null || data.ec_mscm != null || data.ph != null)) {
          lastRawTemp = data.temperature_c;
          lastRawEc = data.ec_mscm;
          lastRawPh = data.ph;
          lastTs = data.ts;
          
          window.dispatchEvent(new CustomEvent('sensors:update', { 
            detail: { 
              temp: data.temperature_c, 
              ec: data.ec_mscm, 
              ph: data.ph, 
              ts: data.ts 
            }
          }));
        }
      } catch (e) {
        console.error('[Sensors] Poll failed:', e);
      }
    }
    
    // Poll immediately and every 2 seconds so the UI reacts close to sensor sample arrival.
    simplePoll();
    setInterval(simplePoll, 2000);
    window.forceSensorsTick = simplePoll;
    // Bind mode buttons via listeners (replace inline onclick for reliability)
    const autoBtn = $("sensors-mode-auto");
    const manualBtn = $("sensors-mode-manual");
    const maintBtn = $("sensors-mode-maint");
    const bindMode = (btn, mode)=>{ if(!btn) return; if(btn.__boundMode) return; btn.addEventListener('click', (e)=>{ e.preventDefault(); sensorsSetMode(mode); }); btn.__boundMode=true; };
    bindMode(autoBtn, 'auto');
    bindMode(manualBtn, 'manual');
    bindMode(maintBtn, 'maintenance');
    // Sync mode from backend and poll every 5s
    refreshServerMode();
    // Mode refresh slower (SSE covers sensors values only)
    setInterval(refreshServerMode, 15000);
    // Sensors health popover interactions
    const badge = $("sensors-health-badge");
    const pop = $("sensors-health-popover");
    if (badge && pop) {
      const fmtAgo = (ts)=>{
        if (!ts) return "n/a";
        const now = Date.now()/1000;
        const age = Math.max(0, Math.round(now - ts));
        if (age < 60) return `${age}s ago`;
        const m = Math.floor(age/60);
        if (m < 60) return `${m}m ago`;
        const h = Math.floor(m/60);
        return `${h}h ${m%60}m ago`;
      };
      const buildHtml = (h)=>{
        const d = h?.diag || {};
        const cacheAge = (h?.cache_age_s!=null)? `${Math.round(h.cache_age_s)}s` : 'n/a';
        const dbAge = (h?.db_age_s!=null)? `${Math.round(h.db_age_s)}s` : 'n/a';
        const dbTsAgo = (h?.db_ts!=null)? fmtAgo(h.db_ts) : 'n/a';
        const lwAgo = d?.last_watchdog_ts ? fmtAgo(d.last_watchdog_ts) : 'never';
        const leAgo = d?.last_error_ts ? fmtAgo(d.last_error_ts) : 'n/a';
        const lastErr = (d?.last_error || '').toString().slice(0,160);
        const fresh = h?.cache_fresh ? 'yes' : 'no';
        return `
          <div style="font-weight:600;margin-bottom:6px;">Sensors Health</div>
          <div style="display:grid;grid-template-columns: 140px 1fr;gap:6px 10px;align-items:center;">
            <div class="muted">Cache Fresh</div><div>${fresh}</div>
            <div class="muted">Cache Age</div><div>${cacheAge}</div>
            <div class="muted">DB Age</div><div>${dbAge}</div>
            <div class="muted">DB Last</div><div>${dbTsAgo}</div>
            <div class="muted">Watchdog Restarts</div><div>${d?.restarts ?? 0}</div>
            <div class="muted">Last Watchdog</div><div>${lwAgo}</div>
            <div class="muted">Last Error</div><div style="max-width:260px;white-space:pre-wrap;word-break:break-word;">${lastErr || '—'}</div>
            <div class="muted">Last Error Time</div><div>${leAgo}</div>
          </div>
        `;
      };
      const place = (anchor)=>{
        const r = anchor.getBoundingClientRect();
        const top = window.scrollY + r.bottom + 8;
        const left = window.scrollX + Math.min(r.left, window.innerWidth - 320);
        pop.style.top = `${top}px`;
        pop.style.left = `${left}px`;
      };
      const hide = ()=>{ pop.style.display = 'none'; };
      const show = ()=>{ pop.style.display = 'block'; };
      let open = false;
      badge.addEventListener('click', async (ev)=>{
        ev.stopPropagation();
        try{
          const r = await fetch('/api/sensors/health', {cache:'no-store'});
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          const h = await r.json();
          pop.innerHTML = buildHtml(h);
          place(badge);
          show();
          open = true;
        }catch(e){
          console.warn('[Sensors] popover fetch failed', e);
        }
      });
      document.addEventListener('click', (ev)=>{
        if (!open) return;
        if (ev.target === badge || pop.contains(ev.target)) return;
        hide();
        open = false;
      });
      document.addEventListener('keydown', (ev)=>{
        if (!open) return;
        if (ev.key === 'Escape') { hide(); open = false; }
      });
      window.addEventListener('resize', ()=>{ if (open) place(badge); });
      window.addEventListener('scroll', ()=>{ if (open) place(badge); }, {passive:true});
    }
    // Bind overrides controls
    const applyBtn = $('btnApplySensorOverrides');
    if(applyBtn && !applyBtn.__bound){ applyBtn.addEventListener('click', ()=>applySensorOverrides()); applyBtn.__bound=true; }
    const clrPh = $('btnClearOverridePh'); if(clrPh && !clrPh.__bound){ clrPh.addEventListener('click', ()=>clearSensorOverride('ph')); clrPh.__bound=true; }
    const clrEc = $('btnClearOverrideEc'); if(clrEc && !clrEc.__bound){ clrEc.addEventListener('click', ()=>clearSensorOverride('ec_mscm')); clrEc.__bound=true; }
    const clrT  = $('btnClearOverrideTemp'); if(clrT && !clrT.__bound){ clrT.addEventListener('click', ()=>clearSensorOverride('temperature_c')); clrT.__bound=true; }
    loadSensorOverrides();
    setInterval(loadSensorOverrides, 30000);
    toggleOverridesVisibility();

    // Debug assist: force direct fetch & KPI assignment if still blank after 3s
    setTimeout(()=>{
      try {
        const phEl = $("kpiPh"), ecEl = $("kpiEc"), tEl = $("kpiTemp");
        const blanks = [phEl, ecEl, tEl].filter(e => e && (e.textContent === '—' || e.textContent === '--'));
        if (blanks.length > 0) {
          console.warn('[Sensors] KPIs still blank after 3s; performing direct fetch');
          fetch('/api/sensors',{cache:'no-store'}).then(r=>r.json()).then(d=>{
            if (phEl && (phEl.textContent === '—' || phEl.textContent === '--') && d.ph!=null) phEl.textContent = d.ph.toFixed(2);
            if (ecEl && (ecEl.textContent === '—' || ecEl.textContent === '--') && d.ec_mscm!=null) ecEl.textContent = d.ec_mscm.toFixed(2);
            if (tEl && (tEl.textContent === '—' || tEl.textContent === '--') && d.temperature_c!=null) tEl.textContent = d.temperature_c.toFixed(2);
            console.warn('[Sensors] Direct fetch applied for blank KPIs');
          }).catch(e=>console.warn('[Sensors] Direct fetch failed', e));
        }
      } catch(e){ console.warn('[Sensors] KPI debug assist error', e); }
    }, 3000);
  }
  // === EC Calibration Handlers (Sensors Tab) ===
  async function ecSetKFromDropdown(){
    const selectEl = $('ec-k-select');
    const msgEl = $('ec-calib-msg');
    if(!selectEl) { console.error('[Sensors] ec-k-select not found'); return; }
    
    const kVal = parseFloat(selectEl.value);
    if(isNaN(kVal) || kVal <= 0){ 
      if(msgEl){ 
        msgEl.textContent = '✗ Invalid K value';
        msgEl.style.display = 'block';
        msgEl.style.background = 'rgba(239,68,68,0.08)';
        msgEl.style.borderColor = 'rgba(239,68,68,0.3)';
        msgEl.style.color = '#fecaca';
      }
      return; 
    }
    
    try{
      const r = await fetch('/api/ec/k', {
        method:'POST', 
        headers:{'Content-Type':'application/json'}, 
        body:JSON.stringify({k:kVal})
      });
      const j = await r.json();
      
      if(msgEl){
        msgEl.textContent = j.ok ? ('✓ K=' + kVal + ' ' + (j.response||'set successfully')) : ('✗ ' + (j.error||'Failed'));
        msgEl.style.display = 'block';
        msgEl.style.background = j.ok ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)';
        msgEl.style.borderColor = j.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)';
        msgEl.style.color = j.ok ? '#a7f3d0' : '#fecaca';
      }
      
      if(j.ok) setTimeout(loadEcCalibrationStatus, 1000);
    }catch(err){ 
      if(msgEl){
        msgEl.textContent = '✗ ' + err.message;
        msgEl.style.display = 'block';
        msgEl.style.background = 'rgba(239,68,68,0.08)';
        msgEl.style.borderColor = 'rgba(239,68,68,0.3)';
        msgEl.style.color = '#fecaca';
      }
      console.error('[Sensors] EC K set error:', err);
    }
  }
  
  async function loadEcCalibrationStatus(){
    try{
      const r = await fetch('/api/ec/cal/status', {cache:'no-store'});
      if(!r.ok) return;
      const j = await r.json();
      
      // Update K dropdown to match probe's actual K value
      const selectEl = $('ec-k-select');
      if(selectEl && j.k != null){
        selectEl.value = j.k.toString();
        console.log('[Sensors] EC K loaded from probe:', j.k);
      }
      
      // Update current EC display
      const ecCurrentEl = $('ec-current-calib');
      if(ecCurrentEl){
        try{
          const sensorsData = await fetch('/api/sensors', {cache:'no-store'}).then(r=>r.json());
          if(sensorsData.ec_mscm != null){
            ecCurrentEl.textContent = sensorsData.ec_mscm.toFixed(2) + ' mS/cm';
          }
        }catch(e){ console.warn('[Sensors] Failed to load current EC:', e); }
      }
      
    }catch(err){
      console.error('[Sensors] Failed to load EC calibration status:', err);
    }
  }
  
  async function ecCalClear(){
    const msgEl = $('ec-calib-msg');
    if(!confirm('Clear EC calibration? This will reset all calibration points.')) return;
    
    try{
      const r = await fetch('/api/ec/cal/clear', {method:'POST'});
      const j = await r.json();
      
      if(msgEl){
        msgEl.textContent = j.ok ? '✓ Calibration cleared' : ('✗ ' + (j.error||'Failed'));
        msgEl.style.display = 'block';
        msgEl.style.background = j.ok ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)';
        msgEl.style.borderColor = j.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)';
        msgEl.style.color = j.ok ? '#a7f3d0' : '#fecaca';
      }
      
      if(j.ok) setTimeout(loadEcCalibrationStatus, 1000);
    }catch(err){
      if(msgEl){
        msgEl.textContent = '✗ ' + err.message;
        msgEl.style.display = 'block';
      }
      console.error('[Sensors] EC cal clear error:', err);
    }
  }
  
  async function ecCalLow(){
    const msgEl = $('ec-calib-msg');
    if(!confirm('Calibrate EC low point (1413 µS/cm)? Ensure probe is in calibration solution.')) return;
    
    try{
      const r = await fetch('/api/ec/cal/low', {method:'POST'});
      const j = await r.json();
      
      if(msgEl){
        msgEl.textContent = j.ok ? '✓ Low point calibrated' : ('✗ ' + (j.error||'Failed'));
        msgEl.style.display = 'block';
        msgEl.style.background = j.ok ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)';
        msgEl.style.borderColor = j.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)';
        msgEl.style.color = j.ok ? '#a7f3d0' : '#fecaca';
      }
      
      if(j.ok) setTimeout(loadEcCalibrationStatus, 1000);
    }catch(err){
      if(msgEl){
        msgEl.textContent = '✗ ' + err.message;
        msgEl.style.display = 'block';
      }
      console.error('[Sensors] EC cal low error:', err);
    }
  }
  
  async function ecCalHigh(){
    const msgEl = $('ec-calib-msg');
    if(!confirm('Calibrate EC high point (12,880 µS/cm)? Ensure probe is in calibration solution.')) return;
    
    try{
      const r = await fetch('/api/ec/cal/high', {method:'POST'});
      const j = await r.json();
      
      if(msgEl){
        msgEl.textContent = j.ok ? '✓ High point calibrated' : ('✗ ' + (j.error||'Failed'));
        msgEl.style.display = 'block';
        msgEl.style.background = j.ok ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)';
        msgEl.style.borderColor = j.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)';
        msgEl.style.color = j.ok ? '#a7f3d0' : '#fecaca';
      }
      
      if(j.ok) setTimeout(loadEcCalibrationStatus, 1000);
    }catch(err){
      if(msgEl){
        msgEl.textContent = '✗ ' + err.message;
        msgEl.style.display = 'block';
      }
      console.error('[Sensors] EC cal high error:', err);
    }
  }
  
  async function ecShowStatus(){
    const msgEl = $('ec-calib-msg');
    try{
      const r = await fetch('/api/ec/cal/status', {cache:'no-store'});
      const j = await r.json();
      
      if(msgEl){
        let statusMsg = j.ok ? `Cal: ${j.cal || 'unknown'}, K: ${j.k != null ? j.k : 'unknown'}` : ('✗ ' + (j.error||'Failed'));
        msgEl.textContent = statusMsg;
        msgEl.style.display = 'block';
        msgEl.style.background = 'rgba(59,130,246,0.08)';
        msgEl.style.borderColor = 'rgba(59,130,246,0.3)';
        msgEl.style.color = '#93c5fd';
      }
    }catch(err){
      if(msgEl){
        msgEl.textContent = '✗ ' + err.message;
        msgEl.style.display = 'block';
      }
      console.error('[Sensors] EC status error:', err);
    }
  }
  
  // Wire up EC calibration buttons
  $('btnEcSetK')?.addEventListener('click', ecSetKFromDropdown);
  $('btnEcCalClear')?.addEventListener('click', ecCalClear);
  $('btnEcCalLow')?.addEventListener('click', ecCalLow);
  $('btnEcCalHigh')?.addEventListener('click', ecCalHigh);
  $('btnEcStatus')?.addEventListener('click', ecShowStatus);
  
  // Load EC K value on boot
  if($('ec-k-select')){
    loadEcCalibrationStatus();
  }
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', __rdwcSensorsBoot);
    console.log('[Sensors] Waiting for DOMContentLoaded');
  } else {
    console.log('[Sensors] DOM already loaded; booting immediately');
    __rdwcSensorsBoot();
  }
})();
