/**
 * Intelligent Temperature Control UI
 * Hailea HS-52A - Cannabis-optimized temperature automation
 */
(() => {
  // Verbosity flag to silence non-critical logs
  const UI_VERBOSE = false;
  // Guard against multiple initializations
  let _refreshInterval = null; // deprecated (pollingManager now drives refreshes)

  function updateEnvHealth() {
    const chip = document.getElementById('env-health-indicator');
    if (!chip) return;

    if (temperatureState.estop) {
      chip.textContent = 'BLOCKED';
      chip.className = 'ui-status-chip error';
      return;
    }

    // Prefer live running state; cooldown guards only matter when OFF
    if (temperatureState.is_running) {
      chip.textContent = 'COOLING';
      chip.className = 'ui-status-chip success';
      return;
    }

    if (temperatureState.in_cooldown || temperatureState.min_runtime_active) {
      chip.textContent = 'WAITING';
      chip.className = 'ui-status-chip warning';
      return;
    }

    chip.textContent = 'AUTO';
    chip.className = 'ui-status-chip success';
  }

  // ===== TEMPERATURE CONTROL LOGIC =====
  const q = (s) => document.querySelector(s);

  let temperatureState = {
    auto_enabled: false,
    is_running: false,
    current_temp: null,
    target_temp: 19.0,
    hysteresis: 0.6,
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

  // Refresh temperature status
  async function refreshTemperatureStatus() {
    try {
      const [status, relays] = await Promise.all([
        getJSON('/api/temperature/status').catch(e => ({ ok: false, error: e.message })),
        getJSON('/api/relays/status').catch(()=>null)
      ]);
      // Defensive: if status is error, show toast and set safe defaults
      if (status && status.ok === false) {
        showToast('Temperature API error: ' + (status.error || 'Unknown'), 'error');
        temperatureState = { ...temperatureState, current_temp: null, is_running: false, auto_enabled: false };
      } else {
        temperatureState = { ...temperatureState, ...status, estop: !!(relays && relays.estop) };
      }
      updateTemperatureUI();
      updateEnvHealth();
    } catch (e) {
      showToast('Failed to refresh temperature status', 'error');
      if (UI_VERBOSE) console.error('Failed to refresh temperature status:', e);
    }
  }

  // Render chiller event log (similar styling to dose logs)
  function renderChillerLog(events) {
    const listEl = q('#temperature-events-list');
    if (!listEl) return;

    if (!events || events.length === 0) {
      listEl.innerHTML = '<div style="text-align:center;padding:16px;color:#94a3b8;">No chiller events yet.</div>';
      return;
    }

    listEl.innerHTML = events.map(evt => {
      const ts = new Date(evt.ts);
      const tsStr = ts.toISOString().replace('T', ' ').split('.')[0];
      const stateText = (evt.state || '').toUpperCase() === 'ON' ? 'ON' : 'OFF';
      const reason = evt.reason || 'chiller';
      
      // Single-row compact chip: timestamp • state • reason
      const dot = '<span style="color:#4b5563;">•</span>';
      const segments = [
        `<span style="font-weight:700;">${tsStr}</span>`,
        `<span style="color:#9ca3af;">${stateText}</span>`,
        `<span style="color:#9ca3af;">${reason}</span>`
      ];

      return `<div style="margin-bottom:4px;padding:4px 6px;border-radius:4px;background:rgba(59,130,246,0.06);border-left:2px solid rgba(59,130,246,0.25);display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:var(--font-xs);color:#cbd5e1;">${segments.join(dot)}</div>`;
    }).join('');
  }

  async function updateChillerLog() {
    try {
      const res = await fetch('/api/temperature/events?limit=500', { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const eventsRaw = Array.isArray(data?.events) ? data.events : [];
      // Map backend shape {ts_utc, prev_state, new_state, reason} to UI shape
      const events = eventsRaw
        .map(ev => ({
          ts: (ev.ts_utc || ev.ts) ? ((ev.ts_utc || ev.ts) * 1000) : Date.now(),
          state: ev.new_state || ev.state || 'OFF',
          reason: ev.reason || ev.prev_state || ''
        }))
        .sort((a,b) => (b.ts||0) - (a.ts||0))
        .slice(0, 100);
      renderChillerLog(events);
    } catch (e) {
      if (UI_VERBOSE) console.error('Chiller log fetch failed', e);
    }
  }

  // Update UI elements
  function updateTemperatureUI() {
    const state = temperatureState;
    // Runtime / cycles KPIs if present in DOM and state
    const runtimeEl = q('#temperature-runtime-today');
    if (runtimeEl && typeof state.total_runtime_today === 'number') {
      const mins = state.total_runtime_today / 60;
      const hrs = mins / 60;
      const display = hrs >= 1 ? `${hrs.toFixed(1)} h` : `${mins.toFixed(0)} min`;
      runtimeEl.textContent = display;
    }
    const cyclesEl = q('#temperature-cycles-today');
    if (cyclesEl && typeof state.cycles_today === 'number') {
      cyclesEl.textContent = `${state.cycles_today}`;
    }
    
    // Auto badge
    const badge = q('#temperature-auto-badge');
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
    const currentTempEl = q('#temperature-current-temp');
    if (currentTempEl) {
      if (state.current_temp !== null && state.current_temp !== undefined) {
        currentTempEl.textContent = `${state.current_temp.toFixed(1)}°C`;
      } else {
        currentTempEl.textContent = '—°C';
      }
    }
    
    // Target temp
    const targetTempEl = q('#temperature-target-temp');
    if (targetTempEl) {
      targetTempEl.textContent = `${state.target_temp.toFixed(1)}°C`;
    }
    
    // Stage
    const stageEl = q('#temperature-stage');
    if (stageEl) {
      const stageNames = {
        'default': 'Default',
        'veg': 'Vegetative',
        'flower': 'Flowering'
      };
      stageEl.textContent = stageNames[state.stage] || 'Default';
    }
    
    // Enable/Disable buttons
    const btnEnable = q('#btnTemperatureAutoEnable');
    const btnDisable = q('#btnTemperatureAutoDisable');
    if (btnEnable && btnDisable) {
      if (state.auto_enabled) {
        btnEnable.style.display = 'none';
        btnDisable.style.display = 'inline-block';
      } else {
        btnEnable.style.display = 'inline-block';
        btnDisable.style.display = 'none';
      }
    }
    
    // Countdown timer (independent of status message)
    const timerKpi = q('#temperature-timer-kpi');
    const timerEl = q('#temperature-countdown-timer');
    
    if (timerKpi && timerEl && state.auto_enabled) {
      let showTimer = false;
      let timerSeconds = 0;
      
      if (state.is_running && state.min_runtime_active && state.current_runtime !== undefined) {
        const minOn = 60; // default min_on_seconds
        timerSeconds = Math.max(0, minOn - state.current_runtime);
        showTimer = timerSeconds > 0;
      } else if (state.in_cooldown && state.seconds_since_off !== undefined) {
        const minOff = 300; // default min_off_seconds
        timerSeconds = Math.max(0, minOff - state.seconds_since_off);
        showTimer = timerSeconds > 0;
      }
      
      if (showTimer && timerSeconds > 0) {
        const mins = Math.floor(timerSeconds / 60);
        const secs = timerSeconds % 60;
        timerEl.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
        timerKpi.style.display = '';
      } else {
        timerKpi.style.display = 'none';
      }
    } else if (timerKpi) {
      timerKpi.style.display = 'none';
    }

    // Status message (legacy field - may not exist in template)
    const statusMsg = q('#temperature-status-message');
    if (statusMsg) {
      if (state.auto_enabled) {
        let msg = '';
        if (state.is_running) {
          msg = state.min_runtime_active ? '❄️ Cooling (min runtime guard)' : '❄️ Actively cooling';
        } else if (state.in_cooldown) {
          msg = '🕒 In cooldown period';
        } else if (state.min_runtime_active) {
          msg = '⏱️ Minimum runtime active';
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
    const stateLabel = q('#temperature-state-label');
    if (stateLabel) {
      let label = 'IDLE';
      if (state.estop) label = 'BLOCKED';
      else if (state.is_running) label = 'COOLING';
      else if (state.in_cooldown || state.min_runtime_active) label = 'WAITING';
      else if (!state.auto_enabled) label = 'MANUAL';
      stateLabel.textContent = label;
    }
    
    // Update settings inputs (but not if user is actively editing them)
    const targetInput = q('#tempTarget');
    const hysteresisInput = q('#temperatureHysteresis');
    const stageSelect = q('#temperatureStage');
    
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
      await postJSON('/api/temperature/auto/enable');
      showToast('Temperature automation enabled', 'success');
      setTimeout(refreshTemperatureStatus, 200);
    } catch (e) {
      console.error('Failed to enable auto control:', e);
      showToast('Failed to enable automation', 'error');
    }
  }

  // Disable auto control
  async function disableAutoControl() {
    try {
      await postJSON('/api/temperature/auto/disable');
      showToast('Temperature automation disabled', 'info');
      setTimeout(refreshTemperatureStatus, 200);
    } catch (e) {
      console.error('Failed to disable auto control:', e);
      showToast('Failed to disable automation', 'error');
    }
  }

  // Save settings
  async function saveSettings() {
    try {
      const targetTemp = parseFloat(q('#tempTarget').value);
      const hysteresis = parseFloat(q('#temperatureHysteresis').value);
      const stage = q('#temperatureStage').value;
      
      // Validate
      if (targetTemp < 14 || targetTemp > 26) {
        showToast('Target temp must be 14-26°C', 'error');
        return;
      }
      
      if (hysteresis < 0.1 || hysteresis > 3.0) {
        showToast('Hysteresis must be 0.1-3.0°C', 'error');
        return;
      }
      
      await postJSON('/api/temperature/settings', {
        target_temp: targetTemp,
        hysteresis: hysteresis,
        stage: stage
      });
      
      showToast('Settings saved successfully', 'success');
      setTimeout(refreshTemperatureStatus, 200);
      
    } catch (e) {
      console.error('Failed to save settings:', e);
      showToast('Failed to save settings', 'error');
    }
  }

  // Force temperature ON/OFF
  async function forceTemperature(desiredOn) {
    try {
      const durationSelect = q('#temperatureForceDuration');
      const duration = durationSelect.value ? parseInt(durationSelect.value) : null;
      
      const action = desiredOn ? 'ON' : 'OFF';
      const durationText = duration ? `for ${duration} minutes` : 'indefinitely';
      
      const ok = confirm(`Force cooling ${action} ${durationText}?\n\nThis will override automation until the duration expires or you manually disable it.`);
      if (!ok) return;
      
      await postJSON('/api/temperature/force', {
        on: desiredOn,
        duration_minutes: duration
      });
      
      showToast(`Cooling forced ${action} ${durationText}`, 'warning');
      setTimeout(refreshTemperatureStatus, 200);
      
    } catch (e) {
      console.error('Failed to force temperature:', e);
      showToast('Failed to apply override', 'error');
    }
  }

  // Wire event handlers
  function wireTemperatureControls() {
    const btnEnable = q('#btnTemperatureAutoEnable');
    const btnDisable = q('#btnTemperatureAutoDisable');
    // Only bind to #btnTemperatureSaveSettings, not #btnSaveTempSettings
    // (controller_settings.js handles #btnSaveTempSettings with complete field set)
    const btnSaveSettings = q('#btnTemperatureSaveSettings');
    const btnForceOn = q('#btnTemperatureForceOn');
    const btnForceOff = q('#btnTemperatureForceOff');
    
    if (btnEnable) btnEnable.addEventListener('click', enableAutoControl);
    if (btnDisable) btnDisable.addEventListener('click', disableAutoControl);
    if (btnSaveSettings) btnSaveSettings.addEventListener('click', saveSettings);
    if (btnForceOn) btnForceOn.addEventListener('click', () => forceTemperature(true));
    if (btnForceOff) btnForceOff.addEventListener('click', () => forceTemperature(false));
  }

  // Initialize
  function initTemperatureControl() {
    // Initialize only if temperature elements exist (works in Temperature tab)
    const currentTempEl = q('#temperature-current-temp');
    if (!currentTempEl) return;
    
    // Prevent multiple initializations
    if (_refreshInterval) {
      console.log('Temperature control already initialized, skipping');
      return;
    }
    
    // Wire controls
    wireTemperatureControls();
    
    // Initial refresh
    refreshTemperatureStatus();
    updateChillerLog();
    
    // Register with centralized polling manager (main loop ~6s)
    if(window.pollingManager && !window.__temperaturePollingRegistered){
      window.__temperaturePollingRegistered = true;
      window.pollingManager.register('temperature-status', async ()=>{ await refreshTemperatureStatus(); await syncTemperatureHoldState(); await updateChillerLog(); }, 'main');
    } else {
      // Fallback: very slow local polling if manager missing
      _refreshInterval = setInterval(() => { refreshTemperatureStatus(); updateChillerLog(); }, 12000);
    }
    console.log('Intelligent temperature control initialized (event-driven)');
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTemperatureControl);
  } else {
    initTemperatureControl();
  }
})();
