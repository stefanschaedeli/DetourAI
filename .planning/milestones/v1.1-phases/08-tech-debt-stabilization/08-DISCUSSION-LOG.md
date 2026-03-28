# Phase 8: Tech Debt Stabilization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 08-tech-debt-stabilization
**Areas discussed:** Map refresh strategy, Stats bar visibility, Drive limit enforcement

---

## Map Refresh Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Full map redraw | Clear all markers + polyline, re-render from updated plan data. Brief flash acceptable. | ✓ |
| Incremental update | Only add/remove/move changed markers. Smoother but more complex, higher risk of stale state. | |
| You decide | Claude picks based on existing code patterns. | |

**User's choice:** Full map redraw
**Notes:** Simple and reliable, matches how renderGuide() already does full HTML replacement.

### Follow-up: Map bounds after edit

| Option | Description | Selected |
|--------|-------------|----------|
| Re-fit to full route | Map zooms to show all stops after edit. Consistent with initial render. | ✓ |
| Keep current view | Map stays where user was looking. Might miss off-screen changes. | |
| You decide | Claude picks based on context. | |

**User's choice:** Re-fit to full route
**Notes:** None

---

## Stats Bar Visibility

| Option | Description | Selected |
|--------|-------------|----------|
| Always visible | Stats bar stays at top across all tabs. Updates immediately after any edit. | ✓ |
| Overview only, refresh on tab switch | Keep stats on overview tab only, ensure fresh data on tab activation. | |
| You decide | Claude picks the best approach. | |

**User's choice:** Always visible
**Notes:** None

---

## Drive Limit Enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| Hard constraint in prompt | Strengthen prompt to make drive limit non-negotiable. | |
| Post-generation validation | Validate each day's drive time after generation, reject/retry if exceeded. | |
| Soft limit with warning | Allow exceeding for unavoidable ferry legs, flag those days. | |
| You decide | Claude picks the best enforcement strategy. | |

**User's choice:** Custom — Two-tier system: soft warning at configured max, hard limit at 130% with post-generation validation handling retries.
**Notes:** User wants flexibility but with a ceiling. 30% over the configured max is the absolute hard limit enforced by post-generation validation.

### Follow-up: Ferry time and drive limit

| Option | Description | Selected |
|--------|-------------|----------|
| Counts toward limit | Ferry time is travel time from user perspective. 4h ferry + 2h driving = 6h. | |
| Separate tracking | Only driving counts toward limit. Ferry shown separately. | ✓ |
| You decide | Claude picks based on UX. | |

**User's choice:** Separate tracking
**Notes:** Ferry time displayed separately so user sees total travel time, but limit enforcement only checks actual driving hours. Island trips should not be penalized for ferry crossings.

---

## Claude's Discretion

- Post-generation validation retry count and error messaging
- Exact prompt wording for strengthened drive limit instructions
- How to surface soft-limit warnings in the UI

## Deferred Ideas

None — discussion stayed within phase scope
