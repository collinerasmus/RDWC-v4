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
        'general.grow_start_date': {label:'Grow start date', type:'date'}
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
    },
    electrical: {
      title: 'Electrical',
      fields: {
        // Supply voltage; relay wattage fields are added dynamically based on environment_info.relay_pins
        'electrical.voltage_v': {label:'Supply voltage (V)', type:'number', min:100, max:260, step:1, tooltip:'Mains supply voltage used for current calculation'}
      }
    }
  };

  let original = {}; // flat map
  let current = {};  // flat map

  function getSaveButtons() {
    return Array.from(document.querySelectorAll('[data-role="save-settings"]'));
  }

  function markDirty() {
    const dirty = Object.keys(diff()).length !== 0;
    getSaveButtons().forEach(btn => { btn.disabled = !dirty; });
  }

  function renderAll(){
    // Render each group into its own dedicated div
    Object.keys(GROUP_DEF).forEach((ns)=>{
      const targetDiv = q(`#settings-${ns}`);
      if (!targetDiv) return;
      
      targetDiv.innerHTML = '';
      const grp = GROUP_DEF[ns];
      if (!grp) return;

      // Create grid for fields (matching pH/EC Parameters style)
      const grid = document.createElement('div');
      grid.style.cssText = 'display:grid;grid-template-columns:repeat(2,max-content);justify-content:start;justify-items:start;column-gap:10px;row-gap:8px;margin-bottom:8px;align-items:end;';
      
      const fields = grp.fields;
      Object.entries(fields).forEach(([key, meta]) => {
        const val = current[key] ?? '';
        const wrap = document.createElement('div');
        
        const label = document.createElement('label');
        const id = `f_${key.replace(/\./g,'_')}`;
        label.htmlFor = id;
        label.style.cssText = 'display:block;font-size:var(--font-xs);margin-bottom:2px;color:#9ca3af;';
        
        // Label text with optional badge
        let labelText = meta.label;
        if (meta.badge) {
          labelText += ` (${meta.badge})`;
        }
        label.textContent = labelText;
        
        if (meta.tooltip) {
          label.title = meta.tooltip;
        }
        
        wrap.appendChild(label);
        
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
          inp.style.cssText = 'width:120px;height:28px;padding:0 6px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;font-size:var(--font-base);';
          inp.addEventListener('input', ()=>{ current[key] = inp.value; markDirty(); });
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

    // Dynamically extend Electrical group with per‑relay watt fields
    try {
      const sysRes = await fetch('/api/system/info?t='+Date.now(), {cache:'no-store'});
      const sys = await sysRes.json();
      const pins = sys?.environment_info?.relay_pins || {};
      const elFields = GROUP_DEF.electrical.fields;
      Object.keys(pins).forEach(name => {
        const key = `electrical.watts.${name}`;
        if (!elFields[key]) {
          elFields[key] = {label:`Watts: ${name.replace(/_/g,' ')}`, type:'number', min:0, max:5000, step:1, tooltip:`Configured wattage for relay '${name}'`};
        }
        // Seed current with existing value if present; otherwise keep blank
        if (flat[key] !== undefined) {
          current[key] = flat[key];
        }
      });
    } catch (e) {
      // Non‑fatal; UI will still render voltage
      console.warn('Failed to extend Electrical fields from system info', e);
    }
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
      // Update Sensors header if grow_start_date changed
      if (changes['general.grow_start_date'] !== undefined) {
        if (typeof updateSensorsHeaderDayN === 'function') {
          updateSensorsHeaderDayN();
        }
        if (window.scheduleModule?.refresh) {
          window.scheduleModule.refresh();
        }
      }
      window.dispatchEvent(new CustomEvent('settings:saved', { detail: { changes } }));
      markDirty();
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
    const saveBtns = getSaveButtons();
    saveBtns.forEach(btn => btn.addEventListener('click', save));

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
    getAll: () => ({...current}),
    reload: async () => { await fetchSettings(); markDirty(); return {...current}; },
    set: (key, value) => { current[key] = value; },
    calculateDayN
  };

  // Auto init once DOM is ready
  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
