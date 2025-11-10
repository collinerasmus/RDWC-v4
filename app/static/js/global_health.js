// global_health.js - lightweight multi-controller health dots updater
(function(){
  const POLL_MS = 6000; // align with existing 6s controller cadence
  let last = { ph:null, ec:null, sensors:null, env:null, lights:null, circ:null, schedule:null, system:null };
  let ready = false;

  function $(q){ return document.querySelector(q); }
  function all(sel){ return Array.from(document.querySelectorAll(sel)); }

  const prevStates = {};
  function setDot(controller, state, title){
    const dot = document.querySelector(`.ctrl-health-dot[data-controller="${controller}"]`);
    if(!dot) return;
    const prev = prevStates[controller];
    dot.className = `ctrl-health-dot ${state}` + (prev && prev!==state? ' changed':'');
    if(title){ dot.title = title; dot.setAttribute('aria-label', controller+': '+title); }
    if(prev && prev!==state){ setTimeout(()=>{ dot.classList.remove('changed'); }, 800); }
    prevStates[controller] = state;
  }

  // Sensors classification aligns visual state with true condition:
  // bad  => data object missing entirely (critical)
  // offline => poller not running / sensors.online false (distinct neutral-failure gray)
  // warn => stale cache (age exceeded freshness window)
  // ok   => fresh sample & online
  // Classify sensors using the same source as Overview: /api/sensors/status
  // running && age<60 => ok; running && age>=60 => warn; !running => offline; null => bad
  function classifySensorsFromStatus(status){
    if(!status) return {state:'bad', title:'No status'};
    const age = status.last_sample_ts ? (Date.now()/1000 - status.last_sample_ts) : Infinity;
    const running = !!status.running;
    // Overview logic: online = running && age < 60. Age >=60 treated same as offline.
    if(!running) return {state:'offline', title:'Offline'};
    if(age >= 60) return {state:'offline', title:`Offline (stale ${Math.round(age)}s)`};
    return {state:'ok', title:`Fresh ${Math.round(age)}s`};
  }

  function classifyPh(ph){
    if(!ph) return {state:'bad', title:'No status'};
    if(ph.guards){
      const hardKeys = ['estop','reservoir'];
      const softKeys = ['safe_off','sensor_stale','interval','daily_cap','ec_baseline_low'];
      const hardActive = hardKeys.some(k => !!ph.guards[k]);
      const softActive = softKeys.some(k => !!ph.guards[k]);
      if(hardActive) return {state:'bad', title:'Hard guard active'};
      if(softActive) return {state:'warn', title:'Soft guard(s)'};
    }
    if(ph.auto && ph.auto.enabled){ return {state:'ok', title:'Auto'}; }
    return {state:'ok', title:'Manual'};
  }

  function classifyEc(ec){
    if(!ec) return {state:'bad', title:'No status'};
    if(ec.guards){
      const hardKeys = ['estop','reservoir'];
      const softKeys = ['sensor_stale','mix_lock','interval','daily_cap'];
      const hardActive = hardKeys.some(k => !!ec.guards[k]);
      const softActive = softKeys.some(k => !!ec.guards[k]);
      if(hardActive) return {state:'bad', title:'Hard guard active'};
      if(softActive) return {state:'warn', title:'Soft guard(s)'};
    }
    if(ec.auto && ec.auto.enabled){ return {state:'ok', title:'Auto'}; }
    return {state:'ok', title:'Manual'};
  }

  function classifyEnv(relays, chiller){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP'};
    if(relays.mode === 'maintenance') return {state:'maint', title:'Maintenance'};
    if(chiller && chiller.error){ return {state:'warn', title:'Chiller error'}; }
    return {state:'ok', title: relays.mode==='manual'?'Manual':'Auto'};
  }

  function classifyLights(relays){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP'};
    if(relays.mode==='maintenance') return {state:'maint', title:'Maintenance'};
    const lights = relays.relays && relays.relays.lights;
    if(lights && lights.is_on) return {state:'ok', title:'On'};
    return {state:'ok', title:'Off'}; // off is normal
  }

  function classifyCirc(relays){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP'};
    const mp = relays.relays && relays.relays.main_pump;
    const isOn = !!(mp && mp.is_on);
    // In MANUAL mode, off is acceptable; warn only in AUTO when expected on
    if(relays.mode === 'manual') return {state:'ok', title: isOn ? 'Main pump on' : 'Main pump off'};
    return isOn ? {state:'ok', title:'Main pump on'} : {state:'warn', title:'Main pump off'};
  }

  function classifySchedule(relays){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP'};
    if(relays.mode==='maintenance') return {state:'maint', title:'Maintenance'};
    return {state:'ok', title: relays.mode==='manual'?'Manual':'Auto'};
  }

  function classifySystem(relays){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP active'};
    return {state:'ok', title: relays.mode};
  }

  async function poll(){
    try {
  const relaysP = fetch('/api/relays/status',{cache:'no-store'}).then(r=>r.ok?r.json():null);
  const sensorsStatusP = fetch('/api/sensors/status',{cache:'no-store'}).then(r=>r.ok?r.json():null);
      const phP = fetch('/api/ph/status',{cache:'no-store'}).then(r=>r.ok?r.json():null);
      const ecP = fetch('/api/ec/status',{cache:'no-store'}).then(r=>r.ok?r.json():null);
      const chillerP = fetch('/api/chiller/status',{cache:'no-store'}).then(r=>r.ok?r.json():null);
  const [relays, sensorsStatus, ph, ec, chiller] = await Promise.all([relaysP,sensorsStatusP,phP,ecP,chillerP]);

  const sSensors = classifySensorsFromStatus(sensorsStatus);
      const sPh = classifyPh(ph);
      const sEc = classifyEc(ec);
      const sEnv = classifyEnv(relays, chiller);
      const sLights = classifyLights(relays);
      const sCirc = classifyCirc(relays);
      const sSchedule = classifySchedule(relays);
      const sSystem = classifySystem(relays);

      setDot('sensors', sSensors.state, sSensors.title);
      setDot('ph', sPh.state, sPh.title);
      setDot('ec', sEc.state, sEc.title);
      setDot('temp', sEnv.state, sEnv.title);
      setDot('lights', sLights.state, sLights.title);
      setDot('circulation', sCirc.state, sCirc.title);
      setDot('schedule', sSchedule.state, sSchedule.title);
      setDot('settings', sSystem.state, sSystem.title);
      // Overview dot summarises worst state severity excluding maintenance using unified precedence
      // Precedence: bad > offline > warn > ok
      const states = [sSensors.state,sPh.state,sEc.state,sEnv.state,sLights.state,sCirc.state,sSchedule.state,sSystem.state]
        .filter(x=>x!=='maint');
      let overviewState = 'ok';
      if(states.includes('bad')) overviewState='bad';
      else if(states.includes('offline')) overviewState='offline';
      else if(states.includes('warn')) overviewState='warn';
      setDot('overview', overviewState, 'Summary');

      ready = true;
    } catch (e){
      console.warn('[global_health] poll error', e);
      // fallback: mark overview/system bad
      setDot('overview','bad','Health poll error');
      setDot('settings','bad','Health poll error');
    }
  }

  function start(){ poll(); setInterval(poll, POLL_MS); }
  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
