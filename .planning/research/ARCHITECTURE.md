# Architecture Patterns

**Domain:** Progressive disclosure travel view redesign within existing vanilla JS SPA
**Researched:** 2026-03-27
**Focus:** Map focus/zoom management, router URL evolution, integration with existing tab architecture

## Current Architecture Analysis

### Layout Structure (as-is)

The travel guide uses a fixed split-panel layout:

```
+----------------------------------+--------------------+
|                                  |  guide-content-    |
|   guide-map-panel (58%, fixed)   |  panel (42%)       |
|   - Google Maps persistent       |  - Tab bar         |
|   - Sidebar overlay              |  - Stats bar       |
|   - Click-to-add popup           |  - #guide-content  |
|                                  |  (content swap)    |
+----------------------------------+--------------------+
```

- **Map panel:** `position: fixed`, 58% width desktop, sticky 30vh mobile
- **Content panel:** Scrollable, `margin-left: 58%`, contains tab bar + content
- **Tab switching:** Full content replacement of `#guide-content` via `renderGuide(plan, tab)`
- **Map state:** Persistent `GoogleMaps._guideMap` survives tab switches; markers/polyline recreated per tab via `_updateMapForTab()`

### Navigation Flow (as-is)

```
Overview tab
  |
  +-- switchGuideTab('stops') --> Stops list (cards)
  |     |
  |     +-- navigateToStop(id) --> Stop detail (full replace)
  |           _activeStopId set, renderGuide re-renders with detail
  |           URL: /travel/{id}/stops/{stopId}
  |
  +-- switchGuideTab('days') --> Days timeline (accordion)
        |
        +-- _toggleDayExpand(num) --> inline expand (no URL change)
        +-- navigateToDay(num) --> Day detail (full replace)
              _activeDayNum set, renderGuide re-renders with detail
              URL: /travel/{id}/days/{dayNum}
```

### Key State Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `activeTab` | string | Current tab: overview/stops/days/calendar/budget |
| `_activeStopId` | number/null | If set, stops tab shows detail instead of list |
| `_activeDayNum` | number/null | If set, days tab shows detail instead of timeline |
| `_guideMapInitialized` | bool | Whether persistent map has been set up |
| `_userInteractingWithMap` | bool | Suppresses auto-pan during drag |
| `_cardObserver` | IntersectionObserver | Scroll-sync between cards and map |

### Current Map Focus Behavior

1. **Tab switch:** `_updateMapForTab()` calls `GoogleMaps.fitAllStops(plan)` -- always zooms out to full route
2. **Card click:** `_onCardClick(stopId)` calls `panToStop()` + `highlightGuideMarker()` -- smooth pan, no zoom
3. **Scroll sync:** IntersectionObserver on cards auto-pans to visible card's stop
4. **Stop detail:** Creates separate `GoogleMaps.initStopOverviewMap()` inside `#guide-content` (NOT the persistent map)
5. **Day detail:** Creates separate `GoogleMaps.initStopOverviewMap()` for day map inside content panel
6. **Marker click:** `_onMarkerClick()` highlights marker + scrolls to card, or switches to stops tab

**Critical finding:** Stop detail and day detail create *independent mini-maps inside the content panel*, ignoring the persistent map entirely. The persistent map stays zoomed to full route even when viewing a single stop.

## Recommended Architecture

### Design Principle: Map as Primary Navigation Surface

The persistent guide map should respond to drill-down context. When the user drills into a day or stop, the persistent map should focus on that region -- not create a separate embedded map. This eliminates redundant map instances and makes the split-panel layout feel intentional.

### Component Boundaries

| Component | Responsibility | Communicates With | Change Type |
|-----------|---------------|-------------------|-------------|
| `guide.js` (renderGuide) | Tab routing + content rendering | MapFocus, Router | **Modify** -- add focus context to render calls |
| MapFocus (new logic in guide.js) | Manages persistent map zoom/bounds per view context | GoogleMaps singleton | **New** -- ~80 lines of focus management |
| Router | URL dispatch + history management | guide.js handlers | **Modify** -- no new routes needed, existing patterns sufficient |
| GoogleMaps singleton | Map API wrapper, markers, polylines | Called by MapFocus | **Modify** -- add `fitBoundsForStops(stopIds)` helper |
| Stop detail renderer | Renders stop detail HTML | MapFocus | **Modify** -- remove embedded mini-map, rely on persistent map |
| Day detail renderer | Renders day detail HTML | MapFocus | **Modify** -- remove embedded mini-map, rely on persistent map |

### Data Flow

```
User clicks "Stop 3" card
  |
  v
navigateToStop(3)
  |
  +-- _activeStopId = 3
  +-- renderGuide(plan, 'stops')  // renders stop detail content
  |     |
  |     +-- #guide-content receives renderStopDetail(plan, 3)
  |           (NO embedded map -- removed)
  |
  +-- _updateMapFocus(plan, 'stops')  // NEW
        |
        +-- stop has lat/lng?
        |     YES --> compute bounds from stop + its POIs
        |             fitBounds on persistent map
        |             highlight marker 3
        |             dim other markers (opacity 0.4)
```

```
User clicks "Tag 5" in days view
  |
  v
navigateToDay(5)
  |
  +-- _activeDayNum = 5
  +-- renderGuide(plan, 'days')  // renders day detail content
  |     |
  |     +-- #guide-content receives renderDayDetail(plan, 5)
  |           (NO embedded map -- removed)
  |
  +-- _updateMapFocus(plan, 'days')  // NEW
        |
        +-- find stops for day 5 via _findStopsForDay()
        +-- compute bounds for those stops
        +-- GoogleMaps.fitBounds(dayBounds)
        +-- show day's POI markers (activities, restaurants)
        +-- highlight day's stop markers, dim others
```

```
User clicks "back" or switches tab
  |
  v
navigateToStopsOverview() / switchGuideTab('overview')
  |
  +-- _activeStopId = null, _activeDayNum = null
  +-- _updateMapFocus(plan, tab)
        |
        +-- no active detail --> GoogleMaps.fitAllStops(plan)
        +-- restore all markers to full opacity
        +-- clear POI markers
```

### Map Focus Management (New Logic)

Add `_updateMapFocus(plan, tab)` to replace the current `_updateMapForTab()`:

```javascript
function _updateMapFocus(plan, tab) {
  if (typeof GoogleMaps === 'undefined' || !_guideMapInitialized) return;

  // Clear any day-specific POI markers
  _clearDayPOIMarkers();

  if (tab === 'stops' && _activeStopId !== null) {
    // STOP DETAIL: zoom to stop region
    const stop = (plan.stops || []).find(
      s => String(s.id) === String(_activeStopId)
    );
    if (stop && stop.lat && stop.lng) {
      const bounds = _computeStopBounds(stop);
      const map = GoogleMaps.getGuideMap();
      if (map) map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
      GoogleMaps.highlightGuideMarker(String(_activeStopId));
      _dimOtherMarkers(String(_activeStopId));
    }
    return;
  }

  if (tab === 'days' && _activeDayNum !== null) {
    // DAY DETAIL: fit to day's stops + show POI markers
    const dayStops = _findStopsForDay(plan, _activeDayNum);
    if (dayStops.length) {
      _fitMapToStops(dayStops);
      _showDayPOIMarkers(plan, _activeDayNum);
      const dayStopIds = dayStops.map(s => String(s.id));
      _dimMarkersExcept(dayStopIds);
    }
    return;
  }

  // DEFAULT: show full route
  GoogleMaps.fitAllStops(plan);
  _restoreAllMarkers();
}
```

### Marker Dimming Strategy

Use CSS classes on the marker overlay divs rather than recreating markers:

```javascript
function _dimOtherMarkers(activeStopId) {
  document.querySelectorAll('.guide-marker').forEach(el => {
    if (el.dataset.stopId === activeStopId) {
      el.classList.remove('dimmed');
      el.classList.add('focused');
    } else {
      el.classList.add('dimmed');
      el.classList.remove('focused');
    }
  });
}

function _dimMarkersExcept(activeStopIds) {
  document.querySelectorAll('.guide-marker').forEach(el => {
    if (activeStopIds.includes(el.dataset.stopId)) {
      el.classList.remove('dimmed');
    } else {
      el.classList.add('dimmed');
    }
  });
}

function _restoreAllMarkers() {
  document.querySelectorAll('.guide-marker').forEach(el => {
    el.classList.remove('dimmed', 'focused');
  });
}
```

```css
.guide-marker.dimmed {
  opacity: 0.35;
  transform: scale(0.8);
  transition: opacity 0.3s, transform 0.3s;
}
.guide-marker.focused {
  transform: scale(1.2);
  transition: transform 0.3s;
}
```

### Day POI Markers (Temporary Layer)

When viewing a day detail, overlay temporary markers for that day's activities/restaurants on the persistent map:

```javascript
let _dayPOIMarkersList = [];

async function _showDayPOIMarkers(plan, dayNum) {
  _clearDayPOIMarkers();
  const map = GoogleMaps.getGuideMap();
  if (!map) return;

  const dayStops = _findStopsForDay(plan, dayNum);
  const entities = [];
  dayStops.forEach(stop => {
    (stop.top_activities || []).forEach((act, i) => {
      entities.push({
        key: 'poi-act-' + stop.id + '-' + i,
        name: act.name, lat: act.lat, lng: act.lon,
        placeId: act.place_id,
        stopLat: stop.lat, stopLng: stop.lng,
        searchType: 'activity', type: 'activity'
      });
    });
    (stop.restaurants || []).forEach((r, i) => {
      entities.push({
        key: 'poi-rest-' + stop.id + '-' + i,
        name: r.name, placeId: r.place_id,
        stopLat: stop.lat, stopLng: stop.lng,
        searchType: 'restaurant', type: 'restaurant'
      });
    });
  });

  const coords = await GoogleMaps.resolveEntityCoordinates(entities);
  entities.forEach(ent => {
    const coord = coords.get(ent.key);
    if (!coord) return;
    const iconClass = ent.type === 'restaurant' ? 'restaurant' : 'activity';
    const marker = GoogleMaps.createDivMarker(map, coord,
      '<div class="poi-marker poi-marker--' + iconClass + '"></div>',
      null
    );
    _dayPOIMarkersList.push(marker);
  });
}

function _clearDayPOIMarkers() {
  _dayPOIMarkersList.forEach(m => { if (m) m.setMap(null); });
  _dayPOIMarkersList = [];
}
```

## Router URL Evolution

### Current Routes (no changes needed)

The existing URL patterns already support the drill-down model:

| URL Pattern | Handler | View |
|-------------|---------|------|
| `/travel/{id}` | `_travel` | Overview (default tab) |
| `/travel/{id}/stops` | `_travelTab('stops')` | Stops list |
| `/travel/{id}/stops/{stopId}` | `_travelStopDetail` | Stop detail |
| `/travel/{id}/days` | `_travelTab('days')` | Days timeline |
| `/travel/{id}/days/{dayNum}` | `_travelDayDetail` | Day detail |
| `/travel/{id}/calendar` | `_travelTab('calendar')` | Calendar |
| `/travel/{id}/budget` | `_travelTab('budget')` | Budget |

**Recommendation:** Keep all existing routes unchanged. The progressive disclosure is a rendering/map-focus concern, not a URL concern. The URLs already model the drill-down hierarchy correctly.

### Back Navigation

Browser back button already works because `navigateToStop()` / `navigateToDay()` call `Router.navigate()` with `skipDispatch: true`. When user presses back, the router dispatches the previous URL which triggers the correct handler.

**One fix needed:** `navigateToStopsOverview()` and `navigateToDaysOverview()` currently use `Router.navigate(base + '/stops', { skipDispatch: true })`. This means pressing back from stop detail goes to the page before the stops list, not to the stops list. Should change to `{ replace: true, skipDispatch: true }` so the back button correctly returns to the previous context.

## Patterns to Follow

### Pattern 1: Animate Map Transitions

Use Google Maps `panTo` + `fitBounds` with staged animations for smooth transitions:

```javascript
function _smoothZoomTo(map, targetBounds) {
  // First pan to center of target bounds
  const center = targetBounds.getCenter();
  map.panTo(center);
  // After pan completes, fit to bounds
  google.maps.event.addListenerOnce(map, 'idle', () => {
    map.fitBounds(targetBounds, { top: 40, right: 40, bottom: 40, left: 40 });
  });
}
```

**Why:** Abrupt zoom changes are disorienting. A pan-then-zoom sequence gives the user spatial context of where the detail fits within the overall route.

### Pattern 2: Bounds Computation for Stops

Compute intelligent bounds rather than using fixed zoom levels:

```javascript
function _computeStopBounds(stop) {
  const bounds = new google.maps.LatLngBounds();
  bounds.extend({ lat: stop.lat, lng: stop.lng });

  // Include activities with known coords
  (stop.top_activities || []).forEach(act => {
    if (act.lat && act.lon) bounds.extend({ lat: act.lat, lng: act.lon });
  });

  // If only the stop center (single point), add ~3km padding
  if (bounds.getNorthEast().equals(bounds.getSouthWest())) {
    const offset = 0.025; // ~2.5km
    bounds.extend({ lat: stop.lat + offset, lng: stop.lng + offset });
    bounds.extend({ lat: stop.lat - offset, lng: stop.lng - offset });
  }
  return bounds;
}

function _fitMapToStops(dayStops) {
  const map = GoogleMaps.getGuideMap();
  if (!map) return;
  const bounds = new google.maps.LatLngBounds();
  dayStops.forEach(s => {
    if (s.lat && s.lng) bounds.extend({ lat: s.lat, lng: s.lng });
  });
  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, { top: 50, right: 50, bottom: 50, left: 50 });
  }
}
```

**Why:** A city stop (Paris) needs wider zoom than a village. Using fitBounds with known POIs gives the right level automatically.

### Pattern 3: Breadcrumb for Drill-Down Context

When in a detail view, show a compact breadcrumb at the top of the content panel:

```javascript
function _renderDrilldownBreadcrumb(plan, tab) {
  if (tab === 'stops' && _activeStopId !== null) {
    const stop = (plan.stops || []).find(
      s => String(s.id) === String(_activeStopId)
    );
    return '<div class="drilldown-breadcrumb">'
      + '<button onclick="navigateToStopsOverview()" class="breadcrumb-back">'
      + 'Alle Stopps</button>'
      + '<span class="breadcrumb-sep">/</span>'
      + '<span class="breadcrumb-current">' + esc(stop?.region || '') + '</span>'
      + '</div>';
  }
  if (tab === 'days' && _activeDayNum !== null) {
    const dp = (plan.day_plans || []).find(d => d.day === _activeDayNum);
    return '<div class="drilldown-breadcrumb">'
      + '<button onclick="navigateToDaysOverview()" class="breadcrumb-back">'
      + 'Alle Tage</button>'
      + '<span class="breadcrumb-sep">/</span>'
      + '<span class="breadcrumb-current">Tag ' + _activeDayNum
      + ': ' + esc(dp?.title || '') + '</span>'
      + '</div>';
  }
  return '';
}
```

**Why:** User needs a way back and needs to know where they are in the hierarchy. The existing back button is inside the detail card, but a persistent breadcrumb above the content is more discoverable.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Embedded Maps in Detail Views

**What:** Creating `GoogleMaps.initStopOverviewMap()` inside `renderStopDetail()` and `renderDayDetail()`.
**Why bad:** Wastes Google Maps API quota (each map instance = API load), creates visual disconnect (two maps on screen), and the persistent map becomes useless during detail views.
**Instead:** Focus the persistent map on the detail's region. Remove embedded maps from detail renderers.

### Anti-Pattern 2: Zoom Level Hardcoding

**What:** Using fixed zoom levels like `setZoom(13)` for all stop details.
**Why bad:** A city stop (Paris) needs zoom 12, a small village needs zoom 15, a region with multiple POIs needs zoom 11.
**Instead:** Use `fitBounds()` with a bounds object computed from the stop's known POI coordinates (see Pattern 2).

### Anti-Pattern 3: Recreating All Markers on Focus Change

**What:** Calling `GoogleMaps.setGuideMarkers(plan)` every time the view changes.
**Why bad:** Destroys and recreates all OverlayView instances, causes visible flicker, loses polyline state.
**Instead:** Keep markers persistent. Use CSS classes (`.dimmed`, `.focused`) to change visual state without re-rendering.

### Anti-Pattern 4: Breaking Scroll Position on Tab Sub-Navigation

**What:** Scrolling `#guide-content` to top when navigating between stop details.
**Why bad:** If user is comparing stops, losing scroll position forces re-orientation.
**Instead:** Only scroll to top when entering a new context (list to detail). For prev/next within details, scroll to top of the detail card.

## Integration Points: New vs Modified

### New Code (~200 lines total)

| Component | Lines (est.) | Location |
|-----------|-------------|----------|
| `_updateMapFocus()` | ~40 | `guide.js` (replaces `_updateMapForTab`) |
| `_dimOtherMarkers()` / `_dimMarkersExcept()` / `_restoreAllMarkers()` | ~25 | `guide.js` |
| `_showDayPOIMarkers()` / `_clearDayPOIMarkers()` | ~50 | `guide.js` |
| `_computeStopBounds()` / `_fitMapToStops()` | ~25 | `guide.js` |
| `_smoothZoomTo()` | ~10 | `guide.js` |
| CSS marker states (`.dimmed`, `.focused`, `.poi-marker`) | ~40 | `styles.css` |

### Modified Code

| File | Function | Change |
|------|----------|--------|
| `guide.js` | `renderStopDetail()` | Remove embedded map div (the `<div class="stop-detail-map">` element) |
| `guide.js` | `renderDayDetail()` | Remove embedded map div (the `<div class="day-detail-map">` element) |
| `guide.js` | `renderGuide()` | Replace `_updateMapForTab(plan, activeTab)` call with `_updateMapFocus(plan, activeTab)` |
| `guide.js` | `_initStopMap()` | Delete entirely (no longer needed) |
| `guide.js` | `_initDayDetailMap()` | Delete entirely (no longer needed) |

### No Changes Needed

| Component | Why unchanged |
|-----------|---------------|
| `router.js` | URL patterns already model the drill-down hierarchy |
| `state.js` | Global `S` object already has `result` with all needed data |
| `api.js` | No new API calls needed |
| `sidebar.js` | Sidebar overlay already shows route context |
| `maps.js` | Existing API sufficient (`panToStop`, `fitAllStops`, `highlightGuideMarker`, `createDivMarker`) |
| Backend (all) | No data model changes; all coords/POIs already in response |

## Build Order (Dependency-Aware)

### Step 1: Map Focus Foundation

**Prerequisites:** None (independent of content changes)
**Deliverables:**
1. Implement `_updateMapFocus()` replacing `_updateMapForTab()`
2. Implement marker dimming functions
3. Add CSS for `.dimmed` / `.focused` marker states
4. Wire into existing `renderGuide()` call

**Verification:** Navigate to stop detail via URL `/travel/{id}/stops/{stopId}`, verify persistent map zooms to stop. Navigate to `/travel/{id}/stops`, verify map zooms out to full route.

### Step 2: Remove Embedded Maps

**Prerequisites:** Step 1 complete (persistent map now handles focus)
**Deliverables:**
1. Remove embedded map divs from `renderStopDetail()` output
2. Remove embedded map divs from `renderDayDetail()` output
3. Delete `_initStopMap()` and `_initDayDetailMap()` functions
4. Remove associated CSS for embedded map containers

**Verification:** Stop detail and day detail no longer render duplicate maps. The persistent map shows the correct region.

### Step 3: Day POI Markers

**Prerequisites:** Step 1 (map focus), Step 2 (no embedded map conflict)
**Deliverables:**
1. Implement `_showDayPOIMarkers()` / `_clearDayPOIMarkers()`
2. Add POI marker CSS (small colored dots for activities vs restaurants)
3. Wire into `_updateMapFocus()` day-detail branch

**Verification:** Navigate to day detail, verify activity/restaurant markers appear on persistent map alongside stop markers. Navigate away, verify POI markers are removed.

### Step 4: Smooth Transitions and Bounds

**Prerequisites:** Steps 1-3 working
**Deliverables:**
1. Implement `_computeStopBounds()` for intelligent zoom levels
2. Implement `_smoothZoomTo()` for animated transitions
3. Replace direct `fitBounds`/`panTo` calls with smooth versions

**Verification:** Transitions between overview and detail feel animated rather than jarring. Different stop sizes (city vs village) get appropriate zoom levels.

## Mobile Considerations

On mobile (< 768px), the map is a sticky 30vh strip at the top. The same focus management applies:
- Stop detail: map zooms to stop, 30vh is enough to show the region
- Day detail: map shows day's stops, POI markers visible
- Scroll sync still works (cards scroll below sticky map)

No layout changes needed for mobile -- the existing responsive breakpoints handle the split-panel to stacked transition. The focus management logic is viewport-independent.

## Sources

- Codebase analysis: `frontend/js/guide.js` (3007 lines) -- tab rendering, navigation, map setup, stop/day detail
- Codebase analysis: `frontend/js/maps.js` (791 lines) -- GoogleMaps singleton, marker management, polyline rendering
- Codebase analysis: `frontend/js/router.js` (343 lines) -- URL patterns, dispatch handlers
- Codebase analysis: `frontend/styles.css` (layout rules at lines 1596-1662) -- split panel, responsive breakpoints
- Codebase analysis: `frontend/index.html` (lines 528-570) -- HTML structure for travel guide section
- Codebase analysis: `backend/models/travel_response.py` -- TravelStop, DayPlan, TravelPlan data models
