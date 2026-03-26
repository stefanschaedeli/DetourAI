---
phase: 02-geographic-routing
plan: 01
subsystem: api
tags: [ferry, island-detection, haversine, google-directions, pydantic]

# Dependency graph
requires:
  - phase: 01-ai-quality
    provides: "maps_helper.py with haversine_km, corridor_bbox, bearing_degrees"
provides:
  - "ferry_ports.py with ISLAND_GROUPS lookup table (8 Mediterranean island groups)"
  - "is_island_destination() for coordinate-based island detection"
  - "validate_island_coordinates() for geocode validation"
  - "ferry_estimate() for haversine-based ferry duration calculation"
  - "get_ferry_ports() for port lookup per island group"
  - "google_directions_with_ferry() wrapper with ferry fallback"
  - "TravelStop.is_ferry, ferry_hours, ferry_cost_chf model fields"
  - "StopOption.is_ferry_required model field"
affects: [02-02-agent-prompts, route-architect, stop-options-finder, day-planner, main-enrichment]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Ferry fallback pattern: wrap google_directions with island lookup on zero result"]

key-files:
  created:
    - backend/utils/ferry_ports.py
    - backend/tests/test_ferry.py
  modified:
    - backend/utils/maps_helper.py
    - backend/models/travel_response.py
    - backend/models/stop_option.py

key-decisions:
  - "Bbox-based island detection (not haversine-from-center) for simpler, more predictable validation"
  - "Ferry speed constant at 30 km/h for all Mediterranean crossings"
  - "google_directions_with_ferry checks both origin and destination for island group membership"

patterns-established:
  - "Ferry fallback: when google_directions returns (0,0,''), check island lookup, return ferry estimate"
  - "Island validation via bounding box membership, not distance from center"

requirements-completed: [GEO-02, GEO-03, GEO-04]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 02 Plan 01: Ferry Detection Foundation Summary

**Island/port lookup table with 8 Mediterranean groups, ferry-aware directions wrapper, and Pydantic model extensions for ferry legs**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T12:20:26Z
- **Completed:** 2026-03-25T12:23:05Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created ferry_ports.py with complete Mediterranean island coverage (Cyclades, Dodecanese, Ionian, Corsica, Sardinia, Sicily, Balearics, Croatian Islands)
- Built google_directions_with_ferry() that transparently falls back to haversine-based ferry estimates when Google returns no driving route
- Extended TravelStop and StopOption models with ferry-specific fields for downstream agent and UI consumption
- 19 tests covering all utility functions, model fields, and mocked async directions wrapper

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ferry_ports.py lookup table and utility functions** - `dd61777` (feat)
2. **Task 2: Add google_directions_with_ferry() wrapper and model extensions** - `1f88073` (feat)

_Both tasks followed TDD: RED (failing tests) -> GREEN (implementation) -> verified_

## Files Created/Modified
- `backend/utils/ferry_ports.py` - Island group lookup table, detection/validation/estimation functions
- `backend/utils/maps_helper.py` - Added google_directions_with_ferry() wrapper with ferry fallback
- `backend/models/travel_response.py` - Added is_ferry, ferry_hours, ferry_cost_chf to TravelStop
- `backend/models/stop_option.py` - Added is_ferry_required to StopOption
- `backend/tests/test_ferry.py` - 19 tests for all ferry functionality

## Decisions Made
- Used bounding box checks for island detection instead of haversine-from-center (simpler, deterministic, bbox data already defined per island group)
- Ferry speed fixed at 30 km/h constant for all crossings (tunable via FERRY_SPEED_KMH)
- google_directions_with_ferry checks BOTH endpoints for island membership (handles ferries in either direction)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Ferry utility functions ready for Plan 02 (agent prompt updates, corridor bypass, ferry time deduction)
- google_directions_with_ferry can replace google_directions calls in route enrichment and day planning
- Model fields ready for agent JSON output parsing and frontend display

---
*Phase: 02-geographic-routing*
*Completed: 2026-03-25*
