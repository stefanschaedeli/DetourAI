# Phase 4: Map-Centric Responsive Layout - Research

**Researched:** 2026-03-25
**Domain:** Frontend UI layout redesign (vanilla JS + CSS)
**Confidence:** HIGH

## Summary

This phase is a major frontend rewrite of the guide view (`#travel-guide` section) from a single-column tab layout into a split-panel map-centric design. The primary target files are `guide.js` (2462 lines), `maps.js` (571 lines), `sidebar.js` (374 lines), and `styles.css` (4960 lines). The backend requires a minor model change: `TravelStop` currently lacks `tags` and `teaser` fields that exist on `StopOption` but are not carried through to the final plan.

The project uses vanilla JS (no framework, no build step) with imperative DOM manipulation. All map functionality goes through the `GoogleMaps` singleton in `maps.js`. The existing tab system, image loading pipeline (5-tier fallback), drag-and-drop reorder, and edit controls (remove/add/replace) from Phase 3 must be preserved and adapted into the new layout. A detailed UI-SPEC already exists at `04-UI-SPEC.md` with component contracts, colors, spacing, typography, and interaction specifications.

**Primary recommendation:** Structure work as: (1) backend model changes to carry teaser/tags through, (2) CSS/HTML split-panel layout skeleton, (3) stop card component rewrite, (4) map panel persistence + bidirectional sync, (5) stats bar + day timeline, (6) mobile responsiveness, (7) click-to-add-stop on map.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Desktop layout is map left (~58%), content right (scrollable). Map panel is position-fixed while content panel scrolls independently.
- **D-02:** Map stays visible across all tabs (overview, stops, days, calendar, budget). Map content adapts to active tab.
- **D-03:** Existing trip sidebar becomes a collapsible overlay on top of the map. Collapsed by default.
- **D-04:** Dashboard stats (total days, stops, distance, budget remaining) displayed as compact stats bar at top of overview tab -- 4 pill/card widgets. No separate dashboard tab.
- **D-05:** Cards use compact row layout with 16:9 photo on the left and structured info on the right.
- **D-06:** 1 hero photo per card. Click card to see more photos in detail view. Existing 5-tier image fallback chain applies.
- **D-07:** Card info includes: stop number + name, drive time from previous stop, nights staying, travel style tags (colored pills), short description from StopOptionsFinder teaser field.
- **D-08:** Edit controls (remove, reorder, replace) always visible as icon row at bottom-right of each card.
- **D-09:** Bidirectional sync with auto-pan on scroll. Click marker -> scroll to card. Click card -> pan map. Map auto-pans as user scrolls. Map auto-fits on tab switch.
- **D-10:** Click-to-add-stop on map. Click empty spot -> reverse geocode -> "Stopp hier hinzufuegen?" prompt -> insert between nearest stops.
- **D-11:** Driving route as black polyline (replacing blue #4a90d9). Ferry segments as dashed black line. Numbered markers at each stop.

### Claude's Discretion
- Mobile layout pattern (map-top strip, bottom sheet, or other)
- Day timeline visual design and interaction pattern
- Animation/transition details for tab switches and card interactions
- Exact breakpoints for responsive layout (current: 480px, 600px, 767px, 900px)
- Map marker styling (size, colors, number badge design)
- Auto-pan scroll debounce/threshold to avoid jarring jumps
- Stats bar widget styling and layout within overview tab
- How calendar tab content adapts to the split-panel layout

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UIR-01 | Desktop layout uses map-centric split-panel with map as the hero element | D-01, D-02: fixed map left 58%, scrollable content right 42%. Layout contract in UI-SPEC defines exact CSS. |
| UIR-02 | Layout is fully responsive -- comfortable to use on phone browsers | D-12: mobile layout with sticky map strip (~30vh) + content below. Breakpoints at 768px and 1100px. |
| UIR-03 | Stops are presented as visual cards with photos, key facts, and travel style tags | D-05, D-06, D-07: compact row cards with 16:9 photo, structured info, tags. **Requires backend model change** to carry `teaser` and `tags`/`highlights` from StopOption to TravelStop. |
| UIR-04 | Day-by-day timeline is interactive -- scrollable with expandable day details | D-13: vertical timeline with left-edge line, expandable day cards. Existing `renderDaysOverview()` and `renderDayDetail()` need refactoring into inline expand/collapse. |
| UIR-05 | Dashboard overview shows key trip stats (total days, stops, distance, budget remaining) | D-04: stats bar at top of overview tab, 4 pill widgets. Distance must be computed client-side from `drive_km_from_prev` on each stop. |
| UIR-06 | Map and content panels stay synchronized -- selecting a stop highlights it on the map and vice versa | D-09: IntersectionObserver on cards for auto-pan, marker click scrolls to card. D-10: click-to-add uses Google Maps JS SDK Geocoder for reverse geocoding. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vanilla JS (ES2020) | N/A | All frontend logic | Project constraint -- no framework migration |
| Vanilla CSS | N/A | All styling | Project constraint -- no CSS framework |
| Google Maps JS SDK | v3 (weekly channel) | Map rendering, markers, polylines, geocoding | Already loaded, all map code uses it |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Inter font | loaded via Google Fonts | Typography | Already in use via `--font-primary` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| IntersectionObserver | scroll event + getBoundingClientRect | IO is cleaner, better perf, supported in all modern browsers |
| CSS position:fixed for map | position:sticky | Fixed is correct per UI-SPEC since map must stay full-height regardless of scroll position |

No new dependencies needed. This phase is purely frontend restructuring with a minor backend model addition.

## Architecture Patterns

### Current Guide View Structure (BEFORE)
```
#travel-guide section
  .guide-header-row (title + replan button)
  .guide-tabs (5 tab buttons)
  #guide-content (dynamically rendered by active tab)
    -> renderOverview()  -> includes #guide-map (map recreated each tab switch)
    -> renderStopsOverview() -> card grid, no map
    -> renderStopDetail() -> sidebar + detail, includes stop-map-{id}
    -> renderDaysOverview() -> card grid
    -> renderDayDetail() -> sidebar + detail, includes day-map-{id}
    -> renderCalendar()
    -> renderBudget()
```

### Target Structure (AFTER)
```
#travel-guide section
  .guide-split-panel
    .guide-map-panel (position: fixed, 58% width)
      #guide-map (persistent, never destroyed between tabs)
      .sidebar-overlay (collapsible, over map)
      .click-to-add-popup (positioned at click coords)
    .guide-content-panel (margin-left: 58%, scrollable)
      .guide-header-row (title + replan)
      .guide-stats-bar (4 stat pills -- overview tab only)
      .guide-tabs (tab buttons)
      .guide-tab-content (rendered by active tab)
```

### Pattern 1: Persistent Map with Tab-Adaptive Content
**What:** Map panel lives outside `#guide-content` so it is never destroyed by content replacements. Map markers/polylines are updated when tabs switch, not recreated.
**When to use:** Always -- this is the core architectural change.
**Implementation:**
- Move `#guide-map` div outside the tab content area into a fixed panel
- `GoogleMaps.initGuideMap()` is called once when guide view loads
- On tab switch, call a new `_updateMapForTab(tab, plan)` that adjusts markers/polylines
- Stop `_initGuideMap(plan)` from being called on every tab render

### Pattern 2: IntersectionObserver for Scroll-Map Sync
**What:** Observe stop cards with IntersectionObserver (threshold 0.6). When the "currently reading" card changes, pan map to that stop.
**When to use:** Stops tab with card list.
**Implementation:**
```javascript
// Debounced to 300ms after scroll stops
let _scrollDebounce = null;
const _cardObserver = new IntersectionObserver((entries) => {
  const visible = entries.find(e => e.isIntersecting);
  if (!visible) return;
  clearTimeout(_scrollDebounce);
  _scrollDebounce = setTimeout(() => {
    const stopId = visible.target.dataset.stopId;
    if (stopId !== _lastPannedStopId) {
      _lastPannedStopId = stopId;
      _panMapToStop(stopId);
      _highlightMarker(stopId);
    }
  }, 300);
}, { threshold: 0.6 });
```

### Pattern 3: Bidirectional Card-Marker Sync
**What:** Click marker -> scroll to card + highlight. Click/hover card -> pan map + highlight marker.
**Implementation:** Each marker gets an onClick that calls `_scrollToAndHighlightCard(stopId)`. Each card gets click/mouseenter that calls `_panAndHighlightMarker(stopId)`. A shared `_selectedStopId` variable prevents ping-pong.

### Pattern 4: Click-to-Add Stop via Map
**What:** Click empty map area -> reverse geocode -> show popup -> confirm -> call add-stop API.
**Implementation:**
- Add `google.maps.event.addListener(map, 'click', _onMapClick)`
- In handler: check if click was on a marker (if so, skip). Use `google.maps.Geocoder().geocode({ location: latLng })` for reverse geocoding on the frontend
- Show an InfoWindow-style popup at the click point with the place name and "Stopp hier hinzufuegen?" button
- On confirm: find the nearest two consecutive stops to determine `insert_after_stop_id`, then call existing `POST /api/travels/{id}/add-stop`

### Anti-Patterns to Avoid
- **Recreating map on every tab switch:** The current code does `_initGuideMap(plan)` in overview tab, creating a new `google.maps.Map` instance each time. This wastes API quota and causes flicker. The map must persist.
- **Content replacement destroying the map container:** Currently `#guide-map` is inside `#guide-content` which gets wiped by content replacement. Map div must be outside the replacement target.
- **Scroll sync without debounce:** Auto-panning the map on every scroll event causes jarring visual jumps. Must debounce to 300ms and only pan when the topmost visible card changes.
- **Blocking main thread during image loading:** Already handled well by lazy loading. Keep this pattern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Scroll position tracking | Manual scroll event + offset math | IntersectionObserver API | Handles thresholds, avoids layout thrashing |
| Reverse geocoding | Backend round-trip | `google.maps.Geocoder` on frontend | Already loaded, avoids network latency for click-to-add UX |
| Map marker highlighting | Custom overlay swap | Update existing `createDivMarker()` overlay class | Reuse existing overlay pattern |
| Responsive breakpoints | JavaScript window.resize | CSS `@media` queries | Pure CSS is more reliable and performant |
| Card photo aspect ratio | JavaScript resize | CSS `aspect-ratio: 16/9` + `object-fit: cover` | Supported in all modern browsers |

## Common Pitfalls

### Pitfall 1: Map Div Destroyed by Content Replacement
**What goes wrong:** `#guide-map` is inside `#guide-content`. When tab switches, the content area is replaced, destroying the map div. Google Maps instance becomes orphaned.
**Why it happens:** Current architecture puts map inside tab content.
**How to avoid:** Move map div to a sibling panel outside the tab content area. Map panel is position:fixed and never touched by content updates.
**Warning signs:** Map goes blank on tab switch; console errors about detached DOM nodes.

### Pitfall 2: TravelStop Missing Tags/Teaser Data
**What goes wrong:** D-07 requires travel style tags and teaser description on cards, but `TravelStop` model has no `tags`, `teaser`, or `highlights` fields. The data exists on `StopOption` but is lost during the StopOption -> TravelStop conversion.
**Why it happens:** Original architecture only needed region/country for display.
**How to avoid:** Add `tags: List[str] = []` and `teaser: Optional[str] = None` to `TravelStop` model. Populate them during stop option selection in `main.py` where the StopOption is converted to a TravelStop.
**Warning signs:** Empty tag pills, missing descriptions on cards.

### Pitfall 3: Total Distance Not Stored
**What goes wrong:** Stats bar needs "Distanz" but `TravelPlan` has no `total_distance_km` field.
**Why it happens:** Distance is per-stop (`drive_km_from_prev`), never aggregated.
**How to avoid:** Compute client-side: `plan.stops.reduce((sum, s) => sum + (s.drive_km_from_prev || 0), 0)`. Simple and always up-to-date.

### Pitfall 4: Auto-Pan Conflicts with User Map Interaction
**What goes wrong:** User drags/zooms the map, then scroll-sync pans it away.
**Why it happens:** IntersectionObserver fires regardless of user map interaction.
**How to avoid:** Set a `_userInteractingWithMap` flag on `dragstart`/`zoom_changed` events. Clear it after 3 seconds of inactivity. Suppress auto-pan while flag is set.
**Warning signs:** Map jumps while user is trying to explore.

### Pitfall 5: Mobile Touch Events on Map Strip
**What goes wrong:** On mobile, user tries to scroll the page but the map strip captures touch events.
**Why it happens:** Google Maps captures touch for pan/zoom by default.
**How to avoid:** On mobile (<768px), set `gestureHandling: 'cooperative'` on the map so single-finger touch scrolls the page, two-finger touch interacts with map.
**Warning signs:** User gets "stuck" on the map and cannot scroll past it on mobile.

### Pitfall 6: CSS Fixed Panel Breaks on iOS Safari
**What goes wrong:** `position: fixed` on the map panel causes layout issues on iOS Safari when the virtual keyboard opens or when the address bar auto-hides.
**Why it happens:** iOS Safari's viewport behavior with `100vh` is non-standard.
**How to avoid:** Use `height: 100dvh` (dynamic viewport height) instead of `100vh`. Supported in Safari 15.4+. Fallback: `height: -webkit-fill-available`.
**Warning signs:** Map panel extends under the toolbar or leaves a gap on iOS.

### Pitfall 7: Sidebar Overlay z-index Conflicts
**What goes wrong:** The collapsible sidebar overlay on the map can conflict with Google Maps controls, InfoWindows, and the click-to-add popup.
**Why it happens:** Google Maps creates its own stacking contexts.
**How to avoid:** Use a z-index hierarchy: map controls (default) < sidebar overlay (z-index: 10) < click-to-add popup (z-index: 20). The sidebar overlay should use `pointer-events: none` on collapsed state.

## Code Examples

Verified patterns from existing codebase and UI-SPEC:

### Split-Panel CSS Layout
```css
/* Source: UI-SPEC layout contract */
.guide-split-panel {
  display: flex;
  min-height: 100vh;
}

.guide-map-panel {
  position: fixed;
  left: 0;
  top: 0;
  width: 58%;
  height: 100dvh;
  z-index: 1;
}

.guide-content-panel {
  margin-left: 58%;
  width: 42%;
  overflow-y: auto;
  min-height: 100dvh;
  padding: var(--space-lg);
}

@media (max-width: 1099px) and (min-width: 768px) {
  .guide-map-panel { width: 50%; }
  .guide-content-panel { margin-left: 50%; width: 50%; }
}

@media (max-width: 767px) {
  .guide-map-panel {
    position: sticky;
    top: 0;
    width: 100%;
    height: 30vh;
  }
  .guide-content-panel {
    margin-left: 0;
    width: 100%;
  }
}
```

### Stop Card HTML Structure
```javascript
// Source: UI-SPEC component contract for stop cards (D-05 through D-08)
function renderStopCard(stop, i, totalStops) {
  const tags = (stop.tags || []).map(t =>
    `<span class="stop-tag-pill">${esc(t)}</span>`
  ).join('');
  const desc = stop.teaser
    ? `<p class="stop-card-desc">${esc(stop.teaser)}</p>`
    : '';

  return `
    <div class="stop-card-row" data-stop-id="${stop.id}">
      <div class="stop-card-photo">
        <!-- lazy-loaded via existing buildHeroPhotoLoading -->
      </div>
      <div class="stop-card-info">
        <div class="stop-card-title">
          <span class="stop-num-badge">${stop.id}</span>
          <h3>${esc(stop.region)}</h3>
        </div>
        <div class="stop-card-meta">
          <span>${stop.drive_hours_from_prev}h vom vorherigen Stopp</span>
          <span>${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}</span>
        </div>
        ${tags ? '<div class="stop-card-tags">' + tags + '</div>' : ''}
        ${desc}
        <div class="stop-card-actions">
          <!-- remove, reorder, replace icon buttons -->
        </div>
      </div>
    </div>
  `;
}
```

### Stats Bar Computation
```javascript
// Source: derived from TravelPlan model -- no total_distance_km field exists
function renderStatsBar(plan) {
  const stops = plan.stops || [];
  const totalDays = plan.day_plans?.length || 0;
  const totalKm = stops.reduce((sum, s) => sum + (s.drive_km_from_prev || 0), 0);
  const budget = plan.cost_estimate?.budget_remaining_chf;

  return `
    <div class="stats-bar">
      <div class="stat-pill">
        <span class="stat-num">${totalDays}</span>
        <span class="stat-label">Tage</span>
      </div>
      <div class="stat-pill">
        <span class="stat-num">${stops.length}</span>
        <span class="stat-label">Stopps</span>
      </div>
      <div class="stat-pill">
        <span class="stat-num">${Math.round(totalKm).toLocaleString('de-CH')}</span>
        <span class="stat-label">km</span>
      </div>
      <div class="stat-pill">
        <span class="stat-num">CHF ${typeof budget === 'number' ? budget.toLocaleString('de-CH') : '-'}</span>
        <span class="stat-label">Budget</span>
      </div>
    </div>
  `;
}
```

### Click-to-Add Reverse Geocode (Frontend)
```javascript
// Source: Google Maps JS SDK Geocoder API
function _onMapClick(event) {
  if (_editInProgress) return;
  const latLng = event.latLng;
  const geocoder = new google.maps.Geocoder();
  geocoder.geocode({ location: latLng }, (results, status) => {
    if (status !== 'OK' || !results[0]) return;
    const placeName = results[0].formatted_address || '';
    _showAddStopPopup(latLng, placeName);
  });
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `100vh` for full viewport | `100dvh` (dynamic viewport height) | Safari 15.4 / 2022 | Fixes iOS toolbar issues |
| Scroll events for visibility | IntersectionObserver | Widely supported since 2019 | Better performance, no layout thrashing |
| Blue polyline (`#0EA5E9`) | Black polyline (`#2D2B3D`) per D-11 | Phase 4 design decision | Visual consistency with dark markers |
| Map recreated per tab | Persistent map instance | Phase 4 architecture | Saves API quota, eliminates flicker |

## Open Questions

1. **TravelStop tags field -- what data populates it?**
   - What we know: `StopOption` has `option_type` (direct, scenic, cultural, via_point) and `highlights`. Neither directly maps to "travel style tags."
   - What is unclear: Should tags come from the user's `travel_styles` request field, or from the stop's `option_type`, or be AI-generated labels?
   - Recommendation: Use `option_type` as primary tag + the user's relevant `travel_styles` that match this stop. Carry `highlights` from StopOption as well for additional card richness. This can be populated during stop selection without re-querying AI.

2. **Existing saved travels -- will they have tags/teaser?**
   - What we know: Saved travels in SQLite store the full plan JSON. Old plans will not have the new fields.
   - What is unclear: Whether to backfill or handle gracefully with defaults.
   - Recommendation: Handle gracefully with `|| []` / `|| ''` in JS. No migration needed -- Pydantic defaults handle new fields on load.

3. **Google Maps click-to-add and existing InfoWindows**
   - What we know: Current markers have `InfoWindow` on click. The map also needs a click handler for empty areas.
   - What is unclear: How to distinguish marker clicks from empty-area clicks.
   - Recommendation: The map 'click' event fires on empty areas. Marker click events are separate and call `event.stop()`. This is standard Google Maps behavior -- no conflict.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | none (defaults) |
| Quick run command | `cd backend && python3 -m pytest tests/test_models.py -x -q` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UIR-03 (backend) | TravelStop model accepts tags and teaser fields | unit | `cd backend && python3 -m pytest tests/test_models.py -x -q` | Needs update |
| UIR-01-06 | Frontend layout, cards, sync, responsiveness | manual-only | Visual inspection in browser | N/A -- no frontend test framework |

### Sampling Rate
- **Per task commit:** `cd backend && python3 -m pytest tests/test_models.py -x -q`
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Update `tests/test_models.py` to cover TravelStop with tags/teaser fields
- [ ] No frontend test framework exists -- all UI validation is manual (browser testing)

## Sources

### Primary (HIGH confidence)
- Project codebase: `frontend/js/guide.js`, `frontend/js/maps.js`, `frontend/styles.css`, `backend/models/travel_response.py`, `backend/models/stop_option.py`
- `04-UI-SPEC.md` -- detailed component contracts, layout specifications, interaction patterns
- `04-CONTEXT.md` -- user decisions D-01 through D-13

### Secondary (MEDIUM confidence)
- Google Maps JS SDK documentation -- IntersectionObserver, Geocoder reverse geocode, OverlayView patterns (verified against existing maps.js usage)
- CSS `100dvh` browser support -- verified: all major browsers since 2022

### Tertiary (LOW confidence)
- None

## Project Constraints (from CLAUDE.md)

- **Stack:** Vanilla JS ES2020, no build step, no frameworks. Python/FastAPI backend.
- **Language:** All user-facing text in German. Prices in CHF.
- **Frontend API:** `/api` prefix (Nginx proxy). No `localhost:8000` in JS.
- **State:** Global `S` object. `esc()` for XSS. No `fetch()` outside `api.js`.
- **Maps:** Google Maps APIs via `GoogleMaps` singleton in `maps.js`.
- **Logging:** File-based logging via `debug_logger.py`. Frontend errors via `apiLogError()`.
- **Git:** Commit after every change, tag with patch version, push.
- **Type hints:** Required on all Python function signatures.
- **Pydantic:** For all API boundaries.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all vanilla JS/CSS
- Architecture: HIGH - clear understanding of current code structure and target layout from UI-SPEC
- Pitfalls: HIGH - identified from direct code analysis (map destruction, missing model fields, iOS quirks)

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable -- no external dependency changes expected)
