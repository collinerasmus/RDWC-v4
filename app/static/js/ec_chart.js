// EC Dose Chart Rendering Module
// Shows EC sensor readings over time with dose events overlaid (Grow, Micro, Bloom)
(function(){
  'use strict';
  console.log('[EC Chart] Loader enter (ec_chart.js start)');

  //==========================================================================
  // ChartController - State management for EC chart
  //==========================================================================
  const ChartController = {
    chart: null,
    state: { lastStart: null, lastEnd: null, lastCount: 0, lastFetchTs: 0 },
    rolling: { active: true, initialized: false, spanMs: 24 * 3600 * 1000, endMs: Date.now() },
    userRangeSelected: false,
    renderMutex: false,
    lastRenderTime: 0,
    
    // Data cache
    cachedEcReadings: null,
    cachedDoseEvents: null,
    cachedTargets: null,
    cachedCurrentEC: null,
    
    // Constants
    REFRESH_INTERVAL_MS: 10000,
    MIN_RENDER_INTERVAL_MS: 3000,
    
    acquireMutex() {
      if (this.renderMutex) return false;
      this.renderMutex = true;
      return true;
    },
    releaseMutex() {
      this.renderMutex = false;
    }
  };

  // Check annotation plugin availability
  let ANNOTATION_AVAILABLE = false;
  if (window.Chart && typeof Chart.register === 'function') {
    const annoPlugin = window['chartjs-plugin-annotation'] || 
                       (window.chartjs && window.chartjs['plugin-annotation']) || 
                       window.ChartAnnotation;
    if (annoPlugin) {
      try {
        Chart.register(annoPlugin);
        ANNOTATION_AVAILABLE = true;
        console.log('[EC Chart] ✓ Annotation plugin registered');
      } catch (e) {
        // Registration failed - annotation features will be disabled
        ANNOTATION_AVAILABLE = false;
        console.warn('[EC Chart] Annotation plugin registration failed:', e.message);
      }
    }
  }

  // Granularity settings for time-based bucketing
  function presetParams(spanMs) {
    const hours = spanMs / (3600 * 1000);
    if (hours <= 2)   return { gran: 30, max: 1000 };
    if (hours <= 24)  return { gran: 60, max: 1500 };
    if (hours <= 168) return { gran: 300, max: 2100 };
    if (hours <= 720) return { gran: 900, max: 3000 };
    return { gran: 3600, max: 2500 };
  }

  /**
   * Fetch EC readings from trends API
   */
  async function fetchEcReadings(fromISO, toISO, gran, max) {
    const q = new URLSearchParams();
    if (fromISO) q.set('from', fromISO);
    if (toISO) q.set('to', toISO);
    if (gran) q.set('gran', String(gran));
    if (max) q.set('max', String(max));
    
    const url = '/api/trends?' + q.toString();
    
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) {
        console.warn('[EC Chart] Trends API failed:', res.status);
        return { data: [], error: 'HTTP ' + res.status };
      }
      const data = await res.json();
      
      const ecSeries = (data?.series?.ec || []).map(function(p) {
        return {
          x: new Date(p.ts * 1000),
          y: Number(p.value)
        };
      }).filter(function(p) { return !isNaN(p.y); });
      
      return { data: ecSeries, error: null };
    } catch (err) {
      console.error('[EC Chart] Failed to fetch EC readings:', err);
      return { data: [], error: err.message };
    }
  }

  /**
   * Build the EC chart with EC readings and dose events per pump
   */
  function buildChart(datasets, tmin, tmax, currentEC, targets, ecReadings, pumpEvents) {
    if (!ChartController.acquireMutex()) return;
    
    const now = Date.now();
    if (now - ChartController.lastRenderTime < ChartController.MIN_RENDER_INTERVAL_MS) {
      ChartController.releaseMutex();
      return;
    }
    ChartController.lastRenderTime = now;
    
    try {
      const el = document.getElementById('ecDoseChart');
      const empty = document.getElementById('ec-dose-empty');
      if (!el) {
        console.error('[EC Chart] ❌ Canvas #ecDoseChart not found!');
        return;
      }

      // Fixed EC axis range for K=0.1 probe (0-8 mS/cm range)
      // Display range optimized for typical hydroponic values (0-2 mS/cm)
      // but can auto-scale if readings exceed this
      const ecMin = 0;
      let ecMax = 2.0; // Default max for typical hydro EC values
      
      // Auto-adjust max if we have readings that exceed the default
      if (ecReadings && ecReadings.length > 0) {
        const maxReading = Math.max(...ecReadings.map(r => r.y || 0));
        if (maxReading > ecMax) {
          ecMax = Math.ceil(maxReading * 1.2); // 20% headroom
          if (ecMax > 8) ecMax = 8; // Cap at probe max (K=0.1 range)
        }
      }
      // Also check current EC
      if (currentEC != null && currentEC > ecMax) {
        ecMax = Math.ceil(currentEC * 1.2);
        if (ecMax > 8) ecMax = 8;
      }

      const hasEcReadings = ecReadings && ecReadings.length > 0;
      const hasDoseData = datasets && datasets.some(ds => (ds.data||[]).length > 0);
      
      // Cache valid data
      if (hasEcReadings) {
        ChartController.cachedEcReadings = ecReadings;
      } else if (ChartController.cachedEcReadings && ChartController.cachedEcReadings.length > 0) {
        ecReadings = ChartController.cachedEcReadings;
      }
      
      if (currentEC != null && !isNaN(currentEC)) {
        ChartController.cachedCurrentEC = currentEC;
      } else if (ChartController.cachedCurrentEC != null) {
        currentEC = ChartController.cachedCurrentEC;
      }
      
      if (targets && targets.low != null) {
        ChartController.cachedTargets = targets;
      } else if (ChartController.cachedTargets) {
        targets = ChartController.cachedTargets;
      }
      
      const hasData = (ecReadings && ecReadings.length > 0) || hasDoseData;
      if (empty) empty.style.display = hasData ? 'none' : 'block';

      const ctx = el.getContext('2d');
      if (!ctx) {
        console.error('[EC Chart] ❌ Failed to get 2D context!');
        return;
      }

      // Build annotations
      const annotations = {};
      
      // Target EC band (hysteresis)
      if (targets && targets.low != null && targets.high != null) {
        annotations.ecBand = {
          type: 'box',
          yMin: targets.low,
          yMax: targets.high,
          yScaleID: 'yEc',
          backgroundColor: 'rgba(34, 197, 94, 0.12)',
          borderWidth: 0,
          drawTime: 'beforeDatasetsDraw'
        };
        
        const setpoint = (targets.low + targets.high) / 2;
        annotations.ecSetpoint = {
          type: 'line',
          yMin: setpoint,
          yMax: setpoint,
          yScaleID: 'yEc',
          borderColor: 'rgba(34, 197, 94, 0.5)',
          borderWidth: 1,
          borderDash: [4, 4],
          label: {
            display: true,
            content: 'Target: ' + setpoint.toFixed(2),
            position: 'end',
            backgroundColor: 'rgba(34, 197, 94, 0.8)',
            color: '#fff',
            font: { size: 10 },
            padding: 3
          }
        };
      }
      
      // Current EC line
      if (currentEC != null && !isNaN(currentEC)) {
        annotations.ecLine = {
          type: 'line',
          yMin: currentEC,
          yMax: currentEC,
          yScaleID: 'yEc',
          borderColor: 'rgba(251, 191, 36, 0.8)',
          borderWidth: 2,
          borderDash: [6, 4],
          label: {
            display: true,
            content: 'Current: ' + currentEC.toFixed(2),
            position: 'start',
            backgroundColor: 'rgba(251, 191, 36, 0.9)',
            color: '#000',
            font: { size: 11, weight: 'bold' },
            padding: 4
          }
        };
      }

      // Build datasets
      const finalDatasets = [];
      
      // EC readings line (primary)
      if (ecReadings && ecReadings.length > 0) {
        finalDatasets.push({
          type: 'line',
          label: 'EC (mS/cm)',
          data: ecReadings,
          order: 0,
          yAxisID: 'yEc',
          borderColor: '#f59e0b', // amber-500
          backgroundColor: 'rgba(245, 158, 11, 0.1)',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          spanGaps: true
        });
      }
      
      // Add dose datasets (Grow, Micro, Bloom as separate series)
      if (datasets && datasets.length > 0) {
        datasets.forEach(ds => {
          const clone = { ...ds };
          clone.yAxisID = 'yDose';
          finalDatasets.push(clone);
        });
      }
      
      const dsUse = finalDatasets.length > 0 ? finalDatasets : [{
        label: 'No data',
        data: [],
        showLine: false,
        pointRadius: 0.0001,
        borderWidth: 0
      }];

      const hasDoseAxis = dsUse.some(ds => ds.yAxisID === 'yDose' && (ds.data||[]).length > 0);

      // Build scales
      const scales = {
        x: {
          type: 'time',
          adapters: { date: {} },
          min: tmin || undefined,
          max: tmax || undefined,
          ticks: { source: 'auto', maxRotation: 0, autoSkip: true },
          time: {
            tooltipFormat: 'yyyy-MM-dd HH:mm',
            displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'MMM d' }
          },
          grid: { color: 'rgba(148,163,184,0.15)', drawTicks: false }
        },
        yEc: {
          type: 'linear',
          position: 'left',
          title: { display: true, text: 'EC (mS/cm)' },
          min: ecMin,
          max: ecMax,
          grid: { color: 'rgba(148,163,184,0.12)', drawTicks: false }
        }
      };
      
      if (hasDoseAxis) {
        scales.yDose = {
          type: 'linear',
          position: 'right',
          title: { display: true, text: 'Dose (s)' },
          beginAtZero: true,
          grid: { drawOnChartArea: false }
        };
      }

      // Plugins config
      const pluginsConfig = {
        legend: { display: true, position: 'top', labels: { usePointStyle: true, boxWidth: 10, padding: 12 } },
        tooltip: {
          enabled: true,
          callbacks: {
            label: function(ctx) {
              const p = ctx.raw;
              const ds = ctx.dataset;
              
              if (ds.label === 'EC (mS/cm)') {
                const v = Number(ctx.parsed.y);
                return ' EC: ' + v.toFixed(3) + ' mS/cm';
              }
              
              if (!p) return '';
              const sec = p.sec != null ? p.sec.toFixed(2) + 's' : '';
              const ec = (p.ecb != null || p.eca != null) ? '  EC: ' + (p.ecb ?? '—') + ' → ' + (p.eca ?? '—') : '';
              return sec + ec;
            }
          }
        }
      };
      
      if (ANNOTATION_AVAILABLE && Object.keys(annotations).length > 0) {
        pluginsConfig.annotation = { annotations: annotations };
      }

      // In-place update if chart exists
      if (ChartController.chart && ChartController.chart.canvas) {
        try {
          ChartController.chart.data.datasets = dsUse;
          if (tmin && tmax) {
            ChartController.chart.options.scales.x.min = tmin;
            ChartController.chart.options.scales.x.max = tmax;
          }
          ChartController.chart.options.scales.yEc.min = ecMin;
          ChartController.chart.options.scales.yEc.max = ecMax;
          if (hasDoseAxis && !ChartController.chart.options.scales.yDose) {
            ChartController.chart.options.scales.yDose = scales.yDose;
          }
          if (ANNOTATION_AVAILABLE) {
            if (!ChartController.chart.options.plugins.annotation) {
              ChartController.chart.options.plugins.annotation = { annotations: annotations };
            } else {
              ChartController.chart.options.plugins.annotation.annotations = annotations;
            }
          }
          ChartController.chart.update('none');
          console.log('[EC Chart] ♻ In-place update');
          return;
        } catch(updateErr) {
          console.warn('[EC Chart] In-place update failed, rebuilding:', updateErr.message);
          try { ChartController.chart.destroy(); } catch(e) {}
          ChartController.chart = null;
        }
      }
      
      // Create new chart
      try {
        ChartController.chart = new Chart(ctx, {
          type: 'line',
          data: { datasets: dsUse },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            parsing: false,
            animation: false,
            interaction: { mode: 'nearest', intersect: false },
            scales: scales,
            plugins: pluginsConfig
          }
        });
        console.log('[EC Chart] ✅ Chart created');
      } catch (chartErr) {
        console.error('[EC Chart] ❌ Chart creation FAILED:', chartErr);
      }
      
    } finally {
      ChartController.releaseMutex();
    }
  }

  async function loadRangeAndRender({start, end}){
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
    
    const startMs = startISO ? new Date(startISO).getTime() : Date.now() - 24*3600*1000;
    const endMs = endISO ? new Date(endISO).getTime() : Date.now();
    const spanMs = endMs - startMs;
    const params = presetParams(spanMs);

    let events = [];
    let currentEC = null;
    let targets = null;
    let ecReadings = [];
    
    try {
      const [eRes, stRes, ecResult] = await Promise.all([
        fetch(`/api/ec/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`, {cache:'no-store'}),
        fetch('/api/ec/status', {cache:'no-store'}),
        fetchEcReadings(startISO, endISO, params.gran, params.max)
      ]);
      
      if (eRes.ok) {
        events = await eRes.json();
      }
      
      ecReadings = ecResult.data;
      
      if (stRes.ok) {
        const statusData = await stRes.json();
        currentEC = statusData?.ec_ms_cm ?? statusData?.ec ?? null;
        targets = statusData?.targets ?? null;
      }
    } catch(err) {
      console.error('[EC Chart] fetch error:', err);
      buildChart([], null, null, null, null, [], []);
      return;
    }

    // Group dose events by pump type (grow, micro, bloom)
    const growPts = [], microPts = [], bloomPts = [];
    
    events.forEach(r => {
      const pt = {
        x: new Date(r.ts),
        y: r.seconds ?? 0,
        sec: r.seconds ?? null,
        ecb: r.ec_before ?? null,
        eca: r.ec_after ?? null,
        pump: r.pump
      };
      
      if (r.pump === 'grow') growPts.push(pt);
      else if (r.pump === 'micro') microPts.push(pt);
      else if (r.pump === 'bloom') bloomPts.push(pt);
    });

    // Build datasets for each pump type
    const datasets = [];
    
    if (growPts.length > 0) {
      datasets.push({
        type: 'scatter',
        label: '🌱 Grow',
        data: growPts,
        order: 1,
        yAxisID: 'yDose',
        pointRadius: 6,
        pointStyle: 'triangle',
        backgroundColor: 'rgba(167, 243, 208, 0.9)', // green-200
        borderColor: 'rgba(34, 197, 94, 1)',
        borderWidth: 1
      });
    }
    
    if (microPts.length > 0) {
      datasets.push({
        type: 'scatter',
        label: '🔬 Micro',
        data: microPts,
        order: 1,
        yAxisID: 'yDose',
        pointRadius: 6,
        pointStyle: 'rect',
        backgroundColor: 'rgba(147, 197, 253, 0.9)', // blue-300
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 1
      });
    }
    
    if (bloomPts.length > 0) {
      datasets.push({
        type: 'scatter',
        label: '🌸 Bloom',
        data: bloomPts,
        order: 1,
        yAxisID: 'yDose',
        pointRadius: 6,
        pointStyle: 'circle',
        backgroundColor: 'rgba(251, 191, 36, 0.9)', // amber-400
        borderColor: 'rgba(245, 158, 11, 1)',
        borderWidth: 1
      });
    }

    const tmin = startISO ? new Date(startISO) : null;
    const tmax = endISO ? new Date(endISO) : null;
    buildChart(datasets, tmin, tmax, currentEC, targets, ecReadings, []);

    ChartController.state = { lastStart: startISO, lastEnd: endISO, lastCount: events.length, lastFetchTs: Date.now() };

    // Update summary badges
    try {
      const todayEl = document.getElementById('ec-total-today');
      const weekEl = document.getElementById('ec-total-week');
      const rate = {
        grow: parseFloat(window.rdwcSettings?.get('dosing.grow_ml_per_sec') || '20'),
        micro: parseFloat(window.rdwcSettings?.get('dosing.micro_ml_per_sec') || '20'),
        bloom: parseFloat(window.rdwcSettings?.get('dosing.bloom_ml_per_sec') || '20')
      };
      
      // Calculate totals
      const now = new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      const weekStart = todayStart - 7 * 24 * 3600 * 1000;
      
      let todayMl = 0, weekMl = 0;
      events.forEach(e => {
        const ts = new Date(e.ts).getTime();
        const ml = (e.seconds || 0) * (rate[e.pump] || 0);
        if (ts >= todayStart) todayMl += ml;
        if (ts >= weekStart) weekMl += ml;
      });
      
      if (todayEl) {
        const valEl = todayEl.querySelector('.kpi-value');
        if (valEl) valEl.textContent = todayMl > 0 ? `${todayMl.toFixed(1)} ml` : '— ml';
        else todayEl.textContent = `Today: ${todayMl.toFixed(1)} ml`;
      }
      if (weekEl) {
        const valEl = weekEl.querySelector('.kpi-value');
        if (valEl) valEl.textContent = weekMl > 0 ? `${weekMl.toFixed(1)} ml` : '— ml';
        else weekEl.textContent = `Week: ${weekMl.toFixed(1)} ml`;
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
