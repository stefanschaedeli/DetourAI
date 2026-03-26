---
phase: 04-map-centric-responsive-layout
plan: 02
subsystem: frontend-maps, frontend-guide
tags: [persistent-map, numbered-markers, polyline, bidirectional-sync, intersection-observer]
dependency_graph:
  requires: [04-01-split-panel-layout]
  provides: [persistent-guide-map, numbered-markers, map-card-sync]
  affects: [guide.js, maps.js, styles.css]
tech_stack:
  added: []
  patterns: [intersection-observer, persistent-singleton-map, gesture-handling]
key_files:
  created: []
  modified:
    - frontend/js/maps.js
    - frontend/js/guide.js
    - frontend/styles.css
decisions:
  - "initPersistentGuideMap reuses _guideMap if container still connected to DOM"
  - "Ferry segments rendered as separate dashed polyline overlaying the main route"
  - "Auto-pan suppressed for 3 seconds after user drag ends"
  - "IntersectionObserver threshold 0.6 with 300ms debounce for scroll sync"
  - "guide-map div removed from renderOverview — map lives in fixed panel"
metrics:
  duration: 4min
  completed: 2026-03-25
---

# Phase 4 Plan 02: Persistent Guide Map + Bidirectional Sync Summary

Persistent map singleton in maps.js with numbered markers (D-11), black polyline, ferry dashes, and bidirectional map-card sync via IntersectionObserver in guide.js.

## What Was Done

### Task 1: Persistent Guide Map and Numbered Markers in maps.js
- Added `initPersistentGuideMap(elId, opts)` that reuses existing map instance if DOM-connected
- Added `getGuideMap()` accessor for current map instance
- Added `clearGuideMarkers()` to remove all markers and polylines
- Added `setGuideMarkers(plan, onMarkerClick)` creating numbered circle markers with D-11 styling
- Start marker shows "S" badge, stops get numbered markers with `data-stop-id`
- Route polyline uses black `#2D2B3D` color (replacing blue `#0EA5E9`)
- Ferry segments render as dashed polyline with symbol icons (repeat 14px)
- Added `highlightGuideMarker(stopId)` toggling `.selected` CSS class
- Added `panToStop(stopId, stops)` for smooth map panning
- Added `fitAllStops(plan)` for bounds fitting with 40px padding
- Mobile gesture handling set to `cooperative` (< 768px) so single-finger scrolls page
- All 7 new methods exported in GoogleMaps IIFE return object

### Task 2: Guide.js Persistent Map + Bidirectional Sync + CSS
- Added `_setupGuideMap(plan)` called once from `showTravelGuide` before rendering
- Map drag listeners suppress auto-pan for 3 seconds after user interaction
- Removed `_initGuideMap(plan)` calls from overview/default renderGuide cases
- Added `_updateMapForTab(plan, tab)` calling `fitAllStops` on every tab switch
- Removed `<div id="guide-map">` from `renderOverview()` — map now in fixed panel
- Added `_onMarkerClick(stopId)` handler: highlights marker, scrolls to card, switches to stops tab if needed
- Added `_scrollToAndHighlightCard(stopId)` with smooth scroll and selected class
- Added `_initScrollSync()` with IntersectionObserver (threshold 0.6, 300ms debounce)
- Auto-pan on scroll only fires when user is not interacting with map
- CSS: `.guide-marker-num` 28px dark circle, `.selected` 36px accent with shadow
- CSS: `.stop-card-row.selected` / `.stop-overview-card.selected` with accent border
- CSS: hover scale(1.15) and prefers-reduced-motion support

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all functionality is wired end-to-end.

## Self-Check: PASSED
