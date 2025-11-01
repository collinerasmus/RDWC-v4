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
          ticks: { maxRotation: 0, autoSkip: true }
        },
        yPh: {
          position: 'left',
          title: { display: true, text: 'pH' }
        },
        yEc: {
          position: 'right',
          title: { display: true, text: 'EC (mS/cm)' },
          grid: { drawOnChartArea: false }
        },
        yTemp: {
          position: 'right',
          title: { display: true, text: 'Temp (°C)' },
          grid: { drawOnChartArea: false }
        }
      },
      elements: {
        line: { tension: 0.3 },
        point: { radius: 0, hoverRadius: 4 }
      }
    }
  });

  const emptyEl = document.getElementById('trendEmpty');
  const btns = document.querySelectorAll('#sensors-card .btn-chip, #trends-card .btn-chip');
  const fromEl = document.getElementById('trendFrom');
  const toEl = document.getElementById('trendTo');
  const applyEl = document.getElementById('trendApply');

  function isoLocal(dt){
    return dt.toISOString().slice(0,16); // yyyy-MM-ddTHH:mm
  }
  
  function rangeFromPreset(preset){
    const now = Date.now();
    let start = now;
    if (preset === '24h') start = now - 24*60*60*1000;
    if (preset === '7d')  start = now - 7*24*60*60*1000;
    if (preset === '30d') start = now - 30*24*60*60*1000;
    if (preset === '90d') start = now - 90*24*60*60*1000;
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
    fromEl.value = isoLocal(new Date(startMs));
    toEl.value = isoLocal(new Date(endMs));
    const { gran, max } = presetParams('grow');
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

  function render(data){
    console.log('[Sensors] render');

    // Series to XY (timestamps in seconds from API, convert to ms)
    const ph    = (data?.series?.ph   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
    const ecRaw = (data?.series?.ec   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
    const temp  = (data?.series?.temp || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
    
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
    const ec = ecRaw.map(p => ({ x:p.x, y: p.y * ecScale }));

    // KPIs (scaled EC)
    const last = arr => (arr && arr.length ? arr[arr.length-1].y : null);
    if (typeof kpiPh   !== 'undefined') kpiPh.textContent   = last(ph)   != null ? Number(last(ph)).toFixed(2) : '—';
    if (typeof kpiEc   !== 'undefined') kpiEc.textContent   = last(ec)   != null ? Number(last(ec)).toFixed(2) : '—';
    if (typeof kpiTemp !== 'undefined') kpiTemp.textContent = last(temp) != null ? Number(last(temp)).toFixed(1) : '—';
    const ecLbl = document.querySelector('.kpi-ec .kpi-label');
    if (ecLbl) ecLbl.textContent = 'EC (mS/cm)';

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

    // IMPORTANT: Set x-axis bounds FIRST before updating data
    if (state.window.start && state.window.end) {
      console.log('[Sensors] setting explicit x-axis bounds:', {
        start: new Date(state.window.start).toISOString(),
        end: new Date(state.window.end).toISOString(),
        data_range: {
          min: Math.min(...ph.map(p=>p.x), ...ec.map(p=>p.x), ...temp.map(p=>p.x)),
          max: Math.max(...ph.map(p=>p.x), ...ec.map(p=>p.x), ...temp.map(p=>p.x))
        }
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

    trendChart.data.datasets = datasets;

    // Empty state toggle
    const hasAny = (ph.length || ec.length || temp.length);
    if (typeof emptyEl !== 'undefined') emptyEl.style.display = hasAny ? 'none' : 'block';

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
    fromEl.value = isoLocal(new Date(start));
    toEl.value   = isoLocal(new Date(end));
    const {gran, max} = presetParams(preset);
    const data = await fetchTrends(new Date(start).toISOString(), new Date(end).toISOString(), gran, max);
    render(data);
    markActive(preset);
    scheduleAutoRefresh();
  }
  
  function markActive(preset){ 
    btns.forEach(b => b.classList.toggle('active', b.dataset.range === preset)); 
  }

  btns.forEach(b => b.addEventListener('click', async () => {
    const preset = b.dataset.range;
    if (preset === 'grow') {
      await loadGrow();
      markActive('grow');
    } else {
      await loadPreset(preset);
    }
  }));
  
  applyEl.addEventListener('click', async () => {
    if(!fromEl.value || !toEl.value) return;
    const startMs = new Date(fromEl.value).getTime();
    const endMs = new Date(toEl.value).getTime();
    state.window = { start: startMs, end: endMs };
    const fromISO = new Date(startMs).toISOString();
    const toISO = new Date(endMs).toISOString();
    const {gran, max} = presetParams('custom');
    const data = await fetchTrends(fromISO, toISO, gran, max);
    render(data);
    markActive('');
    scheduleAutoRefresh();
  });

  // Initial: 24h (changed to match user preference for full window demo)
  loadPreset('24h').catch(err => {
    console.error('[Sensors]', err);
    if (emptyEl) emptyEl.style.display = 'block';
  });
})();
