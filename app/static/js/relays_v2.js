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
  // Global asset version for cache-busting; populated from /api/version on init
  let ASSET_VER = '';

  // Fixed relay order + display names
  const RELAY_ORDER = [
    'dosing_ph_up', 'dosing_grow', 'dosing_micro', 'dosing_bloom',
    'main_pump', 'chiller_pump', 'chiller_power', 'lights'
  ];
  const RELAY_LABELS = {
    dosing_ph_up: 'pH Up Pump',
    dosing_grow: 'Grow Pump',
    dosing_micro: 'Micro Pump',
    dosing_bloom: 'Bloom Pump',
    main_pump: 'Main Pump',
    chiller_pump: 'Chiller Pump',
    chiller_power: 'Water Chiller (AC)',
    lights: 'Grow Lights (AC)'
  };
  // Mirror backend relay pins for tooltip context
  const RELAY_PINS = {
    lights: 21,
    chiller_pump: 16,
    chiller_power: 20,
    main_pump: 26,
    dosing_grow: 6,
    dosing_micro: 13,
    dosing_bloom: 19,
    dosing_ph_up: 5,
  };

  // Global UI state
  const state = { systemMode: 'manual', relays: {}, estop: false, restoredBoot: false };

  async function getJSON(url){
    // Append cache-buster to avoid stale responses when user requests a full refresh
    const bust = ASSET_VER ? `v=${encodeURIComponent(ASSET_VER)}` : `t=${Date.now()}`;
    url += (url.includes('?') ? '&' : '?') + bust;
    const r = await fetch(url, {cache:'no-store'});
    if (!r.ok) throw new Error('HTTP '+r.status+' for '+url);
    return r.json();
  }

  async function postJSON(url, body){
    const bust = ASSET_VER ? `v=${encodeURIComponent(ASSET_VER)}` : `t=${Date.now()}`;
    url += (url.includes('?') ? '&' : '?') + bust;
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
      // Wait a moment for backend propagation to complete
      await new Promise(resolve => setTimeout(resolve, 100));
      // Notify all controller tabs to refresh their modes from backend
      await refreshAllControllerModes();
    } catch(e) {
      console.error('Failed to set system mode:', e);
      showToast('Failed to change system mode', 'error');
    }
  }
  
  async function refreshAllControllerModes() {
    // Notify each controller module to sync from backend (with delay between calls)
    console.log('[System] Refreshing all controller modes from backend...');
    const refreshes = [];
    if (window.refreshServerMode) refreshes.push(window.refreshServerMode()); // Sensors
    if (window.syncCircModeFromBackend) refreshes.push(window.syncCircModeFromBackend()); // Circulation
    if (window.syncLightsModeFromBackend) refreshes.push(window.syncLightsModeFromBackend()); // Lights
    if (window.syncScheduleModeFromBackend) refreshes.push(window.syncScheduleModeFromBackend()); // Schedule
    await Promise.all(refreshes);
    console.log('[System] All controller modes refreshed');
  }
  
  async function syncSystemModeFromControllers() {
    // Check if all controllers are in the same mode, and if so, sync system mode
    try {
      const resp = await getJSON('/api/controllers/status');
      const controllers = resp.controllers || {};
      const controllerNames = Object.keys(controllers);
      const modes = Object.values(controllers).map(c => c.mode).filter(m => m);
      
      console.log('[System] Checking controller modes:', {
        system_mode: resp.system_mode,
        controllers: Object.fromEntries(controllerNames.map(name => [name, controllers[name].mode]))
      });
      
      if (modes.length === 0) {
        console.log('[System] No controller modes found, skipping sync');
        return;
      }
      
      // Check if all controllers have the same mode
      const firstMode = modes[0];
      const allSame = modes.every(m => m === firstMode);
      
      console.log('[System] Mode check:', {
        allSame,
        firstMode,
        systemMode: resp.system_mode,
        needsSync: allSame && firstMode !== resp.system_mode
      });
      
      if (allSame && firstMode !== resp.system_mode) {
        console.log(`[System] All ${modes.length} controllers are "${firstMode}", syncing system mode from "${resp.system_mode}"...`);
        await postJSON('/api/system_mode', { mode: firstMode });
        currentMode = firstMode;
        state.systemMode = firstMode;
        updateModeButtons();
        renderModeHint();
        console.log(`[System] ✓ System mode synced to "${firstMode}"`);
      } else if (allSame) {
        console.log(`[System] All controllers match system mode "${firstMode}", no sync needed`);
      } else {
        console.log('[System] Controllers have different modes, no sync performed');
      }
    } catch (e) {
      console.error('[System] Failed to sync system mode from controllers:', e);
    }
  }
  window.syncSystemModeFromControllers = syncSystemModeFromControllers;

  function updateModeButtons() {
    const autoBtn = q('#mode-auto');
    const manualBtn = q('#mode-manual');
    if (!autoBtn || !manualBtn) return;

    // Reset active classes
    autoBtn.classList.remove('active-auto');
    manualBtn.classList.remove('active-manual');

    if (currentMode === 'auto') {
      autoBtn.classList.add('active-auto');
    } else {
      manualBtn.classList.add('active-manual');
    }
  }

  // --- E-Stop API ------------------------------------------------------------
  async function getEstop() {
    try {
      const r = await fetch('/api/estop', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP '+r.status);
      const j = await r.json();
      return !!j.active;
    } catch(e) {
      console.warn('getEstop failed', e);
      return false;
    }
  }

  async function toggleEstop() {
    try {
      // Use server-side toggle endpoint (backend owns the truth)
      const r = await fetch('/api/relays/estop/toggle', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (!r.ok) throw new Error('HTTP '+r.status);
      const j = await r.json().catch(()=>({}));
      
      // Update UI state from backend response
      state.estop = !!(j.active);
      
      // Immediately update UI before async refresh
      updateEstopButton();
      updateEstopBanner();
      renderModeHint();
      
      // Force immediate relay state refresh (backend changed all relays)
      await refreshRelays();
      
      showToast(state.estop ? 'E-STOP engaged: all relays OFF' : 'E-STOP released', state.estop ? 'error' : 'success');
    } catch(e) {
      console.error('toggleEstop failed', e);
      showToast('Failed to toggle E-STOP', 'error');
    }
  }

  function updateEstopButton() {
    const btn = q('#estop-btn');
    if (!btn) return;
    if (state.estop) {
      btn.classList.add('active');
      btn.textContent = 'E‑STOP ACTIVE';
      btn.title = 'E-Stop is engaged: all relays forced OFF and blocked until release';
    } else {
      btn.classList.remove('active');
      btn.textContent = 'E‑STOP';
      btn.title = 'Emergency Stop: forces all relays OFF and blocks ON until released';
    }
  }

  // --- Relay Status with Lockout Info (smart fallback) ----------------------
  async function getRelayStatusSmart() {
    // Preferred: new wrapper /api/relays/status -> { mode, estop, relays: { name: {is_on} } }
    try {
      const wrap = await getJSON('/api/relays/status');
      if (wrap && wrap.relays) {
        // sync system mode/estop from wrapper
        if (wrap.mode) { currentMode = String(wrap.mode); state.systemMode = currentMode; updateModeButtons(); renderModeHint(); }
        if (typeof wrap.estop === 'boolean') { state.estop = wrap.estop; updateEstopButton(); }
        if (typeof wrap.restored === 'boolean') { state.restoredBoot = !!wrap.restored; }
        // Coerce to { key: {state, lockout} } and ensure all expected relays are present
        const map = {};
        // Start with all known keys so UI doesn't go empty if backend omits some
        RELAY_ORDER.forEach(k => { map[k] = { state: false, lockout: { active:false, seconds_remaining:0 } }; });
        Object.entries(wrap.relays).forEach(([k, v]) => {
          map[k] = { state: !!(v && v.is_on), lockout: { active:false, seconds_remaining:0 } };
        });
        return map;
      }
    } catch(_){}
    // Legacy: /relay/status -> { key: {state, lockout?} }
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
    // Single primary endpoint (now implemented backend-side). If this fails, we degrade gracefully.
    const payload = { on: !!desiredOn };
    const started = performance.now();
    try {
      const r = await postJSON(`/api/relay/${encodeURIComponent(key)}/toggle`, payload);
      r._latency_ms = Math.round(performance.now() - started);
      return r;
    } catch(ePrimary) {
      console.warn('Primary toggle failed, falling back', key, ePrimary);
      try {
        const r2 = await postJSON('/relay/set', { name:key, on: !!desiredOn });
        r2._latency_ms = Math.round(performance.now() - started);
        r2._fallback = 'relay_set_post';
        return r2;
      } catch(ePost){
        try {
          const r3 = await getJSON(`/relay/set?name=${encodeURIComponent(key)}&on=${desiredOn?1:0}`);
          r3._latency_ms = Math.round(performance.now() - started);
          r3._fallback = 'relay_set_get';
          return r3;
        } catch(eGet){
          window.__relayErrors = window.__relayErrors || [];
          window.__relayErrors.push({ key, at: Date.now(), ePrimary: String(ePrimary), ePost: String(ePost), eGet: String(eGet) });
          throw new Error('All relay set methods failed for '+key);
        }
      }
    }
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

  function btnTemplate(key, name, stateOn, lockout){
    // Compact buttons: half width, color-coded
    const isOn = stateOn;
    const isLocked = lockout && lockout.active;
    const isAutoMode = currentMode === 'auto';
    const isEstop = state.estop === true;
    
      let bgClass = isOn ? 'relay-on' : 'relay-off';
    let label = (isOn ? '● ' : '○ ') + name;
    let badges = '';

    // Auto mode: add readonly class and remove hover
    // Auto mode: keep same background; readonly styling handled by CSS class

      // Add countdown pill when lockout info exists (still allow click in Manual)
      if (isLocked && !isEstop) {
        badges += `<span class="countdown-pill" data-countdown="${lockout.seconds_remaining}">${formatCountdown(lockout.seconds_remaining)}</span>`;
      }

    // Add Auto pill in auto mode
    if (isAutoMode && !isEstop) { badges += `<span class="lock-pill">Auto</span>`; }
    if (isEstop) { badges += `<span class="lock-pill" style="border-color: rgba(239,68,68,.65); color:#fecaca;">E‑Stop</span>`; }

    const readonlyClass = (isAutoMode || isEstop) ? 'readonly' : '';
    const disabledAttr = (isAutoMode || isEstop) ? 'disabled' : '';
    const ariaDisabled = (isAutoMode || isEstop) ? 'aria-disabled="true"' : '';
    const title = isEstop
      ? 'E-Stop engaged: controls disabled until released.'
      : (isAutoMode
        ? 'Auto mode: controls disabled. Switch to Manual to operate.'
        : (isLocked ? `Cooldown active (${formatCountdown(lockout.seconds_remaining)}) — manual override allowed.` : ''));

    const pin = RELAY_PINS[key];
    const onOff = isOn ? 'ON' : 'OFF';
    const tooltip = (title ? `${title}\n` : '') + `${name} — BCM ${pin ?? 'N/A'} — ${onOff}`;
    const ariaPressed = isOn ? 'true' : 'false';

    return el(`
      <button 
        data-relay="${key}" 
  class="relay-btn ${bgClass} ${readonlyClass} text-white rounded-lg py-2 px-3 text-sm font-medium transition-all duration-200 flex items-center justify-between"
        ${disabledAttr}
        ${ariaDisabled}
        role="button" aria-pressed="${ariaPressed}"
        title="${tooltip}"
      >
        <span>${label}</span>
        ${badges ? `<span class="flex gap-1">${badges}</span>` : ''}
      </button>
    `);
  }

  function renderModeHint() {
    const el = q('#relays-mode-hint');
    if (!el) return;
    
    if (state.estop) {
      el.textContent = 'E‑STOP ACTIVE: all relays are forced OFF and controls are disabled until released.';
      el.className = 'text-xs text-red-400 mt-2';
    } else if (currentMode === 'auto') {
      const base = 'Auto: controls disabled. Switch to Manual to operate.';
      const extra = state.restoredBoot ? ' \u2022 Restored critical relays from last state.' : '';
      el.textContent = base + extra;
      el.className = 'text-xs text-blue-400 mt-2';
    } else {
      el.textContent = 'Manual: relays can be switched from the panel.';
      el.className = 'text-xs text-gray-400 mt-2';
    }
  }

  function updateEstopBanner() {
    const banner = q('#estop-banner');
    if (!banner) return;
    banner.classList.toggle('hidden', !state.estop);
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
  if (state.systemMode === 'auto' || state.estop) btn.classList.add('readonly');

      // Handlers (only in Manual)
      btn.onclick = () => {
        if (state.systemMode === 'auto' || state.estop) return;
        requestToggle(key);
      };
      btn.onkeydown = (e) => {
        if (state.systemMode === 'auto' || state.estop) return;
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); requestToggle(key); }
      };

      grid.appendChild(btn);
    }
    if (rendered === 0){
      grid.innerHTML = '<div class="text-sm text-gray-400">No relays found from API.</div>';
    }
    
    // Add status subfooter with timestamp for quick triage
    const subfooter = q('#relays-status-subfooter');
    if (subfooter) {
      const now = new Date();
      const hms = now.toTimeString().split(' ')[0]; // HH:MM:SS
      subfooter.textContent = `Last updated at ${hms}`;
    }
    
    renderModeHint();
    updateEstopBanner();
  }

  function wire(){
    const grid = q('#relays-grid');
  if (!grid) return;
    
    grid.querySelectorAll('.relay-btn').forEach(btn => {
      // keep wiring minimal; click/keydown set in renderRelays based on mode
      if (state.systemMode === 'auto' || state.estop) {
        const msg = state.estop ? 'E-STOP engaged: controls disabled' : 'Controls disabled in Auto mode';
        btn.addEventListener('click', (e) => { e.preventDefault(); showToast(msg, 'warning'); });
        btn.addEventListener('keydown', (e) => { if (e.key==='Enter'||e.key===' ') { e.preventDefault(); }});
      }
    });

    // Wire mode toggle buttons
  const autoBtn = q('#mode-auto');
  const manualBtn = q('#mode-manual');
  const estopBtn = q('#estop-btn');
    
    if (autoBtn) {
      autoBtn.addEventListener('click', () => {
        if (state.estop) { showToast('E-STOP engaged: mode change blocked','warning'); return; }
        const prev = currentMode;
        setSystemMode('auto');
        if (prev === 'auto') {
          showToast('Already in AUTO mode','info');
        }
      });
    }
    
    if (manualBtn) {
      manualBtn.addEventListener('click', () => {
        if (state.estop) { showToast('E-STOP engaged: mode change blocked','warning'); return; }
        const prev = currentMode;
        setSystemMode('manual');
        if (prev === 'manual') {
          showToast('Already in MANUAL mode','info');
        } else {
          showToast('Switched to MANUAL: relay controls enabled','success');
        }
      });
    }
    if (estopBtn) {
      estopBtn.addEventListener('click', () => {
        if (!state.estop) {
          const ok = confirm('Engage E-STOP?\nThis will immediately turn all relays OFF and block ON commands until released.');
          if (!ok) return;
        }
        toggleEstop();
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
  async function refreshEstop(){
    try {
      const active = await getEstop();
      if (state.estop !== active) {
        state.estop = active;
        updateEstopButton();
        renderRelays();
      }
    } catch(_){}
  }

  // Initialize when DOM is ready (works even if script loads after DOMContentLoaded)
  let _bootstrapped = false;
  function initRelaysUI(){
    if (_bootstrapped) return; _bootstrapped = true;
    // Fetch asset version early for consistent cache-busting tokens
    (async () => { try { const v = await getJSON('/api/version'); ASSET_VER = v.version || ''; } catch(_){ ASSET_VER=''; } })();
    refreshSystemMode();
    refreshEstop();
    refreshRelays();
    wire();
    // Dynamic polling intervals from settings (fallbacks)
    window.APP_POLL = window.APP_POLL || { relays: 1000, sensors: 5000 };
    let relaysTimer = setInterval(refreshRelays, window.APP_POLL.relays || 1000);
    let estopTimer = setInterval(refreshEstop, 2000);
    let systemModeTimer = setInterval(refreshSystemMode, 3000); // Poll system mode every 3s

    window.addEventListener('settings:ui', (ev)=>{
      try {
        const poll = (ev.detail && ev.detail.poll) || window.APP_POLL || {};
        if (relaysTimer) clearInterval(relaysTimer);
        relaysTimer = setInterval(refreshRelays, Math.max(250, parseInt(poll.relays||1000,10)));
      } catch(e) { /* noop */ }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRelaysUI);
  } else {
    // DOM already loaded; initialize immediately
    initRelaysUI();
  }

  // Public toggle that honors lockout feedback
  async function requestToggle(key){
    try{
      if (state.estop) { showToast('E-STOP engaged: action blocked', 'warning'); return; }
      // Debounce: prevent rapid double toggles within 400ms per relay
      window.__relayLastClick = window.__relayLastClick || {};
      const now = Date.now();
      const last = window.__relayLastClick[key] || 0;
      if (now - last < 400){
        return; // ignore rapid re-click
      }
      window.__relayLastClick[key] = now;
      const info = state.relays[key] || {};
      // micro feedback
      const btn = document.querySelector(`[data-relay="${key}"]`);
      if (btn) btn.classList.add('loading');
      const desired = !info.state;
      const result = await setRelay(key, desired);
      const latency = result && result._latency_ms !== undefined ? result._latency_ms : null;
      if (result && (result.ok===false || result.changed===false)){
        const reason = result.reason || 'unknown';
        const cooldown = result.cooldown_remaining || 0;
        if (reason==='cooldown' || reason==='antiflap'){
          showToast(`Protected: ready in ${fmtSeconds(cooldown)}`,'warning');
        } else if (reason==='blocked' && key==='lights') {
          showToast('Lights changes are limited: use schedule, override, emergency, apply settings, or restore.', 'warning');
        } else {
          showToast(`Action blocked: ${result.message || reason}`,'error');
        }
      } else if (latency !== null) {
        // Success feedback with tiny latency info (for performance triage)
        showToast(`${key} toggled (${desired? 'ON':'OFF'}) in ${latency}ms`, 'success');
      }
      // Refresh after toggle
      setTimeout(refreshRelays, 150);
      if (btn) setTimeout(() => btn.classList.remove('loading'), 350);
    }catch(e){
      console.error('Toggle failed', key, e);
      showToast(`Failed to toggle ${key}`, 'error');
    }
  }
})();
