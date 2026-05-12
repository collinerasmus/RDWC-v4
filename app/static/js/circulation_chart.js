/**
 * Circulation Chart - Clean minimal implementation
 * Displays pump ON periods as horizontal bars (separate rows for main and chiller)
 */
(function() {
  'use strict';

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
    const canvas = document.getElementById('circTimelineChart');
    if (!canvas) return;

    chart = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        datasets: [
          { label: 'Main Pump', data: [], backgroundColor: '#3b82f6', barThickness: 35, borderRadius: 4 },
          { label: 'Chiller Pump', data: [], backgroundColor: '#06b6d4', barThickness: 35, borderRadius: 4 }
        ]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: 'top', labels: { color: '#9ca3af', font: { size: 12 }, padding: 15, usePointStyle: true } },
          tooltip: { callbacks: { title: () => '', label: (ctx) => `${ctx.dataset.label} ON for ${ctx.raw.duration}` } }
        },
        scales: {
          x: { type: 'time', time: { displayFormats: { hour: 'HH:mm', minute: 'HH:mm' } }, grid: { color: 'rgba(148,163,184,0.1)' }, ticks: { color: '#9ca3af' } },
          y: { display: false, grid: { display: false } }
        }
      }
    });
    window.circChart = chart;
    refresh();
  }

  async function refresh() {
    if (!chart) return;
    try {
      const now = Date.now();
      let start = now - chartHours * 3600000;
      let end = now;
      if (customRange) { start = customRange.start; end = customRange.end; }

      const [mainRes, chillerRes] = await Promise.all([
        fetch(`/api/relays/events?name=main_pump&last=5000`, { cache: 'no-store' }),
        fetch(`/api/relays/events?name=chiller_pump&last=5000`, { cache: 'no-store' })
      ]);

      const processPump = async (res, pumpLabel) => {
        if (!res.ok) return [];
        try {
          const events = await res.json();
          if (!events || !Array.isArray(events)) return [];
          
          const sorted = events
            .map(e => ({ ...e, ts: new Date(e.ts).getTime() }))
            .sort((a, b) => a.ts - b.ts);

          const bars = [];
          let onStart = null;
          for (let i = 0; i < sorted.length; i++) {
            const evt = sorted[i];
            if (evt.final === true) {
              if (onStart === null) onStart = evt.ts;
              continue;
            }
            if (evt.final === false && onStart !== null) {
              const segStart = Math.max(onStart, start);
              const segEnd = Math.min(evt.ts, end);
              if (segEnd > segStart) {
                const dur = (segEnd - segStart) / 1000;
                bars.push({ x: [segStart, segEnd], y: pumpLabel, duration: formatDuration(dur) });
              }
              onStart = null;
            }
          }
          if (onStart !== null) {
            const segStart = Math.max(onStart, start);
            const segEnd = end;
            if (segEnd > segStart) {
              const dur = (segEnd - segStart) / 1000;
              bars.push({ x: [segStart, segEnd], y: pumpLabel, duration: formatDuration(dur) });
            }
          }
          return bars;
        } catch (e) {
          console.error(`[CircChart] processPump error for ${pumpLabel}:`, e);
          return [];
        }
      };

      const [mainBars, chillerBars] = await Promise.all([
        processPump(mainRes, 'Main'),
        processPump(chillerRes, 'Chiller')
      ]);

      chart.data.datasets[0].data = mainBars || [];
      chart.data.datasets[1].data = chillerBars || [];
      chart.options.scales.x.min = start;
      chart.options.scales.x.max = end;
      chart.update('none');

      const emptyMsg = document.getElementById('circ-chart-empty');
      if (emptyMsg) emptyMsg.style.display = (!mainBars?.length && !chillerBars?.length) ? 'block' : 'none';

    } catch (e) { console.error('[CircChart]', e); }
  }

  window.setCircChartHours = (h) => { chartHours = h; customRange = null; refresh(); };
  window.setCircChartRange = (s, e) => { customRange = { start: s, end: e }; refresh(); };

  // Auto-refresh every 5 seconds to keep chart live
  setInterval(refresh, 5000);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initChart);
  else setTimeout(initChart, 500);
})();
