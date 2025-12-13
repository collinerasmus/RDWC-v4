/**
 * Circulation Controller - Mode management for Main + Temperature pumps
 */
(() => {
  let circEstop = false;
  let circCooldown = false;

  function updateCircHealth() {
    const chip = document.getElementById('circ-health-indicator');
    if (!chip) return;

    if (circEstop) { chip.textContent='BLOCKED'; chip.className='ui-status-chip error'; return; }
    if (circCooldown) { chip.textContent='WAITING'; chip.className='ui-status-chip warning'; return; }
    chip.textContent = 'AUTO'; chip.className = 'ui-status-chip success';
  }

  async function refreshCirc(){
    try{
      const r = await fetch('/api/relays/status', {cache:'no-store'});
      if(!r.ok) throw new Error('HTTP '+r.status);
      const wrap = await r.json();
      circEstop = !!wrap.estop;
      const rel = wrap.relays || {};
      const main = rel.main_pump || {};
      const temp = rel.chiller_pump || {};
      const cdMain = main.cooldown_remaining || main.cooldown || 0;
      const cdtemp = temp.cooldown_remaining || temp.cooldown || 0;
      circCooldown = (cdMain>0) || (cdtemp>0);
      // Update pump ON/OFF badges (previously only updated in inline script, which might not run)
      const badgeMain = document.getElementById('circ-main-pump');
      if (badgeMain){
        const on = !!main.is_on;
        badgeMain.textContent = on ? 'ON':'OFF';
        badgeMain.className = 'bop-status-badge ' + (on ? 'on':'off');
      }
      const badgetemp = document.getElementById('circ-temperature-pump');
      if (badgetemp){
        const on = !!temp.is_on;
        badgetemp.textContent = on ? 'ON':'OFF';
        badgetemp.className = 'bop-status-badge ' + (on ? 'on':'off');
      }
    }catch(e){ /* leave previous state */ }
    updateCircHealth();
  }

  // Refresh health every 4s from relays
  setInterval(() => {
    if (document.getElementById('circ-health-indicator')) { refreshCirc(); }
  }, 4000); // 4s refresh for parity with lights
})();

