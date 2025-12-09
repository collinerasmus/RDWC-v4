/**
 * pH Detailed Chart
 * Shows pH history with setpoint band, dose events, and total dosed
 * Replaces old ph_chart.js
 */
(function() {
  'use strict';

  console.log('[pH Chart] Initializing');

  let totalDosed = 0; // Track total pH Up dosed in current window

  function init() {
    if (typeof RDWCChart === 'undefined') {
      console.error('[pH Chart] RDWCChart base not loaded');
      return;
    }

    const chart = new RDWCChart({
      canvasId: 'phDoseChart',
      emptyMessageId: 'ph-dose-empty',
      type: 'ph',
      title: 'pH History & Dosing',
      
      onDataFetch: async (startISO, endISO) => {
        // Fetch pH readings from trends API
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
        
        // Fetch dose events
        const doseHours = Math.min(Math.ceil(hours), 168);
        const doseUrl = `/api/dose/recent?hours=${doseHours}`;

        // Fetch targets
        const targetsUrl = '/api/ph/targets';

        try {
          const [trendsRes, doseRes, targetsRes] = await Promise.all([
            fetch(trendsUrl, { cache: 'no-store' }),
            fetch(doseUrl, { cache: 'no-store' }),
            fetch(targetsUrl, { cache: 'no-store' })
          ]);

          const trendsData = trendsRes.ok ? await trendsRes.json() : { series: { ph: [] } };
          const doseData = doseRes.ok ? await doseRes.json() : { events: [] };
          const targetsData = targetsRes.ok ? await targetsRes.json() : {};

          console.log('[pH Chart] Fetched:', {
            ph: trendsData?.series?.ph?.length || 0,
            doses: doseData?.events?.length || 0,
            targets: targetsData
          });

          return { trendsData, doseData, targetsData };
        } catch (e) {
          console.error('[pH Chart] Fetch failed:', e);
          return { trendsData: { series: { ph: [] } }, doseData: { events: [] }, targetsData: {} };
        }
      },

      onRender: (chart, data, window) => {
        const { trendsData, doseData, targetsData } = data;

        // Parse pH readings
        const ph = (trendsData?.series?.ph || []).map(p => ({
          x: p.ts * 1000,
          y: Number(p.value)
        }));

        // Parse dose events (pH Up only)
        const doseEvents = (doseData?.events || [])
          .filter(e => e.pump === 'ph_up' && !e.blocked_by)
          .filter(e => {
            const ts = e.ts * 1000;
            return ts >= window.start && ts <= window.end;
          });

        // Calculate total dosed
        totalDosed = doseEvents.reduce((sum, e) => sum + (e.ml || 0), 0);

        // Update total dosed display
        const totalEl = document.getElementById('ph-total-dosed');
        if (totalEl) {
          totalEl.textContent = `${totalDosed.toFixed(1)} ml`;
        }

        // Get targets
        const phLow = targetsData?.ph_low ?? 5.8;
        const phHigh = targetsData?.ph_high ?? 6.2;

        // Get current pH
        const currentPH = ph.length > 0 ? ph[ph.length - 1].y : null;

        // Build datasets
        const datasets = [];

        // 1. pH setpoint band (box annotation)
        if (phLow && phHigh) {
          datasets.push({
            type: 'line',
            label: 'pH Target Band',
            data: [
              { x: window.start, y: phLow },
              { x: window.end, y: phLow }
            ],
            borderColor: 'rgba(59, 130, 246, 0.3)',
            borderWidth: 1,
            borderDash: [5, 5],
            fill: '+1',
            backgroundColor: window.CHART_COLORS?.setpointBand || 'rgba(59, 130, 246, 0.1)',
            pointRadius: 0
          });
          datasets.push({
            type: 'line',
            label: '',
            data: [
              { x: window.start, y: phHigh },
              { x: window.end, y: phHigh }
            ],
            borderColor: 'rgba(59, 130, 246, 0.3)',
            borderWidth: 1,
            borderDash: [5, 5],
            pointRadius: 0
          });
        }

        // 2. pH history line
        if (ph.length) {
          datasets.push({
            id: 'ph',
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

        // 3. Current pH marker
        if (currentPH != null) {
          datasets.push({
            type: 'scatter',
            label: `Current: ${currentPH.toFixed(2)}`,
            data: [{ x: window.end, y: currentPH }],
            pointRadius: 6,
            pointStyle: 'circle',
            pointBackgroundColor: window.CHART_COLORS?.ph || '#3b82f6',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            showLine: false,
            order: 0
          });
        }

        // 4. Dose events as triangles
        if (doseEvents.length) {
          const doseY = phHigh + 0.3; // Place above target band
          datasets.push({
            type: 'scatter',
            label: `pH Up Doses (${doseEvents.length})`,
            data: doseEvents.map(e => ({ x: e.ts * 1000, y: doseY })),
            pointRadius: 5,
            pointStyle: 'triangle',
            pointBackgroundColor: window.CHART_COLORS?.phUp || '#fbbf24',
            pointBorderColor: window.CHART_COLORS?.phUp || '#fbbf24',
            pointBorderWidth: 1,
            showLine: false,
            order: 2
          });
        }

        // Set fixed y-axis (pH range)
        const phMin = Math.min(phLow - 0.5, 5.0);
        const phMax = Math.max(phHigh + 0.8, 7.5);

        if (!chart.options.scales.y) {
          chart.options.scales.y = {
            type: 'linear',
            title: { display: true, text: 'pH' },
            grid: { color: 'rgba(148,163,184,0.12)' }
          };
        }
        chart.options.scales.y.min = phMin;
        chart.options.scales.y.max = phMax;

        return datasets;
      }
    });

    // Hook up controls
    window.createTimeRangeSelector('phDoseRangeSelect', chart);
    window.createCustomRangeInputs('phDoseFrom', 'phDoseTo', 'phDoseApply', chart);

    // Expose for external access
    window.phChart = chart;

    console.log('[pH Chart] Initialized');
  }

  if (document.readyState !== 'loading') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
