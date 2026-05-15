/**
 * Stacked Overview Chart — pH / EC / Temperature
 *
 * Three separate Chart.js canvases sharing a synchronised X axis.
 * Features:
 *  - Soft filled target band (low→high) per metric
 *  - Lights-on periods rendered as a warm yellow background tint (plugin)
 *  - Dose events rendered as vertical hairlines (plugin) — pH on pH row, EC doses on EC row
 *  - No dual Y-axes, no legend clutter, no averaging
 *  - Axis cache keyed on zoom-bucket so live-refresh never causes scale jumps
 */
(function () {
  'use strict';

  if (window.__overviewCombinedChartModuleLoaded) return;
  window.__overviewCombinedChartModuleLoaded = true;

  // ── Formatting ──────────────────────────────────────────────────────────────
  function fmt(ts) {
    const d = new Date(ts);
    return (
      String(d.getMonth() + 1).padStart(2, '0') + '/' +
      String(d.getDate()).padStart(2, '0') + ' ' +
      String(d.getHours()).padStart(2, '0') + ':' +
      String(d.getMinutes()).padStart(2, '0')
    );
  }

  function setRangeLabel(s, e) {
    const el = document.getElementById('overview-combined-range');
    if (el) el.textContent = fmt(s) + ' — ' + fmt(e);
  }

  // ── Lights helpers ───────────────────────────────────────────────────────────
  function buildLightsIntervals(events, winStart, winEnd) {
    if (!Array.isArray(events) || !events.length) return [];
    const sorted = events
      .map(ev => ({ ts: new Date(ev.ts).getTime(), on: !!ev.final }))
      .sort((a, b) => a.ts - b.ts);

    const prior = [...sorted].filter(ev => ev.ts <= winStart).pop();
    let currentOn = prior ? prior.on : false;
    let currentStart = winStart;
    const intervals = [];

    for (const ev of sorted.filter(ev => ev.ts > winStart && ev.ts < winEnd)) {
      if (ev.on && !currentOn) {
        currentStart = ev.ts;
        currentOn = true;
      } else if (!ev.on && currentOn) {
        intervals.push([currentStart, ev.ts]);
        currentOn = false;
      }
    }
    if (currentOn) intervals.push([currentStart, winEnd]);
    return intervals;
  }

  // ── Axis range helper ───────────────────────────────────────────────────────
  function adaptiveRange(values, bandLow, bandHigh, windowHours, opts) {
    const fin = (values || []).filter(Number.isFinite);
    const hasBand = Number.isFinite(bandLow) && Number.isFinite(bandHigh) && bandHigh > bandLow;
    const floor = fin.length ? Math.min(...fin) : (hasBand ? bandLow : 0);
    const ceil  = fin.length ? Math.max(...fin) : (hasBand ? bandHigh : 1);
    const baseMin = hasBand ? Math.min(floor, bandLow)  : floor;
    const baseMax = hasBand ? Math.max(ceil,  bandHigh) : ceil;

    let minSpan, minPad;
    if      (windowHours <= 1.5)  { minSpan = opts.hourSpan;  minPad = opts.hourPad;  }
    else if (windowHours <= 24)   { minSpan = opts.daySpan;   minPad = opts.dayPad;   }
    else if (windowHours <= 168)  { minSpan = opts.weekSpan;  minPad = opts.weekPad;  }
    else                          { minSpan = opts.monthSpan; minPad = opts.monthPad; }

    const dataSpan = Math.max(baseMax - baseMin, 0);
    const bandSpan = hasBand ? (bandHigh - bandLow) : 0;
    const desiredForBand = bandSpan > 0 ? bandSpan / (opts.bandRatio || 0.5) : 0;
    const padding = Math.max(dataSpan * 0.10, minPad);
    let span = Math.max((baseMax - baseMin) + padding * 2, minSpan, desiredForBand);
    let mid  = (baseMin + baseMax) / 2;
    if (hasBand) mid = (mid + (bandLow + bandHigh) / 2) / 2;

    let min = mid - span / 2;
    let max = mid + span / 2;
    if (opts.zeroFloor && min < 0) { max += Math.abs(min); min = 0; }
    return { min, max };
  }

  // ── Chart.js plugins ────────────────────────────────────────────────────────

  /** Draw warm-yellow tint over lights-on intervals */
  function makeLightsPlugin(getIntervals) {
    return {
      id: 'lightsBackground',
      beforeDraw(chart) {
        const intervals = getIntervals();
        if (!intervals.length) return;
        const { ctx, chartArea, scales } = chart;
        if (!chartArea || !scales.x) return;
        ctx.save();
        ctx.fillStyle = 'rgba(253, 224, 71, 0.08)';
        for (const [on, off] of intervals) {
          const x0 = scales.x.getPixelForValue(on);
          const x1 = scales.x.getPixelForValue(off);
          const left  = Math.max(chartArea.left,  Math.min(x0, x1));
          const right = Math.min(chartArea.right, Math.max(x0, x1));
          if (right > left) ctx.fillRect(left, chartArea.top, right - left, chartArea.bottom - chartArea.top);
        }
        ctx.restore();
      }
    };
  }

  /** Draw vertical hairlines at each dose event timestamp */
  function makeDosePlugin(getEvents, color) {
    return {
      id: 'doseHairlines_' + color.replace(/[^a-z0-9]/gi, '_'),
      beforeDatasetsDraw(chart) {
        const evs = getEvents();
        if (!evs.length) return;
        const { ctx, chartArea, scales } = chart;
        if (!chartArea || !scales.x) return;
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.55;
        for (const { ts } of evs) {
          const x = scales.x.getPixelForValue(ts);
          if (x < chartArea.left || x > chartArea.right) continue;
          ctx.beginPath();
          ctx.moveTo(x, chartArea.top);
          ctx.lineTo(x, chartArea.bottom);
          ctx.stroke();
        }
        ctx.restore();
      }
    };
  }

  // ── Chart factory ────────────────────────────────────────────────────────────
  function makeChart(canvasId, yLabel, yColor, showXAxis, extraPlugins) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    // Destroy any stale instance
    const existing = Chart.getChart(canvasId);
    if (existing) { try { existing.destroy(); } catch (_) {} }

    const tickFont = { size: 10 };
    return new Chart(canvas, {
      type: 'line',
      data: { datasets: [] },
      options: {
        animation: false,
        parsing: false,
        normalized: true,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend:  { display: false },
          decimation: {
            enabled: true,
            algorithm: 'lttb',
            samples: 240,
            threshold: 500
          },
          tooltip: {
            enabled: true,
            backgroundColor: 'rgba(15,23,42,0.92)',
            titleColor: '#e2e8f0',
            bodyColor: '#94a3b8',
            padding: 8,
            cornerRadius: 6,
            filter: (item) => !item.dataset.label.startsWith('_')
          }
        },
        scales: {
          x: {
            type: 'time',
            time: {
              displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'MM/dd' }
            },
            ticks: {
              display: showXAxis,
              color: '#6b7280',
              font: tickFont,
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 10
            },
            grid: { color: 'rgba(255,255,255,0.04)', drawTicks: showXAxis },
            border: { display: false }
          },
          y: {
            position: 'left',
            title: { display: true, text: yLabel, color: yColor, font: { size: 9 } },
            ticks: { color: '#6b7280', font: tickFont, maxTicksLimit: 4, padding: 2 },
            grid: { color: 'rgba(255,255,255,0.06)' },
            border: { display: false }
          }
        }
      },
      plugins: extraPlugins || []
    });
  }

  // ── Band dataset helpers ─────────────────────────────────────────────────────
  function bandDatasets(low, high, start, end, r, g, b) {
    if (!Number.isFinite(low) || !Number.isFinite(high)) return [];
    return [
      {
        label: '_bandLow',
        data: [{ x: start, y: low }, { x: end, y: low }],
        borderColor: 'transparent',
        borderWidth: 0,
        pointRadius: 0,
        fill: '+1',
        backgroundColor: 'rgba(' + r + ',' + g + ',' + b + ',0.13)',
        order: 0
      },
      {
        label: '_bandHigh',
        data: [{ x: start, y: high }, { x: end, y: high }],
        borderColor: 'rgba(' + r + ',' + g + ',' + b + ',0.30)',
        borderWidth: 1,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false,
        order: 0
      }
    ];
  }

  function lineDataset(label, data, color) {
    return {
      label,
      data,
      borderColor: color,
      backgroundColor: color,
      borderWidth: 1.5,
      pointRadius: 0,
      spanGaps: true,
      order: 1
    };
  }

  function downsampleEvenly(points, maxPoints) {
    if (!Array.isArray(points)) return [];
    if (!Number.isFinite(maxPoints) || maxPoints < 2 || points.length <= maxPoints) return points;
    const step = Math.ceil(points.length / maxPoints);
    const out = [];
    for (let i = 0; i < points.length; i += step) out.push(points[i]);
    const last = points[points.length - 1];
    if (out[out.length - 1] !== last) out.push(last);
    return out.length > maxPoints ? out.slice(0, maxPoints) : out;
  }

  function fetchJsonWithTimeout(url, fallback, timeoutMs) {
    const timeout = Number.isFinite(timeoutMs) ? timeoutMs : 7000;
    const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    const timer = setTimeout(function () {
      try { if (ctrl) ctrl.abort(); } catch (_) {}
    }, timeout);

    const options = { cache: 'no-store' };
    if (ctrl) options.signal = ctrl.signal;

    return fetch(url, options)
      .then(function (res) {
        if (!res.ok) return fallback;
        return res.json().catch(function () { return fallback; });
      })
      .catch(function () { return fallback; })
      .finally(function () { clearTimeout(timer); });
  }

  // ── Main init ────────────────────────────────────────────────────────────────
  function init() {
    if (typeof Chart === 'undefined') {
      console.warn('[Overview Stacked] Chart.js not loaded');
      return;
    }

    // Shared plugin state (closures update these arrays in place)
    let lightsIntervals = [];
    let phDoseEvs       = [];
    let ecDoseEvs       = [];

    const lightsPlugin = makeLightsPlugin(() => lightsIntervals);
    const phDosePlugin = makeDosePlugin(() => phDoseEvs, 'rgba(251,191,36,1)');
  const ecDosePlugin = makeDosePlugin(() => ecDoseEvs, 'rgba(249,115,22,1)');

    const phChart   = makeChart('overviewChartPh',   'pH',       '#93c5fd', false, [lightsPlugin, phDosePlugin]);
    const ecChart   = makeChart('overviewChartEc',   'EC mS/cm', '#6ee7b7', false, [lightsPlugin, ecDosePlugin]);
    const tempChart = makeChart('overviewChartTemp', '°C',       '#f87171', true,  [lightsPlugin]);

    if (!phChart || !ecChart || !tempChart) {
      console.warn('[Overview Stacked] One or more canvas elements not found');
      return;
    }

    let timeWindow = { start: Date.now() - 24 * 3600000, end: Date.now() };
    let liveTimer  = null;
    let liveSpanMs = 24 * 3600000;
    const axisCache = { key: null, ph: null, ec: null, temp: null };

    // ── Fetch ──────────────────────────────────────────────────────────────────
    async function fetchData(startISO, endISO) {
      const spanMs = new Date(endISO) - new Date(startISO);
      const hours  = spanMs / 3600000;
      let gran, max;
      if      (hours <= 1)    { gran = 10;   max = 600;  }
      else if (hours <= 6)    { gran = 30;   max = 900;  }
      else if (hours <= 24)   { gran = 60;   max = 1200; }
      else if (hours <= 168)  { gran = 300;  max = 1500; }
      else if (hours <= 720)  { gran = 900;  max = 1400; }
      else if (hours <= 2160) { gran = 1800; max = 1200; }
      else                    { gran = 3600; max = 1000; }

      const q = new URLSearchParams({ from: startISO, to: endISO, gran: String(gran), max: String(max) });
      // Keep long-range calls bounded; trends is primary, others are optional enrichments.
      const phDoseLimit = hours <= 24 ? 2000 : (hours <= 168 ? 5000 : (hours <= 720 ? 10000 : 20000));
      const ecDoseLimit = hours <= 24 ? 2000 : (hours <= 168 ? 5000 : (hours <= 720 ? 10000 : 20000));
      const relayLimit  = hours <= 24 ? 1000 : (hours <= 168 ? 2000 : 3000);
      const isLongRange = hours > 168;

      const [trends, phDose, ecDose, settings, ecStatus, tempStatus, phStatus, lightsEvents] = await Promise.all([
        fetchJsonWithTimeout('/api/trends?' + q, { series: {} }, isLongRange ? 25000 : 10000),
        fetchJsonWithTimeout('/api/ph/dose_log?start=' + encodeURIComponent(startISO) + '&end=' + encodeURIComponent(endISO) + '&limit=' + phDoseLimit, [], isLongRange ? 5000 : 7000),
        fetchJsonWithTimeout('/api/ec/dose_log?start=' + encodeURIComponent(startISO) + '&end=' + encodeURIComponent(endISO) + '&limit=' + ecDoseLimit, { events: [] }, isLongRange ? 5000 : 7000),
        fetchJsonWithTimeout('/api/settings', {}, 6000),
        fetchJsonWithTimeout('/api/ec/status', {}, 6000),
        fetchJsonWithTimeout('/api/temperature/status', {}, 6000),
        fetchJsonWithTimeout('/api/ph/status', {}, 6000),
        fetchJsonWithTimeout('/api/relays/events?name=lights&last=' + relayLimit, [], isLongRange ? 5000 : 7000),
      ]);

      return {
        trends,
        phDose,
        ecDose: { events: ecDose },
        settings,
        ecStatus,
        tempStatus,
        phStatus,
        lightsEvents
      };
    }

    // ── Render ─────────────────────────────────────────────────────────────────
    function render(data, win) {
      const durationHours = (win.end - win.start) / 3600000;
      const windowHours   = Math.max(1 / 60, durationHours);

      const pointCap = durationHours <= 24 ? 1400
        : durationHours <= 168 ? 1200
        : durationHours <= 720 ? 900
        : durationHours <= 2160 ? 700
        : 500;


      const lightsCap = durationHours <= 168 ? 900
        : durationHours <= 720 ? 600
        : 400;

      const ph   = downsampleEvenly((data.trends?.series?.ph   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) })), pointCap);
      const ec   = downsampleEvenly((data.trends?.series?.ec   || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) })), pointCap);
      const temp = downsampleEvenly((data.trends?.series?.temp || []).map(p => ({ x: p.ts * 1000, y: Number(p.value) })), pointCap);

      lightsIntervals = downsampleEvenly(buildLightsIntervals(data.lightsEvents, win.start, win.end), lightsCap);
      phDoseEvs = (data.phDose || [])
        .map(e => ({ ts: new Date(e.ts).getTime() }))
        .filter(e => e.ts >= win.start && e.ts <= win.end)
        .sort((a, b) => a.ts - b.ts);
      ecDoseEvs = (Array.isArray(data.ecDose?.events) ? data.ecDose.events : [])
        .filter(e => !e.blocked_by)
        .map(e => ({ ts: new Date(e.ts_iso || e.ts).getTime() }))
        .filter(e => e.ts >= win.start && e.ts <= win.end)
        .sort((a, b) => a.ts - b.ts);

      const targets  = data.settings?.targets || {};
      const phTgts   = data.phStatus?.targets || {};
      const ecTgts   = data.ecStatus?.targets || {};
      const tSt      = data.tempStatus        || {};

      const phLow  = parseFloat(phTgts.low);
      const phHigh = parseFloat(phTgts.high);
      const ecLow  = parseFloat(ecTgts.low  != null ? ecTgts.low  : targets['ec_low']);
      const ecHigh = parseFloat(ecTgts.high != null ? ecTgts.high : targets['ec_high']);

      let tempLow  = parseFloat(tSt.low);
      let tempHigh = parseFloat(tSt.high);
      const tempSetpoint = parseFloat(tSt.target_temp != null ? tSt.target_temp : (targets['temp_target_c'] != null ? targets['temp_target_c'] : 19));
      if (!Number.isFinite(tempLow) || !Number.isFinite(tempHigh)) {
        const hyst = parseFloat(data.settings?.temperature?.hysteresis != null ? data.settings.temperature.hysteresis : 0.6);
        const t = Number.isFinite(tempSetpoint) ? tempSetpoint : 19;
        tempLow  = t - hyst;
        tempHigh = t + hyst;
      }

      const wKey = durationHours <= 1.5 ? '1h' : durationHours <= 7 ? '6h' : durationHours <= 28 ? '24h' : durationHours <= 200 ? '7d' : 'grow';

      const phVals = ph.map(p => p.y).filter(Number.isFinite);
      const ecVals = ec.map(p => p.y).filter(Number.isFinite);

      const phRng = adaptiveRange(phVals, phLow, phHigh, windowHours, {
        hourSpan: 0.06, hourPad: 0.015, daySpan: 0.10, dayPad: 0.02,
        weekSpan: 0.16, weekPad: 0.03,  monthSpan: 0.22, monthPad: 0.04,
        bandRatio: 0.50, zeroFloor: false
      });
      const ecRng = adaptiveRange(ecVals, ecLow, ecHigh, windowHours, {
        hourSpan: 0.10, hourPad: 0.02, daySpan: 0.16, dayPad: 0.03,
        weekSpan: 0.28, weekPad: 0.04, monthSpan: 0.40, monthPad: 0.06,
        bandRatio: 0.50, zeroFloor: true
      });
      const tRng = Number.isFinite(tempSetpoint)
        ? { min: tempSetpoint - 10, max: tempSetpoint + 10 }
        : adaptiveRange(temp.map(p => p.y).filter(Number.isFinite), tempLow, tempHigh, windowHours, {
            hourSpan: 2, hourPad: 0.5, daySpan: 4, dayPad: 1,
            weekSpan: 6, weekPad: 1.5, monthSpan: 8, monthPad: 2,
            bandRatio: 0.5, zeroFloor: false
          });

      if (axisCache.key !== wKey) {
        axisCache.key  = wKey;
        axisCache.ph   = { min: phRng.min,  max: phRng.max  };
        axisCache.ec   = { min: ecRng.min,  max: ecRng.max  };
        axisCache.temp = { min: tRng.min,   max: tRng.max   };
      } else {
        axisCache.ph.min   = Math.min(axisCache.ph.min,   phRng.min);
        axisCache.ph.max   = Math.max(axisCache.ph.max,   phRng.max);
        axisCache.ec.min   = Math.min(axisCache.ec.min,   ecRng.min);
        axisCache.ec.max   = Math.max(axisCache.ec.max,   ecRng.max);
        axisCache.temp.min = Math.min(axisCache.temp.min, tRng.min);
        axisCache.temp.max = Math.max(axisCache.temp.max, tRng.max);
      }
      if (phVals.length) {
        const pad = Math.max((axisCache.ph.max - axisCache.ph.min) * 0.08, 0.02);
        axisCache.ph.min = Math.min(axisCache.ph.min, Math.min(...phVals) - pad);
        axisCache.ph.max = Math.max(axisCache.ph.max, Math.max(...phVals) + pad);
      }
      if (ecVals.length) {
        const pad = Math.max((axisCache.ec.max - axisCache.ec.min) * 0.08, 0.05);
        axisCache.ec.min = Math.min(axisCache.ec.min, Math.max(0, Math.min(...ecVals) - pad));
        axisCache.ec.max = Math.max(axisCache.ec.max, Math.max(...ecVals) + pad);
      }

      function applyChart(chart, datasets, yMin, yMax) {
        chart.data.datasets = datasets;
        chart.options.scales.x.min = win.start;
        chart.options.scales.x.max = win.end;
        chart.options.scales.y.min = yMin;
        chart.options.scales.y.max = yMax;
        chart.update('none');
      }

      applyChart(phChart,
        [...bandDatasets(phLow, phHigh, win.start, win.end, 59, 130, 246),
         ...(ph.length   ? [lineDataset('pH',      ph,   'rgba(59,130,246,0.9)')]  : [])],
        axisCache.ph.min,   axisCache.ph.max);

      applyChart(ecChart,
        [...bandDatasets(ecLow, ecHigh, win.start, win.end, 16, 185, 129),
         ...(ec.length   ? [lineDataset('EC',      ec,   'rgba(16,185,129,0.9)')]  : [])],
        axisCache.ec.min,   axisCache.ec.max);

      applyChart(tempChart,
        [...bandDatasets(tempLow, tempHigh, win.start, win.end, 239, 68, 68),
         ...(temp.length ? [lineDataset('Temp °C', temp, 'rgba(239,68,68,0.85)')] : [])],
        axisCache.temp.min, axisCache.temp.max);

      const empty = document.getElementById('overview-combined-empty');
      if (empty) empty.style.display = (!ph.length && !ec.length && !temp.length) ? 'block' : 'none';

      setRangeLabel(win.start, win.end);
    }

    // ── Refresh ────────────────────────────────────────────────────────────────
    async function refresh() {
      try {
        const { start, end } = timeWindow;
        const d = await fetchData(new Date(start).toISOString(), new Date(end).toISOString());
        render(d, { start, end });
      } catch (e) {
        console.error('[Overview Stacked] Refresh error', e);
      }
    }

    function stopLive() {
      if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
    }

    function startLive() {
      stopLive();
      liveSpanMs = timeWindow.end - timeWindow.start;
      liveTimer = setInterval(() => {
        timeWindow.end   = Date.now();
        timeWindow.start = timeWindow.end - liveSpanMs;
        refresh();
      }, 5000);
    }

    // ── ChartControls wiring ───────────────────────────────────────────────────
    setRangeLabel(timeWindow.start, timeWindow.end);
    refresh();

    if (typeof ChartControls !== 'undefined' && document.getElementById('overview-combined-controls')) {
      const controls = new ChartControls({
        containerId: 'overview-combined-controls',
        onRangeChange: async (start, end, live) => {
          stopLive();
          axisCache.key = null;
          timeWindow = { start, end };
          setRangeLabel(start, end);
          await refresh();
          if (live) startLive();
        },
        getDataExtent: () => {
          const gs = window.rdwcSettings && window.rdwcSettings.get ? window.rdwcSettings.get('general.grow_start_date') : null;
          return { first: gs ? new Date(gs + 'T00:00:00').getTime() : null, last: Date.now() };
        },
        getGrowStartDate: () => (window.rdwcSettings && window.rdwcSettings.get ? window.rdwcSettings.get('general.grow_start_date') : null)
      });
      controls.applyRange(timeWindow.start, timeWindow.end, false, true);
    }

    window.overviewCombinedChart = { phChart, ecChart, tempChart, refresh, startLive, stopLive };
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', () => setTimeout(init, 200));
})();
