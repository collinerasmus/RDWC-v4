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
    if (name==='schedule' && typeof window.loadSettings==='function'){
      window.loadSettings();
      // Bind save if not bound
      const saveBtn = qs('#btnScheduleSave');
      if (saveBtn && !saveBtn.__bound){
        saveBtn.addEventListener('click', function(){
          if (typeof window.saveSettings==='function') window.saveSettings();
        });
        saveBtn.__bound = true;
      }
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
