(function(){
  const q = (s, r=document) => r.querySelector(s);
  const qa = (s, r=document) => Array.from(r.querySelectorAll(s));

  const GROUP_DEF = {
    general: {
      title: 'General',
      fields: {
        'general.grow_name': {label:'Grow name', type:'text'},
        'general.timezone': {label:'Timezone', type:'text', placeholder:'Africa/Johannesburg'},
        'general.reservoir_liters': {label:'Reservoir (L)', type:'number', min:1, max:1000, step:0.1}
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
        'dosing.mix_delay_s': {label:'Mix delay (s)', type:'number', min:0, max:3600, step:1}
      }
    },
    safety: {
      title: 'Safety',
      fields: {
        'safety.main_pump_min_off_s': {label:'Main pump min OFF (s)', type:'number', min:0, max:3600, step:1, tooltip:'Minimum OFF time to prevent short cycling'},
        'safety.chiller_pump_min_off_s': {label:'Chiller pump min OFF (s)', type:'number', min:0, max:3600, step:1},
        'safety.chiller_min_off_s': {label:'Chiller AC min OFF (s)', type:'number', min:0, max:3600, step:1, tooltip:'Compressor protection — recommended ≥ 300s'},
        'safety.chiller_min_on_s': {label:'Chiller AC min ON (s)', type:'number', min:0, max:3600, step:1},
        'safety.estop_persist': {label:'E‑STOP persists across reboot', type:'checkbox'}
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
      }
      input.id = id;
      input.addEventListener('input', ()=>{
        if (meta.type === 'checkbox'){
          current[key] = input.checked ? 'true' : 'false';
        } else {
          current[key] = input.value;
        }
        markDirty();
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
      markDirty();
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

  // Auto init once DOM is ready
  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
