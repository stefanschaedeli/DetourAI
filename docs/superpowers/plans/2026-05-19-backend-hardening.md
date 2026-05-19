# Backend Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix silent exception swallowing throughout the backend, decompose the 3144-line `main.py` into focused router modules, and add an end-to-end integration test for the planning pipeline.

**Architecture:** Silent failure fixes are surgical inline changes to existing exception handlers — log and re-raise or log and continue with visibility. The `main.py` decomposition extracts endpoints by domain into FastAPI `APIRouter` modules under `backend/routers/`, following the pattern already established by `routers/auth.py`, `routers/admin.py`, and `routers/logs.py`. Integration tests use fixed-response agent stubs (no real Anthropic API calls) to exercise the full job state machine.

**Tech Stack:** Python 3.11, FastAPI, pytest, pytest-mock, redis (mocked in tests via `_InMemoryStore`)

---

## File Structure

**Modified files:**
- `backend/main.py` — retains only: app factory, lifespan, middleware, router registration, static file serving, `_fire_task`, `_periodic_*` helpers, `_new_job`, `_calc_*` helpers, shared Pydantic request models
- `backend/routers/planning.py` — new: `/api/init-job`, `/api/plan-trip`, `/api/plan-location/{job_id}`, `/api/select-stop/{job_id}`, `/api/recompute-options/{job_id}`, `/api/patch-job/{job_id}`, `/api/confirm-route/{job_id}`, `/api/skip-to-leg-end/{job_id}`, `/api/skip-segment/{job_id}`, `/api/progress/{job_id}`, `/api/result/{job_id}`, `/api/log`
- `backend/routers/accommodations.py` — new: `/api/start-accommodations/{job_id}`, `/api/confirm-accommodations/{job_id}`, `/api/select-accommodation/{job_id}`, `/api/research-accommodation/{job_id}`, `/api/start-planning/{job_id}`
- `backend/routers/travels.py` — new: all `/api/travels/*` endpoints (list, save, update, get, delete, replan, replace-stop, replace-stop-select, remove-stop, add-stop, reorder-stops, update-nights, share, unshare, shared token)
- `backend/routers/system.py` — new: `/api/settings`, `/api/ollama/health`, `/api/maps-config`, `/health`, `/.well-known/appspecific/com.chrome.devtools.json`
- `backend/tests/test_integration_planning.py` — new: full flow integration test

**Unchanged files:** All existing routers (`auth.py`, `admin.py`, `logs.py`, `feedback.py`), all agents, all utils, all services.

---

## Task 1: Fix silent exception swallowing

**Files:**
- Modify: `backend/main.py:104`, `backend/main.py:113`, `backend/main.py:158`, `backend/main.py:185`, `backend/main.py:214`, `backend/main.py:2181`, `backend/main.py:2214`, `backend/main.py:2327`

These are the `except Exception: pass` blocks that swallow errors without logging. Each needs a `logger.warning(...)` before the `pass` (or `continue`).

- [ ] **Step 1: Read and understand all silent handlers**

Run: `grep -n "except Exception:" backend/main.py`

The bare `pass` or `continue` after these are the ones to fix. Handlers that already log (like line 106 which logs then fires SSE) are fine.

- [ ] **Step 2: Fix line 104 — SSE push on TimeoutError**

In `_fire_task._run_with_logging`, after a `TimeoutError`, the push_event call is wrapped in a bare except. Change:

```python
            try:
                await debug_logger.push_event(job_id, "job_error", None,
                                              {"message": "Job-Timeout: Die Verarbeitung hat zu lange gedauert."})
            except Exception:
                pass
```

To:

```python
            try:
                await debug_logger.push_event(job_id, "job_error", None,
                                              {"message": "Job-Timeout: Die Verarbeitung hat zu lange gedauert."})
            except Exception as _push_exc:
                import logging as _logging
                _logging.getLogger("travelman").warning("SSE push fehlgeschlagen nach Timeout: %s", _push_exc)
```

- [ ] **Step 3: Fix line 113 — SSE push on general exception**

Same pattern, second try/except in the same `_run_with_logging` function:

```python
            try:
                await debug_logger.push_event(job_id, "job_error", None, {"message": str(exc)})
            except Exception as _push_exc:
                import logging as _logging
                _logging.getLogger("travelman").warning("SSE push fehlgeschlagen nach Fehler: %s", _push_exc)
```

- [ ] **Step 4: Fix line 158 — Redis keys() failure in stuck-job reaper**

```python
        try:
            keys = redis_client.keys("job:*")
        except Exception as _redis_exc:
            logger.warning("Stuck-job reaper: Redis nicht erreichbar: %s", _redis_exc)
            continue
```

- [ ] **Step 5: Fix line 185 — push_event failure in stuck-job reaper**

```python
                try:
                    await debug_logger.push_event(
                        job_id, "job_error", None,
                        {"message": "Job wurde automatisch beendet (Timeout nach 45 Minuten)."},
                    )
                except Exception as _push_exc:
                    logger.warning("SSE push fehlgeschlagen im Stuck-Job-Reaper: %s", _push_exc)
```

- [ ] **Step 6: Fix line 240 — request body read in validation_exception_handler**

```python
    try:
        body = await request.body()
        logger.error(f"Request body: {body.decode('utf-8', errors='replace')[:2000]}")
    except Exception as _body_exc:
        logger.warning("Request body konnte nicht gelesen werden: %s", _body_exc)
```

- [ ] **Step 7: Fix line 2181 — Redis lpop in _drain_redis inside SSE progress**

```python
        except Exception as _drain_exc:
            import logging as _logging
            _logging.getLogger("travelman").warning("Redis drain fehlgeschlagen: %s", _drain_exc)
```

- [ ] **Step 8: Fix line 2214 — Redis delete cleanup in SSE finally block**

```python
                try:
                    await asyncio.to_thread(r.delete, redis_key)
                except Exception as _del_exc:
                    import logging as _logging
                    _logging.getLogger("travelman").warning("Redis cleanup fehlgeschlagen: %s", _del_exc)
```

- [ ] **Step 9: Fix line 2327 — Redis failure in /health endpoint**

```python
    except Exception as _redis_exc:
        import logging as _logging
        _logging.getLogger("travelman").warning("/health: Redis nicht erreichbar: %s", _redis_exc)
        active = 0
        redis_ok = False
```

- [ ] **Step 10: Run the full test suite to confirm nothing broke**

Run: `cd backend && python3 -m pytest tests/ -v -x 2>&1 | tail -20`

Expected: all tests pass (currently 383 passing).

- [ ] **Step 11: Commit**

```bash
git add backend/main.py
git commit -m "fix: Stille Ausnahmen in main.py protokollieren statt ignorieren"
git tag v16.3.1
git push && git push --tags
```

---

## Task 2: Extract `routers/planning.py`

**Files:**
- Create: `backend/routers/planning.py`
- Modify: `backend/main.py`

Move the following endpoints from `main.py` into a new `APIRouter` with prefix `/api`: `init-job`, `plan-trip`, `plan-location/{job_id}`, `select-stop/{job_id}`, `recompute-options/{job_id}`, `patch-job/{job_id}`, `confirm-route/{job_id}`, `skip-to-leg-end/{job_id}`, `skip-segment/{job_id}`, `progress/{job_id}`, `result/{job_id}`, `log`.

These all relate to the interactive planning flow (route building, stop selection, SSE streaming).

- [ ] **Step 1: Write a smoke test that the planning endpoints still respond**

Add to `backend/tests/test_endpoints.py` (or run existing ones):

```bash
cd backend && python3 -m pytest tests/test_endpoints.py -v -k "plan" 2>&1 | head -40
```

Note the test names that currently pass — they must still pass after the move.

- [ ] **Step 2: Create `backend/routers/planning.py`**

```python
"""Planning pipeline endpoints — route building, stop selection, SSE progress stream."""
import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from models.travel_request import TravelRequest
from models.stop_option import StopSelectRequest
from models.trip_leg import RegionPlan
from utils.auth import get_current_user, get_current_user_sse, CurrentUser
from utils.debug_logger import debug_logger, LogLevel
from utils.i18n import t as i18n_t
from services.redis_store import redis_client, get_job, save_job, _job_lang, _JOB_ID_RE
from main import _fire_task, _new_job, _check_user_quota, estimate_trip_tokens, _find_and_stream_options, _calc_route_status, _calc_budget_state

router = APIRouter(prefix="/api", tags=["planning"])
```

Then move each endpoint function body verbatim, replacing `@app.post(...)` / `@app.get(...)` with `@router.post(...)` / `@router.get(...)`.

- [ ] **Step 3: Register the router in `main.py`**

In `main.py`, after the existing `app.include_router(feedback_router)` line, add:

```python
from routers.planning import router as planning_router
app.include_router(planning_router)
```

And remove the moved endpoint definitions from `main.py`.

- [ ] **Step 4: Run tests to verify endpoints still work**

```bash
cd backend && python3 -m pytest tests/test_endpoints.py -v 2>&1 | tail -30
```

Expected: all endpoint tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/planning.py backend/main.py
git commit -m "refactor: Planungs-Endpunkte in routers/planning.py ausgelagert"
git tag v16.3.2
git push && git push --tags
```

---

## Task 3: Extract `routers/accommodations.py`

**Files:**
- Create: `backend/routers/accommodations.py`
- Modify: `backend/main.py`

Move: `start-accommodations/{job_id}`, `confirm-accommodations/{job_id}`, `select-accommodation/{job_id}`, `research-accommodation/{job_id}`, `start-planning/{job_id}`.

- [ ] **Step 1: Create `backend/routers/accommodations.py`**

```python
"""Accommodation selection and planning-start endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from models.travel_request import TravelRequest
from models.accommodation_option import AccommodationSelectRequest, AccommodationResearchRequest
from utils.auth import get_current_user, CurrentUser
from utils.debug_logger import debug_logger, LogLevel
from utils.i18n import t as i18n_t
from services.redis_store import get_job, save_job, _job_lang
from main import _fire_task, _calc_budget_state

router = APIRouter(prefix="/api", tags=["accommodations"])
```

Move the five endpoint functions verbatim, changing `@app.post` to `@router.post`.

- [ ] **Step 2: Register the router in `main.py`**

```python
from routers.accommodations import router as accommodations_router
app.include_router(accommodations_router)
```

Remove the moved definitions from `main.py`.

- [ ] **Step 3: Run tests**

```bash
cd backend && python3 -m pytest tests/ -v -x 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/accommodations.py backend/main.py
git commit -m "refactor: Unterkunft-Endpunkte in routers/accommodations.py ausgelagert"
git tag v16.3.3
git push && git push --tags
```

---

## Task 4: Extract `routers/travels.py`

**Files:**
- Create: `backend/routers/travels.py`
- Modify: `backend/main.py`

Move all `/api/travels/*` endpoints: list, save, update, get, delete, replan, replace-stop, replace-stop-select, remove-stop, add-stop, reorder-stops, update-nights, share, unshare, shared-token read. Also move `_slugify` helper. These endpoints share `save_travel`, `list_travels`, `get_travel`, `update_travel`, `delete_travel` from `utils.travel_db`.

- [ ] **Step 1: Create `backend/routers/travels.py`**

```python
"""Saved travels CRUD, sharing, and in-place route editing endpoints."""
import re
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from models.travel_response import TravelPlan
from utils.auth import get_current_user, CurrentUser
from utils.debug_logger import debug_logger, LogLevel
from utils.travel_db import save_travel, list_travels, get_travel, update_travel, delete_travel
from utils.route_edit_lock import acquire_edit_lock
from services.redis_store import get_job, save_job, _job_lang
from main import _fire_task, _calc_budget_state

router = APIRouter(prefix="/api", tags=["travels"])


def _slugify(text: str) -> str:
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^\w\s-]', '', text.lower())
    return re.sub(r'[-\s]+', '-', text).strip('-')[:50]
```

Also move the `SaveTravelRequest`, `UpdateTravelRequest` Pydantic models that are currently inline in `main.py` into this file.

Move all `@app.get/post/patch/delete` travel endpoints verbatim, changing to `@router.*`.

- [ ] **Step 2: Register the router in `main.py`**

```python
from routers.travels import router as travels_router
app.include_router(travels_router)
```

Remove moved definitions from `main.py`.

- [ ] **Step 3: Run tests**

```bash
cd backend && python3 -m pytest tests/ -v -x 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/travels.py backend/main.py
git commit -m "refactor: Reise-Endpunkte in routers/travels.py ausgelagert"
git tag v16.3.4
git push && git push --tags
```

---

## Task 5: Extract `routers/system.py`

**Files:**
- Create: `backend/routers/system.py`
- Modify: `backend/main.py`

Move: `/api/settings` (GET/PUT/POST reset), `/api/ollama/health`, `/api/maps-config`, `/health`, `/.well-known/appspecific/com.chrome.devtools.json`.

- [ ] **Step 1: Create `backend/routers/system.py`**

```python
"""System endpoints — settings, health, Ollama probe, maps config."""
import json
import os
import time as _time

import aiohttp
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from services.redis_store import redis_client
from main import _running_tasks, _TASK_TIMEOUT_SECONDS, _ACTIVE_JOB_STATUSES

router = APIRouter(tags=["system"])
```

Move the four settings endpoints, `/api/ollama/health`, `/api/maps-config`, `/health`, and `/.well-known/...` verbatim, changing `@app.*` to `@router.*`.

- [ ] **Step 2: Register the router in `main.py`**

```python
from routers.system import router as system_router
app.include_router(system_router)
```

Remove moved definitions from `main.py`.

- [ ] **Step 3: Verify `main.py` line count is under 500**

```bash
wc -l backend/main.py
```

Expected: under 500 lines (was 3144).

- [ ] **Step 4: Run full test suite**

```bash
cd backend && python3 -m pytest tests/ -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/system.py backend/main.py
git commit -m "refactor: System-Endpunkte in routers/system.py ausgelagert — main.py deutlich verschlankt"
git tag v16.3.5
git push && git push --tags
```

---

## Task 6: Integration test for the full planning pipeline

**Files:**
- Create: `backend/tests/test_integration_planning.py`

This test exercises the full job state machine: `init-job` → `plan-trip` (with mocked agent) → `select-stop` → `confirm-route` → `start-accommodations` → `confirm-accommodations` → `start-planning`. It uses `_InMemoryStore` instead of Redis and stubs out all Anthropic API calls.

- [ ] **Step 1: Create the test file**

```python
"""Integration test — full planning pipeline, no real API calls."""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

os.environ.setdefault("DATA_DIR", "/tmp/test_integration")
os.environ.setdefault("JWT_SECRET", "test_secret_that_is_exactly_32chars!")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def patch_jwt_secret(monkeypatch):
    import utils.auth as _auth_mod
    monkeypatch.setattr(_auth_mod, "JWT_SECRET", "test_secret_that_is_exactly_32chars!")


@pytest.fixture
def admin_token():
    from utils.auth import create_access_token
    return create_access_token(user_id=1, username="admin", is_admin=True)


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def client(mocker):
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True
    mock_redis.keys.return_value = []
    mock_redis.set.return_value = True
    mock_redis.lpush.return_value = 1
    mock_redis.lpop.return_value = None
    mocker.patch("services.redis_store.redis_client", mock_redis)
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


_MOCK_STOP_OPTION = {
    "id": 1,
    "region": "Lugano",
    "country": "CH",
    "drive_hours": 2.0,
    "nights": 2,
    "highlights": ["Lago di Lugano", "Altstadt"],
    "teaser": "Tessinische Hauptstadt am See",
    "option_type": "stop",
}

_MINIMAL_TRAVEL_REQUEST = {
    "start_location": "Zürich",
    "main_destination": "Lugano",
    "duration_days": 3,
    "num_adults": 2,
    "num_children": 0,
    "budget": 1000,
    "currency": "CHF",
    "travel_style": "comfort",
    "max_drive_hours_per_day": 4,
    "min_nights_per_stop": 1,
    "trip_mode": "roadtrip",
    "legs": [
        {
            "start_location": "Zürich",
            "end_location": "Lugano",
            "via_points": [],
        }
    ],
    "via_points": [],
    "preferred_activities": [],
    "food_preferences": [],
    "special_wishes": "",
    "circular_route": False,
    "proximity_origin_pct": 0.2,
    "proximity_target_pct": 0.2,
}
```

- [ ] **Step 2: Write test for job initialisation**

```python
def test_init_job_creates_job(client, auth_headers, mocker):
    """POST /api/init-job returns a job_id."""
    mocker.patch("main._check_user_quota", new=AsyncMock(return_value=None))
    res = client.post("/api/init-job", json=_MINIMAL_TRAVEL_REQUEST, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 32
```

- [ ] **Step 3: Run the test to verify it fails first (TDD)**

```bash
cd backend && python3 -m pytest tests/test_integration_planning.py::test_init_job_creates_job -v 2>&1
```

Expected at this point: either PASS (endpoint exists and works) or ImportError if routers not wired yet.

- [ ] **Step 4: Write test for stop option selection flow**

```python
def test_select_stop_advances_job(client, auth_headers, mocker):
    """POST /api/select-stop/{job_id} stores the stop in job state."""
    mocker.patch("main._check_user_quota", new=AsyncMock(return_value=None))

    # Stub StopOptionsFinderAgent to return fixed options
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=([_MOCK_STOP_OPTION], [], 1, True))
    mocker.patch("agents.stop_options_finder.StopOptionsFinderAgent", return_value=mock_agent)

    # Also stub geocoding
    mocker.patch("utils.maps_helper.geocode_google", new=AsyncMock(return_value=(47.3769, 8.5417)))
    mocker.patch("utils.maps_helper.google_directions", new=AsyncMock(return_value={"routes": [], "status": "OK"}))

    # Init job
    init_res = client.post("/api/init-job", json=_MINIMAL_TRAVEL_REQUEST, headers=auth_headers)
    assert init_res.status_code == 200
    job_id = init_res.json()["job_id"]

    # Select the stop
    select_res = client.post(
        f"/api/select-stop/{job_id}",
        json={"stop_id": 1, "option_index": 0},
        headers=auth_headers,
    )
    assert select_res.status_code == 200
    data = select_res.json()
    assert "selected_stops" in data or "job_id" in data
```

- [ ] **Step 5: Write test for job state transitions**

```python
def test_job_status_transitions(client, auth_headers, mocker):
    """confirm-route advances job status to loading_accommodations."""
    mocker.patch("main._check_user_quota", new=AsyncMock(return_value=None))
    mocker.patch("utils.maps_helper.geocode_google", new=AsyncMock(return_value=(47.3769, 8.5417)))
    mocker.patch("utils.maps_helper.google_directions", new=AsyncMock(return_value={"routes": [], "status": "OK"}))
    mocker.patch("utils.maps_helper.google_directions_with_ferry", new=AsyncMock(return_value={"routes": [], "status": "OK"}))

    init_res = client.post("/api/init-job", json=_MINIMAL_TRAVEL_REQUEST, headers=auth_headers)
    job_id = init_res.json()["job_id"]

    # Manually inject selected stops into the job state (bypasses agent)
    from services.redis_store import get_job, save_job
    job = get_job(job_id)
    job["selected_stops"] = [_MOCK_STOP_OPTION]
    job["leg_index"] = len(job.get("request", {}).get("legs", [])) - 1
    save_job(job_id, job)

    confirm_res = client.post(f"/api/confirm-route/{job_id}", headers=auth_headers)
    assert confirm_res.status_code == 200
    # After confirm-route, job should be in loading_accommodations
    updated_job = get_job(job_id)
    assert updated_job["status"] == "loading_accommodations"
```

- [ ] **Step 6: Run the full integration test file**

```bash
cd backend && python3 -m pytest tests/test_integration_planning.py -v 2>&1
```

Expected: all 3 tests pass.

- [ ] **Step 7: Run complete test suite**

```bash
cd backend && python3 -m pytest tests/ -v 2>&1 | tail -20
```

Expected: 386+ tests pass (383 existing + 3 new).

- [ ] **Step 8: Commit**

```bash
git add backend/tests/test_integration_planning.py
git commit -m "test: Integration-Tests für den Planungs-Workflow hinzugefügt"
git tag v16.3.6
git push && git push --tags
```

---

## Self-Review

**Spec coverage check:**
- ✅ Silent failures: Tasks 1 covers all 8 locations found by grep
- ✅ main.py decomposition: Tasks 2–5 extract all endpoint groups; static files and middleware remain in main.py
- ✅ Integration tests: Task 6 covers init-job, select-stop, confirm-route state transitions
- ✅ All tasks have actual code, no TBD/TODO
- ✅ Import references: `_fire_task`, `_new_job`, `_check_user_quota`, `_calc_budget_state` remain in `main.py` and are imported by routers — consistent across tasks
- ✅ `_running_tasks` and `_TASK_TIMEOUT_SECONDS` stay in `main.py` (referenced by system.py via import)
- ⚠️ Circular import risk: routers importing `from main import ...` — if this causes issues, move the shared helpers to a `services/job_helpers.py` module. The plan notes this as the fallback if a circular import error occurs during Task 2 Step 3.
