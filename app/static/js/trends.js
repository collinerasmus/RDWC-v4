/* global Chart */
(function(){
  const chartEl = document.getElementById('trendChart');
  if(!chartEl || typeof Chart === 'undefined') return;

  const COLORS = {
    ph:   '#1f77b4', // blue
    ec:   '#2ca02c', // green
    temp: '#d62728', // red
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
        y: {
          beginAtZero: false
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
  
  async function fetchTrends(fromISO, toISO){
    const q = new URLSearchParams();
    if (fromISO) q.set('from', fromISO);
    if (toISO)   q.set('to', toISO);
    const res = await fetch('/api/trends?' + q.toString(), { cache: 'no-store' });
    if (!res.ok) throw new Error('trends_fetch_failed ' + res.status);
    return res.json();
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
    const ph   = toXY(data?.series?.ph);
    const ec   = toXY(data?.series?.ec);
    const temp = toXY(data?.series?.temp);

    const datasets = [];
    if (ph?.length)   datasets.push({ 
      id:'ph',   
      label:'pH',         
      data:ph,   
      borderColor:COLORS.ph,   
      backgroundColor:COLORS.ph,   
      fill:false 
    });
    if (ec?.length)   datasets.push({ 
      id:'ec',   
      label:'EC',         
      data:ec,   
      borderColor:COLORS.ec,   
      backgroundColor:COLORS.ec,   
      fill:false 
    });
    if (temp?.length) datasets.push({ 
      id:'temp', 
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
    const data = await fetchTrends(from.toISOString(), to.toISOString());
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
    const data = await fetchTrends(fromISO, toISO);
    render(data);
    markActive('');
  });

  // Initial: 7d
  loadPreset('7d').catch(err => {
    console.error('[Trends]', err);
    emptyEl.style.display = 'block';
  });
})();
