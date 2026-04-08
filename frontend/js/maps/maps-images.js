'use strict';

// Maps Images — photo fetching via Google Places API with 4-tier fallback.
// Reads: GoogleMaps (maps-core.js), window._mapsImageCache (maps-core.js).
// Provides: getPlaceImages.

Object.assign(GoogleMaps, (() => {

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /** Fetch up to 5 photo URLs for a place, using a cache keyed on name+coords+context+placeId. */
  async function getPlaceImages(name, lat, lng, context, placeId) {
    const cacheKey = name + '|' + (lat || '') + '|' + (lng || '') + '|' + (context || '') + '|' + (placeId || '');
    if (window._mapsImageCache.has(cacheKey)) return window._mapsImageCache.get(cacheKey);
    const urls = await _fetchImagesWithFallback(name, lat, lng, context, placeId);
    window._mapsImageCache.set(cacheKey, urls);
    return urls;
  }

  // ---------------------------------------------------------------------------
  // Fallback chain
  // ---------------------------------------------------------------------------

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

  // ---------------------------------------------------------------------------
  // Static map and placeholder fallbacks
  // ---------------------------------------------------------------------------

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
