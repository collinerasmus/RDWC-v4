// Calibration Tab UI
// Wires up the dedicated Calibration tab (separate from pH/EC inline calibration)
(function(){
  function el(id){ return document.getElementById(id); }

  // pH Calibration functions
  function phSetMsg(msg, append = false, style = null) {
    const msgEl = el('ph-calib-msg');
    const logEl = el('ph-calib-log');
    if (msgEl) {
      msgEl.textContent = msg;
      msgEl.style.color = style === 'success' ? '#10b981' : style === 'warn' ? '#f59e0b' : '';
    }
    if (append && logEl) {
      const line = document.createElement('div');
      line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
      if (style === 'success') line.style.color = '#10b981';
      if (style === 'warn') line.style.color = '#f59e0b';
      logEl.appendChild(line);
      logEl.scrollTop = logEl.scrollHeight;
    }
  }

  function phSetCurrent(val) {
    const sp = el('ph-current-value');
    if (sp) {
      sp.textContent = Number(val).toFixed(2);
      // Color code based on target range (simplified - should fetch from settings)
      const low = 5.8, high = 6.2;
      if (val < low - 0.05) sp.style.color = '#f87171'; // low = red
      else if (val > high + 0.05) sp.style.color = '#f87171'; // high = red
      else sp.style.color = '#34d399'; // in band
    }
  }

  function phSetBanner(on) {
    const b = el('ph-calib-banner');
    if (b) b.style.display = on ? 'block' : 'none';
  }

  // Disable/enable all pH calibration action buttons during operations
  const phCalibBtnIds = [
    'btnPhRead', 'btnPhStabilize', 'btnPhStatus',
    'btnPhCalibrate', 'btnPhClear',
    'btnLedsOn', 'btnLedsOff', 'btnLedsBlink'
  ];

  function phSetCalibBusy(busy, workingLabel) {
    phCalibBtnIds.forEach(id => {
      const b = el(id);
      if (!b) return;
      if (busy) {
        b.disabled = true;
        if (workingLabel && id === 'btnPhCalibrate') {
          b.dataset._orig = b.textContent;
          b.textContent = workingLabel;
        }
      } else {
        b.disabled = false;
        if (b.dataset._orig) {
          b.textContent = b.dataset._orig;
          delete b.dataset._orig;
        }
      }
    });
    if (busy) phSetMsg('⏳ Working...', true, 'warn');
  }

  async function phCheckCaps() {
    try {
      const r = await (await fetch('/calib/ph/caps?t=' + Date.now(), { cache: 'no-store' })).json();
      phSetBanner(!(r && r.enabled));
    } catch (e) { /* noop */ }
  }

  // pH Read button
  el('btnPhRead')?.addEventListener('click', async () => {
    phSetCalibBusy(true);
    try {
      phSetMsg('Reading (waits for sensor poller to pause, ~8s)...');
      const resp = await fetch('/calib/ph/read?t=' + Date.now(), { cache: 'no-store' });
      const r = await resp.json();
      if (r && r.ok) {
        phSetCurrent(r.value);
        phSetMsg(`pH: ${Number(r.value).toFixed(2)}`, true, 'success');
      } else {
        const hint = (r && r.note === 'NoData')
          ? 'NoData — probe not responding. Check: 1) sensor power relay ON, 2) I²C wiring, 3) /fix_ezo to verify address 0x63.'
          : ((r && r.note) || 'Read failed');
        phSetMsg(hint, false);
      }
    } catch (e) {
      phSetMsg(`Read failed (network): ${e.message}`, false);
    } finally {
      phSetCalibBusy(false);
    }
  });

  // pH Stabilize button
  el('btnPhStabilize')?.addEventListener('click', async () => {
    phSetCalibBusy(true);
    try {
      phSetMsg('Waiting for stable reading...');
      const resp = await fetch('/calib/ph/read_stable?t=' + Date.now(), { cache: 'no-store' });
      const r = await resp.json();
      if (r && r.ok) {
        phSetCurrent(r.value);
        phSetMsg(`Stable pH: ${Number(r.value).toFixed(2)} (σ=${r.std?.toFixed(3) || '?'})`, true, 'success');
      } else {
        const hint = (r && r.note && r.note.includes('NoData'))
          ? 'NoData — probe not responding. Check sensor power & I²C wiring.'
          : ((r && r.note) || 'Stabilize failed');
        phSetMsg(hint, false);
      }
    } catch (e) {
      phSetMsg(`Stabilize failed (network): ${e.message}`, false);
    } finally {
      phSetCalibBusy(false);
    }
  });

  // pH Status button
  el('btnPhStatus')?.addEventListener('click', async () => {
    phSetCalibBusy(true);
    try {
      const resp = await fetch('/calib/ph/status?t=' + Date.now(), { cache: 'no-store' });
      const r = await resp.json();
      if (r && r.ok) {
        const pts = r.points ? (r.points.length ? r.points.join(', ') : 'none') : 'none';
        phSetMsg(`Calibration: ${pts}`, true);
      } else {
        const hint = (r && r.note && r.note.includes('NoData'))
          ? 'NoData — probe not responding. Check sensor power & I²C wiring.'
          : ((r && r.note) || 'Status failed');
        phSetMsg(hint, false);
      }
    } catch (e) {
      phSetMsg(`Status failed (network): ${e.message}`, false);
    } finally {
      phSetCalibBusy(false);
    }
  });

  // pH Calibrate button
  el('btnPhCalibrate')?.addEventListener('click', async () => {
    phSetCalibBusy(true, 'Working…');
    try {
      const kindSel = el('ph-buffer-kind');
      const valInp = el('ph-buffer-val');
      const kind = (kindSel && kindSel.value) || 'mid';
      const val = parseFloat(valInp && valInp.value || '7.00');
      if (!isFinite(val)) {
        phSetMsg('Invalid buffer value', false);
        return;
      }
      const ep = kind === 'low' ? 'low' : kind === 'high' ? 'high' : 'mid';
      phSetMsg(`Sending ${ep} calibration (${val.toFixed(2)})...`);
      const resp = await fetch(`/calib/ph/${ep}?value=${encodeURIComponent(val.toFixed(2))}`, { method: 'POST' });
      let r = null;
      try { r = await resp.json(); } catch (_) { /* ignore */ }
      if (r && r.ok) {
        phSetMsg(r.note || 'Calibration OK', true, 'success');
      } else {
        phSetMsg((r && r.note) || `Calibration failed (HTTP ${resp.status})`, false);
      }
    } catch (e) {
      phSetMsg('Calibration failed (network)', false);
    } finally {
      phSetCalibBusy(false);
    }
  });

  // pH Clear button
  el('btnPhClear')?.addEventListener('click', async () => {
    phSetCalibBusy(true);
    try {
      const r = await (await fetch('/calib/ph/clear', { method: 'POST' })).json();
      if (r && r.ok) {
        phSetMsg(r.note || 'Calibration cleared', true, 'warn');
      } else {
        phSetMsg((r && r.note) || 'Clear rejected', false);
      }
    } catch (e) {
      phSetMsg('Clear failed (network)', false);
    } finally {
      phSetCalibBusy(false);
    }
  });

  // pH LED buttons
  el('btnLedsOn')?.addEventListener('click', async () => {
    try {
      await fetch('/api/relays/pH_leds/on', { method: 'POST' });
      phSetMsg('LEDs ON', true);
    } catch (e) {
      phSetMsg('LEDs ON failed', false);
    }
  });

  el('btnLedsOff')?.addEventListener('click', async () => {
    try {
      await fetch('/api/relays/pH_leds/off', { method: 'POST' });
      phSetMsg('LEDs OFF', true);
    } catch (e) {
      phSetMsg('LEDs OFF failed', false);
    }
  });

  el('btnLedsBlink')?.addEventListener('click', async () => {
    try {
      await fetch('/api/relays/pH_leds/blink?duration_ms=500', { method: 'POST' });
      phSetMsg('LEDs blink', true);
    } catch (e) {
      phSetMsg('LEDs blink failed', false);
    }
  });

  // EC Calibration functions
  function ecSetMsg(msg, style = null) {
    const msgEl = el('ec-calib-msg');
    if (msgEl) {
      msgEl.textContent = msg;
      msgEl.style.color = style === 'success' ? '#10b981' : style === 'warn' ? '#f59e0b' : '';
    }
  }

  const ecCalibBtnIds = ['btnEcClear', 'btnEcCalLow', 'btnEcCalHigh', 'btnEcSetK'];

  function ecSetCalibBusy(busy) {
    ecCalibBtnIds.forEach(id => {
      const b = el(id);
      if (b) b.disabled = busy;
    });
  }

  async function ecLoadStatus() {
    try {
      const r = await (await fetch('/api/ec/cal/status?t=' + Date.now(), { cache: 'no-store' })).json();
      const statusEl = el('ec-cal-status');
      if (statusEl) {
        const pts = r.points || [];
        statusEl.textContent = pts.length ? pts.join(', ') : 'none';
      }
    } catch (e) {
      ecSetMsg('Failed to load status', 'warn');
    }
  }

  // EC Clear button
  el('btnEcClear')?.addEventListener('click', async () => {
    ecSetCalibBusy(true);
    try {
      const r = await (await fetch('/api/ec/cal/clear', { method: 'POST' })).json();
      if (r && r.ok) {
        ecSetMsg(r.note || 'Calibration cleared', 'warn');
        await ecLoadStatus();
      } else {
        ecSetMsg((r && r.note) || 'Clear failed');
      }
    } catch (e) {
      ecSetMsg('Clear failed (network)');
    } finally {
      ecSetCalibBusy(false);
    }
  });

  // EC Calibrate Low button
  el('btnEcCalLow')?.addEventListener('click', async () => {
    ecSetCalibBusy(true);
    try {
      const valInp = el('ec-cal-low-val');
      const val = parseFloat(valInp && valInp.value || '1413');
      if (!isFinite(val)) {
        ecSetMsg('Invalid low value');
        return;
      }
      ecSetMsg(`Calibrating low (${val} µS/cm)...`);
      const r = await (await fetch(`/api/ec/cal/low?value=${val}`, { method: 'POST' })).json();
      if (r && r.ok) {
        ecSetMsg(r.note || 'Low calibration OK', 'success');
        await ecLoadStatus();
      } else {
        ecSetMsg((r && r.note) || 'Low calibration failed');
      }
    } catch (e) {
      ecSetMsg('Low calibration failed (network)');
    } finally {
      ecSetCalibBusy(false);
    }
  });

  // EC Calibrate High button
  el('btnEcCalHigh')?.addEventListener('click', async () => {
    ecSetCalibBusy(true);
    try {
      const valInp = el('ec-cal-high-val');
      const val = parseFloat(valInp && valInp.value || '12880');
      if (!isFinite(val)) {
        ecSetMsg('Invalid high value');
        return;
      }
      ecSetMsg(`Calibrating high (${val} µS/cm)...`);
      const r = await (await fetch(`/api/ec/cal/high?value=${val}`, { method: 'POST' })).json();
      if (r && r.ok) {
        ecSetMsg(r.note || 'High calibration OK', 'success');
        await ecLoadStatus();
      } else {
        ecSetMsg((r && r.note) || 'High calibration failed');
      }
    } catch (e) {
      ecSetMsg('High calibration failed (network)');
    } finally {
      ecSetCalibBusy(false);
    }
  });

  // EC Set K button
  el('btnEcSetK')?.addEventListener('click', async () => {
    ecSetCalibBusy(true);
    try {
      const kSel = el('ec-k-val');
      const k = (kSel && kSel.value) || '1.0';
      ecSetMsg(`Setting K=${k}...`);
      const r = await (await fetch(`/api/ec/k?value=${k}`, { method: 'POST' })).json();
      if (r && r.ok) {
        ecSetMsg(r.note || 'K constant set', 'success');
      } else {
        ecSetMsg((r && r.note) || 'Set K failed');
      }
    } catch (e) {
      ecSetMsg('Set K failed (network)');
    } finally {
      ecSetCalibBusy(false);
    }
  });

  // Dosing Pump Calibration
  // TODO: Wire up dosing pump calibration buttons when UI is finalized

  // Initialize
  (async function init() {
    await phCheckCaps();
    await ecLoadStatus();
  })();

})();
