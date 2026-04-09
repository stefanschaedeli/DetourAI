'use strict';

// Maps Guide — persistent guide map state: stop markers, entity pins, ferry lines, pan/fit/dim.
// Reads: GoogleMaps (maps-core.js), GoogleMaps.renderDrivingRoute (maps-routes.js),
//        window._mapsGuideMarkers, window._mapsGuidePolyline, window._mapsGuideEntityMarkers (maps-core.js).
//        _buildStopMapPin, _buildStopMapPopup (guide-stops.js globals).
// Provides: getGuideMap, clearGuideMarkers, setGuideMarkers, highlightGuideMarker,
//           panToStop, fitAllStops, fitDayStops, dimNonFocusedMarkers, restoreAllMarkers,
//           enableClickToAdd, setGuideEntityMarkers, clearGuideEntityMarkers, filterGuideEntityMarkers.

Object.assign(GoogleMaps, (() => {

  // ---------------------------------------------------------------------------
  // Marker management
  // ---------------------------------------------------------------------------

  /** Return the current guide map instance. */
  function getGuideMap() { return GoogleMaps.guideMap; }

  /** Remove all guide markers and the route polyline from the map. */
  function clearGuideMarkers() {
    window._mapsGuideMarkers.forEach(m => {
      if (m && typeof m.setMap   === 'function') m.setMap(null);
      if (m && typeof m.onRemove === 'function') m.onRemove();
    });
    window._mapsGuideMarkers = [];
    if (window._mapsGuidePolyline) {
      if (typeof window._mapsGuidePolyline.setMap === 'function') window._mapsGuidePolyline.setMap(null);
      window._mapsGuidePolyline = null;
    }
    clearGuideEntityMarkers();
  }

  /** Remove all hotel/activity entity markers from the guide map. */
  function clearGuideEntityMarkers() {
    window._mapsGuideEntityMarkers.forEach(m => {
      if (m && typeof m.setMap   === 'function') m.setMap(null);
      if (m && typeof m.onRemove === 'function') m.onRemove();
    });
    window._mapsGuideEntityMarkers = [];
  }

  /**
   * Async: place hotel and activity markers for every stop on the main guide map.
   * Coordinates are resolved via resolveEntityCoordinates (cached per session).
   * Uses _buildStopMapPin / _buildStopMapPopup from guide-stops.js (globals).
   */
  async function setGuideEntityMarkers(plan) {
    const map = GoogleMaps.guideMap;
    if (!map) return;
    const stops = plan.stops || [];

    // Build entity list — hotels + top activities only (keep density manageable)
    const entities = [];
    stops.forEach(stop => {
      const acc = stop.accommodation;
      if (acc && acc.name) {
        entities.push({
          key: 'gm-hotel-' + stop.id,
          placeId: acc.place_id || null,
          name: acc.name,
          stopLat: stop.lat, stopLng: stop.lng,
          searchType: 'hotel',
          type: 'hotel', data: acc, stopId: String(stop.id),
        });
      }
      (stop.top_activities || []).forEach((act, i) => {
        if (!act.name) return;
        entities.push({
          key: 'gm-act-' + stop.id + '-' + i,
          placeId: act.place_id || null,
          lat: act.lat || null,
          lng: act.lon || null,   // API uses "lon" not "lng"
          name: act.name,
          stopLat: stop.lat, stopLng: stop.lng,
          searchType: 'activity',
          type: 'activity', data: act, stopId: String(stop.id),
        });
      });
    });

    if (entities.length === 0) return;

    let coords;
    try {
      coords = await GoogleMaps.resolveEntityCoordinates(entities);
    } catch (e) {
      return;
    }
    if (!coords || coords.size === 0) return;

    let _openInfoWindow = null;
    for (const ent of entities) {
      const pos = coords.get(ent.key);
      if (!pos) continue;

      // Use pin/popup builders from guide-stops.js (loaded as globals)
      const pinHtml   = typeof _buildStopMapPin  === 'function' ? _buildStopMapPin(ent.type, ent.data)  : '<div class="stop-map-pin">📍</div>';
      const popupHtml = typeof _buildStopMapPopup === 'function' ? _buildStopMapPopup(ent.type, ent.data) : '<div>' + esc(ent.name) + '</div>';
      const infoWindow = new google.maps.InfoWindow({ content: popupHtml });

      let hoverTimeout = null;
      const overlay = GoogleMaps.createDivMarker(map, pos, pinHtml, null);
      overlay._entityType = ent.type;
      overlay._stopId     = ent.stopId;

      // Hover → open info window
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
          }, 300);
        });
      };

      window._mapsGuideEntityMarkers.push(overlay);
    }
  }

  /** Show/hide entity markers by type array, e.g. ['hotel', 'activity']. */
  function filterGuideEntityMarkers(visibleTypes) {
    window._mapsGuideEntityMarkers.forEach(m => {
      if (!m || !m._div) return;
      m._div.style.display = visibleTypes.indexOf(m._entityType) !== -1 ? '' : 'none';
    });
  }

  /** Place numbered stop markers and a driving route polyline for the full plan. */
  function setGuideMarkers(plan, onMarkerClick) {
    clearGuideMarkers();
    const map = GoogleMaps.guideMap;
    if (!map) return;
    const stops = plan.stops || [], bounds = new google.maps.LatLngBounds();
    let hasBounds = false;
    const routePoints = [];

    if (plan.start_lat && plan.start_lng) {
      const pos = { lat: plan.start_lat, lng: plan.start_lng };
      window._mapsGuideMarkers.push(
        GoogleMaps.createDivMarker(map, pos,
          '<div class="guide-marker" data-stop-id="start"><div class="guide-marker-num">S</div></div>', null)
      );
      bounds.extend(pos); hasBounds = true; routePoints.push(pos);
    }

    stops.forEach(stop => {
      if (!stop.lat || !stop.lng) return;
      const pos    = { lat: stop.lat, lng: stop.lng };
      const stopId = String(stop.id);
      const m = GoogleMaps.createDivMarker(map, pos,
        '<div class="guide-marker" data-stop-id="' + esc(stopId) + '"><div class="guide-marker-num">' + stop.id + '</div></div>',
        () => { if (onMarkerClick) onMarkerClick(stopId); }
      );
      m._stopId = stopId;
      window._mapsGuideMarkers.push(m);
      bounds.extend(pos); hasBounds = true; routePoints.push(pos);
    });

    if (routePoints.length >= 2) {
      GoogleMaps.renderDrivingRoute(map, routePoints, { strokeColor: '#2D2B3D', strokeWeight: 3, strokeOpacity: 1.0 })
        .then(r => { window._mapsGuidePolyline = r; });
    }

    stops.forEach((stop, i) => {
      if (!stop.is_ferry || i === 0) return;
      const prev = stops[i - 1];
      const prevPos = prev ? { lat: prev.lat, lng: prev.lng }
                           : (plan.start_lat ? { lat: plan.start_lat, lng: plan.start_lng } : null);
      if (!prevPos || !stop.lat || !stop.lng) return;
      window._mapsGuideMarkers.push(new google.maps.Polyline({
        map,
        path: [new google.maps.LatLng(prevPos.lat, prevPos.lng), new google.maps.LatLng(stop.lat, stop.lng)],
        strokeColor: '#2D2B3D', strokeWeight: 3, strokeOpacity: 0,
        icons: [{ icon: { path: 'M 0,-1 0,1', strokeOpacity: 1, strokeColor: '#2D2B3D', scale: 3 }, offset: '0', repeat: '14px' }],
      }));
    });

    if (hasBounds) {
      map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
      google.maps.event.addListenerOnce(map, 'bounds_changed', () => { if (map.getZoom() > 9) map.setZoom(9); });
    }
  }

  // ---------------------------------------------------------------------------
  // Viewport helpers
  // ---------------------------------------------------------------------------

  /** Visually select the marker for stopId and deselect all others. */
  function highlightGuideMarker(stopId) {
    window._mapsGuideMarkers.forEach(m => {
      if (!m || !m._div) return;
      const markerEl = m._div.querySelector('.guide-marker-num');
      if (!markerEl) return;
      const parentEl = m._div.querySelector('.guide-marker');
      const markerId = parentEl ? parentEl.dataset.stopId : null;
      if (markerId === stopId) markerEl.classList.add('selected');
      else markerEl.classList.remove('selected');
    });
  }

  /** Pan the guide map to center on the stop with the given id. */
  function panToStop(stopId, stops) {
    const map  = GoogleMaps.guideMap;
    const stop = (stops || []).find(s => String(s.id) === stopId);
    if (map && stop && stop.lat && stop.lng) map.panTo({ lat: stop.lat, lng: stop.lng });
  }

  /** Fit the guide map to show all stops in the plan including the start location. */
  function fitAllStops(plan) {
    const map = GoogleMaps.guideMap;
    if (!map) return;
    const bounds = new google.maps.LatLngBounds();
    let hasBounds = false;
    if (plan.start_lat && plan.start_lng) { bounds.extend({ lat: plan.start_lat, lng: plan.start_lng }); hasBounds = true; }
    (plan.stops || []).forEach(s => { if (s.lat && s.lng) { bounds.extend({ lat: s.lat, lng: s.lng }); hasBounds = true; } });
    if (hasBounds) map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
  }

  /** Fit the guide map to show only the stops for a single day (max zoom 13). */
  function fitDayStops(stops) {
    const map = GoogleMaps.guideMap;
    if (!map || !stops.length) return;
    const bounds = new google.maps.LatLngBounds();
    stops.forEach(s => { if (s.lat && s.lng) bounds.extend({ lat: s.lat, lng: s.lng }); });
    map.fitBounds(bounds, { top: 48, right: 48, bottom: 48, left: 48 });
    google.maps.event.addListenerOnce(map, 'idle', function () { if (map.getZoom() > 13) map.setZoom(13); });
  }

  // ---------------------------------------------------------------------------
  // Marker opacity helpers
  // ---------------------------------------------------------------------------

  /** Dim all markers not in focusedStopIds to 35% opacity. */
  function dimNonFocusedMarkers(focusedStopIds) {
    window._mapsGuideMarkers.forEach(function (m) {
      if (!m || !m._div) return;
      m._div.style.transition = 'opacity 0.3s ease';
      m._div.style.opacity = (m._stopId === undefined || focusedStopIds.indexOf(String(m._stopId)) === -1) ? '0.35' : '1';
    });
    window._mapsGuideEntityMarkers.forEach(function (m) {
      if (!m || !m._div) return;
      m._div.style.transition = 'opacity 0.3s ease';
      m._div.style.opacity = (m._stopId === undefined || focusedStopIds.indexOf(String(m._stopId)) === -1) ? '0.35' : '1';
    });
  }

  /** Restore all markers to full opacity. */
  function restoreAllMarkers() {
    window._mapsGuideMarkers.forEach(function (m) {
      if (!m || !m._div) return;
      m._div.style.transition = 'opacity 0.3s ease';
      m._div.style.opacity    = '1';
    });
    window._mapsGuideEntityMarkers.forEach(function (m) {
      if (!m || !m._div) return;
      m._div.style.transition = 'opacity 0.3s ease';
      m._div.style.opacity    = '1';
    });
  }

  // ---------------------------------------------------------------------------
  // Interaction
  // ---------------------------------------------------------------------------

  /** Register a click listener on the map that suppresses place popups and calls onMapClick. */
  function enableClickToAdd(map, onMapClick) {
    google.maps.event.addListener(map, 'click', function (event) {
      if (event.placeId) event.stop();
      onMapClick(event.latLng);
    });
  }

  return { getGuideMap, clearGuideMarkers, setGuideMarkers, highlightGuideMarker,
           panToStop, fitAllStops, fitDayStops, dimNonFocusedMarkers, restoreAllMarkers, enableClickToAdd,
           setGuideEntityMarkers, clearGuideEntityMarkers, filterGuideEntityMarkers };
})());
