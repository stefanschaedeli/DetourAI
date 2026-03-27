---
phase: 08-tech-debt-stabilization
plan: "02"
subsystem: backend/agents
tags: [drive-limits, validation, route-planning, ferry, orchestrator, tdd]
dependency_graph:
  requires: []
  provides: [drive-limit-enforcement, ferry-exclusion-from-drive-time]
  affects: [backend/agents/route_architect.py, backend/orchestrator.py, backend/tests/test_agents_mock.py]
tech_stack:
  added: []
  patterns: [two-tier-validation, retry-on-hard-violation, tdd]
key_files:
  created: []
  modified:
    - backend/agents/route_architect.py
    - backend/orchestrator.py
    - backend/tests/test_agents_mock.py
decisions:
  - "Two-tier validation: soft limit warns, hard limit (130%) retries up to 2x"
  - "Ferry hours excluded from drive limit via drive_hours field (not ferry_hours)"
  - "After 3 total attempts with hard violations, accept with warnings rather than abort trip"
metrics:
  duration_minutes: 8
  completed_date: "2026-03-27"
  tasks_completed: 2
  files_modified: 3
---

# Phase 8 Plan 2: Drive Limit Enforcement Summary

**One-liner:** Two-tier drive limit validation (soft warn/hard retry) added to RouteArchitect prompt and orchestrator post-generation check, with ferry hours excluded from drive time calculation.

## What Was Built

### Task 1: RouteArchitect Prompt Hardening
Added explicit `FAHRZEITLIMIT` block to the RouteArchitect system prompt:
- Instructs the model that ferry time does NOT count as drive time
- Requires every stop to have `drive_hours` (pure drive only) and `ferry_hours` fields
- Hard constraint: no stop may exceed `max_drive_hours_per_day`
- Guidance for island/ferry trips: add a stop before the ferry port
- Updated the existing "Maximale Fahrzeit" line to say "STRIKT" and reference the block below
- Added `ferry_hours: 0` to the example JSON stops

### Task 2: Post-Generation Validation in Orchestrator (TDD)
Added `_validate_drive_limits()` static method to `TravelPlannerOrchestrator`:
- **Soft limit** (> configured max): flags stop with `drive_limit_warning`, accepted
- **Hard limit** (> 130% of max): flags as hard violation, triggers retry
- **Ferry exclusion**: only `drive_hours` checked, `ferry_hours` ignored
- **Start stop**: `drive_hours=0` always passes

Added retry loop in `_run_transit_leg`:
- Up to 2 retries when hard limit violated (3 total attempts)
- After max retries: logs warning and accepts route with flags
- Soft warnings always logged as INFO events

5 new tests added and passing:
- `test_validate_drive_limits_all_under`
- `test_validate_drive_limits_soft_violation`
- `test_validate_drive_limits_hard_violation`
- `test_validate_drive_limits_ferry_excluded`
- `test_validate_drive_limits_zero_drive`

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 8c66790 | feat(08-02): Fahrzeit-Limit im RouteArchitect-Prompt verstärken |
| Task 2 (RED) | f362b28 | test(08-02): Fehlschlagende Tests für _validate_drive_limits |
| Task 2 (GREEN) | d1b74a6 | feat(08-02): Fahrzeit-Validierung im Orchestrator mit Retry-Logik |

## Deviations from Plan

None — plan executed exactly as written.

## Test Results

- 5 new tests: all PASSED
- 123 non-endpoint tests: all PASSED
- 1 pre-existing failure in `test_endpoints.py::test_plan_trip_success` (requires `ANTHROPIC_API_KEY` — unrelated to this plan)

## Known Stubs

None — all functionality is wired end-to-end.

## Self-Check: PASSED
