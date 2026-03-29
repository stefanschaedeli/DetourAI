---
phase: 14-stop-history-awareness-night-distribution
plan: "02"
subsystem: frontend-route-builder
tags: [route-builder, night-display, ui, nights-remaining]
dependency_graph:
  requires: [nights_remaining in meta from plan 14-01]
  provides: [nights-display-in-route-status]
  affects: [frontend/js/route-builder.js]
tech_stack:
  added: []
  patterns: [meta-field-read-with-fallback, textContent-only-for-numbers]
key_files:
  created: []
  modified:
    - frontend/js/route-builder.js
decisions:
  - "Display format 'X Nächte · Y Tage verbleibend' in subtitle — combines both metrics into one readable string"
  - "Fallback daysRem - 1 for backward compat with cached job state missing nights_remaining"
metrics:
  duration_minutes: 3
  completed_date: "2026-03-29"
  tasks_completed: 1
  files_changed: 1
requirements: [RTE-03, RTE-04]
---

# Phase 14 Plan 02: Frontend Night Budget Display Summary

Route builder subtitle now shows "X Nächte · Y Tage verbleibend" during stop selection using nights_remaining from meta, with fallback to daysRem-1 for backward compatibility.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add nights remaining display to route builder status | 7b953e4 | frontend/js/route-builder.js |

## Changes Made

### Task 1 — route-builder.js

Modified `_updateRouteStatus(meta)`:

1. **nights_remaining extraction:** `const nightsRem = (meta.nights_remaining != null) ? meta.nights_remaining : (daysRem > 0 ? daysRem - 1 : 0);` — reads field from meta if present, falls back to `daysRem - 1` for older job state that lacks the field.

2. **budgetInfo variable:** Replaces the former inline days-only string. Produces `"${nightsRem} Nächte · ${daysRem} Tage verbleibend"` when days are known, empty string otherwise.

3. **parts array:** `budgetInfo` replaces the old `daysRem ? ... : ''` expression — same filter(Boolean) pattern, one cleaner variable name.

4. **textContent assignment unchanged:** Still `subtitle.textContent = parts.join(' · ')` — no innerHTML, no XSS concern.

## Verification

```
grep -n "nights_remaining" frontend/js/route-builder.js  → line 339
grep -n "Nächte" frontend/js/route-builder.js             → line 341
grep -n "daysRem - 1" frontend/js/route-builder.js        → line 339
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

Files verified:
- frontend/js/route-builder.js — FOUND, contains nights_remaining, Nächte, daysRem - 1

Commits verified:
- 7b953e4 — FOUND (feat(14-02): Nächte verbleibend in Routenstatus anzeigen)
