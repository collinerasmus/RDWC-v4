/**
 * E-STOP Centralized Store
 * Single source of truth for E-STOP state across all pages
 * Polls /api/estop every 3 seconds and notifies subscribers
 */

(function() {
  const POLL_INTERVAL = 3000;
  let estopState = false;
  const subscribers = [];
  let pollTimer = null;

  /**
   * Subscribe to E-STOP state changes
   * @param {Function} callback - Called with (active: boolean) when state changes
   * @returns {Function} unsubscribe function
   */
  function subscribe(callback) {
    subscribers.push(callback);
    // Immediately notify with current state
    callback(estopState);
    return () => {
      const idx = subscribers.indexOf(callback);
      if (idx >= 0) subscribers.splice(idx, 1);
    };
  }

  /**
   * Get current E-STOP state synchronously
   * @returns {boolean} true if E-STOP is active
   */
  function getEstop() {
    return estopState;
  }

  /**
   * Toggle E-STOP state via API
   * @param {boolean} active - true to activate E-STOP, false to clear
   * @returns {Promise<boolean>} resolved with success status
   */
  async function toggleEstop(active) {
    try {
      const resp = await fetch('/api/estop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active })
      });
      if (!resp.ok) {
        console.error('[estop_store] Toggle failed:', resp.status);
        return false;
      }
      // Force immediate poll to update state
      await pollEstop();
      return true;
    } catch (err) {
      console.error('[estop_store] Toggle error:', err);
      return false;
    }
  }

  /**
   * Poll /api/estop and notify subscribers if state changed
   */
  async function pollEstop() {
    try {
      const resp = await fetch('/api/estop', { cache: 'no-store' });
      if (!resp.ok) {
        console.warn('[estop_store] Poll failed:', resp.status);
        return;
      }
      const data = await resp.json();
      const newState = !!data.active;
      if (newState !== estopState) {
        estopState = newState;
        console.log('[estop_store] State changed:', estopState);
        // Notify all subscribers
        subscribers.forEach(cb => {
          try {
            cb(estopState);
          } catch (err) {
            console.error('[estop_store] Subscriber error:', err);
          }
        });
      }
    } catch (err) {
      console.error('[estop_store] Poll error:', err);
    }
  }

  /**
   * Start background polling
   */
  function startPolling() {
    if (pollTimer) return; // Already running
    pollEstop(); // Initial poll
    pollTimer = setInterval(pollEstop, POLL_INTERVAL);
  }

  /**
   * Stop background polling (cleanup)
   */
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // Auto-start polling when module loads
  startPolling();

  // Expose public API
  window.EstopStore = {
    subscribe,
    getEstop,
    toggleEstop,
    startPolling,
    stopPolling
  };
})();
