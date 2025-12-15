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
      updateEventsLog()
    ]).catch(e => console.error('[Circulation] Parallel refresh error:', e));
  }

  let statsInterval = null;
  let logInterval = null;

  function initCirculation() {
    console.log('[Circulation] Initializing circulation controller');
    
    // Clear existing intervals to prevent duplicates
    if (statsInterval) clearInterval(statsInterval);
    if (logInterval) clearInterval(logInterval);
    
    refreshAll();
    
    // Setup refreshes
    statsInterval = setInterval(() => {
      refreshCirc();
      updateRuntimeStats();
    }, 5000);
    
    logInterval = setInterval(updateEventsLog, 30000);
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
