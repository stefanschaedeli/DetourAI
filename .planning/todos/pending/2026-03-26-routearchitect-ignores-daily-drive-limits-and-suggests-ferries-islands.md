---
created: 2026-03-26T17:47:19.882Z
title: RouteArchitect ignores daily drive limits and suggests ferries/islands
area: agents
files:
  - backend/agents/route_architect.py
  - backend/agents/stop_options_finder.py
---

## Problem

The RouteArchitect agent plans high-level routes that are too aggressive — it eagerly includes ferries and island detours that result in 11+ hour driving days. This violates the user's configured `max_drive_time_per_day` constraint.

When the StopOptionsFinder later tries to find stops along these unrealistic legs, it correctly identifies that all candidate stops are way too far away, but by then the route is already committed.

The root cause is that RouteArchitect doesn't factor in the daily driving time budget when planning the overall route structure. It treats the trip as a point-to-point path without considering that each day's segment must be drivable within the user's limits.

## Solution

- RouteArchitect's system prompt needs to incorporate `max_drive_time_per_day` as a hard constraint when planning the route skeleton
- The agent should estimate driving times between major waypoints and ensure no single day exceeds the limit
- Ferry crossings and island detours should only be suggested when the time budget allows (ferry time + driving time ≤ daily max)
- Consider passing the daily drive limit explicitly in the prompt and instructing the agent to validate each leg's feasibility before including it
