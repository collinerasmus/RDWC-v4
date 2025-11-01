// pH Dose Chart Rendering Module
// Bulletproof chart initialization with empty-state handling and diagnostics
(function(){
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
   */
  function phBuildChart(datasets, timeMin, timeMax) {
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

    PH_CHART = new Chart(ctx, {
      type: 'scatter', // will mix with bars if you add them later
      data: { datasets: dsUse },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        parsing: false,
        scales: {
          x: {
            type: 'time',
            adapters: { date: {} },
            min: timeMin || undefined,
            max: timeMax || undefined,
            ticks: { source: 'auto' }
          },
          y: {
            title: { display: true, text: 'Dose (ml)' },
            suggestedMin: 0
          }
        },
        plugins: {
          legend: { display: true },
          tooltip: {
            enabled: true,
            callbacks: {
              label: (ctx) => {
                const p = ctx.raw;
                if (!p) return '';
                const ml = (p.ml != null) ? `+${p.ml.toFixed(2)} ml` : (p.sec != null ? `~${p.sec.toFixed(2)} s` : '');
                const ph = (p.phb != null || p.pha != null) ? `  pH: ${p.phb ?? '—'} → ${p.pha ?? '—'}` : '';
                return `${ml}${ph}`;
              }
            }
          }
        }
      }
    });

    console.debug('[pH] Chart created/rebuilt', { hasData, datasetCount: dsUse.length });
  }

  /**
   * Load dose data for a given range and render the chart
   * @param {Object} params - {start: ISO string, end: ISO string}
   */
  async function phLoadRangeAndRender({start, end}) {
    const wrap = (id, v) => { console.debug(`[pH] ${id}:`, v); return v; };

    console.debug('[pH] Range request', {start, end});

    // Build URLs for events and summary
    const uEvents = `/api/ph/dose_log?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&limit=2000`;
    const uSummary = `/api/ph/dose_summary?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;

    let events = [];
    let summary = [];
    try {
      const [eRes, sRes] = await Promise.all([
        fetch(uEvents, {cache:'no-store'}), 
        fetch(uSummary, {cache:'no-store'})
      ]);
      if (!eRes.ok) throw new Error(`dose_log HTTP ${eRes.status}`);
      if (!sRes.ok) throw new Error(`dose_summary HTTP ${sRes.status}`);
      events = await eRes.json();
      summary = await sRes.json();
    } catch (err) {
      console.error('[pH] fetch error:', err);
      phBuildChart([], null, null);
      return;
    }

    wrap('events.len', events.length);
    wrap('summary.len', summary.length);

    // Build datasets
    const pts = events.map(r => ({
      x: r.ts, 
      y: (r.volume_ml != null ? r.volume_ml : 0),
      ml: (r.volume_ml != null ? r.volume_ml : null),
      sec: r.seconds ?? null,
      phb: r.ph_before ?? null,
      pha: r.ph_after ?? null
    }));

    // When long windows, also build a bar dataset from summary
    const bars = summary.map(d => ({
      x: d.day, 
      y: d.total_ml ?? 0
    }));

    const haveBars = bars.length > 0;
    const datasets = [
      haveBars ? {
        type: 'bar',
        label: 'Daily total (ml)',
        data: bars,
        order: 2,
        backgroundColor: 'rgba(34,197,94,0.35)',
        borderColor: 'rgba(34,197,94,0.6)'
      } : null,
      {
        type: 'scatter',
        label: 'Dose events',
        data: pts,
        order: 1,
        pointRadius: 3,
        backgroundColor: 'rgba(59,130,246,0.9)'
      }
    ].filter(Boolean);

    // Render chart
    const tmin = events.length ? events[0].ts : (summary[0]?.day ?? null);
    const tmax = events.length ? events[events.length-1].ts : (summary[summary.length-1]?.day ?? null);
    phBuildChart(datasets, tmin, tmax);

    // Update "In range" pill
    const sumMl = events.reduce((a, r) => a + (r.volume_ml ?? 0), 0);
    const hasAnyMl = events.some(r => r.volume_ml != null);
    const pill = document.getElementById('ph-in-range');
    if (pill) {
      pill.textContent = hasAnyMl ? `In range: ${sumMl.toFixed(1)} ml` : 'In range: — ml';
    }

    PH_CHART_STATE = { lastStart: start, lastEnd: end, lastCount: events.length };
    console.debug('[pH] Render complete', PH_CHART_STATE);
  }

  /**
   * Initialize on DOM ready with default 24h range
   */
  function init() {
    console.debug('[pH] DOM ready; boot dose chart.');
    
    // Compute default start/end (24h)
    const now = new Date();
    const start = new Date(now.getTime() - 24*3600*1000).toISOString().slice(0,19);
    const end = now.toISOString().slice(0,19);
    
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

})();
