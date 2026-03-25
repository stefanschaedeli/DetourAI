# Roadmap: Travelman3

## Overview

Travelman3 works but produces unreliable results for complex destinations and lacks modern UX. This roadmap stabilizes AI quality first (stop coordinates, travel style, model bug), adds geographic intelligence for islands and ferries, gives users direct control over their routes, redesigns the frontend around a map-centric responsive layout, and finishes with shareable trip links replacing the deprecated PDF/PPTX export. Each phase builds on the last: correct geography before route editing, route editing controls before layout design, polished layout before public sharing.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: AI Quality Stabilization** - Fix model bug, coordinate validation, travel style enforcement, and stop quality consistency
- [ ] **Phase 2: Geographic Routing** - Island-aware routing with ferry detection, port awareness, and water crossing fallbacks
- [ ] **Phase 3: Route Editing** - User controls to add, remove, reorder, and replace stops with live metric updates
- [ ] **Phase 4: Map-Centric Responsive Layout** - Split-panel map-hero design, mobile responsive, photo cards, timeline, dashboard
- [ ] **Phase 5: Sharing & Cleanup** - Public shareable trip links and removal of deprecated PDF/PPTX export

## Phase Details

### Phase 1: AI Quality Stabilization
**Goal**: Route planning and stop discovery produce consistently high-quality, correctly located results that match the user's travel style
**Depends on**: Nothing (first phase)
**Requirements**: AIQ-01, AIQ-02, AIQ-03, AIQ-04, AIQ-05
**Success Criteria** (what must be TRUE):
  1. A trip planned to Greek islands produces stops located on actual islands, not on the mainland
  2. A beach-focused trip produces exclusively coastal/beach stops, not mountain villages
  3. Stop suggestions are consistently high-quality with no random low-effort entries appearing
  4. Routes between sequential stops follow efficient driving paths without unnecessary zigzag or backtracking
**Plans:** 3 plans

Plans:
- [ ] 01-01-PLAN.md — Model bug fix, utility functions, StopOption model, tests
- [ ] 01-02-PLAN.md — Agent prompt changes (travel style + plausibility + bearing)
- [ ] 01-03-PLAN.md — Validation pipeline in main.py + frontend visual indicators

### Phase 2: Geographic Routing
**Goal**: The system handles island and coastal destinations with ferry awareness, producing complete routes across water crossings
**Depends on**: Phase 1
**Requirements**: GEO-01, GEO-02, GEO-03, GEO-04, GEO-05
**Success Criteria** (what must be TRUE):
  1. Planning a trip from Athens to Santorini produces a route that includes a ferry crossing from Piraeus
  2. Stop coordinates for island destinations resolve to actual island locations, never to nearby mainland points
  3. When Google Directions returns no route for a water crossing, the system constructs a ferry-aware alternative instead of failing
  4. Ferry travel time is deducted from the daily driving budget so days with ferry crossings have realistic schedules
**Plans**: TBD

### Phase 3: Route Editing
**Goal**: Users can directly modify their planned route by adding, removing, reordering, and replacing stops
**Depends on**: Phase 1, Phase 2
**Requirements**: CTL-01, CTL-02, CTL-03, CTL-04, CTL-05
**Success Criteria** (what must be TRUE):
  1. User can remove any stop from the route and the remaining stops reconnect correctly
  2. User can add a custom stop at any position in the route by entering a place name
  3. User can drag stops to reorder the route sequence
  4. User can replace a stop with a guided flow that finds alternatives matching specific criteria (e.g., "more beach", "less driving")
  5. After any route modification, total distance, driving time, and budget estimates update immediately
**Plans**: TBD

### Phase 4: Map-Centric Responsive Layout
**Goal**: The app uses a modern map-centric layout that works well on both desktop and mobile browsers
**Depends on**: Phase 3
**Requirements**: UIR-01, UIR-02, UIR-03, UIR-04, UIR-05, UIR-06
**Success Criteria** (what must be TRUE):
  1. On desktop, the map occupies the hero position in a split-panel layout with content alongside
  2. The app is fully usable on a phone browser — all features accessible, nothing cut off or overlapping
  3. Stops appear as visual cards with photos, key facts, and travel style tags instead of plain text lists
  4. The day-by-day timeline is scrollable and each day can be expanded to show full details
  5. A dashboard overview shows key trip stats: total days, number of stops, total distance, and remaining budget
**Plans**: TBD
**UI hint**: yes

### Phase 5: Sharing & Cleanup
**Goal**: Users can share trip plans via public links and the deprecated PDF/PPTX export is removed
**Depends on**: Phase 4
**Requirements**: SHR-01, SHR-02, SHR-03, SHR-04
**Success Criteria** (what must be TRUE):
  1. User can generate a shareable link for any saved trip plan
  2. Anyone with the link can view the full trip plan without logging in
  3. User can revoke a shared link so it stops working
  4. PDF/PPTX export buttons and backend code are completely removed from the codebase
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. AI Quality Stabilization | 0/3 | Planning complete | - |
| 2. Geographic Routing | 0/? | Not started | - |
| 3. Route Editing | 0/? | Not started | - |
| 4. Map-Centric Responsive Layout | 0/? | Not started | - |
| 5. Sharing & Cleanup | 0/? | Not started | - |
