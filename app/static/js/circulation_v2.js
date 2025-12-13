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
      
      document.getElementById('main-runtime-today')?.textContent = formatDuration(mainStats.runtime);
      document.getElementById('main-cycles-today')?.textContent = mainStats.cycles;
      document.getElementById('main-last-change')?.textContent = formatTimeAgo(mainStats.lastChange);
      document.getElementById('chiller-runtime-today')?.textContent = formatDuration(chillerStats.runtime);
      document.getElementById('chiller-cycles-today')?.textContent = chillerStats.cycles;
      document.getElementById('chiller-last-change')?.textContent = formatTimeAgo(chillerStats.lastChange);
      
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
        listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">No events recorded yet. Events will appear after pump state changes.</div>';
        return;
      }
      
      listEl.innerHTML = allEvents.map(evt => {
        const icon = evt.pump === 'Main Pump' ? '🔄' : '🌊';
        const state = evt.final ? '<span style="color:#10b981;">ON</span>' : '<span style="color:#ef4444;">OFF</span>';
        const time = formatTimeAgo(evt.ts);
        return `<div style="padding:8px;border-bottom:1px solid rgba(148,163,184,0.1);display:flex;align-items:center;gap:8px;"><span>${icon}</span><span style="flex:1;"><strong>${evt.pump}</strong> → ${state}</span><span style="color:#64748b;font-size:var(--font-xs);">${time}</span></div>`;
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
 * Circulation Timeline Chart - Uses unified RDWCChart
 * Initializes after chart_base.js is loaded
 */
(function() {
  'use strict';

  function initCirculationChart() {
    console.log('[CirculationChart] Initializing');

    if (typeof RDWCChart === 'undefined') {
      console.warn('[CirculationChart] RDWCChart not loaded, retrying...');
      setTimeout(initCirculationChart, 500);
      return;
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initChart);
    } else {
      initChart();
    }

    function initChart() {
      window.circChart = new RDWCChart({
        canvasId: 'circTimelineChart',
        emptyMessageId: null,
        type: 'circulation',
        title: 'Pump Activity Timeline',
        
        onDataFetch: async (start, end) => {
          // Fetch events for both pumps
          const [mainResp, chillerResp] = await Promise.all([
            fetch(`/api/relays/events?name=main_pump&last=200`, {cache: 'no-store'}),
            fetch(`/api/relays/events?name=chiller_pump&last=200`, {cache: 'no-store'})
          ]);
          
          const mainEvents = mainResp.ok ? await mainResp.json() : [];
          const chillerEvents = chillerResp.ok ? await chillerResp.json() : [];
          
          // Filter to time window
          const filterEvents = (events) => events
            .filter(e => {
              const t = new Date(e.ts).getTime();
              return t >= start && t <= end;
            })
            .sort((a,b) => new Date(a.ts) - new Date(b.ts));
          
          const mainFiltered = filterEvents(mainEvents);
          const chillerFiltered = filterEvents(chillerEvents);
          
          // Get current states
          const statusResp = await fetch('/api/relays/status', {cache: 'no-store'});
          const statusData = statusResp.ok ? await statusResp.json() : {};
          const currentMainState = statusData.relays?.main_pump?.is_on ? 1 : 0;
          const currentChillerState = statusData.relays?.chiller_pump?.is_on ? 1 : 0;
          
          return {
            mainEvents: mainFiltered,
            chillerEvents: chillerFiltered,
            currentMainState,
            currentChillerState
          };
        },
        
        onRender: (chart, data, timeWindow) => {
          const buildTimeline = (events, currentState, startTime) => {
            const timeline = [];
            if (!events || events.length === 0) {
              timeline.push({ x: new Date(startTime), y: currentState });
              timeline.push({ x: new Date(), y: currentState });
              return timeline;
            }
            
            events.forEach(evt => {
              timeline.push({
                x: new Date(evt.ts),
                y: evt.final ? 1 : 0
              });
            });
            
            const lastState = events.length > 0 ? (events[events.length - 1].final ? 1 : 0) : currentState;
            timeline.push({ x: new Date(), y: lastState });
            
            return timeline;
          };
          
          const mainTimeline = buildTimeline(data.mainEvents, data.currentMainState, timeWindow.start);
          const chillerTimeline = buildTimeline(data.chillerEvents, data.currentChillerState, timeWindow.start);
          
          return [
            {
              label: 'Main Pump',
              data: mainTimeline,
              borderColor: '#60a5fa',
              backgroundColor: 'rgba(96,165,250,0.1)',
              borderWidth: 2,
              stepped: true,
              pointRadius: 3,
              pointBorderColor: '#60a5fa',
              pointBackgroundColor: '#60a5fa',
              fill: false,
              tension: 0
            },
            {
              label: 'Chiller Pump',
              data: chillerTimeline,
              borderColor: '#22d3ee',
              backgroundColor: 'rgba(34,211,238,0.1)',
              borderWidth: 2,
              stepped: true,
              pointRadius: 3,
              pointBorderColor: '#22d3ee',
              pointBackgroundColor: '#22d3ee',
              fill: false,
              tension: 0
            }
          ];
        }
      });
      
      console.log('[CirculationChart] Initialized');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCirculationChart);
  } else {
    setTimeout(initCirculationChart, 1000);
  }
})();
