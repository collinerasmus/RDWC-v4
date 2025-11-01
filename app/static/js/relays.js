/* Relays Control Panel - Clean relay toggles with POST/GET fallback */
(() => {
  const q = (s) => document.querySelector(s);
  const el = (h) => { const d = document.createElement('div'); d.innerHTML = h.trim(); return d.firstChild; };
  
  const post = async (url, body) => {
    const r = await fetch(url, { 
      method: 'POST', 
      headers: { 'Content-Type': 'application/json' }, 
      body: JSON.stringify(body),
      cache: 'no-store'
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  
  async function getJSON(url) { 
    const r = await fetch(url, { cache: 'no-store' }); 
    if (!r.ok) throw new Error('HTTP ' + r.status); 
    return r.json(); 
  }

  // Relay name to friendly label mapping
  const RELAY_MAP = {
    'lights': 'Lights',
    'main_pump': 'Main Pump',
    'chiller_pump': 'Chiller Pump',
    'chiller_power': 'Chiller Power',
    'dosing_grow': 'Dosing Grow',
    'dosing_micro': 'Dosing Micro',
    'dosing_bloom': 'Dosing Bloom',
    'dosing_ph_up': 'Dosing pH Up'
  };

  async function fetchState() {
    try {
      // Try new format first
      return await getJSON('/relay/status');
    } catch (_) {
      // Fallback to legacy format
      return await getJSON('/relay/state');
    }
  }

  function btnTemplate(key, name, on) {
    const cls = on 
      ? 'bg-green-600 hover:bg-green-700 text-white' 
      : 'bg-red-600 hover:bg-red-700 text-white';
    const label = (on ? 'ON ' : 'OFF ') + name;
    return el(`<button data-relay="${key}" class="relay-btn ${cls} rounded-xl py-3 px-4 font-semibold transition-all duration-200 shadow-sm hover:shadow-md">${label}</button>`);
  }

  async function paint() {
    const grid = q('#relays-grid');
    if (!grid) {
      console.warn('[Relays] Grid element not found');
      return;
    }
    
    grid.innerHTML = '<div class="text-gray-400 text-sm col-span-2">Loading relays…</div>';
    
    try {
      const state = await fetchState();
      
      grid.innerHTML = '';
      
      // Paint buttons in order
      Object.keys(RELAY_MAP).forEach(key => {
        const name = RELAY_MAP[key];
        // Handle both flat and nested state formats
        const on = state[key]?.state !== undefined ? state[key].state : !!state[key];
        const btn = btnTemplate(key, name, on);
        grid.appendChild(btn);
      });
      
      wire();
      
      const note = q('#relays-note');
      if (note) {
        note.textContent = 'Click a button to toggle relay state. Updates within 1-2s.';
      }
      
      console.log('[Relays] Painted', Object.keys(RELAY_MAP).length, 'buttons');
    } catch (e) {
      console.error('[Relays] Failed to paint:', e);
      grid.innerHTML = '<div class="text-red-400 text-sm col-span-2">Failed to load relays. Check console for details.</div>';
    }
  }

  function wire() {
    const grid = q('#relays-grid');
    if (!grid) return;
    
    grid.querySelectorAll('.relay-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const key = btn.getAttribute('data-relay');
        const isOn = btn.textContent.trim().startsWith('ON ');
        const desired = !isOn;
        
        // Optimistic UI update
        btn.disabled = true;
        btn.style.opacity = '0.6';
        
        try {
          // Try POST first
          try {
            await post('/relay/set', { name: key, on: desired });
          } catch (postErr) {
            // Fallback to GET
            console.warn('[Relays] POST failed, trying GET fallback', postErr);
            await fetch(`/relay/set?name=${encodeURIComponent(key)}&on=${desired ? 1 : 0}`, { cache: 'no-store' });
          }
          
          // Wait a moment for backend to settle
          await new Promise(resolve => setTimeout(resolve, 300));
          
          // Refresh just this button
          const state = await fetchState();
          const on = state[key]?.state !== undefined ? state[key].state : !!state[key];
          const name = RELAY_MAP[key];
          
          btn.textContent = (on ? 'ON ' : 'OFF ') + name;
          btn.classList.remove('bg-green-600', 'hover:bg-green-700', 'bg-red-600', 'hover:bg-red-700');
          if (on) {
            btn.classList.add('bg-green-600', 'hover:bg-green-700');
          } else {
            btn.classList.add('bg-red-600', 'hover:bg-red-700');
          }
          
          console.log('[Relays] Toggled', key, '->', on);
        } catch (e) {
          console.error('[Relays] Toggle failed', key, e);
          alert(`Failed to toggle ${key}: ${e.message}`);
        } finally {
          btn.disabled = false;
          btn.style.opacity = '1';
        }
      });
    });
  }

  // Auto-refresh relay states every 5 seconds
  let refreshTimer = null;
  
  async function refreshStates() {
    try {
      const state = await fetchState();
      const grid = q('#relays-grid');
      if (!grid) return;
      
      grid.querySelectorAll('.relay-btn').forEach(btn => {
        const key = btn.getAttribute('data-relay');
        const on = state[key]?.state !== undefined ? state[key].state : !!state[key];
        const name = RELAY_MAP[key];
        
        // Only update if state changed to avoid flicker during user interaction
        const currentOn = btn.textContent.trim().startsWith('ON ');
        if (currentOn !== on) {
          btn.textContent = (on ? 'ON ' : 'OFF ') + name;
          btn.classList.remove('bg-green-600', 'hover:bg-green-700', 'bg-red-600', 'hover:bg-red-700');
          if (on) {
            btn.classList.add('bg-green-600', 'hover:bg-green-700');
          } else {
            btn.classList.add('bg-red-600', 'hover:bg-red-700');
          }
        }
      });
    } catch (e) {
      console.warn('[Relays] Auto-refresh failed', e);
    }
  }

  function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(refreshStates, 5000); // Every 5 seconds
  }

  document.addEventListener('DOMContentLoaded', () => {
    console.log('[Relays] Initializing relay control panel');
    paint().then(() => {
      startAutoRefresh();
    }).catch(console.error);
  });
})();
