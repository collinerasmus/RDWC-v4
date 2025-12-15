/**
 * Trends Tab - System Metrics Visualization
 * 
 * Features:
 * - Selected metrics as chips with inline "+" dropdown
 * - Chart.js with zoom/pan/now/export controls
 * - Matches EC/pH/Sensors styling and dark theme
 * - Default 24h view, adjustable 1-168h range
 */

let chartInstance = null;
let metricsHistory = [];
let selectedMetrics = ["cpu_percent", "memory_percent"];
let timeRangeHours = 24;

const AVAILABLE_METRICS = {
    cpu_percent: { label: "CPU %", color: "#FF6B6B" },
    memory_percent: { label: "Memory %", color: "#4ECDC4" },
    disk_percent: { label: "Disk %", color: "#FFE66D" },
    core_voltage_v: { label: "Core Voltage (V)", color: "#95E1D3" },
    load_1m: { label: "Load (1m)", color: "#A8E6CF" },
    load_5m: { label: "Load (5m)", color: "#FF8B94" },
    load_15m: { label: "Load (15m)", color: "#C7CEEA" },
    net_rx_bytes: { label: "RX (bytes)", color: "#B4E7FF" },
    net_tx_bytes: { label: "TX (bytes)", color: "#FFB7B2" }
};

function initTrendsTab() {
    const container = document.getElementById("trends-container");
    if (!container) return;

    // Build controls area (metric selector + time range)
    const controlsDiv = document.createElement("div");
    controlsDiv.className = "trend-controls";
    controlsDiv.innerHTML = `
        <div style="display: flex; gap: 15px; align-items: center; flex-wrap: wrap; margin-bottom: 15px;">
            <div>
                <label style="font-weight: 600; margin-right: 10px; display: block; margin-bottom: 6px;">Metrics</label>
                <div id="selected-metrics" style="display: flex; gap: 8px; flex-wrap: wrap;"></div>
            </div>
            <div style="margin-left: auto; display: flex; gap: 10px; align-items: center;">
                <label style="font-weight: 600;">Hours:</label>
                <input id="hours-input" type="number" min="1" max="168" value="24" style="width: 60px; padding: 6px; border-radius: 4px; border: 1px solid #444; background: #1a1a1a; color: #e0e0e0;">
                <button id="update-range-btn" class="btn-chip" style="cursor: pointer;">Update</button>
            </div>
        </div>
    `;
    container.appendChild(controlsDiv);

    // Build chart area
    const chartDiv = document.createElement("div");
    chartDiv.style.cssText = "position: relative; height: var(--h-trends, 420px); margin-bottom: 10px; border: 1px solid #333; border-radius: 6px; background: #0d1117; padding: 10px;";
    chartDiv.innerHTML = `<canvas id="trends-chart"></canvas>`;
    container.appendChild(chartDiv);

    // Build controls (zoom/pan/export)
    const ctrlDiv = document.createElement("div");
    ctrlDiv.style.cssText = "display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;";
    ctrlDiv.innerHTML = `
        <button id="trends-zoom-in" class="btn-chip" style="cursor: pointer;">Zoom In</button>
        <button id="trends-zoom-out" class="btn-chip" style="cursor: pointer;">Zoom Out</button>
        <button id="trends-pan-left" class="btn-chip" style="cursor: pointer;">← Pan</button>
        <button id="trends-pan-right" class="btn-chip" style="cursor: pointer;">Pan →</button>
        <button id="trends-now" class="btn-chip" style="cursor: pointer;">Now</button>
        <button id="trends-export" class="btn-chip" style="cursor: pointer;">Export CSV</button>
    `;
    container.appendChild(ctrlDiv);

    // Render selected metrics as chips
    renderSelectedMetrics();

    // Wire events
    document.getElementById("update-range-btn").addEventListener("click", updateTimeRange);
    document.getElementById("trends-zoom-in").addEventListener("click", () => handleChartControl("zoom_in"));
    document.getElementById("trends-zoom-out").addEventListener("click", () => handleChartControl("zoom_out"));
    document.getElementById("trends-pan-left").addEventListener("click", () => handleChartControl("pan_left"));
    document.getElementById("trends-pan-right").addEventListener("click", () => handleChartControl("pan_right"));
    document.getElementById("trends-now").addEventListener("click", () => handleChartControl("now"));
    document.getElementById("trends-export").addEventListener("click", () => handleChartControl("export"));

    // Load initial data
    loadMetricsHistory();
}

function renderSelectedMetrics() {
    const metricsDiv = document.getElementById("selected-metrics");
    metricsDiv.innerHTML = "";

    selectedMetrics.forEach((metric, idx) => {
        const meta = AVAILABLE_METRICS[metric];
        if (!meta) return;

        const chip = document.createElement("div");
        chip.style.cssText = `
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            background: ${meta.color}22;
            border: 1px solid ${meta.color};
            border-radius: 20px;
            color: #e0e0e0;
            font-weight: 500;
            font-size: 0.9rem;
        `;
        chip.innerHTML = `
            <span>${meta.label}</span>
            <button style="background: none; border: none; color: #e0e0e0; cursor: pointer; font-weight: bold; padding: 0; margin: -2px; font-size: 1.1rem;" onclick="removeMetric('${metric}')">×</button>
        `;
        metricsDiv.appendChild(chip);
    });

    // Add "+" button to add more metrics
    const addBtn = document.createElement("div");
    addBtn.style.cssText = `
        position: relative;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        background: #333;
        border: 1px dashed #666;
        border-radius: 20px;
        color: #999;
        cursor: pointer;
        font-weight: 500;
    `;
    addBtn.textContent = "+ Add";
    addBtn.addEventListener("click", () => showMetricDropdown(addBtn));
    metricsDiv.appendChild(addBtn);
}

function removeMetric(metric) {
    selectedMetrics = selectedMetrics.filter(m => m !== metric);
    renderSelectedMetrics();
    loadMetricsHistory();
}

function showMetricDropdown(triggerBtn) {
    // Remove any existing dropdown
    const existing = document.getElementById("metric-dropdown");
    if (existing) {
        existing.remove();
        return;  // Toggle: close if already open
    }

    // Get available metrics (not yet selected)
    const available = Object.entries(AVAILABLE_METRICS).filter(
        ([key]) => !selectedMetrics.includes(key)
    );

    if (available.length === 0) {
        alert("All metrics already selected!");
        return;
    }

    // Create dropdown positioned absolutely relative to viewport
    const dropdown = document.createElement("div");
    dropdown.id = "metric-dropdown";
    dropdown.style.cssText = `
        position: fixed;
        background: #1a1a1a;
        border: 1px solid #444;
        border-radius: 6px;
        min-width: 200px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        z-index: 10000;
    `;

    // Position dropdown below the trigger button
    const rect = triggerBtn.getBoundingClientRect();
    dropdown.style.left = (rect.left) + "px";
    dropdown.style.top = (rect.bottom + 4) + "px";

    available.forEach(([key, meta]) => {
        const option = document.createElement("div");
        option.style.cssText = `
            padding: 10px 14px;
            cursor: pointer;
            color: #e0e0e0;
            border-bottom: 1px solid #2a2a2a;
            transition: background 0.2s;
            user-select: none;
        `;
        option.textContent = meta.label;
        option.addEventListener("mouseenter", () => {
            option.style.background = "#2a3a4a";
        });
        option.addEventListener("mouseleave", () => {
            option.style.background = "transparent";
        });
        option.addEventListener("click", () => {
            selectedMetrics.push(key);
            renderSelectedMetrics();
            loadMetricsHistory();
            dropdown.remove();
            document.removeEventListener("click", closeDropdown);
        });
        dropdown.appendChild(option);
    });

    // Close dropdown when clicking outside
    const closeDropdown = (e) => {
        if (!dropdown.contains(e.target) && !triggerBtn.contains(e.target)) {
            dropdown.remove();
            document.removeEventListener("click", closeDropdown);
        }
    };
    document.addEventListener("click", closeDropdown);

    document.body.appendChild(dropdown);
}

function updateTimeRange() {
    const input = document.getElementById("hours-input");
    timeRangeHours = Math.max(1, Math.min(168, parseInt(input.value) || 24));
    input.value = timeRangeHours;
    loadMetricsHistory();
}

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
        .catch(e => console.error("Failed to fetch metrics:", e));
}

function renderChart() {
    const ctx = document.getElementById("trends-chart");
    if (!ctx) return;

    // Prepare datasets
    const datasets = [];
    selectedMetrics.forEach(metric => {
        const meta = AVAILABLE_METRICS[metric];
        if (!meta) return;

        const data = metricsHistory
            .map(row => ({
                x: new Date(row.ts * 1000),
                y: row[metric]
            }))
            .filter(p => p.y !== null);

        datasets.push({
            label: meta.label,
            data: data,
            borderColor: meta.color,
            backgroundColor: meta.color + "20",
            tension: 0.3,
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointBackgroundColor: meta.color,
            pointBorderColor: "#0d1117"
        });
    });

    // Destroy old chart
    if (chartInstance) {
        chartInstance.destroy();
    }

    // Get min/max values for y-axis scaling
    let minVal = 0, maxVal = 100;
    metricsHistory.forEach(row => {
        selectedMetrics.forEach(metric => {
            const val = row[metric];
            if (val !== null) {
                minVal = Math.min(minVal, val);
                maxVal = Math.max(maxVal, val);
            }
        });
    });
    maxVal = Math.max(maxVal, 100);

    // Create chart
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
                    position: "top",
                    labels: {
                        color: "#e0e0e0",
                        boxWidth: 14,
                        padding: 12,
                        font: { size: 12, weight: "500" }
                    }
                },
                tooltip: {
                    backgroundColor: "rgba(13, 17, 23, 0.95)",
                    titleColor: "#e0e0e0",
                    bodyColor: "#e0e0e0",
                    borderColor: "#444",
                    borderWidth: 1,
                    cornerRadius: 4,
                    padding: 10
                }
            },
            scales: {
                x: {
                    type: "time",
                    time: {
                        unit: "auto",
                        displayFormats: {
                            minute: "HH:mm",
                            hour: "HH:mm",
                            day: "MMM DD"
                        }
                    },
                    grid: {
                        color: "#1a1a1a",
                        drawBorder: false
                    },
                    ticks: {
                        color: "#999",
                        font: { size: 11 }
                    },
                    title: {
                        display: true,
                        text: "Time",
                        color: "#e0e0e0",
                        font: { size: 12, weight: "600" }
                    }
                },
                y: {
                    position: "left",
                    min: Math.max(0, minVal - 10),
                    max: maxVal + 10,
                    grid: {
                        color: "#1a1a1a",
                        drawBorder: false
                    },
                    ticks: {
                        color: "#999",
                        font: { size: 11 }
                    },
                    title: {
                        display: true,
                        text: "Values",
                        color: "#e0e0e0",
                        font: { size: 12, weight: "600" }
                    }
                }
            }
        }
    });
}

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
            loadMetricsHistory();
            break;
        }
        case "export": {
            exportMetricsCSV();
            break;
        }
    }
}

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
