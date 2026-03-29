---
phase: 13-architect-pre-plan-for-interactive-flow
plan: "01"
subsystem: agents
tags: [agent, pre-plan, route-quality, tdd]
dependency_graph:
  requires: []
  provides: [ArchitectPrePlanAgent]
  affects: [backend/agents/architect_pre_plan.py, backend/utils/debug_logger.py, backend/utils/settings_store.py]
tech_stack:
  added: []
  patterns: [agent-pattern, call_with_retry, parse_agent_json, debug_logger]
key_files:
  created:
    - backend/agents/architect_pre_plan.py
  modified:
    - backend/utils/debug_logger.py
    - backend/utils/settings_store.py
    - backend/tests/test_agents_mock.py
decisions:
  - "Used max_attempts=1 in call_with_retry per D-14 (no retry on pre-plan)"
  - "Patched get_client() in prompt-only tests — no API key needed for _build_prompt() tests"
metrics:
  duration: "~2.5 min"
  completed: "2026-03-29"
  tasks_completed: 2
  files_changed: 4
---

# Phase 13 Plan 01: ArchitectPrePlanAgent Summary

**One-liner:** New `ArchitectPrePlanAgent` using Sonnet with German system prompt enforcing potential-based nights distribution (total_days - 1 budget, max_drive_hours_per_day limit), registered in debug_logger and settings_store.

## What Was Built

- `backend/agents/architect_pre_plan.py` — `ArchitectPrePlanAgent` class following established agent pattern
- German `SYSTEM_PROMPT` with three KRITISCH constraints: nights by potential, drive limit, nights budget sum
- `_build_prompt()` builds a region plan prompt from `legs[0]` with nights_budget = `total_days - 1`, conditional blocks for travel context
- `run()` uses `call_with_retry(max_attempts=1)` per D-14 (no retry), `parse_agent_json()` for output parsing
- Agent registered in `_COMPONENT_MAP` with dual-name entries (ArchitectPrePlan / ArchitectPrePlanAgent)
- Model and max_tokens defaults (claude-sonnet-4-5, 1024) added to `settings_store.py` DEFAULTS and _RANGES

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create ArchitectPrePlanAgent with tests (TDD) | bba3887 | backend/agents/architect_pre_plan.py, backend/tests/test_agents_mock.py |
| 2 | Register agent in debug_logger and settings_store | 664e988 | backend/utils/debug_logger.py, backend/utils/settings_store.py |

## Verification

- `python3 -m pytest tests/test_agents_mock.py -x -v` — 41 tests pass including 4 new
- `python3 -m pytest tests/ -v` — 299/299 tests green
- `python3 -c "from agents.architect_pre_plan import ArchitectPrePlanAgent; print('import OK')"` — agent importable
- `python3 -c "from utils.debug_logger import _COMPONENT_MAP; assert 'ArchitectPrePlan' in _COMPONENT_MAP"` — debug_logger OK
- `python3 -c "from utils.settings_store import DEFAULTS; assert DEFAULTS['agent.architect_pre_plan.model'] == 'claude-sonnet-4-5'"` — settings_store OK

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Tests for _build_prompt() needed get_client() mock**
- **Found during:** Task 1 GREEN phase
- **Issue:** Tests for `_build_prompt()` (prompt-only tests) called `ArchitectPrePlanAgent.__init__()` which calls `get_client()`, but no `ANTHROPIC_API_KEY` is set in test env, causing RuntimeError
- **Fix:** Added `mocker.patch('agents.architect_pre_plan.get_client', return_value=mock_client)` to `test_architect_pre_plan_prompt_includes_context`, `test_architect_pre_plan_prompt_drive_limit`, and `test_architect_pre_plan_nights_budget`
- **Files modified:** backend/tests/test_agents_mock.py

## Known Stubs

None — all agent output paths are fully wired. The agent is not yet called from `main.py` (that is Plan 02's scope).

## Self-Check: PASSED

- `backend/agents/architect_pre_plan.py` exists: FOUND
- `backend/utils/debug_logger.py` contains ArchitectPrePlan: FOUND
- `backend/utils/settings_store.py` contains agent.architect_pre_plan.model: FOUND
- Commit b1611d9 (RED tests): FOUND
- Commit bba3887 (agent + GREEN): FOUND
- Commit 664e988 (registrations): FOUND
