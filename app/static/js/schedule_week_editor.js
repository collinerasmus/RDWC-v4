/**
 * Schedule Week Editor - Click tiles to edit inline
 * Makes week tiles clickable and editable
 */
(function() {
  'use strict';

  let editingWeekIndex = null;

  function init() {
    // Use event delegation on timeline container
    const timeline = document.getElementById('schedule-timeline-lanes');
    if (!timeline) {
      console.log('[Week Editor] Timeline container not found');
      return;
    }

    console.log('[Week Editor] Initialized, listening on timeline');
    
    timeline.addEventListener('click', (e) => {
      console.log('[Week Editor] Click detected on:', e.target, 'closest tile:', e.target.closest('[data-week]'));
      
      // Find the closest week-block tile
      const tile = e.target.closest('[data-week]');
      if (!tile) {
        console.log('[Week Editor] No tile found in click path');
        return;
      }
      
      if (editingWeekIndex !== null) {
        console.log('[Week Editor] Already editing week', editingWeekIndex);
        return;
      }

      const weekNum = parseInt(tile.getAttribute('data-week'), 10);
      console.log('[Week Editor] Opening tile for week', weekNum);
      onTileClick(weekNum);
    });
  }

  function onTileClick(weekNum) {
    const sched = window.scheduleCache || {};
    console.log('[Week Editor] scheduleCache content:', sched);
    console.log('[Week Editor] weeks array:', sched.weeks);
    
    if (!sched.weeks) {
      console.log('[Week Editor] No weeks array in cache');
      return;
    }

    // Find week by week.week property
    const idx = sched.weeks.findIndex(w => w.week === weekNum);
    console.log('[Week Editor] Looking for weekNum', weekNum, 'found idx:', idx);
    
    if (idx === -1) {
      console.log('[Week Editor] Week not found in array');
      return;
    }

    editingWeekIndex = idx;
    const week = sched.weeks[idx];
    console.log('[Week Editor] Opening week at index', idx, ':', week);

    // Create modal overlay
    const modal = document.createElement('div');
    modal.id = 'week-editor-modal';
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0,0,0,0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10000;
    `;

    const form = document.createElement('div');
    form.style.cssText = `
      background: #0f172a;
      border: 1px solid #374151;
      border-radius: 12px;
      padding: 24px;
      max-width: 400px;
      width: 90%;
      box-shadow: 0 20px 60px rgba(0,0,0,0.8);
    `;

    form.innerHTML = `
      <div style="font-weight:600;font-size:18px;margin-bottom:20px;color:#e0e0e0;">Edit W${weekNum}</div>
      <div style="display:grid;gap:16px;margin-bottom:20px;">
        <div>
          <label style="display:block;font-size:12px;color:#9ca3af;margin-bottom:6px;">Stage</label>
          <select id="modalStage" style="width:100%;height:36px;padding:0 10px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:14px;">
            <option value="seedling">Seedling</option>
            <option value="veg">Veg</option>
            <option value="preflower">Preflower</option>
            <option value="flower">Flower</option>
            <option value="flush">Flush</option>
          </select>
        </div>
        <div>
          <label style="display:block;font-size:12px;color:#9ca3af;margin-bottom:6px;">Light Cycle</label>
          <input type="text" id="modalLights" placeholder="18/6" style="width:100%;height:36px;padding:0 10px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:14px;" />
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <label style="display:block;font-size:12px;color:#9ca3af;margin-bottom:6px;">pH</label>
            <input type="number" id="modalPh" placeholder="6.0" min="4" max="8" step="0.1" style="width:100%;height:36px;padding:0 10px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:14px;" />
          </div>
          <div>
            <label style="display:block;font-size:12px;color:#9ca3af;margin-bottom:6px;">EC</label>
            <input type="number" id="modalEc" placeholder="1.0" min="0" max="3" step="0.1" style="width:100%;height:36px;padding:0 10px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:14px;" />
          </div>
        </div>
        <div>
          <label style="display:block;font-size:12px;color:#9ca3af;margin-bottom:6px;">Temp (°C)</label>
          <input type="number" id="modalTemp" placeholder="20" min="10" max="30" step="0.5" style="width:100%;height:36px;padding:0 10px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:14px;" />
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
        <button id="modalSave" class="btn-secondary" style="padding:10px 16px;">💾 Save</button>
        <button id="modalCancel" class="btn-secondary" style="padding:10px 16px;background:rgba(148,163,184,0.15);border-color:rgba(148,163,184,0.3);">Cancel</button>
      </div>
      <button id="modalDelete" class="btn-secondary" style="width:100%;padding:10px 16px;background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.3);color:#fecaca;">🗑️ Delete Week</button>
      <div id="modalStatus" style="margin-top:12px;font-size:12px;text-align:center;color:#9ca3af;"></div>
    `;

    modal.appendChild(form);
    document.body.appendChild(modal);

    // Populate with current values
    document.getElementById('modalStage').value = week.phase || 'seedling';
    document.getElementById('modalLights').value = week.lights || '18/6';
    document.getElementById('modalPh').value = week.ph ?? '';
    document.getElementById('modalEc').value = week.ec ?? '';
    document.getElementById('modalTemp').value = week.temp ?? '';

    // Attach handlers
    document.getElementById('modalSave').addEventListener('click', () => saveWeek(idx, weekNum, modal));
    document.getElementById('modalCancel').addEventListener('click', () => closeModal(modal));
    document.getElementById('modalDelete').addEventListener('click', () => deleteWeek(idx, weekNum, modal));
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal(modal);
    });
  }

  async function saveWeek(idx, weekNum, modal) {
    const sched = window.scheduleCache || {};
    if (!sched.weeks || !sched.weeks[idx]) return;

    const week = sched.weeks[idx];
    week.phase = document.getElementById('modalStage').value;
    week.lights = document.getElementById('modalLights').value;
    week.ph = parseFloat(document.getElementById('modalPh').value) || null;
    week.ec = parseFloat(document.getElementById('modalEc').value) || null;
    week.temp = parseFloat(document.getElementById('modalTemp').value) || null;

    try {
      const res = await fetch('/api/nutrient_schedule', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sched)
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Refresh timeline
      if (window.renderTimeline) window.renderTimeline();
      if (window.updateKpis) window.updateKpis();

      showStatus(modal, 'Saved ✓', 'success');
      setTimeout(() => closeModal(modal), 800);
    } catch (e) {
      console.error('[Week Editor] Save failed:', e);
      showStatus(modal, 'Save failed', 'error');
    }
  }

  async function deleteWeek(idx, weekNum, modal) {
    const sched = window.scheduleCache || {};
    if (!sched.weeks || !sched.weeks[idx]) return;

    if (!confirm(`Delete W${weekNum}?`)) return;

    sched.weeks.splice(idx, 1);

    try {
      const res = await fetch('/api/nutrient_schedule', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sched)
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      if (window.renderTimeline) window.renderTimeline();
      if (window.updateKpis) window.updateKpis();

      closeModal(modal);
    } catch (e) {
      console.error('[Week Editor] Delete failed:', e);
      showStatus(modal, 'Delete failed', 'error');
    }
  }

  function showStatus(modal, msg, type) {
    const status = modal.querySelector('#modalStatus');
    if (status) {
      status.textContent = msg;
      status.style.color = type === 'success' ? '#86efac' : '#fecaca';
    }
  }

  function closeModal(modal) {
    editingWeekIndex = null;
    modal.remove();
  }

  // Wait for DOM ready and then attach listener
  function waitAndInit() {
    const timeline = document.getElementById('schedule-timeline-lanes');
    if (!timeline) {
      console.log('[Week Editor] Timeline not found yet, retrying...');
      setTimeout(waitAndInit, 500);
      return;
    }
    init();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(waitAndInit, 100));
  } else {
    setTimeout(waitAndInit, 100);
  }
})();
