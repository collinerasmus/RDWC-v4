// Controller-specific settings UI and sync
(function(){
  'use strict';

  // pH Controller Settings
  function initPhSettings(){
    const btn = document.getElementById('btnSavePhSettings');
    if (!btn) return;
    
    // Load current settings
    async function loadPhSettings(){
      try {
        const res = await fetch('/api/settings');
        const settings = await res.json();
        
        // Target range
        if (settings.targets && settings.targets.ph_low !== undefined) {
          document.getElementById('phTargetLow').value = parseFloat(settings.targets.ph_low);
        }
        if (settings.targets && settings.targets.ph_high !== undefined) {
          document.getElementById('phTargetHigh').value = parseFloat(settings.targets.ph_high);
        }
        
        // Dosing parameters
        if (settings.dosing) {
          if (settings.dosing.pulse_ml_grow !== undefined) document.getElementById('phPulseGrow').value = parseFloat(settings.dosing.pulse_ml_grow);
          if (settings.dosing.pulse_ml_micro !== undefined) document.getElementById('phPulseMicro').value = parseFloat(settings.dosing.pulse_ml_micro);
          if (settings.dosing.pulse_ml_bloom !== undefined) document.getElementById('phPulseBloom').value = parseFloat(settings.dosing.pulse_ml_bloom);
          if (settings.dosing.max_ml_hour_ !== undefined) document.getElementById('phMaxMlHour').value = parseFloat(settings.dosing.max_ml_hour_);
          if (settings.dosing.max_ml_day_ !== undefined) document.getElementById('phMaxMlDay').value = parseFloat(settings.dosing.max_ml_day_);
          if (settings.dosing.mix_delay_s !== undefined) document.getElementById('phMixDelay').value = parseInt(settings.dosing.mix_delay_s);
          if (settings.dosing.ph_up_ml_per_sec !== undefined) document.getElementById('phUpMlPerSec').value = parseFloat(settings.dosing.ph_up_ml_per_sec);
        }
        
        // Alerts
        if (settings.alerts) {
          if (settings.alerts.ph_lo_alert !== undefined) document.getElementById('phAlertLow').value = parseFloat(settings.alerts.ph_lo_alert);
          if (settings.alerts.ph_hi_alert !== undefined) document.getElementById('phAlertHigh').value = parseFloat(settings.alerts.ph_hi_alert);
        }
      } catch(e) {
        console.error('Failed to load pH settings:', e);
      }
    }
    
    // Save pH settings
    async function savePhSettings(){
      const btn = document.getElementById('btnSavePhSettings');
      if (!btn) return;
      
      // Validation
      const phLow = parseFloat(document.getElementById('phTargetLow').value);
      const phHigh = parseFloat(document.getElementById('phTargetHigh').value);
      if (phLow >= phHigh) {
        alert('Error: pH Low must be less than pH High');
        return;
      }
      
      const updates = {
        'targets.ph_low': phLow,
        'targets.ph_high': phHigh,
        'dosing.pulse_ml_grow': parseFloat(document.getElementById('phPulseGrow').value) || 0,
        'dosing.pulse_ml_micro': parseFloat(document.getElementById('phPulseMicro').value) || 0,
        'dosing.pulse_ml_bloom': parseFloat(document.getElementById('phPulseBloom').value) || 0,
        'dosing.max_ml_hour_': parseFloat(document.getElementById('phMaxMlHour').value) || 0,
        'dosing.max_ml_day_': parseFloat(document.getElementById('phMaxMlDay').value) || 0,
        'dosing.mix_delay_s': parseInt(document.getElementById('phMixDelay').value) || 0,
        'dosing.ph_up_ml_per_sec': parseFloat(document.getElementById('phUpMlPerSec').value) || 0.83,
        'alerts.ph_lo_alert': parseFloat(document.getElementById('phAlertLow').value) || 0,
        'alerts.ph_hi_alert': parseFloat(document.getElementById('phAlertHigh').value) || 0
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
        const res = await fetch('/api/settings');
        const settings = await res.json();
        
        if (settings.targets) {
          if (settings.targets.ec_target !== undefined) document.getElementById('ecTarget').value = parseFloat(settings.targets.ec_target) * 1000; // Convert mS/cm to ppm
          if (settings.targets.ec_tolerance !== undefined) document.getElementById('ecTolerance').value = parseFloat(settings.targets.ec_tolerance) * 1000;
        }
        if (settings.alerts) {
          if (settings.alerts.ec_lo_alert !== undefined) document.getElementById('ecAlertLow').value = parseFloat(settings.alerts.ec_lo_alert) * 1000;
          if (settings.alerts.ec_hi_alert !== undefined) document.getElementById('ecAlertHigh').value = parseFloat(settings.alerts.ec_hi_alert) * 1000;
        }
      } catch(e) {
        console.error('Failed to load EC settings:', e);
      }
    }
    
    async function saveEcSettings(){
      const btn = document.getElementById('btnSaveEcSettings');
      if (!btn) return;
      
      const ecTarget = (parseFloat(document.getElementById('ecTarget').value) || 0) / 1000;
      const ecTolerance = (parseFloat(document.getElementById('ecTolerance').value) || 0) / 1000;
      
      const updates = {
        'targets.ec_target': ecTarget.toFixed(2),
        'targets.ec_tolerance': ecTolerance.toFixed(2),
        'alerts.ec_lo_alert': ((parseFloat(document.getElementById('ecAlertLow').value) || 0) / 1000).toFixed(2),
        'alerts.ec_hi_alert': ((parseFloat(document.getElementById('ecAlertHigh').value) || 0) / 1000).toFixed(2)
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
          
          const band = document.getElementById('ec-band');
          if (band) band.textContent = `Target: ${ecTarget.toFixed(1)} ±${ecTolerance.toFixed(1)} mS/cm`;
          
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
        const res = await fetch('/api/settings');
        const settings = await res.json();
        
        if (settings.targets && settings.targets.temp_target_c !== undefined) {
          document.getElementById('tempTarget').value = parseFloat(settings.targets.temp_target_c);
        }
        if (settings.alerts) {
          if (settings.alerts.temp_lo_alert !== undefined) document.getElementById('tempAlertLow').value = parseFloat(settings.alerts.temp_lo_alert);
          if (settings.alerts.temp_hi_alert !== undefined) document.getElementById('tempAlertHigh').value = parseFloat(settings.alerts.temp_hi_alert);
        }
        if (settings.safety) {
          if (settings.safety.chiller_min_off_s !== undefined) document.getElementById('chillerMinOff').value = parseInt(settings.safety.chiller_min_off_s);
          if (settings.safety.chiller_min_on_s !== undefined) document.getElementById('chillerMinOn').value = parseInt(settings.safety.chiller_min_on_s);
        }
      } catch(e) {
        console.error('Failed to load temperature settings:', e);
      }
    }
    
    async function saveTempSettings(){
      const btn = document.getElementById('btnSaveTempSettings');
      if (!btn) return;
      
      const tempTarget = parseFloat(document.getElementById('tempTarget').value) || 19;
      
      const updates = {
        'targets.temp_target_c': tempTarget,
        'alerts.temp_lo_alert': parseFloat(document.getElementById('tempAlertLow').value) || 0,
        'alerts.temp_hi_alert': parseFloat(document.getElementById('tempAlertHigh').value) || 0,
        'safety.chiller_min_off_s': parseInt(document.getElementById('chillerMinOff').value) || 300,
        'safety.chiller_min_on_s': parseInt(document.getElementById('chillerMinOn').value) || 60
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
        const res = await fetch('/api/settings');
        const settings = await res.json();
        
        if (settings.safety) {
          if (settings.safety.main_pump_min_off_s !== undefined) document.getElementById('mainPumpMinOff').value = parseInt(settings.safety.main_pump_min_off_s);
          if (settings.safety.chiller_pump_min_off_s !== undefined) document.getElementById('chillerPumpMinOff').value = parseInt(settings.safety.chiller_pump_min_off_s);
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
        'safety.chiller_pump_min_off_s': parseInt(document.getElementById('chillerPumpMinOff').value) || 5
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
