'use strict';

// Maps Routes — driving route rendering via Google Routes API with straight-line fallback.
// Reads: GoogleMaps (maps-core.js).
// Provides: renderDrivingRoute.

Object.assign(GoogleMaps, (() => {

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /** Render a driving route polyline on the map; batches automatically when waypoints > 27. */
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

  // ---------------------------------------------------------------------------
  // Internal rendering helpers
  // ---------------------------------------------------------------------------

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
