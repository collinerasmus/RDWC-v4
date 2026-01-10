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

    // Add week button
    const addBtn = document.getElementById('schedule-add-week-btn');
    if (addBtn) {
      addBtn.addEventListener('click', addWeekFromLast);
    }
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
            <option value="germination">Germination</option>
            <option value="seedling">Seedling</option>
            <option value="veg">Veg</option>
            <option value="preflower">Preflower</option>
            <option value="flower">Flower</option>
            <option value="flush">Flush</option>
          </select>
          <div id="germinationWarning" style="font-size:11px;color:#fbbf24;margin-top:4px;display:none;">⚠️ Germination can only be Week 0</div>
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
        <div style="border-top:1px solid #374151;padding-top:16px;margin-top:8px;">
          <label style="display:block;font-size:12px;color:#9ca3af;margin-bottom:12px;font-weight:600;">Nutrient Ratios (ml/10L)</label>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">
            <div>
              <label style="display:block;font-size:11px;color:#a0aec0;margin-bottom:4px;">Grow</label>
              <input type="number" id="modalGrow" placeholder="0" min="0" max="50" step="0.5" style="width:100%;height:36px;padding:0 10px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:14px;" />
            </div>
            <div>
              <label style="display:block;font-size:11px;color:#a0aec0;margin-bottom:4px;">Micro</label>
              <input type="number" id="modalMicro" placeholder="0" min="0" max="50" step="0.5" style="width:100%;height:36px;padding:0 10px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:14px;" />
            </div>
            <div>
              <label style="display:block;font-size:11px;color:#a0aec0;margin-bottom:4px;">Bloom</label>
              <input type="number" id="modalBloom" placeholder="0" min="0" max="50" step="0.5" style="width:100%;height:36px;padding:0 10px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:14px;" />
            </div>
          </div>
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
    document.getElementById('modalPh').value = week.ph_low ?? '';
    document.getElementById('modalEc').value = week.ec_target ?? '';
    document.getElementById('modalTemp').value = week.temp_target ?? '';
    document.getElementById('modalGrow').value = week.grow_ml10 ?? '';
    document.getElementById('modalMicro').value = week.micro_ml10 ?? '';
    document.getElementById('modalBloom').value = week.bloom_ml10 ?? '';

    // Add event listener to phase dropdown for germination validation
    const stageSelect = document.getElementById('modalStage');
    const warningDiv = document.getElementById('germinationWarning');
    if (stageSelect && warningDiv) {
      stageSelect.addEventListener('change', () => {
        if (stageSelect.value === 'germination' && idx !== 0) {
          warningDiv.style.display = 'block';
          stageSelect.value = week.phase || 'seedling';
        } else {
          warningDiv.style.display = 'none';
        }
      });
      // Disable germination option if not week 0
      const germinationOption = Array.from(stageSelect.options).find(opt => opt.value === 'germination');
      if (germinationOption && idx !== 0) {
        germinationOption.disabled = true;
      }
    }

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

    // Normalize inputs (handle comma decimals, preserve existing on blank)
    const parseNumber = (val, fallback) => {
      if (val === undefined || val === null) return fallback;
      const cleaned = String(val).replace(',', '.').trim();
      if (cleaned === '') return fallback;
      const n = Number.parseFloat(cleaned);
      return Number.isFinite(n) ? n : fallback;
    };

    const phInput = document.getElementById('modalPh').value;
    const ecInput = document.getElementById('modalEc').value;
    const tempInput = document.getElementById('modalTemp').value;
    const growInput = document.getElementById('modalGrow').value;
    const microInput = document.getElementById('modalMicro').value;
    const bloomInput = document.getElementById('modalBloom').value;

    const updates = {
      phase: document.getElementById('modalStage').value,
      lights: document.getElementById('modalLights').value,
      ph_low: parseNumber(phInput, week.ph_low ?? 5.8),
      ph_high: parseNumber(phInput, week.ph_high ?? 6.2),
      ec_target: parseNumber(ecInput, week.ec_target ?? null),
      temp_target: parseNumber(tempInput, week.temp_target ?? null),
      grow_ml10: parseNumber(growInput, week.grow_ml10 ?? null),
      micro_ml10: parseNumber(microInput, week.micro_ml10 ?? null),
      bloom_ml10: parseNumber(bloomInput, week.bloom_ml10 ?? null)
    };

    console.log('[Week Editor] Sending updates for week', weekNum, updates);

    try {
      const res = await fetch(`/api/nutrient_schedule/week/${weekNum}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      });

      const result = await res.json().catch(() => ({}));
      console.log('[Week Editor] API response:', result);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${result.error || 'unknown'}`);

      // Update local cache so UI reflects immediately
      week.phase = updates.phase;
      week.lights = updates.lights;
      week.ph_low = updates.ph_low;
      week.ph_high = updates.ph_high;
      week.ec_target = updates.ec_target;
      week.temp_target = updates.temp_target;
      week.grow_ml10 = updates.grow_ml10;
      week.micro_ml10 = updates.micro_ml10;
      week.bloom_ml10 = updates.bloom_ml10;

      // Re-render from cache
      if (window.renderTimeline) window.renderTimeline();
      if (window.updateKpis) window.updateKpis();

      // Pull fresh from backend to avoid duplication/staleness
      if (window.scheduleRefresh) {
        try { await window.scheduleRefresh(); } catch (_) {}
      }

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

    if (!confirm(`Delete W${weekNum}? This cannot be undone.`)) return;

    try {
      const res = await fetch(`/api/nutrient_schedule/week/${weekNum}`, { method: 'DELETE' });
      const result = await res.json().catch(() => ({}));
      console.log('[Week Editor] Delete response:', result);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${result.error || 'unknown'}`);

      // Remove locally
      sched.weeks.splice(idx, 1);

      if (window.renderTimeline) window.renderTimeline();
      if (window.updateKpis) window.updateKpis();
      if (window.scheduleRefresh) {
        try { await window.scheduleRefresh(); } catch (_) {}
      }

      closeModal(modal);
    } catch (e) {
      console.error('[Week Editor] Delete failed:', e);
      showStatus(modal, 'Delete failed', 'error');
    }
  }

  async function addWeekFromLast() {
    const sched = window.scheduleCache || {};
    const weeks = sched.weeks || [];
    if (!weeks.length) return;

    const last = weeks[weeks.length - 1];
    const newWeekNum = (last.week || weeks.length) + 1;

    const payload = {
      week: newWeekNum,
      phase: last.phase || 'veg',
      grow_ml10: last.grow_ml10 ?? 0,
      micro_ml10: last.micro_ml10 ?? 0,
      bloom_ml10: last.bloom_ml10 ?? 0,
      ec_target: last.ec_target ?? 1.0,
      ph_low: last.ph_low ?? 5.8,
      ph_high: last.ph_high ?? 6.2,
      temp_target: last.temp_target ?? 20.0,
      lights: last.lights || '18/6',
      notes: last.notes || ''
    };

    console.log('[Week Editor] Adding week', newWeekNum, payload);

    try {
      const res = await fetch('/api/nutrient_schedule/week', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const result = await res.json().catch(() => ({}));
      console.log('[Week Editor] Add response:', result);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${result.error || 'unknown'}`);

      // Push locally to show immediately
      weeks.push({ ...payload });
      if (window.renderTimeline) window.renderTimeline();
      if (window.updateKpis) window.updateKpis();
      if (window.scheduleRefresh) {
        try { await window.scheduleRefresh(); } catch (_) {}
      }
    } catch (e) {
      console.error('[Week Editor] Add week failed:', e);
      if (window.showToast) window.showToast('Add week failed', 'error');
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
