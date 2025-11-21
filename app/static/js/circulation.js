/**
 * Circulation Controller - Mode management for Main + Chiller pumps with Safety Interlock
 */
(() => {
  // ===== STATE TRACKING =====
  let isHeld = false;
  let circEstop = false;
  let circCooldown = false;
  let chillerOn = false;
  let chillerPumpOn = false;
  let mainPumpOn = false;

  async function circToggleHold() {
    try {
      const resp = await fetch('/api/controller/circulation/hold', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.ok) {
        isHeld = data.held;
        updateCircHoldButton();
        updateCircHealth();
      }
    } catch (e) {
      console.error('Failed to toggle hold:', e);
    }
  }

  function updateCircHoldButton() {
    const btn = document.getElementById('circ-hold-btn');
    if (!btn) return;
    if (isHeld) {
      btn.classList.add('active', 'warning');
      btn.textContent = 'Resume';
      btn.title = 'Resume automation';
    } else {
      btn.classList.remove('active', 'warning');
      btn.textContent = 'Hold';
      btn.title = 'Pause automation';
    }
  }

  async function syncCircHoldState() {
    try {
      const r = await fetch('/api/controller/circulation/mode', {cache: 'no-store'});
      if (!r.ok) return;
      const data = await r.json();
      if (data.ok && data.mode) {
        isHeld = (data.mode === 'hold');
        updateCircHoldButton();
      }
    } catch (e) {
      // Silent fail
    }
  }

  function updateCircHealth() {
    const chip = document.getElementById('circ-health-indicator');
    if (!chip) return;

    if (circEstop) { chip.textContent='BLOCKED'; chip.className='ui-status-chip error'; return; }
    if (isHeld) { chip.textContent='HELD'; chip.className='ui-status-chip warning'; return; }
    if (circCooldown) { chip.textContent='WAITING'; chip.className='ui-status-chip warning'; return; }
    chip.textContent = 'AUTO'; chip.className = 'ui-status-chip success';
  }

  function updateInterlockUI() {
    // Update interlock banner
    const banner = document.getElementById('circ-interlock-banner');
    if (banner) {
      if (chillerOn && !chillerPumpOn) {
        // CRITICAL: Interlock violation
        banner.style.display = 'block';
        banner.style.background = 'rgba(239,68,68,0.15)';
        banner.style.border = '2px solid #ef4444';
        banner.style.color = '#fecaca';
        banner.innerHTML = '🚨 <strong>INTERLOCK VIOLATION:</strong> Chiller is running without chiller pump! This can damage equipment.';
      } else if (chillerOn && chillerPumpOn) {
        // Interlock active (normal operation)
        banner.style.display = 'block';
        banner.style.background = 'rgba(34,197,94,0.12)';
        banner.style.border = '2px solid #22c55e';
        banner.style.color = '#86efac';
        banner.innerHTML = '✅ <strong>INTERLOCK ACTIVE:</strong> Chiller pump running with chiller (normal operation)';
      } else {
        // No interlock needed
        banner.style.display = 'none';
      }
    }

    // Update chiller pump interlock message
    const pumpInterlock = document.getElementById('circ-chiller-pump-interlock');
    if (pumpInterlock) {
      if (chillerOn) {
        pumpInterlock.innerHTML = '🔒 <strong style="color:#ef4444;">LOCKED:</strong> Cannot turn OFF while chiller is running.';
      } else {
        pumpInterlock.innerHTML = '🔒 <strong>Safety Interlock:</strong> Auto-starts when chiller activates.';
      }
    }

    // Update interlock status indicator
    const interlockStatus = document.getElementById('circ-interlock-status');
    if (interlockStatus) {
      if (chillerOn && chillerPumpOn) {
        interlockStatus.textContent = 'Interlock: ACTIVE ✓';
        interlockStatus.style.color = '#22c55e';
      } else if (chillerOn && !chillerPumpOn) {
        interlockStatus.textContent = 'Interlock: VIOLATION ⚠️';
        interlockStatus.style.color = '#ef4444';
      } else {
        interlockStatus.textContent = 'Interlock: Standby';
        interlockStatus.style.color = '#64748b';
      }
    }

    // Disable chiller pump OFF button when chiller is running
    const chillerPumpBtn = document.getElementById('btnChillerPump');
    if (chillerPumpBtn && chillerOn && chillerPumpOn) {
      chillerPumpBtn.disabled = true;
      chillerPumpBtn.style.opacity = '0.5';
      chillerPumpBtn.style.cursor = 'not-allowed';
      chillerPumpBtn.title = 'Cannot turn OFF: Chiller is running (safety interlock)';
    } else if (chillerPumpBtn) {
      chillerPumpBtn.disabled = false;
      chillerPumpBtn.style.opacity = '1';
      chillerPumpBtn.style.cursor = 'pointer';
      chillerPumpBtn.title = 'Toggle Chiller Pump';
    }
  }

  async function refreshCirc(){
    try{
      const r = await fetch('/api/relays/status', {cache:'no-store'});
      if(!r.ok) throw new Error('HTTP '+r.status);
      const wrap = await r.json();
      circEstop = !!wrap.estop;
      const rel = wrap.relays || {};
      
      // Track pump states
      const main = rel.main_pump || {};
      const chillerPump = rel.chiller_pump || {};
      const chiller = rel.chiller_power || {};
      
      mainPumpOn = !!main.state;
      chillerPumpOn = !!chillerPump.state;
      chillerOn = !!chiller.state;
      
      // Update badges
      const mainBadge = document.getElementById('circ-main-pump');
      const chillerPumpBadge = document.getElementById('circ-chiller-pump');
      const chillerStatus = document.getElementById('circ-chiller-status');
      
      if (mainBadge) {
        mainBadge.textContent = mainPumpOn ? 'ON' : 'OFF';
        mainBadge.className = 'bop-status-badge ' + (mainPumpOn ? 'on' : 'off');
      }
      
      if (chillerPumpBadge) {
        chillerPumpBadge.textContent = chillerPumpOn ? 'ON' : 'OFF';
        chillerPumpBadge.className = 'bop-status-badge ' + (chillerPumpOn ? 'on' : 'off');
      }
      
      if (chillerStatus) {
        chillerStatus.textContent = chillerOn ? 'RUNNING' : 'OFF';
        chillerStatus.style.color = chillerOn ? '#22c55e' : '#94a3b8';
      }
      
      // Check cooldowns
      const cdMain = main.cooldown_remaining || main.cooldown || 0;
      const cdChill = chillerPump.cooldown_remaining || chillerPump.cooldown || 0;
      circCooldown = (cdMain>0) || (cdChill>0);
      
      // Update interlock UI
      updateInterlockUI();
    }catch(e){ 
      console.error('[Circulation] Refresh failed:', e);
    }
    updateCircHealth();
  }

  window.circToggleHold = circToggleHold;

  // Initialize hold state on load
  document.addEventListener('DOMContentLoaded', async () => {
    await syncCircHoldState();
    refreshCirc(); // Initial refresh
  });

  // Refresh every 3 seconds for responsive interlock feedback
  setInterval(() => {
    if (document.getElementById('circ-health-indicator')) { refreshCirc(); }
  }, 3000);
})();
