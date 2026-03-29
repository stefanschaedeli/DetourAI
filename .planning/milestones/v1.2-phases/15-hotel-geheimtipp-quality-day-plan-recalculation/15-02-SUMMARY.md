---
phase: 15-hotel-geheimtipp-quality-day-plan-recalculation
plan: "02"
subsystem: backend
tags: [celery, fastapi, route-editing, nights, recalculation]
dependency_graph:
  requires: [backend/utils/route_edit_helpers.py, backend/utils/route_edit_lock.py]
  provides: [backend/tasks/update_nights_job.py, POST /api/travels/{id}/update-nights]
  affects: [backend/main.py, backend/tests/test_endpoints.py, backend/tests/test_route_editing.py]
tech-stack:
  added: []
  patterns: [Celery task with asyncio.run, _fire_task dual-dispatch, edit lock acquire/release]
key-files:
  created:
    - backend/tasks/update_nights_job.py
  modified:
    - backend/main.py
    - backend/tests/test_endpoints.py
    - backend/tests/test_route_editing.py
decisions:
  - "Followed existing add_stop_job/remove_stop_job pattern exactly for update_nights_job"
  - "Validation (1-14 nights) done at endpoint level before lock acquisition"
  - "TDD approach: failing tests written first, then endpoint implemented"
metrics:
  duration: "~8 min"
  completed: "2026-03-29"
  tasks: 2
  files: 4
---

# Phase 15 Plan 02: Update Nights Backend Infrastructure Summary

**One-liner:** POST /api/travels/{id}/update-nights with Celery task that updates stop nights, rechains arrival_day via recalc_arrival_days, and refreshes day plans via run_day_planner_refresh.

## What Was Built

### Task 1: update_nights_job.py Celery Task

New file `backend/tasks/update_nights_job.py` following the established `add_stop_job.py`/`remove_stop_job.py` pattern:

- `_get_store()` helper for Redis/in-memory fallback
- `_update_nights_job(job_id)` async function that:
  - Loads job from Redis (travel_id, user_id, stop_id, stop_index, new_nights)
  - Updates `stops[stop_index]["nights"]` to new value
  - Pushes `update_nights_progress` SSE event
  - Calls `recalc_arrival_days(stops, from_index=stop_index)` to rechain
  - Calls `run_day_planner_refresh(plan, stops, request, job_id)` for full day plan refresh
  - Saves updated plan via `update_plan_json`
  - Pushes `update_nights_complete` SSE event with full plan
  - `try/except/finally` with `job_error` event and `release_edit_lock(travel_id)` in finally
- `update_nights_job_task` Celery task decorator

### Task 2: Endpoint + _fire_task + Tests (TDD)

**main.py changes:**

- `UpdateNightsRequest(BaseModel)` with `stop_id: int` and `nights: int` (1-14)
- `api_update_nights` endpoint at `POST /api/travels/{travel_id}/update-nights`:
  - Validates nights range (1-14), returns 400 if invalid
  - Loads travel, returns 404 if not found
  - Looks up stop_index by stop_id, returns 400 if not found
  - Acquires edit lock, returns 409 if held
  - Builds job dict, calls `save_job` + `_fire_task("update_nights_job", job_id)`
  - Returns `{"job_id": ..., "status": "editing"}`
- `_fire_task` both Celery and asyncio branches registered for `update_nights_job`

**Test coverage:**

- `test_endpoints.py`: 5 new tests (success, invalid_nights, stop_not_found, travel_not_found, lock_conflict)
- `test_route_editing.py`: 1 new task-level test (update_nights_job_recalcs_arrival_days)

## Test Results

- `pytest tests/test_endpoints.py -k "update_nights"` → 5/5 PASSED
- `pytest tests/test_route_editing.py -k "update_nights"` → 1/1 PASSED
- Full suite (excluding 2 pre-existing ANTHROPIC_API_KEY failures): 264/264 PASSED

Pre-existing failures (`test_plan_trip_success`, `test_research_accommodation_success`) require `ANTHROPIC_API_KEY` in the environment and were failing before this plan.

## Commits

- `4b03a3d`: feat(15-02): Celery-Task update_nights_job.py erstellt
- `1b9ae2e`: feat(15-02): POST /api/travels/{id}/update-nights Endpunkt + Tests

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all functionality is fully wired.

## Self-Check: PASSED
