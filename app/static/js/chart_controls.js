/**
 * Unified Chart Controls Module
 * Provides zoom + slider interface for all RDWC charts
 * Zoom levels: 1h, 1d, 1w, 1m, grow
 */
(function() {
  'use strict';

  const ZOOM_LEVELS = [
    { id: '1h', label: '1 Hour', ms: 60 * 60 * 1000 },
    { id: '1d', label: '1 Day', ms: 24 * 60 * 60 * 1000 },
    { id: '1w', label: '1 Week', ms: 7 * 24 * 60 * 60 * 1000 },
    { id: '1m', label: '1 Month', ms: 30 * 24 * 60 * 60 * 1000 },
    { id: 'grow', label: 'Entire Grow', ms: null } // null = special handling
  ];

  /**
   * ChartControls class - manages zoom + slider for a chart
   */
  class ChartControls {
    constructor(options) {
      this.containerId = options.containerId;
      this.onRangeChange = options.onRangeChange; // callback(start, end)
      this.getGrowStartDate = options.getGrowStartDate || (() => null);
      this.getDataExtent = options.getDataExtent || (() => ({ first: null, last: null }));
      
      this.currentZoomIndex = 1; // default to 1d
      this.sliderPosition = 100; // 0-100, 100 = latest data
      this.isLiveMode = true; // true when slider at 100%
      
      this.container = document.getElementById(this.containerId);
      if (!this.container) {
        console.error('[ChartControls] Container not found:', this.containerId);
        return;
      }
      
      this.render();
      this.updateRange();
    }

    render() {
      const zoom = ZOOM_LEVELS[this.currentZoomIndex];
      
      this.container.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:8px 0;">
          <!-- Zoom controls -->
          <div style="display:flex;align-items:center;gap:6px;">
            <span style="font-size:var(--font-sm);color:#9ca3af;font-weight:600;">Zoom:</span>
            <button class="chart-zoom-out btn-secondary btn-compact" title="Zoom out (wider time range)">
              <span style="font-size:16px;font-weight:bold;">−</span>
            </button>
            <span class="chart-zoom-label" style="min-width:90px;text-align:center;font-size:var(--font-sm);font-weight:600;color:#cbd5e1;">${zoom.label}</span>
            <button class="chart-zoom-in btn-secondary btn-compact" title="Zoom in (narrower time range)">
              <span style="font-size:16px;font-weight:bold;">+</span>
            </button>
          </div>
          
          <!-- Slider -->
          <div style="flex:1;min-width:200px;display:flex;align-items:center;gap:8px;">
            <input type="range" class="chart-slider" min="0" max="100" value="100" 
                   style="flex:1;height:6px;background:#374151;border-radius:3px;cursor:pointer;"
                   title="Drag to pan through time">
          </div>
          
          <!-- Now button -->
          <button class="chart-now-btn btn-secondary btn-compact" title="Jump to latest data">Now</button>
          
          <!-- Export button -->
          <button class="chart-export-btn btn-secondary btn-compact" style="margin-left:auto;" title="Export chart data to CSV">Export CSV</button>
        </div>
        
        <!-- Range display -->
        <div class="chart-range-display" style="font-size:var(--font-xs);color:#9ca3af;text-align:center;margin-top:4px;">
          Loading...
        </div>
      `;
      
      // Wire up event listeners
      const zoomOut = this.container.querySelector('.chart-zoom-out');
      const zoomIn = this.container.querySelector('.chart-zoom-in');
      const slider = this.container.querySelector('.chart-slider');
      const nowBtn = this.container.querySelector('.chart-now-btn');
      const exportBtn = this.container.querySelector('.chart-export-btn');
      
      if (zoomOut) zoomOut.addEventListener('click', () => this.zoomOut());
      if (zoomIn) zoomIn.addEventListener('click', () => this.zoomIn());
      if (slider) {
        slider.addEventListener('input', (e) => this.onSliderChange(parseInt(e.target.value, 10)));
        slider.addEventListener('change', (e) => this.onSliderChange(parseInt(e.target.value, 10)));
      }
      if (nowBtn) nowBtn.addEventListener('click', () => this.jumpToNow());
      if (exportBtn) exportBtn.addEventListener('click', () => this.onExport());
      
      this.elements = { zoomOut, zoomIn, slider, nowBtn, exportBtn };
      this.updateUI();
    }

    zoomOut() {
      if (this.currentZoomIndex < ZOOM_LEVELS.length - 1) {
        this.currentZoomIndex++;
        this.updateRange();
      }
    }

    zoomIn() {
      if (this.currentZoomIndex > 0) {
        this.currentZoomIndex--;
        this.updateRange();
      }
    }

    onSliderChange(value) {
      this.sliderPosition = value;
      this.isLiveMode = (value === 100);
      this.updateRange();
    }

    jumpToNow() {
      this.sliderPosition = 100;
      this.isLiveMode = true;
      if (this.elements.slider) this.elements.slider.value = 100;
      this.updateRange();
    }

    updateRange() {
      const zoom = ZOOM_LEVELS[this.currentZoomIndex];
      const now = Date.now();
      let start, end;

      if (zoom.id === 'grow') {
        // Entire grow range
        const growStart = this.getGrowStartDate();
        if (growStart) {
          start = new Date(growStart).getTime();
          end = now;
        } else {
          // Fallback to 30 days if no grow start
          start = now - 30 * 24 * 60 * 60 * 1000;
          end = now;
        }
      } else {
        // Calculate based on slider position
        const extent = this.getDataExtent();
        const firstData = extent.first ? new Date(extent.first).getTime() : now - 90 * 24 * 60 * 60 * 1000;
        const lastData = extent.last ? new Date(extent.last).getTime() : now;
        
        // Total scrollable range (from first data to now)
        const totalRange = lastData - firstData;
        
        // Window size
        const windowSize = zoom.ms;
        
        // Calculate where window should be based on slider (0=oldest, 100=latest)
        const sliderFraction = this.sliderPosition / 100;
        
        // End of window slides from (firstData + windowSize) to lastData
        const maxEnd = lastData;
        const minEnd = Math.min(firstData + windowSize, lastData);
        end = minEnd + (maxEnd - minEnd) * sliderFraction;
        
        // Start is windowSize before end
        start = end - windowSize;
      }

      // Update UI
      this.updateUI();
      this.updateRangeDisplay(start, end);
      
      // Trigger callback
      if (this.onRangeChange) {
        this.onRangeChange(start, end, this.isLiveMode);
      }
    }

    updateUI() {
      const zoom = ZOOM_LEVELS[this.currentZoomIndex];
      
      // Update zoom label
      const label = this.container.querySelector('.chart-zoom-label');
      if (label) label.textContent = zoom.label;
      
      // Update button states
      if (this.elements.zoomOut) {
        this.elements.zoomOut.disabled = (this.currentZoomIndex === ZOOM_LEVELS.length - 1);
      }
      if (this.elements.zoomIn) {
        this.elements.zoomIn.disabled = (this.currentZoomIndex === 0);
      }
      
      // Update Now button appearance
      if (this.elements.nowBtn) {
        this.elements.nowBtn.classList.toggle('active', this.isLiveMode);
        this.elements.nowBtn.style.background = this.isLiveMode 
          ? 'rgba(34,197,94,0.15)' 
          : 'rgba(148,163,184,0.12)';
        this.elements.nowBtn.style.borderColor = this.isLiveMode
          ? 'rgba(34,197,94,0.45)'
          : 'rgba(148,163,184,0.3)';
      }
    }

    updateRangeDisplay(start, end) {
      const display = this.container.querySelector('.chart-range-display');
      if (!display) return;
      
      const formatDate = (ts) => {
        const d = new Date(ts);
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const hours = String(d.getHours()).padStart(2, '0');
        const mins = String(d.getMinutes()).padStart(2, '0');
        return `${month}/${day} ${hours}:${mins}`;
      };
      
      display.textContent = `${formatDate(start)} — ${formatDate(end)}`;
    }

    onExport() {
      // Override this method with your export logic
      console.log('[ChartControls] Export clicked - override onExport method');
    }

    // Public method to refresh when in live mode
    tick() {
      if (this.isLiveMode) {
        this.updateRange();
      }
    }
  }

  // Export to window
  window.ChartControls = ChartControls;
})();
