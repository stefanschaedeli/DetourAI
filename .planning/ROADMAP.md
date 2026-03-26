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
- [x] **Phase 3: Route Editing** - User controls to add, remove, reorder, and replace stops with live metric updates (completed 2026-03-25)
- [ ] **Phase 4: Map-Centric Responsive Layout** - Split-panel map-hero design, mobile responsive, photo cards, timeline, dashboard
- [ ] **Phase 5: Sharing & Cleanup** - Public shareable trip links and removal of deprecated PDF/PPTX export
- [ ] **Phase 6: Wiring Fixes** - Close audit gaps: share_token persistence, hints wiring, SSE event registration, stop tags population

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
**Plans:** 2/3 plans executed

Plans:
- [x] 01-01-PLAN.md — Model bug fix, utility functions, StopOption model, tests
- [x] 01-02-PLAN.md — Agent prompt changes (travel style + plausibility + bearing)
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
**Plans:** 2 plans

Plans:
- [x] 02-01-PLAN.md — Ferry utilities, island lookup table, model extensions, tests
- [x] 02-02-PLAN.md — Agent prompt updates, route enrichment ferry fallback, corridor bypass

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
**Plans:** 3/3 plans complete

Plans:
- [x] 03-01-PLAN.md — Shared route edit helpers, edit lock, Celery tasks (remove/add/reorder) + tests
- [x] 03-02-PLAN.md — API endpoints, _fire_task registration, edit lock integration, replace-stop hints + endpoint tests
- [x] 03-03-PLAN.md — Frontend edit controls (remove, add modal, drag-and-drop reorder, SSE handlers, replace hints UI)

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
**Plans:** 3/6 plans executed

Plans:
- [x] 04-01-PLAN.md — Backend model extension (TravelStop tags/teaser/highlights) + HTML/CSS split-panel skeleton
- [x] 04-02-PLAN.md — Persistent map panel, numbered markers, black polyline, bidirectional sync
- [x] 04-03-PLAN.md — Stop cards with photos/tags/edit controls + stats bar
- [ ] 04-04-PLAN.md — Day timeline with expand/collapse + sidebar overlay + mobile polish
- [ ] 04-05-PLAN.md — Click-to-add-stop on map (reverse geocode + insert)
- [ ] 04-06-PLAN.md — Visual verification checkpoint (all UIR requirements)

### Phase 5: Sharing & Cleanup
**Goal**: Users can share trip plans via public links and the deprecated PDF/PPTX export is removed
**Depends on**: Phase 4
**Requirements**: SHR-01, SHR-02, SHR-03, SHR-04
**Success Criteria** (what must be TRUE):
  1. User can generate a shareable link for any saved trip plan
  2. Anyone with the link can view the full trip plan without logging in
  3. User can revoke a shared link so it stops working
  4. PDF/PPTX export buttons and backend code are completely removed from the codebase
**Plans:** 0/3 plans executed

Plans:
- [x] 05-01-PLAN.md — Backend sharing infrastructure (DB migration, travel_db functions, API endpoints + tests)
- [x] 05-02-PLAN.md — PDF/PPTX export removal (output_generator, endpoint, buttons, deps, docs cleanup)
- [ ] 05-03-PLAN.md — Frontend sharing UI (share toggle, read-only shared view, router + guide changes)

### Phase 6: Wiring Fixes
**Goal**: Close all audit gaps — fix broken wiring between phases so every v1.0 requirement is fully satisfied
**Depends on**: Phase 5
**Requirements**: CTL-04, SHR-01, AIQ-03, GEO-01, UIR-03
**Gap Closure:** Closes gaps from v1.0 milestone audit
**Success Criteria** (what must be TRUE):
  1. Share toggle shows correct state on page reload for actively shared travels
  2. Replace-stop hints entered by user are forwarded to the StopOptionsFinderAgent
  3. style_mismatch_warning and ferry_detected SSE events fire handlers in the browser
  4. Stop cards display populated tags from AI agent output
**Plans:** 2 plans

Plans:
- [ ] 06-01-PLAN.md — Backend wiring: share_token persistence, StopOption tags model, agent prompt tags, orchestrator merge
- [ ] 06-02-PLAN.md — Frontend wiring: SSE event registration, toast notifications, hints input relocation

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. AI Quality Stabilization | 2/3 | In Progress|  |
| 2. Geographic Routing | 0/2 | Planned | - |
| 3. Route Editing | 0/3 | Complete    | 2026-03-25 |
| 4. Map-Centric Responsive Layout | 3/6 | In Progress|  |
| 5. Sharing & Cleanup | 0/3 | Planned    |  |
| 6. Wiring Fixes | 0/2 | Planned    |  |
