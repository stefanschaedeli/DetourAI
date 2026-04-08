# Frontend Agentic Split — Design Spec
**Date:** 2026-04-08
**Status:** Approved

## Goal

Refactor the frontend JS layer so each file has a single, clearly bounded concern that a dedicated agent (or human) can own, read, and modify without needing context from unrelated files. No build step, no framework, no import/export — plain `<script>` globals throughout.

---

## Approach: Incremental by layer (3 phases)

Each phase is independently deployable. After each phase the app runs normally. Rollback = `git revert` of that phase's commit.

---

## Phase 1 — Maps split

Split `maps.js` (845 lines, 4 concerns) into 4 focused files.

### New files

| File | Responsibility | ~Lines |
|------|---------------|--------|
| `maps-core.js` | `GoogleMaps` object init, map instance creation (`initRouteMap`, `initGuideMap`, `initPersistentGuideMap`, `initStopOverviewMap`), `createDivMarker`, `createPlaceMarker`, `attachAutocomplete`, `resolveEntityCoordinates`, `_onApiReady`, `_setApiKey`, `_log` | ~300 |
| `maps-images.js` | `getPlaceImages()` and all photo-fetching tiers (Place ID, nearby search, text search, static map, SVG placeholder), `_imageCache` | ~180 |
| `maps-routes.js` | `renderDrivingRoute()`, `_renderSingleRoute`, `_renderBatchedRoute`, `_straightLineFallback` | ~120 |
| `maps-guide.js` | Persistent guide map state (`_guideMarkerList`, `_guidePolylineRef`), `setGuideMarkers`, `highlightGuideMarker`, `panToStop`, `fitAllStops`, `fitDayStops`, `dimNonFocusedMarkers`, `restoreAllMarkers`, `clearGuideMarkers`, `enableClickToAdd`, `getGuideMap` | ~220 |

### Extension pattern

`maps-core.js` defines and initializes `GoogleMaps = (() => { ... })()` with core methods plus empty stubs for the shared caches:

```js
// maps-core.js (excerpt)
const GoogleMaps = (() => {
  // Shared state — accessed by maps-images.js, maps-guide.js via closure
  // NOT possible across files in global scope, so use window-level references:
  window._mapsImageCache  = new Map();
  window._mapsCoordCache  = new Map();
  window._mapsGuideMarkers = [];
  window._mapsGuidePolyline = null;
  ...
  return { _onApiReady, _setApiKey, initRouteMap, ... };
})();
```

Each subsequent file extends `GoogleMaps` with `Object.assign`:

```js
// maps-images.js (excerpt)
Object.assign(GoogleMaps, (() => {
  function getPlaceImages(...) { /* uses window._mapsImageCache */ }
  return { getPlaceImages };
})());
```

This means partial load (script error) leaves `GoogleMaps` degraded but not crashing — callers that check `GoogleMaps.getPlaceImages` will get `undefined` rather than a thrown reference error.

### Shared state

| Variable | Declared in | Used in |
|----------|------------|---------|
| `window._mapsImageCache` | `maps-core.js` | `maps-images.js` |
| `window._mapsCoordCache` | `maps-core.js` | `maps-core.js` (`resolveEntityCoordinates`) |
| `window._mapsGuideMarkers` | `maps-core.js` | `maps-guide.js` |
| `window._mapsGuidePolyline` | `maps-core.js` | `maps-guide.js` |
| `_apiKey` | `maps-core.js` closure | `maps-images.js` via `GoogleMaps._getApiKey()` — `maps-core.js` must expose `_getApiKey() { return _apiKey; }` in its returned object |

### Deletion

`maps.js` is deleted after Phase 1. `index.html` replaces its single `<script>` with 4 ordered scripts.

---

## Phase 2 — SSE / comms layer

Extract the SSE wire protocol from `api.js` into a dedicated `sse-client.js`.

### New file: `sse-client.js`

**Responsibility:** EventSource lifecycle, auth token injection, raw event parsing, re-dispatch as DOM CustomEvents.

**Public API:**
```js
SSEClient.open(jobId)   // creates EventSource, wires all known events
SSEClient.close()       // closes active EventSource
```

**Event contract:** For every SSE event name `X`, fires:
```js
window.dispatchEvent(new CustomEvent('sse:X', { detail: parsedData }))
```

Known events wired:
`debug_log`, `route_ready`, `stop_done`, `agent_start`, `agent_done`,
`job_complete`, `job_error`, `accommodation_loading`, `accommodation_loaded`,
`accommodations_all_loaded`, `stop_research_started`, `activities_loaded`,
`restaurants_loaded`, `route_option_ready`, `route_options_done`, `ping`,
`region_plan_ready`, `region_updated`, `leg_complete`,
`replace_stop_progress`, `replace_stop_complete`,
`remove_stop_progress`, `remove_stop_complete`,
`add_stop_progress`, `add_stop_complete`,
`reorder_stops_progress`, `reorder_stops_complete`,
`update_nights_progress`, `update_nights_complete`,
`style_mismatch_warning`, `ferry_detected`

**Error handling:** `source.onerror` fires `window.dispatchEvent(new CustomEvent('sse:error'))`.

### Changes to `api.js`

`openSSE(jobId, handlers)` becomes a backward-compat shim:

```js
function openSSE(jobId, handlers) {
  // Subscribe handlers to window CustomEvents
  Object.keys(handlers).forEach(evt => {
    if (evt === 'onerror') {
      window.addEventListener('sse:error', handlers.onerror, { once: true });
    } else {
      window.addEventListener('sse:' + evt, e => handlers[evt](e.detail), { once: false });
    }
  });
  SSEClient.open(jobId);
  // Return object with .close() for callers that call source.close()
  return { close() { SSEClient.close(); } };
}
```

This means **zero changes** to `progress.js`, `route-builder.js`, or any other existing caller of `openSSE()`.

### Subscriber pattern (new code going forward)

New files subscribe directly to window events instead of passing handlers to `openSSE`:
```js
window.addEventListener('sse:stop_done', e => { /* e.detail = parsed data */ });
```

---

## Phase 3 — `progress.js` split

`progress.js` currently mixes SSE wire-handling with UI rendering. After Phase 2, subscriptions are already via window events. Phase 3 makes the split explicit.

### Split

| File | Responsibility |
|------|---------------|
| `progress.js` | **UI only**: stop card rendering, timeline row management, overlay line updates (calls `progressOverlay.*`), route-builder UI reactions |
| (no new file) | SSE subscriptions stay in `progress.js` but are now explicit `window.addEventListener('sse:X', ...)` calls at the bottom, clearly separated from rendering functions by a `// --- SSE subscriptions ---` section comment |

This is the lightest-touch option: the file gets significantly cleaner without introducing a new file that would need its own CLAUDE.md entry.

---

## Load order in `index.html`

```
state.js
i18n.js
api.js
sse-client.js          ← NEW (Phase 2)
auth.js
loading.js
sse-overlay.js
maps-core.js           ← NEW (Phase 1, replaces maps.js)
maps-images.js         ← NEW (Phase 1)
maps-routes.js         ← NEW (Phase 1)
maps-guide.js          ← NEW (Phase 1)
form.js
route-builder.js
accommodation.js
progress.js
guide-core.js
guide-days.js
guide-edit.js
guide-map.js
guide-overview.js
guide-stops.js
guide-share.js
sidebar.js
router.js
settings.js
travels.js
feedback.js
```

---

## Module ownership map (for CLAUDE.md)

| File(s) | Owner concern | Agent can touch |
|---------|--------------|-----------------|
| `api.js` | HTTP fetch wrappers, all `apiXxx()` functions | Backend API contract changes |
| `sse-client.js` | SSE wire protocol, EventSource lifecycle | New SSE event types |
| `sse-overlay.js` | Overlay component DOM | Overlay UI changes |
| `maps-core.js` | Map init, markers, autocomplete | Core map setup |
| `maps-images.js` | Photo fetching, image cache | Photo quality, fallback tiers |
| `maps-routes.js` | Driving route rendering | Route display, polyline style |
| `maps-guide.js` | Guide map state, markers, ferry lines | Guide map interactions |
| `progress.js` | Planning progress UI (stop cards, timeline) | Progress rendering |

---

## Testing per phase

Each phase ends with:
1. Manual smoke: start a job → watch SSE overlay → open guide → verify map renders + photos load
2. `cd backend && python3 -m pytest tests/ -v` — backend unchanged, confirms no API regressions
3. `git add → git commit → git tag vX.X.Y → git push && git push --tags`

---

## Out of scope

- `guide-*.js` files — already well-split, no changes needed
- `state.js`, `form.js`, `auth.js`, `router.js` — single-concern already
- Backend — zero changes
- CSS / `styles.css` — no changes
- i18n files — no changes
- Build tooling — no build step introduced
