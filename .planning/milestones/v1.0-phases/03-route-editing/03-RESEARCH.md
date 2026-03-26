# Phase 3: Route Editing - Research

**Researched:** 2026-03-25
**Domain:** Backend API + Celery tasks + Frontend UI for saved travel route modifications
**Confidence:** HIGH

## Summary

Phase 3 adds four route editing operations (remove, add, reorder, replace-enhance) to saved travels viewed in the guide view. The existing `replace_stop_job.py` Celery task provides a complete, battle-tested blueprint: endpoint receives request, creates Redis job, fires Celery task, task does Google Directions recalculation + agent research + DB save + SSE progress events. All three new operations (remove, add, reorder) follow this exact architecture.

The frontend already has all the building blocks: HTML5 drag-and-drop handlers in `route-builder.js` (lines 1098-1114), modal dialogs in `guide.js` (replace-stop modal, lines 1913-2032), SSE event listeners for progress tracking, and `renderOverview`/`renderBudget` functions that display the metrics needing refresh. The stops overview grid (`renderStopsOverview`) and stop detail view (`renderStopDetail`) are the integration points for edit controls.

**Primary recommendation:** Build three new Celery tasks (remove, add, reorder) following the `replace_stop_job.py` pattern exactly, with a shared `_recalc_metrics()` helper extracted for segment recalculation + arrival day chain + DB save. Frontend adds edit buttons to the stops overview/detail views and reuses the existing modal + SSE patterns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Route editing operates on **saved travels (SQLite) only** -- the post-planning guide view. The interactive route-building phase (Redis job state, SSE stream) remains unchanged.
- **D-02:** The existing replace-stop feature (`POST /api/travels/{id}/replace-stop`) already works on saved travels and establishes the pattern: endpoint -> Celery task -> Google Directions recalculation -> research agents -> SSE progress -> DB save.
- **D-03:** When a stop is removed, **reconnect adjacent stops**: recalculate Google Directions from the predecessor to the successor. Drop all orphaned research data (accommodations, activities, restaurants, guide text) for the removed stop.
- **D-04:** Recalculate **arrival days** for all subsequent stops after removal. Update the day planner schedule.
- **D-05:** Removal requires a **confirmation dialog** ("Stopp entfernen?") before executing -- research data took AI time to generate and cannot be easily recovered.
- **D-06:** Users add a custom stop via **place name text input** -- type a location name (e.g., "Lyon"), backend geocodes via `geocode_google()`, inserts at the specified position. No map-click insertion (that's Phase 4 territory).
- **D-07:** Insertion position specified by **"insert after stop X"** -- user picks which existing stop the new one follows. Can be refined later via drag-and-drop reorder.
- **D-08:** Custom stops get the **full research pipeline** -- Google Directions for adjacent segments, Activities, Restaurants, Accommodation, TravelGuide agents. Reuse the replace_stop_job.py Celery task pattern.
- **D-09:** Reorder uses **HTML5 drag-and-drop** -- the pattern already exists for region plan cards in route-builder.js. Extend to the saved travel's stop list in the guide view.
- **D-10:** After reorder, **recalculate all affected segments** via Google Directions. At minimum, the segments before and after the moved stop's old and new positions need recalculation.
- **D-11:** The existing replace-stop flow is **already functional** on saved travels. Enhancement: add preference-guided search hints (e.g., "mehr Strand", "weniger Fahrzeit") as optional input to the replacement search.
- **D-12:** Replace-stop stays as-is architecturally -- this phase focuses on adding remove, add, and reorder capabilities that don't exist yet.
- **D-13:** All route modifications trigger **async recalculation via Celery task with SSE progress**. Route edits involve Google Directions API calls and potentially AI research -- too slow for synchronous response.
- **D-14:** Metrics displayed after update: **total distance (km), total driving time (hours), total budget (CHF), per-stop breakdown** (drive_km_from_prev, drive_hours_from_prev). Matches existing renderOverview/renderBudget patterns.
- **D-15:** Frontend shows a **progress indicator** during recalculation (reuse SSE overlay pattern), then refreshes the display with updated metrics.
- **D-16:** Redis optimistic locking needed for concurrent edit protection -- STATE.md flagged this as requiring investigation.
- **D-17:** Each edit operation is **atomic** -- one edit at a time. UI disables edit controls while a modification is in progress (Celery task running).

### Claude's Discretion
- Exact Celery task structure (one task per operation type vs. shared task with operation parameter)
- Whether to extract shared recalculation logic from replace_stop_job.py into a reusable helper or keep separate tasks
- Progress SSE event naming (e.g., `edit_stop_progress`, `remove_stop_complete` vs. generic `route_edit_progress`)
- Whether drag-and-drop reorder of 3+ positions triggers one batch recalculation or sequential segment recalculations
- Exact German wording for confirmation dialogs and progress messages

### Deferred Ideas (OUT OF SCOPE)
- Route-builder phase editing (during interactive route-building with Redis job state)
- Map-click stop insertion (Phase 4 territory)
- Undo/redo for route edits
- Batch editing (multiple stops at once)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CTL-01 | User can remove a stop from the proposed route | `replace_stop_job.py` pattern for Celery task; `_sync_update_plan_json()` for DB persistence; arrival day chain recalc logic at lines 124-130 of replace_stop_job.py |
| CTL-02 | User can add a custom stop to the route at any position | `geocode_google()` for location lookup; full research pipeline from replace_stop_job.py (activities, restaurants, accommodation, travel guide agents); "insert after stop X" position model |
| CTL-03 | User can reorder stops in the route sequence via drag-and-drop | HTML5 drag-and-drop in route-builder.js lines 939-1114 (`_onRegionDragStart`, `_onRegionDrop`); segment recalculation via `google_directions_simple()` |
| CTL-04 | User can replace a stop with guided "find something else" flow | Already implemented at `POST /api/travels/{id}/replace-stop`; enhancement adds optional `hints` parameter to StopOptionsFinderAgent prompt |
| CTL-05 | Route metrics update after any route modification | `renderOverview()` / `renderBudget()` in guide.js already display all metrics; `DayPlannerAgent.run()` recalculates cost_estimate; `_sync_update_plan_json()` persists derived columns |
</phase_requirements>

## Architecture Patterns

### Recommended Task Structure

**Recommendation (Claude's Discretion):** Use separate Celery task files per operation with a shared helper module for common recalculation logic. Rationale: each operation has different complexity (remove is simple, add needs full research, reorder is mid-range), but they all share segment recalculation, arrival day chaining, and DB save.

```
backend/
  tasks/
    replace_stop_job.py          # existing -- keep as-is
    remove_stop_job.py           # NEW: remove + reconnect + day planner
    add_stop_job.py              # NEW: geocode + research pipeline + insert
    reorder_stops_job.py         # NEW: reorder + segment recalc
  utils/
    route_edit_helpers.py        # NEW: shared recalc logic extracted
```

### Shared Recalculation Helper

Extract from `replace_stop_job.py` lines 98-131 and 202-235 into `utils/route_edit_helpers.py`:

```python
# Source: extracted from replace_stop_job.py
async def recalc_segment_directions(
    stops: list, index: int, start_location: str
) -> None:
    """Recalculate Google Directions for segment arriving at stops[index]."""
    if index > 0:
        prev = stops[index - 1]
        prev_place = f"{prev['region']}, {prev.get('country', '')}"
    else:
        prev_place = start_location

    this_place = f"{stops[index]['region']}, {stops[index].get('country', '')}"
    if prev_place:
        hours, km = await google_directions_simple(prev_place, this_place)
        if hours > 0:
            stops[index]["drive_hours_from_prev"] = round(hours, 1)
            stops[index]["drive_km_from_prev"] = round(km)


async def recalc_arrival_days(stops: list, from_index: int = 0) -> None:
    """Rechain arrival_day from from_index onward."""
    if from_index == 0 and stops:
        stops[0]["arrival_day"] = 1
        from_index = 1
    for i in range(max(1, from_index), len(stops)):
        prev = stops[i - 1]
        day = prev.get("arrival_day", 1) + prev.get("nights", 1) + 1
        stops[i]["arrival_day"] = day


async def run_day_planner_refresh(
    plan: dict, stops: list, request, job_id: str
) -> None:
    """Re-run DayPlannerAgent on updated stops, update plan in-place."""
    from agents.day_planner import DayPlannerAgent
    all_accommodations = [
        {"stop_id": s["id"], "option": s["accommodation"]}
        for s in stops if s.get("accommodation")
    ]
    all_research = [
        {"top_activities": s.get("top_activities", []),
         "restaurants": s.get("restaurants", [])}
        for s in stops
    ]
    updated = await DayPlannerAgent(request, job_id).run(
        route={"stops": stops},
        accommodations=all_accommodations,
        activities=all_research,
    )
    plan["day_plans"] = updated.get("day_plans", plan.get("day_plans", []))
    plan["cost_estimate"] = updated.get("cost_estimate", plan.get("cost_estimate", {}))
    plan["google_maps_overview_url"] = updated.get("google_maps_overview_url", plan.get("google_maps_overview_url", ""))
```

### Operation-Specific Task Patterns

**Remove Stop (CTL-01):** Simplest task -- no AI research needed.
1. Load plan from SQLite via `get_travel()`
2. Remove stop from `stops[]`
3. Recalculate directions for the successor stop (reconnect gap)
4. Rechain arrival_days from removal index onward
5. Re-run DayPlannerAgent (updates cost_estimate, day_plans)
6. Save via `update_plan_json()`
7. Push SSE completion event with updated plan

**Add Stop (CTL-02):** Heaviest task -- full research pipeline.
1. Geocode location via `geocode_google()`
2. Build new stop dict with fresh id (max existing id + 1)
3. Insert at position (after specified stop)
4. Recalculate directions for new stop + next stop
5. Rechain arrival_days
6. Run parallel research: Activities, Restaurants, Images (same as replace_stop_job.py lines 140-162)
7. Run TravelGuide agent
8. Run Accommodation agent
9. Re-run DayPlannerAgent
10. Save + push SSE

**Reorder Stops (CTL-03):** Mid-range -- directions recalc but no AI research.
1. Move stop from old_index to new_index in `stops[]`
2. Reassign stop IDs sequentially (1, 2, 3, ...) so display order matches
3. Recalculate directions for all affected segments (at minimum: the 4 segments touching old and new position)
4. Rechain all arrival_days
5. Re-run DayPlannerAgent
6. Save + push SSE

**Recommendation for reorder recalculation (Claude's Discretion):** Recalculate ALL segments. A single move affects up to 4 segments, but computing all is simpler and safer -- Google Directions calls are fast (~200ms each), and a 10-stop trip means only 10 calls (~2s total). This avoids edge-case bugs from partial recalculation.

### API Endpoint Pattern

Follow the existing `POST /api/travels/{travel_id}/replace-stop` pattern:

```python
# Pattern for all new endpoints
class RemoveStopRequest(BaseModel):
    stop_id: int

@app.post("/api/travels/{travel_id}/remove-stop")
async def api_remove_stop(
    travel_id: int,
    body: RemoveStopRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    plan = await get_travel(travel_id, current_user.id)
    if plan is None:
        raise HTTPException(404, detail=f"Reise {travel_id} nicht gefunden")

    # Validate stop exists
    stops = plan.get("stops", [])
    stop_index = next((i for i, s in enumerate(stops) if s.get("id") == body.stop_id), None)
    if stop_index is None:
        raise HTTPException(400, detail=f"Stop {body.stop_id} nicht gefunden")

    # Minimum 1 stop must remain
    if len(stops) <= 1:
        raise HTTPException(400, detail="Mindestens ein Stopp muss verbleiben")

    job_id = uuid.uuid4().hex
    job = {
        "status": "editing",
        "travel_id": travel_id,
        "operation": "remove",
        "stop_index": stop_index,
        "user_id": current_user.id,
    }
    save_job(job_id, job)
    _fire_task("remove_stop_job", job_id)
    return {"job_id": job_id, "status": "editing"}
```

### SSE Event Naming

**Recommendation (Claude's Discretion):** Use operation-specific events for clarity, matching the existing `replace_stop_progress`/`replace_stop_complete` pattern:

| Operation | Progress Event | Complete Event |
|-----------|---------------|----------------|
| Remove | `remove_stop_progress` | `remove_stop_complete` |
| Add | `add_stop_progress` | `add_stop_complete` |
| Reorder | `reorder_stops_progress` | `reorder_stops_complete` |
| Replace | `replace_stop_progress` (existing) | `replace_stop_complete` (existing) |

This keeps the frontend event handlers simple and explicit.

### Frontend Integration Points

**Stops Overview (`renderStopsOverview`):** Add edit toolbar with drag handle, remove button per card. The overview grid (`.stops-overview-grid`) becomes a drag-and-drop zone.

**Stop Detail (`renderStopDetail`):** Add remove button next to the existing "Ersetzen" button in `.stop-header-right`.

**Add Stop UI:** "Stopp hinzufuegen" button in stops overview header. Opens modal similar to replace-stop modal with location input + "insert after" dropdown.

**Edit Lock Pattern:**
```javascript
let _editInProgress = false;

function _lockEditing() {
  _editInProgress = true;
  document.querySelectorAll('.edit-stop-btn, .remove-stop-btn, .add-stop-btn')
    .forEach(btn => btn.disabled = true);
}

function _unlockEditing() {
  _editInProgress = false;
  document.querySelectorAll('.edit-stop-btn, .remove-stop-btn, .add-stop-btn')
    .forEach(btn => btn.disabled = false);
}
```

### Anti-Patterns to Avoid
- **Direct synchronous editing:** Never modify the plan JSON and save without going through the Celery task + SSE pipeline. Even remove (which seems simple) needs DayPlannerAgent re-run.
- **Partial recalculation after reorder:** Trying to only recalculate "affected" segments is error-prone and saves negligible time. Recalculate all.
- **Renumbering stop IDs on reorder but not updating references:** `DayPlan.stops_on_route`, accommodation `stop_id` references, and any other cross-references must be updated when stop IDs change.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Directions recalculation | Custom haversine + speed estimation | `google_directions_simple()` / `google_directions_with_ferry()` | Accuracy, traffic data, ferry handling from Phase 2 |
| Budget recalculation | Manual CHF arithmetic | `DayPlannerAgent.run()` recompute | Handles fuel, activities, food allocation rules correctly |
| Research pipeline | Inline Claude calls in endpoint | Celery task with existing agent classes | Rate limiting, retry logic, SSE progress already handled |
| Confirmation dialogs | Custom dialog framework | Extend existing modal pattern from `openReplaceStopModal()` | Consistent UI, tested pattern |
| Drag-and-drop | Third-party drag library | HTML5 drag-and-drop (matches `route-builder.js`) | No dependencies, already works in the codebase |

## Common Pitfalls

### Pitfall 1: Stop ID Conflicts After Addition
**What goes wrong:** Adding a stop with `id = max(existing_ids) + 1` can collide if stop IDs were non-sequential.
**Why it happens:** Stop IDs in existing data may have gaps from prior removals.
**How to avoid:** Always scan all existing stop IDs and use `max() + 1`. The `id` field on TravelStop is sequential but not necessarily dense.
**Warning signs:** Two stops with the same ID in the stops array.

### Pitfall 2: Arrival Day Chain Breaking
**What goes wrong:** After removal or insertion, subsequent stops have incorrect arrival_day values.
**Why it happens:** The chain formula `arrival_day = prev.arrival_day + prev.nights + 1` (the +1 is for drive day) must be reapplied to ALL stops from the modification point onward.
**How to avoid:** Always call `recalc_arrival_days(stops, from_index)` after any structural change.
**Warning signs:** Day plans reference days that don't exist; calendar shows gaps.

### Pitfall 3: Forgetting to Update DayPlannerAgent After Removal
**What goes wrong:** Removing a stop leaves stale day_plans referencing the removed stop.
**Why it happens:** Temptation to skip DayPlannerAgent re-run for "simple" removal.
**How to avoid:** Every operation (including remove and reorder) MUST re-run DayPlannerAgent.
**Warning signs:** Day plan references stops that no longer exist; cost estimate unchanged after removal.

### Pitfall 4: Concurrent Edits Corrupting State
**What goes wrong:** Two simultaneous edits both read the same plan, make different changes, and the second write overwrites the first.
**Why it happens:** No locking on the SQLite plan_json during long-running Celery tasks.
**How to avoid:** D-17 mandates one edit at a time. Frontend disables controls during task execution. Backend can additionally check for running edit jobs on the same travel_id before starting a new one.
**Warning signs:** Stop data mysteriously reverting after edits.

### Pitfall 5: SSE Connection Lost During Long Edit Task
**What goes wrong:** Browser SSE connection drops during a 30+ second add-stop operation; user sees no completion.
**Why it happens:** Network interruptions, browser backgrounding.
**How to avoid:** Frontend should also poll job status as fallback. On reconnect/tab-refocus, check if the edit job completed and refresh the plan.
**Warning signs:** Progress spinner stuck indefinitely.

### Pitfall 6: Ferry-Aware Segment Recalculation
**What goes wrong:** Reorder moves a stop to/from an island position but uses `google_directions_simple` instead of `google_directions_with_ferry`.
**Why it happens:** Phase 2 added ferry detection, but new code might not use it.
**How to avoid:** Use `google_directions_with_ferry()` for all segment recalculations. Check the `is_ferry` flag on stops.
**Warning signs:** Island stops show 0 km / 0 hours after reorder.

## Code Examples

### Existing Replace-Stop Celery Task Pattern (from replace_stop_job.py)
```python
# Source: backend/tasks/replace_stop_job.py lines 257-261
@celery_app.task(name="tasks.replace_stop_job.replace_stop_job_task")
def replace_stop_job_task(job_id: str):
    """Runs _replace_stop_job() in asyncio event loop."""
    asyncio.run(_replace_stop_job(job_id))
```

### Existing _fire_task Dispatcher (from main.py)
```python
# Source: backend/main.py lines 85-111
def _fire_task(task_name: str, job_id: str, **kwargs):
    if _USE_CELERY:
        # Celery .delay() dispatch
        ...
    else:
        # asyncio.ensure_future() fallback for dev without Redis
        ...
```
New tasks must be registered in `_fire_task()` with both Celery and asyncio paths.

### Existing HTML5 Drag-and-Drop (from route-builder.js)
```javascript
// Source: frontend/js/route-builder.js lines 1101-1114
function _onRegionDragStart(e, index) {
  _dragSourceIndex = index;
  e.dataTransfer.effectAllowed = 'move';
}

function _onRegionDrop(e, targetIndex) {
  e.preventDefault();
  if (_dragSourceIndex === null || _dragSourceIndex === targetIndex) return;
  const regions = window._currentRegions;
  const [moved] = regions.splice(_dragSourceIndex, 1);
  regions.splice(targetIndex, 0, moved);
  _dragSourceIndex = null;
  updateRegionPlanUI(regions, document.querySelector('.region-summary')?.textContent || '');
}
```

### Existing Replace-Stop Modal Pattern (from guide.js)
```javascript
// Source: frontend/js/guide.js lines 1915-1984
function openReplaceStopModal(stopId, currentNights) {
  // 1. Validate saved travel
  // 2. Remove existing modal
  // 3. Create modal DOM with backdrop + form
  // 4. Append to body + animate in
  // 5. Focus input
}
```

### Existing SSE Listener for Replace (from guide.js)
```javascript
// Source: frontend/js/guide.js lines 2095-2112
_replaceStopSSE = openSSE(jobId, {
  replace_stop_progress: (data) => {
    _showReplaceProgress(data.message);
  },
  replace_stop_complete: (data) => {
    if (_replaceStopSSE) { _replaceStopSSE.close(); _replaceStopSSE = null; }
    S.result = data;
    closeReplaceStopModal();
    renderGuide(data, activeTab);
  },
});
```

## Concurrency Protection (D-16, D-17)

### Redis-Based Edit Lock

Since D-17 mandates one edit at a time and D-16 calls for Redis optimistic locking, the simplest effective approach is a Redis-based advisory lock per travel:

```python
EDIT_LOCK_TTL = 300  # 5 minutes max for any edit operation

def acquire_edit_lock(travel_id: int) -> bool:
    """Try to acquire edit lock. Returns True if acquired."""
    key = f"edit_lock:{travel_id}"
    return redis_client.set(key, "1", nx=True, ex=EDIT_LOCK_TTL)

def release_edit_lock(travel_id: int) -> None:
    redis_client.delete(f"edit_lock:{travel_id}")
```

Endpoints check the lock before creating the job. The Celery task releases the lock on completion (or TTL auto-expires as safety net). This is simpler than true optimistic locking (version counters) and sufficient given D-17's one-at-a-time constraint.

### Frontend Lock Enforcement

UI approach: when an edit is initiated, all edit buttons are disabled and a small indicator shows "Bearbeitung lauft..." until the SSE completion event arrives.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio, pytest-mock |
| Config file | No config file (convention-based) |
| Quick run command | `cd backend && python3 -m pytest tests/test_route_editing.py -x` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CTL-01 | Remove stop endpoint validates input, fires task | unit | `pytest tests/test_endpoints.py::test_remove_stop -x` | No -- Wave 0 |
| CTL-01 | Remove task reconnects segments, rechains days | unit | `pytest tests/test_route_editing.py::test_remove_stop_reconnect -x` | No -- Wave 0 |
| CTL-02 | Add stop endpoint geocodes + fires task | unit | `pytest tests/test_endpoints.py::test_add_stop -x` | No -- Wave 0 |
| CTL-02 | Add task runs full research pipeline | unit (mocked) | `pytest tests/test_route_editing.py::test_add_stop_research -x` | No -- Wave 0 |
| CTL-03 | Reorder endpoint validates indices + fires task | unit | `pytest tests/test_endpoints.py::test_reorder_stops -x` | No -- Wave 0 |
| CTL-03 | Reorder task recalculates all segments | unit (mocked) | `pytest tests/test_route_editing.py::test_reorder_recalc -x` | No -- Wave 0 |
| CTL-04 | Replace-stop with hints passes hints to agent | unit (mocked) | `pytest tests/test_route_editing.py::test_replace_with_hints -x` | No -- Wave 0 |
| CTL-05 | All operations update cost_estimate and metrics | unit (mocked) | `pytest tests/test_route_editing.py::test_metrics_update -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python3 -m pytest tests/test_route_editing.py -x`
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_route_editing.py` -- covers CTL-01 through CTL-05 task logic with mocked agents and maps
- [ ] New test cases in `tests/test_endpoints.py` -- endpoint validation for remove, add, reorder
- [ ] Mock fixtures for `google_directions_simple`, `geocode_google`, agent classes

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No route editing | Replace-stop only | Phase 0 (pre-GSD) | Users can swap one stop at a time |
| Manual location only for replace | Manual + search modes | Phase 0 | StopOptionsFinder provides AI alternatives |

**Key observation:** The codebase already solves the hardest problem (replace with full research pipeline). Remove and reorder are strictly simpler subsets. Add is equivalent to replace but with insertion instead of substitution.

## Open Questions

1. **DayPlannerAgent performance on frequent edits**
   - What we know: DayPlannerAgent uses Claude Opus and processes all stops. Each edit triggers a full re-run.
   - What's unclear: Whether frequent edits (3-4 in succession) will cause rate limiting or excessive token costs.
   - Recommendation: Accept the cost for now. D-17 serializes edits, so rate limiting is unlikely. Could optimize later by caching unchanged research data.

2. **Stop ID renumbering on reorder**
   - What we know: Stop IDs are `1, 2, 3, ...` and used in day_plans `stops_on_route` references and accommodation `stop_id` mappings.
   - What's unclear: Whether renumbering IDs after reorder will break any references.
   - Recommendation: Renumber IDs sequentially after reorder AND update all cross-references (day_plans, accommodations). The DayPlannerAgent re-run will regenerate day_plans with correct IDs.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Google Maps Directions API | Segment recalculation | Assumed (env var) | -- | None -- required |
| Redis | Edit locking, job state | Assumed (Docker) | 7 | `_InMemoryStore` fallback in main.py |
| Celery | Async task execution | Assumed (Docker) | 5.4+ | `asyncio.ensure_future()` fallback in `_fire_task()` |
| Anthropic API | Research pipeline (add stop) | Assumed (env var) | -- | TEST_MODE=true uses Haiku |

No missing dependencies -- all required services are already part of the Docker Compose stack.

## Sources

### Primary (HIGH confidence)
- `backend/tasks/replace_stop_job.py` -- Complete reference implementation for Celery task pattern (261 lines, fully read)
- `backend/main.py` lines 85-111, 2259-2421 -- `_fire_task()`, replace-stop endpoints
- `backend/utils/travel_db.py` -- All DB operations including `update_plan_json()`
- `backend/models/travel_response.py` -- TravelStop, DayPlan, CostEstimate models
- `frontend/js/guide.js` lines 1-100, 944-1058, 1913-2032 -- Guide rendering, stops overview, replace modal
- `frontend/js/route-builder.js` lines 935-1168 -- Drag-and-drop, region CRUD operations
- `frontend/js/api.js` lines 304-321 -- `apiReplaceStop()`, `apiReplaceStopSelect()` patterns
- `backend/utils/maps_helper.py` -- `google_directions_simple()`, `google_directions_with_ferry()`, `geocode_google()`

### Secondary (MEDIUM confidence)
- Redis `SET ... NX EX` pattern for advisory locking -- standard Redis pattern, well-documented

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries needed, all patterns exist in codebase
- Architecture: HIGH -- extending existing replace-stop pattern, all code read and verified
- Pitfalls: HIGH -- derived from actual code analysis of edge cases in replace_stop_job.py

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, no external dependency changes expected)
