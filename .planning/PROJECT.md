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
- ✓ Celery replace_stop_job registration for production Docker — v1.1
- ✓ Map markers and polyline refresh after all route edits — v1.1
- ✓ Stats bar immediate update after route edits — v1.1
- ✓ RouteArchitect respects max_drive_time_per_day with ferry exclusion — v1.1
- ✓ guide.js split into 7 focused modules with zero regressions — v1.1
- ✓ Overview-first travel view with compact day cards and trip summary — v1.1
- ✓ Day drill-down with map focus on day's region — v1.1
- ✓ Stop drill-down with map focus on stop area — v1.1
- ✓ Breadcrumb back-navigation at each drill level — v1.1
- ✓ Map marker dimming for non-focused stops — v1.1
- ✓ Browser back/forward with drill-down navigation — v1.1
- ✓ 18 UI items browser-verified and 7 gaps fixed — v1.1
- ✓ Global wishes field forwarded to all 9 agents (travel_description, preferred_activities, mandatory_activities) — v1.2
- ✓ ArchitectPrePlanAgent for strategic region/nights pre-planning before stop selection — v1.2
- ✓ StopOptionsFinder history awareness with dedup safety net — v1.2
- ✓ Nights-remaining budget display during route building — v1.2
- ✓ Geheimtipp distance validation (prompt coordinates + haversine post-filter) — v1.2
- ✓ Geheimtipp name-based dedup within stops — v1.2
- ✓ Inline nights editor replacing prompt() with backend Celery recalculation — v1.2
- ✓ Day plan recalculation after nights changes via Celery + SSE — v1.2

### Active

- Karte beim Öffnen auf Route fokussiert (fitBounds)
- Korrekte Bilder in Stopp-Übersicht
- Tooltips für Edit-Buttons
- Stopauswahl: alle bisherigen Stops sichtbar, Zoom auf letzte + neue
- Stopfinder Performance-Optimierung

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
- v1.2 shipped 2026-03-29 with 319 passing tests; 4 UI polish items deferred to next milestone
- 10 AI agents orchestrated via Celery workers with SSE streaming (9 original + ArchitectPrePlanAgent)
- Geographic intelligence covers 8 Mediterranean island groups with ferry detection
- Map-centric responsive layout with 45/55 split-panel design
- Public sharing via token-based links with read-only mode
- Travel view uses three-level progressive disclosure (overview → day → stop) with breadcrumb navigation and map focus management
- guide.js split into 7 focused modules (core, overview, stops, days, edit, map-sync, nav)
- All known v1.0 tech debt resolved (Celery registration, map redraw, stats sync, drive limits)
- Known minor tech debt: router `_travelTab` missing drill state reset (low severity edge case)

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
| 7-module guide split over incremental extraction | Complete split enables safe progressive disclosure work | ✓ Good (Phase 9) |
| Breadcrumb outside #guide-content | Persists across renderGuide() calls, avoids delegation scope issues | ✓ Good (Phase 10) |
| Marker dimming via OverlayView _div opacity | Simpler than marker icon swaps, works with custom overlays | ✓ Good (Phase 10) |
| 45/55 split-panel ratio (map/content) | Better content readability while keeping map visible | ✓ Good (Phase 11) |
| Drop zones as separate divs between stop cards | Avoids ambiguous on-card drop behavior, clear visual targets | ✓ Good (Phase 11) |
| Nights edit via prompt() with local-state update | No backend PATCH needed for gap closure, simplest approach | Superseded (Phase 15) |
| Inline nights editor with backend Celery recalculation | Proper UI + server-side arrival_day rechaining + day plan refresh | ✓ Good (Phase 15) |
| Haversine post-filter for Geheimtipps (secondary to prompt coordinates) | Prompt improvement is primary fix; haversine is safety net | ✓ Good (Phase 15) |

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
*Last updated: 2026-03-29 after v1.2 milestone*
