---
phase: 14
slug: stop-history-awareness-night-distribution
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | none (no pytest.ini) |
| **Quick run command** | `cd backend && python3 -m pytest tests/test_agents_mock.py -x -v` |
| **Full suite command** | `cd backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3 -m pytest tests/test_agents_mock.py -x -v`
- **After every plan wave:** Run `cd backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | RTE-03 | unit | `cd backend && python3 -m pytest tests/test_agents_mock.py -k "test_stop_options_exclusion_rule" -x` | ❌ W0 | ⬜ pending |
| 14-01-02 | 01 | 1 | RTE-03 | unit | `cd backend && python3 -m pytest tests/test_agents_mock.py -k "test_stop_history_cap" -x` | ❌ W0 | ⬜ pending |
| 14-01-03 | 01 | 1 | RTE-04 | unit | `cd backend && python3 -m pytest tests/test_agents_mock.py -k "test_postprocessing_dedup" -x` | ❌ W0 | ⬜ pending |
| 14-01-04 | 01 | 1 | RTE-04 | unit | `cd backend && python3 -m pytest tests/test_agents_mock.py -k "test_dedup_case_insensitive" -x` | ❌ W0 | ⬜ pending |
| 14-02-01 | 02 | 1 | D-08 | unit | `cd backend && python3 -m pytest tests/test_endpoints.py -k "nights_remaining" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_agents_mock.py` — add test functions for StopOptionsFinder dedup + history cap
- [ ] `tests/test_endpoints.py` — add `nights_remaining` field assertion in select-stop tests

*Existing infrastructure covers all phase requirements — only new test functions needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Streaming latency < 5s after enriched prompt | SC-3 | Requires live Claude API call | Run TEST_MODE=true, select 3+ stops, time first option appearance |
| "Nächte verbleibend" visible in route builder | D-08 | Visual UI check | Start route builder, verify nights indicator in subtitle |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
