# DetourAI

## What This Is

AI-powered road trip planner for friends and family. Users configure a trip (start, destination, duration, budget, travel style), then 9 specialized Claude agents collaboratively build the route, research accommodations/activities/restaurants, and produce a day-by-day travel guide. Features interactive route building with stop selection, map-centric responsive layout, route editing (add/remove/reorder/replace stops), public shareable trip links, and geographic intelligence for island and ferry destinations. Real-time progress via SSE. Deployed via Docker Compose with FastAPI backend and vanilla JS frontend.

## Core Value

Route planning and stop discovery must produce consistently high-quality, geographically correct results for any destination type — mainland, coastal, and island regions alike.

## Requirements

### Validated

- ✓ Multi-step trip configuration form (start, destination, duration, budget, travel style, via points) — existing
- ✓ 9 specialized Claude AI agents for route planning, stop options, accommodations, activities, restaurants, day planning, travel guide, trip analysis — existing
- ✓ Interactive route building: user selects stops one-by-one from AI-generated options — existing
- ✓ Real-time SSE progress streaming during planning — existing
- ✓ Accommodation research with parallel prefetching per stop — existing
- ✓ Day-by-day travel guide with activities, restaurants, driving directions — existing
- ✓ JWT authentication with user accounts — existing
- ✓ Travel plan persistence (save/load/delete) — existing
- ✓ Docker Compose deployment (backend, frontend, Redis, Celery, Nginx) — existing
- ✓ Region/explore mode for legs marked as exploration areas — existing
- ✓ Stop replacement (swap out individual stops with full re-research) — existing
- ✓ Google Maps integration (geocoding, directions, places) — existing
- ✓ Budget tracking and cost estimation across accommodation, food, activities, fuel — existing
- ✓ Calendar/week view for trip timeline — existing
- ✓ Sidebar navigation with route visualization — existing
- ✓ File-based debug logging with per-agent log files — existing
- ✓ Fix route planning for island/coastal destinations (ferry routes, island-aware geography) — v1.0
- ✓ Fix stop finder coordinate resolution (stops landing on mainland instead of target islands) — v1.0
- ✓ Ensure stop finder respects travel style preferences — v1.0
- ✓ Consistent stop quality — eliminate random low-quality suggestions — v1.0
- ✓ Driving efficiency — reduce unnecessary zigzag and backtracking in routes — v1.0
- ✓ User can edit stops manually (add, remove, reorder, replace) — v1.0
- ✓ User can replace individual stops with guided "find something else" flow — v1.0
- ✓ User can reorder stops in the route sequence — v1.0
- ✓ Responsive web design — full mobile browser support — v1.0
- ✓ UI redesign: map-centric layout with the route map as hero element — v1.0
- ✓ UI redesign: card-based stop presentation with photos — v1.0
- ✓ UI redesign: interactive day-by-day timeline (scrollable, expandable) — v1.0
- ✓ UI redesign: dashboard overview with key trip stats — v1.0
- ✓ Public shareable links for trip plans (read-only view for friends/family) — v1.0
- ✓ Remove PDF/PPTX export functionality (deprecated, replaced by shareable links) — v1.0

### Active

**Current Milestone: v1.1 Polish & Travel View Redesign**

**Goal:** Fix all known tech debt and bugs, then redesign the travel view for clarity — overview-first with drill-down into days/stops.

**Target features:**
- Fix map markers/polyline not refreshing after route edits
- Add `replace_stop_job` to Celery include list
- Fix stats bar deferred update after edits
- Fix RouteArchitect ignoring daily drive limits
- Browser-verify 9 pending UI items
- Overview-first travel view with compact day cards
- Day drill-down: focus map on region, show day's elements
- Stop drill-down: focus map on stop region, show stop details
- Progressive disclosure — collapse unfocused content, expand focused

### Out of Scope

- Native mobile app — responsive web is sufficient for current user base
- PWA/offline support — not needed for current friends & family audience
- OAuth/social login — email/password sufficient
- Real-time collaborative editing — single-user planning is fine
- Monetization/payment system — personal project for friends & family
- Multi-language support — German-only as designed
- CSS framework migration — vanilla CSS with Grid/Container Queries is sufficient
- Map library migration — Google Maps SDK + Leaflet covers all needs

## Context

- Used by friends and family circle, not a public product
- v1.0 shipped 2026-03-26 with 286 passing tests across 14,332 LOC Python + 16,092 LOC JS/HTML/CSS
- 9 AI agents orchestrated via Celery workers with SSE streaming
- Geographic intelligence covers 8 Mediterranean island groups with ferry detection
- Map-centric responsive layout with split-panel design, stop cards, day timeline
- Public sharing via token-based links with read-only mode
- Phase 8 (tech debt) fixed: map markers refresh after edits, replace_stop_job registered, stats bar on all tabs, drive limit enforcement with ferry exclusion
- Phase 9 split guide.js (3010 lines) into 7 focused modules — pure structural refactor enabling Phase 10 progressive disclosure UI
- Phase 10 implemented three-level drill-down UI (overview → day → stop) with crossfade transitions, breadcrumb navigation, and map marker dimming/focus management

## Constraints

- **Stack**: Python/FastAPI backend, vanilla JS frontend — no framework migration
- **Deployment**: Docker Compose on TrueNAS — must stay containerized
- **AI Provider**: Anthropic Claude — all agents use claude-opus-4-5/claude-sonnet-4-5
- **Maps**: Google Maps APIs — geocoding, directions, places
- **Budget**: Personal project — optimize AI token costs (TEST_MODE=true for dev)
- **Language**: All user-facing text in German, prices in CHF
- **Auth**: JWT-based, existing system stays

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Drop PDF/PPTX export | User stopped pursuing exports; shareable links replace this | ✓ Good (Phase 5) |
| Full UI redesign over incremental fixes | Current design needs fundamental rethink, not patches | ✓ Good (Phase 4) |
| Responsive web over native app | Friends & family audience doesn't justify native app investment | ✓ Good (Phase 4) |
| Parallel AI quality + UX tracks | Both are equally important; interleave rather than sequence | ✓ Good (v1.0) |
| Public shareable links for trip sharing | Simple, no-auth viewing for recipients | ✓ Good (Phase 5) |
| Bbox-based island detection | Simpler than haversine-from-center, covers all 8 island groups | ✓ Good (Phase 2) |
| Ferry speed constant 30 km/h | Reasonable estimate for Mediterranean ferries | ✓ Good (Phase 2) |
| Corridor check flags but does NOT reject | User sees warning badge, maintains choice | ✓ Good (Phase 1) |
| Tags merge with ordered dedup, max 4 | Prevents tag overload while preserving AI + activity sources | ✓ Good (Phase 6) |
| Ferry-aware directions in all code paths | Route edits on island trips need correct ferry metadata | ✓ Good (Phase 7) |
| Two-tier drive limit validation (soft 100% + hard 130%) | Prevents uncomfortable overlong driving days while staying flexible | ✓ Good (Phase 8) |
| Breadcrumb outside #guide-content | Persists across renderGuide() calls, avoids delegation scope issues | ✓ Good (Phase 10) |
| Marker dimming via OverlayView _div opacity | Simpler than marker icon swaps, works with custom overlays | ✓ Good (Phase 10) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-27 after Phase 10 (progressive-disclosure-ui) completion*
