/**
 * Circulation Controller - Enhanced with runtime stats, timeline, and event logs
 */
(() => {
  let circEstop = false;
  let circCooldown = false;
  let timelineChart = null;

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
      // Fetch relay event logs for both pumps
      const [mainResp, chillerResp] = await Promise.all([
        fetch('/api/relays/events?name=main_pump&last=200', {cache: 'no-store'}),
        fetch('/api/relays/events?name=chiller_pump&last=200', {cache: 'no-store'})
      ]);
      
      const mainEvents = mainResp.ok ? await mainResp.json() : [];
      const chillerEvents = chillerResp.ok ? await chillerResp.json() : [];
      console.log('[Circulation] Fetched events - Main:', mainEvents.length, 'Chiller:', chillerEvents.length);
      
      // Calculate today's stats (SA timezone)
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
        
        // Process events chronologically (reverse order since API returns DESC)
        const sorted = [...events].sort((a,b) => new Date(a.ts) - new Date(b.ts));
        
        sorted.forEach(evt => {
          const evtTime = new Date(evt.ts).getTime();
          const isToday = evtTime >= todayStart;
          const newState = evt.final; // Use 'final' field from event log
          
          if (newState && !lastState) {
            // Pump turned ON
            if (isToday) cycles++;
            lastOnTime = evtTime;
          } else if (!newState && lastState && lastOnTime) {
            // Pump turned OFF - add runtime
            if (isToday) {
              runtime += (evtTime - lastOnTime) / 1000;
            }
            lastOnTime = null;
          }
          
          lastState = newState;
          lastChange = evt.ts;
        });
        
        // If pump is still ON, add time until now
        if (lastState && lastOnTime) {
          const onSince = lastOnTime >= todayStart ? lastOnTime : todayStart;
          runtime += (now.getTime() - onSince) / 1000;
        }
        
        return { runtime, cycles, lastChange };
      };
      
      const mainStats = calcStats(mainEvents);
      const chillerStats = calcStats(chillerEvents);
      console.log('[Circulation] Main stats:', mainStats, 'Chiller stats:', chillerStats);
      
      // Update main pump stats
      const mainRuntimeEl = document.getElementById('main-runtime-today');
      const mainCyclesEl = document.getElementById('main-cycles-today');
      const mainLastChangeEl = document.getElementById('main-last-change');
      
      if (mainRuntimeEl) mainRuntimeEl.textContent = formatDuration(mainStats.runtime);
      if (mainCyclesEl) mainCyclesEl.textContent = String(mainStats.cycles);
      if (mainLastChangeEl) mainLastChangeEl.textContent = formatTimeAgo(mainStats.lastChange);
      
      // Update chiller pump stats
      const chillerRuntimeEl = document.getElementById('chiller-runtime-today');
      const chillerCyclesEl = document.getElementById('chiller-cycles-today');
      const chillerLastChangeEl = document.getElementById('chiller-last-change');
      
      if (chillerRuntimeEl) chillerRuntimeEl.textContent = formatDuration(chillerStats.runtime);
      if (chillerCyclesEl) chillerCyclesEl.textContent = String(chillerStats.cycles);
      if (chillerLastChangeEl) chillerLastChangeEl.textContent = formatTimeAgo(chillerStats.lastChange);
      
    } catch (e) {
      console.error('[Circulation] Stats update error:', e);
    }
  }

  async function updateEventsLog() {
    console.log('[Circulation] Updating events log...');
    try {
      // Fetch recent events for both pumps
      const [mainResp, chillerResp] = await Promise.all([
        fetch('/api/relays/events?name=main_pump&last=10', {cache: 'no-store'}),
        fetch('/api/relays/events?name=chiller_pump&last=10', {cache: 'no-store'})
      ]);
      
      const mainEvents = mainResp.ok ? await mainResp.json() : [];
      const chillerEvents = chillerResp.ok ? await chillerResp.json() : [];
      
      // Combine and sort by timestamp
      const allEvents = [
        ...mainEvents.map(e => ({...e, pump: 'main_pump', label: 'Main'})),
        ...chillerEvents.map(e => ({...e, pump: 'chiller_pump', label: 'Chiller'}))
      ].sort((a,b) => new Date(b.ts) - new Date(a.ts)).slice(0, 10);
      
      const listEl = document.getElementById('circ-events-list');
      if (!listEl) return;
      
      if (allEvents.length === 0) {
        listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">No events recorded yet. Events will appear after pump state changes.</div>';
        return;
      }
      
      listEl.innerHTML = allEvents.map(evt => {
        const stateColor = evt.final ? '#22c55e' : '#64748b';
        const stateText = evt.final ? 'ON' : 'OFF';
        const pumpColor = evt.pump === 'main_pump' ? '#60a5fa' : '#22d3ee';
        
        return `
          <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-bottom:1px solid rgba(148,163,184,0.1);">
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="font-size:18px;">${evt.pump === 'main_pump' ? '🔄' : '🌊'}</span>
              <div>
                <div style="font-size:var(--font-sm);font-weight:600;color:${pumpColor};">${evt.label} Pump</div>
                <div style="font-size:var(--font-xs);color:#9ca3af;">${evt.reason || 'manual'}</div>
              </div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:var(--font-sm);font-weight:600;color:${stateColor};">${stateText}</div>
              <div style="font-size:var(--font-xs);color:#64748b;">${formatTimeAgo(evt.ts)}</div>
            </div>
          </div>
        `;
      }).join('');
      
    } catch (e) {
      console.error('[Circulation] Events log error:', e);
    }
  }

  async function updateTimelineChart() {
    console.log('[Circulation] Updating timeline chart...');
    try {
      const canvas = document.getElementById('circTimelineChart');
      if (!canvas) {
        console.warn('[Circulation] Timeline canvas not found');
        return;
      }
      
      // Fetch 24h of events
      const [mainResp, chillerResp] = await Promise.all([
        fetch('/api/relays/events?name=main_pump&last=200', {cache: 'no-store'}),
        fetch('/api/relays/events?name=chiller_pump&last=200', {cache: 'no-store'})
      ]);
      
      const mainEvents = mainResp.ok ? await mainResp.json() : [];
      const chillerEvents = chillerResp.ok ? await chillerResp.json() : [];
      
      // Filter to last 24h
      const now = Date.now();
      const dayAgo = now - 24 * 3600 * 1000;
      
      const filterEvents = (events) => events
        .filter(e => new Date(e.ts).getTime() >= dayAgo)
        .sort((a,b) => new Date(a.ts) - new Date(b.ts));
      
      const mainFiltered = filterEvents(mainEvents);
      const chillerFiltered = filterEvents(chillerEvents);
      
      // Build timeline data (1=ON, 0=OFF)
      const buildTimeline = (events) => {
        const data = [];
        let lastState = false;
        
        if (!events || events.length === 0) {
          // No events - show current state as flat line
          data.push({ x: new Date(dayAgo), y: 0 });
          data.push({ x: new Date(), y: 0 });
          return data;
        }
        
        events.forEach(evt => {
          const newState = evt.final; // Use 'final' field
          data.push({
            x: new Date(evt.ts),
            y: newState ? 1 : 0
          });
          lastState = newState;
        });
        
        // Add current point
        data.push({ x: new Date(), y: lastState ? 1 : 0 });
        
        return data;
      };
      
      const ctx = canvas.getContext('2d');
      
      if (timelineChart) {
        timelineChart.destroy();
      }
      
      timelineChart = new Chart(ctx, {
        type: 'line',
        data: {
          datasets: [
            {
              label: 'Main Pump',
              data: buildTimeline(mainFiltered),
              borderColor: '#60a5fa',
              backgroundColor: 'rgba(96,165,250,0.1)',
              borderWidth: 2,
              stepped: true,
              pointRadius: 0,
              fill: false
            },
            {
              label: 'Chiller Pump',
              data: buildTimeline(chillerFiltered),
              borderColor: '#22d3ee',
              backgroundColor: 'rgba(34,211,238,0.1)',
              borderWidth: 2,
              stepped: true,
              pointRadius: 0,
              fill: false
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: {
              type: 'time',
              time: {
                unit: 'hour',
                displayFormats: { hour: 'HH:mm' }
              },
              grid: { color: 'rgba(148,163,184,0.1)' },
              ticks: { color: '#9ca3af', maxTicksLimit: 12 }
            },
            y: {
              min: 0,
              max: 1,
              ticks: {
                color: '#9ca3af',
                stepSize: 1,
                callback: (v) => v === 1 ? 'ON' : 'OFF'
              },
              grid: { color: 'rgba(148,163,184,0.1)' }
            }
          },
          plugins: {
            legend: {
              display: true,
              position: 'top',
              labels: { color: '#e0e0e0', boxWidth: 12, padding: 10 }
            },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y === 1 ? 'ON' : 'OFF'}`
              }
            }
          }
        }
      });
      console.log('[Circulation] Timeline chart created successfully');
      
    } catch (e) {
      console.error('[Circulation] Timeline chart error:', e);
    }
  }

  async function refreshCirc(){
    try{
      const r = await fetch('/api/relays/status', {cache:'no-store'});
      if(!r.ok) throw new Error('HTTP '+r.status);
      const wrap = await r.json();
      circEstop = !!wrap.estop;
      const rel = wrap.relays || {};
      const main = rel.main_pump || {};
      const temp = rel.chiller_pump || {};
      console.log('[Circulation] Relay status - Main pump:', main.is_on, 'Chiller pump:', temp.is_on);
      
      const cdMain = main.cooldown_remaining || main.cooldown || 0;
      const cdtemp = temp.cooldown_remaining || temp.cooldown || 0;
      circCooldown = (cdMain>0) || (cdtemp>0);
      
      // Update pump ON/OFF badges
      const badgeMain = document.getElementById('circ-main-pump');
      if (badgeMain){
        const on = !!main.is_on;
        badgeMain.textContent = on ? 'ON':'OFF';
        badgeMain.className = 'bop-status-badge ' + (on ? 'on':'off');
      }
      const badgetemp = document.getElementById('circ-temperature-pump');
      if (badgetemp){
        const on = !!temp.is_on;
        badgetemp.textContent = on ? 'ON':'OFF';
        badgetemp.className = 'bop-status-badge ' + (on ? 'on':'off');
      }
      
      // Update cooldown displays
      const mainCdEl = document.getElementById('main-cooldown');
      const chillerCdEl = document.getElementById('chiller-cooldown');
      if (mainCdEl) mainCdEl.textContent = cdMain > 0 ? `${cdMain}s` : 'Ready';
      if (chillerCdEl) chillerCdEl.textContent = cdtemp > 0 ? `${cdtemp}s` : 'Ready';
      
    }catch(e){ /* leave previous state */ }
    updateCircHealth();
  }

  async function refreshAll() {
    await Promise.all([
      refreshCirc(),
      updateRuntimeStats(),
      updateEventsLog(),
      updateTimelineChart()
    ]);
  }

  // Initialize when tab becomes visible
  function initCirculation() {
    console.log('[Circulation] Initializing circulation controller');
    refreshAll();
    
    // Setup refresh button
    const btnRefresh = document.getElementById('btnRefreshTimeline');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => {
        console.log('[Circulation] Manual refresh triggered');
        updateTimelineChart();
        updateEventsLog();
      });
    }
  }

  // Refresh health every 5s
  setInterval(() => {
    const card = document.getElementById('circ-card');
    if (card && card.style.display !== 'none') {
      refreshCirc();
      updateRuntimeStats();
    }
  }, 5000);

  // Full refresh every 30s when visible
  setInterval(() => {
    const card = document.getElementById('circ-card');
    if (card && card.style.display !== 'none') {
      updateEventsLog();
    }
  }, 30000);

  console.log('[Circulation] Controller script loaded');
  
  // Initialize circulation controller
  function setupCirculation() {
    console.log('[Circulation] Setting up circulation controller');
    
    const card = document.getElementById('circ-card');
    if (!card) {
      console.warn('[Circulation] Card element not found, retrying in 100ms...');
      setTimeout(setupCirculation, 100);
      return;
    }

    // Check if tab is already visible (empty string or not 'none' means visible)
    const isVisible = card.style.display !== 'none';
    console.log('[Circulation] Card display style:', card.style.display, 'isVisible:', isVisible);
    
    if (isVisible) {
      console.log('[Circulation] Tab already visible, initializing immediately');
      initCirculation();
      return;
    }

    // Set up MutationObserver to watch for tab visibility changes
    console.log('[Circulation] Tab not visible yet, setting up observer');
    const observer = new MutationObserver(() => {
      if (card.style.display !== 'none') {
        console.log('[Circulation] Tab became visible, initializing...');
        initCirculation();
        observer.disconnect();
      }
    });

    observer.observe(card, { attributes: true, attributeFilter: ['style'] });
  }

  // Run setup when DOM is ready or immediately if already ready
  if (document.readyState === 'loading') {
    console.log('[Circulation] DOM still loading, waiting for DOMContentLoaded');
    document.addEventListener('DOMContentLoaded', setupCirculation);
  } else {
    console.log('[Circulation] DOM already ready, setting up immediately');
    setupCirculation();
  }
})();

