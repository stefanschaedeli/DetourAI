---
phase: 4
slug: map-centric-responsive-layout
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (backend) / browser manual (frontend) |
| **Config file** | `backend/tests/conftest.py` |
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
| 04-01-01 | 01 | 1 | UIR-01 | integration | `cd backend && python3 -m pytest tests/ -x -q` | TBD | ⬜ pending |
| 04-01-02 | 01 | 1 | UIR-03 | unit | `cd backend && python3 -m pytest tests/test_models.py -x -q` | TBD | ⬜ pending |
| 04-02-01 | 02 | 1 | UIR-03 | manual | Browser: verify stop cards render | N/A | ⬜ pending |
| 04-02-02 | 02 | 1 | UIR-04 | manual | Browser: verify day timeline expand/collapse | N/A | ⬜ pending |
| 04-02-03 | 02 | 1 | UIR-05 | manual | Browser: verify stats bar renders | N/A | ⬜ pending |
| 04-03-01 | 03 | 2 | UIR-02 | manual | Browser: verify mobile layout at 375px | N/A | ⬜ pending |
| 04-03-02 | 03 | 2 | UIR-06 | manual | Browser: verify map interactivity | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. Frontend validation is manual (vanilla JS, no test framework). Backend model tests covered by existing pytest suite.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Split-panel layout renders correctly | UIR-01 | CSS layout, visual verification | Open /travel/{id} on desktop, verify map left 58%, content right 42% |
| Mobile responsive layout | UIR-02 | Visual + touch interaction | Open /travel/{id} at 375px viewport, verify all features accessible |
| Stop cards show photos + metadata | UIR-03 | Visual rendering | Verify cards show landscape photo, name, description, tags, drive time |
| Day timeline expand/collapse | UIR-04 | Interactive behavior | Click day headers, verify expand/collapse animation |
| Stats bar shows trip totals | UIR-05 | Data aggregation + visual | Verify stats bar shows days, stops, distance, budget |
| Map bidirectional sync | UIR-06 | Interactive behavior | Click stop card → map pans; click marker → card scrolls into view |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
