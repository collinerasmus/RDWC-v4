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

  const AXES = {
    ph:   { id:'yPh',   min:5.2,  max:6.5,  title:'pH' },
    ec:   { id:'yEc',   min:0.0,  max:3.0,  title:'EC (mS/cm)' },
    temp: { id:'yTemp', min:16.0, max:28.0, title:'Temp (°C)' }
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
          min: AXES.ph.min,
          max: AXES.ph.max,
          title: { display: true, text: AXES.ph.title }
        },
        yEc: {
          position: 'right',
          min: AXES.ec.min,
          max: AXES.ec.max,
          title: { display: true, text: AXES.ec.title },
          grid: { drawOnChartArea: false }
        },
        yTemp: {
          position: 'right',
          min: AXES.temp.min,
          max: AXES.temp.max,
          title: { display: true, text: AXES.temp.title },
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
    return { gran: 300, max: 2000 }; // default (custom)
  }
  
  async function fetchTrends(fromISO, toISO, gran, max){
    const q = new URLSearchParams();
    if (fromISO) q.set('from', fromISO);
    if (toISO)   q.set('to', toISO);
    if (gran)    q.set('gran', String(gran));
    if (max)     q.set('max',  String(max));
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
      temp: j?.series?.temp?.length || 0,
      note: j?.note,
      error: j?.error
    });
    return j;
  }
  
  function toXY(series){ 
    return (series || []).map(p => ({ 
      x: p.ts * 1000, // Convert Unix timestamp to milliseconds
      y: Number(p.value) 
    })); 
  }

  function updateKPIs(data){
    const last = (arr)=> (arr && arr.length ? arr[arr.length-1].value : null);
    const ph   = data?.series?.ph   || [];
    const ec   = data?.series?.ec   || [];
    const temp = data?.series?.temp || [];
    if (kpiPh)   kpiPh.textContent   = last(ph)   != null ? Number(last(ph)).toFixed(2) : '—';
    if (kpiEc)   kpiEc.textContent   = last(ec)   != null ? Number(last(ec)).toFixed(2) : '—';
    if (kpiTemp) kpiTemp.textContent = last(temp) != null ? Number(last(temp)).toFixed(1) : '—';
  }

  function render(data){
    console.log('[Trends] render');
    const ph   = toXY(data?.series?.ph);
    const ec   = toXY(data?.series?.ec);
    const temp = toXY(data?.series?.temp);

    const datasets = [];
    if (ph?.length)   datasets.push({ 
      id:'ph',
      yAxisID:'yPh',
      label:'pH',         
      data:ph,   
      borderColor:COLORS.ph,   
      backgroundColor:COLORS.ph,   
      fill:false 
    });
    if (ec?.length)   datasets.push({ 
      id:'ec',
      yAxisID:'yEc',
      label:'EC',         
      data:ec,   
      borderColor:COLORS.ec,   
      backgroundColor:COLORS.ec,   
      fill:false 
    });
    if (temp?.length) datasets.push({ 
      id:'temp',
      yAxisID:'yTemp',
      label:'Temp (°C)',  
      data:temp, 
      borderColor:COLORS.temp, 
      backgroundColor:COLORS.temp, 
      fill:false 
    });

    trendChart.data.datasets = datasets;
    trendChart.update('none');

    const hasAny = (ph?.length || ec?.length || temp?.length);
    emptyEl.style.display = hasAny ? 'none' : 'block';

    updateKPIs(data);
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

  btns.forEach(b => b.addEventListener('click', () => loadPreset(b.dataset.range)));
  
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
