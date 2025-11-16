/**
 * Frontend Error Reporter
 * Automatically captures console errors and sends them to backend for debugging
 */

(function() {
  'use strict';

  const LOG_ENDPOINT = '/api/frontend/log';
  const MAX_QUEUE_SIZE = 50;
  const FLUSH_INTERVAL_MS = 5000;
  const MAX_MESSAGE_LENGTH = 2000;
  const MAX_STACK_LENGTH = 5000;

  let logQueue = [];
  let flushTimer = null;

  // Truncate long strings to prevent payload bloat
  function truncate(str, maxLen) {
    if (!str) return str;
    return str.length > maxLen ? str.substring(0, maxLen) + '...[truncated]' : str;
  }

  // Send logs to backend
  async function flushLogs() {
    if (logQueue.length === 0) return;

    const batch = logQueue.splice(0, MAX_QUEUE_SIZE);
    
    try {
      await fetch(LOG_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs: batch })
      });
    } catch (e) {
      // Silent fail - don't create infinite loop of error reporting
      console.warn('[ErrorReporter] Failed to send logs:', e.message);
    }
  }

  // Queue a log entry
  function queueLog(level, message, stack, url, lineNumber, columnNumber, metadata) {
    logQueue.push({
      ts: Math.floor(Date.now() / 1000),
      level,
      message: truncate(message, MAX_MESSAGE_LENGTH),
      stack: truncate(stack, MAX_STACK_LENGTH),
      url: url || window.location.href,
      line_number: lineNumber || null,
      column_number: columnNumber || null,
      user_agent: navigator.userAgent,
      page_url: window.location.href,
      metadata: metadata ? JSON.stringify(metadata) : null
    });

    // Auto-flush on error or if queue is full
    if (level === 'error' || logQueue.length >= MAX_QUEUE_SIZE) {
      if (flushTimer) clearTimeout(flushTimer);
      flushLogs();
    } else {
      // Batch other logs
      if (flushTimer) clearTimeout(flushTimer);
      flushTimer = setTimeout(flushLogs, FLUSH_INTERVAL_MS);
    }
  }

  // Capture global errors
  window.addEventListener('error', function(event) {
    queueLog(
      'error',
      event.message || 'Unknown error',
      event.error?.stack || '',
      event.filename,
      event.lineno,
      event.colno,
      null
    );
  });

  // Capture unhandled promise rejections
  window.addEventListener('unhandledrejection', function(event) {
    queueLog(
      'error',
      'Unhandled Promise Rejection: ' + (event.reason?.message || event.reason),
      event.reason?.stack || '',
      null,
      null,
      null,
      { type: 'promise_rejection' }
    );
  });

  // Intercept console.error and console.warn
  const originalError = console.error;
  const originalWarn = console.warn;

  console.error = function(...args) {
    const message = args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ');
    const error = args.find(a => a instanceof Error);
    queueLog('error', message, error?.stack || '', null, null, null, null);
    originalError.apply(console, args);
  };

  console.warn = function(...args) {
    const message = args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ');
    queueLog('warn', message, '', null, null, null, null);
    originalWarn.apply(console, args);
  };

  // Flush logs before page unload
  window.addEventListener('beforeunload', function() {
    if (logQueue.length > 0) {
      // Use sendBeacon for reliable delivery on page unload
      const data = JSON.stringify({ logs: logQueue });
      navigator.sendBeacon(LOG_ENDPOINT, data);
    }
  });

  // Expose manual logging function
  window.logToBackend = function(level, message, metadata) {
    queueLog(level, message, '', null, null, null, metadata);
  };

  console.log('[ErrorReporter] Initialized - errors will be logged to backend');
})();
