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
  }

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
  });

  // ===== SCHEDULE DISPLAY LOGIC =====

  let scheduleCache = null;
  let selectedWeek = null;
  let pollTimer = null;

  function el(id){ return document.getElementById(id); }

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
    const timeline = el('schedule-timeline');
    if(!timeline) return;

    const sched = scheduleCache;
    if(!sched || !sched.weeks || sched.weeks.length === 0){
      timeline.innerHTML = `
        <div style="padding:24px;text-align:center;color:#94a3b8;">
          <div style="font-size:1.1rem;margin-bottom:12px;">📅 No schedule configured</div>
          <button id="btnSeedSchedule" class="btn-secondary">Seed with EHG Defaults (12 weeks)</button>
        </div>
      `;
      el('btnSeedSchedule')?.addEventListener('click', async ()=>{
        el('btnSeedSchedule').disabled = true;
        await seedSchedule();
        el('btnSeedSchedule').disabled = false;
      });
      return;
    }

    const currentWeek = sched.current_week || 1;
    if(!selectedWeek) selectedWeek = currentWeek;

    // Group weeks by phase
    const phases = {veg: [], bloom: [], flush: []};
    sched.weeks.forEach(w => {
      if(w.phase && phases[w.phase]) phases[w.phase].push(w);
    });

    let html = '<div style="position:relative;overflow-x:auto;padding:12px 0;">';
    html += '<div style="display:flex;gap:4px;min-width:800px;">';

    // Render lanes
    Object.keys(phases).forEach(phase => {
      const weeks = phases[phase];
      if(weeks.length === 0) return;
      
      const colors = {
        veg: 'rgba(34,197,94,0.15)',
        bloom: 'rgba(251,191,36,0.15)',
        flush: 'rgba(148,163,184,0.15)'
      };
      const borderColors = {
        veg: 'rgba(34,197,94,0.4)',
        bloom: 'rgba(251,191,36,0.4)',
        flush: 'rgba(148,163,184,0.4)'
      };

      weeks.forEach(w => {
        const isCurrent = w.week === currentWeek;
        const isSelected = w.week === selectedWeek;
        const boxStyle = `
          flex: 0 0 auto;
          min-width: 100px;
          padding: 12px 8px;
          border: 2px solid ${isSelected ? borderColors[phase].replace('0.4','0.8') : borderColors[phase]};
          border-radius: 8px;
          background: ${colors[phase]};
          cursor: pointer;
          position: relative;
          transition: all 0.2s ease;
        `;
        
        html += `<div style="${boxStyle}" data-week="${w.week}" class="week-block">`;
        html += `<div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;margin-bottom:4px;">${phase}</div>`;
        html += `<div style="font-weight:600;font-size:0.9rem;">Week ${w.week}</div>`;
        html += `<div style="font-size:0.7rem;color:#cbd5e1;margin-top:2px;">EC ${w.ec_target}</div>`;
        
        if(isCurrent){
          html += `<div style="position:absolute;top:-8px;right:8px;background:#ef4444;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.65rem;font-weight:700;">WE ARE HERE</div>`;
          html += `<div style="position:absolute;bottom:-12px;left:50%;transform:translateX(-50%);width:2px;height:20px;background:#ef4444;"></div>`;
        }
        
        html += '</div>';
      });
    });

    html += '</div></div>';
    timeline.innerHTML = html;

    // Click handlers
    document.querySelectorAll('.week-block').forEach(block => {
      block.addEventListener('click', ()=>{
        const week = parseInt(block.getAttribute('data-week'));
        selectedWeek = week;
        renderTimeline();
        renderTargets(week);
      });
    });

    // Auto-render targets for selected week
    renderTargets(selectedWeek);
  }

  function renderTargets(weekNum){
    const card = el('schedule-targets');
    if(!card) return;

    const sched = scheduleCache;
    const week = sched?.weeks?.find(w => w.week === weekNum);
    
    if(!week){
      card.innerHTML = '<div class="muted" style="padding:12px;">Select a week from timeline</div>';
      return;
    }

    const html = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;">
        <div>
          <div style="font-size:0.75rem;color:#94a3b8;margin-bottom:4px;">Phase</div>
          <div style="font-size:1.1rem;font-weight:600;text-transform:capitalize;">${week.phase}</div>
        </div>
        <div>
          <div style="font-size:0.75rem;color:#94a3b8;margin-bottom:4px;">EC Target</div>
          <div style="font-size:1.1rem;font-weight:600;">${week.ec_target} mS/cm</div>
        </div>
        <div>
          <div style="font-size:0.75rem;color:#94a3b8;margin-bottom:4px;">pH Band</div>
          <div style="font-size:1.1rem;font-weight:600;">5.8 – 6.2</div>
        </div>
        <div>
          <div style="font-size:0.75rem;color:#94a3b8;margin-bottom:4px;">Lights</div>
          <div style="font-size:1.1rem;font-weight:600;">${week.lights}</div>
        </div>
      </div>
      <div style="margin-top:16px;padding-top:16px;border-top:1px solid rgba(148,163,184,0.1);">
        <div style="font-size:0.85rem;font-weight:600;margin-bottom:8px;">EHG 3-Part (ml per 10L)</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">
          <div style="padding:12px;border:1px solid rgba(148,163,184,0.2);border-radius:8px;background:rgba(34,197,94,0.05);">
            <div style="font-size:0.75rem;color:#94a3b8;">Grow</div>
            <div style="font-size:1.3rem;font-weight:700;color:#22c55e;">${week.grow_ml10}</div>
          </div>
          <div style="padding:12px;border:1px solid rgba(148,163,184,0.2);border-radius:8px;background:rgba(59,130,246,0.05);">
            <div style="font-size:0.75rem;color:#94a3b8;">Micro</div>
            <div style="font-size:1.3rem;font-weight:700;color:#3b82f6;">${week.micro_ml10}</div>
          </div>
          <div style="padding:12px;border:1px solid rgba(148,163,184,0.2);border-radius:8px;background:rgba(251,191,36,0.05);">
            <div style="font-size:0.75rem;color:#94a3b8;">Bloom</div>
            <div style="font-size:1.3rem;font-weight:700;color:#fbbf24;">${week.bloom_ml10}</div>
          </div>
        </div>
      </div>
      ${week.notes ? `<div style="margin-top:12px;padding:10px;border-radius:6px;background:rgba(59,130,246,0.08);font-size:0.85rem;color:#93c5fd;"><strong>Notes:</strong> ${week.notes}</div>` : ''}
    `;
    
    card.innerHTML = html;
  }

  async function renderPlan(){
    const planCard = el('schedule-plan');
    if(!planCard) return;

    const data = await fetchPlan(48);
    const items = data.plan || [];

    if(items.length === 0){
      planCard.innerHTML = '<div class="muted" style="padding:16px;text-align:center;font-size:0.9rem;">✅ Nothing planned in the next 48 hours</div>';
      return;
    }

    let html = '<div style="display:flex;flex-direction:column;gap:8px;">';
    items.forEach(item => {
      const ts = new Date(item.ts).toLocaleString();
      const reason = item.reason || 'unknown';
      const type = item.type || 'unknown';
      
      html += `<div style="padding:12px;border:1px solid rgba(148,163,184,0.2);border-radius:8px;background:rgba(59,130,246,0.05);">`;
      html += `<div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:6px;">`;
      html += `<div style="font-weight:600;font-size:0.9rem;">${ts}</div>`;
      html += `<span style="padding:2px 8px;border-radius:10px;background:rgba(59,130,246,0.2);font-size:0.7rem;font-weight:600;text-transform:uppercase;">${type}</span>`;
      html += `</div>`;
      
      if(type === 'ec_dose'){
        html += `<div style="font-size:0.85rem;color:#cbd5e1;">`;
        html += `<strong>${item.pump?.toUpperCase()}</strong> • ${item.seconds}s • `;
        html += `${item.from_ec?.toFixed(2)} → ${item.to_ec_est?.toFixed(2)} mS/cm`;
        html += `</div>`;
        html += `<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px;">Reason: ${reason}</div>`;
      }
      
      html += `</div>`;
    });
    html += '</div>';
    
    planCard.innerHTML = html;
  }

  async function renderStatus(){
    const statusCard = el('schedule-status');
    if(!statusCard) return;

    try{
      const settings = window.rdwcSettings?.getAll() || {};
      const minInterval = parseInt(settings['ec.min_interval_sec'] || '300');
      const waterOnly = (settings['safety.water_only'] || 'true').toLowerCase() === 'true';
      const ecMode = settings['ec.mode'] || 'off';

      let html = '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;">';
      
      if(waterOnly){
        html += `<span style="padding:6px 12px;border-radius:10px;background:rgba(251,191,36,0.2);border:1px solid rgba(251,191,36,0.4);font-size:0.8rem;font-weight:600;">💧 Water-Only Mode</span>`;
      }
      
      html += `<span style="padding:6px 12px;border-radius:10px;background:rgba(148,163,184,0.1);border:1px solid rgba(148,163,184,0.3);font-size:0.8rem;font-weight:600;">Automation: ${ecMode.toUpperCase()}</span>`;
      html += `<span style="padding:6px 12px;border-radius:10px;background:rgba(148,163,184,0.1);border:1px solid rgba(148,163,184,0.3);font-size:0.8rem;font-weight:600;">EC Interval: ${minInterval}s</span>`;
      
      html += '</div>';

      // Rapid Test Helper (hidden by default)
      html += `
        <div id="rapid-test-helper" style="display:none;margin-top:12px;padding:12px;border:1px solid rgba(251,191,36,0.3);border-radius:8px;background:rgba(251,191,36,0.05);">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div style="font-size:0.85rem;font-weight:600;">⚡ Rapid Test Mode</div>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
              <span style="font-size:0.75rem;color:#94a3b8;">Interval:</span>
              <select id="rapidIntervalSelect" style="padding:4px 8px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:0.8rem;">
                <option value="300" ${minInterval===300?'selected':''}>300s (Safe)</option>
                <option value="10" ${minInterval===10?'selected':''}>10s (Rapid Test)</option>
              </select>
            </label>
          </div>
          <div style="font-size:0.7rem;color:#94a3b8;margin-top:6px;">Use 10s interval for quick UI testing; restore to 300s after tests.</div>
        </div>
      `;

      statusCard.innerHTML = html;

      // Rapid Test toggle logic
      const rapidSelect = el('rapidIntervalSelect');
      rapidSelect?.addEventListener('change', async ()=>{
        const val = parseInt(rapidSelect.value);
        try{
          const r = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({'ec.min_interval_sec': val})});
          if(r.ok){
            showToast(`Interval set to ${val}s`, 'success');
            // Re-read settings
            if(window.rdwcSettings?.reload) await window.rdwcSettings.reload();
            await renderStatus();
          } else {
            showToast('Failed to update interval', 'error');
          }
        }catch(e){
          showToast('Interval error: '+e.message, 'error');
        }
      });
    }catch(e){
      statusCard.innerHTML = '<div class="muted">Status unavailable</div>';
    }
  }

  function showToast(msg, type){
    if(window.showToast) window.showToast(msg, type);
    else console.log(`[Schedule] ${type}: ${msg}`);
  }

  async function init(){
    const data = await fetchSchedule();
    if(data){
      await renderTimeline();
      await renderPlan();
      await renderStatus();
    }
  }

  // Poll plan every 60s while tab visible
  function startPoll(){
    if(pollTimer) return;
    pollTimer = setInterval(async ()=>{
      const tab = el('tab-schedule');
      if(tab && tab.style.display !== 'none'){
        await renderPlan();
        await renderStatus();
      }
    }, 60000);
  }

  // Export API for other modules
  // Backwards-compatible global hooks used by tabs.js
  window.scheduleModule = {
    init,
    refresh: async ()=>{ await fetchSchedule(); await renderTimeline(); await renderPlan(); await renderStatus(); },
    showRapidHelper: ()=>{ const h = el('rapid-test-helper'); if(h) h.style.display = 'block'; },
    hideRapidHelper: ()=>{ const h = el('rapid-test-helper'); if(h) h.style.display = 'none'; }
  };
  window.scheduleInit = window.scheduleModule.init;
  window.scheduleRefresh = window.scheduleModule.refresh;

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', ()=>{init(); startPoll();});
  } else {
    init();
    startPoll();
  }
})();
