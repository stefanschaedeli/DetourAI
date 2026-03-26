# Phase 6: Wiring Fixes - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Close all audit gaps from the v1.0 milestone audit. Fix broken wiring between phases so every v1.0 requirement is fully satisfied: share_token persistence on reload, replace-stop hints UI, SSE event registration for style/ferry warnings, and stop tags population from AI agents.

</domain>

<decisions>
## Implementation Decisions

### Share toggle reload (SHR-01)
- **D-01:** API refetch is sufficient — the existing flow already calls `apiGetTravel()` on reload which returns `share_token`. Fix the toggle to correctly read the token after the fetch completes. No localStorage caching needed.

### Replace-stop hints UI (CTL-04)
- **D-02:** Add a simple text input field in the replace-stop dialog with a German placeholder like `z.B. mehr Strand, weniger Fahrzeit`. Backend already accepts freeform `hints` string via `ReplaceStopRequest.hints`.
- **D-03:** The hints field is optional — users can leave it empty and replace-stop works as before. No friction added to the existing flow.

### SSE warning display (AIQ-03, GEO-01)
- **D-04:** Register `style_mismatch_warning` and `ferry_detected` in the `openSSE()` events list in `api.js`. Add handler functions in `progress.js`.
- **D-05:** Both events display as toast notifications — brief, auto-dismissing, non-blocking.
- **D-06:** `style_mismatch_warning` uses warning style (amber/yellow): "Stilwarnung: Stopp passt nicht zum Reisestil".
- **D-07:** `ferry_detected` uses informational style (blue/neutral): "Faehre erkannt: Ueberfahrt von X nach Y". Ferries are not problems, just FYI.
- **D-08:** Ensure ferry cost is added to the budget calculation. Ferry cost formula already exists (CHF 50 base + CHF 0.5/km from Phase 2) — verify it's wired into the budget display.

### Stop tags generation (UIR-03)
- **D-09:** Both StopOptionsFinder and ActivitiesAgent contribute tags. StopOptionsFinder adds initial tags when stops are first suggested (travel style, geography). ActivitiesAgent enriches with activity-based tags during research.
- **D-10:** Tags are in German — matching the project convention. Examples: "Strand", "Kultur", "Wandern", "Kueste", "Insel", "Natur", "Berge".
- **D-11:** Maximum 3-4 tags per stop. Agent prompts should request this limit explicitly.
- **D-12:** Tags field already exists on TravelStop model (`tags: List[str] = []`) and frontend already renders them with `stop-tag-pill` CSS class. Only agent prompts and response parsing need changes.

### Claude's Discretion
- Toast notification styling and positioning (top vs bottom, auto-dismiss duration)
- Exact tag vocabulary — Claude can pick appropriate German tags from context
- How to merge/deduplicate tags when both agents contribute (simple union with dedup is fine)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Share toggle
- `frontend/js/guide.js` — `_renderShareToggle()` function (share UI), `showTravelGuide()` (where share_token is read)
- `frontend/js/travels.js` — `openSavedTravel()` (fetches plan with share_token)
- `backend/utils/travel_db.py` — `_sync_get()` returns share_token from DB

### Replace-stop hints
- `backend/main.py` — `ReplaceStopRequest` model and `/api/travels/{travel_id}/replace-stop` endpoint
- `backend/agents/stop_options_finder.py` — `extra_instructions` parameter in `find_options()`
- `frontend/js/guide.js` — Replace-stop dialog (where hints input needs to be added)

### SSE events
- `backend/agents/route_architect.py` — Emits `style_mismatch_warning` and `ferry_detected` events
- `frontend/js/api.js` — `openSSE()` events registration list
- `frontend/js/progress.js` — SSE handler functions

### Stop tags
- `backend/models/travel_response.py` — `TravelStop.tags` field definition
- `backend/agents/stop_options_finder.py` — Agent prompt (needs tags in JSON schema)
- `backend/agents/activities_agent.py` — Agent prompt (needs tag enrichment)
- `frontend/js/guide.js` — Tag pill rendering code (already implemented)

### Ferry budget
- `backend/utils/maps_helper.py` — Ferry cost formula (CHF 50 base + CHF 0.5/km)
- `backend/orchestrator.py` — Budget calculation pipeline

### Design system
- `DESIGN_GUIDELINE.md` — Apple-inspired design system (toast styling should align)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_renderShareToggle(travelId, shareToken)` in guide.js — already renders toggle correctly, just needs share_token passed correctly on reload
- `openSSE()` event registration pattern in api.js — just add two more event names to the array
- `stop-tag-pill` CSS class and tag rendering loop in guide.js — already implemented, waiting for data
- `extra_instructions` parameter in StopOptionsFinderAgent — backend already accepts and uses hints in prompt

### Established Patterns
- SSE handlers follow `on{EventName}` naming in progress.js
- Toast/notification pattern: check existing debug_log handler for positioning reference
- Agent JSON schemas define expected output fields — tags need to be added to the schema in prompts
- `esc()` function used for all user content interpolation (XSS prevention)

### Integration Points
- `openSavedTravel()` in travels.js → `showTravelGuide()` in guide.js → `_renderShareToggle()`: share_token flow
- Replace-stop dialog in guide.js → `apiReplaceStop()` in api.js → backend endpoint: hints flow
- `openSSE()` event list → handler functions in progress.js: SSE event flow
- StopOptionsFinder prompt → TravelStop model → guide.js card rendering: tags flow

</code_context>

<specifics>
## Specific Ideas

- User noted: ensure ferry costs are added to the budget display (verify wiring from Phase 2 formula)
- User plans a future multi-language rebuild — keep all tags in German for now, no i18n infrastructure needed
- Tags should feel descriptive and helpful on the card, not just decorative

</specifics>

<deferred>
## Deferred Ideas

- Multi-language support for the entire app — user will request this as a bigger change in the future
- Preset hint chips for replace-stop (e.g., quick-select "Mehr Strand" buttons) — could enhance UX later but text input is sufficient for now

</deferred>

---

*Phase: 06-wiring-fixes*
*Context gathered: 2026-03-26*
