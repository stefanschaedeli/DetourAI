---
phase: 04-map-centric-responsive-layout
plan: 05
subsystem: frontend-maps, frontend-guide
tags: [click-to-add, reverse-geocode, map-interaction, haversine]
dependency_graph:
  requires: [04-02-persistent-guide-map]
  provides: [click-to-add-stop-on-map]
  affects: [guide.js, maps.js]
tech_stack:
  added: []
  patterns: [google-maps-geocoder, overlay-projection-positioning, haversine-insert-heuristic]
key_files:
  created: []
  modified:
    - frontend/js/guide.js
    - frontend/js/maps.js
decisions:
  - "Frontend reverse geocoding via Google Maps Geocoder (no backend round-trip)"
  - "Insert position determined by haversine distance to nearest stop neighbors"
  - "Popup positioned via OverlayView projection fromLatLngToContainerPixel"
  - "XSS safety via textContent instead of innerHTML for place names"
  - "Separate _doAddStopFromMap function to avoid coupling with modal-based _executeAddStop"
metrics:
  duration: 2min
  completed: 2026-03-25
---

# Phase 4 Plan 05: Click-to-Add-Stop on Map Summary

Map click triggers reverse geocode popup with place name and insert button, using haversine nearest-stop heuristic for insertion position via existing add-stop API.

## What Was Done

### Task 1: Implement click-to-add-stop on map
- Added `enableClickToAdd(map, onMapClick)` to maps.js registering click listener on empty map areas
- Added `_onMapClickToAdd(latLng)` in guide.js — checks `_editInProgress`, reverse geocodes via `google.maps.Geocoder`
- Added `_showClickToAddPopup(latLng, placeName)` — builds popup content with textContent (XSS safe), positions via OverlayView projection, adds Escape key listener
- Added `_hideClickToAddPopup()` — cleans up DOM, listeners, and stored state
- Added `_confirmClickToAdd(placeName)` — finds nearest stop via haversine, determines insert-after position by comparing distances to neighbors
- Added `_haversineKm(lat1, lon1, lat2, lon2)` utility for distance calculations
- Added `_doAddStopFromMap(placeName, afterStopId)` — calls existing `apiAddStop` API with SSE handling
- Wired `GoogleMaps.enableClickToAdd(map, _onMapClickToAdd)` in `_setupGuideMap(plan)`
- enableClickToAdd exported in GoogleMaps IIFE return object

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all functionality is wired end-to-end.

## Self-Check: PASSED
