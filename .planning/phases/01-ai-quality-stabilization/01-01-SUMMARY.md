---
phase: 01-ai-quality-stabilization
plan: 01
subsystem: ai-agents
tags: [geo-math, bearing, corridor, stop-quality, pydantic, pytest]

# Dependency graph
requires: []
provides:
  - "bearing_degrees(), bearing_deviation(), proportional_corridor_buffer() in maps_helper.py"
  - "StopOption model with outside_corridor, corridor_distance_km, travel_style_match fields"
  - "StopOptionsFinder uses correct claude-sonnet-4-5 production model"
  - "test_validation.py with 23 tests for all new validation utilities"
affects: [01-02-PLAN, 01-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns: ["bearing-based backtracking detection", "proportional corridor buffer clamping"]

key-files:
  created:
    - backend/tests/test_validation.py
  modified:
    - backend/agents/stop_options_finder.py
    - backend/models/stop_option.py
    - backend/utils/maps_helper.py
    - backend/tests/test_agents_mock.py

key-decisions:
  - "Style enforcement test (test_stop_options_style_enforcement) intentionally RED until Plan 02 adds STIL-REGEL to SYSTEM_PROMPT"
  - "Source file reading used in test_prod_model_is_sonnet to verify model string without mocking Anthropic client"

patterns-established:
  - "Bearing math for route direction validation: bearing_degrees + bearing_deviation > 90 = backtracking"
  - "Proportional corridor buffer: 20% of leg distance clamped to [15, 100] km"

requirements-completed: [AIQ-01, AIQ-02, AIQ-05]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 01 Plan 01: Model Bug Fix + Geo Utilities + Validation Tests Summary

**Fixed StopOptionsFinder claude-haiku-4-5 -> claude-sonnet-4-5 model bug, added bearing/corridor geo utilities, extended StopOption with validation fields, created 23-test validation suite**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T10:13:54Z
- **Completed:** 2026-03-25T10:16:28Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Fixed critical AIQ-01 bug: StopOptionsFinder was using claude-haiku-4-5 instead of claude-sonnet-4-5 in production
- Added 3 geo utility functions (bearing_degrees, bearing_deviation, proportional_corridor_buffer) for route validation
- Extended StopOption model with outside_corridor, corridor_distance_km, travel_style_match fields
- Created test_validation.py with 23 comprehensive tests covering all new functionality

## Task Commits

Each task was committed atomically:

1. **Task 1: Model bug fix + StopOption model extension + utility functions** - `fbc960b` (fix)
2. **Task 2: Create test_validation.py and add style enforcement test** - `174cb30` (test)

## Files Created/Modified
- `backend/agents/stop_options_finder.py` - Fixed production model from claude-haiku-4-5 to claude-sonnet-4-5
- `backend/models/stop_option.py` - Added outside_corridor, corridor_distance_km, travel_style_match fields
- `backend/utils/maps_helper.py` - Added bearing_degrees(), bearing_deviation(), proportional_corridor_buffer()
- `backend/tests/test_validation.py` - 23 tests for geo utilities, model fields, backtracking detection
- `backend/tests/test_agents_mock.py` - Added test_stop_options_style_enforcement (RED until Plan 02)

## Decisions Made
- Style enforcement test intentionally left as RED (failing) -- correct TDD behavior since Plan 02 hasn't added STIL-REGEL to SYSTEM_PROMPT yet
- Used source file reading in test_prod_model_is_sonnet to verify model string directly, avoiding need for Anthropic client mocking

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all implementations are complete and functional.

## Issues Encountered
- Pre-existing test failure in test_endpoints.py::test_plan_trip_success due to missing ANTHROPIC_API_KEY env var (not caused by this plan, not addressed)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Geo utility functions ready for Plan 03 validation pipeline
- StopOption model extended for corridor/style validation flags
- Plan 02 can proceed to add STIL-REGEL prompt changes (will make style enforcement test GREEN)

---
*Phase: 01-ai-quality-stabilization*
*Completed: 2026-03-25*
