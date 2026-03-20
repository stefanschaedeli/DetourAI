'use strict';

let routeMeta = {};
let _rbMarkers = [];
let _rbPolylines = [];
let _rbMapGeneration = 0;  // stale-request guard for async route rendering

// SSE connection for route-building phase (progressive option streaming)
let _routeSSE = null;
let _streamingOptions = [];    // options collected from SSE before HTTP response
let _streamingMeta = null;     // map_anchors from first route_option_ready event

function openRouteSSE(jobId) {
  if (_routeSSE) { _routeSSE.close(); _routeSSE = null; }
  _streamingOptions = [];
  _streamingMeta = null;

  _routeSSE = openSSE(jobId, {
    route_option_ready:     onRouteOptionReady,
    route_options_done:     onRouteOptionsDone,
    debug_log:              _onRouteBuildDebugLog,
    region_plan_ready: data => { showRegionPlanUI(data.regions, data.summary, data.leg_id); },
    region_updated:    data => { updateRegionPlanUI(data.regions, data.summary); },
    leg_complete:           data => { console.log(`Schnitt ${(data.leg_index || 0) + 1} abgeschlossen (${data.mode || ''})`); },
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
  } else if (msg.includes('Verworfen (zu nahe am Startpunkt')) {
    // Extract place name — format: "  Verworfen (zu nahe am Startpunkt X: N km < M km): PLACE"
    const place = msg.match(/:\s*([^)]+)\s*$/)?.[1]?.trim() || '';
    progressOverlay.addLine('rejected_' + place, `${place} — zu nahe am Startpunkt, wird übersprungen`);
    progressOverlay.completeLine('rejected_' + place, '');
  } else if (msg.includes('Verworfen (zu nahe am Ziel')) {
    const place = msg.match(/:\s*([^)]+)\s*$/)?.[1]?.trim() || '';
    progressOverlay.addLine('rejected_z_' + place, `${place} — zu nahe am Ziel, wird übersprungen`);
    progressOverlay.completeLine('rejected_z_' + place, '');
  } else if (msg.match(/Nur \d+ gültige Option/)) {
    const n = msg.match(/Nur (\d+)/)?.[1] || '0';
    progressOverlay.completeLine('route_options', '');
    progressOverlay.addLine('route_options_retry',
      `Nur ${n} brauchbare Option${n === '1' ? '' : 'en'} — suche weiter…`);
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

function onRouteOptionsDone(data) {
  if (data.no_stops_found) {
    _showNoStopsFoundUI(data.corridor);
    return;
  }

  // All options arrived via SSE — close overlay first, then init map
  const opts = data.options || _streamingOptions;
  const count = opts.length;
  progressOverlay.completeLine('route_options', `${count} Optionen gefunden`);
  progressOverlay.completeLine('route_options_retry', `${count} Optionen gefunden`);
  progressOverlay.completeLine('route_detour', 'Umwege gefunden');
  progressOverlay.close();

  const container = document.getElementById('route-options-container');
  if (!container) return;

  const anchors = _streamingMeta || data.map_anchors || {};

  _initMap(anchors, opts);
  closeRouteSSE();
}

function _buildOptionCardHTML(opt, i) {
  const flag = FLAGS[opt.country] || '';
  const driveKm = opt.drive_km ? ` · ${opt.drive_km} km` : '';
  const overLimit = opt.drives_over_limit;
  const driveWarning = overLimit
    ? `<span class="drive-over-limit-badge"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12" style="vertical-align:-1px;margin-right:3px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>Fahrzeit überschreitet Limit</span>`
    : '';
  const mapsLink = opt.maps_url
    ? `<a class="option-maps-link" href="${safeUrl(opt.maps_url)}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13" style="vertical-align:-2px;margin-right:3px"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>Google Maps</a>`
    : '';
  const extraFields = _buildExtraFields(opt);
  return {
    classes: `option-card${overLimit ? ' over-limit' : ''}`,
    id: `option-card-${i}`,
    html: `
      ${buildHeroPhotoLoading('md')}
      <div class="option-card-body" onclick="selectOption(${i})">
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
    `,
  };
}

function _replaceSkeletonWithCard(slotEl, opt, i) {
  const { classes, id, html } = _buildOptionCardHTML(opt, i);
  slotEl.className = classes + ' option-card-streaming';
  slotEl.id = id;
  slotEl.removeAttribute('onclick');
  slotEl.innerHTML = html;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    slotEl.classList.add('visible');
    if (opt.lat && opt.lon && typeof _lazyLoadEntityImages === 'function') {
      _lazyLoadEntityImages(slotEl, opt.region, opt.lat, opt.lon, 'city');
    }
  }));
}

function appendOptionCard(opt, i) {
  const container = document.getElementById('route-options-container');
  if (!container) return;

  const { classes, id, html } = _buildOptionCardHTML(opt, i);
  const card = document.createElement('div');
  card.className = classes + ' option-card-streaming';
  card.id = id;
  card.innerHTML = html;

  requestAnimationFrame(() => {
    container.appendChild(card);
    requestAnimationFrame(() => {
      card.classList.add('visible');
      if (opt.lat && opt.lon && typeof _lazyLoadEntityImages === 'function') {
        _lazyLoadEntityImages(card, opt.region, opt.lat, opt.lon, 'city');
      }
    });
  });
}

function startRouteBuilding(data) {
  progressOverlay.close();  // immer schliessen — idempotent
  S.selectedStops = [];
  routeMeta = data.meta || {};
  // Persist max_drive_hours from payload for use in all-over-limit banner
  const cachedForm = lsGet(LS_FORM);
  if (cachedForm && cachedForm.max_drive_hours_per_day) {
    routeMeta.max_drive_hours = cachedForm.max_drive_hours_per_day;
  }
  // Explore-Modus: Region-Plan wird angezeigt via SSE region_plan_ready
  if (data.explore_pending) {
    S.loadingOptions = false;
    _updateRouteStatus(data.meta || {});
    renderBuiltStops();
    // If region_plan is included directly (non-SSE path), show it immediately
    if (data.region_plan) {
      showRegionPlanUI(data.region_plan.regions, data.region_plan.summary, data.meta?.leg_id || '');
    }
    return;
  }

  // If streaming already populated the container, only update state + map
  if (_streamingOptions.length >= (data.options || []).length && _streamingOptions.length > 0) {
    // Region-Plan-Panel entfernen und Options-Panel wieder anzeigen
    const regionPanel = document.getElementById('region-plan-panel');
    if (regionPanel) regionPanel.remove();
    const optionsPanel = document.getElementById('options-panel');
    if (optionsPanel) optionsPanel.style.display = '';

    S.currentOptions = data.options || _streamingOptions;
    S.loadingOptions = false;
    progressOverlay.close();
    closeRouteSSE();
    _updateRouteStatus(data.meta || {});
    renderBuiltStops();
    _initMap(data.meta?.map_anchors || _streamingMeta || {}, S.currentOptions);
    _appendSkipCardFromMeta();
    const confirmBtn = document.getElementById('confirm-route-btn');
    if (confirmBtn) confirmBtn.style.display = (data.meta || {}).route_could_be_complete ? 'block' : 'none';
    _streamingOptions = [];
    _streamingMeta = null;
    return;
  }
  _streamingOptions = [];
  _streamingMeta = null;
  progressOverlay.close();
  closeRouteSSE();
  renderOptions(data.options || [], data.meta || {});
}

function _updateRouteStatus(meta) {
  const subtitle = document.getElementById('route-subtitle');
  if (!subtitle) return;
  const stopNum = (meta.stop_number || 1);
  const daysRem = (meta.days_remaining || 0);
  const target  = meta.segment_target || '';
  const segInfo = meta.segment_count > 1
    ? `Segment ${(meta.segment_index || 0) + 1}/${meta.segment_count} → ${esc(target)}`
    : target ? `→ ${esc(target)}` : '';

  const totalLegs = meta.total_legs || 1;
  const legIdx = meta.leg_index || 0;
  const legMode = meta.leg_mode || 'transit';
  const modeLabel = legMode === 'explore' ? 'Erkunden' : 'Transit';
  const legInfo = totalLegs > 1
    ? `Etappe ${legIdx + 1}/${totalLegs} (${modeLabel})`
    : '';

  const parts = [legInfo, `Stop #${stopNum}`, segInfo, daysRem ? `${daysRem} Tage verbleibend` : ''].filter(Boolean);
  subtitle.textContent = parts.join(' · ');

  // Update options count badge
  const countBadge = document.getElementById('options-count');
  if (countBadge && S.currentOptions) {
    countBadge.textContent = `${S.currentOptions.length} Optionen`;
  }
}

function _renderSkipCard(target, skipBonus) {
  const label = skipBonus > 0
    ? `+${skipBonus} Nacht${skipBonus !== 1 ? 'e' : ''} am Ziel`
    : '';
  return `
    <div class="option-card skip-card" id="option-card-skip" onclick="skipStop()">
      <div class="option-card-header">
        <span class="option-card-number skip-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="14" height="14"><polyline points="9 6 15 12 9 18"/></svg></span>
        <div class="option-type-badge type-direct">Direkt</div>
      </div>
      <h3>Direkt nach ${esc(target)} fahren</h3>
      <div class="option-meta">
        <span>Kein Zwischenstopp</span>
        ${label ? `<span class="skip-bonus-badge">${esc(label)}</span>` : ''}
      </div>
      <p class="option-teaser">Übrige Reisetage werden am Ziel verbracht — mehr Zeit vor Ort statt auf der Durchreise.</p>
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

  // Region-Plan-Panel entfernen und Options-Panel wieder anzeigen
  const regionPanel = document.getElementById('region-plan-panel');
  if (regionPanel) regionPanel.remove();
  const optionsPanel = document.getElementById('options-panel');
  if (optionsPanel) optionsPanel.style.display = '';

  // Status header — delegate to shared function
  _updateRouteStatus(meta);

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
    const { classes, id, html } = _buildOptionCardHTML(opt, i);
    return `<div class="${classes}" id="${id}">${html}</div>`;
  }).join('');

  // Lazy-load photos for all rendered option cards
  requestAnimationFrame(() => {
    options.forEach((opt, i) => {
      if (opt.lat && opt.lon && typeof _lazyLoadEntityImages === 'function') {
        const cardEl = document.getElementById(`option-card-${i}`);
        if (cardEl) _lazyLoadEntityImages(cardEl, opt.region, opt.lat, opt.lon, 'city');
      }
    });
  });

  // Banner when ALL options exceed limit
  if (allOverLimit) {
    const banner = document.createElement('div');
    banner.className = 'all-over-limit-banner';
    banner.innerHTML = `
      <p><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14" style="vertical-align:-2px;margin-right:4px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>Alle vorgeschlagenen Etappen überschreiten die maximale Fahrzeit von ${routeMeta.max_drive_hours || ''}h.</p>
      <button class="btn btn-secondary" onclick="openRouteAdjustModal()">Route anpassen…</button>
    `;
    container.prepend(banner);
  }

  // Segment-Kontext-Banner (Von → Nach)
  const prevLabel = (routeMeta.map_anchors || {}).prev_label || '';
  const targetLabel = routeMeta.segment_target || '';
  if (prevLabel || targetLabel) {
    const ctxBanner = document.createElement('div');
    ctxBanner.className = 'segment-context-banner';
    ctxBanner.innerHTML = `
      <span class="segment-from"><span class="segment-label">Von</span>${esc(prevLabel)}</span>
      <span class="segment-arrow">→</span>
      <span class="segment-to"><span class="segment-label">Nach</span>${esc(targetLabel)}</span>
    `;
    container.prepend(ctxBanner);
  }

  // Skip card — always shown when there are option cards (options.length > 0)
  if (options.length > 0) {
    container.insertAdjacentHTML('beforeend',
      _renderSkipCard(meta.segment_target || '', meta.skip_nights_bonus || 0));
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
  if (typeof GoogleMaps === 'undefined' || !window.google) {
    if (typeof S !== 'undefined') {
      S.logs.push({ level: 'WARNING', agent: 'GoogleMaps', message: 'Karte nicht geladen — Google Maps API nicht verfügbar' });
      if (typeof updateDebugLog === 'function') updateDebugLog();
    }
    return;
  }

  const map = GoogleMaps.initRouteMap('route-map', { center: { lat: 47, lng: 8 }, zoom: 6 });
  if (!map) return;

  _clearMap();

  // Always use the last confirmed stop's coordinates as S-marker
  const lastStop = S.selectedStops.length > 0 ? S.selectedStops[S.selectedStops.length - 1] : null;
  if (lastStop && lastStop.lat && lastStop.lon) {
    anchors = { ...anchors, prev_lat: lastStop.lat, prev_lon: lastStop.lon, prev_label: lastStop.region };
  }

  const bounds = new google.maps.LatLngBounds();
  let hasBounds = false;

  // Start pin (green S)
  if (anchors.prev_lat && anchors.prev_lon) {
    const pos = { lat: anchors.prev_lat, lng: anchors.prev_lon };
    const infoWin = new google.maps.InfoWindow({ content: `<b>Start: ${esc(anchors.prev_label || '')}</b>` });
    const m = GoogleMaps.createDivMarker(map, pos,
      `<div class="map-marker-anchor start-pin">S</div>`,
      () => infoWin.open({ map, position: pos })
    );
    _rbMarkers.push(m);
    bounds.extend(pos);
    hasBounds = true;
  }

  // Segment target pin (red Z)
  if (anchors.target_lat && anchors.target_lon) {
    const pos = { lat: anchors.target_lat, lng: anchors.target_lon };
    const infoWin = new google.maps.InfoWindow({ content: `<b>Ziel: ${esc(anchors.target_label || '')}</b>` });
    const m = GoogleMaps.createDivMarker(map, pos,
      `<div class="map-marker-anchor target-pin">Z</div>`,
      () => infoWin.open({ map, position: pos })
    );
    _rbMarkers.push(m);
    bounds.extend(pos);
    hasBounds = true;
  }

  // Option pins (numbered) + dashed branch lines
  const startPt = (anchors.prev_lat && anchors.prev_lon)
    ? new google.maps.LatLng(anchors.prev_lat, anchors.prev_lon) : null;
  const targetPt = (anchors.target_lat && anchors.target_lon)
    ? new google.maps.LatLng(anchors.target_lat, anchors.target_lon) : null;
  const branchColors = ['#0071e3', '#1a7a1a', '#b36000'];

  const dashedIcon = {
    path: 'M 0,-1 0,1',
    strokeOpacity: 1,
    scale: 3,
  };

  const routePromises = [];
  const genBefore = _rbMapGeneration;

  options.filter(o => o.lat && o.lon).forEach((opt, i) => {
    const pos = { lat: opt.lat, lng: opt.lon };
    const tooltipContent = `<div class="map-marker-tooltip">` +
      `<strong>${i + 1}. ${esc(opt.region)}</strong>` +
      `<div>${opt.drive_hours}h Fahrt · ${opt.drive_km || '?'} km</div>` +
      `<div>${opt.nights} Nacht${opt.nights !== 1 ? 'e' : ''}</div>` +
      (opt.teaser ? `<div class="tooltip-teaser">${esc(opt.teaser)}</div>` : '') +
      `</div>`;
    const infoWin = new google.maps.InfoWindow({ content: tooltipContent });
    const m = (opt.place_id
      ? GoogleMaps.createPlaceMarker(map, opt.place_id, pos, `<div class="map-marker-num">${i + 1}</div>`, () => { infoWin.open({ map, position: pos }); selectOption(i); })
      : GoogleMaps.createDivMarker(map, pos, `<div class="map-marker-num">${i + 1}</div>`, () => { infoWin.open({ map, position: pos }); selectOption(i); }));
    _rbMarkers.push(m);
    bounds.extend(pos);
    hasBounds = true;

    const color = branchColors[i] || '#888';
    const optPos = { lat: opt.lat, lng: opt.lon };

    // Queue driving route requests (resolved below in parallel)
    if (startPt) {
      routePromises.push(GoogleMaps.renderDrivingRoute(map,
        [{ lat: startPt.lat(), lng: startPt.lng() }, optPos],
        { strokeColor: color, strokeOpacity: 0, strokeWeight: 2,
          icons: [{ icon: { ...dashedIcon, strokeColor: color, strokeOpacity: 0.8 }, offset: '0', repeat: '10px' }] }
      ));
    }
    if (targetPt) {
      routePromises.push(GoogleMaps.renderDrivingRoute(map,
        [optPos, { lat: targetPt.lat(), lng: targetPt.lng() }],
        { strokeColor: color, strokeOpacity: 0, strokeWeight: 2,
          icons: [{ icon: { ...dashedIcon, strokeColor: color, strokeOpacity: 0.5 }, offset: '0', repeat: '10px' }] }
      ));
    }
  });

  // Resolve driving route requests in parallel
  if (routePromises.length > 0) {
    Promise.allSettled(routePromises).then(results => {
      if (_rbMapGeneration !== genBefore) return; // map was cleared, discard stale results
      results.forEach(r => {
        if (r.status === 'fulfilled' && r.value) _rbPolylines.push(r.value);
      });
    });
  }

  if (hasBounds) {
    map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
    google.maps.event.addListenerOnce(map, 'bounds_changed', () => {
      if (map.getZoom() > 9) map.setZoom(9);
    });
  }
}

function _clearMap() {
  _rbMapGeneration++;
  _rbMarkers.forEach(m => { if (m && typeof m.setMap === 'function') m.setMap(null); });
  _rbPolylines.forEach(l => { if (l && typeof l.setMap === 'function') l.setMap(null); });
  _rbMarkers = [];
  _rbPolylines = [];
}

function scrollToOption(i) {
  document.getElementById(`option-card-${i}`)?.scrollIntoView({ behavior: 'smooth' });
}

function renderBuiltStops() {
  const list = document.getElementById('built-stops-list');
  const panel = document.getElementById('built-stops-panel');
  const countBadge = document.getElementById('built-stops-count');
  if (!list) return;

  const stops = S.selectedStops;
  if (panel) panel.style.display = stops.length > 0 ? '' : 'none';
  if (countBadge) countBadge.textContent = `${stops.length} Stop${stops.length !== 1 ? 's' : ''}`;

  list.innerHTML = stops.map((stop, i) => {
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
  if (S.jobId) {
    progressOverlay.open('Nächsten Stopp suchen…');
    openRouteSSE(S.jobId);
  }
  _showSkeletonCards();

  try {
    const data = await apiSelectStop(S.jobId, idx);

    addBuiltStop(data.selected_stop);
    if (data.via_point_added) addBuiltStop(data.via_point_added);
    saveRouteState();

    const options = data.options || [];
    const meta    = data.meta || {};

    // Handle leg advancement
    if (data.leg_advanced && data.explore_pending) {
      // Explore leg started — wait for SSE region_plan_ready
      progressOverlay.close();
      closeRouteSSE();
      _streamingOptions = [];
      S.loadingOptions = false;
      routeMeta = { ...routeMeta, ...meta };
      renderBuiltStops();
      _updateRouteStatus(meta);
      return;
    }

    if (options.length === 0 && meta.route_could_be_complete) {
      // Route done — close SSE and show confirm
      progressOverlay.close();
      closeRouteSSE();
      _streamingOptions = [];
      renderOptions([], meta);
    } else if (_streamingOptions.filter(Boolean).length >= options.length && options.length > 0) {
      // Streaming already delivered all cards — just update state/map/status
      S.currentOptions = options;
      S.loadingOptions = false;
      progressOverlay.close();
      closeRouteSSE();
      routeMeta = { ...routeMeta, ...meta };
      _updateRouteStatus(meta);
      renderBuiltStops();
      if (typeof updateSidebar === 'function') updateSidebar();
      _initMap(meta.map_anchors || _streamingMeta || {}, options);
      _appendSkipCardFromMeta();
      const confirmBtn = document.getElementById('confirm-route-btn');
      if (confirmBtn) confirmBtn.style.display = meta.route_could_be_complete ? 'block' : 'none';
      _streamingOptions = [];
      _streamingMeta = null;
    } else {
      // Streaming didn't finish yet or SSE unavailable — render from HTTP response
      progressOverlay.close();
      closeRouteSSE();
      _streamingOptions = [];
      renderOptions(options, meta);
    }

  } catch (err) {
    const container = document.getElementById('route-options-container');
    if (container) container.innerHTML = `<div class="error-msg">Fehler: ${esc(err.message)}</div>`;
    progressOverlay.close();
    closeRouteSSE();
    S.loadingOptions = false;
  }
}

function addBuiltStop(stop) {
  if (!stop) return;
  S.selectedStops.push(stop);
}

function _appendSkipCardFromMeta() {
  const container = document.getElementById('route-options-container');
  if (!container || !S.currentOptions.length) return;
  if (container.querySelector('#option-card-skip')) return; // already there
  container.insertAdjacentHTML('beforeend',
    _renderSkipCard(routeMeta.segment_target || '', routeMeta.skip_nights_bonus || 0));
}

async function skipStop() {
  const meta = routeMeta || {};
  const totalLegs = meta.total_legs || 1;
  const legIdx = meta.leg_index || 0;

  if (totalLegs > 1 && legIdx < totalLegs - 1) {
    // Multi-leg: skip to current leg's end and advance
    S.loadingOptions = true;
    _clearMap();
    if (S.jobId) {
      progressOverlay.open('Etappe wird abgeschlossen…');
      openRouteSSE(S.jobId);
    }
    _showSkeletonCards();

    try {
      const data = await apiSkipToLegEnd(S.jobId);
      if (data.selected_stop) addBuiltStop(data.selected_stop);
      saveRouteState();

      const options = data.options || [];
      const newMeta = data.meta || {};

      if (data.explore_pending) {
        progressOverlay.close();
        closeRouteSSE();
        _streamingOptions = [];
        S.loadingOptions = false;
        routeMeta = { ...routeMeta, ...newMeta };
        renderBuiltStops();
        _updateRouteStatus(newMeta);
        return;
      }

      progressOverlay.close();
      closeRouteSSE();
      _streamingOptions = [];

      if (options.length === 0 && newMeta.route_could_be_complete) {
        renderOptions([], newMeta);
      } else {
        renderOptions(options, newMeta);
      }
    } catch (err) {
      const container = document.getElementById('route-options-container');
      if (container) container.innerHTML = `<div class="error-msg">Fehler: ${esc(err.message)}</div>`;
      progressOverlay.close();
      closeRouteSSE();
      S.loadingOptions = false;
    }
  } else {
    confirmRoute();
  }
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
    Router.navigate('/accommodation/' + S.jobId);
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
  Router.navigate('/form');
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
      progressOverlay.close();
      closeRouteSSE();
      routeMeta = { ...routeMeta, ...meta };
      _updateRouteStatus(meta);
      renderBuiltStops();
      _initMap(meta.map_anchors || _streamingMeta || {}, options);
      _appendSkipCardFromMeta();
      _streamingOptions = [];
      _streamingMeta = null;
    } else {
      progressOverlay.close();
      closeRouteSSE();
      _streamingOptions = [];
      renderOptions(options, meta);
    }
  } catch (err) {
    const container = document.getElementById('route-options-container');
    if (container) container.innerHTML = `<div class="error-msg">Fehler: ${esc(err.message)}</div>`;
    progressOverlay.close();
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
// No-stops-found UI
// ---------------------------------------------------------------------------

function _showNoStopsFoundUI(corridor) {
  const container = document.getElementById('route-options-container');
  if (!container) return;
  container.innerHTML = '';

  const mapDiv = document.createElement('div');
  mapDiv.id = 'no-stops-map';
  mapDiv.style.cssText = 'height:300px;border-radius:12px;margin-bottom:16px';

  container.innerHTML = `
    <div class="no-stops-card">
      <h3>Keine passenden Zwischenstopps gefunden</h3>
      <p>Auf der direkten Route zwischen <strong>${esc(corridor.start)}</strong> und
         <strong>${esc(corridor.end)}</strong> gibt es keine passenden Stopps.</p>
    </div>
  `;
  container.appendChild(mapDiv);
  container.insertAdjacentHTML('beforeend', `
    <div class="recompute-bar" style="margin-top:12px">
      <input type="text" id="guidance-text"
        placeholder="z.B. 'In der Nähe von Annecy' oder 'Am Genfer See'" style="flex:1">
      <button class="btn btn-primary btn-sm" onclick="_submitGuidance()">Nochmal suchen</button>
      <button class="btn btn-secondary btn-sm" onclick="skipStop()">Direkt zum Ziel</button>
    </div>
  `);

  // Show corridor on Google Maps
  if (corridor.start_coords && corridor.end_coords && typeof google !== 'undefined') {
    const map = new google.maps.Map(mapDiv, { zoom: 6, center: {
      lat: (corridor.start_coords[0] + corridor.end_coords[0]) / 2,
      lng: (corridor.start_coords[1] + corridor.end_coords[1]) / 2,
    }});
    new google.maps.Marker({ position: { lat: corridor.start_coords[0], lng: corridor.start_coords[1] }, map, label: 'S' });
    new google.maps.Marker({ position: { lat: corridor.end_coords[0], lng: corridor.end_coords[1] }, map, label: 'Z' });
    new google.maps.Polyline({
      path: [
        { lat: corridor.start_coords[0], lng: corridor.start_coords[1] },
        { lat: corridor.end_coords[0], lng: corridor.end_coords[1] },
      ],
      strokeColor: '#4a90d9', strokeWeight: 3, strokeOpacity: 0.7,
      map,
    });
  }
}

async function _submitGuidance() {
  const input = document.getElementById('guidance-text');
  if (!input || !input.value.trim()) return;
  const guidance = input.value.trim();
  progressOverlay.open('Suche mit deiner Angabe…');
  openRouteSSE(S.jobId);
  try {
    const data = await _fetchQuiet(`${API}/recompute-options/${S.jobId}`, {
      method: 'POST',
      body: JSON.stringify({ extra_instructions: guidance }),
    }).then(r => r.json());
    startRouteBuilding(data);
  } catch (err) {
    progressOverlay.close();
    closeRouteSSE();
    console.error('Guidance retry fehlgeschlagen:', err);
  }
}

// ---------------------------------------------------------------------------
// Explore mode: Region plan UI
// ---------------------------------------------------------------------------

let _regionPlanMap = null;
let _regionMarkers = [];
let _regionPolyline = null;

function _buildRegionCardHtml(r, i) {
  const highlightsHtml = (r.highlights || []).length > 0
    ? `<ul class="region-highlights">${r.highlights.map(h => `<li>${esc(h)}</li>`).join('')}</ul>`
    : '';
  const teaserHtml = r.teaser ? `<p class="region-teaser">${esc(r.teaser)}</p>` : '';
  return `
    <div class="region-card" draggable="true" data-index="${i}"
         ondragstart="_onRegionDragStart(event, ${i})"
         ondragover="event.preventDefault(); this.classList.add('drag-over')"
         ondragleave="this.classList.remove('drag-over')"
         ondrop="_onRegionDrop(event, ${i}); this.classList.remove('drag-over')">
      ${buildHeroPhotoLoading('md')}
      <div class="region-card-body">
        <div class="region-card-header">
          <span class="region-card-number">${i + 1}</span>
          <h3>${esc(r.name)}</h3>
          <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); _toggleReplaceRegion(${i})">Ersetzen</button>
        </div>
        ${teaserHtml}
        ${highlightsHtml}
        <p class="region-reason">${esc(r.reason)}</p>
      </div>
      <div class="region-replace-form" id="region-replace-${i}" style="display:none">
        <input type="text" id="region-replace-text-${i}"
          placeholder="Wie soll diese Region ersetzt werden?">
        <button class="btn btn-sm btn-primary" onclick="_doReplaceRegion(${i})">Ersetzen</button>
      </div>
    </div>`;
}

function showRegionPlanUI(regions, summary, legId) {
  progressOverlay.close();
  closeRouteSSE();
  S.loadingOptions = false;

  // Hide options panel, show region plan in its place
  const optionsPanel = document.getElementById('options-panel');
  if (optionsPanel) optionsPanel.style.display = 'none';

  // Remove existing region panel if present
  const existing = document.getElementById('region-plan-panel');
  if (existing) existing.remove();

  // Store regions globally for drag-and-drop
  window._currentRegions = regions;
  window._currentRegionLegId = legId;

  const regionCardsHtml = regions.map((r, i) => _buildRegionCardHtml(r, i)).join('');

  const panel = document.createElement('div');
  panel.id = 'region-plan-panel';
  panel.className = 'route-panel';
  panel.innerHTML = `
    <div class="route-panel-header">
      <h3>Regionen-Plan</h3>
      <div class="region-actions">
        <button class="btn btn-secondary btn-sm" onclick="_toggleRecompute()">Neu berechnen</button>
        <button class="btn btn-primary btn-sm" onclick="_confirmRegions()">Route bestätigen</button>
      </div>
    </div>
    <div class="route-panel-body">
      <p class="region-summary">${esc(summary)}</p>
      <div class="region-plan-layout">
        <div class="region-cards-list" id="region-list">${regionCardsHtml}</div>
        <div class="region-map-panel">
          <div id="region-plan-map"></div>
        </div>
      </div>
      <div id="recompute-form" style="display:none;margin-top:12px">
        <div class="recompute-bar">
          <input type="text" id="recompute-text"
            placeholder="Was soll geändert werden?" style="flex:1">
          <button class="btn btn-sm btn-primary" onclick="_doRecompute()">Neu berechnen</button>
        </div>
      </div>
    </div>
  `;

  // Insert after built-stops-panel or after map
  const builtPanel = document.getElementById('built-stops-panel');
  const routeMap = document.getElementById('route-map');
  const insertAfter = builtPanel || routeMap;
  if (insertAfter && insertAfter.parentNode) {
    insertAfter.parentNode.insertBefore(panel, insertAfter.nextSibling);
  }

  _initRegionMap(regions);
  _lazyLoadRegionImages(regions);
}

function _lazyLoadRegionImages(regions) {
  regions.forEach((r, i) => {
    const card = document.querySelector(`.region-card[data-index="${i}"]`);
    if (card && r.lat && r.lon) {
      _lazyLoadEntityImages(card, r.name, r.lat, r.lon, 'city', 'md');
    }
  });
}

function _initRegionMap(regions) {
  const mapDiv = document.getElementById('region-plan-map');
  if (!mapDiv || typeof google === 'undefined') return;

  const bounds = new google.maps.LatLngBounds();
  const path = [];

  _regionPlanMap = new google.maps.Map(mapDiv, { zoom: 5 });
  _regionMarkers = [];

  regions.forEach((r, i) => {
    const pos = { lat: r.lat, lng: r.lon };
    bounds.extend(pos);
    path.push(pos);

    const marker = new google.maps.Marker({
      position: pos,
      map: _regionPlanMap,
      label: { text: String(i + 1), color: '#fff' },
      title: r.name,
    });
    _regionMarkers.push(marker);
  });

  // Render driving route; fallback to straight line on error
  const regionWaypoints = path.map(p => ({ lat: p.lat, lng: p.lng || p.lon }));
  if (regionWaypoints.length >= 2) {
    GoogleMaps.renderDrivingRoute(_regionPlanMap, regionWaypoints, {
      strokeColor: '#4a90d9', strokeWeight: 3, strokeOpacity: 0.8,
    }).then(r => { _regionPolyline = r; });
  }

  _regionPlanMap.fitBounds(bounds, 50);
}

function updateRegionPlanUI(regions, summary) {
  window._currentRegions = regions;
  // Re-render the cards list
  const list = document.getElementById('region-list');
  if (list) {
    list.innerHTML = regions.map((r, i) => _buildRegionCardHtml(r, i)).join('');
    _lazyLoadRegionImages(regions);
  }
  // Update summary
  const summaryEl = document.querySelector('.region-summary');
  if (summaryEl) summaryEl.textContent = summary;
  // Update map
  _updateRegionMap(regions);
}

function _updateRegionMap(regions) {
  if (!_regionPlanMap) return;
  _regionMarkers.forEach(m => m.setMap(null));
  if (_regionPolyline) _regionPolyline.setMap(null);
  _initRegionMap(regions);
}

// Drag and drop
let _dragSourceIndex = null;

function _onRegionDragStart(e, index) {
  _dragSourceIndex = index;
  e.dataTransfer.effectAllowed = 'move';
}

function _onRegionDrop(e, targetIndex) {
  e.preventDefault();
  if (_dragSourceIndex === null || _dragSourceIndex === targetIndex) return;
  const regions = window._currentRegions;
  const [moved] = regions.splice(_dragSourceIndex, 1);
  regions.splice(targetIndex, 0, moved);
  _dragSourceIndex = null;
  updateRegionPlanUI(regions, document.querySelector('.region-summary')?.textContent || '');
}

function _toggleReplaceRegion(index) {
  const form = document.getElementById(`region-replace-${index}`);
  if (form) form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function _doReplaceRegion(index) {
  const input = document.getElementById(`region-replace-text-${index}`);
  if (!input || !input.value.trim()) return;
  progressOverlay.open('Region wird ersetzt…');
  try {
    const data = await replaceRegion(S.jobId, index, input.value.trim());
    progressOverlay.close();
    if (data.region_plan) {
      updateRegionPlanUI(data.region_plan.regions, data.region_plan.summary);
    }
  } catch (err) {
    progressOverlay.close();
    console.error('Region ersetzen fehlgeschlagen:', err);
  }
}

function _toggleRecompute() {
  const form = document.getElementById('recompute-form');
  if (form) form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function _doRecompute() {
  const input = document.getElementById('recompute-text');
  if (!input || !input.value.trim()) return;
  progressOverlay.open('Route wird neu berechnet…');
  try {
    const data = await recomputeRegions(S.jobId, input.value.trim());
    progressOverlay.close();
    if (data.region_plan) {
      updateRegionPlanUI(data.region_plan.regions, data.region_plan.summary);
    }
  } catch (err) {
    progressOverlay.close();
    console.error('Neu berechnen fehlgeschlagen:', err);
  }
}

async function _confirmRegions() {
  progressOverlay.open('Regionen werden bestätigt…');
  openRouteSSE(S.jobId);
  try {
    const data = await confirmRegions(S.jobId);
    startRouteBuilding(data);
  } catch (err) {
    progressOverlay.close();
    closeRouteSSE();
    console.error('Region-Bestätigung fehlgeschlagen:', err);
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
  if (S.jobId) {
    progressOverlay.open('Route wird angepasst…');
    openRouteSSE(S.jobId);
  }
  _showSkeletonCards();

  try {
    const data = await apiPatchJob(S.jobId, action, extraDays, viaLoc);
    const options = data.options || [];
    const meta = data.meta || {};
    if (_streamingOptions.filter(Boolean).length >= options.length && options.length > 0) {
      S.currentOptions = options;
      S.loadingOptions = false;
      progressOverlay.close();
      closeRouteSSE();
      routeMeta = { ...routeMeta, ...meta };
      _updateRouteStatus(meta);
      renderBuiltStops();
      _initMap(meta.map_anchors || _streamingMeta || {}, options);
      _appendSkipCardFromMeta();
      _streamingOptions = [];
      _streamingMeta = null;
    } else {
      progressOverlay.close();
      closeRouteSSE();
      _streamingOptions = [];
      renderOptions(options, meta);
    }
  } catch (err) {
    const container = document.getElementById('route-options-container');
    if (container) container.innerHTML = `<div class="error-msg">Fehler beim Anpassen: ${esc(err.message)}</div>`;
    progressOverlay.close();
    closeRouteSSE();
    S.loadingOptions = false;
  }
}
