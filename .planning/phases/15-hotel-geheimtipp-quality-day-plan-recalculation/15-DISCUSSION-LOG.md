# Phase 15: Hotel Geheimtipp Quality + Day Plan Recalculation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 15-hotel-geheimtipp-quality-day-plan-recalculation
**Areas discussed:** Geheimtipp distance validation

---

## Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Geheimtipp distance validation | How to validate hotel proximity server-side: haversine threshold, what happens to filtered-out options, whether to add lat/lon to AccommodationOption model | ✓ |
| Nights edit UX | Replacing prompt() with a dedicated button: inline edit vs modal, where the button lives, validation rules | |
| Recalculation trigger flow | What happens after nights change: which Celery task pattern to follow, SSE progress feedback, whether to recalc day plans immediately or on-demand | |
| Migration & edge cases | Whether existing saved travels with wrong arrival_day need migration, handling edge cases like nights=0 or exceeding total budget | |

---

## Geheimtipp Distance Validation

### Q1: Where should the haversine distance check run?

| Option | Description | Selected |
|--------|-------------|----------|
| Post-processing in agent | Check distance after Claude returns options, inside accommodation_researcher.py. Drops Geheimtipps that exceed threshold. | |
| Separate validation layer | New utility function called from main.py after agent returns. More visible but splits accommodation logic across files. | |
| You decide | Claude picks the cleanest integration point based on the existing code patterns. | |

**User's choice:** Free text — "check after but I think primarily the issue is that the distance was not a key consideration in the prompt"
**Notes:** User identified that the root cause is prompt quality, not just missing post-processing validation.

### Q2: How should we strengthen the prompt?

| Option | Description | Selected |
|--------|-------------|----------|
| Add explicit coordinates | Include the stop's lat/lon in the prompt. Gives Claude a concrete reference point instead of just a city name. | ✓ |
| Stronger wording only | Reinforce with KRITISCH tag and repeat the constraint. Keep the prompt text-based without coordinates. | |
| Both + post-processing | Add coordinates to the prompt AND haversine post-processing as safety net. | |

**User's choice:** Add explicit coordinates
**Notes:** None

### Q3: Add haversine post-processing as safety net?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, add post-processing | Haversine check after Claude returns options. Silently drop any Geheimtipp exceeding the radius. User sees 3 options instead of 4. | ✓ |
| Trust the prompt | The coordinates in the prompt should be enough. Skip server-side validation to keep it simple. | |

**User's choice:** Yes, add post-processing
**Notes:** None

### Q4: Dedup approach within a stop?

| Option | Description | Selected |
|--------|-------------|----------|
| Name-based dedup | Case-insensitive exact match on hotel name within the same stop. Simple, sufficient. | ✓ |
| Add lat/lon to AccommodationOption | Extend the model + prompt to return coordinates per hotel. Enables distance-based dedup and distance display in UI. | |
| You decide | Claude picks based on complexity vs value trade-off. | |

**User's choice:** Name-based dedup
**Notes:** None

## Claude's Discretion

- Nights edit UX (replacing prompt() with dedicated button)
- Recalculation trigger flow (Celery task pattern, SSE progress)
- Migration strategy for existing saved travels
- Edge cases (validation ranges, budget impact)

## Deferred Ideas

None
