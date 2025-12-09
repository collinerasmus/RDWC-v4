/**
 * Temperature/Chiller Chart
 * Shows temperature history with setpoint band, chiller on/off events, and total runtime
 * NEW - for chiller tab
 */
(function() {
  'use strict';

  console.log('[Chiller Chart] Initializing');

  let totalChillerTime = 0; // Total chiller ON time in minutes

  function init() {
    if (typeof RDWCChart === 'undefined') {
      console.error('[Chiller Chart] RDWCChart base not loaded');
      return;
    }

    const chart = new RDWCChart({
      canvasId: 'chillerChart',
      emptyMessageId: 'chiller-chart-empty',
      type: 'chiller',
      title: 'Temperature & Chiller Activity',
      
      onDataFetch: async (startISO, endISO) => {
        const span = new Date(endISO) - new Date(startISO);
        const hours = span / (3600 * 1000);
        let gran, max;

        if (hours <= 1) { gran = 30; max = 150; }
        else if (hours <= 24) { gran = 60; max = 1500; }
        else if (hours <= 168) { gran = 300; max = 2100; }
        else if (hours <= 720) { gran = 900; max = 3000; }
        else { gran = 3600; max = 3000; }

        const q = new URLSearchParams();
        q.set('from', startISO);
        q.set('to', endISO);
        q.set('gran', String(gran));
        q.set('max', String(max));

        const trendsUrl = '/api/trends?' + q.toString();
        
        // Fetch chiller events
        const chillerHours = Math.min(Math.ceil(hours), 168);
        const chillerUrl = `/api/chiller/events?hours=${chillerHours}`;

        // Fetch temperature target
        const settingsUrl = '/api/settings';

        try {
          const [trendsRes, chillerRes, settingsRes] = await Promise.all([
            fetch(trendsUrl, { cache: 'no-store' }),
            fetch(chillerUrl, { cache: 'no-store' }).catch(() => null),
            fetch(settingsUrl, { cache: 'no-store' })
          ]);

          const trendsData = trendsRes.ok ? await trendsRes.json() : { series: { temp: [] } };
          const chillerData = chillerRes && chillerRes.ok ? await chillerRes.json() : { events: [] };
          const settingsData = settingsRes.ok ? await settingsRes.json() : {};

          console.log('[Chiller Chart] Fetched:', {
            temp: trendsData?.series?.temp?.length || 0,
            chillerEvents: chillerData?.events?.length || 0
          });

          return { trendsData, chillerData, settingsData };
        } catch (e) {
          console.error('[Chiller Chart] Fetch failed:', e);
          return { trendsData: { series: { temp: [] } }, chillerData: { events: [] }, settingsData: {} };
        }
      },

      onRender: (chart, data, window) => {
        const { trendsData, chillerData, settingsData } = data;

        // Parse temperature readings
        const temp = (trendsData?.series?.temp || []).map(p => ({
          x: p.ts * 1000,
          y: Number(p.value)
        }));

        // Parse chiller events
        const chillerEvents = (chillerData?.events || [])
          .filter(e => {
            const ts = e.ts * 1000;
            return ts >= window.start && ts <= window.end;
          });

        // Calculate total chiller ON time
        totalChillerTime = 0;
        for (let i = 0; i < chillerEvents.length - 1; i++) {
          const current = chillerEvents[i];
          const next = chillerEvents[i + 1];
          if (current.state === 'ON') {
            const onDuration = (next.ts - current.ts) / 60; // minutes
            totalChillerTime += onDuration;
          }
        }

        // Update total runtime display
        const totalEl = document.getElementById('chiller-total-runtime');
        if (totalEl) {
          const hours = Math.floor(totalChillerTime / 60);
          const mins = Math.floor(totalChillerTime % 60);
          totalEl.textContent = `${hours}h ${mins}m`;
        }

        // Get temperature target from settings
        const tempTarget = settingsData?.['targets.temp_target'] ?? 21.0;
        const tempLow = tempTarget - 0.5;
        const tempHigh = tempTarget + 0.5;

        // Get current temp
        const currentTemp = temp.length > 0 ? temp[temp.length - 1].y : null;

        // Build datasets
        const datasets = [];

        // 1. Temperature setpoint band
        if (tempLow && tempHigh) {
          datasets.push({
            type: 'line',
            label: 'Temp Target Band',
            data: [
              { x: window.start, y: tempLow },
              { x: window.end, y: tempLow }
            ],
            borderColor: 'rgba(239, 68, 68, 0.3)',
            borderWidth: 1,
            borderDash: [5, 5],
            fill: '+1',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            pointRadius: 0
          });
          datasets.push({
            type: 'line',
            label: '',
            data: [
              { x: window.start, y: tempHigh },
              { x: window.end, y: tempHigh }
            ],
            borderColor: 'rgba(239, 68, 68, 0.3)',
            borderWidth: 1,
            borderDash: [5, 5],
            pointRadius: 0
          });
        }

        // 2. Temperature history line
        if (temp.length) {
          datasets.push({
            id: 'temp',
            label: 'Temperature',
            data: temp,
            borderWidth: 2,
            borderColor: window.CHART_COLORS?.temp || '#ef4444',
            backgroundColor: window.CHART_COLORS?.temp || '#ef4444',
            pointRadius: 0,
            spanGaps: true,
            order: 1
          });
        }

        // 3. Current temperature marker
        if (currentTemp != null) {
          datasets.push({
            type: 'scatter',
            label: `Current: ${currentTemp.toFixed(1)} °C`,
            data: [{ x: window.end, y: currentTemp }],
            pointRadius: 6,
            pointStyle: 'circle',
            pointBackgroundColor: window.CHART_COLORS?.temp || '#ef4444',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            showLine: false,
            order: 0
          });
        }

        // 4. Chiller ON events as markers
        const chillerOnEvents = chillerEvents.filter(e => e.state === 'ON');
        if (chillerOnEvents.length) {
          const markerY = tempLow - 1.0; // Below target band
          datasets.push({
            type: 'scatter',
            label: `Chiller ON (${chillerOnEvents.length})`,
            data: chillerOnEvents.map(e => ({ x: e.ts * 1000, y: markerY })),
            pointRadius: 5,
            pointStyle: 'rectRot',
            pointBackgroundColor: window.CHART_COLORS?.chillerOn || '#60a5fa',
            pointBorderColor: window.CHART_COLORS?.chillerOn || '#60a5fa',
            pointBorderWidth: 1,
            showLine: false,
            order: 2
          });
        }

        // Set fixed y-axis (temperature range)
        const tempMin = Math.min(tempLow - 2.0, 16.0);
        const tempMax = Math.max(tempHigh + 2.0, 28.0);

        if (!chart.options.scales.y) {
          chart.options.scales.y = {
            type: 'linear',
            title: { display: true, text: 'Temperature (°C)' },
            grid: { color: 'rgba(148,163,184,0.12)' }
          };
        }
        chart.options.scales.y.min = tempMin;
        chart.options.scales.y.max = tempMax;

        return datasets;
      }
    });

    // Hook up controls
    window.createTimeRangeSelector('chillerRangeSelect', chart);
    window.createCustomRangeInputs('chillerFrom', 'chillerTo', 'chillerApply', chart);

    // Expose for external access
    window.chillerChart = chart;

    console.log('[Chiller Chart] Initialized');
  }

  if (document.readyState !== 'loading') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
