/**
 * Schedule Week Editor - Edit schedule weeks directly
 * Reuses scheduleCache from schedule.js (single source of truth)
 * No duplicate API calls or data
 */
(function() {
  'use strict';

  let selectedWeekIndex = null;

  function init() {
    const weekSelect = document.getElementById('weekSelect');
    const btnUpdateWeek = document.getElementById('btnUpdateWeek');
    const btnDeleteWeek = document.getElementById('btnDeleteWeek');

    if (!weekSelect || !btnUpdateWeek || !btnDeleteWeek) return;

    // Initial population from existing schedule.js cache
    setTimeout(() => {
      populateWeekSelector();
      attachEventListeners();
    }, 300);
  }

  function populateWeekSelector() {
    const select = document.getElementById('weekSelect');
    if (!select) return;

    select.innerHTML = '<option value="">Select a week...</option>';

    // Use global scheduleCache from schedule.js (single source of truth)
    const sched = window.scheduleCache || {};
    if (!sched.weeks || !Array.isArray(sched.weeks) || sched.weeks.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'No schedule loaded';
      opt.disabled = true;
      select.appendChild(opt);
      return;
    }

    sched.weeks.forEach((week, idx) => {
      const label = `W${week.week || idx + 1}: ${week.phase || 'N/A'} (EC: ${week.ec?.toFixed(1) || '?'})`;
      const option = document.createElement('option');
      option.value = idx;
      option.textContent = label;
      select.appendChild(option);
    });
  }

  function attachEventListeners() {
    const weekSelect = document.getElementById('weekSelect');
    const btnUpdateWeek = document.getElementById('btnUpdateWeek');
    const btnDeleteWeek = document.getElementById('btnDeleteWeek');

    if (!weekSelect || !btnUpdateWeek || !btnDeleteWeek) return;

    weekSelect.addEventListener('change', onWeekSelected);
    btnUpdateWeek.addEventListener('click', updateSelectedWeek);
    btnDeleteWeek.addEventListener('click', deleteSelectedWeek);
  }

  function onWeekSelected() {
    const select = document.getElementById('weekSelect');
    selectedWeekIndex = parseInt(select.value, 10);

    if (isNaN(selectedWeekIndex)) {
      clearWeekForm();
      return;
    }

    const sched = window.scheduleCache || {};
    if (!sched.weeks || !sched.weeks[selectedWeekIndex]) {
      clearWeekForm();
      return;
    }

    const week = sched.weeks[selectedWeekIndex];

    // Populate form fields from week data
    document.getElementById('stageSelect').value = week.phase || week.stage || 'seedling';
    document.getElementById('lightCycleInput').value = week.lights || week.light_cycle || '18/6';
    document.getElementById('phInput').value = week.ph ?? '';
    document.getElementById('ecInput').value = week.ec ?? '';
    document.getElementById('tempInput').value = week.temp || '';
  }

  function clearWeekForm() {
    selectedWeekIndex = null;
    document.getElementById('stageSelect').value = 'seedling';
    document.getElementById('lightCycleInput').value = '';
    document.getElementById('phInput').value = '';
    document.getElementById('ecInput').value = '';
    document.getElementById('tempInput').value = '';
  }

  async function updateSelectedWeek() {
    if (selectedWeekIndex === null) {
      showFeedback('Please select a week first', 'error');
      return;
    }

    const sched = window.scheduleCache || {};
    if (!sched.weeks || !sched.weeks[selectedWeekIndex]) {
      showFeedback('Week not found', 'error');
      return;
    }

    const week = sched.weeks[selectedWeekIndex];

    // Update week object from form
    week.phase = document.getElementById('stageSelect').value;
    week.lights = document.getElementById('lightCycleInput').value;
    week.ph = parseFloat(document.getElementById('phInput').value) || null;
    week.ec = parseFloat(document.getElementById('ecInput').value) || null;
    week.temp = parseFloat(document.getElementById('tempInput').value) || null;

    // Save to API
    await saveSchedule();
  }

  async function deleteSelectedWeek() {
    if (selectedWeekIndex === null) {
      showFeedback('Please select a week first', 'error');
      return;
    }

    const sched = window.scheduleCache || {};
    if (!sched.weeks || !sched.weeks[selectedWeekIndex]) {
      showFeedback('Week not found', 'error');
      return;
    }

    const weekNum = sched.weeks[selectedWeekIndex].week || selectedWeekIndex + 1;
    if (!confirm(`Delete W${weekNum}? This cannot be undone.`)) {
      return;
    }

    sched.weeks.splice(selectedWeekIndex, 1);
    selectedWeekIndex = null;
    clearWeekForm();

    // Save to API
    await saveSchedule();
  }

  async function saveSchedule() {
    try {
      const sched = window.scheduleCache || {};

      const res = await fetch('/api/nutrient_schedule', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sched)
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Refresh UI
      populateWeekSelector();
      clearWeekForm();
      
      // Trigger schedule.js timeline refresh if available
      if (window.renderTimeline) {
        window.renderTimeline();
      }
      if (window.updateKpis) {
        window.updateKpis();
      }
      
      showFeedback('Schedule updated successfully', 'success');
    } catch (e) {
      console.error('[Schedule Week Editor] Save failed:', e);
      showFeedback(`Save failed: ${e.message}`, 'error');
    }
  }

  function showFeedback(msg, type) {
    let feedback = document.getElementById('scheduleWeekEditorFeedback');
    if (!feedback) {
      feedback = document.createElement('div');
      feedback.id = 'scheduleWeekEditorFeedback';
      const container = document.getElementById('week-editor-container');
      if (container) {
        container.appendChild(feedback);
      } else {
        return;
      }
    }

    feedback.style.cssText = `
      padding: 8px 12px;
      border-radius: 6px;
      font-size: var(--font-xs);
      margin-top: 8px;
      ${type === 'success' 
        ? 'background: rgba(16,185,129,0.2); border: 1px solid rgba(16,185,129,0.4); color: #86efac;'
        : 'background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.4); color: #fecaca;'
      }
    `;
    feedback.textContent = msg;
    feedback.style.display = 'block';

    setTimeout(() => {
      feedback.style.display = 'none';
    }, 4000);
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', () => setTimeout(init, 300));
})();
