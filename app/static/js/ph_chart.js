// pH Dose Chart Rendering Module
// Shows pH sensor readings over time (hysteresis) with dose events overlaid
// pH-only: no EC or temperature data displayed here (use Sensors tab for that)
(function(){
  console.log('[pH Chart] Loader enter (ph_chart.js start)');
  'use strict';

  // Module state
  let PH_CHART = null;
  let PH_CHART_STATE = { lastStart: null, lastEnd: null, lastCount: 0 };
  // Rolling window & user range selection flags (defined early so all functions can reference)
  let USER_RANGE_SELECTED = false;
  let ROLLING_STATE = { active: true, initialized: false, spanMs: 3600*1000, endMs: Date.now() };

  // Constants
  const MIN_PUMP_BAR_WIDTH_MS = 5000; // Minimum 5 seconds width for pump event visibility
  
  // Check annotation plugin availability
  let ANNOTATION_AVAILABLE = false;
  
  // Chart.js v4 UMD bundle auto-registers all core components (controllers, elements, scales, plugins).
  // We only need to register the external annotation plugin if present.
  // NOTE: Do NOT try to access Chart.controllers, Chart.elements, Chart.scales, or Chart.plugins
  // as these are not exposed as properties on the Chart object in the UMD bundle.
  if (window.Chart && typeof Chart.register === 'function') {
    // Register annotation plugin if available (UMD global can be exported under different names)
    const annoPlugin = (
      // Preferred UMD export name used by chartjs-plugin-annotation v3
      window['chartjs-plugin-annotation'] ||
      // Some bundles expose it via a nested chartjs namespace
      (window.chartjs && window.chartjs['plugin-annotation']) ||
      // Older name sometimes used
      window.ChartAnnotation
    );
    
    if (annoPlugin) {
      try {
        Chart.register(annoPlugin);
        ANNOTATION_AVAILABLE = true;
        console.log('[pH Chart] ✓ Annotation plugin registered successfully');
      } catch (regErr) {
        // Plugin may already be registered - check if it's working
        console.debug('[pH Chart] Annotation plugin registration:', regErr?.message);
        // Assume it's available if no critical error
        ANNOTATION_AVAILABLE = true;
      }
    } else {
      console.warn('[pH Chart] ⚠ Annotation plugin not found - pump bars, hysteresis band, and setpoint line will not display');
    }
  } else {
    console.error('[pH Chart] ❌ Chart.js not loaded or Chart.register not available');
  }

  /**
   * Build or rebuild the pH-only chart with sensor readings and dose events overlay
   * @param {Array} datasets - Chart.js datasets for dose events
   * @param {string|null} timeMin - ISO timestamp or null
   * @param {string|null} timeMax - ISO timestamp or null
   * @param {number|null} currentPH - Current live pH reading
   * @param {Object|null} targets - {low: number, high: number} pH target range
   * @param {Array} phReadings - Array of {x: Date, y: number} pH sensor readings
   * @param {Array} pumpEvents - Array of pump ON/OFF events
   */
  function phBuildChart(datasets, timeMin, timeMax, currentPH, targets, phReadings, pumpEvents, schedule) {
    console.log('[pH Chart] 🔧 phBuildChart called', {
      datasetsCount: datasets?.length,
      timeMin, timeMax, currentPH, targets,
      phReadingsCount: phReadings?.length,
      pumpEventsCount: pumpEvents?.length,
      hasSchedule: !!schedule
    });

    // If rolling state is active and initialized and user has NOT selected a fixed range,
    // enforce monotonic window regardless of incoming timeMin/timeMax to prevent back jumps.
    if (ROLLING_STATE.initialized && ROLLING_STATE.active && !USER_RANGE_SELECTED) {
      const enforcedMax = new Date(ROLLING_STATE.endMs);
      const enforcedMin = new Date(ROLLING_STATE.endMs - ROLLING_STATE.spanMs);
      timeMin = enforcedMin;
      timeMax = enforcedMax;
      console.log('[pH Chart] ⏩ Enforcing monotonic window', { enforcedMin, enforcedMax });
    }
    
    const el = document.getElementById('phDoseChart');
    const empty = document.getElementById('ph-dose-empty');

    if (!el) {
      console.error('[pH Chart] ❌ Canvas #phDoseChart not found!');
      return;
    }
    
    console.log('[pH Chart] Canvas found:', el.tagName, 'width:', el.clientWidth, 'height:', el.clientHeight);

    // Check if we have pH data or dose events
    const hasPhReadings = phReadings && phReadings.length > 0;
    const hasDoseData = datasets && datasets.some(ds => (ds.data||[]).length > 0);
    const hasPumpEvents = pumpEvents && pumpEvents.length > 0;
    const hasData = hasPhReadings || hasDoseData || hasPumpEvents;
    
    console.log('[pH Chart] Data flags:', { hasPhReadings, hasDoseData, hasPumpEvents, hasData });
    
    if (hasPhReadings && phReadings.length > 0) {
      console.log('[pH Chart] First pH reading:', phReadings[0]);
      console.log('[pH Chart] Last pH reading:', phReadings[phReadings.length - 1]);
    }
    
    if (empty) {
      empty.style.display = hasData ? 'none' : 'block';
    }

    const ctx = el.getContext('2d');
    if (!ctx) {
      console.error('[pH Chart] ❌ Failed to get 2D context from canvas!');
      return;
    }

    // Destroy previous
    if (PH_CHART && typeof PH_CHART.destroy === 'function') {
      console.log('[pH Chart] Destroying previous chart instance');
      PH_CHART.destroy();
      PH_CHART = null;
    }

    // Calculate pH axis range based on data and targets
    let phMin = 4.5, phMax = 8.0;  // Default range for pH
    if (hasPhReadings) {
      const phValues = phReadings.map(p => p.y).filter(v => v != null && !isNaN(v));
      console.log('[pH Chart] Valid pH values:', phValues.length);
      if (phValues.length > 0) {
        const dataMin = Math.min(...phValues);
        const dataMax = Math.max(...phValues);
        // Expand range to include data with padding
        phMin = Math.min(phMin, dataMin - 0.2);
        phMax = Math.max(phMax, dataMax + 0.2);
      }
    }
    // Include targets in range
    if (targets && targets.low != null) phMin = Math.min(phMin, targets.low - 0.3);
    if (targets && targets.high != null) phMax = Math.max(phMax, targets.high + 0.3);
    // Include current pH in range
    if (currentPH != null) {
      phMin = Math.min(phMin, currentPH - 0.2);
      phMax = Math.max(phMax, currentPH + 0.2);
    }

    // Build annotation plugin config for pH reference line, hysteresis band(s), setpoint, and pump events
    const annotations = {};
    
    // Add hysteresis band (shaded region between low and high targets) FIRST so it's behind everything
    if (targets && targets.low != null && targets.high != null && !isNaN(targets.low) && !isNaN(targets.high)) {
      console.log('[pH Chart] Adding hysteresis band:', targets.low, '-', targets.high);
      annotations.phBand = {
        type: 'box',
        yMin: targets.low,
        yMax: targets.high,
        yScaleID: 'yPh',
        backgroundColor: 'rgba(34, 197, 94, 0.15)',  // green with low opacity
        borderWidth: 0,
        drawTime: 'beforeDatasetsDraw'  // Draw band behind data
      };
      
      // Add setpoint line (midpoint of targets)
      const setpoint = (targets.low + targets.high) / 2;
      console.log('[pH Chart] Adding setpoint line at:', setpoint);
      annotations.phSetpoint = {
        type: 'line',
        yMin: setpoint,
        yMax: setpoint,
        yScaleID: 'yPh',
        borderColor: 'rgba(34, 197, 94, 0.6)',  // green-500 with transparency
        borderWidth: 2,
        borderDash: [6, 4],
        label: {
          display: true,
          content: `Setpoint: ${setpoint.toFixed(1)}`,
          position: 'end',
          backgroundColor: 'rgba(34, 197, 94, 0.8)',
          color: '#fff',
          font: { size: 10 },
          padding: 3
        }
      };
    } else {
      console.warn('[pH Chart] No targets for hysteresis band:', targets);
    }

    // Add time-varying hysteresis bands per grow week across x-axis, using schedule
    try {
      if (schedule && Array.isArray(schedule.weeks)) {
        const startISO = schedule.grow_start_date ? new Date(schedule.grow_start_date) : null;
        if (startISO && !isNaN(startISO.getTime())) {
          schedule.weeks.forEach((wk) => {
            const w = Number(wk.week);
            const low = Number(wk.ph_low);
            const high = Number(wk.ph_high);
            if (!w || isNaN(low) || isNaN(high)) return;
            const xMin = new Date(startISO.getTime() + (w-1) * 7 * 24 * 3600 * 1000);
            const xMax = new Date(startISO.getTime() + w * 7 * 24 * 3600 * 1000);
            // Only add if overlaps current view range
            if (timeMin && xMax < timeMin) return;
            if (timeMax && xMin > timeMax) return;
            const key = `wkBand${w}`;
            annotations[key] = {
              type: 'box',
              xMin, xMax,
              yMin: low, yMax: high,
              yScaleID: 'yPh',
              backgroundColor: 'rgba(34, 197, 94, 0.10)',
              borderColor: 'rgba(34, 197, 94, 0.20)',
              borderWidth: 1,
              drawTime: 'beforeDatasetsDraw'
            };
          });
          console.log('[pH Chart] Added week bands:', Object.keys(annotations).filter(k=>k.startsWith('wkBand')).length);
        } else {
          console.warn('[pH Chart] No grow_start_date in schedule; skipping week bands');
        }
      }
    } catch (e) {
      console.warn('[pH Chart] Failed to add weekly bands:', e?.message);
    }
    
    // Add current pH reference line
    if (currentPH != null && !isNaN(currentPH)) {
      annotations.phLine = {
        type: 'line',
        yMin: currentPH,
        yMax: currentPH,
        yScaleID: 'yPh',
        borderColor: 'rgba(251, 191, 36, 0.8)',  // amber-400
        borderWidth: 2,
        borderDash: [6, 4],
        label: {
          display: true,
          content: `Current: ${currentPH.toFixed(2)}`,
          position: 'start',
          backgroundColor: 'rgba(251, 191, 36, 0.9)',
          color: '#000',
          font: { size: 11, weight: 'bold' },
          padding: 4
        }
      };
    }
    
    // Add pump events as vertical box annotations (show when pump was running)
    // Limit to avoid performance issues with many events
    const maxPumpAnnotations = 100;
    if (hasPumpEvents) {
      console.log('[pH Chart] Adding pump annotations for', Math.min(pumpEvents.length, maxPumpAnnotations), 'events');
      if (pumpEvents.length > maxPumpAnnotations) {
        console.warn(`[pH Chart] Truncating pump annotations: ${pumpEvents.length} events, showing first ${maxPumpAnnotations}`);
      }
      const eventsToShow = pumpEvents.slice(0, maxPumpAnnotations);
      let addedCount = 0;
      eventsToShow.forEach((evt, idx) => {
        if (evt.start && evt.end) {
          const startDate = new Date(evt.start);
          const endDate = new Date(evt.end);
          // Ensure minimum width for visibility (use module constant)
          if (endDate.getTime() - startDate.getTime() < MIN_PUMP_BAR_WIDTH_MS) {
            endDate.setTime(startDate.getTime() + MIN_PUMP_BAR_WIDTH_MS);
          }
          annotations[`pump${idx}`] = {
            type: 'box',
            xMin: startDate,
            xMax: endDate,
            backgroundColor: 'rgba(147, 51, 234, 0.25)',  // purple with low opacity
            borderColor: 'rgba(147, 51, 234, 0.6)',
            borderWidth: 1,
            drawTime: 'beforeDatasetsDraw'
          };
          addedCount++;
        }
      });
      console.log('[pH Chart] Added', addedCount, 'pump box annotations');
    }
    
    // Log final annotations for debugging
    const annotationKeys = Object.keys(annotations);
    console.log('[pH Chart] Final annotations:', annotationKeys.length, 'keys:', annotationKeys.slice(0, 10).join(', '), annotationKeys.length > 10 ? '...' : '');

    // Build final datasets array: pH readings line, then dose datasets
    const finalDatasets = [];
    
    // Add pH readings line dataset (primary)
    if (hasPhReadings) {
      finalDatasets.push({
        type: 'line',
        label: 'pH',
        data: phReadings,
        order: 0,  // Draw first (behind others)
        yAxisID: 'yPh',
        borderColor: '#3b82f6',  // blue-500
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
        spanGaps: true
      });
    }
    
    // Add dose event datasets (on secondary Y-axis)
    if (datasets && datasets.length > 0) {
      datasets.forEach(ds => {
        // Clone and assign to dose Y-axis
        finalDatasets.push({
          ...ds,
          yAxisID: 'yDose'
        });
      });
    }
    
    // Ensure at least one stub dataset so legend/axes render
    const dsUse = finalDatasets.length > 0 ? finalDatasets : [{
      label: 'No data',
      data: [],
      showLine: false,
      pointRadius: 0.0001,
      borderWidth: 0
    }];

    // Check if we have dose data for secondary axis
    const hasDoseAxis = dsUse.some(ds => ds.yAxisID === 'yDose' && (ds.data||[]).length > 0);

    // Build scales: pH on left, dose on right (pH-only chart)
    const scales = {
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
    
    // Add dose axis on right if we have dose data
    if (hasDoseAxis) {
      scales.yDose = {
        type: 'linear',
        position: 'right',
        title: { display: true, text: 'Dose (ml)' },
        beginAtZero: true,
        grid: { drawOnChartArea: false }
      };
    }

    // Build plugins config - only include annotation if plugin is available
    const pluginsConfig = {
      legend: { 
        display: true,
        position: 'top',
        labels: { usePointStyle: true, boxWidth: 10, padding: 12 }
      },
      tooltip: {
        enabled: true,
        callbacks: {
          label: (ctx) => {
            const p = ctx.raw;
            const ds = ctx.dataset;
            
            // pH readings tooltip
            if (ds.label === 'pH') {
              const v = Number(ctx.parsed.y);
              return ` pH: ${v.toFixed(2)}`;
            }
            
            // Dose event tooltip
            if (!p) return '';
            const ml = (p.ml != null) ? `+${p.ml.toFixed(2)} ml` : (p.sec != null ? `~${p.sec.toFixed(2)} s` : '');
            const ph = (p.phb != null || p.pha != null) ? `  pH: ${p.phb ?? '—'} → ${p.pha ?? '—'}` : '';
            return `${ml}${ph}`;
          }
        }
      }
    };
    
    // Add annotation config only if plugin is available
    if (ANNOTATION_AVAILABLE && Object.keys(annotations).length > 0) {
      pluginsConfig.annotation = { annotations: annotations };
      console.log('[pH Chart] Annotations enabled with', Object.keys(annotations).length, 'items');
    } else if (!ANNOTATION_AVAILABLE) {
      console.warn('[pH Chart] Annotations skipped - plugin not available');
    }

    console.log('[pH Chart] 📊 Creating Chart.js instance with:', {
      datasetsCount: dsUse.length,
      scalesKeys: Object.keys(scales),
      pluginsKeys: Object.keys(pluginsConfig),
      annotationsCount: Object.keys(annotations).length
    });
    
    try {
      PH_CHART = new Chart(ctx, {
        type: 'line',
        data: { datasets: dsUse },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          parsing: false,
          animation: false,  // Disable animations for instant updates
          interaction: {
            mode: 'nearest',
            intersect: false
          },
          scales: scales,
          plugins: pluginsConfig
        }
      });
      
      console.log('[pH Chart] ✅ Chart created successfully, datasets:', PH_CHART.data.datasets.length);
    } catch (chartErr) {
      console.error('[pH Chart] ❌ Chart creation FAILED:', chartErr);
      return;
    }

    console.debug('[pH] Chart created/rebuilt', { hasData, hasPhReadings, hasDoseData, datasetCount: dsUse.length, currentPH, annotationAvailable: ANNOTATION_AVAILABLE });
  }

  // Granularity constants for time-based bucketing (in seconds)
  const GRANULARITY = {
    FINE: 30,       // 30-second buckets for short ranges (<2h)
    MINUTE: 60,     // 1-minute buckets for day ranges
    FIVE_MIN: 300,  // 5-minute buckets for week ranges
    QUARTER: 900,   // 15-minute buckets for month ranges
    HOURLY: 3600    // Hourly buckets for 90+ days
  };

  /**
   * Compute granularity params based on time range (matching trends.js logic)
   */
  function presetParams(spanMs) {
    const hours = spanMs / (3600 * 1000);
    if (hours <= 2)   return { gran: GRANULARITY.FINE,     max: 1000 };  // 30s buckets for short ranges
    if (hours <= 24)  return { gran: GRANULARITY.MINUTE,   max: 1500 };  // 1-min buckets
    if (hours <= 168) return { gran: GRANULARITY.FIVE_MIN, max: 2100 };  // 5-min buckets (7 days)
    if (hours <= 720) return { gran: GRANULARITY.QUARTER,  max: 3000 };  // 15-min buckets (30 days)
    return { gran: GRANULARITY.HOURLY, max: 2500 };  // hourly buckets (90+ days)
  }

  /**
   * Fetch pH readings only from trends API
   */
  async function fetchPhReadings(fromISO, toISO, gran, max) {
    const q = new URLSearchParams();
    if (fromISO) q.set('from', fromISO);
    if (toISO) q.set('to', toISO);
    if (gran) q.set('gran', String(gran));
    if (max) q.set('max', String(max));
    
    const url = '/api/trends?' + q.toString();
    console.log('[pH Chart] Fetching pH readings from:', url);
    
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) {
        console.warn('[pH Chart] Trends API failed:', res.status);
        return [];
      }
      const data = await res.json();
      console.log('[pH Chart] Got pH readings:', data?.series?.ph?.length || 0);
      
      // Convert pH series to Chart.js format: {x: Date, y: number}
      // API returns timestamps in Unix epoch seconds, multiply by 1000 for Date
      const phSeries = (data?.series?.ph || []).map(p => ({
        x: new Date(p.ts * 1000),
        y: Number(p.value)
      })).filter(p => !isNaN(p.y));
      
      return phSeries;
    } catch (err) {
      console.error('[pH Chart] Failed to fetch pH readings:', err);
      return [];
    }
  }

  /**
   * Load dose data and pH readings for a given range and render the chart
   * @param {Object} params - {start: ISO string, end: ISO string}
   */
  async function phLoadRangeAndRender({start, end}) {
    // Normalize inputs: accept epoch ms numbers or ISO strings; always send ISO with 'Z'
    const toIso = (v) => {
      if (v == null) return null;
      // If already looks like an ISO string, pass through (ensure Z if missing timezone by treating as Date)
      if (typeof v === 'string') {
        // If string has no timezone, coerce via Date to normalize to UTC Z
        try {
          const d = new Date(v);
          if (!isNaN(d.getTime())) return d.toISOString();
        } catch(e) {/* fallthrough */}
        return v;
      }
      if (typeof v === 'number') {
        const d = new Date(v);
        return isNaN(d.getTime()) ? null : d.toISOString();
      }
      return null;
    };

    const startISO = toIso(start);
    const endISO = toIso(end);

    console.log('[pH Chart] Range request', {start, end, startISO, endISO});

    // Calculate time span for granularity
    const startMs = startISO ? new Date(startISO).getTime() : Date.now() - 3600*1000;
    const endMs = endISO ? new Date(endISO).getTime() : Date.now();
    const spanMs = endMs - startMs;
    const { gran, max } = presetParams(spanMs);

    // Build URLs for events, summary, and live pH
    const uEvents = `/api/ph/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`;
    const uStatus = `/api/ph/status`;

    console.log('[pH Chart] Fetching', {uEvents, uStatus, gran, max});

    let events = [];
    let currentPH = null;
    let targets = null;
    let phReadings = [];
    let schedule = null;  // Declare schedule outside try block for proper scoping
    
    try {
      // Fetch all data in parallel: dose events, status, schedule, AND pH readings
      const [eRes, stRes, schedRes, phData] = await Promise.all([
        fetch(uEvents, {cache:'no-store'}), 
        fetch(uStatus, {cache:'no-store'}),
        fetch('/api/nutrient_schedule', {cache:'no-store'}),
        fetchPhReadings(startISO, endISO, gran, max)
      ]);
      
      console.log('[pH Chart] Response status', {
        events: eRes.status, 
        status: stRes.status,
        schedule: schedRes.status,
        phReadings: phData.length
      });
      
      if (!eRes.ok) throw new Error(`dose_log HTTP ${eRes.status}`);
      
      events = await eRes.json();
      phReadings = phData;
      
      if (stRes.ok) {
        const statusData = await stRes.json();
        currentPH = statusData?.ph ?? null;
        targets = statusData?.targets ?? null;
      }
      // Parse schedule for time-varying pH band
      if (schedRes && schedRes.ok) {
        schedule = await schedRes.json();
      }
    } catch (err) {
      console.error('[pH Chart] fetch error:', err);
      phBuildChart([], null, null, null, null, [], []);
      return;
    }

    console.log('[pH Chart] Data received', {
      events: events.length, 
      phReadings: phReadings.length
    });

    // Build pump event periods from dose_events
    // Each dose event represents a pump ON period; construct start/end pairs
    const pumpEvents = events.map(r => {
      const evtStart = new Date(r.ts);
      const durationMs = (r.seconds ?? 0) * 1000;
      const evtEnd = new Date(evtStart.getTime() + durationMs);
      return {
        start: evtStart.toISOString(),
        end: evtEnd.toISOString(),
        label: r.pump || 'pH Up',
        showLabel: false  // Hide labels to avoid clutter; boxes are enough
      };
    });
    console.log('[pH Chart] Pump events constructed:', pumpEvents.length);

    // Build dose event datasets
    const hasAnyMl = events.some(r => r && r.volume_ml != null);
    console.log('[pH Chart] hasAnyMl:', hasAnyMl, 'sample event:', events[0]);
    
    // Dose events as scatter points (shown on secondary Y-axis)
    const dosePoints = events.map(r => ({
      x: new Date(r.ts),  // Convert ISO string to Date object for Chart.js
      y: hasAnyMl ? (r.volume_ml != null ? r.volume_ml : 0) : (r.seconds ?? 0),
      ml: (r.volume_ml != null ? r.volume_ml : null),
      sec: r.seconds ?? null,
      phb: r.ph_before ?? null,
      pha: r.ph_after ?? null
    }));
    console.log('[pH Chart] Sample dose point:', dosePoints[0]);

    // Build dose datasets
    const doseDatasets = [];
    
    // Dose events scatter (green triangle markers) - assigned to yDose axis
    if (dosePoints.length > 0) {
      doseDatasets.push({
        type: 'scatter',
        label: hasAnyMl ? 'Dose (ml)' : 'Dose (s)',
        data: dosePoints,
        order: 1,
        yAxisID: 'yDose',  // Secondary Y-axis for dose values
        pointRadius: 5,
        pointStyle: 'triangle',
        backgroundColor: 'rgba(34, 197, 94, 0.9)',  // green
        borderColor: 'rgba(34, 197, 94, 1)',
        borderWidth: 1
      });
    }

    // Render chart with pH readings only, dose events, and pump activity
    const tmin = startISO ? new Date(startISO) : null;
    const tmax = endISO ? new Date(endISO) : null;
    console.log('[pH Chart] Axis bounds (from request)', {
      tmin, tmax, startISO, endISO, currentPH, targets, 
      phReadings: phReadings.length,
      pumpEvents: pumpEvents.length
    });
    phBuildChart(doseDatasets, tmin, tmax, currentPH, targets, phReadings, pumpEvents, schedule);

    // Update totals KPI pill with total ml dosed
    const pill = document.getElementById('ph-total-dosed');
    console.log('[pH Chart] Totals KPI pill element:', pill ? 'found' : 'NOT FOUND');
    if (pill) {
      let sumMl = 0, sumSec = 0;
      events.forEach(r => {
        sumMl += (r.volume_ml ?? 0);
        sumSec += (r.seconds ?? 0);
      });
      console.log('[pH Chart] Totals computed:', { sumMl, sumSec, hasAnyMl, eventCount: events.length });
      
      if (hasAnyMl && sumMl > 0) {
        pill.textContent = `Total: ${sumMl.toFixed(1)} ml`;
        pill.style.display = 'inline-block';
      } else if (sumSec > 0) {
        pill.textContent = `Total: ${sumSec.toFixed(1)} s`;
        pill.style.display = 'inline-block';
      } else if (events.length > 0) {
        // If we have events but no ml or seconds, show count
        pill.textContent = `${events.length} doses`;
        pill.style.display = 'inline-block';
      } else {
        pill.style.display = 'none';
      }
      console.log('[pH Chart] Totals KPI updated:', pill.textContent, 'display:', pill.style.display);
    }

    PH_CHART_STATE = { lastStart: startISO || start || null, lastEnd: endISO || end || null, lastCount: events.length };
    console.log('[pH Chart] ✅ Render complete', PH_CHART_STATE);
  }

  /**
   * Initialize on DOM ready with default 1h range (to show recent activity clearly)
   */
  function init() {
    console.log('[pH Chart] 🚀 Init: DOM ready; boot dose chart with default 1h');
    
    // Compute default start/end (1h for detailed recent view)
    const now = new Date();
    const start = new Date(now.getTime() - 3600*1000).toISOString();  // 1 hour
    const end = now.toISOString();
    
    console.log('[pH Chart] Default range', {start, end});
    phLoadRangeAndRender({start, end});
  }

  // Export functions for external use
  window.phDoseChart = {
    render: phLoadRangeAndRender,
    getState: () => PH_CHART_STATE,
    init: init
  };

  // Auto-init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Auto-refresh chart every 10 seconds for smoother, less erratic shifts
  // User-selected ranges are preserved (no rolling). Only default 1h range auto-rolls.
  let autoRefreshTimer = null;
  // ROLLING_STATE & USER_RANGE_SELECTED declared at top
  
  function startAutoRefresh() {
    if (autoRefreshTimer) return; // Already running
    
    console.log('[pH Chart] Starting auto-refresh (10s interval)');
    // Initialize rolling span once from current state
      if (!ROLLING_STATE.initialized) {
      const ls = PH_CHART_STATE?.lastStart;
      const le = PH_CHART_STATE?.lastEnd;
      if (ls && le) {
        const s = new Date(ls).getTime();
        const e = new Date(le).getTime();
        if (isFinite(s) && isFinite(e) && e > s) {
          ROLLING_STATE.spanMs = e - s;
        }
      }
      ROLLING_STATE.endMs = Date.now();
      ROLLING_STATE.initialized = true;
    }

    autoRefreshTimer = setInterval(() => {
      let startISO = PH_CHART_STATE.lastStart;
      let endISO = PH_CHART_STATE.lastEnd;

      if (!USER_RANGE_SELECTED && ROLLING_STATE.active) {
        // Monotonic advance: prefer steady cadence, never go backwards
        const stepMs = 10000; // 10s
        ROLLING_STATE.endMs = Math.max(ROLLING_STATE.endMs + stepMs, Date.now());
        const endMs = ROLLING_STATE.endMs;
        const startMs = endMs - ROLLING_STATE.spanMs;
        endISO = new Date(endMs).toISOString();
        startISO = new Date(startMs).toISOString();
        console.log('[pH Chart] Auto-refresh with monotonic rolling window');
      } else {
        // User selected a range - just refresh data within that fixed window
        console.log('[pH Chart] Auto-refresh with fixed user range');
      }

      phLoadRangeAndRender({ start: startISO, end: endISO });
    }, 10000); // 10 second interval for smoother live updates matching sensors chart cadence
  }
  
  function stopAutoRefresh() {
    if (autoRefreshTimer) {
      console.log('[pH Chart] Stopping auto-refresh');
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }
  
  // Start auto-refresh when module loads
  startAutoRefresh();
  
  // Export auto-refresh controls
  window.phDoseChart.startAutoRefresh = startAutoRefresh;
  window.phDoseChart.stopAutoRefresh = stopAutoRefresh;

  console.log('[pH Chart] Module initialized and window.phDoseChart exported');

  // Update build commit chip dynamically if present
  try {
    const chip = document.getElementById('build-commit-chip');
    if (chip && window.BUILD_COMMIT) {
      chip.textContent = 'commit: ' + window.BUILD_COMMIT;
      chip.className = 'ui-status-chip success';
    }
  } catch(e) { /* ignore */ }

})();
