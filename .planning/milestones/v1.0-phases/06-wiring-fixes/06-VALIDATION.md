---
phase: 6
slug: wiring-fixes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ |
| **Config file** | None (convention-based) |
| **Quick run command** | `cd backend && python3 -m pytest tests/ -x -q` |
| **Full suite command** | `cd backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3 -m pytest tests/ -x -q`
- **After every plan wave:** Run `cd backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 6-01-01 | 01 | 1 | SHR-01 | unit | `pytest tests/test_travel_db.py::test_get_includes_share_token -x` | ❌ W0 | ⬜ pending |
| 6-01-02 | 01 | 1 | AIQ-03 | manual | Browser SSE verification | N/A | ⬜ pending |
| 6-01-03 | 01 | 1 | GEO-01 | manual | Browser SSE verification | N/A | ⬜ pending |
| 6-02-01 | 02 | 1 | UIR-03 | unit | `pytest tests/test_models.py -x -k tags` | ❌ W0 | ⬜ pending |
| 6-02-02 | 02 | 1 | UIR-03 | unit | `pytest tests/test_agents_mock.py -x -k tags` | ❌ W0 | ⬜ pending |
| 6-03-01 | 03 | 1 | CTL-04 | manual | Browser verification | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_travel_db.py::test_get_includes_share_token` — covers SHR-01 share_token persistence
- [ ] `tests/test_models.py` — add test for StopOption with tags field (UIR-03)
- [ ] `tests/test_agents_mock.py` — verify StopOptionsFinder prompt includes "tags" (UIR-03)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| style_mismatch_warning SSE event fires in browser | AIQ-03 | SSE event requires running backend + browser | 1. Start a trip with specific travel style 2. Check browser devtools for `style_mismatch_warning` event |
| ferry_detected SSE event fires toast | GEO-01 | SSE event requires running backend + browser | 1. Plan route with island destination 2. Verify blue info toast appears |
| Hints input accessible in search tab | CTL-04 | UI interaction test | 1. Open replace-stop dialog 2. Switch to search tab 3. Verify hints input is visible and functional |
| Tags rendered on stop cards | UIR-03 | End-to-end data flow | 1. Complete a trip plan 2. Check stop cards display tag pills |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
