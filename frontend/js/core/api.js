'use strict';

// API — fetch wrappers with auth injection and all apiXxx() backend call helpers.
// Reads: authGetToken, authSilentRefresh, showLoginRequired (auth.js), showLoading, hideLoading (unified-overlay.js), S (state.js), t (i18n.js), getLocale (i18n.js), SSEClient (communication/sse-client.js).
// Provides: apiLogin, apiLogout, apiGetMe, apiChangePassword, apiInitJob, apiPlanTrip, apiPlanLocation, apiSelectStop, apiConfirmRoute, apiStartAccommodations, apiConfirmAccommodations, apiSelectAccommodation, apiStartPlanning, apiConfirmAccommodationsQuiet, apiStartPlanningQuiet, apiGetResult, apiPatchJob, apiResearchAccommodation, apiRecomputeOptions, apiSetRundreiseMode, apiSkipToLegEnd, apiSkipSegment, replaceRegion, recomputeRegions, confirmRegions, geocodeRegion, apiSaveTravel, apiGetTravels, apiGetTravel, apiDeleteTravel, apiReplanTravel, apiUpdateTravel, apiGetShared, apiShareTravel, apiUnshareTravel, apiLogError, apiGetSettings, apiSaveSettings, apiResetSettings, apiReplaceStop, apiRemoveStop, apiAddStop, apiReorderStops, apiReplaceStopSelect, apiUpdateNights, openSSE, showToast.

// ---------------------------------------------------------------------------
// Internal helpers — fetch wrappers with auth, loading overlay, and retry
// ---------------------------------------------------------------------------

const API = '/api';  // Nginx proxy — no localhost port

/** Build Authorization header from current in-memory token. */
function _authHeader() {
  const token = authGetToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Core fetch wrapper with Bearer injection, Accept-Language, and 401 → silent-refresh retry. */
async function _fetchWithAuth(url, opts = {}) {
  const makeOpts = () => ({
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'Accept-Language': (typeof getLocale === 'function') ? getLocale() : 'de',
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
      throw new Error('HTTP 401: ' + t('api.session_expired'));
    }
    res = await fetch(url, makeOpts());
  }

  return res;
}

/** Fetch with auth, show loading overlay; throws on non-2xx. */
async function _fetch(url, opts = {}, label) {
  S.apiCalls++;
  if (typeof overlayDebugPush === 'function') overlayDebugPush({ level: 'REQ', message: (opts && opts.method ? opts.method : 'GET') + ' ' + url });
  showLoading(label || t('api.default_loading'));
  try {
    const res = await _fetchWithAuth(url, opts);
    if (typeof overlayDebugPush === 'function') overlayDebugPush({ level: 'RES', message: res.status + ' ' + url });
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
  if (typeof overlayDebugPush === 'function') overlayDebugPush({ level: 'REQ', message: (opts && opts.method ? opts.method : 'GET') + ' ' + url });
  const res = await _fetchWithAuth(url, opts);
  if (typeof overlayDebugPush === 'function') overlayDebugPush({ level: 'RES', message: res.status + ' ' + url });
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

/** Authenticate and populate S.currentUser; delegates to authLogin. */
async function apiLogin(username, password) {
  return authLogin(username, password);
}

/** Log out and clear token; delegates to authLogout. */
async function apiLogout() {
  return authLogout();
}

/** Fetch the current authenticated user's profile. */
async function apiGetMe() {
  const res = await _fetchQuiet(`${API}/auth/me`);
  return res.json();
}

/** Change the current user's password. */
async function apiChangePassword(currentPassword, newPassword) {
  const res = await _fetchQuiet(`${API}/auth/change-password`, {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return res.json();
}

// ---------------------------------------------------------------------------
// Planning pipeline — job lifecycle, route building, accommodation selection
// ---------------------------------------------------------------------------

/** Initialise a new planning job and return the job_id. */
async function apiInitJob(payload) {
  // No loading overlay — skeleton cards provide visual feedback
  const res = await _fetchQuiet(`${API}/init-job`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.json();
}

/** Kick off trip planning (route architect + stop options); streams via SSE. */
async function apiPlanTrip(payload, jobId) {
  // No loading overlay — skeleton cards stream in progressively
  const url = jobId ? `${API}/plan-trip?job_id=${encodeURIComponent(jobId)}` : `${API}/plan-trip`;
  const res = await _fetchQuiet(url, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.json();
}

/** POST /api/plan-location/{jobId} — Ortsreise shortcut, returns {job_id, status, selected_stops}. */
async function apiPlanLocation(payload, jobId) {
  const res = await _fetchQuiet(`${API}/plan-location/${jobId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.json();
}

/** Select a stop option by index in the route builder. */
async function apiSelectStop(jobId, idx) {
  // No overlay — skeleton cards show the loading state
  const res = await _fetchQuiet(`${API}/select-stop/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ option_index: idx }),
  });
  return res.json();
}

/** Lock the chosen route and advance the job to the accommodation phase. */
async function apiConfirmRoute(jobId) {
  const res = await _fetch(`${API}/confirm-route/${jobId}`, { method: 'POST' },
    t('api.confirming_route'));
  return res.json();
}

/** Trigger accommodation research for all stops. */
async function apiStartAccommodations(jobId) {
  const res = await _fetch(`${API}/start-accommodations/${jobId}`, { method: 'POST' },
    t('api.starting_accommodation_search'));
  return res.json();
}

/** Confirm accommodation selections and advance to the planning phase (shows overlay). */
async function apiConfirmAccommodations(jobId, selections) {
  const res = await _fetch(`${API}/confirm-accommodations/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ selections }),
  }, t('api.confirming_accommodations'));
  return res.json();
}

/** Select a single accommodation option for a specific stop. */
async function apiSelectAccommodation(jobId, stopId, optionIdx) {
  const res = await _fetch(`${API}/select-accommodation/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ stop_id: stopId, option_index: optionIdx }),
  }, t('api.selecting_accommodation'));
  return res.json();
}

/** Start the full planning pipeline (activities, restaurants, day planner, guide). */
async function apiStartPlanning(jobId) {
  const res = await _fetch(`${API}/start-planning/${jobId}`, { method: 'POST' },
    t('api.creating_travel_plan'));
  return res.json();
}

/** Confirm accommodations without a loading overlay (used in auto-advance flow). */
async function apiConfirmAccommodationsQuiet(jobId, selections) {
  const res = await _fetchQuiet(`${API}/confirm-accommodations/${jobId}`, {
    method: 'POST', body: JSON.stringify({ selections }),
  });
  return res.json();
}

/** Start planning without a loading overlay (used in auto-advance flow). */
async function apiStartPlanningQuiet(jobId) {
  const res = await _fetchQuiet(`${API}/start-planning/${jobId}`, { method: 'POST' });
  return res.json();
}

/** Fetch the completed travel plan result for a job. */
async function apiGetResult(jobId) {
  const res = await _fetch(`${API}/result/${jobId}`, {}, t('api.loading_results'));
  return res.json();
}


/** Patch the job with a route-builder action (e.g. extend days, add via point). */
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

/** Re-run accommodation research for a single stop with optional extra instructions. */
async function apiResearchAccommodation(jobId, stopId, extraInstructions) {
  const res = await _fetchQuiet(`${API}/research-accommodation/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ stop_id: String(stopId), extra_instructions: extraInstructions || '' }),
  });
  return res.json();
}

/** Recompute stop options for the current leg with optional instructions. */
async function apiRecomputeOptions(jobId, extraInstructions) {
  const res = await _fetchQuiet(`${API}/recompute-options/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ extra_instructions: extraInstructions }),
  });
  return res.json();
}

/** Toggle Rundreise (circular route) mode on or off. */
async function apiSetRundreiseMode(jobId, activate) {
  const res = await _fetchQuiet(`${API}/set-rundreise-mode/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ activate }),
  });
  return res.json();
}

/** Skip remaining stops and jump to the end of the current leg. */
async function apiSkipToLegEnd(jobId) {
  return (await _fetchQuiet(`${API}/skip-to-leg-end/${jobId}`, { method: 'POST' })).json();
}

/** Skip the current route segment and move to the next. */
async function apiSkipSegment(jobId) {
  return (await _fetchQuiet(`${API}/skip-segment/${jobId}`, { method: 'POST' })).json();
}

/** Replace a single region at the given index with a new AI-generated suggestion. */
async function replaceRegion(jobId, index, instruction) {
  return await _fetchQuiet(`${API}/replace-region/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ index, instruction }),
  }).then(r => r.json());
}

/** Recompute all regions with an optional free-text instruction. */
async function recomputeRegions(jobId, instruction) {
  return await _fetchQuiet(`${API}/recompute-regions/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ instruction }),
  }).then(r => r.json());
}

/** Confirm the region list and advance the job to route building. */
async function confirmRegions(jobId, regions) {
  return await _fetchQuiet(`${API}/confirm-regions/${jobId}`, {
    method: 'POST',
    body: JSON.stringify(regions ? { regions } : {}),
  }).then(r => r.json());
}

/** Geocode a region name to coordinates via the backend (Google Maps proxy). */
async function geocodeRegion(jobId, name) {
  return await _fetchQuiet(`${API}/geocode-region/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  }).then(r => r.json());
}

// ---------------------------------------------------------------------------
// Travels CRUD — save, list, get, delete, replan, update
// ---------------------------------------------------------------------------

/** Persist a completed travel plan to the backend. */
async function apiSaveTravel(plan) {
  const res = await _fetchQuiet(`${API}/travels`, {
    method: 'POST', body: JSON.stringify({ plan }),
  });
  return res.json();
}

/** Fetch all saved travels for the current user. */
async function apiGetTravels() {
  return (await _fetchQuiet(`${API}/travels`)).json();
}

/** Fetch a single saved travel by ID. */
async function apiGetTravel(id) {
  return (await _fetchQuiet(`${API}/travels/${id}`)).json();
}

/** Delete a saved travel by ID. */
async function apiDeleteTravel(id) {
  return (await _fetchQuiet(`${API}/travels/${id}`, { method: 'DELETE' })).json();
}

/** Trigger a full replan of an existing saved travel. */
async function apiReplanTravel(id) {
  return (await _fetchQuiet(`${API}/travels/${id}/replan`, { method: 'POST' })).json();
}

/** Partially update a saved travel (e.g. rename via custom_name). */
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

/** Generate a public share token for a saved travel. */
async function apiShareTravel(travelId) {
  return (await _fetchQuiet(`${API}/travels/${travelId}/share`, { method: 'POST' })).json();
}

/** Revoke the public share token for a saved travel. */
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

// ---------------------------------------------------------------------------
// Settings API helpers
// ---------------------------------------------------------------------------

/** Fetch the current user's settings. */
async function apiGetSettings() {
  return (await _fetchQuiet(`${API}/settings`)).json();
}

/** Save the full settings object for the current user. */
async function apiSaveSettings(settings) {
  return (await _fetchQuiet(`${API}/settings`, {
    method: 'PUT',
    body: JSON.stringify({ settings }),
  })).json();
}

/** Reset a settings section (or all settings) to defaults. */
async function apiResetSettings(section) {
  return (await _fetchQuiet(`${API}/settings/reset`, {
    method: 'POST',
    body: JSON.stringify({ section }),
  })).json();
}

// ---------------------------------------------------------------------------
// Guide editing — stop management (replace, remove, add, reorder, nights)
// ---------------------------------------------------------------------------

/** Replace a stop with an AI suggestion or a manually specified location. */
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
  }, t('api.replacing_stop'))).json();
}

/** Remove a stop from the travel plan and recompute the route. */
async function apiRemoveStop(travelId, stopId) {
  return (await _fetch(`${API}/travels/${travelId}/remove-stop`, {
    method: 'POST',
    body: JSON.stringify({ stop_id: stopId }),
  }, t('api.removing_stop'))).json();
}

/** Insert a new stop after the specified stop ID. */
async function apiAddStop(travelId, insertAfterStopId, location, nights) {
  return (await _fetch(`${API}/travels/${travelId}/add-stop`, {
    method: 'POST',
    body: JSON.stringify({
      insert_after_stop_id: insertAfterStopId,
      location: location,
      nights: nights || 1,
    }),
  }, t('api.adding_stop'))).json();
}

/** Move a stop from oldIndex to newIndex in the stop list. */
async function apiReorderStops(travelId, oldIndex, newIndex) {
  return (await _fetch(`${API}/travels/${travelId}/reorder-stops`, {
    method: 'POST',
    body: JSON.stringify({ old_index: oldIndex, new_index: newIndex }),
  }, t('api.reordering_stops'))).json();
}

/** Adopt a specific AI-generated replacement option for a stop. */
async function apiReplaceStopSelect(travelId, jobId, optionIndex) {
  return (await _fetch(`${API}/travels/${travelId}/replace-stop-select`, {
    method: 'POST',
    body: JSON.stringify({ job_id: jobId, option_index: optionIndex }),
  }, t('api.adopting_option'))).json();
}

/** Update the number of nights at a stop without triggering a full replan. */
async function apiUpdateNights(travelId, stopId, nights) {
  return (await _fetchQuiet(`${API}/travels/${travelId}/update-nights`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stop_id: stopId, nights: nights }),
  })).json();
}

/**
 * Open SSE connection for a job.
 * Backward-compat shim — delegates to SSEClient.
 * New code should subscribe to window 'sse:X' CustomEvents directly.
 * @param {string} jobId
 * @param {Object} handlers - keyed by SSE event name
 * @returns {{ close: function }}
 */
function openSSE(jobId, handlers) {
  const listeners = [];
  Object.keys(handlers).forEach(evt => {
    if (evt === 'onerror') {
      const fn = () => handlers.onerror();
      window.addEventListener('sse:error', fn, { once: true });
      listeners.push({ name: 'sse:error', fn });
    } else {
      const fn = (e) => handlers[evt](e.detail);
      window.addEventListener('sse:' + evt, fn);
      listeners.push({ name: 'sse:' + evt, fn });
    }
  });
  SSEClient.open(jobId);
  return {
    close() {
      SSEClient.close();
      listeners.forEach(({ name, fn }) => window.removeEventListener(name, fn));
    },
  };
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
