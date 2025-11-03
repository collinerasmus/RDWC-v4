(function(){
  const q = (s)=>document.querySelector(s);
  const getJSON = async (u)=>{ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); };
  function setBadge(id, on){ const el = q(id); if (!el) return; el.textContent = on?'ON':'OFF'; el.className = 'bop-status-badge '+(on?'on':'off'); }
  async function refresh(){
    try{
      const wrap = await getJSON('/api/relays/status');
      const rel = wrap.relays || {};
      setBadge('#ov-lights', !!(rel.lights && rel.lights.is_on));
      setBadge('#ov-main-pump', !!(rel.main_pump && rel.main_pump.is_on));
      setBadge('#ov-chiller-pump', !!(rel.chiller_pump && rel.chiller_pump.is_on));
      setBadge('#ov-chiller', !!(rel.chiller_power && rel.chiller_power.is_on));
      const mode = wrap.mode || 'manual';
      const estop = !!wrap.estop;
      const modeEl = q('#ov-mode'); const estopEl = q('#ov-estop');
      if (modeEl) modeEl.textContent = 'Mode: ' + mode.toUpperCase();
      if (estopEl) estopEl.textContent = 'E-STOP: ' + (estop?'ACTIVE':'off');
      try{
        const s = await (await fetch('/settings?'+Date.now(),{cache:'no-store'})).json();
        const w = s.today_window; if (w && !w.error) q('#ov-lights-window').textContent = `Lights Window: ${w.on_time} → ${w.off_time}`;
      }catch(e){}
    }catch(e){ console.warn('[Overview] refresh failed', e); }
  }
  function init(){ refresh(); setInterval(refresh, 3000); }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
