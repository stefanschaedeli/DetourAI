'use strict';

/**
 * SSEClient — owns EventSource lifecycle and SSE wire protocol.
 *
 * SSEClient.open(jobId)  — opens EventSource, dispatches window CustomEvents
 * SSEClient.close()      — closes active connection
 *
 * Each SSE event X fires:
 *   window.dispatchEvent(new CustomEvent('sse:X', { detail: parsedData }))
 * On error:
 *   window.dispatchEvent(new CustomEvent('sse:error'))
 */
const SSEClient = (() => {
  const EVENTS = [
    'debug_log', 'route_ready', 'stop_done', 'agent_start', 'agent_done',
    'job_complete', 'job_error', 'accommodation_loading', 'accommodation_loaded',
    'accommodations_all_loaded', 'stop_research_started', 'activities_loaded',
    'restaurants_loaded', 'route_option_ready', 'route_options_done', 'ping',
    'region_plan_ready', 'region_updated', 'leg_complete',
    'replace_stop_progress', 'replace_stop_complete',
    'remove_stop_progress',  'remove_stop_complete',
    'add_stop_progress',     'add_stop_complete',
    'reorder_stops_progress', 'reorder_stops_complete',
    'update_nights_progress', 'update_nights_complete',
    'style_mismatch_warning', 'ferry_detected',
  ];

  let _source = null;

  function open(jobId) {
    close();
    const token = (typeof authGetToken === 'function') ? authGetToken() : null;
    const qs    = token ? '?token=' + encodeURIComponent(token) : '';
    _source     = new EventSource('/api/progress/' + jobId + qs);
    EVENTS.forEach(evt => {
      _source.addEventListener(evt, (e) => {
        let data = {};
        try { data = JSON.parse(e.data); } catch (_) {}
        window.dispatchEvent(new CustomEvent('sse:' + evt, { detail: data }));
      });
    });
    _source.onerror = () => { window.dispatchEvent(new CustomEvent('sse:error')); };
  }

  function close() {
    if (_source) { _source.close(); _source = null; }
  }

  return { open, close };
})();
