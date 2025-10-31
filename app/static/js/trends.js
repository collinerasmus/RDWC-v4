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

  const AXES_PREF = {
    ph:   { min: 5.2,  max: 6.5,  title:'pH' },
    ec:   { min: 0.0,  max: 3.0,  title:'EC (mS/cm)' },
    temp: { min: 16.0, max: 28.0, title:'Temp (°C)' }
  };

  function padRange(min, max, pad=0.05){
    const span = Math.max(1e-9, max - min);
    return { min: min - span*pad, max: max + span*pad };
  }

  function autoAxis(pref, series){
    if (!series || !series.length) return { suggestedMin: pref.min, suggestedMax: pref.max };
    let lo = Infinity, hi = -Infinity;
    for (const p of series){ 
      const v = p.y; 
      if (Number.isFinite(v)){ 
        lo = Math.min(lo, v); 
        hi = Math.max(hi, v); 
      } 
    }
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { suggestedMin: pref.min, suggestedMax: pref.max };
    if (lo < pref.min || hi > pref.max){
      const r = padRange(Math.min(lo, pref.min), Math.max(hi, pref.max));
      return { min: r.min, max: r.max }; // hard min/max when out-of-band
    }
    return { suggestedMin: pref.min, suggestedMax: pref.max }; // prefer but allow auto-fit
  }

  function median(arr){
    if (!arr || !arr.length) return null;
    const a = arr.map(v => v.y).filter(Number.isFinite).sort((a,b) => a-b);
    const m = Math.floor(a.length/2);
    return a.length % 2 ? a[m] : (a[m-1]+a[m])/2;
  }

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
          min: AXES_PREF.ph.min,
          max: AXES_PREF.ph.max,
          title: { display: true, text: AXES_PREF.ph.title }
        },
        yEc: {
          position: 'right',
          min: AXES_PREF.ec.min,
          max: AXES_PREF.ec.max,
          title: { display: true, text: AXES_PREF.ec.title },
          grid: { drawOnChartArea: false }
        },
        yTemp: {
          position: 'right',
          min: AXES_PREF.temp.min,
          max: AXES_PREF.temp.max,
          title: { display: true, text: AXES_PREF.temp.title },
          grid: { drawOnChartArea: false }
        }
      },
      elements: {
        line: { borderWidth: 2, tension: 0.3 },
        point: { radius: 1.8, hoverRadius: 4 }
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
    const url = '/api/trends?' + q.toString();
    LAST_RANGE = { fromISO, toISO }; // Track selected range for x-axis frame
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
      temp: j?.series?.temp?.length || 0,
      note: j?.note,
      error: j?.error
    });
    return j;
  }

  function render(data){
    console.log('[Trends] render');
    
    // Build arrays (timestamps in seconds from API, convert to ms for Chart.js)
    const ph    = (data?.series?.ph   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
    const ecRaw = (data?.series?.ec   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
    const temp  = (data?.series?.temp || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));

    // EC unit auto-detection: if median > 20, assume µS/cm and scale to mS/cm
    let ecScale = 1.0;
    const ecMed = median(ecRaw);
    if (ecMed != null && ecMed > 20) {
      ecScale = 1/1000;
      console.log('[Trends] EC unit detection: scaling µS/cm → mS/cm');
    }
    const ec = ecRaw.map(p => ({ x: p.x, y: p.y * ecScale }));
    
    // Update EC KPI label
    const kpiLbl = document.querySelector('.kpi-ec .kpi-label');
    if (kpiLbl) kpiLbl.textContent = 'EC (mS/cm)';

    // Compute y-axis targets (auto-fit with grow preferences)
    const axPh   = autoAxis(AXES_PREF.ph,   ph);
    const axEc   = autoAxis(AXES_PREF.ec,   ec);
    const axTemp = autoAxis(AXES_PREF.temp, temp);

    // 1) Force x-axis to selected window (even if data is sparse)
    if (LAST_RANGE.fromISO && LAST_RANGE.toISO){
      trendChart.options.scales.x.min = new Date(LAST_RANGE.fromISO).getTime();
      trendChart.options.scales.x.max = new Date(LAST_RANGE.toISO).getTime();
    } else {
      delete trendChart.options.scales.x.min;
      delete trendChart.options.scales.x.max;
    }

    // 2) Apply y-axes auto-fit
    Object.assign(trendChart.options.scales.yPh,   axPh);
    Object.assign(trendChart.options.scales.yEc,   axEc);
    Object.assign(trendChart.options.scales.yTemp, axTemp);

    // 3) Build datasets
    const datasets = [];
    if (ph.length)   datasets.push({ 
      id:'ph',   yAxisID:'yPh',   label:'pH',        
      data:ph,   borderColor:COLORS.ph,   backgroundColor:COLORS.ph,   
      fill:false, spanGaps:true 
    });
    if (ec.length)   datasets.push({ 
      id:'ec',   yAxisID:'yEc',   label:'EC',        
      data:ec,   borderColor:COLORS.ec,   backgroundColor:COLORS.ec,   
      fill:false, spanGaps:true 
    });
    if (temp.length) datasets.push({ 
      id:'temp', yAxisID:'yTemp', label:'Temp (°C)', 
      data:temp, borderColor:COLORS.temp, backgroundColor:COLORS.temp, 
      fill:false, spanGaps:true 
    });
    trendChart.data.datasets = datasets;

    // Update KPIs (using displayed units for EC)
    const last = arr => arr && arr.length ? arr[arr.length-1].y : null;
    if (kpiPh)   kpiPh.textContent   = (last(ph)   != null) ? Number(last(ph)).toFixed(2) : '—';
    if (kpiEc)   kpiEc.textContent   = (last(ec)   != null) ? Number(last(ec)).toFixed(2) : '—';
    if (kpiTemp) kpiTemp.textContent = (last(temp) != null) ? Number(last(temp)).toFixed(1) : '—';

    trendChart.update('none');

    const hasAny = (ph.length || ec.length || temp.length);
    emptyEl.style.display = hasAny ? 'none' : 'block';
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
