/**
 * Relays Control Panel - Auto/Manual modes with smart restoration
 * Features:
 * - Auto/Manual system mode toggle
 * - Compact half-width buttons with color coding
 * - 1-second refresh for responsive UI
 * - Lockout countdown badges for protected relays
 * - Non-blocking notices for protection violations
 */
(() => {
  const q  = (s) => document.querySelector(s);
  const el = (h) => { const d=document.createElement('div'); d.innerHTML=h.trim(); return d.firstChild; };

  let currentMode = 'manual';  // Track current system mode

  // Fixed relay order + display names
  const RELAY_ORDER = [
    'ph_up', 'dosing_grow', 'dosing_micro', 'dosing_bloom',
    'main_pump', 'chiller_pump', 'water_chiller', 'grow_lights'
  ];
  const RELAY_LABELS = {
    ph_up: 'pH Up Pump',
    dosing_grow: 'Grow Pump',
    dosing_micro: 'Micro Pump',
    dosing_bloom: 'Bloom Pump',
    main_pump: 'Main Pump',
    chiller_pump: 'Chiller Pump',
    water_chiller: 'Water Chiller (AC)',
    grow_lights: 'Grow Lights (AC)'
  };

  // Global UI state
  const state = { systemMode: 'manual', relays: {} };

  async function getJSON(url){
    const r = await fetch(url, {cache:'no-store'});
    if (!r.ok) throw new Error('HTTP '+r.status+' for '+url);
    return r.json();
  }

  async function postJSON(url, body){
    const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if (!r.ok) throw new Error('HTTP '+r.status+' for '+url);
    return r.json().catch(()=> ({}));
  }

  // --- System Mode -----------------------------------------------------------
  async function getSystemMode() {
    try {
      const data = await getJSON('/api/system_mode');
      return data.mode || 'manual';
    } catch(e) {
      console.error('Failed to get system mode:', e);
      return 'manual';
    }
  }

  async function setSystemMode(mode) {
    try {
      await postJSON('/api/system_mode', { mode });
      currentMode = mode;
      state.systemMode = mode;
      updateModeButtons();
      renderModeHint();
      showToast(`System mode set to ${mode.toUpperCase()}`, 'success');
      // Repaint to apply readonly styles
      renderRelays();
    } catch(e) {
      console.error('Failed to set system mode:', e);
      showToast('Failed to change system mode', 'error');
    }
  }

  function updateModeButtons() {
    const autoBtn = q('#mode-auto');
    const manualBtn = q('#mode-manual');
    if (!autoBtn || !manualBtn) return;

    if (currentMode === 'auto') {
      autoBtn.classList.add('bg-blue-600', 'text-white');
      autoBtn.classList.remove('bg-gray-700', 'text-gray-300');
      manualBtn.classList.add('bg-gray-700', 'text-gray-300');
      manualBtn.classList.remove('bg-blue-600', 'text-white');
    } else {
      manualBtn.classList.add('bg-blue-600', 'text-white');
      manualBtn.classList.remove('bg-gray-700', 'text-gray-300');
      autoBtn.classList.add('bg-gray-700', 'text-gray-300');
      autoBtn.classList.remove('bg-blue-600', 'text-white');
    }
  }

  // --- Relay Status with Lockout Info (smart fallback) ----------------------
  async function getRelayStatusSmart() {
    // Preferred: /relay/status -> { name: {state, lockout?} }
    try { return await getJSON('/relay/status'); } catch(_){ }
    // Fallbacks that return flat maps -> coerce to uniform shape
    const coerce = (flat) => Object.fromEntries(
      Object.entries(flat || {}).map(([k,v]) => [k, { state: !!v, lockout: { active:false, seconds_remaining:0 } }])
    );
    try { return coerce(await getJSON('/relays/state')); } catch(_){ }
    try { return coerce(await getJSON('/relay/state')); } catch(_){ }
    // Last resort: derive from /relays/map by setting all to false
    try {
      const m = await getJSON('/relays/map');
      const flat = {}; Object.keys(m||{}).forEach(k => flat[k]=false);
      return coerce(flat);
    } catch(_){ }
    return {}; // nothing available
  }

  async function setRelay(key, desiredOn) {
    // Try modern POST with {name,on}
    try { return await postJSON('/relay/set', { name:key, on: !!desiredOn }); } catch(_){}
    // Try GET with ?name=&on=
    try { return await getJSON(`/relay/set?name=${encodeURIComponent(key)}&on=${desiredOn?1:0}`); } catch(_){}
    throw new Error('All relay set methods failed');
  }

  // --- Toast Notifications ---------------------------------------------------
  function showToast(message, type = 'info') {
    const container = q('#toast-container') || (() => {
      const div = el(`<div id="toast-container" class="fixed top-4 right-4 z-50 flex flex-col gap-2"></div>`);
      document.body.appendChild(div);
      return div;
    })();

    const colors = {
      success: 'bg-green-600',
      error: 'bg-red-600',
      warning: 'bg-yellow-600',
      info: 'bg-blue-600'
    };

    const toast = el(`
      <div class="${colors[type] || colors.info} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-2">
        <span>${message}</span>
      </div>
    `);

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // --- UI Rendering ----------------------------------------------------------
  function formatCountdown(seconds) {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  }

  function btnTemplate(key, name, state, lockout){
    // Compact buttons: half width, color-coded
    const isOn = state;
    const isLocked = lockout && lockout.active;
    const isAutoMode = currentMode === 'auto';
    
    let bgClass = isOn ? 'bg-green-600 hover:bg-green-700' : 'bg-gray-600 hover:bg-gray-700';
    let label = (isOn ? '● ' : '○ ') + name;
    let badges = '';

    // Auto mode: add readonly class and remove hover
    if (isAutoMode) {
      bgClass = isOn ? 'bg-green-600' : 'bg-gray-600';  // Remove hover states
    }

    if (isLocked) {
      bgClass = 'bg-gray-500 cursor-not-allowed';
      badges += `<span class="text-xs ml-2 px-2 py-0.5 bg-red-500 rounded lock-pill">${formatCountdown(lockout.seconds_remaining)}</span>`;
    }

    // Add Auto pill in auto mode
    if (isAutoMode) {
      badges += `<span class="text-xs ml-2 px-2 py-0.5 bg-blue-500 rounded lock-pill">Auto</span>`;
    }

    const readonlyClass = isAutoMode ? 'readonly' : '';
    const disabledAttr = (isLocked || isAutoMode) ? 'disabled' : '';
    const ariaDisabled = isAutoMode ? 'aria-disabled="true"' : '';
    const title = isAutoMode 
      ? 'Auto mode: controls disabled. Switch to Manual to operate.' 
      : (isLocked ? `Locked: ${formatCountdown(lockout.seconds_remaining)} remaining` : '');

    return el(`
      <button 
        data-relay="${key}" 
        class="relay-btn ${bgClass} ${readonlyClass} text-white rounded-lg py-2 px-3 text-sm font-medium transition-all duration-200 flex items-center justify-between"
        ${disabledAttr}
        ${ariaDisabled}
        title="${title}"
      >
        <span>${label}</span>
        ${badges ? `<span class="flex gap-1">${badges}</span>` : ''}
      </button>
    `);
  }

  function renderModeHint() {
    const el = q('#relays-mode-hint');
    if (!el) return;
    
    if (currentMode === 'auto') {
      el.textContent = 'Auto: controls disabled. Switch to Manual to operate.';
      el.className = 'text-xs text-blue-400 mt-2';
    } else {
      el.textContent = 'Manual: relays can be switched from the panel.';
      el.className = 'text-xs text-gray-400 mt-2';
    }
  }

  // Render the 8-button grid consistently
  function renderRelays(){
    const grid = q('#relays-grid');
    if (!grid) return console.warn('#relays-grid missing');
    grid.innerHTML = '';

    let rendered = 0;
    for (const key of RELAY_ORDER){
      const info = state.relays[key];
      if (!info) continue; // keep order; skip if backend didn't send
      rendered++;
      const on = !!info.state;
      const name = RELAY_LABELS[key] || key;
      const btn = btnTemplate(
        key,
        name,
        on,
        info.lockout
      );
      // Readonly class in Auto mode
      if (state.systemMode === 'auto') btn.classList.add('readonly');

      // Handlers (only in Manual)
      btn.onclick = () => {
        if (state.systemMode === 'auto') return;
        requestToggle(key);
      };
      btn.onkeydown = (e) => {
        if (state.systemMode === 'auto') return;
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); requestToggle(key); }
      };

      grid.appendChild(btn);
    }
    if (rendered === 0){
      grid.innerHTML = '<div class="text-sm text-gray-400">No relays found from API.</div>';
    }
    renderModeHint();
  }

  function wire(){
    const grid = q('#relays-grid');
    if (!grid) return;
    
    grid.querySelectorAll('.relay-btn').forEach(btn => {
      // keep wiring minimal; click/keydown set in renderRelays based on mode
      if (state.systemMode === 'auto') {
        btn.addEventListener('click', (e) => { e.preventDefault(); showToast('Controls disabled in Auto mode', 'warning'); });
        btn.addEventListener('keydown', (e) => { if (e.key==='Enter'||e.key===' ') { e.preventDefault(); }});
      }
    });

    // Wire mode toggle buttons
    const autoBtn = q('#mode-auto');
    const manualBtn = q('#mode-manual');
    
    if (autoBtn) {
      autoBtn.addEventListener('click', () => {
        if (currentMode !== 'auto') {
          setSystemMode('auto');
        }
      });
    }
    
    if (manualBtn) {
      manualBtn.addEventListener('click', () => {
        if (currentMode !== 'manual') {
          setSystemMode('manual');
        }
      });
    }
  }

  // Helpers and periodic refresh
  function fmtSeconds(sec){
    const s = Math.max(0, Math.floor(sec));
    const m = Math.floor(s/60), r = s%60; return m>0? `${m}m ${r}s` : `${r}s`;
  }
  function tickCountdowns(){
    document.querySelectorAll('#relays-grid .countdown-pill').forEach(elm => {
      const cur = parseInt(elm.getAttribute('data-countdown')||'0',10);
      const next = Math.max(0, cur-1);
      elm.setAttribute('data-countdown', String(next));
      elm.textContent = fmtSeconds(next);
    });
  }
  async function refreshRelays(){
    try{
      const map = await getRelayStatusSmart();
      state.relays = map;
      renderRelays();
      tickCountdowns();
    }catch(e){ console.error('refreshRelays error', e); }
  }
  async function refreshSystemMode(){
    try{
      const data = await getSystemMode();
      currentMode = data || 'manual';
      state.systemMode = currentMode;
      updateModeButtons();
      renderModeHint();
    }catch(_){ }
  }

  // Initialize on load
  document.addEventListener('DOMContentLoaded', () => {
    refreshSystemMode();
    refreshRelays();
    wire();
    setInterval(refreshRelays, 1000);
  });

  // Public toggle that honors lockout feedback
  async function requestToggle(key){
    try{
      const info = state.relays[key] || {};
      const desired = !info.state;
      const result = await setRelay(key, desired);
      if (result && (result.ok===false || result.changed===false)){
        const reason = result.reason || 'unknown';
        const cooldown = result.cooldown_remaining || 0;
        if (reason==='cooldown' || reason==='antiflap'){
          showToast(`Protected: ready in ${fmtSeconds(cooldown)}`,'warning');
        } else {
          showToast(`Action blocked: ${result.message || reason}`,'error');
        }
      }
      // Refresh after toggle
      setTimeout(refreshRelays, 150);
    }catch(e){
      console.error('Toggle failed', key, e);
      showToast(`Failed to toggle ${key}`, 'error');
    }
  }
})();
