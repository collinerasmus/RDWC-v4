// EC Dose Chart Rendering Module
(function(){
  'use strict';

  let EC_CHART = null;
  let EC_STATE = { startISO: null, endISO: null, lastCount: 0 };

  // Defensive Chart.js registration (v4 UMD usually auto-registers)
  if (window.Chart && Chart.register && window.RDWC_CHART_REG_EC === undefined) {
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
    } catch (e) {
      // ignore
    }
    window.RDWC_CHART_REG_EC = true;
  }

  function buildChart(datasets, tmin, tmax, axisTitle) {
    const el = document.getElementById('ecDoseChart');
    const empty = document.getElementById('ec-dose-empty');
    if (!el) return;

    const hasData = datasets && datasets.some(ds => (ds.data||[]).length > 0);
    if (empty) empty.style.display = hasData ? 'none' : 'block';

    const ctx = el.getContext('2d');
    if (EC_CHART && typeof EC_CHART.destroy === 'function') {
      EC_CHART.destroy();
      EC_CHART = null;
    }

    const dsUse = hasData ? datasets : [{
      label: 'No doses',
      data: [],
      showLine: false,
      pointRadius: 0.0001,
      borderWidth: 0
    }];

    const hasCumulative = dsUse.some(ds => ds.yAxisID === 'y2');

    EC_CHART = new Chart(ctx, {
      type: 'scatter',
      data: { datasets: dsUse },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        parsing: false,
        interaction: { mode: 'nearest', intersect: false },
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
            title: { display: true, text: axisTitle || 'Dose (ml)' },
            suggestedMin: 0
          },
          y2: hasCumulative ? {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'Cumulative (ml)' },
            suggestedMin: 0,
            grid: { drawOnChartArea: false }
          } : undefined
        },
        plugins: {
          legend: { display: true, position: 'top' },
          tooltip: {
            enabled: true,
            callbacks: {
              label: (ctx) => {
                const p = ctx.raw;
                const ds = ctx.dataset;
                if (ds.label && ds.label.includes('Cumulative')) {
                  return `Total: ${ctx.parsed.y.toFixed(1)} ml`;
                }
                if (ds.label && ds.label.includes('Daily')) {
                  return `Day total: ${ctx.parsed.y.toFixed(1)} ml`;
                }
                if (!p) return '';
                const ml = (p.ml != null) ? `+${p.ml.toFixed(2)} ml` : (p.sec != null ? `~${p.sec.toFixed(2)} s` : '');
                const ec = (p.ecb != null || p.eca != null) ? `  EC: ${p.ecb ?? '—'} → ${p.eca ?? '—'}` : '';
                return `${ml}${ec}`;
              }
            }
          }
        }
      }
    });
  }

  async function loadRangeAndRender({start, end}){
    // normalize inputs to ISO
    const toIso = (v) => {
      if (v == null) return null;
      if (typeof v === 'string') {
        try { const d = new Date(v); if (!isNaN(d)) return d.toISOString(); } catch(e) {}
        return v;
      }
      if (typeof v === 'number') {
        const d = new Date(v);
        return isNaN(d) ? null : d.toISOString();
      }
      return null;
    };
    const startISO = toIso(start);
    const endISO = toIso(end);

    let events = [];
    let summary = [];
    try{
      const [eRes, sRes] = await Promise.all([
        fetch(`/api/ec/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`, {cache:'no-store'}),
        fetch(`/api/ec/dose_summary?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`, {cache:'no-store'})
      ]);
      if (!eRes.ok) throw new Error(`dose_log HTTP ${eRes.status}`);
      if (!sRes.ok) throw new Error(`dose_summary HTTP ${sRes.status}`);
      events = await eRes.json();
      summary = await sRes.json();
    } catch(err){
      console.error('[EC Chart] fetch error:', err);
      buildChart([], null, null, 'Dose (ml)');
      return;
    }

  const hasAnyMl = events.some(r => r && r.volume_ml != null);
    const pts = events.map(r => ({
      x: new Date(r.ts),
      y: hasAnyMl ? (r.volume_ml != null ? r.volume_ml : 0) : (r.seconds ?? 0),
      ml: (r.volume_ml != null ? r.volume_ml : null),
      sec: r.seconds ?? null,
      ecb: r.ec_before ?? null,
      eca: r.ec_after ?? null
    }));

    const cumulative = [];
    if (hasAnyMl && events.length > 0) {
      let running = 0;
      events.forEach(r => {
        running += (r.volume_ml ?? 0);
        cumulative.push({ x: new Date(r.ts), y: running });
      });
    }

    const bars = hasAnyMl ? summary.map(d => ({ x: new Date(d.day), y: d.total_ml ?? 0 })) : [];

    const datasets = [
      bars.length ? {
        type: 'bar',
        label: 'Daily total (ml)',
        data: bars,
        order: 3,
        backgroundColor: 'rgba(34,197,94,0.35)',
        borderColor: 'rgba(34,197,94,0.6)',
        yAxisID: 'y'
      } : null,
      cumulative.length ? {
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
        yAxisID: 'y2'
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

    const axisTitle = hasAnyMl ? 'Dose (ml)' : 'Dose (s)';
    const tmin = startISO ? new Date(startISO) : null;
    const tmax = endISO ? new Date(endISO) : null;
    buildChart(datasets, tmin, tmax, axisTitle);

    EC_STATE = { startISO, endISO, lastCount: events.length };

    // Update summary badges if present
    try {
      const todayEl = document.getElementById('ec-total-today');
      const weekEl = document.getElementById('ec-total-week');
      if (todayEl && hasAnyMl) {
        const todayStr = new Date().toISOString().slice(0,10);
        const todayTotal = (summary.find(d => d.day === todayStr)?.total_ml) ?? 0;
        todayEl.textContent = `Today: ${Number(todayTotal).toFixed(1)} ml`;
      }
      if (weekEl && hasAnyMl) {
        const sum7 = summary.slice(-7).reduce((a, d) => a + (d.total_ml || 0), 0);
        weekEl.textContent = `Week: ${Number(sum7).toFixed(1)} ml`;
      }
    } catch(e) { /* ignore */ }
  }

  function bindRangeButtons(){
    const buttons = document.querySelectorAll('[data-ec-range]');
    buttons.forEach(btn => {
      if (btn.__bound) return;
      btn.__bound = true;
      btn.addEventListener('click', () => {
        const r = btn.getAttribute('data-ec-range');
        const now = new Date();
        let start;
        if (r === '24h') start = new Date(now.getTime() - 24*3600*1000);
        else if (r === '7d') start = new Date(now.getTime() - 7*24*3600*1000);
        else if (r === '30d') start = new Date(now.getTime() - 30*24*3600*1000);
        else start = new Date(now.getTime() - 24*3600*1000);
        loadRangeAndRender({ start: start.toISOString(), end: now.toISOString() });
      });
    });
  }

  function init(){
    const now = new Date();
    const start = new Date(now.getTime() - 24*3600*1000).toISOString();
    const end = now.toISOString();
    bindRangeButtons();
    loadRangeAndRender({ start, end });
  }

  // Export small API for other modules (ec.js calls refresh after dosing)
  window.ecChart = {
    refresh: function(){
      const now = new Date();
      const end = EC_STATE.endISO || now.toISOString();
      let start = EC_STATE.startISO;
      if (!start) start = new Date(now.getTime() - 24*3600*1000).toISOString();
      loadRangeAndRender({ start, end });
    },
    render: loadRangeAndRender,
    init
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
