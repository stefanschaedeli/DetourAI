---
phase: 02-geographic-routing
plan: 02
subsystem: api
tags: [ferry, island-detection, agent-prompts, corridor-bypass, day-planner, route-enrichment]

# Dependency graph
requires:
  - phase: 02-geographic-routing
    plan: 01
    provides: "ferry_ports.py utilities, google_directions_with_ferry, TravelStop/StopOption ferry fields"
provides:
  - "Ferry-aware route architect prompt with INSEL-ZIEL ERKANNT block"
  - "Island coordinate validation in stop_options_finder after geocoding"
  - "Ferry fallback in main.py route enrichment via google_directions_with_ferry"
  - "Corridor and bearing check bypass for island destination segments"
  - "Ferry time deduction in day planner prompts"
  - "Ferry cost computation in _fallback_cost_estimate (not just 0.0)"
  - "ferry_detected SSE event from route architect"
  - "FerryDetection debug logger component"
affects: [frontend-route-builder, frontend-progress, day-planner-output]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Island corridor bypass: skip corridor+bearing checks when target is island destination", "Ferry cost formula: CHF 50 base + CHF 0.5/km"]

key-files:
  created: []
  modified:
    - backend/agents/route_architect.py
    - backend/agents/stop_options_finder.py
    - backend/agents/day_planner.py
    - backend/main.py
    - backend/utils/debug_logger.py
    - backend/tests/test_ferry.py

key-decisions:
  - "Corridor bypass applies to both corridor check AND bearing check for island targets"
  - "Ferry cost formula: CHF 50 base + CHF 0.5/km for all crossings"
  - "Island coordinate validation logs warning but does not reject stops (graceful degradation)"
  - "Ferry time propagated through day_contexts to _plan_single_day prompt"

patterns-established:
  - "Island bypass: is_island_destination(target_coords) gates corridor/bearing checks"
  - "Ferry info in prompts: deduct ferry_hours from max_drive_hours for remaining driving budget"

requirements-completed: [GEO-01, GEO-02, GEO-03, GEO-05]

# Metrics
duration: 5min
completed: 2026-03-25
---

# Phase 02 Plan 02: Agent Ferry Integration Summary

**Ferry-aware agent prompts, island corridor bypass, ferry time deduction in day planner, and ferry cost computation across route architect, stop finder, day planner, and route enrichment pipeline**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-25T12:25:23Z
- **Completed:** 2026-03-25T12:30:42Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Route architect detects island destinations via geocoding and injects ferry port instructions into Claude prompt
- Stop options finder validates that geocoded island coordinates actually fall within the expected island bounding box
- Route enrichment in main.py uses google_directions_with_ferry for ferry fallback and bypasses corridor/bearing checks for island targets
- Day planner deducts ferry time from daily driving budget in prompts and computes actual ferry costs (not just 0.0)
- 5 new ferry-specific tests bringing ferry test count to 24, full suite at 245

## Task Commits

Each task was committed atomically:

1. **Task 1: Route architect ferry prompt + stop_options_finder island validation + day planner ferry time/cost** - `a7b2a59` (feat)
2. **Task 2: main.py ferry fallback in route enrichment + corridor bypass + ferry-specific tests** - `d16e5ca` (feat)

## Files Created/Modified
- `backend/agents/route_architect.py` - Ferry detection block, INSEL-ZIEL ERKANNT prompt, ferry_detected SSE event
- `backend/agents/stop_options_finder.py` - Island coordinate validation after geocoding (D-10, GEO-02)
- `backend/agents/day_planner.py` - Ferry time deduction in prompt, ferry cost in _fallback_cost_estimate, ferry fields in day_contexts
- `backend/main.py` - google_directions_with_ferry in _enrich_one, is_island_destination corridor bypass
- `backend/utils/debug_logger.py` - FerryDetection component in _COMPONENT_MAP
- `backend/tests/test_ferry.py` - 5 new tests (test_route_architect_ferry_prompt, test_ferry_time_deduction, test_enrich_ferry_detection, test_corridor_bypass_island, test_fallback_cost_estimate_with_ferry)

## Decisions Made
- Corridor bypass applies to both corridor check AND bearing check when target is island (not just corridor)
- Ferry cost formula: CHF 50 base + CHF 0.5/km -- simple, tunable, conservative estimate
- Island coordinate validation uses graceful degradation: logs WARNING but does not reject stops
- Ferry fields (is_ferry, ferry_hours) propagated through day_contexts so _plan_single_day can build ferry-aware prompts

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] TravelRequest requires legs field in tests**
- **Found during:** Task 2 (test creation)
- **Issue:** TravelRequest constructor requires legs=[TripLeg(...)] format, not flat fields
- **Fix:** Created _make_req() helper using TripLeg pattern from existing test_agents_mock.py
- **Files modified:** backend/tests/test_ferry.py
- **Verification:** All 24 ferry tests pass
- **Committed in:** d16e5ca (Task 2 commit)

**2. [Rule 3 - Blocking] DayPlannerAgent requires mocked Anthropic client**
- **Found during:** Task 2 (test creation)
- **Issue:** DayPlannerAgent.__init__ calls get_client() which requires ANTHROPIC_API_KEY
- **Fix:** Mocked get_client and get_model in tests that instantiate the agent
- **Files modified:** backend/tests/test_ferry.py
- **Verification:** All tests pass without API key
- **Committed in:** d16e5ca (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking)
**Impact on plan:** Both fixes necessary for test execution without API keys. No scope creep.

## Issues Encountered
None beyond the auto-fixed test infrastructure issues above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Complete ferry pipeline: detection -> prompt -> enrichment -> corridor bypass -> day planning -> cost estimation
- Frontend can now receive ferry_detected SSE events and display ferry indicators
- All 245 tests passing with 24 ferry-specific tests

---
*Phase: 02-geographic-routing*
*Completed: 2026-03-25*
