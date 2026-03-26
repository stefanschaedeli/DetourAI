---
phase: "03-route-editing"
plan: "01"
subsystem: "backend/tasks, backend/utils"
tags: [route-editing, celery-tasks, edit-lock, helpers]
dependency_graph:
  requires: [replace_stop_job.py pattern, travel_db, maps_helper, debug_logger]
  provides: [route_edit_helpers, route_edit_lock, remove_stop_job, add_stop_job, reorder_stops_job]
  affects: [tasks/__init__.py, debug_logger.py]
tech_stack:
  added: []
  patterns: [advisory-edit-lock, shared-helper-extraction, celery-task-pattern]
key_files:
  created:
    - backend/utils/route_edit_helpers.py
    - backend/utils/route_edit_lock.py
    - backend/tasks/remove_stop_job.py
    - backend/tasks/add_stop_job.py
    - backend/tasks/reorder_stops_job.py
    - backend/tests/test_route_editing.py
  modified:
    - backend/tasks/__init__.py
    - backend/utils/debug_logger.py
decisions:
  - Used google_directions_simple instead of google_directions_with_ferry (function does not exist in codebase)
  - Advisory edit lock with 5-minute TTL and InMemoryStore fallback
metrics:
  duration: "4min"
  completed: "2026-03-25"
---

# Phase 03 Plan 01: Route Edit Backend Tasks Summary

Shared helpers and Celery tasks for remove/add/reorder stop operations on saved travels, with Redis advisory edit lock and 12 passing tests.

## What Was Built

### Task 1: Shared Route Edit Helpers and Edit Lock

Created `backend/utils/route_edit_helpers.py` with 5 reusable async functions extracted from the replace_stop_job.py pattern:

- `recalc_segment_directions()` - Recalculates Google Directions for a single segment
- `recalc_all_segments()` - Recalculates all segments (used after reorder)
- `recalc_arrival_days()` - Rechains arrival_day values from any index onward
- `run_day_planner_refresh()` - Re-runs DayPlannerAgent on the full plan (non-critical failure handling)
- `run_research_pipeline()` - Full research for a single stop (Activities, Restaurants, Images, TravelGuide, Accommodation)

Created `backend/utils/route_edit_lock.py` with Redis NX/EX advisory locking:
- `acquire_edit_lock()` - SET NX EX 300 pattern
- `release_edit_lock()` - DELETE pattern
- InMemoryStore fallback for dev mode (always allows)

Added `"RouteEdit": "agents/route_edit"` to debug_logger's `_COMPONENT_MAP`.

### Task 2: Three Celery Tasks and Tests

**remove_stop_job.py**: Pops stop at index, reconnects successor segment via Google Directions, rechains arrival days, re-runs DayPlanner, saves to DB. SSE events: `remove_stop_progress`, `remove_stop_complete`.

**add_stop_job.py**: Builds new stop dict, inserts at position, recalcs segments for new stop and successor, runs full research pipeline, re-runs DayPlanner. SSE events: `add_stop_progress`, `add_stop_complete`.

**reorder_stops_job.py**: Pops and reinserts stop, reassigns sequential IDs (`s["id"] = i + 1`), recalcs ALL segments via `recalc_all_segments`, rechains all arrival days, re-runs DayPlanner. SSE events: `reorder_stops_progress`, `reorder_stops_complete`.

All three tasks: follow replace_stop_job.py pattern exactly, release edit lock in `finally` block, have error handling with SSE `job_error` events.

**Tests (12 passing)**:
1. `test_recalc_arrival_days` - chain formula from index 0
2. `test_recalc_arrival_days_from_mid` - chain from mid-index
3. `test_recalc_segment_directions` - correct hours/km assignment
4. `test_recalc_segment_directions_first_stop` - uses start_location as origin
5. `test_remove_stop_reconnect` - successor gets recalculated directions
6. `test_remove_stop_arrival_days` - correct chain after removal
7. `test_add_stop_inserts_at_position` - correct insertion index
8. `test_add_stop_runs_research` - full pipeline with mocked agents
9. `test_reorder_recalcs_all` - google_directions called for every stop
10. `test_reorder_renumbers_ids` - sequential IDs after reorder
11. `test_edit_lock_acquire_release` - Redis NX/EX semantics
12. `test_edit_lock_contention` - second acquire fails

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] google_directions_with_ferry does not exist**
- **Found during:** Task 1
- **Issue:** Plan references `google_directions_with_ferry()` which was not implemented in Phase 2
- **Fix:** Used `google_directions_simple()` instead, which is the existing working function
- **Files modified:** backend/utils/route_edit_helpers.py

**2. [Rule 1 - Bug] Test mock patch paths for lazy imports**
- **Found during:** Task 2
- **Issue:** Patching `utils.route_edit_helpers.X` fails because imports are lazy (inside functions)
- **Fix:** Patched at source modules (e.g., `utils.maps_helper.google_directions_simple`, `agents.activities_agent.ActivitiesAgent`)
- **Files modified:** backend/tests/test_route_editing.py

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | cb08e91 | Shared route edit helpers and advisory edit lock |
| 2 | bb0f665 | Celery tasks for remove/add/reorder stops with 12 tests |

## Known Stubs

None - all functions are fully implemented with real logic.

## Self-Check: PASSED
