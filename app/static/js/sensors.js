/* Sensors real-time display with color thresholds and calibration status */
(function(){
  // Respect existing inline poller guard if present
  if (window.__RDWC_SENSORS_POLL_RUNNING__) {
    console.log("[Sensors.js] Another sensors poller active; skipping.");
    return;
  }
  const $ = (id)=>document.getElementById(id);
  
  const setMetric = (el, val, classes) => {
    if (!el) return;
    el.textContent = (val===null || Number.isNaN(val)) ? "--" : String(val.toFixed ? val.toFixed(2) : val);
    el.classList.remove("good","warn","bad");
    el.classList.add(classes);
  };
  
  const classify = (name, v) => {
    if (v===null || Number.isNaN(v)) return "bad";
    if (name==="temp") {
      if (v>=18 && v<=24) return "good";
      if ((v>24 && v<=28) || (v>=16 && v<18)) return "warn";
      return "bad";
    }
    if (name==="ec") {
      if (v>=1.2 && v<=2.0) return "good";
      if ((v>=0.8 && v<1.2) || (v>2.0 && v<=2.4)) return "warn";
      return "bad";
    }
    if (name==="ph") {
      if (v>=5.5 && v<=6.2) return "good";
      if ((v>=5.2 && v<5.5) || (v>6.2 && v<=6.5)) return "warn";
      return "bad";
    }
    return "bad";
  };
  
  const setBadge = (el, ok, detail) => {
    if (!el) return;
    el.textContent = ok ? "OK" : "Check";
    el.classList.remove("ok","check");
    el.classList.add(ok ? "ok" : "check");
    if (detail) el.title = detail;
  };
  
  const setOnline = (ok) => {
    const el = $("sensors-online");
    if (!el) return;
    el.textContent = ok ? "online" : "offline";
    el.classList.remove("online","offline");
    el.classList.add(ok ? "online" : "offline");
  };

  async function fetchHealthDB(){
    try{
      const r = await fetch('/health/db', {cache:'no-store'});
      if(!r.ok) return null;
      return await r.json();
    }catch(e){ return null; }
  }
  
  function renderHealthBadge(h){
    const el = $("sensors-health-badge");
    if (!el) return;
    const age = h?.cache_age_s ?? null;
    const dbAge = h?.db_age_s ?? null;
    let text = "OK", style = {bg:"rgba(34,197,94,0.12)", bd:"rgba(34,197,94,0.4)", fg:"#86efac"};
    if (!h?.cache_has_data) {
      text = (typeof dbAge === 'number') ? `Offline (DB ${Math.round(dbAge)}s)` : "Offline";
      style = {bg:"rgba(239,68,68,0.12)", bd:"rgba(239,68,68,0.4)", fg:"#fecaca"};
    } else if (!h?.cache_fresh) {
      text = `Stale ${Math.round(age)}s`;
      style = {bg:"rgba(234,179,8,0.12)", bd:"rgba(234,179,8,0.4)", fg:"#fde68a"};
    }
    el.textContent = text;
    el.style.background = style.bg;
    el.style.border = `1px solid ${style.bd}`;
    el.style.color = style.fg;
    el.title = `Cache age: ${age ?? 'n/a'}s` + (dbAge!=null? `, DB age: ${dbAge}s` : "");
  }
  
  async function tick(){
    try{
  const r = await fetch("/api/sensors/last", {cache:"no-store"});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      
      const t = j.temperature_c ?? null;
      const e = j.ec_mscm ?? null;
      const p = j.ph ?? null;
      
      setMetric($("val-temp"), t, classify("temp", t));
      setMetric($("val-ec"),   e, classify("ec", e));
      setMetric($("val-ph"),   p, classify("ph", p));
      
      setBadge($("cal-badge-temp"), j.cal?.temp?.is_calibrated === true, j.cal?.temp?.detail || "");
      setBadge($("cal-badge-ec"),   j.cal?.ec?.is_calibrated === true,   j.cal?.ec?.detail || "");
      setBadge($("cal-badge-ph"),   j.cal?.ph?.is_calibrated === true,   j.cal?.ph?.detail || "");
      
      setOnline(!!j.online);
      
      const updated = $("sensors-updated");
      if (updated) {
        if (j.ts) {
          const d = new Date(j.ts);
          updated.textContent = d.toLocaleTimeString();
        } else {
          updated.textContent = new Date().toLocaleTimeString();
        }
      }
      // Fetch sensor cache health and DB health in parallel (non-blocking)
      fetch('/api/sensors/health', {cache:'no-store'})
        .then(r=>r.ok?r.json():null)
        .then(h=>h && renderHealthBadge(h))
        .catch(()=>{});

      fetchHealthDB().then(health=>{
        const dot = $("sensorsFreshnessDot");
        const rateEl = $("samplesRate");
        if (health && dot){
          const age = Number(health.age_seconds||0);
          const rows5 = Number(health.recent_rows_5min||0);
          const rate = rows5/5;
          if (age < 180){ dot.style.background = '#22c55e'; }
          else if (age < 600){ dot.style.background = '#f59e0b'; }
          else { dot.style.background = '#ef4444'; }
          dot.title = `DB age: ${Math.round(age)}s, last 5m rows: ${rows5}`;
          if (rateEl){ rateEl.textContent = `${rate.toFixed(1)} samples/min`; rateEl.title = `${rows5} rows in last 5 minutes`; }
        }
      }).catch(()=>{});
    }catch(err){
      console.error("[Sensors] Fetch error:", err);
      setOnline(false);
    }
  }
  
  document.addEventListener("DOMContentLoaded", ()=>{
    console.log("[Sensors] Initializing real-time updates");
    tick(); // Initial fetch
    // Respect configurable poll interval (default 5000ms)
    const poll = (window.APP_POLL && window.APP_POLL.sensors) ? (parseInt(window.APP_POLL.sensors,10)||5000) : 5000;
    setInterval(tick, Math.max(1500, poll));
    // Sensors health popover interactions
    const badge = $("sensors-health-badge");
    const pop = $("sensors-health-popover");
    if (badge && pop) {
      const fmtAgo = (ts)=>{
        if (!ts) return "n/a";
        const now = Date.now()/1000;
        const age = Math.max(0, Math.round(now - ts));
        if (age < 60) return `${age}s ago`;
        const m = Math.floor(age/60);
        if (m < 60) return `${m}m ago`;
        const h = Math.floor(m/60);
        return `${h}h ${m%60}m ago`;
      };
      const buildHtml = (h)=>{
        const d = h?.diag || {};
        const cacheAge = (h?.cache_age_s!=null)? `${Math.round(h.cache_age_s)}s` : 'n/a';
        const dbAge = (h?.db_age_s!=null)? `${Math.round(h.db_age_s)}s` : 'n/a';
        const dbTsAgo = (h?.db_ts!=null)? fmtAgo(h.db_ts) : 'n/a';
        const lwAgo = d?.last_watchdog_ts ? fmtAgo(d.last_watchdog_ts) : 'never';
        const leAgo = d?.last_error_ts ? fmtAgo(d.last_error_ts) : 'n/a';
        const lastErr = (d?.last_error || '').toString().slice(0,160);
        const fresh = h?.cache_fresh ? 'yes' : 'no';
        return `
          <div style="font-weight:600;margin-bottom:6px;">Sensors Health</div>
          <div style="display:grid;grid-template-columns: 140px 1fr;gap:6px 10px;align-items:center;">
            <div class="muted">Cache Fresh</div><div>${fresh}</div>
            <div class="muted">Cache Age</div><div>${cacheAge}</div>
            <div class="muted">DB Age</div><div>${dbAge}</div>
            <div class="muted">DB Last</div><div>${dbTsAgo}</div>
            <div class="muted">Watchdog Restarts</div><div>${d?.restarts ?? 0}</div>
            <div class="muted">Last Watchdog</div><div>${lwAgo}</div>
            <div class="muted">Last Error</div><div style="max-width:260px;white-space:pre-wrap;word-break:break-word;">${lastErr || '—'}</div>
            <div class="muted">Last Error Time</div><div>${leAgo}</div>
          </div>
        `;
      };
      const place = (anchor)=>{
        const r = anchor.getBoundingClientRect();
        const top = window.scrollY + r.bottom + 8;
        const left = window.scrollX + Math.min(r.left, window.innerWidth - 320);
        pop.style.top = `${top}px`;
        pop.style.left = `${left}px`;
      };
      const hide = ()=>{ pop.style.display = 'none'; };
      const show = ()=>{ pop.style.display = 'block'; };
      let open = false;
      badge.addEventListener('click', async (ev)=>{
        ev.stopPropagation();
        try{
          const r = await fetch('/api/sensors/health', {cache:'no-store'});
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          const h = await r.json();
          pop.innerHTML = buildHtml(h);
          place(badge);
          show();
          open = true;
        }catch(e){
          console.warn('[Sensors] popover fetch failed', e);
        }
      });
      document.addEventListener('click', (ev)=>{
        if (!open) return;
        if (ev.target === badge || pop.contains(ev.target)) return;
        hide();
        open = false;
      });
      document.addEventListener('keydown', (ev)=>{
        if (!open) return;
        if (ev.key === 'Escape') { hide(); open = false; }
      });
      window.addEventListener('resize', ()=>{ if (open) place(badge); });
      window.addEventListener('scroll', ()=>{ if (open) place(badge); }, {passive:true});
    }
  });
})();
