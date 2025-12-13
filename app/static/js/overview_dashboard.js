// Overview Dashboard Controller - Unified KPI display for System tab
// Fetches data from all subsystems and displays in a clean dashboard layout
(function() {
  'use strict';

  const el = (id) => document.getElementById(id);
  const getJSON = async (url) => {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  };

  let refreshTimer = null;
  const REFRESH_INTERVAL = 5000; // 5s for live dashboard feel

  // Main refresh function - fetches all data in parallel
  async function refreshDashboard() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    const refreshEl = el('ov-refresh-time');
    if (refreshEl) refreshEl.textContent = `Updated: ${timeStr}`;

    // Fetch all data in parallel for speed
    try {
      const [sensors, phStatus, ecStatus, tempStatus, relays, autoStatus, schedule] = await Promise.all([
        getJSON('/api/sensors').catch(() => null),
        getJSON('/api/ph/status').catch(() => null),
        getJSON('/api/ec/status').catch(() => null),
        getJSON('/api/temperature/status').catch(() => null),
        getJSON('/api/relays/status').catch(() => null),
        getJSON('/api/auto/status').catch(() => null),
        getJSON('/api/schedule/current_week').catch(() => null)
      ]);

      updateSensorKPIs(sensors);
      updatePhKPIs(phStatus);
      updateEcKPIs(ecStatus);
      updateTempKPIs(tempStatus);
      updateRelayStatuses(relays);
      updateScheduleKPIs(schedule);
      updateSystemStatus(relays, autoStatus);
    } catch (e) {
      console.error('[OverviewDashboard] Refresh error:', e);
    }
  }

  function updateSensorKPIs(sensors) {
    if (!sensors) return;
    
    // Primary sensor readings
    const phEl = el('ov-kpi-ph');
    const ecEl = el('ov-kpi-ec');
    const tempEl = el('ov-kpi-temp');
    
    if (phEl) phEl.textContent = sensors.ph !== null && sensors.ph !== undefined ? sensors.ph.toFixed(2) : '—';
    if (ecEl) ecEl.textContent = sensors.ec_mscm !== null && sensors.ec_mscm !== undefined ? sensors.ec_mscm.toFixed(2) : '—';
    if (tempEl) tempEl.textContent = sensors.temperature_c !== null && sensors.temperature_c !== undefined ? sensors.temperature_c.toFixed(1) : '—';
    
    // Status indicator
    const statusEl = el('ov-sensors-status-text');
    if (statusEl) {
      const age = sensors.ts ? (Date.now() / 1000 - sensors.ts) : 999;
      const online = sensors.online && age < 90;
      
      statusEl.textContent = online ? 'ONLINE' : 'OFFLINE';
      statusEl.className = 'ui-status-chip ' + (online ? 'success' : 'error');
      statusEl.style.fontSize = '0.6rem';
    }
  }

  function updatePhKPIs(status) {
    if (!status) return;
    
    const currentEl = el('ov-kpi-ph-current');
    const setpointEl = el('ov-kpi-ph-setpoint');
    const pumpEl = el('ov-kpi-ph-pump');
    const healthEl = el('ov-ph-health');
    const statusChipEl = el('ov-ph-status');
    
    if (currentEl) currentEl.textContent = status.ph !== null && status.ph !== undefined ? status.ph.toFixed(2) : '—';
    
    // Setpoint from targets midpoint
    if (setpointEl && status.targets) {
      const setpoint = ((status.targets.low + status.targets.high) / 2).toFixed(2);
      setpointEl.textContent = setpoint;
    }
    
    // Pump status (dosing/idle/locked)
    if (pumpEl) {
      const auto = status.auto || {};
      const holding = auto.holding_reason;
      if (holding === 'cooldown') {
        pumpEl.textContent = 'Cooldown';
        pumpEl.style.color = '#f59e0b';
      } else if (holding === 'in_range') {
        pumpEl.textContent = 'In Range';
        pumpEl.style.color = '#16a34a';
      } else if (auto.enabled) {
        pumpEl.textContent = 'Auto Ready';
        pumpEl.style.color = '#3b82f6';
      } else {
        pumpEl.textContent = 'Idle';
        pumpEl.style.color = '#94a3b8';
      }
    }
    
    // Health chip
    if (healthEl && status.guards) {
      const g = status.guards;
      const hardKeys = ['estop', 'safe_off', 'sensor_stale', 'reservoir'];
      const softKeys = ['interval', 'daily_cap'];
      const hardActive = hardKeys.some(k => !!g[k]);
      const softActive = softKeys.some(k => !!g[k]);
      
      healthEl.textContent = hardActive ? 'BLOCKED' : (softActive ? 'WAIT' : 'OK');
      healthEl.className = 'ui-status-chip ' + (hardActive ? 'error' : (softActive ? 'warning' : 'success'));
      healthEl.style.fontSize = '0.6rem';
    }
    
    // Status chip (auto/manual)
    if (statusChipEl && status.auto) {
      const enabled = status.auto.enabled;
      statusChipEl.textContent = enabled ? 'AUTO' : 'MANUAL';
      statusChipEl.className = 'ui-status-chip ' + (enabled ? 'success' : 'neutral');
      statusChipEl.style.fontSize = '0.6rem';
    }
  }

  function updateEcKPIs(status) {
    if (!status) return;
    
    const currentEl = el('ov-kpi-ec-current');
    const setpointEl = el('ov-kpi-ec-setpoint');
    const pumpEl = el('ov-kpi-ec-pump');
    const healthEl = el('ov-ec-health');
    const statusChipEl = el('ov-ec-status');
    
    if (currentEl) currentEl.textContent = status.ec_mscm !== null && status.ec_mscm !== undefined ? status.ec_mscm.toFixed(2) : '—';
    
    // Setpoint from targets midpoint
    if (setpointEl && status.targets) {
      const setpoint = ((status.targets.low + status.targets.high) / 2).toFixed(2);
      setpointEl.textContent = setpoint;
    }
    
    // Pump status
    if (pumpEl) {
      const auto = status.auto || {};
      const holding = auto.holding_reason;
      if (holding === 'cooldown') {
        pumpEl.textContent = 'Cooldown';
        pumpEl.style.color = '#f59e0b';
      } else if (holding === 'in_range') {
        pumpEl.textContent = 'In Range';
        pumpEl.style.color = '#16a34a';
      } else if (auto.enabled) {
        pumpEl.textContent = 'Auto Ready';
        pumpEl.style.color = '#3b82f6';
      } else {
        pumpEl.textContent = 'Idle';
        pumpEl.style.color = '#94a3b8';
      }
    }
    
    // Health chip
    if (healthEl && status.guards) {
      const g = status.guards;
      const hardKeys = ['estop', 'safe_off', 'sensor_stale', 'reservoir'];
      const softKeys = ['interval', 'daily_cap', 'mix_lock'];
      const hardActive = hardKeys.some(k => !!g[k]);
      const softActive = softKeys.some(k => !!g[k]);
      
      healthEl.textContent = hardActive ? 'BLOCKED' : (softActive ? 'WAIT' : 'OK');
      healthEl.className = 'ui-status-chip ' + (hardActive ? 'error' : (softActive ? 'warning' : 'success'));
      healthEl.style.fontSize = '0.6rem';
    }
    
    // Status chip
    if (statusChipEl && status.auto) {
      const enabled = status.auto.enabled;
      statusChipEl.textContent = enabled ? 'AUTO' : 'MANUAL';
      statusChipEl.className = 'ui-status-chip ' + (enabled ? 'success' : 'neutral');
      statusChipEl.style.fontSize = '0.6rem';
    }
  }

  function updateTempKPIs(status) {
    if (!status) return;
    
    const waterEl = el('ov-kpi-water-temp');
    const targetEl = el('ov-kpi-target-temp');
    const healthEl = el('ov-temperature-health');
    const statusChipEl = el('ov-temperature-status');
    
    if (waterEl) waterEl.textContent = status.temperature_c !== null && status.temperature_c !== undefined ? status.temperature_c.toFixed(1) + '°C' : '—';
    if (targetEl) targetEl.textContent = status.target_c !== null && status.target_c !== undefined ? status.target_c.toFixed(1) + '°C' : '—';
    
    // Health chip
    if (healthEl) {
      healthEl.textContent = 'OK';
      healthEl.className = 'ui-status-chip success';
      healthEl.style.fontSize = '0.6rem';
    }
    
    // Status chip
    if (statusChipEl && status.auto !== undefined) {
      const enabled = status.auto;
      statusChipEl.textContent = enabled ? 'AUTO' : 'MANUAL';
      statusChipEl.className = 'ui-status-chip ' + (enabled ? 'success' : 'neutral');
      statusChipEl.style.fontSize = '0.6rem';
    }
  }

  function updateRelayStatuses(relays) {
    if (!relays || !relays.relays) return;
    
    const r = relays.relays;
    
    // Temperature relays
    const chillerEl = el('ov-temperature');
    const tempPumpEl = el('ov-temperature-pump');
    if (chillerEl && r.chiller) {
      chillerEl.textContent = r.chiller.is_on ? 'ON' : 'OFF';
      chillerEl.classList.toggle('relay-on', r.chiller.is_on);
      chillerEl.classList.toggle('relay-off', !r.chiller.is_on);
    }
    if (tempPumpEl && r.temperature_pump) {
      tempPumpEl.textContent = r.temperature_pump.is_on ? 'ON' : 'OFF';
      tempPumpEl.classList.toggle('relay-on', r.temperature_pump.is_on);
      tempPumpEl.classList.toggle('relay-off', !r.temperature_pump.is_on);
    }
    
    // Main pump
    const mainPumpEl = el('ov-main-pump');
    const mainPumpHealthEl = el('ov-main-pump-health');
    if (mainPumpEl && r.main_pump) {
      mainPumpEl.textContent = r.main_pump.is_on ? 'ON' : 'OFF';
      mainPumpEl.classList.toggle('relay-on', r.main_pump.is_on);
      mainPumpEl.classList.toggle('relay-off', !r.main_pump.is_on);
    }
    if (mainPumpHealthEl) {
      mainPumpHealthEl.textContent = 'OK';
      mainPumpHealthEl.className = 'ui-status-chip success';
      mainPumpHealthEl.style.fontSize = '0.6rem';
    }
    
    // Lights
    const lightsEl = el('ov-lights');
    const lightsHealthEl = el('ov-lights-health');
    if (lightsEl && r.lights) {
      lightsEl.textContent = r.lights.is_on ? 'ON' : 'OFF';
      lightsEl.classList.toggle('relay-on', r.lights.is_on);
      lightsEl.classList.toggle('relay-off', !r.lights.is_on);
    }
    if (lightsHealthEl) {
      lightsHealthEl.textContent = 'OK';
      lightsHealthEl.className = 'ui-status-chip success';
      lightsHealthEl.style.fontSize = '0.6rem';
    }
  }

  function updateScheduleKPIs(schedule) {
    if (!schedule) return;
    
    const weekEl = el('ov-schedule-week');
    const phaseEl = el('ov-schedule-phase');
    
    if (weekEl) {
      weekEl.textContent = `Week ${schedule.week_number || '—'}`;
    }
    
    if (phaseEl) {
      const phase = schedule.phase || '—';
      phaseEl.textContent = phase;
      // Color-code phase
      const phaseColors = {
        'seedling': '#86efac',
        'vegetative': '#4ade80',
        'early_flower': '#fb923c',
        'mid_flower': '#f97316',
        'late_flower': '#dc2626',
        'flush': '#3b82f6'
      };
      const color = phaseColors[phase.toLowerCase()] || '#94a3b8';
      phaseEl.style.color = color;
    }
  }

  function updateSystemStatus(relays, autoStatus) {
    // Global Auto badge
    const autoBadgeEl = el('ov-auto-badge');
    if (autoBadgeEl && autoStatus) {
      const globalAuto = autoStatus.global_auto;
      autoBadgeEl.textContent = globalAuto ? 'AUTO' : 'MANUAL';
      autoBadgeEl.className = 'ui-status-chip ' + (globalAuto ? 'success' : 'neutral');
      autoBadgeEl.style.fontSize = 'var(--font-xs)';
    }
    
    // System health
    const healthEl = el('ov-system-health');
    if (healthEl) {
      const estop = relays && relays.estop;
      healthEl.textContent = estop ? 'E-STOP' : 'OK';
      healthEl.className = 'ui-status-chip ' + (estop ? 'error' : 'success');
      healthEl.style.fontSize = '0.6rem';
    }
    
    // E-STOP badge
    const estopBadgeEl = el('ov-estop-badge');
    if (estopBadgeEl && relays) {
      const estop = relays.estop;
      estopBadgeEl.textContent = estop ? 'ACTIVE' : 'OK';
      estopBadgeEl.className = 'ui-status-chip ' + (estop ? 'error' : 'success');
      estopBadgeEl.style.fontSize = '0.6rem';
    }
  }

  function init() {
    // Initial refresh
    refreshDashboard();
    
    // Set up periodic refresh
    refreshTimer = setInterval(refreshDashboard, REFRESH_INTERVAL);
    
    console.log('[OverviewDashboard] Initialized with 5s refresh');
  }

  function cleanup() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  // Auto-init when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose cleanup for tab switching
  window.overviewDashboard = { init, cleanup, refresh: refreshDashboard };
})();
