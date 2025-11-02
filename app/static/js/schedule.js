(function(){
  const q = (s)=>document.querySelector(s);
  function init(){
    const save = q('#btnScheduleSave');
    if (save){ save.addEventListener('click', function(){ if (typeof window.saveSettings==='function') window.saveSettings(); }); }
    // Attempt initial load when script is loaded (tab switch will also call)
    if (typeof window.loadSettings==='function') window.loadSettings();
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
