'use strict';

// SSE Client — EventSource lifecycle, reconnection logic, and SSE wire protocol.
// Reads: authGetToken (auth.js).
// Provides: SSEClient.open, SSEClient.close.

const SSEClient = (() => {
  // ---------------------------------------------------------------------------
  // Known SSE event types
  // ---------------------------------------------------------------------------
  const EVENTS = [
    'debug_log', 'route_ready', 'stop_done', 'agent_start', 'agent_done',
    'job_complete', 'job_error', 'accommodation_loading', 'accommodation_loaded',
    'accommodations_all_loaded', 'stop_research_started', 'activities_loaded',
    'restaurants_loaded', 'route_option_ready', 'route_options_done', 'ping',
    'leg_complete',
    'replace_stop_progress', 'replace_stop_complete',
    'remove_stop_progress',  'remove_stop_complete',
    'add_stop_progress',     'add_stop_complete',
    'reorder_stops_progress', 'reorder_stops_complete',
    'update_nights_progress', 'update_nights_complete',
    'style_mismatch_warning', 'ferry_detected',
  ];

  const MAX_RECONNECT_ATTEMPTS = 5;

  let _source             = null;
  let _currentJobId       = null;
  let _currentToken       = null;
  let _reconnectAttempts  = 0;
  let _reconnectTimer     = null;
  let _wasReconnecting    = false;
  let _openResolve        = null;  // resolves the Promise returned by open()

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  // Attach all known event listeners and error/open handlers to an EventSource.
  function _attachListeners(source) {
    source.onopen = () => {
      // Resolve the open() Promise on first successful connection.
      if (_openResolve) {
        const resolve = _openResolve;
        _openResolve = null;
        resolve();
      }
      // Fire sse:reconnected if we recovered from a failure.
      if (_wasReconnecting) {
        _wasReconnecting    = false;
        _reconnectAttempts  = 0;
        window.dispatchEvent(new CustomEvent('sse:reconnected'));
      }
    };

    EVENTS.forEach(evt => {
      source.addEventListener(evt, (e) => {
        let data = {};
        try { data = JSON.parse(e.data); } catch (_) {}
        window.dispatchEvent(new CustomEvent('sse:' + evt, { detail: data }));
      });
    });

    source.onerror = () => {
      // Only attempt reconnection when there is still a job to reconnect to.
      if (!_currentJobId) {
        window.dispatchEvent(new CustomEvent('sse:error'));
        return;
      }

      if (_reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        window.dispatchEvent(new CustomEvent('sse:fatal_error'));
        return;
      }

      _wasReconnecting = true;
      _reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, _reconnectAttempts - 1), 16000);

      window.dispatchEvent(new CustomEvent('sse:reconnecting', {
        detail: { attempt: _reconnectAttempts, maxAttempts: MAX_RECONNECT_ATTEMPTS },
      }));

      // Close the broken source before scheduling the retry.
      if (_source) { _source.close(); _source = null; }

      _reconnectTimer = setTimeout(() => {
        _reconnectTimer = null;
        _connectSource(_currentJobId, _currentToken);
      }, delay);
    };
  }

  // Create and store a new EventSource, attaching all listeners.
  function _connectSource(jobId, token) {
    const qs  = token ? '?token=' + encodeURIComponent(token) : '';
    _source   = new EventSource('/api/progress/' + jobId + qs);
    _attachListeners(_source);
  }

  // ---------------------------------------------------------------------------
  // Connection management
  // ---------------------------------------------------------------------------

  /**
   * Open an EventSource for jobId, injecting the auth token as a query param.
   * Returns a Promise that resolves when the EventSource `onopen` fires.
   */
  function open(jobId) {
    close();
    _currentJobId      = jobId;
    _currentToken      = (typeof authGetToken === 'function') ? authGetToken() : null;
    _reconnectAttempts = 0;
    _wasReconnecting   = false;

    return new Promise(resolve => {
      _openResolve = resolve;
      _connectSource(_currentJobId, _currentToken);
    });
  }

  /** Close the active EventSource connection and cancel any pending reconnect. */
  function close() {
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
    if (_source)         { _source.close(); _source = null; }
    _currentJobId      = null;
    _currentToken      = null;
    _reconnectAttempts = 0;
    _wasReconnecting   = false;
    _openResolve       = null;
  }

  return { open, close };
})();
