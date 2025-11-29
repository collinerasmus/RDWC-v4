/**
 * Circulation Controller - Mode management for Main + Chiller pumps
 * Uses unified auto-enable system for consistent status display
 */
(() => {
  let circEstop = false;
  let circCooldown = false;
  let circWillAutomate = false;

  function updateCircHealth() {
    const chip = document.getElementById('circ-health-indicator');
    if (!chip) return;

    if (circEstop) { 
      chip.textContent='BLOCKED'; 
      chip.className='ui-status-chip error'; 
      chip.title='E-STOP active';
      return; 
    }
    if (circCooldown) { 
      chip.textContent='WAITING'; 
      chip.className='ui-status-chip warning'; 
      chip.title='Pump cooldown active';
      return; 
    }
    if (!circWillAutomate) {
      chip.textContent = 'MANUAL';
      chip.className = 'ui-status-chip neutral';
      chip.title = 'Manual control mode';
      return;
    }
    chip.textContent = 'AUTO'; 
    chip.className = 'ui-status-chip success';
    chip.title = 'Automation running';
  }

  async function refreshCirc(){
    try{
      // Fetch relay status for pumps and E-STOP
      const r = await fetch('/api/relays/status', {cache:'no-store'});
      if(!r.ok) throw new Error('HTTP '+r.status);
      const wrap = await r.json();
      circEstop = !!wrap.estop;
      const rel = wrap.relays || {};
      const main = rel.main_pump || {};
      const chill = rel.chiller_pump || {};
      const cdMain = main.cooldown_remaining || main.cooldown || 0;
      const cdChill = chill.cooldown_remaining || chill.cooldown || 0;
      circCooldown = (cdMain>0) || (cdChill>0);
      
      // Update pump ON/OFF badges
      const badgeMain = document.getElementById('circ-main-pump');
      if (badgeMain){
        const on = !!main.is_on;
        badgeMain.textContent = on ? 'ON':'OFF';
        badgeMain.className = 'bop-status-badge ' + (on ? 'on':'off');
      }
      const badgeChill = document.getElementById('circ-chiller-pump');
      if (badgeChill){
        const on = !!chill.is_on;
        badgeChill.textContent = on ? 'ON':'OFF';
        badgeChill.className = 'bop-status-badge ' + (on ? 'on':'off');
      }
      
      // Fetch unified auto-enable status for will_automate
      const autoResp = await fetch('/api/auto/status', {cache:'no-store'});
      if (autoResp.ok) {
        const autoData = await autoResp.json();
        circWillAutomate = !!(autoData.controllers && autoData.controllers.circulation && autoData.controllers.circulation.will_automate);
      }
    }catch(e){ /* leave previous state */ }
    updateCircHealth();
  }

  // Refresh health every 4s from relays
  setInterval(() => {
    if (document.getElementById('circ-health-indicator')) { refreshCirc(); }
  }, 4000);
})();
