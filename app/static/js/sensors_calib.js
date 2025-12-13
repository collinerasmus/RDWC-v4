/* Sensors Calibration - Pump calibration workflow */
(function(){
  const $ = (id) => document.getElementById(id);
  
  // Pump calibration state
  let pumpRates = {
    ph: 0,
    grow: 0,
    micro: 0,
    bloom: 0
  };

  // Map UI pump names to backend pump keys
  const pumpKeyMap = {
    ph: 'ph_up',
    grow: 'grow',
    micro: 'micro',
    bloom: 'bloom'
  };

  const toBackendPump = (pumpName) => pumpKeyMap[pumpName] || pumpName;
  
  // Fetch current pump rates
  async function fetchPumpRates() {
    try {
      const r = await fetch('/calib/dose/pumps', {cache:'no-store'});
      if (!r.ok) return;
      const data = await r.json();
      if (data && Array.isArray(data.pumps)) {
        // Reset
        pumpRates = { ph:0, grow:0, micro:0, bloom:0 };
        for (const p of data.pumps) {
          const k = p.key; const rate = typeof p.ml_per_sec === 'number' ? p.ml_per_sec : 0;
          if (k === 'ph_up') pumpRates.ph = rate;
          else if (k === 'grow') pumpRates.grow = rate;
          else if (k === 'micro') pumpRates.micro = rate;
          else if (k === 'bloom') pumpRates.bloom = rate;
        }
        updatePumpRateDisplays();
      }
    } catch(e) {
      console.error('[Sensors Calib] Failed to fetch pump rates:', e);
    }
  }
  
  function updatePumpRateDisplays() {
    const displays = {
      ph: $('ph-pump-rate'),
      grow: $('grow-pump-rate'),
      micro: $('micro-pump-rate'),
      bloom: $('bloom-pump-rate')
    };
    
    for (const [pump, el] of Object.entries(displays)) {
      if (el) {
        const rate = pumpRates[pump];
        el.textContent = rate > 0 ? `${rate.toFixed(3)} ml/s` : 'Not calibrated';
      }
    }
  }
  
  // Prime pump (3s purge)
  async function primePump(pumpName) {
    try {
      const btn = $(`${pumpName}-pump-prime`);
      if (btn) btn.disabled = true;
      const backendPump = toBackendPump(pumpName);
      const primeSeconds = 3.0;
      const r = await fetch(`/calib/dose/prime?pump=${encodeURIComponent(backendPump)}&seconds=${primeSeconds}`, {
        method: 'POST'
      });
      
      if (r.ok) {
        const data = await r.json();
        if (data.ok) {
          showToast(`${pumpName.toUpperCase()} pump primed (3s)`, 'success');
        } else {
          showToast(`Prime failed: ${data.note || data.error || 'Unknown error'}`, 'error');
        }
      } else {
        showToast(`Prime failed: HTTP ${r.status}`, 'error');
      }
    } catch(e) {
      console.error(`[Sensors Calib] Prime ${pumpName} failed:`, e);
      showToast(`Prime error: ${e.message}`, 'error');
    } finally {
      const btn = $(`${pumpName}-pump-prime`);
      if (btn) btn.disabled = false;
    }
  }
  
  // Run calibration
  async function runCalibration(pumpName) {
    try {
      const durationEl = $(`${pumpName}-pump-duration`);
      const btn = $(`${pumpName}-pump-run`);
      
      if (!durationEl) {
        showToast('Duration input not found', 'error');
        return;
      }
      
      const duration = parseFloat(durationEl.value);
      if (isNaN(duration) || duration < 0.2 || duration > 10) {
        showToast('Duration must be between 0.2 and 10 seconds', 'error');
        return;
      }
      
      if (btn) btn.disabled = true;
      const backendPump = toBackendPump(pumpName);
      const r = await fetch(`/calib/dose/run?pump=${encodeURIComponent(backendPump)}&seconds=${duration}`, {
        method: 'POST'
      });
      
      if (r.ok) {
        const data = await r.json();
        if (data.ok) {
          showToast(`${pumpName.toUpperCase()} pump ran for ${duration}s. Measure output and commit.`, 'success');
        } else {
          const msg = data.note || data.error || 'Unknown error';
          showToast(`Run failed: ${msg}`, 'error');
        }
      } else {
        showToast(`Run failed: HTTP ${r.status}`, 'error');
      }
    } catch(e) {
      console.error(`[Sensors Calib] Run ${pumpName} failed:`, e);
      showToast(`Run error: ${e.message}`, 'error');
    } finally {
      const btn = $(`${pumpName}-pump-run`);
      if (btn) btn.disabled = false;
    }
  }
  
  // Commit measured rate
  async function commitRate(pumpName) {
    try {
      const durationEl = $(`${pumpName}-pump-duration`);
      const measuredEl = $(`${pumpName}-pump-measured`);
      const btn = $(`${pumpName}-pump-commit`);
      
      if (!durationEl || !measuredEl) {
        showToast('Input fields not found', 'error');
        return;
      }
      
      const duration = parseFloat(durationEl.value);
      const measured = parseFloat(measuredEl.value);
      
      if (isNaN(duration) || duration < 0.2 || duration > 10) {
        showToast('Duration must be between 0.2 and 10 seconds', 'error');
        return;
      }
      
      if (isNaN(measured) || measured <= 0) {
        showToast('Measured volume must be greater than 0', 'error');
        return;
      }
      
      if (btn) btn.disabled = true;
      const backendPump = toBackendPump(pumpName);
      const r = await fetch(`/calib/dose/commit?pump=${encodeURIComponent(backendPump)}&seconds=${duration}&measured_ml=${measured}`, {
        method: 'POST'
      });
      
      if (r.ok) {
        const data = await r.json();
        if (data.ok) {
          const rate = data.rate_ml_per_sec || (measured / duration);
          pumpRates[pumpName] = rate;
          updatePumpRateDisplays();
          showToast(`${pumpName.toUpperCase()} pump rate saved: ${rate.toFixed(3)} ml/s`, 'success');
        } else {
          showToast(`Commit failed: ${data.note || data.error || 'Unknown error'}`, 'error');
        }
      } else {
        showToast(`Commit failed: HTTP ${r.status}`, 'error');
      }
    } catch(e) {
      console.error(`[Sensors Calib] Commit ${pumpName} failed:`, e);
      showToast(`Commit error: ${e.message}`, 'error');
    } finally {
      const btn = $(`${pumpName}-pump-commit`);
      if (btn) btn.disabled = false;
    }
  }
  
  // Toast notification helper
  function showToast(message, type = 'info') {
    if (window.showToast) {
      window.showToast(message, type);
    } else {
      console.log(`[Toast ${type}] ${message}`);
    }
  }
  
  // Initialize
  function init() {
    // Wire up pH pump buttons
    const phPrime = $('ph-pump-prime');
    const phRun = $('ph-pump-run');
    const phCommit = $('ph-pump-commit');
    
    if (phPrime) phPrime.onclick = () => primePump('ph');
    if (phRun) phRun.onclick = () => runCalibration('ph');
    if (phCommit) phCommit.onclick = () => commitRate('ph');
    
    // Wire up EC pump buttons (grow, micro, bloom)
    ['grow', 'micro', 'bloom'].forEach(pump => {
      const prime = $(`${pump}-pump-prime`);
      const run = $(`${pump}-pump-run`);
      const commit = $(`${pump}-pump-commit`);
      
      if (prime) prime.onclick = () => primePump(pump);
      if (run) run.onclick = () => runCalibration(pump);
      if (commit) commit.onclick = () => commitRate(pump);
    });
    
    // Fetch initial pump rates
    fetchPumpRates();
  }
  
  // Export functions
  window.sensorsCalib = {
    init,
    fetchPumpRates,
    primePump,
    runCalibration,
    commitRate
  };
  
  // Auto-initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
