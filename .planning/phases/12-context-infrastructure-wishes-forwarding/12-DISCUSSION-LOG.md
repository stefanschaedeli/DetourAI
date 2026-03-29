# Phase 12: Context Infrastructure + Wishes Forwarding - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 12-context-infrastructure-wishes-forwarding
**Areas discussed:** Wishes field semantics, Wishes form UI, Agent prompt strategy

---

## Wishes Field Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Three distinct fields | travel_description = free-text vision; preferred_activities = soft preference tags; mandatory_activities = must-do with location | ✓ |
| Two fields only | Merge preferred_activities into travel_description as free text | |
| Single wishes field | One big free-text field, AI parses intent | |

**User's choice:** Three distinct fields
**Notes:** Keeps structured data for agent prompts. Clear separation of intent levels (nice-to-have vs must-do).

---

## Wishes Form UI

### Form Step Placement

| Option | Description | Selected |
|--------|-------------|----------|
| Step 2 with styles | Group with travel styles + travelers. Natural flow: where -> how -> what -> budget -> confirm | ✓ |
| Step 3 (activities step) | Dedicated activities step | |
| New step between 2 and 3 | Dedicated wishes step, adds 6th step | |

**User's choice:** Step 2 with styles

### Preferred Activities Input Style

| Option | Description | Selected |
|--------|-------------|----------|
| Tag input like mandatory | Same tag-chip pattern as S.mandatoryTags | ✓ |
| Free-text field | Simple textarea | |
| Predefined chips + custom | Common activities as chips plus free-text | |

**User's choice:** Tag input like mandatory

### Travel Description Placeholder

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, with example | German placeholder with trip example | ✓ |
| Minimal label only | Just field label | |
| You decide | Claude picks placeholder | |

**User's choice:** Yes, with example

---

## Agent Prompt Strategy

### Prompt Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Same pattern for all | Copy ActivitiesAgent pattern to all agents | |
| Tailored per agent role | Each agent gets relevant fields only | ✓ |
| You decide | Claude picks per agent | |

**User's choice:** Tailored per agent role

### Accommodation Agent Fields

| Option | Description | Selected |
|--------|-------------|----------|
| travel_description only | Match hotel vibe to trip description | |
| All three fields | Maximum context, agent ignores irrelevant | ✓ |
| None | Keep as-is | |

**User's choice:** All three fields

### DayPlanner + TravelGuide Fields

| Option | Description | Selected |
|--------|-------------|----------|
| All three fields | Full context for day plans and narrative | ✓ |
| travel_description + preferred only | Mandatory already baked into stops | |
| travel_description only | Minimal, just set tone | |

**User's choice:** All three fields

---

## Claude's Discretion

- Exact German labels and placeholder text
- Field ordering within Step 2
- Per-agent prompt phrasing

## Deferred Ideas

- "RouteArchitect ignores daily drive limits" — deferred to Phase 13
