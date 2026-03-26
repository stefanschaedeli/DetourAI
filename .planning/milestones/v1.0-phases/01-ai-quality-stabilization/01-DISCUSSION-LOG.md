# Phase 1: AI Quality Stabilization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 01-ai-quality-stabilization
**Areas discussed:** Coordinate Validation, Travel Style Enforcement, Stop Quality Consistency, Route Efficiency, Request Plausibility

---

## Coordinate Validation

### Q1: When a stop's geocoded coordinates fall outside the route corridor, what should happen?

| Option | Description | Selected |
|--------|-------------|----------|
| Reject and re-ask Claude | If coords are >X km off the route corridor, discard the option silently and ask the agent for a replacement. User never sees bad suggestions. | |
| Flag but still show | Show the stop to the user but mark it visually as 'far from route'. Let the user decide whether to accept it. | :white_check_mark: |
| You decide | Claude picks the best approach based on codebase patterns and user experience. | |

**User's choice:** Flag but still show
**Notes:** User prefers transparency over silent filtering for geographic issues.

### Q2: How wide should the route corridor tolerance be?

| Option | Description | Selected |
|--------|-------------|----------|
| Proportional to leg distance | E.g. 20% of the leg distance as corridor width. Short legs get tight corridors, long legs allow more exploration. | :white_check_mark: |
| Fixed distance (e.g. 50km) | Simple: any stop within 50km of the straight-line route is acceptable. | |
| You decide | Claude picks the best tolerance strategy. | |

**User's choice:** Proportional to leg distance
**Notes:** None

---

## Travel Style Enforcement

### Q3: How strictly should travel style preferences filter stop suggestions?

| Option | Description | Selected |
|--------|-------------|----------|
| Strong filter | If user picks 'beach/ocean', ALL stop options must be coastal. No mountain villages. | |
| Weighted preference | Travel style is a strong preference but not absolute. 2 of 3 options match the style, 1 can be a 'wildcard'. | :white_check_mark: |
| You decide | Claude picks the right strictness. | |

**User's choice:** Weighted preference (2/3 match + 1 wildcard)
**Notes:** None

### Q4: Should travel style enforcement differ between RouteArchitect and StopOptionsFinder?

| Option | Description | Selected |
|--------|-------------|----------|
| Both enforce equally | RouteArchitect plans route through style-matching regions. StopOptionsFinder filters stops. Double reinforcement. | :white_check_mark: |
| StopOptionsFinder only | RouteArchitect plans most efficient route. Only stop finder filters by style. | |
| You decide | Claude determines where style enforcement has the most impact. | |

**User's choice:** Both enforce equally
**Notes:** None

---

## Stop Quality Consistency

### Q5: What should define a 'quality' stop suggestion?

| Option | Description | Selected |
|--------|-------------|----------|
| Google Places validation | After Claude suggests a stop, verify it exists in Google Places API. No results / low rating / wrong category = low quality. | :white_check_mark: |
| Prompt engineering only | Improve the prompt to demand higher-quality suggestions. No post-validation. | |
| Both prompt + validation | Strengthen prompt AND validate against Google Places. | |

**User's choice:** Google Places validation
**Notes:** None

### Q6: When a low-quality stop is detected, what should happen?

| Option | Description | Selected |
|--------|-------------|----------|
| Flag visually to user | Show the stop but with a warning indicator. | |
| Re-ask Claude for replacement | Silently discard the bad option and ask Claude for a replacement. User only sees good options. | :white_check_mark: |
| You decide | Claude picks based on existing SSE streaming flow. | |

**User's choice:** Re-ask Claude for replacement
**Notes:** Interesting contrast with coordinate validation (flag) — user sees geographic oddities as potentially intentional but quality failures as never acceptable.

---

## Route Efficiency

### Q7: How should zigzag/backtracking be detected?

| Option | Description | Selected |
|--------|-------------|----------|
| Bearing check between stops | Calculate bearing from each stop to next. >90 degree deviation from overall route bearing = backtracking. | :white_check_mark: |
| Google Directions total vs sum | Compare total route distance against sum of all legs. Ratio > 1.5x = zigzagging. | |
| You decide | Claude picks best detection method. | |

**User's choice:** Bearing check between stops
**Notes:** None

### Q8: When backtracking is detected, what should happen?

| Option | Description | Selected |
|--------|-------------|----------|
| Prevent in prompt | Include previous stop coordinates in StopOptionsFinder prompt. Prevention over detection. | |
| Post-validate and re-ask | Let Claude suggest freely, then check bearing. Re-ask if backtracking. | |
| Both | Prevent in prompt AND post-validate. Maximum reliability. | :white_check_mark: |

**User's choice:** Both prevention and post-validation
**Notes:** None

---

## Request Plausibility

### Q9: When travel style doesn't match destination geography, what should happen?

| Option | Description | Selected |
|--------|-------------|----------|
| Agent challenges the request | RouteArchitect recognizes mismatch and suggests alternatives. Honest, helpful. | :white_check_mark: |
| Best-effort match only | Try to find closest match without challenging. | |
| Warn then proceed | Show warning but still provide best available stops. | |

**User's choice:** Agent challenges the request
**Notes:** User gave specific example: asking for vulcanos in an area with none should be challenged, not result in suggesting "Vulcano Theme Park".

### Q10: At which point should the plausibility check happen?

| Option | Description | Selected |
|--------|-------------|----------|
| RouteArchitect level | Catch mismatches early, before stop selection starts. | :white_check_mark: |
| StopOptionsFinder level | Check at each stop, more granular but later in flow. | |
| Both levels | RouteArchitect warns upfront, StopOptionsFinder handles leg-by-leg edge cases. | |

**User's choice:** RouteArchitect level
**Notes:** None

### Q11: How should the challenge appear to the user?

| Option | Description | Selected |
|--------|-------------|----------|
| SSE message with suggestion | Visible message in progress stream with alternatives. User can adjust or continue. | :white_check_mark: |
| Auto-adapt silently | Silently adapt style to what's available. Less friction, less transparency. | |
| You decide | Claude picks best UX pattern. | |

**User's choice:** SSE message with suggestion
**Notes:** Consistent with user's general preference for transparency.

---

## Claude's Discretion

- Exact corridor width percentage
- Google Places quality thresholds
- Bearing deviation threshold for backtracking
- Maximum retry attempts for replacements
- German wording of plausibility challenge messages

## Deferred Ideas

None — discussion stayed within phase scope.
