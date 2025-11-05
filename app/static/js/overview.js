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
      // Sensor poller status badge
      try{
        const ps = await getJSON('/api/sensors/status');
        const pollerEl = q('#ov-sensor-poller');
        if (pollerEl && ps) {
          const age = ps.last_sample_ts ? (Date.now()/1000 - ps.last_sample_ts) : 999;
          const online = ps.running || age < 30;
          const dot = online ? '🟢' : '🔴';
          const ageStr = age < 60 ? `${Math.round(age)}s` : age < 3600 ? `${Math.round(age/60)}m` : `${Math.round(age/3600)}h`;
          pollerEl.textContent = `Sensors: ${dot} ${online?'Online':'Offline'}`;
          pollerEl.title = `Headless poller • Last sample: ${ageStr} ago • Polls: ${ps.poll_count || 0}`;
          pollerEl.style.borderColor = online ? 'rgba(34,197,94,0.5)' : 'rgba(239,68,68,0.5)';
          pollerEl.style.background = online ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)';
          pollerEl.style.color = online ? '#a7f3d0' : '#fca5a5';
        }
      }catch(e){ console.warn('[Overview] sensor poller status unavailable', e); }
    }catch(e){ console.warn('[Overview] refresh failed', e); }
  }
  function init(){ refresh(); setInterval(refresh, 3000); }
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
