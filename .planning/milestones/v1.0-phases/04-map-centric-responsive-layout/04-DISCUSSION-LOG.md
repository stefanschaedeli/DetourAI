# Phase 4: Map-Centric Responsive Layout - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 04-map-centric-responsive-layout
**Areas discussed:** Split-panel layout, Stop card design, Map interactivity

---

## Split-Panel Layout

### Map arrangement on desktop

| Option | Description | Selected |
|--------|-------------|----------|
| Map left, content right (Recommended) | Map ~58% left, content scrolls right. Google Maps/Airbnb pattern. | ✓ |
| Map right, content left | Content on left (reading flow), map right. Less common. | |
| Map top hero, content below | Full-width map hero (~40vh), content scrolls below. Editorial feel. | |

**User's choice:** Map left, content right
**Notes:** None

### Map visibility across tabs

| Option | Description | Selected |
|--------|-------------|----------|
| Always visible (Recommended) | Map persists across all tabs, content syncs with map. | ✓ |
| Overview + stops + days only | Map hidden on budget tab. | |
| Overview only | Map only on overview, other tabs full-width. | |

**User's choice:** Always visible
**Notes:** None

### Existing trip sidebar

| Option | Description | Selected |
|--------|-------------|----------|
| Replace with map (Recommended) | Map replaces sidebar entirely. Stops visible as markers. | |
| Keep as collapsible overlay | Sidebar overlays on map, collapsed by default. | ✓ |
| Move into content panel | Convert to compact route summary strip in content panel. | |

**User's choice:** Keep as collapsible overlay
**Notes:** None

### Dashboard stats placement

| Option | Description | Selected |
|--------|-------------|----------|
| Stats bar in overview (Recommended) | Compact stats strip at top of overview tab. 4 key numbers as pill widgets. | ✓ |
| Separate dashboard tab | New dedicated tab for stats, charts, breakdown. | |
| Floating stats overlay on map | Key stats as floating card on map panel. | |

**User's choice:** Stats bar in overview
**Notes:** None

---

## Stop Card Design

### Card style

| Option | Description | Selected |
|--------|-------------|----------|
| Photo hero card (Recommended) | Large photo top, name overlay, facts below. 1 card/row. | |
| Compact row card | Horizontal: thumbnail left, info right. More stops visible. | ✓ (modified) |
| Photo grid (2 columns) | 2-column grid with square photos. More density. | |

**User's choice:** Compact row card — but with 16:9 wide-format photo on the left (not small square thumbnail), info structured on the right
**Notes:** User corrected the layout twice to clarify: landscape 16:9 photo on the left side, all info structured on the right side.

### Photos per card

| Option | Description | Selected |
|--------|-------------|----------|
| 1 hero photo (Recommended) | Single best photo as wide banner. Click for more. | ✓ |
| 3 photos with carousel dots | Swipeable photo strip. More visual, heavier. | |
| 1 photo + 2 mini thumbnails | Wide hero + 2 small thumbs in corner. | |

**User's choice:** 1 hero photo
**Notes:** None

### Edit control placement

| Option | Description | Selected |
|--------|-------------|----------|
| On hover / long-press (Recommended) | Hidden by default, appear on hover/long-press. Clean. | |
| Always visible as icon row | Small icon buttons always visible at bottom-right. Discoverable. | ✓ |
| Context menu (three-dot) | Single ⋮ menu button with dropdown. Minimal. | |

**User's choice:** Always visible as icon row
**Notes:** None

### Card info content

| Option | Description | Selected |
|--------|-------------|----------|
| Drive time from previous stop | e.g. "2h 15min von Zürich" | ✓ |
| Nights staying | e.g. "2 Nächte" | ✓ |
| Travel style tags | Colored pills like "Strand", "Kultur" | ✓ |
| Stop number + name | e.g. "3. Lyon" as title | ✓ |

**User's choice:** All four options + short description on why this stop matches travel guidelines
**Notes:** User added custom requirement: a short description explaining why the stop fits the travel style. Maps to StopOptionsFinder teaser field.

---

## Map Interactivity

### Map-content synchronization

| Option | Description | Selected |
|--------|-------------|----------|
| Bidirectional highlight (Recommended) | Click map ↔ highlight card. Auto-fit on tab switch. | |
| Map → content only | One-way: map click scrolls to card. | |
| Bidirectional + auto-pan on scroll | Full sync + map follows scroll position. Most immersive. | ✓ |

**User's choice:** Bidirectional + auto-pan on scroll
**Notes:** None

### Map click to add stop

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, click to add stop (Recommended) | Click empty spot → reverse geocode → confirm → insert. | ✓ |
| No, keep text input only | Map is view-only. Phase 3 text input stays. | |
| Yes, but only in edit mode | Toggle "Bearbeiten" mode to enable click-to-add. | |

**User's choice:** Yes, click to add stop
**Notes:** This was explicitly deferred from Phase 3 to Phase 4.

### Route visualization

| Option | Description | Selected |
|--------|-------------|----------|
| Colored polyline + numbered markers (Recommended) | Driving route as colored polyline, numbered stop markers, dashed ferry. | ✓ (modified) |
| Animated route with direction arrows | Same + animated direction dashes. More GPU usage. | |
| Minimal dots only | Just numbered dots, no polyline. | |

**User's choice:** Option 1 but with black line
**Notes:** User explicitly wants black polyline instead of current blue (#4a90d9). Ferry segments as dashed black.

---

## Claude's Discretion

- Mobile layout adaptation (UIR-02) — user skipped this area, left to Claude
- Day timeline design (UIR-04) — not discussed, left to Claude
- Animation/transition details
- Responsive breakpoints
- Map marker styling details
- Auto-pan debounce threshold

## Deferred Ideas

None — discussion stayed within phase scope
