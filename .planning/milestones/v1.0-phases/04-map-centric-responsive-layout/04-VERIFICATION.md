---
phase: 04-map-centric-responsive-layout
verified: 2026-03-26T00:00:00Z
status: human_needed
score: 17/17 must-haves verified
re_verification: false
human_verification:
  - test: "Open an existing saved travel in the browser on a desktop viewport (>= 1100px)"
    expected: "Map occupies fixed left 58% of the screen; content panel on the right scrolls independently; switching tabs (Stopps, Tage, Kalender, Budget) keeps the map visible without flicker or re-creation"
    why_human: "CSS fixed-panel layout and persistent map lifecycle cannot be verified programmatically"
  - test: "Resize browser to 375px width (mobile) or use DevTools mobile simulation"
    expected: "Map appears as a sticky strip at the top (~30vh); content scrolls below it; tab bar scrolls horizontally; all tap targets appear large enough (>= 44px)"
    why_human: "Responsive layout and touch-target sizing require visual/interactive browser testing"
  - test: "On the Stopps tab, inspect stop cards"
    expected: "Each card shows a 16:9 photo on the left (120px), stop number badge, region name, drive time, nights, tag pills in accent color, and a 2-line-clamped teaser. Remove / Replace / Drag icon buttons are always visible at the card bottom-right."
    why_human: "Card photo lazy-loading, visual tag pill rendering, and icon button visibility require browser observation"
  - test: "On the Tage tab, click a day header"
    expected: "The row expands inline revealing the day title, description, and a time-block schedule list. Clicking again collapses it. Only one day is open at a time."
    why_human: "Expand/collapse animation and single-open behaviour require interactive testing"
  - test: "On the Ubersicht tab, inspect the area above the tabs"
    expected: "Four stat pills appear showing Tage, Stopps, km, and Budget values. Budget pill turns warm/red colour when budget is negative."
    why_human: "Stats bar rendering and conditional colour require visual inspection"
  - test: "Click a numbered map marker"
    expected: "Content panel scrolls to the corresponding stop card; the card receives a left accent border highlight; the marker grows and changes to the accent colour"
    why_human: "Bidirectional map-card sync requires interactive browser testing"
  - test: "Scroll through stop cards slowly"
    expected: "As each card crosses the 60% visibility threshold the map auto-pans to that stop's coordinates. Panning pauses while the user drags the map."
    why_human: "IntersectionObserver behaviour and map-drag suppression require interactive testing"
  - test: "Click an empty area on the map (not a marker)"
    expected: "A popup appears near the click showing a reverse-geocoded place name and a 'Stopp hier hinzufuegen?' button. Pressing Escape or clicking elsewhere dismisses the popup."
    why_human: "Reverse-geocode call, popup positioning, and Escape/outside-click dismissal require interactive testing"
  - test: "Click the sidebar toggle chevron button on the left edge of the map panel"
    expected: "A 240px overlay slides out from the left listing all route stops by number and name. Clicking a stop pans the map and collapses the overlay. Clicking the map background also collapses it. Overlay is absent on mobile."
    why_human: "Sidebar overlay slide animation, click-outside-to-close, and mobile hiding require interactive browser testing"
---

# Phase 4: Map-Centric Responsive Layout Verification Report

**Phase Goal:** Map-centric responsive layout redesign with split-panel layout, persistent map, stop cards, day timeline, stats bar, click-to-add-stop, and mobile responsiveness.
**Verified:** 2026-03-26
**Status:** human_needed — all automated checks passed; 9 items require browser verification
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | TravelStop model accepts tags, teaser, and highlights fields | VERIFIED | `backend/models/travel_response.py` lines 96-98: `tags: List[str] = []`, `teaser: Optional[str] = None`, `highlights: List[str] = []` |
| 2 | Existing saved travels without new fields load without errors (Pydantic defaults) | VERIFIED | All three fields carry defaults; 268 backend tests pass with no regressions |
| 3 | Guide view HTML has split-panel structure with separate map panel and content panel | VERIFIED | `frontend/index.html` lines 530-544: `div.guide-split-panel` > `div.guide-map-panel` + `div.guide-content-panel` |
| 4 | On desktop (>=1100px), map panel is fixed at 58% width, content panel scrolls at 42% | VERIFIED | `frontend/styles.css` lines 1607-1637: `position: fixed; width: 58%` / `margin-left: 58%; width: 42%` |
| 5 | On tablet (768-1099px), panels are 50/50 | VERIFIED | `frontend/styles.css` line 1640: `@media (max-width: 1099px) and (min-width: 768px)` with `width: 50%` on both panels |
| 6 | On mobile (<768px), map is sticky top strip at 30vh, content is full-width below | VERIFIED | `frontend/styles.css` lines 1646-1662: `position: sticky; height: 30vh; width: 100%` |
| 7 | Map persists across tab switches without being destroyed and recreated | VERIFIED | `maps.js:568` `initPersistentGuideMap` reuses `_guideMap` if `getDiv().isConnected`; map lives in fixed HTML panel outside `#guide-content` |
| 8 | Map shows numbered circle markers at each stop (28px dark circles, white numbers) | VERIFIED | `maps.js:610` `setGuideMarkers`; `styles.css:5530` `.guide-marker-num { width: 28px; height: 28px; background: #2D2B3D; color: white; }` |
| 9 | Driving route is rendered as a black polyline (not blue) | VERIFIED | `maps.js:656` `strokeColor: '#2D2B3D', strokeWeight: 3, strokeOpacity: 1.0` |
| 10 | Ferry segments render as dashed black polyline | VERIFIED | `maps.js:673-677` dashed pattern via icon array with `strokeColor: '#2D2B3D'` |
| 11 | Clicking a map marker scrolls the content panel to the corresponding card | VERIFIED | `guide.js:1678` `_onMarkerClick` → `_scrollToAndHighlightCard`; card scrolled into view with `scrollIntoView({ behavior: 'smooth' })` |
| 12 | Map auto-fits all stops when switching tabs | VERIFIED | `guide.js:1672` `_updateMapForTab` calls `GoogleMaps.fitAllStops(plan)` after every tab switch |
| 13 | Stops tab shows compact row cards with 16:9 photo left, structured info right | VERIFIED | `guide.js:1032` `renderStopCard`; `styles.css:1889-1896` `.stop-card-photo { width: 120px; aspect-ratio: 16 / 9 }` |
| 14 | Each card shows stop number badge, name, drive time, nights, tags pills, teaser description | VERIFIED | `guide.js:1032-1073` renders `.stop-num-badge`, stop name, `.stop-card-meta`, `.stop-card-tags`, `.stop-card-desc` |
| 15 | Edit controls (remove, reorder, replace) are always visible as icon row on each card | VERIFIED | `guide.js:1032-1073` `.stop-card-actions` rendered unconditionally (remove conditionally only when `totalStops > 1`); `styles.css:1982` no `display:none` |
| 16 | Stats bar at top of overview tab shows 4 pills: Tage, Stopps, Distanz, Budget | VERIFIED | `guide.js:1007` `renderStatsBar`; wired to `#guide-stats-bar` at `guide.js:43-50`; shows on `activeTab === 'overview'` only |
| 17 | Day timeline shows expandable day cards in a vertical layout with left-edge line | VERIFIED | `guide.js:593-643` `renderDaysOverview` produces `div.day-timeline`; `styles.css:4304` `::before` pseudo-element draws the 2px vertical line |

**Score: 17/17 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/models/travel_response.py` | TravelStop with tags, teaser, highlights fields | VERIFIED | Lines 96-98 contain all three fields with correct types and defaults |
| `backend/tests/test_models.py` | Tests for new TravelStop fields | VERIFIED | `test_travel_stop_tags_teaser` at line 514; 268 tests pass |
| `frontend/index.html` | Split-panel guide layout HTML structure | VERIFIED | `guide-split-panel`, `guide-map-panel`, `guide-content-panel`, `guide-stats-bar`, `sidebar-overlay`, `role="tablist"` all present |
| `frontend/styles.css` | Split-panel CSS with responsive breakpoints, stop cards, day timeline | VERIFIED | All required classes present: `guide-map-panel`, `guide-content-panel`, `stop-card-row`, `stop-card-photo`, `stop-tag-pill`, `day-timeline`, `day-timeline-node`, `day-expand-chevron`, `overlay-node`, `guide-marker-num` |
| `frontend/js/maps.js` | Persistent guide map, numbered markers, black polyline | VERIFIED | All 7 new methods present and exported: `initPersistentGuideMap`, `getGuideMap`, `clearGuideMarkers`, `setGuideMarkers`, `highlightGuideMarker`, `panToStop`, `fitAllStops`, `enableClickToAdd` |
| `frontend/js/guide.js` | Map initialization, tab switch calls updateMapForTab, stop cards, stats bar, click-to-add, day timeline | VERIFIED | All required functions present: `_setupGuideMap`, `_updateMapForTab`, `_onMarkerClick`, `_scrollToAndHighlightCard`, `_initScrollSync`, `renderStopCard`, `renderStatsBar`, `_onCardClick`, `_lazyLoadCardImages`, `renderDaysOverview` with day-timeline, `_toggleDayExpand`, `_onMapClickToAdd`, `_showClickToAddPopup`, `_confirmClickToAdd`, `_hideClickToAddPopup`, `_haversineKm` |
| `frontend/js/sidebar.js` | Sidebar overlay toggle for map panel | VERIFIED | `toggleSidebarOverlay`, `_populateSidebarOverlay`, `_onOverlayNodeClick` at lines 378-437 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `frontend/index.html` | `frontend/styles.css` | CSS class names `guide-split-panel`, `guide-map-panel`, `guide-content-panel` | WIRED | All three class names used in HTML and defined in CSS |
| `frontend/js/guide.js` | `frontend/js/maps.js` | `GoogleMaps.initPersistentGuideMap` + `GoogleMaps.updateMapForTab` | WIRED | `guide.js:1644` calls `initPersistentGuideMap`; `guide.js:1674` calls `fitAllStops` (the update function) |
| `frontend/js/maps.js` | `frontend/js/guide.js` | marker click calls `_scrollToAndHighlightCard` | WIRED | `maps.js:610` `setGuideMarkers` receives `onMarkerClick` callback; `guide.js:1646` passes `_onMarkerClick` which calls `_scrollToAndHighlightCard` at line 1681 |
| `frontend/js/guide.js` | `frontend/js/maps.js` | card click calls `GoogleMaps.highlightGuideMarker` + `GoogleMaps.panToStop` | WIRED | `guide.js:1124-1125` in `_onCardClick` |
| `frontend/js/guide.js` | `frontend/js/maps.js` | `GoogleMaps.enableClickToAdd` called in `_setupGuideMap` | WIRED | `guide.js:1650` |
| `frontend/js/guide.js` | add-stop API | `_doAddStopFromMap` (variant of `_doAddStop`) | WIRED | `guide.js:2597` `_confirmClickToAdd` calls `_doAddStopFromMap` which calls the add-stop API using `travelId` |
| `frontend/js/sidebar.js` | `frontend/index.html` | `#sidebar-overlay` element | WIRED | `sidebar.js:378` `toggleSidebarOverlay` reads `document.getElementById('sidebar-overlay')` which exists in index.html line 534 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `guide.js renderStopCard` | `stop.tags`, `stop.teaser` | `TravelStop` model from `S.result.stops` | Yes — fields populated from StopOption during route building | FLOWING |
| `guide.js renderStatsBar` | `plan.stops`, `plan.total_days` | `S.result` (full plan from API) | Yes — computed from actual stop data | FLOWING |
| `guide.js renderDaysOverview` | `plan.day_plans` | `S.result.day_plans` | Yes — generated by DayPlannerAgent and stored in travel record | FLOWING |
| `maps.js setGuideMarkers` | `plan.stops[].lat/lng` | `S.result.stops` | Yes — coordinates from geocoding during route planning | FLOWING |
| `guide.js _onMapClickToAdd` | `latLng` from map click | Google Maps Geocoder reverse geocode | Yes — live API call to Google Geocoding | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend tests pass (including new TravelStop fields) | `cd backend && python3 -m pytest tests/ -v` | 268 passed, 1 warning | PASS |
| `test_travel_stop_tags_teaser` included in test run | `grep "test_travel_stop_tags_teaser" backend/tests/test_models.py` | Found at line 514 | PASS |
| Split-panel CSS classes exist in HTML | `grep "guide-split-panel\|guide-map-panel" frontend/index.html` | Both found | PASS |
| Map panel is fixed at 58% on desktop | CSS check | `position: fixed; width: 58%` at styles.css:1608-1611 | PASS |
| Mobile sticky map at 30vh | CSS check | `position: sticky; height: 30vh` at styles.css:1650-1654 | PASS |
| All required maps.js methods exported | `grep "initPersistentGuideMap\|enableClickToAdd" frontend/js/maps.js` | All 8 new methods in return object at lines 773-787 | PASS |
| XSS safety: place name uses textContent not innerHTML | `_showClickToAddPopup` inspected | `nameEl.textContent = placeName` at guide.js:2491 — safe | PASS |
| Day timeline aria attributes | HTML inspection | `aria-expanded="false"` on `.day-timeline-header`, `role="list"` on container | PASS |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| UIR-01 | 04-01, 04-02, 04-06 | Desktop layout uses map-centric split-panel with map as hero | SATISFIED | `guide-split-panel` HTML + CSS; fixed 58/42 desktop split; `initPersistentGuideMap` reuses map across tabs |
| UIR-02 | 04-01, 04-04, 04-06 | Layout is fully responsive — comfortable on phone browsers | SATISFIED | Mobile CSS breakpoint at 767px; sticky 30vh map strip; `100dvh` fallback; cooperative gesture handling on mobile; 44px touch targets in mobile media query |
| UIR-03 | 04-03, 04-06 | Stops presented as visual cards with photos, key facts, travel style tags | SATISFIED | `renderStopCard` with `.stop-card-photo` (120px, 16:9), `.stop-num-badge`, `.stop-card-tags`, `.stop-card-desc`; lazy photo loading via `_lazyLoadCardImages` |
| UIR-04 | 04-04, 04-06 | Day-by-day timeline is interactive — scrollable with expandable day details | SATISFIED | `renderDaysOverview` produces `div.day-timeline` with `_toggleDayExpand` expand/collapse; time blocks rendered inline via `renderDayTimeBlocks` |
| UIR-05 | 04-03, 04-06 | Dashboard overview shows key trip stats (total days, stops, distance, budget remaining) | SATISFIED | `renderStatsBar` produces 4 `.stat-pill` elements (Tage, Stopps, km, Budget); wired to `#guide-stats-bar` on overview tab |
| UIR-06 | 04-02, 04-05, 04-06 | Map and content stay synchronized; selecting stop highlights on map and vice versa; click-to-add | SATISFIED | Bidirectional: marker click → `_onMarkerClick` → `_scrollToAndHighlightCard`; card scroll → `IntersectionObserver` → `GoogleMaps.panToStop`; map click → `_onMapClickToAdd` → reverse geocode popup → `_confirmClickToAdd` → `_doAddStopFromMap` |

All 6 requirement IDs declared across plans are covered. No orphaned requirements detected in REQUIREMENTS.md for Phase 4.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `guide.js _confirmClickToAdd` | Calls `_doAddStopFromMap` instead of `_doAddStop` — the plan specified `_doAddStop` but implementation uses a dedicated wrapper | Info | No functional impact; `_doAddStopFromMap` at line 2601 calls the same API endpoint |
| `guide.js renderDaysOverview` | `time-block-list` CSS class from plan spec was not added to `styles.css` — time blocks use the existing pre-Phase-4 `.time-block` class | Info | Visual rendering still works via pre-existing `.time-block` styles; no broken display |

No blocker anti-patterns found. No stub or empty-implementation patterns detected in Phase 4 code.

---

### Human Verification Required

All automated checks (268 tests, CSS presence, function existence, key link wiring, data-flow tracing) passed. The following items require browser testing because they involve visual rendering, CSS layout behaviour, animation, touch interaction, and live Google Maps API behaviour.

**1. Desktop Split-Panel Layout (UIR-01)**
- **Test:** Open a saved travel at `/travel/{id}` on a desktop browser at >= 1100px width
- **Expected:** Map fixed on left at ~58%, content panel on right scrolls; switching tabs keeps map visible without flicker
- **Why human:** CSS `position: fixed` layout and map lifecycle require browser rendering to verify

**2. Mobile Responsive Layout (UIR-02)**
- **Test:** Set browser width to 375px or use DevTools mobile simulation
- **Expected:** Map is a sticky strip at ~30vh; content scrolls below it; tab bar scrolls horizontally; touch targets feel large enough
- **Why human:** Responsive breakpoints, sticky positioning, and touch ergonomics require physical/simulated device testing

**3. Stop Cards Visual Rendering (UIR-03)**
- **Test:** Navigate to Stopps tab on a travel with research data
- **Expected:** 16:9 photo loads on left (120px); number badge, tags pills in accent colour, teaser text visible; Remove/Replace/Drag icons visible at bottom-right of each card
- **Why human:** Lazy photo loading and CSS visual details require browser observation

**4. Day Timeline Expand/Collapse (UIR-04)**
- **Test:** Navigate to Tage tab and click a day header
- **Expected:** Day expands inline with title, description, time-block schedule; only one day open at a time; expand/collapse animated
- **Why human:** Expand/collapse animation and single-open accordion behaviour require interactive testing

**5. Stats Bar Values (UIR-05)**
- **Test:** Navigate to Ubersicht tab
- **Expected:** Four stat pills appear above the tabs showing actual trip numbers (Tage, Stopps, km, Budget in CHF); Budget pill turns warm/red when over budget
- **Why human:** Conditional colour for negative budget requires a travel with exceeded budget to test fully

**6. Map Marker Click — Card Sync (UIR-06)**
- **Test:** Click a numbered map marker
- **Expected:** Content panel scrolls to the card; card gets left accent border; marker enlarges to accent colour
- **Why human:** Google Maps OverlayView marker click events require live map rendering

**7. Card Scroll — Map Auto-Pan (UIR-06)**
- **Test:** On Stopps tab, scroll slowly through stop cards
- **Expected:** Map pans to the stop whose card is most visible; panning stops while user drags the map
- **Why human:** IntersectionObserver behaviour and drag-suppression require interactive testing

**8. Click-to-Add Popup (UIR-06)**
- **Test:** Click an empty area on the map (not on a marker)
- **Expected:** Popup appears with reverse-geocoded place name and "Stopp hier hinzufuegen?" button; Escape or click-away dismisses; confirming starts add-stop flow
- **Why human:** Geocoder API call, popup positioning, and Escape/outside-click dismissal require live browser testing

**9. Sidebar Overlay Toggle**
- **Test:** Click the toggle button on the left edge of the map panel
- **Expected:** Overlay slides out showing route stop list; clicking a stop pans map and collapses overlay; clicking map background collapses overlay; overlay is absent on mobile
- **Why human:** Slide animation, click-outside-to-close, and mobile hiding require interactive browser testing

---

### Gaps Summary

No automated gaps found. All 17 observable truths pass all four verification levels (exists, substantive, wired, data-flowing). The backend test suite is fully green (268 tests). One implementation detail differs from the plan spec (`_doAddStopFromMap` wrapper instead of direct `_doAddStop`), but this is a non-breaking refinement with identical API behaviour. The `time-block-list` CSS class from Plan 04 was not added but the existing `.time-block` class serves the same purpose.

The phase is blocked only on visual/interactive human verification. All 6 UIR requirements have complete code implementations.

---

_Verified: 2026-03-26_
_Verifier: Claude (gsd-verifier)_
