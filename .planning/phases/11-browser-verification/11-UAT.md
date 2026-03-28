---
status: in-progress
phase: 11-browser-verification
source:
  - .planning/phases/10-progressive-disclosure-ui/10-VERIFICATION.md
  - .planning/milestones/v1.0-phases/04-map-centric-responsive-layout/04-VERIFICATION.md
  - .planning/milestones/v1.0-phases/03-route-editing/03-VERIFICATION.md
started: "2026-03-27T22:35:00Z"
updated: "2026-03-28T00:00:00Z"
---

# Phase 11: Browser Verification UAT

## Current Test

[all items tested]

## Tests

### A. Progressive Disclosure (Phase 10)

#### A1. Three-level drill-down visual flow
test: "Open a saved travel plan. Verify: (a) overview shows trip summary header + day cards grid in 3-up layout; (b) click a day card — content crossfades to day detail in ~400ms total; (c) click a stop row — crossfades to stop detail; (d) breadcrumb shows 'Uebersicht > Tag N: Title' at day level and 'Uebersicht > Tag N > StopName' at stop level; (e) click 'Uebersicht' in breadcrumb — crossfades back to overview with breadcrumb hidden"
expected: "Smooth crossfades (not instant), correct breadcrumb text at each level, overview shows day cards on return"
origin: "Phase 10 — 10-VERIFICATION.md"
result: pass
notes: ""

#### A2. Map marker dimming and focus
test: "While viewing a day detail, observe the map. Navigate to a stop detail, observe the map. Return to overview, observe the map."
expected: "Day view — map zooms to show that day's stops with 48px padding, other stops dim to ~35% opacity with 0.3s transition. Stop view — map pans to stop, other markers dim. Overview — all markers restore to full opacity."
origin: "Phase 10 — 10-VERIFICATION.md"
result: fail
notes: "Map zooms in way too much on day drill-down. Stop markers/POIs are not visible when viewing a day detail."

#### A3. Browser back/forward navigation with crossfade
test: "Navigate: overview -> day 3 -> stop 2 -> use browser back -> back again -> use browser forward."
expected: "Each back/forward uses crossfade transition, breadcrumb updates correctly, URL changes between /travel/{id}, /travel/{id}/days/3, /travel/{id}/stops/2. No console errors during rapid clicking."
origin: "Phase 10 — 10-VERIFICATION.md"
result: pass
notes: ""

#### A4. Mobile responsive day cards grid
test: "Open overview in browser DevTools at viewport widths 1200px, 800px, 400px."
expected: "1200px -> 3 columns; 800px -> 2 columns; 400px -> 1 column"
origin: "Phase 10 — 10-VERIFICATION.md"
result: pass
notes: ""

#### A5. Collapsible Reisedetails section
test: "On the overview tab, click 'Reisedetails & Analyse' button."
expected: "Chevron rotates 180 deg, section smoothly expands via max-height transition (0.5s cubic-bezier); click again — smoothly collapses. aria-expanded attribute on button reflects state."
origin: "Phase 10 — 10-VERIFICATION.md"
result: pass
notes: ""

### B. Layout and Responsive (Phase 4)

#### B1. Desktop split-panel layout
test: "Open an existing saved travel in the browser on a desktop viewport (>= 1100px)"
expected: "Map occupies fixed left 58% of the screen; content panel on the right scrolls independently; switching tabs (Stopps, Tage, Kalender, Budget) keeps the map visible without flicker or re-creation"
origin: "Phase 4 — 04-VERIFICATION.md"
result: fail
notes: "Map is way too big. Content panel is cut off. Unused space on the right side. The 58/42 split-panel layout is not rendering correctly."

#### B2. Mobile responsive layout
test: "Resize browser to 375px width (mobile) or use DevTools mobile simulation"
expected: "Map appears as a sticky strip at the top (~30vh); content scrolls below it; tab bar scrolls horizontally; all tap targets appear large enough (>= 44px)"
origin: "Phase 4 — 04-VERIFICATION.md"
result: pass
notes: "Mobile view tested and working correctly."

#### B3. Sidebar overlay toggle
test: "Click the sidebar toggle chevron button on the left edge of the map panel"
expected: "A 240px overlay slides out from the left listing all route stops by number and name. Clicking a stop pans the map and collapses the overlay. Clicking the map background also collapses it. Overlay is absent on mobile."
origin: "Phase 4 — 04-VERIFICATION.md"
result: pass
notes: "Sidebar found and functional after locating the small toggle chevron."

### C. Stop Cards and Stats (Phase 4)

#### C1. Stop cards visual rendering
test: "On the Stopps tab, inspect stop cards"
expected: "Each card shows a 16:9 photo on the left (120px), stop number badge, region name, drive time, nights, tag pills in accent color, and a 2-line-clamped teaser. Remove / Replace / Drag icon buttons are always visible at the card bottom-right."
origin: "Phase 4 — 04-VERIFICATION.md"
result: pass
notes: "Stop cards look great."

#### C2. Day timeline expand/collapse
test: "On the Tage tab, click a day header"
expected: "The row expands inline revealing the day title, description, and a time-block schedule list. Clicking again collapses it. Only one day is open at a time."
origin: "Phase 4 — 04-VERIFICATION.md"
result: pass
notes: "Day timeline expand/collapse works correctly."

#### C3. Stats bar values
test: "On the Uebersicht tab, inspect the area above the tabs"
expected: "Four stat pills appear showing Tage, Stopps, km, and Budget values. Budget pill turns warm/red colour when budget is negative."
origin: "Phase 4 — 04-VERIFICATION.md"
result: fail
notes: "Stats bar font is way too big."

### D. Map Interaction (Phase 4)

#### D1. Map marker click -> card sync
test: "Click a numbered map marker"
expected: "Content panel scrolls to the corresponding stop card; the card receives a left accent border highlight; the marker grows and changes to the accent colour"
origin: "Phase 4 — 04-VERIFICATION.md"
result: pass
notes: ""

#### D2. Card scroll -> map auto-pan
test: "Scroll through stop cards slowly"
expected: "As each card crosses the 60% visibility threshold the map auto-pans to that stop's coordinates. Panning pauses while the user drags the map."
origin: "Phase 4 — 04-VERIFICATION.md"
result: pass
notes: ""

#### D3. Click-to-add popup
test: "Click an empty area on the map (not a marker)"
expected: "A popup appears near the click showing a reverse-geocoded place name and a 'Stopp hier hinzufuegen?' button. Pressing Escape or clicking elsewhere dismisses the popup."
origin: "Phase 4 — 04-VERIFICATION.md"
result: fail
notes: "Popup appears but shows strange/garbled characters instead of a useful place name. Likely encoding issue with reverse geocode response."

### E. Route Editing (Phase 3)

#### E1. Remove stop end-to-end
test: "Click Entfernen on a stop, confirm dialog, stop disappears, driving times and budget recalculate"
expected: "Stop removed from list, metrics (km, budget, days) update correctly, map markers update"
origin: "Phase 3 — 03-VERIFICATION.md"
result: fail
notes: "Works only once. Unclear if stop was actually deleted. Cannot repeat — likely edit lock stuck after first operation."

#### E2. Add stop end-to-end
test: "Click '+ Stopp hinzufuegen', enter location, select insert position, new stop appears with researched activities/restaurants/accommodation"
expected: "New stop inserted at correct position, full research pipeline runs with SSE progress, guide view refreshes with new stop"
origin: "Phase 3 — 03-VERIFICATION.md"
result: fail
notes: "Button greyed out — likely blocked by stuck edit lock from previous E1 remove operation."

#### E3. Drag-and-drop reorder
test: "Drag a stop card to new position in the stops overview grid; order changes, driving times recalculate"
expected: "Stop moves to new position, sequential IDs renumber, driving times/distances recalculate, map polyline updates"
origin: "Phase 3 — 03-VERIFICATION.md"
result: fail
notes: "Drag-and-drop works mechanically but UX issue: drops ON another stop rather than BETWEEN two stops. Confusing interaction model."

#### E4. Edit controls disabled during active operation
test: "While any edit is processing, check remove/add/replace buttons"
expected: "Buttons are greyed out and unclickable while SSE operation is active"
origin: "Phase 3 — 03-VERIFICATION.md"
result: fail
notes: "Edit controls don't work correctly. Editing duration seems to trigger replace-stop flow instead of inline edit."

## Summary

total: 18
passed: 10
issues: 8
pending: 0
skipped: 0
blocked: 0

## Gaps

### GAP-01: Desktop split-panel map too large (B1)
severity: high
origin: Phase 4 regression
description: Map panel at 58% is too large on desktop. Content panel appears cut off with unused space on the right. The split-panel layout is not rendering as designed.
type: CSS layout

### GAP-02: Map over-zooms on day drill-down (A2)
severity: high
origin: Phase 10
description: When drilling into a day detail, the map zooms in too much and stop markers/POIs are not visible. fitDayStops() zoom level is too aggressive.
type: map behavior

### GAP-03: Stats bar font too large (C3)
severity: low
origin: Phase 4
description: Stats bar pills have oversized font. Needs CSS font-size reduction.
type: CSS styling

### GAP-04: Click-to-add popup shows garbled characters (D3)
severity: medium
origin: Phase 4
description: Reverse geocode popup shows strange/garbled characters instead of a readable place name. Possible encoding issue with Google Geocoder response.
type: encoding/data

### GAP-05: Edit lock stuck after remove-stop (E1, E2)
severity: high
origin: Phase 3
description: Remove-stop operation appears to leave the edit lock in place, blocking all subsequent edit operations (add, remove, replace). Lock not released on completion or error.
type: backend logic

### GAP-06: Drag-and-drop drops ON stop instead of BETWEEN (E3)
severity: medium
origin: Phase 3
description: Drag-and-drop reorder drops a stop card onto another stop rather than inserting between two stops. Confusing UX — needs drop-zone indicators between cards.
type: UX/interaction

### GAP-07: Edit duration triggers replace-stop flow (E4)
severity: medium
origin: Phase 3
description: Attempting to edit a stop's duration appears to trigger the replace-stop flow instead of an inline duration edit. Edit controls are not properly differentiated.
type: frontend logic
