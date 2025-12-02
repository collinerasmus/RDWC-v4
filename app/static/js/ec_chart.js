// EC Dose Chart Rendering Module
(function(){
  'use strict';

  let EC_CHART = null;
  let EC_STATE = { startISO: null, endISO: null, lastCount: 0 };

  // Defensive Chart.js registration (v4 UMD usually auto-registers)
  if (window.Chart && Chart.register && window.RDWC_CHART_REG_EC === undefined) {
    try {
      Chart.register(
        Chart.controllers.BarController,
        Chart.controllers.LineController,
        Chart.controllers.ScatterController,
        Chart.elements.BarElement,
        Chart.elements.PointElement,
        Chart.elements.LineElement,
        Chart.scales.TimeScale,
        Chart.scales.LinearScale,
        Chart.plugins.Tooltip,
        Chart.plugins.Legend,
        Chart.plugins.Title
      );
      // Register annotation plugin if available
      if (window.chartjs && window.chartjs.Annotation) {
        Chart.register(window.chartjs.Annotation);
      } else if (window.ChartAnnotation) {
        Chart.register(window.ChartAnnotation);
      }
    } catch (e) {
      // ignore
    }
    window.RDWC_CHART_REG_EC = true;
  }

  function buildChart(datasets, tmin, tmax, axisTitle, currentEC) {
    const el = document.getElementById('ecDoseChart');
    const empty = document.getElementById('ec-dose-empty');
    if (!el) return;

    const hasData = datasets && datasets.some(ds => (ds.data||[]).length > 0);
    if (empty) empty.style.display = hasData ? 'none' : 'block';

    const ctx = el.getContext('2d');
    if (EC_CHART && typeof EC_CHART.destroy === 'function') {
      EC_CHART.destroy();
      EC_CHART = null;
    }

    const dsUse = hasData ? datasets : [{
      label: 'No doses',
      data: [],
      showLine: false,
      pointRadius: 0.0001,
      borderWidth: 0
    }];

    const hasCumulative = dsUse.some(ds => ds.yAxisID === 'y2');

    // Build annotation plugin config for EC reference line
    const annotations = {};
    if (currentEC != null && !isNaN(currentEC)) {
      annotations.ecLine = {
        type: 'line',
        yMin: currentEC,
        yMax: currentEC,
        yScaleID: 'y',
        borderColor: 'rgba(99, 102, 241, 0.8)',  // indigo-500
        borderWidth: 2,
        borderDash: [6, 4],
        label: {
          display: true,
          content: `Current EC: ${currentEC.toFixed(2)} mS/cm`,
          position: 'start',
          backgroundColor: 'rgba(99, 102, 241, 0.9)',
          color: '#fff',
          font: { size: 11, weight: 'bold' },
          padding: 4
        }
      };
    }

    EC_CHART = new Chart(ctx, {
      type: 'scatter',
      data: { datasets: dsUse },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        parsing: false,
        interaction: { mode: 'nearest', intersect: false },
        scales: {
          x: {
            type: 'time',
            adapters: { date: {} },
            min: tmin || undefined,
            max: tmax || undefined,
            ticks: { source: 'auto' }
          },
          y: {
            type: 'linear',
            position: 'left',
            title: { display: true, text: axisTitle || 'Dose (ml)' },
            suggestedMin: 0
          },
          y2: hasCumulative ? {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'Cumulative (ml)' },
            suggestedMin: 0,
            grid: { drawOnChartArea: false }
          } : undefined
        },
        plugins: {
          legend: { display: true, position: 'top' },
          tooltip: {
            enabled: true,
            callbacks: {
              label: (ctx) => {
                const p = ctx.raw;
                const ds = ctx.dataset;
                if (ds.label && ds.label.includes('Cumulative')) {
                  return `Total: ${ctx.parsed.y.toFixed(1)} ml`;
                }
                if (ds.label && ds.label.includes('Daily')) {
                  return `Day total: ${ctx.parsed.y.toFixed(1)} ml`;
                }
                if (!p) return '';
                const ml = (p.ml != null) ? `+${p.ml.toFixed(2)} ml` : (p.sec != null ? `~${p.sec.toFixed(2)} s` : '');
                const ec = (p.ecb != null || p.eca != null) ? `  EC: ${p.ecb ?? '—'} → ${p.eca ?? '—'}` : '';
                return `${ml}${ec}`;
              }
            }
          },
          annotation: {
            annotations: annotations
          }
        }
      }
    });
  }

  async function loadRangeAndRender({start, end}){
    // normalize inputs to ISO
    const toIso = (v) => {
      if (v == null) return null;
      if (typeof v === 'string') {
        try { const d = new Date(v); if (!isNaN(d)) return d.toISOString(); } catch(e) {}
        return v;
      }
      if (typeof v === 'number') {
        const d = new Date(v);
        return isNaN(d) ? null : d.toISOString();
      }
      return null;
    };
    const startISO = toIso(start);
    const endISO = toIso(end);

    let events = [];
    let summary = [];
    let currentEC = null;
    try{
      const [eRes, sRes, stRes] = await Promise.all([
        fetch(`/api/ec/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`, {cache:'no-store'}),
        fetch(`/api/ec/dose_summary?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`, {cache:'no-store'}),
        fetch(`/api/ec/status`, {cache:'no-store'})
      ]);
      if (!eRes.ok) throw new Error(`dose_log HTTP ${eRes.status}`);
      if (!sRes.ok) throw new Error(`dose_summary HTTP ${sRes.status}`);
      events = await eRes.json();
      summary = await sRes.json();
      if (stRes.ok) {
        const statusData = await stRes.json();
        currentEC = statusData?.ec_ms_cm ?? null;
        // Safety: if EC > 20, assume it's in µS/cm and convert to mS/cm
        if (currentEC != null && currentEC > 20) {
          console.warn('[EC Chart] EC value > 20, assuming µS/cm and converting to mS/cm:', currentEC);
          currentEC = currentEC / 1000;
        }
      }
    } catch(err){
      console.error('[EC Chart] fetch error:', err);
      buildChart([], null, null, 'Dose (ml)', null);
      return;
    }

  const hasAnyMl = events.some(r => r && r.volume_ml != null);
    const pts = events.map(r => ({
      x: new Date(r.ts),
      y: hasAnyMl ? (r.volume_ml != null ? r.volume_ml : 0) : (r.seconds ?? 0),
      ml: (r.volume_ml != null ? r.volume_ml : null),
      sec: r.seconds ?? null,
      ecb: r.ec_before ?? null,
      eca: r.ec_after ?? null
    }));

    const cumulative = [];
    if (hasAnyMl && events.length > 0) {
      let running = 0;
      events.forEach(r => {
        running += (r.volume_ml ?? 0);
        cumulative.push({ x: new Date(r.ts), y: running });
      });
    }

    const bars = hasAnyMl ? summary.map(d => ({ x: new Date(d.day), y: d.total_ml ?? 0 })) : [];

    const datasets = [
      bars.length ? {
        type: 'bar',
        label: 'Daily total (ml)',
        data: bars,
        order: 3,
        backgroundColor: 'rgba(34,197,94,0.35)',
        borderColor: 'rgba(34,197,94,0.6)',
        yAxisID: 'y'
      } : null,
      cumulative.length ? {
        type: 'line',
        label: 'Cumulative total (ml)',
        data: cumulative,
        order: 2,
        borderColor: 'rgba(168,85,247,0.8)',
        backgroundColor: 'rgba(168,85,247,0.1)',
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0,
        yAxisID: 'y2'
      } : null,
      {
        type: 'scatter',
        label: hasAnyMl ? 'Dose events (ml)' : 'Dose events (s)',
        data: pts,
        order: 1,
        pointRadius: 3,
        backgroundColor: 'rgba(59,130,246,0.9)',
        yAxisID: 'y'
      }
    ].filter(Boolean);

    const axisTitle = hasAnyMl ? 'Dose (ml)' : 'Dose (s)';
    const tmin = startISO ? new Date(startISO) : null;
    const tmax = endISO ? new Date(endISO) : null;
    buildChart(datasets, tmin, tmax, axisTitle, currentEC);

    EC_STATE = { startISO, endISO, lastCount: events.length };

    // Update summary badges if present
    try {
      const todayEl = document.getElementById('ec-total-today');
      const weekEl = document.getElementById('ec-total-week');
      if (todayEl && hasAnyMl) {
        const todayStr = new Date().toISOString().slice(0,10);
        const todayTotal = (summary.find(d => d.day === todayStr)?.total_ml) ?? 0;
        todayEl.textContent = `Today: ${Number(todayTotal).toFixed(1)} ml`;
      }
      if (weekEl && hasAnyMl) {
        const sum7 = summary.slice(-7).reduce((a, d) => a + (d.total_ml || 0), 0);
        weekEl.textContent = `Week: ${Number(sum7).toFixed(1)} ml`;
      }
    } catch(e) { /* ignore */ }
  }

  let currentRange = { preset: '24h', start: null, end: null };

  async function selectPreset(preset){
    currentRange.preset = preset;
    if (window.rdwcRange) {
      window.rdwcRange.saveLastPreset('rdwc.ec.range', preset);
    }
    
    // Update button states
    const btns = document.querySelectorAll('[data-ec-range]');
    btns.forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-ec-range') === preset);
    });
    
    // Load range
    await loadRange(preset);
  }

  async function loadRange(preset){
    if (!window.rdwcRange) {
      // Fallback to simple time-based ranges
      const now = new Date();
      let start;
      if (preset === '24h') start = new Date(now.getTime() - 24*3600*1000);
      else if (preset === '7d') start = new Date(now.getTime() - 7*24*3600*1000);
      else if (preset === '30d') start = new Date(now.getTime() - 30*24*3600*1000);
      else if (preset === '90d') start = new Date(now.getTime() - 90*24*3600*1000);
      else start = new Date(now.getTime() - 24*3600*1000);
      
      currentRange.start = start.toISOString();
      currentRange.end = now.toISOString();
      loadRangeAndRender({ start: currentRange.start, end: currentRange.end });
      return;
    }
    
    const growDate = window.rdwcSettings?.get('general.grow_start_date');
    const customRange = window.rdwcRange.getCustomRange('rdwc.ec.range');
    
    // Compute start/end
    const range = await window.rdwcRange.rangeToStartEnd(
      preset, 
      customRange.start, 
      customRange.end, 
      growDate
    );
    
    if (!range) {
      console.warn('[EC Chart] Invalid range');
      return;
    }
    
    currentRange.start = range.start;
    currentRange.end = range.end;
    
    // Auto-populate datetime inputs
    const fromEl = document.getElementById('ecDoseFrom');
    const toEl = document.getElementById('ecDoseTo');
    if (fromEl && toEl && range.start && range.end) {
      const formatForInput = (ts) => {
        const d = new Date(ts);
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        const hh = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
      };
      
      fromEl.value = formatForInput(range.start);
      toEl.value = formatForInput(range.end);
    }
    
    // Render chart
    loadRangeAndRender({ start: range.start, end: range.end });
  }

  function toggleCustomInputs(enabled){
    const fromEl = document.getElementById('ecDoseFrom');
    const toEl = document.getElementById('ecDoseTo');
    const applyEl = document.getElementById('ecDoseApply');
    if(!fromEl || !toEl || !applyEl) return;
    fromEl.disabled = !enabled; toEl.disabled = !enabled; applyEl.disabled = !enabled;
    fromEl.style.opacity = enabled ? '1' : '0.55';
    toEl.style.opacity = enabled ? '1' : '0.55';
  }

  async function wireRangeControls(){
    // Restore last preset
    const savedPreset = window.rdwcRange?.getLastPreset('rdwc.ec.range') || '24h';
    currentRange.preset = savedPreset;
    const selectEl = document.getElementById('ecDoseRangeSelect');
    if(selectEl){
      // Disable grow if no start date
      const growDate = window.rdwcSettings?.get('general.grow_start_date');
      if(!growDate){
        const opt = selectEl.querySelector('option[value="grow"]');
        if(opt){ opt.disabled = true; opt.textContent = 'Entire Grow (set start date)'; }
        if(savedPreset==='grow') currentRange.preset='24h';
      }
      selectEl.value = currentRange.preset;
      selectEl.addEventListener('change', ()=>{
        const val = selectEl.value;
        selectPreset(val);
        toggleCustomInputs(val==='custom');
      });
      toggleCustomInputs(selectEl.value==='custom');
    }
    // Custom range apply
    const fromEl = document.getElementById('ecDoseFrom');
    const toEl = document.getElementById('ecDoseTo');
    const applyEl = document.getElementById('ecDoseApply');
    if(applyEl && fromEl && toEl){
      applyEl.addEventListener('click', ()=>{
        const start = fromEl.value; const end = toEl.value;
        if(start && end){
          window.rdwcRange.saveCustomRange('rdwc.ec.range', start, end);
          selectPreset('custom');
          if(selectEl) selectEl.value='custom';
          toggleCustomInputs(true);
        }
      });
    }
    await loadRange(currentRange.preset);
  }

  async function init(){
    wireRangeControls();
  }

  // Export small API for other modules (ec.js calls refresh after dosing)
  window.ecChart = {
    refresh: function(){
      // Re-render with current range to pick up new dose data
      if (currentRange.start && currentRange.end) {
        loadRangeAndRender({ start: currentRange.start, end: currentRange.end });
      } else {
        const now = new Date();
        const start = new Date(now.getTime() - 24*3600*1000).toISOString();
        loadRangeAndRender({ start, end: now.toISOString() });
      }
    },
    render: loadRangeAndRender,
    init,
    getRange: function(){ return {start: currentRange.start, end: currentRange.end, preset: currentRange.preset}; },
    exportCSV: function(){
      let start = currentRange.start, end = currentRange.end;
      if(!start || !end){ window.open('/api/ec/dose_log.csv?hours=24','_blank'); return; }
      const startISO = new Date(start).toISOString();
      const endISO = new Date(end).toISOString();
      window.open(`/api/ec/dose_log.csv?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=5000`, '_blank');
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
