# Phase 9: Guide Module Split - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Decompose the 3010-line `frontend/js/guide.js` monolith (82 functions, 16 module-level variables) into 7 focused modules loaded via script tags in `index.html`. Zero behavioral changes — pure structural refactor to enable safe progressive disclosure work in Phase 10.

</domain>

<decisions>
## Implementation Decisions

### Module Boundaries
- **D-01:** Split into exactly 7 modules: `guide-core.js`, `guide-overview.js`, `guide-stops.js`, `guide-days.js`, `guide-map.js`, `guide-edit.js`, `guide-share.js`
- **D-02:** Function allocation:
  - **guide-core.js** (~200 lines): `showTravelGuide`, `renderGuide`, `switchGuideTab`, `activateGuideTab`, `renderStatsBar`, `loadGuideFromCache`, `_initGuideDelegation`
  - **guide-overview.js** (~400 lines): `renderOverview`, `renderTripAnalysis`, `renderProse`, `renderTravelGuide`, `renderFurtherActivities`, `renderBudget`, `_lazyLoadOverviewImages`, `_highlightReqKeywords`, `_extractReqKeywords`, `_renderReqTags`
  - **guide-stops.js** (~500 lines): `renderStopCard`, `renderStopsOverview`, `renderStopDetail`, `navigateToStop`, `navigateToStopsOverview`, `activateStopDetail`, `_onCardClick`, `_lazyLoadCardImages`, `_lazyLoadSingleStopImages`, `_initStopMap`, `_buildStopMapPin`, `_buildStopMapPopup`
  - **guide-days.js** (~700 lines): `renderDaysOverview`, `renderDayDetail`, `navigateToDay`, `navigateToDaysOverview`, `activateDayDetail`, `_initDayDetailMap`, `_toggleDayExpand`, `_findStopsForDay`, `renderDayTimeBlocks`, `_renderAccommodationHtml`, `_renderActivitiesHtml`, `_renderRestaurantsHtml`, `_renderDayExamplesHtml`, `renderCalendar`, `_initCalendarClicks`
  - **guide-map.js** (~400 lines): `_initGuideMap`, `_setupGuideMap`, `_updateMapForTab`, `_onMarkerClick`, `_scrollToAndHighlightCard`, `_initScrollSync`, `_scrollToGuideStop`, `_scrollToAndHighlight`, `_lazyLoadEntityImages`, `_getActivityIcon`
  - **guide-edit.js** (~700 lines): All editing functions (remove, add, reorder, replace, drag, lock/unlock) PLUS all 5 SSE edit-complete handlers (`remove_stop_complete`, `add_stop_complete`, `reorder_stops_complete`, `replace_stop_complete`)
  - **guide-share.js** (~70 lines): `_renderShareToggle`, `_handleShareToggle`, `_copyShareLink`

### Shared State Strategy
- **D-03:** Each module owns its state variables. No central state object.
  - **guide-core.js** owns navigation state: `activeTab`, `_activeStopId`, `_activeDayNum`
  - **guide-map.js** owns map state: `_guideMarkers`, `_guidePolyline`, `_guideMapInitialized`, `_userInteractingWithMap`, `_userInteractionTimeout`, `_lastPannedStopId`, `_scrollDebounce`, `_cardObserver`
  - **guide-edit.js** owns edit state: `_editInProgress`, `_editSSE`, `_dragStopSourceIndex`
  - **guide-stops.js** owns cache state: `_initializedStopMaps`
- **D-04:** Cross-module state access via exported getters/setters (e.g., guide-edit reads `activeTab` from guide-core's global).

### Edit Operations Placement
- **D-05:** All route editing logic (add/remove/reorder/replace stop, drag-drop, lock/unlock) lives in `guide-edit.js`.
- **D-06:** SSE edit-complete handlers stay in `guide-edit.js` — they call into `renderGuide()` (guide-core) and `GoogleMaps.setGuideMarkers()` (maps.js) as cross-module calls.

### Load Order & Namespacing
- **D-07:** Flat globals — no namespace object. All functions remain global names, consistent with the rest of the codebase. No changes to existing call sites in router.js, progress.js, etc.
- **D-08:** Script tag load order in index.html: `guide-core.js` → `guide-overview.js` → `guide-stops.js` → `guide-days.js` → `guide-map.js` → `guide-edit.js` → `guide-share.js`
- **D-09:** Each module file gets a header comment documenting: what it does, which globals it reads from other guide modules, and what globals it provides.

### Claude's Discretion
- Exact line-level cut points within guide.js for each function
- Whether _private helper functions move with their primary consumer or stay closer to callers
- Header comment format and level of detail

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Frontend — Current Monolith
- `frontend/js/guide.js` — The 3010-line source file being decomposed (82 functions)
- `frontend/index.html` — Script tag load order (guide.js currently loaded here, must be replaced with 7 new tags)

### Frontend — Dependencies
- `frontend/js/state.js` — Global `S` object, `TRAVEL_STYLES`, `FLAGS` — read by guide modules
- `frontend/js/api.js` — `_fetch()`, `_fetchQuiet()`, `openSSE()` — called by guide-edit
- `frontend/js/maps.js` — `GoogleMaps.setGuideMarkers()`, `GoogleMaps.clearGuideMarkers()`, `GoogleMaps.createDivMarker()` — called by guide-map and guide-edit
- `frontend/js/router.js` — Routes to guide functions (`showTravelGuide`, `navigateToStop`, etc.)
- `frontend/js/progress.js` — Calls `showTravelGuide()` on job completion

### Planning
- `.planning/REQUIREMENTS.md` — STRC-01 definition
- `.planning/ROADMAP.md` — Phase 9 success criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- All 82 functions are already globals — no extraction needed, just file separation
- `esc()` function (state.js) used extensively for HTML escaping — all modules will continue using it
- `GoogleMaps` namespace (maps.js) provides the map API that guide-map will call

### Established Patterns
- All JS modules use flat globals — no namespace objects anywhere in the codebase
- Script load order in index.html determines dependency availability
- Private functions prefixed with `_` — convention to maintain in split modules
- `S.result` is the central travel plan data object read by all guide rendering functions

### Integration Points
- `frontend/index.html` — Replace single `<script src="js/guide.js">` with 7 ordered script tags
- `frontend/js/router.js` — Calls `showTravelGuide()`, `navigateToStop()`, `navigateToDay()` — these remain global, no changes needed
- `frontend/js/progress.js` — Calls `showTravelGuide()` on job_complete — remains global, no changes needed
- All existing tests reference guide functions by global name — no test changes expected

</code_context>

<specifics>
## Specific Ideas

- The 7-module split was chosen over fewer modules because guide-share (70 lines) and guide-edit (700 lines) serve distinctly different concerns — keeping them separate improves Phase 10 readability
- SSE handlers deliberately placed in guide-edit.js (not guide-core) because they're the tail end of edit workflows, not general event routing

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-guide-module-split*
*Context gathered: 2026-03-27*
