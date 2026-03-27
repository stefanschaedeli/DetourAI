# Roadmap: DetourAI

## Milestones

- v1.0 AI Trip Planner MVP - Phases 1-7 (shipped 2026-03-26) - [Archive](milestones/v1.0-ROADMAP.md)
- **v1.1 Polish & Travel View Redesign** - Phases 8-11 (in progress)

## Phases

<details>
<summary>v1.0 AI Trip Planner MVP (Phases 1-7) - SHIPPED 2026-03-26</summary>

- [x] Phase 1: AI Quality Stabilization (3/3 plans) - AI model fix, corridor validation, style enforcement, quality gating
- [x] Phase 2: Geographic Routing (2/2 plans) - Island-aware routing, ferry detection, port awareness
- [x] Phase 3: Route Editing (3/3 plans) - Remove/add/reorder/replace stops with Celery tasks
- [x] Phase 4: Map-Centric Responsive Layout (6/6 plans) - Split-panel map-hero, stop cards, day timeline, mobile responsive
- [x] Phase 5: Sharing & Cleanup (3/3 plans) - Public shareable links, PDF/PPTX export removal
- [x] Phase 6: Wiring Fixes (2/2 plans) - Share token persistence, tags, SSE events, hints
- [x] Phase 7: Ferry-Aware Route Edits (1/1 plans) - Ferry-aware directions in all edit paths

**25/25 requirements satisfied** | **286 tests passing** | **166 commits**

</details>

### v1.1 Polish & Travel View Redesign

**Milestone Goal:** Fix all known tech debt and bugs, then redesign the travel view for clarity -- overview-first with drill-down into days/stops.

- [ ] **Phase 8: Tech Debt Stabilization** - Fix production bugs and stale-state issues against the current UI
- [ ] **Phase 9: Guide Module Split** - Split guide.js monolith into focused modules with zero behavioral changes
- [ ] **Phase 10: Progressive Disclosure UI** - Three-level drill-down navigation with map focus management
- [ ] **Phase 11: Browser Verification** - Verify 9 pending UI items against the new progressive disclosure view

## Phase Details

### Phase 8: Tech Debt Stabilization
**Goal**: The existing travel view works correctly -- stop replacement runs in Docker, map visuals stay current after edits, stats reflect actual route state, and driving days respect user limits
**Depends on**: Nothing (first phase of v1.1)
**Requirements**: DEBT-01, DEBT-02, DEBT-03, DEBT-04
**Success Criteria** (what must be TRUE):
  1. User can replace a stop in Docker deployment and the Celery task completes without NotRegistered error
  2. After adding, removing, reordering, or replacing a stop, map markers and polyline reflect the current route without page reload
  3. Stats bar (total distance, drive time, budget) updates immediately after any route edit
  4. RouteArchitect generates routes where no single driving day exceeds the user-configured max_drive_time_per_day, including legs with ferry crossings
**Plans:** 2 plans
Plans:
- [ ] 08-01-PLAN.md — Celery task registration, map redraw after edits, stats bar on all tabs
- [ ] 08-02-PLAN.md — RouteArchitect drive limit enforcement with two-tier validation

### Phase 9: Guide Module Split
**Goal**: guide.js is decomposed into focused modules with clear boundaries, enabling safe progressive disclosure work in Phase 10
**Depends on**: Phase 8
**Requirements**: STRC-01
**Success Criteria** (what must be TRUE):
  1. guide.js is replaced by 5+ focused modules (core, overview, stops, days, map-sync) loaded via script tags in index.html
  2. All existing travel guide functionality works identically -- tab switching, stop/day detail, editing, map sync, SSE handlers
  3. Each module file has a header comment documenting its dependencies and exports
**Plans**: TBD

### Phase 10: Progressive Disclosure UI
**Goal**: Users navigate their travel plan through a three-level drill-down (overview, day, stop) with the persistent map responding to navigation context
**Depends on**: Phase 9
**Requirements**: NAV-01, NAV-02, NAV-03, NAV-04, NAV-05, NAV-06
**Success Criteria** (what must be TRUE):
  1. Travel view opens to a compact overview showing trip summary, clickable day cards, and all stops on the map
  2. Clicking a day card drills into that day's detail -- map zooms to the day's region, showing that day's stops, activities, and restaurants
  3. Clicking a stop from day view drills into stop detail -- map pans and zooms to stop area, showing accommodation, activities, restaurants
  4. Breadcrumb bar (Uebersicht > Tag 3 > Annecy) appears at each drill level and allows back-navigation to any parent level
  5. Non-focused stops appear dimmed on the map when viewing a specific day or stop, and return to full visibility on back-navigation to overview
**Plans**: TBD
**UI hint**: yes

### Phase 11: Browser Verification
**Goal**: All 9 pending UI items from v1.0 are verified against the new progressive disclosure view and any broken items are fixed
**Depends on**: Phase 10
**Requirements**: VRFY-01
**Success Criteria** (what must be TRUE):
  1. Each of the 9 pending UI verification items has been tested in a browser against the new travel view layout
  2. Any items found broken during verification are fixed and re-verified
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:** Phase 8 -> 9 -> 10 -> 11

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. AI Quality Stabilization | v1.0 | 3/3 | Complete | 2026-03-25 |
| 2. Geographic Routing | v1.0 | 2/2 | Complete | 2026-03-25 |
| 3. Route Editing | v1.0 | 3/3 | Complete | 2026-03-25 |
| 4. Map-Centric Responsive Layout | v1.0 | 6/6 | Complete | 2026-03-26 |
| 5. Sharing & Cleanup | v1.0 | 3/3 | Complete | 2026-03-26 |
| 6. Wiring Fixes | v1.0 | 2/2 | Complete | 2026-03-26 |
| 7. Ferry-Aware Route Edits | v1.0 | 1/1 | Complete | 2026-03-26 |
| 8. Tech Debt Stabilization | v1.1 | 0/2 | Planning | - |
| 9. Guide Module Split | v1.1 | 0/0 | Not started | - |
| 10. Progressive Disclosure UI | v1.1 | 0/0 | Not started | - |
| 11. Browser Verification | v1.1 | 0/0 | Not started | - |
