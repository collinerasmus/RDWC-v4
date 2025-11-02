(function(){
  const q = (s)=>document.querySelector(s);
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };
  const postJSON = async (u,b)=>{ const r = await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json().catch(()=>({})); };

  async function refresh(){
    try{
      const wrap = await getJSON('/api/relays/status');
      const st = wrap && wrap.relays ? wrap.relays : {};
      const info = st['lights'] || {};
      const on = !!info.is_on;
      const badge = q('#lights-status');
      const label = q('#lights-label');
      const btn = q('#btnLightsToggle');
      if (badge){
        badge.textContent = on? 'ON':'OFF';
        badge.className = 'bop-status-badge '+(on?'on':'off');
      }
      if (label){ label.textContent = (on? '● ':'○ ') + 'Lights'; }
      if (btn){
        btn.className = 'relay-btn ' + (on? 'relay-on':'relay-off');
        btn.disabled = wrap.mode==='auto' || wrap.estop===true;
        btn.style.opacity = btn.disabled ? '0.6':'1';
        btn.style.cursor = btn.disabled ? 'not-allowed':'pointer';
      }
      // schedule preview
      try{
        const s = await (await fetch('/settings?'+Date.now(),{cache:'no-store'})).json();
        const w = s.today_window;
        q('#lights-window-preview').textContent = (w && !w.error) ? `Window: ${w.on_time} → ${w.off_time}` : '—';
      }catch(e){}
    }catch(e){ console.warn('[Lights] refresh failed', e); }
  }
  async function toggle(){
    try{
      // Use new wrapper endpoint
      await postJSON('/api/relay/lights/toggle',{ on: null /* toggle on server */});
    }catch(e){
      // Fallback to legacy: need current state to invert
      try{
        const wrap = await getJSON('/api/relays/status');
        const cur = wrap && wrap.relays && wrap.relays.lights ? !!wrap.relays.lights.is_on : false;
        await postJSON('/relay/set', { name:'lights', on: !cur });
      }catch(e2){ console.warn('[Lights] toggle failed', e2); }
    }finally{
      setTimeout(refresh, 300);
    }
  }
  function init(){
    const btn = q('#btnLightsToggle');
    if (btn){ btn.addEventListener('click', ()=>{ toggle().catch(()=>{}); }); }
    refresh();
    setInterval(refresh, 3000);
    window.LightsControl = { refresh };
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
