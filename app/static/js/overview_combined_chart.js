(function() {
  'use strict';

  function formatRangeLabel(startMs, endMs) {
    const fmt = (ts) => {
      const d = new Date(ts);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mi = String(d.getMinutes()).padStart(2, '0');
      return `${mm}/${dd} ${hh}:${mi}`;
    };
    const el = document.getElementById('overview-combined-range');
    if (el) {
      el.textContent = `${fmt(startMs)} — ${fmt(endMs)}`;
    }
  }

  function buildStepSeries(events, window, level) {
    // Returns horizontal-only segments: y=level when ON, y=null when OFF.
    // null values break the line so no vertical drop lines are drawn.
    if (!Array.isArray(events) || !events.length) return [];
    const sorted = events
      .map(e => ({ ts: new Date(e.ts).getTime(), final: !!e.final }))
      .sort((a, b) => a.ts - b.ts);

    const prior = [...sorted].filter(e => e.ts <= window.start).pop();
    let lastState = prior ? (prior.final ? 1 : 0) : 0;

    const within = sorted.filter(e => e.ts >= window.start && e.ts <= window.end);
    const pts = [];
    pts.push({ x: window.start, y: lastState ? level : null });
    for (const ev of within) {
      const newState = ev.final ? 1 : 0;
      if (newState !== lastState) {
        if (newState === 1) {
          // OFF → ON: close null segment, open ON segment
          pts.push({ x: ev.ts - 1, y: null });
          pts.push({ x: ev.ts,     y: level });
        } else {
          // ON → OFF: close ON segment, open null segment
          pts.push({ x: ev.ts,     y: level });
          pts.push({ x: ev.ts + 1, y: null });
        }
        lastState = newState;
      }
    }
    pts.push({ x: window.end, y: lastState ? level : null });
    return pts;
  }

  function buildSettingsHistorySeries(history, keys, window) {
    // Convert settings history events into step series data points
    // keys is array of key strings to match; returns { key: points[] } dict
    const result = {};
    const grouped = {};
    
    // Group by key and convert unix ts to ms
    for (const ev of history) {
      if (!keys.includes(ev.key)) continue;
      if (!grouped[ev.key]) grouped[ev.key] = [];
      grouped[ev.key].push({ ts: ev.ts * 1000, value: ev.value });
    }
    
    // Build step series for each key
    for (const key in grouped) {
      const sorted = grouped[key].sort((a, b) => a.ts - b.ts);
      const pts = [];
      
      // Find prior value before window
      const prior = sorted.filter(e => e.ts <= window.start).pop();
      let lastVal = prior ? prior.value : null;
      
      // Add baseline at window.start
      if (lastVal !== null) {
        pts.push({ x: window.start, y: parseFloat(lastVal) });
      }

      // Add changes within window
      const within = sorted.filter(e => e.ts >= window.start && e.ts <= window.end);
      for (const ev of within) {
        // If we had no baseline yet, start at window.start with first value
        if (lastVal === null) {
          lastVal = ev.value;
          pts.push({ x: window.start, y: parseFloat(lastVal) });
        }
        lastVal = ev.value;
        pts.push({ x: ev.ts, y: parseFloat(lastVal) });
      }

      // Close out to window.end if we have a value
      if (lastVal !== null) {
        pts.push({ x: window.end, y: parseFloat(lastVal) });
      }
      
      result[key] = pts;
    }
    
    return result;
  }

  function buildMovingAverageSeries(points, windowMs) {
    if (!Array.isArray(points) || !points.length) return [];
    const ms = Math.max(60 * 1000, Number(windowMs) || (60 * 1000));
    const sorted = [...points]
      .map(p => ({ x: Number(p.x), y: Number(p.y) }))
      .filter(p => Number.isFinite(p.x) && Number.isFinite(p.y))
      .sort((a, b) => a.x - b.x);

    if (!sorted.length) return [];

    const out = [];
    let sum = 0;
    let startIdx = 0;

    for (let i = 0; i < sorted.length; i++) {
      const p = sorted[i];
      sum += p.y;

      while (startIdx <= i && (p.x - sorted[startIdx].x) > ms) {
        sum -= sorted[startIdx].y;
        startIdx += 1;
      }

      const count = i - startIdx + 1;
      out.push({ x: p.x, y: sum / Math.max(1, count) });
    }
    return out;
  }

  function computeAdaptiveAxisRange(values, bandLow, bandHigh, windowHours, options) {
    const finiteValues = (values || []).filter(Number.isFinite);
    const hasBand = Number.isFinite(bandLow) && Number.isFinite(bandHigh) && bandHigh > bandLow;
    const floor = finiteValues.length ? Math.min(...finiteValues) : (hasBand ? bandLow : 0);
    const ceil = finiteValues.length ? Math.max(...finiteValues) : (hasBand ? bandHigh : 1);
    const baseMin = hasBand ? Math.min(floor, bandLow) : floor;
    const baseMax = hasBand ? Math.max(ceil, bandHigh) : ceil;
    const dataSpan = Math.max(baseMax - baseMin, 0);

    let minSpan;
    let minPad;
    if (windowHours <= 1.5) {
      minSpan = options.hourSpan;
      minPad = options.hourPad;
    } else if (windowHours <= 24) {
      minSpan = options.daySpan;
      minPad = options.dayPad;
    } else if (windowHours <= 168) {
      minSpan = options.weekSpan;
      minPad = options.weekPad;
    } else {
      minSpan = options.monthSpan;
      minPad = options.monthPad;
    }

    const bandSpan = hasBand ? (bandHigh - bandLow) : 0;
    const desiredSpanForBand = bandSpan > 0 ? (bandSpan / (options.bandRatio || 0.5)) : 0;
    const padding = Math.max(dataSpan * 0.10, minPad);
    let span = Math.max((baseMax - baseMin) + (padding * 2), minSpan, desiredSpanForBand);
    let mid = (baseMin + baseMax) / 2;

    if (hasBand) {
      const bandMid = (bandLow + bandHigh) / 2;
      mid = (mid + bandMid) / 2;
    }

    let min = mid - (span / 2);
    let max = mid + (span / 2);

    if (options.zeroFloor && min < 0) {
      max += Math.abs(min);
      min = 0;
    }

    return { min, max };
  }

  function init() {
    if (typeof RDWCChart === 'undefined') return;

    const chart = new RDWCChart({
      canvasId: 'overviewCombinedChart',
      emptyMessageId: 'overview-combined-empty',
      type: 'overview-combined',
      title: 'Overview Combined',
      livePointAppend: false,
      layout: { padding: { right: 24 } },
      onDataFetch: async (startISO, endISO) => {
        const spanMs = new Date(endISO) - new Date(startISO);
        const hours = spanMs / 3600000;
        let gran, max;
        if (hours <= 1) { gran = 10; max = 600; }
        else if (hours <= 6) { gran = 20; max = 1200; }
        else if (hours <= 24) { gran = 60; max = 1500; }
        else if (hours <= 168) { gran = 300; max = 2100; }
        else { gran = 900; max = 3000; }

        const q = new URLSearchParams();
        q.set('from', startISO);
        q.set('to', endISO);
        q.set('gran', String(gran));
        q.set('max', String(max));

        const trendsUrl = '/api/trends?' + q.toString();
        const phDoseLimit = hours <= 24 ? 2000 : (hours <= 168 ? 5000 : 20000);
        const phDoseUrl = `/api/ph/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=${phDoseLimit}`;
        const ecDoseUrl = `/api/dose/recent?hours=${Math.max(1, Math.ceil(hours))}`;
        const settingsHistoryUrl = `/api/settings/history?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`;
        // Range-aware event limits: 500 events per day of coverage, capped reasonably
        const relayEventLimit = Math.min(10000, Math.max(500, Math.ceil(hours / 24 * 500)));

        try {
          const [trendsRes, phDoseRes, ecDoseRes, settingsRes, ecStatusRes, tempStatusRes, phStatusRes, lightsRes, mainRes, chillerRes, historyRes] = await Promise.all([
            fetch(trendsUrl, { cache: 'no-store' }),
            fetch(phDoseUrl, { cache: 'no-store' }),
            fetch(ecDoseUrl, { cache: 'no-store' }),
            fetch('/api/settings', { cache: 'no-store' }),
            fetch('/api/ec/status', { cache: 'no-store' }),
            fetch('/api/temperature/status', { cache: 'no-store' }),
            fetch('/api/ph/status', { cache: 'no-store' }),
            fetch(`/api/relays/events?name=lights&last=${relayEventLimit}`, { cache: 'no-store' }),
            fetch(`/api/relays/events?name=main_pump&last=${relayEventLimit}`, { cache: 'no-store' }),
            fetch(`/api/relays/events?name=chiller_pump&last=${relayEventLimit}`, { cache: 'no-store' }),
            fetch(settingsHistoryUrl, { cache: 'no-store' })
          ]);

          const trendsData = trendsRes.ok ? await trendsRes.json() : { series: { ph: [], ec: [], temp: [] } };
          const phDose = phDoseRes.ok ? await phDoseRes.json() : [];
          const ecDose = ecDoseRes.ok ? await ecDoseRes.json() : { events: [] };
          const settings = settingsRes.ok ? await settingsRes.json() : {};
          const ecStatus = ecStatusRes.ok ? await ecStatusRes.json() : {};
          const tempStatus = tempStatusRes.ok ? await tempStatusRes.json() : {};
          const phStatus = phStatusRes.ok ? await phStatusRes.json() : {};
          console.log('[Overview Combined] Raw settings fetch:', settings);
          const lightsEvents = lightsRes.ok ? await lightsRes.json() : [];
          const mainEvents = mainRes.ok ? await mainRes.json() : [];
          const chillerEvents = chillerRes.ok ? await chillerRes.json() : [];
          const settingsHistory = historyRes.ok ? await historyRes.json() : [];

          return { trendsData, phDose, ecDose, settings, ecStatus, tempStatus, phStatus, lightsEvents, mainEvents, chillerEvents, settingsHistory };
        } catch (e) {
          console.error('[Overview Combined] Fetch failed', e);
          return { trendsData: { series: { ph: [], ec: [], temp: [] } }, phDose: [], ecDose: { events: [] }, settings: {}, ecStatus: {}, tempStatus: {}, phStatus: {}, lightsEvents: [], mainEvents: [], chillerEvents: [], settingsHistory: [] };
        }
      },
      onRender: (chartInstance, data, window) => {
        const ph = (data?.trendsData?.series?.ph || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
        const ec = (data?.trendsData?.series?.ec || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
        const temp = (data?.trendsData?.series?.temp || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));

        // Restore temperature smoothing for readability across noisy probes.
        const windowHoursForAvg = Math.max(1 / 60, (window.end - window.start) / 3600000);
        let tempAvgWindowMs;
        if (windowHoursForAvg <= 1) tempAvgWindowMs = 20 * 60 * 1000;
        else if (windowHoursForAvg <= 6) tempAvgWindowMs = 45 * 60 * 1000;
        else if (windowHoursForAvg <= 24) tempAvgWindowMs = 180 * 60 * 1000;
        else if (windowHoursForAvg <= 168) tempAvgWindowMs = 720 * 60 * 1000;
        else tempAvgWindowMs = 1440 * 60 * 1000;
        // Two-pass moving average for stronger low-pass smoothing.
        const tempSmoothed1 = buildMovingAverageSeries(temp, tempAvgWindowMs);
        const tempSmoothed = buildMovingAverageSeries(tempSmoothed1, tempAvgWindowMs);

        const phDoseEvents = (data?.phDose || [])
          .map(e => ({ ts: new Date(e.ts).getTime(), volume_ml: e.volume_ml }))
          .filter(e => e.ts >= window.start && e.ts <= window.end);

        const ecDoseEvents = (data?.ecDose?.events || [])
          .filter(e => !e.blocked_by)
          .map(e => ({ ts: e.ts * 1000, pump: e.pump, ml: e.ml || 0 }))
          .filter(e => e.ts >= window.start && e.ts <= window.end);

        const targets = data?.settings?.targets || {};
        const ecStatusTargets = data?.ecStatus?.targets || {};
        const tempSettings = data?.settings?.temperature || {};
        const phStatusTargets = data?.phStatus?.targets || {};
        const tempStatus = data?.tempStatus || {};
        console.log('[Overview Combined] Targets from settings:', targets);
        console.log('[Overview Combined] pH controller targets:', phStatusTargets);
        
        // ALWAYS use pH controller's computed targets (scheduler-derived)
        const phLowCurrent = parseFloat(phStatusTargets.low);
        const phHighCurrent = parseFloat(phStatusTargets.high);
        
        // pH band is horizontal at controller's current values
        let phLowData, phHighData;
        if (Number.isFinite(phLowCurrent) && Number.isFinite(phHighCurrent)) {
          phLowData = [ { x: window.start, y: phLowCurrent }, { x: window.end, y: phLowCurrent } ];
          phHighData = [ { x: window.start, y: phHighCurrent }, { x: window.end, y: phHighCurrent } ];
          console.log('[Overview Combined] pH band data created:', { phLowData, phHighData });
        } else {
          phLowData = [];
          phHighData = [];
          console.warn('[Overview Combined] pH targets not finite, skipping band');
        }
        
        // Prefer live EC targets from controller status (scheduler-derived), fallback to settings
        const ecLowLive = parseFloat(ecStatusTargets.low);
        const ecHighLive = parseFloat(ecStatusTargets.high);
        const ecLowSettings = parseFloat(targets['ec_low']);
        const ecHighSettings = parseFloat(targets['ec_high']);
        const ecLow = Number.isFinite(ecLowLive) ? ecLowLive : ecLowSettings;
        const ecHigh = Number.isFinite(ecHighLive) ? ecHighLive : ecHighSettings;
        const hasEcBand = Number.isFinite(ecLow) && Number.isFinite(ecHigh);
        console.log('[Overview Combined] EC band:', { ecLow, ecHigh, hasEcBand });
        console.log('[Overview Combined] pH band:', { phLowCurrent, phHighCurrent });

        // Get temperature target band (controller-first, schedule-derived)
        // Prefer live controller-computed band from /api/temperature/status (low/high)
        let tempLow = parseFloat(tempStatus.low);
        let tempHigh = parseFloat(tempStatus.high);
        if (!Number.isFinite(tempLow) || !Number.isFinite(tempHigh)) {
          // Fallback: compute band from settings if controller values unavailable
          const tempTarget = parseFloat((data?.tempStatus?.target_temp) ?? (targets['temp_target_c']));
          const tempHyst = parseFloat(tempSettings['hysteresis']);
          const resolvedTarget = Number.isFinite(tempTarget) ? tempTarget : 19.0;
          const resolvedHyst = Number.isFinite(tempHyst) ? tempHyst : 0.6;
          tempLow = resolvedTarget - resolvedHyst;
          tempHigh = resolvedTarget + resolvedHyst;
        }
        console.log('[Overview Combined] Temp band:', { tempLow, tempHigh, tempStatus });

        const datasets = [];

        // pH band - from historical settings changes or current controller values
        if (phLowData && phHighData && phLowData.length > 0 && phHighData.length > 0) {
          datasets.push({
            type: 'line',
            yAxisID: 'yPh',
            label: 'pH Target',
            data: phLowData,
            borderColor: 'rgba(59, 130, 246, 0.25)',
            borderWidth: 1,
            borderDash: [5, 5],
            stepped: true,
            pointRadius: 0,
            fill: '+1',
            backgroundColor: window.CHART_COLORS?.setpointBand || 'rgba(59, 130, 246, 0.1)',
            order: 0
          });
          datasets.push({
            type: 'line',
            yAxisID: 'yPh',
            label: '',
            data: phHighData,
            borderColor: 'rgba(59, 130, 246, 0.25)',
            borderWidth: 1,
            borderDash: [5, 5],
            stepped: true,
            pointRadius: 0,
            order: 0
          });
        }

        // EC band - static from current settings
        if (hasEcBand) {
          const ecLowData = [ { x: window.start, y: ecLow }, { x: window.end, y: ecLow } ];
          const ecHighData = [ { x: window.start, y: ecHigh }, { x: window.end, y: ecHigh } ];
          datasets.push({
            type: 'line',
            yAxisID: 'yEc',
            label: 'EC Target',
            data: ecLowData,
            borderColor: 'rgba(16, 185, 129, 0.25)',
            borderWidth: 1,
            borderDash: [5, 5],
            stepped: true,
            pointRadius: 0,
            fill: '+1',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            order: 0
          });
          datasets.push({
            type: 'line',
            yAxisID: 'yEc',
            label: '',
            data: ecHighData,
            borderColor: 'rgba(16, 185, 129, 0.25)',
            borderWidth: 1,
            borderDash: [5, 5],
            stepped: true,
            pointRadius: 0,
            order: 0
          });
        }

        // Temperature band - from controller (or computed fallback)
        if (Number.isFinite(tempLow) && Number.isFinite(tempHigh)) {
          const tempLowData = [{ x: window.start, y: tempLow }, { x: window.end, y: tempLow }];
          const tempHighData = [{ x: window.start, y: tempHigh }, { x: window.end, y: tempHigh }];
          datasets.push({
            type: 'line',
            yAxisID: 'yTemp',
            label: 'Temp Target',
            data: tempLowData,
            borderColor: 'rgba(239, 68, 68, 0.25)',
            borderWidth: 1,
            borderDash: [5, 5],
            stepped: true,
            pointRadius: 0,
            fill: '+1',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            order: 0
          });
          datasets.push({
            type: 'line',
            yAxisID: 'yTemp',
            label: '',
            data: tempHighData,
            borderColor: 'rgba(239, 68, 68, 0.25)',
            borderWidth: 1,
            borderDash: [5, 5],
            stepped: true,
            pointRadius: 0,
            order: 0
          });
        }

        // pH series
        if (ph.length) {
          datasets.push({
            id: 'ph',
            yAxisID: 'yPh',
            label: 'pH',
            data: ph,
            borderWidth: 1.5,
            borderColor: 'rgba(59,130,246,0.75)',
            backgroundColor: 'rgba(59,130,246,0.75)',
            pointRadius: 0,
            spanGaps: true,
            order: 2
          });
        }

        // EC series
        if (ec.length) {
          datasets.push({
            id: 'ec',
            yAxisID: 'yEc',
            label: 'EC',
            data: ec,
            borderWidth: 2.2,
            borderColor: 'rgba(16,185,129,0.95)',
            backgroundColor: 'rgba(16,185,129,0.95)',
            pointRadius: 0,
            spanGaps: true,
            order: 1
          });
        }

        // Temp series
        if (temp.length) {
          datasets.push({
            id: 'temp-raw',
            yAxisID: 'yTemp',
            label: 'Temp Raw',
            data: temp,
            borderWidth: 1,
            borderColor: 'rgba(239,68,68,0.20)',
            backgroundColor: 'rgba(239,68,68,0.20)',
            pointRadius: 0,
            spanGaps: true,
            order: 1
          });
          datasets.push({
            id: 'temp',
            yAxisID: 'yTemp',
            label: 'Temperature',
            data: tempSmoothed.length ? tempSmoothed : temp,
            borderWidth: 2,
            borderColor: 'rgba(239,68,68,0.95)',
            backgroundColor: 'rgba(239,68,68,0.95)',
            pointRadius: 0,
            spanGaps: true,
            order: 1
          });
        }

        // Relay state — Lights only on primary axis; circulation hidden from overview for clarity.
        const lightsScaled = buildStepSeries(data?.lightsEvents, window, 0.86);

        if (lightsScaled.length) {
          datasets.push({
            label: 'Lights',
            yAxisID: 'yState',
            data: lightsScaled,
            borderColor: 'rgba(34,197,94,0.55)',
            backgroundColor: 'rgba(34,197,94,0.10)',
            stepped: false,
            spanGaps: false,
            borderWidth: 2,
            fill: false,
            pointRadius: 0,
            order: 2
          });
        }

        // Axes
        if (!chartInstance.options.scales.yPh) {
          chartInstance.options.scales.yPh = { 
            type: 'linear', 
            position: 'left', 
            title: { display: true, text: 'pH', color: '#bfdbfe' },
            ticks: { color: '#9ca3af' },
            grid: { drawOnChartArea: true } 
          };
        }
        if (!chartInstance.options.scales.yEc) {
          chartInstance.options.scales.yEc = { 
            type: 'linear', 
            position: 'right', 
            title: { display: true, text: 'EC (mS/cm)', color: '#86efac' },
            ticks: { color: '#9ca3af' },
            grid: { drawOnChartArea: false } 
          };
        }
        if (!chartInstance.options.scales.yTemp) {
          chartInstance.options.scales.yTemp = { 
            type: 'linear', 
            position: 'right', 
            title: { display: true, text: 'Temp (°C)', color: '#f87171' },
            ticks: { color: '#9ca3af' },
            grid: { drawOnChartArea: false } 
          };
        }
        if (!chartInstance.options.scales.yState) {
          chartInstance.options.scales.yState = {
            type: 'linear',
            position: 'right',
            display: true,
            min: 0,
            max: 1.0,
            grid: { drawOnChartArea: false },
            title: { display: false },
            ticks: {
              display: true,
              color: '#6b7280',
              callback: (v) => {
                const pct = Math.round(v * 100);
                if (pct === 86) return 'Lights';
                if (pct === 0)  return 'OFF';
                return '';
              }
            }
          };
        }

        const phVals = ph.map(p => p.y).filter(Number.isFinite);
        const ecVals = ec.map(p => p.y).filter(Number.isFinite);
        const tempVals = temp.map(p => p.y).filter(Number.isFinite);

        const windowHours = Math.max(1 / 60, (window.end - window.start) / 3600000);

        const phBandLow = Number.isFinite(phLowCurrent) ? phLowCurrent : undefined;
        const phBandHigh = Number.isFinite(phHighCurrent) ? phHighCurrent : undefined;
        const phRange = computeAdaptiveAxisRange(phVals, phBandLow, phBandHigh, windowHours, {
          hourSpan: 0.06,
          hourPad: 0.015,
          daySpan: 0.10,
          dayPad: 0.02,
          weekSpan: 0.16,
          weekPad: 0.03,
          monthSpan: 0.22,
          monthPad: 0.04,
          bandRatio: 0.50,
          zeroFloor: false
        });

        const ecBandLow = Number.isFinite(ecLow) ? ecLow : undefined;
        const ecBandHigh = Number.isFinite(ecHigh) ? ecHigh : undefined;
        const ecRange = computeAdaptiveAxisRange(ecVals, ecBandLow, ecBandHigh, windowHours, {
          hourSpan: 0.10,
          hourPad: 0.02,
          daySpan: 0.16,
          dayPad: 0.03,
          weekSpan: 0.28,
          weekPad: 0.04,
          monthSpan: 0.40,
          monthPad: 0.06,
          bandRatio: 0.50,
          zeroFloor: true
        });

        const tempRange = computeAdaptiveAxisRange(tempVals, tempLow, tempHigh, windowHours, {
          hourSpan: 0.25,
          hourPad: 0.05,
          daySpan: 0.45,
          dayPad: 0.08,
          weekSpan: 0.90,
          weekPad: 0.14,
          monthSpan: 1.40,
          monthPad: 0.22,
          bandRatio: 0.50,
          zeroFloor: true
        });

        const phMin = phRange.min;
        const phMax = phRange.max;
        const ecMin = ecRange.min;
        const ecMax = ecRange.max;
        const tempAxisMin = tempRange.min;
        const tempAxisMax = tempRange.max;

        chartInstance.options.scales.yPh.min = phMin;
        chartInstance.options.scales.yPh.max = phMax;
        chartInstance.options.scales.yEc.min = ecMin;
        chartInstance.options.scales.yEc.max = ecMax;
        chartInstance.options.scales.yTemp.min = tempAxisMin;
        chartInstance.options.scales.yTemp.max = tempAxisMax;

        // Dose markers anchored to top 1/8th of each axis so they stay visually stable
        // when timeline/data range changes.
        const phSpan = Math.max(phMax - phMin, 0.001);
        const ecSpan = Math.max(ecMax - ecMin, 0.001);

        // pH lane centered in the top eighth.
        const phDoseY = phMax - (phSpan * 0.0625);
        if (phDoseEvents.length) {
          datasets.push({
            type: 'scatter',
            yAxisID: 'yPh',
            label: `pH Doses (${phDoseEvents.length})`,
            data: phDoseEvents.map(e => ({ x: e.ts, y: phDoseY })),
            pointRadius: 5,
            pointStyle: 'triangle',
            pointBackgroundColor: window.CHART_COLORS?.phUp || '#fbbf24',
            pointBorderColor: window.CHART_COLORS?.phUp || '#fbbf24',
            pointBorderWidth: 1,
            showLine: false,
            order: 2
          });
        }

        // EC lanes staggered inside the top eighth.
        const doseLevels = {
          grow: ecMax - (ecSpan * 0.020),
          micro: ecMax - (ecSpan * 0.060),
          bloom: ecMax - (ecSpan * 0.100)
        };
        const pumps = ['grow', 'micro', 'bloom'];
        pumps.forEach(pump => {
          const evs = ecDoseEvents.filter(e => e.pump === pump);
          if (!evs.length) return;
          datasets.push({
            type: 'scatter',
            yAxisID: 'yEc',
            label: `${pump} (${evs.length})`,
            data: evs.map(e => ({ x: e.ts, y: doseLevels[pump] })),
            pointRadius: 5,
            pointStyle: 'circle',
            pointBackgroundColor: window.CHART_COLORS?.[pump] || '#6ee7b7',
            pointBorderColor: window.CHART_COLORS?.[pump] || '#6ee7b7',
            pointBorderWidth: 1,
            showLine: false,
            order: 2
          });
        });

        return datasets;
      }
    });

    // Override default window to 1 hour live view while keeping controls consistent
    const now = Date.now();
    chart.timeWindow = { start: now - 60 * 60 * 1000, end: now };
    chart.selectedRange = 'custom';
    chart.isLiveMode = false;
    formatRangeLabel(chart.timeWindow.start, chart.timeWindow.end);
    chart.refresh(true);

    // Wire controls using shared ChartControls
    if (typeof ChartControls !== 'undefined' && document.getElementById('overview-combined-controls')) {
      const controls = new ChartControls({
        containerId: 'overview-combined-controls',
        onRangeChange: async (start, end, isLive) => {
          chart.timeWindow = { start, end };
          chart.isLiveMode = !!isLive;
          chart.selectedRange = isLive ? 'live' : 'custom';
          formatRangeLabel(start, end);
          await chart.refresh(true);
        },
        getDataExtent: () => {
          const growStart = window.rdwcSettings?.get('general.grow_start_date');
          const first = growStart ? new Date(growStart + 'T00:00:00').getTime() : null;
          const last = Date.now();
          return { first, last };
        },
        getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date')
      });
      // Seed controls to 1-hour live view
      controls.applyRange(chart.timeWindow.start, chart.timeWindow.end, false, true);
    }

    window.overviewCombinedChart = chart;
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', () => setTimeout(init, 200));
})();
