# Phase 2: Geographic Routing - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Handle island and coastal destinations with ferry awareness, producing complete routes across water crossings. This phase covers: ferry crossing detection, port/island knowledge, Google Directions failure handling for water crossings, and ferry time integration into daily schedules and budgets.

Requirements: GEO-01, GEO-02, GEO-03, GEO-04, GEO-05

</domain>

<decisions>
## Implementation Decisions

### Ferry Detection Strategy (GEO-01, GEO-03)
- **D-01:** Detect water crossings via **haversine vs driving distance divergence**. When Google Directions returns `(0.0, 0.0, "")` between two stops, or the driving distance is implausibly longer than haversine distance for the region, infer a ferry crossing.
- **D-02:** Route architect prompt explicitly instructs Claude to identify ferry segments when planning routes to/through island destinations. AI identifies the need; validation confirms it.
- **D-03:** Ferry crossings appear as **dedicated ferry legs** in the route — distinct from driving legs. SSE events include a ferry indicator and estimated crossing time.

### Port/Island Knowledge Base (GEO-04)
- **D-04:** Primary ferry port identification is done by **the route architect agent** (claude-opus-4-5). A lightweight lookup table of major island groups provides validation hints but is not the primary source.
- **D-05:** Island group coverage: **Common Mediterranean** — Greek islands (Cyclades, Dodecanese, Ionian), Corsica, Sardinia, Sicily, Balearics, Croatian islands. The AI handles edge cases beyond this list.
- **D-06:** The lookup table maps island groups to their **primary ferry ports** (e.g. Cyclades → Piraeus, Corsica → Nice/Marseille/Livorno). This helps validate AI suggestions, not replace them.

### Google Directions Failure Handling (GEO-03)
- **D-07:** When Google Directions returns no route for a water crossing, construct a **haversine-based ferry estimate** instead of failing. Estimated ferry speed: ~30 km/h average. Segment flagged as `is_ferry: true`.
- **D-08:** **No retry** with different waypoints — Google Directions will never find driving routes across water. Use the ferry estimate directly, saving API calls.

### Coordinate Resolution (GEO-02)
- **D-09:** Stop finder coordinate validation (from Phase 1 corridor check) is extended: when the destination is an island, the corridor check must use the **island's actual bounding box**, not a land-based corridor from the mainland.
- **D-10:** When geocoding island destinations, validate that resolved coordinates fall **on the island** (not nearby mainland). Use haversine distance from island center as a sanity check.

### Daily Schedule Impact (GEO-05)
- **D-11:** Ferry crossing time is **deducted from the daily max_drive_hours**. A 3-hour ferry on a 4.5h/day budget leaves 1.5h of actual driving. DayPlanner must account for this.
- **D-12:** Ferry cost tracked as a **separate budget line** (`ferries_chf`). The field already exists in the output generator. Claude estimates ferry cost based on route, vehicle type, and passenger count.

### Claude's Discretion
- Exact haversine/driving distance divergence threshold for ferry detection
- Ferry speed estimate (30 km/h suggested, can tune)
- Lookup table format and data structure (dict, JSON file, or inline)
- How many ferry port alternatives to include per island group
- Exact wording of German-language ferry-related SSE messages
- Whether to show ferry duration as a range (e.g. "2-4 Stunden") or point estimate

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Route Planning Agents
- `backend/agents/route_architect.py` — Route planning agent, needs ferry-aware prompts
- `backend/agents/stop_options_finder.py` — Stop finder, needs island coordinate validation
- `backend/agents/region_planner.py` — Region planning for explore legs, needs island awareness
- `backend/agents/day_planner.py` — Day schedule agent, must account for ferry time in driving budget

### Maps & Geocoding
- `backend/utils/maps_helper.py` — `google_directions()`, `haversine_km()`, `bearing_degrees()`, `geocode_google()` — core functions that need ferry fallback logic
- `backend/utils/google_places.py` — Place validation, relevant for island stop verification

### Models
- `backend/models/stop_option.py` — StopOption model, may need `is_ferry` or transport mode fields
- `backend/models/travel_response.py` — TravelStop/TripLeg models, need ferry leg representation

### Existing Ferry References
- `backend/agents/output_generator.py:77,159` — Already has `ferries_chf` cost field
- `backend/tests/test_agents_mock.py:71` — Route architect mock already returns `ferry_crossings: []`

### Orchestration
- `backend/main.py` — Streaming option finder, route enrichment, corridor validation (lines ~460-900)
- `backend/orchestrator.py` — Planning pipeline coordination

### Phase 1 Context
- `.planning/phases/01-ai-quality-stabilization/01-CONTEXT.md` — Corridor validation decisions (D-02 through D-04) that this phase extends

### Requirements
- `.planning/REQUIREMENTS.md` — GEO-01 through GEO-05 acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `haversine_km()` in `maps_helper.py` — Distance calculation, usable for ferry distance estimation
- `bearing_degrees()` / `bearing_deviation()` in `maps_helper.py` — Direction calculations from Phase 1
- `proportional_corridor_buffer()` in `maps_helper.py` — Corridor validation, needs island-aware extension
- `google_directions()` returns `(0.0, 0.0, "")` on failure — clean detection point for ferry fallback
- `_haversine_km()` in `main.py:467` — Duplicate of maps_helper version, used in route validation
- `ferries_chf` field already exists in output generator cost breakdown
- `ferry_crossings` field already returned by route architect (visible in test mocks)

### Established Patterns
- All agents: build prompt → `call_with_retry()` → `parse_agent_json()` → log result
- Route validation in `main.py` lines ~800-900: corridor check, bearing check — extend with ferry detection
- SSE events for status updates — add ferry-specific events
- Cost estimation in DayPlanner `_fallback_cost_estimate()` — add ferry cost line

### Integration Points
- `google_directions()` return value `(0.0, 0.0, "")` is the ferry detection trigger
- Route architect prompt needs ferry awareness for island destinations
- `main.py` route enrichment loop (lines ~630, ~800) needs ferry fallback when directions fail
- DayPlanner schedule generation needs ferry time deduction from driving budget
- Frontend `route-builder.js` needs ferry leg visualization (future phase may handle UI, but backend must emit the data)

</code_context>

<specifics>
## Specific Ideas

- **Athens → Santorini test case:** The success criteria specifically require this route to produce a ferry via Piraeus. This is the primary validation scenario.
- **Graceful degradation:** If ferry detection fails, the route should still complete with a warning — never fail entirely because of a water crossing.
- **Existing scaffolding:** The `ferry_crossings` field in route architect response and `ferries_chf` in output generator show this was anticipated in the original design. Phase 2 fills in the actual logic.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-geographic-routing*
*Context gathered: 2026-03-25*
