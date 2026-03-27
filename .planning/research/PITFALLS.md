# Domain Pitfalls

**Domain:** Progressive disclosure UI retrofit on existing vanilla JS travel planner
**Researched:** 2026-03-27
**Confidence:** HIGH (based on direct codebase analysis of guide.js, maps.js, router.js, tasks/__init__.py)

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Full DOM Rebuild on Every Navigation Destroys Map and Listeners

**What goes wrong:** The current `renderGuide()` replaces the entire `#guide-content` element's children on every tab switch. This wipes all DOM nodes, killing IntersectionObservers, scroll positions, and event listeners attached to child elements. Progressive disclosure adds a third depth level (overview -> day -> stop-within-day), which means navigation happens much more frequently than tab switching. Each transition costs a full DOM rebuild.

**Why it happens:** The existing pattern was designed for flat tab switching where full re-renders were acceptable. Progressive disclosure adds nested navigation that the user traverses rapidly (click day, click stop, go back, click another stop). There are 45 DOM content replacement calls in guide.js already.

**Consequences:** Google Maps flickers on every drill-down (the persistent `guide-map` survives but markers get rebuilt). The `_guideMapInitialized` flag and `_initializedStopMaps` set show this is already a known pain point. Scroll positions are lost. Image lazy-loading restarts (shimmer skeletons reappear). The `_cardObserver` IntersectionObserver for scroll-sync must be re-attached after every render. Animation state resets.

**Prevention:**
1. Keep the single persistent map container outside `guide-content` (already done).
2. For drill-down transitions within a tab, use CSS visibility/display toggling on pre-rendered sections rather than full DOM replacement. Render the day overview once, then show/hide day detail as an overlay or swap panel.
3. Only do full content replacement for sections that actually changed (e.g., after a stop edit).
4. Add `showDayDetail(dayNum)` and `showStopInDayDetail(dayNum, stopId)` functions that toggle visibility rather than calling `renderGuide()`.

**Detection:** Map flickers or re-centers on every click. Images re-show shimmer skeletons on drill-down. Console shows repeated `_initGuideDelegation` calls. Scroll position resets when drilling up from stop to day.

**Phase:** Must be the architectural decision made first, before any progressive disclosure code.

---

### Pitfall 2: Guide.js 3007-Line Monolith Makes Progressive Disclosure Ungovernable

**What goes wrong:** `guide.js` contains: tab rendering (overview, stops, days, calendar, budget), stop detail rendering, day detail rendering, map setup, scroll sync, drag-and-drop reorder, stop editing (add/remove/replace), image lazy loading, modals, SSE handlers for edits, event delegation, and URL routing integration. Adding a third navigation depth plus map focus management will push it past 4000 lines with deeply entangled state.

**Why it happens:** Natural accumulation -- each v1.0 feature was small enough to add inline. But progressive disclosure requires coordinating navigation state (`_activeStopId`, `_activeDayNum`, plus a new "current view level" concept) with map focus, URL routing, and content rendering. These concerns are all interleaved in one file.

**Consequences:** Bugs where drilling into a stop within a day sets `_activeStopId` but forgets to update `_activeDayNum`. Map focus functions that check the wrong state variable. `_editInProgress` lock interacts with navigation state in ways that are hard to reason about. Merge conflicts when working on map focus and content rendering simultaneously.

**Prevention:** Split guide.js BEFORE adding progressive disclosure:
- `guide-core.js` -- `showTravelGuide()`, `renderGuide()`, tab switching, view state management
- `guide-overview.js` -- overview rendering, stats bar, trip analysis
- `guide-stops.js` -- stops overview, stop detail, stop editing (add/remove/replace/reorder)
- `guide-days.js` -- days overview, day detail, time blocks
- `guide-map-sync.js` -- map setup, marker click handlers, scroll sync, map focus management

Keep current global function names as exports so nothing breaks.

**Detection:** PRs touching 15+ functions in guide.js. Functions with 3+ conditionals checking `_activeStopId`, `_activeDayNum`, and view level simultaneously.

**Phase:** Must happen as a prep phase before progressive disclosure implementation.

---

### Pitfall 3: Mixing Tech Debt Fixes with UI Redesign Creates Untestable Commits

**What goes wrong:** The milestone includes both bug fixes (map markers not refreshing after edits, Celery include list, stats bar) and a UI redesign (progressive disclosure). If done in the same phase, regressions are impossible to isolate. "Did the map break because of the marker refresh fix, or because of the new focus management code?"

**Why it happens:** Both feel related (map markers + map focus management), so it seems efficient to do them together. But they have different risk profiles: tech debt fixes are surgical and testable against the current UI; UI redesign is exploratory and needs iteration.

**Consequences:** If progressive disclosure introduces a map bug, you cannot revert it without also reverting the marker refresh fix. Testing the marker refresh fix against the NEW view misses bugs that only manifest in the OLD view (which is what users have been using). Stats bar fix validated against old tab layout may break in new progressive layout.

**Prevention:** Strict phase ordering:
1. **Phase 1: Tech debt fixes only** -- map marker refresh, Celery include list, stats bar update, RouteArchitect drive limits. All fixes tested against current UI. Tag a release.
2. **Phase 2: guide.js restructuring** -- split into modules, zero behavioral changes. All existing behavior preserved.
3. **Phase 3: Progressive disclosure UI** -- new navigation, map focus, compact day cards.
4. **Phase 4: Browser verification** -- the 9 pending UI items verified against the new view.

**Detection:** A commit touches both `backend/tasks/__init__.py` and `frontend/js/guide.js` rendering logic. Rollback of a UI change also rolls back an unrelated bug fix.

**Phase:** This is a milestone planning concern, not a specific phase.

---

### Pitfall 4: Map Focus Fighting with Existing Scroll-Sync and User Interaction

**What goes wrong:** The codebase already has three map-movement systems: (1) `_initScrollSync()` with IntersectionObserver that auto-pans map when cards scroll into view, (2) `_onMarkerClick()` that scrolls to cards and highlights markers when map markers are clicked, (3) `_userInteractingWithMap` flag with 3-second timeout that suppresses auto-pan during user drag. Adding a fourth system -- map focus on drill-down where entering "Day 3" zooms the map to Day 3's region -- will fight with all three.

**Why it happens:** Each system was designed independently for the flat tab view. Progressive disclosure adds a hierarchical focus concept that must override scroll-sync when active, but scroll-sync should still work within a drilled-down day's stop list.

**Consequences:** User drills into Day 3 (map should zoom to Amalfi Coast). Scroll-sync immediately fires because a card is visible, panning to a different stop. Or: `_updateMapForTab()` calls `GoogleMaps.fitAllStops()` on every render (line 1716), overriding the day-level zoom. Or: the 3-second `_userInteractionTimeout` expires while user is reading content, and auto-pan snaps the map away from where they were looking.

**Prevention:**
1. Introduce a `_mapFocusMode` state machine: `'all'` (fit all stops), `'day'` (fit day region), `'stop'` (center on single stop). This replaces the ad-hoc `_updateMapForTab()`.
2. Scroll-sync should only be active when `_mapFocusMode === 'all'` and the stops overview is showing.
3. Drill-down sets `_mapFocusMode` and suppresses scroll-sync until the user drills back up.
4. `_userInteractingWithMap` should override ALL automatic movements, including drill-down focus.
5. When the user manually pans/zooms while in a drill-down, do NOT snap back to drill-down bounds.

**Detection:** Map "jumps" or "fights" when navigating between views. User drags map then it snaps back. Drilling into a day does not change map view. Drilling back to overview does not restore full-route view.

**Phase:** The `_mapFocusMode` abstraction should be designed before progressive disclosure work and implemented as part of the guide-map-sync module.

---

### Pitfall 5: URL Routing Collision Between Two Paths to the Same Stop

**What goes wrong:** Current router handles `/travel/{id}/stops/{stopId}` (stop detail from stops tab). Progressive disclosure adds `/travel/{id}/days/{dayNum}` (day drill-down) and will need `/travel/{id}/days/{dayNum}/stops/{stopId}` (stop within day context). These two routes to the same stop detail have different back-navigation behaviors and different map focus states, but render the same content.

**Why it happens:** The existing `navigateToStop()` function sets `_activeStopId` and calls `renderGuide(plan, 'stops')`. The new day-context path needs to set both `_activeDayNum` AND `_activeStopId` and render in a different container. Without careful state tracking, the back button goes to the wrong place.

**Consequences:** User drills: Overview -> Day 3 -> Stop 5 -> Browser Back. Expected: Day 3. Actual: Stops overview (because `navigateToStopsOverview()` is the existing back handler for stops). Or: URL says `/travel/1/days/3/stops/5` but refreshing the page renders the stops-tab view instead of the day-context view because the router does not distinguish.

**Prevention:**
1. Use URL path to encode context: `/travel/{id}/days/{dayNum}/stops/{stopId}` is distinct from `/travel/{id}/stops/{stopId}`.
2. Add a new router pattern for the day-context stop detail. Its handler sets `_activeDayNum` AND `_activeStopId`.
3. Back navigation must be derived from URL structure, not from module-level state. "Go up one level" means trim the last URL segment.
4. Add explicit tests for: bookmark a deep URL, refresh, verify correct view renders.

**Detection:** Browser back goes to unexpected view. Refreshing a deep URL shows wrong content. `_activeDayNum` is stale after navigating via the stops tab.

**Phase:** Router changes should be designed upfront and implemented alongside progressive disclosure views.

## Moderate Pitfalls

### Pitfall 6: Map Marker Refresh Bug Has a Specific Root Cause

**What goes wrong:** After route edits (add/remove/reorder stop), map markers and polyline do not update. Root cause: `_executeRemoveStop()` (and similar edit handlers) call `renderGuide(data, 'stops')` which calls `_updateMapForTab(plan, 'stops')` which calls `GoogleMaps.fitAllStops(plan)`. But `fitAllStops` only adjusts viewport bounds -- it does NOT rebuild markers. `GoogleMaps.setGuideMarkers()` is only called from `_setupGuideMap()`, which is only called from `showTravelGuide()` (initial load).

**Why it happens:** `renderGuide()` adjusts the viewport but `_setupGuideMap()` (which rebuilds markers) is intentionally not called on re-render because it re-initializes the entire map. The marker rebuild step was simply never added to the edit completion path.

**Prevention:** After any stop edit, explicitly call `GoogleMaps.setGuideMarkers(plan, _onMarkerClick)` to rebuild markers with the new stop list. Create a `_refreshMapAfterEdit(plan)` helper that calls both `setGuideMarkers` and `fitAllStops`. Call it from all edit completion handlers (`remove_stop_complete`, `add_stop_complete`, `reorder_stops_complete`, `replace_stop_complete`).

**Detection:** After removing a stop, its marker remains on the map. After reordering stops, marker numbers do not update. After adding a stop, no new marker appears.

**Phase:** Tech debt fix phase. Highest-priority bug fix since it affects current production.

---

### Pitfall 7: `replace_stop_job` Missing from Celery Include List

**What goes wrong:** `backend/tasks/__init__.py` includes `run_planning_job`, `prefetch_accommodations`, `remove_stop_job`, `add_stop_job`, `reorder_stops_job` -- but NOT `replace_stop_job`. The task works in dev mode (no Celery, runs in-process via `asyncio.ensure_future`) but will raise `NotRegistered` in Docker with actual Celery workers.

**Why it happens:** The replace_stop_job was likely added after the initial task registration list, and the include list was not updated.

**Prevention:** Add `"tasks.replace_stop_job"` to the include list. Consider writing a test that scans `backend/tasks/` for `@celery_app.task` decorators and verifies all are included.

**Detection:** Stop replacement works in dev mode but fails in Docker. Celery worker logs show `NotRegistered` error.

**Phase:** Tech debt fix phase. Five-minute fix, test in Docker.

---

### Pitfall 8: Stats Bar Only Re-renders on Overview Tab

**What goes wrong:** In `renderGuide()`, the stats bar is cleared and re-rendered only when `activeTab === 'overview'` (lines 86-93). After a stop edit from the stops tab, `renderGuide(data, 'stops')` is called, so the stats bar shows stale totals (old stop count, old cost estimate) until the user manually switches to the overview tab.

**Prevention:** Always re-render the stats bar in `renderGuide()` regardless of active tab. The stats bar element (`#guide-stats-bar`) is outside `#guide-content`, so it is not affected by content replacement. Alternatively, call a dedicated `_updateStatsBar(plan)` from all edit completion handlers.

**Phase:** Tech debt fix phase. Small fix.

---

### Pitfall 9: Event Delegation Assumes Flat DOM Structure

**What goes wrong:** `_initGuideDelegation()` sets up click handlers on `#guide-content` using `e.target.closest('.stop-overview-card')` etc. With progressive disclosure, the DOM nesting changes: a stop card inside a day card inside the content area. `.closest()` might match an outer container before the intended inner element. For example, a compact day card and a stop card within it both have click handlers -- the click bubbles up and triggers the day card handler after the stop handler.

**Prevention:** Use `data-action` attributes on clickable elements and dispatch on those instead of relying solely on `.closest()` with CSS class names. Ensure inner click handlers call `e.stopPropagation()` when the click is consumed. Test click behavior with nested cards specifically.

**Phase:** Progressive disclosure UI phase. Design delegation strategy before building nested card layouts.

---

### Pitfall 10: Compact Day Cards Without Stable Height Cause Layout Shifts

**What goes wrong:** Compact day cards in the overview will show summary info (day number, location, drive time). If images are lazy-loaded (as currently done with `_lazyLoadCardImages`), cards shift height as images appear, causing jarring layout shifts in the scrollable overview.

**Prevention:** Use fixed-height card containers with CSS `aspect-ratio` placeholders. Apply `contain: content` on cards. Consider omitting images from compact overview cards entirely -- text summary is sufficient at overview level, save images for drill-down detail.

**Phase:** Progressive disclosure UI phase.

## Minor Pitfalls

### Pitfall 11: CSS Transition Conflicts Between Tab Switch and Drill-Down

**What goes wrong:** The current tab switch applies a fade-in (opacity 0->1, translateY 6px->0). If drill-down also animates (e.g., slide-in from right for deeper levels), both animations may conflict when navigation triggers both a tab change and a depth change.

**Prevention:** Distinguish between tab-level transitions (fade) and depth-level transitions (slide/expand). Use a CSS class on the content container to indicate transition type. Ensure only one animation plays at a time by canceling the previous transition before starting a new one.

**Phase:** Progressive disclosure polish step.

---

### Pitfall 12: Google Maps `fitBounds` Over-Zooms on Single Point

**What goes wrong:** Current code uses uniform padding `{ top: 40, right: 40, bottom: 40, left: 40 }` for all `fitBounds` calls (lines 1041, 1672, 2023). When drilling into a single stop, the bounds contain one point, causing maximum zoom (street-level view that shows nothing useful).

**Prevention:** For single-stop focus, use `map.setCenter(stopLatLng)` + `map.setZoom(13)` instead of fitBounds. For day-level focus (2-4 stops), use fitBounds with larger padding. For overview (all stops), keep current padding. Encode this in the `_mapFocusMode` logic.

**Phase:** Progressive disclosure UI phase.

---

### Pitfall 13: Module Load Order in index.html Matters After Split

**What goes wrong:** When splitting guide.js into multiple modules, the new files must be loaded in the correct order in `index.html` script tags. `guide-core.js` must load before `guide-stops.js` (which references `renderGuide`), and `guide-map-sync.js` must load after `maps.js` (which defines `GoogleMaps`). Getting the order wrong causes `ReferenceError` at page load with no helpful error message.

**Prevention:** Document the dependency graph in a comment at the top of each new module file. Keep the original function names as globals (no namespace change). Test by loading the page in a fresh incognito window after every module split.

**Phase:** guide.js restructuring phase.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Tech debt fixes | Marker refresh fix works but breaks after UI redesign changes rendering flow | Design fix as `_refreshMapAfterEdit(plan)` helper that is render-strategy-agnostic |
| Tech debt fixes | Celery include fix seems trivial but needs Docker testing | Test replace-stop in Docker after fix, not just dev mode |
| Tech debt fixes | Stats bar fix changes render timing, may flash stale values during animation | Debounce stats bar update to after the fade-in completes |
| guide.js split | Breaking existing event delegation during module extraction | Keep `_initGuideDelegation` intact in guide-core.js; move render functions first |
| guide.js split | Module load order in index.html causes silent failures | Document dependencies, test in incognito after each extraction |
| guide.js split | Module-level variables (`_activeStopId`, `_editInProgress`) need to be shared across modules | Keep all shared state in guide-core.js or promote to the `S` object in state.js |
| Progressive disclosure | Drill-down from overview vs. from stops tab leads to same stop but different contexts | Use URL path to encode context; derive back-navigation from URL |
| Progressive disclosure | Map focus changes feel jarring without animation | Use `map.panTo()` + `map.setZoom()` with smooth transitions instead of instant `fitBounds` |
| Progressive disclosure | Edit operations during drill-down leave view in inconsistent state | After any edit, reset to parent view level (day overview after removing stop within day) |
| Progressive disclosure | `_updateMapForTab` calls `fitAllStops` unconditionally, overriding drill-down focus | Replace with `_mapFocusMode`-aware update that respects current focus level |
| Browser verification | 9 pending UI items may be invalidated by redesigned view | Verify against NEW view, not old; do this phase last |

## Sources

- Direct codebase analysis: `frontend/js/guide.js` (3007 lines, 45 DOM content replacement calls)
- Direct codebase analysis: `frontend/js/maps.js` -- `setGuideMarkers()` only called from `_setupGuideMap()`
- Direct codebase analysis: `frontend/js/router.js` -- existing route patterns for travel/stops/days
- Direct codebase analysis: `backend/tasks/__init__.py` -- confirmed `replace_stop_job` missing from include list
- Existing code patterns: `_userInteractingWithMap`, `_scrollDebounce`, `_lastPannedStopId` (scroll-sync complexity)
- Existing code patterns: `_activeStopId` / `_activeDayNum` module-level state (navigation depth tracking)
- Existing code patterns: `_lockEditing()` / `_unlockEditing()` (edit state management)
- Project scope: `.planning/PROJECT.md` v1.1 milestone definition

---
*Pitfalls research for: v1.1 Progressive Disclosure Travel View Redesign*
*Researched: 2026-03-27*
