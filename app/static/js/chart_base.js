/**
 * Unified Chart Base Module
 * Provides consistent charting for all RDWC dashboard charts
 * - Fixed axis scaling (no reshape on data changes)
 * - Time range controls (1h, 24h, 1w, 1m, grow window, custom)
 * - Auto-refresh with live data updates
 * - Setpoint bands and event markers
 */
(function() {
  'use strict';

  console.log('[ChartBase] Initializing unified chart system');

  // Time range presets in milliseconds
  const TIME_RANGES = {
    '1h': 3600 * 1000,
    '24h': 24 * 3600 * 1000,
    '1w': 7 * 24 * 3600 * 1000,
    '1m': 30 * 24 * 3600 * 1000
  };

  // Chart color palette
  const COLORS = {
    ph: '#3b82f6',      // blue
    ec: '#10b981',      // emerald
    temp: '#ef4444',    // red
    phUp: '#fbbf24',    // amber
    grow: '#6ee7b7',    // light emerald
    micro: '#67e8f9',   // cyan
    bloom: '#c084fc',   // purple
    chillerOn: '#60a5fa', // light blue
    setpointBand: 'rgba(59, 130, 246, 0.1)' // semi-transparent blue
  };

  /**
   * Calculate API granularity and max points based on time span in hours
   * Shared utility for all charts to ensure consistent query parameters
   * 
   * @param {number} hours - Time span in hours
   * @returns {object} { gran: granularity in seconds, max: max points to fetch }
   */
  function calculateGranularity(hours) {
    if (hours <= 1) { return { gran: 30, max: 150 }; }
    else if (hours <= 24) { return { gran: 60, max: 1500 }; }
    else if (hours <= 168) { return { gran: 300, max: 2100 }; }
    else if (hours <= 720) { return { gran: 900, max: 3000 }; }
    else { return { gran: 3600, max: 3000 }; }
  }

  /**
   * Create a chart instance with standard configuration
   */
  class RDWCChart {
    constructor(config) {
      this.canvasId = config.canvasId;
      this.emptyMessageId = config.emptyMessageId;
      this.type = config.type; // 'sensors', 'ph', 'ec', 'chiller'
      this.title = config.title;
      this.chart = null;
      this.timeWindow = { start: null, end: null };
      this.selectedRange = '24h';
      this.isLiveMode = false;
      this.autoRefreshInterval = null;
      this.lastRefreshTime = 0;
      this.MIN_REFRESH_INTERVAL = 1500; // Keep charts feeling live without spamming the API
      this.livePointAppend = (config.livePointAppend !== false);
      this._refreshSeq = 0;

      // Data cache to prevent flickering
      this.cachedData = null;

      // Callbacks
      this.onDataFetch = config.onDataFetch; // async function(start, end) => data
      this.onRender = config.onRender; // function(chart, data, window) => datasets

      this.init();
    }

    init() {
      const canvas = document.getElementById(this.canvasId);
      if (!canvas) {
        console.error(`[ChartBase] Canvas not found: ${this.canvasId}`);
        return;
      }

      if (typeof Chart === 'undefined') {
        console.error('[ChartBase] Chart.js not loaded');
        return;
      }

      console.log(`[ChartBase] Initializing ${this.type} chart`);

      // Set initial time window to 24h
      this.setTimeRange('24h');

      // Create Chart.js instance
      this.createChart(canvas);

      // Start auto-refresh
      this.startAutoRefresh();

      // Subscribe to live sensor updates
      window.addEventListener('sensors:update', (e) => this.onLiveSensorUpdate(e));
    }

    createChart(canvas) {
      const ctx = canvas.getContext('2d');

      // Destroy any existing chart on this canvas to prevent reuse errors
      if (Chart && Chart.helpers && Chart.helpers.each) {
        Chart.helpers.each(Chart.instances, (instance) => {
          if (instance.canvas === canvas) {
            instance.destroy();
          }
        });
      }

      // Base chart configuration
      this.chart = new Chart(ctx, {
        type: 'line',
        data: { datasets: [] },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          parsing: false,
          normalized: true,
          interaction: { mode: 'nearest', intersect: false },
          plugins: {
            legend: {
              display: true,
              position: 'top',
              labels: { usePointStyle: true, boxWidth: 10, padding: 12 }
            },
            tooltip: {
              enabled: true,
              callbacks: {
                label: (ctx) => this.formatTooltip(ctx)
              }
            }
          },
          scales: {
            x: {
              type: 'time',
              time: {
                tooltipFormat: 'yyyy-MM-dd HH:mm',
                displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'MMM d' }
              },
              ticks: { maxRotation: 0, autoSkip: true },
              grid: { color: 'rgba(148,163,184,0.15)' }
            }
          },
          elements: {
            line: { tension: 0.3 },
            point: { radius: 0, hoverRadius: 4 }
          }
        }
      });

      console.log(`[ChartBase] Chart created: ${this.type}`);
    }

    /**
     * Set time range and update window
     */
    async setTimeRange(range) {
      this.selectedRange = range;
      const now = Date.now();

      if (range === 'grow') {
        // Fetch grow start date
        try {
          const growStart = await this.getGrowStartDate();
          this.timeWindow.start = new Date(growStart).getTime();
          this.timeWindow.end = now;
        } catch (e) {
          console.warn('[ChartBase] Failed to fetch grow start, using 30d fallback:', e);
          this.timeWindow.start = now - TIME_RANGES['1m'];
          this.timeWindow.end = now;
        }
      } else if (range === 'custom') {
        // Custom range set via setCustomRange()
        return;
      } else {
        const spanMs = TIME_RANGES[range] || TIME_RANGES['24h'];
        this.timeWindow.start = now - spanMs;
        this.timeWindow.end = now;
      }

      await this.refresh();
    }

    /**
     * Set custom time range
     */
    async setCustomRange(start, end) {
      this.selectedRange = 'custom';
      this.timeWindow.start = new Date(start).getTime();
      this.timeWindow.end = new Date(end).getTime();
      await this.refresh();
    }

    /**
     * Get grow start date from settings or API
     */
    async getGrowStartDate() {
      // Try settings first
      const growStartDate = window.rdwcSettings?.get('general.grow_start_date');
      if (growStartDate) {
        return new Date(growStartDate + 'T00:00:00').toISOString();
      }

      // Fallback to API
      const resp = await fetch('/api/grow/start');
      if (!resp.ok) throw new Error('Grow start fetch failed');
      const data = await resp.json();
      return data.start;
    }

    /**
     * Refresh chart data
     */
    async refresh(force = false) {
      const now = Date.now();
      if (!force && (now - this.lastRefreshTime < this.MIN_REFRESH_INTERVAL)) {
        console.log(`[ChartBase] ${this.type}: Skipping refresh (too soon)`);
        return;
      }
      this.lastRefreshTime = now;
      const seq = ++this._refreshSeq;

      try {
        const startISO = new Date(this.timeWindow.start).toISOString();
        const endISO = new Date(this.timeWindow.end).toISOString();

        console.log(`[ChartBase] ${this.type}: Fetching data ${startISO} to ${endISO}`);

        // Fetch data via callback
        const data = await this.onDataFetch(startISO, endISO);

        // Discard stale overlapping refreshes; only newest fetch may render.
        if (seq !== this._refreshSeq) {
          console.log(`[ChartBase] ${this.type}: Discarding stale refresh seq ${seq}`);
          return;
        }

        // Cache data for live updates
        this.cachedData = data;

        // Render
        this.render(data);
      } catch (e) {
        console.error(`[ChartBase] ${this.type}: Refresh failed:`, e);
      }
    }

    /**
     * Render chart with data
     */
    render(data) {
      if (!this.chart) return;

      // Call render callback to get datasets
      const datasets = this.onRender(this.chart, data, this.timeWindow);

      // Update chart
      this.chart.data.datasets = datasets;

      // Set fixed time axis
      this.chart.options.scales.x.min = this.timeWindow.start;
      this.chart.options.scales.x.max = this.timeWindow.end;

      // Update y-axis scales (set by render callback via chart.options.scales)

      // Toggle empty message
      const hasData = datasets.some(ds => ds.data && ds.data.length > 0);
      const emptyEl = document.getElementById(this.emptyMessageId);
      if (emptyEl) {
        emptyEl.style.display = hasData ? 'none' : 'block';
      }

      this.chart.update();
      console.log(`[ChartBase] ${this.type}: Rendered ${datasets.length} datasets`);
    }

    /**
     * Format tooltip
     */
    formatTooltip(ctx) {
      const value = ctx.raw?.y;
      if (value == null) return '';

      const label = ctx.dataset.label || '';
      if (this.type === 'circulation' || label.includes('Pump')) {
        return ` ${label}: ${value >= 1 ? 'ON' : 'OFF'}`;
      }
      if (label.includes('pH')) return ` ${label}: ${value.toFixed(2)}`;
      if (label.includes('EC')) return ` ${label}: ${value.toFixed(2)} mS/cm`;
      if (label.includes('Temp')) return ` ${label}: ${value.toFixed(1)} °C`;
      if (label.includes('ml')) return ` ${label}: ${value.toFixed(1)} ml`;
      return ` ${label}: ${value.toFixed(2)}`;
    }

    /**
     * Start auto-refresh
     */
    startAutoRefresh() {
      // Refresh every 5 seconds so target bands, event overlays, and logs stay current.
      this.autoRefreshInterval = setInterval(() => {
        if (!document.hidden) {
          // Slide window when on non-custom ranges or when explicitly in live mode
          if (this.selectedRange !== 'custom' || this.isLiveMode) {
            const now = Date.now();
            const span = this.timeWindow.end - this.timeWindow.start;
            this.timeWindow.start = now - span;
            this.timeWindow.end = now;
          }
          this.refresh();
        }
      }, 5000);

      console.log(`[ChartBase] ${this.type}: Auto-refresh started`);
    }

    /**
     * Stop auto-refresh
     */
    stopAutoRefresh() {
      if (this.autoRefreshInterval) {
        clearInterval(this.autoRefreshInterval);
        this.autoRefreshInterval = null;
        console.log(`[ChartBase] ${this.type}: Auto-refresh stopped`);
      }
    }

    /**
     * Handle live sensor updates
     */
    onLiveSensorUpdate(event) {
      if (!this.livePointAppend) return;

      // Only update if viewing near real-time (within 5 min of now)
      const now = Date.now();
      if (Math.abs(this.timeWindow.end - now) > 5 * 60 * 1000) {
        return; // Not viewing real-time
      }

      const { temp, ec, ph, ts } = event.detail;
      const tsMs = new Date(ts).getTime();

      if (this.selectedRange !== 'custom') {
        const span = this.timeWindow.end - this.timeWindow.start;
        this.timeWindow.end = tsMs;
        this.timeWindow.start = tsMs - span;
        this.chart.options.scales.x.min = this.timeWindow.start;
        this.chart.options.scales.x.max = this.timeWindow.end;
      }

      // Append to datasets
      this.chart.data.datasets.forEach(ds => {
        if (ds.id === 'ph' && ph != null) {
          ds.data.push({ x: tsMs, y: Number(ph) });
          while (ds.data.length && ds.data[0].x < this.timeWindow.start) ds.data.shift();
        } else if (ds.id === 'ec' && ec != null) {
          ds.data.push({ x: tsMs, y: Number(ec) });
          while (ds.data.length && ds.data[0].x < this.timeWindow.start) ds.data.shift();
        } else if (ds.id === 'temp' && temp != null) {
          ds.data.push({ x: tsMs, y: Number(temp) });
          while (ds.data.length && ds.data[0].x < this.timeWindow.start) ds.data.shift();
        }
      });

      this.chart.update('none'); // Fast update without animation
    }

    /**
     * Destroy chart instance
     */
    destroy() {
      this.stopAutoRefresh();
      if (this.chart) {
        this.chart.destroy();
        this.chart = null;
      }
      console.log(`[ChartBase] ${this.type}: Destroyed`);
    }
  }

  /**
   * Create standard time range selector
   */
  function createTimeRangeSelector(selectId, chartInstance) {
    const select = document.getElementById(selectId);
    if (!select) return;

    select.addEventListener('change', async () => {
      const value = select.value;
      if (value !== 'custom') {
        await chartInstance.setTimeRange(value);
      }
    });

    return select;
  }

  /**
   * Create custom range inputs
   */
  function createCustomRangeInputs(fromId, toId, applyId, chartInstance) {
    const fromEl = document.getElementById(fromId);
    const toEl = document.getElementById(toId);
    const applyEl = document.getElementById(applyId);

    if (!fromEl || !toEl || !applyEl) return;

    applyEl.addEventListener('click', async () => {
      if (fromEl.value && toEl.value) {
        await chartInstance.setCustomRange(fromEl.value, toEl.value);
      }
    });
  }

  // Export to global scope
  window.RDWCChart = RDWCChart;
  window.createTimeRangeSelector = createTimeRangeSelector;
  window.createCustomRangeInputs = createCustomRangeInputs;
  window.CHART_COLORS = COLORS;
  window.calculateGranularity = calculateGranularity;

  console.log('[ChartBase] Module loaded');
})();
