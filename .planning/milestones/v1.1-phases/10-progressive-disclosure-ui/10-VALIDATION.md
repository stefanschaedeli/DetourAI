---
phase: 10
slug: progressive-disclosure-ui
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (backend regression only — phase is UI-only) |
| **Config file** | none — pytest discovered via `backend/tests/` |
| **Quick run command** | `cd backend && python3 -m pytest tests/ -v -x` |
| **Full suite command** | `cd backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3 -m pytest tests/ -v -x`
- **After every plan wave:** Run `cd backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | NAV-01 | manual browser | `cd backend && python3 -m pytest tests/ -v -x` (regression) | ✅ | ⬜ pending |
| 10-01-02 | 01 | 1 | NAV-04 | manual browser | `cd backend && python3 -m pytest tests/ -v -x` (regression) | ✅ | ⬜ pending |
| 10-01-03 | 01 | 1 | NAV-06 | manual browser | `cd backend && python3 -m pytest tests/ -v -x` (regression) | ✅ | ⬜ pending |
| 10-02-01 | 02 | 1 | NAV-02 | manual browser | `cd backend && python3 -m pytest tests/ -v -x` (regression) | ✅ | ⬜ pending |
| 10-02-02 | 02 | 1 | NAV-03 | manual browser | `cd backend && python3 -m pytest tests/ -v -x` (regression) | ✅ | ⬜ pending |
| 10-02-03 | 02 | 1 | NAV-05 | manual browser | `cd backend && python3 -m pytest tests/ -v -x` (regression) | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files needed — all 6 NAV requirements are UI-only and verified manually in browser. Backend regression suite serves as automated gate.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Overview renders day cards grid + collapsible section | NAV-01 | Visual UI rendering — no backend testable surface | Open `/travel/{id}`, verify day cards grid visible, collapsible section collapsed by default |
| Day drill-down renders detail + map focus | NAV-02 | Visual UI + Google Maps interaction | Click day card, verify detail renders, map zooms to day region |
| Stop drill-down renders detail + map focus | NAV-03 | Visual UI + Google Maps interaction | Click stop from day view, verify detail renders, map pans to stop |
| Breadcrumb back-navigation | NAV-04 | DOM event delegation + visual rendering | Drill to stop, click breadcrumb segments, verify correct level restores |
| Non-focused markers dim | NAV-05 | Google Maps marker opacity — no DOM-testable API | Drill to day/stop, verify non-focused markers have reduced opacity |
| Browser back/forward | NAV-06 | Router + history API + visual state | Use browser back/forward, verify drill level and map state restore correctly |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
