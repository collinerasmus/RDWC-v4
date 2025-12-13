/**
 * Chart Adapter: Wire ChartControls to existing chart implementations
 * Provides zoom + slider controls for all dashboard charts
 * 
 * Integration points:
 * - Sensors: window.sensorsChart (RDWCChart instance) -> setTimeRange()
 * - Trends: window.trendsChart (RDWCChart instance) -> setTimeRange()
 * - pH: window.phChart (RDWCChart instance) -> setTimeRange()
 * - EC: window.ecChart (RDWCChart instance) -> setTimeRange()
 * - Temperature: window.temperatureChart (RDWCChart instance) -> setTimeRange()
 */
(function() {
  'use strict';

  console.log('[Chart Adapter] Initializing chart controls for all charts');

  // Wait for DOM and dependencies
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 500));
  } else {
    setTimeout(init, 500); // Increased delay to ensure chart modules loaded
  }

  function init() {
    // Check dependencies
    if (typeof ChartControls === 'undefined') {
      console.error('[Chart Adapter] ChartControls not loaded');
      return;
    }

    console.log('[Chart Adapter] Starting initialization...');
    console.log('[Chart Adapter] Available chart instances:', {
      sensorsChart: !!window.sensorsChart,
      trendsChart: !!window.trendsChart,
      phChart: !!window.phChart,
      ecChart: !!window.ecChart,
      temperatureChart: !!window.temperatureChart
    });

    // ===== SENSORS CHART =====
    // sensors_chart.js exposes window.sensorsChart (RDWCChart instance)
    if (document.getElementById('sensors-chart-controls')) {
      if (window.sensorsChart && typeof window.sensorsChart.setTimeRange === 'function') {
        const sensorsControls = new ChartControls({
          containerId: 'sensors-chart-controls',
          onRangeChange: async (start, end) => {
            console.log('[Chart Adapter] Sensors range changed:', start, end);
            try {
              window.sensorsChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.sensorsChart.selectedRange = 'custom';
              await window.sensorsChart.refresh(true);
            } catch (e) {
              console.error('[Chart Adapter] Sensors chart update failed:', e);
            }
          },
          getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date')
        });
        console.log('[Chart Adapter] Sensors controls initialized');
      } else {
        console.warn('[Chart Adapter] Sensors chart controls div found but window.sensorsChart not ready');
      }
    }

    // ===== TRENDS CHART =====
    // sensors_chart.js also initializes window.trendsChart (separate RDWCChart instance for Trends tab)
    if (document.getElementById('trends-controls')) {
      if (window.trendsChart && typeof window.trendsChart.setTimeRange === 'function') {
        const trendsControls = new ChartControls({
          containerId: 'trends-controls',
          onRangeChange: async (start, end) => {
            console.log('[Chart Adapter] Trends range changed:', start, end);
            try {
              window.trendsChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.trendsChart.selectedRange = 'custom';
              await window.trendsChart.refresh(true);
            } catch (e) {
              console.error('[Chart Adapter] Trends chart update failed:', e);
            }
          },
          getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date')
        });
        console.log('[Chart Adapter] Trends controls initialized');
      } else {
        console.warn('[Chart Adapter] Trends chart controls div found but window.trendsChart not ready');
      }
    }

    // ===== pH DOSE CHART =====
    // ph_chart_v2.js exposes window.phChart (RDWCChart instance)
    if (document.getElementById('ph-chart-controls')) {
      if (window.phChart && typeof window.phChart.setTimeRange === 'function') {
        const phControls = new ChartControls({
          containerId: 'ph-chart-controls',
          onRangeChange: async (start, end) => {
            console.log('[Chart Adapter] pH range changed:', start, end);
            try {
              window.phChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.phChart.selectedRange = 'custom';
              await window.phChart.refresh(true);
            } catch (e) {
              console.error('[Chart Adapter] pH chart update failed:', e);
            }
          },
          getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date')
        });
        console.log('[Chart Adapter] pH controls initialized');
      } else {
        console.warn('[Chart Adapter] pH chart controls div found but window.phChart not ready');
      }
    }

    // ===== EC DOSE CHART =====
    // ec_chart_v2.js exposes window.ecChart (RDWCChart instance)
    if (document.getElementById('ec-chart-controls')) {
      if (window.ecChart && typeof window.ecChart.setTimeRange === 'function') {
        const ecControls = new ChartControls({
          containerId: 'ec-chart-controls',
          onRangeChange: async (start, end) => {
            console.log('[Chart Adapter] EC range changed:', start, end);
            try {
              window.ecChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.ecChart.selectedRange = 'custom';
              await window.ecChart.refresh(true);
            } catch (e) {
              console.error('[Chart Adapter] EC chart update failed:', e);
            }
          },
          getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date')
        });
        console.log('[Chart Adapter] EC controls initialized');
      } else {
        console.warn('[Chart Adapter] EC chart controls div found but window.ecChart not ready');
      }
    }

    // ===== TEMPERATURE CHART =====
    // temperature_chart.js should expose window.temperatureChart (RDWCChart instance)
    if (document.getElementById('temperature-chart-controls')) {
      if (window.temperatureChart && typeof window.temperatureChart.setTimeRange === 'function') {
        const tempControls = new ChartControls({
          containerId: 'temperature-chart-controls',
          onRangeChange: async (start, end) => {
            console.log('[Chart Adapter] Temperature range changed:', start, end);
            try {
              window.temperatureChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.temperatureChart.selectedRange = 'custom';
              await window.temperatureChart.refresh(true);
            } catch (e) {
              console.error('[Chart Adapter] Temperature chart update failed:', e);
            }
          },
          getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date')
        });
        console.log('[Chart Adapter] Temperature controls initialized');
      } else {
        console.warn('[Chart Adapter] Temperature chart controls div found but window.temperatureChart not ready');
      }
    }

    console.log('[Chart Adapter] All chart controls initialized successfully');
  }
})();


