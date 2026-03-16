'use strict';

/**
 * GoogleMaps singleton — wraps Google Maps JS SDK.
 * Loaded dynamically after /api/maps-config resolves.
 * Fires 'google-maps-ready' on window when the API is ready.
 */
const GoogleMaps = (() => {
  let _routeMap = null;
  let _guideMap = null;
  let _apiKey = '';

  // Cache: place name|lat|lng|context → [url, ...]
  const _imageCache = new Map();

  /** Push a message to the frontend debug log panel. */
  function _log(level, message) {
    if (typeof S !== 'undefined' && Array.isArray(S.logs)) {
      S.logs.push({ level, agent: 'GoogleMaps', message });
      if (typeof updateDebugLog === 'function') updateDebugLog();
    }
    if (level === 'WARNING' || level === 'ERROR') {
      console.warn('[GoogleMaps]', message);
    }
  }

  /** Called by Maps SDK as callback= parameter. */
  function _onApiReady() {
    _log('INFO', 'Google Maps API bereit');
    document.dispatchEvent(new CustomEvent('google-maps-ready'));
  }

  /**
   * Create (or reuse) the route-builder map.
   */
  function initRouteMap(elId, opts) {
    const el = document.getElementById(elId);
    if (!el) { _log('WARNING', `initRouteMap: Element #${elId} nicht gefunden`); return null; }
    if (_routeMap) return _routeMap;
    try {
      _routeMap = new google.maps.Map(el, {
        center: (opts && opts.center) || { lat: 47, lng: 8 },
        zoom:   (opts && opts.zoom)   || 6,
        mapTypeControl: false,
        streetViewControl: false,
      });
    } catch (e) {
      _log('ERROR', `initRouteMap fehlgeschlagen: ${e.message}`);
      return null;
    }
    return _routeMap;
  }

  /**
   * Always create a fresh guide map (element may be replaced by innerHTML).
   */
  function initGuideMap(elId, opts) {
    const el = document.getElementById(elId);
    if (!el) { _log('WARNING', `initGuideMap: Element #${elId} nicht gefunden`); return null; }
    try {
      _guideMap = new google.maps.Map(el, {
        center: (opts && opts.center) || { lat: 47, lng: 8 },
        zoom:   (opts && opts.zoom)   || 6,
        mapTypeControl: false,
        streetViewControl: false,
      });
    } catch (e) {
      _log('ERROR', `initGuideMap fehlgeschlagen: ${e.message}`);
      return null;
    }
    return _guideMap;
  }

  /**
   * Create a div-based marker via OverlayView (no mapId required).
   */
  function createDivMarker(map, pos, html, onClick) {
    const latLng = new google.maps.LatLng(pos.lat, pos.lng);
    const overlay = new google.maps.OverlayView();

    overlay.onAdd = function () {
      const div = document.createElement('div');
      div.style.position = 'absolute';
      div.style.cursor = 'pointer';
      div.innerHTML = html;
      if (onClick) div.addEventListener('click', onClick);
      this.getPanes().overlayMouseTarget.appendChild(div);
      this._div = div;
    };

    overlay.draw = function () {
      const proj = this.getProjection();
      if (!proj || !this._div) return;
      const pt = proj.fromLatLngToDivPixel(latLng);
      if (pt) {
        this._div.style.left = (pt.x - 14) + 'px';
        this._div.style.top  = (pt.y - 14) + 'px';
      }
    };

    overlay.onRemove = function () {
      if (this._div) { this._div.parentNode && this._div.parentNode.removeChild(this._div); this._div = null; }
    };

    overlay.setMap(map);
    return overlay;
  }

  /**
   * Attach Places Autocomplete to an input element using the new
   * PlaceAutocompleteElement API. The web component is overlaid on top of
   * the existing <input>; when a place is selected the input value is updated
   * and a 'place_changed' custom event is dispatched on the input so that
   * existing form.js listeners keep working unchanged.
   *
   * Returns the PlaceAutocompleteElement instance (or null on failure).
   */
  function attachAutocomplete(inputId, opts) {
    const inputEl = document.getElementById(inputId);
    if (!inputEl) { _log('WARNING', `attachAutocomplete: #${inputId} nicht gefunden`); return null; }
    if (!google.maps.places || !google.maps.places.PlaceAutocompleteElement) {
      _log('WARNING', 'PlaceAutocompleteElement nicht verfügbar');
      return null;
    }

    // Wrap the input in a relative-positioned container so the autocomplete
    // element can sit directly on top.
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:relative; display:contents;';
    inputEl.parentNode.insertBefore(wrapper, inputEl);
    wrapper.appendChild(inputEl);

    const acEl = new google.maps.places.PlaceAutocompleteElement({
      includedPrimaryTypes: (opts && opts.types) ? opts.types : ['(cities)'],
    });

    // Style the autocomplete element to match the original input visually
    acEl.style.cssText = inputEl.style.cssText;
    acEl.className = inputEl.className;

    // Insert right after the input
    inputEl.parentNode.insertBefore(acEl, inputEl.nextSibling);

    // Hide original input — the autocomplete element handles text entry
    inputEl.style.display = 'none';

    acEl.addEventListener('gmp-select', async ({ placePrediction }) => {
      try {
        const place = placePrediction.toPlace();
        await place.fetchFields({ fields: ['displayName', 'formattedAddress', 'location'] });

        const addr = place.formattedAddress || place.displayName || '';
        // Restore original input with the resolved address so form.js can read it
        inputEl.style.display = '';
        inputEl.value = addr;
        inputEl.style.display = 'none';

        // Dispatch synthetic event so existing ac.addListener('place_changed') equivalents fire
        inputEl.dispatchEvent(new CustomEvent('place_changed', {
          detail: { formatted_address: addr, place },
          bubbles: true,
        }));
      } catch (e) {
        _log('WARNING', `Autocomplete place fetch fehlgeschlagen: ${e.message}`);
      }
    });

    // Return a compatibility shim so form.js addListener('place_changed', cb) works
    return {
      _acEl: acEl,
      _inputEl: inputEl,
      addListener(event, cb) {
        if (event === 'place_changed') {
          inputEl.addEventListener('place_changed', (e) => {
            // Provide getPlace() compatible with legacy form.js code
            this._lastPlace = e.detail;
            cb();
          });
        }
      },
      getPlace() {
        return this._lastPlace || {};
      },
    };
  }

  // ---------------------------------------------------------------------------
  // Photo fetching — new Places API (google.maps.places.Place)
  // ---------------------------------------------------------------------------

  /**
   * Fetch up to 5 images for a place. Strategy:
   * 1a. Nearby search (tourist_attraction) by lat/lng — best for cities/regions
   * 1b. Text search by name + location bias — best for specific POIs
   * 2.  Google Static Maps satellite — always available with API key
   * 3.  SVG gradient placeholder
   *
   * Returns Promise<string[]> — 1–5 URLs.
   */
  async function getPlaceImages(name, lat, lng, context, placeId) {
    const cacheKey = name + '|' + (lat || '') + '|' + (lng || '') + '|' + (context || '') + '|' + (placeId || '');
    if (_imageCache.has(cacheKey)) return _imageCache.get(cacheKey);

    const urls = await _fetchImagesWithFallback(name, lat, lng, context, placeId);
    _imageCache.set(cacheKey, urls);
    return urls;
  }

  async function _fetchImagesWithFallback(name, lat, lng, context, placeId) {
    // Tier 0: Place Details by ID (most accurate, cheapest)
    if (placeId) {
      try {
        const { Place } = await google.maps.importLibrary('places');
        const place = new Place({ id: placeId });
        await place.fetchFields({ fields: ['photos'] });
        if (place.photos && place.photos.length >= 1) {
          return place.photos.slice(0, 5).map(p => p.getURI({ maxWidth: 800, maxHeight: 600 }));
        }
      } catch (e) {
        _log('WARNING', `Place Details Fotos fehlgeschlagen für ${placeId}: ${e.message}`);
      }
    }

    // Tier 1a: Nearby search by coordinates (city/region context)
    if (lat && lng && context !== 'hotel' && context !== 'restaurant' && context !== 'activity') {
      try {
        const photos = await _nearbyPhotosByLatLng(lat, lng);
        if (photos.length >= 1) return photos;
      } catch (e) {
        _log('WARNING', `Nearby-Suche fehlgeschlagen für «${name}»: ${e.message}`);
      }
    }

    // Tier 1b: Text search by name (specific POIs or fallback for cities)
    if (name) {
      try {
        const photos = await _photosByTextSearch(name, lat, lng, context);
        if (photos.length >= 1) return photos;
      } catch (e) {
        _log('WARNING', `Text-Suche fehlgeschlagen für «${name}»: ${e.message}`);
      }
    }

    // Tier 2: Static Maps satellite
    const staticUrl = _staticMapUrl(lat, lng);
    if (staticUrl) {
      _log('INFO', `Static Maps verwendet für «${name}»`);
      return [staticUrl];
    }

    // Tier 3: SVG placeholder
    _log('INFO', `SVG Platzhalter verwendet für «${name}»`);
    return [_svgPlaceholder(name)];
  }

  /** Nearby search for tourist attractions at lat/lng — returns photo URLs. */
  async function _nearbyPhotosByLatLng(lat, lng) {
    const { Place, SearchNearbyRankPreference } = await google.maps.importLibrary('places');
    const center = new google.maps.LatLng(lat, lng);

    const { places } = await Place.searchNearby({
      fields: ['photos'],
      locationRestriction: { center, radius: 15000 },
      includedPrimaryTypes: ['tourist_attraction'],
      maxResultCount: 10,
      rankPreference: SearchNearbyRankPreference.POPULARITY,
    });

    // Return photos from the first result that has them
    for (const place of (places || [])) {
      if (place.photos && place.photos.length >= 1) {
        return place.photos.slice(0, 5).map(p => p.getURI({ maxWidth: 800, maxHeight: 600 }));
      }
    }
    return [];
  }

  /** Text search for a named place — returns photo URLs. */
  async function _photosByTextSearch(name, lat, lng, context) {
    const { Place } = await google.maps.importLibrary('places');

    const searchOpts = {
      textQuery: name,
      fields: ['photos'],
      maxResultCount: 5,
    };

    // Add type filter for specific contexts
    if (context === 'hotel')      searchOpts.includedType = 'lodging';
    if (context === 'restaurant') searchOpts.includedType = 'restaurant';
    if (context === 'activity')   searchOpts.includedType = 'tourist_attraction';

    // Location bias if coordinates are available
    if (lat && lng) {
      searchOpts.locationBias = new google.maps.LatLng(lat, lng);
    }

    const { places } = await Place.searchByText(searchOpts);

    for (const place of (places || [])) {
      if (place.photos && place.photos.length >= 1) {
        return place.photos.slice(0, 5).map(p => p.getURI({ maxWidth: 800, maxHeight: 600 }));
      }
    }
    return [];
  }

  function _staticMapUrl(lat, lng) {
    if (!lat || !lng || !_apiKey) return null;
    return `https://maps.googleapis.com/maps/api/staticmap?center=${lat},${lng}&zoom=14&size=800x400&maptype=satellite&key=${_apiKey}`;
  }

  function _svgPlaceholder(name) {
    const hue = (name.charCodeAt(0) || 72) % 360;
    const hue2 = (hue + 40) % 360;
    const label = (name || '?').slice(0, 20);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:hsl(${hue},60%,55%)"/>
          <stop offset="100%" style="stop-color:hsl(${hue2},60%,35%)"/>
        </linearGradient>
      </defs>
      <rect width="800" height="400" fill="url(#g)"/>
      <text x="400" y="210" font-family="sans-serif" font-size="32" fill="rgba(255,255,255,0.9)"
            text-anchor="middle" dominant-baseline="middle">${label}</text>
    </svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  }

  /**
   * Create a marker using Place ID. Falls back to createDivMarker if placeId is null.
   * @param {google.maps.Map} map
   * @param {string|null} placeId - Google Place ID
   * @param {{lat: number, lng: number}} pos - fallback position
   * @param {string} html - marker HTML content
   * @param {Function} onClick - click handler
   */
  function createPlaceMarker(map, placeId, pos, html, onClick) {
    // Always use div marker with known coordinates — Place ID just enriches the info
    return createDivMarker(map, pos, html, onClick);
  }

  function _setApiKey(key) {
    _apiKey = key;
  }

  return {
    _onApiReady,
    _setApiKey,
    initRouteMap,
    initGuideMap,
    createDivMarker,
    createPlaceMarker,
    attachAutocomplete,
    getPlaceImages,
    get routeMap() { return _routeMap; },
    get guideMap()  { return _guideMap; },
  };
})();
