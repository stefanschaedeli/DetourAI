'use strict';

const API = '/api';  // Nginx proxy — no localhost port

async function _fetch(url, opts = {}) {
  S.apiCalls++;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail || ''; } catch (e) {}
    throw new Error(`HTTP ${res.status}: ${detail || res.statusText}`);
  }
  return res;
}

async function apiPlanTrip(payload) {
  const res = await _fetch(`${API}/plan-trip`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.json();
}

async function apiSelectStop(jobId, idx) {
  const res = await _fetch(`${API}/select-stop/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ option_index: idx }),
  });
  return res.json();
}

async function apiConfirmRoute(jobId) {
  const res = await _fetch(`${API}/confirm-route/${jobId}`, { method: 'POST' });
  return res.json();
}

async function apiStartAccommodations(jobId) {
  const res = await _fetch(`${API}/start-accommodations/${jobId}`, { method: 'POST' });
  return res.json();
}

async function apiConfirmAccommodations(jobId, selections) {
  const res = await _fetch(`${API}/confirm-accommodations/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ selections }),
  });
  return res.json();
}

async function apiSelectAccommodation(jobId, stopId, optionIdx) {
  const res = await _fetch(`${API}/select-accommodation/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ stop_id: stopId, option_index: optionIdx }),
  });
  return res.json();
}

async function apiStartPlanning(jobId) {
  const res = await _fetch(`${API}/start-planning/${jobId}`, { method: 'POST' });
  return res.json();
}

async function apiGetResult(jobId) {
  const res = await _fetch(`${API}/result/${jobId}`);
  return res.json();
}

async function apiGenerateOutput(jobId, type) {
  const res = await _fetch(`${API}/generate-output/${jobId}/${type}`, { method: 'POST' });
  return res.blob();
}

/**
 * Open SSE connection for a job.
 * @param {string} jobId
 * @param {Object} handlers - keyed by event name
 * @returns {EventSource}
 */
function openSSE(jobId, handlers) {
  const source = new EventSource(`${API}/progress/${jobId}`);

  const events = [
    'debug_log', 'route_ready', 'stop_done', 'agent_start', 'agent_done',
    'job_complete', 'job_error', 'accommodation_loading', 'accommodation_loaded',
    'accommodations_all_loaded', 'stop_research_started', 'activities_loaded',
    'restaurants_loaded', 'ping',
  ];

  events.forEach(evt => {
    if (handlers[evt]) {
      source.addEventListener(evt, e => {
        let data = {};
        try { data = JSON.parse(e.data); } catch (err) {}
        handlers[evt](data);
      });
    }
  });

  source.onerror = () => {
    if (handlers.onerror) handlers.onerror();
  };

  return source;
}
