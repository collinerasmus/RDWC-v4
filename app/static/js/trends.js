/* global Chart */
(function(){
  // Wait for DOM to be ready before initialization
  if (document.readyState !== 'loading') {
    initTrends();
  } else {
    document.addEventListener('DOMContentLoaded', initTrends);
  }
  
  function initTrends() {
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

    // KPI elements managed by sensors.js; trends only renders chart

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
      if (preset === '24h') return { gran: 60,   max: 1500 };
      if (preset === '7d')  return { gran: 300,  max: 2100 };
      if (preset === '30d') return { gran: 900,  max: 3000 };
      if (preset === '90d') return { gran: 3600, max: 2500 };
      if (preset === 'grow') return { gran: 3600, max: 3000 };
      return { gran: 300, max: 2000 };
    }

    function formatForInput(ts) {
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
      const growStartDate = window.rdwcSettings?.get('general.grow_start_date');
      if (growStartDate) {
        try {
          const startDate = new Date(growStartDate + 'T00:00:00');
          startISO = startDate.toISOString();
        } catch(e) {
          console.warn('Invalid grow_start_date format, using fallback:', e);
        }
      }
      
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
      await fetchDoseEvents();
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

    let doseEventsCache = [];
    let lastDoseFetch = 0;

    async function fetchDoseEvents(){
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

    function render(data){
      console.log('[Sensors] render');

      let ph    = (data?.series?.ph   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
      let ecRaw = (data?.series?.ec   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
      let temp  = (data?.series?.temp || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));

      function interpSingles(series){
        if (!series || series.length < 3) return series;
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
        const merged = [...series, ...out];
        merged.sort((a,b)=>a.x-b.x);
        const dedup = [];
        let prevX = null;
        for (const p of merged){ if (p.x !== prevX){ dedup.push(p); prevX = p.x; } else { dedup[dedup.length-1] = p; } }
        return dedup;
      }
      try{
        const refXs = [...ph.map(p=>p.x), ...ecRaw.map(p=>p.x)];
        temp = fillForward(temp, refXs, 20*60*1000);
      }catch(_){ }

      let ec = ecRaw.map(p => ({ x:p.x, y: p.y }));
      ec = interpSingles(ec);

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
        return { min: pref.min, max: pref.max };
      }
      const aPh   = chooseAxis(PREF.ph,   ph);
      const aEc   = chooseAxis(PREF.ec,   ec);
      const aTemp = chooseAxis(PREF.temp, temp);

      if (state.window.start && state.window.end) {
        trendChart.options.scales.x.min = state.window.start;
        trendChart.options.scales.x.max = state.window.end;
      } else {
        delete trendChart.options.scales.x.min;
        delete trendChart.options.scales.x.max;
      }

      ['yPh','yEc','yTemp'].forEach(id => {
        delete trendChart.options.scales[id].suggestedMin;
        delete trendChart.options.scales[id].suggestedMax;
        delete trendChart.options.scales[id].min;
        delete trendChart.options.scales[id].max;
      });

      trendChart.options.scales.yPh.min   = aPh.min;   trendChart.options.scales.yPh.max   = aPh.max;
      trendChart.options.scales.yEc.min   = aEc.min;   trendChart.options.scales.yEc.max   = aEc.max;
      trendChart.options.scales.yTemp.min = aTemp.min; trendChart.options.scales.yTemp.max = aTemp.max;

      const datasets = [];
      if (ph.length)   datasets.push({ id:'ph',   yAxisID:'yPh',   label:'pH',        data:ph,   borderWidth:2, borderColor:COLORS.ph,   backgroundColor:COLORS.ph,   pointRadius:0, spanGaps:true });
      if (ec.length)   datasets.push({ id:'ec',   yAxisID:'yEc',   label:'EC',        data:ec,   borderWidth:2, borderColor:COLORS.ec,   backgroundColor:COLORS.ec,   pointRadius:0, spanGaps:true });
      if (temp.length) datasets.push({ id:'temp', yAxisID:'yTemp', label:'Temp (°C)', data:temp, borderWidth:2, borderColor:COLORS.temp, backgroundColor:COLORS.temp, pointRadius:0, spanGaps:true });

      trendChart.data.datasets = datasets;

      function synthBounds(series){
        if (!state.window.start || !state.window.end) return series;
        if (!series || series.length === 0) return series;
        if (series.length >= 2) return series;
        const v = series[0].y;
        return [ {x: state.window.start, y: v}, {x: state.window.end, y: v} ];
      }
      trendChart.data.datasets.forEach(ds => { ds.data = synthBounds(ds.data); });

      const hasAny = (ph.length || ec.length || temp.length);
      if (emptyEl) emptyEl.style.display = hasAny ? 'none' : 'block';

      trendChart.update();
      
      try {
        window.trendsData = data;
        window.dispatchEvent(new CustomEvent('trends:update', { detail: { data } }));
      } catch(_e) { }
    }

    let autoRefreshTimer = null;
    function scheduleAutoRefresh() {
      if (autoRefreshTimer) {
        clearTimeout(autoRefreshTimer);
      }
      
      const refreshInterval = 60000;
      autoRefreshTimer = setTimeout(async () => {
        if (!document.hidden && state.window.start && state.window.end) {
          console.log('[Trends] Auto-refresh: fetching updated trends data');
          try {
            const data = await fetchTrends(
              new Date(state.window.start).toISOString(),
              new Date(state.window.end).toISOString()
            );
            render(data);
          } catch(e) {
            console.warn('[Trends] Auto-refresh failed:', e);
          }
          scheduleAutoRefresh();
        } else {
          scheduleAutoRefresh();
        }
      }, refreshInterval);
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
      await fetchDoseEvents();
      const data = await fetchTrends(new Date(start).toISOString(), new Date(end).toISOString(), gran, max);
      render(data);
      scheduleAutoRefresh();
    }

    if (selectEl) {
      selectEl.addEventListener('change', async () => {
        const val = selectEl.value;
        const isCustom = (val === 'custom');
        
        if (fromEl) fromEl.disabled = !isCustom;
        if (toEl) toEl.disabled = !isCustom;
        if (applyEl) applyEl.disabled = !isCustom;
        
        if (!isCustom) {
          if (val === 'grow') {
            await loadGrow();
          } else {
            await loadPreset(val);
          }
        }
      });
    }
    
    if (applyEl) {
      applyEl.addEventListener('click', async () => {
        if(!fromEl.value || !toEl.value) return;
        const startMs = new Date(fromEl.value).getTime();
        const endMs = new Date(toEl.value).getTime();
        state.window = { start: startMs, end: endMs };
        const fromISO = new Date(startMs).toISOString();
        const toISO = new Date(endMs).toISOString();
        const {gran, max} = presetParams('custom');
        await fetchDoseEvents();
        const data = await fetchTrends(fromISO, toISO, gran, max);
        render(data);
        scheduleAutoRefresh();
      });
    }

    window.addEventListener('sensors:update', (e) => {
      const { temp, ec, ph, ts } = e.detail;
      
      const now = Date.now();
      if (!state.window.end || Math.abs(state.window.end - now) > 5*60*1000) {
        return;
      }
      
      if (trendChart && trendChart.data && trendChart.data.datasets) {
        const tsMs = new Date(ts).getTime();
        
        trendChart.data.datasets.forEach(ds => {
          if (ds.id === 'ph' && ph != null) {
            ds.data.push({ x: tsMs, y: Number(ph) });
            if (ds.data.length > 500) ds.data.shift();
          } else if (ds.id === 'ec' && ec != null) {
            ds.data.push({ x: tsMs, y: Number(ec) });
            if (ds.data.length > 500) ds.data.shift();
          } else if (ds.id === 'temp' && temp != null) {
            ds.data.push({ x: tsMs, y: Number(temp) });
            if (ds.data.length > 500) ds.data.shift();
          }
        });
        
        trendChart.update('none');
      }
    });

    window.trendsRefresh = async function() {
      console.log('[Trends] Manual refresh triggered');
      if (state.window.start && state.window.end) {
        try {
          const data = await fetchTrends(
            new Date(state.window.start).toISOString(),
            new Date(state.window.end).toISOString()
          );
          render(data);
        } catch(e) {
          console.warn('[Trends] Refresh failed:', e);
        }
      }
    };

    setInterval(() => {
      if (state.window.start && state.window.end) {
        console.log('[Trends] Auto-refresh (60s timer)');
        window.trendsRefresh();
      }
    }, 60000);

    loadPreset('24h').catch(err => {
      console.error('[Sensors]', err);
      if (emptyEl) emptyEl.style.display = 'block';
    });
  }
})();

window.trendsWindow = window.trendsWindow || {};
try{
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
}catch(e){ }
