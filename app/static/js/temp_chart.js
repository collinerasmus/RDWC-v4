/**
 * Temperature & Chiller History Chart Module
 * Research-backed visualization for Hailea HS-52A chiller operation
 * 
 * Features:
 * - Temperature trends with optimal range zones
 * - Chiller ON/OFF cycle visualization
 * - Compressor protection status indicators
 * - Energy efficiency metrics
 * - Cannabis-specific temperature zones
 */
(function() {
  'use strict';

  let TEMP_CHART = null;
  let TEMP_STATE = { startISO: null, endISO: null, lastCount: 0 };

  // Defensive Chart.js registration (v4 UMD usually auto-registers)
  if (window.Chart && Chart.register && window.RDWC_CHART_REG_TEMP === undefined) {
    try {
      Chart.register(
        Chart.controllers.BarController,
        Chart.controllers.LineController,
        Chart.controllers.ScatterController,
        Chart.elements.BarElement,
        Chart.elements.PointElement,
        Chart.elements.LineElement,
        Chart.scales.TimeScale,
        Chart.scales.LinearScale,
        Chart.plugins.Tooltip,
        Chart.plugins.Legend,
        Chart.plugins.Title,
        Chart.plugins.Filler
      );
      // Register annotation plugin if available
      if (window.chartjs && window.chartjs.Annotation) {
        Chart.register(window.chartjs.Annotation);
      } else if (window.ChartAnnotation) {
        Chart.register(window.ChartAnnotation);
      }
    } catch (e) {
      console.debug('[Temp] Chart.js already registered');
    }
    window.RDWC_CHART_REG_TEMP = true;
  }

  /**
   * Build temperature history chart with chiller operation overlay
   * @param {Array} tempData - Temperature readings [{ts, value}]
   * @param {Array} chillerEvents - Chiller state changes [{ts, state, reason}]
   * @param {string} tmin - ISO start time
   * @param {string} tmax - ISO end time
   * @param {Object} config - Chart configuration options
   */
  function buildTempChart(tempData, chillerEvents, tmin, tmax, config = {}) {
    const el = document.getElementById('tempHistoryChart');
    const empty = document.getElementById('temp-history-empty');
    if (!el) {
      console.error('[Temp] Canvas #tempHistoryChart not found');
      return;
    }

    const hasData = tempData && tempData.length > 0;
    if (empty) empty.style.display = hasData ? 'none' : 'block';

    const ctx = el.getContext('2d');
    if (TEMP_CHART && typeof TEMP_CHART.destroy === 'function') {
      TEMP_CHART.destroy();
      TEMP_CHART = null;
    }

    // Cannabis optimal temperature zones
    const OPTIMAL_MIN = 18.0;
    const OPTIMAL_MAX = 20.0;
    const SAFE_MIN = 16.0;
    const SAFE_MAX = 24.0;
    const CRITICAL_MIN = 14.0;
    const CRITICAL_MAX = 26.0;

    // Build datasets
    const datasets = [];

    // Temperature line
    if (hasData) {
      datasets.push({
        label: 'Water Temperature',
        data: tempData.map(d => ({ x: d.ts, y: d.value })),
        borderColor: 'rgba(59, 130, 246, 0.9)',  // blue-500
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        borderWidth: 2,
        pointRadius: 1,
        pointHoverRadius: 4,
        tension: 0.3,
        fill: false,
        yAxisID: 'y'
      });
    }

    // Chiller state overlay (background shading)
    if (chillerEvents && chillerEvents.length > 0) {
      const chillerZones = [];
      let lastState = false;
      let lastTime = null;

      chillerEvents.forEach((evt, idx) => {
        if (lastTime && lastState) {
          // Create zone for chiller ON period
          chillerZones.push({
            x: lastTime,
            y: CRITICAL_MAX,
            x2: evt.ts,
            label: 'ON'
          });
        }
        lastState = evt.state;
        lastTime = evt.ts;
      });

      // Add zones as separate dataset for better control
      if (chillerZones.length > 0) {
        datasets.push({
          label: 'Chiller ON',
          data: chillerZones.map(z => ({ x: z.x, y: 26 })),
          backgroundColor: 'rgba(34, 197, 94, 0.08)',
          borderColor: 'rgba(34, 197, 94, 0.4)',
          borderWidth: 0,
          pointRadius: 0,
          showLine: false,
          yAxisID: 'y'
        });
      }
    }

    // Build annotation zones for temperature ranges
    const annotations = {};

    // Optimal zone (18-20°C) - green
    annotations.optimalZone = {
      type: 'box',
      yMin: OPTIMAL_MIN,
      yMax: OPTIMAL_MAX,
      backgroundColor: 'rgba(34, 197, 94, 0.05)',
      borderWidth: 0,
      label: {
        display: true,
        content: 'Optimal (18-20°C)',
        position: 'start',
        color: 'rgba(34, 197, 94, 0.8)',
        font: { size: 10, weight: 'bold' },
        padding: 4
      }
    };

    // Safe zone warning boundaries (16°C and 24°C) - yellow
    annotations.safeMinLine = {
      type: 'line',
      yMin: SAFE_MIN,
      yMax: SAFE_MIN,
      borderColor: 'rgba(251, 146, 60, 0.6)',
      borderWidth: 1,
      borderDash: [5, 5],
      label: {
        display: true,
        content: '16°C (Safe min)',
        position: 'start',
        color: 'rgba(251, 146, 60, 0.9)',
        font: { size: 9 },
        padding: 2
      }
    };

    annotations.safeMaxLine = {
      type: 'line',
      yMin: SAFE_MAX,
      yMax: SAFE_MAX,
      borderColor: 'rgba(251, 146, 60, 0.6)',
      borderWidth: 1,
      borderDash: [5, 5],
      label: {
        display: true,
        content: '24°C (Safe max)',
        position: 'end',
        color: 'rgba(251, 146, 60, 0.9)',
        font: { size: 9 },
        padding: 2
      }
    };

    // Critical boundaries (14°C and 26°C) - red
    annotations.critMinLine = {
      type: 'line',
      yMin: CRITICAL_MIN,
      yMax: CRITICAL_MIN,
      borderColor: 'rgba(239, 68, 68, 0.6)',
      borderWidth: 2,
      borderDash: [3, 3],
      label: {
        display: true,
        content: '14°C (Critical)',
        position: 'start',
        color: 'rgba(239, 68, 68, 0.9)',
        font: { size: 9, weight: 'bold' },
        padding: 2
      }
    };

    annotations.critMaxLine = {
      type: 'line',
      yMin: CRITICAL_MAX,
      yMax: CRITICAL_MAX,
      borderColor: 'rgba(239, 68, 68, 0.6)',
      borderWidth: 2,
      borderDash: [3, 3],
      label: {
        display: true,
        content: '26°C (Critical)',
        position: 'end',
        color: 'rgba(239, 68, 68, 0.9)',
        font: { size: 9, weight: 'bold' },
        padding: 2
      }
    };

    // Target temperature line (from config)
    if (config.targetTemp != null && !isNaN(config.targetTemp)) {
      annotations.targetLine = {
        type: 'line',
        yMin: config.targetTemp,
        yMax: config.targetTemp,
        borderColor: 'rgba(168, 85, 247, 0.8)',  // purple-500
        borderWidth: 2,
        borderDash: [8, 4],
        label: {
          display: true,
          content: `Target: ${config.targetTemp.toFixed(1)}°C`,
          position: { x: 'center', y: 'start' },
          backgroundColor: 'rgba(168, 85, 247, 0.9)',
          color: '#fff',
          font: { size: 11, weight: 'bold' },
          padding: 4
        }
      };
    }

    // Create chart
    TEMP_CHART = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: hasData ? datasets : [{
          label: 'No data',
          data: [],
          showLine: false,
          pointRadius: 0.0001,
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        parsing: false,
        interaction: {
          mode: 'nearest',
          intersect: false
        },
        plugins: {
          legend: { 
            display: true,
            position: 'top'
          },
          tooltip: {
            enabled: true,
            callbacks: {
              label: (ctx) => {
                const label = ctx.dataset.label || '';
                const val = ctx.parsed.y;
                if (val == null) return label;
                return `${label}: ${val.toFixed(2)}°C`;
              }
            }
          },
          annotation: {
            annotations: annotations
          }
        },
        scales: {
          x: {
            type: 'time',
            adapters: { date: {} },
            min: tmin || undefined,
            max: tmax || undefined,
            ticks: { source: 'auto' }
          },
          y: {
            type: 'linear',
            position: 'left',
            title: { display: true, text: 'Temperature (°C)' },
            min: Math.max(12, CRITICAL_MIN - 1),
            max: Math.min(28, CRITICAL_MAX + 1)
          }
        }
      }
    });

    TEMP_STATE.startISO = tmin;
    TEMP_STATE.endISO = tmax;
    TEMP_STATE.lastCount = hasData ? tempData.length : 0;

    console.log(`[Temp] Chart built: ${TEMP_STATE.lastCount} points`);
  }

  /**
   * Fetch temperature history and chiller events, then render chart
   */
  async function loadTempHistory(startISO, endISO) {
    try {
      // Fetch temperature data from trends endpoint
      const sensorResp = await fetch(`/api/trends?from=${startISO}&to=${endISO}&gran=300`, {
        cache: 'no-store'
      });
      
      if (!sensorResp.ok) {
        throw new Error(`Trends failed: ${sensorResp.status}`);
      }

      const trendsData = await sensorResp.json();
      
      // Extract temperature readings from series.temp
      const tempSeries = trendsData.series?.temp || [];
      const tempData = tempSeries
        .filter(r => r.value != null && !isNaN(r.value))
        .map(r => ({
          ts: new Date(r.ts * 1000).toISOString(),  // Convert Unix timestamp to ISO
          value: r.value
        }));

      // Fetch chiller events
      let chillerEvents = [];
      try {
        const chillerResp = await fetch(`/api/chiller/events?start=${startISO}&end=${endISO}`, {
          cache: 'no-store'
        });
        if (chillerResp.ok) {
          const chillerData = await chillerResp.json();
          chillerEvents = chillerData.events || [];
        }
      } catch (e) {
        console.warn('[Temp] Chiller events not available:', e);
      }

      // Get current target temperature
      let targetTemp = 19.0;  // default
      try {
        const settingsResp = await fetch('/api/settings', { cache: 'no-store' });
        if (settingsResp.ok) {
          const settings = await settingsResp.json();
          targetTemp = parseFloat(settings['chiller.target_temp']) || 19.0;
        }
      } catch (e) {
        console.warn('[Temp] Could not fetch target temp:', e);
      }

      // Build chart
      buildTempChart(tempData, chillerEvents, startISO, endISO, { targetTemp });

      // Update stats
      updateTempStats(tempData, chillerEvents);

    } catch (err) {
      console.error('[Temp] Failed to load history:', err);
      const empty = document.getElementById('temp-history-empty');
      if (empty) {
        empty.style.display = 'block';
        empty.textContent = 'Failed to load temperature history';
      }
    }
  }

  /**
   * Calculate and display temperature statistics
   */
  function updateTempStats(tempData, chillerEvents) {
    if (!tempData || tempData.length === 0) return;

    const temps = tempData.map(d => d.value);
    const avgTemp = temps.reduce((a, b) => a + b, 0) / temps.length;
    const minTemp = Math.min(...temps);
    const maxTemp = Math.max(...temps);

    // Calculate time in optimal range
    const inOptimal = temps.filter(t => t >= 18.0 && t <= 20.0).length;
    const optimalPercent = (inOptimal / temps.length * 100).toFixed(1);

    // Calculate chiller runtime
    let totalRuntime = 0;
    let cycleCount = 0;
    if (chillerEvents && chillerEvents.length > 1) {
      let lastOn = null;
      chillerEvents.forEach(evt => {
        if (evt.state) {
          lastOn = new Date(evt.ts);
          cycleCount++;
        } else if (lastOn) {
          const offTime = new Date(evt.ts);
          totalRuntime += (offTime - lastOn) / 1000 / 60;  // minutes
          lastOn = null;
        }
      });
    }

    // Update UI elements if they exist
    const statsEl = document.getElementById('temp-stats-summary');
    if (statsEl) {
      statsEl.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;font-size:0.8rem;">
          <div>
            <div class="muted" style="font-size:0.7rem;">Average</div>
            <div style="font-weight:600;color:#93c5fd;">${avgTemp.toFixed(2)}°C</div>
          </div>
          <div>
            <div class="muted" style="font-size:0.7rem;">Min / Max</div>
            <div style="font-weight:600;color:#cbd5e1;">${minTemp.toFixed(1)}°C / ${maxTemp.toFixed(1)}°C</div>
          </div>
          <div>
            <div class="muted" style="font-size:0.7rem;">In Optimal</div>
            <div style="font-weight:600;color:#a7f3d0;">${optimalPercent}%</div>
          </div>
          <div>
            <div class="muted" style="font-size:0.7rem;">Chiller Runtime</div>
            <div style="font-weight:600;color:#d8b4fe;">${totalRuntime.toFixed(0)} min (${cycleCount} cycles)</div>
          </div>
        </div>
      `;
    }
  }

  /**
   * Handle time range selection
   */
  function handleTimeRangeChange() {
    const select = document.getElementById('temp-history-range');
    if (!select) return;

    const range = select.value;
    const now = new Date();
    let start, end = now;

    switch (range) {
      case '24h':
        start = new Date(now - 24 * 60 * 60 * 1000);
        break;
      case '7d':
        start = new Date(now - 7 * 24 * 60 * 60 * 1000);
        break;
      case '30d':
        start = new Date(now - 30 * 24 * 60 * 60 * 1000);
        break;
      case '90d':
        start = new Date(now - 90 * 24 * 60 * 60 * 1000);
        break;
      default:
        start = new Date(now - 24 * 60 * 60 * 1000);
    }

    loadTempHistory(start.toISOString(), end.toISOString());
  }

  // Initialize on page load
  document.addEventListener('DOMContentLoaded', () => {
    const rangeSelect = document.getElementById('temp-history-range');
    if (rangeSelect) {
      rangeSelect.addEventListener('change', handleTimeRangeChange);
      // Load initial data
      handleTimeRangeChange();
    }

    // Refresh every 60 seconds when tab is visible
    setInterval(() => {
      const card = document.getElementById('temp-card');
      if (card && card.style.display !== 'none') {
        handleTimeRangeChange();
      }
    }, 60000);
  });

  // Export for external use
  window.loadTempHistory = loadTempHistory;
  window.buildTempChart = buildTempChart;

})();
