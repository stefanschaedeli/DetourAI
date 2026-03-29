# Phase 15: Hotel Geheimtipp Quality + Day Plan Recalculation - Research

**Researched:** 2026-03-29
**Domain:** Backend post-processing (haversine filter, dedup), Celery task pattern, Frontend nights edit UX
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Primary fix is prompt-level: include the stop's lat/lon coordinates explicitly in the accommodation researcher prompt (e.g., "Zentrum: 47.38°N, 8.54°E — alle Unterkünfte müssen innerhalb von X km davon liegen."). Gives Claude a concrete geographic reference instead of just a city name.

**D-02:** Secondary safety net: haversine post-processing in `accommodation_researcher.py` after Claude returns options. Any Geheimtipp exceeding `hotel_radius_km` from the stop's lat/lon is silently dropped. User sees 3 options instead of 4 — honest, no retry for replacement.

**D-03:** The haversine validation requires geocoding the Geheimtipp hotel name to get coordinates, OR requiring Claude to return approximate coordinates. Since we chose name-based dedup (D-05), the haversine check can use Google Places `search_hotels()` which is already called in the agent (line 279-280) to resolve hotel locations.

**D-04:** Case-insensitive exact match on hotel `name` within the same stop's options. Simple safety net — Claude rarely returns duplicates within one stop.

**D-05:** No lat/lon added to AccommodationOption model. Name-based dedup is sufficient for within-stop deduplication.

### Claude's Discretion

- Nights edit UI: replacing `prompt()` with a dedicated button. Claude decides inline edit vs modal, button placement, and styling. Must follow existing edit patterns in `guide-edit.js`.
- Recalculation trigger: when nights change, Claude decides the Celery task pattern (new task vs extending existing). Follow the established pattern from add/remove/reorder stop tasks in `backend/tasks/`.
- `arrival_day` rechaining: use existing `recalc_arrival_days()` from `route_edit_helpers.py`.
- Day plan refresh: use existing `run_day_planner_refresh()` from `route_edit_helpers.py`.
- SSE progress feedback during recalculation: follow existing SSE patterns from replace_stop_job.
- Migration for existing saved travels with incorrect arrival_day: Claude decides if needed based on analysis of how `_editStopNights()` currently persists data (local-only, no backend call — may not need migration if arrival_day is recalculated on load).
- Edge cases: nights validation range (currently 1-14 in frontend), budget impact of nights changes.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ACC-01 | Hotel-Geheimtipps werden serverseitig per Haversine auf Entfernung validiert | D-02: post-process in `find_options()` using existing `haversine_km()` from `maps_helper.py`; gp_match coords already fetched in `enrich_option()` |
| ACC-02 | Geheimtipp-Duplikate innerhalb eines Stops werden entfernt | D-04: case-insensitive name dedup on `options` list before return |
| BDG-01 | `arrival_day` wird bei jeder Nächte-Änderung korrekt neu berechnet | `recalc_arrival_days(stops, from_index)` in `route_edit_helpers.py` already implements the formula |
| BDG-02 | User kann Nächte pro Stop anpassen (dedizierter Edit-Button) | Current `_editStopNights()` uses `prompt()` — replace with modal or inline edit following replace-stop modal pattern |
| BDG-03 | Tagesplan wird nach Nächte- oder Stop-Änderungen neu berechnet (Celery Task) | New Celery task following `add_stop_job.py` pattern; calls `recalc_arrival_days()` + `run_day_planner_refresh()` |
</phase_requirements>

---

## Summary

Phase 15 has two independent streams. Stream 1 (ACC-01, ACC-02) is pure backend work in `accommodation_researcher.py`: improve the Claude prompt to include explicit stop coordinates for distance context, then add a post-processing step that uses already-fetched Google Places data to verify Geheimtipp location and dedup by name. Stream 2 (BDG-01, BDG-02, BDG-03) replaces the frontend `prompt()` dialog with a proper UI, adds a new backend endpoint + Celery task for nights updates, and wires SSE progress so the user sees day-plan recalculation in real time.

Both streams are additive — they touch existing files in well-understood ways without restructuring anything. Every pattern needed already exists in the codebase: `haversine_km` is in `maps_helper.py`, `recalc_arrival_days` and `run_day_planner_refresh` are in `route_edit_helpers.py`, the Celery task skeleton is identical to `add_stop_job.py`, and the SSE/modal UX pattern is fully established in `guide-edit.js`.

**Primary recommendation:** Implement the two streams in sequence — ACC first (backend-only, low risk) then BDG (new endpoint + task + frontend). No new libraries needed.

---

## Standard Stack

### Core (all already in project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `utils/maps_helper.py` | — | `haversine_km(c1, c2)` | Already used in 3 agents, no new dependency |
| `utils/google_places.py` | — | `search_hotels(lat, lon, radius_m)` | Already called twice in `accommodation_researcher.py` |
| `utils/route_edit_helpers.py` | — | `recalc_arrival_days()`, `run_day_planner_refresh()` | Exact functions needed for BDG stream |
| Celery | >=5.4.0 | Background task for nights recalc | Project standard for all long-running edit ops |
| `utils/debug_logger.py` | — | SSE push + file logging | Required by CLAUDE.md for all new backend code |

### No New Dependencies

This phase requires zero new packages. `math.radians` / `math.asin` are stdlib — the haversine formula is already implemented in `maps_helper.py` and available for import.

**Installation:** None required.

---

## Architecture Patterns

### Recommended Project Structure (no changes)

All new files follow existing structure:

```
backend/
├── tasks/
│   └── update_nights_job.py       # NEW — Celery task for nights update + recalc
├── agents/
│   └── accommodation_researcher.py  # MODIFIED — prompt + post-processing
├── utils/
│   └── route_edit_helpers.py      # UNCHANGED — already has recalc helpers
frontend/js/
└── guide-edit.js                  # MODIFIED — replace _editStopNights()
    guide-stops.js                 # MODIFIED — update nights display trigger
```

---

### Pattern 1: Haversine Post-Processing in `accommodation_researcher.py`

**What:** After `enrich_option()` runs and resolves `gp_match`, use the gp_match coords to validate Geheimtipp distance. The Google Places data is already fetched inside `enrich_option()` — the coords are available as `gp_match["lat"]` and `gp_match["lon"]` (confirmed in `google_places.py` lines 174-175).

**When to use:** Applied inside the existing `enrich_option()` coroutine, after `gp_match` is determined. Only applies when `is_geheimtipp` is True.

**Key insight:** `enrich_option()` already calls `search_hotels(lat, lon, radius_m=req.hotel_radius_km * 1000)` and finds `gp_match` by name match. If gp_match exists and has lat/lon, we can compute haversine distance immediately — no extra API call needed.

**Example:**

```python
# Source: verified against backend/agents/accommodation_researcher.py lines 278-295
# and backend/utils/maps_helper.py line 208

from utils.maps_helper import haversine_km  # already available in project

async def enrich_option(opt: dict) -> dict:
    hotel_name = opt.get("name", "")
    is_geheimtipp = opt.get("is_geheimtipp", False)

    # ... existing booking URL + gp_match logic ...

    # ACC-01: haversine distance check for Geheimtipp
    if is_geheimtipp and gp_match and gp_match.get("lat") and gp_match.get("lon"):
        dist_km = haversine_km((lat, lon), (gp_match["lat"], gp_match["lon"]))
        if dist_km > req.hotel_radius_km:
            opt["_geheimtipp_too_far"] = True  # flag for post-filter
    return opt

# After asyncio.gather — filter flagged options
options = [o for o in options if not o.pop("_geheimtipp_too_far", False)]
```

**Edge case:** If `gp_match` is None (hotel name not found in Google Places), we cannot validate distance. In that case the Geheimtipp passes through — the prompt improvement (D-01) is the primary guard, haversine is secondary.

---

### Pattern 2: Prompt Enhancement for Geheimtipp Distance (D-01)

**What:** Add explicit lat/lon coordinates to the prompt so Claude has a concrete anchor.

**Current prompt line 118:**
```
prompt = f"""Finde genau 4 Unterkunftsoptionen in {region}, {country}.
```

**Enhanced prompt (add coordinate context block):**
```python
# Add after the `Suchradius: {req.hotel_radius_km} km` line in the prompt
coord_hint = ""
if lat and lon:
    coord_hint = f"\nStopzentrum: {lat:.4f}°N, {lon:.4f}°E — alle Unterkünfte müssen innerhalb von {req.hotel_radius_km} km davon liegen."
```

**Location in file:** Insert into the `prompt` f-string at line 123 (after `Suchradius:` line).

---

### Pattern 3: Name-Based Dedup (ACC-02)

**What:** Case-insensitive dedup on `name` within a stop's options list, applied after `asyncio.gather`.

**When to use:** Always — applied to all options, not just Geheimtipp. The dedup ensures we never show two options with the same hotel name to the user.

**Example:**
```python
# After options = list(await asyncio.gather(...)):
seen_names = set()
deduped = []
for opt in options:
    key = opt.get("name", "").strip().lower()
    if key and key not in seen_names:
        seen_names.add(key)
        deduped.append(opt)
options = deduped
result["options"] = options
```

---

### Pattern 4: Celery Task for Nights Update (BDG-03)

**What:** New task `update_nights_job.py` following `add_stop_job.py` pattern exactly.

**Task structure (confirmed from `add_stop_job.py`):**
1. Load job from Redis: `store.get(f"job:{job_id}")` → parse JSON
2. Load travel plan: `await get_travel(travel_id, user_id)`
3. Mutate stop nights in `plan["stops"]`
4. Call `recalc_arrival_days(stops, from_index=stop_index)` — rechains all following stops
5. Push SSE progress event: `"update_nights_progress"`
6. Call `run_day_planner_refresh(plan, stops, request, job_id)`
7. Call `update_plan_json(travel_id, user_id, plan)`
8. Push `"update_nights_complete"` event with full plan
9. Update job status in Redis, call `release_edit_lock(travel_id)`

**`_fire_task` registration:** Add `"update_nights_job"` branch to both the Celery and asyncio paths in `main.py`'s `_fire_task()` function (lines 88-132).

**Celery task decorator:**
```python
@celery_app.task(name="tasks.update_nights_job.update_nights_job_task")
def update_nights_job_task(job_id: str) -> None:
    asyncio.run(_update_nights_job(job_id))
```

---

### Pattern 5: New Backend Endpoint (BDG-02)

**What:** `POST /api/travels/{travel_id}/update-nights` — follows `api_remove_stop()` structure.

**Request body:**
```python
class UpdateNightsRequest(BaseModel):
    stop_id: int
    nights: int  # 1-14
```

**Endpoint logic:**
1. Get travel plan, find stop by `stop_id`
2. Validate `nights` (1 ≤ nights ≤ 14)
3. `acquire_edit_lock(travel_id)` — 409 if locked
4. Write job to Redis with `stop_id`, `nights`, `stop_index`, `travel_id`, `user_id`
5. `_fire_task("update_nights_job", job_id)`
6. Return `{"job_id": job_id, "status": "editing"}`

**Add `UpdateNightsRequest` to the Pydantic models section in `main.py`** (near the other request models around line 2288).

---

### Pattern 6: Frontend Nights Edit UI (BDG-02)

**What:** Replace `prompt()` in `_editStopNights()` (guide-edit.js lines 599-624) with a lightweight inline modal, following the existing replace-stop modal pattern.

**Current trigger (guide-stops.js lines 19-20):**
```javascript
var nightsHtml = '<span class="stop-nights-editable" onclick="event.stopPropagation(); _editStopNights(' + stop.id + ', ' + stop.nights + ')">' + ...
```

**Recommended approach (Claude's discretion):** Inline modal (not full-screen) that appears anchored near the click. Simpler than a full modal because no search/tabs needed — just a number input and confirm button.

**SSE handling (follow `_listenForReplaceComplete()` pattern):**
```javascript
// guide-edit.js — add _listenForNightsComplete()
function _listenForNightsComplete(jobId, travelId) {
  var sse = openSSE(jobId, {
    update_nights_progress: function(data) { /* show progress */ },
    update_nights_complete: function(data) {
      sse.close();
      data._saved_travel_id = travelId;
      S.result = data;
      lsSet(LS_RESULT, { savedAt: new Date().toISOString(), plan: data });
      _unlockEditing();
      renderGuide(data, activeTab);
      if (typeof GoogleMaps !== 'undefined') GoogleMaps.setGuideMarkers(data, _onMarkerClick);
    },
    job_error: function(data) {
      sse.close();
      _unlockEditing();
      alert('Fehler: ' + (data.error || 'Unbekannter Fehler'));
    }
  });
}
```

**Guards to preserve:** `_editInProgress` check must remain — prevents concurrent edits.

---

### Anti-Patterns to Avoid

- **Retrying for a replacement Geheimtipp:** D-02 explicitly says drop it silently. Do not add retry logic.
- **Adding lat/lon to AccommodationOption model:** D-05 prohibits this — name-based dedup is sufficient.
- **Using `prompt()` or `alert()` for the new nights edit:** The whole point of BDG-02 is to replace these.
- **Doing nights validation client-side only:** Validate on backend too (1 ≤ nights ≤ 14) for correctness.
- **Skipping `release_edit_lock()` in the `finally` block:** Every existing task does this — must be maintained.
- **Calling `run_day_planner_refresh` inside `accommodation_researcher.py`:** Wrong layer — day plan recalc belongs in the nights Celery task only.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Great-circle distance | Custom math | `haversine_km()` from `utils/maps_helper.py` | Already tested, used in 3 agents |
| arrival_day rechaining | Manual loop | `recalc_arrival_days(stops, from_index)` from `route_edit_helpers.py` | Formula already correct: `prev.arrival_day + prev.nights + 1` |
| Day plan refresh | Call DayPlannerAgent directly | `run_day_planner_refresh()` from `route_edit_helpers.py` | Has non-critical failure handling, correct accommodation/research assembly |
| Celery task boilerplate | New structure | Copy `add_stop_job.py` structure | Identical pattern — Redis load, modify, recalc, push events, save, release lock |
| Edit lock | Redis SET NX directly | `acquire_edit_lock()` / `release_edit_lock()` from `utils/route_edit_lock.py` | Already handles timeout, atomic SET NX |
| SSE progress | Custom EventSource setup | `openSSE(jobId, handlers)` from `api.js` | Project standard — already handles token auth via query param |

**Key insight:** Every primitive needed for this phase is already implemented and in production. This phase is pure wiring, not invention.

---

## Runtime State Inventory

> Included because nights changes affect stored travel plan data.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | SQLite `data/travels.db` — saved travels contain `arrival_day` per stop | No migration needed: `_editStopNights()` is local-state-only (guide-edit.js line 620: `lsSet(LS_RESULT, ...)` only, no backend call). Existing saved travels have correct `arrival_day` from original plan generation. The new endpoint will recalculate correctly going forward. |
| Live service config | None — no external service config references nights or arrival_day | None |
| OS-registered state | None | None |
| Secrets/env vars | None — no new env vars required | None |
| Build artifacts | None | None |

**Migration conclusion:** No data migration required. The current `_editStopNights()` only updates `localStorage` (never persists to SQLite), so no backend travel records have been corrupted by incorrect arrival_day values from user edits.

---

## Common Pitfalls

### Pitfall 1: gp_match coords may be None
**What goes wrong:** `gp_match["lat"]` raises `KeyError` or returns `None` when Google Places doesn't find the hotel or returns incomplete data.
**Why it happens:** Google Places `nearby_search` returns lat/lon from `geometry.location`, which is always present for real results — but name matching may fail (`gp_match = None`).
**How to avoid:** Guard all haversine calls with `if gp_match and gp_match.get("lat") and gp_match.get("lon")`.
**Warning signs:** `TypeError` in `enrich_option()` logs.

### Pitfall 2: `asyncio.gather` swallows filtered options
**What goes wrong:** The haversine filter runs after `asyncio.gather`, but `enrich_option()` must return the option either way (can't return `None` from gather without restructuring). Using a sentinel flag (`_geheimtipp_too_far`) and filtering after gather is the clean pattern.
**Why it happens:** `asyncio.gather` doesn't support filtering — you can't return "skip this result".
**How to avoid:** Add `_geheimtipp_too_far` flag inside `enrich_option()`, filter with `[o for o in options if not o.pop("_geheimtipp_too_far", False)]` after gather.

### Pitfall 3: Forgetting `_fire_task` registration for new task
**What goes wrong:** `_fire_task("update_nights_job", job_id)` silently does nothing because the branch isn't added to the `elif` chain in `main.py`.
**Why it happens:** `_fire_task` uses if/elif, not dynamic dispatch. Every new task must be manually registered.
**How to avoid:** Add both the Celery branch (`update_nights_job_task.delay(job_id)`) and the asyncio fallback branch (`asyncio.ensure_future(_update_nights_job(job_id))`) to `_fire_task`.
**Warning signs:** Endpoint returns 200 but no SSE events arrive.

### Pitfall 4: Celery task imports `main.py` at top level
**What goes wrong:** Importing `from main import redis_client` at top level causes circular import in Celery worker context.
**Why it happens:** Celery workers import tasks at startup before `main.py` is initialized.
**How to avoid:** Follow the existing pattern: define `_get_store()` helper that imports `redis_client` inside the function (see `add_stop_job.py` lines 12-19).

### Pitfall 5: `arrival_day` rechaining `from_index` argument
**What goes wrong:** Calling `recalc_arrival_days(stops, from_index=0)` forces stop[0].arrival_day = 1 regardless of what it was. This is correct for most cases but the `from_index` must be the index of the stop whose nights changed, not the stop after it.
**Why it happens:** The formula `stops[i].arrival_day = stops[i-1].arrival_day + stops[i-1].nights + 1` means changing stop[i].nights requires recalculating from stop[i+1] onward. But `from_index=stop_index` is also safe since `recalc_arrival_days` only forces `arrival_day=1` when `from_index==0`.
**How to avoid:** Pass `from_index=stop_index` (the index of the edited stop, not +1) — the function handles this correctly: it starts the loop at `max(1, from_index)`, so stop[stop_index] itself is recalculated from its predecessor.

### Pitfall 6: Frontend `_editInProgress` guard not cleared on SSE error
**What goes wrong:** If the Celery task fails and sends `job_error`, the edit lock on the frontend is never released if `_unlockEditing()` isn't called in the `job_error` handler.
**Why it happens:** Error paths are easy to forget.
**How to avoid:** Follow `_listenForReplaceComplete()` pattern exactly — `job_error` handler calls `_unlockEditing()` before `alert()`.

---

## Code Examples

### Haversine import (verified)
```python
# Source: backend/utils/maps_helper.py line 208 — already in project
from utils.maps_helper import haversine_km
# Usage: haversine_km((lat1, lon1), (lat2, lon2)) -> float (km)
```

### recalc_arrival_days (verified)
```python
# Source: backend/utils/route_edit_helpers.py lines 54-69
# Formula: stops[i].arrival_day = stops[i-1].arrival_day + stops[i-1].nights + 1
# Call: await recalc_arrival_days(stops, from_index=stop_index)
```

### Celery task boilerplate (verified from add_stop_job.py)
```python
# Source: backend/tasks/add_stop_job.py lines 147-150
@celery_app.task(name="tasks.update_nights_job.update_nights_job_task")
def update_nights_job_task(job_id: str) -> None:
    asyncio.run(_update_nights_job(job_id))
```

### SSE event push (verified from add_stop_job.py)
```python
# Source: backend/tasks/add_stop_job.py lines 95-97, 126
await debug_logger.push_event(job_id, "update_nights_progress", None, {
    "phase": "day_planner", "message": "Tagespläne werden aktualisiert...",
})
await debug_logger.push_event(job_id, "update_nights_complete", None, plan)
```

### Frontend SSE consumption (verified from guide-edit.js lines 820-845)
```javascript
// Source: frontend/js/guide-edit.js _listenForReplaceComplete()
var sse = openSSE(jobId, {
  update_nights_complete: function(data) { /* update S.result, re-render */ },
  job_error: function(data) { _unlockEditing(); alert(...); }
});
```

---

## Environment Availability

Step 2.6: SKIPPED — phase is backend code modifications and frontend JS changes. No new external dependencies beyond what's already running (Google Places API already in use, Redis/Celery already running).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio, pytest-mock |
| Config file | `backend/tests/conftest.py` |
| Quick run command | `cd backend && python3 -m pytest tests/test_endpoints.py tests/test_agents_mock.py -v -x` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACC-01 | Geheimtipp >radius km from stop coords is dropped from options | unit | `pytest tests/test_agents_mock.py -k "geheimtipp" -x` | ❌ Wave 0 |
| ACC-02 | Duplicate hotel name within a stop is deduplicated | unit | `pytest tests/test_agents_mock.py -k "dedup" -x` | ❌ Wave 0 |
| BDG-01 | arrival_day rechains correctly after nights change | unit | `pytest tests/test_route_editing.py -k "arrival_day" -x` | ❌ Wave 0 |
| BDG-02 | POST /update-nights endpoint creates job and returns job_id | integration | `pytest tests/test_endpoints.py -k "update_nights" -x` | ❌ Wave 0 |
| BDG-03 | update_nights_job task recalcs arrival_days and runs day planner | unit | `pytest tests/test_route_editing.py -k "update_nights" -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python3 -m pytest tests/test_endpoints.py tests/test_agents_mock.py tests/test_route_editing.py -x -q`
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_agents_mock.py` — add `test_geheimtipp_distance_filter` and `test_geheimtipp_dedup` test cases
- [ ] `tests/test_endpoints.py` — add `test_update_nights_success`, `test_update_nights_invalid`, `test_update_nights_lock_conflict`
- [ ] `tests/test_route_editing.py` — add `test_update_nights_job_recalcs_arrival_days` and `test_arrival_day_rechain_after_nights_change`

*(No new test files needed — extend existing test modules)*

---

## Open Questions

1. **Haversine fallback when gp_match is None**
   - What we know: If Google Places can't match the Geheimtipp hotel name, `gp_match = None` and we cannot validate distance.
   - What's unclear: Should a Geheimtipp without a gp_match pass through silently or be logged as unvalidated?
   - Recommendation: Pass through silently (D-02 says "silently dropped" only when exceeding threshold — if threshold can't be checked, no drop). Log at DEBUG level.

2. **`from_index` for recalc_arrival_days when editing first stop**
   - What we know: `recalc_arrival_days(stops, from_index=0)` forces `stops[0].arrival_day = 1`.
   - What's unclear: Is it always correct to force stop[0].arrival_day = 1?
   - Recommendation: Yes — stop[0] always arrives on day 1. The formula is correct as-is.

---

## Sources

### Primary (HIGH confidence)
- `backend/agents/accommodation_researcher.py` — direct code read, lines 64-300
- `backend/utils/route_edit_helpers.py` — direct code read, all functions
- `backend/utils/maps_helper.py` — direct code read, `haversine_km()` at line 208
- `backend/utils/google_places.py` — direct code read, `search_hotels()` return shape (lat/lon at lines 174-175)
- `backend/tasks/add_stop_job.py` — direct code read, full Celery task pattern
- `backend/main.py` — direct code read, `_fire_task()` lines 88-132, edit lock pattern
- `frontend/js/guide-edit.js` — direct code read, `_editStopNights()` lines 599-624, `_listenForReplaceComplete()` lines 820-845
- `frontend/js/guide-stops.js` — direct code read, nights click trigger lines 19-20

### Secondary (MEDIUM confidence)
- None required — all findings from direct code inspection.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project, verified by direct read
- Architecture: HIGH — patterns copied from existing production code
- Pitfalls: HIGH — identified from direct code analysis of edge cases
- Test map: HIGH — follows existing test file structure

**Research date:** 2026-03-29
**Valid until:** 2026-05-01 (stable codebase, no fast-moving dependencies)

## Project Constraints (from CLAUDE.md)

The following directives are mandatory and the planner must verify all tasks comply:

- **German UI text:** All user-facing strings in German (error messages, progress labels, alerts)
- **Prices in CHF:** Always
- **Type hints on all Python function signatures**
- **`call_with_retry()`** for all Claude API calls (not relevant for this phase — no new Claude calls)
- **`parse_agent_json()`** for all Claude JSON parsing (not relevant — no new Claude calls)
- **`debug_logger.log(LogLevel.X, ..., agent="...")`** for all new backend code — with correct agent key
- **Add to `_COMPONENT_MAP`** in `debug_logger.py` if new agent component is introduced (not needed here — using existing "RouteEdit" / "AccommodationResearcher" keys)
- **`async/await` throughout** — blocking calls wrapped in `asyncio.to_thread()`
- **No `fetch()` outside `api.js`** — frontend API call goes in `api.js`
- **`esc()` for all user-content HTML interpolation** in JS
- **`_editInProgress` guard** must be preserved in nights edit flow
- **Never commit `.env`**
- **TEST_MODE=true** → haiku during development
- **Git:** commit after every change as patch release with `git tag vX.X.Y && git push --tags`
