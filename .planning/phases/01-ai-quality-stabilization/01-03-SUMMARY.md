---
phase: 01-ai-quality-stabilization
plan: 03
subsystem: ai-agents
tags: [validation-pipeline, corridor-check, bearing-check, google-places, quality-gate, sse-events, frontend-badges]

# Dependency graph
requires:
  - phase: 01-ai-quality-stabilization
    provides: bearing_degrees, bearing_deviation, proportional_corridor_buffer, StopOption model fields
provides:
  - "Validation pipeline in _enrich_one(): corridor FLAG -> bearing REJECT -> quality REJECT"
  - "validate_stop_quality() in google_places.py for Google Places quality gating"
  - "Frontend corridor warning badge and plausibility banner SSE handler"
  - "5 quality validation tests covering reject/accept/silent-reask paths"
affects: [frontend-route-builder, ai-quality-stabilization]

# Tech tracking
tech-stack:
  added: []
  patterns: ["three-stage validation pipeline (corridor-flag, bearing-reject, quality-reject)", "fire-and-forget SSE plausibility warning", "static code pattern verification tests"]

key-files:
  created: []
  modified:
    - backend/main.py
    - backend/utils/google_places.py
    - backend/utils/maps_helper.py
    - backend/tests/test_validation.py
    - frontend/js/route-builder.js
    - frontend/styles.css

key-decisions:
  - "Corridor check flags but does NOT reject (D-04) -- user sees warning badge but option remains selectable"
  - "Quality validation uses two-tier Google Places check: find_place_from_text then nearby_search (cost-efficient)"
  - "Silent re-ask test uses static code pattern analysis instead of integration test (no running server needed)"
  - "Duplicate bearing_degrees() function removed from maps_helper.py (Plan 01 + Plan 02 both added it)"

patterns-established:
  - "Three-stage validation pipeline: geocode -> proximity -> overshoot -> corridor FLAG -> bearing REJECT -> quality REJECT"
  - "Static code pattern tests for verifying pipeline integration without running server"

requirements-completed: [AIQ-02, AIQ-04]

# Metrics
duration: 4min
completed: 2026-03-25
---

# Phase 01 Plan 03: Validation Pipeline + Frontend Visual Indicators Summary

**Three-stage stop validation pipeline (corridor/bearing/quality) wired into _enrich_one() with frontend warning badges and plausibility banner**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-25T10:21:09Z
- **Completed:** 2026-03-25T10:25:30Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Wired corridor check, bearing check, and Google Places quality validation into _enrich_one() pipeline
- Added validate_stop_quality() to google_places.py with cost-efficient two-tier validation
- Frontend shows "Abseits der Route" warning badge on off-corridor stops and "Wildcard" on non-style-matching stops
- Added style_mismatch_warning SSE handler with dismissible plausibility banner
- 5 new quality validation tests (4 async + 1 static pipeline design test)

## Task Commits

Each task was committed atomically:

1. **Task 1: Validation pipeline in _enrich_one() + validate_stop_quality()** - `45b15d5` (feat)
2. **Task 2: Frontend corridor badge + plausibility banner** - `908ef98` (feat)
3. **Task 3: Quality validation and silent re-ask tests** - `8a25431` (test)

## Files Created/Modified
- `backend/main.py` - Added corridor check, bearing check, quality check to _enrich_one(); imported bearing_degrees, bearing_deviation, proportional_corridor_buffer, validate_stop_quality
- `backend/utils/google_places.py` - Added validate_stop_quality() with find_place_from_text + nearby_search two-tier check
- `backend/utils/maps_helper.py` - Removed duplicate bearing_degrees() function (merge artifact from Plan 01 + Plan 02)
- `backend/tests/test_validation.py` - Added TestQualityValidationReject (4 tests) and TestSilentReask (1 test)
- `frontend/js/route-builder.js` - Added corridor badge, wildcard badge in card rendering; style_mismatch_warning SSE handler
- `frontend/styles.css` - Added .badge-warning, .badge-neutral, .plausibility-banner CSS rules

## Decisions Made
- Corridor check flags but does NOT reject (D-04) -- user sees warning badge but option remains selectable
- Quality validation uses two-tier Google Places check: find_place_from_text then nearby_search (cost-efficient)
- Silent re-ask test uses static code pattern analysis rather than full integration test
- Increased test search window from 5 to 10 lines to accommodate log statements between condition and return

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed duplicate bearing_degrees() function in maps_helper.py**
- **Found during:** Task 1
- **Issue:** Both Plan 01 and Plan 02 added bearing_degrees() to maps_helper.py, creating a duplicate definition
- **Fix:** Removed the first definition (Plan 01's version at line 188), kept the second (Plan 02's at line 254) which is identical in logic
- **Files modified:** backend/utils/maps_helper.py
- **Committed in:** 45b15d5 (Task 1 commit)

**2. [Rule 1 - Bug] Adjusted test search window for static pipeline verification**
- **Found during:** Task 3
- **Issue:** test_silent_reask_pipeline_design searched only 5 lines after `not is_quality` but log statements pushed `return None` to line i+6
- **Fix:** Increased search window from 5 to 10 lines
- **Files modified:** backend/tests/test_validation.py
- **Committed in:** 8a25431 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Known Stubs

None - all implementations are complete and functional.

## Issues Encountered
- Pre-existing test failures in test_endpoints.py (test_plan_trip_success, test_research_accommodation_success) due to missing ANTHROPIC_API_KEY env var -- not caused by this plan, not addressed
- Worktree did not have Plan 01/02 commits -- required git merge main before execution

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All Phase 01 plans complete: model bug fix, geo utilities, prompt enhancement, validation pipeline, frontend indicators
- Phase 01 AI quality stabilization is fully implemented
- Ready for Phase 02 Geographic Routing

---
*Phase: 01-ai-quality-stabilization*
*Completed: 2026-03-25*
