'use strict';

const API = '/api';  // Nginx proxy — no localhost port

async function _fetch(url, opts = {}, label) {
  S.apiCalls++;
  showLoading(label || 'Anfrage läuft…');
  try {
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
  } finally {
    hideLoading();
  }
}

async function apiInitJob(payload) {
  const res = await _fetch(`${API}/init-job`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }, 'Reise wird initialisiert…');
  return res.json();
}

async function apiPlanTrip(payload, jobId) {
  const url = jobId ? `${API}/plan-trip?job_id=${encodeURIComponent(jobId)}` : `${API}/plan-trip`;
  const res = await _fetch(url, {
    method: 'POST',
    body: JSON.stringify(payload),
  }, 'Route wird analysiert…');
  return res.json();
}

async function apiSelectStop(jobId, idx) {
  const res = await _fetch(`${API}/select-stop/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ option_index: idx }),
  }, 'Nächste Routenoption wird geladen…');
  return res.json();
}

async function apiConfirmRoute(jobId) {
  const res = await _fetch(`${API}/confirm-route/${jobId}`, { method: 'POST' },
    'Route wird bestätigt…');
  return res.json();
}

async function apiStartAccommodations(jobId) {
  const res = await _fetch(`${API}/start-accommodations/${jobId}`, { method: 'POST' },
    'Unterkunftsuche wird gestartet…');
  return res.json();
}

async function apiConfirmAccommodations(jobId, selections) {
  const res = await _fetch(`${API}/confirm-accommodations/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ selections }),
  }, 'Unterkünfte werden bestätigt…');
  return res.json();
}

async function apiSelectAccommodation(jobId, stopId, optionIdx) {
  const res = await _fetch(`${API}/select-accommodation/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ stop_id: stopId, option_index: optionIdx }),
  }, 'Unterkunft wird ausgewählt…');
  return res.json();
}

async function apiStartPlanning(jobId) {
  const res = await _fetch(`${API}/start-planning/${jobId}`, { method: 'POST' },
    'Reiseplan wird erstellt…');
  return res.json();
}

async function apiGetResult(jobId) {
  const res = await _fetch(`${API}/result/${jobId}`, {}, 'Ergebnisse werden geladen…');
  return res.json();
}

async function apiGenerateOutput(jobId, type) {
  const res = await _fetch(`${API}/generate-output/${jobId}/${type}`, { method: 'POST' },
    'Dokument wird erstellt…');
  return res.blob();
}

async function apiPatchJob(jobId, action, extraDays, viaPointLocation) {
  const res = await _fetch(`${API}/patch-job/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({
      action,
      extra_days: extraDays || 2,
      via_point_location: viaPointLocation || '',
    }),
  }, 'Route wird angepasst…');
  return res.json();
}

async function apiRecomputeOptions(jobId, extraInstructions) {
  const res = await _fetch(`${API}/recompute-options/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ extra_instructions: extraInstructions }),
  }, 'Routenoptionen werden neu berechnet…');
  return res.json();
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
    'restaurants_loaded', 'route_option_ready', 'route_options_done', 'ping',
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
