/**
 * system_metrics_chart.js - Unified system metrics visualization
 * Single Chart.js canvas with metric selector, time range controls, and CSV export
 */
(function() {
  'use strict';

  const METRICS = {
    cpu_percent: { label: 'CPU %', color: '#FF6B6B', unit: '%' },
    memory_percent: { label: 'Memory %', color: '#4ECDC4', unit: '%' },
    disk_percent: { label: 'Disk %', color: '#FFE66D', unit: '%' },
    core_voltage_v: { label: 'Core Voltage', color: '#95E1D3', unit: 'V' },
    load_1m: { label: 'Load (1m)', color: '#A8E6CF', unit: '' },
    load_5m: { label: 'Load (5m)', color: '#FF8B94', unit: '' },
    load_15m: { label: 'Load (15m)', color: '#C7CEEA', unit: '' },
    net_rx_bytes: { label: 'RX Bytes', color: '#B4E7FF', unit: 'B' },
    net_tx_bytes: { label: 'TX Bytes', color: '#FFB7B2', unit: 'B' }
  };

  const GROUPS = {
    performance: {
      label: 'Performance',
      metrics: ['cpu_percent', 'memory_percent', 'disk_percent']
    },
    load_power: {
      label: 'Load & Power',
      metrics: ['core_voltage_v', 'load_1m', 'load_5m', 'load_15m']
    },
    network: {
      label: 'Network',
      metrics: ['net_rx_bytes', 'net_tx_bytes']
    }
  };

  const TIME_RANGES = [
    { id: '1h', label: '1h', hours: 1 },
    { id: '24h', label: '24h', hours: 24 },
    { id: '7d', label: '7d', hours: 168 }
  ];

  let chartInstance = null;
  let selectedMetrics = [...GROUPS.performance.metrics];
  let currentTimeRange = 24;
  let activeGroup = 'performance';

  // Fetch history data
  async function fetchHistory(hours, metrics) {
    try {
      const metricsStr = metrics.join(',');
      const r = await fetch(`/api/system/metrics/history?start_hours=${hours}&metrics=${encodeURIComponent(metricsStr)}`, {
        cache: 'no-store'
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    } catch (e) {
      console.warn('[SysMetricsChart] fetch failed', e);
      return null;
    }
  }

  // Format bytes nicely
  function formatBytes(n) {
    if (n == null) return '—';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0, v = n;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return v.toFixed(1) + ' ' + units[i];
  }

  // Format value for display
  function formatValue(val, metric) {
    if (val == null) return '—';
    const meta = METRICS[metric] || {};
    if (metric.includes('bytes')) return formatBytes(val);
    const num = typeof val === 'number' ? val : parseFloat(val);
    return isNaN(num) ? '—' : num.toFixed(2) + (meta.unit ? ' ' + meta.unit : '');
  }

  // Build HTML UI
  function buildUI() {
    const container = document.getElementById('system-metrics-container');
    if (!container) return;
    container.innerHTML = '';

    // Build group selector buttons in the KPI row at top of page
    const groupRow = document.getElementById('sys-metrics-groups');
    if (groupRow) {
      groupRow.innerHTML = '';
      Object.entries(GROUPS).forEach(([key, group]) => {
        const btn = document.createElement('div');
        btn.className = 'kpi';
        btn.style.cssText = 'cursor:pointer;transition:all 0.2s;' + (key === activeGroup ? 'border-color:#4ECDC4;' : '');
        btn.dataset.groupKey = key;
        btn.onclick = () => {
          activeGroup = key;
          selectedMetrics = [...group.metrics];
          syncCheckboxes();
          highlightGroups();
          loadChart();
        };
        const label = document.createElement('div');
        label.className = 'kpi-label';
        label.textContent = group.label;
        const value = document.createElement('div');
        value.className = 'kpi-value';
        value.style.cssText = 'font-size:14px;color:#9ca3af;';
        value.textContent = group.metrics.map(m => METRICS[m].label).join(', ');
        btn.appendChild(label);
        btn.appendChild(value);
        groupRow.appendChild(btn);
      });
    }

    // Chart area first
    const chartDiv = document.createElement('div');
    chartDiv.style.cssText = 'position:relative;height:420px;margin-bottom:16px;background:#0d1117;border:1px solid #333;border-radius:8px;padding:10px;';
    chartDiv.innerHTML = '<canvas id="sys-metrics-canvas"></canvas>';
    container.appendChild(chartDiv);

    // Controls under the chart
    const controls = document.createElement('div');
    controls.style.cssText = 'display:flex;flex-direction:column;gap:12px;margin-bottom:16px;';

    const topRow = document.createElement('div');
    topRow.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;';

    // Time range buttons
    const timeButtons = document.createElement('div');
    timeButtons.style.cssText = 'display:flex;gap:6px;';
    TIME_RANGES.forEach(range => {
      const btn = document.createElement('button');
      btn.className = 'btn-chip';
      btn.textContent = range.label;
      btn.style.cssText = range.hours === currentTimeRange
        ? 'background:#4ECDC4;color:#000;'
        : 'background:#333;color:#e0e0e0;';
      btn.onclick = () => {
        currentTimeRange = range.hours;
        document.querySelectorAll('[data-range-btn]').forEach(b => {
          b.style.background = b.dataset.hours == range.hours ? '#4ECDC4' : '#333';
          b.style.color = b.dataset.hours == range.hours ? '#000' : '#e0e0e0';
        });
        loadChart();
      };
      btn.dataset.rangeBtn = '';
      btn.dataset.hours = range.hours;
      timeButtons.appendChild(btn);
    });
    topRow.appendChild(timeButtons);

    controls.appendChild(topRow);

    // Metric selector (checkboxes) below controls
    const selectorDiv = document.createElement('div');
    selectorDiv.style.cssText = 'background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:12px;';

    const selectorLabel = document.createElement('div');
    selectorLabel.style.cssText = 'font-weight:600;color:#e0e0e0;margin-bottom:8px;font-size:13px;';
    selectorLabel.textContent = 'Select metrics:';
    selectorDiv.appendChild(selectorLabel);

    const checkboxGrid = document.createElement('div');
    checkboxGrid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;';

    Object.entries(METRICS).forEach(([key, meta]) => {
      const label = document.createElement('label');
      label.style.cssText = 'display:flex;align-items:center;gap:6px;cursor:pointer;color:#e0e0e0;font-size:12px;';

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = selectedMetrics.includes(key);
      cb.value = key;
      cb.style.cssText = 'cursor:pointer;';
      cb.setAttribute('data-metric-cb', key);
      cb.onchange = () => {
        if (cb.checked && !selectedMetrics.includes(key)) {
          selectedMetrics.push(key);
        } else {
          selectedMetrics = selectedMetrics.filter(m => m !== key);
        }
        // Custom mix cancels active group highlight
        activeGroup = null;
        highlightGroups();
        loadChart();
      };

      const span = document.createElement('span');
      span.textContent = meta.label;
      label.appendChild(cb);
      label.appendChild(span);
      checkboxGrid.appendChild(label);
    });
    selectorDiv.appendChild(checkboxGrid);

    controls.appendChild(selectorDiv);

    // Export button
    const exportBtn = document.createElement('button');
    exportBtn.className = 'btn-chip';
    exportBtn.style.cssText = 'background:#4ECDC4;color:#000;cursor:pointer;align-self:flex-start;';
    exportBtn.textContent = '📥 Export CSV';
    exportBtn.onclick = exportCSV;
    controls.appendChild(exportBtn);

    container.appendChild(controls);
  }

  function highlightGroups() {
    document.querySelectorAll('[data-group-key]').forEach(btn => {
      const isActive = btn.dataset.groupKey === activeGroup;
      if (btn.classList.contains('kpi')) {
        btn.style.borderColor = isActive ? '#4ECDC4' : '';
      } else {
        btn.style.background = isActive ? '#4ECDC4' : '#333';
        btn.style.color = isActive ? '#000' : '#e0e0e0';
      }
    });
  }

  function syncCheckboxes() {
    document.querySelectorAll('input[data-metric-cb]').forEach(cb => {
      cb.checked = selectedMetrics.includes(cb.dataset.metricCb || cb.value);
    });
  }

  // Render chart
  async function loadChart() {
    if (selectedMetrics.length === 0) {
      console.warn('[SysMetricsChart] No metrics selected');
      return;
    }

    const resp = await fetchHistory(currentTimeRange, selectedMetrics);
    if (!resp || !resp.ok) {
      console.warn('[SysMetricsChart] Failed to fetch history');
      return;
    }

    const data = resp.data || [];
    if (data.length === 0) {
      console.log('[SysMetricsChart] No data for range');
      return;
    }

    const datasets = selectedMetrics.map(metric => {
      const meta = METRICS[metric];
      const values = data.map(row => row[metric]);
      return {
        label: meta.label,
        data: values,
        borderColor: meta.color,
        backgroundColor: meta.color + '20',
        tension: 0.3,
        pointRadius: 2,
        pointBackgroundColor: meta.color,
        borderWidth: 2,
        fill: false
      };
    });

    const ctx = document.getElementById('sys-metrics-canvas');
    if (!ctx) return;

    if (chartInstance) {
      chartInstance.destroy();
    }

    chartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.map(row => {
          const ts = typeof row.ts === 'number' ? row.ts * 1000 : row.ts;
          return new Date(ts).toLocaleString();
        }),
        datasets: datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            labels: { color: '#e0e0e0', usePointStyle: true },
            position: 'top'
          }
        },
        scales: {
          x: {
            grid: { color: '#333' },
            ticks: { color: '#aaa', maxTicksLimit: 8 }
          },
          y: {
            grid: { color: '#333' },
            ticks: { color: '#aaa' },
            beginAtZero: false
          }
        }
      }
    });
  }

  // Auto-refresh handling (align with 60s sampling cadence)
  let _refreshHandle = null;
  function startAutoRefresh() {
    if (_refreshHandle) clearInterval(_refreshHandle);
    _refreshHandle = setInterval(() => {
      loadChart();
    }, 60 * 1000);
  }

  // Export CSV
  function exportCSV() {
    if (!chartInstance || !chartInstance.data || chartInstance.data.datasets.length === 0) {
      alert('No chart data to export');
      return;
    }

    const headers = ['Timestamp', ...selectedMetrics.map(m => METRICS[m].label)];
    const rows = [];

    chartInstance.data.labels.forEach((label, idx) => {
      const row = [label];
      chartInstance.data.datasets.forEach(ds => {
        const val = ds.data[idx];
        row.push(val != null ? val : '');
      });
      rows.push(row);
    });

    const csv = [headers.join(','), ...rows.map(r => r.map(v => {
      if (typeof v === 'string' && v.includes(',')) return `"${v}"`;
      return v;
    }).join(','))].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `system_metrics_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // Boot
  function boot() {
    buildUI();
    loadChart();
    startAutoRefresh();
    highlightGroups();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
