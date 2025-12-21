// Controller-specific settings UI and sync
(function(){
  'use strict';

  // Shared helper to fetch settings with proper error handling
  async function fetchSettingsSafe(){
    const res = await fetch('/api/settings');
    if (!res.ok){
      const text = await res.text();
      throw new Error(`settings ${res.status}: ${text?.slice?.(0,200) || text}`);
    }
    return res.json();
  }

  // pH Controller Settings
  function initPhSettings(){
    const btn = document.getElementById('btnSavePhSettings');
    if (!btn) return;
    
    // Load current settings
    async function loadPhSettings(){
      try {
        const settings = await fetchSettingsSafe();
        
        // Helper to safely set element value
        const setVal = (id, val) => {
          const el = document.getElementById(id);
          if (el && val !== undefined && val !== null && !isNaN(val)) el.value = val;
        };
        
        // Target range
        if (settings.targets) {
          setVal('phTargetLow', parseFloat(settings.targets.ph_low));
           setVal('phBand', parseFloat(settings.targets.ph_band ?? '0.2'));
        }
        
        // Dosing parameters
        if (settings.dosing) {
          setVal('phPulseGrow', parseFloat(settings.dosing.pulse_ml_grow));
          setVal('phPulseMicro', parseFloat(settings.dosing.pulse_ml_micro));
          setVal('phPulseBloom', parseFloat(settings.dosing.pulse_ml_bloom));
          setVal('phMaxMlHour', parseFloat(settings.dosing.max_ml_hour_));
          setVal('phMaxMlDay', parseFloat(settings.dosing.max_ml_day_));
          setVal('phMixDelay', parseInt(settings.dosing.mix_delay_s));
          setVal('phUpMlPerSec', parseFloat(settings.dosing.ph_up_ml_per_sec));
        }
        
        // Alerts
        if (settings.alerts) {
          setVal('phAlertLow', parseFloat(settings.alerts.ph_lo_alert));
          setVal('phAlertHigh', parseFloat(settings.alerts.ph_hi_alert));
        }
      } catch(e) {
        console.error('Failed to load pH settings:', e);
      }
    }
    
    // Save pH settings
    async function savePhSettings(){
      const btn = document.getElementById('btnSavePhSettings');
      if (!btn) return;
      
      // Helper to safely get element value
      const getVal = (id, def = 0) => {
        const el = document.getElementById(id);
        return el ? parseFloat(el.value) || def : def;
      };
      
      // Validation
      const phLow = getVal('phTargetLow', 5.8);
      const phBand = getVal('phBand', 0.2);
      const phHigh = phLow + (phBand * 2); // derive symmetric band around midpoint
      if (phBand <= 0) {
        alert('Error: pH band must be greater than 0');
        return;
      }
      
      const updates = {
        'targets.ph_low': phLow,
        'targets.ph_high': phHigh,
        'targets.ph_band': phBand.toFixed(2),
        'dosing.pulse_ml_grow': getVal('phPulseGrow'),
        'dosing.pulse_ml_micro': getVal('phPulseMicro'),
        'dosing.pulse_ml_bloom': getVal('phPulseBloom'),
        'dosing.max_ml_hour_': getVal('phMaxMlHour'),
        'dosing.max_ml_day_': getVal('phMaxMlDay'),
        'dosing.mix_delay_s': parseInt(document.getElementById('phMixDelay')?.value) || 0,
        'dosing.ph_up_ml_per_sec': getVal('phUpMlPerSec', 0.83),
        'alerts.ph_lo_alert': getVal('phAlertLow'),
        'alerts.ph_hi_alert': getVal('phAlertHigh')
      };
      
      // Show loading state
      btn.classList.add('btn-loading');
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = 'Saving...';
      
      try {
        const res = await fetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updates)
        });
        if (res.ok) {
          // Success feedback
          btn.textContent = '✓ Saved';
          btn.classList.remove('btn-loading');
          btn.classList.add('success-feedback');
          
          // Update pH band display
          const band = document.getElementById('ph-band');
          if (band) band.textContent = `Targets ${phLow.toFixed(1)} – ${phHigh.toFixed(1)}`;
          
          // Reset button after 2s
          setTimeout(() => {
            btn.textContent = originalText;
            btn.disabled = false;
            btn.classList.remove('success-feedback');
          }, 2000);
        } else {
          let msg = 'Save failed';
          try { const j = await res.json(); if (j && (j.message || j.field)) { msg = `${j.field || ''} ${j.message || ''}`.trim(); } } catch(_){}
          if (window.showToast) window.showToast(`pH settings: ${msg}`, 'error');
          throw new Error(msg);
        }
      } catch(e) {
        console.error('Failed to save pH settings:', e);
        btn.classList.remove('btn-loading');
        btn.textContent = '✗ Failed';
        if (window.showToast) window.showToast(`pH settings: ${e.message || 'Save failed'}`, 'error');
        setTimeout(() => {
          btn.textContent = originalText;
          btn.disabled = false;
        }, 2000);
      }
    }
    
    btn.addEventListener('click', savePhSettings);
    loadPhSettings();
  }

  // EC Controller Settings
  function initEcSettings(){
    const btn = document.getElementById('btnSaveEcSettings');
    if (!btn) return;
    
    async function loadEcSettings(){
      try {
        const settings = await fetchSettingsSafe();
        
        // Helper to safely set element value
        const setVal = (id, val) => {
          const el = document.getElementById(id);
          if (el && val !== undefined && val !== null && !isNaN(val)) el.value = val;
        };
        
        if (settings.targets) {
          // Target comes strictly from scheduler; do not expose here
          if (document.getElementById('ecTolerance')) {
            setVal('ecTolerance', parseFloat(settings.targets.ec_tolerance));
          }
        }
        if (settings.alerts) {
          setVal('ecAlertLow', parseFloat(settings.alerts.ec_lo_alert));
          setVal('ecAlertHigh', parseFloat(settings.alerts.ec_hi_alert));
        }
      } catch(e) {
        console.error('Failed to load EC settings:', e);
      }
    }
    
    async function saveEcSettings(){
      const btn = document.getElementById('btnSaveEcSettings');
      if (!btn) return;
      
      // Helper to safely get element value
      const getVal = (id, def = 0) => {
        const el = document.getElementById(id);
        return el ? parseFloat(el.value) || def : def;
      };
      
      const ecTolerance = getVal('ecTolerance');
      
      const updates = {
        'targets.ec_tolerance': ecTolerance.toFixed(2)
      };
      
      // Only save alerts if fields exist
      if (document.getElementById('ecAlertLow')) {
        updates['alerts.ec_lo_alert'] = getVal('ecAlertLow').toFixed(2);
      }
      if (document.getElementById('ecAlertHigh')) {
        updates['alerts.ec_hi_alert'] = getVal('ecAlertHigh').toFixed(2);
      }
      
      btn.classList.add('btn-loading');
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = 'Saving...';
      
      try {
        const res = await fetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updates)
        });
        if (res.ok) {
          btn.textContent = '✓ Saved';
          btn.classList.remove('btn-loading');
          btn.classList.add('success-feedback');
          
          const chip = document.getElementById('ecSchedulerTargetChip');
          if (chip && window.lastEcStatus && window.lastEcStatus.targets) {
            const low = window.lastEcStatus.targets.low;
            const high = window.lastEcStatus.targets.high;
            chip.textContent = `Target: ${low?.toFixed?.(1)}–${high?.toFixed?.(1)} mS/cm`;
          }
          
          setTimeout(() => {
            btn.textContent = originalText;
            btn.disabled = false;
            btn.classList.remove('success-feedback');
          }, 2000);
        } else {
          let msg = 'Save failed';
          try { const j = await res.json(); if (j && (j.message || j.field)) { msg = `${j.field || ''} ${j.message || ''}`.trim(); } } catch(_){}
          if (window.showToast) window.showToast(`EC settings: ${msg}`, 'error');
          throw new Error(msg);
        }
      } catch(e) {
        console.error('Failed to save EC settings:', e);
        btn.classList.remove('btn-loading');
        btn.textContent = '✗ Failed';
        if (window.showToast) window.showToast(`EC settings: ${e.message || 'Save failed'}`, 'error');
        setTimeout(() => {
          btn.textContent = originalText;
          btn.disabled = false;
        }, 2000);
      }
    }
    
    btn.addEventListener('click', saveEcSettings);
    loadEcSettings();
  }

  // Temperature Controller Settings
  function initTempSettings(){
    const btn = document.getElementById('btnSaveTempSettings');
    if (!btn) return;
    
    async function loadTempSettings(){
      try {
        const settings = await fetchSettingsSafe();
        
        if (settings.temperature) {
          if (settings.temperature.hysteresis !== undefined) document.getElementById('temperatureHysteresis').value = parseFloat(settings.temperature.hysteresis);
        }
        if (settings.alerts) {
          if (settings.alerts.temp_lo_alert !== undefined) document.getElementById('tempAlertLow').value = parseFloat(settings.alerts.temp_lo_alert);
          if (settings.alerts.temp_hi_alert !== undefined) document.getElementById('tempAlertHigh').value = parseFloat(settings.alerts.temp_hi_alert);
        }
        if (settings.safety) {
          if (settings.safety.temperature_min_off_s !== undefined) document.getElementById('temperatureMinOff').value = parseInt(settings.safety.temperature_min_off_s);
          if (settings.safety.temperature_min_on_s !== undefined) document.getElementById('temperatureMinOn').value = parseInt(settings.safety.temperature_min_on_s);
        }
      } catch(e) {
        console.error('Failed to load temperature settings:', e);
      }
    }
    
    async function saveTempSettings(){
      const btn = document.getElementById('btnSaveTempSettings');
      if (!btn) return;
      
      const hysteresis = parseFloat(document.getElementById('temperatureHysteresis').value) || 0.6;
      
      const updates = {
        'temperature.hysteresis': hysteresis,
        'alerts.temp_lo_alert': parseFloat(document.getElementById('tempAlertLow').value) || 0,
        'alerts.temp_hi_alert': parseFloat(document.getElementById('tempAlertHigh').value) || 0,
        'safety.temperature_min_off_s': parseInt(document.getElementById('temperatureMinOff').value) || 300,
        'safety.temperature_min_on_s': parseInt(document.getElementById('temperatureMinOn').value) || 60
      };
      
      btn.classList.add('btn-loading');
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = 'Saving...';
      
      try {
        const res = await fetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updates)
        });
        if (res.ok) {
          btn.textContent = '✓ Saved';
          btn.classList.remove('btn-loading');
          btn.classList.add('success-feedback');
          
          const targetDisplay = document.getElementById('chiller-target-temp');
          if (targetDisplay) targetDisplay.textContent = `${tempTarget.toFixed(1)}°C`;
          
          // Reload settings from backend to ensure form reflects saved values
          setTimeout(() => {
            loadTempSettings();
          }, 100);
          
          setTimeout(() => {
            btn.textContent = originalText;
            btn.disabled = false;
            btn.classList.remove('success-feedback');
          }, 2000);
        } else {
          let msg = 'Save failed';
          try { const j = await res.json(); if (j && (j.message || j.field)) { msg = `${j.field || ''} ${j.message || ''}`.trim(); } } catch(_){}
          if (window.showToast) window.showToast(`Temperature settings: ${msg}`, 'error');
          throw new Error(msg);
        }
      } catch(e) {
        console.error('Failed to save temperature settings:', e);
        btn.classList.remove('btn-loading');
        btn.textContent = '✗ Failed';
        if (window.showToast) window.showToast(`Temperature settings: ${e.message || 'Save failed'}`, 'error');
        setTimeout(() => {
          btn.textContent = originalText;
          btn.disabled = false;
        }, 2000);
      }
    }
    
    btn.addEventListener('click', saveTempSettings);
    loadTempSettings();
  }

  // Circulation Controller Settings
  function initCircSettings(){
    const btn = document.getElementById('btnSaveCircSettings');
    if (!btn) return;
    
    async function loadCircSettings(){
      try {
        const settings = await fetchSettingsSafe();
        
        if (settings.safety) {
          if (settings.safety.main_pump_min_off_s !== undefined) document.getElementById('mainPumpMinOff').value = parseInt(settings.safety.main_pump_min_off_s);
          if (settings.safety.chiller_pump_min_off_s !== undefined) document.getElementById('temperaturePumpMinOff').value = parseInt(settings.safety.chiller_pump_min_off_s);
        }
      } catch(e) {
        console.error('Failed to load circulation settings:', e);
      }
    }
    
    async function saveCircSettings(){
      const btn = document.getElementById('btnSaveCircSettings');
      if (!btn) return;
      
      const updates = {
        'safety.main_pump_min_off_s': parseInt(document.getElementById('mainPumpMinOff').value) || 5,
        'safety.chiller_pump_min_off_s': parseInt(document.getElementById('temperaturePumpMinOff').value) || 5
      };
      
      btn.classList.add('btn-loading');
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = 'Saving...';
      
      try {
        const res = await fetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updates)
        });
        if (res.ok) {
          btn.textContent = '✓ Saved';
          btn.classList.remove('btn-loading');
          btn.classList.add('success-feedback');
          
          setTimeout(() => {
            btn.textContent = originalText;
            btn.disabled = false;
            btn.classList.remove('success-feedback');
          }, 2000);
        } else {
          let msg = 'Save failed';
          try { const j = await res.json(); if (j && (j.message || j.field)) { msg = `${j.field || ''} ${j.message || ''}`.trim(); } } catch(_){}
          if (window.showToast) window.showToast(`Circulation settings: ${msg}`, 'error');
          throw new Error(msg);
        }
      } catch(e) {
        console.error('Failed to save circulation settings:', e);
        btn.classList.remove('btn-loading');
        btn.textContent = '✗ Failed';
        if (window.showToast) window.showToast(`Circulation settings: ${e.message || 'Save failed'}`, 'error');
        setTimeout(() => {
          btn.textContent = originalText;
          btn.disabled = false;
        }, 2000);
      }
    }
    
    btn.addEventListener('click', saveCircSettings);
    loadCircSettings();
  }

  // Initialize all controller settings
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function(){
      initPhSettings();
      initEcSettings();
      initTempSettings();
      initCircSettings();
    });
  } else {
    initPhSettings();
    initEcSettings();
    initTempSettings();
    initCircSettings();
  }
})();

