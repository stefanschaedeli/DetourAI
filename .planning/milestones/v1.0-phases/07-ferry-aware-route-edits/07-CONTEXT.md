# Phase 7: Ferry-Aware Route Edits - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace `google_directions_simple` with `google_directions_with_ferry` in all route edit code paths (route_edit_helpers.py, replace_stop_job.py, day_planner.py) so that island trip edits produce correct ferry times, distances, and metadata instead of zeros for water crossings.

Requirements: GEO-03, GEO-05

</domain>

<decisions>
## Implementation Decisions

### Ferry Flag Propagation
- **D-01:** When route edits detect a ferry crossing via `google_directions_with_ferry`, the stop receives **full ferry metadata**: `is_ferry=True`, `ferry_hours`, `ferry_cost_chf` — same as initial planning via `_enrich_one()` in main.py. Frontend can show ferry indicators on edited stops.
- **D-02:** `recalc_segment_directions()` in route_edit_helpers.py must unpack the 4-tuple `(hours, km, polyline, is_ferry)` and set ferry fields on the target stop when `is_ferry` is True.

### Day Planner Scope
- **D-03:** `day_planner.py` line 79 also gets swapped from `google_directions_simple` to `google_directions_with_ferry`. This ensures DayPlanner re-runs after edits see ferry segments and correctly deduct ferry time from daily driving budgets (per Phase 2 D-11).
- **D-04:** The import at line 7 changes from `google_directions_simple` to `google_directions_with_ferry`.

### Replace Stop Job
- **D-05:** `replace_stop_job.py` lines 111 and 120 switch from `google_directions_simple` to `google_directions_with_ferry`. Import at line 32 updated accordingly.
- **D-06:** Same ferry metadata propagation as route_edit_helpers — set `is_ferry`, `ferry_hours`, `ferry_cost_chf` on the new stop and next stop when ferry detected.

### Test Strategy
- **D-07:** Existing tests in `test_route_editing.py` update mock targets from `google_directions_simple` to `google_directions_with_ferry` with 4-tuple return values.
- **D-08:** New ferry-specific test cases added: mock `google_directions_with_ferry` returning `is_ferry=True` with ferry hours/km, then assert stops receive `is_ferry`, `ferry_hours`, `ferry_cost_chf` metadata.
- **D-09:** Day planner tests (if any mock `google_directions_simple`) also updated to use the ferry-aware variant.

### Claude's Discretion
- Exact ferry_cost_chf estimation logic (may reuse existing pattern from main.py _enrich_one or Phase 2 ferry_ports.py)
- Whether to extract a shared "set_ferry_metadata" helper or inline the logic in each caller
- Polyline handling — whether to store or discard the polyline returned by google_directions_with_ferry

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Target Files (must modify)
- `backend/utils/route_edit_helpers.py` — `recalc_segment_directions()` uses `google_directions_simple` at line 16/34
- `backend/tasks/replace_stop_job.py` — Uses `google_directions_simple` at lines 32, 111, 120
- `backend/agents/day_planner.py` — Uses `google_directions_simple` at lines 7, 79

### Reference Implementation (pattern to follow)
- `backend/main.py` lines 37-39, 824 — Already uses `google_directions_with_ferry` in `_enrich_one()` — this is the pattern to replicate
- `backend/utils/maps_helper.py` lines 125-165 — Both `google_directions_simple` (2-tuple) and `google_directions_with_ferry` (4-tuple) signatures

### Ferry Infrastructure (from Phase 2)
- `backend/utils/ferry_ports.py` — Island group lookup table, ferry speed constant
- `backend/models/travel_response.py` — `TravelStop` has `is_ferry`, `ferry_hours`, `ferry_cost_chf` fields

### Existing Tests (must update)
- `backend/tests/test_route_editing.py` — Mocks `google_directions_simple` at lines 129-268
- `backend/tests/test_ferry.py` — Existing ferry tests for `google_directions_with_ferry`

### Audit Finding
- `.planning/v1.0-MILESTONE-AUDIT.md` — Gap #6: route_edit_helpers uses google_directions_simple

### Prior Phase Context
- `.planning/phases/02-geographic-routing/02-CONTEXT.md` — Ferry detection decisions (D-01 through D-12)
- `.planning/phases/03-route-editing/03-CONTEXT.md` — Route editing architecture decisions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `google_directions_with_ferry()` in maps_helper.py — Already implemented, returns `(hours, km, polyline, is_ferry)` 4-tuple with ferry fallback
- `_enrich_one()` in main.py line 824 — Reference for how to handle the 4-tuple and set ferry metadata on stops
- `TravelStop` model already has `is_ferry`, `ferry_hours`, `ferry_cost_chf` fields from Phase 2
- Ferry tests in `test_ferry.py` — Existing mock patterns for `google_directions_with_ferry`

### Established Patterns
- `google_directions_simple` returns `(hours, km)` — 2-tuple
- `google_directions_with_ferry` returns `(hours, km, polyline, is_ferry)` — 4-tuple
- Ferry metadata set on stops: `is_ferry=True`, `ferry_hours=X`, `ferry_cost_chf=Y`
- All direction calls use `await` (async functions)

### Integration Points
- `recalc_segment_directions()` → called by remove, add, and reorder operations
- `replace_stop_job.py` → called by replace-stop Celery task
- `day_planner.py` → called by `run_day_planner_refresh()` after any route edit
- All three code paths feed into the same saved travel JSON in SQLite

</code_context>

<specifics>
## Specific Ideas

- **Mechanical swap with metadata:** The core change is swapping function calls and unpacking 4-tuples instead of 2-tuples, plus setting ferry fields. Follow the exact pattern from main.py `_enrich_one()`.
- **Island trip test case:** Athens → Santorini route edit should produce ferry segments with non-zero hours/km and is_ferry=True metadata.
- **Backward compatibility:** Existing non-ferry routes are unaffected — `google_directions_with_ferry` returns `is_ferry=False` for normal driving routes, so the 4-tuple just adds a False flag.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-ferry-aware-route-edits*
*Context gathered: 2026-03-26*
