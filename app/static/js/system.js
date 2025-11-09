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
    const ind = $('system-health-indicator');
    if (!ind) return;
    const estop = !!(lastWrap && lastWrap.estop);
    if (mode==='maintenance'){
      ind.textContent = 'MAINT'; ind.className = 'ui-status-chip warning'; ind.title='Maintenance mode: safeties bypassed';
    } else if (estop){
      ind.textContent = 'BLOCKED'; ind.className = 'ui-status-chip error'; ind.title='E-STOP active';
    } else if (mode==='auto'){
      ind.textContent = 'OK'; ind.className = 'ui-status-chip success'; ind.title='System automation';
    } else {
      ind.textContent = 'OK'; ind.className = 'ui-status-chip success'; ind.title='Manual control with safeties';
    }
  }

  async function refresh(){
    try{
      const wrap = await getJSON('/api/relays/status');
      lastWrap = wrap;
      updateHealth();
    }catch(e){}
  }

  function init(){
    setMode(mode);
    refresh();
    setInterval(refresh, 5000);
    window.systemSetMode = setMode;
  }

  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
