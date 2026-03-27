# Phase 7: Ferry-Aware Route Edits - Research

**Researched:** 2026-03-26
**Domain:** Route edit code paths -- swapping google_directions_simple for google_directions_with_ferry
**Confidence:** HIGH

## Summary

This phase is a mechanical integration fix. Three backend files (`route_edit_helpers.py`, `replace_stop_job.py`, `day_planner.py`) use `google_directions_simple` (2-tuple: hours, km) where they should use `google_directions_with_ferry` (4-tuple: hours, km, polyline, is_ferry). The reference implementation already exists in `main.py:_enrich_one()` (line 824). All ferry infrastructure -- the function itself, the island lookup table, the TravelStop model fields -- was built in Phase 2 and is fully operational.

The change is small in scope (3 files + test updates) but critical for correctness: without it, editing stops on island trips produces zero drive times for water crossings.

**Primary recommendation:** Swap the function calls, unpack the 4-tuple, set ferry metadata when `is_ferry=True`, update all test mocks from 2-tuple to 4-tuple returns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** When route edits detect a ferry crossing via `google_directions_with_ferry`, the stop receives full ferry metadata: `is_ferry=True`, `ferry_hours`, `ferry_cost_chf` -- same as initial planning via `_enrich_one()` in main.py. Frontend can show ferry indicators on edited stops.
- **D-02:** `recalc_segment_directions()` in route_edit_helpers.py must unpack the 4-tuple `(hours, km, polyline, is_ferry)` and set ferry fields on the target stop when `is_ferry` is True.
- **D-03:** `day_planner.py` line 79 also gets swapped from `google_directions_simple` to `google_directions_with_ferry`. This ensures DayPlanner re-runs after edits see ferry segments and correctly deduct ferry time from daily driving budgets (per Phase 2 D-11).
- **D-04:** The import at line 7 changes from `google_directions_simple` to `google_directions_with_ferry`.
- **D-05:** `replace_stop_job.py` lines 111 and 120 switch from `google_directions_simple` to `google_directions_with_ferry`. Import at line 32 updated accordingly.
- **D-06:** Same ferry metadata propagation as route_edit_helpers -- set `is_ferry`, `ferry_hours`, `ferry_cost_chf` on the new stop and next stop when ferry detected.
- **D-07:** Existing tests in `test_route_editing.py` update mock targets from `google_directions_simple` to `google_directions_with_ferry` with 4-tuple return values.
- **D-08:** New ferry-specific test cases added: mock `google_directions_with_ferry` returning `is_ferry=True` with ferry hours/km, then assert stops receive `is_ferry`, `ferry_hours`, `ferry_cost_chf` metadata.
- **D-09:** Day planner tests (if any mock `google_directions_simple`) also updated to use the ferry-aware variant.

### Claude's Discretion
- Exact ferry_cost_chf estimation logic (may reuse existing pattern from main.py _enrich_one or Phase 2 ferry_ports.py)
- Whether to extract a shared "set_ferry_metadata" helper or inline the logic in each caller
- Polyline handling -- whether to store or discard the polyline returned by google_directions_with_ferry

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GEO-03 | System detects when Google Directions returns no route (0,0 fallback) and attempts ferry-aware alternatives | `google_directions_with_ferry` already handles this (falls back to island lookup). Swapping it into edit paths closes the gap. |
| GEO-05 | Route planning accounts for ferry time in daily driving budget | DayPlanner already has ferry time deduction logic (lines 269-278). Swapping its directions call to ferry-aware ensures it receives `is_ferry`/`ferry_hours` data from edited stops. |
</phase_requirements>

## Standard Stack

No new dependencies. This phase modifies only existing code using existing functions.

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.111.0 | HTTP API | Existing stack |
| Pydantic | >=2.7.0 | TravelStop model with ferry fields | Existing stack |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=8.0.0 | Test runner | Test updates |
| pytest-asyncio | >=0.23.0 | Async test support | Async test cases |
| pytest-mock | >=3.12.0 | mocker fixture | Mock patching |

No installation needed.

## Architecture Patterns

### The 4-Tuple Swap Pattern
**What:** Replace `google_directions_simple` (returns `(hours, km)`) with `google_directions_with_ferry` (returns `(hours, km, polyline, is_ferry)`).
**When to use:** Every code path that calls `google_directions_simple` and operates on stop data that could involve water crossings.

**Reference implementation (main.py line 824):**
```python
hours, km, _, is_ferry = await google_directions_with_ferry(prev_location, place)
if hours > 0:
    opt["drive_hours"] = hours
    opt["drive_km"] = km
    if is_ferry:
        opt["is_ferry_required"] = True
        opt["ferry_hours"] = hours
```

### Ferry Metadata Pattern
**What:** When `is_ferry=True`, set three fields on the stop dict: `is_ferry`, `ferry_hours`, `ferry_cost_chf`.
**Formula:** `ferry_cost_chf = 50.0 + (km * 0.5)` (CHF 50 base + CHF 0.50/km, established in Phase 2).

**Example for route_edit_helpers:**
```python
hours, km, _, is_ferry = await google_directions_with_ferry(origin, destination)
if hours > 0:
    target["drive_hours_from_prev"] = round(hours, 1)
    target["drive_km_from_prev"] = round(km)
    if is_ferry:
        target["is_ferry"] = True
        target["ferry_hours"] = round(hours, 1)
        target["ferry_cost_chf"] = round(50.0 + km * 0.5, 2)
    else:
        target["is_ferry"] = False
        target["ferry_hours"] = None
        target["ferry_cost_chf"] = None
```

### Files to Modify (exact locations)

| File | Current Code | Change |
|------|-------------|--------|
| `backend/utils/route_edit_helpers.py` line 16 | `from utils.maps_helper import google_directions_simple` | `from utils.maps_helper import google_directions_with_ferry` |
| `backend/utils/route_edit_helpers.py` line 34 | `hours, km = await google_directions_simple(origin, destination)` | `hours, km, _, is_ferry = await google_directions_with_ferry(origin, destination)` + ferry metadata |
| `backend/tasks/replace_stop_job.py` line 32 | `from utils.maps_helper import geocode_google, google_directions_simple` | `from utils.maps_helper import geocode_google, google_directions_with_ferry` |
| `backend/tasks/replace_stop_job.py` line 111 | `hours, km = await google_directions_simple(prev_place, new_place)` | `hours, km, _, is_ferry = await google_directions_with_ferry(prev_place, new_place)` + ferry metadata |
| `backend/tasks/replace_stop_job.py` line 120 | `hours, km = await google_directions_simple(new_place, nxt_place)` | `hours, km, _, is_ferry = await google_directions_with_ferry(new_place, nxt_place)` + ferry metadata |
| `backend/agents/day_planner.py` line 7 | `from utils.maps_helper import geocode_google, google_directions_simple, build_maps_url` | `from utils.maps_helper import geocode_google, google_directions_with_ferry, build_maps_url` |
| `backend/agents/day_planner.py` line 79 | `dir_tasks.append(google_directions_simple(locations[i - 1], locations[i]))` | `dir_tasks.append(google_directions_with_ferry(locations[i - 1], locations[i]))` |
| `backend/agents/day_planner.py` line 91 | `hours, km = results[i]` | `hours, km, _, is_ferry = results[i]` + set ferry fields on stop |

### Anti-Patterns to Avoid
- **Forgetting the else branch:** When `is_ferry=False`, explicitly clear ferry fields (`is_ferry=False`, `ferry_hours=None`, `ferry_cost_chf=None`) so that a previously-ferry stop that gets edited to a non-ferry route loses its stale metadata.
- **Only setting metadata on one direction:** In `replace_stop_job.py`, both the prev->new AND new->next segments must check for ferry and set metadata on the respective stops.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Ferry detection | Custom haversine + island check | `google_directions_with_ferry()` | Already handles Google fallback + island lookup + ferry estimation |
| Ferry cost calculation | Custom per-caller formula | `50.0 + km * 0.5` (established formula) | Consistency with Phase 2 pattern |

**Key insight:** All ferry infrastructure exists. This phase is purely about wiring it into the edit paths.

## Common Pitfalls

### Pitfall 1: DayPlanner 4-Tuple Unpacking
**What goes wrong:** `day_planner.py` line 91 currently does `hours, km = results[i]`. After switching to `google_directions_with_ferry`, results are 4-tuples, causing `ValueError: too many values to unpack`.
**Why it happens:** The `_enrich_with_google` method gathers results in parallel and unpacks them in a loop.
**How to avoid:** Update the unpacking to `hours, km, _, is_ferry = results[i]` and set ferry metadata on the stop dict.
**Warning signs:** Any test that exercises DayPlanner's `_enrich_with_google` will crash immediately.

### Pitfall 2: Stale Ferry Metadata After Re-edit
**What goes wrong:** A stop marked `is_ferry=True` from a previous edit retains that flag even after being moved/replaced to a non-ferry route.
**Why it happens:** Code only sets ferry fields when `is_ferry=True` but never clears them.
**How to avoid:** Always set all three fields (`is_ferry`, `ferry_hours`, `ferry_cost_chf`) -- use `False/None/None` for non-ferry segments.
**Warning signs:** Stop cards showing ferry icon on mainland-to-mainland routes after reorder.

### Pitfall 3: DayPlanner Zero-Return Fallback
**What goes wrong:** `day_planner.py` line 81 has `async def _zero(): return (0.0, 0.0)` for cases where geocoding fails. After the swap, this must return a 4-tuple.
**Why it happens:** The fallback was written for `google_directions_simple`'s 2-tuple return.
**How to avoid:** Change to `async def _zero(): return (0.0, 0.0, "", False)`.
**Warning signs:** `ValueError` in `_enrich_with_google` when a geocode fails.

### Pitfall 4: replace_stop_job Next-Stop Ferry Metadata
**What goes wrong:** Line 120 recalculates the segment from new stop to next stop. If that segment crosses water, the NEXT stop needs ferry metadata, not the new stop.
**Why it happens:** Easy to set metadata on the wrong stop dict.
**How to avoid:** After the new->next directions call, set `is_ferry`/`ferry_hours`/`ferry_cost_chf` on `nxt` (the next stop), not `new_stop`.

## Code Examples

### route_edit_helpers.py: recalc_segment_directions (complete replacement)
```python
async def recalc_segment_directions(stops: list, index: int, start_location: str) -> None:
    from utils.maps_helper import google_directions_with_ferry

    if index < 0 or index >= len(stops):
        return

    target = stops[index]

    if index > 0:
        prev = stops[index - 1]
        origin = f"{prev['region']}, {prev.get('country', '')}"
    else:
        origin = start_location

    if not origin:
        return

    destination = f"{target['region']}, {target.get('country', '')}"
    hours, km, _, is_ferry = await google_directions_with_ferry(origin, destination)
    if hours > 0:
        target["drive_hours_from_prev"] = round(hours, 1)
        target["drive_km_from_prev"] = round(km)
    if is_ferry:
        target["is_ferry"] = True
        target["ferry_hours"] = round(hours, 1)
        target["ferry_cost_chf"] = round(50.0 + km * 0.5, 2)
    else:
        target["is_ferry"] = False
        target["ferry_hours"] = None
        target["ferry_cost_chf"] = None
```

### Test mock pattern (4-tuple, non-ferry)
```python
with patch("utils.maps_helper.google_directions_with_ferry",
           new_callable=AsyncMock, return_value=(2.5, 200.0, "poly", False)):
    await recalc_segment_directions(stops, 1, "Liestal, Schweiz")
assert stops[1]["drive_hours_from_prev"] == 2.5
assert stops[1]["is_ferry"] is False
```

### Test mock pattern (4-tuple, ferry)
```python
with patch("utils.maps_helper.google_directions_with_ferry",
           new_callable=AsyncMock, return_value=(5.0, 200.0, "", True)):
    await recalc_segment_directions(stops, 1, "Liestal, Schweiz")
assert stops[1]["is_ferry"] is True
assert stops[1]["ferry_hours"] == 5.0
assert stops[1]["ferry_cost_chf"] == 150.0  # 50 + 200*0.5
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio, pytest-mock |
| Config file | `backend/tests/conftest.py` |
| Quick run command | `cd /Users/stefan/Code/DetourAI/backend && python3 -m pytest tests/test_route_editing.py tests/test_ferry.py -x -v` |
| Full suite command | `cd /Users/stefan/Code/DetourAI/backend && python3 -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GEO-03 | recalc_segment_directions uses ferry-aware directions | unit | `cd backend && python3 -m pytest tests/test_route_editing.py -x -k "recalc_segment"` | Exists (needs mock update) |
| GEO-03 | replace_stop_job uses ferry-aware directions | unit | `cd backend && python3 -m pytest tests/test_route_editing.py -x -k "ferry"` | New test needed |
| GEO-05 | DayPlanner _enrich_with_google uses ferry-aware directions | unit | `cd backend && python3 -m pytest tests/test_ferry.py -x -k "day_planner or fallback"` | Partially exists |
| GEO-03+05 | Ferry metadata set on stops after edit | unit | `cd backend && python3 -m pytest tests/test_route_editing.py -x -k "ferry_metadata"` | New test needed |

### Sampling Rate
- **Per task commit:** `cd /Users/stefan/Code/DetourAI/backend && python3 -m pytest tests/test_route_editing.py tests/test_ferry.py -x -v`
- **Per wave merge:** `cd /Users/stefan/Code/DetourAI/backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Update existing mocks in `test_route_editing.py` from 2-tuple to 4-tuple returns (lines 137-138, 152-153, 177-178, 268-269)
- [ ] New test: `test_recalc_segment_directions_ferry` -- mock returns `is_ferry=True`, assert ferry metadata on stop
- [ ] New test: `test_replace_stop_ferry_metadata` -- mock returns `is_ferry=True` for both prev->new and new->next, assert metadata on correct stops

## Discretion Recommendations

### Ferry Cost Calculation
**Recommendation:** Inline the formula `50.0 + km * 0.5` at each call site rather than extracting a helper. There are only 4 call sites (route_edit_helpers x1, replace_stop_job x2, day_planner x1), and the formula is a one-liner. A helper adds indirection for minimal DRY benefit.

### Shared set_ferry_metadata Helper
**Recommendation:** Do NOT extract a shared helper. The logic is 5 lines and differs slightly per caller (route_edit_helpers sets on `target`, replace_stop_job sets on `new_stop` or `nxt`, day_planner sets on `s`). A helper would need the target dict as a parameter, saving almost nothing.

### Polyline Handling
**Recommendation:** Discard the polyline (`_` in unpacking). The edit paths don't render polylines; they only need hours/km/ferry status. The polyline is already stored from the initial planning phase if needed.

## Sources

### Primary (HIGH confidence)
- `backend/utils/maps_helper.py` lines 125-156 -- both `google_directions_simple` and `google_directions_with_ferry` signatures verified
- `backend/main.py` lines 823-835 -- `_enrich_one()` reference implementation verified
- `backend/utils/route_edit_helpers.py` -- current implementation verified (uses `google_directions_simple`)
- `backend/tasks/replace_stop_job.py` -- current implementation verified (uses `google_directions_simple` at lines 32, 111, 120)
- `backend/agents/day_planner.py` -- current implementation verified (uses `google_directions_simple` at lines 7, 79, 91)
- `backend/tests/test_route_editing.py` -- current test mocks verified (2-tuple returns)
- `backend/tests/test_ferry.py` -- existing ferry test patterns verified
- `backend/utils/ferry_ports.py` -- ferry infrastructure verified
- `backend/models/travel_response.py` line 99-101 -- TravelStop ferry fields verified (`is_ferry`, `ferry_hours`, `ferry_cost_chf`)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all functions already exist
- Architecture: HIGH -- reference implementation in main.py is the exact pattern to replicate
- Pitfalls: HIGH -- verified by reading every line of affected code

**Research date:** 2026-03-26
**Valid until:** 2026-04-26 (stable -- internal code patterns, no external dependencies)
