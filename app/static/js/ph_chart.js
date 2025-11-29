// pH Dose Chart Rendering Module
// Shows pH sensor readings over time (hysteresis) with dose events overlaid
(function(){
  console.log('[pH Chart] Loader enter (ph_chart.js start)');
  'use strict';

  // Module state
  let PH_CHART = null;
  let PH_CHART_STATE = { lastStart: null, lastEnd: null, lastCount: 0 };

  // Ensure Chart.js time scale is available (v3/v4 compatible)
  if (window.Chart && Chart.register && window.RDWC_CHART_REG === undefined) {
    // Chart.js v4 UMD auto-registers, but be defensive
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
        Chart.plugins.Title
      );
      // Register annotation plugin if available
      if (window.chartjs && window.chartjs.Annotation) {
        Chart.register(window.chartjs.Annotation);
      } else if (window.ChartAnnotation) {
        Chart.register(window.ChartAnnotation);
      }
    } catch(e) {
      // Already registered or UMD handled it
      console.debug('[pH] Chart.js controllers already registered');
    }
    window.RDWC_CHART_REG = true;
  }

  /**
   * Build or rebuild the pH chart with pH readings line and dose events overlay
   * @param {Array} datasets - Chart.js datasets
   * @param {string|null} timeMin - ISO timestamp or null
   * @param {string|null} timeMax - ISO timestamp or null
   * @param {number|null} currentPH - Current live pH reading
   * @param {Object|null} targets - {low: number, high: number} pH target range
   * @param {Object|null} phReadings - Array of {x: Date, y: number} pH sensor readings
   */
  function phBuildChart(datasets, timeMin, timeMax, currentPH, targets, phReadings) {
    const el = document.getElementById('phDoseChart');
    const empty = document.getElementById('ph-dose-empty');

    if (!el) {
      console.error('[pH] Canvas #phDoseChart not found.');
      return;
    }

    // Check if we have pH readings data (primary) or dose events (secondary)
    const hasPhReadings = phReadings && phReadings.length > 0;
    const hasDoseData = datasets && datasets.some(ds => (ds.data||[]).length > 0);
    const hasData = hasPhReadings || hasDoseData;
    
    if (empty) {
      empty.style.display = hasData ? 'none' : 'block';
    }

    const ctx = el.getContext('2d');

    // Destroy previous
    if (PH_CHART && typeof PH_CHART.destroy === 'function') {
      PH_CHART.destroy();
      PH_CHART = null;
    }

    // Calculate pH axis range based on data and targets
    let phMin = 4.5, phMax = 8.0;  // Default range for pH
    if (hasPhReadings) {
      const phValues = phReadings.map(p => p.y).filter(v => v != null && !isNaN(v));
      if (phValues.length > 0) {
        const dataMin = Math.min(...phValues);
        const dataMax = Math.max(...phValues);
        // Expand range to include data with padding
        phMin = Math.min(phMin, dataMin - 0.2);
        phMax = Math.max(phMax, dataMax + 0.2);
      }
    }
    // Include targets in range
    if (targets && targets.low != null) phMin = Math.min(phMin, targets.low - 0.3);
    if (targets && targets.high != null) phMax = Math.max(phMax, targets.high + 0.3);
    // Include current pH in range
    if (currentPH != null) {
      phMin = Math.min(phMin, currentPH - 0.2);
      phMax = Math.max(phMax, currentPH + 0.2);
    }

    // Build annotation plugin config for pH reference line, hysteresis band, and setpoint
    const annotations = {};
    if (currentPH != null && !isNaN(currentPH)) {
      annotations.phLine = {
        type: 'line',
        yMin: currentPH,
        yMax: currentPH,
        yScaleID: 'yPh',
        borderColor: 'rgba(251, 191, 36, 0.8)',  // amber-400
        borderWidth: 2,
        borderDash: [6, 4],
        label: {
          display: true,
          content: `Current pH: ${currentPH.toFixed(2)}`,
          position: 'start',
          backgroundColor: 'rgba(251, 191, 36, 0.9)',
          color: '#000',
          font: { size: 11, weight: 'bold' },
          padding: 4
        }
      };
    }
    
    // Add hysteresis band (shaded region between low and high targets)
    if (targets && targets.low != null && targets.high != null && !isNaN(targets.low) && !isNaN(targets.high)) {
      annotations.phBand = {
        type: 'box',
        yMin: targets.low,
        yMax: targets.high,
        yScaleID: 'yPh',
        backgroundColor: 'rgba(34, 197, 94, 0.12)',  // green with low opacity
        borderWidth: 0,
        drawTime: 'beforeDatasetsDraw'  // Draw band behind data
      };
      
      // Add setpoint line (midpoint of targets)
      const setpoint = (targets.low + targets.high) / 2;
      annotations.phSetpoint = {
        type: 'line',
        yMin: setpoint,
        yMax: setpoint,
        yScaleID: 'yPh',
        borderColor: 'rgba(34, 197, 94, 0.5)',  // green-500 with transparency
        borderWidth: 1.5,
        borderDash: [4, 4],
        label: {
          display: true,
          content: `Setpoint: ${setpoint.toFixed(1)}`,
          position: 'end',
          backgroundColor: 'rgba(34, 197, 94, 0.8)',
          color: '#fff',
          font: { size: 10 },
          padding: 3
        }
      };
    }

    // Build final datasets array: pH readings line first, then dose datasets
    const finalDatasets = [];
    
    // Add pH readings line dataset (primary)
    if (hasPhReadings) {
      finalDatasets.push({
        type: 'line',
        label: 'pH',
        data: phReadings,
        order: 0,  // Draw first (behind others)
        yAxisID: 'yPh',
        borderColor: '#3b82f6',  // blue-500
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
        spanGaps: true
      });
    }
    
    // Add dose event datasets (on secondary Y-axis)
    if (datasets && datasets.length > 0) {
      datasets.forEach(ds => {
        // Clone and assign to dose Y-axis
        finalDatasets.push({
          ...ds,
          yAxisID: 'yDose'
        });
      });
    }
    
    // Ensure at least one stub dataset so legend/axes render
    const dsUse = finalDatasets.length > 0 ? finalDatasets : [{
      label: 'No data',
      data: [],
      showLine: false,
      pointRadius: 0.0001,
      borderWidth: 0
    }];

    // Check if we have dose data for secondary axis
    const hasDoseAxis = dsUse.some(ds => ds.yAxisID === 'yDose' && (ds.data||[]).length > 0);

    PH_CHART = new Chart(ctx, {
      type: 'line',
      data: { datasets: dsUse },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        parsing: false,
        interaction: {
          mode: 'nearest',
          intersect: false
        },
        scales: {
          x: {
            type: 'time',
            adapters: { date: {} },
            min: timeMin || undefined,
            max: timeMax || undefined,
            ticks: { source: 'auto', maxRotation: 0, autoSkip: true },
            time: {
              tooltipFormat: 'yyyy-MM-dd HH:mm',
              displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'MMM d' }
            },
            grid: { color: 'rgba(148,163,184,0.15)', drawTicks: false }
          },
          yPh: {
            type: 'linear',
            position: 'left',
            title: { display: true, text: 'pH' },
            min: phMin,
            max: phMax,
            grid: { color: 'rgba(148,163,184,0.12)', drawTicks: false }
          },
          yDose: {
            type: 'linear',
            position: 'right',
            title: { display: hasDoseAxis, text: 'Dose (ml)' },
            display: hasDoseAxis,
            beginAtZero: true,
            grid: { drawOnChartArea: false }  // Don't draw grid on chart area
          }
        },
        plugins: {
          legend: { 
            display: true,
            position: 'top',
            labels: { usePointStyle: true, boxWidth: 10, padding: 12 }
          },
          tooltip: {
            enabled: true,
            callbacks: {
              label: (ctx) => {
                const p = ctx.raw;
                const ds = ctx.dataset;
                
                // pH readings tooltip
                if (ds.label === 'pH') {
                  const v = Number(ctx.parsed.y);
                  return ` pH: ${v.toFixed(2)}`;
                }
                
                // Cumulative line tooltip
                if (ds.label && ds.label.includes('Cumulative')) {
                  return `Total: ${ctx.parsed.y.toFixed(1)} ml`;
                }
                
                // Daily bar tooltip
                if (ds.label && ds.label.includes('Daily')) {
                  return `Day total: ${ctx.parsed.y.toFixed(1)} ml`;
                }
                
                // Dose event tooltip
                if (!p) return '';
                const ml = (p.ml != null) ? `+${p.ml.toFixed(2)} ml` : (p.sec != null ? `~${p.sec.toFixed(2)} s` : '');
                const ph = (p.phb != null || p.pha != null) ? `  pH: ${p.phb ?? '—'} → ${p.pha ?? '—'}` : '';
                return `${ml}${ph}`;
              }
            }
          },
          annotation: {
            annotations: annotations
          }
        }
      }
    });

    console.debug('[pH] Chart created/rebuilt', { hasData, hasPhReadings, hasDoseData, datasetCount: dsUse.length, currentPH });
  }

  // Granularity constants for time-based bucketing (in seconds)
  const GRANULARITY = {
    FINE: 30,       // 30-second buckets for short ranges (<2h)
    MINUTE: 60,     // 1-minute buckets for day ranges
    FIVE_MIN: 300,  // 5-minute buckets for week ranges
    QUARTER: 900,   // 15-minute buckets for month ranges
    HOURLY: 3600    // Hourly buckets for 90+ days
  };

  /**
   * Compute granularity params based on time range (matching trends.js logic)
   */
  function presetParams(spanMs) {
    const hours = spanMs / (3600 * 1000);
    if (hours <= 2)   return { gran: GRANULARITY.FINE,     max: 1000 };  // 30s buckets for short ranges
    if (hours <= 24)  return { gran: GRANULARITY.MINUTE,   max: 1500 };  // 1-min buckets
    if (hours <= 168) return { gran: GRANULARITY.FIVE_MIN, max: 2100 };  // 5-min buckets (7 days)
    if (hours <= 720) return { gran: GRANULARITY.QUARTER,  max: 3000 };  // 15-min buckets (30 days)
    return { gran: GRANULARITY.HOURLY, max: 2500 };  // hourly buckets (90+ days)
  }

  /**
   * Fetch pH sensor readings from trends API
   */
  async function fetchPhReadings(fromISO, toISO, gran, max) {
    const q = new URLSearchParams();
    if (fromISO) q.set('from', fromISO);
    if (toISO) q.set('to', toISO);
    if (gran) q.set('gran', String(gran));
    if (max) q.set('max', String(max));
    
    const url = '/api/trends?' + q.toString();
    console.log('[pH Chart] Fetching pH readings from:', url);
    
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) {
        console.warn('[pH Chart] Trends API failed:', res.status);
        return [];
      }
      const data = await res.json();
      const phSeries = data?.series?.ph || [];
      console.log('[pH Chart] Got pH readings:', phSeries.length);
      
      // Convert to Chart.js format: {x: Date, y: number}
      // API returns timestamps in Unix epoch seconds, multiply by 1000 to convert to milliseconds for Date
      return phSeries.map(p => ({
        x: new Date(p.ts * 1000),  // Unix seconds → milliseconds for Date constructor
        y: Number(p.value)
      })).filter(p => !isNaN(p.y));
    } catch (err) {
      console.error('[pH Chart] Failed to fetch pH readings:', err);
      return [];
    }
  }

  /**
   * Load dose data and pH readings for a given range and render the chart
   * @param {Object} params - {start: ISO string, end: ISO string}
   */
  async function phLoadRangeAndRender({start, end}) {
    const wrap = (id, v) => { console.debug(`[pH] ${id}:`, v); return v; };

    // Normalize inputs: accept epoch ms numbers or ISO strings; always send ISO with 'Z'
    const toIso = (v) => {
      if (v == null) return null;
      // If already looks like an ISO string, pass through (ensure Z if missing timezone by treating as Date)
      if (typeof v === 'string') {
        // If string has no timezone, coerce via Date to normalize to UTC Z
        try {
          const d = new Date(v);
          if (!isNaN(d.getTime())) return d.toISOString();
        } catch(e) {/* fallthrough */}
        return v;
      }
      if (typeof v === 'number') {
        const d = new Date(v);
        return isNaN(d.getTime()) ? null : d.toISOString();
      }
      return null;
    };

    const startISO = toIso(start);
    const endISO = toIso(end);

    console.log('[pH Chart] Range request', {start, end, startISO, endISO});

    // Calculate time span for granularity
    const startMs = startISO ? new Date(startISO).getTime() : Date.now() - 24*3600*1000;
    const endMs = endISO ? new Date(endISO).getTime() : Date.now();
    const spanMs = endMs - startMs;
    const { gran, max } = presetParams(spanMs);

    // Build URLs for events, summary, and live pH
    const uEvents = `/api/ph/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`;
    const uSummary = `/api/ph/dose_summary?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`;
    const uStatus = `/api/ph/status`;

    console.log('[pH Chart] Fetching', {uEvents, uSummary, uStatus, gran, max});

    let events = [];
    let summary = [];
    let currentPH = null;
    let targets = null;
    let phReadings = [];
    
    try {
      // Fetch all data in parallel: dose events, summary, status, AND pH readings
      const [eRes, sRes, stRes, phData] = await Promise.all([
        fetch(uEvents, {cache:'no-store'}), 
        fetch(uSummary, {cache:'no-store'}),
        fetch(uStatus, {cache:'no-store'}),
        fetchPhReadings(startISO, endISO, gran, max)
      ]);
      
      console.log('[pH Chart] Response status', {events: eRes.status, summary: sRes.status, status: stRes.status, phReadings: phData.length});
      
      if (!eRes.ok) throw new Error(`dose_log HTTP ${eRes.status}`);
      if (!sRes.ok) throw new Error(`dose_summary HTTP ${sRes.status}`);
      
      events = await eRes.json();
      summary = await sRes.json();
      phReadings = phData;
      
      if (stRes.ok) {
        const statusData = await stRes.json();
        currentPH = statusData?.ph ?? null;
        targets = statusData?.targets ?? null;
      }
    } catch (err) {
      console.error('[pH Chart] fetch error:', err);
      phBuildChart([], null, null, null, null, []);
      return;
    }

    console.log('[pH Chart] Data received', {events: events.length, summary: summary.length, phReadings: phReadings.length});

    // Build dose event datasets
    const hasAnyMl = events.some(r => r && r.volume_ml != null);
    console.log('[pH Chart] hasAnyMl:', hasAnyMl, 'sample event:', events[0]);
    
    // Dose events as scatter points (shown on secondary Y-axis)
    const dosePoints = events.map(r => ({
      x: new Date(r.ts),  // Convert ISO string to Date object for Chart.js
      y: hasAnyMl ? (r.volume_ml != null ? r.volume_ml : 0) : (r.seconds ?? 0),
      ml: (r.volume_ml != null ? r.volume_ml : null),
      sec: r.seconds ?? null,
      phb: r.ph_before ?? null,
      pha: r.ph_after ?? null
    }));
    console.log('[pH Chart] Sample dose point:', dosePoints[0]);

    // Build dose datasets
    const doseDatasets = [];
    
    // Dose events scatter (green triangle markers)
    if (dosePoints.length > 0) {
      doseDatasets.push({
        type: 'scatter',
        label: hasAnyMl ? 'Dose (ml)' : 'Dose (s)',
        data: dosePoints,
        order: 1,
        pointRadius: 5,
        pointStyle: 'triangle',
        backgroundColor: 'rgba(34, 197, 94, 0.9)',  // green
        borderColor: 'rgba(34, 197, 94, 1)',
        borderWidth: 1
      });
    }

    // Render chart with pH readings as line and dose events as scatter
    const tmin = startISO ? new Date(startISO) : null;
    const tmax = endISO ? new Date(endISO) : null;
    console.log('[pH Chart] Axis bounds (from request)', {tmin, tmax, startISO, endISO, currentPH, targets, phReadingsCount: phReadings.length});
    phBuildChart(doseDatasets, tmin, tmax, currentPH, targets, phReadings);

    // Update "In range" pill
    const pill = document.getElementById('ph-in-range');
    if (pill) {
      if (hasAnyMl) {
        const sumMl = events.reduce((a, r) => a + (r.volume_ml ?? 0), 0);
        pill.textContent = `In range: ${sumMl.toFixed(1)} ml`;
      } else {
        const sumSec = events.reduce((a, r) => a + (r.seconds ?? 0), 0);
        pill.textContent = sumSec > 0 ? `In range: ${Math.round(sumSec)} s` : 'In range: — s';
      }
    }

    PH_CHART_STATE = { lastStart: startISO || start || null, lastEnd: endISO || end || null, lastCount: events.length };
    console.log('[pH Chart] ✅ Render complete', PH_CHART_STATE);
  }

  /**
   * Initialize on DOM ready with default 24h range
   */
  function init() {
    console.log('[pH Chart] 🚀 Init: DOM ready; boot dose chart with default 24h');
    
    // Compute default start/end (24h)
    const now = new Date();
    const start = new Date(now.getTime() - 24*3600*1000).toISOString();
    const end = now.toISOString();
    
    console.log('[pH Chart] Default range', {start, end});
    phLoadRangeAndRender({start, end});
  }

  // Export functions for external use
  window.phDoseChart = {
    render: phLoadRangeAndRender,
    getState: () => PH_CHART_STATE,
    init: init
  };

  // Auto-init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  console.log('[pH Chart] Module initialized and window.phDoseChart exported');

})();
