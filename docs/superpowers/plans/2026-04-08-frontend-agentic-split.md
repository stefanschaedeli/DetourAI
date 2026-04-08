# Frontend Agentic Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `frontend/js/maps.js` into 4 focused files, extract SSE wire protocol into `sse-client.js`, and restructure `progress.js` — so each file has one clear concern an agent can own independently.

**Architecture:** Three sequential phases, each independently deployable. Globals and `<script>` tags throughout — no build step, no import/export. Shared state between maps files uses `window._maps*` variables declared in `maps-core.js`. `GoogleMaps` singleton is the public API throughout; subsequent files extend it with `Object.assign`.

**Tech Stack:** Vanilla ES2020, plain globals, Google Maps JS SDK, Server-Sent Events (EventSource), FastAPI backend (unchanged).

---

## Phase 1 — Split `maps.js` into 4 files

### Task 1: Create `maps-core.js`

**Files:**
- Create: `frontend/js/maps-core.js`
- Delete: `frontend/js/maps.js` (in Task 5)

`maps-core.js` owns: GoogleMaps object init, shared window state, map instance creation, markers, autocomplete, coordinate resolution, `_onApiReady`, `_setApiKey`, `_getApiKey`, `_log`.

- [ ] **Step 1: Create `frontend/js/maps-core.js`**

Full file content — copy exactly:

```
'use strict';

/**
 * GoogleMaps core — map init, markers, autocomplete, coordinate resolution.
 * Loaded first of the four maps-*.js files.
 * Shared state for other maps files declared on window here.
 */
const GoogleMaps = (() => {
  // Shared state — other maps-*.js files access these via window.*
  window._mapsImageCache    = new Map();   // used by maps-images.js
  window._mapsCoordCache    = new Map();   // used here in resolveEntityCoordinates
  window._mapsGuideMarkers  = [];          // used by maps-guide.js
  window._mapsGuidePolyline = null;        // used by maps-guide.js

  let _routeMap = null;
  let _guideMap = null;
  let _apiKey   = '';

  function _log(level, message) {
    if (typeof S !== 'undefined' && Array.isArray(S.logs)) {
      S.logs.push({ level, agent: 'GoogleMaps', message });
      if (typeof updateDebugLog === 'function') updateDebugLog();
    }
    if (level === 'WARNING' || level === 'ERROR') console.warn('[GoogleMaps]', message);
  }

  function _onApiReady() {
    _log('INFO', 'Google Maps API bereit');
    document.dispatchEvent(new CustomEvent('google-maps-ready'));
  }

  function _setApiKey(key) { _apiKey = key; }
  function _getApiKey()    { return _apiKey; }

  function initRouteMap(elId, opts) {
    const el = document.getElementById(elId);
    if (!el) { _log('WARNING', 'initRouteMap: Element #' + elId + ' nicht gefunden'); return null; }
    if (_routeMap) return _routeMap;
    try {
      _routeMap = new google.maps.Map(el, {
        center: (opts && opts.center) || { lat: 47, lng: 8 },
        zoom:   (opts && opts.zoom)   || 6,
        mapTypeControl: false, streetViewControl: false,
      });
    } catch (e) { _log('ERROR', 'initRouteMap fehlgeschlagen: ' + e.message); return null; }
    return _routeMap;
  }

  function initGuideMap(elId, opts) {
    const el = document.getElementById(elId);
    if (!el) { _log('WARNING', 'initGuideMap: Element #' + elId + ' nicht gefunden'); return null; }
    try {
      _guideMap = new google.maps.Map(el, {
        center: (opts && opts.center) || { lat: 47, lng: 8 },
        zoom:   (opts && opts.zoom)   || 6,
        mapTypeControl: false, streetViewControl: false,
      });
    } catch (e) { _log('ERROR', 'initGuideMap fehlgeschlagen: ' + e.message); return null; }
    return _guideMap;
  }

  function initPersistentGuideMap(elId, opts) {
    const el = document.getElementById(elId);
    if (!el) { _log('WARNING', 'initPersistentGuideMap: Element #' + elId + ' nicht gefunden'); return null; }
    if (_guideMap && _guideMap.getDiv() && _guideMap.getDiv().isConnected) return _guideMap;
    try {
      _guideMap = new google.maps.Map(el, {
        center: (opts && opts.center) || { lat: 47, lng: 8 },
        zoom:   (opts && opts.zoom)   || 6,
        mapTypeControl: false, streetViewControl: false,
        gestureHandling: window.innerWidth < 768 ? 'cooperative' : 'greedy',
      });
    } catch (e) { _log('ERROR', 'initPersistentGuideMap fehlgeschlagen: ' + e.message); return null; }
    return _guideMap;
  }

  function initStopOverviewMap(elId, opts) {
    const el = document.getElementById(elId);
    if (!el) { _log('WARNING', 'initStopOverviewMap: Element #' + elId + ' nicht gefunden'); return null; }
    try {
      return new google.maps.Map(el, {
        center: (opts && opts.center) || { lat: 47, lng: 8 },
        zoom:   (opts && opts.zoom)   || 13,
        mapTypeControl: false, streetViewControl: false,
        fullscreenControl: false, zoomControl: true,
      });
    } catch (e) { _log('ERROR', 'initStopOverviewMap fehlgeschlagen: ' + e.message); return null; }
  }

  function createDivMarker(map, pos, html, onClick) {
    const latLng  = new google.maps.LatLng(pos.lat, pos.lng);
    const overlay = new google.maps.OverlayView();
    overlay.onAdd = function () {
      const div = document.createElement('div');
      div.style.position = 'absolute';
      div.style.cursor   = 'pointer';
      div.innerHTML      = html;
      if (onClick) div.addEventListener('click', onClick);
      this.getPanes().overlayMouseTarget.appendChild(div);
      this._div = div;
    };
    overlay.draw = function () {
      const proj = this.getProjection();
      if (!proj || !this._div) return;
      const pt = proj.fromLatLngToDivPixel(latLng);
      if (pt) { this._div.style.left = (pt.x - 14) + 'px'; this._div.style.top = (pt.y - 14) + 'px'; }
    };
    overlay.onRemove = function () {
      if (this._div) { this._div.parentNode && this._div.parentNode.removeChild(this._div); this._div = null; }
    };
    overlay.setMap(map);
    return overlay;
  }

  function createPlaceMarker(map, placeId, pos, html, onClick) {
    return createDivMarker(map, pos, html, onClick);
  }

  function attachAutocomplete(inputId, opts) {
    const inputEl = document.getElementById(inputId);
    if (!inputEl) { _log('WARNING', 'attachAutocomplete: #' + inputId + ' nicht gefunden'); return null; }
    if (!google.maps.places || !google.maps.places.PlaceAutocompleteElement) {
      _log('WARNING', 'PlaceAutocompleteElement nicht verfügbar'); return null;
    }
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:relative; display:contents;';
    inputEl.parentNode.insertBefore(wrapper, inputEl);
    wrapper.appendChild(inputEl);
    const acEl = new google.maps.places.PlaceAutocompleteElement({
      includedPrimaryTypes: (opts && opts.types) ? opts.types : ['(cities)'],
    });
    acEl.style.cssText = inputEl.style.cssText;
    acEl.className     = inputEl.className;
    inputEl.parentNode.insertBefore(acEl, inputEl.nextSibling);
    inputEl.style.display = 'none';
    acEl.addEventListener('gmp-select', async ({ placePrediction }) => {
      try {
        const place = placePrediction.toPlace();
        await place.fetchFields({ fields: ['displayName', 'formattedAddress', 'location'] });
        const addr = place.formattedAddress || place.displayName || '';
        inputEl.style.display = '';
        inputEl.value         = addr;
        inputEl.style.display = 'none';
        inputEl.dispatchEvent(new CustomEvent('place_changed', { detail: { formatted_address: addr, place }, bubbles: true }));
      } catch (e) { _log('WARNING', 'Autocomplete place fetch fehlgeschlagen: ' + e.message); }
    });
    return {
      _acEl: acEl, _inputEl: inputEl,
      addListener(event, cb) {
        if (event === 'place_changed') {
          inputEl.addEventListener('place_changed', (e) => { this._lastPlace = e.detail; cb(); });
        }
      },
      getPlace() { return this._lastPlace || {}; },
    };
  }

  async function resolveEntityCoordinates(entities) {
    const results       = new Map();
    const toFetchById   = [];
    const toFetchByText = [];
    for (const ent of entities) {
      if (window._mapsCoordCache.has(ent.key)) { results.set(ent.key, window._mapsCoordCache.get(ent.key)); continue; }
      if (ent.lat && ent.lng) {
        const coord = { lat: ent.lat, lng: ent.lng };
        window._mapsCoordCache.set(ent.key, coord); results.set(ent.key, coord); continue;
      }
      if (ent.placeId) toFetchById.push(ent); else if (ent.name) toFetchByText.push(ent);
    }
    if (toFetchById.length === 0 && toFetchByText.length === 0) return results;
    const { Place } = await google.maps.importLibrary('places');
    if (toFetchById.length > 0) {
      const settled = await Promise.allSettled(toFetchById.map(async (ent) => {
        const place = new Place({ id: ent.placeId });
        await place.fetchFields({ fields: ['location'] });
        if (place.location) {
          const coord = { lat: place.location.lat(), lng: place.location.lng() };
          window._mapsCoordCache.set(ent.key, coord); results.set(ent.key, coord);
        }
      }));
      settled.forEach((r, i) => { if (r.status === 'rejected') { _log('WARNING', 'Koordinaten (ID) fuer ' + toFetchById[i].name + ' fehlgeschlagen: ' + r.reason); toFetchByText.push(toFetchById[i]); } });
    }
    if (toFetchByText.length > 0) {
      const settled = await Promise.allSettled(toFetchByText.map(async (ent) => {
        if (results.has(ent.key)) return;
        const searchOpts = { textQuery: ent.name, fields: ['location'], maxResultCount: 1 };
        if (ent.searchType === 'restaurant') searchOpts.includedType = 'restaurant';
        else if (ent.searchType === 'hotel') searchOpts.includedType = 'lodging';
        if (ent.stopLat && ent.stopLng) searchOpts.locationBias = { center: { lat: ent.stopLat, lng: ent.stopLng }, radius: 50000 };
        const { places } = await Place.searchByText(searchOpts);
        if (places && places[0] && places[0].location) {
          const coord = { lat: places[0].location.lat(), lng: places[0].location.lng() };
          window._mapsCoordCache.set(ent.key, coord); results.set(ent.key, coord);
        }
      }));
      settled.forEach((r, i) => { if (r.status === 'rejected') _log('WARNING', 'Koordinaten (Text) fuer ' + toFetchByText[i].name + ' fehlgeschlagen: ' + r.reason); });
    }
    return results;
  }

  return {
    _onApiReady, _setApiKey, _getApiKey, _log,
    initRouteMap, initGuideMap, initPersistentGuideMap, initStopOverviewMap,
    createDivMarker, createPlaceMarker, attachAutocomplete, resolveEntityCoordinates,
    get routeMap() { return _routeMap; },
    get guideMap()  { return _guideMap; },
  };
})();
```

- [ ] **Step 2: Verify file created**

```bash
wc -l frontend/js/maps-core.js
```
Expected: ~140 lines.

---

### Task 2: Create `maps-images.js`

**Files:**
- Create: `frontend/js/maps-images.js`

- [ ] **Step 1: Create `frontend/js/maps-images.js`**

```
'use strict';

/**
 * GoogleMaps images — photo fetching via Google Places API.
 * Requires maps-core.js to load first.
 * Uses window._mapsImageCache (declared in maps-core.js).
 * Uses GoogleMaps._getApiKey() for static map URLs.
 */
Object.assign(GoogleMaps, (() => {

  async function getPlaceImages(name, lat, lng, context, placeId) {
    const cacheKey = name + '|' + (lat || '') + '|' + (lng || '') + '|' + (context || '') + '|' + (placeId || '');
    if (window._mapsImageCache.has(cacheKey)) return window._mapsImageCache.get(cacheKey);
    const urls = await _fetchImagesWithFallback(name, lat, lng, context, placeId);
    window._mapsImageCache.set(cacheKey, urls);
    return urls;
  }

  async function _fetchImagesWithFallback(name, lat, lng, context, placeId) {
    const googleReady = typeof google !== 'undefined' && google.maps;

    if (googleReady && placeId) {
      try {
        const { Place } = await google.maps.importLibrary('places');
        const place = new Place({ id: placeId });
        await place.fetchFields({ fields: ['photos'] });
        if (place.photos && place.photos.length >= 1)
          return place.photos.slice(0, 5).map(p => p.getURI({ maxWidth: 800, maxHeight: 600 }));
      } catch (e) { GoogleMaps._log('WARNING', 'Place Details Fotos fehlgeschlagen fuer ' + placeId + ': ' + e.message); }
    }

    if (googleReady && lat && lng && context !== 'hotel' && context !== 'restaurant' && context !== 'activity') {
      try {
        const photos = await _nearbyPhotosByLatLng(lat, lng);
        if (photos.length >= 1) return photos;
      } catch (e) { GoogleMaps._log('WARNING', 'Nearby-Suche fehlgeschlagen fuer ' + name + ': ' + e.message); }
    }

    if (googleReady && name) {
      try {
        const photos = await _photosByTextSearch(name, lat, lng, context);
        if (photos.length >= 1) return photos;
      } catch (e) { GoogleMaps._log('WARNING', 'Text-Suche fehlgeschlagen fuer ' + name + ': ' + e.message); }
    }

    const staticUrl = _staticMapUrl(lat, lng);
    if (staticUrl) { GoogleMaps._log('INFO', 'Static Maps verwendet fuer ' + name); return [staticUrl]; }

    GoogleMaps._log('INFO', 'SVG Platzhalter verwendet fuer ' + name);
    return [_svgPlaceholder(name)];
  }

  async function _nearbyPhotosByLatLng(lat, lng) {
    const { Place, SearchNearbyRankPreference } = await google.maps.importLibrary('places');
    const { places } = await Place.searchNearby({
      fields: ['photos'],
      locationRestriction: { center: new google.maps.LatLng(lat, lng), radius: 15000 },
      includedPrimaryTypes: ['tourist_attraction'],
      maxResultCount: 10,
      rankPreference: SearchNearbyRankPreference.POPULARITY,
    });
    for (const place of (places || []))
      if (place.photos && place.photos.length >= 1)
        return place.photos.slice(0, 5).map(p => p.getURI({ maxWidth: 800, maxHeight: 600 }));
    return [];
  }

  async function _photosByTextSearch(name, lat, lng, context) {
    const { Place } = await google.maps.importLibrary('places');
    const searchOpts = { textQuery: name, fields: ['photos'], maxResultCount: 5 };
    if (context === 'hotel')      searchOpts.includedType = 'lodging';
    if (context === 'restaurant') searchOpts.includedType = 'restaurant';
    if (context === 'activity')   searchOpts.includedType = 'tourist_attraction';
    if (lat && lng) searchOpts.locationBias = new google.maps.LatLng(lat, lng);
    const { places } = await Place.searchByText(searchOpts);
    for (const place of (places || []))
      if (place.photos && place.photos.length >= 1)
        return place.photos.slice(0, 5).map(p => p.getURI({ maxWidth: 800, maxHeight: 600 }));
    return [];
  }

  function _staticMapUrl(lat, lng) {
    const key = GoogleMaps._getApiKey();
    if (!lat || !lng || !key) return null;
    return 'https://maps.googleapis.com/maps/api/staticmap?center=' + lat + ',' + lng + '&zoom=14&size=800x400&maptype=satellite&key=' + key;
  }

  function _svgPlaceholder(name) {
    const hue   = (name.charCodeAt(0) || 72) % 360;
    const hue2  = (hue + 40) % 360;
    const label = (name || '?').slice(0, 20);
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400">'
      + '<defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">'
      + '<stop offset="0%" style="stop-color:hsl(' + hue + ',60%,55%)"/>'
      + '<stop offset="100%" style="stop-color:hsl(' + hue2 + ',60%,35%)"/>'
      + '</linearGradient></defs>'
      + '<rect width="800" height="400" fill="url(#g)"/>'
      + '<text x="400" y="210" font-family="sans-serif" font-size="32" fill="rgba(255,255,255,0.9)" text-anchor="middle" dominant-baseline="middle">' + label + '</text>'
      + '</svg>';
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  }

  return { getPlaceImages };
})());
```

- [ ] **Step 2: Verify file created**

```bash
wc -l frontend/js/maps-images.js
```
Expected: ~80 lines.

---

### Task 3: Create `maps-routes.js`

**Files:**
- Create: `frontend/js/maps-routes.js`

- [ ] **Step 1: Create `frontend/js/maps-routes.js`**

```
'use strict';

/**
 * GoogleMaps routes — driving route rendering via Google Routes API.
 * Requires maps-core.js to load first.
 */
Object.assign(GoogleMaps, (() => {

  async function renderDrivingRoute(map, waypoints, opts) {
    if (!waypoints || waypoints.length < 2) return { setMap() {} };
    const polyOpts = {
      strokeColor:   (opts && opts.strokeColor)   || '#4a90d9',
      strokeWeight:  (opts && opts.strokeWeight)  || 3,
      strokeOpacity: opts && opts.strokeOpacity != null ? opts.strokeOpacity : 0.8,
    };
    if (opts && opts.icons) polyOpts.icons = opts.icons;
    return waypoints.length > 27
      ? _renderBatchedRoute(map, waypoints, polyOpts)
      : _renderSingleRoute(map, waypoints, polyOpts);
  }

  async function _renderSingleRoute(map, waypoints, polyOpts) {
    const origin        = waypoints[0];
    const destination   = waypoints[waypoints.length - 1];
    const intermediates = waypoints.slice(1, -1).map(wp => ({ lat: wp.lat, lng: wp.lng }));
    try {
      const { Route } = await google.maps.importLibrary('routes');
      const request = {
        origin:      { lat: origin.lat,      lng: origin.lng },
        destination: { lat: destination.lat, lng: destination.lng },
        travelMode:  'DRIVING',
        fields:      ['path'],
      };
      if (intermediates.length) request.intermediates = intermediates;
      const { routes } = await Route.computeRoutes(request);
      if (!routes || !routes.length || !routes[0].path || !routes[0].path.length) {
        GoogleMaps._log('WARNING', 'Route.computeRoutes lieferte keinen Pfad, Fallback auf gerade Linie');
        return _straightLineFallback(map, waypoints, polyOpts);
      }
      return new google.maps.Polyline({ map, path: routes[0].path, ...polyOpts });
    } catch (e) {
      GoogleMaps._log('WARNING', 'Route.computeRoutes fehlgeschlagen, Fallback: ' + (e.message || e));
      return _straightLineFallback(map, waypoints, polyOpts);
    }
  }

  async function _renderBatchedRoute(map, waypoints, polyOpts) {
    const renderers = [];
    for (let i = 0; i < waypoints.length - 1; i += 26) {
      const batch = waypoints.slice(i, i + 27);
      if (batch.length < 2) break;
      try { renderers.push(await _renderSingleRoute(map, batch, polyOpts)); }
      catch (_) { renderers.push(_straightLineFallback(map, batch, polyOpts)); }
    }
    return { setMap(val) { renderers.forEach(r => { if (r && typeof r.setMap === 'function') r.setMap(val); }); } };
  }

  function _straightLineFallback(map, waypoints, polyOpts) {
    return new google.maps.Polyline({ map, path: waypoints.map(wp => new google.maps.LatLng(wp.lat, wp.lng)), ...polyOpts });
  }

  return { renderDrivingRoute };
})());
```

- [ ] **Step 2: Verify file created**

```bash
wc -l frontend/js/maps-routes.js
```
Expected: ~60 lines.

---

### Task 4: Create `maps-guide.js`

**Files:**
- Create: `frontend/js/maps-guide.js`

- [ ] **Step 1: Create `frontend/js/maps-guide.js`**

```
'use strict';

/**
 * GoogleMaps guide — persistent guide map state, markers, ferry lines, pan/fit.
 * Requires maps-core.js and maps-routes.js to load first.
 * Uses window._mapsGuideMarkers and window._mapsGuidePolyline (declared in maps-core.js).
 */
Object.assign(GoogleMaps, (() => {

  function getGuideMap() { return GoogleMaps.guideMap; }

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
  }

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

  function panToStop(stopId, stops) {
    const map  = GoogleMaps.guideMap;
    const stop = (stops || []).find(s => String(s.id) === stopId);
    if (map && stop && stop.lat && stop.lng) map.panTo({ lat: stop.lat, lng: stop.lng });
  }

  function fitAllStops(plan) {
    const map = GoogleMaps.guideMap;
    if (!map) return;
    const bounds = new google.maps.LatLngBounds();
    let hasBounds = false;
    if (plan.start_lat && plan.start_lng) { bounds.extend({ lat: plan.start_lat, lng: plan.start_lng }); hasBounds = true; }
    (plan.stops || []).forEach(s => { if (s.lat && s.lng) { bounds.extend({ lat: s.lat, lng: s.lng }); hasBounds = true; } });
    if (hasBounds) map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
  }

  function fitDayStops(stops) {
    const map = GoogleMaps.guideMap;
    if (!map || !stops.length) return;
    const bounds = new google.maps.LatLngBounds();
    stops.forEach(s => { if (s.lat && s.lng) bounds.extend({ lat: s.lat, lng: s.lng }); });
    map.fitBounds(bounds, { top: 48, right: 48, bottom: 48, left: 48 });
    google.maps.event.addListenerOnce(map, 'idle', function () { if (map.getZoom() > 13) map.setZoom(13); });
  }

  function dimNonFocusedMarkers(focusedStopIds) {
    window._mapsGuideMarkers.forEach(function (m) {
      if (!m || !m._div) return;
      m._div.style.transition = 'opacity 0.3s ease';
      m._div.style.opacity = (m._stopId === undefined || focusedStopIds.indexOf(String(m._stopId)) === -1) ? '0.35' : '1';
    });
  }

  function restoreAllMarkers() {
    window._mapsGuideMarkers.forEach(function (m) {
      if (!m || !m._div) return;
      m._div.style.transition = 'opacity 0.3s ease';
      m._div.style.opacity    = '1';
    });
  }

  function enableClickToAdd(map, onMapClick) {
    google.maps.event.addListener(map, 'click', function (event) {
      if (event.placeId) event.stop();
      onMapClick(event.latLng);
    });
  }

  return { getGuideMap, clearGuideMarkers, setGuideMarkers, highlightGuideMarker,
           panToStop, fitAllStops, fitDayStops, dimNonFocusedMarkers, restoreAllMarkers, enableClickToAdd };
})());
```

- [ ] **Step 2: Verify file created**

```bash
wc -l frontend/js/maps-guide.js
```
Expected: ~110 lines.

---

### Task 5: Update `index.html` and delete `maps.js`

**Files:**
- Modify: `frontend/index.html`
- Delete: `frontend/js/maps.js`

- [ ] **Step 1: In `frontend/index.html`, replace the maps.js script tag**

Find (around line 782):
```
<script src="/js/maps.js"></script>
```
Replace with:
```
<script src="/js/maps-core.js"></script>
<script src="/js/maps-images.js"></script>
<script src="/js/maps-routes.js"></script>
<script src="/js/maps-guide.js"></script>
```

- [ ] **Step 2: Delete `maps.js`**

```bash
rm frontend/js/maps.js
```

- [ ] **Step 3: Verify new files exist, old is gone**

```bash
ls frontend/js/maps*.js
```
Expected:
```
frontend/js/maps-core.js
frontend/js/maps-guide.js
frontend/js/maps-images.js
frontend/js/maps-routes.js
```

- [ ] **Step 4: Smoke test in browser**

Open the app. Navigate to a saved travel. Verify: map renders with stop markers, photos load in stop cards, route polyline appears. Check browser console for errors.

- [ ] **Step 5: Run backend tests**

```bash
cd backend && python3 -m pytest tests/ -v 2>&1 | tail -5
```
Expected: all pass.

- [ ] **Step 6: Commit Phase 1**

```bash
git add frontend/js/maps-core.js frontend/js/maps-images.js frontend/js/maps-routes.js frontend/js/maps-guide.js frontend/index.html
git rm frontend/js/maps.js
git commit -m "refactor: maps.js in 4 fokussierte Module aufteilen (Phase 1)

- maps-core.js: Init, Marker, Autocomplete, Koordinaten-Aufloesung
- maps-images.js: Foto-Abruf, 4-Tier-Fallback, Image-Cache
- maps-routes.js: Fahrtrouten-Rendering, Batching, Fallback
- maps-guide.js: Guide-Map-State, Marker, Faehren, Pan/Fit/Dim

GoogleMaps-Singleton bleibt oeffentliche API. Gemeinsamer Zustand
via window._maps*-Variablen. maps.js geloescht."
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Phase 2 — Extract `sse-client.js`

### Task 6: Create `sse-client.js`

**Files:**
- Create: `frontend/js/sse-client.js`

- [ ] **Step 1: Create `frontend/js/sse-client.js`**

```
'use strict';

/**
 * SSEClient — owns EventSource lifecycle and SSE wire protocol.
 *
 * SSEClient.open(jobId)  — opens EventSource, dispatches window CustomEvents
 * SSEClient.close()      — closes active connection
 *
 * Each SSE event X fires:
 *   window.dispatchEvent(new CustomEvent('sse:X', { detail: parsedData }))
 * On error:
 *   window.dispatchEvent(new CustomEvent('sse:error'))
 */
const SSEClient = (() => {
  const EVENTS = [
    'debug_log', 'route_ready', 'stop_done', 'agent_start', 'agent_done',
    'job_complete', 'job_error', 'accommodation_loading', 'accommodation_loaded',
    'accommodations_all_loaded', 'stop_research_started', 'activities_loaded',
    'restaurants_loaded', 'route_option_ready', 'route_options_done', 'ping',
    'region_plan_ready', 'region_updated', 'leg_complete',
    'replace_stop_progress', 'replace_stop_complete',
    'remove_stop_progress',  'remove_stop_complete',
    'add_stop_progress',     'add_stop_complete',
    'reorder_stops_progress', 'reorder_stops_complete',
    'update_nights_progress', 'update_nights_complete',
    'style_mismatch_warning', 'ferry_detected',
  ];

  let _source = null;

  function open(jobId) {
    close();
    const token = (typeof authGetToken === 'function') ? authGetToken() : null;
    const qs    = token ? '?token=' + encodeURIComponent(token) : '';
    _source     = new EventSource('/api/progress/' + jobId + qs);
    EVENTS.forEach(evt => {
      _source.addEventListener(evt, (e) => {
        let data = {};
        try { data = JSON.parse(e.data); } catch (_) {}
        window.dispatchEvent(new CustomEvent('sse:' + evt, { detail: data }));
      });
    });
    _source.onerror = () => { window.dispatchEvent(new CustomEvent('sse:error')); };
  }

  function close() {
    if (_source) { _source.close(); _source = null; }
  }

  return { open, close };
})();
```

- [ ] **Step 2: Verify file created**

```bash
wc -l frontend/js/sse-client.js
```
Expected: ~50 lines.

---

### Task 7: Update `api.js` — replace `openSSE` with backward-compat shim

**Files:**
- Modify: `frontend/js/api.js`
- Modify: `frontend/index.html`

The current `openSSE` function creates its own `EventSource`. Replace it with a shim that delegates to `SSEClient` while keeping the old `handlers` object API working for existing callers.

- [ ] **Step 1: In `frontend/js/api.js`, find the `openSSE` function (lines ~382–416)**

Replace the entire function — from `function openSSE(jobId, handlers) {` to its closing `}` — with:

```
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
```

Also remove the JSDoc comment block immediately above the old `openSSE` (the `/** Open SSE connection... */` block at lines ~376–381) and replace with the new one shown above.

- [ ] **Step 2: In `frontend/index.html`, add `sse-client.js` after `api.js`**

Find:
```
<script src="/js/api.js"></script>
```
Add immediately after:
```
<script src="/js/sse-client.js"></script>
```

- [ ] **Step 3: Smoke test**

Start a trip planning job. Verify SSE overlay appears and progress lines update. Open browser console — no errors about `SSEClient` or `openSSE`.

- [ ] **Step 4: Run backend tests**

```bash
cd backend && python3 -m pytest tests/ -v 2>&1 | tail -5
```
Expected: all pass.

- [ ] **Step 5: Commit Phase 2**

```bash
git add frontend/js/sse-client.js frontend/js/api.js frontend/index.html
git commit -m "refactor: SSE-Protokoll in sse-client.js extrahieren (Phase 2)

Neues SSEClient-Singleton verwaltet EventSource-Lifecycle und dispatcht
window CustomEvents ('sse:X'). openSSE() in api.js ist rueckwaerts-
kompatibler Shim — bestehende Aufrufer in progress.js und route-builder.js
unveraendert. Neue Subscriber koennen direkt auf window-Events hoeren."
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Phase 3 — Restructure `progress.js`

### Task 8: Rewrite `progress.js` with clear section separation

**Files:**
- Modify: `frontend/js/progress.js`

Restructure into three sections: UI functions, SSE event handlers, SSE subscription. No behavior changes.

- [ ] **Step 1: Replace all contents of `frontend/js/progress.js`**

```
'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let progressSSE  = null;
let stopProgress = {};  // stop_id => {activities: bool, restaurants: bool}

// ---------------------------------------------------------------------------
// UI: Debug log panel
// ---------------------------------------------------------------------------

function updateDebugLog() {
  if (!S.debugOpen) return;
  const log = document.getElementById('debug-log');
  if (!log) return;
  const recent = S.logs.slice(-50);
  log.innerHTML = recent.map(entry => {
    const level = entry.level || 'INFO';
    const agent = entry.agent ? '[' + entry.agent + '] ' : '';
    return '<div class="log-line log-' + level.toLowerCase() + '">' + esc(agent) + esc(entry.message || '') + '</div>';
  }).join('');
  log.scrollTop = log.scrollHeight;
}

function toggleDebugLog() {
  S.debugOpen = !S.debugOpen;
  const panel = document.getElementById('debug-panel');
  if (panel) panel.classList.toggle('open', S.debugOpen);
  if (S.debugOpen) updateDebugLog();
}

// ---------------------------------------------------------------------------
// UI: Stops timeline
// ---------------------------------------------------------------------------

function buildStopsTimeline(stops) {
  const timeline = document.getElementById('progress-timeline');
  if (!timeline) return;
  stopProgress = {};
  stops.forEach(s => { stopProgress[s.id] = { activities: false, restaurants: false }; });
  timeline.innerHTML = stops.map(stop => {
    const flag = FLAGS[stop.country] || '';
    return '<div class="timeline-stop" id="timeline-stop-' + stop.id + '">'
      + '<div class="timeline-dot"></div>'
      + '<div class="timeline-content">'
      + '<h4>' + flag + ' ' + esc(stop.region || stop.id) + '</h4>'
      + '<div class="timeline-status" id="timeline-status-' + stop.id + '">'
      + '<div class="shimmer-line"></div><div class="shimmer-line short"></div>'
      + '</div></div></div>';
  }).join('');
}

function markAllStopsDone() {
  document.querySelectorAll('.timeline-stop').forEach(el => el.classList.add('done'));
}

function _addAnalysisTimelineRow() {
  const timeline = document.getElementById('progress-timeline');
  if (!timeline || timeline.querySelector('#timeline-analysis')) return;
  timeline.insertAdjacentHTML('beforeend',
    '<div class="timeline-stop" id="timeline-analysis">'
    + '<div class="timeline-dot"></div>'
    + '<div class="timeline-content">'
    + '<h4>' + t('progress.analysis_label') + '</h4>'
    + '<div class="timeline-status" id="timeline-status-analysis">'
    + '<div class="shimmer-line short"></div>'
    + '</div></div></div>'
  );
}

function _completeAnalysisTimelineRow() {
  const stopEl = document.getElementById('timeline-analysis');
  if (stopEl) stopEl.classList.add('done');
  const status = document.getElementById('timeline-status-analysis');
  if (status) {
    status.innerHTML = '<div class="timeline-item done">'
      + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>'
      + '<span>' + t('progress.analysis_complete') + '</span>'
      + '</div>';
  }
}

function cancelPlanning() {
  if (!confirm(t('progress.confirm_cancel'))) return;
  if (S._sseSource) { S._sseSource.close(); S._sseSource = null; }
  Router.navigate('/');
}

// ---------------------------------------------------------------------------
// SSE event handlers
// ---------------------------------------------------------------------------

function onProgressDebugLog(data) {
  S.logs.push(data);
  updateDebugLog();
  const key   = data.message_key || '';
  const count = (data.data && data.data.count) ? data.data.count : 0;
  if      (key === 'progress.orchestrator_start')    { progressOverlay.addLine('orchestrator',  t('progress.orchestrator_starting')); progressOverlay.completeLine('orchestrator', ''); }
  else if (key === 'progress.route_architect_start') { progressOverlay.addLine('route_arch',     t('progress.route_analysis')); }
  else if (key === 'progress.research_phase')        { progressOverlay.addLine('research_phase', t('progress.research_activities', {count})); progressOverlay.completeLine('research_phase', ''); }
  else if (key === 'progress.guide_writing')         { progressOverlay.addLine('guide_phase',    t('progress.guide_writing', {count})); }
  else if (key === 'progress.day_planner_start')     { progressOverlay.completeLine('guide_phase', t('progress.guide_complete')); progressOverlay.addLine('day_planner', t('progress.day_planner_starting')); }
  else if (key === 'progress.analysis_start')        { progressOverlay.completeLine('day_planner', t('progress.day_plan_complete')); progressOverlay.addLine('trip_analysis', t('progress.trip_analysis_starting')); _addAnalysisTimelineRow(); }
  else if (key === 'progress.analysis_failed')       { progressOverlay.completeLine('trip_analysis', t('progress.analysis_skipped')); _completeAnalysisTimelineRow(); }
}

function onStopResearchStarted(data) {
  const region = data.region || '';
  if      (data.section === 'activities')  progressOverlay.addLine('act_'  + data.stop_id, t('progress.activities_for_region',  {region}));
  else if (data.section === 'restaurants') progressOverlay.addLine('rest_' + data.stop_id, t('progress.restaurants_for_region', {region}));
}

function onRouteReady(data) {
  progressOverlay.completeLine('route_arch', t('progress.route_confirmed'));
  buildStopsTimeline(data.stops || []);
  if (typeof updateSidebar === 'function') updateSidebar();
}

function onActivitiesLoaded(data) {
  const { stop_id: stopId, activities = [] } = data;
  progressOverlay.completeLine('act_' + stopId, t('progress.activities_count', {count: activities.length}));
  if (stopProgress[stopId]) stopProgress[stopId].activities = true;
  const status = document.getElementById('timeline-status-' + stopId);
  if (status) {
    const actHtml = '<div class="timeline-item done"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg><span>' + t('progress.activities_loaded', {count: activities.length}) + '</span></div>';
    status.innerHTML = actHtml + (stopProgress[stopId]?.restaurants
      ? status.querySelector('.restaurants-item')?.outerHTML || ''
      : '<div class="shimmer-line short"></div>');
  }
}

function onRestaurantsLoaded(data) {
  const { stop_id: stopId, restaurants = [] } = data;
  progressOverlay.completeLine('rest_' + stopId, t('progress.restaurants_count', {count: restaurants.length}));
  if (stopProgress[stopId]) stopProgress[stopId].restaurants = true;
  const status = document.getElementById('timeline-status-' + stopId);
  if (status) {
    const restHtml = '<div class="timeline-item done restaurants-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg><span>' + t('progress.restaurants_loaded', {count: restaurants.length}) + '</span></div>';
    const shimmer = status.querySelector('.shimmer-line.short');
    if (shimmer) shimmer.remove();
    status.insertAdjacentHTML('beforeend', restHtml);
  }
}

function onStopDone(data) {
  const stopEl = document.getElementById('timeline-stop-' + data.stop_id);
  if (stopEl) stopEl.classList.add('done');
  if (typeof updateSidebar === 'function') updateSidebar();
}

function onAgentStart(data) {
  const el = document.getElementById('progress-agent-status');
  if (el) el.textContent = data.message || t('progress.agent_starting');
}

function onAgentDone(data) {
  const el = document.getElementById('progress-agent-status');
  if (el) el.textContent = data.message || t('progress.agent_done');
}

async function onJobComplete(data) {
  if (progressSSE) { progressSSE.close(); progressSSE = null; }
  progressOverlay.completeLine('trip_analysis', t('progress.analysis_complete'));
  progressOverlay.completeLine('day_planner',   t('progress.day_plan_complete'));
  progressOverlay.completeLine('guide_phase',   t('progress.guide_complete'));
  progressOverlay.completeLine('route_arch',    t('progress.route_confirmed'));
  _completeAnalysisTimelineRow();
  progressOverlay.close();
  S.result = data;
  if (typeof updateSidebar === 'function') updateSidebar();
  lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan: data });
  markAllStopsDone();
  showLoading(t('progress.guide_preparing'));
  try {
    const saved = await apiSaveTravel(data);
    if (saved && saved.id) {
      data._saved_travel_id = saved.id;
      S.result = data;
      lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan: data });
    }
  } catch (err) { console.warn('DB-Speicherung:', err.message); }
  const travelTitle = data.custom_name || data.title || '';
  showTravelGuide(data);
  showSection('travel-guide');
  if (data._saved_travel_id) Router.navigate(Router.travelPath(data._saved_travel_id, travelTitle));
  hideLoading();
}

function onJobError(data) {
  if (progressSSE) { progressSSE.close(); progressSSE = null; }
  progressOverlay.close();
  const el = document.getElementById('progress-error');
  if (el) { el.style.display = 'block'; el.textContent = t('progress.error_prefix') + ' ' + (data.error || t('progress.unknown_error')); }
}

// ---------------------------------------------------------------------------
// SSE subscription (uses openSSE shim which delegates to SSEClient)
// ---------------------------------------------------------------------------

function connectSSE(jobId) {
  if (progressSSE) { progressSSE.close(); progressSSE = null; }
  progressSSE = openSSE(jobId, {
    route_ready:            onRouteReady,
    activities_loaded:      onActivitiesLoaded,
    restaurants_loaded:     onRestaurantsLoaded,
    stop_done:              onStopDone,
    stop_research_started:  onStopResearchStarted,
    agent_start:            onAgentStart,
    agent_done:             onAgentDone,
    job_complete:           onJobComplete,
    job_error:              onJobError,
    debug_log:              onProgressDebugLog,
    style_mismatch_warning: function (data) {
      showToast(t('progress.style_warning') + ' ' + (data.warning || ''), 'warning');
    },
    ferry_detected: function (data) {
      const crossings = data.crossings || [];
      let msg = t('progress.ferry_detected');
      if (crossings.length > 0 && crossings[0].from && crossings[0].to)
        msg += ': ' + t('progress.ferry_crossing', { from: crossings[0].from, to: crossings[0].to });
      showToast(msg, 'info');
    },
    ping:    () => {},
    onerror: () => { console.warn('Progress SSE error'); },
  });
}
```

- [ ] **Step 2: Smoke test**

Start a trip planning job. Verify: overlay appears, timeline rows fill in, debug log opens and shows entries.

- [ ] **Step 3: Run backend tests**

```bash
cd backend && python3 -m pytest tests/ -v 2>&1 | tail -5
```
Expected: all pass.

- [ ] **Step 4: Commit Phase 3**

```bash
git add frontend/js/progress.js
git commit -m "refactor: progress.js in UI-Rendering und SSE-Subscriptions trennen (Phase 3)

Datei in drei klare Abschnitte gegliedert:
1. UI-Funktionen (Debug-Log, Timeline, Stop-Karten)
2. SSE-Event-Handler (onRouteReady, onJobComplete, usw.)
3. SSE-Subscription (connectSSE via openSSE-Shim)

Kein neues Verhalten. Lesbarer fuer agentic Workers."
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 9: Update `frontend/CLAUDE.md` — module ownership

**Files:**
- Modify: `frontend/CLAUDE.md`

- [ ] **Step 1: Replace the Key Files table in `frontend/CLAUDE.md`**

Replace the entire `| File | Responsibility |` table (from the header row to the last table row) with:

```
| File | Responsibility |
|------|---------------|
| `js/state.js` | Global `S` object, TRAVEL_STYLES, FLAGS, localStorage layer |
| `js/api.js` | All fetch wrappers (`_fetch`, `_fetchQuiet`, `_fetchWithAuth`), `openSSE()` shim, all `apiXxx()` functions |
| `js/sse-client.js` | SSE wire protocol — EventSource lifecycle, auth token injection, dispatches `window` CustomEvents (`sse:X`) |
| `js/form.js` | 5-step trip form, `buildPayload()`, tag-input, via-points |
| `js/route-builder.js` | Interactive stop selection flow |
| `js/accommodation.js` | Parallel accommodation loading + selection grid |
| `js/progress.js` | SSE progress UI — stop timeline, overlay lines, debug log |
| `js/guide-core.js` | Travel guide entry point, tab routing |
| `js/guide-overview.js` | Trip overview tab |
| `js/guide-stops.js` | Stop detail cards |
| `js/guide-days.js` | Day-by-day itinerary rendering |
| `js/guide-map.js` | Guide map tab — delegates to GoogleMaps |
| `js/guide-edit.js` | Stop editing (replace, add, remove, reorder) |
| `js/guide-share.js` | Share link generation |
| `js/travels.js` | Saved travels list + management |
| `js/maps-core.js` | GoogleMaps init, markers, autocomplete, coordinate resolution |
| `js/maps-images.js` | Photo fetching (4-tier fallback), image cache — edit this to change photo quality/sources |
| `js/maps-routes.js` | Driving route rendering via Routes API, straight-line fallback |
| `js/maps-guide.js` | Persistent guide map state, stop markers, ferry lines, pan/fit/dim |
| `js/loading.js` | Loading state UI |
| `js/sse-overlay.js` | SSE progress overlay component |
| `js/auth.js` | Authentication / access control |
| `js/router.js` | Client-side routing, pattern-matched routes |
| `js/sidebar.js` | Sidebar navigation component |
| `js/settings.js` | Settings page / preferences |
| `js/i18n.js` | `t()`, `setLocale()`, `getLocale()`, `getFormattingLocale()` |
| `js/types.d.ts` | Generated from OpenAPI — do not edit manually |
| `index.html` | Entry point, `<script>` load order matters |
| `styles.css` | All styles — see DESIGN_GUIDELINE.md for design system |
```

- [ ] **Step 2: Add SSE subscriber pattern section after the Key Files table**

Add immediately after the table:

```
## SSE Subscriber Pattern

New code subscribes directly to window events — do not call `openSSE()` in new files:

```js
// New pattern (direct window event subscription)
window.addEventListener('sse:stop_done', e => {
  const data = e.detail;  // parsed SSE payload
});

// Legacy pattern (still works via openSSE shim — existing files only)
openSSE(jobId, { stop_done: (data) => { ... } });
```
```

- [ ] **Step 3: Commit docs update**

```bash
git add frontend/CLAUDE.md
git commit -m "docs: frontend/CLAUDE.md — Maps-Module und SSE-Pattern aktualisieren"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Spec coverage check

| Spec requirement | Task |
|-----------------|------|
| maps-core.js: init, markers, autocomplete, coord resolution, window._maps* declared | Task 1 |
| maps-images.js: photo fetching, 4-tier fallback, _imageCache, _getApiKey() | Task 2 |
| maps-routes.js: renderDrivingRoute, batching, straight-line fallback | Task 3 |
| maps-guide.js: guide map state, setGuideMarkers, ferry lines, pan/fit/dim | Task 4 |
| index.html load order updated, maps.js deleted | Task 5 |
| sse-client.js: EventSource, auth token, CustomEvent dispatch, all 30 events | Task 6 |
| api.js openSSE shim: backward compat, listener cleanup on close() | Task 7 |
| sse-client.js added to index.html after api.js | Task 7 |
| progress.js: 3 sections (UI, handlers, subscription), connectSSE at bottom | Task 8 |
| frontend/CLAUDE.md: updated file table + SSE subscriber pattern | Task 9 |
| Each phase: smoke test + backend tests + commit + tag + push | Tasks 5, 7, 8 |
