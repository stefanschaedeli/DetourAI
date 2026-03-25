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

- [ ] Fix route planning for island/coastal destinations (ferry routes, island-aware geography)
- [ ] Fix stop finder coordinate resolution (stops landing on mainland instead of target islands)
- [x] Ensure stop finder respects travel style preferences (beach/ocean focus not overridden by mountain stops) — Validated in Phase 1
- [x] Consistent stop quality — eliminate random low-quality suggestions — Validated in Phase 1
- [x] Driving efficiency — reduce unnecessary zigzag and backtracking in routes — Validated in Phase 1
- [ ] User can edit stops manually (rename, move, add, remove)
- [ ] User can adjust preferences mid-planning and regenerate affected parts
- [ ] User can replace individual stops with guided "find something else" flow
- [ ] User can reorder stops in the route sequence
- [ ] Responsive web design — full mobile browser support
- [ ] UI redesign: map-centric layout with the route map as hero element
- [ ] UI redesign: card-based stop presentation with photos (Airbnb/Google Travel style)
- [ ] UI redesign: interactive day-by-day timeline (scrollable, expandable)
- [ ] UI redesign: dashboard overview with key trip stats
- [ ] Public shareable links for trip plans (read-only view for friends/family)
- [ ] Remove PDF/PPTX export functionality (deprecated, replaced by shareable links)

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
- The output_generator (PDF/PPTX) is deprecated and should be removed in favor of shareable web links
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
| Drop PDF/PPTX export | User stopped pursuing exports; shareable links replace this | — Pending |
| Full UI redesign over incremental fixes | Current design needs fundamental rethink, not patches | — Pending |
| Responsive web over native app | Friends & family audience doesn't justify native app investment | — Pending |
| Parallel AI quality + UX tracks | Both are equally important; interleave rather than sequence | — Pending |
| Public shareable links for trip sharing | Simple, no-auth viewing for recipients | — Pending |

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
*Last updated: 2026-03-25 after Phase 1 completion*
