// System status display for Overview and System tabs
(function(){
  const $ = (id)=>document.getElementById(id);
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };

  let lastWrap = null;

  function updateHealth(){
    // Header chip for system relays health status
    const ind = $('system-relays-health') || $('system-health-indicator');
    if (!ind) return;
    const estop = !!(lastWrap && lastWrap.estop);
    if (estop){ 
      ind.textContent = 'BLOCKED'; 
      ind.className = 'ui-status-chip error'; 
      ind.title='E-STOP active'; 
      return; 
    }
    ind.textContent = 'OK'; 
    ind.className = 'ui-status-chip success'; 
    ind.title='System healthy';
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
    refresh();
    setInterval(refresh, 5000);
  }

  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
