---
phase: 07-ferry-aware-route-edits
verified: 2026-03-26T17:30:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 7: Ferry-Aware Route Edits Verification Report

**Phase Goal:** Route edit operations (remove, add, reorder, replace stop) use ferry-aware directions so island trip edits produce correct drive times and distances for water crossings.
**Verified:** 2026-03-26T17:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Editing stops on an island trip recalculates segments using `google_directions_with_ferry` | VERIFIED | All three edit-path files import and call `google_directions_with_ferry`; zero remaining `google_directions_simple` references |
| 2 | Water crossing segments after route edits show correct ferry time/distance/cost | VERIFIED | `is_ferry`, `ferry_hours`, `ferry_cost_chf` set via `50.0 + km * 0.5` formula in all three files |
| 3 | Non-ferry route edits continue to work identically (`is_ferry=False`, ferry fields cleared) | VERIFIED | Explicit `else` branch in all three files sets `is_ferry=False`, `ferry_hours=None`, `ferry_cost_chf=None` |
| 4 | DayPlanner re-runs after edits see ferry segments and deduct ferry time from daily budget | VERIFIED | `_enrich_with_google` unpacks 4-tuple; `_plan_single_day` checks `is_ferry`/`ferry_hours` and injects ferry deduction block into Claude prompt; `_zero` fallback returns `(0.0, 0.0, "", False)` |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/utils/route_edit_helpers.py` | Ferry-aware `recalc_segment_directions` | VERIFIED | Line 16: local import of `google_directions_with_ferry`; line 34: 4-tuple unpack; lines 38-45: ferry metadata set/cleared |
| `backend/tasks/replace_stop_job.py` | Ferry-aware replace stop directions | VERIFIED | Line 32: module-level import; lines 111, 128: two 4-tuple calls with metadata applied to `new_stop` and `nxt` respectively |
| `backend/agents/day_planner.py` | Ferry-aware DayPlanner enrichment | VERIFIED | Line 7: top-level import; line 79: call; line 81: `_zero` returns 4-tuple; lines 91-107: metadata in both success and fallback branches; lines 282-289: ferry time deducted from daily budget in prompt |
| `backend/tests/test_route_editing.py` | Updated mocks + ferry metadata tests | VERIFIED | All existing mocks use 4-tuple `(h, km, "poly", False)`; four new ferry tests present and passing |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/utils/route_edit_helpers.py` | `backend/utils/maps_helper.py` | `from utils.maps_helper import google_directions_with_ferry` | WIRED | Local import at function entry (line 16); called at line 34 |
| `backend/tasks/replace_stop_job.py` | `backend/utils/maps_helper.py` | `from utils.maps_helper import geocode_google, google_directions_with_ferry` | WIRED | Local import inside `_replace_stop_job` (line 32); called twice at lines 111, 128 |
| `backend/agents/day_planner.py` | `backend/utils/maps_helper.py` | `from utils.maps_helper import geocode_google, google_directions_with_ferry, build_maps_url` | WIRED | Top-level import (line 7); called in `_enrich_with_google` (line 79) |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `route_edit_helpers.py::recalc_segment_directions` | `is_ferry`, `ferry_hours`, `ferry_cost_chf` | `google_directions_with_ferry` return value (4-tuple) | Yes — real Google Directions API call with ferry detection | FLOWING |
| `replace_stop_job.py::_replace_stop_job` | `new_stop["is_ferry"]`, `nxt["is_ferry"]` | `google_directions_with_ferry` (two calls, prev->new and new->next) | Yes — live API calls, results written directly to stop dicts | FLOWING |
| `day_planner.py::_enrich_with_google` | `s["is_ferry"]`, `s["ferry_hours"]`, `s["ferry_cost_chf"]` | Parallel `asyncio.gather` over `google_directions_with_ferry` calls | Yes — results propagated to stop dicts and then into day-plan context | FLOWING |
| `day_planner.py::_plan_single_day` | `ferry_hours`, `remaining_drive` | `day_ctx["is_ferry"]` / `day_ctx["ferry_hours"]` set by `_enrich_with_google` | Yes — ferry info injected into Claude prompt as `ferry_info` block | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 16 route editing tests pass (ferry + non-ferry) | `python3 -m pytest tests/test_route_editing.py -x -v` | 16 passed in 0.20s | PASS |
| All 24 ferry tests pass (no regression) | `python3 -m pytest tests/test_ferry.py -x -v` | 24 passed in 0.17s | PASS |
| Combined 40-test run passes | `python3 -m pytest tests/test_route_editing.py tests/test_ferry.py -v` | 40 passed in 0.21s | PASS |
| No `google_directions_simple` in 3 production files | `grep google_directions_simple route_edit_helpers.py replace_stop_job.py day_planner.py` | No output (exit 1) | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| GEO-03 | 07-01-PLAN.md | System detects when Google Directions returns no route (0,0 fallback) and attempts ferry-aware alternatives | SATISFIED (edit-path) | `google_directions_with_ferry` called in all edit paths; replaces the non-detecting `google_directions_simple` — closes the edit-path gap noted in REQUIREMENTS.md traceability |
| GEO-05 | 07-01-PLAN.md | Route planning accounts for ferry time in daily driving budget | SATISFIED (edit-path) | DayPlanner `_plan_single_day` deducts `ferry_hours` from `max_drive_hours_per_day` and adds a ferry time_block to the Claude prompt; `_fallback_cost_estimate` also sums `ferry_cost_chf` per stop |

**Note on GEO-03 and GEO-05 scope:** Both requirements were previously satisfied for the initial planning path in Phase 2. Phase 7 closes the remaining "edit-path" gap documented in REQUIREMENTS.md (line 95-97: "Phase 2, Phase 7 | Complete (initial), Pending (edit-path)"). After this phase, both requirements are fully satisfied across all code paths.

**Orphaned requirements check:** No requirements mapped to Phase 7 in REQUIREMENTS.md beyond GEO-03 and GEO-05. Both accounted for.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `main.py` line 653 | `google_directions_simple` still used in `_enrich_one()` (stop-options enrichment, not an edit path) | Info | Not in scope — this is the stop options display path, not a route edit operation; the phase goal explicitly targets "route edit operations (remove, add, reorder, replace stop)" |
| `tests/test_endpoints.py` line 128 | `mocker.patch('main.google_directions_simple', ...)` mocking the in-scope `main.py` usage above | Info | Consistent with the `main.py` scope boundary; not a blocker |

No blockers or warnings found in the four files modified by this phase.

---

### Human Verification Required

None. All success criteria are programmatically verifiable and confirmed passing.

---

### Gaps Summary

No gaps. All four observable truths are verified at all four levels (exists, substantive, wired, data-flowing). The 16 route editing tests and 24 ferry tests all pass with zero failures.

---

_Verified: 2026-03-26T17:30:00Z_
_Verifier: Claude (gsd-verifier)_
