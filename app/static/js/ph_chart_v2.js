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

        // Fetch pH dose events and summary (volume_ml available)
        const doseLogUrl = `/api/ph/dose_log?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=2000`;
        const doseSummaryUrl = `/api/ph/dose_summary?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`;

        try {
          const [trendsRes, doseLogRes, doseSummaryRes, settingsRes, scheduleRes] = await Promise.all([
            fetch(trendsUrl, { cache: 'no-store' }),
            fetch(doseLogUrl, { cache: 'no-store' }),
            fetch(doseSummaryUrl, { cache: 'no-store' }),
            fetch('/api/settings', { cache: 'no-store' }),
            fetch('/api/schedule/current_week', { cache: 'no-store' })
          ]);

          const trendsData = trendsRes.ok ? await trendsRes.json() : { series: { ph: [] } };
          const doseLog = doseLogRes.ok ? await doseLogRes.json() : [];
          const doseSummary = doseSummaryRes.ok ? await doseSummaryRes.json() : [];
          const settingsData = settingsRes.ok ? await settingsRes.json() : {};
          const scheduleData = scheduleRes.ok ? await scheduleRes.json() : {};
          const targets = settingsData?.targets || {};
          const phSetpoint = typeof scheduleData.ph_setpoint === 'number' ? scheduleData.ph_setpoint : null;

          console.log('[pH Chart] Fetched:', {
            ph: trendsData?.series?.ph?.length || 0,
            doses: doseLog?.length || 0,
            targets: targets
          });

          return { trendsData, doseLog, doseSummary, targets, phSetpoint };
        } catch (e) {
          console.error('[pH Chart] Fetch failed:', e);
          return { trendsData: { series: { ph: [] } }, doseLog: [], doseSummary: [], targets: {}, phSetpoint: null };
        }
      },

      onRender: (chart, data, window) => {
        const { trendsData, doseLog, doseSummary, targets, phSetpoint } = data;

        // Parse pH readings
        const ph = (trendsData?.series?.ph || []).map(p => ({
          x: p.ts * 1000,
          y: Number(p.value)
        }));

        // Parse dose events from /api/ph/dose_log (volume_ml preferred)
        const doseEvents = (doseLog || [])
          .map(e => ({
            ts: new Date(e.ts).getTime(),
            volume_ml: (e.volume_ml != null) ? Number(e.volume_ml) : null,
            seconds: (e.seconds != null) ? Number(e.seconds) : null,
            ph_before: (e.ph_before != null) ? Number(e.ph_before) : null,
            ph_after: (e.ph_after != null) ? Number(e.ph_after) : null
          }))
          .filter(ev => ev.ts >= window.start && ev.ts <= window.end);

        // Calculate total dosed (prefer summary rows if available)
        if (Array.isArray(doseSummary) && doseSummary.length > 0) {
          try {
            totalDosed = doseSummary.reduce((sum, r) => sum + (Number(r.total_ml || 0)), 0);
          } catch(_) { totalDosed = 0; }
        } else {
          totalDosed = doseEvents.reduce((sum, e) => sum + (Number(e.volume_ml || 0)), 0);
        }

        // Update total dosed display
        const totalEl = document.getElementById('ph-total-dosed');
        if (totalEl) {
          totalEl.textContent = 'Total: ' + (Number(totalDosed || 0).toFixed(1)) + ' ml';
          totalEl.style.display = 'inline-block';
        }

        // Get targets from settings (convert strings to floats)
        const band = parseFloat(targets?.ph_band);
        const useBand = !Number.isNaN(band);
        const phLow = useBand && phSetpoint != null ? phSetpoint - band : (parseFloat(targets?.ph_low) || 5.8);
        const phHigh = useBand && phSetpoint != null ? phSetpoint + band : (parseFloat(targets?.ph_high) || 6.2);

        // Get current pH
        const currentPH = ph.length > 0 ? ph[ph.length - 1].y : null;

        // Build datasets
        const datasets = [];

        // 1. pH setpoint band (box annotation)
        const hasBand = Number.isFinite(phLow) && Number.isFinite(phHigh) && phHigh > phLow;
        if (hasBand) {
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

        // Auto-scale the pH tab tightly to visible data and target band.
        // Dose markers are added after range selection so they remain in a fixed lane.
        const phValues = ph.map(point => point.y).filter(Number.isFinite);
        if (Number.isFinite(currentPH)) phValues.push(currentPH);
        if (Number.isFinite(phLow)) phValues.push(phLow);
        if (Number.isFinite(phHigh)) phValues.push(phHigh);

        const phFloor = phValues.length ? Math.min(...phValues) : 5.8;
        const phCeil = phValues.length ? Math.max(...phValues) : 6.2;
        const phSpanData = Math.max(phCeil - phFloor, 0);
        const windowHours = Math.max((window.end - window.start) / (3600 * 1000), 0.01);

        // Adaptive zoom: tighter for short windows, steadier for long windows.
        let minSpan;
        let minPad;
        if (windowHours <= 1.5) {
          minSpan = 0.06;
          minPad = 0.012;
        } else if (windowHours <= 24) {
          minSpan = 0.10;
          minPad = 0.018;
        } else if (windowHours <= 168) {
          minSpan = 0.16;
          minPad = 0.025;
        } else {
          minSpan = 0.22;
          minPad = 0.035;
        }

        const phPadding = Math.max(phSpanData * 0.10, minPad);
        let phMin = phFloor - phPadding;
        let phMax = phCeil + phPadding;

        // Keep a minimum visible span so axis doesn't jitter or over-zoom.
        if ((phMax - phMin) < minSpan) {
          const mid = (phMax + phMin) / 2;
          phMin = mid - (minSpan / 2);
          phMax = mid + (minSpan / 2);
        }

        if (!chart.options.scales.y) {
          chart.options.scales.y = {
            type: 'linear',
            title: { display: true, text: 'pH' },
            grid: { color: 'rgba(148,163,184,0.12)' }
          };
        }
        chart.options.scales.y.min = phMin;
        chart.options.scales.y.max = phMax;

        // 4. Dose events as triangles in a fixed top lane tied to chart range.
        if (doseEvents.length) {
          const span = Math.max(phMax - phMin, 0.001);
          const doseY = phMax - (span * 0.075); // top ~1/8 lane
          datasets.push({
            type: 'scatter',
            label: `pH Up Doses (${doseEvents.length})`,
            data: doseEvents.map(e => ({ x: e.ts, y: doseY })),
            pointRadius: 5,
            pointStyle: 'triangle',
            pointBackgroundColor: window.CHART_COLORS?.phUp || '#fbbf24',
            pointBorderColor: window.CHART_COLORS?.phUp || '#fbbf24',
            pointBorderWidth: 1,
            showLine: false,
            order: 2
          });
        }

        return datasets;
      }
    });

    // Hook up controls
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
