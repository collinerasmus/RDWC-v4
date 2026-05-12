/**
 * Sensors Overview Chart
 * Shows combined pH, EC, and Temperature history on main sensors card
 * Replaces old trends.js
 */
(function() {
  'use strict';

  console.log('[Sensors Chart] Initializing');

  // Wait for DOM and dependencies
  function init() {
    if (typeof RDWCChart === 'undefined') {
      console.error('[Sensors Chart] RDWCChart base not loaded');
      return;
    }

    const chart = new RDWCChart({
      canvasId: 'trendChart',
      emptyMessageId: 'trendEmpty',
      type: 'sensors',
      title: 'Sensor History',
      
      // Data fetch callback
      onDataFetch: async (startISO, endISO) => {
        // Determine granularity based on time span
        const span = new Date(endISO) - new Date(startISO);
        const hours = span / (3600 * 1000);
        let gran, max;

        if (hours <= 1) { gran = 30; max = 150; }      // 30s buckets
        else if (hours <= 24) { gran = 60; max = 1500; } // 1min buckets
        else if (hours <= 168) { gran = 300; max = 2100; } // 5min buckets  
        else if (hours <= 720) { gran = 900; max = 3000; } // 15min buckets
        else { gran = 3600; max = 3000; } // hourly buckets

        const q = new URLSearchParams();
        q.set('from', startISO);
        q.set('to', endISO);
        q.set('gran', String(gran));
        q.set('max', String(max));

        // Try multiple endpoints
        const endpoints = [
          '/api/trends?' + q.toString(),
          '/history?' + q.toString()
        ];

        for (const url of endpoints) {
          try {
            const res = await fetch(url, { cache: 'no-store' });
            if (res.ok) {
              const data = await res.json();
              console.log('[Sensors Chart] Fetched:', {
                ph: data?.series?.ph?.length || 0,
                ec: data?.series?.ec?.length || 0,
                temp: data?.series?.temp?.length || 0
              });
              return data;
            }
          } catch (e) {
            console.warn('[Sensors Chart] Endpoint failed:', url, e);
          }
        }

        console.error('[Sensors Chart] All endpoints failed');
        return { series: { ph: [], ec: [], temp: [] } };
      },

      // Render callback
      onRender: (chart, data, window) => {
        const ph = (data?.series?.ph || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
        const ec = (data?.series?.ec || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
        const temp = (data?.series?.temp || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));

        // Tight dynamic axis scaling so small sensor changes remain visible.
        const AXIS_CFG = {
          ph: { fallback: { min: 5.5, max: 6.5 }, minSpan: 0.35, padRatio: 0.12 },
          ec: { fallback: { min: 1.5, max: 2.5 }, minSpan: 0.25, padRatio: 0.12, hardMin: 0 },
          temp: { fallback: { min: 17.0, max: 19.5 }, minSpan: 0.8, padRatio: 0.14 }
        };

        function dataMinMax(series) {
          let lo = Infinity, hi = -Infinity;
          for (const p of series) {
            if (Number.isFinite(p.y)) {
              lo = Math.min(lo, p.y);
              hi = Math.max(hi, p.y);
            }
          }
          return (Number.isFinite(lo) && Number.isFinite(hi)) ? { lo, hi } : null;
        }

        function chooseAxis(cfg, series) {
          const mm = dataMinMax(series);
          if (!mm) return cfg.fallback;

          const rawSpan = Math.max(mm.hi - mm.lo, 0);
          const pad = Math.max(rawSpan * cfg.padRatio, cfg.minSpan * 0.25);
          let min = mm.lo - pad;
          let max = mm.hi + pad;

          // Keep a minimum visible span to avoid jittery over-zooming.
          if ((max - min) < cfg.minSpan) {
            const mid = (min + max) / 2;
            min = mid - (cfg.minSpan / 2);
            max = mid + (cfg.minSpan / 2);
          }

          if (Number.isFinite(cfg.hardMin)) {
            min = Math.max(cfg.hardMin, min);
          }

          return { min, max };
        }

        const aPh = chooseAxis(AXIS_CFG.ph, ph);
        const aEc = chooseAxis(AXIS_CFG.ec, ec);
        const aTemp = chooseAxis(AXIS_CFG.temp, temp);

        // Create or update y-axes with improved positioning
        // pH on left, EC and Temp stacked on right with offset
        if (!chart.options.scales.yPh) {
          chart.options.scales.yPh = {
            type: 'linear',
            position: 'left',
            title: { display: true, text: 'pH', color: '#9ca3af', font: { size: 11 } },
            grid: { color: 'rgba(148,163,184,0.12)' },
            ticks: { color: '#9ca3af' }
          };
        }
        if (!chart.options.scales.yEc) {
          chart.options.scales.yEc = {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'EC (mS/cm)', color: '#9ca3af', font: { size: 11 } },
            grid: { drawOnChartArea: false },
            ticks: { color: '#9ca3af' }
          };
        }
        if (!chart.options.scales.yTemp) {
          chart.options.scales.yTemp = {
            type: 'linear',
            position: 'right',
            offset: true,
            title: { display: true, text: 'Temp (°C)', color: '#9ca3af', font: { size: 11 } },
            grid: { drawOnChartArea: false },
            ticks: { color: '#9ca3af' }
          };
        }

        // Set fixed axis limits
        chart.options.scales.yPh.min = aPh.min;
        chart.options.scales.yPh.max = aPh.max;
        chart.options.scales.yEc.min = aEc.min;
        chart.options.scales.yEc.max = aEc.max;
        chart.options.scales.yTemp.min = aTemp.min;
        chart.options.scales.yTemp.max = aTemp.max;

        // Build datasets
        const datasets = [];
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
            spanGaps: true
          });
        }
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
            spanGaps: true
          });
        }
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
            spanGaps: true
          });
        }

        return datasets;
      }
    });

    // Hook up time range selector
    window.createCustomRangeInputs('trendFrom', 'trendTo', 'trendApply', chart);

    // Expose for external access
    window.sensorsChart = chart;

    // ===== TRENDS TAB CHART =====
    // Also initialize trendsChart canvas for the Trends tab (separate from Sensors tab)
    // Uses the exact same configuration and shares the same state
    const trendsChartEl = document.getElementById('trendsChart');
    if (trendsChartEl) {
      const trendsChart = new RDWCChart({
        canvasId: 'trendsChart',
        emptyMessageId: 'trendsEmpty',
        type: 'trends',
        title: 'Sensor Trends',
        
        // Reuse the same data fetch logic as sensors chart
        onDataFetch: chart.onDataFetch,
        onRender: chart.onRender
      });

      // Expose for external access
      window.trendsChart = trendsChart;
      console.log('[Sensors Chart] Trends tab chart initialized');
    }

    console.log('[Sensors Chart] Initialized');
  }

  if (document.readyState !== 'loading') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
