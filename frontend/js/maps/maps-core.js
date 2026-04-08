'use strict';

// Maps Core — map init, markers, autocomplete, coordinate resolution.
// Reads: S (state.js), updateDebugLog (progress.js).
// Provides: initRouteMap, initGuideMap, initPersistentGuideMap, initStopOverviewMap,
//           createDivMarker, createPlaceMarker, attachAutocomplete, resolveEntityCoordinates.

const GoogleMaps = (() => {
  // ---------------------------------------------------------------------------
  // Shared state — other maps-*.js files access these via window.*
  // ---------------------------------------------------------------------------
  window._mapsImageCache    = new Map();   // used by maps-images.js
  window._mapsCoordCache    = new Map();   // used here in resolveEntityCoordinates
  window._mapsGuideMarkers  = [];          // used by maps-guide.js
  window._mapsGuidePolyline = null;        // used by maps-guide.js

  let _routeMap = null;
  let _guideMap = null;
  let _apiKey   = '';

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

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

  // ---------------------------------------------------------------------------
  // Map initialisation
  // ---------------------------------------------------------------------------

  /** Initialise (or return existing) the route-planning map in the given element. */
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

  /** Initialise a fresh guide map each time (no singleton guard). */
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

  /** Initialise or reuse a persistent guide map that survives tab switches. */
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

  /** Create a one-off map for a single stop overview card (not cached). */
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

  // ---------------------------------------------------------------------------
  // Markers
  // ---------------------------------------------------------------------------

  /** Create a custom HTML overlay marker at the given position. */
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

  /** Create a place-linked marker (delegates to createDivMarker; placeId reserved for future use). */
  function createPlaceMarker(map, placeId, pos, html, onClick) {
    return createDivMarker(map, pos, html, onClick);
  }

  // ---------------------------------------------------------------------------
  // Autocomplete
  // ---------------------------------------------------------------------------

  /** Attach a Google Places autocomplete element to an existing text input. */
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

  // ---------------------------------------------------------------------------
  // Coordinate resolution
  // ---------------------------------------------------------------------------

  /** Resolve lat/lng for a list of entities using cache, placeId lookup, or text search. */
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
