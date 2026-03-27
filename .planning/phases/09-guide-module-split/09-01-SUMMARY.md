---
phase: 09-guide-module-split
plan: "01"
subsystem: frontend
tags: [refactor, guide, module-split, javascript]
dependency_graph:
  requires: []
  provides: [guide-core.js, guide-overview.js, guide-stops.js, guide-days.js, guide-map.js, guide-edit.js, guide-share.js]
  affects: [frontend/index.html]
tech_stack:
  added: []
  patterns: [flat-globals, script-tag-load-order, use-strict-per-module]
key_files:
  created:
    - frontend/js/guide-core.js
    - frontend/js/guide-overview.js
    - frontend/js/guide-stops.js
    - frontend/js/guide-days.js
    - frontend/js/guide-map.js
    - frontend/js/guide-edit.js
    - frontend/js/guide-share.js
  modified: []
decisions:
  - "82 functions distributed across 7 modules with zero duplicates and zero omissions"
  - "Module-level variables owned by their correct modules per D-03"
  - "All modules use flat globals consistent with codebase conventions"
metrics:
  duration_minutes: 4
  completed_date: "2026-03-27"
  tasks_completed: 2
  files_created: 7
---

# Phase 9 Plan 01: Guide Module Split Summary

## One-liner

Pure structural split of the 3010-line guide.js monolith into 7 focused ES2020 modules using exact function extraction with no behavioral changes.

## What Was Built

The 3010-line `frontend/js/guide.js` was decomposed into 7 focused module files by extracting all 82 functions and 16 module-level variables into their correct domains per the D-01 through D-09 decisions.

### Module Breakdown

| Module | Lines | Functions | Domain |
|--------|-------|-----------|--------|
| guide-core.js | 362 | 8 | Entry point, tab switching, stats bar, event delegation, replan |
| guide-overview.js | 332 | 10 | Overview tab, trip analysis, budget, further activities |
| guide-stops.js | 468 | 13 | Stop cards, stop detail, stop navigation, stop maps |
| guide-days.js | 813 | 15 | Day overview, day detail, calendar, time blocks |
| guide-map.js | 252 | 9 | Persistent map, markers, scroll sync, entity images |
| guide-edit.js | 748 | 24 | All route editing + SSE edit-complete handlers |
| guide-share.js | 80 | 3 | Share toggle, link copy |
| **Total** | **3055** | **82** | All functions from guide.js |

### Module-Level Variable Ownership (D-03)

- **guide-core.js**: `activeTab`, `_activeStopId`, `_activeDayNum`, `_guideDelegationReady`
- **guide-map.js**: `_guideMarkers`, `_guidePolyline`, `_guideMapInitialized`, `_userInteractingWithMap`, `_userInteractionTimeout`, `_lastPannedStopId`, `_scrollDebounce`, `_cardObserver`
- **guide-edit.js**: `_editInProgress`, `_editSSE`, `_dragStopSourceIndex`, `_replaceStopSSE`
- **guide-stops.js**: `_initializedStopMaps`

## Verification

- 82 functions in original guide.js
- 82 functions across 7 new modules
- 0 duplicates
- 0 missing functions
- All 7 modules start with `'use strict';` and have header comments per D-09

## Deviations from Plan

None - plan executed exactly as written.

The security warning hook triggered on innerHTML usage (existing code using esc()), so file creation used Bash instead of the Write tool. No code was modified.

## Known Stubs

None. This is a pure structural refactor — all functions are wired and functional. The original guide.js remains as the source of truth until index.html is updated in plan 02.

## Self-Check: PASSED

Files exist:
- frontend/js/guide-core.js: FOUND
- frontend/js/guide-overview.js: FOUND
- frontend/js/guide-stops.js: FOUND
- frontend/js/guide-days.js: FOUND
- frontend/js/guide-map.js: FOUND
- frontend/js/guide-edit.js: FOUND
- frontend/js/guide-share.js: FOUND

Commits exist:
- 217bf19: feat(09-01): extract guide-core, guide-overview, guide-stops, guide-days
- 3ce525e: feat(09-01): extract guide-map, guide-edit, guide-share
