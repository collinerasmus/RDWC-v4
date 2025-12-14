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
    // For lights with overnight schedules (e.g., 15:00-07:00), we need to count
    // the CURRENT cycle, not just today's calendar day. Find the most recent OFF
    // event and calculate from the previous ON to now.
    
    const normalized = events.map(e => ({
      ts: typeof e.ts === 'string' ? new Date(e.ts).getTime() / 1000 : e.ts,
      final: e.final
    })).sort((a, b) => a.ts - b.ts);

    let total = 0;
    let currentCycleStart = null;

    // Find the start of the current ON period (most recent ON event)
    for (let i = normalized.length - 1; i >= 0; i--) {
      if (normalized[i].final === true) {
        currentCycleStart = normalized[i].ts;
        break;
      }
    }

    // Calculate total from all complete ON/OFF pairs in the last 24 hours
    const last24h = Math.floor(Date.now() / 1000) - 86400;
    let lastOn = null;

    for (const evt of normalized) {
      if (evt.ts < last24h) continue;
      
      if (evt.final === true) {
        lastOn = evt.ts;
      } else if (lastOn) {
        total += evt.ts - lastOn;
        lastOn = null;
      }
    }

    // Add current ON duration if lights are currently ON
    if (currentCycleStart) {
      const currentDuration = Math.floor(Date.now() / 1000) - currentCycleStart;
      if (currentDuration > 0 && currentDuration < 86400) {
        total += currentDuration;
      }
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

    // Build event pairs with durations
    const eventPairs = [];
    let onEvent = null;
    
    for (let i = 0; i < events.length; i++) {
      const evt = events[i];
      const ts = typeof evt.ts === 'string' ? new Date(evt.ts).getTime() : evt.ts * 1000;
      
      if (evt.final === true) {
        onEvent = { ...evt, tsMs: ts };
      } else if (evt.final === false && onEvent) {
        const duration = (ts - onEvent.tsMs) / 1000; // seconds
        eventPairs.push({
          onTime: onEvent.tsMs,
          offTime: ts,
          duration,
          onReason: onEvent.reason,
          offReason: evt.reason
        });
        onEvent = null;
      }
    }
    
    // If still ON, calculate current duration
    if (onEvent && lightsState.is_on) {
      const duration = (Date.now() - onEvent.tsMs) / 1000;
      eventPairs.push({
        onTime: onEvent.tsMs,
        offTime: null,
        duration,
        onReason: onEvent.reason,
        offReason: null
      });
    }

    // Render pairs (most recent first)
    const recent = eventPairs.slice(0, 10);
    container.innerHTML = recent.map(pair => {
      const onD = new Date(pair.onTime);
      const onTime = onD.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const offTime = pair.offTime 
        ? new Date(pair.offTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
        : 'NOW';
      const duration = formatDuration(pair.duration);
      const isActive = !pair.offTime;
      const reason = pair.onReason || 'lights';
      
      // Single-row compact chip: ON time • OFF time • duration • reason
      const dot = '<span style="color:#4b5563;">•</span>';
      const segments = [
        `<span style="font-weight:700;">${onTime}</span>`,
        `<span style="color:#9ca3af;">→ ${offTime}</span>`,
        `<span style="color:#9ca3af;">${duration}</span>`,
        `<span style="color:#9ca3af;">${reason}</span>`
      ];

      return `<div style="margin-bottom:4px;padding:4px 6px;border-radius:4px;background:rgba(251,191,36,0.06);border-left:2px solid rgba(251,191,36,0.25);display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:var(--font-xs);color:#cbd5e1;">${segments.join(dot)}</div>`;
    }).join('');
    
    // Show raw events if no pairs
    if (recent.length === 0) {
      const rawRecent = events.slice(0, 20);
      container.innerHTML = rawRecent.map(evt => {
        const ts = typeof evt.ts === 'string' ? new Date(evt.ts).getTime() : evt.ts * 1000;
        const d = new Date(ts);
        const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const state = evt.final ? 'ON' : 'OFF';
        const color = evt.final ? '#22c55e' : '#ef4444';
        const reason = evt.reason || 'unknown';
        return `<div style="padding:4px 0;border-bottom:1px solid rgba(148,163,184,0.1);display:flex;justify-content:space-between;font-size:12px;">
          <span style="color:${color};font-weight:600;min-width:30px;">${state}</span>
          <span style="flex:1;text-align:right;padding:0 8px;">${time}</span>
          <span class="muted" style="min-width:80px;text-align:right;">${reason}</span>
        </div>`;
      }).join('');
    }
  }

  async function refreshLightsChart() {
    if (!lightsChart) return;

    try {
      // Use custom time range if set (from pan slider), otherwise use current time
      let startMs, endMs;
      if (customTimeRange) {
        startMs = customTimeRange.start;
        endMs = customTimeRange.end;
      } else {
        const now = Date.now();
        startMs = now - currentChartHours * 3600000;
        endMs = now;
      }
      
      const start = Math.floor(startMs / 1000);
      const end = Math.floor(endMs / 1000);

      const events = await getJSON(`/api/relays/events?name=lights&start=${start}&end=${end}`);
      
      if (!events || events.length === 0) {
        lightsChart.data.datasets[0].data = [];
        lightsChart.update('none');
        const totalEl = $('lights-chart-total');
        if (totalEl) totalEl.textContent = '0h 0m';
        return;
      }

      // Normalize timestamps
      const normalizedEvents = events.map(e => ({
        ts: typeof e.ts === 'string' ? new Date(e.ts).getTime() / 1000 : e.ts,
        final: e.final
      })).sort((a, b) => a.ts - b.ts);

      // Calculate total ON time in this window
      let windowTotal = 0;
      for (let i = 0; i < normalizedEvents.length - 1; i++) {
        if (normalizedEvents[i].final === true) {
          windowTotal += normalizedEvents[i + 1].ts - normalizedEvents[i].ts;
        }
      }
      // If last is ON, add time to end of window (not necessarily now)
      if (normalizedEvents[normalizedEvents.length - 1].final === true) {
        windowTotal += end - normalizedEvents[normalizedEvents.length - 1].ts;
      }

      // Update chart total display
      const totalEl = $('lights-chart-total');
      if (totalEl) {
        const hours = Math.floor(windowTotal / 3600);
        const mins = Math.floor((windowTotal % 3600) / 60);
        totalEl.textContent = `${hours}h ${mins}m`;
      }

      // Build step chart data with rectangles for ON periods
      const data = [];
      for (let i = 0; i < normalizedEvents.length; i++) {
        const evt = normalizedEvents[i];
        const state = evt.final ? 1 : 0;
        const ts = evt.ts * 1000;
        
        data.push({ x: ts, y: state });
        
        if (i < normalizedEvents.length - 1) {
          data.push({ x: normalizedEvents[i + 1].ts * 1000 - 1, y: state });
        } else {
          data.push({ x: endMs, y: state });
        }
      }

      lightsChart.data.datasets[0].data = data;
      lightsChart.options.scales.x.min = startMs;
      lightsChart.options.scales.x.max = endMs;
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
          stepped: 'before',
          borderColor: '#22c55e',
          backgroundColor: (context) => {
            const value = context.parsed?.y;
            if (value === 1) {
              return 'rgba(34,197,94,0.3)';
            }
            return 'rgba(148,163,184,0.05)';
          },
          segment: {
            borderColor: ctx => {
              return ctx.p0.parsed.y === 1 ? '#22c55e' : '#64748b';
            },
            borderWidth: ctx => {
              return ctx.p0.parsed.y === 1 ? 3 : 1;
            }
          },
          fill: {
            target: 'origin',
            above: 'rgba(34,197,94,0.25)',
            below: 'rgba(148,163,184,0.03)'
          },
          pointRadius: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: {
            display: true,
            position: 'top',
            align: 'end',
            labels: {
              color: '#9ca3af',
              font: { size: 11 },
              generateLabels: () => [
                {
                  text: '■ ON',
                  fillStyle: '#22c55e',
                  hidden: false,
                  lineWidth: 0
                },
                {
                  text: '■ OFF',
                  fillStyle: '#374151',
                  hidden: false,
                  lineWidth: 0
                }
              ]
            }
          },
          tooltip: {
            callbacks: {
              label: ctx => ctx.parsed.y === 1 ? '● Lights ON' : '○ Lights OFF'
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
              font: { size: 12, weight: 'bold' },
              callback: val => val === 1 ? '💡 ON' : '⚫ OFF'
            },
            grid: { color: 'rgba(148,163,184,0.1)' }
          }
        }
      }
    });

    // Expose chart to window for ChartControls integration
    window.lightsChart = lightsChart;
    refreshLightsChart();
  }

  // Expose chart instance and updater for ChartControls integration
  let customTimeRange = null; // Store custom time range for panning
  
  window.lightsChart = null;
  window.setLightsChartHours = (hours) => {
    currentChartHours = hours;
    customTimeRange = null; // Reset custom range when zoom changes
    refreshLightsChart();
  };
  window.setLightsChartRange = (startMs, endMs) => {
    customTimeRange = { start: startMs, end: endMs };
    refreshLightsChart();
  };

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
        
        // Track ON start time: if lights are ON, find the most recent ON event timestamp
        if (lightsState.is_on) {
          // Only update currentOnStart if not already set or if transitioning from OFF to ON
          if (!currentOnStart || !wasOn) {
            const lastOnEvent = events.find(e => e.final === true);
            if (lastOnEvent) {
              const ts = typeof lastOnEvent.ts === 'string' 
                ? new Date(lastOnEvent.ts).getTime() 
                : lastOnEvent.ts * 1000;
              currentOnStart = ts;
            } else if (!currentOnStart) {
              // No ON event found but lights are ON - use current time as fallback
              currentOnStart = Date.now();
            }
          }
        } else {
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
    // Note: Chart controls now managed by chart_adapter.js (unified ChartControls)
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
