(function(){
  const q = (s, r=document) => r.querySelector(s);
  const qa = (s, r=document) => Array.from(r.querySelectorAll(s));

  const GROUP_DEF = {
    general: {
      title: 'General',
      fields: {
        'general.grow_name': {label:'Grow name', type:'text'},
        'general.timezone': {label:'Timezone', type:'text', placeholder:'Africa/Johannesburg'},
        'general.reservoir_liters': {label:'Reservoir (L)', type:'number', min:1, max:1000, step:0.1},
        'general.grow_start_date': {label:'Grow start date', type:'date', tooltip:'Used for \'Grow\' quick range and Day N'}
      }
    },
    safety: {
      title: 'Safety',
      fields: {
        'safety.estop_persist': {label:'E‑STOP persists across reboot', type:'checkbox'},
        'safety.allow_force': {label:'Allow Force (test)', type:'checkbox', tooltip:'Temporarily allow bypassing cooldown and daily cap for testing only'},
        'safety.maintenance_override': {label:'Maintenance override (test only)', type:'checkbox', tooltip:'Bypasses cooldown/daily cap; clamps single dose; E-STOP/empty reservoir still enforced'},
        'safety.allow_stale_on_override': {label:'Allow stale sensors on override', type:'checkbox', tooltip:'Allows dosing when sensors are stale (TEST ONLY). Off by default.', badge:'TEST'},
        'safety.max_seconds_per_press': {label:'Max seconds per dose press', type:'number', min:0.1, max:10, step:0.1, tooltip:'Hard cap on single manual dose (even with maintenance override)'},
        'safety.max_total_seconds_per_24h': {label:'Max total seconds per 24h (per pump)', type:'number', min:0, max:600, step:1, tooltip:'Daily cap per pump; resets midnight UTC'},
        'safety.min_off_window_sec': {label:'Min off between doses (s)', type:'number', min:0, max:60, step:0.5, tooltip:'Enforces minimum time between pump actuations'},
        'safety.main_pump_min_off_s': {label:'Main pump min off (s)', type:'number', min:0, max:300, step:1, tooltip:'Minimum off time for main circulation pump'},
        'safety.chiller_pump_min_off_s': {label:'Chiller pump min off (s)', type:'number', min:0, max:300, step:1, tooltip:'Minimum off time for chiller pump'},
        'safety.chiller_min_off_s': {label:'Chiller min off (s)', type:'number', min:60, max:3600, step:10, tooltip:'Minimum off time for chiller compressor (protection)'},
        'safety.chiller_min_on_s': {label:'Chiller min on (s)', type:'number', min:30, max:1800, step:10, tooltip:'Minimum runtime for chiller compressor (protection)'}
      }
    },
    alerts: {
      title: 'Alerts',
      fields: {
        'alerts.email_to': {label:'Alert email to', type:'text', placeholder:'user@example.com'},
        'alerts.alert_cooldown_s': {label:'Alert cooldown (s)', type:'number', min:0, max:86400, step:1, tooltip:'Cooldown between alerts to prevent spam'}
      }
    },
    ui: {
      title: 'UI',
      fields: {
        'ui.default_sensor_range': {label:'Default sensor range', type:'text', placeholder:'24h'},
        'ui.relays_poll_ms': {label:'Relays poll (ms)', type:'number', min:250, max:10000, step:50},
        'ui.sensors_poll_ms': {label:'Sensors poll (ms)', type:'number', min:1000, max:60000, step:250}
      }
    }
  };

  let original = {}; // flat map
  let current = {};  // flat map

  function markDirty() {
    const saveBtn = q('#btnSaveSettings');
    if (!saveBtn) return;
    saveBtn.disabled = Object.keys(diff()).length === 0;
  }

  function renderAll(){
    // Render each group into its own dedicated div
    Object.keys(GROUP_DEF).forEach((ns)=>{
      const targetDiv = q(`#settings-${ns}`);
      if (!targetDiv) return;
      
      targetDiv.innerHTML = '';
      const grp = GROUP_DEF[ns];
      if (!grp) return;

      // Create grid for fields
      const grid = document.createElement('div');
      grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-top:12px;';
      
      const fields = grp.fields;
      Object.entries(fields).forEach(([key, meta]) => {
        const val = current[key] ?? '';
        const wrap = document.createElement('div');
        wrap.style.cssText = 'display:flex;flex-direction:column;gap:6px;';
        
        const labelRow = document.createElement('div');
        labelRow.style.cssText = 'display:flex;align-items:center;gap:8px;';
        
        const label = document.createElement('label');
        const id = `f_${key.replace(/\./g,'_')}`;
        label.htmlFor = id;
        label.style.cssText = 'font-size:var(--font-sm);color:#9ca3af;font-weight:500;';
        label.textContent = meta.label;
        labelRow.appendChild(label);
        
        if (meta.badge){
          const badge = document.createElement('span');
          badge.style.cssText = 'padding:2px 6px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.3);border-radius:4px;color:#fca5a5;font-size:0.65rem;font-weight:600;text-transform:uppercase;';
          badge.textContent = meta.badge;
          labelRow.appendChild(badge);
        }
        
        if (meta.tooltip){
          const icon = document.createElement('span');
          icon.textContent = 'ℹ️';
          icon.style.cssText = 'cursor:help;font-size:0.85rem;';
          icon.title = meta.tooltip;
          labelRow.appendChild(icon);
        }
        
        wrap.appendChild(labelRow);
        
        let inp;
        if (meta.type === 'checkbox'){
          inp = document.createElement('input');
          inp.type = 'checkbox';
          inp.id = id;
          inp.checked = (val === 'true' || val === '1' || val === 'True');
          inp.style.cssText = 'width:20px;height:20px;cursor:pointer;';
          inp.addEventListener('change', ()=>{ current[key] = inp.checked ? 'true' : 'false'; markDirty(); });
        } else {
          inp = document.createElement('input');
          inp.type = meta.type || 'text';
          inp.id = id;
          inp.value = val;
          inp.placeholder = meta.placeholder || '';
          if (meta.min !== undefined) inp.min = meta.min;
          if (meta.max !== undefined) inp.max = meta.max;
          if (meta.step !== undefined) inp.step = meta.step;
          inp.style.cssText = 'height:32px;padding:0 10px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:var(--font-base);';
          inp.addEventListener('input', ()=>{ current[key] = inp.value; markDirty(); });
        }
        
        // Add Day N badge after grow_start_date input
        if (key === 'general.grow_start_date') {
          const badge = document.createElement('div');
          badge.id = 'grow-day-n-badge';
          badge.style.cssText = 'margin-top:6px;padding:6px 10px;border-radius:8px;background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.3);color:#93c5fd;font-size:0.85rem;font-weight:500;display:none;';
          wrap.appendChild(badge);
        }
        
        wrap.appendChild(inp);
        grid.appendChild(wrap);
      });
      
      targetDiv.appendChild(grid);
    });
  }

  function bindTabs(){
    // No longer needed - accordions handle interaction natively
  }

  function diff(){
    const d = {};
    for (const [k, v] of Object.entries(current)){
      if (String(v) !== String(original[k] ?? '')){
        d[k] = v;
      }
    }
    return d;
  }

  async function fetchSettings(){
    const res = await fetch('/api/settings?t='+Date.now(), {cache:'no-store'});
    const j = await res.json();
    // flatten
    const flat = {};
    Object.entries(j||{}).forEach(([ns, m])=>{
      Object.entries(m||{}).forEach(([k, v])=> flat[`${ns}.${k}`] = String(v ?? ''));
    });
    // Defensive: seed new safety caps if backend hasn't populated yet (UI fallback)
    const defaults = {
      'safety.max_seconds_per_press': '1.5',
      'safety.max_total_seconds_per_24h': '120',
      'safety.min_off_window_sec': '2'
    };
    Object.entries(defaults).forEach(([k,v])=>{ if (!(k in flat)) flat[k] = v; });
    original = {...flat};
    current = {...flat};
  }

  async function save(){
    const changes = diff();
    if (Object.keys(changes).length===0) return;
    const res = await fetch('/api/settings',{
      method:'PUT',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(changes)
    });
    if (res.status===422){
      const err = await res.json();
      if (window.showToast) showToast(`${err.field||'field'}: ${err.message||'Invalid value'}`, 'error');
      return;
    }
    const j = await res.json();
    if (j.ok){
      original = {...current};
      if (window.showToast) showToast('Settings saved', 'success');
      // Apply UI polling changes
      const uiRel = changes['ui.relays_poll_ms'];
      const uiSen = changes['ui.sensors_poll_ms'];
      window.APP_POLL = window.APP_POLL || { relays: 1000, sensors: 5000 };
      if (uiRel) window.APP_POLL.relays = parseInt(uiRel,10)||1000;
      if (uiSen) window.APP_POLL.sensors = parseInt(uiSen,10)||5000;
      window.dispatchEvent(new CustomEvent('settings:ui', {detail:{poll: window.APP_POLL}}));
      // Update Day N badge and Sensors header if grow_start_date changed
      if (changes['general.grow_start_date'] !== undefined) {
        updateDayNBadge();
        updateSensorsHeaderDayN();
      }
      markDirty();
    }
  }
  
  function updateDayNBadge() {
    const badge = q('#grow-day-n-badge');
    if (!badge) return;
    const startDate = current['general.grow_start_date'];
    if (!startDate) {
      badge.style.display = 'none';
      return;
    }
    const dayN = calculateDayN(startDate, current['general.timezone']);
    if (dayN !== null) {
      badge.textContent = `Day ${dayN}`;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  }
  
  function calculateDayN(startDateStr, timezone) {
    if (!startDateStr) return null;
    try {
      const start = new Date(startDateStr + 'T00:00:00');
      const now = new Date();
      const diffMs = now - start;
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
      return Math.max(1, diffDays + 1);
    } catch (e) {
      return null;
    }
  }
  
  function updateSensorsHeaderDayN() {
    const startDate = current['general.grow_start_date'];
    const badge = q('#sensors-grow-day-badge');
    if (!badge) return;
    if (!startDate) {
      badge.style.display = 'none';
      return;
    }
    const dayN = calculateDayN(startDate, current['general.timezone']);
    if (dayN !== null) {
      badge.textContent = `Grow Day ${dayN}`;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  }

  function bindActions(){
    const saveBtn = q('#btnSaveSettings');
    if (saveBtn) saveBtn.addEventListener('click', save);

    const exportBtn = q('#btnExportSettings');
    if (exportBtn) exportBtn.addEventListener('click', async ()=>{
      const r = await fetch('/api/settings/export?t='+Date.now(), {cache:'no-store'});
      const j = await r.json();
      const blob = new Blob([JSON.stringify(j,null,2)], {type:'application/json'});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'rdwc-settings.json';
      a.click();
    });

    const file = q('#importFile');
    if (file) file.addEventListener('change', async (e)=>{
      const f = e.target.files[0];
      if (!f) return;
      try{
        const txt = await f.text();
        const payload = JSON.parse(txt);
        const keys = Object.keys(payload||{});
        if (!keys.length) return;
        if (!confirm(`Import ${keys.length} keys? This will overwrite existing values.`)) return;
        const r = await fetch('/api/settings/import',{
          method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
        });
        const j = await r.json();
        if (j.ok){ if (window.showToast) showToast(`Imported ${j.changed} keys`, 'success'); await boot(); }
        else { if (window.showToast) showToast(j.message||'Import failed', 'error'); }
      }catch(err){ if (window.showToast) showToast('Invalid JSON', 'error'); }
      e.target.value = '';
    });
  }

  async function boot(){
    try {
      await fetchSettings();
      renderAll();
      bindTabs();
      updateDayNBadge();
      updateSensorsHeaderDayN();
      bindActions();
      markDirty();
      // seed APP_POLL from settings
      window.APP_POLL = window.APP_POLL || { relays: 1000, sensors: 5000 };
      if (current['ui.relays_poll_ms']) window.APP_POLL.relays = parseInt(current['ui.relays_poll_ms'],10)||1000;
      if (current['ui.sensors_poll_ms']) window.APP_POLL.sensors = parseInt(current['ui.sensors_poll_ms'],10)||5000;
      window.dispatchEvent(new CustomEvent('settings:ui', {detail:{poll: window.APP_POLL}}));
    } catch(e){
      console.warn('settings boot failed', e);
    }
  }

  // Expose helper for other modules
  window.rdwcSettings = {
    get: (key) => current[key] || '',
    calculateDayN
  };

  // Auto init once DOM is ready
  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
