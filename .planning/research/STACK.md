# Stack Research

**Domain:** Progressive-disclosure travel view redesign (vanilla JS SPA)
**Researched:** 2026-03-27
**Confidence:** HIGH

> This research covers stack additions/changes needed ONLY for the progressive-disclosure travel view redesign. The existing stack (FastAPI, vanilla JS, Google Maps JS SDK, Redis, Celery, Docker) is validated and not re-evaluated.

---

## Recommended Stack

### No New Libraries Required

The progressive-disclosure redesign requires **zero new dependencies**. All needed capabilities exist in current browser APIs and the existing codebase. This is deliberate -- adding libraries to a vanilla JS project with no build step creates maintenance burden and contradicts the project's no-framework constraint.

### Core Technologies (Already Present -- Extend, Don't Replace)

| Technology | Current Use | New Use for Drill-Down | Confidence |
|------------|-------------|------------------------|------------|
| Google Maps JS SDK (raster) | `panTo()`, `fitBounds()` with padding | Animated map focus per drill-down level: overview=fitAll, day=fitDayRegion, stop=panTo+zoom | HIGH |
| CSS Custom Properties | Design system tokens in `:root` | Add transition timing tokens for drill-down animations | HIGH |
| IntersectionObserver | `_initScrollSync()` for scroll-map sync | Lazy rendering of off-screen day/stop cards | HIGH |
| `requestAnimationFrame` | Tab fade-in animation in `renderGuide()` | Coordinate DOM swap + map animation timing | HIGH |
| CSS Grid / Flexbox | Layout throughout `styles.css` | Collapsible day-card grid, expand/collapse animations via `grid-template-rows` | HIGH |
| Module-scoped state | `_activeStopId`, `_activeDayNum` in `guide.js` | Add `_drillLevel` for 3-level state machine | HIGH |

### New CSS Techniques (Native Browser APIs, Zero Dependencies)

| Technique | Purpose | Why This One | Browser Support | Confidence |
|-----------|---------|--------------|-----------------|------------|
| `document.startViewTransition()` | Smooth cross-fade between overview/day/stop views | Native browser API. Replaces the manual opacity/transform fade already in `renderGuide()`. Graceful fallback: instant swap (current behavior). | Chrome 111+, Edge 111+, Safari 18+, Firefox 133+ -- all major browsers in 2026. | HIGH |
| CSS `grid-template-rows: 0fr/1fr` transition | Animate card expand/collapse for day details, stop sections | Cross-browser. No height measurement needed. Wrap content in a grid child with `min-height: 0` and toggle between `0fr` (collapsed) and `1fr` (expanded). | Chrome 117+, Firefox 117+, Safari 17.2+, Edge 117+ | HIGH |
| `interpolate-size: allow-keywords` | Animate `height: 0` to `height: auto` | Pure CSS, cleaner than grid hack. Declare on `:root` once. | Chromium-only (Chrome 129+, Edge 129+). Firefox/Safari lack support. **Progressive enhancement only** -- use `grid-template-rows` as primary. | MEDIUM |
| `scroll-behavior: smooth` + `scrollIntoView()` | Auto-scroll content panel when drilling into a day/stop | Already partially used in `_scrollToAndHighlightCard()`. Extend to drill-down navigation. | All modern browsers. | HIGH |
| CSS `will-change: transform, opacity` | GPU-accelerate card transitions during drill-down | Apply via class during animation only (not permanently). Prevents layout thrashing on expand/collapse. | All modern browsers. | HIGH |

### Map Animation Strategy

| Drill-Down Level | Map Behavior | Implementation | Existing Code |
|------------------|-------------|----------------|---------------|
| Overview (all stops) | Fit all stops with padding | `GoogleMaps.fitAllStops(plan)` | **Already exists** in `_updateMapForTab()` |
| Day focus | Fit that day's stops into view | **New:** `GoogleMaps.fitDayStops(dayStops)` -- build `LatLngBounds` from day's stop coordinates, call `fitBounds()` with padding | `fitBounds()` already used throughout |
| Stop focus | Pan + zoom to single stop | `GoogleMaps.panToStop(stopId)` + set zoom to ~13 | **Already exists** in `maps.js:720`. Add optional zoom parameter. |

**Key insight:** Google Maps `panTo()` already animates smoothly on raster maps. `fitBounds()` also animates by default. No animation library or vector map migration needed. The existing `panToStop()` does exactly what stop-level drill-down requires.

### Lazy DOM Rendering Strategy

| Pattern | When to Use | Implementation | Confidence |
|---------|-------------|----------------|------------|
| Render-on-demand | Day cards below fold in overview | Render placeholder skeletons (existing pattern from accommodation loading). Replace with real content when IntersectionObserver fires. | HIGH |
| DocumentFragment batching | Initial overview render with many day summaries | Build all day summary cards in a DocumentFragment, append once. Single reflow instead of N. | HIGH |
| Deferred detail content | Stop detail sections (activities, restaurants, accommodation) | Render header/hero immediately, populate detail sections on expand. Already done for images via `_lazyLoadEntityImages()`. | HIGH |

**Virtual scroll is NOT needed.** A trip has at most ~15 stops and ~14 days. Total DOM element count stays under 200 even fully expanded. The real bottleneck is image loading and per-stop map initialization, both of which are already lazy-loaded.

---

## Integration Points

### Existing Code to Extend (Not Replace)

| File | Current Pattern | Extension for Drill-Down |
|------|----------------|--------------------------|
| `guide.js` `renderGuide()` | 5-tab switching (`overview`, `stops`, `days`, `calendar`, `budget`) with `innerHTML` swap | Replace tab paradigm with drill-down state: `{level: 'overview'\|'day'\|'stop', dayNum?, stopId?}`. Keep calendar/budget as secondary tabs. |
| `guide.js` `_updateMapForTab()` | Always calls `fitAllStops()` regardless of tab | Make map focus level-aware: overview=fitAll, day=fitDayRegion, stop=panToStop+zoom |
| `guide.js` `renderOverview()` | Static stat cards + route line + day plan CTA | Replace with clickable compact day cards that trigger day drill-down |
| `guide.js` `renderDaysOverview()` | Lists all days in flat layout | Convert to focused single-day view with prev/next navigation + back-to-overview |
| `guide.js` `renderStopDetail()` | Full stop detail page (accessed via stops tab) | Reuse as-is -- entry point changes from tab to day drill-down click |
| `maps.js` `panToStop()` | Pans to stop at current zoom level | Add optional `zoom` parameter for stop-level focus (default ~13) |
| `maps.js` | No day-region fitting capability | Add `fitDayStops(stops)` method using `LatLngBounds` |
| `router.js` | Routes: `/travel/{id}/stops`, `/travel/{id}/days` | Add: `/travel/{id}/day/{n}`, `/travel/{id}/stop/{id}` for deep-linkable drill-down |
| `styles.css` | Tab fade-in: `opacity 0.2s ease, transform 0.2s ease` | Add drill-down transition classes, `grid-template-rows` expand/collapse, View Transition fallback styles |

### State Machine

```
Overview (all stops on map, compact day cards)
    |
    v  click day card
Day Detail (day's stops highlighted on map, activities/restaurants/schedule)
    |
    v  click stop within day
Stop Detail (stop zoomed on map, full accommodation/activity/restaurant details)
    |
    ^  back button returns to parent level (stop->day, day->overview)
```

State lives in existing `guide.js` module variables:
- `_drillLevel` (new): `'overview'` | `'day'` | `'stop'`
- `_activeDayNum` (existing): which day is focused
- `_activeStopId` (existing): which stop is focused

URL reflects state for deep-linking and browser back button support.

---

## CSS Custom Properties to Add

```css
:root {
  /* Drill-down transition timing */
  --drill-transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  --drill-fade: opacity 0.2s ease, transform 0.2s ease;
  --card-expand: grid-template-rows 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  /* Progressive enhancement: animate to height:auto in Chromium */
  interpolate-size: allow-keywords;
}
```

## View Transition API Usage Pattern

```javascript
function drillTo(level, params) {
  if (document.startViewTransition) {
    document.startViewTransition(() => _renderLevel(level, params));
  } else {
    _renderLevel(level, params);  // Fallback: instant swap (current behavior)
  }
}
```

No polyfill needed. The fallback IS the existing behavior (direct innerHTML swap with opacity fade).

## Grid Row Expand/Collapse Pattern

```css
.day-card-details {
  display: grid;
  grid-template-rows: 0fr;
  transition: var(--card-expand);
  overflow: hidden;
}
.day-card-details.expanded {
  grid-template-rows: 1fr;
}
.day-card-details > .inner {
  min-height: 0;  /* Required for grid row animation to work */
}
```

Cross-browser pattern for animating expand/collapse without measuring content height. The `.inner` wrapper with `min-height: 0` is essential -- without it, the content won't collapse below its intrinsic height.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `document.startViewTransition()` | Manual opacity/transform fade (current approach) | Never -- View Transitions degrade gracefully to instant swap. The manual fade is already the fallback. Strictly better. |
| CSS `grid-template-rows: 0fr/1fr` | `max-height` transition | Never -- `max-height` requires guessing a maximum value. Too high = delayed collapse animation. Too low = content clipped. `grid-template-rows` has neither problem. |
| CSS `grid-template-rows: 0fr/1fr` | `interpolate-size: allow-keywords` | When Firefox/Safari add support. Currently Chromium-only, so it can only be a progressive enhancement. |
| IntersectionObserver lazy render | Virtual scroll library | Never for this project. Max ~15 stops / ~14 days does not justify virtual scroll complexity. |
| Existing Google Maps `panTo()`/`fitBounds()` | Vector maps + `flyCameraTo()` | If wanting cinematic 3D camera flights. Requires `mapId`, Cloud Console map style config, different marker API (AdvancedMarkerElement). Massive migration for marginal visual improvement. |
| Module-scoped state variables | State management library | Never -- violates no-framework constraint. Three variables (`_drillLevel`, `_activeDayNum`, `_activeStopId`) handle a 3-level drill-down. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| GSAP / anime.js / Motion One | 15-50KB for effects CSS handles natively. Card expand/collapse + opacity fades do not need a JS animation library. | CSS transitions + `document.startViewTransition()` |
| Virtual scroll (any library) | Trip data is tiny (max ~15 stops, ~14 days). Zero performance benefit, significant complexity cost. | IntersectionObserver lazy rendering for images/maps |
| Any JS framework or web components | Project constraint: vanilla JS, no build step. Adding lit-html or similar would be scope creep. | Extend existing `renderX()` functions in `guide.js` |
| Google Maps vector map migration | Requires `mapId` setup, Cloud Console config, AdvancedMarkerElement migration (current code uses OverlayView for custom markers). 600+ lines of maps.js to rewrite. | Keep raster maps. `panTo()` and `fitBounds()` already animate smoothly. |
| `max-height` transition for expand/collapse | Timing is always wrong. Must hardcode a max value: too high = collapse appears delayed, too low = content clipped. Visible jump artifacts. | CSS `grid-template-rows: 0fr` to `1fr` transition |
| `@starting-style` for entry animations | Chrome 117+ only as of 2026. Safari/Firefox support is inconsistent. | Classic `requestAnimationFrame` + class toggle pattern (already proven in codebase). |
| Swiper/carousel libraries for day navigation | CSS `scroll-snap-type: x mandatory` handles horizontal day card scrolling natively. 0 bytes vs 30KB+. | CSS scroll-snap |

---

## Version Compatibility

| Feature | Chrome | Firefox | Safari | Edge | Primary/Enhancement |
|---------|--------|---------|--------|------|---------------------|
| `document.startViewTransition()` | 111+ | 133+ | 18+ | 111+ | Primary -- graceful fallback to instant swap |
| `grid-template-rows: 0fr/1fr` transition | 117+ | 117+ | 17.2+ | 117+ | Primary -- expand/collapse animation |
| `interpolate-size: allow-keywords` | 129+ | Not supported | Not supported | 129+ | Enhancement only -- Chromium bonus |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 15+ | Primary -- already in codebase |
| CSS Container Queries | 105+ | 110+ | 16+ | 105+ | Available but not required for drill-down (existing responsive approach sufficient) |
| CSS `scroll-snap` | 69+ | 68+ | 11+ | 79+ | Primary -- horizontal day card navigation |

---

## Installation

```bash
# No new backend dependencies
# No new frontend dependencies
# No new CDN scripts

# Zero changes to requirements.txt
# Zero changes to index.html script tags
# Zero changes to Docker images
```

Everything needed is already in the browser or already loaded.

---

## Sources

- [MDN: View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API) -- same-document API spec, browser support matrix (HIGH confidence)
- [Can I Use: View Transitions (single-document)](https://caniuse.com/view-transitions) -- Chrome 111+, Safari 18+, Firefox 133+ confirmed (HIGH confidence)
- [Chrome Developers: Animate to height auto](https://developer.chrome.com/docs/css-ui/animate-to-height-auto) -- `interpolate-size` documentation, Chromium-only status (HIGH confidence)
- [MDN: interpolate-size](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/interpolate-size) -- Chromium-only confirmed March 2026 (HIGH confidence)
- [Google Maps: Move Camera Easing](https://developers.google.com/maps/documentation/javascript/examples/move-camera-ease) -- camera animation limited to vector maps / 3D (MEDIUM confidence)
- [Google Maps: panTo issue tracker](https://issuetracker.google.com/issues/229662872) -- panTo animation behavior on raster maps confirmed (MEDIUM confidence)
- Codebase analysis: `frontend/js/maps.js` lines 720-750 (`panToStop`), `frontend/js/guide.js` lines 72-145 (`renderGuide`, tab switching, fade animation), `frontend/styles.css` lines 1-80 (design system tokens) -- verified existing patterns (HIGH confidence)
- [CSS-Tricks: Performant Expandable Animations](https://css-tricks.com/performant-expandable-animations-building-keyframes-on-the-fly/) -- grid-template-rows pattern (HIGH confidence)

---
*Stack research for: Progressive-disclosure travel view redesign*
*Researched: 2026-03-27*
