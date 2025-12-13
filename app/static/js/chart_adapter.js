/**
 * Wire up new chart controls to existing chart implementations
 * This adapter integrates ChartControls with trends.js, ph.js, and ec.js
 */
(function() {
  'use strict';

  function init() {
    // Wait for Chart.js and other dependencies
    if (typeof Chart === 'undefined' || typeof ChartControls === 'undefined') {
      console.warn('[ChartAdapter] Dependencies not loaded yet, retrying...');
      setTimeout(init, 500);
      return;
    }

    initSensorsChart();
    initTrendsChart();
    initPhChart();
    initEcChart();
  }

  function initSensorsChart() {
    const controls = new ChartControls({
      containerId: 'sensors-chart-controls',
      onRangeChange: (start, end, isLive) => {
        // Trigger existing trends.js refresh with new range
        if (window.refreshTrends) {
          window.refreshTrends(start, end);
        }
      },
      getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date'),
      getDataExtent: () => ({ first: null, last: null }) // TODO: implement
    });

    // Override export
    if (controls) {
      controls.onExport = () => {
        if (window.exportCsv) window.exportCsv();
      };
    }

    // Store reference for periodic updates
    window.sensorsChartControls = controls;
  }

  function initTrendsChart() {
    const controls = new ChartControls({
      containerId: 'trends-controls',
      onRangeChange: (start, end, isLive) => {
        // Trends tab uses same data/rendering as sensors
        if (window.refreshTrends) {
          window.refreshTrends(start, end);
        }
      },
      getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date'),
      getDataExtent: () => ({ first: null, last: null })
    });

    if (controls) {
      controls.onExport = () => {
        if (window.exportCsv) window.exportCsv();
      };
    }

    window.trendsChartControls = controls;
  }

  function initPhChart() {
    const controls = new ChartControls({
      containerId: 'ph-chart-controls',
      onRangeChange: (start, end, isLive) => {
        // Trigger pH chart refresh
        if (window.phDoseChart && window.phDoseChart.render) {
          window.phDoseChart.render({ start, end });
        }
      },
      getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date'),
      getDataExtent: () => ({ first: null, last: null })
    });

    if (controls) {
      controls.onExport = () => {
        // pH export logic from ph.js
        const start = controls.currentRange?.start;
        const end = controls.currentRange?.end;
        if (start && end) {
          const startISO = new Date(start).toISOString();
          const endISO = new Date(end).toISOString();
          window.open(`/api/ph/dose_log.csv?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=5000`, '_blank');
        }
      };
    }

    window.phChartControls = controls;
  }

  function initEcChart() {
    const controls = new ChartControls({
      containerId: 'ec-chart-controls',
      onRangeChange: (start, end, isLive) => {
        // Trigger EC chart refresh
        if (window.ecDoseChart && window.ecDoseChart.render) {
          window.ecDoseChart.render({ start, end });
        }
      },
      getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date'),
      getDataExtent: () => ({ first: null, last: null })
    });

    if (controls) {
      controls.onExport = () => {
        // EC export logic
        const start = controls.currentRange?.start;
        const end = controls.currentRange?.end;
        if (start && end) {
          const startISO = new Date(start).toISOString();
          const endISO = new Date(end).toISOString();
          window.open(`/api/ec/dose_log.csv?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}&limit=5000`, '_blank');
        }
      };
    }

    window.ecChartControls = controls;
  }

  // Auto-init when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
