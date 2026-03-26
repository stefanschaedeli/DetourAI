---
phase: 7
slug: ferry-aware-route-edits
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio, pytest-mock |
| **Config file** | `backend/tests/conftest.py` |
| **Quick run command** | `cd /Users/stefan/Code/Travelman3/backend && python3 -m pytest tests/test_route_editing.py tests/test_ferry.py -x -v` |
| **Full suite command** | `cd /Users/stefan/Code/Travelman3/backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd /Users/stefan/Code/Travelman3/backend && python3 -m pytest tests/test_route_editing.py tests/test_ferry.py -x -v`
- **After every plan wave:** Run `cd /Users/stefan/Code/Travelman3/backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | GEO-03 | unit | `cd backend && python3 -m pytest tests/test_route_editing.py -x -k "recalc_segment"` | Exists (needs mock update) | ⬜ pending |
| 07-01-02 | 01 | 1 | GEO-03 | unit | `cd backend && python3 -m pytest tests/test_route_editing.py -x -k "ferry"` | New test needed | ⬜ pending |
| 07-01-03 | 01 | 1 | GEO-03+05 | unit | `cd backend && python3 -m pytest tests/test_route_editing.py -x -k "ferry_metadata"` | New test needed | ⬜ pending |
| 07-02-01 | 02 | 1 | GEO-05 | unit | `cd backend && python3 -m pytest tests/test_ferry.py -x -k "day_planner or fallback"` | Partially exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Update existing mocks in `test_route_editing.py` from 2-tuple to 4-tuple returns
- [ ] New test: `test_recalc_segment_directions_ferry` — mock returns `is_ferry=True`, assert ferry metadata on stop
- [ ] New test: `test_replace_stop_ferry_metadata` — mock returns `is_ferry=True` for both prev->new and new->next, assert metadata on correct stops

*Existing infrastructure covers framework requirements — only new test cases needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Ferry icon visible on edited stop card | GEO-03 | Frontend rendering | Edit a stop on an island trip, verify ferry icon appears |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
