# Trip Legs & Explore Mode — Design Spec

**Date:** 2026-03-11
**Status:** Approved
**Scope:** Route planning architecture — replace flat via-points with explicit trip legs, add explore mode for regional circuits

---

## Problem

The current route planner treats every trip as a single planning problem: get from A to B efficiently, with optional via-points and auto-detected Rundreise mode when time is abundant. This breaks down for multi-phase trips like:

> Drive from Switzerland to Greece (transit) → explore Greece for 4 weeks (regional circuit) → drive back (transit)

These phases have fundamentally different planning goals:
- **Transit:** Make distance efficiently with well-balanced daily drives and interesting stops along the way
- **Explore:** Discover the best spots in a region, respecting local logistics (ferries, terrain), without caring about reaching a far endpoint

---

## Solution

Replace the flat `via_points[]` model with explicit **trip legs**. Each leg has a mode: **transit** or **explore**. The planning engine applies different logic per leg.

---

## Data Model

### New file: `models/trip_leg.py`

```python
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator
from datetime import date


class ZoneBBox(BaseModel):
    north: float = Field(ge=-90, le=90)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    west: float = Field(ge=-180, le=180)
    zone_label: str = Field(max_length=100)   # e.g. "Griechenland"

    @model_validator(mode="after")
    def validate_bbox(self) -> "ZoneBBox":
        if self.south >= self.north:
            raise ValueError("south must be less than north")
        return self


class ExploreStop(BaseModel):
    """One stop in an AI-planned explore circuit."""
    name: str = Field(max_length=200)           # concrete town/city, never a region
    lat: float
    lon: float
    suggested_nights: int = Field(ge=1, le=14)
    significance: Literal["anchor", "scenic", "hidden_gem"]
    logistics_note: str = Field(default="", max_length=500)
    # e.g. "Fähre nach Santorini — im Voraus buchen"


class ExploreZoneAnalysis(BaseModel):
    """First-pass output from ExploreZoneAgent — persisted in Redis job state."""
    zone_characteristics: str = Field(max_length=2000)
    # e.g. "Inselreich mit Fährverbindungen; Küstenstraßen eng"
    preliminary_anchors: list[str] = Field(default=[])
    # ordered list of must-see names, pre-circuit-refinement
    guided_questions: list[str] = Field(min_length=1, max_length=3)
    # zone-specific questions for user, e.g. "Sollen Inseln eingeschlossen werden?"


class TripLeg(BaseModel):
    leg_id: str = Field(pattern=r"^leg-\d+$")
    start_location: str = Field(max_length=200)
    end_location: str = Field(max_length=200)
    start_date: date
    end_date: date
    mode: Literal["transit", "explore"]

    # Transit only
    via_points: list[ViaPoint] = Field(default=[])   # existing ViaPoint, unchanged

    # Explore only
    zone_bbox: Optional[ZoneBBox] = None
    zone_guidance: list[str] = Field(default=[])   # user answers to guided questions

    @model_validator(mode="after")
    def validate_leg(self) -> "TripLeg":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if self.mode == "explore" and self.zone_bbox is None:
            raise ValueError("explore legs require zone_bbox")
        return self

    @property
    def total_days(self) -> int:
        return (self.end_date - self.start_date).days


class ExploreAnswersRequest(BaseModel):
    answers: list[str] = Field(min_length=1, max_length=3)
```

Note: `ViaPoint` is imported from `models.travel_request` (no circular import — `TripLeg` imports from that module, `TravelRequest` imports `TripLeg`; split into `models/via_point.py` if needed).

### Changes to `models/travel_request.py`

**Remove** these fields (breaking schema change — existing persisted Redis jobs from before this change are incompatible; no migration needed since jobs TTL in 24h):
```
start_location, main_destination, start_date, end_date, total_days, via_points
```

**Add:**
```python
from models.trip_leg import TripLeg

legs: list[TripLeg] = Field(min_length=1, max_length=20)
```

**Add derived properties** (replaces the removed explicit fields — existing agent/orchestrator code calling `req.start_location` etc. continues to work without changes):
```python
@property
def start_location(self) -> str:
    return self.legs[0].start_location.strip()

@property
def main_destination(self) -> str:
    return self.legs[-1].end_location.strip()

@property
def start_date(self) -> date:
    return self.legs[0].start_date

@property
def end_date(self) -> date:
    return self.legs[-1].end_date

@property
def total_days(self) -> int:
    return sum(leg.total_days for leg in self.legs)

@property
def via_points(self) -> list[ViaPoint]:
    """Flattened via_points across all transit legs — for agents that don't need leg awareness."""
    return [vp for leg in self.legs if leg.mode == "transit" for vp in leg.via_points]
```

**Add cross-leg validator** (after budget validator):
```python
@model_validator(mode="after")
def validate_legs_chain(self) -> "TravelRequest":
    for i in range(1, len(self.legs)):
        prev, curr = self.legs[i - 1], self.legs[i]
        # Normalize before comparing to avoid casing/whitespace mismatch
        if prev.end_location.strip().lower() != curr.start_location.strip().lower():
            raise ValueError(
                f"Leg {i} start_location must match leg {i-1} end_location "
                f"(got '{curr.start_location}' vs '{prev.end_location}')"
            )
        if curr.start_date != prev.end_date:
            raise ValueError(
                f"Leg {i} start_date must equal leg {i-1} end_date"
            )
    return self
```

**Note on `proximity_origin_pct` / `proximity_target_pct`:** These remain global fields. The orchestrator passes the *current leg's* `start_location` as `origin_location` and `end_location` as `target_location` into the route geometry dict per leg — not the global trip start/end. The `route_geometry_cache` keys are scoped to `leg_{leg_index}_{stop_counter}` to avoid cross-leg collisions.

**Note on `min_nights_per_stop` / `max_nights_per_stop`:** These apply to transit legs only. For explore legs, `suggested_nights` from `ExploreStop` is authoritative; the sliders are hidden in the UI.

**Update `tests/test_models.py`:** All tests referencing removed top-level fields (`start_location`, `main_destination`, `start_date`, `end_date`, `via_points`, `total_days`) must be rewritten to use `legs`. This is listed explicitly as a required change.

---

## Job State (Redis)

### Full initial job state — `_new_job(job_id, req)` in `main.py`

The existing function signature is `_new_job(request)`. It becomes `_new_job(job_id, req)` (job_id needed to look up TTL context and for future use). All callers in `main.py` updated accordingly.

```python
def _new_job(job_id: str, req: TravelRequest) -> dict:
    return {
        "status": "building_route",
        "request": req.model_dump(mode="json"),
        "selected_stops": [],

        # Leg tracking
        "leg_index": 0,
        "current_leg_mode": req.legs[0].mode,

        # Transit leg state — reset on each leg transition
        "segment_index": 0,
        "segment_budget": _calc_leg_segment_budget(req, leg_index=0),
        "segment_stops": [],
        "stop_counter": 0,
        "route_geometry_cache": {},
        "route_could_be_complete": False,
        "current_options": [],

        # Explore leg state — reset on each explore leg transition
        "explore_phase": None,
        # None | "awaiting_guidance" | "circuit_ready" | "selecting_stops"
        "explore_zone_analysis": None,      # ExploreZoneAnalysis dict, set after first pass
        "explore_circuit": [],              # list[ExploreStop dicts], set after second pass
        "explore_circuit_position": 0,      # which circuit stop is being interactively selected

        "result": None,
        "error": None,
    }
```

**`explore_phase` is the state discriminator for pause/resume.** It eliminates the race condition identified in review:

| `explore_phase` | `zone_guidance_pending` (old) | Meaning |
|---|---|---|
| `None` | — | Transit leg or explore leg not yet started |
| `"awaiting_guidance"` | True | First-pass done; waiting for user answers |
| `"circuit_ready"` | False | Second-pass done; circuit shown to user |
| `"selecting_stops"` | False | User actively selecting stops from circuit |

### Segment budget helper

```python
def _calc_leg_segment_budget(req: TravelRequest, leg_index: int) -> int:
    leg = req.legs[leg_index]
    n_segments = max(1, len(leg.via_points) + 1)
    budget = leg.total_days // n_segments
    # Preserve existing min guard: at least (min_nights_per_stop + 1) * 2
    min_days = (req.min_nights_per_stop + 1) * 2
    return max(min_days, budget)
```

### Leg transition

When a leg completes (transit: all segments + destination confirmed; explore: all circuit positions confirmed):
1. Append confirmed stops to `selected_stops`
2. Reset per-leg state fields
3. Increment `leg_index`
4. If `leg_index < len(req.legs)`: update `current_leg_mode`, push `leg_complete` SSE event, begin next leg
5. If `leg_index == len(req.legs)`: proceed to full research + day planning (unchanged)

---

## SSE Events

### New events

| Event | Payload | Purpose |
|---|---|---|
| `explore_zone_questions` | `{questions: string[], leg_id: string}` | Zone guidance questions for user |
| `explore_circuit_ready` | `{circuit: ExploreStop[], warnings: string[], leg_id: string}` | Full planned circuit |
| `leg_complete` | `{leg_id: string, leg_index: int, mode: string}` | Any leg done (transit or explore), next starting |

### Unchanged events

`route_option_ready`, `stop_done`, `accommodations_loaded`, `job_complete`, `job_error` — all unchanged.

---

## Pause/Resume for Zone Guidance

The explore planning flow needs user input mid-job. Uses **`explore_phase` in Redis + Celery re-enqueue** — no new async primitives.

**Flow:**

1. `_run_job()` calls `ExploreZoneAgent.run_first_pass()` → stores result in `job["explore_zone_analysis"]`, sets `job["explore_phase"] = "awaiting_guidance"`, pushes `explore_zone_questions` SSE event, sets `job["status"] = "awaiting_zone_guidance"`, saves to Redis, then **returns normally** (no error).

2. `POST /api/answer-explore-questions/{job_id}` receives `ExploreAnswersRequest`:
   - Loads job, validates `explore_phase == "awaiting_guidance"` (else 409)
   - Appends answers to `job["request"]["legs"][job["leg_index"]]["zone_guidance"]`
   - Sets `job["explore_phase"] = "circuit_ready"` (signals resume path)
   - Sets `job["status"] = "building_route"`
   - Saves to Redis
   - Re-enqueues: `run_planning_job_task.delay(job_id)`

3. `_run_job()` resumes. Entry logic checks `explore_phase`:
   - `== "circuit_ready"` → run second-pass zone analysis → generate circuit → set `explore_phase = "selecting_stops"` → push `explore_circuit_ready` → continue with interactive stop selection
   - `== "selecting_stops"` → resume interactive stop selection at `explore_circuit_position`
   - `None` / transit → existing flow

4. **Timeout:** A lightweight periodic check (existing Redis TTL mechanism — no new worker needed): if `status == "awaiting_zone_guidance"` and job age > 30 min, set `status = "error"`, push `job_error` with message `"Zeitüberschreitung bei der Zonenführung — bitte neu starten"`.

---

## Backend Planning Flow

### Orchestrator (`orchestrator.py`)

`TravelPlannerOrchestrator.run()` becomes leg-aware. The existing signature `run(pre_built_stops, pre_selected_accommodations, pre_all_accommodation_options)` is unchanged — `pre_built_stops` is now the full `selected_stops` list across all already-completed legs.

```python
async def run(self, pre_built_stops=None, ...):
    # If pre_built_stops supplied (resume path), skip straight to research
    if pre_built_stops:
        return await self._run_research_and_planning(pre_built_stops, ...)

    all_stops = []
    job = self._load_job()  # reads Redis
    for leg_index in range(job["leg_index"], len(self.req.legs)):
        leg = self.req.legs[leg_index]
        if leg.mode == "transit":
            stops = await self._run_transit_leg(leg, leg_index)
        else:
            stops = await self._run_explore_leg(leg, leg_index)
        all_stops.extend(stops)

    return await self._run_research_and_planning(all_stops, ...)
```

`RouteArchitectAgent` is **not called for explore legs** — `ExploreZoneAgent` replaces it. `DayPlannerAgent` receives the combined `all_stops` list after all legs, same shape as today.

### Transit legs

Unchanged logic:
- `StopOptionsFinder` → `direct / scenic / cultural` options
- Segments from `leg.via_points`
- OSRM enrichment, proximity filters
- `proximity_origin_pct` resolves against `leg.start_location`, `proximity_target_pct` against `leg.end_location`
- `route_geometry_cache` keys prefixed `leg{leg_index}_` to avoid cross-leg collisions

**Removed:**
- Rundreise / detour auto-detection
- `DetourOptionsAgent` calls
- `StopOptionsFinder` Rundreise prompt branch

### Explore legs

**`ExploreZoneAgent`** (`agents/explore_zone_agent.py`) — `claude-opus-4-5`:

First pass prompt inputs: `zone_bbox`, `zone_label`, travel styles, total days in leg, mandatory/preferred activities.

First pass JSON output schema (returned and parsed via `parse_agent_json()`):
```json
{
  "zone_characteristics": "string",
  "preliminary_anchors": ["string"],
  "guided_questions": ["string", "string"]
}
```
Validated against `ExploreZoneAnalysis` Pydantic model.

Second pass prompt inputs: first-pass output + `zone_guidance` answers.

Second pass JSON output schema:
```json
{
  "circuit": [
    {
      "name": "string",
      "lat": 0.0,
      "lon": 0.0,
      "suggested_nights": 3,
      "significance": "anchor|scenic|hidden_gem",
      "logistics_note": "string"
    }
  ],
  "warnings": ["string"]
}
```
`circuit` validated as `list[ExploreStop]`.

**`StopOptionsFinder` explore branch** — `claude-sonnet-4-5`:

New prompt branch activated when `explore_mode=True` in route geometry. Key differences from transit branch:
- No `segment_target` or endpoint proximity filter
- Receives: current circuit position name, surrounding circuit stops, zone bbox, zone characteristics, days remaining in explore leg
- Option types: `"anker"` (must-see anchor), `"landschaft"` (scenic alternative), `"geheimtipp"` (off-the-beaten-path surprise)
- `drive_hours` validated against `max_drive_hours_per_day` as usual
- `suggested_nights` from `ExploreStop` passed as recommended value in prompt; agent returns nights per option

---

## New API Endpoints

| Method | Path | Body | Purpose |
|---|---|---|---|
| `POST` | `/api/answer-explore-questions/{job_id}` | `ExploreAnswersRequest` | Submit zone guidance answers; re-enqueues job |

### Removed endpoints

- `POST /api/set-rundreise-mode/{job_id}` — removed entirely, no replacement

---

## Frontend Changes

### Step 3: Legs Builder (`form.js`, `index.html`)

Replaces current via-points section. Activities section remains below, unchanged.

**Leg card header:** Numbered badge, `start → end`, date range, day count, mode toggle (Transit | Erkunden).

**Transit leg (expanded):** Via-points tag-input, same as current.

**Explore leg (expanded):**
- Leaflet map with rectangle draw tool (bbox drag)
- Zone label input — auto-filled from Nominatim geocoding of bbox center (`address.country` → fallback `address.state` → fallback "Zone"); editable
- If Nominatim fails: silently use "Zone" as default, no error shown

**Leg management:**
- Step 1 still collects global `start_location` + `main_destination` + date range (unchanged)
- Legs builder pre-creates first leg (`start_location → main_destination`) and user adds boundaries
- "Schnitt hinzufügen" inserts a new leg boundary city; frontend auto-chains `end_location` of leg N → `start_location` of leg N+1
- Adjusting leg end date shifts next leg's start date; total must equal trip days — validated before form submit
- Transit: blue (`#4a90d9`), Explore: amber (`#e0b840`)
- `min_nights_per_stop` / `max_nights_per_stop` sliders hidden for explore legs in Step 4

### Route builder (`route-builder.js`)

**Transit legs:** No change to existing stop selection UI.

**Explore legs:**
- After `explore_zone_questions` SSE: show inline question cards in route builder panel; user types/selects answers, submits via `answerExploreQuestions()`
- After `explore_circuit_ready` SSE: display full circuit on map as preview polyline with markers; show circuit stop list in sidebar
- Interactive stop selection proceeds with `anker / landschaft / geheimtipp` card types

**Removed:** Rundreise suggestion banner, "Rundreise aktivieren" button, all `setRundreiseMode()` calls.

### `api.js`

```javascript
async function answerExploreQuestions(jobId, answers) {
    return await apiFetch(`/api/answer-explore-questions/${jobId}`, {
        method: "POST",
        body: JSON.stringify({ answers }),
    });
}
```

---

## Agent Model Assignments (updated)

| Agent | Mode | Model (Prod) | Model (Test) |
|---|---|---|---|
| `ExploreZoneAgent` (new) | Explore | `claude-opus-4-5` | `claude-haiku-4-5` |
| `StopOptionsFinder` (transit branch) | Transit | `claude-sonnet-4-5` | `claude-haiku-4-5` |
| `StopOptionsFinder` (explore branch) | Explore | `claude-sonnet-4-5` | `claude-haiku-4-5` |
| `DetourOptionsAgent` | **removed** | — | — |
| `RouteArchitectAgent` | Transit only | `claude-opus-4-5` | `claude-haiku-4-5` |
| `DayPlannerAgent` | Both (post-all-legs) | `claude-opus-4-5` | `claude-haiku-4-5` |
| All research agents | Both | `claude-sonnet-4-5` | `claude-haiku-4-5` |

---

## What Is Not Changing

- Research agents (Activities, Restaurants, Accommodation, TravelGuide, DayPlanner) — operate per-stop regardless of leg mode
- Budget model, budget percentage split
- OSRM enrichment, Nominatim geocoding, all existing utilities
- SSE streaming infrastructure
- Interactive stop selection UX (card UI, `route_option_ready`, `stop_done` events)
- Redis job TTL (24h), `call_with_retry()`, `parse_agent_json()`

---

## Files Affected

### New files
- `backend/agents/explore_zone_agent.py`
- `backend/models/trip_leg.py` — `TripLeg`, `ZoneBBox`, `ExploreStop`, `ExploreZoneAnalysis`, `ExploreAnswersRequest`

### Modified files
- `backend/models/travel_request.py` — remove flat route fields, add `legs`, add derived properties + cross-leg validator
- `backend/orchestrator.py` — leg-sequential `run()`, `_run_transit_leg()` / `_run_explore_leg()` split
- `backend/main.py` — `_new_job(job_id, req)` rewrite, `_calc_leg_segment_budget()`, new `answer-explore-questions` endpoint, remove `set-rundreise-mode`, leg-aware routing in `select-stop`, `route_geometry_cache` key prefix
- `backend/agents/stop_options_finder.py` — add explore prompt branch, new option types, remove Rundreise branch
- `backend/tasks/run_planning_job.py` — `explore_phase`-based resume logic, `awaiting_zone_guidance` status handling
- `frontend/js/form.js` — Step 3 legs builder UI, Leaflet bbox draw tool, zone label geocoding
- `frontend/js/route-builder.js` — explore circuit display, guided questions UI, remove Rundreise banner + button
- `frontend/js/api.js` — `answerExploreQuestions()` wrapper
- `frontend/index.html` — legs builder markup
- `frontend/js/types.d.ts` — regenerated from updated OpenAPI schema
- `backend/tests/test_models.py` — rewrite all tests referencing removed top-level fields to use `legs`
- `backend/tests/test_endpoints.py` — update request payloads to legs structure
- `backend/tests/test_agents_mock.py` — update agent tests for explore branch
