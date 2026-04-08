---
phase: quick-260408-o3n
plan: 01
subsystem: backend
tags: [refactor, redis, services, circular-import]
dependency_graph:
  requires: []
  provides: [services/redis_store]
  affects: [backend/main.py, backend/tasks/*, backend/orchestrator.py, backend/utils/route_edit_lock.py]
tech_stack:
  added: [backend/services/]
  patterns: [service-module extraction, deferred import simplification]
key_files:
  created:
    - backend/services/__init__.py
    - backend/services/redis_store.py
  modified:
    - backend/main.py
    - backend/tasks/prefetch_accommodations.py
    - backend/tasks/update_nights_job.py
    - backend/tasks/replace_stop_job.py
    - backend/tasks/reorder_stops_job.py
    - backend/tasks/remove_stop_job.py
    - backend/tasks/run_planning_job.py
    - backend/tasks/add_stop_job.py
    - backend/utils/route_edit_lock.py
    - backend/orchestrator.py
    - backend/tests/conftest.py
    - backend/tests/test_endpoints.py
decisions:
  - "Kept _get_store() as deferred function (not top-level import) to preserve Celery worker import-time safety"
  - "Patched services.redis_store.redis_client in tests (not main.redis_client) since client now lives in services"
metrics:
  duration: 12min
  completed: 2026-04-08
  tasks_completed: 3
  files_modified: 12
---

# Phase quick-260408-o3n Plan 01: Extract Redis symbols into services/redis_store.py — Summary

**One-liner:** Extracted redis_client singleton, get_job, save_job, _USE_CELERY, _InMemoryStore, and _job_lang from main.py into new backend/services/redis_store.py, eliminating 9 circular import chains where task/orchestrator modules imported from main.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create backend/services/redis_store.py with extracted symbols | 155d9a4 | services/__init__.py, services/redis_store.py, main.py |
| 2 | Update 9 files to import redis_client from services.redis_store | 1e6d2bc | tasks/*.py (7), utils/route_edit_lock.py, orchestrator.py |
| 3 | Run full test suite to confirm no regressions | e04b243 | tests/conftest.py, tests/test_endpoints.py |

## Verification Results

- `python3 -c "from services.redis_store import redis_client, get_job, save_job, _USE_CELERY"` — OK
- `grep -rn "from main import" tasks/ orchestrator.py utils/route_edit_lock.py` — no matches
- `python3 -c "from main import app"` — App imports OK
- `python3 -m pytest tests/ -v` — 319 passed, 0 failed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mock patches referenced old redis_client location**
- **Found during:** Task 3
- **Issue:** `tests/conftest.py` patched `main.redis_client` in both `client` and `mock_job` fixtures; `tests/test_endpoints.py` patched `main.redis_client` in `mock_redis` fixture. After moving redis_client to services/redis_store, the patches no longer intercepted the actual client, causing 10 test failures (404 instead of expected status codes).
- **Fix:** Updated all three patch targets to `services.redis_store.redis_client`
- **Files modified:** backend/tests/conftest.py, backend/tests/test_endpoints.py
- **Commit:** e04b243

## Known Stubs

None.

## Threat Flags

None — pure internal refactor, no new network endpoints or trust boundaries.

## Self-Check: PASSED

- backend/services/__init__.py: FOUND
- backend/services/redis_store.py: FOUND
- Commit 155d9a4: FOUND
- Commit 1e6d2bc: FOUND
- Commit e04b243: FOUND
- 319 tests passing: CONFIRMED
