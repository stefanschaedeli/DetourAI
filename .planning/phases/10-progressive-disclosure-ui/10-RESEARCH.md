# Phase 10: Progressive Disclosure UI — Research

**Researched:** 2026-03-27
**Domain:** Vanilla JS frontend — drill-down navigation, CSS transitions, Google Maps marker control
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Overview shows compact trip summary header (title, dates, travelers, budget) followed by a grid of clickable day cards. Each day card shows: day number, title/region, stop count, drive time, and a small thumbnail image (first stop's photo).
- **D-02:** Existing overview content (trip analysis, budget breakdown, travel guide prose) moves to a collapsible section below the day cards grid, collapsed by default. User can expand without drilling into a day.
- **D-03:** Crossfade transition between drill-down levels. Current content fades out, new content fades in. CSS transitions with JS coordination.
- **D-04:** Content panel scrolls to top on every drill-down and back-navigation.
- **D-05:** Map uses smooth pan+zoom (Google Maps panTo/fitBounds) when changing drill-down context. Map animates independently of content crossfade.
- **D-06:** Unified breadcrumb bar above content at all drill levels. Format: `Uebersicht > Tag 3 > Annecy`. Each segment is clickable for direct navigation to that level. Hidden (or just static title) at overview level.
- **D-07:** Browser back/forward buttons work with drill-down via URL routing. Each drill-down pushes a URL segment (e.g., `/travel/42/day/3`, `/travel/42/stop/5`). Existing router.js patterns extended with day/stop segments.
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

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NAV-01 | Travel view shows compact overview with trip summary, day cards, and full-route map as default landing | `renderOverview()` in guide-overview.js restructured: new day-cards-grid block + collapsible for existing analysis content |
| NAV-02 | User can drill into a day to see that day's stops, activities, restaurants with map focused on day's region | `navigateToDay()` + `renderDayDetail()` already exist; extend with crossfade, breadcrumb, URL push |
| NAV-03 | User can drill into a stop to see accommodation, activities, restaurants with map focused on stop area | `navigateToStop()` + `renderStopDetail()` already exist; extend with crossfade, breadcrumb, URL push |
| NAV-04 | Breadcrumb navigation allows back-navigation at each drill level (overview <- day <- stop) | New `.guide-breadcrumb` bar inserted in HTML; JS renders correct segments per drill level |
| NAV-05 | Map markers dim for non-focused stops when viewing a specific day or stop | `_updateMapForTab()` in guide-map.js extended; new `dimNonFocusedMarkers(stopIds)` / `restoreAllMarkers()` in maps.js |
| NAV-06 | Browser back/forward buttons work with drill-down navigation via URL routing | `router.js` already has `/travel/{id}/days/{n}` and `/travel/{id}/stops/{n}` routes — handlers call `activateDayDetail` / `activateStopDetail` |

</phase_requirements>

---

## Summary

Phase 10 restructures the travel guide's overview tab into a three-level drill-down: overview (day cards grid), day detail, and stop detail. The persistent Google Maps panel responds at each level. The core rendering functions (`renderDayDetail`, `renderStopDetail`) and navigation helpers (`navigateToDay`, `navigateToStop`) already exist from Phase 9. This phase wires them together under a unified URL-driven navigation model with crossfade transitions, a breadcrumb bar, and map dimming for non-focused stops.

The work is almost entirely frontend — no backend changes needed. The implementation touches six files: `guide-core.js`, `guide-overview.js`, `guide-map.js`, `maps.js`, `router.js`, and `styles.css`. A single new HTML element (the breadcrumb bar) must be added to `index.html`. All patterns are consistent with Phase 9 decisions: flat globals, imperative DOM, no build step.

The highest-risk items are (1) the crossfade sequence coordinating DOM mutation with CSS transitions and scroll-to-top, and (2) map marker dimming using custom div-based OverlayView markers (not standard Google Markers) which requires direct DOM opacity manipulation rather than a standard `setOpacity()` API call.

**Primary recommendation:** Extend existing navigation helpers with crossfade logic and breadcrumb rendering. Use opacity-only dimming on marker `_div` elements. Keep the collapsible section using `max-height` transition (not `display:none` swap) to avoid reflow cost.

---

## Standard Stack

### Core — already in project (no new dependencies)

| Library/API | Version | Purpose | Notes |
|-------------|---------|---------|-------|
| Vanilla JS ES2020 | — | All logic | No build step, no framework |
| Google Maps JS SDK | loaded dynamically | Persistent guide map, fitBounds, panTo | OverlayView-based div markers |
| CSS transitions | — | Crossfade, collapsible, breadcrumb | `opacity`, `max-height`, `transform` only |

**Installation:** None required. All dependencies are already present.

### Alternatives Considered

| Instead of | Could Use | Why rejected |
|------------|-----------|-------------|
| `max-height` transition for collapsible | `height` transition with JS | `height` requires reading clientHeight first — more JS; `max-height` is a pure-CSS pattern already used in codebase |
| Opacity-only marker dimming | Grayscale CSS filter or size reduction | Opacity is the simplest and matches existing `.dragging { opacity: 0.5 }` pattern; grayscale requires a different DOM path |
| `pushState` + popstate for drill-down | hash routing | pushState is already the codebase pattern (router.js) |

---

## Architecture Patterns

### Recommended File Change Summary

```
frontend/
├── js/
│   ├── guide-core.js       — add crossfade helper, breadcrumb render, drill-level dispatch
│   ├── guide-overview.js   — restructure renderOverview(): day-cards-grid + collapsible
│   ├── guide-map.js        — extend _updateMapForTab(): dim/restore markers per drill level
│   ├── maps.js             — add dimNonFocusedMarkers() + restoreAllMarkers() + fitDayStops() to public API
│   └── router.js           — route patterns already exist; verify /day/ vs /days/ naming
├── index.html              — add .guide-breadcrumb bar element (sibling to #guide-content)
└── styles.css              — add new CSS classes (see Component Inventory in UI-SPEC)
```

### Pattern 1: Crossfade Drill-Down (D-03, D-04)

**What:** Two-step opacity transition — current content fades to 0, scroll to top, new content renders at opacity 0 then transitions to 1.

**When to use:** Every drill-down and every back-navigation.

**Critical insight from reading guide-core.js:** The existing `renderGuide()` already has a fade-in animation using inline `style.opacity` + `requestAnimationFrame`. Phase 10 must replace/extend that with the full two-phase crossfade (fade-out first, THEN render new content, THEN fade-in). The current code mutates content immediately then fades in — that pattern cannot produce a true crossfade.

The crossfade function uses the safe DOM mutation pattern already established in the codebase (wrapping HTML strings with a temp element and using appendChild, per the existing pattern in guide-core.js `renderStatsBar`):

```
function _drillTransition(contentEl, renderFn):
  1. Set opacity 0 with ease-in transition (150ms)
  2. After 150ms: set contentEl.scrollTop = 0
  3. Call renderFn() to get HTML string
  4. Use safe DOM update (tmp element + appendChild, same pattern as renderStatsBar in guide-core.js)
  5. Set opacity 0 immediately
  6. requestAnimationFrame: set opacity 1 with ease-out transition (250ms)
```

**Pitfall:** `requestAnimationFrame` inside `setTimeout` — the rAF callback must fire AFTER the new content is painted. Test on slow devices.

### Pattern 2: Breadcrumb Bar Rendering

**What:** A sticky bar rendered above `#guide-content`, updated on every navigation change.

**Key finding:** The breadcrumb bar must live OUTSIDE `#guide-content` (which gets replaced on every render). It must be a sibling element in the HTML inserted before `#guide-content`.

```
In index.html, inside #travel-guide section, BEFORE #guide-content:
  <div id="guide-breadcrumb" class="guide-breadcrumb" style="display:none"></div>
  <div id="guide-content" ...>...</div>
```

Breadcrumb update function in guide-core.js:
```
_renderBreadcrumb(level, plan, dayNum, stopId):
  - level 'overview': hide bar
  - level 'day': show "Übersicht › Tag N: Title"
  - level 'stop': show "Übersicht › Tag N › StopName"
  All segment text must be wrapped with esc() before insertion.
  Use textContent for static segments, esc() for user data segments.
  Add data-nav-level and data-day-num attributes for click delegation.
```

### Pattern 3: Map Dimming with OverlayView Markers (NAV-05)

**Critical finding:** The guide map uses custom div-based markers created via `google.maps.OverlayView`. These are NOT standard `google.maps.Marker` objects and do NOT have a `setOpacity()` method. Dimming must be done by directly manipulating `marker._div.style.opacity`.

The `_guideMarkerList` in `maps.js` stores these overlay objects. Each overlay stores its DOM element at `overlay._div`. The `_stopId` property is set on each marker at creation (line 646 of maps.js: `m._stopId = stopId`).

```
New functions needed in maps.js public API:

dimNonFocusedMarkers(focusedStopIds: string[]):
  For each marker in _guideMarkerList:
    - if marker._div is null: skip (async OverlayView not yet added)
    - if marker._stopId is in focusedStopIds: set opacity 1.0
    - else: set opacity 0.35
    - set transition 'opacity 0.3s ease' on _div

restoreAllMarkers():
  For each marker in _guideMarkerList:
    - if marker._div: set opacity 1.0, transition 'opacity 0.3s ease'

fitDayStops(stops: TravelStop[]):
  Build LatLngBounds from the provided stop array
  Call _guideMap.fitBounds(bounds, {top:48, right:48, bottom:48, left:48})
```

**For polyline:** The `_guidePolylineRef` is a single polyline for the full route. To highlight a day segment, add a separate overlay polyline covering only that day's stops at drill-in, and remove it on back-navigation.

### Pattern 4: Day Cards Grid — Data Mapping

**What:** `day_plans` array contains `{day, title, description, stops_on_route, type}`. The first stop's photo is needed for the thumbnail.

**Mapping `day_plans` to stops for thumbnail:**
- `day_plans[i].stops_on_route` is an array of stop name strings (not IDs)
- Use `_findStopsForDay(plan, dayNum)` (already exists in guide-days.js) to get actual stop objects
- First result provides lat/lng for `_lazyLoadEntityImages`

**Day card data to render:**
- Title: `day_plans[i].title`
- Stop count: `_findStopsForDay(plan, dayNum).length`
- Drive time: sum of `stop.drive_hours_from_prev` for day's stops
- Thumbnail: first stop's region image via `_lazyLoadEntityImages(cardEl, stop.region, stop.lat, stop.lng, 'city', 'sm')`
- Fallback: first letter of day title in a colored box (CSS only)

### Pattern 5: URL Route Alignment

**Critical finding from reading router.js lines 12-13:** The router ALREADY has these patterns:

```
{ pattern: /^\/travel\/(\d+)(?:-[^/]+)?\/stops\/(\d+)$/, handler: '_travelStopDetail' }
{ pattern: /^\/travel\/(\d+)(?:-[^/]+)?\/days\/(\d+)$/, handler: '_travelDayDetail' }
```

The UI-SPEC (10-UI-SPEC.md) specifies `/travel/{id}/day/{n}` and `/travel/{id}/stop/{stopId}` (singular: `day`, `stop`), but the router uses `days` and `stops` (plural). This is a naming discrepancy.

**Recommendation:** Use existing plural patterns (`/days/`, `/stops/`) — no router changes needed. The handlers `activateStopDetail` and `activateDayDetail` already exist and are wired. The navigation helpers `navigateToDay()` and `navigateToStop()` already push `/days/{n}` and `/stops/{n}` URLs respectively.

### Pattern 6: Collapsible Section with max-height

**What:** CSS `max-height` transition for the collapsible details section.

**Known pitfall with `max-height` animation:** If `max-height` is set to `2000px` but actual content is `400px`, the transition completes in the first ~20% of the duration (content reaches its height then stops animating). The visual result is the content appears to jump open almost instantly.

**Fix:** Use a longer transition (0.5s) for the max-height so the easing is visible in the first portion of the animation. Or use JS to measure `scrollHeight` and set `max-height` to the actual measured value for collapse-to-zero.

### Anti-Patterns to Avoid

- **Putting the breadcrumb inside `#guide-content`:** The breadcrumb must persist across `renderGuide()` calls — it cannot live inside guide-content which is replaced on every render.
- **Using `display:none` for crossfade:** Animating from `display:none` does not produce a transition — use `opacity: 0` with `pointer-events: none` instead.
- **Calling `_updateMapForTab` before crossfade completes:** Map focus during a crossfade causes the map to animate while content is invisible. Fire map update after the fade-out (before fade-in) so both complete around the same time.
- **Adding a new click listener for day card clicks:** The `_initGuideDelegation` guard (`_guideDelegationReady`) means only one listener ever exists. New `.day-card-v2` click handling MUST be added to the existing delegation block, not in a new `addEventListener` call.
- **Calling `dimNonFocusedMarkers` without checking `_div` for null:** OverlayView `onAdd` fires asynchronously — `_div` may be null immediately after `setGuideMarkers`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Image lazy loading for thumbnails | Custom IntersectionObserver setup | `_lazyLoadEntityImages()` already in guide-map.js |
| Stop-to-day mapping | Custom day/stop association logic | `_findStopsForDay(plan, dayNum)` already in guide-days.js |
| URL slug generation | Custom slug function | `Router.slugify()` and `Router.travelPath()` already in router.js |
| Map bounds for all stops | Manual lat/lng iteration | `GoogleMaps.fitAllStops(plan)` already in maps.js |
| Map bounds for a day's stops | Manual lat/lng iteration | Add `fitDayStops(stops)` to maps.js using same pattern as `fitAllStops` |
| Marker cleanup | Manual DOM removal | `GoogleMaps.clearGuideMarkers()` and `GoogleMaps.setGuideMarkers()` already in maps.js |

---

## Common Pitfalls

### Pitfall 1: OverlayView `_div` null on initial dimming call
**What goes wrong:** `dimNonFocusedMarkers()` is called immediately after `setGuideMarkers()`, before all OverlayView `onAdd` callbacks have fired. `m._div` is null for markers not yet added to the DOM.
**Why it happens:** `OverlayView.onAdd()` fires asynchronously after `setMap()` is called.
**How to avoid:** Check `if (!m._div) return;` inside the dimming loop. Alternatively, call dimming inside a short `setTimeout(fn, 50)` after `setGuideMarkers`.
**Warning signs:** `TypeError: Cannot set properties of null` on `m._div.style.opacity`.

### Pitfall 2: Crossfade breaks on rapid navigation
**What goes wrong:** User clicks a day card then immediately clicks another — second `renderGuide()` fires during the 150ms fade-out, resulting in double-rendering or flickering.
**Why it happens:** No guard against concurrent transitions.
**How to avoid:** Track a `_transitionInProgress` boolean flag in guide-core.js; ignore navigation calls while `true`. Or cancel the pending `setTimeout` with `clearTimeout` on re-entry.
**Warning signs:** Content flickers or appears twice in quick succession.

### Pitfall 3: Browser back bypasses crossfade
**What goes wrong:** Popstate triggers the router handler, which calls `activateDayDetail` → `renderGuide()` directly, bypassing the crossfade animation.
**Why it happens:** Router handlers were written for direct activation, not transitions.
**How to avoid:** Apply the crossfade inside `renderGuide()` itself (not just in the navigation helpers), so all paths that call `renderGuide` get the transition automatically.
**Warning signs:** Instant content swap on browser back/forward, smooth swap on in-app navigation clicks.

### Pitfall 4: Day card thumbnails never resolve
**What goes wrong:** Day cards render with `.hero-photo-loading` skeleton placeholders that never get replaced by actual images.
**Why it happens:** `_lazyLoadEntityImages` must be called explicitly after the DOM is updated. The new `renderOverview()` call site needs its own lazy-load trigger (equivalent to how guide-stops.js calls `_lazyLoadCardImages` after rendering).
**How to avoid:** After rendering the day cards grid, inside `requestAnimationFrame`, iterate over cards and call `_lazyLoadEntityImages` for each card's first stop.
**Warning signs:** Skeleton spinners persist indefinitely on day cards.

### Pitfall 5: Day card clicks silently ignored
**What goes wrong:** Clicking `.day-card-v2` elements does nothing.
**Why it happens:** `_initGuideDelegation` only registers once (guarded by `_guideDelegationReady`). If `.day-card-v2` selector is not in the existing delegation block before first call, it is never handled.
**How to avoid:** Add `e.target.closest('.day-card-v2')` branch inside the existing `root.addEventListener('click', ...)` block in `_initGuideDelegation`. Do NOT add a new listener.
**Warning signs:** No navigation occurs when clicking day cards; no console errors.

### Pitfall 6: max-height collapsible appears to snap open
**What goes wrong:** Collapsible content appears to expand instantly rather than animating smoothly.
**Why it happens:** If `max-height` is set much larger than actual content height, the animation completes in a tiny fraction of the transition duration.
**How to avoid:** Use `transition: max-height 0.5s` (longer) or use JS to read `scrollHeight` and animate to that exact height.
**Warning signs:** Toggle appears to snap instead of smoothly opening.

---

## Code Examples

### Day Card Markup (esc-safe structure)

All user data (title, drive time, etc.) must use `esc()`. Static structural text (Tag, Stopps) is safe as literals.

```
Template for renderDayCard(dp, plan):
  <div class="day-card-v2" data-day-num="{dp.day}" tabindex="0" role="button">
    <div class="day-card-v2__thumb">
      {buildHeroPhotoLoading('sm')} -- skeleton replaced by _lazyLoadEntityImages post-render
    </div>
    <div class="day-card-v2__body">
      <div class="day-card-v2__title">Tag {dp.day}: {esc(dp.title)}</div>
      <div class="day-card-v2__meta">{stopCount} Stopps · {driveHours}h Fahrt</div>
    </div>
  </div>
```

### Breadcrumb Segment Structure

```
Level 1 (day detail) segments:
  - segment 1: text "Übersicht", data-nav-level="overview", clickable
  - separator: "›"
  - segment 2: text "Tag {N}: {esc(title)}", class --active, non-clickable

Level 2 (stop detail) segments:
  - segment 1: text "Übersicht", data-nav-level="overview", clickable
  - separator: "›"
  - segment 2: text "Tag {N}", data-nav-level="day", data-day-num="{N}", clickable
  - separator: "›"
  - segment 3: text "{esc(stop.region)}", class --active, non-clickable
```

### Collapsible Section CSS Core

```css
/* In styles.css — new classes for overview collapsible */
.overview-collapsible__body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}
.overview-collapsible.is-expanded .overview-collapsible__body {
  max-height: 3000px;
}
.overview-collapsible__chevron {
  display: inline-block;
  transition: transform 0.3s;
}
.overview-collapsible.is-expanded .overview-collapsible__chevron {
  transform: rotate(180deg);
}
@media (prefers-reduced-motion: reduce) {
  .overview-collapsible__body,
  .overview-collapsible__chevron { transition-duration: 0.01ms !important; }
}
```

### Breadcrumb Bar CSS Core

```css
/* In styles.css — breadcrumb bar */
.guide-breadcrumb {
  display: flex;
  align-items: center;
  height: 48px;
  padding: 0 var(--space-md);
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky;
  top: var(--stats-bar-height, 48px);
  z-index: 10;
  gap: var(--space-sm);
}
.guide-breadcrumb__segment {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  cursor: pointer;
}
.guide-breadcrumb__segment--active {
  font-weight: 600;
  color: var(--text-primary);
  cursor: default;
}
.guide-breadcrumb__separator {
  color: var(--text-muted);
  font-size: var(--text-sm);
}
```

### Day Card Grid CSS Core

```css
/* In styles.css — day cards grid */
.day-cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}
@media (max-width: 1023px) {
  .day-cards-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 479px) {
  .day-cards-grid { grid-template-columns: 1fr; }
}
.day-card-v2 {
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
  background: var(--surface-card);
  transition: var(--lift-transition);
}
.day-card-v2:hover {
  transform: var(--lift-y);
  box-shadow: var(--lift-shadow);
}
.day-card-v2__thumb {
  height: 120px;
  overflow: hidden;
  background: var(--bg-secondary);
}
.day-card-v2__body {
  padding: var(--space-md);
}
.day-card-v2__title {
  font-size: var(--text-xl);
  font-weight: 600;
  margin-bottom: var(--space-xs);
}
.day-card-v2__meta {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single `guide.js` (all in one) | 7 modules: guide-core, guide-days, guide-stops, guide-map, guide-overview, guide-edit, guide-share | Phase 9 | Phase 10 extends individual modules without touching others |
| Tab-based navigation (stops/days/overview as separate tabs) | Three-level drill-down (overview → day → stop) | Phase 10 goal | URL routing must reflect drill level, not tab name |
| Flat markers with click-to-navigate | Same markers + dimming for non-focused stops | Phase 10 goal | New `dimNonFocusedMarkers` / `restoreAllMarkers` needed in maps.js |
| `renderOverview()` shows trip analysis inline | Trip analysis in collapsible, day cards grid on top | Phase 10 goal | Full restructure of `renderOverview()` in guide-overview.js |

---

## Open Questions

1. **`/day/` vs `/days/` URL pattern**
   - What we know: router.js already handles `/days/{n}` (plural) and navigation helpers push `/days/{n}`. UI-SPEC says `/day/{n}` (singular).
   - What's unclear: Which should win.
   - Recommendation: Use existing plural patterns (`/days/{n}`, `/stops/{n}`) — no router changes needed. Align implementation with existing routes rather than changing what works.

2. **Day card stop count and drive time computation**
   - What we know: `day_plans[i]` does NOT have explicit stop count or total drive time fields.
   - What's unclear: Are both derivable reliably?
   - Recommendation: Stop count = `_findStopsForDay(plan, dayNum).length`. Drive time = sum of `stop.drive_hours_from_prev` for those stops. Both computable from existing data; document in plan tasks.

3. **Scroll-to-top target element**
   - What we know: `renderGuide()` mutates `#guide-content`. The scrollable container may be the guide-content div or its parent.
   - What's unclear: Which element holds the scrollbar.
   - Recommendation: Set `scrollTop = 0` on both `#guide-content` and the `#travel-guide` section as a safe default. Verify in browser during implementation.

---

## Environment Availability

Step 2.6: SKIPPED — this phase is purely frontend code/CSS changes. No new external tools, CLIs, services, or runtimes are required beyond the existing Google Maps API key already in `.env`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-mock + pytest-asyncio |
| Config file | none — pytest discovered via `backend/tests/` |
| Quick run command | `cd backend && python3 -m pytest tests/ -v -x` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map

This phase is entirely frontend JavaScript. The existing pytest suite covers backend endpoints and models. Frontend-only changes (JS logic, CSS, HTML) have no pytest counterpart.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NAV-01 | Overview renders day cards grid + collapsible section | manual browser | n/a | not applicable (visual) |
| NAV-02 | Day drill-down renders day detail + map focus | manual browser | n/a | not applicable (visual) |
| NAV-03 | Stop drill-down renders stop detail + map focus | manual browser | n/a | not applicable (visual) |
| NAV-04 | Breadcrumb back-navigation restores correct level | manual browser | n/a | not applicable (visual) |
| NAV-05 | Non-focused markers dim to 0.35 opacity | manual browser | n/a | not applicable (visual) |
| NAV-06 | Browser back/forward restores drill level | manual browser | n/a | not applicable (visual) |

**All requirements are UI-only.** Backend test suite must remain green after this phase (no backend changes expected). Run full backend suite as phase gate.

### Sampling Rate

- **Per task commit:** `cd backend && python3 -m pytest tests/ -v -x` (ensure no regressions from accidental backend edits)
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Backend suite green + manual browser verification of all 6 NAV requirements

### Wave 0 Gaps

None — existing test infrastructure covers the backend. No new pytest files needed (all requirements are UI-only and verified manually in browser).

---

## Project Constraints (from CLAUDE.md)

All directives that apply to this phase:

| Directive | Impact on Phase 10 |
|-----------|--------------------|
| All user-facing text in German | Breadcrumb labels: `Übersicht`, `Tag {N}: {Titel}`, collapsible label: `Reisedetails & Analyse` |
| `esc()` for all user-content interpolation | Day card titles, stop names in breadcrumb, day titles in breadcrumb — ALL must use `esc()` |
| No `fetch()` outside api.js | Not applicable — no new API calls in this phase |
| `localStorage` keys prefixed `tp_v1_*` | Not applicable — no new localStorage usage |
| Vanilla ES2020, no build step, no frameworks | No new library imports; all new code is plain JS |
| After every change: commit as patch release and push | Applies to every task |
| Type hints on all Python function signatures | Not applicable (no Python changes) |

---

## Sources

### Primary (HIGH confidence)

- Direct code reading of `frontend/js/guide-core.js` — `renderGuide()`, `switchGuideTab()`, `_initGuideDelegation()` patterns
- Direct code reading of `frontend/js/guide-map.js` — `_guideMarkers`, `_setupGuideMap()`, `_updateMapForTab()`, marker structure
- Direct code reading of `frontend/js/maps.js` — `setGuideMarkers()`, `_guideMarkerList`, `m._stopId` at line 646, public API exports
- Direct code reading of `frontend/js/router.js` — existing route patterns for `/days/{n}` and `/stops/{n}`, all handler implementations
- `.planning/phases/10-progressive-disclosure-ui/10-UI-SPEC.md` — component dimensions, CSS class names, timing values, copywriting contract
- `.planning/phases/10-progressive-disclosure-ui/10-CONTEXT.md` — all locked decisions D-01 through D-11

### Secondary (MEDIUM confidence)

- `frontend/js/guide-days.js` — `navigateToDay()`, `_findStopsForDay()`, breadcrumb span patterns (lines 357, 393-415)
- `frontend/js/guide-stops.js` — `navigateToStop()`, existing breadcrumb span pattern (line 161)
- `frontend/js/guide-overview.js` — full `renderOverview()` structure to be replaced
- `DESIGN_GUIDELINE.md` — Apple-inspired design principles confirming opacity approach

### Tertiary (LOW confidence)

None — all findings are from direct code inspection.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies already exist in codebase
- Architecture patterns: HIGH — all patterns confirmed by reading actual source files
- Pitfalls: HIGH — all identified from specific code constructs observed (OverlayView async, delegation guard, etc.)
- URL routing: HIGH — router.js read in full, existing patterns documented

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable codebase, no external dependency changes expected)
