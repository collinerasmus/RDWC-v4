/**
 * Schedule Week Editor - Edit schedule weeks directly
 * Allows users to add/delete/modify week parameters and persist via API
 */
(function() {
  'use strict';

  let scheduleData = {};
  let selectedWeekIndex = null;

  function init() {
    const weekSelect = document.getElementById('weekSelect');
    const btnUpdateWeek = document.getElementById('btnUpdateWeek');
    const btnDeleteWeek = document.getElementById('btnDeleteWeek');

    if (!weekSelect || !btnUpdateWeek || !btnDeleteWeek) return;

    // Load schedule on init
    loadSchedule();

    // Event listeners
    weekSelect.addEventListener('change', onWeekSelected);
    btnUpdateWeek.addEventListener('click', updateSelectedWeek);
    btnDeleteWeek.addEventListener('click', deleteSelectedWeek);
  }

  async function loadSchedule() {
    try {
      const res = await fetch('/api/scheduler/config');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      scheduleData = await res.json();
      populateWeekSelector();
    } catch (e) {
      console.error('[Schedule Week Editor] Failed to load schedule:', e);
    }
  }

  function populateWeekSelector() {
    const select = document.getElementById('weekSelect');
    select.innerHTML = '<option value="">Select a week...</option>';

    if (!scheduleData.weeks || !Array.isArray(scheduleData.weeks)) {
      return;
    }

    scheduleData.weeks.forEach((week, idx) => {
      const label = `W${idx + 1}: ${week.stage || 'N/A'} (EC: ${week.ec?.toFixed(1) || '?'})`;
      const option = document.createElement('option');
      option.value = idx;
      option.textContent = label;
      select.appendChild(option);
    });
  }

  function onWeekSelected() {
    const select = document.getElementById('weekSelect');
    selectedWeekIndex = parseInt(select.value, 10);

    if (isNaN(selectedWeekIndex)) {
      clearWeekForm();
      return;
    }

    const week = scheduleData.weeks[selectedWeekIndex];
    if (!week) return;

    // Populate form fields
    document.getElementById('stageSelect').value = week.stage || 'seedling';
    document.getElementById('lightCycleInput').value = week.light_cycle || '18/6';
    document.getElementById('phInput').value = week.ph ?? '';
    document.getElementById('ecInput').value = week.ec ?? '';
    document.getElementById('tempInput').value = week.temp ?? '';
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
      alert('Please select a week first');
      return;
    }

    const week = scheduleData.weeks[selectedWeekIndex];
    if (!week) return;

    // Update week object from form
    week.stage = document.getElementById('stageSelect').value;
    week.light_cycle = document.getElementById('lightCycleInput').value;
    week.ph = parseFloat(document.getElementById('phInput').value) || null;
    week.ec = parseFloat(document.getElementById('ecInput').value) || null;
    week.temp = parseFloat(document.getElementById('tempInput').value) || null;

    // Save to API
    await saveSchedule();
  }

  async function deleteSelectedWeek() {
    if (selectedWeekIndex === null) {
      alert('Please select a week first');
      return;
    }

    if (!confirm(`Delete W${selectedWeekIndex + 1}? This cannot be undone.`)) {
      return;
    }

    scheduleData.weeks.splice(selectedWeekIndex, 1);
    selectedWeekIndex = null;
    clearWeekForm();

    // Save to API
    await saveSchedule();
  }

  async function saveSchedule() {
    try {
      const res = await fetch('/api/scheduler/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scheduleData)
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Refresh UI
      populateWeekSelector();
      clearWeekForm();
      
      // Show success feedback
      showFeedback('Schedule updated successfully', 'success');
    } catch (e) {
      console.error('[Schedule Week Editor] Save failed:', e);
      showFeedback(`Save failed: ${e.message}`, 'error');
    }
  }

  function showFeedback(msg, type) {
    // Find or create feedback element
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
  else document.addEventListener('DOMContentLoaded', () => setTimeout(init, 200));
})();
