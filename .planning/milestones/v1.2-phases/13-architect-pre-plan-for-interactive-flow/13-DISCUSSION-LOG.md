# Phase 13: Architect Pre-Plan for Interactive Flow - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 13-architect-pre-plan-for-interactive-flow
**Areas discussed:** Pre-plan content, Nights distribution, Integration point, Failure handling

---

## Folded Todo

| Option | Description | Selected |
|--------|-------------|----------|
| Skip it | Phase 13 creates a NEW lightweight pre-plan agent — fixing the existing RouteArchitect is separate work | |
| Fold it in | Address drive-limit awareness in the new pre-plan so it doesn't repeat the same issue | ✓ |

**User's choice:** Fold it in
**Notes:** Drive-limit enforcement becomes part of the pre-plan's output contract.

---

## Pre-plan Content

### Detail Level

| Option | Description | Selected |
|--------|-------------|----------|
| Region list + nights (Recommended) | Ordered list of regions with recommended nights each. Lean, fast, gives StopOptionsFinder just enough context. | ✓ |
| Full route sketch | Regions + nights + themes + key attractions + driving logic. More context but slower, higher token cost. | |
| Minimal — just nights total per leg | Only total night counts per leg segment, no region breakdown. Very fast but no regional guidance. | |

**User's choice:** Region list + nights (Recommended)
**Notes:** None

### Drive Limits in Pre-Plan

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, include max hours (Recommended) | Pre-plan specifies max_drive_hours is respected between regions. | ✓ |
| No, leave to StopOptionsFinder | StopOptionsFinder already enforces drive limits per-stop. Pre-plan stays purely strategic. | |

**User's choice:** Yes, include max hours (Recommended)
**Notes:** Addresses the folded todo about RouteArchitect ignoring drive limits.

---

## Nights Distribution

### Allocation Logic

| Option | Description | Selected |
|--------|-------------|----------|
| AI judges potential (Recommended) | Sonnet decides based on destination type. Prompt includes total trip days as constraint. | ✓ (modified) |
| Formula-based | Algorithm: capital = 3N, medium city = 2N, else = 1N. Predictable but rigid. | |
| User-adjustable preview | AI proposes, user tweaks before route building. More interactive but adds UI step. | |

**User's choice:** AI judges potential — but with user preference about city vs scenic inferred from context
**Notes:** User wanted the AI to factor in whether the traveler prefers spending more time in cities or scenic areas. Not via a new form field — inferred from existing travel_styles, travel_description, and preferred_activities.

### City-vs-Scenic Preference Capture

| Option | Description | Selected |
|--------|-------------|----------|
| Infer from travel styles (Recommended) | Use existing travel_styles mapping. No new UI needed. | |
| New form field | Add toggle in Step 2. Explicit but adds UI complexity. | |
| Ask in pre-plan prompt | Let Sonnet infer from combined context. No new field, AI decides. | ✓ |

**User's choice:** Ask in pre-plan prompt
**Notes:** Sonnet uses all available context to determine balance.

### Binding vs Advisory

| Option | Description | Selected |
|--------|-------------|----------|
| Advisory (Recommended) | StopOptionsFinder sees recommendations, user still picks final nights. | ✓ |
| Binding defaults | Pre-plan nights become defaults. User can override but StopOptionsFinder treats as fixed. | |

**User's choice:** Advisory (Recommended)
**Notes:** None

---

## Integration Point

### Trigger Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Before first stop request (Recommended) | Run once in _start_leg_route_building(). Store in job["architect_plan"]. | ✓ |
| Per-leg pre-plan | Fresh pre-plan per leg. More accurate but adds latency per leg. | |
| Eager on job creation | Fire on job creation. Ready before user clicks start. May be wasted. | |

**User's choice:** Before first stop request (Recommended)
**Notes:** None

### Agent Design

| Option | Description | Selected |
|--------|-------------|----------|
| New agent class (Recommended) | Separate ArchitectPrePlanAgent using Sonnet. Clean separation. | ✓ |
| Method on RouteArchitect | Add pre_plan() to existing class. Muddies model assignment. | |

**User's choice:** New agent class (Recommended)
**Notes:** None

### Consumption Method

| Option | Description | Selected |
|--------|-------------|----------|
| New parameter (Recommended) | New architect_context parameter on _build_prompt(). Labeled section in prompt. | ✓ |
| Merge into route_geometry | Add pre-plan fields to existing dict. Mixes strategic and geometric data. | |

**User's choice:** New parameter (Recommended)
**Notes:** None

---

## Failure Handling

### Timeout

| Option | Description | Selected |
|--------|-------------|----------|
| 5 seconds (Recommended) | Generous but bounded. Covers normal latency + rate limit retry. | ✓ |
| 3 seconds | Tighter. May trigger false timeouts during API load spikes. | |
| 10 seconds | Very generous. Adds noticeable delay on failure. | |

**User's choice:** 5 seconds (Recommended)
**Notes:** None

### Fallback Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Silent fallback (Recommended) | Log warning, set None, StopOptionsFinder runs as today. User never sees failure. | ✓ |
| Retry once then fallback | One retry then fallback. Slightly more resilient but 2x latency on failure. | |
| Show user hint | SSE message about simplified flow. Transparent but may confuse. | |

**User's choice:** Silent fallback (Recommended)
**Notes:** None

---

## Claude's Discretion

- Exact German system prompt wording
- JSON output schema for pre-plan
- Exact ARCHITECT-EMPFEHLUNG prompt section wording
- Debug logger registration details

## Deferred Ideas

None — discussion stayed within phase scope.
