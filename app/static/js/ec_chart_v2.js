/**
 * EC Detailed Chart
 * Shows EC history with setpoint band, nutrient dose events, and total dosed
 * Replaces old ec_chart.js
 */
(function() {
  'use strict';

  console.log('[EC Chart] Initializing');

  let totalGrow = 0, totalMicro = 0, totalBloom = 0;

  function init() {
    if (typeof RDWCChart === 'undefined') {
      console.error('[EC Chart] RDWCChart base not loaded');
      return;
    }

    const chart = new RDWCChart({
      canvasId: 'ecDoseChart',
      emptyMessageId: 'ec-dose-empty',
      type: 'ec',
      title: 'EC History & Dosing',
      
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
        
        // Fetch unified EC dose log using exact chart window
        const doseUrl = `/api/ec/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`;

        try {
          const [trendsRes, doseRes, statusRes] = await Promise.all([
            fetch(trendsUrl, { cache: 'no-store' }),
            fetch(doseUrl, { cache: 'no-store' }),
            fetch('/api/ec/status', { cache: 'no-store' })
          ]);

          const trendsData = trendsRes.ok ? await trendsRes.json() : { series: { ec: [] } };
          const doseData = doseRes.ok ? await doseRes.json() : [];
          const statusData = statusRes.ok ? await statusRes.json() : {};
          const targets = statusData?.targets || {};

          console.log('[EC Chart] Fetched:', {
            ec: trendsData?.series?.ec?.length || 0,
            doses: Array.isArray(doseData) ? doseData.length : 0,
            targets: targets
          });

          return { trendsData, doseData, targets };
        } catch (e) {
          console.error('[EC Chart] Fetch failed:', e);
          return { trendsData: { series: { ec: [] } }, doseData: { events: [] }, targets: {} };
        }
      },

      onRender: (chart, data, window) => {
        const { trendsData, doseData, targets } = data;

        // Parse EC readings
        const ec = (trendsData?.series?.ec || []).map(p => ({
          x: p.ts * 1000,
          y: Number(p.value)
        }));

        // Parse dose events from unified EC dose log
        const unifiedEvents = Array.isArray(doseData) ? doseData : [];
        const growEvents = unifiedEvents.filter(e => e?.pumps?.grow && e.pumps.grow > 0).map(e => ({ ts: new Date(e.ts).getTime(), ml: e.pumps.grow }));
        const microEvents = unifiedEvents.filter(e => e?.pumps?.micro && e.pumps.micro > 0).map(e => ({ ts: new Date(e.ts).getTime(), ml: e.pumps.micro }));
        const bloomEvents = unifiedEvents.filter(e => e?.pumps?.bloom && e.pumps.bloom > 0).map(e => ({ ts: new Date(e.ts).getTime(), ml: e.pumps.bloom }));

        // Calculate totals directly from ml in pumps
        totalGrow = growEvents.reduce((sum, e) => sum + (Number(e.ml || 0)), 0);
        totalMicro = microEvents.reduce((sum, e) => sum + (Number(e.ml || 0)), 0);
        totalBloom = bloomEvents.reduce((sum, e) => sum + (Number(e.ml || 0)), 0);

        // Update total dosed displays
        const totalEl = document.getElementById('ec-total-dosed');
        if (totalEl) {
          totalEl.textContent = `Grow: ${totalGrow.toFixed(1)} ml  |  Micro: ${totalMicro.toFixed(1)} ml  |  Bloom: ${totalBloom.toFixed(1)} ml`;
        }

        // Get targets (scheduler-derived from /api/ec/status)
        const ecLow = Number(targets?.low);
        const ecHigh = Number(targets?.high);
        const hasValidBand = Number.isFinite(ecLow) && Number.isFinite(ecHigh) && ecLow < ecHigh;

        // Get current EC
        const currentEC = ec.length > 0 ? ec[ec.length - 1].y : null;

        // Build datasets
        const datasets = [];

        // 1. EC setpoint band
        if (hasValidBand) {
          datasets.push({
            type: 'line',
            label: 'EC Target Band',
            data: [
              { x: window.start, y: ecLow },
              { x: window.end, y: ecLow }
            ],
            borderColor: 'rgba(16, 185, 129, 0.3)',
            borderWidth: 1,
            borderDash: [5, 5],
            fill: '+1',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            pointRadius: 0
          });
          datasets.push({
            type: 'line',
            label: '',
            data: [
              { x: window.start, y: ecHigh },
              { x: window.end, y: ecHigh }
            ],
            borderColor: 'rgba(16, 185, 129, 0.3)',
            borderWidth: 1,
            borderDash: [5, 5],
            pointRadius: 0
          });
        }

        // 2. EC history line
        if (ec.length) {
          datasets.push({
            id: 'ec',
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

        // 3. Current EC marker
        if (currentEC != null) {
          datasets.push({
            type: 'scatter',
            label: `Current: ${currentEC.toFixed(2)} mS/cm`,
            data: [{ x: window.end, y: currentEC }],
            pointRadius: 6,
            pointStyle: 'circle',
            pointBackgroundColor: window.CHART_COLORS?.ec || '#10b981',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            showLine: false,
            order: 0
          });
        }

        // 4. Dose events (stacked vertically)
        const doseBase = hasValidBand ? ecHigh : (ec.length ? (Math.max(...ec.map(p => p.y))) : 1.0);
        const doseY = [
          doseBase + 0.3,  // grow (top)
          doseBase + 0.2,  // micro
          doseBase + 0.1   // bloom (bottom)
        ];

        if (growEvents.length) {
          datasets.push({
            type: 'scatter',
            label: `Grow (${growEvents.length})`,
            data: growEvents.map(e => ({ x: e.ts, y: doseY[0] })),
            pointRadius: 5,
            pointStyle: 'circle',
            pointBackgroundColor: window.CHART_COLORS?.grow || '#6ee7b7',
            pointBorderColor: window.CHART_COLORS?.grow || '#6ee7b7',
            pointBorderWidth: 1,
            showLine: false,
            order: 2
          });
        }

        if (microEvents.length) {
          datasets.push({
            type: 'scatter',
            label: `Micro (${microEvents.length})`,
            data: microEvents.map(e => ({ x: e.ts, y: doseY[1] })),
            pointRadius: 5,
            pointStyle: 'circle',
            pointBackgroundColor: window.CHART_COLORS?.micro || '#67e8f9',
            pointBorderColor: window.CHART_COLORS?.micro || '#67e8f9',
            pointBorderWidth: 1,
            showLine: false,
            order: 2
          });
        }

        if (bloomEvents.length) {
          datasets.push({
            type: 'scatter',
            label: `Bloom (${bloomEvents.length})`,
            data: bloomEvents.map(e => ({ x: e.ts, y: doseY[2] })),
            pointRadius: 5,
            pointStyle: 'circle',
            pointBackgroundColor: window.CHART_COLORS?.bloom || '#c084fc',
            pointBorderColor: window.CHART_COLORS?.bloom || '#c084fc',
            pointBorderWidth: 1,
            showLine: false,
            order: 2
          });
        }

        // Auto-scale the EC tab tightly to visible data, target band, and dose markers.
        const ecValues = ec.map(point => point.y).filter(Number.isFinite);
        if (Number.isFinite(currentEC)) ecValues.push(currentEC);
        if (hasValidBand) {
          ecValues.push(ecLow, ecHigh);
        }
        doseY.forEach(value => {
          if (Number.isFinite(value)) ecValues.push(value);
        });

        const ecFloor = ecValues.length ? Math.min(...ecValues) : 1.0;
        const ecCeil = ecValues.length ? Math.max(...ecValues) : 2.0;
        const ecPadding = Math.max((ecCeil - ecFloor) * 0.12, 0.05);
        const ecMin = Math.max(0, ecFloor - ecPadding);
        const ecMax = ecCeil + ecPadding;

        if (!chart.options.scales.y) {
          chart.options.scales.y = {
            type: 'linear',
            title: { display: true, text: 'EC (mS/cm)' },
            grid: { color: 'rgba(148,163,184,0.12)' }
          };
        }
        chart.options.scales.y.min = ecMin;
        chart.options.scales.y.max = ecMax;

        return datasets;
      }
    });

    // Hook up controls (custom range only - no select element in UI)
    window.createCustomRangeInputs('ecDoseFrom', 'ecDoseTo', 'ecDoseApply', chart);

    // Expose for external access
    window.ecChart = chart;

    console.log('[EC Chart] Initialized');
  }

  if (document.readyState !== 'loading') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
