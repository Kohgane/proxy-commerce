/* src/dashboard/static/js/app.js — Admin panel minimal JS */

'use strict';

/**
 * Connect to SSE endpoint and handle real-time events.
 * @param {string} url - SSE endpoint URL (e.g. '/admin/events')
 */
function connectSSE(url) {
  if (!window.EventSource) {
    console.warn('SSE not supported in this browser.');
    return null;
  }
  const source = new EventSource(url);
  source.addEventListener('order_update', function (e) {
    console.log('[SSE] order_update', JSON.parse(e.data));
  });
  source.addEventListener('inventory_alert', function (e) {
    console.log('[SSE] inventory_alert', JSON.parse(e.data));
  });
  source.onerror = function () {
    console.warn('[SSE] connection error — will retry automatically.');
  };
  return source;
}
