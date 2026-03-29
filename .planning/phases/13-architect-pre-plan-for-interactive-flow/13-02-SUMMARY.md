---
phase: 13-architect-pre-plan-for-interactive-flow
plan: "02"
subsystem: backend
tags: [agent, pre-plan, route-quality, tdd, wiring, main.py]
dependency_graph:
  requires: [13-01]
  provides: [ArchitectPrePlan-wired-into-job-flow]
  affects:
    - backend/main.py
    - backend/agents/stop_options_finder.py
    - backend/tests/test_agents_mock.py
tech_stack:
  added: []
  patterns: [asyncio.wait_for, silent-fallback, context-threading, tdd]
key_files:
  created: []
  modified:
    - backend/main.py
    - backend/agents/stop_options_finder.py
    - backend/tests/test_agents_mock.py
decisions:
  - "Other _find_and_stream_options call sites receive architect_context=None (default) — only _start_leg_route_building passes context per RESEARCH.md Open Question 2"
  - "architect_plan persists across legs (not reset in _advance_to_next_leg) because pre-plan covers whole trip"
  - "Guard conditions: not architect_plan_attempted AND leg_index==0 AND stop_counter==0 — prevents re-running on recompute or subsequent stops"
metrics:
  duration: "~3.5 min"
  completed: "2026-03-29"
  tasks_completed: 2
  files_changed: 3
---

# Phase 13 Plan 02: Wire ArchitectPrePlan into Interactive Flow Summary

**One-liner:** ArchitectPrePlanAgent wired into `_start_leg_route_building()` with 5s timeout + silent fallback; context injected into StopOptionsFinder prompts as ARCHITECT-EMPFEHLUNG block.

## What Was Built

- `backend/agents/stop_options_finder.py` — Added `architect_context: dict = None` to `_build_prompt()`, `find_options()`, and `find_options_streaming()`. When architect_context has non-empty regions, a `ARCHITECT-EMPFEHLUNG: RegionA (3N, ~3.0h) → RegionB (6N, ~4.0h)` block is injected between geo_block and bearing_block in the prompt.

- `backend/main.py` — Two new fields in `_new_job()` init dict: `architect_plan` and `architect_plan_attempted`. `_start_leg_route_building()` now runs `ArchitectPrePlanAgent` once before the first `StopOptionsFinder` call (guard: not attempted, leg_index==0, stop_counter==0). Uses `asyncio.wait_for()` with 5s timeout; any exception is caught, logged as WARNING, and `architect_plan` set to None (silent fallback, D-13). `_find_and_stream_options()` now accepts `architect_context: dict = None` parameter, threaded through to `find_options_streaming()`.

- `backend/tests/test_agents_mock.py` — 5 new tests covering the full requirements.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add architect_context to StopOptionsFinder with tests (TDD) | 1492a67 | backend/agents/stop_options_finder.py, backend/tests/test_agents_mock.py |
| 2 | Wire pre-plan into main.py job flow with timeout and fallback (TDD) | c981856 | backend/main.py, backend/tests/test_agents_mock.py |

## Verification

- `python3 -m pytest tests/test_agents_mock.py -x -v` — 44 tests pass including 5 new
- `python3 -m pytest tests/ -v` — 302/304 tests green (2 pre-existing failures require ANTHROPIC_API_KEY in test env)
- `grep -n "ARCHITECT-EMPFEHLUNG" backend/agents/stop_options_finder.py` — context injection present
- `grep -n "architect_plan" backend/main.py | head -20` — job state, pre-plan call, and threading all present
- `grep -n "wait_for.*5.0" backend/main.py` — timeout present
- `grep -n "architect_context" backend/main.py` — parameter threading present

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

## Known Stubs

None — all wiring paths are fully connected. ArchitectPrePlanAgent is called in production flow, result is stored and passed through to StopOptionsFinder prompts.

## Self-Check: PASSED

- `backend/agents/stop_options_finder.py` contains `architect_context`: FOUND
- `backend/agents/stop_options_finder.py` contains `ARCHITECT-EMPFEHLUNG`: FOUND
- `backend/main.py` contains `architect_plan`: FOUND
- `backend/main.py` contains `architect_plan_attempted`: FOUND
- `backend/main.py` contains `asyncio.wait_for`: FOUND (line 325)
- `backend/tests/test_agents_mock.py` contains `test_architect_pre_plan_graceful_fallback`: FOUND
- `backend/tests/test_agents_mock.py` contains `test_architect_pre_plan_stored_in_job`: FOUND
- `backend/tests/test_agents_mock.py` contains `test_stop_options_finder_architect_context_in_prompt`: FOUND
- Commit 1492a67 (Task 1): FOUND
- Commit c981856 (Task 2): FOUND
