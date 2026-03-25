# Phase 4: Map-Centric Responsive Layout - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Redesign the trip viewing experience (guide view) around a map-hero split-panel layout with photo-card stop presentation, interactive timeline, dashboard stats, and full mobile responsiveness. Includes map-click stop insertion (deferred from Phase 3).

Requirements: UIR-01, UIR-02, UIR-03, UIR-04, UIR-05, UIR-06

</domain>

<decisions>
## Implementation Decisions

### Split-Panel Layout (UIR-01)
- **D-01:** Desktop layout is **map left (~58%), content right (scrollable)**. Google Maps / Airbnb pattern. Map panel is position-fixed while content panel scrolls independently.
- **D-02:** Map stays **visible across all tabs** (overview, stops, days, calendar, budget). Map content adapts to active tab — e.g., stops tab highlights stop markers, days tab highlights day segments.
- **D-03:** Existing trip sidebar (route node visualization) becomes a **collapsible overlay on top of the map**. Collapsed by default, click to expand for quick route navigation. Useful for long routes with many stops.
- **D-04:** Dashboard stats (UIR-05: total days, stops, distance, budget remaining) displayed as a **compact stats bar at the top of the overview tab** — 4 key numbers as pill/card widgets. No separate dashboard tab.

### Stop Card Design (UIR-03)
- **D-05:** Cards use a **compact row layout with 16:9 photo on the left** and structured info on the right. Not tall hero cards — keeps scroll depth manageable.
- **D-06:** **1 hero photo** per card (single best Google Places result). Click card to see more photos in detail view. Existing 5-tier image fallback chain (Places > Nearby > Text > Static > SVG) applies.
- **D-07:** Card info (right side) includes: **stop number + name** (title), **drive time from previous stop**, **nights staying**, **travel style tags** (colored pills), and a **short description** explaining why the stop matches the travel style (from StopOptionsFinder teaser field).
- **D-08:** Edit controls (remove, reorder, replace) are **always visible as an icon row** at the bottom-right of each card. Immediately discoverable, no hidden interactions.

### Map Interactivity (UIR-06)
- **D-09:** **Bidirectional sync with auto-pan on scroll**. Click map marker → scroll to & highlight card. Click/hover card → highlight marker + pan map. Map auto-pans as user scrolls through stop cards (follows reading position). Map auto-fits all stops on tab switch.
- **D-10:** **Click-to-add-stop on map** (deferred from Phase 3). Click empty map spot → reverse geocode → "Stopp hier hinzufuegen?" prompt → inserts between nearest existing stops. Triggers the existing add-stop Celery task.
- **D-11:** Driving route rendered as a **black polyline** (replacing current blue #4a90d9) with **numbered markers** at each stop matching card order. Ferry segments shown as **dashed black line**. Active/selected stop marker is enlarged/highlighted.

### Mobile Adaptation (UIR-02)
- **D-12:** Claude's discretion on mobile layout. Recommended approach: map collapses to a compact strip at top (~30vh) with content below. Swipe up to expand content / minimize map.

### Day Timeline (UIR-04)
- **D-13:** Claude's discretion on timeline design. Must be scrollable with expandable day details per UIR-04 success criteria.

### Claude's Discretion
- Mobile layout pattern (map-top strip, bottom sheet, or other)
- Day timeline visual design and interaction pattern
- Animation/transition details for tab switches and card interactions
- Exact breakpoints for responsive layout (current: 480px, 600px, 767px, 900px)
- Map marker styling (size, colors, number badge design)
- Auto-pan scroll debounce/threshold to avoid jarring jumps
- Stats bar widget styling and layout within overview tab
- How calendar tab content adapts to the split-panel layout

### Folded Todos
None — no matching todos found for this phase.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Frontend Layout & Styling
- `frontend/index.html` — Single page with all section containers; guide view section starts at the `#view-guide` block
- `frontend/styles.css` — Monolithic CSS (~5000+ lines); guide styles at `.guide-tabs`, `#guide-map`, stops layout at `.stops-sidebar`; existing breakpoints at 480px, 600px, 767px, 900px
- `DESIGN_GUIDELINE.md` — Apple-inspired design system (color palette, typography, spacing). Current aesthetic reference — Phase 4 may evolve it toward a richer travel-app feel

### Guide View (primary rewrite target)
- `frontend/js/guide.js` — Guide rendering: `renderGuide()`, `renderOverview()`, `renderStopsOverview()`, `renderStopDetail()`, `renderDaysOverview()`, `renderDayDetail()`, `renderCalendar()`, `renderBudget()`. Tab system, stop detail expansion, edit controls (remove/add/reorder/replace)
- `frontend/js/maps.js` — GoogleMaps singleton: `initGuideMap()`, `initStopOverviewMap()`, `createDivMarker()`, `renderDrivingRoute()`, `getPlaceImages()`, `resolveEntityCoordinates()`. Image fetching with 5-tier fallback

### Sidebar & Navigation
- `frontend/js/sidebar.js` — Trip sidebar with route node visualization, collapse toggle
- `frontend/js/router.js` — Client-side routing; guide view at `/travel/{id}`

### State & API
- `frontend/js/state.js` — Global `S` object, `esc()` XSS helper, localStorage layer
- `frontend/js/api.js` — All fetch calls, SSE helpers, JWT injection

### Route Editing (Phase 3 — must integrate into new layout)
- `frontend/js/guide.js` lines with edit controls — Remove button, add-stop modal, drag-and-drop reorder, replace-stop flow
- `backend/tasks/` — Celery tasks for route editing (remove, add, reorder, replace)

### Models (data shape for cards/map)
- `backend/models/travel_response.py` — `TravelStop` (name, lat, lng, nights, drive_km_from_prev, drive_hours_from_prev, tags), `DayPlan`, `CostEstimate`
- `backend/models/stop_option.py` — `StopOption` with `teaser` field for stop description text

### Prior Phase Context
- `.planning/phases/01-ai-quality-stabilization/01-CONTEXT.md` — Visual flag badges for off-corridor stops (D-04)
- `.planning/phases/02-geographic-routing/02-CONTEXT.md` — Ferry leg indicators (D-03), dashed ferry segments
- `.planning/phases/03-route-editing/03-CONTEXT.md` — Edit controls architecture, map-click deferred to Phase 4 (deferred ideas)

### Requirements
- `.planning/REQUIREMENTS.md` — UIR-01 through UIR-06 acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GoogleMaps.initGuideMap()` — Guide map instance, reusable as the fixed left-panel map
- `GoogleMaps.renderDrivingRoute()` — Polyline rendering with batched Routes API (currently blue, change to black)
- `GoogleMaps.createDivMarker()` — Custom HTML markers via OverlayView (for numbered stop markers)
- `GoogleMaps.getPlaceImages()` — 5-tier image fallback (Places → Nearby → Text → Static → SVG) for card photos
- `GoogleMaps.resolveEntityCoordinates()` — Batch coordinate resolution for map markers
- Existing guide tab system (`renderGuide()` switch on `activeTab`) — extend, don't replace
- Existing stops sidebar pattern (2-column layout) — reference for collapsible overlay
- HTML5 drag-and-drop from route-builder.js — portable to new card layout for reordering
- SSE overlay pattern for progress indication during edit operations

### Established Patterns
- Vanilla JS with global `S` state, imperative DOM manipulation via `innerHTML`
- CSS Grid/Flexbox layouts with `@media` breakpoints
- Tab-based navigation within guide view
- `esc()` for XSS-safe HTML interpolation
- `_fetchWithAuth()` / `_fetchQuiet()` for API calls
- `requestAnimationFrame()` for post-render initialization

### Integration Points
- Guide view (`#view-guide` section in index.html) is the primary rewrite target
- `renderGuide()` in guide.js is the entry point — tab dispatch happens here
- Map initialization hooks into `_initGuideMap()` — must be restructured for persistent left-panel map
- Router dispatches to guide view via `/travel/{id}` route
- Edit controls (remove/add/reorder/replace buttons + handlers) must be preserved in new card layout
- Sidebar.js `updateSidebar()` called from `showTravelGuide()` — needs overlay adaptation

</code_context>

<specifics>
## Specific Ideas

- **16:9 photo left, info right card layout:** User specifically wants compact row cards with a landscape-format photo on the left and structured info (number, name, drive time, nights, tags, description) on the right. Not tall hero cards, not tiny thumbnails.
- **Black route polyline:** User explicitly wants the driving route line in black (not the current blue #4a90d9). Ferry segments dashed black.
- **Always-visible edit controls:** Edit buttons (remove, reorder, replace) always visible as icon row on cards — user prefers discoverability over visual cleanliness.
- **Auto-pan on scroll:** Map follows the user's reading position as they scroll through stop cards. Most immersive option, needs careful debouncing.
- **Click-to-add on map:** Direct map interaction for adding stops — reverse geocode the click location, prompt for confirmation, insert between nearest stops.
- **Stop description on card:** Each card shows a short text explaining why this stop matches the travel guidelines — sourced from the StopOptionsFinder `teaser` field.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-map-centric-responsive-layout*
*Context gathered: 2026-03-25*
