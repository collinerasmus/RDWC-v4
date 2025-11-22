// system_info.js - System Information Tab Controller
// Fetches and displays comprehensive system info from /api/system/info

(function() {
  'use strict';

  let refreshInterval = null;
  const REFRESH_INTERVAL_MS = 10000; // 10 seconds

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

    el('pi-cpu', data.cpu_percent ? `${data.cpu_percent.toFixed(1)}%` : '—');
    el('pi-cpu-freq', data.cpu_freq_mhz ? `${data.cpu_freq_mhz.toFixed(0)} MHz` : '—');
    el('pi-cpu-temp', data.cpu_temp_c ? `${data.cpu_temp_c.toFixed(1)}°C` : '—');
    
    if (data.memory) {
      const mem = data.memory;
      const pct = mem.percent ? mem.percent.toFixed(1) : 0;
      const used = formatBytes(mem.used || 0);
      const total = formatBytes(mem.total || 0);
      el('pi-memory', `${used} / ${total} (${pct}%)`);
    } else {
      el('pi-memory', '—');
    }
    
    if (data.disk) {
      const disk = data.disk;
      const pct = disk.percent ? disk.percent.toFixed(1) : 0;
      const used = formatBytes(disk.used || 0);
      const total = formatBytes(disk.total || 0);
      el('pi-disk', `${used} / ${total} (${pct}%)`);
    } else {
      el('pi-disk', '—');
    }
    
    el('pi-uptime', data.uptime_seconds ? formatUptime(data.uptime_seconds) : '—');
  }

  // Populate Software Information section
  function populateSoftwareInfo(data) {
    const el = (id, text) => {
      const elem = document.getElementById(id);
      if (elem) elem.textContent = text;
    };

    el('sw-rdwc-version', data.rdwc_version || '—');
    el('sw-python-version', data.python_version || '—');
    el('sw-git-commit', data.git_commit ? data.git_commit.substring(0, 8) : '—');
    el('sw-git-branch', data.git_branch || '—');

    // Service status chips
    const updateServiceChip = (id, status) => {
      const chip = document.getElementById(id);
      if (!chip) return;
      
      if (status === 'active') {
        chip.className = 'ui-status-chip success';
        chip.textContent = 'Active';
      } else if (status === 'inactive') {
        chip.className = 'ui-status-chip neutral';
        chip.textContent = 'Inactive';
      } else {
        chip.className = 'ui-status-chip error';
        chip.textContent = 'Error';
      }
    };

    if (data.systemd_services) {
      updateServiceChip('svc-api', data.systemd_services['rdwc-api']);
      updateServiceChip('svc-sensors', data.systemd_services['rdwc-sensors']);
    }
  }

  // Populate Environment Information section
  function populateEnvironmentInfo(data) {
    const i2cContainer = document.getElementById('env-i2c-devices');
    const gpioContainer = document.getElementById('env-gpio-pins');
    const sensorPowerEl = document.getElementById('env-sensor-power');

    // I²C devices
    if (i2cContainer) {
      i2cContainer.innerHTML = '';
      if (data.i2c_devices && data.i2c_devices.length > 0) {
        data.i2c_devices.forEach(device => {
          const badge = document.createElement('span');
          badge.style.cssText = 'padding:4px 10px;background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.35);border-radius:6px;color:#93c5fd;font-size:0.85rem;white-space:nowrap;';
          badge.textContent = `${device.address} ${device.name}`;
          i2cContainer.appendChild(badge);
        });
      } else {
        const msg = document.createElement('span');
        msg.style.cssText = 'color:#9ca3af;font-size:0.85rem;';
        msg.textContent = 'No I²C devices detected';
        i2cContainer.appendChild(msg);
      }
    }

    // GPIO pins
    if (gpioContainer) {
      gpioContainer.innerHTML = '';
      if (data.relay_gpio_pins && Object.keys(data.relay_gpio_pins).length > 0) {
        Object.entries(data.relay_gpio_pins).forEach(([name, pin]) => {
          const badge = document.createElement('span');
          badge.style.cssText = 'padding:4px 8px;background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.35);border-radius:6px;color:#a7f3d0;font-size:0.8rem;';
          badge.textContent = `${name}: GPIO ${pin}`;
          gpioContainer.appendChild(badge);
        });
      } else {
        const msg = document.createElement('span');
        msg.style.cssText = 'color:#9ca3af;font-size:0.85rem;';
        msg.textContent = 'No GPIO pins configured';
        gpioContainer.appendChild(msg);
      }
    }

    // Sensor power pin
    if (sensorPowerEl) {
      if (data.sensor_power_pin !== null && data.sensor_power_pin !== undefined) {
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

    el('db-size', data.db_size_bytes ? formatBytes(data.db_size_bytes) : '—');
    
    if (data.record_counts) {
      el('db-readings', data.record_counts.readings ? data.record_counts.readings.toLocaleString() : '0');
      el('db-ph-doses', data.record_counts.ph_dose_log ? data.record_counts.ph_dose_log.toLocaleString() : '0');
      el('db-ec-doses', data.record_counts.ec_dose_log ? data.record_counts.ec_dose_log.toLocaleString() : '0');
    }

    el('db-oldest', formatTimestamp(data.oldest_reading_ts));
    el('db-newest', formatTimestamp(data.newest_reading_ts));
  }

  // Populate Network Information section
  function populateNetworkInfo(data) {
    const hostnameEl = document.getElementById('net-hostname');
    const ipsContainer = document.getElementById('net-ips');

    if (hostnameEl) {
      hostnameEl.textContent = data.hostname || '—';
    }

    if (ipsContainer) {
      ipsContainer.innerHTML = '';
      if (data.ip_addresses && data.ip_addresses.length > 0) {
        data.ip_addresses.forEach(ipInfo => {
          const row = document.createElement('div');
          row.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:6px 10px;background:rgba(0,0,0,0.2);border-radius:6px;';
          
          const iface = document.createElement('span');
          iface.style.cssText = 'font-weight:600;color:#c084fc;';
          iface.textContent = ipInfo.interface;
          
          const ip = document.createElement('span');
          ip.style.cssText = 'color:#d1d5db;font-family:monospace;';
          ip.textContent = `${ipInfo.address}${ipInfo.netmask ? '/' + ipInfo.netmask : ''}`;
          
          row.appendChild(iface);
          row.appendChild(ip);
          ipsContainer.appendChild(row);
        });
      } else {
        const msg = document.createElement('span');
        msg.style.cssText = 'color:#9ca3af;font-size:0.85rem;';
        msg.textContent = 'No network interfaces found';
        ipsContainer.appendChild(msg);
      }
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
        userCell.textContent = proc.username || '—';

        const memCell = document.createElement('td');
        memCell.style.cssText = 'padding:8px 10px;text-align:right;';
        memCell.textContent = proc.memory_percent ? `${proc.memory_percent.toFixed(2)}%` : '—';

        row.appendChild(pidCell);
        row.appendChild(nameCell);
        row.appendChild(userCell);
        row.appendChild(memCell);
        tbody.appendChild(row);
      });
    } else {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 4;
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
