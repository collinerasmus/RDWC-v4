// System Controller mode logic for Overview tab
(function(){
  const $ = (id)=>document.getElementById(id);
  const show = (id, on)=>{ const el=$(id); if(el) el.style.display=on?'block':'none'; };
  const setActive = (btn, on)=>{ if(!btn) return; if(on) btn.classList.add('active'); else btn.classList.remove('active'); };
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };
  const postJSON = async (u,b)=>{ const r = await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json().catch(()=>({})); };

  let mode = localStorage.getItem('system_mode') || 'manual';
  let lastWrap = null;

  async function setMode(next){
    mode = next; localStorage.setItem('system_mode', next);
    
    // Optimistic UI update for BOTH button sets (Overview tab and System Settings tab)
    setActive($('system-mode-auto'), next==='auto');
    setActive($('system-mode-manual'), next==='manual');
    setActive($('system-mode-maint'), next==='maintenance');
    setActive($('mode-auto'), next==='auto');
    setActive($('mode-manual'), next==='manual');
    setActive($('mode-maint'), next==='maintenance');
    
    show('system-auto-content', next==='auto');
    show('system-manual-content', next==='manual');
    show('system-maint-content', next==='maintenance');
    updateHealth();
    
    // Persist backend system mode with propagation to all controllers
    try {
      await postJSON('/api/system_mode', {mode: next});
      console.log(`[System] Mode set to ${next}, propagated to all controllers`);
      
      // Wait for backend propagation to complete
      await new Promise(resolve => setTimeout(resolve, 150));
      
      // Trigger individual controller UI refresh
      console.log('[System] Refreshing all controller modes from backend...');
      const refreshPromises = [];
      if (window.refreshServerMode) refreshPromises.push(window.refreshServerMode().catch(e => console.warn('[System] Sensors mode sync failed:', e)));
      if (window.syncCircModeFromBackend) refreshPromises.push(window.syncCircModeFromBackend().catch(e => console.warn('[System] Circulation mode sync failed:', e)));
      if (window.syncLightsModeFromBackend) refreshPromises.push(window.syncLightsModeFromBackend().catch(e => console.warn('[System] Lights mode sync failed:', e)));
      if (window.syncScheduleModeFromBackend) refreshPromises.push(window.syncScheduleModeFromBackend().catch(e => console.warn('[System] Schedule mode sync failed:', e)));
      
      // Also trigger pH and EC if their sync functions are available
      if (window.phSetMode) {
        try { window.phSetMode(next, true); } catch(e) { console.warn('[System] pH mode set failed:', e); }
      }
      if (window.ecSetMode) {
        try { window.ecSetMode(next, true); } catch(e) { console.warn('[System] EC mode set failed:', e); }
      }
      
      await Promise.all(refreshPromises);
      console.log('[System] All controller modes refreshed');
      
      // Force refresh to show updated state
      setTimeout(() => refresh(), 100);
    } catch(e) {
      console.error('[System] Failed to set mode:', e);
    }
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
      
      // Sync button states from backend
      const backendMode = wrap.mode || 'manual';
      if (backendMode !== mode) {
        mode = backendMode;
        localStorage.setItem('system_mode', mode);
        // Update both button sets
        setActive($('system-mode-auto'), mode==='auto');
        setActive($('system-mode-manual'), mode==='manual');
        setActive($('system-mode-maint'), mode==='maintenance');
        setActive($('mode-auto'), mode==='auto');
        setActive($('mode-manual'), mode==='manual');
        setActive($('mode-maint'), mode==='maintenance');
      }
      
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
    // Don't call setMode(mode) here to avoid triggering API call on page load
    // Instead, just sync UI from localStorage
    setActive($('system-mode-auto'), mode==='auto');
    setActive($('system-mode-manual'), mode==='manual');
    setActive($('system-mode-maint'), mode==='maintenance');
    setActive($('mode-auto'), mode==='auto');
    setActive($('mode-manual'), mode==='manual');
    setActive($('mode-maint'), mode==='maintenance');
    show('system-auto-content', mode==='auto');
    show('system-manual-content', mode==='manual');
    show('system-maint-content', mode==='maintenance');
    
    refresh();
    setInterval(refresh, 5000);
    window.systemSetMode = setMode;
  }

  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
