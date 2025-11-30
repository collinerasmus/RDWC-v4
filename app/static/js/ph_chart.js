// pH Dose Chart Rendering Module
// Shows pH sensor readings over time (hysteresis) with dose events overlaid
// pH-only: no EC or temperature data displayed here (use Sensors tab for that)
(function(){
  console.log('[pH Chart] Loader enter (ph_chart.js start)');
  'use strict';

  //==========================================================================
  // ChartController - Consolidated state management for pH chart
  // STABILITY FIXES: Single owner of chart state, mutex for renders,
  // cached data to prevent flicker, locked legend config
  //==========================================================================
  const ChartController = {
    // Core chart instance - SINGLE OWNER
    chart: null,
    
    // Chart state
    state: { lastStart: null, lastEnd: null, lastCount: 0, lastFetchTs: 0 },
    
    // Rolling window configuration
    rolling: {
      active: true,
      initialized: false,
      spanMs: 3600 * 1000, // 1h default
      endMs: Date.now()
    },
    
    // User range selection
    userRangeSelected: false,
    
    // Render mutex - prevents ALL concurrent render operations
    renderMutex: false,
    pendingRender: null,
    
    // Data cache to prevent empty flicker on transient API failures
    cachedPhReadings: null,
    cachedDoseEvents: null,
    cachedTargets: null,
    cachedCurrentPH: null,
    
    // Visibility state for tab throttling
    isVisible: true,
    
    // Debounce tracking
    lastRenderTime: 0,
    
    // Locked legend configuration - never changes
    LEGEND_CONFIG: {
      display: true,
      position: 'top',
      labels: { usePointStyle: true, boxWidth: 10, padding: 12 }
    },
    
    // Constants
    REFRESH_INTERVAL_MS: 10000,
    ROLLING_DEFAULT_SPAN_MS: 3600 * 1000,
    MIN_PUMP_BAR_WIDTH_MS: 5000,
    MIN_RENDER_INTERVAL_MS: 3000, // Minimum time between renders
    
    // Round timestamp to nearest refresh boundary (prevents micro jitter)
    roundTs(ts) {
      return Math.floor(ts / this.REFRESH_INTERVAL_MS) * this.REFRESH_INTERVAL_MS;
    },
    
    // Acquire render mutex - returns true if acquired, false if already held
    acquireMutex() {
      if (this.renderMutex) {
        console.log('[pH Chart] Render blocked (mutex held)');
        return false;
      }
      this.renderMutex = true;
      return true;
    },
    
    // Release render mutex
    releaseMutex() {
      this.renderMutex = false;
    },
    
    // Persist state to localStorage
    saveState() {
      try {
        localStorage.setItem('ph_chart_state', JSON.stringify({
          userRangeSelected: this.userRangeSelected,
          lastStart: this.state.lastStart,
          lastEnd: this.state.lastEnd,
          spanMs: this.rolling.spanMs
        }));
      } catch(e) { /* ignore */ }
    },
    
    // Restore state from localStorage
    restoreState() {
      try {
        const stored = localStorage.getItem('ph_chart_state');
        if (stored) {
          const parsed = JSON.parse(stored);
          if (parsed.userRangeSelected && parsed.lastStart && parsed.lastEnd) {
            const s = new Date(parsed.lastStart).getTime();
            const e = new Date(parsed.lastEnd).getTime();
            if (isFinite(s) && isFinite(e) && e > s) {
              this.userRangeSelected = true;
              this.rolling.active = false;
              this.state.lastStart = parsed.lastStart;
              this.state.lastEnd = parsed.lastEnd;
              if (parsed.spanMs) this.rolling.spanMs = parsed.spanMs;
              console.log('[pH Chart] Restored user range from localStorage');
              return true;
            }
          }
        }
      } catch(e) { /* ignore */ }
      return false;
    },
    
    // Clear persisted state
    clearState() {
      try {
        localStorage.removeItem('ph_chart_state');
      } catch(e) { /* ignore */ }
    }
  };

  // Check annotation plugin availability
  let ANNOTATION_AVAILABLE = false;
  
  // Chart.js v4 UMD bundle auto-registers all core components
  if (window.Chart && typeof Chart.register === 'function') {
    const annoPlugin = (
      window['chartjs-plugin-annotation'] ||
      (window.chartjs && window.chartjs['plugin-annotation']) ||
      window.ChartAnnotation
    );
    
    if (annoPlugin) {
      try {
        Chart.register(annoPlugin);
        ANNOTATION_AVAILABLE = true;
        console.log('[pH Chart] ✓ Annotation plugin registered successfully');
      } catch (regErr) {
        console.debug('[pH Chart] Annotation plugin registration:', regErr?.message);
        ANNOTATION_AVAILABLE = true;
      }
    } else {
      console.warn('[pH Chart] ⚠ Annotation plugin not found');
    }
  } else {
    console.error('[pH Chart] ❌ Chart.js not loaded');
  }

  // Granularity constants for time-based bucketing (in seconds)
  const GRANULARITY = {
    FINE: 30,
    MINUTE: 60,
    FIVE_MIN: 300,
    QUARTER: 900,
    HOURLY: 3600
  };

  function presetParams(spanMs) {
    const hours = spanMs / (3600 * 1000);
    if (hours <= 2)   return { gran: GRANULARITY.FINE, max: 1000 };
    if (hours <= 24)  return { gran: GRANULARITY.MINUTE, max: 1500 };
    if (hours <= 168) return { gran: GRANULARITY.FIVE_MIN, max: 2100 };
    if (hours <= 720) return { gran: GRANULARITY.QUARTER, max: 3000 };
    return { gran: GRANULARITY.HOURLY, max: 2500 };
  }

  /**
   * Fetch pH readings from trends API with error handling
   */
  async function fetchPhReadings(fromISO, toISO, gran, max) {
    const q = new URLSearchParams();
    if (fromISO) q.set('from', fromISO);
    if (toISO) q.set('to', toISO);
    if (gran) q.set('gran', String(gran));
    if (max) q.set('max', String(max));
    
    const url = '/api/trends?' + q.toString();
    
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) {
        console.warn('[pH Chart] Trends API failed:', res.status);
        return { data: [], error: 'HTTP ' + res.status };
      }
      const data = await res.json();
      
      const phSeries = (data?.series?.ph || []).map(function(p) {
        return {
          x: new Date(p.ts * 1000),
          y: Number(p.value)
        };
      }).filter(function(p) { return !isNaN(p.y); });
      
      return { data: phSeries, error: null };
    } catch (err) {
      console.error('[pH Chart] Failed to fetch pH readings:', err);
      return { data: [], error: err.message };
    }
  }

  /**
   * Build or update the pH chart - STABLE VERSION v2
   * Key stability features:
   * - Mutex prevents ALL concurrent render operations
   * - Cache valid data, never show empty on transient errors
   * - Locked legend config - never modified during updates
   * - Debounce rapid calls
   * - Single in-place update path, minimize chart rebuilds
   */
  function phBuildChart(datasets, timeMin, timeMax, currentPH, targets, phReadings, pumpEvents, schedule) {
    // Acquire mutex - strict single execution
    if (!ChartController.acquireMutex()) {
      return; // Another render in progress, skip this one
    }
    
    // Debounce check - prevent rapid-fire renders
    const now = Date.now();
    if (now - ChartController.lastRenderTime < ChartController.MIN_RENDER_INTERVAL_MS) {
      console.log('[pH Chart] Debounced (too fast)');
      ChartController.releaseMutex();
      return;
    }
    ChartController.lastRenderTime = now;
    
    try {
      // If rolling mode active, enforce monotonic window
      if (ChartController.rolling.initialized && ChartController.rolling.active && !ChartController.userRangeSelected) {
        var endMsRounded = ChartController.roundTs(ChartController.rolling.endMs);
        var enforcedMax = new Date(endMsRounded);
        var enforcedMin = new Date(endMsRounded - ChartController.rolling.spanMs);
        timeMin = enforcedMin;
        timeMax = enforcedMax;
        ChartController.state.lastStart = enforcedMin.toISOString();
        ChartController.state.lastEnd = enforcedMax.toISOString();
      }
      
      var el = document.getElementById('phDoseChart');
      var empty = document.getElementById('ph-dose-empty');

      if (!el) {
        console.error('[pH Chart] ❌ Canvas #phDoseChart not found!');
        return;
      }
      // Fixed pH axis range for stability (prevents y-axis jumping)
      // Hydroponic systems typically operate in 4.0-8.0 range
      const phMin = 4.0;
      const phMax = 8.0;
      console.log('[pH Chart] Using fixed y-axis range:', phMin, '-', phMax);

      var hasPhReadings = phReadings && phReadings.length > 0;
      var hasDoseData = datasets && datasets.some(function(ds) { return (ds.data||[]).length > 0; });
      var hasPumpEvents = pumpEvents && pumpEvents.length > 0;
      
      // STABILITY: Cache valid data - never show empty on transient errors
      if (hasPhReadings) {
        ChartController.cachedPhReadings = phReadings;
      } else if (ChartController.cachedPhReadings && ChartController.cachedPhReadings.length > 0) {
        phReadings = ChartController.cachedPhReadings;
        hasPhReadings = true;
        console.log('[pH Chart] Using cached pH readings');
      }
      
      if (currentPH != null && !isNaN(currentPH)) {
        ChartController.cachedCurrentPH = currentPH;
      } else if (ChartController.cachedCurrentPH != null) {
        currentPH = ChartController.cachedCurrentPH;
      }
      
      if (targets && targets.low != null) {
        ChartController.cachedTargets = targets;
      } else if (ChartController.cachedTargets) {
        targets = ChartController.cachedTargets;
      }
      
      var hasData = hasPhReadings || hasDoseData || hasPumpEvents;
      
      if (empty) {
        empty.style.display = hasData ? 'none' : 'block';
      }

      var ctx = el.getContext('2d');
      if (!ctx) {
        console.error('[pH Chart] ❌ Failed to get 2D context!');
        return;
      }

      // Using previously declared fixed pH axis range (phMin, phMax)

    // Build annotations
    var annotations = {};
    
    // Hysteresis band
    if (targets && targets.low != null && targets.high != null && !isNaN(targets.low) && !isNaN(targets.high)) {
      annotations.phBand = {
        type: 'box',
        yMin: targets.low,
        yMax: targets.high,
        yScaleID: 'yPh',
        backgroundColor: 'rgba(34, 197, 94, 0.15)',
        borderWidth: 0,
        drawTime: 'beforeDatasetsDraw'
      };
      
      var setpoint = (targets.low + targets.high) / 2;
      annotations.phSetpoint = {
        type: 'line',
        yMin: setpoint,
        yMax: setpoint,
        yScaleID: 'yPh',
        borderColor: 'rgba(34, 197, 94, 0.6)',
        borderWidth: 2,
        borderDash: [6, 4],
        label: {
          display: true,
          content: 'Setpoint: ' + setpoint.toFixed(1),
          position: 'end',
          backgroundColor: 'rgba(34, 197, 94, 0.8)',
          color: '#fff',
          font: { size: 10 },
          padding: 3
        }
      };
    }

    // Weekly bands from schedule
    try {
      if (schedule && schedule.weeks && Array.isArray(schedule.weeks)) {
        var startISO = schedule.grow_start_date ? new Date(schedule.grow_start_date) : null;
        if (startISO && !isNaN(startISO.getTime())) {
          schedule.weeks.forEach(function(wk) {
            var w = Number(wk.week);
            var low = Number(wk.ph_low);
            var high = Number(wk.ph_high);
            if (!w || isNaN(low) || isNaN(high)) return;
            var xMin = new Date(startISO.getTime() + (w-1) * 7 * 24 * 3600 * 1000);
            var xMax = new Date(startISO.getTime() + w * 7 * 24 * 3600 * 1000);
            if (timeMin && xMax < timeMin) return;
            if (timeMax && xMin > timeMax) return;
            annotations['wkBand' + w] = {
              type: 'box',
              xMin: xMin,
              xMax: xMax,
              yMin: low,
              yMax: high,
              yScaleID: 'yPh',
              backgroundColor: 'rgba(34, 197, 94, 0.10)',
              borderColor: 'rgba(34, 197, 94, 0.20)',
              borderWidth: 1,
              drawTime: 'beforeDatasetsDraw'
            };
          });
        }
      }
    } catch (e) {
      console.warn('[pH Chart] Failed to add weekly bands:', e && e.message);
    }
    
    // Current pH line
    if (currentPH != null && !isNaN(currentPH)) {
      annotations.phLine = {
        type: 'line',
        yMin: currentPH,
        yMax: currentPH,
        yScaleID: 'yPh',
        borderColor: 'rgba(251, 191, 36, 0.8)',
        borderWidth: 2,
        borderDash: [6, 4],
        label: {
          display: true,
          content: 'Current: ' + currentPH.toFixed(2),
          position: 'start',
          backgroundColor: 'rgba(251, 191, 36, 0.9)',
          color: '#000',
          font: { size: 11, weight: 'bold' },
          padding: 4
        }
      };
    }
    
    // Pump events as boxes
    var maxPumpAnnotations = 100;
    if (hasPumpEvents) {
      var eventsToShow = pumpEvents.slice(0, maxPumpAnnotations);
      eventsToShow.forEach(function(evt, idx) {
        if (evt.start && evt.end) {
          var startDate = new Date(evt.start);
          var endDate = new Date(evt.end);
          if (endDate.getTime() - startDate.getTime() < ChartController.MIN_PUMP_BAR_WIDTH_MS) {
            endDate.setTime(startDate.getTime() + ChartController.MIN_PUMP_BAR_WIDTH_MS);
          }
          annotations['pump' + idx] = {
            type: 'box',
            xMin: startDate,
            xMax: endDate,
            backgroundColor: 'rgba(147, 51, 234, 0.25)',
            borderColor: 'rgba(147, 51, 234, 0.6)',
            borderWidth: 1,
            drawTime: 'beforeDatasetsDraw'
          };
        }
      });
    }

    // Build datasets
    var finalDatasets = [];
    
    if (hasPhReadings) {
      finalDatasets.push({
        type: 'line',
        label: 'pH',
        data: phReadings,
        order: 0,
        yAxisID: 'yPh',
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
        spanGaps: true
      });
    }
    
    if (datasets && datasets.length > 0) {
      datasets.forEach(function(ds) {
        var clone = {};
        for (var k in ds) clone[k] = ds[k];
        clone.yAxisID = 'yDose';
        finalDatasets.push(clone);
      });
    }
    
    var dsUse = finalDatasets.length > 0 ? finalDatasets : [{
      label: 'No data',
      data: [],
      showLine: false,
      pointRadius: 0.0001,
      borderWidth: 0
    }];

    var hasDoseAxis = dsUse.some(function(ds) { return ds.yAxisID === 'yDose' && (ds.data||[]).length > 0; });

    // Build scales
    var scales = {
      x: {
        type: 'time',
        adapters: { date: {} },
        min: timeMin || undefined,
        max: timeMax || undefined,
        ticks: { source: 'auto', maxRotation: 0, autoSkip: true },
        time: {
          tooltipFormat: 'yyyy-MM-dd HH:mm',
          displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'MMM d' }
        },
        grid: { color: 'rgba(148,163,184,0.15)', drawTicks: false }
      },
      yPh: {
        type: 'linear',
        position: 'left',
        title: { display: true, text: 'pH' },
        min: phMin,
        max: phMax,
        grid: { color: 'rgba(148,163,184,0.12)', drawTicks: false }
      }
    };
    
    if (hasDoseAxis) {
      scales.yDose = {
        type: 'linear',
        position: 'right',
        title: { display: true, text: 'Dose (ml)' },
        beginAtZero: true,
        grid: { drawOnChartArea: false }
      };
    }

    // Build plugins config - LOCKED LEGEND: use frozen config, never modify
    var pluginsConfig = {
      legend: JSON.parse(JSON.stringify(ChartController.LEGEND_CONFIG)), // Deep copy
      tooltip: {
        enabled: true,
        callbacks: {
          label: function(ctx) {
            var p = ctx.raw;
            var ds = ctx.dataset;
            
            if (ds.label === 'pH') {
              var v = Number(ctx.parsed.y);
              return ' pH: ' + v.toFixed(2);
            }
            
            if (!p) return '';
            var ml = (p.ml != null) ? '+' + p.ml.toFixed(2) + ' ml' : (p.sec != null ? '~' + p.sec.toFixed(2) + ' s' : '');
            var phStr = (p.phb != null || p.pha != null) ? '  pH: ' + (p.phb != null ? p.phb : '—') + ' → ' + (p.pha != null ? p.pha : '—') : '';
            return ml + phStr;
          }
        }
      }
    };
    
    if (ANNOTATION_AVAILABLE && Object.keys(annotations).length > 0) {
      pluginsConfig.annotation = { annotations: annotations };
    }

    // STABILITY: In-place update ONLY if chart exists and is valid
    if (ChartController.chart && ChartController.chart.canvas) {
      try {
        // Directly update datasets array
        ChartController.chart.data.datasets = dsUse;
        
        // Update x-axis bounds
        if (timeMin && timeMax) {
          ChartController.chart.options.scales.x.min = timeMin;
          ChartController.chart.options.scales.x.max = timeMax;
        }
        
        // Update y-axis bounds
        ChartController.chart.options.scales.yPh.min = phMin;
        ChartController.chart.options.scales.yPh.max = phMax;
        
        // Ensure yDose axis exists if needed
        if (hasDoseAxis && !ChartController.chart.options.scales.yDose) {
          ChartController.chart.options.scales.yDose = scales.yDose;
        }
        
        // Update annotations - preserve structure
        if (ANNOTATION_AVAILABLE) {
          if (!ChartController.chart.options.plugins.annotation) {
            ChartController.chart.options.plugins.annotation = { annotations: annotations };
          } else {
            ChartController.chart.options.plugins.annotation.annotations = annotations;
          }
        }
        
        // LOCKED LEGEND: Force legend config on every update
        ChartController.chart.options.plugins.legend = JSON.parse(JSON.stringify(ChartController.LEGEND_CONFIG));
        
        // Update without animation to prevent flicker
        ChartController.chart.update('none');
        console.log('[pH Chart] ♻ In-place update');
        return;
      } catch(updateErr) {
        console.warn('[pH Chart] In-place update failed, rebuilding:', updateErr.message);
        // Destroy and rebuild
        try {
          ChartController.chart.destroy();
        } catch(e) { /* ignore */ }
        ChartController.chart = null;
      }
    }
    
    // Create new chart (only when necessary)
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
      
      console.log('[pH Chart] ✅ Chart created');
    } catch (chartErr) {
      console.error('[pH Chart] ❌ Chart creation FAILED:', chartErr);
    }
    
    } finally {
      // Always release mutex
      ChartController.releaseMutex();
    }
  }

  /**
   * Load data and render chart with comprehensive error handling
   */
  async function phLoadRangeAndRender(params) {
    // Initialize rolling state if this is first call
    if (!ChartController.rolling.initialized) {
      ChartController.rolling.endMs = ChartController.roundTs(Date.now());
      ChartController.rolling.initialized = true;
      console.log('[pH Chart] Rolling window initialized');
    }
    
    var start = params.start;
    var end = params.end;
    
    var toIso = function(v) {
      if (v == null) return null;
      if (typeof v === 'string') {
        try {
          var d = new Date(v);
          if (!isNaN(d.getTime())) return d.toISOString();
        } catch(e) {}
        return v;
      }
      if (typeof v === 'number') {
        var d2 = new Date(v);
        return isNaN(d2.getTime()) ? null : d2.toISOString();
      }
      return null;
    };

    var startISO = toIso(start);
    var endISO = toIso(end);

    var startMs = startISO ? new Date(startISO).getTime() : Date.now() - 3600*1000;
    var endMs = endISO ? new Date(endISO).getTime() : Date.now();
    var spanMs = endMs - startMs;
    var params2 = presetParams(spanMs);
    var gran = params2.gran;
    var max = params2.max;

    var uEvents = '/api/ph/dose_log?start=' + encodeURIComponent(startISO) + '&end=' + encodeURIComponent(endISO) + '&limit=2000';
    var uStatus = '/api/ph/status';

    var events = [];
    var currentPH = null;
    var targets = null;
    var phReadings = [];
    var schedule = null;
    var fetchError = null;
    
    try {
      var results = await Promise.all([
        fetch(uEvents, {cache:'no-store'}).catch(function(e) { return { ok: false, error: e }; }), 
        fetch(uStatus, {cache:'no-store'}).catch(function(e) { return { ok: false, error: e }; }),
        fetch('/api/nutrient_schedule', {cache:'no-store'}).catch(function(e) { return { ok: false, error: e }; }),
        fetchPhReadings(startISO, endISO, gran, max)
      ]);
      
      var eRes = results[0];
      var stRes = results[1];
      var schedRes = results[2];
      var phResult = results[3];
      
      if (eRes.ok) {
        events = await eRes.json();
      } else {
        fetchError = eRes.error || ('dose_log HTTP ' + eRes.status);
      }
      
      phReadings = phResult.data;
      if (phResult.error) fetchError = fetchError || phResult.error;
      
      if (stRes.ok) {
        var statusData = await stRes.json();
        currentPH = statusData && statusData.ph != null ? statusData.ph : null;
        targets = statusData && statusData.targets ? statusData.targets : null;
      }
      
      if (schedRes && schedRes.ok) {
        schedule = await schedRes.json();
      }
    } catch (err) {
      console.error('[pH Chart] fetch error:', err);
      fetchError = err.message;
    }

    // Show error indicator if fetch failed but still try to render available data
    var errorIndicator = document.getElementById('ph-chart-error');
    if (errorIndicator) {
      if (fetchError && events.length === 0 && phReadings.length === 0) {
        errorIndicator.textContent = '⚠ ' + fetchError;
        errorIndicator.style.display = 'block';
      } else {
        errorIndicator.style.display = 'none';
      }
    }

    // Build pump events
    var pumpEvents = events.map(function(r) {
      var evtStart = new Date(r.ts);
      var durationMs = (r.seconds != null ? r.seconds : 0) * 1000;
      var evtEnd = new Date(evtStart.getTime() + durationMs);
      return {
        start: evtStart.toISOString(),
        end: evtEnd.toISOString(),
        label: r.pump || 'pH Up',
        showLabel: false
      };
    });

    // Build dose datasets
    var hasAnyMl = events.some(function(r) { return r && r.volume_ml != null; });
    
    var dosePoints = events.map(function(r) {
      return {
        x: new Date(r.ts),
        y: hasAnyMl ? (r.volume_ml != null ? r.volume_ml : 0) : (r.seconds != null ? r.seconds : 0),
        ml: r.volume_ml != null ? r.volume_ml : null,
        sec: r.seconds != null ? r.seconds : null,
        phb: r.ph_before != null ? r.ph_before : null,
        pha: r.ph_after != null ? r.ph_after : null
      };
    });

    var doseDatasets = [];
    if (dosePoints.length > 0) {
      doseDatasets.push({
        type: 'scatter',
        label: hasAnyMl ? 'Dose (ml)' : 'Dose (s)',
        data: dosePoints,
        order: 1,
        yAxisID: 'yDose',
        pointRadius: 5,
        pointStyle: 'triangle',
        backgroundColor: 'rgba(34, 197, 94, 0.9)',
        borderColor: 'rgba(34, 197, 94, 1)',
        borderWidth: 1
      });
    }

    var tmin = startISO ? new Date(startISO) : null;
    var tmax = endISO ? new Date(endISO) : null;
    phBuildChart(doseDatasets, tmin, tmax, currentPH, targets, phReadings, pumpEvents, schedule);

    // Update totals KPI
    var pill = document.getElementById('ph-total-dosed');
    if (pill) {
      var sumMl = 0, sumSec = 0;
      events.forEach(function(r) {
        sumMl += (r.volume_ml != null ? r.volume_ml : 0);
        sumSec += (r.seconds != null ? r.seconds : 0);
      });
      
      if (hasAnyMl && sumMl > 0) {
        pill.textContent = 'Total: ' + sumMl.toFixed(1) + ' ml';
        pill.style.display = 'inline-block';
      } else if (sumSec > 0) {
        pill.textContent = 'Total: ' + sumSec.toFixed(1) + ' s';
        pill.style.display = 'inline-block';
      } else if (events.length > 0) {
        pill.textContent = events.length + ' doses';
        pill.style.display = 'inline-block';
      } else {
        pill.style.display = 'none';
      }
    }

    // Update state
    if (ChartController.userRangeSelected || !ChartController.rolling.active) {
      ChartController.state = { 
        lastStart: startISO || start || null, 
        lastEnd: endISO || end || null, 
        lastCount: events.length,
        lastFetchTs: Date.now()
      };
    } else {
      ChartController.state.lastCount = events.length;
      ChartController.state.lastFetchTs = Date.now();
    }
  }

  /**
   * Initialize chart
   */
  function init() {
    console.log('[pH Chart] 🚀 Init');
    
    // Restore persisted state if available
    var restored = ChartController.restoreState();
    
    if (restored && ChartController.state.lastStart && ChartController.state.lastEnd) {
      // Use restored range
      phLoadRangeAndRender({
        start: ChartController.state.lastStart,
        end: ChartController.state.lastEnd
      });
    } else {
      // Default 1h range
      var now = new Date();
      var start = new Date(now.getTime() - 3600*1000).toISOString();
      var end = now.toISOString();
      phLoadRangeAndRender({start: start, end: end});
    }
  }

  /**
   * Set user range (disables rolling)
   */
  function setRange(start, end) {
    var startMs = typeof start === 'string' ? new Date(start).getTime() : start;
    var endMs = typeof end === 'string' ? new Date(end).getTime() : end;
    
    if (isFinite(startMs) && isFinite(endMs) && endMs > startMs) {
      ChartController.userRangeSelected = true;
      ChartController.rolling.active = false;
      ChartController.state.lastStart = new Date(startMs).toISOString();
      ChartController.state.lastEnd = new Date(endMs).toISOString();
      ChartController.rolling.spanMs = endMs - startMs;
      ChartController.saveState();
      console.log('[pH Chart] User range set:', { startMs: startMs, endMs: endMs });
    }
  }
  
  /**
   * Reset to rolling mode
   */
  function resetToRolling() {
    ChartController.userRangeSelected = false;
    ChartController.rolling.active = true;
    ChartController.rolling.endMs = ChartController.roundTs(Date.now());
    ChartController.rolling.spanMs = ChartController.ROLLING_DEFAULT_SPAN_MS;
    ChartController.rolling.initialized = true;
    ChartController.clearState();
    
    console.log('[pH Chart] Reset to rolling mode');
    
    var endMs = ChartController.rolling.endMs;
    var startMs = endMs - ChartController.rolling.spanMs;
    phLoadRangeAndRender({
      start: new Date(startMs).toISOString(),
      end: new Date(endMs).toISOString()
    });
  }
  
  /**
   * Check if user range is selected
   */
  function isUserRangeSelected() {
    return ChartController.userRangeSelected;
  }

  // Export public API
  window.phDoseChart = {
    render: phLoadRangeAndRender,
    getState: function() { return ChartController.state; },
    init: init,
    setRange: setRange,
    resetToRolling: resetToRolling,
    isUserRangeSelected: isUserRangeSelected
  };

  // Auto-init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // REMOVED INTERNAL AUTO-REFRESH: ph.js pollingManager drives all updates via phLoadRangeAndRender
  // This eliminates competing refresh timers that caused legend/data flicker
  
  // Handle visibility changes - just track state, let ph.js handle refresh timing
  document.addEventListener('visibilitychange', function() {
    ChartController.isVisible = !document.hidden;
    console.log('[pH Chart] Tab visibility:', ChartController.isVisible ? 'visible' : 'hidden');
  });
  
  // Stub functions for backward compatibility (ph.js may call these)
  function startAutoRefresh() {
    console.log('[pH Chart] Auto-refresh managed by ph.js pollingManager');
  }
  
  function stopAutoRefresh() {
    console.log('[pH Chart] Auto-refresh managed by ph.js pollingManager');
  }
  
  window.phDoseChart.startAutoRefresh = startAutoRefresh;
  window.phDoseChart.stopAutoRefresh = stopAutoRefresh;

  console.log('[pH Chart] Module initialized');

  // Update build commit chip
  try {
    var chip = document.getElementById('build-commit-chip');
    if (chip && window.BUILD_COMMIT) {
      chip.textContent = 'commit: ' + window.BUILD_COMMIT;
      chip.className = 'ui-status-chip success';
    }
  } catch(e) { /* ignore */ }

})();
