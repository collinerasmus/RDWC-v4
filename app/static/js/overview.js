(function(){
  const q = (s)=>document.querySelector(s);
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };
  function setBadge(id, on){ const el = q(id); if (!el) return; el.className = 'bop-status-badge '+(on?'on':'off'); el.setAttribute('role','status'); el.setAttribute('aria-live','polite'); el.setAttribute('aria-label', (id.replace('#','')+' '+(on?'on':'off')).replace(/[-_]/g,' ')); }
  function setChip(id, text, cls){ const el = q(id); if (!el) return; el.textContent = text; el.className = 'ui-status-chip ' + cls; el.setAttribute('role','status'); el.setAttribute('aria-live','polite'); el.setAttribute('aria-label', (id.replace('#','')+' '+text).replace(/[-_]/g,' ')); }
  const last = { chiller: 0, ph: 0, ec: 0, settings: 0, sensors: 0, consolidated: 0 };
  let useConsolidated = true; // Feature flag for new consolidated endpoint
  
  async function refreshConsolidated(){
    try {
      const data = await getJSON('/api/controllers/status');
      const hb = q('#heartbeat'); if (hb) hb.textContent = 'heartbeat ' + new Date().toLocaleTimeString();
      
      // System-wide state
      const systemMode = data.system_mode || 'manual';
      const estop = !!data.estop;
      const maintOverride = !!data.maintenance_override;
      
      // Update E-STOP buttons
      const estopBtns = document.querySelectorAll('.header-estop-btn, #estop-btn');
      estopBtns.forEach(btn => {
        if (btn) {
          btn.textContent = estop ? '🚨 E-STOP ACTIVE' : (btn.id === 'estop-btn' ? 'E‑STOP' : 'E-STOP');
          btn.className = estop ? 'btn-secondary' : 'btn-secondary';
          btn.style.background = estop ? 'rgba(239,68,68,0.2)' : '';
          btn.style.borderColor = estop ? '#ef4444' : '';
          btn.style.color = estop ? '#ef4444' : '';
        }
      });
      
      // Update mode selector buttons (system-wide)
      const autoBtn = q('#system-mode-auto');
      const manualBtn = q('#system-mode-manual');
      const maintBtn = q('#system-mode-maint');
      if (autoBtn) autoBtn.className = systemMode === 'auto' ? 'btn-chip active' : 'btn-chip';
      if (manualBtn) manualBtn.className = systemMode === 'manual' ? 'btn-chip active' : 'btn-chip';
      if (maintBtn) maintBtn.className = systemMode === 'maintenance' ? 'btn-chip active' : 'btn-chip';
      
      // Show maintenance override banner if active
      let banner = q('#maintenance-override-banner');
      if (maintOverride && !banner) {
        const container = q('.container');
        if (container) {
          banner = document.createElement('div');
          banner.id = 'maintenance-override-banner';
          banner.style.cssText = 'background:rgba(245,158,11,0.15);border:2px solid #f59e0b;color:#fbbf24;padding:12px;margin:12px 0;border-radius:8px;font-weight:600;text-align:center;';
          banner.innerHTML = '⚠️ MAINTENANCE OVERRIDE ACTIVE ⚠️';
          container.insertBefore(banner, container.firstChild);
        }
      } else if (!maintOverride && banner) {
        banner.remove();
      }
      
      // Controllers
      const controllers = data.controllers || {};
      
      // pH Controller
      if (controllers.ph) {
        const ph = controllers.ph;
        const guards = ph.guards || {};
        const hardKeys = ['estop','reservoir'];
        const softKeys = ['safe_off','sensor_stale','interval','daily_cap','ec_baseline_low'];
        const hardActive = hardKeys.some(k => !!guards[k]);
        const softActive = softKeys.some(k => !!guards[k]);
        
        let healthText = 'OK', healthClass = 'success';
        if (hardActive) { healthText = 'BLOCKED'; healthClass = 'danger'; }
        else if (softActive) { healthText = 'GUARDED'; healthClass = 'warning'; }
        
        setChip('#ov-ph-health', healthText, healthClass);
        setChip('#ov-ph-modechip', ph.auto_enabled ? 'AUTO' : 'MANUAL', ph.auto_enabled ? 'success' : 'neutral');
        
        const allActive = [...hardKeys.filter(k=>!!guards[k]), ...softKeys.filter(k=>!!guards[k])];
        const phHealthEl = q('#ov-ph-health');
        if (phHealthEl) {
          phHealthEl.title = allActive.length ? ('Active guards: ' + allActive.join(', ')) : 'All guards OK';
          if (ph.holding_reason) phHealthEl.title += ` | Holding: ${ph.holding_reason}`;
          if (ph.learned_ml_per_pH) phHealthEl.title += ` | Learned: ${ph.learned_ml_per_pH.toFixed(2)} ml/pH`;
        }
      }
      
      // EC Controller
      if (controllers.ec) {
        const ec = controllers.ec;
        const guards = ec.guards || {};
        const hardKeys = ['estop','reservoir'];
        const softKeys = ['sensor_stale','mix_lock','interval','daily_cap'];
        const hardActive = hardKeys.some(k => !!guards[k]);
        const softActive = softKeys.some(k => !!guards[k]);
        
        let healthText = 'OK', healthClass = 'success';
        if (hardActive) { healthText = 'BLOCKED'; healthClass = 'danger'; }
        else if (softActive) { healthText = 'GUARDED'; healthClass = 'warning'; }
        
        setChip('#ov-ec-health', healthText, healthClass);
        setChip('#ov-ec-modechip', ec.auto_enabled ? 'AUTO' : 'MANUAL', ec.auto_enabled ? 'success' : 'neutral');
        
        const allActive = [...hardKeys.filter(k=>!!guards[k]), ...softKeys.filter(k=>!!guards[k])];
        const ecHealthEl = q('#ov-ec-health');
        if (ecHealthEl) {
          ecHealthEl.title = allActive.length ? ('Active guards: ' + allActive.join(', ')) : 'All guards OK';
          if (ec.holding_reason) ecHealthEl.title += ` | Holding: ${ec.holding_reason}`;
          if (ec.learned_ml_per_mScm) ecHealthEl.title += ` | Learned: ${ec.learned_ml_per_mScm.toFixed(2)} ml/mS/cm`;
        }
      }
      
      // Chiller Controller
      if (controllers.chiller) {
        const chiller = controllers.chiller;
        const tempStr = chiller.current_temp ? ` ${chiller.current_temp.toFixed(1)}°C` : '';
        const modeText = chiller.mode === 'manual' ? 'MANUAL' : chiller.mode === 'maintenance' ? 'MAINT' : 'AUTO';
        setChip('#ov-chiller-modechip', modeText + tempStr, 
                chiller.mode === 'manual' ? 'neutral' : chiller.mode === 'maintenance' ? 'warning' : 'success');
      }
      
      // Lights Controller
      if (controllers.lights) {
        const lights = controllers.lights;
        setBadge('#ov-lights', lights.is_on);
        setChip('#ov-lights-modechip', 
                lights.mode === 'manual' ? 'MANUAL' : 'SCHEDULE', 
                lights.mode === 'manual' ? 'neutral' : 'success');
      }
      
      // Circulation Controller
      if (controllers.circulation) {
        const circ = controllers.circulation;
        setBadge('#ov-main-pump', circ.main_pump);
        setBadge('#ov-chiller-pump', circ.chiller_pump);
        setChip('#ov-main-pump-modechip', 
                circ.mode === 'manual' ? 'MANUAL' : 'PROTECTED', 
                circ.mode === 'manual' ? 'neutral' : 'success');
      }
      
      // Update chiller power badge (from relay status - need to keep for now)
      try {
        const relayStatus = await getJSON('/api/relays/status');
        const rel = relayStatus.relays || {};
        setBadge('#ov-chiller', !!(rel.chiller_power && rel.chiller_power.is_on));
      } catch(e) { /* ignore */ }
      
      last.consolidated = Date.now();
    } catch(e) {
      console.error('[Overview] Consolidated endpoint failed, falling back to legacy', e);
      useConsolidated = false; // Fall back to legacy mode on error
    }
  }
  
  async function updateSensors() {
    // Sensor poller status (separate from consolidated endpoint)
    if (Date.now() - last.sensors < 6000) return;
    try {
      const ps = await getJSON('/api/sensors/status');
      const age = ps.last_sample_ts ? (Date.now()/1000 - ps.last_sample_ts) : 9e9;
      const online = ps.running && age < 60;
      let stale = false;
      try {
        const s = await getJSON('/api/sensors');
        if (s && s.ts) {
          const tsAge = Math.max(0, Math.round((Date.now() - new Date(s.ts).getTime())/1000));
          stale = !online && tsAge < 600;
        }
      } catch(_) { /* ignore */ }
      
      const sensorHealthEl = q('#ov-sensors-health');
      const sensorStatusEl = q('#ov-sensors-status');
      const sensorModeEl = q('#ov-sensors-modechip');
      
      if (sensorHealthEl) {
        const ageStr = age < 60 ? `${Math.round(age)}s` : age < 3600 ? `${Math.round(age/60)}m` : `${Math.round(age/3600)}h`;
        sensorHealthEl.textContent = online ? 'ONLINE' : (stale ? 'STALE' : 'OFFLINE');
        sensorHealthEl.className = 'ui-status-chip ' + (online ? 'success' : (stale ? 'warning' : 'danger'));
        sensorHealthEl.title = online
          ? `Headless poller • Last sample: ${ageStr} ago • Polls: ${ps.poll_count || 0}`
          : (stale ? 'Poller down; showing recent DB/cache values (<10m old)' : 'Poller down; no recent data');
      }
      if (sensorStatusEl) {
        sensorStatusEl.textContent = online ? 'ACTIVE' : (stale ? 'RECENT' : 'OFF');
        sensorStatusEl.className = 'ui-status-chip ' + (online ? 'success' : (stale ? 'warning' : 'danger'));
        sensorStatusEl.title = online ? 'Sensor poller active' : (stale ? 'Recent DB/cache fallback' : 'No sensor data');
      }
      if (sensorModeEl) {
        // Get system mode from relays status for sensor mode display
        try {
          const wrap = await getJSON('/api/relays/status');
          sensorModeEl.textContent = wrap && wrap.mode ? wrap.mode.toUpperCase() : 'MANUAL';
          sensorModeEl.className = 'ui-status-chip ' + ((wrap && wrap.mode === 'auto') ? 'success' : 'neutral');
          sensorModeEl.title = 'Sensors mode';
        } catch(_) { /* ignore */ }
      }
      last.sensors = Date.now();
    } catch(e) { 
      console.warn('[Overview] sensor poller status unavailable', e); 
    }
  }
  
  async function refresh(){
    // Try consolidated endpoint first (more efficient, single request)
    if (useConsolidated && (Date.now() - last.consolidated > 2000)) {
      await refreshConsolidated();
      // Still need to update sensors separately as they're not in consolidated yet
      await updateSensors();
      return;
    }
    
    // Legacy fallback path
    try{
  const wrap = await getJSON('/api/relays/status');
  // Debug heartbeat
  const hb = q('#heartbeat'); if (hb) hb.textContent = 'heartbeat ' + new Date().toLocaleTimeString();
      const rel = wrap.relays || {};
      setBadge('#ov-lights', !!(rel.lights && rel.lights.is_on));
      setBadge('#ov-main-pump', !!(rel.main_pump && rel.main_pump.is_on));
      setBadge('#ov-chiller-pump', !!(rel.chiller_pump && rel.chiller_pump.is_on));
      setBadge('#ov-chiller', !!(rel.chiller_power && rel.chiller_power.is_on));
      const mode = wrap.mode || 'manual';
      const estop = !!wrap.estop;
      
      // Update mode chips for each controller (compact, unified)
      setChip('#ov-lights-modechip', mode === 'manual' ? 'MANUAL' : 'SCHEDULE', mode === 'manual' ? 'neutral' : 'success');
      setChip('#ov-main-pump-modechip', mode === 'manual' ? 'MANUAL' : 'PROTECTED', mode === 'manual' ? 'neutral' : 'success');
      
      // Environment (chiller): fetch temperature and show with system mode
      const now = Date.now();
      if (now - last.chiller > 6000) {
        try {
          const chillerStatus = await getJSON('/api/chiller/status');
          const tempInfo = chillerStatus.current_temp ? ` ${chillerStatus.current_temp.toFixed(1)}°C` : '';
          const modeText = mode === 'manual' ? 'MANUAL' : mode === 'maintenance' ? 'MAINT' : 'AUTO';
          setChip('#ov-chiller-modechip', modeText + tempInfo, mode === 'manual' ? 'neutral' : mode === 'maintenance' ? 'warning' : 'success');
          last.chiller = now;
        } catch(e) {
          const modeText = mode === 'manual' ? 'MANUAL' : mode === 'maintenance' ? 'MAINT' : 'AUTO';
          setChip('#ov-chiller-modechip', modeText, mode === 'manual' ? 'neutral' : mode === 'maintenance' ? 'warning' : 'success');
        }
      }
      // Update E-STOP button state for all buttons
      const estopBtns = document.querySelectorAll('.header-estop-btn, #estop-btn');
      estopBtns.forEach(estopBtn => {
        if (estopBtn) {
          estopBtn.textContent = estop ? '🚨 E-STOP ACTIVE' : (estopBtn.id === 'estop-btn' ? 'E‑STOP' : 'E-STOP');
          estopBtn.className = estop ? 'btn-secondary' : 'btn-secondary';
          estopBtn.style.background = estop ? 'rgba(239,68,68,0.2)' : '';
          estopBtn.style.borderColor = estop ? '#ef4444' : '';
          estopBtn.style.color = estop ? '#ef4444' : '';
        }
      });
      // Derive controller health: reuse relay+sensor freshness and guards endpoints for lightweight overview
      const now2 = Date.now();
      if (now2 - last.ph > 6000) {
        try {
          const ph = await getJSON('/api/ph/status');
          const phGuards = ph.guards || {};
          const hardKeys = ['estop','reservoir'];
          const softKeys = ['safe_off','sensor_stale','interval','daily_cap','ec_baseline_low'];
          const hardActive = hardKeys.some(k => !!phGuards[k]);
          const softActive = softKeys.some(k => !!phGuards[k]);
          let phHealthText = 'OK';
          let phHealthClass = 'success';
          if (hardActive){ phHealthText = 'BLOCKED'; phHealthClass = 'danger'; }
          else if (softActive){ phHealthText = 'GUARDED'; phHealthClass = 'warning'; }
          setChip('#ov-ph-health', phHealthText, phHealthClass);
          const phModeChip = q('#ov-ph-modechip'); if (phModeChip) { phModeChip.textContent = (ph.auto && ph.auto.enabled)?'AUTO':'MANUAL'; phModeChip.className = 'ui-status-chip ' + ((ph.auto && ph.auto.enabled)?'success':'neutral'); }
          // Tooltip summarizing guards
          const allActive = [...hardKeys.filter(k=>!!phGuards[k]), ...softKeys.filter(k=>!!phGuards[k])];
          const phHealthEl = q('#ov-ph-health'); if (phHealthEl) phHealthEl.title = allActive.length? ('Active guards: '+allActive.join(', ')) : 'All guards OK';
          last.ph = now2;
        } catch(e){ setChip('#ov-ph-health', '—', 'neutral'); }
      }
      if (now2 - last.ec > 6000) {
        try {
          const ec = await getJSON('/api/ec/status');
          const ecGuards = ec.guards || {};
          const hardKeys = ['estop','reservoir'];
          const softKeys = ['sensor_stale','mix_lock','interval','daily_cap'];
          const hardActive = hardKeys.some(k => !!ecGuards[k]);
          const softActive = softKeys.some(k => !!ecGuards[k]);
          let ecHealthText = 'OK';
          let ecHealthClass = 'success';
          if (hardActive){ ecHealthText = 'BLOCKED'; ecHealthClass = 'danger'; }
          else if (softActive){ ecHealthText = 'GUARDED'; ecHealthClass = 'warning'; }
          setChip('#ov-ec-health', ecHealthText, ecHealthClass);
          const ecModeChip = q('#ov-ec-modechip'); if (ecModeChip) { ecModeChip.textContent = (ec.auto && ec.auto.enabled)?'AUTO':'MANUAL'; ecModeChip.className = 'ui-status-chip ' + ((ec.auto && ec.auto.enabled)?'success':'neutral'); }
          const allActive = [...hardKeys.filter(k=>!!ecGuards[k]), ...softKeys.filter(k=>!!ecGuards[k])];
          const ecHealthEl = q('#ov-ec-health'); if (ecHealthEl) ecHealthEl.title = allActive.length? ('Active guards: '+allActive.join(', ')) : 'All guards OK';
          last.ec = now2;
        } catch(e){ setChip('#ov-ec-health', '—', 'neutral'); }
      }
      // Sensor poller status in dedicated card
      if (Date.now() - last.sensors > 6000) {
        try{
          const ps = await getJSON('/api/sensors/status');
          const age = ps.last_sample_ts ? (Date.now()/1000 - ps.last_sample_ts) : 9e9;
          const online = ps.running && age < 60;
          // Derive a softer state using DB/cache age when poller is down
          let stale = false;
          try {
            const s = await getJSON('/api/sensors');
            if (s && s.ts) {
              const tsAge = Math.max(0, Math.round((Date.now() - new Date(s.ts).getTime())/1000));
              stale = !online && tsAge < 600; // show STALE if we have recent DB/cache within 10min
            }
          } catch(_) { /* ignore */ }
          const sensorHealthEl = q('#ov-sensors-health');
          const sensorStatusEl = q('#ov-sensors-status');
          const sensorModeEl = q('#ov-sensors-modechip');
          if (sensorHealthEl) {
            const ageStr = age < 60 ? `${Math.round(age)}s` : age < 3600 ? `${Math.round(age/60)}m` : `${Math.round(age/3600)}h`;
            sensorHealthEl.textContent = online ? 'ONLINE' : (stale ? 'STALE' : 'OFFLINE');
            sensorHealthEl.className = 'ui-status-chip ' + (online ? 'success' : (stale ? 'warning' : 'danger'));
            sensorHealthEl.title = online
              ? `Headless poller • Last sample: ${ageStr} ago • Polls: ${ps.poll_count || 0}`
              : (stale ? 'Poller down; showing recent DB/cache values (<10m old)' : 'Poller down; no recent data');
          }
          if (sensorStatusEl) {
            sensorStatusEl.textContent = online ? 'ACTIVE' : (stale ? 'RECENT' : 'OFF');
            sensorStatusEl.className = 'ui-status-chip ' + (online ? 'success' : (stale ? 'warning' : 'danger'));
            sensorStatusEl.title = online ? 'Sensor poller active' : (stale ? 'Recent DB/cache fallback' : 'No sensor data');
          }
          if (sensorModeEl) {
            sensorModeEl.textContent = wrap && wrap.mode ? wrap.mode.toUpperCase() : 'MANUAL';
            sensorModeEl.className = 'ui-status-chip ' + ((wrap && wrap.mode === 'auto') ? 'success' : 'neutral');
            sensorModeEl.title = 'Sensors mode';
          }
          last.sensors = Date.now();
        }catch(e){ console.warn('[Overview] sensor poller status unavailable', e); }
      }
      // System status (mode + health + status)
      const systemModeChip = q('#ov-system-modechip');
      const systemHealthChip = q('#ov-system-health');
      const systemStatusChip = q('#ov-system-status');
      if (systemModeChip && wrap) {
        const mode = wrap.mode || 'manual';
        const modeText = mode === 'manual' ? 'MANUAL' : mode === 'maintenance' ? 'MAINT' : 'AUTO';
        systemModeChip.textContent = modeText;
        systemModeChip.className = 'ui-status-chip ' + (mode === 'manual' ? 'neutral' : mode === 'maintenance' ? 'warning' : 'success');
        systemModeChip.title = 'System mode';
      }
      if (systemHealthChip && wrap) {
        const estop = !!wrap.estop;
        systemHealthChip.textContent = estop ? 'E-STOP' : 'OK';
        systemHealthChip.className = 'ui-status-chip ' + (estop ? 'danger' : 'success');
        systemHealthChip.title = estop ? 'Emergency stop active' : 'System nominal';
      }
      if (systemStatusChip && wrap) {
        systemStatusChip.textContent = wrap.estop ? 'BLOCKED' : 'ACTIVE';
        systemStatusChip.className = 'ui-status-chip ' + (wrap.estop ? 'danger' : 'success');
        systemStatusChip.title = wrap.estop ? 'System blocked by E-STOP' : 'System active';
      }
      // Schedule status (mode + status)
      const scheduleChip = q('#ov-schedule-chip');
      const scheduleStatusChip = q('#ov-schedule-status');
      const scheduleModeChip = q('#ov-schedule-modechip');
      if (scheduleChip && wrap) {
        const enabled = wrap.mode === 'auto';
        scheduleChip.textContent = enabled ? 'ENABLED' : 'DISABLED';
        scheduleChip.className = 'ui-status-chip ' + (enabled ? 'success' : 'neutral');
        scheduleChip.title = 'Schedule status';
      }
      if (scheduleStatusChip && wrap) {
        scheduleStatusChip.textContent = wrap.mode === 'auto' ? 'ACTIVE' : 'OFF';
        scheduleStatusChip.className = 'ui-status-chip ' + (wrap.mode === 'auto' ? 'success' : 'neutral');
        scheduleStatusChip.title = 'Schedule activity';
      }
      if (scheduleModeChip && wrap) {
        scheduleModeChip.textContent = wrap.mode ? wrap.mode.toUpperCase() : 'MANUAL';
        scheduleModeChip.className = 'ui-status-chip ' + (wrap.mode === 'auto' ? 'success' : 'neutral');
        scheduleModeChip.title = 'Schedule mode';
      }
    }catch(e){ console.warn('[Overview] refresh failed', e); }
    // Performance hydration mark (first successful pass)
    if (!window.__overviewHydrated){
      window.__overviewHydrated = true;
      try {
        const tSinceNav = (performance.now()).toFixed(0);
        performance.mark('overview-hydrated');
        console.log('[Perf] overview hydrated at ~'+tSinceNav+'ms');
        const evt = new CustomEvent('overview-hydrated', { detail: { ms: Number(tSinceNav) } });
        window.dispatchEvent(evt);
      } catch(_){}
    }
  }
  function init(){
    if (window.UI_DEMO){
      console.warn('[Overview] UI_DEMO active: simulating overview chips');
      const set = (id, text, cls)=>{ const el=q(id); if(el){ el.textContent=text; el.className='ui-status-chip '+cls; }};
      const b = (id, on)=>{ const el=q(id); if(el){ el.className='bop-status-badge '+(on?'on':'off'); }};
      // Simulate stable healthy system
      set('#ov-ph-modechip','MANUAL','neutral'); set('#ov-ph-health','GUARDED','warning');
      set('#ov-ec-modechip','MANUAL','neutral'); set('#ov-ec-health','GUARDED','warning');
      set('#ov-chiller-modechip','AUTO 19.8°C','success');
      set('#ov-main-pump-modechip','PROTECTED','success');
      set('#ov-lights-modechip','SCHEDULE','success');
      set('#ov-schedule-chip','ENABLED','success');
      set('#ov-system-modechip','MANUAL','neutral'); set('#ov-system-health','OK','success');
      const el=q('#ov-sensors-health'); if(el){ el.textContent='ONLINE'; el.className='ui-status-chip success'; }
      b('#ov-lights', true); b('#ov-main-pump', true); b('#ov-chiller-pump', true); b('#ov-chiller', true);
      bindEstopBtn();
      return; // Skip network refresh in demo
    }
    refresh(); setInterval(refresh, 3000); bindEstopBtn();
  }
  // System mode setter for UI buttons
  window.systemSetMode = async function(mode) {
    if (!['auto', 'manual', 'maintenance'].includes(mode)) return;
    try {
      const res = await fetch('/api/system_mode', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({mode})
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      // Optimistic UI update
      const autoBtn = q('#system-mode-auto');
      const manualBtn = q('#system-mode-manual');
      const maintBtn = q('#system-mode-maint');
      if (autoBtn) autoBtn.className = mode === 'auto' ? 'btn-chip active' : 'btn-chip';
      if (manualBtn) manualBtn.className = mode === 'manual' ? 'btn-chip active' : 'btn-chip';
      if (maintBtn) maintBtn.className = mode === 'maintenance' ? 'btn-chip active' : 'btn-chip';
      // Force immediate refresh after 100ms to allow backend propagation to complete
      // This debounce prevents race conditions between mode change API call and status refresh
      setTimeout(() => { useConsolidated = true; refresh(); }, 100);
    } catch(e) {
      console.error('[Overview] Failed to set system mode:', e);
      alert('Failed to set system mode: ' + e.message);
    }
  };
  
  function bindEstopBtn(){
    // Bind all E-STOP buttons across all tabs
    const btns = document.querySelectorAll('.header-estop-btn, #estop-btn');
    btns.forEach(btn => {
      if (btn.__bound) return;
      btn.addEventListener('click', async ()=>{
        try {
          await fetch('/api/relays/estop/toggle', {method:'POST'});
          setTimeout(refresh, 200);
        } catch(e){ console.warn('[Overview] estop toggle failed', e); }
      });
      btn.__bound = true;
    });
  }
  async function bindMaintToggle(){
    const el = q('#ov-maint-toggle');
    if (!el) return;
    try{
      const s = await (await fetch('/api/settings',{cache:'no-store'})).json();
      const current = (s && s.safety && (s.safety.maintenance_override||'false')).toLowerCase()==='true';
      el.checked = current;
    }catch(e){}
    el.addEventListener('change', async ()=>{
      const val = el.checked ? 'true' : 'false';
      try{
        const r = await fetch('/api/settings', {
          method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ 'safety.maintenance_override': val })
        });
        if (!r.ok) throw new Error('HTTP '+r.status);
      }catch(e){ console.warn('[Overview] failed to set maintenance_override', e); el.checked = !el.checked; }
    });
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', ()=>{ init(); bindMaintToggle(); }); else { init(); bindMaintToggle(); }
})();
