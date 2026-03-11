# Trip Legs & Explore Mode Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat via-points trip model with explicit trip legs (transit / explore), adding a new ExploreZoneAgent that plans a regional circuit with guided questions, AI-assigned nights, and ferry/logistics awareness.

**Architecture:** Legs are defined upfront in a new form UI. Transit legs use the existing StopOptionsFinder flow unchanged. Explore legs use a new ExploreZoneAgent (Opus) that analyses a user-drawn zone, asks 2–3 guided questions, then generates an ordered circuit; stop selection is interactive as today. Legs are processed sequentially; all research and day-planning runs after all legs complete.

**Tech Stack:** Python/FastAPI, Pydantic v2, Celery + Redis, Anthropic SDK, Vanilla JS + Leaflet

---

## Chunk 1: Data Models

### Task 1: Extract `ViaPoint` and create `models/trip_leg.py`

**Why this order:** `TripLeg` needs `ViaPoint`. `ViaPoint` currently lives in `travel_request.py`, which will later import `TripLeg` — creating a circular import. Extract `ViaPoint` first so `trip_leg.py` can import it cleanly.

**Files:**
- Create: `backend/models/via_point.py`
- Modify: `backend/models/travel_request.py`
- Create: `backend/models/trip_leg.py`
- Test: `backend/tests/test_models.py` (add new test classes)

- [ ] **Step 1.1: Create `backend/models/via_point.py`**

```python
from typing import Optional
from pydantic import BaseModel, Field
from datetime import date


class ViaPoint(BaseModel):
    location: str = Field(max_length=200)
    fixed_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=500)
```

- [ ] **Step 1.2: Update `travel_request.py` — replace inline ViaPoint class with import**

In `backend/models/travel_request.py`, find and replace:
```python
class ViaPoint(BaseModel):
    location: str = Field(max_length=200)
    fixed_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=500)
```
With (at top of file, after other imports):
```python
from models.via_point import ViaPoint  # noqa: F401 — re-exported for backward compat
```

This keeps `ViaPoint` importable from `models.travel_request` so no existing agent code needs changing.

- [ ] **Step 1.3: Run existing tests to confirm nothing broke**

```bash
cd backend && python3 -m pytest tests/test_models.py -v
```
Expected: all existing tests PASS

- [ ] **Step 1.4: Write failing tests for new models**

Add to `backend/tests/test_models.py`:

```python
from models.trip_leg import ZoneBBox, ExploreStop, ExploreZoneAnalysis, ExploreAnswersRequest, TripLeg
from models.via_point import ViaPoint
from datetime import date
import pytest

class TestZoneBBox:
    def test_valid_bbox(self):
        bbox = ZoneBBox(north=42.0, south=36.0, east=28.0, west=20.0, zone_label="Griechenland")
        assert bbox.zone_label == "Griechenland"

    def test_south_must_be_less_than_north(self):
        with pytest.raises(ValueError, match="south must be less than north"):
            ZoneBBox(north=36.0, south=42.0, east=28.0, west=20.0, zone_label="X")

    def test_lat_bounds(self):
        with pytest.raises(ValueError):
            ZoneBBox(north=91.0, south=36.0, east=28.0, west=20.0, zone_label="X")


class TestExploreStop:
    def test_valid(self):
        s = ExploreStop(name="Athen", lat=37.97, lon=23.72,
                        suggested_nights=3, significance="anchor")
        assert s.significance == "anchor"
        assert s.logistics_note == ""

    def test_nights_bounds(self):
        with pytest.raises(ValueError):
            ExploreStop(name="X", lat=0, lon=0, suggested_nights=0, significance="anchor")

    def test_invalid_significance(self):
        with pytest.raises(ValueError):
            ExploreStop(name="X", lat=0, lon=0, suggested_nights=1, significance="unknown")


class TestExploreZoneAnalysis:
    def test_valid(self):
        a = ExploreZoneAnalysis(
            zone_characteristics="Küstengebiet",
            guided_questions=["Inseln einschließen?"]
        )
        assert len(a.guided_questions) == 1

    def test_requires_at_least_one_question(self):
        with pytest.raises(ValueError):
            ExploreZoneAnalysis(zone_characteristics="X", guided_questions=[])


class TestExploreAnswersRequest:
    def test_valid(self):
        r = ExploreAnswersRequest(answers=["Ja"])
        assert r.answers == ["Ja"]

    def test_max_3_answers(self):
        with pytest.raises(ValueError):
            ExploreAnswersRequest(answers=["a", "b", "c", "d"])

    def test_empty_answers_rejected(self):
        with pytest.raises(ValueError):
            ExploreAnswersRequest(answers=[])


class TestTripLeg:
    def _transit_leg(self, **kwargs):
        defaults = dict(
            leg_id="leg-0",
            start_location="Liestal",
            end_location="Lyon",
            start_date=date(2026, 6, 12),
            end_date=date(2026, 6, 15),
            mode="transit",
        )
        defaults.update(kwargs)
        return TripLeg(**defaults)

    def test_valid_transit_leg(self):
        leg = self._transit_leg()
        assert leg.total_days == 3

    def test_end_before_start_rejected(self):
        with pytest.raises(ValueError, match="end_date must be after start_date"):
            self._transit_leg(end_date=date(2026, 6, 10))

    def test_explore_requires_bbox(self):
        with pytest.raises(ValueError, match="explore legs require zone_bbox"):
            TripLeg(
                leg_id="leg-1",
                start_location="A", end_location="B",
                start_date=date(2026, 6, 15), end_date=date(2026, 7, 15),
                mode="explore",
            )

    def test_leg_id_pattern(self):
        with pytest.raises(ValueError):
            self._transit_leg(leg_id="bad-id")

    def test_valid_explore_leg(self):
        bbox = ZoneBBox(north=42, south=36, east=28, west=20, zone_label="Griechenland")
        leg = TripLeg(
            leg_id="leg-1",
            start_location="Athen", end_location="Athen",
            start_date=date(2026, 6, 15), end_date=date(2026, 7, 15),
            mode="explore", zone_bbox=bbox,
        )
        assert leg.total_days == 30

    def test_via_points_in_transit_leg(self):
        # via_points passed at construction time (Pydantic models are immutable by default)
        vp = ViaPoint(location="Bern")
        leg = self._transit_leg(via_points=[vp])
        assert len(leg.via_points) == 1
        assert leg.via_points[0].location == "Bern"
```

- [ ] **Step 1.5: Run to confirm FAIL**

```bash
cd backend && python3 -m pytest tests/test_models.py::TestZoneBBox tests/test_models.py::TestTripLeg -v
```
Expected: `ImportError` — `trip_leg` module doesn't exist yet

- [ ] **Step 1.6: Create `backend/models/trip_leg.py`**

```python
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator
from datetime import date
from models.via_point import ViaPoint  # no circular import — via_point has no deps


class ZoneBBox(BaseModel):
    north: float = Field(ge=-90, le=90)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    west: float = Field(ge=-180, le=180)
    zone_label: str = Field(max_length=100)

    @model_validator(mode="after")
    def validate_bbox(self) -> "ZoneBBox":
        if self.south >= self.north:
            raise ValueError("south must be less than north")
        return self


class ExploreStop(BaseModel):
    name: str = Field(max_length=200)
    lat: float
    lon: float
    suggested_nights: int = Field(ge=1, le=14)
    significance: Literal["anchor", "scenic", "hidden_gem"]
    logistics_note: str = Field(default="", max_length=500)


class ExploreZoneAnalysis(BaseModel):
    zone_characteristics: str = Field(max_length=2000)
    preliminary_anchors: list[str] = Field(default=[])
    guided_questions: list[str] = Field(min_length=1, max_length=3)


class ExploreAnswersRequest(BaseModel):
    answers: list[str] = Field(min_length=1, max_length=3)


class TripLeg(BaseModel):
    leg_id: str = Field(pattern=r"^leg-\d+$")
    start_location: str = Field(max_length=200)
    end_location: str = Field(max_length=200)
    start_date: date
    end_date: date
    mode: Literal["transit", "explore"]
    via_points: list[ViaPoint] = Field(default=[])
    zone_bbox: Optional[ZoneBBox] = None
    zone_guidance: list[str] = Field(default=[])

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
```

- [ ] **Step 1.7: Run all new model tests**

```bash
cd backend && python3 -m pytest tests/test_models.py::TestZoneBBox tests/test_models.py::TestExploreStop tests/test_models.py::TestExploreZoneAnalysis tests/test_models.py::TestExploreAnswersRequest tests/test_models.py::TestTripLeg -v
```
Expected: all PASS

- [ ] **Step 1.8: Commit**

```bash
git add backend/models/via_point.py backend/models/trip_leg.py backend/models/travel_request.py backend/tests/test_models.py
git commit -m "feat: ViaPoint extrahiert, TripLeg/ZoneBBox/ExploreStop Datenmodelle"
```

---

### Task 2 (old): ~~Extract ViaPoint~~ — merged into Task 1 above.

---

### Task 2: Migrate `TravelRequest` to use `legs`

**Files:**
- Modify: `backend/models/travel_request.py`
- Modify: `backend/tests/test_models.py`

**Important:** This is a breaking schema change. Existing Redis jobs (24h TTL) are naturally invalidated. No migration needed.

- [ ] **Step 3.1: Write failing tests for new TravelRequest shape**

Add to `backend/tests/test_models.py`:

```python
from models.trip_leg import TripLeg, ZoneBBox
from models.travel_request import TravelRequest

def _make_transit_leg(leg_id="leg-0", start="Liestal", end="Lyon",
                      s=date(2026,6,12), e=date(2026,6,15)):
    return TripLeg(leg_id=leg_id, start_location=start, end_location=end,
                   start_date=s, end_date=e, mode="transit")

def _make_explore_leg(leg_id="leg-1", start="Lyon", end="Athen",
                      s=date(2026,6,15), e=date(2026,7,15)):
    bbox = ZoneBBox(north=42, south=36, east=28, west=20, zone_label="Griechenland")
    return TripLeg(leg_id=leg_id, start_location=start, end_location=end,
                   start_date=s, end_date=e, mode="explore", zone_bbox=bbox)

class TestTravelRequestLegs:
    def _base_req(self, legs):
        return TravelRequest(legs=legs)

    def test_derived_properties(self):
        req = self._base_req([_make_transit_leg()])
        assert req.start_location == "Liestal"
        assert req.main_destination == "Lyon"
        assert req.total_days == 3
        assert req.start_date == date(2026, 6, 12)
        assert req.end_date == date(2026, 6, 15)

    def test_multi_leg_chain(self):
        leg0 = _make_transit_leg(end="Lyon", e=date(2026,6,15))
        leg1 = _make_explore_leg(start="Lyon", e=date(2026,7,15))
        req = self._base_req([leg0, leg1])
        assert req.total_days == 33

    def test_chain_validation_location_mismatch(self):
        leg0 = _make_transit_leg(end="Lyon", e=date(2026,6,15))
        leg1 = _make_explore_leg(start="Paris", s=date(2026,6,15), e=date(2026,7,15))
        with pytest.raises(ValueError, match="must match leg"):
            self._base_req([leg0, leg1])

    def test_chain_validation_date_mismatch(self):
        leg0 = _make_transit_leg(end="Lyon", e=date(2026,6,15))
        leg1 = _make_explore_leg(start="Lyon", s=date(2026,6,16), e=date(2026,7,15))
        with pytest.raises(ValueError, match="start_date must equal"):
            self._base_req([leg0, leg1])

    def test_via_points_property_flattens_transit_legs(self):
        from models.via_point import ViaPoint
        # Pass via_points at construction time — Pydantic v2 models are immutable
        leg0 = _make_transit_leg(via_points=[ViaPoint(location="Bern")])
        req = self._base_req([leg0])
        assert len(req.via_points) == 1
        assert req.via_points[0].location == "Bern"
```

- [ ] **Step 3.2: Run to confirm FAIL**

```bash
cd backend && python3 -m pytest tests/test_models.py::TestTravelRequestLegs -v
```
Expected: FAIL (TravelRequest still has old fields)

- [ ] **Step 3.3: Update `travel_request.py`**

Replace the route fields block and add legs + derived properties:

```python
from typing import List, Optional
from pydantic import BaseModel, field_validator, model_validator, Field
from datetime import date
from models.via_point import ViaPoint
from models.trip_leg import TripLeg


class Child(BaseModel):
    age: int

    @field_validator('age')
    @classmethod
    def age_valid(cls, v):
        if not 0 <= v <= 17:
            raise ValueError('age must be 0-17')
        return v


class MandatoryActivity(BaseModel):
    name: str = Field(max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)


class TravelRequest(BaseModel):
    # Route — now defined as legs
    legs: List[TripLeg] = Field(min_length=1, max_length=20)

    # Travellers
    adults: int = Field(default=2, ge=1, le=20)
    children: List[Child] = Field(default=[], max_length=10)
    travel_styles: List[str] = Field(default=[], max_length=14)
    travel_description: str = Field(default="", max_length=2000)

    # Activities
    mandatory_activities: List[MandatoryActivity] = Field(default=[], max_length=20)
    preferred_activities: List[str] = Field(default=[], max_length=20)
    max_activities_per_stop: int = Field(default=5, ge=1, le=20)
    max_restaurants_per_stop: int = Field(default=3, ge=1, le=10)
    activities_radius_km: int = Field(default=30, ge=1, le=200)

    # Route rules (global — apply to all legs)
    max_drive_hours_per_day: float = Field(default=4.5, ge=0.5, le=16)
    min_nights_per_stop: int = Field(default=1, ge=1, le=14)
    max_nights_per_stop: int = Field(default=5, ge=1, le=30)
    proximity_origin_pct: int = Field(default=10, ge=0, le=30)
    proximity_target_pct: int = Field(default=15, ge=0, le=30)

    # Accommodation
    accommodation_preferences: List[str] = Field(default=[], max_length=3)
    hotel_radius_km: int = Field(default=10, ge=1, le=100)

    # Budget
    budget_chf: float = Field(default=3000.0, ge=100, le=500_000)
    budget_buffer_percent: float = Field(default=10.0, ge=0, le=50)
    budget_accommodation_pct: int = Field(default=60, ge=0, le=100)
    budget_food_pct: int = Field(default=20, ge=0, le=100)
    budget_activities_pct: int = Field(default=20, ge=0, le=100)

    # --- Derived properties (replace removed explicit fields) ---

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
    def via_points(self) -> List[ViaPoint]:
        """Flattened via_points across all transit legs."""
        return [vp for leg in self.legs if leg.mode == "transit" for vp in leg.via_points]

    @model_validator(mode='after')
    def budget_pcts_sum_to_100(self):
        total = self.budget_accommodation_pct + self.budget_food_pct + self.budget_activities_pct
        if total != 100:
            raise ValueError(f'budget percentages must sum to 100 (got {total})')
        return self

    @model_validator(mode='after')
    def validate_legs_chain(self):
        for i in range(1, len(self.legs)):
            prev, curr = self.legs[i - 1], self.legs[i]
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

- [ ] **Step 3.4: Run new tests**

```bash
cd backend && python3 -m pytest tests/test_models.py::TestTravelRequestLegs -v
```
Expected: all PASS

- [ ] **Step 3.5: Run full test suite and fix any breakage**

```bash
cd backend && python3 -m pytest tests/test_models.py -v
```
Expected: all PASS (old TravelRequest tests that used top-level fields will need updating — change them to use `legs=` with a `_make_transit_leg()` helper)

- [ ] **Step 3.6: Commit**

```bash
git add backend/models/travel_request.py backend/tests/test_models.py
git commit -m "feat: TravelRequest auf Legs-Architektur umgestellt"
```

---

## Chunk 2: Backend Infrastructure

### Task 4: Update `_new_job()` and segment budget helpers in `main.py`

**Files:**
- Modify: `backend/main.py` (functions `_new_job`, `_calc_segment_budget` → `_calc_leg_segment_budget`)

- [ ] **Step 4.1: Replace `_calc_segment_budget` with `_calc_leg_segment_budget`**

In `backend/main.py`, find `_calc_segment_budget` (line ~137) and replace with:

```python
def _calc_leg_segment_budget(request: TravelRequest, leg_index: int) -> int:
    """Distributes leg days across N segments within the leg."""
    leg = request.legs[leg_index]
    n = max(1, len(leg.via_points) + 1)
    days = [leg.total_days // n] * n
    for i in range(leg.total_days % n):
        days[i] += 1
    min_days = (request.min_nights_per_stop + 1) * 2
    result = days[0]   # start at segment 0 within leg
    return max(min_days, result)
```

- [ ] **Step 4.2: Replace `_new_job` signature and body**

Find `_new_job` (line ~226) and replace with:

```python
def _new_job(job_id: str, request: TravelRequest) -> dict:
    from models.trip_leg import ExploreZoneAnalysis
    return {
        "status": "building_route",
        "request": request.model_dump(mode="json"),
        "selected_stops": [],
        "current_options": [],
        "route_could_be_complete": False,
        "stop_counter": 0,

        # Leg tracking
        "leg_index": 0,
        "current_leg_mode": request.legs[0].mode,

        # Transit leg state (reset on each leg transition)
        "segment_index": 0,
        "segment_budget": _calc_leg_segment_budget(request, 0),
        "segment_stops": [],

        # Explore leg state (reset on each explore leg transition)
        "explore_phase": None,
        # None | "awaiting_guidance" | "circuit_ready" | "selecting_stops"
        "explore_zone_analysis": None,    # ExploreZoneAnalysis dict after first pass
        "explore_circuit": [],            # list[ExploreStop dicts] after second pass
        "explore_circuit_position": 0,

        # Accommodation (unchanged)
        "selected_accommodations": [],
        "current_acc_options": [],
        "accommodation_index": 0,
        "prefetched_accommodations": {},
        "all_accommodation_options": {},
        "all_accommodations_loaded": False,

        # Route geometry cache — keys prefixed "leg{N}_" to scope per leg
        "route_geometry_cache": {},

        "result": None,
        "error": None,
    }
```

- [ ] **Step 4.3: Update all callers of `_new_job` and `_calc_segment_budget`**

Search for calls to the old functions:
```bash
cd backend && grep -n "_new_job\|_calc_segment_budget" main.py
```

For each call to `_new_job(request)` → change to `_new_job(job_id, request)`.
For each call to `_calc_segment_budget(request, ...)` → change to `_calc_leg_segment_budget(request, job["leg_index"])`.

Also remove `_detect_rundreise`, `_apply_rundreise_geometry` functions and their callers — these are replaced by the explicit leg mode system. Search:
```bash
grep -n "_detect_rundreise\|_apply_rundreise\|rundreise_mode\|set-rundreise" main.py
```

Remove the `/api/set-rundreise-mode/{job_id}` endpoint entirely.

- [ ] **Step 4.4: Update route geometry dict to use leg-scoped origin/target**

Search for all places in `main.py` that build or read the route geometry dict:
```bash
grep -n "origin_location\|start_location\|segment_target\|route_geometry" backend/main.py | head -40
```

For each place that passes `req.start_location` as origin or `req.main_destination` as target into the geometry dict, replace with the current leg's values:

**Before (example pattern):**
```python
geo = {
    ...
    "origin_location": req.start_location,
    "segment_target": req.main_destination,
    ...
}
```

**After:**
```python
leg = req.legs[job["leg_index"]]
geo = {
    ...
    "origin_location": leg.start_location,
    "segment_target": leg.end_location,
    ...
}
```

Also prefix `route_geometry_cache` keys with `leg{leg_index}_` to scope per leg:

**Before:**
```python
cache_key = f"{from_loc}|{to_loc}|{stops}"
```

**After:**
```python
cache_key = f"leg{job['leg_index']}_{from_loc}|{to_loc}|{stops}"
```

- [ ] **Step 4.4a: Verify server starts after changes**

```bash
cd backend && python3 -m uvicorn main:app --reload --port 8000
```
Expected: starts without errors. Ctrl+C.

- [ ] **Step 4.5: Verify server starts**

```bash
cd backend && python3 -m uvicorn main:app --reload --port 8000
```
Expected: starts without import errors. Ctrl+C to stop.

- [ ] **Step 4.6: Commit**

```bash
git add backend/main.py
git commit -m "refactor: _new_job und Segment-Budget auf Legs umgestellt, Rundreise entfernt"
```

---

### Task 5: Pause/resume in `run_planning_job.py`

**Files:**
- Modify: `backend/tasks/run_planning_job.py`

- [ ] **Step 5.1: Add explore_phase-aware resume logic**

Replace `_run_job` with:

```python
async def _run_job(job_id: str, pre_built_stops=None, pre_selected_accommodations=None):
    """Runs TravelPlannerOrchestrator.run() and saves result to Redis."""
    from orchestrator import TravelPlannerOrchestrator
    from models.travel_request import TravelRequest
    from utils.debug_logger import debug_logger, LogLevel

    redis_client = _get_store()
    raw = redis_client.get(f"job:{job_id}")
    if not raw:
        return
    job = json.loads(raw)

    # Skip if paused waiting for zone guidance answers
    if job.get("explore_phase") == "awaiting_guidance":
        return

    job["status"] = "running"
    redis_client.setex(f"job:{job_id}", 86400, json.dumps(job))

    request = TravelRequest(**job["request"])

    try:
        orchestrator = TravelPlannerOrchestrator(request, job_id)
        result = await orchestrator.run(
            pre_built_stops=pre_built_stops or job.get("selected_stops"),
            pre_selected_accommodations=pre_selected_accommodations or job.get("selected_accommodations"),
            pre_all_accommodation_options=job.get("all_accommodation_options", {}),
        )

        result["request"] = job["request"]

        raw2 = redis_client.get(f"job:{job_id}")
        job2 = json.loads(raw2) if raw2 else job
        job2["status"] = "complete"
        job2["result"] = result
        redis_client.setex(f"job:{job_id}", 86400, json.dumps(job2))

        try:
            from utils.travel_db import save_travel as _db_save
            await _db_save(result)
        except Exception as db_err:
            await debug_logger.log(
                LogLevel.WARNING, f"DB-Speicherung fehlgeschlagen: {db_err}",
                job_id=job_id, agent="RunPlanningJob",
            )

        await debug_logger.log(
            LogLevel.SUCCESS, "Planungsauftrag abgeschlossen",
            job_id=job_id, agent="RunPlanningJob",
        )

    except Exception as e:
        tb = traceback.format_exc()
        await debug_logger.log(
            LogLevel.ERROR, f"Planungsauftrag fehlgeschlagen: {type(e).__name__}: {e}\n{tb}",
            job_id=job_id, agent="RunPlanningJob",
        )
        raw3 = redis_client.get(f"job:{job_id}")
        job3 = json.loads(raw3) if raw3 else job
        job3["status"] = "error"
        job3["error"] = str(e)
        redis_client.setex(f"job:{job_id}", 86400, json.dumps(job3))
        await debug_logger.push_event(job_id, "job_error", None, {"error": str(e)})
```

- [ ] **Step 5.2: Verify no syntax errors**

```bash
cd backend && python3 -c "from tasks.run_planning_job import run_planning_job_task; print('OK')"
```
Expected: `OK`

- [ ] **Step 5.3: Commit**

```bash
git add backend/tasks/run_planning_job.py
git commit -m "feat: explore_phase Pause/Resume-Logik in run_planning_job"
```

---

### Task 6: `POST /api/answer-explore-questions/{job_id}` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_endpoints.py`

- [ ] **Step 6.1: Write failing endpoint test**

First add a `mock_job` fixture to `backend/tests/conftest.py`:

```python
import json, uuid

@pytest.fixture
def mock_job(mocker):
    """A minimal job dict stored in the mocked Redis, returns the job dict for mutation."""
    job_id = uuid.uuid4().hex
    leg = {
        "leg_id": "leg-0",
        "start_location": "Liestal",
        "end_location": "Paris",
        "start_date": "2026-06-01",
        "end_date": "2026-06-14",
        "mode": "transit",
        "via_points": [],
        "zone_bbox": None,
        "zone_guidance": [],
    }
    job = {
        "job_id": job_id,
        "status": "building_route",
        "request": {"legs": [leg], "adults": 2, "children": [],
                    "budget_accommodation_pct": 60, "budget_food_pct": 20,
                    "budget_activities_pct": 20},
        "selected_stops": [],
        "leg_index": 0,
        "explore_phase": None,
    }

    mock_redis = mocker.patch("main.redis_client")
    mock_redis.get.side_effect = lambda key: (
        json.dumps(job).encode() if key == f"job:{job_id}" else None
    )
    mock_redis.setex.side_effect = lambda key, ttl, val: job.update(json.loads(val))
    mock_redis.keys.return_value = []

    job["job_id"] = job_id  # expose for test access
    return job
```

Then add to `backend/tests/test_endpoints.py`:

```python
class TestAnswerExploreQuestions:
    def test_404_on_missing_job(self, client):
        resp = client.post(
            "/api/answer-explore-questions/" + "a" * 32,
            json={"answers": ["Ja"]}
        )
        assert resp.status_code == 404

    def test_409_if_not_awaiting_guidance(self, client, mock_job):
        """Job exists but explore_phase is not awaiting_guidance."""
        mock_job["explore_phase"] = None
        job_id = mock_job["job_id"]
        resp = client.post(
            f"/api/answer-explore-questions/{job_id}",
            json={"answers": ["Ja"]}
        )
        assert resp.status_code == 409

    def test_accepts_answers_and_re_enqueues(self, client, mock_job):
        mock_job["explore_phase"] = "awaiting_guidance"
        mock_job["leg_index"] = 0
        job_id = mock_job["job_id"]
        resp = client.post(
            f"/api/answer-explore-questions/{job_id}",
            json={"answers": ["Ja, Inseln"]}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
```

- [ ] **Step 6.2: Run to confirm FAIL**

```bash
cd backend && python3 -m pytest tests/test_endpoints.py::TestAnswerExploreQuestions -v
```
Expected: FAIL (endpoint doesn't exist)

- [ ] **Step 6.3: Add endpoint to `main.py`**

Find the endpoint registration block and add (before the static file mount at end of file):

```python
from models.trip_leg import ExploreAnswersRequest

@app.post("/api/answer-explore-questions/{job_id}")
async def answer_explore_questions(job_id: str, body: ExploreAnswersRequest):
    job = get_job(job_id)
    if job.get("explore_phase") != "awaiting_guidance":
        raise HTTPException(status_code=409,
            detail="Job wartet nicht auf Zonenführungs-Antworten")

    # Store answers into the leg's zone_guidance
    leg_index = job.get("leg_index", 0)
    req_data = job["request"]
    req_data["legs"][leg_index]["zone_guidance"] = body.answers

    # Advance explore_phase to trigger second-pass on resume
    job["explore_phase"] = "circuit_ready"
    job["status"] = "building_route"
    job["request"] = req_data
    save_job(job_id, job)

    # Re-enqueue planning job
    _fire_task("run_planning_job", job_id)

    return {"status": "ok"}
```

- [ ] **Step 6.4: Run endpoint tests**

```bash
cd backend && python3 -m pytest tests/test_endpoints.py::TestAnswerExploreQuestions -v
```
Expected: all PASS

- [ ] **Step 6.5: Commit**

```bash
git add backend/main.py backend/tests/test_endpoints.py
git commit -m "feat: POST /api/answer-explore-questions Endpunkt"
```

---

## Chunk 3: ExploreZoneAgent

### Task 7: Create `agents/explore_zone_agent.py`

**Files:**
- Create: `backend/agents/explore_zone_agent.py`
- Test: `backend/tests/test_agents_mock.py`

- [ ] **Step 7.1: Write failing agent tests**

Add to `backend/tests/test_agents_mock.py`:

```python
from unittest.mock import MagicMock, patch
from agents.explore_zone_agent import ExploreZoneAgent
from models.trip_leg import ZoneBBox, ExploreZoneAnalysis, ExploreStop
from models.travel_request import TravelRequest
from models.trip_leg import TripLeg
from datetime import date

def _make_req_with_explore_leg():
    bbox = ZoneBBox(north=42, south=36, east=28, west=20, zone_label="Griechenland")
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Athen", end_location="Athen",
        start_date=date(2026,6,15), end_date=date(2026,7,15),
        mode="explore", zone_bbox=bbox,
    )
    return TravelRequest(legs=[leg])

FIRST_PASS_JSON = """{
  "zone_characteristics": "Inselreich mit Fährverbindungen",
  "preliminary_anchors": ["Athen", "Meteora"],
  "guided_questions": ["Sollen Inseln eingeschlossen werden?"]
}"""

SECOND_PASS_JSON = """{
  "circuit": [
    {"name": "Athen", "lat": 37.97, "lon": 23.72, "suggested_nights": 3,
     "significance": "anchor", "logistics_note": ""},
    {"name": "Delphi", "lat": 38.48, "lon": 22.50, "suggested_nights": 1,
     "significance": "scenic", "logistics_note": ""}
  ],
  "warnings": ["Fährbuchung frühzeitig empfohlen"]
}"""

class TestExploreZoneAgent:
    def _mock_response(self, text):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        msg.model = "claude-opus-4-5"
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        return msg

    @patch("agents.explore_zone_agent.call_with_retry")
    async def test_first_pass_returns_zone_analysis(self, mock_retry):
        mock_retry.return_value = self._mock_response(FIRST_PASS_JSON)
        req = _make_req_with_explore_leg()
        agent = ExploreZoneAgent(req, "job123")
        result = await agent.run_first_pass(leg_index=0)
        assert isinstance(result, ExploreZoneAnalysis)
        assert "Inselreich" in result.zone_characteristics
        assert len(result.guided_questions) == 1

    @patch("agents.explore_zone_agent.call_with_retry")
    async def test_second_pass_returns_circuit(self, mock_retry):
        mock_retry.return_value = self._mock_response(SECOND_PASS_JSON)
        req = _make_req_with_explore_leg()
        agent = ExploreZoneAgent(req, "job123")
        first_pass = ExploreZoneAnalysis(
            zone_characteristics="Inselreich",
            guided_questions=["Inseln?"]
        )
        circuit, warnings = await agent.run_second_pass(
            leg_index=0, first_pass=first_pass, guidance=["Ja"]
        )
        assert len(circuit) == 2
        assert circuit[0].name == "Athen"
        assert circuit[0].significance == "anchor"
        assert warnings == ["Fährbuchung frühzeitig empfohlen"]
```

- [ ] **Step 7.2: Run to confirm FAIL**

```bash
cd backend && python3 -m pytest tests/test_agents_mock.py::TestExploreZoneAgent -v
```
Expected: FAIL (module doesn't exist)

- [ ] **Step 7.3: Create `backend/agents/explore_zone_agent.py`**

```python
import json
from models.travel_request import TravelRequest
from models.trip_leg import ExploreZoneAnalysis, ExploreStop
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Reiserouten-Experte. Analysiere eine Reisezone und plane einen effizienten Rundkurs. "
    "Berücksichtige lokale Logistik (Fähren, Bergpässe, Straßennetze) und geografische Effizienz "
    "(vermeide unnötige Rückwege). "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)

FIRST_PASS_SCHEMA = """{
  "zone_characteristics": "string — Terrain, Logistik, besondere Merkmale der Zone",
  "preliminary_anchors": ["Liste von Muss-Sehen-Orten, geografisch geordnet"],
  "guided_questions": ["2-3 zonenspezifische Fragen an den Reisenden"]
}"""

SECOND_PASS_SCHEMA = """{
  "circuit": [
    {
      "name": "Konkreter Ortsname (Stadt/Dorf, keine Region)",
      "lat": 0.0,
      "lon": 0.0,
      "suggested_nights": 1,
      "significance": "anchor | scenic | hidden_gem",
      "logistics_note": "optional — z.B. Fähre erforderlich"
    }
  ],
  "warnings": ["Logistische Hinweise für die gesamte Route"]
}"""


class ExploreZoneAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-opus-4-5")

    def _leg_context(self, leg_index: int) -> str:
        req = self.request
        leg = req.legs[leg_index]
        bbox = leg.zone_bbox
        styles = ", ".join(req.travel_styles) if req.travel_styles else "keine Angabe"
        return (
            f"Zone: {bbox.zone_label}\n"
            f"Begrenzungsrahmen: N={bbox.north:.2f} S={bbox.south:.2f} "
            f"E={bbox.east:.2f} W={bbox.west:.2f}\n"
            f"Verfügbare Tage in dieser Zone: {leg.total_days}\n"
            f"Reisestile: {styles}\n"
            f"Reisende: {req.adults} Erwachsene"
            + (f", Kinder: {len(req.children)}" if req.children else "")
        )

    async def run_first_pass(self, leg_index: int) -> ExploreZoneAnalysis:
        req = self.request
        leg = req.legs[leg_index]
        context = self._leg_context(leg_index)

        mandatory = ""
        if req.mandatory_activities:
            acts = ", ".join(a.name for a in req.mandatory_activities)
            mandatory = f"\nPflichtaktivitäten: {acts}"

        prompt = (
            f"{context}{mandatory}\n\n"
            f"Analysiere die Zone und erstelle:\n"
            f"1. Eine kurze Charakterisierung der Zone (Terrain, Logistik, Besonderheiten)\n"
            f"2. Eine vorläufige Liste der wichtigsten Sehenswürdigkeiten, geografisch geordnet\n"
            f"3. 2-3 spezifische Fragen an den Reisenden, die den Rundkurs wesentlich beeinflussen\n\n"
            f"Antwortformat:\n{FIRST_PASS_SCHEMA}"
        )

        await debug_logger.log(LogLevel.API, f"→ ExploreZoneAgent (1. Durchlauf) {leg.zone_bbox.zone_label}",
                               job_id=self.job_id, agent="ExploreZoneAgent")

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="ExploreZoneAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        return ExploreZoneAnalysis(**data)

    async def run_second_pass(
        self,
        leg_index: int,
        first_pass: ExploreZoneAnalysis,
        guidance: list[str],
    ) -> tuple[list[ExploreStop], list[str]]:
        req = self.request
        leg = req.legs[leg_index]
        context = self._leg_context(leg_index)

        guidance_str = "\n".join(f"- {q}: {a}" for q, a in
                                  zip(first_pass.guided_questions, guidance))

        prompt = (
            f"{context}\n\n"
            f"Zonenanalyse:\n{first_pass.zone_characteristics}\n\n"
            f"Vorläufige Ankerpunkte: {', '.join(first_pass.preliminary_anchors)}\n\n"
            f"Antworten des Reisenden:\n{guidance_str}\n\n"
            f"Erstelle jetzt einen vollständigen, logistisch optimierten Rundkurs für {leg.total_days} Tage.\n"
            f"Regeln:\n"
            f"- Konkrete Ortsnamen (Städte/Dörfer) — KEINE Regionen\n"
            f"- Geografisch effizienter Rundkurs (minimale Rückwege)\n"
            f"- Fähren und Logistik im Rundkurs berücksichtigen\n"
            f"- Nächte pro Stopp basierend auf Bedeutung und Aktivitätsdichte\n"
            f"- Max. Fahrzeit/Tag: {req.max_drive_hours_per_day}h\n\n"
            f"Antwortformat:\n{SECOND_PASS_SCHEMA}"
        )

        await debug_logger.log(LogLevel.API, f"→ ExploreZoneAgent (2. Durchlauf) {leg.zone_bbox.zone_label}",
                               job_id=self.job_id, agent="ExploreZoneAgent")

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="ExploreZoneAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        circuit = [ExploreStop(**s) for s in data.get("circuit", [])]
        warnings = data.get("warnings", [])
        return circuit, warnings
```

- [ ] **Step 7.4: Run agent tests**

```bash
cd backend && python3 -m pytest tests/test_agents_mock.py::TestExploreZoneAgent -v
```
Expected: all PASS

- [ ] **Step 7.5: Commit**

```bash
git add backend/agents/explore_zone_agent.py backend/tests/test_agents_mock.py
git commit -m "feat: ExploreZoneAgent mit zwei-Durchlauf-Logik"
```

---

## Chunk 4: Orchestrator & StopOptionsFinder

### Task 8: Update `orchestrator.py` for leg-sequential flow

**Files:**
- Modify: `backend/orchestrator.py`

- [ ] **Step 8.1: Add leg-aware routing to orchestrator**

Replace `orchestrator.py` with the leg-sequential version. The existing research and day-planning phases are unchanged — only the route phase changes.

Key changes:
1. `run()` iterates legs starting from `job["leg_index"]`
2. Transit legs call the existing `RouteArchitectAgent` flow (or `pre_built_stops` shortcut)
3. Explore legs call `ExploreZoneAgent` with pause/resume via Redis `explore_phase`
4. All stops accumulate in `all_stops`; research + day-planning run on the full combined list

```python
import asyncio
import json
import os
from models.travel_request import TravelRequest
from agents.route_architect import RouteArchitectAgent
from agents.explore_zone_agent import ExploreZoneAgent
from agents.activities_agent import ActivitiesAgent
from agents.restaurants_agent import RestaurantsAgent
from agents.day_planner import DayPlannerAgent
from agents.travel_guide_agent import TravelGuideAgent
from agents.trip_analysis_agent import TripAnalysisAgent
from models.trip_leg import ExploreZoneAnalysis, ExploreStop
from utils.debug_logger import debug_logger, LogLevel
from utils.image_fetcher import fetch_unsplash_images

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


class TravelPlannerOrchestrator:

    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id

    def _get_store(self):
        try:
            from main import redis_client
            return redis_client
        except Exception:
            import redis as redis_lib
            return redis_lib.from_url(REDIS_URL, decode_responses=True)

    def _load_job(self) -> dict:
        store = self._get_store()
        raw = store.get(f"job:{self.job_id}")
        return json.loads(raw) if raw else {}

    def _save_job(self, job: dict):
        store = self._get_store()
        store.setex(f"job:{self.job_id}", 86400, json.dumps(job))

    async def progress(self, event_type: str, agent_id, data: dict, percent: int = 0):
        await debug_logger.push_event(self.job_id, event_type, agent_id, data, percent)

    async def run(self, pre_built_stops=None, pre_selected_accommodations=None,
                  pre_all_accommodation_options=None) -> dict:
        req = self.request
        job_id = self.job_id

        await debug_logger.log(LogLevel.INFO, "Orchestrator startet", job_id=job_id)

        # Phase 1: Route (leg-sequential)
        if pre_built_stops and len(pre_built_stops) > 0:
            # Resume after all legs completed — go straight to research
            stops = pre_built_stops
            day = 1
            for stop in stops:
                if not stop.get("arrival_day"):
                    stop["arrival_day"] = day
                day += 1 + stop.get("nights", req.min_nights_per_stop)
        else:
            stops = await self._run_all_legs()
            if stops is None:
                # Paused waiting for zone guidance — job state saved, return sentinel
                return {}

        await self.progress("route_ready", "route_architect", {"stops": stops}, 10)

        # Phase 2–4: Research + Day Planning + Analysis (unchanged)
        return await self._run_research_and_planning(
            stops, pre_selected_accommodations, pre_all_accommodation_options
        )

    async def _run_all_legs(self) -> list | None:
        """Runs all legs sequentially. Returns None if paused mid-explore."""
        req = self.request
        job = self._load_job()
        all_stops = list(job.get("selected_stops", []))

        for leg_index in range(job.get("leg_index", 0), len(req.legs)):
            leg = req.legs[leg_index]
            if leg.mode == "transit":
                leg_stops = await self._run_transit_leg(leg, leg_index)
            else:
                leg_stops = await self._run_explore_leg(leg, leg_index)
                if leg_stops is None:
                    return None  # Paused for zone guidance

            all_stops.extend(leg_stops)

            # Advance leg_index in Redis
            job = self._load_job()
            job["leg_index"] = leg_index + 1
            job["current_leg_mode"] = req.legs[leg_index + 1].mode if leg_index + 1 < len(req.legs) else None
            # Reset per-leg state
            job["segment_index"] = 0
            job["segment_stops"] = []
            job["explore_phase"] = None
            job["explore_circuit"] = []
            job["explore_circuit_position"] = 0
            self._save_job(job)

            await debug_logger.push_event(
                self.job_id, "leg_complete", None,
                {"leg_id": leg.leg_id, "leg_index": leg_index, "mode": leg.mode}
            )

        return all_stops

    async def _run_transit_leg(self, leg, leg_index: int) -> list:
        """Transit leg: use RouteArchitectAgent (unchanged logic)."""
        req = self.request
        job = self._load_job()
        existing_stops = job.get("segment_stops", [])

        if existing_stops:
            return existing_stops   # Already built interactively

        await debug_logger.log(LogLevel.AGENT, f"RouteArchitect für Leg {leg_index}", job_id=self.job_id)
        route = await RouteArchitectAgent(req, self.job_id).run()
        return route.get("stops", [])

    async def _run_explore_leg(self, leg, leg_index: int) -> list | None:
        """Explore leg: ExploreZoneAgent two-pass, then interactive selection."""
        job = self._load_job()
        explore_phase = job.get("explore_phase")
        agent = ExploreZoneAgent(self.request, self.job_id)

        if explore_phase is None:
            # First pass: zone analysis + guided questions
            first_pass = await agent.run_first_pass(leg_index)
            job = self._load_job()
            job["explore_zone_analysis"] = first_pass.model_dump()
            job["explore_phase"] = "awaiting_guidance"
            job["status"] = "awaiting_zone_guidance"
            self._save_job(job)
            await debug_logger.push_event(
                self.job_id, "explore_zone_questions", None,
                {"questions": first_pass.guided_questions, "leg_id": leg.leg_id}
            )
            return None  # Pause

        if explore_phase == "circuit_ready":
            # Second pass: generate circuit from guidance answers
            job = self._load_job()
            first_pass = ExploreZoneAnalysis(**job["explore_zone_analysis"])
            guidance = leg.zone_guidance
            circuit, warnings = await agent.run_second_pass(leg_index, first_pass, guidance)
            job = self._load_job()
            job["explore_circuit"] = [s.model_dump() for s in circuit]
            job["explore_phase"] = "selecting_stops"
            self._save_job(job)
            await debug_logger.push_event(
                self.job_id, "explore_circuit_ready", None,
                {"circuit": [s.model_dump() for s in circuit],
                 "warnings": warnings, "leg_id": leg.leg_id}
            )

        # Interactive stop selection (same as transit — user selects from options)
        job = self._load_job()
        return job.get("selected_stops", [])

    async def _run_research_and_planning(self, stops, pre_selected_accommodations,
                                          pre_all_accommodation_options) -> dict:
        """Unchanged research + day planning phase."""
        req = self.request
        job_id = self.job_id

        if pre_selected_accommodations:
            all_accommodations = pre_selected_accommodations
        else:
            all_accommodations = []

        act_map: dict = {}
        rest_map: dict = {}
        loc_img_map: dict = {}
        all_research: list = []

        await debug_logger.log(LogLevel.INFO, f"Forschungsphase: {len(stops)} Stops", job_id=job_id)

        async def research_activities(stop):
            sid = stop.get("id")
            region = stop.get("region", "")
            await debug_logger.push_event(job_id, "stop_research_started", None,
                                           {"stop_id": sid, "region": region, "section": "activities"})
            result = await ActivitiesAgent(req, job_id).run_stop(stop)
            act_map[sid] = result
            await debug_logger.push_event(job_id, "activities_loaded", None,
                                           {"stop_id": sid, "region": region,
                                            "activities": result.get("top_activities", [])})

        async def research_restaurants(stop):
            sid = stop.get("id")
            region = stop.get("region", "")
            await debug_logger.push_event(job_id, "stop_research_started", None,
                                           {"stop_id": sid, "region": region, "section": "restaurants"})
            result = await RestaurantsAgent(req, job_id).run_stop(stop)
            rest_map[sid] = result
            await debug_logger.push_event(job_id, "restaurants_loaded", None,
                                           {"stop_id": sid, "region": region,
                                            "restaurants": result.get("restaurants", [])})

        async def research_location_images(stop):
            sid = stop.get("id")
            region = stop.get("region", "")
            country = stop.get("country", "")
            images = await fetch_unsplash_images(f"{region} {country}", "location travel")
            loc_img_map[sid] = images

        tasks = []
        for stop in stops:
            tasks.append(research_activities(stop))
            tasks.append(research_restaurants(stop))
            tasks.append(research_location_images(stop))
        await asyncio.gather(*tasks)

        for stop in stops:
            sid = stop.get("id")
            stop.update(loc_img_map.get(sid, {}))
            merged = {}
            merged.update(act_map.get(sid, {}))
            merged.update(rest_map.get(sid, {}))
            all_research.append(merged)
            acc = next((a["option"] for a in all_accommodations if a.get("stop_id") == sid), None)
            await debug_logger.push_event(job_id, "stop_done", None, {
                "stop_id": sid,
                "region": stop.get("region"),
                "accommodation": acc,
                "all_accommodation_options": (pre_all_accommodation_options or {}).get(str(sid), []),
                "top_activities": act_map.get(sid, {}).get("top_activities", [])[:3],
                "restaurants": rest_map.get(sid, {}).get("restaurants", [])[:3],
            })

        await debug_logger.log(LogLevel.INFO, f"Reiseführer-Recherche für {len(stops)} Stops", job_id=job_id)
        guide_map: dict = {}

        async def research_travel_guide(stop):
            sid = stop.get("id")
            existing_acts = [a["name"] for a in act_map.get(sid, {}).get("top_activities", [])]
            result = await TravelGuideAgent(req, job_id).run_stop(stop, existing_acts)
            guide_map[sid] = result

        await asyncio.gather(*[research_travel_guide(s) for s in stops])

        for stop in stops:
            sid = stop.get("id")
            guide_result = guide_map.get(sid, {})
            stop["travel_guide"] = guide_result.get("travel_guide")
            stop["further_activities"] = guide_result.get("further_activities", [])
            for act in stop["further_activities"]:
                images = await fetch_unsplash_images(
                    f"{act.get('name', '')} {stop.get('region', '')}", "activity")
                act.update(images)

        await debug_logger.log(LogLevel.INFO, "Tagesplaner startet", job_id=job_id)
        route_for_planner = {"stops": stops}
        plan = await DayPlannerAgent(req, job_id).run(
            route=route_for_planner,
            accommodations=all_accommodations,
            activities=all_research,
        )

        for stop_dict in plan.get("stops", []):
            sid = stop_dict.get("id")
            stop_dict["all_accommodation_options"] = (pre_all_accommodation_options or {}).get(str(sid), [])

        await debug_logger.log(LogLevel.SUCCESS, "Reiseplan fertig!", job_id=job_id)

        try:
            analysis_result = await TripAnalysisAgent(req, job_id).run(plan, req)
            plan["trip_analysis"] = analysis_result
        except Exception as exc:
            await debug_logger.log(LogLevel.WARNING,
                f"Reise-Analyse fehlgeschlagen: {exc}", job_id=job_id)
            plan["trip_analysis"] = None

        await self.progress("job_complete", None, plan, 100)
        return plan
```

- [ ] **Step 8.2: Verify import**

```bash
cd backend && python3 -c "from orchestrator import TravelPlannerOrchestrator; print('OK')"
```
Expected: `OK`

- [ ] **Step 8.3: Commit**

```bash
git add backend/orchestrator.py
git commit -m "feat: Orchestrator auf Leg-sequenzielle Planung umgestellt"
```

---

### Task 9: Add explore prompt branch to `StopOptionsFinder`

**Files:**
- Modify: `backend/agents/stop_options_finder.py`

- [ ] **Step 9.1: Add explore-mode system prompt and prompt branch**

In `stop_options_finder.py`, add after the existing `SYSTEM_PROMPT`:

```python
SYSTEM_PROMPT_EXPLORE = (
    "Du bist ein Entdeckungsreise-Planer. Schlage genau 3 Stopps vor: anker, landschaft, geheimtipp. "
    "KRITISCH — Regeln für das Feld 'region': "
    "Immer eine konkrete Ortschaft — NIEMALS Regionen, Gebirge oder Länder. "
    "KRITISCH — Fahrzeiten: Jede Option muss drive_hours ≤ dem angegebenen Maximum einhalten. "
    "Im Erkunden-Modus: Kein Zieldruck — der Reisende möchte die Zone entdecken. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)
```

Add a new method `_build_prompt_explore` in `StopOptionsFinderAgent`:

```python
def _build_prompt_explore(
    self,
    selected_stops: list,
    circuit_position: int,
    circuit_stops: list,
    zone_characteristics: str,
    days_remaining: int,
    route_geometry: dict,
) -> str:
    req = self.request
    geo = route_geometry or {}
    prev_stop = selected_stops[-1]["region"] if selected_stops else req.start_location

    stops_str = ""
    if selected_stops:
        parts = [
            f"Stop {s['id']}: {s['region']} ({s.get('nights',1)} Nächte)"
            for s in selected_stops
        ]
        stops_str = "Bisherige Stopps: " + ", ".join(parts) + "\n"

    circuit_hint = ""
    if circuit_stops:
        upcoming = circuit_stops[circuit_position:circuit_position + 3]
        circuit_hint = f"Geplante Rundkurs-Stopps in diesem Bereich: {', '.join(upcoming)}\n"

    has_children = bool(req.children)
    family_field = '"family_friendly": true,' if has_children else ""

    return f"""Aktuelle Position: {prev_stop}
Verbleibende Tage in der Zone: {days_remaining}
Zonenmerkmale: {zone_characteristics}
{stops_str}{circuit_hint}
Reisestile: {", ".join(req.travel_styles) if req.travel_styles else "keine Angabe"}
Max. Fahrzeit/Tag: {req.max_drive_hours_per_day}h

Schlage 3 Stopps vor:
- "anker": Muss-gesehen-haben in dieser Zone (hohe Bedeutung, ideal {req.min_nights_per_stop}-{req.max_nights_per_stop} Nächte)
- "landschaft": Malerische Alternative (Natur/Panorama)
- "geheimtipp": Unbekannter, besonderer Geheimtipp

Antworte als JSON:
{{
  "options": [
    {{
      "option_type": "anker",
      "region": "Konkreter Ortsname",
      "country": "Land",
      "lat": 0.0,
      "lon": 0.0,
      "drive_hours": 0.0,
      "nights": {req.min_nights_per_stop},
      {family_field}
      "highlights": ["highlight1"],
      "teaser": "Kurze Beschreibung"
    }}
  ]
}}"""
```

- [ ] **Step 9.2: Add `find_options_explore` method**

Add to `StopOptionsFinderAgent`:

```python
async def find_options_explore(
    self,
    selected_stops: list,
    circuit_position: int,
    circuit_stops: list,
    zone_characteristics: str,
    days_remaining: int,
    route_geometry: dict,
) -> list:
    prompt = self._build_prompt_explore(
        selected_stops, circuit_position, circuit_stops,
        zone_characteristics, days_remaining, route_geometry,
    )

    await debug_logger.log(LogLevel.API, "→ StopOptionsFinder (Erkunden-Modus)",
                            job_id=self.job_id, agent="StopOptionsFinder")

    def call():
        return self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT_EXPLORE,
            messages=[{"role": "user", "content": prompt}],
        )

    response = await call_with_retry(call, job_id=self.job_id, agent_name="StopOptionsFinder")
    text = response.content[0].text
    data = parse_agent_json(text)
    return data.get("options", [])
```

- [ ] **Step 9.3: Verify import**

```bash
cd backend && python3 -c "from agents.stop_options_finder import StopOptionsFinderAgent; print('OK')"
```
Expected: `OK`

- [ ] **Step 9.4: Commit**

```bash
git add backend/agents/stop_options_finder.py
git commit -m "feat: StopOptionsFinder Erkunden-Modus Branch (anker/landschaft/geheimtipp)"
```

---

## Chunk 5: Frontend

### Task 10: Legs builder UI — Step 3 (`form.js` + `index.html`)

**Files:**
- Modify: `frontend/js/form.js`
- Modify: `frontend/index.html`

**Scope:** Replace the via-points section of Step 3 with the legs builder. Activities section (Step 3 lower half) is unchanged.

- [ ] **Step 10.1: Add legs state to `state.js`**

In `frontend/js/state.js`, in the `S` object default state, replace the route fields:

```javascript
// Replace: start_location, main_destination, start_date, end_date, via_points
// With:
legs: [],  // array of {leg_id, start_location, end_location, start_date, end_date, mode, via_points, zone_bbox, zone_guidance}
```

Keep the global `start_location`, `main_destination`, `start_date`, `end_date` in Step 1 — they are used to auto-create the first and last leg. The `legs` array is built from them in Step 3.

- [ ] **Step 10.2: Update `buildPayload()` in `form.js`**

Replace the route fields in `buildPayload()`:

```javascript
function buildPayload() {
    return {
        legs: S.legs,
        // ... rest of fields unchanged
        adults: S.adults,
        children: S.children,
        travel_styles: S.travel_styles,
        // ... etc
    };
}
```

- [ ] **Step 10.3: Add legs builder HTML to `index.html` (Step 3)**

Replace the via-points `<div>` in Step 3 with:

```html
<!-- Legs builder -->
<div class="form-group" id="legs-section">
    <label class="form-label">Reiseschnitte</label>
    <p class="form-hint" id="legs-hint">Deine Reise wird als ein Schnitt geplant. Füge Schnitte hinzu um verschiedene Modi zu kombinieren.</p>
    <div id="legs-container"></div>
    <button type="button" class="btn btn-outline" id="add-leg-btn" onclick="addLeg()">
        + Schnitt hinzufügen
    </button>
</div>
```

- [ ] **Step 10.4: Implement legs builder in `form.js`**

Add these functions to `form.js`:

```javascript
function initLegs() {
    // Auto-create first leg from Step 1 data
    if (S.legs.length === 0) {
        S.legs = [{
            leg_id: "leg-0",
            start_location: S.start_location,
            end_location: S.main_destination,
            start_date: S.start_date,
            end_date: S.end_date,
            mode: "transit",
            via_points: [],
            zone_bbox: null,
            zone_guidance: [],
        }];
    }
    renderLegs();
}

function renderLegs() {
    const container = document.getElementById("legs-container");
    container.innerHTML = S.legs.map((leg, i) => renderLegCard(leg, i)).join("");
}

function renderLegCard(leg, index) {
    const isFirst = index === 0;
    const isLast = index === S.legs.length - 1;
    const modeColor = leg.mode === "explore" ? "#e0b840" : "#4a90d9";
    const days = dateDiffDays(leg.start_date, leg.end_date);

    const transitContent = leg.mode === "transit" ? `
        <div class="leg-via-points">
            <label class="form-label-sm">Via-Punkte (optional)</label>
            <div class="tag-input" id="via-tags-${index}">
                ${(leg.via_points || []).map(vp => `
                    <span class="tag">${esc(vp.location)}
                        <button onclick="removeViaPoint(${index}, '${esc(vp.location)}')" aria-label="Entfernen">×</button>
                    </span>`).join("")}
                <input type="text" placeholder="Via-Punkt hinzufügen…"
                    onkeydown="handleViaInput(event, ${index})"
                    class="tag-input-field">
            </div>
        </div>` : "";

    const exploreContent = leg.mode === "explore" ? `
        <div class="leg-zone">
            <label class="form-label-sm">Erkundungszone</label>
            <div id="zone-map-${index}" class="zone-map-container" style="height:180px;border-radius:8px;overflow:hidden;border:1px solid #ddd;margin-bottom:8px"></div>
            <div class="zone-label-row">
                <span class="form-label-sm">Zone:</span>
                <input type="text" class="input-sm" id="zone-label-${index}"
                    value="${esc(leg.zone_bbox?.zone_label || '')}"
                    oninput="updateZoneLabel(${index}, this.value)"
                    placeholder="Zone benennen…">
            </div>
        </div>` : "";

    return `
    <div class="leg-card" id="leg-card-${index}" style="border-color:${modeColor}">
        <div class="leg-card-header" style="background:${leg.mode === 'explore' ? '#fdf8e8' : '#f5f5f5'}">
            <div class="leg-badge" style="background:${modeColor}">${index + 1}</div>
            <div class="leg-info">
                <div class="leg-route">${esc(leg.start_location)} → ${esc(leg.end_location)}</div>
                <div class="leg-dates">${formatDate(leg.start_date)} – ${formatDate(leg.end_date)} · ${days} Tage</div>
            </div>
            <div class="leg-controls">
                <div class="mode-toggle">
                    <button class="mode-btn ${leg.mode === 'transit' ? 'active' : ''}"
                        onclick="setLegMode(${index}, 'transit')" style="border-color:${modeColor}">Transit</button>
                    <button class="mode-btn ${leg.mode === 'explore' ? 'active' : ''}"
                        onclick="setLegMode(${index}, 'explore')" style="border-color:${modeColor}">Erkunden</button>
                </div>
                ${!isFirst && !isLast ? `<button class="leg-delete-btn" onclick="removeLeg(${index})" aria-label="Schnitt entfernen">×</button>` : ""}
            </div>
        </div>
        <div class="leg-card-body">
            ${transitContent}
            ${exploreContent}
        </div>
    </div>`;
}

function addLeg() {
    const lastLeg = S.legs[S.legs.length - 1];
    const midpoint = prompt("Trennpunkt eingeben (Stadt/Ort):");
    if (!midpoint || !midpoint.trim()) return;

    const boundary = midpoint.trim();
    const totalDays = dateDiffDays(S.start_date, S.end_date);
    const daysPerLeg = Math.floor(totalDays / (S.legs.length + 1));

    // Adjust existing last leg end date
    const newBoundaryDate = addDays(lastLeg.start_date, daysPerLeg);
    lastLeg.end_date = newBoundaryDate;
    lastLeg.end_location = boundary;

    // Insert new leg
    const newLeg = {
        leg_id: `leg-${S.legs.length}`,
        start_location: boundary,
        end_location: S.main_destination,
        start_date: newBoundaryDate,
        end_date: S.end_date,
        mode: "transit",
        via_points: [],
        zone_bbox: null,
        zone_guidance: [],
    };
    S.legs.push(newLeg);
    S.legs[S.legs.length - 1].leg_id = `leg-${S.legs.length - 1}`;
    renderLegs();

    // Init explore map if needed
    S.legs.forEach((leg, i) => {
        if (leg.mode === "explore") initZoneMap(i);
    });
}

function removeLeg(index) {
    if (index === 0 || index === S.legs.length - 1) return;
    const removed = S.legs.splice(index, 1)[0];
    // Reconnect adjacent legs
    S.legs[index - 1].end_location = S.legs[index].start_location;
    S.legs[index - 1].end_date = S.legs[index].start_date;
    // Re-number leg_ids
    S.legs.forEach((leg, i) => { leg.leg_id = `leg-${i}`; });
    renderLegs();
}

function setLegMode(index, mode) {
    S.legs[index].mode = mode;
    if (mode === "explore" && !S.legs[index].zone_bbox) {
        S.legs[index].zone_bbox = null;
    }
    renderLegs();
    if (mode === "explore") {
        setTimeout(() => initZoneMap(index), 50);
    }
}

function handleViaInput(event, legIndex) {
    if (event.key === "Enter" || event.key === ",") {
        event.preventDefault();
        const val = event.target.value.trim().replace(/,$/, "");
        if (val) {
            S.legs[legIndex].via_points.push({ location: val, fixed_date: null, notes: null });
            event.target.value = "";
            renderLegs();
        }
    }
}

function removeViaPoint(legIndex, location) {
    S.legs[legIndex].via_points = S.legs[legIndex].via_points.filter(vp => vp.location !== location);
    renderLegs();
}

function updateZoneLabel(legIndex, label) {
    if (S.legs[legIndex].zone_bbox) {
        S.legs[legIndex].zone_bbox.zone_label = label;
    } else {
        S.legs[legIndex].zone_bbox = { north: 0, south: 0, east: 0, west: 0, zone_label: label };
    }
}

function initZoneMap(legIndex) {
    const containerId = `zone-map-${legIndex}`;
    const container = document.getElementById(containerId);
    if (!container || container._leaflet_id) return;  // already initialized

    const leg = S.legs[legIndex];
    const map = L.map(containerId).setView([48.0, 10.0], 4);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap"
    }).addTo(map);

    let rect = null;

    // Restore existing bbox if present
    if (leg.zone_bbox && leg.zone_bbox.north) {
        const bounds = [[leg.zone_bbox.south, leg.zone_bbox.west],
                        [leg.zone_bbox.north, leg.zone_bbox.east]];
        rect = L.rectangle(bounds, { color: "#e0b840", weight: 2, fillOpacity: 0.15 }).addTo(map);
        map.fitBounds(bounds);
    }

    // Draw bbox on drag
    const drawControl = new L.Draw.Rectangle(map, { shapeOptions: { color: "#e0b840" } });
    map.on(L.Draw.Event.CREATED, async (e) => {
        if (rect) rect.remove();
        rect = e.layer.addTo(map);
        const b = e.layer.getBounds();
        const bbox = {
            north: b.getNorth(), south: b.getSouth(),
            east: b.getEast(), west: b.getWest(),
            zone_label: S.legs[legIndex].zone_bbox?.zone_label || ""
        };
        S.legs[legIndex].zone_bbox = bbox;
        // Auto-geocode zone label
        const center = b.getCenter();
        const label = await geocodeZoneLabel(center.lat, center.lng);
        if (label) {
            S.legs[legIndex].zone_bbox.zone_label = label;
            const labelInput = document.getElementById(`zone-label-${legIndex}`);
            if (labelInput) labelInput.value = label;
        }
    });
    drawControl.enable();
}

async function geocodeZoneLabel(lat, lon) {
    try {
        const resp = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`,
            { headers: { "Accept-Language": "de" } }
        );
        const data = await resp.json();
        return data.address?.country || data.address?.state || null;
    } catch {
        return null;
    }
}
```

- [ ] **Step 10.5: Call `initLegs()` when entering Step 3**

In `form.js`, find the step-navigation logic (where step is set to 3) and add:

```javascript
if (step === 3) {
    initLegs();
}
```

- [ ] **Step 10.6: Add Leaflet.draw dependency to `index.html`**

In `<head>` of `index.html`, add after the Leaflet CSS:

```html
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.css"/>
```

Before `</body>`:
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.js"></script>
```

- [ ] **Step 10.7: Add CSS for leg cards to `styles.css`**

Add at end of `frontend/styles.css`:

```css
.leg-card {
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    margin-bottom: 12px;
    overflow: hidden;
}

.leg-card-header {
    padding: 14px 18px;
    display: flex;
    align-items: center;
    gap: 12px;
}

.leg-badge {
    color: white;
    border-radius: 50%;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: bold;
    flex-shrink: 0;
}

.leg-info {
    flex: 1;
}

.leg-route { font-weight: 600; font-size: 14px; }
.leg-dates { font-size: 12px; color: #666; }

.leg-controls {
    display: flex;
    align-items: center;
    gap: 8px;
}

.mode-toggle {
    display: flex;
    border-radius: 20px;
    overflow: hidden;
    font-size: 12px;
}

.mode-btn {
    border: 1.5px solid #4a90d9;
    background: white;
    color: #4a90d9;
    padding: 4px 12px;
    cursor: pointer;
    font-size: 12px;
}

.mode-btn.active {
    background: #4a90d9;
    color: white;
}

.leg-delete-btn {
    background: none;
    border: none;
    color: #aaa;
    font-size: 18px;
    cursor: pointer;
    padding: 0 4px;
}

.leg-card-body {
    padding: 14px 18px;
    border-top: 1px solid #eee;
}

.zone-map-container { width: 100%; }

.zone-label-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
}

.input-sm {
    border: 1px solid #ddd;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 13px;
    width: 180px;
}

.form-label-sm {
    font-size: 12px;
    font-weight: 600;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
    display: block;
}
```

- [ ] **Step 10.8: Manually test in browser**

```bash
cd backend && python3 -m uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000`, fill Step 1 (start, destination, dates), navigate to Step 3. Verify:
- Single leg card shown (transit mode)
- "Schnitt hinzufügen" button adds a second leg with boundary city prompt
- Mode toggle switches between Transit (blue) and Erkunden (yellow)
- In Erkunden mode: map appears, bbox draw tool works, zone label auto-fills from Nominatim
- Via-points tag input works in Transit mode

- [ ] **Step 10.9: Commit**

```bash
git add frontend/js/form.js frontend/js/state.js frontend/index.html frontend/styles.css
git commit -m "feat: Legs-Builder UI in Schritt 3 (Transit/Erkunden mit Kartenzone)"
```

---

### Task 11: Route builder — explore circuit display and guided questions UI

**Files:**
- Modify: `frontend/js/route-builder.js`
- Modify: `frontend/js/api.js`

- [ ] **Step 11.1: Add `answerExploreQuestions` to `api.js`**

In `frontend/js/api.js`, add:

```javascript
async function answerExploreQuestions(jobId, answers) {
    return await apiFetch(`/api/answer-explore-questions/${jobId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers }),
    });
}
```

- [ ] **Step 11.2: Handle `explore_zone_questions` SSE event in `route-builder.js`**

In `route-builder.js`, in the SSE event handler (where `route_option_ready`, `stop_done` etc. are handled), add:

```javascript
case "explore_zone_questions": {
    const { questions, leg_id } = data;
    showExploreGuidanceForm(questions, leg_id);
    break;
}

case "explore_circuit_ready": {
    const { circuit, warnings, leg_id } = data;
    showExploreCircuit(circuit, warnings);
    break;
}

case "leg_complete": {
    const { leg_id, leg_index, mode } = data;
    await debugLogger.log(`Schnitt ${leg_index + 1} abgeschlossen (${mode})`);
    break;
}
```

- [ ] **Step 11.3: Add `showExploreGuidanceForm` function**

```javascript
function showExploreGuidanceForm(questions, legId) {
    const container = document.getElementById("route-builder-panel") ||
                      document.getElementById("progress-panel");
    if (!container) return;

    const answers = new Array(questions.length).fill("");

    const formHtml = `
        <div class="explore-guidance-form" id="explore-guidance-form">
            <h3 class="guidance-title">Fragen zur Erkundungszone</h3>
            <p class="guidance-subtitle">Beantworte diese Fragen um den Rundkurs zu optimieren</p>
            ${questions.map((q, i) => `
                <div class="guidance-question">
                    <label class="guidance-label">${esc(q)}</label>
                    <input type="text" class="guidance-input" id="guidance-answer-${i}"
                        placeholder="Deine Antwort…"
                        oninput="updateGuidanceAnswer(${i}, this.value)">
                </div>
            `).join("")}
            <button class="btn btn-primary" onclick="submitGuidanceAnswers('${esc(legId)}', ${JSON.stringify(questions).replace(/'/g, "\\'")})">
                Rundkurs planen
            </button>
        </div>`;

    container.insertAdjacentHTML("beforeend", formHtml);
    window._guidanceAnswers = answers;
}

function updateGuidanceAnswer(index, value) {
    if (window._guidanceAnswers) window._guidanceAnswers[index] = value;
}

async function submitGuidanceAnswers(legId, questions) {
    const answers = window._guidanceAnswers || [];
    const form = document.getElementById("explore-guidance-form");
    if (form) form.remove();

    try {
        await answerExploreQuestions(S.job_id, answers);
    } catch (err) {
        console.error("Fehler beim Senden der Antworten:", err);
    }
}
```

- [ ] **Step 11.4: Add `showExploreCircuit` function**

```javascript
function showExploreCircuit(circuit, warnings) {
    const container = document.getElementById("route-builder-panel") ||
                      document.getElementById("progress-panel");
    if (!container) return;

    const warningHtml = warnings.length ? `
        <div class="circuit-warnings">
            ${warnings.map(w => `<div class="circuit-warning">⚠ ${esc(w)}</div>`).join("")}
        </div>` : "";

    const circuitHtml = `
        <div class="explore-circuit" id="explore-circuit">
            <h3 class="circuit-title">Dein Rundkurs</h3>
            ${warningHtml}
            <ol class="circuit-stops">
                ${circuit.map(stop => `
                    <li class="circuit-stop">
                        <span class="circuit-stop-name">${esc(stop.name)}</span>
                        <span class="circuit-stop-nights">${stop.suggested_nights} Nächte</span>
                        ${stop.logistics_note ? `<span class="circuit-logistics">${esc(stop.logistics_note)}</span>` : ""}
                    </li>`).join("")}
            </ol>
            <p class="circuit-hint">Stopps werden nun interaktiv ausgewählt.</p>
        </div>`;

    container.insertAdjacentHTML("beforeend", circuitHtml);
}
```

- [ ] **Step 11.5: Remove Rundreise UI**

In `route-builder.js`, search for:
```bash
grep -n "rundreise\|Rundreise\|set-rundreise" frontend/js/route-builder.js
```

Remove:
- The Rundreise suggestion banner render code
- Any call to `setRundreiseMode` or the old `set-rundreise-mode` endpoint
- The Rundreise detection handler in the SSE event loop

- [ ] **Step 11.6: Add CSS for explore UI to `styles.css`**

```css
.explore-guidance-form, .explore-circuit {
    background: #fdf8e8;
    border: 1.5px solid #e0b840;
    border-radius: 10px;
    padding: 18px;
    margin-bottom: 16px;
}

.guidance-title, .circuit-title {
    font-size: 16px;
    font-weight: 700;
    margin: 0 0 4px;
}

.guidance-subtitle, .circuit-hint {
    font-size: 13px;
    color: #888;
    margin: 0 0 14px;
}

.guidance-question { margin-bottom: 12px; }
.guidance-label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.guidance-input { width: 100%; border: 1px solid #ddd; border-radius: 6px; padding: 6px 10px; font-size: 13px; }

.circuit-stops { list-style: none; padding: 0; margin: 8px 0; }
.circuit-stop { display: flex; align-items: baseline; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f0e090; }
.circuit-stop-name { font-weight: 600; font-size: 14px; flex: 1; }
.circuit-stop-nights { font-size: 12px; color: #888; }
.circuit-logistics { font-size: 11px; color: #b07020; }

.circuit-warnings { margin-bottom: 10px; }
.circuit-warning { background: #fff8e1; border-left: 3px solid #e0b840; padding: 6px 10px; font-size: 12px; margin-bottom: 4px; border-radius: 0 4px 4px 0; }
```

- [ ] **Step 11.7: Commit**

```bash
git add frontend/js/route-builder.js frontend/js/api.js frontend/styles.css
git commit -m "feat: Erkunden-UI in Route-Builder (Zonenführung, Rundkurs-Anzeige)"
```

---

## Chunk 6: Tests & Cleanup

### Task 12: Fix broken existing tests

**Files:**
- Modify: `backend/tests/test_models.py`
- Modify: `backend/tests/test_endpoints.py`
- Modify: `backend/tests/test_agents_mock.py`

- [ ] **Step 12.1: Run full test suite to see what's broken**

```bash
cd backend && python3 -m pytest tests/ -v 2>&1 | head -80
```

- [ ] **Step 12.2: Fix `test_models.py`**

Any test that creates `TravelRequest(start_location=..., main_destination=..., ...)` directly must be updated to use `legs=`:

```python
from datetime import date
from models.trip_leg import TripLeg

def _make_single_transit_req(**kwargs):
    leg = TripLeg(
        leg_id="leg-0",
        start_location=kwargs.pop("start_location", "Liestal"),
        end_location=kwargs.pop("main_destination", "Paris"),
        start_date=kwargs.pop("start_date", date(2026, 6, 1)),
        end_date=kwargs.pop("end_date", date(2026, 6, 14)),
        mode="transit",
    )
    return TravelRequest(legs=[leg], **kwargs)
```

Replace all occurrences of `TravelRequest(start_location=...` in tests with `_make_single_transit_req(...)`.

- [ ] **Step 12.3: Fix `test_endpoints.py`**

All test request bodies that use the old flat format need the `legs` array. Use the same `_make_single_transit_req` helper or build the legs dict directly:

```python
def transit_legs_payload(start="Liestal", end="Paris",
                          start_date="2026-06-01", end_date="2026-06-14"):
    return [{
        "leg_id": "leg-0",
        "start_location": start,
        "end_location": end,
        "start_date": start_date,
        "end_date": end_date,
        "mode": "transit",
        "via_points": [],
        "zone_bbox": None,
        "zone_guidance": [],
    }]
```

- [ ] **Step 12.4: Run full test suite**

```bash
cd backend && python3 -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 12.5: Commit**

```bash
git add backend/tests/
git commit -m "test: Alle Tests auf Legs-Architektur aktualisiert"
```

---

### Task 13: Tag and push final version

- [ ] **Step 13.1: Run complete test suite one final time**

```bash
cd backend && python3 -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 13.2: Start server and do a smoke test**

```bash
cd backend && python3 -m uvicorn main:app --reload --port 8000
```

In a second terminal:
```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```
Expected: 200 response

- [ ] **Step 13.3: Final commit and tag**

```bash
git add -A
git status  # verify nothing unexpected
git commit -m "feat: Trip-Legs und Erkunden-Modus vollständig implementiert" --allow-empty
git tag v6.1.0
git push && git push --tags
```

---

## Helper Functions Referenced

### `dateDiffDays(start, end)` (add to `form.js`)

```javascript
function dateDiffDays(start, end) {
    const s = new Date(start), e = new Date(end);
    return Math.round((e - s) / (1000 * 60 * 60 * 24));
}
```

### `addDays(dateStr, n)` (add to `form.js`)

```javascript
function addDays(dateStr, n) {
    const d = new Date(dateStr);
    d.setDate(d.getDate() + n);
    return d.toISOString().split("T")[0];
}
```

### `formatDate(dateStr)` (add to `form.js` if not present)

```javascript
function formatDate(dateStr) {
    if (!dateStr) return "";
    return new Date(dateStr).toLocaleDateString("de-CH", { day: "numeric", month: "short" });
}
```
