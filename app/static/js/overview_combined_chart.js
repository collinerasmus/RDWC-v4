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
    if (!Array.isArray(events) || !events.length) return [];
    const sorted = events
      .map(e => ({ ts: new Date(e.ts).getTime(), final: !!e.final }))
      .sort((a, b) => a.ts - b.ts);

    // Find the last known state before the window start to preserve visibility on small ranges
    const prior = [...sorted].filter(e => e.ts <= window.start).pop();
    let lastState = prior ? (prior.final ? 1 : 0) : 0;

    const within = sorted.filter(e => e.ts >= window.start && e.ts <= window.end);
    const pts = [];
    pts.push({ x: window.start, y: lastState ? level : 0 });
    for (const ev of within) {
      lastState = ev.final ? 1 : 0;
      pts.push({ x: ev.ts, y: lastState ? level : 0 });
    }
    pts.push({ x: window.end, y: lastState ? level : 0 });
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

  function init() {
    if (typeof RDWCChart === 'undefined') return;

    const chart = new RDWCChart({
      canvasId: 'overviewCombinedChart',
      emptyMessageId: 'overview-combined-empty',
      type: 'overview-combined',
      title: 'Overview Combined',
      layout: { padding: { right: 24 } },
      onDataFetch: async (startISO, endISO) => {
        const spanMs = new Date(endISO) - new Date(startISO);
        const hours = spanMs / 3600000;
        let gran, max;
        if (hours <= 1) { gran = 30; max = 300; }
        else if (hours <= 6) { gran = 45; max = 800; }
        else if (hours <= 24) { gran = 60; max = 1500; }
        else if (hours <= 168) { gran = 300; max = 2100; }
        else { gran = 900; max = 3000; }

        const q = new URLSearchParams();
        q.set('from', startISO);
        q.set('to', endISO);
        q.set('gran', String(gran));
        q.set('max', String(max));

        const trendsUrl = '/api/trends?' + q.toString();
        const phDoseUrl = `/api/ph/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=500`;
        const ecDoseUrl = `/api/dose/recent?hours=${Math.max(1, Math.ceil(hours))}`;
        const settingsHistoryUrl = `/api/settings/history?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`;

        try {
          const [trendsRes, phDoseRes, ecDoseRes, settingsRes, ecStatusRes, tempStatusRes, phStatusRes, lightsRes, mainRes, chillerRes, historyRes] = await Promise.all([
            fetch(trendsUrl, { cache: 'no-store' }),
            fetch(phDoseUrl, { cache: 'no-store' }),
            fetch(ecDoseUrl, { cache: 'no-store' }),
            fetch('/api/settings', { cache: 'no-store' }),
            fetch('/api/ec/status', { cache: 'no-store' }),
            fetch('/api/temperature/status', { cache: 'no-store' }),
            fetch('/api/ph/status', { cache: 'no-store' }),
            fetch('/api/relays/events?name=lights&last=500', { cache: 'no-store' }),
            fetch('/api/relays/events?name=main_pump&last=500', { cache: 'no-store' }),
            fetch('/api/relays/events?name=chiller_pump&last=500', { cache: 'no-store' }),
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
        
        // Get current pH targets from controller (scheduler-derived)
        const phLowLive = parseFloat(phStatusTargets.low);
        const phHighLive = parseFloat(phStatusTargets.high);
        const phLowSettings = parseFloat(targets['ph_low']);
        const phHighSettings = parseFloat(targets['ph_high']);
        const phLowCurrent = Number.isFinite(phLowLive) ? phLowLive : phLowSettings;
        const phHighCurrent = Number.isFinite(phHighLive) ? phHighLive : phHighSettings;
        
        // Build pH target history from settings changes
        const phTargetHistory = buildSteppedSeriesFromHistory(data?.settingsHistory || [], ['targets.ph_low', 'targets.ph_high'], window);
        const phLowHistory = phTargetHistory['targets.ph_low'] || [];
        const phHighHistory = phTargetHistory['targets.ph_high'] || [];
        
        // Use historical data if available, otherwise use current values
        let phLowData, phHighData;
        if (phLowHistory.length > 0 && phHighHistory.length > 0) {
          phLowData = phLowHistory;
          phHighData = phHighHistory;
        } else {
          // Fallback to current values as horizontal lines
          phLowData = [ { x: window.start, y: phLowCurrent }, { x: window.end, y: phLowCurrent } ];
          phHighData = [ { x: window.start, y: phHighCurrent }, { x: window.end, y: phHighCurrent } ];
        }
        
        // Prefer live EC targets from controller status (scheduler-derived), fallback to settings
        const ecLowLive = parseFloat(ecStatusTargets.low);
        const ecHighLive = parseFloat(ecStatusTargets.high);
        const ecLowSettings = parseFloat(targets['ec_low']);
        const ecHighSettings = parseFloat(targets['ec_high']);
        const ecLow = Number.isFinite(ecLowLive) ? ecLowLive : ecLowSettings;
        const ecHigh = Number.isFinite(ecHighLive) ? ecHighLive : ecHighSettings;
        const hasEcBand = Number.isFinite(ecLow) && Number.isFinite(ecHigh);
        console.log('[Overview Combined] Parsed values:', { phLow, phHigh, ecLow, ecHigh, ecLowLive, ecHighLive, ecLowSettings, ecHighSettings });
        console.log('[Overview Combined] hasEcBand?', hasEcBand, 'isFinite checks:', { ecLowFinite: Number.isFinite(ecLow), ecHighFinite: Number.isFinite(ecHigh) });

        // Get temperature target + hysteresis (live)
        // Prefer controller-computed band from temperature status
        const tempLowLive = parseFloat(tempStatus.low);
        const tempHighLive = parseFloat(tempStatus.high);
        const tempTarget = parseFloat(targets['temp_target_c']);
        const tempHyst = parseFloat(tempSettings['hysteresis']);
        const resolvedTarget = Number.isFinite(tempTarget) ? tempTarget : 19.0;
        const resolvedHyst = Number.isFinite(tempHyst) ? tempHyst : 0.6;
        const tempLowFallback = resolvedTarget - resolvedHyst;
        const tempHighFallback = resolvedTarget + resolvedHyst;
        const tempLow = Number.isFinite(tempLowLive) ? tempLowLive : tempLowFallback;
        const tempHigh = Number.isFinite(tempHighLive) ? tempHighLive : tempHighFallback;
        console.log('[Overview Combined] Temp targets:', { tempLow, tempHigh, resolvedTarget, resolvedHyst });

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

        // Temperature band - live only
        if (Number.isFinite(resolvedTarget) && Number.isFinite(resolvedHyst)) {
          const tempLowLive = resolvedTarget - resolvedHyst;
          const tempHighLive = resolvedTarget + resolvedHyst;
          const tempLowData = [{ x: window.start, y: tempLowLive }, { x: window.end, y: tempLowLive }];
          const tempHighData = [{ x: window.start, y: tempHighLive }, { x: window.end, y: tempHighLive }];
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
            borderWidth: 2,
            borderColor: window.CHART_COLORS?.ph || '#3b82f6',
            backgroundColor: window.CHART_COLORS?.ph || '#3b82f6',
            pointRadius: 0,
            spanGaps: true,
            order: 1
          });
        }

        // EC series
        if (ec.length) {
          datasets.push({
            id: 'ec',
            yAxisID: 'yEc',
            label: 'EC',
            data: ec,
            borderWidth: 2,
            borderColor: window.CHART_COLORS?.ec || '#10b981',
            backgroundColor: window.CHART_COLORS?.ec || '#10b981',
            pointRadius: 0,
            spanGaps: true,
            order: 1
          });
        }

        // Temp series
        if (temp.length) {
          datasets.push({
            id: 'temp',
            yAxisID: 'yTemp',
            label: 'Temp (°C)',
            data: temp,
            borderWidth: 2,
            borderColor: window.CHART_COLORS?.temp || '#ef4444',
            backgroundColor: window.CHART_COLORS?.temp || '#ef4444',
            pointRadius: 0,
            spanGaps: true,
            order: 1
          });
        }

        // pH dose markers
        if (phDoseEvents.length) {
          const phDoseY = Number.isFinite(phHigh) ? phHigh + 0.3 : 6.6;
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

        // EC dose markers
        const ecDoseBase = hasEcBand ? ecHigh : (ec.length ? Math.max(...ec.map(p => p.y)) : 1.0);
        const doseLevels = {
          grow: ecDoseBase + 0.3,
          micro: ecDoseBase + 0.2,
          bloom: ecDoseBase + 0.1
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

        // Relay overlays (lights and pumps) - thin bands near top of EC axis
        const lightsScaled = buildStepSeries(data?.lightsEvents, window, 3.2).map(p => ({ x: p.x, y: p.y === 0 ? 3.05 : p.y }));
        const mainScaled = buildStepSeries(data?.mainEvents, window, 3.1).map(p => ({ x: p.x, y: p.y === 0 ? 2.95 : p.y }));
        const chillerScaled = buildStepSeries(data?.chillerEvents, window, 3.0).map(p => ({ x: p.x, y: p.y === 0 ? 2.85 : p.y }));

        if (lightsScaled.length) {
          datasets.push({
            label: 'Lights',
            yAxisID: 'yEc',
            data: lightsScaled,
            borderColor: '#22c55e',
            backgroundColor: 'rgba(34,197,94,0.12)',
            stepped: true,
            borderWidth: 2,
            fill: false,
            pointRadius: 0,
            order: 2
          });
        }
        if (mainScaled.length) {
          datasets.push({
            label: 'Main Pump',
            yAxisID: 'yEc',
            data: mainScaled,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,0.12)',
            stepped: true,
            borderWidth: 2,
            fill: false,
            pointRadius: 0,
            order: 2
          });
        }
        if (chillerScaled.length) {
          datasets.push({
            label: 'Chiller Pump',
            yAxisID: 'yEc',
            data: chillerScaled,
            borderColor: '#06b6d4',
            backgroundColor: 'rgba(6,182,212,0.12)',
            stepped: true,
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
          chartInstance.options.scales.yState = { type: 'linear', position: 'right', display: false, min: 0, max: 4.0, grid: { display: false } };
        }

        const phMin = Number.isFinite(phLow) ? Math.min(phLow - 0.5, 5.0) : 5.0;
        const phMax = Number.isFinite(phHigh) ? Math.max(phHigh + 0.8, 7.5) : 7.5;
        const ecMin = 0.0;
        const ecMax = 4.0;
        // Scale temp axis: anchor band near bottom with slight headroom
        const tempAxisMin = Math.floor(tempLow - 1);
        const tempAxisMax = Math.ceil(tempHigh + 6);

        chartInstance.options.scales.yPh.min = phMin;
        chartInstance.options.scales.yPh.max = phMax;
        chartInstance.options.scales.yEc.min = ecMin;
        chartInstance.options.scales.yEc.max = ecMax;
        chartInstance.options.scales.yTemp.min = tempAxisMin;
        chartInstance.options.scales.yTemp.max = tempAxisMax;

        return datasets;
      }
    });

    // Override default window to 1 hour live view while keeping controls consistent
    const now = Date.now();
    chart.timeWindow = { start: now - 60 * 60 * 1000, end: now };
    chart.selectedRange = 'custom';
    chart.isLiveMode = true;
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
          const phSeries = chart.cachedData?.trendsData?.series?.ph || [];
          const first = phSeries.length ? phSeries[0].ts * 1000 : null;
          const last = phSeries.length ? phSeries[phSeries.length - 1].ts * 1000 : null;
          return { first, last };
        },
        getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date')
      });
      // Seed controls to 1-hour live view
      controls.applyRange(chart.timeWindow.start, chart.timeWindow.end, true);
    }

    window.overviewCombinedChart = chart;
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', () => setTimeout(init, 200));
})();
