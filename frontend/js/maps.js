'use strict';

/**
 * GoogleMaps singleton — wraps Google Maps JS SDK.
 * Loaded dynamically after /api/maps-config resolves.
 * Fires 'google-maps-ready' on window when the API is ready.
 */
const GoogleMaps = (() => {
  let _routeMap = null;
  let _guideMap = null;
  let _placesService = null;
  let _apiKey = '';

  // Cache: place name → [url, url, url]
  const _imageCache = new Map();
  // Cache: place name → place_id string
  const _placeIdCache = new Map();

  /** Called by Maps SDK as callback= parameter. */
  function _onApiReady() {
    // Create a hidden div for PlacesService (requires a map or element)
    const el = document.createElement('div');
    document.body.appendChild(el);
    _placesService = new google.maps.places.PlacesService(el);
    document.dispatchEvent(new CustomEvent('google-maps-ready'));
  }

  /**
   * Create (or reuse) the route-builder map.
   * @param {string} elId  — DOM element id
   * @param {object} opts  — {center:{lat,lng}, zoom}
   */
  function initRouteMap(elId, opts) {
    const el = document.getElementById(elId);
    if (!el) return null;
    if (_routeMap) return _routeMap;
    _routeMap = new google.maps.Map(el, {
      center: (opts && opts.center) || { lat: 47, lng: 8 },
      zoom:   (opts && opts.zoom)   || 6,
      mapTypeControl: false,
      streetViewControl: false,
    });
    return _routeMap;
  }

  /**
   * Always create a fresh guide map (element may be replaced by innerHTML).
   */
  function initGuideMap(elId, opts) {
    const el = document.getElementById(elId);
    if (!el) return null;
    _guideMap = new google.maps.Map(el, {
      center: (opts && opts.center) || { lat: 47, lng: 8 },
      zoom:   (opts && opts.zoom)   || 6,
      mapTypeControl: false,
      streetViewControl: false,
    });
    return _guideMap;
  }

  /**
   * Create a div-based marker using AdvancedMarkerElement if available,
   * falling back to google.maps.Marker.
   */
  function createDivMarker(map, pos, html, onClick) {
    if (google.maps.marker && google.maps.marker.AdvancedMarkerElement) {
      const container = document.createElement('div');
      container.innerHTML = html;
      const marker = new google.maps.marker.AdvancedMarkerElement({
        map,
        position: pos,
        content: container.firstChild || container,
      });
      if (onClick) marker.addListener('click', onClick);
      return marker;
    }
    // Fallback: standard Marker with DivIcon equivalent via label
    const marker = new google.maps.Marker({
      map,
      position: pos,
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 0,
      },
      label: '',
    });
    const overlay = new google.maps.OverlayView();
    overlay.onAdd = function () {
      const div = document.createElement('div');
      div.style.position = 'absolute';
      div.innerHTML = html;
      div.style.cursor = 'pointer';
      if (onClick) div.addEventListener('click', onClick);
      this.getPanes().overlayMouseTarget.appendChild(div);
      this._div = div;
    };
    overlay.draw = function () {
      const proj = this.getProjection();
      if (!proj) return;
      const pt = proj.fromLatLngToDivPixel(marker.getPosition());
      if (pt && this._div) {
        this._div.style.left = (pt.x - 14) + 'px';
        this._div.style.top  = (pt.y - 14) + 'px';
      }
    };
    overlay.setMap(map);
    return marker;
  }

  /**
   * Attach Google Places Autocomplete to an input element.
   */
  function attachAutocomplete(inputId, opts) {
    const el = document.getElementById(inputId);
    if (!el || !google.maps.places) return null;
    const ac = new google.maps.places.Autocomplete(el, Object.assign(
      { types: ['(cities)'], fields: ['formatted_address', 'place_id', 'geometry'] },
      opts || {}
    ));
    return ac;
  }

  /**
   * Find or fetch a Google place_id for a named place.
   * Returns null on failure.
   */
  function findPlaceId(name) {
    if (_placeIdCache.has(name)) return Promise.resolve(_placeIdCache.get(name));
    if (!_placesService) return Promise.resolve(null);
    return new Promise(resolve => {
      _placesService.findPlaceFromQuery(
        { query: name, fields: ['place_id'] },
        (results, status) => {
          if (status === google.maps.places.PlacesServiceStatus.OK && results && results[0]) {
            const id = results[0].place_id;
            _placeIdCache.set(name, id);
            resolve(id);
          } else {
            resolve(null);
          }
        }
      );
    });
  }

  /**
   * Fetch up to 3 images for a place using a tiered fallback:
   * 1. Google Places photos
   * 2. Wikipedia summary thumbnail
   * 3. Google Static Maps satellite
   * 4. SVG gradient placeholder
   *
   * Returns Promise<[overview_url, mood_url, customer_url]> — always 3 items.
   */
  async function getPlaceImages(name, lat, lng) {
    const cacheKey = name + '|' + lat + '|' + lng;
    if (_imageCache.has(cacheKey)) return _imageCache.get(cacheKey);

    const urls = await _fetchImagesWithFallback(name, lat, lng);
    _imageCache.set(cacheKey, urls);
    return urls;
  }

  async function _fetchImagesWithFallback(name, lat, lng) {
    // Tier 1: Google Places photos
    try {
      const placeId = await findPlaceId(name);
      if (placeId && _placesService) {
        const photos = await _getPlacePhotos(placeId);
        if (photos.length >= 1) {
          const urls = [
            photos[0] || null,
            photos[1] || null,
            photos[2] || null,
          ];
          // Fill empty slots with tier-2/3
          for (let i = 0; i < 3; i++) {
            if (!urls[i]) urls[i] = await _wikiImage(name) || _staticMapUrl(lat, lng) || _svgPlaceholder(name);
          }
          return urls;
        }
      }
    } catch (e) { /* fall through */ }

    // Tier 2: Wikipedia
    const wikiUrl = await _wikiImage(name);
    if (wikiUrl) {
      return [wikiUrl, _staticMapUrl(lat, lng) || _svgPlaceholder(name), _svgPlaceholder(name)];
    }

    // Tier 3: Static Maps satellite
    const staticUrl = _staticMapUrl(lat, lng);
    if (staticUrl) {
      return [staticUrl, _svgPlaceholder(name), _svgPlaceholder(name)];
    }

    // Tier 4: SVG placeholder
    const svg = _svgPlaceholder(name);
    return [svg, svg, svg];
  }

  function _getPlacePhotos(placeId) {
    return new Promise(resolve => {
      _placesService.getDetails(
        { placeId, fields: ['photos'] },
        (place, status) => {
          if (status === google.maps.places.PlacesServiceStatus.OK && place && place.photos) {
            const urls = place.photos.slice(0, 3).map(p =>
              p.getUrl({ maxWidth: 800, maxHeight: 400 })
            );
            resolve(urls);
          } else {
            resolve([]);
          }
        }
      );
    });
  }

  async function _wikiImage(name) {
    try {
      const city = name.split(',')[0].trim();
      const resp = await fetch(
        `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(city)}`,
        { headers: { Accept: 'application/json' } }
      );
      if (!resp.ok) return null;
      const data = await resp.json();
      return (data.thumbnail && data.thumbnail.source) || null;
    } catch (e) {
      return null;
    }
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

  function _setApiKey(key) {
    _apiKey = key;
  }

  return {
    _onApiReady,
    _setApiKey,
    initRouteMap,
    initGuideMap,
    createDivMarker,
    attachAutocomplete,
    getPlaceImages,
    findPlaceId,
    get routeMap() { return _routeMap; },
    get guideMap()  { return _guideMap; },
  };
})();
