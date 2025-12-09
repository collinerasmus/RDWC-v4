(function(){
  const $ = (id)=>document.getElementById(id);
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };
  const postJSON = async (u,b)=>{ const r = await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json().catch(()=>({})); };
  const getRelays = async (opts={})=>{
    if (window.pollingManager && window.pollingManager.getRelays) {
      return window.pollingManager.getRelays(opts);
    }
    return getJSON('/api/relays/status');
  };

  let lastRelays = null;
  let lightsIsOn = false;

  function updateWindowPreview(win){
    const el = $('lights-window-kpi');
    if (!el) return;
    if (win && !win.error && win.on_time && win.off_time){ el.textContent = `${win.on_time} → ${win.off_time}`; }
    else { el.textContent = '—'; }
  }

  function updateKpis(modeVal){
    const state = $('lights-state-kpi');
    const sched = $('lights-sched-kpi');
    if (state) state.textContent = lightsIsOn ? 'ON' : 'OFF';
    if (sched){
      // Basic hint based on mode and current state
      if (modeVal==='auto') sched.textContent = 'Following schedule';
      else if (modeVal==='maintenance') sched.textContent = 'Maintenance';
      else sched.textContent = 'Manual control';
    }
  }

  function updateHealth(){
    const ind = $('lights-health-indicator');
    if(!ind) return;
    const estop = !!(lastRelays && lastRelays.estop);
    if (estop){ ind.textContent='BLOCKED'; ind.className='ui-status-chip error'; ind.title='E-STOP active'; return; }
    // Cooldown/anti-flap -> WAITING
    const info = (lastRelays && lastRelays.relays && lastRelays.relays.lights) ? lastRelays.relays.lights : {};
    const cd = info.cooldown_remaining || info.cooldown || 0;
    if (cd && cd > 0){ ind.textContent='WAITING'; ind.className='ui-status-chip warning'; ind.title=`Cooldown ${Math.ceil(cd)}s`; return; }
    ind.textContent = 'AUTO'; ind.className = 'ui-status-chip success'; ind.title = 'Automation running';
  }

  async function refresh(opts={}){
    try{
      const wrap = await getRelays({ force: opts.force }).catch(e => ({ error: e.message }));
      lastRelays = wrap || {};
      const rel = (wrap && wrap.relays) ? wrap.relays : {};
      const info = rel.lights || {};
      lightsIsOn = !!info.is_on;
      const badge = $('lights-status');
      const label = $('lights-label');
      const btn = $('btnLightsToggle');
      if (badge){ badge.textContent = lightsIsOn? 'ON':'OFF'; badge.className = 'bop-status-badge '+(lightsIsOn?'on':'off'); }
      if (label){ label.textContent = (lightsIsOn? '\u25cf ':'\u25cb ') + 'Lights'; }
      // Determine current system mode (prefer relays response; fallback to global system mode)
      const mode = (wrap && wrap.mode) || window.__systemMode || 'manual';
      if (btn){
        const disabled = (mode==='auto' && !localStorage.getItem('safety.allow_force')) || !!wrap.estop;
        btn.className = 'relay-btn ' + (lightsIsOn? 'relay-on':'relay-off');
        btn.disabled = disabled;
        btn.style.opacity = disabled ? '0.6':'1';
        btn.style.cursor = disabled ? 'not-allowed':'pointer';
      }
      // settings window preview - use PollingManager cache
      try{
        const s = await window.PollingManager.getSettings();
        if (s && s.error) {
          updateWindowPreview(null);
        } else {
          updateWindowPreview(s.today_window);
        }
      }catch(e){
        updateWindowPreview(null);
        console.warn('[LightsV2] Failed to fetch settings:', e);
      }
      updateKpis((wrap && wrap.mode) || window.__systemMode || 'manual');
      updateHealth();
    }catch(e){
      updateWindowPreview(null);
      console.warn('[LightsV2] refresh failed', e);
    }
  }

  async function toggle(){
    try{
      await postJSON('/api/relay/lights/toggle', {});
    }catch(e){
      try{
        const wrap = await getJSON('/api/relays/status');
        const cur = !!(wrap && wrap.relays && wrap.relays.lights && wrap.relays.lights.is_on);
        await postJSON('/relay/set', {name:'lights', on: !cur});
      }catch(e2){ console.warn('[LightsV2] toggle failed', e2); }
    }finally{
      if (window.pollingManager && window.pollingManager.invalidate) {
        window.pollingManager.invalidate('relays');
      }
      setTimeout(()=>refresh({ force:true }), 300);
    }
  }

  async function init(){
    $('btnLightsToggle')?.addEventListener('click', ()=> toggle());
    refresh();
    setInterval(refresh, 30000); // Increased from 4s to 30s
  }

  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
