'use strict';

const API = '/api';  // Nginx proxy — no localhost port

/** Build Authorization header from current in-memory token. */
function _authHeader() {
  const token = authGetToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Core fetch wrapper with Bearer injection and 401 → silent-refresh retry. */
async function _fetchWithAuth(url, opts = {}) {
  const makeOpts = () => ({
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ..._authHeader(),
      ...(opts.headers || {}),
    },
    ...opts,
  });

  let res = await fetch(url, makeOpts());

  // On 401, try one silent token refresh then retry once
  if (res.status === 401) {
    const newToken = await authSilentRefresh();
    if (!newToken) {
      // Refresh failed — user must log in again
      if (typeof showLoginRequired === 'function') showLoginRequired();
      throw new Error('HTTP 401: Sitzung abgelaufen. Bitte erneut anmelden.');
    }
    res = await fetch(url, makeOpts());
  }

  return res;
}

async function _fetch(url, opts = {}, label) {
  S.apiCalls++;
  showLoading(label || 'Anfrage läuft…');
  try {
    const res = await _fetchWithAuth(url, opts);
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

/** Like _fetch but without the blocking loading overlay (skeleton cards provide feedback). */
async function _fetchQuiet(url, opts = {}) {
  S.apiCalls++;
  const res = await _fetchWithAuth(url, opts);
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail || ''; } catch (e) {}
    throw new Error(`HTTP ${res.status}: ${detail || res.statusText}`);
  }
  return res;
}

// ---------------------------------------------------------------------------
// Auth API helpers
// ---------------------------------------------------------------------------

async function apiLogin(username, password) {
  return authLogin(username, password);
}

async function apiLogout() {
  return authLogout();
}

async function apiGetMe() {
  const res = await _fetchQuiet(`${API}/auth/me`);
  return res.json();
}

async function apiChangePassword(currentPassword, newPassword) {
  const res = await _fetchQuiet(`${API}/auth/change-password`, {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return res.json();
}

async function apiInitJob(payload) {
  // No loading overlay — skeleton cards provide visual feedback
  const res = await _fetchQuiet(`${API}/init-job`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.json();
}

async function apiPlanTrip(payload, jobId) {
  // No loading overlay — skeleton cards stream in progressively
  const url = jobId ? `${API}/plan-trip?job_id=${encodeURIComponent(jobId)}` : `${API}/plan-trip`;
  const res = await _fetchQuiet(url, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.json();
}

async function apiSelectStop(jobId, idx) {
  // No overlay — skeleton cards show the loading state
  const res = await _fetchQuiet(`${API}/select-stop/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ option_index: idx }),
  });
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

async function apiConfirmAccommodationsQuiet(jobId, selections) {
  const res = await _fetchQuiet(`${API}/confirm-accommodations/${jobId}`, {
    method: 'POST', body: JSON.stringify({ selections }),
  });
  return res.json();
}

async function apiStartPlanningQuiet(jobId) {
  const res = await _fetchQuiet(`${API}/start-planning/${jobId}`, { method: 'POST' });
  return res.json();
}

async function apiGetResult(jobId) {
  const res = await _fetch(`${API}/result/${jobId}`, {}, 'Ergebnisse werden geladen…');
  return res.json();
}


async function apiPatchJob(jobId, action, extraDays, viaPointLocation) {
  const res = await _fetchQuiet(`${API}/patch-job/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({
      action,
      extra_days: extraDays || 2,
      via_point_location: viaPointLocation || '',
    }),
  });
  return res.json();
}

async function apiResearchAccommodation(jobId, stopId, extraInstructions) {
  const res = await _fetchQuiet(`${API}/research-accommodation/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ stop_id: String(stopId), extra_instructions: extraInstructions || '' }),
  });
  return res.json();
}

async function apiRecomputeOptions(jobId, extraInstructions) {
  const res = await _fetchQuiet(`${API}/recompute-options/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ extra_instructions: extraInstructions }),
  });
  return res.json();
}

async function apiSetRundreiseMode(jobId, activate) {
  const res = await _fetchQuiet(`${API}/set-rundreise-mode/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ activate }),
  });
  return res.json();
}

async function apiSkipToLegEnd(jobId) {
  return (await _fetchQuiet(`${API}/skip-to-leg-end/${jobId}`, { method: 'POST' })).json();
}

async function replaceRegion(jobId, index, instruction) {
  return await _fetchQuiet(`${API}/replace-region/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ index, instruction }),
  }).then(r => r.json());
}

async function recomputeRegions(jobId, instruction) {
  return await _fetchQuiet(`${API}/recompute-regions/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ instruction }),
  }).then(r => r.json());
}

async function confirmRegions(jobId, regions) {
  return await _fetchQuiet(`${API}/confirm-regions/${jobId}`, {
    method: 'POST',
    body: JSON.stringify(regions ? { regions } : {}),
  }).then(r => r.json());
}

async function geocodeRegion(jobId, name) {
  return await _fetchQuiet(`${API}/geocode-region/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  }).then(r => r.json());
}

async function apiSaveTravel(plan) {
  const res = await _fetchQuiet(`${API}/travels`, {
    method: 'POST', body: JSON.stringify({ plan }),
  });
  return res.json();
}

async function apiGetTravels() {
  return (await _fetchQuiet(`${API}/travels`)).json();
}

async function apiGetTravel(id) {
  return (await _fetchQuiet(`${API}/travels/${id}`)).json();
}

async function apiDeleteTravel(id) {
  return (await _fetchQuiet(`${API}/travels/${id}`, { method: 'DELETE' })).json();
}

async function apiReplanTravel(id) {
  return (await _fetchQuiet(`${API}/travels/${id}/replan`, { method: 'POST' })).json();
}

async function apiUpdateTravel(id, data) {
  return (await _fetchQuiet(`${API}/travels/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })).json();
}

// ---------------------------------------------------------------------------
// Share API helpers
// ---------------------------------------------------------------------------

/** Fetch a shared travel plan by token (NO auth — public endpoint). */
async function apiGetShared(token) {
  const res = await fetch(`${API}/shared/${token}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiShareTravel(travelId) {
  return (await _fetchQuiet(`${API}/travels/${travelId}/share`, { method: 'POST' })).json();
}

async function apiUnshareTravel(travelId) {
  return (await _fetchQuiet(`${API}/travels/${travelId}/share`, { method: 'DELETE' })).json();
}

/** Send a frontend log entry to the backend. */
async function apiLogError(level, message, source, stack) {
  try {
    await fetch(`${API}/log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, message: String(message).slice(0, 5000), source: String(source || '').slice(0, 200), stack: String(stack || '').slice(0, 10000) }),
    });
  } catch (_) { /* best-effort — don't throw on logging failures */ }
}

async function apiGetSettings() {
  return (await _fetchQuiet(`${API}/settings`)).json();
}

async function apiSaveSettings(settings) {
  return (await _fetchQuiet(`${API}/settings`, {
    method: 'PUT',
    body: JSON.stringify({ settings }),
  })).json();
}

async function apiResetSettings(section) {
  return (await _fetchQuiet(`${API}/settings/reset`, {
    method: 'POST',
    body: JSON.stringify({ section }),
  })).json();
}

async function apiReplaceStop(travelId, stopId, mode, manualLocation, manualNights, hints) {
  return (await _fetch(`${API}/travels/${travelId}/replace-stop`, {
    method: 'POST',
    body: JSON.stringify({
      stop_id: stopId,
      mode,
      manual_location: manualLocation || null,
      manual_nights: manualNights || null,
      hints: hints || null,
    }),
  }, 'Stopp wird ersetzt…')).json();
}

async function apiRemoveStop(travelId, stopId) {
  return (await _fetch(`${API}/travels/${travelId}/remove-stop`, {
    method: 'POST',
    body: JSON.stringify({ stop_id: stopId }),
  }, 'Stopp wird entfernt…')).json();
}

async function apiAddStop(travelId, insertAfterStopId, location, nights) {
  return (await _fetch(`${API}/travels/${travelId}/add-stop`, {
    method: 'POST',
    body: JSON.stringify({
      insert_after_stop_id: insertAfterStopId,
      location: location,
      nights: nights || 1,
    }),
  }, 'Stopp wird hinzugefügt…')).json();
}

async function apiReorderStops(travelId, oldIndex, newIndex) {
  return (await _fetch(`${API}/travels/${travelId}/reorder-stops`, {
    method: 'POST',
    body: JSON.stringify({ old_index: oldIndex, new_index: newIndex }),
  }, 'Stopps werden neu sortiert…')).json();
}

async function apiReplaceStopSelect(travelId, jobId, optionIndex) {
  return (await _fetch(`${API}/travels/${travelId}/replace-stop-select`, {
    method: 'POST',
    body: JSON.stringify({ job_id: jobId, option_index: optionIndex }),
  }, 'Option wird übernommen…')).json();
}

/**
 * Open SSE connection for a job.
 * @param {string} jobId
 * @param {Object} handlers - keyed by event name
 * @returns {EventSource}
 */
function openSSE(jobId, handlers) {
  const token = authGetToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : '';
  const source = new EventSource(`${API}/progress/${jobId}${qs}`);

  const events = [
    'debug_log', 'route_ready', 'stop_done', 'agent_start', 'agent_done',
    'job_complete', 'job_error', 'accommodation_loading', 'accommodation_loaded',
    'accommodations_all_loaded', 'stop_research_started', 'activities_loaded',
    'restaurants_loaded', 'route_option_ready', 'route_options_done', 'ping',
    'region_plan_ready', 'region_updated', 'leg_complete',
    'replace_stop_progress', 'replace_stop_complete',
    'remove_stop_progress', 'remove_stop_complete',
    'add_stop_progress', 'add_stop_complete',
    'reorder_stops_progress', 'reorder_stops_complete',
    'style_mismatch_warning', 'ferry_detected',
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

/**
 * Show a brief auto-dismissing toast notification.
 * @param {string} message
 * @param {'info'|'warning'} type
 */
function showToast(message, type) {
  const toast = document.createElement('div');
  toast.className = `app-toast app-toast--${type}`;
  toast.textContent = message;
  // Stack above existing toasts
  const existing = document.querySelectorAll('.app-toast');
  const offset = 24 + existing.length * 48;
  toast.style.bottom = offset + 'px';
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('visible'));
  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 300);
  }, 6000);
}
