(function(){
  const $ = (id)=>document.getElementById(id);
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };
  const postJSON = async (u,b)=>{ const r = await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json().catch(()=>({})); };

  let isHeld = false;
  let lastRelays = null;
  let lightsIsOn = false;

  async function lightsToggleHold() {
    try {
      const resp = await postJSON('/api/controller/lights/hold', {});
      if (resp.ok) {
        isHeld = resp.held;
        updateLightsHoldButton();
        updateHealth();
      }
    } catch (e) {
      console.error('Failed to toggle hold:', e);
    }
  }

  function updateLightsHoldButton() {
    const btn = $('lights-hold-btn');
    if (!btn) return;
    if (isHeld) {
      btn.classList.add('active', 'warning');
      btn.textContent = 'Resume';
      btn.title = 'Resume automation';
    } else {
      btn.classList.remove('active', 'warning');
      btn.textContent = 'Hold';
      btn.title = 'Pause automation';
    }
  }

  async function syncLightsHoldState() {
    try {
      const resp = await getJSON('/api/controller/lights/mode');
      if (resp.ok && resp.mode) {
        isHeld = (resp.mode === 'hold');
        updateLightsHoldButton();
      }
    } catch (e) {
      // Silent fail
    }
  }

  function updateWindowPreview(win){
    const el = $('lights-window-preview');
    if (!el) return;
    if (win && !win.error && win.on_time && win.off_time){ el.textContent = `Window: ${win.on_time} → ${win.off_time}`; }
    else { el.textContent = 'Window: —'; }
  }

  function updateKpis(){
    const state = $('lights-state-kpi');
    const sched = $('lights-sched-kpi');
    if (state) state.textContent = lightsIsOn ? 'ON' : 'OFF';
    if (sched){
      // Basic hint based on mode and current state
      if (mode==='auto') sched.textContent = 'Following schedule';
      else if (mode==='maintenance') sched.textContent = 'Maintenance';
      else sched.textContent = 'Manual control';
    }
  }

  function updateHealth(){
    const ind = $('lights-health-indicator');
    if(!ind) return;
    const estop = !!(lastRelays && lastRelays.estop);
    if (estop){ ind.textContent='BLOCKED'; ind.className='ui-status-chip error'; ind.title='E-STOP active'; return; }
    if (isHeld){ ind.textContent='HELD'; ind.className='ui-status-chip warning'; ind.title='Automation paused by Hold button'; return; }
    // Cooldown/anti-flap -> WAITING
    const info = (lastRelays && lastRelays.relays && lastRelays.relays.lights) ? lastRelays.relays.lights : {};
    const cd = info.cooldown_remaining || info.cooldown || 0;
    if (cd && cd > 0){ ind.textContent='WAITING'; ind.className='ui-status-chip warning'; ind.title=`Cooldown ${Math.ceil(cd)}s`; return; }
    ind.textContent = 'AUTO'; ind.className = 'ui-status-chip success'; ind.title = 'Automation running';
  }

  async function refresh(){
    try{
      const wrap = await getJSON('/api/relays/status');
      lastRelays = wrap || {};
      const rel = (wrap && wrap.relays) ? wrap.relays : {};
      const info = rel.lights || {};
      lightsIsOn = !!info.is_on;
      const badge = $('lights-status');
      const label = $('lights-label');
      const btn = $('btnLightsToggle');
      if (badge){ badge.textContent = lightsIsOn? 'ON':'OFF'; badge.className = 'bop-status-badge '+(lightsIsOn?'on':'off'); }
      if (label){ label.textContent = (lightsIsOn? '● ':'○ ') + 'Lights'; }
      if (btn){
        const disabled = (mode==='auto' && !localStorage.getItem('safety.allow_force')) || !!wrap.estop;
        btn.className = 'relay-btn ' + (lightsIsOn? 'relay-on':'relay-off');
        btn.disabled = disabled;
        btn.style.opacity = disabled ? '0.6':'1';
        btn.style.cursor = disabled ? 'not-allowed':'pointer';
      }
      // settings window preview
      try{
        const s = await (await fetch('/settings?'+Date.now(), {cache:'no-store'})).json();
        updateWindowPreview(s.today_window);
      }catch(e){}
      updateKpis();
      updateHealth();
    }catch(e){ console.warn('[LightsV2] refresh failed', e); }
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
    }finally{ setTimeout(refresh, 300); }
  }

  async function init(){
    // Sync hold state from backend first
    await syncLightsHoldState();
    
    $('btnLightsToggle')?.addEventListener('click', ()=> toggle());
    refresh();
    setInterval(refresh, 4000);
    // expose for inline onclicks
    window.lightsToggleHold = lightsToggleHold;
  }

  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
