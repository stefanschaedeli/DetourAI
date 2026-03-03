'use strict';

let routeMeta = {};
let _map = null;
let _mapMarkers = [];
let _mapLines = [];

// SSE connection for route-building phase (progressive option streaming)
let _routeSSE = null;
let _streamingOptions = [];    // options collected from SSE before HTTP response
let _streamingMeta = null;     // map_anchors from first route_option_ready event

function openRouteSSE(jobId) {
  if (_routeSSE) { _routeSSE.close(); _routeSSE = null; }
  _streamingOptions = [];
  _streamingMeta = null;

  _routeSSE = openSSE(jobId, {
    route_option_ready: onRouteOptionReady,
    route_options_done: onRouteOptionsDone,
    onerror: () => {},  // silently ignore — HTTP response is the fallback
  });
}

function closeRouteSSE() {
  if (_routeSSE) { _routeSSE.close(); _routeSSE = null; }
}

function onRouteOptionReady(data) {
  const opt = data.option;
  if (!opt) return;

  const alreadyShown = _streamingOptions.some(o => o.id === opt.id && o.option_type === opt.option_type);
  if (alreadyShown) return;

  _streamingOptions.push(opt);

  // Store map anchors from first event for later map init
  if (!_streamingMeta && data.map_anchors) {
    _streamingMeta = data.map_anchors;
  }

  // If we're in the loading state, switch container to card view
  const container = document.getElementById('route-options-container');
  if (!container) return;

  if (container.querySelector('.loading-spinner') || container.innerHTML === '') {
    container.innerHTML = '';
  }

  appendOptionCard(opt, _streamingOptions.length - 1);
}

function onRouteOptionsDone(data) {
  // All options arrived via SSE — init the map now that we have all coords
  const container = document.getElementById('route-options-container');
  if (!container) return;

  const anchors = _streamingMeta || data.map_anchors || {};
  const opts = data.options || _streamingOptions;
  _initMap(anchors, opts);
  closeRouteSSE();
}

function appendOptionCard(opt, i) {
  const container = document.getElementById('route-options-container');
  if (!container) return;

  // Remove route-complete message if present
  const completeMsg = container.querySelector('.route-complete-msg');
  if (completeMsg) completeMsg.remove();

  const flag = FLAGS[opt.country] || '';
  const driveKm = opt.drive_km ? ` · ${opt.drive_km} km` : '';
  const overLimit = opt.drives_over_limit;
  const driveWarning = overLimit
    ? `<span class="drive-over-limit-badge">⚠ Fahrzeit überschreitet Limit</span>`
    : '';
  const mapsLink = opt.maps_url
    ? `<a class="option-maps-link" href="${safeUrl(opt.maps_url)}" target="_blank" rel="noopener">&#x1F5FA; Google Maps</a>`
    : '';
  const extraFields = _buildExtraFields(opt);

  const card = document.createElement('div');
  card.className = `option-card${overLimit ? ' over-limit' : ''} option-card-streaming`;
  card.id = `option-card-${i}`;
  card.setAttribute('onclick', `selectOption(${i})`);
  card.innerHTML = `
    <div class="option-type-badge type-${esc(opt.option_type)}">${esc(opt.option_type)}</div>
    <h3>${flag} ${esc(opt.region)}, ${esc(opt.country)}</h3>
    <div class="option-meta">
      <span class="${overLimit ? 'drive-hours-over' : ''}">${opt.drive_hours}h Fahrt${driveKm}</span>
      <span>${opt.nights} Nacht${opt.nights !== 1 ? 'e' : ''}</span>
    </div>
    ${driveWarning}
    <p class="option-teaser">${esc(opt.teaser)}</p>
    <ul class="option-highlights">
      ${(opt.highlights || []).map(h => `<li>${esc(h)}</li>`).join('')}
    </ul>
    ${extraFields}
    ${mapsLink}
  `;

  // Trigger CSS fade-in
  requestAnimationFrame(() => {
    container.appendChild(card);
    requestAnimationFrame(() => card.classList.add('visible'));
  });
}

function startRouteBuilding(data) {
  S.selectedStops = [];
  routeMeta = data.meta || {};
  // Persist max_drive_hours from payload for use in all-over-limit banner
  const cachedForm = lsGet(LS_FORM);
  if (cachedForm && cachedForm.max_drive_hours_per_day) {
    routeMeta.max_drive_hours = cachedForm.max_drive_hours_per_day;
  }
  // If streaming already populated the container, only update state + map
  if (_streamingOptions.length >= (data.options || []).length && _streamingOptions.length > 0) {
    S.currentOptions = data.options || _streamingOptions;
    S.loadingOptions = false;
    closeRouteSSE();
    _updateRouteStatus(data.meta || {});
    renderBuiltStops();
    _initMap(data.meta?.map_anchors || _streamingMeta || {}, S.currentOptions);
    const confirmBtn = document.getElementById('confirm-route-btn');
    if (confirmBtn) confirmBtn.style.display = (data.meta || {}).route_could_be_complete ? 'block' : 'none';
    _streamingOptions = [];
    _streamingMeta = null;
    return;
  }
  _streamingOptions = [];
  _streamingMeta = null;
  closeRouteSSE();
  renderOptions(data.options || [], data.meta || {});
}

function _updateRouteStatus(meta) {
  const status = document.getElementById('route-status');
  if (!status) return;
  const stopNum = (meta.stop_number || 1);
  const daysRem = (meta.days_remaining || 0);
  const target  = meta.segment_target || '';
  const segInfo = meta.segment_count > 1
    ? ` (Segment ${(meta.segment_index || 0) + 1}/${meta.segment_count} → ${esc(target)})`
    : ` → ${esc(target)}`;
  status.innerHTML = `
    <div class="route-status-info">
      <strong>Stop #${stopNum}</strong>${segInfo}
      <span class="badge">${daysRem} Tage verbleibend</span>
    </div>
  `;
}

function renderOptions(options, meta) {
  routeMeta = meta || routeMeta;
  S.currentOptions = options;
  S.loadingOptions = false;

  const container = document.getElementById('route-options-container');
  const status    = document.getElementById('route-status');
  const confirmBtn = document.getElementById('confirm-route-btn');

  if (!container) return;

  // Status header
  const stopNum = (meta.stop_number || 1);
  const daysRem = (meta.days_remaining || 0);
  const target  = meta.segment_target || '';
  const segInfo = meta.segment_count > 1
    ? ` (Segment ${(meta.segment_index || 0) + 1}/${meta.segment_count} → ${esc(target)})`
    : ` → ${esc(target)}`;

  status.innerHTML = `
    <div class="route-status-info">
      <strong>Stop #${stopNum}</strong>${segInfo}
      <span class="badge">${daysRem} Tage verbleibend</span>
    </div>
  `;

  // Stops built so far
  renderBuiltStops();

  // Options cards
  if (options.length === 0 && meta.route_could_be_complete) {
    container.innerHTML = `
      <div class="route-complete-msg">
        <p>Die Route kann jetzt abgeschlossen werden.</p>
        <button class="btn btn-primary" onclick="confirmRoute()">Route bestätigen</button>
      </div>
    `;
    if (confirmBtn) confirmBtn.style.display = 'none';
    _clearMap();
    return;
  }

  const allOverLimit = options.length > 0 && options.every(o => o.drives_over_limit);

  container.innerHTML = options.map((opt, i) => {
    const flag = FLAGS[opt.country] || '';
    const driveKm = opt.drive_km ? ` · ${opt.drive_km} km` : '';
    const overLimit = opt.drives_over_limit;
    const driveWarning = overLimit
      ? `<span class="drive-over-limit-badge">⚠ Fahrzeit überschreitet Limit</span>`
      : '';
    const mapsLink = opt.maps_url
      ? `<a class="option-maps-link" href="${safeUrl(opt.maps_url)}" target="_blank" rel="noopener">&#x1F5FA; Google Maps</a>`
      : '';
    const extraFields = _buildExtraFields(opt);
    return `
      <div class="option-card${overLimit ? ' over-limit' : ''}" id="option-card-${i}" onclick="selectOption(${i})">
        <div class="option-type-badge type-${esc(opt.option_type)}">${esc(opt.option_type)}</div>
        <h3>${flag} ${esc(opt.region)}, ${esc(opt.country)}</h3>
        <div class="option-meta">
          <span class="${overLimit ? 'drive-hours-over' : ''}">${opt.drive_hours}h Fahrt${driveKm}</span>
          <span>${opt.nights} Nacht${opt.nights !== 1 ? 'e' : ''}</span>
        </div>
        ${driveWarning}
        <p class="option-teaser">${esc(opt.teaser)}</p>
        <ul class="option-highlights">
          ${(opt.highlights || []).map(h => `<li>${esc(h)}</li>`).join('')}
        </ul>
        ${extraFields}
        ${mapsLink}
      </div>
    `;
  }).join('');

  // Banner when ALL options exceed limit
  if (allOverLimit) {
    const banner = document.createElement('div');
    banner.className = 'all-over-limit-banner';
    banner.innerHTML = `
      <p>⚠ Alle vorgeschlagenen Etappen überschreiten die maximale Fahrzeit von ${routeMeta.max_drive_hours || ''}h.</p>
      <button class="btn btn-secondary" onclick="openRouteAdjustModal()">Route anpassen…</button>
    `;
    container.prepend(banner);
  }

  // Init Leaflet map
  _initMap(meta.map_anchors || {}, options);

  // Show confirm button if route could be complete
  if (confirmBtn) {
    confirmBtn.style.display = meta.route_could_be_complete ? 'block' : 'none';
  }
}

function _buildExtraFields(opt) {
  const parts = [];
  if (opt.population) parts.push(`<span class="opt-extra-tag">${esc(opt.population)}</span>`);
  if (opt.altitude_m) parts.push(`<span class="opt-extra-tag">${opt.altitude_m} m</span>`);
  if (opt.language) parts.push(`<span class="opt-extra-tag">${esc(opt.language)}</span>`);
  if (opt.climate_note) parts.push(`<span class="opt-extra-tag">${esc(opt.climate_note)}</span>`);
  if (opt.family_friendly === true) parts.push(`<span class="opt-extra-tag family">Familienfreundlich</span>`);
  if (opt.must_see && opt.must_see.length > 0) {
    parts.push(`<div class="opt-must-see">Must-see: ${opt.must_see.map(m => esc(m)).join(', ')}</div>`);
  }
  return parts.length > 0 ? `<div class="opt-extra-fields">${parts.join('')}</div>` : '';
}

function _initMap(anchors, options) {
  const mapEl = document.getElementById('route-map');
  if (!mapEl) return;

  if (!_map) {
    _map = L.map('route-map').setView([47, 8], 6);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(_map);
  } else {
    _mapMarkers.forEach(m => _map.removeLayer(m));
    _mapLines.forEach(l => _map.removeLayer(l));
    _mapMarkers = [];
    _mapLines = [];
  }

  const bounds = [];

  // Start pin (green)
  if (anchors.prev_lat && anchors.prev_lon) {
    const icon = L.divIcon({
      className: '',
      html: `<div class="map-marker-anchor start-pin">S</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    const m = L.marker([anchors.prev_lat, anchors.prev_lon], { icon })
      .bindPopup(`<b>Start: ${anchors.prev_label || ''}</b>`)
      .addTo(_map);
    _mapMarkers.push(m);
    bounds.push([anchors.prev_lat, anchors.prev_lon]);
  }

  // Segment target pin (red)
  if (anchors.target_lat && anchors.target_lon) {
    const icon = L.divIcon({
      className: '',
      html: `<div class="map-marker-anchor target-pin">Z</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    const m = L.marker([anchors.target_lat, anchors.target_lon], { icon })
      .bindPopup(`<b>Ziel: ${anchors.target_label || ''}</b>`)
      .addTo(_map);
    _mapMarkers.push(m);
    bounds.push([anchors.target_lat, anchors.target_lon]);
  }

  // Option pins (blue, numbered) + branch lines from start → option → target
  const startPt = (anchors.prev_lat && anchors.prev_lon) ? [anchors.prev_lat, anchors.prev_lon] : null;
  const targetPt = (anchors.target_lat && anchors.target_lon) ? [anchors.target_lat, anchors.target_lon] : null;
  const branchColors = ['#0071e3', '#1a7a1a', '#b36000'];

  options.filter(o => o.lat && o.lon).forEach((opt, i) => {
    const icon = L.divIcon({
      className: '',
      html: `<div class="map-marker-num">${i + 1}</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    const marker = L.marker([opt.lat, opt.lon], { icon })
      .bindPopup(`<b>${i + 1}. ${opt.region}</b><br>${opt.drive_hours}h · ${opt.drive_km || '?'} km`)
      .addTo(_map);
    marker.on('click', () => scrollToOption(i));
    _mapMarkers.push(marker);
    bounds.push([opt.lat, opt.lon]);

    const color = branchColors[i] || '#888';
    const optPt = [opt.lat, opt.lon];
    if (startPt) {
      const line = L.polyline([startPt, optPt], { color, weight: 2.5, dashArray: '6 5', opacity: 0.75 }).addTo(_map);
      _mapLines.push(line);
    }
    if (targetPt) {
      const line = L.polyline([optPt, targetPt], { color, weight: 2.5, dashArray: '6 5', opacity: 0.5 }).addTo(_map);
      _mapLines.push(line);
    }
  });

  if (bounds.length > 0) {
    _map.fitBounds(bounds, { padding: [40, 40], maxZoom: 9 });
  }

  setTimeout(() => { if (_map) _map.invalidateSize(); }, 100);
}

function _clearMap() {
  if (_map) {
    _mapMarkers.forEach(m => _map.removeLayer(m));
    _mapLines.forEach(l => _map.removeLayer(l));
    _mapMarkers = [];
    _mapLines = [];
  }
}

function scrollToOption(i) {
  document.getElementById(`option-card-${i}`)?.scrollIntoView({ behavior: 'smooth' });
}

function renderBuiltStops() {
  const list = document.getElementById('built-stops-list');
  if (!list) return;
  list.innerHTML = S.selectedStops.map((stop, i) => {
    const flag = FLAGS[stop.country] || '';
    return `
      <div class="built-stop">
        <div class="built-stop-number">${i + 1}</div>
        <div class="built-stop-info">
          <strong>${flag} ${esc(stop.region)}</strong>
          <span>${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''} · ${stop.drive_hours || stop.drive_hours_from_prev || 0}h Fahrt</span>
        </div>
      </div>
    `;
  }).join('');
}

async function selectOption(idx) {
  if (S.loadingOptions) return;
  S.loadingOptions = true;

  const cards = document.querySelectorAll('.option-card');
  cards.forEach((c, i) => c.classList.toggle('selected', i === idx));

  const container = document.getElementById('route-options-container');
  container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Nächste Optionen werden geladen…</p></div>';
  _clearMap();

  // Open SSE before HTTP call so we can stream options as they arrive
  if (S.jobId) openRouteSSE(S.jobId);

  try {
    const data = await apiSelectStop(S.jobId, idx);

    addBuiltStop(data.selected_stop);

    // Via-point was auto-added?
    if (data.via_point_added) {
      addBuiltStop(data.via_point_added);
    }

    saveRouteState();

    const options = data.options || [];
    const meta    = data.meta || {};

    if (options.length === 0 && meta.route_could_be_complete) {
      // Route done — show confirm
      renderOptions([], meta);
    } else if (options.length > 0) {
      renderOptions(options, meta);
    } else {
      // Unexpected: show confirm
      renderOptions([], meta);
    }

  } catch (err) {
    container.innerHTML = `<div class="error-msg">Fehler: ${esc(err.message)}</div>`;
    S.loadingOptions = false;
  }
}

function addBuiltStop(stop) {
  if (!stop) return;
  S.selectedStops.push(stop);
}

async function confirmRoute() {
  const btn = document.getElementById('confirm-route-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Bestätige…'; }
  S.confirmingRoute = true;

  try {
    const data = await apiConfirmRoute(S.jobId);
    S.allStops = data.selected_stops || [];

    // Show accommodation section and connect SSE BEFORE firing the prefetch,
    // so no accommodation_loaded events are missed.
    showSection('accommodation');
    startAccommodationPhase(data);

    // Wait for the EventSource connection to be established before triggering
    // the prefetch task — otherwise early SSE events may be lost.
    await connectAccommodationSSE(S.jobId);

    // Now trigger the prefetch — events will be received by the open SSE
    await apiStartAccommodations(S.jobId);

  } catch (err) {
    alert('Fehler beim Bestätigen der Route: ' + err.message);
    if (btn) { btn.disabled = false; btn.textContent = 'Route bestätigen'; }
    S.confirmingRoute = false;
  }
}

function backToForm() {
  showSection('form-section');
}

function saveRouteState() {
  const stopsObj = {};
  const stopsOrder = [];
  S.selectedStops.forEach(s => {
    stopsObj[s.id] = s;
    stopsOrder.push(s.id);
  });
  lsSet(LS_ROUTE, { jobId: S.jobId, stops: stopsObj, stopsOrder });
}

async function recomputeOptions() {
  const input = document.getElementById('recompute-input');
  if (!input || S.loadingOptions) return;
  S.loadingOptions = true;

  const extra = input.value.trim();
  const container = document.getElementById('route-options-container');
  container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Neue Optionen werden berechnet…</p></div>';
  _clearMap();

  if (S.jobId) openRouteSSE(S.jobId);

  try {
    const data = await apiRecomputeOptions(S.jobId, extra);
    input.value = '';
    renderOptions(data.options || [], data.meta || {});
  } catch (err) {
    container.innerHTML = `<div class="error-msg">Fehler: ${esc(err.message)}</div>`;
    S.loadingOptions = false;
  }
}

function searchNextStop() {
  // Manual trigger if needed
  if (S.currentOptions.length > 0) {
    renderOptions(S.currentOptions, routeMeta);
  }
}

// ---------------------------------------------------------------------------
// Route-adjust modal (shown when all options exceed drive limit)
// ---------------------------------------------------------------------------

function openRouteAdjustModal() {
  const existing = document.getElementById('route-adjust-modal');
  if (existing) existing.remove();

  const maxH = routeMeta.max_drive_hours || 4.5;
  const overlay = document.createElement('div');
  overlay.id = 'route-adjust-modal';
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-box">
      <button class="modal-close" onclick="closeRouteAdjustModal()">×</button>
      <h3 class="modal-title">Route anpassen</h3>
      <p class="modal-desc">
        Alle vorgeschlagenen Etappen überschreiten die maximale Fahrzeit von <strong>${maxH}h</strong>.
        Wählen Sie eine Lösung:
      </p>

      <div class="modal-option" id="modal-opt-days">
        <label class="modal-option-header">
          <input type="radio" name="adjust-action" value="add_days" checked>
          <span>Reisedauer verlängern</span>
        </label>
        <p class="modal-option-desc">Mehr Tage einplanen, damit kürzere Tagesetappen möglich werden.</p>
        <div class="modal-option-detail" id="modal-detail-days">
          <label>Zusätzliche Tage:
            <select id="modal-extra-days">
              <option value="1">+ 1 Tag</option>
              <option value="2" selected>+ 2 Tage</option>
              <option value="3">+ 3 Tage</option>
              <option value="5">+ 5 Tage</option>
            </select>
          </label>
        </div>
      </div>

      <div class="modal-option" id="modal-opt-via">
        <label class="modal-option-header">
          <input type="radio" name="adjust-action" value="add_via_point">
          <span>Zwischenstopp einfügen</span>
        </label>
        <p class="modal-option-desc">Einen fixen Routenpunkt einfügen, der die Etappe verkürzt.</p>
        <div class="modal-option-detail" id="modal-detail-via" style="display:none">
          <label>Ortschaft:
            <input type="text" id="modal-via-input" placeholder="z.B. Bern, Schweiz" style="width:100%;margin-top:6px">
          </label>
        </div>
      </div>

      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="closeRouteAdjustModal()">Abbrechen</button>
        <button class="btn btn-primary" onclick="applyRouteAdjust()">Anwenden</button>
      </div>
    </div>
  `;

  // Toggle detail panels on radio change
  overlay.querySelectorAll('input[name="adjust-action"]').forEach(r => {
    r.addEventListener('change', () => {
      document.getElementById('modal-detail-days').style.display =
        r.value === 'add_days' ? '' : 'none';
      document.getElementById('modal-detail-via').style.display =
        r.value === 'add_via_point' ? '' : 'none';
    });
  });

  // Close on backdrop click
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeRouteAdjustModal();
  });

  document.body.appendChild(overlay);
}

function closeRouteAdjustModal() {
  const m = document.getElementById('route-adjust-modal');
  if (m) m.remove();
}

async function applyRouteAdjust() {
  const action = document.querySelector('input[name="adjust-action"]:checked')?.value;
  if (!action) return;

  const extraDays = parseInt(document.getElementById('modal-extra-days')?.value) || 2;
  const viaLoc = (document.getElementById('modal-via-input')?.value || '').trim();

  if (action === 'add_via_point' && !viaLoc) {
    alert('Bitte eine Ortschaft für den Zwischenstopp eingeben.');
    return;
  }

  closeRouteAdjustModal();
  S.loadingOptions = true;

  const container = document.getElementById('route-options-container');
  container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Route wird angepasst…</p></div>';
  _clearMap();

  if (S.jobId) openRouteSSE(S.jobId);

  try {
    const data = await apiPatchJob(S.jobId, action, extraDays, viaLoc);
    // Update persisted max_drive_hours if total_days changed
    if (data.meta && data.meta.total_days) {
      routeMeta.max_drive_hours = routeMeta.max_drive_hours; // unchanged — only days shift
    }
    renderOptions(data.options || [], data.meta || {});
  } catch (err) {
    container.innerHTML = `<div class="error-msg">Fehler beim Anpassen: ${esc(err.message)}</div>`;
    S.loadingOptions = false;
  }
}
