/**
 * Intelligent Chiller Control UI
 * Hailea HS-52A - Cannabis-optimized temperature automation
 */
(() => {
  // Verbosity flag to silence non-critical logs
  const UI_VERBOSE = false;
  // ===== SIMPLIFIED HOLD SYSTEM =====
  let isHeld = false;

  async function chillerToggleHold() {
    try {
      const resp = await fetch('/api/controller/chiller/hold', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.ok) {
        isHeld = data.held;
        updateChillerHoldButton();
        updateEnvHealth();
      }
    } catch (e) {
      console.error('Failed to toggle hold:', e);
    }
  }

  function updateChillerHoldButton() {
    const btn = document.getElementById('chiller-hold-btn');
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

  async function syncChillerHoldState() {
    try {
      const resp = await fetch('/api/controller/chiller/mode', {cache: 'no-store'});
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.ok && data.mode) {
        isHeld = (data.mode === 'hold');
        updateChillerHoldButton();
      }
    } catch (e) {
      // Silent fail
    }
  }

  function updateEnvHealth() {
    const chip = document.getElementById('env-health-indicator');
    if (!chip) return;

    if (chillerState.estop) {
      chip.textContent = 'BLOCKED';
      chip.className = 'ui-status-chip error';
      return;
    }

    if (isHeld) {
      chip.textContent = 'HELD';
      chip.className = 'ui-status-chip warning';
      return;
    }

    if (chillerState.in_cooldown || chillerState.min_runtime_active) {
      chip.textContent = 'WAITING';
      chip.className = 'ui-status-chip warning';
      return;
    }

    if (chillerState.is_running) {
      chip.textContent = 'COOLING';
      chip.className = 'ui-status-chip success';
      return;
    }

    chip.textContent = 'AUTO';
    chip.className = 'ui-status-chip success';
  }

  window.chillerToggleHold = chillerToggleHold;

  // Initialize hold state on load
  document.addEventListener('DOMContentLoaded', async () => {
    await syncChillerHoldState();
  });

  // ===== CHILLER CONTROL LOGIC =====
  const q = (s) => document.querySelector(s);

  let chillerState = {
    auto_enabled: false,
    is_running: false,
    current_temp: null,
    target_temp: 19.0,
    hysteresis: 0.5,
    stage: 'default',
    in_cooldown: false,
    min_runtime_active: false,
  };

  // API helpers
  async function getJSON(url) {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
    return r.json();
  }

  async function postJSON(url, body = {}) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
    return r.json().catch(() => ({}));
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

  // Refresh chiller status
  async function refreshChillerStatus() {
    try {
      const [status, relays] = await Promise.all([
        getJSON('/api/chiller/status'),
        getJSON('/api/relays/status').catch(()=>null)
      ]);
      
      // Update state
      chillerState = { ...chillerState, ...status, estop: !!(relays && relays.estop) };
      
      // Update UI
      updateChillerUI();
      updateEnvHealth();

    } catch (e) {
      if (UI_VERBOSE) console.error('Failed to refresh chiller status:', e);
    }
  }

  // Update UI elements
  function updateChillerUI() {
    const state = chillerState;
    
    // Auto badge
    const badge = q('#chiller-auto-badge');
    if (badge) {
      if (state.auto_enabled) {
        badge.textContent = 'Auto Control ON';
        badge.style.background = 'rgba(34,197,94,0.15)';
        badge.style.borderColor = 'rgba(34,197,94,0.45)';
        badge.style.color = '#a7f3d0';
      } else {
        badge.textContent = 'Manual';
        badge.style.background = 'rgba(148,163,184,0.12)';
        badge.style.borderColor = 'rgba(148,163,184,0.3)';
        badge.style.color = '#cbd5e1';
      }
    }
    
    // Current temp
    const currentTempEl = q('#chiller-current-temp');
    if (currentTempEl) {
      if (state.current_temp !== null && state.current_temp !== undefined) {
        currentTempEl.textContent = `${state.current_temp.toFixed(1)}°C`;
      } else {
        currentTempEl.textContent = '—°C';
      }
    }
    
    // Target temp
    const targetTempEl = q('#chiller-target-temp');
    if (targetTempEl) {
      targetTempEl.textContent = `${state.target_temp.toFixed(1)}°C`;
    }
    
    // Stage
    const stageEl = q('#chiller-stage');
    if (stageEl) {
      const stageNames = {
        'default': 'Default',
        'veg': 'Vegetative',
        'flower': 'Flowering'
      };
      stageEl.textContent = stageNames[state.stage] || 'Default';
    }
    
    // Enable/Disable buttons
    const btnEnable = q('#btnChillerAutoEnable');
    const btnDisable = q('#btnChillerAutoDisable');
    if (btnEnable && btnDisable) {
      if (state.auto_enabled) {
        btnEnable.style.display = 'none';
        btnDisable.style.display = 'inline-block';
      } else {
        btnEnable.style.display = 'inline-block';
        btnDisable.style.display = 'none';
      }
    }
    
    // Status message
    const statusMsg = q('#chiller-status-message');
    if (statusMsg) {
      if (state.auto_enabled) {
        let msg = '';
        if (state.in_cooldown) {
          msg = '🕒 In cooldown period';
        } else if (state.min_runtime_active) {
          msg = '⏱️ Minimum runtime active';
        } else if (state.is_running) {
          msg = '❄️ Actively cooling';
        } else {
          msg = '✓ Monitoring temperature';
        }
        statusMsg.textContent = msg;
        statusMsg.style.color = '#93c5fd';
      } else {
        statusMsg.textContent = '';
      }
    }

    // Explicit state label
    const stateLabel = q('#chiller-state-label');
    if (stateLabel) {
      let label = 'IDLE';
      if (state.estop) label = 'BLOCKED';
      else if (isHeld) label = 'HELD';
      else if (state.in_cooldown || state.min_runtime_active) label = 'WAITING';
      else if (state.is_running) label = 'COOLING';
      else if (!state.auto_enabled) label = 'MANUAL';
      stateLabel.textContent = label;
    }
    
    // Update settings inputs (but not if user is actively editing them)
    const targetInput = q('#tempTarget');
    const hysteresisInput = q('#chillerHysteresis');
    const stageSelect = q('#chillerStage');
    
    if (targetInput && document.activeElement !== targetInput) {
      targetInput.value = state.target_temp.toFixed(1);
    }
    if (hysteresisInput && document.activeElement !== hysteresisInput) {
      hysteresisInput.value = state.hysteresis.toFixed(1);
    }
    if (stageSelect && document.activeElement !== stageSelect) {
      stageSelect.value = state.stage || 'default';
    }
  }

  // Enable auto control
  async function enableAutoControl() {
    try {
      await postJSON('/api/chiller/auto/enable');
      showToast('Chiller automation enabled', 'success');
      setTimeout(refreshChillerStatus, 200);
    } catch (e) {
      console.error('Failed to enable auto control:', e);
      showToast('Failed to enable automation', 'error');
    }
  }

  // Disable auto control
  async function disableAutoControl() {
    try {
      await postJSON('/api/chiller/auto/disable');
      showToast('Chiller automation disabled', 'info');
      setTimeout(refreshChillerStatus, 200);
    } catch (e) {
      console.error('Failed to disable auto control:', e);
      showToast('Failed to disable automation', 'error');
    }
  }

  // Save settings
  async function saveSettings() {
    try {
      const targetTemp = parseFloat(q('#tempTarget').value);
      const hysteresis = parseFloat(q('#chillerHysteresis').value);
      const stage = q('#chillerStage').value;
      
      // Validate
      if (targetTemp < 14 || targetTemp > 26) {
        showToast('Target temp must be 14-26°C', 'error');
        return;
      }
      
      if (hysteresis < 0.1 || hysteresis > 3.0) {
        showToast('Hysteresis must be 0.1-3.0°C', 'error');
        return;
      }
      
      await postJSON('/api/chiller/settings', {
        target_temp: targetTemp,
        hysteresis: hysteresis,
        stage: stage
      });
      
      showToast('Settings saved successfully', 'success');
      setTimeout(refreshChillerStatus, 200);
      
    } catch (e) {
      console.error('Failed to save settings:', e);
      showToast('Failed to save settings', 'error');
    }
  }

  // Force chiller ON/OFF
  async function forceChiller(desiredOn) {
    try {
      const durationSelect = q('#chillerForceDuration');
      const duration = durationSelect.value ? parseInt(durationSelect.value) : null;
      
      const action = desiredOn ? 'ON' : 'OFF';
      const durationText = duration ? `for ${duration} minutes` : 'indefinitely';
      
      const ok = confirm(`Force chiller ${action} ${durationText}?\n\nThis will override automation until the duration expires or you manually disable it.`);
      if (!ok) return;
      
      await postJSON('/api/chiller/force', {
        on: desiredOn,
        duration_minutes: duration
      });
      
      showToast(`Chiller forced ${action} ${durationText}`, 'warning');
      setTimeout(refreshChillerStatus, 200);
      
    } catch (e) {
      console.error('Failed to force chiller:', e);
      showToast('Failed to apply override', 'error');
    }
  }

  // Wire event handlers
  function wireChillerControls() {
    const btnEnable = q('#btnChillerAutoEnable');
    const btnDisable = q('#btnChillerAutoDisable');
    // Support both legacy and current save button ids
    const btnSaveSettings = q('#btnChillerSaveSettings') || q('#btnSaveTempSettings');
    const btnForceOn = q('#btnChillerForceOn');
    const btnForceOff = q('#btnChillerForceOff');
    
    if (btnEnable) btnEnable.addEventListener('click', enableAutoControl);
    if (btnDisable) btnDisable.addEventListener('click', disableAutoControl);
    if (btnSaveSettings) btnSaveSettings.addEventListener('click', saveSettings);
    if (btnForceOn) btnForceOn.addEventListener('click', () => forceChiller(true));
    if (btnForceOff) btnForceOff.addEventListener('click', () => forceChiller(false));
  }

  // Initialize
  function initChillerControl() {
    // Initialize only if chiller elements exist (works in Temperature tab)
    const currentTempEl = q('#chiller-current-temp');
    if (!currentTempEl) return;
    
    // Wire controls
    wireChillerControls();
    
    // Initial refresh
    refreshChillerStatus();
    
    // Periodic refresh (every 5 seconds)
    setInterval(refreshChillerStatus, 5000);
    
    console.log('Intelligent chiller control initialized');
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initChillerControl);
  } else {
    initChillerControl();
  }
})();
