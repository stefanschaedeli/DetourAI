---
phase: 12-context-infrastructure-wishes-forwarding
plan: 02
subsystem: backend/agents
tags: [wishes-forwarding, agent-prompts, context-propagation, CTX-02, CTX-03]
dependency_graph:
  requires: []
  provides: [wishes-context-in-all-agents]
  affects: [route_architect, stop_options_finder, region_planner, accommodation_researcher, restaurants_agent, day_planner, travel_guide_agent, trip_analysis_agent]
tech_stack:
  added: []
  patterns: [conditional-prompt-injection, wishes-context-block]
key_files:
  created: []
  modified:
    - backend/agents/route_architect.py
    - backend/agents/stop_options_finder.py
    - backend/agents/region_planner.py
    - backend/agents/accommodation_researcher.py
    - backend/agents/restaurants_agent.py
    - backend/agents/day_planner.py
    - backend/agents/travel_guide_agent.py
    - backend/agents/trip_analysis_agent.py
    - backend/tests/test_agents_mock.py
decisions:
  - "Routing agents (route_architect, stop_options_finder, region_planner, day_planner) include location in mandatory_activities formatting; content agents use name-only"
  - "All 3 wishes fields use empty-safe conditional guards — zero behavioral change when fields are empty"
  - "TripAnalysisAgent and RouteArchitectAgent only add travel_description + preferred_activities (mandatory_activities already present in both)"
metrics:
  duration: 8min
  completed: 2026-03-29
  tasks: 2
  files: 9
---

# Phase 12 Plan 02: Wishes Forwarding to All Agents Summary

All 8 remaining agents now receive travel_description, preferred_activities, and mandatory_activities in their prompts via the canonical ActivitiesAgent pattern (conditional injection blocks).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add wishes context to all 8 agent prompt files | 7d049a2 | 8 agent files |
| 2 | Add test cases for wishes in agent prompts | 886f6c1 | test_agents_mock.py |

## What Was Built

Wishes context forwarding from TravelRequest to all 9 Claude agents. The three fields — `travel_description`, `preferred_activities`, `mandatory_activities` — are now conditionally included in every agent's prompt when non-empty. Empty fields produce no output (zero behavioral change for existing trips without wishes).

**Pattern used (from ActivitiesAgent):**
```python
desc_line = f"\nReisebeschreibung: {req.travel_description}" if req.travel_description else ""
pref_line = f"\nBevorzugte Aktivitäten: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
mandatory_line = f"\nPflichtaktivitäten: ..." if req.mandatory_activities else ""
```

**Routing vs content agent distinction:**
- Routing agents (route_architect, stop_options_finder, region_planner, day_planner): mandatory_activities include `a.location` when set
- Content agents (accommodation_researcher, restaurants_agent, travel_guide_agent, trip_analysis_agent): mandatory_activities use `a.name` only

**Per-agent additions:**
- `route_architect.py`: Added `pref_str` for preferred_activities (travel_description + mandatory already present)
- `stop_options_finder.py`: Added all 3 fields to `_build_prompt()` after style_emphasis block
- `region_planner.py`: Added all 3 fields to `_leg_context()` after Reisestile/Reisende lines
- `accommodation_researcher.py`: Added all 3 fields after extra_hint, before REGELN section
- `restaurants_agent.py`: Added all 3 fields after travel_styles/budget lines
- `day_planner.py`: Added all 3 fields in `_plan_single_day()` after Reisende line
- `travel_guide_agent.py`: Added all 3 fields after Reisestile line
- `trip_analysis_agent.py`: Added travel_description + preferred_activities after Pflichtaktivitäten (mandatory already present)

**Test coverage added (4 new tests):**
- `test_route_architect_includes_preferred_activities`: RouteArchitect prompt contains preferred_activities
- `test_stop_options_finder_includes_all_wishes`: StopOptionsFinder has all 3 fields including location-aware mandatory
- `test_wishes_absent_when_empty`: No wishes lines injected when all fields are empty
- `test_restaurants_agent_includes_wishes`: RestaurantsAgent has all 3 fields with name-only mandatory

## Verification Results

- `grep -r "Bevorzugte Aktivit" agents/ | wc -l` = 9 (one per agent)
- `grep -r "Reisebeschreibung:" agents/ | wc -l` = 9 (one per agent)
- Full test suite: 295 passed (291 baseline + 4 new), 0 failures

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

All modified files verified to contain required strings. All commits exist and test suite passes.
