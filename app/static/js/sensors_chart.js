/**
 * Sensors Overview Chart
 * Shows combined pH, EC, and Temperature history on main sensors card
 * Replaces old trends.js
 */
(function() {
  'use strict';

  if (window.__sensorsChartModuleLoaded) {
    console.warn('[Sensors Chart] Module already loaded, skipping duplicate init');
    return;
  }
  window.__sensorsChartModuleLoaded = true;

  console.log('[Sensors Chart] Initializing');

  // Wait for DOM and dependencies
  function init() {
    if (typeof RDWCChart === 'undefined') {
      console.error('[Sensors Chart] RDWCChart base not loaded');
      return;
    }

    if (window.sensorsChart?.destroy) {
      try {
        window.sensorsChart.destroy();
      } catch (e) {
        console.warn('[Sensors Chart] Failed to destroy previous sensorsChart instance', e);
      }
    }
    if (window.trendsChart?.destroy) {
      try {
        window.trendsChart.destroy();
      } catch (e) {
        console.warn('[Sensors Chart] Failed to destroy previous trendsChart instance', e);
      }
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
        const { gran, max } = window.calculateGranularity(hours);

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

        let trendsData = null;
        for (const url of endpoints) {
          try {
            const res = await fetch(url, { cache: 'no-store' });
            if (res.ok) {
              trendsData = await res.json();
              console.log('[Sensors Chart] Fetched:', {
                ph: trendsData?.series?.ph?.length || 0,
                ec: trendsData?.series?.ec?.length || 0,
                temp: trendsData?.series?.temp?.length || 0
              });
              break;
            }
          } catch (e) {
            console.warn('[Sensors Chart] Endpoint failed:', url, e);
          }
        }

        if (!trendsData) {
          console.error('[Sensors Chart] All endpoints failed');
          trendsData = { series: { ph: [], ec: [], temp: [] } };
        }

        let settings = {};
        let tempStatus = {};
        try {
          const [settingsRes, tempStatusRes] = await Promise.all([
            fetch('/api/settings', { cache: 'no-store' }),
            fetch('/api/temperature/status', { cache: 'no-store' })
          ]);
          settings = settingsRes.ok ? await settingsRes.json() : {};
          tempStatus = tempStatusRes.ok ? await tempStatusRes.json() : {};
        } catch (e) {
          console.warn('[Sensors Chart] Settings/status fetch failed', e);
        }

        return {
          ...trendsData,
          settings,
          tempStatus
        };
      },

      // Render callback
      onRender: (chart, data, window) => {
        const axisCache = chart.__rdwcAxisCache || (chart.__rdwcAxisCache = {
          key: null,
          ph: null,
          ec: null,
          temp: null
        });

        const ph = (data?.series?.ph || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
        const ec = (data?.series?.ec || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));
        const temp = (data?.series?.temp || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) }));

        // Tight dynamic axis scaling so small sensor changes remain visible.
        // Use tighter spans on shorter windows and steadier spans on longer windows.
        const windowHours = Math.max((window.end - window.start) / (3600 * 1000), 0.01);
        let AXIS_CFG;
        if (windowHours <= 1.5) {
          AXIS_CFG = {
            ph: { fallback: { min: 5.75, max: 5.90 }, minSpan: 0.06, padRatio: 0.08 },
            ec: { fallback: { min: 1.95, max: 2.15 }, minSpan: 0.08, padRatio: 0.08, hardMin: 0 },
            temp: { fallback: { min: 17.5, max: 18.6 }, minSpan: 0.25, padRatio: 0.08 }
          };
        } else if (windowHours <= 24) {
          AXIS_CFG = {
            ph: { fallback: { min: 5.70, max: 5.95 }, minSpan: 0.12, padRatio: 0.10 },
            ec: { fallback: { min: 1.90, max: 2.20 }, minSpan: 0.14, padRatio: 0.10, hardMin: 0 },
            temp: { fallback: { min: 17.0, max: 19.0 }, minSpan: 0.45, padRatio: 0.10 }
          };
        } else if (windowHours <= 168) {
          AXIS_CFG = {
            ph: { fallback: { min: 5.60, max: 6.05 }, minSpan: 0.20, padRatio: 0.12 },
            ec: { fallback: { min: 1.70, max: 2.35 }, minSpan: 0.25, padRatio: 0.12, hardMin: 0 },
            temp: { fallback: { min: 16.5, max: 20.0 }, minSpan: 0.80, padRatio: 0.12 }
          };
        } else {
          AXIS_CFG = {
            ph: { fallback: { min: 5.50, max: 6.20 }, minSpan: 0.30, padRatio: 0.14 },
            ec: { fallback: { min: 1.50, max: 2.60 }, minSpan: 0.35, padRatio: 0.14, hardMin: 0 },
            temp: { fallback: { min: 16.0, max: 21.0 }, minSpan: 1.20, padRatio: 0.14 }
          };
        }

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

        const aPhNext = chooseAxis(AXIS_CFG.ph, ph);
        const aEcNext = chooseAxis(AXIS_CFG.ec, ec);
        let aTempNext = chooseAxis(AXIS_CFG.temp, temp);

        // Match Overview behavior: keep temperature axis fixed around setpoint ±10.
        const tempTargets = data?.settings?.targets || {};
        const tempSetpoint = Number(
          (data?.tempStatus?.target_temp) ??
          (tempTargets?.temp_target_c)
        );
        if (Number.isFinite(tempSetpoint)) {
          aTempNext = { min: tempSetpoint - 10, max: tempSetpoint + 10 };
        }

        const durationHours = (window.end - window.start) / (3600 * 1000);
        let windowKey;
        if (durationHours <= 1.5) windowKey = '1h';
        else if (durationHours <= 7) windowKey = '6h';
        else if (durationHours <= 28) windowKey = '24h';
        else if (durationHours <= 200) windowKey = '7d';
        else windowKey = 'grow';

        if (axisCache.key !== windowKey) {
          axisCache.key = windowKey;
          axisCache.ph = { min: aPhNext.min, max: aPhNext.max };
          axisCache.ec = { min: aEcNext.min, max: aEcNext.max };
          axisCache.temp = { min: aTempNext.min, max: aTempNext.max };
        } else {
          axisCache.ph.min = Math.min(axisCache.ph.min, aPhNext.min);
          axisCache.ph.max = Math.max(axisCache.ph.max, aPhNext.max);
          axisCache.ec.min = Math.min(axisCache.ec.min, aEcNext.min);
          axisCache.ec.max = Math.max(axisCache.ec.max, aEcNext.max);
          axisCache.temp.min = Math.min(axisCache.temp.min, aTempNext.min);
          axisCache.temp.max = Math.max(axisCache.temp.max, aTempNext.max);
        }

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
        chart.options.scales.yPh.min = axisCache.ph.min;
        chart.options.scales.yPh.max = axisCache.ph.max;
        chart.options.scales.yEc.min = axisCache.ec.min;
        chart.options.scales.yEc.max = axisCache.ec.max;
        chart.options.scales.yTemp.min = axisCache.temp.min;
        chart.options.scales.yTemp.max = axisCache.temp.max;

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
            spanGaps: true,
            order: 2
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
            spanGaps: true,
            order: 2
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
            spanGaps: true,
            order: 3
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
