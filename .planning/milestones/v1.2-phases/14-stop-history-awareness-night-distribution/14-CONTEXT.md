# Phase 14: Stop History Awareness + Night Distribution - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

StopOptionsFinder must not suggest already-selected stops (prompt-level exclusion + post-processing safety net). Night distribution follows the Architect pre-plan with suggested nights pre-filled in options. Remaining nights balance shown in the UI during stop selection.

</domain>

<decisions>
## Implementation Decisions

### Dedup — Prompt Level
- **D-01:** Add a KRITISCH exclusion rule to the StopOptionsFinder system prompt or user prompt: "Schlage KEINE Orte vor die bereits als Stopp ausgewählt wurden." Leverages the existing `stops_str` listing of bisherige Stopps.
- **D-02:** No separate blocklist block needed — the existing "Bisherige Stopps: ..." line combined with the new exclusion rule is sufficient.

### Dedup — Post-Processing Safety Net (RTE-04)
- **D-03:** Case-insensitive exact match on `region` name against `selected_stops`. Matches the existing confirm-route dedup pattern (main.py line 1740).
- **D-04:** When a duplicate is detected in returned options, silently drop it. User sees fewer than 3 options — simple and honest. No retry for replacement.
- **D-05:** Post-processing dedup runs in `_find_and_stream_options` after each option is enriched, before the SSE event is pushed.

### Night Distribution
- **D-06:** StopOptionsFinder's JSON output includes a `recommended_nights` field pre-filled from the architect plan's region recommendation. User still picks final nights during stop selection, but the default matches the plan.
- **D-07:** Night recommendations from the architect plan are injected more prominently — not just as context but as a suggested default in the prompt (e.g., "Empfehle für diese Region X Nächte basierend auf dem Architect-Plan").

### Night Budget UI
- **D-08:** Frontend displays "X Nächte verbleibend" alongside stop options during route building. The backend already tracks `days_remaining` — extend this to expose a night-specific balance.

### Streaming Stability
- **D-09:** Cap stop history in the prompt. If more than 8 stops are selected, include only the last 5 plus a count summary (e.g., "8 bisherige Stopps, letzte 5: ..."). Prevents unbounded prompt growth on long trips.

### Claude's Discretion
- Exact wording of the KRITISCH exclusion rule in German
- Where exactly in the prompt the exclusion rule is placed (system prompt vs user prompt)
- Exact threshold for history capping (suggested 8/5 but Claude can adjust based on token analysis)
- How `recommended_nights` is derived when the current region doesn't exactly match an architect plan region (fuzzy matching strategy)
- UI placement and styling of the "Nächte verbleibend" indicator

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Agent Implementation
- `backend/agents/stop_options_finder.py` — Main file to modify: `_build_prompt()`, `find_options()`, `find_options_streaming()`
- `backend/agents/architect_pre_plan.py` — Source of `architect_plan` structure (regions, recommended_nights)
- `backend/agents/_client.py` — Client factory, model selection

### Integration Points
- `backend/main.py` lines 719-818 — `_find_and_stream_options()`: where post-processing dedup must be added
- `backend/main.py` lines 1525-1557 — `_next_options()`: where `selected_stops` and `architect_context` are passed
- `backend/main.py` lines 1737-1776 — Existing confirm-route dedup pattern (reference for exact-match approach)

### Prior Phase Context
- `.planning/phases/13-architect-pre-plan-for-interactive-flow/13-CONTEXT.md` — Architect pre-plan decisions (D-05 advisory nights, D-10 job state, D-11 architect_context parameter)

### Frontend
- `frontend/js/route-builder.js` — Route builder UI where "Nächte verbleibend" indicator will be added

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `stops_str` in `_build_prompt()` (line 58-64): Already formats selected stops as a one-liner — exclusion rule hooks directly onto this
- `existing_regions` set in confirm-route (line 1740): Exact dedup pattern to replicate for post-processing
- `days_remaining` in route status: Already computed and passed through — basis for night budget calculation

### Established Patterns
- KRITISCH rules in SYSTEM_PROMPT: Existing convention for hard constraints the AI must follow
- Silent filtering in `_find_and_stream_options`: Options too close to origin/target are already silently dropped — same pattern for dedup
- `architect_context` injection: Phase 13 established the pattern for conditional prompt blocks

### Integration Points
- `_build_prompt()` receives `selected_stops` and `architect_context` — both needed for dedup and night distribution
- `_find_and_stream_options()` processes each option individually (streaming) — dedup check fits naturally per-option
- Frontend `route-builder.js` renders stop options with metadata — nights balance fits in the existing meta display area

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

### Reviewed Todos (not folded)
- "RouteArchitect ignores daily drive limits and suggests ferries/islands" — already folded into Phase 13 (D-03). No action needed.

</deferred>

---

*Phase: 14-stop-history-awareness-night-distribution*
*Context gathered: 2026-03-29*
