# Project Research Summary

**Project:** Travelman3 — v1.1 Progressive Disclosure Travel View Redesign
**Domain:** Vanilla JS SPA progressive disclosure UI retrofit with map focus management
**Researched:** 2026-03-27
**Confidence:** HIGH

## Executive Summary

The v1.1 milestone is a frontend-only redesign that replaces the flat 5-tab travel guide with a 3-level progressive disclosure navigation (Overview -> Day -> Stop). Research confirms the entire redesign is achievable with zero new dependencies: all needed browser APIs are already available (View Transitions API, CSS `grid-template-rows` animation, IntersectionObserver), Google Maps raster API already animates `panTo()`/`fitBounds()` smoothly, and the URL routing structure already models the drill-down hierarchy correctly. The work is extension and refinement of what exists, not a rewrite.

The recommended approach requires a strict 4-phase ordering driven by two critical discoveries. First, `guide.js` at 3007 lines mixes rendering, map setup, editing, SSE handlers, and navigation state — adding a third navigation depth to this monolith without first splitting it creates ungovernable complexity. Second, three production bugs (missing Celery task registration, map markers not refreshing after edits, stale stats bar) must be fixed against the current UI before the redesign begins: mixing repairs with redesign makes regressions impossible to isolate. The correct order is: fix tech debt -> split guide.js into modules -> implement progressive disclosure -> verify pending UI items against the new view.

The central architectural risk is the existing map system having three competing auto-movement mechanisms (IntersectionObserver scroll-sync, marker-click scroll, and `_updateMapForTab` which unconditionally calls `fitAllStops()`). Adding drill-down map focus as a fourth mechanism without a `_mapFocusMode` state machine will cause the map to fight itself — the user drills into Day 3 and scroll-sync immediately snaps the map to a different stop. This state machine must be the first thing built in the progressive disclosure phase: replace `_updateMapForTab()` with a focus-mode-aware `_updateMapFocus()` that suppresses scroll-sync when a day or stop is the active focus.

## Key Findings

### Recommended Stack

No new libraries are required. The redesign uses exclusively what is already in the codebase and the browser. Adding any external library (animation library, virtual scroll, carousel) would violate the no-framework constraint and add maintenance burden to a vanilla JS project with no build step.

The only "new" techniques are native browser APIs available in all major browsers as of 2026: `document.startViewTransition()` (Chrome 111+, Firefox 133+, Safari 18+) for smooth cross-level transitions with graceful fallback to the existing instant swap; and CSS `grid-template-rows: 0fr/1fr` transition (Chrome 117+, Firefox 117+, Safari 17.2+) for expand/collapse animations without height measurement. Both degrade gracefully to current behavior if unsupported — no polyfill needed.

**Core technologies (extend, do not replace):**
- Google Maps JS SDK (raster): `panTo()` + `fitBounds()` — already animate smoothly; no vector map migration needed
- `document.startViewTransition()`: smooth cross-fade between drill-down levels — degrades to current instant swap
- CSS `grid-template-rows: 0fr/1fr` transition: expand/collapse cards without height measurement — cross-browser primary pattern
- IntersectionObserver: lazy rendering of off-screen day/stop cards — already in codebase, extend existing usage
- Module-scoped state: `_drillLevel` (new) + `_activeDayNum` + `_activeStopId` (existing) — three variables handle all navigation state

**Explicitly rejected (with rationale):**
- GSAP / anime.js — CSS handles the needed effects natively; 15-50KB for zero gain
- Virtual scroll — max 15 stops, max 14 days; DOM never exceeds ~200 elements
- Google Maps vector migration — requires `mapId` + Cloud Console config + AdvancedMarkerElement rewrite of 600+ lines of maps.js for marginal visual improvement
- `interpolate-size: allow-keywords` as primary — Chromium-only as of 2026; use `grid-template-rows` as the cross-browser primary

See `.planning/research/STACK.md` for full rationale and version compatibility table.

### Expected Features

Based on competitive analysis (Wanderlog, Google Travel, Apple Maps) and Nielsen Norman Group progressive disclosure standards.

**Must have (table stakes):**
- Overview with all stops on map + compact clickable day cards — entry point to day drill-down
- Day drill-down with `fitBoundsForDay()` map zoom — users expect the map to scope to the selected day
- Stop drill-down with `panToStop()` + zoom — map must center on stop when viewing stop detail
- Breadcrumb navigation (Uebersicht > Tag 3 > Annecy) — users must know where they are and how to get back
- Browser history support across drill-down levels — back button must go up one level, not leave the page
- Animated map transitions between views — jarring jumps feel broken; `panTo()` + `fitBounds()` handle this natively

**Should have (competitive differentiators):**
- Contextual marker styling — day's stops are full-size/colored, others are small/dimmed (Wanderlog/Airbnb pattern)
- Day-scoped route polyline highlighting — dim full route, highlight current day's segment
- Smart map padding for content panel overlap — `fitBounds` padding adjusted for panel width
- Keyboard navigation between days/stops — j/k keys, good for accessibility and power users

**Defer (v2+):**
- Stop-to-stop route animation along polyline — high complexity (manual `panTo` steps along decoded polyline), low user value
- Day weather/drive summary badges on compact cards — needs additional weather data pipeline work
- 3D map fly-through — anti-feature (disorienting, slow, can't skip)

**Anti-features (explicitly do not build):**
- Collapsible map panel — map is always visible, it is the core value
- Nested tabs within drill-down levels — cognitive overload; use flat content sections per level
- Automatic drill-down on page load — always start at overview; let user choose where to drill
- Full page reload for stop/day navigation — kills fluidity; all drill-down stays in the split-panel layout

See `.planning/research/FEATURES.md` for full specification including per-level map behavior and competitive pattern analysis.

### Architecture Approach

The key architectural insight is that stop detail and day detail currently create **independent mini-maps inside the content panel**, making the persistent split-panel map useless when viewing detail views. The redesign eliminates these embedded maps and makes the persistent map context-aware: its zoom and bounds respond to the current drill-down level. This is the "Map as Primary Navigation Surface" principle — it eliminates redundant Google Maps API quota usage and makes the split-panel layout feel intentional rather than vestigial.

The URL routing structure already models the drill-down hierarchy correctly (`/travel/{id}/stops/{stopId}`, `/travel/{id}/days/{dayNum}`). No new routes are needed for the core drill-down. The one issue identified is that `navigateToStopsOverview()` / `navigateToDaysOverview()` use `Router.navigate()` without `replace: true`, so the browser back button skips the list view. One-line fix.

**Major components and their changes:**
1. `guide-core.js` (split from guide.js) — `renderGuide()`, tab switching, view state, shared variables; houses `_activeStopId`, `_activeDayNum`, `_editInProgress`
2. `guide-map-sync.js` (new module from guide.js) — `_updateMapFocus()` replacing `_updateMapForTab()`; `_mapFocusMode` state machine; marker dimming CSS classes; scroll-sync suppression; day POI marker layer
3. `guide-stops.js`, `guide-days.js`, `guide-overview.js` (split from guide.js) — rendering functions only, no direct map calls
4. `maps.js` (minor) — add `fitBoundsForStops(stopIds)` helper; add optional zoom param to `panToStop()`
5. `router.js` (one line) — change overview navigation calls to use `{ replace: true }`

Total new code: approximately 200 lines. Zero backend changes. Zero new API calls.

See `.planning/research/ARCHITECTURE.md` for full data flow diagrams, map focus management code, marker dimming implementation, and build order.

### Critical Pitfalls

1. **Map focus fighting existing scroll-sync** — Three auto-movement systems already compete. Adding drill-down focus without `_mapFocusMode` causes the map to snap away from drill-down context immediately. Introduce `_mapFocusMode: 'all' | 'day' | 'stop'`; suppress scroll-sync when mode is not `'all'`; respect `_userInteractingWithMap` flag in all automated focus changes.

2. **guide.js 3007-line monolith** — Navigation state, rendering, map setup, editing, and SSE handlers are all interleaved. Adding a third depth level before splitting creates bugs where `_activeStopId` is set but `_activeDayNum` is stale, and `_editInProgress` interacts with navigation state unpredictably. Split into 5 focused modules with zero behavioral changes before any progressive disclosure code.

3. **Mixing tech debt fixes with UI redesign** — Bug fixes for Celery include list, marker refresh, and stats bar are surgical and testable against the current UI. Doing them during the redesign makes it impossible to isolate whether a regression was caused by the fix or the redesign. Strict phase ordering: fix first, tag a release, then redesign.

4. **Full DOM rebuild on every navigation** — `renderGuide()` does 45 content replacements. Progressive disclosure means users traverse depth rapidly (click day, click stop, back, click another stop). Each rebuild kills IntersectionObservers, scroll positions, image lazy-load state. Use CSS show/hide toggling on pre-rendered sections for drill-down transitions; reserve full innerHTML replacement for when data actually changes.

5. **URL routing collision between two paths to the same stop** — `/travel/{id}/stops/{stopId}` and a future `/travel/{id}/days/{n}/stops/{id}` both render stop detail with different back-navigation behavior. Use URL path to encode context; derive back-navigation from URL structure, not module-level state. The existing router already handles this pattern — extend it rather than working around it.

See `.planning/research/PITFALLS.md` for all 13 pitfalls with detection signs and phase-specific warnings.

## Implications for Roadmap

Research strongly dictates 4 phases in strict dependency order. Phases 1 and 2 are foundations, not features.

### Phase 1: Tech Debt Stabilization

**Rationale:** Three production bugs must be fixed against the existing UI so regressions are detectable. Pitfall 3 is the explicit research warning: mixing fixes with redesign makes root-cause analysis impossible. All three fixes are small and have exact root causes identified.
**Delivers:** Stable codebase — stop replacement working in Docker, markers refreshing after edits, stats bar always current.
**Addresses:** No user-facing features, but establishes the clean baseline all subsequent phases depend on.
**Specific tasks:**
- Add `"tasks.replace_stop_job"` to Celery include list in `backend/tasks/__init__.py` (5-minute fix, test in Docker)
- Add `_refreshMapAfterEdit(plan)` calling `setGuideMarkers` + `fitAllStops`; wire to all edit completion handlers
- Move stats bar re-render outside the `activeTab === 'overview'` conditional in `renderGuide()`
**Avoids:** Pitfall 7 (Celery NotRegistered in Docker), Pitfall 6 (stale markers after edits), Pitfall 8 (stale stats bar)

### Phase 2: guide.js Module Split

**Rationale:** guide.js at 3007 lines with all concerns interleaved is ungovernable for progressive disclosure work (Pitfall 2). Splitting now, with zero behavioral changes, creates clean module boundaries for Phase 3. The split must come before any navigation logic changes or the two work streams produce unresolvable conflicts.
**Delivers:** `guide-core.js`, `guide-overview.js`, `guide-stops.js`, `guide-days.js`, `guide-map-sync.js` — all existing behavior preserved, all global function names kept.
**Key constraint:** Shared state (`_activeStopId`, `_activeDayNum`, `_editInProgress`) must live in `guide-core.js` or be promoted to `S` object. Document module dependency graph in each file header to prevent load-order failures (Pitfall 13).
**Avoids:** Pitfall 2 (monolith ungovernable), Pitfall 13 (module load order in index.html)

### Phase 3: Progressive Disclosure UI

**Rationale:** With stable code and clean module boundaries, implement the drill-down navigation. Within this phase, map focus management must come first — the existing `_updateMapForTab()` unconditionally calls `fitAllStops()` and would override any drill-down focus set by content renders. Build the infrastructure, then hook content renders into it.
**Delivers:** Full 3-level navigation (Overview -> Day -> Stop), persistent map as primary navigation surface, animated transitions, breadcrumb navigation, deep-linkable URLs, contextual marker styling, compact day cards on overview.
**Uses:** `document.startViewTransition()` with instant-swap fallback, CSS `grid-template-rows` expand/collapse, Google Maps staged `panTo()`+`fitBounds()` animation, IntersectionObserver lazy rendering.
**Build order within phase (dependency-driven):**
1. `_mapFocusMode` state machine + `_updateMapFocus()` + marker dimming CSS (foundation — everything else hooks into this)
2. Remove embedded mini-maps from `renderStopDetail()` and `renderDayDetail()` (prerequisite for step 3)
3. Day POI marker layer on persistent map
4. Compact day cards on overview + `fitBoundsForDay()` map helper
5. Breadcrumb component across all 3 levels
6. Router: add day-context stop route + fix `replace: true` for overview back navigation
7. CSS transitions: View Transition API + grid expand/collapse + drill-down animation classes
**Avoids:** Pitfall 1 (DOM rebuild — use show/hide for drill-down), Pitfall 4 (map fighting scroll-sync — `_mapFocusMode` suppresses it), Pitfall 5 (URL routing collision), Pitfall 9 (event delegation with nested cards — use `data-action` attributes), Pitfall 10 (layout shift on compact cards — fixed-height containers), Pitfall 12 (fitBounds over-zoom on single point — `setCenter()`+`setZoom(13)` for single stops)

### Phase 4: Browser Verification and Polish

**Rationale:** The milestone has 9 pending UI verification items. Pitfall 3 phase-warning: these must be verified against the NEW progressive disclosure view, not the old tab view. Keyboard navigation and smart map padding are polish items that fit naturally at this stage.
**Delivers:** All 9 pending UI items verified against new view, keyboard navigation (j/k between days/stops), smart map padding accounting for content panel width, CSS transition conflict resolution.
**Avoids:** Pitfall 11 (CSS transition conflicts between tab-switch fade and drill-down slide — distinguish the two, cancel previous before starting new)

### Phase Ordering Rationale

- Phase 1 before everything: regressions caused by the redesign are invisible if tech debt fixes are mixed in. The three bugs are also production issues worth fixing immediately regardless of the redesign.
- Phase 2 before Phase 3: adding progressive disclosure to the monolith creates untraceable state bugs. The split is structural, low-risk, and sets up Phase 3 for clean parallel work on map focus vs. content rendering.
- Within Phase 3: `_mapFocusMode` state machine must precede all content changes because `_updateMapForTab()` unconditionally calls `fitAllStops()` on every render — any content change that calls `renderGuide()` will override drill-down focus until the state machine is in place.
- Phase 4 last: verifying UI items requires the final layout to be stable; doing it earlier would require re-verification after layout changes.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3, step 3 (Day POI Markers):** The architecture references `GoogleMaps.resolveEntityCoordinates()` — verify this method exists in `maps.js` or budget time to build it before implementing POI markers.
- **Phase 3, step 6 (Router):** The day-context stop URL pattern (`/days/{n}/stops/{id}` vs. query param) needs a decision before implementation. The nested path is cleaner for browser history but adds a router pattern; query params avoid URL complexity but lose deep-linkability.

Phases with standard patterns (skip additional research):
- **Phase 1 (Tech debt):** All three fixes have exact root causes identified with line-level citations. No additional research needed.
- **Phase 2 (Module split):** Pure refactor, no new logic. Standard module extraction pattern with documented dependency graph.
- **Phase 3, steps 1-2 (Map focus foundation + remove embedded maps):** Architecture document provides complete implementation code.
- **Phase 3, steps 4-5 (Compact cards + breadcrumb):** Data is already available in the response model; straightforward render function work.
- **Phase 4 (Keyboard nav):** Simple `keydown` listener, well-documented pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Based on direct codebase verification of existing patterns + MDN/Can I Use browser support data. Zero external libraries means zero integration uncertainty. |
| Features | HIGH | Based on NNG progressive disclosure standards + direct competitive analysis of Wanderlog/Google Travel. Feature list derived from existing code capabilities already verified to work. |
| Architecture | HIGH | Based on direct codebase analysis of guide.js (3007 lines), maps.js (791 lines), router.js (343 lines). All component boundaries and code patterns verified against actual files with line citations. |
| Pitfalls | HIGH | All 5 critical pitfalls identified through direct codebase analysis with line-level evidence (not speculation). Root causes and fixes confirmed against actual code. |

**Overall confidence:** HIGH

### Gaps to Address

- **`GoogleMaps.resolveEntityCoordinates()` existence:** Day POI markers architecture assumes this method in `maps.js`. Verify before Phase 3 step 3, or budget time to build it as part of that step.
- **`_findStopsForDay()` visibility after module split:** Architecture assumes this function is callable from `guide-map-sync.js` after the Phase 2 split. Confirm it will live in `guide-core.js` as a shared utility during the split planning.
- **Compact day card visual design:** The content to show on compact overview day cards (day number, location names, drive time, stop count) is not specified in DESIGN_GUIDELINE.md. Requires a design decision before Phase 3 step 4.
- **Day-context URL structure:** `/travel/{id}/days/{n}/stops/{id}` (nested, deep-linkable) vs. query params (`?context=day&day=3`) for stop-within-day context. Both work. Decide before Phase 3 step 6 to avoid mid-implementation direction change.

## Sources

### Primary (HIGH confidence)
- Direct codebase: `frontend/js/guide.js` (3007 lines) — tab/detail rendering, navigation, map setup, edit handlers, 45 DOM content replacement calls
- Direct codebase: `frontend/js/maps.js` (791 lines) — GoogleMaps singleton, `panToStop()`, `fitAllStops()`, `setGuideMarkers()`, marker OverlayView pattern
- Direct codebase: `frontend/js/router.js` (343 lines) — URL patterns, dispatch handlers, existing travel/stops/days routes
- Direct codebase: `backend/tasks/__init__.py` — confirmed `replace_stop_job` missing from Celery include list
- [MDN: View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API) — same-document API spec and browser support matrix
- [Can I Use: View Transitions (single-document)](https://caniuse.com/view-transitions) — Chrome 111+, Safari 18+, Firefox 133+ confirmed
- [Chrome Developers: Animate to height auto](https://developer.chrome.com/docs/css-ui/animate-to-height-auto) — `interpolate-size` Chromium-only status
- [CSS-Tricks: Performant Expandable Animations](https://css-tricks.com/performant-expandable-animations-building-keyframes-on-the-fly/) — `grid-template-rows` cross-browser pattern

### Secondary (MEDIUM confidence)
- [Progressive Disclosure — Nielsen Norman Group](https://www.nngroup.com/articles/progressive-disclosure/) — hierarchy navigation standards
- [Wanderlog help docs](https://help.wanderlog.com) — day map scoping, compact view, hide/show days behavior
- [Google Maps JS API fitBounds](https://gist.github.com/mbeaty/1261182) — bounds computation pattern
- [Google Maps: Move Camera Easing](https://developers.google.com/maps/documentation/javascript/examples/move-camera-ease) — camera animation limited to vector maps; raster confirmed via issue tracker

### Tertiary (LOW confidence)
- [Google Maps: panTo issue tracker](https://issuetracker.google.com/issues/229662872) — panTo animation behavior on raster maps (behavior confirmed in codebase but issue tracker is indirect evidence)

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*
