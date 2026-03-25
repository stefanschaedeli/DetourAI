---
phase: 2
slug: geographic-routing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio |
| **Config file** | None (uses default discovery) |
| **Quick run command** | `cd backend && python3 -m pytest tests/test_ferry.py -v` |
| **Full suite command** | `cd backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3 -m pytest tests/test_ferry.py -v`
- **After every plan wave:** Run `cd backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | GEO-04 | unit | `pytest tests/test_ferry.py::test_island_groups_coverage -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | GEO-03 | unit | `pytest tests/test_ferry.py::test_ferry_fallback_on_zero_result -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | GEO-02 | unit | `pytest tests/test_ferry.py::test_island_coordinate_validation -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | GEO-01 | unit (mock) | `pytest tests/test_ferry.py::test_route_architect_ferry_prompt -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | GEO-05 | unit | `pytest tests/test_ferry.py::test_ferry_time_deduction -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ferry.py` — stubs for GEO-01 through GEO-05
- [ ] No additional conftest fixtures needed beyond existing ones

*Existing pytest infrastructure covers all framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Athens→Santorini produces ferry via Piraeus | GEO-01 | Requires live Claude API + Google Directions | Run full trip planning with TEST_MODE=false, verify ferry_crossings in response |
| Island coordinates resolve correctly | GEO-02 | Requires live Google Geocoding API | Geocode "Santorini" and verify lat/lon is on the island |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
