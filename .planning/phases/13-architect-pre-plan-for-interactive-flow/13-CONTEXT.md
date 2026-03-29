# Phase 13: Architect Pre-Plan for Interactive Flow - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Before the first StopOptionsFinder call, generate a lightweight Architect pre-plan that defines regions and recommended nights-per-region (based on destination potential), then inject that context into all StopOptionsFinder prompts. The pre-plan also enforces max_drive_hours_per_day between regions to prevent the existing issue where the RouteArchitect ignores daily drive limits.

</domain>

<decisions>
## Implementation Decisions

### Pre-Plan Content
- **D-01:** Pre-plan output is an ordered list of regions with recommended nights per region and drive-time constraints. E.g. "Provence (2N, ~3h) → Côte d'Azur (3N, ~2h) → Paris (3N, ~4h)"
- **D-02:** No themes, key attractions, or driving logic in the pre-plan — StopOptionsFinder handles specifics. Keep it lean for fast Sonnet response.
- **D-03:** Pre-plan includes max_drive_hours_per_day enforcement — no proposed region transition exceeds the user's limit. This addresses the folded todo about RouteArchitect ignoring drive limits.

### Nights Distribution
- **D-04:** Sonnet judges destination potential using combined context: `travel_description`, `travel_styles`, `preferred_activities`, `mandatory_activities`. No new form field needed — AI infers city-vs-scenic preference from existing inputs.
- **D-05:** Night recommendations are **advisory**, not binding. StopOptionsFinder sees "empfohlen: 2 Nächte" but user still picks final nights during stop selection.
- **D-06:** Total nights across all regions must sum to `total_days - 1` (accounting for travel days). Sonnet gets this as a hard constraint in its prompt.

### Agent Design
- **D-07:** New `ArchitectPrePlanAgent` class in a separate file (`backend/agents/architect_pre_plan.py`), using Sonnet model. Existing `RouteArchitectAgent` stays untouched.
- **D-08:** Agent follows established pattern: German system prompt, `call_with_retry()`, `parse_agent_json()`, debug_logger logging.

### Integration
- **D-09:** Pre-plan runs once before the first StopOptionsFinder call, inside `_start_leg_route_building()` in `main.py`.
- **D-10:** Result stored in `job["architect_plan"]` in Redis job state. All subsequent StopOptionsFinder calls for the same job read from it.
- **D-11:** StopOptionsFinder gets a new `architect_context` parameter on `_build_prompt()`. Injected as a labeled section: "ARCHITECT-EMPFEHLUNG: ..." — clean separation from route geometry data.

### Failure Handling
- **D-12:** 5-second timeout on the pre-plan call. If Sonnet can't respond in time, something is wrong.
- **D-13:** Silent fallback on any failure (timeout, parse error, API error): log warning, set `job["architect_plan"] = None`. StopOptionsFinder runs exactly as today without architect context. User never sees the failure.
- **D-14:** No retry on failure — single attempt with 5s timeout, then fallback. Avoids doubling latency on failure path.

### Folded Todos
- "RouteArchitect ignores daily drive limits and suggests ferries/islands" — addressed by D-03: the new pre-plan enforces max_drive_hours_per_day between proposed regions, preventing unrealistic drive-time suggestions from the strategic layer.

### Claude's Discretion
- Exact German system prompt wording for the new agent
- JSON output schema for the pre-plan (region names, nights, drive hours structure)
- Exact wording of the ARCHITECT-EMPFEHLUNG section injected into StopOptionsFinder prompts
- Whether to add the new agent to _COMPONENT_MAP in debug_logger.py (yes, per CLAUDE.md logging rules)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Agent Pattern Reference
- `backend/agents/activities_agent.py` — Reference implementation for conditional prompt injection (Phase 12 pattern)
- `backend/agents/_client.py` — Client factory, `get_model()` for Sonnet assignment, `get_max_tokens()`
- `backend/agents/route_architect.py` — Existing RouteArchitect for understanding the domain (NOT to be modified)

### StopOptionsFinder Integration
- `backend/agents/stop_options_finder.py` — `_build_prompt()` method where `architect_context` parameter will be added
- `backend/main.py` lines 301-335 — `_start_leg_route_building()` where pre-plan call will be inserted before StopOptionsFinder

### Job State
- `backend/main.py` — `save_job()` / `get_job()` for Redis state management; search for `job["region_plan"]` as pattern for storing agent results in job state

### Models
- `backend/models/travel_request.py` — TravelRequest fields the pre-plan agent needs: `travel_description`, `travel_styles`, `preferred_activities`, `mandatory_activities`, `max_drive_hours_per_day`, `total_days`, legs

### Utilities
- `backend/utils/retry_helper.py` — `call_with_retry()` wrapper
- `backend/utils/json_parser.py` — `parse_agent_json()` for response parsing
- `backend/utils/debug_logger.py` — Logging + `_COMPONENT_MAP` for new agent registration

### Requirements
- `.planning/REQUIREMENTS.md` — RTE-01, RTE-02, RTE-05 mapped to this phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Agent pattern:** All 9 agents follow identical structure — system prompt + `call_with_retry()` + `parse_agent_json()` + logging. Copy any agent as template.
- **Conditional prompt injection:** Phase 12 established `f"...\n" if field else ""` pattern across all agents — reuse for architect_context in StopOptionsFinder.
- **Job state storage:** `job["region_plan"]` already stores agent results in Redis — same pattern for `job["architect_plan"]`.
- **`_start_leg_route_building()`:** Clear insertion point — pre-plan call goes between geometry calculation and StopOptionsFinder instantiation.

### Established Patterns
- Agent model assignment via `get_model("claude-sonnet-4-5", AGENT_KEY)` with TEST_MODE fallback
- German-language system prompts with strict JSON-only output instruction
- `asyncio.to_thread()` wrapping for blocking Anthropic SDK calls (inside `call_with_retry()`)
- Debug logging with `LogLevel.AGENT` for flow, `LogLevel.API` for calls, `LogLevel.PROMPT` for prompts

### Integration Points
- `_start_leg_route_building()` in `main.py` — insert pre-plan before line 319 (StopOptionsFinder instantiation)
- `StopOptionsFinderAgent._build_prompt()` — add `architect_context` parameter
- `_find_and_stream_options()` — pass architect context through to agent
- `_COMPONENT_MAP` in `debug_logger.py` — register new agent for log routing
- Agent model table in `settings_store.py` — add new agent model entry

</code_context>

<specifics>
## Specific Ideas

- User wants the nights distribution to reflect where they'd enjoy spending more time (cities vs scenic), inferred from their existing travel_styles + travel_description + preferred_activities — not a new form field
- The pre-plan should feel invisible to the user — it runs silently, improves StopOptionsFinder quality, and degrades gracefully

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 13-architect-pre-plan-for-interactive-flow*
*Context gathered: 2026-03-29*
