/**
 * Circulation Controller - Mode management for Main + Chiller pumps
 */
(() => {
  // ===== MODE MANAGEMENT =====
  let circMode = localStorage.getItem('circ_mode') || 'manual';

  function circSetMode(next) {
    // Normalize 'maintenance' to 'maint' for consistency
    if (next === 'maintenance') next = 'maint';
    if (!['auto', 'manual', 'maint'].includes(next)) return;
    
    circMode = next;
    localStorage.setItem('circ_mode', next);

    // Update button states
    ['auto', 'manual', 'maint'].forEach(m => {
      const btn = document.getElementById(`circ-mode-${m}`);
      if (btn) btn.classList.toggle('active', m === next);
    });

    // Show/hide content sections if they exist (future expansion)
    const autoContent = document.getElementById('circ-auto-content');
    const manualContent = document.getElementById('circ-manual-content');
    const maintContent = document.getElementById('circ-maint-content');
    if (autoContent) autoContent.style.display = (next === 'auto') ? 'block' : 'none';
    if (manualContent) manualContent.style.display = (next === 'manual') ? 'block' : 'none';
    if (maintContent) maintContent.style.display = (next === 'maint') ? 'block' : 'none';

    updateCircHealth();
  }

  function updateCircHealth() {
    const chip = document.getElementById('circ-health-indicator');
    if (!chip) return;

    if (circMode === 'maint') {
      chip.textContent = 'MAINT';
      chip.className = 'health-chip chip-mode';
    } else {
      chip.textContent = 'OK';
      chip.className = 'health-chip chip-ok';
    }
  }

  window.circSetMode = circSetMode;

  // Initialize mode on load
  document.addEventListener('DOMContentLoaded', () => {
    circSetMode(circMode);
  });

  // Refresh health every 5s (can poll /api/relays/status for pump cooldowns if needed)
  setInterval(() => {
    if (document.getElementById('circ-health-indicator')) {
      updateCircHealth();
    }
  }, 5000);
})();
