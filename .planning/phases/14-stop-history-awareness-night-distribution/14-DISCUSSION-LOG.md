# Phase 14: Stop History Awareness + Night Distribution - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 14-stop-history-awareness-night-distribution
**Areas discussed:** Dedup strategy, Night distribution guidance, Streaming stability

---

## Dedup — Prompt Level

| Option | Description | Selected |
|--------|-------------|----------|
| Add exclusion rule | Add a KRITISCH line: 'Schlage KEINE Orte vor die bereits als Stopp ausgewählt wurden'. Simple, leverages existing stops_str. | ✓ |
| Separate blocklist block | Dedicated BEREITS-BESUCHT block listing stop names as explicit blocklist, separate from bisherige-Stopps listing. | |

**User's choice:** Add exclusion rule
**Notes:** Simple approach preferred — the existing stops listing already provides context, just needs an explicit "don't repeat" instruction.

## Dedup — Post-Processing Detection

| Option | Description | Selected |
|--------|-------------|----------|
| Exact region match | Case-insensitive exact match on region name against selected_stops. Matches existing confirm-route dedup. | ✓ |
| Distance-based (Haversine) | Filter options within 10km of selected stops. Catches name variants but needs geocoding. | |
| Both exact + distance | First exact match, then distance check. Most thorough but adds overhead. | |

**User's choice:** Exact region match
**Notes:** Consistent with existing dedup pattern at route confirmation (line 1740).

## Dedup — Action on Duplicate

| Option | Description | Selected |
|--------|-------------|----------|
| Silently drop it | Remove duplicate, show fewer than 3 options. Simple and honest. | ✓ |
| Re-run agent | Retry agent for replacement. Ensures 3 options but adds latency. | |
| Log warning only | Keep duplicate, log warning. User decides. | |

**User's choice:** Silently drop it
**Notes:** No retry overhead — if AI follows the prompt rule, duplicates should be rare anyway.

## Night Distribution — Prompt Guidance

| Option | Description | Selected |
|--------|-------------|----------|
| Suggest matching nights | StopOptionsFinder includes recommended_nights pre-filled from architect plan. User picks final. | ✓ |
| Keep purely advisory | Current behavior: architect plan shown as context only. | |
| Enforce strictly | Must use architect plan's night count. No deviation. | |

**User's choice:** Suggest matching nights
**Notes:** Balances architect intelligence with user flexibility.

## Night Distribution — Budget Display

| Option | Description | Selected |
|--------|-------------|----------|
| Track internally only | Backend tracks night budget. Prompt adjusts. User doesn't see counter. | |
| Show nights balance in UI | Frontend displays "X Nächte verbleibend" during stop selection. | ✓ |
| No tracking changes | Current days_remaining tracking is sufficient. | |

**User's choice:** Show nights balance in UI
**Notes:** User wants transparency into remaining night budget during route building.

## Streaming Stability — Prompt Length

| Option | Description | Selected |
|--------|-------------|----------|
| Compact history format | Keep one-liner format. ~20 extra tokens. Minimal impact. | |
| Cap history length | If >8 stops, include only last 5 plus count. Prevents unbounded growth. | ✓ |
| No special handling | Even 15 stops is ~200 tokens — negligible for Sonnet. | |

**User's choice:** Cap history length
**Notes:** Proactive measure for long multi-leg trips.

---

## Claude's Discretion

- Exact German wording of KRITISCH exclusion rule
- Prompt placement of exclusion rule
- History cap threshold tuning
- Fuzzy region matching for architect plan nights
- UI styling of "Nächte verbleibend" indicator

## Deferred Ideas

None — discussion stayed within phase scope.
