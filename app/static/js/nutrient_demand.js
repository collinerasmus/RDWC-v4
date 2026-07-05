(function () {
  'use strict';

  const AUTO_REFRESH_MS = 30000;

  const el = (id) => document.getElementById(id);
  const getJSON = async (url) => {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  };

  let chart = null;

  function fmt(value, digits = 1, suffix = '') {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
    return `${Number(value).toFixed(digits)}${suffix}`;
  }

  function setBadge(node, trend) {
    if (!node) return;
    const label = trend || 'unknown';
    node.textContent = label;
    node.className = 'badge ' + (label === 'rising' ? 'warning' : (label === 'falling' ? 'success' : 'neutral'));
  }

  function renderLatest(summary) {
    const latestValue = summary?.latest_value ?? summary?.latest?.total_nutrient_ml ?? 0;
    const yesterday = summary?.yesterday_ml ?? summary?.previous_value ?? 0;
    const sevenDay = summary?.seven_day_average_ml ?? 0;
    const trend = summary?.trend ?? summary?.latest?.ndi_trend ?? 'unknown';

    const latestEl = el('ndi-latest');
    const trendEl = el('ndi-trend');
    const yesterdayEl = el('ndi-yesterday');
    const sevenDayEl = el('ndi-seven-day');
    const trendBadge = el('ndi-trend-badge');
    const tableBadge = el('ndi-table-note');

    if (latestEl) latestEl.textContent = fmt(latestValue, 1, ' ml/day');
    if (trendEl) trendEl.textContent = trend;
    if (yesterdayEl) yesterdayEl.textContent = fmt(yesterday, 1, ' ml');
    if (sevenDayEl) sevenDayEl.textContent = fmt(sevenDay, 1, ' ml/day');
    setBadge(trendBadge, trend);

    if (tableBadge) {
      tableBadge.textContent = summary?.latest?.notes ? 'Latest row has notes' : 'Monitoring only';
    }
  }

  function renderChart(history) {
    const canvas = el('ndi-chart');
    if (!canvas || !window.Chart) return;

    const points = (history || []).map((row) => {
      const x = new Date(`${row.date}T00:00:00`).getTime();
      const y = Number(row.total_nutrient_ml || 0);
      return { x, y };
    }).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));

    if (chart) chart.destroy();
    chart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        datasets: [{
          label: 'Total nutrient ml/day',
          data: points,
          borderColor: '#fb923c',
          backgroundColor: 'rgba(251,146,60,0.18)',
          fill: true,
          tension: 0.25,
          pointRadius: 3,
          pointHoverRadius: 5,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            type: 'time',
            time: { unit: 'day' },
            ticks: { color: '#94a3b8' },
            grid: { color: 'rgba(148,163,184,0.10)' }
          },
          y: {
            beginAtZero: true,
            ticks: { color: '#94a3b8' },
            grid: { color: 'rgba(148,163,184,0.10)' }
          }
        },
        plugins: {
          legend: {
            labels: { color: '#e5e7eb' }
          },
          tooltip: {
            callbacks: {
              label(ctx) {
                return ` ${Number(ctx.parsed.y || 0).toFixed(1)} ml/day`;
              }
            }
          }
        }
      }
    });
  }

  function renderTable(history) {
    const body = el('ndi-table-body');
    const note = el('ndi-chart-note');
    if (!body) return;

    if (!history || !history.length) {
      body.innerHTML = '<tr><td colspan="9" class="muted">No NDI rows have been generated yet.</td></tr>';
      if (note) note.textContent = 'No data';
      return;
    }

    body.innerHTML = history.map((row) => {
      const trend = row.ndi_trend || 'unknown';
      const badgeClass = trend === 'rising' ? 'warning' : (trend === 'falling' ? 'success' : 'neutral');
      return `
        <tr>
          <td>${row.date || '—'}</td>
          <td>${fmt(row.grow_ml, 1)}</td>
          <td>${fmt(row.micro_ml, 1)}</td>
          <td>${fmt(row.bloom_ml, 1)}</td>
          <td>${fmt(row.total_nutrient_ml, 1)}</td>
          <td>${fmt(row.avg_ec, 3)}</td>
          <td>${fmt(row.ec_target, 2)}</td>
          <td>${fmt(row.avg_ph, 2)}</td>
          <td><span class="badge ${badgeClass}">${trend}</span></td>
        </tr>
      `;
    }).join('');

    if (note) note.textContent = `${history.length} day${history.length === 1 ? '' : 's'} loaded`;
  }

  function renderAdvisor(payload) {
    const overview = payload?.overview || null;
    const assessors = payload?.assessors || {};
    const wrap = el('ndi-advisor-list');
    const overviewWrap = el('ndi-advisor-overview');
    const assessorWrap = el('ndi-assessor-list');
    const note = el('ndi-advisor-note');
    if (!wrap) return;

    if (overviewWrap) {
      if (!overview) {
        overviewWrap.innerHTML = '<div class="muted">Advisor overview unavailable.</div>';
      } else {
        const verdict = String(overview.verdict || 'unknown');
        const verdictClass = verdict === 'urgent' ? 'warning' : verdict === 'watch' ? 'neutral' : verdict === 'hold' ? 'neutral' : 'success';
        overviewWrap.innerHTML = `
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
            <strong>${overview.title || 'Overview'}</strong>
            <span class="badge ${verdictClass}">${verdict}</span>
          </div>
          <div class="muted" style="margin-top:6px;">${overview.summary || ''}</div>
          <div style="margin-top:6px;">${overview.action || ''}</div>
        `;
      }
    }

    if (assessorWrap) {
      const items = Object.values(assessors || {});
      if (!items.length) {
        assessorWrap.innerHTML = '<div class="muted">No assessors available.</div>';
      } else {
        assessorWrap.innerHTML = items.map((item) => {
          const status = String(item.status || 'unknown');
          const statusClass = status === 'bad' ? 'warning' : status === 'warn' ? 'neutral' : status === 'good' ? 'success' : 'neutral';
          const recCount = Array.isArray(item.recommendations) ? item.recommendations.length : 0;
          const evidence = item.evidence ? JSON.stringify(item.evidence) : '';
          return `
            <div class="assessor-card">
              <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
                <strong>${item.name || 'assessor'}</strong>
                <span class="badge ${statusClass}">${status} • ${Number(item.score || 0).toFixed(0)}</span>
              </div>
              <div class="muted" style="margin-top:6px;">${item.summary || ''}</div>
              <div class="muted" style="margin-top:6px;font-size:0.8rem;">${recCount} recommendation${recCount === 1 ? '' : 's'}</div>
              ${evidence ? `<div class="muted" style="margin-top:6px;font-size:0.75rem;opacity:0.85;">${evidence}</div>` : ''}
            </div>
          `;
        }).join('');
      }
    }

    const recs = payload?.recommendations || [];
    if (!recs.length) {
      wrap.innerHTML = '<div class="muted">No recommendations available.</div>';
      if (note) note.textContent = 'No guidance';
      return;
    }

    wrap.innerHTML = recs.slice(0, 4).map((r) => {
      const sev = (r.severity || 'info').toLowerCase();
      const badgeClass = sev === 'high' ? 'warning' : (sev === 'medium' ? 'neutral' : 'success');
      const confidence = Number.isFinite(Number(r.confidence)) ? `${Math.round(Number(r.confidence) * 100)}%` : 'n/a';
      return `
        <div class="advisor-item">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
            <strong>${r.title || 'Recommendation'}</strong>
            <span class="badge ${badgeClass}">${sev} • ${confidence}</span>
          </div>
          <div class="muted" style="margin-top:6px;">${r.rationale || ''}</div>
          <div style="margin-top:6px;">${r.action || ''}</div>
        </div>
      `;
    }).join('');

    if (note) note.textContent = `${recs.length} recommendation${recs.length === 1 ? '' : 's'}`;
  }

  async function refresh() {
    const tableNote = el('ndi-table-note');
    const chartNote = el('ndi-chart-note');
    if (tableNote) tableNote.textContent = 'Refreshing…';
    if (chartNote) chartNote.textContent = 'Refreshing…';

    try {
      const [latest, history, advisor] = await Promise.all([
        getJSON('/api/nutrient-demand/latest'),
        getJSON('/api/nutrient-demand/history?scope=grow'),
        getJSON('/api/advisor/recommendations')
      ]);

      renderLatest(latest);
      renderChart(history.history || []);
      renderTable(history.history || []);
      renderAdvisor(advisor || null);

      if (chartNote) {
        const t = new Date();
        chartNote.textContent = `Updated ${t.toLocaleTimeString()} • ${history.history?.length || 0} day${(history.history?.length || 0) === 1 ? '' : 's'} loaded`;
      }
    } catch (err) {
      const body = el('ndi-table-body');
      const advisor = el('ndi-advisor-list');
      if (body) body.innerHTML = '<tr><td colspan="9" class="muted">Failed to load NDI data.</td></tr>';
      if (advisor) advisor.innerHTML = '<div class="muted">Advisor unavailable.</div>';
      if (tableNote) tableNote.textContent = 'Error';
      if (chartNote) chartNote.textContent = 'Error loading data';
      console.error('[NDI] refresh failed:', err);
    }
  }

  function bind() {
    const refreshBtn = el('ndi-refresh');
    if (refreshBtn) refreshBtn.addEventListener('click', refresh);

    // Keep page reasonably live without hammering the API.
    setInterval(() => {
      refresh().catch(() => {});
    }, AUTO_REFRESH_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      bind();
      refresh();
    });
  } else {
    bind();
    refresh();
  }
})();
