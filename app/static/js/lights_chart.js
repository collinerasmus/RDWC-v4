/**
 * Lights Chart - Clean minimal implementation
 * Displays ON periods as horizontal bars
 */
(function() {
  'use strict';

  if (window.__lightsChartModuleLoaded) {
    console.log('[LightsChart] Module already loaded; skipping duplicate init');
    return;
  }
  window.__lightsChartModuleLoaded = true;

  let chart = null;
  let chartHours = 6;
  let customRange = null;

  function formatDuration(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return m > 0 ? `${m}m` : '0m';
  }

  function initChart() {
    const canvas = document.getElementById('lightsChart');
    if (!canvas) return;

    chart = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: { datasets: [{ label: 'Lights ON', data: [], backgroundColor: '#22c55e', barThickness: 40, borderRadius: 4 }] },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: () => '', label: (ctx) => `ON for ${ctx.raw.duration}` } }
        },
        scales: {
          x: { type: 'time', time: { displayFormats: { hour: 'HH:mm', minute: 'HH:mm' } }, grid: { color: 'rgba(148,163,184,0.1)' }, ticks: { color: '#9ca3af' } },
          y: { display: false, grid: { display: false } }
        }
      }
    });
    window.lightsChart = chart;
    refresh();
  }

  async function refresh() {
    if (!chart) return;
    try {
      const now = Date.now();
      let start = now - chartHours * 3600000;
      let end = now;
      if (customRange) { start = customRange.start; end = customRange.end; }

      const res = await fetch(`/api/relays/events?name=lights&last=5000`, { cache: 'no-store' });
      if (!res.ok) { chart.data.datasets[0].data = []; chart.update('none'); return; }

      const events = (await res.json() || [])
        .map(e => ({ ...e, ts: new Date(e.ts).getTime() }))
        .sort((a, b) => a.ts - b.ts);

      const bars = [];
      let onStart = null;
      for (let i = 0; i < events.length; i++) {
        const evt = events[i];
        if (evt.final === true) {
          if (onStart === null) onStart = evt.ts;
          continue;
        }
        if (evt.final === false && onStart !== null) {
          const segStart = Math.max(onStart, start);
          const segEnd = Math.min(evt.ts, end);
          if (segEnd > segStart) {
            const dur = (segEnd - segStart) / 1000;
            bars.push({ x: [segStart, segEnd], y: 'ON', duration: formatDuration(dur) });
          }
          onStart = null;
        }
      }
      if (onStart !== null) {
        const segStart = Math.max(onStart, start);
        const segEnd = end;
        if (segEnd > segStart) {
          const dur = (segEnd - segStart) / 1000;
          bars.push({ x: [segStart, segEnd], y: 'ON', duration: formatDuration(dur) });
        }
      }

      chart.data.datasets[0].data = bars;
      chart.options.scales.x.min = start;
      chart.options.scales.x.max = end;
      chart.update('none');
    } catch (e) { console.error('[LightsChart]', e); }
  }

  window.setLightsChartHours = (h) => { chartHours = h; customRange = null; refresh(); };
  window.setLightsChartRange = (s, e) => { customRange = { start: s, end: e }; refresh(); };

  // Auto-refresh every 5 seconds to keep chart live
  if (window.__lightsChartRefreshTimer) {
    clearInterval(window.__lightsChartRefreshTimer);
  }
  window.__lightsChartRefreshTimer = setInterval(refresh, 5000);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initChart);
  else setTimeout(initChart, 500);
})();
