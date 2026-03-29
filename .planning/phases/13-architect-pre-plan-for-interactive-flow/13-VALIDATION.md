---
phase: 13
slug: architect-pre-plan-for-interactive-flow
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-mock + pytest-asyncio |
| **Config file** | None (tests use sys.path.insert) |
| **Quick run command** | `cd backend && python3 -m pytest tests/test_agents_mock.py -x -v` |
| **Full suite command** | `cd backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3 -m pytest tests/test_agents_mock.py -x -v`
- **After every plan wave:** Run `cd backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | RTE-01 | unit | `pytest tests/test_agents_mock.py::test_architect_pre_plan_agent -x` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 1 | RTE-01 | unit | `pytest tests/test_agents_mock.py::test_architect_pre_plan_stored_in_job -x` | ❌ W0 | ⬜ pending |
| 13-02-01 | 02 | 1 | RTE-02 | unit | `pytest tests/test_agents_mock.py::test_stop_options_finder_architect_context_in_prompt -x` | ❌ W0 | ⬜ pending |
| 13-02-02 | 02 | 1 | RTE-02 | unit | `pytest tests/test_agents_mock.py::test_stop_options_finder_no_architect_context -x` | ❌ W0 | ⬜ pending |
| 13-01-03 | 01 | 1 | RTE-05 | unit | `pytest tests/test_agents_mock.py::test_architect_pre_plan_prompt_includes_context -x` | ❌ W0 | ⬜ pending |
| 13-01-04 | 01 | 1 | RTE-01+D-13 | unit | `pytest tests/test_agents_mock.py::test_architect_pre_plan_graceful_fallback -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] New test functions in `backend/tests/test_agents_mock.py` — stubs for RTE-01, RTE-02, RTE-05, D-13
  - `test_architect_pre_plan_agent` — mock Anthropic, verify `run()` returns dict with `regions` list
  - `test_architect_pre_plan_prompt_includes_context` — verify `_build_prompt()` output contains travel_description and styles
  - `test_stop_options_finder_architect_context_in_prompt` — verify `_build_prompt()` with architect_context includes "ARCHITECT-EMPFEHLUNG"
  - `test_stop_options_finder_no_architect_context` — verify `_build_prompt()` without context does not include "ARCHITECT-EMPFEHLUNG"
  - `test_architect_pre_plan_graceful_fallback` — mock raises TimeoutError, verify no exception escapes
  - `test_architect_pre_plan_stored_in_job` — verify job state updated correctly

*Existing infrastructure covers test framework — only new test functions needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pre-plan produces sensible regions for real trips | RTE-05 | Requires Anthropic API call with real model | Run with TEST_MODE=true, check logs for ARCHITECT-EMPFEHLUNG content |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
