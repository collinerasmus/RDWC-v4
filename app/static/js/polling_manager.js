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
  const CACHE_TTL = 8000; // raised to 8s to reduce hammering

  // Shared data cache with TTLs for common endpoints
  const dataCache = {
    sensors: { data: null, timestamp: 0, ttl: 5000 },  // 5s
    settings: { data: null, timestamp: 0, ttl: 30000 }, // 30s
    health: { data: null, timestamp: 0, ttl: 10000 },   // 10s
    trends: { data: null, timestamp: 0, ttl: 60000 }    // 60s
  };

  // Connection state tracking
  let connectionLost = false;
  let lastSuccessfulFetch = Date.now();
  let consecutiveFailures = 0;
  let dynamicBackoffMs = 0; // increases on failures, reset on success

  function showConnectionBanner(on){
    let el = document.getElementById('conn-status-banner');
    if(!el && on){
      el = document.createElement('div');
      el.id = 'conn-status-banner';
      el.style.cssText = 'position:fixed;top:0;left:0;right:0;padding:6px 12px;background:rgba(239,68,68,0.9);color:#fff;font-size:13px;font-weight:500;z-index:9999;text-align:center;letter-spacing:.5px;';
      el.textContent = 'Connection lost – retrying...';
      document.body.appendChild(el);
    }
    if(el && !on){ el.remove(); }
  }
  
  // Fetch with deduplication and connection recovery
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

    // Make new request with timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout

    const promise = fetch(url, { 
        cache: 'no-store', 
        signal: controller.signal,
        ...options 
      })
      .then(r => {
        clearTimeout(timeoutId);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        lastSuccessfulFetch = Date.now();
        if (connectionLost) {
          console.log('[PollingManager] Connection restored');
          connectionLost = false;
          consecutiveFailures = 0;
          dynamicBackoffMs = 0;
          showConnectionBanner(false);
        }
        requestCache.set(cacheKey, { data, timestamp: Date.now(), promise: null });
        return data;
      })
      .catch(err => {
        clearTimeout(timeoutId);
        requestCache.delete(cacheKey);
        consecutiveFailures += 1;
        // Escalate to connectionLost after 30s since last success or 5 consecutive failures
        if (!connectionLost && (Date.now() - lastSuccessfulFetch > 30000 || consecutiveFailures >= 5)) {
          console.warn('[PollingManager] Connection appears lost');
          connectionLost = true; showConnectionBanner(true);
        }
        // Dynamic backoff: increase delay for priority loops (capped)
        dynamicBackoffMs = Math.min(20000, (dynamicBackoffMs || 1000) * 2);
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
    if (paused) return; // Skip if paused
    
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
    if(dynamicBackoffMs){ await new Promise(r=>setTimeout(r, dynamicBackoffMs)); }
    await executePriority('main');
  }

  // Health polling loop (3s)
  async function healthLoop() {
    if(dynamicBackoffMs){ await new Promise(r=>setTimeout(r, dynamicBackoffMs)); }
    await executePriority('health');
  }

  // Slow polling loop (15s)
  async function slowLoop() {
    if(dynamicBackoffMs){ await new Promise(r=>setTimeout(r, dynamicBackoffMs)); }
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

  // Get cached data or fetch with TTL management
  function getCachedOrFetch(key, url, ttl) {
    const now = Date.now();
    const cached = dataCache[key];
    const effectiveTTL = ttl !== undefined ? ttl : (cached ? cached.ttl : 5000);
    
    if (cached && cached.data && (now - cached.timestamp) < effectiveTTL) {
      if (VERBOSE) console.log(`[PollingManager] Cache hit: ${key}`);
      return Promise.resolve(cached.data);
    }
    
    if (VERBOSE) console.log(`[PollingManager] Cache miss: ${key}, fetching...`);
    return fetchJSON(url).then(data => {
      dataCache[key] = { data, timestamp: now, ttl: effectiveTTL };
      return data;
    });
  }

  // Public API
  window.pollingManager = {
    register,
    unregister,
    fetchJSON,
    start,
    stop,
    pause,
    resume,
    config,  // Allow reading config
    // Cached data getters
    getSensors: () => getCachedOrFetch('sensors', '/api/sensors', 5000),
    getSettings: () => getCachedOrFetch('settings', '/api/settings/export', 30000),
    getHealth: () => getCachedOrFetch('health', '/api/health', 10000),
    getTrends: (params) => {
      // Note: Trends cache is intentionally shared across all parameter variations
      // to reduce backend load. For precise time-range queries, use fetchJSON directly.
      const url = params ? `/api/trends?${new URLSearchParams(params)}` : '/api/trends';
      return fetchJSON(url); // Use fetchJSON which has its own request deduplication
    }
  };

  // Auto-start when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  // Backward compatibility: expose as PollingManager (capital P) too
  window.PollingManager = window.pollingManager;

  console.log('[PollingManager] Initialized - coordinated polling active');
})();
