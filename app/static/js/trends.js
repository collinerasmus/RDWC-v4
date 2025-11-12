/* global Chart */
(function(){
  console.log('[Trends] init');
  const chartEl = document.getElementById('trendChart');
  if(!chartEl) {
    console.error('[Trends] trendChart canvas not found');
    return;
  }
  if(typeof Chart === 'undefined') {
    console.error('[Trends] Chart.js not loaded');
    return;
  }

  const COLORS = {
    ph:   '#1f77b4', // blue
    ec:   '#2ca02c', // green
    temp: '#d62728', // red
  };

  const state = {
    window: { start: null, end: null }, // epoch ms for explicit x-axis bounds
    refreshTimer: null
  };

  const kpiPh   = document.getElementById('kpiPh');
  const kpiEc   = document.getElementById('kpiEc');
  const kpiTemp = document.getElementById('kpiTemp');

  let trendChart = new Chart(chartEl, {
    type: 'line',
    data: { datasets: [] },
    options: {
      animation: false,
      parsing: false,
      normalized: true,
      maintainAspectRatio: true,
      spanGaps: true,
      interaction: { mode: 'nearest', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          labels: { usePointStyle: true, boxWidth: 10, padding: 12, maxWidth: 400 }
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = Number(ctx.raw?.y);
              if (ctx.dataset.id === 'ph')   return ` pH: ${v.toFixed(2)}`;
              if (ctx.dataset.id === 'ec')   return ` EC: ${v.toFixed(2)} mS/cm`;
              if (ctx.dataset.id === 'temp') return ` Temp: ${v.toFixed(1)} °C`;
              return ` ${v}`;
            }
          }
        },
        decimation: { enabled: true, algorithm: 'lttb' }
      },
      scales: {
        x: {
          type: 'time',
          time: { 
            tooltipFormat: 'yyyy-MM-dd HH:mm', 
            displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'MMM d' } 
          },
          ticks: { maxRotation: 0, autoSkip: true },
          grid: { color: 'rgba(148,163,184,0.15)', drawTicks: false }
        },
        yPh: {
          position: 'left',
          title: { display: true, text: 'pH' },
          grid: { color: 'rgba(148,163,184,0.12)', drawTicks:false }
        },
        yEc: {
          position: 'right',
          title: { display: true, text: 'EC (mS/cm)' },
          grid: { color: 'rgba(148,163,184,0.12)', drawTicks:false }
        },
        yTemp: {
          position: 'right',
          title: { display: true, text: 'Temp (°C)' },
          grid: { color: 'rgba(148,163,184,0.12)', drawTicks:false }
        }
      },
      elements: {
        line: { tension: 0.3 },
        point: { radius: 0, hoverRadius: 4 }
      }
    }
  });

  const emptyEl = document.getElementById('trendEmpty');
  const selectEl = document.getElementById('trendRangeSelect');
  const customInputsEl = document.getElementById('trendCustomInputs');
  const fromEl = document.getElementById('trendFrom');
  const toEl = document.getElementById('trendTo');
  const applyEl = document.getElementById('trendApply');

  function rangeFromPreset(preset){
    const now = Date.now();
    let start = now;
    if (preset === '24h') start = now - 24*60*60*1000;
    if (preset === '7d')  start = now - 7*24*60*60*1000;
    if (preset === '30d') start = now - 30*24*60*60*1000;
    if (preset === '90d') start = now - 90*24*60*60*1000;
    if (preset === 'today'){
      const d = new Date();
      d.setHours(0,0,0,0);
      start = d.getTime();
    }
    return { start, end: now };
  }

  function presetParams(preset){
    // All caps are conservative to keep UI snappy
    if (preset === '24h') return { gran: 60,   max: 1500 };  // avg per minute, 24h = 1440 mins
    if (preset === '7d')  return { gran: 300,  max: 2100 };  // 5-min buckets, 7d = 2016 pts
    if (preset === '30d') return { gran: 900,  max: 3000 };  // 15-min buckets
    if (preset === '90d') return { gran: 3600, max: 2500 };  // hourly buckets
    if (preset === 'grow') return { gran: 3600, max: 3000 }; // hourly, up to 3000 pts
    return { gran: 300, max: 2000 }; // default (custom)
  }

  function formatForInput(ts) {
    // Format timestamp for datetime-local input (YYYY-MM-DDTHH:mm)
    const d = new Date(ts);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth()+1).padStart(2,'0');
    const dd = String(d.getDate()).padStart(2,'0');
    const hh = String(d.getHours()).padStart(2,'0');
    const min = String(d.getMinutes()).padStart(2,'0');
    return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
  }

  async function loadGrow(){
    let startISO;
    // Try to get grow_start_date from settings
    const growStartDate = window.rdwcSettings?.get('general.grow_start_date');
    if (growStartDate) {
      // Use grow start date at 00:00 local time
      try {
        const startDate = new Date(growStartDate + 'T00:00:00');
        startISO = startDate.toISOString();
      } catch(e) {
        console.warn('Invalid grow_start_date format, using fallback:', e);
      }
    }
    
    // Fallback to API or 30 days ago
    if (!startISO) {
      try {
        const resp = await fetch('/api/grow/start');
        if (!resp.ok) throw new Error('Grow start fetch failed');
        const data = await resp.json();
        startISO = data.start;
      } catch(err){
        console.error('Failed to fetch grow start:', err);
        const fallback = new Date();
        fallback.setDate(fallback.getDate() - 30);
        startISO = fallback.toISOString();
      }
    }
    
    const nowISO = new Date().toISOString();
    const startMs = new Date(startISO).getTime();
    const endMs = new Date(nowISO).getTime();
    state.window = { start: startMs, end: endMs };
    fromEl.value = formatForInput(startMs);
    toEl.value = formatForInput(endMs);
    const { gran, max } = presetParams('grow');
    await fetchDoseEvents(); // Fetch dose markers
    const data = await fetchTrends(startISO, nowISO, gran, max);
    render(data);
    scheduleAutoRefresh();
  }
  
  async function fetchTrends(fromISO, toISO, gran, max){
    const q = new URLSearchParams();
    if (fromISO) q.set('from', fromISO);
    if (toISO)   q.set('to', toISO);
    if (gran)    q.set('gran', String(gran));
    if (max)     q.set('max',  String(max));
    
    // Try multiple endpoints with fallback
    const endpoints = [
      '/api/trends?' + q.toString(),
      '/history?' + q.toString(),
      '/api/history?' + q.toString()
    ];
    
    for (const url of endpoints) {
      try {
        console.log('[Sensors] GET', url);
        const res = await fetch(url, { cache: 'no-store' });
        if (res.ok) {
          const j = await res.json();
          console.log('[Sensors] data', {
            ph: j?.series?.ph?.length || 0,
            ec: j?.series?.ec?.length || 0,
            temp: j?.series?.temp?.length || 0
          });
          return j;
        }
      } catch(err) {
        console.warn('[Sensors] failed:', url, err);
      }
    }
    
    console.error('[Sensors] all endpoints failed');
    return { series: { ph:[], ec:[], temp:[] } };
  }

  // Dose markers cache
  let doseEventsCache = [];
  let lastDoseFetch = 0;

  async function fetchDoseEvents(){
    // Cache for 10s to avoid repeated fetches during chart updates
    if (Date.now() - lastDoseFetch < 10000 && doseEventsCache.length > 0) {
      return doseEventsCache;
    }
    
    try {
      const hours = state.window.start ? Math.ceil((Date.now() - state.window.start) / (3600*1000)) : 24;
      const r = await fetch(`/api/dose/recent?hours=${Math.min(hours, 168)}`, {cache:'no-store'});
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      doseEventsCache = data.events || [];
      lastDoseFetch = Date.now();
      return doseEventsCache;
    } catch(e) {
      console.warn('[Trends] Failed to fetch dose events:', e);
      return [];
    }
  }

  function addDoseMarkers(datasets, phMin, phMax, ecMin, ecMax){
    // Filter events to visible time range
    const events = doseEventsCache.filter(e => {
      if (!state.window.start || !state.window.end) return true;
      const ts_ms = e.ts * 1000;
      return ts_ms >= state.window.start && ts_ms <= state.window.end;
    });
    
    if (events.length === 0) return;
    
    // Group events by pump type
    const phUpEvents = events.filter(e => e.pump === 'ph_up' && !e.blocked_by);
    const growEvents = events.filter(e => e.pump === 'grow' && !e.blocked_by);
    const microEvents = events.filter(e => e.pump === 'micro' && !e.blocked_by);
    const bloomEvents = events.filter(e => e.pump === 'bloom' && !e.blocked_by);
    
    // Pump colors (subtle for markers)
    const DOSE_COLORS = {
      ph_up: '#fbbf24',  // amber
      grow: '#6ee7b7',   // emerald
      micro: '#67e8f9',  // cyan
      bloom: '#c084fc'   // purple
    };
    
    // Add pH Up markers on pH axis
    if (phUpEvents.length > 0) {
      const y = phMin + (phMax - phMin) * 0.95; // near top
      datasets.push({
        id: 'dose_ph_up',
        type: 'scatter',
        yAxisID: 'yPh',
        label: '↑ pH Up',
        data: phUpEvents.map(e => ({ x: e.ts * 1000, y })),
        pointRadius: 5,
        pointStyle: 'triangle',
        pointBackgroundColor: DOSE_COLORS.ph_up,
        pointBorderColor: DOSE_COLORS.ph_up,
        pointBorderWidth: 1,
        showLine: false
      });
    }
    
    // Add nutrient markers on EC axis (stacked vertically)
    const ecMarkerY = [
      ecMin + (ecMax - ecMin) * 0.90, // grow (top)
      ecMin + (ecMax - ecMin) * 0.85, // micro
      ecMin + (ecMax - ecMin) * 0.80  // bloom (bottom)
    ];
    
    if (growEvents.length > 0) {
      datasets.push({
        id: 'dose_grow',
        type: 'scatter',
        yAxisID: 'yEc',
        label: '↑ Grow',
        data: growEvents.map(e => ({ x: e.ts * 1000, y: ecMarkerY[0] })),
        pointRadius: 5,
        pointStyle: 'circle',
        pointBackgroundColor: DOSE_COLORS.grow,
        pointBorderColor: DOSE_COLORS.grow,
        pointBorderWidth: 1,
        showLine: false
      });
    }
    
    if (microEvents.length > 0) {
      datasets.push({
        id: 'dose_micro',
        type: 'scatter',
        yAxisID: 'yEc',
        label: '↑ Micro',
        data: microEvents.map(e => ({ x: e.ts * 1000, y: ecMarkerY[1] })),
        pointRadius: 5,
        pointStyle: 'circle',
        pointBackgroundColor: DOSE_COLORS.micro,
        pointBorderColor: DOSE_COLORS.micro,
        pointBorderWidth: 1,
        showLine: false
      });
    }
    
    if (bloomEvents.length > 0) {
      datasets.push({
        id: 'dose_bloom',
        type: 'scatter',
        yAxisID: 'yEc',
        label: '↑ Bloom',
        data: bloomEvents.map(e => ({ x: e.ts * 1000, y: ecMarkerY[2] })),
        pointRadius: 5,
        pointStyle: 'circle',
        pointBackgroundColor: DOSE_COLORS.bloom,
        pointBorderColor: DOSE_COLORS.bloom,
        pointBorderWidth: 1,
        showLine: false
      });
    }
  }

  function render(data){
    console.log('[Sensors] render');

    // Series to XY (timestamps in seconds from API, convert to ms)
    let ph    = (data?.series?.ph   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
    let ecRaw = (data?.series?.ec   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
    let temp  = (data?.series?.temp || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));

    // Helper: interpolate single-sample gaps for smoother rendering
    function interpSingles(series){
      if (!series || series.length < 3) return series;
      // estimate expected interval as median delta
      const deltas = [];
      for(let i=1;i<series.length;i++){ const dt = series[i].x - series[i-1].x; if (dt>0) deltas.push(dt); }
      deltas.sort((a,b)=>a-b);
      const mid = Math.floor(deltas.length/2);
      const expected = deltas.length ? (deltas.length%2? deltas[mid] : (deltas[mid-1]+deltas[mid])/2) : 0;
      if (!expected) return series;
      const out = [series[0]];
      for(let i=1;i<series.length;i++){
        const prev = series[i-1], cur = series[i];
        const dt = cur.x - prev.x;
        if (dt > 1.5*expected && dt <= 2.5*expected && Number.isFinite(prev.y) && Number.isFinite(cur.y)){
          // insert midpoint linear interpolation
          const midx = prev.x + Math.round(dt/2);
          const midy = prev.y + (cur.y - prev.y)/2;
          out.push({ x:midx, y: midy });
        }
        out.push(cur);
      }
      return out;
    }
    ph = interpSingles(ph);
    temp = interpSingles(temp);

    // Forward-fill temperature across small gaps using union of PH/EC timestamps (visual continuity)
    function fillForward(series, referenceXs, maxGapMs){
      if (!series || series.length === 0 || !referenceXs || referenceXs.length === 0) return series;
      const sortedRefs = Array.from(new Set(referenceXs)).sort((a,b)=>a-b);
      const out = [];
      let cursor = 0;
      let lastVal = null;
      let lastTs = null;
      for (const x of sortedRefs){
        while (cursor < series.length && series[cursor].x <= x){
          lastVal = series[cursor].y;
          lastTs = series[cursor].x;
          cursor++;
        }
        if (lastVal != null && lastTs != null && (x - lastTs) <= maxGapMs){
          out.push({ x, y: lastVal });
        }
      }
      // keep original points too to preserve exact samples
      const merged = [...series, ...out];
      merged.sort((a,b)=>a.x-b.x);
      // de-dup by x, keep last
      const dedup = [];
      let prevX = null;
      for (const p of merged){ if (p.x !== prevX){ dedup.push(p); prevX = p.x; } else { dedup[dedup.length-1] = p; } }
      return dedup;
    }
    try{
      const refXs = [...ph.map(p=>p.x), ...ecRaw.map(p=>p.x)];
      // Consider gaps up to 20 minutes safe to carry
      temp = fillForward(temp, refXs, 20*60*1000);
    }catch(_){ /* noop */ }
    
    // Debug: Check actual data time range
    if (ph.length) {
      console.log('[Sensors] pH data time range:', {
        first: new Date(ph[0].x).toISOString(),
        last: new Date(ph[ph.length-1].x).toISOString()
      });
    }

    // EC unit autodetect: if median > 20, assume µS/cm and convert to mS/cm
    function median(arr){
      if (!arr || !arr.length) return null;
      const a = arr.map(v=>v.y).filter(Number.isFinite).sort((a,b)=>a-b);
      const m = Math.floor(a.length/2);
      return a.length % 2 ? a[m] : (a[m-1]+a[m])/2;
    }
    let ecScale = 1.0;
    if (median(ecRaw) > 20) ecScale = 1/1000; // µS -> mS
  let ec = ecRaw.map(p => ({ x:p.x, y: p.y * ecScale }));
  ec = interpSingles(ec);

    // KPIs
    const last = arr => (arr && arr.length ? arr[arr.length-1].y : null);
    if (kpiPh) kpiPh.textContent = last(ph) != null ? Number(last(ph)).toFixed(2) : '—';
    if (kpiEc) {
      const ecVal = last(ec);
      kpiEc.textContent = ecVal != null ? Number(ecVal).toFixed(2) : '—';
    }
    if (kpiTemp) kpiTemp.textContent = last(temp) != null ? Number(last(temp)).toFixed(1) : '—';

    // Preferred grow ranges; we will expand if data is out-of-band
    const PREF = {
      ph:   { min: 5.0,  max: 7.8 },
      ec:   { min: 0.0,  max: 3.0 },
      temp: { min: 16.0, max: 28.0 }
    };
    function dataMinMax(series){
      let lo = Infinity, hi = -Infinity;
      for (const p of series){ if (Number.isFinite(p.y)){ lo = Math.min(lo, p.y); hi = Math.max(hi, p.y); } }
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
      return { lo, hi };
    }
    function padded(min, max, pad=0.05){
      const span = Math.max(1e-9, max - min);
      return { min: min - span*pad, max: max + span*pad };
    }
    function chooseAxis(pref, series){
      const mm = dataMinMax(series);
      if (!mm) return { min: pref.min, max: pref.max };
      const outOfBand = (mm.lo < pref.min) || (mm.hi > pref.max);
      if (outOfBand) return padded(Math.min(mm.lo, pref.min), Math.max(mm.hi, pref.max));
      // keep preferred but let Chart adjust within soft bounds
      return { min: pref.min, max: pref.max };
    }
  const aPh   = chooseAxis(PREF.ph,   ph);
  const aEc   = chooseAxis(PREF.ec,   ec);
  const aTemp = chooseAxis(PREF.temp, temp);
  // Auto-fit axis by applying dynamic padding (already handled in chooseAxis when out-of-band)

  // IMPORTANT: Set x-axis bounds to requested timeframe (not data-derived)
    if (state.window.start && state.window.end) {
      console.log('[Sensors] Chart x-axis spans full requested timeframe:', {
        start: new Date(state.window.start).toISOString(),
        end: new Date(state.window.end).toISOString()
      });
        trendChart.options.scales.x.min = state.window.start;
        trendChart.options.scales.x.max = state.window.end;
    } else {
      delete trendChart.options.scales.x.min;
      delete trendChart.options.scales.x.max;
    }

    // IMPORTANT: clear any previous suggestedMin/suggestedMax to avoid conflicts
    ['yPh','yEc','yTemp'].forEach(id => {
      delete trendChart.options.scales[id].suggestedMin;
      delete trendChart.options.scales[id].suggestedMax;
      delete trendChart.options.scales[id].min;
      delete trendChart.options.scales[id].max;
    });

    // Apply hard min/max so lines are guaranteed visible
    trendChart.options.scales.yPh.min   = aPh.min;   trendChart.options.scales.yPh.max   = aPh.max;
    trendChart.options.scales.yEc.min   = aEc.min;   trendChart.options.scales.yEc.max   = aEc.max;
    trendChart.options.scales.yTemp.min = aTemp.min; trendChart.options.scales.yTemp.max = aTemp.max;

    // Build datasets (ensure visible, small point radius for speed)
    const datasets = [];
    if (ph.length)   datasets.push({ id:'ph',   yAxisID:'yPh',   label:'pH',        data:ph,   borderWidth:2, borderColor:COLORS.ph,   backgroundColor:COLORS.ph,   pointRadius:0, spanGaps:true });
    if (ec.length)   datasets.push({ id:'ec',   yAxisID:'yEc',   label:'EC',        data:ec,   borderWidth:2, borderColor:COLORS.ec,   backgroundColor:COLORS.ec,   pointRadius:0, spanGaps:true });
    if (temp.length) datasets.push({ id:'temp', yAxisID:'yTemp', label:'Temp (°C)', data:temp, borderWidth:2, borderColor:COLORS.temp, backgroundColor:COLORS.temp, pointRadius:0, spanGaps:true });

    // Add dose markers as scatter datasets
    addDoseMarkers(datasets, aPh.min, aPh.max, aEc.min, aEc.max);

    trendChart.data.datasets = datasets;

    // If very few points, synthesize boundary points to avoid flatline illusion
    function synthBounds(series){
      if (!state.window.start || !state.window.end) return series;
      if (!series || series.length === 0) return series;
      if (series.length >= 2) return series;
      // duplicate a single point at both bounds
      const v = series[0].y;
      return [ {x: state.window.start, y: v}, {x: state.window.end, y: v} ];
    }
    trendChart.data.datasets.forEach(ds => { ds.data = synthBounds(ds.data); });

    // Empty state toggle
    const hasAny = (ph.length || ec.length || temp.length);
    if (emptyEl) emptyEl.style.display = hasAny ? 'none' : 'block';

    // Force full chart update with recalculation
    trendChart.update();
  }

  function scheduleAutoRefresh() {
    // Cancel existing timer
    if (state.refreshTimer) {
      clearTimeout(state.refreshTimer);
      state.refreshTimer = null;
    }

    // If window end is within 5 min of now, auto-refresh using configured interval
    const now = Date.now();
    if (state.window.end && Math.abs(state.window.end - now) < 5*60*1000) {
      console.log('[Sensors] Auto-refresh enabled (near real-time)');
      state.refreshTimer = setTimeout(async () => {
        const fromISO = new Date(state.window.start).toISOString();
        const toISO = new Date(state.window.end).toISOString();
        const preset = detectPreset();
        const { gran, max } = presetParams(preset || 'custom');
        const data = await fetchTrends(fromISO, toISO, gran, max);
        render(data);
        scheduleAutoRefresh(); // reschedule
      }, Math.max(1000, parseInt((window.APP_POLL && window.APP_POLL.sensors) || 5000, 10)));
    }
  }

  function detectPreset() {
    if (!state.window.start || !state.window.end) return null;
    const span = state.window.end - state.window.start;
    const near24h = Math.abs(span - 24*60*60*1000) < 60*1000;
    const near7d = Math.abs(span - 7*24*60*60*1000) < 60*1000;
    const near30d = Math.abs(span - 30*24*60*60*1000) < 60*1000;
    const near90d = Math.abs(span - 90*24*60*60*1000) < 60*1000;
    if (near24h) return '24h';
    if (near7d) return '7d';
    if (near30d) return '30d';
    if (near90d) return '90d';
    return 'custom';
  }

  async function loadPreset(preset){
    const { start, end } = rangeFromPreset(preset);
    state.window = { start, end };
    fromEl.value = formatForInput(start);
    toEl.value   = formatForInput(end);
    const {gran, max} = presetParams(preset);
    await fetchDoseEvents(); // Fetch dose markers
    const data = await fetchTrends(new Date(start).toISOString(), new Date(end).toISOString(), gran, max);
    render(data);
    scheduleAutoRefresh();
  }

  // Dropdown change handler
  if (selectEl) {
    selectEl.addEventListener('change', async () => {
      const val = selectEl.value;
      const isCustom = (val === 'custom');
      
      // Enable/disable inputs based on selection
      if (fromEl) fromEl.disabled = !isCustom;
      if (toEl) toEl.disabled = !isCustom;
      if (applyEl) applyEl.disabled = !isCustom;
      
      if (!isCustom) {
        // Load preset and populate inputs with resulting timeframe
        if (val === 'grow') {
          await loadGrow();
        } else {
          await loadPreset(val);
        }
      }
    });
  }
  
  // Custom range apply button
  if (applyEl) {
    applyEl.addEventListener('click', async () => {
      if(!fromEl.value || !toEl.value) return;
      const startMs = new Date(fromEl.value).getTime();
      const endMs = new Date(toEl.value).getTime();
      state.window = { start: startMs, end: endMs };
      const fromISO = new Date(startMs).toISOString();
      const toISO = new Date(endMs).toISOString();
      const {gran, max} = presetParams('custom');
      await fetchDoseEvents(); // Fetch dose markers
      const data = await fetchTrends(fromISO, toISO, gran, max);
      render(data);
      scheduleAutoRefresh();
    });
  }

  // Initial: 24h (changed to match user preference for full window demo)
  loadPreset('24h').catch(err => {
    console.error('[Sensors]', err);
    if (emptyEl) emptyEl.style.display = 'block';
  });
})();

// Expose current trends window for export
window.trendsWindow = window.trendsWindow || {};
try{
  // Proxy state updates into global for exportCsv
  (function(){
    const _set = (start,end)=>{ window.trendsWindow.start = start; window.trendsWindow.end = end; };
    const orig = document.getElementById('trendApply');
    if (orig){
      orig.addEventListener('click', ()=>{
        const fromEl = document.getElementById('trendFrom');
        const toEl = document.getElementById('trendTo');
        if (fromEl && toEl && fromEl.value && toEl.value){
          _set(new Date(fromEl.value).getTime(), new Date(toEl.value).getTime());
        }
      });
    }
    // Also hook into dropdown to update global window after load
    const sel = document.getElementById('trendRangeSelect');
    if (sel){
      sel.addEventListener('change', ()=>{
        const fromEl = document.getElementById('trendFrom');
        const toEl = document.getElementById('trendTo');
        if (fromEl && toEl && fromEl.value && toEl.value){
          _set(new Date(fromEl.value).getTime(), new Date(toEl.value).getTime());
        }
      });
    }
  })();
}catch(e){ /* ignore */ }
