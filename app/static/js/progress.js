// Progress/Heartbeat widget logic
(function(){
  const $ = (id)=>document.getElementById(id);
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));

  // Task checklist with weights (sum to 100)
  // Computed via live endpoint health and mode standardization flags
  const tasks = [
    {key:'system', label:'System mode OK', w:15, ok:false},
    {key:'sensors', label:'Sensors live', w:20, ok:false},
    {key:'ph', label:'pH controller healthy', w:15, ok:false},
    {key:'ec', label:'EC controller healthy', w:15, ok:false},
    {key:'schedule', label:'Schedule ready', w:10, ok:false},
    {key:'env', label:'Environment ok', w:10, ok:false},
    {key:'lights', label:'Lights ok', w:10, ok:false},
    {key:'tests', label:'Local tests pass', w:5, ok:false},
  ];

  let lastBeatTs = 0; // ms
  let etaMinutes = null; // computed based on remaining items * average per-item time
  let bootstrap = true;

  function setProgress(p){
    const bar = $('progress-bar');
    const label = $('progress-label');
    if (!bar || !label) return;
    bar.style.width = clamp(p,0,100)+'%';
    const pctTxt = Math.round(clamp(p,0,100))+'% complete';
    label.textContent = pctTxt;
    // Mirror into header summary if present
    const hdr = document.getElementById('hdr-progress');
    if (hdr) hdr.textContent = pctTxt.replace(' complete','');
  }

  function setHeartbeat(ok){
    const dot = $('progress-heartbeat');
    const hbLabel = $('progress-heartbeat-label');
    const etaLabel = $('progress-eta-label');
    if (!dot || !hbLabel || !etaLabel) return;
    if (ok){ dot.style.background = '#22c55e'; dot.classList.add('pulse'); }
    else { dot.style.background = '#ef4444'; dot.classList.remove('pulse'); }
    const ago = lastBeatTs? Math.max(0, Math.round((Date.now()-lastBeatTs)/1000)) : null;
    hbLabel.textContent = ago!=null? `heartbeat ${ago}s ago` : 'heartbeat —';
    etaLabel.textContent = etaMinutes!=null? `${etaMinutes}m remaining` : '—';
    etaLabel.className = 'chip-mini ' + ((etaMinutes!=null && etaMinutes<5)?'ok':'');
    // Mirror into header banner if present
    const hdrHb = document.getElementById('hdr-hb');
    if (hdrHb) hdrHb.textContent = ago!=null? `HB: ${ago}s` : 'HB: —';
    const hdrEta = document.getElementById('hdr-eta');
    if (hdrEta) hdrEta.textContent = etaMinutes!=null? `ETA: ${etaMinutes}m` : 'ETA: —';
  }

  function renderComponentChips(){
    const wrap = $('progress-components');
    if(!wrap) return;
    wrap.innerHTML = tasks.map(t=>{
      return `<span class="chip-mini ${t.ok?'ok':'bad'}" title="${t.label}">${t.key}</span>`;
    }).join('');
  }

  function computePercent(){
    return tasks.reduce((acc,t)=> acc + (t.ok? t.w:0), 0);
  }

  async function pollHealth(){
    try {
      // Prefer server-side snapshot if available
      const snap = await fetch('/api/progress', {cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);
      if (snap && typeof snap.percent==='number' && snap.components){
        // Adopt server snapshot
        tasks.forEach(t=>{ t.ok = !!snap.components[t.key]; });
        lastBeatTs = Date.now() - ((snap.heartbeat_age_s||0)*1000);
        etaMinutes = (typeof snap.eta_minutes==='number')? snap.eta_minutes : null;
        const pct = clamp(snap.percent,0,100);
        setProgress(pct);
        renderComponentChips();
        setHeartbeat(true);
        return;
      }
      // System/Relays
      const sys = await fetch('/api/relays/status', {cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);
      tasks.find(t=>t.key==='system').ok = !!(sys && sys.mode && sys.estop===false);

      // Sensors - use PollingManager cache
      const sensors = await window.PollingManager.getSensors().catch(()=>null);
      tasks.find(t=>t.key==='sensors').ok = !!(sensors && sensors.online===true && sensors.ts);

      // pH status
      const ph = await fetch('/api/ph/status', {cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);
      const phHard = !!(ph && (ph.guards?.estop || ph.guards?.sensor_stale || ph.guards?.reservoir));
      tasks.find(t=>t.key==='ph').ok = !!(ph && !phHard);

      // EC status
      const ec = await fetch('/api/ec/status', {cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);
      const ecHard = !!(ec && (ec.guards?.estop || ec.guards?.sensor_stale || ec.guards?.reservoir));
      tasks.find(t=>t.key==='ec').ok = !!(ec && !ecHard);

      // Schedule readiness (presence of plan or weeks)
      const sched = await fetch('/api/nutrient_schedule', {cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);
      tasks.find(t=>t.key==='schedule').ok = !!(sched && Array.isArray(sched.weeks) && sched.weeks.length>0);

      // Environment via chiller status
      const env = await fetch('/api/temperature/status', {cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);
      tasks.find(t=>t.key==='env').ok = !!env; // basic availability

      // Lights via relays wrap
      const lightsOk = !!(sys && sys.relays && typeof sys.relays.lights==='boolean');
      tasks.find(t=>t.key==='lights').ok = lightsOk;

      // Tests pass flag is updated externally by an injected hook (optional)
      // Leave as-is unless window.PROGRESS_TESTS_PASS is set
      if (typeof window.PROGRESS_TESTS_PASS==='boolean'){
        tasks.find(t=>t.key==='tests').ok = window.PROGRESS_TESTS_PASS;
      }

      lastBeatTs = Date.now();
  const pct = computePercent();
  setProgress(pct);
  renderComponentChips();
      // Simple ETA: assume ~2 minutes per remaining block during bootstrap; shorten as we progress
      const remainW = 100 - pct;
      if (bootstrap){ etaMinutes = Math.ceil(remainW / 10 * 2); } else { etaMinutes = Math.ceil(remainW / 20); }
      setHeartbeat(true);
    } catch(e){
      setHeartbeat(false);
    }
  }

  function init(){
    // Start polling heartbeat every 10s
  pollHealth();
    setInterval(pollHealth, 10000);
    // After first minute, reduce ETA pessimism
    setTimeout(()=>{ bootstrap=false; }, 60000);
  }

  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
