// system_metrics_panel.js - safe, isolated panel for system metrics (no history yet)
(function(){
  'use strict';

  function el(tag, attrs, children){
    var e = document.createElement(tag);
    if(attrs){ Object.keys(attrs).forEach(function(k){ e.setAttribute(k, attrs[k]); }); }
    if(children){ if(Array.isArray(children)){ children.forEach(function(c){ if(c) e.appendChild(c); }); } else if(typeof children==='string'){ e.innerHTML = children; } }
    return e;
  }

  function formatBytes(n){
    if(n==null) return '—';
    var units=['B','KB','MB','GB','TB']; var i=0; var v=n;
    while(v>=1024 && i<units.length-1){ v/=1024; i++; }
    return v.toFixed(1)+' '+units[i];
  }

  function render(container, m){
    container.innerHTML = '';
    var grid = el('div', {style:'display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;'});
    function card(label, value){
      var c = el('div', {class:'card-mini', style:'background:#0d1117;border:1px solid #333;border-radius:8px;padding:10px;color:#e0e0e0;'});
      c.appendChild(el('div', {style:'font-size:12px;opacity:.8;margin-bottom:4px;'}, label));
      c.appendChild(el('div', {style:'font-size:18px;font-weight:600;'}, value));
      return c;
    }
    grid.appendChild(card('CPU %', m.cpu_percent!=null? m.cpu_percent.toFixed(1)+'%':'—'));
    grid.appendChild(card('Memory %', m.memory_percent!=null? m.memory_percent.toFixed(1)+'%':'—'));
    grid.appendChild(card('Disk %', m.disk_percent!=null? m.disk_percent.toFixed(1)+'%':'—'));
    grid.appendChild(card('Core V', m.core_voltage_v!=null? m.core_voltage_v.toFixed(3)+' V':'—'));
    grid.appendChild(card('Load (1m)', m.load_1m!=null? m.load_1m.toFixed(2):'—'));
    grid.appendChild(card('Load (5m)', m.load_5m!=null? m.load_5m.toFixed(2):'—'));
    grid.appendChild(card('Load (15m)', m.load_15m!=null? m.load_15m.toFixed(2):'—'));
    grid.appendChild(card('RX', formatBytes(m.net_rx_bytes)));
    grid.appendChild(card('TX', formatBytes(m.net_tx_bytes)));
    container.appendChild(grid);
  }

  async function fetchCurrent(){
    try{
      const r = await fetch('/api/system/metrics/current', {cache:'no-store'});
      if(!r.ok) throw new Error('HTTP '+r.status);
      const j = await r.json();
      return j && j.data || {};
    }catch(e){ console.warn('[SysMetrics] fetch failed', e); return {}; }
  }

  function start(container){
    let timer=null;
    async function tick(){
      const m = await fetchCurrent();
      render(container, m);
    }
    tick();
    if(window.PollingManager && typeof window.PollingManager.register==='function'){
      window.PollingManager.register('sysmetrics', tick, 'slow');
    } else {
      timer = setInterval(tick, 15000);
    }
    return function stop(){ if(timer) clearInterval(timer); };
  }

  function boot(){
    const container = document.getElementById('system-metrics-panel');
    if(!container) return; // not visible on this build
    container.innerHTML = '<div style="margin:6px 0 10px;color:#aaa;font-size:12px;">System Metrics (beta) — history disabled</div>';
    start(container);
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
