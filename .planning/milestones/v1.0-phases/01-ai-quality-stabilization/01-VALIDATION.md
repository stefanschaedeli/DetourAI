---
phase: 1
slug: ai-quality-stabilization
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-25
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 + pytest-mock 3.15.1 + pytest-asyncio 1.2.0 |
| **Config file** | None (convention-based, `backend/tests/`) |
| **Quick run command** | `cd /Users/stefan/Code/DetourAI/backend && python3 -m pytest tests/ -x -q` |
| **Full suite command** | `cd /Users/stefan/Code/DetourAI/backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd /Users/stefan/Code/DetourAI/backend && python3 -m pytest tests/ -x -q`
- **After every plan wave:** Run `cd /Users/stefan/Code/DetourAI/backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01 | 01 | 1 | AIQ-01 | unit | `pytest tests/test_validation.py::TestStopOptionsFinderModel::test_prod_model_is_sonnet -x` | Plan 01 Task 2 | pending |
| 01-02 | 01 | 1 | AIQ-02 | unit | `pytest tests/test_validation.py::TestStopOptionNewFields::test_corridor_flag -x` | Plan 01 Task 2 | pending |
| 01-03 | 01 | 1 | AIQ-02 | unit | `pytest tests/test_validation.py::TestProportionalCorridorBuffer -x` | Plan 01 Task 2 | pending |
| 01-04 | 01 | 1 | AIQ-03 | unit | `pytest tests/test_agents_mock.py::test_stop_options_style_enforcement -x` | Plan 01 Task 2 | pending |
| 01-05 | 03 | 2 | AIQ-04 | unit | `pytest tests/test_validation.py::TestQualityValidationReject -x` | Plan 03 Task 3 | pending |
| 01-06 | 03 | 2 | AIQ-04 | unit | `pytest tests/test_validation.py::TestSilentReask -x` | Plan 03 Task 3 | pending |
| 01-07 | 01 | 1 | AIQ-05 | unit | `pytest tests/test_validation.py::TestBearingDegrees -x` | Plan 01 Task 2 | pending |
| 01-08 | 01 | 1 | AIQ-05 | unit | `pytest tests/test_validation.py::TestBacktrackingDetection::test_backtracking_detection -x` | Plan 01 Task 2 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_validation.py` — new file for corridor, bearing, quality validation unit tests (Plan 01 Task 2)
- [ ] Tests for `bearing_degrees()` and `bearing_deviation()` math correctness (Plan 01 Task 2)
- [ ] Tests for proportional corridor buffer clamping behavior (Plan 01 Task 2)
- [ ] Test for corridor flag round-trip on StopOption model (Plan 01 Task 2: `test_corridor_flag`)
- [ ] Test for backtracking detection via bearing deviation > 90 (Plan 01 Task 2: `test_backtracking_detection`)
- [ ] Test for StopOptionsFinder production model assignment in `test_agents_mock.py` (Plan 01 Task 2)
- [ ] Test for StopOptionsFinder style enforcement in `test_agents_mock.py` (Plan 01 Task 2: `test_stop_options_style_enforcement`)
- [ ] Tests for Google Places quality validation -- mocked (Plan 03 Task 3: `TestQualityValidationReject`)
- [ ] Test for silent re-ask pipeline pattern (Plan 03 Task 3: `TestSilentReask`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSE plausibility warning shows in frontend | D-12 | Requires running browser + SSE stream | Start a trip with mismatched style, verify SSE event appears in route builder |
| Off-corridor flag renders visually | D-04 | Requires visual inspection | Plan a trip, check if flagged stops show corridor warning indicator |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
