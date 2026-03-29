// Guide Stops — stop cards, stop detail, stop navigation.
// Reads: S (state.js), esc() (state.js), activeTab/_activeStopId (guide-core.js).
// Provides: renderStopCard, renderStopsOverview, renderStopDetail, navigateToStop,
//           navigateToStopsOverview, activateStopDetail, _onCardClick, _lazyLoadCardImages,
//           _lazyLoadSingleStopImages, _initStopMap, _buildStopMapPin, _buildStopMapPopup,
//           stop-drop-zone elements (for drag-and-drop between cards)
'use strict';

let _initializedStopMaps = new Set();

function renderStopCard(stop, i, totalStops) {
  var flag = FLAGS[stop.country] || '';
  var driveInfo = '';
  if (stop.drive_hours_from_prev > 0) {
    driveInfo = esc(String(stop.drive_hours_from_prev)) + 'h Fahrt';
    if (stop.drive_km_from_prev > 0) driveInfo += ' \u00b7 ' + esc(String(stop.drive_km_from_prev)) + ' km';
  }
  var nightsText = stop.nights + ' Nacht' + (stop.nights !== 1 ? 'e' : '');
  var nightsHtml = '<span class="stop-nights-editable" data-nights-stop="' + stop.id + '" onclick="event.stopPropagation(); _editStopNights(' + stop.id + ', ' + stop.nights + ')">' +
    esc(nightsText) + ' <svg class="inline-edit-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></span>';

  var tagsHtml = '';
  if (stop.tags && stop.tags.length > 0) {
    tagsHtml = '<div class="stop-card-tags">' +
      stop.tags.map(function (t) { return '<span class="stop-tag-pill">' + esc(t) + '</span>'; }).join('') +
    '</div>';
  }

  var descHtml = '';
  if (stop.teaser) {
    descHtml = '<p class="stop-card-desc">' + esc(stop.teaser) + '</p>';
  }

  // Edit action buttons — always visible (D-08)
  var removeBtn = totalStops > 1
    ? '<button class="stop-edit-icon stop-edit-remove" aria-label="Stopp entfernen" ' +
      'onclick="event.stopPropagation(); _confirmRemoveStop(' + stop.id + ')">' +
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
      '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>'
    : '';

  var replaceBtn = '<button class="stop-edit-icon stop-edit-replace" aria-label="Stopp ersetzen" ' +
    'onclick="event.stopPropagation(); openReplaceStopModal(' + stop.id + ', ' + stop.nights + ')">' +
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>' +
    '<path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg></button>';

  var dragBtn = '<button class="stop-edit-icon stop-edit-drag" aria-label="Stopp verschieben">' +
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">' +
    '<circle cx="9" cy="6" r="1.5"/><circle cx="15" cy="6" r="1.5"/>' +
    '<circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/>' +
    '<circle cx="9" cy="18" r="1.5"/><circle cx="15" cy="18" r="1.5"/></svg></button>';

  return '<div class="stop-card-row" data-stop-id="' + stop.id + '" data-stop-index="' + i + '" draggable="true" ' +
    'ondragstart="_onStopDragStart(event, ' + i + ')" ' +
    'ondragend="_onStopDragEnd(event)">' +
    '<div class="stop-card-photo">' + buildHeroPhotoLoading('sm') + '</div>' +
    '<div class="stop-card-info">' +
      '<div class="stop-card-title">' +
        '<span class="stop-num-badge">' + (i + 1) + '</span>' +
        '<h3>' + flag + ' ' + esc(stop.region) + '</h3>' +
      '</div>' +
      '<div class="stop-card-meta">' +
        (driveInfo ? '<span>' + driveInfo + '</span>' : '') +
        nightsHtml +
      '</div>' +
      tagsHtml +
      descHtml +
      '<div class="stop-card-actions">' + removeBtn + replaceBtn + dragBtn + '</div>' +
    '</div>' +
  '</div>';
}

// ---------------------------------------------------------------------------
// Stops Overview (card list)
// ---------------------------------------------------------------------------

function renderStopsOverview(plan) {
  var stops = plan.stops || [];
  var html = '';
  for (var i = 0; i < stops.length; i++) {
    // Drop zone before each card (insert at position i)
    html += '<div class="stop-drop-zone" data-drop-index="' + i + '" ' +
      'ondragover="event.preventDefault(); this.classList.add(\'drop-zone-active\')" ' +
      'ondragleave="this.classList.remove(\'drop-zone-active\')" ' +
      'ondrop="_onDropZoneDrop(event, ' + i + ')">' +
      '<div class="drop-zone-line"></div></div>';
    html += renderStopCard(stops[i], i, stops.length);
  }
  // Drop zone after last card (insert at end = stops.length)
  html += '<div class="stop-drop-zone" data-drop-index="' + stops.length + '" ' +
    'ondragover="event.preventDefault(); this.classList.add(\'drop-zone-active\')" ' +
    'ondragleave="this.classList.remove(\'drop-zone-active\')" ' +
    'ondrop="_onDropZoneDrop(event, ' + stops.length + ')">' +
    '<div class="drop-zone-line"></div></div>';

  return '<div class="stop-cards-list">' + html + '</div>' +
    '<div class="stops-overview-actions">' +
      '<button class="btn btn-primary add-stop-btn" onclick="_openAddStopModal()">+ Stopp hinzuf\u00fcgen</button>' +
    '</div>';
}

// ---------------------------------------------------------------------------
// Card Click → Map Sync
// ---------------------------------------------------------------------------

function _onCardClick(stopId) {
  // Highlight the clicked card, remove highlight from others
  document.querySelectorAll('.stop-card-row').forEach(function (card) {
    card.classList.toggle('selected', String(card.dataset.stopId) === String(stopId));
  });

  // Sync with map if GoogleMaps module is available
  if (typeof GoogleMaps !== 'undefined') {
    if (typeof GoogleMaps.panToStop === 'function') GoogleMaps.panToStop(stopId);
    if (typeof GoogleMaps.highlightGuideMarker === 'function') GoogleMaps.highlightGuideMarker(stopId);
  }
}

// ---------------------------------------------------------------------------
// Lazy-load card images
// ---------------------------------------------------------------------------

function _lazyLoadCardImages(plan) {
  var stops = plan.stops || [];
  document.querySelectorAll('.stop-card-row').forEach(function (card) {
    var idx = Number(card.dataset.stopIndex);
    var stop = stops[idx];
    if (!stop) return;
    var photoContainer = card.querySelector('.stop-card-photo');
    if (photoContainer) {
      _lazyLoadEntityImages(photoContainer, stop.region, stop.lat, stop.lng, 'destination', 'sm');
    }
  });
}

// ---------------------------------------------------------------------------
// Stop Detail (full page with sidebar + prev/next)
// ---------------------------------------------------------------------------

function renderStopDetail(plan, stopId) {
  const stops = plan.stops || [];
  const dayPlans = plan.day_plans || [];
  const idx = stops.findIndex(s => String(s.id) === String(stopId));
  const stop = stops[idx];
  if (!stop) return renderStopsOverview(plan);

  const flag = FLAGS[stop.country] || '';
  const prev = idx > 0 ? stops[idx - 1] : null;
  const next = idx < stops.length - 1 ? stops[idx + 1] : null;
  const further = stop.further_activities || [];

  // Sidebar items for quick nav
  const sidebarItems = stops.map(s => {
    const f = FLAGS[s.country] || '';
    return `
      <div class="stops-sidebar-item${String(s.id) === String(stopId) ? ' active' : ''}" data-stop-id="${s.id}">
        <span class="sidebar-stop-num">${s.id}</span>
        <span class="sidebar-stop-label">${f} ${esc(s.region)}</span>
      </div>
    `;
  }).join('');

  return `
    <div class="stops-layout">
      <aside class="stops-sidebar">
        <div class="stops-sidebar-inner">
          ${sidebarItems}
        </div>
      </aside>
      <div class="stops-main">
        <div class="stop-detail-nav">
          <button class="stop-detail-back">\u2190 Alle Stops</button>
          <span class="stop-detail-breadcrumb">Stop ${stop.id}: ${flag} ${esc(stop.region)}</span>
        </div>

        <div class="stop-card" id="guide-stop-${stop.id}" data-stop-id="${stop.id}">
          <div class="stop-detail-header">
            <div class="stop-header-left">
              <div class="stop-number">Stop ${stop.id}</div>
              <h3>${flag} ${esc(stop.region)}, ${esc(stop.country)}</h3>
              <div class="stop-meta">
                Tag ${stop.arrival_day} \u00b7 ${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}
                ${stop.drive_hours_from_prev > 0 ? ` \u00b7 ${stop.drive_hours_from_prev}h Fahrt` : ''}
                ${stop.drive_km_from_prev > 0 ? ` \u00b7 ${stop.drive_km_from_prev} km` : ''}
              </div>
            </div>
            <div class="stop-header-right">
              ${stops.length > 1 ? `<button class="remove-stop-btn btn-icon-danger" onclick="event.stopPropagation(); _confirmRemoveStop(${stop.id})" title="Stopp entfernen">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                Entfernen
              </button>` : ''}
              <button class="replace-stop-btn" onclick="event.stopPropagation(); openReplaceStopModal(${stop.id}, ${stop.nights})" title="Stopp ersetzen">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
                Ersetzen
              </button>
              ${(stop.place_id || stop.google_maps_url) ? `<a href="${safeUrl(stop.place_id ? 'https://www.google.com/maps/place/?q=place_id:' + stop.place_id : stop.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
            </div>
          </div>

          <div class="stop-body" style="display:block">
            ${buildHeroPhotoLoading('lg')}
            <div class="stop-overview-map" id="stop-map-${stop.id}"></div>
            ${renderTravelGuide(stop.travel_guide)}
            ${_renderAccommodationHtml(stop)}
            ${_renderActivitiesHtml(stop)}
            ${renderFurtherActivities(further)}
            ${_renderRestaurantsHtml(stop)}
            ${_renderDayExamplesHtml(stop, dayPlans)}
          </div>
        </div>

        <div class="stop-detail-prevnext">
          ${prev ? `<button class="btn btn-secondary stop-nav-prev" data-stop-id="${prev.id}">\u2190 Stop ${prev.id}: ${esc(prev.region)}</button>` : '<span></span>'}
          ${next ? `<button class="btn btn-secondary stop-nav-next" data-stop-id="${next.id}">Stop ${next.id}: ${esc(next.region)} \u2192</button>` : '<span></span>'}
        </div>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Stop navigation helpers
// ---------------------------------------------------------------------------

function navigateToStop(stopId) {
  _activeStopId = Number(stopId);
  var plan = S.result;
  if (!plan) return;

  // Determine which day this stop belongs to for breadcrumb
  var stop = (plan.stops || []).find(function(s) { return String(s.id) === String(stopId); });
  if (stop && _activeDayNum == null) {
    _activeDayNum = stop.arrival_day || null;
  }

  _drillTransition(
    function() { return renderStopDetail(plan, Number(stopId)); },
    function() {
      _initGuideDelegation();
      var s = (plan.stops || []).find(function(x) { return String(x.id) === String(stopId); });
      if (s) {
        _initStopMap(s);
        _lazyLoadSingleStopImages(plan, s);
      }
    }
  );

  _renderBreadcrumb('stop', plan, _activeDayNum, stopId);
  _updateMapForTab(plan, 'stops', 'stop', { stopId: Number(stopId), dayNum: _activeDayNum });

  if (plan._saved_travel_id) {
    var title = plan.custom_name || plan.title || '';
    var base = Router.travelPath(plan._saved_travel_id, title);
    Router.navigate(base + '/stops/' + stopId, { skipDispatch: true });
  }
}

function navigateToStopsOverview() {
  _activeStopId = null;
  if (_activeDayNum != null) {
    navigateToDay(_activeDayNum);
  } else {
    _navigateToOverview();
  }
}

function activateStopDetail(stopId) {
  _activeStopId = Number(stopId);
  var plan = S.result;
  if (!plan) return;

  var stop = (plan.stops || []).find(function(s) { return String(s.id) === String(stopId); });
  if (stop && _activeDayNum == null) {
    _activeDayNum = stop.arrival_day || null;
  }

  _drillTransition(
    function() { return renderStopDetail(plan, Number(stopId)); },
    function() {
      _initGuideDelegation();
      var s = (plan.stops || []).find(function(x) { return String(x.id) === String(stopId); });
      if (s) {
        _initStopMap(s);
        _lazyLoadSingleStopImages(plan, s);
      }
    }
  );

  _renderBreadcrumb('stop', plan, _activeDayNum, stopId);
  _updateMapForTab(plan, 'stops', 'stop', { stopId: Number(stopId), dayNum: _activeDayNum });
}


function _buildStopMapPin(type, entity) {
  if (type === 'hotel') return '<div class="stop-map-pin pin-hotel">🏨</div>';
  if (type === 'activity') return `<div class="stop-map-pin pin-activity">${_getActivityIcon(entity.name)}</div>`;
  if (type === 'restaurant') return '<div class="stop-map-pin pin-restaurant">🍽</div>';
  return '<div class="stop-map-pin pin-activity">📍</div>';
}

function _buildStopMapPopup(type, entity) {
  if (type === 'hotel') {
    const ratingStr = entity.rating ? `${entity.rating}★` : '';
    return `<div class="stop-map-popup">
      <strong>${esc(entity.name)}</strong>
      <div class="popup-meta">
        ${entity.type ? esc(entity.type) : ''}
        ${entity.price_per_night_chf ? ` · CHF ${entity.price_per_night_chf}/Nacht` : ''}
        ${ratingStr ? ` · ${ratingStr}` : ''}
      </div>
    </div>`;
  }
  if (type === 'activity') {
    return `<div class="stop-map-popup">
      <strong>${esc(entity.name)}</strong>
      <div class="popup-meta">
        ${entity.duration_hours ? entity.duration_hours + 'h' : ''}
        ${entity.price_chf > 0 ? ' · CHF ' + entity.price_chf : ' · kostenlos'}
      </div>
      ${entity.description ? `<div class="popup-desc">${esc(entity.description)}</div>` : ''}
    </div>`;
  }
  if (type === 'restaurant') {
    return `<div class="stop-map-popup">
      <strong>${esc(entity.name)}</strong>
      <div class="popup-meta">
        ${entity.cuisine ? esc(entity.cuisine) : ''}
        ${entity.price_range ? ' · ' + esc(entity.price_range) : ''}
      </div>
      ${entity.family_friendly ? '<div class="popup-badge">Familienfreundlich</div>' : ''}
    </div>`;
  }
  return `<div class="stop-map-popup"><strong>${esc(entity.name || '')}</strong></div>`;
}

function _scrollToAndHighlight(selector, stopId) {
  const container = document.getElementById(`guide-stop-${stopId}`);
  if (!container) return;
  const el = container.querySelector(selector);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.remove('highlight-flash');
  void el.offsetWidth; // reflow to restart animation
  el.classList.add('highlight-flash');
  el.addEventListener('animationend', () => el.classList.remove('highlight-flash'), { once: true });
}

async function _initStopMap(stop) {
  if (!window.google || !google.maps) return;
  if (_initializedStopMaps.has(stop.id)) return;
  _initializedStopMaps.add(stop.id);

  const elId = 'stop-map-' + stop.id;
  const center = { lat: stop.lat || 47, lng: stop.lng || 8 };
  const map = GoogleMaps.initStopOverviewMap(elId, { center, zoom: 13 });
  if (!map) return;

  // Collect ALL entities from this stop (with or without place_id)
  const entities = [];
  const acc = stop.accommodation;
  if (acc && acc.name) {
    entities.push({
      key: `hotel-${stop.id}`,
      placeId: acc.place_id || null,
      name: acc.name,
      stopLat: stop.lat, stopLng: stop.lng,
      searchType: 'hotel',
      type: 'hotel', data: acc, index: 0,
    });
  }

  (stop.top_activities || []).forEach((act, i) => {
    if (!act.name) return;
    entities.push({
      key: `act-${stop.id}-${i}`,
      placeId: act.place_id || null,
      lat: act.lat || null,
      lng: act.lon || null,
      name: act.name,
      stopLat: stop.lat, stopLng: stop.lng,
      searchType: 'activity',
      type: 'activity', data: act, index: i,
    });
  });

  (stop.further_activities || []).forEach((act, i) => {
    if (!act.name) return;
    entities.push({
      key: `fact-${stop.id}-${i}`,
      placeId: act.place_id || null,
      lat: act.lat || null,
      lng: act.lon || null,
      name: act.name,
      stopLat: stop.lat, stopLng: stop.lng,
      searchType: 'activity',
      type: 'activity', data: act, index: i,
      isFurther: true,
    });
  });

  (stop.restaurants || []).forEach((r, i) => {
    if (!r.name) return;
    entities.push({
      key: `rest-${stop.id}-${i}`,
      placeId: r.place_id || null,
      name: r.name,
      stopLat: stop.lat, stopLng: stop.lng,
      searchType: 'restaurant',
      type: 'restaurant', data: r, index: i,
    });
  });

  if (entities.length === 0) return;

  let coords;
  try {
    coords = await GoogleMaps.resolveEntityCoordinates(entities);
  } catch (e) {
    console.error('Stop map coord resolve:', e);
    return;
  }

  if (coords.size === 0) return;

  const bounds = new google.maps.LatLngBounds();
  let _openInfoWindow = null;

  for (const ent of entities) {
    const pos = coords.get(ent.key);
    if (!pos) continue;

    bounds.extend(pos);
    const pinHtml = _buildStopMapPin(ent.type, ent.data);
    const popupHtml = _buildStopMapPopup(ent.type, ent.data);
    const infoWindow = new google.maps.InfoWindow({ content: popupHtml });

    let hoverTimeout = null;

    const overlay = GoogleMaps.createDivMarker(map, pos, pinHtml, () => {
      // Click → scroll to corresponding section
      if (ent.type === 'hotel') {
        _scrollToAndHighlight('.stop-accommodation', stop.id);
      } else if (ent.type === 'activity') {
        if (ent.isFurther) {
          _scrollToAndHighlight('.further-activities', stop.id);
        } else {
          _scrollToAndHighlight(`.activities-grid .activity-card:nth-child(${ent.index + 1})`, stop.id);
        }
      } else if (ent.type === 'restaurant') {
        _scrollToAndHighlight(`.restaurants-list .restaurant-item:nth-child(${ent.index + 1})`, stop.id);
      }
    });

    // Hover behavior — attach to overlay div after it's added
    const origOnAdd = overlay.onAdd;
    overlay.onAdd = function () {
      origOnAdd.call(this);
      const div = this._div;
      if (!div) return;

      div.addEventListener('mouseenter', () => {
        clearTimeout(hoverTimeout);
        if (_openInfoWindow) _openInfoWindow.close();
        infoWindow.setPosition(pos);
        infoWindow.open(map);
        _openInfoWindow = infoWindow;
      });

      div.addEventListener('mouseleave', () => {
        hoverTimeout = setTimeout(() => {
          infoWindow.close();
          if (_openInfoWindow === infoWindow) _openInfoWindow = null;
        }, 150);
      });
    };
  }

  // Fit bounds with padding
  if (coords.size > 1) {
    map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
  }
}

function _lazyLoadSingleStopImages(plan, stop) {
  const stopEl = document.getElementById(`guide-stop-${stop.id}`);
  if (!stopEl) return;
  const lat = stop.lat;
  const lng = stop.lng;

  _lazyLoadEntityImages(stopEl.querySelector('.stop-detail-header')?.parentElement || stopEl, stop.region, lat, lng, 'city');

  const accEl = stopEl.querySelector('.stop-accommodation');
  if (accEl && stop.accommodation) {
    _lazyLoadEntityImages(accEl, stop.accommodation.name, lat, lng, 'hotel');
    accEl.querySelectorAll('.acc-alt-item').forEach((el, i) => {
      const altOpts = (stop.all_accommodation_options || []).filter(o => o.name !== stop.accommodation.name);
      const o = altOpts[i];
      if (o) _lazyLoadEntityImages(el, o.name, lat, lng, 'hotel');
    });
  }

  stopEl.querySelectorAll('.activity-card').forEach((el, i) => {
    const act = (stop.top_activities || [])[i];
    if (act) _lazyLoadEntityImages(el, act.name, lat, lng, 'activity');
  });

  stopEl.querySelectorAll('.further-activity-item').forEach((el, i) => {
    const act = (stop.further_activities || [])[i];
    if (act) _lazyLoadEntityImages(el, act.name, lat, lng, 'activity');
  });

  stopEl.querySelectorAll('.restaurant-item').forEach((el, i) => {
    const rest = (stop.restaurants || [])[i];
    if (rest) _lazyLoadEntityImages(el, rest.name, lat, lng, 'restaurant');
  });
}

