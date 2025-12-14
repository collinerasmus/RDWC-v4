/**
 * Lights Control UI - Grow Light Automation
 * Features: ON/OFF chart, totalizer (current/daily), schedule management
 */
(() => {
  'use strict';

  let lightsChart = null;
  let currentChartHours = 24;
  let currentOnStart = null;
  let todayTotalSeconds = 0;
  let totalizerInterval = null;

  // API helpers
  async function getJSON(url) {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  async function postJSON(url, body = {}) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
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

  let durationHours = 0;

  function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '0m';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  function updateLightsHealth() {
    const chip = $('lights-health-indicator');
    if (!chip) return;

    if (lightsState.estop) {
      chip.textContent = 'BLOCKED';
      chip.className = 'ui-status-chip error';
      chip.title = 'E-STOP active';
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
    chip.title = 'Schedule active';
  }

  function updateTotalizer() {
    const currentEl = $('lights-current-duration');
    const todayEl = $('lights-today-total');

    if (!currentEl || !todayEl) return;

    if (lightsState.is_on && currentOnStart) {
      const elapsed = Math.floor((Date.now() - currentOnStart) / 1000);
      currentEl.textContent = formatDuration(elapsed);
    } else {
      currentEl.textContent = '—';
    }

    todayEl.textContent = formatDuration(todayTotalSeconds);
  }

  function startTotalizerUpdates() {
    if (totalizerInterval) clearInterval(totalizerInterval);
    totalizerInterval = setInterval(updateTotalizer, 1000);
  }

  function calculateTodayTotal(events) {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const todayStartTs = todayStart.getTime() / 1000;

    const todayEvents = events.filter(e => e.ts >= todayStartTs);
    let total = 0;
    let lastOn = null;

    for (const evt of todayEvents) {
      if (evt.final) {
        lastOn = evt.ts;
      } else if (lastOn) {
        total += evt.ts - lastOn;
        lastOn = null;
      }
    }

    // If still ON, add time to now
    if (lastOn) {
      total += Math.floor(Date.now() / 1000) - lastOn;
    }

    todayTotalSeconds = total;
  }

  function updateLightsUI(settings) {
    const badge = $('lights-status');
    if (badge) {
      badge.textContent = lightsState.is_on ? 'ON' : 'OFF';
      badge.className = 'bop-status-badge ' + (lightsState.is_on ? 'on' : 'off');
    }

    const durationEl = $('lights-duration-kpi');
    if (durationEl) {
      durationEl.textContent = durationHours > 0 ? `${durationHours}h` : '—';
    }

    const windowEl = $('lights-window-kpi');
    if (windowEl && settings?.root) {
      const onTime = settings.root.lights_on_time || '';
      const hours = parseFloat(settings.root.lights_duration_hours) || 0;
      
      if (onTime && hours > 0) {
        const [onH, onM] = onTime.split(':').map(Number);
        const onMinutes = onH * 60 + onM;
        const offMinutes = (onMinutes + hours * 60) % 1440;
        const offH = Math.floor(offMinutes / 60);
        const offM = offMinutes % 60;
        const offTime = `${String(offH).padStart(2, '0')}:${String(offM).padStart(2, '0')}`;
        windowEl.textContent = `${onTime} → ${offTime}`;
      } else {
        windowEl.textContent = '—';
      }
    }

    const cooldownEl = $('lights-cooldown-display');
    if (cooldownEl) {
      if (lightsState.cooldown_remaining > 0) {
        cooldownEl.textContent = `⏱️ Cooldown: ${Math.ceil(lightsState.cooldown_remaining)}s remaining`;
        cooldownEl.style.display = 'block';
      } else {
        cooldownEl.style.display = 'none';
      }
    }

    updateLightsHealth();
    updateTotalizer();
  }

  function renderLightsEventLog(events) {
    const container = $('lights-events-list');
    if (!container) return;

    if (!events || events.length === 0) {
      container.innerHTML = '<div class="muted" style="padding:8px;">No events</div>';
      return;
    }

    const recent = events.slice(0, 20);
    container.innerHTML = recent.map(evt => {
      const d = new Date(evt.ts * 1000);
      const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const state = evt.final ? 'ON' : 'OFF';
      const color = evt.final ? '#22c55e' : '#ef4444';
      const reason = evt.reason || 'unknown';
      return `<div style="padding:4px 0;border-bottom:1px solid rgba(148,163,184,0.1);display:flex;justify-content:space-between;">
        <span style="color:${color};font-weight:600;">${state}</span>
        <span>${time}</span>
        <span class="muted">${reason}</span>
      </div>`;
    }).join('');
  }

  async function refreshLightsChart() {
    if (!lightsChart) return;

    try {
      const now = Date.now();
      const start = Math.floor((now - currentChartHours * 3600000) / 1000);
      const end = Math.floor(now / 1000);

      const events = await getJSON(`/api/relays/events?name=lights&start=${start}&end=${end}`);
      
      if (!events || events.length === 0) {
        lightsChart.data.datasets[0].data = [];
        lightsChart.update('none');
        return;
      }

      // Build step chart data
      const data = [];
      for (let i = 0; i < events.length; i++) {
        const evt = events[i];
        const state = evt.final ? 1 : 0;
        const ts = evt.ts * 1000;
        
        data.push({ x: ts, y: state });
        
        // Add next point if not last
        if (i < events.length - 1) {
          data.push({ x: events[i + 1].ts * 1000 - 1, y: state });
        } else {
          data.push({ x: now, y: state });
        }
      }

      lightsChart.data.datasets[0].data = data;
      lightsChart.options.scales.x.min = now - currentChartHours * 3600000;
      lightsChart.options.scales.x.max = now;
      lightsChart.update('none');

    } catch (e) {
      console.error('[Lights] Chart refresh failed:', e);
    }
  }

  function initLightsChart() {
    const canvas = $('lightsChart');
    if (!canvas || !window.Chart) return;

    const ctx = canvas.getContext('2d');
    lightsChart = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label: 'Lights State',
          data: [],
          stepped: false,
          borderColor: '#fbbf24',
          backgroundColor: 'rgba(251,191,36,0.2)',
          fill: true,
          pointRadius: 0,
          borderWidth: 2,
          segment: {
            borderColor: ctx => {
              const y = ctx.p0.parsed.y;
              return y === 1 ? '#22c55e' : '#ef4444';
            },
            backgroundColor: ctx => {
              const y = ctx.p0.parsed.y;
              return y === 1 ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.1)';
            }
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
              label: ctx => ctx.parsed.y === 1 ? '● ON' : '○ OFF'
            }
          }
        },
        scales: {
          x: {
            type: 'time',
            time: {
              displayFormats: { hour: 'HH:mm', minute: 'HH:mm' }
            },
            grid: { color: 'rgba(148,163,184,0.1)' },
            ticks: { color: '#9ca3af' }
          },
          y: {
            min: 0,
            max: 1,
            ticks: {
              stepSize: 1,
              color: '#9ca3af',
              callback: val => val === 1 ? 'ON' : 'OFF'
            },
            grid: { color: 'rgba(148,163,184,0.1)' }
          }
        }
      }
    });

    refreshLightsChart();
  }

  function createChartControls() {
    const container = $('lights-chart-controls');
    if (!container) return;

    container.innerHTML = `
      <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:12px;">
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
        getJSON('/api/relays/events?name=lights&last=100').catch(() => []),
        getJSON('/api/settings').catch(() => ({}))
      ]);

      if (relays.relays?.lights) {
        const wasOn = lightsState.is_on;
        lightsState.is_on = !!relays.relays.lights.is_on;
        lightsState.cooldown_remaining = relays.relays.lights.cooldown_remaining || 0;
        
        // Track ON start time
        if (lightsState.is_on && !wasOn && events.length > 0) {
          const lastOn = events.find(e => e.final);
          if (lastOn) currentOnStart = lastOn.ts * 1000;
        } else if (!lightsState.is_on) {
          currentOnStart = null;
        }
      }

      lightsState.estop = !!relays.estop;
      durationHours = parseFloat(settings.root?.lights_duration_hours) || 0;

      calculateTodayTotal(events);
      updateLightsUI(settings);
      renderLightsEventLog(events);

    } catch (e) {
      console.error('[Lights] Refresh failed:', e);
    }
  }

  async function toggleLights() {
    try {
      await postJSON('/api/relay/lights/toggle', {});
      showToast('Lights toggled', 'success');
      setTimeout(() => refreshLightsStatus(), 300);
    } catch (e) {
      showToast('Toggle failed: ' + e.message, 'error');
    }
  }

  async function saveSettings() {
    try {
      const onTime = $('lightsOnTime')?.value;
      if (!onTime) {
        showToast('Enter lights on time', 'warning');
        return;
      }

      await postJSON('/api/settings', { lights_on_time: onTime });
      showToast('Settings saved', 'success');
      setTimeout(() => refreshLightsStatus(), 300);
    } catch (e) {
      showToast('Save failed: ' + e.message, 'error');
    }
  }

  async function loadSettings() {
    try {
      const settings = await getJSON('/api/settings');
      const onTimeInput = $('lightsOnTime');
      
      if (onTimeInput) {
        // Default to sunset (18:55 for Pretoria) if not set
        onTimeInput.value = settings.root?.lights_on_time || '18:55';
      }

      durationHours = parseFloat(settings.root?.lights_duration_hours) || 0;
      updateLightsUI(settings);

    } catch (e) {
      console.error('[Lights] Load failed:', e);
    }
  }

  async function init() {
    const toggleBtn = $('btnLightsToggle');
    if (toggleBtn) toggleBtn.addEventListener('click', toggleLights);

    const saveBtn = $('btnSaveLightsSettings');
    if (saveBtn) saveBtn.addEventListener('click', saveSettings);

    await loadSettings();
    await refreshLightsStatus();
    
    initLightsChart();
    createChartControls();
    startTotalizerUpdates();

    // Periodic refresh
    setInterval(() => {
      refreshLightsStatus();
      refreshLightsChart();
    }, 10000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
