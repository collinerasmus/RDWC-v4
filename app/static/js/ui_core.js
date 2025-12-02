/**
 * UI Core - Initialization and utility functions
 * Extracted from inline scripts in index.html
 */

// Lightweight UI demo flag: enable with ?demo=1 or localStorage.ui_demo='1'
(function(){
  try{
    const params = new URLSearchParams(window.location.search);
    const q = params.get('demo');
    if (q === '1' || q === 'true') localStorage.setItem('ui_demo','1');
    if (q === '0' || q === 'false') localStorage.removeItem('ui_demo');
    window.UI_DEMO = localStorage.getItem('ui_demo') === '1';
  }catch(_){ window.UI_DEMO = false; }
})();

// Initialize header auto button: wire click handlers and sync with API
(function(){
  function updateAutoStatus(){
    fetch('/api/auto/status', {cache:'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(data){
        // Update global auto button
        var btn = document.getElementById('global-auto-btn');
        var state = document.getElementById('global-auto-state');
        if (btn && state) {
          var isOn = data.global_auto;
          state.textContent = isOn ? 'ON' : 'OFF';
          btn.classList.toggle('active', isOn);
          btn.style.background = isOn ? 'rgba(34,197,94,0.15)' : 'rgba(148,163,184,0.12)';
          btn.style.borderColor = isOn ? 'rgba(34,197,94,0.45)' : 'rgba(148,163,184,0.3)';
        }
        
        // Update per-controller status chips - all 5 controllers
        var controllers = data.controllers || {};
        ['ph', 'ec', 'chiller', 'circulation', 'lights'].forEach(function(ctrl){
          var chip = document.getElementById('ctrl-' + ctrl + '-chip');
          if (chip) {
            var info = controllers[ctrl] || {};
            var willAuto = info.will_automate;
            var chipSpan = chip.querySelector('span');
            if (chipSpan) {
              chipSpan.textContent = willAuto ? 'AUTO' : 'OFF';
            }
            chip.style.background = willAuto ? 'rgba(34,197,94,0.1)' : 'rgba(148,163,184,0.08)';
            chip.style.borderColor = willAuto ? 'rgba(34,197,94,0.35)' : 'rgba(148,163,184,0.25)';
          }
        });
      })
      .catch(function(err){
        console.warn('[Header Auto] Failed to fetch auto status:', err);
      });
  }
  
  function toggleGlobalAuto(){
    fetch('/api/auto/status', {cache:'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(data){
        var newState = !data.global_auto;
        return fetch('/api/auto/global', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({enabled: newState})
        });
      })
      .then(function(){ updateAutoStatus(); })
      .catch(function(err){
        console.error('[Header Auto] Failed to toggle:', err);
      });
  }
  
  function initHeaderAutoButton(){
    var btn = document.getElementById('global-auto-btn');
    if (btn) {
      btn.addEventListener('click', toggleGlobalAuto);
    }
    updateAutoStatus();
    // Poll status every 2 seconds for responsive UI
    setInterval(updateAutoStatus, 2000);
  }
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHeaderAutoButton);
  } else {
    initHeaderAutoButton();
  }
})();

// Fallback quick-population for controller Mode labels (runs immediately, before dynamic loader chain)
(function(){
  async function quickModes(){
    try {
      // Use unified auto-enable system
      const autoStatus = await fetch('/api/auto/status',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
      const globalAuto = autoStatus && autoStatus.global_auto;
      const controllers = autoStatus && autoStatus.controllers || {};
      
      // Update status chips based on will_automate (global_auto AND controller_auto)
      var lightsChip = document.getElementById('ov-lights-status');
      if (lightsChip) { 
        var willAuto = controllers.lights && controllers.lights.will_automate;
        lightsChip.textContent = willAuto ? 'AUTO' : 'MANUAL'; 
        lightsChip.className = 'ui-status-chip ' + (willAuto ? 'success':'neutral'); 
      }
      var mainPumpChip = document.getElementById('ov-main-pump-status');
      if (mainPumpChip) { 
        var willAuto = controllers.circulation && controllers.circulation.will_automate;
        mainPumpChip.textContent = willAuto ? 'AUTO' : 'MANUAL'; 
        mainPumpChip.className = 'ui-status-chip ' + (willAuto ? 'success':'neutral'); 
      }
      
      // Chiller status
      try {
        const ch = await fetch('/api/chiller/status',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
        var chChip = document.getElementById('ov-chiller-status');
        if (chChip) {
          var willAuto = controllers.chiller && controllers.chiller.will_automate;
          chChip.textContent = willAuto ? 'AUTO' : 'MANUAL';
          chChip.className = 'ui-status-chip ' + (willAuto ? 'success':'neutral');
        }
        var chHealthChip = document.getElementById('ov-chiller-health');
        if (chHealthChip && ch) {
          chHealthChip.textContent = ch.is_on ? 'RUNNING' : 'IDLE';
          chHealthChip.className = 'ui-status-chip ' + (ch.is_on ? 'RUNNING' : 'IDLE');
        }
      } catch(e){
        var chChip2 = document.getElementById('ov-chiller-status');
        if (chChip2) { chChip2.textContent = 'MANUAL'; chChip2.className = 'ui-status-chip neutral'; }
      }
      
      // pH status
      try {
        const ph = await fetch('/api/ph/status',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
        var phStatusChip = document.getElementById('ov-ph-status'); 
        if (phStatusChip) { 
          var willAuto = controllers.ph && controllers.ph.will_automate;
          phStatusChip.textContent = willAuto ? 'AUTO' : 'MANUAL'; 
          phStatusChip.className = 'ui-status-chip ' + (willAuto ? 'success':'neutral'); 
          // Clarify relationship between global AUTO and controller AUTO
          if (!willAuto && globalAuto) {
            phStatusChip.title = 'Global AUTO is ON; pH auto is OFF';
          } else if (willAuto) {
            phStatusChip.title = 'pH automation enabled';
          } else {
            phStatusChip.title = 'pH automation disabled';
          }
        }
        var phHealth = document.getElementById('ov-ph-health'); 
        if (phHealth) { 
          var g=ph.guards||{}; 
          var hardKeys=['estop','reservoir'];
          var softKeys=['safe_off','sensor_stale','interval','daily_cap','ec_baseline_low'];
          var hardActive = hardKeys.some(function(k){ return !!g[k]; });
          var softActive = softKeys.some(function(k){ return !!g[k]; });
          phHealth.textContent = hardActive ? 'BLOCKED' : (softActive ? 'GUARDED' : 'OK'); 
          phHealth.className = 'ui-status-chip ' + (hardActive ? 'danger' : (softActive ? 'warning' : 'success')); 
          var allActive = hardKeys.concat(softKeys).filter(function(k){ return !!g[k]; });
          phHealth.title = allActive.length ? ('Guards: '+allActive.join(', ')) : 'All guards OK'; 
        }
      } catch(e){ var phHealth = document.getElementById('ov-ph-health'); if (phHealth) { phHealth.textContent='—'; phHealth.className='ui-status-chip neutral'; }}
      
      // EC status
      try {
        const ec = await fetch('/api/ec/status',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
        var ecStatusChip = document.getElementById('ov-ec-status'); 
        if (ecStatusChip) { 
          var willAuto = controllers.ec && controllers.ec.will_automate;
          ecStatusChip.textContent = willAuto ? 'AUTO' : 'MANUAL'; 
          ecStatusChip.className = 'ui-status-chip ' + (willAuto ? 'success':'neutral'); 
        }
        var ecHealth = document.getElementById('ov-ec-health'); 
        if (ecHealth) { 
          var g=ec.guards||{}; 
          var hardKeys=['estop','reservoir'];
          var softKeys=['sensor_stale','mix_lock','interval','daily_cap'];
          var hardActive = hardKeys.some(function(k){ return !!g[k]; });
          var softActive = softKeys.some(function(k){ return !!g[k]; });
          ecHealth.textContent = hardActive ? 'BLOCKED' : (softActive ? 'GUARDED' : 'OK'); 
          ecHealth.className = 'ui-status-chip ' + (hardActive ? 'danger' : (softActive ? 'warning' : 'success')); 
          var allActive = hardKeys.concat(softKeys).filter(function(k){ return !!g[k]; });
          ecHealth.title = allActive.length ? ('Guards: '+allActive.join(', ')) : 'All guards OK'; 
        }
      } catch(e){ var ecHealth = document.getElementById('ov-ec-health'); if (ecHealth) { ecHealth.textContent='—'; ecHealth.className='ui-status-chip neutral'; }}
      
      // System status
      var sysStatusChip = document.getElementById('ov-system-status');
      if (sysStatusChip) {
        sysStatusChip.textContent = globalAuto ? 'AUTO' : 'MANUAL';
        sysStatusChip.className = 'ui-status-chip ' + (globalAuto ? 'success':'neutral');
      }
    } catch(e) {
      /* silent */
    }
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', quickModes); else quickModes();
})();
