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
      console.log('[ChartControls] Constructor called with containerId:', options.containerId);
      this.containerId = options.containerId;
      this.onRangeChange = options.onRangeChange; // callback(start, end)
      this.getGrowStartDate = options.getGrowStartDate || (() => null);
      this.getDataExtent = options.getDataExtent || (() => ({ first: null, last: null }));
      
      this.currentZoomIndex = 1; // default to 1d
      this.sliderPosition = 100; // 0-100, 100 = latest data
      this.isLiveMode = true; // true when slider at 100%
      this.currentStart = null; // last computed start ts
      this.currentEnd = null;   // last computed end ts
      
      this.container = document.getElementById(this.containerId);
      if (!this.container) {
        console.error('[ChartControls] Container not found:', this.containerId);
        return;
      }
      console.log('[ChartControls] Container found, calling render()');
      
      this.render();
      this.updateRange();
      console.log('[ChartControls] Initialization complete');
    }

    render() {
      const zoom = ZOOM_LEVELS[this.currentZoomIndex];
      console.log('[ChartControls] render() called for container:', this.containerId, 'with zoom level:', zoom.label);
      
      this.container.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:8px 0;">
          <!-- Zoom controls -->
          <div style="display:flex;align-items:center;gap:6px;">
            <span style="font-size:var(--font-sm);color:#9ca3af;font-weight:600;">Zoom:</span>
            <button class="chart-zoom-out btn-secondary btn-compact" style="background:#334155;color:#e2e8f0;border:1px solid #1f2937;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;" title="Zoom out (wider time range)">
              <span style="font-size:16px;font-weight:bold;">−</span>
            </button>
            <span class="chart-zoom-label" style="min-width:90px;text-align:center;font-size:var(--font-sm);font-weight:600;color:#cbd5e1;">${zoom.label}</span>
            <button class="chart-zoom-in btn-secondary btn-compact" style="background:#334155;color:#e2e8f0;border:1px solid #1f2937;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;" title="Zoom in (narrower time range)">
              <span style="font-size:16px;font-weight:bold;">+</span>
            </button>
          </div>
          
          <!-- Pan controls -->
          <div style="display:flex;align-items:center;gap:6px;">
            <span style="font-size:var(--font-sm);color:#9ca3af;font-weight:600;">Pan:</span>
            <button class="chart-pan-left btn-secondary btn-compact" style="background:#334155;color:#e2e8f0;border:1px solid #1f2937;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;" title="Pan backward in time">
              <span style="font-size:16px;font-weight:bold;">←</span>
            </button>
            <button class="chart-pan-right btn-secondary btn-compact" style="background:#334155;color:#e2e8f0;border:1px solid #1f2937;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;" title="Pan forward in time">
              <span style="font-size:16px;font-weight:bold;">→</span>
            </button>
            <button class="chart-now-btn btn-secondary btn-compact" style="background:#334155;color:#e2e8f0;border:1px solid #1f2937;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;" title="Jump to latest data">Now</button>
          </div>
          
          <!-- Export button -->
          <button class="chart-export-btn btn-secondary btn-compact" style="margin-left:auto;background:#334155;color:#e2e8f0;border:1px solid #1f2937;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;" title="Export chart data to CSV">Export CSV</button>
        </div>
        
        <!-- Range display -->
        <div class="chart-range-display" style="font-size:var(--font-xs);color:#9ca3af;text-align:center;margin-top:4px;">
          Loading...
        </div>
      `;
      
      // Wire up event listeners
      const zoomOut = this.container.querySelector('.chart-zoom-out');
      const zoomIn = this.container.querySelector('.chart-zoom-in');
      const panLeft = this.container.querySelector('.chart-pan-left');
      const panRight = this.container.querySelector('.chart-pan-right');
      const nowBtn = this.container.querySelector('.chart-now-btn');
      const exportBtn = this.container.querySelector('.chart-export-btn');
      
      console.log('[ChartControls] Buttons found - zoomOut:', !!zoomOut, 'zoomIn:', !!zoomIn, 'panLeft:', !!panLeft, 'panRight:', !!panRight, 'nowBtn:', !!nowBtn, 'exportBtn:', !!exportBtn);
      console.log('[ChartControls] Container innerHTML length:', this.container.innerHTML.length);
      console.log('[ChartControls] Container style:', this.container.getAttribute('style'));
      
      if (zoomOut) zoomOut.addEventListener('click', () => this.zoomOut());
      if (zoomIn) zoomIn.addEventListener('click', () => this.zoomIn());
      if (panLeft) panLeft.addEventListener('click', () => this.panLeft());
      if (panRight) panRight.addEventListener('click', () => this.panRight());
      if (nowBtn) nowBtn.addEventListener('click', () => this.jumpToNow());
      if (exportBtn) exportBtn.addEventListener('click', () => this.onExport());
      
      this.elements = { zoomOut, zoomIn, panLeft, panRight, nowBtn, exportBtn };
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

    panLeft() {
      // Pan backward by exactly one current zoom window (no slider rounding)
      const zoom = ZOOM_LEVELS[this.currentZoomIndex];
      if (zoom.id === 'grow') return; // no pan for full grow view

      const now = Date.now();
      const extent = this.getDataExtent();
      const firstData = extent.first ? new Date(extent.first).getTime() : now - 90 * 24 * 60 * 60 * 1000;
      const lastData = extent.last ? new Date(extent.last).getTime() : now;
      const windowSize = zoom.ms;

      if (this.currentStart == null || this.currentEnd == null) {
        this.updateRange();
      }

      let newStart = Math.max(firstData, this.currentStart - windowSize);
      let newEnd = newStart + windowSize;
      if (newEnd > lastData) {
        newEnd = lastData;
        newStart = Math.max(firstData, newEnd - windowSize);
      }
      this.applyRange(newStart, newEnd, false);
    }

    panRight() {
      // Pan forward by exactly one current zoom window (no slider rounding)
      const zoom = ZOOM_LEVELS[this.currentZoomIndex];
      if (zoom.id === 'grow') return; // no pan for full grow view

      const now = Date.now();
      const extent = this.getDataExtent();
      const firstData = extent.first ? new Date(extent.first).getTime() : now - 90 * 24 * 60 * 60 * 1000;
      const lastData = extent.last ? new Date(extent.last).getTime() : now;
      const windowSize = zoom.ms;

      if (this.currentStart == null || this.currentEnd == null) {
        this.updateRange();
      }

      let newEnd = Math.min(lastData, this.currentEnd + windowSize);
      let newStart = newEnd - windowSize;
      if (newStart < firstData) {
        newStart = firstData;
        newEnd = Math.min(lastData, newStart + windowSize);
      }
      const isLive = (newEnd >= lastData);
      this.applyRange(newStart, newEnd, isLive);
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

      // Persist and update UI
      this.currentStart = start;
      this.currentEnd = end;
      this.updateUI();
      this.updateRangeDisplay(start, end);
      // Trigger callback
      if (this.onRangeChange) {
        this.onRangeChange(start, end, this.isLiveMode);
      }
    }

    // Apply a specific range directly (used by pan operations)
    applyRange(start, end, isLive = false) {
      this.isLiveMode = !!isLive;
      this.currentStart = start;
      this.currentEnd = end;
      // Sync slider for UI states (best effort)
      const zoom = ZOOM_LEVELS[this.currentZoomIndex];
      if (zoom.id !== 'grow') {
        const now = Date.now();
        const extent = this.getDataExtent();
        const firstData = extent.first ? new Date(extent.first).getTime() : now - 90 * 24 * 60 * 60 * 1000;
        const lastData = extent.last ? new Date(extent.last).getTime() : now;
        const windowSize = zoom.ms;
        const maxEnd = lastData;
        const minEnd = Math.min(firstData + windowSize, lastData);
        const clampedEnd = Math.max(minEnd, Math.min(maxEnd, end));
        const frac = (clampedEnd - minEnd) / (maxEnd - minEnd || 1);
        this.sliderPosition = Math.max(0, Math.min(100, Math.round(frac * 100)));
      }
      this.updateUI();
      this.updateRangeDisplay(start, end);
      if (this.onRangeChange) {
        this.onRangeChange(start, end, this.isLiveMode);
      }
    }

    updateUI() {
      const zoom = ZOOM_LEVELS[this.currentZoomIndex];
      const now = Date.now();
      const extent = this.getDataExtent ? this.getDataExtent() : { first: null, last: null };
      const firstData = extent.first ? new Date(extent.first).getTime() : (now - 90 * 24 * 60 * 60 * 1000);
      const lastData = extent.last ? new Date(extent.last).getTime() : now;
      const epsilon = 1000; // 1s tolerance at live edge

      // Update zoom label
      const label = this.container.querySelector('.chart-zoom-label');
      if (label) label.textContent = zoom.label;
      
      // Update zoom button states
      if (this.elements.zoomOut) {
        this.elements.zoomOut.disabled = (this.currentZoomIndex === ZOOM_LEVELS.length - 1);
      }
      if (this.elements.zoomIn) {
        this.elements.zoomIn.disabled = (this.currentZoomIndex === 0);
      }
      
      // Update pan button states
      if (this.elements.panLeft) {
        const atLeftEdge = (this.currentStart != null) ? (this.currentStart <= firstData + epsilon) : (this.sliderPosition <= 0);
        this.elements.panLeft.disabled = atLeftEdge;
      }
      if (this.elements.panRight) {
        const atRightEdge = (this.currentEnd != null) ? (this.currentEnd >= lastData - epsilon) : (this.sliderPosition >= 100);
        this.elements.panRight.disabled = atRightEdge;
      }
      
      // Update Now button appearance
      if (this.elements.nowBtn) {
        this.elements.nowBtn.disabled = this.isLiveMode;
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
