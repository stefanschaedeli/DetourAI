# Travelman3

## What This Is

AI-powered road trip planner for friends and family. Users configure a trip (start, destination, duration, budget, travel style), then specialized Claude agents collaboratively build the route, research accommodations/activities/restaurants, and produce a day-by-day travel guide. Real-time progress via SSE. Currently deployed via Docker Compose with FastAPI backend and vanilla JS frontend.

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

### Active

- [x] Fix route planning for island/coastal destinations (ferry routes, island-aware geography) — Validated in Phase 2
- [x] Fix stop finder coordinate resolution (stops landing on mainland instead of target islands) — Validated in Phase 2
- [x] Ensure stop finder respects travel style preferences (beach/ocean focus not overridden by mountain stops) — Validated in Phase 1
- [x] Consistent stop quality — eliminate random low-quality suggestions — Validated in Phase 1
- [x] Driving efficiency — reduce unnecessary zigzag and backtracking in routes — Validated in Phase 1
- [x] User can edit stops manually (rename, move, add, remove) — Validated in Phase 3
- [ ] User can adjust preferences mid-planning and regenerate affected parts — deferred to future milestone
- [x] User can replace individual stops with guided "find something else" flow — Validated in Phase 3
- [x] User can reorder stops in the route sequence — Validated in Phase 3
- [x] Responsive web design — full mobile browser support — Validated in Phase 4
- [x] UI redesign: map-centric layout with the route map as hero element — Validated in Phase 4
- [x] UI redesign: card-based stop presentation with photos (Airbnb/Google Travel style) — Validated in Phase 4
- [x] UI redesign: interactive day-by-day timeline (scrollable, expandable) — Validated in Phase 4
- [x] UI redesign: dashboard overview with key trip stats — Validated in Phase 4
- [x] Public shareable links for trip plans (read-only view for friends/family) — Validated in Phase 5
- [x] Remove PDF/PPTX export functionality (deprecated, replaced by shareable links) — Validated in Phase 5

### Out of Scope

- Native mobile app — responsive web is sufficient for current user base
- PWA/offline support — not needed for current friends & family audience
- OAuth/social login — email/password sufficient
- Real-time collaborative editing — single-user planning is fine
- Monetization/payment system — personal project for friends & family
- Multi-language support — German-only as designed

## Context

- Used by friends and family circle, not a public product
- App works well for mainland Europe (France, Germany) but struggles with geography-heavy destinations (Greek islands, coastal routes with ferries)
- The current Apple-inspired design guideline needs a full rethink — wants richer, more visual travel-app feel
- Stop quality is inconsistent: sometimes excellent, sometimes random or mismatched to travel style
- The output_generator (PDF/PPTX) has been removed; sharing is now via public web links
- Current UI flow (5-step form → route builder → results) works but needs better user control at every stage

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
| Drop PDF/PPTX export | User stopped pursuing exports; shareable links replace this | ✓ Done (Phase 5) |
| Full UI redesign over incremental fixes | Current design needs fundamental rethink, not patches | ✓ Done (Phase 4) |
| Responsive web over native app | Friends & family audience doesn't justify native app investment | ✓ Done (Phase 4) |
| Parallel AI quality + UX tracks | Both are equally important; interleave rather than sequence | ✓ Done (v1.0) |
| Public shareable links for trip sharing | Simple, no-auth viewing for recipients | ✓ Done (Phase 5) |

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
*Last updated: 2026-03-26 after Phase 6 completion — v1.0 milestone complete, all wiring gaps closed*
