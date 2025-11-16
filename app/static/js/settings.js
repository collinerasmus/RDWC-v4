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
    },
    chiller: {
      title: 'Chiller',
      fields: {
        'chiller.target_temp': {label:'Target temp (°C)', type:'number', min:15, max:28, step:0.5, tooltip:'Optimal water temperature for DWC/RDWC'},
        'chiller.hysteresis': {label:'Hysteresis (°C)', type:'number', min:0.1, max:3, step:0.1, tooltip:'Temperature deadband (e.g., 0.5°C: ON at +0.5, OFF at -0.5)'},
        'chiller.min_on_seconds': {label:'Min ON time (s)', type:'number', min:30, max:1800, step:10, tooltip:'Minimum compressor runtime (protection)'},
        'chiller.min_off_seconds': {label:'Min OFF time (s)', type:'number', min:60, max:3600, step:10, tooltip:'Minimum compressor cooldown (protection)'},
        'chiller.control_interval_s': {label:'Control check interval (s)', type:'number', min:10, max:300, step:5, tooltip:'How often to check temperature and adjust'},
        'chiller.auto_enabled': {label:'Auto control enabled', type:'checkbox', tooltip:'Enable automatic temperature control'},
        'chiller.max_temp_alarm': {label:'Max temp alarm (°C)', type:'number', min:20, max:35, step:0.5, tooltip:'Alert if water exceeds this temperature'},
        'chiller.min_temp_alarm': {label:'Min temp alarm (°C)', type:'number', min:10, max:20, step:0.5, tooltip:'Alert if water below this temperature'},
        'chiller.stage': {label:'Growth stage', type:'select', options:['default','veg','flower'], tooltip:'Optimizes temperature for growth stage'}
      }
    },
    automation: {
      title: 'Automation',
      fields: {
        'ph.auto_enabled': {label:'pH automation enabled', type:'checkbox', tooltip:'Enable automatic pH Up dosing'},
        'dosing.ph_up_step_min_ml': {label:'pH Up min step (ml)', type:'number', min:0.1, max:5, step:0.1, tooltip:'Minimum dose amount for pH Up'},
        'dosing.ph_up_step_max_ml': {label:'pH Up max step (ml)', type:'number', min:0.5, max:10, step:0.5, tooltip:'Maximum dose amount for pH Up'},
        'dosing.ph_up_safety_factor': {label:'pH Up safety factor', type:'number', min:0.1, max:1, step:0.05, tooltip:'Conservative multiplier (0.6 = 60% of learned value)'},
        'dosing.ph_min_interval_s': {label:'pH min interval (s)', type:'number', min:60, max:3600, step:30, tooltip:'Minimum time between pH doses'},
        'dosing.observe_s_after_dose': {label:'pH observe window (s)', type:'number', min:3600, max:86400, step:3600, tooltip:'Wait time after dose before next action'},
        'ec.auto_enabled': {label:'EC automation enabled', type:'checkbox', tooltip:'Enable automatic EC (nutrient) dosing'},
        'dosing.ec_step_ml_min': {label:'EC min step (ml)', type:'number', min:1, max:50, step:1, tooltip:'Minimum total dose amount for EC'},
        'dosing.ec_step_ml_max': {label:'EC max step (ml)', type:'number', min:10, max:500, step:10, tooltip:'Maximum total dose amount for EC'},
        'dosing.ec_safety_factor': {label:'EC safety factor', type:'number', min:0.1, max:1, step:0.05, tooltip:'Conservative multiplier (0.6 = 60% of learned value)'},
        'dosing.ec_min_interval_s': {label:'EC min interval (s)', type:'number', min:60, max:3600, step:30, tooltip:'Minimum time between EC doses'},
        'dosing.ec_max_ml_day': {label:'EC max ml/day', type:'number', min:0, max:1000, step:10, tooltip:'Daily cap for total EC dosing (0 = unlimited)'}
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

      // EC Calibration (full wizard moved from EC Controller card)
      const ecWrap = document.createElement('div');
      ecWrap.className = 'card';
      ecWrap.style.padding = '12px';
      ecWrap.style.marginTop = '12px';
      ecWrap.innerHTML = `
        <h3 style="margin-top:0;">EC Calibration</h3>
        <div style="padding:12px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);border-radius:8px;margin-bottom:16px;color:#fecaca;">
          ⚠️ <strong>Warning:</strong> Calibration affects all EC readings. Follow Atlas Scientific calibration procedure precisely. Rinse probe between steps.
        </div>
        
        <div style="margin-bottom:16px;padding:12px;background:rgba(148,163,184,0.05);border:1px solid rgba(148,163,184,0.2);border-radius:8px;">
          <div style="font-weight:600;margin-bottom:8px;">Current Status</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.9rem;">
            <div>Calibration: <strong id="ecCalStatusValue">—</strong></div>
            <div>K Factor: <strong id="ecKValue">—</strong></div>
            <div>Current EC: <strong id="ecCalCurrentReading">—</strong> mS/cm</div>
            <div><button id="btnEcCalRefreshStatus" class="btn-text" style="padding:4px 8px;font-size:0.85rem;">🔄 Refresh</button></div>
          </div>
        </div>
        
        <div style="margin-bottom:16px;padding:12px;background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.25);border-radius:8px;">
          <div style="font-weight:600;margin-bottom:8px;">Calibration Steps</div>
          <ol style="margin:0;padding-left:20px;line-height:1.8;">
            <li>Rinse probe with DI water and shake dry</li>
            <li>Place probe in 1413 µS/cm solution</li>
            <li>Wait 30s for stabilization, then click "Low Point (1413 µS/cm)"</li>
            <li><em>(Optional)</em> For 2-point: rinse, place in 12,880 µS/cm, wait 30s, click "High Point"</li>
            <li>Verify reading matches known solution</li>
          </ol>
        </div>
        
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">
          <button id="btnEcCalClear" class="btn-secondary" title="Clear calibration and start fresh">Clear Calibration</button>
          <button id="btnEcCalLow" class="btn-primary" title="Apply 1-point calibration at 1413 µS/cm">Low Point (1413 µS/cm)</button>
          <button id="btnEcCalHigh" class="btn-secondary" title="Apply high point for 2-point calibration at 12,880 µS/cm">High Point (12,880 µS/cm)</button>
          <button id="btnEcCalSetK" class="btn-secondary" title="Set K factor (probe constant)">Set K=1.0</button>
        </div>
        
        <div id="ecCalMessage" class="muted" style="padding:8px;border-radius:6px;background:rgba(148,163,184,0.05);border:1px solid rgba(148,163,184,0.2);min-height:40px;">
          Ready. Click "Refresh" to see current status.
        </div>
      `;

      // Dosing calibration
      const doseWrap = document.createElement('div');
      doseWrap.className = 'card';
      doseWrap.style.padding = '12px';
      doseWrap.style.marginTop = '12px';
      doseWrap.innerHTML = `
        <h3 style="margin-top:0;">Dosing Calibration</h3>
        <div id="dose-calib-banner" class="row" style="margin-bottom:6px;display:none">
          <span class="muted">Writes are disabled. Set CALIB_ENABLE=1 and restart service to enable calibration commands.</span>
        </div>
        <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap;">
          <label for="dose-pump">Pump:</label>
          <select id="dose-pump" style="padding:4px;border-radius:4px;border:1px solid #1f2937;background:#111827;color:#e6edf3"></select>
          <span class="muted">Current rate:</span>
          <span id="dose-current">—</span>
          <button id="btnDoseRefresh" class="btn-secondary">Refresh</button>
        </div>
        <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px;">
          <label>Prime:</label>
          <button id="btnDosePrimeToggle" class="btn-secondary">Start Priming</button>
          <span class="muted">Manual start/stop; auto‑stops after safety timeout.</span>
        </div>
        <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px;">
          <label>Run:</label>
          <input id="dose-run-sec" type="number" min="0.2" max="10.0" step="0.1" value="5.0" style="width:80px;padding:4px;border-radius:4px;border:1px solid #1f2937;background:#111827;color:#e6edf3"/>
          <span class="muted">sec</span>
          <button id="btnDoseRun" class="btn-secondary">Run</button>
        </div>
        <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px;">
          <label>Measured:</label>
          <input id="dose-measured-ml" type="number" min="0.1" step="0.1" value="50.0" style="width:100px;padding:4px;border-radius:4px;border:1px solid #1f2937;background:#111827;color:#e6edf3"/>
          <span class="muted">ml</span>
          <button id="btnDoseCommit" class="btn-secondary" title="Compute ml/s and save">Compute & Save</button>
        </div>
        <div class="row" style="margin-top:6px">
          <span id="dose-calib-msg" class="muted"></span>
        </div>
        <div id="dose-calib-log" class="muted" style="margin-top:8px;max-height:160px;overflow:auto;font-family:ui-monospace, monospace;font-size:12px;border-top:1px dashed #1f2937;padding-top:6px"></div>
      `;

      panel.appendChild(title);
      panel.appendChild(doseWrap);
      panel.appendChild(ecWrap);

      // Panel-scoped query helper
      const qP = (sel) => panel.querySelector(sel);
      
      // EC Calibration wiring
      const ecMsgEl = qP('#ecCalMessage');
      const setEcMsg = (t, ok=true)=>{ if (ecMsgEl){ ecMsgEl.textContent = t||''; ecMsgEl.style.color = ok? '#9ca3af' : '#fca5a5'; } };
      const ecStatus = async ()=>{
        try{
          const r = await (await fetch('/api/ec/cal/status?t='+Date.now(), {cache:'no-store'})).json();
          if (!r || !r.ok){ setEcMsg('Status load failed', false); return; }
          const sts = qP('#ecCalStatusValue'); if (sts) sts.textContent = r.status || '—';
          const kv = qP('#ecKValue'); if (kv) kv.textContent = r.K ? Number(r.K).toFixed(2) : '—';
          const ecCur = qP('#ecCalCurrentReading'); if (ecCur) ecCur.textContent = r.ec_mscm!=null ? Number(r.ec_mscm).toFixed(2) : '—';
          setEcMsg(`Status: ${r.status}. K=${r.K||'—'}, EC=${r.ec_mscm!=null ? r.ec_mscm.toFixed(2) : '—'} mS/cm`);
        }catch(e){ setEcMsg('Status failed', false); }
      };
      const btnEcCalRefreshStatus = qP('#btnEcCalRefreshStatus');
      if (btnEcCalRefreshStatus) btnEcCalRefreshStatus.addEventListener('click', ecStatus);
      const btnEcCalClear = qP('#btnEcCalClear');
      if (btnEcCalClear) btnEcCalClear.addEventListener('click', async ()=>{
        try{
          setEcMsg('Clearing calibration...');
          const r = await (await fetch('/api/ec/cal/clear', {method:'POST'})).json();
          if (r && r.ok){ setEcMsg(r.note || 'Calibration cleared'); await ecStatus(); }
          else { setEcMsg((r && r.note) || 'Clear failed', false); }
        }catch(e){ setEcMsg('Clear failed', false); }
      });
      const btnEcCalLow = qP('#btnEcCalLow');
      if (btnEcCalLow) btnEcCalLow.addEventListener('click', async ()=>{
        try{
          setEcMsg('Setting low point (1413 µS/cm)...');
          const r = await (await fetch('/api/ec/cal/low', {method:'POST'})).json();
          if (r && r.ok){ setEcMsg(r.note || 'Low point calibration accepted'); await ecStatus(); }
          else { setEcMsg((r && r.note) || 'Low cal failed', false); }
        }catch(e){ setEcMsg('Low cal failed', false); }
      });
      const btnEcCalHigh = qP('#btnEcCalHigh');
      if (btnEcCalHigh) btnEcCalHigh.addEventListener('click', async ()=>{
        try{
          setEcMsg('Setting high point (12,880 µS/cm)...');
          const r = await (await fetch('/api/ec/cal/high', {method:'POST'})).json();
          if (r && r.ok){ setEcMsg(r.note || 'High point calibration accepted'); await ecStatus(); }
          else { setEcMsg((r && r.note) || 'High cal failed', false); }
        }catch(e){ setEcMsg('High cal failed', false); }
      });
      const btnEcCalSetK = qP('#btnEcCalSetK');
      if (btnEcCalSetK) btnEcCalSetK.addEventListener('click', async ()=>{
        try{
          setEcMsg('Setting K=1.0...');
          const r = await (await fetch('/api/ec/k', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({k:1.0})})).json();
          if (r && r.ok){ setEcMsg(r.note || 'K factor set to 1.0'); await ecStatus(); }
          else { setEcMsg((r && r.note) || 'K set failed', false); }
        }catch(e){ setEcMsg('K set failed', false); }
      });

  // Dosing wiring (qP already defined above for panel-scoped queries)
  const doseMsgEl = qP('#dose-calib-msg');
  const doseLog = (line)=>{ const box = qP('#dose-calib-log'); if (!box) return; const ts=new Date().toLocaleTimeString(); const div=document.createElement('div'); div.textContent = `[${ts}] ${line}`; box.appendChild(div); box.scrollTop = box.scrollHeight; };
      const setDoseMsg = (t, ok=true)=>{ if (doseMsgEl){ doseMsgEl.textContent = t||''; doseMsgEl.style.color = ok? '#9ca3af' : '#fca5a5'; } doseLog(t); };
  const doseSel = qP('#dose-pump');
  const doseCur = qP('#dose-current');
      const renderPumps = async ()=>{
        try{
          const r = await (await fetch('/calib/dose/pumps?t='+Date.now(), {cache:'no-store'})).json();
          if (!r || !r.ok) throw new Error('load failed');
          if (!Array.isArray(r.pumps)) r.pumps = [];
          const prev = doseSel ? doseSel.value : '';
          if (doseSel){
            // Rebuild options fresh each time for robustness
            doseSel.innerHTML = '';
            if (r.pumps.length === 0){
              const opt = document.createElement('option');
              opt.value = '';
              opt.textContent = 'No pumps available';
              opt.disabled = true; opt.selected = true;
              doseSel.appendChild(opt);
            } else {
              r.pumps.forEach(p=>{
                const opt = document.createElement('option');
                opt.value = p.key;
                opt.textContent = p.label;
                doseSel.appendChild(opt);
              });
              // Prefer previous selection if still present; else first
              const hasPrev = r.pumps.some(p=>p.key===prev);
              doseSel.value = hasPrev ? prev : r.pumps[0].key;
            }
          }
          // Update current rate display
          const sel = (doseSel && doseSel.value) || (r.pumps[0] && r.pumps[0].key);
          const found = (r.pumps||[]).find(p=>p.key===sel);
          if (doseCur) doseCur.textContent = found? `${Number(found.ml_per_sec||0).toFixed(3)} ml/s` : '—';
        }catch(e){ if (doseCur) doseCur.textContent = '—'; }
      };
  if (doseSel){ doseSel.addEventListener('change', renderPumps); }
  const btnDoseRefresh = qP('#btnDoseRefresh'); if (btnDoseRefresh) btnDoseRefresh.addEventListener('click', renderPumps);
  const btnPrime = qP('#btnDosePrimeToggle');
      let primeMonitorInterval = null;
      async function refreshPrimeState(){
        try{
          const r = await (await fetch('/calib/dose/status?t='+Date.now(), {cache:'no-store'})).json();
          const pump = doseSel && doseSel.value;
          const on = !!(r && r.ok && r.states && r.states[pump]);
          if (btnPrime) btnPrime.textContent = on? 'Stop Priming' : 'Start Priming';
          // Start/stop monitoring based on state
          if (on && !primeMonitorInterval){
            primeMonitorInterval = setInterval(refreshPrimeState, 2000);
          } else if (!on && primeMonitorInterval){
            clearInterval(primeMonitorInterval);
            primeMonitorInterval = null;
          }
          return on;
        }catch(e){ if (btnPrime) btnPrime.textContent = 'Start Priming'; return false; }
      }
      if (btnPrime) btnPrime.addEventListener('click', async ()=>{
        try{
          const pump = doseSel && doseSel.value;
          const on = await refreshPrimeState();
          const ep = on? '/calib/dose/stop' : '/calib/dose/start';
          const r = await (await fetch(`${ep}?pump=${encodeURIComponent(pump)}`, {method:'POST'})).json();
          if (r && r.ok){
            const nowOn = await refreshPrimeState();
            setDoseMsg(nowOn? `Priming ${pump}…` : `Stopped priming ${pump}`);
          } else {
            setDoseMsg((r && r.note) || 'Prime toggle failed', false);
          }
        }catch(e){ setDoseMsg('Prime toggle failed', false); }
      });
      const btnRun = qP('#btnDoseRun'); if (btnRun) btnRun.addEventListener('click', async ()=>{
        try{
          const pump = doseSel && doseSel.value; const sec = parseFloat((qP('#dose-run-sec')||{}).value||'5');
          const r = await (await fetch(`/calib/dose/run?pump=${encodeURIComponent(pump)}&seconds=${encodeURIComponent(sec)}`, {method:'POST'})).json();
          setDoseMsg(r && r.ok? `Running ${pump} for ${r.scheduled_s||sec}s` : (r.note||'Run failed'), !!(r&&r.ok));
        }catch(e){ setDoseMsg('Run failed', false); }
      });
      const btnCommit = qP('#btnDoseCommit'); if (btnCommit) btnCommit.addEventListener('click', async ()=>{
        try{
          const pump = doseSel && doseSel.value; const sec = parseFloat((qP('#dose-run-sec')||{}).value||'5'); const ml = parseFloat((qP('#dose-measured-ml')||{}).value||'0');
          if (!pump || !isFinite(sec) || !isFinite(ml) || sec<=0 || ml<=0){ setDoseMsg('Enter seconds and measured ml', false); return; }
          const rate = ml/sec; setDoseMsg(`Computed ${rate.toFixed(3)} ml/s; saving...`);
          const r = await (await fetch(`/calib/dose/commit?pump=${encodeURIComponent(pump)}&seconds=${encodeURIComponent(sec)}&measured_ml=${encodeURIComponent(ml)}`, {method:'POST'})).json();
          if (r && r.ok){ setDoseMsg(`Saved ${Number(r.rate_ml_per_sec||rate).toFixed(3)} ml/s to ${pump}`); await renderPumps(); }
          else {
            if (r && r.field){ setDoseMsg(`${r.field}: ${r.message||'Invalid'}`, false); }
            else setDoseMsg((r && r.note) || 'Save failed', false);
          }
        }catch(e){ setDoseMsg('Save failed', false); }
      });

      // Prime values on open
      ecStatus(); renderPumps(); refreshPrimeState();
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
      } else if (meta.type === 'select'){
        input = document.createElement('select');
        input.style.cssText = 'margin-left:8px;padding:4px 8px;border-radius:4px;border:1px solid #1f2937;background:#111827;color:#e6edf3;cursor:pointer;';
        if (meta.options && Array.isArray(meta.options)) {
          meta.options.forEach(opt => {
            const option = document.createElement('option');
            option.value = opt;
            option.textContent = opt;
            if (val === opt) option.selected = true;
            input.appendChild(option);
          });
        }
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
      const handleChange = ()=>{
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
      };
      input.addEventListener('input', handleChange);
      if (meta.type === 'select') {
        input.addEventListener('change', handleChange);
      }
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
