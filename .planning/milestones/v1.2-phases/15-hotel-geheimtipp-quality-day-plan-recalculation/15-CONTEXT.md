# Phase 15: Hotel Geheimtipp Quality + Day Plan Recalculation - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Two distinct capabilities: (1) Server-side quality enforcement for Geheimtipp hotel recommendations — distance validation and dedup within each stop. (2) Proper nights editing flow — dedicated UI button replacing prompt(), arrival_day rechaining, and day plan recalculation via Celery with SSE progress.

</domain>

<decisions>
## Implementation Decisions

### Geheimtipp Distance Validation (ACC-01)
- **D-01:** Primary fix is prompt-level: include the stop's lat/lon coordinates explicitly in the accommodation researcher prompt (e.g., "Zentrum: 47.38°N, 8.54°E — alle Unterkünfte müssen innerhalb von X km davon liegen."). Gives Claude a concrete geographic reference instead of just a city name.
- **D-02:** Secondary safety net: haversine post-processing in `accommodation_researcher.py` after Claude returns options. Any Geheimtipp exceeding `hotel_radius_km` from the stop's lat/lon is silently dropped. User sees 3 options instead of 4 — honest, no retry for replacement.
- **D-03:** The haversine validation requires geocoding the Geheimtipp hotel name to get coordinates, OR requiring Claude to return approximate coordinates. Since we chose name-based dedup (D-05), the haversine check can use Google Places `search_hotels()` which is already called in the agent (line 279-280) to resolve hotel locations.

### Geheimtipp Dedup (ACC-02)
- **D-04:** Case-insensitive exact match on hotel `name` within the same stop's options. Simple safety net — Claude rarely returns duplicates within one stop.
- **D-05:** No lat/lon added to AccommodationOption model. Name-based dedup is sufficient for within-stop deduplication.

### Nights Edit UX (BDG-02)

### Claude's Discretion
- Nights edit UI: replacing `prompt()` with a dedicated button. Claude decides inline edit vs modal, button placement, and styling. Must follow existing edit patterns in `guide-edit.js`.
- Recalculation trigger: when nights change, Claude decides the Celery task pattern (new task vs extending existing). Follow the established pattern from add/remove/reorder stop tasks in `backend/tasks/`.
- `arrival_day` rechaining: use existing `recalc_arrival_days()` from `route_edit_helpers.py`.
- Day plan refresh: use existing `run_day_planner_refresh()` from `route_edit_helpers.py`.
- SSE progress feedback during recalculation: follow existing SSE patterns from replace_stop_job.
- Migration for existing saved travels with incorrect arrival_day: Claude decides if needed based on analysis of how `_editStopNights()` currently persists data (local-only, no backend call — may not need migration if arrival_day is recalculated on load).
- Edge cases: nights validation range (currently 1-14 in frontend), budget impact of nights changes.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Accommodation Agent
- `backend/agents/accommodation_researcher.py` — Main file: prompt construction (lines 120-135), post-processing (lines 250-280), Google Places enrichment
- `backend/models/accommodation_option.py` — AccommodationOption model with `is_geheimtipp`, `geheimtipp_hinweis` fields

### Route Edit Helpers
- `backend/utils/route_edit_helpers.py` — `recalc_arrival_days()`, `run_day_planner_refresh()`, `recalc_segment_directions()` — reuse these for nights edit
- `backend/tasks/add_stop_job.py` — Reference pattern for Celery task that calls recalc helpers
- `backend/tasks/remove_stop_job.py` — Reference pattern for Celery task with SSE progress
- `backend/tasks/reorder_stops_job.py` — Reference pattern for full recalc after structural change

### Frontend Nights Edit
- `frontend/js/guide-edit.js` lines 596-624 — Current `_editStopNights()` with `prompt()` — to be replaced
- `frontend/js/guide-stops.js` lines 19-20 — Current nights display with inline edit trigger

### Prior Phase Context
- `.planning/phases/14-stop-history-awareness-night-distribution/14-CONTEXT.md` — Night budget UI decisions (D-08), nights_remaining tracking
- `.planning/phases/13-architect-pre-plan-for-interactive-flow/13-CONTEXT.md` — Architect pre-plan decisions

### Requirements
- `.planning/REQUIREMENTS.md` — ACC-01, ACC-02, BDG-01, BDG-02, BDG-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `recalc_arrival_days(stops, from_index)` in `route_edit_helpers.py` — Already handles arrival_day rechaining; formula: `prev.arrival_day + prev.nights + 1`
- `run_day_planner_refresh(plan, stops, request, job_id)` in `route_edit_helpers.py` — Re-runs DayPlannerAgent on full plan, non-critical failure handling
- `search_hotels(lat, lon, radius_m)` in `utils/google_places.py` — Already used in accommodation researcher for Google Places enrichment; can validate Geheimtipp location
- Celery task pattern in `tasks/` — All existing edit tasks follow: parse job → modify stops → recalc helpers → SSE events → save

### Established Patterns
- Accommodation researcher already has stop `lat`/`lon` available (lines 95-96)
- All stop edit tasks use same SSE event pattern for progress feedback
- Frontend edit operations use `_editInProgress` guard to prevent concurrent edits
- `_fetchWithAuth()` for backend calls from frontend edit operations

### Integration Points
- `backend/main.py` — New endpoint needed for nights update (PATCH or POST pattern)
- `frontend/js/guide-edit.js` — Replace `_editStopNights()` with backend-calling version
- `backend/tasks/` — New Celery task for nights update + recalculation
- SSE stream — Progress events during day plan recalculation

</code_context>

<specifics>
## Specific Ideas

- User emphasized that the core Geheimtipp problem is that distance wasn't a key consideration in the prompt — the fix should primarily improve prompt quality by adding explicit coordinates, not just add post-processing validation.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 15-hotel-geheimtipp-quality-day-plan-recalculation*
*Context gathered: 2026-03-29*
