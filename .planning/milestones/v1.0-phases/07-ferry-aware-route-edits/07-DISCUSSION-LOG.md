# Phase 7: Ferry-Aware Route Edits - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 07-ferry-aware-route-edits
**Areas discussed:** Ferry flag propagation, Day planner scope, Test strategy

---

## Ferry Flag Propagation

| Option | Description | Selected |
|--------|-------------|----------|
| Full ferry metadata (Recommended) | Set is_ferry=true, ferry_hours, ferry_cost_chf on the stop — same as initial planning. Frontend can show ferry indicators on edited stops. | ✓ |
| Swap function only | Just replace the function call and unpack the 4-tuple — use hours/km but discard is_ferry. Simplest change, ferry metadata only from initial planning. | |
| You decide | Claude picks the right approach based on existing patterns | |

**User's choice:** Full ferry metadata (Recommended)
**Notes:** Stops edited on island trips should get the same ferry indicators as stops from initial planning.

---

## Day Planner Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Swap in day planner too (Recommended) | Consistent ferry handling everywhere. Day planner already accounts for ferry time in budgets (Phase 2 D-11). Swapping ensures re-runs after edits also see ferry segments. | ✓ |
| Leave day planner as-is | Day planner runs via run_day_planner_refresh() after edits. It recalculates from scratch — but without ferry awareness it may produce incorrect schedules for island trips. | |
| You decide | Claude picks based on risk analysis | |

**User's choice:** Swap in day planner too (Recommended)
**Notes:** Consistency across all direction-calling code paths.

---

## Test Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Add ferry-specific cases (Recommended) | Add test cases where mocked google_directions_with_ferry returns is_ferry=True with ferry hours. Verify stops get is_ferry metadata set. Also update existing test mocks. | ✓ |
| Swap mocks only | Just change mock targets from google_directions_simple to google_directions_with_ferry and adjust return tuples. No new ferry-specific assertions. | |
| You decide | Claude picks based on coverage needs | |

**User's choice:** Add ferry-specific cases (Recommended)
**Notes:** Ensures ferry metadata propagation is actually verified, not just assumed from the function swap.

---

## Claude's Discretion

- Exact ferry_cost_chf estimation logic
- Whether to extract shared ferry metadata helper or inline
- Polyline handling (store or discard)

## Deferred Ideas

None — discussion stayed within phase scope
