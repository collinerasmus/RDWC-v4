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
      updateModeButtons();
      renderModeHint();
      showToast(`System mode set to ${mode.toUpperCase()}`, 'success');
      // Repaint to apply readonly styles
      await paint();
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

  // --- Relay Status with Lockout Info ---------------------------------------
  async function getRelayStatus() {
    // Get full status including lockout information
    const status = await getJSON('/relay/status');
    return status;
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

  async function paint() {
    const grid = q('#relays-grid');
    if (!grid) return;
    
    grid.innerHTML = '<div class="col-span-2 text-gray-400 text-sm text-center">Loading relays…</div>';

    try {
      const [modeData, status] = await Promise.all([
        getJSON('/api/system_mode').catch(() => ({mode: 'manual'})),
        getRelayStatus()
      ]);

      currentMode = modeData.mode || 'manual';
      updateModeButtons();
      renderModeHint();

      grid.innerHTML = '';
      
      Object.keys(status).forEach(key => {
        const info = status[key];
        const name = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        const btn = btnTemplate(key, name, info.state, info.lockout);
        grid.appendChild(btn);
      });
      
      wire();
    } catch(e) {
      console.error('Paint failed:', e);
      grid.innerHTML = '<div class="col-span-2 text-red-400 text-sm text-center">Failed to load relays</div>';
    }
  }

  function wire(){
    const grid = q('#relays-grid');
    if (!grid) return;
    
    grid.querySelectorAll('.relay-btn').forEach(btn => {
      // UI-level guard: block all interaction in Auto mode
      btn.addEventListener('click', async (e) => {
        if (currentMode === 'auto') {
          e.preventDefault();
          showToast('Controls disabled in Auto mode', 'warning');
          return;
        }
        
        const key = btn.getAttribute('data-relay');
        const wasOn = btn.textContent.includes('●');
        
        try{
          btn.disabled = true;
          btn.style.opacity = '0.6';
          
          const result = await setRelay(key, !wasOn);
          
          // Check if request was blocked
          if (result.ok === false || result.changed === false) {
            const reason = result.reason || 'unknown';
            const cooldown = result.cooldown_remaining || 0;
            
            if (reason === 'cooldown' || reason === 'antiflap') {
              showToast(`Protected: ready in ${formatCountdown(cooldown)}`, 'warning');
            } else if (reason === 'blocked') {
              showToast(`Action blocked: ${result.message || 'not allowed'}`, 'error');
            }
          }
          
          // Refresh to show actual state
          await paint();
          
        }catch(e){
          console.error('Toggle failed', key, e);
          showToast(`Failed to toggle ${key}`, 'error');
        }finally{
          btn.disabled = false;
          btn.style.opacity = '1';
        }
      });

      // Keyboard guard for accessibility
      btn.addEventListener('keydown', (e) => {
        if (currentMode === 'auto') {
          e.preventDefault();
          return;
        }
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          btn.click();
        }
      });
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

  // Fast refresh with debouncing
  let refreshTimeout = null;
  async function periodicRefresh(){
    try{
      const status = await getRelayStatus();
      
      document.querySelectorAll('#relays-grid .relay-btn').forEach(btn => {
        const key = btn.getAttribute('data-relay');
        if (!(key in status)) return;
        
        const info = status[key];
        const isOn = info.state;
        const isLocked = info.lockout && info.lockout.active;
        
        // Update button appearance
        const symbol = isOn ? '● ' : '○ ';
        const name = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        
        // Update label
        const labelSpan = btn.querySelector('span');
        if (labelSpan) labelSpan.textContent = symbol + name;
        
        // Update colors
        btn.classList.remove('bg-green-600', 'hover:bg-green-700', 'bg-gray-600', 'hover:bg-gray-700', 'bg-gray-500', 'cursor-not-allowed');
        
        if (isLocked) {
          btn.classList.add('bg-gray-500', 'cursor-not-allowed');
          btn.disabled = true;
          
          // Update or add countdown badge
          let badge = btn.querySelector('span:last-child');
          const countdownText = formatCountdown(info.lockout.seconds_remaining);
          if (badge && badge.classList.contains('bg-red-500')) {
            badge.textContent = countdownText;
          } else {
            badge = el(`<span class="text-xs ml-2 px-2 py-0.5 bg-red-500 rounded">${countdownText}</span>`);
            btn.appendChild(badge);
          }
        } else {
          btn.disabled = false;
          btn.classList.add(isOn ? 'bg-green-600' : 'bg-gray-600');
          btn.classList.add(isOn ? 'hover:bg-green-700' : 'hover:bg-gray-700');
          
          // Remove countdown badge if present
          const badge = btn.querySelector('span.bg-red-500');
          if (badge) badge.remove();
        }
      });
      
    }catch(e){ 
      console.debug('Refresh skipped', e); 
    }
  }

  // Initialize on load
  document.addEventListener('DOMContentLoaded', () => {
    paint().catch(err => {
      const grid = q('#relays-grid');
      if (grid) grid.innerHTML = `<div class="col-span-2 text-red-400 text-sm text-center">Error: ${String(err)}</div>`;
      console.error(err);
    });
    
    // Fast 1-second refresh
    setInterval(periodicRefresh, 1000);
  });
})();
