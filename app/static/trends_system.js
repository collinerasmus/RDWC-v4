/**
 * Trends Tab - System Metrics Visualization
 * 
 * Features:
 * - Multi-select metric dropdown
 * - '+' button to add metrics to chart
 * - Chart.js with auto-scaling and controls
 * - Reuses chart_controls.js (zoom/pan/now/export)
 * - Default 24h view, selectable 1-168h range
 */

// Chart instance
let systemMetricsChart = null;
let chartInstance = null;

// Available system metrics
const AVAILABLE_METRICS = {
    cpu_percent: { label: "CPU %", color: "#FF6384", yAxisId: "y_left" },
    memory_percent: { label: "Memory %", color: "#36A2EB", yAxisId: "y_left" },
    disk_percent: { label: "Disk %", color: "#FFCE56", yAxisId: "y_left" },
    core_voltage_v: { label: "Core Voltage (V)", color: "#4BC0C0", yAxisId: "y_right" },
    load_1m: { label: "Load (1m)", color: "#9966FF", yAxisId: "y_left" },
    load_5m: { label: "Load (5m)", color: "#FF9F40", yAxisId: "y_left" },
    load_15m: { label: "Load (15m)", color: "#C9CBCF", yAxisId: "y_left" },
    net_rx_bytes: { label: "RX (bytes)", color: "#00FF00", yAxisId: "y_right" },
    net_tx_bytes: { label: "TX (bytes)", color: "#FF00FF", yAxisId: "y_right" }
};

// Current state
let selectedMetrics = ["cpu_percent", "memory_percent"];  // Default metrics
let metricsHistory = [];
let timeRangeHours = 24;

/**
 * Initialize Trends tab DOM and event handlers
 */
function initTrendsTab() {
    const trendsContainer = document.getElementById("trends-container");
    if (!trendsContainer) return;

    // Build KPI space with metric selector
    const kpiArea = document.createElement("div");
    kpiArea.className = "kpi-area";
    kpiArea.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px; padding: 10px; background: #f9f9f9; border-radius: 4px;">
            <label for="metric-selector" style="font-weight: bold;">Metrics:</label>
            <select id="metric-selector" multiple size="3" style="flex: 1; min-width: 200px;">
            </select>
            <button id="add-metric-btn" class="btn btn-sm btn-primary" style="white-space: nowrap;">
                + Add Selected
            </button>
            <div id="time-range-controls" style="margin-left: 20px;">
                <label for="hours-input" style="font-weight: bold;">Hours:</label>
                <input id="hours-input" type="number" min="1" max="168" value="24" style="width: 60px;">
                <button id="update-range-btn" class="btn btn-sm btn-secondary" style="white-space: nowrap;">Update</button>
            </div>
        </div>
    `;
    trendsContainer.appendChild(kpiArea);

    // Populate metric selector
    const selector = document.getElementById("metric-selector");
    Object.entries(AVAILABLE_METRICS).forEach(([key, meta]) => {
        const option = document.createElement("option");
        option.value = key;
        option.textContent = meta.label;
        option.selected = selectedMetrics.includes(key);
        selector.appendChild(option);
    });

    // Event handlers
    document.getElementById("add-metric-btn").addEventListener("click", addSelectedMetric);
    document.getElementById("update-range-btn").addEventListener("click", updateTimeRange);

    // Create chart container
    const chartArea = document.createElement("div");
    chartArea.className = "chart-area";
    chartArea.style.cssText = "position: relative; height: 420px; margin-top: 10px; border: 1px solid #ddd; border-radius: 4px; padding: 10px;";
    chartArea.innerHTML = `
        <canvas id="trends-chart"></canvas>
        <div id="chart-controls" style="margin-top: 10px; display: flex; gap: 10px; justify-content: center;">
            <button id="trends-zoom-in" class="btn btn-sm btn-info">Zoom In</button>
            <button id="trends-zoom-out" class="btn btn-sm btn-info">Zoom Out</button>
            <button id="trends-pan-left" class="btn btn-sm btn-info">← Pan</button>
            <button id="trends-pan-right" class="btn btn-sm btn-info">Pan →</button>
            <button id="trends-now" class="btn btn-sm btn-warning">Now</button>
            <button id="trends-export" class="btn btn-sm btn-success">Export CSV</button>
        </div>
    `;
    trendsContainer.appendChild(chartArea);

    // Wire up chart controls
    const controls = {
        zoom_in: document.getElementById("trends-zoom-in"),
        zoom_out: document.getElementById("trends-zoom-out"),
        pan_left: document.getElementById("trends-pan-left"),
        pan_right: document.getElementById("trends-pan-right"),
        now: document.getElementById("trends-now"),
        export: document.getElementById("trends-export")
    };

    Object.entries(controls).forEach(([action, btn]) => {
        if (btn) {
            btn.addEventListener("click", () => handleChartControl(action));
        }
    });

    // Initial chart load
    loadMetricsHistory();
}

/**
 * Add selected metric(s) from dropdown to chart
 */
function addSelectedMetric() {
    const selector = document.getElementById("metric-selector");
    const selected = Array.from(selector.selectedOptions).map(o => o.value);
    
    selected.forEach(metric => {
        if (!selectedMetrics.includes(metric)) {
            selectedMetrics.push(metric);
        }
    });

    // Update selector to reflect current selection
    Array.from(selector.options).forEach(option => {
        option.selected = selectedMetrics.includes(option.value);
    });

    // Reload chart with new metrics
    loadMetricsHistory();
}

/**
 * Update time range and reload
 */
function updateTimeRange() {
    const hoursInput = document.getElementById("hours-input");
    const hours = Math.max(1, Math.min(168, parseInt(hoursInput.value) || 24));
    hoursInput.value = hours;
    timeRangeHours = hours;
    loadMetricsHistory();
}

/**
 * Fetch metrics history from API and render chart
 */
function loadMetricsHistory() {
    if (selectedMetrics.length === 0) {
        console.warn("No metrics selected");
        return;
    }

    const metricsParam = selectedMetrics.join(",");
    const url = `/api/system/metrics/history?metrics=${encodeURIComponent(metricsParam)}&hours=${timeRangeHours}`;

    fetch(url)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                console.error("API error:", data.error);
                return;
            }
            metricsHistory = data.data;
            renderChart();
        })
        .catch(e => console.error("Failed to fetch metrics history:", e));
}

/**
 * Render Chart.js chart with selected metrics
 */
function renderChart() {
    const ctx = document.getElementById("trends-chart");
    if (!ctx) return;

    // Prepare datasets
    const datasets = [];
    selectedMetrics.forEach(metric => {
        const meta = AVAILABLE_METRICS[metric];
        if (!meta) return;

        const data = metricsHistory.map(row => ({
            x: new Date(row.ts * 1000),
            y: row[metric]
        })).filter(p => p.y !== null);

        datasets.push({
            label: meta.label,
            data: data,
            borderColor: meta.color,
            backgroundColor: meta.color + "20",  // Semi-transparent
            tension: 0.3,
            yAxisId: meta.yAxisId,
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4
        });
    });

    // Destroy old chart
    if (chartInstance) {
        chartInstance.destroy();
    }

    // Create new chart
    chartInstance = new Chart(ctx, {
        type: "line",
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: "index",
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    position: "top"
                },
                title: {
                    display: true,
                    text: `System Metrics (${timeRangeHours}h)`
                }
            },
            scales: {
                x: {
                    type: "time",
                    time: {
                        unit: "minute",
                        displayFormats: {
                            minute: "HH:mm",
                            hour: "HH:mm",
                            day: "MMM DD"
                        }
                    },
                    title: {
                        display: true,
                        text: "Time"
                    }
                },
                y_left: {
                    position: "left",
                    title: {
                        display: true,
                        text: "CPU/Memory/Disk % / Load"
                    },
                    min: 0,
                    max: 100
                },
                y_right: {
                    position: "right",
                    title: {
                        display: true,
                        text: "Voltage (V) / Network (bytes)"
                    }
                }
            }
        }
    });
}

/**
 * Handle chart control actions (zoom, pan, export, etc.)
 */
function handleChartControl(action) {
    if (!chartInstance) return;

    const xScale = chartInstance.scales.x;
    if (!xScale) return;

    switch (action) {
        case "zoom_in": {
            const range = xScale.max - xScale.min;
            const center = (xScale.min + xScale.max) / 2;
            xScale.min = center - range / 4;
            xScale.max = center + range / 4;
            chartInstance.update();
            break;
        }
        case "zoom_out": {
            const range = xScale.max - xScale.min;
            const center = (xScale.min + xScale.max) / 2;
            xScale.min = center - range;
            xScale.max = center + range;
            chartInstance.update();
            break;
        }
        case "pan_left": {
            const range = xScale.max - xScale.min;
            xScale.min -= range * 0.25;
            xScale.max -= range * 0.25;
            chartInstance.update();
            break;
        }
        case "pan_right": {
            const range = xScale.max - xScale.min;
            xScale.min += range * 0.25;
            xScale.max += range * 0.25;
            chartInstance.update();
            break;
        }
        case "now": {
            // Reset to latest data
            loadMetricsHistory();
            break;
        }
        case "export": {
            exportMetricsCSV();
            break;
        }
    }
}

/**
 * Export metrics as CSV
 */
function exportMetricsCSV() {
    if (metricsHistory.length === 0) {
        alert("No data to export");
        return;
    }

    const headers = ["timestamp", ...selectedMetrics];
    const rows = metricsHistory.map(row => [
        new Date(row.ts * 1000).toISOString(),
        ...selectedMetrics.map(m => row[m] !== null ? row[m] : "")
    ]);

    const csv = [
        headers.join(","),
        ...rows.map(r => r.join(","))
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `trends_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
}

// Init on page load
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTrendsTab);
} else {
    initTrendsTab();
}
