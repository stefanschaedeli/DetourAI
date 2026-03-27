// Guide Map — persistent map, markers, scroll sync, entity images.
// Reads: S (state.js), activeTab/_activeStopId (guide-core.js), GoogleMaps (maps.js).
// Provides: _initGuideMap, _setupGuideMap, _updateMapForTab, _onMarkerClick,
//           _scrollToAndHighlightCard, _initScrollSync, _scrollToGuideStop,
//           _lazyLoadEntityImages, _getActivityIcon
'use strict';

let _guideMarkers = [];
let _guidePolyline = null;
let _guideMapInitialized = false;
let _userInteractingWithMap = false;
let _userInteractionTimeout = null;
let _lastPannedStopId = null;
let _scrollDebounce = null;
let _cardObserver = null;

function _scrollToGuideStop(stopId) {
  navigateToStop(stopId);
}

function _initGuideMap(plan) {
  if (typeof GoogleMaps === 'undefined' || !window.google) {
    if (typeof S !== 'undefined') {
      S.logs.push({ level: 'WARNING', agent: 'GoogleMaps', message: 'Reiseführer-Karte nicht geladen — Google Maps API nicht verfügbar' });
      if (typeof updateDebugLog === 'function') updateDebugLog();
    }
    return;
  }

  const stops = plan.stops || [];

  // initGuideMap always creates a fresh instance (element replaced by innerHTML)
  const map = GoogleMaps.initGuideMap('guide-map', { center: { lat: 47, lng: 8 }, zoom: 6 });
  if (!map) return;

  _guideMarkers = [];
  _guidePolyline = null;

  const bounds = new google.maps.LatLngBounds();
  let hasBounds = false;
  const routePoints = [];

  // Start pin (green S)
  if (plan.start_lat && plan.start_lng) {
    const pos = { lat: plan.start_lat, lng: plan.start_lng };
    const infoWin = new google.maps.InfoWindow({ content: `<b>Start: ${esc(plan.start_location)}</b>` });
    const m = GoogleMaps.createDivMarker(map, pos,
      `<div class="map-marker-anchor start-pin">S</div>`,
      () => infoWin.open({ map, position: pos })
    );
    _guideMarkers.push(m);
    bounds.extend(pos);
    hasBounds = true;
    routePoints.push(new google.maps.LatLng(pos.lat, pos.lng));
  }

  stops.forEach((stop, i) => {
    const sLat = stop.lat;
    const sLng = stop.lng;
    if (!sLat || !sLng) return;

    const isLast = i === stops.length - 1;
    const pos = { lat: sLat, lng: sLng };
    const infoContent = `<b>${FLAGS[stop.country] || ''} ${esc(stop.region)}</b><br>${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}`;
    const infoWin = new google.maps.InfoWindow({ content: infoContent });
    const markerHtml = isLast
      ? `<div class="map-marker-anchor target-pin">Z</div>`
      : `<div class="map-marker-num">${stop.id}</div>`;
    const stopId = stop.id;
    const m = (stop.place_id
      ? GoogleMaps.createPlaceMarker(map, stop.place_id, pos, markerHtml, () => { infoWin.open({ map, position: pos }); _scrollToGuideStop(stopId); })
      : GoogleMaps.createDivMarker(map, pos, markerHtml, () => { infoWin.open({ map, position: pos }); _scrollToGuideStop(stopId); }));
    _guideMarkers.push(m);
    bounds.extend(pos);
    hasBounds = true;
    routePoints.push(new google.maps.LatLng(sLat, sLng));
  });

  // Driving route through all route points (falls back to straight line on error)
  if (routePoints.length >= 2) {
    const guideWaypoints = routePoints.map(pt => ({ lat: pt.lat(), lng: pt.lng() }));
    GoogleMaps.renderDrivingRoute(map, guideWaypoints, {
      strokeColor: '#0EA5E9', strokeWeight: 3, strokeOpacity: 0.8,
    }).then(r => { _guidePolyline = r; });
  }

  if (hasBounds) {
    map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
    google.maps.event.addListenerOnce(map, 'bounds_changed', () => {
      if (map.getZoom() > 9) map.setZoom(9);
    });
  }
}

// ---------------------------------------------------------------------------
// Persistent guide map + bidirectional sync (D-09, D-11)
// ---------------------------------------------------------------------------

/** Initialize the persistent guide map once. Reuses existing map on subsequent calls. */
function _setupGuideMap(plan) {
  if (typeof GoogleMaps === 'undefined' || !window.google) return;
  const map = GoogleMaps.initPersistentGuideMap('guide-map', { center: { lat: 47, lng: 8 }, zoom: 6 });
  if (!map) return;
  GoogleMaps.setGuideMarkers(plan, _onMarkerClick);
  _guideMapInitialized = true;

  // Enable click-to-add-stop on empty map areas (D-10)
  GoogleMaps.enableClickToAdd(map, _onMapClickToAdd);

  // Suppress auto-pan during user map interaction (Pitfall 4)
  google.maps.event.addListener(map, 'dragstart', () => {
    _userInteractingWithMap = true;
    clearTimeout(_userInteractionTimeout);
  });
  google.maps.event.addListener(map, 'dragend', () => {
    _userInteractionTimeout = setTimeout(() => { _userInteractingWithMap = false; }, 3000);
  });

  // Click-outside-to-close sidebar overlay (D-03)
  google.maps.event.addListener(map, 'click', () => {
    const overlay = document.getElementById('sidebar-overlay');
    if (overlay && overlay.classList.contains('expanded')) {
      overlay.classList.remove('expanded');
      overlay.classList.add('collapsed');
    }
  });
}

/**
 * Update map view when switching tabs, with optional drill-level awareness.
 * @param {Object} plan
 * @param {string} tab - active guide tab
 * @param {string} [drillLevel] - 'overview' | 'day' | 'stop' (inferred from state if not passed)
 * @param {Object} [drillContext] - { dayNum, stopId }
 */
function _updateMapForTab(plan, tab, drillLevel, drillContext) {
  if (typeof GoogleMaps === 'undefined' || !_guideMapInitialized) return;

  // Infer drill level from state if not explicitly passed
  if (!drillLevel) {
    if (_activeStopId != null) {
      drillLevel = 'stop';
      drillContext = { stopId: _activeStopId, dayNum: _activeDayNum };
    } else if (_activeDayNum != null) {
      drillLevel = 'day';
      drillContext = { dayNum: _activeDayNum };
    } else {
      drillLevel = 'overview';
      drillContext = {};
    }
  }

  if (drillLevel === 'day' && drillContext && drillContext.dayNum) {
    var dayStops = _findStopsForDay(plan, Number(drillContext.dayNum));
    var focusedIds = dayStops.map(function(s) { return String(s.id); });
    GoogleMaps.fitDayStops(dayStops);
    setTimeout(function() { GoogleMaps.dimNonFocusedMarkers(focusedIds); }, 50);
  } else if (drillLevel === 'stop' && drillContext && drillContext.stopId) {
    GoogleMaps.panToStop(drillContext.stopId, plan.stops || []);
    setTimeout(function() { GoogleMaps.dimNonFocusedMarkers([String(drillContext.stopId)]); }, 50);
  } else {
    GoogleMaps.fitAllStops(plan);
    GoogleMaps.restoreAllMarkers();
  }
}

/** Handle marker click: highlight marker and scroll to card. */
function _onMarkerClick(stopId) {
  if (typeof GoogleMaps !== 'undefined') GoogleMaps.highlightGuideMarker(stopId);
  if (activeTab === 'stops') {
    _scrollToAndHighlightCard(stopId);
  } else {
    _activeStopId = null;
    switchGuideTab('stops');
    requestAnimationFrame(() => {
      setTimeout(() => _scrollToAndHighlightCard(stopId), 100);
    });
  }
}

/** Scroll content panel to a stop card and highlight it. */
function _scrollToAndHighlightCard(stopId) {
  const sel = '[data-stop-id="' + stopId + '"]';
  const card = document.querySelector('.stop-card-row' + sel)
    || document.querySelector('.stop-overview-card' + sel);
  if (!card) return;
  document.querySelectorAll('.stop-card-row.selected, .stop-overview-card.selected')
    .forEach(el => el.classList.remove('selected'));
  card.classList.add('selected');
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/** Set up IntersectionObserver on stop cards for auto-pan (D-09). */
function _initScrollSync() {
  if (_cardObserver) _cardObserver.disconnect();
  if (typeof GoogleMaps === 'undefined') return;

  _cardObserver = new IntersectionObserver((entries) => {
    if (_userInteractingWithMap) return;
    const visible = entries.find(e => e.isIntersecting);
    if (!visible) return;
    clearTimeout(_scrollDebounce);
    _scrollDebounce = setTimeout(() => {
      const stopId = visible.target.dataset.stopId;
      if (stopId && stopId !== _lastPannedStopId) {
        _lastPannedStopId = stopId;
        GoogleMaps.panToStop(stopId, S.result?.stops || []);
        GoogleMaps.highlightGuideMarker(stopId);
      }
    }, 300);
  }, { threshold: 0.6 });

  document.querySelectorAll('[data-stop-id]').forEach(card => {
    _cardObserver.observe(card);
  });
}

/**
 * Lazily load images for an entity (stop, activity, restaurant, accommodation)
 * via Google Places and fill the hero-photo skeleton container.
 */
async function _lazyLoadEntityImages(containerEl, placeName, lat, lng, context, sizeClass) {
  const placeholder = containerEl?.querySelector('.hero-photo-loading');
  if (!containerEl || typeof GoogleMaps === 'undefined') {
    if (placeholder) placeholder.remove();
    return;
  }
  // Safety timeout: remove shimmer if image loading hangs
  const timer = placeholder && setTimeout(() => { if (placeholder.isConnected) placeholder.remove(); }, 12000);
  try {
    const urls = await GoogleMaps.getPlaceImages(placeName, lat, lng, context);
    const size = sizeClass || (placeholder?.classList.contains('hero-photo--lg') ? 'lg'
      : placeholder?.classList.contains('hero-photo--sm') ? 'sm' : 'md');
    const isGalleryCompact = placeholder?.classList.contains('hero-gallery-compact');
    const isGallery = placeholder?.classList.contains('hero-gallery');
    const newHtml = isGalleryCompact
      ? buildHeroPhotoGalleryCompact(urls, placeName)
      : isGallery
        ? buildHeroPhotoGallery(urls, placeName, size)
        : buildHeroPhoto(urls, placeName, size);
    clearTimeout(timer);
    if (!newHtml) {
      if (placeholder) placeholder.remove();
      return;
    }
    if (placeholder) {
      const tmp = document.createElement('div');
      tmp.innerHTML = newHtml;
      placeholder.replaceWith(tmp.firstElementChild);
    } else {
      const tmp = document.createElement('div');
      tmp.innerHTML = newHtml;
      containerEl.insertBefore(tmp.firstElementChild, containerEl.firstChild);
    }
  } catch (e) {
    clearTimeout(timer);
    if (placeholder) placeholder.remove();
    if (typeof S !== 'undefined') {
      S.logs.push({ level: 'WARNING', agent: 'GoogleMaps', message: `_lazyLoadEntityImages fehlgeschlagen für «${placeName}»: ${e.message}` });
      if (typeof updateDebugLog === 'function') updateDebugLog();
    }
  }
}

/** Walk the rendered stops section and lazy-load images for all entities. */
// ---------------------------------------------------------------------------
// Stop Overview Maps
// ---------------------------------------------------------------------------

function _getActivityIcon(name) {
  const n = (name || '').toLowerCase();
  if (/museum|galerie|gallery/.test(n)) return '🏛';
  if (/wander|hiking|randonnée/.test(n)) return '🥾';
  if (/see|lac|lake|schwimm|baignade|baden/.test(n)) return '🏊';
  if (/schloss|castle|château|burg|palast|palace/.test(n)) return '🏰';
  if (/park|garten|jardin|garden/.test(n)) return '🌿';
  if (/markt|market|marché/.test(n)) return '🛍';
  if (/kirche|church|église|dom|cathedral/.test(n)) return '⛪';
  if (/ski|snowboard/.test(n)) return '⛷';
  if (/strand|beach|plage/.test(n)) return '🏖';
  if (/wein|vin|wine/.test(n)) return '🍷';
  return '⭐';
}

