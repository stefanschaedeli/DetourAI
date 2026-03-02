'use strict';

let routeMeta = {};
let _map = null;
let _mapMarkers = [];
let _mapLines = [];

function startRouteBuilding(data) {
  S.selectedStops = [];
  routeMeta = data.meta || {};
  renderOptions(data.options || [], data.meta || {});
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

  container.innerHTML = options.map((opt, i) => {
    const flag = FLAGS[opt.country] || '';
    const driveKm = opt.drive_km ? ` · ${opt.drive_km} km` : '';
    const mapsLink = opt.maps_url
      ? `<a class="option-maps-link" href="${esc(opt.maps_url)}" target="_blank" rel="noopener">&#x1F5FA; Google Maps</a>`
      : '';
    const extraFields = _buildExtraFields(opt);
    return `
      <div class="option-card" id="option-card-${i}" onclick="selectOption(${i})">
        <div class="option-type-badge type-${esc(opt.option_type)}">${esc(opt.option_type)}</div>
        <h3>${flag} ${esc(opt.region)}, ${esc(opt.country)}</h3>
        <div class="option-meta">
          <span>${opt.drive_hours}h Fahrt${driveKm}</span>
          <span>${opt.nights} Nacht${opt.nights !== 1 ? 'e' : ''}</span>
        </div>
        <p class="option-teaser">${esc(opt.teaser)}</p>
        <ul class="option-highlights">
          ${(opt.highlights || []).map(h => `<li>${esc(h)}</li>`).join('')}
        </ul>
        ${extraFields}
        ${mapsLink}
      </div>
    `;
  }).join('');

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
