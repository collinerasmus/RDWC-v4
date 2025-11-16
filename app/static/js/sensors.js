/* Sensors real-time display with color thresholds and calibration status */
(function(){
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
      const updated = $("sensors-updated");
      if (updated){ updated.innerHTML = 'Updated: '+new Date().toLocaleTimeString()+ ' <span style="color:#22c55e;">(demo)</span>'; }
      setOnline(true);
    }, 3000);
    return; // Abort real wiring
  }
  
  // Runtime timers for network vs simulation
  let netTimer = null, simTimer = null, ready = false;

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
    const updated = $("sensors-updated");
    if (updated){ updated.innerHTML = 'Updated: '+new Date().toLocaleTimeString()+ (label?` <span style="color:#22c55e;">(${label})</span>`:''); }
    setOnline(true);
  }

  function stopTimers(){ if (netTimer){ clearInterval(netTimer); netTimer=null; } if (simTimer){ clearInterval(simTimer); simTimer=null; } }
  function ensurePolling(){
    stopTimers();
    // Always poll backend (maintenance mode now served via effective values)
    tick();
    const poll = (window.APP_POLL && window.APP_POLL.sensors) ? (parseInt(window.APP_POLL.sensors,10)||5000) : 5000;
    netTimer = setInterval(tick, Math.max(1500, poll));
  }

  async function fetchHealthDB(){
    try{
      const r = await fetch('/health/db', {cache:'no-store'});
      if(!r.ok) return null;
      return await r.json();
    }catch(e){ return null; }
  }
  
  function renderHealthBadge(h){
    const el = $("sensors-health-badge");
    if (!el) return;
    const age = h?.cache_age_s ?? null;
    const dbAge = h?.db_age_s ?? null;
    let text = "OK", style = {bg:"rgba(34,197,94,0.12)", bd:"rgba(34,197,94,0.4)", fg:"#86efac"};
    if (!h?.cache_has_data) {
      text = (typeof dbAge === 'number') ? `Offline (DB ${Math.round(dbAge)}s)` : "Offline";
      style = {bg:"rgba(239,68,68,0.12)", bd:"rgba(239,68,68,0.4)", fg:"#fecaca"};
    } else if (!h?.cache_fresh) {
      text = `Stale ${Math.round(age)}s`;
      style = {bg:"rgba(234,179,8,0.12)", bd:"rgba(234,179,8,0.4)", fg:"#fde68a"};
    }
    el.textContent = text;
    el.style.background = style.bg;
    el.style.border = `1px solid ${style.bd}`;
    el.style.color = style.fg;
    el.title = `Cache age: ${age ?? 'n/a'}s` + (dbAge!=null? `, DB age: ${dbAge}s` : "");
  }
  
  async function tick(){
    // Always fetch; backend applies maintenance overrides
    try{
      const r = await fetch("/api/sensors", {cache:"no-store"});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      
      const t = j.temperature_c ?? null;
      const e = j.ec_mscm ?? null;
      const p = j.ph ?? null;
      __lastSensorsOnline = !!j.online;
      
  // Adapted: use KPI elements directly (ids kpiTemp/kpiEc/kpiPh)
  setMetric($("kpiTemp"), t, classify("temp", t));
  setMetric($("kpiEc"),   e, classify("ec", e));
  setMetric($("kpiPh"),   p, classify("ph", p));
      
  // Calibration badge elements may be absent in this layout; guard safely
  setBadge($("cal-badge-temp"), j.cal?.temp?.is_calibrated === true, j.cal?.temp?.detail || "");
  setBadge($("cal-badge-ec"),   j.cal?.ec?.is_calibrated === true,   j.cal?.ec?.detail || "");
  setBadge($("cal-badge-ph"),   j.cal?.ph?.is_calibrated === true,   j.cal?.ph?.detail || "");
      
      setOnline(!!j.online);
      
      const updated = $("sensors-updated");
      if (updated) {
        let ts = j.ts ? new Date(j.ts) : new Date();
        const age = Math.max(0, Math.round((Date.now() - ts.getTime())/1000));
        // Show age in updated text with color coding
        let ageColor = '#22c55e'; // green
        if (age >= 300) ageColor = '#ef4444'; // red
        else if (age >= 60) ageColor = '#f59e0b'; // yellow
        updated.innerHTML = `Updated: ${ts.toLocaleTimeString()} <span style="color:${ageColor};">(${age}s ago)</span>`;
      }
      // Fetch sensor cache health and DB health in parallel (non-blocking)
      fetch('/api/sensors/health', {cache:'no-store'})
        .then(r=>r.ok?r.json():null)
        .then(h=>{ if (h){ __lastSensorsHealth = h; renderHealthBadge(h); updateSensorsHealth(); } })
        .catch(()=>{});

      fetchHealthDB().then(health=>{
        const dot = $("sensorsFreshnessDot");
        if (health && dot){
          const age = Number(health.age_seconds||0);
          const rows5 = Number(health.recent_rows_5min||0);
          if (age < 180){ dot.style.background = '#22c55e'; }
          else if (age < 600){ dot.style.background = '#f59e0b'; }
          else { dot.style.background = '#ef4444'; }
          dot.title = `DB age: ${Math.round(age)}s, last 5m: ${rows5} rows`;
        }
      }).catch(()=>{});

      // Update overrides panel (original vs effective)
      updateOverridesPanel(j);
    }catch(err){
      console.error("[Sensors] Fetch error:", err);
      setOnline(false);
      __lastSensorsOnline = false;
      updateSensorsHealth();
      // Fallback: attempt /api/sensors/status then /api/sensors/read (db mode)
      try {
        const statusR = await fetch('/api/sensors/status',{cache:'no-store'});
        if (statusR.ok){
          const statusJ = await statusR.json();
          if (Array.isArray(statusJ.recent) && statusJ.recent.length){
            const row = statusJ.recent[0];
            const t = row.temperature_c ?? row.temp_c ?? null;
            const e = row.ec_mscm ?? row.ec_ms_cm ?? null;
            const p = row.ph ?? null;
            setMetric($("kpiTemp"), t, classify("temp", t));
            setMetric($("kpiEc"),   e, classify("ec", e));
            setMetric($("kpiPh"),   p, classify("ph", p));
            const updated = $("sensors-updated");
            if (updated && row.ts){
              const ts = new Date(row.ts * 1000);
              const age = Math.max(0, Math.round((Date.now() - ts.getTime())/1000));
              updated.innerHTML = `Updated: ${ts.toLocaleTimeString()} <span style="color:${age>=300?'#ef4444':age>=60?'#f59e0b':'#22c55e'};">(${age}s ago)</span>`;
            }
            return; // Fallback satisfied
          }
        }
        // Secondary fallback: /api/sensors/read (db)
        const lastR = await fetch('/api/sensors/read',{cache:'no-store'});
        if (lastR.ok){
          const lastJ = await lastR.json();
          const t = lastJ.temperature_c ?? null;
          const e = lastJ.ec_mscm ?? null;
          const p = lastJ.ph ?? null;
          setMetric($("kpiTemp"), t, classify("temp", t));
          setMetric($("kpiEc"),   e, classify("ec", e));
          setMetric($("kpiPh"),   p, classify("ph", p));
        }
      } catch(_) { /* swallow fallback errors */ }
    }
  }
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
  // Recent readings now embedded in settings details (always visible when expanded)
  async function refreshRecent(){
    const list = $("s-recent");
    if(!list) return;
    try{
      const r = await fetch('/api/sensors/status', {cache:'no-store'});
      if(!r.ok) throw new Error('HTTP '+r.status);
      const j = await r.json();
      const rows = j?.recent || [];
      if(rows.length===0){ list.innerHTML = '<div style="padding:2px 0;">No recent readings</div>'; return; }
      // Take first 5 (already sorted newest first by API)
      list.innerHTML = rows.slice(0,5).map(e => {
        const when = e.ts?.replace('T',' ').replace('Z','') || '—';
        const ph = e.ph!=null? e.ph.toFixed(2):'—';
        const ec = e.ec_mscm!=null? e.ec_mscm.toFixed(2):'—';
        const t  = e.temperature_c!=null? e.temperature_c.toFixed(2):'—';
        return `<div style="padding:2px 0;">${when} • pH ${ph} • EC ${ec} • Temp ${t}°C</div>`;
      }).join('');
    }catch(e){ list.innerHTML = '<div style="padding:2px 0;color:#f59e0b;">Load error</div>'; }
  }
  
  document.addEventListener("DOMContentLoaded", ()=>{
    console.log("[Sensors] Initializing real-time updates");
    ready = true;
    ensurePolling();
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
    setInterval(refreshServerMode, 5000);
    // Initialize recent readings list
    refreshRecent();
    // Periodically refresh recent list (every 45s)
    setInterval(refreshRecent, 45000);
    // Read now handler (only enabled in Manual/Maintenance mode)
    const btn = $("btnSensorsReadNow");
    if (btn){
      const updateBtnState = ()=>{
        if (sensorsMode === 'auto'){
          btn.disabled = true;
          btn.title = 'Read now is only available in Manual or Maintenance mode';
        } else {
          btn.disabled = false;
          btn.title = 'Trigger immediate sensor read';
        }
      };
      updateBtnState();
      // Re-check whenever mode changes
      const origSetMode = window.sensorsSetMode;
      window.sensorsSetMode = (m)=>{ origSetMode(m); updateBtnState(); };
      
      btn.addEventListener('click', async ()=>{
        if (sensorsMode === 'auto') return; // safety guard
        try{
          btn.disabled = true; btn.textContent = (sensorsMode==='maintenance')?'Simulating...':'Reading...';
          if (sensorsMode==='maintenance'){
            simulateStep('manual');
          } else {
            const r = await fetch('/read_now', {method:'POST'});
            setTimeout(()=>{ tick(); }, 1000);
          }
        }catch(e){ console.warn('[Sensors] read_now failed', e); }
        finally{ updateBtnState(); btn.textContent = 'Read now'; }
      });
    }
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
    setInterval(loadSensorOverrides, 15000);
    toggleOverridesVisibility();
  });
})();
