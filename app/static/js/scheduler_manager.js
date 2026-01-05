/**
 * Scheduler Manager - Advanced scheduler UI with CRUD operations
 * Allows editing schedule entries, daily caps, and persisting changes
 */
(function() {
  'use strict';

  let currentConfig = {};

  // Initialize scheduler manager
  function init() {
    loadSchedulerConfig();
    attachEventListeners();
  }

  // Load current scheduler configuration
  async function loadSchedulerConfig() {
    try {
      const res = await fetch('/api/scheduler/config');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      currentConfig = await res.json();
      renderUI();
    } catch (e) {
      console.error('[SchedulerManager] Failed to load config:', e);
      showStatus('Failed to load scheduler config', 'error');
    }
  }

  // Render the scheduler UI
  function renderUI() {
    // Enable toggle
    const enabledCheckbox = document.getElementById('schedulerEnabled');
    if (enabledCheckbox) {
      enabledCheckbox.checked = currentConfig.enabled || false;
    }

    // Render entries
    renderEntries();

    // Render daily caps
    renderDailyCaps();
  }

  // Render schedule entries list
  function renderEntries() {
    const list = document.getElementById('schedulerEntriesList');
    if (!list) return;

    const entries = currentConfig.entries || [];
    if (!entries.length) {
      list.innerHTML = '<div style="color:#6b7280;padding:8px;">No entries configured</div>';
      return;
    }

    list.innerHTML = entries.map((entry, idx) => `
      <div style="padding:8px;border:1px solid #374151;border-radius:4px;margin-bottom:6px;background:rgba(0,0,0,0.1);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <div style="font-weight:600;color:#e0e0e0;">
            ${entry.name} <span style="color:#9ca3af;">[${entry.kind}]</span>
          </div>
          <button class="btn-delete-entry" data-index="${idx}" style="padding:2px 8px;font-size:var(--font-xs);background:#ef4444;border:none;border-radius:3px;color:white;cursor:pointer;">Delete</button>
        </div>
        <div style="color:#9ca3af;font-size:var(--font-xs);line-height:1.4;">
          Time: <strong>${entry.at || entry.on_at || '—'}</strong> |
          ${entry.duration_sec ? `Duration: <strong>${entry.duration_sec}s</strong> | ` : ''}
          Days: <strong>${(entry.days || []).length > 0 ? entry.days.join(',') : '—'}</strong>
        </div>
      </div>
    `).join('');

    // Attach delete handlers
    list.querySelectorAll('.btn-delete-entry').forEach(btn => {
      btn.addEventListener('click', () => deleteEntry(parseInt(btn.dataset.index)));
    });
  }

  // Render daily caps editor
  function renderDailyCaps() {
    const list = document.getElementById('schedulerCapsList');
    if (!list) return;

    const caps = currentConfig.daily_caps || {};
    if (!Object.keys(caps).length) {
      list.innerHTML = '<div style="color:#6b7280;">No caps configured</div>';
      return;
    }

    list.innerHTML = Object.entries(caps).map(([relay, cap]) => `
      <div style="display:flex;align-items:center;gap:6px;">
        <label style="min-width:80px;color:#9ca3af;">${relay}:</label>
        <input type="number" class="cap-input" data-relay="${relay}" value="${cap}" style="width:80px;height:28px;padding:0 6px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:4px;font-size:var(--font-xs);" />
        <span style="font-size:var(--font-xs);color:#6b7280;">s/day</span>
      </div>
    `).join('');

    // Auto-update config when caps change
    list.querySelectorAll('.cap-input').forEach(input => {
      input.addEventListener('change', () => {
        const relay = input.dataset.relay;
        currentConfig.daily_caps[relay] = parseInt(input.value) || 0;
      });
    });
  }

  // Delete entry
  function deleteEntry(index) {
    if (!confirm('Delete this schedule entry?')) return;
    currentConfig.entries.splice(index, 1);
    renderEntries();
  }

  // Add new entry
  function addEntry() {
    const name = document.getElementById('entryName')?.value?.trim();
    const kind = document.getElementById('entryKind')?.value || 'pulse';
    const time = document.getElementById('entryTime')?.value;
    const duration = parseInt(document.getElementById('entryDuration')?.value || 0);

    if (!name || !time) {
      showStatus('Name and Time are required', 'error');
      return;
    }

    const entry = {
      name,
      kind,
      days: [0, 1, 2, 3, 4, 5, 6] // All days by default
    };

    if (kind === 'pulse') {
      entry.at = time;
      entry.duration_sec = duration;
    } else {
      entry.on_at = time;
      entry.off_at = time; // User can edit later via API if needed
    }

    currentConfig.entries.push(entry);
    
    // Clear form
    document.getElementById('entryName').value = '';
    document.getElementById('entryTime').value = '';
    document.getElementById('entryDuration').value = '';

    renderEntries();
    showStatus('Entry added (unsaved)', 'info');
  }

  // Save configuration
  async function saveScheduler() {
    const saveBtn = document.getElementById('btnSaveScheduler');
    if (saveBtn) saveBtn.disabled = true;

    try {
      // Update enabled status
      currentConfig.enabled = document.getElementById('schedulerEnabled')?.checked || false;

      const res = await fetch('/api/scheduler/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentConfig)
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || `HTTP ${res.status}`);
      }

      const result = await res.json();
      console.log('[SchedulerManager] Saved successfully:', result);
      showStatus('✅ Scheduler saved successfully (changes persist on restart)', 'success');
      
    } catch (e) {
      console.error('[SchedulerManager] Save error:', e);
      showStatus(`❌ Save failed: ${e.message}`, 'error');
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  // Show status message
  function showStatus(msg, type) {
    const statusDiv = document.getElementById('schedulerSaveStatus');
    if (!statusDiv) return;

    const colors = {
      'success': '#10b981',
      'error': '#ef4444',
      'info': '#3b82f6'
    };

    statusDiv.textContent = msg;
    statusDiv.style.color = colors[type] || '#9ca3af';
    statusDiv.style.display = 'block';

    if (type === 'success' || type === 'error') {
      setTimeout(() => {
        statusDiv.style.display = 'none';
      }, 5000);
    }
  }

  // Attach event listeners
  function attachEventListeners() {
    const addBtn = document.getElementById('btnAddEntry');
    if (addBtn) addBtn.addEventListener('click', addEntry);

    const saveBtn = document.getElementById('btnSaveScheduler');
    if (saveBtn) saveBtn.addEventListener('click', saveScheduler);

    const enabledCheckbox = document.getElementById('schedulerEnabled');
    if (enabledCheckbox) {
      enabledCheckbox.addEventListener('change', () => {
        currentConfig.enabled = enabledCheckbox.checked;
        showStatus(enabledCheckbox.checked ? 'Scheduler enabled' : 'Scheduler disabled', 'info');
      });
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 100);
  }

  // Expose for external use
  window.schedulerManager = {
    reload: loadSchedulerConfig,
    save: saveScheduler
  };

})();
