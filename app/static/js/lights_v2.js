/**
 * Intelligent Lights Control UI - Grow Light Scheduler (Edge-Only)
 * FastAPI integration with schedule, mode management, and relay protection
 */
(() => {
  const UI_VERBOSE = false;
  
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

  // DOM helpers
  const $ = (id) => document.getElementById(id);
  const q = (s) => document.querySelector(s);

  // Toast notifications
  function showToast(message, type = 'info') {
    const container = $('toast-container') || (() => {
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

  // State tracking
  let lightsState = {
    is_on: false,
    mode: 'manual',
    estop: false,
    cooldown_remaining: 0,
    schedule_enabled: true,
  };

  let lightsEvents = [];

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined || seconds <= 0) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function updateLightsHealth() {
    const chip = $('lights-health-indicator');
    if (!chip) return;

    if (lightsState.estop) {
      chip.textContent = 'BLOCKED';
      chip.className = 'ui-status-chip error';
      chip.title = 'E-STOP is active';
      return;
    }

    if (lightsState.mode === 'maintenance') {
      chip.textContent = 'MAINT';
      chip.className = 'ui-status-chip warning';
      chip.title = 'Maintenance mode';
      return;
    }

    if (lightsState.cooldown_remaining > 0) {
      chip.textContent = 'WAITING';
      chip.className = 'ui-status-chip warning';
      chip.title = `Cooldown ${Math.ceil(lightsState.cooldown_remaining)}s`;
      return;
    }

    if (lightsState.mode === 'auto' && lightsState.schedule_enabled) {
      chip.textContent = 'RUNNING';
      chip.className = 'ui-status-chip success';
      chip.title = 'Schedule automation active';
      return;
    }

    chip.textContent = 'MANUAL';
    chip.className = 'ui-status-chip neutral';
    chip.title = 'Manual control mode';
  }

  function updateLightsUI() {
    // State badge
    const badge = $('lights-status');
    if (badge) {
      badge.textContent = lightsState.is_on ? 'ON' : 'OFF';
      badge.className = 'bop-status-badge ' + (lightsState.is_on ? 'on' : 'off');
    }

    // Mode indicator
    const modeEl = $('lights-mode-indicator');
    if (modeEl) {
      modeEl.textContent = lightsState.mode.toUpperCase();
      modeEl.className = 'ui-status-chip ' + 
        (lightsState.mode === 'auto' ? 'success' : lightsState.mode === 'maintenance' ? 'warning' : 'neutral');
    }

    // Schedule KPI
    const schedEl = $('lights-sched-kpi');
    if (schedEl) {
      if (lightsState.mode === 'auto' && lightsState.schedule_enabled) {
        schedEl.textContent = 'Following schedule';
      } else if (lightsState.mode === 'auto' && !lightsState.schedule_enabled) {
        schedEl.textContent = 'Schedule disabled';
      } else if (lightsState.mode === 'maintenance') {
        schedEl.textContent = 'Maintenance mode';
      } else {
        schedEl.textContent = 'Manual control';
      }
    }

    // Cooldown display
    const cooldownEl = $('lights-cooldown-display');
    if (cooldownEl) {
      if (lightsState.cooldown_remaining > 0) {
        cooldownEl.style.display = 'block';
        cooldownEl.textContent = `Cooldown: ${formatDuration(lightsState.cooldown_remaining)}`;
      } else {
        cooldownEl.style.display = 'none';
      }
    }

    // Mode buttons
    ['auto', 'manual', 'maintenance'].forEach(m => {
      const btn = $(`lights-mode-${m}`);
      if (btn) btn.classList.toggle('active', m === lightsState.mode);
    });

    // Toggle button state
    const toggleBtn = $('btnLightsToggle');
    if (toggleBtn) {
      const canToggle = !lightsState.estop && (lightsState.mode === 'manual' || 
        (lightsState.mode === 'auto' && localStorage.getItem('safety.allow_force')));
      toggleBtn.disabled = !canToggle;
      toggleBtn.style.opacity = canToggle ? '1' : '0.6';
      toggleBtn.style.cursor = canToggle ? 'pointer' : 'not-allowed';
      toggleBtn.className = 'relay-btn ' + (lightsState.is_on ? 'relay-on' : 'relay-off');
      const label = toggleBtn.querySelector('.relay-label');
      if (label) {
        label.textContent = (lightsState.is_on ? '● ' : '○ ') + 'Lights';
      }
    }

    updateLightsHealth();
  }

  function renderLightsEventLog(events) {
    const listEl = $('lights-events-list');
    if (!listEl) return;

    if (!events || events.length === 0) {
      listEl.innerHTML = '<div style="text-align:center;padding:16px;color:#94a3b8;">No lights events yet.</div>';
      return;
    }

    listEl.innerHTML = events.slice(-20).reverse().map(evt => {
      const ts = new Date(evt.ts * 1000);
      const tsStr = ts.toISOString().replace('T', ' ').split('.')[0];
      const state = evt.final ? '<span style="color:#22c55e;font-weight:600;">ON</span>' : '<span style="color:#ef4444;font-weight:600;">OFF</span>';
      const reason = evt.reason ? ` · ${evt.reason}` : '';
      return `
        <div style="padding:6px 4px;border-bottom:1px solid rgba(148,163,184,0.12);display:flex;align-items:center;gap:8px;">
          <span style="font-weight:700;color:#e5e7eb;white-space:nowrap;">${tsStr}</span>
          <span style="color:#9ca3af;">• Lights</span>
          <span style="color:#9ca3af;">→</span>
          <span>${state}</span>
          <span style="color:#6b7280;margin-left:auto;">${reason}</span>
        </div>
      `;
    }).join('');
  }

  async function refreshLightsStatus() {
    try {
      const [relays, events, settings] = await Promise.all([
        getJSON('/api/relays/status').catch(() => ({})),
        getJSON('/api/relays/events?name=lights&last=50').catch(() => []),
        (() => {
          if (window.PollingManager && window.PollingManager.getSettings) {
            return window.PollingManager.getSettings().catch(() => ({}));
          }
          return getJSON('/api/settings').catch(() => ({}));
        })()
      ]);

      if (relays.relays && relays.relays.lights) {
        lightsState.is_on = !!relays.relays.lights.is_on;
      }
      lightsState.mode = relays.mode || 'manual';
      lightsState.estop = !!relays.estop;

      // Parse cooldown from relay info
      if (relays.relays && relays.relays.lights) {
        const info = relays.relays.lights;
        lightsState.cooldown_remaining = (info.cooldown_remaining || info.cooldown || 0);
      }

      // Get schedule window
      if (settings.today_window) {
        const windowEl = $('lights-window-kpi');
        if (windowEl) {
          windowEl.textContent = `${settings.today_window.on_time} → ${settings.today_window.off_time}`;
        }
      }

      lightsEvents = events;
      updateLightsUI();
      renderLightsEventLog(lightsEvents);
    } catch (e) {
      if (UI_VERBOSE) console.error('[Lights] refresh failed:', e);
    }
  }

  async function setMode(newMode) {
    try {
      await postJSON('/api/relays/mode', { mode: newMode });
      lightsState.mode = newMode;
      updateLightsUI();
      showToast(`Mode changed to ${newMode}`, 'success');
      setTimeout(() => refreshLightsStatus(), 300);
    } catch (e) {
      showToast('Failed to change mode: ' + e.message, 'error');
    }
  }

  async function toggleLights() {
    try {
      await postJSON('/api/relay/lights/toggle', {});
      if (window.pollingManager && window.pollingManager.invalidate) {
        window.pollingManager.invalidate('relays');
      }
      setTimeout(() => refreshLightsStatus(), 300);
    } catch (e) {
      showToast('Failed to toggle lights: ' + e.message, 'error');
    }
  }

  async function init() {
    // Attach mode buttons
    ['auto', 'manual', 'maintenance'].forEach(m => {
      const btn = $(`lights-mode-${m}`);
      if (btn) btn.addEventListener('click', () => setMode(m));
    });

    // Attach toggle button
    const toggleBtn = $('btnLightsToggle');
    if (toggleBtn) toggleBtn.addEventListener('click', toggleLights);

    // Initial refresh and polling
    refreshLightsStatus();
    setInterval(refreshLightsStatus, 30000); // Poll every 30 seconds

    // Sync mode from backend every 5s
    setInterval(async () => {
      try {
        const relays = await getJSON('/api/relays/status');
        if (relays.mode) lightsState.mode = relays.mode;
      } catch (e) {
        if (UI_VERBOSE) console.warn('[Lights] mode sync failed:', e);
      }
    }, 5000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
