/**
 * Intelligent Lights Control UI - Grow Light Scheduler (Edge-Only)
 * Chart, duration display, midnight-safe window calculation
 */
(() => {
  const UI_VERBOSE = false;
  let lightsChart = null;
  let currentChartHours = 24;

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

  const $ = (id) => document.getElementById(id);

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

  let lightsState = {
    is_on: false,
    estop: false,
    cooldown_remaining: 0,
  };

  let lightsEvents = [];
  let durationHours = 0;

  function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '—';
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

    if (lightsState.cooldown_remaining > 0) {
      chip.textContent = 'WAITING';
      chip.className = 'ui-status-chip warning';
      chip.title = `Cooldown ${Math.ceil(lightsState.cooldown_remaining)}s`;
      return;
    }

    chip.textContent = 'RUNNING';
    chip.className = 'ui-status-chip success';
    chip.title = 'Schedule automation active';
  }

  function updateLightsUI(settings) {
    console.log('[Lights] updateLightsUI called with settings:', settings);
    
    // State badge
    const badge = $('lights-status');
    if (badge) {
      badge.textContent = lightsState.is_on ? 'ON' : 'OFF';
      badge.className = 'bop-status-badge ' + (lightsState.is_on ? 'on' : 'off');
    }

    // Duration KPI - show hours value
    const durationEl = $('lights-sched-kpi');
    if (durationEl) {
      if (durationHours > 0) {
        durationEl.textContent = `${durationHours}h`;
        console.log('[Lights] Duration displayed:', durationEl.textContent);
      } else {
        durationEl.textContent = '—';
      }
    }

    // Window KPI - calculate with midnight rollover
    const windowEl = $('lights-window-kpi');
    if (windowEl && settings) {
      const onTime = settings.lights_on_time || '';
      const hours = parseFloat(settings.lights_duration_hours) || 0;
      
      if (onTime && hours > 0) {
        const [onH, onM] = onTime.split(':').map(Number);
        const onMinutes = onH * 60 + onM;
        const offMinutes = (onMinutes + hours * 60) % 1440; // wrap at 24h
        const offH = Math.floor(offMinutes / 60);
        const offM = offMinutes % 60;
        const offTime = `${String(offH).padStart(2, '0')}:${String(offM).padStart(2, '0')}`;
        windowEl.textContent = `${onTime} → ${offTime}`;
        console.log('[Lights] Window displayed:', windowEl.textContent);
      } else {
        windowEl.textContent = '—';
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

    // Toggle button
    const toggleBtn = $('btnLightsToggle');
    if (toggleBtn) {
      toggleBtn.disabled = lightsState.estop;
      toggleBtn.style.opacity = lightsState.estop ? '0.6' : '1';
      toggleBtn.style.cursor = lightsState.estop ? 'not-allowed' : 'pointer';
    }

    updateLightsHealth();
  }

  function renderLightsEventLog(events) {
    const listEl = $('lights-events-list');
    if (!listEl) return;

    if (!events || events.length === 0) {
      listEl.innerHTML = '<div style="text-align:center;padding:16px;color:#94a3b8;">No events yet.</div>';
      return;
    }

    listEl.innerHTML = events.slice(-20).reverse().map(evt => {
      const ts = new Date(evt.ts * 1000);
      const tsStr = ts.toISOString().replace('T', ' ').split('.')[0];
      const state = evt.final ? '<span style="color:#22c55e;font-weight:600;">ON</span>' : '<span style="color:#ef4444;font-weight:600;">OFF</span>';
      const reason = evt.reason ? ` · ${evt.reason}` : '';
      return `
        <div style="padding:6px 4px;border-bottom:1px solid rgba(148,163,184,0.12);display:flex;gap:8px;">
          <span style="font-weight:700;color:#e5e7eb;white-space:nowrap;">${tsStr}</span>
          <span style="color:#9ca3af;">→ Lights ${state}${reason}</span>
        </div>
      `;
    }).join('');
  }

  async function refreshLightsChart() {
    if (!lightsChart) {
      console.warn('[Lights] Chart not initialized, skipping refresh');
      return;
    }

    try {
      const now = Date.now();
      const hoursAgo = currentChartHours;
      const start = Math.floor((now - hoursAgo * 3600000) / 1000);
      const end = Math.floor(now / 1000);

      console.log('[Lights] Fetching chart data:', {start, end, hours: hoursAgo});
      const events = await getJSON(`/api/relays/events?name=lights&start=${start}&end=${end}`);
      console.log('[Lights] Fetched events:', events.length);
      
      if (!events || events.length === 0) {
        lightsChart.data.datasets[0].data = [];
        lightsChart.update('none');
        console.log('[Lights] No events, chart cleared');
        return;
      }

      // Build timeline segments
      const segments = [];
      for (let i = 0; i < events.length - 1; i++) {
        const evt = events[i];
        const next = events[i + 1];
        segments.push({
          x: evt.ts * 1000,
          y: evt.final ? 1 : 0,
          next_x: next.ts * 1000
        });
      }

      // Last segment extends to now
      const last = events[events.length - 1];
      segments.push({
        x: last.ts * 1000,
        y: last.final ? 1 : 0,
        next_x: now
      });

      lightsChart.data.datasets[0].data = segments;
      lightsChart.options.scales.x.min = now - hoursAgo * 3600000;
      lightsChart.options.scales.x.max = now;
      lightsChart.update('none');
      console.log('[Lights] Chart updated with', segments.length, 'segments');

    } catch (e) {
      console.error('[Lights] chart refresh failed:', e);
    }
  }

  function initLightsChart() {
    const canvas = $('lightsChart');
    if (!canvas) {
      console.warn('[Lights] Chart canvas not found');
      return;
    }
    
    if (!window.Chart) {
      console.error('[Lights] Chart.js not loaded');
      return;
    }

    console.log('[Lights] Initializing chart');
    const ctx = canvas.getContext('2d');
    lightsChart = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label: 'Lights',
          data: [],
          stepped: 'before',
          borderColor: '#fbbf24',
          backgroundColor: 'rgba(251,191,36,0.15)',
          fill: true,
          pointRadius: 0,
          borderWidth: 2,
          segment: {
            borderColor: ctx => ctx.p0.parsed.y === 1 ? '#22c55e' : '#ef4444',
            backgroundColor: ctx => ctx.p0.parsed.y === 1 ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.08)'
          }
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ctx.parsed.y === 1 ? 'ON' : 'OFF'
            }
          }
        },
        scales: {
          x: {
            type: 'time',
            time: { displayFormats: { hour: 'HH:mm', minute: 'HH:mm' } },
            grid: { color: 'rgba(148,163,184,0.1)' },
            ticks: { color: '#9ca3af' }
          },
          y: {
            min: 0,
            max: 1,
            ticks: {
              stepSize: 1,
              color: '#9ca3af',
              callback: (val) => val === 1 ? 'ON' : 'OFF'
            },
            grid: { color: 'rgba(148,163,184,0.1)' }
          }
        }
      }
    });

    console.log('[Lights] Chart created');
    refreshLightsChart();
  }

  function createChartControls() {
    const container = $('lights-chart-controls');
    if (!container) return;

    container.innerHTML = `
      <div style="display:flex;gap:8px;margin-top:12px;align-items:center;justify-content:center;flex-wrap:wrap;">
        <button class="chart-zoom-btn" data-hours="6">6h</button>
        <button class="chart-zoom-btn active" data-hours="24">24h</button>
        <button class="chart-zoom-btn" data-hours="72">3d</button>
        <button class="chart-zoom-btn" data-hours="168">7d</button>
      </div>
    `;

    container.querySelectorAll('.chart-zoom-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        currentChartHours = parseInt(btn.dataset.hours);
        container.querySelectorAll('.chart-zoom-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        refreshLightsChart();
      });
    });
  }

  async function refreshLightsStatus() {
    try {
      const [relays, events, settings] = await Promise.all([
        getJSON('/api/relays/status').catch(() => ({})),
        getJSON('/api/relays/events?name=lights&last=50').catch(() => []),
        getJSON('/api/settings').catch(() => ({}))
      ]);

      if (relays.relays && relays.relays.lights) {
        lightsState.is_on = !!relays.relays.lights.is_on;
        lightsState.cooldown_remaining = relays.relays.lights.cooldown_remaining || 0;
      }
      lightsState.estop = !!relays.estop;

      durationHours = settings.lights_duration_hours || 0;

      lightsEvents = events;
      updateLightsUI(settings);
      renderLightsEventLog(lightsEvents);

    } catch (e) {
      if (UI_VERBOSE) console.error('[Lights] refresh failed:', e);
    }
  }

  async function toggleLights() {
    try {
      await postJSON('/api/relay/lights/toggle', {});
      showToast('Lights toggled', 'success');
      setTimeout(() => refreshLightsStatus(), 300);
    } catch (e) {
      showToast('Failed to toggle lights: ' + e.message, 'error');
    }
  }

  async function saveSettings() {
    try {
      const onTime = $('lightsOnTime').value;
      
      if (!onTime) {
        showToast('Please enter lights on time', 'warning');
        return;
      }

      await postJSON('/api/settings', {
        lights_on_time: onTime
      });

      showToast('Settings saved', 'success');
      setTimeout(() => refreshLightsStatus(), 300);
    } catch (e) {
      showToast('Failed to save settings: ' + e.message, 'error');
    }
  }

  async function loadSettings() {
    try {
      const settings = await getJSON('/api/settings');
      console.log('[Lights] Loaded settings:', settings);
      
      const onTimeInput = $('lightsOnTime');
      if (onTimeInput && settings.lights_on_time) {
        onTimeInput.value = settings.lights_on_time;
      }

      durationHours = parseFloat(settings.lights_duration_hours) || 0;
      console.log('[Lights] Duration hours:', durationHours);
      updateLightsUI(settings);

    } catch (e) {
      console.error('[Lights] load settings failed:', e);
    }
  }

  async function init() {
    console.log('[Lights] Initializing lights controller');
    
    const toggleBtn = $('btnLightsToggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', toggleLights);
      console.log('[Lights] Toggle button wired');
    }

    const saveBtn = $('btnSaveLightsSettings');
    if (saveBtn) {
      saveBtn.addEventListener('click', saveSettings);
      console.log('[Lights] Save button wired');
    }

    await loadSettings();
    initLightsChart();
    createChartControls();
    await refreshLightsStatus();

    setInterval(refreshLightsStatus, 30000);
    setInterval(refreshLightsChart, 60000);
    
    console.log('[Lights] Initialization complete');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
