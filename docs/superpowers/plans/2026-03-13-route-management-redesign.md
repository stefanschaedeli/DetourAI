# Route Management Redesign — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign route management: remove detours from transit mode (add user guidance fallback), replace explore mode map-drawing with text-based region planning + interactive UI, fix StopOptionsFinder to always return locations not regions.

**Architecture:** Three parallel workstreams: (1) Backend models + new RegionPlannerAgent, (2) Backend endpoint changes in main.py + orchestrator.py, (3) Frontend form + route-builder UI changes. Tests accompany each workstream.

**Tech Stack:** Python/FastAPI, Pydantic models, Anthropic Claude API, Vanilla JS, Google Maps, HTML5 drag-and-drop, Server-Sent Events

**Spec:** `docs/superpowers/specs/2026-03-13-route-management-redesign.md`

---

## Chunk 1: Models + RegionPlannerAgent

### Task 1: Update Pydantic Models

**Files:**
- Modify: `backend/models/trip_leg.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Add new models to trip_leg.py**

Add `RegionPlanItem`, `RegionPlan`, `ReplaceRegionRequest`, `RecomputeRegionsRequest` after the existing `ExploreStop` class (line 28), and add `explore_description` to `TripLeg`:

```python
# Add after ExploreStop (line 28):

class RegionPlanItem(BaseModel):
    name: str = Field(max_length=200)
    lat: float
    lon: float
    reason: str = Field(max_length=500)


class RegionPlan(BaseModel):
    regions: list[RegionPlanItem] = Field(min_length=1)
    summary: str = Field(max_length=1000)


class ReplaceRegionRequest(BaseModel):
    index: int = Field(ge=0)
    instruction: str = Field(max_length=1000)


class RecomputeRegionsRequest(BaseModel):
    instruction: str = Field(max_length=1000)
```

In the `TripLeg` class (line 41), add after `zone_guidance`:

```python
    explore_description: Optional[str] = None
```

- [ ] **Step 2: Keep old explore models as dead code (deferred to Chunk 2)**

Do NOT delete `ExploreZoneAnalysis` or `ExploreAnswersRequest` yet — they are still imported by `main.py`, `orchestrator.py`, and `explore_zone_agent.py`. They will be removed in Task 5 when those consumers are updated.

- [ ] **Step 3: Write tests for new models**

Add new test classes AFTER the existing `TestExploreAnswersRequest` class (line 590 of `test_models.py`). Keep the old tests for now — they still pass since the models still exist. Add at the import block near line 531, add the new model imports:

```python
# At line 531, change:
from models.trip_leg import ZoneBBox, ExploreStop, ExploreZoneAnalysis, ExploreAnswersRequest, TripLeg
# To:
from models.trip_leg import (ZoneBBox, ExploreStop, ExploreZoneAnalysis, ExploreAnswersRequest,
                              RegionPlanItem, RegionPlan, ReplaceRegionRequest, RecomputeRegionsRequest, TripLeg)
```

Add these test classes after `TestExploreAnswersRequest`:

```python
class TestRegionPlanItem:
    def test_valid(self):
        item = RegionPlanItem(name="Tessin", lat=46.2, lon=8.95, reason="Seen")
        assert item.name == "Tessin"

    def test_name_too_long(self):
        with pytest.raises(ValueError):
            RegionPlanItem(name="x" * 201, lat=46.2, lon=8.95, reason="ok")


class TestRegionPlan:
    def test_valid(self):
        plan = RegionPlan(
            regions=[RegionPlanItem(name="Tessin", lat=46.2, lon=8.95, reason="Seen")],
            summary="Kurztrip"
        )
        assert len(plan.regions) == 1

    def test_empty_regions_rejected(self):
        with pytest.raises(ValueError):
            RegionPlan(regions=[], summary="Leer")

    def test_summary_too_long(self):
        with pytest.raises(ValueError):
            RegionPlan(
                regions=[RegionPlanItem(name="X", lat=0, lon=0, reason="ok")],
                summary="x" * 1001
            )


class TestReplaceRegionRequest:
    def test_valid(self):
        r = ReplaceRegionRequest(index=0, instruction="Ersetze durch Wallis")
        assert r.index == 0

    def test_negative_index_rejected(self):
        with pytest.raises(ValueError):
            ReplaceRegionRequest(index=-1, instruction="test")


class TestRecomputeRegionsRequest:
    def test_valid(self):
        r = RecomputeRegionsRequest(instruction="Mehr Küste")
        assert r.instruction == "Mehr Küste"

    def test_empty_instruction_allowed(self):
        # Empty string is allowed — no min_length constraint
        r = RecomputeRegionsRequest(instruction="")
        assert r.instruction == ""
```

Update imports at top of `test_models.py` to include `RegionPlanItem, RegionPlan, ReplaceRegionRequest, RecomputeRegionsRequest` and remove `ExploreZoneAnalysis, ExploreAnswersRequest`.

- [ ] **Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_models.py -v`
Expected: All tests pass including new model tests.

- [ ] **Step 5: Commit**

```bash
git add backend/models/trip_leg.py backend/tests/test_models.py
git commit -m "feat: RegionPlan Pydantic-Modelle und explore_description auf TripLeg

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Create RegionPlannerAgent

**Files:**
- Create: `backend/agents/region_planner.py`
- Test: `backend/tests/test_agents_mock.py`

- [ ] **Step 1: Write failing test for RegionPlannerAgent**

In `test_agents_mock.py`, replace the ENTIRE explore section (lines 451-535) — this includes the comment header, imports (`ExploreZoneAgent`, `ExploreZoneAnalysis`), the `_make_req_with_explore_leg()` fixture, JSON fixtures, and the `TestExploreZoneAgent` class. Replace with:

```python
# RegionPlannerAgent — region-based route planning
# ---------------------------------------------------------------------------

from agents.region_planner import RegionPlannerAgent
from models.trip_leg import RegionPlan, RegionPlanItem

def _make_req_with_explore_leg():
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Zürich", end_location="Zürich",
        start_date=date(2026, 6, 15), end_date=date(2026, 7, 1),
        mode="explore",
        explore_description="Schweizer Alpen erkunden, Bergdörfer und Seen",
    )
    return TravelRequest(legs=[leg])

PLAN_JSON = """{
  "regions": [
    {"name": "Tessin", "lat": 46.2, "lon": 8.95, "reason": "Mediterranes Flair"},
    {"name": "Graubünden", "lat": 46.8, "lon": 9.8, "reason": "Alpenlandschaft"}
  ],
  "summary": "Rundreise durch die Schweizer Alpen"
}"""

REPLACE_JSON = """{
  "regions": [
    {"name": "Wallis", "lat": 46.3, "lon": 7.6, "reason": "Matterhorn-Region"},
    {"name": "Graubünden", "lat": 46.8, "lon": 9.8, "reason": "Alpenlandschaft"}
  ],
  "summary": "Angepasste Rundreise mit Wallis statt Tessin"
}"""


class TestRegionPlannerAgent:
    def _mock_response(self, text):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        msg.model = "claude-opus-4-5"
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        return msg

    @patch("agents.region_planner.get_client")
    @patch("agents.region_planner.call_with_retry")
    def test_plan_returns_region_plan(self, mock_retry, mock_get_client):
        import asyncio
        mock_get_client.return_value = MagicMock()
        mock_retry.return_value = self._mock_response(PLAN_JSON)
        req = _make_req_with_explore_leg()
        agent = RegionPlannerAgent(req, "job123")

        result = asyncio.run(agent.plan(
            description="Schweizer Alpen",
            leg_index=0,
        ))
        assert isinstance(result, RegionPlan)
        assert len(result.regions) == 2
        assert result.regions[0].name == "Tessin"
        assert "Rundreise" in result.summary

    @patch("agents.region_planner.get_client")
    @patch("agents.region_planner.call_with_retry")
    def test_replace_region(self, mock_retry, mock_get_client):
        import asyncio
        mock_get_client.return_value = MagicMock()
        mock_retry.return_value = self._mock_response(REPLACE_JSON)
        req = _make_req_with_explore_leg()
        agent = RegionPlannerAgent(req, "job123")

        current_plan = RegionPlan(
            regions=[
                RegionPlanItem(name="Tessin", lat=46.2, lon=8.95, reason="Mediterranes Flair"),
                RegionPlanItem(name="Graubünden", lat=46.8, lon=9.8, reason="Alpenlandschaft"),
            ],
            summary="Original"
        )
        result = asyncio.run(agent.replace_region(
            index=0,
            instruction="Ersetze durch Wallis",
            current_plan=current_plan,
            leg_index=0,
        ))
        assert isinstance(result, RegionPlan)
        assert result.regions[0].name == "Wallis"

    @patch("agents.region_planner.get_client")
    @patch("agents.region_planner.call_with_retry")
    def test_recalculate(self, mock_retry, mock_get_client):
        import asyncio
        mock_get_client.return_value = MagicMock()
        mock_retry.return_value = self._mock_response(PLAN_JSON)
        req = _make_req_with_explore_leg()
        agent = RegionPlannerAgent(req, "job123")

        current_plan = RegionPlan(
            regions=[RegionPlanItem(name="X", lat=0, lon=0, reason="alt")],
            summary="Alt"
        )
        result = asyncio.run(agent.recalculate(
            instruction="Mehr Küste",
            current_plan=current_plan,
            leg_index=0,
        ))
        assert isinstance(result, RegionPlan)
        assert len(result.regions) == 2
```

This replacement covers the entire block including:
- Line 452: section comment
- Line 456: `from agents.explore_zone_agent import ExploreZoneAgent`
- Line 457: `from models.trip_leg import ZoneBBox, ExploreZoneAnalysis, ExploreStop`
- Lines 458-460: old imports
- Lines 462-487: old `_make_req_with_explore_leg`, `FIRST_PASS_JSON`, `SECOND_PASS_JSON` fixtures
- Lines 488-535: old `TestExploreZoneAgent` class

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_agents_mock.py::TestRegionPlannerAgent -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agents.region_planner'`

- [ ] **Step 3: Create RegionPlannerAgent**

Create `backend/agents/region_planner.py`:

```python
from models.travel_request import TravelRequest
from models.trip_leg import RegionPlan, RegionPlanItem
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Reiserouten-Stratege. Plane eine Rundreise durch Regionen basierend auf der "
    "Beschreibung des Reisenden. Ordne Regionen in einer logistisch sinnvollen Reihenfolge "
    "(minimale Rückwege, geografische Effizienz). Jede Region soll ein Gebiet repräsentieren, "
    "in dem der Reisende konkrete Stopps machen kann. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)

REGION_SCHEMA = """{
  "regions": [
    { "name": "Regionsname", "lat": 0.0, "lon": 0.0, "reason": "Warum diese Region" }
  ],
  "summary": "Zusammenfassung der Rundreise"
}"""


class RegionPlannerAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-opus-4-5")

    def _leg_context(self, leg_index: int) -> str:
        req = self.request
        leg = req.legs[leg_index]
        styles = ", ".join(req.travel_styles) if req.travel_styles else "keine Angabe"
        return (
            f"Startort: {leg.start_location}\n"
            f"Endort: {leg.end_location}\n"
            f"Verfügbare Tage: {leg.total_days}\n"
            f"Max. Fahrzeit/Tag: {req.max_drive_hours_per_day}h\n"
            f"Reisestile: {styles}\n"
            f"Reisende: {req.adults} Erwachsene"
            + (f", Kinder: {len(req.children)}" if req.children else "")
        )

    async def plan(self, description: str, leg_index: int) -> RegionPlan:
        context = self._leg_context(leg_index)

        prompt = (
            f"{context}\n\n"
            f"Beschreibung des Reisenden:\n{description}\n\n"
            f"Erstelle einen Regionen-Plan: eine geordnete Liste von Regionen, "
            f"die der Reisende auf einer Rundreise besuchen soll.\n"
            f"- Jede Region = ein Gebiet mit mehreren möglichen Stopps\n"
            f"- Logistisch sinnvolle Reihenfolge (minimale Rückwege)\n"
            f"- Anzahl Regionen passend zur verfügbaren Zeit\n\n"
            f"Antwortformat:\n{REGION_SCHEMA}"
        )

        await debug_logger.log(
            LogLevel.API, f"→ RegionPlannerAgent (Plan) {description[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        return RegionPlan(**data)

    async def replace_region(
        self, index: int, instruction: str,
        current_plan: RegionPlan, leg_index: int,
    ) -> RegionPlan:
        context = self._leg_context(leg_index)
        regions_str = "\n".join(
            f"{i+1}. {r.name} — {r.reason}" for i, r in enumerate(current_plan.regions)
        )

        prompt = (
            f"{context}\n\n"
            f"Aktueller Regionen-Plan:\n{regions_str}\n\n"
            f"Der Reisende möchte Region {index+1} ({current_plan.regions[index].name}) ersetzen:\n"
            f'"{instruction}"\n\n'
            f"Erstelle den aktualisierten Plan. Ersetze NUR Region {index+1}, "
            f"behalte alle anderen Regionen bei. Passe die Reihenfolge an falls nötig.\n\n"
            f"Antwortformat:\n{REGION_SCHEMA}"
        )

        await debug_logger.log(
            LogLevel.API,
            f"→ RegionPlannerAgent (Ersetzen #{index+1}) {instruction[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        return RegionPlan(**data)

    async def recalculate(
        self, instruction: str,
        current_plan: RegionPlan, leg_index: int,
    ) -> RegionPlan:
        context = self._leg_context(leg_index)
        regions_str = "\n".join(
            f"{i+1}. {r.name} — {r.reason}" for i, r in enumerate(current_plan.regions)
        )

        prompt = (
            f"{context}\n\n"
            f"Bisheriger Regionen-Plan:\n{regions_str}\n"
            f"Zusammenfassung: {current_plan.summary}\n\n"
            f"Korrektur des Reisenden:\n\"{instruction}\"\n\n"
            f"Erstelle einen komplett neuen Regionen-Plan unter Berücksichtigung "
            f"der Korrektur. Der bisherige Plan dient als Kontext.\n\n"
            f"Antwortformat:\n{REGION_SCHEMA}"
        )

        await debug_logger.log(
            LogLevel.API,
            f"→ RegionPlannerAgent (Neu berechnen) {instruction[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        return RegionPlan(**data)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_agents_mock.py::TestRegionPlannerAgent -v`
Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/agents/region_planner.py backend/tests/test_agents_mock.py
git commit -m "feat: RegionPlannerAgent mit plan/replace/recalculate Operationen

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Update StopOptionsFinder Prompt — Locations Not Regions

**Files:**
- Modify: `backend/agents/stop_options_finder.py`

- [ ] **Step 1: Update SYSTEM_PROMPT**

The prompt at line 13 already has the location-not-region instruction (added in a previous session). Verify it contains:
```
"Immer eine konkrete Ortschaft (Stadt, Dorf, Kleinstadt) angeben — NIEMALS Regionen"
```
If present, no change needed.

- [ ] **Step 2: Remove explore-specific dead code**

Delete these three items from `stop_options_finder.py`:
- `SYSTEM_PROMPT_EXPLORE` (lines 24-31)
- `_build_prompt_explore()` method (lines 362-419)
- `find_options_explore()` method (lines 421-449)

- [ ] **Step 3: Run scoped tests**

Run: `cd backend && python3 -m pytest tests/test_models.py tests/test_agents_mock.py -v`
Expected: All tests pass. Full test suite will pass after Chunk 2 removes old consumers.

- [ ] **Step 4: Commit**

```bash
git add backend/agents/stop_options_finder.py
git commit -m "refactor: Explore-spezifische Methoden aus StopOptionsFinder entfernt

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: Backend Endpoint Changes

### Task 4: Remove DetourOptionsAgent and Its Fallback

**Files:**
- Delete: `backend/agents/detour_options_agent.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Remove DetourOptionsAgent fallback from `_find_and_stream_options()`**

In `main.py`, remove the fallback block at lines 771-808. This is the section starting with:
```python
    # Fallback: wenn 0 gültige Optionen (direkt oder nach Retry) → DetourOptionsAgent
```

Replace it with the no-stops-found response. After the retry logic (which ends around line 769), if still 0 valid options:

```python
    if len(enriched_options) == 0:
        # Keine gültigen Optionen — Frontend zeigt Korridor + Eingabefeld
        await debug_logger.log(
            LogLevel.WARNING,
            f"0 gültige Optionen — Frontend zeigt Korridor für Benutzerführung",
            job_id=job_id,
        )
        await debug_logger.push_event(
            job_id, "route_options_done", None,
            {
                "options": [],
                "map_anchors": map_anchors,
                "estimated_total_stops": 0,
                "route_could_be_complete": False,
                "no_stops_found": True,
                "corridor": {
                    "start": prev_location,
                    "end": segment_target,
                    "start_coords": prev_coords,
                    "end_coords": target_coords,
                },
            },
        )
        return [], 0, False
```

- [ ] **Step 2: Delete detour_options_agent.py**

```bash
rm backend/agents/detour_options_agent.py
```

- [ ] **Step 3: Remove detour-related comment on line 748**

Remove the comment `# Retry only if 1–2 valid options (worth filling up; 0 goes straight to DetourOptionsAgent)` — replace with `# Retry only if 1–2 valid options (worth filling up)`.

- [ ] **Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: All tests pass. If any test references `DetourOptionsAgent`, remove that test.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py && git rm backend/agents/detour_options_agent.py
git commit -m "refactor: DetourOptionsAgent entfernt — Benutzerführung statt Umwege

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Remove Old Explore Endpoints and Update Job State

**Files:**
- Delete: `backend/agents/explore_zone_agent.py`
- Modify: `backend/main.py`
- Modify: `backend/orchestrator.py`

- [ ] **Step 1: Update `_new_job()` in main.py**

In `_new_job()` (line 341), replace the explore state fields:

Old (lines 360-365):
```python
        # Explore leg state (reset on each explore leg transition)
        "explore_phase": None,
        # None | "awaiting_guidance" | "circuit_ready" | "selecting_stops"
        "explore_zone_analysis": None,    # ExploreZoneAnalysis dict after first pass
        "explore_circuit": [],            # list[ExploreStop dicts] after second pass
        "explore_circuit_position": 0,
```

New:
```python
        # Explore/Region leg state (reset on each explore leg transition)
        "region_plan": None,           # RegionPlan dict after planning
        "region_plan_confirmed": False, # True after user confirms
```

Remove the `from models.trip_leg import ExploreZoneAnalysis` import at line 342.

- [ ] **Step 2: Update `_start_explore_leg()` to use RegionPlannerAgent**

Replace the function at lines 274-302:

```python
async def _start_explore_leg(job: dict, job_id: str, request: TravelRequest) -> dict:
    """Start explore-mode leg: runs RegionPlannerAgent, returns region plan."""
    from agents.region_planner import RegionPlannerAgent

    leg_index = job["leg_index"]
    leg = request.legs[leg_index]
    description = leg.explore_description or f"{leg.start_location} bis {leg.end_location} erkunden"

    agent = RegionPlannerAgent(request, job_id)
    region_plan = await agent.plan(description=description, leg_index=leg_index)

    job["region_plan"] = region_plan.model_dump()
    job["status"] = "awaiting_region_confirmation"
    save_job(job_id, job)

    await debug_logger.push_event(
        job_id, "region_plan_ready", None,
        {"regions": [r.model_dump() for r in region_plan.regions],
         "summary": region_plan.summary,
         "leg_id": leg.leg_id}
    )

    return {
        "options": [],
        "meta": {
            "leg_index": leg_index,
            "total_legs": len(request.legs),
            "leg_mode": leg.mode,
        },
        "explore_pending": True,
        "region_plan": region_plan.model_dump(),
        "leg_advanced": True,
    }
```

- [ ] **Step 3: Remove the `answer-explore-questions` endpoint**

Delete the entire `answer_explore_questions()` function (starting at line 1997 `@app.post("/api/answer-explore-questions/{job_id}")`). This is a large block (~70 lines).

Remove the import `from models.trip_leg import ExploreAnswersRequest` at line 26.

- [ ] **Step 4: Add new region plan endpoints**

Add these 4 endpoints to `main.py`:

```python
# ---------------------------------------------------------------------------
# POST /api/replace-region/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/replace-region/{job_id}")
async def replace_region(job_id: str, body: ReplaceRegionRequest):
    from agents.region_planner import RegionPlannerAgent
    from models.trip_leg import RegionPlan

    job = get_job(job_id)
    if not job.get("region_plan"):
        raise HTTPException(status_code=409, detail="Kein Regionen-Plan vorhanden")

    current_plan = RegionPlan(**job["region_plan"])
    if body.index >= len(current_plan.regions):
        raise HTTPException(status_code=400, detail="Ungültiger Region-Index")

    request = TravelRequest(**job["request"])
    agent = RegionPlannerAgent(request, job_id)
    new_plan = await agent.replace_region(
        index=body.index,
        instruction=body.instruction,
        current_plan=current_plan,
        leg_index=job["leg_index"],
    )

    job["region_plan"] = new_plan.model_dump()
    save_job(job_id, job)

    await debug_logger.push_event(
        job_id, "region_updated", None,
        {"regions": [r.model_dump() for r in new_plan.regions],
         "summary": new_plan.summary}
    )

    return {"status": "ok", "region_plan": new_plan.model_dump()}


# ---------------------------------------------------------------------------
# POST /api/recompute-regions/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/recompute-regions/{job_id}")
async def recompute_regions(job_id: str, body: RecomputeRegionsRequest):
    from agents.region_planner import RegionPlannerAgent
    from models.trip_leg import RegionPlan

    job = get_job(job_id)
    if not job.get("region_plan"):
        raise HTTPException(status_code=409, detail="Kein Regionen-Plan vorhanden")

    current_plan = RegionPlan(**job["region_plan"])
    request = TravelRequest(**job["request"])
    agent = RegionPlannerAgent(request, job_id)
    new_plan = await agent.recalculate(
        instruction=body.instruction,
        current_plan=current_plan,
        leg_index=job["leg_index"],
    )

    job["region_plan"] = new_plan.model_dump()
    save_job(job_id, job)

    await debug_logger.push_event(
        job_id, "region_updated", None,
        {"regions": [r.model_dump() for r in new_plan.regions],
         "summary": new_plan.summary}
    )

    return {"status": "ok", "region_plan": new_plan.model_dump()}


# ---------------------------------------------------------------------------
# POST /api/confirm-regions/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/confirm-regions/{job_id}")
async def confirm_regions(job_id: str):
    from models.trip_leg import RegionPlan

    job = get_job(job_id)
    if not job.get("region_plan"):
        raise HTTPException(status_code=409, detail="Kein Regionen-Plan vorhanden")

    region_plan = RegionPlan(**job["region_plan"])
    request = TravelRequest(**job["request"])
    leg_index = job["leg_index"]

    # Convert regions to via_points on the leg (invisible to user)
    via_points = []
    for region in region_plan.regions:
        via_points.append({
            "location": region.name,
            "fixed_date": None,
            "notes": f"Region: {region.reason}",
        })

    # Inject via_points into the request leg
    req_data = job["request"]
    req_data["legs"][leg_index]["via_points"] = via_points
    # Switch leg mode to transit for stop-by-stop processing
    req_data["legs"][leg_index]["mode"] = "transit"
    job["request"] = req_data
    job["region_plan_confirmed"] = True
    job["current_leg_mode"] = "transit"

    # Recalculate segment budget with new via_points
    request = TravelRequest(**req_data)
    job["segment_budget"] = _calc_leg_segment_budget(request, leg_index)
    save_job(job_id, job)

    # Start stop finding for the first segment
    result = await _start_leg_route_building(job, job_id, request)
    result["job_id"] = job_id
    return result
```

Add imports at the top of main.py:
```python
from models.trip_leg import ReplaceRegionRequest, RecomputeRegionsRequest
```

- [ ] **Step 5: Update `_advance_to_next_leg()` to reset region state**

In `_advance_to_next_leg()` (around line 196), find and remove the old explore state resets:

```python
    # Remove these lines:
    job["explore_phase"] = None
    job["explore_zone_analysis"] = None
    job["explore_circuit"] = []
    job["explore_circuit_position"] = 0
```

Replace with:
```python
    job["region_plan"] = None
    job["region_plan_confirmed"] = False
```

- [ ] **Step 6: Update orchestrator.py**

In `orchestrator.py`, replace the imports (lines 7, 13):

Old:
```python
from agents.explore_zone_agent import ExploreZoneAgent
from models.trip_leg import ExploreZoneAnalysis, ExploreStop
```

New:
```python
from agents.region_planner import RegionPlannerAgent
from models.trip_leg import RegionPlan
```

Update `_run_all_legs()` per-leg state reset (lines 99-101). Replace:

```python
            job["explore_phase"] = None
            job["explore_circuit"] = []
            job["explore_circuit_position"] = 0
```

With:
```python
            job["region_plan"] = None
            job["region_plan_confirmed"] = False
```

Replace `_run_explore_leg()` method (lines 124-162):

```python
    async def _run_explore_leg(self, leg, leg_index: int) -> Optional[list]:
        """Explore leg: RegionPlannerAgent plans regions, user confirms interactively."""
        job = self._load_job()

        if not job.get("region_plan"):
            # First call: generate region plan
            description = leg.explore_description or f"{leg.start_location} bis {leg.end_location} erkunden"
            agent = RegionPlannerAgent(self.request, self.job_id)
            region_plan = await agent.plan(description=description, leg_index=leg_index)
            job = self._load_job()
            job["region_plan"] = region_plan.model_dump()
            job["status"] = "awaiting_region_confirmation"
            self._save_job(job)
            await debug_logger.push_event(
                self.job_id, "region_plan_ready", None,
                {"regions": [r.model_dump() for r in region_plan.regions],
                 "summary": region_plan.summary, "leg_id": leg.leg_id}
            )
            return None  # Pause — user confirms via /api/confirm-regions

        # Region plan confirmed — stops are being selected via normal transit flow
        job = self._load_job()
        return job.get("selected_stops", [])
```

- [ ] **Step 7: Delete old models from trip_leg.py**

Now that all consumers are updated, delete `ExploreZoneAnalysis` (lines 31-34) and `ExploreAnswersRequest` (lines 37-38) from `trip_leg.py`. Also update `test_models.py` line 531 import to remove them, and delete the `TestExploreZoneAnalysis` and `TestExploreAnswersRequest` test classes (lines 566-590).

- [ ] **Step 8: Delete explore_zone_agent.py**

```bash
rm backend/agents/explore_zone_agent.py
```

- [ ] **Step 8: Update endpoint tests**

In `test_endpoints.py`, replace the `answer-explore-questions` tests (around lines 410-463) with tests for the new region endpoints:

```python
class TestRegionEndpoints:
    def test_replace_region_409_no_plan(self, client, mock_job):
        job_id = mock_job["job_id"]
        resp = client.post(
            f"/api/replace-region/{job_id}",
            json={"index": 0, "instruction": "Wallis stattdessen"}
        )
        assert resp.status_code == 409

    def test_recompute_regions_409_no_plan(self, client, mock_job):
        job_id = mock_job["job_id"]
        resp = client.post(
            f"/api/recompute-regions/{job_id}",
            json={"instruction": "Mehr Küste"}
        )
        assert resp.status_code == 409

    def test_confirm_regions_409_no_plan(self, client, mock_job):
        job_id = mock_job["job_id"]
        resp = client.post(f"/api/confirm-regions/{job_id}")
        assert resp.status_code == 409

    def test_replace_region_400_index_out_of_bounds(self, client, mock_job, mocker):
        mock_job["region_plan"] = {
            "regions": [{"name": "Tessin", "lat": 46.2, "lon": 8.95, "reason": "Seen"}],
            "summary": "Test"
        }
        job_id = mock_job["job_id"]
        resp = client.post(
            f"/api/replace-region/{job_id}",
            json={"index": 5, "instruction": "egal"}
        )
        assert resp.status_code == 400

    def test_replace_region_ok(self, client, mock_job, mocker):
        from models.trip_leg import RegionPlan, RegionPlanItem
        mock_job["region_plan"] = {
            "regions": [{"name": "Tessin", "lat": 46.2, "lon": 8.95, "reason": "Seen"}],
            "summary": "Test"
        }
        mock_job["leg_index"] = 0
        mock_job["request"]["legs"][0]["mode"] = "explore"
        job_id = mock_job["job_id"]
        new_plan = RegionPlan(
            regions=[RegionPlanItem(name="Wallis", lat=46.3, lon=7.6, reason="Matterhorn")],
            summary="Neu"
        )
        mock_agent = mocker.patch("agents.region_planner.RegionPlannerAgent", autospec=True)
        mock_agent.return_value.replace_region = mocker.AsyncMock(return_value=new_plan)
        mocker.patch("main.debug_logger.push_event", new_callable=mocker.AsyncMock)

        resp = client.post(
            f"/api/replace-region/{job_id}",
            json={"index": 0, "instruction": "Wallis stattdessen"}
        )
        assert resp.status_code == 200
        assert resp.json()["region_plan"]["regions"][0]["name"] == "Wallis"
```

- [ ] **Step 9: Run all tests**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 10: Commit**

```bash
git add backend/main.py backend/orchestrator.py backend/tests/test_endpoints.py && git rm backend/agents/explore_zone_agent.py
git commit -m "feat: Region-Plan Endpoints und ExploreZoneAgent/answer-explore-questions entfernt

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: Frontend Changes

### Task 6: Update Form — Replace Zone Map With Textarea

**Files:**
- Modify: `frontend/js/form.js`

- [ ] **Step 1: Replace explore content HTML**

In `renderLegCard()`, replace the explore content section (lines 362-373):

Old:
```javascript
  const exploreContent = leg.mode === "explore" ? `
      <div class="leg-zone">
          <label class="form-label-sm">Erkundungszone</label>
          <div id="zone-map-${index}" class="zone-map-container" style="height:180px;..."></div>
          <div class="zone-label-row">
              <span class="form-label-sm">Zone:</span>
              <input type="text" class="input-sm" id="zone-label-${index}"
                  value="${esc(leg.zone_bbox?.zone_label || '')}"
                  oninput="updateZoneLabel(${index}, this.value)"
                  placeholder="Zone benennen…">
          </div>
      </div>` : "";
```

New:
```javascript
  const exploreContent = leg.mode === "explore" ? `
      <div class="leg-zone">
          <label class="form-label-sm">Was möchtest du erkunden?</label>
          <textarea id="explore-text-${index}" class="input-sm"
              placeholder="z.B. 'Die Französischen Alpen — Bergdörfer, Seen und Alpenpässe' oder 'Toskana mit Fokus auf Weingüter und mittelalterliche Städte'"
              rows="3"
              oninput="S.legs[${index}].explore_description = this.value"
          >${esc(leg.explore_description || '')}</textarea>
      </div>` : "";
```

- [ ] **Step 2: Remove initZoneMap() function**

Delete the `initZoneMap()` function (lines 493-538).

- [ ] **Step 3: Remove geocodeZoneLabel() function**

Delete the `geocodeZoneLabel()` function (lines 540-551).

- [ ] **Step 4: Update setLegMode()**

In `setLegMode()` (lines 456-465), remove the zone map initialization:

Old:
```javascript
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
```

New:
```javascript
function setLegMode(index, mode) {
  S.legs[index].mode = mode;
  if (mode === "explore" && !S.legs[index].explore_description) {
    S.legs[index].explore_description = '';
  }
  renderLegs();
}
```

- [ ] **Step 5: Update buildPayload()**

In `buildPayload()` (around line 771), the `cleanLegs` mapping already strips `_pending_zone_label`. No additional changes needed since `explore_description` is already a regular field on the leg object that passes through.

- [ ] **Step 6: Initialize explore_description in leg defaults**

In `addLeg()` (line 417), add `explore_description: ''` to the new leg object literal (around lines 417-427). Also add it to the initial leg in `initLegs()` if present.

- [ ] **Step 7: Commit**

```bash
git add frontend/js/form.js
git commit -m "feat: Explore-Modus Textfeld statt Leaflet-Kartenzeichnung

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Update API.js — Region Plan API Calls + SSE Events

**Files:**
- Modify: `frontend/js/api.js`

- [ ] **Step 1: Remove answerExploreQuestions()**

Delete the function at lines 152-157:
```javascript
async function answerExploreQuestions(jobId, answers) { ... }
```

- [ ] **Step 2: Add region plan API functions**

Add these functions:

```javascript
async function replaceRegion(jobId, index, instruction) {
  return await _fetchQuiet(`${API}/replace-region/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ index, instruction }),
  }).then(r => r.json());
}

async function recomputeRegions(jobId, instruction) {
  return await _fetchQuiet(`${API}/recompute-regions/${jobId}`, {
    method: 'POST',
    body: JSON.stringify({ instruction }),
  }).then(r => r.json());
}

async function confirmRegions(jobId) {
  return await _fetchQuiet(`${API}/confirm-regions/${jobId}`, {
    method: 'POST',
  }).then(r => r.json());
}
```

- [ ] **Step 3: Update SSE event list in openSSE()**

In the `events` array (lines 198-204), replace:
```javascript
    'explore_zone_questions', 'explore_circuit_ready',
```
with:
```javascript
    'region_plan_ready', 'region_updated',
```

- [ ] **Step 4: Commit**

```bash
git add frontend/js/api.js
git commit -m "feat: Region-Plan API-Funktionen und SSE-Events aktualisiert

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 8: Update Route-Builder — Region Plan UI + No-Stops-Found

**Files:**
- Modify: `frontend/js/route-builder.js`

- [ ] **Step 1: Update SSE handlers in openRouteSSE()**

Replace the explore handlers (lines 21-22):

Old:
```javascript
    explore_zone_questions: data => { showExploreGuidanceForm(data.questions, data.leg_id); },
    explore_circuit_ready:  data => { showExploreCircuit(data.circuit, data.warnings); },
```

New:
```javascript
    region_plan_ready: data => { showRegionPlanUI(data.regions, data.summary, data.leg_id); },
    region_updated:    data => { updateRegionPlanUI(data.regions, data.summary); },
```

- [ ] **Step 2: Remove old explore functions**

Delete these functions:
- `showExploreGuidanceForm()` (lines 774-798)
- `submitGuidanceAnswers()` (lines 804-843)
- `showExploreCircuit()` (lines 845-871)
- `window._guidanceAnswers` reference
- `updateGuidanceAnswer()` if it exists

- [ ] **Step 3: Remove detour banner code**

Delete `_insertDetourBanner()` (lines 105-112).

Remove the detour banner insertion calls:
- In `onRouteOptionsDone()`: remove the `allDetour` check and `_insertDetourBanner()` call (around line 128)
- In `renderOptions()`: remove the `allDetour` variable declaration (line 325) AND the detour banner insertion block (lines 353-358)

- [ ] **Step 4: Handle no_stops_found in onRouteOptionsDone()**

In `onRouteOptionsDone()`, add handling for `no_stops_found`:

```javascript
function onRouteOptionsDone(data) {
  // ...existing code for closing overlays...

  if (data.no_stops_found) {
    _showNoStopsFoundUI(data.corridor);
    return;
  }

  // ...existing option rendering code...
}
```

- [ ] **Step 5: Add _showNoStopsFoundUI()**

```javascript
function _showNoStopsFoundUI(corridor) {
  const container = document.getElementById('route-options-container');
  if (!container) return;
  container.innerHTML = '';

  const mapDiv = document.createElement('div');
  mapDiv.id = 'no-stops-map';
  mapDiv.style.cssText = 'height:300px;border-radius:12px;margin-bottom:16px';

  container.innerHTML = `
    <div class="no-stops-found">
      <h3>Keine passenden Zwischenstopps gefunden</h3>
      <p>Auf der direkten Route zwischen <strong>${esc(corridor.start)}</strong> und
         <strong>${esc(corridor.end)}</strong> gibt es keine passenden Stopps.</p>
    </div>
  `;
  container.appendChild(mapDiv);
  container.insertAdjacentHTML('beforeend', `
    <div class="guidance-input-row" style="margin-top:12px">
      <label class="form-label-sm">Wo möchtest du anhalten?</label>
      <input type="text" class="input-sm" id="guidance-text"
        placeholder="z.B. 'In der Nähe von Annecy' oder 'Am Genfer See'" style="width:100%">
      <button class="btn btn-primary" style="margin-top:8px" onclick="_submitGuidance()">
        Nochmal suchen
      </button>
      <button class="btn btn-secondary" style="margin-top:8px;margin-left:8px" onclick="skipStop()">
        Direkt zum Ziel fahren
      </button>
    </div>
  `);

  // Show corridor on Google Maps
  if (corridor.start_coords && corridor.end_coords && typeof google !== 'undefined') {
    const map = new google.maps.Map(mapDiv, { zoom: 6, center: {
      lat: (corridor.start_coords[0] + corridor.end_coords[0]) / 2,
      lng: (corridor.start_coords[1] + corridor.end_coords[1]) / 2,
    }});
    new google.maps.Marker({ position: { lat: corridor.start_coords[0], lng: corridor.start_coords[1] }, map, label: 'S' });
    new google.maps.Marker({ position: { lat: corridor.end_coords[0], lng: corridor.end_coords[1] }, map, label: 'Z' });
    new google.maps.Polyline({
      path: [
        { lat: corridor.start_coords[0], lng: corridor.start_coords[1] },
        { lat: corridor.end_coords[0], lng: corridor.end_coords[1] },
      ],
      strokeColor: '#4a90d9', strokeWeight: 3, strokeOpacity: 0.7,
      map,
    });
  }
}

async function _submitGuidance() {
  const input = document.getElementById('guidance-text');
  if (!input || !input.value.trim()) return;
  const guidance = input.value.trim();
  progressOverlay.open('Suche mit deiner Angabe…');
  openRouteSSE(S.jobId);
  try {
    const data = await _fetchQuiet(`${API}/recompute-options/${S.jobId}`, {
      method: 'POST',
      body: JSON.stringify({ extra_instructions: guidance }),
    }).then(r => r.json());
    startRouteBuilding(data);
  } catch (err) {
    progressOverlay.close();
    closeRouteSSE();
    console.error('Guidance retry fehlgeschlagen:', err);
  }
}
```

- [ ] **Step 6: Add Region Plan UI**

Add the region plan interactive UI:

```javascript
let _regionPlanMap = null;
let _regionMarkers = [];
let _regionPolyline = null;

function showRegionPlanUI(regions, summary, legId) {
  progressOverlay.close();
  closeRouteSSE();
  S.loadingOptions = false;

  const container = document.getElementById('route-builder-panel') ||
                    document.getElementById('progress-panel');
  if (!container) return;

  // Store regions globally for drag-and-drop
  window._currentRegions = regions;
  window._currentRegionLegId = legId;

  const regionListHtml = regions.map((r, i) => `
    <li class="region-item" draggable="true" data-index="${i}"
        ondragstart="_onRegionDragStart(event, ${i})"
        ondragover="event.preventDefault()"
        ondrop="_onRegionDrop(event, ${i})">
      <div class="region-item-content">
        <span class="region-number">${i + 1}</span>
        <div class="region-info">
          <strong>${esc(r.name)}</strong>
          <span class="region-reason">${esc(r.reason)}</span>
        </div>
        <button class="btn btn-sm btn-outline" onclick="_toggleReplaceRegion(${i})">Ersetzen</button>
      </div>
      <div class="region-replace-form" id="region-replace-${i}" style="display:none">
        <input type="text" class="input-sm" id="region-replace-text-${i}"
          placeholder="Wie soll diese Region ersetzt werden?">
        <button class="btn btn-sm btn-primary" onclick="_doReplaceRegion(${i})">Ersetzen</button>
      </div>
    </li>
  `).join('');

  container.innerHTML = `
    <div class="region-plan-ui">
      <h3>Regionen-Plan</h3>
      <p class="region-summary">${esc(summary)}</p>
      <div class="region-plan-layout">
        <div class="region-list-panel">
          <ol class="region-list" id="region-list">${regionListHtml}</ol>
          <div class="region-actions">
            <button class="btn btn-secondary" onclick="_toggleRecompute()">Neu berechnen</button>
            <button class="btn btn-primary" onclick="_confirmRegions()">Route bestätigen</button>
          </div>
          <div id="recompute-form" style="display:none;margin-top:8px">
            <input type="text" class="input-sm" id="recompute-text"
              placeholder="Was soll geändert werden?" style="width:100%">
            <button class="btn btn-sm btn-primary" style="margin-top:4px" onclick="_doRecompute()">
              Neu berechnen
            </button>
          </div>
        </div>
        <div class="region-map-panel">
          <div id="region-plan-map" style="height:400px;border-radius:12px"></div>
        </div>
      </div>
    </div>
  `;

  _initRegionMap(regions);
}

function _initRegionMap(regions) {
  const mapDiv = document.getElementById('region-plan-map');
  if (!mapDiv || typeof google === 'undefined') return;

  const bounds = new google.maps.LatLngBounds();
  const path = [];

  _regionPlanMap = new google.maps.Map(mapDiv, { zoom: 5 });
  _regionMarkers = [];

  regions.forEach((r, i) => {
    const pos = { lat: r.lat, lng: r.lon };
    bounds.extend(pos);
    path.push(pos);

    const marker = new google.maps.Marker({
      position: pos,
      map: _regionPlanMap,
      label: { text: String(i + 1), color: '#fff' },
      title: r.name,
    });
    _regionMarkers.push(marker);
  });

  _regionPolyline = new google.maps.Polyline({
    path,
    strokeColor: '#4a90d9',
    strokeWeight: 3,
    strokeOpacity: 0.8,
    map: _regionPlanMap,
  });

  _regionPlanMap.fitBounds(bounds, 50);
}

function updateRegionPlanUI(regions, summary) {
  window._currentRegions = regions;
  // Re-render the list
  const list = document.getElementById('region-list');
  if (list) {
    list.innerHTML = regions.map((r, i) => `
      <li class="region-item" draggable="true" data-index="${i}"
          ondragstart="_onRegionDragStart(event, ${i})"
          ondragover="event.preventDefault()"
          ondrop="_onRegionDrop(event, ${i})">
        <div class="region-item-content">
          <span class="region-number">${i + 1}</span>
          <div class="region-info">
            <strong>${esc(r.name)}</strong>
            <span class="region-reason">${esc(r.reason)}</span>
          </div>
          <button class="btn btn-sm btn-outline" onclick="_toggleReplaceRegion(${i})">Ersetzen</button>
        </div>
        <div class="region-replace-form" id="region-replace-${i}" style="display:none">
          <input type="text" class="input-sm" id="region-replace-text-${i}"
            placeholder="Wie soll diese Region ersetzt werden?">
          <button class="btn btn-sm btn-primary" onclick="_doReplaceRegion(${i})">Ersetzen</button>
        </div>
      </li>
    `).join('');
  }
  // Update summary
  const summaryEl = document.querySelector('.region-summary');
  if (summaryEl) summaryEl.textContent = summary;
  // Update map
  _updateRegionMap(regions);
}

function _updateRegionMap(regions) {
  if (!_regionPlanMap) return;
  _regionMarkers.forEach(m => m.setMap(null));
  if (_regionPolyline) _regionPolyline.setMap(null);
  _initRegionMap(regions);
}

// Drag and drop
let _dragSourceIndex = null;

function _onRegionDragStart(e, index) {
  _dragSourceIndex = index;
  e.dataTransfer.effectAllowed = 'move';
}

function _onRegionDrop(e, targetIndex) {
  e.preventDefault();
  if (_dragSourceIndex === null || _dragSourceIndex === targetIndex) return;
  const regions = window._currentRegions;
  const [moved] = regions.splice(_dragSourceIndex, 1);
  regions.splice(targetIndex, 0, moved);
  _dragSourceIndex = null;
  updateRegionPlanUI(regions, document.querySelector('.region-summary')?.textContent || '');
}

function _toggleReplaceRegion(index) {
  const form = document.getElementById(`region-replace-${index}`);
  if (form) form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function _doReplaceRegion(index) {
  const input = document.getElementById(`region-replace-text-${index}`);
  if (!input || !input.value.trim()) return;
  progressOverlay.open('Region wird ersetzt…');
  try {
    const data = await replaceRegion(S.jobId, index, input.value.trim());
    progressOverlay.close();
    if (data.region_plan) {
      updateRegionPlanUI(data.region_plan.regions, data.region_plan.summary);
    }
  } catch (err) {
    progressOverlay.close();
    console.error('Region ersetzen fehlgeschlagen:', err);
  }
}

function _toggleRecompute() {
  const form = document.getElementById('recompute-form');
  if (form) form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function _doRecompute() {
  const input = document.getElementById('recompute-text');
  if (!input || !input.value.trim()) return;
  progressOverlay.open('Route wird neu berechnet…');
  try {
    const data = await recomputeRegions(S.jobId, input.value.trim());
    progressOverlay.close();
    if (data.region_plan) {
      updateRegionPlanUI(data.region_plan.regions, data.region_plan.summary);
    }
  } catch (err) {
    progressOverlay.close();
    console.error('Neu berechnen fehlgeschlagen:', err);
  }
}

async function _confirmRegions() {
  progressOverlay.open('Route wird bestätigt — Stopps werden gesucht…');
  openRouteSSE(S.jobId);
  try {
    const data = await confirmRegions(S.jobId);
    startRouteBuilding(data);
  } catch (err) {
    progressOverlay.close();
    closeRouteSSE();
    console.error('Region-Bestätigung fehlgeschlagen:', err);
  }
}
```

- [ ] **Step 7: Update startRouteBuilding() explore_pending handling**

The existing `explore_pending` block (lines 216-221) now needs to handle region plan data:

```javascript
  // Explore-Modus: Region-Plan wird angezeigt via SSE region_plan_ready
  if (data.explore_pending) {
    S.loadingOptions = false;
    _updateRouteStatus(data.meta || {});
    renderBuiltStops();
    // If region_plan is included directly (non-SSE path), show it immediately
    if (data.region_plan) {
      showRegionPlanUI(data.region_plan.regions, data.region_plan.summary, data.meta?.leg_id || '');
    }
    return;
  }
```

- [ ] **Step 8: Commit**

```bash
git add frontend/js/route-builder.js
git commit -m "feat: Region-Plan UI mit Drag-and-Drop, Ersetzen, Neu-Berechnen und No-Stops-Found

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: Cleanup and Documentation

### Task 9: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update agent model assignments table**

Add `RegionPlannerAgent` to the table and remove `DetourOptionsAgent`:

```
| RegionPlannerAgent | claude-opus-4-5 | claude-haiku-4-5 |
```

Remove the `DetourOptionsAgent` row.

- [ ] **Step 2: Update file tree**

In the architecture tree, replace:
```
│   │   ├── detour_options_agent.py      # claude-sonnet-4-5 (Rundreise detours)
```
with:
```
│   │   ├── region_planner.py            # claude-opus-4-5 (region route planning)
```

Remove `explore_zone_agent.py` if it appears in the tree (it may already be absent).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md Agent-Tabelle und Dateibaum aktualisiert

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 10: Final Integration Test

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 2: Verify no stale imports**

Run: `cd backend && python3 -c "from main import app; print('OK')"`
Expected: `OK` (no import errors).

Run: `cd backend && python3 -c "from orchestrator import TravelPlannerOrchestrator; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Verify deleted files are gone**

```bash
ls backend/agents/detour_options_agent.py 2>/dev/null && echo "STILL EXISTS" || echo "OK deleted"
ls backend/agents/explore_zone_agent.py 2>/dev/null && echo "STILL EXISTS" || echo "OK deleted"
```

- [ ] **Step 4: Check for stale references**

```bash
grep -r "DetourOptionsAgent\|detour_options_agent\|ExploreZoneAgent\|explore_zone_agent\|ExploreZoneAnalysis\|ExploreAnswersRequest\|answerExploreQuestions\|answer-explore-questions\|explore_zone_questions\|explore_circuit_ready\|showExploreGuidanceForm\|submitGuidanceAnswers\|showExploreCircuit\|_guidanceAnswers\|initZoneMap\|geocodeZoneLabel\|_insertDetourBanner" backend/ frontend/ --include="*.py" --include="*.js" -l
```
Expected: No results (all references cleaned up).

- [ ] **Step 5: Frontend syntax check**

```bash
node --check frontend/js/route-builder.js && node --check frontend/js/form.js && node --check frontend/js/api.js && echo "OK"
```
Expected: `OK` (no syntax errors).

- [ ] **Step 6: Tag and push**

```bash
git tag vX.X.Y   # increment from latest
git push && git push --tags
```
