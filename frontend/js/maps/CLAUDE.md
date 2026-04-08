# frontend/js/maps/CLAUDE.md

All Google Maps interactions. Single `GoogleMaps` namespace, extended via `Object.assign()`.
Do NOT modify backend/, infra/, core/, guide/, communication/, or features/.

## Files & Load Order

| File | Responsibility |
|------|---------------|
| `maps-core.js` | GoogleMaps IIFE — init, markers, autocomplete, coordinate resolution, shared state |
| `maps-images.js` | Photo fetching via Google Places API (4-tier fallback), image cache |
| `maps-routes.js` | Driving route polylines via Routes API, straight-line fallback, 27+ waypoint batching |
| `maps-guide.js` | Persistent guide map state — stop markers, ferry lines, pan/fit/dim |

Load order: `maps-core` → `maps-images` → `maps-routes` → `maps-guide`

## Extension Pattern

All four files share the `GoogleMaps` namespace using `Object.assign`:

```js
// maps-core.js declares the base
const GoogleMaps = (() => { … })();

// maps-images.js extends it
Object.assign(GoogleMaps, (() => { … })());
```

Never reassign `GoogleMaps` — only extend with `Object.assign`.

## Shared State (declared in maps-core.js)

- `_mapsImageCache` — Place photo cache keyed by place_id
- `_mapsCoordCache` — Geocoding result cache
- `_mapsGuideMarkers` — Active guide map markers array
- `_mapsGuidePolyline` — Active route polyline

## Key Functions

- `GoogleMaps.initMap(divId)` — initialize a map in a container
- `GoogleMaps.getPlaceImages(name, location)` — 4-tier photo fallback
- `GoogleMaps.renderDrivingRoute(map, waypoints)` — draw route with fallback
- `GoogleMaps.getGuideMap()`, `setGuideMarkers()`, `clearGuideMarkers()` — guide tab map
- `GoogleMaps.resolveCoords(location)` — geocode with caching

## Photo Fallback Tiers (maps-images.js)

1. Google Places text search photo
2. Nearby search photo
3. Wikipedia image
4. Placeholder image
