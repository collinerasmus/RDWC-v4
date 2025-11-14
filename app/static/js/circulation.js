/**
 * Circulation Controller - Mode management for Main + Chiller pumps
 */
(() => {
  // ===== MODE MANAGEMENT =====
  let circMode = localStorage.getItem('circ_mode') || 'manual';
  let circEstop = false;
  let circCooldown = false;

  function circSetMode(next) {
    // Normalize 'maintenance' to 'maint' for consistency
    if (next === 'maintenance') next = 'maint';
    if (!['auto', 'manual', 'maint'].includes(next)) return;
    
    circMode = next;
    localStorage.setItem('circ_mode', next);

    // Update button states
    ['auto', 'manual', 'maint'].forEach(m => {
      const btn = document.getElementById(`circ-mode-${m}`);
      if (btn) btn.classList.toggle('active', m === next);
    });

    // Show/hide content sections if they exist (future expansion)
    const autoContent = document.getElementById('circ-auto-content');
    const manualContent = document.getElementById('circ-manual-content');
    const maintContent = document.getElementById('circ-maint-content');
    if (autoContent) autoContent.style.display = (next === 'auto') ? 'block' : 'none';
    if (manualContent) manualContent.style.display = (next === 'manual') ? 'block' : 'none';
    if (maintContent) maintContent.style.display = (next === 'maint') ? 'block' : 'none';

    updateCircHealth();
  }

  function updateCircHealth() {
    const chip = document.getElementById('circ-health-indicator');
    if (!chip) return;

    if (circEstop) { chip.textContent='BLOCKED'; chip.className='ui-status-chip error'; return; }
    if (circMode === 'maint') { chip.textContent='MAINT'; chip.className='ui-status-chip warning'; return; }
    if (circCooldown) { chip.textContent='HOLDING'; chip.className='ui-status-chip warning'; return; }
    chip.textContent = 'OK'; chip.className = 'ui-status-chip success';
  }

  async function refreshCirc(){
    try{
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
    }catch(e){ /* leave previous state */ }
    updateCircHealth();
  }

  window.circSetMode = circSetMode;

  // Initialize mode on load
  document.addEventListener('DOMContentLoaded', () => {
    circSetMode(circMode);
  });

  // Refresh health every 5s from relays
  setInterval(() => {
    if (document.getElementById('circ-health-indicator')) { refreshCirc(); }
  }, 5000);
})();
