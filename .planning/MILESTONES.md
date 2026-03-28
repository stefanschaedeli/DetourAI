# Milestones

## v1.1 Polish & Travel View Redesign (Shipped: 2026-03-28)

**Phases:** 4 | **Plans:** 11 | **Tasks:** 16
**Timeline:** 2 days (2026-03-27 → 2026-03-28) | **Commits:** 34
**Source changes:** 23 files changed, +896 / -167 lines
**Tests:** 291 passing
**Requirements:** 12/12 satisfied (DEBT 1-4, STRC-01, NAV 1-6, VRFY-01)

**Delivered:** Fixed all known tech debt and bugs, split guide.js monolith into 7 modules, and redesigned the travel view with three-level progressive disclosure (overview → day → stop) with breadcrumb navigation and map focus management.

**Key accomplishments:**

1. **Tech Debt Stabilization** — Fixed Celery task registration, map marker/polyline refresh after all 5 edit paths, stats bar unconditional on all tabs, two-tier drive limit enforcement with ferry exclusion
2. **Guide Module Split** — Split guide.js (3010 lines, 82 functions) into 7 focused modules with zero behavioral regressions
3. **Progressive Disclosure UI** — Three-level drill-down (overview → day → stop) with crossfade transitions, breadcrumb navigation, and map marker dimming/focus management
4. **Browser Verification** — Verified all 18 pending UI items, fixed 7 gaps (split-panel ratio, zoom cap, stats font, SSE error handling, geocode popup, drag-drop zones, inline nights edit)

**Known tech debt (accepted):**

- Router `_travelTab` handler missing drill state reset (2-line fix, low severity edge case)
- Nyquist validation files incomplete for phases 8, 9, 11

---

## v1.0 AI Trip Planner MVP (Shipped: 2026-03-26)

**Phases:** 7 | **Plans:** 20 | **Tasks:** 36
**Timeline:** 3 days (2026-03-24 → 2026-03-26) | **Commits:** 166
**Codebase:** 14,332 LOC Python + 16,092 LOC JS/HTML/CSS | 148 files changed, +27,555 / -1,134 lines
**Tests:** 286 passing

**Delivered:** Full-stack AI trip planner with 9 Claude agents, interactive route building, map-centric responsive UI, public sharing, and geographic intelligence for island/ferry destinations.

**Key accomplishments:**

1. **AI Quality Stabilization** — Fixed model bug, added three-stage stop validation pipeline (corridor/bearing/quality), travel style enforcement in agent prompts, plausibility warning system
2. **Geographic Routing** — Island-aware routing with 8 Mediterranean island groups, ferry detection, port awareness, ferry time/cost computation, corridor bypass for water crossings
3. **Route Editing** — Remove/add/reorder/replace stops with Celery tasks, edit locking, metric recalculation, SSE progress streaming, drag-and-drop UI
4. **Map-Centric Responsive Layout** — Split-panel map-hero design, persistent map with numbered markers, stop cards with photos/tags, day timeline with expand/collapse, stats bar, click-to-add-stop, mobile responsive
5. **Sharing & Cleanup** — Public shareable links with read-only view, share toggle, URL preservation, PDF/PPTX export removal
6. **Wiring Fixes** — Share token persistence, tags population from AI agents, SSE event registration with toast notifications, hints forwarding to search agent

**Known tech debt (accepted):**

- Map markers/polyline not refreshed after route edits (visual regression)
- replace_stop_job missing from Celery include list (production bug)
- Stats bar deferred update after edits
- 9 UI items pending human browser verification

**Requirements:** 25/25 satisfied (AIQ 1-5, GEO 1-5, CTL 1-5, UIR 1-6, SHR 1-4)

---
