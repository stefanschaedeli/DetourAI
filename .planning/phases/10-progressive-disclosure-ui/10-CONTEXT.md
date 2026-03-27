# Phase 10: Progressive Disclosure UI - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Three-level drill-down navigation for the travel view: overview (compact day cards + trip summary), day detail (day's stops/activities/restaurants with map focused on region), and stop detail (accommodation/activities/restaurants with map focused on stop area). Persistent map responds to navigation context with smooth animations. Breadcrumb bar provides back-navigation at each level. Browser back/forward works via URL routing.

</domain>

<decisions>
## Implementation Decisions

### Overview Landing
- **D-01:** Overview shows a compact trip summary header (title, dates, travelers, budget) followed by a grid of clickable day cards. Each day card shows: day number, title/region, stop count, drive time, and a small thumbnail image (first stop's photo).
- **D-02:** Existing overview content (trip analysis, budget breakdown, travel guide prose) moves to a collapsible section below the day cards grid, collapsed by default. User can expand without drilling into a day.

### Drill-Down Transitions
- **D-03:** Crossfade transition between drill-down levels. Current content fades out, new content fades in. CSS transitions with JS coordination.
- **D-04:** Content panel scrolls to top on every drill-down and back-navigation.
- **D-05:** Map uses smooth pan+zoom (Google Maps panTo/fitBounds) when changing drill-down context. Map animates independently of content crossfade.

### Breadcrumb & Back-Navigation
- **D-06:** Unified breadcrumb bar above content at all drill levels. Format: `Uebersicht > Tag 3 > Annecy`. Each segment is clickable for direct navigation to that level. Hidden (or just static title) at overview level.
- **D-07:** Browser back/forward buttons work with drill-down via URL routing. Each drill-down pushes a URL segment (e.g., `/travel/42/day/3`, `/travel/42/stop/5`). Existing router.js patterns extended with day/stop segments.

### Map Focus (not discussed — Claude's discretion)
- **D-08:** At overview level, all stops shown on map with full visibility and route polyline.
- **D-09:** At day level, map zooms to that day's region. Non-focused stops appear dimmed (reduced opacity). Day's polyline segment highlighted.
- **D-10:** At stop level, map pans and zooms to stop area. Non-focused stops dimmed further or hidden.
- **D-11:** On back-navigation to overview, all markers return to full visibility and map re-fits to full route.

### Claude's Discretion
- Crossfade timing and easing (CSS transition duration/curve)
- Day card grid layout details (columns, gap, responsive breakpoints)
- Thumbnail image sizing and fallback for stops without photos
- Marker dimming approach (opacity, grayscale, or size reduction)
- Collapsible section toggle design (accordion, chevron, etc.)
- How editing UI integrates at each drill level (guide-edit.js handlers)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Frontend — Guide Modules (Phase 9 output)
- `frontend/js/guide-core.js` — Entry point, tab switching, `renderGuide()`, state vars (`activeTab`, `_activeStopId`, `_activeDayNum`)
- `frontend/js/guide-overview.js` — `renderOverview()` with trip analysis, budget, prose (to be restructured)
- `frontend/js/guide-stops.js` — `renderStopsOverview()`, `renderStopDetail()`, `navigateToStop()`, existing breadcrumb span
- `frontend/js/guide-days.js` — `renderDaysOverview()`, `renderDayDetail()`, `navigateToDay()`, existing breadcrumb span
- `frontend/js/guide-map.js` — `_updateMapForTab()`, marker management, scroll sync
- `frontend/js/guide-edit.js` — Route editing + SSE handlers (must work at all drill levels)
- `frontend/js/guide-share.js` — Share toggle (must remain accessible)

### Frontend — Routing & State
- `frontend/js/router.js` — Client-side routing with `/travel/{id}` patterns (extend with `/day/{n}`, `/stop/{id}`)
- `frontend/js/state.js` — Global `S` object, `TRAVEL_STYLES`, `FLAGS`
- `frontend/js/maps.js` — `GoogleMaps` namespace, marker creation, guide map state

### Frontend — Styling
- `frontend/styles.css` — All CSS (crossfade transitions, breadcrumb bar, day card grid go here)
- `DESIGN_GUIDELINE.md` — Apple-inspired design system

### Planning
- `.planning/REQUIREMENTS.md` — NAV-01 through NAV-06 definitions
- `.planning/ROADMAP.md` — Phase 10 success criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `navigateToStop(stopId)`, `navigateToDay(dayNum)` — already exist in guide-stops.js and guide-days.js, can be extended for URL-push behavior
- `renderStopDetail(plan, stopId)`, `renderDayDetail(plan, dayNum)` — existing detail renderers, usable as drill-down targets
- `_activeStopId`, `_activeDayNum` in guide-core.js — already track current drill context
- `_updateMapForTab()` in guide-map.js — existing map focus logic, extend for drill-down levels
- Breadcrumb spans already exist in guide-days.js (line 357) and guide-stops.js (line 161)
- `renderStatsBar(plan)` in guide-core.js — stats bar already visible on all tabs (Phase 8)

### Established Patterns
- Flat globals with cross-module function calls (Phase 9 D-07)
- Tab switching via `switchGuideTab()` in guide-core.js updates URL via `Router.navigate()`
- All route edit SSE handlers follow `*_complete` → update `S.result` → `renderGuide(data, tab)` pattern
- Google Maps panTo/fitBounds already used in maps.js for marker navigation

### Integration Points
- `guide-core.js` `renderGuide()` — central dispatch, needs drill-down level awareness
- `router.js` — needs new route patterns: `/travel/{id}/day/{n}`, `/travel/{id}/stop/{id}`
- `guide-overview.js` `renderOverview()` — restructure to day-cards + collapsible details
- `guide-map.js` `_updateMapForTab()` — extend for per-day and per-stop map focus with dimming
- `frontend/index.html` — no script tag changes needed (modules already loaded)

</code_context>

<specifics>
## Specific Ideas

- Compact day cards with thumbnails chosen over text-only for visual richness
- Collapsible details section chosen over moving content to drill-down — keeps trip analysis accessible at overview level without extra clicks
- Crossfade chosen over instant swap — user wanted polished transitions
- Unified breadcrumb bar chosen over inline breadcrumbs — consistent navigation pattern across all levels

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-progressive-disclosure-ui*
*Context gathered: 2026-03-27*
