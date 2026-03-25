---
phase: 03-route-editing
verified: 2026-03-25T18:15:29Z
status: gaps_found
score: 4/5 must-haves verified
re_verification: false
gaps:
  - truth: "Replace-stop modal includes an optional hints text field that influences search results"
    status: partial
    reason: "Hints UI field exists and is stored in the job dict, but hints are never passed to StopOptionsFinderAgent. The extra_instructions parameter of _find_and_stream_options is left as the default empty string, so user-entered preferences are silently ignored."
    artifacts:
      - path: "backend/main.py"
        issue: "_find_and_stream_options call (lines 2377-2390) omits extra_instructions=body.hints even though StopOptionsFinderAgent supports it via its extra_instructions parameter"
    missing:
      - "Pass body.hints as extra_instructions in the _find_and_stream_options call at the replace-stop search mode branch in api_replace_stop"
human_verification:
  - test: "Remove stop flow end-to-end"
    expected: "Click Entfernen on a stop, confirm dialog, stop disappears, driving times and budget recalculate"
    why_human: "Real-time SSE flow, visual confirmation dialog, metric updates require browser interaction"
  - test: "Add stop flow end-to-end"
    expected: "Click + Stopp hinzufuegen, enter location, select insert position, new stop appears with researched activities/restaurants/accommodation"
    why_human: "Modal form interaction, Celery task execution with real geocoding, SSE progress streaming"
  - test: "Drag-and-drop reorder"
    expected: "Drag a stop card to new position in the stops overview grid; order changes, driving times recalculate"
    why_human: "Drag-and-drop is a pointer event flow that cannot be verified programmatically"
  - test: "Edit controls disabled during active operation"
    expected: "While any edit is processing, remove/add/replace buttons are greyed out and unclickable"
    why_human: "Visual UI state dependent on SSE timing"
---

# Phase 03: Route Editing Verification Report

**Phase Goal:** Users can directly modify their planned route by adding, removing, reordering, and replacing stops
**Verified:** 2026-03-25T18:15:29Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Remove stop task reconnects adjacent stops and rechains arrival days | VERIFIED | `stops.pop(stop_index)` + `recalc_segment_directions` + `recalc_arrival_days` in `remove_stop_job.py` lines 73-82; 2 dedicated passing tests |
| 2 | Add stop task geocodes location, inserts at position, runs full research pipeline | VERIFIED | `stops.insert(insert_pos, new_stop)` at line 91; `run_research_pipeline` at line 109 in `add_stop_job.py`; test `test_add_stop_runs_research` passes |
| 3 | Reorder task moves stop and recalculates all segment directions | VERIFIED | `stops.pop/insert` at lines 75-76; `recalc_all_segments` at line 86; sequential ID reassignment `s["id"] = i + 1` at line 80 in `reorder_stops_job.py`; 2 passing tests |
| 4 | All three tasks re-run DayPlannerAgent and save updated plan to SQLite | VERIFIED | `run_day_planner_refresh` called in all 3 tasks; `update_plan_json` called before SSE complete event; `cost_estimate` and `day_plans` updated in-place |
| 5 | Edit lock prevents concurrent modifications | VERIFIED | `acquire_edit_lock(travel_id)` in all 4 edit endpoints; `release_edit_lock(travel_id)` in `finally` block in all 4 task files; 409 returned when lock held; `test_edit_lock_contention` passes |
| 6 | POST /api/travels/{id}/remove-stop validates stop exists and at least 1 stop remains | VERIFIED | 404 for missing travel, 400 for unknown stop_id, 400 "Mindestens ein Stopp" for single-stop plan; 3 passing endpoint tests |
| 7 | POST /api/travels/{id}/add-stop geocodes location and fires add_stop_job | VERIFIED | `geocode_google` called before job creation; 400 on geocode failure or empty location; `_fire_task("add_stop_job", job_id)` dispatches task |
| 8 | POST /api/travels/{id}/reorder-stops validates indices and fires reorder_stops_job | VERIFIED | 400 on out-of-range or equal indices; `_fire_task("reorder_stops_job", job_id)` dispatches task |
| 9 | User sees remove/add/reorder controls in guide view | VERIFIED | `remove-stop-btn` rendered in stop detail when `stops.length > 1` (line 1049); `add-stop-btn` in stops overview (line 992); `draggable="true"` on each stop card (line 955) |
| 10 | SSE handlers refresh guide view after edit operations complete | VERIFIED | All three complete handlers (`remove_stop_complete`, `add_stop_complete`, `reorder_stops_complete`) set `S.result = data` and call `renderGuide(data, 'stops')` |
| 11 | Route metrics update after any route modification (CTL-05) | VERIFIED | `run_day_planner_refresh` updates `plan["cost_estimate"]` and `plan["day_plans"]`; per-stop `drive_hours_from_prev`/`drive_km_from_prev` recalculated via `recalc_segment_directions`; full plan returned in SSE complete event |
| 12 | Replace-stop modal includes hints field that guides search results | FAILED | `replace-stop-hints` input exists in `openReplaceStopModal` (guide.js line 2299); `apiReplaceStop` sends hints to backend (api.js line 312); backend stores hints in job dict (main.py line 2404); **BUT** hints are never passed to `StopOptionsFinderAgent` — `_find_and_stream_options` call omits `extra_instructions` even though that parameter exists and would inject hints into the prompt |

**Score:** 11/12 truths verified (automated) — 1 gap found

---

## Required Artifacts

| Artifact | Expected | Level 1: Exists | Level 2: Substantive | Level 3: Wired | Status |
|----------|----------|-----------------|----------------------|----------------|--------|
| `backend/utils/route_edit_helpers.py` | Shared recalc logic: 5 async functions | 179 lines | All 5 functions present with real impl | Imported by all 3 task files | VERIFIED |
| `backend/utils/route_edit_lock.py` | Redis advisory edit lock | 36 lines | `acquire_edit_lock` with `nx=True, ex=300` | Imported by all 4 edit tasks | VERIFIED |
| `backend/tasks/remove_stop_job.py` | Celery remove task | 125 lines | Full Celery task with `stops.pop`, recalc, DB save | Registered in `tasks/__init__.py`; dispatched by `_fire_task` | VERIFIED |
| `backend/tasks/add_stop_job.py` | Celery add task with research | 150 lines | Full Celery task with `stops.insert`, research pipeline, DB save | Registered in `tasks/__init__.py`; dispatched by `_fire_task` | VERIFIED |
| `backend/tasks/reorder_stops_job.py` | Celery reorder task | 131 lines | Full Celery task with `recalc_all_segments`, ID renumbering, DB save | Registered in `tasks/__init__.py`; dispatched by `_fire_task` | VERIFIED |
| `backend/tests/test_route_editing.py` | 8+ tests for all flows | 324 lines | 12 tests, all passing | n/a (test file) | VERIFIED |
| `backend/main.py` | 3 new endpoints + `_fire_task` registration | Existing file | New endpoints + models + edit lock in 3 new + 1 existing endpoints | Endpoints registered, verified via `app.routes` introspection | VERIFIED |
| `backend/tests/test_endpoints.py` | 8+ endpoint tests for new routes | Existing file | 10 new tests added | All 10 pass | VERIFIED |
| `frontend/js/api.js` | `apiRemoveStop`, `apiAddStop`, `apiReorderStops` | Exists | 3 functions with `_fetch` to correct endpoints; hints wired to `apiReplaceStop` | Called from `guide.js` edit handlers | VERIFIED |
| `frontend/js/guide.js` | Remove/add/reorder UI + SSE handlers | Exists | All 9 required functions present; draggable cards; SSE complete handlers | Controls rendered in stop detail and overview; SSE handlers call `renderGuide` | VERIFIED |
| `frontend/styles.css` | Route editing CSS | Exists | `.btn-icon-danger`, `.drag-handle`, `.stop-overview-card.dragging`, `.drag-over`, `.modal-backdrop`, `.stops-overview-actions` | Applied via class names in guide.js templates | VERIFIED |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tasks/remove_stop_job.py` | `utils/route_edit_helpers.py` | `from utils.route_edit_helpers import` | WIRED | Line 24 imports `recalc_segment_directions, recalc_arrival_days, run_day_planner_refresh` |
| `tasks/add_stop_job.py` | `utils/route_edit_helpers.py` | `from utils.route_edit_helpers import` | WIRED | Lines 24-26 import all shared helpers |
| `tasks/reorder_stops_job.py` | `utils/route_edit_helpers.py` | `from utils.route_edit_helpers import` | WIRED | Lines 24-25 import `recalc_all_segments`, `recalc_arrival_days`, `run_day_planner_refresh` |
| All task files | `utils/route_edit_lock.py` | `acquire/release_edit_lock` | WIRED | `release_edit_lock(travel_id)` in `finally` block in all 4 task files; `acquire_edit_lock` in all 4 edit endpoints |
| `main.py` (endpoints) | `tasks/remove_stop_job.py` | `_fire_task("remove_stop_job", job_id)` | WIRED | Line 2492 dispatches; both Celery (line 104) and asyncio (line 124) branches in `_fire_task` |
| `main.py` (endpoints) | `tasks/add_stop_job.py` | `_fire_task("add_stop_job", job_id)` | WIRED | Line 2536 dispatches; both branches registered |
| `main.py` (endpoints) | `tasks/reorder_stops_job.py` | `_fire_task("reorder_stops_job", job_id)` | WIRED | Line 2572 dispatches; both branches registered |
| `main.py` api_replace_stop | hints field | `extra_instructions` in `_find_and_stream_options` | NOT WIRED | `hints` stored in job dict (line 2404) but `_find_and_stream_options` called without `extra_instructions=body.hints` (lines 2377-2390); `StopOptionsFinderAgent` has full support via `extra_instructions` parameter |
| `frontend/js/api.js` (apiRemoveStop) | `POST /api/travels/{id}/remove-stop` | `_fetch` call | WIRED | Line 318 |
| `frontend/js/api.js` (apiAddStop) | `POST /api/travels/{id}/add-stop` | `_fetch` call | WIRED | Line 325 |
| `frontend/js/api.js` (apiReorderStops) | `POST /api/travels/{id}/reorder-stops` | `_fetch` call | WIRED | Line 336 |
| `frontend/js/guide.js` (SSE handlers) | SSE events | `openSSE` event listeners | WIRED | `remove_stop_complete` (line 2025), `add_stop_complete` (line 2167), `reorder_stops_complete` (line 2225) |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `guide.js` SSE complete handlers | `data` (full plan) | Backend Celery task returns updated plan via SSE `remove_stop_complete` / `add_stop_complete` / `reorder_stops_complete` | Yes — tasks load from SQLite, modify, run DayPlanner, save back, return full plan in SSE event | FLOWING |
| `run_day_planner_refresh` | `plan["cost_estimate"]`, `plan["day_plans"]` | `DayPlannerAgent.run()` output | Yes — real agent call; updates in-place from agent result | FLOWING |
| `recalc_segment_directions` | `stop["drive_hours_from_prev"]`, `stop["drive_km_from_prev"]` | `google_directions_simple()` | Yes — real Google Directions API call | FLOWING |
| `api_replace_stop` (search mode) | hints preferences | user input via `replace-stop-hints` → `apiReplaceStop` → job dict | Stored but not consumed — `StopOptionsFinderAgent` never receives hints | DISCONNECTED |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 3 new endpoints registered | `python3 -c "from main import app; routes=[r.path for r in app.routes]; print([r for r in routes if 'stop' in r or 'reorder' in r])"` | `['/api/travels/{travel_id}/replace-stop', '/api/travels/{travel_id}/replace-stop-select', '/api/travels/{travel_id}/remove-stop', '/api/travels/{travel_id}/add-stop', '/api/travels/{travel_id}/reorder-stops']` | PASS |
| route_editing test suite | `python3 -m pytest tests/test_route_editing.py -v` | 12 passed in 0.21s | PASS |
| endpoint tests for new routes | `python3 -m pytest tests/test_endpoints.py -k "remove_stop or add_stop or reorder_stops or edit_lock"` | 10 passed in 0.19s | PASS |
| full test suite | `python3 -m pytest tests/ -v` | 267 passed, 1 warning in 1.26s | PASS |
| route_edit_helpers importable | `python3 -c "from utils.route_edit_helpers import recalc_segment_directions, recalc_all_segments, recalc_arrival_days, run_day_planner_refresh, run_research_pipeline; print('OK')"` | OK | PASS |
| route_edit_lock importable | `python3 -c "from utils.route_edit_lock import acquire_edit_lock, release_edit_lock; print('OK')"` | OK | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CTL-01 | 03-01, 03-02, 03-03 | User can remove a stop from the proposed route | SATISFIED | `remove_stop_job.py` + `api_remove_stop` endpoint + `_confirmRemoveStop` UI + 5 tests |
| CTL-02 | 03-01, 03-02, 03-03 | User can add a custom stop to the route at any position | SATISFIED | `add_stop_job.py` + `api_add_stop` endpoint + `_openAddStopModal` UI + 4 tests |
| CTL-03 | 03-01, 03-02, 03-03 | User can reorder stops via drag-and-drop | SATISFIED | `reorder_stops_job.py` + `api_reorder_stops` endpoint + drag-and-drop in guide.js + 3 tests |
| CTL-04 | 03-02, 03-03 | User can replace a stop with guided "find something else" flow (e.g., "more beach", "less driving") | PARTIAL | Replace-stop exists and is functional. Hints field added to UI and API. BUT: hints are stored in job dict but never forwarded to `StopOptionsFinderAgent.find_options_streaming()` via `extra_instructions`. User preferences are silently discarded. |
| CTL-05 | 03-01, 03-02, 03-03 | Route metrics update after any route modification | SATISFIED | `run_day_planner_refresh` updates `cost_estimate` + `day_plans`; per-stop drive times recalculated; full updated plan returned to frontend which calls `renderGuide` |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/main.py` | 2377-2390 | `extra_instructions` not passed to `_find_and_stream_options` despite `body.hints` being available | Warning | Hints silently ignored — user-entered preferences have no effect on replacement suggestions; CTL-04 partially unmet |

No other anti-patterns detected. No TODO/FIXME/placeholder comments in phase files. No empty implementations. All `release_edit_lock` calls are in `finally` blocks.

---

## Human Verification Required

### 1. Remove Stop End-to-End

**Test:** Navigate to a saved travel with 2+ stops. Click a stop to open detail. Click "Entfernen". Confirm in the dialog.
**Expected:** Stop disappears from the stops overview, driving times between adjacent stops update, budget/distance metrics update in overview tab.
**Why human:** Real-time SSE flow, visual confirmation dialog, metric updates require browser and running Celery worker.

### 2. Add Stop End-to-End

**Test:** From the stops overview, click "+ Stopp hinzufuegen". Enter a real location (e.g. "Lyon"), choose an "insert after" stop from the dropdown, click "Hinzufuegen".
**Expected:** New stop appears after the selected position with researched activities, restaurants, and accommodation. Driving times recalculate.
**Why human:** Requires live geocoding API, Celery task execution, SSE progress streaming, and full research pipeline.

### 3. Drag-and-Drop Reorder

**Test:** In the stops overview grid, drag one stop card to a different position.
**Expected:** Stops reorder visually with drag-over highlighting; after drop, the backend recalculates all segments and refreshes the view.
**Why human:** Drag-and-drop is a pointer-event flow that cannot be simulated without a browser.

### 4. Edit Controls Disabled During Active Operation

**Test:** Start any edit operation (remove/add/reorder). While the SSE progress is active, try clicking another remove or replace button.
**Expected:** All edit buttons (`.remove-stop-btn`, `.add-stop-btn`, `.replace-stop-btn`) are disabled and visually greyed out.
**Why human:** Requires observing UI state during SSE timing window.

---

## Gaps Summary

**1 automated gap** blocking full CTL-04 satisfaction:

The hints field was added to the replace-stop flow as specified, but the final wire-up was missed. `StopOptionsFinderAgent` already supports user preferences through its `extra_instructions` parameter (verified in `stop_options_finder.py` lines 48, 76-77). The `_find_and_stream_options` wrapper passes this through. The fix is a single-line change: add `extra_instructions=body.hints or ""` to the `_find_and_stream_options` call in `api_replace_stop` search mode (main.py ~line 2389).

All other phase requirements (CTL-01, CTL-02, CTL-03, CTL-05) are fully satisfied with real implementations, passing tests, and correct wiring. The full test suite (267 tests) remains green.

---

_Verified: 2026-03-25T18:15:29Z_
_Verifier: Claude (gsd-verifier)_
