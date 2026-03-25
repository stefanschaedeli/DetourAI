# Phase 1: AI Quality Stabilization - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix the AI agent pipeline so stop discovery produces correctly located, travel-style-matched, consistently high-quality results. This phase covers: model bug fix, coordinate validation, travel style enforcement in prompts, stop quality gates, route efficiency checks, and request plausibility validation.

Requirements: AIQ-01, AIQ-02, AIQ-03, AIQ-04, AIQ-05

</domain>

<decisions>
## Implementation Decisions

### Model Bug Fix (AIQ-01)
- **D-01:** Fix `backend/agents/stop_options_finder.py:33` — change hardcoded `"claude-haiku-4-5"` to `"claude-sonnet-4-5"` as the production model. Straightforward one-line fix.

### Coordinate Validation (AIQ-02)
- **D-02:** Validate all geocoded stop coordinates against the route corridor bounding box after Claude suggests them.
- **D-03:** Corridor width is **proportional to leg distance** (e.g. 20% of the leg distance). Short legs get tight corridors, long legs allow more exploration.
- **D-04:** When a stop falls outside the corridor: **flag it visually to the user** but still show it. Do NOT silently reject — the user may have a reason for off-route stops.

### Travel Style Enforcement (AIQ-03)
- **D-05:** Travel style is a **weighted preference, not an absolute filter**. 2 of 3 stop options must match the requested style. 1 can be a "wildcard" that's still interesting for the area.
- **D-06:** Style enforcement happens at **both** RouteArchitect and StopOptionsFinder levels. RouteArchitect plans routes through style-matching regions. StopOptionsFinder filters individual stops. Double reinforcement.

### Stop Quality Consistency (AIQ-04)
- **D-07:** After Claude suggests a stop, validate it against **Google Places API**. If the place has no results, very low rating, or is clearly wrong category (e.g. gas station instead of town), it's low-quality.
- **D-08:** When a low-quality stop is detected: **silently re-ask Claude for a replacement**. User only sees good options. (Different from coordinate validation which flags but shows.)

### Route Efficiency (AIQ-05)
- **D-09:** Detect zigzag/backtracking via **bearing check between stops**. Calculate bearing from each stop to the next; if a stop reverses direction significantly (>90 degree deviation from overall route bearing), it's backtracking.
- **D-10:** Use **both prevention and post-validation**. Prevention: include previous stop coordinates and route bearing in StopOptionsFinder prompt so Claude knows the direction. Post-validation: check bearing after suggestion, re-ask if backtracking detected.

### Request Plausibility
- **D-11:** When travel style preferences don't match the destination geography (e.g. "vulcanos" in France), the **RouteArchitect challenges the request early** — before stop selection begins.
- **D-12:** Challenge appears as an **SSE message with suggestion**: "Hinweis: Auf dieser Route gibt es keine Vulkangebiete. Stattdessen bieten sich an: [alternatives]. Mochtest du den Reisestil anpassen?" User can adjust or continue.
- **D-13:** This is a new SSE event type (e.g. `style_mismatch_warning`) that the frontend must handle. If user doesn't respond / continues, proceed with best-available stops.

### Claude's Discretion
- Exact corridor width percentage (20% suggested but Claude can tune based on testing)
- Google Places quality threshold (minimum rating, minimum review count)
- Bearing deviation threshold for backtracking (90 degrees suggested but can be refined)
- Maximum number of retry attempts when re-asking Claude for replacements (suggest 2 retries max)
- Exact wording of the German-language plausibility challenge messages

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Agent Implementation
- `backend/agents/_client.py` — Model selection logic (`get_model()`, `get_max_tokens()`, TEST_MODE handling)
- `backend/agents/stop_options_finder.py` — The primary agent to fix (model bug + prompt improvements)
- `backend/agents/route_architect.py` — Route planning agent (plausibility checks, style enforcement at route level)

### Utilities
- `backend/utils/maps_helper.py` — Geocoding (`geocode_google()`), directions, coordinate handling
- `backend/utils/google_places.py` — Google Places API for stop quality validation
- `backend/utils/retry_helper.py` — `call_with_retry()` pattern for re-asking Claude
- `backend/utils/json_parser.py` — `parse_agent_json()` for parsing agent responses
- `backend/utils/debug_logger.py` — SSE event system (new event types needed for plausibility warnings)

### Models
- `backend/models/stop_option.py` — StopOption model (may need new fields for corridor flags)

### Codebase Analysis
- `.planning/codebase/CONCERNS.md` — Documents the model bug (Technical Debt section) and other known issues
- `.planning/REQUIREMENTS.md` — AIQ-01 through AIQ-05 acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_model(prod_model, agent_key)` in `_client.py` — already supports settings override, just needs correct prod model passed
- `geocode_google()` in `maps_helper.py` — returns lat/lng, can be used for corridor validation
- `google_places.py` — has `search_places()` and `get_place_details()` for quality validation
- `call_with_retry()` — handles 429/529 with exponential backoff, reusable for re-ask logic
- `debug_logger` — SSE event push system, can emit new event types for plausibility warnings

### Established Patterns
- All agents follow: build prompt -> `call_with_retry()` -> `parse_agent_json()` -> log result
- SSE events pushed via `debug_logger.log()` or custom event types
- All user-facing text in German
- Agent JSON responses parsed with `parse_agent_json()` which strips markdown fences

### Integration Points
- StopOptionsFinder is called from `backend/main.py` streaming endpoint — validation logic hooks in after each option is generated
- RouteArchitect is called first in the planning flow — plausibility check goes here
- SSE stream in `frontend/js/route-builder.js` needs to handle new event types (corridor flag, plausibility warning)
- `frontend/js/route-builder.js` renders stop option cards — needs visual flag for off-corridor stops

</code_context>

<specifics>
## Specific Ideas

- **Vulcano example:** User specifically wants the system to challenge impossible requests (e.g. vulcanos in France) rather than finding something tangentially named "Vulcano" (like a theme park). The agent should be honest about geographic reality.
- **Flag vs reject:** User prefers transparency — show off-corridor stops with a flag rather than hiding them. But low-quality stops should be silently replaced (user should never see garbage).
- **2/3 rule for travel style:** Not all-or-nothing filtering. Two of three options match the style, one can be a pleasant surprise. Keeps variety while respecting preferences.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-ai-quality-stabilization*
*Context gathered: 2026-03-25*
