// system_info.js - System Information Tab Controller
// Fetches and displays comprehensive system info from /api/system/info

(function() {
  'use strict';

  let refreshInterval = null;
  const REFRESH_INTERVAL_MS = 30000; // 30 seconds (increased from 10s)

  // Format bytes to human-readable size
  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
  }

  // Format seconds to human-readable uptime
  function formatUptime(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    const parts = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    
    return parts.length > 0 ? parts.join(' ') : '< 1m';
  }

  // Format timestamp to local date/time
  function formatTimestamp(ts) {
    if (!ts) return '—';
    const date = new Date(ts * 1000);
    return date.toLocaleString();
  }

  // Update refresh indicator status
  function updateRefreshIndicator(success) {
    const indicator = document.getElementById('sys-info-refresh-indicator');
    if (!indicator) return;
    
    if (success) {
      indicator.className = 'ui-status-chip success';
      indicator.textContent = 'Live';
      indicator.title = 'Auto-refresh every 10s';
    } else {
      indicator.className = 'ui-status-chip error';
      indicator.textContent = 'Error';
      indicator.title = 'Failed to fetch system info';
    }
  }

  // Populate Pi Information section
  function populatePiInfo(data) {
    const el = (id, text) => {
      const elem = document.getElementById(id);
      if (elem) elem.textContent = text;
    };

    el('pi-cpu', data.cpu_percent !== null && data.cpu_percent !== undefined ? `${data.cpu_percent.toFixed(1)}%` : '—');
    el('pi-cpu-freq', data.cpu_freq_mhz ? `${data.cpu_freq_mhz.toFixed(0)} MHz` : '—');
    el('pi-cpu-temp', data.temperature_c ? `${data.temperature_c.toFixed(1)}°C` : '—');
    if (data.load_avg && Array.isArray(data.load_avg)) {
      el('pi-load', data.load_avg.map(v => v.toFixed(2)).join(' / '));
    } else {
      el('pi-load', '—');
    }
    el('pi-gov', data.cpu_governor || '—');
    
    // Memory from direct properties (not nested) - split into 3 blocks
    if (data.memory_total_mb) {
      const total = data.memory_total_mb * 1024 * 1024; // Convert MB to bytes
      const used = data.memory_used_mb * 1024 * 1024;
      const pct = data.memory_percent ? data.memory_percent.toFixed(1) : 0;
      el('pi-memory-used', formatBytes(used));
      el('pi-memory-total', formatBytes(total));
      el('pi-memory-pct', `${pct}%`);
    } else {
      el('pi-memory-used', '—');
      el('pi-memory-total', '—');
      el('pi-memory-pct', '—');
    }
    
    // Disk from direct properties (not nested) - split into 3 blocks
    if (data.disk_total_gb) {
      const total = data.disk_total_gb * 1024 * 1024 * 1024; // Convert GB to bytes
      const used = data.disk_used_gb * 1024 * 1024 * 1024;
      const pct = data.disk_percent ? data.disk_percent.toFixed(1) : 0;
      el('pi-disk-used', formatBytes(used));
      el('pi-disk-total', formatBytes(total));
      el('pi-disk-pct', `${pct}%`);
    } else {
      el('pi-disk-used', '—');
      el('pi-disk-total', '—');
      el('pi-disk-pct', '—');
    }
    
    el('pi-uptime', data.uptime_seconds ? formatUptime(data.uptime_seconds) : '—');

    // Measured power/voltage/throttle
    if (data.core_voltage_v !== undefined) {
      el('pi-voltage', (data.core_voltage_v || data.core_voltage_v === 0) ? `${Number(data.core_voltage_v).toFixed(2)} V` : '—');
    }
    const yn = (b) => (b === true ? 'Yes' : (b === false ? 'No' : '—'));
    el('pi-undervolt', yn(data.under_voltage));
    if (data.under_voltage === true) {
      const badge = document.getElementById('pi-undervolt-badge');
      if (badge) badge.innerHTML = '<span style="color:#ef4444;font-weight:600;">⚠ Active</span>';
    }
    el('pi-freq', yn(data.freq_capped));
    el('pi-throttled', yn(data.throttled));
    
    // Throttle history badges
    const tbadges = document.getElementById('pi-throttle-badges');
    if (tbadges) {
      const badges = [];
      if (data.under_voltage_has_occurred) badges.push('<span style="color:#fca5a5;">⚠ UV</span>');
      if (data.freq_capped_has_occurred) badges.push('<span style="color:#fbbf24;">⚡ Freq</span>');
      if (data.throttled_has_occurred) badges.push('<span style="color:#f87171;">🔥 Throttled</span>');
      if (data.soft_temp_limit_has_occurred) badges.push('<span style="color:#fb923c;">🌡 TempLim</span>');
      tbadges.innerHTML = badges.length > 0 ? 'Seen since boot: ' + badges.join(', ') : '';
    }
  }

  // Populate Software Information section
  function populateSoftwareInfo(data) {
    const el = (id, text) => {
      const elem = document.getElementById(id);
      if (elem) elem.textContent = text;
    };

    el('sw-rdwc-version', data.rdwc_version || '—');
    el('sw-python-version', data.python_version || '—');
    
    // Git info is nested under data.git
    if (data.git) {
      el('sw-git-commit', data.git.commit ? data.git.commit.substring(0, 8) : '—');
      el('sw-git-branch', data.git.branch || '—');
    } else {
      el('sw-git-commit', '—');
      el('sw-git-branch', '—');
    }

    // Service status chips - services is nested
    const updateServiceValue = (id, status) => {
      const elem = document.getElementById(id);
      console.log(`[SystemInfo] Updating service ${id} with status: "${status}"`);
      if (!elem) {
        console.warn(`[SystemInfo] Element ${id} not found`);
        return;
      }
      
      if (status === 'active') {
        elem.textContent = 'Active';
        elem.style.color = '#10b981'; // success green
      } else if (status === 'inactive') {
        elem.textContent = 'Inactive';
        elem.style.color = '#9ca3af'; // neutral gray
      } else {
        elem.textContent = 'Error';
        elem.style.color = '#ef4444'; // error red
        console.error(`[SystemInfo] Unexpected service status for ${id}: "${status}"`);
      }
    };

    if (data.services) {
      console.log('[SystemInfo] Services object:', data.services);
      updateServiceValue('svc-api', data.services['rdwc']);
      updateServiceValue('svc-sensors', data.services['rdwc-sensors']);
    } else {
      console.warn('[SystemInfo] No services data received');
    }
  }

  // Populate Environment Information section
  function populateEnvironmentInfo(data) {
    const i2cContainer = document.getElementById('env-i2c-container');
    const gpioContainer = document.getElementById('env-gpio-container');
    const sensorPowerEl = document.getElementById('env-sensor-power');

    // I²C devices - create individual kpi blocks with blue color
    if (i2cContainer) {
      i2cContainer.innerHTML = '';
      if (data.i2c_devices && data.i2c_devices.length > 0) {
        data.i2c_devices.forEach(device => {
          const kpi = document.createElement('div');
          kpi.className = 'kpi';
          
          const label = document.createElement('div');
          label.className = 'kpi-label';
          label.textContent = device.name;
          
          const value = document.createElement('div');
          value.className = 'kpi-value';
          value.textContent = device.address;
          value.style.color = '#93c5fd'; // Blue for I²C
          
          kpi.appendChild(label);
          kpi.appendChild(value);
          i2cContainer.appendChild(kpi);
        });
      } else {
        const kpi = document.createElement('div');
        kpi.className = 'kpi';
        kpi.innerHTML = '<div class="kpi-label">I²C Devices</div><div class="kpi-value" style="color:#9ca3af;">None detected</div>';
        i2cContainer.appendChild(kpi);
      }
    }

    // GPIO pins - create individual kpi blocks with green color
    if (gpioContainer) {
      gpioContainer.innerHTML = '';
      if (data.relay_pins && Object.keys(data.relay_pins).length > 0) {
        Object.entries(data.relay_pins).forEach(([name, pin]) => {
          const kpi = document.createElement('div');
          kpi.className = 'kpi';
          
          const label = document.createElement('div');
          label.className = 'kpi-label';
          label.textContent = name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
          
          const value = document.createElement('div');
          value.className = 'kpi-value';
          value.textContent = `GPIO ${pin}`;
          value.style.color = '#a7f3d0'; // Green for GPIO
          
          kpi.appendChild(label);
          kpi.appendChild(value);
          gpioContainer.appendChild(kpi);
        });
      } else {
        const kpi = document.createElement('div');
        kpi.className = 'kpi';
        kpi.innerHTML = '<div class="kpi-label">GPIO Pins</div><div class="kpi-value" style="color:#9ca3af;">None configured</div>';
        gpioContainer.appendChild(kpi);
      }
    }

    // Sensor power pin
    if (sensorPowerEl) {
      if (data.sensor_power_pin && data.sensor_power_pin !== 'not configured') {
        sensorPowerEl.textContent = `GPIO ${data.sensor_power_pin}`;
      } else {
        sensorPowerEl.textContent = 'Not configured';
        sensorPowerEl.style.color = '#9ca3af';
      }
    }
  }

  // Populate Database Information section
  function populateDatabaseInfo(data) {
    const el = (id, text) => {
      const elem = document.getElementById(id);
      if (elem) elem.textContent = text;
    };

    // DB size in MB
    el('db-size', data.size_mb ? `${data.size_mb.toFixed(2)} MB` : '—');
    el('db-free', (data.disk_free_gb || data.disk_free_gb === 0) ? `${data.disk_free_gb.toFixed(2)} GB` : '—');
    
    // Disk free with severity badge
    if (data.disk_free_percent || data.disk_free_percent === 0) {
      el('db-free-pct', `${data.disk_free_percent.toFixed(1)}%`);
      const fbadge = document.getElementById('db-free-badge');
      if (fbadge) {
        let color = '#10b981';
        let text = '';
        if (data.disk_free_percent < 5) {
          color = '#ef4444';
          text = '🔴 CRITICAL';
        } else if (data.disk_free_percent < 10) {
          color = '#f97316';
          text = '🟠 LOW';
        } else if (data.disk_free_percent < 20) {
          color = '#eab308';
          text = '🟡 WARN';
        }
        fbadge.innerHTML = text ? `<span style="color:${color};font-weight:600;">${text}</span>` : '';
      }
    } else {
      el('db-free-pct', '—');
    }
    el('db-health', data.smart_health || '—');
    
    // Record counts from tables object
    if (data.tables) {
      el('db-readings', data.tables.readings ? data.tables.readings.toLocaleString() : '0');
      el('db-ph-doses', data.tables.ph_dose_log ? data.tables.ph_dose_log.toLocaleString() : '0');
      el('db-ec-doses', data.tables.ec_dose_log ? data.tables.ec_dose_log.toLocaleString() : '0');
    } else {
      el('db-readings', '0');
      el('db-ph-doses', '0');
      el('db-ec-doses', '0');
    }

    // Parse ISO timestamps
    const parseTimestamp = (isoStr) => {
      if (!isoStr) return null;
      // Parse format like "2025-11-01T14:37:59"
      const date = new Date(isoStr);
      return date.getTime() / 1000; // Convert to Unix timestamp
    };

    el('db-oldest', formatTimestamp(parseTimestamp(data.oldest_reading)));
    el('db-newest', formatTimestamp(parseTimestamp(data.newest_reading)));
  }

  // Populate Network Information section
  function populateNetworkInfo(data) {
    const hostnameEl = document.getElementById('net-hostname');
    const ipsContainer = document.getElementById('net-ips-container');
    const wifiEl = document.getElementById('net-wifi');
    const ifstatsEl = document.getElementById('net-ifstats');

    if (hostnameEl) {
      hostnameEl.textContent = data.hostname || '—';
    }

    if (ipsContainer) {
      ipsContainer.innerHTML = '';
      if (data.ip_addresses && data.ip_addresses.length > 0) {
        data.ip_addresses.forEach(ipInfo => {
          const kpi = document.createElement('div');
          kpi.className = 'kpi';
          
          const label = document.createElement('div');
          label.className = 'kpi-label';
          label.textContent = ipInfo.interface;
          
          const value = document.createElement('div');
          value.className = 'kpi-value';
          const netmask = ipInfo.netmask ? `/${ipInfo.netmask}` : '';
          value.textContent = `${ipInfo.address}${netmask}`;
          value.style.color = '#93c5fd';
          
          kpi.appendChild(label);
          kpi.appendChild(value);
          ipsContainer.appendChild(kpi);
        });
      } else {
        const msg = document.createElement('div');
        msg.className = 'muted';
        msg.textContent = 'No interfaces found';
        ipsContainer.appendChild(msg);
      }
    }

    if (wifiEl) {
      if (data.wifi) {
        const parts = [];
        if (data.wifi.ssid) parts.push(`SSID: ${data.wifi.ssid}`);
        if (data.wifi.signal_dbm !== null && data.wifi.signal_dbm !== undefined) parts.push(`Signal: ${data.wifi.signal_dbm} dBm`);
        if (data.wifi.quality_pct !== null && data.wifi.quality_pct !== undefined) parts.push(`Quality: ${data.wifi.quality_pct}%`);
        if (data.wifi.bitrate) parts.push(`Bitrate: ${data.wifi.bitrate}`);
        wifiEl.textContent = parts.join(' • ') || 'WiFi detected';
      } else {
        wifiEl.textContent = '';
      }
    }

    if (ifstatsEl) {
      if (data.iface_stats) {
        const lines = Object.entries(data.iface_stats).map(([name, st]) => {
          const err = (st.errin || st.errout || st.dropin || st.dropout) ? ` err:${st.errin||0}/${st.errout||0} drop:${st.dropin||0}/${st.dropout||0}` : '';
          return `${name}: rx ${(st.bytes_recv/1e6).toFixed(1)}MB tx ${(st.bytes_sent/1e6).toFixed(1)}MB${err}`;
        });
        ifstatsEl.textContent = lines.join(' • ');
      } else {
        ifstatsEl.textContent = '';
      }
    }
  }

  // Populate Electrical breakdown (optional); Pi KPIs handled in populatePiInfo
  function populateElectricalInfo(data) {
    const br = document.getElementById('el-breakdown');
    const hint = document.getElementById('el-hint');

    if (!br || !hint) return;

    if (data.breakdown && data.breakdown.length > 0) {
      const label = data.computed_from_config ? 'Configured loads (not measured)' : 'Loads';
      br.innerHTML = `<div style="margin-bottom:6px;">${label}:</div>` + data.breakdown
        .map(item => `• ${item.relay.replace(/_/g,' ')} — ${Number(item.watts).toFixed(1)} W`)
        .join('<br/>');
      hint.style.display = 'none';
    } else {
      br.textContent = 'No configured loads or relays currently ON';
      hint.style.display = 'block';
    }
  }

  // Populate Process Information section
  function populateProcessInfo(data) {
    const tbody = document.getElementById('proc-table');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (data.rdwc_processes && data.rdwc_processes.length > 0) {
      data.rdwc_processes.forEach(proc => {
        const row = document.createElement('tr');
        row.style.cssText = 'border-bottom:1px solid rgba(55,65,81,0.3);';

        const pidCell = document.createElement('td');
        pidCell.style.cssText = 'padding:8px 10px;';
        pidCell.textContent = proc.pid || '—';

        const nameCell = document.createElement('td');
        nameCell.style.cssText = 'padding:8px 10px;font-family:monospace;font-size:0.8rem;';
        nameCell.textContent = proc.name || '—';

        const userCell = document.createElement('td');
        userCell.style.cssText = 'padding:8px 10px;';
        userCell.textContent = proc.user || proc.username || '—';

        const cpuCell = document.createElement('td');
        cpuCell.style.cssText = 'padding:8px 10px;text-align:right;';
        cpuCell.textContent = proc.cpu_percent !== null && proc.cpu_percent !== undefined ? `${proc.cpu_percent.toFixed(1)}%` : '—';

        const memCell = document.createElement('td');
        memCell.style.cssText = 'padding:8px 10px;text-align:right;';
        memCell.textContent = proc.memory_percent !== null && proc.memory_percent !== undefined ? `${proc.memory_percent.toFixed(2)}%` : '—';

        const rtCell = document.createElement('td');
        rtCell.style.cssText = 'padding:8px 10px;text-align:right;';
        if (proc.runtime_seconds !== null && proc.runtime_seconds !== undefined) {
          const mins = Math.floor(proc.runtime_seconds / 60);
          const hours = Math.floor(mins / 60);
          const remMins = mins % 60;
          rtCell.textContent = hours > 0 ? `${hours}h ${remMins}m` : `${remMins}m`;
        } else {
          rtCell.textContent = '—';
        }

        row.appendChild(pidCell);
        row.appendChild(nameCell);
        row.appendChild(userCell);
        row.appendChild(cpuCell);
        row.appendChild(memCell);
        row.appendChild(rtCell);
        tbody.appendChild(row);
      });
    } else {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 6;
      cell.style.cssText = 'padding:12px;text-align:center;color:#9ca3af;';
      cell.textContent = 'No RDWC processes found';
      row.appendChild(cell);
      tbody.appendChild(row);
    }
  }

  // Main fetch function
  async function fetchSystemInfo() {
    try {
      const response = await fetch('/api/system/info', {
        cache: 'no-store',
        headers: { 'Cache-Control': 'no-store' }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      // Populate all sections
      if (data.pi_info) populatePiInfo(data.pi_info);
      if (data.software_info) populateSoftwareInfo(data.software_info);
      if (data.environment_info) populateEnvironmentInfo(data.environment_info);
      if (data.database_info) populateDatabaseInfo(data.database_info);
      if (data.network_info) populateNetworkInfo(data.network_info);
      if (data.process_info) populateProcessInfo(data.process_info);
      if (data.electrical_info) populateElectricalInfo(data.electrical_info);

      updateRefreshIndicator(true);
    } catch (error) {
      console.error('Failed to fetch system info:', error);
      updateRefreshIndicator(false);
    }
  }

  // Start auto-refresh
  function startAutoRefresh() {
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    refreshInterval = setInterval(fetchSystemInfo, REFRESH_INTERVAL_MS);
  }

  // Stop auto-refresh
  function stopAutoRefresh() {
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
    }
  }

  // Initialize
  function init() {
    // Bind manual refresh button
    const btnRefresh = document.getElementById('btnRefreshSystemInfo');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => {
        fetchSystemInfo();
      });
    }

    // Initial fetch
    fetchSystemInfo();

    // Start auto-refresh
    startAutoRefresh();

    // Stop auto-refresh when tab is not visible
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        stopAutoRefresh();
      } else {
        // Check if System tab is active before restarting
        const systemTab = document.getElementById('settings-card');
        if (systemTab && systemTab.style.display !== 'none') {
          startAutoRefresh();
          fetchSystemInfo(); // Immediate refresh on return
        }
      }
    });

    console.log('System Info controller initialized with 10s auto-refresh');
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Export for debugging
  window.systemInfo = {
    refresh: fetchSystemInfo,
    startAutoRefresh,
    stopAutoRefresh
  };

})();
