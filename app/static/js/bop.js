/**
 * BOP (Balance of Plant) - RDWC System Coordination
 * Coordinates Main Pump, Chiller Pump, and Chiller for proper RDWC operation
 * 
 * Rules:
 * 1. Chiller requires Chiller Pump to be ON
 * 2. Chiller combo (Chiller + Chiller Pump) requires Main Pump to be ON
 * 3. Main Pump ON triggers Chiller combo for accurate sensor readings
 * 4. Lights operate independently (part of grow cycle)
 */
(() => {
  const q = (s) => document.querySelector(s);
  const qAll = (s) => document.querySelectorAll(s);

  // BOP relay configuration
  const BOP_RELAYS = ['lights', 'main_pump', 'chiller_pump', 'chiller_power'];
  
  let bopState = {
    lights: false,
    main_pump: false,
    chiller_pump: false,
    chiller_power: false,
    estop: false,
    systemMode: 'manual'
  };

  // API helpers
  async function getJSON(url) {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
    return r.json();
  }

  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
    return r.json().catch(() => ({}));
  }

  // Check coordination rules
  function checkCoordinationRules(relay, desiredState) {
    const current = bopState;
    
    // If turning OFF, always allow (safety first)
    if (!desiredState) return { allowed: true };
    
    // If E-STOP active, block all ON commands
    if (current.estop) {
      return { allowed: false, reason: 'E-STOP is engaged' };
    }

    // Rule 1: Chiller requires Chiller Pump to be ON
    if (relay === 'chiller_power' && !current.chiller_pump) {
      return { 
        allowed: false, 
        reason: 'Chiller requires Chiller Pump to be running',
        suggest: 'Turn on Chiller Pump first'
      };
    }

    // Rule 2: Chiller Pump requires Main Pump to be ON (for RDWC circulation)
    if (relay === 'chiller_pump' && !current.main_pump) {
      return { 
        allowed: false, 
        reason: 'Chiller Pump requires Main Pump to be running',
        suggest: 'Turn on Main Pump first for RDWC circulation'
      };
    }

    // Rule 2b: Chiller requires Main Pump (via Chiller Pump requirement)
    if (relay === 'chiller_power' && !current.main_pump) {
      return { 
        allowed: false, 
        reason: 'Chiller requires Main Pump to be running for RDWC circulation',
        suggest: 'Turn on Main Pump and Chiller Pump first'
      };
    }

    return { allowed: true };
  }

  // Apply coordination rules when toggling
  async function toggleBOPRelay(relay) {
    try {
      const currentState = bopState[relay];
      const desiredState = !currentState;
      
      // Check coordination rules
      const check = checkCoordinationRules(relay, desiredState);
      if (!check.allowed) {
        showCoordinationBlock(check.reason, check.suggest);
        return;
      }

      // If turning ON Main Pump, auto-enable chiller combo for RDWC
      if (relay === 'main_pump' && desiredState) {
        await toggleRelay('main_pump', true);
        // Auto-enable chiller combo after short delay
        setTimeout(async () => {
          try {
            await toggleRelay('chiller_pump', true);
            await toggleRelay('chiller_power', true);
            showToast('RDWC circulation active: Main Pump + Chiller combo enabled', 'success');
          } catch (e) {
            console.error('Failed to auto-enable chiller combo:', e);
          }
        }, 500);
        return;
      }

      // If turning OFF Main Pump, warn and auto-disable chiller combo
      if (relay === 'main_pump' && !desiredState) {
        const ok = confirm('Turning OFF Main Pump will also disable Chiller Pump and Chiller.\n\nContinue?');
        if (!ok) return;
        
        await toggleRelay('chiller_power', false);
        await toggleRelay('chiller_pump', false);
        await toggleRelay('main_pump', false);
        showToast('RDWC circulation stopped: Main Pump + Chiller combo disabled', 'warning');
        return;
      }

      // If turning OFF Chiller Pump, also turn OFF Chiller
      if (relay === 'chiller_pump' && !desiredState && bopState.chiller_power) {
        await toggleRelay('chiller_power', false);
        await toggleRelay('chiller_pump', false);
        showToast('Chiller combo disabled', 'info');
        return;
      }

      // Normal toggle
      await toggleRelay(relay, desiredState);
      
      // If we just turned ON Chiller Pump and Main Pump is ON, suggest enabling Chiller
      if (relay === 'chiller_pump' && desiredState && bopState.main_pump && !bopState.chiller_power) {
        setTimeout(() => {
          const enableChiller = confirm('Chiller Pump is now ON.\n\nEnable Chiller for full cooling?');
          if (enableChiller) {
            toggleRelay('chiller_power', true);
          }
        }, 300);
      }

    } catch (e) {
      console.error('BOP toggle failed:', e);
      showToast(`Failed to toggle ${relay}`, 'error');
    }
  }

  // Toggle relay via API
  async function toggleRelay(relay, desiredState) {
    try {
      // Try new wrapper endpoint
      const result = await postJSON(`/api/relay/${encodeURIComponent(relay)}/toggle`, { on: !!desiredState });
      
      // Refresh BOP state immediately
      setTimeout(refreshBOPState, 150);
      
      return result;
    } catch (e) {
      // Fallback to legacy endpoint
      try {
        return await postJSON('/relay/set', { name: relay, on: !!desiredState });
      } catch (e2) {
        throw new Error('All relay set methods failed');
      }
    }
  }

  // Show coordination block banner
  function showCoordinationBlock(reason, suggest) {
    const banner = q('#bop-coordination-banner');
    const message = q('#bop-coordination-message');
    if (banner && message) {
      message.textContent = `${reason}. ${suggest || ''}`;
      banner.style.display = 'block';
    }
  }

  // Toast notifications
  function showToast(message, type = 'info') {
    const container = q('#toast-container') || (() => {
      const div = document.createElement('div');
      div.id = 'toast-container';
      div.style.cssText = 'position:fixed;top:16px;right:16px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
      document.body.appendChild(div);
      return div;
    })();

    const colors = {
      success: 'rgba(34,197,94,0.9)',
      error: 'rgba(239,68,68,0.9)',
      warning: 'rgba(251,191,36,0.9)',
      info: 'rgba(59,130,246,0.9)'
    };

    const toast = document.createElement('div');
    toast.style.cssText = `
      background: ${colors[type] || colors.info};
      color: white;
      padding: 12px 16px;
      border-radius: 8px;
      box-shadow: 0 4px 6px rgba(0,0,0,0.3);
      font-size: 14px;
      max-width: 320px;
      opacity: 1;
      transition: opacity 0.3s;
    `;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // Refresh BOP relay states
  async function refreshBOPState() {
    try {
      // Get relay status (prefer new wrapper endpoint)
      let relayData;
      try {
        const wrap = await getJSON('/api/relays/status');
        if (wrap && wrap.relays) {
          relayData = wrap.relays;
          bopState.estop = !!wrap.estop;
          bopState.systemMode = wrap.mode || 'manual';
        }
      } catch (e) {
        // Fallback to legacy endpoint
        relayData = await getJSON('/relay/status');
      }

      // Update BOP state
      BOP_RELAYS.forEach(relay => {
        const info = relayData[relay];
        if (info) {
          bopState[relay] = !!(info.is_on || info.state);
        }
      });

      // Update UI
      updateBOPUI();

    } catch (e) {
      console.error('Failed to refresh BOP state:', e);
    }
  }

  // Update BOP UI elements
  function updateBOPUI() {
    // Update status badges
    BOP_RELAYS.forEach(relay => {
      const badge = q(`#bop-${relay}-status`);
      if (badge) {
        const isOn = bopState[relay];
        badge.textContent = isOn ? 'ON' : 'OFF';
        badge.className = `bop-status-badge ${isOn ? 'on' : 'off'}`;
      }
    });

    // Update relay buttons in BOP card
    BOP_RELAYS.forEach(relay => {
      const btn = q(`#bop-card .relay-btn[data-relay="${relay}"]`);
      if (btn) {
        const isOn = bopState[relay];
        btn.className = `relay-btn ${isOn ? 'relay-on' : 'relay-off'}`;
        
        // Update label
        const label = btn.querySelector('.relay-label');
        if (label) {
          const relayNames = {
            lights: 'Lights',
            main_pump: 'Main Pump',
            chiller_pump: 'Chiller Pump',
            chiller_power: 'Chiller'
          };
          label.textContent = (isOn ? '● ' : '○ ') + (relayNames[relay] || relay);
        }

        // Disable buttons in Auto mode or E-STOP
        if (bopState.systemMode === 'auto' || bopState.estop) {
          btn.disabled = true;
          btn.style.opacity = '0.6';
          btn.style.cursor = 'not-allowed';
        } else {
          btn.disabled = false;
          btn.style.opacity = '1';
          btn.style.cursor = 'pointer';
        }
      }
    });
  }

  // Wire BOP relay buttons
  function wireBOPButtons() {
    BOP_RELAYS.forEach(relay => {
      const btn = q(`#bop-card .relay-btn[data-relay="${relay}"]`);
      if (btn) {
        btn.addEventListener('click', () => {
          if (bopState.systemMode === 'auto') {
            showToast('Controls disabled in Auto mode', 'warning');
            return;
          }
          if (bopState.estop) {
            showToast('E-STOP engaged: action blocked', 'warning');
            return;
          }
          toggleBOPRelay(relay);
        });
      }
    });
  }

  // Initialize BOP UI
  function initBOP() {
    const bopCard = q('#bop-card');
    if (!bopCard) {
      console.warn('BOP card not found in DOM');
      return;
    }

    // Wire buttons
    wireBOPButtons();

    // Initial state refresh
    refreshBOPState();

    // Periodic refresh (1 second)
    setInterval(refreshBOPState, 1000);

    console.log('BOP (Balance of Plant) initialized');
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBOP);
  } else {
    initBOP();
  }
})();
