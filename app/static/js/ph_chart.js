// pH Dose Chart Rendering Module
// Bulletproof chart initialization with empty-state handling and diagnostics
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
   * Build or rebuild the dose chart with given datasets
   * @param {Array} datasets - Chart.js datasets
   * @param {string|null} timeMin - ISO timestamp or null
   * @param {string|null} timeMax - ISO timestamp or null
   * @param {string|null} axisTitle - Y-axis label
   * @param {number|null} currentPH - Current live pH reading
   */
  function phBuildChart(datasets, timeMin, timeMax, axisTitle, currentPH) {
    const el = document.getElementById('phDoseChart');
    const empty = document.getElementById('ph-dose-empty');

    if (!el) {
      console.error('[pH] Canvas #phDoseChart not found.');
      return;
    }

    // Show empty hint if no data, but still build a stub chart so axes/legend exist
    const hasData = datasets && datasets.some(ds => (ds.data||[]).length > 0);
    if (empty) {
      empty.style.display = hasData ? 'none' : 'block';
    }

    const ctx = el.getContext('2d');

    // Destroy previous
    if (PH_CHART && typeof PH_CHART.destroy === 'function') {
      PH_CHART.destroy();
      PH_CHART = null;
    }

    // Ensure at least one stub dataset so legend/axes render
    const dsUse = (hasData ? datasets : [{
      label: 'No doses',
      data: [],
      showLine: false,
      pointRadius: 0.0001,   // invisible but forces legend/axes init
      borderWidth: 0
    }]);

    // Check if we have a cumulative dataset that needs a second Y-axis
    const hasCumulative = dsUse.some(ds => ds.yAxisID === 'y2');

    // Build annotation plugin config for pH reference line
    const annotations = {};
    if (currentPH != null && !isNaN(currentPH)) {
      annotations.phLine = {
        type: 'line',
        yMin: currentPH,
        yMax: currentPH,
        yScaleID: 'y',
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

    PH_CHART = new Chart(ctx, {
      type: 'scatter', // will mix with bars and lines
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
            ticks: { source: 'auto' }
          },
          y: {
            type: 'linear',
            position: 'left',
            title: { display: true, text: axisTitle || 'Dose (ml)' },
            beginAtZero: true
          }
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
                const p = ctx.raw;
                const ds = ctx.dataset;
                
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

    console.debug('[pH] Chart created/rebuilt', { hasData, datasetCount: dsUse.length, currentPH });
  }

  /**
   * Load dose data for a given range and render the chart
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

    // Build URLs for events, summary, and live pH
    const uEvents = `/api/ph/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`;
    const uSummary = `/api/ph/dose_summary?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`;
    const uStatus = `/api/ph/status`;

    console.log('[pH Chart] Fetching', {uEvents, uSummary, uStatus});

    let events = [];
    let summary = [];
    let currentPH = null;
    try {
      const [eRes, sRes, stRes] = await Promise.all([
        fetch(uEvents, {cache:'no-store'}), 
        fetch(uSummary, {cache:'no-store'}),
        fetch(uStatus, {cache:'no-store'})
      ]);
      console.log('[pH Chart] Response status', {events: eRes.status, summary: sRes.status, status: stRes.status});
      if (!eRes.ok) throw new Error(`dose_log HTTP ${eRes.status}`);
      if (!sRes.ok) throw new Error(`dose_summary HTTP ${sRes.status}`);
      events = await eRes.json();
      summary = await sRes.json();
      if (stRes.ok) {
        const statusData = await stRes.json();
        currentPH = statusData?.ph ?? null;
      }
    } catch (err) {
      console.error('[pH Chart] fetch error:', err);
      phBuildChart([], null, null, null);
      return;
    }

    console.log('[pH Chart] Data received', {events: events.length, summary: summary.length});

    // Build datasets
    const hasAnyMl = events.some(r => r && r.volume_ml != null);
    console.log('[pH Chart] hasAnyMl:', hasAnyMl, 'sample event:', events[0]);
    const pts = events.map(r => ({
      x: new Date(r.ts),  // Convert ISO string to Date object for Chart.js
      y: hasAnyMl ? (r.volume_ml != null ? r.volume_ml : 0) : (r.seconds ?? 0),
      ml: (r.volume_ml != null ? r.volume_ml : null),
      sec: r.seconds ?? null,
      phb: r.ph_before ?? null,
      pha: r.ph_after ?? null
    }));
    console.log('[pH Chart] Sample point:', pts[0]);

    // Build cumulative total line (running sum over time)
    const cumulative = [];
    if (hasAnyMl && events.length > 0) {
      let runningTotal = 0;
      events.forEach(r => {
        runningTotal += (r.volume_ml ?? 0);
        cumulative.push({
          x: new Date(r.ts),
          y: runningTotal
        });
      });
    }

    // When long windows, also build a bar dataset from summary (only meaningful when ml calibration exists)
    const bars = hasAnyMl ? summary.map(d => ({
      x: new Date(d.day),  // Convert day string to Date object
      y: d.total_ml ?? 0
    })) : [];

    const haveBars = bars.length > 0;
    const haveCumulative = cumulative.length > 0;
    
    const datasets = [
      haveBars ? {
        type: 'bar',
        label: 'Daily total (ml)',
        data: bars,
        order: 3,
        backgroundColor: 'rgba(34,197,94,0.35)',
        borderColor: 'rgba(34,197,94,0.6)',
        yAxisID: 'y'
      } : null,
      haveCumulative ? {
        type: 'line',
        label: 'Cumulative total (ml)',
        data: cumulative,
        order: 2,
        borderColor: 'rgba(168,85,247,0.8)',
        backgroundColor: 'rgba(168,85,247,0.1)',
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0,
        yAxisID: 'y'
      } : null,
      {
        type: 'scatter',
        label: hasAnyMl ? 'Dose events (ml)' : 'Dose events (s)',
        data: pts,
        order: 1,
        pointRadius: 3,
        backgroundColor: 'rgba(59,130,246,0.9)',
        yAxisID: 'y'
      }
    ].filter(Boolean);

    // Render chart
    const axisTitle = hasAnyMl ? 'Dose (ml)' : 'Dose (s)';
    // Use the REQUESTED timeframe for axis bounds (not data bounds)
    // This ensures the full timeframe is visible even with sparse data
    const tmin = startISO ? new Date(startISO) : null;
    const tmax = endISO ? new Date(endISO) : null;
    console.log('[pH Chart] Axis bounds (from request)', {tmin, tmax, startISO, endISO, currentPH});
    phBuildChart(datasets, tmin, tmax, axisTitle, currentPH);

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
