---
phase: 08-tech-debt-stabilization
plan: "01"
subsystem: infra, ui
tags: [celery, google-maps, guide, route-editing, stats-bar]

requires: []
provides:
  - Celery replace_stop_job task registered — stop replacement works in Docker
  - Map markers and polyline redraw after every route edit (all 5 handlers)
  - Stats bar visible unconditionally on all travel guide tabs
affects: [travel-view, route-editing, celery-workers]

tech-stack:
  added: []
  patterns:
    - "After every SSE edit-complete handler, call GoogleMaps.setGuideMarkers(data, _onMarkerClick) to sync map with updated plan"
    - "Stats bar renders unconditionally inside renderGuide — no tab condition"

key-files:
  created: []
  modified:
    - backend/tasks/__init__.py
    - frontend/js/guide.js

key-decisions:
  - "GoogleMaps.setGuideMarkers called after renderGuide (not inside) to keep concerns separate"
  - "Stats bar always visible on all tabs — removed tab-conditional rendering"

patterns-established:
  - "Map redraw pattern: if (typeof GoogleMaps !== 'undefined') GoogleMaps.setGuideMarkers(data, _onMarkerClick)"

requirements-completed: [DEBT-01, DEBT-02, DEBT-03]

duration: 2min
completed: 2026-03-27
---

# Phase 8 Plan 01: Tech Debt Quick Fixes Summary

**Celery replace_stop_job registered, map markers redraw after all 5 route edits, stats bar unconditional on all tabs**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-27T14:54:00Z
- **Completed:** 2026-03-27T14:56:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `tasks.replace_stop_job` to Celery include list — stop replacement now dispatches correctly in Docker (DEBT-01)
- Added `GoogleMaps.setGuideMarkers(data, _onMarkerClick)` after all 5 route-edit SSE complete handlers (DEBT-02)
- Removed `if (activeTab === 'overview')` guard from stats bar rendering — shows on all tabs (DEBT-03)

## Task Commits

1. **Task 1: Register replace_stop_job and add map redraws** - `a6c192d` (fix)
2. **Task 2: Make stats bar visible on all tabs** - `43a9038` (fix)

## Files Created/Modified

- `backend/tasks/__init__.py` — Added `"tasks.replace_stop_job"` to Celery include list (6 tasks total)
- `frontend/js/guide.js` — 5 map redraw calls added; stats bar condition removed

## Decisions Made

- `GoogleMaps.setGuideMarkers` is called after `renderGuide`, not inside it, to keep map redraw separate from DOM render logic
- Stats bar now always renders — the old `activeTab === 'overview'` guard was overly restrictive

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- 2 pre-existing test failures (`test_plan_trip_success`, `test_research_accommodation_success`) due to missing `ANTHROPIC_API_KEY` in test environment — unrelated to this plan; 284 tests pass

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All three quick fixes applied and verified
- Ready for Plan 02 (remaining tech debt items: RouteArchitect drive-limit fix and browser UI verification)

---
*Phase: 08-tech-debt-stabilization*
*Completed: 2026-03-27*
