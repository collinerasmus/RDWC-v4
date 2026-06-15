(function(){
  const q = (s, r=document) => r.querySelector(s);

  function asBool(v){
    return v === true || String(v).toLowerCase() === 'true' || String(v) === '1';
  }

  function setPill(state, text){
    const pill = q('#reports-health-indicator');
    if (!pill) return;
    pill.textContent = text;
    pill.className = 'ui-status-chip ' + state;
  }

  function setNote(msg){
    const el = q('#reports-status-note');
    if (el) el.textContent = msg;
  }

  function setResult(msg){
    const el = q('#reports-last-result');
    if (el) el.textContent = msg;
  }

  async function loadPreferences(){
    const r = await fetch('/api/reports/preferences?t=' + Date.now(), {cache:'no-store'});
    const j = await r.json();

    const enabled = q('#reports-enabled');
    const sendTime = q('#reports-send-time');
    const recipient = q('#reports-recipient-email');
    const transport = q('#reports-transport');
    const includePhoto = q('#reports-include-photo');
    const includeStatus = q('#reports-include-status');
    const includeForecast = q('#reports-include-forecast');

    if (enabled) enabled.checked = asBool(j.enabled);
    if (sendTime) sendTime.value = j.send_time || '07:00';
    if (recipient) recipient.value = j.recipient_email || '';
    if (transport) transport.value = (j.transport || 'pi').toLowerCase();
    if (includePhoto) includePhoto.checked = asBool(j.include_photo);
    if (includeStatus) includeStatus.checked = asBool(j.include_status);
    if (includeForecast) includeForecast.checked = asBool(j.include_forecast);
  }

  async function loadStatus(){
    const r = await fetch('/api/reports/status?t=' + Date.now(), {cache:'no-store'});
    const j = await r.json();
    const missing = Array.isArray(j.missing_required_env) ? j.missing_required_env : [];
    const pwSet = !!j.smtp_password_set;

    if (missing.length){
      setPill('warning', 'Config missing');
      if (missing.length === 1 && missing[0] === 'EMAIL_PASSWORD') {
        setNote('Gmail app password is not set. Enter it below and click "Save Mail Credentials".');
      } else {
        setNote('Missing required mail env: ' + missing.join(', ') + '. Configure credentials in this Reports tab.');
      }
    } else {
      const active = (j.timer_active || '').trim();
      const enabled = (j.timer_enabled || '').trim();
      if (active === 'active' && enabled === 'enabled') {
        setPill('success', 'Pi timer active');
      } else {
        setPill('neutral', 'Timer not active');
      }
      setNote('Timer active=' + active + ', enabled=' + enabled + ', app password=' + (pwSet ? 'set' : 'missing'));
    }
  }

  function gatherPayload(){
    return {
      enabled: !!q('#reports-enabled')?.checked,
      send_time: q('#reports-send-time')?.value || '07:00',
      recipient_email: (q('#reports-recipient-email')?.value || '').trim(),
      include_photo: !!q('#reports-include-photo')?.checked,
      include_status: !!q('#reports-include-status')?.checked,
      include_forecast: !!q('#reports-include-forecast')?.checked,
      transport: (q('#reports-transport')?.value || 'pi').trim().toLowerCase()
    };
  }

  async function savePreferences(){
    const btn = q('#btnReportsSave');
    const before = btn ? btn.textContent : '';
    if (btn){ btn.disabled = true; btn.textContent = 'Saving...'; }

    try {
      const payload = gatherPayload();
      const r = await fetch('/api/reports/preferences', {
        method: 'PUT',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const j = await r.json();
      if (!r.ok || !j.ok) {
        throw new Error(j.message || j.error || 'save_failed');
      }
      if (window.showToast) window.showToast('Report preferences saved', 'success');
      setResult('Preferences saved at ' + new Date().toLocaleString());
      await loadStatus();
    } catch (e) {
      if (window.showToast) window.showToast('Save failed: ' + (e.message || e), 'error');
      setResult('Save failed: ' + (e.message || e));
    } finally {
      if (btn){ btn.disabled = false; btn.textContent = before || 'Save Report Preferences'; }
    }
  }

  async function saveCredentials(){
    const btn = q('#btnReportsSaveCredentials');
    const pwInput = q('#reports-app-password');
    const before = btn ? btn.textContent : '';
    const password = (pwInput?.value || '').trim();

    if (!password){
      if (window.showToast) window.showToast('Enter app password first', 'warning');
      setResult('Mail credential save skipped: app password is empty.');
      return;
    }

    if (btn){ btn.disabled = true; btn.textContent = 'Saving...'; }
    try {
      const r = await fetch('/api/reports/credentials', {
        method: 'PUT',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ email_password: password })
      });
      const j = await r.json();
      if (!r.ok || !j.ok) {
        throw new Error(j.detail || j.error || 'credential_save_failed');
      }
      if (pwInput) pwInput.value = '';
      if (window.showToast) window.showToast('Mail credentials saved', 'success');
      setResult('Mail credentials saved at ' + new Date().toLocaleString());
      await loadStatus();
    } catch (e) {
      if (window.showToast) window.showToast('Credential save failed', 'error');
      setResult('Credential save failed\n\n' + (e.message || e));
    } finally {
      if (btn){ btn.disabled = false; btn.textContent = before || 'Save Mail Credentials'; }
    }
  }

  async function sendTest(){
    const btn = q('#btnReportsSendTest');
    const before = btn ? btn.textContent : '';
    if (btn){ btn.disabled = true; btn.textContent = 'Sending...'; }
    setResult('Sending test report...');

    try {
      const r = await fetch('/api/reports/send_test', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: '{}'
      });
      const j = await r.json();
      if (!r.ok || !j.ok) {
        const err = (j.stderr || j.stdout || j.error || 'send_failed').toString();
        throw new Error(err);
      }
      if (window.showToast) window.showToast('Test report sent', 'success');
      setResult('Test send OK\n\n' + ((j.stdout || '').trim() || 'No stdout'));
    } catch (e) {
      if (window.showToast) window.showToast('Test send failed', 'error');
      setResult('Test send failed\n\n' + (e.message || e));
    } finally {
      if (btn){ btn.disabled = false; btn.textContent = before || 'Send Test Report Now'; }
    }
  }

  async function applyTimer(){
    const btn = q('#btnReportsApplyTimer');
    const before = btn ? btn.textContent : '';
    if (btn){ btn.disabled = true; btn.textContent = 'Applying...'; }
    setResult('Applying send time to Pi timer...');

    try {
      const r = await fetch('/api/reports/apply_timer', { method: 'POST' });
      const j = await r.json();
      if (!r.ok || !j.ok) {
        throw new Error((j.detail || j.error || 'apply_timer_failed').toString());
      }
      if (window.showToast) window.showToast('Pi timer updated', 'success');
      setResult('Timer update OK\n\nSend time: ' + (j.send_time || 'n/a'));
      await loadStatus();
    } catch (e) {
      if (window.showToast) window.showToast('Apply timer failed', 'error');
      setResult('Apply timer failed\n\n' + (e.message || e));
    } finally {
      if (btn){ btn.disabled = false; btn.textContent = before || 'Apply Send Time to Pi Timer'; }
    }
  }

  function bind(){
    const saveBtn = q('#btnReportsSave');
    const saveCredsBtn = q('#btnReportsSaveCredentials');
    const applyBtn = q('#btnReportsApplyTimer');
    const testBtn = q('#btnReportsSendTest');
    const refreshBtn = q('#btnReportsRefresh');
    if (saveBtn) saveBtn.addEventListener('click', savePreferences);
    if (saveCredsBtn) saveCredsBtn.addEventListener('click', saveCredentials);
    if (applyBtn) applyBtn.addEventListener('click', applyTimer);
    if (testBtn) testBtn.addEventListener('click', sendTest);
    if (refreshBtn) refreshBtn.addEventListener('click', async () => {
      await loadPreferences();
      await loadStatus();
    });
  }

  async function boot(){
    if (!q('#reports-card')) return;
    bind();
    await loadPreferences();
    await loadStatus();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
