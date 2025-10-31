/* Sensors real-time display with color thresholds and calibration status */
(function(){
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
  
  async function tick(){
    try{
      const r = await fetch("/api/sensors", {cache:"no-store"});
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
    }catch(err){
      console.error("[Sensors] Fetch error:", err);
      setOnline(false);
    }
  }
  
  document.addEventListener("DOMContentLoaded", ()=>{
    console.log("[Sensors] Initializing real-time updates");
    tick(); // Initial fetch
    setInterval(tick, 2000); // Update every 2s
  });
})();
