---
phase: 03-route-editing
plan: 02
subsystem: api
tags: [fastapi, endpoints, edit-lock, pydantic, celery]

requires:
  - phase: 03-route-editing/01
    provides: Celery tasks (remove/add/reorder), route_edit_lock, route_edit_helpers
provides:
  - 3 new POST endpoints for route editing (remove-stop, add-stop, reorder-stops)
  - _fire_task registration for all 3 new task types
  - Edit lock integration in all 4 edit endpoints
  - Replace-stop hints parameter for guided search
  - 10 endpoint tests covering validation and lock conflict
affects: [03-route-editing/03, frontend]

tech-stack:
  added: []
  patterns: [edit-lock-before-dispatch, request-model-per-operation]

key-files:
  created: []
  modified:
    - backend/main.py
    - backend/tasks/replace_stop_job.py
    - backend/tests/test_endpoints.py

key-decisions:
  - "Edit lock placed after input validation but before job creation to avoid unnecessary locks on invalid requests"
  - "Replace-stop search mode stores hints in job dict for future StopOptionsFinderAgent prompt enhancement"

patterns-established:
  - "Edit endpoint pattern: validate input -> acquire lock -> create job -> fire task -> return job_id"

requirements-completed: [CTL-01, CTL-02, CTL-03, CTL-04, CTL-05]

duration: 6min
completed: 2026-03-25
---

# Phase 03 Plan 02: API Endpoints Summary

**3 neue Route-Edit-Endpoints (remove/add/reorder) mit Edit-Lock, _fire_task-Integration und replace-stop hints**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-25T13:55:02Z
- **Completed:** 2026-03-25T14:01:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- 3 new POST endpoints for remove-stop, add-stop, and reorder-stops with full input validation
- _fire_task dispatcher extended with 3 new task types in both Celery and asyncio branches
- Edit lock (acquire_edit_lock) integrated into all 4 edit endpoints (remove, add, reorder, replace)
- Replace-stop enhanced with optional hints parameter for guided search
- replace_stop_job.py wrapped in try/finally with release_edit_lock
- 10 new endpoint tests all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add API endpoints, _fire_task registration, and edit lock integration** - `997ae8e` (feat)
2. **Task 2: Add endpoint tests for remove, add, reorder, and lock conflict** - `5925b09` (test)

## Files Created/Modified
- `backend/main.py` - 3 new endpoints, 3 request models, _fire_task extensions, edit lock import + integration, hints field on ReplaceStopRequest
- `backend/tasks/replace_stop_job.py` - try/finally with release_edit_lock for lock cleanup
- `backend/tests/test_endpoints.py` - 10 new tests covering all validation paths and lock conflict

## Decisions Made
- Edit lock placed after input validation but before job creation -- avoids unnecessary locks on invalid requests
- Replace-stop search mode stores hints in job dict for future StopOptionsFinderAgent prompt enhancement
- replace_stop_job.py refactored with try/finally to ensure lock release matches new task patterns

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 3 route editing endpoints are live and tested
- Plan 03 (SSE progress events + frontend integration) can proceed
- Edit lock ensures safe concurrent access across all edit operations

---
*Phase: 03-route-editing*
*Completed: 2026-03-25*
