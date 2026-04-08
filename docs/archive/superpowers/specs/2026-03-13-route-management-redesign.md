# Route Management Redesign

## Problem

Three issues with the current route management:

1. **Transit mode** uses DetourOptionsAgent as fallback when no stops fit the corridor. This sends users on detours instead of focusing on reaching the destination within the time budget.
2. **Explore mode** requires drawing a rectangle on a map — unintuitive and broken. Users can't express what they want to explore.
3. **StopOptionsFinder** sometimes returns regions (e.g., "Tessin") instead of concrete locations (e.g., "Bellinzona").

## Solution

### 1. Transit Mode — No Detours, User Guidance Fallback

**Remove DetourOptionsAgent entirely.** Replace with:

1. `StopOptionsFinder` searches for stops along the direct corridor. Prompt updated: "Finde Stopps entlang der direkten Route. Keine Umwege. Fokus auf Ankunft am Ziel innerhalb des Zeitbudgets." Proximity rules (min distance from start/destination) still apply.

2. If 0 valid options after enrichment+filtering:
   - Backend returns `{ "status": "no_stops_found", "corridor": { start, end, start_coords, end_coords } }`
   - Frontend shows corridor on Google Maps (start pin → end pin, polyline between them)
   - Below map: "Keine passenden Zwischenstopps auf dieser Strecke gefunden"
   - Text field: "Wo möchtest du anhalten? (z.B. 'In der Nähe von Annecy' oder 'Am Genfer See')"
   - User submits → reuses existing `POST /api/recompute-options/{job_id}` with `{ extra_instructions: "..." }` (endpoint already exists and accepts `extra_instructions`)
   - Backend re-runs `StopOptionsFinder` with guidance via existing `extra_instructions` parameter
   - If still 0 → "Auch mit deiner Angabe keine Stopps gefunden. Du kannst direkt zum Ziel fahren." + skip button

3. Delete `backend/agents/detour_options_agent.py` and all references (imports in main.py, fallback logic in `_find_and_stream_options()` lines 771-808, detour banner in route-builder.js).

### 2. Explore Mode — RegionPlannerAgent + Interactive Region Plan UI

Replace map-drawing with a text-based flow:

1. User types free-text description of what they want to explore
2. RegionPlannerAgent produces an ordered list of regions
3. Interactive UI lets user reorder, replace individual regions, or recalculate
4. On confirm → regions become invisible via_points → StopOptionsFinder drills down stop by step

#### RegionPlannerAgent (new)

**File:** `backend/agents/region_planner.py`

**Model:** claude-opus-4-5 (production) / claude-haiku-4-5 (test) — follows `get_model()` pattern from `_client.py`.

**Input:** Free-text description + trip metadata (days, travel styles, adults/children, max drive hours, start/end locations).

**System prompt:**
```
Du bist ein Reiserouten-Stratege. Plane eine Rundreise durch Regionen basierend auf der
Beschreibung des Reisenden. Ordne Regionen in einer logistisch sinnvollen Reihenfolge
(minimale Rückwege, geografische Effizienz). Jede Region soll ein Gebiet repräsentieren,
in dem der Reisende konkrete Stopps machen kann.
Antworte AUSSCHLIESSLICH als valides JSON-Objekt.
```

**Output:**
```json
{
  "regions": [
    { "name": "Tessin", "lat": 46.2, "lon": 8.95, "reason": "Mediterranes Flair, Seen" },
    { "name": "Graubünden", "lat": 46.8, "lon": 9.8, "reason": "Alpenlandschaft, Engadin" },
    { "name": "Vorarlberg", "lat": 47.2, "lon": 9.9, "reason": "Rückweg über Österreich" }
  ],
  "summary": "Rundreise durch die Süd- und Ostalpen mit mediterranem Einstieg"
}
```

**Three operations:**
1. `plan(description, leg)` — initial region plan from free text
2. `replace_region(index, instruction, current_plan)` — replace one region based on user text, keeping rest stable
3. `recalculate(instruction, current_plan)` — redo entire plan using current plan + correction as context

**Pydantic models (new in `models/trip_leg.py`):**
```python
class RegionPlanItem(BaseModel):
    name: str = Field(max_length=200)
    lat: float
    lon: float
    reason: str = Field(max_length=500)

class RegionPlan(BaseModel):
    regions: list[RegionPlanItem] = Field(min_length=1)
    summary: str = Field(max_length=1000)
```

#### Frontend: Region Plan UI

New section in route-builder.js, shown after explore leg starts.

**Layout:**
- **Left:** Ordered list of regions (drag-to-reorder via native HTML5 `draggable` + `dragstart`/`dragover`/`drop` events)
  - Each item: region name, reason, "Ersetzen" button
  - "Ersetzen" → expands text field below item: "Wie soll diese Region ersetzt werden?" + submit
  - On submit → `POST /api/replace-region/{job_id}` → only that region updates
- **Right:** Google Maps with numbered markers at region coordinates, polyline connecting them in order
  - Map updates after every reorder, replace, or recalculate
- **Bottom:** "Neu berechnen" button → expands text field: "Was soll geändert werden?" + submit
  - On submit → `POST /api/recompute-regions/{job_id}` → full list replaces
- **Confirm button:** "Route bestätigen" → proceeds to stop-by-stop drilling

#### Backend Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/plan-regions/{job_id}` | POST | Initial region plan from explore text |
| `/api/replace-region/{job_id}` | POST | Replace single region `{ index: int, instruction: str }` |
| `/api/recompute-regions/{job_id}` | POST | Recalculate all `{ instruction: str }` |
| `/api/confirm-regions/{job_id}` | POST | Lock regions → convert to invisible via_points → start stop finding |

**Request models:**
```python
class ReplaceRegionRequest(BaseModel):
    index: int = Field(ge=0)
    instruction: str = Field(max_length=1000)

class RecomputeRegionsRequest(BaseModel):
    instruction: str = Field(max_length=1000)
```

#### SSE Events

| Event | Data | Purpose |
|-------|------|---------|
| `region_plan_ready` | `{ regions: [...], summary: str }` | Initial region plan computed |
| `region_updated` | `{ regions: [...], summary: str }` | After replace or recompute |

**Removed SSE events:**
- `explore_zone_questions` — replaced by `region_plan_ready`
- `explore_circuit_ready` — no longer needed (regions → via_points, then normal stop flow)

**Removed SSE handlers in route-builder.js:**
- `showExploreGuidanceForm()` (lines 774-798)
- `submitGuidanceAnswers()` (lines 804-843)
- `showExploreCircuit()` (lines 845-871)

#### After Confirmation

When user confirms regions:
1. Backend converts regions to via_points on the leg (injected, not visible to user)
2. Starts StopOptionsFinder for the first segment (start → first region center)
3. Normal stop-by-stop flow — user picks stops, never sees "region" labels
4. Regions ensure StopOptionsFinder searches in the right geographic area

#### Redis Job State Changes

Replace current explore state fields in `_new_job()`:

```python
# Old (remove):
"explore_phase": None,
"explore_zone_analysis": None,
"explore_circuit": [],
"explore_circuit_position": 0,

# New:
"region_plan": None,           # RegionPlan dict after planning
"region_plan_confirmed": False, # True after user confirms
```

### 3. StopOptionsFinder — Locations Not Regions

**Prompt addition to system prompt:**
```
Nenne IMMER einen konkreten Ortsnamen (Stadt, Dorf, Gemeinde) — NIEMALS eine Region,
einen Kanton, ein Bundesland oder ein Tal. Beispiel: "Bellinzona" statt "Tessin",
"Chamonix" statt "Mont-Blanc-Region".
```

**JSON schema instructions:**
```
"region": "Konkreter Ortsname (Stadt/Dorf) — keine Regionen oder Gebiete"
```

**Explore-scoped segments** get additional prompt context via `extra_instructions`:
```
Suche Stopps in der Gegend von {region_name} (ca. {lat}, {lon}).
Finde konkrete Orte, nicht die Region selbst.
```

### 4. Form Changes — Explore Mode Input

Replace zone map drawing with single free-text textarea:

```html
<div class="explore-content" id="explore-content-${index}">
  <label>Was möchtest du erkunden?</label>
  <textarea id="explore-text-${index}"
    placeholder="z.B. 'Die Französischen Alpen — Bergdörfer, Seen und Alpenpässe'"
    rows="3"></textarea>
</div>
```

**Removed:** `initZoneMap()`, `geocodeZoneLabel()`, Leaflet.draw dependency (only used for zone drawing).

**TripLeg model changes:**
- **Add:** `explore_description: Optional[str] = None`
- **Keep:** `zone_bbox` (optional, unused in new flow but no schema breakage)
- **Keep:** `zone_guidance` (unused in new flow but no schema breakage)

**Data flow:** Textarea value stored in `S.legs[index].explore_description` → included in `buildPayload()` → sent to backend.

### 5. Model Changes Summary

**`backend/models/trip_leg.py`:**
- **Add:** `RegionPlanItem`, `RegionPlan` models
- **Add:** `ReplaceRegionRequest`, `RecomputeRegionsRequest` models
- **Add:** `explore_description: Optional[str] = None` on `TripLeg`
- **Keep:** `ZoneBBox`, `ExploreStop` (unused but no breakage)
- **Remove:** `ExploreZoneAnalysis`, `ExploreAnswersRequest` (no longer referenced)

### 6. Orchestrator Changes

**`backend/orchestrator.py`:**
- Remove import of `ExploreZoneAgent`, `ExploreZoneAnalysis`, `ExploreStop`
- Replace `_run_explore_leg()` method (lines 124-162) with region-based flow:
  - Call `RegionPlannerAgent.plan()` instead of `ExploreZoneAgent`
  - Store region plan in job state
  - No two-pass flow — single pass produces regions, user refines interactively

### 7. Removed Endpoint

**`POST /api/answer-explore-questions/{job_id}`** (main.py line 1997) — removed entirely. The two-pass explore flow (questions → answers) is replaced by the region plan endpoints.

Frontend references to remove:
- `answerExploreQuestions()` in `api.js` (line 152)
- SSE handlers for `explore_zone_questions` and `explore_circuit_ready` in `route-builder.js`

## End-to-End Flows

### Flow A: Transit (Happy Path)
```
Transit leg (A → B, 5 days)
  → StopOptionsFinder: 3 options along direct corridor
  → User picks stops one by one → route complete
```

### Flow B: Transit (No Stops Found)
```
Transit leg (A → B, 2 days, short distance)
  → StopOptionsFinder: 0 valid options
  → Frontend shows corridor on Google Maps + text field
  → User types guidance → POST /api/recompute-options/{job_id} with extra_instructions
  → StopOptionsFinder re-runs with guidance
  → Options found → normal flow (or skip to destination)
```

### Flow C: Explore
```
Explore leg, user types "Französische Alpen, Bergdörfer und Seen"
  → POST /api/plan-trip → leg.mode == "explore"
  → RegionPlannerAgent.plan(): [Annecy-Gebiet, Vanoise, Briançon, Provence-Alpen]
  → SSE region_plan_ready → Frontend shows region plan UI
  → User reorders, replaces, recalculates as needed
  → User clicks "Route bestätigen"
  → POST /api/confirm-regions/{job_id}
  → Backend converts regions to invisible via_points
  → StopOptionsFinder starts for segment 1
  → Normal stop-by-stop flow (user never sees region names)
```

### Flow D: Multi-Leg (Transit + Explore)
```
Leg 1: Transit (Liestal → Annecy, 3 days) → Flow A/B
Leg 2: Explore ("Französische Alpen erkunden", 5 days) → Flow C
Leg 3: Transit (→ Paris, 2 days) → Flow A/B
```

## File Changes Summary

| Action | File | Scope |
|--------|------|-------|
| **New** | `backend/agents/region_planner.py` | RegionPlannerAgent with plan/replace/recalculate |
| **Delete** | `backend/agents/detour_options_agent.py` | Entire file |
| **Delete** | `backend/agents/explore_zone_agent.py` | Entire file |
| **Edit** | `backend/main.py` | New region endpoints, remove detour fallback, remove answer-explore-questions endpoint, update `_new_job()` state, update `plan_trip()` explore branch |
| **Edit** | `backend/orchestrator.py` | Replace ExploreZoneAgent with RegionPlannerAgent, update `_run_explore_leg()` |
| **Edit** | `backend/agents/stop_options_finder.py` | Prompt: no detours, locations not regions, explore region context; remove `find_options_explore()`, `_build_prompt_explore()`, `SYSTEM_PROMPT_EXPLORE` (dead code after explore rework) |
| **Edit** | `backend/models/trip_leg.py` | Add RegionPlanItem, RegionPlan, ReplaceRegionRequest, RecomputeRegionsRequest, explore_description; remove ExploreZoneAnalysis, ExploreAnswersRequest |
| **Edit** | `frontend/js/form.js` | Replace zone map with textarea, remove initZoneMap/geocodeZoneLabel |
| **Edit** | `frontend/js/route-builder.js` | Region plan UI, no_stops_found corridor display, remove explore guidance/circuit handlers, remove detour banner |
| **Edit** | `frontend/js/api.js` | Remove answerExploreQuestions(), add region plan API calls, update SSE event list (add `region_plan_ready`/`region_updated`, remove `explore_zone_questions`/`explore_circuit_ready`) |
| **Edit** | `CLAUDE.md` | Add RegionPlannerAgent to agent model assignments table, update file tree (remove detour_options_agent.py, add region_planner.py) |
| **Edit** | `tests/` | See test changes section below |

## Test Changes

### Tests to remove/replace
- `test_agents_mock.py`: Tests referencing `ExploreZoneAgent` → replace with `RegionPlannerAgent` tests
- `test_endpoints.py`: Tests for `/api/answer-explore-questions` → replace with region endpoint tests
- `test_models.py`: Tests for `ExploreZoneAnalysis`, `ExploreAnswersRequest` → replace with `RegionPlan`, `RegionPlanItem` tests

### New tests needed
- `RegionPlannerAgent`: mock Anthropic, verify prompt structure, JSON parsing for all 3 operations
- Region endpoints: plan-regions, replace-region, recompute-regions, confirm-regions (happy path + error cases)
- `RegionPlan`/`RegionPlanItem` Pydantic validation
- Transit no-stops-found response shape
- `StopOptionsFinder` with explore region context (extra_instructions containing region guidance)
