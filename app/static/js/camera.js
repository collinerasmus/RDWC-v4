(function(){
  if (window.__cameraReady) return;

  const PLACEHOLDER_SVG = 'data:image/svg+xml,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="200" height="150">' +
    '<rect fill="#111827" width="100" height="100"/>' +
    '<text x="50" y="45" text-anchor="middle" fill="#94a3b8" font-size="9">RDWC Camera</text>' +
    '<text x="50" y="58" text-anchor="middle" fill="#64748b" font-size="8">No live stream</text>' +
    '</svg>'
  );

  const state = {
    active: false,
    selectedMode: 'auto',
    currentMode: 'none',
    streamHealthy: false,
    healthTimer: null,
    snapshotTimer: null,
    switchDebounce: 0,
    timelapse: null,
  };

  const el = (id) => document.getElementById(id);
  const fmtAgo = (ts) => {
    if (!ts) return '\u2014';
    const sec = Math.max(0, Math.floor(Date.now() / 1000 - Number(ts)));
    if (sec < 60) return sec + 's ago';
    if (sec < 3600) return Math.floor(sec / 60) + 'm ago';
    return Math.floor(sec / 3600) + 'h ago';
  };

  function setStatusText(text){
    const pill = el('camera-status-pill');
    if (pill) pill.textContent = text;
  }

  function showOverlay(text){
    const overlay = el('camera-overlay');
    if (!overlay) return;
    overlay.textContent = text;
    overlay.style.display = 'flex';
  }

  function hideOverlay(){
    const overlay = el('camera-overlay');
    if (overlay) overlay.style.display = 'none';
  }

  function usePlaceholder(msg){
    const img = el('camera-stream');
    const obj = el('camera-object');
    state.currentMode = 'none';
    if (obj){ obj.style.display = 'none'; obj.data = ''; }
    if (img){ img.src = PLACEHOLDER_SVG; img.style.display = 'block'; }
    showOverlay(msg || 'Camera unavailable');
    setStatusText('Status: unavailable');
  }

  function useSnapshot(){
    const img = el('camera-stream');
    const obj = el('camera-object');
    state.currentMode = 'snapshot';
    if (obj){ obj.style.display = 'none'; obj.data = ''; }
    if (img){
      img.src = '/camera/snapshot.jpg?t=' + Date.now();
      img.style.display = 'block';
      img.onerror = function(){ usePlaceholder('Snapshot unavailable'); };
    }
    hideOverlay();
    setStatusText('Status: snapshot');
  }

  function useStream(){
    const img = el('camera-stream');
    const obj = el('camera-object');
    state.currentMode = 'streaming';
    if (obj){ obj.style.display = 'none'; obj.data = ''; }
    if (img){
      img.src = '/camera/stream?t=' + Date.now();
      img.style.display = 'block';
      img.onerror = function(){
        state.switchDebounce = 2;
        state.streamHealthy = false;
        useSnapshot();
      };
    }
    hideOverlay();
    setStatusText('Status: streaming');
  }

  async function checkCameraStatus(){
    try {
      const r = await fetch('/camera/status', { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch(_) {
      return null;
    }
  }

  async function checkStreamHealth(){
    try {
      const r = await fetch('/camera/stream/health', { cache: 'no-store' });
      return r.status === 204;
    } catch(_) {
      return false;
    }
  }

  function stopSnapshotTimer(){
    if (state.snapshotTimer){
      clearInterval(state.snapshotTimer);
      state.snapshotTimer = null;
    }
  }

  function startSnapshotTimer(){
    stopSnapshotTimer();
    const sec = Math.max(5, parseInt(el('cam-snapshot-every')?.value || '20', 10) || 20);
    state.snapshotTimer = setInterval(function(){
      if (!state.active) return;
      if (state.currentMode === 'snapshot') useSnapshot();
    }, sec * 1000);
  }

  async function applyCameraMode(){
    if (!state.active) return;

    if (state.switchDebounce > 0){
      state.switchDebounce -= 1;
      return;
    }

    const status = await checkCameraStatus();
    if (!status || !status.available){
      state.streamHealthy = false;
      usePlaceholder('Camera unavailable');
      return;
    }

    if (state.selectedMode === 'snapshot'){
      useSnapshot();
      return;
    }

    if (state.selectedMode === 'stream'){
      useStream();
      return;
    }

    const healthy = await checkStreamHealth();
    state.streamHealthy = healthy;
    if (healthy){
      useStream();
    } else {
      useSnapshot();
    }
  }

  function stopHealthPolling(){
    if (state.healthTimer){
      clearInterval(state.healthTimer);
      state.healthTimer = null;
    }
  }

  function startHealthPolling(){
    stopHealthPolling();
    state.healthTimer = setInterval(function(){
      applyCameraMode().catch(function(){});
    }, 5000);
  }

  async function fetchTimelapseStatus(){
    try {
      const r = await fetch('/camera/timelapse/status', { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch(_) {
      return null;
    }
  }

  function renderTimelapseStatus(st){
    if (!st) return;
    state.timelapse = st;

    const runEl = el('camera-running');
    const countEl = el('camera-frame-count');
    const nextEl = el('camera-next-capture');
    const lastEl = el('camera-last-capture');
    const sessEl = el('camera-session-id');
    const note = el('camera-timelapse-note');
    const lastFrameLink = el('camera-last-frame-link');

    if (runEl) runEl.textContent = st.running ? 'Running' : 'Stopped';
    if (countEl) countEl.textContent = String(st.frame_count || 0);
    if (nextEl) nextEl.textContent = st.running ? ((st.next_capture_in_s ?? '\u2014') + 's') : '\u2014';
    if (lastEl) lastEl.textContent = st.last_capture_ts ? fmtAgo(st.last_capture_ts) : '\u2014';
    if (sessEl) sessEl.textContent = st.session_id || '\u2014';

    if (lastFrameLink){
      if (st.last_frame){
        const rel = String(st.last_frame).replace(/\\\\/g, '/');
        lastFrameLink.textContent = 'Last frame saved';
        lastFrameLink.href = '/camera/snapshot.jpg?t=' + Date.now();
        lastFrameLink.title = rel;
      } else {
        lastFrameLink.textContent = '\u2014';
        lastFrameLink.removeAttribute('href');
        lastFrameLink.removeAttribute('title');
      }
    }

    const msg = st.last_error || st.stopped_reason || (st.running ? 'Timelapse active' : 'Ready');
    if (note) note.textContent = msg;

    const startBtn = el('btn-camera-start');
    const stopBtn = el('btn-camera-stop');
    if (startBtn) startBtn.disabled = !!st.running;
    if (stopBtn) stopBtn.disabled = !st.running;
  }

  function setTimelapseNote(msg){
    const note = el('camera-timelapse-note');
    if (note) note.textContent = msg || 'Ready';
  }

  async function refreshSessions(){
    const list = el('camera-sessions');
    if (!list) return;
    try {
      const r = await fetch('/camera/timelapse/sessions?limit=8', { cache: 'no-store' });
      if (!r.ok) throw new Error('sessions_failed');
      const j = await r.json();
      const items = (j && j.items) || [];
      if (!items.length){
        list.innerHTML = '<div class="muted" style="font-size:var(--font-xs);">No timelapse sessions yet.</div>';
        return;
      }
      list.innerHTML = items.map(function(s){
        return '<div style="padding:6px 8px;border-radius:6px;background:rgba(148,163,184,0.08);border:1px solid rgba(148,163,184,0.2);margin-bottom:6px;">' +
          '<div style="display:flex;justify-content:space-between;gap:8px;">' +
          '<span style="font-weight:600;">' + s.session_id + '</span>' +
          '<span class="muted">' + s.frames + ' frames</span>' +
          '</div>' +
          '<div class="muted" style="font-size:var(--font-xs);margin-top:2px;">' + s.path + '</div>' +
          '</div>';
      }).join('');
    } catch(_) {
      list.innerHTML = '<div class="muted" style="font-size:var(--font-xs);">Session history unavailable.</div>';
    }
  }

  async function postJSON(url, body){
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    const txt = await r.text();
    let data = null;
    try { data = txt ? JSON.parse(txt) : null; } catch(_){ data = null; }
    if (!r.ok) {
      const msg = (data && (data.error || data.detail)) || ('HTTP ' + r.status);
      throw new Error(msg);
    }
    return data || {};
  }

  async function startTimelapse(){
    const payload = {
      interval_s: parseInt(el('cam-interval-s')?.value || '300', 10),
      quality: parseInt(el('cam-quality')?.value || '80', 10),
      max_frames: parseInt(el('cam-max-frames')?.value || '0', 10),
      label: (el('cam-label')?.value || 'grow').trim(),
    };
    try {
      const res = await postJSON('/camera/timelapse/start', payload);
      if (res && res.status) renderTimelapseStatus(res.status);
      else if (res && res.error) setTimelapseNote('Start failed: ' + res.error);
      else setTimelapseNote('Start failed');
    } catch(e) {
      setTimelapseNote('Start failed: ' + (e && e.message ? e.message : 'request error'));
    }
    await refreshSessions();
  }

  async function stopTimelapse(){
    try {
      const res = await postJSON('/camera/timelapse/stop', {});
      if (res && res.status) renderTimelapseStatus(res.status);
      else setTimelapseNote('Stop failed');
    } catch(e) {
      setTimelapseNote('Stop failed: ' + (e && e.message ? e.message : 'request error'));
    }
    await refreshSessions();
  }

  async function captureNow(){
    const quality = parseInt(el('cam-quality')?.value || '80', 10);
    try {
      const res = await postJSON('/camera/timelapse/capture', { quality: quality });
      if (res && res.status) {
        renderTimelapseStatus(res.status);
        useSnapshot();
      } else if (res && res.error) {
        setTimelapseNote('Capture failed: ' + res.error);
      } else {
        setTimelapseNote('Capture failed');
      }
    } catch(e) {
      setTimelapseNote('Capture failed: ' + (e && e.message ? e.message : 'request error'));
    }
    await refreshSessions();
  }

  function onModeChange(){
    const modeEl = el('cam-view-mode');
    state.selectedMode = modeEl ? modeEl.value : 'auto';
    applyCameraMode().catch(function(){});
    if (state.selectedMode === 'snapshot') startSnapshotTimer();
    else stopSnapshotTimer();
  }

  async function refreshAll(){
    const st = await fetchTimelapseStatus();
    if (st) renderTimelapseStatus(st);
    await refreshSessions();
    await applyCameraMode();
  }

  function setActive(active){
    state.active = !!active;
    if (state.active){
      refreshAll().catch(function(){});
      startHealthPolling();
      if (state.selectedMode === 'snapshot') startSnapshotTimer();
    } else {
      stopHealthPolling();
      stopSnapshotTimer();
      usePlaceholder('Open Camera tab to start feed');
    }
  }

  function bind(){
    const startBtn = el('btn-camera-start');
    const stopBtn = el('btn-camera-stop');
    const capBtn = el('btn-camera-capture');
    const refreshBtn = el('btn-camera-refresh');
    const modeSel = el('cam-view-mode');
    const snapEvery = el('cam-snapshot-every');

    if (startBtn && !startBtn.__bound){ startBtn.__bound = true; startBtn.addEventListener('click', function(){ startTimelapse(); }); }
    if (stopBtn && !stopBtn.__bound){ stopBtn.__bound = true; stopBtn.addEventListener('click', function(){ stopTimelapse(); }); }
    if (capBtn && !capBtn.__bound){ capBtn.__bound = true; capBtn.addEventListener('click', function(){ captureNow(); }); }
    if (refreshBtn && !refreshBtn.__bound){ refreshBtn.__bound = true; refreshBtn.addEventListener('click', function(){ refreshAll().catch(function(){ setTimelapseNote('Refresh failed'); }); }); }
    if (modeSel && !modeSel.__bound){ modeSel.__bound = true; modeSel.addEventListener('change', onModeChange); }
    if (snapEvery && !snapEvery.__bound){ snapEvery.__bound = true; snapEvery.addEventListener('change', function(){ if (state.selectedMode === 'snapshot') startSnapshotTimer(); }); }

    window.addEventListener('tab-changed', function(ev){
      const tab = ev && ev.detail && ev.detail.tab;
      setActive(tab === 'camera');
    });

    document.addEventListener('visibilitychange', function(){
      if (document.hidden){
        stopHealthPolling();
        stopSnapshotTimer();
      } else if (state.active) {
        startHealthPolling();
        if (state.selectedMode === 'snapshot') startSnapshotTimer();
        refreshAll().catch(function(){});
      }
    });

    state.selectedMode = modeSel ? modeSel.value : 'auto';
    const initialTab = (location.hash || '#overview').replace('#', '');
    setActive(initialTab === 'camera');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();

  window.__cameraReady = true;
})();
