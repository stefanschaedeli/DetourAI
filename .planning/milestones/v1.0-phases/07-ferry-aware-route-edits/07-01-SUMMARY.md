---
phase: 07-ferry-aware-route-edits
plan: 01
subsystem: api
tags: [google-directions, ferry, route-editing, 4-tuple]

# Dependency graph
requires:
  - phase: 02-geographic-routing
    provides: google_directions_with_ferry function returning 4-tuple
  - phase: 03-route-editing
    provides: route_edit_helpers.py, replace_stop_job.py edit infrastructure
provides:
  - Ferry-aware segment recalculation in route_edit_helpers.py
  - Ferry metadata propagation in replace_stop_job.py (both segments)
  - Ferry-aware DayPlanner enrichment with 4-tuple unpacking
  - Ferry metadata test coverage for route editing code paths
affects: [day-planner, replace-stop, route-editing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "4-tuple (hours, km, polyline, is_ferry) unpacking for all directions calls"
    - "Ferry metadata propagation: is_ferry/ferry_hours/ferry_cost_chf on stop dicts"
    - "Explicit ferry field clearing (False/None/None) on non-ferry segments"

key-files:
  created: []
  modified:
    - backend/utils/route_edit_helpers.py
    - backend/tasks/replace_stop_job.py
    - backend/agents/day_planner.py
    - backend/tests/test_route_editing.py

key-decisions:
  - "Patch targets for replace_stop_job tests use original module paths (utils.travel_db.get_travel) since imports are local"

patterns-established:
  - "Ferry cost formula CHF 50 + km*0.5 applied consistently in all route edit paths"

requirements-completed: [GEO-03, GEO-05]

# Metrics
duration: 4min
completed: 2026-03-26
---

# Phase 07 Plan 01: Ferry-Aware Route Edits Summary

**Replaced google_directions_simple with google_directions_with_ferry in all route edit code paths, propagating ferry metadata (is_ferry, ferry_hours, ferry_cost_chf) on island trip edits**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-26T16:59:00Z
- **Completed:** 2026-03-26T17:03:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- All 3 production files (route_edit_helpers.py, replace_stop_job.py, day_planner.py) now use ferry-aware 4-tuple directions
- Ferry metadata (is_ferry, ferry_hours, ferry_cost_chf) propagated on ferry crossings, explicitly cleared on non-ferry segments
- 4 new ferry-specific tests added (2 for recalc_segment_directions, 2 for replace_stop_job)
- All 16 route editing tests pass, 24 ferry tests pass (no regression), 284/286 full suite pass (2 pre-existing env failures)

## Task Commits

Each task was committed atomically:

1. **Task 1: Swap google_directions_simple to google_directions_with_ferry** - `3a3fe74` (test: RED) + `c5a8501` (feat: GREEN)
2. **Task 2: Update test mocks and add ferry metadata tests** - `f8e8c50` (test)

## Files Created/Modified
- `backend/utils/route_edit_helpers.py` - Ferry-aware recalc_segment_directions with 4-tuple unpack and metadata
- `backend/tasks/replace_stop_job.py` - Ferry metadata on both prev->new and new->next segments
- `backend/agents/day_planner.py` - 4-tuple unpack in _enrich_with_google, _zero fallback returns 4-tuple
- `backend/tests/test_route_editing.py` - All mocks updated to 4-tuple, 4 new ferry tests added

## Decisions Made
- Patch targets for replace_stop_job integration tests use original module paths (e.g., utils.travel_db.get_travel) since _replace_stop_job uses local imports inside the function body

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed mock patch targets for replace_stop_job tests**
- **Found during:** Task 2 (replace_stop_job ferry tests)
- **Issue:** Plan specified `patch("tasks.replace_stop_job.get_travel", ...)` but the function uses local imports, so the attribute doesn't exist at module level
- **Fix:** Changed patch targets to original module paths (e.g., `utils.travel_db.get_travel`, `utils.debug_logger.debug_logger`)
- **Files modified:** backend/tests/test_route_editing.py
- **Verification:** All 16 tests pass
- **Committed in:** f8e8c50

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary fix for test patching targets. No scope creep.

## Issues Encountered
None beyond the mock patching target issue documented above.

## Known Stubs
None - all ferry metadata is fully wired end-to-end.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Ferry-aware directions now consistent across all code paths (initial planning, route editing, stop replacement, day planning)
- Ready for validation testing of island trip edit scenarios

## Self-Check: PASSED

All 4 modified files exist. All 3 commit hashes verified in git log.

---
*Phase: 07-ferry-aware-route-edits*
*Completed: 2026-03-26*
