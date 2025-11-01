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

  let LAST_RANGE = { fromISO: null, toISO: null };

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
          bounds: 'ticks'
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
  const btns = document.querySelectorAll('#trends-card .btn-chip');
  const fromEl = document.getElementById('trendFrom');
  const toEl = document.getElementById('trendTo');
  const applyEl = document.getElementById('trendApply');

  function isoLocal(dt){
    return dt.toISOString().slice(0,16); // yyyy-MM-ddTHH:mm
  }
  
  function rangeFromPreset(preset){
    const now = new Date();
    let from = new Date(now);
    if (preset === '24h') from.setHours(now.getHours() - 24);
    if (preset === '7d')  from.setDate(now.getDate() - 7);
    if (preset === '30d') from.setDate(now.getDate() - 30);
    if (preset === '90d') from.setDate(now.getDate() - 90);
    return { from, to: now };
  }

  function presetParams(preset){
    // All caps are conservative to keep UI snappy
    if (preset === '24h') return { gran: 60,   max: 1200 };  // avg per minute, <=1200pts
    if (preset === '7d')  return { gran: 300,  max: 2000 };  // 5-min buckets
    if (preset === '30d') return { gran: 900,  max: 2500 };  // 15-min buckets
    if (preset === '90d') return { gran: 3600, max: 2500 };  // hourly buckets
    if (preset === 'grow') return { gran: 3600, max: 3000 }; // hourly, up to 3000 pts
    return { gran: 300, max: 2000 }; // default (custom)
  }

  async function loadGrow(){
    let startISO;
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
    const nowISO = new Date().toISOString();
    fromEl.value = isoLocal(new Date(startISO));
    toEl.value = isoLocal(new Date(nowISO));
    const { gran, max } = presetParams('grow');
    const data = await fetchTrends(startISO, nowISO, gran, max);
    render(data);
  }
  
  async function fetchTrends(fromISO, toISO, gran, max){
    const q = new URLSearchParams();
    if (fromISO) q.set('from', fromISO);
    if (toISO)   q.set('to', toISO);
    if (gran)    q.set('gran', String(gran));
    if (max)     q.set('max',  String(max));
    LAST_RANGE = { fromISO, toISO };
    const url = '/api/trends?' + q.toString();
    console.log('[Trends] GET', url);
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) {
      console.error('[Trends] fetch failed', res.status);
      return { series: { ph:[], ec:[], temp:[] } };
    }
    const j = await res.json();
    console.log('[Trends] data', {
      ph: j?.series?.ph?.length || 0,
      ec: j?.series?.ec?.length || 0,
      temp: j?.series?.temp?.length || 0
    });
    return j;
  }

  function render(data){
    console.log('[Trends] render');

    // Series to XY (timestamps in seconds from API)
    const ph    = (data?.series?.ph   || []).map(p => ({ x:new Date(p.ts * 1000), y:Number(p.value) }));
    const ecRaw = (data?.series?.ec   || []).map(p => ({ x:new Date(p.ts * 1000), y:Number(p.value) }));
    const temp  = (data?.series?.temp || []).map(p => ({ x:new Date(p.ts * 1000), y:Number(p.value) }));

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

    // Force x-axis to selected window using Date objects
    if (LAST_RANGE.fromISO && LAST_RANGE.toISO){
      trendChart.options.scales.x.min = new Date(LAST_RANGE.fromISO);
      trendChart.options.scales.x.max = new Date(LAST_RANGE.toISO);
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

    trendChart.update('none');
  }

  async function loadPreset(preset){
    const { from, to } = rangeFromPreset(preset);
    fromEl.value = isoLocal(from);
    toEl.value   = isoLocal(to);
    const {gran, max} = presetParams(preset);
    const data = await fetchTrends(from.toISOString(), to.toISOString(), gran, max);
    render(data);
    markActive(preset);
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
    const fromISO = new Date(fromEl.value).toISOString();
    const toISO   = new Date(toEl.value).toISOString();
    const {gran, max} = presetParams('custom'); // default custom tuning
    const data = await fetchTrends(fromISO, toISO, gran, max);
    render(data);
    markActive('');
  });

  // Initial: 7d
  loadPreset('7d').catch(err => {
    console.error('[Trends]', err);
    emptyEl.style.display = 'block';
  });
})();
