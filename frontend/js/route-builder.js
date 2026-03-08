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
    debug_log:          _onRouteBuildDebugLog,
    onerror: () => {},  // silently ignore — HTTP response is the fallback
  });
}

function _showSkeletonCards() {
  const container = document.getElementById('route-options-container');
  if (!container) return;
  container.innerHTML = [0, 1, 2].map(i => `
    <div class="option-card option-skeleton" id="option-slot-${i}">
      <div class="skeleton-badge shimmer-elem"></div>
      <div class="skeleton-title shimmer-elem"></div>
      <div class="skeleton-meta shimmer-elem"></div>
      <div class="skeleton-line shimmer-elem"></div>
      <div class="skeleton-line shimmer-elem short"></div>
    </div>
  `).join('');
}

function closeRouteSSE() {
  if (_routeSSE) { _routeSSE.close(); _routeSSE = null; }
}

function _onRouteBuildDebugLog(data) {
  const msg = data.message || '';
  if (msg.startsWith('Neue Reise:')) {
    progressOverlay.addLine('trip_init', 'Reisedaten werden analysiert…');
    progressOverlay.completeLine('trip_init', '');
  } else if (msg.startsWith('Route-Optionen:')) {
    const m = msg.match(/Route-Optionen:\s*(.+?)\s*\(/);
    const label = m ? m[1] : 'Route';
    progressOverlay.addLine('route_options', `Suche Zwischenstopps von ${label}…`);
  } else if (msg.includes('Retry mit Abstandshinweis')) {
    progressOverlay.completeLine('route_options', '');
    progressOverlay.addLine('route_options_retry', 'Suche Zwischenstopps — zweiter Versuch…');
  } else if (msg.includes('DetourOptionsAgent')) {
    progressOverlay.addLine('route_detour', 'Suche Umweg-Optionen seitlich der Route…');
  }
}

function showRundreiseModal(meta) {
  document.getElementById('rundreise-modal')?.remove();
  const ratio = ((meta || {}).rundreise_threshold_ratio || 2).toFixed(1);
  const target = esc((meta || {}).segment_target || '');
  const overlay = document.createElement('div');
  overlay.id = 'rundreise-modal';
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-box">
      <h3 class="modal-title">Rundreise-Modus</h3>
      <p class="modal-desc">Du hast <strong>${ratio}×</strong> mehr Zeit als für die direkte
        Route nach <strong>${target}</strong> nötig wäre. Möchtest du bewusste Umwege
        erkunden statt der direkten Strecke zu folgen?</p>
      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="declineRundreise()">Nein, direkte Route</button>
        <button class="btn btn-primary" onclick="activateRundreise()">Ja, Umwege erkunden</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
}

function _closeRundreiseModal() { document.getElementById('rundreise-modal')?.remove(); }

async function activateRundreise() { _closeRundreiseModal(); await _applyRundreiseChoice(true); }
async function declineRundreise()  { _closeRundreiseModal(); await _applyRundreiseChoice(false); }

async function _applyRundreiseChoice(activate) {
  progressOverlay.open('Alternativen werden gesucht…');
  openRouteSSE(S.jobId);
  _showSkeletonCards();
  try {
    const data = await apiSetRundreiseMode(S.jobId, activate);
    startRouteBuilding(data);
  } catch (err) {
    const container = document.getElementById('route-options-container');
    if (container) container.innerHTML = `<div class="error-msg">Fehler: ${esc(err.message)}</div>`;
    S.loadingOptions = false;
  }
}

function onRouteOptionReady(data) {
  const opt = data.option;
  if (!opt) return;

  const optIndex = data.option_index ?? _streamingOptions.length;

  // Dedup: ignore if we already have this slot filled
  if (_streamingOptions[optIndex] != null) return;

  _streamingOptions[optIndex] = opt;

  // Store map anchors from first event
  if (!_streamingMeta && data.map_anchors) {
    _streamingMeta = data.map_anchors;
  }

  // Replace skeleton slot with real card
  const slot = document.getElementById(`option-slot-${optIndex}`);
  if (slot) {
    _replaceSkeletonWithCard(slot, opt, optIndex);
  } else {
    // No skeleton (e.g. first load before skeleton was shown) — append
    appendOptionCard(opt, optIndex);
  }

  const regionName = opt.region || '';
  progressOverlay.addLine(`option_${optIndex}`, `Option ${optIndex + 1} gefunden: ${regionName}`);
  progressOverlay.completeLine(`option_${optIndex}`, '');
}

function _insertDetourBanner() {
  const container = document.getElementById('route-options-container');
  if (!container || container.querySelector('.detour-banner')) return;
  const banner = document.createElement('div');
  banner.className = 'detour-banner';
  banner.innerHTML = `<strong>Umweg-Optionen:</strong> Auf dieser Strecke gibt es zu wenig Raum für einen klassischen Zwischenstopp. Diese Orte liegen seitlich der Route und machen die Reise abwechslungsreicher — von dort ist das Ziel weiterhin erreichbar.`;
  container.prepend(banner);
}

function onRouteOptionsDone(data) {
  // All options arrived via SSE — init the map now that we have all coords
  const container = document.getElementById('route-options-container');
  if (!container) return;

  const anchors = _streamingMeta || data.map_anchors || {};
  const opts = data.options || _streamingOptions;
  const count = opts.length;
  progressOverlay.completeLine('route_options', `${count} Optionen gefunden`);
  progressOverlay.completeLine('route_options_retry', `${count} Optionen gefunden`);
  progressOverlay.completeLine('route_detour', 'Umwege gefunden');
  progressOverlay.close();

  const allDetour = opts.length > 0 && opts.every(o => o.is_detour);
  if (allDetour) { _insertDetourBanner(); }
  _initMap(anchors, opts);
  closeRouteSSE();
}

function _buildOptionCardHTML(opt, i) {
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
  return {
    classes: `option-card${overLimit ? ' over-limit' : ''}`,
    id: `option-card-${i}`,
    html: `
      <div class="option-card-header">
        <span class="option-card-number">${i + 1}</span>
        <div class="option-type-badge type-${esc(opt.option_type)}">${esc(opt.option_type)}</div>
      </div>
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
    `,
  };
}

function _replaceSkeletonWithCard(slotEl, opt, i) {
  const { classes, id, html } = _buildOptionCardHTML(opt, i);
  slotEl.className = classes + ' option-card-streaming';
  slotEl.id = id;
  slotEl.setAttribute('onclick', `selectOption(${i})`);
  slotEl.innerHTML = html;
  requestAnimationFrame(() => requestAnimationFrame(() => slotEl.classList.add('visible')));
}

function appendOptionCard(opt, i) {
  const container = document.getElementById('route-options-container');
  if (!container) return;

  const { classes, id, html } = _buildOptionCardHTML(opt, i);
  const card = document.createElement('div');
  card.className = classes + ' option-card-streaming';
  card.id = id;
  card.setAttribute('onclick', `selectOption(${i})`);
  card.innerHTML = html;

  requestAnimationFrame(() => {
    container.appendChild(card);
    requestAnimationFrame(() => card.classList.add('visible'));
  });
}

function startRouteBuilding(data) {
  if ((data.meta || {}).rundreise_suggestion) {
    const container = document.getElementById('route-options-container');
    if (container) container.innerHTML = '';
    closeRouteSSE();
    showRundreiseModal(data.meta);
    return;
  }
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
  const allDetour = options.length > 0 && options.every(o => o.is_detour);

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
        <div class="option-card-header">
          <span class="option-card-number">${i + 1}</span>
          <div class="option-type-badge type-${esc(opt.option_type)}">${esc(opt.option_type)}</div>
        </div>
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

  if (allDetour) {
    const banner = document.createElement('div');
    banner.className = 'detour-banner';
    banner.innerHTML = `<strong>Umweg-Optionen:</strong> Auf dieser Strecke gibt es zu wenig Raum für einen klassischen Zwischenstopp. Diese Orte liegen seitlich der Route und machen die Reise abwechslungsreicher — von dort ist das Ziel weiterhin erreichbar.`;
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
    const tooltipHtml = `<div class="map-marker-tooltip">` +
      `<strong>${i + 1}. ${esc(opt.region)}</strong>` +
      `<div>${opt.drive_hours}h Fahrt · ${opt.drive_km || '?'} km</div>` +
      `<div>${opt.nights} Nacht${opt.nights !== 1 ? 'e' : ''}</div>` +
      (opt.teaser ? `<div class="tooltip-teaser">${esc(opt.teaser)}</div>` : '') +
      `</div>`;
    const marker = L.marker([opt.lat, opt.lon], { icon })
      .bindTooltip(tooltipHtml, { className: 'map-marker-tooltip-wrap', direction: 'top', offset: [0, -14] })
      .addTo(_map);
    marker.on('click', () => selectOption(i));
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

  _clearMap();

  // Open SSE + show skeletons before HTTP call — options stream in progressively
  if (S.jobId) openRouteSSE(S.jobId);
  _showSkeletonCards();

  try {
    const data = await apiSelectStop(S.jobId, idx);

    addBuiltStop(data.selected_stop);
    if (data.via_point_added) addBuiltStop(data.via_point_added);
    saveRouteState();

    const options = data.options || [];
    const meta    = data.meta || {};

    if (options.length === 0 && meta.route_could_be_complete) {
      // Route done — close SSE and show confirm
      closeRouteSSE();
      _streamingOptions = [];
      renderOptions([], meta);
    } else if (_streamingOptions.filter(Boolean).length >= options.length && options.length > 0) {
      // Streaming already delivered all cards — just update state/map/status
      S.currentOptions = options;
      S.loadingOptions = false;
      closeRouteSSE();
      _updateRouteStatus(meta);
      renderBuiltStops();
      _initMap(meta.map_anchors || _streamingMeta || {}, options);
      const confirmBtn = document.getElementById('confirm-route-btn');
      if (confirmBtn) confirmBtn.style.display = meta.route_could_be_complete ? 'block' : 'none';
      _streamingOptions = [];
      _streamingMeta = null;
    } else {
      // Streaming didn't finish yet or SSE unavailable — render from HTTP response
      closeRouteSSE();
      _streamingOptions = [];
      renderOptions(options, meta);
    }

  } catch (err) {
    const container = document.getElementById('route-options-container');
    if (container) container.innerHTML = `<div class="error-msg">Fehler: ${esc(err.message)}</div>`;
    closeRouteSSE();
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
    progressOverlay.open('Unterkunftsoptionen werden gesucht…');

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
  _clearMap();
  if (S.jobId) {
    progressOverlay.open('Neu berechnung…');
    openRouteSSE(S.jobId);
  }
  _showSkeletonCards();

  try {
    const data = await apiRecomputeOptions(S.jobId, extra);
    input.value = '';
    const options = data.options || [];
    const meta = data.meta || {};
    if (_streamingOptions.filter(Boolean).length >= options.length && options.length > 0) {
      S.currentOptions = options;
      S.loadingOptions = false;
      closeRouteSSE();
      _updateRouteStatus(meta);
      renderBuiltStops();
      _initMap(meta.map_anchors || _streamingMeta || {}, options);
      _streamingOptions = [];
      _streamingMeta = null;
    } else {
      closeRouteSSE();
      _streamingOptions = [];
      renderOptions(options, meta);
    }
  } catch (err) {
    const container = document.getElementById('route-options-container');
    if (container) container.innerHTML = `<div class="error-msg">Fehler: ${esc(err.message)}</div>`;
    closeRouteSSE();
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

  _clearMap();
  if (S.jobId) openRouteSSE(S.jobId);
  _showSkeletonCards();

  try {
    const data = await apiPatchJob(S.jobId, action, extraDays, viaLoc);
    const options = data.options || [];
    const meta = data.meta || {};
    if (_streamingOptions.filter(Boolean).length >= options.length && options.length > 0) {
      S.currentOptions = options;
      S.loadingOptions = false;
      closeRouteSSE();
      _updateRouteStatus(meta);
      renderBuiltStops();
      _initMap(meta.map_anchors || _streamingMeta || {}, options);
      _streamingOptions = [];
      _streamingMeta = null;
    } else {
      closeRouteSSE();
      _streamingOptions = [];
      renderOptions(options, meta);
    }
  } catch (err) {
    const container = document.getElementById('route-options-container');
    if (container) container.innerHTML = `<div class="error-msg">Fehler beim Anpassen: ${esc(err.message)}</div>`;
    closeRouteSSE();
    S.loadingOptions = false;
  }
}
