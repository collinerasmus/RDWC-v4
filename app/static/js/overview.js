(function(){
  const q = (s)=>document.querySelector(s);
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };
  function setBadge(id, on){ const el = q(id); if (!el) return; el.textContent = ''; el.className = 'bop-status-badge '+(on?'on':'off'); el.setAttribute('role','status'); el.setAttribute('aria-live','polite'); el.setAttribute('aria-label', (id.replace('#','')+' '+(on?'on':'off')).replace(/[-_]/g,' ')); }
  function setChip(id, text, cls){ const el = q(id); if (!el) return; el.textContent = text; el.className = 'ui-status-chip ' + cls; el.setAttribute('role','status'); el.setAttribute('aria-live','polite'); el.setAttribute('aria-label', (id.replace('#','')+' '+text).replace(/[-_]/g,' ')); }
  const last = { chiller: 0, ph: 0, ec: 0, settings: 0, sensors: 0 };
  async function refresh(){
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
          const age = ps.last_sample_ts ? (Date.now()/1000 - ps.last_sample_ts) : 999;
          const online = ps.running && age < 60;
          const sensorHealthEl = q('#ov-sensors-health');
          if (sensorHealthEl) {
            const dot = online ? '🟢' : '🔴';
            const ageStr = age < 60 ? `${Math.round(age)}s` : age < 3600 ? `${Math.round(age/60)}m` : `${Math.round(age/3600)}h`;
            sensorHealthEl.textContent = online ? 'ONLINE' : 'OFFLINE';
            sensorHealthEl.className = 'ui-status-chip ' + (online ? 'success' : 'danger');
            sensorHealthEl.title = `Headless poller • Last sample: ${ageStr} ago • Polls: ${ps.poll_count || 0}`;
          }
          last.sensors = Date.now();
        }catch(e){ console.warn('[Overview] sensor poller status unavailable', e); }
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
  function init(){ refresh(); setInterval(refresh, 3000); bindEstopBtn(); }
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
