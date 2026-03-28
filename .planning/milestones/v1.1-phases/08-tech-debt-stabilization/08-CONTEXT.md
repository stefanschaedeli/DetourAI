# Phase 8: Tech Debt Stabilization - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix 4 production bugs in the current travel view: Celery task registration, map marker/polyline refresh after route edits, stats bar staleness, and RouteArchitect drive limit enforcement. No new features — the existing UI must work correctly before the Phase 10 redesign.

</domain>

<decisions>
## Implementation Decisions

### Map Refresh After Route Edits (DEBT-02)
- **D-01:** Full map redraw after every route edit (add/remove/reorder/replace). Clear all markers and polyline, re-render from updated plan data. No incremental diffing.
- **D-02:** Re-fit map bounds to full route after each edit. Map zooms to show all stops so user sees the complete updated route.

### Stats Bar (DEBT-03)
- **D-03:** Stats bar (distance, drive time, budget) always visible across all tabs, not just overview. After any route edit, stats update immediately regardless of active tab.

### Drive Limit Enforcement (DEBT-04)
- **D-04:** Two-tier enforcement system:
  - **Soft limit:** User-configured `max_drive_time_per_day`. Days exceeding this get a warning flag but are accepted.
  - **Hard limit:** 130% of configured max. Post-generation validation rejects routes where any day exceeds the hard limit and triggers a retry.
- **D-05:** Ferry time does NOT count toward the drive limit. Only actual driving time is measured against the soft/hard limits. Ferry time is tracked and displayed separately so the user sees total travel time, but limit enforcement checks driving hours only.
- **D-06:** Strengthen RouteArchitect prompt to emphasize the drive limit, plus add post-generation validation as a safety net.

### Celery Registration (DEBT-01)
- **D-07:** Add `tasks.replace_stop_job` to the Celery include list in `tasks/__init__.py`. One-line fix, no design decisions needed.

### Claude's Discretion
- Implementation details for the post-generation validation (retry count, error messaging)
- Exact prompt wording for strengthened drive limit instructions
- How to surface soft-limit warnings in the UI (badge, color, tooltip — must be in German)

### Folded Todos
- "RouteArchitect ignores daily drive limits and suggests ferries/islands" — directly addressed by DEBT-04 decisions above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backend — Celery & Tasks
- `backend/tasks/__init__.py` — Celery app definition with include list (DEBT-01 fix location)
- `backend/tasks/replace_stop_job.py` — Replace stop task implementation

### Backend — Route Architect
- `backend/agents/route_architect.py` — RouteArchitect agent with drive limit prompt (line 113: `Maximale Fahrzeit pro Tag`)
- `backend/models/travel_request.py` — TravelRequest model with `max_drive_hours_per_day` field

### Frontend — Map
- `frontend/js/maps.js` — Map initialization, marker creation (`createDivMarker`), guide map state (`_guideMap`)
- `frontend/js/guide.js` — `renderGuide()` (line 72), `renderStatsBar()` (line 1049), route edit SSE handlers (lines 2298-2930)

### Frontend — Stats
- `frontend/js/guide.js` — Stats bar rendering in `renderGuide()` (lines 83-93), `renderStatsBar()` function (line 1049)

### Planning
- `.planning/REQUIREMENTS.md` — DEBT-01 through DEBT-04 definitions
- `.planning/ROADMAP.md` — Phase 8 success criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `renderStatsBar(plan)` in guide.js — already renders stats HTML, just needs to be called on all tabs
- `createDivMarker(map, pos, html, onClick)` in maps.js — marker creation function for redraw
- `openSSE(jobId, handlers)` in api.js — already wired into all edit complete handlers
- `call_with_retry(fn, ...)` in retry_helper.py — can wrap post-generation validation retries

### Established Patterns
- All route edit SSE handlers follow the same pattern: `*_complete` → update `S.result` → `renderGuide(data, tab)`
- Map is initialized via `initGuideMap(el)` which creates a `google.maps.Map` instance cached in `_guideMap`
- Markers are created via `createDivMarker()` overlay pattern, not native Google markers

### Integration Points
- Route edit complete handlers in guide.js (remove_stop_complete, add_stop_complete, reorder_stops_complete, replace_stop_complete) — all need map redraw call added
- `renderGuide()` function — stats bar rendering needs to work on all tabs, not just overview
- RouteArchitect prompt construction — needs stronger drive limit language + ferry time separation
- Post-generation validation — new logic after RouteArchitect returns, before proceeding to next pipeline step

</code_context>

<specifics>
## Specific Ideas

- Two-tier drive limit (soft warning + 130% hard reject) is a user-specified requirement, not a suggestion
- Ferry time explicitly excluded from drive limit calculation — island trips should not be penalized for ferry crossings
- Stats bar must be "always visible" — this was a deliberate choice over "refresh on tab switch"

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-tech-debt-stabilization*
*Context gathered: 2026-03-27*
