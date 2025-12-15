/**
 * Temperature Chart
 * Shows temperature history with setpoint band, cooler on/off events, and total runtime
 * NEW - for temperature tab
 */
(function() {
  'use strict';

  console.log('[Temperature Chart] Initializing');

  let totalCoolerTime = 0; // Total cooler ON time in minutes

  function init() {
    if (typeof RDWCChart === 'undefined') {
      console.error('[Temperature Chart] RDWCChart base not loaded');
      return;
    }

    const chart = new RDWCChart({
      canvasId: 'temperatureChart',
      emptyMessageId: 'temperature-chart-empty',
      type: 'temperature',
      title: 'Temperature & Cooling Activity',
      
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
        
        // Fetch cooler events
        const coolerHours = Math.min(Math.ceil(hours), 168);
        const coolerUrl = `/api/temperature/events?hours=${coolerHours}`;

        // Fetch temperature target
        const settingsUrl = '/api/settings';

        try {
          const [trendsRes, coolerRes, settingsRes] = await Promise.all([
            fetch(trendsUrl, { cache: 'no-store' }),
            fetch(coolerUrl, { cache: 'no-store' }).catch(() => null),
            fetch(settingsUrl, { cache: 'no-store' })
          ]);

          const trendsData = trendsRes.ok ? await trendsRes.json() : { series: { temp: [] } };
          const coolerData = coolerRes && coolerRes.ok ? await coolerRes.json() : { events: [] };
          const settingsData = settingsRes.ok ? await settingsRes.json() : {};

          console.log('[Temperature Chart] Fetched:', {
            temp: trendsData?.series?.temp?.length || 0,
            coolerEvents: coolerData?.events?.length || 0
          });

          return { trendsData, coolerData, settingsData };
        } catch (e) {
          console.error('[Temperature Chart] Fetch failed:', e);
          return { trendsData: { series: { temp: [] } }, coolerData: { events: [] }, settingsData: {} };
        }
      },

      onRender: (chart, data, window) => {
        const { trendsData, coolerData, settingsData } = data;

        // Parse temperature readings
        const temp = (trendsData?.series?.temp || []).map(p => ({
          x: p.ts * 1000,
          y: Number(p.value)
        }));

        // Parse cooler events
        const coolerEvents = (coolerData?.events || [])
          .filter(e => {
            const ts = e.ts * 1000;
            return ts >= window.start && ts <= window.end;
          });

        // Calculate total cooler ON time
        totalCoolerTime = 0;
        for (let i = 0; i < coolerEvents.length - 1; i++) {
          const current = coolerEvents[i];
          const next = coolerEvents[i + 1];
          if (current.state === 'ON') {
            const onDuration = (next.ts - current.ts) / 60; // minutes
            totalCoolerTime += onDuration;
          }
        }

        // Update total runtime display
        const totalEl = document.getElementById('temperature-total-runtime');
        if (totalEl) {
          const hours = Math.floor(totalCoolerTime / 60);
          const mins = Math.floor(totalCoolerTime % 60);
          totalEl.textContent = `${hours}h ${mins}m`;
        }

        // Get temperature target and hysteresis from settings
        const tempTarget = settingsData?.['targets.temp_target'] ?? 21.0;
        const tempHysteresis = settingsData?.['temperature.hysteresis'] ?? 0.5;
        const tempLow = tempTarget - tempHysteresis;
        const tempHigh = tempTarget + tempHysteresis;

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

        // 4. Cooler ON events as markers
        const coolerOnEvents = coolerEvents.filter(e => e.state === 'ON');
        if (coolerOnEvents.length) {
          const markerY = tempLow - 1.0; // Below target band
          datasets.push({
            type: 'scatter',
            label: `Cooler ON (${coolerOnEvents.length})`,
            data: coolerOnEvents.map(e => ({ x: e.ts * 1000, y: markerY })),
            pointRadius: 5,
            pointStyle: 'rectRot',
            pointBackgroundColor: window.CHART_COLORS?.coolerOn || '#60a5fa',
            pointBorderColor: window.CHART_COLORS?.coolerOn || '#60a5fa',
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
    window.createTimeRangeSelector('temperatureRangeSelect', chart);
    window.createCustomRangeInputs('temperatureFrom', 'temperatureTo', 'temperatureApply', chart);

    // Expose for external access
    window.temperatureChart = chart;

    console.log('[Temperature Chart] Initialized');
  }

  if (document.readyState !== 'loading') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
