# Phase 12: Context Infrastructure + Wishes Forwarding - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Get user wishes (travel description, preferred activities, mandatory activities) into the trip form UI and forward them reliably to all 9 agents via their prompts. The TravelRequest model and orchestrator already pass these fields — this phase adds the missing frontend UI for `preferred_activities` and updates 6 agent prompts to use the wishes fields.

</domain>

<decisions>
## Implementation Decisions

### Wishes Field Semantics
- **D-01:** Three distinct fields maintained: `travel_description` (free-text trip vision), `preferred_activities` (soft preference tags), `mandatory_activities` (must-do items with optional location)
- **D-02:** `preferred_activities` uses structured tag input (same pattern as mandatory activities), not free text

### Wishes Form UI
- **D-03:** All wishes fields go in Step 2 alongside travel styles and travelers — natural flow: where -> how -> what -> budget -> confirm
- **D-04:** `preferred_activities` uses same tag-chip input pattern as existing `S.mandatoryTags` for consistent UX
- **D-05:** `travel_description` textarea gets a German placeholder with example: "Beschreibe deine Traumreise... z.B. Romantischer Roadtrip durch die Provence mit Weinproben und kleinen Dorfern"

### Agent Prompt Strategy
- **D-06:** Prompts are tailored per agent role — each agent gets the fields relevant to its task
- **D-07:** All agents get all three fields (`travel_description`, `preferred_activities`, `mandatory_activities`) — maximum context, agents ignore what they don't need
- **D-08:** Follow ActivitiesAgent's existing pattern: conditionally include fields only when non-empty, as labeled sections in the prompt

### Per-Agent Field Assignment (all get all 3 fields)

| Agent | travel_description | preferred_activities | mandatory_activities | Status |
|-------|:--:|:--:|:--:|---|
| RouteArchitectAgent | already done | ADD | already done | Partial |
| StopOptionsFinderAgent | ADD | ADD | ADD | Needs all |
| RegionPlannerAgent | ADD | ADD | ADD | Needs all |
| AccommodationResearcherAgent | ADD | ADD | ADD | Needs all |
| ActivitiesAgent | already done | already done | already done | Complete |
| RestaurantsAgent | ADD | ADD | ADD | Needs all |
| DayPlannerAgent | ADD | ADD | ADD | Needs all |
| TravelGuideAgent | ADD | ADD | ADD | Needs all |
| TripAnalysisAgent | ADD | ADD | already done | Partial |

### Claude's Discretion
- Exact German labels and placeholder wording for the new form fields
- Ordering of wishes fields within Step 2 (relative to styles and travelers)
- Exact prompt phrasing per agent (follow German prompt convention)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backend Models
- `backend/models/travel_request.py` — TravelRequest Pydantic model with existing `travel_description`, `preferred_activities`, `mandatory_activities` fields

### Agent Reference Implementation
- `backend/agents/activities_agent.py` lines 183-185 — Reference pattern for conditional wishes inclusion in prompts (all 3 fields already implemented)
- `backend/agents/route_architect.py` lines 47-50, 122 — Partial implementation (travel_description + mandatory_activities)

### Frontend Form
- `frontend/js/form.js` — Form structure, `buildPayload()` function (line 729+), tag input pattern for mandatory activities
- `frontend/js/state.js` — S object state management, TRAVEL_STYLES constant

### Agent Files to Update
- `backend/agents/stop_options_finder.py` — Needs all 3 fields
- `backend/agents/region_planner.py` — Needs all 3 fields
- `backend/agents/accommodation_researcher.py` — Needs all 3 fields
- `backend/agents/restaurants_agent.py` — Needs all 3 fields
- `backend/agents/day_planner.py` — Needs all 3 fields
- `backend/agents/travel_guide_agent.py` — Needs all 3 fields
- `backend/agents/trip_analysis_agent.py` — Needs travel_description + preferred_activities
- `backend/agents/route_architect.py` — Needs preferred_activities only

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **TravelRequest model:** All 3 fields already defined with validation (max lengths, list limits)
- **MandatoryActivity model:** Nested model with `name` + optional `location` (lines 19-21 of travel_request.py)
- **ActivitiesAgent prompt pattern:** Conditional inclusion template at lines 183-185 — copy this for other agents
- **Tag input component:** Existing pattern for `S.mandatoryTags` in form.js — reuse for `preferred_activities`
- **Orchestrator:** Already passes full TravelRequest to all agents — no changes needed

### Established Patterns
- Agent prompts use conditional blocks: `f"\nReisebeschreibung: {req.travel_description}" if req.travel_description else ""`
- Form fields restored from localStorage cache in form restoration logic
- buildPayload() assembles all form data into TravelRequest-compatible dict

### Integration Points
- `buildPayload()` in form.js — must populate `preferred_activities` from new `S.preferredTags` state
- `S` object in state.js — add `preferredTags: []` field
- Step 2 HTML in index.html — add preferred activities tag input section
- Form cache/restore logic — persist `preferredTags` to localStorage

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches following the established patterns.

</specifics>

<deferred>
## Deferred Ideas

### Reviewed Todos (not folded)
- "RouteArchitect ignores daily drive limits and suggests ferries/islands" — Phase 13 scope (Architect Pre-Plan), not context forwarding

None other — discussion stayed within phase scope.

</deferred>

---

*Phase: 12-context-infrastructure-wishes-forwarding*
*Context gathered: 2026-03-29*
