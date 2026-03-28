// Guide Edit — route editing (add/remove/reorder/replace/drag), SSE edit handlers.
// Reads: S (state.js), esc() (state.js), activeTab (guide-core.js),
//        _fetch/_fetchQuiet/openSSE (api.js), GoogleMaps (maps.js).
// Provides: _lockEditing, _unlockEditing, _confirmRemoveStop, _executeRemoveStop,
//           _openAddStopModal, _executeAddStop, _haversineKm, _onMapClickToAdd,
//           _showClickToAddPopup, _hideClickToAddPopup, _confirmClickToAdd,
//           _doAddStopFromMap, _onStopDragStart, _onStopDragEnd, _onStopDrop,
//           _onDropZoneDrop, _editStopNights,
//           openReplaceStopModal, closeReplaceStopModal, _switchReplaceTab,
//           _showReplaceProgress, _hideReplaceProgress, _doManualReplace,
//           _doSearchReplace, _selectSearchOption, _listenForReplaceComplete
'use strict';

let _editInProgress = false;
let _editSSE = null;
let _dragStopSourceIndex = null;

// ---------------------------------------------------------------------------
// Edit Lock — one operation at a time (D-17)
// ---------------------------------------------------------------------------

function _lockEditing() {
  _editInProgress = true;
  document.querySelectorAll('.remove-stop-btn, .add-stop-btn, .replace-stop-btn').forEach(btn => {
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.style.pointerEvents = 'none';
  });
  document.querySelectorAll('.stop-overview-card[draggable]').forEach(card => {
    card.style.opacity = '0.5';
    card.style.pointerEvents = 'none';
  });
}

function _unlockEditing() {
  _editInProgress = false;
  document.querySelectorAll('.remove-stop-btn, .add-stop-btn, .replace-stop-btn').forEach(btn => {
    btn.disabled = false;
    btn.style.opacity = '';
    btn.style.pointerEvents = '';
  });
  document.querySelectorAll('.stop-overview-card[draggable]').forEach(card => {
    card.style.opacity = '';
    card.style.pointerEvents = '';
  });
}

// ---------------------------------------------------------------------------
// Remove Stop — confirm + execute
// ---------------------------------------------------------------------------

function _confirmRemoveStop(stopId) {
  if (_editInProgress) return;
  const plan = S.result;
  if (!plan) return;
  const stop = (plan.stops || []).find(s => s.id === stopId);
  if (!stop) return;

  const existing = document.getElementById('confirm-remove-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'confirm-remove-modal';
  modal.className = 'modal-backdrop';

  // Build modal content safely using esc() for user data
  const heading = document.createElement('h3');
  heading.textContent = 'Stopp entfernen?';

  const para = document.createElement('p');
  para.innerHTML = 'M\u00f6chtest du <strong>' + esc(stop.region) + '</strong> wirklich entfernen? Alle recherchierten Daten (Aktivit\u00e4ten, Restaurants, Unterk\u00fcnfte) gehen verloren.';

  const actions = document.createElement('div');
  actions.className = 'modal-actions';

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn-secondary';
  cancelBtn.textContent = 'Abbrechen';
  cancelBtn.onclick = () => modal.remove();

  const removeBtn = document.createElement('button');
  removeBtn.className = 'btn btn-danger';
  removeBtn.textContent = 'Entfernen';
  removeBtn.onclick = () => _executeRemoveStop(stopId);

  actions.appendChild(cancelBtn);
  actions.appendChild(removeBtn);

  const content = document.createElement('div');
  content.className = 'modal-content';
  content.appendChild(heading);
  content.appendChild(para);
  content.appendChild(actions);

  modal.appendChild(content);
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
  document.body.appendChild(modal);
}

async function _executeRemoveStop(stopId) {
  const modal = document.getElementById('confirm-remove-modal');
  if (modal) modal.remove();

  const travelId = S.result._saved_travel_id || S.result.id;
  if (!travelId) return;

  _lockEditing();
  try {
    const res = await apiRemoveStop(travelId, stopId);
    _editSSE = openSSE(res.job_id, {
      remove_stop_progress: () => {},
      remove_stop_complete: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        data._saved_travel_id = travelId;
        S.result = data;
        lsSet(LS_RESULT, { savedAt: new Date().toISOString(), plan: data });
        _activeStopId = null;
        _unlockEditing();
        renderGuide(data, 'stops');
        if (typeof GoogleMaps !== 'undefined') GoogleMaps.setGuideMarkers(data, _onMarkerClick);
      },
      job_error: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Fehler beim Entfernen: ' + (data.error || 'Unbekannter Fehler'));
      },
      onerror: () => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Verbindung verloren beim Entfernen des Stopps.');
      },
    });
  } catch (err) {
    _unlockEditing();
    alert('Fehler: ' + err.message);
  }
}

// ---------------------------------------------------------------------------
// Add Stop — modal + execute
// ---------------------------------------------------------------------------

function _openAddStopModal() {
  if (_editInProgress) return;
  const plan = S.result;
  if (!plan) return;

  const savedId = plan._saved_travel_id;
  if (!savedId) {
    alert('Reise muss zuerst gespeichert werden.');
    return;
  }

  const stops = plan.stops || [];
  const existing = document.getElementById('add-stop-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'add-stop-modal';
  modal.className = 'modal-backdrop';

  const content = document.createElement('div');
  content.className = 'modal-content';

  const heading = document.createElement('h3');
  heading.textContent = 'Stopp hinzuf\u00fcgen';
  content.appendChild(heading);

  // Location input
  const locGroup = document.createElement('div');
  locGroup.className = 'form-group';
  const locLabel = document.createElement('label');
  locLabel.textContent = 'Ort';
  locLabel.setAttribute('for', 'add-stop-location');
  const locInput = document.createElement('input');
  locInput.type = 'text';
  locInput.id = 'add-stop-location';
  locInput.className = 'form-input';
  locInput.placeholder = 'z.B. Lyon, Marseille...';
  locGroup.appendChild(locLabel);
  locGroup.appendChild(locInput);
  content.appendChild(locGroup);

  // Insert-after select
  const afterGroup = document.createElement('div');
  afterGroup.className = 'form-group';
  const afterLabel = document.createElement('label');
  afterLabel.textContent = 'Einf\u00fcgen nach';
  afterLabel.setAttribute('for', 'add-stop-after');
  const afterSelect = document.createElement('select');
  afterSelect.id = 'add-stop-after';
  afterSelect.className = 'form-input';
  stops.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = s.region + ' (Stop ' + s.id + ')';
    afterSelect.appendChild(opt);
  });
  afterGroup.appendChild(afterLabel);
  afterGroup.appendChild(afterSelect);
  content.appendChild(afterGroup);

  // Nights input
  const nightsGroup = document.createElement('div');
  nightsGroup.className = 'form-group';
  const nightsLabel = document.createElement('label');
  nightsLabel.textContent = 'N\u00e4chte';
  nightsLabel.setAttribute('for', 'add-stop-nights');
  const nightsInput = document.createElement('input');
  nightsInput.type = 'number';
  nightsInput.id = 'add-stop-nights';
  nightsInput.className = 'form-input';
  nightsInput.value = '1';
  nightsInput.min = '1';
  nightsInput.max = '14';
  nightsInput.style.width = '80px';
  nightsGroup.appendChild(nightsLabel);
  nightsGroup.appendChild(nightsInput);
  content.appendChild(nightsGroup);

  // Actions
  const actions = document.createElement('div');
  actions.className = 'modal-actions';
  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn-secondary';
  cancelBtn.textContent = 'Abbrechen';
  cancelBtn.onclick = () => modal.remove();
  const addBtn = document.createElement('button');
  addBtn.className = 'btn btn-primary';
  addBtn.textContent = 'Hinzuf\u00fcgen';
  addBtn.onclick = () => _executeAddStop();
  actions.appendChild(cancelBtn);
  actions.appendChild(addBtn);
  content.appendChild(actions);

  modal.appendChild(content);
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
  document.body.appendChild(modal);
  setTimeout(() => locInput.focus(), 100);
}

async function _executeAddStop() {
  const location = (document.getElementById('add-stop-location')?.value || '').trim();
  if (!location) { alert('Bitte Ortsnamen eingeben'); return; }

  const afterId = parseInt(document.getElementById('add-stop-after')?.value) || 1;
  const nights = parseInt(document.getElementById('add-stop-nights')?.value) || 1;

  const modal = document.getElementById('add-stop-modal');
  if (modal) modal.remove();

  const travelId = S.result._saved_travel_id || S.result.id;
  if (!travelId) return;

  _lockEditing();
  try {
    const res = await apiAddStop(travelId, afterId, location, nights);
    _editSSE = openSSE(res.job_id, {
      add_stop_progress: () => {},
      add_stop_complete: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        data._saved_travel_id = travelId;
        S.result = data;
        lsSet(LS_RESULT, { savedAt: new Date().toISOString(), plan: data });
        _unlockEditing();
        renderGuide(data, 'stops');
        if (typeof GoogleMaps !== 'undefined') GoogleMaps.setGuideMarkers(data, _onMarkerClick);
      },
      job_error: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Fehler beim Hinzuf\u00fcgen: ' + (data.error || 'Unbekannter Fehler'));
      },
      onerror: () => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Verbindung verloren beim Hinzuf\u00fcgen des Stopps.');
      },
    });
  } catch (err) {
    _unlockEditing();
    alert('Fehler: ' + err.message);
  }
}

// ---------------------------------------------------------------------------
// Click-to-Add-Stop on Map (D-10)
// ---------------------------------------------------------------------------

/** Haversine distance in km between two lat/lng points. */
function _haversineKm(lat1, lon1, lat2, lon2) {
  var R = 6371;
  var dLat = (lat2 - lat1) * Math.PI / 180;
  var dLon = (lon2 - lon1) * Math.PI / 180;
  var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Handle click on empty map area — reverse geocode and show popup. */
function _onMapClickToAdd(latLng) {
  if (_editInProgress) return;
  _hideClickToAddPopup();
  var geocoder = new google.maps.Geocoder();
  geocoder.geocode({ location: { lat: latLng.lat(), lng: latLng.lng() } }, function(results, status) {
    if (status !== 'OK' || !results || !results.length) return;

    // Build a clean short name from address components (avoids garbled full addresses)
    var placeName = '';
    var components = results[0].address_components || [];
    var locality = '';
    var region = '';
    var country = '';
    for (var c = 0; c < components.length; c++) {
      var types = components[c].types || [];
      if (types.indexOf('locality') !== -1) locality = components[c].long_name;
      else if (types.indexOf('administrative_area_level_1') !== -1) region = components[c].long_name;
      else if (types.indexOf('country') !== -1) country = components[c].long_name;
    }

    if (locality) {
      placeName = locality + (country ? ', ' + country : '');
    } else if (region) {
      placeName = region + (country ? ', ' + country : '');
    } else {
      // Fallback: first two parts of formatted_address
      var parts = (results[0].formatted_address || '').split(',');
      placeName = parts.slice(0, 2).join(',').trim();
    }

    _showClickToAddPopup(latLng, placeName);
  });
}

/** Show click-to-add popup at map click position. */
function _showClickToAddPopup(latLng, placeName) {
  var popup = document.getElementById('click-to-add-popup');
  if (!popup) return;

  var map = GoogleMaps.getGuideMap();
  if (!map) return;

  // Store latLng for later use in confirm
  popup._clickLatLng = latLng;
  popup._placeName = placeName;

  // Build popup content safely using DOM methods — textContent for place name (XSS safe)
  var nameEl = document.createElement('div');
  nameEl.className = 'popup-place-name';
  nameEl.textContent = placeName;

  var btn = document.createElement('button');
  btn.className = 'popup-add-btn';
  btn.textContent = 'Stopp hier hinzuf\u00fcgen?';
  btn.onclick = function() { _confirmClickToAdd(popup._placeName); };

  // Clear previous content safely and append new DOM elements
  while (popup.firstChild) popup.removeChild(popup.firstChild);
  popup.appendChild(nameEl);
  popup.appendChild(btn);

  // Position popup using map overlay projection
  var overlay = new google.maps.OverlayView();
  overlay.draw = function() {};
  overlay.setMap(map);

  // Wait for projection to be ready
  google.maps.event.addListenerOnce(map, 'idle', function() {
    var proj = overlay.getProjection();
    if (proj) {
      var point = proj.fromLatLngToContainerPixel(latLng);
      if (point) {
        popup.style.left = point.x + 'px';
        popup.style.top = (point.y - 10) + 'px';
        popup.style.transform = 'translate(-50%, -100%)';
      }
    }
    overlay.setMap(null);
  });

  popup.style.display = 'block';

  // Escape key dismisses popup
  popup._escHandler = function(e) {
    if (e.key === 'Escape') _hideClickToAddPopup();
  };
  document.addEventListener('keydown', popup._escHandler);
}

/** Hide click-to-add popup and clean up listeners. */
function _hideClickToAddPopup() {
  var popup = document.getElementById('click-to-add-popup');
  if (!popup) return;
  popup.style.display = 'none';
  while (popup.firstChild) popup.removeChild(popup.firstChild);
  popup._clickLatLng = null;
  popup._placeName = null;
  if (popup._escHandler) {
    document.removeEventListener('keydown', popup._escHandler);
    popup._escHandler = null;
  }
}

/** Confirm adding a stop at the clicked map location. */
function _confirmClickToAdd(placeName) {
  if (!placeName) return;
  var plan = S.result;
  if (!plan) return;

  var popup = document.getElementById('click-to-add-popup');
  var clickLatLng = popup ? popup._clickLatLng : null;
  _hideClickToAddPopup();

  if (!clickLatLng) return;

  var stops = plan.stops || [];
  if (stops.length === 0) {
    // No stops yet — insert after position 0 (start)
    _doAddStopFromMap(placeName, 0);
    return;
  }

  // Find nearest stop by haversine distance
  var clickLat = clickLatLng.lat();
  var clickLng = clickLatLng.lng();
  var nearestIdx = 0;
  var nearestDist = Infinity;

  stops.forEach(function(stop, i) {
    if (!stop.lat || !stop.lng) return;
    var d = _haversineKm(clickLat, clickLng, stop.lat, stop.lng);
    if (d < nearestDist) {
      nearestDist = d;
      nearestIdx = i;
    }
  });

  // Determine if click falls before or after the nearest stop
  // by comparing distances to the previous and next stops
  var insertAfterId;
  var nearestStop = stops[nearestIdx];
  var prevStop = nearestIdx > 0 ? stops[nearestIdx - 1] : null;
  var nextStop = nearestIdx < stops.length - 1 ? stops[nearestIdx + 1] : null;

  var distToPrev = prevStop && prevStop.lat && prevStop.lng
    ? _haversineKm(clickLat, clickLng, prevStop.lat, prevStop.lng)
    : Infinity;
  var distToNext = nextStop && nextStop.lat && nextStop.lng
    ? _haversineKm(clickLat, clickLng, nextStop.lat, nextStop.lng)
    : Infinity;

  // If click is closer to the previous stop than the next, insert before nearest
  if (distToPrev < distToNext && prevStop) {
    insertAfterId = prevStop.id;
  } else {
    insertAfterId = nearestStop.id;
  }

  _doAddStopFromMap(placeName, insertAfterId);
}

/** Execute add-stop from map click — reuses the existing add-stop API flow. */
function _doAddStopFromMap(placeName, afterStopId) {
  var plan = S.result;
  if (!plan) return;

  var travelId = plan._saved_travel_id || plan.id;
  if (!travelId) {
    alert('Reise muss zuerst gespeichert werden.');
    return;
  }

  _lockEditing();
  apiAddStop(travelId, afterStopId, placeName, 1).then(function(res) {
    _editSSE = openSSE(res.job_id, {
      add_stop_progress: function() {},
      add_stop_complete: function(data) {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        data._saved_travel_id = travelId;
        S.result = data;
        lsSet(LS_RESULT, { savedAt: new Date().toISOString(), plan: data });
        _unlockEditing();
        renderGuide(data, 'stops');
        if (typeof GoogleMaps !== 'undefined') GoogleMaps.setGuideMarkers(data, _onMarkerClick);
      },
      job_error: function(data) {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Fehler beim Hinzuf\u00fcgen: ' + (data.error || 'Unbekannter Fehler'));
      },
      onerror: function() {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Verbindung verloren beim Hinzuf\u00fcgen des Stopps.');
      },
    });
  }).catch(function(err) {
    _unlockEditing();
    alert('Fehler: ' + err.message);
  });
}

// ---------------------------------------------------------------------------
// Drag-and-Drop Reorder
// ---------------------------------------------------------------------------

function _onStopDragStart(e, index) {
  if (_editInProgress) { e.preventDefault(); return; }
  _dragStopSourceIndex = index;
  e.dataTransfer.effectAllowed = 'move';
  e.currentTarget.classList.add('dragging');
}

function _onStopDragEnd(e) {
  e.currentTarget.classList.remove('dragging');
  document.querySelectorAll('.stop-drop-zone').forEach(z => z.classList.remove('drop-zone-active'));
}

async function _onStopDrop(e, targetIndex) {
  e.preventDefault();
  document.querySelectorAll('.stop-overview-card, .stop-card-row').forEach(c => {
    c.classList.remove('drag-over');
    c.classList.remove('dragging');
  });

  if (_dragStopSourceIndex === null || _dragStopSourceIndex === targetIndex) {
    _dragStopSourceIndex = null;
    return;
  }

  const travelId = S.result._saved_travel_id || S.result.id;
  if (!travelId) return;

  const oldIdx = _dragStopSourceIndex;
  _dragStopSourceIndex = null;

  _lockEditing();
  try {
    const res = await apiReorderStops(travelId, oldIdx, targetIndex);
    _editSSE = openSSE(res.job_id, {
      reorder_stops_progress: () => {},
      reorder_stops_complete: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        data._saved_travel_id = travelId;
        S.result = data;
        lsSet(LS_RESULT, { savedAt: new Date().toISOString(), plan: data });
        _unlockEditing();
        renderGuide(data, 'stops');
        if (typeof GoogleMaps !== 'undefined') GoogleMaps.setGuideMarkers(data, _onMarkerClick);
      },
      job_error: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Fehler beim Sortieren: ' + (data.error || 'Unbekannter Fehler'));
      },
      onerror: () => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Verbindung verloren beim Sortieren.');
      },
    });
  } catch (err) {
    _unlockEditing();
    alert('Fehler: ' + err.message);
  }
}

// ---------------------------------------------------------------------------
// Drop Zone handler for between-card drag-and-drop (GAP-06)
// Must be top-level (not inside an IIFE) for inline HTML ondrop attributes.
// ---------------------------------------------------------------------------

async function _onDropZoneDrop(e, dropBeforeIndex) {
  e.preventDefault();
  document.querySelectorAll('.stop-drop-zone').forEach(z => z.classList.remove('drop-zone-active'));

  if (_dragStopSourceIndex === null) return;
  var sourceIdx = _dragStopSourceIndex;

  // Convert "insert before dropBeforeIndex" to "move to position"
  // If dragging downward, the removal of source shifts indexes
  var targetIdx = dropBeforeIndex;
  if (sourceIdx < dropBeforeIndex) targetIdx = dropBeforeIndex - 1;

  if (sourceIdx === targetIdx) {
    _dragStopSourceIndex = null;
    return;
  }

  // Delegate to existing _onStopDrop
  _onStopDrop(e, targetIdx);
}

// ---------------------------------------------------------------------------
// Inline nights edit — local-state-only update (GAP-07)
// ---------------------------------------------------------------------------

function _editStopNights(stopId, currentNights) {
  if (_editInProgress) return;
  var input = prompt('Anzahl N\u00e4chte:', currentNights);
  if (input === null) return;
  var nights = parseInt(input);
  if (isNaN(nights) || nights < 1 || nights > 14) {
    alert('Bitte eine Zahl zwischen 1 und 14 eingeben.');
    return;
  }
  if (nights === currentNights) return;

  // Update local state only — persisted when travel is saved
  var stops = (S.result && S.result.stops) || [];
  for (var i = 0; i < stops.length; i++) {
    if (stops[i].id === stopId) {
      stops[i].nights = nights;
      break;
    }
  }

  // Update localStorage cache
  lsSet(LS_RESULT, { savedAt: new Date().toISOString(), plan: S.result });

  // Re-render stops view to show updated nights
  renderGuide(S.result, 'stops');
}

// ---------------------------------------------------------------------------
// Replace Stop — Modal + SSE handling
// ---------------------------------------------------------------------------

let _replaceStopSSE = null;

function openReplaceStopModal(stopId, currentNights) {
  const plan = S.result;
  if (!plan) return;

  const savedId = plan._saved_travel_id;
  if (!savedId) {
    alert('Reise muss zuerst gespeichert werden.');
    return;
  }

  const stop = (plan.stops || []).find(s => s.id === stopId);
  if (!stop) return;

  const stopIdx = (plan.stops || []).indexOf(stop);
  const prevLabel = stopIdx > 0
    ? plan.stops[stopIdx - 1].region
    : plan.start_location || '';
  const nextLabel = stopIdx < plan.stops.length - 1
    ? plan.stops[stopIdx + 1].region
    : '';

  // Remove existing modal
  const existing = document.getElementById('replace-stop-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'replace-stop-modal';
  modal.className = 'replace-modal';
  modal.innerHTML = `
    <div class="replace-modal-backdrop" onclick="closeReplaceStopModal()"></div>
    <div class="replace-modal-content">
      <div class="replace-modal-header">
        <h3>Stopp ersetzen: ${esc(stop.region)}</h3>
        <button class="replace-modal-close" onclick="closeReplaceStopModal()">&times;</button>
      </div>

      <div class="replace-modal-tabs">
        <button class="replace-tab active" data-tab="manual" onclick="_switchReplaceTab('manual')">Ort eingeben</button>
        <button class="replace-tab" data-tab="search" onclick="_switchReplaceTab('search')">Neue Suche</button>
      </div>

      <div class="replace-hints-section" style="margin-bottom:16px">
        <label style="display:block;font-size:var(--text-sm,14px);color:var(--text-secondary,#666);margin-bottom:4px">Hinweise (optional)</label>
        <input type="text" id="replace-stop-hints" class="replace-input"
          placeholder="z.B. mehr Strand, weniger Fahrzeit"
          style="width:100%;padding:12px 16px;font-size:16px;border:1px solid var(--border-default,#ddd);border-radius:8px;box-sizing:border-box" />
      </div>

      <div class="replace-tab-content" id="replace-tab-manual">
        <div class="replace-form">
          <label>Neuer Ort</label>
          <input type="text" id="replace-manual-location" class="replace-input" placeholder="z.B. Lyon, Frankreich" />
          <label>Nächte <small>(Standard: ${currentNights})</small></label>
          <input type="number" id="replace-manual-nights" class="replace-input" min="1" max="14" value="${currentNights}" />
          <button class="btn btn-primary replace-submit-btn" id="replace-manual-btn"
            onclick="_doManualReplace(${savedId}, ${stopId})">Ersetzen</button>
        </div>
      </div>

      <div class="replace-tab-content" id="replace-tab-search" style="display:none">
        <p class="replace-search-info">
          Suche basierend auf ${esc(prevLabel)} → ${nextLabel ? esc(nextLabel) : 'Reiseende'}
          mit den Original-Einstellungen.
        </p>
        <button class="btn btn-primary replace-submit-btn" id="replace-search-btn"
          onclick="_doSearchReplace(${savedId}, ${stopId})">Alternativen suchen</button>
        <div id="replace-search-results" class="replace-search-results"></div>
      </div>

      <div id="replace-progress" class="replace-progress" style="display:none">
        <div class="replace-spinner"></div>
        <p id="replace-progress-msg">Wird bearbeitet…</p>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  requestAnimationFrame(() => modal.classList.add('visible'));

  // Focus input
  const input = document.getElementById('replace-manual-location');
  if (input) setTimeout(() => input.focus(), 100);
}

function closeReplaceStopModal() {
  const modal = document.getElementById('replace-stop-modal');
  if (modal) {
    modal.classList.remove('visible');
    setTimeout(() => modal.remove(), 200);
  }
  if (_replaceStopSSE) {
    _replaceStopSSE.close();
    _replaceStopSSE = null;
  }
}

function _switchReplaceTab(tab) {
  document.querySelectorAll('.replace-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.getElementById('replace-tab-manual').style.display = tab === 'manual' ? '' : 'none';
  document.getElementById('replace-tab-search').style.display = tab === 'search' ? '' : 'none';
}

function _showReplaceProgress(msg) {
  const p = document.getElementById('replace-progress');
  const m = document.getElementById('replace-progress-msg');
  if (p) p.style.display = '';
  if (m) m.textContent = msg || 'Wird bearbeitet…';
}

function _hideReplaceProgress() {
  const p = document.getElementById('replace-progress');
  if (p) p.style.display = 'none';
}

async function _doManualReplace(travelId, stopId) {
  const loc = (document.getElementById('replace-manual-location')?.value || '').trim();
  const nights = parseInt(document.getElementById('replace-manual-nights')?.value) || 1;
  const hints = (document.getElementById('replace-stop-hints')?.value || '').trim();
  if (!loc) { alert('Bitte einen Ort eingeben.'); return; }

  const btn = document.getElementById('replace-manual-btn');
  if (btn) btn.disabled = true;
  _lockEditing();
  _showReplaceProgress('Ort wird gesucht…');

  try {
    const res = await apiReplaceStop(travelId, stopId, 'manual', loc, nights, hints);
    _listenForReplaceComplete(res.job_id, travelId);
  } catch (err) {
    _hideReplaceProgress();
    if (btn) btn.disabled = false;
    alert('Fehler: ' + err.message);
  }
}

async function _doSearchReplace(travelId, stopId) {
  const btn = document.getElementById('replace-search-btn');
  if (btn) btn.disabled = true;
  const hints = (document.getElementById('replace-stop-hints')?.value || '').trim();
  _lockEditing();
  _showReplaceProgress('Alternativen werden gesucht…');

  try {
    const res = await apiReplaceStop(travelId, stopId, 'search', null, null, hints);
    _hideReplaceProgress();
    if (btn) btn.disabled = false;

    const options = res.options || [];
    const container = document.getElementById('replace-search-results');
    if (!container) return;

    if (!options.length) {
      container.innerHTML = '<p class="replace-no-results">Keine Alternativen gefunden.</p>';
      return;
    }

    container.innerHTML = options.map((opt, i) => `
      <div class="replace-option-card" onclick="_selectSearchOption(${travelId}, '${esc(res.job_id)}', ${i})">
        <div class="replace-option-header">
          <strong>${FLAGS[opt.country] || ''} ${esc(opt.region)}</strong>
          <span class="replace-option-type">${esc(opt.option_type || '')}</span>
        </div>
        <p class="replace-option-teaser">${esc(opt.teaser || '')}</p>
        <div class="replace-option-meta">
          ${opt.drive_hours ? `${opt.drive_hours}h Fahrt` : ''}
          ${opt.drive_km ? ` · ${opt.drive_km} km` : ''}
          ${opt.nights ? ` · ${opt.nights} Nacht${opt.nights !== 1 ? 'e' : ''}` : ''}
        </div>
      </div>
    `).join('');
  } catch (err) {
    _hideReplaceProgress();
    if (btn) btn.disabled = false;
    alert('Fehler: ' + err.message);
  }
}

async function _selectSearchOption(travelId, jobId, optionIndex) {
  _showReplaceProgress('Gewählter Stopp wird recherchiert…');

  try {
    const res = await apiReplaceStopSelect(travelId, jobId, optionIndex);
    _listenForReplaceComplete(res.job_id, travelId);
  } catch (err) {
    _hideReplaceProgress();
    alert('Fehler: ' + err.message);
  }
}

function _listenForReplaceComplete(jobId, travelId) {
  _showReplaceProgress('Recherche läuft…');

  _replaceStopSSE = openSSE(jobId, {
    replace_stop_progress: (data) => {
      const msg = data.message || 'Wird bearbeitet…';
      _showReplaceProgress(msg);
    },
    replace_stop_complete: (data) => {
      if (_replaceStopSSE) { _replaceStopSSE.close(); _replaceStopSSE = null; }
      // data is the full updated plan
      data._saved_travel_id = travelId;
      S.result = data;
      lsSet(LS_RESULT, { jobId: data.job_id || jobId, savedAt: new Date().toISOString(), plan: data });
      _unlockEditing();
      closeReplaceStopModal();
      renderGuide(data, activeTab);
      if (typeof GoogleMaps !== 'undefined') GoogleMaps.setGuideMarkers(data, _onMarkerClick);
    },
    job_error: (data) => {
      if (_replaceStopSSE) { _replaceStopSSE.close(); _replaceStopSSE = null; }
      _unlockEditing();
      _hideReplaceProgress();
      alert('Fehler beim Ersetzen: ' + (data.error || 'Unbekannter Fehler'));
    },
    debug_log: (data) => {
      if (data.message) _showReplaceProgress(data.message);
    },
    onerror: () => {
      if (_replaceStopSSE) { _replaceStopSSE.close(); _replaceStopSSE = null; }
      _unlockEditing();
      alert('Verbindung verloren beim Ersetzen des Stopps.');
    },
  });
}

