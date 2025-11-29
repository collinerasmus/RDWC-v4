// global_health.js - lightweight multi-controller health dots updater
// Uses unified auto-enable system for consistent status display
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
  function classifySensorsFromStatus(status){
    if(!status) return {state:'bad', title:'No status'};
    const age = status.last_sample_ts ? (Date.now()/1000 - status.last_sample_ts) : Infinity;
    const running = !!status.running;
    
    // If age is > 5 minutes, page was idle - give it time to recover
    if(age > 300) {
      return {state:'warn', title:'Recovering from idle...'};
    }
    
    // Overview logic: online = running && age < 60. Age >=60 treated same as offline.
    if(!running) return {state:'offline', title:'Offline'};
    if(age >= 60) return {state:'offline', title:`Offline (stale ${Math.round(age)}s)`};
    return {state:'ok', title:`Fresh ${Math.round(age)}s`};
  }

  function classifyPh(ph, autoStatus){
    if(!ph) return {state:'bad', title:'No status'};
    if(ph.guards){
      const hardKeys = ['estop','reservoir'];
      const softKeys = ['safe_off','sensor_stale','interval','daily_cap','ec_baseline_low'];
      const hardActive = hardKeys.some(k => !!ph.guards[k]);
      const softActive = softKeys.some(k => !!ph.guards[k]);
      if(hardActive) return {state:'bad', title:'Hard guard active'};
      if(softActive) return {state:'warn', title:'Soft guard(s)'};
    }
    // Use unified auto-enable system
    const willAutomate = autoStatus && autoStatus.controllers && autoStatus.controllers.ph && autoStatus.controllers.ph.will_automate;
    if(willAutomate) return {state:'ok', title:'Auto'};
    return {state:'ok', title:'Manual'};
  }

  function classifyEc(ec, autoStatus){
    if(!ec) return {state:'bad', title:'No status'};
    if(ec.guards){
      const hardKeys = ['estop','reservoir'];
      const softKeys = ['sensor_stale','mix_lock','interval','daily_cap'];
      const hardActive = hardKeys.some(k => !!ec.guards[k]);
      const softActive = softKeys.some(k => !!ec.guards[k]);
      if(hardActive) return {state:'bad', title:'Hard guard active'};
      if(softActive) return {state:'warn', title:'Soft guard(s)'};
    }
    // Use unified auto-enable system
    const willAutomate = autoStatus && autoStatus.controllers && autoStatus.controllers.ec && autoStatus.controllers.ec.will_automate;
    if(willAutomate) return {state:'ok', title:'Auto'};
    return {state:'ok', title:'Manual'};
  }

  function classifyEnv(relays, chiller, autoStatus){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP'};
    if(chiller && chiller.error){ return {state:'warn', title:'Chiller error'}; }
    // Use unified auto-enable system
    const willAutomate = autoStatus && autoStatus.controllers && autoStatus.controllers.chiller && autoStatus.controllers.chiller.will_automate;
    return {state:'ok', title: willAutomate ? 'Auto' : 'Manual'};
  }

  function classifyLights(relays, autoStatus){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP'};
    const lights = relays.relays && relays.relays.lights;
    if(lights && lights.is_on) return {state:'ok', title:'On'};
    return {state:'ok', title:'Off'};
  }
  }

  function classifyCirc(relays, autoStatus){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP'};
    const mp = relays.relays && relays.relays.main_pump;
    const isOn = !!(mp && mp.is_on);
    // Use unified auto-enable system
    const willAutomate = autoStatus && autoStatus.controllers && autoStatus.controllers.circulation && autoStatus.controllers.circulation.will_automate;
    if(!willAutomate) return {state:'ok', title: isOn ? 'Main pump on' : 'Main pump off'};
    // In AUTO mode, warn only when expected to be on but isn't
    return isOn ? {state:'ok', title:'Main pump on'} : {state:'warn', title:'Main pump off'};
  }

  function classifySchedule(relays, autoStatus){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP'};
    // Use unified auto-enable system - schedule follows lights controller
    const willAutomate = autoStatus && autoStatus.controllers && autoStatus.controllers.lights && autoStatus.controllers.lights.will_automate;
    return {state:'ok', title: willAutomate ? 'Auto' : 'Manual'};
  }

  function classifySystem(relays, autoStatus){
    if(!relays) return {state:'bad', title:'No relays'};
    if(relays.estop) return {state:'bad', title:'E-STOP active'};
    // Use global_auto from unified auto-enable system
    const globalAuto = autoStatus && autoStatus.global_auto;
    return {state:'ok', title: globalAuto ? 'auto' : 'manual'};
  }

  async function poll(){
    try {
      // Use polling manager for deduplicated requests
      const fetchJSON = window.pollingManager?.fetchJSON || (url => fetch(url,{cache:'no-store'}).then(r=>r.ok?r.json():null));
      
      const [relays, sensorsStatus, ph, ec, chiller, autoStatus] = await Promise.all([
        fetchJSON('/api/relays/status').catch(()=>null),
        fetchJSON('/api/sensors/status').catch(()=>null),
        fetchJSON('/api/ph/status').catch(()=>null),
        fetchJSON('/api/ec/status').catch(()=>null),
        fetchJSON('/api/chiller/status').catch(()=>null),
        fetchJSON('/api/auto/status').catch(()=>null)
      ]);

      const sSensors = classifySensorsFromStatus(sensorsStatus);
      const sPh = classifyPh(ph, autoStatus);
      const sEc = classifyEc(ec, autoStatus);
      const sEnv = classifyEnv(relays, chiller, autoStatus);
      const sLights = classifyLights(relays, autoStatus);
      const sCirc = classifyCirc(relays, autoStatus);
      const sSchedule = classifySchedule(relays, autoStatus);
      const sSystem = classifySystem(relays, autoStatus);

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

  // Register with polling manager instead of own setInterval
  function start(){
    if (window.pollingManager) {
      // Use polling manager for coordinated updates
      window.pollingManager.register('global-health', poll, 'health');
    } else {
      // Fallback if polling manager not loaded yet
      console.warn('[global_health] Polling manager not found, using fallback');
      poll();
      setInterval(poll, POLL_MS);
    }
  }
  
  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
