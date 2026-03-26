---
phase: 3
slug: route-editing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio, pytest-mock |
| **Config file** | none — convention-based |
| **Quick run command** | `cd backend && python3 -m pytest tests/test_route_editing.py -x` |
| **Full suite command** | `cd backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3 -m pytest tests/test_route_editing.py -x`
- **After every plan wave:** Run `cd backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | CTL-01 | unit | `pytest tests/test_endpoints.py::test_remove_stop -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | CTL-01 | unit | `pytest tests/test_route_editing.py::test_remove_stop_reconnect -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | CTL-02 | unit | `pytest tests/test_endpoints.py::test_add_stop -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | CTL-02 | unit (mocked) | `pytest tests/test_route_editing.py::test_add_stop_research -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | CTL-03 | unit | `pytest tests/test_endpoints.py::test_reorder_stops -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 1 | CTL-03 | unit (mocked) | `pytest tests/test_route_editing.py::test_reorder_recalc -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 2 | CTL-04 | unit (mocked) | `pytest tests/test_route_editing.py::test_replace_with_hints -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 2 | CTL-05 | unit (mocked) | `pytest tests/test_route_editing.py::test_metrics_update -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_route_editing.py` — stubs for CTL-01 through CTL-05 task logic with mocked agents and maps
- [ ] New test cases in `tests/test_endpoints.py` — endpoint validation for remove, add, reorder
- [ ] Mock fixtures for `google_directions_simple`, `geocode_google`, agent classes

*Existing test infrastructure (conftest.py, test_endpoints.py, test_agents_mock.py) covers framework setup.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Drag-and-drop reorder UX | CTL-03 | Browser interaction, HTML5 drag events | Open guide view, drag a stop card to new position, verify list reorders and API fires |
| SSE progress during edit | CTL-05 | Requires live SSE stream observation | Trigger any edit, observe progress overlay updates in real-time |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
