/**
 * Shared range utilities for Trends and pH dose charts
 * Provides consistent date range computation and localStorage persistence
 */
(function(){
  const RANGES = ['1h', '24h', '7d', '30d', '90d', 'grow', 'custom'];
  
  function isoLocal(dt){
    return dt.toISOString().slice(0,16); // yyyy-MM-ddTHH:mm
  }
  
  function rangeFromPreset(preset){
    const now = Date.now();
    let start = now;
    if (preset === '1h')  start = now - 60*60*1000;
    if (preset === '24h') start = now - 24*60*60*1000;
    if (preset === '7d')  start = now - 7*24*60*60*1000;
    if (preset === '30d') start = now - 30*24*60*60*1000;
    if (preset === '90d') start = now - 90*24*60*60*1000;
    return { start, end: now };
  }
  
  async function rangeToStartEnd(preset, customStart, customEnd, growStartDate){
    if (preset === 'custom') {
      if (!customStart || !customEnd) return null;
      const start = new Date(customStart).getTime();
      const end = new Date(customEnd).getTime();
      if (isNaN(start) || isNaN(end) || start >= end) return null;
      return { start, end };
    }
    
    if (preset === 'grow') {
      // Use growStartDate from settings if provided
      if (growStartDate) {
        try {
          const startDate = new Date(growStartDate + 'T00:00:00');
          const start = startDate.getTime();
          const end = Date.now();
          if (!isNaN(start) && start < end) {
            return { start, end };
          }
        } catch(e) {
          console.warn('Invalid grow_start_date:', e);
        }
      }
      // Fallback to 30 days
      const fallback = new Date();
      fallback.setDate(fallback.getDate() - 30);
      return { start: fallback.getTime(), end: Date.now() };
    }
    
    // Standard presets
    return rangeFromPreset(preset);
  }
  
  function saveLastPreset(key, preset){
    try {
      localStorage.setItem(key + '.lastPreset', preset);
    } catch(e){}
  }
  
  function getLastPreset(key, defaultPreset = '24h'){
    try {
      return localStorage.getItem(key + '.lastPreset') || defaultPreset;
    } catch(e){
      return defaultPreset;
    }
  }
  
  function saveCustomRange(key, start, end){
    try {
      localStorage.setItem(key + '.customStart', start);
      localStorage.setItem(key + '.customEnd', end);
    } catch(e){}
  }
  
  function getCustomRange(key){
    try {
      return {
        start: localStorage.getItem(key + '.customStart'),
        end: localStorage.getItem(key + '.customEnd')
      };
    } catch(e){
      return { start: null, end: null };
    }
  }
  
  // Export to global
  window.rdwcRange = {
    RANGES,
    isoLocal,
    rangeFromPreset,
    rangeToStartEnd,
    saveLastPreset,
    getLastPreset,
    saveCustomRange,
    getCustomRange
  };
})();
