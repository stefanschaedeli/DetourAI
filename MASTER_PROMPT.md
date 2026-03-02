# Travelman2 — Complete Rebuild Specification

You are building **Travelman2**, a full-stack AI-powered road trip planner from scratch.
Read this document completely before writing any code. Implement it phase by phase, stopping
after each phase for verification before continuing.

---

## Application Overview

Users fill in a 5-step form to configure a road trip (start, via-points, destination, dates,
travellers, travel styles, accommodation preferences, budget). The backend then runs a
3-phase interactive planning flow:

1. **Route Builder** — user interactively picks from 3 stop options until the route is complete
2. **Accommodation Phase** — all accommodation options load in parallel; user picks one per stop
3. **Full Planning** — orchestrator runs activities/restaurants/day-planner agents in parallel,
   streams SSE progress to frontend, outputs an interactive travel guide web page

---

## Architecture Diagram

```
Browser (Vanilla JS)
    │
    │  HTTP/SSE via /api/*
    ▼
Nginx  ──── serves frontend/ (static files)
    │  proxy_pass /api/ →
    ▼
FastAPI (port 8000)
    │
    ├── Redis  (job state: job:{id} JSON, TTL 24h)
    │
    └── Celery Workers
            ├── tasks/run_planning_job.py
            └── tasks/prefetch_accommodations.py
                    │
                    └── Anthropic API (Claude)
                            ├── route_architect     → claude-opus-4-5
                            ├── stop_options_finder → claude-sonnet-4-5
                            ├── accommodation_researcher → claude-sonnet-4-5
                            ├── activities_agent    → claude-sonnet-4-5
                            ├── restaurants_agent   → claude-sonnet-4-5
                            └── day_planner         → claude-opus-4-5
                    │
                    ├── OpenStreetMap Nominatim (geocoding)
                    ├── OSRM (routing / drive times)
                    └── Wikipedia API (activity images)
```

---

## Technology Stack

- **Backend:** Python 3.11+, FastAPI, `sse-starlette`, `anthropic` SDK, `redis`, `celery`
- **Frontend:** Vanilla HTML/CSS/JS (no build step), Inter font, Apple-inspired design
- **Infrastructure:** Docker Compose, Nginx, Redis
- **Testing:** pytest, FastAPI TestClient
- **Type safety:** OpenAPI → TypeScript via `openapi-typescript`
- **Output:** `fpdf2` (PDF), `python-pptx` (PPTX)
- **External APIs:** Anthropic Claude, Nominatim, OSRM, Wikipedia

---

## Directory Structure (target)

```
travelman2/
├── CLAUDE.md
├── docker-compose.yml
├── infra/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── backend/
│   ├── main.py
│   ├── orchestrator.py
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── run_planning_job.py
│   │   └── prefetch_accommodations.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── route_architect.py
│   │   ├── stop_options_finder.py
│   │   ├── accommodation_researcher.py
│   │   ├── activities_agent.py
│   │   ├── restaurants_agent.py
│   │   ├── day_planner.py
│   │   └── output_generator.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── travel_request.py
│   │   ├── travel_response.py
│   │   ├── stop_option.py
│   │   └── accommodation_option.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── debug_logger.py
│   │   ├── maps_helper.py
│   │   ├── retry_helper.py
│   │   └── json_parser.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_models.py
│   │   ├── test_endpoints.py
│   │   └── test_agents_mock.py
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── js/
│       ├── state.js
│       ├── api.js
│       ├── form.js
│       ├── route-builder.js
│       ├── accommodation.js
│       ├── progress.js
│       ├── guide.js
│       └── types.d.ts        (generated — do not edit)
├── scripts/
│   └── generate-types.sh
└── outputs/
```

---

## Environment Variables

```bash
# backend/.env  (never commit — use .env.example as template)
ANTHROPIC_API_KEY=sk-ant-...
TEST_MODE=true          # true = all agents use claude-haiku-4-5 (cheap dev/test)
REDIS_URL=redis://localhost:6379
```

---

## Data Models (Pydantic — implement verbatim)

### `backend/models/travel_request.py`

```python
from typing import List, Optional
from pydantic import BaseModel, field_validator
from datetime import date

class Child(BaseModel):
    age: int
    @field_validator('age')
    @classmethod
    def age_valid(cls, v):
        if not 0 <= v <= 17:
            raise ValueError('age must be 0-17')
        return v

class ViaPoint(BaseModel):
    location: str
    fixed_date: Optional[date] = None
    notes: Optional[str] = None

class MandatoryActivity(BaseModel):
    name: str
    location: Optional[str] = None

class TravelRequest(BaseModel):
    # Route
    start_location: str
    via_points: List[ViaPoint] = []
    main_destination: str
    start_date: date
    end_date: date
    total_days: int

    # Travellers
    adults: int = 2
    children: List[Child] = []
    travel_styles: List[str] = []        # adventure, relaxation, culture, romantic,
                                          # culinary, road_trip, nature, city, wellness,
                                          # sport, group, kids, slow_travel, party
    travel_description: str = ""

    # Activities
    mandatory_activities: List[MandatoryActivity] = []
    preferred_activities: List[str] = []
    max_activities_per_stop: int = 5
    max_restaurants_per_stop: int = 3
    activities_radius_km: int = 30

    # Route rules
    max_drive_hours_per_day: float = 4.5
    min_nights_per_stop: int = 1
    max_nights_per_stop: int = 5

    # Accommodation
    accommodation_styles: List[str] = []  # hotel, apartment, camping, hostel, airbnb
    accommodation_must_haves: List[str] = []  # pool, wifi, parking, kitchen, breakfast
    hotel_radius_km: int = 10

    # Budget
    budget_chf: float = 3000.0
    budget_buffer_percent: float = 10.0
```

### `backend/models/travel_response.py`

```python
from typing import List, Optional
from pydantic import BaseModel

class StopAccommodation(BaseModel):
    name: str
    type: str                        # hotel, apartment, camping, hostel, airbnb
    price_per_night_chf: float
    total_price_chf: float
    rating: Optional[float] = None
    features: List[str] = []
    booking_url: Optional[str] = None

class StopActivity(BaseModel):
    name: str
    description: str
    duration_hours: float
    price_chf: float = 0.0
    suitable_for_children: bool = False
    notes: Optional[str] = None
    address: Optional[str] = None
    google_maps_url: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: List[str] = []

class Restaurant(BaseModel):
    name: str
    cuisine: str
    price_range: str                 # €, €€, €€€
    family_friendly: bool = False
    notes: Optional[str] = None

class TravelStop(BaseModel):
    id: int
    region: str
    country: str
    arrival_day: int
    nights: int
    drive_hours_from_prev: float = 0.0
    drive_km_from_prev: float = 0.0
    lat: Optional[float] = None
    lng: Optional[float] = None
    accommodation: Optional[StopAccommodation] = None
    top_activities: List[StopActivity] = []
    restaurants: List[Restaurant] = []
    google_maps_url: Optional[str] = None
    notes: Optional[str] = None

class DayPlan(BaseModel):
    day: int
    date: Optional[str] = None
    type: str                        # drive, rest, activity, mixed
    title: str
    description: str
    stops_on_route: List[str] = []
    google_maps_route_url: Optional[str] = None

class CostEstimate(BaseModel):
    accommodations_chf: float
    ferries_chf: float = 0.0
    activities_chf: float
    food_chf: float
    fuel_chf: float
    total_chf: float
    budget_remaining_chf: float

class TravelPlan(BaseModel):
    job_id: str
    start_location: str
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    stops: List[TravelStop]
    day_plans: List[DayPlan]
    cost_estimate: CostEstimate
    google_maps_overview_url: Optional[str] = None
    outputs: dict = {}
```

### `backend/models/stop_option.py`

```python
from typing import List, Optional
from pydantic import BaseModel, field_validator

class StopOption(BaseModel):
    id: int
    option_type: str                 # direct, scenic, cultural, via_point
    region: str
    country: str
    drive_hours: float
    nights: int
    highlights: List[str] = []
    teaser: str
    is_fixed: bool = False

class StopOptionsResponse(BaseModel):
    options: List[StopOption]
    route_could_be_complete: bool
    days_remaining: int
    current_stop_number: int
    estimated_total_stops: int

class StopSelectRequest(BaseModel):
    option_index: int

    @field_validator('option_index')
    @classmethod
    def index_valid(cls, v):
        if not 0 <= v <= 2:
            raise ValueError('option_index must be 0, 1, or 2')
        return v
```

### `backend/models/accommodation_option.py`

```python
from typing import List, Optional
from pydantic import BaseModel

class AccommodationOption(BaseModel):
    id: str
    option_type: str                 # budget, comfort, premium
    name: str
    type: str                        # hotel, apartment, camping, hostel, airbnb
    price_per_night_chf: float
    total_price_chf: float
    price_range: str                 # €, €€, €€€
    separate_rooms_available: bool = False
    max_persons: int = 4
    rating: Optional[float] = None
    features: List[str] = []
    teaser: str
    suitable_for_children: bool = False
    booking_hint: str = ""

class BudgetState(BaseModel):
    total_budget_chf: float
    accommodation_budget_chf: float  # 45% of total
    spent_chf: float
    remaining_chf: float
    nights_confirmed: int
    total_nights: int
    avg_per_night_chf: float
    selected_count: int
    total_stops: int

class AccommodationSelectRequest(BaseModel):
    stop_id: int
    option_index: int
```

---

## API Endpoints

All endpoints under prefix `/api/`. CORS enabled for all origins.

### `POST /api/plan-trip`
**Body:** `TravelRequest`
**Returns:**
```json
{
  "job_id": "abc12345",
  "status": "building_route",
  "options": [/* 3 StopOption objects */],
  "meta": {
    "stop_number": 1,
    "days_remaining": 9,
    "estimated_total_stops": 4,
    "route_could_be_complete": false,
    "must_complete": false,
    "segment_index": 0,
    "segment_count": 1,
    "segment_target": "Französische Alpen"
  }
}
```
**Side effect:** Creates Redis key `job:{job_id}`, calls `StopOptionsFinderAgent` for first 3 options.

---

### `POST /api/select-stop/{job_id}`
**Body:** `{"option_index": 0}`
**Returns:** `{job_id, selected_stop, selected_stops[], options[], meta}` (same meta structure as plan-trip)
**Special cases:**
- `must_complete=true` + NOT last segment → inserts via-point stop, starts new segment, returns next options
- `must_complete=true` + last segment → returns `options: []`, `route_could_be_complete: true`

---

### `POST /api/confirm-route/{job_id}`
**Returns:** `{job_id, status: "loading_accommodations", selected_stops[], budget_state, total_stops}`
**Side effect:** Appends missing via-points and main destination to `selected_stops`, assigns 1-based IDs,
then fires Celery task `prefetch_accommodations` which loads all 3 acc options per stop in parallel
(Semaphore 2) and sends SSE events as each completes.

---

### `POST /api/confirm-accommodations/{job_id}`
**Body:** `{"selections": {"1": 0, "2": 1, "3": 2}}` (stop_id → option_index)
**Returns:** `{job_id, status: "accommodations_confirmed", budget_state, selected_count, total_stops}`

---

### `POST /api/select-accommodation/{job_id}` (sequential fallback)
**Body:** `AccommodationSelectRequest`
**Returns:** `{job_id, selected, budget_state, all_complete, stop?, options?, stop_number, total_stops}`

---

### `POST /api/start-planning/{job_id}`
**Returns:** `{job_id, status: "planning_started", stop_count}`
**Side effect:** Fires Celery task `run_planning_job` with `pre_built_stops` + `pre_selected_accommodations`.

---

### `GET /api/progress/{job_id}`
**Returns:** SSE stream
Subscribes to `debug_logger` queue for job_id, streams events until `job_complete`.
Sends `ping` heartbeat every 45 seconds.

---

### `GET /api/result/{job_id}`
**Returns:** Full job dict from Redis (includes `result` key with `TravelPlan` data)

---

### `POST /api/generate-output/{job_id}/{file_type}`
`file_type`: `pdf` or `pptx`
**Returns:** File download (FileResponse)

---

### `GET /health`
**Returns:** `{"status": "ok", "active_jobs": N}`

---

## SSE Event Types

All events sent as `EventSource` named events. Each carries a JSON payload.

| Event | Payload | When |
|-------|---------|------|
| `debug_log` | `{level, message, agent?, data?, ts}` | Any agent log line |
| `route_ready` | `{stops: StopOption[]}` | After route confirmed, before research |
| `accommodation_loading` | `{stop_id, region, country}` | Before fetching acc options for a stop |
| `accommodation_loaded` | `{stop_id, stop, options: AccommodationOption[3]}` | After acc options fetched |
| `accommodations_all_loaded` | `{total_stops}` | All stops have acc options |
| `stop_research_started` | `{stop_id, region, section}` | Before activities or restaurants |
| `activities_loaded` | `{stop_id, region, activities: StopActivity[]}` | After activities fetched |
| `restaurants_loaded` | `{stop_id, region, restaurants: Restaurant[]}` | After restaurants fetched |
| `stop_done` | `{stop_id, region, accommodation, top_activities[], restaurants[]}` | After all research for a stop |
| `agent_start` | `{agent_id, message}` | Named agent begins |
| `agent_done` | `{agent_id, message}` | Named agent completes |
| `job_complete` | Full `TravelPlan` dict | Planning finished |
| `job_error` | `{error: string}` | Any unhandled exception |

---

## Redis Job State

Key: `job:{job_id}` (JSON string, TTL 24h)

```json
{
  "status": "building_route | loading_accommodations | selecting_accommodations | accommodations_confirmed | pending | running | complete | error",
  "request": { /* TravelRequest dict */ },
  "selected_stops": [],
  "current_options": [],
  "route_could_be_complete": false,
  "stop_counter": 0,
  "segment_index": 0,
  "segment_budget": 10,
  "segment_stops": [],
  "selected_accommodations": [],
  "current_acc_options": [],
  "accommodation_index": 0,
  "prefetched_accommodations": {},
  "all_accommodations_loaded": false,
  "result": null,
  "error": null
}
```

---

## Celery Tasks

### `tasks/prefetch_accommodations.py`
```python
@celery_app.task
def prefetch_accommodations_task(job_id: str):
    """Runs _prefetch_all_accommodations() in asyncio event loop."""
    asyncio.run(_prefetch_all_accommodations(job_id))
```

### `tasks/run_planning_job.py`
```python
@celery_app.task
def run_planning_job_task(job_id: str):
    """Runs TravelPlannerOrchestrator.run() in asyncio event loop."""
    asyncio.run(_run_job(job_id))
```

Celery worker: `celery -A tasks worker --loglevel=info`
Broker + backend: Redis (`REDIS_URL` env var)

---

## Agent Implementations

### 1. `RouteArchitectAgent` (route_architect.py)
**Model:** `claude-opus-4-5` (prod) / `claude-haiku-4-5` (test)
**Input:** TravelRequest
**Output JSON:**
```json
{
  "stops": [
    {"id": 1, "region": "Annecy", "country": "FR", "arrival_day": 2,
     "nights": 2, "drive_hours": 3.5, "is_fixed": false, "notes": "..."}
  ],
  "total_drive_days": 3,
  "total_rest_days": 7,
  "ferry_crossings": []
}
```
**System prompt:** "Du bist ein Reiseplaner für Familien. Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."

**Prompt includes:** start, via_points (with fixed dates), main_destination, total_days, start_date–end_date, adults, children ages, travel_styles, max_drive_hours_per_day, min/max_nights_per_stop, budget_chf, mandatory_activities, travel_description.

---

### 2. `StopOptionsFinderAgent` (stop_options_finder.py)
**Model:** `claude-sonnet-4-5` (prod) / `claude-haiku-4-5` (test)
**Input:** TravelRequest + `selected_stops[]` + `stop_number` + `days_remaining` + `route_could_be_complete` + `segment_target`
**Output JSON:**
```json
{
  "options": [
    {"id": 1, "option_type": "direct", "region": "Annecy", "country": "FR",
     "drive_hours": 3.5, "nights": 2, "highlights": ["Lac Annecy", "Vieille ville"],
     "teaser": "Idyllische Alpenstadt..."},
    {"id": 2, "option_type": "scenic", ...},
    {"id": 3, "option_type": "cultural", ...}
  ],
  "estimated_total_stops": 4,
  "route_could_be_complete": false
}
```
**Key logic:**
- Always generate exactly 3 options: direct, scenic, cultural
- Validate drive times via Nominatim + OSRM (replacing Claude estimates)
- Segment-aware: knows `Segment N of M` towards `segment_target`
- If `route_could_be_complete=true`: one option should complete the route to target
- `max_drive_hours` constraint must be respected

**Drive time validation:**
```python
# After Claude proposes options, for each option:
coord_prev = await geocode_nominatim(prev_stop_region, prev_country)
coord_next = await geocode_nominatim(option.region, option.country)
if coord_prev and coord_next:
    hours, km = await osrm_route([coord_prev, coord_next])
    option["drive_hours"] = hours
    option["drive_km"] = km
```

---

### 3. `AccommodationResearcherAgent` (accommodation_researcher.py)
**Model:** `claude-sonnet-4-5` (prod) / `claude-haiku-4-5` (test)
**Method:** `find_options(stop: dict, budget_per_night: float, semaphore=None)`
**Output JSON:**
```json
{
  "stop_id": 1,
  "region": "Annecy",
  "options": [
    {"id": "acc_1_budget", "option_type": "budget", "name": "...", "type": "hotel",
     "price_per_night_chf": 85, "total_price_chf": 170, "price_range": "€",
     "separate_rooms_available": false, "max_persons": 4, "rating": 7.5,
     "features": ["WiFi", "Parkplatz"], "teaser": "...",
     "suitable_for_children": true, "booking_hint": "booking.com"},
    {"id": "acc_1_comfort", "option_type": "comfort", ...},
    {"id": "acc_1_premium", "option_type": "premium", ...}
  ]
}
```
**Budget tiers:**
- Budget: 65% of `budget_per_night * (1 - buffer_percent/100)`
- Comfort: 100% of effective rate
- Premium: 160% of effective rate

**Semaphore:** Pass `asyncio.Semaphore(2)` from `_prefetch_all_accommodations` for parallel calls.

---

### 4. `ActivitiesAgent` (activities_agent.py)
**Model:** `claude-sonnet-4-5` (prod) / `claude-haiku-4-5` (test)
**Method:** `run_stop(stop: dict)`
**Output JSON:**
```json
{
  "stop_id": 1,
  "region": "Annecy",
  "top_activities": [
    {"name": "Bootsfahrt Lac d'Annecy", "description": "...",
     "duration_hours": 2.0, "price_chf": 25, "suitable_for_children": true,
     "notes": "...", "address": "...", "google_maps_url": "...",
     "image_url": "https://...", "image_urls": ["https://...", "https://..."]}
  ]
}
```
**WikipediaEnricher:** After Claude proposes activities, fetch up to 4 Wikipedia images per activity:
1. `GET https://en.wikipedia.org/w/api.php?action=query&titles={activity_name}&prop=pageimages|images&format=json`
2. Batch imageinfo for thumbnails: `action=query&titles={img_titles}&prop=imageinfo&iiprop=url&iiurlwidth=800`
3. Filter: skip file names matching `/(logo|icon|map|symbol|flag|coat|seal|blank)/i`
4. Sleep 400ms between activities to respect Wikipedia rate limits.

---

### 5. `RestaurantsAgent` (restaurants_agent.py)
**Model:** `claude-sonnet-4-5` (prod) / `claude-haiku-4-5` (test)
**Method:** `run_stop(stop: dict)`
**Output JSON:**
```json
{
  "stop_id": 1,
  "region": "Annecy",
  "restaurants": [
    {"name": "Le Clos des Sens", "cuisine": "Französisch",
     "price_range": "€€€", "family_friendly": false, "notes": "..."}
  ]
}
```
**Budget:** ~15% of total_budget / persons / total_days (CHF per meal per person)
**Prompt includes:** travel_styles, activities_radius_km, children count, max_restaurants_per_stop.

---

### 6. `DayPlannerAgent` (day_planner.py)
**Model:** `claude-opus-4-5` (prod) / `claude-haiku-4-5` (test)
**Input:** `route: dict`, `accommodations: list`, `activities: list`
**Output JSON:**
```json
{
  "day_plans": [
    {"day": 1, "type": "drive", "title": "Abreise nach Annecy",
     "description": "...", "stops_on_route": ["Basel", "Mulhouse"]}
  ],
  "cost_estimate": {
    "accommodations_chf": 1800, "ferries_chf": 0, "activities_chf": 400,
    "food_chf": 700, "fuel_chf": 200, "total_chf": 3100, "budget_remaining_chf": 1900
  }
}
```
**Key logic:**
1. `_build_stops()`: merge route + accommodations + activities; normalize `drive_hours` → `drive_hours_from_prev`
2. `_enrich_with_osrm()`:
   - Geocode all locations sequentially (sleep 350ms between calls)
   - OSRM calls in parallel (`asyncio.gather`)
   - Store `lat`, `lng`, `drive_hours_from_prev`, `drive_km_from_prev` on each stop
3. Claude only generates `day_plans` + `cost_estimate` (small output)
4. `_fallback_cost_estimate()`: if Claude doesn't return cost_estimate:
   - Accommodations: from stop data (or CHF 120/night fallback)
   - Activities: CHF 80 × num_stops
   - Food: CHF 50 × total_nights
   - Fuel: drive_hours_total × CHF 12/h

---

### 7. `OutputGeneratorAgent` (output_generator.py)
**Methods:** `_create_pdf(plan: dict, output_dir: Path)` → Path, `_create_pptx(plan: dict, output_dir: Path)` → Path
**PDF:** fpdf2 — cover page, stops table, day plan list, cost summary
**PPTX:** python-pptx — title slide + one slide per stop + cost summary slide
Called on-demand via `POST /api/generate-output/{job_id}/{type}`.

---

## Utility Modules

### `utils/debug_logger.py`

```python
import asyncio
from enum import Enum
from datetime import datetime

class LogLevel(str, Enum):
    DEBUG   = "DEBUG"
    INFO    = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR   = "ERROR"
    AGENT   = "AGENT"
    API     = "API"

class DebugLogger:
    def __init__(self):
        self._subscribers: dict[str, asyncio.Queue] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=200)
        self._subscribers[job_id] = q
        return q

    def unsubscribe(self, job_id: str):
        self._subscribers.pop(job_id, None)

    async def log(self, level: LogLevel, message: str, *,
                  job_id: str = None, agent: str = None, data: dict = None):
        # Terminal output (ANSI colors)
        color = {
            LogLevel.DEBUG: "\033[94m", LogLevel.INFO: "\033[96m",
            LogLevel.SUCCESS: "\033[92m", LogLevel.WARNING: "\033[93m",
            LogLevel.ERROR: "\033[91m", LogLevel.AGENT: "\033[95m",
            LogLevel.API: "\033[94m",
        }.get(level, "")
        prefix = f"[{agent}] " if agent else ""
        print(f"{color}[{level.value}] {prefix}{message}\033[0m")

        # SSE push
        if job_id and job_id in self._subscribers:
            await self._subscribers[job_id].put({
                "type": "debug_log",
                "level": level.value,
                "message": message,
                "agent": agent,
                "data": data,
                "ts": datetime.now().isoformat(),
            })

    async def push_event(self, job_id: str, event_type: str,
                         agent_id, data, percent: int = 0):
        if job_id in self._subscribers:
            await self._subscribers[job_id].put({
                "type": event_type,
                "agent_id": agent_id,
                "data": data,
                "percent": percent,
            })

debug_logger = DebugLogger()   # module-level singleton
```

---

### `utils/maps_helper.py`

```python
import asyncio
import aiohttp
from typing import Optional

async def geocode_nominatim(place: str, country_code: str = "") -> Optional[tuple[float, float]]:
    """Returns (lat, lon) or None. Max 1 req/s — caller must sleep."""
    params = {"q": place, "format": "json", "limit": 1}
    if country_code:
        params["countrycodes"] = country_code.lower()
    async with aiohttp.ClientSession() as s:
        async with s.get("https://nominatim.openstreetmap.org/search",
                         params=params,
                         headers={"User-Agent": "Travelman2/1.0"}) as r:
            data = await r.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    return None

async def osrm_route(coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Returns (hours, km). coords = [(lat,lon), ...]"""
    points = ";".join(f"{lon},{lat}" for lat, lon in coords)
    url = f"http://router.project-osrm.org/route/v1/driving/{points}?overview=false"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            data = await r.json()
            if data.get("routes"):
                route = data["routes"][0]
                hours = round(route["duration"] / 3600, 1)
                km    = round(route["distance"] / 1000, 0)
                return hours, km
    return 0.0, 0.0

def build_maps_url(locations: list[str]) -> Optional[str]:
    """Builds Google Maps Directions URL."""
    locs = [l for l in locations if l]
    if not locs:
        return None
    if len(locs) == 1:
        return f"https://maps.google.com/?q={locs[0].replace(' ', '+')}"
    origin = locs[0].replace(' ', '+')
    dest   = locs[-1].replace(' ', '+')
    wp     = '|'.join(l.replace(' ', '+') for l in locs[1:-1])
    url    = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}"
    if wp:
        url += f"&waypoints={wp}"
    return url
```

---

### `utils/retry_helper.py`

```python
import asyncio
import random
from anthropic import RateLimitError
from utils.debug_logger import LogLevel, debug_logger

async def call_with_retry(fn, *, job_id: str = None, agent_name: str = None,
                          max_attempts: int = 5):
    """Wraps a blocking Anthropic SDK call with exponential backoff on 429."""
    for attempt in range(1, max_attempts + 1):
        try:
            return await asyncio.to_thread(fn)
        except RateLimitError:
            if attempt == max_attempts:
                raise
            delay = 2 ** (attempt - 1) + random.random()
            await debug_logger.log(
                LogLevel.WARNING,
                f"Rate limit (attempt {attempt}/{max_attempts}) — retry in {delay:.1f}s",
                job_id=job_id, agent=agent_name,
            )
            await asyncio.sleep(delay)
```

---

### `utils/json_parser.py`

```python
import json
import re

def parse_agent_json(text: str) -> dict:
    """Strips markdown code fences and parses JSON."""
    text = text.strip()
    text = re.sub(r'^```[a-z]*\n?', '', text)
    text = re.sub(r'\n?```$', '', text)
    text = text.strip()
    return json.loads(text)
```

---

## Orchestrator (`backend/orchestrator.py`)

```python
class TravelPlannerOrchestrator:

    async def run(self, pre_built_stops=None, pre_selected_accommodations=None) -> dict:

        # Phase 1: Route
        if pre_built_stops:
            stops = pre_built_stops
            # assign arrival_day if missing
        else:
            route = await RouteArchitectAgent(self.request, self.job_id).run()
            stops = route.get("stops", [])

        await self.progress("route_ready", "route", {"stops": stops}, 10)

        # Phase 2: Research
        if pre_selected_accommodations:
            all_accommodations = pre_selected_accommodations
            # Run ALL stops' activities + restaurants in parallel
            # Each fires activities_loaded + restaurants_loaded SSE events when done
            # Internally limited by Semaphore(2) inside each agent
            act_map, rest_map = {}, {}

            async def research_activities(stop, idx):
                result = await ActivitiesAgent(...).run_stop(stop)
                act_map[stop["id"]] = result
                await self.progress("activities_loaded", ...)

            async def research_restaurants(stop, idx):
                result = await RestaurantsAgent(...).run_stop(stop)
                rest_map[stop["id"]] = result
                await self.progress("restaurants_loaded", ...)

            tasks = []
            for idx, stop in enumerate(stops):
                tasks.append(research_activities(stop, idx))
                tasks.append(research_restaurants(stop, idx))
            await asyncio.gather(*tasks)

            # merge results + send stop_done per stop
            all_activities = [merge(act_map[s["id"]], rest_map[s["id"]]) for s in stops]

        else:
            # Sequential: accommodation + activities + restaurants per stop
            for i, stop in enumerate(stops):
                acc, act, rest = await asyncio.gather(
                    AccommodationResearcherAgent(...).run_stop(stop),
                    ActivitiesAgent(...).run_stop(stop),
                    RestaurantsAgent(...).run_stop(stop),
                )
                # send SSE events for each

        # Phase 3: Day Planner
        plan = await DayPlannerAgent(...).run(route, all_accommodations, all_activities)

        # Final
        await self.progress("job_complete", None, plan, 100)
        return plan
```

---

## Main.py — Key Logic

### Segment Budget Calculation
```python
def _calc_segment_budget(request, seg_idx):
    """Distributes total_days across N segments (N = len(via_points)+1)."""
    n = len(request.via_points) + 1
    days = [request.total_days // n] * n
    for i in range(request.total_days % n):
        days[i] += 1
    min_days = (request.min_nights_per_stop + 1) * 2
    return max(min_days, days[seg_idx] if seg_idx < n else days[-1])
```

### Route Status
```python
def _calc_route_status(request, segment_stops, segment_budget, is_last_segment):
    """Determines must_complete and route_could_be_complete for current segment."""
    days_used = sum(1 + s.get("nights", request.min_nights_per_stop) for s in segment_stops)
    days_remaining = max(0, segment_budget - days_used)
    reserve = 1 + request.min_nights_per_stop   # drive day + stay at target
    effective_days = days_remaining - reserve
    one_more_stop = 1 + request.min_nights_per_stop

    must_complete  = effective_days <= 0
    could_complete = 0 < effective_days <= one_more_stop and len(segment_stops) >= 1

    return {
        "days_remaining": days_remaining,
        "must_complete": must_complete,
        "route_could_be_complete": could_complete or must_complete,
    }
```

### Budget State
```python
def _calc_budget_state(request, selected_stops, selected_accommodations):
    """45% of total budget → accommodation."""
    acc_budget = request.budget_chf * 0.45
    total_nights = sum(s.get("nights", request.min_nights_per_stop) for s in selected_stops)
    spent = sum(a["option"].get("total_price_chf", 0) for a in selected_accommodations)
    # ... returns BudgetState dict
```

### Via-Point Insertion (in `/api/select-stop`)
When `must_complete=True` and NOT the last segment:
1. Insert via-point stop into `selected_stops` with `option_type: "via_point"`, `is_fixed: True`
2. Increment `segment_index`
3. Recalculate `segment_budget` for new segment
4. Call `StopOptionsFinderAgent` for new segment immediately
5. Return `segment_complete: True`, `via_point_added: {...}` in response

### Destination Appending (in `/api/confirm-route`)
If `main_destination` not already in `selected_stops`:
- Calculate `dest_nights` = `clamp(days_remaining - 1, min_nights, max_nights)`
- Estimate `drive_hours` from average of known stops
- Append as `option_type: "direct"`

---

## Frontend Modules

### `frontend/js/state.js`
Global state object `S`, constants, and utilities:

```javascript
const TRAVEL_STYLES = [
  { id: 'adventure',    label: 'Abenteuer',     icon: `<svg>...</svg>` },
  { id: 'relaxation',  label: 'Entspannung',   icon: `<svg>...</svg>` },
  { id: 'culture',     label: 'Kultur',         icon: `<svg>...</svg>` },
  { id: 'romantic',    label: 'Romantik',       icon: `<svg>...</svg>` },
  { id: 'culinary',    label: 'Kulinarisch',    icon: `<svg>...</svg>` },
  { id: 'road_trip',   label: 'Road Trip',      icon: `<svg>...</svg>` },
  { id: 'nature',      label: 'Natur',          icon: `<svg>...</svg>` },
  { id: 'city',        label: 'Städtereise',    icon: `<svg>...</svg>` },
  { id: 'wellness',    label: 'Wellness & Spa', icon: `<svg>...</svg>` },
  { id: 'sport',       label: 'Sport & Outdoor',icon: `<svg>...</svg>` },
  { id: 'group',       label: 'Gruppenreise',   icon: `<svg>...</svg>` },
  { id: 'kids',        label: 'Familienaktiv.', icon: `<svg>...</svg>` },
  { id: 'slow_travel', label: 'Slow Travel',    icon: `<svg>...</svg>` },
  { id: 'party',       label: 'Nightlife',      icon: `<svg>...</svg>` },
];

const FLAGS = { CH:'🇨🇭', FR:'🇫🇷', DE:'🇩🇪', IT:'🇮🇹', AT:'🇦🇹',
                ES:'🇪🇸', NL:'🇳🇱', BE:'🇧🇪', PT:'🇵🇹', GB:'🇬🇧' };

const S = {
  step: 1, adults: 2, children: [], travelStyles: [], mandatoryTags: [],
  jobId: null, sse: null, logs: [], apiCalls: 0, debugOpen: false, result: null,
  // Route Builder
  selectedStops: [], currentOptions: [], loadingOptions: false, confirmingRoute: false,
  // Accommodation Phase
  allStops: [], selectedAccommodations: [], prefetchedOptions: {},
  pendingSelections: {}, allAccLoaded: false, accSelectionCount: 0,
};
```

**localStorage keys:**
- `tp_v1_form` → TravelRequest form fields
- `tp_v1_route` → `{jobId, stops: {id: StopOption}, stopsOrder: [id,...]}`
- `tp_v1_accommodations` → `{jobId, accommodations, allStops, prefetchedOptions, pendingSelections}`
- `tp_v1_result` → `{jobId, savedAt: ISO, plan: TravelPlan}`

**Resume logic:** On load, detect highest phase from localStorage and show resume banner.

---

### `frontend/js/api.js`
All API calls and SSE. No fetch() calls anywhere else.

```javascript
const API = '/api';  // Nginx proxy — no localhost port

async function apiPlanTrip(payload) { ... }
async function apiSelectStop(jobId, idx) { ... }
async function apiConfirmRoute(jobId) { ... }
async function apiSelectAccommodation(jobId, stopId, idx) { ... }
async function apiConfirmAccommodations(jobId, selections) { ... }
async function apiStartPlanning(jobId) { ... }
async function apiGetResult(jobId) { ... }
async function apiGenerateOutput(jobId, type) { ... }  // returns blob

function openSSE(jobId, handlers) {
  const source = new EventSource(`${API}/progress/${jobId}`);
  const events = [
    'debug_log', 'route_ready', 'stop_done', 'agent_start', 'agent_done',
    'job_complete', 'job_error', 'accommodation_loading', 'accommodation_loaded',
    'accommodations_all_loaded', 'stop_research_started', 'activities_loaded', 'restaurants_loaded',
  ];
  // register each handler
  return source;
}
```

**Important:** `API = '/api'` (Nginx proxy path, not `http://localhost:8000/api`)

---

### `frontend/js/form.js`
5-step form:
- **Step 1:** Start → Via-points (add/remove/toggle-date) → End + date range
- **Step 2:** Traveller counter + travel style grid (14 cards, multi-select SVG icons)
- **Step 3:** Tag-input for mandatory activities + hotel radius + activities radius sliders
- **Step 4:** Accommodation type grid + must-haves grid + drive sliders + budget input
- **Step 5:** Summary before submit

Key functions: `buildPayload()`, `submitTrip()`, `renderSummary()`, `addViaPoint()`,
`removeViaPoint(idx)`, `toggleViaDate(idx)`, `initTravelStyles()`, `toggleStyle(card)`,
`addTagFromInput()`, `removeTag(name)`, `renderTags()`,
`setupFormAutoSave()`, `restoreFormFromCache()`.

---

### `frontend/js/route-builder.js`
Interactive stop selection.

Key functions: `startRouteBuilding()`, `renderOptions(options, meta)`, `selectOption(idx)`,
`searchNextStop()`, `confirmRoute()`, `backToForm()`, `saveRouteState()`, `addBuiltStop(stop)`.

`confirmRoute()`:
1. Calls `apiConfirmRoute(jobId)`
2. Immediately calls `connectAccommodationSSE(jobId)` to open SSE before accommodation phase

---

### `frontend/js/accommodation.js`
Parallel accommodation loading + selection grid.

Key functions: `connectAccommodationSSE(jobId)`, `startAccommodationPhase(data)`,
`buildAllStopPanels(stops)`, `handleAccommodationLoaded(data)`,
`selectAccommodationInPanel(stopId, optionIdx)`,
`startPlanningWithAllSelections()`, `redoRoute()`.

**Flow:**
1. SSE `accommodation_loading` → show shimmer for stop panel
2. SSE `accommodation_loaded` → render 3 budget/comfort/premium cards in panel
3. SSE `accommodations_all_loaded` → enable "Start Planning" button
4. User selects one option per stop panel
5. "Start Planning" → `apiConfirmAccommodations(jobId, pendingSelections)` → `apiStartPlanning(jobId)`

---

### `frontend/js/progress.js`
SSE progress handlers during full planning.

Key functions: `connectSSE(jobId)`, `buildStopsTimeline(stops)`,
`onRouteReady(data)`, `onStopDone(data)`, `onActivitiesLoaded(data)`,
`onRestaurantsLoaded(data)`, `onJobComplete(data)`, `markAllStopsDone()`.

Shimmer pattern: each stop section shows loading shimmer until its event arrives,
then replaces shimmer with real content.

---

### `frontend/js/guide.js`
Travel guide rendering (main output).

Key functions: `showTravelGuide(plan)`, `switchGuideTab(tab)`,
`renderOverview(plan)`, `renderStops(plan)`, `renderDayPlan(plan)`,
`renderBudget(plan)`, `generateOutput(type)`, `loadGuideFromCache()`.

**4 tabs:** Übersicht · Stops & Details · Tagesplan · Budget

`renderBudget`: always use `typeof check` before accessing cost_estimate fields:
```javascript
const cost = plan.cost_estimate || {};
const total = typeof cost.total_chf === 'number' ? cost.total_chf : 0;
```

---

## Docker & Nginx Configuration

### `docker-compose.yml`
```yaml
version: '3.9'
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  backend:
    build:
      context: .
      dockerfile: infra/Dockerfile.backend
    ports: ["8000:8000"]
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - TEST_MODE=${TEST_MODE:-true}
      - REDIS_URL=redis://redis:6379
    depends_on: [redis]
    volumes:
      - ./outputs:/app/outputs

  celery:
    build:
      context: .
      dockerfile: infra/Dockerfile.backend
    command: celery -A tasks worker --loglevel=info
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - TEST_MODE=${TEST_MODE:-true}
      - REDIS_URL=redis://redis:6379
    depends_on: [redis]

  frontend:
    build:
      context: .
      dockerfile: infra/Dockerfile.frontend
    ports: ["80:80"]
    depends_on: [backend]
```

### `infra/Dockerfile.backend`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `infra/Dockerfile.frontend`
```dockerfile
FROM nginx:alpine
COPY frontend/ /usr/share/nginx/html/
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
```

### `infra/nginx.conf`
```nginx
server {
    listen 80;

    # Serve frontend static files
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # Proxy API calls to FastAPI
    location /api/ {
        proxy_pass http://backend:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection '';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        # SSE support
        proxy_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        chunked_transfer_encoding on;
    }
}
```

---

## `backend/requirements.txt`
```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
sse-starlette>=1.8.2
anthropic>=0.28.0
python-dotenv>=1.0.1
pydantic>=2.7.0
aiohttp>=3.9.5
redis>=5.0.4
celery>=5.4.0
fpdf2>=2.7.9
python-pptx>=0.6.23
```

---

## `scripts/generate-types.sh`
```bash
#!/bin/bash
set -e
echo "Starting FastAPI server for OpenAPI spec..."
cd backend
uvicorn main:app --host 127.0.0.1 --port 18765 &
SERVER_PID=$!
sleep 2

echo "Generating TypeScript types..."
npx openapi-typescript http://127.0.0.1:18765/openapi.json \
    --output ../frontend/js/types.d.ts

kill $SERVER_PID
echo "Done: frontend/js/types.d.ts"
```

---

## Test Suite (`backend/tests/`)

### `conftest.py`
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def sample_request():
    return {
        "start_location": "Liestal, Schweiz",
        "main_destination": "Paris, Frankreich",
        "start_date": "2026-06-01",
        "end_date": "2026-06-10",
        "total_days": 10,
        "adults": 2,
        "children": [],
        "budget_chf": 5000,
        "travel_styles": ["culture", "culinary"],
    }
```

### `test_models.py`
```python
def test_travel_request_valid(sample_request):
    from models.travel_request import TravelRequest
    req = TravelRequest(**sample_request)
    assert req.adults == 2
    assert req.budget_chf == 5000

def test_child_age_invalid():
    with pytest.raises(ValueError):
        Child(age=25)

def test_via_point_optional_date():
    vp = ViaPoint(location="Bern")
    assert vp.fixed_date is None

def test_accommodation_option_types():
    # test budget/comfort/premium option_type validation
    ...
```

### `test_endpoints.py`
```python
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_plan_trip_missing_field(client):
    r = client.post("/api/plan-trip", json={"start_location": "A"})
    assert r.status_code == 422

def test_select_stop_job_not_found(client):
    r = client.post("/api/select-stop/fakeid", json={"option_index": 0})
    assert r.status_code == 404

def test_confirm_route_no_stops(client, sample_request, mocker):
    # mock StopOptionsFinderAgent
    ...
```

### `test_agents_mock.py`
```python
def test_route_architect_json_parsing(mocker):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"stops": [], "total_drive_days": 2, ...}')],
        usage=MagicMock(input_tokens=100, output_tokens=50),
    )
    mocker.patch('anthropic.Anthropic', return_value=mock_client)
    # run agent and assert output structure

def test_retry_on_rate_limit(mocker):
    # mock RateLimitError on first call, success on second
    ...

def test_parse_agent_json_strips_fences():
    from utils.json_parser import parse_agent_json
    raw = '```json\n{"stops": []}\n```'
    assert parse_agent_json(raw) == {"stops": []}
```

---

## Implementation Phases

### Phase 1: Project Scaffold + Docker
1. Create all directories (backend/, frontend/, infra/, scripts/, outputs/)
2. Create `backend/.env.example` with all env vars
3. Create `backend/requirements.txt`
4. Create `docker-compose.yml`
5. Create `infra/Dockerfile.backend`, `infra/Dockerfile.frontend`
6. Create `infra/nginx.conf`
7. Create `scripts/generate-types.sh` (chmod +x)
8. Create `CLAUDE.md` (copy from rebuild spec)
9. **Verify:** `docker compose build` succeeds; `docker compose up` starts all services;
   `curl http://localhost/health` returns 200

### Phase 2: Data Models + Type Generation
1. Create all 4 Pydantic model files (travel_request, travel_response, stop_option, accommodation_option)
2. Create minimal `backend/main.py` (FastAPI app with `/health` and OpenAPI enabled)
3. Create `backend/models/__init__.py`
4. Run `scripts/generate-types.sh` → verify `frontend/js/types.d.ts` generated
5. **Verify:** All models importable; no Pydantic validation errors on sample data

### Phase 3: Backend Core (API + Redis Job State)
1. Create all 4 utility modules (debug_logger, maps_helper, retry_helper, json_parser)
2. Implement full `backend/main.py` with all 11 endpoints
   - Replace `active_jobs: dict` with Redis (`redis.from_url(REDIS_URL)`)
   - Job state: `redis_client.setex(f"job:{job_id}", 86400, json.dumps(job_dict))`
   - Helper: `get_job(job_id)` reads + parses from Redis, raises 404 if missing
   - Helper: `save_job(job_id, job_dict)` serializes + saves to Redis
3. Create `backend/tasks/__init__.py` with Celery app init
4. Create Celery task stubs (run_planning_job, prefetch_accommodations)
5. **Verify:** `POST /api/plan-trip` with sample request → returns job_id + options stub

### Phase 4: All 6 Agents + Orchestrator
1. Implement each agent in order: route_architect → stop_options_finder →
   accommodation_researcher → activities_agent (+ WikipediaEnricher) → restaurants_agent → day_planner
2. Implement output_generator (PDF + PPTX)
3. Implement `backend/orchestrator.py`
4. Wire Celery tasks to orchestrator.run() + prefetch logic
5. **Verify (TEST_MODE=true):** Run full trip from Liestal → Paris, 10 days, CHF 5000.
   All endpoints return valid data. SSE streams through job_complete event.

### Phase 5: Frontend (7 JS modules)
1. Create `frontend/index.html` — all HTML structure including 5-step form, route-builder,
   accommodation-builder, progress, travel-guide sections. Include all 7 JS modules as `<script>` tags.
2. Create `frontend/styles.css` — Apple-inspired design (#f5f5f7 bg, #0071e3 accent,
   Inter font). Include form, route-builder, accommodation grid, progress timeline,
   travel-guide styles.
3. Create each JS module in order: state.js → api.js → form.js → route-builder.js →
   accommodation.js → progress.js → guide.js
4. **Verify:** Open `http://localhost` in browser. Complete full flow: form → route selection →
   accommodation selection → planning progress → travel guide.

### Phase 6: Tests + Final Verification
1. Create `backend/tests/conftest.py`
2. Create `test_models.py`, `test_endpoints.py`, `test_agents_mock.py`
3. Run `python3 -m pytest tests/ -v` → all tests pass
4. **End-to-end checklist:**
   - [ ] `GET /health` → 200
   - [ ] `POST /api/plan-trip` with sample request → job_id + 3 stop options
   - [ ] `POST /api/select-stop/{id}` → next 3 options
   - [ ] `POST /api/confirm-route/{id}` → starts acc prefetch, returns budget_state
   - [ ] SSE `accommodation_loading` / `accommodation_loaded` per stop
   - [ ] SSE `accommodations_all_loaded` when all stops done
   - [ ] `POST /api/confirm-accommodations/{id}` → accommodations_confirmed
   - [ ] `POST /api/start-planning/{id}` → planning_started
   - [ ] SSE `activities_loaded` + `restaurants_loaded` per stop
   - [ ] SSE `job_complete` with full TravelPlan
   - [ ] Travel guide renders with all 4 tabs
   - [ ] `POST /api/generate-output/{id}/pdf` → downloads PDF
   - [ ] `python3 -m pytest tests/ -v` → all green
   - [ ] `docker compose up` → full stack running

---

## Key Conventions (non-negotiable)

- All user-visible text **in German**
- Prices always **in CHF**
- Agents return **only valid JSON** — no markdown, no explanations
- `TEST_MODE=true` → all agents use `claude-haiku-4-5`
- Job state stored in **Redis** (not in-memory dict)
- Claude API calls always through **`call_with_retry()`**
- Agent JSON always parsed through **`parse_agent_json()`**
- Every API call logged with **`debug_logger.log(LogLevel.API, ...)`**
- `esc()` on all user content before HTML insertion (XSS prevention)
- Frontend `API = '/api'` (Nginx proxy, not `http://localhost:8000/api`)
- Nominatim: sleep **350ms** between geocode calls

---

## Test Trip
Use this throughout development to verify the full flow:
- **Start:** Liestal, Schweiz
- **Destination:** Französische Alpen → Paris, Frankreich
- **Duration:** 10 Tage (01.06.2026 – 10.06.2026)
- **Travellers:** 2 Erwachsene
- **Max drive:** 4.5h/day
- **Budget:** CHF 5'000
- **Travel styles:** culture, culinary

---

## Start Commands Summary

```bash
# Development (local)
cd backend && python3 -m uvicorn main:app --reload --port 8000
# Open frontend/index.html directly in browser (or via Nginx)

# Docker (production-like)
docker compose up --build

# Tests
cd backend && python3 -m pytest tests/ -v

# Celery worker (separate terminal)
cd backend && celery -A tasks worker --loglevel=info

# Type generation
bash scripts/generate-types.sh
```
