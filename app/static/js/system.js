// System Controller status for Overview tab
// NOTE: Old mode system (AUTO/MANUAL/MAINTENANCE) is DEPRECATED
// New system uses /api/auto/* endpoints with global_auto and per-controller auto flags
(function(){
  const $ = (id)=>document.getElementById(id);
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };
  const postJSON = async (u,b)=>{ const r = await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json().catch(()=>({})); };

  let lastWrap = null;
  let globalAuto = false;

  // DEPRECATED: Old setMode function kept for backward compatibility
  // Now just updates global auto enable
  function setMode(next){
    if (next === 'auto') {
      postJSON('/api/auto/global', {enabled: true}).catch(()=>{});
    } else if (next === 'manual') {
      postJSON('/api/auto/global', {enabled: false}).catch(()=>{});
    }
    // Maintenance mode affects safety.maintenance_override setting
    if (next === 'maintenance'){
      fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({'safety.maintenance_override': 'true'})}).catch(()=>{});
    } else {
      fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({'safety.maintenance_override': 'false'})}).catch(()=>{});
    }
  }

  function updateHealth(){
    // Header chip id moved to system-relays-health
    const ind = $('system-relays-health') || $('system-health-indicator');
    if (!ind) return;
    const estop = !!(lastWrap && lastWrap.estop);
    if (estop){ ind.textContent = 'BLOCKED'; ind.className = 'ui-status-chip error'; ind.title='E-STOP active'; return; }
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

    // Fetch auto status
    try {
      const autoStatus = await getJSON('/api/auto/status');
      globalAuto = autoStatus.global_auto;
      if (modeEl) {
        modeEl.textContent = globalAuto ? 'AUTO' : 'MANUAL';
        modeEl.style.color = globalAuto ? '#22c55e' : '#94a3b8';
      }
    } catch(e) {
      if (modeEl) {
        modeEl.textContent = 'UNKNOWN';
        modeEl.style.color = '#94a3b8';
      }
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
        const health = await window.PollingManager.getHealth();
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
    setInterval(refresh, 15000); // Increased from 5s to 15s, uses cached health data
    // DEPRECATED: Keep for backward compatibility
    window.systemSetMode = setMode;
  }

  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
