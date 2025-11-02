// EC Control UI
(function(){
  const POLL_DEFAULT = 5000;
  let pollMs = POLL_DEFAULT;
  let pollTimer = null;
  lastStatus = null;
  let countdownTimer = null;
  let lastPollAt = Date.now();
  // Recent collapse state
  let recentCollapsed = true;
  let recentHeaderBound = false;

  function el(id){ return document.getElementById(id); }

  async function fetchStatus(){
    try{
      const r = await fetch('/api/ec/status', {cache: 'no-store'});
      if(!r.ok) throw new Error('status');
      return await r.json();
    }catch(e){ return null; }
  }

  function guardActive(g){
    if(!g) return false;
    return g.estop || g.sensor_stale || g.interval || g.daily_cap || g.reservoir || g.mix_lock;
  }

  function guardList(g){
    const out = [];
    if(g.estop) out.push('E-STOP');
    if(g.sensor_stale) out.push('Sensor stale');
    if(g.interval) out.push('Min interval');
    if(g.daily_cap) out.push('Daily cap');
    if(g.reservoir) out.push('Reservoir');
    if(g.mix_lock) out.push('Mix lock');
    return out;
  }

  function guardHints(g){
    const tips = [];
    if(g.estop) tips.push('E-STOP: Emergency stop is active; all dosing blocked.');
    if(g.sensor_stale) tips.push('Sensor stale: EC reading is older than 5 min.');
    if(g.interval) tips.push('Min interval: Waiting between doses.');
    if(g.daily_cap) tips.push('Daily cap reached.');
    if(g.reservoir) tips.push('Reservoir set to 0 L; dosing disabled.');
    if(g.mix_lock) tips.push('pH or EC dose in progress.');
    return tips.join('\n');
  }

  function setRecentCollapsed(collapsed){
    recentCollapsed = !!collapsed;
    const hdr = el('ec-recent-header');
    const list = el('ec-recent');
    if(hdr){ hdr.textContent = recentCollapsed ? 'Recent Doses ▸' : 'Recent Doses ▾'; }
    if(list){ list.style.display = recentCollapsed ? 'none' : 'block'; }
  }

  function renderStatus(s){
    lastStatus = s;
    lastPollAt = Date.now();
    const ecVal = el('ec-current');
    const ppmVal = el('ec-ppm');
    const band = el('ec-band');
    const guards = el('ec-guards');
    const recent = el('ec-recent');
    const resBanner = el('ec-reservoir-banner');
    const cdPill = el('ec-countdown-pill');
    
    if(ecVal){ ecVal.textContent = (s && s.ec_ms_cm!=null) ? s.ec_ms_cm.toFixed(2) : '—'; }
    if(ppmVal){ 
      const ppm = (s && s.ec_ms_cm!=null) ? Math.round(s.ec_ms_cm * 500) : null;
      ppmVal.textContent = ppm!=null ? ppm : '—'; 
    }
    if(band && s){ band.textContent = `Targets ${s.targets.low} – ${s.targets.high} mS/cm`; }
    if(guards && s){
      const list = guardList(s.guards);
      guards.textContent = list.length ? list.join(' · ') : 'All clear';
      guards.style.color = list.length ? '#f59e0b' : '#16a34a';
      guards.title = list.length ? guardHints(s.guards) : '';
    }
    if(resBanner && s){ resBanner.style.display = s.guards?.reservoir ? 'block' : 'none'; }
    if(recent && s){
      recent.innerHTML = '';
      (s.recent||[]).forEach(r => {
        const li = document.createElement('div');
        li.className = 'muted';
        const when = r.ts_utc?.replace('T',' ').replace('Z','');
        const mix = r.mix_ratio || '';
        li.textContent = `${when} • ${r.action} • ${r.volume_ml||''} ml • ${mix} • ${r.result}${r.reason? ' • '+r.reason: ''}`;
        recent.appendChild(li);
      });

      // Bind header click once
      const hdr = el('ec-recent-header');
      if (hdr && !recentHeaderBound){
        recentHeaderBound = true;
        hdr.addEventListener('click', ()=>{
          setRecentCollapsed(!recentCollapsed);
        });
      }
      setRecentCollapsed(recentCollapsed);
    }
    
    // Today total
    const todayEl = el('ec-total-today');
    if(todayEl && s){ todayEl.textContent = `Today: ${(s.today_ml||0).toFixed(1)} ml`; }

    // Determine disabled state
    const g = s?.guards || {};
    const maint = (window.rdwcSettings?.get('safety.maintenance_override')||'false').toLowerCase() === 'true';
    const bypass = maint;
    const blockedCooldown = (g.interval || g.daily_cap) && !bypass;
    const blockedHard = !!(g.estop || g.sensor_stale || g.reservoir || g.mix_lock);
    const disabled = blockedCooldown || blockedHard;
    ['btnEcDose10','btnEcDose50','btnEcDose100','btnEcDoseCustom','ecCustomMl'].forEach(id=>{
      const e = el(id); if(e){ e.disabled = disabled; e.title = disabled ? 'Blocked by guard(s)' : ''; }
    });

    // Maintenance override badge
    const badge = el('ecMaintBadge');
    if (badge) badge.style.display = maint ? 'inline-block' : 'none';

    // Automation toggle button
    const autoBtn = el('btnEcAutoToggle');
    if (autoBtn) {
      const enabled = !!(s && s.auto && s.auto.enabled);
      autoBtn.textContent = enabled ? 'Disable EC automation' : 'Enable EC automation';
      autoBtn.title = 'Automatically raises EC when below target band using G/M/B mix';
    }

    // Automation badges
    const stateBadge = el('ecAutoStateBadge');
    const learnedBadge = el('ecLearnedBadge');
    if (stateBadge && s) {
      const enabled = !!(s.auto && s.auto.enabled);
      if (!enabled) {
        stateBadge.textContent = 'Disabled';
        stateBadge.style.borderColor = 'rgba(148,163,184,.35)';
        stateBadge.style.color = '#cbd5e1';
        stateBadge.style.background = 'rgba(148,163,184,.08)';
        stateBadge.title = '';
      } else {
        const reason = s.auto?.holding_reason;
        if (reason) {
          stateBadge.textContent = `Holding: ${reason}`;
          stateBadge.style.borderColor = 'rgba(251,191,36,.4)';
          stateBadge.style.color = '#fef3c7';
          stateBadge.style.background = 'rgba(251,191,36,.12)';
          stateBadge.title = 'Auto is enabled but holding due to guard';
        } else {
          stateBadge.textContent = 'Active';
          stateBadge.style.borderColor = 'rgba(34,197,94,.4)';
          stateBadge.style.color = '#86efac';
          stateBadge.style.background = 'rgba(34,197,94,.12)';
          stateBadge.title = 'Automation running';
        }
      }
    }
    if (learnedBadge && s) {
      const learned = s.auto?.learned_ml_per_mScm;
      if (learned != null) {
        learnedBadge.textContent = `Learned: ${learned.toFixed(1)} ml/mScm`;
        learnedBadge.style.display = 'inline-block';
      } else {
        learnedBadge.style.display = 'none';
      }
    }
  }

  function startPoll(){
    stopPoll();
    pollTimer = setInterval(async ()=>{
      const s = await fetchStatus();
      if(s) renderStatus(s);
    }, pollMs);
  }

  function stopPoll(){
    if(pollTimer){ clearInterval(pollTimer); pollTimer = null; }
  }

  async function doseEC(ml){
    const mix = document.querySelector('input[name="ecMixRatio"]:checked')?.value || 'schedule';
    const body = { ml, mix_ratio: mix, reason: 'manual' };
    if (mix === 'custom') {
      body.custom = {
        grow: parseFloat(el('ecCustomGrow')?.value || 0),
        micro: parseFloat(el('ecCustomMicro')?.value || 0),
        bloom: parseFloat(el('ecCustomBloom')?.value || 0)
      };
    }
    try{
      const r = await fetch('/api/ec/dose', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      if(!r.ok){
        const e = await r.json();
        showToast(`Dose failed: ${e.error||'unknown'}`, 'error');
        return;
      }
      showToast(`Dosed ${ml} ml`, 'success');
      const s = await fetchStatus();
      if(s) renderStatus(s);
      if(window.ecChart) window.ecChart.refresh();
    }catch(e){
      showToast(`Dose error: ${e.message}`, 'error');
    }
  }

  async function toggleAuto(){
    if(!lastStatus) return;
    const enabled = !!(lastStatus.auto && lastStatus.auto.enabled);
    const body = {enable: !enabled};
    try{
      const r = await fetch('/api/ec/auto', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      if(!r.ok){
        const e = await r.json();
        showToast(`Auto toggle failed: ${e.error||'unknown'}`, 'error');
        return;
      }
      showToast(enabled ? 'EC automation disabled' : 'EC automation enabled', 'success');
      const s = await fetchStatus();
      if(s) renderStatus(s);
    }catch(e){
      showToast(`Auto toggle error: ${e.message}`, 'error');
    }
  }

  function showToast(msg, type){
    if(window.showToast) window.showToast(msg, type);
    else console.log(`[EC] ${type}: ${msg}`);
  }

  // Custom ratio toggle
  function setupMixRatioToggle(){
    const radios = document.querySelectorAll('input[name="ecMixRatio"]');
    const customDiv = el('ec-custom-ratio');
    radios.forEach(r => {
      r.addEventListener('change', ()=>{
        if(customDiv) customDiv.style.display = (r.value === 'custom' && r.checked) ? 'block' : 'none';
      });
    });
  }

  // Initialize
  async function init(){
    const s = await fetchStatus();
    if(s) renderStatus(s);
    startPoll();
    setupMixRatioToggle();

    // Dose buttons
    el('btnEcDose10')?.addEventListener('click', ()=>doseEC(10));
    el('btnEcDose50')?.addEventListener('click', ()=>doseEC(50));
    el('btnEcDose100')?.addEventListener('click', ()=>doseEC(100));
    el('btnEcDoseCustom')?.addEventListener('click', ()=>{
      const ml = parseFloat(el('ecCustomMl')?.value || 0);
      if(ml > 0) doseEC(ml);
    });
    el('btnEcAutoToggle')?.addEventListener('click', toggleAuto);

    // Settings save
    el('btnSaveEcSettings')?.addEventListener('click', async ()=>{
      const payload = {
        'targets.ec_low': el('ecTargetLow')?.value,
        'targets.ec_high': el('ecTargetHigh')?.value,
        'dosing.grow_ml_per_sec': el('ecGrowMlPerSec')?.value,
        'dosing.micro_ml_per_sec': el('ecMicroMlPerSec')?.value,
        'dosing.bloom_ml_per_sec': el('ecBloomMlPerSec')?.value,
        'dosing.ec_step_ml_min': el('ecStepMinMl')?.value,
        'dosing.ec_step_ml_max': el('ecStepMaxMl')?.value,
        'dosing.ec_safety_factor': el('ecSafetyFactor')?.value,
        'dosing.ec_min_interval_s': el('ecMinInterval')?.value,
        'dosing.ec_max_ml_day': el('ecMaxMlDay')?.value
      };
      try{
        const r = await fetch('/api/settings', {
          method: 'PUT',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });
        if(!r.ok){
          const e = await r.json();
          showToast(`Save failed: ${e.error||e.message||'unknown'}`, 'error');
          return;
        }
        showToast('EC settings saved', 'success');
        const s = await fetchStatus();
        if(s) renderStatus(s);
      }catch(e){
        showToast(`Save error: ${e.message}`, 'error');
      }
    });
  }

  // Load settings into UI
  async function loadECSettings(){
    if(!window.rdwcSettings) return;
    el('ecTargetLow').value = window.rdwcSettings.get('targets.ec_low') || '0.8';
    el('ecTargetHigh').value = window.rdwcSettings.get('targets.ec_high') || '1.2';
    el('ecGrowMlPerSec').value = window.rdwcSettings.get('dosing.grow_ml_per_sec') || '25';
    el('ecMicroMlPerSec').value = window.rdwcSettings.get('dosing.micro_ml_per_sec') || '25';
    el('ecBloomMlPerSec').value = window.rdwcSettings.get('dosing.bloom_ml_per_sec') || '25';
    el('ecStepMinMl').value = window.rdwcSettings.get('dosing.ec_step_ml_min') || '10';
    el('ecStepMaxMl').value = window.rdwcSettings.get('dosing.ec_step_ml_max') || '120';
    el('ecSafetyFactor').value = window.rdwcSettings.get('dosing.ec_safety_factor') || '0.6';
    el('ecMinInterval').value = window.rdwcSettings.get('dosing.ec_min_interval_s') || '300';
    el('ecMaxMlDay').value = window.rdwcSettings.get('dosing.ec_max_ml_day') || '0';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ()=>{
      loadECSettings();
      init();
    });
  } else {
    loadECSettings();
    init();
  }

  window.ecController = { init, fetchStatus, renderStatus, doseEC, toggleAuto };
})();
