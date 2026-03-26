# Phase 3: Route Editing - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can directly modify their planned route by adding, removing, reordering, and replacing stops on saved travel plans, with live metric updates after every change. Editing targets saved travels (SQLite), not the in-progress route-building phase (Redis).

Requirements: CTL-01, CTL-02, CTL-03, CTL-04, CTL-05

</domain>

<decisions>
## Implementation Decisions

### Editing Scope
- **D-01:** Route editing operates on **saved travels (SQLite) only** — the post-planning guide view. The interactive route-building phase (Redis job state, SSE stream) remains unchanged.
- **D-02:** The existing replace-stop feature (`POST /api/travels/{id}/replace-stop`) already works on saved travels and establishes the pattern: endpoint → Celery task → Google Directions recalculation → research agents → SSE progress → DB save.

### Stop Removal (CTL-01)
- **D-03:** When a stop is removed, **reconnect adjacent stops**: recalculate Google Directions from the predecessor to the successor. Drop all orphaned research data (accommodations, activities, restaurants, guide text) for the removed stop.
- **D-04:** Recalculate **arrival days** for all subsequent stops after removal. Update the day planner schedule.
- **D-05:** Removal requires a **confirmation dialog** ("Stopp entfernen?") before executing — research data took AI time to generate and cannot be easily recovered.

### Custom Stop Addition (CTL-02)
- **D-06:** Users add a custom stop via **place name text input** — type a location name (e.g., "Lyon"), backend geocodes via `geocode_google()`, inserts at the specified position. No map-click insertion (that's Phase 4 territory).
- **D-07:** Insertion position specified by **"insert after stop X"** — user picks which existing stop the new one follows. Can be refined later via drag-and-drop reorder.
- **D-08:** Custom stops get the **full research pipeline** — Google Directions for adjacent segments, Activities, Restaurants, Accommodation, TravelGuide agents. Reuse the replace_stop_job.py Celery task pattern.

### Drag-and-Drop Reorder (CTL-03)
- **D-09:** Reorder uses **HTML5 drag-and-drop** — the pattern already exists for region plan cards in route-builder.js. Extend to the saved travel's stop list in the guide view.
- **D-10:** After reorder, **recalculate all affected segments** via Google Directions. At minimum, the segments before and after the moved stop's old and new positions need recalculation.

### Replace Stop Enhancement (CTL-04)
- **D-11:** The existing replace-stop flow is **already functional** on saved travels. Enhancement: add preference-guided search hints (e.g., "mehr Strand", "weniger Fahrzeit") as optional input to the replacement search.
- **D-12:** Replace-stop stays as-is architecturally — this phase focuses on adding remove, add, and reorder capabilities that don't exist yet.

### Metric Recalculation (CTL-05)
- **D-13:** All route modifications trigger **async recalculation via Celery task with SSE progress**. Route edits involve Google Directions API calls and potentially AI research — too slow for synchronous response.
- **D-14:** Metrics displayed after update: **total distance (km), total driving time (hours), total budget (CHF), per-stop breakdown** (drive_km_from_prev, drive_hours_from_prev). Matches existing renderOverview/renderBudget patterns.
- **D-15:** Frontend shows a **progress indicator** during recalculation (reuse SSE overlay pattern), then refreshes the display with updated metrics.

### Concurrency & State
- **D-16:** Redis optimistic locking needed for concurrent edit protection — STATE.md flagged this as requiring investigation. Research phase should spike this pattern.
- **D-17:** Each edit operation is **atomic** — one edit at a time. UI disables edit controls while a modification is in progress (Celery task running).

### Claude's Discretion
- Exact Celery task structure (one task per operation type vs. shared task with operation parameter)
- Whether to extract shared recalculation logic from replace_stop_job.py into a reusable helper or keep separate tasks
- Progress SSE event naming (e.g., `edit_stop_progress`, `remove_stop_complete` vs. generic `route_edit_progress`)
- Whether drag-and-drop reorder of 3+ positions triggers one batch recalculation or sequential segment recalculations
- Exact German wording for confirmation dialogs and progress messages

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Replace-Stop Infrastructure (primary pattern to extend)
- `backend/tasks/replace_stop_job.py` — Full Celery task for stop replacement: directions recalc, research agents, DB save, SSE events
- `backend/main.py` lines ~2270-2440 — `POST /api/travels/{id}/replace-stop` and `replace-stop-select` endpoints

### Route Building & State
- `backend/main.py` lines ~390-900 — Route building flow, `_calc_budget_state()`, streaming option finder, route enrichment
- `backend/utils/travel_db.py` — SQLite persistence for saved travels (CRUD operations)
- `backend/utils/maps_helper.py` — `geocode_google()`, `google_directions()`, `google_directions_with_ferry()`, `haversine_km()`

### Models
- `backend/models/travel_response.py` — `TravelPlan`, `TravelStop`, `DayPlan`, `CostEstimate` models
- `backend/models/stop_option.py` — `StopOption` model

### Frontend
- `frontend/js/guide.js` — Guide view with existing replace-stop UI, `renderOverview()`, `renderBudget()`, stop rendering
- `frontend/js/route-builder.js` — Route builder with HTML5 drag-and-drop for region cards (lines 939-1114)
- `frontend/js/api.js` — `apiReplaceStop()`, `apiReplaceStopSelect()` — API wrappers to extend

### Agent Pipeline
- `backend/agents/activities_agent.py` — Activities research per stop
- `backend/agents/restaurants_agent.py` — Restaurant research per stop
- `backend/agents/accommodation_researcher.py` — Accommodation research per stop
- `backend/agents/travel_guide_agent.py` — Travel guide text per stop
- `backend/agents/day_planner.py` — Day schedule with driving budget (ferry time deduction from Phase 2)

### Prior Phase Context
- `.planning/phases/01-ai-quality-stabilization/01-CONTEXT.md` — Corridor validation, quality gates (D-04: flag don't reject)
- `.planning/phases/02-geographic-routing/02-CONTEXT.md` — Ferry handling, island awareness (affects segment recalculation)

### Requirements
- `.planning/REQUIREMENTS.md` — CTL-01 through CTL-05 acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `replace_stop_job.py` — Complete Celery task pattern: directions recalc → research agents → DB save → SSE events. Primary blueprint for new edit operations.
- HTML5 drag-and-drop in `route-builder.js` (lines 939-1114) — `_onRegionDragStart`, `_onRegionDrop`, drag CSS classes. Can be extended to guide view stop list.
- `google_directions_simple()` / `google_directions_with_ferry()` in `maps_helper.py` — Segment recalculation functions ready to use.
- `_calc_budget_state()` in `main.py` — Budget tracking during route building, patterns reusable for post-edit recalculation.
- `renderOverview()` / `renderBudget()` in `guide.js` — Metric display functions, already show distance/time/budget.
- `apiReplaceStop()` / `apiReplaceStopSelect()` in `api.js` — API wrapper pattern to follow for new endpoints.

### Established Patterns
- Celery task with SSE progress events for long-running operations
- `_fetchWithAuth()` for authenticated API calls from frontend
- German-language UI text and error messages throughout
- Confirmation modals using existing modal patterns in guide.js

### Integration Points
- Guide view (`guide.js`) is where edit controls (remove, add, reorder buttons) will be added per stop
- `travel_db.py` save/update operations for persisting route modifications
- SSE event system (`debug_logger`) for progress streaming during recalculation
- Existing `POST /api/travels/{id}/replace-stop` as the architectural model for new endpoints

</code_context>

<specifics>
## Specific Ideas

- **Replace-stop as blueprint:** The existing replace-stop feature establishes the exact pattern — endpoint, Celery task, Google Directions recalc, research pipeline, SSE progress, DB save. New operations (remove, add, reorder) follow this same architecture.
- **Drag-and-drop reuse:** The region card drag-and-drop in route-builder.js (complete with CSS grab cursors, drag events, array reordering) is directly portable to the guide view's stop list.
- **One edit at a time:** Since each edit triggers a Celery task with potential AI research, edits must be sequential. UI disables controls while an edit is in progress.

</specifics>

<deferred>
## Deferred Ideas

- **Route-builder phase editing:** Adding/removing/reordering stops during the interactive route-building phase (Redis job state) — significantly more complex due to SSE streaming state. Could be a future enhancement.
- **Map-click stop insertion:** Clicking on the map to add a stop at a geographic position — requires Phase 4's map-centric layout first.
- **Undo/redo for route edits:** Would need a history stack of route states. Not needed for v1.
- **Batch editing:** Edit multiple stops at once (e.g., remove 3 stops, then recalculate once). Current one-at-a-time approach is simpler and safer.

</deferred>

---

*Phase: 03-route-editing*
*Context gathered: 2026-03-25*
