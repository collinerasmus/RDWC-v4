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

    // ===== SENSORS CHART =====
    // sensors_chart.js exposes window.sensorsChart (RDWCChart instance)
    if (document.getElementById('sensors-chart-controls')) {
      if (window.sensorsChart && typeof window.sensorsChart.setTimeRange === 'function') {
        const sensorsControls = new ChartControls({
          containerId: 'sensors-chart-controls',
          onRangeChange: async (start, end, isLive) => {
            console.log('[Chart Adapter] Sensors range changed:', start, end);
            try {
              window.sensorsChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.sensorsChart.isLiveMode = !!isLive;
              window.sensorsChart.selectedRange = isLive ? 'live' : 'custom';
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
          onRangeChange: async (start, end, isLive) => {
            console.log('[Chart Adapter] Trends range changed:', start, end);
            try {
              window.trendsChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.trendsChart.isLiveMode = !!isLive;
              window.trendsChart.selectedRange = isLive ? 'live' : 'custom';
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
          onRangeChange: async (start, end, isLive) => {
            console.log('[Chart Adapter] pH range changed:', start, end);
            try {
              window.phChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.phChart.isLiveMode = !!isLive;
              window.phChart.selectedRange = isLive ? 'live' : 'custom';
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
          onRangeChange: async (start, end, isLive) => {
            console.log('[Chart Adapter] EC range changed:', start, end);
            try {
              window.ecChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.ecChart.isLiveMode = !!isLive;
              window.ecChart.selectedRange = isLive ? 'live' : 'custom';
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
          onRangeChange: async (start, end, isLive) => {
            console.log('[Chart Adapter] Temperature range changed:', start, end);
            try {
              window.temperatureChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
              window.temperatureChart.isLiveMode = !!isLive;
              window.temperatureChart.selectedRange = isLive ? 'live' : 'custom';
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

    // ===== LIGHTS CHART =====
    // lights_v2.js exposes window.lightsChart with setLightsChartRange for panning
    if (document.getElementById('lights-chart-controls')) {
      if (window.lightsChart && window.setLightsChartRange) {
        const lightsControls = new ChartControls({
          containerId: 'lights-chart-controls',
          onRangeChange: async (start, end) => {
            console.log('[Chart Adapter] Lights range changed:', start, end);
            try {
              window.setLightsChartRange(start, end);
            } catch (e) {
              console.error('[Chart Adapter] Lights chart update failed:', e);
            }
          },
          getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date')
        });
        console.log('[Chart Adapter] Lights controls initialized');
      } else {
        console.warn('[Chart Adapter] Lights chart controls div found but window.lightsChart not ready');
      }
    }

    // ===== CIRCULATION CHART =====
    // circulation_v2.js initializes window.circChart (RDWCChart instance)
    // Note: Circulation chart may initialize after chart_adapter, so we retry aggressively
    function initCirculationControls(attempts = 0) {
      const container = document.getElementById('circ-chart-controls');
      if (!container) {
        console.error('[Chart Adapter] circ-chart-controls container not found');
        return;
      }
      
      if (window.circChart && typeof window.circChart.setTimeRange === 'function') {
        try {
          const circControls = new window.ChartControls({
            containerId: 'circ-chart-controls',
            onRangeChange: async (start, end, isLive) => {
              console.log('[Chart Adapter] Circulation range changed:', start, end);
              try {
                window.circChart.timeWindow = { start: new Date(start).getTime(), end: new Date(end).getTime() };
                window.circChart.isLiveMode = !!isLive;
                window.circChart.selectedRange = isLive ? 'live' : 'custom';
                await window.circChart.refresh(true);
              } catch (e) {
                console.error('[Chart Adapter] Circulation chart update failed:', e);
              }
            },
            getGrowStartDate: () => window.rdwcSettings?.get('general.grow_start_date')
          });
        } catch (e) {
          console.error('[Chart Adapter] Failed to create ChartControls for circulation:', e.message);
        }
      } else if (attempts < 50) {
        setTimeout(() => initCirculationControls(attempts + 1), 200);
      } else {
        console.error('[Chart Adapter] Circulation chart not ready after retries');
      }
    }
    initCirculationControls();
  }
})();


