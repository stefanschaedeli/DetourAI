# frontend/js/guide/CLAUDE.md

Travel guide viewer — tab-based, lazy-loaded, SSE-driven editing.
Do NOT modify backend/, infra/, core/, maps/, communication/, or features/.

## Files

| File | Responsibility |
|------|---------------|
| `guide-core.js` | Entry point — `showTravelGuide()`, tab routing, crossfade transitions, stats bar |
| `guide-overview.js` | Overview tab — trip analysis prose, activities, budget breakdown |
| `guide-stops.js` | Stop cards — flag/drive info/nights, stop detail view, lazy image loading |
| `guide-days.js` | Day-by-day itinerary — day overview, detail, calendar, time blocks |
| `guide-map.js` | Map tab — delegates to `GoogleMaps`, scroll sync, marker clicks |
| `guide-edit.js` | Editing — add/remove/reorder/replace stops, drag-and-drop, SSE handlers |
| `guide-share.js` | Share toggle UI, link copy |

## Architecture

- All files read from `S.result` (TravelPlan object) — never mutate it directly
- Tabs: overview / stops / days / calendar / budget / map
- `guide-core.js` is the entry point; other files are registered as tab renderers
- Header comments declare `// Reads:` and `// Provides:` as manual dependency contracts

## Crossfade & Navigation

- `switchGuideTab(tab)` in `guide-core.js` handles tab transitions with crossfade guards
- `_drillTransitionTimer` prevents rapid consecutive tab switches
- `navigateToStop(stopId)` and `navigateToDay(dayIdx)` handle drill-down views
- Breadcrumb delegation: guide-stops and guide-days call back to guide-core

## Editing (guide-edit.js)

- Edit-lock pattern: `_editInProgress` flag prevents concurrent operations
- SSE-driven: replace/add operations stream results via `window.addEventListener('sse:*')`
- Drag-and-drop reorder via HTML5 drag events
- Uses `openSSE()` shim from `core/api.js` for edit operations

## Lazy Loading

- Images lazy-loaded in overview, stops, and map tabs
- `IntersectionObserver` used for viewport-based loading triggers
- Photo data fetched via `GoogleMaps.getPlaceImages()` from `maps/`
