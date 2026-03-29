---
phase: 15
slug: hotel-geheimtipp-quality-day-plan-recalculation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio, pytest-mock |
| **Config file** | `backend/tests/conftest.py` |
| **Quick run command** | `cd backend && python3 -m pytest tests/test_endpoints.py tests/test_agents_mock.py -v -x` |
| **Full suite command** | `cd backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3 -m pytest tests/test_endpoints.py tests/test_agents_mock.py tests/test_route_editing.py -x -q`
- **After every plan wave:** Run `cd backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | ACC-01 | unit | `pytest tests/test_agents_mock.py -k "geheimtipp_distance" -x` | ❌ W0 | ⬜ pending |
| 15-01-02 | 01 | 1 | ACC-02 | unit | `pytest tests/test_agents_mock.py -k "geheimtipp_dedup" -x` | ❌ W0 | ⬜ pending |
| 15-02-01 | 02 | 1 | BDG-01 | unit | `pytest tests/test_route_editing.py -k "arrival_day" -x` | ❌ W0 | ⬜ pending |
| 15-02-02 | 02 | 1 | BDG-02 | integration | `pytest tests/test_endpoints.py -k "update_nights" -x` | ❌ W0 | ⬜ pending |
| 15-02-03 | 02 | 1 | BDG-03 | unit | `pytest tests/test_route_editing.py -k "update_nights" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_agents_mock.py` — add `test_geheimtipp_distance_filter` and `test_geheimtipp_dedup` test stubs
- [ ] `tests/test_endpoints.py` — add `test_update_nights_success`, `test_update_nights_invalid`, `test_update_nights_lock_conflict` stubs
- [ ] `tests/test_route_editing.py` — add `test_update_nights_job_recalcs_arrival_days` and `test_arrival_day_rechain_after_nights_change` stubs

*Existing infrastructure covers all phase requirements — extend existing test modules.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Nights edit UI button renders correctly | BDG-02 | Visual element positioning/styling | Open travel guide, verify edit pencil icon appears next to nights count, click and verify modal/inline input appears |
| SSE progress visible during recalculation | BDG-03 | Real-time UI feedback | Edit nights on a saved travel, verify progress overlay appears and updates |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
