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
    targets: {
      title: 'Targets',
      fields: {
        'targets.ph_low': {label:'pH Low', type:'number', min:4.0, max:7.5, step:0.01},
        'targets.ph_high': {label:'pH High', type:'number', min:4.0, max:7.5, step:0.01},
        'targets.ec_target': {label:'EC Target (mS/cm)', type:'number', min:0.0, max:4.0, step:0.01},
        'targets.ec_tolerance': {label:'EC Tolerance (±)', type:'number', min:0.0, max:4.0, step:0.01},
        'targets.temp_target_c': {label:'Temp Target (°C)', type:'number', min:15, max:28, step:1}
      }
    },
    dosing: {
      title: 'Dosing',
      fields: {
        'dosing.pulse_ml_grow': {label:'Grow pulse (ml)', type:'number', min:0, max:1000, step:1},
        'dosing.pulse_ml_micro': {label:'Micro pulse (ml)', type:'number', min:0, max:1000, step:1},
        'dosing.pulse_ml_bloom': {label:'Bloom pulse (ml)', type:'number', min:0, max:1000, step:1},
        'dosing.max_ml_hour_': {label:'Max per hour (ml)', type:'number', min:0, max:5000, step:1},
        'dosing.max_ml_day_': {label:'Max per day (ml)', type:'number', min:0, max:20000, step:1},
        'dosing.mix_delay_s': {label:'Mix delay (s)', type:'number', min:0, max:3600, step:1},
        'dosing.ph_up_ml_per_sec': {label:'pH Up calibration (ml/s)', type:'number', min:0.1, max:200, step:0.1, tooltip:'Used to convert seconds to ml for totals'}
      }
    },
    safety: {
      title: 'Safety',
      fields: {
        'safety.main_pump_min_off_s': {label:'Main pump min OFF (s)', type:'number', min:0, max:3600, step:1, tooltip:'Minimum OFF time to prevent short cycling'},
        'safety.chiller_pump_min_off_s': {label:'Chiller pump min OFF (s)', type:'number', min:0, max:3600, step:1},
        'safety.chiller_min_off_s': {label:'Chiller AC min OFF (s)', type:'number', min:0, max:3600, step:1, tooltip:'Compressor protection — recommended ≥ 300s'},
        'safety.chiller_min_on_s': {label:'Chiller AC min ON (s)', type:'number', min:0, max:3600, step:1},
        'safety.estop_persist': {label:'E‑STOP persists across reboot', type:'checkbox'},
        'safety.allow_force': {label:'Allow Force (test)', type:'checkbox', tooltip:'Temporarily allow bypassing cooldown and daily cap for testing only'},
        'safety.maintenance_override': {label:'Maintenance override (test only)', type:'checkbox', tooltip:'Bypasses cooldown/daily cap; clamps single dose; E-STOP/empty reservoir still enforced'},
        'safety.allow_stale_on_override': {label:'Allow stale sensors on override', type:'checkbox', tooltip:'Allows dosing when sensors are stale (TEST ONLY). Off by default.', badge:'TEST'}
      }
    },
    alerts: {
      title: 'Alerts',
      fields: {
        'alerts.email_to': {label:'Alert email to', type:'text', placeholder:'user@example.com'},
        'alerts.ph_hi_alert': {label:'pH high threshold', type:'number', min:4.0, max:7.5, step:0.01},
        'alerts.ph_lo_alert': {label:'pH low threshold', type:'number', min:4.0, max:7.5, step:0.01},
        'alerts.ec_hi_alert': {label:'EC high (mS/cm)', type:'number', min:0, max:4, step:0.01},
        'alerts.ec_lo_alert': {label:'EC low (mS/cm)', type:'number', min:0, max:4, step:0.01},
        'alerts.temp_hi_alert': {label:'Temp high (°C)', type:'number', min:15, max:40, step:1},
        'alerts.temp_lo_alert': {label:'Temp low (°C)', type:'number', min:0, max:28, step:1},
        'alerts.alert_cooldown_s': {label:'Alert cooldown (s)', type:'number', min:0, max:86400, step:1}
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
    calibration: {
      title: 'Calibration',
      fields: { /* custom-rendered below */ }
    }
  };

  let original = {}; // flat map
  let current = {};  // flat map

  function markDirty() {
    const saveBtn = q('#btnSaveSettings');
    if (!saveBtn) return;
    saveBtn.disabled = Object.keys(diff()).length === 0;
  }

  function renderGroup(ns){
    const panel = document.createElement('div');
    panel.dataset.ns = ns;
    // Custom panel for Calibration
    if (ns === 'calibration'){
      const title = document.createElement('h3');
      title.textContent = 'Calibration';
      title.className = 'muted';
      title.style.margin = '0 0 8px 0';

      // pH calibration card
      const phWrap = document.createElement('div');
      phWrap.className = 'card';
      phWrap.style.padding = '12px';
      phWrap.innerHTML = `
        <h3 style="margin-top:0;">pH Calibration</h3>
        <div id="ph-calib-banner" class="row" style="margin-bottom:6px;display:none">
          <span class="muted">Writes are disabled. Set CALIB_ENABLE=1 and restart service to enable calibration commands.</span>
        </div>
        <div class="row">
          <label>Current pH:</label>
          <span id="ph-current" style="margin-left:8px">—</span>
          <button id="btnPhRead" class="btn-secondary" style="margin-left:8px">Read</button>
          <button id="btnPhStatus" class="btn-secondary" style="margin-left:8px">Status</button>
        </div>
        <div class="row" style="margin-top:6px;align-items:center;flex-wrap:wrap;gap:6px;">
          <label>Buffer:</label>
          <select id="ph-buffer-kind" style="margin-left:8px;padding:4px;border-radius:4px;border:1px solid #1f2937;background:#111827;color:#e6edf3">
            <option value="mid" data-default="7.00">Mid (7.00)</option>
            <option value="low" data-default="4.00">Low (4.00)</option>
            <option value="high" data-default="10.00">High (10.00)</option>
          </select>
          <input id="ph-buffer-val" type="number" step="0.01" min="0" max="14" value="7.00" style="width:90px;margin-left:4px;padding:4px;border-radius:4px;border:1px solid #1f2937;background:#111827;color:#e6edf3"/>
          <button id="btnPhCalibrate" class="btn-secondary">Calibrate</button>
          <button id="btnPhClear" class="btn-secondary" style="margin-left:8px">Clear</button>
        </div>
        <div class="row" style="margin-top:6px">
          <span id="ph-calib-msg" class="muted"></span>
        </div>
      `;

      // EC placeholder
      const ecWrap = document.createElement('div');
      ecWrap.className = 'card';
      ecWrap.style.padding = '12px';
      ecWrap.style.marginTop = '12px';
      ecWrap.innerHTML = `
        <h3 style="margin-top:0;">EC Calibration (coming soon)</h3>
        <div class="row">
          <button class="btn-secondary" disabled title="Planned">Start</button>
          <button class="btn-secondary" style="margin-left:8px" disabled title="Planned">Apply</button>
          <span class="muted" style="margin-left:10px">Planned – will match pH flow</span>
        </div>
      `;

      panel.appendChild(title);
      panel.appendChild(phWrap);
      panel.appendChild(ecWrap);

      // Wire up pH controls
      const msg = () => q('#ph-calib-msg');
      const setMsg = (t, ok=true) => { const el = msg(); if (!el) return; el.textContent = t||''; el.style.color = ok? '#9ca3af' : '#fca5a5'; };
      const setCurrent = (v) => { const sp = q('#ph-current'); if (sp) sp.textContent = (v==null? '—' : Number(v).toFixed(2)); };
      const setBanner = (on) => { const b = q('#ph-calib-banner'); if (b) b.style.display = on? 'block':'none'; };

      // Default buffer value follows selection
      const kindSel = q('#ph-buffer-kind');
      const valInp = q('#ph-buffer-val');
      if (kindSel && valInp){
        kindSel.addEventListener('change', ()=>{
          const opt = kindSel.options[kindSel.selectedIndex];
          const def = opt ? (opt.getAttribute('data-default')||'') : '';
          if (def) valInp.value = def;
        });
      }

      const read = async ()=>{
        try{
          const r = await (await fetch('/calib/ph/read?t='+Date.now(), {cache:'no-store'})).json();
          if (r && r.ok){ setCurrent(r.value); setMsg('Read OK'); }
          else { setMsg(r && r.note ? r.note : 'Read failed', false); }
        }catch(e){ setMsg('Read failed', false); }
      };
      const status = async ()=>{
        try{
          const r = await (await fetch('/calib/ph/status?t='+Date.now(), {cache:'no-store'})).json();
          if (r && r.ok){ setMsg('Status: ' + (r.status||'unknown') + (r.flags? ' • '+r.flags.join(', '):'')); }
          else { setMsg('Status check failed', false); }
        }catch(e){ setMsg('Status check failed', false); }
      };
      const caps = async ()=>{
        try{
          const r = await (await fetch('/calib/ph/caps?t='+Date.now(), {cache:'no-store'})).json();
          setBanner(!(r && r.enabled));
        }catch(e){ /* noop */ }
      };
      const doCal = async ()=>{
        try{
          const kind = (kindSel && kindSel.value) || 'mid';
          const val  = parseFloat(valInp && valInp.value || '7.00');
          const ep = kind==='low'? 'low' : kind==='high'? 'high' : 'mid';
          const r = await (await fetch(`/calib/ph/${ep}?value=${encodeURIComponent(val.toFixed(2))}`, {method:'POST'})).json();
          if (r && r.ok){ setMsg(r.note || 'Calibration command sent'); }
          else { setMsg((r && r.note) || 'Calibration rejected', false); }
        }catch(e){ setMsg('Calibration failed', false); }
      };
      const clear = async ()=>{
        try{
          const r = await (await fetch('/calib/ph/clear', {method:'POST'})).json();
          if (r && r.ok){ setMsg(r.note || 'Calibration cleared'); }
          else { setMsg((r && r.note) || 'Clear rejected', false); }
        }catch(e){ setMsg('Clear failed', false); }
      };

      const bRead = q('#btnPhRead'); if (bRead) bRead.addEventListener('click', read);
      const bStat = q('#btnPhStatus'); if (bStat) bStat.addEventListener('click', status);
      const bCal  = q('#btnPhCalibrate'); if (bCal) bCal.addEventListener('click', doCal);
      const bClr  = q('#btnPhClear'); if (bClr) bClr.addEventListener('click', clear);

      // Prime values on open
      setMsg(''); caps(); status(); read();
      return panel;
    }
    const fields = GROUP_DEF[ns].fields;
    Object.entries(fields).forEach(([key, meta]) => {
      const val = current[key] ?? '';
      const wrap = document.createElement('div');
      wrap.className = 'row';
      const id = `f_${key.replace(/\./g,'_')}`;
      const label = document.createElement('label');
      label.textContent = meta.label + ':';
      let input;
      if (meta.type === 'checkbox'){
        input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = String(val).toLowerCase() === 'true';
      } else {
        input = document.createElement('input');
        input.type = meta.type || 'text';
        if (meta.min!=null) input.min = meta.min;
        if (meta.max!=null) input.max = meta.max;
        if (meta.step!=null) input.step = meta.step;
        if (meta.placeholder) input.placeholder = meta.placeholder;
        input.value = val;
        input.style.cssText = 'margin-left:8px;padding:4px;border-radius:4px;border:1px solid #1f2937;background:#111827;color:#e6edf3;';
        // For date inputs, set max to today
        if (meta.type === 'date') {
          const today = new Date().toISOString().split('T')[0];
          input.max = today;
        }
      }
      input.id = id;
      input.addEventListener('input', ()=>{
        if (meta.type === 'checkbox'){
          current[key] = input.checked ? 'true' : 'false';
        } else {
          current[key] = input.value;
        }
        markDirty();
        // Update Day N badge if grow_start_date changed
        if (key === 'general.grow_start_date') {
          updateDayNBadge();
        }
      });
      wrap.appendChild(label);
      wrap.appendChild(input);
      if (meta.tooltip){
        const tip = document.createElement('span');
        tip.className = 'muted';
        tip.style.marginLeft = '8px';
        tip.textContent = meta.tooltip;
        wrap.appendChild(tip);
      }
      // Optional badge (e.g., TEST)
      if (meta.badge){
        const badge = document.createElement('span');
        badge.textContent = meta.badge;
        badge.style.cssText = 'margin-left:8px;padding:2px 6px;border-radius:6px;background:rgba(220,38,38,0.12);border:1px solid rgba(220,38,38,0.3);color:#fca5a5;font-size:0.75rem;';
        wrap.appendChild(badge);
      }
      
      // Add Day N badge after grow_start_date input
      if (key === 'general.grow_start_date') {
        const badge = document.createElement('span');
        badge.id = 'grow-day-n-badge';
        badge.className = 'muted';
        badge.style.cssText = 'margin-left:8px;padding:4px 8px;border-radius:6px;background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.3);color:#93c5fd;font-size:0.85rem;';
        badge.style.display = 'none';
        wrap.appendChild(badge);
      }
      
      panel.appendChild(wrap);
    });
    return panel;
  }

  function renderAll(){
    const tabs = q('#settings-tabs');
    const panels = q('#settings-panels');
    if (!tabs || !panels) return;
    panels.innerHTML = '';
    tabs.querySelectorAll('.btn-chip').forEach(btn => btn.classList.remove('active'));

    Object.keys(GROUP_DEF).forEach((ns,i)=>{
      const panel = renderGroup(ns);
      panel.style.display = i===0 ? 'block' : 'none';
      panels.appendChild(panel);
    });

    // Activate first tab
    const first = tabs.querySelector('[data-tab]');
    if (first) first.classList.add('active');
  }

  function bindTabs(){
    const tabs = q('#settings-tabs');
    const panels = q('#settings-panels');
    if (!tabs || !panels) return;
    tabs.addEventListener('click', (e)=>{
      const btn = e.target.closest('[data-tab]');
      if (!btn) return;
      const ns = btn.dataset.tab;
      qa('#settings-tabs .btn-chip').forEach(b=>b.classList.toggle('active', b===btn));
      qa('#settings-panels > div').forEach(p=> p.style.display = (p.dataset.ns===ns?'block':'none'));
    });
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
