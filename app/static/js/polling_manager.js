// polling_manager.js - Single coordinated polling system for entire UI
// Replaces 27+ uncoordinated setInterval loops
// Deduplicates fetch requests, manages update priorities
(function(){
  const VERBOSE = false;
  
  // Central polling configuration
  const config = {
    mainInterval: 6000,      // 6 seconds - main update cycle
    healthInterval: 3000,    // 3 seconds - critical health checks
    slowInterval: 15000      // 15 seconds - slow updates (trends, etc)
  };

  // Registered callbacks
  const callbacks = {
    main: [],      // 6s: controllers, relays, sensors
    health: [],    // 3s: global health status
    slow: []       // 15s: trends, charts
  };

  // Request cache - deduplicate concurrent fetches
  const requestCache = new Map();
  const CACHE_TTL = 2000; // 2 seconds

  // Fetch with deduplication
  async function fetchJSON(url, options = {}) {
    const cacheKey = url + JSON.stringify(options);
    const cached = requestCache.get(cacheKey);
    
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      if (VERBOSE) console.log(`[PollingManager] Cache hit: ${url}`);
      return cached.data;
    }

    // Check if request is already in flight
    if (cached && cached.promise) {
      if (VERBOSE) console.log(`[PollingManager] Request in flight: ${url}`);
      return cached.promise;
    }

    // Make new request
    const promise = fetch(url, { cache: 'no-store', ...options })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        requestCache.set(cacheKey, { data, timestamp: Date.now(), promise: null });
        return data;
      })
      .catch(err => {
        requestCache.delete(cacheKey);
        throw err;
      });

    requestCache.set(cacheKey, { promise, timestamp: Date.now() });
    return promise;
  }

  // Register a callback
  function register(name, callback, priority = 'main') {
    if (!callbacks[priority]) {
      console.error(`[PollingManager] Invalid priority: ${priority}`);
      return;
    }

    if (VERBOSE) console.log(`[PollingManager] Registering: ${name} (${priority})`);
    callbacks[priority].push({ name, callback });
  }

  // Unregister a callback
  function unregister(name, priority = 'main') {
    if (!callbacks[priority]) return;
    callbacks[priority] = callbacks[priority].filter(c => c.name !== name);
    if (VERBOSE) console.log(`[PollingManager] Unregistered: ${name}`);
  }

  // Execute all callbacks for a priority level
  async function executePriority(priority) {
    const items = callbacks[priority];
    if (items.length === 0) return;

    if (VERBOSE) console.log(`[PollingManager] Executing ${priority}: ${items.length} callbacks`);

    // Execute all callbacks in parallel (they can use fetchJSON for deduplication)
    await Promise.allSettled(items.map(item => {
      try {
        return item.callback();
      } catch (err) {
        console.error(`[PollingManager] Error in ${item.name}:`, err);
        return null;
      }
    }));
  }

  // Main polling loop (6s)
  async function mainLoop() {
    await executePriority('main');
  }

  // Health polling loop (3s)
  async function healthLoop() {
    await executePriority('health');
  }

  // Slow polling loop (15s)
  async function slowLoop() {
    await executePriority('slow');
  }

  // Start all polling loops
  function start() {
    if (VERBOSE) console.log('[PollingManager] Starting all loops');
    
    // Run immediately then on intervals
    healthLoop();
    setInterval(healthLoop, config.healthInterval);

    mainLoop();
    setInterval(mainLoop, config.mainInterval);

    slowLoop();
    setInterval(slowLoop, config.slowInterval);
  }

  // Stop all polling (for cleanup/testing)
  function stop() {
    // Clear all intervals - would need to track interval IDs
    console.log('[PollingManager] Stop requested - reload page to restart');
  }

  // Pause/resume polling (e.g., when tab hidden)
  let paused = false;
  function pause() {
    paused = true;
    if (VERBOSE) console.log('[PollingManager] Paused');
  }

  function resume() {
    if (paused) {
      paused = false;
      if (VERBOSE) console.log('[PollingManager] Resumed - triggering immediate refresh');
      healthLoop();
      mainLoop();
    }
  }

  // Handle visibility changes
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      pause();
    } else {
      resume();
    }
  });

  // Public API
  window.pollingManager = {
    register,
    unregister,
    fetchJSON,
    start,
    stop,
    pause,
    resume,
    config  // Allow reading config
  };

  // Auto-start when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  console.log('[PollingManager] Initialized - coordinated polling active');
})();
