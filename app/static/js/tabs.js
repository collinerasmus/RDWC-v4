(function(){
  if (window.__tabsReady) return; // prevent double-init
  const qs = (s)=>document.querySelector(s);
  const qsa = (s)=>Array.from(document.querySelectorAll(s));
  function showTab(name){
    qsa('.tab-section').forEach(sec=>{
      const match = (sec.getAttribute('data-tab')===name);
      sec.style.display = match? '' : 'none';
    });
    qsa('#tabs-nav .btn-chip').forEach(btn=>{
      btn.classList.toggle('active', btn.getAttribute('data-tab')===name);
    });
    // Lazy hooks per tab
    if (name==='schedule'){
      // New Schedule preview init & refresh hooks
      if (typeof window.scheduleInit==='function') try{ window.scheduleInit(); }catch(e){ console.warn('scheduleInit error', e); }
      if (typeof window.scheduleRefresh==='function') try{ window.scheduleRefresh(); }catch(e){ console.warn('scheduleRefresh error', e); }
    }
    if (name==='lights' && typeof window.LightsControl!=='undefined'){
      window.LightsControl.refresh();
    }
    if (name==='circulation' && typeof window.CircControl!=='undefined'){
      window.CircControl.refresh();
    }
    if (name==='temp'){
      // chiller.js poller runs on its own; nothing to do
    }
    if (name==='ph'){
      // Refresh pH chart when tab becomes visible
      if (typeof window.phDoseChart!=='undefined' && window.phDoseChart.refresh){
        try{ window.phDoseChart.refresh(); }catch(e){ console.warn('pH chart refresh error', e); }
      }
    }
    if (name==='ec'){
      // Refresh EC chart when tab becomes visible
      if (typeof window.ecDoseChart!=='undefined' && window.ecDoseChart.refresh){
        try{ window.ecDoseChart.refresh(); }catch(e){ console.warn('EC chart refresh error', e); }
      }
    }
    if (name==='sensors'){
      // Refresh trends chart when tab becomes visible
      if (typeof window.trendsRefresh==='function'){
        try{ window.trendsRefresh(); }catch(e){ console.warn('Trends refresh error', e); }
      }
    }
  }
  function init(){
    const nav = qs('#tabs-nav');
    if (!nav) return;
    nav.addEventListener('click', (e)=>{
      const btn = e.target.closest('[data-tab]');
      if (!btn) return;
      const tab = btn.getAttribute('data-tab');
      location.hash = '#'+tab;
      showTab(tab);
    });
    let initial = (location.hash||'#overview').replace('#','');
    // Fallback to overview if tab does not exist
    const tabs = qsa('.tab-section').map(s=>s.getAttribute('data-tab'));
    if (!tabs.includes(initial)) initial = 'overview';
    showTab(initial);
    window.addEventListener('hashchange', ()=>{
      const tab = (location.hash||'#overview').replace('#','');
      showTab(tab);
    });
    window.__tabsReady = true;
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
