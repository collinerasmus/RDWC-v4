/**
 * Circulation Controller v2 - Integrated with unified chart system
 * Uses RDWCChart base class for timeline, consistent with other dashboard charts
 */
(() => {
  let circEstop = false;
  let circCooldown = false;

  function updateCircHealth() {
    const chip = document.getElementById('circ-health-indicator');
    if (!chip) return;

    if (circEstop) { chip.textContent='BLOCKED'; chip.className='ui-status-chip error'; return; }
    if (circCooldown) { chip.textContent='WAITING'; chip.className='ui-status-chip warning'; return; }
    chip.textContent = 'AUTO'; chip.className = 'ui-status-chip success';
  }

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return '—';
    if (seconds === 0) return '0s';
    if (seconds < 0) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function formatTimeAgo(ts) {
    if (!ts) return '—';
    const now = Date.now();
    const diff = Math.floor((now - new Date(ts).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
    return `${Math.floor(diff/86400)}d ago`;
  }

  async function updateRuntimeStats() {
    console.log('[Circulation] Updating runtime stats...');
    try {
      const [mainResp, chillerResp] = await Promise.all([
        fetch('/api/relays/events?name=main_pump&last=200', {cache: 'no-store'}),
        fetch('/api/relays/events?name=chiller_pump&last=200', {cache: 'no-store'})
      ]);
      
      const mainEvents = mainResp.ok ? await mainResp.json() : [];
      const chillerEvents = chillerResp.ok ? await chillerResp.json() : [];
      console.log('[Circulation] Fetched events - Main:', mainEvents.length, 'Chiller:', chillerEvents.length);
      
      const now = new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      
      const calcStats = (events) => {
        let runtime = 0;
        let cycles = 0;
        let lastState = false;
        let lastChange = null;
        let lastOnTime = null;
        
        if (!events || events.length === 0) {
          return { runtime: 0, cycles: 0, lastChange: null };
        }
        
        const sorted = [...events].sort((a,b) => new Date(a.ts) - new Date(b.ts));
        
        sorted.forEach(evt => {
          const evtTime = new Date(evt.ts).getTime();
          const isToday = evtTime >= todayStart;
          const newState = evt.final;
          
          if (newState && !lastState) {
            if (isToday) cycles++;
            lastOnTime = evtTime;
          } else if (!newState && lastState && lastOnTime) {
            if (isToday) {
              runtime += (evtTime - lastOnTime) / 1000;
            }
            lastOnTime = null;
          }
          
          lastState = newState;
          lastChange = evt.ts;
        });
        
        if (lastState && lastOnTime) {
          const onSince = lastOnTime >= todayStart ? lastOnTime : todayStart;
          runtime += (now.getTime() - onSince) / 1000;
        }
        
        return { runtime, cycles, lastChange };
      };
      
      const mainStats = calcStats(mainEvents);
      const chillerStats = calcStats(chillerEvents);
      console.log('[Circulation] Main stats:', mainStats, 'Chiller stats:', chillerStats);
      
      const mainRuntimeEl = document.getElementById('main-runtime-today');
      if (mainRuntimeEl) mainRuntimeEl.textContent = formatDuration(mainStats.runtime);
      const mainCyclesEl = document.getElementById('main-cycles-today');
      if (mainCyclesEl) mainCyclesEl.textContent = mainStats.cycles;
      const mainLastEl = document.getElementById('main-last-change');
      if (mainLastEl) mainLastEl.textContent = formatTimeAgo(mainStats.lastChange);
      const chillerRuntimeEl = document.getElementById('chiller-runtime-today');
      if (chillerRuntimeEl) chillerRuntimeEl.textContent = formatDuration(chillerStats.runtime);
      const chillerCyclesEl = document.getElementById('chiller-cycles-today');
      if (chillerCyclesEl) chillerCyclesEl.textContent = chillerStats.cycles;
      const chillerLastEl = document.getElementById('chiller-last-change');
      if (chillerLastEl) chillerLastEl.textContent = formatTimeAgo(chillerStats.lastChange);
      
    } catch (e) {
      console.error('[Circulation] Stats error:', e);
    }
  }

  async function updateEventsLog() {
    console.log('[Circulation] Updating events log...');
    try {
      const [mainResp, chillerResp] = await Promise.all([
        fetch('/api/relays/events?name=main_pump&last=10', {cache: 'no-store'}),
        fetch('/api/relays/events?name=chiller_pump&last=10', {cache: 'no-store'})
      ]);
      
      const mainEvents = mainResp.ok ? await mainResp.json() : [];
      const chillerEvents = chillerResp.ok ? await chillerResp.json() : [];
      
      const allEvents = [
        ...mainEvents.map(e => ({...e, pump: 'Main Pump'})),
        ...chillerEvents.map(e => ({...e, pump: 'Chiller Pump'}))
      ]
        .sort((a,b) => new Date(b.ts) - new Date(a.ts))
        .slice(0, 10);
      
      const listEl = document.getElementById('circ-events-list');
      if (!listEl) return;
      
      if (allEvents.length === 0) {
        listEl.innerHTML = '<div style="text-align:center;padding:16px;color:#94a3b8;">No events yet. Events will appear after pump state changes.</div>';
        return;
      }

      listEl.innerHTML = allEvents.map(evt => {
        const ts = new Date(evt.ts);
        const tsStr = ts.toISOString().replace('T',' ').split('.')[0];
        const state = evt.final ? '<span style="color:#22c55e;font-weight:600;">ON</span>' : '<span style="color:#ef4444;font-weight:600;">OFF</span>';
        const reason = evt.reason ? ` · ${evt.reason}` : '';
        return `
          <div style="padding:6px 4px;border-bottom:1px solid rgba(148,163,184,0.12);display:flex;align-items:center;gap:8px;">
            <span style="font-weight:700;color:#e5e7eb;white-space:nowrap;">${tsStr}</span>
            <span style="color:#9ca3af;">• ${evt.pump}</span>
            <span style="color:#9ca3af;">→</span>
            <span>${state}</span>
            <span style="color:#9ca3af;">${reason}</span>
          </div>
        `;
      }).join('');
      
    } catch (e) {
      console.error('[Circulation] Events log error:', e);
    }
  }

  async function refreshCirc() {
    try {
      const statusResp = await fetch('/api/relays/status', {cache: 'no-store'});
      const statusData = statusResp.ok ? await statusResp.json() : {};
      
      circEstop = statusData.estop || false;
      circCooldown = statusData.mode === 'manual';
      updateCircHealth();
      
      const mainPumpOn = statusData.relays?.main_pump?.is_on || false;
      const chillerPumpOn = statusData.relays?.chiller_pump?.is_on || false;
      
      const mainBadge = document.getElementById('circ-main-pump');
      const chillerBadge = document.getElementById('circ-temperature-pump');
      
      if (mainBadge) {
        mainBadge.textContent = mainPumpOn ? 'ON' : 'OFF';
        mainBadge.className = mainPumpOn ? 'ui-status-chip success' : 'ui-status-chip secondary';
      }
      if (chillerBadge) {
        chillerBadge.textContent = chillerPumpOn ? 'ON' : 'OFF';
        chillerBadge.className = chillerPumpOn ? 'ui-status-chip success' : 'ui-status-chip secondary';
      }
      
      console.log('[Circulation] Relay status - Main pump:', mainPumpOn, 'Chiller pump:', chillerPumpOn);
      
    } catch (e) {
      console.error('[Circulation] Relay status error:', e);
    }
  }

  async function refreshAll() {
    await Promise.all([
      refreshCirc(),
      updateRuntimeStats(),
      updateEventsLog(),
      window.circChart?.refresh(true)
    ]).catch(e => console.error('[Circulation] Parallel refresh error:', e));
  }

  function initCirculation() {
    console.log('[Circulation] Initializing circulation controller');
    refreshAll();
    
    // Setup refreshes
    setInterval(() => {
      refreshCirc();
      updateRuntimeStats();
    }, 5000);
    
    setInterval(updateEventsLog, 30000);
  }

  function setupCirculation() {
    console.log('[Circulation] Setting up circulation controller');
    const card = document.getElementById('circ-card');
    
    if (!card) {
      setTimeout(setupCirculation, 100);
      return;
    }
    
    const isVisible = card.style.display !== 'none';
    console.log('[Circulation] Card display style:', card.style.display, 'isVisible:', isVisible);
    
    if (isVisible) {
      console.log('[Circulation] Tab already visible, initializing immediately');
      initCirculation();
    } else {
      const observer = new MutationObserver(() => {
        if (card.style.display !== 'none') {
          observer.disconnect();
          console.log('[Circulation] Tab became visible, initializing');
          initCirculation();
        }
      });
      observer.observe(card, {attributes: true, attributeFilter: ['style']});
    }
  }

  // Setup handlers
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupCirculation);
  } else {
    console.log('[Circulation] DOM already ready, setting up immediately');
    setupCirculation();
  }

  console.log('[Circulation] Controller script loaded');
})();

/**
 * Circulation Timeline Chart - Direct Chart.js implementation (matches lights_v2 pattern)
 */
(function() {
  'use strict';

  let circChart = null;
  let currentChartHours = 6;
  let customTimeRange = null;

  function initCirculationChart() {
    console.log('[CirculationChart] Initializing');

    const canvas = document.getElementById('circTimelineChart');
    if (!canvas || !window.Chart) {
      console.warn('[CirculationChart] Canvas or Chart.js not ready, retrying...');
      setTimeout(initCirculationChart, 500);
      return;
    }

    const ctx = canvas.getContext('2d');
    circChart = new Chart(ctx, {
      type: 'bar',
      data: {
        datasets: [
          {
            label: 'Main Pump',
            data: [],
            backgroundColor: '#3b82f6',
            barThickness: 35,
            borderRadius: 4,
            borderSkipped: false
          },
          {
            label: 'Chiller Pump',
            data: [],
            backgroundColor: '#06b6d4',
            barThickness: 35,
            borderRadius: 4,
            borderSkipped: false
          }
        ]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: { 
            display: true,
            position: 'top',
            labels: {
              color: '#9ca3af',
              font: { size: 12 },
              padding: 15,
              usePointStyle: true,
              pointStyle: 'rect'
            }
          },
          tooltip: {
            callbacks: {
              title: () => '',
              label: (ctx) => {
                const bar = ctx.raw;
                return `${ctx.dataset.label} ON for ${bar.duration}`;
              }
            }
          }
        },
        scales: {
          x: {
            type: 'time',
            time: {
              displayFormats: { hour: 'HH:mm', minute: 'HH:mm' }
            },
            grid: { color: 'rgba(148,163,184,0.1)' },
            ticks: { color: '#9ca3af' }
          },
          y: {
            stacked: false,
            grid: { display: false },
            ticks: { display: false }
          }
        }
      }
    });

    // Expose chart to window for ChartControls integration
    window.circChart = circChart;
    refreshCirculationChart();
  }

  function formatDurationShort(seconds) {
    if (!seconds || seconds < 0) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m`;
    return `${Math.floor(seconds)}s`;
  }

  async function refreshCirculationChart() {
    if (!circChart) return;

    try {
      const now = Date.now();
      let startMs, endMs;

      if (customTimeRange) {
        startMs = customTimeRange.start;
        endMs = customTimeRange.end;
      } else {
        endMs = now;
        startMs = now - (currentChartHours * 3600 * 1000);
      }

      // Fetch events for both pumps
      const [mainResp, chillerResp, statusResp] = await Promise.all([
        fetch('/api/relays/events?name=main_pump&last=200', {cache: 'no-store'}),
        fetch('/api/relays/events?name=chiller_pump&last=200', {cache: 'no-store'}),
        fetch('/api/relays/status', {cache: 'no-store'})
      ]);

      const mainEvents = mainResp.ok ? await mainResp.json() : [];
      const chillerEvents = chillerResp.ok ? await chillerResp.json() : [];
      const statusData = statusResp.ok ? await statusResp.json() : {};

      const currentMainOn = statusData.relays?.main_pump?.is_on || false;
      const currentChillerOn = statusData.relays?.chiller_pump?.is_on || false;

      // Convert events to bars (ON periods only)
      const convertToBars = (events, currentlyOn, yLabel) => {
        const bars = [];

        // Sort events chronologically
        const sorted = [...events]
          .map(e => ({ ...e, tsMs: new Date(e.ts).getTime() }))
          .sort((a, b) => a.tsMs - b.tsMs);

        // Filter to events in window
        const inWindow = sorted.filter(e => e.tsMs >= startMs && e.tsMs <= endMs);

        // Build bars from consecutive ON/OFF pairs
        for (let i = 0; i < inWindow.length - 1; i++) {
          if (inWindow[i].final === true) {
            const onStart = inWindow[i].tsMs;
            const onEnd = inWindow[i + 1].tsMs;
            const duration = (onEnd - onStart) / 1000;
            
            bars.push({
              x: [onStart, onEnd],
              y: yLabel,
              duration: formatDurationShort(duration)
            });
          }
        }

        // Handle ongoing ON period at window end
        if (inWindow.length > 0 && inWindow[inWindow.length - 1].final === true) {
          const onStart = inWindow[inWindow.length - 1].tsMs;
          const duration = (endMs - onStart) / 1000;
          
          bars.push({
            x: [onStart, endMs],
            y: yLabel,
            duration: formatDurationShort(duration)
          });
        }

        // Handle case where pump was already ON at window start
        if (inWindow.length > 0 && inWindow[0].final === false) {
          // Pump was ON before window, find the OFF event
          const onEnd = inWindow[0].tsMs;
          const duration = (onEnd - startMs) / 1000;
          
          bars.unshift({
            x: [startMs, onEnd],
            y: yLabel,
            duration: formatDurationShort(duration)
          });
        } else if (inWindow.length === 0 && currentlyOn) {
          // No events in window but pump is currently ON
          const duration = (endMs - startMs) / 1000;
          bars.push({
            x: [startMs, endMs],
            y: yLabel,
            duration: formatDurationShort(duration)
          });
        }

        return bars;
      };

      const mainBars = convertToBars(mainEvents, currentMainOn, 'Main');
      const chillerBars = convertToBars(chillerEvents, currentChillerOn, 'Chiller');

      circChart.data.datasets[0].data = mainBars;
      circChart.data.datasets[1].data = chillerBars;

      circChart.options.scales.x.min = startMs;
      circChart.options.scales.x.max = endMs;
      circChart.update('none');

      // Hide/show empty message
      const emptyMsg = document.getElementById('circ-chart-empty');
      if (emptyMsg) {
        emptyMsg.style.display = (mainBars.length === 0 && chillerBars.length === 0) ? 'block' : 'none';
      }

    } catch (e) {
      console.error('[CirculationChart] Refresh failed:', e);
    }
  }

  // Expose functions for ChartControls integration
  window.circChart = null;
  window.setCircChartHours = (hours) => {
    currentChartHours = hours;
    customTimeRange = null;
    refreshCirculationChart();
  };
  window.setCircChartRange = (startMs, endMs) => {
    customTimeRange = { start: startMs, end: endMs };
    refreshCirculationChart();
  };

  // Add refresh method for backward compatibility
  Object.defineProperty(window, 'circChart', {
    get: () => ({ refresh: refreshCirculationChart, chart: circChart }),
    set: (val) => { circChart = val; }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCirculationChart);
  } else {
    setTimeout(initCirculationChart, 1000);
  }
})();
