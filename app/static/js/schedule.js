// Schedule Module - Timeline, Targets, and Action Preview
(function(){
  'use strict';

  // ===== MODE MANAGEMENT =====
  let scheduleMode = localStorage.getItem('schedule_mode') || 'auto';

  function scheduleSetMode(next) {
    if (!['auto', 'manual', 'maint'].includes(next)) return;
    scheduleMode = next;
    localStorage.setItem('schedule_mode', next);

    ['auto', 'manual', 'maint'].forEach(m => {
      const btn = document.getElementById(`schedule-mode-${m}`);
      if (btn) btn.classList.toggle('active', m === next);
    });

    // Show/hide content sections if they exist
    const autoContent = document.getElementById('schedule-auto-content');
    const manualContent = document.getElementById('schedule-manual-content');
    const maintContent = document.getElementById('schedule-maint-content');
    if (autoContent) autoContent.style.display = (next === 'auto') ? 'block' : 'none';
    if (manualContent) manualContent.style.display = (next === 'manual') ? 'block' : 'none';
    if (maintContent) maintContent.style.display = (next === 'maint') ? 'block' : 'none';

    updateScheduleHealth();
    // Check if all controllers now match and sync system mode if so
    if (window.syncSystemModeFromControllers) {
      setTimeout(() => window.syncSystemModeFromControllers(), 200);
    }
  }
  
  async function syncScheduleModeFromBackend() {
    try {
      // Schedule controller uses lights mode since schedule controls lights
      const r = await fetch('/api/controller/lights/mode', {cache: 'no-store'});
      if (!r.ok) return;
      const data = await r.json();
      if (data.ok && data.mode) {
        // Normalize maintenance to maint for UI
        const mode = data.mode === 'maintenance' ? 'maint' : data.mode;
        scheduleSetMode(mode);
        console.log('[Schedule] Synced mode from backend (lights):', mode);
      }
    } catch (e) {
      console.error('[Schedule] Failed to sync mode from backend:', e);
    }
  }
  window.syncScheduleModeFromBackend = syncScheduleModeFromBackend;

  function updateScheduleHealth() {
    const chip = document.getElementById('schedule-health-indicator');
    if (!chip) return;

    if (scheduleMode === 'maint') {
      chip.textContent = 'MAINT';
      chip.className = 'ui-status-chip warning';
      return;
    }
    const ok = !!(scheduleCache && Array.isArray(scheduleCache.weeks) && scheduleCache.weeks.length);
    if (!ok) { chip.textContent = 'UNSET'; chip.className = 'ui-status-chip warning'; return; }
    chip.textContent = 'OK';
    chip.className = 'ui-status-chip success';
  }

  window.scheduleSetMode = scheduleSetMode;

  // Initialize mode on load
  document.addEventListener('DOMContentLoaded', () => {
    scheduleSetMode(scheduleMode);
    // Poll mode every 5 seconds to pick up system mode changes (if backend endpoint exists)
    setInterval(() => {
      if (window.syncScheduleModeFromBackend) {
        window.syncScheduleModeFromBackend();
      }
    }, 5000);
  });

  // ===== SCHEDULE DISPLAY LOGIC =====

  let scheduleCache = null;
  let pollTimer = null;

  function el(id){ return document.getElementById(id); }

  function getDayN(dateStr){
    if(!dateStr) return null;
    if(window.rdwcSettings?.calculateDayN){
      return window.rdwcSettings.calculateDayN(dateStr, window.rdwcSettings.get?.('general.timezone'));
    }
    try{
      const start = new Date(`${dateStr}T00:00:00`);
      const diff = Date.now() - start.getTime();
      const day = Math.floor(diff/86400000)+1;
      return Number.isFinite(day) ? Math.max(1, day) : null;
    }catch(_){
      return null;
    }
  }

  async function fetchSchedule(){
    try{
      const r = await fetch('/api/nutrient_schedule', {cache: 'no-store'});
      if(!r.ok) return null;
      const data = await r.json();
      scheduleCache = data;
      return data;
    }catch(e){ return null; }
  }

  async function fetchPlan(hours=48){
    try{
      const r = await fetch(`/api/schedule/plan?hours=${hours}`, {cache: 'no-store'});
      if(!r.ok) return {plan: []};
      return await r.json();
    }catch(e){ return {plan: []}; }
  }

  async function seedSchedule(){
    try{
      const r = await fetch('/api/nutrient_schedule/seed?source=ehg-defaults', {method: 'POST'});
      const data = await r.json();
      if(r.ok && data.ok){
        showToast('Schedule seeded with EHG defaults', 'success');
        await fetchSchedule();
        await renderTimeline();
        return true;
      } else {
        showToast(data.error || 'Seed failed', 'error');
        return false;
      }
    }catch(e){
      showToast('Seed error: ' + e.message, 'error');
      return false;
    }
  }

  function renderTimeline(){
    const timeline = el('schedule-timeline-lanes');
    if(!timeline) return;

    const sched = scheduleCache;
    if(!sched || !sched.weeks || sched.weeks.length === 0){
      timeline.innerHTML = `
        <div style="padding:24px;text-align:center;color:#94a3b8;">
          <div style="font-size:1.1rem;margin-bottom:12px;">📅 No schedule configured</div>
          <button id="btnSeedSchedule" class="btn-secondary">Seed Defaults (12 weeks)</button>
        </div>
      `;
      el('btnSeedSchedule')?.addEventListener('click', async ()=>{
        const btn = el('btnSeedSchedule');
        if(btn) btn.disabled = true;
        await seedSchedule();
        if(btn) btn.disabled = false;
        updateKpis();
      });
      // Also wire settings panel seed button if present
      const seedSettingsBtn = el('scheduleSeedBtn');
      if(seedSettingsBtn && !seedSettingsBtn._wired){
        seedSettingsBtn._wired = true;
        seedSettingsBtn.addEventListener('click', async ()=>{
          seedSettingsBtn.disabled = true;
          await seedSchedule();
          seedSettingsBtn.disabled = false;
          updateKpis();
          renderTimeline();
        });
      }
      return;
    }

    const currentWeek = sched.current_week || 1;
    const firstWeekNum = sched.weeks[0]?.week ?? null;
    const firstIsGermination = (sched.weeks[0]?.phase === 'germination');
    const subtractOne = firstIsGermination && firstWeekNum !== 0; // If first week is germination but numbered 1, shift display

    // Calendar-style grid layout (4 columns x 3 rows for 12 weeks)
    let html = '<div style="padding:16px 0;">';
    html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;max-width:100%;">';

    sched.weeks.forEach(w => {
      const phase = w.phase || 'week';
      const isCurrent = w.week === currentWeek;
      const phaseColors = {
        germination:'rgba(168,85,247,0.15)',
        seedling:'rgba(147,197,253,0.15)',
        veg:'rgba(34,197,94,0.15)',
        preflower:'rgba(251,191,36,0.18)',
        flower:'rgba(217,70,239,0.20)',
        flush:'rgba(59,130,246,0.18)'
      };
      const borderColors = {
        germination:'rgba(168,85,247,0.45)',
        seedling:'rgba(147,197,253,0.45)',
        veg:'rgba(34,197,94,0.45)',
        preflower:'rgba(251,191,36,0.55)',
        flower:'rgba(217,70,239,0.55)',
        flush:'rgba(59,130,246,0.50)'
      };
      const phaseIcons = {
        germination:'🌾',
        seedling:'🌱',
        veg:'🌿',
        preflower:'🌸',
        flower:'🌺',
        flush:'💧'
      };
      const bg = phaseColors[phase] || 'rgba(148,163,184,0.15)';
      const bd = borderColors[phase] || 'rgba(148,163,184,0.40)';
      const icon = phaseIcons[phase] || '📅';
      
      const boxStyle = `
        padding:14px 12px;
        border:2px solid ${bd};
        border-radius:10px;
        background:${bg};
        cursor:pointer;
        position:relative;
        transition:all .2s ease;
        min-height:110px;
        display:flex;
        flex-direction:column;
      `;
      
      html += `<div style="${boxStyle}" data-week="${w.week}" class="week-block">`;
      
      // Header row with phase icon and week number
      html += `<div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px;">`;
      html += `<div style="font-size:1.3rem;line-height:1;">${icon}</div>`;
      const displayWeek = phase === 'germination' ? 0 : w.week;
      const displayWeek = phase === 'germination' ? 0 : (subtractOne ? (w.week - 1) : w.week);
      html += `<div style="font-size:0.85rem;font-weight:700;color:#e0e0e0;">W${displayWeek}</div>`;
      html += `</div>`;
      
      // Phase name
      html += `<div style="font-size:0.7rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">${phase}</div>`;
      
      // Nutrient proportion bars
      const total = w.grow_ml10 + w.micro_ml10 + w.bloom_ml10;
      const growPct = total > 0 ? (w.grow_ml10 / total * 100).toFixed(0) : 0;
      const microPct = total > 0 ? (w.micro_ml10 / total * 100).toFixed(0) : 0;
      const bloomPct = total > 0 ? (w.bloom_ml10 / total * 100).toFixed(0) : 0;
      
      html += `<div style="margin-bottom:6px;">`;
      html += `<div style="display:flex;height:18px;border-radius:4px;overflow:hidden;border:1px solid rgba(148,163,184,0.25);">`;
      if(total > 0){
        html += `<div style="width:${growPct}%;background:#22c55e;" title="Grow ${w.grow_ml10}ml"></div>`;
        html += `<div style="width:${microPct}%;background:#3b82f6;" title="Micro ${w.micro_ml10}ml"></div>`;
        html += `<div style="width:${bloomPct}%;background:#fbbf24;" title="Bloom ${w.bloom_ml10}ml"></div>`;
      } else {
        html += `<div style="width:100%;background:rgba(148,163,184,0.15);display:flex;align-items:center;justify-content:center;font-size:0.65rem;color:#94a3b8;">Flush</div>`;
      }
      html += `</div>`;
      html += `<div style="display:flex;justify-content:space-between;font-size:0.65rem;color:#94a3b8;margin-top:2px;">`;
      html += `<span>G:${w.grow_ml10}</span><span>M:${w.micro_ml10}</span><span>B:${w.bloom_ml10}</span>`;
      html += `</div></div>`;
      
      // Target values
      html += `<div style="flex:1;display:flex;flex-direction:column;gap:3px;font-size:0.75rem;color:#cbd5e1;">`;
      html += `<div><span style="color:#94a3b8;">EC:</span> <strong>${w.ec_target}</strong></div>`;
      // Calculate pH setpoint as midpoint of range
      const phSetpoint = ((w.ph_low + w.ph_high) / 2).toFixed(2);
      html += `<div><span style="color:#94a3b8;">pH:</span> ${phSetpoint}</div>`;
      html += `<div><span style="color:#94a3b8;">🌡:</span> ${w.temp_target}°C</div>`;
      html += `<div><span style="color:#94a3b8;">💡:</span> ${w.lights}</div>`;
      html += `</div>`;
      
      // Current week indicator
      if(isCurrent){
        html += `<div style="position:absolute;top:12px;left:50%;transform:translateX(-50%);background:#ef4444;color:#fff;padding:4px 10px;border-radius:14px;font-size:0.7rem;font-weight:700;box-shadow:0 4px 12px rgba(239,68,68,0.5);z-index:10;">NOW</div>`;
      }
      
      html += '</div>';
    });

    html += '</div></div>';
    timeline.innerHTML = html;

    // Remove week selector buttons - not needed without targets panel
    const weekSel = el('schedule-week-selector');
    if(weekSel) weekSel.innerHTML = '';

    updateKpis();
  }

  function showToast(msg, type){
    if(window.showToast) window.showToast(msg, type);
    else console.log(`[Schedule] ${type}: ${msg}`);
  }

  function updateKpis(){
    const sched = scheduleCache;
    if(!sched) return;
    const cwEl = el('schedule-current-week-kpi');
    const phaseEl = el('schedule-phase-kpi');
    const startEl = el('schedule-grow-start-kpi');
    const dayEl = el('schedule-grow-day-kpi');
    const week = sched.current_week || 1;
    const firstWeekNum = sched.weeks?.[0]?.week ?? null;
    const firstIsGermination = (sched.weeks?.[0]?.phase === 'germination');
    const displayWeek = (firstIsGermination && firstWeekNum !== 0) ? Math.max(0, week - 1) : week;
    const currentWeekRow = sched.weeks?.find(w=>w.week===week);
    
    // Add visual emphasis to active values
    if(cwEl){
      cwEl.textContent = displayWeek;
      cwEl.style.color = '#10b981';
      cwEl.style.textShadow = '0 0 8px rgba(16,185,129,0.4)';
    }
    if(phaseEl){
      const phase = currentWeekRow?.phase || '—';
      phaseEl.textContent = phase;
      phaseEl.style.textTransform = 'capitalize';
      if(phase !== '—'){
        const phaseColors = {seedling:'#93c5fd',veg:'#22c55e',preflower:'#fbbf24',flower:'#db70ef',flush:'#3b82f6'};
        phaseEl.style.color = phaseColors[phase] || '#e0e0e0';
      }
    }
    if(startEl){
      const dateStr = sched.grow_start_date ? new Date(sched.grow_start_date).toLocaleDateString() : '—';
      startEl.textContent = dateStr;
      startEl.style.fontWeight = dateStr !== '—' ? '600' : '400';
    }
    if(dayEl){
      const day = getDayN(sched.grow_start_date);
      dayEl.textContent = day ? day : '—';
      if(day){
        dayEl.style.color = '#10b981';
        dayEl.style.fontSize = '1.3rem';
        dayEl.style.fontWeight = '700';
      }
    }
  }

  async function init(){
    const data = await fetchSchedule();
    if(data){
      updateKpis();
      await renderTimeline();
    } else {
      // Still wire seed defaults button if present
      const seedBtn = el('scheduleSeedBtn');
      if(seedBtn && !seedBtn._wired){
        seedBtn._wired = true;
        seedBtn.addEventListener('click', async ()=>{
          seedBtn.disabled = true; await seedSchedule(); seedBtn.disabled=false; await fetchSchedule(); renderTimeline(); });
      }
    }
  }

  // Poll timeline every 60s while tab visible
  function startPoll(){
    if(pollTimer) return;
    pollTimer = setInterval(async ()=>{
      const tab = el('tab-schedule');
      if(tab && tab.style.display !== 'none'){
        await fetchSchedule();
        await renderTimeline();
      }
    }, 60000);
  }

  // Export API for other modules
  // Backwards-compatible global hooks used by tabs.js
  window.scheduleModule = {
    init,
    refresh: async ()=>{ await fetchSchedule(); await renderTimeline(); }
  };
  window.scheduleInit = window.scheduleModule.init;
  window.scheduleRefresh = window.scheduleModule.refresh;
  
  // Expose scheduleCache for week editor
  Object.defineProperty(window, 'scheduleCache', {
    get() { return scheduleCache; },
    set(v) { scheduleCache = v; }
  });

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', ()=>{init(); startPoll();});
  } else {
    init();
    startPoll();
  }
})();
