// mode_manager.js - centralized mode change event broadcaster
// Provides a single source of truth for system mode transitions.
// Other modules listen for 'mode-changed' events on window.
(function(){
  const MODE_KEY = 'system_mode';
  let current = localStorage.getItem(MODE_KEY) || 'auto';

  function dispatch(){
    window.dispatchEvent(new CustomEvent('mode-changed', { detail: { mode: current } }));
  }

  async function sync(){
    try{
      const r = await fetch('/api/mode', {cache:'no-store'}); // unified endpoint expected
      if(r.ok){
        const j = await r.json();
        if(j && j.mode && j.mode !== current){
          current = j.mode; localStorage.setItem(MODE_KEY, current); dispatch();
        }
      }
    }catch(e){ /* silent */ }
  }

  async function setMode(next){
    try{
      const r = await fetch('/api/mode', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({mode: next})});
      const j = await r.json().catch(()=>({}));
      if(r.ok && j.ok && j.mode){
        current = j.mode; localStorage.setItem(MODE_KEY, current); dispatch();
      } else {
        console.warn('[ModeManager] Reject:', r.status, j);
      }
    }catch(e){ console.warn('[ModeManager] setMode error', e); }
  }

  // Public API
  window.modeManager = { get: ()=>current, set: setMode, sync };

  // Initial sync + periodic refresh (30s)
  if(document.readyState === 'loading'){ document.addEventListener('DOMContentLoaded', ()=>{ sync(); dispatch(); }); }
  else { sync(); dispatch(); }
  setInterval(sync, 30000);
})();
