/**
 * EC Dose Chart - Clean implementation
 * Shows EC sensor readings over time with dose events overlaid per pump
 */
(function(){
  'use strict';
  console.log('[EC Chart] Initializing...');

  let chart = null;
  let currentRange = { preset: '24h', start: null, end: null };

  // Register Chart.js components if needed
  if (window.Chart && Chart.register) {
    try {
      Chart.register(
        Chart.controllers.LineController,
        Chart.controllers.ScatterController,
        Chart.elements.PointElement,
        Chart.elements.LineElement,
        Chart.scales.TimeScale,
        Chart.scales.LinearScale,
        Chart.plugins.Tooltip,
        Chart.plugins.Legend
      );
    } catch (e) {
      // Already registered
    }
  }

  /**
   * Fetch EC readings from trends API
   */
  async function fetchEcReadings(startISO, endISO) {
    try {
      const params = new URLSearchParams();
      if (startISO) params.set('from', startISO);
      if (endISO) params.set('to', endISO);
      params.set('gran', '60'); // 1 minute granularity
      params.set('max', '2000');
      
      const url = '/api/trends?' + params.toString();
      console.log('[EC Chart] Fetching EC readings from:', url);
      
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) {
        console.error('[EC Chart] EC readings fetch failed:', res.status);
        return [];
      }
      
      const data = await res.json();
      console.log('[EC Chart] Trends API response:', data);
      
      const ecData = (data?.series?.ec || []).map(p => ({
        x: new Date(p.ts * 1000),
        y: Number(p.value)
      })).filter(p => !isNaN(p.y));
      
      console.log('[EC Chart] Parsed EC readings:', ecData.length, 'points');
      return ecData;
    } catch (e) {
      console.error('[EC Chart] Failed to fetch EC readings:', e);
      return [];
    }
  }

  /**
   * Fetch dose events from API
   */
  async function fetchDoseEvents(startISO, endISO) {
    try {
      const params = new URLSearchParams();
      if (startISO) params.set('start', startISO);
      if (endISO) params.set('end', endISO);
      params.set('limit', '500');
      
      const url = '/api/ec/dose_log?' + params.toString();
      console.log('[EC Chart] Fetching dose events from:', url);
      
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) {
        console.error('[EC Chart] Dose events fetch failed:', res.status);
        return [];
      }
      
      const data = await res.json();
      console.log('[EC Chart] Dose events response:', data);
      return data;
    } catch (e) {
      console.error('[EC Chart] Failed to fetch dose events:', e);
      return [];
    }
  }

  /**
   * Fetch current EC status for targets
   */
  async function fetchEcStatus() {
    try {
      const res = await fetch('/api/ec/status', { cache: 'no-store' });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  /**
   * Build and render the chart
   */
  function renderChart(ecReadings, doseEvents, status) {
    console.log('[EC Chart] renderChart called with:', 
      'ecReadings:', ecReadings?.length || 0,
      'doseEvents:', doseEvents?.length || 0,
      'status:', status ? 'present' : 'null');
    
    const canvas = document.getElementById('ecDoseChart');
    const emptyMsg = document.getElementById('ec-dose-empty');
    
    if (!canvas) {
      console.error('[EC Chart] Canvas element #ecDoseChart not found');
      return;
    }

    // Destroy existing chart
    if (chart) {
      chart.destroy();
      chart = null;
    }

    const ctx = canvas.getContext('2d');
    
    // Group dose events by pump
    const growDoses = [];
    const microDoses = [];
    const bloomDoses = [];
    
    console.log('[EC Chart] Processing dose events...');
    (doseEvents || []).forEach((e, i) => {
      if (i < 3) console.log('[EC Chart] Dose event', i, ':', e);
      
      const point = {
        x: new Date(e.ts || e.ts_utc || e.ts_iso),
        y: e.ec_after ?? e.ec_before ?? 0,
        seconds: e.seconds,
        ecBefore: e.ec_before,
        ecAfter: e.ec_after,
        pump: e.pump
      };
      
      if (e.pump === 'grow') growDoses.push(point);
      else if (e.pump === 'micro') microDoses.push(point);
      else if (e.pump === 'bloom') bloomDoses.push(point);
    });
    
    console.log('[EC Chart] Dose counts - grow:', growDoses.length, 'micro:', microDoses.length, 'bloom:', bloomDoses.length);

    // Build datasets
    const datasets = [];
    
    // EC readings line (primary)
    if (ecReadings && ecReadings.length > 0) {
      datasets.push({
        type: 'line',
        label: 'EC (mS/cm)',
        data: ecReadings,
        borderColor: '#f59e0b',
        backgroundColor: 'rgba(245, 158, 11, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
        yAxisID: 'yEc'
      });
    }
    
    // Dose events - Grow
    if (growDoses.length > 0) {
      datasets.push({
        type: 'scatter',
        label: '🌱 Grow',
        data: growDoses,
        pointRadius: 8,
        pointStyle: 'triangle',
        backgroundColor: 'rgba(34, 197, 94, 0.8)',
        borderColor: '#16a34a',
        borderWidth: 2,
        yAxisID: 'yEc'
      });
    }
    
    // Dose events - Micro
    if (microDoses.length > 0) {
      datasets.push({
        type: 'scatter',
        label: '🔬 Micro',
        data: microDoses,
        pointRadius: 8,
        pointStyle: 'rect',
        backgroundColor: 'rgba(59, 130, 246, 0.8)',
        borderColor: '#2563eb',
        borderWidth: 2,
        yAxisID: 'yEc'
      });
    }
    
    // Dose events - Bloom
    if (bloomDoses.length > 0) {
      datasets.push({
        type: 'scatter',
        label: '🌸 Bloom',
        data: bloomDoses,
        pointRadius: 8,
        pointStyle: 'circle',
        backgroundColor: 'rgba(168, 85, 247, 0.8)',
        borderColor: '#9333ea',
        borderWidth: 2,
        yAxisID: 'yEc'
      });
    }

    // Show/hide empty message
    const hasData = datasets.length > 0 && datasets.some(ds => ds.data.length > 0);
    if (emptyMsg) {
      emptyMsg.style.display = hasData ? 'none' : 'block';
    }

    // If no data, create placeholder dataset
    if (!hasData) {
      datasets.push({
        label: 'No data',
        data: [],
        pointRadius: 0
      });
    }

    // Calculate Y axis range
    let yMin = 0;
    let yMax = 2.0; // Default max for hydro
    
    if (ecReadings && ecReadings.length > 0) {
      const maxReading = Math.max(...ecReadings.map(r => r.y));
      if (maxReading > yMax) {
        yMax = Math.ceil(maxReading * 1.2);
      }
    }
    
    // Check current EC
    const currentEC = status?.ec_ms_cm ?? status?.ec;
    if (currentEC && currentEC > yMax) {
      yMax = Math.ceil(currentEC * 1.2);
    }
    
    // Cap at probe max (K=0.1 = 8 mS/cm)
    if (yMax > 8) yMax = 8;

    // Build annotations for target band
    const annotations = {};
    const targets = status?.targets;
    
    if (targets && targets.low != null && targets.high != null) {
      annotations.targetBand = {
        type: 'box',
        yMin: targets.low,
        yMax: targets.high,
        yScaleID: 'yEc',
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
        borderWidth: 0
      };
      
      // Target setpoint line
      const setpoint = (targets.low + targets.high) / 2;
      annotations.setpointLine = {
        type: 'line',
        yMin: setpoint,
        yMax: setpoint,
        yScaleID: 'yEc',
        borderColor: 'rgba(34, 197, 94, 0.5)',
        borderWidth: 1,
        borderDash: [4, 4],
        label: {
          display: true,
          content: 'Target: ' + setpoint.toFixed(2),
          position: 'end',
          backgroundColor: 'rgba(34, 197, 94, 0.8)',
          color: '#fff',
          font: { size: 10 }
        }
      };
    }
    
    // Current EC line
    if (currentEC != null && !isNaN(currentEC)) {
      annotations.currentLine = {
        type: 'line',
        yMin: currentEC,
        yMax: currentEC,
        yScaleID: 'yEc',
        borderColor: 'rgba(251, 191, 36, 0.9)',
        borderWidth: 2,
        borderDash: [6, 4],
        label: {
          display: true,
          content: 'Now: ' + currentEC.toFixed(2),
          position: 'start',
          backgroundColor: 'rgba(251, 191, 36, 0.9)',
          color: '#000',
          font: { size: 11, weight: 'bold' }
        }
      };
    }

    // Check if annotation plugin is available (multiple detection methods)
    let hasAnnotation = false;
    try {
      hasAnnotation = !!(
        (window.Chart && Chart.registry && Chart.registry.plugins && Chart.registry.plugins.get('annotation')) ||
        (window['chartjs-plugin-annotation']) ||
        (window.chartjs && window.chartjs['plugin-annotation']) ||
        (window.ChartAnnotation)
      );
    } catch (e) {
      hasAnnotation = false;
    }

    // Create chart
    chart = new Chart(ctx, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'nearest', intersect: false },
        scales: {
          x: {
            type: 'time',
            time: {
              tooltipFormat: 'MMM d, HH:mm',
              displayFormats: {
                minute: 'HH:mm',
                hour: 'HH:mm',
                day: 'MMM d'
              }
            },
            min: currentRange.start ? new Date(currentRange.start) : undefined,
            max: currentRange.end ? new Date(currentRange.end) : undefined,
            grid: { color: 'rgba(148, 163, 184, 0.1)' },
            ticks: { maxRotation: 0 }
          },
          yEc: {
            type: 'linear',
            position: 'left',
            min: yMin,
            max: yMax,
            title: { display: true, text: 'EC (mS/cm)' },
            grid: { color: 'rgba(148, 163, 184, 0.1)' }
          }
        },
        plugins: {
          legend: {
            display: true,
            position: 'top',
            labels: { usePointStyle: true, boxWidth: 10 }
          },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                const ds = ctx.dataset;
                const raw = ctx.raw;
                
                if (ds.label === 'EC (mS/cm)') {
                  return 'EC: ' + ctx.parsed.y.toFixed(3) + ' mS/cm';
                }
                
                // Dose event
                if (raw && raw.pump) {
                  let label = raw.pump.charAt(0).toUpperCase() + raw.pump.slice(1);
                  label += ': ' + (raw.seconds || 0).toFixed(1) + 's';
                  if (raw.ecBefore != null && raw.ecAfter != null) {
                    const delta = raw.ecAfter - raw.ecBefore;
                    label += ' (Δ' + (delta >= 0 ? '+' : '') + delta.toFixed(3) + ')';
                  }
                  return label;
                }
                
                return ctx.parsed.y.toFixed(3);
              }
            }
          },
          annotation: hasAnnotation ? { annotations } : undefined
        }
      }
    });

    console.log('[EC Chart] Rendered with', ecReadings?.length || 0, 'EC readings and', 
      (growDoses.length + microDoses.length + bloomDoses.length), 'dose events');
  }

  /**
   * Load data and render chart
   */
  async function loadAndRender() {
    console.log('[EC Chart] Loading data for range:', currentRange);
    
    // Calculate time range
    let startISO, endISO;
    const now = new Date();
    
    if (currentRange.start && currentRange.end) {
      startISO = new Date(currentRange.start).toISOString();
      endISO = new Date(currentRange.end).toISOString();
    } else {
      // Default to 24 hours
      const start = new Date(now.getTime() - 24 * 3600 * 1000);
      startISO = start.toISOString();
      endISO = now.toISOString();
      currentRange.start = startISO;
      currentRange.end = endISO;
    }

    // Fetch all data in parallel
    const [ecReadings, doseEvents, status] = await Promise.all([
      fetchEcReadings(startISO, endISO),
      fetchDoseEvents(startISO, endISO),
      fetchEcStatus()
    ]);

    // Render chart
    renderChart(ecReadings, doseEvents, status);
    
    // Update KPI badges if they exist
    updateKpiBadges(doseEvents, status);
  }

  /**
   * Update Today/Week KPI badges
   */
  function updateKpiBadges(doseEvents, status) {
    const todayEl = document.getElementById('ec-total-today');
    const weekEl = document.getElementById('ec-total-week');
    
    if (!todayEl && !weekEl) return;
    
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const weekStart = todayStart - 7 * 24 * 3600 * 1000;
    
    // Get pump rates from settings or use defaults (typical peristaltic pump rate)
    const DEFAULT_PUMP_RATE = 1.5; // ml/sec - typical for small peristaltic pumps
    const rates = {
      grow: parseFloat(window.rdwcSettings?.get('dosing.grow_ml_per_sec')) || DEFAULT_PUMP_RATE,
      micro: parseFloat(window.rdwcSettings?.get('dosing.micro_ml_per_sec')) || DEFAULT_PUMP_RATE,
      bloom: parseFloat(window.rdwcSettings?.get('dosing.bloom_ml_per_sec')) || DEFAULT_PUMP_RATE
    };
    
    let todayMl = 0, weekMl = 0;
    
    (doseEvents || []).forEach(e => {
      const ts = new Date(e.ts || e.ts_utc || e.ts_iso).getTime();
      const ml = (e.volume_ml != null) ? e.volume_ml : ((e.seconds || 0) * (rates[e.pump] || DEFAULT_PUMP_RATE));
      
      if (ts >= todayStart) todayMl += ml;
      if (ts >= weekStart) weekMl += ml;
    });
    
    if (todayEl) {
      const valEl = todayEl.querySelector('.kpi-value');
      if (valEl) valEl.textContent = todayMl.toFixed(1) + ' ml';
    }
    
    if (weekEl) {
      const valEl = weekEl.querySelector('.kpi-value');
      if (valEl) valEl.textContent = weekMl.toFixed(1) + ' ml';
    }
  }

  /**
   * Select a preset range
   */
  function selectPreset(preset) {
    currentRange.preset = preset;
    
    const now = new Date();
    let start;
    
    switch (preset) {
      case '24h':
        start = new Date(now.getTime() - 24 * 3600 * 1000);
        break;
      case '7d':
        start = new Date(now.getTime() - 7 * 24 * 3600 * 1000);
        break;
      case '30d':
        start = new Date(now.getTime() - 30 * 24 * 3600 * 1000);
        break;
      case '90d':
        start = new Date(now.getTime() - 90 * 24 * 3600 * 1000);
        break;
      case 'today':
        start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        break;
      case 'grow':
        const growDate = window.rdwcSettings?.get('general.grow_start_date');
        start = growDate ? new Date(growDate) : new Date(now.getTime() - 30 * 24 * 3600 * 1000);
        break;
      default:
        start = new Date(now.getTime() - 24 * 3600 * 1000);
    }
    
    currentRange.start = start.toISOString();
    currentRange.end = now.toISOString();
    
    // Save preference
    if (window.rdwcRange) {
      window.rdwcRange.saveLastPreset('rdwc.ec.range', preset);
    }
    
    loadAndRender();
  }

  /**
   * Wire up UI controls
   */
  function wireControls() {
    // Range select dropdown
    const selectEl = document.getElementById('ecDoseRangeSelect');
    if (selectEl) {
      // Restore last preset
      const savedPreset = window.rdwcRange?.getLastPreset('rdwc.ec.range') || '24h';
      selectEl.value = savedPreset;
      currentRange.preset = savedPreset;
      
      selectEl.addEventListener('change', function() {
        selectPreset(this.value);
      });
    }
    
    // Custom range inputs
    const fromEl = document.getElementById('ecDoseFrom');
    const toEl = document.getElementById('ecDoseTo');
    const applyEl = document.getElementById('ecDoseApply');
    
    if (applyEl && fromEl && toEl) {
      applyEl.addEventListener('click', function() {
        const start = fromEl.value;
        const end = toEl.value;
        if (start && end) {
          currentRange.preset = 'custom';
          currentRange.start = new Date(start).toISOString();
          currentRange.end = new Date(end).toISOString();
          loadAndRender();
        }
      });
    }
    
    // Refresh button
    const refreshBtn = document.getElementById('btnEcRefreshChart');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function() {
        loadAndRender();
      });
    }
    
    // Export CSV button
    const exportBtn = document.getElementById('btnEcExport');
    if (exportBtn) {
      exportBtn.addEventListener('click', function() {
        let url = '/api/ec/dose_log.csv?hours=24';
        if (currentRange.start && currentRange.end) {
          url = '/api/ec/dose_log.csv?start=' + encodeURIComponent(currentRange.start) + 
                '&end=' + encodeURIComponent(currentRange.end);
        }
        window.open(url, '_blank');
      });
    }
  }

  /**
   * Initialize
   */
  function init() {
    console.log('[EC Chart] Init called');
    wireControls();
    selectPreset(currentRange.preset);
  }

  // Export API for other modules
  window.ecChart = {
    refresh: loadAndRender,
    render: loadAndRender,
    init: init,
    selectPreset: selectPreset,
    getRange: function() { return currentRange; },
    exportCSV: function() {
      let url = '/api/ec/dose_log.csv?hours=24';
      if (currentRange.start && currentRange.end) {
        url = '/api/ec/dose_log.csv?start=' + encodeURIComponent(currentRange.start) + 
              '&end=' + encodeURIComponent(currentRange.end);
      }
      window.open(url, '_blank');
    }
  };

  // Auto-init when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  console.log('[EC Chart] Module loaded');
})();
