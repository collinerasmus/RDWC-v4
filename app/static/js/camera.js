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
    recommendation: null,
    sessions: [],
    playbackUrl: null,
    countdownTimer: null,
    nextCaptureAtMs: null,
    storage: null,
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
    const fps = Math.max(2, Math.min(24, parseInt(el('cam-stream-fps')?.value || '10', 10) || 10));
    const quality = Math.max(40, Math.min(95, parseInt(el('cam-stream-quality')?.value || '85', 10) || 85));
    state.currentMode = 'streaming';
    if (obj){ obj.style.display = 'none'; obj.data = ''; }
    if (img){
      img.src = '/camera/stream?fps=' + fps + '&quality=' + quality + '&t=' + Date.now();
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
      Promise.all([
        fetchTimelapseStatus().then(function(st){ if (st) renderTimelapseStatus(st); }),
        applyCameraMode(),
      ]).catch(function(e){
        setTimelapseNote('Camera check failed: ' + (e && e.message ? e.message : 'request error'));
      });
    }, 5000);
  }

  function stopCountdownTimer(){
    if (state.countdownTimer) {
      clearInterval(state.countdownTimer);
      state.countdownTimer = null;
    }
  }

  function updateNextCaptureCountdown(){
    const nextEl = el('camera-next-capture');
    if (!nextEl) return;
    if (!state.timelapse || !state.timelapse.running || !state.nextCaptureAtMs) {
      nextEl.textContent = '\u2014';
      return;
    }
    const remaining = Math.max(0, Math.ceil((state.nextCaptureAtMs - Date.now()) / 1000));
    nextEl.textContent = remaining + 's';
  }

  function startCountdownTimer(){
    stopCountdownTimer();
    state.countdownTimer = setInterval(updateNextCaptureCountdown, 1000);
    updateNextCaptureCountdown();
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
    const skippedEl = el('camera-skipped-count');
    const policyEl = el('camera-capture-policy');
    const sessEl = el('camera-session-id');
    const note = el('camera-timelapse-note');
    const lastFrameLink = el('camera-last-frame-link');
    const lightsOnlyEl = el('cam-lights-on-only');

    if (runEl) {
      if (st.running && st.capture_allowed_now === false && st.capture_policy_reason === 'lights_off') runEl.textContent = 'Running (waiting lights-on)';
      else runEl.textContent = st.running ? 'Running' : 'Stopped';
    }
    if (countEl) countEl.textContent = String(st.frame_count || 0);
    if (skippedEl) skippedEl.textContent = String(st.skipped_captures || 0);
    if (st.running) {
      if (st.next_capture_ts) {
        state.nextCaptureAtMs = Number(st.next_capture_ts) * 1000;
      } else if (st.next_capture_in_s !== null && st.next_capture_in_s !== undefined) {
        state.nextCaptureAtMs = Date.now() + Number(st.next_capture_in_s) * 1000;
      } else {
        state.nextCaptureAtMs = null;
      }
      startCountdownTimer();
    } else {
      state.nextCaptureAtMs = null;
      stopCountdownTimer();
      if (nextEl) nextEl.textContent = '\u2014';
    }
    if (lastEl) lastEl.textContent = st.last_capture_ts ? fmtAgo(st.last_capture_ts) : '\u2014';
    if (policyEl) {
      if (st.lights_on_only) {
        policyEl.textContent = (st.capture_allowed_now === false) ? 'Lights-off hold' : 'Lights-on only';
      } else {
        policyEl.textContent = 'Always capture';
      }
    }
    if (lightsOnlyEl && !st.running) lightsOnlyEl.checked = !!st.lights_on_only;
    if (sessEl) sessEl.textContent = st.session_id || '\u2014';

    if (lastFrameLink){
      if (st.last_frame){
        const rel = String(st.last_frame).replace(/\\\\/g, '/');
        lastFrameLink.textContent = 'Last frame saved';
        lastFrameLink.href = '/camera/timelapse/preview?t=' + Date.now();
        lastFrameLink.title = rel;
      } else {
        lastFrameLink.textContent = '\u2014';
        lastFrameLink.removeAttribute('href');
        lastFrameLink.removeAttribute('title');
      }
    }

    const preview = el('camera-timelapse-preview');
    if (preview) {
      if (st.last_frame) {
        preview.src = '/camera/timelapse/preview?t=' + Date.now();
        preview.style.display = 'block';
      } else {
        preview.removeAttribute('src');
        preview.style.display = 'none';
      }
    }

    let msg = st.last_error || st.stopped_reason || (st.running ? 'Timelapse active' : 'Ready');
    if (st.running && st.capture_allowed_now === false && st.capture_policy_reason === 'lights_off') {
      msg = 'Running, waiting for lights-on window';
    }
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

  function setPlaybackState(url, note){
    const video = el('camera-playback-video');
    const open = el('btn-camera-open-playback');
    const download = el('btn-camera-download-playback');
    const msg = el('camera-playback-note');

    state.playbackUrl = url || null;
    if (msg) msg.textContent = note || 'No render yet.';

    if (video) {
      if (url) {
        video.src = url;
        try { video.load(); } catch(_) {}
        video.style.display = 'block';
      } else {
        video.removeAttribute('src');
        try { video.load(); } catch(_) {}
        video.style.display = 'none';
      }
    }

    if (open) {
      if (url) {
        open.href = url;
        open.style.pointerEvents = 'auto';
        open.style.opacity = '1';
      } else {
        open.removeAttribute('href');
        open.style.pointerEvents = 'none';
        open.style.opacity = '0.6';
      }
    }

    if (download) {
      if (url) {
        download.href = url;
        download.style.pointerEvents = 'auto';
        download.style.opacity = '1';
      } else {
        download.removeAttribute('href');
        download.style.pointerEvents = 'none';
        download.style.opacity = '0.6';
      }
    }
  }

  function renderGrowPlan(rec){
    const plan = el('camera-grow-plan');
    if (!plan || !rec) return;
    const mins = Number(rec.estimated_video_minutes || 0).toFixed(1);
    const gb = Number(rec.estimated_storage_gb || 0).toFixed(2);
    plan.textContent = 'Estimated render: ' + rec.expected_frames + ' frames over ' + rec.grow_days + ' days (~' + mins + ' min at ' + rec.output_fps + ' fps, about ' + gb + ' GB storage).';
  }

  async function fetchRecommendation(){
    try {
      const r = await fetch('/camera/timelapse/recommendation?grow_days=0&output_fps=24', { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch(_) {
      return null;
    }
  }

  async function fetchStorage(){
    try {
      const r = await fetch('/camera/timelapse/storage', { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch(_) {
      return null;
    }
  }

  function estimateFillDays(storage, recommendation){
    if (!storage || !recommendation) return null;
    const maxMb = Number(storage.policy && storage.policy.max_total_mb || 0);
    const usedMb = Number(storage.total_mb || 0);
    const estGrowMb = Number(recommendation.estimated_storage_mb || 0);
    const growDays = Math.max(1, Number(recommendation.grow_days || 56));
    if (maxMb <= 0 || estGrowMb <= 0) return null;
    const mbPerDay = estGrowMb / growDays;
    if (mbPerDay <= 0) return null;
    const remaining = Math.max(0, maxMb - usedMb);
    return Math.floor(remaining / mbPerDay);
  }

  function renderStorageSummary(storage, recommendation){
    const note = el('camera-playback-note');
    if (!note || !storage) return;
    const used = Number(storage.total_mb || 0).toFixed(1);
    const sessions = Number(storage.sessions || 0);
    const maxMb = Number(storage.policy && storage.policy.max_total_mb || 0);
    const fillDays = estimateFillDays(storage, recommendation);
    let risk = 'No cap set';
    if (maxMb > 0) {
      const pct = Math.max(0, Math.min(100, Math.round((Number(storage.total_mb || 0) / maxMb) * 100)));
      if (pct >= 90) risk = 'High risk';
      else if (pct >= 75) risk = 'Medium risk';
      else risk = 'Low risk';
    }
    let txt = 'Storage: ' + used + ' MB across ' + sessions + ' sessions';
    if (maxMb > 0) txt += ' (cap ' + maxMb + ' MB, ' + risk + ')';
    if (fillDays !== null) txt += ', est. ~' + fillDays + ' days to cap at current cadence';
    note.textContent = txt;

    const preview = storage.prune_preview || {};
    const previewEl = el('camera-storage-preview');
    if (previewEl) {
      const n = Number(preview.candidate_count || 0);
      const mb = Number(preview.candidate_mb || 0).toFixed(1);
      previewEl.textContent = n > 0
        ? ('Prune preview: ' + n + ' sessions (' + mb + ' MB) are eligible by policy.')
        : 'Prune preview: no sessions currently eligible by policy.';
    }
  }

  async function createBackupArchive(scope){
    const res = await postJSON('/camera/timelapse/storage/archive', { scope: scope || 'prune_candidates' });
    if (!res || !res.ok || !res.archive || !res.archive.url) {
      throw new Error('backup_archive_failed');
    }
    const link = el('btn-camera-download-backup');
    if (link) {
      link.href = res.archive.url + '?t=' + Date.now();
      link.style.pointerEvents = 'auto';
      link.style.opacity = '1';
      link.textContent = 'Download Backup ZIP';
    }
    setTimelapseNote('Backup ZIP ready (' + (res.sessions || []).length + ' sessions). Download before prune.');
    return res;
  }

  async function pruneStorage(){
    try {
      const storage = state.storage || await fetchStorage();
      const preview = storage && storage.prune_preview ? storage.prune_preview : null;
      const candidateCount = Number(preview && preview.candidate_count || 0);
      if (candidateCount <= 0) {
        setTimelapseNote('No sessions eligible for policy prune right now.');
        return;
      }

      const prepare = window.confirm(
        'Policy prune will delete ' + candidateCount + ' session(s).\n\n' +
        'Do you want to PREPARE a backup ZIP for download first?'
      );
      if (prepare) {
        setTimelapseNote('Preparing backup ZIP before prune...');
        await createBackupArchive('prune_candidates');
      }

      const go = window.confirm(
        'Final confirmation: delete policy-prune candidates now?\n\n' +
        'Tip: Download backup ZIP first if you need to keep archive data on PC.'
      );
      if (!go) {
        setTimelapseNote('Prune cancelled. No data deleted.');
        return;
      }

      setTimelapseNote('Pruning timelapse storage...');
      const res = await postJSON('/camera/timelapse/storage/prune', { confirm: true });
        const storageUpdated = res && res.storage ? res.storage : await fetchStorage();
        if (storageUpdated) {
          state.storage = storageUpdated;
          renderStorageSummary(storageUpdated, state.recommendation);
      }
      if (res && res.ok) {
        setTimelapseNote('Prune complete: removed ' + (res.removed_count || 0) + ' sessions.');
      } else {
        setTimelapseNote('Prune failed');
      }
      await refreshSessions();
    } catch (e) {
      setTimelapseNote('Prune failed: ' + (e && e.message ? e.message : 'request error'));
    }
  }

  function applyRecommendationToInputs(rec){
    if (!rec) return;
    const intervalEl = el('cam-interval-s');
    const qualityEl = el('cam-quality');
    const maxEl = el('cam-max-frames');
    if (intervalEl) intervalEl.value = String(rec.interval_s || 600);
    if (qualityEl) qualityEl.value = String(rec.quality || 88);
    if (maxEl) maxEl.value = String(rec.max_frames || 8000);
    renderGrowPlan(rec);
    setTimelapseNote('Applied 8-week grow preset');
  }

  function renderInsights(payload){
    const summary = el('camera-insights-summary');
    const points = el('camera-insights-points');
    if (!summary || !points) return;
    if (!payload || !payload.ok){
      const err = payload && (payload.error || payload.detail || 'unavailable');
      summary.textContent = 'Analysis unavailable: ' + err;
      points.innerHTML = '';
      return;
    }

    const fb = payload.grow_feedback || {};
    const m = payload.metrics || {};
    summary.textContent = 'Score ' + (fb.visual_progress_score ?? '--') + '/100, confidence ' + Math.round((fb.confidence || 0) * 100) + '%, green trend ' + (m.green_ratio_delta ?? 0) + '.';

    const obs = Array.isArray(fb.observations) ? fb.observations : [];
    const recs = Array.isArray(fb.recommendations) ? fb.recommendations : [];
    const lines = [];
    obs.slice(0, 2).forEach(function(x){ lines.push('<div>Observation: ' + x + '</div>'); });
    recs.slice(0, 2).forEach(function(x){ lines.push('<div>Action: ' + x + '</div>'); });
    points.innerHTML = lines.join('');
  }

  async function refreshInsights(){
    const sid = (state.timelapse && state.timelapse.session_id) || '';
    const hasEnoughCurrent = !!(state.timelapse && Number(state.timelapse.frame_count || 0) >= 2);
    let pick = sid;
    if (!hasEnoughCurrent) {
      const recent = (state.sessions || []).find(function(s){ return Number(s.frames || 0) >= 2; });
      if (recent && recent.session_id) pick = recent.session_id;
    }
    try {
      const qsid = pick ? ('&session_id=' + encodeURIComponent(pick)) : '';
      const r = await fetch('/camera/timelapse/insights?sample_frames=8' + qsid, { cache: 'no-store' });
      if (!r.ok) {
        let err = null;
        try { err = await r.json(); } catch(_) { err = null; }
        renderInsights(err || { ok: false, error: 'request_failed' });
        return;
      }
      const j = await r.json();
      renderInsights(j);
    } catch(_) {
      renderInsights(null);
    }
  }

  async function refreshSessions(){
    const list = el('camera-sessions');
    if (!list) return;
    try {
      const r = await fetch('/camera/timelapse/sessions?limit=8', { cache: 'no-store' });
      if (!r.ok) throw new Error('sessions_failed');
      const j = await r.json();
      const items = (j && j.items) || [];
      state.sessions = items;
      if (!items.length){
        list.innerHTML = '<div class="muted" style="font-size:var(--font-xs);">No timelapse sessions yet.</div>';
        return;
      }
      const valid = items.filter(function(s){ return Number(s.frames || 0) >= 2; });
      const tiny = items.length - valid.length;
      const shown = valid.slice(0, 6);
      list.innerHTML = shown.map(function(s){
        return '<div style="padding:6px 8px;border-radius:6px;background:rgba(148,163,184,0.08);border:1px solid rgba(148,163,184,0.2);margin-bottom:6px;">' +
          '<div style="display:flex;justify-content:space-between;gap:8px;">' +
          '<span style="font-weight:600;">' + s.session_id + '</span>' +
          '<span class="muted">' + s.frames + ' frames</span>' +
          '</div>' +
          '<div class="muted" style="font-size:var(--font-xs);margin-top:2px;">' + s.path + '</div>' +
          '</div>';
      }).join('') +
      '<div class="muted" style="font-size:var(--font-xs);margin-top:4px;">Using sessions with 2+ frames. Skipping ' + tiny + ' tiny sessions.</div>';
    } catch(_) {
      list.innerHTML = '<div class="muted" style="font-size:var(--font-xs);">Session history unavailable.</div>';
    }
  }

  async function renderPlayback(){
    console.log('[Camera] renderPlayback() CALLED');
    const days = Math.max(1, Math.min(120, parseInt(el('cam-playback-days')?.value || '56', 10) || 56));
    const fps = Math.max(12, Math.min(60, parseInt(el('cam-playback-fps')?.value || '24', 10) || 24));
    const btn = el('btn-camera-render-playback');
    console.log('[Camera] render params - days=' + days + ', fps=' + fps + ', btn_found=' + !!btn);

    try {
      if (btn) btn.disabled = true;
      setPlaybackState(state.playbackUrl, `Rendering video (${days}d, ${fps} fps)...`);
      
      if (window.console && window.console.log) console.log('[Camera] Render request: days=' + days + ', fps=' + fps);

      const res = await postJSONWithTimeout('/camera/timelapse/render', {
        days: days,
        fps: fps,
        min_session_frames: 2,
        max_frames: 5000,
      }, 300000); // 5 min timeout for rendering

      if (!res || !res.ok || !res.video || !res.video.url) {
        const errMsg = res && res.error ? res.error : 'no_frames_or_sessions';
        setPlaybackState(null, 'Render failed (' + errMsg + '). Try a larger window or ensure enough frames are captured.');
        if (window.console && window.console.log) console.log('[Camera] Render failed:', res);
        return;
      }

      const url = res.video.url + '?t=' + Date.now();
      const note = 'Rendered ' + res.frames_written + ' frames from ' + res.used_sessions + ' sessions (skipped ' + res.skipped_sessions + ').';
      setPlaybackState(url, note);
      if (window.console && window.console.log) console.log('[Camera] Render success:', res);
    } catch (e) {
      const errMsg = (e && e.message ? e.message : 'request error');
      setPlaybackState(null, 'Render failed: ' + errMsg);
      if (window.console && window.console.error) console.error('[Camera] Render exception:', e);
    } finally {
      if (btn) btn.disabled = false;
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

  async function postJSONWithTimeout(url, body, timeoutMs = 60000){
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
        signal: controller.signal,
      });
      const txt = await r.text();
      let data = null;
      try { data = txt ? JSON.parse(txt) : null; } catch(_){ data = null; }
      if (!r.ok) {
        const msg = (data && (data.error || data.detail)) || ('HTTP ' + r.status);
        throw new Error(msg);
      }
      return data || {};
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async function startTimelapse(){
    const lightsOnly = !!el('cam-lights-on-only')?.checked;
    const payload = {
      interval_s: parseInt(el('cam-interval-s')?.value || '300', 10),
      quality: parseInt(el('cam-quality')?.value || '80', 10),
      max_frames: parseInt(el('cam-max-frames')?.value || '0', 10),
      lights_on_only: lightsOnly,
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

  async function cleanupNighttimeFrames(){
    const brightnessThreshold = parseInt(el('cam-cleanup-brightness')?.value || '60', 10);
    const confirm = window.confirm(
      'Remove frames with brightness < ' + brightnessThreshold + ' (nighttime captures)?\n' +
      'This will scan all sessions and delete dark frames.\n\n' +
      'Continue?'
    );
    if (!confirm) return;

    try {
      setTimelapseNote('Scanning and removing nighttime frames...');
      const res = await postJSON('/camera/timelapse/cleanup', {
        brightness_threshold: brightnessThreshold
      });
      
      if (res && res.ok) {
        const msg = 'Cleaned ' + res.frames_deleted + ' frames from ' + res.sessions_processed + ' sessions (' + res.total_freed_mb + ' MB freed).';
        setTimelapseNote(msg);
        if (res.errors && res.errors.length) {
          console.warn('Cleanup errors:', res.errors);
        }
        await refreshSessions();
      } else {
        const err = res && (res.error || res.detail) || 'unknown_error';
        setTimelapseNote('Cleanup failed: ' + err);
      }
    } catch(e) {
      setTimelapseNote('Cleanup failed: ' + (e && e.message ? e.message : 'request error'));
    }
  }

  function onModeChange(){
    const modeEl = el('cam-view-mode');
    state.selectedMode = modeEl ? modeEl.value : 'auto';
    applyCameraMode().catch(function(e){
      setTimelapseNote('Mode apply failed: ' + (e && e.message ? e.message : 'request error'));
    });
    if (state.selectedMode === 'snapshot') startSnapshotTimer();
    else stopSnapshotTimer();
  }

  async function refreshAll(){
    if (!state.recommendation){
      state.recommendation = await fetchRecommendation();
      if (state.recommendation) {
        renderGrowPlan(state.recommendation);
      }
    }
    const storage = await fetchStorage();
    if (storage) {
      state.storage = storage;
      renderStorageSummary(storage, state.recommendation);
    }
    const st = await fetchTimelapseStatus();
    if (st) renderTimelapseStatus(st);
    await refreshSessions();
    await refreshInsights();
    await applyCameraMode();
  }

  function setActive(active){
    state.active = !!active;
    if (state.active){
      refreshAll().catch(function(e){
        setTimelapseNote('Refresh failed: ' + (e && e.message ? e.message : 'request error'));
      });
      startHealthPolling();
      if (state.selectedMode === 'snapshot') startSnapshotTimer();
    } else {
      stopHealthPolling();
      stopSnapshotTimer();
      stopCountdownTimer();
      usePlaceholder('Open Camera tab to start feed');
    }
  }

  function bind(){
    console.log('[Camera] bind() starting - setting up event listeners');
    const startBtn = el('btn-camera-start');
    const stopBtn = el('btn-camera-stop');
    const capBtn = el('btn-camera-capture');
    const refreshBtn = el('btn-camera-refresh');
    const analyzeBtn = el('btn-camera-insights');
    const presetBtn = el('btn-camera-apply-grow-preset');
    const renderBtn = el('btn-camera-render-playback');
    const cleanupBtn = el('btn-camera-cleanup-nighttime');
    const pruneBtn = el('btn-camera-prune-storage');
    const backupBtn = el('btn-camera-backup-storage');
    const modeSel = el('cam-view-mode');
    const snapEvery = el('cam-snapshot-every');
    const streamFps = el('cam-stream-fps');
    const streamQuality = el('cam-stream-quality');

    if (startBtn && !startBtn.__bound){ startBtn.__bound = true; startBtn.addEventListener('click', function(){ startTimelapse(); }); }
    if (stopBtn && !stopBtn.__bound){ stopBtn.__bound = true; stopBtn.addEventListener('click', function(){ stopTimelapse(); }); }
    if (capBtn && !capBtn.__bound){ capBtn.__bound = true; capBtn.addEventListener('click', function(){ captureNow(); }); }
    if (refreshBtn && !refreshBtn.__bound){ refreshBtn.__bound = true; refreshBtn.addEventListener('click', function(){ refreshAll().catch(function(){ setTimelapseNote('Refresh failed'); }); }); }
    if (analyzeBtn && !analyzeBtn.__bound){ analyzeBtn.__bound = true; analyzeBtn.addEventListener('click', function(){ refreshInsights(); }); }
    if (renderBtn && !renderBtn.__bound){ renderBtn.__bound = true; console.log('[Camera] renderBtn event listener attached'); renderBtn.addEventListener('click', function(){ renderPlayback(); }); }
    if (cleanupBtn && !cleanupBtn.__bound){ cleanupBtn.__bound = true; cleanupBtn.addEventListener('click', function(){ cleanupNighttimeFrames(); }); }
    if (pruneBtn && !pruneBtn.__bound){ pruneBtn.__bound = true; pruneBtn.addEventListener('click', function(){ pruneStorage(); }); }
    if (backupBtn && !backupBtn.__bound){ backupBtn.__bound = true; backupBtn.addEventListener('click', function(){ createBackupArchive('prune_candidates').catch(function(e){ setTimelapseNote('Backup ZIP failed: ' + (e && e.message ? e.message : 'request error')); }); }); }
    if (presetBtn && !presetBtn.__bound){ presetBtn.__bound = true; presetBtn.addEventListener('click', function(){
      const rec = state.recommendation;
      if (rec) {
        applyRecommendationToInputs(rec);
        const dayInput = el('cam-playback-days');
        if (dayInput && rec.grow_days) dayInput.value = String(rec.grow_days);
      } else {
        fetchRecommendation().then(function(r){ state.recommendation = r; applyRecommendationToInputs(r); }).catch(function(){ setTimelapseNote('Preset fetch failed'); });
      }
    }); }
    if (modeSel && !modeSel.__bound){ modeSel.__bound = true; modeSel.addEventListener('change', onModeChange); }
    if (snapEvery && !snapEvery.__bound){ snapEvery.__bound = true; snapEvery.addEventListener('change', function(){ if (state.selectedMode === 'snapshot') startSnapshotTimer(); }); }
    if (streamFps && !streamFps.__bound){ streamFps.__bound = true; streamFps.addEventListener('change', function(){ if (state.active && state.currentMode === 'streaming') useStream(); }); }
    if (streamQuality && !streamQuality.__bound){ streamQuality.__bound = true; streamQuality.addEventListener('change', function(){ if (state.active && state.currentMode === 'streaming') useStream(); }); }

    window.addEventListener('tab-changed', function(ev){
      const tab = ev && ev.detail && ev.detail.tab;
      setActive(tab === 'camera');
    });

    // Fallback: keep camera tab state synchronized even if a custom tab event is missed.
    const cameraCard = el('camera-card');
    if (cameraCard && !cameraCard.__cameraObserverBound) {
      cameraCard.__cameraObserverBound = true;
      const syncFromCard = function(){
        const visible = cameraCard.style.display !== 'none';
        if (!!state.active !== !!visible) setActive(visible);
        if (visible) {
          fetchTimelapseStatus().then(function(st){ if (st) renderTimelapseStatus(st); }).catch(function(){});
        }
      };
      const observer = new MutationObserver(syncFromCard);
      observer.observe(cameraCard, { attributes: true, attributeFilter: ['style', 'class'] });
      syncFromCard();
    }

    document.addEventListener('visibilitychange', function(){
      if (document.hidden){
        stopHealthPolling();
        stopSnapshotTimer();
      } else if (state.active) {
        startHealthPolling();
        if (state.selectedMode === 'snapshot') startSnapshotTimer();
        refreshAll().catch(function(e){
          setTimelapseNote('Refresh failed: ' + (e && e.message ? e.message : 'request error'));
        });
      }
    });

    state.selectedMode = modeSel ? modeSel.value : 'auto';
    const initialTab = (location.hash || '#overview').replace('#', '');
    setActive(initialTab === 'camera');
    // Always attempt one immediate status fill so KPI fields don't remain as placeholders.
    fetchTimelapseStatus().then(function(st){ if (st) renderTimelapseStatus(st); }).catch(function(){});
  }

  if (document.readyState === 'loading') { console.log('[Camera] Registering DOMContentLoaded'); document.addEventListener('DOMContentLoaded', bind); }
  else { console.log('[Camera] DOM ready, calling bind() now'); bind(); }

  window.__cameraReady = true;
})();
