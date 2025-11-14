// System Controller mode logic for Overview tab
(function(){
  const $ = (id)=>document.getElementById(id);
  const show = (id, on)=>{ const el=$(id); if(el) el.style.display=on?'block':'none'; };
  const setActive = (btn, on)=>{ if(!btn) return; if(on) btn.classList.add('active'); else btn.classList.remove('active'); };
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };
  const postJSON = async (u,b)=>{ const r = await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json().catch(()=>({})); };

  let mode = localStorage.getItem('system_mode') || 'manual';
  let lastWrap = null;

  function setMode(next){
    mode = next; localStorage.setItem('system_mode', next);
    setActive($('system-mode-auto'), next==='auto');
    setActive($('system-mode-manual'), next==='manual');
    setActive($('system-mode-maint'), next==='maintenance');
    show('system-auto-content', next==='auto');
    show('system-manual-content', next==='manual');
    show('system-maint-content', next==='maintenance');
    updateHealth();
    // Persist backend system mode (auto/manual only)
    if (next==='auto' || next==='manual'){
      postJSON('/api/relays/mode', {mode: next}).catch(()=>{});
    }
    // Maintenance mode affects safety.maintenance_override setting
    if (next==='maintenance'){
      fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({'safety.maintenance_override': 'true'})}).catch(()=>{});
    } else {
      fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({'safety.maintenance_override': 'false'})}).catch(()=>{});
    }
    // Propagate global intent to individual controllers (only auto/manual)
    try {
      if (next==='auto' && window.phSetMode) window.phSetMode('auto');
      if (next==='manual' && window.phSetMode) window.phSetMode('manual');
    }catch(e){}
    try {
      if (next==='auto' && window.ecSetMode) window.ecSetMode('auto');
      if (next==='manual' && window.ecSetMode) window.ecSetMode('manual');
    }catch(e){}
    // Environment (chiller) maps auto/manual; maintenance leaves per-controller specifics to user
    try {
      if (next==='auto' && window.envSetMode) window.envSetMode('auto');
      if (next==='manual' && window.envSetMode) window.envSetMode('manual');
    }catch(e){}
  }

  function updateHealth(){
    // Header chip id moved to system-relays-health
    const ind = $('system-relays-health') || $('system-health-indicator');
    if (!ind) return;
    const estop = !!(lastWrap && lastWrap.estop);
    if (estop){ ind.textContent = 'BLOCKED'; ind.className = 'ui-status-chip error'; ind.title='E-STOP active'; return; }
    if (mode==='maintenance'){ ind.textContent = 'MAINT'; ind.className = 'ui-status-chip warning'; ind.title='Maintenance mode: safeties bypassed'; return; }
    ind.textContent = 'OK'; ind.className = 'ui-status-chip success'; ind.title='System healthy';
  }

  async function refresh(){
    try{
      const wrap = await getJSON('/api/relays/status');
      lastWrap = wrap;
      updateHealth();
      updateSystemStatus(wrap);
    }catch(e){}
  }

  async function updateSystemStatus(wrap){
    // Update system status panel in System tab
    const modeEl = $('sys-mode-display');
    const estopEl = $('sys-estop-display');
    const sensorsEl = $('sys-sensors-display');
    const apiEl = $('sys-api-display');
    const piStatsEl = $('sys-pi-stats');

    if (modeEl) {
      const mode = wrap.mode || 'manual';
      modeEl.textContent = mode.toUpperCase();
      modeEl.style.color = mode === 'manual' ? '#94a3b8' : mode === 'maintenance' ? '#fb923c' : '#22c55e';
    }

    if (estopEl) {
      const estop = !!wrap.estop;
      estopEl.textContent = estop ? 'ACTIVE' : 'Off';
      estopEl.style.color = estop ? '#ef4444' : '#22c55e';
    }

    if (sensorsEl) {
      try {
        const ps = await getJSON('/api/sensors/status');
        const age = ps.last_sample_ts ? (Date.now()/1000 - ps.last_sample_ts) : 999;
        const online = ps.running && age < 60;
        sensorsEl.textContent = online ? 'ONLINE' : 'OFFLINE';
        sensorsEl.style.color = online ? '#22c55e' : '#ef4444';
      } catch(e) {
        sensorsEl.textContent = 'ERROR';
        sensorsEl.style.color = '#ef4444';
      }
    }

    if (apiEl) {
      // API is responding if we got here
      apiEl.textContent = 'ONLINE';
      apiEl.style.color = '#22c55e';
    }

    if (piStatsEl) {
      try {
        const health = await getJSON('/health');
        const uptime = health.uptime_seconds || 0;
        const days = Math.floor(uptime / 86400);
        const hours = Math.floor((uptime % 86400) / 3600);
        const mins = Math.floor((uptime % 3600) / 60);
        const uptimeStr = days > 0 ? `${days}d ${hours}h` : hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
        
        piStatsEl.innerHTML = `
          <div><strong>Version:</strong> ${health.version || 'unknown'}</div>
          <div><strong>API Uptime:</strong> ${uptimeStr}</div>
          <div><strong>Database:</strong> ${health.db_ok ? '✓ Connected' : '✗ Error'}</div>
          <div><strong>Camera:</strong> ${health.camera_ok ? '✓ Available' : '○ Unavailable'}</div>
        `;
      } catch(e) {
        piStatsEl.innerHTML = '<div style="color:#ef4444;">Unable to fetch system health</div>';
      }
    }
  }

  function init(){
    setMode(mode);
    refresh();
    setInterval(refresh, 5000);
    window.systemSetMode = setMode;
  }

  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
